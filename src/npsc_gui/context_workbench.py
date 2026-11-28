"""Offline context workbench; no implicit access to Hermes or model endpoints."""
from __future__ import annotations

import json
import sys

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)

from agent_context import STRATEGIES, plan_request, recall, verify_request_plan
from context_io import export_plan, load_messages
from extractive_context import plan_extractive_request
from nscp_resources import inventory, root_path


class ContextWorkbench(QDialog):
    """Explicit file-based preview, exact recall and local resource inventory."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NSCP · Context Workbench")
        self.resize(900, 680)
        self._plan = None
        self._source = None
        root = QVBoxLayout(self)
        note = QLabel("Local experimental workbench · structural verification only · no automatic model calls")
        note.setWordWrap(True)
        root.addWidget(note)
        self.tabs = QTabWidget(self)
        root.addWidget(self.tabs)
        self._build_plan()
        self._build_recall()
        self._build_resources()

    def _file_field(self, layout, label):
        row = QHBoxLayout()
        field = QLineEdit()
        button = QPushButton("Browse…")
        def choose():
            path, _ = QFileDialog.getOpenFileName(self, label, "", "JSON (*.json)")
            if path:
                field.setText(path)
        button.clicked.connect(choose)
        row.addWidget(field)
        row.addWidget(button)
        layout.addRow(label, row)
        return field

    @staticmethod
    def _output():
        widget = QPlainTextEdit()
        widget.setReadOnly(True)
        return widget

    def _build_plan(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.transcript_path = self._file_field(form, "Original transcript")
        self.request_path = self._file_field(form, "Request (optional)")
        self.budget = QSpinBox()
        self.budget.setRange(1, 2_000_000)
        self.budget.setValue(8192)
        form.addRow("Estimated context budget", self.budget)
        self.strategy = QComboBox()
        self.strategy.addItems(STRATEGIES)
        self.strategy.setCurrentText("adaptive")
        form.addRow("Planning strategy", self.strategy)
        self.excerpts = QCheckBox("Include exact lexical excerpts (BM25)")
        form.addRow(self.excerpts)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.plan_button = QPushButton("Plan and verify")
        self.plan_button.clicked.connect(self.run_plan)
        self.export_button = QPushButton("Export new JSON…")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.save_plan)
        actions.addWidget(self.plan_button)
        actions.addWidget(self.export_button)
        layout.addLayout(actions)
        self.plan_status = QLabel("No plan")
        self.plan_status.setWordWrap(True)
        layout.addWidget(self.plan_status)
        self.plan_output = self._output()
        layout.addWidget(self.plan_output, 1)
        self.tabs.addTab(page, "Context")
        for control, signal in ((self.transcript_path, "textChanged"), (self.request_path, "textChanged"),
                                (self.budget, "valueChanged"), (self.strategy, "currentIndexChanged"),
                                (self.excerpts, "toggled")):
            getattr(control, signal).connect(self.invalidate)

    def invalidate(self, *_):
        self._plan = None
        self._source = None
        self.export_button.setEnabled(False)
        self.plan_status.setText("Inputs changed; generate a new plan")
        self.plan_output.clear()
        self.recall_ref.clear()
        self.recall_output.clear()

    def run_plan(self):
        self.invalidate()
        try:
            source = load_messages(self.transcript_path.text())
            request = load_messages(self.request_path.text()) if self.request_path.text().strip() else source
            budget = self.budget.value()
            planner = plan_extractive_request if self.excerpts.isChecked() else plan_request
            candidate = planner(request, source, budget, strategy=self.strategy.currentText())
            candidate.report["verification"] = verify_request_plan(request, source, candidate, budget)
            self._plan, self._source = candidate, source
            report = candidate.report
            self.plan_status.setText(
                f'{report["tokens_before"]:,} → {report["tokens_after"]:,} estimated tokens · '
                f'{len(report["references"])} archived results · '
                + ("fits estimate" if report["fits_metered_budget"] else "budget unmet"))
            self.export_button.setEnabled(report["fits_metered_budget"])
            self.recall_ref.addItems(list(dict.fromkeys(report["references"])))
            self.plan_output.setPlainText(json.dumps(
                {"report": report, "messages": candidate.messages}, ensure_ascii=False, indent=2))
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            self.plan_status.setText("Plan rejected: " + type(exc).__name__)

    def save_plan(self):
        if self._plan is None or not self.export_button.isEnabled():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export new plan", "", "JSON (*.json)")
        if path:
            try:
                export_plan(path, self._plan)
                self.plan_status.setText("Exported new file; original files untouched")
            except (OSError, ValueError) as exc:
                self.plan_status.setText("Export rejected: " + type(exc).__name__)

    def _build_recall(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.recall_ref = QComboBox()
        form.addRow("Issued plan reference", self.recall_ref)
        self.offset = QSpinBox()
        self.offset.setRange(0, 4 * 1024 * 1024)
        form.addRow("Character offset", self.offset)
        self.limit = QSpinBox()
        self.limit.setRange(1, 12000)
        self.limit.setValue(4000)
        form.addRow("Character limit", self.limit)
        layout.addLayout(form)
        button = QPushButton("Recall from loaded original")
        button.clicked.connect(self.run_recall)
        layout.addWidget(button)
        self.recall_output = self._output()
        layout.addWidget(self.recall_output, 1)
        self.tabs.addTab(page, "Recall")

    def run_recall(self):
        if self._source is None or not self.recall_ref.currentText():
            self.recall_output.setPlainText("No issued reference")
            return
        try:
            data = recall(self._source, self.recall_ref.currentText(),
                          offset=self.offset.value(), limit=self.limit.value())
            self.recall_output.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
        except (ValueError, TypeError) as exc:
            self.recall_output.setPlainText("Recall rejected: " + type(exc).__name__)

    def _build_resources(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.resource_root = QLineEdit()
        try:
            self.resource_root.setText(str(root_path()))
        except ValueError:
            pass
        form.addRow("Shared extras directory", self.resource_root)
        layout.addLayout(form)
        button = QPushButton("Inspect resource availability")
        button.clicked.connect(self.refresh_resources)
        layout.addWidget(button)
        layout.addWidget(QLabel("Presence only; no automatic hashing, installation or inference."))
        self.resource_output = self._output()
        layout.addWidget(self.resource_output, 1)
        self.tabs.addTab(page, "Engines")

    def refresh_resources(self):
        try:
            result = inventory(root_path(self.resource_root.text()))
            self.resource_output.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        except (OSError, ValueError) as exc:
            self.resource_output.setPlainText("Inventory rejected: " + type(exc).__name__)


def main():
    app = QApplication(sys.argv)
    from npsc_gui.design.style import apply_design, get_theme
    apply_design(app, get_theme("dark"))
    dialog = ContextWorkbench()
    dialog.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
