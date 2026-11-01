#!/usr/bin/env python3
"""Real environment/tool integration; preparation is explicit and checks offline.

Uses installed dependencies through a private fixture environment, never touches
an application's environment. Run after installing requirements.txt separately.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
RUNTIME = REPO / 'runtime/project_runtime.py'
HOOK = REPO / 'hooks/scripts/verify-on-stop.sh'
sys.path.insert(0, str(RUNTIME.parent))
import project_runtime as runtime


class Ecosystem(unittest.TestCase):
    manager = 'python'

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='fastapi-real-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.env = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH'],
                        PIP_NO_INDEX='1', UV_OFFLINE='1', UV_NO_SYNC='1',
                        POETRY_VIRTUALENVS_CREATE='false', POETRY_NO_INTERACTION='1')
        self.env.pop('VIRTUAL_ENV', None)
        self.env.pop('PROJECT_ROOT', None)
        self.env.pop('CLAUDE_PROJECT_DIR', None)
        # An actual venv interpreter, with the already prepared test dependency
        # directory exposed explicitly. No installation happens in this fixture.
        self.command([sys.executable, '-m', 'venv', '--without-pip', str(self.root / '.venv')])
        sites = subprocess.check_output([sys.executable, '-c', 'import site,json; print(json.dumps(site.getsitepackages()))'], text=True)
        self.env['PYTHONPATH'] = os.pathsep.join(json.loads(sites))
        self.write('pyproject.toml', '''[project]
name = "fastapi-real-fixture"
version = "0.0.0"
requires-python = ">=3.11"
dependencies = []
[tool.ruff]
line-length = 120
[tool.ruff.lint]
select = ["E4", "E7", "E9", "F"]
[tool.mypy]
files = ["app.py", "test_app.py"]
check_untyped_defs = true
[tool.pytest.ini_options]
testpaths = ["test_app.py"]
''')
        self.source = '''from fastapi import FastAPI
app = FastAPI()
@app.get("/hello")
def hello() -> dict[str, str]:
    return {"message": "hello"}
'''
        self.test = '''from fastapi.testclient import TestClient
from app import app
def test_hello() -> None:
    with TestClient(app) as client:
        assert client.get("/hello").json() == {"message": "hello"}
'''
        self.write('app.py', self.source)
        self.write('test_app.py', self.test)
        if self.manager == 'uv':
            self.command(['uv', 'lock', '--offline'])
        elif self.manager == 'poetry':
            self.command(['poetry', 'lock'])
        state = Path(tempfile.gettempdir()) / ('fastapi-tools-build-' + str(os.getuid()) + '-' + hashlib.sha256(str(self.root.resolve()).encode()).hexdigest())
        self.addCleanup(lambda: shutil.rmtree(state, ignore_errors=True))

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def command(self, args):
        result = subprocess.run(args, cwd=self.root, env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def invoke(self, **options):
        request = {'action': 'run', 'projectRoot': str(self.root), 'task': 'verify', **options}
        result = subprocess.run(
            [sys.executable, str(RUNTIME)], input=json.dumps(request), cwd=self.root,
            env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def stop(self):
        result = subprocess.run(['bash', str(HOOK)], input=json.dumps({'cwd': str(self.root)}),
                                env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def test_lifecycle(self):
        self.assertEqual(runtime.discover(self.root)['buildTool'], self.manager)
        initial = self.invoke()
        self.assertTrue(initial['ok'], initial)
        self.assertFalse(initial['reused'])
        self.assertIn('All checks passed', initial['stdout'])
        self.assertIn('Success: no issues found', initial['stdout'])
        self.assertIn('1 passed', initial['stdout'])
        self.assertTrue(self.invoke()['reused'])
        self.assertIsNone(self.stop())
        self.write('test_app.py', self.test.replace('"hello"}', '"wrong"}'))
        failed = self.invoke(task='test', collectTestReports=True)
        self.assertFalse(failed['ok'])
        self.assertIn('AssertionError', failed['stdout'])
        self.assertIn('<failure', failed['testReports'][0]['content'])
        self.command(['node', str(REPO / 'tests/python-ecosystem/mcp-report.mjs')])
        self.assertEqual(self.stop()['decision'], 'block')
        self.write('test_app.py', self.test)
        self.assertFalse(self.invoke()['reused'])
        self.write('app.py', self.source + '\nimport os\n')
        self.assertFalse(self.invoke()['ok'])  # Real Ruff F401.
        self.write('app.py', self.source + '\nvalue: int = "wrong"\n')
        mismatch = self.invoke()
        self.assertFalse(mismatch['ok'])
        self.assertIn('Incompatible types', mismatch['stdout'])
        self.write('app.py', self.source + '\ndef broken(:\n')
        self.assertEqual(self.stop()['decision'], 'block')
        self.write('app.py', self.source)
        self.assertTrue(self.invoke()['ok'])
        self.assertIsNone(self.stop())
        # Current queries a real SQLite history without applying migrations.
        self.write('alembic.ini', '[alembic]\nscript_location = db\nsqlalchemy.url = sqlite:///fixture.db\n')
        self.write('db/env.py', '''from alembic import context
from sqlalchemy import create_engine
with create_engine(context.config.get_main_option("sqlalchemy.url")).connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
''')
        self.write('db/versions/base.py', 'revision = "base"\ndown_revision = None\ndef upgrade():\n    pass\n')
        status = self.invoke(task='migration-status')
        self.assertTrue(status['ok'], status)
        self.assertEqual(status['command'][-1], 'current')
        self.assertEqual(runtime.migration_inventory(self.root)['heads'], ['base'])
        # A real long pytest subprocess is bounded and invalidates success.
        self.write('test_app.py', 'import time\ndef test_slow():\n    time.sleep(30)\n')
        slow = self.invoke(task='test', timeoutMs=1500)
        self.assertTrue(slow['timedOut'], slow)
        self.write('test_app.py', self.test)
        self.assertFalse(self.invoke()['reused'])


class GeneratedProject(unittest.TestCase):
    def test_generated_application_runs_without_installing_it(self):
        from project_initializer import initialize_project
        with tempfile.TemporaryDirectory(prefix='fastapi-generated-real-') as base:
            destination = Path(base) / 'new-api'
            generated = initialize_project({'destination': str(destination), 'projectName': 'new-api', 'explicitRequest': True})
            self.assertFalse(generated['dependenciesInstalled'])
            self.assertFalse(generated['codeExecuted'])
            request = {'action': 'run', 'projectRoot': str(destination), 'task': 'verify'}
            result = subprocess.run([sys.executable, str(RUNTIME)], cwd=destination,
                                    input=json.dumps(request), capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            verified = json.loads(result.stdout)
            self.assertTrue(verified['ok'], verified)
            self.assertIn('1 passed', verified['stdout'])
            state = Path(tempfile.gettempdir()) / ('fastapi-tools-build-' + str(os.getuid()) + '-' + hashlib.sha256(str(destination).encode()).hexdigest())
            shutil.rmtree(state, ignore_errors=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--managers', nargs='+', choices=['python', 'uv', 'poetry'], default=['python', 'uv', 'poetry'])
    args = parser.parse_args()
    print(json.dumps({'python': sys.version.split()[0], **{name: importlib.metadata.version(name) for name in
          ('fastapi', 'pydantic', 'pytest', 'ruff', 'mypy', 'alembic', 'poetry')}}), flush=True)
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(GeneratedProject))
    for manager in args.managers:
        case = type('Real_' + manager, (Ecosystem,), {'manager': manager})
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
