"""MCP mocks must mirror the real server catalog, and MCP graders must be observable."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from component_inventory_test import PLUGIN, ROOT, frontmatter

SERVER, CONFIG = next(iter(json.loads((ROOT / '.mcp.json').read_text())['mcpServers'].items()))
SCRIPT = CONFIG['args'][0].replace('${CLAUDE_PLUGIN_ROOT}', str(ROOT))
PREFIX = f'mcp__plugin_{PLUGIN}_{SERVER}__'
CATALOG = ROOT / 'evals/mocks' / SERVER / '_tools.json'


def live_catalog():
    """Ask the real stdio server for tools/list; no model, network or project access."""
    script = r"""
const { spawn } = require('node:child_process');
const child = spawn(process.execPath, [process.argv[1]], { cwd: process.argv[2], stdio: ['pipe', 'pipe', 'inherit'],
  env: { ...process.env, PROJECT_ROOT: process.argv[2] } });
let buffer = '';
const send = message => child.stdin.write(JSON.stringify({ jsonrpc: '2.0', ...message }) + '\n');
child.stdout.on('data', chunk => {
  buffer += chunk;
  for (let i; (i = buffer.indexOf('\n')) >= 0;) {
    const message = JSON.parse(buffer.slice(0, i)); buffer = buffer.slice(i + 1);
    if (message.id === 1) { send({ method: 'notifications/initialized' }); send({ id: 2, method: 'tools/list', params: {} }); }
    if (message.id === 2) { process.stdout.write(JSON.stringify(message.result)); child.kill(); }
  }
});
send({ id: 1, method: 'initialize', params: { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'mock-contract', version: '1' } } });
"""
    with tempfile.TemporaryDirectory() as cwd:
        result = subprocess.run([CONFIG['command'], '-e', script, SCRIPT, cwd],
                                capture_output=True, text=True, timeout=30, check=True,
                                env={k: v for k, v in os.environ.items() if k not in ('NODE_OPTIONS', 'NODE_PATH')})
    return json.loads(result.stdout)


def mock_files():
    return sorted(p for p in ROOT.glob('evals/**/mocks/*/*.md') if '/.replay/' not in p.as_posix())


class MockContractTests(unittest.TestCase):
    def test_saved_catalog_is_the_real_tools_list(self):
        self.assertEqual(json.loads(CATALOG.read_text()), live_catalog(),
                         'Regenerate evals/mocks/<server>/_tools.json from the server tools/list result')

    def test_mocks_name_real_tools_and_guard_declared_arguments(self):
        tools = {t['name']: t for t in json.loads(CATALOG.read_text())['tools']}
        self.assertTrue(mock_files())
        for path in mock_files():
            with self.subTest(mock=path.relative_to(ROOT).as_posix()):
                self.assertEqual(path.parent.name, SERVER)
                self.assertIn(path.stem, tools)
                text = path.read_text()
                header = text.split('---', 2)[1] if text.startswith('---\n') else ''
                properties = tools[path.stem]['inputSchema'].get('properties', {})
                for line in header.splitlines():
                    key, _, value = line.partition(':')
                    if line.startswith('  '):
                        self.assertIn(key.strip(), properties)
                        # An unquoted YAML boolean never equals the call input in expect: guards.
                        self.assertNotIn(value.strip(), {'true', 'false'})
                    elif line.strip():
                        self.assertIn(key, {'error', 'expect'})
                for marker in ('/home/', '/Users/', '/tmp/claude', 'scratchpad'):
                    self.assertNotIn(marker, text)

    def test_mcp_graders_target_mocked_plugin_tools(self):
        tools = {t['name'] for t in json.loads(CATALOG.read_text())['tools']}
        found = 0
        for path in ROOT.glob('evals/*/graders/*.md'):
            grader = frontmatter(path)
            tool = grader.get('tool', '')
            if not tool.startswith('mcp__'):
                continue
            found += 1
            with self.subTest(grader=path.relative_to(ROOT).as_posix()):
                self.assertTrue(tool.startswith(PREFIX))
                self.assertIn(tool.removeprefix(PREFIX), tools)
                # An unmocked tool is absent from the run, so even a negative check would pass trivially.
                case = path.parent.parent
                self.assertTrue((case / 'mocks' / SERVER / (tool.removeprefix(PREFIX) + '.md')).is_file())
        self.assertGreaterEqual(found, 5)


if __name__ == '__main__':
    unittest.main()
