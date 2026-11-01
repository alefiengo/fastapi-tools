# Matriz de capacidades (0.3.0)

| Componente | Claude Code | Adaptador Codex local | Evidencia o límite |
| --- | --- | --- | --- |
| Skills compartidas | `skills/` | mismo `skills/` | CLI leyó 16. Registro no prueba selección por modelo. |
| Agentes especialistas | `agents/` y permisos del host | sin registro | No hay equivalencia automática de subagentes ni de sus restricciones. |
| Hooks | cinco hooks en tres eventos | desactivados explícitamente | CLI `plugin/read` devolvió cero hooks. Sin guards ni Stop automático. |
| MCP stdio | `.mcp.json` con variables Claude | `codex/mcp.json`, wrapper y launcher | Protocolo real con CLI 0.166.0, sin instalación ni turnos de modelo. |
| Descubrimiento / AST | runtime Python compartido | mismo runtime vía MCP | Sin importar aplicación; raíz del cwd del MCP, incluyendo subdirectorios. |
| Checks finitos | hooks/MCP/runtime | MCP/runtime explícitos | `run_build task:verify`; mismos locks y políticas de ejecución. |
| Pytest y JUnit | MCP/runtime | mismo MCP/runtime | Requiere herramientas instaladas en la aplicación; el adaptador no las instala. |
| Alembic | lint estático / status explícito | igual vía MCP | Status ejecuta configuración; lint no consulta BD. |
| OpenAPI y salud | estático/HTTP explícito | igual vía MCP | FastAPI no crea health automáticamente; puerto por entorno, 8000 por defecto. |
| Inicialización | herramienta/skill compartida | catálogo MCP compartido, sin duplicación | `initialize_project`, con autorización explícita; runtime `action: initialize`. |
| Puerto de aplicación | `userConfig.app_port` | `FASTAPI_APP_PORT` | No se traduce el esquema de configuración de Claude. |
| LSP | `.lsp.json` según host | sin integración del plugin | No se importa configuración LSP de Claude. |
| Doctor offline | chequea registro Claude | chequea registro Codex y paths | No es herramienta MCP; no instala ni verifica autenticación. |
| Versiones del doctor | manifiestos/package/lock/servidor | exige concordancia con 0.3.0 | Node/Python por probes; Codex standalone por metadatos, sin arrancarlo. |
| Desktop / web alojada | no establecido aquí | no establecido aquí | Requiere ejecutor local. No se verificó publicación ni flujo de interfaz. |

Las pruebas deterministas cubren el adaptador y el doctor; el smoke opcional
comprueba lectura de empaquetado por la CLI y MCP registrado temporalmente.
No son evaluaciones de comportamiento del modelo. Un test separado
install-smoke verifica marketplace add, plugin add y plugin list en CODEX_HOME
temporal; no valida el arranque desde la caché instalada ni desktop.
El smoke local confirmó 16 skills/siete herramientas y los tests de release
exigen esas cantidades. El director confirmó 7/7 regresiones Node fuera del
sandbox del worker, que había recibido `EPERM`. El smoke CLI real pasó sin
instalación ni llamadas a modelos de pago.

La documentación oficial admite el
[overlay de compatibilidad y la sustitución explícita de hooks](https://developers.openai.com/plugins/build/plugins).
El adaptador desactiva los hooks existentes de Claude aunque otras superficies
Codex dispongan de lifecycle hooks: su formato y sus garantías no se presumen
intercambiables. Véase [uso, pruebas y límites de Codex](codex.md).
