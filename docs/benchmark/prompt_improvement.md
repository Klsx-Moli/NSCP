# Benchmark de mejora real de prompts

Target: **codex** · casos: **31** · generado sin llamadas a modelos.

## Resumen ejecutivo

NSCP produce **dos** salidas y su calidad es muy distinta. Medirlas juntas
escondería la conclusión, así que se reportan por separado:

| Salida | Qué es | Estructura | Expansión |
|---|---|---:|---:|
| `optimized_prompt` (“Copiar prompt”) | objetivo completo + rol, tareas, restricciones, contrato de salida, verificación y ruta de bloqueo | 5.74/8 | ×4.1 |
| `reconstructed` (artefacto completo) | prompt reconstruido con seeds y directivas de perfil añadidas | 8.0/8 | ×10.33 |

El prompt copiable ya no es el original con una cabecera: ahora declara **5.74/8** señales de estructura frente a **0.0/8** del input, conservando el **100%** de los requisitos literales. Quedan **6 de 31** casos sin señal nueva, todos entradas vagas de una línea.

## Lo que sí y lo que no

- **Sí**: estructura del prompt copiable (+5.74 señales medias sobre 8).
- **Sí**: estructura del artefacto completo (+8.0 señales medias sobre 8).
- **Sí**: las ambigüedades detectadas se convierten en preguntas visibles (62 detectadas → 62 mostradas).
- **Sí**: los requisitos literales del input se preservan (100.0% en el prompt copiable, 97.0% en el reconstruido).
- **No**: el prompt compilado no se acorta (×4.1 el copiable, ×10.33 el completo).
- **No**: una entrada vaga de una línea sigue sin poder estructurarse: no hay información que extraer, solo preguntas que hacer.
- **No**: la puntuación interna `prompt_quality` apenas cambia (83.71 → 84.29, +0.58): mide contrato semántico, no utilidad.

## Agregado

| Métrica | Valor |
|---|---:|
| Casos | 31 |
| Estructura media (input) | 0.0/8 |
| Estructura media (prompt copiable) | 5.74/8 |
| Estructura media (artefacto completo) | 8.0/8 |
| Preservación de requisitos (copiable) | 100.0% |
| Preservación de requisitos (completo) | 97.0% |
| Expansión mediana (copiable / completo) | ×4.1 / ×10.33 |
| Calidad interna input → output | 83.71 → 84.29 (+0.58) |
| Puntuación de preservación (validador) | 95.81/100 |
| Ambigüedades detectadas → preguntas mostradas | 62 → 62 |
| Casos con pérdidas críticas | 2 |
| Casos con restricciones inventadas | 0 |

## Por grupo

| Grupo | Casos | Estructura copiable | Estructura completa | Preservación | Expansión |
|---|---:|---:|---:|---:|---:|
| data | 2 | 7.0/8 | 8.0/8 | 100.0% | ×3.83 |
| forum | 10 | 7.0/8 | 8.0/8 | 100.0% | ×4.27 |
| learning | 2 | 7.0/8 | 8.0/8 | 100.0% | ×4.34 |
| multilingual | 3 | 4.67/8 | 8.0/8 | 100.0% | ×4.74 |
| sysadmin | 2 | 7.5/8 | 8.0/8 | 100.0% | ×13.05 |
| technical | 4 | 7.5/8 | 8.0/8 | 100.0% | ×9.84 |
| vague | 5 | 1.4/8 | 8.0/8 | 100.0% | ×1.0 |
| writing | 3 | 4.67/8 | 8.0/8 | 100.0% | ×3.53 |

## Detalle por caso

| Caso | Grupo | Perfil | Estructura copiable | Estructura completa | Req. | Expansión | Ambigüedades |
|---|---|---|---:|---:|---:|---:|---:|
| forum-python-keyerror | forum | ADVANCED | 0→7 | 0→8 | 100% | ×3.63 | 2→2 |
| forum-js-async-order | forum | STANDARD | 0→7 | 0→8 | 100% | ×3.68 | 2→2 |
| forum-sql-slow | forum | STANDARD | 0→7 | 0→8 | 100% | ×4.10 | 2→2 |
| forum-docker-port | forum | ADVANCED | 0→7 | 0→8 | 100% | ×4.85 | 2→2 |
| forum-css-layout | forum | ADVANCED | 0→7 | 0→8 | 100% | ×4.85 | 2→2 |
| forum-git-undo | forum | STANDARD | 0→7 | 0→8 | 100% | ×4.12 | 2→2 |
| forum-regex-email | forum | ADVANCED | 0→7 | 0→8 | 100% | ×5.36 | 2→2 |
| forum-memory-leak | forum | STANDARD | 0→7 | 0→8 | 100% | ×4.10 | 2→2 |
| forum-excel-formula | forum | ADVANCED | 0→7 | 0→8 | 100% | ×4.80 | 2→2 |
| forum-cors-error | forum | ADVANCED | 0→7 | 0→8 | 100% | ×4.41 | 2→2 |
| vague-one-line-1 | vague | FAST | 0→0 | 0→8 | 100% | ×1.00 | 2→2 |
| vague-one-line-2 | vague | ADVANCED | 0→7 | 0→8 | 100% | ×52.67 | 2→2 |
| vague-one-line-3 | vague | FAST | 0→0 | 0→8 | 100% | ×1.00 | 2→2 |
| vague-one-line-4 | vague | FAST | 0→0 | 0→8 | 100% | ×1.00 | 2→2 |
| vague-one-line-5 | vague | FAST | 0→0 | 0→8 | 100% | ×1.00 | 2→2 |
| tech-api-fastapi | technical | ADVANCED | 0→7 | 0→8 | 100% | ×2.37 | 2→2 |
| tech-migration-plan | technical | ROP | 0→8 | 0→8 | 100% | ×16.83 | 2→2 |
| tech-data-pipeline | technical | STANDARD | 0→7 | 0→8 | 100% | ×2.85 | 2→2 |
| tech-review | technical | ROP | 0→8 | 0→8 | 100% | ×17.67 | 2→2 |
| writing-email | writing | FAST | 0→0 | 0→8 | 100% | ×1.00 | 2→2 |
| writing-rewrite | writing | STANDARD | 0→7 | 0→8 | 100% | ×3.53 | 2→2 |
| writing-docs | writing | ADVANCED | 0→7 | 0→8 | 100% | ×4.53 | 2→2 |
| data-analysis | data | ADVANCED | 0→7 | 0→8 | 100% | ×3.77 | 2→2 |
| data-metrics | data | STANDARD | 0→7 | 0→8 | 100% | ×3.89 | 2→2 |
| sysadmin-nginx | sysadmin | ADVANCED | 0→7 | 0→8 | 100% | ×3.96 | 2→2 |
| sysadmin-backup | sysadmin | ROP | 0→8 | 0→8 | 100% | ×22.14 | 2→2 |
| learning-explain | learning | ADVANCED | 0→7 | 0→8 | 100% | ×4.49 | 2→2 |
| learning-interview | learning | ADVANCED | 0→7 | 0→8 | 100% | ×4.18 | 2→2 |
| i18n-french | multilingual | ADVANCED | 0→7 | 0→8 | 100% | ×5.67 | 2→2 |
| i18n-german | multilingual | ADVANCED | 0→7 | 0→8 | 100% | ×4.74 | 2→2 |
| i18n-portuguese | multilingual | FAST | 0→0 | 0→8 | 100% | ×1.00 | 2→2 |

## Casos que requieren atención

- **vague-one-line-1**: pérdidas críticas → `missing_goal`
- **vague-one-line-2**: pérdidas críticas → `missing_goal`
