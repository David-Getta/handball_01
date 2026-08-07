"""Teendő-rangsor — a megszólaló rétegek fontossági sorrendben.

A rendszer háromszáz körüli réteget számol; egy edző ebbe belefullad.
Ez a modul a MEGSZÓLALÓ (nem None) ítéleteket gyűjti össze, és
rangsorolja: mi az az öt dolog, amivel a jövő héten foglalkozni kell.

A rangsor NEM tanult súlyozás, hanem kimondott, vitatható edzői
sorrend — épp ez a magyarázható lánc lényege:

1. **ár** — amit már gólban megfizettek; a hiba ára a legdrágább
   információ, mert bizonyítottan pontot ér;
2. **ember** — néven nevezett minta; holnap reggel kiosztható feladat
   (kit fogjunk, kit pihentessünk);
3. **szünet** — ami a félidőben megváltozik; ez a meccs közbeni
   döntést írja felül, tehát előre kell tudni;
4. **fáradás** — időfüggő romlás; az utolsó húsz perc tervezése;
5. **állás** — eredményjelző-függő minta; feltételes, csak akkor él,
   ha az adott állás előáll;
6. **felkészülés** — poszt-profil: nem hiba és nem is romlás, hanem
   állandó tulajdonság ("a beállójuk hat méterről fejez be"). Ezért
   van a sor VÉGÉN: sürgősség nélkül, de kiosztható feladatként — és
   ha a fenti öt család hallgat (rövid felvétel, kevés esemény),
   akkor legalább ez a lista nem marad üresen.

Családon belül a nyilvántartás sorrendje dönt (stabil, determinisztikus
kimenet). A modul csak olvassa a többi réteget — mindegyiket külön
try/except-tel, hogy egy réteg hibája ne vigye el a rangsort.
"""

from __future__ import annotations

from typing import Optional

from ..models.tracking import Match

# Ennyi teendőt adunk vissza a rangsor tetejéről.
PRF_TOP_N = 5

# A családok sorrendje = a rangsor sorrendje (lásd a modul-docstringet).
PRF_FAMILY_ORDER = ("ár", "ember", "szünet", "fáradás", "állás",
                    "felkészülés")


def _registry() -> list[tuple[str, str, str, str]]:
    """(család, címke, modul, függvénynév) — a rangsorba vont rétegek.

    Kurált lista: minden tétel csapatonkénti dictet ad "verdict"
    kulccsal. A teljes lencse-listák a meccs-jelentés szekcióiban
    láthatók; ide a döntés-értékű rétegek kerültek.
    """
    return [
        # --- ár: amit már gólban megfizettek -------------------------
        ("ár", "Eladott labda ára", "defense", "turnover_punishment"),
        ("ár", "Kihagyás ára", "xg", "miss_punishment"),
        ("ár", "Kihagyás-büntetés", "momentum", "punished_misses"),
        ("ár", "Csere-lyuk ára", "substitutions", "gap_punishment"),
        ("ár", "Kettőzés ára", "defense", "double_punishment"),
        ("ár", "Kilépés ára", "defense", "stepout_punishment"),
        ("ár", "Indítás-hiba ára", "goalkeeper", "outlet_punishment"),
        ("ár", "Elhúzódó támadás ára", "tactics", "slow_attack_cost"),
        ("ár", "Eladás-ár posztonként", "roles", "role_turnover_cost"),
        # --- ember: néven nevezett minta -----------------------------
        ("ember", "Tüzes kéz", "momentum", "hot_hands"),
        ("ember", "Aszály-törő", "momentum", "drought_breakers"),
        ("ember", "Hajrá-birtokló", "momentum", "clutch_ball_hogs"),
        ("ember", "Eltűnő ember", "momentum", "fading_scorers"),
        ("ember", "Eltűnő védő", "defense", "fading_defenders"),
        ("ember", "Felzárkózás-húzó", "momentum", "comeback_carriers"),
        # --- szünet: ami a félidőben megváltozik ---------------------
        ("szünet", "Szünet-váltás", "attack_types", "attack_mix_shift"),
        ("szünet", "Fal-váltás a szünetre", "tactics",
         "defense_form_shift"),
        ("szünet", "Oldal-váltás a szünetre", "tactics",
         "attack_side_shift"),
        ("szünet", "Poszt-váltás a szünetre", "roles",
         "role_share_shift"),
        # --- fáradás: időfüggő romlás --------------------------------
        ("fáradás", "Tempó-esés", "attack_types", "team_pace_fade"),
        ("fáradás", "Lövőerő-esés", "event_detection",
         "shot_speed_fade"),
        ("fáradás", "Gólpassz-esés", "attack_types", "assist_fade"),
        ("fáradás", "Lepattanó-esés", "attack_types",
         "second_chance_fade"),
        ("fáradás", "Fal-fáradás", "xg", "wall_fade"),
        ("fáradás", "Kapus-forma", "goalkeeper", "gk_save_fade"),
        ("fáradás", "Fegyelem-esés", "rules", "discipline_fade"),
        # --- állás: eredményjelző-függő minta ------------------------
        ("állás", "Hiba-állás", "attack_types", "turnovers_by_score"),
        ("állás", "Kontra-állás", "attack_types", "breaks_by_score"),
        ("állás", "Fegyelem-állás", "rules", "suspensions_by_score"),
        ("állás", "Hetes-állás", "rules", "sevens_by_score"),
        ("állás", "7a6-állás", "goalkeeper", "empty_net_by_score"),
        ("állás", "Sprint-állás", "stats", "sprints_by_score"),
        ("állás", "Poszt-állás", "roles", "role_share_by_score"),
        # --- felkészülés: poszt-profil (állandó tulajdonság) ---------
        ("felkészülés", "Poszt-lövéstávolság", "roles",
         "role_shot_distance"),
        ("felkészülés", "Poszt-kapuoldal", "roles", "role_goal_placement"),
        ("felkészülés", "Poszt-lövéserő", "roles", "role_shot_power"),
        ("felkészülés", "Poszt-lövésidőzítés", "roles", "role_shot_timing"),
        ("felkészülés", "Poszt-eladási zóna", "roles",
         "role_turnover_zones"),
        ("felkészülés", "Poszt-labdatartás", "roles", "role_hold_time"),
        ("felkészülés", "Poszt-nyomás", "roles", "role_pressure_finish"),
        ("felkészülés", "Figura-befejező", "setplays",
         "setplay_finishers"),
        ("felkészülés", "Időkérés-befejező", "stoppages",
         "timeout_finisher"),
        ("felkészülés", "Kontra-poszt", "roles", "role_fast_breaks"),
        ("felkészülés", "Gólpassz-poszt", "roles",
         "role_assist_sources"),
        ("felkészülés", "Lövésválasztás", "decisions",
         "shot_choice_quality"),
        ("felkészülés", "Labdaszerző-poszt", "defense",
         "role_steal_sources"),
        ("felkészülés", "Lepattanó-poszt", "attack_types",
         "second_chance_roles"),
        ("felkészülés", "Blokk-poszt", "defense",
         "role_block_sources"),
        ("felkészülés", "7a6-befejező", "goalkeeper",
         "seven_six_finisher_roles"),
        ("felkészülés", "Hetes-okozó poszt", "rules",
         "seven_conceder_roles"),
        ("felkészülés", "Kiülő-poszt", "rules",
         "suspended_roles"),
        ("felkészülés", "Visszafutás-poszt", "defense",
         "slow_retreat_roles"),
        ("felkészülés", "Átvert-poszt", "defense",
         "beaten_defender_roles"),
        ("felkészülés", "Elzáró-poszt", "attack_types",
         "screen_setter_roles"),
        ("felkészülés", "Indítás-vadász poszt", "goalkeeper",
         "outlet_hunter_roles"),
        ("felkészülés", "Bejátszó-poszt", "attack_types",
         "pivot_feeder_roles"),
        ("felkészülés", "Vasember-poszt", "stats", "iron_man_roles"),
        ("felkészülés", "Kockáztató-poszt", "attack_types",
         "risky_passer_roles"),
        ("felkészülés", "Kettőző-poszt", "defense",
         "doubling_defender_roles"),
        ("felkészülés", "Kiosztás-poszt", "attack_types",
         "kickout_target_roles"),
        ("felkészülés", "Emberelőny-poszt", "rules",
         "powerplay_shooter_roles"),
        ("felkészülés", "Emberhátrány-poszt", "rules",
         "shorthanded_shooter_roles"),
        ("felkészülés", "Hajrá-poszt", "momentum",
         "clutch_scorer_roles"),
        ("felkészülés", "Felzárkózás-poszt", "momentum",
         "comeback_carrier_roles"),
        ("felkészülés", "Pazarló-poszt", "xg",
         "wasteful_shooter_roles"),
        ("felkészülés", "Ziccer-poszt", "xg",
         "big_chance_roles"),
        ("felkészülés", "Kulcs-poszt", "priorities", "key_post"),
    ]


def priority_findings(match: Match, config=None) -> dict:
    """Teendő-rangsor: a megszólaló ítéletek fontossági sorrendben.

    Végigolvassa a rangsorba vont rétegeket, összegyűjti a nem-None
    ítéleteket, és a családok kimondott sorrendje szerint rendezi
    (ár → ember → szünet → fáradás → állás; lásd a modul
    docstringjét). A cél nem újabb mérés, hanem a döntés-terhelés
    csökkentése: háromszáz rétegből öt teendő.

    Edzőileg: a "top" lista a jövő heti fókusz — a "families" pedig
    megmutatja, MELYIK TERÜLETRŐL jön a legtöbb jelzés (ha minden
    jelzés az ár-családból jön, nem finomhangolni kell, hanem a
    hibákat megállítani).

    Visszatérés csapatonként: {"top": [{"family", "label",
    "verdict"}] (legfeljebb PRF_TOP_N), "total", "families":
    {család: darab}} — üres lista, ha egyetlen réteg sem szólal meg
    (nem találgatunk).
    """
    import importlib

    from .primitive_cache import primitive_cache

    found: dict = {"home": [], "away": []}
    # Közös hatókör: a rangsorba vont rétegek ugyanazokat az alap-
    # méréseket kérik — így meccsenként egyszer futnak le.
    with primitive_cache(match):
        for family, label, mod_name, fn_name in _registry():
            try:
                mod = importlib.import_module(f".{mod_name}", __package__)
                fn = getattr(mod, fn_name)
                res = fn(match, config)
            except Exception:
                continue  # egy réteg hibája nem viheti el a rangsort
            for side in ("home", "away"):
                rec = (res or {}).get(side) or {}
                verdict = rec.get("verdict")
                if verdict:
                    found[side].append({"family": family, "label": label,
                                        "verdict": str(verdict)})

    order = {f: i for i, f in enumerate(PRF_FAMILY_ORDER)}
    out = {}
    for side in ("home", "away"):
        items = found[side]
        # Stabil rendezés: család-sorrend, azon belül a nyilvántartás
        # sorrendje (az enumerate-index tartja meg).
        ranked = sorted(enumerate(items),
                        key=lambda pair: (order.get(pair[1]["family"],
                                                    len(order)),
                                          pair[0]))
        families: dict = {}
        for _, it in ranked:
            families[it["family"]] = families.get(it["family"], 0) + 1
        out[side] = {
            "top": [it for _, it in ranked[:PRF_TOP_N]],
            "total": len(items),
            "families": families,
        }
    return out


# Kulcs-poszt: ennyi rétegnek kell ugyanarra a posztra mutatnia, hogy
# a posztot a meccsterv első lapjának mondjuk ki.
KP_MIN_LAYERS = 3

# A poszt-ítéletes rétegek: mindegyik csapatonkénti dictet ad
# "main_role" és "verdict" kulccsal ("egy réteg, sok felület" minta).
KP_LAYERS: tuple = (
    ("Figura-befejező", "setplays", "setplay_finishers"),
    ("Időkérés-befejező", "stoppages", "timeout_finisher"),
    ("Kontra-poszt", "roles", "role_fast_breaks"),
    ("Gólpassz-poszt", "roles", "role_assist_sources"),
    ("Lepattanó-poszt", "attack_types", "second_chance_roles"),
    ("Elzáró-poszt", "attack_types", "screen_setter_roles"),
    ("7a6-befejező", "goalkeeper", "seven_six_finisher_roles"),
    ("Labdaszerző-poszt", "defense", "role_steal_sources"),
    ("Blokk-poszt", "defense", "role_block_sources"),
    ("Visszafutás-poszt", "defense", "slow_retreat_roles"),
    ("Átvert-poszt", "defense", "beaten_defender_roles"),
    ("Hetes-okozó poszt", "rules", "seven_conceder_roles"),
    ("Kiülő-poszt", "rules", "suspended_roles"),
    ("Indítás-vadász poszt", "goalkeeper", "outlet_hunter_roles"),
    ("Bejátszó-poszt", "attack_types", "pivot_feeder_roles"),
    ("Kockáztató-poszt", "attack_types", "risky_passer_roles"),
    ("Vasember-poszt", "stats", "iron_man_roles"),
    ("Kettőző-poszt", "defense", "doubling_defender_roles"),
    ("Kiosztás-poszt", "attack_types", "kickout_target_roles"),
    ("Emberelőny-poszt", "rules", "powerplay_shooter_roles"),
    ("Emberhátrány-poszt", "rules", "shorthanded_shooter_roles"),
    ("Hajrá-poszt", "momentum", "clutch_scorer_roles"),
    ("Felzárkózás-poszt", "momentum", "comeback_carrier_roles"),
    ("Pazarló-poszt", "xg", "wasteful_shooter_roles"),
    ("Ziccer-poszt", "xg", "big_chance_roles"),
)


def key_post(match: Match, config=None) -> dict:
    """Kulcs-poszt: HÁNY RÉTEG mutat ugyanarra a posztra.

    A poszt-lencse rétegek (kire fut ki a játékuk, hol sebezhető a
    védekezésük) egyenként egy-egy mintát mondanak ki — ez a réteg
    összeszámolja őket: ha a megszólaló ítéletek zöme ugyanazt a
    posztot nevezi meg, az a csapat KULCS-POSZTJA.

    Edzőileg ez a meccsterv első lapja. Az ellenfélnél: ha náluk a
    beállóra mutat a lepattanó-, a blokk- és az elzáró-réteg is, nem
    három külön feladat van, hanem EGY — az ő kezelése (fogás, zárás,
    kettőzés) többet old meg, mint bármely részszabály. Saját
    csapatnál: ha a mintáink egy emberre futnak ki, a játékunk
    kiszámítható — tehermentesítés és variáció kell.

    Visszatérés csapatonként: {"layers" (megszólaló poszt-réteg),
    "posts": {poszt: réteg-darab}, "named": [{"layer", "poszt"}],
    "top", "verdict"} — a top/verdict None, ha nincs KP_MIN_LAYERS
    egyező réteg, vagy az élen holtverseny áll.
    """
    import importlib

    from .primitive_cache import primitive_cache

    out: dict = {side: {"layers": 0, "posts": {}, "named": [],
                        "top": None, "verdict": None}
                 for side in ("home", "away")}
    with primitive_cache(match):
        for label, mod_name, fn_name in KP_LAYERS:
            try:
                mod = importlib.import_module(f".{mod_name}", __package__)
                rec_all = getattr(mod, fn_name)(match)
            except Exception:
                continue
            for side in ("home", "away"):
                rec = rec_all.get(side) or {}
                poszt = rec.get("main_role")
                if rec.get("verdict") is None or poszt is None:
                    continue
                o = out[side]
                o["layers"] += 1
                o["posts"][poszt] = o["posts"].get(poszt, 0) + 1
                o["named"].append({"layer": label, "poszt": poszt})
    for o in out.values():
        o["posts"] = dict(sorted(o["posts"].items(),
                                 key=lambda kv: -kv[1]))
        if not o["posts"]:
            continue
        vals = list(o["posts"].values())
        top_n = vals[0]
        tie = len(vals) > 1 and vals[1] == top_n
        if top_n >= KP_MIN_LAYERS and not tie:
            poszt = next(iter(o["posts"]))
            o["top"] = poszt
            o["verdict"] = (
                f"a kulcs-posztjuk a(z) {poszt}: {top_n} réteg "
                f"ítélete fut ki rá (a {o['layers']} megszólalóból) — "
                "az ő kezelése nem részfeladat, hanem a meccsterv "
                "első lapja")
    return out
