# Sebesség-profil — a réteg-csomag ideje egy teljes meccsen

*Generált fájl — ne kézzel szerkeszd. Frissítés:*
`cd backend && python -m scripts.speed_profile`

A kész termék sebesség-célja (`docs/ROADMAP.md`, "Sebesség-cél"):
egy 60 perces meccs TELJES elemzése ≤ 15 perc
a pilot GPU-s szerverén, a gyors kép ≤ 3 perc.
Ez a lap a RÉTEG-részt méri (kész követésből a 500+ elemző réteg),
amelyre a keret ≤ 5 perc CPU-n — a többi a
felismerésé, azt a pilot valódi felvételen méri.

Mérés: 3600 mp-es szimulált meccs, 8.33 fps (a termék ritkítása), 30000 kocka; verzió v0.1.193+8aa0932e; gép: x86_64, 4 mag, Python 3.11.17.

- **Rétegek összesen: 1 perc 9 mp** (521 réteg, átlag 133 ms) — ítélet: **MEGFELEL**
- Gyors kép (coach_summary, xg, defense, training_focus): 59,0 mp
- Szimuláció (nem a termék része): 1,1 mp

## A 15 leglassabb réteg

| Réteg | Idő | A csomag %-a |
|---|---|---|
| `coach_summary` | 59,0 mp | 85.0% |
| `intensity_trend` | 655 ms | 0.9% |
| `advanced_defender_roles` | 310 ms | 0.4% |
| `clutch_setplay` | 201 ms | 0.3% |
| `clutch_defense_shape` | 200 ms | 0.3% |
| `advanced_defender` | 182 ms | 0.3% |
| `pass_direction` | 175 ms | 0.3% |
| `line_height_by_score` | 163 ms | 0.2% |
| `attack_duration_efficiency` | 156 ms | 0.2% |
| `wall_gaps` | 155 ms | 0.2% |
| `big_chance_feeder_roles` | 154 ms | 0.2% |
| `press_after_goal` | 144 ms | 0.2% |
| `figure_vs_formation` | 144 ms | 0.2% |
| `side_switching` | 143 ms | 0.2% |
| `setplay_by_score` | 140 ms | 0.2% |

## Olvasat

A réteg-csomag ideje a kocka-számmal nő: a lassú rétegek a
kockánként dolgozó alap-mérések (lövés-felismerés, poszt-becslés,
formáció), amelyeket a `primitive_cache` hatókör meccsenként
egyszer számol — a csomagban tehát a fenti összeg a felső
korlát, a megosztott mérések miatt a valóság kevesebb. Ha egy
réteg a csomag több mint 10%-át viszi, az a gyorsítás első
jelöltje (gyorsítótárazott alap-mérés, időablakos számolás).

