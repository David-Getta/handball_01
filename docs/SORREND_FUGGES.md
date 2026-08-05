# Sorrend-függés — mely rétegre hat a kapus-jelölés

*Generált fájl — ne kézzel szerkeszd. Frissítés:*
`cd backend && python -m scripts.order_sensitivity`

A `detect_goalkeepers` beleír a meccsbe (`role = "kapus"`), és
több réteg a szerepből dolgozik. Az alábbi rétegek eredménye
ezért ATTÓL FÜGG, megtörtént-e már a kapus-jelölés, amikor
lefutnak — egy nagy összeállításban tehát a kiértékelés
sorrendjétől. Ez a lista a döntés alapja: hol érdemes kimondott,
determinisztikus szerep-jelöléssel indítani.

Mérés: 240 mp-es szimulált meccs (mag: 7); **313 réteg** összevetve, ebből **38 sorrend-függő**.

## A mérés korlátja

A szimulált meccs (`simulate_ground_truth`) MOZGÁST modellez,
lövés-eseményt nem termel — a szimulált lövések a demó-epizódokból
jönnek, amelyeket ez a mérés nem használ. Ezért a LÖVÉS-ALAPÚ
rétegek itt üres bemenettel futnak: mindkét ágon ugyanazt a
semmit adják, tehát "nem sorrend-függőnek" látszanak. Ez nem
bizonyíték — csak annyit jelent, hogy ezekről a rétegekről a
mérés NEM MOND SEMMIT. Valós (vagy lövéseket is tartalmazó)
felvételen újra kell mérni.

## Sorrend-függő rétegek

| Réteg |
|---|
| `advanced_defender` |
| `block_recoveries` |
| `blocked_by_role` |
| `blocked_shooters` |
| `blocked_shot_rate` |
| `blocks` |
| `clutch_lineup` |
| `coach_summary` |
| `defensive_aggression` |
| `defensive_line_height` |
| `distance_battle` |
| `double_punishment` |
| `doubling_defenders` |
| `gk_positioning` |
| `key_moments` |
| `key_players` |
| `line_height_by_score` |
| `marking` |
| `match_card_en` |
| `opening_lineup` |
| `pass_security` |
| `phase_specialists` |
| `pivot_guards` |
| `post_powerplay` |
| `powerplay_defense` |
| `powerplay_pace` |
| `pressure_sensitive_players` |
| `priority_findings` |
| `recovery_discipline` |
| `rotation` |
| `rules` |
| `shorthanded_attack` |
| `sprint_threats` |
| `susp_earner_roles` |
| `susp_earners` |
| `suspensions_by_score` |
| `training` |
| `wall_gaps` |
