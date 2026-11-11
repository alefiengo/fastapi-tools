#!/usr/bin/env node
// Per-process setup only. Codex CLI 0.167.0 expands no variables in the
// compatibility MCP format and passes no plugin-root variable to its servers
// (codex-mcp/src/plugin_config.rs). Its Agent Plugins format does provide
// PLUGIN_ROOT, but requires a cwd inside the plugin, which would lose the
// workspace cwd that selects the application. Resolve our own installation,
// then explicitly forward that path to MCP.
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const child = spawn('codex', process.argv.slice(2), {
  cwd: process.cwd(),
  env: { ...process.env, FASTAPI_TOOLS_PLUGIN_ROOT: fileURLToPath(new URL('../', import.meta.url)) },
  stdio: 'inherit',
});
// A terminal Ctrl-C already signals the whole foreground group, Codex included:
// forwarding SIGINT would deliver it twice. Signals aimed only at this wrapper
// are forwarded so Codex never outlives it.
process.on('SIGINT', () => {});
for (const signal of ['SIGTERM', 'SIGHUP']) process.on(signal, () => child.kill(signal));
child.on('error', error => { console.error(`Cannot launch Codex: ${error.message}`); process.exitCode = 1; });
child.on('exit', (code, signal) => { process.exitCode = code ?? (signal === 'SIGINT' ? 130 : signal === 'SIGTERM' ? 143 : signal === 'SIGHUP' ? 129 : 1); });
