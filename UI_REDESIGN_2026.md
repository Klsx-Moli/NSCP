# NSCP — Rediseño de interfaz (2026-11-15)

Este documento registra la auditoría, el sistema de diseño resultante, las
decisiones de layout y la evidencia de verificación. Sustituye a los informes
previos de rediseño como referencia vigente.

---

## 1. Auditoría (estado encontrado)

Método: lectura del 100 % de `src/npsc_gui/**`, introspección del árbol real de
widgets con QPA de Windows, capturas propias y contraste calculado con WCAG 2.1.
Línea base de tests: **405 passed, 1 skipped**.

### Bugs visuales encontrados (no documentados antes)

| # | Defecto | Causa raíz | Evidencia |
|---|---|---|---|
| 1 | Marcos tipo “pestaña” falsos bajo el header en todas las pantallas | `QWidget { background }` global pintaba un rectángulo opaco detrás de cada `QLabel` | zoom del header a 3× y muestreo de píxeles en y=48 |
| 2 | El glifo de marca “N” se pintaba sin fondo azul | `QFrame#Header QLabel` tenía mayor especificidad que `QLabel#BrandGlyph` | píxeles `#0c0f13` dentro del glifo |
| 3 | Iconos de las tool cards como cuadros vacíos (tofu) | glifos `⌕ ⎘` dependían de la fuente y del fallback | captura del dashboard |
| 4 | Chips de estado con esquinas rectas | `border-radius: 999px` no se aplica en Qt | comparación 999px vs 12px |
| 5 | Doble anillo de foco | `QProxyStyle` dibujaba foco sobre controles que ya lo tenían por QSS | captura del botón primario |
| 6 | Durante la compilación no había progreso ni cancelación accionable | ambos vivían en la página de inicio, oculta tras cambiar a resultado | `simple_cancel_btn.isVisible() == False` en pleno trabajo |
| 7 | Estado de error conservaba métricas de la compilación anterior (93/100) | no se limpiaban los labels al fallar | captura de error |
| 8 | Cambio de idioma mapeaba `0→es`, resto→`en`; sin retraducción de la UI | handler truncado | 7 idiomas seleccionables, 2 efectivos |
| 9 | `motion_enabled()` devolvía “reducir movimiento” | lógica invertida | animaciones activas solo al pedir reducirlas |
| 10 | Filas alternas azul brillante en Historial/Plantillas | `setAlternatingRowColors(True)` con selección de acento | captura de Versiones |

### Problemas de jerarquía y densidad

- El resultado era un `QLabel` + 4 áreas de texto: no parecía el producto.
- El dashboard de métricas aparecía con ceros antes de compilar.
- Resultados acumulaba 5 botones y 10 pestañas con el mismo peso visual.
- Mezcla de 11 tamaños de fuente y 38 colores únicos en el QSS anterior.
- Márgenes inconsistentes (40/28/16/10/8/6/4) sin retícula.

### Estados ausentes

Sin estado indeterminado real, sin cancelación visible en la vista de trabajo,
sin “resultado parcial” diferenciado, sin vacío explicativo en Resultados y sin
preferencia de movimiento reducido aplicada de verdad.

---

## 2. Sistema de diseño

### Tokens (`src/npsc_gui/design/tokens.py`)

- **Espaciado:** 4 / 8 / 12 / 16 / 24 / 32 / 48.
- **Radios:** 3 (dot) / 6 (sm) / 10 (md) / 14 (lg) / 20 (xl) / 13 (pill).
  El radio de píldora debe ser ≤ altura/2: Qt ignora valores desproporcionados.
- **Bordes:** 1 px; foco 2 px.
- **Tipografía:** `Segoe UI Variable Text` (presente en Windows 10/11),
  display 24/600, título 16/600, sección 11/600 con tracking, cuerpo 13/400,
  etiqueta 12/500, caption 11/400, código 12 mono.
  QSS de Qt **no** soporta `text-transform` ni `letter-spacing`: no se usan para
  comunicar jerarquía.
- **Paleta oscura:** base `#0A0C0F`, superficie `#0F1216`, elevada `#141920`,
  input `#0C1014`, borde `#262E38`, texto `#EDF1F5`/`#AEB7C2`/`#8C96A3`,
  acento `#1B6096` con marca `#5FC8F2`, éxito `#3CC98C`, aviso `#E7B04A`,
  error `#F07287`.
- **Contraste:** texto ≥ 8.6:1 sobre cualquier superficie; bordes interactivos
  ≥ 3:1; blanco sobre acento 5.4:1. Verificado en tests.
- **Motion:** 0 / 120 / 200 / 280 / 450 ms con curvas de entrada, salida,
  estándar y rápida.
- **Métricas:** header 56, sidebar 216 (rail 56), statusbar 26, botón 32/40,
  editor mínimo 190, rail 312.

### Componentes (`src/npsc_gui/components/`)

| Componente | Estados implementados |
|---|---|
| `PrimaryButton` | default, hover, pressed, disabled, **loading** (bloquea clics y conserva ancho) |
| `SecondaryButton` | default, hover, pressed, disabled |
| `GhostButton` | default, hover, pressed, disabled |
| `IconButton` | default, hover, pressed, disabled, tooltip accesible |
| `Card` | superficie con borde sutil y jerarquía interna |
| `StatusChip` | idle, ready, working, success, warning, error |
| `MetricTile` | valor + caption + semántica de color |
| `ResultCard` | idle, working, success, warning, error, vacío |
| `ProgressIndicator` | determinado + indeterminado con segmento viajero |
| `ToastHost` / `Toast` | info, success, warning, error; pila acotada a 3 |
| `InlineNotice` | info, success, warning, error + acción |
| `EmptyState` | título, explicación, acción |
| `Skeleton` | shimmer; estático si se reduce el movimiento |
| `SegmentedControl` | exclusivo, con foco |
| `Field` | default, focus, error, disabled |
| `ToolCard` | hover, focus, selected, activación por teclado |
| `PageHeader` | título + subtítulo + acciones |
| `icons` | 14 iconos vectoriales pintados con `QPainter` (nítidos a cualquier DPI) |

### Motion (`src/npsc_gui/design/motion.py`)

- `reduce_motion()` se aplica en proceso y en `QSettings`.
- Las animaciones colapsan a 0 ms en lugar de saltarse de forma inconsistente.
- `reveal()` anima **solo opacidad**: animar `geometry` de un widget gestionado
  por layout provoca solapes con sus hermanos (bug detectado y corregido).

---

## 3. Layout

- **Shell:** header 56 px con marca, subtítulo, chip de estado, conmutador de
  modo y tres acciones globales; statusbar 26 px con mensaje, perfil, modo y
  ubicación de datos.
- **Modo sencillo:** columna de contenido + rail de configuración de 312 px.
  Una sola acción primaria; acciones secundarias en texto; el resultado ocupa
  una página propia a ancho completo.
- **Resultado:** `ResultCard` con chip, título, metadatos, score, tres métricas
  reales, cuerpo monoespaciado en superficie propia y tres acciones. Debajo, el
  detalle técnico en pestañas (contenido, no navegación principal).
- **Modo experto:** sidebar de 216 px que colapsa a rail de 56 px por debajo de
  1060 px de ancho, con iconos vectoriales y tooltips.
- **Estados:** trabajo (barra + etapa + cancelar), éxito, aviso, error, cancelado
  y vacío, cada uno con mensaje y acción siguiente.

---

## 4. Verificación

- `pytest tests/` → ver `.pytest_final.log` (resultado adjunto al informe final).
- `tests/test_ui_redesign.py` añade 32 tests: tokens, invariantes del QSS,
  estados de componentes, loading, indeterminado, ResultCard, iconos, motion,
  splash e i18n en los 7 idiomas.
- Capturas reales en `screenshots/final/`:

| Archivo | Estado |
|---|---|
| `00_splash.png` | splash de marca |
| `01_home_idle.png` | inicio |
| `02_home_invalid.png` | validación con error accionable |
| `30_working_real.png` | compilación en curso con progreso y cancelar |
| `22_success.png` | éxito |
| `05_result_error.png` | error accionable |
| `31_canceled_real.png` | cancelación |
| `07_home_light.png`, `09_result_success_light.png` | tema claro |
| `11_language_en.png`, `11_language_de.png`, `11_language_zh.png` | idioma |
| `12_home_dpi150.png` | DPI 150 % (1924×1163 con DPR 1.875) |
| `13_home_narrow.png`, `15_expert_collapsed.png` | ventana estrecha |
| `10_expert_*.png` | las 10 páginas del modo experto |

- Modo portable verificado: con el marcador `portable/`, configuración y datos
  se escriben en `portable_data/`.
- Build: ver sección de entrega final.

---

## 5. Fuera de alcance / límites conocidos

- No se añadió funcionalidad nueva de compilación.
- El contenido de las pestañas técnicas sigue siendo texto plano por diseño:
  son salidas de auditoría, no la superficie principal.
- La tipografía usa Segoe UI Variable del sistema; no se empaqueta una fuente
  externa para no inflar el binario.
