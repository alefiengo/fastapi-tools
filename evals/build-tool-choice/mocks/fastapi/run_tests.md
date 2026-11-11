---
error: true
---

{
  "name": null,
  "requiresPython": null,
  "dependencies": [
    "fastapi==0.115.6",
    "httpx==0.28.1",
    "pytest==8.3.4",
    "black==24.10.0"
  ],
  "isFastAPI": true,
  "checks": [
    "pytest"
  ],
  "root": "/workspace/orders-api",
  "buildTool": "python",
  "buildFile": "requirements.txt",
  "python": "/workspace/orders-api/.venv/bin/python",
  "environment": "/workspace/orders-api/.venv",
  "workspaceRoot": null,
  "modules": [],
  "discoveryScope": "Nearest Python project; dependencies are declarations, not resolved installations",
  "command": [
    "/workspace/orders-api/.venv/bin/python",
    "-m",
    "pytest",
    "--junitxml=.fastapi-tools/pytest.xml"
  ],
  "steps": [
    [
      "/workspace/orders-api/.venv/bin/python",
      "-m",
      "pytest",
      "--junitxml=.fastapi-tools/pytest.xml"
    ]
  ],
  "tasks": [
    "test"
  ],
  "profiles": [],
  "module": null,
  "testClass": null,
  "testPath": null,
  "hadPreviousAttempt": false,
  "changedSinceLastAttempt": false,
  "staleReportsIgnored": 0,
  "ok": false,
  "exitCode": 1,
  "stdout": "============================= test session starts ==============================\nplatform linux -- Python 3.12.15, pytest-8.3.4, pluggy-1.7.0\nrootdir: /workspace/orders-api\nconfigfile: pytest.ini\ntestpaths: tests\nplugins: anyio-4.16.0, platformdirs-4.14.5\ncollected 1 item\n\ntests/test_orders.py F                                                   [100%]\n\n=================================== FAILURES ===================================\n_______________________________ test_read_order ________________________________\ntests/test_orders.py:7: in test_read_order\n    with TestClient(app) as client:\n.venv/lib/python3.12/site-packages/starlette/testclient.py:739: in __enter__\n    portal.call(self.wait_startup)\n.venv/lib/python3.12/site-packages/anyio/from_thread.py:347: in call\n    return cast(T_Retval, self.start_task_soon(func, *args).result())\n/usr/local/lib/python3.12/concurrent/futures/_base.py:456: in result\n    return self.__get_result()\n/usr/local/lib/python3.12/concurrent/futures/_base.py:401: in __get_result\n    raise self._exception\n.venv/lib/python3.12/site-packages/anyio/from_thread.py:272: in _call_func\n    retval = await retval_or_awaitable\n.venv/lib/python3.12/site-packages/starlette/testclient.py:774: in wait_startup\n    await receive()\n.venv/lib/python3.12/site-packages/starlette/testclient.py:765: in receive\n    self.task.result()\n/usr/local/lib/python3.12/concurrent/futures/_base.py:449: in result\n    return self.__get_result()\n/usr/local/lib/python3.12/concurrent/futures/_base.py:401: in __get_result\n    raise self._exception\n.venv/lib/python3.12/site-packages/anyio/from_thread.py:272: in _call_func\n    retval = await retval_or_awaitable\n.venv/lib/python3.12/site-packages/starlette/testclient.py:755: in lifespan\n    await self.app(scope, self.stream_receive.receive, self.stream_send.send)\n.venv/lib/python3.12/site-packages/fastapi/applications.py:1054: in __call__\n    await super().__call__(scope, receive, send)\n.venv/lib/python3.12/site-packages/starlette/applications.py:113: in __call__\n    await self.middleware_stack(scope, receive, send)\n.venv/lib/python3.12/site-packages/starlette/middleware/errors.py:152: in __call__\n    await self.app(scope, receive, send)\n.venv/lib/python3.12/site-packages/starlette/middleware/exceptions.py:48: in __call__\n    await self.app(scope, receive, send)\n.venv/lib/python3.12/site-packages/starlette/routing.py:715: in __call__\n    await self.middleware_stack(scope, receive, send)\n.venv/lib/python3.12/site-packages/starlette/routing.py:724: in app\n    await self.lifespan(scope, receive, send)\n.venv/lib/python3.12/site-packages/starlette/routing.py:693: in lifespan\n    async with self.lifespan_context(app) as maybe_state:\n/usr/local/lib/python3.12/contextlib.py:210: in __aenter__\n    return await anext(self.gen)\napp/main.py:11: in lifespan\n    raise RuntimeError(\"DATABASE_URL is not set\")\nE   RuntimeError: DATABASE_URL is not set\n- generated xml file: /workspace/orders-api/.fastapi-tools/pytest.xml -\n=========================== short test summary info ============================\nFAILED tests/test_orders.py::test_read_order - RuntimeError: DATABASE_URL is ...\n============================== 1 failed in 0.35s ===============================\n",
  "stderr": "",
  "reused": false,
  "verificationIncomplete": false,
  "durationMs": 661,
  "fingerprint": "e7f5a3572175c708f8ee90d85d3d4dcbd55afebed74d6ffc49d7b081bcb5a975",
  "inputsChanged": false,
  "cacheable": true,
  "cacheDiagnostic": null,
  "timedOut": false,
  "outputLimitExceeded": false,
  "suites": [
    {
      "suite": "pytest",
      "tests": 1,
      "failures": 1,
      "errors": 0,
      "skipped": 0,
      "timeSec": 0.349
    }
  ],
  "failures": [
    {
      "test": "tests.test_orders.test_read_order",
      "message": "RuntimeError: DATABASE_URL is not set"
    }
  ],
  "reportErrors": []
}
