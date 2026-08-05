# Sorrend-függés — mely rétegre hat a kapus-jelölés

*Generált fájl — ne kézzel szerkeszd. Frissítés:*
`cd backend && python -m scripts.order_sensitivity`

A `detect_goalkeepers` beleír a meccsbe (`role = "kapus"`), és
több réteg a szerepből dolgozik. Az alábbi rétegek eredménye
ezért ATTÓL FÜGG, megtörtént-e már a kapus-jelölés, amikor
lefutnak — egy nagy összeállításban tehát a kiértékelés
sorrendjétől. Ez a lista a döntés alapja: hol érdemes kimondott,
determinisztikus szerep-jelöléssel indítani.

Mérés: 240 mp-es szimulált meccs (mag: 7); **313 réteg** összevetve, ebből **50 sorrend-függő**.

## A mérés köre

A szimuláció ebben a futásban LŐ is (6
lövés/perc, a hazai mezőnyjátékosok körbejárva), tehát a
lövés-alapú rétegek valódi bemenetet kaptak. A szimuláció
alapértelmezésben csak mozgást modellez — enélkül ezek a
rétegek üres bemeneten futnának, és a mérés róluk nem
mondana semmit.

## Sorrend-függő rétegek

| Réteg |
|---|
| `advanced_defender` |
| `ball_winners` |
| `beaten_defenders` |
| `block_recoveries` |
| `blocked_by_role` |
| `blocked_shooters` |
| `blocked_shot_rate` |
| `blocks` |
| `clutch_ball_hogs` |
| `clutch_lineup` |
| `coach_summary` |
| `corridor_goals` |
| `defensive_aggression` |
| `defensive_line_height` |
| `distance_battle` |
| `double_punishment` |
| `doubling_defenders` |
| `gk_positioning` |
| `gk_shorthanded_saves` |
| `key_moments` |
| `key_players` |
| `line_height_by_score` |
| `marking` |
| `match_card_en` |
| `momentum` |
| `opening_lineup` |
| `pass_security` |
| `phase_specialists` |
| `pivot_guards` |
| `post_powerplay` |
| `powerplay_defense` |
| `powerplay_pace` |
| `powerplay_shooters` |
| `pressure_sensitive_players` |
| `recovery_discipline` |
| `rotation` |
| `rules` |
| `shorthanded_attack` |
| `sprint_threats` |
| `steal_launch` |
| `steal_types` |
| `susp_earner_roles` |
| `susp_earners` |
| `suspensions_by_score` |
| `targeted_defenders` |
| `training` |
| `transition_offense` |
| `unpressured_assists` |
| `wall_gaps` |
| `wrongfooted_keeper` |
