# Releases

Publish from a validated commit on main using a PR and Conventional Commits.
Actions and automatic Dependabot updates are disabled; retain security alerts,
secret scanning and all other PR/history/delete/force-push protections. Do not
claim a hosted CI matrix when only local evidence exists.

Choose versions exclusively from FastAPI Tools changes. This project has its own
release lifecycle; do not align versions or release decisions with another project.
The historical 0.1.0 to 0.3.0 jump is explained in CHANGELOG.md and establishes no
cross-project relationship. Record numbering exceptions explicitly.

1. Select a semantic version and align Claude manifest, marketplace entry, Codex
   manifest, MCP package, both lockfile root versions, MCP initialization literal
   and the expected-version guard in scripts/install-doctor.py.
   Keep identity and existing dependency resolutions unless an audited fix needs change.
2. Update changelog, upgrade instructions, compatibility, security and audit evidence.
   Run CONTRIBUTING.md checks, offline doctor, host registration smoke, real Python
   fixtures and FastAPI examples. Record environment, warnings and limits. Do not
   run paid behavioral evaluations without a separate budget and authorization.
3. Commit, push a branch, open a PR and merge validated changes. Preserve branch
   rules. Verify the merged tree matches the validated tree, then synchronize main.
4. Create an annotated exact version tag at that merged commit; push the tag.
   Publish with `gh release create <tag> --verify-tag --latest --notes-file <file>`.
   Attach a validation report containing the exact commit, versions, commands,
   outcomes, warnings and platform limits. This private MCP package is not an npm
   publication; GitHub provides source archives.
5. Read back release, latest pointer, tag target and all attached files. Confirm
   version alignment and download/verify the validation artifact. Leave main
   synchronized and the working tree clean; remove the completed branch.

Retain earlier tags/releases. GitHub publication does not submit the plugin to
OpenAI or Anthropic directories, refresh installed caches or establish measured
skill efficacy. Installed bundles need updating, dependency installation and a
host restart. A directory validator may report optional listing metadata that is
outside source-release compatibility; preserve that warning in the report.
