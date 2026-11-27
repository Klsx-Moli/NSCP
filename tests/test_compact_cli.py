import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import json
import random
import npsc_compact_cli as cli
sys.path.insert(0, os.path.dirname(__file__))
from compaction_helpers import build


def write(tmp_path, hist):
    p = tmp_path / "in.json"
    p.write_text(json.dumps([{"role": v.role, "content": v.content, "pinned": v.pinned} for v in hist]))
    return str(p)


def test_cli_ok_writes_json(tmp_path):
    hist = [v for v in build(random.Random(5), 40, 0)]
    out = tmp_path / "o.json"
    rc = cli.run_cli(["--input", write(tmp_path, hist), "--out", str(out), "--num-ctx", "1500"])
    data = json.loads(out.read_text())
    assert rc == 0 and data["report"]["triggered"] and data["messages"][0]["role"] == "system"
    assert data["report"]["verification"]["status"] in ("pass", "advisory", "pass_after_fallback_truncation")


def test_cli_strict_blocked_exit_2(tmp_path):
    hist = build(random.Random(3), 60, 1)
    out = tmp_path / "o.json"
    rc = cli.run_cli(["--input", write(tmp_path, hist), "--out", str(out), "--num-ctx", "1500", "--strict"])
    data = json.loads(out.read_text())
    assert rc == 2 and data["blocked"] is True and data["reasons"] and data["messages"] == []


def test_cli_passthrough_small(tmp_path):
    hist = build(random.Random(5), 3, 0)
    out = tmp_path / "o.json"
    assert cli.run_cli(["--input", write(tmp_path, hist), "--out", str(out), "--num-ctx", "8192", "--strict"]) == 0
    assert json.loads(out.read_text())["report"]["triggered"] is False


def test_cli_invalid_input_exit_1(tmp_path, capsys):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps([{"role": "robot", "content": "x"}]))
    assert cli.run_cli(["--input", str(p), "--out", "-", "--num-ctx", "1000"]) == 1
    assert "invalido" in capsys.readouterr().err


def test_cli_missing_file_exit_1(tmp_path):
    assert cli.run_cli(["--input", str(tmp_path / "no.json"), "--out", "-", "--num-ctx", "1000"]) == 1


def test_cli_stdout_and_messages_wrapper(tmp_path, capsys):
    hist = build(random.Random(5), 3, 0)
    p = tmp_path / "w.json"
    p.write_text(json.dumps({"messages": [{"role": v.role, "content": v.content} for v in hist]}))
    assert cli.run_cli(["--input", str(p), "--out", "-", "--num-ctx", "8192"]) == 0
    assert json.loads(capsys.readouterr().out)["report"]["schema"] == "neuroprompt/compaction-result/v1"


def test_gate_policy_default_when_config_missing(monkeypatch):
    monkeypatch.setattr(cli.Path, "read_text", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    assert cli.load_gate_policy() == {"min_score": 80, "max_critical_losses": 0}
