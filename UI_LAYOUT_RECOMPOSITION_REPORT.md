# UI Layout Recomposition Report — NSCP

## 1. Historial disponible

Solo existe un commit en el repositorio (`7200870 Snapshot inicial importado desde backup local 2026-09-26`).
No hay backup `_backups/mode-redesign-20260609-025641/` en el sistema de archivos local.
No hay historial suficiente para comparar con una version anterior "mejor". Lo afirmo tal cual: no se inventa version anterior.

## 2. Causas encontradas (archivo, clase, ubicacion)

### main_window.py — _build_simple_home (antes)
- Margenes 40,28,40,28 y spacing 16 → lienzo inflado.
- Titulo grande "NeuroPrompt Semantic Compiler" (SimpleTitle, display_size-4px) duplicando el brand del header de la ventana.
- Prompt label + editor con min height 160 + stretch.
- Fila de perfil con addStretch(1) reservando espacio.
- Boton principal a ancho completo, min height 44, texto en mayusculas por QSS.
- Fila secundaria (Ejemplo/Limpiar/Cancelar/Historial) + addStretch(1).
- Fila de modo enlace + addStretch(1).
- Fila de scan ring + health dashboard con addLayout(simple_dash_row) y HealthDashboard con stretch 1 → panel vacio gigante cuando ocultos.
- Progress bar siempre presente.

### main_window.py — _build_simple_result
- Margenes 40,28,40,28, spacing 12.
- ResultCard + EmptyState + Skeleton + header + tabs + metrics + files row.

### theme/builder QSS
- QLabel#SimpleTitle con display_size-4px (grande) → jerarquia exagerada.
- Sin min-height global problematico, pero los paddings acumulados inflan.

### Comportamiento al redimensionar
- setMinimumSize(960, 640) en MainWindow (linea 157) → oculta problemas en ventanas menores.
- Editor con stretch 1 correcto, pero los contenedores ocultos (scan/health) seguian reservando espacio via addLayout.

## 3. Cambios concretos de layout

Archivo: src/npsc_gui/main_window.py, metodo _build_simple_home (recompuesto completo):
- Margenes reducidos a 20,12,20,12; spacing 8.
- Eliminado el titulo grande "NeuroPrompt Semantic Compiler".
- Subtitulo convertido en ayuda breve secundaria (Muted).
- Toolbar del editor: etiqueta + Ejemplo/Limpiar/Cancelar/Historial en una fila compacta.
- Editor con min height 100 y stretch 1 (absorbe crecimiento vertical).
- Perfil: fila compacta sin stretch exagerado.
- Avanzado: margenes internos 12,6,12,6; spacing 6.
- Boton principal con ancho fijo 180px y min height 34 (proporcional, no barra completa).
- Eliminado el lienzo vacio: scan ring/health en fila compacta sin stretch del contenedor principal.
- Progress bar compacta.

Archivo: src/npsc_gui/main_window.py, metodo _build_simple_result:
- Margenes reducidos a 20,12,20,12; spacing 10.

Archivo: src/npsc_gui/main_window.py, metodo _build_simple_mode:
- Sin cambios estructurales (mantiene QStackedWidget home/result). Propuesta de dos paneles documentada abajo.

## 4. Propuesta de dos paneles (no implementada aun)

Para cuando ya existe resultado: usar un QSplitter horizontal (entrada | resultado) cuando el ancho >= ~1000px, y disposicion vertical por debajo. Conserva acceso al texto de entrada al revisar el resultado. No implementado en esta iteracion por riesgo de romper el flujo de compile/render existente; queda como siguiente bloque.

## 5. Tamanos realmente probados

Capturas generadas (screenshots/):
- simple_900x650.png (ventana 900x650, captura 1200x813 por DPI 1.33)
- simple_1100x750.png (1375x938)
- simple_1400x900.png (1750x1055)
- simple_adv_open.png (1375x938, opciones avanzadas abiertas)
- simple_result.png (1375x938, resultado generado)
- verify_final.png (1920x1055)

Escala de Windows: DPI 1.33 (125%) observado en las capturas. No se probo otro escalado; no se afirma que se probo.

## 6. Verificacion

- Tests test_i18n + test_gui_b9: 10/10 PASS.
- Build .exe: dist/NSCP/NSCP.exe (2026-11-08 23:37:03), arranca estable (exit 124 = timeout esperado).
- Suite completa previa: 405 passed (no se re-ejecuto tras este bloque; cambios son de layout, no de logica).

## 7. Pendientes y limitaciones

- Dos paneles entrada/resultado no implementados (propuesto).
- i18n de textos estaticos largos (perfiles, resultados) pendiente.
- Agrupacion de 5 botones de ayuda en menu pendiente.
- Capturas no inspeccionadas visualmente por el agente (modelo actual no soporta vision); la aceptacion visual corresponde al usuario.
- No se declaro premium ni objetivo logrado.

---
## Actualizacion v2 (dos paneles)
_build_simple_mode convertido a QSplitter horizontal (home | result). Result oculto hasta compilar; al compilar se muestra junto al input (sizes [400,700]). Min width 300 en result. Conserva acceso al texto de entrada al revisar resultado. Capturas: split_900x650.png, split_1100x750.png, split_1400x900.png, split_adv_open.png, split_result.png.
