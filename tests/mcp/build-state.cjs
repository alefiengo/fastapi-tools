// Mirrors runtime/project_runtime.py state_dir(): FASTAPI_TOOLS_STATE_HOME when
// set, otherwise <passwd home>/.cache/fastapi-tools (independent of TMPDIR and
// HOME); the folder is build-<sha256 of the resolved project root>. The
// runtime's private temporary fallback (no usable home) is not mirrored here.
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

function stateBase() {
  return process.env.FASTAPI_TOOLS_STATE_HOME || path.join(os.userInfo().homedir, '.cache', 'fastapi-tools');
}

function buildStateDir(root) {
  let resolved;
  try { resolved = fs.realpathSync(root); } catch { resolved = path.resolve(root); }
  const key = crypto.createHash('sha256').update(resolved).digest('hex');
  return path.join(stateBase(), `build-${key}`);
}

// Call before deleting the project directory, while its realpath still resolves.
function removeBuildState(...roots) {
  for (const root of roots) {
    const folder = buildStateDir(root);
    const info = fs.lstatSync(folder, { throwIfNoEntry: false });
    if (info?.isDirectory() && !info.isSymbolicLink()) fs.rmSync(folder, { recursive: true, force: true });
  }
}

module.exports = { buildStateDir, removeBuildState };
