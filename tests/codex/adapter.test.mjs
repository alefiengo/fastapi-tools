import assert from 'node:assert/strict';
import { test } from 'node:test';
import { cp, mkdir, mkdtemp, readFile, readdir, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const { removeBuildState } = createRequire(import.meta.url)('../mcp/build-state.cjs');
const json = async file => JSON.parse(await readFile(path.join(root, file), 'utf8'));
const tools = ['analyze_project', 'app_health', 'check_migrations', 'initialize_project', 'openapi_endpoints', 'run_build', 'run_tests'];
const projectMetadata = '[project]\nname="demo"\nversion="1.0"\ndependencies=["fastapi"]\n';

async function temporary(t) {
  const base = await realpath(await mkdtemp(path.join(tmpdir(), 'fastapi-codex-')));
  t.after(() => { removeBuildState(path.join(base, 'application with spaces')); return rm(base, { recursive: true, force: true }); });
  return base;
}

async function client(t, { relocated = false, nested = false, project = true } = {}) {
  const base = await temporary(t);
  const app = path.join(base, 'application with spaces');
  const cwd = nested ? path.join(app, 'app/nested') : app;
  await mkdir(cwd, { recursive: true });
  if (project) {
    await writeFile(path.join(app, 'pyproject.toml'), projectMetadata);
    // Static inspection and compilation must not import application code.
    await writeFile(path.join(app, 'main.py'), 'from fastapi import FastAPI\napp=FastAPI()\n@app.get("/items")\ndef items(): pass\nraise RuntimeError("never import application")\n');
  }
  let plugin = root;
  if (relocated) {
    // Exercise real relocation, URL escaping and argument boundaries. Keep the
    // installed dependency tree shared; no npm/network/model calls in tests.
    plugin = path.join(base, "plugin ' $() with spaces");
    await mkdir(plugin);
    for (const directory of ['codex', 'runtime']) await cp(path.join(root, directory), path.join(plugin, directory), { recursive: true });
    await mkdir(path.join(plugin, 'mcp-server'));
    for (const file of ['index.js', 'package.json']) await cp(path.join(root, 'mcp-server', file), path.join(plugin, 'mcp-server', file));
    // Dependencies live at the plugin root, where Claude Code installs them.
    for (const file of ['package.json', 'package-lock.json']) await cp(path.join(root, file), path.join(plugin, file));
    await symlink(path.join(root, 'node_modules'), path.join(plugin, 'node_modules'), 'dir');
  }
  const config = await json('codex/mcp.json');
  const server = config.mcpServers['fastapi'];
  const child = spawn(server.command, server.args, {
    cwd,
    env: { ...process.env, FASTAPI_TOOLS_PLUGIN_ROOT: plugin, PROJECT_ROOT: '/stale-project', CLAUDE_PROJECT_DIR: '/stale-claude-project', FASTAPI_APP_PORT: '8181' },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  let serial = 0, stderr = '';
  const pending = new Map();
  child.stderr.on('data', chunk => { stderr += chunk; });
  const lines = createInterface({ input: child.stdout });
  lines.on('line', line => {
    const data = JSON.parse(line);
    pending.get(data.id)?.(data);
  });
  child.on('exit', () => { for (const resolve of pending.values()) resolve({ error: { message: stderr || 'MCP exited' } }); });
  t.after(async () => {
    lines.close();
    if (child.exitCode === null && child.signalCode === null) {
      const exited = once(child, 'exit');
      child.kill('SIGKILL');
      await exited;
    }
  });
  const request = (method, params) => new Promise((resolve, reject) => {
    const id = ++serial;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`${method} timed out: ${stderr}`)); }, 10000);
    pending.set(id, data => {
      clearTimeout(timer); pending.delete(id);
      data.error ? reject(new Error(data.error.message)) : resolve(data.result);
    });
    child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
  });
  const initialized = await request('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'codex-adapter-test', version: '1' } });
  assert.equal(initialized.serverInfo.name, 'mcp-fastapi');
  child.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n');
  return { base, app, cwd, request, call: (name, args = {}) => request('tools/call', { name, arguments: args }) };
}
const value = result => JSON.parse(result.content[0].text);

test('Codex packages skills and its own MCP config, explicitly suppressing default hooks', async () => {
  const manifest = await json('.codex-plugin/plugin.json');
  assert.equal(manifest.name, 'fastapi-tools');
  assert.equal(manifest.version, (await json('.claude-plugin/plugin.json')).version);
  assert.ok(manifest.interface.shortDescription.length <= 30);
  assert.deepEqual(await readdir(path.join(root, '.codex-plugin')), ['plugin.json']);
  for (const key of ['skills', 'mcpServers']) {
    assert.ok(manifest[key].startsWith('./'));
    assert.ok(!manifest[key].split('/').includes('..'));
    await readdir(path.dirname(path.join(root, manifest[key])));
  }
  assert.deepEqual(manifest.hooks, { hooks: {} });
  // Codex 0.167.0 RawPluginManifest has no such field; it would be dropped silently.
  assert.ok(!('requires_local_executor' in manifest));
  assert.ok(!('agents' in manifest));
  assert.ok(!('lspServers' in manifest));
  assert.equal(manifest.skills, './skills/');
  const skillDirectories = await readdir(path.join(root, 'skills'));
  assert.equal(skillDirectories.length, 16);
  assert.equal(manifest.mcpServers, './codex/mcp.json');
  const config = await json('codex/mcp.json');
  assert.doesNotMatch(JSON.stringify(config), /CLAUDE_|\$\{|user_config/);
  assert.equal(config.mcpServers['fastapi'].cwd, undefined);
  const forwarded = config.mcpServers['fastapi'].env_vars;
  assert.equal(new Set(forwarded).size, forwarded.length);
  // Codex passes only DEFAULT_ENV_VARS plus env_vars (codex-rs/rmcp-client/src/utils.rs, rust-v0.167.0).
  for (const name of ['HOME', 'LOGNAME', 'PATH', 'SHELL', 'USER', 'LANG', 'LC_ALL', 'TERM', 'TMPDIR', 'TZ']) assert.ok(!forwarded.includes(name), name);
  for (const name of ['FASTAPI_TOOLS_PLUGIN_ROOT', 'FASTAPI_APP_PORT', 'FASTAPI_TOOLS_PYTHON', 'FASTAPI_TOOLS_STATE_HOME', 'VIRTUAL_ENV', 'PYTHONPATH',
    'UV_PROJECT_ENVIRONMENT', 'UV_CACHE_DIR', 'UV_PYTHON', 'UV_PYTHON_INSTALL_DIR', 'POETRY_HOME', 'POETRY_DATA_DIR',
    'POETRY_CONFIG_DIR', 'POETRY_CACHE_DIR', 'POETRY_VIRTUALENVS_PATH', 'POETRY_VIRTUALENVS_IN_PROJECT',
    'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY',
    'http_proxy', 'https_proxy', 'no_proxy']) assert.ok(forwarded.includes(name), name);
});

test('the actual config and launcher complete MCP initialize/list-tools after relocation', async t => {
  const c = await client(t, { relocated: true, nested: true });
  const names = (await c.request('tools/list', {})).tools.map(tool => tool.name).sort();
  assert.deepEqual(names, tools);
  const analyzed = await c.call('analyze_project');
  assert.ok(!analyzed.isError, analyzed.content[0].text);
  assert.equal(value(analyzed).root, c.app);
  assert.equal(value(analyzed).isFastAPI, true);
  assert.equal(value(analyzed).endpoints.endpoints[0].path, '/items');
});

test('the launcher executes real shared Python syntax checks and surfaces failures', async t => {
  const c = await client(t);
  const first = await c.call('run_build', { task: 'compile', force: true });
  assert.ok(!first.isError, first.content[0].text);
  assert.equal(value(first).exitCode, 0);
  await writeFile(path.join(c.app, 'main.py'), 'def broken(:\n');
  const failed = await c.call('run_build', { task: 'compile', force: true });
  assert.equal(failed.isError, true);
  assert.notEqual(value(failed).exitCode, 0);
});

test('the shared server rejects shell payloads through the adapter', async t => {
  const c = await client(t);
  const response = await c.call('run_build', { task: 'compile; touch INJECTED' });
  assert.equal(response.isError, true);
  assert.ok(!(await readdir(c.app)).includes('INJECTED'));
});

test('initialization requires explicit intent and refuses an existing project', async t => {
  const c = await client(t, { nested: true });
  const destination = path.join(c.cwd, 'new-app');
  const cases = [
    [{ destination, explicitRequest: false }, /explicitRequest|Invalid input/],
    [{ destination: 'new-app', explicitRequest: true }, /absolute directory path/],
    [{ destination, explicitRequest: true }, /Existing Python project or workspace ancestor: pyproject\.toml/],
  ];
  for (const [args, reason] of cases) {
    const response = await c.call('initialize_project', { projectName: 'new-app', ...args });
    assert.equal(response.isError, true, response.content[0].text);
    assert.match(response.content[0].text, reason);
  }
  assert.ok(!(await readdir(c.cwd)).includes('new-app'));
});

test('missing/relative plugin roots fail visibly without selecting the application as a plugin', async () => {
  const server = (await json('codex/mcp.json')).mcpServers['fastapi'];
  for (const rootValue of ['', 'relative-plugin']) {
    const result = spawnSync(server.command, server.args, { env: { ...process.env, FASTAPI_TOOLS_PLUGIN_ROOT: rootValue }, encoding: 'utf8', timeout: 5000 });
    assert.ifError(result.error);
    assert.equal(result.status, 1);
    assert.equal(result.stdout, '');
    assert.match(result.stderr, /FASTAPI_TOOLS_PLUGIN_ROOT is required/);
  }
});

test('the Codex wrapper resolves its own root, keeps cwd/arguments and propagates failure', async t => {
  const base = await temporary(t);
  const bin = path.join(base, 'bin');
  await mkdir(bin);
  await writeFile(path.join(bin, 'codex'), `#!${process.execPath}\nconsole.log(JSON.stringify({cwd:process.cwd(),args:process.argv.slice(2),root:process.env.FASTAPI_TOOLS_PLUGIN_ROOT})); process.exitCode=7;\n`, { mode: 0o755 });
  const args = ['-C', '/application with spaces', 'a prompt with $() and "quotes"'];
  const result = spawnSync(process.execPath, [path.join(root, 'codex/run.mjs'), ...args], {
    cwd: base, env: { ...process.env, PATH: bin + path.delimiter + process.env.PATH, FASTAPI_TOOLS_PLUGIN_ROOT: '/stale-plugin' }, encoding: 'utf8', timeout: 5000,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 7, result.stderr);
  const record = JSON.parse(result.stdout);
  assert.equal(record.cwd, base);
  assert.deepEqual(record.args, args);
  assert.equal(path.resolve(record.root), path.resolve(root));
});

test('the Codex wrapper delivers one terminal SIGINT and forwards SIGTERM/SIGHUP', async t => {
  const base = await temporary(t);
  const bin = path.join(base, 'bin');
  const log = path.join(base, 'signals.log');
  await mkdir(bin);
  await writeFile(path.join(bin, 'codex'), `#!${process.execPath}
const fs = require('node:fs');
for (const name of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(name, () => fs.appendFileSync(${JSON.stringify(log)}, name + '\\n'));
fs.appendFileSync(${JSON.stringify(log)}, 'ready\\n');
setTimeout(() => process.exit(0), 1500);
`, { mode: 0o755 });
  const env = { ...process.env, PATH: bin + path.delimiter + process.env.PATH };
  const wait = async predicate => { for (let i = 0; i < 200 && !(await predicate()); i++) await new Promise(r => setTimeout(r, 10)); };
  const seen = async () => (await readFile(log, 'utf8').catch(() => '')).split('\n').filter(line => line && line !== 'ready');
  for (const [signal, group, expected] of [['SIGINT', true, ['SIGINT']], ['SIGTERM', false, ['SIGTERM']], ['SIGHUP', false, ['SIGHUP']]]) {
    await writeFile(log, '');
    const wrapper = spawn(process.execPath, [path.join(root, 'codex/run.mjs')], { env, detached: true, stdio: 'ignore' });
    const exited = once(wrapper, 'exit');
    await wait(async () => (await readFile(log, 'utf8')).includes('ready'));
    // A terminal Ctrl-C signals the whole foreground group; other signals target the wrapper.
    process.kill(group ? -wrapper.pid : wrapper.pid, signal);
    const [code] = await exited;
    assert.equal(code, 0, signal);
    assert.deepEqual(await seen(), expected, signal);
  }
});
