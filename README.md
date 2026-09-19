# README1 — What this repository did

This is the walkthrough of the intern selection task as actually built.

- **[README.md](README.md)** is the original assignment. It is not a how-to.
- **[DATA_SCHEMA.md](DATA_SCHEMA.md)** explains how to read the logs, not what to automate.
- **[REPORT.md](REPORT.md)** is the client-facing judgment (ROI, risks, time).
- **[WORKLOG.md](WORKLOG.md)** is what was tried and cut on this build.

Run everything with one command. Python 3 stdlib only.

```bash
python3 run.py
```

---

## 1. Goal

Recover units of work from PC operation logs, rank Dataset B processes for automation, and ship a prototype that runs.

Dataset A (`dataset_a 2/`) has ground truth. It is used for **one** IoU measurement so we know whether the cutter is good enough to rank. Dataset B (`dataset_b/`) has no ground truth; it is the production analysis. Japanese process names from A are **not** copied onto B.

“Good enough” here means: same gold process usually gets the same predicted label, and most gold spans overlap a predicted span at IoU ≥ 0.5. It does **not** mean billable time from segments.

---

## 2. Repository map

| Path | Role |
|---|---|
| `run.py` | Only public entry. Eval A → segment/rank B → demo. |
| `pipeline.py` | Merge chunks, drop `SYSTEM`, label portal routes, cut on route change or 60s idle. |
| `eval_a.py` | Single IoU pass vs `gt_manifest.json`. No grid search. |
| `analyze_b.py` | Rank labels with a product score. |
| `demo.py` | Memo / portal-note / CSV drafts from case JSON. |
| `dataset_a 2/` | 63 sessions, ~162k events, ground truth. Folder name is `dataset_a 2`. |
| `dataset_b/` | 15 sessions, ~20k events, no GT. |
| `segments.jsonl` | Step 1 deliverable (Dataset B, non-`unrelated`). |
| `artifacts/eval_a.json` | Dataset A metrics (60s idle). |
| `artifacts/analysis_b.json` | Full ranking, including `unrelated`. |
| `automation/sample_cases.json` | Cases taken from B `extracted_text` (clipboard text is redacted). |
| `automation/out/` | Demo outputs. |

Chunks are recording buckets, not process boundaries. Ingest concatenates them by timestamp.

---

## 3. Step 1 — how a click stream becomes a label

Nothing in the log says “expense claim started.” A unit of work is **time on one portal route** (`127.0.0.1` port + URL hash such as `#/payroll-items`), including Excel / Word / Notepad hops that keep the last real hash (copy-paste).

Rules in `pipeline.py`:

- Drop `SYSTEM` events.
- Port `5122/5132` → `hr`, `5123/5133` → `finance`, `5124/5134` → `ops`.
- Hash `#/payroll-items` → `payroll_items`, and the same for onboarding, leave, social-insurance, resident-tax.
- Dashboard hashes are navigation: keep the last real route, else `unrelated`.
- Explorer / Teams / terminal with no portal context → `unrelated`.
- Split when the label changes **or** idle exceeds **60 seconds**. No debounce grid.

Labels are snake_case (`hr_payroll_items`), not Dataset A `family_name` values.

**Dataset A eval** (`artifacts/eval_a.json`, 1,752 gold executions):

| Metric | Value |
|---|---|
| Mean IoU | 0.627 |
| Median IoU | 0.733 |
| Share of gold spans with IoU ≥ 0.5 | 73.1% |
| Label purity (same gold code → one predicted label) | 0.961 |

Gold code `I` often lands on `unrelated` (Excel-heavy work with a weak portal signal). That miss is left visible.

`segments.jsonl` is one JSON object per line:

```json
{"session_id": "ses_…", "start": "2026-07-01T16:44:42Z", "end": "2026-07-01T16:45:16Z", "label": "finance_payroll_items"}
```

`unrelated` rows are omitted from the file. They still appear in `artifacts/analysis_b.json`.

---

## 4. Step 2 — Dataset B ranking

Four hashed users, 15 sessions. Work is swivel-chair: Edge on `:5132` (HR), `:5133` (finance), `:5134` (ops), plus Word, Excel, Notepad. Operators paste into portal fields such as `#pi-note`. Clipboard **text** is null; only event counts are used.

The three portals share hash routes. `#/payroll-items` is people/payroll-style rows on HR, PO/vendor lists on finance, inventory batches on ops. The **procedure** (open list → copy fields → paste a note) is what we automate.

Score = `executions × dwell_seconds × people × (1 + clipboard_per_exec)`. The `+1` keeps a process with zero clipboard events from scoring zero. `unrelated` scores high on volume; it is still **deferred** (no structure, Teams/Explorer noise).

**Priority** (from `artifacts/analysis_b.json`):

1. `hr_payroll_items` — 31 exec, 1168s, 143 clipboard events, 4 people. Highest score.
2. `ops_leave_applications` — 19 exec, long dwell, high clipboard. Strong runner-up, more mixed Excel.
3. `finance_payroll_items` — 28 exec, same 4 people, same list+note pattern.
4. `hr_onboarding` — 17 exec; Word checklist in the loop.
5. `ops_payroll_items` — 18 exec, highest clipboard per exec (~5.1).
6. Other leave / tax / insurance routes — fewer executions, same note-paste pattern.
7. **Defer:** `unrelated` (Explorer, Teams, terminal, OpenWith).

**Chosen build target:** the `#/payroll-items` family (HR + finance + ops): 31+28+18 = **77 executions** in this sample. Most frequent structured list+note loop, all four people, no Teams driving.

Logs are sped up versus production. Rankings are relative, not claimed FTE hours.

---

## 5. Step 3 — prototype

`demo.py` turns structured case rows into:

- `automation/out/settlement_memo.txt` — 精算確認メモ-style draft
- `automation/out/portal_notes.jsonl` — per-case text for `#pi-note` / `#ob-note`
- `automation/out/spreadsheet_rows.csv` — same rows for Excel

Exception rows (⚠, 未確認, 未処理) are listed and **not** auto-approved. Sample input: [automation/sample_cases.json](automation/sample_cases.json).

**Why this process and scope:** highest-impact list+note loop. Scope is draft generation, not clicking a live desktop: no live API besides mock localhost apps; clipboard contents missing so pixel RPA cannot be checked; warning rows are already a human gate.

**Why this form:** deterministic Python runs offline and maps 1:1 to observed fields. n8n / Power Automate needs a tenant and connectors we do not have. Full desktop RPA is fragile with no running UI. An LLM-only agent would invent amounts from redacted clipboards.

**Still human:** login/SSO, deciding 未確認 rows, confirming ⚠ vendors, pasting/clicking Complete, any case not in the list schema.

**Realistic impact in this sample:** 77 payroll-items executions with several clipboard events each. If half of those pastes become “generate note → human clicks paste,” repetitive typing drops; exception handling does not.

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

Expected files: `artifacts/eval_a.json` (unless `--skip-a`), `artifacts/analysis_b.json`, `segments.jsonl`, `automation/out/*`.

Datasets and screenshots are local and large; they are not meant to be fully versioned.

---

## 7. What we did not do

- Screenshot / OCR models (`extracted_text` already has list tables).
- Transfer Dataset A Japanese family names onto B.
- Grid-search thresholds or sequence models.
- Live RPA against the mock HTTP portals.
- Automating Teams, Explorer, or policy Word documents.

---

## 8. Assignment deliverables vs this repo

| Assignment item | Where it is |
|---|---|
| Step 1 output on Dataset B | [segments.jsonl](segments.jsonl) |
| Full repository + git history | this repo |
| Final report | [REPORT.md](REPORT.md) |
| Work log | [WORKLOG.md](WORKLOG.md) |
| This walkthrough | **this file** (`README.md`) |
