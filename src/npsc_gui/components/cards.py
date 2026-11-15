"""Surface components — Card, ResultCard, MetricTile, EmptyState, PageHeader.

``ResultCard`` is the visual centre of the product: it carries the compiled
prompt, the validation score, the metadata and the next actions. Nothing else
on screen is allowed to compete with it.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from i18n import tr
from npsc_gui.components.buttons import PrimaryButton, SecondaryButton
from npsc_gui.components.status_chip import StatusChip
from npsc_gui.design.style import active_theme

_SEMANTIC_BY_SCORE = (
    (85, "success"),
    (60, "warning"),
    (0, "error"),
)


def _score_semantic(score: int) -> str:
    for threshold, semantic in _SEMANTIC_BY_SCORE:
        if score >= threshold:
            return semantic
    return "error"


def _refresh(*widgets: QWidget) -> None:
    for widget in widgets:
        widget.style().unpolish(widget)
        widget.style().polish(widget)


class Card(QFrame):
    """Elevated surface with optional title/subtitle and a content area."""

    def __init__(self, title: str = "", subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NPSCCard")
        theme = active_theme()
        s = theme.spacing

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(s.xl, s.lg, s.xl, s.lg)
        self._layout.setSpacing(s.md)

        if title or subtitle:
            head = QVBoxLayout()
            head.setSpacing(2)
            if title:
                self._title_label = QLabel(title)
                self._title_label.setObjectName("ResultTitle")
                head.addWidget(self._title_label)
            if subtitle:
                self._subtitle_label = QLabel(subtitle)
                self._subtitle_label.setObjectName("ResultMeta")
                self._subtitle_label.setWordWrap(True)
                head.addWidget(self._subtitle_label)
            self._layout.addLayout(head)
            separator = QFrame()
            separator.setObjectName("CardSeparator")
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFixedHeight(1)
            self._layout.addWidget(separator)

        self._content = QVBoxLayout()
        self._content.setSpacing(s.sm)
        self._layout.addLayout(self._content, 1)

    def content(self) -> QVBoxLayout:
        return self._content

    def add_row(self, widget: QWidget) -> None:
        self._content.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._content.addLayout(layout)


class MetricTile(QFrame):
    """Compact metric: value, caption and an optional thin meter."""

    def __init__(
        self,
        caption: str,
        value: str = "—",
        semantic: str = "muted",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NPSCMetricPill")
        theme = active_theme()
        s = theme.spacing
        self._semantic = semantic

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s.md, s.sm, s.md, s.sm)
        layout.setSpacing(1)

        self._value = QLabel(value)
        self._value.setObjectName("MetricValue")
        self._value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._caption = QLabel(caption)
        self._caption.setObjectName("MetricCaption")

        layout.addWidget(self._value)
        layout.addWidget(self._caption)
        self.set_semantic(semantic)

    def value(self) -> str:
        return self._value.text()

    def set_value(self, value: str) -> None:
        self._value.setText(value)

    def caption(self) -> str:
        return self._caption.text()

    def set_caption(self, caption: str) -> None:
        self._caption.setText(caption)

    def set_semantic(self, semantic: str) -> None:
        self._semantic = semantic
        self._value.setProperty("semantic", semantic)
        palette = active_theme().palette
        colour = {
            "success": palette.success,
            "info": palette.accent_brand,
            "warning": palette.warning,
            "error": palette.error,
            "muted": palette.text_tertiary,
        }.get(semantic, palette.text_secondary)
        self._value.setStyleSheet(
            f"color: {colour}; background: transparent; border: none;"
        )


class ResultCard(QFrame):
    """The result is the product: score, metadata, content and next actions."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NPSCResultCard")
        self.setProperty("resultState", "idle")
        theme = active_theme()
        s = theme.spacing

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s.xl, s.lg, s.xl, s.lg)
        layout.setSpacing(s.md)

        # ── header: state chip · title/meta · score block ─────────────────
        header = QHBoxLayout()
        header.setSpacing(s.lg)

        titles = QVBoxLayout()
        titles.setSpacing(s.xs)
        self.chip = StatusChip(tr("result.state.idle"), "idle")
        chip_row = QHBoxLayout()
        chip_row.setSpacing(s.sm)
        chip_row.addWidget(self.chip)
        chip_row.addStretch(1)
        titles.addLayout(chip_row)

        self.title_label = QLabel(tr("result.state.idle"))
        self.title_label.setObjectName("ResultTitle")
        titles.addWidget(self.title_label)

        self.meta_label = QLabel("")
        self.meta_label.setObjectName("ResultMeta")
        self.meta_label.setWordWrap(True)
        titles.addWidget(self.meta_label)
        header.addLayout(titles, 1)

        score_col = QVBoxLayout()
        score_col.setSpacing(0)
        score_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.score_label = QLabel("—")
        self.score_label.setObjectName("ResultCardValue")
        self.score_label.setProperty("semantic", "muted")
        self.score_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.score_caption = QLabel(tr("result.score"))
        self.score_caption.setObjectName("ResultCardLabel")
        self.score_caption.setAlignment(Qt.AlignmentFlag.AlignRight)
        score_col.addWidget(self.score_label)
        score_col.addWidget(self.score_caption)
        header.addLayout(score_col, 0)
        layout.addLayout(header)

        separator = QFrame()
        separator.setObjectName("CardSeparator")
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFixedHeight(1)
        layout.addWidget(separator)

        # ── counts row: real metrics, no decorative placeholders ──────────
        metrics = QHBoxLayout()
        metrics.setSpacing(s.sm)
        self.metric_constraints = MetricTile(tr("result.constraints"), "—", "muted")
        self.metric_warnings = MetricTile(tr("result.warnings"), "—", "muted")
        self.metric_errors = MetricTile(tr("result.errors"), "—", "muted")
        for tile in (self.metric_constraints, self.metric_warnings, self.metric_errors):
            metrics.addWidget(tile, 1)
        layout.addLayout(metrics)

        self.counts_label = QLabel("")
        self.counts_label.setObjectName("ResultMeta")
        self.counts_label.setVisible(False)
        layout.addWidget(self.counts_label)

        # ── body: the compiled prompt ─────────────────────────────────────
        self.body = QPlainTextEdit()
        self.body.setReadOnly(True)
        self.body.setObjectName("ResultBody")
        self.body.setPlaceholderText(tr("result.empty.hint"))
        self.body.setMinimumHeight(160)
        self.body.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.body, 1)

        # ── actions ───────────────────────────────────────────────────────
        actions = QHBoxLayout()
        actions.setSpacing(s.sm)
        self.copy_button = PrimaryButton(tr("result.action.copy"))
        self.save_button = SecondaryButton(tr("result.action.save"))
        self.new_button = SecondaryButton(tr("result.action.new"))
        self.copy_button.setEnabled(False)
        self.save_button.setEnabled(False)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.save_button)
        actions.addWidget(self.new_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self._result: dict[str, Any] | None = None

    # ── public API ────────────────────────────────────────────────────────

    @property
    def result(self) -> dict[str, Any] | None:
        return self._result

    def set_result(self, result: dict[str, Any] | None) -> None:
        """Populate the card from a compile result dictionary."""
        self._result = result
        if not result:
            self.clear()
            return

        validation = result.get("context_loss_report") or {}
        score = int(validation.get("score") or 0)
        warnings = list(validation.get("warnings") or [])
        errors = list(validation.get("critical_losses") or [])
        constraints = list(validation.get("critical_constraints_preserved") or [])

        if errors:
            state = "error"
        elif validation.get("strict_status") == "blocked":
            state = "error"
        elif warnings:
            state = "warning"
        else:
            state = "success"

        self.chip.set_state(state)
        self.chip.set_text(tr(f"result.state.{state}"))
        self.title_label.setText(tr("result.title"))
        self.score_label.setText(str(score))
        self.score_label.setProperty("semantic", _score_semantic(score))
        _refresh(self.score_label)

        profile = result.get("applied_profile", "—")
        target = result.get("target", "—")
        digest = str(result.get("prompt_sha256", ""))[:8]
        self.meta_label.setText(
            f"{tr('result.profile')}: {profile}   ·   {tr('result.target')}: {target}"
            f"   ·   {tr('result.hash')}: {digest or '—'}"
        )

        self.metric_constraints.set_value(str(len(constraints)))
        self.metric_constraints.set_semantic("success" if constraints else "muted")
        self.metric_warnings.set_value(str(len(warnings)))
        self.metric_warnings.set_semantic("warning" if warnings else "muted")
        self.metric_errors.set_value(str(len(errors)))
        self.metric_errors.set_semantic("error" if errors else "muted")
        self.counts_label.setText(
            f"{tr('result.score')}: {score}/100 · "
            f"{tr('result.constraints')}: {len(constraints)} · "
            f"{tr('result.warnings')}: {len(warnings)} · "
            f"{tr('result.errors')}: {len(errors)}"
        )

        self.body.setPlainText(result.get("optimized_prompt", ""))
        self.copy_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self._set_state_property(state)

    def set_working(self, message: str = "") -> None:
        self.chip.set_state("working")
        self.chip.set_text(tr("result.state.working"))
        self.title_label.setText(message or tr("result.state.working"))
        self.score_label.setText("…")
        self.score_label.setProperty("semantic", "info")
        _refresh(self.score_label)
        self.meta_label.setText("")
        self.counts_label.setText("")
        for tile in (self.metric_constraints, self.metric_warnings, self.metric_errors):
            tile.set_value("—")
            tile.set_semantic("muted")
        self.body.setPlainText("")
        self.copy_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self._set_state_property("idle")

    def clear(self) -> None:
        self._result = None
        self.chip.set_state("idle")
        self.chip.set_text(tr("result.state.idle"))
        self.title_label.setText(tr("result.state.idle"))
        self.score_label.setText("—")
        self.score_label.setProperty("semantic", "muted")
        _refresh(self.score_label)
        self.meta_label.setText("")
        self.counts_label.setText("")
        for tile in (self.metric_constraints, self.metric_warnings, self.metric_errors):
            tile.set_value("—")
            tile.set_semantic("muted")
        self.body.setPlainText("")
        self.copy_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self._set_state_property("idle")

    def _set_state_property(self, state: str) -> None:
        self.setProperty("resultState", state)
        _refresh(self)


class EmptyState(QFrame):
    """Explains what will appear here and what to do next."""

    def __init__(
        self,
        title: str = "",
        hint: str = "",
        glyph: str = "◇",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NPSCEmptyState")
        theme = active_theme()
        s = theme.spacing

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s.xxl, s.xxl, s.xxl, s.xxl)
        layout.setSpacing(s.md)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._glyph = QLabel(glyph)
        self._glyph.setObjectName("EmptyGlyph")
        self._glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._glyph)

        self.title_label = QLabel(title or tr("result.empty.title"))
        self.title_label.setObjectName("EmptyTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.hint_label = QLabel(hint or tr("result.empty.hint"))
        self.hint_label.setObjectName("EmptyHint")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        self._action_slot = QHBoxLayout()
        self._action_slot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(self._action_slot)

    def set_action(self, button: QWidget) -> None:
        self._action_slot.addWidget(button)


class PageHeader(QWidget):
    """Consistent page heading: title, one-line explanation, right-side actions."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        theme = active_theme()
        s = theme.spacing

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(s.md)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("PageSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        text_col.addWidget(self.title_label)
        text_col.addWidget(self.subtitle_label)
        layout.addLayout(text_col, 1)

        self._actions = QHBoxLayout()
        self._actions.setSpacing(s.sm)
        layout.addLayout(self._actions, 0)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        self.subtitle_label.setText(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))

    def add_action(self, widget: QWidget) -> None:
        self._actions.addWidget(widget)


__all__ = ["Card", "MetricTile", "ResultCard", "EmptyState", "PageHeader"]
