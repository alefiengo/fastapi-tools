// Host-boundary regressions: packaging, HTTP targets, shutdown signals, symlinked
// roots, runtime interpreter selection, JUnit decoding, annotations and state cleanup.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const readline = require('node:readline');
const { spawn, spawnSync } = require('node:child_process');
const { buildStateDir, removeBuildState } = require('./build-state.cjs');

const repository = path.resolve(__dirname, '../..');
const entry = path.join(repository, 'mcp-server/index.js');
const pythonExecutable = spawnSync('python3', ['-c', 'import sys; print(sys.executable)'], { encoding: 'utf8' }).stdout.trim();
const value = result => JSON.parse(result.content[0].text);
const project = '[project]\nname="demo"\ndependencies=["fastapi", "pytest"]\n';

async function temporaryRoot(t, prefix) {
  const root = await fsp.realpath(await fsp.mkdtemp(path.join(os.tmpdir(), prefix)));
  t.after(async () => { removeBuildState(root); await fsp.rm(root, { recursive: true, force: true }); });
  return root;
}

async function write(root, files) {
  for (const [name, content] of Object.entries(files)) {
    const file = path.join(root, name);
    await fsp.mkdir(path.dirname(file), { recursive: true });
    await fsp.writeFile(file, content, { mode: name.includes('bin/') ? 0o755 : 0o644 });
  }
}

function connect(t, { root, env = {}, script = entry }) {
  const child = spawn(process.execPath, [script], { cwd: root, env: { ...process.env, PROJECT_ROOT: root, ...env }, stdio: ['pipe', 'pipe', 'pipe'] });
  let serial = 0, stderr = '';
  const pending = new Map();
  child.stderr.on('data', chunk => { stderr += chunk; });
  readline.createInterface({ input: child.stdout }).on('line', line => {
    const data = JSON.parse(line);
    pending.get(data.id)?.(data);
  });
  const exited = new Promise(resolve => child.on('exit', (code, signal) => {
    for (const settle of pending.values()) settle({ error: { message: stderr || 'Server exited' } });
    resolve({ code, signal });
  }));
  t.after(() => { if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL'); });
  const request = (method, params) => new Promise((resolve, reject) => {
    const id = ++serial;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`${method} timed out: ${stderr}`)); }, 15000);
    pending.set(id, data => { clearTimeout(timer); pending.delete(id); data.error ? reject(new Error(data.error.message)) : resolve(data.result); });
    child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
  });
  const ready = request('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'boundary', version: '1' } })
    .then(() => child.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n'));
  return { child, exited, ready, request, call: (name, args = {}) => request('tools/call', { name, arguments: args }) };
}

async function client(t, options) {
  const connection = connect(t, options);
  await connection.ready;
  return connection;
}

async function listener(t, host, handler) {
  const server = http.createServer(handler);
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, host, resolve); });
  t.after(() => new Promise(resolve => server.close(resolve)));
  return server.address().port;
}

const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

test('plugin-root dependencies satisfy Claude Code automatic installation', () => {
  // https://code.claude.com/docs/en/plugins/loading.md: the install runs only when the
  // plugin root contains package.json and a lockfile; registry, https, no overrides.
  const read = file => JSON.parse(fs.readFileSync(path.join(repository, file), 'utf8'));
  const pkg = read('package.json');
  const lock = read('package-lock.json');
  assert.equal(pkg.type, undefined, 'root package stays CommonJS for tests');
  assert.equal(pkg.overrides, undefined);
  assert.ok([2, 3].includes(lock.lockfileVersion));
  assert.deepEqual(lock.packages[''].dependencies, pkg.dependencies);
  assert.deepEqual(lock.packages[''].devDependencies || {}, pkg.devDependencies || {});
  for (const [name, item] of Object.entries(lock.packages)) {
    if (!name) continue;
    assert.ok(!item.link, `${name} must be a registry package`);
    assert.match(item.resolved, /^https:\/\/registry\.npmjs\.org\//, name);
    assert.match(item.integrity, /^sha512-/, name);
  }
  assert.deepEqual(read('mcp-server/package.json'), { type: 'module' });
  assert.equal(fs.existsSync(path.join(repository, 'mcp-server/package-lock.json')), false);
  const parser = lock.packages['node_modules/fast-xml-parser'].version.split('.').map(Number);
  assert.ok(parser[0] > 5 || (parser[0] === 5 && parser[1] >= 12), 'GHSA-474x-hrwr-fgx4 is fixed in 5.12.0');
});

test('loopback host policy uses the parsed hostname', async () => {
  const { isLoopbackHost } = await import(entry);
  for (const url of ['http://localhost:8000', 'http://127.0.0.1', 'http://127.255.0.9', 'http://[::1]:1', 'http://[0:0:0:0:0:0:0:1]', 'http://2130706433', 'http://0x7f.1', 'http://LOCALHOST']) {
    assert.equal(isLoopbackHost(new URL(url).hostname), true, url);
  }
  for (const url of ['http://192.168.0.8', 'http://169.254.169.254', 'http://10.0.0.1', 'http://127.0.0.1.nip.io', 'http://localhost.', 'http://app.localhost', 'http://[::ffff:127.0.0.1]', 'http://[::]', 'http://0.0.0.0', 'http://example.com']) {
    assert.equal(isLoopbackHost(new URL(url).hostname), false, url);
  }
});

test('HTTP tools refuse non-loopback hosts without sending a request', async t => {
  const external = Object.values(os.networkInterfaces()).flat().find(item => item && item.family === 'IPv4' && !item.internal);
  const requests = [];
  const handler = (req, res) => { requests.push(req.url); res.setHeader('content-type', 'application/json'); res.end('{"status":"ok","SecretAccessKey":"never"}'); };
  const port = await listener(t, '0.0.0.0', handler);
  const root = await temporaryRoot(t, 'mcp-boundary-');
  await write(root, { 'pyproject.toml': project });
  const c = await client(t, { root });
  const target = external ? `http://${external.address}:${port}` : 'http://192.0.2.1:9';
  for (const [tool, args] of [['app_health', { baseUrl: target, paths: { health: '/latest/meta-data/iam/security-credentials/role' } }], ['openapi_endpoints', { mode: 'runtime', baseUrl: target }]]) {
    const response = await c.call(tool, args);
    assert.equal(response.isError, true, response.content[0].text);
    assert.match(response.content[0].text, /loopback/);
    assert.doesNotMatch(response.content[0].text, /never/);
  }
  assert.deepEqual(requests, []);
  const oversized = await c.call('app_health', { baseUrl: `http://localhost:${port}/${'a'.repeat(2100)}` });
  assert.equal(oversized.isError, true);
  assert.match(oversized.content[0].text, /2048|too_big|Too big/i);
  assert.deepEqual(requests, []);
  const local = await c.call('app_health', { baseUrl: `http://127.0.0.1:${port}` });
  assert.equal(local.isError, undefined, local.content[0].text);
  assert.equal(value(local).results[0].health.status, 'ok');
});

test('IPv6 loopback remains a valid application target', async t => {
  let port;
  try { port = await listener(t, '::1', (req, res) => res.end('{"status":"ok"}')); } catch { t.skip('IPv6 loopback unavailable'); return; }
  const root = await temporaryRoot(t, 'mcp-boundary-');
  await write(root, { 'pyproject.toml': project });
  const c = await client(t, { root });
  const response = await c.call('app_health', { baseUrl: `http://[::1]:${port}` });
  assert.equal(response.isError, undefined, response.content[0].text);
});

test('read-only tools declare annotations and executing tools do not', async t => {
  const root = await temporaryRoot(t, 'mcp-boundary-');
  await write(root, { 'pyproject.toml': project });
  const c = await client(t, { root });
  const tools = Object.fromEntries((await c.request('tools/list', {})).tools.map(tool => [tool.name, tool.annotations || {}]));
  for (const name of ['analyze_project', 'openapi_endpoints', 'app_health']) {
    assert.equal(tools[name].readOnlyHint, true, name);
    assert.equal(tools[name].openWorldHint, false, name);
  }
  for (const name of ['run_build', 'run_tests', 'check_migrations', 'initialize_project']) assert.notEqual(tools[name].readOnlyHint, true, name);
});

for (const signalName of ['SIGINT', 'SIGTERM']) {
  test(`${signalName} from the host stops a running build and its lock holder`, async t => {
    const root = await temporaryRoot(t, 'mcp-signal-');
    const ticks = path.join(root, 'ticks.log');
    await write(root, {
      'pyproject.toml': project,
      '.venv/bin/python': `#!/bin/sh\nfor i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do echo tick >> '${ticks}'; sleep 0.25; done\necho completed >> '${ticks}'\n`,
    });
    const c = await client(t, { root });
    const call = c.call('run_build', { task: 'compile', force: true }).catch(() => null);
    const deadline = Date.now() + 10000;
    while (!fs.existsSync(ticks) && Date.now() < deadline) await sleep(25);
    assert.ok(fs.existsSync(ticks), 'build did not start');
    c.child.kill(signalName);
    const exit = await c.exited;
    assert.equal(exit.code, 128 + os.constants.signals[signalName]);
    await call;
    const atExit = fs.readFileSync(ticks, 'utf8').split('\n').filter(Boolean).length;
    await sleep(1500);
    const lines = fs.readFileSync(ticks, 'utf8').split('\n').filter(Boolean);
    assert.equal(lines.includes('completed'), false);
    assert.ok(lines.length <= atExit + 1, `build kept running: ${atExit} -> ${lines.length}`);
  });
}

test('a symlinked plugin root still serves the tools', async t => {
  const root = await temporaryRoot(t, 'mcp-link-');
  await write(root, { 'pyproject.toml': project });
  const link = path.join(root, 'linked-plugin');
  await fsp.symlink(repository, link, 'dir');
  const c = await client(t, { root, script: path.join(link, 'mcp-server/index.js') });
  assert.equal((await c.request('tools/list', {})).tools.length, 7);
});

test('runtime interpreter skips an older python3 and honors FASTAPI_TOOLS_PYTHON', async t => {
  const root = await temporaryRoot(t, 'mcp-python-');
  const old = '#!/bin/sh\necho 3.10\nexit 3\n';
  await write(root, { 'pyproject.toml': project, 'app/main.py': 'from fastapi import FastAPI\napp = FastAPI()\n', 'bin/python3': old, 'only-old/python3': old, 'bin/python-old': old });
  await fsp.chmod(path.join(root, 'only-old/python3'), 0o755);
  await fsp.chmod(path.join(root, 'bin/python-old'), 0o755);
  await fsp.symlink(pythonExecutable, path.join(root, 'bin/python3.11'));
  // PATH holds only the fixture binaries: an activated 3.10 venv first, 3.11+ later.
  const fallback = await client(t, { root, env: { PATH: path.join(root, 'bin') } });
  const analyzed = await fallback.call('analyze_project');
  assert.equal(analyzed.isError, undefined, analyzed.content[0].text);
  assert.equal(value(analyzed).isFastAPI, true);
  const missing = await client(t, { root, env: { PATH: path.join(root, 'only-old') } });
  const refused = await missing.call('analyze_project');
  assert.equal(refused.isError, true);
  assert.match(value(refused).error, /requires Python 3\.11\+.*python3 \(3\.10\).*python3\.11 \(not found\).*FASTAPI_TOOLS_PYTHON/);
  const override = await client(t, { root, env: { PATH: path.join(root, 'bin'), FASTAPI_TOOLS_PYTHON: path.join(root, 'bin/python-old') } });
  assert.match(value(await override.call('analyze_project')).error, /FASTAPI_TOOLS_PYTHON is not a usable Python 3\.11\+ interpreter/);
  const explicit = await client(t, { root, env: { PATH: path.join(root, 'only-old'), FASTAPI_TOOLS_PYTHON: pythonExecutable } });
  assert.equal((await explicit.call('analyze_project')).isError, undefined);
});

test('JUnit numeric character references are decoded once', async t => {
  const root = await temporaryRoot(t, 'mcp-junit-');
  // pytest/ElementTree writes newlines in attributes as &#10; and escapes literal text.
  const report = '<testsuites><testsuite name="pytest" tests="1" failures="1"><testcase classname="t" name="multi"><failure message="AssertionError: line one&#10;  line &lt;two&gt; &amp;#10; &#x41;">trace</failure></testcase></testsuite></testsuites>';
  await write(root, {
    'pyproject.toml': project,
    '.venv/bin/python': `#!${pythonExecutable}\nimport pathlib\nstate = pathlib.Path.cwd() / '.fastapi-tools'\nstate.mkdir(exist_ok=True)\n(state / 'pytest.xml').write_text(${JSON.stringify(report)})\n`,
  });
  const c = await client(t, { root });
  const response = await c.call('run_tests');
  assert.equal(response.isError, true);
  assert.equal(value(response).failures[0].message, 'AssertionError: line one\n  line <two> &#10; A');
});

test('fixture cleanup removes the runtime build state it created', async t => {
  const root = await temporaryRoot(t, 'mcp-state-');
  await write(root, { 'pyproject.toml': '[project]\nname="demo"\ndependencies=["fastapi"]\n', 'main.py': 'value = 1\n' });
  const c = await client(t, { root });
  assert.equal((await c.call('run_build', { task: 'compile', force: true })).isError, undefined);
  // Detects divergence from runtime state_dir(): the computed folder must exist.
  assert.ok(fs.statSync(buildStateDir(root)).isDirectory());
  removeBuildState(root);
  assert.equal(fs.existsSync(buildStateDir(root)), false);
});

test('runtime and version probe ignore PYTHONPATH while the build still receives it', async t => {
  const root = await temporaryRoot(t, 'mcp-isolated-');
  const library = path.join(root, 'application-path');
  // Outside the project: writing inside it would change the build inputs.
  const seen = path.join(await temporaryRoot(t, 'mcp-isolated-output-'), 'build-pythonpath.txt');
  const marker = name => `open(${JSON.stringify(path.join(root, name + '.imported'))}, 'w').write('imported')\n`;
  await write(root, {
    'pyproject.toml': project,
    'app/main.py': 'from fastapi import FastAPI\napp = FastAPI()\n',
    // Application modules shadowing standard-library names the runtime imports.
    'application-path/secrets.py': marker('secrets'),
    'application-path/json.py': marker('json'),
    '.venv/bin/python': `#!/bin/sh\nprintf '%s' "$PYTHONPATH" > '${seen}'\n`,
  });
  const c = await client(t, { root, env: { PYTHONPATH: library } });
  const analyzed = await c.call('analyze_project');
  assert.equal(analyzed.isError, undefined, analyzed.content[0].text);
  const built = await c.call('run_build', { task: 'compile', force: true });
  assert.equal(built.isError, undefined, built.content[0].text);
  assert.deepEqual((await fsp.readdir(root)).filter(name => name.endsWith('.imported')), []);
  assert.equal(await fsp.readFile(seen, 'utf8'), library);
});

test('an activated 3.11+ venv does not run its .pth startup code in the runtime', async t => {
  const root = await temporaryRoot(t, 'mcp-site-');
  await write(root, { 'pyproject.toml': project, 'app/main.py': 'from fastapi import FastAPI\napp = FastAPI()\n' });
  const venv = path.join(root, 'activated');
  const created = spawnSync(pythonExecutable, ['-m', 'venv', '--without-pip', venv], { encoding: 'utf8' });
  assert.equal(created.status, 0, created.stderr);
  const purelib = spawnSync(path.join(venv, 'bin/python'), ['-c', 'import sysconfig; print(sysconfig.get_paths()["purelib"])'], { encoding: 'utf8' }).stdout.trim();
  const marker = path.join(root, 'pth.imported');
  await fsp.writeFile(path.join(purelib, 'startup.pth'), `import pathlib; pathlib.Path(${JSON.stringify(marker)}).write_text('imported')\n`);
  const c = await client(t, { root, env: { PATH: `${path.join(venv, 'bin')}${path.delimiter}${process.env.PATH}`, VIRTUAL_ENV: venv } });
  const analyzed = await c.call('analyze_project');
  assert.equal(analyzed.isError, undefined, analyzed.content[0].text);
  assert.equal(fs.existsSync(marker), false);
});
