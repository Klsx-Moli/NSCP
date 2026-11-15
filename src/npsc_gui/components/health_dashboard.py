"""HealthDashboard — compact row of real compilation metrics.

The dashboard is only meaningful once a compilation exists, so callers show it
after a result arrives. Before that it is hidden, and the home screen keeps a
single primary action instead of four placeholders with zeros.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from i18n import tr
from npsc_gui.components.cards import MetricTile
from npsc_gui.design.style import active_theme


class MetricPill(MetricTile):
    """Backwards-compatible alias of :class:`MetricTile`."""

    def __init__(self, label: str, value: str = "—", semantic: str = "muted", parent=None) -> None:
        super().__init__(label, value, semantic, parent)
        self._val = self._value
        self._lbl = self._caption


class HealthDashboard(QFrame):
    """Compact panel with metric tiles for the last compilation."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NPSCHealthDash")
        self._metrics: dict[str, MetricTile] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        theme = active_theme()
        s = theme.spacing

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(s.sm)

        title = QLabel(tr("health.title"))
        title.setObjectName("HealthSectionTitle")
        layout.addWidget(title)

        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(s.sm)
        for key, label, value, semantic in [
            ("score", tr("health.preservation"), "—", "muted"),
            ("constraints", tr("result.constraints"), "—", "muted"),
            ("warnings", tr("result.warnings"), "—", "muted"),
            ("errors", tr("result.errors"), "—", "muted"),
        ]:
            tile = MetricTile(label, value, semantic)
            self._metrics[key] = tile
            metrics_row.addWidget(tile)
        layout.addLayout(metrics_row)

    def get_metric(self, key: str) -> MetricTile | None:
        """Return the metric tile for ``key``, or None."""
        return self._metrics.get(key)

    def update_metrics(
        self,
        score: int,
        constraints: int,
        warnings: int,
        errors: int,
    ) -> None:
        self._metrics["score"].set_value(f"{score}/100")
        self._metrics["score"].set_semantic(
            "success" if score >= 85 else "warning" if score >= 60 else "error"
        )
        self._metrics["constraints"].set_value(str(constraints))
        self._metrics["constraints"].set_semantic("success" if constraints else "muted")
        self._metrics["warnings"].set_value(str(warnings))
        self._metrics["warnings"].set_semantic("warning" if warnings else "muted")
        self._metrics["errors"].set_value(str(errors))
        self._metrics["errors"].set_semantic("error" if errors else "muted")


__all__ = ["HealthDashboard", "MetricPill"]
