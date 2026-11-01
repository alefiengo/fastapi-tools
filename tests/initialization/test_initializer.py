#!/usr/bin/env python3
"""Initializer safety tests: local generation, anchored staging and no-clobber."""
import ast
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runtime'))
import project_initializer as initializer
from project_runtime import discover, static_endpoints


class InitializerTests(unittest.TestCase):
    def setUp(self):
        # Success fixtures need a temporary base outside existing workspaces.
        # /tmp can itself contain a protected .git mount in agent sandboxes.
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR') or '/var/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.target = self.root / 'service'

    def request(self, **kwargs):
        return dict(destination=str(self.target), projectName='sample-api', explicitRequest=True, **kwargs)

    def assert_clean(self):
        self.assertFalse(any(self.root.glob('.fastapi-tools-init-*')))

    def test_scaffold_is_discoverable_static_and_never_executes_or_installs(self):
        with patch('subprocess.Popen', side_effect=AssertionError('must not execute')):
            result = initializer.initialize_project(self.request())
        self.assertTrue(result['ok'])
        self.assertFalse(result['dependenciesInstalled'])
        self.assertFalse(result['codeExecuted'])
        self.assertEqual(result['files'], sorted(p.relative_to(self.target).as_posix() for p in self.target.rglob('*') if p.is_file()))
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)
        for path in self.target.rglob('*'):
            self.assertFalse(path.is_symlink())
            if path.suffix == '.py':
                ast.parse(path.read_bytes())
            if path.is_file():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        config = tomllib.loads((self.target / 'pyproject.toml').read_text())
        self.assertEqual(config['tool']['fastapi']['entrypoint'], 'app.main:app')
        self.assertIn('pytest', discover(self.target)['checks'])
        self.assertEqual(static_endpoints(self.target)['endpoints'][0]['path'], '/')
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['service'])
        self.assert_clean()

    def test_explicit_request_and_validation_precede_writes(self):
        for field, invalid in [('explicitRequest', None), ('explicitRequest', False), ('explicitRequest', 'true'), ('explicitRequest', 1),
                               ('destination', 'relative'), ('destination', str(self.root / 'missing' / 'child')),
                               ('destination', str(self.root) + '/../bad'), ('destination', '/'),
                               ('projectName', 'x"\nmalicious'), ('projectName', '../bad'), ('projectName', '-bad')]:
            request = self.request(); request[field] = invalid
            with self.subTest(field=field, invalid=invalid), self.assertRaises((ValueError, OSError)):
                initializer.initialize_project(request)
            self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_destinations_including_dangling_links_are_untouched(self):
        for kind in ('directory', 'file', 'link', 'dangling'):
            if kind == 'directory': self.target.mkdir()
            elif kind == 'file': self.target.write_text('original')
            else: self.target.symlink_to(self.root if kind == 'link' else self.root / 'missing')
            before = self.target.lstat()
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'absent'):
                initializer.initialize_project(self.request())
            self.assertEqual(self.target.lstat().st_ino, before.st_ino)
            self.target.rmdir() if kind == 'directory' else self.target.unlink()
            self.assert_clean()

    def test_python_and_workspace_ancestors_are_protected(self):
        parent = self.root / 'nested'; parent.mkdir()
        for marker in ('pyproject.toml', 'setup.py', 'setup.cfg', 'requirements-dev.txt', 'uv.lock', '.venv',
                       'poetry.lock', '__init__.py', '.git', 'package.json', 'pnpm-workspace.yaml', 'demo.code-workspace'):
            file = self.root / marker; file.symlink_to(self.root / 'absent-marker')
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, 'ancestor'):
                initializer.initialize_project({**self.request(), 'destination': str(parent / 'service')})
            file.unlink()
            self.assertEqual(list(parent.iterdir()), [])
            self.assert_clean()

    def test_symlink_ancestor_is_rejected_without_writing_through_it(self):
        real = self.root / 'real'; real.mkdir()
        alias = self.root / 'alias'; alias.symlink_to(real, target_is_directory=True)
        with self.assertRaises(OSError):
            initializer.initialize_project({**self.request(), 'destination': str(alias / 'new')})
        self.assertEqual(list(real.iterdir()), [])
        self.assert_clean()

    def test_private_staging_and_failure_cleanup(self):
        def fail(stage, files):
            self.assertEqual(stat.S_IMODE(os.fstat(stage).st_mode), 0o700)
            self.assertFalse(self.target.exists())
            raise ValueError('controlled failure')
        with patch.object(initializer, 'write_scaffold', fail), self.assertRaisesRegex(ValueError, 'controlled'):
            initializer.initialize_project(self.request())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_exclusive_publication_never_replaces_racing_directory_file_or_symlink(self):
        original = initializer.publish
        for kind in ('directory', 'file', 'symlink'):
            inode = []
            def race(parent, stage, name):
                if kind == 'directory': self.target.mkdir()
                elif kind == 'file': self.target.write_text('keep')
                else: self.target.symlink_to(self.root / 'unrelated')
                inode.append(self.target.lstat().st_ino)
                return original(parent, stage, name)
            with self.subTest(kind=kind), patch.object(initializer, 'publish', race), self.assertRaisesRegex(ValueError, 'appeared'):
                initializer.initialize_project(self.request())
            self.assertEqual(self.target.lstat().st_ino, inode[0])
            if kind == 'file': self.assertEqual(self.target.read_text(), 'keep')
            self.target.rmdir() if kind == 'directory' else self.target.unlink()
            self.assert_clean()

    def test_parent_swap_is_detected_and_cleanup_uses_original_descriptor(self):
        parent = self.root / 'parent'; parent.mkdir()
        moved = self.root / 'moved'
        original = initializer.write_scaffold
        def swap(stage, files):
            original(stage, files)
            parent.rename(moved)
            parent.mkdir()
        with patch.object(initializer, 'write_scaffold', swap), self.assertRaisesRegex(ValueError, 'parent changed'):
            initializer.initialize_project({**self.request(), 'destination': str(parent / 'new')})
        self.assertEqual(list(parent.iterdir()), [])
        self.assertEqual(list(moved.iterdir()), [])

    def test_ancestor_project_appearing_during_staging_is_rejected(self):
        original = initializer.write_scaffold
        def change(stage, files):
            original(stage, files)
            (self.root / 'pyproject.toml').write_text('')
        with patch.object(initializer, 'write_scaffold', change), self.assertRaisesRegex(ValueError, 'ancestor'):
            initializer.initialize_project(self.request())
        self.assertFalse(self.target.exists()); self.assert_clean()

    def test_cli_contract_and_no_replace(self):
        def invoke(request):
            return subprocess.run([sys.executable, str(ROOT / 'runtime/project_runtime.py')], input=json.dumps(request), text=True, capture_output=True, timeout=10)
        response = invoke({'action': 'initialize', **self.request()})
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(json.loads(response.stdout)['destination'], str(self.target))
        response = invoke({'action': 'initialize', **self.request()})
        self.assertEqual(response.returncode, 1)
        self.assertIn('absent', json.loads(response.stdout)['error'])
        self.assert_clean()

    def test_cli_sigterm_cleans_private_staging(self):
        script = '''import sys, time
sys.path.insert(0, sys.argv[1])
import project_initializer, project_runtime
original = project_initializer.write_scaffold
def pause(stage, files):
    original(stage, files)
    print('STAGED', file=sys.stderr, flush=True)
    time.sleep(30)
project_initializer.write_scaffold = pause
project_runtime.main()
'''
        process = subprocess.Popen([sys.executable, '-c', script, str(ROOT / 'runtime')], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            process.stdin.write(json.dumps({'action': 'initialize', **self.request()})); process.stdin.close(); process.stdin = None
            # Bounded readiness wait, without sleeping through a failed child.
            import select
            self.assertTrue(select.select([process.stderr], [], [], 5)[0])
            self.assertEqual(process.stderr.readline().strip(), 'STAGED')
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 1, stderr)
            self.assertIn('cancelled', json.loads(stdout)['error'])
            self.assertEqual(list(self.root.iterdir()), [])
        finally:
            if process.poll() is None: process.kill(); process.wait()

    def test_existing_staging_collision_is_never_removed(self):
        stage = self.root / '.fastapi-tools-init-collision'
        stage.mkdir(); (stage / 'keep').write_text('original')
        with patch.object(initializer.secrets, 'token_hex', return_value='collision'), self.assertRaises(FileExistsError):
            initializer.initialize_project(self.request())
        self.assertEqual((stage / 'keep').read_text(), 'original')
        self.assertFalse(self.target.exists())

    def test_unsupported_exclusive_rename_fails_closed_and_cleans(self):
        with patch.object(initializer.sys, 'platform', 'unsupported'), self.assertRaisesRegex(ValueError, 'unavailable'):
            initializer.initialize_project(self.request())
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
