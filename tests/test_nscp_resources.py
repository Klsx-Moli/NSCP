import json
from pathlib import Path

import pytest

from nscp_resources import apply_import, inventory, model_files, plan_import, root_path, run_cli


def make_model(source, mid="qwen3-embedding-0.6b-q8"):
    source.mkdir(exist_ok=True)
    filename = model_files(mid)[0][-1]
    path = source / filename
    path.write_bytes(b"fixture, not real weights")
    return path


def test_import_read_only_copy_replay_and_conflict(tmp_path):
    source = tmp_path / "downloads"
    original = make_model(source)
    root = tmp_path / "extras"
    rows = plan_import(root, [source])
    assert len(rows) == 1 and rows[0]["action"] == "copy"
    assert not root.exists()
    apply_import(root, rows, min_free_bytes=0)
    target = Path(rows[0]["target"])
    assert target.read_bytes() == original.read_bytes()
    assert inventory(root, verify=True)["models"][0]["files"][0]["sha256"] == rows[0]["sha256"]
    assert plan_import(root, [source])[0]["action"] == "reuse"
    original.write_bytes(b"different")
    conflict = plan_import(root, [source])
    assert conflict[0]["action"] == "conflict"
    with pytest.raises(ValueError, match="conflicts"):
        apply_import(root, conflict, min_free_bytes=0)
    assert target.read_bytes() != original.read_bytes()


def test_reject_source_mutation_and_existing_destination(tmp_path):
    source = tmp_path / "downloads"
    original = make_model(source)
    root = tmp_path / "extras"
    plan = plan_import(root, [source])
    original.write_bytes(b"mutated")
    with pytest.raises(ValueError, match="Source changed"):
        apply_import(root, plan, min_free_bytes=0)
    plan = plan_import(root, [source])
    target = Path(plan[0]["target"])
    target.parent.mkdir(parents=True)
    target.write_bytes(b"do not replace")
    with pytest.raises(FileExistsError):
        apply_import(root, plan, min_free_bytes=0)
    assert target.read_bytes() == b"do not replace"
    assert not list(target.parent.glob(".nscp-import-*"))


def test_kompress_bundle_not_mixed_across_sources(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    paths = model_files("kompress-v2-base-int8")
    for parts in paths[:2]:
        (a / parts[-1]).write_bytes(b"fixture")
    for parts in paths[2:]:
        (b / parts[-1]).write_bytes(b"fixture")
    assert plan_import(tmp_path / "extras", [a, b]) == []
    for parts in paths[2:]:
        (a / parts[-1]).write_bytes(b"fixture")
    assert len(plan_import(tmp_path / "extras", [a, b])) == len(paths)


def test_root_precedence_and_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NSCP_EXTRAS_DIR", str(tmp_path / "env"))
    assert root_path() == tmp_path / "env"
    assert root_path(str(tmp_path / "cli")) == tmp_path / "cli"
    with pytest.raises(ValueError):
        root_path("relative")
    assert run_cli(["--root", str(tmp_path / "cli"), "list"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert all(r["availability"] == "MISSING" for r in data["models"])


def test_root_escape_and_space_guard(tmp_path):
    source = tmp_path / "downloads"
    make_model(source)
    root = tmp_path / "extras"
    rows = plan_import(root, [source])
    with pytest.raises(ValueError, match="space"):
        apply_import(root, rows, min_free_bytes=10**30)
    assert not Path(rows[0]["target"]).exists()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "models").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink permission unavailable")
    with pytest.raises(ValueError, match="escapes root"):
        inventory(root)


@pytest.mark.parametrize("mid", ["ctxprune-small-int8", "multilingual-minilm-nli-onnx"])
def test_new_onnx_bundle_targeted_import(tmp_path, mid):
    source = tmp_path / "source"
    source.mkdir()
    files = model_files(mid)
    for parts in files:
        (source / parts[-1]).write_bytes(parts[-1].encode())
    root = tmp_path / "extras"
    rows = plan_import(root, [source], model_ids=[mid])
    assert len(rows) == len(files)
    assert {row["model_id"] for row in rows} == {mid}
    apply_import(root, rows, min_free_bytes=0)
    result = next(m for m in inventory(root)["models"] if m["model_id"] == mid)
    assert result["availability"] == "PRESENT"
    assert result["inference"] == "not_verified"


def test_resource_plan_cli_is_read_only_and_reports_unresolved_need(tmp_path, capsys):
    policy = tmp_path / "policy.json"
    root = tmp_path / "no-extras"
    data = {"capacity": {"ram_bytes": 100, "vram_bytes": None},
            "reserve": {"ram_bytes": 10, "vram_bytes": 0},
            "costs": {"embedding": {"ram_bytes": 20, "vram_bytes": 1}},
            "context_tokens": 200, "request_budget": 100,
            "need": "semantic", "health": {"embedding": "ready"}}
    policy.write_text(json.dumps(data), encoding="utf-8")
    args = ["--root", str(root), "plan-route", "--policy", str(policy)]
    assert run_cli(args) == 2
    assert json.loads(capsys.readouterr().out)["decision"]["route"] == "RECOVERY"
    assert not root.exists()
    data["costs"]["embedding"]["vram_bytes"] = 0
    policy.write_text(json.dumps(data), encoding="utf-8")
    assert run_cli(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["decision"]["route"] == "EMBEDDING"
    assert result["execution"] == "not_executed"
    assert not root.exists()
    policy.write_text(" " * 65537, encoding="utf-8")
    assert run_cli(args) == 2
    assert "byte limit" in capsys.readouterr().err


def test_live_resource_cli_cannot_override_a_smaller_explicit_cap(tmp_path, capsys, monkeypatch):
    import resource_snapshot
    observed = {"schema": "nscp/resource-snapshot/v1", "capacity": {"ram_bytes": 40, "vram_bytes": None},
                "ram_status": "observed", "vram_status": "unknown", "allocation_guaranteed": False}
    monkeypatch.setattr(resource_snapshot, "snapshot", lambda: observed)
    assert run_cli(["snapshot"]) == 0
    assert json.loads(capsys.readouterr().out) == observed
    data = {"capacity": {"ram_bytes": 100, "vram_bytes": None},
            "reserve": {"ram_bytes": 10, "vram_bytes": 0},
            "costs": {"embedding": {"ram_bytes": 31, "vram_bytes": 0}},
            "context_tokens": 200, "request_budget": 100,
            "need": "semantic", "health": {"embedding": "ready"}}
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    args = ["plan-route", "--policy", str(path), "--live-ram"]
    assert run_cli(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["capacity"]["ram_bytes"] == 40
    assert result["decision"]["route"] == "RECOVERY"
    assert result["resource_snapshot"] == observed
    data["capacity"]["ram_bytes"] = 20
    data["costs"]["embedding"]["ram_bytes"] = 10
    path.write_text(json.dumps(data), encoding="utf-8")
    assert run_cli(args) == 0
    assert json.loads(capsys.readouterr().out)["capacity"]["ram_bytes"] == 20
    observed["capacity"]["ram_bytes"] = None
    observed["ram_status"] = "unknown"
    assert run_cli(args) == 2
    assert json.loads(capsys.readouterr().out)["capacity"]["ram_bytes"] is None
