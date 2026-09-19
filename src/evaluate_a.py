"""Evaluate segmentation against Dataset A gt_manifest.json executions."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .ingest import session_dirs, load_session_events
from .segment import (
    DEFAULT_DEBOUNCE_MS,
    DEFAULT_IDLE_MS,
    Segment,
    segment_events,
)


@dataclass
class GoldSpan:
    session_id: str
    code: str
    family_name: str
    start_ms: int
    end_ms: int
    variant: str | None
    case_id: str | None


def _parse_ts_ms(value: str | None) -> int | None:
    if not value or not isinstance(value, str):
        return None
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(ts.timestamp() * 1000)


def load_gold(session_dir: Path) -> list[GoldSpan]:
    path = session_dir / "gt_manifest.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    session_id = session_dir.name
    spans: list[GoldSpan] = []
    for proc in data.get("processes") or []:
        family = proc.get("family_name") or ""
        code = proc.get("code") or ""
        for ex in proc.get("executions") or []:
            start = _parse_ts_ms(ex.get("start_ts"))
            end = _parse_ts_ms(ex.get("end_ts"))
            if start is None or end is None or end <= start:
                continue
            spans.append(
                GoldSpan(
                    session_id=session_id,
                    code=str(ex.get("code") or code),
                    family_name=family,
                    start_ms=start,
                    end_ms=end,
                    variant=ex.get("variant"),
                    case_id=ex.get("case_id"),
                )
            )
    spans.sort(key=lambda s: s.start_ms)
    return spans


def iou(a0: int, a1: int, b0: int, b1: int) -> float:
    inter = max(0, min(a1, b1) - max(a0, b0))
    union = max(a1, b0, a0, b1) - min(a0, b0)
    # standard interval union
    union = (a1 - a0) + (b1 - b0) - inter
    if union <= 0:
        return 0.0
    return inter / union


def match_spans(gold: list[GoldSpan], pred: list[Segment]) -> list[tuple[GoldSpan, Segment | None, float]]:
    used: set[int] = set()
    rows = []
    for g in gold:
        best_i = -1
        best = 0.0
        for i, p in enumerate(pred):
            if i in used:
                continue
            score = iou(g.start_ms, g.end_ms, p.start_ms, p.end_ms)
            if score > best:
                best = score
                best_i = i
        if best_i >= 0 and best > 0:
            used.add(best_i)
            rows.append((g, pred[best_i], best))
        else:
            rows.append((g, None, 0.0))
    return rows


@dataclass
class EvalResult:
    n_gold: int
    n_pred: int
    mean_iou: float
    median_iou: float
    pct_iou_at_0_3: float
    pct_iou_at_0_5: float
    label_purity: float
    dominant_label_by_code: dict[str, str]
    debounce_ms: int
    idle_ms: int


def summarize(matches: list[tuple[GoldSpan, Segment | None, float]], n_pred: int, debounce_ms: int, idle_ms: int) -> EvalResult:
    ious = [m[2] for m in matches]
    n = len(ious) or 1
    ordered = sorted(ious)
    median = ordered[len(ordered) // 2] if ordered else 0.0
    by_code_labels: dict[str, Counter] = defaultdict(Counter)
    for g, p, score in matches:
        if p is None or score < 0.1:
            continue
        by_code_labels[g.code][p.label] += 1
    purities = []
    dominant = {}
    for code, ctr in by_code_labels.items():
        total = sum(ctr.values())
        lab, c = ctr.most_common(1)[0]
        purities.append(c / total)
        dominant[code] = lab
    return EvalResult(
        n_gold=len(matches),
        n_pred=n_pred,
        mean_iou=sum(ious) / n if ious else 0.0,
        median_iou=median,
        pct_iou_at_0_3=sum(1 for x in ious if x >= 0.3) / n,
        pct_iou_at_0_5=sum(1 for x in ious if x >= 0.5) / n,
        label_purity=sum(purities) / len(purities) if purities else 0.0,
        dominant_label_by_code=dominant,
        debounce_ms=debounce_ms,
        idle_ms=idle_ms,
    )


def evaluate_dataset(
    root: Path,
    *,
    debounce_ms: int = DEFAULT_DEBOUNCE_MS,
    idle_ms: int = DEFAULT_IDLE_MS,
) -> EvalResult:
    all_matches = []
    n_pred = 0
    for ses in session_dirs(root):
        gold = load_gold(ses)
        if not gold:
            continue
        events = load_session_events(ses)
        pred = segment_events(ses.name, events, debounce_ms=debounce_ms, idle_ms=idle_ms)
        n_pred += len(pred)
        all_matches.extend(match_spans(gold, pred))
    return summarize(all_matches, n_pred, debounce_ms, idle_ms)


def grid_search(root: Path) -> list[EvalResult]:
    results = []
    for debounce in (3000, 4000, 5000):
        for idle in (45000, 60000, 90000):
            results.append(evaluate_dataset(root, debounce_ms=debounce, idle_ms=idle))
    results.sort(key=lambda r: (r.mean_iou, r.label_purity), reverse=True)
    return results


def result_to_dict(r: EvalResult) -> dict:
    return {
        "n_gold": r.n_gold,
        "n_pred": r.n_pred,
        "mean_iou": round(r.mean_iou, 4),
        "median_iou": round(r.median_iou, 4),
        "pct_iou_at_0_3": round(r.pct_iou_at_0_3, 4),
        "pct_iou_at_0_5": round(r.pct_iou_at_0_5, 4),
        "label_purity": round(r.label_purity, 4),
        "dominant_label_by_code": r.dominant_label_by_code,
        "debounce_ms": r.debounce_ms,
        "idle_ms": r.idle_ms,
    }
