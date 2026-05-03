"""Download the Kikawa H3N2 and H1N1 Auspice JSONs into ./examples/data/.

Idempotent: skips a file if it already exists. Re-fetch by deleting the file.

Run from the project root:

    .venv/bin/python examples/fetch_auspice_data.py

These JSONs back the real-data tests in tests/test_real_data.py and the
end-to-end Kikawa example. They are not committed to the repo because they
are several hundred KB, may be updated upstream, and are reproducibly
fetchable from the URLs below.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

OUT_DIR = Path(__file__).parent / "data"

REPO_RAW = (
    "https://raw.githubusercontent.com/jbloomlab/flu-seqneut-2025to2026/main/auspice"
)

FILES = {
    "flu-seqneut-2025to2026_H3N2.json": f"{REPO_RAW}/flu-seqneut-2025to2026_H3N2.json",
    "flu-seqneut-2025to2026_H1N1.json": f"{REPO_RAW}/flu-seqneut-2025to2026_H1N1.json",
}


def fetch_one(name: str, url: str, out_dir: Path) -> Path:
    out_path = out_dir / name
    if out_path.exists():
        print(f"skip {out_path} (already exists)")
        return out_path
    print(f"fetch {url}")
    with urllib.request.urlopen(url) as resp:
        data = resp.read()
    out_path.write_bytes(data)
    print(f"wrote {out_path} ({len(data):,} bytes)")
    return out_path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        fetch_one(name, url, OUT_DIR)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        sys.exit(1)
