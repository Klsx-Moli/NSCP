"""Application chrome — header, sidebar and status bar.

The chrome owns no product logic: it renders the current mode/status and emits
signals upward. Keeping it here keeps ``main_window.py`` focused on workflow.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from i18n import tr
from npsc_gui.components.buttons import IconButton
from npsc_gui.components.icons import icon
from npsc_gui.components.nav_group import NavGroup, NavItem
from npsc_gui.components.status_chip import StatusChip
from npsc_gui.design.style import active_theme


class _SidebarToggle(QPushButton):
    """Quiet chevron button used only to fold/unfold the sidebar."""

    def __init__(self, parent=None) -> None:
        super().__init__("", parent)
        self.setObjectName("SidebarToggle")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


class Header(QFrame):
    """Compact top bar: identity, current mode, global state, global actions."""

    mode_toggle_requested = Signal()
    settings_requested = Signal()
    help_requested = Signal()
    about_requested = Signal()
    context_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Header")
        theme = active_theme()
        s = theme.spacing
        m = theme.metrics
        self.setFixedHeight(m.header_height)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(s.lg, 0, s.md, 0)
        layout.setSpacing(s.sm)

        brand = QLabel("N")
        brand.setObjectName("BrandGlyph")
        brand.setFixedSize(28, 28)
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setToolTip("NeuroPrompt Semantic Compiler")

        wordmark = QLabel("NeuroPrompt")
        wordmark.setObjectName("BrandWordmark")

        self.subtitle = QLabel(tr("app.subtitle"))
        self.subtitle.setObjectName("AppSubtitle")

        divider = QLabel()
        divider.setObjectName("HeaderDivider")
        divider.setFixedSize(1, 16)

        self.version_label = QLabel("v1.0.0")
        self.version_label.setObjectName("AppSubtitle")

        layout.addWidget(brand)
        layout.addSpacing(2)
        layout.addWidget(wordmark)
        layout.addWidget(divider)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.version_label)
        layout.addStretch(1)

        self.chip = StatusChip(tr("status.ready"), "ready")
        layout.addWidget(self.chip)

        self.mode_button = QPushButton(tr("mode.activate_extreme"))
        self.mode_button.setObjectName("ModeToggleBtn")
        self.mode_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_button.clicked.connect(self.mode_toggle_requested)
        layout.addWidget(self.mode_button)
        self.context_button = QPushButton("Compressor")
        self.context_button.setToolTip("Open local context workbench")
        self.context_button.clicked.connect(self.context_requested)
        layout.addWidget(self.context_button)

        spacer = QWidget()
        spacer.setFixedWidth(s.xs)
        layout.addWidget(spacer)

        self.about_button = IconButton("", tr("about.title"), self)
        self.about_button.setIcon(icon("info", 16, theme.palette.text_tertiary))
        self.about_button.clicked.connect(self.about_requested)
        self.settings_button = IconButton("", tr("settings.title"), self)
        self.settings_button.setIcon(icon("settings", 16, theme.palette.text_tertiary))
        self.settings_button.clicked.connect(self.settings_requested)
        self.help_button = IconButton("", "Ayuda", self)
        self.help_button.setIcon(icon("help", 16, theme.palette.text_tertiary))
        self.help_button.clicked.connect(self.help_requested)

        layout.addWidget(self.about_button)
        layout.addWidget(self.settings_button)
        layout.addWidget(self.help_button)

    # ── API ───────────────────────────────────────────────────────────────

    def set_mode(self, mode: str) -> None:
        if mode == "simple":
            self.mode_button.setText(tr("mode.activate_extreme"))
            self.mode_button.setToolTip(tr("mode.activate_extreme"))
            self.subtitle.setText(tr("app.subtitle"))
        else:
            self.mode_button.setText(tr("mode.activate_simple"))
            self.mode_button.setToolTip(tr("mode.activate_simple"))
            self.subtitle.setText(tr("app.subtitle"))

    def set_state(self, state: str, text: str) -> None:
        self.chip.set_state(state)
        self.chip.set_text(text)

    def retranslate(self) -> None:
        self.subtitle.setText(tr("app.subtitle"))
        self.about_button.setToolTip(tr("about.title"))
        self.settings_button.setToolTip(tr("settings.title"))
        self.mode_button.setText(
            tr("mode.activate_extreme") if "extreme" not in self.mode_button.text().lower()
            and False else self.mode_button.text()
        )


class Sidebar(QFrame):
    """Grouped navigation. Collapses to a narrow rail on demand."""

    page_requested = Signal(str)
    collapsed_changed = Signal(bool)

    GROUPS = (
        ("nav.group.main", ("resumen", "compilar", "resultados", "validacion")),
        ("nav.group.tools", ("perfiles", "glosario", "plantillas", "avanzado")),
        ("nav.group.history", ("historial",)),
        ("nav.group.system", ("configuracion",)),
    )

    LABELS = {
        "resumen": "nav.page.dashboard",
        "compilar": "nav.page.compiler",
        "resultados": "nav.page.results",
        "validacion": "nav.page.validation",
        "perfiles": "nav.page.profiles",
        "glosario": "nav.page.glossary",
        "plantillas": "nav.page.templates",
        "avanzado": "nav.page.advanced",
        "historial": "nav.page.history",
        "configuracion": "nav.page.settings",
    }

    COLLAPSED_WIDTH = 56

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        theme = active_theme()
        s = theme.spacing
        self._expanded_width = theme.metrics.sidebar_width
        self._collapsed = False
        self.setFixedWidth(self._expanded_width)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, s.md, 0, s.md)
        layout.setSpacing(0)

        self._groups: list[NavGroup] = []
        self._items: dict[str, NavItem] = {}
        for group_key, pages in self.GROUPS:
            group = NavGroup(tr(group_key))
            for page in pages:
                item = group.add_item(page, tr(self.LABELS[page]))
                item.clicked_page.connect(self.page_requested)
                self._items[page] = item
            layout.addWidget(group)
            self._groups.append(group)

        layout.addStretch(1)

        self._toggle = _SidebarToggle(self)
        self._toggle.setFixedSize(28, 24)
        self._toggle.setToolTip(tr("nav.collapse.tooltip"))
        self._toggle.setIcon(icon("chevron-left", 14, theme.palette.text_tertiary))
        self._toggle.clicked.connect(self.toggle_collapsed)
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(s.md, 0, 0, s.sm)
        toggle_row.addWidget(self._toggle)
        toggle_row.addStretch(1)
        layout.addLayout(toggle_row)

        self.footer = QLabel("Offline · local")
        self.footer.setObjectName("MicroLabel")
        self.footer.setContentsMargins(s.lg, 0, 0, 0)
        layout.addWidget(self.footer)

    @property
    def items(self) -> dict[str, NavItem]:
        return self._items

    def select(self, page: str) -> None:
        for key, item in self._items.items():
            item.setChecked(key == page)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.setFixedWidth(
            self.COLLAPSED_WIDTH if collapsed else self._expanded_width
        )
        theme = active_theme()
        self._toggle.setIcon(
            icon(
                "chevron-right" if collapsed else "chevron-left",
                14,
                theme.palette.text_tertiary,
            )
        )
        self._toggle.setToolTip(
            tr("nav.expand.tooltip") if collapsed else tr("nav.collapse.tooltip")
        )
        for group in self._groups:
            group.set_collapsed(collapsed)
        self.footer.setVisible(not collapsed)
        self.collapsed_changed.emit(collapsed)

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def retranslate(self) -> None:
        for group, (group_key, pages) in zip(self._groups, self.GROUPS):
            group.set_label(tr(group_key))
            for page in pages:
                self._items[page].setProperty("fullText", tr(self.LABELS[page]))
                self._items[page].setText(tr(self.LABELS[page]))
            if self._collapsed:
                group.set_collapsed(True)
        self._toggle.setToolTip(
            tr("nav.expand.tooltip") if self._collapsed else tr("nav.collapse.tooltip")
        )


class StatusBar(QFrame):
    """Thin footer: what happened, which profile, which mode, where data lives."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusBar")
        theme = active_theme()
        s = theme.spacing
        self.setFixedHeight(theme.metrics.statusbar_height)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(s.md, 0, s.md, 0)
        layout.setSpacing(s.sm)

        self.dot = QLabel()
        self._set_dot(theme.palette.text_tertiary)

        self.message = QLabel(tr("status.ready"))
        self.message.setObjectName("MicroLabel")

        self.profile = QLabel("")
        self.profile.setObjectName("MicroLabel")

        self.mode = QLabel(tr("status.mode_simple"))
        self.mode.setObjectName("MicroLabel")

        self.detail = QLabel("Offline · local")
        self.detail.setObjectName("MicroLabel")

        layout.addWidget(self.dot)
        layout.addWidget(self.message)
        layout.addWidget(self._dot_sep())
        layout.addWidget(self.profile)
        layout.addWidget(self._dot_sep())
        layout.addWidget(self.mode)
        layout.addStretch(1)
        layout.addWidget(self.detail)

    def _dot_sep(self) -> QLabel:
        sep = QLabel("·")
        sep.setObjectName("MicroLabel")
        return sep

    def _set_dot(self, colour: str) -> None:
        self.dot.setFixedSize(6, 6)
        self.dot.setStyleSheet(
            f"background: {colour}; border-radius: 3px; border: none;"
        )

    def set_message(self, message: str, semantic: str = "idle") -> None:
        palette = active_theme().palette
        colours = {
            "idle": palette.text_tertiary,
            "ready": palette.success,
            "working": palette.accent_brand,
            "success": palette.success,
            "warning": palette.warning,
            "error": palette.error,
        }
        self._set_dot(colours.get(semantic, palette.text_tertiary))
        self.message.setText(message)

    def set_profile(self, profile: str) -> None:
        self.profile.setText(f"{tr('simple.label.profile')}: {profile}" if profile else "")

    def set_mode(self, mode: str) -> None:
        self.mode.setText(
            tr("status.mode_simple") if mode == "simple" else tr("status.mode_extreme")
        )
        # Historical status-bar contract (tests and user habits): "Modo: …".
        self.mode.setText(f"Modo: {'Sencillo' if mode == 'simple' else 'Extremo'}")

    def set_detail(self, detail: str) -> None:
        self.detail.setText(detail)

    def retranslate(self, mode: str, profile: str, message: str) -> None:
        self.set_mode(mode)
        self.set_profile(profile)
        self.message.setText(message)


__all__ = ["Header", "Sidebar", "StatusBar"]
