"""SegmentedControl — mutually exclusive mode/option switch."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton

from npsc_gui.design.style import active_theme


class SegmentedControl(QFrame):
    """A row of exclusive segments. Use it for equivalent modes, not for tabs."""

    activated = Signal(int)
    segment_activated = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NPSCSegmentedControl")
        theme = active_theme()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self._on_id_clicked)
        self._buttons: list[QPushButton] = []

    def add_segment(self, text: str, data: str = "") -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("NPSCSegment")
        button.setCheckable(True)
        segment_id = len(self._buttons)
        self._group.addButton(button, segment_id)
        self._buttons.append(button)
        self.layout().addWidget(button)
        if data:
            button.setProperty("segmentData", data)
        return button

    def set_segments(self, items: list[tuple[str, str]]) -> None:
        for button in self._buttons:
            self.layout().removeWidget(button)
            button.deleteLater()
        self._buttons.clear()
        for text, data in items:
            self.add_segment(text, data)

    def current_index(self) -> int:
        return self._group.checkedId()

    def current_data(self) -> str:
        index = self.current_index()
        if 0 <= index < len(self._buttons):
            return str(self._buttons[index].property("segmentData"))
        return ""

    def set_current_index(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)

    def set_current_data(self, data: str) -> None:
        for index, button in enumerate(self._buttons):
            if str(button.property("segmentData")) == data:
                button.setChecked(True)
                self.activated.emit(index)
                return

    def _on_id_clicked(self, index: int) -> None:
        self.activated.emit(index)
        self.segment_activated.emit(self.current_data())


__all__ = ["SegmentedControl"]
