const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const readline = require('node:readline');
const http = require('node:http');
const entry = path.resolve(__dirname, '../../mcp-server/index.js');

async function fixture(t, files, env = {}) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'mcp-regression-'));
  for (const [name, content] of Object.entries(files)) {
    const file = path.join(root, name);
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(file, content, { mode: (name.endsWith('/python') || name.startsWith('bin/')) ? 0o755 : 0o644 });
  }
  const child = spawn(process.execPath, [entry], { env: { ...process.env, PROJECT_ROOT: root, ...Object.fromEntries(Object.entries(env).map(([key, value]) => [key, value.replaceAll("{{root}}", root)])) }, stdio: ['pipe', 'pipe', 'pipe'] });
  let serial = 0, stderr = '';
  const pending = new Map();
  child.stderr.on('data', d => stderr += d);
  readline.createInterface({ input: child.stdout }).on('line', line => {
    const data = JSON.parse(line);
    if (pending.has(data.id)) { pending.get(data.id)(data); pending.delete(data.id); }
  });
  child.on('exit', () => { for (const resolve of pending.values()) resolve({ error: { message: stderr || 'Server exited' } }); });
  const request = (method, params) => new Promise((resolve, reject) => {
    const id = ++serial;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`${method} timed out: ${stderr}`)); }, 10000);
    pending.set(id, data => { clearTimeout(timer); data.error ? reject(new Error(data.error.message)) : resolve(data.result); });
    child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
  });
  t.after(async () => { child.kill(); await fs.rm(root, { recursive: true, force: true }); });
  const initialized = await request('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'regression', version: '1' } });
  assert.equal(initialized.protocolVersion, '2025-11-25');
  child.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n');
  const cancel = id => {
    child.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/cancelled', params: { requestId: id, reason: 'test' } }) + '\n');
    // The SDK intentionally suppresses responses to cancelled requests.
    pending.get(id)?.({ result: {} });
    pending.delete(id);
  };
  return { root, request, cancel, call: (name, args = {}) => request('tools/call', { name, arguments: args }), child };
}
const value = result => JSON.parse(result.content[0].text);
const project = '[project]\nname="demo"\ndependencies=["fastapi"]\n';
const fakePython = spawnSync('python3', ['-c', "import runpy; print(runpy.run_path('tests/project-runtime/regressions.py')['FAKE_PYTHON'], end='')"], { cwd: path.resolve(__dirname, '../..'), encoding: 'utf8' }).stdout;
const files = extra => ({ 'pyproject.toml': project, '.venv/bin/python': fakePython, ...extra });

async function listener(t, handler) {
  const server = http.createServer(handler);
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  t.after(() => new Promise(resolve => server.close(resolve)));
  return `http://127.0.0.1:${server.address().port}`;
}

test('real stdio registers six FastAPI tools', async t => {
  const client = await fixture(t, files());
  assert.deepEqual((await client.request('tools/list', {})).tools.map(t => t.name).sort(), ['analyze_project','app_health','check_migrations','openapi_endpoints','run_build','run_tests']);
});

test('analyze_project declares dependencies and routes without executing app', async t => {
  const client = await fixture(t, files({ 'app/main.py': 'from fastapi import FastAPI\napp=FastAPI()\n@app.get("/items")\ndef read(): pass\nraise RuntimeError("never import")\n' }));
  const data = value(await client.call('analyze_project'));
  assert.equal(data.isFastAPI, true);
  assert.deepEqual(data.dependencies, ['fastapi']);
  assert.equal(data.endpoints.endpoints[0].path, '/items');
});

test('validated tasks and test selectors reject shell payloads', async t => {
  const client = await fixture(t, files({ 'tests/test_one.py': 'def test_one(): pass\n' }));
  assert.equal((await client.call('run_build', { task: 'compile; touch injected' })).isError, true);
  for (const testPath of ["X'; touch injected", '--help', '../escape', '/tmp']) {
    assert.equal((await client.call('run_tests', { testPath })).isError, true);
  }
  assert.equal(await fs.stat(path.join(client.root, 'injected')).catch(() => null), null);
  const response = await client.call('run_tests', { testPath: 'tests/test_one.py::test_one' });
  assert.equal(response.isError, undefined);
  assert.equal(value(response).suites[0].tests, 1);
});

test('full gate reuse, forced run and changed source are visible', async t => {
  const client = await fixture(t, files({ 'main.py': 'value=1\n' }));
  assert.equal(value(await client.call('run_build', { task: 'verify' })).reused, false);
  assert.equal(value(await client.call('run_build', { task: 'verify' })).reused, true);
  assert.equal(value(await client.call('run_build', { task: 'verify', force: true })).reused, false);
  await fs.writeFile(path.join(client.root, 'main.py'), 'value=2\n');
  assert.equal(value(await client.call('run_build', { task: 'verify' })).reused, false);
});

test('failed pytest retains diagnostics and excludes stale reports', async t => {
  const client = await fixture(t, files({ '.fastapi-tools/fail': '', '.fastapi-tools/pytest.xml': '<testsuite name="old" tests="9"/>' }));
  const response = await client.call('run_tests');
  const data = value(response);
  assert.equal(response.isError, true); assert.equal(data.exitCode, 7);
  assert.match(data.stderr, /controlled failure/);
  assert.deepEqual(data.suites, []); assert.equal(data.staleReportsIgnored, 1);
});

test('fresh JUnit failures become structured errors', async t => {
  const python = fakePython.replace('failures="0"', 'failures="1"').replace('<testcase name="ok"/>', '<testcase name="bad"><failure message="assert &amp; failed"/></testcase>');
  const client = await fixture(t, files({ '.venv/bin/python': python }));
  const response = await client.call('run_tests');
  assert.equal(response.isError, true);
  assert.equal(value(response).failures[0].message, 'assert & failed');
});

test('DTD test reports are rejected', async t => {
  const python = fakePython.replace('<testsuites>', '<!DOCTYPE testsuites><testsuites>');
  const client = await fixture(t, files({ '.venv/bin/python': python }));
  const response = await client.call('run_tests');
  assert.equal(response.isError, true); assert.match(value(response).reportErrors[0], /DTD/);
});

test('Alembic lint finds missing parents and risks without database access', async t => {
  const client = await fixture(t, files({ 'alembic/versions/x.py': 'revision="x"\ndown_revision="missing"\ndef upgrade():\n    op.drop_table("orders")\n' }));
  const response = await client.call('check_migrations');
  const data = value(response);
  assert.equal(response.isError, true); assert.equal(data.databaseAccess, false);
  assert.equal(data.errors[0].code, 'missing-parent'); assert.equal(data.risks.length, 1);
  assert.equal(await fs.stat(path.join(client.root, '.fastapi-tools/calls')).catch(() => null), null);
  const status = value(await client.call('check_migrations', { mode: 'status' }));
  assert.ok(status.command.includes('alembic')); assert.equal(status.command.at(-1), 'current');
});

test('runtime OpenAPI uses /openapi.json and comparison keeps evidence separate', async t => {
  const requests = [];
  const baseUrl = await listener(t, (req, res) => { requests.push(req.url); res.end(JSON.stringify({ openapi: '3.1.0', paths: { '/items': { get: { operationId: 'items' } }, '/runtime': { post: {} } } })); });
  const client = await fixture(t, files({ 'main.py': 'from fastapi import FastAPI\napp=FastAPI()\n@app.get("/items")\ndef read(): pass\n' }));
  const data = value(await client.call('openapi_endpoints', { mode: 'compare', baseUrl }));
  assert.deepEqual(requests, ['/openapi.json']);
  assert.equal(data.runtime.count, 2); assert.equal(data.comparison.onlyRuntime[0].path, '/runtime');
  assert.deepEqual(data.comparison.onlyStatic, []);
});

test('health defaults, configured paths and absent/denied endpoints are diagnosed', async t => {
  const requests = [];
  const baseUrl = await listener(t, (req, res) => { requests.push(req.url); if (req.url === '/ready') res.end('{"status":"ok"}'); else { res.statusCode = req.url === '/health' ? 404 : 403; res.end('{}'); } });
  const client = await fixture(t, files());
  const missing = await client.call('app_health', { baseUrl });
  assert.equal(missing.isError, true); assert.match(value(missing).results[0].diagnosis, /absent/);
  const ready = await client.call('app_health', { baseUrl, probes: ['readiness'], paths: { readiness: '/ready' } });
  assert.equal(ready.isError, undefined); assert.equal(value(ready).results[0].health.status, 'ok');
  const denied = await client.call('app_health', { baseUrl, probes: ['liveness'] });
  assert.equal(denied.isError, true); assert.match(value(denied).results[0].diagnosis, /Access denied/);
  assert.deepEqual(requests, ['/health','/ready','/health/live']);
});

test('runtime document, URL and redirects are validated', async t => {
  const baseUrl = await listener(t, (req, res) => { if (req.url === '/redirect') { res.statusCode=302; res.setHeader('location', '/openapi.json'); } res.end('not JSON'); });
  const client = await fixture(t, files());
  for (const args of [{ baseUrl }, { baseUrl: 'file:///tmp/x' }, { baseUrl: 'http://user:pass@localhost' }, { baseUrl, documentPath: '/redirect' }, { baseUrl, documentPath: '//evil' }]) {
    assert.equal((await client.call('openapi_endpoints', { mode: 'runtime', ...args })).isError, true);
  }
});

test('process output limits and cancellation terminate subprocesses', async () => {
  const { run } = await import(entry);
  const bounded = await run(process.execPath, ['-e', 'console.log("x".repeat(10000))'], { maxOutputBytes: 100 });
  assert.match(bounded.error, /Output limit/); assert.ok(bounded.stdout.length <= 100);
  const controller = new AbortController();
  const pending = run(process.execPath, ['-e', 'setTimeout(()=>{},10000)'], { signal: controller.signal });
  controller.abort(); assert.match((await pending).error, /Cancelled/);
});
