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
    "/opt/fastapi-tools/runtime/source_inventory.py",
    "--syntax",
    "/workspace/orders-api"
  ],
  "steps": [
    [
      "/workspace/orders-api/.venv/bin/python",
      "/opt/fastapi-tools/runtime/source_inventory.py",
      "--syntax",
      "/workspace/orders-api"
    ]
  ],
  "tasks": [
    "compile"
  ],
  "profiles": [],
  "module": null,
  "testClass": null,
  "testPath": null,
  "hadPreviousAttempt": false,
  "changedSinceLastAttempt": false,
  "ok": true,
  "exitCode": 0,
  "stdout": "Python syntax check passed\n",
  "stderr": "",
  "reused": false,
  "verificationIncomplete": false,
  "durationMs": 92,
  "fingerprint": "e7f5a3572175c708f8ee90d85d3d4dcbd55afebed74d6ffc49d7b081bcb5a975",
  "inputsChanged": false,
  "cacheable": true,
  "cacheDiagnostic": null,
  "timedOut": false,
  "outputLimitExceeded": false
}
