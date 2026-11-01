# Metodología de evaluación y evidencia B1

El [inventario](component-evidence.json) cubre cada skill y agente distribuido:
trigger, hash del texto revisado, regresiones relacionadas, casos prospectivos y
solapamientos. **Beneficio conductual: NO MEDIDO.** No se ejecutaron evaluaciones
pagadas ni generaciones de modelos. Un ejemplo correcto, un grader de activación
o un smoke de integración no demuestra que un componente mejore las respuestas.

La referencia Spring Boot se inspeccionó sólo con `git show` en el tag `v0.3.0`
(`ba3c6cf541983d0164c10021ed9e1e0ae81905c1`). Se adaptó el diseño experimental a
Python y ASGI con una implementación propia; no se trasladaron convenciones JVM,
herramientas de migración ni garantías de salud de Spring a FastAPI.

## Qué evidencia cuenta

| Señal | Qué permite concluir | Qué queda pendiente |
| --- | --- | --- |
| Integridad de frontmatter, referencias y permisos | El componente está inventariado y mantiene su superficie | Carga efectiva en cada host |
| Pruebas deterministas del harness | Preparación/comparación coherentes bajo fixtures sintéticas | Eficacia de skills/agentes |
| Ejemplos reales FastAPI/Pydantic/SQLAlchemy/Alembic | Comportamientos concretos ejecutados en ese entorno | PostgreSQL, carga, todos los rangos de versiones |
| `tool_used` | Activación observada en un transcript real, si se ejecuta | Calidad o causalidad |
| Rúbrica de calidad sobre respuesta congelada | Resultado por criterio de esa muestra y juez | Generalización y comparación causal |
| Full frente a baseline/selected-minus | Diferencias pareadas bajo entradas equivalentes | Beneficio si faltan brazos, aislamiento o identidad real de modelos |

Los campos funcionales del inventario apuntan a pruebas disponibles, no afirman
que cada componente haya sido ejecutado por un modelo. Las fuentes y checksums
permiten detectar deriva; no autentican una ejecución ni sustituyen sus logs.

## Fuentes oficiales consultadas antes de las decisiones

- [Claude plugin evals](https://code.claude.com/docs/en/plugin-evals): distingue
  activación/calidad, grants, mocks, scaffold y servidores MCP reales.
- [Skills](https://code.claude.com/docs/en/skills) y
  [agentes](https://code.claude.com/docs/en/sub-agents): frontmatter y herramientas
  son parte del producto; B1 conserva las capacidades existentes.
- [CLI](https://code.claude.com/docs/en/cli-reference): el límite de gasto es una
  estimación que puede excederse; no es garantía de facturación exacta.
- [FastAPI async tests](https://fastapi.tiangolo.com/advanced/async-tests/): HTTPX
  no inicia lifespan automáticamente.
- [Pydantic migration](https://docs.pydantic.dev/latest/migration/): nullable no
  implica omittable en v2; TypeError de un validator no pasa a ValidationError.
- [SQLAlchemy sesiones](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
  y [asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html): rollback
  tras fallo de flush, sesión por tarea y carga explícita de relaciones.
- [Alembic autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html):
  revisión manual, límites de detección de renames y alcance ejecutable de check.

## Ablación offline

`evals/tools/ablation.py` sólo ofrece `plan`, `prepare` y `compare`: no ejecuta
modelos, builds, instalaciones ni red. El plan fija host/versión, modelo solicitado,
effort, juez canónico, turnos/tiempo, repeticiones, prompts, todos los graders,
snapshots y componentes retirados. Usa tres variantes:

- `baseline`: mismo proyecto, sin plugin.
- `full`: proyecto y producto completos para el experimento Claude Code.
- `selected-minus`: mismo producto retirando sólo las skills/agentes elegidos.

Para aislar la contribución de un componente, retirarlo solo; retirar skill y
agente juntos mide la intervención conjunta. Un snapshot preparado no acredita
la carga efectiva del plugin ni la disponibilidad de dependencias MCP. Este
harness está diseñado para Claude Code; no mide el comportamiento de Codex.

```bash
python3 evals/tools/ablation.py plan /tmp/b1-plan.json \
  --snapshot /tmp/fastapi-fixture --cases test-writer-behavior \
  --model EXACT_GENERATOR_ID --effort high --host-version EXACT_HOST_VERSION \
  --canonical-judge EXACT_JUDGE_ID --generation-timeout 300 --max-turns 10 \
  --minus fastapi-testing fastapi-test-writer
python3 evals/tools/ablation.py prepare /tmp/b1-plan.json /tmp/b1-full \
  --variant full --case test-writer-behavior --record /tmp/b1-full-provenance.json
python3 evals/tools/ablation.py compare /tmp/b1-plan.json /tmp/b1-pending.json
```

El snapshot de aplicación debe ser explícito, separado del checkout del plugin.
Preparar cada brazo en un destino nuevo y ausente. Los registros de operador
quedan fuera de ambos árboles fuente y del árbol de generación. Éste contiene
sólo `workspace/` y, cuando corresponde, `plugin/`. Se conservan contenidos y bits
ejecutables, se rechazan symlinks y archivos especiales incluidos, y se verifica
la deriva antes de copiar. Se excluyen, a cualquier profundidad, instrucciones
de mantenimiento AGENTS/CLAUDE/GEMINI, evals, graders, informes, docs, entornos,
caches, credenciales `.env*` y dependencias generadas. Inspeccionar los archivos
incluidos: el filtrado no es un detector universal de secretos o respuestas.

Un runner externo autorizado deberá aplicar aislamiento real de herramientas y
filesystem, desactivar instrucciones/plugins ambientales, suministrar el mismo
prompt/contexto a cada brazo y registrar la carga efectiva. Directorios frescos
y hashes no impiden a una herramienta sin restricciones leer árboles vecinos.
Los graders/registros nunca deben exponerse al generador. El contexto del caso
test-writer está embebido y una regresión comprueba su igualdad con los fixtures.

## Congelar, juzgar y comparar

El freezer conserva compatibilidad con el brazo `with`, run 0; admite `--arm`,
`--variant` y `--provenance`. Exige el prompt actual y fija definiciones de graders.
Para comparación pareada, verifica que el reporte declare `modelRequested`,
`effort`, `claudeVersion` y `executionLimits` iguales a la preparación. Un reporte
antiguo sin procedencia puede juzgarse por separado, pero no probar equivalencia
retrospectiva. No se infieren argumentos reales a partir del plan.

```bash
python3 evals/tools/frozen_judge.py freeze /tmp/generation.json \
  evals/test-writer-behavior /tmp/full-frozen.json --arm with --variant full \
  --provenance /tmp/b1-full-provenance.json
python3 evals/tools/ablation.py compare /tmp/b1-plan.json /tmp/b1-comparison.json \
  --entry /tmp/full-frozen.json /tmp/full-judged.json \
  --entry /tmp/baseline-frozen.json /tmp/baseline-judged.json
```

Usar `-` como segundo argumento de `--entry` retiene una generación sin juez.
El comando `judge` es externo y pagado; requiere autorización y presupuesto
explícitos, además de `--authorize-paid --max-budget-usd`. El presupuesto estimado
se reparte entre los jueces solicitados; conservar margen para posibles excesos
del CLI. Ninguna operación offline llama automáticamente a `judge`.

El juez recibe sólo prompt, criterios y líneas de la respuesta congelada: no
identidad del brazo, puntuaciones previas ni metadatos de generación. Se ejecuta
desde un cwd temporal vacío con herramientas/MCP desactivados. Cada criterio
necesita booleano, razón y línea literal no vacía para PASS. Omisiones/fallos
quedan como fallos; un error de invocación no se convierte en calidad aprobada.
El primer juez, preregistrado, es canónico. Otros jueces son diagnósticos.

La comparación conserva los criterios por muestra, activación separada,
telemetría de generación y juicio, y brazos ausentes. Tokens/coste/duración sólo
proceden del resultado que los declara, nunca de sumas del informe que puedan
incluir graders. Campos ausentes son `unavailable`, no cero; un cero declarado
sigue siendo un dato. Modelos resueltos diferentes producen `incomparable`; sin
identidad resuelta no se calcula delta. Los techos opcionales se preregistran en
JSON con generation/judging e inputTokens/outputTokens/costUSD/durationMs;
`null` significa no registrado y una métrica ausente no aprueba un techo.

Todos los informes se crean sin sobrescribir. Los sellos SHA-256 detectan cambios
accidentales; alguien puede recalcularlos sobre evidencia fabricada. Conservar
reportes originales y logs confiables. El harness no declara automáticamente
eficacia, significancia estadística ni ahorro de tokens/coste.

## Inicializador coordinado con el director

Contrato confirmado en esta sesión:
`initialize_project({destination, projectName, explicitRequest: true})`, que delega
al CLI `action: initialize`. La skill verifica el esquema realmente instalado;
no inventa opciones ni respuesta final. Exige destino ausente, autorización
explícita y protección de ancestros Python/workspace. Directorios vacíos y
symlinks colgantes son destinos existentes. La generación queda separada de
instalar dependencias, ejecutar, migrar, git y publicar.

Los tres casos cubren autorización positiva, ancestros/destinos protegidos y
preview sin autorización. Sin herramienta real o grant, el caso positivo sólo
evalúa el tratamiento de esa limitación. Una futura evaluación funcional real
necesita permisos de herramienta exactos del host, dependencias MCP y scaffold
autorizado; `--trust-plugin` no concede por sí solo esos accesos. Los checks
runtime/MCP y la revisión independiente del inicializador pertenecen al director.

## Hallazgos B1 y redundancias

| Trigger inspeccionado | Hallazgo/corrección | Archivos principales |
| --- | --- | --- |
| Comparar un componente con su ausencia | Faltaban plan, preparación sin fuga y comparación pareada offline | evals/tools/ablation.py, tests/evaluations/ablation_test.py |
| Rejuzgar un informe | Faltaban procedencia por brazo, métricas separadas y cegado del juez | evals/tools/frozen_judge.py, tests/evaluations/judge_test.py |
| Afirmar cobertura/beneficio de catálogo | Faltaba evidencia individual; activación y calidad se confundían | docs/component-evidence.json, tests/evaluations/component_inventory_test.py, evals/*/graders/ |
| Crear proyecto nuevo | Faltaba skill con contrato del nuevo MCP y límites de destino | skills/fastapi-initializer/SKILL.md, evals/initializer-*/ |
| Flush fallido/rollback aparente | Mock o teardown pueden ocultar falta de atomicidad; se exige escritura real y observador independiente | skills/fastapi-testing/, skills/fastapi-database/, agents/fastapi-runtime-reviewer.md, tests/examples/test_sqlalchemy.py |
| Alembic check/autogenerate | No equivalen al lint AST ni prueban rename/backfill seguro | skills/fastapi-database/, agents/fastapi-migration-reviewer.md, tests/examples/test_alembic.py |
| Migración Pydantic | Required/null, TypeError y lazy ORM necesitan pruebas wire | skills/fastapi-pydantic-v1-to-v2-migration/, tests/examples/test_pydantic_async.py |
| Chequear fronteras de módulos | Evitar imponer import-linter si no está configurado | skills/fastapi-modular-architecture/ |

Se retienen todos los componentes existentes. La revisión de redundancias está
en el inventario con miembros, distinción de salida/permisos y decisión. Hay
solapamientos entre diseño/implementación, guía de tests/escritor, DB/revisores,
rendimiento/carga, arquitectura/diseñador y Docker/CI/revisor. Son candidatos a
ablación, no evidencia para eliminar componentes. No se cambiaron permisos de
producto para configurar al equipo.

## Validación y límites

```bash
bash tests/evaluations/test-basic.sh
EXAMPLES_PYTHON=.fastapi-tools/validation-env/bin/python bash tests/examples/check.sh
git diff --check -- skills agents evals tests/evaluations tests/examples \
  docs/component-evidence.json docs/evaluation-methodology.md
```

Los ejemplos incluyen router/OpenAPI, respuesta filtrada, overrides, lifespan,
errores Pydantic v2, rollback SQLAlchemy real y Alembic contra SQLite temporal.
No prueban PostgreSQL, concurrencia AsyncSession real ni una matriz completa de
versiones. El director validó los diez ejemplos completos con SQLAlchemy 2.0.55,
dentro del rango declarado, después de la preparación explícita de dependencias.
El worker sólo pudo ejecutar un subconjunto por restricciones de su sandbox;
el informe de auditoría separa esos límites del resultado final integrado.

Las 26 regresiones offline de evaluación validan mecanismos de preparación,
procedencia, comparación y conservación de fallos. El parser YAML de packaging
valida el frontmatter; el validador auxiliar skill-creator no estuvo disponible
por falta de PyYAML. Los smokes de instalación aislada de Codex y los ecosistemas
Python son evidencia funcional de integración, no mediciones conductuales.
Ver docs/audit-2026-10-31.md para comandos, versiones y límites finales.
