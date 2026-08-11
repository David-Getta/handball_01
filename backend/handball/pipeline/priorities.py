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
from .primitive_cache import memoize_primitive

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
        ("ár", "Csere-hozam", "substitutions",
         "substitution_yield"),
        ("ár", "Kettőzés ára", "defense", "double_punishment"),
        ("ár", "Kilépés ára", "defense", "stepout_punishment"),
        ("ár", "Indítás-hiba ára", "goalkeeper", "outlet_punishment"),
        ("ár", "Elhúzódó támadás ára", "tactics", "slow_attack_cost"),
        ("ár", "Visszaállás ára", "defense", "retreat_punishment"),
        ("ár", "Kipattanó ára", "goalkeeper", "rebound_punishment"),
        ("ár", "Kapus-visszaérés", "goalkeeper", "keeper_return"),
        ("ár", "7a6 eladás ára", "goalkeeper",
         "empty_net_turnovers"),
        ("ár", "Kétperc ára", "rules", "suspension_cost"),
        ("ár", "Emberelőny-hozam", "rules", "powerplay_yield"),
        ("ár", "Eladás-ár posztonként", "roles", "role_turnover_cost"),
        # --- ember: néven nevezett minta -----------------------------
        ("ember", "Tüzes kéz", "momentum", "hot_hands"),
        ("ember", "Aszály-törő", "momentum", "drought_breakers"),
        ("ember", "Hajrá-birtokló", "momentum", "clutch_ball_hogs"),
        ("ember", "Eltűnő ember", "momentum", "fading_scorers"),
        ("ember", "Eltűnő védő", "defense", "fading_defenders"),
        ("ember", "Felzárkózás-húzó", "momentum", "comeback_carriers"),
        ("ember", "Fáradt-eladó", "decisions",
         "tired_turnover_players"),
        ("ember", "Visszafutás-lemaradó", "defense",
         "slow_retreat_players"),
        ("ember", "Fáradt-fal ember", "defense",
         "tired_conceder_players"),
        ("ember", "Indítás-vadász", "goalkeeper", "outlet_hunters"),
        ("ember", "Kiszolgált befejező", "roles",
         "assisted_scorers"),
        ("ember", "Kétperc-gyűjtő", "rules",
         "suspension_collectors"),
        ("ember", "Felhozatal-ember", "goalkeeper",
         "outlet_targets"),
        ("ember", "Kettőzött ember", "defense", "doubled_targets"),
        ("ember", "Hátrapasszoló", "attack_types",
         "backward_passers"),
        ("ember", "Térnyerő", "decisions", "ball_carriers"),
        ("ember", "Sávváltó", "attack_types", "lane_switchers"),
        ("ember", "Menekülő", "decisions", "press_outlets"),
        ("ember", "Vég-birtokos", "attack_types", "last_holders"),
        ("ember", "Ziccer-előkészítő", "xg", "big_chance_feeders"),
        ("ember", "Válaszhiba-ember", "momentum",
         "response_turnover_players"),
        ("ember", "Időkérés-hibázó", "stoppages",
         "timeout_turnover_players"),
        ("ember", "Hetesdobó", "rules", "seven_taker_players"),
        ("ember", "Hetes-kihagyó", "rules", "seven_miss_players"),
        ("ember", "Kipattanó-szedő", "defense",
         "defensive_rebound_players"),
        ("ember", "Emberelőny-hibázó", "rules",
         "powerplay_turnover_players"),
        ("ember", "Emberhátrány-hibázó", "rules",
         "shorthanded_turnover_players"),
        ("ember", "Kulcs-ember", "priorities", "key_player"),
        # --- szünet: ami a félidőben megváltozik ---------------------
        ("szünet", "Szünet-váltás", "attack_types", "attack_mix_shift"),
        ("szünet", "Fal-váltás a szünetre", "tactics",
         "defense_form_shift"),
        ("szünet", "Oldal-váltás a szünetre", "tactics",
         "attack_side_shift"),
        ("szünet", "Poszt-váltás a szünetre", "roles",
         "role_share_shift"),
        ("szünet", "Emberfogás-váltás", "defense", "marking_shift"),
        # --- fáradás: időfüggő romlás --------------------------------
        ("fáradás", "Tempó-esés", "attack_types", "team_pace_fade"),
        ("fáradás", "Lövőerő-esés", "event_detection",
         "shot_speed_fade"),
        ("fáradás", "Gólpassz-esés", "attack_types", "assist_fade"),
        ("fáradás", "Lepattanó-esés", "attack_types",
         "second_chance_fade"),
        ("fáradás", "Fal-fáradás", "xg", "wall_fade"),
        ("fáradás", "Blokk-fáradás", "defense", "block_fade"),
        ("fáradás", "Kapus-forma", "goalkeeper", "gk_save_fade"),
        ("fáradás", "Fegyelem-esés", "rules", "discipline_fade"),
        ("fáradás", "Sprint-esés", "stats", "sprint_fade"),
        ("fáradás", "Futómunka-eloszlás", "stats",
         "running_load_balance"),
        # --- állás: eredményjelző-függő minta ------------------------
        ("állás", "Hiba-állás", "attack_types", "turnovers_by_score"),
        ("állás", "Kontra-állás", "attack_types", "breaks_by_score"),
        ("állás", "Fegyelem-állás", "rules", "suspensions_by_score"),
        ("állás", "Hetes-állás", "rules", "sevens_by_score"),
        ("állás", "7a6-állás", "goalkeeper", "empty_net_by_score"),
        ("állás", "Sprint-állás", "stats", "sprints_by_score"),
        ("állás", "Poszt-állás", "roles", "role_share_by_score"),
        ("állás", "Óralopás", "momentum", "clock_management"),
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
        ("felkészülés", "Figura-kopás", "setplays", "setplay_decay"),
        ("felkészülés", "Időkérés-befejező", "stoppages",
         "timeout_finisher"),
        ("felkészülés", "Kontra-poszt", "roles", "role_fast_breaks"),
        ("felkészülés", "Gólpassz-poszt", "roles",
         "role_assist_sources"),
        ("felkészülés", "Lövésválasztás", "decisions",
         "shot_choice_quality"),
        ("felkészülés", "Elzárás-hozam", "attack_types",
         "screen_yield"),
        ("felkészülés", "Hetes-hozam", "rules", "seven_yield"),
        ("felkészülés", "Passzív-kockázat", "rules", "passive_risk"),
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
        ("felkészülés", "Labdatartó-poszt", "decisions",
         "hold_time_roles"),
        ("felkészülés", "Pressz-poszt", "decisions",
         "press_sensitive_roles"),
        ("felkészülés", "Csendtörő-poszt", "momentum",
         "drought_breaker_roles"),
        ("felkészülés", "Eltűnő-poszt", "momentum",
         "fading_scorer_roles"),
        ("felkészülés", "Hajráhiba-poszt", "momentum",
         "clutch_turnover_roles"),
        ("felkészülés", "Forró-poszt", "momentum",
         "hot_hand_roles"),
        ("felkészülés", "Középkezdő-poszt", "momentum",
         "restart_taker_roles"),
        ("felkészülés", "Sprint-poszt", "stats",
         "sprint_threat_roles"),
        ("felkészülés", "Lágypassz-poszt", "decisions",
         "soft_pass_roles"),
        ("felkészülés", "Hajrákéz-poszt", "momentum",
         "clutch_hog_roles"),
        ("felkészülés", "Kiszolgált-poszt", "roles",
         "assisted_scorer_roles"),
        ("felkészülés", "Rajt-poszt", "momentum",
         "opening_scorer_roles"),
        ("felkészülés", "Passzív-poszt", "rules",
         "passive_holder_roles"),
        ("felkészülés", "Fáradó-poszt", "stats",
         "fatigue_roles"),
        ("felkészülés", "Kettőzött-poszt", "defense",
         "doubled_target_roles"),
        ("felkészülés", "Elzárt-poszt", "defense",
         "screened_defender_roles"),
        ("felkészülés", "Újrakezdő-poszt", "momentum",
         "second_start_roles"),
        ("felkészülés", "Hetesdobó-poszt", "rules",
         "seven_taker_roles"),
        ("felkészülés", "Blokkolt-poszt", "defense",
         "blocked_shooter_roles"),
        ("felkészülés", "Ziccerhagyó-poszt", "xg",
         "missed_chance_roles"),
        ("felkészülés", "Kilépő-poszt", "defense",
         "advanced_defender_roles"),
        ("felkészülés", "Beállóőr-poszt", "defense",
         "pivot_guard_roles"),
        ("felkészülés", "Indító-poszt", "roles",
         "attack_starter_roles"),
        ("felkészülés", "Előkészítő-poszt", "attack_types",
         "last_pass_roles"),
        ("felkészülés", "Előnyben-poszt", "momentum",
         "lead_scorer_roles"),
        ("felkészülés", "Térnyerő-poszt", "decisions",
         "ball_carrier_roles"),
        ("felkészülés", "Hátrapassz-poszt", "attack_types",
         "backward_pass_roles"),
        ("felkészülés", "Fáradt-eladó poszt", "decisions",
         "tired_turnover_roles"),
        ("felkészülés", "Fáradt-lövő poszt", "xg",
         "tired_shooter_roles"),
        ("felkészülés", "Fáradt-fal poszt", "defense",
         "tired_conceder_roles"),
        ("felkészülés", "Forgatott-poszt", "substitutions",
         "substituted_roles"),
        ("felkészülés", "Beérkező-poszt", "substitutions",
         "sub_in_roles"),
        ("felkészülés", "Drága-eladó poszt", "defense",
         "costly_turnover_roles"),
        ("felkészülés", "Áttörő-poszt", "attack_types",
         "breakthrough_roles"),
        ("felkészülés", "Védőmotor-poszt", "defense",
         "fading_defender_roles"),
        ("felkészülés", "Fedezett-lövő poszt", "defense",
         "covered_shooter_roles"),
        ("felkészülés", "Célkereszt-poszt", "defense",
         "targeted_defender_roles"),
        ("felkészülés", "Letámadó-poszt", "defense",
         "high_steal_roles"),
        ("felkészülés", "Álló-poszt", "tactics",
         "static_attacker_roles"),
        ("felkészülés", "Elzárópáros-poszt", "attack_types",
         "screen_pair_roles"),
        ("felkészülés", "Csere-stílus", "substitutions",
         "swap_style"),
        ("felkészülés", "Hetespáros-poszt", "rules",
         "seven_pair_roles"),
        ("felkészülés", "Kontrapáros-poszt", "attack_types",
         "fast_break_pair_roles"),
        ("felkészülés", "Gólpasszpáros-poszt", "roles",
         "assist_pair_roles"),
        ("felkészülés", "Kettőzőpáros-poszt", "defense",
         "doubling_pair_roles"),
        ("felkészülés", "Lepattanópáros-poszt", "attack_types",
         "rebound_pair_roles"),
        ("felkészülés", "Kulcs-poszt", "priorities", "key_post"),
        ("felkészülés", "Kulcs-páros", "priorities", "key_pair"),
        ("felkészülés", "Specialista-poszt", "roles",
         "specialist_roles"),
        ("felkészülés", "Emberelőnypáros-poszt", "rules",
         "powerplay_pair_roles"),
        ("felkészülés", "Válasz-poszt", "momentum",
         "response_scorer_roles"),
        ("felkészülés", "Elöl lógó poszt", "defense",
         "recovery_roles"),
        ("felkészülés", "Sávváltó-poszt", "attack_types",
         "lane_switch_roles"),
        ("felkészülés", "Időkéréspáros-poszt", "stoppages",
         "timeout_pair_roles"),
        ("felkészülés", "Menekülő-poszt", "decisions",
         "press_outlet_roles"),
        ("felkészülés", "Vég-birtokos poszt", "attack_types",
         "last_holder_roles"),
        ("felkészülés", "Ziccer-előkészítő poszt", "xg",
         "big_chance_feeder_roles"),
        ("felkészülés", "Hetes-kihagyó poszt", "rules",
         "seven_miss_roles"),
        ("felkészülés", "Ziccerpáros-poszt", "xg",
         "big_chance_pair_roles"),
        ("felkészülés", "Emberelőny-hiba poszt", "rules",
         "powerplay_turnover_roles"),
        ("felkészülés", "Válaszhiba-poszt", "momentum",
         "response_turnover_roles"),
        ("felkészülés", "Időkérés-hiba poszt", "stoppages",
         "timeout_turnover_roles"),
        ("felkészülés", "Visszaállás-idő", "defense", "retreat_time"),
        ("felkészülés", "Kapkodás-index", "attack_types",
         "post_goal_rush"),
        ("felkészülés", "Emberhátrány-hiba poszt", "rules",
         "shorthanded_turnover_roles"),
        ("felkészülés", "Hajrá-kapus", "goalkeeper",
         "gk_clutch_saves"),
        ("felkészülés", "Figura-koncentráció", "setplays",
         "setplay_concentration"),
        ("felkészülés", "Lepattanó-szedő poszt", "defense",
         "defensive_rebound_roles"),
        ("felkészülés", "Kétperc-páros", "rules",
         "suspension_chain_roles"),
        ("felkészülés", "Áttörés-hozam", "attack_types",
         "breakthrough_yield"),
    ]


def _prf_copy(val: dict) -> dict:
    """Védő-másolat a gyorsítótárazott rangsorhoz (a hívó módosíthatja)."""
    return {side: {"top": [dict(it) for it in rec["top"]],
                   "total": rec["total"],
                   "families": dict(rec["families"])}
            for side, rec in val.items()}


@memoize_primitive("priority_findings", copy=_prf_copy)
def _priority_findings_cached(match: Match, config=None) -> dict:
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


def priority_findings(match: Match, config=None) -> dict:
    """Teendő-rangsor (lásd `_priority_findings_cached`).

    A számolás a `primitive_cache` hatókörön belül meccsenként EGYSZER
    fut le: az ellenszer-lap és a meccs-csomag is ezt olvassa, így a
    rangsor nem számolódik újra rétegenként.
    """
    return _priority_findings_cached(match, config)


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
    ("Labdatartó-poszt", "decisions", "hold_time_roles"),
    ("Pressz-poszt", "decisions", "press_sensitive_roles"),
    ("Csendtörő-poszt", "momentum", "drought_breaker_roles"),
    ("Eltűnő-poszt", "momentum", "fading_scorer_roles"),
    ("Hajráhiba-poszt", "momentum", "clutch_turnover_roles"),
    ("Forró-poszt", "momentum", "hot_hand_roles"),
    ("Középkezdő-poszt", "momentum", "restart_taker_roles"),
    ("Sprint-poszt", "stats", "sprint_threat_roles"),
    ("Lágypassz-poszt", "decisions", "soft_pass_roles"),
    ("Hajrákéz-poszt", "momentum", "clutch_hog_roles"),
    ("Kiszolgált-poszt", "roles", "assisted_scorer_roles"),
    ("Rajt-poszt", "momentum", "opening_scorer_roles"),
    ("Passzív-poszt", "rules", "passive_holder_roles"),
    ("Fáradó-poszt", "stats", "fatigue_roles"),
    ("Kettőzött-poszt", "defense", "doubled_target_roles"),
    ("Elzárt-poszt", "defense", "screened_defender_roles"),
    ("Újrakezdő-poszt", "momentum", "second_start_roles"),
    ("Hetesdobó-poszt", "rules", "seven_taker_roles"),
    ("Blokkolt-poszt", "defense", "blocked_shooter_roles"),
    ("Ziccerhagyó-poszt", "xg", "missed_chance_roles"),
    ("Kilépő-poszt", "defense", "advanced_defender_roles"),
    ("Beállóőr-poszt", "defense", "pivot_guard_roles"),
    ("Indító-poszt", "roles", "attack_starter_roles"),
    ("Előkészítő-poszt", "attack_types", "last_pass_roles"),
    ("Előnyben-poszt", "momentum", "lead_scorer_roles"),
    ("Térnyerő-poszt", "decisions", "ball_carrier_roles"),
    ("Hátrapassz-poszt", "attack_types", "backward_pass_roles"),
    ("Fáradt-eladó poszt", "decisions", "tired_turnover_roles"),
    ("Fáradt-lövő poszt", "xg", "tired_shooter_roles"),
    ("Fáradt-fal poszt", "defense", "tired_conceder_roles"),
    ("Forgatott-poszt", "substitutions", "substituted_roles"),
    ("Beérkező-poszt", "substitutions", "sub_in_roles"),
    ("Drága-eladó poszt", "defense", "costly_turnover_roles"),
    ("Áttörő-poszt", "attack_types", "breakthrough_roles"),
    ("Védőmotor-poszt", "defense", "fading_defender_roles"),
    ("Fedezett-lövő poszt", "defense", "covered_shooter_roles"),
    ("Célkereszt-poszt", "defense", "targeted_defender_roles"),
    ("Letámadó-poszt", "defense", "high_steal_roles"),
    ("Álló-poszt", "tactics", "static_attacker_roles"),
    ("Specialista-poszt", "roles", "specialist_roles"),
    ("Válasz-poszt", "momentum", "response_scorer_roles"),
    ("Elöl lógó poszt", "defense", "recovery_roles"),
    ("Sávváltó-poszt", "attack_types", "lane_switch_roles"),
    ("Menekülő-poszt", "decisions", "press_outlet_roles"),
    ("Vég-birtokos poszt", "attack_types", "last_holder_roles"),
    ("Ziccer-előkészítő poszt", "xg", "big_chance_feeder_roles"),
    ("Hetes-kihagyó poszt", "rules", "seven_miss_roles"),
    ("Emberelőny-hiba poszt", "rules", "powerplay_turnover_roles"),
    ("Válaszhiba-poszt", "momentum", "response_turnover_roles"),
    ("Időkérés-hiba poszt", "stoppages", "timeout_turnover_roles"),
    ("Emberhátrány-hiba poszt", "rules",
     "shorthanded_turnover_roles"),
    ("Lepattanó-szedő poszt", "defense", "defensive_rebound_roles"),
)


# Kulcs-páros: a PÁROS-lencse rétegek (két posztot megnevező minták)
# névsora, és ennyi egyező réteg kell a kulcs-páros kimondásához. A
# páros-rétegek szándékosan NEM a KP_LAYERS-ben vannak: a kulcs-poszt
# egy embert keres, a kulcs-páros egy kettőst — a kettő keverése
# mindkét számot hígítaná.
KPR_MIN_LAYERS = 2
KP_PAIRS: tuple = (
    ("Elzárópáros-poszt", "attack_types", "screen_pair_roles"),
    ("Hetespáros-poszt", "rules", "seven_pair_roles"),
    ("Kontrapáros-poszt", "attack_types", "fast_break_pair_roles"),
    ("Gólpasszpáros-poszt", "roles", "assist_pair_roles"),
    ("Kettőzőpáros-poszt", "defense", "doubling_pair_roles"),
    ("Lepattanópáros-poszt", "attack_types", "rebound_pair_roles"),
    ("Emberelőnypáros-poszt", "rules", "powerplay_pair_roles"),
    ("Időkéréspáros-poszt", "stoppages", "timeout_pair_roles"),
    ("Ziccerpáros-poszt", "xg", "big_chance_pair_roles"),
    ("Kétperc-páros", "rules", "suspension_chain_roles"),
)

# A Specialista-poszt a KP_LAYERS-be tartozik (egy posztot nevez meg).


def key_pair(match: Match, config=None) -> dict:
    """Kulcs-páros: HÁNY RÉTEG mutat ugyanarra a POSZTPÁRRA.

    A páros-lencse rétegek (ki zár kinek, ki indít kinek, ki érkezik
    a lepattanóra, melyik kettős kettőz) egyenként egy-egy bejáratott
    kettőst neveznek meg — ez a réteg összeszámolja őket: ha több
    ítélet ugyanazt a párost adja vissza, az a csapat KULCS-PÁROSA.

    Edzőileg ez a meccsterv második lapja (a kulcs-poszt után): a
    kulcs-poszt EGY embert jelöl ki, a kulcs-páros egy TENGELYT — a
    kettejük közti passzsáv és a hozzájuk tartozó figura az, amit
    szét kell választani. Ha a kettőst megbontjuk (a sávot zárva, az
    egyiket kivéve), több minta hal el egyszerre. Saját csapatnál a
    kulcs-páros a kiszámíthatóság mérője: a figuráinknak másik
    tengelyen is futniuk kell.

    Visszatérés csapatonként: {"layers" (megszólaló páros-réteg),
    "pairs": {páros: réteg-darab}, "named": [{"layer", "pair"}],
    "top", "verdict"} — a top/verdict None, ha nincs KPR_MIN_LAYERS
    egyező réteg, vagy az élen holtverseny áll.
    """
    import importlib

    from .primitive_cache import primitive_cache

    out: dict = {side: {"layers": 0, "pairs": {}, "named": [],
                        "top": None, "verdict": None}
                 for side in ("home", "away")}
    with primitive_cache(match):
        for label, mod_name, fn_name in KP_PAIRS:
            try:
                mod = importlib.import_module(f".{mod_name}", __package__)
                rec_all = getattr(mod, fn_name)(match)
            except Exception:
                continue
            for side in ("home", "away"):
                rec = rec_all.get(side) or {}
                par = rec.get("main_role")
                if rec.get("verdict") is None or par is None:
                    continue
                o = out[side]
                o["layers"] += 1
                o["pairs"][par] = o["pairs"].get(par, 0) + 1
                o["named"].append({"layer": label, "pair": par})
    for o in out.values():
        o["pairs"] = dict(sorted(o["pairs"].items(),
                                 key=lambda kv: -kv[1]))
        if not o["pairs"]:
            continue
        vals = list(o["pairs"].values())
        top_n = vals[0]
        tie = len(vals) > 1 and vals[1] == top_n
        if top_n >= KPR_MIN_LAYERS and not tie:
            par = next(iter(o["pairs"]))
            o["top"] = par
            o["verdict"] = (
                f"a kulcs-párosuk a(z) {par}: {top_n} réteg ítélete "
                f"mutat rá (a {o['layers']} megszólalóból) — a "
                "kettejük közti sávot kell szétvágni, mert azzal "
                "több mintájuk hal el egyszerre")
    return out


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


# Kulcs-ember: az EMBERT (nem posztot) megnevező rétegek névsora, és
# ennyi egyező réteg kell a kulcs-ember kimondásához. A poszt-lencse
# küszöbénél magasabb, mert emberből több forrás van, és egy sztár
# természetes módon több listán szerepel — a jelzés akkor érdekes, ha
# NÉGY különböző szempont ugyanoda mutat.
KPL_MIN_LAYERS = 4

KPL_LAYERS: tuple = (
    ("Tüzes kéz", "momentum", "hot_hands"),
    ("Aszály-törő", "momentum", "drought_breakers"),
    ("Hajrá-birtokló", "momentum", "clutch_ball_hogs"),
    ("Eltűnő ember", "momentum", "fading_scorers"),
    ("Felzárkózás-húzó", "momentum", "comeback_carriers"),
    ("Hajrá-hibázó", "momentum", "clutch_turnover_players"),
    ("Középkezdés-átvevő", "momentum", "restart_targets"),
    ("Eltűnő védő", "defense", "fading_defenders"),
    ("Letámadó", "defense", "high_steal_players"),
    ("Átvert védő", "defense", "beaten_defenders"),
    ("Kettőző védő", "defense", "doubling_defenders"),
    ("Blokkolt lövő", "defense", "blocked_shooters"),
    ("Fedezett lövő", "defense", "covered_shooters"),
    ("Beállóőr", "defense", "pivot_guards"),
    ("Kilépő védő", "defense", "advanced_defender"),
    ("Kipattanó-szedő", "defense", "defensive_rebound_players"),
    ("Támadás-indító", "attack_types", "attack_starters"),
    ("Beálló-bejátszó", "attack_types", "pivot_feeders"),
    ("Áttörő", "attack_types", "breakthrough_players"),
    ("Elzáró", "attack_types", "screen_setters"),
    ("Kockázatos passzoló", "attack_types", "risky_passers"),
    ("Kiosztás-célpont", "attack_types", "kickout_targets"),
    ("Pressz-érzékeny", "decisions", "pressure_sensitive_players"),
    ("Emberelőny-lövő", "rules", "powerplay_shooters"),
    ("Emberhátrány-lövő", "rules", "shorthanded_shooters"),
    ("Fáradt-eladó", "decisions", "tired_turnover_players"),
    ("Visszafutás-lemaradó", "defense", "slow_retreat_players"),
    ("Fáradt-fal ember", "defense", "tired_conceder_players"),
    ("Indítás-vadász", "goalkeeper", "outlet_hunters"),
    ("Kiszolgált befejező", "roles", "assisted_scorers"),
    ("Kétperc-gyűjtő", "rules", "suspension_collectors"),
    ("Felhozatal-ember", "goalkeeper", "outlet_targets"),
    ("Kettőzött ember", "defense", "doubled_targets"),
    ("Hátrapasszoló", "attack_types", "backward_passers"),
    ("Térnyerő", "decisions", "ball_carriers"),
    ("Sávváltó", "attack_types", "lane_switchers"),
    ("Menekülő", "decisions", "press_outlets"),
    ("Vég-birtokos", "attack_types", "last_holders"),
    ("Ziccer-előkészítő", "xg", "big_chance_feeders"),
    ("Válaszhiba-ember", "momentum", "response_turnover_players"),
    ("Időkérés-hibázó", "stoppages", "timeout_turnover_players"),
    ("Hetesdobó", "rules", "seven_taker_players"),
    ("Hetes-kihagyó", "rules", "seven_miss_players"),
    ("Emberelőny-hibázó", "rules", "powerplay_turnover_players"),
    ("Emberhátrány-hibázó", "rules",
     "shorthanded_turnover_players"),
    ("Hetes-okozó", "rules", "seven_meter_conceders"),
    ("Sprint-veszély", "stats", "sprint_threats"),
    ("Pazarló lövő", "xg", "wasteful_shooters"),
)


def key_player(match: Match, config=None) -> dict:
    """Kulcs-ember: HÁNY RÉTEG mutat ugyanarra a JÁTÉKOSRA.

    A Kulcs-poszt a posztot, a Kulcs-páros a kettőst nevezi meg — ez
    az EMBERT: a néven nevező rétegek (tüzes kéz, aszály-törő,
    hajrá-birtokló, letámadó, áttörő, elzáró, kipattanó-szedő,
    hetes-kihagyó, …) élén álló játékosokat számolja össze
    csapatonként. A három szintézis szándékosan külön áll: a "melyik
    poszt", a "melyik kettős" és a "melyik EMBER" kérdés más-más
    választ ad, és nem szabad hígítaniuk egymást.

    Edzőileg ez a személyre szóló feladat lapja. Az ellenfélnél: ha
    négy különböző szempont ugyanazt az embert dobja ki, ő nem egy a
    hét mezőnyjátékos közül — az ő kezelése (emberfogás, kettőzés,
    tudatos fárasztás, a labdaútjának elvágása) önmagában
    meccstervnyi. Saját csapatnál ugyanez a figyelmeztetés: ha
    minden rajta fut keresztül, egy jó ellenfél egy emberrel
    megfogja a játékunkat — tehermentesítés és második út kell.

    Visszatérés csapatonként: {"layers" (megszólaló ember-réteg),
    "players": {játékos-kulcs: réteg-darab}, "named": [{"layer",
    "player"}], "top", "verdict"} — a top/verdict None, ha nincs
    KPL_MIN_LAYERS egyező réteg, vagy az élen holtverseny áll. A
    játékos-kulcs a mezszám, ha ismert; különben a track-azonosító.
    """
    import importlib

    from .primitive_cache import primitive_cache

    out: dict = {side: {"layers": 0, "players": {}, "named": [],
                        "top": None, "verdict": None}
                 for side in ("home", "away")}
    with primitive_cache(match):
        for label, mod_name, fn_name in KPL_LAYERS:
            try:
                mod = importlib.import_module(f".{mod_name}", __package__)
                rec_all = getattr(mod, fn_name)(match)
            except Exception:
                continue
            for side in ("home", "away"):
                rec = rec_all.get(side) or {}
                top = rec.get("top")
                if not isinstance(top, dict):
                    continue
                pid = top.get("player_id")
                if pid is None:
                    continue
                jersey = top.get("jersey")
                kulcs = str(jersey if jersey is not None else pid)
                o = out[side]
                o["layers"] += 1
                o["players"][kulcs] = o["players"].get(kulcs, 0) + 1
                o["named"].append({"layer": label, "player": kulcs})
    for o in out.values():
        o["players"] = dict(sorted(o["players"].items(),
                                   key=lambda kv: -kv[1]))
        if not o["players"]:
            continue
        vals = list(o["players"].values())
        top_n = vals[0]
        tie = len(vals) > 1 and vals[1] == top_n
        if top_n >= KPL_MIN_LAYERS and not tie:
            kulcs = next(iter(o["players"]))
            o["top"] = kulcs
            o["verdict"] = (
                f"a kulcs-emberük a(z) {kulcs}. számú: {top_n} réteg "
                f"ítélete mutat rá (a {o['layers']} megszólalóból) — "
                "ő nem egy a hét mezőnyjátékos közül, az ő kezelése "
                "önmagában meccstervnyi feladat")
    return out



# Ellenszer-lap: ennyi közös kulcsszó kell a teendő és a gyakorlat
# párosításához, és a szavakat ennyi karakterre csonkolva hasonlítjuk
# (a magyar toldalékok miatt).
CPL_MIN_OVERLAP = 1
CPL_STEM = 6


def _cpl_words(text: str) -> set:
    """Összehasonlítható szótövek: kisbetűs, CPL_STEM hosszú előtagok.

    A magyar toldalékok miatt teljes szó-egyezésre nem lehet építeni
    ("kettőzés" / "kettőzését" / "kettőzés-elleni"), ezért a szavakat
    az első CPL_STEM karakterükre csonkoljuk.
    """
    out = set()
    szo = ""
    for ch in text.lower():
        if ch.isalnum():
            szo += ch
        else:
            if len(szo) >= CPL_STEM:
                out.add(szo[:CPL_STEM])
            szo = ""
    if len(szo) >= CPL_STEM:
        out.add(szo[:CPL_STEM])
    return out


def counter_plan(match: Match, config=None) -> dict:
    """Ellenszer-lap: a teendő-rangsor mellé a HOZZÁ TARTOZÓ gyakorlat.

    A teendő-rangsor (priority_findings) megmondja, MI a baj; az
    edzés-fókusz (training_focus) azt, MIT lehet gyakorolni — de a
    kettő eddig két külön lista volt, és az edzőnek fejben kellett
    összekötnie. Ez a réteg elvégzi a párosítást: minden teendőhöz
    megkeresi a legjobban illeszkedő edzés-tételt (közös szótövek a
    címke/ítélet és a gyakorlat címe/indoklása között), és egy
    gyakorlatot csak egyszer használ fel.

    Edzőileg ez a hétfő reggeli lap: probléma → gyakorlat, sorrendben.
    Ahol nincs párja egy teendőnek, az őszinte jelzés: arra a
    problémára még nincs kész edzés-válaszunk, ott a vezetőedző
    döntése kell.

    Visszatérés csapatonként: {"pairs": [{"family", "label",
    "verdict", "drill_title", "drill"}], "matched", "total",
    "verdict"} — a drill_title/drill None, ha nincs illeszkedő
    gyakorlat; a verdict None, ha egyetlen teendő sincs.
    """
    from .training import training_focus

    findings = priority_findings(match, config)
    focus = training_focus(match, config)

    out: dict = {}
    for side in ("home", "away"):
        top = (findings.get(side) or {}).get("top") or []
        items = list(focus.get(side) or [])
        pairs: list = []
        used: set = set()
        for f in top:
            szavak = _cpl_words(f"{f.get('label', '')} "
                                f"{f.get('verdict', '')}")
            best, best_score = None, 0
            for i, it in enumerate(items):
                if i in used:
                    continue
                score = len(szavak & _cpl_words(
                    f"{it.get('title', '')} {it.get('why', '')}"))
                if score > best_score:
                    best, best_score = i, score
            row = {"family": f.get("family"), "label": f.get("label"),
                   "verdict": f.get("verdict"), "drill_title": None,
                   "drill": None}
            if best is not None and best_score >= CPL_MIN_OVERLAP:
                used.add(best)
                row["drill_title"] = items[best].get("title")
                row["drill"] = items[best].get("drill")
            pairs.append(row)
        matched = sum(1 for r in pairs if r["drill"] is not None)
        rec = {"pairs": pairs, "matched": matched, "total": len(pairs),
               "verdict": None}
        if pairs:
            if matched == len(pairs):
                rec["verdict"] = (
                    f"mind a(z) {len(pairs)} teendőhöz van kész "
                    "gyakorlat — a hétfői edzés összeállítható a "
                    "listából")
            elif matched:
                rec["verdict"] = (
                    f"a(z) {len(pairs)} teendőből {matched}-hez van "
                    f"kész gyakorlat; a maradék "
                    f"{len(pairs) - matched} edzői döntést kíván")
            else:
                rec["verdict"] = (
                    f"a(z) {len(pairs)} teendőhöz nincs illeszkedő "
                    "gyakorlat a fókusz-listán — ezekre a vezetőedző "
                    "saját megoldása kell")
        out[side] = rec
    return out
