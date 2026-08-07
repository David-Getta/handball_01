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
