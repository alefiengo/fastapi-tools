# Releases

1. Choose a semantic version from changes to public tools, configuration and
   installation behavior. Update CHANGELOG.md and compatibility guidance.
2. Align the Claude plugin, marketplace, MCP package, both lockfile roots and
   server initialization version. Align the Codex manifest and doctor guard when
   those components are present. Preserve dependency resolutions unless audited.
3. Run CONTRIBUTING.md checks for the features in the release. Record actual
   platform/tool versions and limitations; behavioral evaluations need a separate
   explicit budget and authorization.
4. Merge normal maintenance through a PR, preserving branch and security rules.
   Tag the validated main commit with an annotated vX.Y.Z tag. Publish using
   `gh release create <tag> --verify-tag --latest --notes-file <file>`.
5. Attach a validation report identifying the exact commit, versions, checks and
   limits. Verify Latest, the tag target, source archive and downloaded report.
   Leave main synchronized and the working tree clean.

Actions and automatic Dependabot updates are disabled; release evidence is local.
Application CI templates remain available. Preserve vulnerability alerts, secret
scanning and branch protections. A GitHub release does not submit the plugin to
host directories, refresh installed caches or establish measured model efficacy.
