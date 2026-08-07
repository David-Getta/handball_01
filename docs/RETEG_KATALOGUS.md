# Réteg-katalógus — a meccs-csomag regisztrált elemző rétegei

*Generált fájl — ne kézzel szerkeszd. Frissítés:*
`cd backend && python -m scripts.layer_catalog`

Összesen **326 réteg**, modulonként csoportosítva; a
leírás a réteg-függvény docstringjének első sora.

## attack_types (70)

| Réteg | Mit mér |
|---|---|
| `assist_concentration` | Előkészítő-függés: mennyire egy emberre épül a gólpassz-termelés. |
| `assist_fade` | Gólpassz-esés: MEGÁLL-E A LABDA a hajrára. |
| `assist_reliance` | Asszist-függés: a gólok mekkora része előkészített (gólpasszos). |
| `assist_sources` | Gólpassz-forrás: honnan készítik elő a gólokat — szélről (beadás), |
| `attack_depth` | Támadás-mélység: MILYEN MESSZE állnak a kaputól felállt |
| `attack_duration_efficiency` | Befejezés-hatékonyság a támadás HOSSZA szerint. |
| `attack_efficiency` | Támadás-típusonkénti befejezés-hatékonyság csapatonként. |
| `attack_headcount` | Felfutási létszám: HÁNY EMBERREL támadnak. |
| `attack_mix_shift` | Szünet-váltás: ÁTRENDEZIK-E a támadójátékot a szünet után. |
| `attack_origins` | Honnan indulnak a támadások: középkezdésből (kapott gól után), |
| `attack_outcomes` | Támadás-kimenetel: MIVEL zárulnak a támadásaik. |
| `attack_rhythm` | Ritmus-egyhangúság: mennyire egyforma hosszúak a támadások. |
| `attack_side_bias` | Oldal-részrehajlás: a lövések a támadás melyik oldaláról jönnek. |
| `attack_starters` | Támadás-indítók: KI hozza fel a labdát. |
| `attack_vs_wall_height` | Fal-magasság elleni játék: MEGBÜNTETIK-E A FELFUTÓ FALAT. |
| `attack_width` | Támadás-szélesség: mennyire húzza szét a csapat a pályát. |
| `balls_out` | Kidobott labda: hányszor hagyja el a labda a pályát az OLDALVONALON. |
| `break_share_fade` | Kontra-esés: MELYIK FÉLIDŐBEN kontráznak. |
| `break_sources` | Kontra-forrás: MIBŐL INDUL a lerohanásuk. |
| `breaks_by_score` | Kontra-állás: MIKOR futják a lerohanásaikat — állás szerint. |
| `breakthrough_players` | Áttörő játékosok: KI JUT BE labdával a falba. |
| `buildup_side` | Kihozatal-oldal: MELYIK OLDALON indítják a támadást. |
| `buildup_time` | Felhozatal-idő: MENNYI IDŐ ALATT érnek a támadó térfélre. |
| `circulation_direction` | Labda-forgatás iránya: MERRE JÁRATJÁK a labdát felállt támadásban. |
| `crossing_runs` | Keresztjáték: MENNYIT KERESZTEZNEK a hátsó sorban. |
| `double_pivot_usage` | Két beállós játék: MENNYIT JÁTSZANAK két emberrel a 6 m-en. |
| `fast_break_conversion` | Lerohanás-hatékonyság: MENNYI LESZ GÓL a kontráikból. |
| `fast_break_finishers` | Ki fejezi be a lerohanásokat: a lerohanás-szakaszokra eső gólok |
| `fast_break_headstart` | Kontra-elszökés: ELŐRE SZÖKÖTT emberrel kontráznak-e. |
| `fast_break_support` | Kontra-kíséret: HÁNYAN FUTNAK FEL a lerohanásaiknál. |
| `fast_break_waves` | Kontra-hullámok: az ELSŐ EMBER vagy a MÁSODIK HULLÁM fejezi be |
| `goal_buildup` | Gól-előkészítés hossza: direkt vagy kombinatív gólokból élnek. |
| `goal_placement` | Kapu-sarok: a gólok a kapu MELYIK oldalára mennek (bal/közép/jobb), |
| `kickout_targets` | Kiosztás-célpont: HOVÁ megy a labda, ha a betörés nem lövéssel zárul. |
| `long_attack_outcomes` | Kivárás-csapda: MI LESZ A HOSSZÚ TÁMADÁSAIKBÓL. |
| `overload_finishing` | Fölény-befejezés: fölényben vagy felállt fal ellen szereznek gólt. |
| `pace` | Meccs-tempó: hány támadás jut egy percre. |
| `pace_by_score` | Támadás-hossz állás szerint: mit csinál a csapat előnyben és |
| `pass_chains` | Passz-lánc: támadásonként hány passz előzi meg a befejezést, és |
| `pass_direction` | Passz-irány: mennyire viszik ELŐRE a labdát (vertikális, penetráló |
| `pass_direction_by_score` | Passz-irány-állás: MERRE jár a labda előnyben és hátrányban. |
| `pass_risk` | Passz-kockázat: a hosszú passzok eladás-aránya a rövidekhez |
| `pivot_feeders` | Beálló-kiszolgálók: KI adja be a labdát a beállónak. |
| `pivot_service` | Beálló-futtatás: MOZGÁSBÓL vagy ÁLLVA kapja-e a beálló a labdát. |
| `pivot_side` | Beálló-oldal: MELYIK OLDALON dolgozik a beállójuk. |
| `pivot_usage` | Beálló-terhelés: a támadások mekkora része megy át a beállón, és |
| `pullback_rate` | Visszahozott támadások: LEZÁRJÁK vagy ÚJRAJÁRATJÁK a betörést. |
| `rebound_winners` | Lepattanó-szerzők: KI NYERI a kipattanókat. |
| `risky_passers` | Kockázatos passzolók: KINEK a hosszú labdái foghatók el. |
| `screen_pairs` | Elzárás-páros: KI ZÁR KINEK — a bejáratott elzáró-lövő kettős. |
| `screen_setters` | Elzárók: KI ÁLL ELZÁRÁSBA a lövőik előtt. |
| `screen_usage` | Elzárás-használat: elzárásból lőnek, vagy tisztán, 1v1-ből. |
| `second_chance` | Második roham / lepattanó-visszaszerzés: a saját, gólt NEM érő lövés |
| `second_chance_fade` | Lepattanó-esés: MELYIK FÉLIDŐBEN él a második roham. |
| `second_chance_roles` | Lepattanó-poszt: KI LŐ MÁSODSZOR — melyik posztjuk viszi a |
| `shooter_placement` | Lövő-kapuoldal: ki melyik sarokba lő. |
| `shooter_ranges` | Lövő-távolság profil: KI LŐ TÁVOLRÓL és ki közelről. |
| `shot_distance_fade` | Lövés-távolság esése: KIFELÉ SZORULNAK-E a hajrára. |
| `shot_ranges` | Lövés-távolság profil: honnan lő és honnan szerez gólt a csapat. |
| `shot_timing` | Lövés-időzítés: MIKOR lőnek a támadáson belül — első hullámban |
| `side_switching` | Oldalváltás: széthúzzák-e a falat gyors keresztpasszokkal. |
| `team_pace_fade` | Tempó-esés: a csapat támadás/perc mutatója az 1. vs 2. félidőben. |
| `transition_offense` | Átmenet-támadás: a labdaszerzésből mennyi gyors gól születik. |
| `turnovers_by_score` | Hiba-állás: HÁTRÁNYBAN SZÓRJÁK-E a labdát. |
| `width_by_score` | Szorult játék: HÁTRÁNYBAN mennyire húzzák szét a pályát. |
| `wing_finishing` | Szélső-befejezés: a szélső (éles) szögből, közelről leadott lövések |
| `wing_finishing_by_side` | Szélső-befejezés oldalanként: MELYIK szélsőjük veszélyes. |
| `wing_involvement` | Szélső-bevonás: ELJUT-E a labda a szélre a támadásaikban. |
| `wing_service` | Szélső-futtatás: LENDÜLETBŐL vagy ÁLLVA kapják-e a szélsők a |
| `wing_shot_depth` | Szélső-mélység: MILYEN MÉLYRŐL lőnek a szélsőik. |

## coach_summary (1)

| Réteg | Mit mér |
|---|---|
| `coach_summary` | A meccs automatikus edzői összefoglalója. |

## decisions (6)

| Réteg | Mit mér |
|---|---|
| `hold_time_players` | Labdatartás-idő: KI meddig tartja magánál a labdát. |
| `pass_security` | Pressz-tűrés: labdabiztonság testközeli védő mellett vs szabadon. |
| `pass_speed` | Passz-sebesség: ÉLES vagy LÁGY a labdajáratásuk. |
| `pressure_sensitive_players` | Pressz-érzékeny játékosok: KI VESZÍTI EL a labdát szorításban. |
| `shot_choice_quality` | Lövésválasztás: LŐNEK-E, AMIKOR JOBB HELYZET VAN a pályán. |
| `support_distance` | Támogatás-távolság (izoláció-jel): milyen messze van a labdás |

## defense (57)

| Réteg | Mit mér |
|---|---|
| `advanced_defender` | Kilépő védő: VAN-E ELŐRETOLT EMBERÜK a falban, és ki az. |
| `ball_winners` | Labdaszerzők: birtokos-váltásnál (csapatváltás) az ÚJ birtokos |
| `beaten_defenders` | Átvert védők: KI MÖGÖTT esnek a kapott gólok. |
| `block_recoveries` | Blokk-lepattanó: A BLOKK UTÁN ki szerzi meg a labdát. |
| `blocked_by_role` | Falba lövő posztok: MELYIK POSZTJUK lő rendre a falba. |
| `blocked_shooters` | Lefogott lövők: KINEK A LÖVÉSÉT viszi el rendre a fal. |
| `blocked_shot_rate` | Falba lövés (támadó-oldali blokk-arány): a csapat lövés-kísérleteinek |
| `blocks` | Blokkolt lövések: a mezőnyvédőn elakadó lövés felismerése. |
| `breakthroughs` | Betörés-folyosók: támadásonként hol lép be a labdás ember a |
| `conceded_by_attack_type` | Kapott gólok támadás-típus szerint: MILYEN TÁMADÁSBÓL kapják a |
| `conceded_by_role` | Kapott gólok posztonként: MELYIK POSZT ELLEN szivárognak. |
| `conceded_momentum` | Lendület-gólok: MOZGÁSBÓL ÉRKEZŐ lövőktől kapják-e a gólokat. |
| `conceded_side_bias` | Engedett-oldal: a fal melyik oldala felől jönnek a lövések. |
| `conceded_tempo` | Bontó tempó: A JÁRATÁS SZEDI-E SZÉT a védekezésüket. |
| `corridor_goals` | Folyosó-gólok: NYITOTT FOLYOSÓN kapják-e a gólokat. |
| `costly_turnover_players` | Drága eladók: kinek az eladásai kerülnek gólba. |
| `counter_press` | Ellen-press: az eladott labdát azonnal visszaszerzik-e. |
| `covered_shooters` | Fedezetten lövők: KI HÚZZA EL a ravaszt nyomás alatt is. |
| `defense` | Mindkét csapat VÉDEKEZÉSÉNEK képe a kapott lövésekből. |
| `defense_setup_time` | Falépítés-idő: MENNYI IDŐ ALATT ÁLL FEL a faluk. |
| `defensive_aggression` | Védekezés-keménység: MENNYI BÜNTETÉST hoz a faluk. |
| `defensive_line_height` | Védekezési vonal magassága: milyen mélyen vagy magasan áll a fal. |
| `defensive_shift_lag` | Fal-csúszás késése: MILYEN GYORSAN igazodik a faluk az |
| `defensive_width` | Védelmi tömörség (fal-szélesség): milyen szélesen áll a védőfal. |
| `double_punishment` | Kettőzés-büntetés: MÖGÉ BETALÁLNAK-E a kettőzésüknek. |
| `double_teams` | Kettőzés: rálép-e a második védő is a labdásra. |
| `doubling_defenders` | Kettőző emberek: KI JÖN MÁSODIKNAK a labdásra. |
| `fading_defenders` | Eltűnő védő: KI viszi a védekezést az első félidőben — és áll le. |
| `high_steal_players` | Elöl szerző védők: KI SZED LABDÁT a támadó térfélen. |
| `line_height_by_score` | Védekezési mélység állás szerint: ELŐNYBEN vagy HÁTRÁNYBAN |
| `marking` | Őrzési párok: ki kit fogott a védekezésben. |
| `pivot_defense` | Beálló-védekezés: mennyire bírja a fal az ellenfél beállóját. |
| `pivot_guards` | Beálló-őr: KI ŐRZI az ellenfél beállóját. |
| `press_after_goal` | Gól utáni letámadás: SAJÁT GÓL UTÁN feljebb megy-e a fal. |
| `pressure_fade` | Védekezés-fellazulás: a védekezési nyomás változása az 1. és a 2. |
| `pressure_finishing` | Nyomás alatti befejezés: szabad vs fedezett lövések gólaránya. |
| `recovery` | Visszarendeződés-idő: labdavesztés után mennyi idő alatt ér |
| `recovery_discipline` | Visszaérés-fegyelem: KI nem fut vissza védekezni. |
| `role_block_sources` | Blokk-poszt: MELYIK POSZTJUK BLOKKOL. |
| `role_steal_sources` | Labdaszerző-poszt: MELYIK POSZTJUK NYERI a labdákat. |
| `screen_defense` | Elzárás-védekezés: bírja-e a fal az ellenfél elzárásait. |
| `second_chance_allowed` | Lepattanó-fal: hány második rohamot enged a védekezés. |
| `steal_height` | Labdaszerzés-magasság (letámadás-jel): HOL szerez labdát a csapat. |
| `steal_launch` | Szerzés utáni indítás: AZONNAL ELŐRE megy-e a szerzett labda. |
| `steal_types` | Labdaszerzés-típus: ELFOGJÁK vagy LESZERELIK a labdát. |
| `stepout_punishment` | Kilépés-büntetés: A KILÉPÉSÜK MÖGÉ betalálnak-e. |
| `targeted_defenders` | Célba vett védő: KIRE lőnek, és kinél lesz belőle gól. |
| `turnover_clusters` | Hiba-sorozatok: EGYMÁS UTÁN jönnek-e az eladott labdák. |
| `turnover_fade` | Labdabiztonság-esés: az eladás-ütem változása az 1. és a 2. félidő |
| `turnover_players` | Labdaeladók: KI veszíti el a legtöbbször a labdát — a labdabiztonság |
| `turnover_punishment` | Eladás-büntetés: az eladott labda fél percen belül gólba kerül-e. |
| `turnover_timing` | Eladás-időzítés: a birtoklás hányadik másodpercében jön az eladás. |
| `turnover_zones` | Hol veszíti el a labdát egy csapat — pálya-harmad szerint. |
| `unpressured_assists` | Zavartalan előkészítők: HAGYJÁK-E DOLGOZNI a gólpassz-adót. |
| `wall_gaps` | Fal-rés: mekkora réseket hagy a rendezett védőfal. |
| `wing_closeouts` | Szélső-kifutás: IDŐBEN ÉRNEK-E KI a szélső lövéseire. |
| `wing_defense` | Szélső-védekezés: bírja-e a fal a szélső lövéseket. |

## event_detection (10)

| Réteg | Mit mér |
|---|---|
| `assist_network` | Gólpassz-hálózat: ki kinek készíti elő a gólokat. |
| `assist_ranges` | Gólpassz-hossz: HOSSZÚ INDÍTÁSOKBÓL vagy RÖVID KOMBINÁCIÓKBÓL |
| `assist_zones` | Gólpassz-zónák: HONNAN érkezik a gólpassz — edzői ítélettel. |
| `goal_concentration` | Gól-koncentráció (gólfüggés): mennyire épül EGY emberre a csapat |
| `pass_length` | Passz-hossz profil: rövid kombinációs vagy hosszú, direkt passzjáték. |
| `pass_length_by_score` | Passz-hossz-állás: MIKOR váltanak hosszú labdákra. |
| `pass_network` | Passz-hálózat: ki kinek adogat — a játékszervezés fő tengelye. |
| `shooter_power` | Lövő-erő: kinek a legkeményebb a lövése. |
| `shot_speed_fade` | Lövőerő-esés: a lövés-sebesség változása az 1. és a 2. félidő között — |
| `shot_speeds` | Lövés-sebességek a labda-kinematikából. |

## goalkeeper (33)

| Réteg | Mit mér |
|---|---|
| `empty_net_by_score` | 7a6-állás: MILYEN ÁLLÁSNÁL vállalják az üres kaput. |
| `empty_net_context` | A 7 a 6 szakaszok játékhelyzete: állásból és időből mikor húzzák |
| `empty_net_goals` | Üres kapura kapott gólok: a 7 a 6 (lehozott kapus) ára. |
| `gk_assists` | Kapus-gólpassz: hány gól indul KÖZVETLENÜL a kapus kezéből. |
| `gk_break_response` | Lerohanás-védés: hogy véd a kapus gyorsindítás ellen. |
| `gk_change_effect` | Kapuscsere-hatás: segített-e a kapuscsere. |
| `gk_cold_streaks` | Kapus-hidegedés: HIDEG KÉZZEL beesik-e a védése. |
| `gk_early_saves` | Kapus-bemelegedés: HOGYAN VÉD a meccs első tíz percében. |
| `gk_free_shot_saves` | Kapus szabad lövés ellen: a fal segítsége nélkül is véd-e. |
| `gk_goal_threat` | Kapus-gól veszély: RÁDOB-E A KAPUSUK az üres kapura. |
| `gk_outlet_length` | Kapus-indítás hossza: hosszú indítós vagy rövid kihozós a kapus. |
| `gk_outlet_security` | Indítás-biztonság: a kapus-indítás kihez jut el először. |
| `gk_outlet_side` | Kapus-indítás iránya: melyik oldalra nyit a kapus. |
| `gk_positioning` | Kapus-kimozdulás: milyen mélyen áll a kapus a kapuja előtt. |
| `gk_rebound_control` | Kapus-kipattanó: FOGJA vagy KIÜTI a labdát a kapusuk. |
| `gk_save_fade` | Kapus-forma félidőnként: a védés-hatékonyság változása az 1. és a |
| `gk_save_ranges` | Kapus védés-hatékonyság lövés-távolság szerint: melyik távolságból |
| `gk_save_streaks` | Kapus-sorozat: ha rákap, SOROZATBAN véd-e a kapus. |
| `gk_saves_by_role` | Kapus-védés posztonként: MELYIK POSZT lövéseit fogja a kapusuk. |
| `gk_saves_by_score` | Kapus állás szerint: HÁTRÁNYBAN FELJAVUL vagy ÖSSZEESIK-E. |
| `gk_saves_by_speed` | Kapus-védés lövés-sebesség szerint: a BOMBÁKAT vagy a HELYEZETT |
| `gk_shorthanded_saves` | Kapus emberhátrányban: NŐ-E a kapusuk a két perc alatt. |
| `gk_timeline` | Ki védett mikor — kapus-szolgálatok és cserék csapatonként. |
| `gk_weak_side` | Kapus-gyengeoldal: a kapu melyik oldalára kap gólt a csapat. |
| `keeper_involvement` | Kapus-bevonás: MENNYIRE JÁTSZANAK VISSZA a kapusnak. |
| `outlet_pace_by_score` | Indítás-állás: VEZETVE LASSÍTJÁK-E a kapus-indítást. |
| `outlet_punishment` | Indítás-hiba ára: GÓLBA KERÜLNEK-E az elszórt indításaik. |
| `outlet_target_roles` | Felhozatal-posztok: MELYIK POSZTRA hozzák fel a labdát. |
| `outlets` | Kapus-indítás: védés után mennyi idő alatt ér a labda a felezőig |
| `reading_keeper` | Olvasó kapus: ELŐRE OLVASSA-E a lövéseket a kapusuk. |
| `seven_keeper_swaps` | Hetesre cserélt kapus: HOZNAK-E SPECIALISTÁT a büntetőkre. |
| `seven_six_finisher_roles` | 7a6-befejező poszt: KIRE FUT KI a hetedik ember játéka. |
| `wrongfooted_keeper` | Becsapott kapus: ELMOZDÍTJÁK-E a kapusukat a gólok előtt. |

## halftime (2)

| Réteg | Mit mér |
|---|---|
| `first_half_close` | A félidő-zárás mérlege: ki üt utoljára a szünet előtt. |
| `second_half_start` | A szünet utáni kezdés mérlege: ki üt először a 2. félidőben. |

## momentum (35)

| Réteg | Mit mér |
|---|---|
| `bench_scoring` | Pad-gólok: A KISPAD IS TERMEL-E, vagy csak a kezdők. |
| `black_window` | Fekete ötperc: a meccs MELYIK ÖT PERCE süllyed el. |
| `close_game_record` | Szoros meccs-mérleg: hogyan végződött az 1-2 gólos meccs. |
| `closing_attacks` | Félidő-zárás: MIT KEZDENEK AZ UTOLSÓ LABDÁVAL. |
| `clutch` | Hajrá-teljesítmény: ki bírja jobban a meccs végét. |
| `clutch_ball_hogs` | Hajrá-labdabirtoklás: EGY KÉZBEN VAN-E a végjátékuk. |
| `clutch_lineup` | Hajrá-ötös: KIK VANNAK A PÁLYÁN a döntő szakaszban. |
| `clutch_scorers` | Hajrá-emberek: KI szerzi a gólokat a meccs utolsó CLUTCH_WINDOW_S |
| `clutch_shot_quality` | Hajrá-lövésválasztás: milyen helyzetekből lőnek a meccs végén. |
| `clutch_turnover_players` | Hajrá-hibázók: KI ADJA EL a labdát a döntő szakaszban. |
| `clutch_turnovers` | Hajrá-eladás: nyomás alatt megőrzik-e a labdát. |
| `comeback_carriers` | Felzárkózás-húzó: KIN keresztül jönnek vissza hátrányból. |
| `drought_anatomy` | Gólcsend-anatómia: a leghosszabb gólcsend alatt lőtt-e a csapat. |
| `drought_breakers` | Csend-törők: KI DOBJA a gólcsendet megtörő gólt. |
| `droughts` | Gólcsend: a leghosszabb saját gól nélküli időszak csapatonként. |
| `fading_scorers` | Eltűnő ember: KI él az első félidőben, és tűnik el a másodikra. |
| `half_openings` | Félidő-nyitás: HOGYAN INDULNAK a két félidő első 5 percében. |
| `halftime` | Félidei állás a felismert gólokból és a félidő-határból. |
| `halftime_comeback` | Félidei hátrányból fordítás: a félidei állás vs a végeredmény. |
| `hot_hands` | Forró kéz: VAN-E SOROZATLÖVŐJÜK, aki egymás után dobja a gólokat. |
| `key_moments` | A meccs gerince: kulcs-pillanatok egyetlen, időrendi listában. |
| `lead_protection` | Előny-őrzés: a meccs közbeni legnagyobb vezetés vs a végeredmény. |
| `momentum` | A gól-sorozatok LEHETSÉGES OKAI — az edzői "miért" réteg. |
| `opening` | Kezdés-profil: ki szerzi a meccs ELSŐ gólját, és milyen a korai állás. |
| `opening_lineup` | Kezdő hatos: KIKKEL KEZDENEK. |
| `parity_breaks` | Holtpont-mérleg: döntetlen állásról ki lép el góllal. |
| `post_goal_lapses` | Gól utáni elalvás: a saját gól után azonnal visszakapott gólok. |
| `progression` | Vezetés-alakulás: az állás menete a felismert gólokból. |
| `punished_misses` | Kihagyás-büntetés: MEGBÜNTETIK-E a kihagyott ziccereiket. |
| `quarter_profile` | Negyedóra-profil: MELYIK MECCS-SZAKASZ AZ ÖVÉK az óra szerint. |
| `responses` | Válasz-gólok: milyen gyorsan felel egy csapat a kapott gólra. |
| `restart_speed` | Középkezdés-tempó: kapott gól után mennyi idő alatt ér át a |
| `restart_targets` | Középkezdés-átvevő: KINÉL indul újra a játék a kapott gól után. |
| `run_containment` | Sorozat-törés: az ellenfél sorozatait ki meddig hagyja elfutni. |
| `win_prob` | Meccs-esély görbe: P(hazai győzelem) a felismert gólok mentén. |

## playmaker (1)

| Réteg | Mit mér |
|---|---|
| `playmaker` | Mindkét csapat irányító-függése. |

## priorities (1)

| Réteg | Mit mér |
|---|---|
| `priority_findings` | Teendő-rangsor: a megszólaló ítéletek fontossági sorrendben. |

## quality (1)

| Réteg | Mit mér |
|---|---|
| `confidence` | Réteg-megbízhatóság: mely elemzési rétegeknek van elég mintája |

## roles (22)

| Réteg | Mit mér |
|---|---|
| `assist_role_pairs` | Gólpassz-tengelyek poszt szerint: MELYIK VONALON esnek a góljaik. |
| `assists_by_role` | Gólpassz-posztok: MELYIK POSZTJUK készíti elő a góljaikat. |
| `goals_by_role` | Poszt szerinti gólmegoszlás: MELYIK POSZTRÓL jönnek a góljaik. |
| `phase_specialists` | Egyirányú játékosok: KI JÁTSZIK CSAK VÉDEKEZNI vagy CSAK TÁMADNI. |
| `positions` | Poszt-becslés a támadó-fázis átlag-pozícióiból. |
| `role_assist_sources` | Gólpassz-poszt: MELYIK POSZTJUK KEZÉBŐL indulnak a góljaik. |
| `role_fast_breaks` | Kontra-poszt: MELYIK POSZTJUK FUT KI a lerohanásokon. |
| `role_goal_placement` | Poszt-kapuoldal: MELYIK POSZTJUK MELYIK SARKOT keresi. |
| `role_hold_time` | Poszt-labdatartás: MELYIK POSZTNÁL áll meg a labda. |
| `role_pass_map` | Poszt-passzháló: MELYIK VONALON jár a labda a támadásaikban. |
| `role_possession_share` | Poszt-birtoklás: MELYIK POSZTNÁL van a labda a szervezett |
| `role_pressure_finish` | Poszt-nyomás: MELYIK POSZTJUK FEJEZ BE FEDEZETTEN IS. |
| `role_receive_zones` | Poszt-átvételi zóna: MILYEN MESSZE a kaputól veszi át a labdát |
| `role_share_by_score` | Poszt-állás: MELYIK POSZTON keresztül fejeznek be HÁTRÁNYBAN. |
| `role_share_shift` | Poszt-váltás a szünetre: MELYIK POSZTRA épül a befejezésük a |
| `role_shot_distance` | Poszt-lövéstávolság: MELYIK POSZTJUK MILYEN MESSZIRŐL lő. |
| `role_shot_power` | Poszt-lövéserő: MELYIK POSZTJUK LŐ KEMÉNYEN. |
| `role_shot_timing` | Poszt-lövésidőzítés: MELYIK POSZTJUK MIKOR fejez be a támadáson |
| `role_turnover_cost` | Eladás-ár poszt szerint: MELYIK POSZTJUK eladása kerül gólba. |
| `role_turnover_zones` | Poszt-eladási zóna: MELYIK POSZTJUK adja el a labdát a TÁMADÓ |
| `shot_efficiency_by_role` | Poszt szerinti befejezés-hatékonyság: MELYIK POSZTRÓL ÉRDEMES |
| `turnovers_by_role` | Poszt-hibák: MELYIK POSZTJUK veszíti el a labdát. |

## rules (24)

| Réteg | Mit mér |
|---|---|
| `discipline_fade` | Fegyelem-esés: a kiállítások félidőnkénti eloszlása — a fáradás-kép |
| `double_shorthand` | Kettős emberhátrány: MIT KEZD a csapat négy mezőnyjátékossal. |
| `excess_players` | Létszám-hiba: mikor van HETEDIK mezőnyjátékos a pályán. |
| `gk_seven_directions` | Kapus-hetesvédés irány szerint: MELYIK SAROKBA menő heteseket |
| `post_powerplay` | Visszaállás: MI TÖRTÉNIK, AMIKOR VISSZAÉR a kiállított ember. |
| `post_seven_lapses` | Hetes utáni percek: LERAGADNAK-E az adott hetes után. |
| `powerplay_defense` | Emberelőny-védekezés: emberelőnyben is kapnak-e gólt. |
| `powerplay_pace` | Emberelőny-tempó: ELNYÚJTJÁK vagy KAPKODJÁK az emberelőnyt. |
| `powerplay_shooters` | Emberelőny-lövők: KI FEJEZ BE a két perc alatt. |
| `rules` | A szabály-értő réteg összegzése egy hívásban (az API-nak). |
| `seven_conceder_roles` | Hetes-okozó poszt: MELYIK SÁVJUK szakad be hetessel. |
| `seven_earner_roles` | Hetes-kiharcolás poszt szerint: MELYIK POSZTRÓL rántják le őket. |
| `seven_earners` | Ki harcolja ki a hétméterseket: a hetes-jel előtt a támadott |
| `seven_meter_conceders` | Hetes-okozó védők: KINÉL szakad meg a védekezés hetessel. |
| `seven_meter_defense` | Hetes-védés: a kapus mérlege a RÁ dobott hetesekből. |
| `seven_shot_directions` | Hetes-oldal: MERRE DOBJÁK a heteseiket. |
| `sevens_by_score` | Hetes-állás: MIKOR harcolják ki a heteseiket — állás szerint. |
| `sevens_fade` | Hetes-fáradás: MIKOR ADJÁK a heteseket. |
| `shorthanded_attack` | Hátrány-támadás: mit támadnak a kiállítás alatt. |
| `shorthanded_shape` | Emberhátrány-forma: MIT JÁTSZANAK öt emberrel. |
| `shorthanded_shooters` | Emberhátrány-lövők: KI VÁLLALJA a befejezést öt emberrel. |
| `susp_earner_roles` | Kiállítás-kiharcolás poszt szerint: MELYIK POSZTJUK hozza a |
| `susp_earners` | Ki harcolja ki a kiállításokat: a hátrány kezdete előtti |
| `suspensions_by_score` | Fegyelem-állás: MIKOR jönnek a kiállítások — állás szerint. |

## scouting (1)

| Réteg | Mit mér |
|---|---|
| `key_players` | Kulcsemberek egy meccsből: kinél dől el a játék — szereponként a |

## setplays (2)

| Réteg | Mit mér |
|---|---|
| `setplay_efficiency` | Melyik figura működik: klaszterenként támadás / lövés / gól. |
| `setplay_finishers` | Figura-befejező: MELYIK FIGURÁJUKAT KI FEJEZI BE. |

## stats (9)

| Réteg | Mit mér |
|---|---|
| `distance_battle` | Futás-mérleg: MELYIK CSAPAT FUTJA TÚL a másikat. |
| `intensity_trend` | Kondíció-mutató: az ELSŐ és MÁSODIK félidőben mért átlagos |
| `pair_plus_minus` | Páros-mérleg: MELYIK KETTŐ megy jól EGYÜTT a pályán. |
| `player_fatigue` | Játékosonkénti tempó-visszaesés: első vs második félidő átlag- |
| `player_plus_minus` | Játékos-mérleg (+/−): kinek a pályán léte alatt jobb a |
| `possession` | Labdabirtoklás-arány csapatonként. |
| `rotation` | Rotáció-mélység: hány emberrel játssza a csapat a meccset. |
| `sprint_threats` | Sprint-veszély: KI VISZI A KONTRÁT — a legtöbbet sprintelő ember. |
| `sprints_by_score` | Sprint-állás: MIKOR sprintel a csapat — vezetésnél vagy hátrányban. |

## stoppages (9)

| Réteg | Mit mér |
|---|---|
| `long_break_response` | Hosszú állás utáni játék: KIZÖKKENTI-E ŐKET a hosszú megszakítás. |
| `playing_time` | Effektív játékidő: MENNYI a tényleges játék a megszakításokhoz |
| `stoppages` | MŰKÖDÖTT-E az időkérés? — a kérő csapat kapott góljai előtte/utána. |
| `timeout_finisher` | Időkérés-befejező: AZ IDŐKÉRÉS UTÁN KIRE JÁTSZANAK. |
| `timeout_first_attack` | Időkérés utáni első támadás: VAN-E KÉSZ FIGURÁJUK. |
| `timeout_first_defense` | Időkérés utáni védekezés: MEGÁLL-E A FAL a megszakítás után. |
| `timeout_record` | Időkérés-mérleg csapatonként: hányszor működött a "mentő" időkérés. |
| `timeout_sub_combo` | Időkérés-csomag: AZ IDŐKÉRÉSÜK CSERÉVEL JÁR-E. |
| `timeout_timing` | Időkérés-időzítés: MIKOR kérnek időt. |

## substitutions (8)

| Réteg | Mit mér |
|---|---|
| `gap_punishment` | Csere-büntetés: GÓLBA KERÜLNEK-E a csere-lyukak. |
| `late_subs` | Késő cserék: nagy tempó-esésű játékosok, akiket NEM cseréltek le. |
| `sub_gaps` | Csere-lyukak: MENNYI IDEIG JÁTSZANAK 5-EN csere közben. |
| `subs_by_score` | Csere-állás: VEZETVE FORGATNAK-E. |
| `substitution_blocks` | Csere-blokkok: egyesével cserélnek, vagy egységekben. |
| `substitution_triggers` | Csere-kiváltók: KAPOTT GÓL UTÁN cserélnek-e. |
| `substitutions` | Cserék + a cserék utáni IMPACT_S másodperc mérlege csapatonként. |
| `swap_pairs` | Váltópárok: KI KIT VÁLT a cseréknél. |

## summary_en (2)

| Réteg | Mit mér |
|---|---|
| `match_card_en` | English match card: compact, English-language match summary. |
| `scouting_cards_en` | English scouting card: a one-page opponent brief per team. |

## tactics (12)

| Réteg | Mit mér |
|---|---|
| `attack_motion` | Támadó-mozgás: álló vagy mozgásos a szervezett támadás. |
| `attack_side_shift` | Oldal-váltás a szünetre: MÁSIK SZÁRNYRA teszik-e át a játékot. |
| `attack_sides` | Melyik oldalon folyik a támadójáték — bal/közép/jobb sáv szerint. |
| `defense_form_shift` | Fal-váltás a szünetre: MÁS FALAT hoznak-e a második félidőre. |
| `field_tilt` | Területi fölény (field tilt): a csapat labdabirtoklásának mekkora |
| `formation_switching` | Védekezés-váltás: egy rendszert játszanak, vagy váltogatnak. |
| `pass_tempo` | Passz-tempó (labdajáratás sebessége): hány passz jut a SAJÁT |
| `slow_attack_cost` | Elhúzódó támadás ára: a passzív-veszélyes hosszú akciók HOZAMA. |
| `slow_attacks` | Elhúzódó (passzív-veszélyes) támadások csapatonként. |
| `static_attackers` | Álló támadók: KI mozog labda nélkül a legkevesebbet. |
| `tilt_fade` | Területi-fölény-esés: a field tilt az 1. vs a 2. félidőben. |
| `vs_formation` | Támadó-hatékonyság a VÉDŐFORMA szerint: melyik fal ellen megy. |

## training (1)

| Réteg | Mit mér |
|---|---|
| `training` | Csapatonként rangsorolt edzés-fókusz lista ({"home": [...], ...}). |

## xg (19)

| Réteg | Mit mér |
|---|---|
| `big_chance_finishers` | Ziccer-befejezők: KI ÉRTÉKESÍTI a nagy helyzeteket. |
| `big_save_momentum` | Bravúr utáni lendület: a nagy védés után jön-e gyors gól elöl. |
| `big_saves` | Bravúr-védések: nagy értékű (xG >= BIG_CHANCE_XG) helyzet, amit a |
| `conceded_chance_quality` | Kapott helyzetek minősége: MILYEN LÖVÉSEKET ENGED a fal. |
| `defense_by_score` | Előny-védekezés: LEÜL-E A FALUK, amikor vezetnek. |
| `finish_fade` | Befejezés-esés: a gólra váltás az 1. vs 2. félidőben. |
| `finisher_rotation` | Befejező-váltás: UGYANAZ fejez-e be a következő támadásban is. |
| `goal_patterns` | Gól-minta: UGYANAZT a gólt lövik-e újra és újra. |
| `miss_punishment` | Kihagyott ziccer ára: a kihagyott nagy helyzet utáni gyors kapott gól. |
| `missed_big_chances` | A kihagyott nagy helyzetek: xG >= BIG_CHANCE_XG, de nem gól. |
| `shot_accuracy` | Célzás-pontosság: a lövés-kísérletekből mennyi tart kapura. |
| `shot_concentration` | Lövő-koncentráció: mennyire egy emberre épül a lövés-terhelés. |
| `shot_quality_by_score` | Lövés-választás állás szerint: HÁTRÁNYBAN ELKAPKODJÁK-E. |
| `shot_release` | Elsütés-idő: kapásból lőnek, vagy sokáig fogják a labdát. |
| `wall_fade` | Fal-fáradás: MELYIK FÉLIDŐBEN nyílik ki a fal. |
| `wasteful_shooters` | Pontatlan lövők: KINEK a lövései mennek mellé. |
| `xg` | A meccs minden lövésének helyzetminősége + csapat-összegzés. |
| `xg_prevented` | Megmentett gólok (GSAx): a kapura tartó lövések összesített |
| `xg_saved` | Hárított xG: a fogott lövések helyzet-értékének összege a VÉDŐ |
