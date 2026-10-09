#!/usr/bin/env python3
"""Exercise actual hook launchers with proposed Write/Edit payloads."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
ACTION=sys.argv.pop(1)
spec=importlib.util.spec_from_file_location('runtime_fixtures',ROOT/'tests/project-runtime/regressions.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)

class HookTests(unittest.TestCase):
    def setUp(self):
        self.fixture=tempfile.TemporaryDirectory();self.addCleanup(self.fixture.cleanup)
        self.root=Path(self.fixture.name)

    def invoke(self,file=None,content=None,**extra):
        args={}
        if file is not None: args['file_path']=str(file)
        if content is not None: args['content']=content
        args.update(extra.pop('tool_input',{}))
        result=subprocess.run(['bash',str(ROOT/'hooks/scripts'/f'{ACTION}.sh')],input=json.dumps({'tool_input':args,'cwd':str(self.root),**extra}),capture_output=True,text=True,cwd=self.root,env=dict(os.environ,CLAUDE_PROJECT_DIR=str(self.root)))
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout) if result.stdout else None

    def project(self,fastapi=True):
        (self.root/'pyproject.toml').write_text('[project]\nname="demo"\ndependencies='+ ('["fastapi"]' if fastapi else '[]')+'\n')
        python=self.root/'.venv/bin/python';python.parent.mkdir(parents=True)
        python.write_text(fixtures.FAKE_PYTHON);python.chmod(0o755)

    def deny(self,result):
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'],'deny')

    def test_diagnostics(self):
        helper=ROOT/'hooks/scripts/hook-runtime.py'
        result=subprocess.run([sys.executable,str(helper),ACTION],input='{broken',capture_output=True,text=True)
        self.assertIn('invalid JSON',json.loads(result.stdout)['systemMessage'])
        result=subprocess.run(['/bin/bash',str(ROOT/'hooks/scripts'/f'{ACTION}.sh')],input='{}',capture_output=True,text=True,env={'PATH':'/unavailable'})
        self.assertIn('Python 3 is required',json.loads(result.stdout)['systemMessage'])

    def test_secret_guard(self):
        if ACTION!='guard-secrets':self.skipTest('other hook')
        for content in ('DATABASE_URL=postgresql+asyncpg://app:literal@localhost/app','DB_PASSWORD=hunter2','api_key: literal-secret','password: ${DB_PASSWORD:unsafe}', 'secrets: {password: ${DB_PASSWORD}, token: literal}', '"password": "literal"'):
            self.deny(self.invoke(self.root/'.env',content))
        for content in ('DATABASE_URL=postgresql://app:${DB_PASSWORD}@localhost/app','PASSWORD=${DB_PASSWORD}','PASSWORD=dummy','# PASSWORD=real','password: ${DB_PASSWORD:${FALLBACK}}','token_url: https://issuer/token'):
            self.assertIsNone(self.invoke(self.root/'.env',content))
        for content in ('JWT_SECRET="literal"','DB_PASSWORD: str = "literal"','DATABASE_URL="postgresql+psycopg://app:literal@db/app"','DB_PASSWORD=os.getenv("DB_PASSWORD", "literal")'):
            self.deny(self.invoke(self.root/'settings.py',content))
        self.assertIsNone(self.invoke(self.root/'settings.py','DB_PASSWORD=os.environ["DB_PASSWORD"]'))
        self.assertIsNone(self.invoke(self.root/'settings.py','DB_PASSWORD=os.getenv("DB_PASSWORD")'))
        path=self.root/'settings.py';path.write_text('DB_PASSWORD=os.getenv("DB_PASSWORD")\n')
        self.deny(self.invoke(path,tool_input={'old_string':'os.getenv("DB_PASSWORD")','new_string':'"literal"'}))

    def test_schema_guard(self):
        if ACTION!='guard-ddl':self.skipTest('other hook')
        self.deny(self.invoke(self.root/'main.py','Base.metadata.drop_all(engine)'))
        self.deny(self.invoke(self.root/'main.py','async def startup():\n    await conn.run_sync(Base.metadata.drop_all)'))
        self.assertIsNone(self.invoke(self.root/'main.py','Base.metadata.create_all(engine)'))
        self.assertIsNone(self.invoke(self.root/'db_local.py','Base.metadata.drop_all(engine)'))
        self.assertIsNone(self.invoke(self.root/'tests/conftest.py','Base.metadata.drop_all(engine)'))
        self.assertIsNone(self.invoke(self.root/'main.py','# Base.metadata.drop_all(engine)'))

    def test_revision_lint(self):
        if ACTION!='lint-migration':self.skipTest('other hook')
        self.project();path=self.root/'alembic/versions/x.py';path.parent.mkdir(parents=True)
        path.write_text('revision=None\ndown_revision=None\ndef upgrade(): pass\n')
        self.assertIn('revision',self.invoke(path)['hookSpecificOutput']['additionalContext'])
        path.write_text('revision="x"\ndown_revision=None\ndef upgrade():\n    op.drop_table("orders")\n')
        self.assertIn('data loss',self.invoke(path)['hookSpecificOutput']['additionalContext'])
        path.write_text('revision="x"\ndown_revision=None\ndef upgrade(): pass\ndef downgrade():\n    op.drop_table("orders")\n')
        self.assertIsNone(self.invoke(path))

    def test_batch_edits(self):
        if ACTION!='post-edit-compile':self.skipTest('other hook')
        self.project();path=self.root/'main.py';path.write_text('value=1\n')
        self.assertIsNone(self.invoke(path))
        self.assertFalse((self.root/'.fastapi-tools/calls').exists())
        sys.path.insert(0,str(ROOT/'runtime'));from project_runtime import state_dir
        self.assertTrue((state_dir(self.root)/'pending.json').exists())

    def test_stop_gate_failure_reuse_and_recursion(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        self.project();self.assertIsNone(self.invoke())
        calls=self.root/'.fastapi-tools/calls';initial=calls.read_text()
        self.assertIsNone(self.invoke());self.assertEqual(initial,calls.read_text())
        (self.root/'main.py').write_text('value=2')
        (self.root/'.fastapi-tools/fail').write_text('')
        result=self.invoke();self.assertEqual(result['decision'],'block');self.assertIn('controlled failure',result['reason'])
        self.assertIsNone(self.invoke(stop_hook_active=True))

    def test_unrelated_python_project_skipped(self):
        if ACTION not in ('verify-on-stop','post-edit-compile'):self.skipTest('other hook')
        self.project(fastapi=False)
        path=self.root/'main.py';path.write_text('value=1')
        self.assertIsNone(self.invoke(path));self.assertFalse((self.root/'.fastapi-tools/calls').exists())

if __name__=='__main__':unittest.main()
