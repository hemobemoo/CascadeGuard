"""Write the generated evaluation documents (PR 5): the scripted traces in
docs/evaluation/traces/, docs/gap-analysis.md and the unpublished conclusion draft. Scripted
agents and committed files only: no API call. `--check` writes nothing and exits 1 if a
committed file differs from what would be generated.

    uv run python scripts/build_reports.py [--check]
"""

import argparse
import sys

from cascadeguard.knowledge.loader import PROJECT_ROOT
from cascadeguard.storage.reports import build


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="compare only; write nothing")
    args = parser.parse_args()
    stale = 0
    for path, text in build().items():
        shown = path.relative_to(PROJECT_ROOT).as_posix()
        old = path.read_text(encoding="utf-8").replace("\r\n", "\n") if path.exists() else None
        if old == text:
            continue
        stale += 1
        if args.check:
            print(f"stale: {shown}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {shown}")
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
