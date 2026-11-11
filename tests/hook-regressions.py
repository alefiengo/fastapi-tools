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
        self.state_home=fixtures.isolate_state(self)
        self.fixture=tempfile.TemporaryDirectory();self.addCleanup(self.fixture.cleanup)
        self.root=Path(self.fixture.name).resolve()

    def invoke(self,file=None,content=None,action=None,project=None,env=None,**extra):
        args={}
        if file is not None: args['file_path']=str(file)
        if content is not None: args['content']=content
        args.update(extra.pop('tool_input',{}))
        project=project or self.root
        payload={'tool_input':args,'cwd':str(project),**extra}
        result=subprocess.run(['bash',str(ROOT/'hooks/scripts'/f'{action or ACTION}.sh')],input=json.dumps(payload),capture_output=True,text=True,cwd=project,env=dict(os.environ,CLAUDE_PROJECT_DIR=str(project),**(env or {})))
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout) if result.stdout else None

    def project(self,fastapi=True,root=None):
        root=root or self.root
        (root/'pyproject.toml').write_text('[project]\nname="demo"\ndependencies='+ ('["fastapi","pytest"]' if fastapi else '[]')+'\n')
        python=root/'.venv/bin/python';python.parent.mkdir(parents=True)
        python.write_text(fixtures.FAKE_PYTHON);python.chmod(0o755)

    def calls(self,root=None):
        file=(root or self.root)/'.fastapi-tools/calls'
        return file.read_text().splitlines() if file.exists() else []

    def edited(self,path):
        # A real edit goes through PostToolUse, which records the edit hint.
        self.assertIsNone(self.invoke(path,'x',action='post-edit-compile'))

    def decision(self,result):
        return result['hookSpecificOutput']['permissionDecision'] if result else None

    def deny(self,result):
        self.assertEqual(self.decision(result),'deny')

    def test_diagnostics(self):
        helper=ROOT/'hooks/scripts/hook-runtime.py'
        result=subprocess.run([sys.executable,str(helper),ACTION],input='{broken',capture_output=True,text=True)
        self.assertIn('invalid JSON',json.loads(result.stdout)['systemMessage'])
        result=subprocess.run(['/bin/bash',str(ROOT/'hooks/scripts'/f'{ACTION}.sh')],input='{}',capture_output=True,text=True,env={'PATH':'/unavailable'})
        self.assertIn('Python 3.11+ is required',json.loads(result.stdout)['systemMessage'])

    def test_launcher_selects_python_311_and_isolates_plugin_imports(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        bin=self.root/'bin';bin.mkdir()
        (bin/'python3').write_text('#!/bin/sh\nexit 1\n');(bin/'python3').chmod(0o755)  # like an old venv python3
        (bin/'python3.11').symlink_to(sys.executable)
        planted=self.root/'planted';planted.mkdir()
        (planted/'tomllib.py').write_text(f'open({str(self.root/"PLANTED")!r},"w").close()\nraise ImportError("planted")\n')
        app=self.root/'app';app.mkdir();self.project(root=app)
        (app/'.venv/bin/python').write_text(fixtures.FAKE_PYTHON.replace("print('controlled check passed')",
            "import os\n(state / 'pythonpath').write_text(os.environ.get('PYTHONPATH', ''))\nprint('controlled check passed')"))
        env={'PATH':f'{bin}:/usr/bin:/bin','PYTHONPATH':str(planted)}
        self.assertIsNone(self.invoke(project=app,env=env))
        self.assertTrue(self.calls(app))
        self.assertFalse((self.root/'PLANTED').exists())
        self.assertEqual((app/'.fastapi-tools/pythonpath').read_text(),str(planted))  # checks keep the environment
        result=self.invoke(project=app,env={'FASTAPI_TOOLS_PYTHON':str(bin/'python3')})
        self.assertIn('FASTAPI_TOOLS_PYTHON',result['systemMessage'])

    def test_secret_guard(self):
        if ACTION!='guard-secrets':self.skipTest('other hook')
        (self.root/'pyproject.toml').write_text('[project]\nname="demo"\n')
        for content in ('DATABASE_URL=postgresql+asyncpg://app:literal@localhost/app','DB_PASSWORD=hunter2','api_key: literal-secret','password: ${DB_PASSWORD:unsafe}', 'secrets: {password: ${DB_PASSWORD}, token: literal}', '"password": "literal"','SECRET_KEY=b3f1c9a2e8d74f5a'):
            self.assertEqual(self.decision(self.invoke(self.root/'.env',content)),'ask',content)
        for content in ('DATABASE_URL=postgresql://app:${DB_PASSWORD}@localhost/app','PASSWORD=${DB_PASSWORD}','PASSWORD=dummy','# PASSWORD=real','password: ${DB_PASSWORD:${FALLBACK}}','token_url: https://issuer/token','POSTGRES_PASSWORD=changethis'):
            self.assertIsNone(self.invoke(self.root/'.env',content),content)
        for content in ('JWT_SECRET="literal"','DB_PASSWORD: str = "literal"','DATABASE_URL="postgresql+psycopg://app:literal@db/app"','DB_PASSWORD=os.getenv("DB_PASSWORD", "literal")'):
            self.deny(self.invoke(self.root/'settings.py',content))
        self.assertIsNone(self.invoke(self.root/'settings.py','DB_PASSWORD=os.environ["DB_PASSWORD"]'))
        self.assertIsNone(self.invoke(self.root/'settings.py','DB_PASSWORD=os.getenv("DB_PASSWORD")'))
        path=self.root/'settings.py';path.write_text('DB_PASSWORD=os.getenv("DB_PASSWORD")\n')
        self.deny(self.invoke(path,tool_input={'old_string':'os.getenv("DB_PASSWORD")','new_string':'"literal"'}))

    def test_secret_guard_covers_fastapi_secrets_and_official_placeholders(self):
        if ACTION!='guard-secrets':self.skipTest('other hook')
        (self.root/'pyproject.toml').write_text('[project]\nname="demo"\n')
        for name,content in (('app/core/config.py','SECRET_KEY = "b3f1c9a2e8d74f5a9c0e1d2f"'),
                             ('app/main.py','SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"'),
                             ('app/core/security.py','JWT_SECRET = "literal-value"'),
                             ('app/core/config.py','secret_key: SecretStr = SecretStr("literal-value")'),
                             ('config.yaml','aws_secret_access_key: wJalrXUtnFEMI'),
                             ('config.yaml','url: mongodb://app:hunter2@db:27017/app'),
                             ('config.toml','broker = "amqp://app:hunter2@mq:5672//"'),
                             ('app/settings.py','x='+'('*300+'1'+')'*300+'\nDB_PASSWORD="literal"')):
            with self.subTest(name=name,content=content[:40]):
                self.deny(self.invoke(self.root/name,content))
        for name,content in (('compose.yml','      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:?Variable not set}'),
                             ('compose.yml','      SMTP_PASSWORD: ${SMTP_PASSWORD:-}'),
                             ('compose.yml','      POSTGRES_PASSWORD: $POSTGRES_PASSWORD'),
                             ('compose.yml','      DATABASE_URL: postgresql://postgres:${POSTGRES_PASSWORD:?Variable not set}@db:5432/app'),
                             ('openapi.json','{"properties": {"token": null}}'),
                             ('app/config.py','token_url = "https://issuer/token"')):
            with self.subTest(name=name,content=content[:40]):
                self.assertIsNone(self.invoke(self.root/name,content))
        for name in ('tests/fixtures/users.json','tests/test_settings.py','.env.test','.env.example'):
            content='{"password": "test-password"}' if name.endswith('.json') else ('password = "test-password"' if name.endswith('.py') else 'DB_PASSWORD=test')
            self.assertEqual(self.decision(self.invoke(self.root/name,content)),'ask',name)
        existing=self.root/'app/settings.py';existing.parent.mkdir(exist_ok=True);existing.write_text('DB_PASSWORD = "legacy"\nDEBUG = False\n')
        self.assertIsNone(self.invoke(existing,tool_input={'old_string':'DEBUG = False','new_string':'DEBUG = True'}))
        result=self.invoke(self.root/'.env','PASSWORD='+'${A:'*2000+'x'+'}'*2000)
        self.assertEqual(self.decision(result),'ask')  # deep nesting is a literal, without a traceback

    def test_edit_fifo_does_not_block_secret_guard(self):
        if ACTION!='guard-secrets':self.skipTest('other hook')
        path=self.root/'settings.py'
        os.mkfifo(path)
        self.deny(self.invoke(path,tool_input={'old_string':'old','new_string':'JWT_SECRET="literal"'}))

    def test_schema_guard(self):
        if ACTION!='guard-ddl':self.skipTest('other hook')
        self.deny(self.invoke(self.root/'main.py','Base.metadata.drop_all(engine)'))
        self.deny(self.invoke(self.root/'main.py','async def startup():\n    await conn.run_sync(Base.metadata.drop_all)'))
        self.assertIsNone(self.invoke(self.root/'main.py','Base.metadata.create_all(engine)'))
        self.assertIsNone(self.invoke(self.root/'db_local.py','Base.metadata.drop_all(engine)'))
        self.assertIsNone(self.invoke(self.root/'tests/conftest.py','Base.metadata.drop_all(engine)'))
        self.assertIsNone(self.invoke(self.root/'main.py','# Base.metadata.drop_all(engine)'))

    def test_schema_guard_uses_project_relative_test_paths(self):
        if ACTION!='guard-ddl':self.skipTest('other hook')
        project=self.root/'tests'/'service';project.mkdir(parents=True)
        (project/'pyproject.toml').write_text('[project]\nname="svc"\n')
        self.deny(self.invoke(project/'app/main.py','Base.metadata.drop_all(engine)',project=project))
        for name in ('conftest.py','test/test_db.py','app/test_models.py'):
            self.assertIsNone(self.invoke(project/name,'Base.metadata.drop_all(engine)',project=project),name)
        existing=project/'app/reset.py';existing.parent.mkdir(exist_ok=True);existing.write_text('Base.metadata.drop_all(engine)\nVALUE = 1\n')
        self.assertIsNone(self.invoke(existing,tool_input={'old_string':'VALUE = 1','new_string':'VALUE = 2'},project=project))
        self.deny(self.invoke(project/'app/main.py','x='+'['*300+']'*300+'\nBase.metadata.drop_all(engine)',project=project))

    def test_revision_lint(self):
        if ACTION!='lint-migration':self.skipTest('other hook')
        self.project();path=self.root/'alembic/versions/x.py';path.parent.mkdir(parents=True)
        path.write_text('revision=None\ndown_revision=None\ndef upgrade(): pass\n')
        self.assertIn('revision',self.invoke(path)['hookSpecificOutput']['additionalContext'])
        path.write_text('revision="x"\ndown_revision=None\ndef upgrade():\n    op.drop_table("orders")\n')
        self.assertIn('data loss',self.invoke(path)['hookSpecificOutput']['additionalContext'])
        path.write_text('revision="x"\ndown_revision=None\ndef upgrade(): pass\ndef downgrade():\n    op.drop_table("orders")\n')
        self.assertIsNone(self.invoke(path))
        path.write_text('import sqlalchemy as sa\nrevision="x"\ndown_revision=None\ndef upgrade():\n    op.execute(sa.text("DROP TABLE users"))\n')
        self.assertIn('destructive SQL',self.invoke(path)['hookSpecificOutput']['additionalContext'])

    def test_api_versions_package_is_not_linted_as_alembic(self):
        if ACTION!='lint-migration':self.skipTest('other hook')
        self.project()
        for name in ('a','b'):
            path=self.root/f'alembic/versions/{name}.py';path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(f'revision="{name}"\ndown_revision=None\ndef upgrade(): pass\n')
        router=self.root/'app/api/versions/v1.py';router.parent.mkdir(parents=True);router.write_text('router = None\n')
        self.assertIsNone(self.invoke(router))
        self.assertIn('Multiple heads',self.invoke(self.root/'alembic/versions/a.py')['hookSpecificOutput']['additionalContext'])

    def test_batch_edits(self):
        if ACTION!='post-edit-compile':self.skipTest('other hook')
        self.project();path=self.root/'main.py';path.write_text('value=1\n')
        self.assertIsNone(self.invoke(path))
        self.assertFalse((self.root/'.fastapi-tools/calls').exists())
        sys.path.insert(0,str(ROOT/'runtime'));from project_runtime import state_dir
        hint=json.loads((state_dir(self.root)/'pending.json').read_text())
        self.assertEqual(hint['root'],str(self.root))

    def test_stop_gate_failure_reuse_and_recursion(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        self.project();self.assertIsNone(self.invoke())
        initial=self.calls()
        self.assertIsNone(self.invoke());self.assertEqual(initial,self.calls())
        (self.root/'main.py').write_text('value=2')
        (self.root/'.fastapi-tools/fail').write_text('')
        result=self.invoke();self.assertEqual(result['decision'],'block');self.assertIn('controlled failure',result['reason'])
        # The continuation is still checked, but reported instead of blocked again.
        result=self.invoke(stop_hook_active=True)
        self.assertNotIn('decision',result);self.assertIn('already failed',result['systemMessage'])

    def test_stop_hook_active_still_verifies_the_fix_attempt(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        self.project();source=self.root/'main.py';source.write_text('def broken(:\n');self.edited(source)
        self.assertEqual(self.invoke()['decision'],'block')
        source.write_text('def still_broken(:\n');self.edited(source)
        result=self.invoke(stop_hook_active=True)
        self.assertNotIn('decision',result);self.assertIn('SyntaxError',result['systemMessage'])
        source.write_text('value=1\n');self.edited(source)
        self.assertIsNone(self.invoke(stop_hook_active=True))

    def test_preexisting_failure_without_edits_is_reported_not_rerun(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        self.project();(self.root/'.fastapi-tools').mkdir();(self.root/'.fastapi-tools/fail').write_text('')
        first=self.invoke();self.assertNotIn('decision',first);self.assertIn('controlled failure',first['systemMessage'])
        calls=len(self.calls())
        again=self.invoke();self.assertNotIn('decision',again);self.assertIn('already failed',again['systemMessage'])
        self.assertEqual(len(self.calls()),calls)

    def test_nested_project_with_edit_hint_is_verified(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        (self.root/'README.md').write_text('# monorepo\n')
        service=self.root/'services/api';service.mkdir(parents=True);self.project(root=service)
        source=service/'main.py';source.write_text('def broken(:\n');self.edited(source)
        result=self.invoke();self.assertEqual(result['decision'],'block')
        self.assertIn('SyntaxError',result['reason']);self.assertIn(str(service),result['reason'])

    def test_worktree_session_checks_its_worktree_only(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        self.project();(self.root/'main.py').write_text('value=1\n')
        worktree=self.root/'.claude/worktrees/feat';worktree.mkdir(parents=True);self.project(root=worktree)
        source=worktree/'main.py';source.write_text('def broken(:\n')
        self.assertIsNone(self.invoke(source,'x',action='post-edit-compile',cwd=str(worktree)))
        self.assertIsNone(self.invoke())  # main session: other worktrees are neither inputs nor hints
        result=self.invoke(cwd=str(worktree))
        self.assertEqual(result['decision'],'block');self.assertIn(str(worktree),result['reason'])

    def test_untrusted_shared_ancestor_is_never_executed(self):
        if ACTION not in ('verify-on-stop','post-edit-compile'):self.skipTest('other hook')
        shared=self.root/'shared';shared.mkdir();self.project(root=shared)
        marker=self.root/'EXECUTED'
        (shared/'.venv/bin/python').write_text(f'#!/bin/sh\ntouch {marker}\n')
        os.chmod(shared,0o1777);self.addCleanup(os.chmod,shared,0o700)
        workspace=shared/'workspace';workspace.mkdir();(workspace/'main.py').write_text('value=1\n')
        result=self.invoke(workspace/'main.py','x',project=workspace)
        self.assertIn('writable by other users',result['systemMessage'])
        self.assertFalse(marker.exists())

    def test_unrelated_python_project_skipped(self):
        if ACTION not in ('verify-on-stop','post-edit-compile'):self.skipTest('other hook')
        self.project(fastapi=False)
        path=self.root/'main.py';path.write_text('value=1')
        self.assertIsNone(self.invoke(path));self.assertFalse((self.root/'.fastapi-tools/calls').exists())
        self.assertEqual(list(self.state_home.glob('build-*/pending.json')),[])

    def test_stop_does_not_impose_pytest_or_optional_checks(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        self.project()
        (self.root/'pyproject.toml').write_text('[project]\nname="api"\ndependencies=["fastapi"]\n')
        self.assertIsNone(self.invoke())
        calls=self.calls()
        self.assertEqual(len(calls),1)
        self.assertIn('--syntax',calls[0])

    def test_stop_blocks_when_verification_cannot_complete(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        self.project();self.edited(self.root/'pyproject.toml')
        external=self.root/'external';external.mkdir()
        (self.root/'.fastapi-tools').symlink_to(external,target_is_directory=True)
        result=self.invoke()
        self.assertEqual(result['decision'],'block')
        self.assertIn('Unsafe test report',result['reason'])
        self.assertEqual(list(external.iterdir()),[])

    def test_stop_detects_inputs_changed_without_post_edit_hint(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        self.project();self.assertIsNone(self.invoke())
        (self.root/'main.py').write_text('def invalid(:')
        result=self.invoke()
        self.assertEqual(result['decision'],'block')
        self.assertIn('SyntaxError',result['reason'])

    def test_stop_blocks_fastapi_metadata_errors_without_hijacking_generic_python(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        self.project()
        (self.root/'pyproject.toml').write_text('[project\n')
        (self.root/'main.py').write_text('from fastapi import FastAPI\napp=FastAPI()\n')
        result=self.invoke()
        self.assertEqual(result['decision'],'block')
        self.assertIn('could not discover',result['reason'])
        (self.root/'main.py').write_text('value=1\n')
        self.assertNotIn('decision',self.invoke())

    def test_stop_blocks_uninspectable_final_inputs(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        self.project();self.edited(self.root/'pyproject.toml')
        (self.root/'linked.py').symlink_to(ROOT/'runtime/project_runtime.py')
        result=self.invoke()
        self.assertEqual(result['decision'],'block')
        self.assertIn('could not be fully inspected',result['reason'])

    # --- Independent review regressions (RV-1, RV-2, RV-8, RV-9) ------------

    def test_edit_hint_blocks_even_after_a_remembered_failure(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        self.project();source=self.root/'main.py';source.write_text('def broken(:\n')
        self.assertIsNone(self.invoke(source,'x',action='post-edit-compile',session_id='author'))
        verified=subprocess.run([sys.executable,str(fixtures.RUNTIME)],input=json.dumps({'action':'run','task':'verify','projectRoot':str(self.root),'skipUnchangedFailure':True}),capture_output=True,text=True)
        self.assertFalse(json.loads(verified.stdout)['ok'])  # e.g. the MCP run_build verify Claude ran first
        result=self.invoke(session_id='author')
        self.assertEqual(result['decision'],'block');self.assertIn('SyntaxError',result['reason'])

    def test_sessions_only_consume_their_own_edit_hints(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        self.project();source=self.root/'main.py';source.write_text('def broken(:\n')
        self.assertIsNone(self.invoke(source,'x',action='post-edit-compile',session_id='author'))
        other=self.invoke(session_id='observer')
        self.assertNotIn('decision',other)  # it did not edit: report, never block it
        author=self.invoke(session_id='author')
        self.assertEqual(author['decision'],'block')

    def test_cwd_outside_the_project_does_not_widen_the_scope(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        project=self.root/'project';project.mkdir();self.project(root=project);(project/'main.py').write_text('value=1\n')
        elsewhere=self.root/'elsewhere/api';elsewhere.mkdir(parents=True);self.project(root=elsewhere)
        source=elsewhere/'main.py';source.write_text('def broken(:\n')
        self.assertIsNone(self.invoke(source,'x',action='post-edit-compile',project=elsewhere,session_id='s'))
        self.assertIsNone(self.invoke(project=project,cwd=str(self.root/'elsewhere'),session_id='s'))
        self.assertEqual(self.calls(elsewhere),[])

    def test_launcher_and_supervisor_skip_site_and_pth_files(self):
        if ACTION!='verify-on-stop':self.skipTest('other hook')
        environment=self.root/'runtime-env'
        subprocess.run([sys.executable,'-m','venv','--without-pip',str(environment)],check=True)
        site=next(environment.glob('lib/python3*/site-packages'))
        marker=self.root/'PTH_EXECUTED'
        (site/'planted.pth').write_text(f'import os; open({str(marker)!r}, "w").close()\n')
        app=self.root/'app';app.mkdir();self.project(root=app)
        # The fake application interpreter ignores PYTHONPATH itself (-I), so a
        # shadowed pathlib can only break plugin code started without -I.
        python=app/'.venv/bin/python';python.write_text(fixtures.FAKE_PYTHON.replace(f'#!{sys.executable}',f'#!{sys.executable} -I',1))
        planted=self.root/'shadow';planted.mkdir();(planted/'pathlib.py').write_text('raise ImportError("shadowed")\n')
        result=self.invoke(project=app,env={'PATH':f'{environment}/bin:'+os.environ['PATH'],'PYTHONPATH':str(planted)})
        self.assertIsNone(result)
        self.assertTrue(self.calls(app))
        self.assertFalse(marker.exists())

    def test_guards_exempt_only_real_test_locations(self):
        if ACTION not in ('guard-ddl','guard-secrets'):self.skipTest('other hook')
        (self.root/'pyproject.toml').write_text('[project]\nname="demo"\n[tool.pytest.ini_options]\ntestpaths=["qa"]\n')
        if ACTION=='guard-ddl':
            for name in ('app/fixtures/db.py','app/testing/reset.py','app/tests/reset.py'):
                self.deny(self.invoke(self.root/name,'Base.metadata.drop_all(engine)'))
            for name in ('qa/helpers.py','tests/fixtures/db.py','test/db.py','app/test_db.py','app/db_test.py','app/conftest.py'):
                self.assertIsNone(self.invoke(self.root/name,'Base.metadata.drop_all(engine)'),name)
        else:
            self.deny(self.invoke(self.root/'app/fixtures/settings.py','SECRET_KEY = "literal-value"'))
            self.assertEqual(self.decision(self.invoke(self.root/'qa/settings.py','SECRET_KEY = "literal-value"')),'ask')

if __name__=='__main__':unittest.main()
