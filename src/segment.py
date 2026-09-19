"""Rule-based process segmenter with debounce and idle gaps."""

from __future__ import annotations

from dataclasses import dataclass

from .features import (
    EventFeatures,
    annotate_with_carry_forward,
    extract_event_features,
    label_for_key,
    process_key,
)

# Frozen after Dataset A grid search (see evaluate_a.py / REPORT.md).
DEFAULT_DEBOUNCE_MS = 4000
DEFAULT_IDLE_MS = 90000
DEFAULT_MIN_SEGMENT_MS = 2500


@dataclass
class Segment:
    session_id: str
    start_ms: int
    end_ms: int
    start_iso: str
    end_iso: str
    label: str
    key: str
    n_events: int
    n_clipboard: int
    machine_id: str
    username_hash: str
    apps: list[str]
    titles: list[str]

    def to_jsonl_row(self) -> dict:
        return {
            "session_id": self.session_id,
            "start": _to_utc_z(self.start_iso, self.start_ms),
            "end": _to_utc_z(self.end_iso, self.end_ms),
            "label": self.label,
        }


def _to_utc_z(iso: str, ms: int) -> str:
    if iso.endswith("Z"):
        # Keep second precision for the required deliverable format.
        core = iso.replace("Z", "")
        if "." in core:
            core = core.split(".", 1)[0]
        return core + "Z"
    if ms:
        from datetime import datetime, timezone

        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return iso


def _iso(f: EventFeatures) -> str:
    return f.timestamp_iso


def segment_features(
    session_id: str,
    feats: list[EventFeatures],
    *,
    debounce_ms: int = DEFAULT_DEBOUNCE_MS,
    idle_ms: int = DEFAULT_IDLE_MS,
    min_segment_ms: int = DEFAULT_MIN_SEGMENT_MS,
) -> list[Segment]:
    if not feats:
        return []
    feats = annotate_with_carry_forward(feats)

    segments: list[Segment] = []
    cur_key = process_key(feats[0])
    cur_start = feats[0]
    last = feats[0]
    pending_key: str | None = None
    pending_since: EventFeatures | None = None
    n_events = 0
    n_clip = 0
    apps: dict[str, int] = {}
    titles: dict[str, int] = {}

    def bump(f: EventFeatures) -> None:
        nonlocal n_events, n_clip
        n_events += 1
        if f.is_clipboard:
            n_clip += 1
        if f.app_name:
            apps[f.app_name] = apps.get(f.app_name, 0) + 1
        if f.window_title:
            titles[f.window_title] = titles.get(f.window_title, 0) + 1

    def close_upto(end_f: EventFeatures) -> None:
        nonlocal n_events, n_clip, apps, titles
        dur = end_f.timestamp_ms - cur_start.timestamp_ms
        if n_events > 0 and dur >= min_segment_ms and cur_key != "unrelated":
            segments.append(
                Segment(
                    session_id=session_id,
                    start_ms=cur_start.timestamp_ms,
                    end_ms=end_f.timestamp_ms,
                    start_iso=_iso(cur_start),
                    end_iso=_iso(end_f),
                    label=label_for_key(cur_key),
                    key=cur_key,
                    n_events=n_events,
                    n_clipboard=n_clip,
                    machine_id=end_f.machine_id or cur_start.machine_id,
                    username_hash=end_f.username_hash or cur_start.username_hash,
                    apps=sorted(apps, key=apps.get, reverse=True)[:8],
                    titles=sorted(titles, key=titles.get, reverse=True)[:6],
                )
            )
        elif n_events > 0 and dur >= min_segment_ms and cur_key == "unrelated":
            # Keep long unrelated blocks so eval can see them as non-overlap.
            segments.append(
                Segment(
                    session_id=session_id,
                    start_ms=cur_start.timestamp_ms,
                    end_ms=end_f.timestamp_ms,
                    start_iso=_iso(cur_start),
                    end_iso=_iso(end_f),
                    label="unrelated",
                    key="unrelated",
                    n_events=n_events,
                    n_clipboard=n_clip,
                    machine_id=end_f.machine_id or cur_start.machine_id,
                    username_hash=end_f.username_hash or cur_start.username_hash,
                    apps=sorted(apps, key=apps.get, reverse=True)[:8],
                    titles=sorted(titles, key=titles.get, reverse=True)[:6],
                )
            )
        n_events = 0
        n_clip = 0
        apps = {}
        titles = {}

    bump(feats[0])

    for f in feats[1:]:
        gap = f.timestamp_ms - last.timestamp_ms
        key = process_key(f)

        if gap >= idle_ms:
            close_upto(last)
            cur_key = key
            cur_start = f
            pending_key = None
            pending_since = None
            bump(f)
            last = f
            continue

        if key != cur_key:
            if pending_key != key:
                pending_key = key
                pending_since = f
            elif pending_since and (f.timestamp_ms - pending_since.timestamp_ms) >= debounce_ms:
                close_upto(pending_since)
                cur_key = key
                cur_start = pending_since
                pending_key = None
                pending_since = None
                bump(f)
                last = f
                continue
        else:
            pending_key = None
            pending_since = None

        bump(f)
        last = f

    close_upto(last)

    # Merge adjacent identical labels with tiny gaps (debounce leftovers).
    merged: list[Segment] = []
    for seg in segments:
        if (
            merged
            and merged[-1].label == seg.label
            and seg.start_ms - merged[-1].end_ms <= debounce_ms
        ):
            prev = merged[-1]
            merged[-1] = Segment(
                session_id=prev.session_id,
                start_ms=prev.start_ms,
                end_ms=seg.end_ms,
                start_iso=prev.start_iso,
                end_iso=seg.end_iso,
                label=prev.label,
                key=prev.key,
                n_events=prev.n_events + seg.n_events,
                n_clipboard=prev.n_clipboard + seg.n_clipboard,
                machine_id=prev.machine_id or seg.machine_id,
                username_hash=prev.username_hash or seg.username_hash,
                apps=list(dict.fromkeys(prev.apps + seg.apps)),
                titles=list(dict.fromkeys(prev.titles + seg.titles)),
            )
        else:
            merged.append(seg)
    return merged


def segment_events(session_id: str, events: list[dict], **kwargs) -> list[Segment]:
    feats = [extract_event_features(e) for e in events]
    return segment_features(session_id, feats, **kwargs)
