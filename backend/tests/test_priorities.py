"""A teendő-rangsor (priorities.priority_findings) tesztjei."""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                      PlayerPosition, Team)
from handball.pipeline.priorities import PRF_TOP_N, priority_findings


def _meta():
    return MatchMeta(match_id="prf", home_team="H", away_team="A", fps=25.0)


def _two_family_match():
    """Olyan meccs, ami EGYSZERRE vált ki egy ár- és egy állás-jelzést.

    Három 36 mp-es hazai támadás gól nélkül → "elhúzódó támadás ára"
    (ár-család); ugyanezek alatt a hazai kapus 25 m-re a saját
    kapujától → három üres-kapus szakasz döntetlennél → "7a6-állás"
    (állás-család). A szakaszok közti 3 mp-es szabad labda szétvágja
    mindkét szakasz-sorozatot.
    """
    frames = []
    t = 0
    for _ in range(3):
        for _ in range(int(36 * 25)):
            frames.append(Frame(t=t, players=[
                PlayerPosition(track_id=1, team=Team.HOME, x=30.0, y=10.0),
                PlayerPosition(track_id=2, team=Team.HOME, x=25.0, y=10.0,
                               role="kapus"),
            ], ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(int(3 * 25)):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(), frames)


def test_priority_findings_ranks_cost_before_score_state():
    """Az ár-család jelzése a rangsor élére kerül az állás-család elé."""
    prf = priority_findings(_two_family_match())
    h = prf["home"]
    assert h["total"] >= 2, h
    families = [it["family"] for it in h["top"]]
    assert families[0] == "ár", h["top"]
    assert "állás" in families, h["top"]
    # Az ár-jelzés megelőzi az állás-jelzést a listában.
    assert families.index("ár") < families.index("állás")
    labels = [it["label"] for it in h["top"]]
    assert "Elhúzódó támadás ára" in labels
    assert "7a6-állás" in labels
    assert h["families"].get("ár", 0) >= 1
    assert h["families"].get("állás", 0) >= 1
    assert len(h["top"]) <= PRF_TOP_N


def test_priority_findings_silent_without_evidence():
    """Üres meccsen egyetlen réteg sem szólal meg — nem találgatunk."""
    frames = [Frame(t=i, players=[],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0))
              for i in range(200)]
    prf = priority_findings(Match(_meta(), frames))
    for side in ("home", "away"):
        assert prf[side]["top"] == []
        assert prf[side]["total"] == 0
        assert prf[side]["families"] == {}


def test_felkeszules_csalad_a_sor_vegen_all():
    """A poszt-profil jelzések a rangsor VÉGÉRE kerülnek.

    A poszt-profil nem hiba és nem romlás, hanem állandó tulajdonság
    ("a beállójuk hat méterről fejez be") — sürgősség nélkül. Ezért nem
    tolhatja el az árat, az embert vagy a fáradást; viszont ha azok
    hallgatnak (rövid felvétel, kevés esemény), legalább a lista nem
    marad üresen.
    """
    from handball.pipeline.priorities import (PRF_FAMILY_ORDER, _registry)

    assert PRF_FAMILY_ORDER[-1] == "felkészülés", PRF_FAMILY_ORDER
    fams = {f for f, _, _, _ in _registry()}
    assert "felkészülés" in fams, fams
    # Minden nyilvántartott család szerepel a sorrendben — különben a
    # rendezés némán a lista elejére dobná.
    assert fams <= set(PRF_FAMILY_ORDER), fams - set(PRF_FAMILY_ORDER)


def test_a_poszt_lencse_eljut_a_rangsorba():
    """A poszt-lencse lövés-rétegei rangsorba vont rétegek.

    Enélkül az ítéletük ("őt ki kell zárni", "a kapus arra állhat rá")
    csak böngészéssel lenne megtalálható a háromszáz réteg közt.
    """
    from handball.pipeline.priorities import _registry

    names = {fn for _, _, _, fn in _registry()}
    for layer in ("role_shot_distance", "role_shot_power",
                  "role_shot_timing", "role_goal_placement",
                  # A befejező-lencse: kire lépj ki, melyik figurájuk
                  # kire fut ki, és időkérés után kit fogj.
                  "role_pressure_finish", "setplay_finishers",
                  "timeout_finisher", "role_fast_breaks",
                  "role_assist_sources", "shot_choice_quality",
                  "role_steal_sources", "second_chance_roles",
                  "role_block_sources", "seven_six_finisher_roles",
                  "seven_conceder_roles", "suspended_roles",
                  "slow_retreat_roles", "beaten_defender_roles",
                  "screen_setter_roles", "key_post",
                  "outlet_hunter_roles", "pivot_feeder_roles",
                  "iron_man_roles", "risky_passer_roles",
                  "doubling_defender_roles", "kickout_target_roles",
                  "powerplay_shooter_roles", "shorthanded_shooter_roles",
                  "clutch_scorer_roles", "comeback_carrier_roles",
                  "wasteful_shooter_roles", "big_chance_roles",
                  "hold_time_roles", "press_sensitive_roles",
                  "drought_breaker_roles", "fading_scorer_roles",
                  "clutch_turnover_roles", "hot_hand_roles",
                  "restart_taker_roles", "sprint_threat_roles",
                  "soft_pass_roles", "clutch_hog_roles",
                  "assisted_scorer_roles", "opening_scorer_roles",
                  "passive_holder_roles", "fatigue_roles",
                  "doubled_target_roles", "screened_defender_roles",
                  "second_start_roles", "seven_taker_roles",
                  "blocked_shooter_roles", "missed_chance_roles",
                  "advanced_defender_roles", "pivot_guard_roles",
                  "attack_starter_roles", "last_pass_roles",
                  "lead_scorer_roles", "ball_carrier_roles",
                  "backward_pass_roles", "tired_turnover_roles",
                  "tired_shooter_roles", "tired_conceder_roles",
                  "substituted_roles", "sub_in_roles",
                  "costly_turnover_roles", "breakthrough_roles",
                  "fading_defender_roles", "covered_shooter_roles",
                  "targeted_defender_roles", "high_steal_roles",
                  "static_attacker_roles", "screen_pair_roles",
                  "swap_style", "seven_pair_roles",
                  "fast_break_pair_roles", "assist_pair_roles",
                  "doubling_pair_roles", "rebound_pair_roles",
                  "specialist_roles", "powerplay_pair_roles",
                  "response_scorer_roles", "recovery_roles",
                  "lane_switch_roles", "timeout_pair_roles",
                  "press_outlet_roles", "last_holder_roles",
                  "big_chance_feeder_roles", "seven_miss_roles",
                  "big_chance_pair_roles",
                  "powerplay_turnover_roles",
                  "response_turnover_roles",
                  "timeout_turnover_roles",
                  "shorthanded_turnover_roles",
                  "defensive_rebound_roles",
                  "suspension_chain_roles"):
        assert layer in names, f"{layer} nincs a rangsorban"


def _pl_kp(track_id, team, x, y, role=None):
    from handball.models.tracking import PositionSource
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED,
                          confidence=1.0, role=role)


def _kp_match():
    """Három poszt-réteg ugyanarra fut ki: a vendég 21-es (beálló)
    szedi a labdákat, blokkol ÉS mögötte esnek a kapott gólok — a
    kulcs-poszt tehát a beálló. A 23-as (szélső) mindenből egyet kap,
    hogy legyen szórás is."""
    pos = {21: (6.0, 10.0), 23: (6.0, 1.0)}
    frames = []
    t = 0

    def away_cast():
        # Mindkét oldalon jelölt kapus áll a kapuban, hogy a
        # kapus-felismerés ne a mezőnyvédőt jelölje meg.
        return [_pl_kp(21, Team.AWAY, *pos[21]),
                _pl_kp(23, Team.AWAY, *pos[23]),
                _pl_kp(29, Team.AWAY, 39.5, 10.0, role="kapus"),
                _pl_kp(9, Team.HOME, 0.5, 10.0, role="kapus")]

    for _ in range(150):             # vendég-birtoklás: poszt-minta
        frames.append(Frame(t=t, players=[
            _pl_kp(1, Team.HOME, 30.0, 10.0)] + away_cast(),
            ball=Ball(x=6.2, y=10.0, confidence=1.0)))
        t += 1

    # Labdaszerzések: hazai birtoklás → a megadott vendég szerez.
    for tid in [21] * 5 + [23]:
        for _ in range(15):
            frames.append(Frame(t=t, players=[
                _pl_kp(1, Team.HOME, 25.0, 10.0)] + away_cast(),
                ball=Ball(x=25.2, y=10.0, confidence=1.0)))
            t += 1
        sx, sy = pos[tid]
        for _ in range(40):
            frames.append(Frame(t=t, players=[
                _pl_kp(1, Team.HOME, 25.0, 10.0)] + away_cast(),
                ball=Ball(x=sx + 0.2, y=sy, confidence=1.0)))
            t += 1

    # Blokkok: a hazai lövés a megadott vendég védőn fordul vissza.
    for tid in [21] * 3 + [23]:
        other = 23 if tid == 21 else 21
        for x in (29.0, 30.2, 31.4, 32.4, 31.0, 29.5, 28.0):
            frames.append(Frame(t=t, players=[
                _pl_kp(1, Team.HOME, 28.0, 10.0),
                _pl_kp(tid, Team.AWAY, 32.5, 10.0),
                _pl_kp(other, Team.AWAY, 20.0, 5.0),
                _pl_kp(29, Team.AWAY, 39.5, 10.0, role="kapus"),
                _pl_kp(9, Team.HOME, 0.5, 10.0, role="kapus")],
                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(15):
            frames.append(Frame(t=t, players=[
                _pl_kp(1, Team.HOME, 28.0, 10.0)] ,
                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1

    # Kapott gólok: a lövő mellett a megadott vendég védő áll.
    for tid in [21] * 3 + [23]:
        other = 23 if tid == 21 else 21

        def goal_cast():
            return [_pl_kp(1, Team.HOME, 33.0, 10.0),
                    _pl_kp(tid, Team.AWAY, 34.0, 10.0),
                    _pl_kp(other, Team.AWAY, 22.0, 16.0),
                    _pl_kp(9, Team.HOME, 0.5, 10.0, role="kapus")]

        for _ in range(10):
            frames.append(Frame(t=t, players=goal_cast(),
                                ball=Ball(x=33.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for i in range(8):
            frames.append(Frame(t=t, players=goal_cast(),
                                ball=Ball(x=min(33.0 + (i + 1), 40.5),
                                          y=10.0, confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(), frames)


def test_key_post_names_the_convergent_post():
    """Ha három poszt-réteg is ugyanarra a posztra fut ki, az a
    kulcs-poszt — a meccsterv első lapja."""
    from handball.pipeline.priorities import KP_MIN_LAYERS, key_post

    rec = key_post(_kp_match())["away"]
    assert rec["posts"].get("beálló", 0) >= KP_MIN_LAYERS, rec
    assert rec["top"] == "beálló", rec
    assert rec["verdict"] and "meccsterv első lapja" in rec["verdict"], rec


def test_key_post_silent_without_convergence():
    """Kevés vagy széttartó poszt-ítéletből nincs kulcs-poszt."""
    from handball.pipeline.priorities import key_post

    rec = key_post(_two_family_match())["away"]
    assert rec["top"] is None and rec["verdict"] is None, rec


def test_kulcs_poszt_lefedi_a_poszt_iteletes_retegeket():
    """Őr-teszt: minden pipeline-függvény, amely "main_role" ítéletet
    ad (poszt-lencse réteg), szerepeljen a KP_LAYERS listában — így az
    új poszt-réteg nem maradhat ki a kulcs-poszt összegzésből."""
    import pathlib
    import re

    from handball.pipeline.priorities import KP_LAYERS, KP_PAIRS

    # A poszt-lencse a KP_LAYERS-be, a POSZTPÁR-lencse a KP_PAIRS-be
    # tartozik (kulcs-poszt vs. kulcs-páros) — mindkettő lefedésnek
    # számít, de a két lista szándékosan külön áll.
    covered = ({fn for _, _, fn in KP_LAYERS}
               | {fn for _, _, fn in KP_PAIRS})
    # A hetes-oldal (irány-ítélet) és a poszt-nyomás kivétel: nem
    # posztot neveznek meg, vagy más a szerkezetük.
    pipeline_dir = pathlib.Path("handball/pipeline")
    missing = []
    for mod in pipeline_dir.glob("*.py"):
        if mod.name in ("scouting.py", "report_html.py",
                        "priorities.py"):
            continue
        src = mod.read_text(encoding="utf-8")
        for m in re.finditer(r"\ndef (\w+)\(", src):
            fn = m.group(1)
            end = src.find("\ndef ", m.end())
            body = src[m.start():end if end > 0 else len(src)]
            if '"main_role"' in body and fn not in covered:
                missing.append(f"{mod.stem}.{fn}")
    assert not missing, ("hiányzik a KP_LAYERS/KP_PAIRS listákból: "
                         + ", ".join(sorted(missing)))


def test_minden_kp_reteg_a_riport_lencsekben_is():
    """ŐR: minden Kulcs-poszt bizonyíték-réteg jelenjen meg a
    HTML-riport Befejező- vagy Védő-lencse táblájában is.

    A lencse-sorokat kézzel soroljuk fel a report_html-ben — ez a
    teszt a KP_LAYERS névsorával veti össze őket, hogy egy új réteg
    lencse-sora ne maradhasson ki csendben.
    """
    import re

    from handball.pipeline.priorities import KP_LAYERS

    src = open("handball/pipeline/report_html.py",
               encoding="utf-8").read()
    i = src.index("fin_rows = _lens_rows")
    k = src.index("if def_rows:")
    lens_names = set(re.findall(r'\("([^"]+)",\s*[a-z_0-9]+\),?',
                                src[i:k]))
    kp_names = {name for (name, _m, _f) in KP_LAYERS}
    hianyzik = sorted(kp_names - lens_names)
    assert not hianyzik, (
        f"KP-rétegek lencse-sor nélkül: {hianyzik}")


def test_kulcs_paros_osszegzi_a_paros_retegeket():
    """A kulcs-páros akkor szólal meg, ha több páros-réteg ugyanazt a
    kettőst nevezi meg — és a KP_PAIRS a páros-rétegeket a
    kulcs-poszt listájától külön tartja."""
    from handball.pipeline.priorities import (KP_LAYERS, KP_PAIRS,
                                              key_pair)

    # A két lista nem fed át: a poszt- és a páros-lencse külön él.
    assert not ({fn for _, _, fn in KP_PAIRS}
                & {fn for _, _, fn in KP_LAYERS})
    assert len(KP_PAIRS) >= 5

    rec = key_pair(_kp_match())
    for side in ("home", "away"):
        o = rec[side]
        assert set(o) == {"layers", "pairs", "named", "top", "verdict"}
        # Minden megnevezett páros egy-egy páros-rétegtől jön.
        cimkek = {label for label, _m, _f in KP_PAIRS}
        assert all(n["layer"] in cimkek for n in o["named"]), o["named"]


def test_kulcs_ember_szerkezete_es_nevsora():
    """A kulcs-ember az EMBERT nevező rétegekből épül, és a névsora
    nem fed át a poszt- és a páros-lencse listáival."""
    from handball.pipeline.priorities import (KP_LAYERS, KP_PAIRS,
                                              KPL_LAYERS, key_player)

    nevek = {fn for _, _, fn in KPL_LAYERS}
    assert not (nevek & {fn for _, _, fn in KP_LAYERS})
    assert not (nevek & {fn for _, _, fn in KP_PAIRS})
    assert len(KPL_LAYERS) >= 20

    rec = key_player(_kp_match())
    for side in ("home", "away"):
        o = rec[side]
        assert set(o) == {"layers", "players", "named", "top",
                          "verdict"}
        cimkek = {label for label, _m, _f in KPL_LAYERS}
        assert all(n["layer"] in cimkek for n in o["named"]), o["named"]


def _kpl_stub(monkeypatch, tops):
    """`tops` = rétegenként a hazai oldal "top"-ja (vagy None). A
    stub-modult a pipeline-csomagba tesszük, és a KPL_LAYERS erre
    mutat — így a küszöb és a holtverseny szabálya önmagában
    ellenőrizhető."""
    import sys
    import types

    from handball.pipeline import priorities

    mod = types.ModuleType("handball.pipeline.kpl_stub")
    nevek = []
    for i, top in enumerate(tops):
        fn_name = f"stub_{i}"
        setattr(mod, fn_name,
                (lambda t: (lambda match, config=None: {
                    "home": {"top": t}, "away": {"top": None}}))(top))
        nevek.append((f"Stub {i}", "kpl_stub", fn_name))
    monkeypatch.setitem(sys.modules, "handball.pipeline.kpl_stub", mod)
    monkeypatch.setattr(priorities, "KPL_LAYERS", tuple(nevek))
    return priorities


def test_kulcs_ember_negy_egyezo_retegtol_szolal_meg(monkeypatch):
    """Négy réteg ugyanarra az emberre → kulcs-ember; háromnál még
    hallgat."""
    egy = {"player_id": 7, "jersey": 7}
    mas = {"player_id": 9, "jersey": 9}

    prio = _kpl_stub(monkeypatch, [egy, egy, egy, egy, mas])
    rec = prio.key_player(_kp_match())["home"]
    assert rec["layers"] == 5 and rec["players"]["7"] == 4, rec
    assert rec["top"] == "7", rec
    assert rec["verdict"] and "kulcs-emberük" in rec["verdict"], rec

    prio = _kpl_stub(monkeypatch, [egy, egy, egy, mas])
    rec = prio.key_player(_kp_match())["home"]
    assert rec["top"] is None and rec["verdict"] is None, rec


def test_kulcs_ember_holtversenynel_hallgat(monkeypatch):
    """Ha két ember ugyanannyi réteget kap, nincs kulcs-ember."""
    egy = {"player_id": 7, "jersey": 7}
    mas = {"player_id": 9, "jersey": 9}

    prio = _kpl_stub(monkeypatch, [egy] * 4 + [mas] * 4)
    rec = prio.key_player(_kp_match())["home"]
    assert rec["top"] is None and rec["verdict"] is None, rec


def test_kulcs_ember_lefedi_az_ember_iteletes_retegeket():
    """ŐR: minden pipeline-függvény, amely EMBERT nevez meg (a "top"
    mezőjében player_id áll), szerepeljen a KPL_LAYERS listában.

    Enélkül egy új ember-réteg csendben kimaradna a Kulcs-ember
    összegzéséből: a szintézis akkor is "négy réteg mutat rá"-t
    mondana, ha valójában öt lenne — a bizonyíték-lánc pedig
    hiányos maradna.
    """
    import pathlib
    import re

    from handball.pipeline.priorities import KPL_LAYERS

    covered = {fn for _, _, fn in KPL_LAYERS}
    # Kivételek. A poszt-lencse rétegek a top-jukban POSZTOT adnak
    # (a player_id csak a belső számolásban szerepel), a páros-lencse
    # kettőst, a privát segédek pedig nem rétegek.
    kivetel = {"screen_pairs",          # PÁROS-lencse (két embert nevez)
               "blocked_by_role",       # poszt-lencse
               "outlet_target_roles",   # poszt-lencse
               "seven_earner_roles",    # poszt-lencse
               "susp_earner_roles"}     # poszt-lencse
    pipeline_dir = pathlib.Path("handball/pipeline")
    missing = []
    for mod in pipeline_dir.glob("*.py"):
        if mod.name in ("priorities.py", "scouting.py",
                        "report_html.py"):
            continue
        src = mod.read_text(encoding="utf-8")
        for m in re.finditer(r"\ndef (\w+)\(", src):
            fn = m.group(1)
            if fn.startswith("_") or fn in covered or fn in kivetel:
                continue
            end = src.find("\ndef ", m.end())
            body = src[m.start():end if end > 0 else len(src)]
            if '"player_id"' in body and '"top"' in body:
                missing.append(f"{mod.stem}.{fn}")
    assert not missing, ("hiányzik a KPL_LAYERS listából: "
                         + ", ".join(sorted(missing)))


def test_ellenszer_lap_parositja_a_teendot_a_gyakorlattal(monkeypatch):
    """Minden teendőhöz a legjobban illeszkedő gyakorlat kerül, egy
    gyakorlatot csak egyszer használunk fel."""
    from handball.pipeline import priorities

    monkeypatch.setattr(priorities, "priority_findings",
                        lambda match, config=None: {
                            "home": {"top": [
                                {"family": "ár", "label": "Kétperc ára",
                                 "verdict": "a kiállításaik gólba kerülnek"},
                                {"family": "ember",
                                 "label": "Kettőzött ember",
                                 "verdict": "a kettőzés a 7-esre jár rá"},
                                {"family": "állás", "label": "Óralopás",
                                 "verdict": "vezetve elhúzzák a támadást"},
                            ]},
                            "away": {"top": []}})
    import handball.pipeline.training as training
    monkeypatch.setattr(training, "training_focus",
                        lambda match, config=None: {
                            "home": [
                                {"area": "támadás",
                                 "title": "Kettőzés-elleni leadás",
                                 "why": "a kettőzés nálunk elakad",
                                 "drill": "leadás a lekapcsolódó társnak"},
                                {"area": "védekezés",
                                 "title": "Fegyelem emberre szabva",
                                 "why": "a kiállításaink egy emberre "
                                        "gyűlnek",
                                 "drill": "párharc-időzítés"},
                            ],
                            "away": []})

    rec = priorities.counter_plan(_kp_match())["home"]
    assert rec["total"] == 3, rec
    assert rec["matched"] == 2, rec
    party = {r["label"]: r["drill_title"] for r in rec["pairs"]}
    assert party["Kettőzött ember"] == "Kettőzés-elleni leadás", party
    assert party["Kétperc ára"] == "Fegyelem emberre szabva", party
    assert party["Óralopás"] is None, party
    assert rec["verdict"] and "edzői döntést" in rec["verdict"], rec


def test_ellenszer_lap_hallgat_teendo_nelkul(monkeypatch):
    """Teendő nélkül nincs lap (nem találgatunk)."""
    from handball.pipeline import priorities

    monkeypatch.setattr(priorities, "priority_findings",
                        lambda match, config=None: {
                            "home": {"top": []}, "away": {"top": []}})
    rec = priorities.counter_plan(_kp_match())["home"]
    assert rec["pairs"] == [] and rec["verdict"] is None, rec


def test_rangsor_hatokoron_belul_egyszer_szamolodik(monkeypatch):
    """A teendő-rangsor a primitive_cache hatókörön belül meccsenként
    egyszer fut le — az ellenszer-lap így nem számoltatja újra."""
    from handball.pipeline import priorities
    from handball.pipeline.primitive_cache import primitive_cache

    hivas = {"n": 0}
    eredeti = priorities._registry

    def szamlalt():
        hivas["n"] += 1
        return eredeti()

    monkeypatch.setattr(priorities, "_registry", szamlalt)
    m = _kp_match()
    with primitive_cache(m):
        elso = priorities.priority_findings(m)
        masodik = priorities.priority_findings(m)
    assert hivas["n"] == 1, hivas
    assert elso == masodik
    assert elso is not masodik          # védő-másolat, nem közös objektum


def test_edzes_fokusz_hatokoron_belul_egyszer_szamolodik():
    """Az edzés-fókusz is meccsenként egyszer épül fel a hatókörön
    belül, és minden hívó SAJÁT másolatot kap."""
    from handball.pipeline.primitive_cache import primitive_cache
    from handball.pipeline.training import training_focus

    m = _kp_match()
    with primitive_cache(m):
        elso = training_focus(m)
        masodik = training_focus(m)
        assert elso == masodik
        assert elso is not masodik
        if elso["home"]:
            elso["home"][0]["title"] = "MÓDOSÍTVA"
            assert training_focus(m)["home"][0]["title"] != "MÓDOSÍTVA"


def test_kulcs_ember_kuszob_a_lencse_meretevel_no(monkeypatch):
    """A küszöb a padló és a lista tizede közül a nagyobbik: kis
    lencsénél 4 egyezés elég, nagy lencsénél már nem."""
    egy = {"player_id": 7, "jersey": 7}
    mas = {"player_id": 9, "jersey": 9}

    # Kis lencse (5 réteg): a padló (4) dönt.
    prio = _kpl_stub(monkeypatch, [egy] * 4 + [mas])
    assert prio.key_player(_kp_match())["home"]["top"] == "7"

    # Nagy lencse (60 réteg): a tized (6) dönt, négy egyezés kevés
    # (a többi réteg hallgat, tehát nincs más jelölt sem).
    prio = _kpl_stub(monkeypatch, [egy] * 4 + [None] * 56)
    assert prio.key_player(_kp_match())["home"]["top"] is None


# ---- Hajrá-profil (mi romlik a leginkább a meccs végére) --------------------


def test_hajra_profil_rangsorol_es_kimondja_a_kezdopontot(monkeypatch):
    """Két jel közül a NAGYOBB tétű áll elöl.

    A rangsor kimondott edzői döntés: elöl az, ami közvetlenül gólt ér
    (a lassuló visszaállás minden lövés után kontra-ablakot nyit), és
    csak utána a támadó-oldali beszűkülés.
    """
    from handball.pipeline import priorities as pr

    ures = {"home": {}, "away": {}}
    monkeypatch.setattr(
        "handball.pipeline.defense.retreat_fade",
        lambda m, c=None: {"home": {"fh_s": 4.0, "sh_s": 7.0, "slow_s": 3.0},
                           "away": {}})
    monkeypatch.setattr(
        "handball.pipeline.attack_types.wing_involvement_fade",
        lambda m, c=None: {"home": {"fh_pct": 70.0, "sh_pct": 40.0,
                                    "drop_pct": 30.0}, "away": {}})
    monkeypatch.setattr("handball.pipeline.defense.line_height_fade",
                        lambda m, c=None: ures)
    monkeypatch.setattr("handball.pipeline.defense.pressure_fade",
                        lambda m, c=None: ures)
    monkeypatch.setattr("handball.pipeline.stats.sprint_fade",
                        lambda m, c=None: ures)

    rec = pr.fatigue_profile(Match(_meta(), []))["home"]
    assert rec["count"] == 2
    assert rec["top"] == "Lassuló visszaállás"
    assert rec["signals"][0]["layer"] == "retreat_fade"
    assert rec["signals"][1]["layer"] == "wing_involvement_fade"
    assert rec["verdict"] and "kontra-ablak" in rec["verdict"]
    # Két jel még nem MINTÁZAT — a "már nem véletlen" mondat nem jár.
    assert "nem véletlen" not in rec["verdict"]


def test_harom_jel_mar_mintazat(monkeypatch):
    """Három azonos irányú jel egy meccsen a hatvan perc kérdése — ezt
    ki kell mondani, mert máshogy hangzik, mint egyetlen szám."""
    from handball.pipeline import priorities as pr

    monkeypatch.setattr(
        "handball.pipeline.defense.retreat_fade",
        lambda m, c=None: {"home": {"fh_s": 4.0, "sh_s": 7.0, "slow_s": 3.0},
                           "away": {}})
    monkeypatch.setattr(
        "handball.pipeline.defense.line_height_fade",
        lambda m, c=None: {"home": {"fh_m": 8.5, "sh_m": 6.5, "drop_m": 2.0},
                           "away": {}})
    monkeypatch.setattr(
        "handball.pipeline.defense.pressure_fade",
        lambda m, c=None: {"home": {"fh_m": 1.0, "sh_m": 2.5,
                                    "loosen_m": 1.5}, "away": {}})
    monkeypatch.setattr("handball.pipeline.attack_types.wing_involvement_fade",
                        lambda m, c=None: {"home": {}, "away": {}})
    monkeypatch.setattr("handball.pipeline.stats.sprint_fade",
                        lambda m, c=None: {"home": {}, "away": {}})

    rec = pr.fatigue_profile(Match(_meta(), []))["home"]
    assert rec["count"] >= pr.FATIGUE_PATTERN_MIN
    assert "nem véletlen" in rec["verdict"]
    assert rec["verdict"].startswith(f"{rec['count']} fáradás-jel")


def test_ures_hajra_profil_ertekes_informacio():
    """Ha egyetlen esés sem szólal meg, a csapat kibírja a hatvan
    percet — ez nem hiányzó adat, hanem eredmény. Üres jelentés, None
    ítélet, hallgatás."""
    from handball.pipeline.priorities import fatigue_profile

    rec = fatigue_profile(Match(_meta(), []))["home"]
    assert rec["signals"] == []
    assert rec["count"] == 0
    assert rec["top"] is None and rec["verdict"] is None
