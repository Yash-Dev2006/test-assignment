"""Per-event features: app, URL path, title, clipboard, extracted text."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

# Dataset A mock portals use 512x; Dataset B uses 513x. Same method, different hosts.
PORT_DOMAIN = {
    "5122": "hr",
    "5132": "hr",
    "5123": "finance",
    "5133": "finance",
    "5124": "ops",
    "5134": "ops",
}

TITLE_DOMAIN = (
    ("HR人事", "hr"),
    ("財務会計", "finance"),
    ("受発注", "ops"),
)

ROUTE_NAMES = {
    "onboarding": "onboarding",
    "leave-applications": "leave_applications",
    "payroll-items": "payroll_items",
    "social-insurance": "social_insurance",
    "resident-tax": "resident_tax",
    "dashboard": "dashboard",
}

BROWSER_APPS = {"google chrome", "microsoft edge", "chrome", "msedge", "firefox"}
SWIVEL_APPS = {
    "notepad",
    "microsoft word",
    "microsoft excel",
    "winword",
    "excel",
    "onenote",
}
NOISE_APPS = {
    "windowsterminal",
    "windows explorer",
    "explorer",
    "procmine-desktop-agent",
    "nvidia overlay",
    "settings",
    "openwith",
    "ms-teams",
    "teams",
    "prl_cc",
}

DOC_LABELS = (
    ("精算確認", "settlement_memo"),
    ("在庫調整", "inventory_adjust_memo"),
    ("IT申請", "it_request_memo"),
    ("nyusha_checklist", "onboarding_checklist_doc"),
    ("expense_calc", "expense_calc_sheet"),
    ("budget_analysis", "budget_analysis_sheet"),
)


@dataclass
class EventFeatures:
    timestamp_ms: int
    timestamp_iso: str
    event_type: str
    layer: str
    app_name: str
    process_name: str
    window_title: str
    url: str
    url_host: str
    url_port: str
    url_hash: str
    domain: str
    clipboard_len: int | None
    extracted_snippet: str
    machine_id: str
    username_hash: str
    is_clipboard: bool
    is_noise: bool
    is_browser: bool
    is_swivel: bool
    doc_hint: str


def _get(d: Any, *keys: str, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def _norm_app(name: str) -> str:
    return (name or "").strip().lower()


def _route_from_url(url: str) -> tuple[str, str, str]:
    if not url:
        return "", "", ""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = str(parsed.port or "")
    fragment = (parsed.fragment or "").split("?")[0].strip("/")
    return host, port, fragment


def _domain_from_port_or_title(port: str, title: str, host: str) -> str:
    if port in PORT_DOMAIN:
        return PORT_DOMAIN[port]
    if host.startswith("127.0.0.1") or host == "localhost":
        pass
    for needle, domain in TITLE_DOMAIN:
        if needle in (title or ""):
            return domain
    return ""


def _doc_hint(title: str) -> str:
    t = title or ""
    tl = t.lower()
    for needle, label in DOC_LABELS:
        if needle.lower() in tl or needle in t:
            return label
    return ""


def extract_event_features(event: dict[str, Any]) -> EventFeatures:
    ctx = event.get("context") or {}
    app = ctx.get("active_app") or {}
    tab = ctx.get("active_browser_tab") or {}
    payload = event.get("payload") or {}
    source = event.get("source") or {}

    app_name = app.get("app_name") or ""
    process_name = app.get("process_name") or ""
    window_title = app.get("window_title") or ""

    url = tab.get("url") or ""
    if not url:
        url = payload.get("url") or _get(payload, "tab", "url", default="") or ""
        if isinstance(url, dict):
            url = url.get("url") or ""

    host, port, fragment = _route_from_url(url)
    domain = _domain_from_port_or_title(port, window_title, host)

    clip_len = None
    is_clip = event.get("event_type") == "clipboard_change"
    if is_clip:
        clip_len = payload.get("text_length")

    extracted = ctx.get("extracted_text") or {}
    snippet = ""
    if isinstance(extracted, dict):
        snippet = (extracted.get("text") or "")[:240]
    elif isinstance(extracted, str):
        snippet = extracted[:240]

    norm = _norm_app(app_name) or _norm_app(process_name.replace(".exe", ""))
    is_browser = any(b in norm for b in BROWSER_APPS)
    is_swivel = any(s in norm for s in SWIVEL_APPS)
    is_noise = any(n in norm for n in NOISE_APPS) or "slack" in (url or "")

    return EventFeatures(
        timestamp_ms=int(event.get("timestamp_ms") or 0),
        timestamp_iso=event.get("timestamp_iso") or "",
        event_type=event.get("event_type") or "",
        layer=event.get("layer") or "",
        app_name=app_name,
        process_name=process_name,
        window_title=window_title,
        url=url,
        url_host=host,
        url_port=port,
        url_hash=fragment,
        domain=domain,
        clipboard_len=clip_len,
        extracted_snippet=snippet,
        machine_id=source.get("machine_id") or "",
        username_hash=source.get("username_hash") or "",
        is_clipboard=is_clip,
        is_noise=is_noise,
        is_browser=is_browser,
        is_swivel=is_swivel,
        doc_hint=_doc_hint(window_title),
    )


def annotate_with_carry_forward(feats: list[EventFeatures]) -> list[EventFeatures]:
    """Fill missing URL/domain from the last known browser context in the session."""
    last_host = last_port = last_hash = last_domain = ""
    last_url = ""
    out: list[EventFeatures] = []
    for f in feats:
        if f.is_browser and f.url:
            last_url = f.url
            last_host = f.url_host or last_host
            last_port = f.url_port or last_port
            if f.url_hash and f.url_hash != "dashboard":
                last_hash = f.url_hash
            elif not f.url_hash or f.url_hash == "dashboard":
                f.url_hash = last_hash
            if f.domain:
                last_domain = f.domain
        elif f.is_browser and not f.url:
            f.url = last_url
            f.url_host = last_host
            f.url_port = last_port
            f.url_hash = last_hash
            if not f.domain:
                f.domain = last_domain
        elif f.is_swivel:
            # Keep last portal identity; this is the copy-paste hop, not a new process.
            if not f.url_hash:
                f.url_host = last_host
                f.url_port = last_port
                f.url_hash = last_hash
                f.url = last_url
            if not f.domain:
                f.domain = last_domain
        elif f.domain:
            last_domain = f.domain
        if f.domain:
            last_domain = f.domain
        if f.url_hash:
            last_hash = f.url_hash
            last_host = f.url_host or last_host
            last_port = f.url_port or last_port
        out.append(f)
    return out


def process_key(f: EventFeatures) -> str:
    """Stable key used by the segmenter: (portal domain, hash) or doc/noise."""
    if f.is_noise and not f.is_browser and not f.is_swivel:
        return "unrelated"
    route = ROUTE_NAMES.get(f.url_hash, f.url_hash.replace("-", "_") if f.url_hash else "")
    if f.domain and route and route != "dashboard":
        return f"{f.domain}_{route}"
    if f.domain and (not route or route == "dashboard"):
        # Dashboard / empty hash: stay on last real route via carry-forward; else unrelated.
        return "unrelated"
    if f.doc_hint:
        return f.doc_hint
    if f.is_swivel:
        return "desktop_doc"
    if f.is_browser:
        return "unrelated"
    return "unrelated"


def label_for_key(key: str) -> str:
    return key or "unrelated"
