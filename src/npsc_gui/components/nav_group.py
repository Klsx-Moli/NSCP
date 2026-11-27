"""Nav group — sidebar navigation group with label and items."""
from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

from npsc_gui.design.style import active_theme


class NavItem(QPushButton):
    """Single navigation item in sidebar."""

    clicked_page = Signal(str)

    def __init__(self, page_id: str, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("NPSCNavItem")
        self.setProperty("nav", "true")
        self.setCheckable(True)
        self._page_id = page_id
        self.clicked.connect(lambda _checked=False: self.clicked_page.emit(self._page_id))

    @property
    def page_id(self) -> str:
        return self._page_id


class NavGroup(QFrame):
    """Group of NavItems with an uppercase label."""

    def __init__(self, label: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NPSCNavGroup")
        self._items: list[NavItem] = []
        self._collapsed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._label = QLabel(label)
        self._label.setObjectName("NavGroupLabel")
        self._label.setVisible(bool(label))
        layout.addWidget(self._label)

        self._layout = layout

    def set_label(self, label: str) -> None:
        self._label.setText(label)
        self._label.setVisible(bool(label) and not self._collapsed)

    def add_item(self, page_id: str, text: str) -> NavItem:
        item = NavItem(page_id, text)
        self._items.append(item)
        self._layout.addWidget(item)
        return item

    def set_collapsed(self, collapsed: bool) -> None:
        """Hide group labels and item text, keeping each item focusable."""

        self._collapsed = collapsed
        self._label.setVisible(not collapsed and bool(self._label.text()))
        palette = active_theme().palette
        for item in self._items:
            if not item.property("fullText"):
                item.setProperty("fullText", item.text())
            if collapsed:
                item.setText("")
                item.setIcon(self._icon_for(item.page_id, palette.text_secondary))
                item.setIconSize(QSize(16, 16))
                item.setToolTip(str(item.property("fullText")))
                item.setAccessibleName(str(item.property("fullText")))
            else:
                item.setIcon(QIcon())
                item.setText(str(item.property("fullText")))
                item.setToolTip("")

    _ICONS = {
        "resumen": "layers",
        "compilar": "spark",
        "resultados": "check",
        "validacion": "check",
        "perfiles": "settings",
        "glosario": "info",
        "plantillas": "copy",
        "avanzado": "settings",
        "historial": "chevron-down",
        "configuracion": "settings",
    }

    def _icon_for(self, page_id: str, colour: str):
        from npsc_gui.components.icons import icon

        return icon(self._ICONS.get(page_id, "spark"), 16, colour)

    @property
    def items(self) -> list[NavItem]:
        return list(self._items)
