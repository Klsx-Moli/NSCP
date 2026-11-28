"""Main window — workflow composition on top of the design system.

Structure:
- ``chrome`` owns the header, sidebar and status bar.
- ``components`` owns every visual primitive (buttons, cards, feedback).
- this module owns the workflow: prompt → compile → result, plus the expert
  pages that expose the compiler's technical output.

Visual hierarchy (deliberate, in this order):
1. what the user is doing now (page header),
2. the input and the configuration in use (editor + rail),
3. what the system is processing (inline status + progress),
4. the result (``ResultCard`` — the product),
5. the next action (one primary button per context).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from compilation_profiles import supported_profile_names
from field_validator import validate_compile_form
from i18n import normalize_language, set_language, tr
from model_adapter import load_model_profiles
from npsc_gui.about_dialog import AboutDialog
from npsc_gui.advanced_mode_page import AdvancedModePage
from npsc_gui.chrome import Header, Sidebar, StatusBar
from npsc_gui.components.buttons import (
    DangerButton,
    GhostButton,
    PrimaryButton,
    SecondaryButton,
)
from npsc_gui.components.cards import (
    Card,
    EmptyState,
    PageHeader,
    ResultCard,
)
from npsc_gui.components.feedback import (
    InlineNotice,
    ProgressIndicator,
    Skeleton,
    ToastHost,
)
from npsc_gui.components.health_dashboard import HealthDashboard
from npsc_gui.components.tool_card import ToolCard
from npsc_gui.controller import CompileController
from npsc_gui.design import motion
from npsc_gui.design.style import active_theme, apply_design, get_theme
from npsc_gui.export_preview import ExportPreviewDialog
from npsc_gui.glossary import (
    CATEGORIES,
    format_entry,
    get_entry,
    load_glossary,
    search_glossary,
)
from npsc_gui.help_popover import ContextHelpButton, close_context_help_popovers
from npsc_gui.history_page import build_history_page
from npsc_gui.settings import data_dir, load_settings, reset_settings, save_settings
from npsc_gui.template_page import build_template_page
from npsc_gui.tooltips import apply_tooltip, glossary_term_for, help_text
from template_manager import TemplateManager
from token_estimator import estimate_counters
from variables import extract_variables, fill_variables
from version_history import VersionHistory

ROOT = Path(__file__).resolve().parents[2]
ICON_PATH = ROOT / "assets" / "icons" / "nscp.ico"
ICON_SVG = ROOT / "assets" / "icons" / "neuro-prompt-semantic-compiler.svg"
EXAMPLE_PATH = ROOT / "examples" / "messy_prompt.txt"

MODE_SIMPLE = "simple"
MODE_EXTREME = "extreme"

LANGUAGES = ("es", "en", "fr", "de", "ru", "ko", "zh")

PROFILES = supported_profile_names()
MODELS = list(load_model_profiles().keys())

LEVEL_KEYS = (
    ("level.auto", "profile_default"),
    ("level.safe", "safe"),
    ("level.balanced", "balanced"),
    ("level.compact", "aggressive"),
    ("level.all", "all"),
)
PRIVACY_KEYS = (
    ("privacy.full_original", "full_original"),
    ("privacy.hash_only", "hash_only"),
    ("privacy.redacted", "redacted_preview"),
)


def _levels() -> tuple[tuple[str, str], ...]:
    return tuple((tr(key), value) for key, value in LEVEL_KEYS)


def _privacy_modes() -> tuple[tuple[str, str], ...]:
    return tuple((tr(key), value) for key, value in PRIVACY_KEYS)


def _fill_combo(combo: QComboBox, items: tuple[tuple[str, str], ...]) -> None:
    """(Re)label a combo while keeping the current data value selected."""
    current = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    for label, value in items:
        combo.addItem(label, value)
    for index in range(combo.count()):
        if combo.itemData(index) == current:
            combo.setCurrentIndex(index)
            break
    combo.blockSignals(False)


PROFILE_DEFINITIONS = (
    ("AUTO", "profile.def.auto"),
    ("FAST", "profile.def.fast"),
    ("STANDARD", "profile.def.standard"),
    ("ADVANCED", "profile.def.advanced"),
    ("ROP", "profile.def.rop"),
    ("RESEARCH_MAX", "profile.def.research"),
)


class CompileWorker(QObject):
    """Runs one compilation off the UI thread and reports coarse stages."""

    progress = Signal(int, str)
    finished = Signal(dict)
    failed = Signal(str)
    canceled = Signal()

    def __init__(self, controller: CompileController, request: dict) -> None:
        super().__init__()
        self.controller = controller
        self.request = request
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True

    @Slot()
    def run(self) -> None:
        stages = [
            (10, "Analizando intención"),
            (25, "Detectando restricciones"),
            (40, "Seleccionando perfil"),
            (55, "Generando IR semántica"),
            (70, "Compilando NSL y prompt"),
            (85, "Validando preservación"),
            (95, "Preparando el resultado"),
        ]
        try:
            for value, label in stages[:4]:
                if self.cancel_requested:
                    self.canceled.emit()
                    return
                self.progress.emit(value, label)
            if self.cancel_requested:
                self.canceled.emit()
                return
            result = self.controller.compile(**self.request)
            if self.cancel_requested:
                self.canceled.emit()
                return
            for value, label in stages[4:]:
                if self.cancel_requested:
                    self.canceled.emit()
                    return
                self.progress.emit(value, label)
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user verbatim
            self.failed.emit(str(exc))


def _combo(items) -> QComboBox:
    combo = QComboBox()
    for label, value in items:
        combo.addItem(label, value)
    return combo


def _label(text: str, name: str = "Muted") -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    return widget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        set_language(str(self.settings.get("language", "es")))
        self.controller = CompileController()
        self.result: dict | None = None
        self.cancel_requested = False
        self.worker_thread: QThread | None = None
        self.worker: CompileWorker | None = None
        self.last_saved_dir: Path | None = None
        self.pages: dict[str, QWidget] = {}
        self.nav_items: dict[str, Any] = {}
        self.section_help_buttons: dict[str, ContextHelpButton] = {}
        self.option_help_buttons: dict[str, ContextHelpButton] = {}

        self._variable_values: dict[str, str] = {}
        self._version_history = VersionHistory()
        self._template_manager = TemplateManager()
        self._current_mode: str = MODE_SIMPLE
        self._advanced_sections_dirty = False
        self._warnings_acknowledged = False
        self._last_stage = ""

        self._counters_debounce_timer = QTimer(self)
        self._counters_debounce_timer.setSingleShot(True)
        self._counters_debounce_timer.setInterval(150)
        self._counters_debounce_timer.timeout.connect(self._update_counters)

        self.setObjectName("NPSCMainWindow")
        self.setWindowTitle("NeuroPrompt Semantic Compiler")
        self.setMinimumSize(900, 620)
        self.resize(int(self.settings["window_width"]), int(self.settings["window_height"]))
        screen = QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(
                area.x() + (area.width() - self.width()) // 2,
                area.y() + (area.height() - self.height()) // 2,
            )
        icon = ICON_PATH if ICON_PATH.exists() else ICON_SVG
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        self._build_ui()
        self._bind_shortcuts()
        self._restore_settings()
        self._update_counters()
        self.header.set_state("ready", tr("status.ready"))
        self.status_bar.set_message(tr("status.ready"), "ready")
        self._retranslate_ui()

    # ─── Layout ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("RootSurface")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = Header(self)
        self.header.mode_toggle_requested.connect(self._toggle_mode)
        self.header.settings_requested.connect(self._open_settings)
        self.header.help_requested.connect(self._open_help)
        self.header.about_requested.connect(self._open_about)
        self.header.context_requested.connect(self._open_context_workbench)
        layout.addWidget(self.header)

        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self._build_simple_mode())
        self.mode_stack.addWidget(self._build_extreme_mode())
        layout.addWidget(self.mode_stack, 1)

        self.status_bar = StatusBar(self)
        self.status_mode = self.status_bar.mode
        layout.addWidget(self.status_bar)

        self.setCentralWidget(root)

        self._toast = ToastHost(self)
        self.toast_host = self._toast

    # ─── Simple mode ───────────────────────────────────────────────

    def _build_simple_mode(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.simple_stack = QStackedWidget()
        self.simple_home_panel = self._build_simple_home()
        self.simple_result_panel = self._build_simple_result()
        self.simple_stack.addWidget(self.simple_home_panel)
        self.simple_stack.addWidget(self.simple_result_panel)
        layout.addWidget(self.simple_stack, 1)
        return container

    def _scroll_page(self) -> tuple[QScrollArea, QVBoxLayout]:
        """A vertically scrollable page with a centred content column."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("RootSurface")
        layout = QVBoxLayout(content)
        margin = active_theme().spacing
        layout.setContentsMargins(margin.xxl, margin.xl, margin.xxl, margin.xl)
        layout.setSpacing(margin.lg)
        scroll.setWidget(content)
        return scroll, layout

    def _build_simple_home(self) -> QWidget:
        page, layout = self._scroll_page()

        self.home_header = PageHeader()
        layout.addWidget(self.home_header)

        body = QHBoxLayout()
        body.setSpacing(active_theme().spacing.lg)

        # ── editor card ───────────────────────────────────────────────
        editor_card = Card()
        editor = editor_card.content()
        editor.setSpacing(active_theme().spacing.md)

        prompt_row = QHBoxLayout()
        prompt_row.setSpacing(active_theme().spacing.sm)
        self.simple_prompt_label = _label(tr("home.input_label"), "FieldLabel")
        prompt_row.addWidget(self.simple_prompt_label)
        prompt_row.addStretch(1)

        self.example_button = GhostButton(tr("simple.button.example"))
        self.example_button.clicked.connect(self.load_example)
        apply_tooltip(self.example_button, "example")
        self.clear_button = GhostButton(tr("simple.button.clear"))
        self.clear_button.clicked.connect(self.new_prompt)
        apply_tooltip(self.clear_button, "reset")
        self.history_button = GhostButton(tr("simple.button.history"))
        self.history_button.clicked.connect(self._show_simple_history)
        prompt_row.addWidget(self.example_button)
        prompt_row.addWidget(self.clear_button)
        prompt_row.addWidget(self.history_button)
        editor.addLayout(prompt_row)

        self.simple_prompt_edit = QPlainTextEdit()
        self.simple_prompt_edit.setPlaceholderText(tr("simple.placeholder"))
        self.simple_prompt_edit.setMinimumHeight(active_theme().metrics.editor_min_height)
        self.simple_prompt_edit.textChanged.connect(self._on_simple_prompt_changed)
        self.simple_prompt_edit.setAccessibleName(tr("home.input_label"))
        editor.addWidget(self.simple_prompt_edit, 1)

        counters = QHBoxLayout()
        counters.setSpacing(active_theme().spacing.md)
        self.simple_char_label = _label("", "MicroLabel")
        self.simple_token_label = _label("", "MicroLabel")
        self.simple_profile_hint = _label(tr("profile.auto_recommended"), "SimpleProfileValue")
        counters.addWidget(self.simple_char_label)
        counters.addWidget(self.simple_token_label)
        counters.addStretch(1)
        counters.addWidget(self.simple_profile_hint)
        editor.addLayout(counters)
        self.simple_help_text = _label(tr("home.input_help"), "MicroLabel")
        self.simple_help_text.setWordWrap(True)
        editor.addWidget(self.simple_help_text)

        self.simple_inline_notice = InlineNotice("", "error")
        self.simple_inline_notice.hide()
        editor.addWidget(self.simple_inline_notice)

        self.simple_progress = ProgressIndicator()
        self.simple_progress.setVisible(False)
        editor.addWidget(self.simple_progress)

        working_row = QHBoxLayout()
        working_row.setSpacing(active_theme().spacing.sm)
        self.simple_stage_label = _label("", "MicroLabel")
        working_row.addWidget(self.simple_stage_label, 1)
        self.simple_cancel_btn = DangerButton(tr("simple.button.cancel"))
        self.simple_cancel_btn.clicked.connect(self.cancel_compile)
        apply_tooltip(self.simple_cancel_btn, "cancel")
        self.simple_cancel_btn.setVisible(False)
        apply_tooltip(self.simple_cancel_btn, "cancel")
        working_row.addWidget(self.simple_cancel_btn)
        editor.addLayout(working_row)

        actions = QHBoxLayout()
        actions.setSpacing(active_theme().spacing.sm)
        self.simple_compile_btn = PrimaryButton(tr("simple.button.compile"))
        self.simple_compile_btn.clicked.connect(self.compile_current)
        self.simple_compile_btn.setAccessibleName(tr("simple.button.compile"))
        apply_tooltip(self.simple_compile_btn, "compile")
        actions.addWidget(self.simple_compile_btn)
        self.simple_shortcut_hint = _label("Ctrl + Enter", "MicroLabel")
        actions.addWidget(self.simple_shortcut_hint)
        actions.addStretch(1)
        editor.addLayout(actions)

        body.addWidget(editor_card, 1)

        # ── configuration rail ────────────────────────────────────────
        self.home_rail = Card()
        rail = self.home_rail.content()
        rail.setSpacing(active_theme().spacing.md)
        self.rail_title = _label(tr("home.rail.title"), "ResultTitle")
        rail.addWidget(self.rail_title)
        self.rail_help = _label(tr("home.rail.help"), "MicroLabel")
        self.rail_help.setWordWrap(True)
        rail.addWidget(self.rail_help)

        self.rail_profile_label = _label(tr("simple.label.profile"), "FieldLabel")
        rail.addWidget(self.rail_profile_label)
        self.simple_profile_combo = QComboBox()
        self.simple_profile_combo.addItems(PROFILES)
        self.simple_profile_combo.currentTextChanged.connect(self._on_simple_profile_combo_changed)
        rail.addWidget(self.simple_profile_combo)

        self.rail_profile_help = _label(tr("home.rail.profile_help"), "MicroLabel")
        self.rail_profile_help.setWordWrap(True)
        rail.addWidget(self.rail_profile_help)

        self.rail_model_label = _label(tr("simple.label.model"), "FieldLabel")
        rail.addWidget(self.rail_model_label)
        self.simple_target_combo = QComboBox()
        self.simple_target_combo.addItems(MODELS)
        self.simple_target_combo.currentTextChanged.connect(self._on_target_changed)
        rail.addWidget(self.simple_target_combo)

        self.rail_level_label = _label(tr("simple.label.level"), "FieldLabel")
        rail.addWidget(self.rail_level_label)
        self.simple_level_combo = _combo(_levels())
        rail.addWidget(self.simple_level_combo)

        self.rail_privacy_label = _label(tr("simple.label.privacy"), "FieldLabel")
        rail.addWidget(self.rail_privacy_label)
        self.simple_privacy_combo = _combo(_privacy_modes())
        rail.addWidget(self.simple_privacy_combo)

        self.simple_strict_check = QCheckBox(tr("simple.check.strict"))
        rail.addWidget(self.simple_strict_check)
        self.simple_preserve_check = QCheckBox(tr("simple.check.preserve"))
        self.simple_preserve_check.setChecked(True)
        rail.addWidget(self.simple_preserve_check)
        rail.addStretch(1)

        self.home_rail.setFixedWidth(active_theme().metrics.rail_width)
        body.addWidget(self.home_rail, 0)

        layout.addLayout(body, 1)
        return page

    # ─── Simple result ─────────────────────────────────────────────

    def _build_simple_result(self) -> QWidget:
        page, layout = self._scroll_page()
        layout.setSpacing(active_theme().spacing.lg)

        self.result_header = PageHeader(tr("result.page.title"), tr("result.page.subtitle"))
        self.result_new_button = SecondaryButton(tr("result.action.new"))
        self.result_new_button.clicked.connect(self._simple_new_compilation)
        self.result_header.add_action(self.result_new_button)
        layout.addWidget(self.result_header)

        # ── live work strip: stage, real progress and a working cancel ──
        self.work_strip = QFrame()
        self.work_strip.setObjectName("NPSCPanel")
        work_layout = QVBoxLayout(self.work_strip)
        work_layout.setContentsMargins(
            active_theme().spacing.lg,
            active_theme().spacing.sm + 2,
            active_theme().spacing.lg,
            active_theme().spacing.sm + 2,
        )
        work_layout.setSpacing(active_theme().spacing.sm)
        work_top = QHBoxLayout()
        work_top.setSpacing(active_theme().spacing.sm)
        self.result_stage_label = _label("", "FieldLabel")
        work_top.addWidget(self.result_stage_label, 1)
        self.result_cancel_btn = DangerButton(tr("simple.button.cancel"))
        self.result_cancel_btn.setProperty("compact", "true")
        self.result_cancel_btn.clicked.connect(self.cancel_compile)
        apply_tooltip(self.result_cancel_btn, "cancel")
        work_top.addWidget(self.result_cancel_btn, 0)
        work_layout.addLayout(work_top)
        self.result_progress = ProgressIndicator()
        work_layout.addWidget(self.result_progress)
        layout.addWidget(self.work_strip)
        self.work_strip.hide()

        self.simple_result_card = ResultCard()
        self.simple_result_card.setMinimumHeight(420)
        self.simple_result_card.copy_button.clicked.connect(self.copy_recommended)
        self.simple_result_card.new_button.clicked.connect(self._simple_new_compilation)
        self.simple_result_card.save_button.clicked.connect(self.save_all)
        layout.addWidget(self.simple_result_card, 1)

        self.simple_empty_state = EmptyState()
        self.simple_empty_state.hide()
        layout.addWidget(self.simple_empty_state)

        self.simple_skeleton = Skeleton(lines=5)
        self.simple_skeleton.hide()
        layout.addWidget(self.simple_skeleton)

        self.simple_result_header = _label("", "MicroLabel")
        self.simple_result_header.setVisible(False)
        layout.addWidget(self.simple_result_header)

        # ── metrics: only real values, shown after a compilation ──────
        self.simple_metrics_panel = QFrame()
        self.simple_metrics_panel.setObjectName("NPSCPanel")
        metrics_layout = QVBoxLayout(self.simple_metrics_panel)
        metrics_layout.setContentsMargins(
            active_theme().spacing.lg,
            active_theme().spacing.md,
            active_theme().spacing.lg,
            active_theme().spacing.md,
        )
        metrics_layout.setSpacing(active_theme().spacing.sm)
        self.simple_health = HealthDashboard()
        metrics_layout.addWidget(self.simple_health)
        layout.addWidget(self.simple_metrics_panel)
        self.simple_metrics_panel.hide()

        # ── detail tabs: the same result, in technical views ──────────
        self.simple_detail_card = Card(
            tr("result.detail.title"), tr("result.detail.help")
        )
        detail = self.simple_detail_card.content()
        self.simple_tabs = QTabWidget()
        self.simple_optimized_tab = QPlainTextEdit()
        self.simple_optimized_tab.setReadOnly(True)
        self.simple_tabs.addTab(self.simple_optimized_tab, tr("result.tab.optimized"))

        self.simple_report_tab = QPlainTextEdit()
        self.simple_report_tab.setReadOnly(True)
        self.simple_tabs.addTab(self.simple_report_tab, tr("result.tab.report"))

        self.simple_validation_tab = QPlainTextEdit()
        self.simple_validation_tab.setReadOnly(True)
        self.simple_tabs.addTab(self.simple_validation_tab, tr("result.tab.validation"))

        self.simple_questions_tab = QPlainTextEdit()
        self.simple_questions_tab.setReadOnly(True)
        self.simple_tabs.addTab(self.simple_questions_tab, tr("result.tab.questions"))
        detail.addWidget(self.simple_tabs)
        layout.addWidget(self.simple_detail_card)
        self.simple_detail_card.hide()

        self.simple_metrics_label = _label("", "MicroLabel")
        self.simple_quality_label = _label("", "MicroLabel")
        self.simple_quality_label.setWordWrap(True)
        layout.addWidget(self.simple_metrics_label)
        layout.addWidget(self.simple_quality_label)

        files_row = QHBoxLayout()
        files_row.setSpacing(active_theme().spacing.sm)
        self.simple_files_label = _label("", "MicroLabel")
        self.simple_open_files_btn = GhostButton(tr("results.button.open_folder"))
        self.simple_open_files_btn.clicked.connect(self.open_last_output)
        self.simple_open_files_btn.setVisible(False)
        files_row.addWidget(self.simple_files_label, 1)
        files_row.addWidget(self.simple_open_files_btn, 0)
        layout.addLayout(files_row)

        layout.addStretch(1)
        return page

    # ─── Expert mode ───────────────────────────────────────────────

    def _build_extreme_mode(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.page_requested.connect(self._select_page)
        self.nav_items = self.sidebar.items
        layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self._add_page("resumen", self._build_dashboard())
        self._add_page("compilar", self._build_compiler())
        self._add_page("resultados", self._build_results())
        self._add_page("validacion", self._build_validation())
        self._add_page("perfiles", self._build_profiles())
        self._add_page("glosario", self._build_glossary())
        self._add_page("plantillas", self._build_template_page())
        self._add_page("historial", self._build_history_page())
        self._add_page("configuracion", self._build_settings_page())
        self._add_page("avanzado", self._build_advanced_editable())
        layout.addWidget(self.stack, 1)
        return container

    def _add_page(self, name: str, widget: QWidget) -> None:
        self.pages[name] = widget
        self.stack.addWidget(widget)

    def _select_page(self, name: str) -> None:
        close_context_help_popovers()
        if self._current_mode != MODE_EXTREME:
            self._switch_to_mode(MODE_EXTREME)
        widget = self.pages.get(name)
        if widget is None:
            return
        self.stack.setCurrentWidget(widget)
        self.sidebar.select(name)
        self.settings["last_section"] = name
        save_settings(self._collect_settings())

    # ─── Helpers ───────────────────────────────────────────────────

    def _help_button(self, key: str) -> ContextHelpButton:
        title, body = help_text(key)
        return ContextHelpButton(
            title, body, self, glossary_term_for(key), self.open_glossary_term
        )

    def _section_header(self, title: str, help_key: str | None = None) -> QFrame:
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(active_theme().spacing.xs)
        label = QLabel(title)
        label.setObjectName("SectionTitle")
        layout.addWidget(label)
        layout.addStretch(1)
        button = self._help_button(help_key or title)
        self.section_help_buttons[title] = button
        layout.addWidget(button)
        return frame

    def _label_with_help(self, text: str, help_key: str) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(active_theme().spacing.xs)
        layout.addWidget(QLabel(text))
        button = self._help_button(help_key)
        self.option_help_buttons[help_key] = button
        layout.addWidget(button)
        layout.addStretch(1)
        return layout

    def _page(self, title: str, subtitle: str, header_attr: str) -> tuple:
        page, layout = self._scroll_page()
        header = PageHeader(title, subtitle)
        setattr(self, header_attr, header)
        layout.addWidget(header)
        return page, layout

    # ─── Dashboard page ────────────────────────────────────────────

    def _build_dashboard(self) -> QWidget:
        page, layout = self._page(
            tr("nav.page.dashboard"), tr("page.dashboard.subtitle"), "dashboard_header"
        )

        editor_card = Card()
        editor = editor_card.content()
        editor.setSpacing(active_theme().spacing.md)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        self.prompt_tab_label = QLabel(tr("simple.prompt.label"))
        self.prompt_tab_label.setObjectName("PromptTab")
        self.prompt_tab_label.setProperty("active", True)
        tab_row.addWidget(self.prompt_tab_label)
        tab_row.addStretch(1)
        editor.addLayout(tab_row)

        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText(tr("simple.placeholder"))
        self.prompt_edit.setMinimumHeight(active_theme().metrics.editor_min_height)
        self.prompt_edit.textChanged.connect(self._on_extreme_prompt_changed)
        editor.addWidget(self.prompt_edit, 1)

        footer = QHBoxLayout()
        footer.setSpacing(active_theme().spacing.sm)
        self.char_label = _label("", "MicroLabel")
        self.token_label = _label("", "MicroLabel")
        footer.addWidget(self.char_label)
        footer.addWidget(self.token_label)
        footer.addStretch(1)

        self.profile_combo = QComboBox()
        self.profile_combo.addItems(PROFILES)
        self.target_combo = QComboBox()
        self.target_combo.addItems(MODELS)
        self.target_combo.currentTextChanged.connect(self._on_target_changed)
        self.level_combo = _combo(_levels())
        for text, widget in (
            (tr("simple.label.profile"), self.profile_combo),
            (tr("simple.label.model"), self.target_combo),
            (tr("simple.label.level"), self.level_combo),
        ):
            footer.addWidget(_label(text, "MicroLabel"))
            footer.addWidget(widget)
        editor.addLayout(footer)

        actions = QHBoxLayout()
        actions.setSpacing(active_theme().spacing.sm)
        self.compile_hero_btn = PrimaryButton(tr("simple.button.compile"))
        self.compile_hero_btn.clicked.connect(self.compile_current)
        apply_tooltip(self.compile_hero_btn, "compile")
        actions.addWidget(self.compile_hero_btn)

        self.render_file_btn = SecondaryButton(tr("simple.button.load_file"))
        self.render_file_btn.clicked.connect(self.load_file)
        apply_tooltip(self.render_file_btn, "load_file")
        actions.addWidget(self.render_file_btn)

        self.render_example_btn = SecondaryButton(tr("simple.button.example"))
        self.render_example_btn.clicked.connect(self.load_example)
        apply_tooltip(self.render_example_btn, "example")
        actions.addWidget(self.render_example_btn)

        self.render_clear_btn = SecondaryButton(tr("simple.button.clear"))
        self.render_clear_btn.clicked.connect(self.new_prompt)
        apply_tooltip(self.render_clear_btn, "reset")
        actions.addWidget(self.render_clear_btn)

        actions.addStretch(1)
        self.cancel_button = DangerButton(tr("simple.button.cancel"))
        self.cancel_button.clicked.connect(self.cancel_compile)
        self.cancel_button.setVisible(False)
        apply_tooltip(self.cancel_button, "cancel")
        actions.addWidget(self.cancel_button)
        editor.addLayout(actions)

        self.progress = ProgressIndicator()
        self.progress.setVisible(False)
        editor.addWidget(self.progress)

        self.hero_status = _label("", "MicroLabel")
        editor.addWidget(self.hero_status)
        layout.addWidget(editor_card)

        self.extreme_health_panel = QFrame()
        self.extreme_health_panel.setObjectName("NPSCPanel")
        health_layout = QVBoxLayout(self.extreme_health_panel)
        health_layout.setContentsMargins(
            active_theme().spacing.lg,
            active_theme().spacing.md,
            active_theme().spacing.lg,
            active_theme().spacing.md,
        )
        self.extreme_health = HealthDashboard()
        health_layout.addWidget(self.extreme_health)
        layout.addWidget(self.extreme_health_panel)
        self.extreme_health_panel.hide()

        self.tools_title = _label(tr("section.tools"), "SectionTitle")
        layout.addWidget(self.tools_title)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(active_theme().spacing.md)
        t1 = ToolCard(tr("tool.analyze"), tr("tool.analyze.desc"))
        t1.set_icon_text("⌕")
        t2 = ToolCard(tr("tool.validate"), tr("tool.validate.desc"))
        t2.set_icon_text("✓")
        t3 = ToolCard(tr("tool.copy_save"), tr("tool.copy_save.desc"))
        t3.set_icon_text("⎘")
        t1.clicked.connect(self.analyze_only)
        t2.clicked.connect(lambda: self._select_page("validacion"))
        t3.clicked.connect(self.copy_recommended)
        for card in (t1, t2, t3):
            tools_row.addWidget(card)
        tools_row.addStretch(1)
        layout.addLayout(tools_row)
        layout.addStretch(1)
        return page

    # ─── Compiler page ─────────────────────────────────────────────

    def _build_compiler(self) -> QWidget:
        page, layout = self._page(
            tr("nav.page.compiler"), tr("page.compiler.subtitle"), "compiler_header"
        )
        self.compiler_header_help = self._help_button("Compilador")
        self.compiler_header.add_action(self.compiler_header_help)

        options = Card()
        options_body = options.content()
        options_body.setSpacing(active_theme().spacing.md)

        # Each option is one row: label + help on the left, control on the right.
        def _row(label_layout, control) -> QWidget:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(active_theme().spacing.md)
            row_layout.addLayout(label_layout, 1)
            row_layout.addWidget(control, 2)
            return row

        self.strict_check = QCheckBox(tr("simple.check.enable"))
        options_body.addWidget(
            _row(self._label_with_help(tr("simple.check.strict"), "strict"), self.strict_check)
        )

        self.preserve_check = QCheckBox(tr("simple.check.enable"))
        self.preserve_check.setChecked(True)
        options_body.addWidget(
            _row(
                self._label_with_help(tr("simple.check.preserve"), "privacy"),
                self.preserve_check,
            )
        )

        self.privacy_combo = _combo(_privacy_modes())
        options_body.addWidget(
            _row(self._label_with_help(tr("simple.label.privacy"), "privacy"), self.privacy_combo)
        )

        self.custom_model_edit = QLineEdit()
        self.custom_model_edit.setPlaceholderText(tr("simple.label.custom_model_hint"))
        self._custom_model_row = _row(
            self._label_with_help(tr("simple.label.custom_model"), "custom_model"),
            self.custom_model_edit,
        )
        options_body.addWidget(self._custom_model_row)
        layout.addWidget(options)

        prompt_card = Card()
        prompt_body = prompt_card.content()
        self.compiler_prompt = QPlainTextEdit()
        self.compiler_prompt.setReadOnly(True)
        self.compiler_prompt.setPlaceholderText(tr("result.empty_prompt"))
        prompt_body.addWidget(self.compiler_prompt)

        counter_row = QHBoxLayout()
        counter_row.setSpacing(active_theme().spacing.md)
        self.char_label2 = _label("", "MicroLabel")
        self.token_label2 = _label("", "MicroLabel")
        counter_row.addWidget(self.char_label2)
        counter_row.addWidget(self.token_label2)
        counter_row.addStretch(1)
        prompt_body.addLayout(counter_row)
        layout.addWidget(prompt_card, 1)

        actions = QHBoxLayout()
        actions.setSpacing(active_theme().spacing.sm)
        self.compile_button = PrimaryButton(tr("simple.button.compile"))
        self.compile_button.clicked.connect(self.compile_current)
        apply_tooltip(self.compile_button, "compile")
        actions.addWidget(self.compile_button)

        for text, handler, key in (
            (tr("compiler.button.analyze"), self.analyze_only, "analyze"),
            (tr("simple.button.clear"), self.new_prompt, "reset"),
            (tr("simple.button.load_file"), self.load_file, "load_file"),
            (tr("compiler.button.paste"), self.paste_prompt, "paste"),
            (tr("simple.button.example"), self.load_example, "example"),
            (tr("results.button.save"), self.save_all, "save"),
        ):
            button = SecondaryButton(text)
            button.clicked.connect(handler)
            apply_tooltip(button, key)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)
        self._on_target_changed(self.target_combo.currentText())
        self.section_help_buttons["Compilador"] = self.compiler_header_help
        return page

    # ─── Results page ──────────────────────────────────────────────

    def _build_results(self) -> QWidget:
        page, layout = self._page(
            tr("nav.page.results"), tr("page.results.subtitle"), "results_header"
        )

        # ── primary actions: one dominant, the rest clearly secondary ──
        actions = QHBoxLayout()
        actions.setSpacing(active_theme().spacing.sm)
        self.copy_button = PrimaryButton(tr("results.button.copy_prompt"))
        self.copy_button.clicked.connect(self.copy_recommended)
        apply_tooltip(self.copy_button, "copy")
        actions.addWidget(self.copy_button)

        for text, handler, key in (
            (tr("results.button.save"), self.save_all, "save"),
            (tr("results.button.open_folder"), self.open_last_output, "open_folder"),
        ):
            button = SecondaryButton(text)
            button.clicked.connect(handler)
            apply_tooltip(button, key)
            actions.addWidget(button)
        actions.addStretch(1)

        # ── technical actions live in a single, quiet menu ─────────────
        self.results_more_button = GhostButton("⋯ " + tr("results.button.more"))
        self.results_more_menu = QMenu(self)
        self._add_result_menu_action(
            self.results_more_menu, tr("results.button.copy_json"), self.copy_json, "copy_json"
        )
        self._add_result_menu_action(
            self.results_more_menu,
            tr("results.button.export_preview"),
            self._open_export_preview,
            "export_preview",
        )
        self.results_more_button.setMenu(self.results_more_menu)
        actions.addWidget(self.results_more_button)

        self.results_help = self._help_button("results_tab")
        self.section_help_buttons[tr("section.results")] = self.results_help
        actions.addWidget(self.results_help)
        layout.addLayout(actions)

        self.extreme_skeleton = Skeleton(lines=6)
        self.extreme_skeleton.hide()
        layout.addWidget(self.extreme_skeleton)

        # ── tabs grouped by intent, not by data source ────────────────
        self.results_empty = EmptyState(
            tr("result.empty.title"), tr("result.empty.hint")
        )
        layout.addWidget(self.results_empty)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.summary_text = self._text_tab("Resumen")
        self.optimized_text = self._text_tab("Prompt listo para usar")
        self.hybrid_text = self._text_tab("Informe completo")
        self.original_text = self._text_tab("Prompt original")
        self.validation_text = self._text_tab("Validación")
        self.nsl_text = self._text_tab("NSL compacto")
        self.json_text = self._text_tab("JSON para programas")
        self.seeds_text = self._text_tab(tr("result.rules"))
        self.constraints_text = self._text_tab("Restricciones y origen")
        self.profile_text = self._text_tab("Perfil aplicado")
        self.tabs.currentChanged.connect(lambda _index: close_context_help_popovers())
        layout.addWidget(self.tabs, 1)
        self.tabs.hide()
        return page

    def _add_result_menu_action(self, menu: QMenu, text: str, handler, tooltip_key: str) -> None:
        action = menu.addAction(text)
        action.triggered.connect(handler)
        action.setToolTip(self._tooltip_text(tooltip_key))

    def _tooltip_text(self, key: str) -> str:
        from npsc_gui.tooltips import BRIEF_TOOLTIPS

        return BRIEF_TOOLTIPS.get(key, "")

    def _text_tab(self, title: str) -> QPlainTextEdit:
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        self.tabs.addTab(editor, title)
        return editor

    # ─── Validation / profiles / glossary / settings ───────────────

    def _build_validation(self) -> QWidget:
        page, layout = self._page(
            tr("nav.page.validation"), tr("page.validation.subtitle"), "validation_header"
        )
        self.validation_header_help = self._help_button("Validación")
        self.validation_header.add_action(self.validation_header_help)
        self.section_help_buttons["Validación"] = self.validation_header_help
        card = Card()
        self.validation_detail = QTextEdit()
        self.validation_detail.setReadOnly(True)
        card.content().addWidget(self.validation_detail)
        layout.addWidget(card, 1)
        return page

    def _build_profiles(self) -> QWidget:
        page, layout = self._page(
            tr("nav.page.profiles"), tr("page.profiles.subtitle"), "profiles_header"
        )
        self.profiles_header_help = self._help_button("Perfiles")
        self.profiles_header.add_action(self.profiles_header_help)
        self.section_help_buttons["Perfiles"] = self.profiles_header_help
        self.profile_cards: list[Card] = []
        for name, description_key in PROFILE_DEFINITIONS:
            card = Card()
            body = card.content()
            title = QLabel(name)
            title.setObjectName("ValueStrong")
            body.addWidget(title)
            text = _label(tr(description_key), "MicroLabel")
            text.setWordWrap(True)
            body.addWidget(text)
            page_layout = body
            page_layout.addStretch(1)
            layout.addWidget(card)
            self.profile_cards.append(card)
        layout.addStretch(1)
        return page

    def _build_glossary(self) -> QWidget:
        page, layout = self._page(
            tr("nav.page.glossary"), tr("page.glossary.subtitle"), "glossary_header"
        )

        self.glossary_header_help = self._help_button("Glosario")
        self.glossary_header.add_action(self.glossary_header_help)
        self.section_help_buttons["Glosario"] = self.glossary_header_help

        controls = QHBoxLayout()
        controls.setSpacing(active_theme().spacing.sm)
        self.glossary_search = QLineEdit()
        self.glossary_search.setPlaceholderText(tr("glossary.search_placeholder"))
        self.glossary_search.textChanged.connect(self._refresh_glossary)
        self.glossary_category = QComboBox()
        self.glossary_category.addItems(CATEGORIES)
        self.glossary_category.currentTextChanged.connect(self._refresh_glossary)
        self.glossary_count = _label("", "MicroLabel")
        controls.addWidget(self.glossary_search, 1)
        controls.addWidget(self.glossary_category)
        controls.addWidget(self.glossary_count)
        layout.addLayout(controls)

        split = QHBoxLayout()
        split.setSpacing(active_theme().spacing.md)
        list_card = Card()
        self.glossary_list = QListWidget()
        self.glossary_list.setMinimumWidth(280)
        self.glossary_list.currentItemChanged.connect(self._on_glossary_selection_changed)
        list_card.content().addWidget(self.glossary_list)
        split.addWidget(list_card, 0)

        detail_card = Card()
        self.glossary_detail = QTextEdit()
        self.glossary_detail.setReadOnly(True)
        self.glossary_detail.setPlainText(tr("glossary.search"))
        detail_card.content().addWidget(self.glossary_detail)
        split.addWidget(detail_card, 1)
        layout.addLayout(split, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.copy_glossary_button = SecondaryButton(tr("glossary.copy"))
        self.copy_glossary_button.clicked.connect(self.copy_glossary_explanation)
        bottom.addWidget(self.copy_glossary_button)
        layout.addLayout(bottom)
        self._refresh_glossary()
        return page

    def _build_settings_page(self) -> QWidget:
        page, layout = self._page(
            tr("nav.page.settings"), tr("page.settings.subtitle"), "settings_header"
        )

        self.settings_header_help = self._help_button("Configuración")
        self.settings_header.add_action(self.settings_header_help)
        self.section_help_buttons["Configuración"] = self.settings_header_help

        appearance = Card()
        appearance_body = appearance.content()
        self.appearance_title = _label(tr("settings.appearance"), "SectionTitle")
        appearance_body.addWidget(self.appearance_title)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(active_theme().spacing.md)
        theme_row.addWidget(_label(tr("settings.theme"), "FieldLabel"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(tr("settings.theme.dark"), "dark")
        self.theme_combo.addItem(tr("settings.theme.light"), "light")
        self.theme_combo.setCurrentIndex(
            0 if self.settings.get("theme", "dark") == "dark" else 1
        )
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self.theme_combo, 1)
        appearance_body.addLayout(theme_row)

        language_row = QHBoxLayout()
        language_row.setSpacing(active_theme().spacing.md)
        language_row.addWidget(_label(tr("settings.language"), "FieldLabel"))
        self.language_combo = QComboBox()
        self.LANGUAGE_LABELS = (
            ("Español", "es"),
            ("English", "en"),
            ("Français", "fr"),
            ("Deutsch", "de"),
            ("Русский", "ru"),
            ("한국어", "ko"),
            ("中文", "zh"),
        )
        for label, value in self.LANGUAGE_LABELS:
            self.language_combo.addItem(label, value)
        stored_language = normalize_language(str(self.settings.get("language", "es")))
        self.language_combo.setCurrentIndex(LANGUAGES.index(stored_language))
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        language_row.addWidget(self.language_combo, 1)
        appearance_body.addLayout(language_row)

        self.theme_combo.setCurrentIndex(
            0 if self.settings.get("theme", "dark") == "dark" else 1
        )

        self.reduce_motion_check = QCheckBox(tr("settings.reduce_motion"))
        self.reduce_motion_check.setChecked(motion.reduce_motion())
        self.reduce_motion_check.toggled.connect(self._on_reduce_motion_toggled)
        appearance_body.addWidget(self.reduce_motion_check)
        self.reduce_motion_help = _label(tr("settings.reduce_motion.help"), "MicroLabel")
        self.reduce_motion_help.setWordWrap(True)
        appearance_body.addWidget(self.reduce_motion_help)
        layout.addWidget(appearance)

        behaviour = Card()
        behaviour_body = behaviour.content()
        self.behaviour_title = _label(tr("settings.behavior"), "SectionTitle")
        behaviour_body.addWidget(self.behaviour_title)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(active_theme().spacing.md)
        mode_row.addWidget(_label(tr("settings.startup_mode"), "FieldLabel"))
        self.startup_mode_combo = QComboBox()
        self.startup_mode_combo.addItem(tr("status.mode_simple"), MODE_SIMPLE)
        self.startup_mode_combo.addItem(tr("status.mode_extreme"), MODE_EXTREME)
        self.startup_mode_combo.setCurrentIndex(
            0 if self.settings.get("startup_mode", MODE_SIMPLE) == MODE_SIMPLE else 1
        )
        mode_row.addWidget(self.startup_mode_combo, 1)
        behaviour_body.addLayout(mode_row)

        data_card = Card()
        data_body = data_card.content()
        self.data_title = _label(tr("settings.data_location"), "SectionTitle")
        data_body.addWidget(self.data_title)
        self.data_help = _label(tr("settings.data_location.help"), "MicroLabel")
        self.data_help.setWordWrap(True)
        data_body.addWidget(self.data_help)
        self.data_path_label = _label(str(data_dir()), "MonoText")
        self.data_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        data_body.addWidget(self.data_path_label)
        layout.addWidget(data_card)

        reset_card = Card()
        reset_body = reset_card.content()
        hint = _label(tr("settings.reset.help"), "MicroLabel")
        hint.setWordWrap(True)
        reset_body.addWidget(hint)
        self.reset_button = SecondaryButton(tr("settings.reset"))
        self.reset_button.clicked.connect(self.reset_configuration)
        apply_tooltip(self.reset_button, "settings_reset")
        reset_body.addWidget(self.reset_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(reset_card)

        layout.addWidget(behaviour)
        layout.addStretch(1)
        return page

    # ─── Template / history / advanced ─────────────────────────────

    def _build_template_page(self) -> QWidget:
        return build_template_page(self)

    def _build_history_page(self) -> QWidget:
        return build_history_page(self)

    def _build_advanced_editable(self) -> QWidget:
        self._advanced_page = AdvancedModePage()
        self._advanced_page.compile_requested.connect(self._compile_from_advanced)
        self._advanced_page.sections_changed.connect(self._on_advanced_sections_changed)
        return self._advanced_page

    # ─── Mode switching ────────────────────────────────────────────

    def _toggle_mode(self) -> None:
        target = MODE_EXTREME if self._current_mode == MODE_SIMPLE else MODE_SIMPLE
        self._switch_to_mode(target)

    def _switch_to_mode(self, mode: str) -> None:
        close_context_help_popovers()
        self._current_mode = mode
        if mode == MODE_SIMPLE:
            self.mode_stack.setCurrentIndex(0)
            self.status_mode.setText(tr("status.mode_simple"))
            self._sync_prompts(simple_wins=True)
            self._sync_combos_extreme_to_simple()
        else:
            self.mode_stack.setCurrentIndex(1)
            self.status_mode.setText(tr("status.mode_extreme"))
            self._sync_prompts(simple_wins=False)
            self._sync_combos_simple_to_extreme()
            self._select_page("resultados" if self.result else "resumen")
        self.header.set_mode(mode)
        self.status_bar.set_mode(mode)
        if self._advanced_page_present():
            self._advanced_page.set_informal_input(self.prompt_edit.toPlainText())
        save_settings(self._collect_settings())

    def _advanced_page_present(self) -> bool:
        return hasattr(self, "_advanced_page") and hasattr(self, "prompt_edit")

    def _sync_prompts(self, *, simple_wins: bool) -> None:
        if not (hasattr(self, "prompt_edit") and hasattr(self, "simple_prompt_edit")):
            return
        simple_text = self.simple_prompt_edit.toPlainText()
        extreme_text = self.prompt_edit.toPlainText()
        if simple_wins:
            if simple_text and simple_text != extreme_text:
                self.prompt_edit.blockSignals(True)
                self.prompt_edit.setPlainText(simple_text)
                self.prompt_edit.blockSignals(False)
            elif extreme_text and not simple_text:
                self.simple_prompt_edit.setPlainText(extreme_text)
        else:
            if extreme_text and extreme_text != simple_text:
                self.simple_prompt_edit.blockSignals(True)
                self.simple_prompt_edit.setPlainText(extreme_text)
                self.simple_prompt_edit.blockSignals(False)
            elif simple_text and not extreme_text:
                self.prompt_edit.blockSignals(True)
                self.prompt_edit.setPlainText(simple_text)
                self.prompt_edit.blockSignals(False)

    def _sync_combos_simple_to_extreme(self) -> None:
        if not hasattr(self, "simple_profile_combo"):
            return
        self.profile_combo.setCurrentText(self.simple_profile_combo.currentText())
        self.target_combo.setCurrentText(self.simple_target_combo.currentText())
        level = self.simple_level_combo.currentData()
        self._set_combo_value(self.level_combo, str(level or "profile_default"))
        self.strict_check.setChecked(self.simple_strict_check.isChecked())
        self.preserve_check.setChecked(self.simple_preserve_check.isChecked())
        privacy = self.simple_privacy_combo.currentData()
        self._set_combo_value(self.privacy_combo, str(privacy or "full_original"))

    def _sync_combos_extreme_to_simple(self) -> None:
        if not hasattr(self, "simple_profile_combo"):
            return
        self.simple_profile_combo.setCurrentText(self.profile_combo.currentText())
        self.simple_target_combo.setCurrentText(self.target_combo.currentText())
        level = self.level_combo.currentData()
        self._set_combo_value(self.simple_level_combo, str(level or "profile_default"))
        self.simple_strict_check.setChecked(self.strict_check.isChecked())
        self.simple_preserve_check.setChecked(self.preserve_check.isChecked())
        privacy = self.privacy_combo.currentData()
        self._set_combo_value(self.simple_privacy_combo, str(privacy or "full_original"))

    # ─── Prompt sync ───────────────────────────────────────────────

    def _on_simple_prompt_changed(self) -> None:
        text = self.simple_prompt_edit.toPlainText()
        if hasattr(self, "prompt_edit"):
            self.prompt_edit.blockSignals(True)
            self.prompt_edit.setPlainText(text)
            self.prompt_edit.blockSignals(False)
        self._counters_debounce_timer.start()
        profile = (
            self.simple_profile_combo.currentText()
            if hasattr(self, "simple_profile_combo")
            else "AUTO"
        )
        self.simple_profile_hint.setText(
            tr("profile.auto_recommended") if profile == "AUTO" else profile
        )

    def _on_extreme_prompt_changed(self) -> None:
        if self._current_mode != MODE_EXTREME:
            return
        text = self.prompt_edit.toPlainText()
        if hasattr(self, "simple_prompt_edit"):
            if text != self.simple_prompt_edit.toPlainText():
                self.simple_prompt_edit.blockSignals(True)
                self.simple_prompt_edit.setPlainText(text)
                self.simple_prompt_edit.blockSignals(False)
        self._counters_debounce_timer.start()

    def _on_simple_profile_combo_changed(self, text: str) -> None:
        self.simple_profile_hint.setText(
            tr("profile.auto_recommended") if text == "AUTO" else text
        )
        if hasattr(self, "profile_combo"):
            self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentText(text)
            self.profile_combo.blockSignals(False)

    def _on_target_changed(self, target: str) -> None:
        visible = target == "custom"
        if hasattr(self, "custom_model_edit"):
            self.custom_model_edit.setVisible(visible)
        if hasattr(self, "_custom_model_row"):
            self._custom_model_row.setVisible(visible)

    # ─── Simple-mode result state ──────────────────────────────────

    def _show_results(self) -> None:
        self.simple_stack.setCurrentWidget(self.simple_result_panel)

    def _show_home(self) -> None:
        self.simple_stack.setCurrentWidget(self.simple_home_panel)

    def _simple_new_compilation(self) -> None:
        self.result = None
        self.simple_prompt_edit.clear()
        if hasattr(self, "simple_result_card"):
            self.simple_result_card.clear()
        self.simple_result_panel.setVisible(True)
        self.simple_metrics_panel.hide()
        self.simple_detail_card.hide()
        self.simple_skeleton.hide()
        self.simple_progress.setVisible(False)
        self.simple_progress.setValue(0)
        self.simple_cancel_btn.setVisible(False)
        self.simple_stage_label.setText("")
        self._show_home()
        self.simple_prompt_edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def _show_simple_history(self) -> None:
        if self.result:
            self._switch_to_mode(MODE_EXTREME)
            self._select_page("resultados")
        else:
            self._toast.show_message(tr("history.none"), "info")

    # ─── Settings, dialogs, language ───────────────────────────────

    def _open_settings(self) -> None:
        self._switch_to_mode(MODE_EXTREME)
        self._select_page("configuracion")

    def _open_help(self) -> None:
        self._switch_to_mode(MODE_EXTREME)
        self._select_page("glosario")

    def _open_context_workbench(self) -> None:
        from npsc_gui.context_workbench import ContextWorkbench
        ContextWorkbench(self).exec()

    def _open_about(self) -> None:
        dialog = AboutDialog(self, language=str(self.settings.get("language", "es")))
        dialog.exec()

    def _open_export_preview(self) -> None:
        result = getattr(self, "result", None)
        if not result:
            self._toast.show_message(tr("error.no_result"), "warning")
            return
        ExportPreviewDialog(result, self).exec()

    def _on_theme_changed(self, index: int) -> None:
        theme_name = "dark" if index == 0 else "light"
        self.settings["theme"] = theme_name
        app = QApplication.instance()
        if app is not None:
            apply_design(app, get_theme(theme_name))
            self.setStyleSheet("")
        # Keep the selector truthful when the theme is changed from code too.
        if hasattr(self, "theme_combo") and self.theme_combo.currentIndex() != index:
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(index)
            self.theme_combo.blockSignals(False)
        self._restyle_dynamic_widgets()
        save_settings(self._collect_settings())

    def _restyle_dynamic_widgets(self) -> None:
        for widget in (
            getattr(self, "simple_metrics_panel", None),
            getattr(self, "extreme_health_panel", None),
            getattr(self, "simple_detail_card", None),
            getattr(self, "home_rail", None),
        ):
            if widget is not None:
                widget.style().unpolish(widget)
                widget.style().polish(widget)
        self.header.set_state(
            "working" if self._is_compiling() else "ready",
            tr("status.working") if self._is_compiling() else tr("status.ready"),
        )
        self.status_bar.set_message(self.status_bar.message.text(), "idle")
        self.update()

    def _on_language_changed(self, index: int) -> None:
        language = LANGUAGES[index] if 0 <= index < len(LANGUAGES) else "es"
        self.settings["language"] = set_language(language)
        save_settings(self._collect_settings())
        self._retranslate_ui()
        self._toast.show_message(tr("toast.language_changed"), "info")

    def _on_reduce_motion_toggled(self, checked: bool) -> None:
        motion.set_motion_enabled(not checked)

    # ─── Settings persistence ──────────────────────────────────────

    def _restore_settings(self) -> None:
        self.profile_combo.setCurrentText(str(self.settings["profile"]))
        self.target_combo.setCurrentText(str(self.settings["target"]))
        self._set_combo_value(self.level_combo, str(self.settings["level"]))
        self.strict_check.setChecked(bool(self.settings["strict_validation"]))
        self.preserve_check.setChecked(bool(self.settings["preserve_original"]))
        self._set_combo_value(
            self.privacy_combo,
            str(self.settings.get("privacy_mode", "full_original")),
        )
        self.custom_model_edit.setText(str(self.settings.get("custom_model_name", "")))
        output_dir = str(self.settings.get("output_dir", ""))
        self.last_saved_dir = Path(output_dir) if output_dir else None
        self._sync_combos_extreme_to_simple()

        startup_mode = str(self.settings.get("startup_mode", MODE_SIMPLE))
        if startup_mode not in (MODE_SIMPLE, MODE_EXTREME):
            startup_mode = MODE_SIMPLE
        self._switch_to_mode(startup_mode)
        if self._current_mode == MODE_EXTREME:
            last_section = str(self.settings.get("last_section", "resumen"))
            if last_section not in self.pages:
                last_section = "resumen"
            self._select_page(last_section)

    def _collect_settings(self) -> dict:
        if self.isMaximized():
            normal = self.normalGeometry()
            width, height = normal.width(), normal.height()
        else:
            width, height = self.width(), self.height()
        return {
            "advanced_mode": self._current_mode == MODE_EXTREME,
            "startup_mode": self._current_mode,
            "theme": self.settings.get("theme", "dark"),
            "language": self.settings.get("language", "es"),
            "profile": self.profile_combo.currentText(),
            "target": self.target_combo.currentText(),
            "level": self._combo_value(self.level_combo),
            "strict_validation": self.strict_check.isChecked(),
            "preserve_original": self.preserve_check.isChecked(),
            "privacy_mode": self._combo_value(self.privacy_combo),
            "custom_model_name": self.custom_model_edit.text(),
            "last_section": next(
                (
                    name
                    for name, widget in self.pages.items()
                    if widget is self.stack.currentWidget()
                ),
                "resumen",
            ),
            "window_width": width,
            "window_height": height,
            "output_dir": self.settings.get("output_dir", ""),
        }

    # ─── Shortcuts ─────────────────────────────────────────────────

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_prompt)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.load_file)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_all)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.compile_current)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.compile_current)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, activated=self.copy_recommended)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.new_prompt)
        QShortcut(QKeySequence("F1"), self, activated=self._open_help)
        QShortcut(QKeySequence("Ctrl+M"), self, activated=self._toggle_mode)
        QShortcut(QKeySequence("Ctrl+G"), self, activated=self._save_project)
        QShortcut(QKeySequence("Ctrl+Shift+O"), self, activated=self._load_project)
        QShortcut(QKeySequence("Ctrl+Shift+V"), self, activated=self._show_variable_dialog)

    def _escape(self) -> None:
        if self._is_compiling():
            self.cancel_compile()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        # Escape is deliberately NOT a global QShortcut: that would swallow the
        # key in text editors, dialogs and help popovers. It only cancels a
        # running compilation and only when nothing else consumed it.
        if (
            event.key() == Qt.Key.Key_Escape
            and self._is_compiling()
            and not event.isAccepted()
        ):
            self.cancel_compile()
            event.accept()
            return
        super().keyPressEvent(event)

    # ─── Counters & status ─────────────────────────────────────────

    def _update_counters(self) -> None:
        text = self._get_current_prompt()
        chars, tokens = estimate_counters(text)
        for label in (
            getattr(self, "char_label", None),
            getattr(self, "char_label2", None),
            getattr(self, "simple_char_label", None),
        ):
            if label is not None:
                label.setText(tr("home.characters").format(count=chars))
        for label in (
            getattr(self, "token_label", None),
            getattr(self, "token_label2", None),
            getattr(self, "simple_token_label", None),
        ):
            if label is not None:
                label.setText(tr("home.tokens").format(count=tokens))
        if hasattr(self, "compiler_prompt"):
            self.compiler_prompt.setPlainText(text)

    def _set_header_status(self, state: str, text: str) -> None:
        self.header.set_state(state, text)

    def _set_status(
        self,
        message: str,
        profile: str,
        validation: str,
        path: str,
    ) -> None:
        state = validation.lower().strip().replace(" ", "_") or "normal"
        semantic = "idle"
        if state in ("normal", "pass"):
            semantic = "success"
        elif state in ("procesando", "warning"):
            semantic = "warning"
        elif state in ("error", "bloqueado", "blocked", "fail"):
            semantic = "error"
        elif state in ("cancelado", "canceled"):
            semantic = "idle"
        self.status_bar.set_message(message, semantic)
        self.status_bar.set_profile(profile)
        chip_state = {
            "idle": "idle",
            "success": "success",
            "warning": "warning",
            "error": "error",
        }[semantic]
        self._set_header_status(chip_state, message)

    def _combo_value(self, combo: QComboBox) -> str:
        value = combo.currentData()
        return str(value if value is not None else combo.currentText())

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value or combo.itemText(index) == value:
                combo.setCurrentIndex(index)
                return

    # ─── Compile workflow ──────────────────────────────────────────

    def _build_compile_request(self) -> dict | None:
        prompt = self._get_current_prompt().strip()
        if not prompt:
            self._show_inline_error(tr("error.empty_input"), tr("error.empty_hint"))
            return None
        if self._current_mode == MODE_SIMPLE:
            return {
                "prompt": prompt,
                "target": self.simple_target_combo.currentText(),
                "profile": self.simple_profile_combo.currentText(),
                "level": self._combo_value(self.simple_level_combo),
                "strict": self.simple_strict_check.isChecked(),
                "preserve_original": self.simple_preserve_check.isChecked(),
                "privacy_mode": self._combo_value(self.simple_privacy_combo),
                "custom_model_name": "",
            }
        return {
            "prompt": prompt,
            "target": self.target_combo.currentText(),
            "profile": self.profile_combo.currentText(),
            "level": self._combo_value(self.level_combo),
            "strict": self.strict_check.isChecked(),
            "preserve_original": self.preserve_check.isChecked(),
            "privacy_mode": self._combo_value(self.privacy_combo),
            "custom_model_name": self.custom_model_edit.text(),
        }

    def _show_inline_error(self, title: str, message: str) -> None:
        self.simple_inline_notice.set_state("error")
        self.simple_inline_notice.set_message(f"{title}. {message}" if message else title)
        self.simple_inline_notice.show()
        if self._current_mode == MODE_SIMPLE:
            self.simple_prompt_edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def _clear_inline_error(self) -> None:
        self.simple_inline_notice.hide()
        self.simple_inline_notice.set_message("")

    def _is_compiling(self) -> bool:
        return bool(self.worker_thread and self.worker_thread.isRunning())

    def compile_current(self) -> None:
        prompt = self._get_current_prompt().strip()
        if not prompt:
            self._show_inline_error(tr("error.empty_input"), tr("error.empty_hint"))
            return
        if self._is_compiling():
            return
        self._clear_inline_error()

        detected = extract_variables(prompt)
        if detected:
            unfilled = [v for v in detected if not self._variable_values.get(v, "").strip()]
            if unfilled:
                self._toast.show_message(
                    tr("error.variables_unfilled").format(
                        variables=", ".join(unfilled)
                    ),
                    "warning",
                    4200,
                )
                self._show_variable_dialog()
                return
            prompt, _ = fill_variables(prompt, self._variable_values, strict=False)

        validation = validate_compile_form(
            prompt, variables=self._variable_values, strict=False
        )
        if validation.errors:
            self._show_inline_error(
                tr("error.validation"),
                " · ".join(str(e["message"]) for e in validation.errors),
            )
            return
        if validation.warnings and not self._warnings_acknowledged:
            self._warnings_acknowledged = True
            self._toast.show_message(
                tr("warning.compiling_with_warnings").format(
                    count=len(validation.warnings)
                ),
                "warning",
                3600,
            )

        request = self._build_compile_request()
        if request is None:
            return
        if detected:
            request["prompt"] = prompt

        self.cancel_requested = False
        self._warnings_acknowledged = False
        self._enter_working_state()

        self.worker_thread = QThread(self)
        self.worker = CompileWorker(self.controller, request)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.failed.connect(self._on_worker_failed)
        self.worker.canceled.connect(self._on_worker_canceled)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker.canceled.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.worker.canceled.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def _enter_working_state(self) -> None:
        self._last_stage = ""
        self.simple_compile_btn.set_loading(True)
        self.simple_compile_btn.setText(tr("status.working"))
        if hasattr(self, "compile_button"):
            self.compile_button.set_loading(True)
        if hasattr(self, "compile_hero_btn"):
            self.compile_hero_btn.set_loading(True)
        self.simple_cancel_btn.setVisible(True)
        self.simple_cancel_btn.setEnabled(True)
        if hasattr(self, "cancel_button"):
            self.cancel_button.setVisible(True)
            self.cancel_button.setEnabled(True)
        self.simple_progress.set_indeterminate(True)
        self.simple_progress.set_variant("info")
        self.simple_progress.setVisible(True)
        if hasattr(self, "progress"):
            self.progress.set_indeterminate(True)
            self.progress.setVisible(True)
        self.simple_stage_label.setText(tr("toast.compile_started"))
        # The result page is what the user sees while compiling: give it the
        # stage, the progress and a working cancel button.
        self.work_strip.show()
        self.result_stage_label.setText(tr("toast.compile_started"))
        self.result_progress.set_indeterminate(True)
        self.result_progress.set_variant("info")
        self.result_cancel_btn.setEnabled(True)
        self.result_cancel_btn.setVisible(True)
        self.simple_result_card.set_working()
        self.simple_skeleton.show()
        self.simple_result_card.hide()
        self.simple_detail_card.hide()
        self.simple_metrics_panel.hide()
        self._show_results()
        if hasattr(self, "extreme_skeleton"):
            self.extreme_skeleton.show()
            self.tabs.hide()
            self.results_empty.hide()
        self._set_header_status("working", tr("status.working"))
        self.status_bar.set_message(tr("status.working"), "working")
        self._working_toast = self._toast.show_message(
            tr("toast.compile_started"), "info", 20000
        )

    def _dismiss_working_toast(self) -> None:
        toast = getattr(self, "_working_toast", None)
        if toast is not None:
            try:
                toast.hide_now()
            except RuntimeError:
                pass
            self._working_toast = None

    def _exit_working_state(self) -> None:
        self._dismiss_working_toast()
        self.simple_compile_btn.set_loading(False, tr("simple.button.compile"))
        if hasattr(self, "compile_button"):
            self.compile_button.set_loading(False, tr("simple.button.compile"))
        if hasattr(self, "compile_hero_btn"):
            self.compile_hero_btn.set_loading(False, tr("simple.button.compile"))
        self.simple_cancel_btn.setVisible(False)
        if hasattr(self, "cancel_button"):
            self.cancel_button.setVisible(False)
        self.simple_progress.set_indeterminate(False)
        self.simple_progress.setVisible(False)
        if hasattr(self, "progress"):
            self.progress.set_indeterminate(False)
            self.progress.setVisible(False)
        if hasattr(self, "work_strip"):
            self.work_strip.hide()
            self.result_progress.set_indeterminate(False)
            self.result_progress.setRange(0, 100)
            self.result_progress.setValue(0)
        self.simple_skeleton.hide()
        self.worker = None
        self.worker_thread = None

    def cancel_compile(self) -> None:
        if not self._is_compiling():
            return
        self.cancel_requested = True
        if self.worker:
            self.worker.cancel()
        self.simple_stage_label.setText(tr("status.cancelling"))
        if hasattr(self, "result_stage_label"):
            self.result_stage_label.setText(tr("status.cancelling"))
            self.result_cancel_btn.setEnabled(False)
        self.status_bar.set_message(tr("status.cancelling"), "warning")

    # ─── Current state helpers ─────────────────────────────────────

    def _current_editor(self):
        if self._current_mode == MODE_SIMPLE:
            return getattr(self, "simple_prompt_edit", None)
        return getattr(self, "prompt_edit", None)

    # ─── Initial focus ─────────────────────────────────────────────

    def changeEvent(self, event) -> None:
        """Claim the prompt editor when the window is first activated.

        Qt assigns initial focus to the first focusable child (a header button
        here), and that assignment is queued AFTER the activation event. A
        short watcher waits for it, then moves focus to the editor. If the user
        focuses something else afterwards, the watcher stops immediately.
        """
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.ActivationChange
            and self.isActiveWindow()
            and self._current_editor() is not None
            and not getattr(self, "_prompt_focus_watcher", None)
        ):
            self._prompt_focus_attempts = 0
            self._prompt_focus_claimed = False
            watcher = QTimer(self)
            watcher.setInterval(20)
            watcher.timeout.connect(self._claim_prompt_focus)
            watcher.start()
            self._prompt_focus_watcher = watcher

    def _claim_prompt_focus(self) -> None:
        self._prompt_focus_attempts += 1
        editor = self._current_editor()
        current = self.focusWidget()
        if editor is None or current is editor:
            self._stop_prompt_focus_watcher()
            return
        if current is None or not getattr(self, "_prompt_focus_claimed", False):
            editor.setFocus(Qt.FocusReason.OtherFocusReason)
            self._prompt_focus_claimed = True
        else:
            self._stop_prompt_focus_watcher()
            return
        if self._prompt_focus_attempts >= 100:
            self._stop_prompt_focus_watcher()

    def _stop_prompt_focus_watcher(self) -> None:
        watcher = getattr(self, "_prompt_focus_watcher", None)
        if watcher is not None:
            watcher.stop()
            watcher.deleteLater()
            self._prompt_focus_watcher = None

    def _get_current_prompt(self) -> str:
        editor = self._current_editor()
        return editor.toPlainText() if editor is not None else ""

    def _get_current_profile(self) -> str:
        if self._current_mode == MODE_SIMPLE and hasattr(self, "simple_profile_combo"):
            return self.simple_profile_combo.currentText()
        if hasattr(self, "profile_combo"):
            return self.profile_combo.currentText()
        return "AUTO"

    # ─── Worker callbacks ──────────────────────────────────────────

    @Slot(int, str)
    def _on_worker_progress(self, value: int, label: str) -> None:
        if self.cancel_requested:
            return
        self._last_stage = label
        if hasattr(self, "progress"):
            self.progress.set_variant("info")
            self.progress.setValue(value)
        self.simple_progress.set_variant("info")
        self.simple_progress.setValue(value)
        self.simple_stage_label.setText(f"{label} · {value}%")
        if hasattr(self, "result_progress"):
            self.result_progress.set_indeterminate(False)
            self.result_progress.setRange(0, 100)
            self.result_progress.setValue(value)
            self.result_stage_label.setText(f"{label} · {value}%")
        if hasattr(self, "hero_status"):
            self.hero_status.setText(f"{label} · {value}%")
        self.status_bar.set_message(label, "working")

    @Slot(dict)
    def _on_worker_finished(self, result: dict) -> None:
        self.result = result
        self._render_result()
        try:
            compiled = result.get("optimized_prompt", result.get("chosen_nsl", ""))
            if compiled:
                summary = self._get_current_prompt()[:80]
                self._version_history.create_version(
                    name=summary or "Compilación",
                    content=compiled,
                    informal_input=result.get("original", ""),
                    target=result.get("target", "auto"),
                    profile=result.get("applied_profile", "AUTO"),
                )
        except Exception:
            pass
        save_settings(self._collect_settings())
        self._exit_working_state()
        self._show_results()
        if self._current_mode == MODE_EXTREME:
            self._select_page("resultados")

    @Slot(str)
    def _on_worker_failed(self, message: str) -> None:
        self._exit_working_state()
        self._toast.clear()
        self.simple_progress.set_variant("error")
        self.simple_progress.set_indeterminate(False)
        self.simple_progress.setRange(0, 100)
        self.simple_progress.setValue(100)
        self.simple_progress.setVisible(True)
        self.simple_stage_label.setText("")

        card = self.simple_result_card
        card.clear()
        card.chip.set_state("error")
        card.chip.set_text(tr("result.state.error"))
        card.title_label.setText(tr("toast.compile_failed"))
        card.meta_label.setText(tr("error.compile_failed"))
        card.body.setPlainText(message)
        card.show()
        self.simple_skeleton.hide()
        self.simple_detail_card.hide()
        self.simple_metrics_panel.hide()
        # Never leave numbers from a previous compilation under an error.
        self.simple_metrics_label.setText("")
        self.simple_quality_label.setText("")
        self.simple_files_label.setText("")
        self.simple_open_files_btn.setVisible(False)
        self._show_results()

        if self._current_mode == MODE_EXTREME:
            if hasattr(self, "extreme_skeleton"):
                self.extreme_skeleton.hide()
            self.tabs.show()
            self.results_empty.hide()
        self._set_header_status("error", tr("toast.compile_failed"))
        self._set_status(tr("toast.compile_failed"), self._get_current_profile(), "error", "")
        self._toast.show_message(tr("toast.compile_failed"), "error", 4200)

    @Slot()
    def _on_worker_canceled(self) -> None:
        self._exit_working_state()
        self._toast.clear()
        self.simple_progress.set_indeterminate(False)
        self.simple_progress.setVisible(False)
        self.simple_stage_label.setText("")
        self.simple_result_card.clear()
        self.simple_result_card.chip.set_state("idle")
        self.simple_result_card.chip.set_text(tr("result.state.canceled"))
        self.simple_result_card.title_label.setText(tr("result.state.canceled"))
        self.simple_result_card.meta_label.setText(tr("result.canceled.hint"))
        self.simple_result_card.show()
        self.simple_skeleton.hide()
        self.simple_detail_card.hide()
        self.simple_metrics_panel.hide()
        self.simple_metrics_label.setText("")
        self.simple_quality_label.setText("")
        self.simple_files_label.setText("")
        self.simple_open_files_btn.setVisible(False)
        self._show_results()
        if hasattr(self, "hero_status"):
            self.hero_status.setText(tr("result.state.canceled"))
        self._set_header_status("warning", tr("toast.compile_canceled"))
        self._set_status(tr("toast.compile_canceled"), self._get_current_profile(), "cancelado", "")
        self._toast.show_message(tr("toast.compile_canceled"), "warning", 2600)

    # ─── Result rendering ──────────────────────────────────────────

    def _render_b9_fields(self, result: dict[str, Any]) -> None:
        quality = result.get("quality_report") or {}
        score = quality.get("score")
        issues = quality.get("issues") or []
        if score is None:
            self.simple_quality_label.setText("")
            self.simple_quality_label.setToolTip("")
        else:
            severity_rank = {"error": 0, "warning": 1, "info": 2}
            top = sorted(issues, key=lambda i: severity_rank.get(i.get("severity"), 3))[:8]
            counts = {"error": 0, "warning": 0, "info": 0}
            for issue in issues:
                severity = issue.get("severity", "info")
                counts[severity] = counts.get(severity, 0) + 1
            # Kept in the historical "Calidad: N/100 · …" shape: this label is a
            # documented contract (see tests/test_gui_b9.py) and is also parsed
            # by users' own scripts.
            prefix = "Quality" if tr("result.quality").startswith("Quality") else "Calidad"
            if prefix == "Calidad":
                self.simple_quality_label.setText(
                    f"Calidad: {score}/100 · {counts['error']} errores · "
                    f"{counts['warning']} avisos · {counts['info']} notas"
                )
            else:
                self.simple_quality_label.setText(
                    f"Quality: {score}/100 · {counts['error']} errors · "
                    f"{counts['warning']} warnings · {counts['info']} notes"
                )
            if top:
                tooltip = "\n".join(
                    f"[{i.get('severity', '?')}] {i.get('message', '')}" for i in top
                )
                more = len(issues) - len(top)
                if more > 0:
                    tooltip += "\n… " + tr("result.quality_more").format(count=more)
                self.simple_quality_label.setToolTip(tooltip)
            else:
                self.simple_quality_label.setToolTip(tr("result.quality_clean"))

        clarification = result.get("clarification") or {}
        questions = list(clarification.get("questions") or [])
        if not questions:
            questions = [
                str(q) for q in ((result.get("four_layers") or {}).get("open_questions") or [])
            ]
        if questions:
            body = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, start=1))
            if clarification.get("required"):
                body = tr("result.questions_required") + "\n\n" + body
        else:
            body = tr("result.questions_none")
        self.simple_questions_tab.setPlainText(body)

        count = len(questions)
        tab_title = (
            tr("result.tab.questions_count").format(count=count)
            if count
            else tr("result.tab.questions_none")
        )
        index = self.simple_tabs.indexOf(self.simple_questions_tab)
        if index >= 0:
            self.simple_tabs.setTabText(index, tab_title)

    def _render_result(self) -> None:
        if not self.result:
            self._set_status(tr("error.no_result"), self._get_current_profile(), "error", "")
            return
        result = self.result
        validation = result["context_loss_report"]
        score = validation.get("score", 0)
        profile = result["applied_profile"]
        warnings = len(validation.get("warnings", []))
        errors = len(validation.get("critical_losses", []))
        constraints = len(validation.get("critical_constraints_preserved", []))

        # ── simple mode ───────────────────────────────────────────────
        self.simple_result_card.set_result(result)
        self.simple_result_card.show()
        self.simple_empty_state.hide()
        self.simple_skeleton.hide()
        self.simple_detail_card.show()
        # The result card already owns score + counts; the separate health panel
        # would duplicate the same numbers on the same screen.
        self.simple_metrics_panel.hide()

        self.simple_result_header.setText(tr("toast.compile_done"))
        self.simple_metrics_label.setText(
            tr("result.summary").format(
                score=score, constraints=constraints, files=self._generated_file_count()
            )
        )

        self.simple_optimized_tab.setPlainText(result.get("optimized_prompt", ""))
        self.simple_report_tab.setPlainText(result.get("hybrid_markdown", ""))
        self.simple_validation_tab.setPlainText(result.get("context_loss_markdown", ""))
        self._render_b9_fields(result)

        self.simple_health.update_metrics(
            score=score, constraints=constraints, warnings=warnings, errors=errors
        )

        if self.last_saved_dir and self.last_saved_dir.exists():
            self.simple_files_label.setText(str(self.last_saved_dir))
            self.simple_open_files_btn.setVisible(True)
        else:
            self.simple_files_label.setText("")
            self.simple_open_files_btn.setVisible(False)

        # ── expert mode ───────────────────────────────────────────────
        self.extreme_health.update_metrics(
            score=score, constraints=constraints, warnings=warnings, errors=errors
        )
        self.extreme_health_panel.show()

        if hasattr(self, "summary_text"):
            self.summary_text.setPlainText(
                f"Perfil solicitado: {result['requested_profile']}\n"
                f"Perfil aplicado: {profile}\n"
                f"Motivo AUTO: {result.get('auto_info', {}).get('selection_reason', 'manual')}\n"
                f"Huella digital (SHA-256): {result['prompt_sha256']}\n"
                f"Puntuación de preservación: {score}/100\n"
                f"retention_score: {validation.get('retention_score', score)}\n"
                f"precision_score: {validation.get('precision_score', 0)}\n"
                f"unsupported_addition_score: {validation.get('unsupported_addition_score', 0)}\n"
                f"nsl_size_ratio: {validation.get('nsl_size_ratio', validation.get('compression_ratio_nsl', 0))}\n"
                f"execution_size_ratio: {validation.get('execution_size_ratio', validation.get('expansion_ratio_execution_prompt', 0))}\n"
                f"Restricciones preservadas: {', '.join(validation.get('critical_constraints_preserved', [])) or 'ninguna detectada'}\n"
                f"Advertencias: {', '.join(validation.get('warnings', [])) or 'ninguna'}\n"
                "Siguiente acción recomendada: copia el Prompt listo para usar.",
            )
        if hasattr(self, "original_text"):
            self.original_text.setPlainText(
                result["original"]
                if result.get("privacy_mode") == "full_original"
                else "[omitido por modo de privacidad]"
            )
        if hasattr(self, "hybrid_text"):
            self.hybrid_text.setPlainText(result.get("hybrid_markdown", ""))
        if hasattr(self, "optimized_text"):
            self.optimized_text.setPlainText(result.get("optimized_prompt", ""))
        if hasattr(self, "nsl_text"):
            self.nsl_text.setPlainText(result.get("chosen_nsl", ""))
        if hasattr(self, "json_text"):
            self.json_text.setPlainText(
                json.dumps(result.get("hybrid_json", {}), indent=2, ensure_ascii=False)
            )
        if hasattr(self, "seeds_text"):
            self.seeds_text.setPlainText(
                json.dumps(result.get("seeds", []), indent=2, ensure_ascii=False)
            )
        if hasattr(self, "constraints_text"):
            self.constraints_text.setPlainText(
                json.dumps(
                    result.get("semantic_ir", {}).get("effective_prompt_ir", {}),
                    indent=2,
                    ensure_ascii=False,
                )
            )
        if hasattr(self, "validation_text"):
            self.validation_text.setPlainText(result.get("context_loss_markdown", ""))
        if hasattr(self, "validation_detail"):
            self.validation_detail.setPlainText(result.get("context_loss_markdown", ""))
        if hasattr(self, "profile_text"):
            self.profile_text.setPlainText(
                json.dumps(result.get("profile_status", {}), indent=2, ensure_ascii=False)
            )
        if hasattr(self, "extreme_skeleton"):
            self.extreme_skeleton.hide()
            self.tabs.show()
            self.results_empty.hide()

        if validation.get("strict_status") == "blocked":
            self._set_status(tr("status.blocked"), profile, "bloqueado", "")
        else:
            self._set_status(tr("status.done"), profile, validation.get("profile_status", "pass"), "")
        self._toast.show_message(tr("toast.compile_done"), "success")

    def _generated_file_count(self) -> int:
        last = self.controller.last_result
        if not last:
            return 0
        return len(last.get("generated_files", []) or [])

    # ─── Clipboard / save ──────────────────────────────────────────

    def copy_recommended(self) -> None:
        if self.result:
            text = self.result.get("optimized_prompt", "")
        elif hasattr(self, "optimized_text"):
            text = self.optimized_text.toPlainText()
        else:
            text = ""
        if not text:
            self._toast.show_message(tr("toast.nothing_to_copy"), "warning")
            return
        QApplication.clipboard().setText(text)
        self.simple_result_card.copy_button.set_idle_text(tr("toast.copied"))
        self.simple_result_card.copy_button.setText(tr("toast.copied"))
        QTimer.singleShot(
            1600,
            lambda: self.simple_result_card.copy_button.set_idle_text(
                tr("result.action.copy")
            ),
        )
        self._set_status(tr("toast.copied"), self._get_current_profile(), "normal", "")
        self._toast.show_message(tr("toast.copied"), "success")

    def copy_json(self) -> None:
        if not hasattr(self, "json_text") or not self.json_text.toPlainText():
            self._toast.show_message(tr("toast.nothing_to_copy"), "warning")
            return
        QApplication.clipboard().setText(self.json_text.toPlainText())
        self._set_status(tr("toast.copied"), self._get_current_profile(), "normal", "")
        self._toast.show_message(tr("toast.copied"), "success")

    def save_all(self) -> None:
        if not self.result:
            self._toast.show_message(tr("toast.compile_first"), "warning")
            return
        default = self.settings.get("output_dir") or str(data_dir() / "outputs")
        path = QFileDialog.getExistingDirectory(self, tr("results.button.save"), default)
        if not path:
            return
        artifacts = self.controller.save_all(path)
        self.settings["output_dir"] = path
        self.last_saved_dir = Path(path)
        save_settings(self._collect_settings())
        self.simple_files_label.setText(path)
        self.simple_open_files_btn.setVisible(True)
        self.simple_metrics_label.setText(
            tr("result.summary").format(
                score=self.result["context_loss_report"].get("score", 0),
                constraints=len(
                    self.result["context_loss_report"].get(
                        "critical_constraints_preserved", []
                    )
                ),
                files=len(artifacts),
            )
        )
        self._toast.show_message(
            tr("toast.saved_path").format(path=path), "success", 3400
        )
        self._set_status(
            tr("toast.saved"),
            self.result["applied_profile"],
            self.result["context_loss_report"].get("profile_status", "pass"),
            path,
        )

    def open_last_output(self) -> None:
        configured = str(self.settings.get("output_dir", "")).strip()
        candidate = self.last_saved_dir or (Path(configured) if configured else None)
        if candidate is None or not candidate.exists():
            self._toast.show_message(tr("toast.no_folder"), "warning")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(candidate)))
        self._set_status(tr("toast.folder_opened"), self._get_current_profile(), "normal", "")

    def reset_configuration(self) -> None:
        reset_settings()
        self.settings = load_settings()
        self._restore_settings()
        self._set_status(tr("config.reset"), self._get_current_profile(), "normal", "")
        self._toast.show_message(tr("config.reset"), "success")

    # ─── Prompt actions ────────────────────────────────────────────

    def new_prompt(self) -> None:
        self.result = None
        self.simple_prompt_edit.clear()
        self.prompt_edit.clear()
        self.simple_result_card.clear()
        self.simple_metrics_panel.hide()
        self.simple_detail_card.hide()
        self.simple_skeleton.hide()
        self.simple_progress.set_indeterminate(False)
        self.simple_progress.setVisible(False)
        self.simple_stage_label.setText("")
        self._clear_inline_error()
        self._show_home()
        self.progress_strip_reset()
        self.extreme_health_panel.hide()
        self._set_status(tr("status.new_prompt"), self._get_current_profile(), "normal", "")

    def progress_strip_reset(self) -> None:
        if hasattr(self, "progress"):
            self.progress.set_indeterminate(False)
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setVisible(False)
        if hasattr(self, "hero_status"):
            self.hero_status.setText(tr("status.ready_prompt"))

    def paste_prompt(self) -> None:
        text = QApplication.clipboard().text()
        editor = self._current_editor()
        if editor is not None and text:
            editor.insertPlainText(text)
            self._toast.show_message(tr("toast.pasted"), "info", 1800)

    def load_example(self) -> None:
        if not EXAMPLE_PATH.exists():
            return
        content = EXAMPLE_PATH.read_text(encoding="utf-8")
        self._load_prompt_text(content, tr("toast.example_loaded"))

    def load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("simple.button.load_file"), str(ROOT), "Textos (*.txt *.md);;Todos (*)"
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            self._toast.show_message(str(exc), "error")
            return
        self._load_prompt_text(content, tr("toast.file_loaded").format(name=Path(path).name))

    def _load_prompt_text(self, content: str, confirmation: str) -> None:
        editor = self._current_editor()
        if editor is not None:
            editor.setPlainText(content)
            editor.setFocus(Qt.FocusReason.OtherFocusReason)
        if self._current_mode == MODE_EXTREME:
            self._select_page("compilar")
        self._toast.show_message(confirmation, "info", 2000)

    def analyze_only(self) -> None:
        had_result = bool(self.result)
        self.compile_current()
        if had_result:
            self._switch_to_mode(MODE_EXTREME)
            self._select_page("validacion")

    def compile_auto(self) -> None:
        self.simple_profile_combo.setCurrentText("AUTO")
        self.profile_combo.setCurrentText("AUTO")
        if self._get_current_prompt().strip():
            self.compile_current()

    # ─── Glossary ──────────────────────────────────────────────────

    def _refresh_glossary(self) -> None:
        if not hasattr(self, "glossary_list"):
            return
        current = self.glossary_list.currentItem()
        current_id = current.data(Qt.ItemDataRole.UserRole) if current else ""
        query = self.glossary_search.text() if hasattr(self, "glossary_search") else ""
        category = (
            self.glossary_category.currentText()
            if hasattr(self, "glossary_category")
            else "Todas"
        )
        matches = search_glossary(query, category)
        self.glossary_list.blockSignals(True)
        self.glossary_list.clear()
        for entry in matches:
            item = QListWidgetItem(f"{entry['term']}  ·  {entry['simple_name']}")
            item.setData(Qt.ItemDataRole.UserRole, entry["id"])
            self.glossary_list.addItem(item)
            if entry["id"] == current_id:
                self.glossary_list.setCurrentItem(item)
        self.glossary_list.blockSignals(False)
        self.glossary_count.setText(
            tr("glossary.count").format(count=len(load_glossary()))
        )
        if not matches:
            self.glossary_detail.setPlainText(tr("glossary.empty"))
            return
        if not self.glossary_list.currentItem():
            self.glossary_list.setCurrentRow(0)

    def _on_glossary_selection_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        entry = get_entry(str(current.data(Qt.ItemDataRole.UserRole)))
        if entry:
            self.glossary_detail.setPlainText(
                format_entry(entry, self._current_mode == MODE_EXTREME)
            )

    def open_glossary_term(self, term_id: str | None) -> None:
        self._switch_to_mode(MODE_EXTREME)
        self._select_page("glosario")
        if not term_id:
            self.glossary_search.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        entry = get_entry(term_id)
        self.glossary_search.setText(entry["term"] if entry else term_id)
        self._refresh_glossary()
        for index in range(self.glossary_list.count()):
            item = self.glossary_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == (entry["id"] if entry else term_id):
                self.glossary_list.setCurrentItem(item)
                break
        self.glossary_search.setFocus(Qt.FocusReason.OtherFocusReason)

    def copy_glossary_explanation(self) -> None:
        QApplication.clipboard().setText(self.glossary_detail.toPlainText())
        self._toast.show_message(tr("glossary.copied"), "success")

    # ─── Advanced mode bridge ──────────────────────────────────────

    def _compile_from_advanced(self) -> None:
        if not hasattr(self, "_advanced_page"):
            return
        combined = self._advanced_page.get_combined_prompt().strip()
        if not combined:
            self._toast.show_message(tr("mode.advanced.no_content"), "warning")
            return
        self.prompt_edit.setPlainText(combined)
        self.simple_prompt_edit.blockSignals(True)
        self.simple_prompt_edit.setPlainText(combined)
        self.simple_prompt_edit.blockSignals(False)
        self._select_page("compilar")
        self.compile_current()

    def _on_advanced_sections_changed(self, data: dict) -> None:
        self._advanced_sections_dirty = True

    # ─── i18n ──────────────────────────────────────────────────────

    def _retranslate_ui(self) -> None:
        self.header.set_mode(self._current_mode)
        self.sidebar.retranslate()
        self.status_bar.set_mode(self._current_mode)
        self.status_bar.set_profile(self._get_current_profile())

        self.home_header.set_title(tr("simple.title"))
        self.home_header.set_subtitle(tr("simple.subtitle"))
        self.dashboard_header.set_title(tr("nav.page.dashboard"))
        self.dashboard_header.set_subtitle(tr("page.dashboard.subtitle"))
        self.compiler_header.set_title(tr("nav.page.compiler"))
        self.compiler_header.set_subtitle(tr("page.compiler.subtitle"))
        self.results_header.set_title(tr("nav.page.results"))
        self.results_header.set_subtitle(tr("page.results.subtitle"))
        self.validation_header.set_title(tr("nav.page.validation"))
        self.validation_header.set_subtitle(tr("page.validation.subtitle"))
        self.profiles_header.set_title(tr("nav.page.profiles"))
        self.profiles_header.set_subtitle(tr("page.profiles.subtitle"))
        self.glossary_header.set_title(tr("nav.page.glossary"))
        self.glossary_header.set_subtitle(tr("page.glossary.subtitle"))
        self.settings_header.set_title(tr("nav.page.settings"))
        self.settings_header.set_subtitle(tr("page.settings.subtitle"))

        self.simple_prompt_label.setText(tr("home.input_label"))
        self.simple_prompt_edit.setPlaceholderText(tr("simple.placeholder"))
        self.simple_help_text.setText(tr("home.input_help"))
        self.example_button.setText(tr("simple.button.example"))
        self.clear_button.setText(tr("simple.button.clear"))
        self.history_button.setText(tr("simple.button.history"))
        self.simple_compile_btn.setText(tr("simple.button.compile"))
        self.simple_cancel_btn.setText(tr("simple.button.cancel"))
        self.rail_title.setText(tr("home.rail.title"))
        self.rail_help.setText(tr("home.rail.help"))
        self.rail_profile_label.setText(tr("simple.label.profile"))
        self.rail_profile_help.setText(tr("home.rail.profile_help"))
        self.rail_model_label.setText(tr("simple.label.model"))
        self.rail_level_label.setText(tr("simple.label.level"))
        self.rail_privacy_label.setText(tr("simple.label.privacy"))
        self.simple_strict_check.setText(tr("simple.check.strict"))
        self.simple_preserve_check.setText(tr("simple.check.preserve"))
        profile = self._get_current_profile()
        self.simple_profile_hint.setText(
            tr("profile.auto_recommended") if profile == "AUTO" else profile
        )

        self.simple_result_card.copy_button.set_idle_text(tr("result.action.copy"))
        self.simple_result_card.copy_button.setText(tr("result.action.copy"))
        self.simple_result_card.save_button.setText(tr("result.action.save"))
        self.simple_result_card.new_button.setText(tr("result.action.new"))
        self.result_header.set_title(tr("result.page.title"))
        self.result_header.set_subtitle(tr("result.page.subtitle"))
        self.result_new_button.setText(tr("result.action.new"))
        self.simple_detail_card._title_label.setText(tr("result.detail.title"))
        self.simple_detail_card._subtitle_label.setText(tr("result.detail.help"))
        self.simple_tabs.setTabText(0, tr("result.tab.optimized"))
        self.simple_tabs.setTabText(1, tr("result.tab.report"))
        self.simple_tabs.setTabText(2, tr("result.tab.validation"))
        self.simple_tabs.setTabText(3, tr("result.tab.questions_none"))
        if self.result:
            self._render_b9_fields(self.result)

        self.tools_title.setText(tr("section.tools"))
        self.strict_check.setText(tr("simple.check.strict"))
        self.preserve_check.setText(tr("simple.check.preserve"))
        self.appearance_title.setText(tr("settings.appearance"))
        self.behaviour_title.setText(tr("settings.behavior"))
        self.data_title.setText(tr("settings.data_location"))
        self.data_help.setText(tr("settings.data_location.help"))
        self.reduce_motion_check.setText(tr("settings.reduce_motion"))
        self.reduce_motion_help.setText(tr("settings.reduce_motion.help"))
        self.reset_button.setText(tr("settings.reset"))
        self.startup_mode_combo.setItemText(0, tr("status.mode_simple"))
        self.startup_mode_combo.setItemText(1, tr("status.mode_extreme"))
        self.theme_combo.setItemText(0, tr("settings.theme.dark"))
        self.theme_combo.setItemText(1, tr("settings.theme.light"))
        _fill_combo(self.level_combo, _levels())
        _fill_combo(self.simple_level_combo, _levels())
        _fill_combo(self.privacy_combo, _privacy_modes())
        _fill_combo(self.simple_privacy_combo, _privacy_modes())
        for card, (_name, description_key) in zip(
            self.profile_cards, PROFILE_DEFINITIONS
        ):
            body = card.content()
            labels = body.itemAt(1).widget()
            if labels is not None:
                labels.setText(tr(description_key))
        self.copy_button.setText(tr("results.button.copy_prompt"))
        self.copy_glossary_button.setText(tr("glossary.copy"))
        self.glossary_search.setPlaceholderText(tr("glossary.search_placeholder"))
        self._counters_retranslate()

    def _counters_retranslate(self) -> None:
        text = self._get_current_prompt()
        chars, tokens = estimate_counters(text)
        for label in (
            getattr(self, "char_label", None),
            getattr(self, "char_label2", None),
            getattr(self, "simple_char_label", None),
        ):
            if label is not None:
                label.setText(tr("home.characters").format(count=chars))
        for label in (
            getattr(self, "token_label", None),
            getattr(self, "token_label2", None),
            getattr(self, "simple_token_label", None),
        ):
            if label is not None:
                label.setText(tr("home.tokens").format(count=tokens))

    # ─── Window events ─────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_toast"):
            self._toast.reposition()
        if hasattr(self, "sidebar"):
            # Keep the content area usable: below ~1060 px the sidebar folds.
            self.sidebar.set_collapsed(self.width() < 1060)

    def closeEvent(self, event) -> None:
        if self._is_compiling():
            self.cancel_requested = True
            if self.worker:
                self.worker.cancel()
            self.worker_thread.quit()
            self.worker_thread.wait(3000)
        save_settings(self._collect_settings())
        super().closeEvent(event)

    # ─── Project save / load ───────────────────────────────────────

    def _save_project(self) -> None:
        from datetime import datetime, timezone

        prompt = self._get_current_prompt()
        if not prompt.strip():
            self._toast.show_message(tr("error.empty_input"), "warning")
            return
        default = str(data_dir() / "projects")
        path, _ = QFileDialog.getSaveFileName(
            self, tr("project.save"), default, "Proyecto NPSC (*.npsc.json)"
        )
        if not path:
            return
        if not path.endswith(".npsc.json"):
            path += ".npsc.json"
        project = {
            "schema_version": "1.0",
            "project_name": Path(path).stem,
            "prompt_version": "1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "target_profile": self._get_current_profile(),
            "mode": self._current_mode,
            "informal_input": prompt,
            "sections": {},
            "variables": self._variable_values,
            "tags": [],
            "history": [],
        }
        if self.result:
            project["last_result"] = {
                "optimized_prompt": self.result.get("optimized_prompt", ""),
                "applied_profile": self.result.get("applied_profile", ""),
                "target": self.result.get("target", "auto"),
            }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(project, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        self._toast.show_message(
            tr("toast.project_saved").format(name=Path(path).name), "success"
        )

    def _load_project(self) -> None:
        default = str(data_dir() / "projects")
        path, _ = QFileDialog.getOpenFileName(
            self, tr("project.load"), default, "Proyecto NPSC (*.npsc.json)"
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self._toast.show_message(str(exc), "error")
            return
        informal = data.get("informal_input", "")
        if informal:
            self.simple_prompt_edit.setPlainText(informal)
            self.prompt_edit.setPlainText(informal)
        self._variable_values = data.get("variables", {})
        profile = data.get("target_profile", "AUTO")
        self.simple_profile_combo.setCurrentText(profile)
        self.profile_combo.setCurrentText(profile)
        self._toast.show_message(
            tr("toast.project_loaded").format(
                name=data.get("project_name", Path(path).name)
            ),
            "success",
        )

    def _show_variable_dialog(self) -> None:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit

        prompt = self._get_current_prompt()
        found = extract_variables(prompt)
        if not found:
            self._toast.show_message(tr("variables.none"), "info")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("variables.title"))
        dialog.setMinimumSize(420, 180)
        layout = QFormLayout(dialog)
        edits: dict[str, QLineEdit] = {}
        for name in found:
            edit = QLineEdit()
            edit.setPlaceholderText(tr("variables.placeholder").format(name=name))
            edit.setText(self._variable_values.get(name, ""))
            layout.addRow(f"{{{{{name}}}}}", edit)
            edits[name] = edit
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        for name, edit in edits.items():
            value = edit.text().strip()
            if value:
                self._variable_values[name] = value
        filled = sum(1 for name in found if self._variable_values.get(name, "").strip())
        self._toast.show_message(
            tr("variables.filled").format(filled=filled, total=len(found)), "success"
        )


def create_application(argv: list[str] | None = None) -> tuple[QApplication, MainWindow]:
    """Build the QApplication + MainWindow with the design system installed."""
    import sys

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("NeuroPrompt Semantic Compiler")
    app.setOrganizationName("NPSC")
    settings = load_settings()
    apply_design(app, get_theme(str(settings.get("theme", "dark"))))
    window = MainWindow()
    return app, window








