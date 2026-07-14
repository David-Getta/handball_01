# EIC Accelerator — pitch deck (10 dia, angol)

A Step 1 rövid pályázathoz max. 10 diás deck kell PDF-ben. Ez a vázlat
diánként adja a címet, a tartalmat (angolul, beemelhetően) és magyar
megjegyzést arról, mit kell még kitölteni/eldönteni. A `[TODO: ...]`
helyeket a cégadatokkal és a pilot-számokkal kell feltölteni.

---

## Slide 1 — Title / One-liner

> **SportMachine** — Professional-grade match analytics for every handball
> team, from a single camera. No sensors, no multi-camera rig, no cloud.

- Logó, név, tagline, kontakt.
- *(HU: a "single camera, no hardware" a horog — ez különböztet meg.)*

## Slide 2 — Problem

> Match analytics is a luxury. Pro clubs pay €10–50k/year for multi-camera
> systems (Veo, Spiideo) or wearable sensors (Catapult). The 100,000+
> amateur and youth teams across Europe get nothing: coaches rewatch
> full-match videos by hand — hours of work for fragments of insight.

- *(HU: 1 erős szám kell ide az EU-s amatőr/utánpótlás csapatok számáról —
  [TODO: EHF/nemzeti szövetségi statisztika].)*

## Slide 3 — Solution (product demo screenshots)

> One panning camera → full tactical and physical analysis, on the coach's
> own laptop. Upload the match video, mark 4 court corners, get: player
> tracking, heatmaps, shot maps, pass networks, sprint/load monitoring,
> fatigue curves, auto-detected events with video clips (goal / save /
> miss, with the shooter identified), attack-type breakdown (fast break /
> quick restart / positional / 7-on-6), rule-level insights (suspensions,
> penalties, passive-play risk, power-play efficiency), goalkeeper
> analytics, an auto-written coach summary in plain language, printable
> match reports, and opponent scouting with "how to beat them" keys.

- 3-4 valódi képernyőkép (meccs-nézet, lövéstérkép, jelentés, klip-export).
- *(HU: a funkciólista kész — a képernyőképeket a valódi appból kell lőni.)*

## Slide 4 — Why now / Why us (the deep tech)

> The hard problem: a **single panning camera** never sees the full court.
> Our engine solves it with proprietary pieces working together:
> (1) pan-tracking calibration that keeps pixel→meter mapping valid while
> the camera moves; (2) off-screen state estimation that never contaminates
> measured data; (3) plausibility-filtered load analytics robust to
> detection noise; (4) a **rule-understanding layer** that reconstructs
> referee decisions (suspensions, penalties, passive play) purely from
> tracking data — unique in the market; (5) a fully **explainable,
> on-device AI chain** (identity gates from space-time + jersey colour +
> our own digit-recognition net trained without any external data) —
> no cloud, no black box, GDPR/AI-Act friendly for youth sport.
>
> **Measured, reproducible accuracy** (public benchmark in repo):
> calibration error 0.06 m mean · 91% direct measurement coverage ·
> 99% event recall under partial camera view · speed metrics stable
> under 5 cm noise.

- *(HU: ez az Excellence-dia — a benchmark-táblázat ide kerül. A
  "proprietary" szóhoz FTO/szabadalmi ellenőrzés kell [TODO].)*

## Slide 5 — Product status (TRL evidence)

> Working product today (v0.1.x, Windows + macOS): full pipeline from
> video upload to printed report, guided analysis wizard with one-frame
> detection preview, auto-updating desktop app, 300+ automated tests,
> versioned accuracy benchmark as regression gate, built-in quality
> self-check that tells the coach what to fix in plain language.
> Pilot deployments with [TODO: N] clubs in Hungary — [TODO: quotes/LOIs].

- *(HU: TRL 5-6 állítás — a pilot-számok és LOI-k NÉLKÜL ez a dia gyenge;
  ez a legfontosabb kitöltendő.)*

## Slide 6 — Market

> Bottom-up: [TODO: X] registered handball teams in the EU × €[TODO]
> annual subscription = €[TODO]M SAM. Expansion: the engine is
> sport-agnostic (basketball, futsal, ice hockey) — same pipeline,
> different court model. TAM: team sports video analytics, growing
> [TODO]% CAGR.

- *(HU: TAM/SAM/SOM számítás kell [TODO] — EHF-regisztrációk, árpont-teszt
  a pilotokból.)*

## Slide 7 — Business model & GTM

> B2B SaaS-style subscription per team/season, priced for amateur budgets
> (€[TODO]/season vs. €10k+ incumbents). Land: youth academies and
> regional leagues via federations and coach communities. Expand: per-sport
> modules, league-level packages, scouting marketplace.

- *(HU: árazást a pilotok visszajelzésére kell alapozni [TODO].)*

## Slide 8 — Competition

> | | SportMachine | Veo/Spiideo | Hudl | Catapult |
> |---|---|---|---|---|
> | Hardware needed | **none** | fixed multi-cam | cam+cloud | wearables |
> | Runs locally (GDPR/minors) | **yes** | no | no | no |
> | Price point | **amateur** | pro | semi-pro | pro |
> | Handball-specific tactics | **yes** | generic | generic | physical only |

- *(HU: ellenőrizni az aktuális versenytárs-árakat/funkciókat [TODO].)*

## Slide 9 — Team

> [TODO: alapító(k), sport + tech háttér, tanácsadók (pl. edzői/szövetségi
> referenciák), tervezett kulcs-felvételek a grantből.]

- *(HU: az EIC-nél a csapat-dia súlyos — egyszemélyes csapatnál a bővítési
  terv és a tanácsadói kör kritikus.)*

## Slide 10 — The ask & milestones

> Seeking €[TODO: 0.5–2.5]M EIC grant to go from validated prototype
> (TRL 5-6) to market-ready product (TRL 8):
> M1 Sport-specific detector fine-tuned on proprietary dataset (accuracy ×2
> on ball tracking) · M2 jersey-number OCR for persistent player identity ·
> M3 multi-sport engine (basketball, futsal) · M4 [TODO: N] paying pilot
> leagues · M5 CE/compliance + go-to-market.

- *(HU: a mérföldköveknek költséggel és idővonallal kell párosulniuk a
  Step 2-ben — itt elég a lista.)*

---

## Használat

1. Töltsd ki a `[TODO]` helyeket (cég, pilot-számok, piac, árazás, csapat).
2. A 3-4. dia képernyőképeit és benchmark-tábláját a valódi appból/repóból.
3. Vidd át 10 diára (Canva/PowerPoint/Google Slides) — dián max. 5-6 sor.
4. A zsűri EN-ben olvas: a fenti idézett blokkok közvetlenül beemelhetők.
