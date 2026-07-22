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
    """Csapatonként rangsorolt edzés-fókusz lista ({"home": [...], ...})."""
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

    return out
