#!/usr/bin/env python3
"""Shared hook runtime. Python 3 standard library only; never executes input as shell."""
import ast
import json
import os
from pathlib import Path
import re
import sys


def emit(event, message):
    if event == 'PreToolUse':
        result = {'hookSpecificOutput': {'hookEventName': event, 'permissionDecision': 'deny',
                                       'permissionDecisionReason': message}}
    elif event == 'Stop':
        result = {'decision': 'block', 'reason': message}
    else:
        result = {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': message}}
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))


def notice(message):
    print(json.dumps({'systemMessage': message}, ensure_ascii=False, separators=(',', ':')))


def read_input():
    raw = sys.stdin.read()
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


def proposed(data, path):
    args = data.get('tool_input', {})
    if 'content' in args:
        return args['content']
    if 'new_string' in args:
        old, new = args.get('old_string', ''), args['new_string']
        try:
            text = path.read_text()
        except OSError:
            # At least inspect the replacement if the old file cannot be read.
            return new
        if not old:
            return new if not text else text + '\n' + new
        if old not in text:
            return text + '\n' + new
        return text.replace(old, new, -1 if args.get('replace_all') else 1)
    return ''


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime'))
from project_runtime import discover, mark_pending, run_build, relevant, BuildCancelled



def unquote(value):
    value = re.split(r'\s+#', value, maxsplit=1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def config_path(path):
    return path.suffix in ('.toml', '.yaml', '.yml', '.ini', '.cfg', '.json') or (path.suffix == '.py' and re.search(r'(?:config|settings)', path.stem))


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
    match = re.fullmatch(r'\$\{([A-Za-z_][\w.-]*)(?::(.*))?\}', value)
    if not match:
        return False
    default = match.group(2)
    return default is None or default.lower() in ('', 'changeme', 'change_me', 'example', 'dummy') or safe_placeholder(default)


def embedded_credential(value):
    match = re.search(r'(?i)(?:postgres(?:ql)?(?:\+\w+)?|mysql(?:\+\w+)?)://[^:@/]+:([^@/]+)@', value)
    return bool(match and not safe_placeholder(match.group(1)) and match.group(1).lower() not in ('dummy', 'example', 'changeme'))


def secrets(data, path):
    if not (config_path(path) or path.name.startswith('.env') or path.name.endswith('.env')):
        return
    if path.suffix == '.py':
        python_secrets(data, path)
        return
    # Match each scalar independently: a placeholder elsewhere never exempts a literal.
    pattern = re.compile(r"(?i)(?:^|[\s:{,])[\"']?([\w.-]*(?:password|passwd|secret|api[_-]?key|token|private[_-]?key)[\w.-]*)[\"']?\s*[:=]\s*")
    for line in proposed(data, path).splitlines():
        if line.lstrip().startswith(('#', '!')):
            continue
        if embedded_credential(line):
            emit('PreToolUse', f'Possible hard-coded database URL credential in {path}. Read the password from the environment.')
            return
        flow = path.suffix in ('.yaml', '.yml') and bool(re.search(r'(?:^|:)\s*\{', line))
        for match in pattern.finditer(line):
            depth = 0
            for token in re.findall(r'\$\{|}', line[:match.start(1)]):
                depth = depth + 1 if token == '${' else max(0, depth - 1)
            if depth:
                continue  # a nested placeholder default is a value, not a new key
            raw = line[match.end():]
            value = unquote(flow_scalar(raw) if flow else raw)
            key = re.sub(r'[^a-z0-9]', '', match.group(1).lower())
            if not key.endswith(('password', 'passwd', 'secret', 'apikey', 'token', 'privatekey')):
                continue  # policy flags, credential names and token URLs are not credentials
            if key.endswith('privatekey') and value.startswith(('classpath:', 'file:')):
                continue  # key material remains in the referenced resource, not this scalar
            if value.startswith('{') or value in ('[]', '{}'):
                continue  # nested configuration is inspected field by field
            if not value or value.lower() in ('changeme', 'change_me', 'example', 'dummy'):
                continue
            if re.fullmatch(r'<[^<>]+>', value):
                continue
            if safe_placeholder(value):
                continue
            emit('PreToolUse', f'Possible hard-coded credential ({match.group(1)}) in {path}. Use an environment variable such as ${{DB_PASSWORD}}.')
            return


def python_secrets(data, path):
    try:
        tree = ast.parse(proposed(data, path))
    except SyntaxError:
        return
    sensitive = re.compile(r'(?i)(?:password|passwd|secret|api_?key|token|private_?key)$')
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            value = node.value
            # Environment lookups are safe unless their fallback embeds a secret.
            if isinstance(value, ast.Call) and ast.unparse(value.func) in ('os.getenv', 'os.environ.get', 'getenv'):
                value = value.args[1] if len(value.args) > 1 else next((kw.value for kw in value.keywords if kw.arg == 'default'), None)
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                secret = value.value
                url_secret = embedded_credential(secret)
                if (sensitive.search(target.id) and secret and secret.lower() not in ('changeme', 'change_me', 'dummy', 'example') and not re.fullmatch(r'<[^<>]+>', secret)) or url_secret:
                    emit('PreToolUse', f'Possible hard-coded credential ({target.id}) in {path}. Read secrets from environment variables or a secret store.')
                    return


def ddl(data, path):
    if path.suffix != '.py' or 'tests' in path.parts or re.search(r'(?:^|_)(?:dev|local)(?:_|$)', path.stem):
        return
    try:
        tree = ast.parse(proposed(data, path))
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and ((isinstance(node.func, ast.Attribute) and node.func.attr == 'drop_all') or any(isinstance(arg, ast.Attribute) and arg.attr == 'drop_all' for arg in node.args)):
            emit('PreToolUse', f'Destructive metadata.drop_all() in {path}. Use a reviewed Alembic migration; isolate development resets in a dev/local helper or test fixture.')
            return


def build(event, data, path):
    if event == 'Stop' and data.get('stop_hook_active'):
        return
    location = path if event == 'PostToolUse' else Path(os.environ.get('CLAUDE_PROJECT_DIR') or data.get('cwd') or os.getcwd())
    try:
        info = discover(location)
    except ValueError:
        return
    if not info.get('isFastAPI'):
        return
    if event == 'PostToolUse':
        # Batch edits: record pending work, never launch a build for each keystroke.
        # Stop hashes current sources/configuration and checks edits from any source.
        if relevant(path.resolve(), Path(info['root'])):
            mark_pending(info['root'])
        return
    try:
        result = run_build({'projectRoot': info['root'], 'task': 'verify'}, own_process_group=True)
    except (OSError, ValueError, TimeoutError, BuildCancelled) as error:
        notice(str(error))
        return
    if not result['ok']:
        detail = 'timed out' if result['timedOut'] else ('exceeded output limit' if result['outputLimitExceeded'] else f"exit {result['exitCode']}")
        output = result['stdout'] + result['stderr']
        emit(event, f"Build check failed: {result['tasks'][0]} ({detail}) in {info['root']}.\n" + '\n'.join(output.splitlines()[:40]))
    elif result.get('inputsChanged'):
        emit(event, 'Build inputs changed during verification. Run verification again on the final source contents.')


def lint(data, path):
    if path.suffix != '.py' or 'versions' not in path.parts or not path.is_file():
        return
    from project_runtime import migration_inventory
    try:
        info = discover(path)
    except ValueError:
        return
    inventory = migration_inventory(Path(info['root']))
    relative = path.resolve().relative_to(Path(info['root'])).as_posix()
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
        build('Stop', data, path)
    elif args.get('file_path'):
        if action == 'guard-secrets':
            secrets(data, path)
        elif action == 'guard-ddl':
            ddl(data, path)
        elif action == 'post-edit-compile':
            build('PostToolUse', data, path)
        elif action == 'lint-migration':
            lint(data, path)


if __name__ == '__main__':
    try:
        main()
    except (OSError, TypeError, ValueError, AttributeError) as error:
        notice(f'FastAPI hook skipped: {error}')
