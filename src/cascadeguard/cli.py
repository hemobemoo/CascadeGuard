"""Command-line entry point. Phase 0 stub; `run` is implemented in Phase 2."""

import argparse
from collections.abc import Sequence

from cascadeguard import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cascadeguard")
    parser.add_argument("--version", action="version", version=f"cascadeguard {__version__}")
    subcommands = parser.add_subparsers(dest="command")
    run = subcommands.add_parser("run", help="run a scenario (not implemented yet)")
    run.add_argument("scenario")
    run.add_argument("--repair", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        print("cascadeguard run: not implemented yet (Phase 2).")
        return 1
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
