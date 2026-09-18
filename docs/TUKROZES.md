# Tükrözés-őr — helyesen fordul-e meg a bal és a jobb

*Generált fájl — ne kézzel szerkeszd. Frissítés:*
`cd backend && python -m scripts.mirror_sides`

A pálya hossztengelyére tükrözött meccsen (y → 20 − y) minden
oldal-megnevezésnek meg kell fordulnia. Ami nem fordul meg, az
a nyers koordinátából nevez oldalt — és a két csapat közül az
egyikről FORDÍTVA állít (szemben állnak).

Mérés: 120 mp-es szimulált meccs (mag: 7); **11 oldal-címkés réteg** vizsgálva, ebből **0 hibás**.

## Nyelvi megjegyzés

Magyarul a *jobb* nem csak oldal, hanem *better* is („jobb
szabad helyzet volt"). Az őr ezért CSAK a pontos oldal-címkéket
cseréli (dict-kulcs vagy önálló címke-érték), a mondatokat soha;
a próza-gyártó összegző rétegek kimaradnak a mérésből.

## Hibás réteg: nincs

Minden oldal-címkés réteg helyesen tükröződik.

## Vizsgált rétegek

- `attack_side_shift`
- `attack_sides`
- `defensive_gaps`
- `gk_saves_by_hand`
- `gk_seven_directions`
- `gk_weak_side`
- `goal_placement`
- `role_goal_placement`
- `seven_shot_directions`
- `shooter_placement`
- `wing_finishing_by_side`

## Kihagyva (próza-gyártó összegzők)

- `coach_summary`
- `counter_plan`
- `priority_findings`
- `training`
