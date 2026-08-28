# EIC Pre-accelerator — Part B draft skeleton (EN)

*Working skeleton for the proposal's technical part, following the
Excellence / Impact / Implementation structure used by the evaluators.
Fill-in markers: ⬜ = needs company/financial data that does not live
in this repository. Companion documents:
`docs/PALYAZAT_EIC_PRE_ACCELERATOR.md` (plan, HU),
`docs/EXECUTIVE_SUMMARY_EN.md` (one-pager).*

---

## 1. Excellence

### 1.1 Problem and vision

Objective match analysis is out of reach for the long tail of European
sport. SportMachine turns a single panning-camera (or phone) recording
of a handball match into coach-ready tactical intelligence — reports,
opponent scouting, match plans and weekly training focus — with zero
extra hardware and fully on-premise processing.

### 1.2 The innovation (deep-tech core)

- Single-camera pipeline: panning-camera calibration, out-of-frame
  position estimation, single-camera ball tracking, jersey-number OCR
  with a self-trained digit network (synthetic data, reject class).
- **Rule-aware layer (unique on the market)**: suspensions,
  seven-metre throws and passive-play risk recognised from the imprint
  of referee decisions in tracking data alone.
- **Explainable AI chain**: every verdict is tied to explicit,
  inspectable thresholds; with insufficient samples the system stays
  silent instead of guessing (AI Act / GDPR-friendly by design).
- 503 analysis layers over a shared tracking data model; outputs
  phrased automatically in coach language.

### 1.3 Current status (TRL) and evidence

- End-to-end prototype working on simulated and real footage (TRL 3–4).
- Evidence infrastructure already in place: 2,140 automated tests,
  reproducible benchmark (`python -m scripts.benchmark`), built-in
  precision/recall validation against human annotation
  (`scripts/validate_match`), and a dated, versioned measurement
  ledger (`docs/MERESI_JEGYZOKONYV.md`).
- ⬜ TRL 4 closure on annotated real-match datasets is the first
  work package (see 3.2).

### 1.4 IPR

⬜ Codebase, trademark and know-how held by the applicant SME;
freedom-to-operate screening planned in WP4 (patentable elements:
panning-camera calibration + out-of-frame estimation + rule-imprint
recognition).

## 2. Impact

### 2.1 Market

- Underserved segment: youth academies, schools, lower divisions —
  hundreds of thousands of teams in the EU; incumbent solutions
  (multi-camera installs, wearables, cloud platforms) target the
  professional elite at professional prices.
- Entry market: Hungarian handball (strong domestic references);
  expansion: EU handball nations, then sport-agnostic scaling
  (basketball, futsal, ice hockey on the same engine).
- ⬜ TAM/SAM/SOM quantification, pricing study.

### 2.2 Business model

Per-club licence + season subscription, priced for the amateur
segment; on-premise deployment keeps operating costs and data-privacy
risk low. ⬜ 3-year financial projection.

### 2.3 European added value / widening

A Hungarian deep-tech SME exporting affordable sport technology to an
EU-wide underserved market — the exact gap the Pre-accelerator
addresses; the project explicitly prepares the company for the EIC
Accelerator.

## 3. Quality and efficiency of implementation

### 3.1 Team

⬜ Founder(s), technical lead, sport-domain advisors, part-time
finance. Hiring plan under the grant: computer-vision engineer,
pilot/customer-success operator.

### 3.2 Work plan (24 months)

| WP | Months | Content | Key KPI |
|---|---|---|---|
| WP1 Real-data validation | 1–6 | annotated real-match dataset (≥10 matches), accuracy targets, measurement ledger | goal recall ≥ target on real footage; ledger public per release |
| WP2 Pilot (TRL 5) | 4–14 | 3–5 clubs use the product across a half-season; robustness in real halls (lighting, occlusion, crowd) | ≥3 active pilot clubs; ≥40 matches analysed |
| WP3 Demonstration (TRL 6) | 12–24 | season-long multi-club deployment, productisation (installer, licensing, support) | ≥8 clubs; first paying licences |
| WP4 IPR + investment readiness | 6–24 | FTO analysis, IP strategy, pitch materials, LOIs, EIC Accelerator application | FTO report; ≥5 LOIs; Accelerator Step 1 submitted |

### 3.3 Risks

| Risk | L | Mitigation |
|---|---|---|
| Real-footage accuracy below target | M | measurement ledger catches early; fine-tuning path exists (`docs/FINETUNE.md`) |
| Pilot clubs churn | M | over-recruit, NCP/federation channels, free pilot licence |
| Competitor moves down-market | L | cost structure (no hardware) and rule-aware/explainable differentiation |
| 30% co-funding gap | M | ⬜ own resources plan / bridge investor |

### 3.4 Budget

⬜ €300–500k total, 70% EU / 30% own; personnel-dominated cost plan
per WP.
