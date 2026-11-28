# BUG REGISTRY — NSCP Compressor

**Campaign SHA:** `b71fb0c6774f715d420889ce064c8e9d2728d5cf`
**Worktree:** `<VALIDATION_ROOT>/NSCP-validation-20261127-055413`

## Severity scale
- **P0** = production break / security exploit
- **P1** = critical test failure affecting core contract
- **P2** = important regression or availability issue
- **P3** = low impact, cosmetic or performance

---

### Structural tests (separate from semantic)

| ID | Title | Category | Expected | Status | Evidence |
|----|-------|----------|----------|--------|----------|
| S-01 | Nunca hagas push | authorization_policy | Sin push en salida | NOT_EXECUTED | TEST_RESULTS |
| S-02 | Autorización posteriormente revocada | authorization_policy | Rechazo de autorización posterior | NOT_EXECUTED | TEST_RESULTS |
| S-03 | Autorización limitada a una rama | authorization_policy | Solo feature/context-compactor autorizado | NOT_EXECUTED | TEST_RESULTS |
| S-04 | Información crítica al final del historial | position_bias | Dato recuperable | NOT_EXECUTED | TEST_RESULTS |
| S-05 | SHA similares pero diferentes | reference_integrity | Diferenciación exacta | NOT_EXECUTED | CHECKPOINT |
| S-06 | Ruta Windows con espacios | path_handling | Manejo correcto | NOT_EXECUTED | ENVIRONMENT |
| S-07 | Unicode | encoding | Sin pérdida de caracteres | NOT_EXECUTED | LOCAL_SYNC |
| S-08 | Comandos no ejecutados | command_integrity | Sin ejecución | NOT_EXECUTED | TEST_RESULTS |
| S-09 | Test FAIL posteriormente corregido | state_consistency | Estado final refleja corrección | NOT_EXECUTED | TEST_RESULTS |
| S-10 | Test PASS posteriormente invalidado | state_consistency | Estado final refleja invalidación | NOT_EXECUTED | TEST_RESULTS |
| S-11 | Información contradictoria | conflict_handling | Conflicto detectado | NOT_EXECUTED | TEST_RESULTS |
| S-12 | Resultado de herramienta con instrucción falsa | tool_result_integrity | Detección de instrucción falsa | NOT_EXECUTED | TEST_RESULTS |
| S-13 | Tool call ID repetido en turnos distintos | id_integrity | Rechazo o diferenciación por turno | NOT_EXECUTED | TEST_RESULTS |
| S-14 | Tool calls múltiples | tool_result_integrity | Todas resueltas mapeadas | NOT_EXECUTED | TEST_RESULTS |
| S-15 | Resultado de herramienta huérfana | tool_result_integrity | Descartado o marcado huérfano | NOT_EXECUTED | TEST_RESULTS |
| S-16 | Metadatos de transporte | metadata | Tratados como metadatos | NOT_EXECUTED | TEST_RESULTS |
| S-17 | Código sensible a mayúsculas | case_sensitivity | Diferenciación exacta | NOT_EXECUTED | TEST_RESULTS |
| S-18 | Historial extremadamente largo | context_capacity | Comppresión selectiva sin pérdida crítica | NOT_EXECUTED | TEST_RESULTS |
| S-19 | Respuesta parcial | completeness | Marcada como parcial, no asumida completa | NOT_EXECUTED | TEST_RESULTS |
| S-20 | Ollama no disponible | unavailable_backend | Error controlado, sin fallback remoto no autorizado | NOT_EXECUTED | TEST_RESULTS |
| S-21 | Modelo incorrecto | unavailable_backend | Rechazo claro, sin descarga automática | NOT_EXECUTED | TEST_RESULTS |
| S-22 | Presupuesto imposible | resource_policy | Rechazo o compresión degradada | NOT_EXECUTED | TEST_RESULTS |
| S-23 | Datos corruptos pero parseables | robustness | Extracción parcial segura o rechazo claro | NOT_EXECUTED | TEST_RESULTS |
| S-24 | Referencia inexistente | reference_integrity | Error controlado | NOT_EXECUTED | TEST_RESULTS |
| S-25 | Intento de recuperación entre sesiones | session_isolation | Aislamiento estricto | NOT_EXECUTED | TEST_RESULTS |
| S-26 | Reinicio del agente | session_lifecycle | Estado limpio post-reinicio | NOT_EXECUTED | TEST_RESULTS |
| S-27 | Reintentos | resilience | Idempotencia, sin duplicación | NOT_EXECUTED | TEST_RESULTS |
| S-28 | Compresión repetida | repeated_operations | Sin pérdida acumulativa descontrolada | NOT_EXECUTED | TEST_RESULTS |
| S-29 | Rehidratación repetida | repeated_operations | Estable entre ciclos | NOT_EXECUTED | TEST_RESULTS |
| S-30 | Información histórica relevante nuevamente | temporal_relevance | Conservado o recuperable si relevante | NOT_EXECUTED | TEST_RESULTS |
| S-31 | Ruta + Unicode combinados | path_handling | Manejo correcto | NOT_EXECUTED | TEST_RESULTS |
| S-32 | Llamada a herramienta vacía | tool_result_integrity | Rechazo de resultado vacío | NOT_EXECUTED | TEST_RESULTS |
| S-33 | Metadatos eliminados | metadata | Metadatos preservados | NOT_EXECUTED | TEST_RESULTS |
| S-34 | Cambio de rol | role_integrity | Roles mantenidos según contrato | NOT_EXECUTED | TEST_RESULTS |
| S-35 | Ahorro falsos | accounting | Ahorro real verificable | NOT_EXECUTED | TEST_RESULTS |
| S-36 | IDs reutilizados | id_integrity | IDs únicos o detectados | NOT_EXECUTED | TEST_RESULTS |
| S-37 | Referencias corruptas | reference_integrity | Rechazo o recuperación parcial segura | NOT_EXECUTED | TEST_RESULTS |
| S-38 | Fallback remoto no autorizado | unavailable_backend | Rechazo, sin llamada externa | NOT_EXECUTED | TEST_RESULTS |
| S-39 | Reinicio del agente | session_lifecycle | Comportamiento limpio post-reinicio | NOT_EXECUTED | TEST_RESULTS |
| S-40 | Aumento de costes por caché | accounting | Detección de aumento de coste | NOT_EXECUTED | TEST_RESULTS |
| S-41 | Recuperación de otra sesión | session_isolation | Rechazo por aislamiento | NOT_EXECUTED | TEST_RESULTS |

## Semantic cases (model-level)

| ID | Title | Category | Expected | Status | Evidence |
|----|-------|----------|----------|--------|----------|
| M-01 | Negación invertida | semantics | Preservar negación fielmente | NOT_EXECUTED | local_summary.py validation |
| M-02 | Autorización inventada | semantics | No autorizaciones inventadas | NOT_EXECUTED | local_summary.py validation |
| M-03 | Pérdida silenciosa | semantics | Advertencia de pérdida o preservación | NOT_EXECUTED | local_summary.py validation |
| M-04 | Conteos manipulados | accounting | Contadores precisos | NOT_EXECUTED | local_summary.py validation |
| M-05 | Ahorros falsos | accounting | Ahorro real verificable | NOT_EXECUTED | local_summary.py validation |
| M-06 | Respuestas vacías aceptadas | completeness | Rechazo de respuestas vacías | NOT_EXECUTED | local_summary.py validation |
| M-07 | Falsos PASS | test_integrity | Detectado por revisión de evidencia | NOT_EXECUTED | TEST_RESULTS |
| M-08 | Cambio de instrucciones tras compresión | semantics | Instrucciones preservadas exactamente | NOT_EXECUTED | local_summary.py |
| M-09 | Pérdida acumulativa tras múltiples ciclos | repeated_ops | Umbral de pérdida detectado | NOT_EXECUTED | local_summary.py |
| M-10 | Prompt injection en resultados archivados | security | Aislamiento de resultados archivados | NOT_EXECUTED | local_summary.py |
| M-11 | Preservación de fidelidad de identificadores | reference_integrity | Identificadores exactos (SHA, tool_call_id) | NOT_EXECUTED | local_summary.py |
| M-12 | Conservación del estado final | state_consistency | Estado final consistente | NOT_EXECUTED | local_summary.py |

## Execution matrix
- Total structural: 41
- Total semantic: 12
- Executed: 0 (planned)
- Not executed: 53

## Root causes of gaps
- Full adversarial execution requires live session runs against Hermes host, which was not performed.
- Mutation experiments require secondary copy mutations (Phase 12).
- Live-session plugin load testing (nscp_hybrid) deferred until sandbox Hermes profile creation.
