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

class RuntimeTests(unittest.TestCase):
    def setUp(self):
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
        result=run_build(self.request(task='test',timeoutMs=100),own_process_group=True)
        self.assertTrue(result['timedOut']); self.assertFalse(result['ok'])
        (self.state/'delay').unlink(); (self.state/'noisy').write_text('')
        result=run_build(self.request(task='test',maxOutputBytes=100),own_process_group=True)
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
                run_build(self.request(task='test'), own_process_group=True)
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
                run_build(self.request(task='test'), own_process_group=True)
        self.assertIsNotNone(children[0].poll())

if __name__=='__main__': unittest.main()
