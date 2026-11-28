import json

import pytest
from PySide6.QtWidgets import QApplication

from context_io import export_plan, load_messages
from npsc_gui.context_workbench import ContextWorkbench
from test_agent_context import transcript


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_file_boundaries_and_duplicate_keys(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('[{"role":"user","role":"tool","content":"x"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        load_messages(path)
    path.write_text('[{"role":"user","content":NaN}]', encoding="utf-8")
    with pytest.raises(ValueError, match="Non-finite"):
        load_messages(path)


def test_workbench_plan_recall_export_and_input_invalidation(qt_app, tmp_path):
    rows = transcript()
    source = tmp_path / "source.json"
    source.write_text(json.dumps(rows), encoding="utf-8")
    w = ContextWorkbench()
    try:
        w.transcript_path.setText(str(source))
        w.budget.setValue(6000)
        # Add enough tail messages to protect the current turn without
        # making the old result part of the protected eight-message tail.
        rows.extend([{"role": "assistant", "content": "answer"}, {"role": "user", "content": "next"}] * 8)
        source.write_text(json.dumps(rows), encoding="utf-8")
        w.run_plan()
        assert w._plan is not None and w._plan.report["references"]
        assert w._plan.report["verification"]["status"] == "structurally_verified"
        w.run_recall()
        assert json.loads(w.recall_output.toPlainText())["content"]
        if w._plan.report["fits_metered_budget"]:
            target = tmp_path / "export.json"
            export_plan(target, w._plan)
            with pytest.raises(FileExistsError):
                export_plan(target, w._plan)
        assert json.loads(source.read_text(encoding="utf-8")) == rows
        w.budget.setValue(5000)
        assert w._plan is None and not w.export_button.isEnabled()
        assert w.recall_ref.count() == 0
        w.resource_root.setText(str(tmp_path / "extras"))
        w.refresh_resources()
        assert len(json.loads(w.resource_output.toPlainText())["models"]) == 6
    finally:
        w.close()
