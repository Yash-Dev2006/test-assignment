"""Rank Dataset B processes for automation (frequency × time × people × feasibility)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .ingest import load_session_events, session_dirs
from .segment import Segment, segment_events


FEASIBILITY = {
    # Local HTTP portals + structured notepad templates: high.
    "hr_payroll_items": 0.95,
    "finance_payroll_items": 0.95,
    "ops_payroll_items": 0.90,
    "hr_onboarding": 0.85,
    "finance_onboarding": 0.80,
    "ops_onboarding": 0.80,
    "hr_leave_applications": 0.85,
    "finance_leave_applications": 0.85,
    "ops_leave_applications": 0.80,
    "hr_social_insurance": 0.80,
    "finance_social_insurance": 0.80,
    "ops_social_insurance": 0.75,
    "hr_resident_tax": 0.80,
    "finance_resident_tax": 0.85,
    "ops_resident_tax": 0.75,
    "settlement_memo": 0.90,
    "inventory_adjust_memo": 0.90,
    "it_request_memo": 0.70,
    "unrelated": 0.05,
}

# Teams / Explorer / one-off docs are deferred.
DEFER_PREFIXES = ("unrelated", "desktop_doc", "onboarding_checklist", "expense_calc", "budget_analysis")


@dataclass
class ProcessStats:
    label: str
    executions: int = 0
    dwell_ms: int = 0
    machines: set[str] = field(default_factory=set)
    users: set[str] = field(default_factory=set)
    sessions: set[str] = field(default_factory=set)
    clipboard_events: int = 0
    apps: set[str] = field(default_factory=set)
    title_hints: set[str] = field(default_factory=set)

    @property
    def dwell_s(self) -> float:
        return self.dwell_ms / 1000.0

    @property
    def clipboard_per_exec(self) -> float:
        return self.clipboard_events / self.executions if self.executions else 0.0

    @property
    def repetitiveness(self) -> float:
        # More executions and more copy-paste => more repetitive.
        clip = min(self.clipboard_per_exec / 8.0, 1.0)
        freq = min(self.executions / 20.0, 1.0)
        return 0.6 * freq + 0.4 * clip

    @property
    def feasibility(self) -> float:
        if self.label in FEASIBILITY:
            return FEASIBILITY[self.label]
        if self.label.startswith(DEFER_PREFIXES) or self.label == "unrelated":
            return 0.1
        return 0.55

    @property
    def score(self) -> float:
        people = min(max(len(self.users), 1) / 4.0, 1.0)
        time_n = min(self.dwell_s / 600.0, 1.0)
        freq_n = min(self.executions / 25.0, 1.0)
        raw = (
            0.30 * freq_n
            + 0.30 * time_n
            + 0.15 * people
            + 0.15 * self.repetitiveness
            + 0.10 * self.feasibility
        ) * 100
        if self.feasibility < 0.3:
            return raw * 0.15
        return raw


def collect_segments(root: Path, **seg_kwargs) -> list[Segment]:
    segs: list[Segment] = []
    for ses in session_dirs(root):
        events = load_session_events(ses)
        segs.extend(segment_events(ses.name, events, **seg_kwargs))
    return segs


def analyze(segments: list[Segment]) -> list[ProcessStats]:
    by: dict[str, ProcessStats] = {}
    for s in segments:
        st = by.setdefault(s.label, ProcessStats(label=s.label))
        st.executions += 1
        st.dwell_ms += max(0, s.end_ms - s.start_ms)
        if s.machine_id:
            st.machines.add(s.machine_id)
        if s.username_hash:
            st.users.add(s.username_hash)
        st.sessions.add(s.session_id)
        st.clipboard_events += s.n_clipboard
        st.apps.update(s.apps)
        st.title_hints.update(s.titles[:3])
    return sorted(by.values(), key=lambda x: x.score, reverse=True)


def stats_to_dict(st: ProcessStats) -> dict:
    return {
        "label": st.label,
        "executions": st.executions,
        "dwell_seconds": round(st.dwell_s, 1),
        "unique_machines": len(st.machines),
        "unique_users": len(st.users),
        "sessions": len(st.sessions),
        "clipboard_events": st.clipboard_events,
        "clipboard_per_exec": round(st.clipboard_per_exec, 2),
        "apps": sorted(st.apps),
        "feasibility": round(st.feasibility, 2),
        "repetitiveness": round(st.repetitiveness, 2),
        "score": round(st.score, 2),
        "priority": "defer" if st.label == "unrelated" or st.feasibility < 0.3 else "consider",
    }


def write_segments_jsonl(segments: list[Segment], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for s in segments:
            if s.label == "unrelated":
                continue
            fh.write(json.dumps(s.to_jsonl_row(), ensure_ascii=False) + "\n")


def load_segments_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows
