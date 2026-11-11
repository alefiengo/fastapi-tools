#!/usr/bin/env python3
"""Shared hook runtime. Python 3 standard library only; never executes input as shell."""
import ast
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys
import time


def emit(event, message, decision='deny'):
    if event == 'PreToolUse':
        result = {'hookSpecificOutput': {'hookEventName': event, 'permissionDecision': decision,
                                       'permissionDecisionReason': message}}
    elif event == 'Stop':
        result = {'decision': 'block', 'reason': message}
    else:
        result = {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': message}}
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))


def notice(message):
    print(json.dumps({'systemMessage': message}, ensure_ascii=False, separators=(',', ':')))


def read_input():
    raw = sys.stdin.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        notice('FastAPI hook skipped: input exceeds 2 MiB limit.')
        return None
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError('expected an object')
        return value
    except (ValueError, TypeError) as error:
        notice(f'FastAPI hook skipped: invalid JSON input ({error}).')
        return None


def current_text(path):
    try:
        return read_regular(path).decode('utf-8')
    except (OSError, ValueError):
        return None


def proposed(data, path):
    args = data.get('tool_input', {})
    if 'content' in args:
        return args['content']
    if 'new_string' in args:
        old, new = args.get('old_string', ''), args['new_string']
        text = current_text(path)
        if text is None:
            # At least inspect the replacement if the old file cannot be read.
            return new
        if not old:
            return new if not text else text + '\n' + new
        if old not in text:
            return text + '\n' + new
        return text.replace(old, new, -1 if args.get('replace_all') else 1)
    return ''


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime'))
import project_runtime  # noqa: E402
from project_runtime import (discover, mark_pending, run_build, relevant, find_root, migration_inventory, pending_roots,  # noqa: E402
                             clear_pending, pyproject, ini_config, BuildCancelled, DiscoveryError, read_regular)

PLACEHOLDERS = {'', 'changeme', 'change_me', 'change-me', 'changethis', 'example', 'dummy', 'placeholder',
                'null', 'none', '~', 'true', 'false'}
SENSITIVE_SUFFIXES = ('password', 'passwd', 'secret', 'apikey', 'token', 'privatekey',
                      'secretkey', 'secretaccesskey', 'signingkey')
PYTHON_SENSITIVE = re.compile(r'(?i)(?:password|passwd|secret|api_?key|token|private_?key|secret_?key'
                              r'|secret_?access_?key|signing_?key)$')
KEY_PATTERN = re.compile(r"(?i)(?:^|[\s:{,])[\"']?([\w.-]{0,256}(?:password|passwd|secret|api[_-]?key|token|private[_-]?key"
                         r"|signing[_-]?key|access[_-]?key)[\w.-]{0,256})[\"']?\s*[:=]\s*")
URL_CREDENTIAL = re.compile(r'(?i)\b[a-z][a-z0-9+.-]{0,30}://[^\s:@/]{0,256}:([^\s@/]{1,512})@')
LINE_LIMIT = 4096


def unquote(value):
    value = re.split(r'\s+#', value, maxsplit=1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def config_path(path):
    return (path.suffix in ('.toml', '.yaml', '.yml', '.ini', '.cfg', '.json')
            or path.name.startswith('.env') or path.name.endswith('.env'))


def flow_scalar(value):
    """Read one flow-map scalar while preserving quotes and ${...} expressions."""
    quote = None
    placeholders = 0
    skip_next = False
    for index, char in enumerate(value):
        if skip_next:
            skip_next = False
            continue
        if quote:
            if char == quote:
                # JSON-style double-quote escapes; YAML single quotes escape by doubling.
                if quote == '"' and (len(value[:index]) - len(value[:index].rstrip('\\'))) % 2:
                    continue
                if quote == "'" and index + 1 < len(value) and value[index+1] == "'":
                    skip_next = True
                    continue
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char == '{' and index and value[index-1] == '$':
            placeholders += 1
        elif char == '}' and placeholders:
            placeholders -= 1
        elif char in ',}' and not placeholders:
            return value[:index].strip()
    return value.strip()


def safe_placeholder(value):
    """$VAR, ${VAR}, ${VAR?msg}, ${VAR:?msg} or a safe default (${VAR:-x}, ${VAR-x}, ${VAR:x})."""
    for _ in range(16):
        if re.fullmatch(r'\$[A-Za-z_]\w*', value):
            return True
        match = re.fullmatch(r'\$\{([A-Za-z_][\w.]*)(?:(:?\?)(.*)|(:-|-|:)(.*))?\}', value, re.S)
        if not match:
            return False
        if match.group(2) is not None or match.group(4) is None:
            return True
        value = match.group(5)
        if value.lower() in PLACEHOLDERS:
            return True
    return False  # Deeper nesting is treated as a literal.


def harmless(value):
    return value.lower() in PLACEHOLDERS or bool(re.fullmatch(r'<[^<>]+>', value)) or safe_placeholder(value)


def url_credential(value):
    match = URL_CREDENTIAL.search(value)
    return bool(match and not harmless(match.group(1)))


def line_findings(text, flow_maps=False):
    findings = []
    for line in text.splitlines():
        line = line[:LINE_LIMIT]
        if line.lstrip().startswith(('#', '!')):
            continue
        if url_credential(line):
            findings.append(('url', line.strip()))
            continue
        flow = flow_maps and bool(re.search(r'(?:^|:)\s*\{', line))
        for match in KEY_PATTERN.finditer(line):
            depth = 0
            for token in re.findall(r'\$\{|}', line[:match.start(1)]):
                depth = depth + 1 if token == '${' else max(0, depth - 1)
            if depth:
                continue  # a nested placeholder default is a value, not a new key
            raw = line[match.end():]
            value = unquote(flow_scalar(raw) if flow else raw)
            key = re.sub(r'[^a-z0-9]', '', match.group(1).lower())
            if not key.endswith(SENSITIVE_SUFFIXES):
                continue  # policy flags, credential names and token URLs are not credentials
            if key.endswith('privatekey') and value.startswith(('classpath:', 'file:')):
                continue  # key material remains in the referenced resource, not this scalar
            if value.startswith(('{', '[')) or harmless(value):
                continue  # nested configuration is inspected field by field
            findings.append((match.group(1), value))
    return findings


def string_literal(value):
    if isinstance(value, ast.Call) and value.args and ast.unparse(value.func).split('.')[-1] == 'SecretStr':
        value = value.args[0]
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None


def python_findings(text):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return line_findings(text)  # Partial or unusual sources still get a line scan.
    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        # Environment lookups are safe unless their fallback embeds a secret.
        if isinstance(value, ast.Call) and ast.unparse(value.func) in ('os.getenv', 'os.environ.get', 'getenv'):
            value = value.args[1] if len(value.args) > 1 else next((kw.value for kw in value.keywords if kw.arg == 'default'), None)
        secret = string_literal(value)
        if secret is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and ((PYTHON_SENSITIVE.search(target.id) and not harmless(secret)) or url_credential(secret)):
                findings.append((target.id, secret))
    return findings


def introduced(findings, before):
    """Only findings added by this write count; existing lines are unrelated."""
    return list((Counter(findings) - Counter(before)).elements())


def project_relative(path, data):
    root = Path(find_root(path) or os.environ.get('CLAUDE_PROJECT_DIR') or data.get('cwd') or path.parent).resolve()
    try:
        return root, path.resolve().relative_to(root)
    except ValueError:
        return root, Path(path.name)


def configured_testpaths(root):
    """pytest testpaths from pyproject, pytest.ini, tox.ini or setup.cfg."""
    paths = []
    try:
        tool = pyproject(root).get('tool', {}).get('pytest', {})
        for section in (tool.get('ini_options', {}), tool):
            value = section.get('testpaths') if isinstance(section, dict) else None
            paths.extend([value] if isinstance(value, str) else value if isinstance(value, list) else [])
    except (OSError, ValueError, AttributeError):
        pass
    for name, header in (('pytest.ini', 'pytest'), ('.pytest.ini', 'pytest'), ('tox.ini', 'pytest'), ('setup.cfg', 'tool:pytest')):
        try:
            paths.extend(ini_config(root / name).get(header, 'testpaths', fallback='').split())
        except (OSError, ValueError):
            pass
    return [Path(item.strip('/')) for item in paths if isinstance(item, str) and item.strip('/') and '..' not in item]


def test_path(root, relative):
    """Test code: top-level tests/ or test/, configured pytest testpaths, or
    pytest's own file conventions. fixtures/ or testing/ elsewhere is production."""
    name = relative.name.lower()
    if name == 'conftest.py' or (name.startswith('test_') or name.endswith('_test.py')) and name.endswith('.py'):
        return True
    if len(relative.parts) > 1 and relative.parts[0] in ('tests', 'test'):
        return True
    return any(relative.parts[:len(base.parts)] == base.parts for base in configured_testpaths(root) if len(relative.parts) > len(base.parts))


def secrets(data, path):
    if not (config_path(path) or path.suffix == '.py'):
        return
    scan = python_findings if path.suffix == '.py' else (lambda text: line_findings(text, path.suffix in ('.yaml', '.yml', '.json')))
    before = current_text(path)
    found = introduced(scan(proposed(data, path)), scan(before) if before else [])
    if not found:
        return
    root, relative = project_relative(path, data)
    local = path.name.startswith('.env') or path.name.endswith('.env') or test_path(root, relative)
    name = found[0][0] if found[0][0] != 'url' else 'database or service URL'
    if local:
        emit('PreToolUse', f'Possible literal credential ({name}) in {relative}. Confirm it is a local or test-only value that is never committed.', 'ask')
    else:
        emit('PreToolUse', f'Possible hard-coded credential ({name}) in {relative}. Read it from an environment variable such as ${{DB_PASSWORD}} or a secret store.')


def drop_all_calls(text):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return len(re.findall(r'(?m)^[^#\n]*\.drop_all\b', text))
    return sum(1 for node in ast.walk(tree) if isinstance(node, ast.Call) and (
        (isinstance(node.func, ast.Attribute) and node.func.attr == 'drop_all')
        or any(isinstance(arg, ast.Attribute) and arg.attr == 'drop_all' for arg in node.args)))


def ddl(data, path):
    if path.suffix != '.py':
        return
    root, relative = project_relative(path, data)
    if test_path(root, relative) or re.search(r'(?:^|_)(?:dev|local)(?:_|$)', path.stem):
        return
    before = current_text(path)
    if drop_all_calls(proposed(data, path)) > (drop_all_calls(before) if before else 0):
        emit('PreToolUse', f'Destructive metadata.drop_all() in {relative}. Use a reviewed Alembic migration; isolate development resets in a dev/local helper or test fixture.')


def inside(path, base):
    try:
        Path(path).resolve().relative_to(Path(base).resolve())
        return True
    except ValueError:
        return False


def session_scope(data):
    project = Path(os.environ.get('CLAUDE_PROJECT_DIR') or data.get('cwd') or os.getcwd()).resolve()
    cwd = Path(data.get('cwd') or project).resolve()
    worktrees = project / '.claude' / 'worktrees'
    # CLAUDE_PROJECT_DIR stays at the main checkout; cwd follows a worktree.
    # A cwd outside the project (other than its worktrees) does not widen the
    # scope: hints elsewhere belong to other projects.
    primary = cwd if inside(cwd, worktrees) else project

    def allowed(root):
        if not inside(root, project):
            return False
        if inside(root, worktrees) and not (inside(primary, worktrees) and inside(root, primary)):
            return False  # Another session's worktree.
        return True
    return primary, allowed


STOP_BUDGET = 540  # Seconds; the host's default command hook timeout is 600.


def verify_root(root, token, deadline, session=''):
    """Return (message or None, blocking) for one project."""
    remaining = deadline - time.monotonic()
    if remaining < 1:
        return f'FastAPI verification skipped for {root}: Stop time budget exhausted.', token is not None
    try:
        # After an edit by this session, always recheck: a remembered failure
        # from another caller must not turn the gate into a notice.
        result = run_build({'projectRoot': root, 'task': 'verify', 'skipUnchangedFailure': token is None,
                            'timeoutMs': int(min(300, remaining) * 1000)})
    except (OSError, ValueError, TimeoutError, BuildCancelled) as error:
        return f'FastAPI verification could not complete in {root}: {error}', token is not None
    if token is not None:
        clear_pending(root, token, session)
    blocking = token is not None or result.get('changedSinceLastAttempt', False)
    if result.get('unchangedFailure'):
        return (f'FastAPI verification already failed for these unchanged inputs and environment in {root}; '
                'fix the failure, or recheck with the run_build tool (task verify).'), blocking
    if result.get('verificationIncomplete'):
        return 'Final build inputs could not be fully inspected: ' + str(result.get('cacheDiagnostic')), blocking
    if not result['ok']:
        detail = 'timed out' if result['timedOut'] else ('exceeded output limit' if result['outputLimitExceeded'] else f"exit {result['exitCode']}")
        output = (result['stdout'] + result['stderr']).splitlines()
        return f"Build check failed: {result['tasks'][0]} ({detail}) in {root}.\n" + '\n'.join(output[-40:]), blocking
    if result.get('inputsChanged'):
        return f'Build inputs changed during verification in {root}. Exclude generated files (tool.fastapi-tools fingerprint-exclude) or run verification again on the final contents.', blocking
    if not result.get('cacheable', True):
        return 'Final build inputs could not be fully inspected: ' + str(result.get('cacheDiagnostic')), blocking
    return None, False


def stop(data):
    deadline = time.monotonic() + STOP_BUDGET
    # After a block, Claude continues with stop_hook_active=true: still verify,
    # but report to the user instead of blocking again.
    active = bool(data.get('stop_hook_active'))
    primary, allowed = session_scope(data)
    session = str(data.get('session_id') or '')
    messages, blocking = [], False
    try:
        hints = {root: token for root, token in pending_roots(session).items() if allowed(root)}
    except (OSError, ValueError) as error:
        hints = {}
        messages.append(f'FastAPI edit hints unavailable: {error}')
    roots = {}
    try:
        info = discover(primary)
        if info.get('isFastAPI'):
            roots[info['root']] = hints.get(info['root'])
    except ValueError as error:
        if not str(error).startswith('No Python project found'):
            fastapi = isinstance(error, DiscoveryError) and error.is_fastapi
            messages.append(f'FastAPI verification could not discover the project: {error}' if fastapi
                            else f'FastAPI discovery failed: {error}')
            blocking |= fastapi
    for root, token in sorted(hints.items()):
        if root in roots or len(roots) >= 16:
            continue
        if not Path(root).is_dir():
            clear_pending(root, token, session)  # The project was moved or removed.
            continue
        try:
            info = discover(root)
        except ValueError as error:
            if str(error).startswith('No Python project found'):
                clear_pending(root, token, session)
                continue
            messages.append(f'FastAPI discovery failed for edited project {root}: {error}')
            blocking = True
            continue
        if info.get('isFastAPI') and info['root'] == root:
            roots[root] = token
        else:
            clear_pending(root, token, session)
    for root, token in roots.items():
        message, blocks = verify_root(root, token, deadline, session)
        if message:
            messages.append(message)
            blocking |= blocks
    messages.extend(project_runtime.STATE_NOTICE)
    if not messages:
        return
    if blocking and not active:
        emit('Stop', '\n\n'.join(messages))
    else:
        notice('\n\n'.join(messages))


def post_edit(path, session=''):
    try:
        info = discover(path)
    except ValueError as error:
        if not str(error).startswith('No Python project found'):
            notice(f'FastAPI discovery failed: {error}')
        return
    # Batch edits: record pending work, never launch a build for each keystroke.
    # Stop selects hinted projects and also fingerprints edits from any source.
    if info.get('isFastAPI') and relevant(path.resolve(), Path(info['root'])):
        mark_pending(info['root'], session)


def lint(data, path):
    if path.suffix != '.py' or 'versions' not in path.parts or not path.is_file():
        return
    root = find_root(path)
    if root is None:
        return
    inventory = migration_inventory(Path(root))
    relative = path.resolve().relative_to(Path(root)).as_posix()
    if not any(relative.startswith(location.rstrip('/') + '/') for location in inventory['locations']):
        return  # A versions/ package that is not an Alembic location.
    messages = [item['message'] for item in inventory['errors'] + inventory['risks'] if item.get('file') in (None, relative)]
    messages += inventory['warnings']
    if messages:
        emit('PostToolUse', path.name + ': ' + '\n'.join(messages) + '\nNever edit an applied revision; add a new migration.')


def main():
    action = sys.argv[1]
    data = read_input()
    if data is None:
        return
    args = data.get('tool_input', {})
    path = Path(args.get('file_path', ''))
    if not path.is_absolute() and args.get('file_path'):
        path = Path(data.get('cwd') or os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd()) / path
    if action == 'verify-on-stop':
        stop(data)
    elif args.get('file_path'):
        if action == 'guard-secrets':
            secrets(data, path)
        elif action == 'guard-ddl':
            ddl(data, path)
        elif action == 'post-edit-compile':
            post_edit(path, str(data.get('session_id') or ''))
        elif action == 'lint-migration':
            lint(data, path)


if __name__ == '__main__':
    try:
        main()
    except (OSError, TypeError, ValueError, AttributeError, RecursionError, MemoryError) as error:
        notice(f'FastAPI hook skipped: {error}')
