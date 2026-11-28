"""Install the experimental NSCP context plugin without modifying config.yaml."""
from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "nscp_context"
ENGINES = ("nscp_context", "nscp_hybrid")


def install(hermes_home: Path, engine=PLUGIN) -> Path:
    if engine not in ENGINES:
        raise ValueError("Unsupported NSCP engine")
    source = ROOT / "integrations" / "hermes" / engine
    files = {
        "__init__.py": (source / "__init__.py").read_bytes(),
        "plugin.yaml": (source / "plugin.yaml").read_bytes(),
        "agent_context.py": (ROOT / "src" / "agent_context.py").read_bytes(),
    }
    for module in ("local_summary", "extractive_context", "local_retrieval",
                   "semantic_memory", "semantic_ranking"):
        files[module + ".py"] = (ROOT / "src" / (module + ".py")).read_bytes()
    if engine == "nscp_hybrid":
        files["request_engine.py"] = (ROOT / "integrations" / "hermes" / PLUGIN / "__init__.py").read_bytes()
    plugins = hermes_home / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    dest = plugins / engine
    if dest.is_symlink():
        raise FileExistsError(f"Refusing symlink {dest}")
    if dest.exists():
        if dest.is_dir() and all((dest / name).is_file() and not (dest / name).is_symlink()
                                  and (dest / name).read_bytes() == data for name, data in files.items()):
            return dest
        raise FileExistsError(f"Refusing to overwrite existing plugin: {dest}")
    with tempfile.TemporaryDirectory(prefix=".nscp-install-", dir=plugins) as temp:
        staged = Path(temp) / engine
        staged.mkdir()
        for name, data in files.items():
            (staged / name).write_bytes(data)
        if dest.exists() or dest.is_symlink():
            raise FileExistsError(f"Plugin appeared during installation: {dest}")
        staged.rename(dest)
    return dest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-home", type=Path,
                        default=Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")))
    parser.add_argument("--engine", choices=ENGINES, default=PLUGIN)
    args = parser.parse_args(argv)
    dest = install(args.hermes_home, args.engine)
    print(f"Installed (not activated): {dest}")
    print("Experimental: verify ContextEngine and nscp_recall in a separate Hermes session first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
