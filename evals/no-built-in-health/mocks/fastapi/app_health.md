---
error: true
---

{
  "results": [
    {
      "probe": "health",
      "endpoint": "/health",
      "status": 404,
      "ok": false,
      "diagnosis": "Endpoint absent: check exposure, configured health or OpenAPI path and whether the relevant feature is configured."
    },
    {
      "probe": "readiness",
      "endpoint": "/health/ready",
      "status": 404,
      "ok": false,
      "diagnosis": "Endpoint absent: check exposure, configured health or OpenAPI path and whether the relevant feature is configured."
    },
    {
      "probe": "liveness",
      "endpoint": "/health/live",
      "status": 404,
      "ok": false,
      "diagnosis": "Endpoint absent: check exposure, configured health or OpenAPI path and whether the relevant feature is configured."
    }
  ],
  "limitation": "FastAPI has no built-in health routes. Only selected paths are fetched; configure them to match the application. No credentials are forwarded."
}
