# Benchmark de mejora real de prompts

Target: **codex** · casos: **31** · generado sin llamadas a modelos.

## Resumen ejecutivo

NSCP produce **dos** salidas y su calidad es muy distinta. Medirlas juntas
escondería la conclusión, así que se reportan por separado:

| Salida | Qué es | Estructura | Expansión |
|---|---|---:|---:|
| `optimized_prompt` (“Copiar prompt”) | original + cabecera de perfil + una línea genérica | 1.74/8 | ×1.91 |
| `reconstructed` (artefacto completo) | prompt reconstruido con rol, tareas, restricciones, contrato de salida y verificación | 8.0/8 | ×10.14 |

En **6 de 31** casos el prompt que el usuario copia no aporta ninguna señal estructural nueva: sale igual que la entrada.
La mejora real está en el artefacto reconstruido, no en el botón de copiar.

## Lo que sí y lo que no

- **Sí**: estructura del artefacto completo (+8.0 señales medias sobre 8 posibles).
- **Sí**: las ambigüedades detectadas se convierten en preguntas visibles (62 detectadas → 62 mostradas).
- **Sí**: los requisitos literales del input se preservan (100.0% en el prompt copiable, 87.0% en el reconstruido).
- **No**: el prompt copiable no se acorta (×1.91) ni gana estructura en entradas vagas.
- **No**: la puntuación interna `prompt_quality` apenas cambia (83.71 → 84.29, +0.58): mide contrato semántico, no utilidad.

## Agregado

| Métrica | Valor |
|---|---:|
| Casos | 31 |
| Estructura media (input) | 0.0/8 |
| Estructura media (prompt copiable) | 1.74/8 |
| Estructura media (artefacto completo) | 8.0/8 |
| Preservación de requisitos (copiable) | 100.0% |
| Preservación de requisitos (completo) | 87.0% |
| Expansión mediana (copiable / completo) | ×1.91 / ×10.14 |
| Calidad interna input → output | 83.71 → 84.29 (+0.58) |
| Puntuación de preservación (validador) | 90.94/100 |
| Ambigüedades detectadas → preguntas mostradas | 62 → 62 |
| Casos con pérdidas críticas | 2 |
| Casos con restricciones inventadas | 0 |

## Por grupo

| Grupo | Casos | Estructura copiable | Estructura completa | Preservación | Expansión |
|---|---:|---:|---:|---:|---:|
| data | 2 | 1.0/8 | 8.0/8 | 100.0% | ×1.8 |
| forum | 10 | 1.3/8 | 8.0/8 | 100.0% | ×1.97 |
| learning | 2 | 1.0/8 | 8.0/8 | 100.0% | ×1.87 |
| multilingual | 3 | 1.0/8 | 8.0/8 | 100.0% | ×1.95 |
| sysadmin | 2 | 4.5/8 | 8.0/8 | 100.0% | ×11.61 |
| technical | 4 | 5.0/8 | 8.0/8 | 100.0% | ×8.89 |
| vague | 5 | 0.4/8 | 8.0/8 | 100.0% | ×1.0 |
| writing | 3 | 1.0/8 | 8.0/8 | 100.0% | ×1.78 |

## Detalle por caso

| Caso | Grupo | Perfil | Estructura copiable | Estructura completa | Req. | Expansión | Ambigüedades |
|---|---|---|---:|---:|---:|---:|---:|
| forum-python-keyerror | forum | ADVANCED | 0→2 | 0→8 | 100% | ×1.78 | 2→2 |
| forum-js-async-order | forum | STANDARD | 0→1 | 0→8 | 100% | ×1.84 | 2→2 |
| forum-sql-slow | forum | STANDARD | 0→1 | 0→8 | 100% | ×1.96 | 2→2 |
| forum-docker-port | forum | ADVANCED | 0→1 | 0→8 | 100% | ×1.98 | 2→2 |
| forum-css-layout | forum | ADVANCED | 0→1 | 0→8 | 100% | ×1.98 | 2→2 |
| forum-git-undo | forum | STANDARD | 0→2 | 0→8 | 100% | ×2.10 | 2→2 |
| forum-regex-email | forum | ADVANCED | 0→1 | 0→8 | 100% | ×2.11 | 2→2 |
| forum-memory-leak | forum | STANDARD | 0→1 | 0→8 | 100% | ×1.96 | 2→2 |
| forum-excel-formula | forum | ADVANCED | 0→2 | 0→8 | 100% | ×2.17 | 2→2 |
| forum-cors-error | forum | ADVANCED | 0→1 | 0→8 | 100% | ×1.87 | 2→2 |
| vague-one-line-1 | vague | FAST | 0→0 | 0→8 | 100% | ×1.00 | 2→2 |
| vague-one-line-2 | vague | ADVANCED | 0→2 | 0→8 | 100% | ×17.00 | 2→2 |
| vague-one-line-3 | vague | FAST | 0→0 | 0→8 | 100% | ×1.00 | 2→2 |
| vague-one-line-4 | vague | FAST | 0→0 | 0→8 | 100% | ×1.00 | 2→2 |
| vague-one-line-5 | vague | FAST | 0→0 | 0→8 | 100% | ×1.00 | 2→2 |
| tech-api-fastapi | technical | ADVANCED | 0→2 | 0→8 | 100% | ×1.57 | 2→2 |
| tech-migration-plan | technical | ROP | 0→8 | 0→8 | 100% | ×16.13 | 2→2 |
| tech-data-pipeline | technical | STANDARD | 0→2 | 0→8 | 100% | ×1.65 | 2→2 |
| tech-review | technical | ROP | 0→8 | 0→8 | 100% | ×17.14 | 2→2 |
| writing-email | writing | FAST | 0→0 | 0→8 | 100% | ×1.00 | 2→2 |
| writing-rewrite | writing | STANDARD | 0→1 | 0→8 | 100% | ×1.78 | 2→2 |
| writing-docs | writing | ADVANCED | 0→2 | 0→8 | 100% | ×2.07 | 2→2 |
| data-analysis | data | ADVANCED | 0→1 | 0→8 | 100% | ×1.70 | 2→2 |
| data-metrics | data | STANDARD | 0→1 | 0→8 | 100% | ×1.91 | 2→2 |
| sysadmin-nginx | sysadmin | ADVANCED | 0→1 | 0→8 | 100% | ×1.75 | 2→2 |
| sysadmin-backup | sysadmin | ROP | 0→8 | 0→8 | 100% | ×21.46 | 2→2 |
| learning-explain | learning | ADVANCED | 0→1 | 0→8 | 100% | ×1.93 | 2→2 |
| learning-interview | learning | ADVANCED | 0→1 | 0→8 | 100% | ×1.82 | 2→2 |
| i18n-french | multilingual | ADVANCED | 0→2 | 0→8 | 100% | ×2.39 | 2→2 |
| i18n-german | multilingual | ADVANCED | 0→1 | 0→8 | 100% | ×1.95 | 2→2 |
| i18n-portuguese | multilingual | FAST | 0→0 | 0→8 | 100% | ×1.00 | 2→2 |

## Cobertura en entradas de varias frases

**5 de 31** casos (16%) tienen requisitos después de la primera frase que el artefacto reconstruido **no** incluye. El prompt copiable sí los conserva porque embebe el texto original.

| Caso | Frases | Requisitos de frases 2+ ausentes del artefacto |
|---|---:|---|
| forum-python-keyerror | 5 | `CSV` |
| tech-api-fastapi | 5 | `201, 422` |
| tech-migration-plan | 4 | `16` |
| data-metrics | 2 | `SQL` |
| sysadmin-nginx | 3 | `/etc/ssl.` |

Está cubierto por `tests/test_reconstruction_coverage.py` con un `xfail` estricto: cuando el extractor transporte el objetivo completo, ese test pasará a verde y este número deberá bajar a cero.

## Casos que requieren atención

- **vague-one-line-1**: pérdidas críticas → `missing_goal`
- **vague-one-line-2**: pérdidas críticas → `missing_goal`
