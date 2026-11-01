#!/usr/bin/env python3
"""Optional local Codex protocol check; isolated configuration, no model turns.

Requires Codex CLI, Node and the already installed mcp-server dependencies.
Not part of test-basic.sh: CI need not install/authenticate a Codex CLI.
"""
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import tempfile
import time
import threading


ROOT = Path(__file__).resolve().parents[2]
TOOLS = {'app_health', 'analyze_project', 'check_migrations', 'initialize_project',
         'openapi_endpoints', 'run_build', 'run_tests'}


def main():
    with tempfile.TemporaryDirectory(prefix='fastapi-codex-cli-') as temporary:
        base = Path(temporary)
        home = base / 'codex-home'
        home.mkdir()
        market = base / 'market'
        catalog = market / '.agents/plugins/marketplace.json'
        catalog.parent.mkdir(parents=True)
        (market / 'fastapi-tools').symlink_to(ROOT, target_is_directory=True)
        catalog.write_text(json.dumps({
            'name': 'fastapi-isolated',
            'interface': {'displayName': 'FastAPI isolated test'},
            'plugins': [{
                'name': 'fastapi-tools',
                'source': {'source': 'local', 'path': './fastapi-tools'},
                'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_USE'},
            }],
        }))
        app = base / 'application with spaces'
        app.mkdir()
        (app / 'pyproject.toml').write_text(
            '[project]\nname="app"\nversion="1.0"\ndependencies=["fastapi"]\n')
        # Register the shipped MCP wiring only in this disposable host config.
        # plugin/read checks packaging; no plugin/install is ever requested.
        server = json.loads((ROOT / 'codex/mcp.json').read_text())['mcpServers']['fastapi']
        (home / 'config.toml').write_text(
            '[mcp_servers.fastapi]\ncommand = ' + json.dumps(server['command']) +
            '\nargs = ' + json.dumps(server['args']) +
            '\nenv_vars = ' + json.dumps(server['env_vars']) + '\n')
        # No credentials copied and no global installation/config changes.
        environment = {**os.environ, 'CODEX_HOME': str(home),
                       'PROJECT_ROOT': '/stale-project-context'}
        version = subprocess.run(['codex', '--version'], cwd=app, env=environment,
                                 capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        with (base / 'stderr.log').open('w+') as errors:
            child = subprocess.Popen(
                ['node', str(ROOT / 'codex/run.mjs'), 'app-server', '--stdio'],
                cwd=app, env=environment, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=errors, text=True,
                start_new_session=True,
            )
            messages = queue.Queue()

            def read():
                try:
                    for line in child.stdout:
                        messages.put(json.loads(line))
                except Exception as error:
                    messages.put({'readerError': str(error)})

            threading.Thread(target=read, daemon=True).start()
            serial = 0

            def request(method, params):
                nonlocal serial
                # This allowlist prevents accidental addition of a model turn.
                assert method in {
                    'initialize', 'plugin/read', 'thread/start',
                    'mcpServerStatus/list', 'mcpServer/tool/call',
                }, method
                serial += 1
                identifier = serial
                child.stdin.write(json.dumps({'id': identifier, 'method': method,
                                              'params': params}) + '\n')
                child.stdin.flush()
                deadline = time.monotonic() + 30
                while True:
                    try:
                        data = messages.get(timeout=max(0, deadline - time.monotonic()))
                    except queue.Empty:
                        errors.flush()
                        errors.seek(0)
                        raise AssertionError(f'{method} timed out:\n{errors.read()}')
                    assert 'readerError' not in data, data
                    if data.get('id') != identifier:
                        continue
                    assert 'error' not in data, data
                    return data['result']

            try:
                request('initialize', {
                    'clientInfo': {'name': 'fastapi-codex-protocol-check', 'version': '1'},
                    'capabilities': {'experimentalApi': True},
                })
                selector = {'marketplacePath': str(catalog), 'pluginName': 'fastapi-tools'}
                plugin = request('plugin/read', selector)['plugin']
                assert plugin['hooks'] == [], plugin['hooks']
                assert plugin['mcpServers'] == ['fastapi'], plugin['mcpServers']
                skills = list((ROOT / 'skills').glob('*/SKILL.md'))
                assert len(skills) == 16, skills
                assert len(plugin['skills']) == 16, plugin['skills']
                assert any(skill['name'].endswith(':fastapi-initializer') for skill in plugin['skills']), plugin['skills']
                # Starting an empty thread initializes local capabilities. There
                # is no turn/start, prompt, model response or behavioral eval.
                thread = request('thread/start', {
                    'cwd': str(app), 'ephemeral': True,
                    'approvalPolicy': 'never', 'sandbox': 'read-only',
                })['thread']['id']
                status = request('mcpServerStatus/list', {'threadId': thread})
                server = next(item for item in status['data'] if item['name'] == 'fastapi')
                assert not server['toolsError'], server['toolsError']
                assert set(server['tools']) == TOOLS, server['tools']
                payload = request('mcpServer/tool/call', {
                    'threadId': thread, 'server': 'fastapi',
                    'tool': 'analyze_project', 'arguments': {},
                })
                assert not payload.get('isError'), payload
                analyzed = json.loads(payload['content'][0]['text'])
                assert Path(analyzed['root']).resolve() == app.resolve(), analyzed
                print(f'PASS {version}: {len(skills)} skills, no hooks, {len(server["tools"])} MCP tools, actual application cwd; no plugin installation or model turns')
            finally:
                # Kill only this isolated process group, including wrapper/MCP.
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=10)


if __name__ == '__main__':
    main()
