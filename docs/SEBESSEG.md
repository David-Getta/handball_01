# Sebesség-profil — a réteg-csomag ideje egy teljes meccsen

*Generált fájl — ne kézzel szerkeszd. Frissítés:*
`cd backend && python -m scripts.speed_profile`

A kész termék sebesség-célja (`docs/ROADMAP.md`, "Sebesség-cél"):
egy 60 perces meccs TELJES elemzése ≤ 15 perc
a pilot GPU-s szerverén, a gyors kép ≤ 3 perc.
Ez a lap a RÉTEG-részt méri (kész követésből a 500+ elemző réteg),
amelyre a keret ≤ 5 perc CPU-n — a többi a
felismerésé, azt a pilot valódi felvételen méri.

Mérés: 3600 mp-es szimulált meccs, 8.33 fps (a termék ritkítása), 30000 kocka; verzió v0.1.193+3a9da7c5; gép: x86_64, 4 mag, Python 3.11.17.

- **Rétegek összesen: 1 perc 16 mp** (521 réteg, átlag 146 ms) — ítélet: **MEGFELEL**
- Gyors kép (coach_summary, xg, defense, training_focus): 1 perc 4 mp
- Szimuláció (nem a termék része): 937 ms

## A 15 leglassabb réteg

| Réteg | Idő | A csomag %-a |
|---|---|---|
| `coach_summary` | 1 perc 4 mp | 83.8% |
| `intensity_trend` | 880 ms | 1.2% |
| `defense_system_choice` | 681 ms | 0.9% |
| `shooter_defender_matchup` | 348 ms | 0.5% |
| `advanced_defender_roles` | 308 ms | 0.4% |
| `keeper_choice` | 263 ms | 0.3% |
| `key_moments` | 203 ms | 0.3% |
| `pressure_decision_quality` | 197 ms | 0.3% |
| `defensive_gaps` | 197 ms | 0.3% |
| `advanced_defender` | 190 ms | 0.3% |
| `wall_gaps` | 165 ms | 0.2% |
| `clutch_defense_shape` | 159 ms | 0.2% |
| `attack_duration_efficiency` | 154 ms | 0.2% |
| `line_height_by_score` | 153 ms | 0.2% |
| `press_after_goal` | 148 ms | 0.2% |

## Olvasat

A réteg-csomag ideje a kocka-számmal nő: a lassú rétegek a
kockánként dolgozó alap-mérések (lövés-felismerés, poszt-becslés,
formáció), amelyeket a `primitive_cache` hatókör meccsenként
egyszer számol — a csomagban tehát a fenti összeg a felső
korlát, a megosztott mérések miatt a valóság kevesebb. Ha egy
réteg a csomag több mint 10%-át viszi, az a gyorsítás első
jelöltje (gyorsítótárazott alap-mérés, időablakos számolás).

