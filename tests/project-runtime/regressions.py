#!/usr/bin/env python3
"""Runtime checks use real processes with a controlled Python environment."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'runtime/project_runtime.py'
sys.path.insert(0, str(RUNTIME.parent))
from project_runtime import discover, build_plan, run_build, static_endpoints, migration_inventory, fingerprint

FAKE_PYTHON = f'''#!{sys.executable}
import pathlib, sys, time, subprocess
root = pathlib.Path.cwd()
state = root / '.fastapi-tools'
state.mkdir(exist_ok=True)
with (state / 'calls').open('a') as output:
    output.write(' '.join(sys.argv[1:]) + '\\n')
if (state / 'delay').exists():
    time.sleep(float((state / 'delay').read_text()))
if (state / 'noisy').exists():
    print('x' * 10000)
if (state / 'fail').exists():
    print('controlled failure', file=sys.stderr)
    sys.exit(7)
if '--syntax' in sys.argv:
    sys.exit(subprocess.call([{sys.executable!r}, *sys.argv[1:]]))
if 'pytest' in sys.argv:
    (state / 'pytest.xml').write_text('<testsuites><testsuite name="pytest" tests="1" failures="0"><testcase name="ok"/></testsuite></testsuites>')
print('controlled check passed')
'''

def isolate_state(case):
    """Private runtime state per test, removed afterwards (never ~/.cache)."""
    from unittest.mock import patch
    home = tempfile.TemporaryDirectory(prefix='fastapi-tools-state-')
    case.addCleanup(home.cleanup)
    os.chmod(home.name, 0o700)
    patcher = patch.dict(os.environ, {'FASTAPI_TOOLS_STATE_HOME': home.name})
    patcher.start()
    case.addCleanup(patcher.stop)
    return Path(home.name)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.state_home = isolate_state(self)
        self.fixture = tempfile.TemporaryDirectory()
        self.addCleanup(self.fixture.cleanup)
        self.root = Path(self.fixture.name)
        (self.root / 'pyproject.toml').write_text('[project]\nname = "demo"\ndependencies = ["fastapi", "ruff", "mypy", "pytest"]\n')
        (self.root / 'app').mkdir()
        self.source = self.root / 'app/main.py'
        self.source.write_text('value = 1\n')
        self.python = self.root / '.venv/bin/python'
        self.python.parent.mkdir(parents=True)
        self.python.write_text(FAKE_PYTHON)
        self.python.chmod(0o755)
        self.state = self.root / '.fastapi-tools'
        self.state.mkdir()

    def request(self, **extra):
        return {'action':'run', 'projectRoot':str(self.root), 'task':'verify', **extra}

    def invoke(self, **extra):
        result = subprocess.run([sys.executable, str(RUNTIME)], input=json.dumps(self.request(**extra)), capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return json.loads(result.stdout)

    def calls(self):
        return (self.state / 'calls').read_text().splitlines()

    def test_discovery_and_validated_selection(self):
        self.assertEqual(discover(self.source)['root'], str(self.root))
        self.assertTrue(discover(self.root)['isFastAPI'])
        (self.root / 'tests').mkdir()
        test = self.root / 'tests/test_one.py'
        test.write_text('def test_one(): pass\n')
        command = build_plan(self.request(task='test', testPath='tests/test_one.py::test_one'))['command']
        self.assertEqual(command[-1], 'tests/test_one.py::test_one')
        for extra in ({'task':'compile; touch bad'}, {'testPath':'../escape','task':'test'}, {'testPath':'--help','task':'test'}, {'testPath':'tests; echo bad','task':'test'}, {'testPath':str(test),'task':'test'}, {'module':'app'}, {'profiles':['dev']}, {'tasks':['compile','test']}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                build_plan(self.request(**extra))

    def test_nearest_root_and_requirements(self):
        child=self.root/'service'; child.mkdir(); (child/'requirements.txt').write_text('fastapi>=0.100\n')
        self.assertEqual(discover(child)['root'], str(child))
        self.assertTrue(discover(child)['isFastAPI'])

    def test_ambiguous_managers_are_refused(self):
        (self.root/'uv.lock').write_text('version = 1\n')
        (self.root/'poetry.lock').write_text('')
        with self.assertRaisesRegex(ValueError, 'Ambiguous Python managers'):
            discover(self.root)

    def test_declared_uv_and_poetry_runner(self):
        from unittest.mock import patch
        (self.root/'uv.lock').write_text('version = 1')
        with patch('project_runtime.shutil.which', return_value='/bin/uv'):
            self.assertEqual(build_plan(self.request(task='test'))['command'][:6], ['/bin/uv','run','--frozen','--offline','--no-sync','python'])
        with patch('project_runtime.shutil.which', return_value=None), self.assertRaises(ValueError):
            build_plan(self.request())
        (self.root/'uv.lock').unlink(); (self.root/'poetry.lock').write_text('')
        with patch('project_runtime.shutil.which', return_value='/bin/poetry'):
            self.assertEqual(build_plan(self.request(task='test'))['command'][:3], ['/bin/poetry','run','python'])

    def test_full_gate_checks_and_reuse(self):
        first=self.invoke(); self.assertTrue(first['ok'], first); self.assertFalse(first['reused'])
        calls=self.calls(); self.assertEqual(len(calls),4)
        self.assertIn('ruff check',calls[1]); self.assertIn('mypy',calls[2]); self.assertIn('pytest',calls[3])
        self.assertTrue(self.invoke()['reused'])
        (self.root/'README.md').write_text('prose')
        self.assertTrue(self.invoke()['reused'])
        self.source.write_text('value = 2\n')
        self.assertFalse(self.invoke()['reused'])
        self.assertFalse(self.invoke(reuse=False)['reused'])

    def test_config_lock_environment_and_deleted_input_invalidate(self):
        self.invoke()
        for name in ('settings.py','requirements-dev.txt','config.json','input-data'):
            file=self.root/name; file.write_text('')
            self.assertFalse(self.invoke()['reused'])
            file.unlink(); self.assertFalse(self.invoke()['reused'])
        before=fingerprint(self.root)
        from unittest.mock import patch
        with patch.dict(os.environ, {'FASTAPI_TEST_CHANGED':'yes'}):
            self.assertNotEqual(before, fingerprint(self.root))

    def test_compile_or_targeted_test_cannot_satisfy_gate(self):
        self.assertTrue(self.invoke(task='compile')['ok'])
        self.assertFalse(self.invoke()['reused'])
        self.assertTrue(self.invoke(task='test', testPath='app')['ok'])
        self.assertFalse(self.invoke()['reused'])

    def test_failure_invalidates_success_and_stops_sequence(self):
        self.invoke(); (self.state/'fail').write_text('')
        result=self.invoke(reuse=False)
        self.assertFalse(result['ok']); self.assertEqual(result['exitCode'],7)
        self.assertIn('controlled failure',result['stderr'])
        (self.state/'fail').unlink()
        self.assertFalse(self.invoke()['reused'])

    def test_syntax_failure_is_real(self):
        self.source.write_text('def broken(:\n')
        result=self.invoke()
        self.assertFalse(result['ok']); self.assertIn('SyntaxError',result['stderr'])
        self.assertEqual(len(self.calls()),1)

    def test_timeout_and_output_limit(self):
        (self.state/'delay').write_text('2')
        result=run_build(self.request(task='test',timeoutMs=100))
        self.assertTrue(result['timedOut']); self.assertFalse(result['ok'])
        (self.state/'delay').unlink(); (self.state/'noisy').write_text('')
        result=run_build(self.request(task='test',maxOutputBytes=100))
        self.assertTrue(result['outputLimitExceeded']); self.assertFalse(result['ok'])

    def test_cross_process_lock(self):
        (self.state/'delay').write_text('.25')
        command=[sys.executable,str(RUNTIME)]
        first=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        first.stdin.write(json.dumps(self.request(task='test',reuse=False))); first.stdin.close(); first.stdin=None
        try:
            deadline=time.monotonic()+5
            while not (self.state/'calls').exists():
                self.assertLess(time.monotonic(),deadline); time.sleep(.02)
            start=time.monotonic(); second=self.invoke(task='test',reuse=False)
            out,err=first.communicate(timeout=5)
            self.assertTrue(json.loads(out)['ok'],err); self.assertTrue(second['ok'])
            self.assertGreater(time.monotonic()-start,.35)
            self.assertEqual(len(self.calls()),2)
        finally:
            if first.poll() is None: first.kill(); first.wait()

    def test_reports_are_fresh_and_stale_excluded(self):
        first=self.invoke(task='test',collectTestReports=True)
        self.assertEqual(len(first['testReports']),1)
        (self.state/'fail').write_text('')
        failed=self.invoke(task='test',collectTestReports=True)
        self.assertEqual(failed['testReports'],[]); self.assertEqual(failed['staleReportsIgnored'],1)

    def test_symlink_report_rejected_and_source_prevents_reuse(self):
        outside=self.root.parent/'outside-report'
        (self.state/'pytest.xml').symlink_to(outside)
        self.assertIn('Unsafe test report',self.invoke(task='test')['error'])
        (self.state/'pytest.xml').unlink()
        (self.root/'external.py').symlink_to(ROOT/'runtime/project_runtime.py')
        result=self.invoke(task='compile'); self.assertTrue(result['ok']); self.assertFalse(result['cacheable'])
        verification=self.invoke(); self.assertFalse(verification['ok']); self.assertTrue(verification['verificationIncomplete'])
        self.assertFalse(self.invoke()['reused'])

    def test_routes_resolve_imports_and_nested_prefixes_without_importing(self):
        self.source.write_text('from fastapi import FastAPI\nfrom .routes import router as items\napp = FastAPI()\napp.include_router(items, prefix="/api/v1")\nraise RuntimeError("must never import")\n')
        (self.root/'app/routes.py').write_text('from fastapi import APIRouter\nrouter=APIRouter(prefix="/items")\n@router.get("/{item_id}")\nasync def read(item_id: int): pass\n')
        inventory=static_endpoints(self.root)
        self.assertEqual(inventory['endpoints'][0]['path'],'/api/v1/items/{item_id}')
        self.assertEqual(inventory['endpoints'][0]['method'],'GET')
        self.assertEqual(inventory['warnings'],[])

    def test_routes_multiple_methods_computed_paths_and_unmounted(self):
        self.source.write_text('from fastapi import FastAPI, APIRouter\napp=FastAPI()\nrouter=APIRouter()\n@app.api_route("/x",methods=["GET","POST"])\ndef read(): pass\n@app.get(PATH)\ndef unknown(): pass\n@router.get("/hidden")\ndef hidden(): pass\n')
        inventory=static_endpoints(self.root)
        self.assertEqual(inventory['count'],2); self.assertEqual(len(inventory['unmounted']),1)
        self.assertTrue(inventory['warnings'])

    def test_alembic_graph_merges_duplicates_cycles_and_upgrade_risks(self):
        directory=self.root/'alembic/versions';directory.mkdir(parents=True)
        def revision(name,rev,down,body='pass'):
            (directory/name).write_text(f'revision={rev!r}\ndown_revision={down!r}\ndef upgrade():\n    {body}\ndef downgrade():\n    op.drop_table("old")\n')
        revision('base.py','base',None)
        revision('a.py','a','base','op.drop_column("orders", "owner")')
        revision('b.py','b','base')
        self.assertEqual(migration_inventory(self.root)['heads'],['a','b'])
        revision('merge.py','merge',('a','b'))
        result=migration_inventory(self.root);self.assertEqual(result['heads'],['merge'])
        self.assertEqual(len(result['risks']),1); self.assertFalse(result['databaseAccess'])
        revision('dup.py','a','missing');revision('loop.py','loop','loop')
        codes={e['code'] for e in migration_inventory(self.root)['errors']}
        self.assertTrue({'duplicate-revision','missing-parent','cycle'} <= codes)

    def test_source_package_named_build_and_generated_coverage(self):
        source=self.root/'src/build/module.py'; source.parent.mkdir(parents=True)
        source.write_text('value=1')
        self.invoke()
        (self.root/'.coverage').write_bytes(b'generated coverage')
        self.assertTrue(self.invoke()['reused'])
        source.write_text('def broken(:')
        result=self.invoke();self.assertFalse(result['ok']);self.assertIn('SyntaxError',result['stderr'])

    def test_computed_alembic_parent_is_not_treated_as_base(self):
        directory=self.root/'alembic/versions'; directory.mkdir(parents=True)
        (directory/'x.py').write_text('revision="x"\ndown_revision=get_parent()\ndef upgrade(): pass\n')
        result=migration_inventory(self.root)
        self.assertEqual(result['migrations'],[])
        self.assertEqual(result['errors'][0]['code'],'metadata')

    def test_custom_alembic_location(self):
        (self.root/'alembic.ini').write_text('[alembic]\nscript_location = db/migrations\n')
        directory=self.root/'db/migrations/versions';directory.mkdir(parents=True)
        (directory/'x.py').write_text('revision="x"\ndown_revision=None\ndef upgrade(): pass\n')
        self.assertEqual(migration_inventory(self.root)['heads'],['x'])

    def test_verify_does_not_impose_undeclared_tools_or_test_runner(self):
        (self.root/'pyproject.toml').write_text('[project]\nname="demo"\ndependencies=["fastapi", "pytest-cov", "ruff-lsp", "mypy-extensions"]\n')
        self.assertEqual(discover(self.root)['checks'], [])
        result=self.invoke(); self.assertTrue(result['ok'], result)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn('--syntax', self.calls()[0])
        for task in ('lint', 'typecheck', 'test'):
            self.assertIn('not declared or configured', self.invoke(task=task)['error'])

    def test_external_tool_configuration_and_static_setup_cfg_declarations(self):
        (self.root/'pyproject.toml').unlink()
        (self.root/'setup.cfg').write_text('[metadata]\nname=cfg-app\n[options]\ninstall_requires=\n    fastapi>=0.100\n[options.extras_require]\ntest=\n    pytest>=7\n[mypy]\nignore_missing_imports=true\n')
        (self.root/'.ruff.toml').write_text('line-length=100\n')
        info=discover(self.root)
        self.assertEqual(info['name'], 'cfg-app')
        self.assertTrue(info['isFastAPI'])
        self.assertEqual(info['checks'], ['mypy','pytest','ruff'])
        self.assertTrue(self.invoke()['ok'])
        (self.root/'setup.cfg').write_text('[metadata]\nname=cfg-app\n')
        (self.root/'.ruff.toml').unlink()
        (self.root/'tox.ini').write_text('[other]\nvalue=1\n')
        self.assertEqual(discover(self.root)['checks'], [])
        (self.root/'tox.ini').write_text('[pytest]\ntestpaths=tests\n')
        self.assertEqual(discover(self.root)['checks'], ['pytest'])

    def test_static_metadata_rejects_symlinks_and_fifos_without_reading_external_data(self):
        outside=self.root/'outside.toml'; outside.write_text('[project]\nname="external"\n')
        config=self.root/'pyproject.toml'; config.unlink(); config.symlink_to(outside)
        result=self.invoke(); self.assertFalse(result['ok']); self.assertIn('error', result)
        config.unlink(); os.mkfifo(config)
        start=time.monotonic(); result=self.invoke()
        self.assertFalse(result['ok']); self.assertLess(time.monotonic()-start, 2)

    def test_report_hardlinks_are_rejected_before_execution(self):
        outside=self.root/'keep.xml'; outside.write_text('unchanged')
        os.link(outside, self.state/'pytest.xml')
        result=self.invoke(task='test'); self.assertIn('Unsafe test report', result['error'])
        self.assertEqual(outside.read_text(), 'unchanged')
        self.assertFalse((self.state/'calls').exists())

    def test_bad_report_after_command_preserves_command_failure_and_output(self):
        self.python.write_text(FAKE_PYTHON.replace("print('controlled check passed')", "(state / 'pytest.xml').unlink(); (state / 'pytest.xml').symlink_to('/unavailable')\nprint('controlled stderr', file=sys.stderr)\nsys.exit(9)"))
        result=self.invoke(task='test', collectTestReports=True)
        self.assertFalse(result['ok']); self.assertEqual(result['exitCode'],9)
        self.assertIn('controlled stderr', result['stderr'])
        self.assertEqual(result['testReports'], [])
        self.assertIn('Unsafe test report', result['testReportErrors'][0])

    def test_destructive_upgrade_sql_word_boundaries(self):
        directory=self.root/'alembic/versions';directory.mkdir(parents=True)
        (directory/'x.py').write_text('revision="x"\ndown_revision=None\ndef upgrade():\n    op.execute("DROP TABLE orders")\n    op.execute("TRUNCATE TABLE logs")\n    op.execute("DELETE FROM users")\n    op.execute("SELECT dropped FROM events")\ndef downgrade():\n    op.execute("DROP TABLE old")\n')
        inventory=migration_inventory(self.root)
        self.assertEqual([risk['code'] for risk in inventory['risks']], ['destructive-sql']*3)

    def test_src_markdown_is_a_build_input(self):
        source=self.root/'src/template.md';source.parent.mkdir();source.write_text('one')
        self.assertTrue(self.invoke()['ok'])
        source.write_text('two'); self.assertFalse(self.invoke()['reused'])

    def test_state_fifo_is_not_opened_as_a_blocking_stream(self):
        from project_runtime import state_read
        os.mkfifo(self.state/'state.json')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            state_read(self.state)

    def test_runtime_request_size_is_bounded(self):
        result=subprocess.run([sys.executable,str(RUNTIME)],input=' '* (1024*1024+1),capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,1)
        self.assertIn('1 MiB',json.loads(result.stdout)['error'])

    def test_setup_failure_cleans_spawned_process(self):
        from unittest.mock import patch, Mock
        from project_runtime import BuildCancelled
        original = subprocess.Popen
        children = []
        def start(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            return child
        selector = Mock()
        selector.register.side_effect = BuildCancelled('cancel during setup')
        with patch('project_runtime.subprocess.Popen', side_effect=start), patch('project_runtime.selectors.DefaultSelector', return_value=selector):
            with self.assertRaises(BuildCancelled):
                run_build(self.request(task='test'))
        self.assertIsNotNone(children[0].poll())
        selector.close.assert_called_once()

    def test_final_fingerprint_failure_is_incomplete_verification(self):
        self.python.write_text(FAKE_PYTHON.replace("print('controlled check passed')", "source=root/'app/main.py'\nif not source.is_symlink():\n    source.unlink(); source.symlink_to(root/'missing.py')\nprint('controlled check passed')"))
        result=self.invoke()
        self.assertEqual(result['exitCode'], 0)
        self.assertFalse(result['ok'])
        self.assertTrue(result['verificationIncomplete'])
        self.assertIn('symlink',result['cacheDiagnostic'])

    def test_signal_during_spawn_is_deferred_then_cleans_child(self):
        import signal
        from unittest.mock import patch
        from project_runtime import BuildCancelled
        original = subprocess.Popen
        children = []
        def start(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            os.kill(os.getpid(), signal.SIGTERM)
            return child
        with patch('project_runtime.subprocess.Popen', side_effect=start):
            with self.assertRaisesRegex(BuildCancelled, 'cancelled'):
                run_build(self.request(task='test'))
        self.assertIsNotNone(children[0].poll())

    # --- Audit 2026-11-11 regressions (R-1..R-20) ---------------------------

    def test_world_writable_ancestor_or_root_is_refused_before_execution(self):
        child = self.root / 'workspace'; child.mkdir()
        os.chmod(self.root, 0o1777)
        self.addCleanup(os.chmod, self.root, 0o700)
        with self.assertRaisesRegex(ValueError, 'writable by other users'):
            discover(child)
        result = subprocess.run([sys.executable, str(RUNTIME)], input=json.dumps({'action': 'run', 'projectRoot': str(child), 'task': 'compile'}),
                                capture_output=True, text=True)
        self.assertIn('writable by other users', json.loads(result.stdout)['error'])
        self.assertFalse((self.state / 'calls').exists())
        os.chmod(self.root, 0o700)
        os.chmod(self.python, 0o757)
        with self.assertRaisesRegex(ValueError, 'untrusted ancestor interpreter'):
            discover(child)
        self.assertEqual(discover(self.root)['root'], str(self.root))  # requested folder itself

    def test_syntax_check_never_needs_runtime_only_modules(self):
        blocker = self.root.parent / (self.root.name + '-blocker')
        blocker.mkdir(); self.addCleanup(lambda: __import__('shutil').rmtree(blocker))
        (blocker / 'tomllib.py').write_text('raise ImportError("simulated Python 3.10: no tomllib")\n')
        self.python.write_text(f'#!/bin/sh\nPYTHONPATH={blocker} exec {sys.executable} "$@"\n')
        result = self.invoke(task='compile')
        self.assertTrue(result['ok'], result)
        self.assertIn('Python syntax check passed', result['stdout'])
        source = (ROOT / 'runtime/source_inventory.py').read_text()
        import ast
        ast.parse(source, feature_version=(3, 8))
        self.assertNotRegex(source, r'(?m)^\s*(?:import|from)\s+tomllib')

    def test_files_written_by_checks_and_configured_exclusions_keep_reuse(self):
        self.python.write_text(FAKE_PYTHON.replace("print('controlled check passed')",
            "import os\nfor name in ('test.db', 'test.db-journal', 'coverage.xml', 'app.log', 'uploads/x.bin', '.hypothesis/examples/x'):\n"
            "    path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(os.urandom(8))\n"
            "print('controlled check passed')"))
        (self.root / 'pyproject.toml').write_text('[project]\nname = "demo"\ndependencies = ["fastapi", "pytest"]\n'
                                                  '[tool.fastapi-tools]\nfingerprint-exclude = ["uploads/*"]\n')
        first = self.invoke(); self.assertTrue(first['ok'], first); self.assertFalse(first['inputsChanged'])
        self.assertTrue(self.invoke()['reused'])
        (self.root / 'pyproject.toml').write_text('[project]\nname = "demo"\ndependencies = ["fastapi", "pytest"]\n'
                                                  '[tool.fastapi-tools]\nfingerprint-exclude = "uploads/*"\n')
        self.assertIn('fingerprint-exclude', self.invoke()['cacheDiagnostic'])

    def test_virtualenv_named_env_and_internal_symlinks_are_inspectable(self):
        env = self.root / 'env'; (env / 'lib').mkdir(parents=True)
        (env / 'pyvenv.cfg').write_text('home = /usr/bin\n'); (env / 'lib64').symlink_to('lib')
        (self.root / 'app/config').mkdir(); (self.root / 'app/config/dev.env').write_text('LOG=info\n')
        (self.root / '.env.local').symlink_to('app/config/dev.env')
        (self.root / 'shared').symlink_to('app', target_is_directory=True)
        first = self.invoke(); self.assertTrue(first['ok'], first); self.assertTrue(first['cacheable'])
        self.assertTrue(self.invoke()['reused'])
        (self.root / 'app/config/dev.env').write_text('LOG=debug\n')
        self.assertFalse(self.invoke()['reused'])
        (self.root / 'outside.py').symlink_to(ROOT / 'runtime/project_runtime.py')
        self.assertTrue(self.invoke()['verificationIncomplete'])

    def test_interpreter_selection_venv_dir_uv_workspace_and_missing_uv_environment(self):
        from unittest.mock import patch
        import shutil as sh
        sh.rmtree(self.root / '.venv')
        python = self.root / 'venv/bin/python'; python.parent.mkdir(parents=True)
        python.write_text(FAKE_PYTHON); python.chmod(0o755)
        self.assertEqual(discover(self.root)['python'], str(python))
        workspace = self.root / 'ws'; member = workspace / 'packages/api'; member.mkdir(parents=True)
        (workspace / 'pyproject.toml').write_text('[project]\nname="root"\n[tool.uv.workspace]\nmembers=["packages/*"]\n')
        (workspace / 'uv.lock').write_text('version = 1\n')
        (member / 'pyproject.toml').write_text('[project]\nname="api"\ndependencies=["fastapi"]\n')
        info = discover(member)
        self.assertEqual((info['buildTool'], info['workspaceRoot']), ('uv', str(workspace)))
        with patch('project_runtime.shutil.which', return_value='/bin/uv'), self.assertRaisesRegex(ValueError, 'environment is missing'):
            build_plan({'projectRoot': str(member), 'task': 'compile'})
        (workspace / '.venv/bin').mkdir(parents=True); (workspace / '.venv/bin/python').write_text(''); (workspace / '.venv/pyvenv.cfg').write_text('')
        with patch('project_runtime.shutil.which', return_value='/bin/uv'):
            self.assertEqual(build_plan({'projectRoot': str(member), 'task': 'compile'})['command'][:6], ['/bin/uv', 'run', '--frozen', '--offline', '--no-sync', 'python'])

    def test_mypy_configured_targets_are_not_overridden(self):
        self.assertEqual(build_plan(self.request(task='typecheck'))['command'][-1], '.')
        (self.root / 'pyproject.toml').write_text('[project]\nname = "demo"\ndependencies = ["fastapi", "mypy"]\n[tool.mypy]\nfiles = ["app"]\n')
        self.assertEqual(build_plan(self.request(task='typecheck'))['command'][-2:], ['-m', 'mypy'])
        (self.root / 'pyproject.toml').write_text('[project]\nname = "demo"\ndependencies = ["fastapi", "mypy"]\n')
        (self.root / 'mypy.ini').write_text('[mypy]\npackages = app\n')
        self.assertEqual(build_plan(self.request(task='typecheck'))['command'][-1], 'mypy')

    def test_parametrized_pytest_ids_are_accepted_without_option_injection(self):
        (self.root / 'tests').mkdir(); (self.root / 'tests/test_one.py').write_text('')
        for selection in ('tests/test_one.py::test_x[1-2]', 'tests/test_one.py::Test::test_x[a b/c]', 'tests/test_one.py::test_x[--flag]'):
            self.assertEqual(build_plan(self.request(task='test', testPath=selection))['command'][-1], selection)
        for selection in ('--co', 'tests/test_one.py[1]', 'tests/test_one.py::test_x[1]::other', 'tests/test_one.py::test_x[\n]', '../x.py::t[1]'):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                build_plan(self.request(task='test', testPath=selection))

    def test_supervisor_kills_build_when_runtime_is_killed_or_hung_up(self):
        import signal
        self.python.write_text(f'#!{sys.executable}\nimport os, pathlib, time\n'
                               f'pathlib.Path({str(self.state / "pid")!r}).write_text(str(os.getpid()))\ntime.sleep(60)\n')
        for signum in (signal.SIGKILL, signal.SIGHUP):
            with self.subTest(signal=signum):
                (self.state / 'pid').unlink(missing_ok=True)
                child = subprocess.Popen([sys.executable, str(RUNTIME)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                child.stdin.write(json.dumps(self.request(task='test'))); child.stdin.close(); child.stdin = None
                deadline = time.monotonic() + 10
                while not (self.state / 'pid').exists():
                    self.assertLess(time.monotonic(), deadline); time.sleep(.05)
                build = int((self.state / 'pid').read_text())
                child.send_signal(signum); child.communicate(timeout=10)
                deadline = time.monotonic() + 5
                while True:
                    try:
                        os.kill(build, 0)
                    except ProcessLookupError:
                        break
                    if time.monotonic() > deadline:
                        os.kill(build, signal.SIGKILL)
                        self.fail('build survived its runtime')
                    time.sleep(.05)

    def test_state_location_ignores_tmpdir_and_is_private(self):
        from unittest.mock import patch
        import project_runtime as runtime
        first = subprocess.run([sys.executable, str(RUNTIME)], input=json.dumps({'action': 'state-location', 'projectRoot': str(self.root)}),
                               capture_output=True, text=True, env=dict(os.environ, TMPDIR=str(self.root)))
        second = subprocess.run([sys.executable, str(RUNTIME)], input=json.dumps({'action': 'state-location', 'projectRoot': str(self.root)}),
                                capture_output=True, text=True, env=dict(os.environ, TMPDIR='/var/tmp'))
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))
        self.assertTrue(json.loads(first.stdout)['stateDir'].startswith(str(self.state_home)))
        with tempfile.TemporaryDirectory() as home:
            os.chmod(home, 0o700)
            account = type('Account', (), {'pw_dir': home})()
            environment = {k: v for k, v in os.environ.items() if k != 'FASTAPI_TOOLS_STATE_HOME'}
            with patch.dict(os.environ, environment, clear=True), patch.object(runtime.pwd, 'getpwuid', return_value=account):
                self.assertEqual(runtime.state_base(), Path(home) / '.cache/fastapi-tools')
                os.chmod(home, 0o777)
                fallback = Path(home) / 'tmp'; fallback.mkdir()
                with patch.object(runtime.tempfile, 'gettempdir', return_value=str(fallback)):
                    self.assertEqual(runtime.state_base(), fallback / f'fastapi-tools-{os.getuid()}')
                os.chmod(home, 0o700)
                os.chmod(Path(home) / '.cache/fastapi-tools', 0o755)
                with self.assertRaisesRegex(ValueError, 'Unsafe build state directory'):
                    runtime.state_base()
        with patch.dict(os.environ, {'FASTAPI_TOOLS_STATE_HOME': 'relative'}), self.assertRaisesRegex(ValueError, 'absolute'):
            runtime.state_base()

    def test_host_adapter_variables_are_not_build_inputs(self):
        from unittest.mock import patch
        before = fingerprint(self.root)
        with patch.dict(os.environ, {'CLAUDE_PLUGIN_OPTION_APP_PORT': '8000', 'CLAUDE_PLUGIN_DATA': '/x', 'FASTAPI_APP_PORT': '1',
                                     'FASTAPI_TOOLS_PYTHON': '/x/python', 'FASTAPI_TOOLS_PLUGIN_ROOT': '/x'}):
            self.assertEqual(before, fingerprint(self.root))
        with patch.dict(os.environ, {'DATABASE_URL': 'sqlite://'}):
            self.assertNotEqual(before, fingerprint(self.root))

    def test_declared_non_fastapi_project_is_not_scanned(self):
        (self.root / 'pyproject.toml').write_text('[project]\nname="django-site"\ndependencies=["django"]\n')
        self.source.write_text('import fastapi\n')
        self.assertFalse(discover(self.root)['isFastAPI'])
        (self.root / 'pyproject.toml').write_text('[project]\nname="slim"\ndependencies=["fastapi-slim"]\n')
        self.assertTrue(discover(self.root)['isFastAPI'])
        (self.root / 'pyproject.toml').write_text('[project]\nname="undeclared"\n')
        self.assertTrue(discover(self.root)['isFastAPI'])

    def test_unchanged_failure_is_not_rerun_and_history_is_reported(self):
        (self.state / 'fail').write_text('')
        first = self.invoke(skipUnchangedFailure=True)
        self.assertFalse(first['ok']); self.assertFalse(first['hadPreviousAttempt'])
        calls = len(self.calls())
        again = self.invoke(skipUnchangedFailure=True)
        self.assertTrue(again['unchangedFailure']); self.assertEqual(len(self.calls()), calls)
        self.source.write_text('value = 3\n')
        changed = self.invoke(skipUnchangedFailure=True)
        self.assertTrue(changed['changedSinceLastAttempt']); self.assertGreater(len(self.calls()), calls)

    def test_migration_inventory_reports_locations_and_text_sql(self):
        directory = self.root / 'alembic/versions'; directory.mkdir(parents=True)
        (directory / 'x.py').write_text('import sqlalchemy as sa\nrevision="x"\ndown_revision=None\ndef upgrade():\n    op.execute(sa.text("DROP TABLE users"))\n')
        inventory = migration_inventory(self.root)
        self.assertEqual(inventory['locations'], ['alembic/versions'])
        self.assertEqual([risk['code'] for risk in inventory['risks']], ['destructive-sql'])

    # --- Independent review regressions (RV-1..RV-9) ------------------------

    def test_linked_directory_into_ignored_location_is_an_input(self):
        target = self.root / 'build/gen'; target.mkdir(parents=True)
        (target / 'mod.py').write_text('value = 1\n')
        (self.root / 'gen').symlink_to('build/gen', target_is_directory=True)
        first = self.invoke(); self.assertTrue(first['ok'], first)
        self.assertTrue(self.invoke()['reused'])
        (target / 'mod.py').write_text('def broken(:\n')
        result = self.invoke()
        self.assertFalse(result['reused']); self.assertFalse(result['ok']); self.assertIn('SyntaxError', result['stderr'])

    def test_indefinite_failures_are_not_remembered(self):
        (self.state / 'delay').write_text('2')
        timed_out = self.invoke(skipUnchangedFailure=True, timeoutMs=300)
        self.assertTrue(timed_out['timedOut'])
        (self.state / 'delay').unlink(); calls = len(self.calls())
        again = self.invoke(skipUnchangedFailure=True)
        self.assertNotIn('unchangedFailure', again); self.assertTrue(again['ok'], again)
        self.assertGreater(len(self.calls()), calls)
        self.python.write_text(FAKE_PYTHON.replace("print('controlled check passed')",
            "if 'pytest' in sys.argv: (root / 'generated.txt').write_text(str(time.time()))\nprint('controlled check passed')"))
        self.assertTrue(self.invoke(skipUnchangedFailure=True, reuse=False)['inputsChanged'])
        self.assertNotIn('unchangedFailure', self.invoke(skipUnchangedFailure=True))

    def test_environment_identity_invalidates_remembered_failure_and_reuse(self):
        site = self.root / '.venv/lib/python3.12/site-packages'; site.mkdir(parents=True)
        (self.root / '.venv/pyvenv.cfg').write_text('home = /usr/bin\n')
        (self.state / 'fail').write_text('')
        self.assertFalse(self.invoke(skipUnchangedFailure=True)['ok'])
        self.assertTrue(self.invoke(skipUnchangedFailure=True)['unchangedFailure'])
        (site / 'fastapi-0.162.0.dist-info').mkdir()  # e.g. after uv sync
        (self.state / 'fail').unlink()
        repaired = self.invoke(skipUnchangedFailure=True)
        self.assertNotIn('unchangedFailure', repaired); self.assertTrue(repaired['ok'], repaired)
        self.assertTrue(self.invoke()['reused'])
        (site / 'fastapi-0.162.0.dist-info').rename(site / 'fastapi-0.163.0.dist-info')
        self.assertFalse(self.invoke()['reused'])

    def test_pending_hints_are_per_session_and_never_lost_by_clear(self):
        import project_runtime as runtime
        runtime.mark_pending(self.root, 'session-a')
        first = runtime.pending_roots('session-a')[str(self.root)]
        runtime.mark_pending(self.root, 'session-b')
        self.assertEqual(set(runtime.pending_roots('session-b')), {str(self.root)})
        self.assertEqual(runtime.pending_roots('session-c'), {})
        runtime.mark_pending(self.root, 'session-a')  # a newer edit while Stop verified
        runtime.clear_pending(self.root, first, 'session-a')
        self.assertIn(str(self.root), runtime.pending_roots('session-a'))
        runtime.clear_pending(self.root, runtime.pending_roots('session-a')[str(self.root)], 'session-a')
        self.assertEqual(runtime.pending_roots('session-a'), {})
        self.assertIn(str(self.root), runtime.pending_roots('session-b'))

    def test_group_writable_roots_need_a_private_group(self):
        from unittest.mock import patch
        import project_runtime as runtime
        child = self.root / 'workspace'; child.mkdir()
        os.chmod(self.root, 0o770); self.addCleanup(os.chmod, self.root, 0o700)
        with patch.object(runtime, 'private_group', return_value=False), self.assertRaisesRegex(ValueError, 'writable by other users'):
            discover(child)
        with patch.object(runtime, 'private_group', return_value=False), self.assertRaisesRegex(ValueError, 'writable by other users'):
            discover(self.root)
        with patch.object(runtime, 'private_group', return_value=True):
            self.assertEqual(discover(child)['root'], str(self.root))

    def test_symlinked_cache_is_accepted_only_when_private_and_fallback_is_reported(self):
        from unittest.mock import patch
        import project_runtime as runtime
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as real:
            os.chmod(home, 0o700); os.chmod(real, 0o700)
            (Path(home) / '.cache').symlink_to(real, target_is_directory=True)
            account = type('Account', (), {'pw_dir': home})()
            environment = {k: v for k, v in os.environ.items() if k != 'FASTAPI_TOOLS_STATE_HOME'}
            fallback = Path(home) / 'tmp'; fallback.mkdir()
            with patch.dict(os.environ, environment, clear=True), patch.object(runtime.pwd, 'getpwuid', return_value=account), \
                    patch.object(runtime.tempfile, 'gettempdir', return_value=str(fallback)), patch.object(runtime, 'STATE_NOTICE', []):
                self.assertEqual(runtime.state_base(), Path(home) / '.cache/fastapi-tools')
                self.assertTrue((Path(real) / 'fastapi-tools').is_dir())
                self.assertEqual(runtime.STATE_NOTICE, [])
                os.chmod(real, 0o777)
                self.assertEqual(runtime.state_base(), fallback / f'fastapi-tools-{os.getuid()}')
                self.assertIn('temporary fallback', runtime.STATE_NOTICE[0])
                os.chmod(real, 0o700)
        result = subprocess.run([sys.executable, str(RUNTIME)], input=json.dumps({'action': 'state-location'}), capture_output=True, text=True,
                                env={k: v for k, v in os.environ.items() if k != 'FASTAPI_TOOLS_STATE_HOME'} | {'HOME': '/nonexistent'})
        self.assertNotIn('stateDiagnostic', json.loads(result.stdout))  # HOME is not used; the passwd home is

if __name__=='__main__': unittest.main()
