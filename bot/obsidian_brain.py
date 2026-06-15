"""Runtime access to Spencer's Obsidian vault.

The vault is Spencer's primary knowledge layer. Generated notes mirror verified
system state; manual notes preserve operator-reviewed memory. This module never
places orders or changes trading authority.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


DEFAULT_BRAIN_DIR = Path(__file__).resolve().parents[1] / "brain"
INDEX_FILE = ".spencer-brain-index.json"
MAX_CAPTURE_CHARS = 40_000
CAPTURE_FOLDERS = {
    "memory": "Memory/Inbox",
    "decision": "Memory/Decisions",
    "lesson": "Memory/Lessons",
    "question": "Memory/Questions",
    "task": "Memory/Tasks",
    "session": "Memory/Sessions",
    "observation": "Memory/Observations",
}
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*")


@dataclass(frozen=True)
class BrainNote:
    note_id: str
    title: str
    path: str
    tags: tuple[str, ...]
    links: tuple[str, ...]
    managed: bool
    source: str | None
    updated: str | None
    modified: str
    content: str

    def public(self, *, include_content: bool = False) -> dict[str, Any]:
        payload = asdict(self)
        payload["tags"] = list(self.tags)
        payload["links"] = list(self.links)
        if not include_content:
            payload.pop("content", None)
        return payload


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.startswith("[") and value.endswith("]"):
        return [
            item.strip().strip("\"'")
            for item in value[1:-1].split(",")
            if item.strip()
        ]
    return value.strip("\"'")


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized
    end = normalized.find("\n---\n", 4)
    if end < 0:
        return {}, normalized

    metadata: dict[str, Any] = {}
    active_list: str | None = None
    for line in normalized[4:end].splitlines():
        if active_list and line.startswith(("  - ", "- ")):
            metadata.setdefault(active_list, []).append(line.split("-", 1)[1].strip().strip("\"'"))
            continue
        active_list = None
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        parsed = _parse_scalar(value)
        metadata[key] = parsed
        if parsed == "":
            metadata[key] = []
            active_list = key
    return metadata, normalized[end + 5 :]


def _title(path: Path, body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def _tags(metadata: dict[str, Any]) -> tuple[str, ...]:
    value = metadata.get("tags", [])
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list):
        return ()
    return tuple(sorted({str(item).strip().lower() for item in value if str(item).strip()}))


def _tokens(value: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(value) if len(token) > 1]


def _slug(value: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return result[:80] or "untitled"


def _snippet(body: str, terms: Iterable[str], width: int = 320) -> str:
    compact = re.sub(r"\s+", " ", body).strip()
    lowered = compact.lower()
    positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    start = max(0, (min(positions) if positions else 0) - width // 4)
    end = min(len(compact), start + width)
    return f"{'...' if start else ''}{compact[start:end].strip()}{'...' if end < len(compact) else ''}"


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


class ObsidianBrain:
    def __init__(self, root: Path | str = DEFAULT_BRAIN_DIR) -> None:
        self.root = Path(root).expanduser().resolve()

    def ensure_layout(self) -> list[str]:
        self.root.mkdir(parents=True, exist_ok=True)
        created: list[str] = []
        folders = [
            "Memory/Inbox",
            "Memory/Decisions",
            "Memory/Lessons",
            "Memory/Questions",
            "Memory/Tasks",
            "Memory/Sessions",
            "Memory/Observations",
            "Reference",
            "Daily",
            "Templates",
        ]
        for folder in folders:
            (self.root / folder).mkdir(parents=True, exist_ok=True)

        seeds = {
            "Memory/Memory Home.md": """---
tags: [spencer, memory, moc]
managed: false
---
# Memory Home

Human-reviewed durable memory. Notes in this folder are never overwritten by
the automated exporter.

- [[Memory/Inbox]]
- [[Memory/Decisions]]
- [[Memory/Lessons]]
- [[Memory/Questions]]
- [[Memory/Tasks]]
- [[Memory/Sessions]]
- [[Memory/Observations]]

Back to [[Spencer]].
""",
            "Templates/Memory.md": """---
type: memory
created:
updated:
source:
confidence: unverified
status: inbox
tags: [spencer, memory]
managed: false
---
# Memory title

## Fact or observation

## Evidence

## Why it matters

## Related
""",
            "Templates/Decision.md": """---
type: decision
created:
updated:
source:
status: active
tags: [spencer, decision]
managed: false
---
# Decision title

## Decision

## Evidence

## Consequences

## Review trigger
""",
            "Templates/Daily Note.md": """---
type: daily-note
date:
tags: [spencer, daily]
managed: false
---
# Daily Note

## Verified changes

## Decisions

## Lessons

## Open questions
""",
        }
        for section in (
            "Inbox",
            "Decisions",
            "Lessons",
            "Questions",
            "Tasks",
            "Sessions",
            "Observations",
        ):
            seeds[f"Memory/{section}.md"] = f"""---
tags: [spencer, memory, moc]
managed: false
---
# {section}

Index for reviewed and captured {section.lower()}.

<!-- SPENCER:MEMORY-LINKS:START -->
<!-- SPENCER:MEMORY-LINKS:END -->

Back to [[Memory/Memory Home]].
"""
        for relative, content in seeds.items():
            path = self.root / relative
            if not path.exists():
                path.write_text(content, encoding="utf-8")
                created.append(relative)

        obsidian = self.root / ".obsidian"
        obsidian.mkdir(parents=True, exist_ok=True)
        configs = {
            ".obsidian/templates.json": {
                "folder": "Templates",
                "dateFormat": "YYYY-MM-DD",
                "timeFormat": "HH:mm",
            },
            ".obsidian/daily-notes.json": {
                "folder": "Daily",
                "format": "YYYY-MM-DD",
                "template": "Templates/Daily Note",
                "autorun": False,
            },
        }
        for relative, payload in configs.items():
            path = self.root / relative
            if not path.exists():
                path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                created.append(relative)
        return created

    def _safe_path(self, relative: str) -> Path:
        candidate = (self.root / relative).resolve()
        if os.path.commonpath([str(self.root), str(candidate)]) != str(self.root):
            raise ValueError("Brain path must stay inside the vault")
        return candidate

    def notes(self) -> list[BrainNote]:
        if not self.root.exists():
            return []
        notes: list[BrainNote] = []
        for path in sorted(self.root.rglob("*.md")):
            relative_path = path.relative_to(self.root)
            if ".obsidian" in relative_path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            metadata, body = _split_frontmatter(text)
            relative = relative_path.as_posix()
            note_id = relative[:-3]
            notes.append(
                BrainNote(
                    note_id=note_id,
                    title=_title(path, body),
                    path=relative,
                    tags=_tags(metadata),
                    links=tuple(dict.fromkeys(match.strip() for match in WIKILINK_RE.findall(body))),
                    managed=bool(metadata.get("managed", False)),
                    source=str(metadata["source_path"]) if metadata.get("source_path") else None,
                    updated=str(metadata["updated"]) if metadata.get("updated") else None,
                    modified=datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(),
                    content=body.strip(),
                )
            )
        return notes

    def _lookup(self, notes: list[BrainNote]) -> dict[str, BrainNote]:
        lookup: dict[str, BrainNote] = {}
        for note in notes:
            lookup[note.note_id.lower()] = note
            lookup.setdefault(Path(note.note_id).name.lower(), note)
            lookup.setdefault(note.title.lower(), note)
        return lookup

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        terms = _tokens(query)
        if not terms:
            return []
        phrase = query.strip().lower()
        matches: list[tuple[float, BrainNote]] = []
        for note in self.notes():
            title = note.title.lower()
            body = note.content.lower()
            tags = " ".join(note.tags)
            score = 0.0
            if phrase and phrase in title:
                score += 20
            elif phrase and phrase in body:
                score += 10
            for term in terms:
                score += title.count(term) * 8
                score += tags.count(term) * 5
                score += min(body.count(term), 12) * 1.5
                score += sum(2 for link in note.links if term in link.lower())
            if score > 0:
                matches.append((score, note))

        matches.sort(key=lambda item: (-item[0], item[1].path))
        return [
            {
                **note.public(),
                "score": round(score, 2),
                "snippet": _snippet(note.content, terms),
                "wikilink": f"[[{note.note_id}]]",
            }
            for score, note in matches[: max(1, min(int(limit), 25))]
        ]

    def get_note(self, note_ref: str) -> dict[str, Any] | None:
        notes = self.notes()
        note = self._lookup(notes).get(note_ref.strip().removesuffix(".md").lower())
        if not note:
            return None
        return {**note.public(include_content=True), "wikilink": f"[[{note.note_id}]]"}

    def context(self, query: str, limit: int = 6, max_chars: int = 7_000) -> dict[str, Any]:
        results = self.search(query, limit=limit)
        sections: list[str] = [f"# Spencer Obsidian context\n\nQuestion: {query}"]
        used: list[dict[str, Any]] = []
        for result in results:
            section = (
                f"\n## {result['title']}\n"
                f"Source: {result['wikilink']}\n"
                f"{result['snippet']}\n"
            )
            if len("\n".join(sections)) + len(section) > max(500, min(max_chars, 20_000)):
                break
            sections.append(section)
            used.append(
                {
                    "title": result["title"],
                    "path": result["path"],
                    "wikilink": result["wikilink"],
                }
            )
        if not used:
            sections.append("\nNo matching vault evidence was found.")
        return {"query": query, "context": "\n".join(sections), "citations": used}

    def recall(self, query: str, limit: int = 6) -> dict[str, Any]:
        results = self.search(query, limit=limit)
        if not results:
            return {
                "ok": True,
                "mode": "local-recall",
                "text": "I could not find a matching fact in the Obsidian brain. This is an unknown, not a negative result.",
                "citations": [],
            }
        lines = ["I found these relevant notes in Spencer's Obsidian brain:"]
        for result in results:
            lines.append(f"- {result['title']}: {result['snippet']} ({result['wikilink']})")
        return {
            "ok": True,
            "mode": "local-recall",
            "text": "\n".join(lines),
            "citations": [
                {
                    "title": result["title"],
                    "path": result["path"],
                    "wikilink": result["wikilink"],
                }
                for result in results
            ],
        }

    def status(self) -> dict[str, Any]:
        notes = self.notes()
        lookup = self._lookup(notes)
        incoming: dict[str, int] = {note.note_id: 0 for note in notes}
        broken: list[dict[str, str]] = []
        link_count = 0
        for note in notes:
            for link in note.links:
                link_count += 1
                target = lookup.get(link.lower())
                if target:
                    incoming[target.note_id] += 1
                else:
                    broken.append({"source": note.note_id, "target": link})

        ignored_orphans = {"spencer", "readme", "memory/memory home"}
        orphans = [
            note.note_id
            for note in notes
            if incoming[note.note_id] == 0
            and note.note_id.lower() not in ignored_orphans
            and not note.path.startswith("Templates/")
        ]
        modified = max((note.modified for note in notes), default=None)
        return {
            "ok": True,
            "primary": True,
            "vault": str(self.root),
            "home": "Spencer.md",
            "noteCount": len(notes),
            "generatedCount": sum(1 for note in notes if note.managed),
            "manualCount": sum(1 for note in notes if not note.managed),
            "memoryCount": sum(1 for note in notes if note.path.startswith("Memory/")),
            "referenceCount": sum(1 for note in notes if note.path.startswith("Reference/")),
            "linkCount": link_count,
            "brokenLinkCount": len(broken),
            "orphanCount": len(orphans),
            "brokenLinks": broken[:50],
            "orphans": orphans[:50],
            "lastModified": modified,
            "paperOnly": True,
            "liveTrading": False,
            "brokerExecution": False,
        }

    def graph(self) -> dict[str, Any]:
        notes = self.notes()
        lookup = self._lookup(notes)
        nodes = [
            {
                "id": note.note_id,
                "title": note.title,
                "path": note.path,
                "managed": note.managed,
                "tags": list(note.tags),
            }
            for note in notes
        ]
        edges = []
        for note in notes:
            for link in note.links:
                target = lookup.get(link.lower())
                if target:
                    edges.append({"source": note.note_id, "target": target.note_id})
        return {"ok": True, "nodes": nodes, "edges": edges}

    def capture(
        self,
        *,
        title: str,
        content: str,
        kind: str = "memory",
        tags: Iterable[str] = (),
        source: str = "operator",
        confidence: str = "unverified",
    ) -> dict[str, Any]:
        title = title.strip()
        content = content.strip()
        kind = kind.strip().lower()
        if not title or not content:
            raise ValueError("title and content are required")
        if len(content) > MAX_CAPTURE_CHARS:
            raise ValueError(f"content exceeds {MAX_CAPTURE_CHARS} characters")
        if kind not in CAPTURE_FOLDERS:
            raise ValueError(f"unsupported memory kind: {kind}")

        self.ensure_layout()
        now = datetime.now().astimezone()
        folder = self._safe_path(CAPTURE_FOLDERS[kind])
        folder.mkdir(parents=True, exist_ok=True)
        base = f"{now.strftime('%Y-%m-%d-%H%M%S')}-{_slug(title)}"
        target = folder / f"{base}.md"
        counter = 2
        while target.exists():
            target = folder / f"{base}-{counter}.md"
            counter += 1

        clean_tags = sorted(
            {"spencer", "memory", kind, *(_slug(str(tag)) for tag in tags if str(tag).strip())}
        )
        frontmatter = [
            "---",
            f"type: {_yaml_string(kind)}",
            f"created: {_yaml_string(now.isoformat(timespec='seconds'))}",
            f"updated: {_yaml_string(now.isoformat(timespec='seconds'))}",
            f"source: {_yaml_string(source.strip() or 'operator')}",
            f"confidence: {_yaml_string(confidence.strip() or 'unverified')}",
            "status: inbox",
            f"tags: [{', '.join(clean_tags)}]",
            "managed: false",
            "---",
            f"# {title}",
            "",
            content,
            "",
            "## Review",
            "",
            "- [ ] Evidence checked",
            "- [ ] Keep as durable memory",
            "- [ ] Link to related notes",
            "",
        ]
        temp = target.with_suffix(".md.tmp")
        temp.write_text("\n".join(frontmatter), encoding="utf-8")
        temp.replace(target)
        relative = target.relative_to(self.root).as_posix()
        self.write_index()
        return {"created": relative, "wikilink": f"[[{relative[:-3]}]]", "kind": kind}

    def _refresh_memory_indexes(self) -> None:
        start_marker = "<!-- SPENCER:MEMORY-LINKS:START -->"
        end_marker = "<!-- SPENCER:MEMORY-LINKS:END -->"
        for folder_name in CAPTURE_FOLDERS.values():
            folder = self.root / folder_name
            section = Path(folder_name).name
            index_path = self.root / "Memory" / f"{section}.md"
            if not index_path.exists():
                continue
            links = [
                f"- [[{path.relative_to(self.root).as_posix()[:-3]}]]"
                for path in sorted(folder.glob("*.md"))
            ]
            block = f"{start_marker}\n" + ("\n".join(links) if links else "") + f"\n{end_marker}"
            text = index_path.read_text(encoding="utf-8")
            if start_marker in text and end_marker in text:
                before, rest = text.split(start_marker, 1)
                _, after = rest.split(end_marker, 1)
                updated = before + block + after
            else:
                updated = text.rstrip() + f"\n\n{block}\n"
            if updated != text:
                temp = index_path.with_suffix(".md.tmp")
                temp.write_text(updated, encoding="utf-8")
                temp.replace(index_path)

    def write_index(self) -> dict[str, Any]:
        self.ensure_layout()
        self._refresh_memory_indexes()
        notes = self.notes()
        payload = {
            "schemaVersion": 1,
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "vault": str(self.root),
            "notes": [note.public() for note in notes],
            "status": self.status(),
        }
        target = self.root / INDEX_FILE
        temp = target.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(target)
        return {
            "ok": True,
            "index": str(target),
            "noteCount": len(notes),
            "generatedAt": payload["generatedAt"],
        }
