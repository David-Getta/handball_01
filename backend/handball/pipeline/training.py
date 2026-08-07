"""Edzés-fókusz javaslatok — a meccs gyengeségeiből következő gyakorlás.

A meccs utáni elemzés akkor ér célba, ha a következő EDZÉST alakítja.
Ez a réteg a már kiszámolt elemzésekből (védekezés, helyzetminőség,
hetesek, labdabiztonság, erőnlét, emberelőny, irányító-függés) állít
össze csapatonként rangsorolt gyakorlás-fókuszokat:

    {"area":  a terület (védekezés/befejezés/...),
     "title": a fókusz egy mondatban,
     "why":   a meccs-adat, ami indokolja,
     "drill": javasolt gyakorlat-típus}

Szándékosan szabály-alapú (nem nyelvi modell): minden javaslat mögött
kiszámolt szám áll, így az edző ellenőrizheti. A lista rangsorolt, és
legfeljebb MAX_ITEMS elemű — a fókusz attól fókusz, hogy kevés.
"""

from __future__ import annotations

from typing import Optional

from ..models.tracking import Match, Team
from .tactics import TacticsConfig

MAX_ITEMS = 5


def training_focus(match: Match,
                   config: Optional[TacticsConfig] = None) -> dict:
    """Csapatonként rangsorolt edzés-fókusz lista ({"home": [...], ...}).

    A szabályok ugyanazokat az alap-méréseket kérik újra, ezért a futás
    egy `primitive_cache` hatókörben zajlik — az eredmény változatlan.
    """
    from .primitive_cache import primitive_cache
    with primitive_cache(match):
        return _training_focus_cached(match, config)


def _training_focus_cached(match: Match,
                           config: Optional[TacticsConfig] = None) -> dict:
    """Az edzés-fókusz tényleges felépítése (lásd `training_focus`)."""
    config = config or TacticsConfig()
    out: dict = {"home": [], "away": []}

    def add(side, area, title, why, drill):
        if len(out[side]) < MAX_ITEMS:
            out[side].append({"area": area, "title": title,
                              "why": why, "drill": drill})

    # 1) Fedezés-fegyelem: sok szabadon hagyott lövő.
    try:
        from .defense import defense_analysis
        d = defense_analysis(match, config)
        for side in ("home", "away"):
            rec = d[side]
            if rec["shots_against"] >= 4 and (rec["free_pct"] or 0) >= 40:
                add(side, "védekezés", "Fedezés-fegyelem",
                    f"a kapott lövések {rec['free_pct']:.0f}%-ánál nem volt "
                    "védő a lövő 2 m-es körzetében",
                    "2v2/3v3 zárás-lecsúszás, kilépés a lövőre, "
                    "segítő-visszazárás párban")
            if rec["worst_zone"] and \
                    rec["zones"][rec["worst_zone"]]["goals"] >= 2:
                add(side, "védekezés",
                    f"Zóna-védekezés: {rec['worst_zone']}",
                    f"{rec['zones'][rec['worst_zone']]['goals']} kapott gól "
                    "ebből a zónából",
                    "a zóna páros-hármas védekezési helyzeteinek ismétlése "
                    "sokszorozott támadó-befejezéssel")
    except Exception:
        pass

    # 2) Befejezés: a helyzetek megvoltak, a gólok nem.
    try:
        from .xg import match_xg
        tx = match_xg(match, config)["teams"]
        for side in ("home", "away"):
            rec = tx[side]
            if rec["shots"] >= 4 and rec["diff"] <= -1.5:
                add(side, "befejezés", "Befejezés nyomás alatt",
                    f"a várhatónál {abs(rec['diff']):.1f} góllal kevesebb "
                    "született a kidolgozott helyzetekből",
                    "kapura lövés fáradtan/kontakt után, döntéshelyzetes "
                    "befejező sorozatok időkényszerrel")
    except Exception:
        pass

    # 3) Hetesek: kihagyott büntetők.
    try:
        from .rules import seven_meter_summary
        s7 = seven_meter_summary(match, config)
        for side in ("home", "away"):
            rec = s7[side]
            misses = rec["saved"] + rec["missed"]
            if rec["attempts"] >= 2 and misses * 2 >= rec["attempts"]:
                add(side, "befejezés", "Hétméteres-rutin",
                    f"{rec['attempts']} büntetőből {misses} kimaradt",
                    "hetes-sorozatok meccs-szimulált nyomással "
                    "(fáradt állapotban, sorrenddel)")
    except Exception:
        pass

    # 4) Labdabiztonság: több eladott labda, mint lövés.
    try:
        from .event_detection import EventType, detect_events
        ev = detect_events(match, config)
        for team, side in ((Team.HOME, "home"), (Team.AWAY, "away")):
            to = sum(1 for e in ev
                     if e.type == EventType.TURNOVER and e.team == team)
            sh = sum(1 for e in ev
                     if e.type in (EventType.SHOT, EventType.GOAL)
                     and e.team == team)
            if to >= 3 and to >= sh:
                add(side, "támadás", "Labdabiztonság",
                    f"{to} labdaeladás {sh} kapura lövés mellett",
                    "passz-folyosós játékok létszámhátrányban, "
                    "labdavezetés-korlátos kisjátékok")
    except Exception:
        pass

    # 5) Erőnlét: nagy intenzitás-esés a hajrára.
    try:
        from .stats import compute_intensity_timeline
        windows = compute_intensity_timeline(match)
        usable = [w for w in windows
                  if w["home_avg_ms"] > 0 or w["away_avg_ms"] > 0]
        third = max(1, len(usable) // 3)
        if len(usable) >= 3:
            for side in ("home", "away"):
                key = f"{side}_avg_ms"
                start = [w[key] for w in usable[:third] if w[key] > 0]
                end = [w[key] for w in usable[-third:] if w[key] > 0]
                if start and end:
                    s_avg = sum(start) / len(start)
                    e_avg = sum(end) / len(end)
                    if s_avg > 0 and (s_avg - e_avg) / s_avg >= 0.12:
                        drop = 100.0 * (s_avg - e_avg) / s_avg
                        add(side, "erőnlét", "Meccsvégi állóképesség",
                            f"az intenzitás a hajrára {drop:.0f}%-kal esett",
                            "intervallumos állóképesség + a csere-ritmus "
                            "áttekintése (rövidebb etapok a hajrában)")
    except Exception:
        pass

    # 6) Emberelőny: a létszámfölény nem hozott jobb gólarányt.
    try:
        from .rules import powerplay_efficiency
        eff = powerplay_efficiency(match, config)
        for side in ("home", "away"):
            rec = eff.get(side)
            if rec and rec["pp_shots"] >= 3 and rec["eq_shots"] >= 3 \
                    and rec["pp_eff_pct"] < rec["eq_eff_pct"]:
                add(side, "támadás", "Emberelőnyös figurák",
                    f"emberelőnyben {rec['pp_eff_pct']:.0f}% a gólarány, "
                    f"egyenlő létszámnál {rec['eq_eff_pct']:.0f}%",
                    "6v5 felállt figurák begyakorlása időkényszerrel")
    except Exception:
        pass

    # 6b) Gyenge támadás-típus: gyakori, de rosszul konvertáló támadásmód.
    try:
        from .attack_types import attack_efficiency
        eff = attack_efficiency(match, config)
        _drills = {
            "felállt támadás": "felállt védelem elleni figurák: beúszás, "
                               "keresztmozgás, tudatos befejezés-választás",
            "lerohanás": "lerohanás-befejezés fáradtan: 1-1, 2-1 helyzetek "
                         "kapura, gyors döntéssel",
            "gyors indítás": "gyors indítás utáni rendezett befejezés — "
                             "ne kapkodott lövés",
            "7 a 6": "7 a 6 elleni figurák: a plusz ember kihasználása "
                     "idő-kényszerrel",
        }
        for side in ("home", "away"):
            for typ, rec in (eff.get(side) or {}).items():
                if rec["attacks"] >= 4 and rec["goal_pct"] <= 25.0:
                    add(side, "támadás", f"Befejezés: {typ}",
                        f"a(z) {typ} támadásaik {rec['goal_pct']:.0f}%-a lett "
                        f"gól ({rec['goals']}/{rec['attacks']})",
                        _drills.get(typ, "az adott támadásmód befejezésének "
                                    "gyakorlása"))
    except Exception:
        pass

    # 7) Irányító-függés: a saját támadás egyetlen emberen múlik.
    try:
        from .playmaker import playmaker_dependency
        pd = playmaker_dependency(match, config)
        for side in ("home", "away"):
            rec = pd[side]
            if rec["dependency"] == "magas":
                add(side, "támadás", "Második szervező felépítése",
                    "az irányító nélkül futott támadások lövésig jutása "
                    f"{100 * (rec['shot_rate_drop'] or 0):.0f} "
                    "százalékponttal esik",
                    "támadásszervezés-gyakorlás az első számú irányító "
                    "nélkül, átlövő/beálló indítási variációk")
    except Exception:
        pass

    # 8) Átmenet-védekezés: sok gyors kapott gól labdavesztés után.
    try:
        from .defense import transition_defense
        td = transition_defense(match, config)
        for side in ("home", "away"):
            rec = td[side]
            if rec["turnovers"] >= 4 and rec["transition_goals_against"] >= 2:
                add(side, "védekezés", "Visszazárás labdavesztés után",
                    f"{rec['transition_goals_against']} gyors gólt kaptak "
                    f"labdaeladás után ({rec['pct']:.0f}%)",
                    "átmenet-védekezés: azonnali visszafutás és a labdás "
                    "megállítása, 5v6 rendezetlen helyzetek gyakorlása")
    except Exception:
        pass

    # 9) Laza védekezés: sok tér a lövőnek (magas engedett xG mellett).
    try:
        from .defense import defense_analysis, defensive_pressure
        dp = defensive_pressure(match, config)
        da = defense_analysis(match, config)
        for side in ("home", "away"):
            pr = dp[side]["avg_pressure_m"]
            if (pr is not None and pr >= 2.5
                    and da[side]["shots_against"] >= 4):
                add(side, "védekezés", "Aktívabb kilépés a lövőre",
                    f"a labdásra átlag {pr:.1f} m-re álltak — sok tér a "
                    "9 m-es lövéshez",
                    "kilépés-visszalépés drill, aktív kéz a lövősávban, "
                    "kettős blokk gyakorlása")
    except Exception:
        pass

    # 10) Sok elöl (támadó harmadban) elvesztett labda: a befejezés
    # kapkodó/kockázatos — az ellenfél kontrája ezekből indul.
    try:
        from .defense import turnover_zones
        tz = turnover_zones(match, config)
        for side in ("home", "away"):
            rec = tz[side]
            if rec["total"] >= 5 and rec["front_pct"] >= 50.0:
                add(side, "támadás", "Biztonságos befejezés",
                    f"a labdaeladásaik {rec['front_pct']:.0f}%-a a támadó "
                    "harmadban történt — ezekből indul az ellenfél kontrája",
                    "befejezés-döntés gyakorlása nyomás alatt (lövés vagy "
                    "visszajátszás), passz a szélső-beálló kapcsolatban, "
                    "labdavesztés utáni azonnali letámadás")
    except Exception:
        pass

    # 11) Elvesztett szoros hajrá: a végjáték-helyzeteket gyakorolni kell.
    try:
        from .momentum import clutch_performance
        cp = clutch_performance(match, config)
        if cp.get("available") and cp.get("close"):
            gh, ga = cp["home"]["goals"], cp["away"]["goals"]
            for side, own, opp in (("home", gh, ga), ("away", ga, gh)):
                if opp - own >= 2:
                    add(side, "végjáték", "Szoros végjáték gyakorlása",
                        f"a szoros hajrát {opp}–{own}-ra elvesztették",
                        "szituációs játék: utolsó 5 perc szimulálása "
                        "(1-2 gólos állásról), támadás-befejezés nyomás "
                        "alatt, időkérés utáni figura begyakorlása")
    except Exception:
        pass

    # 12) Sok lövésüket blokkolják: a lövés-előkészítésen kell dolgozni.
    try:
        from .defense import detect_blocks
        bl = detect_blocks(match, config)
        for side in ("home", "away"):
            other = "away" if side == "home" else "home"
            against = bl[other]["blocks"]  # az ellenfél blokkjai = ellenünk
            if against >= 3:
                add(side, "támadás", "Lövés a blokk ellen",
                    f"{against} lövésüket blokkolta az ellenfél fala",
                    "elmozgás lövés előtt (át- és kilépés), lövőcsel után "
                    "váltott ritmus, emelt/pattintott lövés a blokk mellett")
    except Exception:
        pass

    # 13) Második félidei gól-visszaesés: a mérleg félidők közt romlik
    # (gól-alapú jel, a tempó-alapú fáradás-szabály kiegészítője).
    try:
        from .momentum import halftime_score, score_progression
        hs = halftime_score(match, config)
        if hs is not None:
            fin = score_progression(match, config)["final"]
            for side, i in (("home", 0), ("away", 1)):
                opp = "away" if side == "home" else "home"
                fh_d = hs[side] - hs[opp]
                sh_d = (fin[i] - hs[side]) - (fin[1 - i] - hs[opp])
                if fh_d - sh_d >= 3 and (fin[0] + fin[1]) >= 8:
                    add(side, "kondíció", "Második félidei visszaesés",
                        f"a félidő-mérleg {fh_d:+d}-ról {sh_d:+d}-ra "
                        "romlott",
                        "forgatás-terv (tervezett cserék a 40. perc körül), "
                        "magas intenzitású intervall-blokk az edzésen, "
                        "a 2. félidei kezdő öt percre külön figura")
    except Exception:
        pass

    # 14) Lassú válasz a kapott gólra: az újraindulást kell gyakorolni.
    try:
        from .momentum import goal_responses
        gr = goal_responses(match, config)
        for side in ("home", "away"):
            rec = gr[side]
            if rec["responses"] >= 3 and (rec["avg_s"] or 0) >= 150.0:
                add(side, "mentális", "Újraindulás kapott gól után",
                    f"átlag {rec['avg_s']:.0f} mp telt el a válaszgólig",
                    "kapott gól utáni azonnali gyors középkezdés "
                    "begyakorlása, 'következő labda' rutin, pozitív "
                    "kommunikáció a falban")
    except Exception:
        pass

    # 15) Egy védőforma ellen elakadnak: fal elleni figurákat kell
    # gyakorolni (a felderítés tükör-szabálya a SAJÁT csapatra).
    try:
        from .tactics import efficiency_vs_formation
        ef = efficiency_vs_formation(match, config)
        for side in ("home", "away"):
            pools = [(f_, v) for f_, v in ef[side].items()
                     if v["shots"] >= 4]
            if len(pools) < 2:
                continue

            def _pct(v):
                return 100.0 * v["goals"] / v["shots"]
            worst = min(pools, key=lambda kv: _pct(kv[1]))
            best = max(pools, key=lambda kv: _pct(kv[1]))
            if _pct(best[1]) - _pct(worst[1]) >= 25.0:
                add(side, "támadás", f"Játék a {worst[0]} fal ellen",
                    f"a {worst[0]} ellen csak {_pct(worst[1]):.0f}%-ot "
                    "konvertáltak",
                    f"{worst[0]} elleni figurák (beálló-elzárások, "
                    "átlövő-keresztek, szélső-befutás), türelmes "
                    "körbejátszás a fal megbontásáig")
    except Exception:
        pass

    # 16) Terméketlen hosszú támadások: időkorlátos befejezés-gyakorlás.
    try:
        from .attack_types import attack_duration_efficiency
        de = attack_duration_efficiency(match, config)
        for side in ("home", "away"):
            lr = de[side].get("hosszú (35 mp+)")
            sr = de[side].get("rövid (<15 mp)")
            if not (lr and sr and lr["attacks"] >= 4
                    and sr["attacks"] >= 4):
                continue
            lp = 100.0 * lr["goals"] / lr["attacks"]
            sp_ = 100.0 * sr["goals"] / sr["attacks"]
            if sp_ - lp >= 20.0:
                add(side, "támadás", "Befejezés időkorláttal",
                    f"a hosszú támadásaik csak {lp:.0f}%-ban hoztak gólt "
                    f"(a rövidek {sp_:.0f}%-ban)",
                    "25 mp-es belső óra a felállt támadásra edzésen, "
                    "korai lövés-döntés gyakorlása, második hullám "
                    "(visszatámadás lepattanóra)")
    except Exception:
        pass

    # 17) Kihagyott ziccerek: nagy xG-jű helyzetek gól nélkül —
    # a helyzetkihasználást célzottan kell gyakorolni.
    try:
        from .xg import missed_big_chances
        miss: dict[str, int] = {"home": 0, "away": 0}
        for m in missed_big_chances(match, config):
            miss[m["team"]] += 1
        for side in ("home", "away"):
            if miss[side] >= 3:
                add(side, "támadás", "Ziccer-befejezés",
                    f"{miss[side]} nagy helyzetük (xG >= 0,5) maradt "
                    "gól nélkül",
                    "ziccer-sorozatok fáradtan (sprint után befejezés), "
                    "kapus elleni 1 az 1 döntésgyakorlás, sarokra "
                    "helyezés jelre")
    except Exception:
        pass

    # 18) Lassú kapus-indítás: a védés utáni felhozatal gyakorlása —
    # a gyors kidobás kontra-fegyver (a felderítési kulcs tükör-szabálya).
    try:
        from .goalkeeper import outlet_speed
        osp = outlet_speed(match, config)
        for side in ("home", "away"):
            rec = osp[side]
            if rec["outlets"] >= 3 and rec["fast"] / rec["outlets"] < 0.5:
                avg = rec["sum_s"] / rec["outlets"]
                add(side, "kapus", "Gyors indítás védés után",
                    f"a {rec['outlets']} mért indításból csak "
                    f"{rec['fast']} ért át gyorsan a felezőn "
                    f"(átlag {avg:.0f} mp)",
                    "kidobás-gyakorlás célkapukra, első passz a futó "
                    "szélsőnek, indítás-jel begyakorlása védés után")
    except Exception:
        pass

    # 19) A 7 a 6 ára: ha többször kaptak gólt az üresen hagyott kapuba,
    # a lehozott kapusos játék labdabiztonságát kell gyakorolni.
    try:
        from .goalkeeper import empty_net_goals
        eng = empty_net_goals(match, config)
        for side in ("home", "away"):
            rec = eng[side]
            if rec["conceded_empty"] >= 2:
                add(side, "támadás", "7 a 6 labdabiztonság",
                    f"{rec['conceded_empty']} gólt kaptak üres kapura "
                    "a lehozott kapusos játék kockázataként",
                    "emberelőnyös figurák labdabiztos befejezéssel, "
                    "labdavesztés utáni azonnali letámadás, a kapus "
                    "gyors visszaérkezésének gyakorlása")
    except Exception:
        pass

    # 20) Egy-tengelyű támadás: ha a gólok zöme egyetlen (gólpasszoló ->
    # lövő) párosból jön, az ellenfél elvágja — B-tervet kell építeni.
    try:
        from .event_detection import (EventType, assist_network,
                                      detect_shots)
        net = assist_network(match, config)
        goals_by = {"home": 0, "away": 0}
        for e in detect_shots(match, config):
            if e.type == EventType.GOAL:
                goals_by[e.team.value] += 1
        for side in ("home", "away"):
            pairs = net[side]["pairs"]
            if not pairs or not goals_by[side]:
                continue
            top = pairs[0]
            share = top["goals"] / goals_by[side]
            if top["goals"] >= 3 and share >= 0.6:
                add(side, "támadás", "Támadás-változatosság",
                    f"a gólok {100.0 * share:.0f}%-a a(z) {top['from']}. "
                    f"→ {top['to']}. tengelyről jött",
                    "másodlagos befejezési utak gyakorlása (szélső-"
                    "befutás, beálló-játék), lekapcsolódó mozgások a "
                    "tengely letámadása ellen")
    except Exception:
        pass

    # 24) Szélső-játék: ha vannak szélsők a felállásban, de a gólokból
    # kimaradnak, a támadás beszűkült — szélesíteni kell.
    try:
        from .roles import estimate_positions
        from .xg import match_xg
        est = estimate_positions(match, config)
        r_xg = match_xg(match, config)
        for side in ("home", "away"):
            wings = {tid for tid, p_ in est.get(side, {}).items()
                     if p_["poszt"] == "szélső"}
            if not wings:
                continue
            team_goals = r_xg["teams"][side]["goals"]
            if team_goals < 6:
                continue
            wing_goals = sum(rec["goals"] for rec in r_xg.get("shooters", [])
                             if rec["team"] == side
                             and rec["player_id"] in wings)
            if wing_goals / team_goals <= 0.15:
                add(side, "támadás", "Szélső-játék bevonása",
                    f"a {team_goals} gólból csak {wing_goals} jött "
                    "szélsőtől, pedig a felállásban ott vannak",
                    "szélső-befutások begyakorlása, gyors átemelés a "
                    "túloldali szélsőnek, bedobás utáni szélső-figura")
    except Exception:
        pass

    # 23) Visszarendeződés-tempó: ha méréssel is lassú a visszaérés,
    # nem kell kontra-gólt várni a jelzéshez — korai figyelmeztetés.
    try:
        from .defense import RECOVERY_SLOW_S, transition_recovery
        trr = transition_recovery(match, config)
        for side in ("home", "away"):
            rec = trr[side]
            if (rec["transitions"] >= 4 and rec["avg_s"] is not None
                    and rec["avg_s"] >= RECOVERY_SLOW_S):
                add(side, "védekezés", "Visszarendeződés-tempó",
                    f"átlag {rec['avg_s']:.1f} mp a felálló védelemig "
                    f"({rec['slow']}/{rec['transitions']} lassú átmenet)",
                    "visszafutás-versenyek 3 mp-es célidővel, az első "
                    "visszaérő oszt-szerepének begyakorlása, védő-"
                    "átvételi kommunikáció")
    except Exception:
        pass

    # 22) Kapus-forma: ha a kapus a helyzetekhez képest sokat kap
    # (negatív GSAx), célzott kapus-edzés kell — nem a fal a hibás.
    try:
        from .xg import xg_prevented
        xp = xg_prevented(match, config)
        for side in ("home", "away"):
            rec = xp[side]
            if rec["conceded"] >= 3 and rec["prevented"] <= -2.0:
                add(side, "kapus", "Kapus-forma",
                    f"a kapott gólok {abs(rec['prevented']):.1f}-gyel "
                    "haladják meg a helyzetekből várhatót (GSAx "
                    f"{rec['prevented']:+.1f})",
                    "helyezkedés-videózás a kapott gólokból, "
                    "reakció-gyakorlatok közeli lövésekre, sarok-védés "
                    "ismétlő sorozatok")
    except Exception:
        pass

    # 21) Rotáció-tervezés: ha többen is nagyot esnek a tempóból és
    # cserét sem kapnak, a pad használatát kell megtervezni.
    try:
        from .substitutions import late_sub_flags
        per_side: dict[str, int] = {"home": 0, "away": 0}
        for f_ in late_sub_flags(match, config):
            per_side[f_["team"]] += 1
        for side in ("home", "away"):
            if per_side[side] >= 2:
                add(side, "kondíció", "Rotáció-tervezés",
                    f"{per_side[side]} játékos 20%+ tempót esett a 2. "
                    "félidőben, és végig a pályán maradt",
                    "tervezett csere-ablakok a 40–50. percre, a kulcs-"
                    "posztokon kettős szereposztás begyakorlása")
    except Exception:
        pass

    # 25) Fegyelem: ha a csapat többször kiül (2+ felismert kiállítás),
    # a védekezés-technikán kell dolgozni — az emberhátrány a
    # leggyorsabb módja a meccs elvesztésének.
    try:
        from .rules import detect_powerplay
        n_susp = {"home": 0, "away": 0}
        for w in detect_powerplay(match):
            n_susp[w["team_down"]] += 1
        for side in ("home", "away"):
            if n_susp[side] >= 2:
                add(side, "védekezés", "Fegyelmezett védekezés",
                    f"{n_susp[side]} kiállítást szedett össze a csapat "
                    "— az emberhátrányok percei kapott gólokat érnek",
                    "test-elzárás kéz nélkül (1v1 falgyakorlat), "
                    "lépésmunka a betörő lassítására fogás helyett, "
                    "kiszorítás oldalra a hatosnál")
    except Exception:
        pass

    # 26) Szünet utáni kezdés: ha a 2. félidő első 5 percében 2+ gólos
    # mínuszba kerül a csapat, a visszatérés-protokollon kell dolgozni.
    try:
        from .halftime import second_half_start
        shs = second_half_start(match, config)
        if shs is not None:
            for side, other in (("home", "away"), ("away", "home")):
                if shs[other] - shs[side] >= 2:
                    add(side, "mentális", "Szünet utáni protokoll",
                        f"a 2. félidő első 5 perce {shs[side]}–"
                        f"{shs[other]} — a csapat az öltözőben maradt",
                        "a 2. félidő első támadása legyen előre "
                        "megbeszélt figura; bemelegítő 2 perces magas "
                        "tempójú játék a pályára lépés előtt")
    except Exception:
        pass

    # 27) Figura-frissítés: ha a leggyakoribb figura terméketlen (4+
    # támadásból legfeljebb 20% gól), az ellenfelek már olvassák —
    # variáció kell.
    try:
        from .setplays import setplay_efficiency
        eff_tf = setplay_efficiency(match)
        for side in ("home", "away"):
            rows_tf = eff_tf.get(side) or []
            if not rows_tf:
                continue
            top_tf = rows_tf[0]  # gyakoriság szerint az első
            if top_tf["attacks"] >= 4 and top_tf["goal_pct"] <= 20.0:
                add(side, "támadás", "Figura-frissítés",
                    f"a leggyakoribb figura {top_tf['attacks']} "
                    f"támadásból csak {top_tf['goals']} gólt hozott "
                    f"({top_tf['goal_pct']:.0f}%) — kiszámíthatóvá vált",
                    "a fő figurához második befejezési ág begyakorlása "
                    "(át a túloldalra / beálló-bejátszás), és egy új "
                    "nyitó-variáció ugyanabból az alapállásból")
    except Exception:
        pass

    # 28) Hetes-variáció: ha a fő dobónk irány-képe kiszámítható (2+
    # mért heteséből 75%+ egy sávba megy), az ellenfél kapusa készülni
    # fog rá — váltogatás kell.
    try:
        from .rules import seven_meter_outcomes
        by_taker: dict = {}
        for sm in seven_meter_outcomes(match, config):
            if sm.get("shooter_id") is None or not sm.get("irany"):
                continue
            rec28 = by_taker.setdefault((sm["team"], sm["shooter_id"]),
                                        {})
            rec28[sm["irany"]] = rec28.get(sm["irany"], 0) + 1
        for (side, pid), dirs28 in by_taker.items():
            n28 = sum(dirs28.values())
            if n28 >= 2 and max(dirs28.values()) / n28 >= 0.75:
                add(side, "befejezés", "Hetes-variáció",
                    f"a(z) {pid}. játékos hetesei kiszámíthatóak: a "
                    f"mért {n28} dobásból a nagy többség ugyanabba a "
                    "sávba ment",
                    "hetes-sorozat kötelező irány-váltogatással "
                    "(a dobó előre húzott kártya szerint lő), kapussal, "
                    "nyomás alatt")
                break  # csapatonként egy fókusz elég
    except Exception:
        pass

    # 30) Beálló-kapcsolat: ha van beálló, de a támadások alig mennek
    # rajta át (15% alatt), vagy a beállós játék terméketlen (a gólarány
    # 15+ ponttal rosszabb, mint nélküle), a beadás-játékot kell
    # gyakorolni.
    try:
        from .attack_types import pivot_usage
        pu30 = pivot_usage(match, config)
        for side in ("home", "away"):
            rec30 = pu30[side]
            if rec30["attacks"] < 6 or not rec30["pivot_ids"]:
                continue
            share30 = 100.0 * rec30["pivot_attacks"] / rec30["attacks"]
            if share30 <= 15.0:
                add(side, "támadás", "Beálló-kapcsolat",
                    f"a támadások mindössze {share30:.0f}%-a megy a "
                    "beállón át — a legjobb helyzeteket adó kapcsolat "
                    "kihasználatlan",
                    "beadás-gyakorlat mozgó beállóra: átlövő-beálló "
                    "kettősök, elzárás után azonnali beadás, védőkkel")
                continue
            other30 = rec30["attacks"] - rec30["pivot_attacks"]
            if (rec30["pivot_attacks"] >= 3 and other30 >= 3
                    and rec30["pivot_goal_pct"] is not None
                    and rec30["other_goal_pct"] is not None
                    and rec30["other_goal_pct"]
                    - rec30["pivot_goal_pct"] >= 15.0):
                add(side, "támadás", "Beálló-kapcsolat",
                    f"a beállós támadás terméketlen ("
                    f"{rec30['pivot_goal_pct']:.0f}% gól, nélküle "
                    f"{rec30['other_goal_pct']:.0f}%) — a beadás vagy "
                    "a befejezés akad el",
                    "beadás utáni befejezés-sorozat: fordulás lövésbe "
                    "két védő közt, passzív jelzésig kötelező beadás")
    except Exception:
        pass

    # 32) Passz-lánc: ha a hosszú körbejáratás terméketlen (6+ passzos
    # támadások gólarány nélkül), vagy a rövid játék elkapkodott (a
    # támadások zöme 0–2 passz, gyenge gólaránnyal), célzott gyakorlat.
    try:
        from .attack_types import pass_chains
        pc32 = pass_chains(match, config)
        for side in ("home", "away"):
            rec32 = pc32[side]
            if rec32["attacks"] < 6:
                continue
            long32 = rec32["buckets"].get("6+ passz")
            short32 = rec32["buckets"].get("0–2 passz")
            if (long32 and long32["attacks"] >= 4
                    and long32["goal_pct"] <= 20.0):
                add(side, "támadás", "Passz-lánc",
                    f"a hosszú (6+ passzos) támadások terméketlenek "
                    f"({long32['goals']}/{long32['attacks']} gól) — a "
                    "körbejáratás végén elfogy a lendület",
                    "körbejáratás időkorláttal: a 4. passz után két "
                    "passzon belül kötelező befejezés-kísérlet, "
                    "passzív-jelzéssel")
                continue
            if (short32 and short32["attacks"] >= 4
                    and short32["goal_pct"] <= 25.0
                    and short32["attacks"] / rec32["attacks"] >= 0.6):
                add(side, "támadás", "Passz-lánc",
                    f"a támadások zöme 0–2 passzos, de gyenge "
                    f"gólaránnyal ({short32['goals']}/"
                    f"{short32['attacks']}) — elkapkodott befejezések",
                    "türelem-gyakorlat: minimum 4 passz kötelező a "
                    "lövés előtt, kivéve tiszta ziccernél")
    except Exception:
        pass

    # 31) Sáv-védelem: ha az ellenfél betörései egy sávban
    # koncentrálódnak ellenünk (40%+, 2+ gól onnan), a segítő védő
    # csúszását kell gyakorolni abban a sávban.
    try:
        from .defense import breakthrough_lanes
        bl31 = breakthrough_lanes(match, config)
        for att31 in ("home", "away"):
            def31 = "away" if att31 == "home" else "home"
            rec31 = bl31[att31]
            if rec31["entries"] < 5 or not rec31["top_lane"]:
                continue
            top31 = rec31["lanes"][rec31["top_lane"]]
            share31 = 100.0 * top31["entries"] / rec31["entries"]
            if share31 >= 40.0 and top31["goals"] >= 2:
                add(def31, "védekezés", "Sáv-védelem",
                    f"az ellenfél betöréseinek {share31:.0f}%-a a(z) "
                    f"{rec31['top_lane']} sávban jött, {top31['goals']} "
                    "góllal — a segítő védő későn ér oda",
                    "sáv-védelem gyakorlat: a betörő sávjába a szomszéd "
                    "védő időben csúszik be, mögötte lánc-zárás, "
                    "3 támadó vs 3 védő felállásból")
    except Exception:
        pass

    # 33) Kapus-helyezkedés: ha a saját kapus túl kint áll (átlag 1,5 m+
    # a gólvonaltól), az átemelés ellen sebezhető — helyezkedés-gyakorlat.
    try:
        from .goalkeeper import gk_positioning
        gp33 = gk_positioning(match, config)
        for side in ("home", "away"):
            rec33 = gp33[side]
            if rec33["avg_depth_m"] is None:
                continue
            if rec33["avg_depth_m"] >= 1.5:
                add(side, "kapus", "Kapus-helyezkedés",
                    f"a kapus átlag {rec33['avg_depth_m']:.1f} m-re áll "
                    "ki a gólvonaltól — az átemelés és a lob ellen "
                    "sebezhető, főleg kontránál",
                    "kapus-helyezkedés gyakorlat: gyors visszalépés a "
                    "vonalra átemelés-veszélynél, mélység-igazítás a "
                    "lövő távolságához, kontra-visszatérés")
    except Exception:
        pass

    # 34) Kontra-befejezés: ha a csapat sok labdát szerez, de alig
    # váltja gyors gólra (4+ szerzés, 20% alatti konverzió), a
    # lerohanás-befejezést kell gyakorolni.
    try:
        from .attack_types import transition_offense
        to34 = transition_offense(match, config)
        for side in ("home", "away"):
            rec34 = to34[side]
            if rec34["steals"] < 4:
                continue
            conv34 = 100.0 * rec34["quick_goals"] / rec34["steals"]
            if conv34 <= 20.0:
                add(side, "támadás", "Kontra-befejezés",
                    f"{rec34['steals']} labdaszerzésből csak "
                    f"{rec34['quick_goals']} lett gyors gól "
                    f"({conv34:.0f}%) — a megszerzett labda nem fordul "
                    "azonnali gólra",
                    "lerohanás-befejezés gyakorlat: 2-1 és 3-2 "
                    "túlszám kapura futásból, gyors első passz a "
                    "szerzés után, higgadt befejezés kapussal")
    except Exception:
        pass

    # 29) Emberfogás-tapadás: ha van lazán őrző védőnk (a leglazább
    # emberfogó 2,5 m+ átlagtávról kíséri az emberét), az egy-egy
    # elleni védekezést kell gyakorolni — névre szólóan.
    try:
        from .defense import MARK_LOOSE_M, marking_pairs
        mk29 = marking_pairs(match, config)
        for side in ("home", "away"):
            cands = [d29 for d29 in mk29[side]["defenders"]
                     if d29["frames"] >= 50]
            if not cands:
                continue
            loose29 = max(cands, key=lambda d29: d29["avg_dist_m"])
            if loose29["avg_dist_m"] < MARK_LOOSE_M:
                continue
            pid29 = (loose29["defender_jersey"]
                     if loose29["defender_jersey"] is not None
                     else loose29["defender"])
            add(side, "védekezés", "Emberfogás-tapadás",
                f"a(z) {pid29}-es átlag {loose29['avg_dist_m']:.1f} "
                "m-ről őrzi az emberét — az egy-egy elleni tapadás "
                "laza",
                "1-1 elleni árnyékolás szűk folyosóban: a védő végig "
                "karnyújtáson belül marad, 30 mp-es körök, "
                "szerepcserével")
    except Exception:
        pass

    # 35) Lövésválasztás: ha a csapat sokat lő távolról (átlövés), de
    # gyenge a gólarány (5+ távoli lövés, a lövések 40%+-a távoli,
    # 25% alatti gólarány), a lövésválasztást és az átlövő-technikát
    # kell gyakorolni.
    try:
        from .attack_types import shot_ranges
        sr35 = shot_ranges(match, config)
        for side in ("home", "away"):
            rec35 = sr35[side]
            far35 = rec35["far"]
            if far35["shots"] < 5 or rec35["total_shots"] < 1:
                continue
            far_pct35 = 100.0 * far35["shots"] / rec35["total_shots"]
            goal_pct35 = far35["goal_pct"]
            if goal_pct35 is None or goal_pct35 > 25.0 or far_pct35 < 40.0:
                continue
            add(side, "támadás", "Lövésválasztás",
                f"a lövések {far_pct35:.0f}%-a távolról esik, de a "
                f"távoli gólarány csak {goal_pct35:.0f}% — sok az "
                "alacsony esélyű átlövés",
                "lövésválasztás-játék: átlövés csak tiszta helyzetben, "
                "különben még egy lejátszás a beállóra/betörésre; "
                "átlövő-technika kapussal, blokk fölött/mellett, "
                "felugrásból pontos sarokra")
    except Exception:
        pass

    # 36) Kapus-védés sáv szerint: ha a SAJÁT kapusunk egy távolság-sávra
    # feltűnően gyenge (elég kaputra érkezett lövés, 50% alatti védés), azt
    # a sávot kell célzottan gyakorolni.
    try:
        from .goalkeeper import GK_RANGE_MIN_FACED, gk_save_ranges
        gsr36 = gk_save_ranges(match, config)
        _drill36 = {
            "close": "közeli lövés-védés: lábmunka és reflex a 6-os "
                     "vonalról, beálló- és szélső-szögek zárása",
            "mid": "közép-távoli lövés-védés: kéz-láb koordináció, a "
                   "test-vonal tartása, kilépés a lövőre",
            "far": "átlövés-védés: felső sarkok olvasása, blokk mögötti "
                   "helyezkedés a védőfallal összehangolva",
        }
        _lbl36 = {"close": "közeli", "mid": "közép-távoli", "far": "távoli"}
        for side in ("home", "away"):
            wb36 = gsr36[side]["weak_band"]
            if wb36 is None:
                continue
            b36 = gsr36[side][wb36]
            if b36["faced"] < GK_RANGE_MIN_FACED or b36["save_pct"] is None \
                    or b36["save_pct"] >= 50.0:
                continue
            add(side, "kapus", "Kapus-védés sáv szerint",
                f"a kapus a(z) {_lbl36[wb36]} lövésekre gyenge "
                f"({b36['save_pct']:.0f}% védés, {b36['saves']}/"
                f"{b36['faced']})",
                _drill36[wb36])
    except Exception:
        pass

    # 37) Befejezés-változatosság: ha a góljaink zöme (6+ gólból 55%+)
    # ugyanarra a kapuoldalra megy, kiszámíthatóak vagyunk — a
    # hely-változtatást kell gyakorolni.
    try:
        from .attack_types import goal_placement
        gp37 = goal_placement(match, config)
        _lbl37 = {"bal": "bal", "közép": "középső", "jobb": "jobb"}
        for side in ("home", "away"):
            rec37 = gp37[side]
            dom37 = rec37["dominant"]
            if dom37 is None or rec37["goals"] < 6:
                continue
            share37 = 100.0 * rec37[dom37] / rec37["goals"]
            if share37 < 55.0:
                continue
            add(side, "támadás", "Befejezés-változatosság",
                f"a góljaink {share37:.0f}%-a a(z) {_lbl37[dom37]} "
                "kapuoldalra megy — kiszámítható a befejezés, a kapus "
                "felkészülhet rá",
                "célzott-lövés játék: felváltva a négy sarokba és "
                "középre kapussal, a kapus mozgásának olvasása; "
                "büntető-kör, ha kétszer egymás után ugyanoda lősz")
    except Exception:
        pass

    # 38) Szélső-befejezés: ha a szélső (éles) szögből gyengén fejeznek be
    # (4+ szélső-lövés, 30% alatti gólarány), a szélső-befejezést kell
    # gyakorolni.
    try:
        from .attack_types import wing_finishing
        wf38 = wing_finishing(match, config)
        for side in ("home", "away"):
            rec38 = wf38[side]
            if rec38["shots"] < 4 or rec38["goal_pct"] is None \
                    or rec38["goal_pct"] > 30.0:
                continue
            add(side, "támadás", "Szélső-befejezés",
                f"a szélső szögből csak {rec38['goal_pct']:.0f}% a "
                f"gólarány ({rec38['goals']}/{rec38['shots']}) — az éles "
                "szög nincs kihasználva",
                "szélső-befejezés gyakorlat: felugrásos lövés a hosszú "
                "sarokba és a kapus lába közé, ejtés a kilépő kapus fölött, "
                "beadás-befejezés a szélről 1-1 kapussal")
    except Exception:
        pass

    # 39) Védekezési vonal: ha felfutó/agresszív falat húzunk, a mögöttes
    # teret kell tudni zárni (visszafutás), mély falnál a türelmes felállt
    # védekezést és a beálló-őrzést gyakorolni.
    try:
        from .defense import (DEF_LINE_DEEP_M, DEF_LINE_HIGH_M,
                              DEF_LINE_MIN_FRAMES, defensive_line_height)
        dlh39 = defensive_line_height(match, config)
        for side in ("home", "away"):
            rec39 = dlh39[side]
            if rec39["avg_height_m"] is None \
                    or rec39["frames"] < DEF_LINE_MIN_FRAMES:
                continue
            avg39 = rec39["avg_height_m"]
            if avg39 >= DEF_LINE_HIGH_M:
                add(side, "védekezés", "Felfutó fal — mögöttes tér",
                    f"felfutó, agresszív fal (átlag {avg39:.1f} m-re a "
                    "kaputól) — a hátatok mögötti tér és a lefutás a "
                    "kockázat",
                    "kilépés + visszafutás játék: a felső védő kilép a "
                    "lövőre, a szomszéd azonnal zár mögé; 3-2 elleni "
                    "visszafutás túlszámban, kommunikációval")
            elif avg39 <= DEF_LINE_DEEP_M:
                add(side, "védekezés", "Mély fal — aktív kilépés",
                    f"mély, passzív fal (átlag {avg39:.1f} m-re a kaputól) "
                    "— a távoli lövést túl könnyen engeditek",
                    "aktív 6-0/5-1 kilépés-gyakorlat: időzített kilépés az "
                    "átlövőre és visszazárás a beállóra, a mélység "
                    "megtartásával")
    except Exception:
        pass

    # 40) Vertikális építkezés: ha nagyon türelmesen köröztetünk (30+
    # passz, 20% alatti előre-passz), a mélységi, penetráló játékot kell
    # gyakorolni — különben kiszámítható és könnyen védhető a támadás.
    try:
        from .attack_types import PASS_FORWARD_MIN_M, pass_direction
        pd40 = pass_direction(match, config)
        for side in ("home", "away"):
            rec40 = pd40[side]
            if rec40["passes"] < 30 or rec40["forward_pct"] is None \
                    or rec40["forward_pct"] > 20.0:
                continue
            add(side, "támadás", "Vertikális építkezés",
                f"csak az átadások {rec40['forward_pct']:.0f}%-a visz "
                "előre — sok az oldalpassz, a támadás kiszámítható és "
                "könnyen védhető",
                "mélységi játék gyakorlat: minden 2. átadás legyen előre "
                f"(min. {PASS_FORWARD_MIN_M:.0f} m nyereség), betörés-utáni "
                "kiadás, gyors első hullám a lerohanásban")
    except Exception:
        pass

    # 41) Gól-előkészítés változatossága: ha a gólpasszaink zöme (4+
    # gólpasszból 60%+) egyetlen forrásból (szél/közép/hátsó) jön, a
    # támadás kiszámítható — több irányból kell tudni gólt előkészíteni.
    try:
        from .attack_types import ASSIST_SOURCE_MIN, assist_sources
        asr41 = assist_sources(match, config)
        _drill41 = {
            "szél": "több csatorna: a szél mellé beálló-leadás és átlövő-"
                    "csel, hogy ne csak a beadásra épüljön a gól",
            "közép": "külső befejezés: átlövés és szélső-beadás gyakorlása, "
                     "hogy ne csak a beállóra/betörésre menjen minden",
            "hátsó": "belső játék: beálló-leadás, betörés és szélső-beadás, "
                     "hogy ne csak az átlövő-kiadás készítse a gólt",
        }
        _lbl41 = {"szél": "a szélről", "közép": "középről",
                  "hátsó": "a hátsó sorból"}
        for side in ("home", "away"):
            rec41 = asr41[side]
            dom41 = rec41["dominant"]
            if dom41 is None or rec41["assists"] < max(ASSIST_SOURCE_MIN, 4):
                continue
            share41 = 100.0 * rec41[dom41] / rec41["assists"]
            if share41 < 60.0:
                continue
            add(side, "támadás", "Gól-előkészítés változatossága",
                f"a gólpasszaink {share41:.0f}%-a {_lbl41[dom41]} jön — "
                "kiszámítható a gól-előkészítés, egy forrás elvételével "
                "megfogható",
                _drill41[dom41])
    except Exception:
        pass

    # 42) Labdabiztonság: ha egy játékosunk feltűnően sok labdát elveszít
    # (4+ eladás, és a csapat eladásainak jó része tőle), névre szóló
    # labdabiztonság-gyakorlás.
    try:
        from .defense import turnover_players
        tp42 = turnover_players(match, config)
        for side in ("home", "away"):
            rec42 = tp42[side]
            if rec42["total"] < 6 or not rec42["players"]:
                continue
            top42 = rec42["players"][0]
            if top42["losses"] < 4 \
                    or top42["losses"] / rec42["total"] < 0.35:
                continue
            who42 = (f"{top42['jersey']}-es" if top42["jersey"] is not None
                     else f"{top42['player_id']}. játékos")
            add(side, "támadás", "Labdabiztonság",
                f"a(z) {who42} veszíti a legtöbb labdát "
                f"({top42['losses']} eladás a csapat {rec42['total']}-ből) "
                "— rá fognak presselni",
                "labdabiztonság-gyakorlat névre szólóan: átvétel nyomás "
                "alatt, testes fedezés, döntéshozatal 1-1-ben; kikényszerí"
                "tett présben rövid, biztos megoldások")
    except Exception:
        pass

    # 43) Második roham: ha a kimaradt lövések (6+) után ritkán megyünk a
    # lepattanóra (8% alatt), a második esélyeket adjuk el — a beállós
    # lepattanó-harcot és a lövés utáni bemozgást kell gyakorolni.
    try:
        from .attack_types import SECOND_CHANCE_MIN, second_chance
        sc43 = second_chance(match, config)
        for side in ("home", "away"):
            rec43 = sc43[side]
            if rec43["misses"] < max(6, SECOND_CHANCE_MIN) \
                    or rec43["rebound_pct"] is None \
                    or rec43["rebound_pct"] > 8.0:
                continue
            add(side, "támadás", "Második roham",
                f"a kimaradt lövések után csak {rec43['rebound_pct']:.0f}%-ban "
                f"szerezzük vissza a lepattanót ({rec43['second_chances']}/"
                f"{rec43['misses']}) — a második esélyeket eldobjuk",
                "lepattanó-gyakorlat: beálló és szélső bemozgás a lövés "
                "pillanatában, kiharcolt lepattanó után azonnali második "
                "befejezés; lövés-blokk után a támadó visszaszerzés 1-1-ben")
    except Exception:
        pass

    # 44) Kezdés: ha a meccs nyitányát rendre elveszítjük (a korai — első 6
    # gólos — mérleg 2+ góllal negatív), a koncentrált, tervezett kezdést
    # kell gyakorolni (bemelegített első támadások, kész nyitó-figurák).
    try:
        from .momentum import opening_profile
        op44 = opening_profile(match, config)
        for side in ("home", "away"):
            rec44 = op44[side]
            if rec44["scores_first"] is None \
                    or rec44["early_goals_seen"] < 4:
                continue
            if rec44["early_for"] - rec44["early_against"] > -2:
                continue
            add(side, "támadás", "Kezdés",
                f"a meccs nyitányát elveszítjük (korai mérleg "
                f"{rec44['early_for']}–{rec44['early_against']} az első "
                "gólokban) — lassan lendülünk játékba",
                "tervezett kezdés: alaposan bemelegített első támadások, "
                "2-3 begyakorolt nyitó-figura az első percekre, és "
                "koncentrációs rutin az első sípszótól (ne kelljen "
                "'belerázódni' a meccsbe)")
    except Exception:
        pass

    # 45) Lövőerő-esés: ha a 2. félidőre érdemben lassulnak a lövéseink
    # (fáradás-jel), lövőerő-állóképességet kell építeni.
    try:
        from .event_detection import FADE_DROP_PCT, shot_speed_fade
        sf45 = shot_speed_fade(match, config)
        for side in ("home", "away"):
            rec45 = sf45[side]
            if rec45["drop_pct"] is None or rec45["drop_pct"] < FADE_DROP_PCT:
                continue
            add(side, "kondíció", "Lövőerő-állóképesség",
                f"a lövés-sebességünk a 2. félidőre {rec45['drop_pct']:.0f}%-ot "
                f"esik ({rec45['fh_avg_kmh']:.0f} → {rec45['sh_avg_kmh']:.0f} "
                "km/h) — fáradó karral fejezzük be a meccset",
                "lövőerő-állóképesség: kapura lövés sorozatban FÁRADT "
                "állapotban (kör-edzés után azonnal), erős-kar munka "
                "(medicinlabda-dobások), és a hajrá-lövők tudatos "
                "pihentetése a meccs közepén")
    except Exception:
        pass

    # 46) Gól-koncentráció: ha a góljaink zöme (5+ gólból 40%+) egy embertől
    # jön, az ellenfél őt fogja kikapcsolni — másodlagos befejezőket kell
    # építeni, hogy a csapat ne álljon le vele együtt.
    try:
        from .event_detection import goal_concentration
        gc46 = goal_concentration(match, config)
        for side in ("home", "away"):
            rec46 = gc46[side]
            if not rec46["concentrated"]:
                continue
            top46 = rec46["scorers"][0]
            add(side, "támadás", "Gól-eloszlás",
                f"a góljaink {rec46['top_share_pct']:.0f}%-át egy játékos "
                f"(a {top46['player_id']}. jelű) szerzi — ha őt lefogják, "
                "leáll a támadójátékunk",
                "másodlagos befejezők építése: a fő lövő elzáróként/"
                "előkészítőként is játsszon (2. hullám lövések), a szélsők "
                "és a beálló kapjanak kidolgozott befejezés-helyzeteket; "
                "gyakorlás emberfogás ellen, amikor a fő lövő ki van véve")
    except Exception:
        pass

    # 47) Támogatás-távolság: ha a labdásunk rendre magára marad (átlag 7 m+
    # vagy 35%+ izolált kocka), a présjáték szétszed minket — a labda
    # melletti bemozgást kell gyakorolni.
    try:
        from .decisions import (SUPPORT_ISO_M, SUPPORT_MIN_FRAMES,
                                support_distance)
        sd47 = support_distance(match, config)
        for side in ("home", "away"):
            rec47 = sd47[side]
            if rec47["avg_m"] is None or rec47["frames"] < SUPPORT_MIN_FRAMES:
                continue
            if rec47["avg_m"] < SUPPORT_ISO_M and rec47["iso_pct"] < 35.0:
                continue
            add(side, "támadás", "Támogató mozgás",
                f"a labdás játékosunk magára marad (a legközelebbi társ "
                f"átlag {rec47['avg_m']:.1f} m-re, az idő "
                f"{rec47['iso_pct']:.0f}%-ában izolált) — présben nincs "
                "passzopciónk",
                "támogató bemozgás gyakorlás: a labda melletti két játékos "
                "mindig passztávolságban (4-5 m), üres oldali beindulás a "
                "labdás felé présnél; 3-2-1 létszámfölényes kijátszás "
                "présnyomás alatt")
    except Exception:
        pass

    # 48) Területi fölény: ha a birtoklásunk a saját térfelünkön ragad
    # (45% alatti elöl-arány), a labdakihozatalt kell gyakorolni — prés
    # ellen nem jutunk el a kapuig.
    try:
        from .tactics import TILT_LOW_PCT, TILT_MIN_FRAMES, field_tilt
        ft48 = field_tilt(match, config)
        for side in ("home", "away"):
            rec48 = ft48[side]
            if rec48["tilt_pct"] is None \
                    or rec48["frames"] < TILT_MIN_FRAMES \
                    or rec48["tilt_pct"] > TILT_LOW_PCT:
                continue
            add(side, "támadás", "Labdakihozatal",
                f"a birtoklásunk csak {rec48['tilt_pct']:.0f}%-ban zajlik az "
                "ellenfél térfelén — a saját térfelünkön ragadunk, a prés "
                "megfog minket",
                "kihozatal-gyakorlás prés ellen: kapus + 3 hátsó ember "
                "kijátszás létszámhátrányban, hosszú indítás a szélsőnek "
                "mint szelep, és a középső átlövő visszalépő segítsége; "
                "cél: 10 mp alatt átérni a félpályán")
    except Exception:
        pass

    # 49) Védelmi tömörség: ha a falunk széthúzott (a közép nyitva), a
    # belső zárást kell gyakorolni — betörésekből és beállóból kapunk.
    try:
        from .defense import (DEF_WIDTH_MIN_FRAMES, DEF_WIDTH_WIDE_M,
                              defensive_width)
        dw49 = defensive_width(match, config)
        for side in ("home", "away"):
            rec49 = dw49[side]
            if rec49["avg_width_m"] is None \
                    or rec49["frames"] < DEF_WIDTH_MIN_FRAMES \
                    or rec49["avg_width_m"] < DEF_WIDTH_WIDE_M:
                continue
            add(side, "védekezés", "Fal-tömörség",
                f"a falunk széthúzott (átlag {rec49['avg_width_m']:.0f} m "
                "széles) — a közép nyitva: betörésből és beállóból "
                "kaphatunk",
                "tömörség-gyakorlás: a fal a labda oldalára záródik "
                "(labda-oldali segítség), a két belső védő váll-váll "
                "mellett; árnyék-védekezés szűkülő folyosóval, beálló-"
                "leválás elleni kommunikáció")
    except Exception:
        pass

    # 50) Engedett lövésminőség: ha a falunk átlagosan nagy értékű (ziccer-
    # közeli) lövéseket enged (8+ kapott lövésből 0,38+ xG/lövés), a
    # helyzet-megelőzést kell gyakorolni — a kapus egyedül kevés.
    try:
        from .defense import defense_analysis
        da50 = defense_analysis(match, config)
        for side in ("home", "away"):
            rec50 = da50[side]
            n50 = rec50["shots_against"]
            if n50 < 8:
                continue
            avg50 = float(rec50["xg_against"]) / n50
            if avg50 < 0.38:
                continue
            add(side, "védekezés", "Ziccer-megelőzés",
                f"a kapott lövéseink átlagos értéke magas ({avg50:.2f} "
                "xG/lövés) — a falunk nagy helyzetekbe engedi az ellenfelet",
                "ziccer-megelőzés: a betörési sávok zárása (segítő védő "
                "korai becsúszása), beálló-fogás testtel, a szélső-beadás "
                "levegőben történő megzavarása; a fal együtt mozog, hogy "
                "lövés csak kintről, nyomás alatt jöhessen")
    except Exception:
        pass

    # 51) Passz-tempó: ha állva, lassan járatjuk a labdát (12 passz/perc
    # alatt), a fal békében felállhat ellenünk — a labdajáratás sebességét
    # kell növelni.
    try:
        from .tactics import (PT_MIN_POSS_S, PT_SLOW_PER_MIN, pass_tempo)
        pt51 = pass_tempo(match, config)
        for side in ("home", "away"):
            rec51 = pt51[side]
            if rec51["per_min"] is None \
                    or rec51["poss_s"] < PT_MIN_POSS_S \
                    or rec51["per_min"] > PT_SLOW_PER_MIN:
                continue
            add(side, "támadás", "Labdajáratás-tempó",
                f"állva járatjuk a labdát ({rec51['per_min']:.0f} "
                "passz/perc) — a fal békében felállhat, kiszámíthatóak "
                "vagyunk",
                "tempó-gyakorlás: kétérintéses járatás-játék (max 1 mp a "
                "labdával), oldalváltás 3 passzon belül kötelezően, "
                "passz-után-mozgás (give-and-go) minden átadásnál; "
                "büntető-kör, ha a labda megáll")
    except Exception:
        pass

    # 52) Falba lövés: ha a lövéseink nagy része (4+ blokkból 20%+) az
    # ellenfél blokkján akad el, a lövés-előkészítést kell gyakorolni.
    try:
        from .defense import (BLOCKED_HIGH_PCT, BLOCKED_MIN,
                              blocked_shot_rate)
        br52 = blocked_shot_rate(match, config)
        for side in ("home", "away"):
            rec52 = br52[side]
            if rec52["blocked"] < BLOCKED_MIN \
                    or rec52["blocked_pct"] is None \
                    or rec52["blocked_pct"] < BLOCKED_HIGH_PCT:
                continue
            add(side, "támadás", "Lövés-előkészítés",
                f"a lövés-kísérleteink {rec52['blocked_pct']:.0f}%-a "
                f"blokkon akad el ({rec52['blocked']}/"
                f"{rec52['attempts']}) — a falba lövünk",
                "lövés-előkészítés: elzárás a lövő elé (a blokkolót "
                "kivenni), lövőcsel után elmozdulás egy fél lépéssel, "
                "átemelés/bevetődés mint alternatíva; átlövés CSAK "
                "tiszta helyzetből — falba lövésért büntető-kör")
    except Exception:
        pass

    # 53) Szerzés-magasság: ha a szerzéseink kizárólag hátul születnek
    # (6+ szerzésből 10% alatti elöl-arány), a letámadás mint fegyver
    # hiányzik — az elöl-zavarást kell gyakorolni.
    try:
        from .defense import STEAL_HEIGHT_MIN, steal_height
        st53 = steal_height(match, config)
        for side in ("home", "away"):
            rec53 = st53[side]
            if rec53["high_pct"] is None \
                    or rec53["steals"] < max(6, STEAL_HEIGHT_MIN) \
                    or rec53["high_pct"] > 10.0:
                continue
            add(side, "védekezés", "Letámadás",
                f"a szerzéseink csak {rec53['high_pct']:.0f}%-a születik "
                f"elöl ({rec53['high_steals']}/{rec53['steals']}) — az "
                "ellenfél építkezését nem zavarjuk",
                "letámadás-gyakorlás: 2-3 perces magas-prés szakaszok "
                "(a passzsáv elvétele, a visszapassz provokálása), "
                "jelre induló váltás mély falra; kis pályás 3-3 prés-játék "
                "szerzés-pontokkal")
    except Exception:
        pass

    # 54) Passz-hossz: ha hosszú passzokra épül a játékunk (15+ passzból
    # 30%+ 10 m fölötti) ÉS sokat adunk el, a passz-szerkezetet kell
    # biztonságosabbra hangolni.
    try:
        from .event_detection import (PLEN_LONG_PCT, PLEN_MIN_PASSES,
                                      pass_length)
        pl54 = pass_length(match, config)
        for side in ("home", "away"):
            rec54 = pl54[side]
            if rec54["long_pct"] is None \
                    or rec54["passes"] < PLEN_MIN_PASSES \
                    or rec54["long_pct"] < PLEN_LONG_PCT:
                continue
            # Csak akkor javaslat, ha az eladások is jelzik a kockázatot.
            from .defense import turnover_zones
            tz54 = turnover_zones(match, config)[side]
            if tz54["total"] < 6:
                continue
            add(side, "támadás", "Passz-szerkezet",
                f"a passzaink {rec54['long_pct']:.0f}%-a hosszú (10 m+), és "
                f"{tz54['total']} labdát adtunk el — a hosszú labda a fő "
                "kockázati forrásunk",
                "passz-szerkezet gyakorlás: hosszú passz csak tiszta "
                "sávba (a védő mögé, nem mellé), egyébként két rövidből "
                "épülő oldalváltás; passz-után-mozgás, hogy mindig legyen "
                "rövid opció")
    except Exception:
        pass

    # 55) Lövés-időzítés: ha rendre kivárunk (5+ lőtt támadásból 22+ mp-es
    # átlag lövésig-idő), a támadás-lezárást kell gyakorolni — a passzív
    # jel és a kapkodás ellenünk dolgozik.
    try:
        from .attack_types import (SHTIM_LATE_AVG_S, SHTIM_MIN_SHOTS,
                                   shot_timing)
        st55 = shot_timing(match, config)
        for side in ("home", "away"):
            rec55 = st55[side]
            if rec55["avg_s"] is None \
                    or rec55["shots"] < SHTIM_MIN_SHOTS \
                    or rec55["avg_s"] < SHTIM_LATE_AVG_S:
                continue
            add(side, "támadás", "Támadás-lezárás",
                f"átlag {rec55['avg_s']:.0f} mp után jutunk lövésig — a "
                "támadásaink elhúzódnak, a passzív jel és a kényszerű "
                "lövés fenyeget",
                "támadás-lezárás gyakorlás: 25 mp-es órával játszott "
                "támadások (le kell zárni előtte), a 15. mp-től kötelező "
                "befejezés-kezdeményezés (betörés/elzárás-lövés), és "
                "kész 'utolsó 5 mp' figura a kényszerhelyzetre")
    except Exception:
        pass

    # 56) Védekezés-fellazulás: ha a falunk a 2. félidőre érdemben lazul
    # (0,5 m+), a védekezés-állóképességet és a hajrá-fegyelmet kell
    # építeni — a meccs végi szabad lövők ebből születnek.
    try:
        from .defense import (PRESSURE_FADE_LOOSEN_M,
                              PRESSURE_FADE_MIN_FRAMES, pressure_fade)
        pf56 = pressure_fade(match, config)
        for side in ("home", "away"):
            rec56 = pf56[side]
            if rec56["loosen_m"] is None \
                    or rec56["fh_frames"] < PRESSURE_FADE_MIN_FRAMES \
                    or rec56["loosen_m"] < PRESSURE_FADE_LOOSEN_M:
                continue
            add(side, "védekezés", "Védekezés-állóképesség",
                f"a falunk a 2. félidőre fellazul (átlag "
                f"{rec56['fh_m']:.1f} → {rec56['sh_m']:.1f} m a labdástól) "
                "— a hajrában szabad lövőket hagyunk",
                "védekezés-állóképesség: hosszú (3-4 perces) folyamatos "
                "védekezés-szakaszok fáradtan (kör-edzés után), kilépés-"
                "visszazárás sorozatban, és a hajrá-fegyelem rögzítése — "
                "az utolsó 10 percben plusz kommunikáció, korábbi "
                "védő-csere")
    except Exception:
        pass

    # 57) Időkérés-forgatókönyv: ha az időkéréseink rendre nem hoznak
    # fordulatot (2+ hatástalan, és több, mint a sikeres), az időkérés
    # utáni újraindulást kell begyakorolni.
    try:
        from .stoppages import timeout_record
        tr57 = timeout_record(match, config)
        for side in ("home", "away"):
            rec57 = tr57[side]
            if rec57["failed"] < 2 or rec57["failed"] <= rec57["broke"]:
                continue
            add(side, "taktika", "Időkérés-forgatókönyv",
                f"az időkéréseink nem hoznak fordulatot ({rec57['failed']}/"
                f"{rec57['broke'] + rec57['failed']} hatástalan) — a "
                "megszakítás után ugyanúgy kapjuk a gólokat",
                "időkérés-forgatókönyv: minden időkéréshez KÉSZ első "
                "védekezés (ki kit fog, milyen fal) és kész első támadás "
                "(begyakorolt figura); az időkérés utáni 2 percet külön "
                "gyakorold edzésen sípszóra indítva")
    except Exception:
        pass

    # 58) Labdabiztonság-esés: ha a 2. félidőre érdemben nő az eladás-
    # ütemünk (+0,2/perc), a fáradt kéz labdabiztonságát kell építeni.
    try:
        from .defense import TURNOVER_FADE_RISE_PER_MIN, turnover_fade
        tf58 = turnover_fade(match, config)
        for side in ("home", "away"):
            rec58 = tf58[side]
            if rec58["rise_per_min"] is None \
                    or rec58["rise_per_min"] < TURNOVER_FADE_RISE_PER_MIN:
                continue
            add(side, "támadás", "Labdabiztonság fáradtan",
                f"a 2. félidőre megnő az eladás-ütemünk "
                f"({rec58['fh_per_min']:.1f} → {rec58['sh_per_min']:.1f} "
                "eladás/perc birtoklás) — fáradtan kienged a kezünk",
                "labdabiztonság fáradtan: passz- és átvétel-gyakorlatok "
                "kör-edzés UTÁN (magas pulzuson), kétlabdás járatás, "
                "présnyomásos 5-5 a edzés végén; a hajrá-felállásban a "
                "legbiztosabb kezű játékosok kapják a labdát")
    except Exception:
        pass

    # 346) Fáradt-fal poszt: ha a falunk a második félidőre egy poszt
    # ellen leül, csere- és kondíció-terv kell arra a sávra.
    try:
        from .defense import tired_conceder_roles
        tcr346 = tired_conceder_roles(match, config)
        for side in ("home", "away"):
            rec346 = tcr346[side]
            if rec346.get("verdict") is None:
                continue
            add(side, "védekezés", "Második félidőre leülő sáv",
                f"a falunk a második félidőre a(z) "
                f"{rec346['main_role']} poszt ellen ül le "
                f"({rec346['fh']} → {rec346['sh']} kapott gól) — a "
                "felkészült ellenfél a szünet után pont oda fog "
                "nyitni",
                "sáv-frissítés a második félidőre: tervezett "
                "védő-csere a leülő sávban a 40. perc körül, "
                "kondicionális blokk a belső védőknek, és a "
                "besegítés-rend fáradt lábakkal is videóról",
                )
    except Exception:
        pass

    # 345) Fáradt-lövő poszt: ha egy posztunk lövései a második
    # félidőre szétmennek, fáradt célzás-blokk és átosztás kell.
    try:
        from .xg import tired_shooter_roles
        fsa345 = tired_shooter_roles(match, config)
        for side in ("home", "away"):
            rec345 = fsa345[side]
            if rec345.get("verdict") is None:
                continue
            add(side, "fáradás", "Fáradtan szétmenő lövés",
                f"a(z) {rec345['main_role']} posztunk kaput "
                "elkerülő lövései a második félidőre megugranak "
                f"({rec345['fh']} → {rec345['sh']}) — fáradtan "
                "szétmegy a lövése, és az ellenfél rá fogja engedni",
                "fáradt célzás-blokk a posztnak: kapura lövés magas "
                "pulzuson (kör-edzés után), sarok-célzás kapussal, "
                "és a második félidei figurákban a befejezés "
                "átosztása frissebb posztra",
                )
    except Exception:
        pass

    # 344) Fáradt-eladó poszt: ha egy posztunk eladásai a második
    # félidőre megugranak, terhelés-menedzsment és fáradt
    # labdabiztonság kell.
    try:
        from .decisions import tired_turnover_roles
        fto344 = tired_turnover_roles(match, config)
        for side in ("home", "away"):
            rec344 = fto344[side]
            if rec344.get("verdict") is None:
                continue
            add(side, "fáradás", "Fáradtan kinyíló kéz",
                f"a(z) {rec344['main_role']} posztunk eladásai a "
                f"második félidőre megugranak ({rec344['fh']} → "
                f"{rec344['sh']}) — fáradtan nála nyílik ki a kéz, "
                "és az ellenfél pressze pontosan őt fogja keresni",
                "fáradt labdabiztonság a posztnak: passz- és "
                "átvétel-gyakorlat magas pulzuson (kör-edzés után), "
                "korábbi pihentetés-blokk a második félidőben, és "
                "eladás utáni azonnali visszatámadás-szabály",
                )
    except Exception:
        pass

    # 343) Hátrapassz-poszt: ha a játékunk mindig ugyanannál a
    # posztnál fordul vissza, a pressz ellenünk jutalmat hoz.
    try:
        from .attack_types import (BPR_SHARE_PCT,
                                   backward_pass_roles)
        bpr343 = backward_pass_roles(match, config)
        for side in ("home", "away"):
            rec343 = bpr343[side]
            if rec343.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztnál visszaforduló játék",
                f"a hátra-passzaink {rec343['share_pct']:.0f}%-a "
                f"a(z) {rec343['main_role']} posztunknál történik "
                f"({rec343['passes']} hátra-passzból; "
                f"{BPR_SHARE_PCT:.0f}% fölött már minta) — nyomás "
                "alatt nála fordul vissza a lendület, és az "
                "ellenfél pressze jutalmat kap",
                "előre-játék bátorság a posztnak: nyomás alatti "
                "betörés-döntés gyakorlása (1-1 után passz előre), "
                "hátra-passz csak kettős nyomásnál szabály a "
                "kisjátékokban, és a lendület-megtartó átadások "
                "videó-elemzése",
                )
    except Exception:
        pass

    # 342) Térnyerő-poszt: ha a térnyerésünk egy poszt lábán van, a
    # felhozatal-teher aránytalan, és egy korai kontakt lefékez.
    try:
        from .decisions import TNR_SHARE_PCT, ball_carrier_roles
        tnr342 = ball_carrier_roles(match, config)
        for side in ("home", "away"):
            rec342 = tnr342[side]
            if rec342.get("verdict") is None:
                continue
            add(side, "támadás", "Egy lábon álló térnyerés",
                f"a térnyerésünk {rec342['share_pct']:.0f}%-a a(z) "
                f"{rec342['main_role']} posztunk lábán van "
                f"({rec342['meters']:.0f} labdás előre-méterből; "
                f"{TNR_SHARE_PCT:.0f}% fölött már minta) — egy "
                "korai kontakt rá az egész felhozatalunkat lefékezi",
                "térnyerés-teher elosztása: második labdavivő "
                "gyakorlása, korai kontakt elleni átadás (ütközés "
                "előtti leadás), és a szélső-felhozatal mint B-út",
                )
    except Exception:
        pass

    # 341) Előnyben-poszt: ha a vezetés-tartásunk egy posztra épül,
    # az ellenfél a kivételével gyorsan visszajön.
    try:
        from .momentum import LGR_SHARE_PCT, lead_scorer_roles
        lgr341 = lead_scorer_roles(match, config)
        for side in ("home", "away"):
            rec341 = lgr341[side]
            if rec341.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztra épülő előny-tartás",
                f"vezetésnél a góljaink {rec341['share_pct']:.0f}"
                f"%-a a(z) {rec341['main_role']} posztról jön "
                f"({rec341['goals']} előnyben lőtt gólból; "
                f"{LGR_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél az ő kivételével gyorsan visszajöhet",
                "előny-tartás két lábon: vezetésnél a figurák két "
                "befejező posztra is kifuthassanak, időhúzás-figura "
                "B-befejezővel, és a kulcs-emberünk tehermentesítése"
                " elzárásokkal",
                )
    except Exception:
        pass

    # 340) Előkészítő-poszt: ha a lövéseinket mindig ugyanaz a
    # posztunk készíti elő, egy sávzárás az egész lövő-játékunkat
    # lekapcsolja.
    try:
        from .attack_types import EPR_SHARE_PCT, last_pass_roles
        epr340 = last_pass_roles(match, config)
        for side in ("home", "away"):
            rec340 = epr340[side]
            if rec340.get("verdict") is None:
                continue
            add(side, "támadás", "Egy kézen futó előkészítés",
                f"a lövéseinket {rec340['share_pct']:.0f}%-ban a(z)"
                f" {rec340['main_role']} posztunk készíti elő "
                f"({rec340['passes']} előkészítő passzból; "
                f"{EPR_SHARE_PCT:.0f}% fölött már minta) — az ő "
                "sávjának zárásával a lövőink előkészítés nélkül "
                "maradnak",
                "második előkészítő építése: a figurák utolsó "
                "passza két posztról is jöhessen (szélső-visszatett,"
                " beálló-kioldás), és sávzárás elleni kijátszás "
                "gyakorlása 4-4-ben",
                )
    except Exception:
        pass

    # 339) Indító-poszt: ha a támadásaink mindig ugyanannál a
    # posztnál indulnak, egy jó pressz az egész szervezésünket
    # megfojtja.
    try:
        from .roles import ATS_SHARE_PCT, attack_starter_roles
        ats339 = attack_starter_roles(match, config)
        for side in ("home", "away"):
            rec339 = ats339[side]
            if rec339.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztnál induló szervezés",
                f"a támadásaink {rec339['share_pct']:.0f}%-a a(z) "
                f"{rec339['main_role']} posztnál indul "
                f"({rec339['attacks']} szakaszból; "
                f"{ATS_SHARE_PCT:.0f}% fölött már minta) — egy "
                "korai pressz a felhozónkra az egész szervezésünket"
                " megfojtja",
                "második labdafelhozó: pressz elleni felhozatal "
                "gyakorlása két indítóval, hátra-passz biztonsági "
                "szelep a kapusnak, és a szélső-felhozatal mint "
                "B-terv begyakorolva",
                )
    except Exception:
        pass

    # 338) Beállóőr-poszt: ha a beálló-őrzésünk egy posztunkon áll,
    # egy elzárással kihúzható — kell a váltás-szabály.
    try:
        from .defense import PGR_SHARE_PCT, pivot_guard_roles
        pgr338 = pivot_guard_roles(match, config)
        for side in ("home", "away"):
            rec338 = pgr338[side]
            if rec338.get("verdict") is None:
                continue
            add(side, "védekezés", "Egy emberen álló beálló-őrzés",
                f"a beálló-őrzésünk {rec338['share_pct']:.0f}%-ban "
                f"a(z) {rec338['main_role']} posztunkon áll "
                f"({PGR_SHARE_PCT:.0f}% fölött már minta) — egy "
                "elzárással kihúzható, és a beálló felszabadul",
                "beálló-őrzés váltás-szabállyal: elzárásnál a "
                "szomszéd védő veszi át a beállót (hangos jelzéssel),"
                " 2-2 elleni elzárás-védés kisjátékban, és a "
                "besegítés rendje videóról",
                )
    except Exception:
        pass

    # 337) Kilépő-poszt: ha a falunk mindig ugyanannál a posztnál
    # lép ki, a mögötte nyíló teret a felkészült ellenfél bejátssza.
    try:
        from .defense import advanced_defender_roles
        adr337 = advanced_defender_roles(match, config)
        for side in ("home", "away"):
            rec337 = adr337[side]
            if rec337.get("verdict") is None:
                continue
            add(side, "védekezés", "Kilépő mögötti tér",
                f"a falunk a(z) {rec337['main_role']} posztnál lép "
                f"ki (a társaknál {rec337['gap_m']:.1f} m-rel "
                "előrébb) — a kilépőnk mögötti teret a felkészült "
                "ellenfél elzárással és befutóval bünteti",
                "kilépés mögötti biztosítás: a kilépő melletti két "
                "védő zárás-gyakorlata (csúszás a beálló elé), "
                "elzárás-lekapcsolás a kilépőnek, és 2 az 1 elleni "
                "helyzetek védése kisjátékban",
                )
    except Exception:
        pass

    # 336) Ziccerhagyó-poszt: ha a ziccereinket mindig ugyanaz a
    # posztunk hagyja ki, a helyzeteink egy része kárba vész.
    try:
        from .xg import MCR_SHARE_PCT, missed_chance_roles
        mcr336 = missed_chance_roles(match, config)
        for side in ("home", "away"):
            rec336 = mcr336[side]
            if rec336.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztnál kieső ziccerek",
                f"a kihagyott ziccereink {rec336['share_pct']:.0f}"
                f"%-a a(z) {rec336['main_role']} posztnál esik "
                f"({rec336['misses']} kihagyásból; "
                f"{MCR_SHARE_PCT:.0f}% fölött már minta) — a "
                "kialakított helyzeteink egy része nála kárba vész",
                "befejezés-gyakorlás a posztnak: ziccer-sorozatok "
                "kapussal (fáradtan is, kör-edzés után), "
                "hatosról-fordulós és ejtés-variációk, valamint "
                "önbizalom-építés: sikeres sorozattal záruljon",
                )
    except Exception:
        pass

    # 335) Blokkolt-poszt: ha egy posztunk lövéseit rendre blokkolják,
    # a lövés-előkészítés hiányzik — elmozgatás nélkül falba lövünk.
    try:
        from .defense import BSR_SHARE_PCT, blocked_shooter_roles
        bsr335 = blocked_shooter_roles(match, config)
        for side in ("home", "away"):
            rec335 = bsr335[side]
            if rec335.get("verdict") is None:
                continue
            add(side, "támadás", "Falba lövő poszt",
                f"a blokkolt lövéseink {rec335['share_pct']:.0f}%-a "
                f"a(z) {rec335['main_role']} posztról jön "
                f"({rec335['blocks']} blokkból; "
                f"{BSR_SHARE_PCT:.0f}% fölött már minta) — az "
                "előkészítetlen lövésünk falba megy, és onnan "
                "kontra indul",
                "lövés-előkészítés a posztnak: elzárás-lövés "
                "kombinációk, lövőcsel a záró védőre, és "
                "lövés-szelekció videóról — zárt sávba nem lövünk, "
                "hanem tovább járatjuk",
                )
    except Exception:
        pass

    # 334) Hetesdobó-poszt: ha a heteseinket mindig ugyanaz a posztunk
    # dobja, az ellenfél kapusa egyetlen dobó szokásaira készülhet.
    try:
        from .rules import STK_SHARE_PCT, seven_taker_roles
        stk334 = seven_taker_roles(match, config)
        for side in ("home", "away"):
            rec334 = stk334[side]
            if rec334.get("verdict") is None:
                continue
            add(side, "támadás", "Egy dobóra épülő hetes",
                f"a heteseinket {rec334['share_pct']:.0f}%-ban a(z) "
                f"{rec334['main_role']} posztunk dobja "
                f"({rec334['attempts']} hetesből; "
                f"{STK_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél kapusa egyetlen dobó szokásaira készülhet",
                "második kijelölt hetes-dobó: heti hetes-verseny a "
                "kijelöléshez, a fő dobónak pedig irány-variálás "
                "(kapus-mozgásra dobás gyakorlása) videó-visszajelzéssel",
                )
    except Exception:
        pass

    # 333) Újrakezdő-poszt: ha a szünet utáni rajtunk egy posztra
    # épül, a felkészült ellenfél a második félidőt az ő fogásával
    # kezdi.
    try:
        from .momentum import SSR_SHARE_PCT, second_start_roles
        ssr333 = second_start_roles(match, config)
        for side in ("home", "away"):
            rec333 = ssr333[side]
            if rec333.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztra épülő második rajt",
                f"a szünet utáni góljaink {rec333['share_pct']:.0f}"
                f"%-a a(z) {rec333['main_role']} posztról jön "
                f"({rec333['goals']} gól a második félidő első tíz "
                f"percében; {SSR_SHARE_PCT:.0f}% fölött már minta) "
                "— az ellenfél a szünetben pontosan tudja, kire "
                "álljon rá",
                "második félidei nyitó-forgatókönyv B-vel: az "
                "újrakezdés első három figurája két különböző "
                "befejező posztra megbeszélve, és a rajt-emberünk "
                "tehermentesítése elzárásokkal",
                )
    except Exception:
        pass

    # 332) Elzárt-poszt: ha egy védőnk rendre elakad az
    # elzárásokban, oda fogja hozni a figuráit minden ellenfél.
    try:
        from .defense import SDR_SHARE_PCT, screened_defender_roles
        sdr332 = screened_defender_roles(match, config)
        for side in ("home", "away"):
            rec332 = sdr332[side]
            if rec332.get("verdict") is None:
                continue
            add(side, "védekezés", "Elzárásban elakadó védő",
                f"az elzárások {rec332['share_pct']:.0f}%-ban a(z) "
                f"{rec332['main_role']} posztunkon lévő védőt "
                f"találják meg ({rec332['screens']} elakadásból; "
                f"{SDR_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél oda fogja hozni a figuráit",
                "elzárás-elleni csomag a védőnek: átcsúszás- és "
                "váltás-gyakorlat hangos kommunikációval, elzárás-"
                "felismerés videóról, és korai testkontakt az "
                "elzáróval, mielőtt beáll a pozíciója",
                )
    except Exception:
        pass

    # 331) Kettőzött-poszt: ha egy posztunkat rendre kettőzik, neki
    # lekapcsolódó társ és kettőzés-elleni leadás kell.
    try:
        from .defense import DTR_SHARE_PCT, doubled_target_roles
        dtr331 = doubled_target_roles(match, config)
        for side in ("home", "away"):
            rec331 = dtr331[side]
            if rec331.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztra járó kettőzés",
                f"az ellenfél kettőzései {rec331['share_pct']:.0f}"
                f"%-ban a(z) {rec331['main_role']} posztunkra "
                f"érkeznek ({DTR_SHARE_PCT:.0f}% fölött már minta) "
                "— a következő ellenfél is ezt a receptet fogja "
                "követni",
                "kettőzés-elleni csomag a posztnak: lekapcsolódó "
                "társ (mindig legyen leadási irány), egyérintős "
                "kijátszás kettőzés ellen 3-3-ban, és a kettőzés "
                "mögötti üres ember tudatos keresése videóról",
                )
    except Exception:
        pass

    # 330) Fáradó-poszt: ha egy posztunk tempója a második félidőre
    # rendre visszaesik, kondicionális blokk és korábbi pihentetés
    # kell neki.
    try:
        from .stats import FTR_DROP_PCT, fatigue_roles
        ftr330 = fatigue_roles(match, config)
        for side in ("home", "away"):
            rec330 = ftr330[side]
            if rec330.get("verdict") is None:
                continue
            add(side, "fáradás", "Második félidőre visszaeső poszt",
                f"a(z) {rec330['main_role']} posztunk tempója a "
                f"második félidőre −{rec330['drop_pct']:.0f}%-ot "
                f"esik ({FTR_DROP_PCT:.0f}% fölött már minta) — az "
                "ellenfél a szünet után pont az ő sávjában fog "
                "támadni",
                "kondicionális blokk a posztnak (ismételt sprint-"
                "állóképesség, második félidőt szimuláló fáradt "
                "játék-gyakorlat), és csere-terv: korábbi, rövidebb "
                "pihentetés az első félidőben",
                )
    except Exception:
        pass

    # 329) Passzív-poszt: ha a terméketlen támadásaink egy posztnál
    # halnak el, oda kész befejező megoldás kell a passzív jelzés
    # előttre.
    try:
        from .rules import PVR_SHARE_PCT, passive_holder_roles
        pvr329 = passive_holder_roles(match, config)
        for side in ("home", "away"):
            rec329 = pvr329[side]
            if rec329.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztnál elhaló támadás",
                f"a lövés nélküli hosszú támadásaink labdás idejének"
                f" {rec329['share_pct']:.0f}%-a a(z) "
                f"{rec329['main_role']} posztnál telik "
                f"({PVR_SHARE_PCT:.0f}% fölött már minta) — a "
                "passzív jelzés alatt nála ragad a labda, és onnan "
                "jön a kényszer-eladás",
                "passzív-protokoll: 25 másodperc után kötelező "
                "figura-indítás, a posztnak kész befejező megoldás "
                "(bejátszás vagy átlövés-elzárás), és 5-0-s "
                "időhúzás-elleni gyakorlás sípszóra",
                )
    except Exception:
        pass

    # 328) Rajt-poszt: ha a meccs-nyitásunk egy posztra épül, a
    # felkészült ellenfél az első perctől rá áll — kell a második
    # nyitó-megoldás.
    try:
        from .momentum import OSR_SHARE_PCT, opening_scorer_roles
        osr328 = opening_scorer_roles(match, config)
        for side in ("home", "away"):
            rec328 = osr328[side]
            if rec328.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztra épülő rajt",
                f"a meccs eleji góljaink {rec328['share_pct']:.0f}"
                f"%-a a(z) {rec328['main_role']} posztról jön "
                f"({rec328['goals']} gól az első tíz percben; "
                f"{OSR_SHARE_PCT:.0f}% fölött már minta) — a "
                "felkészült ellenfél az első perctől rá áll",
                "nyitó-forgatókönyv B-vel: az első öt figura előre "
                "megbeszélve két különböző befejező posztra, és a "
                "rajt-emberünk tehermentesítése elzárásokkal, ha "
                "kiemelt fogást kap",
                )
    except Exception:
        pass

    # 327) Kiszolgált-poszt: ha egy posztunk csak kiszolgálásból él,
    # a passzsáv-zárás ellen tervre van szüksége.
    try:
        from .roles import ASR_SHARE_PCT, assisted_scorer_roles
        asr327 = assisted_scorer_roles(match, config)
        for side in ("home", "away"):
            rec327 = asr327[side]
            if rec327.get("verdict") is None:
                continue
            add(side, "támadás", "Kiszolgálásból élő poszt",
                f"a kiszolgált góljaink {rec327['share_pct']:.0f}%-a"
                f" a(z) {rec327['main_role']} posztunkon fejeződik "
                f"be ({rec327['assisted']} asszisztos gólból; "
                f"{ASR_SHARE_PCT:.0f}% fölött már minta) — ha a "
                "felé futó passzt elvágják, a fő befejezőnk elhal",
                "önálló helyzet-teremtés a posztnak: 1-1 elleni "
                "betörés-gyakorlat, második bejátszási útvonal "
                "(hátoldali befutás, visszatett labda), és a "
                "figurákba beépített csere-célpont",
                )
    except Exception:
        pass

    # 326) Hajrákéz-poszt: ha a végjátékunk egy kézen fut, egy jó
    # kettőzés az egész záró tervünket megfojtja.
    try:
        from .momentum import CHR_SHARE_PCT, clutch_hog_roles
        chr326 = clutch_hog_roles(match, config)
        for side in ("home", "away"):
            rec326 = chr326[side]
            if rec326.get("verdict") is None:
                continue
            add(side, "fáradás", "Egy kézen futó végjáték",
                f"a végjátékunk labdás idejének "
                f"{rec326['share_pct']:.0f}%-a a(z) "
                f"{rec326['main_role']} posztunknál van "
                f"({CHR_SHARE_PCT:.0f}% fölött már minta) — egy jó "
                "hajrá-kettőzés az egész záró tervünket megfojtja",
                "második labdakihozó a hajrára: a záró figurák "
                "indítása két posztról is begyakorolva, kettőzés "
                "elleni kijátszás (hátoldali felfutás, beálló-"
                "leadás) a kulcs-kezünknek",
                )
    except Exception:
        pass

    # 325) Lágypassz-poszt: ha egy posztunk lágyan passzol, az ő
    # labdáiba az ellenfél beleér — passz-élesség a téma.
    try:
        from .decisions import SPS_SHARE_PCT, soft_pass_roles
        sps325 = soft_pass_roles(match, config)
        for side in ("home", "away"):
            rec325 = sps325[side]
            if rec325.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztról jövő lágy passzok",
                f"a lágy passzaink {rec325['share_pct']:.0f}%-a a(z)"
                f" {rec325['main_role']} posztról jön "
                f"({rec325['soft']} lágy passzból; "
                f"{SPS_SHARE_PCT:.0f}% fölött már minta) — az ő "
                "labdáiba az ellenfél beleér, és abból kontra indul",
                "passz-élesség a posztnak: csuklós, feszes átadás "
                "gyakorlása fáradtan is (kör-edzés után), pattintott"
                " és test melletti passz a beleérő védő ellen, és "
                "passzsáv-nyomás alatti 3-3",
                )
    except Exception:
        pass

    # 324) Sprint-poszt: ha a sprint-teher egy posztunkon áll, a
    # kontránk kiszámítható, és az az ember hamarabb fárad el.
    try:
        from .stats import SPR_SHARE_PCT, sprint_threat_roles
        spr324 = sprint_threat_roles(match, config)
        for side in ("home", "away"):
            rec324 = spr324[side]
            if rec324.get("verdict") is None:
                continue
            add(side, "fáradás", "Egy posztra jutó sprint-teher",
                f"a sprintjeink {rec324['share_pct']:.0f}%-át a(z) "
                f"{rec324['main_role']} posztunk futja "
                f"({rec324['sprints']} sprintből; "
                f"{SPR_SHARE_PCT:.0f}% fölött már minta) — a "
                "kontránk kiszámítható, és a motorunk hamarabb "
                "elfárad",
                "kontra-teher elosztása: második kifutó ember "
                "kijelölése és gyakorlása (két sávos lerohanás), a "
                "sprint-teher figyelése a cserék időzítésénél",
                )
    except Exception:
        pass

    # 323) Középkezdő-poszt: ha a középkezdésünk mindig ugyanannál a
    # posztnál indul, a felkészült ellenfél letámadása pont őt fogja.
    try:
        from .momentum import RTR_SHARE_PCT, restart_taker_roles
        rtr323 = restart_taker_roles(match, config)
        for side in ("home", "away"):
            rec323 = rtr323[side]
            if rec323.get("verdict") is None:
                continue
            add(side, "támadás", "Kiszámítható középkezdés",
                f"a kapott gól utáni középkezdésünk "
                f"{rec323['share_pct']:.0f}%-ban a(z) "
                f"{rec323['main_role']} posztnál indul "
                f"({rec323['takes']} átvételből; "
                f"{RTR_SHARE_PCT:.0f}% fölött már minta) — a "
                "felkészült ellenfél letámadása pont őt fogja le",
                "középkezdés-variációk: legalább két begyakorolt "
                "átvevő (poszt szerint is más), hátrafelé induló "
                "első passz letámadás ellen, és gyors középkezdés "
                "mint fegyver, ha az ellenfél lassan áll vissza",
                )
    except Exception:
        pass

    # 322) Forró-poszt: ha a sorozatainkat mindig ugyanaz a posztunk
    # lövi, az ellenfél az első gól után rá fog állni — kell a
    # második lendület-vivő.
    try:
        from .momentum import HHR_SHARE_PCT, hot_hand_roles
        hhr322 = hot_hand_roles(match, config)
        for side in ("home", "away"):
            rec322 = hhr322[side]
            if rec322.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztra épülő lendület",
                f"a gólsorozataink {rec322['share_pct']:.0f}%-a a(z)"
                f" {rec322['main_role']} posztról jön "
                f"({rec322['streak_goals']} sorozat-gólból; "
                f"{HHR_SHARE_PCT:.0f}% fölött már minta) — az első "
                "gólunk után az ellenfél pontosan tudja, kire "
                "álljon rá",
                "lendület-átadás gyakorlása: a sorozatban lévő "
                "emberről induló kijátszások (róla lekapcsolódó "
                "társ, elzárás neki, hogy másnak nyíljon tér), és "
                "második befejező kijelölése a forró szakaszokra",
                )
    except Exception:
        pass

    # 321) Hajráhiba-poszt: ha a hajrában mindig ugyanannál a
    # posztunknál megy el a labda, az ellenfél záró pressze oda jön.
    try:
        from .momentum import CTR_SHARE_PCT, clutch_turnover_roles
        ctr321 = clutch_turnover_roles(match, config)
        for side in ("home", "away"):
            rec321 = ctr321[side]
            if rec321.get("verdict") is None:
                continue
            add(side, "fáradás", "Egy posztnál elmenő hajrá-labda",
                f"a hajrá-eladásaink {rec321['share_pct']:.0f}%-a "
                f"a(z) {rec321['main_role']} posztnál történik "
                f"({rec321['turnovers']} eladás az utolsó öt "
                f"percben; {CTR_SHARE_PCT:.0f}% fölött már minta) — "
                "az ellenfél záró pressze pontosan oda fog jönni",
                "hajrá-labdabiztonság: a záró öt perc figuráiban a "
                "poszt tehermentesítése (korai leadás, kettős "
                "kijátszási irány), pressz elleni 6-6 fáradtan a "
                "edzés végén, és időkérés-terv a beszorult labdára",
                )
    except Exception:
        pass

    # 320) Eltűnő-poszt: ha egy posztunk termelése a második félidőre
    # elhal, a terhelés-menedzsment és a kondíció a téma.
    try:
        from .momentum import fading_scorer_roles
        fdp320 = fading_scorer_roles(match, config)
        for side in ("home", "away"):
            rec320 = fdp320[side]
            if rec320.get("verdict") is None:
                continue
            add(side, "fáradás", "Második félidőre eltűnő poszt",
                f"a(z) {rec320['main_role']} posztunk az első "
                f"félidőben él ({rec320['fh']} gól-részvétel), a "
                f"másodikra eltűnik ({rec320['sh']}) — a termelése "
                "fáradással vagy az ellenfél átállásával elhal",
                "terhelés-menedzsment a posztnak: korábbi, rövidebb "
                "pihentetés-blokkok az első félidőben, kondicionális "
                "blokk (ismételt sprint-állóképesség) az edzésen, és "
                "B-megoldás a második félidei figurákba",
                )
    except Exception:
        pass

    # 319) Csendtörő-poszt: ha a gólcsendjeinket mindig ugyanaz a
    # posztunk töri meg, a válság-megoldásunk kiszámítható és fogható.
    try:
        from .momentum import GCT_SHARE_PCT, drought_breaker_roles
        gct319 = drought_breaker_roles(match, config)
        for side in ("home", "away"):
            rec319 = gct319[side]
            if rec319.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztra futó válság-megoldás",
                f"a gólcsendjeinket {rec319['share_pct']:.0f}%-ban "
                f"a(z) {rec319['main_role']} posztunk töri meg "
                f"({rec319['breaks']} csend-törő gólból; "
                f"{GCT_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél a csendünk alatt pontosan tudja, kit "
                "fogjon",
                "válság-forgatókönyv B-vel: gólcsend-szituációs 6-6 "
                "(3 perc gól nélkül → kötelező figura), amelyben a "
                "befejezés más-más posztra van kiosztva, plusz "
                "hetes-kiharcolás mint biztonsági szelep",
                )
    except Exception:
        pass

    # 318) Pressz-poszt: ha szorításban mindig ugyanaz a posztunk
    # veszíti a labdát, az ellenfél kettőzése oda fog érkezni.
    try:
        from .decisions import PSR_SHARE_PCT, press_sensitive_roles
        psr318 = press_sensitive_roles(match, config)
        for side in ("home", "away"):
            rec318 = psr318[side]
            if rec318.get("verdict") is None:
                continue
            add(side, "támadás", "Szorításban ejtett labda egy poszton",
                f"a nyomott eladásaink {rec318['share_pct']:.0f}%-a "
                f"a(z) {rec318['main_role']} posztnál történik "
                f"({rec318['press_to']} nyomott eladásból; "
                f"{PSR_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél kettőzése pontosan oda fog érkezni",
                "nyomás alatti kiadás a posztnak: 1+1 elleni "
                "labdatartás szorításban, kettőzés elleni leadás "
                "(bejátszás, visszajátszás) és test-test elleni "
                "labdavédelem falra dolgozva",
                )
    except Exception:
        pass

    # 317) Labdatartó-poszt: ha a labda egy posztunknál ragad, oda
    # időzíti az ellenfél a kettőzést, és ott lassul a támadásunk.
    try:
        from .decisions import HTR_SHARE_PCT, hold_time_roles
        htr317 = hold_time_roles(match, config)
        for side in ("home", "away"):
            rec317 = htr317[side]
            if rec317.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztnál ragadó labda",
                f"a mért labdatartásunk {rec317['share_pct']:.0f}%-a "
                f"a(z) {rec317['main_role']} posztnál telik "
                f"({rec317['seconds']:.0f} mp-ből; "
                f"{HTR_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél oda időzíti a kettőzést, és ott lassul a "
                "támadásunk",
                "tempó-szabály a posztnak: két másodperces "
                "továbbítási limit a figurákban, egyérintős "
                "passz-körök és kettőzés elleni leadás-gyakorlat "
                "(bejátszás a beállónak, visszajátszás az üresnek)",
                )
    except Exception:
        pass

    # 316) Ziccer-poszt: ha a nagy helyzeteink egy posztnál alakulnak
    # ki, a helyzet-teremtésünk egysíkú, és egy besegítéssel lezárható.
    try:
        from .xg import BCR_SHARE_PCT, big_chance_roles
        bcr316 = big_chance_roles(match, config)
        for side in ("home", "away"):
            rec316 = bcr316[side]
            if rec316.get("verdict") is None:
                continue
            add(side, "támadás", "Egysíkú helyzet-teremtés",
                f"a ziccereink {rec316['share_pct']:.0f}%-a a(z) "
                f"{rec316['main_role']} posztnál alakul ki "
                f"({rec316['chances']} nagy helyzetből; "
                f"{BCR_SHARE_PCT:.0f}% fölött már minta) — egy jól "
                "időzített besegítés az egész helyzet-teremtésünket "
                "lezárja",
                "helyzet-teremtő variációk más posztokra: szélső "
                "befutások, második hullámos átlövés és hetes-"
                "kiharcolás gyakorlása, hogy a ziccer ne csak egy "
                "poszton születhessen",
                )
    except Exception:
        pass

    # 315) Pazarló-poszt: ha a mellé lövéseink egy posztra sűrűsödnek,
    # az ellenfél ráengedi a lövést, és a kidobásból minket kontráz.
    try:
        from .xg import WSR_SHARE_PCT, wasteful_shooter_roles
        wsr315 = wasteful_shooter_roles(match)
        for side in ("home", "away"):
            rec315 = wsr315[side]
            if rec315.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztra sűrűsödő pontatlanság",
                f"a kaput elkerülő lövéseink {rec315['share_pct']:.0f}"
                f"%-a a(z) {rec315['main_role']} posztról jön "
                f"({rec315['off_target']} mellé/blokkolt lövésből; "
                f"{WSR_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél ráengedi a lövést, és a kidobásból kontráz",
                "célzás-blokk a posztnak: kapura lövés fáradtan "
                "(kör-edzés után), sarok-célzás kapussal, és "
                "lövés-szelekció videóról — mellé lövés helyett "
                "inkább újraszervezés vagy bejátszás",
                )
    except Exception:
        pass

    # 314) Felzárkózás-poszt: ha hátrányból mindig ugyanaz a posztunk
    # ment minket, egy jó fogással beragasztható a hátrányunk.
    try:
        from .momentum import CBR_SHARE_PCT, comeback_carrier_roles
        cbr314 = comeback_carrier_roles(match, config)
        for side in ("home", "away"):
            rec314 = cbr314[side]
            if rec314.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztra futó felzárkózás",
                f"hátrányból a gól-részvételeink {rec314['share_pct']:.0f}"
                f"%-a a(z) {rec314['main_role']} posztról jön "
                f"({rec314['trailing']} hátrány-gól-részvételből; "
                f"{CBR_SHARE_PCT:.0f}% fölött már minta) — ha a "
                "mentő-emberünket kiveszik, a hátrányunk beragad",
                "hátrány-figurák második opcióval: a felzárkózó "
                "játékainkban kötelező kijátszani a mentő-poszt "
                "MELLETTI befejezőt is (bejátszás, hátoldali szélső), "
                "és 2 perces hátrány-szituációs 6-6 minden edzésen",
                )
    except Exception:
        pass

    # 313) Hajrá-poszt: ha a végjátékunk egy posztra fut ki, a záró
    # percekben egyetlen jó emberfogás megfojt minket.
    try:
        from .momentum import CSR_SHARE_PCT, clutch_scorer_roles
        csr313 = clutch_scorer_roles(match, config)
        for side in ("home", "away"):
            rec313 = csr313[side]
            if rec313.get("verdict") is None:
                continue
            add(side, "fáradás", "Egy posztra futó végjáték",
                f"a hajrá-góljaink {rec313['share_pct']:.0f}%-a a(z) "
                f"{rec313['main_role']} posztról esik "
                f"({rec313['goals']} hajrá-gólból; "
                f"{CSR_SHARE_PCT:.0f}% fölött már minta) — egy jó "
                "emberfogás a záró percekben megfojtja a támadásunkat",
                "hajrá-forgatókönyv B-vel: a záró öt perc figuráiban "
                "kötelező a másodlagos befejező is, és emberfogás "
                "elleni lekapcsolódás-gyakorlat (elzárás-átfutás, "
                "hátoldali befutás) a kulcs-emberünknek")
    except Exception:
        pass

    # 312) Emberhátrány-poszt: ha öt emberrel mindig ugyanaz a
    # posztunk vállal be, a hátrány-játékunk kiszámítható.
    try:
        from .rules import SHR_SHARE_PCT, shorthanded_shooter_roles
        shr312 = shorthanded_shooter_roles(match, config)
        for side in ("home", "away"):
            rec312 = shr312[side]
            if rec312.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztra futó hátrány-játék",
                f"öt emberrel a lövéseink {rec312['share_pct']:.0f}"
                f"%-a a(z) {rec312['main_role']} posztról jön "
                f"({rec312['shots']} hátrány-lövésből; "
                f"{SHR_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél emberelőnyben pontosan tudja, kit zárjon",
                "hátrány-repertoár: öt emberre két megjátszható "
                "befejezés (időhúzó körjáték után beálló-beadás VAGY "
                "kilépő átlövés) — és jelre váltakozik, ki a vállaló")
    except Exception:
        pass

    # 311) Emberelőny-poszt: ha az emberelőnyünk mindig ugyanarra a
    # posztra fut ki, öt védő is elég ellene.
    try:
        from .rules import PPR_SHARE_PCT, powerplay_shooter_roles
        ppr311 = powerplay_shooter_roles(match, config)
        for side in ("home", "away"):
            rec311 = ppr311[side]
            if rec311.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztra futó emberelőny",
                f"az emberelőny-lövéseink {rec311['share_pct']:.0f}"
                f"%-a a(z) {rec311['main_role']} posztról jön "
                f"({rec311['shots']} lövésből; {PPR_SHARE_PCT:.0f}% "
                "fölött már minta) — a megfogyatkozott fal is tudja, "
                "hova álljon",
                "emberelőny-figurák két befejezési úttal: minden "
                "gyakorlat-körben kötelező a másodlagos kifutás is "
                "(túloldali átlövő, beálló-lecsorgás) — a hatodik "
                "ember akkor ér valamit, ha KÉT helyen fáj")
    except Exception:
        pass

    # 310) Kiosztás-poszt: ha a betörésünk utáni labda mindig
    # ugyanoda megy, az ellenfél a sávot előre zárja.
    try:
        from .attack_types import KOR_SHARE_PCT, kickout_target_roles
        kor310 = kickout_target_roles(match, config)
        for side in ("home", "away"):
            rec310 = kor310[side]
            if rec310.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztra járó kiosztás",
                f"a betöréseink utáni labda {rec310['share_pct']:.0f}"
                f"%-ban a(z) {rec310['main_role']} posztra megy "
                f"({rec310['kickouts']} kiosztásból; "
                f"{KOR_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél a sávot előre zárja, és a betörőnkre "
                "bátran kettőzik",
                "kiosztás-variációk: betörés után körönként más a "
                "kijelölt fogadó (túloldali átlövő, visszazáró "
                "szélső, second-line beálló) — a betörő fejben két "
                "opcióval induljon")
    except Exception:
        pass

    # 309) Kettőző-poszt: ha a kettőzésünk mindig ugyanarról a
    # posztról érkezik, az ellenfél előre tudja, hol nyílik a pálya.
    try:
        from .defense import DDR_SHARE_PCT, doubling_defender_roles
        ddr309 = doubling_defender_roles(match, config)
        for side in ("home", "away"):
            rec309 = ddr309[side]
            if rec309.get("verdict") is None:
                continue
            add(side, "védekezés", "Kiolvasható kettőzés",
                f"a kettőzött időnk {rec309['share_pct']:.0f}%-ában "
                f"a(z) {rec309['main_role']} posztunk lép ki "
                f"({DDR_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél előre tudja, kinek az embere marad üresen",
                "kettőzés-forgó: a második ember jelre váltakozik "
                "(nem mindig ugyanaz lép ki), és minden kettőzésnél "
                "kijelölt besegítő zárja az elhagyott embert")
    except Exception:
        pass

    # 308) Kockáztató-poszt: ha a hosszú eladásaink egy posztról
    # jönnek, az ellenfél a sávjába áll, és kontrát kap belőle.
    try:
        from .attack_types import RPR_SHARE_PCT, risky_passer_roles
        rpr308 = risky_passer_roles(match, config)
        for side in ("home", "away"):
            rec308 = rpr308[side]
            if rec308.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztról szórt hosszú labdák",
                f"az elszórt hosszú passzaink "
                f"{rec308['share_pct']:.0f}%-a a(z) "
                f"{rec308['main_role']} posztról indul "
                f"({rec308['turnovers']} eladásból; "
                f"{RPR_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél a sávjába áll, és minden elszórt labdából "
                "kontrát kapunk",
                "passz-technika blokk a terhelt posztra: hosszú "
                "indítás csak feszes, előre vezetett labdával, "
                "nyomás alatt kötelező a rövid biztonsági megoldás — "
                "sávba lépő védővel gyakorolva")
    except Exception:
        pass

    # 307) Vasember-poszt: ha egy posztunk csere nélkül végigmegy, a
    # hajrában ott fáradunk el — az ellenfél oda viszi majd a tempót.
    try:
        from .stats import IRM_SHARE_PCT, iron_man_roles
        irm307 = iron_man_roles(match, config)
        for side in ("home", "away"):
            rec307 = irm307[side]
            if rec307.get("verdict") is None:
                continue
            add(side, "fáradás", "Cserétlen poszt",
                f"a(z) {rec307['main_role']} posztunk "
                f"{rec307['share_pct']:.0f}%-os jelenléttel "
                "végigjátssza a meccset, miközben a többi posztot "
                f"cseréljük ({IRM_SHARE_PCT:.0f}% fölött már minta) — "
                "az ellenfél a hajrában oda fogja vinni a tempót",
                "váltóember-építés: a cserétlen posztra kijelölt "
                "második ember kap heti játékperc-célt (edzőmeccsen "
                "és sima meccs első félidejében), hogy a hajrára "
                "legyen valódi váltás")
    except Exception:
        pass

    # 306) Bejátszó-poszt: ha a beálló-játékunk egy kézen fut, a
    # bejátszónk zárásával az egész belső játékunk leáll.
    try:
        from .attack_types import PFR_SHARE_PCT, pivot_feeder_roles
        pfr306 = pivot_feeder_roles(match, config)
        for side in ("home", "away"):
            rec306 = pfr306[side]
            if rec306.get("verdict") is None:
                continue
            add(side, "támadás", "Egy kézen futó beálló-játék",
                f"a beálló-beadásaink {rec306['share_pct']:.0f}%-a "
                f"a(z) {rec306['main_role']} posztról jön "
                f"({rec306['feeds']} beadásból; "
                f"{PFR_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél a bejátszónk zárásával az egész belső "
                "játékunkat leállítja",
                "beadás-forgó: a figurákban a beálló-bejátszás "
                "felelőse körönként váltakozik (irányító, átlövő, "
                "szélső-befutás után), és minden posztnak van "
                "begyakorolt beadás-fajtája (pattintott, átemelt, "
                "test mellől)")
    except Exception:
        pass

    # 305) Indítás-vadász poszt: ha a letámadásunk egy emberen fut, az
    # ellenfél az indítását egyszerűen a sávján kívül nyitja.
    try:
        from .goalkeeper import OHR_SHARE_PCT, outlet_hunter_roles
        ohr305 = outlet_hunter_roles(match, config)
        for side in ("home", "away"):
            rec305 = ohr305[side]
            if rec305.get("verdict") is None:
                continue
            add(side, "védekezés", "Egy emberen futó indítás-vadászat",
                f"az elrabolt indításaink {rec305['share_pct']:.0f}%-a"
                f" a(z) {rec305['main_role']} poszté "
                f"({rec305['steals']} rablásból; "
                f"{OHR_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél kapusa a sávján kívül fog nyitni, és a "
                "letámadásunk üresben fut",
                "letámadás-forgó: a kapus-indítás vadásza jelre "
                "vándorol (szélső, átlövő, beálló felváltva), a "
                "második ember a visszapasszt zárja — a cél, hogy a "
                "rablás a RENDSZERÉ legyen, ne egy emberé")
    except Exception:
        pass

    # 304) Kulcs-poszt: ha az elemzés rétegei ugyanarra a posztunkra
    # mutatnak, a játékunk egy emberen áll — az ellenfél is látja.
    try:
        from .priorities import KP_MIN_LAYERS, key_post
        kp304 = key_post(match, config)
        for side in ("home", "away"):
            rec304 = kp304[side]
            if rec304.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztra futó játék",
                f"{rec304['posts'][rec304['top']]} poszt-réteg "
                f"ítélete fut ki a(z) {rec304['top']} posztunkra "
                f"({KP_MIN_LAYERS} egyező réteg fölött már minta) — "
                "az ellenfél egyetlen ember kezelésével több "
                "mintánkat kapcsolja ki egyszerre",
                "tehermentesítő hét: a kulcs-poszt minden szerepére "
                "(befejezés, lepattanó, elzárás) kijelölt második "
                "felelős gyakorol — a cél, hogy a következő meccsen "
                "egyik minta se egy emberen álljon")
    except Exception:
        pass

    # 303) Elzáró-poszt: ha az elzárás-játékunk egy emberre épül, a
    # kivétele után a lövőink fedve maradnak.
    try:
        from .attack_types import SCR2_SHARE_PCT, screen_setter_roles
        sc2_303 = screen_setter_roles(match, config)
        for side in ("home", "away"):
            rec303 = sc2_303[side]
            if rec303.get("verdict") is None:
                continue
            add(side, "támadás", "Egy posztra épülő elzárás-játék",
                f"az elzárásaink {rec303['share_pct']:.0f}%-a a(z) "
                f"{rec303['main_role']} posztról jön "
                f"({rec303['screens']} elzárásból; "
                f"{SCR2_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél előre tudja, honnan érkezik a test, és az "
                "elzárónkat elölről fogja",
                "elzárás-variációk: a figurákban az elzáró posztja "
                "körönként váltakozik (beálló, átlövő, befutó szélső)"
                " — a cél, hogy a váltás-kommunikációjukat minden "
                "körben újra kelljen kezdeni")
    except Exception:
        pass

    # 302) Átvert-poszt: ha a kapott góljaink egy poszt
    # párharc-vereségéből esnek, az ellenfél is oda fogja vinni.
    try:
        from .defense import BTR_SHARE_PCT, beaten_defender_roles
        btr302 = beaten_defender_roles(match, config)
        for side in ("home", "away"):
            rec302 = btr302[side]
            if rec302.get("verdict") is None:
                continue
            add(side, "védekezés", "Egy poszton eső párharc-vereségek",
                f"a védőhöz rendelt kapott góljaink "
                f"{rec302['share_pct']:.0f}%-a a(z) "
                f"{rec302['main_role']} posztunk mögött esik "
                f"({rec302['goals']} gólból; {BTR_SHARE_PCT:.0f}% "
                "fölött már minta) — az ellenfél tudatosan az ő "
                "emberét fogja támadni",
                "párharc-blokk a terhelt posztra: 1v1-sorozat "
                "váltakozó támadókkal, mögötte kötelező besegítő "
                "váltás — és videón közösen megnézni, MELYIK mozdulat "
                "veri meg (lépés-előny, testcsel, elzárás)")
    except Exception:
        pass

    # 301) Visszafutás-poszt: ha a visszarendeződésünk mindig ugyanott
    # szakad el, az ellenfél kontrái menetrend szerint jönnek.
    try:
        from .defense import RTR_SHARE_PCT, slow_retreat_roles
        rtr301 = slow_retreat_roles(match, config)
        for side in ("home", "away"):
            rec301 = rtr301[side]
            if rec301.get("verdict") is None:
                continue
            add(side, "védekezés", "Egy poszton elszakadó visszafutás",
                f"az ellenfél-kontráknál {rec301['share_pct']:.0f}%-ban"
                f" a(z) {rec301['main_role']} posztunk maradt elöl "
                f"({rec301['breaks']} kontrából; "
                f"{RTR_SHARE_PCT:.0f}% fölött már minta) — az ellenfél"
                " az ő sávjába fogja vezetni a kontráit",
                "visszafutás-staféta: minden lövésünk pillanatában "
                "kijelölt első visszafutó van (jelre váltakozik, hogy "
                "ne mindig ugyanaz maradjon elöl), a második hullám a "
                "labdás sávot zárja — sípszóra mérve, hogy a hatodik "
                "ember hány másodperc alatt ér a felezőn túlra")
    except Exception:
        pass

    # 300) Kiülő-poszt: ha a kétperceink egy posztra járnak, a
    # létszámhátrányunk menetrend szerint érkezik.
    try:
        from .rules import SUP_SHARE_PCT, suspended_roles
        sup300 = suspended_roles(match, config)
        for side in ("home", "away"):
            rec300 = sup300[side]
            if rec300.get("verdict") is None:
                continue
            add(side, "védekezés", "Egy posztra járó kétpercek",
                f"a kiállításaink {rec300['share_pct']:.0f}%-a a(z) "
                f"{rec300['main_role']} poszté "
                f"({rec300['suspensions']} kiállításból; "
                f"{SUP_SHARE_PCT:.0f}% fölött már minta) — az "
                "ellenfél tudatosan az ő sávjába fogja vezetni a "
                "játékot, és a hátrányunk menetrend szerint érkezik",
                "szituációs 1v1 a terhelt posztra: betörés-sorozat "
                "ellen csak elcsúszás és testes megállítás ér, mögé "
                "kötelező besegítő áll — és a videón együtt nézzék "
                "meg, MELYIK mozdulat hozza a sípszót")
    except Exception:
        pass

    # 299) Hetes-okozó poszt: ha a heteseink egy sávban szakadnak be,
    # ott a védőnk kézzel áll meg — az ellenfél oda fog betörni.
    try:
        from .rules import SVR_SHARE_PCT, seven_conceder_roles
        svr299 = seven_conceder_roles(match, config)
        for side in ("home", "away"):
            rec299 = svr299[side]
            if rec299.get("verdict") is None:
                continue
            add(side, "védekezés", "Egy sávban beszakadó hetesek",
                f"az okozott heteseink {rec299['share_pct']:.0f}%-a "
                f"a(z) {rec299['main_role']} poszté "
                f"({rec299['sevens']} hetesből; {SVR_SHARE_PCT:.0f}% "
                "fölött már minta) — az ellenfél tudatosan oda fogja "
                "vezetni a betöréseket",
                "lábmunka-gyakorlat a beszakadó sávra: 1v1 betörés "
                "ellen tilos a kézhasználat (síppal fújva), a "
                "megállítás csak elcsúszással és testtel érvényes — "
                "mögötte besegítő ér, hogy ne kelljen szabálytalankodni")
    except Exception:
        pass

    # 298) 7a6-befejező poszt: ha a hetedik emberrel is mindig
    # ugyanoda lyukadunk ki, az emberelőnyünk kiszámítható.
    try:
        from .goalkeeper import EN7_SHARE_PCT, seven_six_finisher_roles
        en7_298 = seven_six_finisher_roles(match, config)
        for side in ("home", "away"):
            rec298 = en7_298[side]
            if rec298.get("verdict") is None:
                continue
            add(side, "támadás", "Kiszámítható 7 a 6",
                f"a 7 a 6-os lövéseink {rec298['share_pct']:.0f}%-a "
                f"a(z) {rec298['main_role']} posztról jön "
                f"({rec298['shots']} lövésből; {EN7_SHARE_PCT:.0f}% "
                "fölött már minta) — az ellenfél besűríti a sávot, és "
                "a szerzése mögött üres a kapunk",
                "7 a 6 két kijátszási úttal: minden gyakorlat-körben "
                "kötelező a másodlagos befejezés is (átemelés a "
                "túloldali beállóra, szélső-visszazárás) — a hetedik "
                "ember akkor ér valamit, ha KÉT helyen fáj")
    except Exception:
        pass

    # 297) Blokk-poszt: ha a blokk-munkánk egy emberen áll, az
    # elmozgatása után a faltól nincs védelmünk az átlövés ellen.
    try:
        from .defense import RBK_SHARE_PCT, role_block_sources
        rbk297 = role_block_sources(match, config)
        for side in ("home", "away"):
            rec297 = rbk297[side]
            if rec297.get("verdict") is None:
                continue
            add(side, "védekezés", "Egy emberen álló blokk-munka",
                f"a blokkjaink {rec297['share_pct']:.0f}%-a a(z) "
                f"{rec297['main_role']} poszttól jön "
                f"({rec297['blocks']} blokkból; "
                f"{RBK_SHARE_PCT:.0f}% fölött már minta) — az ellenfél "
                "egy beálló-felfutással kihúzza, és a fal mögötte "
                "nyitva marad",
                "blokk-staféta a falban: átlövés-sorozat ellen a "
                "kilépő-blokkoló szerep jelre vándorol a belső hármas "
                "között — a cél, hogy a blokk a FALÉ legyen, ne egy "
                "emberé")
    except Exception:
        pass

    # 296) Lepattanó-poszt: ha a második rohamunk egy emberen múlik, a
    # kizárása után nincs második esélyünk.
    try:
        from .attack_types import SCR_SHARE_PCT, second_chance_roles
        scr296 = second_chance_roles(match, config)
        for side in ("home", "away"):
            rec296 = scr296[side]
            if rec296.get("verdict") is None:
                continue
            add(side, "támadás", "Egy emberen álló második roham",
                f"a második lövéseink {rec296['share_pct']:.0f}%-a a(z) "
                f"{rec296['main_role']} posztról jön "
                f"({rec296['second_shots']} második lövésből; "
                f"{SCR_SHARE_PCT:.0f}% fölött már minta) — ha őt "
                "kizárják a lepattanóból, nincs második esélyünk",
                "lepattanó-játék 3v3-ban: minden lövés után KÉT "
                "kijelölt érkező megy a lepattanóra (a lövő sosem) — a "
                "második hullám posztja körönként váltakozik, hogy a "
                "lepattanó-szerzés ne egy emberé legyen")
    except Exception:
        pass

    # 295) Labdaszerző-poszt: ha a szerzéseink egy emberen múlnak, a
    # letámadásunk egyetlen cserével hatástalanítható.
    try:
        from .defense import RSW_SHARE_PCT, role_steal_sources
        rsw295 = role_steal_sources(match, config)
        for side in ("home", "away"):
            rec295 = rsw295[side]
            if rec295.get("verdict") is None:
                continue
            add(side, "védekezés", "Egy emberen álló labdaszerzés",
                f"a szerzéseink {rec295['share_pct']:.0f}%-a a(z) "
                f"{rec295['main_role']} posztról jön "
                f"({rec295['steals']} szerzésből; "
                f"{RSW_SHARE_PCT:.0f}% fölött már minta) — az ellenfél "
                "egyszerűen elkerüli a sávját, vagy kivárja a cseréjét",
                "nyomás-váltó gyakorlat: a letámadásban a kilépő ember "
                "posztja jelre váltakozik (nem mindig ugyanaz lép ki) — "
                "a cél, hogy a szerzés a RENDSZERÉ legyen, ne egy "
                "emberé")
    except Exception:
        pass

    # 294) Gólpassz-poszt: ha a góljaink egy poszt kezéből indulnak, az
    # ellenfél a passzt veszi el, és az egész támadásunk megáll.
    try:
        from .roles import RAS_SHARE_PCT, role_assist_sources
        ras294 = role_assist_sources(match, config)
        for side in ("home", "away"):
            rec294 = ras294[side]
            if rec294.get("verdict") is None:
                continue
            add(side, "támadás", "Egy kézből induló gólgyártás",
                f"a góljaink {rec294['share_pct']:.0f}%-a a(z) "
                f"{rec294['main_role']} kezéből indul "
                f"({rec294['assists']} gólpasszból; "
                f"{RAS_SHARE_PCT:.0f}% fölött már mintázat) — ha őt "
                "kiveszik, megáll a támadásunk",
                "MÁSODIK ELOSZTÓ gyakorlat: a fő elosztó posztja 5 "
                "támadásonként tiltott (edzői jel), a szomszéd poszt "
                "veszi át az utolsó passzt — előbb lassítva, majd "
                "teljes tempóban, védőkkel")
    except Exception:
        pass

    # 293) Hetes-oldal: ha a heteseink mindig ugyanarra az oldalra
    # mennek, egy felkészült kapus előre eldöntött vetődéssel fogja
    # őket — a legtisztább helyzetünk válik kiszámíthatóvá.
    try:
        from .rules import SVD_SHARE_PCT, seven_shot_directions
        svd293 = seven_shot_directions(match, config)
        for side in ("home", "away"):
            rec293 = svd293[side]
            if rec293.get("verdict") is None:
                continue
            add(side, "támadás", "Kiszámítható hetes-oldal",
                f"a heteseink {rec293['share_pct']:.0f}%-a "
                f"{rec293['dominant']} oldalra megy "
                f"({rec293['attempts']} mérhető dobásból; "
                f"{SVD_SHARE_PCT:.0f}% fölött már mintázat) — egy "
                "felkészült kapus előre eldöntött vetődéssel fogja",
                "hetes-sorozat az edzés VÉGÉN, fáradtan: a dobó minden "
                "dobás előtt kap egy oldalt (edzői jel), és oda kell "
                "dobnia — a cél, hogy nyomás alatt se a begyakorolt "
                "sarok jöjjön automatikusan, hanem döntés")
    except Exception:
        pass

    # 292) Kontra-poszt: ha a lerohanásaink egy poszton záródnak, az
    # ellenfél egy emberrel hatástalanítja a leggyorsabb fegyverünket.
    try:
        from .roles import RFB_SHARE_PCT, role_fast_breaks
        rfb292 = role_fast_breaks(match, config)
        for side in ("home", "away"):
            rec292 = rfb292[side]
            if rec292.get("verdict") is None:
                continue
            add(side, "támadás", "Egy csatornás kontra",
                f"a lerohanásaink {rec292['share_pct']:.0f}%-a a(z) "
                f"{rec292['main_role']} poszton zárul "
                f"({rec292['shots']} kontra-lövésből; "
                f"{RFB_SHARE_PCT:.0f}% fölött már mintázat) — az "
                "ellenfél egy kijelölt emberrel hatástalanítja",
                "kétsávos kontra-gyakorlat: az indítás után a labda "
                "kötelezően sávot vált, mielőtt kapura mehet — a "
                "második hullám embere is kap befejezést, hogy a "
                "kontránk ne egy emberen múljon")
    except Exception:
        pass

    # 291) Lövésválasztás: ha a lövéseink nagy részénél volt jobb
    # szabad helyzet a pályán, nem a lövéstechnika a gond — a fejet
    # kell felhozni a lövés előtt.
    try:
        from .decisions import SCQ_HIGH_PCT, shot_choice_quality
        scq291 = shot_choice_quality(match, config)
        for side in ("home", "away"):
            rec291 = scq291[side]
            if rec291["pct"] is None or rec291["pct"] < SCQ_HIGH_PCT:
                continue
            add(side, "támadás", "Eldobott jobb helyzet",
                f"a lövéseink {rec291['pct']:.0f}%-ánál volt jobb SZABAD "
                f"helyzet a pályán ({rec291['better_options']}/"
                f"{rec291['shots']} lövés; {SCQ_HIGH_PCT:.0f}% fölött "
                "már mintázat) — nem a lövéstechnika a gond, hanem hogy "
                "nem nézünk fel",
                "DÖNTÉS-JÁTÉK: 4-4 a fél pályán, a lövés csak azután "
                "érvényes, hogy a lövő megnevezte, ki állt szabadabban; "
                "ha rosszul nevezi meg, a gól nem számít — a cél a "
                "felnézés reflexe, nem a passz-kényszer")
    except Exception:
        pass

    # 290) Időkérés-befejező: ha az időkérés utáni támadásunk mindig
    # ugyanarra a posztra fut ki, az ellenfél elé áll — pont a
    # legfontosabb támadásunkat fogják meg.
    try:
        from .stoppages import TOF_SHARE_PCT, timeout_finisher
        tof290 = timeout_finisher(match, config)
        for side in ("home", "away"):
            rec290 = tof290[side]
            if rec290.get("verdict") is None:
                continue
            add(side, "támadás", "Kiszámítható időkérés-befejezés",
                f"időkérés után a lövéseink {rec290['share_pct']:.0f}%-a "
                f"a(z) {rec290['main_role']} posztról jött "
                f"({rec290['shots']} lövésből, {rec290['timeouts']} "
                f"időkérés után; {TOF_SHARE_PCT:.0f}% fölött már "
                "mintázat) — az ellenfél elé áll",
                "KÉT időkérés-figura a táblára, azonos indítással: az "
                "egyik a szokásos befejezőre, a másik a mögé érkezőre "
                "fut ki — az edzés végén, fáradtan, egy hívó szóra "
                "kell mennie mindkettőnek")
    except Exception:
        pass

    # 289) Figura-befejező: ha a figuránk mindig ugyanarra a posztra
    # fut ki, egy felkészült fal a figura indulásakor odacsúszik.
    try:
        from .setplays import SPF_SHARE_PCT, setplay_finishers
        spf289 = setplay_finishers(match, config)
        for side in ("home", "away"):
            tel289 = spf289[side].get("telegraphed")
            if tel289 is None:
                continue
            add(side, "támadás", "Kiszámítható figura-befejezés",
                f"a(z) {tel289['figure']}. figuránk lövéseinek "
                f"{tel289['share_pct']:.0f}%-a a(z) {tel289['poszt']} "
                f"posztra fut ki ({tel289['shots']} lövésből; "
                f"{SPF_SHARE_PCT:.0f}% fölött már mintázat) — egy "
                "felkészült fal a figura indulásakor odacsúszik",
                "MÁSODIK BEFEJEZŐ a figurába: ugyanaz az indítás, de a "
                "harmadik passz után választható két végpont — a "
                "döntést a fal csúszása hozza, ne az edzői utasítás; "
                "előbb lassítva, döntés-jelre, majd teljes tempóban")
    except Exception:
        pass

    # 288) Poszt-nyomás: ha egy posztunk fedezetten beesik, a nyomás
    # alatti befejezést kell gyakorolnia — az ellenfél épp rá lép ki.
    try:
        from .roles import RPF_GAP_PCT, role_pressure_finish
        rpf288 = role_pressure_finish(match, config)
        for side in ("home", "away"):
            rec288 = rpf288[side]
            shy288 = rec288.get("pressure_shy")
            if shy288 is None:
                continue
            add(side, "befejezés", "Fedezetten beeső poszt",
                f"a(z) {shy288['poszt']} posztunk a fedezett lövései "
                f"{shy288['covered_pct']:.0f}%-át lövi be "
                f"({shy288['covered_shots']} lövésből; ez "
                f"{shy288['gap_pct']:.0f} százalékponttal a csapat-átlag "
                f"alatt van, {RPF_GAP_PCT:.0f} fölött már mintázat) — az "
                "ellenfél épp rá fog kilépni",
                "nyomás alatti befejezés: kontakt-lövés párnával és "
                "kinyújtott kézzel a lövősávban, kényszerített "
                "test-érintkezés után — a cél nem az erő, hanem hogy a "
                "kar üteme ne változzon, amikor hozzáérnek")
    except Exception:
        pass

    # 287) Poszt-kapuoldal: ha egy posztunk mindig ugyanoda lő, az
    # ellenfél kapusa ráállhat — a kapuoldal-váltás gyakorlandó.
    try:
        from .roles import RGP_SHARE_PCT, role_goal_placement
        rgp287 = role_goal_placement(match, config)
        for side in ("home", "away"):
            rec287 = rgp287[side]
            pred287 = rec287.get("predictable")
            if pred287 is None:
                continue
            add(side, "befejezés", "Kiszámítható kapuoldal",
                f"a(z) {pred287['poszt']} posztunk a góljai "
                f"{pred287['share_pct']:.0f}%-át {pred287['dominant']} "
                f"oldalra lövi ({pred287['goals']} gólból; "
                f"{RGP_SHARE_PCT:.0f}% fölött már mintázat) — egy "
                "felkészült kapus erre rááll",
                "kapuoldal-váltás gyakorlása: ugyanabból a helyzetből "
                "váltakozó sarok, a kapus MOZDULATÁRA döntve — a cél "
                "nem a másik sarok begyakorlása, hanem hogy a döntés az "
                "utolsó pillanatban szülessen")
    except Exception:
        pass
    # 286) Poszt-lövéserő: ha az egyik posztunk lövése kiugróan
    # kemény, a többié viszont nem, a befejezés egy emberre szűkül.
    try:
        from .roles import RSP_GAP_KMH, role_shot_power
        rsp286 = role_shot_power(match, config)
        for side in ("home", "away"):
            rec286 = rsp286[side]
            hard286 = rec286.get("hardest")
            if hard286 is None:
                continue
            add(side, "befejezés", "Egy posztra szűkül a lövőerő",
                f"a(z) {hard286['poszt']} posztunk átlag "
                f"{hard286['avg_kmh']:.0f} km/h-val lő "
                f"({hard286['shots']} lövés), a csapat-átlagunk "
                f"{rec286['team_avg_kmh']:.0f} km/h — a különbség "
                f"{hard286['gap_kmh']:.0f} km/h "
                f"({RSP_GAP_KMH:.0f} km/h fölött már mintázat), tehát a "
                "kapusnak elég egy posztra készülnie",
                "lövőerő-gyakorlat a TÖBBI posztnak: elzárás utáni "
                "felugrásos befejezés súlyzós bemelegítés után, és "
                "kapura lövés kötött karmunkával — a cél, hogy a fal ne "
                "tudjon egyetlen emberre beállni")
    except Exception:
        pass
    # 285) Poszt-lövésidőzítés: ha egy posztunk a támadás végén lő, az
    # a passzív-jel kockázata és a kifáradt befejezés.
    try:
        from .roles import RST_GAP_S, role_shot_timing
        rst285 = role_shot_timing(match, config)
        for side in ("home", "away"):
            rec285 = rst285[side]
            late285 = rec285.get("latest")
            if late285 is None:
                continue
            add(side, "befejezés", "Túl későn fejezünk be",
                f"a(z) {late285['poszt']} posztunk átlag "
                f"{late285['avg_s']:.1f} másodperccel a támadás kezdete "
                f"után lő ({late285['shots']} lövés), a csapat-átlagunk "
                f"{rec285['team_avg_s']:.1f} mp — a különbség "
                f"{late285['gap_s']:.1f} mp "
                f"({RST_GAP_S:.0f} mp fölött már mintázat), és a kivárt "
                "labda a passzív-jel kockázatát is hozza",
                "időre játszott támadás-gyakorlat: a posztra érkező "
                "labda után KÖTÖTT idő (pl. 12 mp) a befejezésig — a "
                "cél nem a kapkodás, hanem hogy a döntés ne csússzon a "
                "fal megfáradásának kivárásáig")
    except Exception:
        pass
    # 284) Poszt-lövéstávolság: ha egy posztunk rendre messziről lő,
    # az a kapusnak dolgozik — a befejezést közelebb kell hozni.
    try:
        from .roles import RSD_GAP_M, role_shot_distance
        rsd284 = role_shot_distance(match, config)
        for side in ("home", "away"):
            rec284 = rsd284[side]
            far284 = rec284.get("farthest")
            if far284 is None:
                continue
            add(side, "befejezés", "Túl messziről fejezünk be",
                f"a(z) {far284['poszt']} posztunk átlag "
                f"{far284['avg_m']:.1f} méterről lő "
                f"({far284['shots']} lövés), a csapat-átlagunk "
                f"{rec284['team_avg_m']:.1f} m — a különbség "
                f"{far284['gap_m']:.1f} m "
                f"({RSD_GAP_M:.0f} m fölött már mintázat), és a távoli "
                "lövés a kapusnak kedvez",
                "befejezés-gyakorlat ebből a posztból ÚGY, hogy a lövés "
                "csak a 9 m-es vonalon belülről érvényes: elzárás után "
                "beugrás vagy egy plusz labdajáratás — a cél nem több "
                "lövés, hanem közelebbi")
    except Exception:
        pass
    # 283) Poszt-eladási zóna: ha egy posztunk a támadó harmadban ad
    # el, abból kontra lesz.
    try:
        from .roles import RTZ_GAP_PP, role_turnover_zones
        rtz283 = role_turnover_zones(match, config)
        for side in ("home", "away"):
            rec283 = rtz283[side]
            risk283 = rec283.get("riskiest")
            if risk283 is None:
                continue
            add(side, "átmenet", "Kockázatos eladási zóna",
                f"a(z) {risk283['poszt']} posztunk eladásainak "
                f"{risk283['front_pct']:.0f}%-a "
                f"({risk283['front']}/{risk283['turnovers']}) a támadó "
                f"harmadban történik, a csapat-átlagunk "
                f"{rec283['team_front_pct']:.0f}% "
                f"({RTZ_GAP_PP:.0f} százalékpont fölött már mintázat) — "
                "onnan indul ellenünk a kontra",
                "kockázatos zóna: befejezés-gyakorlat ebből a posztból "
                "azzal a szabállyal, hogy eladás után AZONNAL indul a "
                "visszafutás — kijelölt fékező emberrel; a cél nem a "
                "kevesebb eladás, hanem hogy ne legyen belőle gól")
    except Exception:
        pass
    # 282) Poszt-labdatartás: ha egy posztunknál megáll a labda, az
    # ellenfél oda küldi a második embert.
    try:
        from .roles import RHT_GAP_S, role_hold_time
        rht282 = role_hold_time(match, config)
        for side in ("home", "away"):
            rec282 = rht282[side]
            slow282 = rec282.get("slowest")
            if slow282 is None:
                continue
            add(side, "támadás", "Továbbítás-tempó",
                f"a(z) {slow282['poszt']} posztunknál áll meg a labda: "
                f"{slow282['avg_s']:.1f} mp/érintés a csapat-átlagunk "
                f"{rec282['team_avg_s']:.1f} mp helyett "
                f"({RHT_GAP_S:.1f} mp fölötti eltérés már érdemi) — "
                "egy felkészült ellenfél pont oda küldi a második "
                "embert",
                "továbbítás-tempó: labdajáratás időkorláttal — a "
                "domináns poszt legfeljebb egy másodpercig tarthatja "
                "a labdát, a döntést előre kell meghozni; aztán "
                "ugyanez kettőző védelem ellen, sorozatban")
    except Exception:
        pass
    # 281) Poszt-átvételi zóna: ha egy posztunk messze veszi át a
    # labdát, onnan nehéz befejezni.
    try:
        from .roles import RRZ_GAP_M, role_receive_zones
        rrz281 = role_receive_zones(match, config)
        for side in ("home", "away"):
            rec281 = rrz281[side]
            far281 = rec281.get("farthest")
            if far281 is None:
                continue
            add(side, "támadás", "Átvételi mélység",
                f"a(z) {far281['poszt']} posztunk átlagosan "
                f"{far281['avg_m']:.1f} m-en veszi át a labdát, a "
                f"csapat-átlagunk {rec281['team_avg_m']:.1f} m "
                f"({RRZ_GAP_M:.1f} m fölötti eltérés már érdemi) — "
                "onnan minden befejezés nehezebb, és a védő kényelmesen "
                "áll",
                "átvételi mélység: bejátszás-gyakorlat, ahol a "
                "fogadónak MOZGÁSBAN, egy méterrel beljebb kell "
                "megkapnia a labdát — a passzoló csak akkor adhat, ha a "
                "fogadó indult; védővel, sorozatban")
    except Exception:
        pass
    # 280) Poszt-passzháló: ha a passzaink egy vonalon mennek, az
    # elfogás kiszámítható.
    try:
        from .roles import RPM_SHARE, role_pass_map
        rpm280 = role_pass_map(match, config)
        for side in ("home", "away"):
            rec280 = rpm280[side]
            top280 = rec280.get("top")
            if top280 is None:
                continue
            add(side, "támadás", "Passz-útvonalak bővítése",
                f"a poszthoz kötött passzaink "
                f"{top280['share_pct']:.0f}%-a a(z) {top280['from']} → "
                f"{top280['to']} vonalon megy "
                f"({top280['passes']}/{rec280['passes_total']}; "
                f"{RPM_SHARE:.0f}% fölött már kiszámítható) — egy "
                "olvasó védő erre a sávra áll rá, és ingyen labdát kap",
                "passz-útvonalak: labdajáratás-gyakorlat szabállyal — "
                "ugyanaz a vonal kétszer egymás után nem használható, "
                "így a harmadik és negyedik útvonal is beépül; "
                "aktív, kezes védelem ellen, sorozatban")
    except Exception:
        pass
    # 279) Poszt-birtoklás: ha a labda idejének több mint felét egy
    # poszt tartja, a játékunk egy emberen áll.
    try:
        from .roles import RPS_DOMINANT_PCT, role_possession_share
        rps279 = role_possession_share(match, config)
        for side in ("home", "away"):
            rec279 = rps279[side]
            top279 = rec279.get("top")
            if top279 is None:
                continue
            add(side, "támadás", "Labdatartás-megosztás",
                f"a szervezett támadásainkban a labda idejének "
                f"{top279['pct']:.0f}%-át a(z) {top279['poszt']} tartja "
                f"({RPS_DOMINANT_PCT:.0f}% fölött már egy emberen áll a "
                "játék) — egy felkészült ellenfél kijelölt emberrel "
                "támadja le, és a támadásunk megakad",
                "labdatartás-megosztás: támadás-gyakorlat szabállyal — "
                "a domináns poszt legfeljebb két érintésig tarthatja a "
                "labdát, a felépítést a többi vonalnak kell vinnie; "
                "aztán szabad játék, letámadó védelem ellen")
    except Exception:
        pass
    # 278) Poszt-állás: ha hátrányban egyetlen posztra szűkül a
    # befejezésünk, azt az ellenfél lezárja.
    try:
        from .roles import RBS_GAP_PP, role_share_by_score
        rbs278 = role_share_by_score(match, config)
        for side in ("home", "away"):
            rec278 = rbs278[side]
            sh278 = rec278.get("shift")
            if sh278 is None or sh278["gap_pp"] <= 0:
                continue
            add(side, "támadás", "Hátrány-befejezés",
                f"hátrányban a(z) {sh278['poszt']} posztra szűkül a "
                f"befejezésünk ({sh278['trailing_pct']:.0f}% vs "
                f"{sh278['rest_pct']:.0f}% egyébként; "
                f"{RBS_GAP_PP:.0f} százalékpont fölött már mintázat) — "
                "egy felkészült ellenfél a hajrában pont ezt a vonalat "
                "zárja le",
                "hátrány-forgatókönyv: két perc hátrányból indított "
                "játék, ahol a domináns poszt SZÁNDÉKOSAN nem "
                "fejezhet be — a cél, hogy nyomás alatt is legyen "
                "második és harmadik befejező vonalunk")
    except Exception:
        pass
    # 277) Eladás-ár poszt szerint: ha egy posztunk eladásai rendre
    # gólba kerülnek, ott a visszarendeződés hiányzik.
    try:
        from .roles import RTC_QUICK_S, role_turnover_cost
        rtc277 = role_turnover_cost(match, config)
        for side in ("home", "away"):
            rec277 = rtc277[side]
            worst277 = rec277.get("worst")
            if worst277 is None:
                continue
            add(side, "átmenet", "Eladás utáni visszarendeződés",
                f"a(z) {worst277['poszt']} posztunk eladásainak "
                f"{worst277['rate_pct']:.0f}%-át "
                f"({worst277['punished']}/{worst277['turnovers']}) "
                f"{RTC_QUICK_S:.0f} mp-en belüli kapott gól követte — "
                "itt nem az eladások SZÁMA a baj, hanem hogy mindig "
                "büntetlenül indulhat rá a kontra",
                "váltás-sprint: eladás-szimuláció ebből a posztból, "
                "és az első három másodperc gyakorlása — kijelölt "
                "fékező ember a labdára, a többi vonalban vissza; "
                "sorozatban, fáradtan is")
    except Exception:
        pass
    # 276) Poszt-váltás a szünetre: ha a befejezésünk átrendeződik,
    # tudatosítani kell — ne véletlen legyen.
    try:
        from .roles import RSS_GAP_PP, role_share_shift
        rss276 = role_share_shift(match, config)
        for side in ("home", "away"):
            rec276 = rss276[side]
            if rec276["verdict"] is None:
                continue
            sh276 = rec276["shift"]
            add(side, "taktika", "Félidei átrendezés",
                f"a befejezésünk átrendeződik a szünetre: "
                f"{rec276['verdict']} ({sh276['first_pct']:.0f}% → "
                f"{sh276['second_pct']:.0f}%; {RSS_GAP_PP:.0f} "
                "százalékpont fölött már mintázat) — kérdés, hogy ez "
                "tudatos döntés volt-e vagy a fáradás sodorta így",
                "félidei átrendezés: a második félidő első három "
                "támadását előre kiosztott felállással gyakoroljuk "
                "(a szünetben kimondott poszt-fókusszal), és "
                "videón nézzük vissza, hogy a váltás szándékos volt-e")
    except Exception:
        pass
    # 275) Gólpassz-tengely: ha a góljaink egy vonalon esnek, azt az
    # ellenfél elvágja — több tengely kell.
    try:
        from .roles import ARP_MIN_PAIRS, ARP_SHARE, assist_role_pairs
        arp275 = assist_role_pairs(match, config)
        for side in ("home", "away"):
            rec275 = arp275[side]
            top275 = rec275.get("top")
            if top275 is None or rec275["pairs_total"] < ARP_MIN_PAIRS:
                continue
            add(side, "támadás", "Tengely-bővítés",
                f"a gólpasszos góljaink {top275['share_pct']:.0f}%-a a(z) "
                f"{top275['from']} → {top275['to']} vonalon esik "
                f"({top275['goals']}/{rec275['pairs_total']}; "
                f"{ARP_SHARE:.0f}% fölött már kiszámítható) — egy "
                "felkészült ellenfél ezt az egy vonalat elvágja",
                "tengely-bővítés: ugyanabból a felállásból két másik "
                "befejező vonal gyakorlása (a domináns tengely "
                "SZÁNDÉKOS kihagyásával), majd szabad játék, ahol a "
                "védő mozgása dönti el, melyik vonal nyílik")
    except Exception:
        pass
    # 274) Poszt-hatékonyság: ha egy posztunkról alig megy be a lövés,
    # az a poszt befejezés-gyakorlata a heti téma.
    try:
        from .roles import (SER_GAP_PP, SER_MIN_SHOTS,
                            shot_efficiency_by_role)
        ser274 = shot_efficiency_by_role(match, config)
        for side in ("home", "away"):
            rec274 = ser274[side]
            worst274 = rec274.get("worst")
            if worst274 is None or worst274["shots"] < SER_MIN_SHOTS:
                continue
            add(side, "támadás", "Poszt-befejezés",
                f"a(z) {worst274['poszt']} posztunkról csak "
                f"{worst274['pct']:.0f}% megy be "
                f"({worst274['goals']}/{worst274['shots']} lövés), a "
                f"csapat-átlagunk {rec274['team_pct']:.0f}% — "
                f"{abs(worst274['gap_pp']):.0f} százalékpont a "
                f"lemaradás ({SER_GAP_PP:.0f} fölött érdemi); az "
                "ellenfél erre rá fog engedni",
                f"poszt-befejezés: {worst274['poszt']}-gyakorlat "
                "sorozatban, mérkőzés-szerű fáradtsággal — előbb "
                "üres kapura a technika, aztán kapussal és védővel, "
                "és a hét végén ugyanezt a réteget nézzük vissza")
    except Exception:
        pass
    # 273) Kiosztás-célpont: ha a betörés után mindig ugyanoda megy a
    # labda, a védekezés előre tudja — a kiosztást variálni kell.
    try:
        from .attack_types import (KOT_CONCENTRATION_PCT,
                                   KOT_MIN_KICKOUTS, kickout_targets)
        kot273 = kickout_targets(match, config)
        for side in ("home", "away"):
            rec273 = kot273[side]
            if (rec273["verdict"] != "kiszámítható a kiosztás"
                    or rec273["kickouts"] < KOT_MIN_KICKOUTS):
                continue
            who273 = rec273["top"]
            lab273 = (f"{who273['jersey']} mezszámú"
                      if who273.get("jersey") is not None
                      else f"{who273['player_id']} azonosítójú")
            add(side, "támadás", "Kiosztás-variálás",
                f"a betörés után a labda {rec273['top_pct']:.0f}%-ban "
                f"a(z) {lab273} játékoshoz megy "
                f"({who273['count']}/{rec273['kickouts']} kiosztás; "
                f"{KOT_CONCENTRATION_PCT:.0f}% fölött a védekezés "
                "előre tudja) — az ő védője előre elmozdulhat a "
                "passzsávba, a betörőnkre pedig indulhat a kettőzés",
                "kiosztás-variálás: ugyanabból a betörésből három "
                "kimenet gyakorlása (átadás a másik oldalra, "
                "visszaadás a felívelőre, saját befejezés) — a "
                "célpontot a védő mozgása döntse el, ne a beidegzés")
    except Exception:
        pass
    # 272) Teendő-rangsor: ha egy területről jön a jelzések többsége,
    # a heti edzés súlypontját is oda kell tenni.
    try:
        from .priorities import priority_findings
        prf272 = priority_findings(match, config)
        for side in ("home", "away"):
            rec272 = prf272[side]
            fams = rec272.get("families") or {}
            total = sum(fams.values())
            if total < 4:
                continue
            top, n = max(fams.items(), key=lambda kv: kv[1])
            if n < 2:
                continue
            add(side, "taktika", "Heti súlypont",
                f"a rólunk gyűlt {total} jelzésből {n} ugyanabba az "
                f"irányba mutat ({top}-család) — szétszórt "
                "javítgatás helyett egy területre kell koncentrálni",
                "heti súlypont: a hét edzéseinek fő blokkja erre az "
                "egy területre menjen (a többi legfeljebb "
                "bemelegítés-szinten), és a hét végén ugyanezt a "
                "réteget nézzük vissza — mérhető javulás vagy nem")
    except Exception:
        pass
    # 271) Befejező-váltás: ha ugyanaz fejez be sorozatban, a
    # befejezés-rotáció a téma — a védekezés ráállhat a lövőnkre.
    try:
        from .xg import finisher_rotation
        frt271 = finisher_rotation(match, config)
        for side in ("home", "away"):
            rec271 = frt271[side]
            if rec271["verdict"] != "ugyanaz fejez be sorozatban":
                continue
            add(side, "tamadas", "Befejezés-rotáció",
                f"ugyanaz fejez be sorozatban nálunk "
                f"({rec271['repeat_pct']:.0f}% ismétlés "
                f"{rec271['shots']} lövésből) — a védekezés a "
                "második támadásban már rákészül a lövőnkre",
                "befejezés-rotáció: a figurasorban a második támadás "
                "KÖTELEZŐEN másik emberre fut ki (a pad hangosan "
                "jelöli a befejezőt) — az edzésmeccsen ugyanattól a "
                "lövőtől a második egymás utáni befejezés fél pontot "
                "ér")
    except Exception:
        pass
    # 270) Gól-minta: ha a góljaink egy képre járnak, a befejezés-
    # szórás a téma — a kiszámítható minta egy igazítással elzárható.
    try:
        from .xg import GPT_MIN_GOALS, GPT_SHARE_PCT, goal_patterns
        gpt270 = goal_patterns(match, config)
        for side in ("home", "away"):
            rec270 = gpt270[side]
            if rec270["verdict"] is None:
                continue
            add(side, "tamadas", "Befejezés-szórás",
                f"a góljaink egy képre járnak ({rec270['top']}, "
                f"{rec270['patterns'][rec270['top']]}/"
                f"{rec270['goals']}) — egy fal-igazítással "
                "elzárhatóak vagyunk",
                "befejezés-szórás: a figurasorba kötelező második és "
                "harmadik befejezési pont (másik sáv, másik táv) — az "
                "edzésmeccsen ugyanabból a mintából a második gól már "
                "csak fél pontot ér")
    except Exception:
        pass
    # 269) Kettős emberhátrány: ha a négyfős játékunk gólesőt hoz, a
    # 4 fős fal és az időhúzó labdatartás a téma.
    try:
        from .rules import double_shorthand
        dsh269 = double_shorthand(match, config)
        for side in ("home", "away"):
            rec269 = dsh269[side]
            if rec269["verdict"] != "a kettős emberhátrány végzetes nekik":
                continue
            add(side, "vedekezes", "Négyfős fal",
                f"a kettős emberhátrány végzetes nekünk "
                f"({rec269['conceded']} kapott gól "
                f"{rec269['seconds']:.0f} mp alatt) — a 4 fős "
                "játékunk nincs begyakorolva",
                "négyfős fal: 4-0 mély fal gyakorlása kapussal "
                "(sarok-védés felosztva), támadásban időhúzó "
                "labdatartás-rondó — kettős hátrányban a cél nem a "
                "gól, hanem a túlélés: 2 percet kell ellenni, nem "
                "kettőt visszadobni")
    except Exception:
        pass
    # 268) Létszám-hiba: ha a cseréink átfednek, a cserefolyosó-
    # fegyelem a téma — a hetedik ember ingyen kiállítást ér.
    try:
        from .rules import excess_players
        xsp268 = excess_players(match, config)
        for side in ("home", "away"):
            rec268 = xsp268[side]
            if rec268["verdict"] is None:
                continue
            add(side, "taktika", "Cserefolyosó-fegyelem",
                f"a cseréink átfednek ({rec268['windows']} ablakban "
                "hetedik mezőnyjátékos a pályán) — ez büntethető, és "
                "a váltás-pillanatunk rendezetlen",
                "cserefolyosó-fegyelem: a csere CSAK a lejövő "
                "térdmagasságú jelére indul (előbb le, aztán fel), a "
                "cserezóna-szalag kötelező — az edzésmeccsen minden "
                "átfedés azonnali 2 perces emberhátrányt ér, hogy az "
                "ára beégjen")
    except Exception:
        pass
    # 267) Felzárkózás-húzó: ha egy emberen áll a mentésünk, a
    # hátrány-teher szétosztása a téma.
    try:
        from .momentum import comeback_carriers
        cbc267 = comeback_carriers(match, config)
        for side in ("home", "away"):
            rec267 = cbc267[side]
            if rec267["verdict"] is None:
                continue
            add(side, "taktika", "Hátrány-teher szétosztása",
                f"{rec267['verdict']} — ha őt megfogják, nincs "
                "második mentőemberünk",
                "hátrány-figurák két emberre: a hátrány-szituációs "
                "edzésmeccsen a húzóember minden második támadásban "
                "csali (rá kettőznek), és a kijelölt második ember "
                "zárja a figurát — a mentés ne egy kézben legyen")
    except Exception:
        pass
    # 266) Eltűnő védő: ha a védő-motorunk a második félidőre leáll,
    # a védő-rotáció a téma.
    try:
        from .defense import fading_defenders
        fdd266 = fading_defenders(match, config)
        for side in ("home", "away"):
            rec266 = fdd266[side]
            if rec266["verdict"] is None:
                continue
            add(side, "vedekezes", "Védő-motor rotáció",
                f"{rec266['verdict']} — a hajrában az ő zónája "
                "nyílik ki",
                "védő-motor rotáció: a legtöbbet dolgozó védő a "
                "szünet KÖRÜL kap tervezett pihenő-blokkot (az utolsó "
                "5 perc az első félidőből + az első 5 a másodikból), "
                "hogy a hajrában is odaérjen — az edzésmeccsen a pad "
                "számolja a szerzés+blokk terhelést")
    except Exception:
        pass
    # 265) Sprint-állás: ha hátrányban sprintbe menekülünk, az
    # ütemtartó felzárkózás a téma — a pánik-futás a hajrát viszi el.
    try:
        from .stats import sprints_by_score
        spb265 = sprints_by_score(match, config)
        for side in ("home", "away"):
            rec265 = spb265[side]
            if rec265["verdict"] != "hátrányban sprintbe menekülnek":
                continue
            add(side, "taktika", "Ütemtartó felzárkózás",
                f"hátrányban sprintbe menekülünk "
                f"({rec265['trailing']['sprints']} sprint hátrányban) "
                "— a pánik-futás a hajrára elviszi a lábunkat",
                "ütemtartó felzárkózás: hátrány-szituációs játék, ahol "
                "a felzárkózás KIZÁRÓLAG szervezett támadásból "
                "történhet — sprint csak tiszta labdaszerzés után "
                "engedélyezett, minden más pánik-futás mínusz pont; "
                "a pulzus-zónát az erőnléti stáb köti be")
    except Exception:
        pass
    # 264) Eltűnő ember: ha a kulcsemberünk a második félidőre elhal,
    # a terhelés-menedzsment a téma.
    try:
        from .momentum import fading_scorers
        fdr264 = fading_scorers(match, config)
        for side in ("home", "away"):
            rec264 = fdr264[side]
            if rec264["verdict"] is None:
                continue
            add(side, "taktika", "Terhelés-menedzsment",
                f"{rec264['verdict']} — a második félidőre elfogy a "
                "kulcsemberünk",
                "terhelés-menedzsment: a kulcsember az első félidőben "
                "rövidebb blokkokban játszik (tervezett 2-3 perces "
                "pihenőkkel), a szünet után pedig friss lábbal, "
                "kijelölt figurákra érkezik — az edzésen a fáradásos "
                "befejezés-gyakorlat az övé")
    except Exception:
        pass
    # 263) Fekete ötperc: ha egy öt perces ablakunk rendre elúszik, a
    # tervezett csere-blokk és az időkérés-készenlét a téma.
    try:
        from .momentum import black_window
        blw263 = black_window(match, config)
        for side in ("home", "away"):
            rec263 = blw263[side]
            if rec263["verdict"] is None:
                continue
            add(side, "taktika", "Fekete ötperc kezelése",
                f"{rec263['verdict']} — ebben az ablakban rendre "
                "elveszítjük a fonalat",
                "fekete ötperc-terv: a kispad előre kijelölt "
                "csere-blokkot időzít az ablak ELÉ (friss védő-sor), "
                "az időkérés-jel készenlétben — az edzésmeccsen a "
                "gyakorlatvezető szimulálja a lyukat (két gyors "
                "kapott gól), és a csapat begyakorolt protokollal "
                "válaszol: lassított támadás, biztos befejezés")
    except Exception:
        pass
    # 262) Oldal-váltás a szünetre: ha az ellenfél a szünetben szárnyat
    # váltott ellenünk, a súlypont-olvasás a téma.
    try:
        from .tactics import attack_side_shift
        sds262 = attack_side_shift(match, config)
        for side, other in (("home", "away"), ("away", "home")):
            rec262 = sds262[other]
            if rec262["verdict"] is None:
                continue
            add(side, "vedekezes", "Súlypont-olvasás a szünet után",
                f"az ellenfél a szünetben szárnyat váltott ellenünk "
                f"({rec262['fh_main']} → {rec262['sh_main']}) — a "
                "falunk súlypontja a rossz oldalon maradt",
                "súlypont-olvasás: az edzésmeccs második felében a "
                "támadó csapat a pad jelére oldalt vált, a védő fal "
                "hangosan mondja be és három labdán belül tükrözi a "
                "súlypontot (erős védő + kettőzés az új oldalra) — "
                "aki későn vált, büntetőkört fut")
    except Exception:
        pass
    # 261) Fal-váltás a szünetre: ha az ellenfél a szünetben falat
    # váltott ellenünk, a felismerés-rutin a téma.
    try:
        from .tactics import defense_form_shift
        dfs261 = defense_form_shift(match, config)
        for side, other in (("home", "away"), ("away", "home")):
            rec261 = dfs261[other]
            if rec261["verdict"] is None \
                    or "falat váltanak" not in rec261["verdict"]:
                continue
            add(side, "tamadas", "Fal-felismerés a szünet után",
                f"az ellenfél a szünetben falat váltott ellenünk "
                f"({rec261['fh_main']} → {rec261['sh_main']}) — az "
                "első félidei támadó-tervünk a másodikban már nem "
                "működött",
                "fal-felismerés rutin: az edzésmeccsen a védő fal a "
                "pad jelére formát vált, a támadó irányító dolga a "
                "HANGOS bemondás és az azonnali figurasor-váltás — "
                "két kész sorral megyünk minden meccsre")
    except Exception:
        pass
    # 260) Passz-hossz-állás: ha hátrányban hosszú labdákra váltunk,
    # a rövid kombináció hátrányban is a téma — az átdobálás elfogható.
    try:
        from .event_detection import pass_length_by_score
        pls260 = pass_length_by_score(match, config)
        for side in ("home", "away"):
            rec260 = pls260[side]
            if rec260["verdict"] != "hátrányban hosszú labdákra váltanak":
                continue
            add(side, "tamadas", "Rövid kombináció hátrányban",
                f"hátrányban hosszú labdákra váltunk "
                f"({rec260['trailing']['long']} hosszú passz "
                f"{rec260['trailing']['passes']} hátrányban adottból) "
                "— az átdobált labdáink elfoghatók",
                "rövid kombináció hátrányban: hátrány-szituációs "
                "kisjáték, ahol a 10 m-nél hosszabb passz azonnali "
                "labdavesztésnek számít — a felzárkózás útja a gyors, "
                "rövid átadás-sor, nem az átdobálás")
    except Exception:
        pass
    # 259) Kapus-gólpassz: ha az ellenfél kapusa gólpasszt ért
    # ellenünk, a lövés utáni azonnali hátraindulás a téma.
    try:
        from .goalkeeper import gk_assists
        gka259 = gk_assists(match, config)
        for side, other in (("home", "away"), ("away", "home")):
            rec259 = gka259[other]
            if rec259["verdict"] is None:
                continue
            add(side, "vedekezes", "Kapus-indítás sávzárás",
                f"az ellenfél kapusa {rec259['assists']} gólpasszt "
                "ért ellenünk — a lövésünk után senki nem vágta el "
                "a hosszú indítás sávját",
                "kapus-indítás elleni zárás: lövés-gyakorlat, ahol a "
                "lövés PILLANATÁBAN egy kijelölt ember (a lövéstől "
                "legtávolabbi) sarkon fordul és a felező-sávba fut — "
                "a kapus-kidobás elé érés pont, a mögé engedés "
                "büntetőkör")
    except Exception:
        pass
    # 258) Passz-irány-állás: ha az ellenfél előnyben hátrajáratott
    # ellenünk, a vezetés elleni letámadás a téma.
    try:
        from .attack_types import pass_direction_by_score
        pds258 = pass_direction_by_score(match, config)
        for side, other in (("home", "away"), ("away", "home")):
            rec258 = pds258[other]
            if rec258["verdict"] != \
                    "előnyben hátrafelé járatják a labdát":
                continue
            add(side, "vedekezes", "Letámadás a hátrajáratás ellen",
                "az ellenfél előnyben hátrafelé járatta a labdát, és "
                "hagytuk: az időölésük ellen nem léptünk fel",
                "letámadás-gyakorlat vezető ellenfél ellen: az első "
                "hátrapassz a kollektív jel — a két szélső azonnal "
                "felugrik a fogadóra, a belsők a visszajátszás sávját "
                "zárják; cél a szerzés vagy a passzív-óra "
                "újraindítása")
    except Exception:
        pass
    # 257) Szünet-váltás: ha félidőn át ugyanazt játsszuk, a B-terv a
    # téma — a kiszámítható mixre az ellenfél ráállhat.
    try:
        from .attack_types import attack_mix_shift
        ams257 = attack_mix_shift(match, config)
        for side in ("home", "away"):
            rec257 = ams257[side]
            if rec257["verdict"] != "félidőn át ugyanazt játsszák":
                continue
            add(side, "taktika", "B-terv a szünetre",
                f"félidőn át ugyanazt játsszuk (a támadás-mixünk "
                f"mindössze {rec257['shift_pp']:.0f} százalékpontot "
                "mozdult a szünet után) — az ellenfél védő-terve "
                "végig ránk állhat",
                "B-terv építése: az edzésmeccs második felében "
                "KÖTELEZŐ a mix-váltás (a pad hangos jelére a felállt "
                "játékról indításokra vagy fordítva) — a cél, hogy a "
                "szünet utáni első öt percben más képet mutassunk")
    except Exception:
        pass
    # 256) Lepattanó-esés: ha a hajrára elfogy a lepattanó-harcunk, a
    # fáradásos lepattanó-munka a téma — a második labda akarat-játék.
    try:
        from .attack_types import second_chance_fade
        scf256 = second_chance_fade(match, config)
        for side in ("home", "away"):
            rec256 = scf256[side]
            if rec256["verdict"] != "a hajrára elfogy a lepattanó-harcuk":
                continue
            add(side, "tamadas", "Lepattanó-harc fáradtan",
                f"a hajrára elfogy a lepattanó-harcunk (visszaharcolt "
                f"lepattanó {rec256['fh_won']}/{rec256['fh_misses']} → "
                f"{rec256['sh_won']}/{rec256['sh_misses']}) — a "
                "kimaradt lövésünk a hajrában a támadásunk vége",
                "fáradásos lepattanó-gyakorlat: sprint-sorozat után "
                "lövés + KÖTELEZŐ rárobbanás a kipattanóra (aki nem "
                "indul meg, büntetőkör) — a második labda akarat-"
                "játék, fáradt lábbal kell beépülnie")
    except Exception:
        pass
    # 255) Gólpassz-esés: ha a hajrában megáll nálunk a labda, a
    # fáradt csapatjáték a téma — az egyéni megoldás védekezhetőbb.
    try:
        from .attack_types import assist_fade
        asf255 = assist_fade(match, config)
        for side in ("home", "away"):
            rec255 = asf255[side]
            if rec255["verdict"] != "a hajrában megáll a labda":
                continue
            add(side, "tamadas", "Hajra-csapatjáték",
                f"a hajrában megáll nálunk a labda (gólpasszos gól "
                f"{rec255['fh_assisted']}/{rec255['fh_goals']} → "
                f"{rec255['sh_assisted']}/{rec255['sh_goals']}) — "
                "fáradtan egyéni megoldásokba menekülünk",
                "hajra-csapatjáték: fáradásos befejezés-gyakorlat "
                "(sprint-sorozat UTÁN jön a támadás), ahol gól csak "
                "gólpasszból érvényes — a fáradt láb mellé a második "
                "és harmadik átadás is beépül")
    except Exception:
        pass
    # 254) Kapus-sorozat: ha az ellenfél kapusa sorozatban védett
    # ellenünk, a lövés-kép váltás a téma — ugyanazt lőttük neki.
    try:
        from .goalkeeper import gk_save_streaks
        gst254 = gk_save_streaks(match, config)
        for side, other in (("home", "away"), ("away", "home")):
            rec254 = gst254[other]
            if rec254["verdict"] is None:
                continue
            add(side, "tamadas", "Lövés-kép váltás",
                f"az ellenfél kapusa sorozatban védett ellenünk "
                f"({rec254['streaks']} hármas széria, leghosszabb: "
                f"{rec254['longest']}) — hagytuk rákapni: ugyanazt "
                "a képet lőttük",
                "lövés-kép váltás: lövés-sorozat gyakorlat, ahol két "
                "azonos befejezés után a harmadiknak KÖTELEZŐEN más "
                "(zóna, ritmus, poszt) — a padról hangos jel megy, "
                "ha a kapus sorozatban ér labdát")
    except Exception:
        pass
    # 253) 7a6-állás: ha az ellenfél rendszerszinten üres kapuval
    # játszik, az üres-kapus átkapcsolás a téma.
    try:
        from .goalkeeper import empty_net_by_score
        ens253 = empty_net_by_score(match, config)
        for side, other in (("home", "away"), ("away", "home")):
            rec253 = ens253[other]
            if rec253["verdict"] != \
                    "állástól függetlenül lehozzák a kapust":
                continue
            _ens_n253 = (rec253["trailing"] + rec253["leading"]
                         + rec253["level"])
            add(side, "taktika", "Üres kapu-készenlét",
                f"az ellenfél 7a6-ja rendszer ({_ens_n253} üres-kapus "
                "szakasz, nem csak hátrányban) — a szerzéseink után "
                "nem néztünk fel az üres kapura",
                "üres-kapus átkapcsolás: szerzés-játék, ahol minden "
                "labdaszerzés után az első kötelező mozdulat a "
                "felnézés — az üres kapura dobott találat dupla "
                "pont, a fel nem ismert helyzet mínusz")
    except Exception:
        pass
    # 252) Kontra-állás: ha hátrányban kontrába menekülünk, a
    # szervezett visszajövetel a téma — a kapkodó futás labdát ad el.
    try:
        from .attack_types import breaks_by_score
        bks252 = breaks_by_score(match, config)
        for side in ("home", "away"):
            rec252 = bks252[side]
            if rec252["verdict"] != "hátrányban kontrába menekülnek":
                continue
            add(side, "tamadas", "Szervezett visszajövetel",
                f"hátrányban kontrába menekülünk (hátrányban "
                f"{rec252['trailing']['breaks']} lerohanás "
                f"{rec252['trailing']['attacks']} támadásból) — a "
                "kapkodó futás kockázatos labdákkal jár",
                "szervezett visszajövetel: hátrány-szituációs játék, "
                "ahol a kontra CSAK tiszta szerzés után indulhat — "
                "minden más labdánál kötelező a felállt támadás; a "
                "cél, hogy a hátrány ne kapcsolja ki a döntéshozatalt")
    except Exception:
        pass
    # 251) Hetes-állás: ha vezetésnél sorra adjuk az olcsó heteseket a
    # hátrányban lévőnek, a vezetés-őrző lábmunka a téma.
    try:
        from .rules import sevens_by_score
        svs251 = sevens_by_score(match, config)
        for side, other in (("home", "away"), ("away", "home")):
            rec251 = svs251[other]
            if rec251["verdict"] != \
                    "hátrányban harcolják ki a heteseiket":
                continue
            add(side, "vedekezes", "Vezetés-őrző lábmunka",
                f"az ellenfél hátrányból {rec251['trailing']} hetest "
                "harcolt ki ellenünk — vezetésnél kézzel ütünk a "
                "betörőre, és visszaadjuk a legolcsóbb gólt",
                "vezetés-őrző lábmunka: betörés-védés 1-1-ben úgy, "
                "hogy a kéz végig a magasban marad (lent ütő kéz = "
                "azonnali hetes a gyakorlatban is) — a cél az elzárt "
                "út, nem a labdaütés")
    except Exception:
        pass
    # 250) Fegyelem-állás: ha a kiállításaink hátrányban sűrűsödnek,
    # a hideg fej a téma — a frusztrációs kiállítás dupla ár.
    try:
        from .rules import suspensions_by_score
        sps250 = suspensions_by_score(match, config)
        for side in ("home", "away"):
            rec250 = sps250[side]
            if rec250["verdict"] != "hátrányban elszáll a fegyelmük":
                continue
            add(side, "taktika", "Hideg fej hátrányban",
                f"a kiállításaink az eredményt követik "
                f"({rec250['trailing']} kiállítás hátrányban) — "
                "frusztrációból ütünk, és az dupla ár: ember is, "
                "emberhátrányban kapott gól is",
                "hideg fej-protokoll: hátrány-szituációs edzésmeccs "
                "(mínusz kettőről indul a csapat), ahol a "
                "szabálytalanság azonnali cserét ér — a cél a "
                "hátrányban is szabályos, lábbal dolgozó védekezés")
    except Exception:
        pass
    # 249) Kidobott labda: ha sok labdát dobunk ki magunktól, a
    # szélső-passz pontossága és az indítás-hossz kontrollja a téma.
    try:
        from .attack_types import OBT_MIN, balls_out
        obt249 = balls_out(match, config)
        for side in ("home", "away"):
            rec249 = obt249[side]
            if rec249["out"] < OBT_MIN:
                continue
            add(side, "tamadas", "Oldalvonal-fegyelem",
                f"{rec249['out']} labdát dobtunk ki az oldalvonalon — "
                "a legolcsóbb eladás: ehhez ellenfél sem kellett",
                "szélső-passz pontosság: átadások a szélső sávban "
                "oldalvonal-szalaggal (a szalagon túlra tett labda "
                "mínusz), hosszú indítás csak megadott jelre — a "
                "kidobott labda az edzésmeccsen azonnali labdavesztés "
                "ÉS büntetőkör")
    except Exception:
        pass
    # 248) Elhúzódó támadás ára: ha a hosszú akcióink üresen zárulnak,
    # a támadás-lezárás időre a téma — a türelem most nem terem gólt.
    try:
        from .tactics import slow_attack_cost
        sac248 = slow_attack_cost(match, config)
        for side in ("home", "away"):
            rec248 = sac248[side]
            if rec248["verdict"] != \
                    "az elhúzódó támadásaik üresen zárulnak":
                continue
            add(side, "tamadas", "Támadás-lezárás időre",
                f"az elhúzódó támadásaink üresen zárulnak "
                f"({rec248['scored']}/{rec248['slow']} hosszú akció "
                "ért gólt) — a passzív jel árnyékában körbejáratunk "
                "terv nélkül",
                "támadás-lezárás időre: a figura a 25. másodpercben "
                "indul kötelezően, 35 mp-nél síp — ami addig nem "
                "zárul lövéssel, az mínusz pont; a játékvezető "
                "passzív jelet mutat, hogy a döntéskényszer beépüljön")
    except Exception:
        pass
    # 247) Indítás-hiba ára: ha az elszórt indításaink gólba kerülnek,
    # az indítás-biztonság sürgős — az ár már bizonyított.
    try:
        from .goalkeeper import outlet_punishment
        olp247 = outlet_punishment(match, config)
        for side in ("home", "away"):
            rec247 = olp247[side]
            if rec247["verdict"] != \
                    "az elszórt indításaik gólba kerülnek":
                continue
            add(side, "vedekezes", "Indítás-biztonság",
                f"az elszórt indításaink gólba kerülnek "
                f"({rec247['punished']}/{rec247['lost']} elveszett "
                "kihozatal után jött gyors gól) — a rossz első "
                "passz nálunk azonnali büntetést hoz",
                "indítás-biztonság: a kapus két biztos rövid "
                "célpontot kap (a szélső mindig felkínál), nyomás "
                "alatt TILOS a vak hosszú — az edzésmeccsen az "
                "elveszett indítás mínusz, az elveszett indítás "
                "utáni 10 mp-en belül kapott gól dupla mínusz")
    except Exception:
        pass
    # 246) Kihagyás-büntetés: ha a kihagyásaink után azonnal büntetnek,
    # a kihagyás utáni fél perc a téma — előbb védekezni, aztán bánkódni.
    try:
        from .momentum import punished_misses
        pmb246 = punished_misses(match, config)
        for side in ("home", "away"):
            rec246 = pmb246[side]
            if rec246["verdict"] != \
                    "a kihagyásaik után azonnal büntetik őket":
                continue
            add(side, "vedekezes", "Kihagyás utáni fél perc",
                f"a kihagyott ziccereink után rendre azonnal gólt "
                f"kapunk ({rec246['punished']}/{rec246['misses']}) — "
                "a fejünk a kihagyásnál marad, a visszarendeződés "
                "késik",
                "kihagyás utáni fókusz: az edzésmeccsen minden "
                "kihagyott ziccer után 30 mp kiemelt védekezés-idő "
                "(hangosan számolva) — ha ez alatt gólt kapunk, "
                "dupla mínusz; ha labdát szerzünk, dupla pont — a "
                "szabály: előbb védekezni, aztán bánkódni")
    except Exception:
        pass
    # 245) Kilépés-büntetés: ha a kilépésünk mögé betalálnak, a mögé
    # csúszás a téma — a szomszéd zárja a rést.
    try:
        from .defense import stepout_punishment
        sop245 = stepout_punishment(match, config)
        for side in ("home", "away"):
            rec245 = sop245[side]
            if rec245["verdict"] != "a kilépésük mögé betalálnak":
                continue
            add(side, "vedekezes", "Mögé csúszás",
                f"a kilépéseink mögé betalálnak ({rec245['behind_stepout']}"
                f"/{rec245['goals']} kapott gólnál volt kiugró "
                "védőnk) — a kilépés mögötti rést rendre megjátsszák",
                "mögé csúszás gyakorlat: minden kilépésnél a "
                "szomszéd védő automatikusan a rés mögé csúszik "
                "(hangos jelre), a kilépő pedig a kiadás után "
                "azonnal visszazár — az edzésmeccsen a kilépés mögé "
                "kapott gól dupla mínusz, a lezárt rés pont a "
                "csúszónak")
    except Exception:
        pass
    # 244) Kettőzés-büntetés: ha a kettőzésünk gólba kerül, a
    # kettőzés-visszazárás a téma — vagy vissza kell fogni.
    try:
        from .defense import double_punishment
        dbp244 = double_punishment(match, config)
        for side in ("home", "away"):
            rec244 = dbp244[side]
            if rec244["verdict"] != "a kettőzésük gólba kerül":
                continue
            add(side, "vedekezes", "Kettőzés-visszazárás",
                f"a kettőzésünk gólba kerül ({rec244['conceded_after']}"
                " gól esett közvetlenül kettőzés után) — az üresen "
                "hagyott embert rendre megtalálják",
                "kettőzés-visszazárás: a kettőzés pillanatában a "
                "maradék védők előre kijelölt csúszása (ki veszi át "
                "az üres embert), és a kettőzők azonnali "
                "visszazárása a kiadás után — az edzésmeccsen a "
                "kettőzés utáni 3 mp-en belül kapott gól dupla "
                "mínusz, a lezárt kettőzés-hullám pont")
    except Exception:
        pass
    # 243) Olvasó kapus: ha a kapusunk csak reflexből véd, az
    # olvasás-készség a téma — a lövő teste elárulja a sarkot.
    try:
        from .goalkeeper import reading_keeper
        rdk243 = reading_keeper(match, config)
        for side in ("home", "away"):
            rec243 = rdk243[side]
            if rec243["verdict"] != "reflexből véd":
                continue
            add(side, "vedekezes", "Kapus-olvasás",
                f"a kapusunk reflexből véd (csak {rec243['read']}/"
                f"{rec243['saves']} védésnél indult előre) — a "
                "reflex a közeli ziccernél kevés, az olvasott "
                "indulás hozná a plusz védéseket",
                "olvasás-gyakorlat a kapusnak: a lövő elkötelező "
                "jeleinek (csípő, váll, elugró láb) tanulása lassított "
                "majd éles sorozatokkal — az edzésen a lövés ELŐTT "
                "bemondott helyes sarok pontot ér, és a jól olvasott "
                "védés duplát")
    except Exception:
        pass
    # 242) Becsapott kapus: ha a kapusunk elmozdítható, a csel-állás
    # a téma — kivárás, nem korai vetődés.
    try:
        from .goalkeeper import wrongfooted_keeper
        wfk242 = wrongfooted_keeper(match, config)
        for side in ("home", "away"):
            rec242 = wfk242[side]
            if rec242["verdict"] != "elmozdítható a kapusuk":
                continue
            add(side, "vedekezes", "Kapus csel-állás",
                f"a kapusunk elmozdítható: {rec242['fooled']}/"
                f"{rec242['goals']} kapott gólnál ellenirányba "
                "mozdult — a lövéscsel rendre beviszi",
                "csel-állás gyakorlat a kapusnak: cselező lövők "
                "sorozata ellen a szabály az utolsó ütemig tartott "
                "alaphelyzet (mozdulni csak a labda elszakadására "
                "szabad) — a cselre indulás mínusz, az állva "
                "kivédett csel-lövés dupla pont")
    except Exception:
        pass
    # 241) Lendület-gólok: ha mozgásból kapjuk a gólokat, a bekísérés
    # a téma — az érkező embert időben fel kell venni.
    try:
        from .defense import conceded_momentum
        cgm241 = conceded_momentum(match, config)
        for side in ("home", "away"):
            rec241 = cgm241[side]
            if rec241["verdict"] != "mozgásból kapják a gólokat":
                continue
            add(side, "vedekezes", "Bekísérés",
                f"a kapott góljaink zöménél lendületből érkezett a "
                f"lövő ({rec241['running']}/{rec241['goals']}) — az "
                "érkező embert senki nem veszi fel időben, a "
                "lendület átmegy a falon",
                "bekísérés-gyakorlat: a fal a betörő/befutó embert "
                "hangos átadás-jellel kíséri (aki elé kerül, azé), "
                "és a mélységből érkezőre KÖTELEZŐ a korai kilépés "
                "— az edzésmeccsen a lendületből kapott gól dupla "
                "mínusz, a megállított betörés pont a felvevőnek")
    except Exception:
        pass
    # 240) Bontó tempó: ha a járatás szed szét minket, a váltás-
    # fegyelem tempó alatt a téma.
    try:
        from .defense import conceded_tempo
        ctm240 = conceded_tempo(match, config)
        for side in ("home", "away"):
            rec240 = ctm240[side]
            if rec240["verdict"] != "a járatás szedi szét őket":
                continue
            add(side, "vedekezes", "Váltás tempó alatt",
                f"a kapott góljaink előtt átlag "
                f"{rec240['avg_passes']:.1f} passz megy 8 mp-en "
                "belül — a pörgő járatásnál a váltásaink késnek, és "
                "a fal szétnyílik",
                "váltás tempó alatt: a fal 6v6 ellen kap pörgő "
                "járatást (kötelező minimum passz-szám a támadónak), "
                "és hangos, korai váltással tart — az edzésmeccsen "
                "a harmadik passz utáni kapott gól dupla mínusz, a "
                "tempó alatt is zárt fal pont")
    except Exception:
        pass
    # 239) Folyosó-gólok: ha nyitott folyosókon kapjuk a gólokat, a
    # visszazárás és a fal-zárás a téma.
    try:
        from .defense import corridor_goals
        crg239 = corridor_goals(match, config)
        for side in ("home", "away"):
            rec239 = crg239[side]
            if rec239["verdict"] != "nyitott folyosókon kapják a gólokat":
                continue
            add(side, "vedekezes", "Folyosó-zárás",
                f"a kapott góljaink zöménél senki nem állt a "
                f"lövésvonalban ({rec239['open']}/{rec239['goals']}) "
                "— a fal nem ér oda vagy szétnyílik, a kapus "
                "fedezetlen lövéseket kap",
                "folyosó-zárás: visszarendeződésnél az első védő "
                "MINDIG a kapu-lövő vonalra áll (nem a labdára fut), "
                "a fal pedig zárás-jelre húz össze — az edzésmeccsen "
                "a lövésvonalban álló védővel kapott gól rendben "
                "van, a nyitott folyosós gól dupla mínusz")
    except Exception:
        pass
    # 238) Csere-büntetés: ha a csere-lyukaink már gólba kerültek, a
    # csere-ütem javítása sürgős — nem mért kockázat, megfizetett ár.
    try:
        from .substitutions import gap_punishment
        gpn238 = gap_punishment(match, config)
        for side in ("home", "away"):
            rec238 = gpn238[side]
            if rec238["verdict"] != "a csere-lyukaik gólba kerülnek":
                continue
            add(side, "vedekezes", "Csere-ütem",
                f"a csere-lyukaink gólba kerülnek ({rec238['conceded']}"
                f" kapott gól {rec238['gap_s']:.0f} mp öt fős játék "
                "alatt) — a lassú csere már nem kockázat, hanem "
                "megfizetett ár",
                "csere-ütem gyakorlat: ki és be EGY ütemben, a "
                "cserezónán belül kéz-a-kézben váltás — az "
                "edzésmeccsen minden öt fős védekezett másodperc "
                "mínusz pont a cserélő sornak, a csere alatt kapott "
                "gól dupla mínusz")
    except Exception:
        pass
    # 237) Zavartalan előkészítők: ha a gólpassz-adót hagyjuk
    # dolgozni, a passzsáv-nyomás a téma.
    try:
        from .defense import unpressured_assists
        upa237 = unpressured_assists(match, config)
        for side in ("home", "away"):
            rec237 = upa237[side]
            if rec237["verdict"] != "az előkészítőt hagyják dolgozni":
                continue
            add(side, "vedekezes", "Nyomás a kiadóra",
                f"a kapott gólpasszaink zöme zavartalan kiadásból jön "
                f"({rec237['unpressured']}/{rec237['assisted']}) — a "
                "gól már a passznál eldől, mi pedig csak a lövőnél "
                "kezdünk védekezni",
                "passzsáv-nyomás: a labdás ember védője a kiadás "
                "pillanatában kézzel a passzsávban, testtel a "
                "kiadón — az edzésmeccsen a zavart (megütött, "
                "elhajló) kiadás pontot ér a védőnek, a zavartalan "
                "gólpassz mínuszt")
    except Exception:
        pass
    # 236) Átvert védők: ha egy emberünk rendre elveszíti a párharcot
    # a kapott góloknál, segítés-rend és párharc-edzés a téma.
    try:
        from .defense import beaten_defenders
        btn236 = beaten_defenders(match, config)
        for side in ("home", "away"):
            top236 = btn236[side]["top"]
            if top236 is None:
                continue
            mez236 = (f"{top236['jersey']} mezszámú"
                      if top236["jersey"] is not None
                      else f"{top236['player_id']} azonosítójú")
            add(side, "vedekezes", "Párharc-segítés",
                f"a kapott góljainknál rendre a(z) {mez236} "
                f"játékosunk veszíti a párharcot ({top236['beaten']}/"
                f"{btn236[side]['goals']}) — az ellenfél előbb-utóbb "
                "tudatosan rá viszi majd a betöréseket",
                "párharc-segítés: a kiemelt védő mellé kijelölt "
                "besegítő (hangos jelre lépő váltás), plusz 1v1 "
                "védő-lábmunka gyakorlat — az edzésmeccsen a mellette "
                "esett gól a besegítő mínusza is, a megállított "
                "betörés dupla pont a párnak")
    except Exception:
        pass
    # 235) Indítás-állás: ha vezetve mi is leülünk az indítással, az
    # előny-menedzsment tudatosítása a téma — de ne álljon le a láb.
    try:
        from .goalkeeper import outlet_pace_by_score
        ops235 = outlet_pace_by_score(match, config)
        for side in ("home", "away"):
            rec235 = ops235[side]
            if rec235["verdict"] != "előnyben is pörgetik":
                continue
            add(side, "vedekezes", "Indítás-kontroll előnyben",
                f"előnyben is pörgetjük az indítást (átlag "
                f"{rec235['lead']['avg_s']:.1f} mp kihozatal "
                "vezetve) — ez fegyver, de kétélű: a gyors indítás "
                "előnyben kockázatot is visz a játékunkba",
                "indítás-kontroll: a kapus két jelet tanul — "
                "PÖRGETÉS (azonnali hosszú) és KONTROLL (biztos "
                "rövid, felállt támadás) —, és az edzésmeccsen a "
                "pad jelzi, melyik jön; az előnyben eladott gyors "
                "indítás dupla mínusz, a jelre hozott jó döntés "
                "pont")
    except Exception:
        pass
    # 234) Csere-állás: ha vezetve sem pihentetünk, a pad bizalma a
    # téma — a kulcsember nem bírja végig a szezont.
    try:
        from .substitutions import subs_by_score
        sbs234 = subs_by_score(match, config)
        for side in ("home", "away"):
            rec234 = sbs234[side]
            if rec234["verdict"] != "vezetve sem nyúlnak a sorhoz":
                continue
            add(side, "vedekezes", "A pad bizalma",
                f"vezetve sem cserélünk (csak {rec234['lead_subs']} "
                f"cserehullám előnyben, {rec234['rest_subs']} "
                "egyébként) — a kulcsembereink előnyben is végig "
                "fent vannak, a hajrára és a szezonra elfogynak",
                "pad-bizalom építése: az edzésmeccsen előre "
                "kihirdetett csere-rend (minden 2 gólos előnynél "
                "KÖTELEZŐ hullám), és a becserélt sor külön "
                "pontversenye — a pihentetés alatt hozott gólok "
                "dupla pontot érnek a padnak")
    except Exception:
        pass
    # 233) Előny-védekezés: ha vezetve leül a falunk, az előny
    # megtartása a téma — a fal nem pihenhet.
    try:
        from .xg import defense_by_score
        dbs233 = defense_by_score(match, config)
        for side in ("home", "away"):
            rec233 = dbs233[side]
            if rec233["verdict"] != "előnyben leül a faluk":
                continue
            add(side, "vedekezes", "Előny-védekezés",
                f"vezetve leül a falunk: a kapott átlag-xG "
                f"{rec233['rest']['avg_xg']:.2f}-ról "
                f"{rec233['leading']['avg_xg']:.2f}-ra nő, amikor "
                "előnyben vagyunk — a megnyert meccset is vissza "
                "lehet így adni",
                "előny-megtartó védekezés: edzésmeccs vezetésből "
                "(2-0-ról indítva), ahol a vezető csapat fala "
                "kapja a pontot minden kintről elrontatott "
                "támadásért — a vezetés alatt beengedett ziccer "
                "dupla mínusz, és a sor hangosan számolja, hány "
                "támadás óta feszes a fal")
    except Exception:
        pass
    # 232) Hiba-állás: ha hátrányban kapkodunk, a nyomás alatti
    # rendezettség a téma.
    try:
        from .attack_types import turnovers_by_score
        tbs232 = turnovers_by_score(match, config)
        for side in ("home", "away"):
            rec232 = tbs232[side]
            if rec232["verdict"] != "hátrányban kapkodnak":
                continue
            tr232 = rec232["trailing"]
            add(side, "tamadas", "Rendezettség hátrányban",
                f"hátrányban kapkodunk: {tr232['turnovers']}/"
                f"{tr232['attacks']} hátrányban futott támadásunk "
                "zárult eladással — a sietség több labdát ad el, "
                "mint amennyi gólt a gyorsítás hoz",
                "nyomás alatti rendezettség: edzésmeccs mesterséges "
                "hátrányból (0-2-ről indítva), ahol a cél a KÖTELEZŐ "
                "befejezésig vitt támadás — az eladással záruló "
                "támadás mínusz pont, a lövésig vitt (akár kihagyott) "
                "támadás pont, és a gyors gól csak akkor dupla, ha "
                "nem eladásból jött vissza az ellenfél")
    except Exception:
        pass
    # 231) Kettőző emberek: ha mindig ugyanaz az emberünk kettőz, a
    # kettőzés-forgatás a téma — ne legyen kiolvasható.
    try:
        from .defense import doubling_defenders
        dtp231 = doubling_defenders(match, config)
        for side in ("home", "away"):
            top231 = dtp231[side]["top"]
            if top231 is None:
                continue
            mez231 = (f"{top231['jersey']} mezszámú"
                      if top231["jersey"] is not None
                      else f"{top231['player_id']} azonosítójú")
            add(side, "vedekezes", "Kettőzés-forgatás",
                f"a kettőzésünk kiszámítható: a kettőzött idő "
                f"{top231['share_pct']:.0f}%-ában a(z) {mez231} "
                "játékosunk a második ember — az ellenfél előre "
                "tudja, kinek az őrzöttje szabadul",
                "kettőzés-forgatás: a kettőző ember posztonként "
                "forogjon (a fal mindkét széléről és középről is "
                "jöjjön második) — az edzésmeccsen a védő sor "
                "hangos jelre váltja, ki lép rá, és a kiszámítható "
                "(harmadszor is ugyanonnan jövő) kettőzés mínusz "
                "pont")
    except Exception:
        pass
    # 230) Szélső-mélység: ha messziről lőnek a szélsőink, a befutás
    # begyakorlása a téma, nem a lövőerő.
    try:
        from .attack_types import wing_shot_depth
        wsd230 = wing_shot_depth(match, config)
        for side in ("home", "away"):
            rec230 = wsd230[side]
            if rec230["verdict"] != "messziről lövő szélsők":
                continue
            add(side, "tamadas", "Szélső-befutás",
                f"a szélsőink átlag {rec230['avg_m']:.1f} m-ről "
                "eresztik el a lövést — rossz szögből, kényszerből "
                "lövünk, a kapus bátran jöhet ki ránk",
                "szélső-befutás gyakorlat: a szélső a hatosig "
                "kísért befutásból, elugrásból fejez be — az "
                "edzésmeccsen a hatos vonaláról (6 m-en belülről) "
                "leadott szélső-lövés dupla pontot ér, a 8 m-en "
                "túli szélső-lövés visszajátszandó")
    except Exception:
        pass
    # 229) Kontra-esés: ha a második félidőre eláll a kontránk, a
    # láb és a kontra-döntés kondicionálása a téma.
    try:
        from .attack_types import break_share_fade
        brf229 = break_share_fade(match, config)
        for side in ("home", "away"):
            rec229 = brf229[side]
            if rec229["verdict"] != \
                    "a második félidőben eláll a kontrájuk":
                continue
            _fh229 = 100.0 * rec229["fh_breaks"] / rec229["fh_attacks"]
            _sh229 = 100.0 * rec229["sh_breaks"] / rec229["sh_attacks"]
            add(side, "tamadas", "Kontra a második félidőben is",
                f"a lerohanás-arányunk {_fh229:.0f}%-ról "
                f"{_sh229:.0f}%-ra esik a második félidőre — fáradva "
                "már nem indulunk el, pedig a helyzet ugyanúgy ott "
                "van",
                "kontra-kondicionálás: fáradt lábbal (edzés végén) "
                "futott 3-a-2 lerohanás-sorozatok, ahol az indulás "
                "KÖTELEZŐ minden labdaszerzés után — az edzésmeccs "
                "második felében a kihagyott indulás mínusz pont, a "
                "végigvitt kontra dupla")
    except Exception:
        pass
    # 228) Felhozatal-posztok: ha egyetlen posztra épül a
    # felhozatalunk, a második felhozatal-út beépítése a téma.
    try:
        from .goalkeeper import outlet_target_roles
        otr228 = outlet_target_roles(match, config)
        for side in ("home", "away"):
            rec228 = otr228[side]
            top228 = rec228["top"]
            if top228 is None or top228["share_pct"] < 60.0:
                continue
            add(side, "tamadas", "Második felhozatal-út",
                f"a felhozatalunk {top228['share_pct']:.0f}%-a a(z) "
                f"{top228['poszt']} posztra megy ({top228['count']}/"
                f"{rec228['outlets']} indítás-célpont) — ha őt "
                "letámadják, az egész felhozatalunk megakad",
                "második felhozatal-út: kidobás-variációk edzése "
                "letámadó védők ellen — a kapus két kötelező "
                "célpontot kap, és a nyomás alatt a MÁSIK oldalra "
                "indít; az edzésmeccsen a letámadás alatt is tiszta "
                "felhozatal pontot ér, az eladott indítás mínuszt")
    except Exception:
        pass
    # 227) Falba lövő posztok: ha egy posztunk rendre a falba lő, a
    # lövés-előkészítés a téma, nem a lövő ereje.
    try:
        from .defense import blocked_by_role
        bbr227 = blocked_by_role(match, config)
        for side in ("home", "away"):
            top227 = bbr227[side]["top"]
            if top227 is None:
                continue
            add(side, "tamadas", "Lövés-előkészítés",
                f"a falba lőtt lövéseink a(z) {top227['poszt']} "
                f"posztról jönnek ({top227['blocked']}/"
                f"{bbr227[side]['blocked']} lefogott lövés) — a "
                "poszt lövései előkészítés nélkül, álló falba "
                "mennek",
                "lövés-előkészítés a kiemelt posztnak: elzárás "
                "utáni lövés, egy-ütemű lövőcsel és helycsere a "
                "lövés előtt — az edzésmeccsen az előkészítés "
                "(elzárás vagy csel) utáni gól dupla pont, az álló "
                "falba lőtt blokkolt lövés mínusz")
    except Exception:
        pass
    # 226) Kiállítás-posztok: ha egy posztunk ellen sok a kiállításig
    # menő fogás, a kiharcolás tudatosítása a téma — nekünk fegyver.
    try:
        from .rules import susp_earner_roles
        sur226 = susp_earner_roles(match, config)
        for side in ("home", "away"):
            top226 = sur226[side]["top"]
            if top226 is None:
                continue
            add(side, "tamadas", "Kiállítás-kiharcolás",
                f"a kétperceseinket a(z) {top226['poszt']} poszt "
                f"hozza ({top226['count']}/"
                f"{sur226[side]['suspensions']} kiharcolt "
                "kiállítás) — ez működő fegyver, tudatosítva még "
                "többet ér",
                "kiharcolás-gyakorlat: a kiemelt poszt bátor, "
                "vonalra vitt megindulásai élő védő ellen — a "
                "test-test kontaktot vállalni kell, a lövést az "
                "érintkezés UTÁN is be kell fejezni; az "
                "edzésmeccsen a kiharcolt szabálytalanság pontot "
                "ér, a kontakt-kerülő megtorpanás mínuszt")
    except Exception:
        pass
    # 225) Gólpassz-posztok: ha egyetlen posztról készítjük elő a
    # gólokat, a második előkészítő-út beépítése a téma.
    try:
        from .roles import assists_by_role
        abr225 = assists_by_role(match, config)
        for side in ("home", "away"):
            rec225 = abr225[side]
            top225 = rec225["top"]
            if top225 is None or top225["share_pct"] < 60.0:
                continue
            add(side, "tamadas", "Második előkészítő-út",
                f"a góljaink {top225['share_pct']:.0f}%-át a(z) "
                f"{top225['poszt']} poszt készíti elő "
                f"({top225['assists']}/{rec225['assists']} gólpassz) "
                "— ha az ő kezét megfogják, a támadásunk megáll",
                "második előkészítő-út: támadás-variációk, ahol a "
                "befejezés előtti utolsó passzt KÖTELEZŐEN más "
                "poszt adja (szélső-visszatét, beálló-kiosztás) — "
                "az edzésmeccsen a nem a fő posztról érkező "
                "gólpassz dupla pontot ér")
    except Exception:
        pass
    # 224) Lefogott lövők: ha egy emberünk lövését rendre elviszi a
    # fal, lövő-variáció kell neki, nem több ugyanolyan lövés.
    try:
        from .defense import blocked_shooters
        bsh224 = blocked_shooters(match, config)
        for side in ("home", "away"):
            top224 = bsh224[side]["top"]
            if top224 is None:
                continue
            mez224 = (f"{top224['jersey']} mezszámú"
                      if top224["jersey"] is not None
                      else f"{top224['player_id']} azonosítójú")
            add(side, "tamadas", "Lövő-variációk",
                f"a(z) {mez224} játékosunk lövését rendre elviszi a "
                f"fal ({top224['blocked']}/{bsh224[side]['blocked']} "
                "lefogott lövés az övé) — a védők már olvassák az "
                "egyetlen lövő-mozdulatát",
                "lövő-variáció gyakorlat a kiemelt lövőnek: "
                "lövőcsel után áttolt lövés, elhajlás és bevetődés "
                "váltogatva élő fal ellen — az edzésmeccsen a "
                "blokkolt lövése mínusz pont, a csel utáni "
                "gólja dupla pont")
    except Exception:
        pass
    # 223) Kontra-elszökés: ha mindig együtt futunk fel, az elszökő
    # ember beépítése a téma.
    try:
        from .attack_types import fast_break_headstart
        fbh223 = fast_break_headstart(match, config)
        for side in ("home", "away"):
            rec223 = fbh223[side]
            if rec223["verdict"] != "együtt futnak fel":
                continue
            add(side, "tamadas", "Elszökő ember",
                f"a kontráink mindig együtt futnak fel (csak "
                f"{rec223['ahead']}/{rec223['breaks']} lerohanás "
                "indult a labda előtt váró emberrel) — a védelem "
                "így mindig beér, mert nincs, aki megelőzze",
                "elszökő-gyakorlat: a kijelölt szélső a saját "
                "lövésünk pillanatában már fordul és indul — a "
                "kapus/labdaszerző első dolga a hosszú indítás; az "
                "edzésmeccsen az elszökött embernek adott gólt érő "
                "indítás dupla pontot ér")
    except Exception:
        pass
    # 222) Kontra-hullámok: ha csak az első ember fejezi be a
    # kontránkat, a második hullám beépítése a téma.
    try:
        from .attack_types import fast_break_waves
        fbw222 = fast_break_waves(match, config)
        for side in ("home", "away"):
            rec222 = fbw222[side]
            if rec222["verdict"] != "az első ember fejezi be a kontrát":
                continue
            add(side, "tamadas", "Kontra második hulláma",
                f"a lerohanásainkat szinte csak az első ember fejezi "
                f"be ({rec222['second']}/{rec222['breaks']} kontra "
                "zárult a befutó lövésével) — ha az első embert "
                "felveszik, a kontránk elhal",
                "kontra-hullám gyakorlat: 2-az-1 és 3-a-2 ellen "
                "lerohanás, ahol az első ember KÖTELEZŐEN kihúzza a "
                "védőt és visszatesz a befutónak — az edzésmeccsen "
                "a második hullámból szerzett kontragól dupla "
                "pontot ér")
    except Exception:
        pass
    # 221) Beálló-futtatás: ha állva kap a beállónk, a lefordulós
    # átvétel begyakorlása a téma.
    try:
        from .attack_types import pivot_service
        psv221 = pivot_service(match, config)
        for side in ("home", "away"):
            rec221 = psv221[side]
            if rec221["verdict"] != "állva kapja a beálló":
                continue
            add(side, "tamadas", "Lefordulós beálló",
                f"a beállónk beragadva, állva kapja a labdát (csak "
                f"{rec221['running']}/{rec221['receptions']} átvétel "
                "mozgásból) — az álló beállót a védője lezárja, "
                "mielőtt megfordulna",
                "lefordulós átvétel: elzárás-leforduló párgyakorlat "
                "(a beálló az elzárásból kifordulva, mozgás közben "
                "kapja a bejátszást és egy ütemből fejez be) — az "
                "edzésmeccsen csak a mozgásból átvett beálló-gól ér "
                "pontot, az állva átvett labda visszajátszandó")
    except Exception:
        pass
    # 220) Keresztjáték: ha statikus a hátsó sorunk, a kereszt-
    # mozgások beépítése a téma.
    try:
        from .attack_types import crossing_runs
        crx220 = crossing_runs(match, config)
        for side in ("home", "away"):
            rec220 = crx220[side]
            if rec220["verdict"] != "statikus a hátsó soruk":
                continue
            add(side, "tamadas", "Keresztmozgások",
                f"támadásonként csak {rec220['per_attack']:.1f} "
                "keresztezést futunk a hátsó sorban — a védők végig "
                "a saját emberükön maradhatnak, és soha nem kerülnek "
                "váltás-döntés elé",
                "keresztmozgások: alap-keresztek gyakorlása "
                "(irányító-átlövő kereszt labdával és labda nélkül) — "
                "az edzésmeccsen minden felállt támadásban kötelező "
                "legalább egy kereszt a lövés előtt, és a kereszt "
                "utáni második hullám (a visszainduló ember) kapja a "
                "prémium-pontot")
    except Exception:
        pass

    # 219) Szélső-futtatás: ha a szélsőink állva kapják a labdát, a
    # futtatott széljáték a téma.
    try:
        from .attack_types import wing_service
        wsv219 = wing_service(match, config)
        for side in ("home", "away"):
            rec219 = wsv219[side]
            if rec219["verdict"] != "állva kapják a szélsők":
                continue
            add(side, "tamadas", "Futtatott széljáték",
                f"csak {rec219['running']}/{rec219['receptions']} "
                "szélső-átvételünk jött mozgásból — az álló szélsőt "
                "a kifutó védő lezárja, mielőtt lendületet venne, és "
                "a szögünk is szűkebb",
                "futtatott széljáték: időzítés-gyakorlat az átlövő "
                "és a szélső között — a szélső a passz INDULÁSAKOR "
                "lép be a sávba (nem előbb), a labda futtatva, a "
                "lépéskényszer előtt érkezik; az edzésmeccsen az "
                "állóhelyből átvett szélső-labda visszajár, hogy a "
                "mozgásból érkezés beépüljön")
    except Exception:
        pass

    # 218) Csere-lyukak: ha csere közben öten maradunk, a csere-ütem
    # a téma.
    try:
        from .substitutions import sub_gaps
        sbg218 = sub_gaps(match, config)
        for side in ("home", "away"):
            rec218 = sbg218[side]
            if rec218["verdict"] != "lyukas a cseréjük":
                continue
            add(side, "taktika", "Csere-ütem",
                f"összesen {rec218['gap_s']:.0f} másodpercig "
                "játszottunk öt mezőnyjátékossal csere közben — ez "
                "ingyen emberelőny az ellenfélnek, pont a gyors "
                "indításaik pillanatában",
                "csere-ütem: a ki- és belépő játékos a cserezónában "
                "kézjellel vált (a belépő már a zóna szélén áll, "
                "amikor a kilépő odaér) — az edzésmeccsen minden "
                "olyan másodperc, amíg öten vagyunk a pályán, "
                "hangosan számolva megy, és a lyukas csere azonnali "
                "labdavesztést ér")
    except Exception:
        pass

    # 217) Gólpassz-hossz: ha csak rövid kombinációkból élünk, a
    # hosszú indítás beépítése a téma.
    try:
        from .event_detection import assist_ranges
        asr217 = assist_ranges(match, config)
        for side in ("home", "away"):
            rec217 = asr217[side]
            if rec217["verdict"] != "rövid kombinációkból élnek":
                continue
            add(side, "tamadas", "Hosszú előkészítés",
                f"csak {rec217['long']}/{rec217['assisted']} "
                "gólpasszunk jött 8 méteren túlról — minden gólunk "
                "kis területen születik, és egy jól tömörítő fal az "
                "egész gólgyártásunkat megfojtja",
                "hosszú előkészítés: átemelés- és bejátszás-blokk — "
                "szélső-váltás hosszú kereszttel, beálló-etetés a "
                "9-esről, és kifutó-indítás a szélsőnek; az "
                "edzésmeccsen a 8 méteren túlról előkészített gól "
                "duplán számít, hogy a hosszú megoldás beépüljön")
    except Exception:
        pass

    # 216) Kapus-kipattanó: ha a kapusunk kiüti a labdát, a kipattanó-
    # irányítás a téma.
    try:
        from .goalkeeper import gk_rebound_control
        grc216 = gk_rebound_control(match, config)
        for side in ("home", "away"):
            rec216 = grc216[side]
            if rec216["verdict"] != "kiüti a labdát a kapusuk":
                continue
            add(side, "kapus", "Kipattanó-irányítás",
                f"csak {rec216['caught']}/{rec216['saves']} védés "
                "maradt a kapusunknál — a kiütött labda élő labda a "
                "kapunk előtt, és a rárohanó támadó a legolcsóbb "
                "gólt kapja",
                "kipattanó-irányítás: védés-technika blokk — a "
                "kiütés iránya SOHA nem középre, hanem a szélek felé "
                "vagy alapvonalon kívülre; a fal két szélső védője a "
                "lövésnél automatikusan a kipattanó-zónába lép, és a "
                "kapus hangosan jelzi (enyém/tiéd), kié a megült "
                "labda")
    except Exception:
        pass

    # 215) Kivárás-csapda: ha a hosszú támadásaink elhalnak, a
    # figura-zárás időzítése a téma.
    try:
        from .attack_types import long_attack_outcomes
        lao215 = long_attack_outcomes(match, config)
        for side in ("home", "away"):
            rec215 = lao215[side]
            if rec215["verdict"] != "a hosszú támadásaik elhalnak":
                continue
            add(side, "tamadas", "Figura-zárás időben",
                f"{rec215['died']}/{rec215['long_attacks']} hosszú "
                "támadásunk lövés nélkül halt el — a kivárásunk nem "
                "türelem, hanem terv-hiány: a passzív jel előtt nem "
                "jut el a labda lövő-helyzetig",
                "figura-zárás időben: 25 másodperces órával vívott "
                "támadás-gyakorlat — a figurának a 20. másodpercig "
                "kötelezően lövésig kell érnie, különben a labda az "
                "ellenfélé; minden figurához előre kimondott B-zárás "
                "tartozik (hetes-kényszerítő betörés vagy beállós), "
                "és az elhalt támadásokat a videón külön nézzük")
    except Exception:
        pass

    # 214) Felfutási létszám: ha mindenkit felküldünk, a biztosítás-
    # rend a téma.
    try:
        from .attack_types import attack_headcount
        ahc214 = attack_headcount(match, config)
        for side in ("home", "away"):
            rec214 = ahc214[side]
            if rec214["verdict"] != "mindenkit felküldenek":
                continue
            add(side, "taktika", "Biztosítás-rend",
                f"átlag {rec214['avg_up']:.1f} mezőnyjátékosunk van "
                "fent a támadásokban — a hátunk mögött üres a pálya, "
                "minden eladott labda és hosszú kidobás kontrát ér "
                "ellenünk",
                "biztosítás-rend: felállt támadásban mindig kijelölt "
                "biztosító ember marad a felező környékén (posztonként "
                "rögzítve, ki az) — az edzésmeccsen minden kontragól, "
                "amit üresen hagyott térfélről kapunk, duplán számít, "
                "és a biztosító hiányát a videón névre szólóan "
                "jelöljük")
    except Exception:
        pass

    # 213) Blokk-lepattanó: ha a blokkjaink visszahullanak, a blokk
    # utáni második mozdulat a téma.
    try:
        from .defense import block_recoveries
        brc213 = block_recoveries(match, config)
        for side in ("home", "away"):
            rec213 = brc213[side]
            if rec213["verdict"] != "a blokkjaik visszahullanak":
                continue
            add(side, "vedekezes", "Blokk utáni lepattanó",
                f"csak {rec213['recovered']}/{rec213['blocks']} "
                "blokk-lepattanót szereztünk meg — a jó blokk után a "
                "támadó második esélyt kap, sokszor még jobb "
                "helyzetből",
                "blokk utáni lepattanó: blokk-gyakorlat párban — a "
                "blokkoló a blokk után NEM nézi a labdát, hanem "
                "azonnal fordul és a lepattanó felé lép, a mögötte "
                "álló társ hangosan irányítja (hol a labda); a menet "
                "csak akkor pont, ha a blokk után a labda is a védőké")
    except Exception:
        pass

    # 212) Ziccer-befejezők: ha egy emberünk a nagy helyzeteket is
    # kihagyja, a ziccer-rutin a téma.
    try:
        from .xg import big_chance_finishers
        bcf212 = big_chance_finishers(match, config)
        for side in ("home", "away"):
            shaky212 = bcf212[side]["shaky"]
            if shaky212 is None:
                continue
            add(side, "tamadas", "Ziccer-rutin",
                f"a(z) {shaky212['player_id']} azonosítójú a nagy "
                f"helyzeteit is kihagyja "
                f"({shaky212['goals']}/{shaky212['chances']}) — a "
                "kihagyott ziccer duplán büntet: elmarad a gól, és "
                "kontra indul belőle",
                "ziccer-rutin: fáradt állapotban vívott befejezés-"
                "sorozat a hatosról — kapus ellen, időkényszerrel, és "
                "minden kihagyás után azonnali visszafutás; a "
                "döntést leegyszerűsítjük (két bevált befejezés "
                "sarkonként), és a videón a kihagyások mintáját "
                "külön nézzük vissza")
    except Exception:
        pass

    # 211) Hetes utáni percek: ha az adott hetes után is kapunk rá, a
    # hetes körüli újrarendeződés a téma.
    try:
        from .rules import post_seven_lapses
        psl211 = post_seven_lapses(match, config)
        for side in ("home", "away"):
            rec211 = psl211[side]
            if rec211["verdict"] is None:
                continue
            add(side, "vedekezes", "Hetes utáni újrarendeződés",
                f"{rec211['sevens_against']} adott hetesünk után "
                f"{rec211['extra_conceded']} további gólt kaptunk — a "
                "hetes körüli leállás alatt reklamálunk és "
                "átrendeződünk, az újraindítás pedig készületlenül "
                "ér minket",
                "hetes utáni újrarendeződés: minden edzésbeli hetes "
                "után kötelező 10 másodperces protokoll — a fal "
                "hangosan újraszámol (ki kit fog), a kapus jelzi a "
                "felállást, és a hetes kimenetelétől függetlenül "
                "azonnal éles védekezés következik; a reklamálás a "
                "gyakorlatban is azonnali hátrányt ér")
    except Exception:
        pass

    # 210) Labda-forgatás: ha egy irányba forgatunk, a kétirányú
    # játék a téma.
    try:
        from .attack_types import circulation_direction
        cir210 = circulation_direction(match, config)
        for side in ("home", "away"):
            rec210 = cir210[side]
            if rec210["verdict"] is None:
                continue
            _dir210 = ("balra" if rec210["verdict"] == "balra forgatnak"
                       else "jobbra")
            add(side, "tamadas", "Kétirányú forgatás",
                f"a forgásunk egyirányú ({rec210['left']} balra, "
                f"{rec210['right']} jobbra tartó oldalpassz) — a "
                "felkészült ellenfél a megszokott sávunkat zárja, és "
                "a kettőzést a forgás végpontjára időzíti",
                "kétirányú forgatás: figura-gyakorlás tükrözve — "
                "minden bejáratott figurát a másik oldalra is "
                "megtanulunk, és az edzésmeccsen kötelező a "
                "forgásváltás minden harmadik támadásban; a gyenge "
                "irányú átadásokat külön passz-blokk erősíti")
    except Exception:
        pass

    # 209) Elzárás-páros: ha a párosunk kiszámítható, a figura
    # variálása a téma.
    try:
        from .attack_types import screen_pairs
        scp209 = screen_pairs(match, config)
        for side in ("home", "away"):
            top209 = scp209[side]["top"]
            if top209 is None:
                continue
            add(side, "tamadas", "Elzárás-variálás",
                f"az elzárásaink egy párosra járnak (a(z) "
                f"{top209['setter_id']} zár a(z) "
                f"{top209['shooter_id']} azonosítójúnak, "
                f"{top209['shots']} közös lövés) — a felkészült "
                "ellenfél párban fog készülni, és az elzárásunk "
                "hatástalanná válik",
                "elzárás-variálás: ugyanaz az elzárás-figura három "
                "változatban — másik oldalra, másik lövővel, és "
                "ál-elzárással (a zár után leperdülés a kapura); az "
                "edzésmeccsen a fő páros csak minden harmadik "
                "elzárást játszhatja, hogy a többi változat is "
                "élessé váljon")
    except Exception:
        pass

    # 208) Szélső-kifutás: ha későn érünk ki a szélre, a kifutás-
    # időzítés a téma.
    try:
        from .defense import wing_closeouts
        wco208 = wing_closeouts(match, config)
        for side in ("home", "away"):
            rec208 = wco208[side]
            if rec208["verdict"] != "későn érnek ki a szélre":
                continue
            add(side, "vedekezes", "Szél-kifutás időzítése",
                f"átlag {rec208['avg_m']:.1f} m-re volt a védőnk a "
                "lövő szélsőtől — a szélső kényelmesen, teljes "
                "szögből lőhetett, és ez nem a kapus hibája",
                "szél-kifutás időzítése: oldalváltás-gyakorlat, ahol "
                "a szélső védő már a beadó passz LEVEGŐBEN LÉTEKOR "
                "indul (nem az átvételkor) — a cél az érkezés a "
                "lövő karjáig az első lendületvételre; minden késői "
                "kifutást a videón külön jelölünk, és a kapussal "
                "közös szög-zárás egészíti ki")
    except Exception:
        pass

    # 207) Csend-törők: ha a gólcsendjeinket mindig más töri meg
    # (nincs válság-lövőnk), a vész-megoldás kijelölése a téma.
    try:
        from .momentum import drought_breakers
        drb207 = drought_breakers(match, config)
        for side in ("home", "away"):
            rec207 = drb207[side]
            if rec207["droughts_broken"] < 2 or rec207["top"] is not None:
                continue
            add(side, "tamadas", "Válság-lövő kijelölése",
                f"{rec207['droughts_broken']} hosszú gólcsendünk volt, "
                "és mindig más törte meg — vész-helyzetben nincs "
                "kijelölt megoldásunk, a csend ezért nyúlik hosszúra",
                "válság-lövő kijelölése: két begyakorolt vész-figura "
                "egy megnevezett befejezővel — az edzésmeccsen minden "
                "3 perces gólcsend után kötelező a vész-figura, és a "
                "kijelölt lövő zárja; a szerep meccsenként előre "
                "kihirdetve, hogy csendben mindenki tudja, kihez "
                "megy a labda")
    except Exception:
        pass

    # 206) Forró kéz: ha az ellenfélnél sorozatlövő volt, a sorozat-
    # törő reakció a téma. (Saját oldalról: a forró kéz etetése.)
    try:
        from .momentum import hot_hands
        hh206 = hot_hands(match, config)
        for side in ("home", "away"):
            top206 = hh206["away" if side == "home" else "home"]["top"]
            if top206 is None:
                continue
            add(side, "vedekezes", "Sorozat-törő reakció",
                f"az ellenfél sorozatlövője ({top206['player_id']} "
                f"azonosító) {top206['streaks']} gólsorozatot dobott "
                f"ránk (leghosszabb: {top206['longest']}) — az első "
                "gólja után nem reagáltunk, és a második-harmadik "
                "már lendületből jött",
                "sorozat-törő reakció: edzésmeccsen minden kapott "
                "gól után hangos kijelölés (ki dobta, ki őrzi), és a "
                "gólszerzőre a következő védekezésben kötelező "
                "őrzés-váltás vagy korai kettőzés — a szabály "
                "beépüléséig a reakció elmaradása külön jelzést kap "
                "a videó-visszanézésen")
    except Exception:
        pass

    # 205) Kapus-hidegedés: ha a kapusunk hidegen sebezhető, a csendes
    # percek rutinja a téma.
    try:
        from .goalkeeper import gk_cold_streaks
        gcs205 = gk_cold_streaks(match, config)
        for side in ("home", "away"):
            rec205 = gcs205[side]
            if rec205["verdict"] != "hidegen sebezhető a kapusuk":
                continue
            add(side, "kapus", "Kapus-melegentartás",
                f"hosszú csend után {rec205['cold']['save_pct']:.0f}%, "
                f"ritmusban {rec205['warm']['save_pct']:.0f}% a "
                "kapusunk védés-aránya — pont az első, váratlan "
                "lövésnél a legdrágább a hidegség",
                "kapus-melegentartás: a csendes percekre aktivitás-"
                "rutin épül (mozgás a kapuban, hangos irányítás, "
                "falhoz igazítás) + edzésen szimulált csend-blokkok: "
                "3 perc lövés nélkül, majd előre nem jelzett első "
                "lövés — a menet csak akkor zárul, ha az első hideg "
                "lövésből három egymás után fogott")
    except Exception:
        pass

    # 204) Fal-magasság elleni játék: ha a felfutó fal megfog minket,
    # a prés elleni megoldások a téma.
    try:
        from .attack_types import attack_vs_wall_height
        avw204 = attack_vs_wall_height(match, config)
        for side in ("home", "away"):
            rec204 = avw204[side]
            if rec204["verdict"] != "a felfutó fal megfogja őket":
                continue
            add(side, "tamadas", "Prés elleni játék",
                f"felfutó fal ellen {rec204['high']['goal_pct']:.0f}%, "
                f"mély fal ellen {rec204['deep']['goal_pct']:.0f}% a "
                "gólarányunk — a kilépő, agresszív védekezésre nincs "
                "begyakorolt válaszunk, és az ellenfelek ezt előbb-"
                "utóbb észreveszik",
                "prés elleni játék: 3-2-1 elleni támadás-gyakorlat, "
                "ahol a kilépő védő MÖGÉ kötelező a folytatás — "
                "beállós-lecsúszás a kilépő helyére, egyérintős "
                "passz a felszabaduló emberre, és átemelés-gyakorlat "
                "a kapus fölött; a menet gólja csak a kilépő mögötti "
                "térből érvényes")
    except Exception:
        pass

    # 203) Kontra-forrás: ha a kapott kontrák egy forrásból jönnek, a
    # forrás-specifikus visszarendeződés a téma.
    try:
        from .attack_types import break_sources
        bsrc203 = break_sources(match, config)
        for side in ("home", "away"):
            other203 = bsrc203["away" if side == "home" else "home"]
            top203 = other203["top"]
            if top203 is None:
                continue
            add(side, "vedekezes", "Kontra-forrás zárása",
                f"az ellenfél kontráinak fő forrása a(z) "
                f"{top203['source']} volt ({top203['breaks']}/"
                f"{other203['breaks']} lerohanás) — a visszarendeződés "
                "általános gyakorlása helyett ezt az egy pillanatot "
                "kell megölni",
                "kontra-forrás zárása: forrás-specifikus átmenet-"
                "gyakorlat — védés-indulásnál a lövő azonnal a "
                "kapus-indítás sávjába zár vissza, kihagyott lövésnél "
                "a lepattanó után mindenki kötelezően hármat sprintel "
                "hátra, labdaszerzés-forrásnál pedig az átmeneti "
                "keresztpassz az edzésen is tiltott")
    except Exception:
        pass

    # 202) Kapus-gól veszély: ha az ellenfél kapusa dobott már ránk,
    # az üres kapu védése a téma. (Saját oldalon: gyakorolható fegyver.)
    try:
        from .goalkeeper import gk_goal_threat
        gkg202 = gk_goal_threat(match, config)
        for side in ("home", "away"):
            other202 = gkg202["away" if side == "home" else "home"]
            if other202["verdict"] is None:
                continue
            add(side, "taktika", "Üres kapu védése",
                f"az ellenfél kapusa gólveszélyes volt ellenünk "
                f"({other202['attempts']} kapura dobás, "
                f"{other202['goals']} gól) — a 7 a 6-unk alatt az "
                "üres kapunk nyitott célpont",
                "üres kapu védése: 7 a 6 gyakorlat, ahol "
                "labdavesztésnél egy előre kijelölt játékos (mindig "
                "a legközelebbi hátsó) azonnal a kapu síkjába "
                "sprintel — a kapus-átívelést a sávban álló ember "
                "blokkolja; a lövésünk pillanatában pedig senki nem "
                "fordít hátat a labdának")
    except Exception:
        pass

    # 201) Hosszú állás utáni játék: ha a megszakítások kizökkentenek
    # minket, az újraindulás-rutin a téma.
    try:
        from .stoppages import long_break_response
        lbr201 = long_break_response(match, config)
        for side in ("home", "away"):
            rec201 = lbr201[side]
            if rec201["verdict"] != "a hosszú állások kizökkentik őket":
                continue
            add(side, "taktika", "Újraindulás-rutin",
                f"a hosszú megszakítások utáni mérlegünk "
                f"{rec201['goals_for']}-{rec201['goals_against']} — "
                "a váratlan állás után hidegen és fejben máshol "
                "térünk vissza, és az első két perc rendre elúszik",
                "újraindulás-rutin: az edzésen váratlan 3 perces "
                "állásokat rendelünk el (mindenki leül), majd azonnal "
                "éles 2 perces szakasz jön, amelynek az eredményét "
                "külön mérjük — a visszatérésre kötelező protokoll "
                "épül: 30 mp mozgás, hangos feladat-egyeztetés, és "
                "az első támadás mindig begyakorolt figura")
    except Exception:
        pass

    # 200) Hajrá-labdabirtoklás: ha a végjátékunk egy kézben van, a
    # másodlagos játékszervezés a téma.
    try:
        from .momentum import clutch_ball_hogs
        cbh200 = clutch_ball_hogs(match, config)
        for side in ("home", "away"):
            top200 = cbh200[side]["top"]
            if top200 is None:
                continue
            add(side, "tamadas", "Második játékszervező",
                f"a hajrá labdás idejének nagy részét egy ember viszi "
                f"(a(z) {top200['player_id']} azonosítójú) — ha őt a "
                "végjátékban kettőzik vagy kipontozódik, nincs, aki "
                "átvegye a záró figurák szervezését",
                "második játékszervező: a hajrá-figurákat két "
                "indítási ponttal gyakoroljuk — ugyanaz a figura "
                "elindítható az irányítótól ÉS az átlövőtől is; az "
                "edzésmeccsek utolsó öt percében az első számú "
                "szervező kötelezően csali (labda nélkül köt le két "
                "védőt), és a záró támadást a második ember vezeti")
    except Exception:
        pass

    # 199) Negyedóra-profil: ha van visszatérő hullámvölgyünk, a
    # szakasz-terv a téma.
    try:
        from .momentum import quarter_profile
        qp199 = quarter_profile(match, config)
        for side in ("home", "away"):
            worst199 = qp199[side]["worst"]
            if worst199 is None:
                continue
            add(side, "taktika", "Negyedóra-terv",
                f"a(z) {worst199['quarter']}. negyedóra rendre "
                f"elúszik ({worst199['diff']} a gólkülönbségünk "
                "ott) — a meccseink egy órarendszerű hullámvölgyben "
                "dőlnek el, és ez tervezéssel kezelhető",
                "negyedóra-terv: a gyenge szakasz elejére előre "
                "beírt csere-hullám és egy kötelező időkérés-pont "
                "kerül (ha a különbség ott 2 fölé nő) — az "
                "edzésmeccseken ugyanezt a 15 percet emelt "
                "intenzitással játsszuk, hogy a hullámvölgy "
                "fiziológiás oka (frissesség, koncentráció) "
                "célzottan edzve legyen")
    except Exception:
        pass

    # 198) Beálló-őr: ha a beálló-őrzésünk egy emberen áll, az
    # őrzés-váltás a téma.
    try:
        from .defense import pivot_guards
        pvg198 = pivot_guards(match, config)
        for side in ("home", "away"):
            top198 = pvg198[side]["top"]
            if top198 is None:
                continue
            add(side, "vedekezes", "Beálló-őrzés váltásban",
                f"a beálló-őrzésünk egy emberen áll (a(z) "
                f"{top198['player_id']} azonosítójú viszi az őrzés-idő "
                "nagy részét) — ha őt elzárással kihúzzák vagy "
                "kipontozódik, a belső védekezésünk borul",
                "beálló-őrzés váltásban: 6-0 elleni gyakorlat, ahol a "
                "két belső védő KÖTELEZŐEN váltja a beállót minden "
                "átjátszásnál (elöl-mögött csere hangos jelzéssel) — "
                "a menet hibája, ha a beálló kettő másodpercnél "
                "tovább marad ugyanannál az őrzőnél elzárás után, és "
                "a gyakorlat végén a szélső védő is beáll egy "
                "váltás-sorra")
    except Exception:
        pass

    # 197) Időkérés-csomag: ha az időkérésünk sosem jár cserével, a
    # kispad-eszköztár bővítése a téma.
    try:
        from .stoppages import timeout_sub_combo
        tsc197 = timeout_sub_combo(match, config)
        for side in ("home", "away"):
            rec197 = tsc197[side]
            if rec197["verdict"] != "az időkérésük tiszta taktika":
                continue
            add(side, "taktika", "Időkérés-eszköztár",
                f"az időkéréseink ({rec197['timeouts']}) szinte soha "
                "nem járnak cserével — a szünet csak szóbeli "
                "utasítás, pedig a friss láb és az új párosítás "
                "legalább akkora fegyver, mint az új figura",
                "időkérés-eszköztár: az edzésmeccseken minden "
                "időkéréshez kötelező döntés-lista jár (kit "
                "cserélünk, kire megy az új kettőzés, mi az első "
                "figura) — a kispad 30 másodperc alatt mondja ki "
                "mindhármat, és az időkérés utáni első támadás/"
                "védekezés párosát külön visszanézzük")
    except Exception:
        pass

    # 196) Lövés-választás állás szerint: ha hátrányban elkapkodjuk a
    # lövéseket, a nyomás alatti helyzet-válogatás a téma.
    try:
        from .xg import shot_quality_by_score
        sqs196 = shot_quality_by_score(match, config)
        for side in ("home", "away"):
            rec196 = sqs196[side]
            if rec196["verdict"] != "hátrányban elkapkodják a lövéseket":
                continue
            add(side, "tamadas", "Helyzet-válogatás nyomás alatt",
                f"hátrányban {rec196['other_avg_xg']:.2f}-ról "
                f"{rec196['trail_avg_xg']:.2f}-ra esik a lövéseink "
                "átlagos helyzet-értéke — pont akkor lövünk rosszat, "
                "amikor minden támadás számít, és a kis esélyű "
                "lövés duplán büntet: nem lesz gól, és kontra jön "
                "belőle",
                "helyzet-válogatás nyomás alatt: hátrányból (0-2) "
                "induló edzésmeccs, ahol csak a 0,3 feletti "
                "helyzet-értékű lövés ér gólt (a kispad hangosan "
                "minősíti: zöld/piros) — két piros lövés után a "
                "támadó sor büntető-visszafutást fut, és a menet "
                "csak türelmes, kidolgozott góllal zárható")
    except Exception:
        pass

    # 195) Kapus állás szerint: ha a kapusunk hátrányban összeesik, a
    # mentális újraindítás a téma.
    try:
        from .goalkeeper import gk_saves_by_score
        gks195 = gk_saves_by_score(match, config)
        for side in ("home", "away"):
            rec195 = gks195[side]
            if rec195["verdict"] != "hátrányban összeesik a kapusuk":
                continue
            add(side, "kapus", "Kapus-újraindítás",
                f"hátrányban {rec195['trail']['save_pct']:.0f}%-ra "
                f"esik a kapusunk védés-aránya (a szokásos "
                f"{rec195['other']['save_pct']:.0f}% helyett) — pont "
                "akkor fogy el, amikor a csapatnak a legnagyobb "
                "szüksége lenne rá",
                "kapus-újraindítás: rutin-protokoll kapott gól utánra "
                "(kortyolás, sapka-igazítás, egy kulcsszó a "
                "beállásra) + hátrány-szimulált védés-sorozat: az "
                "edző 0-2-es állást hirdet, és a kapus csak akkor "
                "zárhatja a menetet, ha egymás után két lövést "
                "megfog — a bravúr-élmény hátrányban is beépül")
    except Exception:
        pass

    # 194) Szorult játék: ha hátrányban beszűkülünk, a nyomás alatti
    # szélesség-tartás a téma.
    try:
        from .attack_types import width_by_score
        wbs194 = width_by_score(match, config)
        for side in ("home", "away"):
            rec194 = wbs194[side]
            if rec194["verdict"] != "hátrányban beszűkülnek":
                continue
            add(side, "tamadas", "Szélesség nyomás alatt",
                f"hátrányban {rec194['other_avg_m']:.0f} m-ről "
                f"{rec194['trail_avg_m']:.0f} m-re szűkül a "
                "támadásunk — pont akkor játszunk egy csatornába, "
                "amikor a legnagyobb szükség lenne a fal "
                "széthúzására",
                "szélesség nyomás alatt: eredményhátrányból induló "
                "edzésmeccs (0-2-ről), ahol gól csak akkor ér, ha a "
                "támadásban a labda mindkét szélsőt megjárta — a "
                "szélső-sávok elhagyása azonnali labdavesztés, és a "
                "kispad hangosan számolja a szélesség-métert")
    except Exception:
        pass

    # 193) Visszaállás: ha a kiállításunk leteltekor megzavarodunk, a
    # visszaérkezés koreográfiája a téma.
    try:
        from .rules import post_powerplay
        ppp193 = post_powerplay(match, config)
        for side in ("home", "away"):
            rec193 = ppp193[side]
            if rec193["verdict"] != "a visszaállásnál megzavarodnak":
                continue
            add(side, "taktika", "Visszaállás-rend",
                f"a kiállításaink letelte utáni perc mérlege "
                f"{rec193['goals_for']}-{rec193['goals_against']} — "
                "a visszaérő ember hidegen jön, a felállás egy "
                "percig rendezetlen, és az ellenfél pont ide időzíti "
                "a támadását",
                "visszaállás-rend: emberhátrány-gyakorlat, amelyben a "
                "visszaérkezés is koreografált — a visszaérő ember "
                "MINDIG ugyanoda áll be (szélre), a fal belülről "
                "tömörít kifelé, és az első védekezésben tilos a "
                "kilépés; támadásban a visszaérés utáni első labda "
                "kötelezően biztonsági, begyakorolt figurába megy")
    except Exception:
        pass

    # 192) Poszt-hibák: ha egy posztunk szórja a labdát, a poszt-
    # specifikus labdabiztonság a téma.
    try:
        from .roles import turnovers_by_role
        tbr192 = turnovers_by_role(match, config)
        for side in ("home", "away"):
            top192 = tbr192[side]["top"]
            if top192 is None:
                continue
            add(side, "tamadas", "Poszt-labdabiztonság",
                f"a labdaeladásaink {top192['share_pct']:.0f}%-a a(z) "
                f"{top192['poszt']} posztról jön "
                f"({top192['turnovers']} eladás) — nem szétszórt "
                "hiba, hanem egy poszt sávját olvassa az ellenfél",
                "poszt-labdabiztonság: az érintett poszt kap célzott "
                "blokkot — beállónál kétkezes átvétel-gyakorlat "
                "kontakt alatt, irányítónál passz-csel és sávváltás "
                "kettőzés ellen, szélsőnél a bejátszás időzítése a "
                "kifutó védő mögé; a blokk végén 5-5, ahol az adott "
                "poszt hibája két pontot ér az ellenfélnek")
    except Exception:
        pass

    # 191) Futás-mérleg: ha az ellenfél túlfut minket, az alap-
    # állóképesség és az okos futás a téma.
    try:
        from .stats import distance_battle
        dbt191 = distance_battle(match, config)
        for side in ("home", "away"):
            rec191 = dbt191[side]
            if rec191["verdict"] != "túlfutja őket az ellenfél":
                continue
            add(side, "taktika", "Futás-mérleg",
                f"az ellenfél túlfutott minket (a mezőnyünk "
                f"{rec191['distance_m']:.0f} métert tett meg, "
                "érdemben kevesebbet, mint ők) — a második labdákra "
                "és a visszazárásba rendre később érünk oda, és ez "
                "nem taktika kérdése, hanem lábé",
                "futás-mérleg: intervallum-alap növelése (heti két "
                "futóblokk meccstempó feletti szakaszokkal) + okos "
                "futás gyakorlat — a támadás-befejezés után az első "
                "három lépés KÖTELEZŐEN sprint hátra, és a "
                "videó-visszanézésen a sétáló visszazárásokat névre "
                "szólóan jelöljük")
    except Exception:
        pass

    # 190) Egyirányú játékosok: ha váltott sorokkal játszunk, a
    # váltás-ütem a téma.
    try:
        from .roles import phase_specialists
        phs190 = phase_specialists(match, config)
        for side in ("home", "away"):
            rec190 = phs190[side]
            if rec190["verdict"] != "váltott sorokkal játszanak":
                continue
            add(side, "taktika", "Sorváltás-ütem",
                "váltott sorokkal játszunk (külön védekező és támadó "
                "egység) — a fegyver csak akkor él, ha a váltás "
                "gyorsabb, mint az ellenfél átmenete: minden lassú "
                "csere egy ütemre rossz felállást hagy a pályán",
                "sorváltás-ütem: átmenet-gyakorlat stopperrel, ahol a "
                "váltó egység már a lövésünk pillanatában a "
                "cserezónánál áll — a cél, hogy a teljes sorváltás a "
                "labda térfél-átérése ELŐTT lezáruljon; a "
                "gyakorlatvezető időnként gyors középkezdést rendel "
                "el, és minden fent ragadt embert névre szólóan "
                "jelzünk")
    except Exception:
        pass

    # 189) Sprint-veszély: ha a kontra-teher egy emberen van, a
    # második hullám bekapcsolása a téma.
    try:
        from .stats import sprint_threats
        spt189 = sprint_threats(match, config)
        for side in ("home", "away"):
            rec189 = spt189[side]
            if rec189["verdict"] != "kijelölt kontra-emberük van":
                continue
            top189 = rec189["top"]
            add(side, "tamadas", "Kontra második hulláma",
                f"a csapat {rec189['team_sprints']} sprintjéből "
                f"{top189['sprints']} egy emberé (a(z) "
                f"{top189['player_id']} azonosítójú) — ha őt lezárják "
                "vagy elfárad, a gyors ellentámadásunk megszűnik, "
                "mert nincs, aki átvegye",
                "kontra második hulláma: indítás-gyakorlat, ahol az "
                "első kifutót a gyakorlatvezető rendre LEZÁRJA — a "
                "labda kötelezően a második hullámra megy (belső "
                "emberek felfutása), és minden szélső megtanulja a "
                "kifutó szerepet; a sprint-terhet félidőnként "
                "számoljuk, és a kispad tudatosan váltja a kifutókat")
    except Exception:
        pass

    # 188) Hetesre cserélt kapus: ha specialistát hozunk a büntetőkre,
    # a beugró kapus bemelegítése és a visszaállás a téma.
    try:
        from .goalkeeper import seven_keeper_swaps
        svk188 = seven_keeper_swaps(match, config)
        for side in ("home", "away"):
            rec188 = svk188[side]
            if rec188["verdict"] != "hetesre kapust cserélnek":
                continue
            add(side, "kapus", "Hetes-kapus rutin",
                f"az ellenünk ítélt {rec188['sevens_against']} "
                f"hetesből {rec188['swaps']}-nál cseréltünk kapust — "
                "a fegyver csak akkor él, ha a beugró hidegen is "
                "hozza a formáját, és a visszacsere nem hagy üres "
                "kaput az újraindításnál",
                "hetes-kapus rutin: a beugró kapus edzésen is "
                "hidegről érkezik a hetes-sorozatokra (kerékpár vagy "
                "várakozás után azonnal a kapuba), a csere-ütemet "
                "pedig órával gyakoroljuk — beállás, védés, "
                "visszaállás úgy, hogy a gyors középkezdésnél már a "
                "mezőnykapus áll bent")
    except Exception:
        pass

    # 187) Kilépő védő: ha előretolt emberrel védekezünk, a mögötte
    # lévő tér biztosítása a téma.
    try:
        from .defense import advanced_defender
        adv187 = advanced_defender(match, config)
        for side in ("home", "away"):
            top187 = adv187[side]["top"]
            if top187 is None:
                continue
            add(side, "vedekezes", "Kilépő mögötti biztosítás",
                f"kilépő védővel játszunk (a(z) "
                f"{top187['player_id']} azonosítójú "
                f"{adv187[side]['gap_m']:.1f} méterrel a sor előtt "
                "áll) — a kilépés csak akkor ér valamit, ha a háta "
                "mögötti teret a sor zárja, különben ott ingyen "
                "kapunk beállós-gólt",
                "kilépő mögötti biztosítás: 5-1 elleni támadás-"
                "gyakorlat, ahol a támadók KÖTELEZŐEN a kilépő háta "
                "mögé játszanak — a két belső védő hangosan vált "
                "(ki csúszik be a beállóra), a kilépő pedig "
                "megtanulja, mikor kell visszazárnia; a menet hibája "
                "minden szabad labda a kilépő mögötti sávban")
    except Exception:
        pass

    # 186) Középkezdés-átvevő: ha a saját újraindításunk egy emberre
    # jár, a középkezdés-variálás a téma.
    try:
        from .momentum import restart_targets
        rst186 = restart_targets(match, config)
        for side in ("home", "away"):
            top186 = rst186[side]["top"]
            if top186 is None:
                continue
            add(side, "taktika", "Középkezdés-variálás",
                f"a kapott gól utáni újraindításaink egy emberre "
                f"járnak (a(z) {top186['player_id']} azonosítójú "
                f"vette át {top186['takes']} alkalommal) — a "
                "felkészült ellenfél pont őt fogja le a felezőnél, "
                "és a gyors középkezdésünk megáll",
                "középkezdés-variálás: újraindítás-gyakorlat két "
                "bejáratott átvevővel és egy harmadik, üresen "
                "kifutó emberrel — a kezdő játékos a letámadás "
                "képére dönt (fogott átvevő = azonnali hosszú a "
                "kifutóra), és minden ismétlésben más veszi át a "
                "labdát, hogy ne legyen olvasható minta")
    except Exception:
        pass

    # 185) Váltópárok: ha a cserénk kiszámítható, a csere-variálás a
    # téma.
    try:
        from .substitutions import swap_pairs
        swp185 = swap_pairs(match, config)
        for side in ("home", "away"):
            top185 = swp185[side]["top"]
            if top185 is None:
                continue
            add(side, "taktika", "Csere-variálás",
                f"a cserénk kiszámítható: a(z) {top185['out_id']} "
                f"azonosítójút {top185['count']} alkalommal is "
                f"ugyanaz váltotta — a felkészült ellenfél előre "
                "tudja, ki jön, és kész tervvel várja a beállót",
                "csere-variálás: az edzésmeccseken a kulcsposztokra "
                "két különböző váltó készül (más profillal: egy "
                "lövő és egy játékszervező), és a meccsterv "
                "helyzethez köti, melyik jön — előnyben a szervező, "
                "hajrában vagy hátrányban a lövő; a beálló első "
                "labdájára kötelező előre megbeszélt figura, hogy ne "
                "az ellenfél terve érvényesüljön")
    except Exception:
        pass

    # 184) Visszahozott támadások: ha minden betörésünket visszahozzuk,
    # a lezárás-bátorság a téma.
    try:
        from .attack_types import pullback_rate
        pb184 = pullback_rate(match, config)
        for side in ("home", "away"):
            rec184 = pb184[side]
            if rec184["verdict"] != "behúzzák, aztán visszahozzák":
                continue
            add(side, "tamadas", "Betörés-lezárás",
                f"a {rec184['entries']} betörésünkből "
                f"{rec184['pullbacks']} lövés nélküli visszahozás — "
                "bejutunk a 9-esen belülre, de nem merjük lezárni, "
                "így a fal újra összeáll, és jön a passzív jel",
                "betörés-lezárás: 9-esen belüli döntés-gyakorlat — a "
                "betörő KÖTELEZŐEN lezár (lövés vagy beállós-passz), "
                "visszapassz a 9-esen belülről tilos; kapus és fal "
                "ellen megy, és minden visszahozott labda az "
                "ellenfélnek jár, hogy a visszafordulás árát a "
                "gyakorlat is megmutassa")
    except Exception:
        pass

    # 183) Szerzés utáni indítás: ha a szerzett labda helyben ragad, az
    # átmenet-gyorsaság a téma.
    try:
        from .defense import steal_launch
        stl183 = steal_launch(match, config)
        for side in ("home", "away"):
            rec183 = stl183[side]
            if rec183["verdict"] != "szerzés után biztosítanak":
                continue
            add(side, "tamadas", "Szerzésből indítás",
                f"a {rec183['steals']} szerzésünkből csak "
                f"{rec183['forward']} után ment azonnal előre a labda "
                "— a megszerzett labda helyben ragad, mire felnézünk, "
                "az ellenfél visszaér, és kezdődik az állóháború",
                "szerzésből indítás: labdaszerzés-játék, ahol a "
                "szerzés utáni 3 másodpercben kötelező az előre "
                "passz vagy a labdavezetés a felezőn túlra — ha nem "
                "sikerül, a labda visszajár; a szerző NEM passzolhat "
                "hátra, és a két szélső a szerzés pillanatában "
                "sprintet indít, hogy legyen kinek előre adni")
    except Exception:
        pass

    # 182) Hetes-fáradás: ha fáradtan adjuk a heteseket, a kéz nélküli
    # test-védekezés a téma.
    try:
        from .rules import sevens_fade
        s7f182 = sevens_fade(match, config)
        for side in ("home", "away"):
            rec182 = s7f182[side]
            if rec182["verdict"] != "a második félidőben adják a heteseket":
                continue
            add(side, "vedekezes", "Hetes nélküli hajrá",
                f"az adott heteseink zöme a második félidőre esik "
                f"({rec182['fh']} az elsőben, {rec182['sh']} a "
                "másodikban) — fáradva már kézzel védünk, és a "
                "kapkodó belenyúlás hetest meg időleges emberhátrányt "
                "ér",
                "hetes nélküli hajrá: fáradt állapotban (futás vagy "
                "kör-edzés után) 6-0 elleni test-védekezés, ahol a "
                "kéz a hát mögött van — labdát csak lábmunkával, "
                "testtel lehet fogni; minden kézzel belenyúlás "
                "azonnali hetes a gyakorlatban is, és a menet csak "
                "három tiszta zárás után áll meg")
    except Exception:
        pass

    # 181) Fal-fáradás: ha a falunk a második félidőre kinyílik, a
    # védekezés állóképessége a téma.
    try:
        from .xg import wall_fade
        wf181 = wall_fade(match, config)
        for side in ("home", "away"):
            rec181 = wf181[side]
            if rec181["verdict"] != "a második félidőre kinyílik a faluk":
                continue
            add(side, "vedekezes", "Fal-állóképesség",
                f"a kapott lövések átlagos helyzet-értéke "
                f"{rec181['fh_avg_xga']:.2f}-ról "
                f"{rec181['sh_avg_xga']:.2f}-ra nő a szünet után — "
                "nem több lövést kapunk, hanem egyre jobbakat: a "
                "fáradó lábak késve lépnek, és a fal a hatos előtt "
                "nyílik ki",
                "fal-állóképesség: védekezés-gyakorlat fáradtan — "
                "kör-edzés vagy futás UTÁN 6-0 elleni védekezés, "
                "ahol csak az számít hibának, ha a hatos előtt "
                "szabad lövés születik; a belső védők párban "
                "beszélnek (átadás hangosan), és a menet addig tart, "
                "amíg három tiszta zárás össze nem jön")
    except Exception:
        pass

    # 180) Pad-gólok: ha csak a kezdők termelnek, a második sor
    # gólbátorsága a téma.
    try:
        from .momentum import bench_scoring
        ben180 = bench_scoring(match, config)
        for side in ("home", "away"):
            rec180 = ben180[side]
            if rec180["verdict"] != "csak a kezdők termelnek":
                continue
            add(side, "tamadas", "Pad-termelés",
                f"a {rec180['goals']} lövőhöz köthető gólunkból csak "
                f"{rec180['bench_goals']} jött a padról — ha a kezdő "
                "sor elfárad vagy kipontozódik, nincs, aki átvegye a "
                "gólfelelősséget",
                "pad-termelés: edzésmeccs, ahol a második sor zárja "
                "mindkét félidőt, és az utolsó öt perc gólja duplán "
                "számít — a padról beállók kapják a kijelölt "
                "figurákat, és minden beálló első támadásában "
                "kötelező a lövésig vitt megoldás, hogy a "
                "gólbátorság beépüljön")
    except Exception:
        pass

    # 179) Labdaszerzés-típus: ha minden szerzésünk testre menő
    # szerelés, a passzsáv-olvasás a téma.
    try:
        from .defense import steal_types
        stt179 = steal_types(match, config)
        for side in ("home", "away"):
            rec179 = stt179[side]
            if rec179["verdict"] != "testre mennek":
                continue
            add(side, "vedekezes", "Passzsáv-olvasás",
                f"a {rec179['steals']} labdaszerzésünkből csak "
                f"{rec179['interceptions']} röptében elfogott passz — "
                "mindent kontaktból szerzünk, ami fault és kiállítást "
                "kockáztat, miközben az elfogott passz ingyen "
                "indítást adna",
                "passzsáv-olvasás: árnyék-védekezés gyakorlat, ahol a "
                "védő NEM érhet a támadóhoz — labdát csak a passzsávba "
                "lépve szerezhet; a támadók kötelezően keresztbe "
                "járatnak, a védők a passzoló válla és szeme alapján "
                "mozdulnak, és minden elfogás után azonnali indítás "
                "zárja a menetet")
    except Exception:
        pass

    # 178) Kapott helyzetek minősége: ha a falunk nagy helyzeteket
    # enged, a hatos előtti tér védése a téma.
    try:
        from .xg import conceded_chance_quality
        ccq178 = conceded_chance_quality(match, config)
        for side in ("home", "away"):
            rec178 = ccq178[side]
            if rec178["verdict"] != "nagy helyzeteket engednek":
                continue
            add(side, "vedekezes", "Hatos előtti tér",
                f"a ránk jövő {rec178['shots']} lövés átlagos "
                f"helyzet-értéke {rec178['avg_xga']:.2f} — nem a "
                "lövések SZÁMA a baj, hanem hogy közelről és "
                "szemből engedjük őket, ami a kapusnak is "
                "védhetetlen",
                "hatos előtti tér: beállós elleni 6-0 gyakorlat, "
                "ahol a két belső védő MINDIG szendvicsben tartja a "
                "beállót, és az áttörő elé a szomszéd lép be "
                "(kettőzés) — a szabály, hogy a hatos előtti sávban "
                "senki nem kaphat szabad labdát; minden beengedett "
                "közeli lövés után a fal újra felállva ismétel")
    except Exception:
        pass

    # 177) Félidő-zárás: ha a dudaszó előtti utolsó labda elhal, a
    # záró támadás rutinja a téma.
    try:
        from .momentum import closing_attacks
        clo177 = closing_attacks(match, config)
        for side in ("home", "away"):
            rec177 = clo177[side]
            if rec177["verdict"] != "elpuskázzák a záró labdát":
                continue
            add(side, "tamadas", "Záró labda",
                f"a félidők utolsó percében {rec177['attacks']} "
                f"támadásunkból csak {rec177['goals']} lett gól — az "
                "ingyen kapott utolsó labdát dobjuk el, pedig ott "
                "nincs kockázat: rosszabb, mint a semmi, csak a korai "
                "lövés",
                "záró labda: óra elleni gyakorlat — 45 másodperc a "
                "kijelzőn, egy támadás, és a szabály, hogy a lövés "
                "csak az utolsó 8 másodpercben jöhet; a figurát "
                "előre kimondjuk, a kapus is beáll támadóban, és "
                "minden korai lövés büntetése visszafutás")
    except Exception:
        pass

    # 176) Lerohanás-hatékonyság: ha a kontráink nem érnek gólt, a
    # befejezés-döntés a téma.
    try:
        from .attack_types import fast_break_conversion
        fbc176 = fast_break_conversion(match, config)
        for side in ("home", "away"):
            rec176 = fbc176[side]
            if rec176["verdict"] != "elpuskázzák a kontrát":
                continue
            add(side, "tamadas", "Kontra-befejezés",
                f"{rec176['breaks']} lerohanásból csak "
                f"{rec176['goals']} lett gól "
                f"({rec176['share_pct']:.0f}%) — a legolcsóbb "
                "gólhelyzeteinket dobjuk el, pedig ott már csak egy "
                "döntés van hátra",
                "kontra-befejezés: 2-1 és 3-2 fogyó létszámú "
                "gyakorlat futásból, fáradtan — a szabály, hogy a "
                "labdás a kapus MOZDULÁSÁIG nem dönt, és minden "
                "menetben ki kell mondani a döntést (passz vagy "
                "lövés); minden kihagyás után azonnali "
                "visszarendeződés-sprint")
    except Exception:
        pass

    # 175) Félidő-nyitás: ha a félidők első perceiben rendre
    # hátrányba kerülünk, a kezdés rutinja a téma.
    try:
        from .momentum import half_openings
        hop175 = half_openings(match, config)
        for side in ("home", "away"):
            rec175 = hop175[side]
            if rec175["verdict"] != "lassan indulnak":
                continue
            add(side, "jatek", "Félidő-nyitás",
                f"a félidők első öt percében {rec175['goals_for']}-"
                f"{rec175['goals_against']} a mérlegünk — a meccs "
                "elején és a szünet után hideg lábbal, kész terv "
                "nélkül kezdünk, és utána végig kergetünk",
                "félidő-nyitás: edzés-végi \"első öt perc\" blokk — "
                "teljes bemelegítés után élesben induló 5 perces "
                "meccsrész, előre kiosztott kezdő hetessel és két "
                "megbeszélt nyitó figurával; a szünet utáni kezdést "
                "külön is gyakoroljuk: 10 perc állás (öltözői "
                "beszéd) után azonnal éles kezdés")
    except Exception:
        pass

    # 174) Időkérés utáni védekezés: ha az időkérésünk után rendre
    # gólt kapunk, a megszakítás utáni védekezés-rend a téma.
    try:
        from .stoppages import timeout_first_defense
        tfd174 = timeout_first_defense(match, config)
        for side in ("home", "away"):
            rec174 = tfd174[side]
            if rec174["verdict"] != "időkérés után szivárgó fal":
                continue
            add(side, "vedekezes", "Időkérés utáni védekezés",
                f"az időkéréseink {rec174['share_pct']:.0f}%-a után "
                "gólt kaptunk az ellenfél első rohamából — a "
                "megszakítás alatt a támadást beszéljük meg, a "
                "védekezés-feladatokat nem, és a hideg lábból induló "
                "fal az első rohamnál a leglassabb",
                "időkérés utáni védekezés: edzésen minden "
                "figura-megbeszélés UTÁN a védekezés következik — a "
                "kispadról induló 6-6, ahol a megszakítás után az "
                "ELSŐ feladat a kiosztás hangos ismétlése (ki megy a "
                "beállóra, ki a lövőre), és csak a második labdánál "
                "jön a saját támadás")
    except Exception:
        pass

    # 173) Gól utáni letámadás: ha a saját gólunk után magasabban
    # védekezünk, a letámadás-rend és a mögötte lévő tér a téma.
    try:
        from .defense import press_after_goal
        pag173 = press_after_goal(match, config)
        for side in ("home", "away"):
            rec173 = pag173[side]
            if rec173["verdict"] != "gól után letámadnak":
                continue
            add(side, "vedekezes", "Gól utáni letámadás",
                f"saját gólunk után {rec173['after_m']:.1f} m-en áll a "
                f"falunk a szokásos {rec173['base_m']:.1f} m helyett — "
                "ez jó lendület, de a mögöttünk lévő tér ilyenkor a "
                "legnagyobb, és egy hosszú kapus-indítás ki is "
                "használja",
                "gól utáni letámadás: 6-6 gyakorlat, ahol minden "
                "góllövés UTÁN azonnal letámadásba fordul a csapat — "
                "a labdásra kettőzés, a kapus-passz sávja zárva, és "
                "EGY kijelölt ember hátul marad a hosszú indításra; "
                "két elveszett labda után visszaállunk, hogy a "
                "határa is gyakorolt legyen")
    except Exception:
        pass

    # 172) Felhozatal-idő: ha lassan hozzuk fel a labdát, az ellenfél
    # rendezetten felállhat — a gyors kihozatal a téma.
    try:
        from .attack_types import buildup_time
        but172 = buildup_time(match, config)
        for side in ("home", "away"):
            rec172 = but172[side]
            if rec172["verdict"] != "lassan hozzák fel":
                continue
            add(side, "tamadas", "Gyors felhozatal",
                f"átlag {rec172['avg_s']:.1f} mp alatt érünk át a "
                "támadó térfélre — ennyi idő alatt bármelyik "
                "ellenfél rendezetten felállhat, így minden "
                "támadásunk állóháborúban indul",
                "gyors felhozatal: kihozatal-gyakorlat stopperrel, a "
                "cél a felezővonal 4 másodpercen belül — a labda "
                "előre megy, nem oldalra (első passz mindig a "
                "leghosszabb szabad társnak), a szélsők azonnal "
                "szélesre nyitnak, és minden negyedik ismétlés "
                "üresen hagyott ellenfél-térfélről indul, hogy a "
                "lerohanás-döntés is beleférjen")
    except Exception:
        pass

    # 171) Kapus-bevonás: ha sokat játszunk vissza, a kapus
    # labdabiztonsága és a kihozatal-rend a téma.
    try:
        from .goalkeeper import keeper_involvement
        kiv171 = keeper_involvement(match, config)
        for side in ("home", "away"):
            rec171 = kiv171[side]
            if rec171["verdict"] != "sokat játszanak vissza":
                continue
            add(side, "kapus", "Kapus a kihozatalban",
                f"a birtoklásaink {rec171['share_pct']:.0f}%-ában "
                "megjárta a labda a kapust — ez a labda a "
                "legolvashatóbb, és egy letámadó ellenfél pont ide "
                "küldi a második emberét",
                "kapus a kihozatalban: kihozatal-gyakorlat "
                "letámadással, ahol a kapus KÉT megoldást gyakorol — "
                "rövid, oldalra vezetett passz a felszabaduló "
                "szélsőnek, és hosszú indítás a felezővonal mögé; a "
                "döntést a letámadó második ember helyzete adja, és "
                "a kapusnak hangosan kell jeleznie")
    except Exception:
        pass

    # 170) Fedezetten lövők: ha valaki nyomás alatt is elhúzza a
    # ravaszt, a lövés-választás a téma.
    try:
        from .defense import covered_shooters
        cov170 = covered_shooters(match, config)
        for side in ("home", "away"):
            top170 = cov170[side]["top"]
            if top170 is None:
                continue
            who170 = (f"a {top170['jersey']}-es mezszámú játékos"
                      if top170.get("jersey") is not None
                      else f"a {top170['player_id']} azonosítójú játékos")
            pct170 = 100.0 * top170["covered"] / top170["shots"]
            add(side, "támadás", "Lövés-választás nyomás alatt",
                f"{who170} lövéseinek {pct170:.0f}%-a fedezetten "
                f"ment el ({top170['covered']}/{top170['shots']}) — a "
                "fedezett lövés alacsony értékű befejezés, és az "
                "ellenfél pont ezt engedi neki",
                "lövés-választás nyomás alatt: felállt támadás "
                "azzal a szabállyal, hogy fedezett helyzetből TILOS "
                "lőni — a labdának tovább kell mennie, és csak a "
                "kiugratásból vagy elzárás utáni szabad helyzetből "
                "jöhet a befejezés; a gyakorlat a fedezett lövést "
                "eladásként számolja")
    except Exception:
        pass

    # 169) Pressz-érzékeny játékosok: ha valakinél a szorítás eladás,
    # a nyomás alatti kiadás a téma.
    try:
        from .decisions import pressure_sensitive_players
        psp169 = pressure_sensitive_players(match, config)
        for side in ("home", "away"):
            top169 = psp169[side]["top"]
            if top169 is None:
                continue
            who169 = (f"a {top169['jersey']}-es mezszámú játékos"
                      if top169.get("jersey") is not None
                      else f"a {top169['player_id']} azonosítójú játékos")
            pct169 = (100.0 * top169["press_to"]
                      / top169["press_events"])
            add(side, "támadás", "Nyomás alatti kiadás",
                f"{who169} nyomott döntéseinek {pct169:.0f}%-a "
                f"eladás lett ({top169['press_to']}/"
                f"{top169['press_events']}) — egy felkészült ellenfél "
                "rá küldi a kettőzést, és onnan indítja a kontrát",
                "nyomás alatti kiadás: 2 az 1 elleni gyakorlat, ahol "
                "a labdást testközelből szorítják — a szabály, hogy "
                "a labda EGY érintéssel megy tovább a szabad társhoz, "
                "és a passz a szorítás ELLENKEZŐ oldalára indul; "
                "utána ugyanez fáradtan, kiabálás mellett")
    except Exception:
        pass

    # 168) Elöl szerző védők: ha van ilyen emberünk, a letámadás
    # köré lehet védekezést építeni.
    try:
        from .defense import high_steal_players
        hsp168 = high_steal_players(match, config)
        for side in ("home", "away"):
            top168 = hsp168[side]["top"]
            if top168 is None:
                continue
            who168 = (f"a {top168['jersey']}-es mezszámú játékos"
                      if top168.get("jersey") is not None
                      else f"a {top168['player_id']} azonosítójú játékos")
            add(side, "védekezés", "Letámadás a szerzőnk köré",
                f"{who168} a szerzéseinek nagy részét a támadó "
                f"térfélen hozta ({top168['high']}/"
                f"{top168['steals']}) — ez a képesség csak akkor ér "
                "gólt, ha a csapat együtt lép vele",
                "letámadás a szerzőnk köré: 6-6 elleni gyakorlás, "
                "ahol a kijelölt szerzőnk indítja a preszt (ő megy a "
                "felhozóra), a többiek pedig sávot zárnak mögötte — "
                "a szerzés után kötelező az azonnali befejezés hat "
                "másodpercen belül")
    except Exception:
        pass

    # 167) Pontatlan lövők: ha valakinek a lövései elkerülik a kaput,
    # a célzás a téma.
    try:
        from .xg import wasteful_shooters
        wst167 = wasteful_shooters(match, config)
        for side in ("home", "away"):
            top167 = wst167[side]["top"]
            if top167 is None:
                continue
            who167 = (f"a {top167['jersey']}-es mezszámú játékos"
                      if top167.get("jersey") is not None
                      else f"a {top167['player_id']} azonosítójú játékos")
            pct167 = (100.0 * top167["off_target"] / top167["shots"])
            add(side, "támadás", "Kapura tartó lövés",
                f"{who167} lövéseinek {pct167:.0f}%-a elkerülte a "
                f"kaput ({top167['off_target']}/{top167['shots']}) — a "
                "mellé lövés a legolcsóbb támadás-halál: nincs "
                "lepattanó, csak ellenfél-indítás",
                "kapura tartó lövés: célzás-blokk kapussal, ahol a "
                "kapuban két sarokba tett jelzés a cél — a lövés "
                "csak akkor ér pontot, ha kapura megy; a "
                "gyakorlatot fáradtan is le kell futtatni, mert a "
                "pontatlanság a meccs végén nő")
    except Exception:
        pass

    # 166) Kezdő hatos: a nyitó emberek együtt gyakorolják a meccs
    # első támadásait (az első öt perc beárazza a mérkőzést).
    try:
        from .momentum import opening_lineup
        opl166 = opening_lineup(match, config)
        for side in ("home", "away"):
            core166 = opl166[side]["core"][:6]
            if len(core166) < 4:
                continue
            names166 = []
            for row in core166:
                names166.append(
                    f"{row['jersey']}-es" if row.get("jersey") is not None
                    else f"#{row['player_id']}")
            add(side, "taktika", "Nyitó figurák begyakorlása",
                f"a meccs első öt percében ez a hat ember volt a "
                f"pályán ({', '.join(names166)}) — a nyitány "
                "beárazza a mérkőzést, és ott még nincs meccsritmus",
                "nyitó figurák: az edzés ELEJÉN, hidegen jön két "
                "bejátszott nyitó támadás EZZEL a felállással "
                "(kijelölt indító, egy elzárás, kijelölt befejező) — "
                "utána azonnal védekezés-blokk, hogy a meccskezdés "
                "ritmusa is meglegyen")
    except Exception:
        pass

    # 165) Hetes-kiharcolás poszt szerint: az ellenfél hetes-forrása
    # megmondja, melyik posztunkon kell a legfegyelmezettebb kéz.
    try:
        from .rules import seven_earner_roles
        ser165 = seven_earner_roles(match, config)
        for side in ("home", "away"):
            opp165 = "away" if side == "home" else "home"
            top165 = ser165[opp165]["top"]
            if top165 is None:
                continue
            add(side, "védekezés",
                f"Kéz nélküli védekezés: {top165['poszt']}",
                f"az ellenfél heteseinek "
                f"{top165['share_pct']:.0f}%-át a {top165['poszt']} "
                f"posztról harcolta ki ({top165['count']}/"
                f"{ser165[opp165]['sevens']}) — ott a mi kezünk "
                "megy a testre, és abból lesz a büntető",
                f"kéz nélküli védekezés a {top165['poszt']} ellen: "
                "1-1 gyakorlat hátrakulcsolt kézzel, majd "
                "felszabadított kézzel úgy, hogy a kéz csak a "
                "labdára mehet — az edző minden kéz-kontaktusnál "
                "fújja a hetest, hogy a fegyelem meccs-szinten is "
                "meglegyen")
    except Exception:
        pass

    # 164) Időkérés utáni első támadás: ha nem hoz gólt, a kész
    # figura a téma.
    try:
        from .stoppages import timeout_first_attack
        tfa164 = timeout_first_attack(match, config)
        for side in ("home", "away"):
            rec164 = tfa164[side]
            if rec164["verdict"] != "üres időkérés":
                continue
            add(side, "taktika", "Időkérés utáni figura",
                f"az időkéréseink csak {rec164['share_pct']:.0f}%-a "
                f"után jött gól ({rec164['goals']}/"
                f"{rec164['timeouts']}) — a megszakítás így nem "
                "fegyver, csak szusszanás",
                "időkérés utáni figura: két-három BEJÁTSZOTT "
                "záró-figura, amit az időkérésnél csak be kell "
                "mondani (kijelölt indító, kijelölt befejező, "
                "egy elzárás) — edzésen 20 másodperces "
                "megbeszéléssel indítva gyakoroljátok, hogy meccsen "
                "is beférjen a szünetbe")
    except Exception:
        pass

    # 163) Kockázatos passzolók: ha valakinek a hosszú labdái
    # elvesznek, a passz-technika a téma.
    try:
        from .attack_types import risky_passers
        rsk163 = risky_passers(match, config)
        for side in ("home", "away"):
            top163 = rsk163[side]["top"]
            if top163 is None:
                continue
            who163 = (f"a {top163['jersey']}-es mezszámú játékos"
                      if top163.get("jersey") is not None
                      else f"a {top163['player_id']} azonosítójú játékos")
            pct163 = 100.0 * top163["turnovers"] / top163["tries"]
            add(side, "támadás", "Hosszú passz technikája",
                f"{who163} hosszú labdáinak {pct163:.0f}%-a elveszett "
                f"({top163['turnovers']}/{top163['tries']}) — az "
                "ilyen labda ívesen, késve érkezik, és az ellenfél "
                "abból indít kontrát",
                "hosszú passz technikája: páros gyakorlat 15-20 "
                "m-ről, ahol a labdát MELLMAGASSÁGBAN, a futó társ "
                "elé kell vezetni — előbb álló fogadóval, majd "
                "induló szélsővel, végül védővel a sávban; a "
                "gyakorlat az íves, magas labdát nem fogadja el")
    except Exception:
        pass

    # 162) Elzárók: ha egy ember állítja az elzárásainkat, a
    # változatos elzárás-játék a téma.
    try:
        from .attack_types import screen_setters
        scs162 = screen_setters(match, config)
        for side in ("home", "away"):
            top162 = scs162[side]["top"]
            if top162 is None:
                continue
            who162 = (f"a {top162['jersey']}-es mezszámú játékos"
                      if top162.get("jersey") is not None
                      else f"a {top162['player_id']} azonosítójú játékos")
            add(side, "támadás", "Változatos elzárás-játék",
                f"az elzárásaink nagy részét {who162} állította "
                f"({top162['screens']} elzárás a "
                f"{scs162[side]['screens']}-ből) — a védelem "
                "hozzá igazítja a váltásait, és a lövőink nem "
                "szabadulnak fel",
                "változatos elzárás-játék: felállt támadás azzal a "
                "szabállyal, hogy az elzárást minden támadásban MÁS "
                "ember állítja, és minden második elzárás után "
                "leválás (az elzáró bemozdul a 6 m-re) — így a "
                "váltásukat kényszerítitek döntésre")
    except Exception:
        pass

    # 161) Kapus-bemelegedés: ha a kapusunk lassan melegszik be, a
    # meccs eleji készenlét a téma.
    try:
        from .goalkeeper import gk_early_saves
        gke161 = gk_early_saves(match, config)
        for side in ("home", "away"):
            rec161 = gke161[side]
            if rec161["verdict"] != "lassan melegszik be":
                continue
            add(side, "kapus", "Meccs eleji készenlét",
                f"a kapusunk az első tíz percben "
                f"{rec161['early']['save_pct']:.0f}%-ot fogott a "
                f"későbbi {rec161['rest']['save_pct']:.0f}% helyett — "
                "a meccs elején olcsó gólokat kapunk, és a korai "
                "hátrány végigkíséri a mérkőzést",
                "meccs eleji készenlét: hosszabb, terheléses "
                "kapus-bemelegítés a meccs előtt — 20-25 éles lövés "
                "vegyes távolságból és szögből, az utolsó öt lövés "
                "meccstempóban, közvetlenül a kezdés előtt; edzésen "
                "ugyanez az első gyakorlat, hidegen kezdve")
    except Exception:
        pass

    # 160) Emberhátrány-lövők: ha egy ember viszi a hátrányos
    # befejezést, a hátrányos támadás szélesítése a téma.
    try:
        from .rules import shorthanded_shooters
        shs160 = shorthanded_shooters(match, config)
        for side in ("home", "away"):
            top160 = shs160[side]["top"]
            if top160 is None:
                continue
            who160 = (f"a {top160['jersey']}-es mezszámú játékos"
                      if top160.get("jersey") is not None
                      else f"a {top160['player_id']} azonosítójú játékos")
            add(side, "támadás", "Emberhátrányos befejezés",
                f"emberhátrányban {who160} lőtte a lövéseink nagy "
                f"részét ({top160['shots']} lövés a "
                f"{shs160[side]['shots']}-ből) — egy felkészült "
                "ellenfél rá rendezi a biztosítást, és elfogy a "
                "kontra-fenyegetésünk",
                "emberhátrányos befejezés: 5-6 elleni támadójáték "
                "azzal a szabállyal, hogy a befejezés csak "
                "kiugratásból vagy beállós helyzetből jöhet, és "
                "minden támadásban MÁS ember zárja — a cél a "
                "labdatartás mellett a valós gólveszély, nem a "
                "kényszerlövés")
    except Exception:
        pass

    # 159) Hajrá-hibázók: ha egy emberünknél megy el a labda a végén,
    # a nyomás alatti döntés a téma.
    try:
        from .momentum import clutch_turnover_players
        ctp159 = clutch_turnover_players(match, config)
        for side in ("home", "away"):
            top159 = ctp159[side]["top"]
            if top159 is None:
                continue
            who159 = (f"a {top159['jersey']}-es mezszámú játékos"
                      if top159.get("jersey") is not None
                      else f"a {top159['player_id']} azonosítójú játékos")
            add(side, "taktika", "Nyomás alatti döntés",
                f"a hajrában {who159} veszítette el a labdát a "
                f"legtöbbször ({top159['turnovers']} eladás a döntő "
                "szakaszban) — a fáradtság és a tét együtt rontja a "
                "döntéseit, és ott a legdrágább a hiba",
                "nyomás alatti döntés: az edzés végén, fáradtan, "
                "zajban (kiabálás, taps) játszott 5 perces "
                "meccs-részlet egy gólos hátrányból — kötött "
                "szabály, hogy a labda nem maradhat két másodpercnél "
                "tovább senkinél, és minden eladás azonnali "
                "büntető-sprinttel jár")
    except Exception:
        pass

    # 158) Csere-kiváltók: ha kapott gólra cserélünk, a tervezett
    # csere-rend a téma.
    try:
        from .substitutions import substitution_triggers
        stg158 = substitution_triggers(match, config)
        for side in ("home", "away"):
            rec158 = stg158[side]
            if rec158["verdict"] != "kapott gólra cserélnek":
                continue
            add(side, "taktika", "Tervezett csere-rend",
                f"a cseréink {rec158['share_pct']:.0f}%-a kapott gól "
                f"után jött ({rec158['after_conceded']}/"
                f"{rec158['subs']}) — a kispad reagál, nem tervez, és "
                "a csere pont a legrosszabb pillanatban, a "
                "középkezdés előtt bontja meg a sorokat",
                "tervezett csere-rend: a meccs elején rögzített "
                "csere-pontok (pl. minden 10. percben, illetve "
                "időkérés után), fix cserepárokkal — az edzőmeccsen "
                "az edző csak ezekben a percekben cserélhet, kapott "
                "gól után SOHA; a hajrá-ötös cseréje külön, előre "
                "bejelentett pillanatban jön")
    except Exception:
        pass

    # 157) Falépítés-idő: ha lassan állunk fel, a rendeződés a téma.
    try:
        from .defense import defense_setup_time
        dst157 = defense_setup_time(match, config)
        for side in ("home", "away"):
            rec157 = dst157[side]
            if rec157["verdict"] != "lassan állnak fel":
                continue
            add(side, "védekezés", "Gyors falépítés",
                f"átlag {rec157['avg_s']:.1f} másodperc telt el a "
                f"rendezett falunk felállásáig "
                f"({rec157['cases']} mért birtokváltás) — ennyi idő "
                "alatt az ellenfél már befejezi a támadást",
                "gyors falépítés: labdavesztés-jelre a hat védőnek "
                "KÖTELEZŐ öt másodpercen belül elfoglalnia a "
                "helyét — az edző stopperrel méri, és a késés "
                "sprinttel jár; utána ugyanez ellenfél-indítással, "
                "hogy a fékezés és a felállás egyszerre menjen")
    except Exception:
        pass

    # 156) Kapus emberhátrányban: ha a kapusunk ilyenkor visszaesik, a
    # fal nélküli helyzetek védése a téma.
    try:
        from .goalkeeper import gk_shorthanded_saves
        gsh156 = gk_shorthanded_saves(match, config)
        for side in ("home", "away"):
            rec156 = gsh156[side]
            if rec156["verdict"] != "emberhátrányban visszaesik":
                continue
            add(side, "kapus", "Kapus emberhátrányban",
                f"a kapusunk emberhátrányban csak "
                f"{rec156['sh']['save_pct']:.0f}%-ot fogott a szokásos "
                f"{rec156['eq']['save_pct']:.0f}% helyett — öt "
                "emberrel a fal nem ér mindenhová, és a kapus "
                "egyedül marad a helyzetekkel",
                "kapus emberhátrányban: 6-5 elleni helyzetgyakorlás "
                "a kapussal, ahol a lövések a szélekről és a beállós "
                "helyzetekből jönnek — a kapus a fallal EGYEZTETVE "
                "választ oldalt (a védő mutatja a zárt sarkot), és "
                "minden védés után azonnali indítás jön")
    except Exception:
        pass

    # 155) Emberelőny-lövők: ha egy emberre épül az emberelőnyünk, a
    # befejezés szélesítése a téma.
    try:
        from .rules import powerplay_shooters
        pps155 = powerplay_shooters(match, config)
        for side in ("home", "away"):
            top155 = pps155[side]["top"]
            if top155 is None:
                continue
            who155 = (f"a {top155['jersey']}-es mezszámú játékos"
                      if top155.get("jersey") is not None
                      else f"a {top155['player_id']} azonosítójú játékos")
            add(side, "támadás", "Emberelőny több befejezővel",
                f"emberelőnyben {who155} adta le a lövéseink "
                f"nagy részét ({top155['shots']} lövés a "
                f"{pps155[side]['shots']}-ből) — egy felkészült "
                "ellenfél rá rendezi a falat, és elfogy az "
                "emberelőnyünk",
                "emberelőny több befejezővel: 6-5 elleni gyakorlás "
                "azzal a szabállyal, hogy ugyanaz az ember nem "
                "fejezhet be kétszer egymás után — a figurákat úgy "
                "kell felépíteni, hogy a beálló és a szélső is "
                "helyzetbe kerüljön, és minden befejezés előtt "
                "legyen egy oldalváltás")
    except Exception:
        pass

    # 154) Lövés-távolság esése: ha a hajrára kifelé szorulunk, a
    # fáradt befejezés a téma.
    try:
        from .attack_types import shot_distance_fade
        sdf154 = shot_distance_fade(match, config)
        for side in ("home", "away"):
            rec154 = sdf154[side]
            if rec154["verdict"] != "kifelé szorulnak":
                continue
            add(side, "erőnlét", "Fáradt befejezés",
                f"a lövéseink átlagos távolsága "
                f"{rec154['fh_avg_m']:.1f} m-ről "
                f"{rec154['sh_avg_m']:.1f} m-re nőtt a második "
                "félidőre — a hajrában már nem vállaljuk a betörést, "
                "és kívülről lövünk",
                "fáradt befejezés: az edzés VÉGÉN, fáradtan jön a "
                "befejezés-blokk — 8-10 betöréses helyzet kapussal, "
                "ahol a lövés csak 9 m-en belülről ér pontot; "
                "közben rövid sprint-sorozat, hogy a pulzus a "
                "meccs-hajrához hasonló legyen")
    except Exception:
        pass

    # 153) Kapott gólok támadás-típus szerint: ha a gólok nagy része
    # lerohanásból jön, a visszarendeződés a téma.
    try:
        from .defense import conceded_by_attack_type
        cat153 = conceded_by_attack_type(match, config)
        for side in ("home", "away"):
            top153 = cat153[side]["top"]
            if top153 is None:
                continue
            if "lerohanás" in top153["type"] or "gyors" in top153["type"]:
                add(side, "védekezés", "Visszarendeződés a kontra ellen",
                    f"a kapott góljaink {top153['share_pct']:.0f}%-a "
                    f"{top153['type']}-ból jött "
                    f"({top153['goals']}/{cat153[side]['goals']}) — nem "
                    "a fal minőségével van baj, hanem azzal, hogy nem "
                    "érünk vissza",
                    "visszarendeződés: minden támadás-gyakorlat "
                    "végén KÖTELEZŐ visszafutás a felezővonalig, "
                    "majd 4-5 elleni fékezés — az edző a lövés "
                    "pillanatában indítja az ellentámadást, és csak "
                    "a rendezetten megállított kontra ér pontot")
            else:
                add(side, "védekezés", "Felállt fal szervezése",
                    f"a kapott góljaink {top153['share_pct']:.0f}%-a "
                    f"{top153['type']}-ból jött "
                    f"({top153['goals']}/{cat153[side]['goals']}) — a "
                    "rendezett fal ellen is szivárgunk, tehát a "
                    "szervezésen kell dolgozni",
                    "felállt fal szervezése: 6-0 elleni támadójáték "
                    "hangos vezényszóval — minden átadásnál a "
                    "kezdeményező védő bemondja a nevet, és a "
                    "gyakorlat csak akkor ér pontot, ha a "
                    "lövés-kényszert a fal hozza ki, nem az idő")
    except Exception:
        pass

    # 152) Áttörő játékosok: ha az ellenfél egy embere sorozatban
    # betör, a duplázás és a vonal-zárás a téma.
    try:
        from .attack_types import breakthrough_players
        btp152 = breakthrough_players(match, config)
        for side in ("home", "away"):
            opp152 = "away" if side == "home" else "home"
            top152 = btp152[opp152]["top"]
            if top152 is None:
                continue
            add(side, "védekezés", "Duplázás a betörőre",
                f"az ellenfél egyik embere {top152['entries']} "
                f"alkalommal jutott be a 9 m-es körzetbe "
                f"({top152['goals']} gólos támadás) — a betörés "
                "vonalát nem zárjuk időben, és a fal utána szétnyílik",
                "duplázás a betörőre: 2 az 1 elleni gyakorlat, ahol a "
                "betörő indulására a szomszéd védő AZONNAL bezáródik "
                "— a labdás védője tereli, a segítő állítja meg "
                "testtel; kézzel érinteni tilos, a gyakorlat "
                "szabálytalanságért mínuszt ad")
    except Exception:
        pass

    # 151) Két beállós játék: ha az ellenfél két beállóval játszik, a
    # közép-tömörítés a téma (a saját oldalon a felállás variálása).
    try:
        from .attack_types import double_pivot_usage
        dpv151 = double_pivot_usage(match, config)
        for side in ("home", "away"):
            opp151 = "away" if side == "home" else "home"
            rec151 = dpv151[opp151]
            if rec151["verdict"] != "két beállóval játszanak":
                continue
            add(side, "védekezés", "Közép-tömörítés két beálló ellen",
                f"az ellenfél a támadásaik {rec151['share_pct']:.0f}%-"
                "ában két emberrel dolgozott a 6 m-en — a két középső "
                "védőnk így folyamatosan túlterhelt, és az "
                "átadás-zavarból jönnek a gólok",
                "közép-tömörítés: 6-0 elleni gyakorlás két beállóval "
                "szemben, ahol MINDEN középső védőnek SAJÁT beállója "
                "van (nincs átadás), a szélső védők pedig feljebb "
                "lépnek a széles átlövőre — a támadók kötelezően "
                "cserélik a két beálló helyét, hogy a fogás "
                "folyamatos legyen")
    except Exception:
        pass

    # 150) Hajrá-ötös: a záró szakasz emberei együtt gyakorolják a
    # befejezést (a hajrában nincs idő ismerkedni).
    try:
        from .momentum import clutch_lineup
        cll150 = clutch_lineup(match, config)
        for side in ("home", "away"):
            core150 = cll150[side]["core"][:6]
            if len(core150) < 4:
                continue
            names150 = []
            for row in core150:
                names150.append(
                    f"{row['jersey']}-es" if row.get("jersey") is not None
                    else f"#{row['player_id']}")
            add(side, "taktika", "Hajrá-ötös begyakorlása",
                f"a döntő tíz percben ez a hat ember volt a pályán "
                f"({', '.join(names150)}) — a hajrában nincs idő "
                "ismerkedni, a záró figuráknak automatizmusnak kell "
                "lenniük",
                "hajrá-ötös begyakorlása: edzés végén, fáradtan, "
                "EZZEL a felállással gyakoroljátok a záró "
                "helyzeteket — utolsó támadás egy gólos hátrányból, "
                "hetes, és emberelőnyös befejezés; minden szituáció "
                "kijelölt indítóval és kijelölt befejezővel")
    except Exception:
        pass

    # 149) Kontra-kíséret: ha magányos kontrát futunk, a kíséret a
    # téma (a lerohanás nem egyemberes műfaj).
    try:
        from .attack_types import fast_break_support
        fbs149 = fast_break_support(match, config)
        for side in ("home", "away"):
            rec149 = fbs149[side]
            if rec149["verdict"] != "magányos kontra":
                continue
            add(side, "támadás", "Kontra-kíséret",
                f"a lerohanásainknál átlag "
                f"{rec149['avg_runners']:.1f} emberünk indult el "
                f"({rec149['breaks']} lerohanás) — egy emberrel a "
                "kontra megállítható, és a visszaérő védő nyugodtan "
                "kivárhat",
                "kontra-kíséret: 3 a 2 elleni gyors indítás a "
                "kapustól, ahol a labdás mellett KÉT kísérőnek kell "
                "elérnie a támadó térfelet — a befejezés csak "
                "átadásból jöhet, egyéni elfutásból nem ér gólt; "
                "utána ugyanez visszaérő védővel, hogy a döntés is "
                "gyakorolva legyen")
    except Exception:
        pass

    # 148) Kapus-hetesvédés iránya: ha egy sarokra későn érünk, az a
    # sarok a téma.
    try:
        from .rules import gk_seven_directions
        g7d148 = gk_seven_directions(match, config)
        for side in ("home", "away"):
            weak148 = g7d148[side]["weak_dir"]
            if weak148 is None:
                continue
            add(side, "kapus", f"Hetes-védés: {weak148['irany']} sarok",
                f"a kapusunk a {weak148['irany']} sarokba menő "
                f"hetesekből csak {weak148['save_pct']:.0f}%-ot fogott "
                f"({weak148['faced']} hetes) — egy felkészült "
                "ellenfél pontosan ide fogja lőni a büntetőt",
                "hetes-védés sarokra: sorozat-hetesek úgy, hogy a "
                f"lövők a {weak148['irany']} sarokba lőnek — a kapus "
                "előbb csak a lábmunkát gyakorolja (oldalra lépés, "
                "nagy test), majd a lövő karját figyelve indul; a "
                "sorozat végén vegyes irányok, hogy a felismerés is "
                "meglegyen")
    except Exception:
        pass

    # 147) Kihozatal-oldal: ha mindig ugyanarról az oldalról indítunk,
    # a kihozatal kiszámítható — az oldalváltó indítás a téma.
    try:
        from .attack_types import buildup_side
        bus147 = buildup_side(match, config)
        for side in ("home", "away"):
            rec147 = bus147[side]
            if rec147["dominant"] in (None, "közép"):
                continue
            add(side, "támadás", "Oldalváltó kihozatal",
                f"a támadásaink {rec147['share_pct']:.0f}%-a a "
                f"{rec147['dominant']} oldalról indult "
                f"({rec147['attacks']} mért támadás) — egy letámadó "
                "ellenfél erre az oldalra fogja küldeni a két emberét",
                "oldalváltó kihozatal: kihozatal-gyakorlat "
                "letámadással, ahol a kapus felváltva indít a két "
                "oldalra, és az indítás oldalát a MÁSIK oldal "
                "szélsőjének hangos jelzése dönti el — a labdának "
                "három passzon belül át kell érnie a felezővonalon")
    except Exception:
        pass

    # 146) Lepattanó-szerzők: ha az ellenfél gyűjti a kipattanókat, a
    # kipattanó-kísérés a téma (a saját oldalon a védekező lepattanó).
    try:
        from .attack_types import rebound_winners
        rbw146 = rebound_winners(match, config)
        for side in ("home", "away"):
            opp146 = "away" if side == "home" else "home"
            top146 = rbw146[opp146]["top_off"]
            if top146 is None:
                continue
            add(side, "védekezés", "Kipattanó-kísérés",
                f"az ellenfél egyik embere {top146['rebounds']} "
                "kipattanót gyűjtött be a saját lövéseik után — a "
                "blokk és a védés utáni pillanatokban nem zárjuk be a "
                "6 m-es teret",
                "kipattanó-kísérés: blokk-gyakorlat, ahol minden "
                "blokkolt vagy védett lövés után a legközelebbi "
                "védőnek KÖTELEZŐ a labdára indulnia, a szomszédja "
                "pedig kiszorítja a beállót a 6 m-es térből — a "
                "gyakorlat csak akkor ér pontot, ha a lepattanót a "
                "védekező csapat szerzi meg")
    except Exception:
        pass

    # 145) Lövő-távolság: ha valaki csak távolról lő, a befejezés
    # közelebb hozása a téma.
    try:
        from .attack_types import shooter_ranges
        shr145 = shooter_ranges(match, config)
        for side in ("home", "away"):
            far145 = shr145[side]["far"]
            if far145 is None:
                continue
            who145 = (f"a {far145['jersey']}-es mezszámú játékos"
                      if far145.get("jersey") is not None
                      else f"a {far145['player_id']} azonosítójú játékos")
            add(side, "támadás", "Befejezés közelebbről",
                f"{who145} átlag {far145['avg_dist_m']:.1f} m-ről lőtt "
                f"({far145['shots']} lövés) — ilyen távolról a kapus "
                "és a blokk együtt dolgozik, ezért a lövéseink olcsón "
                "elvehetők",
                "befejezés közelebbről: 1-1 és kétszemélyes figura a "
                "9 m-en, ahol a lövés CSAK a védő mellett elhaladva, "
                "befelé lépésből jöhet — a gyakorlat a 9 m-en kívüli "
                "lövést nem fogadja el; utána ugyanez blokkolóval, "
                "hogy a lövés előtti egy lépés kényszer legyen")
    except Exception:
        pass

    # 144) Emberhátrány-forma: ha öt emberrel egy formát húzunk, a
    # forma elleni tipikus megoldásokat kell begyakorolni.
    try:
        from .rules import shorthanded_shape
        shs144 = shorthanded_shape(match, config)
        for side in ("home", "away"):
            rec144 = shs144[side]
            if rec144["main"] is None:
                continue
            add(side, "védekezés", f"Emberhátrány {rec144['main']}-ban",
                f"emberhátrányban a mért kockák "
                f"{rec144['main_pct']:.0f}%-ában {rec144['main']}-s "
                "falat húztunk — egy felkészült ellenfél pontosan "
                "tudja, hol a szabad terület e mögött",
                "emberhátrány-védekezés: 5-6 elleni gyakorlás a "
                f"{rec144['main']}-s alapállásból, ahol a támadók "
                "kötelezően oldalt váltanak minden harmadik passznál "
                "— a védőknek hangos vezényszóval kell átadniuk, és "
                "a lövő-vonalba csak akkor lépnek ki, ha mögöttük "
                "van a segítő")
    except Exception:
        pass

    # 143) Emberelőny-tempó: ha emberelőnyben kapkodunk, a
    # helyzet-kivárás a téma.
    try:
        from .rules import powerplay_pace
        ppp143 = powerplay_pace(match, config)
        for side in ("home", "away"):
            rec143 = ppp143[side]
            if rec143["verdict"] != "kapkodnak emberelőnyben":
                continue
            add(side, "támadás", "Emberelőny kivárással",
                f"emberelőnyben {rec143['pp_avg_s']:.0f} mp-es "
                f"támadásokat játszottunk a {rec143['eq_avg_s']:.0f} "
                f"mp-es átlagunk helyett "
                f"({rec143['pp_attacks']} emberelőnyös támadás) — a "
                "két percet elkapkodjuk, és a korai lövésből lesz az "
                "ellenfél kontrája",
                "emberelőny kivárással: 6-5 elleni támadójáték azzal "
                "a szabállyal, hogy a befejezés előtt legalább hat "
                "passznak és egy oldalváltásnak kell lennie — lőni "
                "csak 9 m-en belülről vagy üres kapura szabad; a "
                "gyakorlat eladott labdáért mínuszt ad, hogy a "
                "türelem legyen a nyerő")
    except Exception:
        pass

    # 142) Effektív játékidő: szakadozott meccsnél a ritmus-tartás a
    # téma (a leállások utáni újraindulás).
    try:
        from .stoppages import playing_time_profile
        ptp142 = playing_time_profile(match, config)["home"]
        if ptp142["verdict"] == "szakadozott meccskép":
            for side in ("home", "away"):
                add(side, "taktika", "Ritmus-tartás leállások után",
                    f"az effektív játékidő {ptp142['effective_pct']:.0f}% "
                    f"volt ({ptp142['stoppages']} megszakítás, "
                    f"{ptp142['stopped_s'] / 60.0:.0f} perc holt idő) "
                    "— a sok leállás széttöri a ritmust, és az "
                    "újraindulás pillanata dönti el a szakaszokat",
                    "ritmus-tartás: edzőmeccs-részlet, ahol az edző "
                    "váratlanul 60-90 másodpercre leállítja a játékot "
                    "(mint egy sérülés vagy videó-nézés), majd "
                    "azonnal indít — a leállás alatt a csapatnak "
                    "mozgásban kell maradnia, és az újraindulás után "
                    "az ELSŐ támadást kötött figurából kell "
                    "befejezni")
    except Exception:
        pass

    # 141) Védekezés-keménység: ha a falunk sok büntetést hoz, a
    # szabályos keménység a téma.
    try:
        from .defense import defensive_aggression
        agr141 = defensive_aggression(match, config)
        for side in ("home", "away"):
            rec141 = agr141[side]
            if rec141["verdict"] != "kemény fal":
                continue
            add(side, "védekezés", "Szabályos keménység",
                f"a védekezett támadásaink {rec141['pct']:.0f}%-a "
                f"végződött hetessel vagy kiállítással "
                f"({rec141['sevens']} hetes, {rec141['suspensions']} "
                f"kiállítás {rec141['attacks']} támadásból) — a "
                "keménység így emberhátrányt és ingyen gólt termel",
                "szabályos keménység: 1-1 gyakorlat a betörő ellen, "
                "ahol a védő CSAK a törzzsel és a lábbal állhat "
                "útba — a kar a labda felé nyúlhat, a testre soha; "
                "a gyakorlat pontot a szabályos megállításért ad, és "
                "minden szabálytalanság után a védő ötös sprintje jön")
    except Exception:
        pass

    # 140) Visszaérés-fegyelem: ha valaki elöl lóg védekezéskor, a
    # visszafutás a téma.
    try:
        from .defense import recovery_discipline
        rcd140 = recovery_discipline(match, config)
        for side in ("home", "away"):
            worst140 = rcd140[side]["worst"]
            if worst140 is None:
                continue
            who140 = (f"a {worst140['jersey']}-es mezszámú játékos"
                      if worst140.get("jersey") is not None
                      else f"a {worst140['player_id']} azonosítójú játékos")
            add(side, "védekezés", "Visszafutás-fegyelem",
                f"{who140} a védekezett időnek csak "
                f"{worst140['share_pct']:.0f}%-ában volt a saját "
                "térfelén — mögötte nincs védő, és az ellenfél "
                "kapusa pont oda fog indítani",
                "visszafutás-fegyelem: 5-6 elleni visszazárás "
                "gyakorlása labdaeladásból indítva — az utolsó "
                "támadó KÖTELEZŐEN a felezővonalig fut vissza, "
                "mielőtt bárki labdába nyúlhatna; ha nem ér vissza, "
                "a gyakorlat újraindul, és a támadás gólja duplán "
                "számít")
    except Exception:
        pass

    # 139) Kapus-védés lövés-tempó szerint: ha az egyik sávban
    # sebezhető a kapusunk, az a sáv a téma.
    try:
        from .goalkeeper import gk_saves_by_speed
        gsp139 = gk_saves_by_speed(match, config)
        for side in ("home", "away"):
            weak139 = gsp139[side]["weak_band"]
            if weak139 is None:
                continue
            band139 = "placed" if weak139 == "helyezett" else "hard"
            rec139 = gsp139[side][band139]
            if weak139 == "helyezett":
                drill139 = ("helyezett lövés védése: sorozatlövés "
                            "lassabb, sarokba helyezett és pattintott "
                            "lövésekkel — a kapus ne dőljön el korán, "
                            "a lábmunka vigye a testet a labda "
                            "vonalába, és a pattanó labdát alacsony "
                            "kézzel fogja")
            else:
                drill139 = ("kemény lövés védése: sorozatlövés 9 "
                            "m-ről, teljes erőből, a kapus "
                            "reakció-indítással (a lövő karjára "
                            "figyelve) és nagy testtel — a "
                            "blokkolókkal egyeztetett sarok-zárással")
            add(side, "kapus", f"{weak139.capitalize()} lövések védése",
                f"a kapusunk a {weak139} lövésekből csak "
                f"{rec139['save_pct']:.0f}%-ot fogott "
                f"({rec139['saves']}/{rec139['faced']}) — egy "
                "felkészült ellenfél pont ilyen lövéseket fog "
                "választani",
                drill139)
    except Exception:
        pass

    # 138) Álló támadók: ha valaki labda nélkül alig mozog, a labda
    # nélküli munka a téma.
    try:
        from .tactics import static_attackers
        sta138 = static_attackers(match, config)
        for side in ("home", "away"):
            rec138 = sta138[side]["static"]
            if rec138 is None:
                continue
            who138 = (f"a {rec138['jersey']}-es mezszámú játékos"
                      if rec138.get("jersey") is not None
                      else f"a {rec138['player_id']} azonosítójú játékos")
            add(side, "támadás", "Labda nélküli munka",
                f"{who138} {rec138['avg_mps']:.2f} m/s-mal mozgott a "
                f"támadásban, a csapatátlag "
                f"{sta138[side]['team_avg_mps']:.2f} m/s — az ő "
                "védőjét bármikor el lehet venni kettőzésre, mert "
                "labda nélkül nem jelent fenyegetést",
                "labda nélküli munka: felállt támadás azzal a "
                "szabállyal, hogy labda nélkül MINDENKINEK mozognia "
                "kell — minden átadás után indulás (keresztezés, "
                "beúszás vagy elfutás); az edző fütyülésére a labdás "
                "megáll, és aki nem mozgásban van, az fut egy "
                "hosszot")
    except Exception:
        pass

    # 137) Szélső-befejezés oldalanként: ha az egyik szélsőnk érdemben
    # gyengébben fejez be, az ő szög-befejezése a téma.
    try:
        from .attack_types import wing_finishing_by_side
        wfs137 = wing_finishing_by_side(match, config)
        for side in ("home", "away"):
            rec137 = wfs137[side]
            if rec137["weak"] is None:
                continue
            weak137 = rec137[rec137["weak"]]
            strong137 = rec137[rec137["strong"]]
            add(side, "támadás", "Szélső-befejezés éles szögből",
                f"a {rec137['weak']} szélsőnk "
                f"{weak137['goal_pct']:.0f}%-ot értékesített "
                f"({weak137['goals']}/{weak137['shots']}), a másik "
                f"oldalon {strong137['goal_pct']:.0f}% — a védelem ezt "
                "kiszámolja, és arra az oldalra engedi rá a lövést",
                "szélső-befejezés éles szögből: sorozatlövés a "
                "gyengébb oldalról kapussal, három megoldással "
                "váltogatva (hosszú sarok emeléssel, rövid sarok "
                "lapos lövéssel, és a kapus lábai közé) — a szélső "
                "MINDIG a levegőben, befelé lépve fejezzen be, hogy "
                "a szöge nyíljon")
    except Exception:
        pass

    # 136) Beálló-oldal: ha a beállónk mindig ugyanoda áll be,
    # kiszámítható — az oldalváltó beállózás a téma.
    try:
        from .attack_types import pivot_side
        pvs136 = pivot_side(match, config)
        for side in ("home", "away"):
            rec136 = pvs136[side]
            if rec136["dominant"] in (None, "közép"):
                continue
            add(side, "támadás", "Oldalváltó beállózás",
                f"a beállónk a mért kockák "
                f"{rec136['share_pct']:.0f}%-ában a "
                f"{rec136['dominant']} oldalon állt be — a védelem "
                "erre felkészül, és mindig ugyanaz a védőpár várja",
                "oldalváltó beállózás: felállt támadás azzal a "
                "szabállyal, hogy a beálló minden második támadásban "
                "átvált a másik oldalra, és az átvonuláskor a falon "
                "BELÜL, a védők háta mögött megy át — a kiszolgálás "
                "az átvonulás pillanatában érkezzen, hogy az "
                "átadás-zavart is gyakoroljátok")
    except Exception:
        pass

    # 135) Fal-csúszás: ha lassan követjük az oldalváltást, az eltolás
    # a téma.
    try:
        from .defense import defensive_shift_lag
        dsl135 = defensive_shift_lag(match, config)
        for side in ("home", "away"):
            rec135 = dsl135[side]
            if rec135["verdict"] != "lassan csúsznak":
                continue
            add(side, "védekezés", "Eltolás oldalváltásra",
                f"a falunk {rec135['lag_s']:.1f} mp késéssel követte a "
                "labda oldalváltásait — két gyors átjátszás után a "
                "túloldalon rés nyílik, és ott érkezik a befejezőjük",
                "eltolás oldalváltásra: a fal 6 játékossal áll, a "
                "támadók csak keresztpasszokat adnak (lövés nélkül) — "
                "a védőknek a labda ÉRKEZÉSE előtt kell a helyükön "
                "lenniük, hangos vezényszóval; utána ugyanez "
                "befejezéssel, ahol minden késve érkezett eltolás "
                "után az öt védő visszafut a felezővonalig")
    except Exception:
        pass

    # 134) Passz-sebesség: ha lágy a labdajáratásunk, a feszes passz a
    # téma.
    try:
        from .decisions import pass_speed
        psp134 = pass_speed(match, config)
        for side in ("home", "away"):
            rec134 = psp134[side]
            if rec134["label"] != "lágy labdajáratás":
                continue
            add(side, "támadás", "Feszes passz",
                f"a passzainknak csak {rec134['fast_pct']:.0f}%-a volt "
                f"feszes (átlag {rec134['avg_ms']:.1f} m/s, "
                f"{rec134['passes']} mért passz) — a lassú labdába "
                "bele lehet érni, és minden elfogott passz kontrát ér "
                "ellenünk",
                "feszes passz: páros passzgyakorlat 8-10 m-ről, "
                "mellmagasságban, egy érintéssel — a fogadó a labdával "
                "szemben lép, a passz a MELLKASRA megy, nem ívelten; "
                "utána ugyanez védővel a passzsávban, hogy a feszes "
                "passz kényszer legyen, ne választás")
    except Exception:
        pass

    # 133) Beálló-kiszolgálók: ha egy ember adja a beadások felét, a
    # kiszolgálás szélesítése a téma.
    try:
        from .attack_types import pivot_feeders
        pf133 = pivot_feeders(match, config)
        for side in ("home", "away"):
            top133 = pf133[side]["top"]
            if top133 is None:
                continue
            who133 = (f"a {top133['jersey']}-es mezszámú játékos"
                      if top133.get("jersey") is not None
                      else f"a {top133['player_id']} azonosítójú játékos")
            add(side, "támadás", "Beálló-kiszolgálás több kézből",
                f"{who133} adta a beállónak menő beadások "
                f"{top133['share_pct']:.0f}%-át "
                f"({top133['feeds']}/{pf133[side]['feeds']}) — egy "
                "felkészült védelem ezt az egy átadás-vonalat zárja, "
                "és a beállónk kiesik a játékból",
                "beálló-kiszolgálás több kézből: felállt támadás "
                "azzal a szabállyal, hogy a beálló egymás után "
                "kétszer nem kaphatja ugyanattól a játékostól a "
                "labdát — a beadás jöhet a szélsőtől és a "
                "kiugró átlövőtől is, és minden beadás után "
                "azonnali oldalváltás")
    except Exception:
        pass

    # 132) Hetes-okozó védők: ha egy védőnk sorozatban okoz hetest, a
    # lábbal védekezés a téma.
    try:
        from .rules import seven_meter_conceders
        smc132 = seven_meter_conceders(match, config)
        for side in ("home", "away"):
            top132 = smc132[side]["top"]
            if top132 is None:
                continue
            jn132 = top132.get("jersey")
            who132 = (f"a {jn132}-es mezszámú védőnk" if jn132 is not None
                      else f"a {top132['player_id']} azonosítójú védőnk")
            add(side, "védekezés", "Lábbal védekezés",
                f"{who132} {top132['conceded']} hetest okozott — a "
                "betörést kézzel állítja meg, ami hetest és "
                "kiállítást ér",
                "lábbal védekezés: 1-1 gyakorlat a 9 m-en, ahol a "
                "védő KEZE hátul van összekulcsolva — csak "
                "lábmunkával, testtel szabad terelni; utána "
                "ugyanez felszabadított kézzel, de a szabály az, "
                "hogy a kéz csak a labdára mehet, a testre soha")
    except Exception:
        pass

    # 131) Támadás-mélység: ha mélyen, hátrahúzódva támadunk, a
    # vonalra lépés a téma.
    try:
        from .attack_types import attack_depth
        adp131 = attack_depth(match, config)
        for side in ("home", "away"):
            rec131 = adp131[side]
            if rec131["style"] != "mély (hátrahúzódó)":
                continue
            add(side, "támadás", "Vonalra lépő támadás",
                f"a támadóink átlagosan {rec131['avg_depth_m']:.1f} "
                "m-re álltak a kaputól — ilyen mélyről csak távoli "
                "lövés marad, a védelem pedig nyugodtan kiléphet "
                "ránk",
                "vonalra lépő támadás: felállt támadás azzal a "
                "szabállyal, hogy az átlövők a labda átvételekor "
                "MÁR lépés közben legyenek befelé (a 9 m-es vonalon "
                "belülre érkezve fejezzenek be vagy adják tovább) — "
                "a gyakorlat pontot csak 9 m-en belülről leadott "
                "lövésért vagy beállós befejezésért ad")
    except Exception:
        pass

    # 130) Szélső-bevonás: ha a labda ki sem megy a szélre, a
    # szélesség-tartás a téma.
    try:
        from .attack_types import wing_involvement
        wi130 = wing_involvement(match, config)
        for side in ("home", "away"):
            rec130 = wi130[side]
            if rec130["verdict"] != "közép-központú":
                continue
            add(side, "támadás", "Szélesség-tartás",
                f"a támadásaink csak {rec130['share_pct']:.0f}%-ában "
                f"jutott ki a labda a szélre "
                f"({rec130['with_wing']}/{rec130['attacks']}) — a "
                "védelem befelé tömörülhet, mert a szélső nem "
                "jelent fenyegetést",
                "szélesség-tartás: felállt támadás azzal a "
                "szabállyal, hogy a befejezés előtt a labdának "
                "MINDKÉT szélsőt meg kell járnia — a szélsők a "
                "9 m-es vonal magasságában, a felezővonal felé "
                "nyitva kérjék a labdát, és minden átvétel után "
                "azonnal induljanak befelé (beadás vagy betörés)")
    except Exception:
        pass

    # 129) Védekezési mélység állás szerint: ha vezetve visszaülünk, a
    # vezetés-védés a téma (a fal helye ne az eredménytől függjön).
    try:
        from .defense import line_height_by_score
        lhs129 = line_height_by_score(match, config)
        for side in ("home", "away"):
            rec129 = lhs129[side]
            if rec129["verdict"] != "hátrányban feljebb lépnek":
                continue
            add(side, "védekezés", "Vezetés-védés azonos fallal",
                f"hátrányban {rec129['trailing']['avg_height_m']:.1f} "
                f"m-en, vezetve "
                f"{rec129['leading']['avg_height_m']:.1f} m-en állt a "
                "falunk — vezetve visszaülünk, és pont akkor "
                "engedjük felállni az ellenfelet, amikor zárni "
                "kellene a meccset",
                "vezetés-védés: edzőmeccs-részlet 3 gólos előnyből "
                "indítva, azzal a szabállyal, hogy a fal ugyanott áll, "
                "mint döntetlennél (kijelölt magasság, kilépő "
                "középső védő) — a gyakorlat csak akkor ér pontot, ha "
                "az öt perc alatt nem kaptok két gólnál többet")
    except Exception:
        pass

    # 128) Támadás-kimenetel: ha a támadásaink lövés nélkül halnak el,
    # a befejezésig vitel a téma.
    try:
        from .attack_types import attack_outcomes
        ao128 = attack_outcomes(match, config)
        for side in ("home", "away"):
            rec128 = ao128[side]
            if rec128["verdict"] != "lövés nélkül halnak el":
                continue
            add(side, "támadás", "Befejezésig vitt támadás",
                f"a támadásaink {rec128['turnover_pct']:.0f}%-a lövés "
                f"nélkül, eladással halt el ({rec128['attacks']} "
                "támadásból) — a kidolgozás közben veszítjük el a "
                "labdát, tehát a helyzet minősége előtt a "
                "befejezésig jutás a feladat",
                "befejezésig vitt támadás: felállt támadás azzal a "
                "szabállyal, hogy MINDEN támadást lövéssel kell "
                "zárni — ha 30 másodpercen belül nincs lövés, a "
                "kijelölt átlövő vállalja; a gyakorlat pontot csak "
                "leadott lövésért ad, gólért kettőt, eladásért "
                "mínuszt")
    except Exception:
        pass

    # 127) Kapus-védés posztonként: ha egy szögből sebezhető a
    # kapusunk, az adott szög védése a téma.
    try:
        from .goalkeeper import gk_saves_by_role
        gsr127 = gk_saves_by_role(match, config)
        _drill127 = {
            "szélső": ("szélső-szög védése: sorozatlövés a szélről "
                       "mindkét oldalról, a kapus a rövid sarkot "
                       "zárja és kilép a szögbe — a védőkkel együtt, "
                       "hogy a terelés is stimmeljen"),
            "beálló": ("közeli lövés védése: beállós befejezés 6 "
                       "m-ről, a kapus kilépéssel csökkenti a szöget, "
                       "a lábmunka és a nagy test a téma"),
            "átlövő": ("átlövés védése: sorozatlövés 9-10 m-ről blokk "
                       "mögül, a kapus a blokkolt oldal ellenkező "
                       "sarkára rendezkedik — a védőkkel egyeztetett "
                       "sarok-zárással"),
            "irányító": ("középső átlövés védése: sorozatlövés a "
                         "közép-átlövő helyéről, váltott magasságban, "
                         "a kapus alaphelyzetének javításával"),
        }
        for side in ("home", "away"):
            weak127 = gsr127[side]["weak"]
            if weak127 is None:
                continue
            add(side, "kapus", f"{weak127['poszt'].capitalize()}-szög védése",
                f"a kapusunk a {weak127['poszt']} posztról csak "
                f"{weak127['save_pct']:.0f}%-ot fogott "
                f"({weak127['faced']} kapura tartó lövés) — egy "
                "felkészült ellenfél pont onnan fogja lövetni",
                _drill127.get(weak127["poszt"],
                              "szög-védés: sorozatlövés az adott "
                              "posztról, kilépéssel és sarok-zárással"))
    except Exception:
        pass

    # 126) Hiba-sorozatok: ha egy eladás után jön a következő, a
    # hiba utáni rendezés a téma.
    try:
        from .defense import turnover_clusters
        tc126 = turnover_clusters(match, config)
        for side in ("home", "away"):
            rec126 = tc126[side]
            if rec126["verdict"] != "sorozatban hibáznak":
                continue
            add(side, "taktika", "Hiba utáni rendezés",
                f"az eladásaink {rec126['share_pct']:.0f}%-a egy "
                f"percen belül követte az előzőt "
                f"({rec126['clustered']}/{rec126['turnovers']}, "
                f"{rec126['clusters']} sorozat) — egy hiba után "
                "kapkodunk, és rögtön jön a második",
                "hiba utáni rendezés: támadójáték azzal a szabállyal, "
                "hogy eladott labda után a következő támadás KÖTÖTT — "
                "kijelölt indító, legalább négy passz, és csak "
                "biztos helyzetből lehet befejezni; edzésen "
                "eladás-büntetéssel (a hibázó ötös visszafut) "
                "gyakoroljátok, hogy meccsen is legyen mihez nyúlni")
    except Exception:
        pass

    # 125) Kapott gólok posztonként: ha egy poszt ellen szivárgunk, az
    # adott poszt védekezése a téma.
    try:
        from .defense import conceded_by_role
        cbr125 = conceded_by_role(match, config)
        _drill125 = {
            "szélső": ("szélső-védekezés: 1-1 a szélen, a védő "
                       "időben kifut és a kaputól elfelé tereli a "
                       "szélsőt, a kapus a rövid sarkot zárja — "
                       "sorozatban, mindkét oldalon"),
            "beálló": ("beálló-védekezés: 3-3 a 6 m körül, a "
                       "középső védő elé áll a beállónak és nem "
                       "engedi befordulni, a szomszéd hangosan "
                       "átadja — beúszó beállóval is"),
            "átlövő": ("átlövés-védekezés: kilépés-gyakorlat a "
                       "lövő-vonalba felemelt kézzel, majd azonnali "
                       "visszalépés a résbe, a kapus a blokk mögé "
                       "rendezve"),
            "irányító": ("irányító-védekezés: kettőzés a 9 m-en "
                         "kívül, a labdás irányítót két védő zárja, "
                         "a többiek csúsznak — a kettőzés utáni "
                         "visszarendeződéssel együtt"),
        }
        for side in ("home", "away"):
            top125 = cbr125[side]["top"]
            if top125 is None:
                continue
            add(side, "védekezés", f"{top125['poszt'].capitalize()}-védekezés",
                f"a kapott góljaink {top125['share_pct']:.0f}%-a a "
                f"{top125['poszt']} posztról jött "
                f"({top125['goals']}/{cbr125[side]['goals']}) — a "
                "falunk ezen a poszton szivárog, és egy felkészült "
                "ellenfél pont oda fog játszani",
                _drill125.get(top125["poszt"],
                              "poszt-védekezés: az adott poszt elleni "
                              "1-1 és segítő-csúszás gyakorlása"))
    except Exception:
        pass

    # 124) Poszt szerinti gólmegoszlás: ha egy posztra épül a
    # befejezésünk, a poszt-váltogatás a téma.
    try:
        from .roles import goals_by_role
        gbr124 = goals_by_role(match, config)
        for side in ("home", "away"):
            top124 = gbr124[side]["top"]
            if top124 is None:
                continue
            add(side, "támadás", "Befejezés több posztról",
                f"a góljaink {top124['share_pct']:.0f}%-a a "
                f"{top124['poszt']} posztról jött "
                f"({top124['goals']}/{gbr124[side]['goals']}) — egy "
                "felkészült ellenfél erre az egy posztra rendezi a "
                "védekezését, és elfogy a támadásunk",
                "befejezés több posztról: felállt támadás azzal a "
                f"szabállyal, hogy a {top124['poszt']} posztról csak "
                "minden harmadik befejezés jöhet — a többit a "
                "szomszédos posztoknak kell megoldaniuk (üres "
                "kapura, majd kapussal), hogy meccsen is bátran "
                "lőjenek onnan")
    except Exception:
        pass

    # 123) Gólpassz-zónák: ha minden előkészítés egy vonalról jön, a
    # támadásunk kiszámítható — a második vonal nyitása a téma.
    try:
        from .event_detection import assist_zones
        az123 = assist_zones(match, config)
        for side in ("home", "away"):
            top123 = az123[side]["top"]
            if top123 is None:
                continue
            add(side, "támadás", "Előkészítés két vonalról",
                f"a gólpasszaink {top123['share_pct']:.0f}%-a "
                f"{top123['zone']} érkezett "
                f"({top123['goals']}/{az123[side]['assists']}) — egy "
                "felkészült védelem ezt az egy átadás-vonalat zárja, "
                "és elfogy a támadásunk",
                "előkészítés két vonalról: 6-0 elleni támadó-játék "
                "azzal a szabállyal, hogy a gólpassz nem jöhet "
                f"kétszer egymás után {top123['zone']} — a "
                "befejezésnek legalább két különböző vonalról kell "
                "előkészítve lennie (szélső, beálló, átlövő), "
                "különben a gól nem számít")
    except Exception:
        pass

    # 122) Támadás-indítók: ha egy ember hozza fel a labdát, a
    # kihozatal letámadás-állóvá tétele a téma.
    try:
        from .attack_types import attack_starters
        st122 = attack_starters(match, config)
        for side in ("home", "away"):
            top122 = st122[side]["top"]
            if top122 is None:
                continue
            who122 = (f"a {top122['jersey']}-es mezszámú játékos"
                      if top122.get("jersey") is not None
                      else f"a {top122['player_id']} azonosítójú játékos")
            add(side, "támadás", "Kihozatal több kézbe",
                f"{who122} hozta fel a labdát a támadások "
                f"{top122['share_pct']:.0f}%-ában "
                f"({top122['starts']}/{st122[side]['attacks']}) — egy "
                "letámadó ellenfél ezt kiszámolja, és őt fogja "
                "elzárni",
                "kihozatal letámadás ellen: 4-2 elleni kihozatal a "
                "saját térfélen, azzal a szabállyal, hogy a "
                "felhozatalt három különböző ember indítja "
                "felváltva (a kapus indítása is számít); ha az "
                "elsőt zárják, a második opció automatikusan "
                "beindul — a kapussal együtt gyakorolva")
    except Exception:
        pass

    # 121) Időkérés-időzítés: ha későn fékezünk, a sorozat-kezelés
    # (mikor kérünk időt) a téma.
    try:
        from .stoppages import TOT_LATE_MIN, timeout_timing
        tot121 = timeout_timing(match, config)
        for side in ("home", "away"):
            rec121 = tot121[side]
            if rec121["verdict"] != "hagyják elszaladni":
                continue
            add(side, "taktika", "Sorozat-kezelés",
                f"átlag {rec121['avg_before']:.1f} kapott gól után "
                f"kértünk időt ({rec121['timeouts']} időkérés, a "
                f"küszöb {TOT_LATE_MIN:.1f}) — mire megszakítottuk a "
                "játékot, a sorozat már elvitte a meccset",
                "sorozat-kezelés: fix szabály a kispadon — a MÁSODIK "
                "kapott gól után jön az időkérés, és legyen rá egy "
                "bejátszott, 20 másodperces forgatókönyv (kijelölt "
                "befejező, egy figura, egy védekezési utasítás); "
                "edzésen játsszátok le hátrányból indulva")
    except Exception:
        pass

    # 120) Páros-mérleg: ha egy kettősünk együtt érdemben rosszabb, az
    # egység-építés (kivel kivel) a téma.
    try:
        from .stats import PAIR_MIN_MINUTES, pair_plus_minus
        prm120 = pair_plus_minus(match, config)
        for side in ("home", "away"):
            worst120 = prm120[side]["worst"]
            if worst120 is None \
                    or worst120["minutes"] < PAIR_MIN_MINUTES:
                continue
            add(side, "taktika", "Egység-építés",
                f"a(z) {' és '.join(str(i) for i in worst120['players'])} "
                f"azonosítójú kettősünk együtt {worst120['for']}-"
                f"{worst120['against']} mérleget hozott "
                f"({worst120['minutes']:.0f} közös perc, "
                f"{worst120['diff_per_min']:.2f} gól/perc a csapatátlag "
                "helyett) — külön-külön lehetnek jók, együtt nem "
                "működnek",
                "egység-építés: nézzétek meg a közös szakaszaikat "
                "(ki hova mozdul, ki kit fed), és próbáljátok ki őket "
                "külön blokkban egy-egy edzőmeccsen; ha a párosítás "
                "marad, adjatok nekik egy fix feladat-megosztást "
                "(egyikük indít, a másik zár)")
    except Exception:
        pass

    # 119) Csere-blokkok: ha egységekben cserélünk, a csere-fegyelem
    # (a váltás ütemének védelme) a téma.
    try:
        from .substitutions import (SUBBLK_BLOCK_PCT,
                                    substitution_blocks)
        sbl119 = substitution_blocks(match, config)
        for side in ("home", "away"):
            rec119 = sbl119[side]
            if rec119["verdict"] != "blokkos csere":
                continue
            add(side, "taktika", "Csere-fegyelem",
                f"egységekben cserélünk (a {rec119['waves']} "
                f"hullámból {rec119['block_waves']} volt 2+ fős, a "
                f"küszöb {SUBBLK_BLOCK_PCT:.0f}%) — a váltás ütemében "
                "egy pillanatra rossz emberek vannak a pályán, ezt "
                "egy gyors ellenfél megbünteti",
                "csere-fegyelem: a blokkos cserét csak holt "
                "játékhelyzetben (kapusnál lévő labda, saját "
                "bedobás) indítsátok, kijelölt fékező emberrel "
                "középen; edzésen 20 gyakorlás élő játékban, "
                "stopperrel — a hullám maradjon 3 mp alatt")
    except Exception:
        pass

    # 118) Lövőerő-esés: ha a 2. félidőre esik a lövéserőnk, a fáradt
    # állapotban gyakorolt befejezés a téma.
    try:
        from .event_detection import (POWER_FADE_DROP_KMH,
                                      shot_power_fade)
        spf118 = shot_power_fade(match, config)
        for side in ("home", "away"):
            rec118 = spf118[side]
            if rec118["drop_kmh"] is None \
                    or rec118["drop_kmh"] < POWER_FADE_DROP_KMH:
                continue
            add(side, "erőnlét", "Lövőerő a hajrában",
                f"a 2. félidőre {rec118['drop_kmh']:.0f} km/h-t "
                f"vesztett a lövésünk ({rec118['fh_avg_kmh']:.0f} → "
                f"{rec118['sh_avg_kmh']:.0f} km/h, a küszöb "
                f"{POWER_FADE_DROP_KMH:.0f}) — a hajrában az átlövés "
                "már nem fegyver",
                "fáradt befejezés: minden edzés végén 10 perc "
                "lövőgyakorlat magas pulzuson (sprint után azonnal "
                "lövés), a törzs- és vállerő heti két külön körrel; a "
                "hajrá-figurákban pedig a kidolgozott ziccer legyen a "
                "cél, ne a távoli bomba")
    except Exception:
        pass

    # 117) Labdatartás-idő: ha valakinél érdemben megáll a labda, a
    # gyorsabb továbbítás a téma.
    try:
        from .decisions import HOLD_GAP_S, hold_time_players
        htp117 = hold_time_players(match, config)
        for side in ("home", "away"):
            slow117 = htp117[side]["slowest"]
            if slow117 is None:
                continue
            who117 = (f"{slow117['jersey']}-es mezszámú"
                      if slow117["jersey"] is not None
                      else f"{slow117['player_id']} azonosítójú")
            add(side, "támadás", "Gyorsabb továbbítás",
                f"a(z) {who117} játékosunknál áll meg a labda: átlag "
                f"{slow117['avg_s']:.1f} mp tartás a csapatátlag "
                f"{htp117[side]['avg_s']:.1f} mp helyett "
                f"({slow117['holds']} labdás szakasz, a küszöb "
                f"{HOLD_GAP_S:.1f} mp eltérés) — nála van ideje "
                "odaérni a kettőzésnek",
                "két-érintéses játék: felállt támadásban a labda "
                "legfeljebb két ütemig maradhat egy kézben "
                "(passz–passz–befejezés), külön kör érkezés közbeni "
                "átvétellel; nála pedig kényszerítő döntés: elzárásra "
                "indulás vagy azonnali továbbadás")
    except Exception:
        pass

    # 116) Védekezés-váltás: ha végig egy rendszert játszunk, a
    # második változat betanítása a téma.
    try:
        from .tactics import FSW_ONE_SYSTEM_PCT, formation_switching
        fsw116 = formation_switching(match, config)
        for side in ("home", "away"):
            rec116 = fsw116[side]
            if rec116["verdict"] != "egy rendszer":
                continue
            add(side, "védekezés", "Második védekezési változat",
                f"végig egy rendszert játszottunk ({rec116['main']}, a "
                f"védekezett támadások {rec116['main_pct']:.0f}%-ában, "
                f"a küszöb {FSW_ONE_SYSTEM_PCT:.0f}%) — ha az "
                "ellenfél megfejti, nincs mire váltani",
                "második változat: 15 perc alapforma-váltás jelre "
                "(6-0 ↔ 5-1) élő támadás közben, hangos bemondással; "
                "a váltás pillanatában az előretolt védő és a "
                "szomszédja átadja egymásnak az embert")
    except Exception:
        pass

    # 115) Célba vett védő: ha egy védőnk előtt a csapatátlagnál
    # érdemben többször megy be a lövés, a segítség-rendszer a téma.
    try:
        from .defense import (TDEF_GAP_PP, TDEF_MIN_SHOTS,
                              targeted_defenders)
        tdf115 = targeted_defenders(match, config)
        for side in ("home", "away"):
            weak115 = tdf115[side]["weak"]
            if weak115 is None \
                    or weak115["shots"] < TDEF_MIN_SHOTS:
                continue
            who115 = (f"{weak115['jersey']}-es mezszámú"
                      if weak115["jersey"] is not None
                      else f"{weak115['player_id']} azonosítójú")
            add(side, "védekezés", "Védő-segítés",
                f"a(z) {who115} védőnk előtt megy be a legtöbb lövés "
                f"({weak115['goals']}/{weak115['shots']}, a "
                f"csapatátlagnál {weak115['gap_pp']:.0f} "
                f"százalékponttal magasabb gólarány, a küszöb "
                f"{TDEF_GAP_PP:.0f}) — az ellenfél oda viszi a "
                "befejezéseket",
                "segítés-rendszer: a szomszéd védő zárja a lövőszöget "
                "(kifelé tolás), a kapussal beszéljétek meg a szöget "
                "ezen a poszton, és külön 1-1 blokk: kilépés–"
                "visszalépés a lövő elé, elzárás alatti átcsúszással")
    except Exception:
        pass

    # 114) Játékos-mérleg: ha valakinek a pályán léte alatt érdemben
    # rosszabb a gólkülönbségünk, a szerep-tisztázás a téma.
    try:
        from .stats import PM_MIN_MINUTES, player_plus_minus
        pm114 = player_plus_minus(match, config)
        for side in ("home", "away"):
            worst114 = pm114[side]["worst"]
            if worst114 is None \
                    or worst114["minutes"] < PM_MIN_MINUTES:
                continue
            add(side, "taktika", "Szerep-tisztázás",
                f"a(z) {worst114['player_id']} azonosítójú játékosunk "
                f"pályán léte alatt {worst114['for']}-"
                f"{worst114['against']} a mérlegünk "
                f"({worst114['minutes']:.0f} perc, "
                f"{worst114['diff_per_min']:.2f} gól/perc a csapatátlag "
                "helyett) — nem ítélet, hanem kérdés: kivel és mikor "
                "játszik",
                "szerep-tisztázás: nézzétek végig a vele töltött "
                "szakaszokat (kivel van egy egységben, milyen "
                "állásnál), párosítsátok stabil társsal, és adjatok "
                "neki egy világos feladatot támadásban és "
                "védekezésben is")
    except Exception:
        pass

    # 113) Lövő-erő: ha van a csapatátlag felett bombázónk, a távoli
    # befejezés köré épített figura a téma.
    try:
        from .event_detection import (SHOOTER_POWER_MIN_SHOTS,
                                      shooter_power)
        spw113 = shooter_power(match, config)
        for side in ("home", "away"):
            cannon113 = spw113[side]["cannon"]
            if cannon113 is None \
                    or cannon113["shots"] < SHOOTER_POWER_MIN_SHOTS:
                continue
            add(side, "támadás", "Bombázó kihasználása",
                f"a(z) {cannon113['player_id']} azonosítójú lövőnk "
                f"bombáz ({cannon113['avg_kmh']:.0f} km/h átlag, "
                f"csapatátlag {spw113[side]['avg_kmh']:.0f} km/h, "
                f"csúcs {cannon113['max_kmh']:.0f} km/h) — ezt a "
                "fegyvert tudatosan kell elsütni",
                "bombázó kihasználása: elzárás-figura az ő "
                "lövőtávjára (a fal kihúzása után szabad átlövés), "
                "gyors labdajáratás az ő oldalára a fal átterhelésével, "
                "és lövés-sorozat fáradtan — a végén is meglegyen a "
                "sebesség")
    except Exception:
        pass

    # 112) Lövő-kapuoldal: ha egy befejezőnk mindig ugyanoda lő, a
    # kapuoldal-váltás a téma.
    try:
        from .attack_types import (SHOOTER_SIDE_MIN_GOALS,
                                   shooter_placement)
        shp112 = shooter_placement(match, config)
        for side in ("home", "away"):
            pred112 = shp112[side]["predictable"]
            if pred112 is None \
                    or pred112["goals"] < SHOOTER_SIDE_MIN_GOALS:
                continue
            add(side, "támadás", "Kapuoldal-váltás",
                f"a(z) {pred112['player_id']} azonosítójú lövőnk "
                f"kiszámítható: a {pred112['goals']} góljából "
                f"{pred112['share_pct']:.0f}% a "
                f"{pred112['dominant']} oldalra ment — a kapus "
                "felkészülhet rá",
                "kapuoldal-váltás vele: célzott lövés-sorozat a "
                "gyengébb oldalra (kapus nélkül, majd kapussal), "
                "vezényszóra váltott sarok lövés közben, és "
                "lövőcsel-gyakorlat — a kapus mozdulatára kell "
                "reagálni, nem előre eldönteni az oldalt")
    except Exception:
        pass

    # 111) Szélső-védekezés: ha a szélről kapjuk a gólokat, a
    # szélső-őrzés és a kapus szöge a téma.
    try:
        from .defense import (WINGDEF_GAP_PP, WINGDEF_MIN_SHOTS,
                              wing_defense)
        wdf111 = wing_defense(match, config)
        for side in ("home", "away"):
            rec111 = wdf111[side]
            if rec111["verdict"] != "szélen nyitott" \
                    or rec111["wing_shots"] < WINGDEF_MIN_SHOTS \
                    or rec111["gap_pp"] is None \
                    or rec111["gap_pp"] < WINGDEF_GAP_PP:
                continue
            add(side, "védekezés", "Szélső-védekezés",
                f"a szélről kapjuk a gólokat: a szélső lövések "
                f"{rec111['wing_pct']:.0f}%-a gól ellenünk "
                f"({rec111['wing_goals']}/{rec111['wing_shots']}), "
                f"középről csak {rec111['center_pct']:.0f}% — a "
                "szélső-őrzés és a kapus szöge a hiba",
                "szélső-védekezés: a szélső védő kilépése a labda "
                "érkezésekor (szöget zárva, nem szemben állva), "
                "kapus-védő egyeztetés a rövid sarokra, és "
                "szélső-lövés sorozat védése mindkét oldalon")
    except Exception:
        pass

    # 110) Drága eladók: ha egy játékosunk eladásai rendre gólba
    # kerülnek, vele a nyomás alatti labdakezelés a téma.
    try:
        from .defense import TO_COST_MIN, costly_turnover_players
        ctp110 = costly_turnover_players(match, config)
        for side in ("home", "away"):
            worst110 = ctp110[side]["worst"]
            if worst110 is None \
                    or worst110["turnovers"] < TO_COST_MIN \
                    or worst110["punished"] < 2:
                continue
            add(side, "támadás", "Nyomás alatti labdakezelés",
                f"a(z) {worst110['player_id']} azonosítójú játékosunk "
                f"eladásaiból {worst110['punished']} kapott gól lett "
                f"({worst110['turnovers']} eladásból) — az ő hibái "
                "kerülnek a legtöbbe",
                "nyomás alatti labdakezelés vele: kettőzés elleni "
                "kiszabadulás párokban, átvétel és passz zavarással "
                "(kéz a labdán), és döntés-gyakorlat — ha zárt a sáv, "
                "vissza a biztos társhoz, nem előre a présbe")
    except Exception:
        pass

    # 109) Emberelőny-védekezés: ha emberelőnyben is kapunk gólt, a
    # befejezés utáni visszarendeződés a téma.
    try:
        from .rules import PPDEF_MIN_S, powerplay_defense
        ppd109 = powerplay_defense(match, config)
        for side in ("home", "away"):
            rec109 = ppd109[side]
            if rec109["verdict"] != "szivárog" \
                    or rec109["pp_seconds"] < PPDEF_MIN_S \
                    or rec109["pp_per_min"] is None:
                continue
            add(side, "védekezés", "Emberelőny-védekezés",
                f"emberelőnyben is szivárgunk: {rec109['pp_conceded']} "
                f"kapott gól {rec109['pp_seconds'] / 60:.1f} perc "
                f"emberelőny alatt ({rec109['pp_per_min']:.2f} "
                f"gól/perc, egyenlő létszámnál "
                f"{rec109['eq_per_min']:.2f}) — a kiállítás nálunk "
                "nem büntetés, hanem kockázat",
                "emberelőny-védekezés: 6-5 elleni támadás úgy, hogy a "
                "befejezés után azonnal két ember hazasprintel, "
                "kijelölt biztosító a lövés pillanatában, és "
                "emberelőny-figura lövés-tiltással a szélső helyéről "
                "— előnyben nem kockázatos lövés kell, hanem gól")
    except Exception:
        pass

    # 108) Kapus szabad lövés ellen: ha a kapusunk csak a fal mögött
    # véd, a szabad lövés elleni kapusmunka a téma.
    try:
        from .goalkeeper import GKFREE_MIN_SHOTS, gk_free_shot_saves
        gkf108 = gk_free_shot_saves(match, config)
        for side in ("home", "away"):
            rec108 = gkf108[side]
            if rec108["verdict"] != "falfüggő" \
                    or rec108["free_shots"] < GKFREE_MIN_SHOTS \
                    or rec108["gap_pp"] is None:
                continue
            add(side, "kapus", "Szabad lövés elleni védés",
                f"a kapusunk falfüggő: fedezett lövésnél "
                f"{rec108['covered_save_pct']:.0f}%-ot véd, szabadon "
                f"leadottnál csak {rec108['free_save_pct']:.0f}%-ot "
                f"({rec108['free_saves']}/{rec108['free_shots']}) — "
                "tiszta lövéshelyzetben magára marad",
                "szabad lövés elleni kapusmunka: zavartalan átlövések "
                "sorozata változó ritmusban (a kapus indulási idejére), "
                "helyezkedés-korrekció a lövő karjához igazítva, és "
                "fal-kapus egyeztetés — a fal mindig egy oldalt zárjon, "
                "a kapus a másikat védje")
    except Exception:
        pass

    # 107) Kettőzés: ha nem lép rá második védő a labdásra, a
    # kettőzés-mechanizmus és a mögötte lévő zárás a téma.
    try:
        from .defense import (DOUBLE_MIN_FRAMES, double_teams)
        dbl107 = double_teams(match, config)
        for side in ("home", "away"):
            rec107 = dbl107[side]
            if rec107["verdict"] != "1v1-et hagy" \
                    or rec107["holder_frames"] < DOUBLE_MIN_FRAMES \
                    or rec107["doubled_pct"] is None:
                continue
            add(side, "védekezés", "Kettőzés",
                f"nem lépünk rá másodikként a labdásra: a labdás-idő "
                f"csak {rec107['doubled_pct']:.0f}%-ában van két "
                "védőnk a labdán — minden befejezőjük 1v1-et kap "
                "ellenünk",
                "kettőzés: kettőzés-jelre (vezényszó) begyakorolt "
                "rálépés a szomszéd védőtől, mögötte azonnali "
                "átvétel-csúszás a beállóra, és 4-4 kisjáték "
                "szabállyal — az átlövőt a lövés előtt két védőnek "
                "kell elérnie")
    except Exception:
        pass

    # 106) Kapus-indítás iránya: ha a kapusunk mindig ugyanarra az
    # oldalra nyit, az indítás-irány variálása a téma.
    try:
        from .goalkeeper import GK_SIDE_MIN_PASSES, gk_outlet_side
        gos106 = gk_outlet_side(match, config)
        for side in ("home", "away"):
            rec106 = gos106[side]
            if rec106["side"] is None \
                    or rec106["outlets"] < GK_SIDE_MIN_PASSES:
                continue
            pct106 = (rec106["left_pct"] if rec106["side"] == "bal"
                      else 100.0 - rec106["left_pct"])
            add(side, "kapus", "Indítás-irány",
                f"a kapusunk szinte mindig a {rec106['side']} oldalra "
                f"indít ({pct106:.0f}%, {rec106['outlets']} "
                "indításból) — az ellenfél előre elindulhat arra az "
                "oldalra, és a kidobásból lesz a kontrája",
                "indítás-irány: kidobás-gyakorlat mindkét oldalra "
                "(vezényszóra váltott irány), a két szélső egyszerre "
                "nyit ellentétes irányba, és letámadás elleni "
                "kihozatal — ha a fogadó oldal zárt, a kapus a "
                "másikra vagy rövidre indít")
    except Exception:
        pass

    # 105) Hajrá-eladás: ha a végén megugrik az eladás-ütemünk, a
    # nyomás alatti döntés és a hajrá-felállás a téma.
    try:
        from .momentum import (CLUTCH_TO_MIN_EARLY, CLUTCH_TO_RISE_PER_MIN,
                               clutch_turnovers)
        cto105 = clutch_turnovers(match, config)
        if cto105.get("available"):
            for side in ("home", "away"):
                rec105 = cto105[side]
                if rec105["verdict"] != "hajrá-hibázó" \
                        or rec105["early_to"] < CLUTCH_TO_MIN_EARLY \
                        or rec105["delta_per_min"] is None \
                        or rec105["delta_per_min"] < CLUTCH_TO_RISE_PER_MIN:
                    continue
                add(side, "támadás", "Hajrá-labdakezelés",
                    f"a hajrában megugrik az eladás-ütemünk "
                    f"({rec105['early_per_min']:.2f} → "
                    f"{rec105['clutch_per_min']:.2f} eladás/perc, "
                    f"{rec105['clutch_to']} eladás a hajrában) — "
                    "nyomás alatt rossz döntéseket hozunk",
                    "hajrá-labdakezelés: fix hajrá-felállás (ki viszi "
                    "a labdát, ki a beálló), döntés-játék zajjal és "
                    "eredményjelzővel (élő állás, fogyó idő), és "
                    "szabály a kisjátékban — a hajrában a rossz passz "
                    "kétszer annyit ér az ellenfélnek")
    except Exception:
        pass

    # 104) Hátrány-támadás: ha a kiállítás alatt megbénul a
    # támadójátékunk, a hátrányos labdatartás a téma.
    try:
        from .rules import SHATK_MIN_S, shorthanded_attack
        sha104 = shorthanded_attack(match, config)
        for side in ("home", "away"):
            rec104 = sha104[side]
            if rec104["verdict"] != "megbénul" \
                    or rec104["sh_seconds"] < SHATK_MIN_S \
                    or rec104["sh_per_min"] is None:
                continue
            add(side, "támadás", "Hátrány-támadás",
                f"emberhátrányban megbénulunk: {rec104['sh_goals']} gól "
                f"{rec104['sh_seconds'] / 60:.1f} perc kiállítás alatt "
                f"({rec104['sh_per_min']:.2f} gól/perc, egyenlő "
                f"létszámnál {rec104['eq_per_min']:.2f}) — minden "
                "kiállítás azonnal gólkülönbség",
                "hátrányos támadás: 5-6 elleni labdatartás-játék "
                "(időre, eladás nélkül), betanult 5 fős figura "
                "beállóval, és hátrányban is vállalt lerohanás — a "
                "két percet ki kell húzni, nem átvészelni")
    except Exception:
        pass

    # 103) Fölény-befejezés: ha csak létszámfölényben vagyunk
    # eredményesek, a felállt támadás befejezése a téma.
    try:
        from .attack_types import (OVERLOAD_GAP_PP, OVERLOAD_MIN_SHOTS,
                                   overload_finishing)
        ovl103 = overload_finishing(match, config)
        for side in ("home", "away"):
            rec103 = ovl103[side]
            if rec103["verdict"] != "fölény-függő" \
                    or rec103["set_shots"] < OVERLOAD_MIN_SHOTS \
                    or rec103["gap_pp"] is None \
                    or rec103["gap_pp"] < OVERLOAD_GAP_PP:
                continue
            add(side, "támadás", "Felállt támadás",
                f"csak létszámfölényben vagyunk eredményesek: "
                f"fölényben {rec103['overload_pct']:.0f}%, felállt fal "
                f"ellen {rec103['set_pct']:.0f}% a gólarányunk "
                f"({rec103['set_goals']}/{rec103['set_shots']}) — ha "
                "az ellenfél hazaér, elfogy a fegyverünk",
                "felállt támadás: 6-0 elleni figura-sor betanítása "
                "(keresztezés, beállós bejátszás, elzárás utáni "
                "lövés), 1v1-áttörés gyakorlása lövő-távolságról, és "
                "6-6 felállt támadás lerohanás-tiltással (csak "
                "kidolgozott helyzetből lehet befejezni)")
    except Exception:
        pass

    # 102) Ellen-press: ha az eladott labdára nem támadunk rá, a
    # szerzés utáni első három másodperc a téma.
    try:
        from .defense import (COUNTERPRESS_MIN_TO, COUNTERPRESS_WINDOW_S,
                              counter_press)
        cpr102 = counter_press(match, config)
        for side in ("home", "away"):
            rec102 = cpr102[side]
            if rec102["verdict"] != "beletörődik" \
                    or rec102["turnovers"] < COUNTERPRESS_MIN_TO \
                    or rec102["rate_pct"] is None:
                continue
            add(side, "védekezés", "Ellen-press",
                f"az eladás után beletörődünk: az eladásaink "
                f"{rec102['rate_pct']:.0f}%-a után szerezzük csak "
                f"vissza a labdát {COUNTERPRESS_WINDOW_S:.0f} mp-en "
                f"belül ({rec102['regained']}/{rec102['turnovers']}) — "
                "az ellenfél minden szerzése ingyen kontra",
                "ellen-press: átmenet-játék eladás-jelre (a labda "
                "elvesztésekor a legközelebbi két játékos azonnal "
                "rátámad, a többi zárja a mélységet), 3 mp-es "
                "visszaszerzési szabály kisjátékban, és eladás utáni "
                "sprint-vezényszó a felállásban")
    except Exception:
        pass

    # 101) Hajrá-lövésválasztás: ha a végén romlik a lövéseink
    # helyzetértéke, a hajrá-figurák és a türelem a téma.
    try:
        from .momentum import (CLUTCH_SQ_DROP, CLUTCH_SQ_MIN_SHOTS,
                               clutch_shot_quality)
        csq101 = clutch_shot_quality(match, config)
        if csq101.get("available"):
            for side in ("home", "away"):
                rec101 = csq101[side]
                if rec101["verdict"] != "elkapkodja" \
                        or rec101["clutch_shots"] < CLUTCH_SQ_MIN_SHOTS \
                        or rec101["delta"] is None \
                        or -rec101["delta"] < CLUTCH_SQ_DROP:
                    continue
                add(side, "támadás", "Hajrá-türelem",
                    f"a hajrában elkapkodjuk a befejezést: a lövéseink "
                    f"helyzetértéke {rec101['early_avg']:.2f}-ről "
                    f"{rec101['clutch_avg']:.2f}-re esik "
                    f"({rec101['clutch_shots']} hajrá-lövés) — nyomás "
                    "alatt rossz helyzetekből lövünk",
                    "hajrá-türelem: betanult hajrá-figurák (2-3 fix "
                    "befejezés, amit fáradtan is tudunk), "
                    "fáradt-állapotú befejezés-gyakorlat (sprint utáni "
                    "lövés kidolgozott helyzetből), és szabály a "
                    "kisjátékban — a hajrában csak a második "
                    "labdaérintés után, kidolgozott helyzetből lőhetsz")
    except Exception:
        pass

    # 100) Passz-kockázat: ha a hosszú passzaink elvesznek, a hosszú
    # passz technikája és a bejátszás-döntés a téma.
    try:
        from .attack_types import (PASSRISK_GAP_PP,
                                   PASSRISK_MIN_TRIES, pass_risk)
        prk100 = pass_risk(match, config)
        for side in ("home", "away"):
            rec100 = prk100[side]
            if rec100["verdict"] != "kockázatos" \
                    or rec100["long_tries"] < PASSRISK_MIN_TRIES \
                    or rec100["gap_pp"] is None \
                    or rec100["gap_pp"] < PASSRISK_GAP_PP:
                continue
            add(side, "támadás", "Hosszú passz",
                f"a hosszú passzaink elvesznek: "
                f"{rec100['long_to_pct']:.0f}%-uk eladás "
                f"({rec100['long_to']}/{rec100['long_tries']}), a "
                f"rövideknek csak {rec100['short_to_pct']:.0f}%-a — "
                "az ellenfél a hosszú sávjainkban vadászik",
                "hosszú passz: feszes, előre vezetett labda "
                "technika-sor (mellmagasság, futó társ elé), "
                "átjátszás védő-sávon át párokban, és döntés-játék — "
                "ha a sáv zárt, a hosszú passz helyett indíts")
    except Exception:
        pass

    # 99) Elzárás-védekezés: ha az elzárásokon szétesik a váltásunk,
    # a váltás-kommunikáció a téma.
    try:
        from .defense import (SCRDEF_GAP_PP, SCRDEF_MIN_SCREENED,
                              screen_defense)
        scd99 = screen_defense(match, config)
        for side in ("home", "away"):
            rec99 = scd99[side]
            if rec99["verdict"] != "gyenge" \
                    or rec99["screened_shots"] < SCRDEF_MIN_SCREENED \
                    or rec99["gap_pp"] is None \
                    or rec99["gap_pp"] < SCRDEF_GAP_PP:
                continue
            add(side, "védekezés", "Váltás elzáráson",
                f"az elzárásokon szétesik a váltásunk: elzárásos "
                f"lövésekből {rec99['screened_pct']:.0f}% gól esik "
                f"ellenünk, elzárás nélküliekből csak "
                f"{rec99['open_pct']:.0f}% "
                f"({rec99['screened_goals']}/"
                f"{rec99['screened_shots']} vs {rec99['open_goals']}/"
                f"{rec99['open_shots']}) — a zár mögül mindig tiszta "
                "lövést kapunk",
                "váltás elzáráson: hangos váltás-gyakorlat (a zárt "
                "védő kiált, a szomszéd veszi át), átcsúszás a zár "
                "elé félpályás 3-3-ban, és zár-leolvasás — a zárót a "
                "közeli védő fogja, a lövőt a váltó")
    except Exception:
        pass

    # 98) Elzárás-használat: ha elzárás nélkül lövünk, a lövőnk
    # magára marad — az elzárás-játék a téma.
    try:
        from .attack_types import (SCREEN_LOW_PCT, SCREEN_MIN_SHOTS,
                                   screen_usage)
        scu98 = screen_usage(match, config)
        for side in ("home", "away"):
            rec98 = scu98[side]
            if rec98["style"] != "elzárás nélküli" \
                    or rec98["shots"] < SCREEN_MIN_SHOTS \
                    or rec98["screen_pct"] > SCREEN_LOW_PCT:
                continue
            add(side, "támadás", "Elzárás-játék",
                f"elzárás nélkül lövünk: az őrzött lövéseink csak "
                f"{rec98['screen_pct']:.0f}%-ánál zárja el társ a "
                f"lövő őrzőjét ({rec98['screened']}/{rec98['shots']}) "
                "— a lövőink magukra maradnak a kilépő védővel "
                "szemben",
                "elzárás-játék: beállós elzárás-sor (a beálló az "
                "átlövő őrzőjére zár, az átlövő a zár mögé lép), "
                "átlövő-átlövő kereszt elzárással, és leolvasás — "
                "váltásnál a zárótól indul a leszakadás")
    except Exception:
        pass

    # 97) Oldalváltás: ha egy oldalon ragadunk, a fal ellenünk
    # nyugodtan eltolható — a keresztjáték a téma.
    try:
        from .attack_types import (SWITCH_LOW_PCT, SWITCH_MIN_PASSES,
                                   side_switching)
        ssw97 = side_switching(match, config)
        for side in ("home", "away"):
            rec97 = ssw97[side]
            if rec97["style"] != "egy-oldalas" \
                    or rec97["passes"] < SWITCH_MIN_PASSES \
                    or rec97["switch_pct"] > SWITCH_LOW_PCT:
                continue
            add(side, "támadás", "Oldalváltás",
                f"egy oldalon ragadunk: a támadó passzaink csak "
                f"{rec97['switch_pct']:.0f}%-a oldalváltás "
                f"({rec97['switches']}/{rec97['passes']}) — a fal "
                "nyugodtan ránk tolható, a túloldali szélsőnk éhen "
                "marad",
                "keresztjáték: kötelező két oldalváltás minden "
                "akcióban (kisjáték-szabály), hosszú keresztpassz "
                "technika-sor (feszes, egy ütemű váltás), és "
                "szélső-szélső átjátszás a fal átmozgatására")
    except Exception:
        pass

    # 96) Lerohanás-védés: ha a kapusunk gyorsindítás ellen szakad
    # be, a kapus-edzés és a visszarendeződés együtt a téma.
    try:
        from .goalkeeper import (GKBR_GAP_PP, GKBR_MIN_FACED,
                                 gk_break_response)
        gkb96 = gk_break_response(match, config)
        for side in ("home", "away"):
            rec96 = gkb96[side]
            if rec96["verdict"] != "érzékeny" \
                    or rec96["fast_faced"] < GKBR_MIN_FACED \
                    or rec96["set_faced"] < GKBR_MIN_FACED \
                    or rec96["set_pct"] - rec96["fast_pct"] \
                    < GKBR_GAP_PP:
                continue
            add(side, "kapus", "Lerohanás-védés",
                f"a kapusunk gyorsindítás ellen "
                f"{rec96['fast_pct']:.0f}%-ot véd, rendezett támadás "
                f"ellen {rec96['set_pct']:.0f}%-ot ({rec96['fast_saves']}"
                f"/{rec96['fast_faced']} vs {rec96['set_saves']}/"
                f"{rec96['set_faced']}) — az átmenet a nyílt sebünk",
                "lerohanás-védés a kapusnak: 2v1 és 3v2 gyorsindítás "
                "elleni sorozat (gyors kijövetel, szög-zárás, lábmunka "
                "hátrálásból), a mezőnynek pedig visszarendeződés — a "
                "kapus ne maradjon egyedül az első hullám ellen")
    except Exception:
        pass

    # 95) Gól-előkészítés hossza: ha csak hosszú akcióból van gólunk,
    # az első hullámunk fogatlan — a direkt befejezés a téma.
    try:
        from .attack_types import (BUILDUP_LONG_SHARE,
                                   BUILDUP_MIN_GOALS, goal_buildup)
        gb95 = goal_buildup(match, config)
        for side in ("home", "away"):
            rec95 = gb95[side]
            if rec95["style"] != "kombinatív" \
                    or rec95["goals"] < BUILDUP_MIN_GOALS \
                    or rec95["long_pct"] < BUILDUP_LONG_SHARE:
                continue
            add(side, "támadás", "Direkt befejezés",
                f"csak hosszú akcióból van gólunk: a góljaink "
                f"{rec95['long_pct']:.0f}%-a 5+ passzos akció vége "
                f"({rec95['long']}/{rec95['goals']}) — az első "
                "hullámunk és az átmenetünk nem termel, minden gólért "
                "sokat kell dolgoznunk",
                "direkt befejezés: 2 passzos gyorsindítás-sorozat "
                "(szerzés után legfeljebb két passz a kapuig), első "
                "hullámos befejezés 3-2 ellen, és lerohanás-verseny — "
                "a gyors gól is legyen a repertoárban")
    except Exception:
        pass

    # 94) Előkészítő-függés: ha a gólpasszaink egy emberen múlnak, az
    # ellenfél őt vágja el — második játékszervező kell.
    try:
        from .attack_types import (ASSIST_CONC_MIN,
                                   ASSIST_CONC_TOP_SHARE,
                                   assist_concentration)
        ac94 = assist_concentration(match, config)
        for side in ("home", "away"):
            rec94 = ac94[side]
            if not rec94["concentrated"] \
                    or rec94["assists"] < ASSIST_CONC_MIN \
                    or rec94["share"] < ASSIST_CONC_TOP_SHARE:
                continue
            add(side, "támadás", "Második játékszervező",
                f"az előkészítésünk egy emberen múlik: a gólpasszaink "
                f"{100.0 * rec94['share']:.0f}%-a a(z) "
                f"{rec94['top_player_id']}. játékostól jön "
                f"({rec94['top_assists']}/{rec94['assists']}) — ha őt "
                "elveszik vagy elfárad, megáll a befejezésünk",
                "második játékszervező kinevelése: irányító-szerep "
                "forgatása a kisjátékban, betanult figurák a másik "
                "átlövő indításával, és befejezés előkészítő nélkül "
                "(cselből átlövés) — a fő előkészítő pihenőjében is "
                "legyen gólunk")
    except Exception:
        pass

    # 93) Középkezdés-tempó: ha kapott gól után lassan indítunk, az
    # ellenfél falja rendezetten vár — a gyors középkezdés a téma.
    try:
        from .momentum import (RESTART_MIN_GOALS, RESTART_SLOW_SHARE,
                               restart_speed)
        rs93 = restart_speed(match, config)
        for side in ("home", "away"):
            rec93 = rs93[side]
            if rec93["style"] != "lassú" \
                    or rec93["restarts"] < RESTART_MIN_GOALS \
                    or rec93["fast_pct"] > RESTART_SLOW_SHARE:
                continue
            add(side, "támadás", "Gyors középkezdés",
                f"kapott gól után lassan indítunk: átlag "
                f"{rec93['avg_s']:.0f} mp, mire a labda átér az "
                f"ellenfél térfelére (csak {rec93['fast']}/"
                f"{rec93['restarts']} gyors újraindítás) — mire "
                "odaérünk, a faluk rendezetten vár",
                "gyors középkezdés: kijelölt labdaszedő (a kapott gól "
                "után az övé a labda), begyakorolt első három passz "
                "középkezdésből, és 5 mp-es szabály a kisjátékban — "
                "aki gól után 5 mp-en belül nem indít, labdát veszt")
    except Exception:
        pass

    # 92) Elsütés-idő: ha a lövőink sokáig fogják a labdát, a blokk
    # és a kilépés mindig odaér — a gyors elsütés a téma.
    try:
        from .xg import (RELEASE_MIN_SHOTS, RELEASE_SLOW_SHARE,
                         shot_release)
        sr92 = shot_release(match, config)
        for side in ("home", "away"):
            rec92 = sr92[side]
            if rec92["style"] != "labdafogó" \
                    or rec92["shots"] < RELEASE_MIN_SHOTS \
                    or rec92["quick_pct"] > RELEASE_SLOW_SHARE:
                continue
            add(side, "támadás", "Gyors elsütés",
                f"a lövőink sokáig fogják a labdát: csak "
                f"{rec92['quick_pct']:.0f}% a gyors (0,6 mp-en "
                f"belüli) elsütés, átlag {rec92['avg_hold_s']:.1f} mp "
                "birtoklás a lövés előtt — a blokk és a kilépő védő "
                "mindig odaér ránk",
                "gyors elsütés: kapásból lövés sorozatban (passzból "
                "egy ütem, lövés), lövő-kör időnyomással (aki 1 mp-nél "
                "tovább fogja, ismétel), és döntés-gyakorlat: kapás "
                "előtt eldöntve lövés vagy passz")
    except Exception:
        pass

    # 91) Beálló-védekezés: ha az ellenfél beállója ellen szakad be a
    # falunk, a beálló-őrzés (elöl-mögött, kettőzés) a téma.
    try:
        from .defense import PIVOT_DEF_MIN_ATTACKS, pivot_defense
        pd91 = pivot_defense(match, config)
        for side in ("home", "away"):
            rec91 = pd91[side]
            if rec91["verdict"] != "gyenge" \
                    or rec91["pivot_attacks"] < PIVOT_DEF_MIN_ATTACKS:
                continue
            add(side, "védekezés", "Beálló-őrzés",
                f"az ellenünk vezetett beállós támadások "
                f"{rec91['pivot_goal_pct']:.0f}%-a lett gól, a beálló "
                f"nélkülieknek csak "
                f"{rec91['other_goal_pct']:.0f}%-a — a beálló ellenünk "
                "külön fegyver",
                "beálló-őrzés: elöl-mögött váltás gyakorlása jelre (ki "
                "megy elé, ki mögé), kettőzés-időzítés a beúszásra, és "
                "a beálló testes zárása labda nélkül — 3-3 elleni "
                "játék középen, ahol a beálló az egyetlen befejező")
    except Exception:
        pass

    # 90) Indítás-biztonság: ha a kapus-indításunk az ellenfélnél köt
    # ki, a kihozatalunk letámadható — a biztos első passz a téma.
    try:
        from .goalkeeper import (GK_OUTLET_LOST_PCT, GK_OUTLET_SEC_MIN,
                                 gk_outlet_security)
        gs90 = gk_outlet_security(match, config)
        for side in ("home", "away"):
            rec90 = gs90[side]
            if rec90["lost_pct"] is None \
                    or rec90["outlets"] < GK_OUTLET_SEC_MIN \
                    or rec90["lost_pct"] < GK_OUTLET_LOST_PCT:
                continue
            add(side, "kapus", "Indítás-biztonság",
                f"a kapus-indításunk elcsíphető: {rec90['outlets']} "
                f"indításból {rec90['lost']} az ellenfélnél kötött ki "
                f"({rec90['lost_pct']:.0f}%) — a letámadás ellenünk "
                "termel",
                "indítás-biztonság: kihozatal-minták letámadás ellen "
                "(két biztos rövid opció + egy hosszú szélső-kiugrás), "
                "a kapus döntés-gyakorlata nyomás alatt (mikor rövid, "
                "mikor hosszú, mikor időhúzó), és a fogadók "
                "elmozgás-időzítése a kapus-labda pillanatában")
    except Exception:
        pass

    # 89) Támadó-mozgás: ha áll a támadásunk, a védő ingyen léphet ki
    # ránk — a labda nélküli mozgás (passzolj és fuss) a téma.
    try:
        from .tactics import (ATTACK_MOTION_MIN_S,
                              ATTACK_MOTION_STATIC_MPS, attack_motion)
        am89 = attack_motion(match, config)
        for side in ("home", "away"):
            rec89 = am89[side]
            if rec89["style"] != "álló" \
                    or rec89["time_s"] < ATTACK_MOTION_MIN_S \
                    or rec89["avg_mps"] > ATTACK_MOTION_STATIC_MPS:
                continue
            add(side, "támadás", "Labda nélküli mozgás",
                f"áll a támadásunk: szervezett támadásban átlag "
                f"{rec89['avg_mps']:.1f} m/s-mal mozgunk — az álló "
                "támadóra a védő kockázat nélkül kiléphet, a "
                "kilépés ellenünk ingyen van",
                "passzolj és fuss: minden passz után kötelező elfutás "
                "(a passz utáni megállás hibának számít a "
                "kisjátékban), kereszt- és beúszás-minták "
                "sorozatban, és 6 a 6 elleni játék 'mozgás-szabállyal' "
                "— aki 3 mp-ig egy helyben áll, labdát veszt")
    except Exception:
        pass

    # 88) Fal-rés: ha a rendezett falunk réseket hagy, a betörés és a
    # beúszó beálló ellenünk terv — a zárás-távolság a téma.
    try:
        from .defense import (WALL_GAP_M, WALL_GAP_MIN_FRAMES,
                              WALL_GAP_SHARE_PCT, wall_gaps)
        wg88 = wall_gaps(match, config)
        for side in ("home", "away"):
            rec88 = wg88[side]
            if rec88["share_pct"] is None \
                    or rec88["frames"] < WALL_GAP_MIN_FRAMES \
                    or rec88["share_pct"] < WALL_GAP_SHARE_PCT:
                continue
            add(side, "védekezés", "Zárás-távolság a falban",
                f"a falunk réses: a rendezett védekezésünk kockáinak "
                f"{rec88['share_pct']:.0f}%-ában {WALL_GAP_M:.1f} m-nél "
                f"nagyobb rés volt a szomszéd védők között (átlagos "
                f"legnagyobb rés {rec88['avg_gap_m']:.1f} m) — a "
                "betörő és a beúszó beálló ezt bünteti",
                "zárás-távolság: fal-mozgás labda-oldalra karnyújtás-"
                "ellenőrzéssel (a szomszédok érjenek össze kilépésnél), "
                "kereszt elleni átadás-átvétel hangos kommunikációval, "
                "és 2-2 elleni rés-zárás játék a 6-oson")
    except Exception:
        pass

    # 87) Gólcsend-anatómia: a néma csend szervezés-gond (lövésig sem
    # jutunk), a kihagyós csend befejezés-gond — más-más edzés-téma.
    try:
        from .momentum import (DROUGHT_ANATOMY_MIN_S,
                               DROUGHT_SHOOTING_PER_MIN,
                               DROUGHT_SILENT_PER_MIN, drought_anatomy)
        da87 = drought_anatomy(match, config)
        for side in ("home", "away"):
            rec87 = da87[side]
            if rec87["verdict"] is None \
                    or rec87["drought_s"] < DROUGHT_ANATOMY_MIN_S:
                continue
            _da87_min = rec87["drought_s"] / 60.0
            if rec87["verdict"] == "néma":
                add(side, "támadás", "Gólcsend-törés (szervezés)",
                    f"a leghosszabb gólcsendünk ({_da87_min:.0f} perc) "
                    f"néma volt: {rec87['shots']} lövésig jutottunk — "
                    "ilyenkor a támadás-szervezésünk áll le",
                    "csend-törő minták: két begyakorolt 'vész-figura' "
                    "(egyszerű, biztos lövést hozó lefutás), amit "
                    "gólcsendben automatikusan elővesz a csapat, plusz "
                    "időkérés-terv: mikor kérjen időt az edző a csend "
                    "törésére")
            else:
                add(side, "támadás", "Gólcsend-törés (befejezés)",
                    f"a leghosszabb gólcsendünk ({_da87_min:.0f} perc) "
                    f"kihagyós volt: {rec87['shots']} lövés is volt "
                    "benne, csak nem ment be — a befejezés a gond",
                    "befejezés nyomás alatt: fáradt állapotban (sorozat "
                    "után) lövés-döntés gyakorlás — sarok-váltás, ha a "
                    "kapus belejött, és ziccer-rutin, hogy a csendben "
                    "se kapkodjunk")
    except Exception:
        pass

    # 86) Engedett-oldal: ha a falunk egyik oldala átjárható, az
    # ellenfél oda szervez — az oldal-védő és a segítő-csúszás a téma.
    try:
        from .defense import (CONCEDED_SIDE_MIN_SHOTS, CONCEDED_SIDE_PCT,
                              conceded_side_bias)
        cs86 = conceded_side_bias(match, config)
        for side in ("home", "away"):
            rec86 = cs86[side]
            if rec86["weak_side"] is None \
                    or rec86["left"] + rec86["right"] \
                    < CONCEDED_SIDE_MIN_SHOTS \
                    or rec86["weak_pct"] < CONCEDED_SIDE_PCT:
                continue
            add(side, "védekezés", "Fal-oldal erősítés",
                f"a falunk {rec86['weak_side']} oldala átjárható: a "
                f"kapott szélső-sávos lövések "
                f"{rec86['weak_pct']:.0f}%-a arról jön — az ellenfél "
                "oda szervezi a befejezést",
                "fal-oldal erősítés: a gyenge oldali 2-es/3-as védő "
                "zárás-technikája (kilépés-visszazárás párban), a "
                "segítő-csúszás időzítése arról az oldalról, és "
                "oldal-specifikus 2-2 elleni védekezés-sorozatok")
    except Exception:
        pass

    # 85) Eladás-büntetés: ha az eladásaink gyors gólba kerülnek, a
    # váltás-sprint hiányzik — az eladás utáni visszarendeződés a téma.
    try:
        from .defense import (TO_PUNISH_HIGH_PCT, TO_PUNISH_MIN,
                              turnover_punishment)
        tp85 = turnover_punishment(match, config)
        for side in ("home", "away"):
            rec85 = tp85[side]
            if rec85["rate_pct"] is None \
                    or rec85["turnovers"] < TO_PUNISH_MIN \
                    or rec85["rate_pct"] < TO_PUNISH_HIGH_PCT:
                continue
            add(side, "védekezés", "Váltás-sprint eladás után",
                f"az eladásaink drágák: {rec85['turnovers']} eladásból "
                f"{rec85['punished']} után fél percen belül gólt "
                f"kaptunk ({rec85['rate_pct']:.0f}%) — eladás után nem "
                "érünk vissza",
                "váltás-sprint: eladás-jelre azonnali hátrasprint "
                "kisjátékban (az eladó köteles a labdásig visszazárni), "
                "a legközelebbi ember késleltet, a többiek a kapu felé "
                "zárnak — a kontra-gól ellenük kezdődő edzésjáték")
    except Exception:
        pass

    # 84) Kapus-indítás hossza: ha a kapusunk egysíkúan indít, az
    # ellenfél ráállhat — az indítás-variancia a téma.
    try:
        from .goalkeeper import gk_outlet_length
        go84 = gk_outlet_length(match, config)
        for side in ("home", "away"):
            rec84 = go84[side]
            if rec84["style"] is None:
                continue
            _go_desc = ("szinte csak hosszút indít"
                        if rec84["style"] == "hosszú"
                        else "mindent rövidre hoz ki")
            add(side, "kapus", "Indítás-variancia",
                f"a kapusunk {_go_desc} (a kapus-passzai "
                f"{rec84['long_pct']:.0f}%-a 15 m feletti, "
                f"{rec84['long']}/{rec84['outlets']}) — az ellenfél "
                "ráállhat az egysíkú kihozatalunkra",
                "indítás-variancia: a kapus mindkét opciót gyakorolja "
                "(hosszú indítás a kiugró szélsőnek + rövid kihozatal "
                "nyomás alatt), és a padról jelzett indítás-váltás, "
                "hogy az ellenfél letámadása ne tudjon ráállni")
    except Exception:
        pass

    # 83) Területi-fölény-esés: ha a 2. félidőre hátracsúszik a
    # játékunk, fáradtan nem tartjuk elöl a labdát — a téma a
    # labdakihozatal és a magas birtoklás fáradtan.
    try:
        from .tactics import TILT_FADE_DROP_PP, tilt_fade
        tf83 = tilt_fade(match, config)
        for side in ("home", "away"):
            rec83 = tf83[side]
            if rec83["drop_pp"] is None \
                    or rec83["drop_pp"] < TILT_FADE_DROP_PP:
                continue
            _fh83 = 100.0 * rec83["fh_opp"] / rec83["fh_frames"]
            _sh83 = 100.0 * rec83["sh_opp"] / rec83["sh_frames"]
            add(side, "támadás", "Területi fölény fáradtan",
                f"a 2. félidőre hátracsúszik a játékunk (területi "
                f"fölény {_fh83:.0f}% → {_sh83:.0f}%) — fáradtan nem "
                "tartjuk az ellenfél térfelén a labdát",
                "magas birtoklás fáradtan: kör-edzés utáni (magas "
                "pulzusú) területjáték az ellenfél térfelén, "
                "kihozatal-minták a 2. félidei presszre, és a hajrá "
                "tudatos lassítása — a labda fusson, ne a játékos")
    except Exception:
        pass

    # 82) Asszist-függés: ha minden gólunk egyéni villanás, a
    # kulcsember kettőzésével levehetők rólunk — a kiadás a téma.
    try:
        from .attack_types import (ASSIST_DEP_LOW_PCT,
                                   ASSIST_DEP_MIN_GOALS,
                                   assist_reliance)
        ad82 = assist_reliance(match, config)
        for side in ("home", "away"):
            rec82 = ad82[side]
            if rec82["assisted_pct"] is None \
                    or rec82["goals"] < ASSIST_DEP_MIN_GOALS \
                    or rec82["assisted_pct"] > ASSIST_DEP_LOW_PCT:
                continue
            add(side, "támadás", "Előkészített befejezés",
                f"a góljaink zöme egyéni megoldás (csak "
                f"{rec82['assisted']}/{rec82['goals']} gólpasszos) — "
                "a kulcsemberünk kettőzésével levehetők vagyunk",
                "előkészített befejezés: kiadás-figurák gyakorlása "
                "(betörés-kiadás a beállónak, szélső-beadás), a "
                "kettőzött labdás KÖTELEZŐ továbbadása, és a gólpassz "
                "külön dicsérete a kisjátékokban (a gólpasszos gól "
                "két pontot ér)")
    except Exception:
        pass

    # 81) Lepattanó-fal: ha a lövések után nem zárunk, az ellenfél
    # második hulláma jár — a box-out és a zárás a téma.
    try:
        from .defense import (SC_ALLOW_HIGH_PCT, SC_ALLOW_MIN,
                              second_chance_allowed)
        sca81 = second_chance_allowed(match, config)
        for side in ("home", "away"):
            rec81 = sca81[side]
            if rec81["allowed_pct"] is None \
                    or rec81["opp_misses"] < SC_ALLOW_MIN \
                    or rec81["allowed_pct"] < SC_ALLOW_HIGH_PCT:
                continue
            add(side, "védekezés", "Lepattanó-zárás",
                f"a lövések után nem zárunk: az ellenfél a kimaradt "
                f"lövései {rec81['allowed_pct']:.0f}%-ánál újra lőtt "
                f"({rec81['allowed']}/{rec81['opp_misses']}) — a jól "
                "védett első hullám munkája vész kárba",
                "lepattanó-zárás: box-out gyakorlat minden lövés-záró "
                "sorban (a belső hármas kötelezően testet fordít), a "
                "szélsők belépése a rövid lepattanóra, és a kapus "
                "hangos irányítása, kié a kipattanó")
    except Exception:
        pass

    # 80) Pressz-tűrés: ha testközeli védőnél megugrik az eladásunk,
    # az agresszív fal ellenünk termel — a nyomás alatti passz a téma.
    try:
        from .decisions import (PRESS_TO_RISE_PP,
                                pass_security_under_pressure)
        ps80 = pass_security_under_pressure(match, config)
        for side in ("home", "away"):
            rec80 = ps80[side]
            if rec80["rise_pp"] is None \
                    or rec80["rise_pp"] < PRESS_TO_RISE_PP:
                continue
            add(side, "támadás", "Nyomás alatti passz",
                f"testközeli védőnél az eladás-arányunk "
                f"{rec80['press_to_pct']:.0f}%-ra ugrik (szabadon "
                f"{rec80['free_to_pct']:.0f}%) — az agresszív fal "
                "ellenünk termel",
                "nyomás alatti passz: szűk területes labdatartás "
                "(4-4 rácsban, testközeli védővel), passz előtti "
                "váll-csel és lépés-előny begyakorlása, plusz a "
                "labdás játékos melletti KÖTELEZŐ rövid passz-opció "
                "(felkínálkozás szabályként)")
    except Exception:
        pass

    # 79) Eladás-időzítés: ha a birtoklás elején adjuk el a labdát, a
    # letámadás ellenünk termel — a kihozatal nyomás alatt a téma.
    try:
        from .defense import (TO_EARLY_S, TO_EARLY_SHARE, TO_TIMING_MIN,
                              turnover_timing)
        tt79 = turnover_timing(match, config)
        for side in ("home", "away"):
            rec79 = tt79[side]
            if rec79["early_pct"] is None \
                    or rec79["timed"] < TO_TIMING_MIN \
                    or rec79["early_pct"] < 100.0 * TO_EARLY_SHARE:
                continue
            add(side, "támadás", "Kihozatal nyomás alatt",
                f"az eladásaink {rec79['early_pct']:.0f}%-a a birtoklás "
                f"első {TO_EARLY_S:.0f} másodpercében jön "
                f"({rec79['early']}/{rec79['timed']}) — a letámadás "
                "ellenünk azonnal termel",
                "kihozatal nyomás alatt: 3-2 elleni kihozatal-gyakorlat "
                "letámadó védőkkel, kötelező biztonsági passz-opció "
                "(visszajátszás a kapusnak), és a szélső-nyitás mint "
                "első kijátszási irány begyakorlása")
    except Exception:
        pass

    # 78) Kapus-gyengeoldal: ha egy oldalra kapjuk a gólokat, az
    # ellenfél lövő-terve kész — a kapus oldal-technikája a téma.
    try:
        from .goalkeeper import gk_weak_side
        gw78 = gk_weak_side(match, config)
        for side in ("home", "away"):
            rec78 = gw78[side]
            if rec78["weak_side"] is None:
                continue
            add(side, "kapus", "Kapus-oldaltechnika",
                f"a kapunk a(z) {rec78['weak_side']} oldalán átjárható "
                f"(oda ment a bekapott gólok "
                f"{100.0 * rec78['share']:.0f}%-a, "
                f"{rec78[rec78['weak_side']]}/{rec78['goals']}) — az "
                "ellenfél lövő-terve kész recept ellenünk",
                "kapus-oldaltechnika: célzott sorozatok a gyenge "
                "oldalra (elhelyezett lövések jelzett sarokra), "
                "beállás-korrekció videóról, és vetődés-technika a "
                "gyenge oldali alsó/felső sarokra")
    except Exception:
        pass

    # 77) Lövő-koncentráció: ha a lövés-terhelésünk egy emberre épül,
    # az ellenfél kettőzéssel lefejezheti — a lövés-elosztás a téma.
    try:
        from .xg import shot_concentration
        sc77 = shot_concentration(match, config)
        for side in ("home", "away"):
            rec77 = sc77[side]
            if not rec77["concentrated"]:
                continue
            add(side, "támadás", "Lövés-elosztás",
                f"a lövés-terhelésünk egy emberre épül (a fő lövő adja "
                f"a lövések {100.0 * rec77['share']:.0f}%-át, "
                f"{rec77['top_shots']}/{rec77['shots']}) — kettőzéssel "
                "lefejezhető a támadásunk",
                "lövés-elosztás: a másod- és harmad-lövő befejezései "
                "edzésen (figura-variánsok, ahol a fő lövő csali és a "
                "kettőzésből kimaradó társ zár), plusz a fő lövőnek "
                "kettőzés elleni átadó-döntések")
    except Exception:
        pass

    # 76) Ritmus-egyhangúság: ha belső órán játszunk, az ellenfél
    # ráállhat — a tudatos ritmus-váltás a téma.
    try:
        from .attack_types import (RHYTHM_CV_LOW, RHYTHM_MIN_ATTACKS,
                                   attack_rhythm)
        ar76 = attack_rhythm(match, config)
        for side in ("home", "away"):
            rec76 = ar76[side]
            if rec76["cv"] is None \
                    or rec76["n"] < RHYTHM_MIN_ATTACKS + 2 \
                    or rec76["cv"] > RHYTHM_CV_LOW:
                continue
            add(side, "támadás", "Ritmus-váltás",
                f"belső órán támadunk (átlag {rec76['avg_s']:.0f} mp, "
                f"±{rec76['sd_s']:.0f}) — az ellenfél ráállhat az "
                "óránkra",
                "ritmus-váltás: kevert tempójú támadás-sorozatok "
                "edzésen (gyors első hullám / hosszú kivárás felváltva, "
                "a padról jelezve), és a figurák indítás-idejének "
                "tudatos variálása, hogy a lövés-perc ne legyen "
                "kiszámítható")
    except Exception:
        pass

    # 75) Oldal-részrehajlás: ha a támadásunk fél-oldalas, ellenünk
    # eltolt fallal védekeznek — az oldal-egyensúly a téma.
    try:
        from .attack_types import attack_side_bias
        sb75 = attack_side_bias(match, config)
        for side in ("home", "away"):
            rec75 = sb75[side]
            if rec75["bias_side"] is None:
                continue
            add(side, "támadás", "Oldal-egyensúly",
                f"a támadásunk fél-oldalas: a szélső-sávos lövéseink "
                f"{rec75['bias_pct']:.0f}%-a a {rec75['bias_side']} "
                "oldalról jön — az ellenfél eltolt fallal várhat",
                "oldal-egyensúly: a gyenge oldal tudatos terhelése "
                "(minden harmadik figura oda fusson ki), gyors "
                "oldalváltó passzok begyakorlása a fal átmozgatására, "
                "és a gyenge oldali átlövő/szélső önbizalom-helyzetei "
                "edzésen")
    except Exception:
        pass

    # 74) Célzás-pontosság: ha a lövéseink fele mellé megy, a lövés
    # ára nálunk dupla — technikai célzás-edzés a téma.
    try:
        from .xg import (ACCURACY_LOW_PCT, ACCURACY_MIN_SHOTS,
                         shot_accuracy)
        sa74 = shot_accuracy(match, config)
        for side in ("home", "away"):
            rec74 = sa74[side]
            if rec74["pct"] is None \
                    or rec74["attempts"] < ACCURACY_MIN_SHOTS \
                    or rec74["pct"] > ACCURACY_LOW_PCT:
                continue
            add(side, "támadás", "Célzás",
                f"a lövéseinknek csak {rec74['pct']:.0f}%-a tartott "
                f"kapura ({rec74['attempts']} kísérletből "
                f"{rec74['on_target']}) — a mellé lövés ajándék az "
                "ellenfélnek",
                "célzás-edzés: sarok-célzás sorozatban (alsó-felső "
                "sarkok jelölve), lövés-válogatás — rossz szögből nem "
                "lövünk, hanem visszajátszunk —, és fáradt célzás a "
                "kondi-blokk végén, mert a mellé lövések ott sűrűsödnek")
    except Exception:
        pass

    # 73) Befejezés-esés: ha a gólra váltásunk a 2. félidőre esik, a
    # fáradt befejezés a téma.
    try:
        from .xg import FINISH_FADE_DROP_PP, finish_fade
        ff73 = finish_fade(match, config)
        for side in ("home", "away"):
            rec73 = ff73[side]
            if rec73["drop_pp"] is None \
                    or rec73["drop_pp"] < FINISH_FADE_DROP_PP:
                continue
            _f73_fh = 100.0 * rec73["fh_goals"] / rec73["fh_shots"]
            _f73_sh = 100.0 * rec73["sh_goals"] / rec73["sh_shots"]
            add(side, "támadás", "Fáradt befejezés",
                f"a gólra váltásunk a 2. félidőre esik ({_f73_fh:.0f}% "
                f"→ {_f73_sh:.0f}%) — fáradtan már nem ül a lövés",
                "fáradt befejezés: lövés-sorozatok az edzés VÉGÉN "
                "(kör-edzés után célra), ziccer-befejezés pulzus-plafon "
                "felett, és a hajrá-szabály rögzítése: az utolsó 10 "
                "percben csak kidolgozott helyzetre lövünk")
    except Exception:
        pass

    # 72) Bravúr utáni lendület: ha a kapusbravúrjaink elhalnak, a
    # védés utáni azonnali indítás a téma.
    try:
        from .xg import BIG_SAVE_SPARK_MIN, big_save_momentum
        bs72 = big_save_momentum(match, config)
        for side in ("home", "away"):
            rec72 = bs72[side]
            if rec72["saves"] < BIG_SAVE_SPARK_MIN + 1 \
                    or rec72["sparked"] > 0:
                continue
            add(side, "támadás", "Bravúr utáni indítás",
                f"{rec72['saves']} nagy védésünkből egyet sem váltottunk "
                "gyors gólra — a bravúr nálunk elhal",
                "védés utáni indítás: a kapus első passza előre "
                "(kidobás-gyakorlás célkapukra), a szélsők azonnali "
                "indulása nagy védésnél, és 5 mp-es szabály — a bravúr "
                "utáni első támadás fejben is támadás legyen, ne "
                "leforgás")
    except Exception:
        pass

    # 71) Sorozat-törés: ha az elszenvedett sorozatok rendre elfutnak,
    # a sorozat-törés protokollja a téma.
    try:
        from .momentum import (RUN_CONTAIN_LONG, RUN_CONTAIN_MIN,
                               run_containment)
        rc71 = run_containment(match, config)
        for side in ("home", "away"):
            rec71 = rc71[side]
            if rec71["avg_len"] is None \
                    or rec71["suffered"] < RUN_CONTAIN_MIN \
                    or rec71["avg_len"] < RUN_CONTAIN_LONG:
                continue
            add(side, "taktika", "Sorozat-törés protokoll",
                f"az ellenfél sorozatai elfutottak ({rec71['suffered']} "
                f"sorozat, átlag {rec71['avg_len']:.1f} gól) — a 3-0-nál "
                "nem tudtunk megállni",
                "sorozat-törés protokoll: 0-2-nél automatikus jelzés a "
                "padról (ki kéri az időt és mikor), az időkérés utáni "
                "első támadásra kész figura, tempó-kivétel (hosszabb "
                "támadás), és védekezés-váltás begyakorlása sorozat "
                "közben")
    except Exception:
        pass

    # 70) Holtpont-mérleg: ha az egál-pillanatokat rendre elengedjük,
    # a nyomás alatti befejezés a téma.
    try:
        from .momentum import PARITY_MIN_TIES, parity_breaks
        pb70 = parity_breaks(match, config)
        for side in ("home", "away"):
            rec70 = pb70[side]
            if rec70["rate_pct"] is None \
                    or rec70["ties"] < PARITY_MIN_TIES + 1 \
                    or rec70["rate_pct"] > 35.0:
                continue
            add(side, "mentális", "Holtpont-játék",
                f"{rec70['ties']} döntetlen-állásból csak "
                f"{rec70['won']}-szor léptünk el — az egálnál mi "
                "remegünk",
                "holtpont-játék: edzésmeccs egál-állásról (a következő "
                "gól dönt, sorozatban), büntetős-jellegű nyomás-"
                "gyakorlatok fáradtan, és az egál utáni első támadásra "
                "kijelölt, begyakorolt figura")
    except Exception:
        pass

    # 69) Félidei hátrányból fordítás: ha hátrányból nem tudtunk
    # visszajönni, a szünet utáni fordítás-protokoll a téma.
    try:
        from .momentum import halftime_comeback
        htc69 = halftime_comeback(match, config)
        for side in ("home", "away"):
            rec69 = htc69[side]
            if rec69["verdict"] != "elbukta":
                continue
            add(side, "taktika", "Szünet utáni fordítás-protokoll",
                f"félidei {-rec69['ht_margin']} gólos hátrányból nem "
                "jöttünk vissza — a hátrányban játék a gyengénk",
                "fordítás-protokoll: edzésmeccs indítása mínusz 2-ről "
                "(15 perc a fordításra), a szünet utáni első három "
                "támadásra kész figura, és letámadós/5-1-es váltás "
                "begyakorlása hátrányban")
    except Exception:
        pass

    # 68) Tempó-esés: ha a 2. félidőre érdemben esik a támadás/perc,
    # elfogy a láb — a futó-állóképesség és a rotáció a téma.
    try:
        from .attack_types import PACE_FADE_DROP_PER_MIN, team_pace_fade
        tpf68 = team_pace_fade(match, config)
        for side in ("home", "away"):
            rec68 = tpf68[side]
            if rec68["drop_per_min"] is None \
                    or rec68["drop_per_min"] < PACE_FADE_DROP_PER_MIN:
                continue
            _t68_fh = rec68["fh_attacks"] / rec68["fh_min"]
            _t68_sh = rec68["sh_attacks"] / rec68["sh_min"]
            add(side, "kondíció", "Tempó-állóképesség",
                f"a támadás-ütemünk a 2. félidőre esik ({_t68_fh:.1f} → "
                f"{_t68_sh:.1f} támadás/perc) — elfogy a láb",
                "tempó-állóképesség: intervallum-futás kézilabda-"
                "specifikusan (pálya-hossz sprintek gyors középkezdésből), "
                "6 a 6 elleni hosszú szakaszok a tempó tartásával, és a "
                "rotáció tudatos szélesítése — a szünet utáni első 10 "
                "percre friss láb menjen")
    except Exception:
        pass

    # 67) Kihagyott ziccer ára: ha a kihagyásainkat rendre azonnal
    # büntetik, a kihagyás utáni visszarendeződés a téma.
    try:
        from .xg import miss_punishment
        mp67 = miss_punishment(match, config)
        for side in ("home", "away"):
            rec67 = mp67[side]
            if rec67["rate_pct"] is None or rec67["rate_pct"] < 40.0 \
                    or rec67["punished"] < 2:
                continue
            add(side, "védekezés", "Kihagyás utáni fejtartás",
                f"{rec67['misses']} kihagyott ziccerünkből "
                f"{rec67['punished']} után fél percen belül gólt kaptunk "
                "— a kihagyás után áll a csapat",
                "kihagyás utáni visszarendeződés: helyzet-kihagyás után "
                "AZONNALI védekezés-gyakorlat (a lövő is visszazár), a "
                "'következő labda' szabály hangosítása (a hibán nem "
                "rágódunk), és kontra-elhárítás kihagyott lövés utáni "
                "kidobásból")
    except Exception:
        pass

    # 66) Kapuscsere-hatás: ha a csere sem segített (mindkét kapus
    # nehéz napja), a kapus-alapok és a fal-kapus összhang a téma.
    try:
        from .goalkeeper import GK_CHANGE_DELTA_PP, gk_change_effect
        gce66 = gk_change_effect(match, config)
        for side in ("home", "away"):
            rec66 = gce66[side]
            if rec66["delta_pp"] is None \
                    or rec66["delta_pp"] > -GK_CHANGE_DELTA_PP:
                continue
            _p66 = 100.0 * rec66["pre_saves"] / rec66["pre_faced"]
            _q66 = 100.0 * rec66["post_saves"] / rec66["post_faced"]
            add(side, "védekezés", "Kapus-poszt",
                f"a kapuscsere sem segített ({_p66:.0f}% → {_q66:.0f}% "
                "védés a csere után) — mindkét kapusnak nehéz napja volt",
                "kapus-alapok + fal-kapus összhang: alaptechnika-sor "
                "mindkét kapusnak (helyezkedés, sarok-zárás), a fal és a "
                "kapus sáv-felosztásának tisztázása (ki mit vállal), és "
                "a kapott gólok lövés-térképének közös visszanézése")
    except Exception:
        pass

    # 65) Hetes-védés: ha a kapusunk a rá dobott heteseket rendre kapja,
    # a hetes-készülés a kapus-edzés témája.
    try:
        from .rules import seven_meter_defense
        s7d65 = seven_meter_defense(match, config)
        for side in ("home", "away"):
            rec65 = s7d65[side]
            if rec65["faced"] < 2 or rec65["saved"] > 0:
                continue
            add(side, "védekezés", "Hetes-védés",
                f"a kapusunk mind a {rec65['faced']} kapura tartó hetest "
                "kapta — a hetes ellenünk most kész gól",
                "kapus hetes-készülés: a következő ellenfél dobóinak "
                "sarok-statisztikája (felderítő-jelentésből), "
                "hetes-sorozat edzésen fáradt lövőkkel (meccs-szimuláció), "
                "és a kapus késleltetett mozdulat-időzítésének "
                "gyakorlása videó-visszajelzéssel")
    except Exception:
        pass

    # 64) Félidő-zárás: ha a szünet előtti perceket érdemben elvesztettük,
    # az 1. félidő végi koncentráció a téma.
    try:
        from .halftime import first_half_close
        fhc64 = first_half_close(match, config)
        if fhc64 is not None:
            for side in ("home", "away"):
                other = "away" if side == "home" else "home"
                if fhc64[other] - fhc64[side] < 2:
                    continue
                add(side, "taktika", "Félidő-zárás",
                    f"a szünet előtti 5 percet {fhc64[side]}–"
                    f"{fhc64[other]}-ra elvesztettük — a félidő végére "
                    "elfogy a fókusz",
                    "az 1. félidő zárásának begyakorlása: az edzés-meccs "
                    "utolsó 5 perce mindig 'félidő-hajrá' (kihirdetett "
                    "állással), az utolsó támadás mindig kidolgozott "
                    "figurából, és a falban hangos, névre szóló "
                    "vezénylés a fáradó szakaszban")
    except Exception:
        pass

    # 63) Szoros vereség: ha ez a meccs 1-2 gólon úszott el, a
    # hajrá-forgatókönyv a következő edzés témája.
    try:
        from .momentum import close_game_record
        cg63 = close_game_record(match, config)
        for side in ("home", "away"):
            if cg63[side]["verdict"] != "szoros vereség":
                continue
            add(side, "taktika", "Hajrá-forgatókönyv",
                f"a meccs {abs(cg63[side]['margin'])} gólon úszott el — "
                "a szoros hajrát nem mi hoztuk",
                "hajrá-szituációk gyakorlása: utolsó 5 perc -1-ről és "
                "+1-ről (mindkét irány), utolsó-támadás figura időkéréssel "
                "megbeszélve, 7 a 6 elleni játék le- és visszaváltása, és "
                "a hajrá-ötös + a büntetőt dobók előre kijelölve")
    except Exception:
        pass

    # 62) Gól utáni elalvás: ha a góljaink után rendre azonnali választ
    # kapunk, a középkezdés elleni visszarendeződés a téma.
    try:
        from .momentum import post_goal_lapses
        pgl62 = post_goal_lapses(match, config)
        for side in ("home", "away"):
            rec62 = pgl62[side]
            if rec62["rate_pct"] is None or rec62["rate_pct"] < 40.0 \
                    or rec62["quick_replies"] < 2:
                continue
            add(side, "védekezés", "Koncentráció gól után",
                f"a góljaink {rec62['rate_pct']:.0f}%-ára fél percen belül "
                f"jött válasz ({rec62['goals']} gólból "
                f"{rec62['quick_replies']}) — a középkezdés után elalszunk",
                "gól utáni visszarendeződés: gólöröm-szimuláció után "
                "azonnali középkezdés elleni védekezés (6-0-ba érés "
                "időre), a gólszerző NEM eshet ki a visszafutásból, és "
                "kijelölt 'ébresztő' hang a pályán (ki szól, ki irányít)")
    except Exception:
        pass

    # 61) Fegyelem-esés: ha a kiállításaink a 2. félidőre sűrűsödnek,
    # a fáradt védekezés-technika a téma — a hajrában nem szabad
    # emberhátrányba kerülni.
    try:
        from .rules import discipline_fade
        df61 = discipline_fade(match, config)
        for side in ("home", "away"):
            rec61 = df61[side]
            if rec61["verdict"] != "hajrában szabálytalankodnak":
                continue
            add(side, "védekezés", "Fegyelem fáradtan",
                f"a kiállításaink a 2. félidőre sűrűsödtek "
                f"({rec61['fh_susp']} → {rec61['sh_susp']}) — fáradtan "
                "késve érkezünk és szabálytalanul zárunk",
                "védekezés-technika fáradt állapotban: lábmunka-alapú "
                "zárás kör-edzés UTÁN (kéz nélkül, tiszta test-pozícióból), "
                "1-1 védekezés szabálytalanság nélkül pontozva, és a "
                "hajrá-falba a leghiggadtabb védők kijelölése")
    except Exception:
        pass

    # 60) Előny-őrzés: ha ezen a meccsen 3+ gólos vezetés ment el, a
    # vezetés-menedzsment a következő edzés témája.
    try:
        from .momentum import lead_protection
        lp60 = lead_protection(match, config)
        for side in ("home", "away"):
            rec60 = lp60[side]
            if not rec60["blown"]:
                continue
            add(side, "taktika", "Előny-őrzés",
                f"{rec60['max_lead']} gólos vezetés ment el ezen a "
                "meccsen — a megszerzett előnyt nem tudtuk megtartani",
                "vezetés-menedzsment: 10 perces játék 3 gólos előnyről "
                "(a vezető csapat hosszú, türelmes támadásokat játszik, "
                "cél a hibátlan labdajáratás), időkérés-forgatókönyv az "
                "olvadó előnyre, és a hajrá-ötös kijelölése előre")
    except Exception:
        pass

    # 59) Kapus-forma félidőnként: ha a kapusunk a 2. félidőre érdemben
    # esik (15+ százalékpont), a kapus-terhelést és a csere-időzítést kell
    # átgondolni.
    try:
        from .goalkeeper import GK_FADE_DROP_PP, gk_save_fade
        gf59 = gk_save_fade(match, config)
        for side in ("home", "away"):
            rec59 = gf59[side]
            if rec59["drop_pp"] is None \
                    or rec59["drop_pp"] < GK_FADE_DROP_PP:
                continue
            _f59 = 100.0 * rec59["fh_saves"] / rec59["fh_faced"]
            _s59 = 100.0 * rec59["sh_saves"] / rec59["sh_faced"]
            add(side, "védekezés", "Kapus-terhelés",
                f"a kapusunk védés-hatékonysága a 2. félidőre esik "
                f"({_f59:.0f}% → {_s59:.0f}%) — a hajrára elfogy",
                "kapus-terhelés kezelése: tervezett kapuscsere a 2. félidő "
                "elején/közepén (a friss szem is előny), a kapus-bemelegítő "
                "rutin megismétlése a szünetben, és lövő-sorozatos "
                "reakció-gyakorlat fáradt állapotban az edzés végén")
    except Exception:
        pass

    return out
