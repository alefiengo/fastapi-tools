#!/usr/bin/env python3
"""Project discovery and coordinated builds, shared by hooks and MCP (stdlib only).

CLI accepts a JSON object on stdin and returns JSON on stdout. Build subprocesses
inherit the CLI process group so an MCP cancellation terminates the whole group.
"""
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import tomllib

class BuildCancelled(RuntimeError):
    pass


BUILD_FILES = ('pyproject.toml', 'requirements.txt', 'setup.cfg', 'setup.py')
INVOCATION_ENV = {'CLAUDE_PROJECT_DIR', 'CLAUDE_PLUGIN_ROOT', 'CLAUDE_SESSION_ID', 'CODEX_THREAD_ID', 'MCP_SERVER_NAME', 'PROJECT_ROOT', 'PWD', 'OLDPWD', 'SHLVL', '_'}
IGNORED = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', '__pycache__', '.idea', '.vscode', '.pytest_cache', '.ruff_cache', '.mypy_cache', '.fastapi-tools', 'htmlcov'}
TASKS = {'compile', 'lint', 'typecheck', 'test', 'verify', 'package', 'dependencies', 'migration-status'}


def build_file(folder):
    return next((name for name in BUILD_FILES if (folder / name).is_file()), None)


def source_files(root):
    for folder, directories, filenames in os.walk(root, followlinks=False):
        directories[:] = sorted(d for d in directories if not ignored_directory(Path(folder) / d, root) and not (Path(folder) / d).is_symlink())
        for name in sorted(filenames):
            file = Path(folder) / name
            if file.suffix == '.py' and not file.is_symlink():
                yield file


def project_metadata(root):
    config = root / 'pyproject.toml'
    data = tomllib.loads(config.read_text()) if config.is_file() else {}
    project, tools = data.get('project', {}), data.get('tool', {})
    dependencies = list(project.get('dependencies', []))
    for group in project.get('optional-dependencies', {}).values():
        dependencies.extend(group)
    for group in data.get('dependency-groups', {}).values():
        dependencies.extend(item for item in group if isinstance(item, str))
    poetry = tools.get('poetry', {})
    for name, version in poetry.get('dependencies', {}).items():
        dependencies.append(f'{name} {version}')
    for group in poetry.get('group', {}).values():
        dependencies.extend(f'{name} {version}' for name, version in group.get('dependencies', {}).items())
    for file in sorted(root.glob('requirements*.txt')):
        dependencies.extend(line.strip() for line in file.read_text().splitlines() if line.strip() and not line.lstrip().startswith(('#', '-')))
    # Metadata only: never import application code during discovery.
    fastapi = any(re.match(r'(?i)^fastapi(?:\b|\[)', dep) for dep in dependencies)
    if not fastapi:
        for file in source_files(root):
            if re.search(r'(?m)^\s*(?:from\s+fastapi\b|import\s+fastapi\b)', file.read_text(errors='replace')):
                fastapi = True
                break
    return {'name': project.get('name') or poetry.get('name'), 'requiresPython': project.get('requires-python'),
            'dependencies': dependencies, 'isFastAPI': fastapi,
            'checks': [name for name in ('ruff', 'mypy') if name in tools or any(re.match(r'(?i)^' + name + r'\b', dep) for dep in dependencies)]}


def discover(location):
    location = Path(location).resolve()
    folder = location if location.is_dir() else location.parent
    root = next((p for p in (folder, *folder.parents) if build_file(p)), None)
    if root is None:
        raise ValueError(f'No Python project found from {location}; expected pyproject.toml or requirements.txt')
    metadata = project_metadata(root)
    tool = 'uv' if (root / 'uv.lock').is_file() else ('poetry' if (root / 'poetry.lock').is_file() else 'python')
    python = root / '.venv' / 'bin' / 'python'
    return dict(metadata, root=str(root), buildTool=tool, buildFile=build_file(root),
                python=str(python) if python.is_file() else sys.executable,
                modules=[], discoveryScope='Nearest Python project; dependencies are declarations, not resolved installations')


def python_command(info):
    if info['buildTool'] in ('uv', 'poetry'):
        tool = shutil.which(info['buildTool'])
        if not tool:
            raise ValueError(f"{info['buildTool']} is required by the project lockfile but is unavailable")
        # Never install or synchronize dependencies as a side effect of a check.
        return [tool, 'run', '--frozen', '--offline', '--no-sync', 'python'] if info['buildTool'] == 'uv' else [tool, 'run', 'python']
    return [info['python']]


def build_plan(request):
    info = discover(request.get('projectRoot') or os.getcwd())
    tasks = request.get('tasks') or [request.get('task', 'compile')]
    if not isinstance(tasks, list) or len(tasks) != 1 or not isinstance(tasks[0], str):
        raise ValueError('Exactly one task is required; verify combines all configured checks')
    task = 'verify' if tasks[0] == 'check' else tasks[0]
    if task not in TASKS:
        raise ValueError('Unsupported task; allowed: ' + ', '.join(sorted(TASKS)))
    if request.get('module') is not None or request.get('profiles'):
        raise ValueError('Python checks use the nearest project root; module/profile selectors are unsupported')
    selection = request.get('testPath')
    if selection is not None:
        if task != 'test' or not isinstance(selection, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+(?:\:\:[A-Za-z_][A-Za-z0-9_]*)*', selection):
            raise ValueError('testPath must be a relative pytest file/directory, optionally ::class::test')
        file = (Path(info['root']) / selection.split('::')[0]).resolve()
        if not file.is_relative_to(Path(info['root'])) or not file.exists() or selection.startswith('-') or Path(selection.split('::')[0]).is_absolute():
            raise ValueError('testPath must exist inside the project root')
    runner = python_command(info)
    runtime = str(Path(__file__).resolve())
    compile_command = [*runner, runtime, '--syntax', info['root']]
    lint_command = [*runner, '-m', 'ruff', 'check', '.']
    type_command = [*runner, '-m', 'mypy', '.']
    tests = [*runner, '-m', 'pytest', '--junitxml=.fastapi-tools/pytest.xml', *([selection] if selection else [])]
    if task == 'verify':
        commands = [compile_command]
        if 'ruff' in info['checks']:
            commands.append(lint_command)
        if 'mypy' in info['checks']:
            commands.append(type_command)
        commands.append(tests)
        command = [sys.executable, runtime, '--checks', json.dumps(commands)]
    else:
        command = {'compile': compile_command, 'lint': lint_command, 'typecheck': type_command, 'test': tests,
                   'package': [*runner, '-m', 'build', '--no-isolation'],
                   'dependencies': [*runner, '-c', 'import importlib.metadata as m, json; print(json.dumps(sorted([{"name": d.metadata["Name"], "version": d.version} for d in m.distributions()], key=lambda d: d["name"].lower())))'],
                   'migration-status': [*runner, '-m', 'alembic', 'current']}[task]
    return dict(info, command=command, tasks=[task], profiles=[], module=None, testClass=None, testPath=selection)


def ignored_directory(path, root):
    if path.name in ('build', 'dist') and ('src' in path.relative_to(root).parts or (path / '__init__.py').is_file()):
        return False
    return path.name in IGNORED or path.name.endswith('.egg-info')


def relevant(path, root):
    relative = path.relative_to(root)
    if path.name == '.coverage' or path.name.startswith('.coverage.'):
        return False
    if any(ignored_directory(root / Path(*relative.parts[:index + 1]), root) for index in range(len(relative.parts) - 1)):
        return False
    # Build scripts can read arbitrary configuration names, binary fixtures,
    # extensionless inputs and data under docs. Exempt only pure prose outside src.
    return path.suffix.lower() not in ('.md', '.rst', '.adoc')


def fingerprint(root):
    root = Path(root)
    digest = hashlib.sha256(Path(__file__).read_bytes())
    count, total = 0, 0
    environment = {key: value for key, value in os.environ.items() if key not in INVOCATION_ENV}
    def walk_error(error):
        raise error
    for folder, directories, filenames in os.walk(root, followlinks=False, onerror=walk_error):
        for name in directories:
            if not ignored_directory(Path(folder) / name, root) and (Path(folder) / name).is_symlink():
                raise ValueError(f'Cannot fingerprint symlinked build directory: {Path(folder) / name}')
        directories[:] = sorted(d for d in directories if not ignored_directory(Path(folder) / d, root) and not (Path(folder) / d).is_symlink())
        for name in sorted(filenames):
            path = Path(folder) / name
            if not relevant(path, root):
                continue
            if path.is_symlink():
                # Avoid treating uninspected external sources as verified.
                raise ValueError(f'Cannot fingerprint symlinked build input: {path}')
            metadata = path.stat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f'Cannot fingerprint nonregular build input: {path}')
            if metadata.st_size + total > 128 * 1024 * 1024:
                raise ValueError('Build input fingerprint exceeds safety limit; verification will run without reuse')
            with path.open('rb') as source:
                content = source.read(128 * 1024 * 1024 - total + 1)
            digest.update((metadata.st_mode & 0o777).to_bytes(8, 'big'))
            total += len(content)
            count += 1
            if total > 128 * 1024 * 1024 or count > 50000:
                raise ValueError('Build input fingerprint exceeds safety limit; verification will run without reuse')
            relative = path.relative_to(root).as_posix().encode()
            for variable in re.findall(rb'\$\{([A-Za-z_][A-Za-z0-9_]*)', content):
                key = variable.decode()
                environment[key] = os.environ.get(key)
            digest.update(len(relative).to_bytes(8, 'big') + relative)
            digest.update(len(content).to_bytes(8, 'big') + content)
    digest.update(json.dumps(environment, sort_keys=True).encode())
    return digest.hexdigest()


def state_dir(root):
    key = hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()
    folder = Path(tempfile.gettempdir()) / f'fastapi-tools-build-{os.getuid()}-{key}'
    try:
        folder.mkdir(mode=0o700)
    except FileExistsError:
        pass
    info = folder.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Unsafe shared build state directory')
    return folder


def state_read(folder):
    path = folder / 'state.json'
    if path.is_symlink():
        raise ValueError('Unsafe build state file')
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def state_write(folder, data):
    handle, temporary = tempfile.mkstemp(prefix='state-', dir=folder)
    try:
        with os.fdopen(handle, 'w') as output:
            json.dump(data, output)
        os.replace(temporary, folder / 'state.json')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def acquire(folder, deadline):
    lock = folder / 'build.lock'
    handle = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    stream = os.fdopen(handle, 'a')
    try:
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return stream
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Timed out waiting for the project build lock')
                time.sleep(.05)
    except BaseException:
        stream.close()
        raise


def terminate(process, own_group):
    if own_group:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        # CLI must remain in its caller's group. Kill its build descendants only.
        try:
            listing = subprocess.run(['ps', '-eo', 'pid=,ppid=,pgid='], capture_output=True, text=True, timeout=2).stdout
            rows = [tuple(map(int, line.split())) for line in listing.splitlines() if len(line.split()) == 3]
            pairs = [(pid, parent) for pid, parent, group in rows]
            ids = {process.pid}
            if os.getpgrp() == os.getpid():
                ids |= {pid for pid, parent, group in rows if group == os.getpgrp() and pid != os.getpid()}
            while True:
                children = {pid for pid, parent in pairs if parent in ids}
                if children <= ids:
                    break
                ids |= children
            for pid in sorted(ids, reverse=True):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        finally:
            if process.poll() is None:
                process.kill()
    process.wait()


def test_report_snapshot(root):
    """Read pytest's report while the caller owns the project check lock."""
    file = Path(root) / '.fastapi-tools' / 'pytest.xml'
    if file.parent.is_symlink() or file.is_symlink():
        raise ValueError('Unsafe test report path')
    if not file.is_file():
        return {}
    metadata = file.stat()
    if metadata.st_size > 8 * 1024 * 1024:
        raise ValueError('Test report exceeds 8 MiB limit')
    content = file.read_bytes()
    if len(content) > 8 * 1024 * 1024:
        raise ValueError('Test report exceeds 8 MiB limit')
    return {str(file): ((metadata.st_mtime_ns, metadata.st_ctime_ns, metadata.st_size), content.decode('utf-8', 'replace'))}


def run_build(request, own_process_group=False):
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
        if plan['tasks'] in (['test'], ['verify']):
            report_dir = Path(plan['root']) / '.fastapi-tools'
            if report_dir.is_symlink() or (report_dir / 'pytest.xml').is_symlink():
                raise ValueError('Unsafe test report path')
            report_dir.mkdir(exist_ok=True)
        cache_diagnostic = None
        try:
            before = fingerprint(plan['root'])
        except (OSError, ValueError) as error:
            before, cache_diagnostic = None, str(error)
        state = state_read(folder)
        verification = plan['tasks'] in (['verify'], ['check'])
        scope = json.dumps([plan['buildTool'], plan['tasks'], plan['profiles'], plan['module'], plan['testPath']], separators=(',', ':'))
        scopes = state.get('verifiedScopes', {})
        if not isinstance(scopes, dict):
            scopes = {}
        if before is not None and request.get('reuse', True) and verification and scopes.get(scope) == before:
            return dict(plan, ok=True, exitCode=0, stdout='', stderr='', reused=True, fingerprint=before, timedOut=False, outputLimitExceeded=False, inputsChanged=False, cacheable=True, cacheDiagnostic=None, durationMs=round((time.monotonic() - start) * 1000))
        # Any build attempt invalidates previous success; failure/cancellation cannot
        # preserve a stale verification after clean or other mutating build tasks.
        state.pop('verifiedScopes', None)
        state.pop('verifiedFingerprint', None)
        state_write(folder, state)
        process = subprocess.Popen(plan['command'], cwd=plan['root'], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=own_process_group)
        selector = selectors.DefaultSelector()
        outputs = {'stdout': bytearray(), 'stderr': bytearray()}
        for name in outputs:
            selector.register(getattr(process, name), selectors.EVENT_READ, name)
        timed_out, too_large, used = False, False, 0
        previous_handlers = {}
        if own_process_group:
            def interrupted(signum, frame):
                raise BuildCancelled(f'Build cancelled by signal {signum}')
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous_handlers[signum] = signal.signal(signum, interrupted)
        try:
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
                terminate(process, own_process_group)
            else:
                try:
                    process.wait(timeout=max(.001, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    timed_out = True
                    terminate(process, own_process_group)
            try:
                after = fingerprint(plan['root'])
            except (OSError, ValueError) as error:
                after, cache_diagnostic = None, str(error)
            ok = process.returncode == 0 and not timed_out and not too_large
            if ok and verification and before is not None and before == after:
                state['verifiedScopes'] = {scope: after}
                state.pop('pendingFingerprint', None)
                state_write(folder, state)
                try:
                    (folder / 'pending.json').unlink()
                except FileNotFoundError:
                    pass
            report_result = {}
            if collect_reports:
                reports_after = test_report_snapshot(plan['root'])
                fresh = [{'file': file, 'content': value[1]} for file, value in reports_after.items()
                         if reports_before.get(file) != value]
                report_result = {'testReports': fresh, 'staleReportsIgnored': len(reports_after) - len(fresh)}
            return dict(plan, **report_result, ok=ok, exitCode=process.returncode, **{name: bytes(value).decode('utf-8', 'replace') for name, value in outputs.items()},
                        reused=False, durationMs=round((time.monotonic() - start) * 1000), fingerprint=before, inputsChanged=before is not None and after is not None and before != after, cacheable=before is not None and after is not None, cacheDiagnostic=cache_diagnostic, timedOut=timed_out, outputLimitExceeded=too_large)
        finally:
            selector.close()
            for name in outputs:
                getattr(process, name).close()
            try:
                if own_process_group or process.poll() is None:
                    terminate(process, own_process_group)
            finally:
                for signum, handler in previous_handlers.items():
                    signal.signal(signum, handler)


def mark_pending(location):
    info = discover(location)
    folder = state_dir(info['root'])
    # A hint has its own file, so editing never waits for an ongoing build. The
    # actual success gate remains locked and compares all current input contents.
    handle, temporary = tempfile.mkstemp(prefix='pending-', dir=folder)
    try:
        with os.fdopen(handle, 'w') as output:
            json.dump({'pending': True}, output)
        os.replace(temporary, folder / 'pending.json')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return info


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
            tree = ast.parse(file.read_bytes())
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
    import configparser
    locations, warnings = [], []
    config = root / 'alembic.ini'
    if config.is_file():
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(config)
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
    files = set()
    for location in locations:
        directory = (root / location.strip()).resolve()
        if not directory.is_relative_to(root):
            warnings.append('Skipped external migration location: ' + location)
            continue
        files.update(source_files(directory))
    migrations, errors, risks, ids = [], [], [], {}
    for file in sorted(files):
        relative = file.relative_to(root).as_posix()
        try:
            tree = ast.parse(file.read_bytes())
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
                        sql = literal(node.args[0])
                        if isinstance(sql, str) and re.search(r'(?i)\\b(?:DROP|TRUNCATE|DELETE)\\b', sql):
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
    return {'mode': 'lint', 'databaseAccess': False, 'migrations': migrations, 'heads': heads, 'errors': errors, 'risks': risks, 'warnings': warnings,
            'limitation': 'Static revision graph and upgrade risks only; no env.py execution or database access. Applied-state immutability requires database/history evidence.'}


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError('Expected JSON object')
        action = request.get('action', 'discover')
        if action == 'discover':
            result = discover(request.get('projectRoot') or os.getcwd())
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
            result = mark_pending(request.get('projectRoot') or os.getcwd())
        else:
            raise ValueError('Unknown runtime action')
        print(json.dumps(result))
    except (OSError, ValueError, TypeError, TimeoutError, BuildCancelled) as error:
        print(json.dumps({'ok': False, 'error': str(error), 'exitCode': 1}))
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--syntax':
        for file in source_files(Path(sys.argv[2])):
            compile(file.read_bytes(), str(file), 'exec')
        print('Python syntax check passed')
    elif len(sys.argv) > 1 and sys.argv[1] == '--checks':
        for command in json.loads(sys.argv[2]):
            code = subprocess.call(command, stdin=subprocess.DEVNULL)
            if code:
                sys.exit(code)
    else:
        main()
