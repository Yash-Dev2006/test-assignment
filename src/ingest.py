"""Walk session chunks, merge events, drop SYSTEM noise."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


def session_dirs(root: Path) -> list[Path]:
    root = Path(root)
    return sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("ses_"))


def iter_raw_events(session_dir: Path) -> Iterator[dict[str, Any]]:
    chunks = sorted(session_dir.glob("chunk_*/events.jsonl"))
    for chunk in chunks:
        with chunk.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


def load_session_events(
    session_dir: Path,
    *,
    drop_system: bool = True,
) -> list[dict[str, Any]]:
    events = list(iter_raw_events(session_dir))
    if drop_system:
        events = [e for e in events if e.get("layer") != "SYSTEM"]
    events.sort(key=lambda e: (e.get("timestamp_ms") or 0, e.get("event_id") or ""))
    return events


def iter_dataset_sessions(root: Path) -> Iterator[tuple[str, Path, list[dict[str, Any]]]]:
    for ses in session_dirs(root):
        yield ses.name, ses, load_session_events(ses)
