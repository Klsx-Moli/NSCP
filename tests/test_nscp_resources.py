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
