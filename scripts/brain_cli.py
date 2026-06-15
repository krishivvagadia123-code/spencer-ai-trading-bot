"""Command-line access to Spencer's primary Obsidian brain."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.obsidian_brain import DEFAULT_BRAIN_DIR, ObsidianBrain


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Search and maintain Spencer's Obsidian brain.")
    command.add_argument("--vault", type=Path, default=DEFAULT_BRAIN_DIR)
    subcommands = command.add_subparsers(dest="command", required=True)
    subcommands.add_parser("status")
    subcommands.add_parser("reindex")

    search = subcommands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=8)

    context = subcommands.add_parser("context")
    context.add_argument("query")
    context.add_argument("--limit", type=int, default=6)
    context.add_argument("--max-chars", type=int, default=7000)

    capture = subcommands.add_parser("capture")
    capture.add_argument("title")
    capture.add_argument("content")
    capture.add_argument("--kind", choices=sorted(CAPTURE_KINDS), default="memory")
    capture.add_argument("--tag", action="append", default=[])
    capture.add_argument("--source", default="operator")
    capture.add_argument("--confidence", default="unverified")
    return command


CAPTURE_KINDS = {
    "memory",
    "decision",
    "lesson",
    "question",
    "task",
    "session",
    "observation",
}


def main() -> int:
    args = parser().parse_args()
    brain = ObsidianBrain(args.vault)
    if args.command == "status":
        payload = brain.status()
    elif args.command == "reindex":
        payload = brain.write_index()
    elif args.command == "search":
        payload = {"ok": True, "results": brain.search(args.query, args.limit)}
    elif args.command == "context":
        payload = brain.context(args.query, args.limit, args.max_chars)
    else:
        payload = brain.capture(
            title=args.title,
            content=args.content,
            kind=args.kind,
            tags=args.tag,
            source=args.source,
            confidence=args.confidence,
        )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
