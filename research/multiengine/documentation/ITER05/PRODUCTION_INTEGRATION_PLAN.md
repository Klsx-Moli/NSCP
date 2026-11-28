PLAN DE INTEGRACION A PRODUCCION (NO EJECUTADO)
Generado: 2026-11-28T00:42:13.421796+00:00
Estado: propuesta; main, NSCP productivo y Hermes activo sin cambios.

1. Annexar los prototipos aislados como dependencias opcionales, no defaults.
2. Anadir flags de configuracion explicitos: engine=bm25|embedding|hybrid|
   compactor|deterministic; modelo_eembedding_id y version_de_indice.
3. Contrato obligatorio: todo resultado lleva classification y evidence_path.
4. Gate previo: repetir benchmarks en el SHA que se integre, no reutilizar
   estas cifras de 97ea9e9.
5. Pruebas de regresion: dedupe por identidad, RECOVERY, NaN/Inf, dimension,
   session isolation, invalidacion de modelo, rehidratacion tras reinicio.
6. Medir VRAM real de reranker y compactor antes de habilitar -ngl > 0.
7. No activar todos los motores por defecto; presupuesto y latencia gobiernan.
8. Rollback: no integrar; los prototipos viven solo en NSCP_LOCAL_EVIDENCE.
