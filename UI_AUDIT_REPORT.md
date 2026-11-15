# NSCP — Auditoría visual y propuesta de rediseño (2026-11-08)

Estado auditado: working tree con 43 modificados / 7 untracked (sin commit).
Base verificada: `7200870 Snapshot inicial importado desde backup local 2026-09-26`.
Suite baseline: **312 passed, 10 subtests passed** (`pytest tests/ -q --basetemp=...`), 201 s.

Método y límites (honesto):
- Se leyó el 100 % del código de UI (`src/npsc_gui/**`, 6206 LOC).
- Se capturaron 12 pantallas reales en Windows con QPA nativa y se analizaron con
  **UI Binder** (heurístico OpenCV local, offline) para geometría y jerarquía.
- El analizador visual por IA (`vision_analyze`) y el backend `zai-vision` no estaban
  operativos en esta sesión (connection error / HTTP 429 "Insufficient balance").
  Por tanto **no hay juicio estético automatizado de las capturas**; el diagnóstico
  visual se apoya en geometría medida, métricas de contraste y lectura del código.
- Los scripts de evidencia quedan en `scripts/_ui_audit_*.py` y las capturas en
  `screenshots/audit_before/`.

---

## 1. Inventario real

### 1.1 Shell
| Elemento | Especificación | Evidencia |
|---|---|---|
| Header | `QFrame#Header`, 44 px fijos | `main_window.py:255-319` |
| StatusBar | `QFrame#StatusBar`, 24 px | `main_window.py:697-723` |
| Progress strip | `QProgressBar` 3 px, global | `main_window.py:243-248` |
| Mode stack | `QStackedWidget` 2 modos | `main_window.py:237-240` |

Controles del header: brand `QLabel` "N", título, separador, subtítulo, versión,
`StatusChip`, `ModeToggleBtn`, y **3** `HeaderIconButton` ("i", "⚙", "?").

### 1.2 Modo sencillo (2 vistas)
**Home** (6 botones, 1 editor, 4 combos, 2 checks, 1 dashboard, 1 anillo):
`SimpleTitle`, `SimpleSubtitle`, `SimplePromptLabel`, `QPlainTextEdit`,
`Perfil:` + `SimpleProfileValue`, `SimpleAdvToggle`, `SimpleAdvFrame` (oculto),
`PrimaryButton` "COMPILAR PROMPT", `Cargar ejemplo`, `Limpiar`, `Cancelar`
(oculto), `Historial`, `¿Necesitas control técnico completo?`,
`HealthDashboard` (4 `MetricPill`) **visible en idle**, `ScanRing` 52 px (oculto),
`QProgressBar` (oculto).

**Resultado**: `SimpleResultHeader` (`QLabel`), 4 pestañas `QPlainTextEdit`
("Prompt optimizado", "Informe", "Validación", "Preguntas abiertas"),
`PrimaryButton` "COPIAR PROMPT", `Guardar`, `Nueva compilación`, 3 `QLabel` y
`Abrir carpeta`.

### 1.3 Modo extremo (sidebar + 10 páginas)
Sidebar 190 px fijos, 4 grupos (`Principal`, `Herramientas`, `Historial`, `Sistema`)
y 10 `NavItem`.

| Página | Contenido principal |
|---|---|
| `resumen` | `ScanRing` 140, `PrimaryButton`, `HeroStatus`, prompt, 3 combos, 2 contadores, 4 botones, `HealthDashboard` **visible en idle**, 3 `ToolCard` |
| `compilar` | 5 campos, prompt espejo, 7 botones, `QProgressBar` |
| `resultados` | **5 botones + 8 `QToolButton` de ayuda + 10 pestañas** (23 controles) |
| `validacion` | 1 `QTextEdit` |
| `perfiles` | 1 `QTextEdit` estático |
| `glosario` | búsqueda, categoría, lista, detalle, botón |
| `plantillas` | `build_template_page` |
| `historial` | `build_history_page` |
| `configuracion` | 3 combos, 1 etiqueta, 1 botón |
| `avanzado` | `AdvancedModePage` |

### 1.4 Diálogos y feedback
`AboutDialog`, `ExportPreviewDialog`, `QMessageBox` (**18 usos**), diálogo de
variables, diálogos de archivo. No existe `Toast`, `InlineNotice`, `EmptyState`,
`Skeleton` ni `SegmentedControl`.

### 1.5 Componentes
Vivos: `ScanRing`, `HealthDashboard`/`MetricPill`, `StatusChip`, `ToolCard`,
`NavGroup`/`NavItem`.
**Muertos (no instanciados):** `ResultCard` (`result_card.py`), `CircleIndicator`
(`circle_indicator.py`). Solo quedan sus selectores QSS en `theme.py:431-512`.

---

## 2. Problemas por categoría (con evidencia)

### 2.1 Jerarquía visual
- **H1 — El dashboard de métricas aparece en idle.** `simple_health` y
  `extreme_health` están en el layout sin ocultar. Verificado:
  `simple_health visible=True` y `extreme_health visible=True` con el
  `resumen` activo y **sin ninguna compilación**. En pantalla se ven 4 pastillas
  con `—/100, 0, 0, 0` debajo del botón principal. UI Binder detectó en la home
  4 paneles iguales de 415×81 px en y=905 (`01_simple_home_idle.ui.json`).
  Competencia directa con la acción primaria.
- **H2 — El resultado no es el centro visual en modo sencillo.** Es un `QLabel`
  de una línea + 4 `QPlainTextEdit` en pestañas. No existe ninguna `ResultCard`
  instanciada. El resultado parece texto pegado.
- **H3 — Página de resultados saturada.** 5 botones + 8 botones de ayuda +
  10 pestañas = 23 controles; los 5 botones tienen peso visual idéntico.
- **H4 — El header compite consigo mismo.** Identidad (brand + título +
  subtítulo + versión) + chip de estado + toggle + 3 iconos en 44 px.

### 2.2 Densidad y alineación
- **D1 — 10 tamaños de tab con textos largos** ("Restricciones y origen") en
  `QTabBar`: caben, pero la barra no tiene agrupación ni scroll visible.
- **D2 — Modo sencillo:** 40 px de margen, 16 px de espaciado, título de 18 px +
  subtítulo + etiqueta antes del editor. Hay aire arriba y no abajo.
- **D3 — 139 literales de tamaño** (`px`/`pt`) y **77 ocurrencias de color hex**
  (38 únicos) en `theme.py`. No existe una retícula aplicada: los márgenes son
  40/28/16/10/8/6/4 según el constructor.

### 2.3 Feedback
- **F1 — No hay feedback no bloqueante.** Todo confirma en la barra de estado,
  con `text_muted` a **3.44:1** de contraste.
- **F2 — 18 `QMessageBox`** para errores, variables, guardado y avisos:
  bloquean la interacción.
- **F3 — "Copiar" no confirma en el botón.** Solo cambia el texto de estado.
- **F4 — Progreso solo determinista.** No hay indicador indeterminado ni
  skeletons.

### 2.4 Estados
- **S1 — Sin `EmptyState`.** Resultados/validación vacíos no explican qué hacer.
- **S2 — Sin estado "configuración incompleta".**
- **S3 — Sin estado "resultado parcial"** diferenciado de éxito.
- **S4 — Sin estado "cancelado"** con mensaje y acción siguiente.
- **S5 — Transiciones de vista por corte seco** (`setCurrentIndex`), sin fade ni
  desplazamiento.
- **S6 — `ToolCard` no es focuseable** y se activa con
  `mousePressEvent = lambda` (`main_window.py:908-910`): no responde a teclado,
  no tiene `pressed`/`selected` y no expone estado accesible.
- **S7 — Splash:** GIF de **200×200 px, 12 frames, 3532 bytes**; 1500 ms fijos;
  **no se puede cerrar con clic ni con Escape**; la ventana principal entra con
  `QGraphicsOpacityEffect` + `QPropertyAnimation` a 400 ms (`main.py:35-41`),
  efecto que el propio brief marca como riesgo.

### 2.5 Tipografía y contraste (medido)
- **T1 — Inter no existe.** `QFontDatabase` nativo: `Inter MISSING`,
  `Segoe UI FOUND`. El QSS declara `Inter, "Noto Sans", "Segoe UI"` y **cae
  siempre a Segoe UI**. La tipografía "premium" declarada no es la que se pinta.
- **T2 — 11 tamaños distintos** en QSS: 9.5, 10, 10.5, 11, 11.5, 12, 13, 14,
  18, 20, 28. Mezcla de `pt` y `px`.
- **T3 — Contraste por debajo de WCAG AA:**
  | Par | Ratio | Veredicto |
  |---|---|---|
  | `text_muted` sobre `bg_card` | 3.44:1 | FAIL (texto normal) |
  | `text_on_accent` sobre `accent` | 3.73:1 | FAIL (11.5 px bold) |
  | `state_error` sobre `bg_card` | 4.38:1 | FAIL (justo) |
  | `border_subtle` vs `bg_card` | 1.48:1 | FAIL (no-texto 3:1) |
  | `border_input` vs `bg_card` | 2.10:1 | FAIL (no-texto 3:1) |
  | `text_primary` sobre `bg_card` | 14.02:1 | OK |
  | `text_secondary` sobre `bg_card` | 7.07:1 | OK |
- **T4 — El acento #2B8BC8 con blanco** solo sirve para texto grande; el botón
  primario usa 11.5 px bold → no cumple AA.

### 2.6 Interacción, DPI y rendimiento
- **I1 — Sin atajos de teclado para la navegación** del sidebar (solo Ctrl+M para
  modo, Ctrl+Retorno para compilar).
- **I2 — Sin preferencia "reducir animaciones".**
- **I3 — Sin manejo explícito de DPI** (Qt6 aplica su política por defecto; no
  hay `setHighDpiScaleFactorRoundingPolicy` ni prueba a 125 %/150 %).
- **I4 — `ScanRing` repinta a 50 ms** con `QTimer` mientras escanea (20 fps de
  repintado completo). Aceptable, pero sin guardia de movimiento reducido.
- **I5 — Foco inicial:** el header recibe el foco al abrir; se corrigió con un
  watcher de 20 ms (`main_window.py:167-223`). Solución frágil, no estructural.

### 2.7 Calidad de código
- **CO1 — `main_window.py`: 2410 LOC (39 % del GUI).**
- **CO2 — `theme.py`: 1014 LOC, 131 entradas de selector y 6 duplicados:**
  `QFrame#NPSCCircle` (2×), `QFrame#NPSCMetricPill` (2×),
  `QFrame#NPSCMetricPill:hover` (2×), `QLabel#MetricPillValue` (2×),
  `QLabel#MetricPillLabel` (2×). Las reglas tardías pisan a las tempranas.
- **CO3 — `design_tokens.py` (59 LOC, untracked) tiene 0 importadores.** Stub
  muerto: ni palette, ni estados, ni transiciones.
- **CO4 — 93 literales españoles** embebidos en `main_window.py` sin `tr()`:
  la i18n de 7 idiomas está rota en la pantalla principal.
- **CO5 — 18 `setStyleSheet` inline** (14 en `main_window.py`) + 4 componentes
  con color hardcodeado (`scan_ring.py` 16 hex, `health_dashboard.py` 6).
- **CO6 — Sin tests de UI** para tokens, componentes o estados (solo
  `test_compilation_profiles.py` menciona `theme`).

---

## 3. Top 10 mejoras por impacto percibido (before → after)

1. **Ocultar el dashboard de métricas en idle** → before: 4 pastillas con ceros
   bajo el botón; after: home limpia, una sola acción primaria.
2. **ResultCard premium en modo sencillo** → before: `QLabel` + 4 áreas de texto;
   after: tarjeta con score, metadatos, validación y acciones.
3. **Tokens reales y únicos** → before: 139 tamaños + 77 colores + 6 selectores
   duplicados; after: todo el QSS generado desde tokens.
4. **Tipografía real** → before: Inter inexistente → Segoe UI, 11 tamaños;
   after: fuente declarada y empaquetada (o Segoe UI Variable), escala de 6.
5. **Contraste AA** → before: muted 3.44:1, on-accent 3.73:1, error 4.38:1;
   after: ≥4.5:1 texto y ≥3:1 bordes.
6. **Splash integrado** → before: GIF 200×200 3.5 KB, 1500 ms, sin skip;
   after: marca vectorial ≤1.2 s, skip con clic/Escape, salida con fundido.
7. **Feedback no bloqueante** → before: 18 `QMessageBox` + barra de estado;
   after: `Toast`/`InlineNotice` + estados en el propio botón.
8. **Estados completos** → before: sin empty/indeterminado/parcial/cancelado;
   after:EmptyState, Progress indeterminado, partial, cancelado.
9. **Ordenar resultados** → before: 23 controles; after: primarias/secundarias
   separadas, tabs agrupadas, ayuda en un solo punto.
10. **Componentes con estados y accesibilidad reales** → before: `ToolCard` sin
    teclado y colores inline; after: default/hover/pressed/focus/selected/
    disabled/loading/error/success en todos.

---

## 4. Propuesta de sistema de diseño

### 4.1 Tokens (`src/npsc_gui/design/tokens.py`)
- **Spacing:** 4 / 8 / 12 / 16 / 24 / 32 / 48.
- **Radius:** 6 controles pequeños, 10 inputs y chips, 14 tarjetas, 20 superficies.
- **Borde:** 1 px `border.default`; 2 px `border.focus`.
- **Sombra:** `0 1px 2px rgba(0,0,0,.20)` y `0 4px 12px rgba(0,0,0,.24)`.
- **Tipografía (escala de 6):** display 22/700, title 17/650, section 13/650
  mayúsculas + tracking, body 13/400, label 12/500, caption 11/400, code 12 mono.
- **Paleta oscura (ajustada a AA):** base `#0B0D10`, surface `#111318`,
  raised `#171A20`, input `#12151A`, border `#262B33` / strong `#333A45`,
  text primary `#E9ECF0`, secondary `#A8AEB8`, tertiary `#8B929D`,
  accent `#2E86C8`, accent strong `#4CB8F5`, success `#35B27A`,
  warning `#DFA02C`, error `#E0576A`.
- **Motion:** instant 0, micro 120, short 200, medium 280, long 450.
  Curvas: enter `cubic-bezier(0.16,1,0.3,1)`, exit `cubic-bezier(0.4,0,1,1)`,
  layout `cubic-bezier(0.4,0,0.2,1)`, hover `cubic-bezier(0.2,0,0,1)`.
- **Estados:** default, hover, pressed, focus, selected, disabled, loading,
  error, success — cada componente los consume.

### 4.2 Componentes (`src/npsc_gui/components/`)
`PrimaryButton`, `SecondaryButton`, `IconButton`, `Card`, `StatusChip`
(idle/ready/working/success/warning/error), `ProgressIndicator`
(determinado + indeterminado), `ResultCard`, `Field` (label + control + ayuda +
error), `Toast`/`InlineNotice`, `EmptyState`, `Skeleton`, `SegmentedControl`.

### 4.3 Layout
- Shell: header 48 px, statusbar 28 px.
- Modo sencillo: columna centrada de 880 px; hero = prompt + primaria; el
  resultado pasa a ser la tarjeta protagonista.
- Modo extremo: sidebar 208 px; páginas con cabecera de sección consistente;
  resultados con acciones agrupadas.

### 4.4 Motion
`QPropertyAnimation` sobre opacity/geometry; **sin `QGraphicsOpacityEffect` en
ventanas completas**; respeto a "reducir animaciones" vía `QSettings`.

### 4.5 UIBinder (uso propuesto)
- **Medición:** geometría y jerarquía de las 12 capturas (ya ejecutado).
- **Verificación:** `analyze-project` + grafo de capacidades + orphan detector
  para demostrar que el rediseño no pierde capacidades; `bindings/verify`.
- **Diff visual:** `Visual Fidelity Score` antes/después por pantalla.
- **No** usar el export de widgets como base del rediseño: el layout exportado es
  aproximado (VBox/HBox/Grid) e incrusta el grafo de capacidades completo.

---

## 5. Plan por fases

| Fase | Contenido | Verificación |
|---|---|---|
| 0 | Puntos de restauración (snapshot git), tests baseline, inventario UIBinder | 312 tests PASS (hecho) |
| 1 | Tokens reales + `builder.py` que genera QSS desde tokens; sin tocar layout | Tests + diff QSS sin cambios visuales inesperados |
| 2 | Componentes base con estados y foco | Tests unitarios por componente |
| 3 | Layout y jerarquía: header, sidebar, espaciado, ocultar métricas en idle | Capturas antes/después + UIBinder diff |
| 4 | `ResultCard` premium (simple y extremo) | Captura + tests |
| 5 | Estados: idle/loading/success/warning/error/empty/disabled/focus/partial/cancel + motion | Captura por estado + tests |
| 6 | Splash integrado y saltable; retirar GIF | Captura + arranque real |
| 7 | Verificación final: suite, i18n, build `.exe`, DPI, portable | Evidencia por estado |

Fuera de alcance (no tocar): lógica de compilación, i18n core, persistencia.
Adaptación permitida: solo lo necesario para i18n de literales nuevos.

---

## 6. Decisión necesaria antes de la fase 1

Ver pregunta adjunta: cómo usar UIBinder en este rediseño.
