#!/usr/bin/env python3
"""Project discovery and coordinated builds, shared by hooks and MCP (stdlib only).

CLI accepts a JSON object on stdin and returns JSON on stdout. Builds run in
their own session under a supervisor that kills the whole group on
cancellation, timeout or loss of its parent.
"""
import ast
import configparser
import fcntl
import fnmatch
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import tomllib

# Isolated interpreters (-I) do not prepend the script directory.
_RUNTIME_DIR = str(Path(__file__).resolve().parent)
if _RUNTIME_DIR not in sys.path:
    sys.path.insert(0, _RUNTIME_DIR)
from source_inventory import ignored_directory, read_regular, source_files  # noqa: E402


class BuildCancelled(RuntimeError):
    pass


class DiscoveryError(ValueError):
    def __init__(self, message, is_fastapi=False):
        super().__init__(message)
        self.is_fastapi = is_fastapi


BUILD_FILES = ('pyproject.toml', 'requirements.txt', 'setup.cfg', 'setup.py')
LOCK_FILES = ('uv.lock', 'poetry.lock')
FASTAPI_DISTRIBUTIONS = {'fastapi', 'fastapi-slim'}
# Variables that identify an invocation or a host adapter, not build inputs.
INVOCATION_ENV = {'CLAUDE_PROJECT_DIR', 'CLAUDE_PLUGIN_ROOT', 'CLAUDE_PLUGIN_DATA', 'CLAUDE_SESSION_ID', 'CLAUDE_ENV_FILE',
                  'CODEX_THREAD_ID', 'MCP_SERVER_NAME', 'PROJECT_ROOT', 'FASTAPI_APP_PORT', 'PWD', 'OLDPWD', 'SHLVL', '_'}
INVOCATION_PREFIXES = ('CLAUDE_PLUGIN_', 'FASTAPI_TOOLS_')
# Files that tests and applications commonly write while checks run.
GENERATED_FILES = ('.coverage', '.coverage.*', 'coverage.xml', '*.log', '*.db', '*.db-journal', '*.db-wal', '*.db-shm',
                   '*.sqlite', '*.sqlite-journal', '*.sqlite-wal', '*.sqlite-shm',
                   '*.sqlite3', '*.sqlite3-journal', '*.sqlite3-wal', '*.sqlite3-shm')
TASKS = {'compile', 'lint', 'typecheck', 'test', 'verify', 'package', 'dependencies', 'migration-status'}
TEST_PATH = re.compile(r'[A-Za-z0-9_./-]+(?:::[A-Za-z_][A-Za-z0-9_]*)*(?:::[A-Za-z_][A-Za-z0-9_]*\[[^\x00-\x1f\x7f]{0,512}\])?')


def build_file(folder):
    return next((name for name in BUILD_FILES if (folder / name).is_file()), None)


def find_root(location):
    """Nearest folder with a build file; static helper without trust checks."""
    location = Path(location).resolve()
    folder = location if location.is_dir() else location.parent
    return next((p for p in (folder, *folder.parents) if build_file(p)), None)


def private_group(gid):
    """The user's own primary group with no other members (umask 002 setups)."""
    try:
        account = pwd.getpwuid(os.getuid())
        group = grp.getgrgid(gid)
    except KeyError:
        return False
    return gid == account.pw_gid and group.gr_name == account.pw_name and set(group.gr_mem) <= {account.pw_name}


def writable_by_others(info):
    return bool(info.st_mode & stat.S_IWOTH or (info.st_mode & stat.S_IWGRP and not private_group(info.st_gid)))


def trusted_entry(path, label):
    """An entry another local user could have planted or can rewrite is refused."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if info.st_uid not in (os.getuid(), 0) or (not stat.S_ISLNK(info.st_mode) and writable_by_others(info)):
        raise DiscoveryError(f'Refusing untrusted {label}: {path} is owned by another user or writable by others')
    if stat.S_ISLNK(info.st_mode):
        target = Path(path).resolve()
        if target.exists():
            trusted_entry(target, label + ' target')


def check_trust(root, requested):
    """The requested folder is the user's choice. A build file found in an
    ancestor, and anything executed from it, must belong to the user."""
    if writable_by_others(os.lstat(root)):
        # Includes sticky shared directories such as /tmp and shared group
        # directories: other users can plant files there.
        raise DiscoveryError(f'Refusing project root writable by other users: {root}')
    if root == requested:
        return
    trusted_entry(root, 'ancestor project directory')
    for name in (*BUILD_FILES, *LOCK_FILES, '.venv', 'venv'):
        trusted_entry(root / name, 'ancestor project file')
    for environment in ('.venv', 'venv'):
        trusted_entry(root / environment / 'bin', 'ancestor environment')
        trusted_entry(root / environment / 'bin' / 'python', 'ancestor interpreter')


def ini_config(file):
    parser = configparser.ConfigParser(interpolation=None)
    if file.exists() or file.is_symlink():
        try:
            parser.read_string(read_regular(file).decode('utf-8'))
        except configparser.Error as error:
            raise ValueError(f'Invalid INI configuration: {file}: {error}') from error
    return parser


def pyproject(root):
    config = root / 'pyproject.toml'
    return tomllib.loads(read_regular(config).decode('utf-8')) if config.exists() or config.is_symlink() else {}


def project_metadata(root):
    data = pyproject(root)
    try:
        project, tools = data.get('project', {}), data.get('tool', {})
        dependencies = list(project.get('dependencies', []))
        for group in project.get('optional-dependencies', {}).values():
            dependencies.extend(group)
        for group in data.get('dependency-groups', {}).values():
            dependencies.extend(item for item in group if isinstance(item, str))
        poetry = tools.get('poetry', {})
        for name, version in poetry.get('dependencies', {}).items():
            dependencies.append(f'{name} {version}')
        for name, version in poetry.get('dev-dependencies', {}).items():
            dependencies.append(f'{name} {version}')
        for group in poetry.get('group', {}).values():
            dependencies.extend(f'{name} {version}' for name, version in group.get('dependencies', {}).items())
        setup = ini_config(root / 'setup.cfg')
        dependencies.extend(setup.get('options', 'install_requires', fallback='').splitlines())
        if setup.has_section('options.extras_require'):
            for value in setup['options.extras_require'].values():
                dependencies.extend(value.splitlines())
        for file in sorted(root.glob('requirements*.txt')):
            dependencies.extend(line.strip() for line in read_regular(file).decode('utf-8').splitlines() if line.strip() and not line.lstrip().startswith(('#', '-')))
        dependencies = [dep.strip() for dep in dependencies if dep.strip()]
        names = set()
        for dep in dependencies:
            match = re.match(r'([A-Za-z0-9][A-Za-z0-9._-]*)', dep)
            if match:
                names.add(re.sub(r'[-_.]+', '-', match[1]).lower())
        names.discard('python')  # Poetry declares the interpreter as a dependency.
        checks = {name for name in ('ruff', 'mypy', 'pytest') if name in tools or name in names}
        if any((root / name).exists() or (root / name).is_symlink() for name in ('ruff.toml', '.ruff.toml')):
            checks.add('ruff')
        if any((root / name).exists() or (root / name).is_symlink() for name in ('mypy.ini', '.mypy.ini')) or setup.has_section('mypy'):
            checks.add('mypy')
        if (any((root / name).exists() or (root / name).is_symlink() for name in ('pytest.ini', '.pytest.ini', 'pytest.toml', '.pytest.toml'))
                or setup.has_section('tool:pytest') or ini_config(root / 'tox.ini').has_section('pytest')):
            checks.add('pytest')
        fastapi = bool(names & FASTAPI_DISTRIBUTIONS)
        if not fastapi and not names:
            # Only undeclared projects need source evidence; a project that
            # declares other dependencies is not scanned on every edit.
            fastapi = fastapi_import_evidence(root)
        return {'name': project.get('name') or poetry.get('name') or setup.get('metadata', 'name', fallback=None),
                'requiresPython': project.get('requires-python') or setup.get('options', 'python_requires', fallback=None),
                'dependencies': dependencies, 'isFastAPI': fastapi, 'checks': sorted(checks)}
    except (AttributeError, TypeError) as error:
        raise ValueError('Invalid static Python dependency declarations') from error


def fastapi_import_evidence(root):
    """Fallback evidence when metadata is absent or invalid; never import the app."""
    for file in source_files(root):
        if re.search(r'(?m)^\s*(?:from\s+fastapi\b|import\s+fastapi\b)',
                     read_regular(file).decode('utf-8', 'replace')):
            return True
    return False


def uv_workspace(root, requested):
    """An enclosing uv workspace owns the lockfile and environment of members."""
    for parent in root.parents:
        if (parent / 'uv.lock').is_file() and (parent / 'pyproject.toml').is_file():
            check_trust(parent, requested)
            try:
                tool = pyproject(parent).get('tool', {})
            except (OSError, ValueError):
                return None
            if isinstance(tool, dict) and isinstance(tool.get('uv'), dict) and 'workspace' in tool['uv']:
                return parent
            return None
        if build_file(parent):
            return None
    return None


def environment_python(root):
    candidates = [root / '.venv' / 'bin' / 'python', root / 'venv' / 'bin' / 'python']
    active = os.environ.get('VIRTUAL_ENV')
    if active and Path(active).resolve().is_relative_to(root):
        candidates.append(Path(active) / 'bin' / 'python')
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def discover(location):
    location = Path(location).resolve()
    folder = location if location.is_dir() else location.parent
    root = next((p for p in (folder, *folder.parents) if build_file(p)), None)
    if root is None:
        raise ValueError(f'No Python project found from {location}; expected pyproject.toml or requirements.txt')
    check_trust(root, folder)
    try:
        metadata = project_metadata(root)
    except (OSError, ValueError, TypeError) as error:
        try:
            evidence = fastapi_import_evidence(root)
        except (OSError, ValueError):
            evidence = False
        raise DiscoveryError(str(error), is_fastapi=evidence) from error
    if (root / 'uv.lock').is_file() and (root / 'poetry.lock').is_file():
        raise DiscoveryError('Ambiguous Python managers: both uv.lock and poetry.lock exist; select one explicitly in the project',
                             is_fastapi=metadata['isFastAPI'])
    workspace = None
    if (root / 'uv.lock').is_file():
        tool = 'uv'
    elif (root / 'poetry.lock').is_file():
        tool = 'poetry'
    else:
        workspace = uv_workspace(root, folder)
        tool = 'uv' if workspace else 'python'
    environment_root = workspace or root
    python = environment_python(environment_root)
    return dict(metadata, root=str(root), buildTool=tool, buildFile=build_file(root),
                python=str(python) if python else sys.executable,
                environment=str(python.parent.parent) if python else None,
                workspaceRoot=str(workspace) if workspace else None,
                modules=[], discoveryScope='Nearest Python project; dependencies are declarations, not resolved installations')


def python_command(info):
    if info['buildTool'] in ('uv', 'poetry'):
        tool = shutil.which(info['buildTool'])
        if not tool:
            raise ValueError(f"{info['buildTool']} is required by the project lockfile but is unavailable")
        if info['buildTool'] == 'uv':
            if not info.get('environment') and not os.environ.get('UV_PROJECT_ENVIRONMENT'):
                # uv run would create an empty environment as a side effect.
                expected = Path(info.get('workspaceRoot') or info['root']) / '.venv'
                raise ValueError(f'uv project environment is missing ({expected}); create it explicitly (for example uv sync) before checks')
            # Never install or synchronize dependencies as a side effect of a check.
            return [tool, 'run', '--frozen', '--offline', '--no-sync', 'python']
        return [tool, 'run', 'python']
    return [info['python']]


def mypy_configured_targets(root):
    """mypy treats command-line paths as overriding files/packages/modules."""
    keys = ('files', 'packages', 'modules')
    try:
        section = pyproject(root).get('tool', {}).get('mypy', {})
    except AttributeError:
        section = {}
    if isinstance(section, dict) and any(section.get(key) for key in keys):
        return True
    for name, header in (('mypy.ini', 'mypy'), ('.mypy.ini', 'mypy'), ('setup.cfg', 'mypy')):
        parser = ini_config(root / name)
        if parser.has_section(header) and any(parser.get(header, key, fallback='').strip() for key in keys):
            return True
    return False


def build_plan(request):
    info = discover(request.get('projectRoot') or os.getcwd())
    tasks = request.get('tasks', [request.get('task', 'compile')])
    if not isinstance(tasks, list) or len(tasks) != 1 or not isinstance(tasks[0], str):
        raise ValueError('Exactly one task is required; verify combines all configured checks')
    task = 'verify' if tasks[0] == 'check' else tasks[0]
    if task not in TASKS:
        raise ValueError('Unsupported task; allowed: ' + ', '.join(sorted(TASKS)))
    if request.get('module') is not None or request.get('profiles'):
        raise ValueError('Python checks use the nearest project root; module/profile selectors are unsupported')
    selection = request.get('testPath')
    if selection is not None:
        # One argv element (never a shell), so pytest parameter IDs are safe;
        # options and paths outside the project are refused.
        if task != 'test' or not isinstance(selection, str) or selection.startswith('-') or not TEST_PATH.fullmatch(selection):
            raise ValueError('testPath must be a relative pytest file/directory, optionally ::class::test or ::test[parameter-id]')
        path = selection.split('::')[0]
        file = (Path(info['root']) / path).resolve()
        if Path(path).is_absolute() or not file.is_relative_to(Path(info['root'])) or not file.exists():
            raise ValueError('testPath must exist inside the project root')
    required = {'lint': 'ruff', 'typecheck': 'mypy', 'test': 'pytest'}.get(task)
    if required and required not in info['checks']:
        raise ValueError(f'{required} is not declared or configured in this project')
    runner = python_command(info)
    runtime = str(Path(__file__).resolve())
    syntax = str(Path(__file__).resolve().parent / 'source_inventory.py')
    root = Path(info['root'])
    # -I -S: the application's interpreter runs plugin code without PYTHONPATH,
    # the script directory, site or .pth files (available since Python 3.4).
    compile_command = [*runner, '-I', '-S', syntax, '--syntax', info['root']]
    lint_command = [*runner, '-m', 'ruff', 'check', '.']
    type_command = [*runner, '-m', 'mypy', *([] if mypy_configured_targets(root) else ['.'])]
    tests = [*runner, '-m', 'pytest', '--junitxml=.fastapi-tools/pytest.xml', *([selection] if selection else [])]
    if task == 'verify':
        steps = [compile_command]
        if 'ruff' in info['checks']:
            steps.append(lint_command)
        if 'mypy' in info['checks']:
            steps.append(type_command)
        if 'pytest' in info['checks']:
            steps.append(tests)
        command = [sys.executable, runtime, '--checks', json.dumps(steps)]
    else:
        command = {'compile': compile_command, 'lint': lint_command, 'typecheck': type_command, 'test': tests,
                   'package': [*runner, '-m', 'build', '--no-isolation'],
                   'dependencies': [*runner, '-c', 'import importlib.metadata as m, json; print(json.dumps(sorted([{"name": d.metadata["Name"], "version": d.version} for d in m.distributions()], key=lambda d: d["name"].lower())))'],
                   'migration-status': [*runner, '-m', 'alembic', 'current']}[task]
        steps = [command]
    return dict(info, command=command, steps=steps, tasks=[task], profiles=[], module=None, testClass=None, testPath=selection)


def relevant(path, root, excluded=()):
    relative = path.relative_to(root)
    if any(fnmatch.fnmatchcase(path.name, pattern) for pattern in GENERATED_FILES):
        return False
    if any(fnmatch.fnmatchcase(relative.as_posix(), pattern) for pattern in excluded):
        return False
    if any(ignored_directory(root / Path(*relative.parts[:index + 1]), root) for index in range(len(relative.parts) - 1)):
        return False
    # Build scripts can read arbitrary configuration names, binary fixtures,
    # extensionless inputs and data under docs. Exempt only pure prose outside src.
    return 'src' in relative.parts or path.suffix.lower() not in ('.md', '.rst', '.adoc')


def fingerprint_exclusions(root):
    """Optional [tool.fastapi-tools] fingerprint-exclude glob patterns."""
    try:
        section = pyproject(root).get('tool', {}).get('fastapi-tools', {})
    except AttributeError:
        section = {}
    patterns = section.get('fingerprint-exclude', []) if isinstance(section, dict) else []
    if (not isinstance(patterns, list) or len(patterns) > 100
            or not all(isinstance(item, str) and 0 < len(item) <= 256 for item in patterns)):
        raise ValueError('tool.fastapi-tools.fingerprint-exclude must be a list of at most 100 glob strings')
    return tuple(patterns)


def build_environment():
    return {key: value for key, value in os.environ.items()
            if key not in INVOCATION_ENV and not key.startswith(INVOCATION_PREFIXES)}


def environment_identity(environment):
    """Cheap identity of the selected environment: pyvenv.cfg plus installed
    distribution names (with versions), so `uv sync` or a reinstall that
    changes them invalidates reuse and remembered failures."""
    if not environment:
        return [sys.executable]
    folder = Path(environment)
    identity = []
    try:
        identity.append(read_regular(folder / 'pyvenv.cfg', 64 * 1024).decode('utf-8', 'replace'))
    except (OSError, ValueError):
        identity.append(None)
    for site in sorted(folder.glob('lib/python*/site-packages')) + sorted(folder.glob('Lib/site-packages')):
        try:
            with os.scandir(site) as entries:
                names = sorted(entry.name for entry in entries
                               if entry.name.endswith(('.dist-info', '.egg-info', '.egg-link', '.pth')))
        except OSError:
            names = None
        identity.append([str(site.relative_to(folder)), names[:20000] if names else names])
    return identity


def fingerprint(root, environment=None):
    root = Path(root)
    excluded = fingerprint_exclusions(root)
    digest = hashlib.sha256(Path(__file__).read_bytes())
    digest.update(Path(__file__).with_name('source_inventory.py').read_bytes())
    count, total = 0, 0
    variables = build_environment()
    limit = 128 * 1024 * 1024

    def internal_target(path):
        # Links inside the project are inputs; external or dangling links are
        # uninspected sources and never count as verified.
        target = path.resolve()
        if not target.exists():
            raise ValueError(f'Cannot fingerprint dangling symlinked build input: {path}')
        if not target.is_relative_to(root):
            raise ValueError(f'Cannot fingerprint symlinked build input outside the project: {path}')
        return target

    def skipped_location(target):
        """True when the walk never visits target in place (ignored/excluded)."""
        parts = target.relative_to(root).parts
        for index in range(len(parts)):
            prefix = root / Path(*parts[:index + 1])
            if prefix.is_dir() and (ignored_directory(prefix, root)
                                    or any(fnmatch.fnmatchcase(prefix.relative_to(root).as_posix(), p) for p in excluded)):
                return True
        return False

    def record(kind, relative, content=b''):
        digest.update(kind + len(relative).to_bytes(8, 'big') + relative)
        digest.update(len(content).to_bytes(8, 'big') + content)

    def add_file(source, relative):
        nonlocal count, total
        metadata = source.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f'Cannot fingerprint nonregular build input: {source}')
        if metadata.st_size + total > limit:
            raise ValueError('Build input fingerprint exceeds safety limit; verification will run without reuse')
        content = read_regular(source, limit - total)
        digest.update((metadata.st_mode & 0o777).to_bytes(8, 'big'))
        total += len(content)
        count += 1
        if total > limit or count > 50000:
            raise ValueError('Build input fingerprint exceeds safety limit; verification will run without reuse')
        for variable in re.findall(rb'\$\{([A-Za-z_][A-Za-z0-9_]*)', content):
            key = variable.decode()
            if key not in INVOCATION_ENV and not key.startswith(INVOCATION_PREFIXES):
                variables[key] = os.environ.get(key)
        record(b'F', relative, content)

    def add_linked_directory(target, link):
        # The target is not walked in place, so its contents are hashed here,
        # under the link's name. Nested links stay uninspected.
        for folder, directories, filenames in os.walk(target, followlinks=False, onerror=walk_error):
            for name in directories:
                if (Path(folder) / name).is_symlink():
                    raise ValueError(f'Cannot fingerprint nested symlink in linked directory: {Path(folder) / name}')
            directories.sort()
            for name in sorted(filenames):
                path = Path(folder) / name
                if path.is_symlink():
                    raise ValueError(f'Cannot fingerprint nested symlink in linked directory: {path}')
                if any(fnmatch.fnmatchcase(name, pattern) for pattern in GENERATED_FILES):
                    continue
                add_file(path, (link + '/' + path.relative_to(target).as_posix()).encode())

    def walk_error(error):
        raise error
    for folder, directories, filenames in os.walk(root, followlinks=False, onerror=walk_error):
        kept = []
        for name in sorted(directories):
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            if ignored_directory(path, root) or any(fnmatch.fnmatchcase(relative, pattern) for pattern in excluded):
                continue
            if path.is_symlink():
                target = internal_target(path)
                record(b'D', relative.encode(), target.relative_to(root).as_posix().encode())
                if skipped_location(target):
                    add_linked_directory(target, relative)
                continue
            kept.append(name)
        directories[:] = kept
        for name in sorted(filenames):
            path = Path(folder) / name
            if not relevant(path, root, excluded):
                continue
            relative = path.relative_to(root).as_posix().encode()
            source = path
            if path.is_symlink():
                source = internal_target(path)
                record(b'L', relative, source.relative_to(root).as_posix().encode())
            add_file(source, relative)
    digest.update(json.dumps(variables, sort_keys=True).encode())
    digest.update(json.dumps(environment_identity(environment)).encode())
    return digest.hexdigest()


def private_directory(folder):
    try:
        folder.mkdir(mode=0o700)
    except FileExistsError:
        pass
    info = folder.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError(f'Unsafe build state directory: {folder} must be a private 0700 directory of the current user')
    return folder


STATE_NOTICE = []  # Visible diagnostic when the temporary fallback is in use.


def owned_private_directory(path, label):
    info = os.stat(path)  # Follows a symlinked ~/.cache to its real directory.
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or writable_by_others(info):
        raise ValueError(f'{label} is not a directory of the current user that only they can write')


def state_base():
    """Per-user state independent of TMPDIR/HOME/XDG, which hosts can vary.

    FASTAPI_TOOLS_STATE_HOME is an explicit override for isolated runs. A
    private temporary fallback is used only without a usable home directory,
    and is reported because processes with different TMPDIR do not share it.
    """
    override = os.environ.get('FASTAPI_TOOLS_STATE_HOME')
    if override:
        if not os.path.isabs(override):
            raise ValueError('FASTAPI_TOOLS_STATE_HOME must be an absolute path')
        return private_directory(Path(override))
    try:
        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        owned_private_directory(home, 'The home directory')
        cache = home / '.cache'
        try:
            cache.mkdir(mode=0o700)
        except FileExistsError:
            pass
        # ~/.cache may be a symlink; its resolved target must be the user's own.
        owned_private_directory(cache, '~/.cache')
    except (KeyError, OSError, ValueError) as error:
        base = private_directory(Path(tempfile.gettempdir()) / f'fastapi-tools-{os.getuid()}')
        notice = (f'Runtime state uses the temporary fallback {base} ({error}); processes with a different TMPDIR '
                  'do not share its locks or results. Set FASTAPI_TOOLS_STATE_HOME or fix ~/.cache.')
        if notice not in STATE_NOTICE:
            STATE_NOTICE.append(notice)
        return base
    return private_directory(cache / 'fastapi-tools')


def state_dir(root):
    key = hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()
    return private_directory(state_base() / f'build-{key}')


def state_read(folder, name='state.json'):
    path = folder / name
    try:
        content = read_regular(path, 1024 * 1024)
    except FileNotFoundError:
        return {}
    try:
        value = json.loads(content)
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def state_write(folder, data, name='state.json'):
    handle, temporary = tempfile.mkstemp(prefix='state-', dir=folder)
    try:
        with os.fdopen(handle, 'w') as output:
            json.dump(data, output)
        os.replace(temporary, folder / name)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def acquire(folder, deadline, name='build.lock'):
    lock = folder / name
    handle = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    metadata = os.fstat(handle)
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077):
        os.close(handle)
        raise ValueError('Unsafe build lock file')
    stream = os.fdopen(handle, 'a')
    try:
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return stream
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f'Timed out waiting for the project {name}')
                time.sleep(.05)
    except BaseException:
        stream.close()
        raise


def terminate(process):
    # The supervisor leads its own session: one signal reaches every descendant.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def test_report_snapshot(root):
    """Read pytest's report while the caller owns the project check lock."""
    file = Path(root) / '.fastapi-tools' / 'pytest.xml'
    if file.parent.is_symlink() or file.is_symlink():
        raise ValueError('Unsafe test report path')
    if not file.exists():
        return {}
    metadata = file.stat()
    if metadata.st_nlink != 1:
        raise ValueError('Unsafe test report hardlink')
    content = read_regular(file)
    return {str(file): ((metadata.st_mtime_ns, metadata.st_ctime_ns, metadata.st_size), content.decode('utf-8', 'replace'))}


CANCEL_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)


def run_build(request):
    plan = build_plan(request)
    timeout = request.get('timeoutMs', 300000)
    limit = request.get('maxOutputBytes', 4 * 1024 * 1024)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 600000:
        raise ValueError('timeoutMs must be between 1 and 600000')
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 16 * 1024 * 1024:
        raise ValueError('maxOutputBytes must be between 1 and 16777216')
    start = time.monotonic()
    deadline = start + timeout / 1000
    folder = state_dir(plan['root'])
    with acquire(folder, deadline):
        collect_reports = request.get('collectTestReports', False)
        if collect_reports and plan['tasks'] != ['test']:
            raise ValueError('collectTestReports requires only the test task')
        reports_before = test_report_snapshot(plan['root']) if collect_reports else {}
        if plan['tasks'] == ['test'] or plan['tasks'] == ['verify'] and 'pytest' in plan['checks']:
            report_dir = Path(plan['root']) / '.fastapi-tools'
            if report_dir.is_symlink() or (report_dir / 'pytest.xml').is_symlink():
                raise ValueError('Unsafe test report path')
            report_dir.mkdir(exist_ok=True)
            report_file = report_dir / 'pytest.xml'
            if report_file.exists():
                metadata = report_file.lstat()
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                    raise ValueError('Unsafe test report path')
        cache_diagnostic = None
        try:
            before = fingerprint(plan['root'], plan.get('environment'))
        except (OSError, ValueError) as error:
            before, cache_diagnostic = None, str(error)
        state = state_read(folder)
        verification = plan['tasks'] == ['verify']
        scope = json.dumps([plan['buildTool'], plan['tasks'], plan['profiles'], plan['module'], plan['testPath']], separators=(',', ':'))
        scopes = state.get('verifiedScopes', {})
        if not isinstance(scopes, dict):
            scopes = {}
        attempts = state.get('lastAttempts', {})
        if not isinstance(attempts, dict):
            attempts = {}
        previous = attempts.get(scope) if isinstance(attempts.get(scope), dict) else None
        previous_fingerprint = previous.get('fingerprint') if previous else None
        changed = previous_fingerprint is not None and before is not None and before != previous_fingerprint
        history = {'hadPreviousAttempt': previous is not None, 'changedSinceLastAttempt': changed}
        if before is not None and request.get('reuse', True) and verification and scopes.get(scope) == before:
            return dict(plan, **history, ok=True, exitCode=0, stdout='', stderr='', reused=True, fingerprint=before, timedOut=False, outputLimitExceeded=False, inputsChanged=False, cacheable=True, cacheDiagnostic=None, durationMs=round((time.monotonic() - start) * 1000))
        if (request.get('skipUnchangedFailure') and verification and before is not None
                and previous and previous.get('ok') is False and previous_fingerprint == before):
            # The same inputs already failed; report it without rerunning.
            return dict(plan, **history, ok=False, unchangedFailure=True, exitCode=previous.get('exitCode', 1), stdout='', stderr='', reused=True, fingerprint=before, timedOut=False, outputLimitExceeded=False, inputsChanged=False, cacheable=True, cacheDiagnostic=None, durationMs=round((time.monotonic() - start) * 1000))
        # Any build attempt invalidates previous success; failure/cancellation cannot
        # preserve a stale verification after clean or other mutating build tasks.
        state.pop('verifiedScopes', None)
        state.pop('verifiedFingerprint', None)
        state_write(folder, state)
        process, selector = None, None
        outputs = {'stdout': bytearray(), 'stderr': bytearray()}
        timed_out, too_large, used = False, False, 0
        previous_handlers = {}
        deferred_signal = []
        try:
            # Record cancellation during Popen/pipe setup, when ownership of
            # the child is not yet available for cleanup. Do not block OS
            # signals: children must inherit the ordinary signal mask.
            def defer(signum, frame):
                deferred_signal.append(signum)
            for signum in CANCEL_SIGNALS:
                previous_handlers[signum] = signal.signal(signum, defer)
            # -I -S: plugin code ignores PYTHON* variables, site and .pth files;
            # the checks themselves inherit the environment unchanged.
            supervised = [sys.executable, '-I', '-S', str(Path(__file__).resolve()), '--checks', json.dumps(plan['steps']), str(os.getpid())]
            process = subprocess.Popen(supervised, cwd=plan['root'], stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                                       env=dict(os.environ, POETRY_VIRTUALENVS_CREATE='false'))
            selector = selectors.DefaultSelector()
            for name in outputs:
                selector.register(getattr(process, name), selectors.EVENT_READ, name)

            def interrupted(signum, frame):
                raise BuildCancelled(f'Build cancelled by signal {signum}')
            for signum in previous_handlers:
                signal.signal(signum, interrupted)
            if deferred_signal:
                raise BuildCancelled(f'Build cancelled by signal {deferred_signal[0]}')
            while selector.get_map():
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                for key, _ in selector.select(min(.1, max(0, deadline - time.monotonic()))):
                    block = os.read(key.fileobj.fileno(), 65536)
                    if not block:
                        selector.unregister(key.fileobj)
                        continue
                    remaining = max(0, limit - used)
                    outputs[key.data].extend(block[:remaining])
                    used += len(block)
                    if used > limit:
                        too_large = True
                        break
                if too_large:
                    break
            if timed_out or too_large:
                terminate(process)
            else:
                try:
                    process.wait(timeout=max(.001, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    timed_out = True
                    terminate(process)
            try:
                after = fingerprint(plan['root'], plan.get('environment'))
            except (OSError, ValueError) as error:
                after, cache_diagnostic = None, str(error)
            verification_incomplete = verification and (before is None or after is None)
            ok = process.returncode == 0 and not timed_out and not too_large and not verification_incomplete
            if verification:
                # Remember only a definite result for inputs that stayed the same.
                # Timeouts, output limits, uninspectable or changing inputs and
                # cancellations say nothing reusable about these inputs.
                definite = (before is not None and before == after and not timed_out and not too_large)
                if definite:
                    state['lastAttempts'] = {scope: {'fingerprint': before, 'ok': ok, 'exitCode': process.returncode}}
                else:
                    state.pop('lastAttempts', None)
            if ok and verification and before is not None and before == after:
                state['verifiedScopes'] = {scope: after}
            state_write(folder, state)
            report_result = {}
            if collect_reports:
                try:
                    reports_after = test_report_snapshot(plan['root'])
                    fresh = [{'file': file, 'content': value[1]} for file, value in reports_after.items()
                             if reports_before.get(file) != value]
                    report_result = {'testReports': fresh, 'staleReportsIgnored': len(reports_after) - len(fresh)}
                except (OSError, ValueError) as error:
                    ok = False
                    report_result = {'testReports': [], 'testReportErrors': [str(error)]}
            return dict(plan, **history, **report_result, ok=ok, exitCode=process.returncode, **{name: bytes(value).decode('utf-8', 'replace') for name, value in outputs.items()},
                        reused=False, verificationIncomplete=verification_incomplete, durationMs=round((time.monotonic() - start) * 1000), fingerprint=before, inputsChanged=before is not None and after is not None and before != after, cacheable=before is not None and after is not None, cacheDiagnostic=cache_diagnostic, timedOut=timed_out, outputLimitExceeded=too_large)
        finally:
            try:
                if selector is not None:
                    selector.close()
            finally:
                try:
                    if process is not None:
                        for name in outputs:
                            getattr(process, name).close()
                        terminate(process)
                finally:
                    for signum, handler in previous_handlers.items():
                        signal.signal(signum, handler)


def supervise(steps, parent):
    """Run checks sequentially as session leader; kill the group on
    cancellation or when the runtime that started it disappears."""
    leader = os.getpgrp() == os.getpid()
    child = None

    def stop(*_):
        if leader:
            os.killpg(os.getpgrp(), signal.SIGKILL)
        if child is not None and child.poll() is None:
            child.kill()
        os._exit(1)
    for signum in CANCEL_SIGNALS:
        signal.signal(signum, stop)
    if os.getppid() != parent:
        stop()
    for command in steps:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL)
        while True:
            try:
                code = child.wait(timeout=.2)
                break
            except subprocess.TimeoutExpired:
                if os.getppid() != parent:
                    stop()
        if code:
            sys.exit(code if code > 0 else 128 - code)


def pending_hint(folder):
    hint = state_read(folder, 'pending.json')
    sessions = hint.get('sessions')
    return dict(hint, sessions=sessions if isinstance(sessions, dict) else {})


class pending_lock:
    """Short lock for pending.json only; never waits for a running build."""

    def __init__(self, folder):
        self.folder = folder

    def __enter__(self):
        self.stream = acquire(self.folder, time.monotonic() + 5, 'pending.lock')
        return self

    def __exit__(self, *_):
        self.stream.close()


def mark_pending(location, session=''):
    info = discover(location)
    folder = state_dir(info['root'])
    # A hint has its own file and lock, so editing never waits for an ongoing
    # build. Each session keeps its own token: Stop only consumes its own.
    with pending_lock(folder):
        hint = pending_hint(folder)
        sessions = hint['sessions']
        sessions[str(session)] = secrets.token_hex(16)
        state_write(folder, {'root': info['root'], 'sessions': sessions}, 'pending.json')
    return info


def clear_pending(root, token, session=''):
    """Remove this session's hint only if no newer edit replaced it."""
    folder = state_dir(root)
    with pending_lock(folder):
        hint = pending_hint(folder)
        sessions = hint['sessions']
        if sessions.get(str(session)) != token:
            return
        del sessions[str(session)]
        if sessions:
            state_write(folder, {'root': hint.get('root', str(root)), 'sessions': sessions}, 'pending.json')
        else:
            try:
                (folder / 'pending.json').unlink()
            except FileNotFoundError:
                pass


def pending_roots(session='', limit=4096):
    """Projects this session edited, read from the private per-user state."""
    roots = {}
    with os.scandir(state_base()) as entries:
        for index, entry in enumerate(entries):
            if index >= limit:
                break
            if not entry.name.startswith('build-') or not entry.is_dir(follow_symlinks=False):
                continue
            hint = pending_hint(Path(entry.path))
            root, token = hint.get('root'), hint['sessions'].get(str(session))
            if isinstance(root, str) and os.path.isabs(root) and isinstance(token, str):
                roots[root] = token
    return roots


def literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def module_name(file, root):
    parts = list(file.relative_to(root).with_suffix('').parts)
    if parts and parts[0] == 'src':
        parts.pop(0)
    if parts and parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def static_endpoints(root):
    """AST evidence only. No application imports or dependency execution."""
    objects, edges, routes, aliases, warnings = {}, [], [], {}, []
    for file in source_files(root):
        relative, module = file.relative_to(root).as_posix(), module_name(file, root)
        try:
            tree = ast.parse(read_regular(file))
        except SyntaxError as error:
            warnings.append(f'{relative}:{error.lineno}: {error.msg}')
            continue
        names = aliases.setdefault(module, {})
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                parent = module.split('.') if file.name == '__init__.py' else module.split('.')[:-1]
                base = '.'.join(parent[:len(parent) - node.level + 1]) if node.level else ''
                imported = '.'.join(x for x in (base, node.module) if x)
                for name in node.names:
                    names[name.asname or name.name] = imported + '.' + name.name
            elif isinstance(node, ast.Import):
                for name in node.names:
                    names[name.asname or name.name.split('.')[0]] = name.name if name.asname else name.name.split('.')[0]
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Call):
                call = node.value
                kind = ast.unparse(call.func).split('.')[-1]
                kind = names.get(kind, kind).split('.')[-1]
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if kind in ('FastAPI', 'APIRouter'):
                    keywords = {kw.arg: literal(kw.value) for kw in call.keywords}
                    for target in targets:
                        if isinstance(target, ast.Name):
                            objects[module + '.' + target.id] = {'kind': kind, 'prefix': keywords.get('prefix', ''), 'file': relative}
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                if isinstance(call.func, ast.Attribute) and call.func.attr == 'include_router' and call.args:
                    keywords = {kw.arg: literal(kw.value) for kw in call.keywords}
                    edges.append((module, ast.unparse(call.func.value), ast.unparse(call.args[0]), keywords.get('prefix', ''), relative))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                        continue
                    method = dec.func.attr
                    if method not in ('get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace', 'api_route'):
                        continue
                    keywords = {kw.arg: literal(kw.value) for kw in dec.keywords}
                    route = literal(dec.args[0]) if dec.args else keywords.get('path')
                    if not isinstance(route, str):
                        warnings.append(f'{relative}:{node.lineno}: computed route path is unresolved')
                        continue
                    methods = (keywords.get('methods') or ['GET']) if method == 'api_route' else [method.upper()]
                    if not isinstance(methods, (list, tuple)) or not all(isinstance(m, str) for m in methods):
                        warnings.append(f'{relative}:{node.lineno}: computed methods are unresolved')
                        continue
                    for verb in methods:
                        routes.append((module, ast.unparse(dec.func.value), {'method': verb.upper(), 'path': route, 'file': relative, 'line': node.lineno, 'function': node.name}))
    def resolve(module, name):
        first, *rest = name.split('.')
        return '.'.join([aliases.get(module, {}).get(first, module + '.' + first), *rest])
    linked = {}
    for module, owner, router, prefix, file in edges:
        owner, router = resolve(module, owner), resolve(module, router)
        if owner not in objects or router not in objects or not isinstance(prefix, str):
            warnings.append(f'{file}: unresolved include_router({router})')
            continue
        linked.setdefault(owner, []).append((router, prefix))
    endpoints, reached = [], set()
    def visit(owner, prefix, stack):
        if owner in stack:
            warnings.append('Cyclic router inclusion: ' + owner)
            return
        own_prefix = objects[owner]['prefix']
        if not isinstance(own_prefix, str):
            warnings.append('Computed router prefix: ' + owner)
            return
        prefix += own_prefix
        reached.add(owner)
        for module, name, route in routes:
            if resolve(module, name) == owner:
                endpoints.append(dict(route, path=prefix + route['path']))
        for router, extra in linked.get(owner, []):
            visit(router, prefix + extra, stack | {owner})
    for name, obj in objects.items():
        if obj['kind'] == 'FastAPI':
            visit(name, '', set())
    unmounted = [route for module, name, route in routes if resolve(module, name) not in reached]
    return {'endpoints': endpoints, 'count': len(endpoints), 'unmounted': unmounted, 'warnings': warnings,
            'limitation': 'Static top-level constructors, decorators and include_router calls only; factories, re-exports, mounts, conditional and computed registration need runtime OpenAPI.'}


def migration_inventory(root):
    locations, warnings = [], []
    config = root / 'alembic.ini'
    if config.is_file():
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(read_regular(config).decode('utf-8'))
        values = parser['alembic'] if parser.has_section('alembic') else {}
        script = values.get('script_location', 'alembic').replace('%(here)s', str(root))
        version_locations = values.get('version_locations')
        if version_locations:
            separator = values.get('path_separator', values.get('version_path_separator', 'space'))
            delimiter = {'os': os.pathsep, 'space': None, 'newline': '\n', ':': ':', ';': ';'}.get(separator)
            locations = version_locations.replace('%(here)s', str(root)).split(delimiter)
        else:
            locations = [str(Path(script) / 'versions')]
    else:
        locations = ['alembic/versions', 'migrations/versions']
    files, scanned = set(), []
    for location in locations:
        directory = (root / location.strip()).resolve()
        if not directory.is_relative_to(root):
            warnings.append('Skipped external migration location: ' + location)
            continue
        if not directory.exists():
            continue
        scanned.append(directory.relative_to(root).as_posix())
        files.update(source_files(directory))
    migrations, errors, risks, ids = [], [], [], {}
    for file in sorted(files):
        relative = file.relative_to(root).as_posix()
        try:
            tree = ast.parse(read_regular(file))
        except SyntaxError as error:
            errors.append({'file': relative, 'code': 'syntax', 'message': str(error)})
            continue
        values, unresolved = {}, set()
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        values[target.id] = literal(node.value)
                        if values[target.id] is None and not (isinstance(node.value, ast.Constant) and node.value.value is None):
                            unresolved.add(target.id)
        revision, down = values.get('revision'), values.get('down_revision')
        if file.name == '__init__.py':
            continue
        if 'down_revision' not in values or unresolved & {'down_revision', 'depends_on'}:
            errors.append({'file': relative, 'code': 'metadata', 'message': 'Expected explicit literal down_revision and depends_on metadata'})
            continue
        if not isinstance(revision, str) or not revision:
            errors.append({'file': relative, 'code': 'revision', 'message': 'Expected a nonempty literal revision identifier'})
            continue
        if down is not None and not isinstance(down, str) and not (isinstance(down, (tuple, list)) and all(isinstance(x, str) for x in down)):
            errors.append({'file': relative, 'code': 'down-revision', 'message': 'Expected literal down_revision, tuple of parents or None'})
            continue
        parents = [down] if isinstance(down, str) else list(down or [])
        dependencies = values.get('depends_on') or []
        dependencies = [dependencies] if isinstance(dependencies, str) else dependencies
        if not isinstance(dependencies, (list, tuple)) or not all(isinstance(x, str) for x in dependencies):
            errors.append({'file': relative, 'code': 'depends-on', 'message': 'Expected literal dependency identifiers'})
            dependencies = []
        entry = {'file': relative, 'revision': revision, 'downRevision': parents, 'dependsOn': list(dependencies)}
        migrations.append(entry)
        if revision in ids:
            errors.append({'file': relative, 'code': 'duplicate-revision', 'message': 'Duplicate revision ' + revision})
        ids[revision] = entry
        upgrade = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'upgrade'), None)
        if upgrade is None:
            errors.append({'file': relative, 'code': 'upgrade', 'message': 'Missing upgrade()'})
        else:
            for node in ast.walk(upgrade):
                if isinstance(node, ast.Call):
                    name = ast.unparse(node.func)
                    if name.endswith(('.drop_table', '.drop_column', '.drop_index', '.alter_column')):
                        risks.append({'file': relative, 'line': node.lineno, 'code': 'ddl-risk', 'message': name + ': review data loss, locking and rolling compatibility'})
                    if name.endswith('.execute') and node.args:
                        argument = node.args[0]
                        # op.execute(sa.text("...")) carries the same literal SQL.
                        if (isinstance(argument, ast.Call) and argument.args
                                and ast.unparse(argument.func).split('.')[-1] == 'text'):
                            argument = argument.args[0]
                        sql = literal(argument)
                        if isinstance(sql, str) and re.search(r'(?i)\b(?:DROP|TRUNCATE|DELETE)\b', sql):
                            risks.append({'file': relative, 'line': node.lineno, 'code': 'destructive-sql', 'message': 'Review destructive SQL in upgrade()'})
    graph = {entry['revision']: entry['downRevision'] + entry['dependsOn'] for entry in migrations}
    active, visited = set(), set()
    def walk(revision):
        if revision in active:
            errors.append({'code': 'cycle', 'message': 'Cyclic revision graph: ' + revision})
            return
        if revision in visited:
            return
        active.add(revision)
        for parent in graph.get(revision, []):
            if parent not in ids:
                errors.append({'code': 'missing-parent', 'message': revision + ' references missing revision ' + parent})
            else:
                walk(parent)
        active.remove(revision)
        visited.add(revision)
    for revision in graph:
        walk(revision)
    referenced = {parent for parents in graph.values() for parent in parents}
    heads = sorted(set(ids) - referenced)
    if len(heads) > 1:
        warnings.append('Multiple heads: confirm intentional branches or add a merge revision')
    return {'mode': 'lint', 'databaseAccess': False, 'locations': scanned, 'migrations': migrations, 'heads': heads, 'errors': errors, 'risks': risks, 'warnings': warnings,
            'limitation': 'Static revision graph and upgrade risks only; no env.py execution or database access. Applied-state immutability requires database/history evidence.'}



def main():
    def interrupted(signum, frame):
        raise BuildCancelled(f'Runtime cancelled by signal {signum}')
    for signum in CANCEL_SIGNALS:
        signal.signal(signum, interrupted)
    try:
        raw = sys.stdin.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('Runtime request exceeds 1 MiB limit')
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ValueError('Expected JSON object')
        action = request.get('action', 'discover')
        if action == 'discover':
            result = discover(request.get('projectRoot') or os.getcwd())
        elif action == 'initialize':
            from project_initializer import initialize_project
            result = initialize_project(request)
        elif action == 'plan':
            result = build_plan(request)
        elif action == 'run':
            result = run_build(request)
        elif action == 'analyze':
            result = discover(request.get('projectRoot') or os.getcwd())
            result['endpoints'] = static_endpoints(Path(result['root']))
        elif action == 'migrations':
            result = migration_inventory(Path(discover(request.get('projectRoot') or os.getcwd())['root']))
        elif action == 'mark':
            result = mark_pending(request.get('projectRoot') or os.getcwd(), request.get('sessionId') or '')
        elif action == 'state-location':
            # Lets other adapters and tests clean exactly their own state.
            result = {'stateBase': str(state_base()),
                      'stateDir': str(state_dir(request['projectRoot'])) if request.get('projectRoot') else None}
        else:
            raise ValueError('Unknown runtime action')
        if STATE_NOTICE and isinstance(result, dict):
            result['stateDiagnostic'] = STATE_NOTICE[0]
        encoded = json.dumps(result)
        if len(encoded.encode('utf-8')) > 24 * 1024 * 1024:
            encoded = json.dumps({'ok': False, 'exitCode': 1, 'error': 'Runtime result exceeds 24 MiB serialized limit; narrow the scope'})
        print(encoded)
    except (OSError, ValueError, TypeError, TimeoutError, BuildCancelled, configparser.Error, RecursionError) as error:
        print(json.dumps({'ok': False, 'error': str(error), 'exitCode': 1}))
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--syntax':
        from source_inventory import syntax_check
        syntax_check(Path(sys.argv[2]))
    elif len(sys.argv) > 1 and sys.argv[1] == '--checks':
        supervise(json.loads(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else os.getppid())
    else:
        main()
