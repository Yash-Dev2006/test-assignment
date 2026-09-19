# README1 — What this repository did

Here is the actual version of the intern selection task walk-through.

The original assignment is [README.md](README.md) and it is not a how-to.
-The file **[DATA_SCHEMA.md](DATA_SCHEMA.md)** describes how to read the logs, not what should be automated.
The client-facing judgment (covering ROI, risks, and time) is given in [REPORT.md].
The text referred to as [WORKLOG.md](WORKLOG.md) consists of the parts that were attempted and then discarded in this build.

You can run all of it with a single command using only the Python 3 standard library.

```bash
python3 run.py
```

---

## 1. Goal

Retrieve the units of work from the PC operation logs, rank the processes in Dataset B with a view to automating them, and deliver a prototype that runs.

Dataset A (`dataset_a 2/`) includes ground truth; it is employed for one IoU measurement so that we can determine whether the cutter is good enough to rank. Dataset B (`dataset_b/`), on the other hand, has no ground truth and is used for production analysis. The Japanese process names from dataset A are not copied over to dataset B.

By saying "good enough" we mean that the same gold process usually results in the same predicted label and that most gold spans have an intersection-over-union (IoU) of at least 0.5 with a predicted span. It does not refer to the billable time from the segments.

---

## 2. Repository map

| Path | Role |
|---|---|
| `run.py` | This is the only public entry point. First, it runs Eval A, then segments and ranks B, then shows a demo. |
| `pipeline.py` | Merge chunks, drop `SYSTEM`, label portal routes, cut when the route changes or after 60 seconds of no activity. |
| eval_a.py | When using a single IoU pass with gt_manifest.json, there is no grid search. |
The product score is used to rank the labels in `analyze_b.py`.
| `demo.py` | Makes memos, portal notes, and CSV drafts from case JSON. |
The dataset_a 2 folder contains 63 sessions, approximately 162 thousand events, and the ground truth. The name of the folder is dataset_a 2.
| `dataset_b/` | 15 sessions. About 20,000 events. No GT. |
| `segments.jsonl` | Step 1 result (Dataset B, not `unrelated`). |
| `artifacts/eval_a.json` | Dataset A results. System idle for 60 seconds. |
The file artifacts/analysis_b.json contains the complete ranking, including the unrelated items.
The cases in the file `automation/sample_cases.json` were obtained from B's `extracted_text` (the text that was copied to the clipboard has been redacted).
| `automation/out/` | Demo results. |

Chunks are not process boundaries but recording buckets. Ingestion joins them according to the timestamp.

---

## 3. The first step—how a click stream becomes a label

The log contains no entry indicating that "an expense claim was started". A unit of work is defined as the time spent on a single portal route (`127.0.0.1` port together with a URL hash such as `#/payroll-items`), this including the time spent using Excel / Word / Notepad while retaining the final actual hash (from copy-and-paste).

Rules in `pipeline.py`:

- Drop `SYSTEM` events.
The port 5122/5132 is assigned to hr, 5123/5133 to finance, and 5124/5134 to ops.
Change `#/payroll-items` to `payroll_items`, and make the same change for onboarding, leave, and social-insurance.
The dashboard hashes are used for navigation: keep the most recent route, otherwise use 'unrelated'.
- If the Explorer/Teams/terminal has no portal context then it is deemed unrelated.
- Split whenever the label changes or when idle time exceeds 60 seconds. There is no debounce grid.

The labels are in snake_case (for example hr_payroll_items) not the `family_name` values from Dataset A.

Dataset A evaluation (`artifacts/eval_a.json`, 1,752 gold executions):

| Metric | Value |
|---|---|
| Mean IoU | 0.627 |
| Median IoU | 0.733 |
The proportion of gold spans with an IoU of at least 0.5 is 73.1%.
The purity of the label (with the same gold code resulting in a single predicted label) is 0.961.

The Gold code I frequently results in 'unrelated' (in the case of work that involves a lot of Excel and has a weak portal signal). That error remains visible.

`segments.jsonl` has one JSON object on each line.

```json
{"session_id": "ses_…", "start": "2026-07-01T16:44:42Z", "end": "2026-07-01T16:45:16Z", "label": "finance_payroll_items"}
```

The unrelated rows are left out of the file, even though they do appear in artificials/analysis_b.json.

---

## 4. Step 2. Dataset B ranking

There are four hashed users and 15 sessions. The work involved sitting in swivel chairs: using Edge on ports `:5132` (HR), `:5133` (finance), `:5134` (ops), as well as Word, Excel and Notepad. The operators paste information into portal fields such as `#pi-note`. The text on the clipboard is empty; only the number of events are used.

The three portals have identical hash routes: `#/payroll-items` covers the payroll-style rows on the HR section, the PO/vendor lists on finance, and the inventory batches on ops. It is the procedure—consisting of opening the list, copying the fields and then pasting a note—that we are automating.

Score = executions multiplied by dwell_seconds by people and then by (1 + clipboard_per_exec). The term +1 ensures that a process with no clipboard events does not receive a zero score. Although unrelated has a high volume it is still deferred (lacking in structure, with Teams and Explorer noise).

**Priority** (from `artifacts/analysis_b.json`):

1. `hr_payroll_items` — 31 executives, 1168s, 143 clipboard events, 4 individuals, the highest score.
— ops_leave_applications — 19 executives, a long dwell time, and a high clipboard usage. It was a strong second choice, with a more mixed use of Excel.
3. `finance_payroll_items`. 28 exec. Same 4 people. Same list plus note pattern.
4. For hr_onboarding — 17 executives; the word checklist is being applied in the process.
5. `ops_payroll_items` — 18 executives, the highest number of items per executive (~5.1).
6. Other leave, tax, or insurance routes. Fewer executions. Same note-paste pattern.
7. **Defer:** unrelated (Explorer, Teams, terminal, OpenWith).

The build target selected was the `#/payroll-items` family (involving HR and finance and ops): there are 77 executions in this instance, 31 plus 28 plus 18 equals 77, and the most common type is the structured list followed by a note, with all four people participating, and no instances involving Teams.

The speed of logs is increased in comparison to that of production, and the rankings are relative not absolute in terms of FTE hours.

---

## 5. Step 3. Prototype

`demo.py` changes structured case rows into:

- `automation/out/settlement_memo.txt` , 精算確認メモ-style draft
- `automation/out/portal_notes.jsonl` is the case-by-case text for `#pi-note` or `#ob-note`.
- `automation/out/spreadsheet_rows.csv` — consists of the same rows for Excel

Exception rows (⚠, 未確認, 未処理) are listed and are not auto-approved. Sample input: [automation/sample_cases.json](automation/sample_cases.json).

**Reason for this process and scope:** because it involves the highest-impact list plus note loop. The scope refers only to the generation of drafts, not to clicking on a live desktop environment: the only API available is mock localhost applications; since the clipboard contents are not available, it is not possible to verify the pixel RPA; warning rows are already subject to a human check.

**Reason for choosing this method:** Deterministic Python works offline and has a one-to-one correspondence with the actual fields. We don't have a tenant or connectors for n8n / Power Automate. Full desktop RPA is unsuitable since there is no running user interface. A standalone LLM agent would come up with amounts from redacted clipboards.

Logging in through SSO, deciding on the unconfirmed rows, confirming the ⚠ vendors, putting in or clicking 'Complete', and covering any case not listed in the schema.

This sample includes 77 executions of payroll-items together with several clipboard events each; if half of those paste operations result in 'generate note → human clicks paste', then repetitive typing will decrease whereas exception handling will not.

---

## 6. Reproduce

From the repo root:

```bash
python3 run.py
```

Skip Dataset A (faster) if you only need B + demo:

```bash
python3 run.py --skip-a
```

Expected files: `artifacts/eval_a.json` (unless you use `--skip-a`), `artifacts/analysis_b.json`, `segments.jsonl`, `automation/out/*`.

The datasets and screenshots are large and local; they are not intended to be fully versioned.

---

## 7. What we did not do

- The screenshot or OCR models (since the text extracted already includes lists and tables).
- Transfer the Japanese family names from dataset A to dataset B.
Grid search thresholds or use sequence models.
- Carry out real-time RPA against the mock HTTP portals.
- Automate Teams, Explorer, or policy Word documents.

---

## The deliverables for the assignment compared to this repository

| Assignment item | Where it is |
|---|---|
Step 1 output on Dataset B. See [segments.jsonl](segments.jsonl).
| Full repository + git history | this repo |
| Final report | [REPORT.md](REPORT.md) |
| Work log | [WORKLOG.md](WORKLOG.md) |
| For this walkthrough | this file (`README1.md`) |
