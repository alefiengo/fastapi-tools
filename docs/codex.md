# Codex: adaptador local y diagnóstico offline (0.3.0)

El plugin 0.3.0 publica `.codex-plugin/plugin.json`, reutiliza `skills/` y referencia
`codex/mcp.json`. El formato de compatibilidad sigue documentado por OpenAI.
La configuración raíz `.mcp.json` pertenece a Claude Code: sus variables de
proyecto y `user_config` no deben trasladarse a Codex.

## Uso local

Se necesitan Linux/macOS, Node >=20.3, Python >=3.11 y las dependencias bloqueadas
de `mcp-server/` preparadas previamente. El adaptador no instala dependencias.
Los checks de la aplicación necesitan su propio entorno Python y herramientas;
la selección de uv, Poetry o `.venv` pertenece exclusivamente al runtime.

Preparar las dependencias bloqueadas del servidor antes de instalar el plugin:

```bash
npm ci --omit=dev --prefix /ruta/absoluta/fastapi-tools/mcp-server
```

Crear un marketplace local fuera del checkout y de la aplicación. Los comandos
siguientes son una receta de instalación. El doctor no los ejecuta; el test
opcional install-smoke los verifica exclusivamente con CODEX_HOME temporal. Sustituir las rutas de ejemplo y mantener disponible el checkout:

```bash
mkdir -p /ruta/absoluta/fastapi-local/.agents/plugins
ln -s /ruta/absoluta/fastapi-tools /ruta/absoluta/fastapi-local/fastapi-tools
```

Guardar este catálogo en
`/ruta/absoluta/fastapi-local/.agents/plugins/marketplace.json`:

```json
{
  "name": "fastapi-local",
  "interface": { "displayName": "FastAPI local" },
  "plugins": [
    {
      "name": "fastapi-tools",
      "source": { "source": "local", "path": "./fastapi-tools" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_USE" }
    }
  ]
}
```

Registrar el marketplace e instalar el plugin (estos comandos escriben el
registro/cache local de Codex y son acciones explícitas del usuario):

```bash
codex plugin marketplace add /ruta/absoluta/fastapi-local
codex plugin add fastapi-tools@fastapi-local
```

La CLI 0.166.0 confirmó la receta y la instalación local en un CODEX_HOME
temporal: marketplace add, plugin add y plugin list devolvieron 0.3.0 habilitado.
La prueba de protocolo es independiente y registra MCP temporalmente; no demuestra
por sí sola el arranque desde la caché instalada. Después, arrancar con el wrapper
de la misma versión del checkout:

```bash
node /ruta/absoluta/fastapi-tools/codex/run.mjs -C /ruta/absoluta/aplicacion
```

El wrapper determina su propia ubicación y pasa `FASTAPI_TOOLS_PLUGIN_ROOT`
solo al proceso hijo. Preserva argumentos, cwd y código de salida; no escribe
configuración. El MCP requiere esa ruta absoluta y falla visiblemente si falta.
`codex/mcp.json` reenvía esa variable y `FASTAPI_APP_PORT` mediante `env_vars`;
no contiene interpolaciones de Claude ni fija `cwd`. El puerto predeterminado
es 8000. Ejemplo:

```bash
FASTAPI_APP_PORT=8181 node /ruta/fastapi-tools/codex/run.mjs -C /ruta/aplicacion
```

`codex/launch.mjs` sustituye cualquier `PROJECT_ROOT` heredado por el cwd real
del proceso MCP y carga el servidor compartido. No descubre proyectos ni genera
comandos alternativos. `analyze_project` permite comprobar la raíz seleccionada.
Cambiar de directorio en una herramienta shell no cambia el cwd del MCP ya
iniciado: iniciar una sesión nueva para otra aplicación. Mantener alineadas la
versión del plugin instalado y la del wrapper; este carga el MCP de su checkout.

El handoff explícito de ruta evita depender de expansión de `${PLUGIN_ROOT}`
en el loader de compatibilidad. Las pruebas propias de este repositorio validan
el wrapper y su configuración con Codex 0.166.0; no prueban la interpolación
automática de esa variable. No se afirma compatibilidad de un inicio bare `codex`
sin la variable ni de un inicio desktop sin este entorno. Este adaptador no
requiere archivos, instalación ni configuración de Spring Boot Tools.

## Doctor offline

El doctor arranca con Python 3.11+ y usa la biblioteca estándar. Ejecutarlo con
un checkout y ejecutables Node/Python de confianza:

```bash
python3 /ruta/fastapi-tools/scripts/install-doctor.py --workspace /ruta/aplicacion
python3 /ruta/fastapi-tools/scripts/install-doctor.py --json \
  --workspace /ruta/aplicacion/app --project /ruta/aplicacion
```

`--plugin-root` toma por defecto el checkout del script; `--workspace`, el cwd.
`--node` y `--python` permiten seleccionar ejecutables, sin argumentos de shell.
El workspace debe existir fuera del bundle. `--project` añade dos consultas
estáticas `action: discover` al runtime y compara raíces canónicas; admite un
workspace anidado en el mismo proyecto. No importa la aplicación ni ejecuta
`setup.py`, tests, migraciones, gestores de paquetes o herramientas del proyecto.

Comprueba:

- Linux/macOS, versiones y paths de Node/Python; presencia de Codex en PATH.
- JSON y rutas internas de los manifiestos, registro Claude/Codex, supresión
  explícita de hooks y reutilización de skills, MCP y runtime.
- Loader exacto admitido, cwd heredado, variables reenviadas y ruta del wrapper.
- Concordancia de versiones plugin/marketplace/package/lock/servidor con 0.3.0
  y concordancia de declaraciones de dependencias package/lock.
- Resolución local de exports ESM y existencia de archivos, incluido
  `@modelcontextprotocol/server/stdio`, sin importar las dependencias.

No ejecuta Codex: incluso `codex --version` intentó crear aliases locales en
esta instalación. Si existe `codex-package.json` del paquete standalone junto
al binario resuelto, valida su entrypoint y lee su versión como metadatos.
Otros formatos de instalación pueden dejar `version: null`; el reporte expone
`versionProbe: skipped`. Esto no prueba compatibilidad ni autenticación del host.

No usa red, no escribe archivos, no instala paquetes ni modifica configuración, y no arranca
MCP/hosts. Las únicas ejecuciones son probes acotados de Node/Python y descubrimiento
estático opcional, con Python aislado y sin inicialización de site. Cada probe tiene límite de cinco segundos y 64 KiB de salida;
se eliminan variables heredadas de preload, cobertura, caché e historial que
podrían causar cargas o escrituras incidentales. Resolver dependencias no prueba
integridad, compatibilidad de versiones instaladas ni arranque correcto del MCP.
El doctor tampoco inspecciona skills instaladas en caché ni el cwd de otro proceso.

La salida JSON tiene `schemaVersion: 1`, `ok`, `exitCode`, `pluginRoot`,
`workspace` y `checks` ordenados con `id`, `status`, `message` y evidencia
específica. Estados: `ok`, `warning`, `error`, `skipped`. Los mensajes no son API.
Códigos: 0 sin errores (admite warnings/skips), 1 diagnóstico fallido,
2 argumentos inválidos (usage de argparse en stderr, también con `--json`).
Un Python ausente o demasiado antiguo requiere preparación previa para arrancar.

## Diferencias y límites

Las skills compartidas conservan instrucciones orientadas a Claude cuando
corresponda; declarar su directorio no traduce herramientas del host, subagentes
ni garantiza selección por un modelo. `agents/` no se registra como agentes Codex.
Leer su guía manualmente no equivale a ejecutar revisores independientes.

El manifiesto establece `hooks: {"hooks": {}}`, suprimiendo el descubrimiento
predeterminado de `hooks/hooks.json`. Este adaptador no proporciona guards,
compilación post-edición ni verificación automática Stop. Solicitar explícitamente
`run_build` con `task: verify` y examinar el resultado. Locks, límites, cancelación
y reutilización de verificaciones siguen siendo responsabilidad del runtime.
`.lsp.json`, modelos/permisos de agentes Claude y `userConfig` tampoco se traducen.

Las siete herramientas son `analyze_project`, `run_build`, `run_tests`,
`check_migrations`, `openapi_endpoints`, `app_health` e `initialize_project`.
El adaptador publica el catálogo del servidor sin lista propia. El contrato de
inicialización usa `destination`, `projectName`, `explicitRequest: true`; el
runtime procesa `action: initialize`.
No inferir autorización de generación por ausencia de archivos. El doctor no
invoca inicialización. Sus políticas concretas corresponden al runtime compartido.

El análisis estático no importa código y no confirma rutas dinámicas. Los checks
explícitos pueden ejecutar configuración de pytest, herramientas y Alembic; se
requiere una aplicación de confianza. Los modos HTTP/status tienen los efectos
y límites descritos en la arquitectura. El funcionamiento web sin ejecutor local,
la publicación pública y la interfaz desktop no se verificaron.

## Evidencia reproducible

```bash
bash tests/codex/test-basic.sh
bash tests/install-doctor/test-basic.sh
python3 -B tests/codex/cli-smoke.py
python3 -B tests/codex/install-smoke.py
```

La suite del adaptador usa mensajes stdio reales de inicialización, catálogo y
llamadas MCP. Comprueba reubicación con espacios/metacaracteres, cwd anidado,
variables antiguas, AST sin imports, compilación Python válida/fallida, rechazo
de payload de shell y propagación de argumentos/salida del wrapper. Exige exactamente
16 skills y siete herramientas; comprueba rechazos de `initialize_project`
sin generar ni hacer llamadas de red.

El smoke opcional requiere Codex instalado, pero no autenticación ni modelos.
Crea un `CODEX_HOME` y catálogo temporales, usa `plugin/read` para leer skills y
hooks y registra el wiring MCP en configuración exclusivamente temporal. Inicia
un thread vacío y llama `analyze_project`; una allowlist excluye `turn/start`
y `plugin/install`. No instala el plugin ni toca configuración global.

La comprobación local con Codex CLI 0.166.0 pasó con 16 skills, cero hooks y siete
herramientas tras integrar el inicializador. El director confirmó 7/7 regresiones
del adaptador fuera del sandbox del worker. El test separado install-smoke
verifica instalación/listado en estado temporal y elimina su registro al salir.
Ninguno valida selección semántica de skills ni interfaz desktop. Las regresiones del doctor prueban ausencia de
mutaciones, dependencias que fallarían si se importaran, versiones inconsistentes,
exports faltantes, JSON inválido, rutas escapadas y límites de probes.

## Fuentes oficiales consultadas

- [Package your plugin](https://developers.openai.com/plugins/build/plugins):
  overlay de compatibilidad, rutas internas y hooks explícitos que reemplazan
  descubrimiento predeterminado.
- [Plugins: guía de OpenAI](https://learn.chatgpt.com/docs/plugins):
  distribución y diferencias entre superficies de ejecución.
- [Plugins en Agents API](https://developers.openai.com/api/docs/guides/agents-api/tools/plugins):
  ejemplo de `skills` y `mcpServers` en el manifiesto de compatibilidad.

Fuentes consultadas el 2026-10-31. `codex --help`, `codex plugin --help` y
`codex plugin add --help` y `codex plugin marketplace add --help` confirmaron la interfaz local 0.166.0. La instalación se probó únicamente en
estado temporal; no se modificó configuración global ni se ejecutaron comandos
de publicación, autenticación o turnos de modelo.
