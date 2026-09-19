# Note-draft prototype

Operators in Dataset B copy values between local portals (`127.0.0.1:5132/5133/5134`) and Notepad/Word/Excel, then paste a remark into fields such as `#pi-note` and `#ob-note`. Clipboard *content* is redacted in the logs (`text_content: null`), so this tool drafts the memo from structured case rows taken from `context.extracted_text`.

## Run

From the repo root:

```bash
python3 -m src.automation.demo --input automation/sample_cases.json --out automation/out
```

Writes:

- `settlement_memo.txt` — 精算確認メモ-style draft
- `portal_notes.jsonl` — one note per case for the portal textarea
- `spreadsheet_rows.csv` — same rows for Excel

Exception rows (⚠, 未確認, 未処理) are listed but **not** auto-approved.

## Out of scope

Live browser RPA, SSO, and posting into the mock HTTP apps.
