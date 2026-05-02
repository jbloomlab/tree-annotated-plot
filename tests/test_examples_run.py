"""Smoke-test that scripts in `examples/` still run end-to-end.

These tests don't validate visual correctness — they only confirm that each
example's `main()` executes without raising, and that the expected output files
land in a writable location. This guards against silent drift when the public
API changes.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _load_example(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_synthetic_example_runs(tmp_path, monkeypatch):
    module = _load_example(EXAMPLES_DIR / "synthetic_example.py")
    monkeypatch.setattr(module, "OUT_DIR", tmp_path)
    module.main()
    assert (tmp_path / "synthetic_example.html").exists()
    assert (tmp_path / "synthetic_example.png").exists()
