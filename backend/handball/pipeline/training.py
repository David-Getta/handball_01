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

    return out
