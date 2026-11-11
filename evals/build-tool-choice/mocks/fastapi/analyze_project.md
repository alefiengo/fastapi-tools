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
  "endpoints": {
    "endpoints": [
      {
        "method": "GET",
        "path": "/orders/{order_id}",
        "file": "app/main.py",
        "line": 20,
        "function": "read_order"
      }
    ],
    "count": 1,
    "unmounted": [],
    "warnings": [],
    "limitation": "Static top-level constructors, decorators and include_router calls only; factories, re-exports, mounts, conditional and computed registration need runtime OpenAPI."
  }
}
