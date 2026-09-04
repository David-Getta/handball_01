# SportMachine — Executive Summary (EN)

*One-page project summary for EU funding applications (EIC
Pre-accelerator / EIC Accelerator). Hungarian planning documents:
`docs/PALYAZAT_EIC_PRE_ACCELERATOR.md`, `docs/PALYAZAT_EIC.md`.*

## What it is

SportMachine turns a single video recording of a handball match —
captured with one panning camera or a phone — into coach-ready
tactical intelligence: match reports, opponent scouting profiles,
match plans and weekly training focus, all generated automatically
and phrased in the coach's own language.

## The problem

Sports analytics today serves the professional elite. Existing
solutions (multi-camera installations, wearable sensors, cloud
platforms) are too expensive and too complex for the long tail of
European sport: youth academies, schools and lower-division clubs —
hundreds of thousands of teams across the EU with no affordable access
to objective match analysis.

## The technology (deep-tech core)

- **Single panning camera → full tactical picture**: proprietary
  calibration, out-of-frame position estimation and single-camera ball
  tracking.
- **Rule-aware analysis layer** — unique on the market: suspensions,
  seven-metre throws and passive-play risk are recognised from the
  imprint of referee decisions in the tracking data itself.
- **Explainable AI chain**: every verdict is backed by an explicit,
  inspectable threshold — no black boxes (GDPR / AI Act friendly).
  With few samples the system stays silent rather than guessing.
- **On-premise processing**: no video upload, no cloud dependency —
  critical for clubs working with minors.
- **504 analysis layers** across attack, defence, goalkeeping, rules,
  momentum and physical load; **2,209 automated tests** and a
  reproducible benchmark guard the quality of every release. (Live
  figures, generated from the codebase: `docs/SZAMOK.md`; per-layer
  catalogue: `docs/RETEG_KATALOGUS.md`.)

## Product surfaces

One engine, many outputs: REST API and match packages; Hungarian
coach-language match summaries; multi-match opponent scouting with
match-plan rules ("their weakness × your strength"); weekly training
focus with concrete drills; printable HTML reports; a Flutter desktop
client with 260+ scouting tiles.

## Market and scaling

Entry sport: handball (a European strength sport with strong Hungarian
references). The pipeline is sport-agnostic by design — basketball,
futsal and ice hockey reuse the same engine. Business model: per-club
licence and season subscription, priced for the amateur segment.

## Status and ask

Working end-to-end prototype validated on simulated and real footage
(TRL 3–4). The EIC Pre-accelerator project (24 months, €300–500k,
70% funding rate) closes TRL 4 on annotated real-match datasets,
runs a 3–5 club pilot to TRL 5, demonstrates a season-long multi-club
deployment (TRL 6), and prepares the company for the EIC Accelerator.

## Why EU / widening support

A Hungarian deep-tech SME bringing exportable, affordable sport
technology from a widening country to an EU-wide underserved market —
precisely the gap the EIC Pre-accelerator was created to close.
