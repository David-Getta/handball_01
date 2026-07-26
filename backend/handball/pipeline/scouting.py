"""
[Ellenfél-felderítés] — egy meccsből (vagy több meccsből) EGY edzői felderítő
jelentést állít össze egy adott csapatról.

Ez a szoftver "headline" haszna: az edző hetente órákat tölt az ellenfél
meccseinek kézi elemzésével (hogyan védekeznek, mi a tempójuk, ki a kulcs-lövő,
milyen figurákat játszanak). Ezt itt AUTOMATIKUSAN, egy jelentéssé sűrítjük — a
korábbi elemző rétegekre építve (tactics, analytics, event_detection, setplays).

A jelentés EGY csapatra szól (a felderített ellenfélre). Tartalma:
- Támadó identitás: mennyit támadnak szervezetten, tempó, gyors-indítás arány,
- Védekezés: leggyakoribb forma + megoszlás (amikor ez a csapat véd),
- Támadó zónák: súlypont + hotspotok, figurák száma,
- Befejezés: lövések/gólok/hatékonyság,
- Kulcsjátékosok: legaktívabbak + labdabirtoklás-idő,
- Edzői kulcsok: "hogyan játssz ellenük" + erősségek/gyengeségek.

Tiszta adatfeldolgozás (videó nélkül tesztelhető). Több meccs egyesíthető
(combine_reports) — több meccs adja a valós, zajmentes profilt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Optional

from ..models.tracking import Match, Frame, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import (
    TacticsConfig, Phase, possession_team, classify_phase, detect_formation,
    compute_tempo, phase_percentages,
)
from .analytics import compute_team_heatmap, compute_team_summary
from .event_detection import detect_events, EventType
from .setplays import segment_attacks, discover_setplays
from .stats import compute_player_stats

# A labda ekkora (támadó irányú) sebessége (m/s) felett "gyors indítás".
_FASTBREAK_MS = 6.0


@dataclass
class KeyPlayer:
    """Egy kulcsjátékos összegzője a felderített csapatból."""
    track_id: int
    possession_frames: int   # hány frame-en át volt nála a labda (irányító-jel)
    distance_m: float        # megtett táv (aktivitás)
    role: str                # becsült szerep (pl. "irányító", "aktív mezőnyjátékos")


@dataclass
class ScoutingReport:
    """Egy csapat felderítő jelentése (edzői nyelven is)."""
    team: str
    team_name: str
    matches: int = 1
    # Támadó identitás
    attack_share_pct: float = 0.0
    fast_break_pct: float = 0.0
    avg_ball_speed_ms: float = 0.0
    avg_attack_duration_s: float = 0.0
    # Védekezés
    defense_main: str = "—"
    defense_distribution: dict = field(default_factory=dict)
    # Támadó zóna
    attack_centroid_x: float = 0.0
    attack_centroid_y: float = 0.0
    num_figures: int = 0
    attacks: int = 0
    # Befejezés
    shots: int = 0
    goals: int = 0
    turnovers: int = 0
    shot_efficiency_pct: float = 0.0
    # Helyzetminőség: az összes lövésük várható gól-értéke (xG) és a
    # befejezés-eltérés (gól − xG): pozitív = a helyzeteik felett lőnek.
    xg: float = 0.0
    xg_diff: float = 0.0
    # A VÉDEKEZÉSÜK képe (defense.py): mennyi lövést engednek, ebből
    # mennyi volt SZABAD (nem volt védő a lövő 2 m-es körzetében), és
    # zónánként hol lyukas a faluk — ebből jön a "hova játssz" kulcs.
    def_shots_against: int = 0
    def_goals_against: int = 0
    def_free_shots: int = 0
    def_zones: dict = field(default_factory=dict)
    # Engedett lövésminőség: a kapott lövések xG-összege — meccsek közt
    # pontosan összegződik (átlag engedett xG/lövés = xga_sum /
    # def_shots_against). Alacsony = kiszorító védekezés (rossz lövéseket
    # kényszerít), magas = ziccereket enged.
    xga_sum: float = 0.0
    # Átmenet-védekezés: gyors kapott gólok labdavesztés után (%).
    transition_turnovers: int = 0
    transition_goals_against: int = 0
    # Labdaeladások helye: összes eladás és ebből a TÁMADÓ harmadban
    # elkövetettek (darabszámok, hogy meccsek közt összegezhetők legyenek).
    turnover_total: int = 0
    turnover_front: int = 0
    # Labdabirtoklás-arány (a felderített csapaté, %).
    possession_pct: float = 0.0
    # Gólpassz-vezér: a legtöbb gólpasszt adó játékos (track_id, db).
    top_assist_id: int | None = None
    top_assist_count: int = 0
    # Passz-hálózat: a leggyakoribb passz-párok [{"from","to","passes"}]
    # (meccsek közt párokként összegezhető) és az összes passz.
    pass_pairs: list = field(default_factory=list)
    pass_total: int = 0
    # Hajrá-mérleg: szoros állásról induló hajrákban (utolsó 5 perc)
    # dobott/kapott gólok és az ilyen hajrák száma (meccsek közt összegződik).
    clutch_goals_for: int = 0
    clutch_goals_against: int = 0
    clutch_matches: int = 0
    # A leghosszabb gólcsendjük (mp) — meccsek közt a maximum marad.
    drought_longest_s: float = 0.0
    # Blokkolt lövéseik (a felderített csapat védőinek blokkjai) — összegződik.
    blocks: int = 0
    # Elhúzódó (35 mp+) támadásaik darabszámai — meccsek közt összegződik.
    slow_attacks_total: int = 0
    slow_attacks_slow: int = 0
    # Félidőnkénti gólmérleg (csak felismert szünetű meccsekből, összegződik).
    fh_goals_for: int = 0
    fh_goals_against: int = 0
    sh_goals_for: int = 0
    sh_goals_against: int = 0
    # Lövés-erő: mért lövéseik száma és sebesség-összege (km/h) — az átlag
    # a darabszámokból mindig pontosan visszaszámolható több meccsre is.
    shot_speed_n: int = 0
    shot_speed_sum_kmh: float = 0.0
    shot_speed_max_kmh: float = 0.0
    # Lövőerő-esés (fáradás-jel): a mért lövések félidőnkénti darabszáma és
    # sebesség-összege (km/h) — meccsek közt pontosan összegződik, az 1./2.
    # félidei átlag és az esés (%) bármikor visszaszámolható.
    ssf_fh_n: int = 0
    ssf_fh_sum_kmh: float = 0.0
    ssf_sh_n: int = 0
    ssf_sh_sum_kmh: float = 0.0
    # Nyomás alatti befejezés: szabad/fedezett lövéseik és góljaik.
    fin_free_shots: int = 0
    fin_free_goals: int = 0
    fin_cov_shots: int = 0
    fin_cov_goals: int = 0
    # Támadás-oldal megoszlás: kockaszámok sávonként (összegződik).
    side_frames: dict = field(default_factory=dict)
    # Válasz-gólok: megválaszolt kapott gólok száma és összes válasz-idő
    # (mp) — az átlag darabszámból pontosan visszaszámolható.
    response_n: int = 0
    response_sum_s: float = 0.0
    # Védőforma elleni hatékonyságuk: {forma: {"shots","goals"}} —
    # formánként összegződik meccsek közt.
    vs_formation: dict = field(default_factory=dict)
    # Támadás-hossz szerinti hatékonyságuk: {vödör: {"attacks","goals"}}.
    duration_eff: dict = field(default_factory=dict)
    # Védekezési nyomás: a labdáshoz legközelebbi védő átlag-távolsága (m).
    defensive_pressure_m: float = 0.0
    # Irányító-függés (playmaker.py): a fő szervezőjük, és mennyit esik a
    # lövésig jutásuk, ha ő nincs a labdánál ("fogd meg" kulcs).
    playmaker_id: int | None = None
    playmaker_involvement_pct: float = 0.0
    playmaker_drop: float | None = None
    playmaker_dependency: str | None = None
    # Csere-minták (substitutions.py): hány cserehullámot futnak, ebből
    # hány jött HÁTRÁNYBAN, és mi a cserék utáni 90 mp gól-mérlege.
    sub_rotations: int = 0
    sub_trailing: int = 0
    sub_after_for: int = 0
    sub_after_against: int = 0
    # Lövési zónák: zóna -> {"shots": n, "goals": n} — HONNAN lőnek és honnan
    # eredményesek (balszél / beálló / átlövés bal-közép-jobb / jobbszél).
    shot_zones: dict = field(default_factory=dict)
    # A FELDERÍTETT csapat kapusa (a kapus-jelölésből, ha van):
    # kapott kapura tartó lövések / védések / kapott gólok zóna-bontással.
    gk_on_target: int = 0
    gk_saves: int = 0
    # A kapusuk bravúr-védései: fogott nagy helyzetek (xG >= 0,5, save).
    gk_big_saves: int = 0
    # Hárított xG: a fogott lövések helyzet-értékének összege — a nehéz
    # védések súlyozott mutatója; meccsek közt összegződik.
    gk_xg_saved: float = 0.0
    # Megmentett gólok (GSAx): kapura tartó xG mínusz kapott gól —
    # negatív, ha a kapusuk a vártnál többet kap; összegződik.
    gk_xg_prevented: float = 0.0
    # Ziccer-mérlegük: nagy xG-jű helyzeteik száma és a gól nélkül maradtak
    # — meccsek közt összegződik, az arány mindig visszaszámolható.
    big_total: int = 0
    big_missed: int = 0
    # Kapus-indításuk: mért indítások, összidő (mp) és a gyorsak száma
    # (védés után 6 mp-en belül a felezőn) — meccsek közt összegződik.
    gk_outlets: int = 0
    gk_outlet_sum_s: float = 0.0
    gk_outlet_fast: int = 0
    gk_conceded_zones: dict = field(default_factory=dict)
    # Minden kapura tartó lövés zóna-bontása (védés is) — ebből és a
    # kapott gólok zónáiból zónánkénti védés-hatékonyság, így a kapus
    # LEGGYENGÉBB sarka is látszik (nemcsak hova esett a legtöbb gól).
    gk_on_target_zones: dict = field(default_factory=dict)
    # 7 a 6 elleni (lehozott kapusos) játék összideje másodpercben.
    empty_net_s: float = 0.0
    # Üres kapura kapott góljaik (7 a 6 közben) — meccsek közt összegződik.
    empty_net_conceded: int = 0
    # A 7 a 6 időzítése: szakaszaik száma és ebből hány indult
    # hátrányban / a hajrában — meccsek közt összegződik.
    en_windows: int = 0
    en_trailing: int = 0
    en_endgame: int = 0
    # Tempó-profil: támadásaik száma és a mért játékpercek — az
    # átlagos támadás/perc több meccsre pontosan visszaszámolható.
    pace_attacks: int = 0
    pace_minutes: float = 0.0
    # Támadás-eredet: {eredet: {"attacks", "goals"}} — honnan indulnak
    # (középkezdés/kidobás/labdaszerzés); eredetenként összegződik.
    attack_origins: dict = field(default_factory=dict)
    # Visszarendeződés: mért átmenetek, összidő és a lassúak (5 mp+)
    # száma — az átlag több meccsre pontosan visszaszámolható.
    rec_transitions: int = 0
    rec_sum_s: float = 0.0
    rec_slow: int = 0
    # Becsült posztok: {track_id: poszt} — meccsek közt az első érdemi
    # becslés marad (a felállás ritkán változik).
    positions: dict = field(default_factory=dict)
    # Szélső-függés: a becsült szélsők góljai és az azonosított lövőktől
    # jött összes gól — meccsek közt összegződik.
    wing_goals: int = 0
    wing_total_goals: int = 0
    # Gól-eloszlás posztonként: {poszt: gól} — meccsek közt összegződik.
    post_goals: dict = field(default_factory=dict)
    # Lövő-szokások: [{"player_id", "zone", "shots"}] — honnan lőnek a
    # játékosaik; (játékos, zóna) párokként meccsek közt összegezhető.
    shooter_zones: list = field(default_factory=list)
    # A lövőik fáradása: [{"player_id", "drop_sum_pct", "n"}] — a 2.
    # félidei tempó-esések összege és darabszáma (átlag visszaszámolható).
    shooter_fades: list = field(default_factory=list)
    # Gólpassz-párok: [{"from", "to", "goals"}] — ki kinek készíti elő a
    # góljaikat; párokként meccsek közt összegezhető.
    assist_pairs: list = field(default_factory=list)
    # Befejezés-többlet lövőnként: [{"player_id", "diff"}] — gól − xG;
    # játékosonként meccsek közt összegezhető.
    shooter_overperf: list = field(default_factory=list)
    # Blokkolóik: [{"player_id", "blocks"}] — ki tartja a falukat;
    # játékosonként meccsek közt összegezhető.
    blockers: list = field(default_factory=list)
    # A kapus-indításaik célpontjai: [{"player_id", "n"}] — kinek megy
    # az első hosszú passz; játékosonként meccsek közt összegezhető.
    gk_outlet_targets: list = field(default_factory=list)
    # A lerohanásaik befejezői: [{"player_id", "goals"}] — ki futja ki a
    # kontrákat; játékosonként meccsek közt összegezhető.
    fb_finishers: list = field(default_factory=list)
    # A hetes-dobóik: [{"player_id", "attempts", "goals"}] — ki áll oda a
    # hétméteresekhez és milyen mérleggel; meccsek közt összegezhető.
    seven_takers: list = field(default_factory=list)
    # A hetes-kiharcolóik: [{"player_id", "earned"}] — kit rántanak le;
    # játékosonként meccsek közt összegezhető.
    seven_earners: list = field(default_factory=list)
    # A kiállítás-kiharcolóik: [{"player_id", "earned"}] — ki hozza a
    # 2 perceket; játékosonként meccsek közt összegezhető.
    susp_earners: list = field(default_factory=list)
    # A kiülőik: [{"player_id", "suspensions"}] — ki szedi össze a
    # 2 perceket; játékosonként meccsek közt összegezhető.
    susp_players: list = field(default_factory=list)
    # Emberfogóik: védőnkénti őrzés-kockák + táv-összeg
    # [{"player_id", "frames", "dist_sum"}] — darabszám-alapú, meccsek
    # közt pontosan összegezhető; átlagtáv = dist_sum / frames.
    markers: list = field(default_factory=list)
    # Beálló-terhelés: támadások / beállós támadások / góljaik / beálló
    # nélküli gólok — darabszámok, meccsek közt pontosan összegződnek.
    pivot_total_attacks: int = 0
    pivot_attacks: int = 0
    pivot_goals: int = 0
    pivot_other_goals: int = 0
    # Betörés-folyosóik: {sáv: {"entries", "goals"}} — hol lépnek be a
    # 9 m-en belülre; darabszámok, meccsek közt pontosan összegződnek.
    break_entries: int = 0
    break_lanes: dict = field(default_factory=dict)
    # Passz-láncaik: támadások / összes passz / vödrönkénti mérleg
    # {vödör: {"attacks", "goals"}} — darabszámok, pontosan összegződnek.
    pass_attacks: int = 0
    pass_total: int = 0
    pass_buckets: dict = field(default_factory=dict)
    # Rotációjuk: bevetett + alapember összegek és a mérhető meccsek
    # száma — átlag = összeg / meccsek, pontosan összegződik.
    rotation_used_sum: int = 0
    rotation_regulars_sum: int = 0
    rotation_matches: int = 0
    # Labdaszerzőik: [{"player_id", "steals"}] — ki szerzi a labdákat;
    # játékosonként meccsek közt pontosan összegezhető.
    ball_winners: list = field(default_factory=list)
    # Labdaeladók: [{"player_id", "losses"}] — kinek a leggyengébb a
    # labdabiztonsága; (játékos) párokként meccsek közt összegződik.
    turnover_players: list = field(default_factory=list)
    # Hajrá-emberek: [{"player_id", "goals"}] — ki szerzi a gólokat a meccs
    # végén; meccsek közt összegződik.
    clutch_scorers: list = field(default_factory=list)
    # Gól-koncentráció: lövőnkénti gólszámok [{player_id, goals}] —
    # meccsek közt pontosan összegződik; a fő gólszerző részesedése
    # (gólfüggés) a teljes mintából számolható vissza.
    scorer_goals: list = field(default_factory=list)
    # Támogatás-távolság (izoláció-jel): a mért labdás kockák száma, a
    # legközelebbi társ táv-összege (m) és az izolált kockák száma —
    # meccsek közt pontosan összegződik (átlag = összeg / kockák,
    # izolált-arány = izolált / kockák).
    sup_frames: int = 0
    sup_sum_m: float = 0.0
    sup_iso: int = 0
    # Területi fölény (field tilt): birtokos kockák + ebből az ellenfél
    # térfelén lévők — meccsek közt pontosan összegződik (tilt = opp/összes).
    tilt_frames: int = 0
    tilt_opp: int = 0
    # Védelmi tömörség (fal-szélesség): a felállt védekezés y-terjedelmének
    # összege + mért kockák — meccsek közt pontosan összegződik (átlag =
    # összeg / kockák). Tömör fal = szélek nyitva; széthúzott = közép nyitva.
    defw_sum_m: float = 0.0
    defw_frames: int = 0
    # Passz-tempó (labdajáratás): passzok + mért birtoklás-idő (mp) —
    # meccsek közt pontosan összegződik (passz/perc = 60·passz/idő).
    pt_passes: int = 0
    pt_poss_s: float = 0.0
    # Falba lövés (támadó-oldali blokk-arány): az ellenfél blokkjai ellenük
    # + összes lövés-kísérlet — meccsek közt pontosan összegződik
    # (arány = blk_for / blk_attempts).
    blk_for: int = 0
    blk_attempts: int = 0
    # Szerzés-magasság (letámadás-jel): összes labdaszerzés + ebből az elöl
    # (a saját támadó térfélen) történtek — meccsek közt pontosan
    # összegződik (elöl-arány = high / steals).
    steal_n: int = 0
    steal_high: int = 0
    # Passz-hossz profil: mért passzok + hossz-összeg (m) + hosszú (10 m+)
    # passzok — meccsek közt pontosan összegződik (átlag = összeg / darab,
    # hosszú-arány = hosszú / darab).
    plen_n: int = 0
    plen_sum_m: float = 0.0
    plen_long: int = 0
    # Lövés-időzítés: lövéssel záruló támadások + lövésig-idő összege (mp)
    # + korai (8 mp-en belüli) lövések — meccsek közt pontosan összegződik
    # (átlag = összeg / darab, korai-arány = korai / darab).
    shtim_n: int = 0
    shtim_sum_s: float = 0.0
    shtim_early: int = 0
    # Védekezés-fellazulás: a védekezési nyomás félidőnkénti táv-összege és
    # kockaszáma — meccsek közt pontosan összegződik (félidei átlag =
    # összeg / kockák; lazulás = 2. félidei átlag − 1. félidei átlag).
    prf_fh_sum_m: float = 0.0
    prf_fh_n: int = 0
    prf_sh_sum_m: float = 0.0
    prf_sh_n: int = 0
    # Időkérés-mérleg: felismert időkéréseik + ebből a sorozatot megtörő
    # (broke) és a fordulatot nem hozó (failed) — meccsek közt összegződik.
    to_n: int = 0
    to_broke: int = 0
    to_failed: int = 0
    # Labdabiztonság-esés: félidőnkénti eladások + mért birtoklás-idő (mp)
    # — meccsek közt pontosan összegződik (ütem = 60·eladás/idő).
    tof_fh_to: int = 0
    tof_fh_poss_s: float = 0.0
    tof_sh_to: int = 0
    tof_sh_poss_s: float = 0.0
    # Kapus-forma félidőnként: félidőnkénti kapura tartó lövések + védések
    # — meccsek közt pontosan összegződik (védés% félidőnként visszaszámolható).
    gsf_fh_faced: int = 0
    gsf_fh_saves: int = 0
    gsf_sh_faced: int = 0
    gsf_sh_saves: int = 0
    # Előny-őrzés: hány meccsen léptek el 3+ góllal, abból hányszor
    # engedték el (a végén nem nyertek) — darabszámok, összegződnek.
    lp_led: int = 0
    lp_blown: int = 0
    lp_biggest: int = 0
    # Fegyelem-esés: kiállítások félidőnként (csak félidő-jeles meccsről)
    # — darabszámok, összegződnek.
    disc_fh_susp: int = 0
    disc_sh_susp: int = 0
    # Gól utáni elalvás: saját gólok + fél percen belül visszakapott
    # válasz-gólok — darabszámok, összegződnek.
    pgl_goals: int = 0
    pgl_quick: int = 0
    # Szoros meccs-mérleg: 1-2 gólos meccsek kimenetele — darabszámok,
    # összegződnek.
    cg_wins: int = 0
    cg_losses: int = 0
    cg_draws: int = 0
    # Hetes-védés: a kapusukra dobott kapura tartó hetesek + fogások —
    # darabszámok, összegződnek.
    s7d_faced: int = 0
    s7d_saved: int = 0
    # Kapuscsere-hatás: cserék + csere előtti/utáni kapura tartó lövések
    # és védések — darabszámok, összegződnek.
    gkc_changes: int = 0
    gkc_pre_faced: int = 0
    gkc_pre_saves: int = 0
    gkc_post_faced: int = 0
    gkc_post_saves: int = 0
    # Kihagyott ziccer ára: kihagyások + fél percen belül büntetett
    # kihagyások — darabszámok, összegződnek.
    bcp_misses: int = 0
    bcp_punished: int = 0
    # Tempó-esés: félidőnkénti támadás-darab + mért perc — meccsek közt
    # pontosan összegződik (ütem = darab / perc).
    tpf_fh_attacks: int = 0
    tpf_fh_min: float = 0.0
    tpf_sh_attacks: int = 0
    tpf_sh_min: float = 0.0
    # Félidei hátrányból fordítás: hátrányos félidők + kimenetelük —
    # darabszámok, összegződnek.
    htc_behind: int = 0
    htc_turned: int = 0
    htc_saved: int = 0
    # Holtpont-mérleg: góllal lezárt döntetlen-állások + az elvitt
    # holtpontok — darabszámok, összegződnek.
    pb_ties: int = 0
    pb_won: int = 0
    # Sorozat-törés: futott/elszenvedett 3+ gólos sorozatok és
    # összhosszuk — darabszámok, összegződnek.
    rn_made: int = 0
    rn_made_goals: int = 0
    rn_suffered: int = 0
    rn_suffered_goals: int = 0
    # Bravúr utáni lendület: nagy védések + gyorsan góllá váltott
    # bravúrok — darabszámok, összegződnek.
    bsm_saves: int = 0
    bsm_sparked: int = 0
    # Befejezés-esés: félidőnkénti lövés-kísérletek + gólok —
    # darabszámok, összegződnek.
    ff_fh_shots: int = 0
    ff_fh_goals: int = 0
    ff_sh_shots: int = 0
    ff_sh_goals: int = 0
    # Célzás-pontosság: lövés-kísérletek + kaput érő lövések —
    # darabszámok, összegződnek.
    ac_attempts: int = 0
    ac_on_target: int = 0
    # Oldal-részrehajlás: lövések a támadás bal/közép/jobb sávjából —
    # darabszámok, összegződnek.
    sb_left: int = 0
    sb_center: int = 0
    sb_right: int = 0
    # Ritmus-egyhangúság: támadás-darab + hossz-összeg + négyzetösszeg
    # — összegekből az átlag/szórás meccsek közt visszaszámolható.
    ar_n: int = 0
    ar_sum_s: float = 0.0
    ar_sumsq_s: float = 0.0
    # Lövő-koncentráció: azonosított lövőjű lövések + ebből a meccs fő
    # lövőjének darabjai — darabszámok, meccsek közt összegződnek
    # (részarány = top / összes).
    sc_shots: int = 0
    sc_top_shots: int = 0
    # Kapus-gyengeoldal: BEKAPOTT gólok kapu-oldal szerint (a kapus
    # szemszögéből) — darabszámok, meccsek közt összegződnek.
    gw_bal: int = 0
    gw_kozep: int = 0
    gw_jobb: int = 0
    # Eladás-időzítés: időzíthető eladások + ebből a koraiak (a
    # birtoklás első másodperceiben) — darabszámok, összegződnek.
    tt_timed: int = 0
    tt_early: int = 0
    # Pressz-tűrés: nyomott/szabad passzok és eladások — darabszámok,
    # meccsek közt összegződnek (eladás-arány = to / (passz + to)).
    ps_press_passes: int = 0
    ps_press_to: int = 0
    ps_free_passes: int = 0
    ps_free_to: int = 0
    # Lepattanó-fal: az ellenfél lepattanó-lehetőségei ellenünk + a
    # visszaengedett második rohamok és góljaik — darabszámok,
    # meccsek közt összegződnek (arány = allowed / opp_misses).
    sca_opp_misses: int = 0
    sca_allowed: int = 0
    sca_goals: int = 0
    # Asszist-függés: gólok + ebből a gólpasszosak — darabszámok,
    # meccsek közt összegződnek (arány = assisted / goals).
    ad_goals: int = 0
    ad_assisted: int = 0
    # Területi-fölény-esés: félidőnkénti birtokos kockák + ebből az
    # ellenfél térfelén lévők — darabszámok, meccsek közt pontosan
    # összegződnek (tilt = opp / frames félidőnként).
    tf_fh_frames: int = 0
    tf_fh_opp: int = 0
    tf_sh_frames: int = 0
    tf_sh_opp: int = 0
    # Kapus-indítás hossza: kapus-passzok + ebből a hosszúak (15 m+)
    # — darabszámok, meccsek közt összegződnek (arány = long/outlets).
    gko_outlets: int = 0
    gko_long: int = 0
    # Eladás-büntetés: eladások + ebből a fél percen belül góllal
    # büntetettek — darabszámok, meccsek közt összegződnek.
    tpu_turnovers: int = 0
    tpu_punished: int = 0
    # Engedett-oldal: kapott lövések a fal oldala szerint (bal a fal
    # bal oldala) — darabszámok, meccsek közt összegződnek.
    csb_left: int = 0
    csb_center: int = 0
    csb_right: int = 0
    # Gólcsend-anatómia: a leghosszabb gólcsendek össz-másodperce +
    # a bennük leadott lövések — összegek, meccsek közt összeadódnak
    # (ütem = shots / (s/60)).
    da_drought_s: float = 0.0
    da_shots: int = 0
    # Fal-rés: mért falkockák + ebből a réses (3,5 m+ szomszéd-táv)
    # kockák — darabszámok, meccsek közt összegződnek.
    wg_frames: int = 0
    wg_wide: int = 0
    # Támadó-mozgás: szervezett támadásban megtett út + mért
    # játékos-idő — összegek, meccsek közt összeadódnak
    # (átlagsebesség = dist / time).
    am_dist_m: float = 0.0
    am_time_s: float = 0.0
    # Indítás-biztonság: kapus-indítások + ebből az ellenfélnél
    # kikötők — darabszámok, meccsek közt összegződnek.
    gos_outlets: int = 0
    gos_lost: int = 0
    # Beálló-védekezés: az ellenük vezetett beállós és beálló nélküli
    # támadások + a belőlük esett gólok — darabszámok, meccsek közt
    # összegződnek (gólarány = goals / attacks külön-külön).
    pd_pivot_attacks: int = 0
    pd_pivot_goals: int = 0
    pd_other_attacks: int = 0
    pd_other_goals: int = 0
    # Elsütés-idő: mérhető lövések + ebből a gyors (0,6 mp-en belüli)
    # elsütések — darabszámok, meccsek közt összegződnek.
    sr_shots: int = 0
    sr_quick: int = 0
    # Középkezdés-tempó: mérhető újraindítások kapott gól után + a
    # gyorsak (12 mp-en belüli térfél-átlépés) + össz-idő — összegek,
    # meccsek közt összeadódnak.
    rs_restarts: int = 0
    rs_fast: int = 0
    rs_sum_s: float = 0.0
    # Előkészítő-függés: gólpasszos gólok + ebből a fő előkészítőé —
    # darabszámok, meccsek közt összegződnek (a top meccsenkénti fő
    # előkészítő összege — közelítés, mint a lövő-koncentrációnál).
    ac_assists: int = 0
    ac_top_assists: int = 0
    # Gól-előkészítés hossza: gólok + ebből a direkt (0-2 passzos) és
    # a kombinatív (5+ passzos) — darabszámok, meccsek közt
    # összegződnek.
    gb_goals: int = 0
    gb_short: int = 0
    gb_long: int = 0
    # Lerohanás-védés: a kapusuk kaput eltaláló lövései fázisonként
    # (gyorsindításos / rendezett) + védései — darabszámok, meccsek
    # közt összegződnek.
    gkb_fast_faced: int = 0
    gkb_fast_saves: int = 0
    gkb_set_faced: int = 0
    gkb_set_saves: int = 0
    # Oldalváltás: támadó-térfeles passzok + ebből a keresztpasszok
    # (10 m+ oldalirány) — darabszámok, meccsek közt összegződnek.
    ssw_passes: int = 0
    ssw_switches: int = 0
    # Elzárás-használat: őrzött lövések + ebből az elzárásból leadott
    # (társ az őrző 2 m-es körzetében) — darabszámok, meccsek közt
    # összegződnek.
    scu_shots: int = 0
    scu_screened: int = 0
    # Elzárás-védekezés: az ellenük leadott elzárásos és elzárás
    # nélküli őrzött lövések + a belőlük esett gólok — darabszámok,
    # meccsek közt összegződnek (gólarány külön-külön).
    scd_screened_shots: int = 0
    scd_screened_goals: int = 0
    scd_open_shots: int = 0
    scd_open_goals: int = 0
    # Passz-kockázat: hosszú (10 m+) és rövid passz-kísérletek + a
    # belőlük lett eladások — darabszámok, meccsek közt összegződnek
    # (eladás-arány sávonként külön).
    prk_long_tries: int = 0
    prk_long_to: int = 0
    prk_short_tries: int = 0
    prk_short_to: int = 0
    # Hajrá-lövésválasztás: a hajrá előtti és a hajrá-lövések száma +
    # xG-összege — darabszámok és összegek, meccsek közt pontosan
    # összegződnek (átlag = xg / shots fázisonként).
    # Ellen-press: az eladásaik száma + a 6 mp-en belül visszaszerzett
    # labdák száma — darabszámok, meccsek közt összegződnek (arány =
    # regained / turnovers).
    cpr_turnovers: int = 0
    cpr_regained: int = 0
    csq_early_shots: int = 0
    csq_early_xg: float = 0.0
    csq_clutch_shots: int = 0
    csq_clutch_xg: float = 0.0
    # Kapus-kimozdulás: táv-összeg + kockák (átlag = összeg / kockák,
    # meccsek közt pontosan összegződik).
    gk_depth_sum_m: float = 0.0
    gk_depth_frames: int = 0
    # Átmenet-támadásuk: szerzések + gyors gólok — darabszámok, meccsek
    # közt pontosan összegződnek (konverzió = gyors gól / szerzés).
    trans_steals: int = 0
    trans_quick_goals: int = 0
    # Lövés-távolság sávok — lövés/gól darabszámok, meccsek közt pontosan
    # összegződnek (gólarány sávonként = gól / lövés a teljes mintán).
    sr_close_shots: int = 0
    sr_close_goals: int = 0
    sr_mid_shots: int = 0
    sr_mid_goals: int = 0
    sr_far_shots: int = 0
    sr_far_goals: int = 0
    # Kapusuk védése lövés-távolság szerint — kaputra érkezett lövés/védés
    # darabszámok, meccsek közt pontosan összegződnek (védési arány = védés
    # / kaputra érkezett lövés az adott sávban). A gyenge sáv a támadásnak
    # fogódzó: onnan érdemes lőni.
    gk_close_faced: int = 0
    gk_close_saves: int = 0
    gk_mid_faced: int = 0
    gk_mid_saves: int = 0
    gk_far_faced: int = 0
    gk_far_saves: int = 0
    # Kapu-sarok: hova mennek a góljaik (bal/közép/jobb, a lövő szemszögéből)
    # — gólszámok, meccsek közt pontosan összegződnek. Kiszámítható befejezés
    # esetén a kapus felkészülhet rá.
    place_bal: int = 0
    place_kozep: int = 0
    place_jobb: int = 0
    # Szélső-befejezés — a szélső (éles) szögből leadott lövések/góljaik
    # darabszáma, meccsek közt pontosan összegződnek (szélső-gólarány =
    # gól / szélső-lövés). Erős szélső széthúzza a védelmet. (Külön a fenti
    # wing_goals "szélső-függéstől": ez a szög szerinti BEFEJEZÉS-minőség.)
    wing_fin_shots: int = 0
    wing_fin_goals: int = 0
    # Passz-irány — előre-passzok és összes mért passz, plusz az
    # előrehaladás-összeg; meccsek közt pontosan összegződnek (előre-arány =
    # előre / összes; átlag-előrehaladás = összeg / összes).
    pdir_forward: int = 0
    pdir_passes: int = 0
    pdir_prog_sum: float = 0.0
    # Gólpassz-forrás: honnan készítik elő a gólokat (szél/közép/hátsó) —
    # gólpassz-darabszámok, meccsek közt pontosan összegződnek.
    asrc_szel: int = 0
    asrc_kozep: int = 0
    asrc_hatso: int = 0
    # Második roham / lepattanó-visszaszerzés: a nem gólos lövések (misses),
    # az ezek után megnyert második rohamok (second_chances) és ezekből a
    # gólok (second_goals) — darabszámok, meccsek közt pontosan összegződnek
    # (visszaszerzési arány = second / misses; gólarány = goals / second).
    sc_misses: int = 0
    sc_second: int = 0
    sc_goals: int = 0
    # Védekezési vonal magassága — a felállt védekezés mélység-összege és a
    # mért kockák száma (átlag = összeg / kockák), meccsek közt pontosan
    # összegződik. Magas fal = felfutó/agresszív, alacsony = mély/passzív.
    defline_sum_m: float = 0.0
    defline_frames: int = 0
    # Hány kiállítást szedett össze a csapat (felismert emberhátrányok)
    # — meccsek közt összegződik, a trendben meccsenkénti átlag.
    suspensions: int = 0
    # A szünet utáni kezdés (a 2. félidő első 5 perce): dobott/kapott
    # gólok + hány meccsen volt mérhető félidő-jel — összegződik.
    restart_for: int = 0
    restart_against: int = 0
    restart_matches: int = 0
    # A félidő-zárás (az 1. félidő utolsó 5 perce): dobott/kapott gólok +
    # hány meccsen volt mérhető félidő-jel — összegződik.
    fhc_for: int = 0
    fhc_against: int = 0
    fhc_matches: int = 0
    # Kezdés-profil (a meccs nyitánya, gól-sorrendből): hányszor szerezte a
    # csapat a meccs első gólját, hány gólos meccsen mérhető ez, és a korai
    # ablak (első 6 gól) dobott/kapott gólmérlege — meccsek közt pontosan
    # összegződik (nyitógól-arány = first_yes / first_matches).
    open_first_yes: int = 0
    open_first_matches: int = 0
    open_for: int = 0
    open_against: int = 0
    # Támadás-szélesség: mérhető kockák + összterjedelem — meccsek
    # közt összegződik, az átlag visszaszámolható.
    width_frames: int = 0
    width_sum_m: float = 0.0
    # A legjobb meccs-figurájuk: a leggólerősebb visszatérő minta
    # mérlege (meccsek közt a legerősebb marad — a címkék meccsenként
    # függetlenek, ezért nem összegzünk).
    best_fig_attacks: int = 0
    best_fig_goals: int = 0
    # Előny-kezelés: támadás-darab + összhossz állás szerint (vezetve /
    # hátrányban) — meccsek közt összegződik, az átlag visszaszámolható.
    lead_attacks: int = 0
    lead_sum_s: float = 0.0
    trail_attacks: int = 0
    trail_sum_s: float = 0.0
    # Emberelőny-mutatók (kiállítások alatt): lövés/gól előnyben, és a
    # HÁTRÁNYBAN kapott gólok — a "kerüld a kiállítást ellenük" jelhez.
    pp_shots: int = 0
    pp_goals: int = 0
    sh_conceded: int = 0
    sh_seconds: float = 0.0
    # Támadás-mix: {típus: százalék} — lerohanás / gyors indítás / felállt / 7a6.
    attack_mix: dict = field(default_factory=dict)
    # Támadás-hatékonyság típusonként: {típus: {attacks, shots, goals,
    # shot_pct, goal_pct}} — melyik támadásmódjuk mennyire eredményes.
    attack_efficiency: dict = field(default_factory=dict)
    # Védekezés-váltások: [{"t","from","to","margin"}] — mikor és milyen
    # állásnál váltottak formát (margin < 0: hátrányban voltak).
    defense_switches: list = field(default_factory=list)
    # Kulcsjátékosok + edzői kulcsok
    key_players: list = field(default_factory=list)
    strengths: list = field(default_factory=list)
    weaknesses: list = field(default_factory=list)
    keys_to_game: list = field(default_factory=list)


def _other(team: Team) -> Team:
    return Team.AWAY if team == Team.HOME else Team.HOME


def _team_of_track(match: Match) -> dict:
    """track_id -> a leggyakrabban látott csapata (a csapat-hovatartozás stabil jele)."""
    tally: dict[int, dict[Team, int]] = {}
    for f in match.frames:
        for p in f.players:
            tally.setdefault(p.track_id, {}).setdefault(p.team, 0)
            tally[p.track_id][p.team] += 1
    return {tid: max(counts.items(), key=lambda kv: kv[1])[0] for tid, counts in tally.items()}


def _fast_break_pct(match: Match, team: Team, config: TacticsConfig) -> float:
    """A csapat labdás pillanatai közül mennyi a GYORS, támadó irányú indítás (%)."""
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    target_x = config.attacks_toward_x(team)
    sign = 1.0 if target_x > COURT_LENGTH_M / 2.0 else -1.0
    poss_frames = 0
    fast = 0
    prev = None
    for f in match.frames:
        poss = possession_team(f, config)
        if poss == team and f.ball is not None:
            poss_frames += 1
            if prev is not None:
                speed = (f.ball.x - prev) * sign * fps
                if speed >= _FASTBREAK_MS:
                    fast += 1
        prev = f.ball.x if f.ball is not None else None
    return 100.0 * fast / poss_frames if poss_frames else 0.0


def _defense_distribution(match: Match, team: Team, config: TacticsConfig) -> dict:
    """A csapat védekezési formáinak megoszlása (%), amikor ÉPP VÉDEKEZIK."""
    tally: dict[str, int] = {}
    for f in match.frames:
        phase = classify_phase(f, config)
        # a csapat akkor véd, ha az ELLENFELE támad
        defends = (phase == Phase.HOME_ATTACK and team == Team.AWAY) or \
                  (phase == Phase.AWAY_ATTACK and team == Team.HOME)
        if not defends:
            continue
        label = detect_formation(f, team, config).label
        tally[label] = tally.get(label, 0) + 1
    total = sum(tally.values())
    if not total:
        return {}
    return {k: round(100.0 * v / total, 1) for k, v in sorted(tally.items(), key=lambda kv: -kv[1])}


def _shot_zone(bx: float, by: float, attacked_goal_x: float) -> str:
    """A lövés helyének kézilabdás zóna-címkéje a TÁMADÓ szemszögéből.

    A bal/jobb oldalt a támadás irányához igazítjuk (a +x kapura támadva a
    balszél az alacsony y; a -x kapura fordítva). Zónák:
    - balszél / jobbszél: a kapuhoz közel, a szélső sávban,
    - beálló (6 m): közel, középen,
    - átlövés bal/közép/jobb: távolabbról (~9 m-től).
    """
    dist = abs(bx - attacked_goal_x)
    # Bal/jobb a támadó szemszögéből: +x kapu felé az alacsony y a BAL oldal.
    left = by < COURT_WIDTH_M * 0.30
    right = by > COURT_WIDTH_M * 0.70
    if attacked_goal_x < COURT_LENGTH_M / 2.0:
        left, right = right, left  # a -x kapura támadva tükrözve
    if dist <= 9.0 and (left or right):
        return "balszél" if left else "jobbszél"
    if dist <= 7.5:
        return "beálló (6 m)"
    if left:
        return "átlövés bal"
    if right:
        return "átlövés jobb"
    return "átlövés közép"


def _shot_zones(match: Match, team: Team, config: TacticsConfig) -> dict:
    """Zóna -> {"shots": n, "goals": n} a csapat lövéseiből (eseményekből)."""
    frames_by_t = {f.t: f for f in match.frames}
    zones: dict[str, dict] = {}
    goal_x = config.attacks_toward_x(team)
    for e in detect_events(match, config):
        if e.team != team or e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        frame = frames_by_t.get(e.t)
        if frame is None or frame.ball is None:
            continue
        z = _shot_zone(frame.ball.x, frame.ball.y, goal_x)
        rec = zones.setdefault(z, {"shots": 0, "goals": 0})
        rec["shots"] += 1
        if e.type == EventType.GOAL:
            rec["goals"] += 1
    # A leggyakoribb zóna elöl (a jelentésben így olvasható).
    return dict(sorted(zones.items(), key=lambda kv: -kv[1]["shots"]))


def formation_switch_profile(match: Match, team: Team,
                             config: Optional[TacticsConfig] = None) -> list[dict]:
    """Védekezés-váltások: MIKOR váltott a csapat formát, és milyen állásnál.

    15 mp-es ablakonként a többségi védekezési forma (csak érdemi, legalább
    ~1 mp-nyi védekezéssel rendelkező ablakok); két szomszédos ablak eltérő
    formája = váltás. A váltás pillanatához az AKTUÁLIS gólkülönbséget is
    kiszámoljuk (a felismert gólokból) — ebből látszik a minta: pl.
    "hátrányban 5-1-re váltanak".

    Visszatérés: [{"t", "from", "to", "margin"}] — margin < 0: a csapat
    épp hátrányban volt a váltáskor.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = max(1, round(15.0 * fps))

    goals = [(e.t, e.team) for e in detect_events(match, config)
             if e.type == EventType.GOAL]

    def margin_at(t: int) -> int:
        own = sum(1 for gt, gteam in goals if gt <= t and gteam == team)
        opp = sum(1 for gt, gteam in goals if gt <= t and gteam != team)
        return own - opp

    timeline: list[tuple[int, str]] = []
    frames = match.frames
    for w0 in range(0, len(frames), win):
        tally: dict[str, int] = {}
        for f in frames[w0:w0 + win]:
            phase = classify_phase(f, config)
            defends = (phase == Phase.HOME_ATTACK and team == Team.AWAY) or \
                      (phase == Phase.AWAY_ATTACK and team == Team.HOME)
            if not defends:
                continue
            label = detect_formation(f, team, config).label
            tally[label] = tally.get(label, 0) + 1
        if sum(tally.values()) >= fps:
            timeline.append((frames[w0].t,
                             max(tally.items(), key=lambda kv: kv[1])[0]))

    switches: list[dict] = []
    for (_, a), (t1, b) in zip(timeline, timeline[1:]):
        if a != b:
            switches.append({"t": t1, "from": a, "to": b,
                             "margin": margin_at(t1)})
    return switches


def _key_players(match: Match, team: Team, config: TacticsConfig, top: int = 4) -> list[KeyPlayer]:
    """A csapat kulcsjátékosai: labdabirtoklás-idő (irányító-jel) + aktivitás."""
    team_of = _team_of_track(match)
    poss_frames: dict[int, int] = {}
    for f in match.frames:
        if f.ball is None or not f.players:
            continue
        holder = min(f.players, key=lambda p: math.hypot(p.x - f.ball.x, p.y - f.ball.y))
        d = math.hypot(holder.x - f.ball.x, holder.y - f.ball.y)
        if d <= config.possession_radius_m and holder.team == team:
            poss_frames[holder.track_id] = poss_frames.get(holder.track_id, 0) + 1

    stats = compute_player_stats(match)
    # A kapus-jelölést (role="kapus", lásd goalkeeper.py) átvesszük — a
    # kapus ne "irányítóként" szerepeljen, csak mert nála is jár a labda.
    gk_tracks = {p.track_id for f in match.frames for p in f.players
                 if p.role == "kapus"}
    # Poszt-becslés: a "mezőnyjátékos" helyett konkrét posztot írunk,
    # ha van elég támadó-fázisú minta.
    try:
        from .roles import estimate_positions
        est_pos = estimate_positions(match, config).get(team.value, {})
    except Exception:
        est_pos = {}
    rows: list[KeyPlayer] = []
    # A csapat játékosai: akiket többségében ehhez a csapathoz soroltunk.
    for tid, tteam in team_of.items():
        if tteam != team:
            continue
        pf = poss_frames.get(tid, 0)
        dist = stats[tid].distance_m if tid in stats else 0.0
        role = ("kapus" if tid in gk_tracks
                else "irányító" if pf > 0 else "mezőnyjátékos")
        if role == "mezőnyjátékos" and tid in est_pos:
            role = est_pos[tid]["poszt"]
        rows.append(KeyPlayer(track_id=tid, possession_frames=pf,
                              distance_m=round(dist, 1), role=role))
    # Rendezés: előbb a legtöbb labdabirtoklás, majd a legaktívabb.
    rows.sort(key=lambda r: (r.possession_frames, r.distance_m), reverse=True)
    # A legaktívabbat "irányítónak" csak akkor hívjuk, ha tényleg birtokolt sokat.
    return rows[:top]


def _coach_keys(rep: ScoutingReport) -> tuple[list, list, list]:
    """Edzői kulcsok: erősségek, gyengeségek, és "hogyan játssz ellenük"."""
    strengths, weaknesses, keys = [], [], []

    # Védekezés elleni terv.
    dmain = rep.defense_main
    if dmain == "6-0":
        keys.append("Mély 6-0 faluk ellen: 9 m-es lövés és beúszó, csald ki a védőt.")
    elif dmain == "5-1":
        keys.append("5-1-ük ellen: az előretolt védő kicselezése, gyors lefordulás.")
    elif dmain == "3-2-1":
        keys.append("3-2-1-ük ellen: terheld a beállót és a szélső réseket.")
    elif dmain and dmain != "—":
        keys.append(f"Védőformájuk főleg {dmain} — keresd a legüresebb sávot ellene.")

    # Tempó.
    if rep.fast_break_pct >= 12.0:
        strengths.append(f"Gyors indítás ({rep.fast_break_pct:.0f}%) — veszélyes lerohanás.")
        keys.append("Zárj vissza gyorsan lövés/labdavesztés után — magas a lerohanásuk.")
    if rep.avg_attack_duration_s and rep.avg_attack_duration_s < 6.0:
        strengths.append(f"Gyors támadásépítés (~{rep.avg_attack_duration_s:.1f} s).")
    elif rep.avg_attack_duration_s >= 12.0:
        weaknesses.append(f"Lassú, hosszú támadások (~{rep.avg_attack_duration_s:.1f} s) — türelmes védekezés kifárasztja őket.")

    # Befejezés.
    if rep.shots >= 3:
        if rep.shot_efficiency_pct >= 55.0:
            strengths.append(f"Erős befejezés ({rep.shot_efficiency_pct:.0f}% gólarány).")
            keys.append("Szűkítsd a lövőteret 9 m-en és a szélen — jól fejeznek be.")
        elif rep.shot_efficiency_pct <= 35.0:
            weaknesses.append(f"Gyenge befejezés ({rep.shot_efficiency_pct:.0f}%) — engedd a rossz helyzetű lövést.")
    if rep.turnovers >= 3 and rep.turnovers >= rep.shots:
        weaknesses.append("Sok labdaeladás — agresszív, aktív védekezés kifizetődő ellenük.")

    # Helyzetminőség: a gólarányuknál mélyebb kép — a helyzeteikhez képest
    # lőnek-e többet/kevesebbet, és milyen minőségű helyzetekig jutnak el.
    if rep.shots >= 4 and rep.xg > 0:
        if rep.xg_diff >= 1.5:
            strengths.append(f"A helyzeteik FELETT teljesítenek "
                             f"(+{rep.xg_diff:.1f} gól a várhatóhoz képest) — "
                             "a kis esélyű lövéseiket is belövik.")
            keys.append("Ne engedj tiszta helyzetet — minden hibát büntetnek.")
        elif rep.xg_diff <= -1.5:
            weaknesses.append(f"A helyzeteiknél kevesebbet lőnek "
                              f"({rep.xg_diff:.1f}) — a befejezésük bizonytalan.")
        avg_q = rep.xg / rep.shots
        if avg_q >= 0.45:
            keys.append("Türelmesen NAGY helyzetekig jutnak — előbb a beúszást "
                        "és a hatosról jövő lövést zárd le.")
        elif avg_q <= 0.28:
            keys.append("Sok kis esélyű (távoli/szélső) lövést vállalnak — "
                        "belső zónában maradhat szoros a fal.")

    # Irányító-függés: ha a fő szervező nélkül leáll a játékuk, a
    # legjobb védekezési terv Ő maga.
    if rep.playmaker_dependency == "magas" and rep.playmaker_drop is not None:
        weaknesses.append(
            f"Erősen az irányítóra épülnek — nélküle a támadásaik "
            f"lövésig jutása {100 * rep.playmaker_drop:.0f} százalékponttal esik.")
        keys.append("Fogd meg az irányítót (emberfogás/korai kontakt) — "
                    "nélküle leáll a támadásépítésük.")

    # A játékszervezésük tengelye: a leggyakoribb passz-kapcsolat. Ha egy
    # páros viszi a játékot, annak elvágása (sávzárás, letámadás) töri meg
    # a ritmusukat.
    if rep.pass_total >= 15 and rep.pass_pairs:
        pr = rep.pass_pairs[0]
        if int(pr["passes"]) >= 5:
            keys.append(
                f"A játékuk tengelye a {pr['from']}. és {pr['to']}. játékos "
                f"kapcsolata ({pr['passes']} passz) — ennek elvágása "
                "(sávzárás, agresszív letámadás) megtöri a ritmusukat.")

    # Hosszú támadásaik terméketlenek? Ha a hosszú (35 mp+) vödör (4+
    # támadásból) 20+ ponttal rosszabb a rövidnél, a türelem nekik nem
    # barát — a fegyelmezett fal kivárhatja őket.
    long_rec = rep.duration_eff.get("hosszú (35 mp+)")
    short_rec = rep.duration_eff.get("rövid (<15 mp)")
    if (long_rec and short_rec and long_rec["attacks"] >= 4
            and short_rec["attacks"] >= 4):
        long_pct = 100.0 * long_rec["goals"] / long_rec["attacks"]
        short_pct = 100.0 * short_rec["goals"] / short_rec["attacks"]
        if short_pct - long_pct >= 20.0:
            keys.append(
                f"A hosszú támadásaik terméketlenek ({long_pct:.0f}% vs "
                f"{short_pct:.0f}% a rövideknél) — kivárható őket: a "
                "fegyelmezett fal ellen elfogy az ötletük.")

    # Melyik fal fogja meg őket: ha egy forma ellen (4+ lövésből) jóval
    # rosszabbul konvertálnak, mint máshol, az a javasolt felállás.
    if rep.vs_formation:
        pools = [(f_, v) for f_, v in rep.vs_formation.items()
                 if v["shots"] >= 4]
        if len(pools) >= 2:
            def pct(v):
                return 100.0 * v["goals"] / v["shots"]
            worst = min(pools, key=lambda kv: pct(kv[1]))
            best = max(pools, key=lambda kv: pct(kv[1]))
            if pct(best[1]) - pct(worst[1]) >= 25.0:
                keys.append(
                    f"A {worst[0]} fal ellen elakadnak "
                    f"({pct(worst[1]):.0f}% gólarány, a {best[0]} ellen "
                    f"{pct(best[1]):.0f}%) — ellenük {worst[0]}-ban állj fel.")

    # Válasz-idő: gyorsan rendezik-e a sorokat kapott gól után.
    if rep.response_n >= 4:
        avg_resp = rep.response_sum_s / rep.response_n
        if avg_resp <= 60.0:
            strengths.append(
                f"Kapott gól után gyorsan rendezik a sorokat (átlag "
                f"{avg_resp:.0f} mp a válaszgólig) — egy-egy góllal nem "
                "törhetők meg, sorozat kell.")
        elif avg_resp >= 150.0:
            weaknesses.append(
                f"Kapott gól után megtorpannak (átlag {avg_resp:.0f} mp a "
                "válaszgólig) — betalálás után azonnal emelj tempót, "
                "ilyenkor építhető sorozat.")

    # Támadás-oldal súlypont: ha egy szárnyra épül a játék, a fal
    # súlypontja is oda tolható.
    side_total = sum(rep.side_frames.values()) if rep.side_frames else 0
    if side_total >= 250:  # ~10 mp támadójáték minimum
        top_side, top_n = max(rep.side_frames.items(), key=lambda kv: kv[1])
        pct = 100.0 * top_n / side_total
        if top_side != "közép" and pct >= 45.0:
            keys.append(
                f"A támadójátékuk súlypontja a {top_side} oldal "
                f"({pct:.0f}%) — told oda a fal súlypontját, és a "
                "másik szárnyon hagyj teret a kontrának.")

    # Nyomás alatti befejezés: ha fedezve alig, szabadon jól konvertálnak,
    # a fegyelmezett (szabálytalanság nélküli) szoros fal önmagában elég.
    if rep.fin_free_shots >= 3 and rep.fin_cov_shots >= 3:
        free_pct = 100.0 * rep.fin_free_goals / rep.fin_free_shots
        cov_pct = 100.0 * rep.fin_cov_goals / rep.fin_cov_shots
        if free_pct - cov_pct >= 30.0:
            keys.append(
                f"Fedezett helyzetben alig veszélyesek ({cov_pct:.0f}% vs "
                f"{free_pct:.0f}% szabadon) — a szoros, fegyelmezett fal "
                "önmagában megfogja őket, ne szabálytalankodj feleslegesen.")
        elif cov_pct >= 45.0:
            strengths.append(
                f"Nyomás alatt is hidegvérű lövőik vannak (fedezve is "
                f"{cov_pct:.0f}%-ot konvertálnak) — a fal önmagában kevés, "
                "korai zavarás és blokk kell.")

    # Lövés-erő: nagy átlagsebességű lövések — a blokk és a korai zavarás
    # felértékelődik ellenük; lassú lövéseknél a kapus-munka a kulcs.
    if rep.shot_speed_n >= 5:
        avg = rep.shot_speed_sum_kmh / rep.shot_speed_n
        if avg >= 85.0:
            strengths.append(
                f"Nagy erejű lövőik vannak (átlag {avg:.0f} km/h, "
                f"csúcs {rep.shot_speed_max_kmh:.0f}) — a kapus reakcióra "
                "nem építhetsz: blokk és korai zavarás kell.")

    # Lövőerő-esés: ha a 2. félidőre rendre lassulnak a lövéseik, a hajrában
    # a kapus többet fog belőlük — a meccs vége ellenük dolgozik.
    if rep.ssf_fh_n >= 5 and rep.ssf_sh_n >= 5 and rep.ssf_fh_sum_kmh > 0:
        _f_fh = rep.ssf_fh_sum_kmh / rep.ssf_fh_n
        _f_sh = rep.ssf_sh_sum_kmh / rep.ssf_sh_n
        _f_drop = 100.0 * (_f_fh - _f_sh) / _f_fh
        if _f_drop >= 8.0:
            keys.append(
                f"A 2. félidőre esik a lövőerejük ({_f_fh:.0f} → "
                f"{_f_sh:.0f} km/h, −{_f_drop:.0f}%) — fáradnak: a hajrában "
                "a kapusod bátran vállalhat, és a ti frissességetek "
                "(rotáció) dönthet.")
        elif _f_drop <= -8.0:
            keys.append(
                f"A 2. félidőben még nő is a lövőerejük ({_f_fh:.0f} → "
                f"{_f_sh:.0f} km/h) — mély a rotációjuk: a hajrát nem "
                "lehet kivárásra játszani ellenük.")

    # Félidő-minta: melyik félidőben erősebbek (halmozott mérlegből).
    fh_diff = rep.fh_goals_for - rep.fh_goals_against
    sh_diff = rep.sh_goals_for - rep.sh_goals_against
    fh_total = rep.fh_goals_for + rep.fh_goals_against
    if fh_total + rep.sh_goals_for + rep.sh_goals_against >= 8:
        if sh_diff - fh_diff >= 3:
            keys.append(
                f"A 2. félidőben rendre feljavulnak (félidő-mérleg "
                f"{fh_diff:+d} → {sh_diff:+d}) — az elején szerezz olyan "
                "előnyt, amit a hajrájuk sem fordít meg.")
        elif fh_diff - sh_diff >= 3:
            keys.append(
                f"A 2. félidőben rendre elfogynak (félidő-mérleg "
                f"{fh_diff:+d} → {sh_diff:+d}) — türelem: a meccs második "
                "fele neked dolgozik.")

    # Hosszan járatják a labdát: fegyelmezett fal + passzív-jel kivárása.
    if rep.slow_attacks_total >= 6:
        slow_pct = 100.0 * rep.slow_attacks_slow / rep.slow_attacks_total
        if slow_pct >= 30.0:
            keys.append(
                f"A támadásaik {slow_pct:.0f}%-a 35 mp fölé húzódik — "
                "maradj fegyelmezett a falban, ne ugorj ki: a passzív-jel "
                "és a kapkodó befejezés nekik fáj.")

    # Aktív blokkoló fal: az átlövés ellenük drága — kerülő utak kellenek.
    if rep.blocks >= 3:
        strengths.append(f"Aktív a faluk: {rep.blocks} lövést blokkoltak.")
        keys.append("Sokat blokkolnak — átlövés helyett beálló-játékkal és "
                    "szélső-befutásokkal kerüld a falat.")
    # A fal kulcsembere: ha egy védő adja a blokkok zömét, őt kell
    # kimozdítani a helyéről.
    if rep.blockers and rep.blockers[0]["blocks"] >= 3:
        top_b = rep.blockers[0]
        keys.append(
            f"A faluk kulcsa a(z) {top_b['player_id']}. játékos "
            f"({top_b['blocks']} blokk) — elzárással húzd ki a helyéről: "
            "mögötte nyílik meg az átlövés.")

    # Hosszú gólcsendre hajlamosak: ha leállnak, akkor kell ellépni.
    if rep.drought_longest_s >= 480.0:
        keys.append(
            f"Hajlamosak hosszú gólcsendre (leghosszabb: "
            f"{rep.drought_longest_s / 60:.0f} perc) — ha leáll a "
            "támadójátékuk, tempót fel: ilyenkor kell ellépni.")

    # Hajrá-mérleg: szoros végjátékban nyújtott teljesítményük.
    if rep.clutch_matches >= 1:
        diff = rep.clutch_goals_for - rep.clutch_goals_against
        if diff >= 2:
            strengths.append(
                f"Szoros hajrában erősek (+{diff} gól a hajrákban) — ne "
                "hagyd a végjátékra a döntést.")
        elif diff <= -2:
            weaknesses.append(
                f"Szoros hajrában elfogynak ({diff} gól a hajrákban) — "
                "kiegyenlített meccsen a türelem nekik fáj.")
            keys.append("Tartsd szorosan a meccset a hajráig — a végjátékban "
                        "rendre alulmaradnak.")

    # Csere-mintáik: mikor forgatnak, és mit hoznak a cseréik.
    if rep.sub_rotations >= 2:
        trail_pct = 100.0 * rep.sub_trailing / rep.sub_rotations
        diff = rep.sub_after_for - rep.sub_after_against
        if trail_pct >= 70.0:
            keys.append("Jellemzően hátrányban forgatnak — a cserehullámuk "
                        "után friss sorra és tempóváltásra készülj.")
        if diff >= 2:
            strengths.append(f"A cseréik frissítést hoznak: a cserehullámok "
                             f"utáni mérlegük +{diff} gól.")
        elif diff <= -2:
            weaknesses.append(f"A cserehullámaik után megingnak: a cserék "
                              f"utáni mérlegük {diff} gól — a forgatásuk "
                              "utáni percekben érdemes rájuk ijeszteni.")

    # Védekezési nyomás: szoros vagy laza fal — így támadd.
    if rep.defensive_pressure_m and rep.def_shots_against >= 4:
        if rep.defensive_pressure_m <= 1.3:
            keys.append("Szorosan, előretolva védekeznek (a labdásra "
                        f"átlag {rep.defensive_pressure_m:.1f} m-re lépnek ki) "
                        "— keresd a lecsúszást, a beállót és a betörést.")
        elif rep.defensive_pressure_m >= 2.5:
            keys.append("Lazán, mélyen védekeznek (a labdásra átlag "
                        f"{rep.defensive_pressure_m:.1f} m-re állnak) — "
                        "vállald a 9 m-es lövést, van rá tér.")

    # Gyenge visszazárásuk: futtass rájuk labdaszerzés után.
    if (rep.transition_turnovers >= 4
            and rep.transition_goals_against >= 2):
        pct = 100.0 * rep.transition_goals_against / rep.transition_turnovers
        keys.append(f"Gyenge a visszazárásuk (a labdavesztéseik "
                    f"{pct:.0f}%-a gyors kapott gól) — labdaszerzés után "
                    "azonnal indíts, keresd a lerohanást.")

    # Elöl (támadó harmadban) sok elvesztett labda: felkészült védekezésből
    # azonnali indítás — kontrára építhető gyengeség.
    if rep.turnover_total >= 5:
        front_pct = 100.0 * rep.turnover_front / rep.turnover_total
        if front_pct >= 50.0:
            weaknesses.append(
                f"A labdaeladásaik {front_pct:.0f}%-a a támadó harmadban "
                "történik — labdaszerzéskor a védelmük még előretolva áll.")
            keys.append("Sok labdát adnak el elöl — szervezett labdaszerzés "
                        "után azonnali hosszú indítással büntethető.")

    # A VÉDEKEZÉSÜK gyengéi: szabad lövések és lyukas zóna — "hova játssz".
    if rep.def_shots_against >= 4:
        free_pct = 100.0 * rep.def_free_shots / rep.def_shots_against
        if free_pct >= 40.0:
            weaknesses.append(f"A lövők {free_pct:.0f}%-át SZABADON hagyják — "
                              "türelmes körbejátszással kijön a tiszta lövés.")
            keys.append("Járasd a labdát a tiszta lövésig — gyakran marad "
                        "őrizetlen a lövő ellenük.")
        worst = max(rep.def_zones.items(),
                    key=lambda kv: (kv[1]["goals"], kv[1]["shots"]),
                    default=(None, None))[0] if rep.def_zones else None
        if worst and rep.def_zones[worst]["goals"] >= 2:
            keys.append(f"A faluk itt lyukas: {worst} "
                        f"({rep.def_zones[worst]['goals']} kapott gól) — "
                        "ide szervezz befejezést.")

    # Engedett lövésminőség: milyen értékű lövéseket enged a faluk.
    if rep.def_shots_against >= 8 and rep.xga_sum > 0:
        _xga = rep.xga_sum / rep.def_shots_against
        if _xga >= 0.38:
            weaknesses.append(
                f"Ziccereket engednek (átlag {_xga:.2f} xG/lövés a kapott "
                "lövéseken) — a faluk mögé be lehet jutni.")
            keys.append(
                "Türelmesen a nagy helyzetig: betörésekkel és beálló-"
                "játékkal ellenük kijön a ziccer — ne elégedj meg a "
                "távoli lövéssel.")
        elif _xga <= 0.22:
            strengths.append(
                f"Kiszorító védekezés: rossz lövéseket kényszerítenek ki "
                f"(átlag {_xga:.2f} xG/lövés) — a kapusuk dolgát a faluk "
                "könnyíti.")
            keys.append(
                "A faluk kiszorít — előre eltervezett figurákkal és gyors "
                "indításokkal kerüld el, hogy rossz szögű lövésekbe "
                "kényszerülj.")

    # Emberfogásuk: a leglazább védő megtámadható oldala.
    if rep.markers:
        loose_m = max(rep.markers,
                      key=lambda m_: m_["dist_sum"] / m_["frames"])
        loose_avg = loose_m["dist_sum"] / loose_m["frames"]
        if loose_m["frames"] >= 50 and loose_avg >= 2.5:
            weaknesses.append(
                f"A(z) {loose_m['player_id']}-es védőjük lazán őrzi az "
                f"emberét (átlag {loose_avg:.1f} m).")
            keys.append(
                f"A(z) {loose_m['player_id']}-es védő oldalára vidd az "
                "egy-egy elleni játékot — ott van tér.")
        # A tapadó emberfogójuk viszont erősség: oda elzárás nélkül
        # nem érdemes befejezést szervezni.
        tight_m = min(rep.markers,
                      key=lambda m_: m_["dist_sum"] / m_["frames"])
        tight_avg = tight_m["dist_sum"] / tight_m["frames"]
        if tight_m["frames"] >= 50 and tight_avg <= 1.5:
            strengths.append(
                f"A(z) {tight_m['player_id']}-es védőjük tapadó "
                f"emberfogó (átlag {tight_avg:.1f} m).")
            keys.append(
                f"A(z) {tight_m['player_id']}-es védő oldalára csak "
                "elzárással szervezz befejezést — egy-egyben nehezen "
                "verhető.")

    # Beálló-terhelésük: ha a támadásaik zöme a beállón át megy,
    # a beálló-védelem lesz a meccs egyik kulcsa.
    if rep.pivot_total_attacks >= 6:
        pshare = 100.0 * rep.pivot_attacks / rep.pivot_total_attacks
        if pshare >= 40.0:
            keys.append(
                f"Támadásaik {pshare:.0f}%-a a beállón át megy — "
                "szendvics a beállóra, és előzd meg a beadást: a "
                "kapott labdája már veszély.")
            if rep.pivot_attacks >= 3:
                pg = 100.0 * rep.pivot_goals / rep.pivot_attacks
                other_n = rep.pivot_total_attacks - rep.pivot_attacks
                og = (100.0 * rep.pivot_other_goals / other_n
                      if other_n else None)
                if og is not None and pg - og >= 15.0:
                    strengths.append(
                        f"A beálló-játékuk kifizetődő: {pg:.0f}% gól a "
                        f"beállón át, {og:.0f}% nélküle.")
                elif og is not None and og - pg >= 15.0:
                    weaknesses.append(
                        f"A beálló-játékuk terméketlen ({pg:.0f}% gól, "
                        f"nélküle {og:.0f}%) — hagyd, hogy oda "
                        "erőltessék.")

    # Betörés-folyosójuk: ha egy sávban koncentrálódnak a betöréseik,
    # oda kell a segítő védő.
    if rep.break_entries >= 5 and rep.break_lanes:
        top_lane, top_rec = next(iter(rep.break_lanes.items()))
        lane_share = 100.0 * top_rec["entries"] / rep.break_entries
        if lane_share >= 40.0:
            keys.append(
                f"Betöréseik {lane_share:.0f}%-a a(z) {top_lane} "
                "sávban jön — oda segítő védőt, a sáv-váltást előre "
                "beszéljétek meg.")

    # Passz-láncaik: miből élnek — gyors első hullám vagy türelmes
    # körbejáratás (a legjobb gólarányú vödörből, 4+ támadástól).
    if rep.pass_attacks >= 6 and rep.pass_buckets:
        best_pb = None
        for lab_pb, v_pb in rep.pass_buckets.items():
            if v_pb["attacks"] < 4 or not v_pb["goals"]:
                continue
            pct_pb = 100.0 * v_pb["goals"] / v_pb["attacks"]
            if best_pb is None or pct_pb > best_pb[1]:
                best_pb = (lab_pb, pct_pb, v_pb)
        if best_pb is not None and best_pb[1] >= 40.0:
            if best_pb[0] == "0–2 passz":
                keys.append(
                    f"A gyors első hullámból élnek ({best_pb[1]:.0f}% "
                    "gól 0–2 passzból) — az első lövést zárd le, "
                    "a visszazárás az első lépésnél dől el.")
            elif best_pb[0] == "6+ passz":
                keys.append(
                    f"Türelmesen körbejáratnak ({best_pb[1]:.0f}% gól "
                    "6+ passzból) — ne ugrálj ki a falból, a hosszú "
                    "támadás végén jön a valódi befejezés.")

    # Rotációjuk: szűk pad = a hajrában fogynak el; széles pad =
    # végig magas tempót bírnak.
    if rep.rotation_matches:
        avg_used = rep.rotation_used_sum / rep.rotation_matches
        if avg_used <= 8.0:
            weaknesses.append(
                f"Szűk rotációval játszanak (átlag {avg_used:.0f} "
                "bevetett játékos).")
            keys.append(
                "Szűk a paduk — vidd tempóban a meccset, sok cserével: "
                "a hajrára elfogynak.")
        elif avg_used >= 11.0:
            strengths.append(
                f"Széles paddal forgatnak (átlag {avg_used:.0f} "
                "bevetett játékos) — a tempó nekik dolgozik.")

    # Labdaszerzőjük: aki elcsípi a passzokat — vele szemben óvatos játék.
    if rep.ball_winners:
        top_bw = rep.ball_winners[0]
        if top_bw["steals"] >= 3:
            strengths.append(
                f"A(z) {top_bw['player_id']}-es a labdaszerzőjük "
                f"({top_bw['steals']} szerzés).")
            keys.append(
                f"A(z) {top_bw['player_id']}-es elcsípi a labdákat — "
                "az ő zónájában rövid, biztos passz; a hosszú "
                "keresztpasszt nála ne erőltesd.")

    # Labdaeladójuk: a leggyengébb labdabiztonságú játékos — rá érdemes
    # presselni, provokálni az eladást.
    if rep.turnover_players:
        top_to = rep.turnover_players[0]
        if top_to["losses"] >= 4:
            keys.append(
                f"A(z) {top_to['player_id']}-es a leggyengébb "
                f"labdabiztonságú ({top_to['losses']} eladás) — rá "
                "presselj, zárd a passzsávjait, provokáld az eladást a "
                "gyors indításhoz.")

    # Gól-koncentráció: ha a góljaik zöme egy embertől jön, az ő
    # kikapcsolása az egész támadójátékukat megfojtja; ha elosztott,
    # csak a csapatszintű védekezés működik.
    _sg_total = sum(w["goals"] for w in (rep.scorer_goals or []))
    if _sg_total >= 5 and rep.scorer_goals:
        _sg_top = rep.scorer_goals[0]
        _sg_share = 100.0 * _sg_top["goals"] / _sg_total
        if _sg_share >= 40.0:
            keys.append(
                f"Góljaik {_sg_share:.0f}%-át a(z) {_sg_top['player_id']}-es "
                f"szerzi ({_sg_top['goals']}/{_sg_total}) — egy emberre épül "
                "a támadójátékuk: az ő kikapcsolása (szoros őrzés, korai "
                "kilépés, akár emberfogás) a meccs kulcsa.")
        elif _sg_share <= 25.0 and len(rep.scorer_goals) >= 4:
            keys.append(
                f"A gólszerzésük elosztott (a fő lövőjük is csak "
                f"{_sg_share:.0f}%) — nincs kit kikapcsolni: csapatszintű, "
                "fegyelmezett fal kell ellenük, nem egy-egy párharc.")

    # Kapus-forma félidőnként: ha a kapusuk a 2. félidőre esik, a hajrában
    # kell bátran lőni rá; ha akkor lendül formába, az elején kell büntetni.
    if rep.gsf_fh_faced >= 4 and rep.gsf_sh_faced >= 4:
        _gsf_fh = 100.0 * rep.gsf_fh_saves / rep.gsf_fh_faced
        _gsf_sh = 100.0 * rep.gsf_sh_saves / rep.gsf_sh_faced
        if _gsf_fh - _gsf_sh >= 15.0:
            keys.append(
                f"A kapusuk a 2. félidőre esik ({_gsf_fh:.0f}% → "
                f"{_gsf_sh:.0f}% védés) — a hajrában lőjetek rá bátran, "
                "ott már nem tartja a korai formáját.")
        elif _gsf_sh - _gsf_fh >= 15.0:
            keys.append(
                f"A kapusuk a 2. félidőre lendül formába ({_gsf_fh:.0f}% → "
                f"{_gsf_sh:.0f}% védés) — az elején büntesd, a hajrában "
                "már csak a kidolgozott ziccer megy be neki.")

    # Kihagyott ziccer ára: ha a kihagyásaik után rendre gyors büntetést
    # kapnak, a kihagyásuk a ti indítás-jeletek.
    if rep.bcp_misses >= 4:
        _bcp_rate = 100.0 * rep.bcp_punished / rep.bcp_misses
        if _bcp_rate >= 40.0:
            keys.append(
                f"A kihagyott ziccereik megbosszulják magukat: "
                f"{rep.bcp_misses} kihagyásból {rep.bcp_punished} után "
                "fél percen belül gólt kaptak — a kihagyásuk a ti "
                "indítás-jeletek: ilyenkor fejben még a helyzetnél "
                "vannak, AZONNAL játsszátok meg a gyors középkezdést "
                "vagy a kidobást.")

    # Tempó-esés: akinek a 2. félidőre elfogy a lába, az ellen a 2.
    # félidőben tempót KELL emelni.
    if rep.tpf_fh_min >= 8.0 and rep.tpf_sh_min >= 8.0:
        _tpf_fh = rep.tpf_fh_attacks / rep.tpf_fh_min
        _tpf_sh = rep.tpf_sh_attacks / rep.tpf_sh_min
        if _tpf_fh - _tpf_sh >= 0.2:
            keys.append(
                f"A 2. félidőre elfogy a lábuk ({_tpf_fh:.1f} → "
                f"{_tpf_sh:.1f} támadás/perc) — a 2. félidőben tempót "
                "KELL emelni ellenük: gyors középkezdés, futó kézi, a "
                "friss lábak a szünet utánra; a lassú leforgás az ő "
                "meccsük.")

    # Félidei hátrányból fordítás: kinek ér valamit a félidei előny.
    if rep.htc_behind >= 2:
        if rep.htc_turned == 0 and rep.htc_saved == 0:
            keys.append(
                f"Félidei hátrányból nem jönnek vissza ({rep.htc_behind} "
                "ilyen meccsből egyet sem mentettek) — az első félidő a "
                "meccs: ha a szünetre előnnyel mész, náluk fejben el van "
                "döntve; a hangsúlyt az első 30 percre tedd.")
        elif 2 * rep.htc_turned >= rep.htc_behind:
            keys.append(
                f"Félidei hátrányból rendre fordítanak ({rep.htc_behind} "
                f"ilyen meccsből {rep.htc_turned} fordítás) — a félidei "
                "előny ellenük nem ér semmit: a szünet után újra meg "
                "kell nyerni a meccset, a második félidőre tarts friss "
                "lábat és kész figurát.")

    # Holtpont-mérleg: az egál a legtisztább nyomás-teszt.
    if rep.pb_ties >= 4:
        _pb_rate = 100.0 * rep.pb_won / rep.pb_ties
        if _pb_rate >= 65.0:
            keys.append(
                f"A holtpontokat ők nyerik ({rep.pb_ties} "
                f"döntetlen-állásból {rep.pb_won}-szor ők léptek el) — "
                "ne csússz velük egálba: előnyből kontrolláld a meccset, "
                "és ha beér az egál, időkéréssel törd meg a "
                "holtpont-ritmusukat.")
        elif _pb_rate <= 35.0:
            keys.append(
                f"Az egálnál ők remegnek ({rep.pb_ties} "
                f"döntetlen-állásból csak {rep.pb_won}-szor léptek el) — "
                "utolérni elég: hozd egálra, és a holtpontnál türelmes, "
                "kidolgozott támadással tiétek a következő gól.")

    # Sorozat-törés: hol áll meg ellenük a sorozat.
    if rep.rn_suffered >= 3:
        _rn_avg = rep.rn_suffered_goals / rep.rn_suffered
        if _rn_avg >= 4.5:
            keys.append(
                f"A sorozat ellenük elfut ({rep.rn_suffered} elszenvedett "
                f"sorozat, átlag {_rn_avg:.1f} gól) — ha megvan a 2-0, "
                "nyomjátok meg: a 3-0-jukból rendre 5-6-0 lesz, és az "
                "időkérésük sem mentőöv.")
        elif _rn_avg <= 3.4:
            keys.append(
                f"A sorozatot ellenük 3-nál törik ({rep.rn_suffered} "
                f"elszenvedett sorozat, átlag {_rn_avg:.1f} gól) — "
                "sorozattal nem ölöd meg őket: a meccset végig kell "
                "játszani, az előnyt apránként kell összerakni.")

    # Bravúr utáni lendület: mennyibe kerül ellenük a rossz lövés.
    if rep.bsm_saves >= 4:
        _bsm_rate = 100.0 * rep.bsm_sparked / rep.bsm_saves
        if _bsm_rate >= 40.0:
            keys.append(
                f"A kapusbravúrjuk indítás ({rep.bsm_saves} nagy "
                f"védésből {rep.bsm_sparked} után fél percen belül gólt "
                "szereztek) — a rossz lövés ellenük kontra: válogassátok "
                "meg a befejezést, és a lövő is azonnal zárjon vissza.")
        elif _bsm_rate == 0.0:
            keys.append(
                f"A bravúr náluk elhal ({rep.bsm_saves} nagy védésből "
                "egyet sem váltottak gyors gólra) — a kapusuk megfog, de "
                "nem büntet: a merész lövésnek nincs kontra-ára, fel "
                "lehet vállalni.")

    # Befejezés-esés: mikor ül a lövésük, és mikor már nem.
    if rep.ff_fh_shots >= 8 and rep.ff_sh_shots >= 8:
        _ff_fh = 100.0 * rep.ff_fh_goals / rep.ff_fh_shots
        _ff_sh = 100.0 * rep.ff_sh_goals / rep.ff_sh_shots
        if _ff_fh - _ff_sh >= 15.0:
            keys.append(
                f"A befejezésük a 2. félidőre esik ({_ff_fh:.0f}% → "
                f"{_ff_sh:.0f}% gólra váltás) — az első félidőt éld "
                "túl: a hajrában a lövésük már nem ül, ott elég a "
                "tömör fal és a lepattanó — a türelmes védekezés a "
                "második félidőben kifizet.")

    # Célzás-pontosság: mennyibe kerül nekik a lövés.
    if rep.ac_attempts >= 10:
        _ac_pct = 100.0 * rep.ac_on_target / rep.ac_attempts
        if _ac_pct <= 55.0:
            keys.append(
                f"A lövéseiknek csak {_ac_pct:.0f}%-a tart kapura "
                f"({rep.ac_attempts} kísérletből {rep.ac_on_target}) — "
                "minden mellé lövésük ajándék-kidobás: a kapusotok első "
                "passza előre, a szélsők induljanak a mellé lövés "
                "pillanatában, és a blokkot bátran vállaljátok.")
        elif _ac_pct >= 80.0:
            keys.append(
                f"A lövéseik {_ac_pct:.0f}%-a kaput ér — a kapusotok "
                "egyedül nem marad meg ellenük: a blokk-munka kötelező, "
                "a fal és a kapus sáv-felosztását előre tisztázzátok.")

    # Oldal-részrehajlás: fél-oldalas támadás ellen a fal eltolható.
    _sb_wings = rep.sb_left + rep.sb_right
    if _sb_wings >= 10:
        _sb_pct = 100.0 * max(rep.sb_left, rep.sb_right) / _sb_wings
        if _sb_pct >= 65.0:
            _sb_side = "bal" if rep.sb_left >= rep.sb_right else "jobb"
            keys.append(
                f"A támadásuk fél-oldalas: a szélső-sávos lövéseik "
                f"{_sb_pct:.0f}%-a a {_sb_side} oldalukról jön — told "
                "el a falat arra az oldalra, a segítő védő előre "
                "csúszhat, a gyenge oldali szélsőjük felől pedig "
                "kockázat nélkül lehet zárni.")

    # Ritmus-egyhangúság: a belső órájukra rá lehet állni.
    if rep.ar_n >= 12 and rep.ar_sum_s > 0:
        _ar_avg = rep.ar_sum_s / rep.ar_n
        _ar_var = max(0.0, rep.ar_sumsq_s / rep.ar_n - _ar_avg * _ar_avg)
        _ar_sd = _ar_var ** 0.5
        if _ar_avg > 0 and _ar_sd / _ar_avg <= 0.35:
            keys.append(
                f"Belső órán támadnak: átlag {_ar_avg:.0f} mp, alig "
                f"±{_ar_sd:.0f} szórással — az órájukra rá lehet állni: "
                f"a {max(0.0, _ar_avg - 5.0):.0f}. másodperc körül "
                "időzített kettőzés/letámadás rendre a "
                "lövés-előkészítésüket töri meg.")

    # Ellen-press: rátámadnak-e az eladott labdára.
    if rep.cpr_turnovers >= 8:
        _cpr = 100.0 * rep.cpr_regained / rep.cpr_turnovers
        if _cpr >= 35.0:
            keys.append(
                f"Az eladás pillanatában azonnal visszatámadnak (az "
                f"eladásaik {_cpr:.0f}%-át 6 mp-en belül visszaszerzik) "
                "— a szerzés után az ELSŐ passz legyen tiszta: ne "
                "cselezz a saját térfélen, azonnal játszd előre a "
                "labdát a felszabaduló társnak.")
        elif _cpr <= 15.0:
            keys.append(
                f"Az eladás után beletörődnek (az eladásaiknak csak "
                f"{_cpr:.0f}%-át szerzik vissza gyorsan) — minden "
                "labdaszerzés ingyen lerohanás ellenük: a szerzés után "
                "azonnal indítsatok, a szélsők fussanak.")

    # Hajrá-lövésválasztás: elkapkodják-e a végén a befejezést.
    if rep.csq_early_shots >= 5 and rep.csq_clutch_shots >= 5:
        _csq_early = rep.csq_early_xg / rep.csq_early_shots
        _csq_clutch = rep.csq_clutch_xg / rep.csq_clutch_shots
        if _csq_early - _csq_clutch >= 0.05:
            keys.append(
                f"A hajrában elkapkodják a befejezést: a lövéseik "
                f"helyzetértéke {_csq_early:.2f}-ről "
                f"{_csq_clutch:.2f}-re esik a meccs végére — a "
                "hajrában elég tartani a falat és nem hibázni: ők "
                "maguktól bevállalják a rossz lövéseket.")
        elif _csq_clutch - _csq_early >= 0.05:
            keys.append(
                f"A hajrában kidolgozzák a helyzeteket (a lövéseik "
                f"helyzetértéke {_csq_early:.2f}-ről "
                f"{_csq_clutch:.2f}-re nő) — a végén is kell a "
                "fegyelem: a fal ne lazuljon, a beálló-őrzés és a "
                "váltás a hajrában is éljen.")

    # Passz-kockázat: a hosszú passzsávjaik vadászterületek-e.
    if rep.prk_long_tries >= 8 and rep.prk_short_tries >= 8:
        _prk_long = 100.0 * rep.prk_long_to / rep.prk_long_tries
        _prk_short = 100.0 * rep.prk_short_to / rep.prk_short_tries
        if _prk_long - _prk_short >= 15.0:
            keys.append(
                f"A hosszú passzaik kockázatosak: "
                f"{_prk_long:.0f}%-uk elveszik, a rövideknek csak "
                f"{_prk_short:.0f}%-a ({rep.prk_long_to}/"
                f"{rep.prk_long_tries}) — zárjátok a hosszú "
                "passzsávokat: letámadás és sávba állás, a hosszú "
                "átjátszásaikra vadásszatok.")
        elif _prk_short - _prk_long >= 15.0:
            keys.append(
                f"A hosszú passzokat is biztosan kezelik "
                f"({_prk_long:.0f}% eladás, a rövideknél "
                f"{_prk_short:.0f}%) — a passzsáv-vadászat ellenük "
                "nem fizet: inkább a lövő-fedezésre és a "
                "visszarendeződésre tegyétek a hangsúlyt.")

    # Elzárás-védekezés: bírja-e a faluk az elzárást, vagy minden
    # figurát zárással kell zárni ellenük.
    if rep.scd_screened_shots >= 6 and rep.scd_open_shots > 0:
        _scd_scr = (100.0 * rep.scd_screened_goals
                    / rep.scd_screened_shots)
        _scd_opn = 100.0 * rep.scd_open_goals / rep.scd_open_shots
        if _scd_scr - _scd_opn >= 15.0:
            keys.append(
                f"Rosszul váltanak elzárás ellen: elzárásos "
                f"lövésekből {_scd_scr:.0f}% gól esik ellenük, "
                f"elzárás nélküliekből csak {_scd_opn:.0f}% — minden "
                "figurát elzárással zárjatok: beállós zár az átlövő "
                "őrzőjére, átlövő-kereszt, és a zár mögül lövés.")
        elif _scd_opn - _scd_scr >= 15.0:
            keys.append(
                f"Jól váltanak az elzárásokon (elzárásos lövésekből "
                f"csak {_scd_scr:.0f}% gól ellenük, elzárás "
                f"nélküliekből {_scd_opn:.0f}%) — az elzárás ellenük "
                "zsákutca: keressetek tiszta 1v1-et és üres "
                "területet, ne a zárra játsszatok.")

    # Elzárás-használat: az elzárásos ellen váltás-kommunikáció, az
    # elzárás nélküli lövő magára van hagyva.
    if rep.scu_shots >= 8:
        _scu_pct = 100.0 * rep.scu_screened / rep.scu_shots
        if _scu_pct >= 40.0:
            keys.append(
                f"Elzárásokból lőnek: az őrzött lövéseik "
                f"{_scu_pct:.0f}%-ánál társ zárja el a lövő őrzőjét "
                f"({rep.scu_screened}/{rep.scu_shots}) — a "
                "váltás-kommunikáció a meccs: hangos váltás vagy "
                "átcsúszás az elzárás alatt, különben a lövőjük "
                "mindig tisztán marad.")
        elif _scu_pct <= 10.0:
            keys.append(
                f"Elzárás nélkül lőnek (az őrzött lövéseik csak "
                f"{_scu_pct:.0f}%-ánál van elzárás) — a lövőik "
                "magukra vannak hagyva: agresszív kilépés és blokk, "
                "a segítő védőnek nem kell váltásra készülnie.")

    # Oldalváltás: az oldalváltó ellen kompakt eltolás, az
    # egy-oldalas ellen bátran eltolható a fal.
    if rep.ssw_passes >= 30:
        _ssw_pct = 100.0 * rep.ssw_switches / rep.ssw_passes
        if _ssw_pct >= 12.0:
            keys.append(
                f"Oldalváltásokkal húzzák szét a falat: a támadó "
                f"passzaik {_ssw_pct:.0f}%-a keresztpassz "
                f"({rep.ssw_switches}/{rep.ssw_passes}) — kompakt "
                "eltolás kell: a váltás alatt zárt sávok, senki nem "
                "csúszhat el, a szélső védő ne lépjen ki korán.")
        elif _ssw_pct <= 3.0:
            keys.append(
                f"Egy oldalon ragadnak: a támadó passzaik csak "
                f"{_ssw_pct:.0f}%-a oldalváltás ({rep.ssw_switches}/"
                f"{rep.ssw_passes}) — a fal bátran eltolható a "
                "kedvenc oldalukra: a túloldali szélsőjük éhen marad, "
                "a segítő védő is a labda-oldalra csalható.")

    # Lerohanás-védés: az érzékeny kapus ellen futni kell, a
    # lerohanás-fogó ellen a gyors befejezést is ki kell játszani.
    if rep.gkb_fast_faced >= 4 and rep.gkb_set_faced >= 4:
        _gkb_fast = 100.0 * rep.gkb_fast_saves / rep.gkb_fast_faced
        _gkb_set = 100.0 * rep.gkb_set_saves / rep.gkb_set_faced
        if _gkb_set - _gkb_fast >= 15.0:
            keys.append(
                f"A kapusuk a lerohanásokra érzékeny: gyorsindítás "
                f"ellen {_gkb_fast:.0f}%, rendezett támadás ellen "
                f"{_gkb_set:.0f}% a védése — FUSS: minden szerzés és "
                "kapott gól után azonnali indítás, az első hullámot "
                "fejezd is be.")
        elif _gkb_fast - _gkb_set >= 15.0:
            keys.append(
                f"A kapusuk lerohanás-fogó: gyorsindítás ellen "
                f"{_gkb_fast:.0f}% a védése (rendezett ellen "
                f"{_gkb_set:.0f}%) — a lerohanást is JÁTSZD ki: csel "
                "vagy visszatett labda a csapott lövés helyett, üres "
                "lerohanásból ne lőj rá vaktában.")

    # Gól-előkészítés hossza: a direkt csapat ellen az első hullám
    # megfogása, a kombinatív ellen a fal türelme a meccs.
    if rep.gb_goals >= 4:
        _gb_short = 100.0 * rep.gb_short / rep.gb_goals
        _gb_long = 100.0 * rep.gb_long / rep.gb_goals
        if _gb_short >= 50.0:
            keys.append(
                f"Direkt gólokból élnek: a góljaik {_gb_short:.0f}%-a "
                f"legfeljebb két passzból esik ({rep.gb_short}/"
                f"{rep.gb_goals}) — a visszarendeződés és az első "
                "hullám megfogása a meccs: eladott labda után azonnal "
                "hátra, a hosszú indítást a középső ember fékezi.")
        elif _gb_long >= 50.0:
            keys.append(
                f"Kombinatív gólokból élnek: a góljaik "
                f"{_gb_long:.0f}%-a 5+ passzos akció vége "
                f"({rep.gb_long}/{rep.gb_goals}) — türelmes, "
                "fegyelmezett fal kell: aki az ötödik passznál kilép "
                "vagy cselre ugrik, azon átmennek.")

    # Előkészítő-függés: a kulcs-előkészítő elvágása az egész
    # befejezést megbénítja.
    if rep.ac_assists >= 6:
        _ac_share = rep.ac_top_assists / rep.ac_assists
        if _ac_share >= 0.5:
            keys.append(
                f"Az előkészítésük egy emberen múlik: a gólpasszaik "
                f"{100.0 * _ac_share:.0f}%-a ugyanattól a játékostól "
                f"jön ({rep.ac_top_assists}/{rep.ac_assists}) — "
                "előfogás és a passzsávjának zárása, korai kettőzés "
                "rajta: ha őt elvágjátok, a befejezőik éhen maradnak.")

    # Középkezdés-tempó: a lerohanós ellen tilos az ünneplés, a lassú
    # újraindító középkezdése letámadható.
    if rep.rs_restarts >= 4:
        _rs_pct = 100.0 * rep.rs_fast / rep.rs_restarts
        if _rs_pct >= 50.0:
            keys.append(
                f"Kapott gól után is lerohannak: az újraindításaik "
                f"{_rs_pct:.0f}%-ánál 12 mp-en belül átér a labda "
                f"({rep.rs_fast}/{rep.rs_restarts}) — gól után TILOS "
                "az ünneplés: azonnali visszarendeződés, kijelölt "
                "fékező ember középen.")
        elif _rs_pct <= 20.0:
            keys.append(
                f"Lassan indítanak középről (átlag "
                f"{rep.rs_sum_s / rep.rs_restarts:.0f} mp a kapott "
                "gól után a térfél-átlépésig) — a középkezdésük "
                "letámadható: gól után előre-pressz, a hátsó "
                "passzsávok zárása.")

    # Elsütés-idő: a kapásból lövő az időzítést borítja, a labdafogó
    # időt ad a kilépésre és a blokkra.
    if rep.sr_shots >= 8:
        _sr_pct = 100.0 * rep.sr_quick / rep.sr_shots
        if _sr_pct >= 60.0:
            keys.append(
                f"Kapásból lőnek: a lövéseik {_sr_pct:.0f}%-a 0,6 "
                f"mp-en belüli elsütés ({rep.sr_quick}/{rep.sr_shots}) "
                "— a kapusod a PASSZRA mozduljon, ne a lövésre, a "
                "sáncnak kész kéztartás kell, cselre nem szabad "
                "ugrani.")
        elif _sr_pct <= 25.0:
            keys.append(
                f"Sokáig fogják a labdát lövés előtt (csak "
                f"{_sr_pct:.0f}% gyors elsütés) — van időtök: "
                "agresszív kilépés a lövőre, a blokk ellenük szinte "
                "ingyen van, és a kapus is be tud állni a sarokra.")

    # Beálló-védekezés: bírják-e a beállót, vagy oda kell etetni.
    if rep.pd_pivot_attacks >= 6 and rep.pd_other_attacks > 0:
        _pd_piv = 100.0 * rep.pd_pivot_goals / rep.pd_pivot_attacks
        _pd_oth = 100.0 * rep.pd_other_goals / rep.pd_other_attacks
        if _pd_piv - _pd_oth >= 15.0:
            keys.append(
                f"A beálló-őrzésük gyenge: az ellenük vezetett beállós "
                f"támadások {_pd_piv:.0f}%-a gól, a beálló nélkülieknek "
                f"csak {_pd_oth:.0f}%-a — etessétek a beállót: "
                "elöl-mögött váltás, beúszás a rés mögé, és a "
                "kettőzésük késésre kényszerítése.")
        elif _pd_oth - _pd_piv >= 15.0:
            keys.append(
                f"Bírják a beállót (az ellenük vezetett beállós "
                f"támadásokból csak {_pd_piv:.0f}% gól, beálló nélkül "
                f"{_pd_oth:.0f}%) — ne oda erőltessétek: játsszátok "
                "körbe őket, a beálló inkább kötő-ember legyen, mint "
                "befejező.")

    # Indítás-biztonság: az elcsíphető kihozatalra letámadás a válasz.
    if rep.gos_outlets >= 6:
        _gos_pct = 100.0 * rep.gos_lost / rep.gos_outlets
        if _gos_pct >= 25.0:
            keys.append(
                f"A kapus-indításuk elcsíphető: {rep.gos_outlets} "
                f"indításból {rep.gos_lost} az ellenfélnél köt ki "
                f"({_gos_pct:.0f}%) — támadjátok le a kihozatalt: a "
                "fogadók lefedése + egy letámadó a kapusra, és az "
                "indításuk kapkodássá válik.")

    # Támadó-mozgás: az álló támadás ellen kockázat nélkül léphettek
    # ki; a mozgásos ellen a fegyelmezett átadás-átvétel a kulcs.
    if rep.am_time_s >= 120.0:
        _am_avg = rep.am_dist_m / rep.am_time_s
        if _am_avg <= 0.9:
            keys.append(
                f"Álló a támadásuk: szervezett támadásban átlag "
                f"{_am_avg:.1f} m/s-mal mozognak, labda nélkül alig "
                "futnak el — lépjetek ki bátran a labdásra, a statikus "
                "támadót a kilépés megöli, segíteni nem jön senki.")
        elif _am_avg >= 1.6:
            keys.append(
                f"Mozgásos a támadásuk (átlag {_am_avg:.1f} m/s): "
                "keresztek, elfutások, beúszások — NE kövessetek "
                "embert: fegyelmezett átadás-átvétel, a fal maradjon "
                "rendezett, és hangos kommunikáció a váltásoknál.")

    # Fal-rés: réses a rendezett faluk — betörés és beúszás ellene.
    if rep.wg_frames >= 100:
        _wg_share = 100.0 * rep.wg_wide / rep.wg_frames
        if _wg_share >= 40.0:
            keys.append(
                f"A faluk réses: a rendezett védekezésük kockáinak "
                f"{_wg_share:.0f}%-ában 3,5 m-nél nagyobb rés van a "
                "szomszéd védők között — betörésekkel és beúszó "
                "beállóval támadjátok a réseket, a kereszt-mozgás "
                "szét is húzza őket.")

    # Gólcsend-anatómia: néma vagy kihagyós a leghosszabb csendjük.
    if rep.da_drought_s >= 300.0:
        _da_pm = rep.da_shots / (rep.da_drought_s / 60.0)
        if _da_pm <= 0.3:
            keys.append(
                f"A gólcsendjük néma: a leghosszabb csendjeikben "
                f"({rep.da_drought_s / 60.0:.0f} perc) lövésig is alig "
                f"jutottak ({rep.da_shots} lövés) — ha egyszer "
                "megfogtátok őket, tartsátok a presszt: maguktól nem "
                "találnak vissza a meccsbe.")
        elif _da_pm >= 0.8:
            keys.append(
                f"A gólcsendjük kihagyós: a csendben is lőnek "
                f"(percenként {_da_pm:.1f}) — a csendjüket a kapusod "
                "tartja: tartsd melegen (bemelegítő lövések a "
                "szünetben), és ne válts védekezést, ami működik.")

    # Engedett-oldal: a fal egyik oldala átjárható.
    _csb_wings = rep.csb_left + rep.csb_right
    if _csb_wings >= 8:
        _csb_pct = 100.0 * max(rep.csb_left, rep.csb_right) / _csb_wings
        if _csb_pct >= 65.0:
            _csb_side = "bal" if rep.csb_left >= rep.csb_right else "jobb"
            keys.append(
                f"A faluk {_csb_side} oldala átjárható: a kapott "
                f"szélső-sávos lövések {_csb_pct:.0f}%-a arról jön "
                f"({max(rep.csb_left, rep.csb_right)}/{_csb_wings}) — "
                "arra az oldalra szervezzétek a befejezést, és onnan "
                "húzzátok szét a segítő-csúszásukat.")

    # Eladás-büntetés: az eladásaik gyors gólba kerülnek.
    if rep.tpu_turnovers >= 6:
        _tpu_pct = 100.0 * rep.tpu_punished / rep.tpu_turnovers
        if _tpu_pct >= 35.0:
            keys.append(
                f"Az eladásaik drágák: {rep.tpu_turnovers} eladásukból "
                f"{rep.tpu_punished} után fél percen belül gólt kaptak "
                f"({_tpu_pct:.0f}%) — eladás után nem érnek vissza: "
                "minden szerzésetek után azonnal, gondolkodás nélkül "
                "induljon az első hullám.")

    # Kapus-indítás hossza: az egysíkú kihozatalra ráállhat a terv.
    if rep.gko_outlets >= 6:
        _gko_share = rep.gko_long / rep.gko_outlets
        if _gko_share >= 0.5:
            keys.append(
                f"Hosszú indítós a kapusuk (a kapus-passzai "
                f"{100.0 * _gko_share:.0f}%-a 15 m feletti, "
                f"{rep.gko_long}/{rep.gko_outlets}) — zárjátok a "
                "szélső indítás-sávokat biztos hátsó emberrel: ha a "
                "hosszút elveszitek, rövidre kényszerülnek, amit nem "
                "szoktak.")
        elif _gko_share <= 0.15:
            keys.append(
                f"Mindent rövidre hoz ki a kapusuk (csak "
                f"{rep.gko_long}/{rep.gko_outlets} hosszú indítás) — "
                "a magas letámadás rájuk fér: presszeljétek a "
                "kihozatalt, a hosszú kényszer-indításuk gyakorlatlan.")

    # Területi-fölény-esés: a 2. félidőre hátracsúszó birtoklás.
    if rep.tf_fh_frames >= 100 and rep.tf_sh_frames >= 100:
        _tf_fh = 100.0 * rep.tf_fh_opp / rep.tf_fh_frames
        _tf_sh = 100.0 * rep.tf_sh_opp / rep.tf_sh_frames
        if _tf_fh - _tf_sh >= 12.0:
            keys.append(
                f"A 2. félidőre elvész a területi fölényük "
                f"({_tf_fh:.0f}% → {_tf_sh:.0f}% az ellenfél térfelén) "
                "— az első félidei nyomásukat álljátok ki türelemmel: "
                "a hajrára magától átfordul a pálya, akkor kell "
                "feltolni a játékot.")

    # Asszist-függés: kiadásból élő vs egyéni befejezés — más a terv.
    if rep.ad_goals >= 6:
        _ad_pct = 100.0 * rep.ad_assisted / rep.ad_goals
        if _ad_pct >= 70.0:
            keys.append(
                f"Kiadásból élnek: a góljaik {_ad_pct:.0f}%-a "
                f"gólpasszos ({rep.ad_assisted}/{rep.ad_goals}) — a "
                "passzsávok elvágása (aktív kéz, a beálló elé lépés) "
                "többet ér ellenük, mint az 1-1 elleni hősködés.")
        elif _ad_pct <= 35.0:
            keys.append(
                f"Egyéni megoldásokból élnek: csak a góljaik "
                f"{_ad_pct:.0f}%-a gólpasszos ({rep.ad_assisted}/"
                f"{rep.ad_goals}) — a kulcsember-párharcokat kell "
                "megnyerni: emberfogás, korai test, kettőzés a "
                "labdás villanásaira.")

    # Lepattanó-fal: a lövés utáni zárás hiánya — a második hullám jár.
    if rep.sca_opp_misses >= 6:
        _sca_pct = 100.0 * rep.sca_allowed / rep.sca_opp_misses
        if _sca_pct >= 35.0:
            keys.append(
                f"A faluk nem zár a lövések után: az ellenfelek a "
                f"kimaradt lövéseik {_sca_pct:.0f}%-ánál újra lőhettek "
                f"ellenük ({rep.sca_allowed}/{rep.sca_opp_misses}) — a "
                "lövéseitek után menjetek rá a lepattanóra: a második "
                "hullám ellenük ingyen-lövés.")

    # Pressz-tűrés: rászorított védőnél megugró eladás-arány.
    _ps_press_n = rep.ps_press_passes + rep.ps_press_to
    _ps_free_n = rep.ps_free_passes + rep.ps_free_to
    if _ps_press_n >= 10 and _ps_free_n >= 10:
        _ps_press_pct = 100.0 * rep.ps_press_to / _ps_press_n
        _ps_free_pct = 100.0 * rep.ps_free_to / _ps_free_n
        if _ps_press_pct - _ps_free_pct >= 15.0:
            keys.append(
                f"Pressz-érzékenyek: testközeli védőnél az eladásaik "
                f"aránya {_ps_press_pct:.0f}% (szabadon csak "
                f"{_ps_free_pct:.0f}%) — az agresszív, kilépő fal és a "
                "kettőzés ellenük nem kockázat, hanem termelés: "
                "szorítsátok rá a labdásra az első védőt.")

    # Eladás-időzítés: a korai eladó a letámadásra érzékeny.
    if rep.tt_timed >= 6 and rep.tt_early / rep.tt_timed >= 0.5:
        keys.append(
            f"Korai eladók: az eladásaik "
            f"{100.0 * rep.tt_early / rep.tt_timed:.0f}%-a a birtoklás "
            f"első 10 másodpercében jön ({rep.tt_early}/{rep.tt_timed}) "
            "— a magas, korai letámadás ellenük azonnal termel: a "
            "kihozataluknál presszeljetek, ne a felállt támadásuknál.")

    # Kapus-gyengeoldal: egy oldalra kapott gólok — kész lövő-terv.
    _gw_goals = rep.gw_bal + rep.gw_kozep + rep.gw_jobb
    if _gw_goals >= 6:
        _gw_tally = {"bal": rep.gw_bal, "közép": rep.gw_kozep,
                     "jobb": rep.gw_jobb}
        _gw_weak = max(_gw_tally, key=lambda k: _gw_tally[k])
        if _gw_tally[_gw_weak] / _gw_goals >= 0.45:
            keys.append(
                f"A kapujuk a(z) {_gw_weak} oldalán átjárható (a kapus "
                f"szemszögéből): oda kapták a gólok "
                f"{100.0 * _gw_tally[_gw_weak] / _gw_goals:.0f}%-át "
                f"({_gw_tally[_gw_weak]}/{_gw_goals}) — a befejezők "
                "tudatosan arra az oldalra célozzanak.")

    # Lövő-koncentráció: egy emberre épülő lövés-terhelés — a
    # védekezés személyre szabható.
    if rep.sc_shots >= 12:
        _sc_share = rep.sc_top_shots / rep.sc_shots
        if _sc_share >= 0.35:
            keys.append(
                f"A lövés-terhelésük egy emberre épül: a fő lövőjük "
                f"adja a lövéseik {100.0 * _sc_share:.0f}%-át "
                f"({rep.sc_top_shots}/{rep.sc_shots}) — emberfogás "
                "vagy korai kettőzés rajta, és onnantól olyanoknak "
                "kell befejezniük, akik ezt nem szokták.")

    # Kapuscsere-hatás: bejön-e náluk a csere — a lövő-terv a második
    # kapusra is kell-e, vagy nincs mögötte mentőöv.
    if (rep.gkc_changes >= 2 and rep.gkc_pre_faced >= 4
            and rep.gkc_post_faced >= 4):
        _gkc_pre = 100.0 * rep.gkc_pre_saves / rep.gkc_pre_faced
        _gkc_post = 100.0 * rep.gkc_post_saves / rep.gkc_post_faced
        if _gkc_post - _gkc_pre >= 15.0:
            keys.append(
                f"A kapuscseréjük bejön ({_gkc_pre:.0f}% → "
                f"{_gkc_post:.0f}% védés a cserék után) — az első kapus "
                "megingása után másik minőség jön: a lövő-tervet a "
                "második kapusra IS készítsétek el.")
        elif _gkc_pre - _gkc_post >= 15.0:
            keys.append(
                f"A kapuscseréjük sem segít ({_gkc_pre:.0f}% → "
                f"{_gkc_post:.0f}% védés a cserék után) — ha az első "
                "kapusuk megingott, nyomjátok tovább: nincs mögötte "
                "mentőöv.")

    # Hetes-védés: a hetest fogó kapus ellen a hetes nem kész gól; a
    # sosem fogó ellen a hetes-kiharcolás biztos üzlet.
    if rep.s7d_faced >= 3:
        _s7_rate = 100.0 * rep.s7d_saved / rep.s7d_faced
        if _s7_rate >= 40.0:
            keys.append(
                f"A kapusuk hetest fog ({rep.s7d_faced} kapura tartóból "
                f"{rep.s7d_saved}) — a hetes ellenük nem kész gól: a "
                "dobóitok sarok-váltással, késleltetéssel készüljenek, "
                "és kihagyott hetes után ne törjön meg a lendület.")
        elif rep.s7d_saved == 0 and rep.s7d_faced >= 4:
            keys.append(
                f"Hetest nem fognak ({rep.s7d_faced} kapura tartóból 0 "
                "védés) — a hetes-kiharcolás ellenük biztos üzlet: "
                "vigyétek be a beállóra a labdát, vállaljátok az "
                "ütközést.")

    # Szoros meccs-mérleg: aki a szorosat rendre elbukja, azt elég
    # meccsben tartani; aki hozza, attól nem lehet ajándékot várni.
    _cg_dec = rep.cg_wins + rep.cg_losses
    if _cg_dec + rep.cg_draws >= 2:
        if rep.cg_losses >= 2 and rep.cg_losses >= 2 * rep.cg_wins:
            keys.append(
                f"A szoros meccseket elbukják ({rep.cg_wins} győzelem – "
                f"{rep.cg_losses} vereség az 1-2 gólos meccseken) — "
                "tartsd meccsben magad, a hajrában ŐK roppannak meg.")
        elif rep.cg_wins >= 2 and rep.cg_wins >= 2 * rep.cg_losses:
            keys.append(
                f"A szoros meccseket hozzák ({rep.cg_wins}–"
                f"{rep.cg_losses} az 1-2 gólos meccseken) — tőlük nem "
                "jön ajándék a hajrában: még a szoros állás előtt kell "
                "ellépni tőlük.")

    # Gól utáni elalvás: ha a góljaik után rendre bejön az azonnali
    # válasz, a középkezdésük utáni első támadás a ti nagy esélyetek.
    if rep.pgl_goals >= 5:
        _pgl_rate = 100.0 * rep.pgl_quick / rep.pgl_goals
        if _pgl_rate >= 40.0:
            keys.append(
                f"Gól után elalszanak: a góljaik {_pgl_rate:.0f}%-ára fél "
                f"percen belül jött válasz ({rep.pgl_goals} gólból "
                f"{rep.pgl_quick}) — a középkezdésük után AZONNAL "
                "támadjatok, ott a legpuhább a visszarendeződésük.")
        elif _pgl_rate <= 10.0 and rep.pgl_goals >= 10:
            keys.append(
                f"Gól után nem alszanak el ({rep.pgl_goals} góljukból csak "
                f"{rep.pgl_quick} után jött gyors válasz) — a középkezdés "
                "utáni kapkodó gyorsindítás ellenük eladott labda.")

    # Fegyelem-esés: akinek a kiállításai a hajrában jönnek, az ellen a
    # meccs végén kell bevinni az egy-egy párharcokat.
    if rep.disc_fh_susp + rep.disc_sh_susp >= 3:
        if rep.disc_sh_susp - rep.disc_fh_susp >= 2:
            keys.append(
                f"A kiállításaik a 2. félidőben jönnek "
                f"({rep.disc_fh_susp} → {rep.disc_sh_susp}) — fáradtan "
                "szabálytalankodnak: a hajrában vigyétek be az egy-egy "
                "párharcokat, jönni fog az emberelőny.")
        elif rep.disc_fh_susp - rep.disc_sh_susp >= 2:
            keys.append(
                f"Az elején kemények ({rep.disc_fh_susp} → "
                f"{rep.disc_sh_susp} kiállítás) — a meccs elején "
                "provokáld ki a párharcokat, ott jön a korai emberelőny.")

    # Előny-őrzés: aki 3+ gólos vezetést is elenged, az ellen sosem
    # szabad feladni; aki mindig megtartja, azt nem szabad hagyni ellépni.
    if rep.lp_led >= 1:
        if rep.lp_blown >= 1:
            keys.append(
                f"3+ gólos vezetést is elengednek ({rep.lp_led} ellépésből "
                f"{rep.lp_blown} ment el, volt {rep.lp_biggest} gólos is) — "
                "hátrányban SE adjátok fel, ez a csapat visszahozható.")
        elif rep.lp_led >= 2:
            keys.append(
                f"Amit megfognak, megtartják: {rep.lp_led} meccsen léptek "
                "el 3+ góllal, és egyet sem engedtek el — nem szabad "
                "hagyni őket ellépni, mert onnan nincs visszaút.")

    # Labdabiztonság-esés: ha a 2. félidőre nő az eladás-ütemük, a hajrában
    # kell rájuk presselni — ott törékeny a kezük.
    if rep.tof_fh_poss_s >= 120.0 and rep.tof_sh_poss_s >= 120.0:
        _tof_fh = 60.0 * rep.tof_fh_to / rep.tof_fh_poss_s
        _tof_sh = 60.0 * rep.tof_sh_to / rep.tof_sh_poss_s
        if _tof_sh - _tof_fh >= 0.2:
            keys.append(
                f"A 2. félidőre megnő az eladás-ütemük ({_tof_fh:.1f} → "
                f"{_tof_sh:.1f} eladás/perc birtoklás) — a hajrában "
                "törékeny a labdabiztonságuk: a présnyomást a meccs "
                "második felére időzítsd.")

    # Időkérés-mérleg: működik-e a "mentő" időkérésük.
    if rep.to_broke + rep.to_failed >= 2:
        if rep.to_broke > rep.to_failed:
            keys.append(
                f"Az időkérésük működik ({rep.to_broke}/"
                f"{rep.to_broke + rep.to_failed} megtörte a sorozatot) — ha "
                "sorozatban vagy, számíts rá: legyen kész az időkérés "
                "UTÁNI első támadásod, hogy a lendület megmaradjon.")
        elif rep.to_failed > rep.to_broke:
            keys.append(
                f"Az időkérésük hatástalan ({rep.to_failed}/"
                f"{rep.to_broke + rep.to_failed} nem hozott fordulatot) — a "
                "megkezdett sorozatot az időkérésük után is tolhatod, ne "
                "állj le tőle.")

    # Védekezés-fellazulás: ha a faluk a 2. félidőre lazul, a hajrát kell
    # megtolni ellenük; ha szorosabbra vált, az elején kell előnyt szerezni.
    if rep.prf_fh_n >= 100 and rep.prf_sh_n >= 100 \
            and rep.prf_fh_sum_m > 0 and rep.prf_sh_sum_m > 0:
        _prf_fh = rep.prf_fh_sum_m / rep.prf_fh_n
        _prf_sh = rep.prf_sh_sum_m / rep.prf_sh_n
        _prf_d = _prf_sh - _prf_fh
        if _prf_d >= 0.5:
            keys.append(
                f"A védekezésük a 2. félidőre fellazul (átlag "
                f"{_prf_fh:.1f} → {_prf_sh:.1f} m a labdástól) — a hajrában "
                "nyílnak a rések: a meccs végét toljátok meg, ott jön a "
                "szabad lövő.")
        elif _prf_d <= -0.5:
            keys.append(
                f"A 2. félidőre szorosabbra húzzák a védekezést "
                f"({_prf_fh:.1f} → {_prf_sh:.1f} m) — az előnyt az első "
                "félidőben kell megszerezni, a hajrájuk kemény.")

    # Lövés-időzítés: az első hullámból élő lövők ellen a visszarendeződés,
    # a kivárók ellen a türelmes fal a kulcs.
    if rep.shtim_n >= 5 and rep.shtim_sum_s > 0:
        _sh_early_pct = 100.0 * rep.shtim_early / rep.shtim_n
        _sh_avg = rep.shtim_sum_s / rep.shtim_n
        if _sh_early_pct >= 45.0:
            keys.append(
                f"Az első hullámból lőnek (a lövéseik {_sh_early_pct:.0f}%-a "
                f"a támadás első 8 mp-ében) — a visszarendeződés ellenük "
                "életbiztosítás: lövés után azonnal hátra, az első "
                "passzsávot elvenni.")
        elif _sh_avg >= 22.0:
            keys.append(
                f"Kivárós lövők (átlag {_sh_avg:.0f} mp után lőnek) — a "
                "falad maradjon türelmes és fegyelmezett a támadás végéig: "
                "a hibára és a passzív-jel előtti kapkodásra játszanak.")

    # Passz-hossz: a hosszú-passzos, direkt játék elfogható; a rövid
    # kombináció présálló, de lassú.
    if rep.plen_n >= 15 and rep.plen_sum_m > 0:
        _pl_long_pct = 100.0 * rep.plen_long / rep.plen_n
        _pl_avg = rep.plen_sum_m / rep.plen_n
        if _pl_long_pct >= 30.0:
            keys.append(
                f"Hosszú passzokkal játszanak (a passzaik {_pl_long_pct:.0f}%-a "
                f"10 m fölötti, átlag {_pl_avg:.0f} m) — ülj rá a "
                "passzsávokra: a hosszú labda elfogható, és belőle azonnali "
                "kontra jön.")
        elif _pl_avg <= 6.0:
            keys.append(
                f"Rövid, biztonsági passzokkal kombinálnak (átlag "
                f"{_pl_avg:.0f} m) — a présre nehezen fognak hibázni: "
                "türelmes, zárt fal és a beálló-kapcsolat elvágása kell.")

    # Szerzés-magasság: ha elöl (letámadásból) szereznek sokat, a
    # kihozatalunknak készen kell állnia; ha csak hátul, elöl nem zavarnak.
    if rep.steal_n >= 4:
        _st_pct = 100.0 * rep.steal_high / rep.steal_n
        if _st_pct >= 35.0:
            keys.append(
                f"A szerzéseik {_st_pct:.0f}%-a ELÖL, letámadásból jön "
                f"({rep.steal_high}/{rep.steal_n}) — a labdakihozatalt "
                "készítsd elő: rövid, biztos passzok hátul, a kapus is "
                "játékban, szelep a szélen.")
        elif _st_pct <= 10.0 and rep.steal_n >= 6:
            keys.append(
                f"Elöl nem zavarnak (a szerzéseik csak {_st_pct:.0f}%-a "
                "elöl) — a hátsó építkezésed nyugodt lehet: időt hagynak "
                "a felállásra és a figura-indításra.")

    # Falba lövés: ha a lövéseik nagy része blokkon akad el, rosszul
    # előkészített lövésekkel élnek — a fegyelmezett blokk-fal megfogja őket.
    if rep.blk_for >= 4 and rep.blk_attempts > 0:
        _blk_pct = 100.0 * rep.blk_for / rep.blk_attempts
        if _blk_pct >= 20.0:
            weaknesses.append(
                f"A lövés-kísérleteik {_blk_pct:.0f}%-a blokkon akad el "
                f"({rep.blk_for}/{rep.blk_attempts}) — rosszul előkészített, "
                "kényszerű lövésekbe hajszolhatók.")
            keys.append(
                "Álljatok bele a lövéseikbe: a fegyelmezett kétkezes blokk "
                "ellenük kiemelt fegyver — a falba lőnek, ha nincs idejük "
                "elzárással tisztát csinálni.")

    # Passz-tempó: pörgetett labdajáratás fárasztja a falat; lassú, álló
    # járatás mellett a védelem békében felállhat.
    if rep.pt_poss_s >= 120.0 and rep.pt_passes > 0:
        _pt = 60.0 * rep.pt_passes / rep.pt_poss_s
        if _pt >= 22.0:
            keys.append(
                f"Pörgetik a labdát (átlag {_pt:.0f} passz/perc a "
                "birtoklásukban) — a falad sokat fog mozogni: fegyelmezett "
                "záródás és váltás-kommunikáció kell, különben megnyílik "
                "a rés.")
        elif _pt <= 12.0:
            keys.append(
                f"Lassan, állva járatják a labdát ({_pt:.0f} passz/perc) — "
                "kiszámítható támadójáték: a falad békében felállhat, és "
                "a passzsávokra rá lehet ülni labdaszerzésért.")

    # Területi fölény: hol zajlik a birtoklásuk — elöl nyomnak, vagy a
    # saját térfelükön ragadnak (kihozási gond → letámadható).
    if rep.tilt_frames >= 100:
        _tilt = 100.0 * rep.tilt_opp / rep.tilt_frames
        if _tilt >= 65.0:
            keys.append(
                f"A birtoklásuk {_tilt:.0f}%-a az ellenfél térfelén zajlik — "
                "elöl nyomnak: mély, türelmes fal kell, és a mögöttes "
                "terület a kontráidé.")
        elif _tilt <= 45.0:
            keys.append(
                f"A birtoklásuk a saját térfelükön ragad (csak {_tilt:.0f}% "
                "elöl) — kihozási gondjaik vannak: told fel a letámadást, "
                "már a kapus-indításnál zavarj.")

    # Támogatás-távolság: magára hagyott labdás ellen a prés működik;
    # szoros támogatás ellen a prés kockázatos (kijátsszák).
    if rep.sup_frames >= 100 and rep.sup_sum_m > 0:
        _sup_avg = rep.sup_sum_m / rep.sup_frames
        _sup_iso_pct = 100.0 * rep.sup_iso / rep.sup_frames
        if _sup_avg >= 7.0 or _sup_iso_pct >= 35.0:
            keys.append(
                f"A labdás játékosuk rendre magára marad (a legközelebbi "
                f"társ átlag {_sup_avg:.1f} m-re, az idő "
                f"{_sup_iso_pct:.0f}%-ában izolált) — a prés működik "
                "ellenük: letámadással kényszeríts egyéni megoldásokat "
                "és eladásokat.")
        elif _sup_avg <= 4.0:
            keys.append(
                f"Szorosan támogatják a labdást (átlag {_sup_avg:.1f} m a "
                "legközelebbi társ) — a prés kockázatos ellenük, rövid "
                "passzokkal kijátsszák: inkább zárt, fegyelmezett fal.")

    # Hajrá-emberük: aki a meccs végén gólt szerez — rá a hajrában
    # fokozott figyelem, akár emberfogás.
    if rep.clutch_scorers:
        top_cs = rep.clutch_scorers[0]
        if top_cs["goals"] >= 2:
            keys.append(
                f"A(z) {top_cs['player_id']}-es a hajrá-emberük "
                f"({top_cs['goals']} gól a meccsek végén) — a hajrában rá "
                "fokozott figyelem, szoros őrzés vagy emberfogás.")

    # Átmenet-támadás: ha sok labdaszerzést gyorsan gólra váltanak,
    # a labdabiztonság a kulcs ellenük.
    if rep.trans_steals >= 4 and rep.trans_quick_goals >= 2:
        conv = 100.0 * rep.trans_quick_goals / rep.trans_steals
        if conv >= 30.0:
            keys.append(
                f"A labdaszerzéseiket gyorsan gólra váltják "
                f"({rep.trans_quick_goals}/{rep.trans_steals}, "
                f"{conv:.0f}%) — labdabiztonság a saját térfélen, "
                "kockázatos keresztpasszt ne vállalj, és lövés után "
                "azonnal zárj vissza.")

    # Lövés-távolság profil: honnan lő a legtöbbet — a védekezés
    # súlypontjához (kifelé zárni az átlövőkre vagy a 6-ost erősíteni).
    _sr_total = rep.sr_close_shots + rep.sr_mid_shots + rep.sr_far_shots
    if _sr_total >= 8:
        _far_share = 100.0 * rep.sr_far_shots / _sr_total
        _close_share = 100.0 * rep.sr_close_shots / _sr_total
        _far_pct = (100.0 * rep.sr_far_goals / rep.sr_far_shots
                    if rep.sr_far_shots else 0.0)
        if _far_share >= 45.0:
            s_sr = f"Lövéseik {_far_share:.0f}%-a távolról (átlövés) esik"
            if rep.sr_far_shots:
                s_sr += f", {_far_pct:.0f}%-os gólaránnyal"
            s_sr += " — lépj ki az átlövőkre és blokkolj; "
            s_sr += ("gyenge a távoli gólarányuk, a kapus dolgozhat"
                     if _far_pct < 25.0 else "erős átlövők, aktív blokk kell")
            keys.append(s_sr + ".")
        elif _close_share >= 45.0:
            keys.append(
                f"Lövéseik {_close_share:.0f}%-a közelről (beálló/szélső, "
                "betörés) esik — a 6-os védelmét kell megerősíteni, "
                "beálló-őrzés és a betörési sávok zárása a kulcs.")

    # Kapusuk gyenge sávja: ahol a legkevésbé véd, oda érdemes lőni.
    _gk_bands = [
        ("close", "közelről (beálló/szélső/betörés)",
         rep.gk_close_faced, rep.gk_close_saves),
        ("mid", "közép-távból", rep.gk_mid_faced, rep.gk_mid_saves),
        ("far", "távolról (átlövés)", rep.gk_far_faced, rep.gk_far_saves),
    ]
    _gk_cand = [(lbl, fc, sv) for (_k, lbl, fc, sv) in _gk_bands if fc >= 4]
    if _gk_cand:
        _gk_worst = min(_gk_cand, key=lambda t: t[2] / t[1])
        _gk_lbl, _gk_fc, _gk_sv = _gk_worst
        _gk_pct = 100.0 * _gk_sv / _gk_fc
        # Csak akkor emeljük ki, ha tényleg gyenge (50% alatti védés).
        if _gk_pct < 50.0:
            keys.append(
                f"Kapusuk a(z) {_gk_lbl} lövésekre a leggyengébb "
                f"({_gk_pct:.0f}% védés, {_gk_sv}/{_gk_fc}) — a "
                "befejezéseket ebbe a sávba érdemes terelni.")

    # Kapu-sarok: ha a góljaik zöme egy oldalra megy, a mi kapusunk
    # felkészülhet rá (kiszámítható befejezés).
    _pl_total = rep.place_bal + rep.place_kozep + rep.place_jobb
    if _pl_total >= 6:
        _pl_bands = [("bal alsó/felső", rep.place_bal),
                     ("középre", rep.place_kozep),
                     ("jobb alsó/felső", rep.place_jobb)]
        _pl_dom = max(_pl_bands, key=lambda t: t[1])
        _pl_share = 100.0 * _pl_dom[1] / _pl_total
        if _pl_share >= 50.0:
            keys.append(
                f"Góljaik {_pl_share:.0f}%-a a(z) {_pl_dom[0]} kapuoldalra "
                f"megy ({_pl_dom[1]}/{_pl_total}) — a kapusunk erre "
                "készülhet, kiszámítható a befejezésük.")

    # Szélső-játék: erős szélső széthúzza a védelmet; gyenge szélsőre
    # ráengedhető a szög.
    if rep.wing_fin_shots >= 4:
        _wing_pct = 100.0 * rep.wing_fin_goals / rep.wing_fin_shots
        if _wing_pct >= 55.0:
            keys.append(
                f"Szélsőik veszélyesek ({rep.wing_fin_goals}/"
                f"{rep.wing_fin_shots}, {_wing_pct:.0f}% szélső-gólarány) — "
                "a szélső-védőnek ki kell lépnie és szűkíteni a szöget, a "
                "beadásokat is figyeld.")
        elif _wing_pct <= 25.0:
            keys.append(
                f"Szélső-befejezésük gyenge ({rep.wing_fin_goals}/"
                f"{rep.wing_fin_shots}, {_wing_pct:.0f}%) — a szélső lövést "
                "rá lehet engedni, befelé zárj a beállóra/átlövőre.")

    # Passz-irány: vertikális (előre) vagy türelmes (oldalra) építkezés.
    if rep.pdir_passes >= 30:
        _fwd_pct = 100.0 * rep.pdir_forward / rep.pdir_passes
        if _fwd_pct >= 45.0:
            keys.append(
                f"Vertikálisan játszanak ({_fwd_pct:.0f}% előre-passz) — "
                "gyorsan visszazárni, a mélységi passzsávokat elvenni.")
        elif _fwd_pct <= 20.0:
            keys.append(
                f"Türelmesen köröztetik a labdát ({_fwd_pct:.0f}% "
                "előre-passz) — a beállóra és az elzárásokra figyelj, ne "
                "húzódj szét idő előtt.")

    # Gólpassz-forrás: ha a gól-előkészítés zöme egy helyről jön, azt a
    # forrást kell elvenni.
    _asrc_total = rep.asrc_szel + rep.asrc_kozep + rep.asrc_hatso
    if _asrc_total >= 4:
        _asrc = [("a szélről (beadás) — a szélső-beadást és a szélső átvételét zárd",
                  rep.asrc_szel),
                 ("középről (beálló/betörés-kiadás) — a beálló-őrzés és a betörési sávok zárása",
                  rep.asrc_kozep),
                 ("a hátsó sorból (átlövő-kiadás) — az átlövőre kilépés és a passzsáv elvétele",
                  rep.asrc_hatso)]
        _asrc_dom = max(_asrc, key=lambda t: t[1])
        _asrc_share = 100.0 * _asrc_dom[1] / _asrc_total
        if _asrc_share >= 50.0:
            keys.append(
                f"Góljaik {_asrc_share:.0f}%-át {_asrc_dom[0]}.")

    # Második roham: mennyire harcolnak a kimaradt lövés utáni lepattanóért.
    if rep.sc_misses >= 6:
        _sc_pct = 100.0 * rep.sc_second / rep.sc_misses
        if _sc_pct >= 25.0:
            _sc_g = (f", ebből {rep.sc_goals} gól" if rep.sc_goals else "")
            keys.append(
                f"Harcolnak a lepattanóért ({rep.sc_second}/{rep.sc_misses} "
                f"kimaradás után újra lőnek, {_sc_pct:.0f}%{_sc_g}) — a lövés "
                "után is fogd le a beállót és tisztázd a lepattanót, ne fordulj "
                "ki idő előtt.")
        elif _sc_pct <= 8.0:
            keys.append(
                f"A kimaradt lövések után nem mennek a lepattanóra "
                f"({_sc_pct:.0f}%) — a védés/blokk után azonnal indíthatsz "
                "gyors ellentámadást.")

    # Védekezési vonal magassága: felfutó fal mögé lefutás/átemelés, mély
    # fal ellen türelmes játék és beálló.
    if rep.defline_frames >= 100:
        _dl = rep.defline_sum_m / rep.defline_frames
        from .defense import DEF_LINE_DEEP_M, DEF_LINE_HIGH_M
        if _dl >= DEF_LINE_HIGH_M:
            keys.append(
                f"Felfutó, agresszív falat húznak (átlag {_dl:.1f} m-re a "
                "kaputól) — a hátuk mögötti tér a fegyver: lefutás, "
                "átemelés, gyors indítás, egy az egy elleni betörés.")
        elif _dl <= DEF_LINE_DEEP_M:
            keys.append(
                f"Mélyen, passzívan védekeznek (átlag {_dl:.1f} m-re a "
                "kaputól) — türelmes felállt játék, a beálló mozgatása és "
                "a távoli lövés kényszerítése töri meg őket.")

    # Védelmi tömörség: tömör fal mellett a szélek, széthúzott mellett a
    # közép nyílik.
    if rep.defw_frames >= 100 and rep.defw_sum_m > 0:
        _dw = rep.defw_sum_m / rep.defw_frames
        from .defense import DEF_WIDTH_NARROW_M, DEF_WIDTH_WIDE_M
        if _dw <= DEF_WIDTH_NARROW_M:
            keys.append(
                f"Tömör, keskeny falat húznak (átlag {_dw:.0f} m széles) — "
                "a szélek nyitva vannak: gyors oldalváltások, szélső-"
                "befejezések és beadások ellenük a recept.")
        elif _dw >= DEF_WIDTH_WIDE_M:
            keys.append(
                f"Széthúzott falat húznak (átlag {_dw:.0f} m széles) — a "
                "közép nyílik: betörés a réseken, beálló-játék és "
                "elzárás-leválás középen.")

    # Kapus-kimozdulás: a kint álló kapus átemelhető, a vonalon
    # maradó ellen a lepattanóra kell menni.
    if rep.gk_depth_frames >= 100:
        gk_depth = rep.gk_depth_sum_m / rep.gk_depth_frames
        if gk_depth >= 1.5:
            keys.append(
                f"Kapusuk kint áll (átlag {gk_depth:.1f} m-re a "
                "gólvonaltól) — az átemelés és a lob a fegyver, főleg "
                "kontránál.")
        elif gk_depth <= 0.8:
            keys.append(
                f"Kapusuk a vonalon marad (átlag {gk_depth:.1f} m) — "
                "közelről a felső sarkok nyílnak, és minden lepattanóra "
                "rá kell mozdulni.")

    # Lövési zónák: ha egy zóna dominál (a lövések ≥40%-a, legalább 3 lövésből),
    # konkrét védekezési kulcsot adunk rá.
    total_shots = sum(z["shots"] for z in rep.shot_zones.values())
    if total_shots >= 3:
        zone, rec = next(iter(rep.shot_zones.items()))
        share = 100.0 * rec["shots"] / total_shots
        if share >= 40.0:
            keys.append(f"Lövéseik zöme ({share:.0f}%) innen jön: {zone} — ott zárj szorosabban.")
        for zone, rec in rep.shot_zones.items():
            if rec["shots"] >= 3 and rec["goals"] / rec["shots"] >= 0.6:
                strengths.append(f"Nagyon eredményesek innen: {zone} "
                                 f"({rec['goals']}/{rec['shots']} gól).")
                break

    # Kapusuk: erős/gyenge védés-hatékonyság és a verhető zóna.
    if rep.gk_on_target >= 4:
        save_pct = 100.0 * rep.gk_saves / rep.gk_on_target
        if save_pct >= 40.0:
            strengths.append(f"Jó kapus ({save_pct:.0f}% védés) — a rossz "
                             "helyzetű lövést megfogja.")
        elif save_pct <= 20.0:
            weaknesses.append(f"Bizonytalan kapus ({save_pct:.0f}% védés) — "
                              "érdemes kapura menni.")
    # Megmentett gólok: ha a kapusuk a vártnál többet kap, támadható.
    if rep.gk_xg_prevented / max(1, rep.matches) <= -1.0:
        weaknesses.append(
            f"Kapusuk a helyzetekhez képest sokat kap "
            f"({rep.gk_xg_prevented / rep.matches:+.1f} gól/meccs a "
            "várthoz képest) — a kapura lövés kifizetődő.")
    # Hárított xG: a kapusuk a nehéz lövéseket is fogja-e.
    if rep.gk_xg_saved / max(1, rep.matches) >= 1.0:
        strengths.append(
            f"Kapusuk a nehéz lövéseket is fogja (hárított xG: "
            f"{rep.gk_xg_saved / rep.matches:.1f}/meccs) — a helyzet "
            "önmagában nem gól ellenük.")
    # Ziccer-mérleg: bravúros kapus / kihagyós befejezés.
    if rep.gk_big_saves >= 2:
        strengths.append(f"Kapusuk ziccert is fog ({rep.gk_big_saves} "
                         "bravúr-védés) — a tiszta helyzetet is pontosan, "
                         "sarokra kell befejezni.")
    if rep.big_total >= 4 and rep.big_missed / rep.big_total >= 0.5:
        weaknesses.append(
            f"Ziccereket hagynak ki: {rep.big_total} nagy helyzetükből "
            f"{rep.big_missed} kimaradt — szoros fal mellett a nagy "
            "helyzet sem garantált gól náluk.")
    # Kapus-indításuk: ha a mért indítások fele gyors, a lövés utáni
    # visszarendeződés létkérdés ellenük.
    if rep.gk_outlets >= 2 and rep.gk_outlet_fast / rep.gk_outlets >= 0.5:
        avg = rep.gk_outlet_sum_s / rep.gk_outlets
        keys.append(
            f"Kapusuk gyorsan indít (átlag {avg:.0f} mp alatt a felezőn) "
            "— minden lövés után AZONNAL vissza: a lassú visszafutást "
            "kontrával büntetik.")
    # A hetes-dobójuk: ha kirajzolódik, ki áll oda, a kapus az ő
    # szokásaira készülhet — gyenge mérlegnél ez bizalom-kérdés is.
    if rep.seven_takers and rep.seven_takers[0]["attempts"] >= 2:
        top_s = rep.seven_takers[0]
        sent7 = (f"A heteseiket a(z) {top_s['player_id']}. játékos dobja "
                 f"({top_s['goals']}/{top_s['attempts']} gól) — a kapus "
                 "az ő szokásaira készüljön.")
        if (top_s["attempts"] >= 3
                and top_s["goals"] / top_s["attempts"] <= 0.5):
            sent7 += " A mérlege gyenge: a kapus bátran vállalhat mozgást."
        # Ha az iránya kiszámítható (a mért hetesei 70%-a egy sávba
        # megy), a kapus konkrét utasítást kap.
        dirs7 = top_s.get("dirs") or {}
        n_dirs = sum(dirs7.values())
        if n_dirs >= 3:
            best_d = max(dirs7, key=dirs7.get)
            if dirs7[best_d] / n_dirs >= 0.7:
                from .rules import SEVEN_DIR_HU
                hu = SEVEN_DIR_HU[best_d]
                sent7 += (f" Kiszámítható: a mért hetesei "
                          f"{100.0 * dirs7[best_d] / n_dirs:.0f}%-ban "
                          f"{hu} mennek — a kapus induljon {hu}.")
        keys.append(sent7)
    # A beállójuk: ha egyértelmű, ki az, célzott utasítás jár hozzá.
    pivots = [tid for tid, p_ in (rep.positions or {}).items()
              if p_ == "beálló"]
    if len(pivots) == 1:
        keys.append(
            f"A beállójuk a(z) {pivots[0]}. játékos — az elzárásaira "
            "lépj ki korán, és tartsd folyamatos fizikai kontaktban: "
            "ha ő labdát kap 6 méteren, az már késő.")
    # Szélső-függés: honnan jönnek a góljaik a posztok szerint.
    if rep.wing_total_goals >= 6:
        wing_share = rep.wing_goals / rep.wing_total_goals
        if wing_share >= 0.4:
            keys.append(
                f"A góljaik {100.0 * wing_share:.0f}%-át a szélsőik "
                "szerzik — zárd a szélső sávot: a szélre kilépő védő "
                "ne késsen, és a bedobásnál is figyelj rájuk.")
        elif wing_share <= 0.1 and any(
                p_ == "szélső" for p_ in (rep.positions or {}).values()):
            keys.append(
                "A szélsőik alig vannak játékban — a faluk középen "
                "dől el: szűkíthetsz, a sávot vállalhatod.")
    # Támadás-szélesség: széthúzott vagy beszűkült támadójáték.
    if rep.width_frames >= 100 and rep.width_sum_m > 0:
        avg_w = rep.width_sum_m / rep.width_frames
        if avg_w >= 14.0:
            keys.append(
                f"Szélesen támadnak (átlag {avg_w:.0f} m-re húzzák "
                "szét a falat) — a szélső védőid ne csússzanak be: a "
                "kilépés fegyelme ellenük a kulcs.")
        elif avg_w <= 9.0:
            keys.append(
                f"Szűken támadnak (átlag {avg_w:.0f} m) — bátran "
                "szűkíthetsz: a fal középen dolgozzon, a szélre alig "
                "jár labda.")
    # A legjobb figurájuk: begyakorolt minta, ami gólt hoz — a fal
    # akkor véd ellene, ha az első passzokról felismeri.
    if rep.best_fig_attacks >= 3 and rep.best_fig_goals >= 2:
        keys.append(
            f"Van egy figurájuk, ami működik: {rep.best_fig_attacks} "
            f"támadásból {rep.best_fig_goals} gól — nézd vissza a "
            "figura-klipeket, és az első passzokról ismerjétek fel: "
            "aki előbb lép, az töri meg.")
    # Előny-kezelés: időhúzás vezetve, kapkodás hátrányban.
    if (rep.lead_attacks >= 3 and rep.trail_attacks >= 3):
        lead_avg = rep.lead_sum_s / rep.lead_attacks
        trail_avg = rep.trail_sum_s / rep.trail_attacks
        if lead_avg - trail_avg >= 8.0:
            keys.append(
                f"Előnyben húzzák az időt (átlag {lead_avg:.0f} mp-es "
                f"támadások, hátrányban {trail_avg:.0f}) — ne engedd "
                "őket előnybe: az elején tartsd magas tempón a meccset, "
                "mert vezetve altatják.")
        if trail_avg <= 12.0 and lead_avg - trail_avg >= 8.0:
            keys.append(
                "Hátrányban kapkodnak (rövid, kényszerített támadások) "
                "— ha nálatok az előny, a türelmes védekezés hibákba "
                "kergeti őket.")
    # A szünet utáni kezdés: ki üt először a 2. félidőben.
    if rep.restart_matches >= 1:
        d_rs = rep.restart_against - rep.restart_for
        if d_rs >= 3:
            keys.append(
                f"Az öltözőből rosszul jönnek ki: a 2. félidő első 5 "
                f"percében a mérlegük {rep.restart_for}–"
                f"{rep.restart_against} — a szünet után TI kezdjetek "
                "magas tempóval, ott nyitva vannak.")
        elif d_rs <= -3:
            keys.append(
                f"A szünet után ők ütnek először ({rep.restart_for}–"
                f"{rep.restart_against} az első 5 percben) — a 2. "
                "félidő eleje ellenük kiemelt figyelmet kér: kész "
                "tervvel gyertek ki az öltözőből.")
    # A félidő-zárás: ki üt utoljára a szünet előtt.
    if rep.fhc_matches >= 1:
        d_fhc = rep.fhc_against - rep.fhc_for
        if d_fhc >= 3:
            keys.append(
                f"Az 1. félidő hajráját elengedik: a szünet előtti 5 "
                f"percben a mérlegük {rep.fhc_for}–{rep.fhc_against} — "
                "a félidő végén nyomjatok rá, ott olcsó gólok vannak, "
                "és a lendület is veletek megy az öltözőbe.")
        elif d_fhc <= -3:
            keys.append(
                f"A félidő-zárásuk erős ({rep.fhc_for}–{rep.fhc_against} "
                "a szünet előtti 5 percben) — a félidő utolsó perceiben "
                "TILOS kiengedni: náluk ott szokott eldőlni a lendület.")
    # Kezdés-profil: milyen a meccs nyitánya — gyorsan vezetést szereznek-e.
    if rep.open_first_matches >= 3:
        _of_rate = 100.0 * rep.open_first_yes / rep.open_first_matches
        _of_bal = rep.open_for - rep.open_against
        if _of_rate >= 65.0 or _of_bal >= 3:
            keys.append(
                f"Erős kezdők: a meccsek {_of_rate:.0f}%-ában ők szerzik az "
                f"első gólt (korai mérleg {rep.open_for}–{rep.open_against}) — "
                "az első percektől koncentrálj, ne engedd, hogy elhúzzanak; a "
                "nyitógólért külön meg kell küzdeni.")
        elif _of_rate <= 35.0 or _of_bal <= -3:
            keys.append(
                f"Lassan kezdenek: csak a meccsek {_of_rate:.0f}%-ában övék az "
                f"első gól (korai mérleg {rep.open_for}–{rep.open_against}) — "
                "menj rájuk az elején, a korai előny megtörheti a tervüket.")
    # Visszarendeződés: lassú védelem ellen a gyors indítás a fegyver.
    if rep.rec_transitions >= 4:
        rec_avg = rep.rec_sum_s / rep.rec_transitions
        if rec_avg >= 5.0:
            keys.append(
                f"Lassan rendeződnek vissza (átlag {rec_avg:.1f} mp a "
                "felálló védelemig) — labdaszerzés után AZONNAL indíts: "
                "az első 5 másodperc a tiéd.")
        elif rec_avg <= 3.0:
            keys.append(
                f"Villámgyorsan visszaérnek (átlag {rec_avg:.1f} mp) — "
                "a kontra ellenük ritkán jön össze, építs türelmes "
                "felállt támadásra.")
    # Támadás-eredet: ha a góljaik jelentős része labdaszerzésből jön,
    # a labdabiztonság ellenük duplán számít.
    ao = rep.attack_origins or {}
    total_goals_ao = sum(v.get("goals", 0) for v in ao.values())
    steal_goals = (ao.get("labdaszerzés") or {}).get("goals", 0)
    if total_goals_ao >= 5 and steal_goals / total_goals_ao >= 0.5:
        keys.append(
            f"A góljaik {100.0 * steal_goals / total_goals_ao:.0f}%-a "
            "labdaszerzésből indul — a labdabiztonság ellenük duplán "
            "számít: kevesebb kényszerített passz, biztos befejezés.")
    # Lövés-választás: átlagos helyzet-érték lövésenként — megmutatja,
    # válogatósak-e vagy távolról is vállalkoznak.
    if rep.shots >= 10 and rep.xg > 0:
        avg_xg = rep.xg / rep.shots
        if avg_xg <= 0.10:
            keys.append(
                f"Sok kis esélyű lövést vállalnak (átlag "
                f"{avg_xg:.2f} xG/lövés) — a távoli lövést engedheted, "
                "a betörést és a beállót zárd.")
        elif avg_xg >= 0.18:
            keys.append(
                f"Válogatósak: csak jó helyzetből lőnek (átlag "
                f"{avg_xg:.2f} xG/lövés) — fegyelmezett fal és a "
                "passzív-jel kivárása ellenük a recept.")
    # Hidegvérű befejező: aki tartósan a helyzetei felett teljesít,
    # annak a fél-helyzeteit sem szabad megengedni.
    if rep.shooter_overperf and rep.shooter_overperf[0]["diff"] >= 1.0:
        top_o = rep.shooter_overperf[0]
        keys.append(
            f"A(z) {top_o['player_id']}. játékos a helyzetei FELETT "
            f"teljesít ({top_o['diff']:+.1f} gól az xG-hez képest) — ne "
            "hagyd tisztán: a fél-helyzetét is belövi.")
    # A hetes-kiharcolójuk: akit rendre lerántanak — ellene csak
    # szabálytalanság nélkül szabad védekezni.
    if rep.seven_earners and rep.seven_earners[0]["earned"] >= 2:
        top_e = rep.seven_earners[0]
        keys.append(
            f"A heteseiket jellemzően a(z) {top_e['player_id']}. játékos "
            f"harcolja ki ({top_e['earned']} hetes) — vele szemben "
            "fegyelmezetten, kéz nélkül védekezz: a betörését tested "
            "helyzetével lassítsd, ne fogással.")
    # A kiállítás-kiharcolójuk: aki rendre 2 percet hoz nekik — vele
    # szemben a belemenés dupla hiba (hetes helyett emberhátrány).
    if rep.susp_earners and rep.susp_earners[0]["earned"] >= 2:
        top_se = rep.susp_earners[0]
        keys.append(
            f"A kiállításokat jellemzően a(z) {top_se['player_id']}. "
            f"játékos harcolja ki ({top_se['earned']} kiharcolt 2 perc) "
            "— a betörésénél a test tartsa fel, a kéz maradjon lent: "
            "ellene a belemenés emberhátrányt ér.")
    # A fegyelmezetlen védőjük: aki rendre kiül — támadd egy-egyben,
    # a következő belemenése újabb emberelőnyt hoz nekünk.
    if rep.susp_players and rep.susp_players[0]["suspensions"] >= 2:
        top_sp = rep.susp_players[0]
        keys.append(
            f"A(z) {top_sp['player_id']}. játékosuk fegyelmezetlen "
            f"({top_sp['suspensions']} kiállítás) — támadd őt egy az "
            "egyben: nyomás alatt szabálytalankodik, és a harmadik "
            "2 perc végleges kizárás.")
    # A kontra befejezője: ha a lerohanás-gólok zömét ugyanaz a játékos
    # szerzi, a visszafutásnál ő az első számú felvevendő ember.
    if rep.fb_finishers and rep.fb_finishers[0]["goals"] >= 2:
        top_f = rep.fb_finishers[0]
        keys.append(
            f"A lerohanásaikat a(z) {top_f['player_id']}. játékos fejezi "
            f"be ({top_f['goals']} kontra-gól) — labdavesztés után őt "
            "keresd meg először a visszafutásnál.")
    # Az indítás célpontja: ha a hosszú passzok zöme ugyanahhoz a
    # játékoshoz megy, az ő megelőzése öli meg a kontrát.
    if rep.gk_outlets >= 2 and rep.gk_outlet_targets:
        top_t = rep.gk_outlet_targets[0]
        if top_t["n"] >= 2 and top_t["n"] / rep.gk_outlets >= 0.5:
            keys.append(
                f"Az indításaik célpontja a(z) {top_t['player_id']}. "
                f"játékos ({top_t['n']}/{rep.gk_outlets} indítás) — a "
                "visszafutásnál őt kell először felvenni: az elébe "
                "lépés labdaszerzés.")
    # Lövő-szokás: ha a fő lövőjük jellemzően egy zónából dolgozik,
    # arra a helyzetre külön lehet készülni.
    if rep.shooter_zones:
        best = _top_shooter_habit(rep)
        if best:
            pid, z, n, total = best
            keys.append(
                f"A(z) {pid}. játékos lövéseinek {100.0 * n / total:.0f}%-a "
                f"innen jön: {z} — erre a helyzetre külön készülj "
                "(fal-állás, kapus-pozíció).")
    # A fő lövőjük fáradása: hajrá-kulcs, ha a 2. félidőben lelassul.
    if rep.shooter_zones and rep.shooter_fades:
        per_shots: dict = {}
        for rec_sz in rep.shooter_zones:
            per_shots[rec_sz["player_id"]] = (
                per_shots.get(rec_sz["player_id"], 0) + rec_sz["shots"])
        top_pid = max(per_shots.items(), key=lambda kv: kv[1])[0]
        fade = next((f for f in rep.shooter_fades
                     if f["player_id"] == top_pid and f["n"]), None)
        if fade:
            avg_drop = fade["drop_sum_pct"] / fade["n"]
            if avg_drop >= SHOOTER_FADE_PCT:
                keys.append(
                    f"A fő lövőjük ({top_pid}. játékos) elfárad: a második "
                    f"félidőben átlag {avg_drop:.0f}%-kal lassabb — a "
                    "hajrában friss védőt rá, és kényszerítsd "
                    "visszafutásra.")
    # A gól-tengely: ha egy (gólpasszoló -> lövő) páros 3+ gólt hozott,
    # a passzsáv elvágása többet ér, mint a lövő önmagában.
    if rep.assist_pairs:
        top_ap = max(rep.assist_pairs, key=lambda pr: pr["goals"])
        if top_ap["goals"] >= 3:
            keys.append(
                f"A góljaik tengelye a(z) {top_ap['from']}. → "
                f"{top_ap['to']}. páros ({top_ap['goals']} gól) — a "
                "passzsáv elvágása (elé lépés, letámadás) többet ér, "
                "mint a lövő önálló fogása.")
    if rep.gk_conceded_zones:
        zone, n = max(rep.gk_conceded_zones.items(), key=lambda kv: kv[1])
        if n >= 2:
            keys.append(f"Kapusuk innen kapta a legtöbb gólt: {zone} "
                        f"({n} gól) — támadd onnan.")
    # Zóna szerinti védés-hatékonyság: a legalacsonyabb védés%-ú, legalább
    # 3 lövést kapott sarok — konkrét célpont a lövőknek.
    if rep.gk_on_target_zones:
        cand = []
        for z, faced in rep.gk_on_target_zones.items():
            if faced >= 3:
                conc = rep.gk_conceded_zones.get(z, 0)
                cand.append((z, 100.0 * (faced - conc) / faced, faced))
        if cand:
            z, pct, faced = min(cand, key=lambda t: t[1])
            if pct <= 50.0:
                keys.append(f"Kapusuk leggyengébb sarka: {z} "
                            f"({pct:.0f}% védés, {faced} lövésből) — "
                            "ide lőjetek.")

    # Emberelőny: ha jól váltják gólra, a kiállítás ellenük duplán fáj.
    if rep.pp_shots >= 3:
        pp_eff = 100.0 * rep.pp_goals / rep.pp_shots
        if pp_eff >= 60.0:
            strengths.append(f"Emberelőnyben nagyon hatékonyak "
                             f"({rep.pp_goals}/{rep.pp_shots} gól) — "
                             "kerüld a felesleges kiállítást.")
        elif pp_eff <= 25.0:
            weaknesses.append(f"Az emberelőnyt rosszul használják ki "
                              f"({pp_eff:.0f}%) — hátrányban is védekezhetsz "
                              "bátran.")
    if rep.sh_seconds >= 60.0 and rep.sh_conceded >= 2:
        per_min = 60.0 * rep.sh_conceded / rep.sh_seconds
        if per_min >= 1.0:
            weaknesses.append("Emberhátrányban összeomlanak "
                              f"({rep.sh_conceded} kapott gól "
                              f"{rep.sh_seconds / 60:.1f} perc alatt).")

    # Védekezés-váltás minta: hátrányban ismétlődően ugyanarra a formára
    # váltanak → az edző előre begyakorolhatja az ellenszert.
    trailing = [s_ for s_ in rep.defense_switches if s_.get("margin", 0) < 0]
    if trailing:
        tally: dict = {}
        for s_ in trailing:
            tally[s_["to"]] = tally.get(s_["to"], 0) + 1
        to, n = max(tally.items(), key=lambda kv: kv[1])
        if n >= 2:
            keys.append(f"Amikor hátrányban vannak, {to} védekezésre "
                        f"váltanak ({n}×) — legyen begyakorolt támadásod "
                        "ellene.")

    # 7 a 6: ha érdemben használják (meccsenként >= 20 mp), készülj rá.
    if rep.empty_net_s / max(1, rep.matches) >= 20.0:
        strengths.append(f"Tudatosan játszanak 7 a 6 ellen "
                         f"(~{rep.empty_net_s / rep.matches:.0f} mp/meccs).")
        keys.append("Lehozott kapussal támadnak — labdaszerzés után az "
                    "ÜRES KAPURA azonnal dobhatsz, gyakorold a hosszú indítást.")
    # Tempó-profil: a csapat támadás/perc mutatója (csak érdemi, 20+
    # mért percnél). A meccs-szintű küszöbök (2,2 / 1,4 összesített)
    # fele jut egy csapatra: 1,1 fölött tempós, 0,7 alatt lassú.
    if rep.pace_minutes >= 20.0:
        per_min = rep.pace_attacks / rep.pace_minutes
        if per_min >= 1.1:
            keys.append(
                f"Tempósan játszanak ({per_min:.1f} támadás/perc) — mély "
                "rotációval bírd a tempójukat, és ha megcsúszol, "
                "lassítsd le a meccset.")
        elif per_min <= 0.7:
            keys.append(
                f"Lassú meccseket játszanak ({per_min:.1f} támadás/perc) "
                "— a tempóváltás és a gyors középkezdés kizökkenti őket.")
    # A 7 a 6 időzítése: ha mintázata van, előre lehet rá készülni.
    if rep.en_windows >= 2 and rep.en_trailing / rep.en_windows >= 0.7:
        keys.append(
            f"A 7 a 6-ot hátrányban húzzák elő ({rep.en_trailing}/"
            f"{rep.en_windows} szakasz) — ha vezetsz ellenük, számíts a "
            "lehozott kapusra: beszéld meg előre a hosszú dobás jogát.")
    # Ha ez már gólokba is került nekik, az gyengeség: büntethető szokás.
    if rep.empty_net_conceded >= 2:
        weaknesses.append(
            f"A 7 a 6-juk kockázatos: {rep.empty_net_conceded} gólt "
            "kaptak üres kapura — a labdaszerzés utáni gyors dobás "
            "ellenük kiemelten kifizetődő.")

    if not keys:
        keys.append("Kevés a minta — több meccsük felderítése pontosít.")
    return strengths, weaknesses, keys


def scout_team(match: Match, team: Team, config: Optional[TacticsConfig] = None) -> ScoutingReport:
    """Egy csapat felderítő jelentése EGY meccsből."""
    config = config or TacticsConfig()
    team_name = match.meta.home_team if team == Team.HOME else match.meta.away_team

    # Támadó identitás.
    pct = phase_percentages(match, config)
    attack_key = Phase.HOME_ATTACK.value if team == Team.HOME else Phase.AWAY_ATTACK.value
    tempo = compute_tempo(match, config)

    # Védekezés.
    dist = _defense_distribution(match, team, config)
    dmain = next(iter(dist), "—")

    # Támadó zóna + figurák.
    summ = compute_team_summary(match, team)
    figures = discover_setplays(match, config)
    team_attacks = sum(1 for s in segment_attacks(match, config) if s.team == team)

    # Befejezés (események).
    events = detect_events(match, config)
    shots = sum(1 for e in events if e.type in (EventType.SHOT, EventType.GOAL) and e.team == team)
    goals = sum(1 for e in events if e.type == EventType.GOAL and e.team == team)
    turnovers = sum(1 for e in events if e.type == EventType.TURNOVER and e.team == team)
    eff = 100.0 * goals / shots if shots else 0.0

    rep = ScoutingReport(
        team=team.value,
        team_name=team_name,
        attack_share_pct=round(pct.get(attack_key, 0.0), 1),
        fast_break_pct=round(_fast_break_pct(match, team, config), 1),
        avg_ball_speed_ms=round(tempo.avg_ball_speed_ms, 2),
        avg_attack_duration_s=round(tempo.avg_attack_duration_s, 2),
        defense_main=dmain,
        defense_distribution=dist,
        attack_centroid_x=round(summ.avg_centroid_x, 1),
        attack_centroid_y=round(summ.avg_centroid_y, 1),
        num_figures=figures.num_figures,
        attacks=team_attacks,
        shots=shots,
        goals=goals,
        turnovers=turnovers,
        shot_efficiency_pct=round(eff, 1),
        shot_zones=_shot_zones(match, team, config),
        key_players=[asdict(k) for k in _key_players(match, team, config)],
    )
    # A felderített csapat KAPUSÁNAK mutatói (ha van kapus-jelölés) —
    # ebből jön a "kapusuk innen verhető" kulcs.
    try:
        from .goalkeeper import detect_empty_net, goalkeeper_stats
        gk = goalkeeper_stats(match, config).get(team.value)
        if gk:
            rep.gk_on_target = gk["on_target"]
            rep.gk_saves = gk["saves"]
            rep.gk_conceded_zones = dict(gk["conceded_zones"])
            rep.gk_on_target_zones = dict(gk.get("on_target_zones", {}))
        rep.empty_net_s = round(sum(
            w["duration_s"] for w in detect_empty_net(match, config)
            if w["team"] == team.value), 1)
        from .goalkeeper import empty_net_goals
        rep.empty_net_conceded = empty_net_goals(
            match, config)[team.value]["conceded_empty"]
        from .goalkeeper import empty_net_context
        enc = empty_net_context(match, config)[team.value]
        rep.en_windows = enc["windows"]
        rep.en_trailing = enc["trailing"]
        rep.en_endgame = enc["endgame"]
        from .attack_types import match_pace
        pc = match_pace(match, config)
        if pc.get("available"):
            rep.pace_attacks = pc[f"{team.value}_attacks"]
            rep.pace_minutes = pc["duration_min"]
        from .attack_types import attack_origins
        rep.attack_origins = {
            k: dict(v) for k, v in
            attack_origins(match, config)[team.value].items()}
        from .defense import transition_recovery
        trr = transition_recovery(match, config)[team.value]
        rep.rec_transitions = trr["transitions"]
        rep.rec_sum_s = trr["sum_s"]
        rep.rec_slow = trr["slow"]
        from .roles import estimate_positions
        rep.positions = {tid: r["poszt"] for tid, r in
                         estimate_positions(match, config)
                         .get(team.value, {}).items()}
        wings = {tid for tid, p_ in rep.positions.items()
                 if p_ == "szélső"}
        for rec_sh in match_xg(match, config).get("shooters", []):
            if rec_sh["team"] != team.value:
                continue
            rep.wing_total_goals += rec_sh["goals"]
            if rec_sh["player_id"] in wings:
                rep.wing_goals += rec_sh["goals"]
            poszt_sh = rep.positions.get(rec_sh["player_id"])
            if poszt_sh and rec_sh["goals"]:
                rep.post_goals[poszt_sh] = (
                    rep.post_goals.get(poszt_sh, 0) + rec_sh["goals"])
    except Exception:
        pass
    try:
        from .attack_types import attack_efficiency, attack_mix
        rep.attack_mix = attack_mix(match, config).get(team.value, {})
        rep.attack_efficiency = attack_efficiency(match, config).get(
            team.value, {})
        from .attack_types import fast_break_finishers
        rep.fb_finishers = [
            dict(f) for f in
            fast_break_finishers(match, config)[team.value]]
        from .rules import seven_meter_outcomes
        sv: dict = {}
        for sm in seven_meter_outcomes(match, config):
            if sm["team"] != team.value or sm.get("shooter_id") is None:
                continue
            rec7 = sv.setdefault(sm["shooter_id"],
                                 {"attempts": 0, "goals": 0,
                                  "dirs": {}})
            rec7["attempts"] += 1
            rec7["goals"] += int(sm["outcome"] == "gól")
            if sm.get("irany"):
                rec7["dirs"][sm["irany"]] = \
                    rec7["dirs"].get(sm["irany"], 0) + 1
        rep.seven_takers = [
            {"player_id": pid, **r}
            for pid, r in sorted(sv.items(),
                                 key=lambda kv: -kv[1]["attempts"])]
        from .rules import seven_meter_earners
        rep.seven_earners = [
            dict(e) for e in
            seven_meter_earners(match, config)[team.value]]
        from .rules import suspension_earners
        rep.susp_earners = [
            dict(e) for e in
            suspension_earners(match, config)[team.value]]
        from .rules import suspended_players
        rep.susp_players = [
            dict(e) for e in
            suspended_players(match, config)[team.value]]
        from .defense import marking_pairs
        rep.markers = [
            {"player_id": (d["defender_jersey"]
                           if d["defender_jersey"] is not None
                           else d["defender"]),
             "frames": d["frames"], "dist_sum": d["dist_sum"]}
            for d in marking_pairs(match, config)[team.value]["defenders"]]
        from .attack_types import pivot_usage
        pu = pivot_usage(match, config)[team.value]
        rep.pivot_total_attacks = pu["attacks"]
        rep.pivot_attacks = pu["pivot_attacks"]
        rep.pivot_goals = pu["pivot_goals"]
        rep.pivot_other_goals = pu["other_goals"]
        from .defense import breakthrough_lanes
        bl = breakthrough_lanes(match, config)[team.value]
        rep.break_entries = bl["entries"]
        rep.break_lanes = {k: dict(v) for k, v in bl["lanes"].items()}
        from .attack_types import pass_chains
        pch = pass_chains(match, config)[team.value]
        rep.pass_attacks = pch["attacks"]
        rep.pass_total = pch["passes"]
        rep.pass_buckets = {
            k: {"attacks": v["attacks"], "goals": v["goals"]}
            for k, v in pch["buckets"].items()}
        from .stats import rotation_depth
        rd = rotation_depth(match)[team.value]
        if rd["used"] >= 6:
            rep.rotation_used_sum = rd["used"]
            rep.rotation_regulars_sum = rd["regulars"]
            rep.rotation_matches = 1
        from .defense import ball_winners
        rep.ball_winners = [
            {"player_id": (w["jersey"] if w["jersey"] is not None
                           else w["player_id"]),
             "steals": w["steals"]}
            for w in ball_winners(match, config)[team.value]["players"]]
        from .defense import turnover_players
        rep.turnover_players = [
            {"player_id": (w["jersey"] if w["jersey"] is not None
                           else w["player_id"]),
             "losses": w["losses"]}
            for w in turnover_players(match, config)[team.value]["players"]]
        from .momentum import clutch_scorers
        rep.clutch_scorers = [
            {"player_id": (w["jersey"] if w["jersey"] is not None
                           else w["player_id"]),
             "goals": w["goals"]}
            for w in clutch_scorers(match, config)[team.value]["players"]]
        from .event_detection import goal_concentration
        rep.scorer_goals = list(
            goal_concentration(match, config)[team.value]["scorers"])
        from .decisions import support_distance
        suprec = support_distance(match, config)[team.value]
        rep.sup_frames = suprec["frames"]
        if suprec["avg_m"] is not None:
            rep.sup_sum_m = round(suprec["avg_m"] * suprec["frames"], 1)
            rep.sup_iso = suprec["iso_frames"]
        from .tactics import field_tilt
        ftrec = field_tilt(match, config)[team.value]
        rep.tilt_frames = ftrec["frames"]
        rep.tilt_opp = ftrec["opp_half_frames"]
        from .defense import defensive_width
        dwrec = defensive_width(match, config)[team.value]
        if dwrec["avg_width_m"] is not None:
            rep.defw_sum_m = round(
                dwrec["avg_width_m"] * dwrec["frames"], 1)
            rep.defw_frames = dwrec["frames"]
        from .tactics import pass_tempo
        ptrec = pass_tempo(match, config)[team.value]
        rep.pt_passes = ptrec["passes"]
        rep.pt_poss_s = ptrec["poss_s"]
        from .defense import blocked_shot_rate
        brrec = blocked_shot_rate(match, config)[team.value]
        rep.blk_for = brrec["blocked"]
        rep.blk_attempts = brrec["attempts"]
        from .defense import steal_height
        strec = steal_height(match, config)[team.value]
        rep.steal_n = strec["steals"]
        rep.steal_high = strec["high_steals"]
        from .event_detection import pass_length
        plrec = pass_length(match, config)[team.value]
        rep.plen_n = plrec["passes"]
        if plrec["avg_m"] is not None:
            rep.plen_sum_m = round(plrec["avg_m"] * plrec["passes"], 1)
            rep.plen_long = plrec["long_passes"]
        from .attack_types import shot_timing
        shrec = shot_timing(match, config)[team.value]
        rep.shtim_n = shrec["shots"]
        if shrec["avg_s"] is not None:
            rep.shtim_sum_s = round(shrec["avg_s"] * shrec["shots"], 1)
            rep.shtim_early = shrec["early"]
        from .defense import pressure_fade
        prfrec = pressure_fade(match, config)[team.value]
        if prfrec["fh_m"] is not None:
            rep.prf_fh_sum_m = round(prfrec["fh_m"] * prfrec["fh_frames"], 1)
            rep.prf_fh_n = prfrec["fh_frames"]
        if prfrec["sh_m"] is not None:
            rep.prf_sh_sum_m = round(prfrec["sh_m"] * prfrec["sh_frames"], 1)
            rep.prf_sh_n = prfrec["sh_frames"]
        from .stoppages import timeout_record
        torec = timeout_record(match, config)[team.value]
        rep.to_n = torec["timeouts"]
        rep.to_broke = torec["broke"]
        rep.to_failed = torec["failed"]
        from .defense import turnover_fade
        tofrec = turnover_fade(match, config)[team.value]
        if tofrec["rise_per_min"] is not None:
            rep.tof_fh_to = tofrec["fh_to"]
            rep.tof_fh_poss_s = tofrec["fh_poss_s"]
            rep.tof_sh_to = tofrec["sh_to"]
            rep.tof_sh_poss_s = tofrec["sh_poss_s"]
        from .goalkeeper import gk_save_fade
        gsfrec = gk_save_fade(match, config)[team.value]
        if gsfrec["drop_pp"] is not None:
            rep.gsf_fh_faced = gsfrec["fh_faced"]
            rep.gsf_fh_saves = gsfrec["fh_saves"]
            rep.gsf_sh_faced = gsfrec["sh_faced"]
            rep.gsf_sh_saves = gsfrec["sh_saves"]
        from .rules import discipline_fade
        dfrec = discipline_fade(match, config)[team.value]
        rep.disc_fh_susp = dfrec["fh_susp"]
        rep.disc_sh_susp = dfrec["sh_susp"]
        from .rules import seven_meter_defense
        s7drec = seven_meter_defense(match, config)[team.value]
        rep.s7d_faced = s7drec["faced"]
        rep.s7d_saved = s7drec["saved"]
        from .xg import miss_punishment
        bcprec = miss_punishment(match, config)[team.value]
        rep.bcp_misses = bcprec["misses"]
        rep.bcp_punished = bcprec["punished"]
        from .attack_types import team_pace_fade
        tpfrec = team_pace_fade(match, config)[team.value]
        rep.tpf_fh_attacks = tpfrec["fh_attacks"]
        rep.tpf_fh_min = tpfrec["fh_min"]
        rep.tpf_sh_attacks = tpfrec["sh_attacks"]
        rep.tpf_sh_min = tpfrec["sh_min"]
        from .goalkeeper import gk_change_effect
        gkcrec = gk_change_effect(match, config)[team.value]
        if gkcrec["changes"]:
            rep.gkc_changes = gkcrec["changes"]
            rep.gkc_pre_faced = gkcrec["pre_faced"]
            rep.gkc_pre_saves = gkcrec["pre_saves"]
            rep.gkc_post_faced = gkcrec["post_faced"]
            rep.gkc_post_saves = gkcrec["post_saves"]
        from .momentum import close_game_record
        cgrec = close_game_record(match, config)[team.value]
        if cgrec["verdict"] == "szoros győzelem":
            rep.cg_wins = 1
        elif cgrec["verdict"] == "szoros vereség":
            rep.cg_losses = 1
        elif cgrec["verdict"] == "döntetlen":
            rep.cg_draws = 1
        from .momentum import halftime_comeback
        htcrec = halftime_comeback(match, config)[team.value]
        if htcrec["verdict"] is not None:
            rep.htc_behind = 1
            if htcrec["verdict"] == "fordította":
                rep.htc_turned = 1
            elif htcrec["verdict"] == "mentette":
                rep.htc_saved = 1
        from .momentum import parity_breaks
        pbrec = parity_breaks(match, config)[team.value]
        rep.pb_ties = pbrec["ties"]
        rep.pb_won = pbrec["won"]
        from .momentum import run_containment
        rnrec = run_containment(match, config)[team.value]
        rep.rn_made = rnrec["made"]
        rep.rn_made_goals = rnrec["made_goals"]
        rep.rn_suffered = rnrec["suffered"]
        rep.rn_suffered_goals = rnrec["suffered_goals"]
        from .xg import big_save_momentum
        bsmrec = big_save_momentum(match, config)[team.value]
        rep.bsm_saves = bsmrec["saves"]
        rep.bsm_sparked = bsmrec["sparked"]
        from .xg import finish_fade
        ffrec = finish_fade(match, config)[team.value]
        if ffrec["drop_pp"] is not None:
            rep.ff_fh_shots = ffrec["fh_shots"]
            rep.ff_fh_goals = ffrec["fh_goals"]
            rep.ff_sh_shots = ffrec["sh_shots"]
            rep.ff_sh_goals = ffrec["sh_goals"]
        from .xg import shot_accuracy
        sarec = shot_accuracy(match, config)[team.value]
        rep.ac_attempts = sarec["attempts"]
        rep.ac_on_target = sarec["on_target"]
        from .attack_types import attack_side_bias
        sbrec = attack_side_bias(match, config)[team.value]
        rep.sb_left = sbrec["left"]
        rep.sb_center = sbrec["center"]
        rep.sb_right = sbrec["right"]
        from .attack_types import attack_rhythm
        arrec = attack_rhythm(match, config)[team.value]
        rep.ar_n = arrec["n"]
        rep.ar_sum_s = arrec["sum_s"]
        rep.ar_sumsq_s = arrec["sumsq_s"]
        from .xg import shot_concentration
        screc = shot_concentration(match, config)[team.value]
        rep.sc_shots = screc["shots"]
        rep.sc_top_shots = screc["top_shots"]
        from .goalkeeper import gk_weak_side
        gwrec = gk_weak_side(match, config)[team.value]
        rep.gw_bal = gwrec["bal"]
        rep.gw_kozep = gwrec["közép"]
        rep.gw_jobb = gwrec["jobb"]
        from .defense import turnover_timing
        ttrec = turnover_timing(match, config)[team.value]
        rep.tt_timed = ttrec["timed"]
        rep.tt_early = ttrec["early"]
        from .decisions import pass_security_under_pressure
        psrec = pass_security_under_pressure(match, config)[team.value]
        rep.ps_press_passes = psrec["press_passes"]
        rep.ps_press_to = psrec["press_to"]
        rep.ps_free_passes = psrec["free_passes"]
        rep.ps_free_to = psrec["free_to"]
        from .defense import second_chance_allowed
        scarec = second_chance_allowed(match, config)[team.value]
        rep.sca_opp_misses = scarec["opp_misses"]
        rep.sca_allowed = scarec["allowed"]
        rep.sca_goals = scarec["allowed_goals"]
        from .attack_types import assist_reliance
        adrec = assist_reliance(match, config)[team.value]
        rep.ad_goals = adrec["goals"]
        rep.ad_assisted = adrec["assisted"]
        from .tactics import tilt_fade
        tfrec = tilt_fade(match, config)[team.value]
        rep.tf_fh_frames = tfrec["fh_frames"]
        rep.tf_fh_opp = tfrec["fh_opp"]
        rep.tf_sh_frames = tfrec["sh_frames"]
        rep.tf_sh_opp = tfrec["sh_opp"]
        from .goalkeeper import gk_outlet_length
        gorec = gk_outlet_length(match, config)[team.value]
        rep.gko_outlets = gorec["outlets"]
        rep.gko_long = gorec["long"]
        from .defense import turnover_punishment
        tpurec = turnover_punishment(match, config)[team.value]
        rep.tpu_turnovers = tpurec["turnovers"]
        rep.tpu_punished = tpurec["punished"]
        from .defense import conceded_side_bias
        csbrec = conceded_side_bias(match, config)[team.value]
        rep.csb_left = csbrec["left"]
        rep.csb_center = csbrec["center"]
        rep.csb_right = csbrec["right"]
        from .momentum import drought_anatomy
        darec = drought_anatomy(match, config)[team.value]
        rep.da_drought_s = darec["drought_s"]
        rep.da_shots = darec["shots"]
        from .defense import wall_gaps
        wgrec = wall_gaps(match, config)[team.value]
        rep.wg_frames = wgrec["frames"]
        rep.wg_wide = wgrec["wide"]
        from .tactics import attack_motion
        amrec = attack_motion(match, config)[team.value]
        rep.am_dist_m = amrec["dist_m"]
        rep.am_time_s = amrec["time_s"]
        from .goalkeeper import gk_outlet_security
        gosrec = gk_outlet_security(match, config)[team.value]
        rep.gos_outlets = gosrec["outlets"]
        rep.gos_lost = gosrec["lost"]
        from .defense import pivot_defense
        pdrec = pivot_defense(match, config)[team.value]
        rep.pd_pivot_attacks = pdrec["pivot_attacks"]
        rep.pd_pivot_goals = pdrec["pivot_goals"]
        rep.pd_other_attacks = pdrec["other_attacks"]
        rep.pd_other_goals = pdrec["other_goals"]
        from .xg import shot_release
        srrec = shot_release(match, config)[team.value]
        rep.sr_shots = srrec["shots"]
        rep.sr_quick = srrec["quick"]
        from .momentum import restart_speed
        rsrec = restart_speed(match, config)[team.value]
        rep.rs_restarts = rsrec["restarts"]
        rep.rs_fast = rsrec["fast"]
        rep.rs_sum_s = rsrec["sum_s"]
        from .attack_types import assist_concentration
        acrec = assist_concentration(match, config)[team.value]
        rep.ac_assists = acrec["assists"]
        rep.ac_top_assists = acrec["top_assists"]
        from .attack_types import goal_buildup
        gbrec = goal_buildup(match, config)[team.value]
        rep.gb_goals = gbrec["goals"]
        rep.gb_short = gbrec["short"]
        rep.gb_long = gbrec["long"]
        from .goalkeeper import gk_break_response
        gkbrec = gk_break_response(match, config)[team.value]
        rep.gkb_fast_faced = gkbrec["fast_faced"]
        rep.gkb_fast_saves = gkbrec["fast_saves"]
        rep.gkb_set_faced = gkbrec["set_faced"]
        rep.gkb_set_saves = gkbrec["set_saves"]
        from .attack_types import side_switching
        sswrec = side_switching(match, config)[team.value]
        rep.ssw_passes = sswrec["passes"]
        rep.ssw_switches = sswrec["switches"]
        from .attack_types import screen_usage
        scurec = screen_usage(match, config)[team.value]
        rep.scu_shots = scurec["shots"]
        rep.scu_screened = scurec["screened"]
        from .defense import screen_defense
        scdrec = screen_defense(match, config)[team.value]
        rep.scd_screened_shots = scdrec["screened_shots"]
        rep.scd_screened_goals = scdrec["screened_goals"]
        rep.scd_open_shots = scdrec["open_shots"]
        rep.scd_open_goals = scdrec["open_goals"]
        from .attack_types import pass_risk
        prkrec = pass_risk(match, config)[team.value]
        rep.prk_long_tries = prkrec["long_tries"]
        rep.prk_long_to = prkrec["long_to"]
        rep.prk_short_tries = prkrec["short_tries"]
        rep.prk_short_to = prkrec["short_to"]
        from .defense import counter_press
        cprrec = counter_press(match, config)[team.value]
        rep.cpr_turnovers = cprrec["turnovers"]
        rep.cpr_regained = cprrec["regained"]
        from .momentum import clutch_shot_quality
        csqall = clutch_shot_quality(match, config)
        if csqall.get("available"):
            csqrec = csqall[team.value]
            rep.csq_early_shots = csqrec["early_shots"]
            rep.csq_early_xg = csqrec["early_xg"]
            rep.csq_clutch_shots = csqrec["clutch_shots"]
            rep.csq_clutch_xg = csqrec["clutch_xg"]
        from .momentum import post_goal_lapses
        pglrec = post_goal_lapses(match, config)[team.value]
        rep.pgl_goals = pglrec["goals"]
        rep.pgl_quick = pglrec["quick_replies"]
        from .momentum import lead_protection
        lprec = lead_protection(match, config)[team.value]
        if lprec["led"]:
            rep.lp_led = 1
            rep.lp_blown = 1 if lprec["blown"] else 0
            rep.lp_biggest = lprec["max_lead"]
        from .goalkeeper import gk_positioning
        gp = gk_positioning(match, config)[team.value]
        if gp["avg_depth_m"] is not None:
            rep.gk_depth_sum_m = round(
                gp["avg_depth_m"] * gp["frames"], 1)
            rep.gk_depth_frames = gp["frames"]
        from .attack_types import transition_offense
        to_ = transition_offense(match, config)[team.value]
        rep.trans_steals = to_["steals"]
        rep.trans_quick_goals = to_["quick_goals"]
        from .attack_types import shot_ranges
        sr = shot_ranges(match, config)[team.value]
        rep.sr_close_shots = sr["close"]["shots"]
        rep.sr_close_goals = sr["close"]["goals"]
        rep.sr_mid_shots = sr["mid"]["shots"]
        rep.sr_mid_goals = sr["mid"]["goals"]
        rep.sr_far_shots = sr["far"]["shots"]
        rep.sr_far_goals = sr["far"]["goals"]
        from .goalkeeper import gk_save_ranges
        gsr = gk_save_ranges(match, config)[team.value]
        rep.gk_close_faced = gsr["close"]["faced"]
        rep.gk_close_saves = gsr["close"]["saves"]
        rep.gk_mid_faced = gsr["mid"]["faced"]
        rep.gk_mid_saves = gsr["mid"]["saves"]
        rep.gk_far_faced = gsr["far"]["faced"]
        rep.gk_far_saves = gsr["far"]["saves"]
        from .attack_types import goal_placement
        gp = goal_placement(match, config)[team.value]
        rep.place_bal = gp["bal"]
        rep.place_kozep = gp["közép"]
        rep.place_jobb = gp["jobb"]
        from .attack_types import wing_finishing
        wf = wing_finishing(match, config)[team.value]
        rep.wing_fin_shots = wf["shots"]
        rep.wing_fin_goals = wf["goals"]
        from .attack_types import pass_direction
        pdr = pass_direction(match, config)[team.value]
        rep.pdir_forward = pdr["forward"]
        rep.pdir_passes = pdr["passes"]
        rep.pdir_prog_sum = round(
            (pdr["avg_progress_m"] or 0.0) * pdr["passes"], 1)
        from .attack_types import assist_sources
        asr = assist_sources(match, config)[team.value]
        rep.asrc_szel = asr["szél"]
        rep.asrc_kozep = asr["közép"]
        rep.asrc_hatso = asr["hátsó"]
        from .attack_types import second_chance
        scr = second_chance(match, config)[team.value]
        rep.sc_misses = scr["misses"]
        rep.sc_second = scr["second_chances"]
        rep.sc_goals = scr["second_goals"]
        from .defense import defensive_line_height
        dlh = defensive_line_height(match, config)[team.value]
        if dlh["avg_height_m"] is not None:
            rep.defline_sum_m = round(
                dlh["avg_height_m"] * dlh["frames"], 1)
            rep.defline_frames = dlh["frames"]
        from .rules import detect_powerplay
        rep.suspensions = sum(
            1 for w in detect_powerplay(match)
            if w["team_down"] == team.value)
        from .halftime import second_half_start
        shs = second_half_start(match, config)
        if shs is not None:
            other = "away" if team.value == "home" else "home"
            rep.restart_for = shs[team.value]
            rep.restart_against = shs[other]
            rep.restart_matches = 1
        from .halftime import first_half_close
        fhcr = first_half_close(match, config)
        if fhcr is not None:
            other = "away" if team.value == "home" else "home"
            rep.fhc_for = fhcr[team.value]
            rep.fhc_against = fhcr[other]
            rep.fhc_matches = 1
        from .momentum import opening_profile
        opr = opening_profile(match, config)[team.value]
        if opr["scores_first"] is not None:
            rep.open_first_matches = 1
            rep.open_first_yes = 1 if opr["scores_first"] else 0
            rep.open_for = opr["early_for"]
            rep.open_against = opr["early_against"]
        from .attack_types import attack_width
        aw = attack_width(match, config)[team.value]
        rep.width_frames = aw["frames"]
        if aw["avg_width_m"] is not None:
            rep.width_sum_m = round(aw["avg_width_m"] * aw["frames"], 1)
        from .setplays import setplay_efficiency
        rows_fig = setplay_efficiency(match, config).get(team.value) or []
        best_fig = max(rows_fig, key=lambda r: r["goals"], default=None)
        if best_fig is not None and best_fig["goals"] >= 1:
            rep.best_fig_attacks = best_fig["attacks"]
            rep.best_fig_goals = best_fig["goals"]
        from .attack_types import pace_by_score
        pbs = pace_by_score(match, config)[team.value]
        rep.lead_attacks = pbs["leading"]["attacks"]
        rep.lead_sum_s = pbs["leading"]["sum_s"]
        rep.trail_attacks = pbs["trailing"]["attacks"]
        rep.trail_sum_s = pbs["trailing"]["sum_s"]
    except Exception:
        pass
    try:
        from .xg import match_xg
        trec = match_xg(match, config)["teams"][team.value]
        rep.xg = trec["xg"]
        rep.xg_diff = trec["diff"]
        from .xg import BIG_CHANCE_XG, big_saves, missed_big_chances
        rep.big_total = sum(
            1 for sh in match_xg(match, config).get("shots", [])
            if sh["team"] == team.value
            and sh.get("xg", 0.0) >= BIG_CHANCE_XG)
        rep.big_missed = sum(1 for m in missed_big_chances(match, config)
                             if m["team"] == team.value)
        # A lövő az ellenfél — a védés a felderített csapat kapusáé.
        rep.gk_big_saves = sum(1 for b in big_saves(match, config)
                               if b["team"] != team.value)
        from .xg import xg_saved
        rep.gk_xg_saved = xg_saved(match, config)[team.value]
        from .xg import xg_prevented
        rep.gk_xg_prevented = xg_prevented(
            match, config)[team.value]["prevented"]
        from .goalkeeper import outlet_speed
        orec = outlet_speed(match, config)[team.value]
        rep.gk_outlets = orec["outlets"]
        rep.gk_outlet_sum_s = orec["sum_s"]
        rep.gk_outlet_fast = orec["fast"]
        rep.gk_outlet_targets = [dict(t) for t in orec.get("targets", [])]
        # Lövő-szokások: azonosított lövőik lövései zóna szerint.
        goal_x = config.attacks_toward_x(team)
        hab: dict = {}
        for sh in match_xg(match, config).get("shots", []):
            if sh["team"] != team.value or sh.get("player_id") is None:
                continue
            z = _shot_zone(sh["x"], sh["y"], goal_x)
            hab[(sh["player_id"], z)] = hab.get((sh["player_id"], z), 0) + 1
        rep.shooter_zones = [
            {"player_id": pid, "zone": z, "shots": n}
            for (pid, z), n in sorted(hab.items(), key=lambda kv: -kv[1])]
        # A lövőik mért tempó-esése (a fő lövő elleni hajrá-kulcshoz).
        from .stats import player_fatigue
        shooter_ids = {pid for (pid, _z) in hab}
        rep.shooter_fades = [
            {"player_id": f["track_id"],
             "drop_sum_pct": f["drop_pct"], "n": 1}
            for f in player_fatigue(match)
            if f["team"] == team.value and f["track_id"] in shooter_ids]
        from .event_detection import assist_network
        rep.assist_pairs = [dict(pr) for pr in
                            assist_network(match, config)[team.value]["pairs"]]
        rep.shooter_overperf = [
            {"player_id": rec["player_id"], "diff": rec["diff"]}
            for rec in match_xg(match, config).get("shooters", [])
            if rec["team"] == team.value]
    except Exception:
        pass
    try:
        from .defense import defense_analysis
        drec = defense_analysis(match, config)[team.value]
        rep.def_shots_against = drec["shots_against"]
        rep.def_goals_against = drec["goals_against"]
        rep.def_free_shots = drec["free_shots"]
        rep.def_zones = {z: dict(v) for z, v in drec["zones"].items()}
        rep.xga_sum = round(float(drec.get("xg_against", 0.0)), 2)
        from .defense import transition_defense
        trec = transition_defense(match, config)[team.value]
        rep.transition_turnovers = trec["turnovers"]
        rep.transition_goals_against = trec["transition_goals_against"]
        from .defense import turnover_zones
        tzrec = turnover_zones(match, config)[team.value]
        rep.turnover_total = tzrec["total"]
        rep.turnover_front = tzrec["zones"].get("támadó", 0)
        from .stats import possession_share
        rep.possession_pct = possession_share(match, config)[team.value]["pct"]
        from .event_detection import assist_network
        leaders = assist_network(match, config)[team.value]["leaders"]
        if leaders:
            rep.top_assist_id = leaders[0]["player_id"]
            rep.top_assist_count = leaders[0]["assists"]
        from .event_detection import pass_network
        pnet = pass_network(match, config)[team.value]
        rep.pass_pairs = list(pnet["pairs"])
        rep.pass_total = pnet["total_passes"]
        from .momentum import clutch_performance
        cp = clutch_performance(match, config)
        if cp.get("available") and cp.get("close"):
            own = cp[team.value]["goals"]
            opp = cp["away" if team == Team.HOME else "home"]["goals"]
            rep.clutch_goals_for = own
            rep.clutch_goals_against = opp
            rep.clutch_matches = 1
        from .momentum import goal_droughts
        rep.drought_longest_s = goal_droughts(match, config)[
            team.value]["longest_s"]
        from .defense import detect_blocks
        blk = detect_blocks(match, config)[team.value]
        rep.blocks = blk["blocks"]
        rep.blockers = [dict(b) for b in blk.get("blockers", [])]
        from .tactics import slow_attacks
        sarec = slow_attacks(match, config)[team.value]
        rep.slow_attacks_total = sarec["attacks"]
        rep.slow_attacks_slow = sarec["slow"]
        from .attack_types import attack_duration_efficiency
        de = attack_duration_efficiency(match, config)[team.value]
        rep.duration_eff = {k: {"attacks": v["attacks"],
                                "goals": v["goals"]} for k, v in de.items()}
        from .tactics import efficiency_vs_formation
        efrec = efficiency_vs_formation(match, config)[team.value]
        rep.vs_formation = {k: {"shots": v["shots"], "goals": v["goals"]}
                            for k, v in efrec.items()}
        from .momentum import goal_responses
        grec = goal_responses(match, config)[team.value]
        rep.response_n = grec["responses"]
        rep.response_sum_s = round(
            (grec["avg_s"] or 0.0) * grec["responses"], 1)
        from .tactics import attack_sides
        asrec = attack_sides(match, config)[team.value]
        n_side = asrec["frames"]
        rep.side_frames = {k: round(asrec[k] * n_side / 100.0)
                           for k in ("bal", "közép", "jobb")}
        from .defense import pressure_finishing
        pf = pressure_finishing(match, config)[team.value]
        rep.fin_free_shots = pf["free"]["shots"]
        rep.fin_free_goals = pf["free"]["goals"]
        rep.fin_cov_shots = pf["covered"]["shots"]
        rep.fin_cov_goals = pf["covered"]["goals"]
        from .event_detection import shot_speeds
        sprec = shot_speeds(match, config)["teams"][team.value]
        rep.shot_speed_n = sprec["n"]
        rep.shot_speed_sum_kmh = round(sprec["avg_kmh"] * sprec["n"], 1)
        rep.shot_speed_max_kmh = sprec["max_kmh"]
        from .event_detection import shot_speed_fade
        fdrec = shot_speed_fade(match, config)[team.value]
        rep.ssf_fh_n = fdrec["fh_n"]
        rep.ssf_fh_sum_kmh = round(fdrec["fh_avg_kmh"] * fdrec["fh_n"], 1)
        rep.ssf_sh_n = fdrec["sh_n"]
        rep.ssf_sh_sum_kmh = round(fdrec["sh_avg_kmh"] * fdrec["sh_n"], 1)
        from .momentum import halftime_score, score_progression
        hs = halftime_score(match, config)
        if hs is not None:
            fin = score_progression(match, config)["final"]
            own_i = 0 if team == Team.HOME else 1
            own_key = "home" if team == Team.HOME else "away"
            opp_key = "away" if team == Team.HOME else "home"
            rep.fh_goals_for = hs[own_key]
            rep.fh_goals_against = hs[opp_key]
            rep.sh_goals_for = fin[own_i] - hs[own_key]
            rep.sh_goals_against = fin[1 - own_i] - hs[opp_key]
        from .defense import defensive_pressure
        pr = defensive_pressure(match, config)[team.value]["avg_pressure_m"]
        if pr is not None:
            rep.defensive_pressure_m = pr
    except Exception:
        pass
    try:
        from .playmaker import playmaker_dependency
        prec = playmaker_dependency(match, config)[team.value]
        rep.playmaker_id = prec["playmaker"]
        rep.playmaker_involvement_pct = prec["involvement_pct"]
        rep.playmaker_drop = prec["shot_rate_drop"]
        rep.playmaker_dependency = prec["dependency"]
    except Exception:
        pass
    try:
        from .substitutions import substitution_impact
        goals_sorted = sorted(
            (e.t, e.team) for e in detect_events(match, config)
            if e.type == EventType.GOAL)

        def _margin_at(t: int) -> int:
            own = sum(1 for gt, gteam in goals_sorted
                      if gt <= t and gteam == team)
            opp = sum(1 for gt, gteam in goals_sorted
                      if gt <= t and gteam != team)
            return own - opp

        si = substitution_impact(match, config)
        for ev in si["events"]:
            if ev["team"] != team.value:
                continue
            rep.sub_rotations += 1
            if _margin_at(ev["t"]) < 0:
                rep.sub_trailing += 1
            rep.sub_after_for += ev["goals_for_after"]
            rep.sub_after_against += ev["goals_against_after"]
    except Exception:
        pass
    try:
        rep.defense_switches = formation_switch_profile(match, team, config)
    except Exception:
        pass
    try:
        from .rules import powerplay_efficiency
        eff = powerplay_efficiency(match, config).get(team.value)
        if eff:
            rep.pp_shots = eff["pp_shots"]
            rep.pp_goals = eff["pp_goals"]
            rep.sh_conceded = eff["sh_conceded"]
            rep.sh_seconds = eff["sh_seconds"]
    except Exception:
        pass
    s, w, k = _coach_keys(rep)
    rep.strengths, rep.weaknesses, rep.keys_to_game = s, w, k
    return rep



# A fő lövő "elfárad" kulcs küszöbe: ekkora 2. félidei tempó-esés
# (%) fölött érdemes a hajrára külön készülni ellene.
SHOOTER_FADE_PCT = 15.0


def _top_shooter_habit(rep) -> tuple | None:
    """A legkoncentráltabb fő lövő: (player_id, zóna, lövés a zónából,
    összes lövés), ha 4+ lövésének 60%+-a egy zónából jön — különben None.
    A kulcs, a narratíva és a kliens-csempe közös küszöbe."""
    per: dict = {}
    for rec in (rep.shooter_zones or []):
        pz = per.setdefault(rec["player_id"], {})
        pz[rec["zone"]] = pz.get(rec["zone"], 0) + int(rec["shots"])
    best = None
    for pid, zn in per.items():
        total = sum(zn.values())
        z, n = max(zn.items(), key=lambda kv: kv[1])
        if total >= 4 and n / total >= 0.6 and (best is None or n > best[2]):
            best = (pid, z, n, total)
    return best


# "Ágyú" szerep: e lövés-sebesség (km/h) fölött a lövő külön említést
# érdemel a kulcsember-listában — a kapusnak reakció-terv kell rá.
CANNON_KMH = 85.0


def match_key_players(match: Match, config=None) -> dict:
    """Kulcsemberek egy meccsből: kinél dől el a játék — szereponként a
    legjellemzőbb játékos, csak érdemi mintánál. A jelentés Kulcsemberek
    táblája és az API ugyanebből dolgozik (azonos küszöbök a felderítési
    kulcsokkal).

    Visszatérés: {"home"/"away": [{"role", "player_id", "detail"}]}
    """
    config = config or TacticsConfig()
    out: dict = {"home": [], "away": []}

    # Poszt-becslés: ha van elég minta, a mérleg mellé odaírjuk a
    # posztot is ("4 gól / 6 lövés · átlövő").
    try:
        from .roles import estimate_positions
        _posts = estimate_positions(match, config)
    except Exception:
        _posts = {"home": {}, "away": {}}

    def add(side, role, pid, detail):
        p_ = (_posts.get(side) or {}).get(pid)
        if p_ is not None and role != "Bravúr-kapus":
            detail = f"{detail} · {p_['poszt']}"
        out[side].append({"role": role, "player_id": pid, "detail": detail})

    try:
        from .xg import match_xg
        r = match_xg(match, config)
        for side in ("home", "away"):
            top = next((rec for rec in r.get("shooters", [])
                        if rec["team"] == side), None)
            if top and top["shots"] >= 3:
                add(side, "Fő lövő", top["player_id"],
                    f"{top['goals']} gól / {top['shots']} lövés")
    except Exception:
        pass
    try:
        from .defense import detect_blocks
        blk = detect_blocks(match, config)
        for side in ("home", "away"):
            bl = blk[side].get("blockers") or []
            if bl and bl[0]["blocks"] >= 2:
                add(side, "A fal kulcsa", bl[0]["player_id"],
                    f"{bl[0]['blocks']} blokk")
    except Exception:
        pass
    try:
        from .rules import seven_meter_outcomes
        sv: dict = {}
        for sm in seven_meter_outcomes(match, config):
            if sm.get("shooter_id") is None:
                continue
            k = (sm["team"], sm["shooter_id"])
            a, g = sv.get(k, (0, 0))
            sv[k] = (a + 1, g + int(sm["outcome"] == "gól"))
        for side in ("home", "away"):
            cand = [(pid, ag) for (tm, pid), ag in sv.items() if tm == side]
            if cand:
                pid, (a, g) = max(cand, key=lambda c: c[1][0])
                if a >= 2:
                    add(side, "Hetes-dobó", pid, f"{g}/{a} gól")
    except Exception:
        pass
    try:
        from .attack_types import fast_break_finishers
        fb = fast_break_finishers(match, config)
        for side in ("home", "away"):
            fl = fb.get(side) or []
            if fl and fl[0]["goals"] >= 2:
                add(side, "Kontra-befejező", fl[0]["player_id"],
                    f"{fl[0]['goals']} kontra-gól")
    except Exception:
        pass
    try:
        from .rules import seven_meter_earners
        sme = seven_meter_earners(match, config)
        for side in ("home", "away"):
            el = sme.get(side) or []
            if el and el[0]["earned"] >= 2:
                add(side, "Hetes-kiharcoló", el[0]["player_id"],
                    f"{el[0]['earned']} kiharcolt hetes")
    except Exception:
        pass
    try:
        from .rules import suspension_earners
        sue = suspension_earners(match, config)
        for side in ("home", "away"):
            el = sue.get(side) or []
            if el and el[0]["earned"] >= 2:
                add(side, "2 perc-hozó", el[0]["player_id"],
                    f"{el[0]['earned']} kiharcolt kiállítás")
    except Exception:
        pass
    try:
        from .goalkeeper import outlet_speed
        osp = outlet_speed(match, config)
        for side in ("home", "away"):
            tg = osp[side].get("targets") or []
            if tg and tg[0]["n"] >= 2:
                add(side, "Indítás-célpont", tg[0]["player_id"],
                    f"{tg[0]['n']} indítás")
    except Exception:
        pass
    try:
        from .event_detection import assist_network
        net = assist_network(match, config)
        for side in ("home", "away"):
            pairs = net[side]["pairs"]
            if pairs and pairs[0]["goals"] >= 2:
                top = pairs[0]
                # A tengely két emberből áll — a lövő a "játékos", az
                # előkészítő a mérlegben szerepel.
                add(side, "Gól-tengely", top["to"],
                    f"a(z) {top['from']}. játékostól, {top['goals']} gól")
    except Exception:
        pass
    try:
        from .xg import match_xg as _mxg_kp
        r_kp = _mxg_kp(match, config)
        for side in ("home", "away"):
            best = None
            for rec in r_kp.get("shooters", []):
                if rec["team"] != side:
                    continue
                if best is None or rec["diff"] > best["diff"]:
                    best = rec
            if best is not None and best["diff"] >= 1.0:
                add(side, "Hidegvérű befejező", best["player_id"],
                    f"{best['diff']:+.1f} gól az xG-hez képest")
    except Exception:
        pass
    try:
        from .goalkeeper import goalkeeper_stats
        from .xg import big_saves
        gstats = goalkeeper_stats(match)
        n_big = {"home": 0, "away": 0}
        for bs in big_saves(match, config):
            # A lövő csapata áll a rekordban — a védés a másik oldalé.
            n_big["away" if bs["team"] == "home" else "home"] += 1
        for side in ("home", "away"):
            rec_gk = gstats.get(side)
            if rec_gk and n_big[side] >= 2:
                add(side, "Bravúr-kapus", rec_gk["track_id"],
                    f"{n_big[side]} fogott ziccer")
    except Exception:
        pass
    try:
        from .event_detection import shot_speeds
        sp = shot_speeds(match, config)
        for side in ("home", "away"):
            best = None
            for sh in sp.get("shots", []):
                if sh["team"] != side or sh.get("player_id") is None:
                    continue
                if best is None or sh["speed_kmh"] > best["speed_kmh"]:
                    best = sh
            if best is not None and best["speed_kmh"] >= CANNON_KMH:
                add(side, "Ágyú", best["player_id"],
                    f"{best['speed_kmh']:.0f} km/h lövés")
    except Exception:
        pass
    return out


def _merge_seven_earners(reports) -> list:
    """Hetes-kiharcolónkénti darabszámok pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for e in (r.seven_earners or []):
            tally[e["player_id"]] = (tally.get(e["player_id"], 0)
                                     + int(e["earned"]))
    return [{"player_id": pid, "earned": n}
            for pid, n in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_susp_earners(reports) -> list:
    """Kiállítás-kiharcolónkénti darabszámok pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for e in (r.susp_earners or []):
            tally[e["player_id"]] = (tally.get(e["player_id"], 0)
                                     + int(e["earned"]))
    return [{"player_id": pid, "earned": n}
            for pid, n in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_susp_players(reports) -> list:
    """Kiülőnkénti kiállítás-számok pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for e in (r.susp_players or []):
            tally[e["player_id"]] = (tally.get(e["player_id"], 0)
                                     + int(e["suspensions"]))
    return [{"player_id": pid, "suspensions": n}
            for pid, n in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_markers(reports) -> list:
    """Emberfogónkénti őrzés-kockák és táv-összegek pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for e in (r.markers or []):
            rec = tally.setdefault(e["player_id"], [0, 0.0])
            rec[0] += int(e["frames"])
            rec[1] += float(e["dist_sum"])
    return [{"player_id": pid, "frames": n, "dist_sum": round(ds, 2)}
            for pid, (n, ds) in sorted(tally.items(),
                                       key=lambda kv: -kv[1][0])]


def _merge_break_lanes(reports) -> dict:
    """Sávonkénti betörés/gól számok pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for k, v in (r.break_lanes or {}).items():
            cur = tally.setdefault(k, {"entries": 0, "goals": 0})
            cur["entries"] += int(v.get("entries", 0))
            cur["goals"] += int(v.get("goals", 0))
    return dict(sorted(tally.items(),
                       key=lambda kv: -kv[1]["entries"]))


def _merge_pass_buckets(reports) -> dict:
    """Passz-vödrönkénti támadás/gól számok pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for k, v in (r.pass_buckets or {}).items():
            cur = tally.setdefault(k, {"attacks": 0, "goals": 0})
            cur["attacks"] += int(v.get("attacks", 0))
            cur["goals"] += int(v.get("goals", 0))
    return tally


def _merge_ball_winners(reports) -> list:
    """Labdaszerzőnkénti darabszámok pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for w in (r.ball_winners or []):
            tally[w["player_id"]] = (tally.get(w["player_id"], 0)
                                     + int(w["steals"]))
    return [{"player_id": pid, "steals": n}
            for pid, n in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_turnover_players(reports) -> list:
    """Labdaeladónkénti darabszámok pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for w in (r.turnover_players or []):
            tally[w["player_id"]] = (tally.get(w["player_id"], 0)
                                     + int(w["losses"]))
    return [{"player_id": pid, "losses": n}
            for pid, n in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_clutch_scorers(reports) -> list:
    """Hajrá-emberenkénti gólszámok pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for w in (r.clutch_scorers or []):
            tally[w["player_id"]] = (tally.get(w["player_id"], 0)
                                     + int(w["goals"]))
    return [{"player_id": pid, "goals": n}
            for pid, n in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_scorer_goals(reports) -> list:
    """Lövőnkénti gólszámok (gól-koncentráció) pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for w in (r.scorer_goals or []):
            tally[w["player_id"]] = (tally.get(w["player_id"], 0)
                                     + int(w["goals"]))
    return [{"player_id": pid, "goals": n}
            for pid, n in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_seven_takers(reports) -> list:
    """Hetes-dobónkénti kísérlet/gól/irány számok pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for t in (r.seven_takers or []):
            cur = tally.setdefault(t["player_id"], [0, 0, {}])
            cur[0] += int(t["attempts"])
            cur[1] += int(t["goals"])
            for d, n in (t.get("dirs") or {}).items():
                cur[2][d] = cur[2].get(d, 0) + int(n)
    return [{"player_id": pid, "attempts": a, "goals": g, "dirs": ds}
            for pid, (a, g, ds) in sorted(tally.items(),
                                          key=lambda kv: -kv[1][0])]


def _merge_fb_finishers(reports) -> list:
    """Kontra-befejezők gólszámainak pontos összegzése meccsek közt."""
    tally: dict = {}
    for r in reports:
        for f in (r.fb_finishers or []):
            tally[f["player_id"]] = (tally.get(f["player_id"], 0)
                                     + int(f["goals"]))
    return [{"player_id": pid, "goals": n}
            for pid, n in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_outlet_targets(reports) -> list:
    """Indítás-célpontok darabszámainak pontos összegzése meccsek közt."""
    tally: dict = {}
    for r in reports:
        for t in (r.gk_outlet_targets or []):
            tally[t["player_id"]] = tally.get(t["player_id"], 0) + int(t["n"])
    return [{"player_id": pid, "n": n}
            for pid, n in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_blockers(reports) -> list:
    """Blokkolónkénti blokkszámok pontos összegzése meccsek közt."""
    tally: dict = {}
    for r in reports:
        for b in (r.blockers or []):
            tally[b["player_id"]] = (tally.get(b["player_id"], 0)
                                     + int(b["blocks"]))
    return [{"player_id": pid, "blocks": n}
            for pid, n in sorted(tally.items(), key=lambda kv: -kv[1])]


def matchup_plan(own: "ScoutingReport",
                 opp: "ScoutingReport") -> list[str]:
    """Meccsterv-illesztés: a SAJÁT és az ELLENFÉL profiljának
    keresztezése — nem általános kulcsok, hanem erre a párosításra
    szabott mondatok. Minden mondat mögött mindkét oldal számai állnak.
    """
    plan: list[str] = []

    # 1) A lassú visszarendeződésük × a mi lerohanásunk.
    if (opp.rec_transitions >= 4
            and opp.rec_sum_s / opp.rec_transitions >= 5.0
            and own.fast_break_pct >= 8.0):
        plan.append(
            "A visszarendeződésük lassú "
            f"({opp.rec_sum_s / opp.rec_transitions:.1f} mp), a ti "
            f"lerohanás-arányotok {own.fast_break_pct:.0f}% — a kontra "
            "ebben a párosításban az első számú fegyveretek.")

    # 2) A gyenge kapusuk × a ti lövés-kedvetek.
    if (opp.matches and opp.gk_xg_prevented / opp.matches <= -1.0
            and own.shots >= 10):
        plan.append(
            "Kapusuk a helyzetekhez képest sokat kap "
            f"({opp.gk_xg_prevented / opp.matches:+.1f}/meccs) — "
            "vállaljátok bátran a kapura lövést, a ti lövés-mennyiségetek "
            f"({own.shots} lövés) itt kifizetődik.")

    # 3) A blokkoló faluk × a ti átlövés-függésetek.
    own_back_goals = (own.post_goals or {}).get("átlövő", 0)
    own_total_pg = sum((own.post_goals or {}).values())
    if (opp.blocks >= 3 and own_total_pg >= 6
            and own_back_goals / own_total_pg >= 0.5):
        plan.append(
            f"Sokat blokkolnak ({opp.blocks} blokk), és a ti góljaitok "
            f"{100.0 * own_back_goals / own_total_pg:.0f}%-a átlövésből "
            "jön — erre a meccsre kellenek a beálló- és szélső-megoldások.")

    # 4) A labdaszerzésből élő támadásuk × a ti elöl vesztett labdáitok.
    opp_ao = opp.attack_origins or {}
    opp_steal_goals = (opp_ao.get("labdaszerzés") or {}).get("goals", 0)
    if opp_steal_goals >= 4 and own.turnover_front >= 5:
        plan.append(
            f"A góljaik nagy része labdaszerzésből jön ({opp_steal_goals} "
            f"gól), ti pedig sokat hibáztok elöl ({own.turnover_front} "
            "elöl vesztett labda) — a labdabiztonság ezen a meccsen "
            "duplán számít.")

    # 5) A gyors kapus-indításuk × a ti lassú visszaérésetek.
    if (opp.gk_outlets >= 2
            and opp.gk_outlet_fast / opp.gk_outlets >= 0.5
            and own.rec_transitions >= 4
            and own.rec_sum_s / own.rec_transitions >= 5.0):
        plan.append(
            "Kapusuk gyorsan indít, ti pedig lassan értek vissza "
            f"(átlag {own.rec_sum_s / own.rec_transitions:.1f} mp) — "
            "lövés után az azonnali visszafutás legyen az első parancs.")

    # 6) A gyenge hetes-dobójuk × a ti formában lévő kapusotok.
    opp_taker = (opp.seven_takers or [None])[0]
    if (opp_taker and opp_taker["attempts"] >= 3
            and opp_taker["goals"] / opp_taker["attempts"] <= 0.5
            and own.matches and own.gk_xg_saved / own.matches >= 1.0):
        plan.append(
            f"A hetes-dobójuk bizonytalan ({opp_taker['goals']}/"
            f"{opp_taker['attempts']}), a ti kapusotok formában van — "
            "hetesnél bátran vállalhat mozgást, ez a párbaj nektek áll.")

    # 7) A tempós játékuk × a ti működő rotációtok.
    if (opp.pace_minutes >= 20.0
            and opp.pace_attacks / opp.pace_minutes >= 1.1
            and own.sub_rotations >= 2
            and own.sub_after_for - own.sub_after_against >= 0):
        plan.append(
            "Tempós meccs lesz "
            f"({opp.pace_attacks / opp.pace_minutes:.1f} támadás/perc az "
            "ő oldalukon) — a rotációtok mérlege jó, forgassatok "
            "bátran: a friss lábak nálatok vannak.")

    # 8) A kihagyós befejezésük × a ti bravúr-kapusotok.
    if (opp.big_total >= 4 and opp.big_missed / opp.big_total >= 0.5
            and own.gk_big_saves >= 2):
        plan.append(
            f"Ziccereket hagynak ki ({opp.big_missed}/{opp.big_total}), "
            f"a ti kapusotok pedig fogja őket ({own.gk_big_saves} "
            "bravúr-védés) — a nagy helyzeteik sem biztos gólok: ne "
            "essetek szét egy-egy védekezési hiba után.")

    # 9) A fegyelmezetlen védőjük × a ti kiharcolóitok.
    opp_sp = (opp.susp_players or [None])[0]
    own_earn = 0
    own_earner_id = None
    for lst in (own.susp_earners or []), (own.seven_earners or []):
        if lst and lst[0]["earned"] > own_earn:
            own_earn = lst[0]["earned"]
            own_earner_id = lst[0]["player_id"]
    if (opp_sp and opp_sp["suspensions"] >= 2 and own_earn >= 2
            and own_earner_id is not None):
        plan.append(
            f"A(z) {opp_sp['player_id']}. játékosuk fegyelmezetlen "
            f"({opp_sp['suspensions']} kiállítás), nálatok a(z) "
            f"{own_earner_id}. játékos harcolja ki a szabálytalanságokat "
            f"({own_earn}×) — küldd őt az ő sávjába: 2 perc vagy hetes "
            "lesz belőle.")

    # 11) A működő figurájuk × a ti fedezés-hibáitok.
    if (opp.best_fig_attacks >= 3 and opp.best_fig_goals >= 2
            and own.def_shots_against >= 8
            and own.def_free_shots / own.def_shots_against >= 0.4):
        plan.append(
            f"Van egy figurájuk, ami működik ({opp.best_fig_attacks} "
            f"támadásból {opp.best_fig_goals} gól), ti pedig sokszor "
            f"hagytok szabad lövőt ({100.0 * own.def_free_shots / own.def_shots_against:.0f}%) "
            "— a figura-felismerés nálatok életbiztosítás: nézzétek a "
            "figura-klipeket, és az első passznál szóljon a fal.")

    # 12) Az ő széles játékuk × a ti szélről kapott góljaitok.
    opp_avg_w = (opp.width_sum_m / opp.width_frames
                 if opp.width_frames >= 100 and opp.width_sum_m > 0
                 else None)
    own_conc_zones = own.gk_conceded_zones or {}
    own_conc = sum(own_conc_zones.values())
    own_wing_conc = sum(v for z, v in own_conc_zones.items()
                        if "szél" in z)
    if (opp_avg_w is not None and opp_avg_w >= 14.0
            and own_conc >= 6 and own_wing_conc / own_conc >= 0.4):
        plan.append(
            f"Szélesen játszanak (átlag {opp_avg_w:.0f} m), ti pedig a "
            f"kapott gólok {100.0 * own_wing_conc / own_conc:.0f}%-át "
            "szélről kapjátok — a szélső-védő kilépés-fegyelme ezen a "
            "meccsen döntő: későn kilépni tilos, besegíteni középre "
            "csak labda-oldalon.")

    # 10) Az ő időhúzásuk × a ti erős kezdésetek.
    if (opp.lead_attacks >= 3 and opp.trail_attacks >= 3
            and own.fh_goals_for - own.fh_goals_against >= 3):
        opp_lead_avg = opp.lead_sum_s / opp.lead_attacks
        opp_trail_avg = opp.trail_sum_s / opp.trail_attacks
        if opp_lead_avg - opp_trail_avg >= 8.0:
            plan.append(
                f"Előnyben altatják a meccset (átlag {opp_lead_avg:.0f} "
                f"mp-es támadások), ti pedig jól kezdtek "
                f"({own.fh_goals_for}–{own.fh_goals_against} az első "
                "félidőkben) — ha az elején ti vezettek, a fő fegyverük "
                "kiesik: nyissatok magas tempóval.")

    # 13) A leglazább emberfogójuk: az ő oldalára vidd az egy-egyet.
    if opp.markers:
        loose = max(opp.markers,
                    key=lambda m_: m_["dist_sum"] / m_["frames"])
        loose_avg = loose["dist_sum"] / loose["frames"]
        if loose["frames"] >= 50 and loose_avg >= 2.5:
            plan.append(
                f"A(z) {loose['player_id']}-es védőjük lazán őrzi az "
                f"emberét (átlag {loose_avg:.1f} m) — az ő oldalára "
                "szervezd az egy-egy elleni játékot és a betöréseket.")

    # 14) A tapadó emberfogójuk × a ti fő lövőtök: elzárással kell
    # szabadítani, vagy a másik oldalra terhelni.
    if opp.markers:
        tight = min(opp.markers,
                    key=lambda m_: m_["dist_sum"] / m_["frames"])
        tight_avg = tight["dist_sum"] / tight["frames"]
        own_top = (own.shooter_overperf or [None])[0]
        if (tight["frames"] >= 50 and tight_avg <= 1.5
                and own_top and own_top.get("diff", 0) >= 1.0):
            plan.append(
                f"A(z) {tight['player_id']}-es védőjük tapadó emberfogó "
                f"(átlag {tight_avg:.1f} m), a ti fő lövőtök pedig a(z) "
                f"{own_top['player_id']}. játékos — ha őt fogja, "
                "elzárással szabadítsd, vagy tudatosan a túloldalra "
                "terhelj: egy-egyben ott nem lesz tér.")

    # 15) Az ő beálló-terhelésük × a ti kiállítás-hajlamotok: a beálló-
    # védelem testtel megy, nem fogással — különben 2 perc lesz.
    if opp.pivot_total_attacks >= 6 and own.suspensions >= 2:
        pshare15 = 100.0 * opp.pivot_attacks / opp.pivot_total_attacks
        if pshare15 >= 40.0:
            plan.append(
                f"Támadásaik {pshare15:.0f}%-a a beállón át megy, ti "
                f"pedig {own.suspensions} kiállítást szedtetek össze — "
                "a beállót testtel és helyezkedéssel tartsd, fogással "
                "ne: náluk ebből 2 perc és hetes lesz.")

    # 16) Az ő betörés-sávjuk × a ti laza falatok: abban a sávban kell
    # korábban kilépni.
    if (opp.break_entries >= 6 and opp.break_lanes
            and own.defensive_pressure_m >= 2.0):
        top16, rec16 = next(iter(opp.break_lanes.items()))
        share16 = 100.0 * rec16["entries"] / opp.break_entries
        if share16 >= 50.0:
            plan.append(
                f"A betöréseik {share16:.0f}%-a a(z) {top16} sávban "
                f"jön, ti pedig lazán védekeztek (átlag "
                f"{own.defensive_pressure_m:.1f} m) — abban a sávban "
                "lépj ki korábban, és a segítő védő már a betörés "
                "ELŐTT csússzon be.")

    # 17) Az ő gyors első hullámuk × a ti gyenge visszazárásotok.
    qb = (opp.pass_buckets or {}).get("0–2 passz")
    if (qb and qb["attacks"] >= 4 and qb["goals"]
            and 100.0 * qb["goals"] / qb["attacks"] >= 40.0
            and own.transition_goals_against >= 2):
        plan.append(
            f"A góljaik jelentős része 0–2 passzos villámtámadásból "
            f"jön ({qb['goals']}/{qb['attacks']}), ti pedig "
            f"{own.transition_goals_against} átmenet-gólt kaptatok — "
            "lövés után NE reklamálj, az első két hazafutó lépés "
            "kötelező mindenkinek.")

    # 19) Az ő kint álló kapusuk × a ti kontra-játékotok: az indulás
    # utáni első átemelést vállalni kell.
    if (opp.gk_depth_frames >= 100
            and opp.gk_depth_sum_m / opp.gk_depth_frames >= 1.5
            and own.fast_break_pct >= 10.0):
        depth19 = opp.gk_depth_sum_m / opp.gk_depth_frames
        plan.append(
            f"Kapusuk kint áll (átlag {depth19:.1f} m-re a gólvonaltól), "
            f"ti pedig sokat indultok ({own.fast_break_pct:.0f}% gyors "
            "indítás) — kontránál az első átemelést vállalni KELL, még "
            "félpályáról is: vagy gól, vagy visszazavarja a kapust.")

    # 18) Az ő szűk paduk × a ti széles rotációtok: a tempó a fegyver.
    if opp.rotation_matches and own.rotation_matches:
        opp_used = opp.rotation_used_sum / opp.rotation_matches
        own_used = own.rotation_used_sum / own.rotation_matches
        if opp_used <= 8.0 and own_used >= 10.0:
            plan.append(
                f"Náluk átlag {opp_used:.0f} ember viszi a meccset, "
                f"nálatok {own_used:.0f} — magas tempó és sűrű csere "
                "az első perctől: a második félidő közepére nyílik "
                "az olló, ott kell elmenni.")

    # 20) Az ő kapusuk gyenge a távolira × a ti távoli lövés-erőtök.
    if opp.gk_far_faced >= 4 and opp.gk_far_saves / opp.gk_far_faced <= 0.40:
        own_sr_total = (own.sr_close_shots + own.sr_mid_shots
                        + own.sr_far_shots)
        own_far_pct = (own.sr_far_shots / own_sr_total
                       if own_sr_total else 0.0)
        if own.sr_far_shots >= 5 and own_far_pct >= 0.30:
            opp_far_save = 100.0 * opp.gk_far_saves / opp.gk_far_faced
            plan.append(
                f"Kapusuk a távoli lövésekre gyenge ({opp_far_save:.0f}% "
                f"védés), ti pedig sokat lőtök kintről ({own.sr_far_shots} "
                "távoli lövés) — erre a meccsre élesítsétek az átlövést, "
                "keressétek bátran a távoli befejezést.")

    # 21) Az ő gyenge lepattanó-harcuk × a ti kontra-erőtök: a védett/blokkolt
    # lövésük után azonnal indulni kell, mert nem mennek a lepattanóra.
    if (opp.sc_misses >= 6
            and 100.0 * opp.sc_second / opp.sc_misses <= 8.0
            and own.fast_break_pct >= 10.0):
        opp_reb = 100.0 * opp.sc_second / opp.sc_misses
        plan.append(
            f"A kimaradt lövéseik után alig mennek a lepattanóra "
            f"({opp_reb:.0f}%), ti pedig sokat indultok "
            f"({own.fast_break_pct:.0f}% gyors indítás) — a védés/blokk a ti "
            "kontrátok rajtja: a kapus és a szélső azonnal indul, nem várunk.")

    # 22) Az ő erős lepattanó-harcuk × a ti blokkoló faluk: a blokk után a
    # laza labdát BE kell fogni, különben második esélyt adtok.
    if (opp.sc_misses >= 6
            and 100.0 * opp.sc_second / opp.sc_misses >= 25.0
            and own.blocks >= 3):
        opp_reb2 = 100.0 * opp.sc_second / opp.sc_misses
        plan.append(
            f"Harcolnak a lepattanóért ({opp_reb2:.0f}% második roham), ti "
            f"pedig sokat blokkoltok ({own.blocks} blokk) — a blokk után a "
            "laza labdát be kell fogni, nem elég megpattintani: a beállót "
            "fogd le, a szélső záródjon a rövid lepattanóra.")

    # 23) Az ő lassú kezdésük × a ti jó kezdésetek: a meccs nyitánya a ti
    # ablakotok — az első percekben kell elhúzni.
    if (opp.open_first_matches >= 3 and own.open_first_matches >= 3):
        opp_rate = 100.0 * opp.open_first_yes / opp.open_first_matches
        own_rate = 100.0 * own.open_first_yes / own.open_first_matches
        opp_slow = opp_rate <= 35.0 or (opp.open_for - opp.open_against) <= -3
        own_fast = own_rate >= 65.0 or (own.open_for - own.open_against) >= 3
        if opp_slow and own_fast:
            plan.append(
                f"Ők lassan kezdenek (a meccsek {opp_rate:.0f}%-ában övék az "
                f"első gól), ti pedig jól ({own_rate:.0f}%) — a meccs nyitánya "
                "a ti ablakotok: kész nyitó-figurákkal, magas tempóval menjetek "
                "rájuk az első perctől, a korai előny megtöri a tervüket.")

    # 24) Az ő 2. félidei lövőerő-esésük × a ti működő rotációtok: a hajrát
    # tempóval kell vinni — a fáradó lövéseiket a kapus fogja.
    if (opp.ssf_fh_n >= 5 and opp.ssf_sh_n >= 5 and opp.ssf_fh_sum_kmh > 0
            and own.rotation_matches and own.sub_rotations >= 2):
        _mf_fh = opp.ssf_fh_sum_kmh / opp.ssf_fh_n
        _mf_sh = opp.ssf_sh_sum_kmh / opp.ssf_sh_n
        _mf_drop = 100.0 * (_mf_fh - _mf_sh) / _mf_fh
        own_used24 = own.rotation_used_sum / own.rotation_matches
        if _mf_drop >= 8.0 and own_used24 >= 9.0:
            plan.append(
                f"A 2. félidőre esik a lövőerejük ({_mf_fh:.0f} → "
                f"{_mf_sh:.0f} km/h), ti pedig szélesen forogtok "
                f"(átlag {own_used24:.0f} ember) — a hajrát vigyétek "
                "tempóval: az ő lövéseik puhulnak, a ti friss lábaitok "
                "döntenek; a kapusotok a végén bátran vállalhat.")

    # 25) Az ő gólfüggésük × a ti tapadó emberfogótok: a fő gólszerzőjükre
    # a legjobb védőt kell állítani — egy emberen múlik a támadójátékuk.
    _pg_total = sum(w["goals"] for w in (opp.scorer_goals or []))
    if _pg_total >= 5 and opp.scorer_goals and own.markers:
        _pg_top = opp.scorer_goals[0]
        _pg_share = 100.0 * _pg_top["goals"] / _pg_total
        tight25 = min(own.markers,
                      key=lambda m_: m_["dist_sum"] / m_["frames"])
        tight25_avg = tight25["dist_sum"] / tight25["frames"]
        if _pg_share >= 40.0 and tight25["frames"] >= 50 \
                and tight25_avg <= 1.5:
            plan.append(
                f"Góljaik {_pg_share:.0f}%-át a(z) {_pg_top['player_id']}-es "
                f"szerzi, nálatok pedig a(z) {tight25['player_id']}-es a "
                f"tapadó emberfogó (átlag {tight25_avg:.1f} m) — ez a "
                "párosítás adja magát: ő fogja a fő gólszerzőt akár emberfogva, "
                "és az egész támadójátékuk megfojtható.")

    # 26) Az ő izolált labdásuk × a ti labdaszerzésből élő támadásotok:
    # a letámadás ellenük közvetlenül gólt ér.
    if (opp.sup_frames >= 100 and opp.sup_sum_m > 0
            and opp.sup_iso / opp.sup_frames >= 0.35
            and own.trans_steals >= 4 and own.trans_quick_goals >= 2):
        _i26 = 100.0 * opp.sup_iso / opp.sup_frames
        plan.append(
            f"A labdásuk az idő {_i26:.0f}%-ában magára marad, ti pedig a "
            f"szerzéseiteket gyorsan gólra váltjátok "
            f"({own.trans_quick_goals}/{own.trans_steals}) — magas "
            "letámadás az első perctől: az izolált labdás az eladásaival "
            "a ti kontráitokat fogja etetni.")

    # 27) Az ő hátul ragadó birtoklásuk × a ti szoros védekezésetek: a
    # feltolt letámadás a saját térfelükre szögezi őket.
    if (opp.tilt_frames >= 100
            and 100.0 * opp.tilt_opp / opp.tilt_frames <= 45.0
            and 0.0 < own.defensive_pressure_m <= 1.6):
        _t27 = 100.0 * opp.tilt_opp / opp.tilt_frames
        plan.append(
            f"A birtoklásuk a saját térfelükön ragad (csak {_t27:.0f}% "
            f"elöl), ti pedig szorosan védekeztek (átlag "
            f"{own.defensive_pressure_m:.1f} m) — told fel az egész "
            "csapatot: a letámadásod a saját kapujuk elé szögezi őket, "
            "és minden szerzés ziccert ér.")

    # 28) Az ő tömör faluk × a ti erős szélső-játékotok: a nyitott
    # szélekre kell terhelni.
    if (opp.defw_frames >= 100 and opp.defw_sum_m > 0
            and opp.defw_sum_m / opp.defw_frames <= 11.0
            and own.wing_fin_shots >= 4
            and own.wing_fin_goals / own.wing_fin_shots >= 0.5):
        _w28 = opp.defw_sum_m / opp.defw_frames
        _wp28 = 100.0 * own.wing_fin_goals / own.wing_fin_shots
        plan.append(
            f"Tömör, keskeny falat húznak (átlag {_w28:.0f} m), a ti "
            f"szélső-befejezésetek pedig erős ({own.wing_fin_goals}/"
            f"{own.wing_fin_shots}, {_wp28:.0f}%) — gyors oldalváltásokkal "
            "terheld a nyitott szélekre: a szélsőitek erre a meccsre a fő "
            "fegyver.")

    # 29) Az ő ziccert engedő faluk × a ti közeli befejezés-erőtök: a
    # betörős/beállós játék ellenük duplán kifizetődik.
    if (opp.def_shots_against >= 8 and opp.xga_sum > 0
            and opp.xga_sum / opp.def_shots_against >= 0.38):
        own_sr29 = own.sr_close_shots + own.sr_mid_shots + own.sr_far_shots
        if own.sr_close_shots >= 5 and own_sr29 > 0 \
                and own.sr_close_shots / own_sr29 >= 0.40:
            _x29 = opp.xga_sum / opp.def_shots_against
            plan.append(
                f"A faluk ziccereket enged (átlag {_x29:.2f} xG/lövés), ti "
                f"pedig amúgy is közelről éltek (a lövéseitek "
                f"{100.0 * own.sr_close_shots / own_sr29:.0f}%-a közeli) — "
                "türelmes betörős/beállós játékkal minden támadásból nagy "
                "helyzet hozható ki ellenük.")

    # 30) Az ő lassú labdajáratásuk × a ti labdaszerző védekezésetek: a
    # passzsávokra ráülve az álló járatás eladásokká válik.
    if (opp.pt_poss_s >= 120.0 and opp.pt_passes > 0
            and 60.0 * opp.pt_passes / opp.pt_poss_s <= 12.0
            and own.trans_steals >= 4):
        _pt30 = 60.0 * opp.pt_passes / opp.pt_poss_s
        plan.append(
            f"Lassan, állva járatják a labdát ({_pt30:.0f} passz/perc), ti "
            f"pedig éltek a labdaszerzésből ({own.trans_steals} szerzés) — "
            "üljetek rá a kiszámítható passzsávokra: az álló járatásból "
            "szerzett labda azonnali kontra.")

    # 31) Az ő falba lövő támadásuk × a ti blokkoló falatok: a blokk
    # ellenük nem mellékes — a fő fegyver.
    if (opp.blk_for >= 4 and opp.blk_attempts > 0
            and 100.0 * opp.blk_for / opp.blk_attempts >= 20.0
            and own.blocks >= 3):
        _b31 = 100.0 * opp.blk_for / opp.blk_attempts
        plan.append(
            f"A lövés-kísérleteik {_b31:.0f}%-a blokkon akad el, ti pedig "
            f"amúgy is sokat blokkoltok ({own.blocks} blokk) — ez a "
            "párosítás a falatoknak áll: minden átlövésbe beleállni, a "
            "blokk után pedig azonnal indulni.")

    # 32) Az ő letámadásuk × a ti hátul ragadó birtoklásotok: a kihozatal
    # ellenük külön felkészülést kér.
    if (opp.steal_n >= 4
            and 100.0 * opp.steal_high / opp.steal_n >= 35.0
            and own.tilt_frames >= 100
            and 100.0 * own.tilt_opp / own.tilt_frames <= 50.0):
        _st32 = 100.0 * opp.steal_high / opp.steal_n
        plan.append(
            f"A szerzéseik {_st32:.0f}%-a elöl, letámadásból jön, a ti "
            "birtoklásotok pedig amúgy is hátul ragad "
            f"({100.0 * own.tilt_opp / own.tilt_frames:.0f}% elöl) — a "
            "kihozatal ellenük külön terv: kapus játékban, rövid "
            "kijátszás létszámfölénnyel, hosszú szelep a szélsőnek.")

    # 33) Az ő hosszú-passzos játékuk × a ti labdaszerzőitek: a passzsáv-
    # ülés ellenük közvetlen kontra-forrás.
    if (opp.plen_n >= 15 and opp.plen_sum_m > 0
            and 100.0 * opp.plen_long / opp.plen_n >= 30.0
            and own.trans_steals >= 4):
        _pl33 = 100.0 * opp.plen_long / opp.plen_n
        plan.append(
            f"A passzaik {_pl33:.0f}%-a hosszú (10 m+), ti pedig éltek a "
            f"labdaszerzésből ({own.trans_steals} szerzés) — a hosszú "
            "passzsávokra ültetett védőitek elfogásai adják majd a "
            "legolcsóbb góljaitokat.")

    # 34) Az ő első-hullám lövéseik × a ti lassú visszaérésetek: a lövés
    # utáni azonnali visszafutás ellenük nem tanács, hanem parancs.
    if (opp.shtim_n >= 5 and opp.shtim_sum_s > 0
            and 100.0 * opp.shtim_early / opp.shtim_n >= 45.0
            and own.rec_transitions >= 4
            and own.rec_sum_s / own.rec_transitions >= 5.0):
        _sh34 = 100.0 * opp.shtim_early / opp.shtim_n
        plan.append(
            f"A lövéseik {_sh34:.0f}%-a a támadás első 8 mp-éből jön, ti "
            f"pedig lassan értek vissza (átlag "
            f"{own.rec_sum_s / own.rec_transitions:.1f} mp) — ellenük a "
            "lövés utáni első két hazafutó lépés kötelező mindenkinek, "
            "különben az első hullámuk büntet.")

    # 35) Az ő fellazuló faluk × a ti hajrá-erőtök: a meccs vége a ti
    # ablakotok — oda kell időzíteni a friss lábakat.
    if (opp.prf_fh_n >= 100 and opp.prf_sh_n >= 100
            and opp.prf_fh_sum_m > 0 and opp.prf_sh_sum_m > 0
            and opp.prf_sh_sum_m / opp.prf_sh_n
            - opp.prf_fh_sum_m / opp.prf_fh_n >= 0.5
            and own.clutch_matches >= 1
            and own.clutch_goals_for > own.clutch_goals_against):
        _p35_fh = opp.prf_fh_sum_m / opp.prf_fh_n
        _p35_sh = opp.prf_sh_sum_m / opp.prf_sh_n
        plan.append(
            f"A védekezésük a 2. félidőre fellazul ({_p35_fh:.1f} → "
            f"{_p35_sh:.1f} m), ti pedig jók vagytok a hajrában "
            f"({own.clutch_goals_for}–{own.clutch_goals_against} a "
            "meccsek végén) — a friss átlövőt a második félidő közepére "
            "időzítsd: az ő fáradó faluk + a ti hajrátok döntheti el a "
            "meccset.")

    # 36) Az ő hatástalan időkérésük × a ti sorozat-képességetek: a
    # lendületed az időkérésükön is átér.
    if (opp.to_failed >= 2 and opp.to_failed > opp.to_broke
            and own.goals >= 10):
        plan.append(
            f"Az időkérésük rendre hatástalan ({opp.to_failed} nem hozott "
            "fordulatot) — ha sorozatban vagytok, az időkérésük ne "
            "zökkentsen ki: ugyanazzal a tempóval és ugyanazokkal a "
            "figurákkal gyertek vissza, a lendület a tiétek marad.")

    # 46) Az ő kihagyás utáni zavaruk × a ti gyors átmenetetek: minden
    # kihagyott ziccerük indítás-jel.
    if (opp.bcp_misses >= 4
            and 100.0 * opp.bcp_punished / opp.bcp_misses >= 40.0
            and own.trans_steals >= 3 and own.trans_quick_goals >= 2):
        plan.append(
            f"Kihagyott ziccer után zavartak ({opp.bcp_misses} "
            f"kihagyásból {opp.bcp_punished} után fél percen belül "
            f"büntetést kaptak), ti pedig jól váltjátok gólra a gyors "
            f"átmenetet ({own.trans_quick_goals} gyors gól "
            f"{own.trans_steals} szerzésből) — minden kihagyásuk után "
            "azonnali indítás: a kapus kezéből első passz előre.")

    # 47) Az ő elfogyó lábuk × a ti bírt tempótok: a 2. félidő a ti
    # ablakotok — futni kell, amikor ők már nem tudnak.
    if (opp.tpf_fh_min >= 8.0 and opp.tpf_sh_min >= 8.0
            and own.tpf_fh_min >= 8.0 and own.tpf_sh_min >= 8.0
            and opp.tpf_fh_attacks / opp.tpf_fh_min
            - opp.tpf_sh_attacks / opp.tpf_sh_min >= 0.2
            and own.tpf_fh_attacks / own.tpf_fh_min
            - own.tpf_sh_attacks / own.tpf_sh_min <= 0.0):
        _p47_fh = opp.tpf_fh_attacks / opp.tpf_fh_min
        _p47_sh = opp.tpf_sh_attacks / opp.tpf_sh_min
        plan.append(
            f"A 2. félidőre elfogy a lábuk ({_p47_fh:.1f} → "
            f"{_p47_sh:.1f} támadás/perc), a ti tempótok viszont kitart "
            "— a szünet után azonnal tempót fel: gyors középkezdés "
            "minden gól után, futó kézi, és a friss lábakat a 2. "
            "félidőre időzítsd; a fáradó láb ellen a tempó a kés.")

    # 48) Az ő feladott félidei hátrányuk × a ti erős kezdésetek: ha a
    # szünetre előnyben vagytok, a meccs náluk fejben lefutott.
    if (opp.htc_behind >= 2 and opp.htc_turned == 0
            and opp.htc_saved == 0
            and own.open_first_matches >= 1
            and own.open_for > own.open_against):
        plan.append(
            f"Félidei hátrányból egyszer sem jöttek vissza "
            f"({opp.htc_behind} ilyen meccsből 0), ti pedig erősen "
            f"kezdtek ({own.open_for}–{own.open_against} a korai "
            "gólokból) — a meccsterv az első 30 percre épüljön: "
            "szerezz félidei előnyt, a szünet után ők maguktól "
            "elengedik.")

    # 49) Az ő remegő holtpontjuk × a ti holtpont-erőtök: az egál nektek
    # jó — a kiegyenlített állás az ő nyomásuk, a ti labdátok.
    if (opp.pb_ties >= 4 and 100.0 * opp.pb_won / opp.pb_ties <= 35.0
            and own.pb_ties >= 4
            and 100.0 * own.pb_won / own.pb_ties >= 60.0):
        plan.append(
            f"Az egálnál ők remegnek ({opp.pb_ties} döntetlen-állásból "
            f"csak {opp.pb_won}-szor léptek el), ti pedig hozzátok a "
            f"holtpontokat ({own.pb_won}/{own.pb_ties}) — a szoros "
            "állástól nem kell félni: egálnál a következő gól papíron a "
            "tiétek, türelmes befejezéssel zárjátok a holtpontokat.")

    # 50) Az ő elfutó sorozataik × a ti sorozat-képességetek: a
    # mini-sorozatot ellenük végig kell nyomni.
    if (opp.rn_suffered >= 3
            and opp.rn_suffered_goals / opp.rn_suffered >= 4.5
            and own.rn_made >= 3):
        _p50_avg = opp.rn_suffered_goals / opp.rn_suffered
        plan.append(
            f"A sorozat ellenük elfut ({opp.rn_suffered} elszenvedett "
            f"sorozat, átlag {_p50_avg:.1f} gól), ti pedig tudtok "
            f"sorozatot futni ({own.rn_made} sorozat a meccseiteken) — "
            "ha megvan a 2-0, ne váltsatok le róla: letámadás, gyors "
            "középkezdés, és az ő időkérésük után is a megkezdett "
            "nyomás — a 3-0-jukból náluk 5-6-0 lesz.")

    # 51) Az ő elhaló bravúrjuk × a ti gyors visszarendeződésetek: a
    # merész lövésnek ellenük nincs ára.
    if (opp.bsm_saves >= 4 and opp.bsm_sparked == 0
            and own.rec_transitions >= 3
            and own.rec_sum_s / own.rec_transitions <= 4.0):
        plan.append(
            f"A bravúr náluk elhal ({opp.bsm_saves} nagy védésből 0 "
            f"gyors gól), ti pedig gyorsan értek vissza (átlag "
            f"{own.rec_sum_s / own.rec_transitions:.1f} mp) — a merész "
            "lövést fel lehet vállalni: a kapusuk megfoghatja, de "
            "kontra nem jön belőle, ti addig visszaértek.")

    # 52) Az ő eső befejezésük × a ti kitartó tempótok: a 2. félidőben
    # ők már nem büntetnek, ti igen.
    if (opp.ff_fh_shots >= 8 and opp.ff_sh_shots >= 8
            and 100.0 * opp.ff_fh_goals / opp.ff_fh_shots
            - 100.0 * opp.ff_sh_goals / opp.ff_sh_shots >= 15.0
            and own.tpf_fh_min >= 8.0 and own.tpf_sh_min >= 8.0
            and own.tpf_fh_attacks / own.tpf_fh_min
            - own.tpf_sh_attacks / own.tpf_sh_min <= 0.0):
        _p52_fh = 100.0 * opp.ff_fh_goals / opp.ff_fh_shots
        _p52_sh = 100.0 * opp.ff_sh_goals / opp.ff_sh_shots
        plan.append(
            f"A befejezésük a 2. félidőre esik ({_p52_fh:.0f}% → "
            f"{_p52_sh:.0f}% gólra váltás), a ti tempótok viszont "
            "kitart — az első félidőben ne menj bele lövöldözésbe: "
            "tartsd meccsben magad, a második félidőben az ő lövésük "
            "már nem ül, a tiéd igen — ott dől el a meccs.")

    # 53) Az ő mellé-lövésük × a ti gyors átmenetetek: a mellé lőtt
    # labda a ti indítás-jeletek.
    if (opp.ac_attempts >= 10
            and 100.0 * opp.ac_on_target / opp.ac_attempts <= 55.0
            and own.trans_steals >= 3 and own.trans_quick_goals >= 2):
        _p53_pct = 100.0 * opp.ac_on_target / opp.ac_attempts
        plan.append(
            f"A lövéseiknek csak {_p53_pct:.0f}%-a tart kapura, ti "
            f"pedig jól váltjátok gólra a gyors átmenetet "
            f"({own.trans_quick_goals} gyors gól {own.trans_steals} "
            "szerzésből) — minden mellé lövésük indítás: a kapus "
            "kidobása az induló szélsőre, mielőtt a faluk visszaáll.")

    # 54) Az ő fél-oldalas támadásuk × a ti blokk-erőtök: az eltolt fal
    # elé lőnek majd.
    if (opp.sb_left + opp.sb_right >= 10
            and 100.0 * max(opp.sb_left, opp.sb_right)
            / (opp.sb_left + opp.sb_right) >= 65.0
            and own.blocks >= 5):
        _p54_pct = (100.0 * max(opp.sb_left, opp.sb_right)
                    / (opp.sb_left + opp.sb_right))
        _p54_side = "bal" if opp.sb_left >= opp.sb_right else "jobb"
        plan.append(
            f"A támadásuk fél-oldalas ({_p54_pct:.0f}% a {_p54_side} "
            f"oldalukról), ti pedig jól blokkoltok ({own.blocks} blokk "
            "a meccseiteken) — toljátok el a falat az erős oldalukra: "
            "a megszokott lövő-sávjukban dupla kéz vár, és a blokk "
            "onnan már kontra-indítás.")

    # 55) Az ő belső órájuk × a ti labdaszerzésetek: az időzített
    # kettőzés a leggyengébb pillanatukban ér oda.
    if (opp.ar_n >= 12 and opp.ar_sum_s > 0
            and own.trans_steals >= 5):
        _p55_avg = opp.ar_sum_s / opp.ar_n
        _p55_var = max(0.0, opp.ar_sumsq_s / opp.ar_n
                       - _p55_avg * _p55_avg)
        if _p55_avg > 0 and (_p55_var ** 0.5) / _p55_avg <= 0.35:
            plan.append(
                f"Belső órán támadnak (átlag {_p55_avg:.0f} mp, "
                f"±{_p55_var ** 0.5:.0f}), ti pedig jó labdaszerzők "
                f"vagytok ({own.trans_steals} szerzés) — állítsatok "
                f"órát: a {max(0.0, _p55_avg - 5.0):.0f}. másodpercnél "
                "jöjjön az időzített kettőzés a labdásra, pont a "
                "lövés-előkészítésük pillanatában.")

    # 81) Az ő beletörődő ellen-pressük × a ti lerohanásotok: minden
    # labdaszerzés ingyen kontra ellenük.
    if (opp.cpr_turnovers >= 8
            and 100.0 * opp.cpr_regained / opp.cpr_turnovers <= 15.0
            and own.fast_break_pct >= 10.0):
        plan.append(
            f"Az eladás után beletörődnek (az eladásaiknak csak "
            f"{100.0 * opp.cpr_regained / opp.cpr_turnovers:.0f}%-át "
            f"szerzik vissza 6 mp-en belül), ti pedig sokat indultok "
            f"({own.fast_break_pct:.0f}% gyors indítás) — minden "
            "labdaszerzés után azonnal induljon a kontra: a szélsők "
            "fussanak, a szerző ne várja meg a felállt védekezést.")

    # 80) Az ő hajrá-elkapkodásuk × a ti hajrá-erőtök: a meccs végén
    # nekik kell hibázniuk, nektek csak tartani kell.
    if (opp.csq_early_shots >= 5 and opp.csq_clutch_shots >= 5
            and own.clutch_goals_for - own.clutch_goals_against >= 2
            and (opp.csq_early_xg / opp.csq_early_shots)
            - (opp.csq_clutch_xg / opp.csq_clutch_shots) >= 0.05):
        plan.append(
            f"A hajrában elkapkodják a befejezést (a lövéseik "
            f"helyzetértéke "
            f"{opp.csq_early_xg / opp.csq_early_shots:.2f}-ről "
            f"{opp.csq_clutch_xg / opp.csq_clutch_shots:.2f}-re esik), "
            f"ti pedig erősek vagytok a végén ({own.clutch_goals_for}"
            f"-{own.clutch_goals_against} a hajrá-mérlegetek) — a "
            "meccs végén ne kockáztassatok: tartsátok "
            "a falat, minden támadást játsszatok végig, és hagyjátok "
            "őket rossz lövésekbe futni.")

    # 79) Az ő kockázatos hosszú passzaik × a ti magas szerzésetek: a
    # hosszú átjátszás a ti csapdátokba fut.
    if (opp.prk_long_tries >= 8 and opp.prk_short_tries >= 8
            and own.steal_n >= 8 and own.steal_high / own.steal_n >= 0.35
            and (100.0 * opp.prk_long_to / opp.prk_long_tries)
            - (100.0 * opp.prk_short_to / opp.prk_short_tries)
            >= 15.0):
        plan.append(
            f"A hosszú passzaik kockázatosak "
            f"({100.0 * opp.prk_long_to / opp.prk_long_tries:.0f}% "
            f"elveszik, a rövideknél csak "
            f"{100.0 * opp.prk_short_to / opp.prk_short_tries:.0f}%), "
            f"ti pedig elöl szereztek ({own.steal_high}/"
            f"{own.steal_n} magas szerzés) — állj a hosszú "
            "passzsávjaikba: a letámadás hosszú átjátszásra "
            "kényszeríti őket, és onnan indul a lerohanásotok.")

    # 78) Az ő gyenge elzárás-váltásuk × a ti elzárás-játékotok: amit
    # nem bírnak, abból ti amúgy is sokat játszotok.
    if (opp.scd_screened_shots >= 6 and opp.scd_open_shots > 0
            and own.scu_shots >= 8
            and (100.0 * opp.scd_screened_goals
                 / opp.scd_screened_shots)
            - (100.0 * opp.scd_open_goals / opp.scd_open_shots)
            >= 15.0
            and 100.0 * own.scu_screened / own.scu_shots >= 30.0):
        plan.append(
            f"Rosszul váltanak elzárás ellen (elzárásos lövésekből "
            f"{100.0 * opp.scd_screened_goals / opp.scd_screened_shots:.0f}"
            f"% gól esik ellenük, elzárás nélküliekből "
            f"{100.0 * opp.scd_open_goals / opp.scd_open_shots:.0f}%), "
            f"ti pedig eleve sokat játszotok elzárással (a lövéseitek "
            f"{100.0 * own.scu_screened / own.scu_shots:.0f}%-a) — "
            "minden figura zárral záruljon: beállós zár az átlövő "
            "őrzőjére, és a zár mögül azonnal lövés.")

    # 77) Az ő elzárás nélküli lövéseik × a ti blokk-falatok: a
    # magára hagyott lövőt a sánc megeszi.
    if (opp.scu_shots >= 8 and own.blocks >= 5
            and 100.0 * opp.scu_screened / opp.scu_shots <= 10.0):
        plan.append(
            f"Elzárás nélkül lőnek (az őrzött lövéseik csak "
            f"{100.0 * opp.scu_screened / opp.scu_shots:.0f}%-ánál "
            f"van elzárás), ti pedig eleve jól blokkoltok "
            f"({own.blocks} blokk) — a lövőjük magára marad: "
            "agresszív kilépés kész sánccal, váltásra nem kell "
            "készülni, a kapus a maradék sarokra állhat.")

    # 76) Az ő egy-oldalas támadásuk × a ti szerzés-gépezetetek: a
    # kedvenc oldaluk passzsávjai a ti vadászterületetek.
    if (opp.ssw_passes >= 30 and own.steal_n >= 8
            and 100.0 * opp.ssw_switches / opp.ssw_passes <= 3.0):
        plan.append(
            f"Egy oldalon ragadnak (a támadó passzaik csak "
            f"{100.0 * opp.ssw_switches / opp.ssw_passes:.0f}%-a "
            f"oldalváltás), ti pedig sokat szerzitek a labdát "
            f"({own.steal_n} szerzés) — told el a falat a kedvenc "
            "oldalukra és vadássz a bejátszásaikra: a szűk oldalon "
            "kényszerített passzokból jön a szerzés és a lerohanás.")

    # 75) Az ő lerohanás-érzékeny kapusuk × a ti lerohanás-
    # gépezetetek: minden szerzés után futni kell.
    if (opp.gkb_fast_faced >= 4 and opp.gkb_set_faced >= 4
            and own.trans_steals >= 4 and own.trans_quick_goals >= 2
            and (100.0 * opp.gkb_set_saves / opp.gkb_set_faced)
            - (100.0 * opp.gkb_fast_saves / opp.gkb_fast_faced)
            >= 15.0):
        plan.append(
            f"A kapusuk a lerohanásokra érzékeny (gyorsindítás ellen "
            f"{100.0 * opp.gkb_fast_saves / opp.gkb_fast_faced:.0f}% "
            f"védés, rendezett ellen "
            f"{100.0 * opp.gkb_set_saves / opp.gkb_set_faced:.0f}%), "
            f"a ti lerohanás-gépezetetek pedig termel "
            f"({own.trans_quick_goals} gyors gól {own.trans_steals} "
            "szerzésből) — minden labdaszerzés után FUSS: az első "
            "hullám végig kényszer legyen rajtuk.")

    # 74) Az ő kombinatív góltermelésük × a ti rés-mentes falatok: ha
    # a hosszú akcióikra nem szakad fel a fal, elfogy az ötletük.
    if (opp.gb_goals >= 4 and own.wg_frames >= 100
            and 100.0 * opp.gb_long / opp.gb_goals >= 50.0
            and 100.0 * own.wg_wide / own.wg_frames <= 20.0):
        plan.append(
            f"A góljaik {100.0 * opp.gb_long / opp.gb_goals:.0f}%-a "
            f"hosszú, 5+ passzos akció vége, a ti falatok viszont "
            f"rés-mentes (a kockák csak "
            f"{100.0 * own.wg_wide / own.wg_frames:.0f}%-ában van "
            "3,5 m+ rés) — ez a ti meccsetek: türelem a falban, semmi "
            "korai kilépés, és a nyolcadik passznál is fegyelem — "
            "előbb fogy el az ötletük, mint a ti türelmetek.")

    # 73) Az ő egy-emberes előkészítésük × a ti labdaszerzésetek: a
    # kulcs-előkészítő passzsávja a ti vadászterületetek.
    if (opp.ac_assists >= 6 and own.steal_n >= 8
            and opp.ac_top_assists / opp.ac_assists >= 0.5):
        plan.append(
            f"Az előkészítésük egy emberen múlik (a gólpasszaik "
            f"{100.0 * opp.ac_top_assists / opp.ac_assists:.0f}%-a "
            f"egy játékostól jön), ti pedig sokat szerzitek a labdát "
            f"({own.steal_n} szerzés) — a kulcs-előkészítő passzsávja "
            "a vadászterületetek: előfogás az ő sávjában, és a "
            "szerzésből azonnal indul a lerohanás.")

    # 72) Az ő lassú középkezdésük × a ti elöl-szerző presszetek: a
    # gól utáni letámadás dupla gólt érhet.
    if (opp.rs_restarts >= 4 and own.steal_n >= 8
            and 100.0 * opp.rs_fast / opp.rs_restarts <= 20.0
            and own.steal_high / own.steal_n >= 0.35):
        plan.append(
            f"Lassan indítanak középről (átlag "
            f"{opp.rs_sum_s / opp.rs_restarts:.0f} mp a kapott gól "
            f"után), ti pedig elöl szerzitek a labdát "
            f"({own.steal_high}/{own.steal_n} magas szerzés) — gól "
            "után NE hátra, hanem előre: letámadott középkezdésből a "
            "második gól fél percen belül jöhet, ez a sorozat-gyilkos "
            "fegyveretek.")

    # 71) Az ő labdafogó lövőik × a ti blokk-falatok: aki sokáig
    # fogja a labdát, annak a blokk mindig odaér.
    if (opp.sr_shots >= 8 and own.blocks >= 5
            and 100.0 * opp.sr_quick / opp.sr_shots <= 25.0):
        plan.append(
            f"A lövőik sokáig fogják a labdát (csak "
            f"{100.0 * opp.sr_quick / opp.sr_shots:.0f}% gyors "
            f"elsütés), ti pedig eleve jól blokkoltok "
            f"({own.blocks} blokk) — a blokk ellenük mindig odaér: "
            "agresszív kilépés a lövőre, kész sánc, és a kapus a "
            "maradék sarokra állhat.")

    # 70) Az ő gyenge beálló-őrzésük × a ti beállós játékotok: amit
    # nem bírnak, abból ti amúgy is sokat játszotok.
    if (opp.pd_pivot_attacks >= 6 and opp.pd_other_attacks > 0
            and own.pivot_attacks >= 6 and own.pivot_total_attacks > 0
            and (100.0 * opp.pd_pivot_goals / opp.pd_pivot_attacks
                 - 100.0 * opp.pd_other_goals / opp.pd_other_attacks)
            >= 15.0
            and own.pivot_attacks / own.pivot_total_attacks >= 0.3):
        plan.append(
            f"A beálló-őrzésük gyenge (az ellenük vezetett beállós "
            f"támadások "
            f"{100.0 * opp.pd_pivot_goals / opp.pd_pivot_attacks:.0f}"
            f"%-a gól, beálló nélkül csak "
            f"{100.0 * opp.pd_other_goals / opp.pd_other_attacks:.0f}"
            f"%), ti pedig eleve sokat játszotok a beállóval "
            f"({own.pivot_attacks}/{own.pivot_total_attacks} támadás) — "
            "vigyétek a meccset a beállóra: elöl-mögött váltás, "
            "beúszás a kettőzésük mögé, és minden figura a beállón "
            "keresztül záruljon.")

    # 69) Az ő elcsíphető indításuk × a ti elöl-szerző presszetek: a
    # kihozataluk a ti vadászterületetek.
    if (opp.gos_outlets >= 6 and own.steal_n >= 8
            and 100.0 * opp.gos_lost / opp.gos_outlets >= 25.0
            and own.steal_high / own.steal_n >= 0.35):
        plan.append(
            f"A kapus-indításuk elcsíphető ({opp.gos_lost}/"
            f"{opp.gos_outlets} az ellenfélnél köt ki), ti pedig elöl "
            f"szerzitek a labdát ({own.steal_high}/{own.steal_n} magas "
            "szerzés) — a kihozataluk a ti vadászterületetek: teljes "
            "letámadás minden kapus-labdánál, az elcsípett indítás "
            "üres kapura menő kontra.")

    # 68) Az ő álló támadásuk × a ti kilépős védekezésetek: a
    # statikus támadó a kilépő védőnek nem tud válaszolni.
    if (opp.am_time_s >= 120.0 and own.defensive_pressure_m
            and own.def_shots_against >= 4
            and opp.am_dist_m / opp.am_time_s <= 0.9
            and own.defensive_pressure_m <= 1.3):
        plan.append(
            f"A támadásuk áll (átlag "
            f"{opp.am_dist_m / opp.am_time_s:.1f} m/s szervezett "
            f"támadásban), ti pedig eleve szorosan, kilépve védekeztek "
            f"(átlag {own.defensive_pressure_m:.1f} m a labdásra) — "
            "toljátok fel a kilépést nyugodtan: az álló támadó "
            "mellől nem mozdul el senki, a segítség nem érkezik, a "
            "presszetek ingyen van.")

    # 67) Az ő réses faluk × a ti betörés-játékotok: a rés pont annak
    # a fegyvernek kedvez, amivel ti a legtöbbet éltek.
    if (opp.wg_frames >= 100 and own.break_entries >= 8
            and 100.0 * opp.wg_wide / opp.wg_frames >= 40.0):
        plan.append(
            f"A faluk réses (a rendezett védekezésük kockáinak "
            f"{100.0 * opp.wg_wide / opp.wg_frames:.0f}%-ában 3,5 m+ "
            f"rés), ti pedig sokat éltek betörésből "
            f"({own.break_entries} betörés) — az egy az egy elleni "
            "betörés ellenük nem kockázat, hanem a terv: a rést "
            "támadó betörő mögé beúszó beálló, és kész a ziccer.")

    # 66) Az ő néma gólcsendjük × a ti elöl-szerző presszetek: ha
    # egyszer megfogtátok őket, a pressz tartva tartja a csendet.
    if (opp.da_drought_s >= 300.0 and own.steal_n >= 8
            and opp.da_shots / (opp.da_drought_s / 60.0) <= 0.3
            and own.steal_high / own.steal_n >= 0.35):
        plan.append(
            f"A gólcsendjük néma (a leghosszabb csendjeikben, "
            f"{opp.da_drought_s / 60.0:.0f} perc alatt csak "
            f"{opp.da_shots} lövésig jutottak), ti pedig elöl "
            f"szerzitek a labdát ({own.steal_high}/{own.steal_n} magas "
            "szerzés) — ha egyszer leállítottátok a támadásukat, NE "
            "váltsatok: a presszetek tartja a csendet, ők maguktól "
            "nem találnak vissza.")

    # 65) Az ő gyenge fal-oldaluk × a ti erős támadó-oldalatok: ha a
    # kettő egybeesik, a meccsterv magától megírja magát.
    _p65_wings = opp.csb_left + opp.csb_right
    _p65_own_wings = own.sb_left + own.sb_right
    if _p65_wings >= 8 and _p65_own_wings >= 8:
        _p65_pct = 100.0 * max(opp.csb_left, opp.csb_right) / _p65_wings
        _p65_weak = "bal" if opp.csb_left >= opp.csb_right else "jobb"
        # A fal balja a támadó jobbja: az ő bal-gyengéjükhöz a ti
        # jobb-erősségetek illik (és fordítva).
        _p65_own_match = (own.sb_right if _p65_weak == "bal"
                          else own.sb_left)
        if (_p65_pct >= 65.0
                and _p65_own_match / _p65_own_wings >= 0.55):
            plan.append(
                f"A faluk {_p65_weak} oldala átjárható (a kapott "
                f"szélső-sávos lövések {_p65_pct:.0f}%-a arról jön), "
                "és a ti támadásotok épp arról az oldalról a "
                f"legerősebb ({_p65_own_match}/{_p65_own_wings} "
                "szélső-sávos lövés) — a meccsterv kész: a figuráitok "
                "arra az oldalra fussanak ki, a gyenge oldal-védőjük "
                "mögé.")

    # 64) Az ő drága eladásaik × a ti kontra-gólgépetek: a szerzés
    # utáni azonnali indulás náluk a legtöbbet hozza.
    if (opp.tpu_turnovers >= 6 and own.trans_steals >= 4
            and own.trans_quick_goals >= 2
            and opp.tpu_punished / opp.tpu_turnovers >= 0.35):
        plan.append(
            f"Az eladásaik drágák (a {opp.tpu_turnovers} eladásukból "
            f"{opp.tpu_punished} után fél percen belül gólt kaptak), "
            f"ti pedig jól váltjátok gólra a szerzést "
            f"({own.trans_quick_goals}/{own.trans_steals} gyors gól) "
            "— minden labdaszerzés után azonnali indulás: ellenük a "
            "kontra nem lehetőség, hanem kötelező első opció.")

    # 63) Az ő hosszú-indításos kapusuk × a ti gyors
    # visszarendeződésetek: a hosszú labda nem talál üres területet.
    if (opp.gko_outlets >= 6 and own.rec_transitions >= 6
            and opp.gko_long / opp.gko_outlets >= 0.5
            and own.rec_slow / own.rec_transitions <= 0.2):
        plan.append(
            f"Hosszú indításokból élnek (a kapus-passzaik "
            f"{100.0 * opp.gko_long / opp.gko_outlets:.0f}%-a 15 m "
            f"feletti), ti pedig gyorsan visszarendeződtök (csak "
            f"{own.rec_slow}/{own.rec_transitions} lassú "
            "visszafutás) — a hosszú labdájuk nálatok nem talál üres "
            "területet: zárjátok a rövid opciót is letámadó emberrel "
            "a kapusra, és a kényszer-indítás a tiétek.")

    # 62) Az ő területi fölény-esésük × a ti kitartó tempótok: a
    # hajrában a pálya magától átfordul — akkor kell rákapcsolni.
    if (opp.tf_fh_frames >= 100 and opp.tf_sh_frames >= 100
            and own.tpf_fh_min >= 8.0 and own.tpf_sh_min >= 8.0):
        _p62_fh = 100.0 * opp.tf_fh_opp / opp.tf_fh_frames
        _p62_sh = 100.0 * opp.tf_sh_opp / opp.tf_sh_frames
        _p62_own_fh = own.tpf_fh_attacks / own.tpf_fh_min
        _p62_own_sh = own.tpf_sh_attacks / own.tpf_sh_min
        if _p62_fh - _p62_sh >= 12.0 and _p62_own_sh >= _p62_own_fh:
            plan.append(
                f"A 2. félidőre hátracsúszik a játékuk (területi "
                f"fölény {_p62_fh:.0f}% → {_p62_sh:.0f}%), ti pedig a "
                "2. félidőben is tartjátok a tempót — az 1. félidei "
                "nyomásukat álljátok ki kockázat nélkül, a hajrában "
                "viszont tudatosan toljátok fel a játékot: ott már ti "
                "diktáltok, ők csak kapaszkodnak.")

    # 61) Az ő kiadás-függő támadásuk × a ti labdaszerzésetek: az
    # elvágott gólpassz nem csak védekezés — azonnali kontra.
    if (opp.ad_goals >= 6 and own.trans_steals >= 5
            and opp.ad_assisted / opp.ad_goals >= 0.70):
        plan.append(
            f"Kiadásból élnek (a góljaik "
            f"{100.0 * opp.ad_assisted / opp.ad_goals:.0f}%-a "
            f"gólpasszos), ti pedig jó labdaszerzők vagytok "
            f"({own.trans_steals} szerzés) — vadásszátok a "
            "gólpasszaikat: aktív kéz a kiadó-sávokban, a beálló elé "
            "lépés — az elcsípett kiadás nálatok azonnali kontra.")

    # 60) Az ő áteresztő faluk × a ti lepattanó-harcotok: a második
    # hullám oda megy, ahol amúgy is erősek vagytok.
    if (opp.sca_opp_misses >= 6 and own.sc_misses >= 6
            and opp.sca_allowed / opp.sca_opp_misses >= 0.35
            and own.sc_second / own.sc_misses >= 0.35):
        plan.append(
            f"A faluk nem zár a lövések után (az ellenfelek a kimaradt "
            f"lövéseik "
            f"{100.0 * opp.sca_allowed / opp.sca_opp_misses:.0f}%-ánál "
            f"újra lőhettek), ti pedig amúgy is jól harcoljátok a "
            f"lepattanót ({own.sc_second}/{own.sc_misses} visszaszerzés) "
            "— minden lövésetekre menjen be a lepattanó-ember: a "
            "második hullám ellenük terv, nem véletlen.")

    # 59) Az ő pressz-érzékenységük × a ti szoros falatok: aki
    # amúgy is testközelben védekezik, annak ez ingyen-termelés.
    _p59_press_n = opp.ps_press_passes + opp.ps_press_to
    _p59_free_n = opp.ps_free_passes + opp.ps_free_to
    if (_p59_press_n >= 10 and _p59_free_n >= 10
            and own.defensive_pressure_m
            and own.defensive_pressure_m <= 1.3):
        _p59_press = 100.0 * opp.ps_press_to / _p59_press_n
        _p59_free = 100.0 * opp.ps_free_to / _p59_free_n
        if _p59_press - _p59_free >= 15.0:
            plan.append(
                f"Pressz-érzékenyek (testközeli védőnél az eladásaik "
                f"{_p59_press:.0f}%-ra ugranak, szabadon "
                f"{_p59_free:.0f}%), ti pedig eleve szorosan védekeztek "
                f"(átlag {own.defensive_pressure_m:.1f} m-re a "
                "labdástól) — ez ingyen-termelés: az első védő minden "
                "labdaátvételnél lépjen testközelbe, a második pedig "
                "készüljön a kipattanó labdára.")

    # 58) Az ő korai eladásaik × a ti elöl-szerzésetek: a magas pressz
    # ott termel, ahol ők a leggyengébbek — a kihozatalnál.
    if (opp.tt_timed >= 6 and opp.tt_early / opp.tt_timed >= 0.5
            and own.steal_n >= 4 and own.steal_high >= 3):
        plan.append(
            f"Korai eladók (az eladásaik "
            f"{100.0 * opp.tt_early / opp.tt_timed:.0f}%-a a birtoklás "
            f"első 10 másodpercében), ti pedig elöl is szerzitek a "
            f"labdát ({own.steal_high}/{own.steal_n} szerzés a felső "
            "harmadban) — toljátok fel a presszt a kihozatalukra: az "
            "első passzukra lépjetek rá, és a szerzésből azonnal "
            "üres kapura fordultok.")

    # 57) Az ő kapus-gyengeoldaluk × a ti célzás-pontosságotok: aki
    # pontosan lő, annak a gyenge sarok kész gól-recept.
    _p57_goals = opp.gw_bal + opp.gw_kozep + opp.gw_jobb
    if _p57_goals >= 6 and own.ac_attempts >= 8 \
            and own.ac_on_target / own.ac_attempts >= 0.70:
        _p57_tally = {"bal": opp.gw_bal, "közép": opp.gw_kozep,
                      "jobb": opp.gw_jobb}
        _p57_weak = max(_p57_tally, key=lambda k: _p57_tally[k])
        if _p57_tally[_p57_weak] / _p57_goals >= 0.45:
            plan.append(
                f"A kapujuk a(z) {_p57_weak} oldalán átjárható (oda "
                f"kapták a gólok "
                f"{100.0 * _p57_tally[_p57_weak] / _p57_goals:.0f}%-át), "
                f"ti pedig pontosan céloztok (a lövéseitek "
                f"{100.0 * own.ac_on_target / own.ac_attempts:.0f}%-a "
                "kapura tart) — a befejezés-terv egy mondat: a(z) "
                f"{_p57_weak} oldalra fejezzetek be, a kapus "
                "szemszögéből nézve.")

    # 56) Az ő fő lövőjük × a ti aktív falatok: a személyre szabott
    # kettőzés + blokk a legrövidebb út a támadásuk lefejezéséhez.
    if (opp.sc_shots >= 12 and own.blocks >= 3
            and opp.sc_top_shots / opp.sc_shots >= 0.35):
        _p56_share = 100.0 * opp.sc_top_shots / opp.sc_shots
        plan.append(
            f"A lövés-terhelésük egy emberre épül (a fő lövőjük adja a "
            f"lövéseik {_p56_share:.0f}%-át), a ti falatok pedig aktív "
            f"({own.blocks} blokk) — szabjátok rá: korai kettőzés a fő "
            "lövőn, a blokk az ő megszokott sávjára készül, a többiek "
            "lövését pedig vállaljátok be.")

    # 45) Az ő mentőöv nélküli kapus-posztjuk × a ti erős kezdésetek: a
    # korai nyomás az egész meccsüket megroppanthatja.
    if (opp.gkc_changes >= 2 and opp.gkc_pre_faced >= 4
            and opp.gkc_post_faced >= 4
            and own.open_first_matches >= 1
            and own.open_for > own.open_against):
        _g45_pre = 100.0 * opp.gkc_pre_saves / opp.gkc_pre_faced
        _g45_post = 100.0 * opp.gkc_post_saves / opp.gkc_post_faced
        if _g45_pre - _g45_post >= 15.0:
            plan.append(
                f"A kapuscseréjük sem segít ({_g45_pre:.0f}% → "
                f"{_g45_post:.0f}% a cserék után), ti pedig erősen "
                f"kezdtek ({own.open_for}–{own.open_against} a korai "
                "gólokból) — az első percekben menjetek rá az első "
                "kapusukra: ha megtörik, a padon sincs mentőöv, és az "
                "egész meccsük megroppan.")

    # 44) Az ő hetest nem fogó kapusuk × a ti hetes-kiharcolótok: a
    # lerántott labda ellenük biztos gól — kiharcolni kell, nem lőni.
    if (opp.s7d_faced >= 4 and opp.s7d_saved == 0
            and own.seven_earners and own.seven_earners[0]["earned"] >= 2):
        _g44_e = own.seven_earners[0]
        plan.append(
            f"A kapusuk hetest nem fog ({opp.s7d_faced} kapura tartóból "
            f"0 védés), nálatok pedig a(z) {_g44_e['player_id']}. játékos "
            f"rendre kiharcolja ({_g44_e['earned']} hetes) — járassátok "
            "rá a labdát a betörésekhez: minden kiharcolt hetes ellenük "
            "kész gól.")

    # 43) Az ő elengedett félidő-zárásuk × a ti erős zárásotok: a szünet
    # előtti 5 perc a ti terepetek — dupla lendület az öltözőbe.
    if (opp.fhc_matches >= 1 and own.fhc_matches >= 1
            and opp.fhc_against - opp.fhc_for >= 3
            and own.fhc_for > own.fhc_against):
        plan.append(
            f"Az 1. félidő hajráját elengedik ({opp.fhc_for}–"
            f"{opp.fhc_against} a szünet előtti 5 percben), ti pedig "
            f"erősen zártok ({own.fhc_for}–{own.fhc_against}) — a félidő "
            "utolsó 5 percére időzítsetek egy tempó-emelést: onnan "
            "lendülettel mentek az öltözőbe, ők pedig fejben már a "
            "szünetben lesznek.")

    # 42) Az ő szoros-meccs gyengeségük × a ti hajrá-erőtök: a meccset
    # szoros hajrába kell vinni — ott ők megroppannak, ti nem.
    if (opp.cg_losses >= 2 and opp.cg_losses >= 2 * opp.cg_wins
            and own.clutch_matches >= 1
            and own.clutch_goals_for > own.clutch_goals_against):
        plan.append(
            f"A szoros meccseket elbukják ({opp.cg_wins}–{opp.cg_losses} "
            f"az 1-2 gólos meccseken), ti pedig erősek vagytok a hajrában "
            f"({own.clutch_goals_for}–{own.clutch_goals_against}) — nem "
            "kell szétlőni őket: elég meccsben maradni, mert a szoros "
            "hajrában ők remegnek, ti nem.")

    # 41) Az ő gól utáni elalvásuk × a ti gyors válaszotok: minden kapott
    # gólra azonnali válasz jöhet — a középkezdésük után kell rohanni.
    if (opp.pgl_goals >= 5
            and 100.0 * opp.pgl_quick / opp.pgl_goals >= 40.0
            and own.response_n >= 4
            and own.response_sum_s / own.response_n <= 60.0):
        _g41_rate = 100.0 * opp.pgl_quick / opp.pgl_goals
        _g41_resp = own.response_sum_s / own.response_n
        plan.append(
            f"Gól után elalszanak (a góljaik {_g41_rate:.0f}%-ára fél "
            f"percen belül jött válasz), ti pedig gyorsan válaszoltok "
            f"(átlag {_g41_resp:.0f} mp) — minden kapott gól után a "
            "középkezdésükre AZONNAL menjetek rá: az ő góljuk ne lendület "
            "legyen nekik, hanem a ti következő gólotok előszobája.")

    # 40) Az ő hajrá-kiállításaik × a ti emberelőny-játékotok: a meccs
    # végén emberelőny várható — előre gyakorolt figurával kell büntetni.
    if (opp.disc_fh_susp + opp.disc_sh_susp >= 3
            and opp.disc_sh_susp - opp.disc_fh_susp >= 2
            and own.pp_shots >= 3 and own.pp_goals >= 1):
        _g40_eff = 100.0 * own.pp_goals / own.pp_shots
        plan.append(
            f"A kiállításaik a 2. félidőben jönnek ({opp.disc_fh_susp} → "
            f"{opp.disc_sh_susp}), ti pedig élni tudtok az emberelőnnyel "
            f"({own.pp_goals}/{own.pp_shots} lövésből gól, "
            f"{_g40_eff:.0f}%) — a hajrában vigyétek be az egy-egy "
            "párharcokat, és legyen kész az emberelőny-figura: ott "
            "dőlhet el a meccs.")

    # 39) Az ő elengedett vezetéseik × a ti hajrá-erőtök: hátrányban is
    # türelmesen kell játszani — ez a csapat a végén elereszti a meccset.
    if (opp.lp_blown >= 1 and own.clutch_matches >= 1
            and own.clutch_goals_for > own.clutch_goals_against):
        plan.append(
            f"Vezetést is elengednek ({opp.lp_led} db 3+ gólos ellépésből "
            f"{opp.lp_blown} ment el), ti pedig erősek vagytok a hajrában "
            f"({own.clutch_goals_for}–{own.clutch_goals_against}) — ha "
            "hátrányba kerültök, ne kapkodjatok: türelmes játékkal a "
            "meccs végén visszajön, ők pedig görcsölni kezdenek.")

    # 38) Az ő 2. félidőre eső kapusuk × a ti hajrá-erőtök: a meccs végén
    # a lövéseitek dupla eséllyel mennek be.
    if (opp.gsf_fh_faced >= 4 and opp.gsf_sh_faced >= 4
            and own.clutch_matches >= 1
            and own.clutch_goals_for > own.clutch_goals_against):
        _g38_fh = 100.0 * opp.gsf_fh_saves / opp.gsf_fh_faced
        _g38_sh = 100.0 * opp.gsf_sh_saves / opp.gsf_sh_faced
        if _g38_fh - _g38_sh >= 15.0:
            plan.append(
                f"A kapusuk a 2. félidőre esik ({_g38_fh:.0f}% → "
                f"{_g38_sh:.0f}% védés), ti pedig jók vagytok a hajrában "
                f"({own.clutch_goals_for}–{own.clutch_goals_against}) — a "
                "meccs végén vállaljátok bátran a lövést: ott a kapusuk "
                "már nem ment meg mindent.")

    # 37) Az ő 2. félidei eladás-dömpingjük × a ti szerzés-gólgépetek: a
    # présnyomást a meccs második felére kell időzíteni.
    if (opp.tof_fh_poss_s >= 120.0 and opp.tof_sh_poss_s >= 120.0
            and own.trans_steals >= 4 and own.trans_quick_goals >= 2):
        _t37_fh = 60.0 * opp.tof_fh_to / opp.tof_fh_poss_s
        _t37_sh = 60.0 * opp.tof_sh_to / opp.tof_sh_poss_s
        if _t37_sh - _t37_fh >= 0.2:
            plan.append(
                f"A 2. félidőre megugrik az eladás-ütemük ({_t37_fh:.1f} → "
                f"{_t37_sh:.1f} eladás/perc), ti pedig a szerzéseiteket "
                f"gólra váltjátok ({own.trans_quick_goals}/"
                f"{own.trans_steals}) — a présnyomást a második félidőre "
                "időzítsd: ott dől be a labdabiztonságuk, és onnan jönnek "
                "az olcsó gólok.")

    return plan


def _merge_attack_origins(reports) -> dict:
    """Eredet szerinti támadás/gól számok pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for k, v in (r.attack_origins or {}).items():
            cur = tally.setdefault(k, {"attacks": 0, "goals": 0})
            cur["attacks"] += int(v.get("attacks", 0))
            cur["goals"] += int(v.get("goals", 0))
    return tally


def _merge_shooter_overperf(reports) -> list:
    """Lövőnkénti befejezés-többlet (gól − xG) pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for rec in (r.shooter_overperf or []):
            tally[rec["player_id"]] = round(
                tally.get(rec["player_id"], 0.0) + float(rec["diff"]), 2)
    return [{"player_id": pid, "diff": d}
            for pid, d in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_assist_pairs(reports) -> list:
    """(gólpasszoló, lövő) párok gólszámainak pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for pr in (r.assist_pairs or []):
            k = (pr["from"], pr["to"])
            tally[k] = tally.get(k, 0) + int(pr["goals"])
    return [{"from": a, "to": b, "goals": n}
            for (a, b), n in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_shooter_fades(reports) -> list:
    """Játékosonkénti tempó-esés összegek pontos összevonása."""
    tally: dict = {}
    for r in reports:
        for rec in (r.shooter_fades or []):
            cur = tally.setdefault(rec["player_id"], [0.0, 0])
            cur[0] += float(rec["drop_sum_pct"])
            cur[1] += int(rec["n"])
    return [{"player_id": pid, "drop_sum_pct": round(d, 1), "n": n}
            for pid, (d, n) in sorted(tally.items())]


def _merge_shooter_zones(reports) -> list:
    """(játékos, zóna) párok lövésszámainak pontos összegzése meccsek közt."""
    tally: dict = {}
    for r in reports:
        for rec in (r.shooter_zones or []):
            k = (rec["player_id"], rec["zone"])
            tally[k] = tally.get(k, 0) + int(rec["shots"])
    return [{"player_id": pid, "zone": z, "shots": n}
            for (pid, z), n in sorted(tally.items(), key=lambda kv: -kv[1])]

def combine_reports(reports: list[ScoutingReport]) -> ScoutingReport:
    """Több meccs jelentését egyesíti egy csapatról (több meccs = valós profil).

    A számszerű mezőket átlagolja, a darabszámokat összegzi, a védőforma-megoszlást
    súlyozottan egyesíti, és újraszámolja az edzői kulcsokat az összképből.
    """
    if not reports:
        raise ValueError("üres jelentéslista")
    if len(reports) == 1:
        return reports[0]

    n = len(reports)
    def avg(attr):
        return round(sum(getattr(r, attr) for r in reports) / n, 2)

    # Védőforma-megoszlás egyesítése (átlag a jelentések között).
    merged_dist: dict[str, float] = {}
    for r in reports:
        for k, v in r.defense_distribution.items():
            merged_dist[k] = merged_dist.get(k, 0.0) + v / n
    merged_dist = {k: round(v, 1) for k, v in sorted(merged_dist.items(), key=lambda kv: -kv[1])}

    # Lövési zónák egyesítése: zónánként összegzett lövés/gól.
    merged_zones: dict[str, dict] = {}
    for r in reports:
        for z, rec in r.shot_zones.items():
            m = merged_zones.setdefault(z, {"shots": 0, "goals": 0})
            m["shots"] += rec["shots"]
            m["goals"] += rec["goals"]
    merged_zones = dict(sorted(merged_zones.items(), key=lambda kv: -kv[1]["shots"]))

    shots = sum(r.shots for r in reports)
    goals = sum(r.goals for r in reports)
    rep = ScoutingReport(
        team=reports[0].team,
        team_name=reports[0].team_name,
        matches=n,
        attack_share_pct=avg("attack_share_pct"),
        fast_break_pct=avg("fast_break_pct"),
        avg_ball_speed_ms=avg("avg_ball_speed_ms"),
        avg_attack_duration_s=avg("avg_attack_duration_s"),
        defense_main=next(iter(merged_dist), "—"),
        defense_distribution=merged_dist,
        attack_centroid_x=avg("attack_centroid_x"),
        attack_centroid_y=avg("attack_centroid_y"),
        num_figures=sum(r.num_figures for r in reports),
        attacks=sum(r.attacks for r in reports),
        shots=shots,
        goals=goals,
        turnovers=sum(r.turnovers for r in reports),
        shot_efficiency_pct=round(100.0 * goals / shots, 1) if shots else 0.0,
        shot_zones=merged_zones,
        key_players=[],  # játékos-azonosítók meccsenként eltérők; összevonás nem triviális
        gk_on_target=sum(r.gk_on_target for r in reports),
        gk_saves=sum(r.gk_saves for r in reports),
        gk_big_saves=sum(r.gk_big_saves for r in reports),
        gk_xg_saved=round(sum(r.gk_xg_saved for r in reports), 2),
        gk_xg_prevented=round(sum(r.gk_xg_prevented for r in reports), 2),
        gk_outlets=sum(r.gk_outlets for r in reports),
        gk_outlet_sum_s=round(sum(r.gk_outlet_sum_s for r in reports), 1),
        gk_outlet_fast=sum(r.gk_outlet_fast for r in reports),
        big_total=sum(r.big_total for r in reports),
        big_missed=sum(r.big_missed for r in reports),
        empty_net_s=round(sum(r.empty_net_s for r in reports), 1),
        empty_net_conceded=sum(r.empty_net_conceded for r in reports),
        en_windows=sum(r.en_windows for r in reports),
        en_trailing=sum(r.en_trailing for r in reports),
        en_endgame=sum(r.en_endgame for r in reports),
        pace_attacks=sum(r.pace_attacks for r in reports),
        pace_minutes=round(sum(r.pace_minutes for r in reports), 1),
        attack_origins=_merge_attack_origins(reports),
        rec_transitions=sum(r.rec_transitions for r in reports),
        rec_sum_s=round(sum(r.rec_sum_s for r in reports), 1),
        rec_slow=sum(r.rec_slow for r in reports),
        positions={tid: poszt for r in reversed(reports)
                   for tid, poszt in (r.positions or {}).items()},
        wing_goals=sum(r.wing_goals for r in reports),
        wing_total_goals=sum(r.wing_total_goals for r in reports),
        post_goals={
            p_: sum((r.post_goals or {}).get(p_, 0) for r in reports)
            for p_ in {k for r in reports
                       for k in (r.post_goals or {})}},
        shooter_zones=_merge_shooter_zones(reports),
        shooter_fades=_merge_shooter_fades(reports),
        assist_pairs=_merge_assist_pairs(reports),
        shooter_overperf=_merge_shooter_overperf(reports),
        blockers=_merge_blockers(reports),
        gk_outlet_targets=_merge_outlet_targets(reports),
        fb_finishers=_merge_fb_finishers(reports),
        seven_takers=_merge_seven_takers(reports),
        seven_earners=_merge_seven_earners(reports),
        susp_earners=_merge_susp_earners(reports),
        susp_players=_merge_susp_players(reports),
        markers=_merge_markers(reports),
        pivot_total_attacks=sum(r.pivot_total_attacks for r in reports),
        pivot_attacks=sum(r.pivot_attacks for r in reports),
        pivot_goals=sum(r.pivot_goals for r in reports),
        pivot_other_goals=sum(r.pivot_other_goals for r in reports),
        break_entries=sum(r.break_entries for r in reports),
        break_lanes=_merge_break_lanes(reports),
        pass_attacks=sum(r.pass_attacks for r in reports),
        pass_total=sum(r.pass_total for r in reports),
        pass_buckets=_merge_pass_buckets(reports),
        rotation_used_sum=sum(r.rotation_used_sum for r in reports),
        rotation_regulars_sum=sum(r.rotation_regulars_sum
                                  for r in reports),
        rotation_matches=sum(r.rotation_matches for r in reports),
        ball_winners=_merge_ball_winners(reports),
        turnover_players=_merge_turnover_players(reports),
        clutch_scorers=_merge_clutch_scorers(reports),
        scorer_goals=_merge_scorer_goals(reports),
        sup_frames=sum(r.sup_frames for r in reports),
        sup_sum_m=round(sum(r.sup_sum_m for r in reports), 1),
        sup_iso=sum(r.sup_iso for r in reports),
        tilt_frames=sum(r.tilt_frames for r in reports),
        tilt_opp=sum(r.tilt_opp for r in reports),
        defw_sum_m=round(sum(r.defw_sum_m for r in reports), 1),
        defw_frames=sum(r.defw_frames for r in reports),
        pt_passes=sum(r.pt_passes for r in reports),
        pt_poss_s=round(sum(r.pt_poss_s for r in reports), 1),
        blk_for=sum(r.blk_for for r in reports),
        blk_attempts=sum(r.blk_attempts for r in reports),
        steal_n=sum(r.steal_n for r in reports),
        steal_high=sum(r.steal_high for r in reports),
        plen_n=sum(r.plen_n for r in reports),
        plen_sum_m=round(sum(r.plen_sum_m for r in reports), 1),
        plen_long=sum(r.plen_long for r in reports),
        shtim_n=sum(r.shtim_n for r in reports),
        shtim_sum_s=round(sum(r.shtim_sum_s for r in reports), 1),
        shtim_early=sum(r.shtim_early for r in reports),
        prf_fh_sum_m=round(sum(r.prf_fh_sum_m for r in reports), 1),
        prf_fh_n=sum(r.prf_fh_n for r in reports),
        prf_sh_sum_m=round(sum(r.prf_sh_sum_m for r in reports), 1),
        prf_sh_n=sum(r.prf_sh_n for r in reports),
        to_n=sum(r.to_n for r in reports),
        to_broke=sum(r.to_broke for r in reports),
        to_failed=sum(r.to_failed for r in reports),
        tof_fh_to=sum(r.tof_fh_to for r in reports),
        tof_fh_poss_s=round(sum(r.tof_fh_poss_s for r in reports), 1),
        tof_sh_to=sum(r.tof_sh_to for r in reports),
        tof_sh_poss_s=round(sum(r.tof_sh_poss_s for r in reports), 1),
        gsf_fh_faced=sum(r.gsf_fh_faced for r in reports),
        gsf_fh_saves=sum(r.gsf_fh_saves for r in reports),
        gsf_sh_faced=sum(r.gsf_sh_faced for r in reports),
        gsf_sh_saves=sum(r.gsf_sh_saves for r in reports),
        lp_led=sum(r.lp_led for r in reports),
        lp_blown=sum(r.lp_blown for r in reports),
        lp_biggest=max((r.lp_biggest for r in reports), default=0),
        disc_fh_susp=sum(r.disc_fh_susp for r in reports),
        disc_sh_susp=sum(r.disc_sh_susp for r in reports),
        pgl_goals=sum(r.pgl_goals for r in reports),
        pgl_quick=sum(r.pgl_quick for r in reports),
        cg_wins=sum(r.cg_wins for r in reports),
        cg_losses=sum(r.cg_losses for r in reports),
        cg_draws=sum(r.cg_draws for r in reports),
        s7d_faced=sum(r.s7d_faced for r in reports),
        s7d_saved=sum(r.s7d_saved for r in reports),
        gkc_changes=sum(r.gkc_changes for r in reports),
        gkc_pre_faced=sum(r.gkc_pre_faced for r in reports),
        gkc_pre_saves=sum(r.gkc_pre_saves for r in reports),
        gkc_post_faced=sum(r.gkc_post_faced for r in reports),
        gkc_post_saves=sum(r.gkc_post_saves for r in reports),
        bcp_misses=sum(r.bcp_misses for r in reports),
        bcp_punished=sum(r.bcp_punished for r in reports),
        tpf_fh_attacks=sum(r.tpf_fh_attacks for r in reports),
        tpf_fh_min=round(sum(r.tpf_fh_min for r in reports), 1),
        tpf_sh_attacks=sum(r.tpf_sh_attacks for r in reports),
        tpf_sh_min=round(sum(r.tpf_sh_min for r in reports), 1),
        htc_behind=sum(r.htc_behind for r in reports),
        htc_turned=sum(r.htc_turned for r in reports),
        htc_saved=sum(r.htc_saved for r in reports),
        pb_ties=sum(r.pb_ties for r in reports),
        pb_won=sum(r.pb_won for r in reports),
        rn_made=sum(r.rn_made for r in reports),
        rn_made_goals=sum(r.rn_made_goals for r in reports),
        rn_suffered=sum(r.rn_suffered for r in reports),
        rn_suffered_goals=sum(r.rn_suffered_goals for r in reports),
        bsm_saves=sum(r.bsm_saves for r in reports),
        bsm_sparked=sum(r.bsm_sparked for r in reports),
        ff_fh_shots=sum(r.ff_fh_shots for r in reports),
        ff_fh_goals=sum(r.ff_fh_goals for r in reports),
        ff_sh_shots=sum(r.ff_sh_shots for r in reports),
        ff_sh_goals=sum(r.ff_sh_goals for r in reports),
        ac_attempts=sum(r.ac_attempts for r in reports),
        ac_on_target=sum(r.ac_on_target for r in reports),
        sb_left=sum(r.sb_left for r in reports),
        sb_center=sum(r.sb_center for r in reports),
        sb_right=sum(r.sb_right for r in reports),
        ar_n=sum(r.ar_n for r in reports),
        ar_sum_s=round(sum(r.ar_sum_s for r in reports), 1),
        ar_sumsq_s=round(sum(r.ar_sumsq_s for r in reports), 1),
        sc_shots=sum(r.sc_shots for r in reports),
        sc_top_shots=sum(r.sc_top_shots for r in reports),
        gw_bal=sum(r.gw_bal for r in reports),
        gw_kozep=sum(r.gw_kozep for r in reports),
        gw_jobb=sum(r.gw_jobb for r in reports),
        tt_timed=sum(r.tt_timed for r in reports),
        tt_early=sum(r.tt_early for r in reports),
        ps_press_passes=sum(r.ps_press_passes for r in reports),
        ps_press_to=sum(r.ps_press_to for r in reports),
        ps_free_passes=sum(r.ps_free_passes for r in reports),
        ps_free_to=sum(r.ps_free_to for r in reports),
        sca_opp_misses=sum(r.sca_opp_misses for r in reports),
        sca_allowed=sum(r.sca_allowed for r in reports),
        sca_goals=sum(r.sca_goals for r in reports),
        ad_goals=sum(r.ad_goals for r in reports),
        ad_assisted=sum(r.ad_assisted for r in reports),
        tf_fh_frames=sum(r.tf_fh_frames for r in reports),
        tf_fh_opp=sum(r.tf_fh_opp for r in reports),
        tf_sh_frames=sum(r.tf_sh_frames for r in reports),
        tf_sh_opp=sum(r.tf_sh_opp for r in reports),
        gko_outlets=sum(r.gko_outlets for r in reports),
        gko_long=sum(r.gko_long for r in reports),
        tpu_turnovers=sum(r.tpu_turnovers for r in reports),
        tpu_punished=sum(r.tpu_punished for r in reports),
        csb_left=sum(r.csb_left for r in reports),
        csb_center=sum(r.csb_center for r in reports),
        csb_right=sum(r.csb_right for r in reports),
        da_drought_s=sum(r.da_drought_s for r in reports),
        da_shots=sum(r.da_shots for r in reports),
        wg_frames=sum(r.wg_frames for r in reports),
        wg_wide=sum(r.wg_wide for r in reports),
        am_dist_m=sum(r.am_dist_m for r in reports),
        am_time_s=sum(r.am_time_s for r in reports),
        gos_outlets=sum(r.gos_outlets for r in reports),
        gos_lost=sum(r.gos_lost for r in reports),
        pd_pivot_attacks=sum(r.pd_pivot_attacks for r in reports),
        pd_pivot_goals=sum(r.pd_pivot_goals for r in reports),
        pd_other_attacks=sum(r.pd_other_attacks for r in reports),
        pd_other_goals=sum(r.pd_other_goals for r in reports),
        sr_shots=sum(r.sr_shots for r in reports),
        sr_quick=sum(r.sr_quick for r in reports),
        rs_restarts=sum(r.rs_restarts for r in reports),
        rs_fast=sum(r.rs_fast for r in reports),
        rs_sum_s=round(sum(r.rs_sum_s for r in reports), 1),
        ac_assists=sum(r.ac_assists for r in reports),
        ac_top_assists=sum(r.ac_top_assists for r in reports),
        gb_goals=sum(r.gb_goals for r in reports),
        gb_short=sum(r.gb_short for r in reports),
        gb_long=sum(r.gb_long for r in reports),
        gkb_fast_faced=sum(r.gkb_fast_faced for r in reports),
        gkb_fast_saves=sum(r.gkb_fast_saves for r in reports),
        gkb_set_faced=sum(r.gkb_set_faced for r in reports),
        gkb_set_saves=sum(r.gkb_set_saves for r in reports),
        ssw_passes=sum(r.ssw_passes for r in reports),
        ssw_switches=sum(r.ssw_switches for r in reports),
        scu_shots=sum(r.scu_shots for r in reports),
        scu_screened=sum(r.scu_screened for r in reports),
        scd_screened_shots=sum(r.scd_screened_shots for r in reports),
        scd_screened_goals=sum(r.scd_screened_goals for r in reports),
        scd_open_shots=sum(r.scd_open_shots for r in reports),
        scd_open_goals=sum(r.scd_open_goals for r in reports),
        prk_long_tries=sum(r.prk_long_tries for r in reports),
        prk_long_to=sum(r.prk_long_to for r in reports),
        prk_short_tries=sum(r.prk_short_tries for r in reports),
        prk_short_to=sum(r.prk_short_to for r in reports),
        cpr_turnovers=sum(r.cpr_turnovers for r in reports),
        cpr_regained=sum(r.cpr_regained for r in reports),
        csq_early_shots=sum(r.csq_early_shots for r in reports),
        csq_early_xg=round(sum(r.csq_early_xg for r in reports), 2),
        csq_clutch_shots=sum(r.csq_clutch_shots for r in reports),
        csq_clutch_xg=round(sum(r.csq_clutch_xg for r in reports), 2),
        gk_depth_sum_m=round(sum(r.gk_depth_sum_m for r in reports), 1),
        gk_depth_frames=sum(r.gk_depth_frames for r in reports),
        trans_steals=sum(r.trans_steals for r in reports),
        trans_quick_goals=sum(r.trans_quick_goals for r in reports),
        sr_close_shots=sum(r.sr_close_shots for r in reports),
        sr_close_goals=sum(r.sr_close_goals for r in reports),
        sr_mid_shots=sum(r.sr_mid_shots for r in reports),
        sr_mid_goals=sum(r.sr_mid_goals for r in reports),
        sr_far_shots=sum(r.sr_far_shots for r in reports),
        sr_far_goals=sum(r.sr_far_goals for r in reports),
        gk_close_faced=sum(r.gk_close_faced for r in reports),
        gk_close_saves=sum(r.gk_close_saves for r in reports),
        gk_mid_faced=sum(r.gk_mid_faced for r in reports),
        gk_mid_saves=sum(r.gk_mid_saves for r in reports),
        gk_far_faced=sum(r.gk_far_faced for r in reports),
        gk_far_saves=sum(r.gk_far_saves for r in reports),
        place_bal=sum(r.place_bal for r in reports),
        place_kozep=sum(r.place_kozep for r in reports),
        place_jobb=sum(r.place_jobb for r in reports),
        wing_fin_shots=sum(r.wing_fin_shots for r in reports),
        wing_fin_goals=sum(r.wing_fin_goals for r in reports),
        defline_sum_m=round(sum(r.defline_sum_m for r in reports), 1),
        defline_frames=sum(r.defline_frames for r in reports),
        pdir_forward=sum(r.pdir_forward for r in reports),
        pdir_passes=sum(r.pdir_passes for r in reports),
        pdir_prog_sum=round(sum(r.pdir_prog_sum for r in reports), 1),
        asrc_szel=sum(r.asrc_szel for r in reports),
        asrc_kozep=sum(r.asrc_kozep for r in reports),
        asrc_hatso=sum(r.asrc_hatso for r in reports),
        sc_misses=sum(r.sc_misses for r in reports),
        sc_second=sum(r.sc_second for r in reports),
        sc_goals=sum(r.sc_goals for r in reports),
        suspensions=sum(r.suspensions for r in reports),
        restart_for=sum(r.restart_for for r in reports),
        restart_against=sum(r.restart_against for r in reports),
        restart_matches=sum(r.restart_matches for r in reports),
        fhc_for=sum(r.fhc_for for r in reports),
        fhc_against=sum(r.fhc_against for r in reports),
        fhc_matches=sum(r.fhc_matches for r in reports),
        open_first_yes=sum(r.open_first_yes for r in reports),
        open_first_matches=sum(r.open_first_matches for r in reports),
        open_for=sum(r.open_for for r in reports),
        open_against=sum(r.open_against for r in reports),
        width_frames=sum(r.width_frames for r in reports),
        width_sum_m=round(sum(r.width_sum_m for r in reports), 1),
        best_fig_attacks=max(reports,
                             key=lambda r: r.best_fig_goals)
        .best_fig_attacks,
        best_fig_goals=max(r.best_fig_goals for r in reports),
        lead_attacks=sum(r.lead_attacks for r in reports),
        lead_sum_s=round(sum(r.lead_sum_s for r in reports), 1),
        trail_attacks=sum(r.trail_attacks for r in reports),
        trail_sum_s=round(sum(r.trail_sum_s for r in reports), 1),
        pp_shots=sum(r.pp_shots for r in reports),
        pp_goals=sum(r.pp_goals for r in reports),
        sh_conceded=sum(r.sh_conceded for r in reports),
        sh_seconds=round(sum(r.sh_seconds for r in reports), 1),
        xg=round(sum(r.xg for r in reports), 2),
        xg_diff=round(goals - sum(r.xg for r in reports), 2),
        def_shots_against=sum(r.def_shots_against for r in reports),
        def_goals_against=sum(r.def_goals_against for r in reports),
        def_free_shots=sum(r.def_free_shots for r in reports),
        xga_sum=round(sum(r.xga_sum for r in reports), 2),
        transition_turnovers=sum(r.transition_turnovers for r in reports),
        transition_goals_against=sum(r.transition_goals_against for r in reports),
        turnover_total=sum(r.turnover_total for r in reports),
        turnover_front=sum(r.turnover_front for r in reports),
        clutch_goals_for=sum(r.clutch_goals_for for r in reports),
        clutch_goals_against=sum(r.clutch_goals_against for r in reports),
        clutch_matches=sum(r.clutch_matches for r in reports),
        drought_longest_s=max((r.drought_longest_s for r in reports),
                              default=0.0),
        blocks=sum(r.blocks for r in reports),
        slow_attacks_total=sum(r.slow_attacks_total for r in reports),
        slow_attacks_slow=sum(r.slow_attacks_slow for r in reports),
        fh_goals_for=sum(r.fh_goals_for for r in reports),
        fh_goals_against=sum(r.fh_goals_against for r in reports),
        sh_goals_for=sum(r.sh_goals_for for r in reports),
        sh_goals_against=sum(r.sh_goals_against for r in reports),
        shot_speed_n=sum(r.shot_speed_n for r in reports),
        fin_free_shots=sum(r.fin_free_shots for r in reports),
        fin_free_goals=sum(r.fin_free_goals for r in reports),
        fin_cov_shots=sum(r.fin_cov_shots for r in reports),
        fin_cov_goals=sum(r.fin_cov_goals for r in reports),
        side_frames={k: sum(r.side_frames.get(k, 0) for r in reports)
                     for k in ("bal", "közép", "jobb")},
        response_n=sum(r.response_n for r in reports),
        response_sum_s=round(sum(r.response_sum_s for r in reports), 1),
        shot_speed_sum_kmh=round(sum(r.shot_speed_sum_kmh
                                     for r in reports), 1),
        ssf_fh_n=sum(r.ssf_fh_n for r in reports),
        ssf_fh_sum_kmh=round(sum(r.ssf_fh_sum_kmh for r in reports), 1),
        ssf_sh_n=sum(r.ssf_sh_n for r in reports),
        ssf_sh_sum_kmh=round(sum(r.ssf_sh_sum_kmh for r in reports), 1),
        shot_speed_max_kmh=max((r.shot_speed_max_kmh for r in reports),
                               default=0.0),
        possession_pct=round(
            sum(r.possession_pct for r in reports if r.possession_pct)
            / max(1, sum(1 for r in reports if r.possession_pct)), 1),
        defensive_pressure_m=round(
            sum(r.defensive_pressure_m for r in reports if r.defensive_pressure_m)
            / max(1, sum(1 for r in reports if r.defensive_pressure_m)), 2),
        sub_rotations=sum(r.sub_rotations for r in reports),
        sub_trailing=sum(r.sub_trailing for r in reports),
        sub_after_for=sum(r.sub_after_for for r in reports),
        sub_after_against=sum(r.sub_after_against for r in reports),
        defense_switches=[s_ for r in reports for s_ in r.defense_switches],
    )
    # Támadás-hossz szerinti hatékonyság egyesítése (vödrönként).
    for r in reports:
        for k, v in r.duration_eff.items():
            m = rep.duration_eff.setdefault(k, {"attacks": 0, "goals": 0})
            m["attacks"] += v["attacks"]
            m["goals"] += v["goals"]
    # Védőforma elleni hatékonyság egyesítése (formánként összegezve).
    for r in reports:
        for form, v in r.vs_formation.items():
            m = rep.vs_formation.setdefault(form, {"shots": 0, "goals": 0})
            m["shots"] += v["shots"]
            m["goals"] += v["goals"]
    # Passz-hálózat egyesítése: azonos (from,to) párok passzai összeadódnak.
    rep.pass_total = sum(r.pass_total for r in reports)
    merged_pairs: dict = {}
    for r in reports:
        for pr in r.pass_pairs:
            key = (pr["from"], pr["to"])
            merged_pairs[key] = merged_pairs.get(key, 0) + int(pr["passes"])
    rep.pass_pairs = [{"from": a, "to": b, "passes": n}
                      for (a, b), n in sorted(merged_pairs.items(),
                                              key=lambda kv: -kv[1])[:5]]
    # Kapott-gól és kapura tartó lövés zónák egyesítése.
    for r in reports:
        for z, n in r.gk_conceded_zones.items():
            rep.gk_conceded_zones[z] = rep.gk_conceded_zones.get(z, 0) + n
        for z, n in r.gk_on_target_zones.items():
            rep.gk_on_target_zones[z] = rep.gk_on_target_zones.get(z, 0) + n
    # Védekezési zónák egyesítése (kapott lövés/gól/szabad zónánként).
    for r in reports:
        for z, v in r.def_zones.items():
            m = rep.def_zones.setdefault(z, {"shots": 0, "goals": 0, "free": 0})
            for k in ("shots", "goals", "free"):
                m[k] += v.get(k, 0)
    rep.def_zones = dict(sorted(rep.def_zones.items(),
                                key=lambda kv: -kv[1]["shots"]))

    # Támadás-mix egyesítése: a támadás-számmal súlyozott átlag.
    total_atk = sum(max(1, r.attacks) for r in reports)
    mix: dict[str, float] = {}
    for r in reports:
        w = max(1, r.attacks) / total_atk
        for t, pct in r.attack_mix.items():
            mix[t] = mix.get(t, 0.0) + pct * w
    rep.attack_mix = {t: round(v, 1) for t, v in
                      sorted(mix.items(), key=lambda kv: -kv[1])}
    # Támadás-hatékonyság egyesítése: típusonként a darabszámok összege.
    eff: dict[str, dict] = {}
    for r in reports:
        for typ, rec in (r.attack_efficiency or {}).items():
            m = eff.setdefault(typ, {"attacks": 0, "shots": 0, "goals": 0})
            for key in ("attacks", "shots", "goals"):
                m[key] += rec.get(key, 0)
    for rec in eff.values():
        n = max(1, rec["attacks"])
        rec["shot_pct"] = round(100.0 * rec["shots"] / n, 1)
        rec["goal_pct"] = round(100.0 * rec["goals"] / n, 1)
    rep.attack_efficiency = eff
    s, w, k = _coach_keys(rep)
    rep.strengths, rep.weaknesses, rep.keys_to_game = s, w, k
    return rep


def scouting_narrative(rep: ScoutingReport) -> list[dict]:
    """Összefüggő magyar mondatok a jelentés számaiból: hogyan játszik a
    csapat, és hol fogható meg. A felderítő képernyő és a nyomtatott
    jelentés bevezetője — sablon-alapú és determinisztikus (minden mondat
    mögött kiszámolt szám áll).

    Visszatérés: [{"title", "body"}, ...]
    """
    name = rep.team_name or "Az ellenfél"
    out: list[dict] = []

    # Így támadnak: tempó + lerohanás-hajlam.
    parts: list[str] = []
    if rep.avg_attack_duration_s:
        if rep.avg_attack_duration_s < 6.0:
            parts.append("gyorsan, átlag "
                         f"{rep.avg_attack_duration_s:.0f} másodperces támadásokkal jön")
        elif rep.avg_attack_duration_s >= 12.0:
            parts.append("türelmesen építkezik (átlag "
                         f"{rep.avg_attack_duration_s:.0f} s egy támadás)")
        else:
            parts.append("közepes tempóban építkezik (átlag "
                         f"{rep.avg_attack_duration_s:.0f} s egy támadás)")
    if rep.fast_break_pct >= 12.0:
        parts.append(f"a labdás ideje {rep.fast_break_pct:.0f}%-ában gyorsan "
                     "indít — a lerohanás fegyverük")
    elif rep.fast_break_pct > 0:
        parts.append(f"lerohanást ritkán vezet ({rep.fast_break_pct:.0f}%)")
    if parts:
        body = f"{name} " + ", ".join(parts) + "."
        # Támadás-mix: a legjellemzőbb típus kiemelése.
        if rep.attack_mix:
            top_type, top_pct = next(iter(rep.attack_mix.items()))
            if top_pct >= 40.0:
                body += (f" Támadásaik {top_pct:.0f}%-a {top_type} — "
                         "erre készülj elsőként.")
        # Hatékonyság: a legeredményesebb támadás-típusuk külön figyelmeztetés.
        best = None
        for typ, rec in (rep.attack_efficiency or {}).items():
            if rec.get("attacks", 0) >= 3 and (
                    best is None or rec["goal_pct"] > best[1]["goal_pct"]):
                best = (typ, rec)
        if best and best[1]["goal_pct"] >= 50.0:
            body += (f" A legeredményesebb támadásmódjuk a {best[0]} "
                     f"({best[1]['goal_pct']:.0f}% gól) — ezt kell "
                     "elsőként megfognod.")
        # A játékszervezés tengelye: a leggyakoribb passz-kapcsolat.
        if rep.pass_total >= 15 and rep.pass_pairs:
            pr = rep.pass_pairs[0]
            if int(pr["passes"]) >= 5:
                body += (f" A játékuk a {pr['from']}. és {pr['to']}. játékos "
                         f"tengelyén megy ({pr['passes']} passz).")
        # Stílus-jegyek: labdajáratás-tempó, passz-hossz, területi fölény.
        if rep.pt_poss_s >= 120.0 and rep.pt_passes > 0:
            _n_pt = 60.0 * rep.pt_passes / rep.pt_poss_s
            if _n_pt >= 22.0:
                body += (f" A labdát pörgetik ({_n_pt:.0f} passz/perc) — "
                         "a fal folyamatos mozgásra kényszerül.")
            elif _n_pt <= 12.0:
                body += (f" A labdát állva járatják ({_n_pt:.0f} "
                         "passz/perc) — kiszámítható építkezés.")
        if rep.plen_n >= 15 and rep.plen_sum_m > 0:
            _n_lp = 100.0 * rep.plen_long / rep.plen_n
            if _n_lp >= 30.0:
                body += (f" Passzaik {_n_lp:.0f}%-a hosszú — a direkt "
                         "játékuk elfogható.")
        if rep.tilt_frames >= 100:
            _n_ti = 100.0 * rep.tilt_opp / rep.tilt_frames
            if _n_ti >= 65.0:
                body += (f" Birtoklásuk {_n_ti:.0f}%-a az ellenfél "
                         "térfelén zajlik — elöl nyomó csapat.")
            elif _n_ti <= 45.0:
                body += (f" Birtoklásuk a saját térfelükön ragad "
                         f"({_n_ti:.0f}% elöl) — kihozási gondok.")
        # Miből élnek: ha kirajzolódik a fő gól-forrás, elmondjuk.
        ao_n = rep.attack_origins or {}
        tg = sum(v.get("goals", 0) for v in ao_n.values())
        if tg >= 5:
            top_o, top_v = max(ao_n.items(),
                               key=lambda kv: kv[1].get("goals", 0))
            share_o = 100.0 * top_v.get("goals", 0) / tg
            if share_o >= 50.0:
                body += (f" A góljaik fő forrása: {top_o} "
                         f"({share_o:.0f}%).")
        # Melyik fal fogja meg őket (ha van elég formánkénti minta).
        pools = [(f_, v) for f_, v in (rep.vs_formation or {}).items()
                 if v["shots"] >= 4]
        if len(pools) >= 2:
            def _pct(v):
                return 100.0 * v["goals"] / v["shots"]
            worst = min(pools, key=lambda kv: _pct(kv[1]))
            best = max(pools, key=lambda kv: _pct(kv[1]))
            if _pct(best[1]) - _pct(worst[1]) >= 25.0:
                body += (f" A {worst[0]} fal ellen csak "
                         f"{_pct(worst[1]):.0f}%-ot konvertálnak "
                         f"(a {best[0]} ellen {_pct(best[1]):.0f}%-ot).")
        # Hosszú vs rövid támadások hozama (ha van elég minta).
        lr = rep.duration_eff.get("hosszú (35 mp+)")
        sr = rep.duration_eff.get("rövid (<15 mp)")
        if (lr and sr and lr["attacks"] >= 4 and sr["attacks"] >= 4):
            lp = 100.0 * lr["goals"] / lr["attacks"]
            sp_ = 100.0 * sr["goals"] / sr["attacks"]
            if sp_ - lp >= 20.0:
                body += (f" A hosszú támadásaik terméketlenek "
                         f"({lp:.0f}% vs {sp_:.0f}% a rövideknél).")
            elif lp - sp_ >= 20.0:
                body += (f" A türelmes, hosszú támadásaik kifejezetten "
                         f"eredményesek ({lp:.0f}%).")
        # Oldal-súlypont: melyik szárnyra épül a támadásépítés.
        side_total = sum(rep.side_frames.values()) if rep.side_frames else 0
        if side_total >= 250:
            top_side, top_n = max(rep.side_frames.items(),
                                  key=lambda kv: kv[1])
            pct = 100.0 * top_n / side_total
            if top_side != "közép" and pct >= 45.0:
                body += (f" A támadásépítésük súlypontja a {top_side} "
                         f"oldal ({pct:.0f}%).")
        out.append({"title": "Így támadnak", "body": body})

    # Védekezésük: fő forma + váltogatás + a fal térbeli/minőségi jegyei.
    if rep.defense_distribution:
        items = list(rep.defense_distribution.items())
        main, share = items[0]
        body = f"Fő védekezési formájuk a {main} (az idő {share:.0f}%-ában)."
        if len(items) >= 2 and items[1][1] >= 25.0:
            body += (f" Sokat váltanak {items[1][0]}-ra is "
                     f"({items[1][1]:.0f}%) — készülj mindkettőre.")
        elif share >= 75.0:
            body += " Ragaszkodnak hozzá — egy begyakorolt ellenszer sokat ér."
        # Fal-szélesség: tömör (szélek nyitva) vagy széthúzott (közép nyitva).
        if rep.defw_frames >= 100 and rep.defw_sum_m > 0:
            _n_dw = rep.defw_sum_m / rep.defw_frames
            if _n_dw <= 11.0:
                body += (f" A faluk tömör (átlag {_n_dw:.0f} m széles) — "
                         "a szélek nyitva.")
            elif _n_dw >= 15.0:
                body += (f" A faluk széthúzott (átlag {_n_dw:.0f} m) — "
                         "a közép nyílik.")
        # Engedett lövésminőség: ziccert engedő vagy kiszorító fal.
        if rep.def_shots_against >= 8 and rep.xga_sum > 0:
            _n_xga = rep.xga_sum / rep.def_shots_against
            if _n_xga >= 0.38:
                body += (f" Ziccereket engednek (átlag {_n_xga:.2f} "
                         "xG/lövés) — türelemmel nagy helyzetig lehet jutni.")
            elif _n_xga <= 0.22:
                body += (f" Kiszorító fal (átlag {_n_xga:.2f} xG/lövés) — "
                         "rossz lövésekbe kényszerítenek.")
        # Szerzés-magasság: elöl zavaró (letámadó) vagy passzív elöl-játék.
        if rep.steal_n >= 4:
            _n_st = 100.0 * rep.steal_high / rep.steal_n
            if _n_st >= 35.0:
                body += (f" Szerzéseik {_n_st:.0f}%-a elöl, letámadásból "
                         "jön — a kihozatalodat készítsd elő.")
        out.append({"title": "Védekezésük", "body": body})

    # Félidő-minta: a felismert szünetű meccsek félidőnkénti mérlegéből.
    fh_d = rep.fh_goals_for - rep.fh_goals_against
    sh_d = rep.sh_goals_for - rep.sh_goals_against
    if (rep.fh_goals_for + rep.fh_goals_against
            + rep.sh_goals_for + rep.sh_goals_against) >= 8:
        if sh_d - fh_d >= 3:
            out.append({"title": "Félidő-minta", "body": (
                f"A második félidőben rendre feljavulnak: a félidő-mérlegük "
                f"{fh_d:+d}-ról {sh_d:+d}-ra vált — az első félidőben kell "
                "előnyt építeni ellenük.")})
        elif fh_d - sh_d >= 3:
            out.append({"title": "Félidő-minta", "body": (
                f"A második félidőben rendre elfogynak: a félidő-mérlegük "
                f"{fh_d:+d}-ról {sh_d:+d}-ra romlik — a meccs második fele "
                "ellenük dolgozik.")})

    # Végjáték: a szoros hajrák halmozott mérlege (ha volt ilyen hajrá).
    if rep.clutch_matches >= 1:
        diff = rep.clutch_goals_for - rep.clutch_goals_against
        n = rep.clutch_matches
        base = (f"{n} szoros hajrát" if n > 1 else "Egy szoros hajrát"
                ) + " látott a felderítés"
        if diff >= 2:
            body = (f"{base}: a mérlegük +{diff} gól — a végjátékban "
                    "hidegvérűek, ne hagyd a döntést a hajrára.")
        elif diff <= -2:
            body = (f"{base}: a mérlegük {diff} gól — a végjátékban "
                    "rendre alulmaradnak, a szoros meccs neked kedvez.")
        else:
            body = (f"{base}: kiegyenlített hajrá-mérleg ({diff:+d} gól).")
        out.append({"title": "Végjáték", "body": body})

    # Befejezésük: hatékonyság + kedvenc zóna. Több meccsnél az összegek
    # félrevezetők lennének jelzés nélkül — kiírjuk a meccs-számot.
    if rep.shots:
        prefix = f"{rep.matches} meccs alatt " if rep.matches > 1 else ""
        body = (f"{prefix}{rep.shots} lövésükből {rep.goals} gól "
                f"({rep.shot_efficiency_pct:.0f}%-os gólarány).")
        total = sum(z["shots"] for z in rep.shot_zones.values())
        if total:
            zone, rec = next(iter(rep.shot_zones.items()))
            body += (f" Legtöbbet innen lőnek: {zone} "
                     f"(a lövéseik {100.0 * rec['shots'] / total:.0f}%-a).")
        if rep.turnovers:
            body += f" Labdaeladásuk: {rep.turnovers}."
        # Gól-eloszlás posztok szerint (ha van becsült poszt-adat).
        pg = rep.post_goals or {}
        pg_total = sum(pg.values())
        if pg_total >= 6:
            parts_pg = ", ".join(
                f"{p_} {100.0 * n / pg_total:.0f}%"
                for p_, n in sorted(pg.items(), key=lambda kv: -kv[1]))
            body += f" Gól-eloszlás posztok szerint: {parts_pg}."
        # Lövés-választás: válogatósak vagy távolról is vállalkoznak.
        if rep.shots >= 10 and rep.xg > 0:
            avg_xg = rep.xg / rep.shots
            if avg_xg <= 0.10:
                body += (f" Sok kis esélyű lövést vállalnak (átlag "
                         f"{avg_xg:.2f} xG/lövés).")
            elif avg_xg >= 0.18:
                body += (f" Válogatósak: csak jó helyzetből lőnek "
                         f"(átlag {avg_xg:.2f} xG/lövés).")
        out.append({"title": "Befejezésük", "body": body})

    # Kapusuk: védés-hatékonyság, csak érdemi mintánál (>=4 kapura tartó).
    if rep.gk_on_target >= 4:
        pct = 100.0 * rep.gk_saves / rep.gk_on_target
        if pct >= 40.0:
            body = (f"Kapusuk erős: {rep.gk_on_target} kapura tartó lövésből "
                    f"{rep.gk_saves} védés ({pct:.0f}%) — a tiszta helyzetig "
                    "érdemes türelmesen játszani.")
        elif pct <= 20.0:
            body = (f"Kapusuk bizonytalan: {rep.gk_on_target} kapura tartó "
                    f"lövésből csak {rep.gk_saves} védés ({pct:.0f}%) — "
                    "a kapura lövés kifizetődő.")
        else:
            body = (f"Kapusuk átlagos: {rep.gk_saves} védés "
                    f"{rep.gk_on_target} kapura tartó lövésből ({pct:.0f}%).")
        if rep.gk_big_saves >= 2:
            body += (f" Ziccert is fog: {rep.gk_big_saves} nagy helyzetet "
                     "(xG ≥ 0,5) hárított.")
        if rep.gk_xg_saved / max(1, rep.matches) >= 1.0:
            body += (f" A védései nehézség-súlyozva is erősek: "
                     f"{rep.gk_xg_saved / rep.matches:.1f} hárított "
                     "xG meccsenként.")
        out.append({"title": "Kapusuk", "body": body})

    # Fő lövőjük szokása: honnan dolgozik (ha kirajzolódik a minta).
    habit = _top_shooter_habit(rep)
    if habit:
        pid, z, n, total = habit
        out.append({
            "title": "Fő lövőjük",
            "body": (f"A(z) {pid}. játékos {total} lövéséből {n} "
                     f"({100.0 * n / total:.0f}%) ugyanonnan jött: {z} — "
                     "a fal és a kapus erre a helyzetre készülhet."),
        })

    # Felállásuk: a becsült posztok egy mondatban.
    if rep.positions:
        by_post: dict = {}
        for tid, poszt in sorted(rep.positions.items()):
            by_post.setdefault(poszt, []).append(str(tid))
        order = ["irányító", "átlövő", "beálló", "szélső"]
        parts_p = [f"{p_}: {', '.join(by_post[p_])}."
                   for p_ in order if p_ in by_post]
        if parts_p:
            out.append({
                "title": "Felállásuk",
                "body": ("Becsült posztok a mozgásképből — "
                         + " ".join(parts_p)),
            })

    # Fegyelmük: kiállítás-hajlam + a kiülők és kiharcolók nevei.
    if rep.suspensions >= 2 or (rep.susp_players
                                and rep.susp_players[0]["suspensions"] >= 2):
        per_match = rep.suspensions / max(1, rep.matches)
        body = (f"Fegyelmezetlenek: {rep.suspensions} kiállítás "
                f"{rep.matches} meccsen (átlag {per_match:.1f}/meccs).")
        if rep.susp_players:
            who = ", ".join(
                f"{e['player_id']}. ({e['suspensions']}×)"
                for e in rep.susp_players[:3])
            body += f" A kiülőik: {who}."
        if rep.susp_earners and rep.susp_earners[0]["earned"] >= 2:
            body += (f" A másik irányban a(z) "
                     f"{rep.susp_earners[0]['player_id']}. játékosuk "
                     f"harcolja ki a 2 perceket "
                     f"({rep.susp_earners[0]['earned']}×) — vele "
                     "szemben kéz nélkül védekezzetek.")
        body += (" A nyomás alatti védekezésük sebezhető: a bátor "
                 "betörés náluk emberelőnyt érhet.")
        out.append({"title": "Fegyelmük", "body": body})

    # Kulcsjátékos: akinél a legtöbb labda megfordul — a kapust átugorjuk
    # (nála kidobásoknál jár a labda, nem ő szervezi a támadást).
    kp = next((k for k in rep.key_players if k.get("role") != "kapus"), None)
    if kp is not None:
        if kp.get("possession_frames", 0) > 0:
            out.append({
                "title": "Kulcsjátékos",
                "body": (f"A legtöbb labda a(z) {kp['track_id']}. játékosnál "
                         f"fordult meg ({kp.get('role', 'mezőnyjátékos')}) — az "
                         "ő megfogása a támadásaik kulcsa."),
            })

    if not out:
        out.append({"title": "Kevés adat",
                    "body": "Ehhez a csapathoz még kevés a minta — több "
                            "meccs felderítése pontosít."})
    return out


def report_to_dict(rep: ScoutingReport) -> dict:
    """A jelentés JSON-barát szótárrá alakítása (az API-hoz) — a szöveges
    narratívával kiegészítve."""
    d = asdict(rep)
    d["narrative"] = scouting_narrative(rep)
    return d


# ---- Fejlődés-követés (trend) ------------------------------------------------

# A trendben követett mutatók: (mező, magyar címke, egység, jobb-e ha nő; None =
# semleges irány, per_match: a darabszámot meccsenkénti átlagra normáljuk).
_TREND_METRICS = [
    ("attack_share_pct", "Szervezett támadás", "%", True, False),
    ("fast_break_pct", "Gyors indítás", "%", True, False),
    ("avg_attack_duration_s", "Átl. támadáshossz", " s", None, False),
    ("shot_efficiency_pct", "Gólarány", "%", True, False),
    ("shots", "Lövés / meccs", "", True, True),
    ("goals", "Gól / meccs", "", True, True),
    ("turnovers", "Labdaeladás / meccs", "", False, True),
    # Új rétegek: birtoklás (több = jobb), védekezési nyomás (kevesebb
    # méter = szorosabb = jobb), elöl vesztett labdák (kevesebb = jobb).
    ("possession_pct", "Labdabirtoklás", "%", True, False),
    ("defensive_pressure_m", "Védekezési nyomás", " m", False, False),
    ("turnover_front", "Elöl vesztett labda / meccs", "", False, True),
    ("blocks", "Blokk / meccs", "", True, True),
    # Kapus-rétegek: fogott ziccerek és gyors indítások (több = jobb).
    ("gk_big_saves", "Bravúr-védés / meccs", "", True, True),
    ("gk_outlet_fast", "Gyors indítás védés után / meccs", "", True, True),
    ("gk_xg_saved", "Hárított xG / meccs", "", True, True),
    ("gk_xg_prevented", "Megmentett gól (GSAx) / meccs", "", True, True),
    # Fegyelem: kiállítás meccsenként (kevesebb = jobb; a 0 valós érték).
    ("suspensions", "Kiállítás / meccs", "", False, True),
    # Beálló-terhelés: beállós támadás meccsenként (irány-semleges).
    ("pivot_attacks", "Beállós támadás / meccs", "", None, True),
    # Második roham: kimaradt lövés után visszaszerzett lepattanó
    # meccsenként (több = agresszívabb harc a lepattanóért = jobb).
    ("sc_second", "Második roham / meccs", "", True, True),
    # Kezdés: milyen arányban szerzik a meccs első gólját (jó kezdés =
    # gyorsan a saját tempójukat kényszerítik rá az ellenfélre = jobb).
    ("open_first_yes", "Nyitógól-arány", "", True, True),
]


def trend_report(older: ScoutingReport, newer: ScoutingReport) -> dict:
    """Két időszak jelentésének összevetése — fejlődés-követés edzői nyelven.

    A darabszám-mutatókat meccsenkénti átlagra normáljuk (különben a több meccs
    "több lövésnek" látszana). Minden mutatóhoz: régi/új érték, változás, és
    hogy ez javulás-e ("better": True/False/None). A "summary" magyar mondatok
    a jelentős (>=10%-os) változásokról.
    """
    metrics = []
    summary = []
    # Az új, opcionális rétegek 0-ja "nincs mérés"-t jelent — ilyenkor a
    # mutatót kihagyjuk, hogy ne látsszon hamis javulásnak/romlásnak.
    optional = {"possession_pct", "defensive_pressure_m",
                "gk_big_saves", "gk_outlet_fast", "gk_xg_saved",
                "gk_xg_prevented", "pivot_attacks", "sc_second",
                "open_first_yes"}
    for field_name, label, unit, up_is_better, per_match in _TREND_METRICS:
        a = float(getattr(older, field_name))
        b = float(getattr(newer, field_name))
        if field_name in optional and (a == 0.0 or b == 0.0):
            continue
        if per_match:
            a = a / max(1, older.matches)
            b = b / max(1, newer.matches)
        delta = b - a
        better = None
        if up_is_better is not None and abs(delta) > 1e-9:
            better = (delta > 0) == up_is_better
        metrics.append({
            "metric": field_name, "label": label, "unit": unit,
            "older": round(a, 2), "newer": round(b, 2),
            "delta": round(delta, 2), "better": better,
        })
        # Jelentős változás → magyar mondat (a semleges irányút nem minősítjük).
        base = max(abs(a), 1e-9)
        if better is not None and abs(delta) / base >= 0.10:
            word = "Javult" if better else "Romlott"
            summary.append(f"{word}: {label.lower()} {a:.1f}{unit} → {b:.1f}{unit}.")

    if not summary:
        summary.append("Nincs jelentős változás a két időszak között.")
    return {
        "team_name": newer.team_name,
        "older_matches": older.matches,
        "newer_matches": newer.matches,
        "metrics": metrics,
        "summary": summary,
    }
