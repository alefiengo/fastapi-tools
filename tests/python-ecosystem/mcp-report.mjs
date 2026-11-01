// Exercise the real MCP report parser against actual pytest output.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

const child = spawn(process.execPath, [fileURLToPath(new URL('../../mcp-server/index.js', import.meta.url))], {
  cwd: process.cwd(), env: { ...process.env, PROJECT_ROOT: process.cwd() },
  stdio: ['pipe', 'pipe', 'pipe'], detached: true,
});
let serial = 0, errors = '';
const pending = new Map();
child.stderr.on('data', data => { errors += data; });
createInterface({ input: child.stdout }).on('line', line => {
  const response = JSON.parse(line);
  pending.get(response.id)?.(response);
});
const request = (method, params) => new Promise((resolve, reject) => {
  const id = ++serial;
  const timer = setTimeout(() => { pending.delete(id); reject(new Error(`${method}: ${errors}`)); }, 45000);
  pending.set(id, response => {
    clearTimeout(timer); pending.delete(id);
    response.error ? reject(new Error(JSON.stringify(response.error))) : resolve(response.result);
  });
  child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
});
try {
  await request('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'real-pytest', version: '1' } });
  child.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n');
  const response = await request('tools/call', { name: 'run_tests', arguments: {} });
  const result = JSON.parse(response.content[0].text);
  assert.equal(response.isError, true, JSON.stringify(result));
  assert.equal(result.exitCode, 1, JSON.stringify(result));
  assert.ok(result.suites.some(suite => suite.tests === 1 && suite.failures === 1), JSON.stringify(result));
  assert.ok(result.failures.some(failure => failure.test.includes('test_hello')), JSON.stringify(result));
  assert.deepEqual(result.reportErrors, []);
  console.log('PASS actual pytest JUnit parsed through MCP');
} finally {
  try { process.kill(-child.pid, 'SIGKILL'); } catch {}
}
