import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../../', import.meta.url));
const require = createRequire(path.join(root, 'package.json'));
const { parse } = require('yaml');
const read = file => readFileSync(path.join(root, file), 'utf8');
const json = file => JSON.parse(read(file));
const frontmatter = file => parse(read(file).match(/^---\n([\s\S]*?)\n---/)[1]);

test('plugin, marketplace and MCP package versions agree', () => {
  const plugin = json('.claude-plugin/plugin.json');
  const entry = json('.claude-plugin/marketplace.json').plugins.find(p => p.name === plugin.name);
  assert.equal(entry.version, plugin.version);
  assert.match(plugin.version, /^\d+\.\d+\.\d+$/);
  assert.equal(json('package.json').version, plugin.version);
  assert.equal(json('.codex-plugin/plugin.json').version, plugin.version);
  assert.equal(json('package-lock.json').version, plugin.version);
  assert.equal(json('package-lock.json').packages[''].version, plugin.version);
  assert.equal(read('mcp-server/index.js').match(/name: "mcp-fastapi", version: "([^"]+)"/)[1], plugin.version);
});

test('the standalone LSP map registers a Python server with the required fields', () => {
  const servers = json('.lsp.json');
  for (const server of Object.values(servers)) {
    assert.equal(typeof server.command, 'string');
    assert.ok(Object.keys(server.extensionToLanguage).length);
  }
  assert.equal(servers.python.extensionToLanguage['.py'], 'python');
});

test('all declared options reach a component and references resolve', () => {
  const options = json('.claude-plugin/plugin.json').userConfig;
  const server = json('.mcp.json').mcpServers['fastapi'];
  const definition = JSON.stringify(server);
  for (const name of Object.keys(options)) assert.ok(definition.includes(`\${user_config.${name}}`));
  for (const match of definition.matchAll(/\$\{user_config\.(\w+)\}/g)) assert.ok(options[match[1]]);
  assert.equal(server.env.PROJECT_ROOT, '${CLAUDE_PROJECT_DIR}');
  assert.equal(server.env.FASTAPI_APP_PORT, '${user_config.app_port}');
});

test('registered hook launchers and their shared runtime are shipped and executable', () => {
  const config = json('hooks/hooks.json');
  for (const entries of Object.values(config.hooks)) {
    for (const entry of entries) for (const hook of entry.hooks) {
      const relative = hook.command.match(/hooks\/scripts\/[\w.-]+/)[0];
      assert.ok(statSync(path.join(root, relative)).mode & 0o111);
    }
  }
  assert.ok(statSync(path.join(root, 'hooks/scripts/hook-runtime.py')).isFile());
});

test('skills and agents have unique matching names and reviewers cannot mutate files or run commands', () => {
  const skills = readdirSync(path.join(root, 'skills'));
  const names = new Set();
  for (const directory of skills) {
    const data = frontmatter(`skills/${directory}/SKILL.md`);
    assert.equal(data.name, directory);
    assert.equal(typeof data.description, 'string');
    assert.ok(!names.has(data.name)); names.add(data.name);
  }
  for (const file of readdirSync(path.join(root, 'agents')).filter(f => f.endsWith('.md'))) {
    const data = frontmatter(`agents/${file}`);
    assert.equal(data.name, file.slice(0, -3));
    const tools = data.tools.split(',').map(t => t.trim());
    // Only the test-writer may write; reviewers and the design agents are read-only.
    if (data.name !== 'fastapi-test-writer') assert.ok(tools.every(t => ['Read', 'Glob', 'Grep'].includes(t)), data.name);
  }
});

test('GitLab template declares stages and PostgreSQL 18 compose persists its data directory', () => {
  const fences = file => [...read(file).matchAll(/```yaml\n([\s\S]*?)\n```/g)].map(m => parse(m[1]));
  const gitlab = fences('skills/fastapi-ci/SKILL.md').find(doc => doc['image-build']);
  assert.ok(gitlab);
  for (const [name, job] of Object.entries(gitlab)) if (job?.stage) {
    assert.ok(gitlab.stages.includes(job.stage), `${name} uses undefined stage ${job.stage}`);
  }
  const compose = fences('skills/fastapi-docker/SKILL.md').find(doc => doc.services);
  assert.ok(compose.services.db.image.startsWith('postgres:18'));
  assert.ok(compose.services.db.volumes.some(volume => volume.split(':')[1] === '/var/lib/postgresql'));
});

test('MCP lockfile matches package metadata and declared direct dependencies', () => {
  const pkg = json('package.json');
  const lock = json('package-lock.json');
  assert.equal(lock.version, pkg.version);
  assert.deepEqual(lock.packages[''].dependencies, pkg.dependencies);
  assert.deepEqual(lock.packages[''].devDependencies, pkg.devDependencies);
  assert.deepEqual(lock.packages[''].engines, pkg.engines);
  assert.ok(pkg.engines.node);
});

test('dependencies sit at the plugin root, where Claude Code installs them for marketplace plugins', () => {
  // https://code.claude.com/docs/en/plugins/loading.md: the install runs only when the plugin's
  // root directory contains both a package.json and a supported lockfile (npm lockfileVersion 2 or 3).
  const lock = json('package-lock.json');
  assert.ok([2, 3].includes(lock.lockfileVersion));
  assert.ok(Object.keys(json('package.json').dependencies).length > 0);
  assert.equal(json('package.json').overrides, undefined);
  assert.deepEqual(json('mcp-server/package.json'), { type: 'module' });
  assert.ok(!existsSync(path.join(root, 'mcp-server/package-lock.json')));
  const server = json('.mcp.json').mcpServers.fastapi;
  assert.deepEqual(server.args, ['${CLAUDE_PLUGIN_ROOT}/mcp-server/index.js']);
  assert.ok(existsSync(path.join(root, 'mcp-server/index.js')));
  // Claude Code does not document cwd for plugin MCP servers and drops it.
  assert.equal(server.cwd, undefined);
});

test('maintenance instructions stay separate and repository automation is disabled', () => {
  assert.ok(existsSync(path.join(root, 'AGENTS.md')));
  assert.equal(frontmatter('docs/skills/repo-director/SKILL.md').name, 'repo-director');
  assert.ok(!existsSync(path.join(root, 'skills/repo-director')));
  assert.ok(!existsSync(path.join(root, '.github/dependabot.yml')));
  const workflows = path.join(root, '.github/workflows');
  assert.ok(!existsSync(workflows) || readdirSync(workflows).length === 0);
  assert.ok(!read('README.md').includes('/actions/workflows/'));
});


test('registered components and shared runtime are consistent', () => {
  const agents = readdirSync(path.join(root, 'agents')).filter(f => f.endsWith('.md')).sort();
  assert.deepEqual(agents, ['fastapi-api-designer.md', 'fastapi-architect.md', 'fastapi-code-reviewer.md', 'fastapi-docker-reviewer.md', 'fastapi-migration-reviewer.md', 'fastapi-runtime-reviewer.md', 'fastapi-test-writer.md']);
  assert.equal(readdirSync(path.join(root, 'skills')).length, 16);
  assert.ok(!json('.claude-plugin/plugin.json').experimental?.monitors);
  const hooks = json('hooks/hooks.json').hooks;
  assert.equal(Object.values(hooks).flatMap(entries => entries.flatMap(entry => entry.hooks)).length, 5);
  assert.ok(existsSync(path.join(root, 'runtime/project_runtime.py')));
  assert.match(read('hooks/scripts/hook-runtime.py'), /project_runtime/);
  assert.match(read('mcp-server/index.js'), /project_runtime/);
  const review = read('skills/fastapi-pr-review/SKILL.md');
  for (const [name] of review.matchAll(/\bfastapi-[a-z-]+\b/g)) {
    assert.ok(existsSync(path.join(root, `agents/${name}.md`)) || existsSync(path.join(root, `skills/${name}/SKILL.md`)), `Unknown review component: ${name}`);
  }
  assert.match(review, /Prose-only/);
  assert.match(review, /verification status/);
});

const words = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];
const counts = () => ({
  skills: readdirSync(path.join(root, 'skills')).length,
  agents: readdirSync(path.join(root, 'agents')).filter(f => f.endsWith('.md')).length,
  hooks: Object.values(json('hooks/hooks.json').hooks).flatMap(entries => entries.flatMap(entry => entry.hooks)).length,
  tools: [...read('mcp-server/index.js').matchAll(/\bregister\("([a-z_]+)"/g)].map(m => m[1]),
});
const names = directory => readdirSync(path.join(root, directory)).map(f => f.replace(/\.md$/, '')).sort();

test('documented component counts and lists match the shipped components', () => {
  const { skills, agents, hooks, tools } = counts();
  assert.equal(tools.length, 7);
  const readme = read('README.md');
  assert.ok(readme.includes(`${skills} shared skills`));
  assert.ok(readme.includes(`${words[tools.length]} MCP tools`));
  assert.ok(readme.includes(`${words[agents]} specialist agents and ${words[hooks]}\nhooks`));
  const section = heading => readme.split(`## ${heading}\n`)[1].split('\n## ')[0];
  const bullets = text => [...text.matchAll(/^- `([^`]+)`$/gm)].map(m => m[1]).sort();
  assert.deepEqual(bullets(section('Skills')), names('skills'));
  assert.deepEqual(bullets(section('Agents')), names('agents'));
  assert.deepEqual([...section('MCP tools').matchAll(/^\| (\w+) \|/gm)].map(m => m[1]).filter(n => n !== 'Tool').sort(), [...tools].sort());
  const hookNames = [...section('Hooks and verification').matchAll(/^\| ([a-z-]+) \| (?:Pre|Post)?[A-Za-z]+ \|/gm)].map(m => m[1]).filter(n => n !== 'Hook');
  assert.deepEqual(hookNames.sort(), readdirSync(path.join(root, 'hooks/scripts')).filter(f => f.endsWith('.sh') && f !== 'launch.sh').map(f => f.slice(0, -3)).sort());
  assert.equal(hookNames.length, hooks);
  const claude = json('.claude-plugin/plugin.json').description;
  assert.ok(claude.includes(`${skills} skills, ${words[agents]} specialist agents and ${words[tools.length]} MCP tools`));
  assert.ok(json('package.json').description.toLowerCase().startsWith(`${words[tools.length]} fastapi mcp tools`));
  assert.ok(read('docs/codex.md').includes(`exactly\n${skills} skills and ${words[tools.length]} tools`));
  assert.ok(read('docs/capability-matrix.md').includes(`CLI read ${skills}.`));
  assert.ok(read('docs/capability-matrix.md').includes(`Five hooks across three events`) === (hooks === 5));
  const events = Object.keys(json('hooks/hooks.json').hooks).length;
  assert.equal(events, 3);
});

test('manifests carry the same license, repository and homepage as the repository', () => {
  const plugin = json('.claude-plugin/plugin.json');
  const entry = json('.claude-plugin/marketplace.json').plugins[0];
  const codex = json('.codex-plugin/plugin.json');
  assert.match(read('LICENSE'), /^MIT License/);
  for (const manifest of [plugin, entry, codex]) {
    assert.equal(manifest.license, 'MIT');
    assert.equal(manifest.repository, 'https://github.com/alefiengo/fastapi-tools');
    assert.equal(manifest.homepage, `${manifest.repository}#readme`);
    assert.equal(manifest.author.name, plugin.author.name);
  }
  assert.equal(codex.interface.websiteURL, plugin.homepage);
  assert.ok(!('requires_local_executor' in codex));
  const advisory = `${plugin.repository}/security/advisories/new`;
  assert.ok(read('SECURITY.md').includes(`(${advisory})`));
  assert.ok(read('.github/ISSUE_TEMPLATE/config.yml').includes(advisory));
  assert.match(read('SECURITY.md'), /latest release/);
});

test('CHANGELOG sections, dates and links are well formed and the README example names a released tag', () => {
  const log = read('CHANGELOG.md');
  const sections = [...log.matchAll(/^## \[([^\]]+)\](?: - (\d{4}-\d{2}-\d{2}))?$/gm)];
  assert.ok(sections.length >= 3);
  const version = json('.claude-plugin/plugin.json').version;
  const [top, ...released] = sections;
  assert.ok(top[1] === 'Unreleased' || top[1] === version, 'the newest section is Unreleased or the current version');
  if (top[1] === 'Unreleased') assert.ok(released[0][1] === version || version > released[0][1], 'the current version is released or newer');
  const dates = released.map(m => m[2]);
  for (const [index, date] of dates.entries()) {
    assert.ok(date && !Number.isNaN(Date.parse(date)));
    if (index) assert.ok(date <= dates[index - 1], 'sections are newest first');
  }
  for (const [, label] of sections) assert.match(log, new RegExp(`^\\[${label}\\]: https://github.com/alefiengo/fastapi-tools/`, 'm'));
  if (top[1] === 'Unreleased') assert.match(log.split('## [Unreleased]')[1].split(/^## \[/m)[0], /### Compatibility/);
  const tag = read('README.md').match(/--branch v(\d+\.\d+\.\d+) /)[1];
  assert.ok(released.some(m => m[1] === tag), 'README clone example targets a released version');
});

test('documentation keeps no hard-coded plugin version and its relative links resolve', () => {
  const version = json('.claude-plugin/plugin.json').version;
  for (const file of ['docs/codex.md', 'docs/capability-matrix.md', 'docs/architecture.md', 'docs/releases.md', 'CONTRIBUTING.md', 'SECURITY.md']) {
    assert.ok(!new RegExp(`(?<![\\d.])${version.replaceAll('.', '\\.')}(?![\\d.])`).test(read(file)), `${file} embeds the plugin version`);
  }
  const markdown = ['README.md', 'CONTRIBUTING.md', 'SECURITY.md', 'AGENTS.md', 'CHANGELOG.md', 'evals/README.md', 'tests/python-ecosystem/README.md',
    ...readdirSync(path.join(root, 'docs')).filter(f => f.endsWith('.md')).map(f => `docs/${f}`)];
  const broken = [];
  for (const file of markdown) {
    for (const [, target] of read(file).matchAll(/\]\(([^)#\s]+)(?:#[^)]*)?\)/g)) {
      if (/^(?:[a-z]+:)/.test(target)) continue;
      if (!existsSync(path.join(root, path.dirname(file), target))) broken.push(`${file} -> ${target}`);
    }
  }
  assert.deepEqual(broken, []);
});

test('the doctor reads versions from the manifests and hooks start through the shared launcher', () => {
  assert.doesNotMatch(read('scripts/install-doctor.py'), /== '\d+\.\d+\.\d+'/);
  const launcher = path.join(root, 'hooks/scripts/launch.sh');
  assert.ok(statSync(launcher).mode & 0o111);
  for (const file of readdirSync(path.join(root, 'hooks/scripts')).filter(f => f.endsWith('.sh') && f !== 'launch.sh')) {
    assert.match(read(`hooks/scripts/${file}`), /launch\.sh/, file);
  }
});

test('.gitignore keeps environments, dependencies, caches and local state out of the repository', () => {
  const lines = new Set(read('.gitignore').split('\n').map(line => line.trim()));
  for (const entry of ['node_modules/', '__pycache__/', '.venv/', 'venv/', '.fastapi-tools/', '.env', '.env.local', '.claude/settings.local.json', 'evals/results/']) {
    assert.ok(lines.has(entry), `${entry} is ignored`);
  }
});
