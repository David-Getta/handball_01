# Sebesség-profil — a réteg-csomag ideje egy teljes meccsen

*Generált fájl — ne kézzel szerkeszd. Frissítés:*
`cd backend && python -m scripts.speed_profile`

A kész termék sebesség-célja (`docs/ROADMAP.md`, "Sebesség-cél"):
egy 60 perces meccs TELJES elemzése ≤ 15 perc
a pilot GPU-s szerverén, a gyors kép ≤ 3 perc.
Ez a lap a RÉTEG-részt méri (kész követésből a 500+ elemző réteg),
amelyre a keret ≤ 5 perc CPU-n — a többi a
felismerésé, azt a pilot valódi felvételen méri.

Mérés: 3600 mp-es szimulált meccs, 8.33 fps (a termék ritkítása), 30000 kocka; verzió v0.1.194+818e97d8; gép: arm, 10 mag, Python 3.12.16.

- **Rétegek összesen: 23,0 mp** (521 réteg, átlag 44 ms) — ítélet: **MEGFELEL**
- Gyors kép (coach_summary, xg, defense, training_focus): 19,4 mp
- Szimuláció (nem a termék része): 336 ms

## A 15 leglassabb réteg

| Réteg | Idő | A csomag %-a |
|---|---|---|
| `coach_summary` | 19,4 mp | 84.6% |
| `intensity_trend` | 213 ms | 0.9% |
| `advanced_defender_roles` | 99 ms | 0.4% |
| `advanced_defender` | 70 ms | 0.3% |
| `clutch_defense_shape` | 67 ms | 0.3% |
| `figure_vs_formation` | 64 ms | 0.3% |
| `line_height_by_score` | 64 ms | 0.3% |
| `setplay_by_score` | 63 ms | 0.3% |
| `setplay_shapes` | 62 ms | 0.3% |
| `press_after_goal` | 62 ms | 0.3% |
| `clutch_setplay` | 62 ms | 0.3% |
| `defense_shapes` | 61 ms | 0.3% |
| `attack_duration_efficiency` | 52 ms | 0.2% |
| `setplay_repeat_choice` | 52 ms | 0.2% |
| `setplay_decay` | 52 ms | 0.2% |

## Olvasat

A réteg-csomag ideje a kocka-számmal nő: a lassú rétegek a
kockánként dolgozó alap-mérések (lövés-felismerés, poszt-becslés,
formáció), amelyeket a `primitive_cache` hatókör meccsenként
egyszer számol — a csomagban tehát a fenti összeg a felső
korlát, a megosztott mérések miatt a valóság kevesebb. Ha egy
réteg a csomag több mint 10%-át viszi, az a gyorsítás első
jelöltje (gyorsítótárazott alap-mérés, időablakos számolás).

