#!/usr/bin/env node
/** Seven FastAPI-aware tools; runtime owns discovery, initialization and checks. */

import { McpServer } from "@modelcontextprotocol/server";
import { serveStdio } from "@modelcontextprotocol/server/stdio";
import { z } from "zod";
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { XMLParser, XMLValidator } from "fast-xml-parser";

// ── helpers ─────────────────────────────────────────────────────────

// Children still running, so a host shutdown signal can stop their process groups.
const activeChildren = new Set();

// No shell interpretation. Bound captured output and terminate the whole process
// group so Python subprocesses cannot keep running after cancellation or timeout.
export function run(command, args = [], { cwd, timeout = 120_000, signal, input, maxOutputBytes = 4 * 1024 * 1024, env = process.env } = {}) {
  return new Promise((resolve) => {
    if (signal?.aborted) { resolve({ stdout: "", stderr: "", exitCode: 1, error: "Cancelled" }); return; }
    let stdout = "", stderr = "", reason, spawnError, size = 0, killTimer;
    const grouped = process.platform !== "win32";
    const child = spawn(command, args, { cwd, env, shell: false, detached: grouped, stdio: [input === undefined ? "ignore" : "pipe", "pipe", "pipe"] });
    if (input !== undefined) { child.stdin.on("error", () => {}); child.stdin.end(input); }
    const kill = (sig) => {
      try { grouped ? process.kill(-child.pid, sig) : child.kill(sig); } catch { /* already exited */ }
    };
    const stop = (why) => {
      if (reason) return;
      reason = why;
      kill("SIGTERM");
      killTimer = setTimeout(() => kill("SIGKILL"), 1000);
      killTimer.unref();
    };
    const capture = (stream) => (chunk) => {
      const remaining = maxOutputBytes - size;
      const text = chunk.subarray(0, Math.max(0, remaining)).toString();
      size += chunk.length;
      if (stream === "stdout") stdout += text; else stderr += text;
      if (size > maxOutputBytes) stop("Output limit exceeded");
    };
    child.stdout.on("data", capture("stdout"));
    child.stderr.on("data", capture("stderr"));
    const abort = () => stop("Cancelled");
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();
    const timer = setTimeout(() => stop("Timed out"), timeout);
    let closed;
    const entry = { stop, closed: new Promise(done => { closed = done; }) };
    activeChildren.add(entry);
    child.on("error", (error) => { spawnError = error.message; stderr += error.message; });
    child.on("close", (code, exitSignal) => {
      // A terminated parent may close its pipes while detached descendants live.
      if (reason) kill("SIGKILL");
      clearTimeout(timer);
      clearTimeout(killTimer);
      signal?.removeEventListener("abort", abort);
      activeChildren.delete(entry);
      closed();
      resolve({ stdout, stderr, exitCode: spawnError ? 1 : code ?? 1, ...(spawnError || reason || exitSignal ? { error: spawnError || reason || `Terminated by ${exitSignal}` } : {}) });
    });
  });
}

const textResult = (value, isError = false) => ({ content: [{ type: "text", text: typeof value === "string" ? value : JSON.stringify(value, null, 2) }], ...(isError ? { isError: true } : {}) });
const result = (r) => textResult(r, r.exitCode !== 0 || r.ok === false || r.inputsChanged === true);
const asArray = (value) => value == null ? [] : Array.isArray(value) ? value : [value];
// An entity map enables numeric references (pytest writes newlines as &#10;) in
// the same single decoding pass, without adding HTML named entities.
const xmlEntities = { amp: "&", apos: "'", gt: ">", lt: "<", quot: "\"" };
const xmlParser = new XMLParser({ ignoreAttributes: false, attributeNamePrefix: "@", parseAttributeValue: false, removeNSPrefix: true, htmlEntities: xmlEntities });
function parseXml(text) {
  if (text.length > 8 * 1024 * 1024) throw new Error("XML file exceeds 8 MiB limit.");
  if (/<!DOCTYPE|<!ENTITY/i.test(text)) throw new Error("DTD and entity declarations are not supported.");
  const valid = XMLValidator.validate(text);
  if (valid !== true) throw new Error(`Invalid XML: ${valid.err.msg}`);
  return xmlParser.parse(text);
}
const runtimeFile = fileURLToPath(new URL("../runtime/project_runtime.py", import.meta.url));
// The runtime needs Python 3.11+ (tomllib); an activated application venv may
// put an older python3 first on PATH. Shared rule with the hook launchers.
export const RUNTIME_PYTHON_CANDIDATES = ["python3", "python3.14", "python3.13", "python3.12", "python3.11"];
// The runtime is standard-library only. -I ignores PYTHON* variables (PYTHONPATH
// could shadow json/secrets with application modules) and the script directory;
// -S skips site, so an activated venv's .pth files never run. os.environ is not
// modified, so build subprocesses still receive the caller's environment.
export const RUNTIME_PYTHON_FLAGS = ["-I", "-S"];
const VERSION_PROBE = "import sys; print('%d.%d' % sys.version_info[:2]); sys.exit(0 if sys.version_info >= (3, 11) else 3)";
export async function selectRuntimePython(env = process.env) {
  const override = env.FASTAPI_TOOLS_PYTHON;
  const checked = [];
  for (const command of override ? [override] : RUNTIME_PYTHON_CANDIDATES) {
    const probe = await run(command, [...RUNTIME_PYTHON_FLAGS, "-c", VERSION_PROBE], { env, timeout: 5000, maxOutputBytes: 1024 });
    const version = /^\d+\.\d+$/.test(probe.stdout.trim()) ? probe.stdout.trim() : null;
    if (!probe.error && probe.exitCode === 0 && version) return command;
    checked.push(`${command} (${version || (probe.error && /ENOENT/.test(probe.stderr) ? "not found" : "unusable")})`);
  }
  throw new Error(override
    ? `FASTAPI_TOOLS_PYTHON is not a usable Python 3.11+ interpreter: ${checked.join(", ")}.`
    : `The plugin runtime requires Python 3.11+; checked ${checked.join(", ")}. Set FASTAPI_TOOLS_PYTHON to a Python 3.11+ interpreter. The application's environment is selected separately.`);
}
// Cached per process; a failed selection is retried on the next request.
let runtimePython;
function runtimeInterpreter(env) {
  runtimePython ??= selectRuntimePython(env).catch(error => { runtimePython = undefined; throw error; });
  return runtimePython;
}
async function runtime(payload, ctx, timeout = 120_000) {
  // This plugin-owned setting selects diagnostic HTTP endpoints, not build inputs.
  const buildEnvironment = { ...process.env };
  delete buildEnvironment.FASTAPI_APP_PORT;
  const python = await runtimeInterpreter(buildEnvironment);
  const execution = await run(python, [...RUNTIME_PYTHON_FLAGS, runtimeFile], {
    input: JSON.stringify({ projectRoot: process.env.PROJECT_ROOT || process.cwd(), ...payload }), env: buildEnvironment,
    timeout, signal: ctx?.mcpReq?.signal, maxOutputBytes: 32 * 1024 * 1024,
  });
  if (execution.error) throw new Error(execution.error);
  let response;
  try { response = JSON.parse(execution.stdout); } catch { throw new Error(`Project runtime failed: ${execution.stderr || execution.stdout}`); }
  if (execution.exitCode !== 0 || response.error) throw new Error(response.error || execution.stderr || "Project runtime failed");
  return response;
}
async function requireProject(ctx) {
  const project = await runtime({ action: "discover" }, ctx);
  if (!project.buildTool) throw new Error("No Python project found.");
  return project;
}
async function build(project, options, ctx, timeout = 120_000) {
  return runtime({ action: "run", projectRoot: project.root, ...options, timeoutMs: timeout }, ctx, timeout + 2000);
}

// ── tool implementations ────────────────────────────────────────────

async function analyzeProject(_args, ctx) {
  return textResult(await runtime({ action: "analyze" }, ctx));
}
async function initializeProject(args, ctx) {
  return result(await runtime({ action: "initialize", ...args }, ctx));
}
async function runBuild(args, ctx) {
  const project = await requireProject(ctx);
  return result(await build(project, { task: args?.task || "compile", reuse: !args?.force }, ctx, 300_000));
}
async function checkMigrations(args, ctx) {
  if (args?.mode === "status") {
    const project = await requireProject(ctx);
    return result(await build(project, { task: "migration-status", reuse: false }, ctx));
  }
  const inventory = await runtime({ action: "migrations" }, ctx);
  return textResult(inventory, inventory.errors.length > 0);
}

// ── tool: run_tests ─────────────────────────────────────────────────
async function runTests(args, ctx) {
  const project = await requireProject(ctx);
  const testPath = args?.testPath;
  {
    // Capture both snapshots and report contents inside the shared build lock.
    // A queued invocation must never claim XML generated by another build.
    const { testReports = [], ...r } = await build(project, { task: "test", testPath, reuse: false, collectTestReports: true }, ctx, 300_000);
    const suites = [], failures = [], reportErrors = [...(r.testReportErrors || [])];
    const staleReportsIgnored = r.staleReportsIgnored || 0;
    for (const { file, content } of testReports) {
      try {
        const parsed = parseXml(content);
        const visit = (suite) => {
          if (!suite) return;
          if (suite["@tests"] !== undefined) suites.push({ suite: suite["@name"] || path.basename(file), tests: Number(suite["@tests"] || 0), failures: Number(suite["@failures"] || 0), errors: Number(suite["@errors"] || 0), skipped: Number(suite["@skipped"] || 0), timeSec: Number(suite["@time"] || 0) });
          for (const test of asArray(suite.testcase)) {
            for (const failure of [...asArray(test.failure), ...asArray(test.error)]) failures.push({ test: `${test["@classname"] || ""}.${test["@name"] || ""}`, message: String(failure["@message"] || failure["#text"] || failure).slice(0, 2000) });
          }
          for (const child of asArray(suite.testsuite)) visit(child);
        };
        for (const suite of asArray(parsed.testsuite ?? parsed.testsuites?.testsuite)) visit(suite);
      } catch (e) { reportErrors.push(`${path.relative(project.root, file)}: ${e.message}`); }
    }
    return textResult({ ...r, suites, failures, staleReportsIgnored, reportErrors, ...(suites.length ? {} : { diagnostic: "No fresh test reports generated by this invocation." }) }, r.exitCode !== 0 || r.ok === false || r.inputsChanged === true || reportErrors.length > 0 || suites.some(s => s.failures || s.errors));
  }
}

// ── tool: openapi_endpoints ─────────────────────────────────────────
async function staticEndpoints(ctx) {
  const analysis = await runtime({ action: "analyze" }, ctx);
  return analysis.endpoints;
}

// The WHATWG parser canonicalizes IPv4 forms (2130706433, 0x7f.1) and IPv6, so
// the parsed hostname is compared literally; other names are never resolved.
export function isLoopbackHost(hostname) {
  if (hostname === "localhost" || hostname === "[::1]") return true;
  const octets = hostname.split(".");
  return octets.length === 4 && octets[0] === "127" && octets.every(octet => /^\d{1,3}$/.test(octet) && Number(octet) <= 255);
}
function appUrl(baseUrl, endpoint) {
  const configuredPort = process.env.FASTAPI_APP_PORT || "8000";
  if (!/^\d+$/.test(configuredPort) || Number(configuredPort) < 1 || Number(configuredPort) > 65535) throw new Error("FASTAPI_APP_PORT must be between 1 and 65535.");
  const url = new URL(baseUrl || `http://localhost:${configuredPort}`);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error("baseUrl must be HTTP(S), without credentials, query or fragment.");
  // Diagnostics target the local application only; never internal or metadata services.
  if (!isLoopbackHost(url.hostname)) throw new Error("baseUrl must target a loopback host: localhost, 127.0.0.0/8 or [::1].");
  url.pathname = url.pathname.replace(/\/$/, "") + endpoint;
  return url;
}
function httpDiagnosis(status) {
  if (status === 401 || status === 403) return "Access denied: check the application's authentication/authorization; no automatic credential forwarding is performed.";
  if (status === 404) return "Endpoint absent: check exposure, configured health or OpenAPI path and whether the relevant feature is configured.";
  if (status >= 500) return "Application or dependency unhealthy; inspect the selected endpoint and application logs.";
  return status >= 200 && status < 300 ? "Endpoint available." : `Unexpected HTTP status ${status}.`;
}
async function fetchDocument(url, ctx) {
  try {
    const response = await fetch(url, { redirect: "error", signal: AbortSignal.any([AbortSignal.timeout(10_000), ...(ctx?.mcpReq?.signal ? [ctx.mcpReq.signal] : [])]) });
    let size = 0, text = "";
    const decoder = new TextDecoder();
    for await (const chunk of response.body || []) {
      size += chunk.length;
      if (size > 2 * 1024 * 1024) throw new Error("HTTP document exceeds 2 MiB limit.");
      text += decoder.decode(chunk, { stream: true });
    }
    text += decoder.decode();
    return { status: response.status, ok: response.ok, text, diagnosis: httpDiagnosis(response.status) };
  } catch (e) { return { ok: false, error: e.message, diagnosis: "Connection, TLS, cancellation or response limit failure; confirm the application port are reachable." }; }
}
async function appHealth(args, ctx) {
  const probes = [...new Set(args?.probes || ["health"])], results = [];
  for (const probe of probes) {
    const endpoint = args?.paths?.[probe] || ({ health: "/health", readiness: "/health/ready", liveness: "/health/live" })[probe];
    const response = await fetchDocument(appUrl(args?.baseUrl, endpoint), ctx);
    let health;
    if (response.ok) {
      try { health = JSON.parse(response.text); } catch { response.ok = false; response.error = "Health endpoint did not return valid JSON."; }
    } else if (response.status >= 500) { try { health = JSON.parse(response.text); } catch { /* no response body disclosure for access errors */ } }
    if (["down", "unhealthy", "error", "DOWN", "OUT_OF_SERVICE"].includes(health?.status)) { response.ok = false; response.diagnosis = "Health reports an unavailable application or dependency; inspect application logs."; }
    results.push({ probe, endpoint, ...response, text: undefined, ...(health ? { health } : {}) });
  }
  return textResult({ results, limitation: "FastAPI has no built-in health routes. Only selected paths are fetched; configure them to match the application. No credentials are forwarded." }, results.some(r => !r.ok));
}
async function openapiEndpoints(args, ctx) {
  const mode = args?.mode || "static";
  const inventory = mode === "runtime" ? undefined : await staticEndpoints(ctx);
  if (mode === "static") return textResult({ mode, ...inventory });
  const response = await fetchDocument(appUrl(args?.baseUrl, args?.documentPath || "/openapi.json"), ctx);
  if (!response.ok) return textResult({ mode, runtime: { ...response, text: undefined }, ...(inventory ? { static: inventory } : {}) }, true);
  let document;
  try {
    document = JSON.parse(response.text);
    if (!document || !/^3\.\d+\.\d+/.test(document.openapi) || !document.paths || typeof document.paths !== "object" || Array.isArray(document.paths)) throw new Error("Expected OpenAPI 3.x document with a paths object.");
  } catch (e) { return textResult({ mode, error: `Invalid runtime OpenAPI: ${e.message}`, ...(inventory ? { static: inventory } : {}) }, true); }
  const endpoints = [], warnings = [];
  for (const [route, item] of Object.entries(document.paths)) {
    if (!route.startsWith("/") || !item || typeof item !== "object") { warnings.push(`Invalid path item: ${route}`); continue; }
    if (item.$ref) warnings.push(`${route}: referenced path item is not resolved; external references are never fetched.`);
    for (const method of ["get", "put", "post", "delete", "options", "head", "patch", "trace"]) if (item[method] && typeof item[method] === "object") endpoints.push({ method: method.toUpperCase(), path: route, operationId: item[method].operationId || null });
  }
  const runtimeInventory = { source: "runtime-openapi", version: document.openapi, status: response.status, endpoints, count: endpoints.length, warnings };
  const result = { mode, runtime: runtimeInventory, ...(inventory ? { static: inventory } : {}) };
  if (inventory) {
    const match = (a, b) => a.path === b.path && (a.method === b.method || a.method === "ANY" || b.method === "ANY");
    result.comparison = { onlyStatic: inventory.endpoints.filter(e => !endpoints.some(r => match(e, r))), onlyRuntime: endpoints.filter(e => !inventory.endpoints.some(r => match(e, r))), limitation: "Differences can reflect conditional routes, mounted apps, router factories, hidden endpoints or static-parser limits; they are findings to investigate, not proven API defects." };
  }
  return textResult(result);
}

// ── server & registration ───────────────────────────────────────────

const readOnly = { readOnlyHint: true, openWorldHint: false };
export function createServer() {
  const server = new McpServer({ name: "mcp-fastapi", version: "0.3.0" });
  const register = (name, description, inputSchema, handler, annotations) => server.registerTool(name, { description, ...(inputSchema ? { inputSchema } : {}), ...(annotations ? { annotations } : {}) }, async (...args) => {
    // The SDK calls schema-less tools with (ctx), others with (args, ctx).
    try { return await handler(...(inputSchema ? args : [{}, args[0]])); } catch (e) { return textResult({ error: e.message }, true); }
  });
  const endpointPath = z.string().regex(/^\/(?!\/)[^?#]*$/).max(300);
  const baseUrl = z.string().max(2048).optional().describe("Loopback application URL (localhost, 127.0.0.0/8 or [::1]); defaults to http://localhost:<app port>.");
  register("analyze_project", "Discover Python project metadata, declared dependencies, environment and static FastAPI routes without importing the app.", undefined, analyzeProject, readOnly);
  register("initialize_project", "Generate a local FastAPI project only for an explicit user request. Requires an absolute absent destination with an existing parent outside Python projects/workspaces; refuses symlink ancestors and concurrent destinations. Installs nothing and executes no code.", z.object({ destination: z.string().min(1).max(4096), projectName: z.string().min(1).max(100), explicitRequest: z.literal(true) }), initializeProject, { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false });
  register("run_build", "Run finite Python checks through shared locks and fingerprints. verify checks syntax plus declared/configured Ruff, mypy and pytest. Does not install dependencies.", z.object({ task: z.enum(["compile", "lint", "typecheck", "package", "verify", "check", "dependencies"]).default("compile"), force: z.boolean().default(false) }), runBuild);
  register("run_tests", "Run pytest with a fresh JUnit report and structured failures under the shared project lock.", z.object({ testPath: z.string().optional().describe("Relative pytest file/directory, optionally ::class::test.") }), runTests);
  register("check_migrations", "Inspect Alembic revision graphs and upgrade risks without database access. Explicit status mode executes alembic current against the configured database.", z.object({ mode: z.enum(["lint", "status"]).default("lint") }), checkMigrations);
  register("openapi_endpoints", "Inventory static FastAPI routes, fetch runtime OpenAPI from the local application or compare both with parser limitations.", z.object({ mode: z.enum(["static", "runtime", "compare"]).default("static"), baseUrl, documentPath: endpointPath.default("/openapi.json") }), openapiEndpoints, readOnly);
  register("app_health", "Query configured health/readiness/liveness paths of the local application. FastAPI does not supply health routes automatically.", z.object({ baseUrl, probes: z.array(z.enum(["health", "readiness", "liveness"])).min(1).max(3).default(["health"]), paths: z.object({ health: endpointPath.optional(), readiness: endpointPath.optional(), liveness: endpointPath.optional() }).optional() }), appHealth, readOnly);
  return server;
}

// Node resolves symlinks in the main module URL but not in argv[1].
function invokedDirectly() {
  if (!process.argv[1]) return false;
  try { return fs.realpathSync(process.argv[1]) === fs.realpathSync(fileURLToPath(import.meta.url)); } catch { return false; }
}

// Claude Code stops stdio servers with SIGINT, SIGTERM 100 ms later and SIGKILL
// 400 ms after that. Detached runtimes outlive a default signal exit, so ask each
// runtime group to stop: the runtime traps SIGTERM and kills its build session.
let shuttingDown = false;
function shutdown(signalName) {
  if (shuttingDown) return;
  shuttingDown = true;
  const pending = [...activeChildren].map(entry => { entry.stop("Server stopped"); return entry.closed; });
  const exit = () => process.exit(128 + (os.constants.signals[signalName] || 0));
  Promise.race([Promise.all(pending), new Promise(done => setTimeout(done, 300))]).then(exit, exit);
}

if (invokedDirectly()) {
  for (const signalName of ["SIGINT", "SIGTERM", "SIGHUP"]) process.on(signalName, () => shutdown(signalName));
  serveStdio(createServer, { onerror: error => console.error(error.message) });
}
