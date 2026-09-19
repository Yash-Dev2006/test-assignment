"""Fill Japanese memo / portal note text from structured case rows.

Clipboard payloads in the logs redact `text_content`. This prototype uses the
fields that *do* appear on screen (extracted_text lists + form ids like pi-note)
to generate the note operators currently paste by hand.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

CASE_ID_RE = re.compile(r"(P\d+-\d+-\d+)")
WARNING_MARKERS = ("⚠", "警告", "例外", "要確認")


def is_exception(case: dict[str, Any]) -> bool:
    blob = " ".join(str(case.get(k) or "") for k in ("name", "item", "status", "flags", "note"))
    status = (case.get("status") or "").strip()
    if any(m in blob for m in WARNING_MARKERS):
        return True
    if status in ("未確認", "未処理", "要確認"):
        return True
    return False


def render_portal_note(case: dict[str, Any]) -> str:
    """Text destined for portal fields like #pi-note / #ob-note."""
    cid = case.get("case_id") or ""
    name = case.get("name") or ""
    item = case.get("item") or ""
    amount = case.get("amount") or "—"
    status = case.get("status") or ""
    emp = case.get("employee_or_vendor_id") or ""
    if is_exception(case):
        return (
            f"【要確認】{cid} {name}（{emp}）\n"
            f"項目: {item} / 金額: {amount} / 画面ステータス: {status}\n"
            "自動下書き停止。警告マークまたは未処理のため人手レビュー。"
        )
    return (
        f"{cid} {name}（{emp}）\n"
        f"項目: {item} / 金額: {amount}\n"
        f"照合結果: 画面ステータス「{status or '完了'}」に基づき備考を自動生成。"
        " 金額・取引先はポータル一覧から転記。例外なし。"
    )


def render_settlement_memo(cases: list[dict[str, Any]]) -> str:
    auto = [c for c in cases if not is_exception(c)]
    manual = [c for c in cases if is_exception(c)]
    lines = [
        "精算確認メモ（自動下書き）",
        "================================",
        f"件数: {len(cases)}  自動転記可: {len(auto)}  人手レビュー: {len(manual)}",
        "",
        "■ 自動転記候補",
    ]
    for c in auto:
        lines.append(
            f"- {c.get('case_id')} | {c.get('employee_or_vendor_id')} | {c.get('name')} | "
            f"{c.get('item')} | {c.get('amount')} | {c.get('status')}"
        )
    lines += ["", "■ 人手レビュー（警告 / 未確認）"]
    if not manual:
        lines.append("- （なし）")
    for c in manual:
        lines.append(
            f"- {c.get('case_id')} | {c.get('employee_or_vendor_id')} | {c.get('name')} | "
            f"{c.get('item')} | {c.get('amount')} | {c.get('status')}  ← 停止"
        )
    lines += [
        "",
        "残作業: 例外行の金額確認、ポータルへの貼り付け承認、SSO ログインは対象外。",
    ]
    return "\n".join(lines) + "\n"


def load_cases(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "cases" in data:
        return list(data["cases"])
    if isinstance(data, list):
        return data
    raise ValueError("Expected a JSON list, {\"cases\": [...]}, or CSV")


def write_outputs(cases: list[dict[str, Any]], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    memo_path = out_dir / "settlement_memo.txt"
    notes_path = out_dir / "portal_notes.jsonl"
    csv_path = out_dir / "spreadsheet_rows.csv"
    memo_path.write_text(render_settlement_memo(cases), encoding="utf-8")
    with notes_path.open("w", encoding="utf-8") as fh:
        for c in cases:
            row = {
                "case_id": c.get("case_id"),
                "exception": is_exception(c),
                "portal_field": c.get("portal_field") or "pi-note",
                "note": render_portal_note(c),
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["case_id", "employee_or_vendor_id", "name", "item", "amount", "status", "exception", "note"],
        )
        w.writeheader()
        for c in cases:
            w.writerow(
                {
                    "case_id": c.get("case_id"),
                    "employee_or_vendor_id": c.get("employee_or_vendor_id"),
                    "name": c.get("name"),
                    "item": c.get("item"),
                    "amount": c.get("amount"),
                    "status": c.get("status"),
                    "exception": is_exception(c),
                    "note": render_portal_note(c).replace("\n", " / "),
                }
            )
    return {"memo": str(memo_path), "notes": str(notes_path), "csv": str(csv_path)}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate settlement memo + portal notes from case JSON/CSV")
    p.add_argument("--input", default="automation/sample_cases.json")
    p.add_argument("--out", default="automation/out")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    cases = load_cases(Path(args.input))
    written = write_outputs(cases, Path(args.out))
    n_exc = sum(1 for c in cases if is_exception(c))
    print(
        json.dumps(
            {"cases": len(cases), "exceptions": n_exc, "auto": len(cases) - n_exc, **written},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
