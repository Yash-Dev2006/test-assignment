# Work log

AI (Cursor) was used to explore the schema, implement the Python pipeline, run eval/analyze, and draft this log/report. Thresholds and the automation target were chosen from the measured numbers, not from Dataset A process names.

## What we expected vs what the data showed

- README Dataset A is HR/finance/ops with Chrome + Excel + Notepad. Dataset B is **different hosts** (`5132/5133/5134`) and Edge, but the **same hash routes** (`payroll-items`, `onboarding`, `leave-applications`, …). Transferring A’s Japanese `family_name` labels would have been wrong. We transferred only the method: URL + title + clipboard *events*.
- Clipboard `text_content` is always null. A bot that “replays copies” cannot be checked. That killed full RPA for this day.
- `text_input_complete` is rare and unhelpful, as the spec warned.

## Tries that worked

- Merging chunks by timestamp and dropping `SYSTEM` events.
- Carry-forward of the last real URL hash across Excel/Word/Notepad so a copy-paste hop stays in the same segment.
- Debounce 4s so Alt-Tab is not a new process.
- Grid on Dataset A: 4s debounce + 90s idle beat 60s idle (mean IoU 0.635 vs 0.629). Stopped there.
- Ranking by frequency × time × people × clipboard × feasibility. Payroll-items family won on all four people in the B sample.

## Tries that did not work (or we cut)

- Treating dashboard hashes as their own process — they are navigation, not work. Mapped to last route or `unrelated`.
- Using `unrelated` dwell as an automation candidate — lots of time, no structure. Forced low score.
- Reading 45k screenshots as the primary feature. `extracted_text` already has list tables.
- n8n / Power Automate / LLM agent as the day-one demo: no tenant, no live UI, redacted clipboards.

## Decision log

- **Good enough IoU:** ~0.63 mean / 76% at 0.5. Enough to rank; not enough to claim perfect case boundaries.
- **One prototype:** generate 精算確認メモ + `#pi-note` drafts; stop on ⚠ / 未確認 / 未処理.
- **Not in scope:** posting into the mock HTTP apps, Teams, policy Word documents.

## Commands actually run

```bash
python3 -m src inventory --root dataset_b
python3 -m src evaluate-a --root "dataset_a 2" --grid
python3 -m src evaluate-a --root "dataset_a 2" --out artifacts/eval_a.json
python3 -m src analyze-b --root dataset_b --out artifacts/analysis_b.json --segments-out segments.jsonl
python3 -m src demo --input automation/sample_cases.json --out automation/out
```
