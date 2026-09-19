# Final report: operation logs to an automation proposal

This is a one-day MVP. The goal is client ROI, not a production RPA stack. Dataset A (`dataset_a 2/`) was used only to freeze segmentation thresholds. Dataset B is the production analysis. Process names from A were **not** copied onto B.

How to reproduce:

```bash
python3 -m src evaluate-a --root "dataset_a 2" --out artifacts/eval_a.json
python3 -m src analyze-b --root dataset_b --out artifacts/analysis_b.json --segments-out segments.jsonl
python3 -m src demo --input automation/sample_cases.json --out automation/out
```

---

## Step 1 — Recovering units of work

The logs are a click stream. A “unit of work” is treated as **time spent on one portal route** (URL hash such as `#/payroll-items`) including the Excel/Word/Notepad hops that belong to that screen (copy-paste). Alt-Tab flicker under 4 seconds is not a new process. Idle gaps over 90 seconds close a segment.

**Frozen thresholds** (grid on 1,752 gold executions in Dataset A): `debounce_ms=4000`, `idle_ms=90000`.

| Metric | Value |
|---|---|
| Mean IoU vs `gt_manifest` executions | **0.635** |
| Median IoU | 0.722 |
| Share of gold spans with IoU ≥ 0.5 | **76.4%** |
| Label purity (same gold `process_code` → one predicted label) | **0.964** |

That is “good enough” for ranking automation: boundaries are usually in the right neighborhood, and the same gold process maps to a stable label. We did not chase 0.9 IoU with screenshots or sequence models.

Gold code `I` often lands on `unrelated` (Excel-heavy work with weak portal signal). That is a known miss, documented rather than papered over.

Dataset B output: [`segments.jsonl`](segments.jsonl) (164 non-`unrelated` rows). Labels are snake_case route names (`hr_payroll_items`, not Dataset A’s Japanese family names).

---

## Step 2 — Dataset B analysis and ranked candidates

Four machines / four hashed users, 15 sessions, ~20k events. Work is **swivel-chair**: Microsoft Edge on `127.0.0.1:5132` (HR), `:5133` (finance), `:5134` (ops/inventory), plus Word, Excel, and Notepad (`精算確認メモ`, `在庫調整メモ`, `IT申請メモ`). Clipboard **length** is recorded; clipboard **text is redacted**. Operators paste into portal textareas `#pi-note`, `#ob-note`, `#la-note`, `#si-note`, `#rt-note`.

The three portals share the same hash routes. `#/payroll-items` on finance is an order/PO list; on HR it is payroll-item style rows; on ops it is inventory batches. The **procedure** (open list → copy fields → paste a note) is the same, which is what we automate.

Ranking = frequency × dwell time × people × copy-paste rate × feasibility. `unrelated` (Teams, Explorer, terminal) is scored down and deferred.

**Priority order** (from [`artifacts/analysis_b.json`](artifacts/analysis_b.json)):

1. **`hr_payroll_items`** — 26 executions, 1353s dwell, 141 clipboard events, 4 people. Highest score (97.6).
2. **`finance_payroll_items`** — 23 exec, 1191s, same 4 people. Same UI pattern on the finance host.
3. **`finance_resident_tax`** — 18 exec, 803s.
4. **`ops_payroll_items`** — 16 exec, 711s, high clipboard rate.
5. **`ops_leave_applications`** — 16 exec, 1158s (long dwell, slightly less “list confirm” structure).
6. **`hr_onboarding`** — 14 exec, 1024s; Word checklist (`nyusha_checklist_*`) in the loop.
7. Leave / social-insurance routes — fewer executions; still the same note-paste pattern.
8. **Defer:** Teams, Explorer, OpenWith, one-off Word policy docs, and `unrelated`.

**Chosen automation target:** the **`#/payroll-items` family** (HR + finance + ops hosts). It is the most frequent, involves everyone in the B sample, is dominated by structured list rows plus a notes field, and does not require driving Microsoft Teams.

Onboarding is a strong runner-up (long dwell, checklist Word doc) but has more document branches. Leave applications are similar but less frequent on the HR host.

Logs are sped up versus production. Rankings are **relative**, not claimed hours saved per year.

---

## Step 3 — What we built, and why

**Built:** a Python CLI ([`src/automation/demo.py`](src/automation/demo.py)) that turns structured case rows into:

- a 精算確認メモ-style draft
- per-case portal notes for `#pi-note` / `#ob-note`
- a CSV for Excel

Exception rows (⚠, 未確認, 未処理) are listed and **not** auto-approved. Sample input is taken from real `extracted_text` on Dataset B screens ([`automation/sample_cases.json`](automation/sample_cases.json)).

### Why this process and this scope

Impact is highest on the payroll-items / PO / inventory **list + note** loop. Scope is **draft generation**, not clicking the live desktop, because:

- There is no live API besides mock `127.0.0.1` apps that are not running here.
- Clipboard contents are missing from the logs, so a pixel RPA bot cannot be validated against ground-truth paste strings.
- Warnings on rows are already a human gate; automating those would destroy trust.

A shared note-renderer can later cover onboarding (`ob-note`) and leave (`la-note`) without a second product.

### Why this implementation form (and what we rejected)

| Option | Decision |
|---|---|
| Deterministic Python CLI | **Chosen.** Runs offline, easy to demo, maps 1:1 to observed fields. |
| n8n / Power Automate | Rejected. No client tenant, no connectors to `127.0.0.1` mock portals. |
| Full desktop RPA | Rejected. Fragile selectors, no running UI, OpenWith/Explorer noise in the logs. |
| LLM-only agent | Rejected for day one. Japanese UI + missing clipboard text would hallucinate amounts. An LLM can sit *behind* the same JSON later. |

### Manual work that remains, and realistic impact

Still human: login/SSO, deciding 未確認 rows, confirming ⚠ vendors, actually pasting/clicking Complete in the portal, and any case not in the list schema.

Realistic impact **in this sample:** about **65 executions** of the payroll-items family (HR+finance+ops) with ~5 clipboard events each. If half of those pastes become “generate note → human clicks paste,” the repetitive typing/formatting is cut; exception handling is not. Relative to other B processes, this is the largest slice of structured work. Absolute FTE savings would be a lie given compressed wait times in the capture environment.

### Risks and mitigations

| Risk | Evidence | Mitigation |
|---|---|---|
| Wrong segment boundaries | Mean IoU 0.64, not 0.9; gold `I` → `unrelated` | Use segments for *ranking*, not for billing; review a sample of B sessions before rollout |
| Same hash route, different business meaning | Finance `#/payroll-items` shows PO vendors; HR shows people | Parameterize templates per host/port; do not hard-code “payroll” copy |
| Mock localhost APIs | URLs are `127.0.0.1:513x` | Treat as a stand-in for a real intranet; integration is a later phase |
| PII in clipboard / screen text | Names, employee IDs, vendor names in `extracted_text` | Keep drafts local; redact before any LLM vendor; existing agent already redacts clipboard text |
| Japanese UI / policy docs | Word titles like `gyomu_itaku_keihi_kitei` | Template in Japanese; do not auto-edit policy Word files |
| `text_input_complete` unusable | Spec + null `text_content` | Reconstruct from list OCR + form field ids only |

---

## Time allocation (compressed 1 day instead of 7)

| Block | What happened |
|---|---|
| Ingest + inventory | Confirmed B portals/routes; ignored duplicate `dataset_a *` folders |
| Segment + eval | Rule-based cutter; froze 4s / 90s after grid |
| Dataset B segments + ranking | `segments.jsonl` + `artifacts/analysis_b.json` |
| Prototype | Note/CSV generator with exception stop |
| Write-up | This report + work log |

**Deferred:** screenshot models, multi-process bots, live RPA, cleaning duplicate dataset folders, production SSO.

---

## Deliverables checklist

- [`segments.jsonl`](segments.jsonl) — Step 1 on Dataset B
- This report
- [`WORKLOG.md`](WORKLOG.md)
- Git history of the analysis code (datasets and screenshots are local; too large to version)
