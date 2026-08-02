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
    # Játékos-mérlegük: [{"player_id", "frames", "for", "against"}] —
    # a pályán töltött kockák és a rájuk eső gólok; darabszámok,
    # meccsek közt összegződnek (a percre vetített mérleg ebből
    # pontosan visszaszámolható).
    player_plus_minus: list = field(default_factory=list)
    pm_fps: float = 25.0
    # Célba vett védőik: [{"player_id", "jersey", "shots", "goals"}] —
    # védőnként a rá eső kapott lövések és gólok darabszáma, + a
    # csapat-összegek; darabszámok, meccsek közt pontosan összegződnek
    # (a gólarány ebből visszaszámolható).
    targeted_defenders: list = field(default_factory=list)
    tdf_shots: int = 0
    tdf_goals: int = 0
    # Védekezés-váltásuk: {forma: védekezett támadás} + a mért
    # támadások, a szomszédos támadás-párok és a köztük történt
    # váltások száma — darabszámok, meccsek közt pontosan
    # összegződnek (váltás-arány = fsw_switches / fsw_pairs).
    # Labdatartásuk: [{"player_id", "jersey", "holds", "frames"}] —
    # játékosonként a labdás szakaszok száma és a bennük töltött
    # kockák; darabszámok, meccsek közt pontosan összegződnek (az
    # átlagos tartás = frames / holds / fps).
    hold_players: list = field(default_factory=list)
    hold_fps: float = 25.0
    # Lövőerő-esésük: félidőnként a mért lövések száma + a
    # sebesség-összeg (km/h) — darabszámok és összegek, meccsek közt
    # pontosan összegződnek (félidő-átlag = összeg / darab).
    # Csere-blokkjaik: a cserehullámok száma, a bennük mozgatott
    # játékosok összege és a 2+ fős hullámok száma — darabszámok,
    # meccsek közt pontosan összegződnek (blokk-arány = block / waves,
    # átlagos hullám-méret = players / waves).
    # Páros-mérlegük: [{"players": [id, id], "frames", "for",
    # "against"}] — az együtt töltött kockák és a rájuk eső gólok;
    # darabszámok, meccsek közt pontosan összegződnek (a percre
    # vetített mérleg ebből visszaszámolható).
    # Időkérés-időzítésük: a felismert időkéréseik, az előttük álló
    # kapott gólok összege és a hajrában (utolsó 10 perc) kértek
    # száma — darabszámok, meccsek közt pontosan összegződnek (átlag =
    # sum_before / timeouts).
    # Kapus-bevonásuk: a mért birtoklási szakaszok és azok száma,
    # amelyekben a kapus is birtokolt — darabszámok, meccsek közt
    # pontosan összegződnek (arány = kiv_with / kiv_spells).
    kiv_spells: int = 0
    kiv_with: int = 0
    # Keresztjátékuk: mért támadásaik és a hátsó sor oldalcseréi —
    # darabszámok, meccsek közt pontosan összegződnek.
    crx_attacks: int = 0
    crx_crosses: int = 0
    # Szélső-futtatásuk: szélső-átvételeik és a mozgásból jövők —
    # darabszámok, meccsek közt pontosan összegződnek.
    wsv_receptions: int = 0
    wsv_running: int = 0
    psv_receptions: int = 0
    psv_running: int = 0
    fbw_breaks: int = 0
    fbw_second: int = 0
    fbh_breaks: int = 0
    fbh_ahead: int = 0
    bsh_blocked: int = 0
    bsh_shooters: dict = field(default_factory=dict)
    abr_assists: int = 0
    abr_roles: dict = field(default_factory=dict)
    sur_suspensions: int = 0
    sur_roles: dict = field(default_factory=dict)
    bbr_blocked: int = 0
    bbr_roles: dict = field(default_factory=dict)
    otr_outlets: int = 0
    otr_roles: dict = field(default_factory=dict)
    brf_fh_attacks: int = 0
    brf_fh_breaks: int = 0
    brf_sh_attacks: int = 0
    brf_sh_breaks: int = 0
    wsd_shots: int = 0
    wsd_depth_sum_m: float = 0.0
    dtp_frames: int = 0
    dtp_doublers: dict = field(default_factory=dict)
    btn_goals: int = 0
    btn_free: int = 0
    btn_defenders: dict = field(default_factory=dict)
    upa_assisted: int = 0
    upa_unpressured: int = 0
    gpn_gap_s: float = 0.0
    gpn_gaps: int = 0
    gpn_conceded: int = 0
    crg_goals: int = 0
    crg_open: int = 0
    ctm_goals: int = 0
    ctm_passes_sum: int = 0
    cgm_goals: int = 0
    cgm_running: int = 0
    wfk_goals: int = 0
    wfk_fooled: int = 0
    rdk_saves: int = 0
    rdk_read: int = 0
    dbp_doubled_frames: int = 0
    dbp_conceded_after: int = 0
    sop_goals: int = 0
    sop_behind: int = 0
    pmb_misses: int = 0
    pmb_punished: int = 0
    olp_lost: int = 0
    olp_punished: int = 0
    sac_slow: int = 0
    sac_scored: int = 0
    obt_out: int = 0
    sps_tr: int = 0
    sps_lead: int = 0
    sps_level: int = 0
    svs_tr: int = 0
    svs_lead: int = 0
    svs_level: int = 0
    bks_tr_attacks: int = 0
    bks_tr_breaks: int = 0
    bks_rest_attacks: int = 0
    bks_rest_breaks: int = 0
    ens_tr: int = 0
    ens_lead: int = 0
    ens_level: int = 0
    gst_on_target: int = 0
    gst_streaks: int = 0
    asf_fh_goals: int = 0
    asf_fh_assisted: int = 0
    asf_sh_goals: int = 0
    asf_sh_assisted: int = 0
    scf_fh_misses: int = 0
    scf_fh_won: int = 0
    scf_sh_misses: int = 0
    scf_sh_won: int = 0
    ams_fh_attacks: int = 0
    ams_fh_break: int = 0
    ams_fh_quick: int = 0
    ams_sh_attacks: int = 0
    ams_sh_break: int = 0
    ams_sh_quick: int = 0
    pds_lead_passes: int = 0
    pds_lead_back: int = 0
    pds_rest_passes: int = 0
    pds_rest_back: int = 0
    gka_assists: int = 0
    pls_tr_passes: int = 0
    pls_tr_long: int = 0
    pls_rest_passes: int = 0
    pls_rest_long: int = 0
    dfs_fh_attacks: int = 0
    dfs_sh_attacks: int = 0
    dfs_fh_labels: dict = field(default_factory=dict)
    dfs_sh_labels: dict = field(default_factory=dict)
    sds_fh_frames: int = 0
    sds_sh_frames: int = 0
    sds_fh_counts: dict = field(default_factory=dict)
    sds_sh_counts: dict = field(default_factory=dict)
    tbs_tr_attacks: int = 0
    tbs_tr_tos: int = 0
    tbs_rest_attacks: int = 0
    tbs_rest_tos: int = 0
    dbs_lead_shots: int = 0
    dbs_lead_xg: float = 0.0
    dbs_rest_shots: int = 0
    dbs_rest_xg: float = 0.0
    sbs_lead_subs: int = 0
    sbs_rest_subs: int = 0
    sbs_lead_s: float = 0.0
    sbs_rest_s: float = 0.0
    ops_lead_outlets: int = 0
    ops_lead_sum_s: float = 0.0
    ops_rest_outlets: int = 0
    ops_rest_sum_s: float = 0.0
    # Csere-lyukaik: csere közbeni öt fős játék másodpercei — összeg,
    # meccsek közt pontosan összegződik.
    sbg_gap_s: float = 0.0
    # Gólpassz-hosszuk: gólpasszos góljaik és a hosszú (8+ m)
    # előkészítésből esők — darabszámok, meccsek közt pontosan
    # összegződnek.
    asr_assisted: int = 0
    asr_long: int = 0
    # Kapus-kipattanójuk: mért védéseik és a kapusnál maradó labdák —
    # darabszámok, meccsek közt pontosan összegződnek.
    grc_saves: int = 0
    grc_caught: int = 0
    # Kivárás-csapdájuk: hosszú felállt támadásaik és a lövés nélkül
    # elhalók — darabszámok, meccsek közt pontosan összegződnek.
    lao_n: int = 0
    lao_died: int = 0
    # Felfutási létszámuk: támadó-kockák és a fent lévő mezőny-
    # játékosok összege — darabszám/összeg, meccsek közt pontosan
    # összegződnek (átlag = ahc_sum_up / ahc_frames).
    ahc_frames: int = 0
    ahc_sum_up: int = 0
    # Blokk-lepattanóik: mért blokkjaik és a belőlük visszaszerzett
    # labdák — darabszámok, meccsek közt pontosan összegződnek.
    brc_blocks: int = 0
    brc_recovered: int = 0
    # Ziccer-befejezőik: játékosonként a nagy helyzetek és góljaik
    # [{"player_id", "chances", "goals"}] — darabszámok, meccsek közt
    # játékos szerint összegződnek.
    bcf_players: list = field(default_factory=list)
    # Hetes utáni perceik: adott heteseik és az utánuk kapott további
    # gólok — darabszámok, meccsek közt pontosan összegződnek.
    psl_sevens: int = 0
    psl_extra: int = 0
    # Labda-forgatásuk: balra és jobbra tartó oldalpasszaik száma —
    # darabszámok, meccsek közt pontosan összegződnek.
    cir_left: int = 0
    cir_right: int = 0
    # Elzárás-párosaik: (elzáró, lövő) kettősök közös lövés-számai
    # [{"setter_id", "shooter_id", "shots"}] — darabszámok, meccsek
    # közt páros szerint összegződnek.
    scp_pairs: list = field(default_factory=list)
    # Szélső-kifutásuk: az ellenük leadott szélső-lövések száma és a
    # legközelebbi védő távolság-összege — darabszám/összeg, meccsek
    # közt pontosan összegződnek (átlag = wco_sum_m / wco_shots).
    wco_shots: int = 0
    wco_sum_m: float = 0.0
    # Csend-törőik: gólcsend-törések [{"player_id", "breaks"}] —
    # darabszámok, meccsek közt játékos szerint összegződnek.
    drb_players: list = field(default_factory=list)
    # Forró kezük: gólsorozataik [{"player_id", "length"}] — meccsek
    # közt listaként összegződnek (játékos szerint darab + leghosszabb).
    hh_streaks: list = field(default_factory=list)
    # Kapus-hidegedésük: hosszú csend utáni és ritmusban kapott
    # kapura tartó lövések + védések — darabszámok, meccsek közt
    # pontosan összegződnek.
    gcs_cold_faced: int = 0
    gcs_cold_saves: int = 0
    gcs_warm_faced: int = 0
    gcs_warm_saves: int = 0
    # Fal-magasság elleni játékuk: felfutó és mély fal ellen vívott
    # támadásaik + góljaik — darabszámok, meccsek közt pontosan
    # összegződnek.
    avw_high_attacks: int = 0
    avw_high_goals: int = 0
    avw_deep_attacks: int = 0
    avw_deep_goals: int = 0
    # Kontra-forrásaik: lerohanásaik forrás szerinti darabszámai
    # ({"védés"/"kihagyott lövés"/"labdaszerzés": darab}) — meccsek
    # közt kulcs szerint összegződnek.
    bsrc_sources: dict = field(default_factory=dict)
    # Kapus-gól veszélyük: a kapusuk kapura dobásai és góljai —
    # darabszámok, meccsek közt pontosan összegződnek.
    gkg_attempts: int = 0
    gkg_goals: int = 0
    # Hosszú állásaik utáni játék: mért hosszú megszakítások és az
    # utánuk lévő két perc gólmérlege — darabszámok, meccsek közt
    # pontosan összegződnek.
    lbr_breaks: int = 0
    lbr_for: int = 0
    lbr_against: int = 0
    # Hajrá-labdabirtoklásuk: játékosonkénti hajrá-labdás kockák
    # [{"player_id", "jersey", "frames"}] + az összes mért hajrá-kocka
    # — darabszámok, meccsek közt pontosan összegződnek.
    cbh_frames: int = 0
    cbh_players: list = field(default_factory=list)
    # Negyedóra-profiljuk: negyedóránkénti lőtt és kapott gólok
    # ({"1".."4": gól}) + a mért percek — darabszámok/összegek, meccsek
    # közt pontosan összegződnek (kulcs szerint összeadva).
    qp_for: dict = field(default_factory=dict)
    qp_against: dict = field(default_factory=dict)
    qp_min: float = 0.0
    # Beálló-őrük: védőnként a beálló-őrzés kockái [{"player_id",
    # "jersey", "frames"}] + az összes mért őrzés-kocka — darabszámok,
    # meccsek közt pontosan összegződnek (játékos szerint).
    pvg_frames: int = 0
    pvg_guards: list = field(default_factory=list)
    # Időkérés-csomagjuk: mért időkéréseik és ebből a cserével járók
    # — darabszámok, meccsek közt pontosan összegződnek.
    tsc_timeouts: int = 0
    tsc_with_subs: int = 0
    # Lövés-választásuk állás szerint: hátrányban és egyébként leadott
    # lövések + helyzetérték-összegek — darabszám/összeg, meccsek közt
    # pontosan összegződnek (átlag = sqs_*_sum_xg / sqs_*_shots).
    sqs_trail_shots: int = 0
    sqs_trail_sum_xg: float = 0.0
    sqs_other_shots: int = 0
    sqs_other_sum_xg: float = 0.0
    # Kapusuk állás szerint: hátrányban és egyébként kapura kapott
    # lövések + védések — darabszámok, meccsek közt pontosan
    # összegződnek (arányok külön-külön).
    gks_trail_faced: int = 0
    gks_trail_saves: int = 0
    gks_other_faced: int = 0
    gks_other_saves: int = 0
    # Szorult játékuk: hátrányban és egyébként mért támadó-kockák és
    # szélesség-összegek — darabszám/összeg, meccsek közt pontosan
    # összegződnek (átlag = wbs_*_sum_m / wbs_*_frames).
    wbs_trail_frames: int = 0
    wbs_trail_sum_m: float = 0.0
    wbs_other_frames: int = 0
    wbs_other_sum_m: float = 0.0
    # Visszaállásuk: a mért kiállítás-lejáratok és az utánuk lévő perc
    # gólmérlege — darabszámok, meccsek közt pontosan összegződnek.
    ppp_returns: int = 0
    ppp_for: int = 0
    ppp_against: int = 0
    # Poszt-hibáik: labdaeladásaik poszt szerinti darabszámai
    # ({poszt: eladások}) — darabszámok, meccsek közt pontosan
    # összegződnek (kulcs szerint összeadva).
    tbr_roles: dict = field(default_factory=dict)
    # Futás-mérlegük: a mezőnyjátékosaik mért táv-összege, az
    # ellenfeleiké, és a mért percek — összegek, meccsek közt pontosan
    # összegződnek (fajlagos = dbt_m / dbt_min).
    dbt_m: float = 0.0
    dbt_opp_m: float = 0.0
    dbt_min: float = 0.0
    # Egyirányú játékosaik: játékosonként a fázis-besorolt kockák és
    # ebből a védekezésben töltöttek [{"player_id", "jersey",
    # "frames", "def_frames"}] — darabszámok, meccsek közt pontosan
    # összegződnek (játékos szerint).
    phs_players: list = field(default_factory=list)
    # Sprint-veszélyük: játékosonként a sprintek száma és a sprint-táv
    # [{"player_id", "jersey", "sprints", "sprint_m"}] — darabszám/
    # összeg, meccsek közt pontosan összegződnek (játékos szerint).
    spt_players: list = field(default_factory=list)
    # Hetesre cserélt kapusuk: az ellenük ítélt hetesek és ebből a
    # frissen beállt kapusra jutók száma — darabszámok, meccsek közt
    # pontosan összegződnek.
    svk_sevens: int = 0
    svk_swaps: int = 0
    # Kilépő védőjük: védőnként a felállt védekezésben mért kockák és
    # a kaputávolság-összeg [{"player_id", "jersey", "frames",
    # "depth_sum_m"}] — darabszám/összeg, meccsek közt pontosan
    # összegződnek (átlag = depth_sum_m / frames).
    adv_players: list = field(default_factory=list)
    # Középkezdés-átvevőik: a mért újraindításaik száma és az átvevők
    # [{"player_id", "jersey", "takes"}] — darabszámok, meccsek közt
    # pontosan összegződnek (játékos szerint összeadva).
    rst_restarts: int = 0
    rst_players: list = field(default_factory=list)
    # Váltópárjaik: az egy-ki-egy-be cseréik száma és a párosok
    # [{"out_id", "in_id", "count"}] — darabszámok, meccsek közt
    # pontosan összegződnek (a párosok kulcs szerint összeadva).
    swp_swaps: int = 0
    swp_pairs: list = field(default_factory=list)
    # Visszahozott támadásaik: a betörés-epizódjaik és ebből a lövés
    # nélküli visszahozások száma — darabszámok, meccsek közt pontosan
    # összegződnek (arány = pb_pullbacks / pb_entries).
    pb_entries: int = 0
    pb_pullbacks: int = 0
    # Szerzés utáni indításuk: a mért szerzéseik és ebből az azonnal
    # előre vitt labdák száma — darabszámok, meccsek közt pontosan
    # összegződnek (arány = stl_fwd / stl_steals).
    stl_steals: int = 0
    stl_fwd: int = 0
    # Hetes-fáradásuk: az adott heteseik száma félidőnként —
    # darabszámok, meccsek közt pontosan összegződnek.
    s7f_fh: int = 0
    s7f_sh: int = 0
    # Fal-fáradásuk: félidőnként a rájuk jövő lövések száma és a
    # helyzet-értékük összege — darabszám/összeg, meccsek közt
    # pontosan összegződnek (átlag = wf_*_sum_xga / wf_*_shots).
    wf_fh_shots: int = 0
    wf_fh_sum_xga: float = 0.0
    wf_sh_shots: int = 0
    wf_sh_sum_xga: float = 0.0
    # Pad-góljaik: a lövőhöz köthető góljaik és ebből a padról
    # beállók góljai — darabszámok, meccsek közt pontosan összegződnek
    # (arány = ben_bench / ben_goals).
    ben_goals: int = 0
    ben_bench: int = 0
    # Labdaszerzés-típusuk: a szerzéseik és ebből a röptében elfogott
    # passzok száma — darabszámok, meccsek közt pontosan összegződnek
    # (arány = stt_int / stt_steals).
    stt_steals: int = 0
    stt_int: int = 0
    # Kapott helyzeteik minősége: a rájuk jövő lövések száma és a
    # helyzet-értékük összege — darabszám/összeg, meccsek közt
    # pontosan összegződnek (átlag = ccq_sum_xga / ccq_shots).
    ccq_shots: int = 0
    ccq_sum_xga: float = 0.0
    # Félidő-zárásuk: a félidők utolsó percében indult támadásaik és
    # a gólig jutók száma — darabszámok, meccsek közt pontosan
    # összegződnek (arány = clo_goals / clo_attacks).
    clo_attacks: int = 0
    clo_goals: int = 0
    # Lerohanás-hatékonyságuk: a mért lerohanásaik száma és a gólig
    # jutók száma — darabszámok, meccsek közt pontosan összegződnek
    # (arány = fbc_goals / fbc_breaks).
    fbc_breaks: int = 0
    fbc_goals: int = 0
    # Félidő-nyitásuk: a félidők első 5 percében szerzett és kapott
    # góljaik — darabszámok, meccsek közt pontosan összegződnek
    # (mérleg = ho_for - ho_against).
    ho_for: int = 0
    ho_against: int = 0
    # Időkérés utáni védekezésük: a mért időkéréseik száma és azok
    # száma, amelyek után az ellenfél első rohamából gól esett —
    # darabszámok, meccsek közt pontosan összegződnek (arány =
    # tfd_conceded / tfd_timeouts).
    tfd_timeouts: int = 0
    tfd_conceded: int = 0
    # Gól utáni letámadásuk: a saját góljuk utáni ablakban, illetve
    # azon kívül mért védekező kockák száma és a fal-magasságok
    # összege — darabszám/összeg, meccsek közt pontosan összegződnek
    # (átlagok = pag_*_sum_m / pag_*_frames).
    pag_after_frames: int = 0
    pag_after_sum_m: float = 0.0
    pag_base_frames: int = 0
    pag_base_sum_m: float = 0.0
    # Felhozatal-idejük: a mért felhozatalok száma és a térfél-
    # átlépésig eltelt másodpercek összege — darabszám/összeg, meccsek
    # közt pontosan összegződnek (átlag = but_sum_s / but_cases).
    but_cases: int = 0
    but_sum_s: float = 0.0
    # Fedezetten lövőik: [{"player_id", "jersey", "shots",
    # "covered"}] — ki lő nyomás alatt is; darabszámok, meccsek közt
    # pontosan összegződnek.
    covered_shooters: list = field(default_factory=list)
    # Pressz-érzékeny játékosaik: [{"player_id", "jersey",
    # "press_events", "press_to"}] — ki veszíti el a labdát
    # szorításban; darabszámok, meccsek közt pontosan összegződnek.
    pressure_players: list = field(default_factory=list)
    # Elöl szerző védőik: [{"player_id", "jersey", "steals", "high"}]
    # — ki szed labdát a támadó térfélen; darabszámok, meccsek közt
    # pontosan összegződnek.
    high_stealers: list = field(default_factory=list)
    # Pontatlan lövőik: [{"player_id", "jersey", "shots",
    # "off_target"}] — kinek a lövései kerülik el a kaput;
    # darabszámok, meccsek közt pontosan összegződnek.
    wasteful_shooters: list = field(default_factory=list)
    # Kezdő embereik: [{"player_id", "jersey", "frames"}] — az első öt
    # percben a pályán töltött kockák; darabszámok, meccsek közt
    # pontosan összegződnek (aki több meccset kezd, előre kerül).
    opening_players: list = field(default_factory=list)
    # Hetes-kiharcolásuk poszt szerint: {poszt: darab} — melyik
    # posztról rántják le őket; darabszámok, meccsek közt pontosan
    # összegződnek.
    seven_earner_roles: dict = field(default_factory=dict)
    # Időkérés utáni első támadásuk: a mért időkérések és az utánuk
    # született góljaik — darabszámok, meccsek közt pontosan
    # összegződnek (arány = tfa_goals / tfa_timeouts).
    tfa_timeouts: int = 0
    tfa_goals: int = 0
    # Kockázatos passzolóik: [{"player_id", "jersey", "tries",
    # "turnovers"}] — kinek a hosszú labdái foghatók el; darabszámok,
    # meccsek közt pontosan összegződnek.
    risky_passers: list = field(default_factory=list)
    # Elzáróik: [{"player_id", "jersey", "screens"}] — ki áll elzárásba
    # a lövőik előtt; darabszámok, meccsek közt pontosan összegződnek.
    screen_setters: list = field(default_factory=list)
    # Kapusuk meccskezdése: az első tíz percben és utána a kapura tartó
    # lövések és a fogások — darabszámok, meccsek közt pontosan
    # összegződnek (védés-arány = saves / faced).
    gke_early_faced: int = 0
    gke_early_saves: int = 0
    gke_rest_faced: int = 0
    gke_rest_saves: int = 0
    # Emberhátrány-lövőik: [{"player_id", "jersey", "shots", "goals"}]
    # — ki vállalja a befejezést öt emberrel; darabszámok, meccsek közt
    # pontosan összegződnek.
    sh_shooters: list = field(default_factory=list)
    # Hajrá-hibázóik: [{"player_id", "jersey", "turnovers"}] — kinél
    # megy el a labda a döntő szakaszban; darabszámok, meccsek közt
    # pontosan összegződnek.
    clutch_losers: list = field(default_factory=list)
    # Csere-kiváltóik: a mért cserék és azok száma, amelyek kapott gól
    # után jöttek — darabszámok, meccsek közt pontosan összegződnek
    # (arány = stg_after / stg_subs).
    stg_subs: int = 0
    stg_after: int = 0
    # Falépítés-idejük: a mért birtokváltások és a rendezett falig
    # eltelt idő összege (mp) — összegek, meccsek közt pontosan
    # összegződnek (átlag = összeg / eset).
    dst_cases: int = 0
    dst_sum_s: float = 0.0
    # Kapusuk emberhátrányban: helyzetenként (emberhátrány / egyenlő
    # létszám) a kapura tartó lövések és a fogások — darabszámok,
    # meccsek közt pontosan összegződnek.
    gsh_sh_faced: int = 0
    gsh_sh_saves: int = 0
    gsh_eq_faced: int = 0
    gsh_eq_saves: int = 0
    # Emberelőny-lövőik: [{"player_id", "jersey", "shots", "goals"}] —
    # ki fejez be a két perc alatt; darabszámok, meccsek közt pontosan
    # összegződnek.
    pp_shooters: list = field(default_factory=list)
    # Lövés-távolságuk félidőnként: félidőnként a mért lövések és a
    # távolság-összeg (m) — összegek, meccsek közt pontosan
    # összegződnek (félidő-átlag = összeg / darab).
    sdf_fh_shots: int = 0
    sdf_fh_sum_m: float = 0.0
    sdf_sh_shots: int = 0
    sdf_sh_sum_m: float = 0.0
    # Kapott góljaik támadás-típus szerint: {típus: gólok} — melyik
    # műfajból szivárognak; darabszámok, meccsek közt pontosan
    # összegződnek (részarány = típus / összes kapott gól).
    conceded_types: dict = field(default_factory=dict)
    # Áttörő játékosaik: [{"player_id", "jersey", "entries", "goals"}]
    # — ki jut be labdával a 9 m-es körzetbe és hány gólos támadásban;
    # darabszámok, meccsek közt pontosan összegződnek.
    breakthrough_players: list = field(default_factory=list)
    # Két beállós játékuk: a mért támadások és azok száma, amelyekben
    # két emberük is a 6 m-es zónában dolgozott — darabszámok, meccsek
    # közt pontosan összegződnek (arány = dpv_double / dpv_attacks).
    dpv_attacks: int = 0
    dpv_double: int = 0
    # Hajrá-embereik: [{"player_id", "jersey", "frames"}] — az utolsó
    # 10 percben a pályán töltött kockák; darabszámok, meccsek közt
    # pontosan összegződnek (aki több meccsen is fent van, előre kerül).
    clutch_players: list = field(default_factory=list)
    # Kontra-kíséretük: a mért lerohanások és a felfutó emberek
    # összege — összegek, meccsek közt pontosan összegződnek (átlag =
    # összeg / lerohanás).
    fbs_breaks: int = 0
    fbs_sum_runners: float = 0.0
    # Kapusuk hetesvédése irány szerint: irányonként (bal / közép /
    # jobb, a dobó szemszögéből) a kapura tartó hetesek és a fogások —
    # darabszámok, meccsek közt pontosan összegződnek.
    g7d_faced: dict = field(default_factory=dict)
    g7d_saved: dict = field(default_factory=dict)
    # Kihozatal-oldaluk: sávonként (bal / közép / jobb) a támadások —
    # darabszámok, meccsek közt pontosan összegződnek (részarány =
    # sáv / összes támadás).
    bus_left: int = 0
    bus_center: int = 0
    bus_right: int = 0
    # Lepattanó-szerzőik: [{"player_id", "jersey", "rebounds"}] — ki
    # gyűjti a saját lövéseik kipattanóit; darabszámok, meccsek közt
    # pontosan összegződnek.
    rebounders: list = field(default_factory=list)
    # Lövőik távolság-profilja: [{"player_id", "jersey", "shots",
    # "sum_dist_m"}] — lövőnként a lövések száma és a távolság-összeg;
    # összegek, meccsek közt pontosan összegződnek (átlag = összeg /
    # darab).
    shooter_ranges: list = field(default_factory=list)
    # Emberhátrány-formájuk: {forma: kocka} — milyen falat húznak öt
    # emberrel; darabszámok, meccsek közt pontosan összegződnek.
    sh_shape: dict = field(default_factory=dict)
    # Emberelőny-tempójuk: emberelőnyben és egyenlő létszámnál a mért
    # támadások száma és össz-hosszuk (mp) — összegek, meccsek közt
    # pontosan összegződnek (átlag = összeg / darab).
    ppp_pp_attacks: int = 0
    ppp_pp_sum_s: float = 0.0
    ppp_eq_attacks: int = 0
    ppp_eq_sum_s: float = 0.0
    # Meccs-ritmusuk: a mért játékidő, a megszakított idő (mp) és a
    # náluk megállt játék megszakításai — összegek, meccsek közt
    # pontosan összegződnek (effektív arány = 1 − stopped / total).
    ptp_total_s: float = 0.0
    ptp_stopped_s: float = 0.0
    ptp_own_stoppages: int = 0
    # Védekezés-keménységük: a védekezett támadások, az ellenük ítélt
    # hetesek és a kapott kiállítások — darabszámok, meccsek közt
    # pontosan összegződnek (arány = (hetes + kiállítás) / támadás).
    agr_attacks: int = 0
    agr_sevens: int = 0
    agr_susp: int = 0
    # Visszaérés-fegyelmük: [{"player_id", "jersey", "frames",
    # "home_frames"}] — játékosonként a védekezett kockák és azok,
    # amelyekben a saját térfélen volt; darabszámok, meccsek közt
    # pontosan összegződnek (arány = home_frames / frames).
    recovery_players: list = field(default_factory=list)
    # Kapusuk védései lövés-tempó szerint: sávonként (kemény /
    # helyezett) a kapura tartó lövések és a fogások — darabszámok,
    # meccsek közt pontosan összegződnek (védés-arány = saves / faced).
    gsp_hard_faced: int = 0
    gsp_hard_saves: int = 0
    gsp_placed_faced: int = 0
    gsp_placed_saves: int = 0
    # Álló támadóik: [{"player_id", "jersey", "seconds", "dist_m"}] —
    # játékosonként a támadásban mért idő és megtett út; összegek,
    # meccsek közt pontosan összegződnek (átlag = dist_m / seconds).
    static_attackers: list = field(default_factory=list)
    # Szélső-befejezésük oldalanként: oldalanként a szélső-sávos
    # lövések és góljaik — darabszámok, meccsek közt pontosan
    # összegződnek (gólarány = gól / lövés).
    wfs_left_shots: int = 0
    wfs_left_goals: int = 0
    wfs_right_shots: int = 0
    wfs_right_goals: int = 0
    # Beállójuk oldala: sávonként (bal / közép / jobb) a mért kockák —
    # darabszámok, meccsek közt pontosan összegződnek (részarány =
    # sáv / összes).
    pvs_left: int = 0
    pvs_center: int = 0
    pvs_right: int = 0
    # Fal-csúszásuk késése: a mért védekezett kockák és a mért késés
    # (mp) szorzata — összegek, hogy meccsek közt súlyozva átlagolható
    # legyen (átlag-késés = dsl_sum_s / dsl_frames).
    dsl_frames: int = 0
    dsl_sum_s: float = 0.0
    # Passz-sebességük: a mért passzok, a sebesség-összeg (m/s) és az
    # éles (12 m/s feletti) passzok száma — összegek, meccsek közt
    # pontosan összegződnek (átlag = összeg / darab).
    psp_passes: int = 0
    psp_sum_ms: float = 0.0
    psp_fast: int = 0
    # Beálló-kiszolgálóik: [{"player_id", "jersey", "feeds"}] —
    # játékosonként a beállónak adott beadások; darabszámok, meccsek
    # közt pontosan összegződnek (részarány = feeds / összes beadás).
    pivot_feeders: list = field(default_factory=list)
    # Hetes-okozó védőik: [{"player_id", "conceded"}] — kinél szakad
    # meg a védekezés hetessel; darabszámok, meccsek közt pontosan
    # összegződnek.
    seven_conceders: list = field(default_factory=list)
    # Támadás-mélységük: a mért kockák és a kapu-távolság összege (m) —
    # összegek, meccsek közt pontosan összegződnek (átlag = összeg /
    # kocka).
    adp_frames: int = 0
    adp_sum_m: float = 0.0
    # Szélső-bevonásuk: a mért támadások és azok száma, amelyekben
    # kiment a labda a szélre — darabszámok, meccsek közt pontosan
    # összegződnek (arány = wi_with_wing / wi_attacks).
    wi_attacks: int = 0
    wi_with_wing: int = 0
    # Védekezési mélységük állás szerint: állásonként a mért kockák és
    # a magasság-összeg (m) — összegek, meccsek közt pontosan
    # összegződnek (átlag = összeg / kocka).
    lhs_lead_frames: int = 0
    lhs_lead_sum_m: float = 0.0
    lhs_trail_frames: int = 0
    lhs_trail_sum_m: float = 0.0
    # Támadás-kimeneteleik: {kimenetel: darab} — mivel zárulnak a
    # támadásaik (lövés / eladás / hetes / egyéb); darabszámok, meccsek
    # közt pontosan összegződnek (arány = kimenetel / összes támadás).
    attack_outcomes: dict = field(default_factory=dict)
    # Kapusuk védései posztonként: {poszt: {"faced", "saves"}} — melyik
    # szögből sebezhető; darabszámok, meccsek közt pontosan
    # összegződnek (védés-arány = saves / faced).
    gk_role_saves: dict = field(default_factory=dict)
    # Hiba-sorozataik: az eladásaik száma, a sorozatban (egy percen
    # belül egymást követve) érkezők száma és a sorozatok darabszáma —
    # darabszámok, meccsek közt pontosan összegződnek (sorozat-arány =
    # tc_clustered / tc_turnovers).
    tc_turnovers: int = 0
    tc_clustered: int = 0
    tc_clusters: int = 0
    # Kapott góljaik posztonként: {poszt: gólok} — melyik poszt ellen
    # szivárog a faluk; darabszámok, meccsek közt pontosan
    # összegződnek (részarány = poszt / összes kapott gól).
    conceded_roles: dict = field(default_factory=dict)
    # Poszt szerinti gólmegoszlásuk: {poszt: gólok} — melyik posztról
    # jönnek a góljaik; darabszámok, meccsek közt pontosan
    # összegződnek (részarány = poszt / összes poszthoz kötött gól).
    role_goals: dict = field(default_factory=dict)
    # Gólpassz-zónáik: {zóna: gólpasszok} — honnan érkezik az
    # előkészítés (szélről / beállótól / átlövésből); darabszámok,
    # meccsek közt pontosan összegződnek (részarány = zóna / összes).
    assist_zones: dict = field(default_factory=dict)
    # Támadás-indítóik: [{"player_id", "jersey", "starts"}] —
    # játékosonként hányszor ő hozta fel a labdát; darabszámok, meccsek
    # közt pontosan összegződnek (részarány = starts / összes indítás).
    starters: list = field(default_factory=list)
    tot_timeouts: int = 0
    tot_sum_before: int = 0
    tot_late: int = 0
    pair_plus_minus: list = field(default_factory=list)
    pair_fps: float = 25.0
    sbl_waves: int = 0
    sbl_players: int = 0
    sbl_block_waves: int = 0
    fsw_labels: dict = field(default_factory=dict)
    fsw_attacks: int = 0
    fsw_pairs: int = 0
    fsw_switches: int = 0
    # Lövő-erejük: [{"player_id", "shots", "sum_kmh", "max_kmh"}] —
    # a sebesség-összeg és a lövésszám tárolva, hogy az átlag meccsek
    # közt pontosan visszaszámolható legyen; + a csapat sebesség-
    # összege és lövésszáma a csapatátlaghoz.
    shooter_power: list = field(default_factory=list)
    spw_team_shots: int = 0
    spw_team_sum_kmh: float = 0.0
    # Lövő-kapuoldaluk: [{"player_id", "goals", "bal", "közép",
    # "jobb"}] — ki melyik sarokba lő; darabszámok, meccsek közt
    # játékosonként és oldalanként összegződnek.
    shooter_placement: list = field(default_factory=list)
    # Szélső-védekezés: a szélső, illetve középső sávból kapott
    # lövések és gólok száma — darabszámok, meccsek közt összegződnek
    # (gólarány sávonként külön).
    wdf_wing_shots: int = 0
    wdf_wing_goals: int = 0
    wdf_center_shots: int = 0
    wdf_center_goals: int = 0
    # Drága eladóik: [{"player_id", "turnovers", "punished"}] — kinek
    # az eladásaiból lett fél percen belüli kapott gól; darabszámok,
    # meccsek közt játékosonként összegződnek.
    costly_turnover_players: list = field(default_factory=list)
    # Emberelőny-védekezés: emberelőnyben töltött idő és az alatta
    # kapott gólok + az egyenlő létszámú viszonyítás — darabszámok és
    # összegek, meccsek közt pontosan összegződnek (ütem = gól / perc).
    ppd_seconds: float = 0.0
    ppd_conceded: int = 0
    ppd_eq_seconds: float = 0.0
    ppd_eq_conceded: int = 0
    # Kapus szabad lövés ellen: a szabad, illetve fedezett lövésre
    # kapott kapura tartó lövések és a védések száma — darabszámok,
    # meccsek közt összegződnek (védés-arány sávonként külön).
    gkf_free_shots: int = 0
    gkf_free_saves: int = 0
    gkf_cov_shots: int = 0
    gkf_cov_saves: int = 0
    # Kettőzés: a labdás-kockák és a kettőzött kockák száma + a
    # kikényszerített eladások — darabszámok, meccsek közt
    # összegződnek (arány = doubled / holder).
    dbl_holder_frames: int = 0
    dbl_doubled_frames: int = 0
    dbl_forced_to: int = 0
    # Kapus-indítás iránya: a bal, illetve jobb oldalra adott
    # kapus-indítások száma — darabszámok, meccsek közt összegződnek
    # (arány = left / (left + right)).
    gos_left: int = 0
    gos_right: int = 0
    # Hajrá-eladás: a hajrá előtti és a hajrá-eladások száma + a két
    # fázis hossza másodpercben — darabszámok és összegek, meccsek közt
    # pontosan összegződnek (ütem = eladás / perc fázisonként).
    cto_early_to: int = 0
    cto_early_s: float = 0.0
    cto_clutch_to: int = 0
    cto_clutch_s: float = 0.0
    # Hátrány-támadás: emberhátrányban töltött idő és az alatta lőtt
    # lövések/gólok + az egyenlő létszámnál szerzett gólok és a hozzá
    # tartozó idő — darabszámok és összegek, meccsek közt pontosan
    # összegződnek (ütem = gól / perc fázisonként).
    sha_seconds: float = 0.0
    sha_shots: int = 0
    sha_goals: int = 0
    sha_eq_seconds: float = 0.0
    sha_eq_goals: int = 0
    # Fölény-befejezés: a létszámfölényből, illetve a felállt fal
    # ellen leadott lövések és gólok száma — darabszámok, meccsek közt
    # összegződnek (gólarány sávonként külön).
    ovl_shots: int = 0
    ovl_goals: int = 0
    ovl_set_shots: int = 0
    ovl_set_goals: int = 0
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

    # Játékos-mérleg: kinek a pályán léte alatt megy a legjobban.
    _pm_rows = [p for p in (rep.player_plus_minus or [])
                if p["frames"] / (rep.pm_fps or 25.0) / 60.0 >= 5.0]
    if _pm_rows:
        _pm_best = max(
            _pm_rows,
            key=lambda p: ((p["for"] - p["against"])
                           / max(0.1, p["frames"] / (rep.pm_fps or 25.0)
                                 / 60.0)))
        _pm_min = _pm_best["frames"] / (rep.pm_fps or 25.0) / 60.0
        _pm_diff = _pm_best["for"] - _pm_best["against"]
        if _pm_diff / _pm_min >= 0.15:
            keys.append(
                f"A(z) {_pm_best['player_id']} azonosítójú játékosuk "
                f"a pályán megy a legjobban a játékuk "
                f"({_pm_best['for']}-{_pm_best['against']} a mérleg "
                f"{_pm_min:.0f} perc alatt) — vele szemben kell a "
                "legerősebb védekezés, és őt kell fárasztani: menjetek "
                "rá védekezésben is.")

    # Kapus-bevonás: kiterjedjen-e a letámadás a kapusra.
    if rep.kiv_spells >= 8:
        _kiv_pct = 100.0 * rep.kiv_with / rep.kiv_spells
        if _kiv_pct >= 25.0:
            keys.append(
                f"Sokat játszanak vissza a kapusnak (a birtoklásaik "
                f"{_kiv_pct:.0f}%-ában megjárja a labda a kapust) — a "
                "letámadásnak rá is ki kell terjednie: onnan hosszú, "
                "olvasható passz jön, és a kapusra lépve labdát "
                "lehet szerezni.")
        elif _kiv_pct <= 5.0:
            keys.append(
                f"Nem játszanak vissza a kapusnak (a birtoklásaiknak "
                f"csak {_kiv_pct:.0f}%-ában érinti a labdát) — a "
                "kihozataluk szűk, mezőnyben zajlik: a passzsávokat "
                "kell zárni, a kapusra menni fölösleges.")

    # Keresztjáték: kell-e váltás-fegyelem a faladnak.
    if rep.crx_attacks >= 8:
        _crx_per = rep.crx_crosses / rep.crx_attacks
        if _crx_per >= 1.0:
            keys.append(
                f"Sokat kereszteznek (támadásonként átlag "
                f"{_crx_per:.1f} oldalcsere a hátsó sorban) — a "
                "váltás-fegyelem dönt: hangos, korai átadás a védők "
                "közt, különben a kereszt után ketten fogjátok "
                "ugyanazt az embert.")
        elif _crx_per <= 0.3:
            keys.append(
                f"Statikus a hátsó soruk (támadásonként csak "
                f"{_crx_per:.1f} keresztezés) — ember-ember tartás is "
                "vállalható ellenük: nincs váltás-helyzet, a védőid "
                "végig a saját emberükön maradhatnak.")

    # Szélső-futtatás: kifutással vagy sávzárással védekezz a szélen.
    if rep.wsv_receptions >= 6:
        _wsv_pct = 100.0 * rep.wsv_running / rep.wsv_receptions
        if _wsv_pct >= 55.0:
            keys.append(
                f"Futtatva kapják a szélsőik a labdát "
                f"({rep.wsv_running}/{rep.wsv_receptions} átvétel "
                "mozgásból) — a kifutás mindig késni fog: a "
                "futópassz sávját kell zárni, nem a lövést fogni.")
        elif _wsv_pct <= 25.0:
            keys.append(
                f"Állva kapják a szélsőik a labdát (csak "
                f"{rep.wsv_running}/{rep.wsv_receptions} átvétel "
                "mozgásból) — a bátor, korai kifutás a recept: az "
                "álló szélső lezárható, mielőtt lendületet venne.")

    # Beálló-futtatás: a bejátszás előtt vagy után lépj a beálló elé.
    if rep.psv_receptions >= 5:
        _psv_pct = 100.0 * rep.psv_running / rep.psv_receptions
        if _psv_pct >= 55.0:
            keys.append(
                f"Mozgásból kapja a beállójuk a labdát "
                f"({rep.psv_running}/{rep.psv_receptions} átvétel "
                "lefordulásból) — az átvétel utáni birkózás késő: a "
                "bejátszás ELŐTT kell elé lépni, hangos váltással a "
                "passzsávot zárni.")
        elif _psv_pct <= 25.0:
            keys.append(
                f"Állva, beragadva kap a beállójuk (csak "
                f"{rep.psv_running}/{rep.psv_receptions} átvétel "
                "mozgásból) — testes elé állással és a bejátszás "
                "utáni azonnali kettőzéssel lezárható, mielőtt "
                "megfordulna.")

    # Kontra-hullámok: kit kell felvenni a visszafutásnál.
    if rep.fbw_breaks >= 5:
        _fbw_pct = 100.0 * rep.fbw_second / rep.fbw_breaks
        if _fbw_pct >= 50.0:
            keys.append(
                f"A kontráikat a második hullám fejezi be "
                f"({rep.fbw_second}/{rep.fbw_breaks} lerohanás a "
                "befutó lövésével) — az első ember felvétele NEM "
                "elég: a visszafutásnál a középső sávot töltsétek "
                "fel, mert a gól a befutótól jön.")
        elif _fbw_pct <= 20.0:
            keys.append(
                f"Az első ember fejezi be a kontráikat (csak "
                f"{rep.fbw_second}/{rep.fbw_breaks} lerohanás a "
                "befutóé) — az indítópassz elvágása és az első "
                "ember azonnali felvétele megöli a kontrájukat.")

    # Kontra-elszökés: kell-e állandó mélységbiztosítás ellenük.
    if rep.fbh_breaks >= 5:
        _fbh_pct = 100.0 * rep.fbh_ahead / rep.fbh_breaks
        if _fbh_pct >= 40.0:
            keys.append(
                f"Előre szökött emberrel kontráznak "
                f"({rep.fbh_ahead}/{rep.fbh_breaks} lerohanás indult "
                "a labda előtt váró játékossal) — állandó "
                "mélységbiztosítás kell: a fal mögött mindig "
                "maradjon egy kijelölt védő, és a hosszú "
                "indítópasszt kell elvágni.")
        elif _fbh_pct <= 10.0:
            keys.append(
                f"Együtt futnak fel a kontráik (csak "
                f"{rep.fbh_ahead}/{rep.fbh_breaks} lerohanás indult "
                "elszökött emberrel) — az első két visszafutó a "
                "labdás embert lassítsa: a védelem beér, mert "
                "nincs, aki megelőzze.")

    # Lefogott lövők: ki ellen éri meg falban maradni.
    if rep.bsh_blocked >= 4 and rep.bsh_shooters:
        _bsh_label, _bsh_n = next(iter(rep.bsh_shooters.items()))
        _bsh_share = 100.0 * _bsh_n / rep.bsh_blocked
        _bsh_vals = list(rep.bsh_shooters.values())
        _bsh_tie = len(_bsh_vals) > 1 and _bsh_vals[1] == _bsh_n
        if _bsh_share >= 50.0 and not _bsh_tie:
            keys.append(
                f"A(z) {_bsh_label} mezszámú lövőjük lövését rendre "
                f"elviszi a fal ({_bsh_n}/{rep.bsh_blocked} lefogott "
                "lövés az övé) — ellene érdemes falban maradni: nem "
                "kell kifutni, a blokk dolgozik helyettetek.")

    # Gólpassz-posztok: melyik poszt kezét kell megfogni.
    if rep.abr_assists >= 5 and rep.abr_roles:
        _abr_poszt, _abr_n = next(iter(rep.abr_roles.items()))
        _abr_vals = list(rep.abr_roles.values())
        _abr_tie = len(_abr_vals) > 1 and _abr_vals[1] == _abr_n
        if 100.0 * _abr_n / rep.abr_assists >= 45.0 and not _abr_tie:
            keys.append(
                f"A góljaikat jellemzően a(z) {_abr_poszt} posztról "
                f"készítik elő ({_abr_n}/{rep.abr_assists} gólpassz) "
                "— az ő kezét kell megfogni: irányítónál felső "
                "kettőzés, szélsőnél a visszatett labda zárása, "
                "beállónál elé állás a kiosztás ellen is.")

    # Kiállítás-posztok: hol tilos a kéz, hol kell a korai lépés.
    if rep.sur_suspensions >= 3 and rep.sur_roles:
        _sur_poszt, _sur_n = next(iter(rep.sur_roles.items()))
        _sur_vals = list(rep.sur_roles.values())
        _sur_tie = len(_sur_vals) > 1 and _sur_vals[1] == _sur_n
        if (100.0 * _sur_n / rep.sur_suspensions >= 50.0
                and not _sur_tie):
            keys.append(
                f"A kétperceseket jellemzően a(z) {_sur_poszt} "
                f"posztról hozzák ({_sur_n}/{rep.sur_suspensions} "
                "kiharcolt kiállítás) — ellene fegyelmezett kéz és "
                "korai, testes lépés kell: a kései fogás náluk "
                "emberelőnyt termel.")

    # Falba lövő posztok: hol elég tartani a falat.
    if rep.bbr_blocked >= 4 and rep.bbr_roles:
        _bbr_poszt, _bbr_n = next(iter(rep.bbr_roles.items()))
        _bbr_vals = list(rep.bbr_roles.values())
        _bbr_tie = len(_bbr_vals) > 1 and _bbr_vals[1] == _bbr_n
        if 100.0 * _bbr_n / rep.bbr_blocked >= 50.0 and not _bbr_tie:
            keys.append(
                f"A falba lőtt lövéseik a(z) {_bbr_poszt} posztról "
                f"jönnek ({_bbr_n}/{rep.bbr_blocked} lefogott lövés) "
                "— ott a fal tartása elég: nem kell kilépni, a "
                "blokk magától termel.")

    # Felhozatal-posztok: kit kell fogni a letámadásnál.
    if rep.otr_outlets >= 4 and rep.otr_roles:
        _otr_poszt, _otr_n = next(iter(rep.otr_roles.items()))
        _otr_vals = list(rep.otr_roles.values())
        _otr_tie = len(_otr_vals) > 1 and _otr_vals[1] == _otr_n
        if 100.0 * _otr_n / rep.otr_outlets >= 50.0 and not _otr_tie:
            keys.append(
                f"A felhozataluk a(z) {_otr_poszt} posztra épül "
                f"({_otr_n}/{rep.otr_outlets} indítás-célpont) — a "
                "letámadásnál őt kell fogni: nála akad meg az egész "
                "felhozatal, a kapus kényszer-hosszút dob.")

    # Kontra-esés: melyik félidőre kell a visszafutást élezni.
    if (rep.brf_fh_attacks >= 5 and rep.brf_sh_attacks >= 5):
        _brf_fh = 100.0 * rep.brf_fh_breaks / rep.brf_fh_attacks
        _brf_sh = 100.0 * rep.brf_sh_breaks / rep.brf_sh_attacks
        if _brf_sh - _brf_fh <= -15.0:
            keys.append(
                f"A második félidőben eláll a kontrájuk (a "
                f"lerohanás-arányuk {_brf_fh:.0f}%-ról "
                f"{_brf_sh:.0f}%-ra esik) — az elejét kell túlélni: "
                "a szünet után már a felállt védekezésetek dolgozik, "
                "nem a visszafutás.")
        elif _brf_sh - _brf_fh >= 15.0:
            keys.append(
                f"A hajrára kontrázósabbak (a lerohanás-arányuk "
                f"{_brf_fh:.0f}%-ról {_brf_sh:.0f}%-ra nő) — a "
                "második félidőben duplán szigorú visszafutás-"
                "fegyelem és biztos labdakezelés kell ellenük.")

    # Szélső-mélység: várjon vagy jöjjön a kapus a szélső-lövésnél.
    if rep.wsd_shots >= 5:
        _wsd_avg = rep.wsd_depth_sum_m / rep.wsd_shots
        if _wsd_avg <= 6.5:
            keys.append(
                f"Mélyre befutó szélsőik vannak (átlag "
                f"{_wsd_avg:.1f} m-ről lőnek) — a kapusnak várnia "
                "kell: a korai kifutás öngól, a szöget a kifutó "
                "védő zárja még a befutás előtt.")
        elif _wsd_avg >= 8.5:
            keys.append(
                f"Messziről lövő szélsőik vannak (átlag "
                f"{_wsd_avg:.1f} m-ről eresztik el) — a szög "
                "ráengedhető: a kapus bátran jöhet ki, a falnak "
                "nem kell szétszorulnia a szélre.")

    # Kettőző emberek: kiolvasható-e, honnan jön a kettőzésük.
    if rep.dtp_frames >= 50 and rep.dtp_doublers:
        _dtp_label, _dtp_n = next(iter(rep.dtp_doublers.items()))
        _dtp_vals = list(rep.dtp_doublers.values())
        _dtp_tie = len(_dtp_vals) > 1 and _dtp_vals[1] == _dtp_n
        if 100.0 * _dtp_n / rep.dtp_frames >= 40.0 and not _dtp_tie:
            keys.append(
                f"Kiszámítható a kettőzésük: a(z) {_dtp_label} "
                f"mezszámú jön másodiknak (a kettőzött idő "
                f"{100.0 * _dtp_n / rep.dtp_frames:.0f}%-ában) — a "
                "kettőzés pillanatában az Ő embere szabadul: oda "
                "menjen az első passz, begyakorolt jelre.")

    # Átvert védők: kire kell vinni az 1v1-et.
    if rep.btn_goals >= 4 and rep.btn_defenders:
        _btn_label, _btn_n = next(iter(rep.btn_defenders.items()))
        _btn_vals = list(rep.btn_defenders.values())
        _btn_tie = len(_btn_vals) > 1 and _btn_vals[1] == _btn_n
        if 100.0 * _btn_n / rep.btn_goals >= 40.0 and not _btn_tie:
            keys.append(
                f"A kapott góljaiknál rendre a(z) {_btn_label} "
                f"mezszámú védő veszíti a párharcot "
                f"({_btn_n}/{rep.btn_goals}) — rá vigyétek az "
                "1v1-et: elzárással hozzá tereljétek a lövőt, az ő "
                "oldala a nyitott ajtó.")

    # Zavartalan előkészítők: futhat-e ellenük a kidolgozott játék.
    if rep.upa_assisted >= 5:
        _upa_pct = 100.0 * rep.upa_unpressured / rep.upa_assisted
        if _upa_pct >= 60.0:
            keys.append(
                f"Az előkészítőt hagyják dolgozni ({rep.upa_unpressured}"
                f"/{rep.upa_assisted} kapott gólpassz zavartalan "
                "kiadásból) — a kidolgozott játékotok szabadon futhat: "
                "türelmes járatás után a kiadó nyugodtan mérheti ki "
                "az utolsó passzt.")
        elif _upa_pct <= 25.0:
            keys.append(
                f"Az előkészítőre rálépnek (csak {rep.upa_unpressured}"
                f"/{rep.upa_assisted} zavartalan kiadás) — az utolsó "
                "passz eléjük nehéz: egy-ütemű, korai kiadások "
                "kellenek, mielőtt a nyomás odaér.")

    # Csere-büntetés: bizonyítottan büntethető-e a cseréjük.
    if rep.gpn_conceded >= 2:
        keys.append(
            f"A csere-lyukaik gólba kerülnek ({rep.gpn_conceded} "
            f"kapott gól {rep.gpn_gap_s:.0f} mp öt fős játék alatt) "
            "— a cseréjük pillanata bizonyítottan támadható: gyors "
            "középkezdés és azonnali befejezés, amíg hiányzik az "
            "emberük.")

    # Folyosó-gólok: a faluk vagy a kapusuk a gyenge pont.
    if rep.crg_goals >= 5:
        _crg_pct = 100.0 * rep.crg_open / rep.crg_goals
        if _crg_pct >= 50.0:
            keys.append(
                f"Nyitott folyosókon kapják a gólokat "
                f"({rep.crg_open}/{rep.crg_goals} előtt senki nem "
                "állt a lövésvonalban) — a faluk nem ér oda: a "
                "betörést és a gyors átmenetet erőltessétek, ne a "
                "kintről lövöldözést.")
        elif _crg_pct <= 20.0:
            keys.append(
                f"Zárt fal mögött is bekapják (csak {rep.crg_open}/"
                f"{rep.crg_goals} gól jött nyitott folyosón) — a "
                "kapus-oldaluk a kérdés: türelmes, kimozgató játék "
                "után a pontos elhelyezés visz be, nem az erő.")

    # Bontó tempó: járatással vagy egyéni akcióval kell bontani.
    if rep.ctm_goals >= 5:
        _ctm_avg = rep.ctm_passes_sum / rep.ctm_goals
        if _ctm_avg >= 3.0:
            keys.append(
                f"A járatás szedi szét őket (a kapott góljaik előtt "
                f"átlag {_ctm_avg:.1f} passz ment 8 mp-en belül) — "
                "tempót emeljetek: minél több oldalváltás és passz, "
                "annál előbb nyílik a rés a falukon.")
        elif _ctm_avg <= 1.5:
            keys.append(
                f"Egyéni akciókból kapják a gólokat (átlag "
                f"{_ctm_avg:.1f} passz a góljaik előtt) — az 1v1-ben "
                "erős embereiteket engedjétek rájuk: a hosszú "
                "járatás csak időt ad nekik rendeződni.")

    # Lendület-gólok: a betörőt vagy az átlövőt kell rájuk küldeni.
    if rep.cgm_goals >= 5:
        _cgm_pct = 100.0 * rep.cgm_running / rep.cgm_goals
        if _cgm_pct >= 55.0:
            keys.append(
                f"Mozgásból kapják a gólokat ({rep.cgm_running}/"
                f"{rep.cgm_goals} gólnál lendületből érkezett a "
                "lövő) — a bekísérésük késik: a betörőt és a "
                "befutót játsszátok, az érkező embert nem veszik "
                "fel időben.")
        elif _cgm_pct <= 25.0:
            keys.append(
                f"Állóhelyből is bekapják (csak {rep.cgm_running}/"
                f"{rep.cgm_goals} gól jött mozgásból) — a faluk "
                "tiszta lövést enged: a nyugodt, kivárt átlövés is "
                "termel ellenük.")

    # Becsapott kapus: csellel vagy első ütemből kell-e lőni.
    if rep.wfk_goals >= 5:
        _wfk_pct = 100.0 * rep.wfk_fooled / rep.wfk_goals
        if _wfk_pct >= 40.0:
            keys.append(
                f"Elmozdítható a kapusuk ({rep.wfk_fooled}/"
                f"{rep.wfk_goals} kapott gólnál ellenirányba "
                "mozdult) — minden lövő hozzon kötelező lövőcselt: "
                "a kapus elindul, a labda a másik oldalé.")
        elif _wfk_pct <= 10.0:
            keys.append(
                f"A kapusuk állja a cseleket (csak {rep.wfk_fooled}/"
                f"{rep.wfk_goals} gólnál mozdult rosszul) — a csel "
                "ellene időpocsékolás: első ütemből, pontosan a "
                "sarokba kell lőni.")

    # Olvasó kapus: ütem-váltással vagy kitartott sarokkal kell lőni.
    if rep.rdk_saves >= 5:
        _rdk_pct = 100.0 * rep.rdk_read / rep.rdk_saves
        if _rdk_pct >= 50.0:
            keys.append(
                f"A kapusuk olvassa a lövéseket ({rep.rdk_read}/"
                f"{rep.rdk_saves} védésnél indult előre a labda "
                "oldalára) — a korai elköteleződését büntessétek: "
                "ütem-váltás és csel, ne a megszokott sarok.")
        elif _rdk_pct <= 15.0:
            keys.append(
                f"Reflexből véd a kapusuk (csak {rep.rdk_read}/"
                f"{rep.rdk_saves} olvasott védés) — nincs mit "
                "becsapni: a kitartott, pontos sarok-lövés visz be.")

    # Kettőzés-büntetés: megéri-e kivárni a kettőzésüket.
    if rep.dbp_conceded_after >= 2:
        keys.append(
            f"A kettőzésük gólba kerül ({rep.dbp_conceded_after} "
            "gól esett közvetlenül kettőzés után) — a kettőzés-jel "
            "nálatok támadási jel: az első passz azonnal a "
            "felszabadult emberhez, és kész a helyzet.")

    # Kilépés-büntetés: a kilépőjük mögötti rés bizonyítottan él.
    if rep.sop_goals >= 5:
        _sop_pct = 100.0 * rep.sop_behind / rep.sop_goals
        if _sop_pct >= 40.0:
            keys.append(
                f"A kilépésük mögé betalálnak ({rep.sop_behind}/"
                f"{rep.sop_goals} kapott gólnál volt kiugró védő) — "
                "a kilépőt játsszátok meg: gyors átemelés vagy "
                "betörés a helyére, a rés bizonyítottan ott van.")

    # Kihagyás-büntetés: törékeny-e a fejük a kihagyás után.
    if rep.pmb_misses >= 4:
        _pmb_pct = 100.0 * rep.pmb_punished / rep.pmb_misses
        if _pmb_pct >= 40.0:
            keys.append(
                f"A kihagyásaik után azonnal büntethetők "
                f"({rep.pmb_punished}/{rep.pmb_misses} kihagyott "
                "ziccerüket követte fél percen belüli gól) — a "
                "ziccer-kimaradásuk a ti jeletek: azonnali tempó, "
                "kapura vitt első támadás, amíg mentálisan lent "
                "vannak.")
        elif _pmb_pct <= 10.0:
            keys.append(
                f"Jól emésztik a kihagyást (csak {rep.pmb_punished}/"
                f"{rep.pmb_misses} kihagyásukat követte gyors gól) — "
                "a kimaradt ziccerük után nincs ingyen lendület: a "
                "megszokott játékotokat vigyétek tovább.")

    # Indítás-hiba ára: bizonyítottan termel-e a letámadás.
    if rep.olp_punished >= 2:
        keys.append(
            f"Az elszórt indításaik gólba kerülnek ({rep.olp_punished}"
            f"/{rep.olp_lost} elveszett kihozatal után jött gyors "
            "gól) — a magas letámadás bizonyítottan termel ellenük: "
            "a kapus-indításokat vadásszátok.")

    # Elhúzódó támadás ára: megéri-e nekik a hosszú akció.
    if rep.sac_slow >= 3:
        _sac_pct = 100.0 * rep.sac_scored / rep.sac_slow
        if _sac_pct <= 25.0:
            keys.append(
                f"Az elhúzódó támadásaik üresen zárulnak ({rep.sac_scored}"
                f"/{rep.sac_slow} hosszú akció ért gólt) — türelmes, "
                "hibátlan védekezéssel a passzív jel nektek dolgozik: "
                "ne kockáztassatok, várjátok ki a kényszerű lövést.")
        elif _sac_pct >= 60.0:
            keys.append(
                f"A hosszú akcióikat is gólra váltják ({rep.sac_scored}"
                f"/{rep.sac_slow}) — a 35. másodpercben is teljes "
                "koncentráció: a falban senki nem kapcsolhat ki.")

    # Kidobott labda: olcsó eladások — oldalvonalra szorítás.
    if rep.obt_out >= 3:
        keys.append(
            f"Sok labdát dobnak ki maguktól az oldalvonalon "
            f"({rep.obt_out} kidobott labda) — szorítsátok a "
            "labdásukat az oldalvonalra: a szélső sávban pontatlanok, "
            "és a hibához ellenfél sem kell.")

    # Fegyelem-állás: a frusztrációs kiállítás ellenük fegyver.
    _sps_n = rep.sps_tr + rep.sps_lead + rep.sps_level
    if _sps_n >= 3 and rep.sps_tr - (rep.sps_lead + rep.sps_level) >= 2:
        keys.append(
            f"Hátrányban elszáll a fegyelmük ({rep.sps_tr}/{_sps_n} "
            "kiállításuk hátrányban jött) — ha vezettek, vállaljátok "
            "a kontaktot és játsszatok türelmesen: a frusztrációjuk "
            "kiállítást terem nektek.")
    elif _sps_n >= 3 and rep.sps_lead - (rep.sps_tr + rep.sps_level) >= 2:
        keys.append(
            f"Előnyben szabálytalankodnak ({rep.sps_lead}/{_sps_n} "
            "kiállításuk vezetésnél jött) — vezetés-őrző keménység: "
            "ha ők vezetnek, a betörőt védeni kell, jön az ütés.")

    # Hetes-állás: hátrányban a hetes a menekülő-fegyverük.
    _svs_n = rep.svs_tr + rep.svs_lead + rep.svs_level
    if _svs_n >= 3 and rep.svs_tr - (rep.svs_lead + rep.svs_level) >= 2:
        keys.append(
            f"Hátrányban a hetes a menekülő-fegyverük ({rep.svs_tr}/"
            f"{_svs_n} kiharcolt hetesük hátrányban jött) — ha "
            "vezettek, a fal lábbal védekezzen és ne üssön: a "
            "betörőjük a kezet keresi, a kapusnál hetes-készenlét.")

    # Kontra-állás: hátrányban futni fognak.
    if rep.bks_tr_attacks >= 5 and rep.bks_rest_attacks >= 5:
        _bks_tr = 100.0 * rep.bks_tr_breaks / rep.bks_tr_attacks
        _bks_rest = 100.0 * rep.bks_rest_breaks / rep.bks_rest_attacks
        if _bks_tr - _bks_rest >= 12.0:
            keys.append(
                f"Hátrányban kontrába menekülnek (hátrányban a "
                f"támadásaik {_bks_tr:.0f}%-a lerohanás, egyébként "
                f"{_bks_rest:.0f}%) — ha vezettek, a visszafutás-"
                "fegyelem dönt: fáradt lábbal is vissza kell érni, "
                "mert futni fognak.")

    # 7a6-állás: rendszer-7a6 ellen állandó üres-kapus készenlét.
    _ens_n = rep.ens_tr + rep.ens_lead + rep.ens_level
    if _ens_n >= 3 and (rep.ens_lead + rep.ens_level) - rep.ens_tr >= 2:
        keys.append(
            f"A 7 a 6 náluk nem mentőöv, hanem rendszer ({_ens_n} "
            f"üres-kapus szakaszból csak {rep.ens_tr} jött "
            "hátrányban) — minden szerzés után az első nézés a "
            "túloldali üres kapu, nem csak a hajrában.")
    elif _ens_n >= 3 and rep.ens_tr - (rep.ens_lead + rep.ens_level) >= 2:
        keys.append(
            f"Csak hátrányban hozzák le a kapust ({rep.ens_tr}/"
            f"{_ens_n} üres-kapus szakasz hátrányban) — amint "
            "megvan a vezetésetek, kapcsoljatok üres-kapus fejre: "
            "jönni fog a 7 a 6.")

    # Kapus-sorozat: a rákapó kapus ellen lövés-kép váltás.
    if rep.gst_on_target >= 6 and rep.gst_streaks >= 2:
        keys.append(
            f"Ha rákap, sorozatban véd a kapusuk ({rep.gst_streaks} "
            f"hármas védés-széria {rep.gst_on_target} kapura tartó "
            "lövésből) — két védése után válts lövés-képet: más "
            "zóna, más ritmus (pattintott/emelt), ha kell, időkérés.")

    # Gólpassz-esés: a hajrában megálló labda támadható.
    if rep.asf_fh_goals >= 3 and rep.asf_sh_goals >= 3:
        _asf_fh = 100.0 * rep.asf_fh_assisted / rep.asf_fh_goals
        _asf_sh = 100.0 * rep.asf_sh_assisted / rep.asf_sh_goals
        if _asf_fh - _asf_sh >= 25.0:
            keys.append(
                f"A hajrában megáll náluk a labda (gólpasszos gól "
                f"{_asf_fh:.0f}% → {_asf_sh:.0f}%) — a második "
                "félidőben a labdás emberük dupla nyomást kaphat: "
                "a passz úgyis megállt, egyéni megoldásból élnek.")

    # Lepattanó-esés: záráskor a második labda a tiétek.
    if rep.scf_fh_misses >= 3 and rep.scf_sh_misses >= 3:
        _scf_fh = 100.0 * rep.scf_fh_won / rep.scf_fh_misses
        _scf_sh = 100.0 * rep.scf_sh_won / rep.scf_sh_misses
        if _scf_fh - _scf_sh >= 25.0:
            keys.append(
                f"A hajrára elfogy a lepattanó-harcuk (visszaharcolt "
                f"lepattanó {_scf_fh:.0f}% → {_scf_sh:.0f}%) — "
                "záráskor a blokk és a védés utáni labda a tiétek: "
                "a kimaradt lövésük ott már a támadásuk vége.")

    # Szünet-váltás: kire készülj a második félidőben.
    if rep.ams_fh_attacks >= 6 and rep.ams_sh_attacks >= 6:
        _ams_shift = (abs(100.0 * rep.ams_fh_break / rep.ams_fh_attacks
                          - 100.0 * rep.ams_sh_break
                          / rep.ams_sh_attacks)
                      + abs(100.0 * rep.ams_fh_quick
                            / rep.ams_fh_attacks
                            - 100.0 * rep.ams_sh_quick
                            / rep.ams_sh_attacks)) / 2.0
        if _ams_shift >= 30.0:
            keys.append(
                f"A szünet után átrendezik a támadójátékukat "
                f"(~{_ams_shift:.0f} százalékpontos mix-váltás) — a "
                "ti szünetetekben ne a folytatásra készüljetek, "
                "hanem arra, MIT hoznak, ha az első félidei nem megy.")
        elif _ams_shift <= 10.0:
            keys.append(
                "Félidőn át ugyanazt játsszák (a támadás-mixük alig "
                "mozdul a szünet után) — egy jól előkészített "
                "védő-terv kitart ellenük 60 percen át: azt "
                "csiszoljátok, ne váltogassatok.")

    # Passz-irány-állás: az előny-hátrajáratás letámadható.
    if rep.pds_lead_passes >= 10 and rep.pds_rest_passes >= 10:
        _pds_lead = 100.0 * rep.pds_lead_back / rep.pds_lead_passes
        _pds_rest = 100.0 * rep.pds_rest_back / rep.pds_rest_passes
        if _pds_lead - _pds_rest >= 12.0:
            keys.append(
                f"Előnyben hátrafelé járatják a labdát (hátra-passz "
                f"{_pds_lead:.0f}% előnyben, egyébként "
                f"{_pds_rest:.0f}%) — ha ők vezetnek, magas "
                "letámadás: az első hátrapasszra rá lehet lépni, az "
                "időölésükből szerzés lesz.")

    # Kapus-gólpassz: a kapus-indítás sávját kell zárni.
    if rep.gka_assists >= 2:
        keys.append(
            f"A kapusuk keze gólt indít ({rep.gka_assists} "
            "kapus-gólpassz) — a lövésetek pillanatában induljon a "
            "visszafutás: az első hazafutó dolga nem a labda, hanem "
            "a kapus-passz sávjának elvágása.")

    # Passz-hossz-állás: a hátrány-hosszúlabda elfogható.
    if rep.pls_tr_passes >= 10 and rep.pls_rest_passes >= 10:
        _pls_tr = 100.0 * rep.pls_tr_long / rep.pls_tr_passes
        _pls_rest = 100.0 * rep.pls_rest_long / rep.pls_rest_passes
        if _pls_tr - _pls_rest >= 12.0:
            keys.append(
                f"Hátrányban hosszú labdákra váltanak (hosszú passz "
                f"{_pls_tr:.0f}% hátrányban, egyébként "
                f"{_pls_rest:.0f}%) — ha vezettek, üljetek a "
                "passzsávokra: az átdobált labdáik elfogása kontrát "
                "ér.")

    # Fal-váltás a szünetre: két támadó-tervvel kell érkezni.
    def _dfs_main(labels, n):
        if n < 5 or not labels:
            return None
        main, cnt = max(labels.items(), key=lambda kv: kv[1])
        return main if 100.0 * cnt / n >= 60.0 else None
    _dfs_fh = _dfs_main(rep.dfs_fh_labels, rep.dfs_fh_attacks)
    _dfs_sh = _dfs_main(rep.dfs_sh_labels, rep.dfs_sh_attacks)
    if _dfs_fh and _dfs_sh and _dfs_fh != _dfs_sh:
        keys.append(
            f"A szünet után falat váltanak ({_dfs_fh} → {_dfs_sh}) — "
            "két kész figurasorral érkezzetek: az első félidei "
            "támadó-terv a másodikban már nem ér semmit, a szünet "
            "utáni első támadásnál hangosan mondjátok be a formát.")

    # Oldal-váltás a szünetre: a fal súlypontját át kell tenni.
    def _sds_main(cnt, n):
        if n < 100 or not cnt:
            return None
        main, c = max(cnt.items(), key=lambda kv: kv[1])
        return main if 100.0 * c / n >= 40.0 else None
    _sds_fh = _sds_main(rep.sds_fh_counts, rep.sds_fh_frames)
    _sds_sh = _sds_main(rep.sds_sh_counts, rep.sds_sh_frames)
    if _sds_fh and _sds_sh and _sds_fh != _sds_sh:
        keys.append(
            f"A szünet után oldalt váltanak ({_sds_fh} → {_sds_sh}) — "
            "a szünet utáni első öt percben olvassátok újra a "
            "súlypontot: a fal erős embere és a kettőzés kerüljön át "
            "a másik oldalra.")

    # Hiba-állás: mikor éri meg présre váltani.
    if rep.tbs_tr_attacks >= 5 and rep.tbs_rest_attacks >= 5:
        _tbs_tr = 100.0 * rep.tbs_tr_tos / rep.tbs_tr_attacks
        _tbs_rest = 100.0 * rep.tbs_rest_tos / rep.tbs_rest_attacks
        if _tbs_tr - _tbs_rest >= 10.0:
            keys.append(
                f"Hátrányban kapkodnak (az eladós támadásaik aránya "
                f"{_tbs_rest:.0f}%-ról {_tbs_tr:.0f}%-ra ugrik) — az "
                "első ellépés után váltsatok présre: nyomás alatt "
                "ontják a labdát, és minden szerzés a különbséget "
                "hizlalja.")
        elif _tbs_tr - _tbs_rest <= -5.0:
            keys.append(
                f"Hátrányban is rendezettek (eladós támadás: "
                f"{_tbs_tr:.0f}%, egyébként {_tbs_rest:.0f}%) — a "
                "prés ellenük nem térül meg: a fegyelmezett fal "
                "többet ér, mint a kockázatos letámadás.")

    # Előny-védekezés: mit ér a faluk, amikor vezetnek.
    if rep.dbs_lead_shots >= 5 and rep.dbs_rest_shots >= 5:
        _dbs_lead = rep.dbs_lead_xg / rep.dbs_lead_shots
        _dbs_rest = rep.dbs_rest_xg / rep.dbs_rest_shots
        if _dbs_lead - _dbs_rest >= 0.05:
            keys.append(
                f"Előnyben leül a faluk (kapott átlag-xG vezetve "
                f"{_dbs_lead:.2f}, egyébként {_dbs_rest:.2f}) — ha "
                "hátrányba kerültök, nincs ok pánikra: a vezetésük "
                "puhább falat hoz, türelmes, bevitt támadásokkal "
                "visszajön a meccs.")
        elif _dbs_lead - _dbs_rest <= -0.02:
            keys.append(
                f"Előnyben is feszes a faluk (kapott átlag-xG "
                f"vezetve {_dbs_lead:.2f}) — ellenük a korai "
                "hátrány valódi baj: az elejét kell megnyerni, mert "
                "vezetve sem nyílik ki a védekezésük.")

    # Csere-állás: mit tesznek az előnnyel a padon.
    if (rep.sbs_lead_s >= 120.0 and rep.sbs_rest_s >= 120.0
            and rep.sbs_lead_subs + rep.sbs_rest_subs >= 4):
        _sbs_lead = rep.sbs_lead_subs / rep.sbs_lead_s
        _sbs_rest = rep.sbs_rest_subs / rep.sbs_rest_s
        if _sbs_lead >= 1.5 * _sbs_rest and rep.sbs_lead_subs >= 3:
            keys.append(
                f"Vezetve forgatnak ({rep.sbs_lead_subs} cserehullám "
                f"előnyben, {rep.sbs_rest_subs} egyébként) — a "
                "szoros meccs a fegyver ellenük: amíg nincs meg az "
                "előnyük, nem mernek pihentetni, és a kezdősoruk a "
                "hajrára elfárad.")
        elif (_sbs_lead <= 0.5 * _sbs_rest
              and rep.sbs_rest_subs >= 3):
            keys.append(
                f"Vezetve sem nyúlnak a sorhoz (csak "
                f"{rep.sbs_lead_subs} cserehullám előnyben) — a "
                "fáradó kulcsemberük végig fent marad: a meccs "
                "végén őt kell megtámadni.")

    # Indítás-állás: húzzák-e az időt a kihozatallal.
    if rep.ops_lead_outlets >= 4 and rep.ops_rest_outlets >= 4:
        _ops_lead = rep.ops_lead_sum_s / rep.ops_lead_outlets
        _ops_rest = rep.ops_rest_sum_s / rep.ops_rest_outlets
        if _ops_lead - _ops_rest >= 2.0:
            keys.append(
                f"Vezetve lassítják az indítást (átlag "
                f"{_ops_lead:.1f} mp kihozatal előnyben, "
                f"{_ops_rest:.1f} mp egyébként) — ha hátrányban "
                "vagytok, minden másodperc drága: kapott gól után "
                "azonnali középkezdés, és a lassítást a "
                "játékvezetőnél is jelezzétek.")
        elif _ops_lead - _ops_rest <= -1.0:
            keys.append(
                f"Előnyben is pörgetik az indítást (átlag "
                f"{_ops_lead:.1f} mp) — a védésük utáni pillanat a "
                "legveszélyesebb: a lövést azonnali visszarendeződés "
                "kövesse, nem reklamálás.")

    # Csere-lyukak: a cseréjük pillanata támadási jel-e.
    if rep.sbg_gap_s >= 20.0:
        keys.append(
            f"Lyukas a cseréjük (meccsenként átlagosan "
            f"{rep.sbg_gap_s / max(1, rep.matches):.0f} másodpercig "
            "öten védekeznek csere közben) — a cseréjük pillanata "
            "támadási jel: gyors középkezdés és azonnali befejezés, "
            "amíg hiányzik az emberük.")

    # Gólpassz-hossz: a sávzárás vagy a kis terület védése dönt.
    if rep.asr_assisted >= 5:
        _asr_pct = 100.0 * rep.asr_long / rep.asr_assisted
        if _asr_pct >= 50.0:
            keys.append(
                f"Hosszú gólpasszokból élnek ({rep.asr_long}/"
                f"{rep.asr_assisted} előkészítés jött 8 méteren "
                "túlról) — a passzsávakat zárjátok: a hosszú labda "
                "elfogható, és minden elfogás kontrát ér.")
        elif _asr_pct <= 20.0:
            keys.append(
                f"Rövid kombinációkból élnek (csak {rep.asr_long}/"
                f"{rep.asr_assisted} hosszú előkészítés) — a kis "
                "terület védése dönt: hangos váltások és testes "
                "besegítés a hatos előtt, mert kézről kézre járatva "
                "bontanak.")

    # Kapus-kipattanó: kell-e kipattanó-vadász a lövéseitek mögé.
    if rep.grc_saves >= 4:
        _grc_pct = 100.0 * rep.grc_caught / rep.grc_saves
        if _grc_pct <= 40.0:
            keys.append(
                f"Kiüti a labdát a kapusuk (csak {rep.grc_caught}/"
                f"{rep.grc_saves} védés maradt nála) — minden "
                "lövéseteket kísérjétek: a kijelölt kipattanó-vadász "
                "a hatosnál marad a lövés után, mert a kiütött labda "
                "a legolcsóbb gól.")
        elif _grc_pct >= 70.0:
            keys.append(
                f"Fogja a labdát a kapusuk ({rep.grc_caught}/"
                f"{rep.grc_saves} védés nála maradt) — a lövésetek "
                "pillanatában már indulni kell hátra: a fogott labda "
                "azonnali indítást ér, kipattanóra hiába vártok.")

    # Kivárás-csapda: véd-e ellenük a türelmes fal.
    if rep.lao_n >= 5:
        _lao_pct = 100.0 * rep.lao_died / rep.lao_n
        if _lao_pct >= 40.0:
            keys.append(
                f"A hosszú támadásaik elhalnak ({rep.lao_died}/"
                f"{rep.lao_n} lövés nélkül) — a kivárás nekik csapda: "
                "fegyelmezett, kivárós fal ellenük a recept, a "
                "passzív jel felétek dolgozik.")
        elif _lao_pct <= 15.0:
            keys.append(
                f"A hosszú támadásaik is lövésig érnek (csak "
                f"{rep.lao_died}/{rep.lao_n} halt el) — a kivárás nem "
                "véd ellenük: korai megzavarás kell, kilépés és "
                "kettőzés, mielőtt a figurájuk kibomlana.")

    # Felfutási létszám: kontrázhatók-e, és kettőzhető-e a faluk ellenük.
    if rep.ahc_frames >= 100:
        _ahc_avg = rep.ahc_sum_up / rep.ahc_frames
        if _ahc_avg >= 5.5:
            keys.append(
                f"Mindenkit felküldenek (átlag {_ahc_avg:.1f} mezőny-"
                "játékos fent) — a hátuk mögött üres a pálya: minden "
                "labdaszerzésetek kontrát ér, és a hosszú kapus-"
                "kidobás is fegyver ellenük.")
        elif _ahc_avg <= 4.5:
            keys.append(
                f"Biztosítva támadnak (átlag csak {_ahc_avg:.1f} "
                "mezőnyjátékos fent) — kontrát nehéz ellenük vezetni, "
                "viszont elöl emberhátrányban vannak: a fal bátran "
                "kettőzhet, a kimaradó támadójuk nem büntet.")

    # Blokk-lepattanó: mennyit ér a blokkolt lövésünk ellenük.
    if rep.brc_blocks >= 4:
        _brc_pct = 100.0 * rep.brc_recovered / rep.brc_blocks
        if _brc_pct >= 60.0:
            keys.append(
                f"A blokk után a labdát is megszerzik "
                f"({rep.brc_recovered}/{rep.brc_blocks} lepattanó az "
                "övék) — a blokkjukba lőtt labda egyenlő a "
                "labdavesztéssel: a blokk-kar mellett kell ellőni, "
                "vagy be kell játszani, nem átlőni rajtuk.")
        elif _brc_pct <= 30.0:
            keys.append(
                f"A blokkjaik visszahullanak (csak "
                f"{rep.brc_recovered}/{rep.brc_blocks} lepattanót "
                "szereztek meg) — a blokkolt lövés után azonnal "
                "támadjatok újra: a lepattanó a tiétek, és a faluk "
                "ilyenkor még rendezetlen.")

    # Ziccer-befejezők: kinél kell a helyzetet már előbb megelőzni.
    _bcf_acc: dict = {}
    for _bcf_pr in (rep.bcf_players or []):
        _bcf_rec = _bcf_acc.setdefault(_bcf_pr["player_id"], [0, 0])
        _bcf_rec[0] += _bcf_pr["chances"]
        _bcf_rec[1] += _bcf_pr["goals"]
    for _bcf_pid, (_bcf_c, _bcf_g) in sorted(_bcf_acc.items(),
                                             key=lambda kv: -kv[1][0]):
        if _bcf_c < 3:
            continue
        _bcf_pct = 100.0 * _bcf_g / _bcf_c
        if _bcf_pct >= 80.0:
            keys.append(
                f"Ziccer-biztos befejezőjük a(z) {_bcf_pid} "
                f"azonosítójú ({_bcf_g}/{_bcf_c} nagy helyzet) — nála "
                "a helyzetet már a kialakulása előtt kell megelőzni: "
                "korábbi besegítés, mert amit a hatoson megkap, az "
                "gól.")
            break
        if _bcf_pct <= 40.0:
            keys.append(
                f"A(z) {_bcf_pid} azonosítójú a nagy helyzeteket is "
                f"kihagyja ({_bcf_g}/{_bcf_c}) — a fal vállalhatja, "
                "hogy inkább őt engedi helyzetbe a veszélyesebb "
                "társak helyett.")
            break

    # Hetes utáni percek: duplán ér-e az ellenük megítélt hetes.
    if rep.psl_sevens >= 3 and rep.psl_extra >= 2:
        keys.append(
            f"A hetes utáni percben is büntethetők ({rep.psl_sevens} "
            f"adott hetesük után {rep.psl_extra} további gólt kaptak) "
            "— a hetes körüli leállás megtöri a védekezés-ritmusukat: "
            "a hetesetek utáni támadást is kész figurával játsszátok "
            "meg, amíg rendezetlenek.")

    # Labda-forgatás: hol érdemes kettőzni és merre terelni.
    _cir_total = rep.cir_left + rep.cir_right
    if _cir_total >= 20:
        _cir_lp = 100.0 * rep.cir_left / _cir_total
        if _cir_lp >= 60.0 or _cir_lp <= 40.0:
            _cir_dir = "balra" if _cir_lp >= 60.0 else "jobbra"
            keys.append(
                f"Egy irányba forgatnak ({_cir_dir} megy az "
                f"oldalpasszaik {max(_cir_lp, 100 - _cir_lp):.0f}%-a) "
                "— a kettőzés a forgás végpontján ér a legtöbbet, és "
                "az ellenirányba terelés (a megszokott sáv zárása) "
                "kizökkenti a ritmusukat.")

    # Elzárás-páros: melyik kettősükre kell párban készülni.
    _scp_acc: dict = {}
    for _scp_pr in (rep.scp_pairs or []):
        _scp_key = (_scp_pr["setter_id"], _scp_pr["shooter_id"])
        _scp_acc[_scp_key] = _scp_acc.get(_scp_key, 0) + _scp_pr["shots"]
    if _scp_acc:
        _scp_top = max(_scp_acc, key=lambda k: _scp_acc[k])
        if _scp_acc[_scp_top] >= 3:
            keys.append(
                f"Bejáratott elzárás-párosuk van (a(z) {_scp_top[0]} "
                f"azonosítójú zár a(z) {_scp_top[1]} azonosítójúnak, "
                f"{_scp_acc[_scp_top]} közös lövés) — párban "
                "védekezzetek ellene: az elzáró őrzője előre szól, a "
                "lövő őrzője pedig az elzárás előtt lép ki, hogy ne "
                "szoruljon mögé.")

    # Szélső-kifutás: érdemes-e szélesen játszani ellenük.
    if rep.wco_shots >= 4:
        _wco_avg = rep.wco_sum_m / rep.wco_shots
        if _wco_avg >= 2.5:
            keys.append(
                f"Későn érnek ki a szélre (átlag {_wco_avg:.1f} m-re "
                "volt a védőjük a lövő szélsőtől) — a széljáték ingyen "
                "terem ellenük: gyors oldalváltásokkal hordjatok "
                "labdát a szélsőitekre.")
        elif _wco_avg <= 1.2:
            keys.append(
                f"Zárják a szélsőt (átlag {_wco_avg:.1f} m-en volt a "
                "védőjük a lövéskor) — a szélső-bejátszás zsákutca: a "
                "szélre húzott védelmük mögött a beállót keressétek.")

    # Csend-törők: kihez menekül a labda, amikor áll a szekerük.
    _drb_per: dict = {}
    for _drb_pr in (rep.drb_players or []):
        _drb_per[_drb_pr["player_id"]] = (
            _drb_per.get(_drb_pr["player_id"], 0) + _drb_pr["breaks"])
    if _drb_per:
        _drb_pid = max(_drb_per, key=lambda k: _drb_per[k])
        if _drb_per[_drb_pid] >= 2:
            keys.append(
                f"Van válság-lövőjük: a(z) {_drb_pid} azonosítójú "
                f"{_drb_per[_drb_pid]} gólcsendet tört meg — a saját "
                "sorozatotok alatt őt fogjátok a legszorosabban: "
                "hozzá menekül a labda, amikor áll a szekerük.")

    # Forró kéz: kire kell azonnal reagálni az első gólja után.
    _hh_per: dict = {}
    for _hh_st in (rep.hh_streaks or []):
        _hh_rec = _hh_per.setdefault(
            _hh_st["player_id"], {"streaks": 0, "longest": 0})
        _hh_rec["streaks"] += 1
        _hh_rec["longest"] = max(_hh_rec["longest"], _hh_st["length"])
    _hh_cands = [(pid, r) for pid, r in _hh_per.items()
                 if r["streaks"] >= 2 or r["longest"] >= 3]
    if _hh_cands:
        _hh_pid, _hh_top = max(_hh_cands,
                               key=lambda kv: (kv[1]["streaks"],
                                               kv[1]["longest"]))
        keys.append(
            f"Van sorozatlövőjük: a(z) {_hh_pid} azonosítójú "
            f"{_hh_top['streaks']} gólsorozatot dobott (leghosszabb: "
            f"{_hh_top['longest']}) — az ELSŐ gólja után azonnal "
            "reagáljatok: őrzés-váltás vagy kettőzés rá, mielőtt "
            "lendületbe jönne.")

    # Kapus-hidegedés: érdemes-e éheztetni a kapusukat.
    if rep.gcs_cold_faced >= 4 and rep.gcs_warm_faced >= 4:
        _gcs_c = 100.0 * rep.gcs_cold_saves / rep.gcs_cold_faced
        _gcs_w = 100.0 * rep.gcs_warm_saves / rep.gcs_warm_faced
        if _gcs_w - _gcs_c >= 15.0:
            keys.append(
                f"Hidegen sebezhető a kapusuk (hosszú csend után "
                f"{_gcs_c:.0f}%, ritmusban {_gcs_w:.0f}% a "
                "védés-aránya) — éheztessétek: hosszú, türelmes "
                "birtoklás után jöjjön a kidolgozott lövés, pont "
                "amikor rég nem volt dolga.")
        elif _gcs_c - _gcs_w >= 15.0:
            keys.append(
                f"Hidegen is stabil a kapusuk ({_gcs_c:.0f}% a "
                "hosszú csendek után) — az éheztetés nála nem "
                "működik: inkább a sorozatos, gyors befejezésekkel "
                "kell ritmusból kizökkenteni.")

    # Fal-magasság elleni játék: milyen magas fallal védekezzetek.
    if (rep.avw_high_attacks >= 5 and rep.avw_deep_attacks >= 5):
        _avw_h = 100.0 * rep.avw_high_goals / rep.avw_high_attacks
        _avw_d = 100.0 * rep.avw_deep_goals / rep.avw_deep_attacks
        if _avw_h - _avw_d <= -20.0:
            keys.append(
                f"A felfutó fal megfogja őket (magas fal ellen "
                f"{_avw_h:.0f}%, mély ellen {_avw_d:.0f}% a "
                "gólarányuk) — bátran lépjetek ki és védekezzetek "
                "magasan: nincs válaszuk a nyomásra.")
        elif _avw_h - _avw_d >= 20.0:
            keys.append(
                f"A felfutó falat megbüntetik (magas fal ellen "
                f"{_avw_h:.0f}%, mély ellen {_avw_d:.0f}% a "
                "gólarányuk) — ellenük a mély, kompakt fal a "
                "biztonságos terv: a kilépések mögé azonnal "
                "betörnek vagy átemelik.")

    # Kontra-forrás: melyik pillanatban kell megölni a kontrájukat.
    _bsrc_total = sum((rep.bsrc_sources or {}).values())
    if _bsrc_total >= 4 and rep.bsrc_sources:
        _bsrc_items = sorted(rep.bsrc_sources.items(),
                             key=lambda kv: -kv[1])
        _bsrc_src, _bsrc_n = _bsrc_items[0]
        _bsrc_tie = (len(_bsrc_items) > 1
                     and _bsrc_items[1][1] == _bsrc_n)
        if 100.0 * _bsrc_n / _bsrc_total >= 50.0 and not _bsrc_tie:
            _bsrc_advice = {
                "védés": ("a lövésetek pillanatában induljon a "
                          "visszarendeződés, és a kapus-indítás "
                          "sávját zárjátok"),
                "kihagyott lövés": ("a lepattanó-fegyelem dönt: "
                                    "kimaradt lövés után senki nem "
                                    "áll meg, és a kidobást lassítani "
                                    "kell"),
                "labdaszerzés": ("átmenetben tilos a keresztpassz, és "
                                 "a labdabiztonság mindenek előtt"),
            }[_bsrc_src]
            keys.append(
                f"A kontráik főleg ebből indulnak: {_bsrc_src} "
                f"({_bsrc_n}/{_bsrc_total} lerohanás) — {_bsrc_advice}.")

    # Kapus-gól veszély: szabad-e üresen hagyni a kaputokat.
    if rep.gkg_attempts >= 1:
        keys.append(
            f"Gólveszélyes a kapusuk ({rep.gkg_attempts} kapura "
            f"dobás, {rep.gkg_goals} gól) — a 7 a 6-otok alatt mindig "
            "legyen kijelölt visszafutó, aki labdavesztésnél elsőként "
            "ér a kapu síkjába, és a kapus-kidobásnál is zárjátok a "
            "hosszú sávot.")

    # Hosszú állás utáni játék: kié az újraindítás pillanata.
    if rep.lbr_breaks >= 2:
        _lbr_diff = rep.lbr_for - rep.lbr_against
        if _lbr_diff <= -2:
            keys.append(
                f"A hosszú állások kizökkentik őket (a megszakítások "
                f"utáni mérlegük {rep.lbr_for}-{rep.lbr_against}) — "
                "minden sérülés-szünet és technikai állás a ti "
                "pillanatotok: kész figurával és letámadással "
                "jöjjetek ki belőle, amíg ők hidegek.")
        elif _lbr_diff >= 2:
            keys.append(
                f"A hosszú állások után meglódulnak (a megszakítások "
                f"utáni mérlegük {rep.lbr_for}-{rep.lbr_against}) — "
                "az újraindítás utáni első védekezés extra figyelmet "
                "kapjon, és az állás alatt a pad is mozogjon: ne ők "
                "kapcsoljanak vissza elsőnek.")

    # Hajrá-labdabirtoklás: kit kell kettőzni a végjátékban.
    if rep.cbh_frames >= 200 and rep.cbh_players:
        _cbh_top = max(rep.cbh_players, key=lambda r: r["frames"])
        if 100.0 * _cbh_top["frames"] / rep.cbh_frames >= 35.0:
            keys.append(
                f"Egy kézben van a végjátékuk: a hajrá labdás idejének "
                f"nagy részét a(z) {_cbh_top['player_id']} azonosítójú "
                "viszi — a hajrá-kettőzés rá menjen: ha tőle elveszitek "
                "a labdát, vagy korán labdához sem engeditek, a záró "
                "figuráik el sem indulnak.")

    # Negyedóra-profil: mikorra időzítsük az időkérést és a friss sort.
    if rep.qp_min >= 40.0:
        _qp_diffs = {q: rep.qp_for.get(q, 0) - rep.qp_against.get(q, 0)
                     for q in ("1", "2", "3", "4")}
        _qp_best = max(_qp_diffs, key=lambda q: _qp_diffs[q])
        _qp_worst = min(_qp_diffs, key=lambda q: _qp_diffs[q])
        if _qp_diffs[_qp_best] >= 3:
            keys.append(
                f"A(z) {_qp_best}. negyedóra az övék "
                f"(+{_qp_diffs[_qp_best]} ott a gólkülönbségük) — az "
                "erős szakaszuk ELŐTT jöjjön a saját időkérés és a "
                "friss sor: ne az ő lendületükben kelljen kapkodni.")
        if _qp_diffs[_qp_worst] <= -3:
            keys.append(
                f"A(z) {_qp_worst}. negyedórában esnek szét "
                f"({_qp_diffs[_qp_worst]} ott a gólkülönbségük) — oda "
                "kell tempót időzíteni: pörgetett cserék és gyors "
                "középkezdések, amíg tart a hullámvölgyük.")

    # Beálló-őr: kire épül a belső védekezésük.
    if rep.pvg_frames >= 300 and rep.pvg_guards:
        _pvg_top = max(rep.pvg_guards, key=lambda r: r["frames"])
        if 100.0 * _pvg_top["frames"] / rep.pvg_frames >= 60.0:
            keys.append(
                f"Egy ember őrzi a beállótokat: a(z) "
                f"{_pvg_top['player_id']} azonosítójú viszi az "
                "őrzés-idő nagy részét — az elzárást rá kell vinni: "
                "ha őt kihúzzátok, a beálló felszabadul, és a "
                "besegítés rendje is borul.")

    # Időkérés-csomag: mire számíts az időkérésük után.
    if rep.tsc_timeouts >= 2:
        _tsc_pct = 100.0 * rep.tsc_with_subs / rep.tsc_timeouts
        if _tsc_pct >= 70.0:
            keys.append(
                f"Az időkérésük cserével jár ({rep.tsc_with_subs}/"
                f"{rep.tsc_timeouts} időkérésnél új ember jött) — az "
                "időkérésük után frissítsétek a párosítást: az első "
                "támadásukban friss lábú ember érkezik, a kettőzés "
                "és az őrzés az új emberre menjen.")
        elif _tsc_pct <= 30.0:
            keys.append(
                f"Az időkérésük tiszta taktika ({rep.tsc_timeouts} "
                "időkérésből szinte egyik sem járt cserével) — "
                "ugyanazok jönnek vissza, de új figurával: az "
                "időkérésük utáni első támadásnál a fal extra "
                "figyelmet kapjon, és hangosan menjen az egyeztetés.")

    # Lövés-választás állás szerint: önmagát védi-e a vezetésetek.
    if rep.sqs_trail_shots >= 5 and rep.sqs_other_shots >= 5:
        _sqs_t = rep.sqs_trail_sum_xg / rep.sqs_trail_shots
        _sqs_o = rep.sqs_other_sum_xg / rep.sqs_other_shots
        if _sqs_o - _sqs_t >= 0.08:
            keys.append(
                f"Hátrányban elkapkodják a lövéseket (az átlagos "
                f"helyzet-értékük {_sqs_o:.2f}-ról {_sqs_t:.2f}-ra "
                "esik) — ha vezettek, a meccs önmagát nyeri: nyugodt "
                "fal, semmi kockázat, a rossz lövéseik nektek "
                "dolgoznak.")
        elif _sqs_t - _sqs_o >= 0.08:
            keys.append(
                f"Hátrányban is türelmesek (az átlagos "
                f"helyzet-értékük {_sqs_t:.2f} hátrányban is) — a "
                "vezetés ellenük sosem biztonságos: a hajrában is "
                "teljes védekezés-fegyelem kell, mert nem fognak "
                "kapkodni.")

    # Kapus állás szerint: mennyit ér a kapusuk, ha vezettek.
    if rep.gks_trail_faced >= 4 and rep.gks_other_faced >= 4:
        _gks_t = 100.0 * rep.gks_trail_saves / rep.gks_trail_faced
        _gks_o = 100.0 * rep.gks_other_saves / rep.gks_other_faced
        if _gks_t - _gks_o >= 15.0:
            keys.append(
                f"Hátrányban feljavul a kapusuk ({_gks_t:.0f}% a "
                f"védés-aránya a szokásos {_gks_o:.0f}% helyett) — ha "
                "vezettek, csak kidolgozott helyzetet lőjetek rá: a "
                "bravúrjaiból lendület lesz, és a rossz lövés őket "
                "hozza vissza a meccsbe.")
        elif _gks_o - _gks_t >= 15.0:
            keys.append(
                f"Hátrányban összeesik a kapusuk (csak {_gks_t:.0f}% "
                f"a védés-aránya a szokásos {_gks_o:.0f}% helyett) — "
                "ha vezettek, bátran jöhet a távoli lövés is: a "
                "megingott kapus minden újabb góllal tovább csúszik.")

    # Szorult játék: mi történik velük, ha vezettek ellenük.
    if rep.wbs_trail_frames >= 100 and rep.wbs_other_frames >= 100:
        _wbs_t = rep.wbs_trail_sum_m / rep.wbs_trail_frames
        _wbs_o = rep.wbs_other_sum_m / rep.wbs_other_frames
        if _wbs_o - _wbs_t >= 2.0:
            keys.append(
                f"Hátrányban beszűkül a támadásuk ({_wbs_o:.0f} m-ről "
                f"{_wbs_t:.0f} m-re esik a terjedelme) — ha vezettek, "
                "tömörítsétek a falat: a szélsőik maguktól "
                "kikapcsolódnak, és az erőltetett középső megoldásaik "
                "a blokkotokba futnak.")
        elif _wbs_t - _wbs_o >= 2.0:
            keys.append(
                f"Hátrányban kinyílik a támadásuk ({_wbs_o:.0f} m-ről "
                f"{_wbs_t:.0f} m-re nő a terjedelme) — ha vezettek, a "
                "szélső-védelem és a kifutás dönt: a "
                "visszakapaszkodásuk a szélekről jön.")

    # Visszaállás: mit kezdjünk a kiállításaik leteltével.
    if rep.ppp_returns >= 2:
        _ppp_diff = rep.ppp_for - rep.ppp_against
        if _ppp_diff <= -2:
            keys.append(
                f"A visszaállásnál megzavarodnak (a kiállításaik "
                f"letelte utáni perc mérlege {rep.ppp_for}-"
                f"{rep.ppp_against}) — a lejáró kiállításuk a ti "
                "támadás-jelzésetek: időzítsétek úgy, hogy a "
                "visszaérő, hideg emberük zónájába menjen az első "
                "támadás.")
        elif _ppp_diff >= 2:
            keys.append(
                f"A visszaálló emberrel feltámadnak (a kiállításaik "
                f"letelte utáni perc mérlege {rep.ppp_for}-"
                f"{rep.ppp_against}) — a visszaérés utáni első "
                "támadásukat kell megfogni: ott dől el, lendületet "
                "vesznek-e, ezért oda időkérést is megér.")

    # Poszt-hibák: melyik passzsávban érdemes zavarni.
    _tbr_total = sum((rep.tbr_roles or {}).values())
    if _tbr_total >= 6 and rep.tbr_roles:
        _tbr_items = sorted(rep.tbr_roles.items(), key=lambda kv: -kv[1])
        _tbr_poszt, _tbr_n = _tbr_items[0]
        _tbr_tie = len(_tbr_items) > 1 and _tbr_items[1][1] == _tbr_n
        if 100.0 * _tbr_n / _tbr_total >= 40.0 and not _tbr_tie:
            keys.append(
                f"A labdaeladásaik a(z) {_tbr_poszt} posztról jönnek "
                f"({_tbr_n}/{_tbr_total} eladás) — ott érdemes "
                "zavarni: a beállónál a bejátszás-vonalra lépés, az "
                "irányítónál a felső kettőzés, a szélsőnél a "
                "szélső-bejátszások vadászata termel labdát.")

    # Futás-mérleg: vállalható-e velük a futóverseny.
    if rep.dbt_min >= 10.0 and rep.dbt_m > 0 and rep.dbt_opp_m > 0:
        if rep.dbt_m >= rep.dbt_opp_m * 1.10:
            keys.append(
                f"Túlfutják az ellenfeleiket "
                f"({rep.dbt_m / rep.dbt_min:.0f} m/perc a mezőny-"
                "futásmennyiségük) — velük nem szabad futóversenyt "
                "vállalni: lassított tempó, felállt fal és hosszú "
                "támadások, hogy a futóerejük ne érjen semmit.")
        elif rep.dbt_m <= rep.dbt_opp_m * 0.90:
            keys.append(
                f"Túlfutja őket az ellenfél (csak "
                f"{rep.dbt_m / rep.dbt_min:.0f} m/perc a mezőny-"
                "futásmennyiségük) — a tempó a fegyver ellenük: gyors "
                "középkezdés, korai indítások és második hullám, mert "
                "a visszazárásuk rendre késik.")

    # Egyirányú játékosok: sebezhető-e a támadás-védekezés váltásuk.
    _phs_meas = [r for r in (rep.phs_players or [])
                 if r["frames"] >= 1500]
    _phs_def = [r for r in _phs_meas
                if 100.0 * r["def_frames"] / r["frames"] >= 75.0]
    _phs_atk = [r for r in _phs_meas
                if 100.0 * r["def_frames"] / r["frames"] <= 25.0]
    if _phs_def and _phs_atk:
        keys.append(
            f"Váltott sorokkal játszanak (a(z) "
            f"{_phs_def[0]['player_id']} azonosítójú csak védekezik, "
            f"a(z) {_phs_atk[0]['player_id']} azonosítójú csak "
            "támad) — a csere pillanatában sebezhetők: a gyors "
            "középkezdés és a szerzés utáni azonnali indítás rossz "
            "embereket talál a pályán, a fent ragadt támadójukat "
            "pedig meg kell támadni.")

    # Sprint-veszély: kire kell a névre szóló fékező-feladat.
    _spt_rows = rep.spt_players or []
    _spt_total = sum(r["sprints"] for r in _spt_rows)
    if _spt_total >= 10 and _spt_rows:
        _spt_top = max(_spt_rows, key=lambda r: r["sprints"])
        if 100.0 * _spt_top["sprints"] / _spt_total >= 30.0:
            keys.append(
                f"Kijelölt kontra-emberük van (a(z) "
                f"{_spt_top['player_id']} azonosítójú futotta a "
                f"csapat {_spt_total} sprintjéből "
                f"{_spt_top['sprints']}-t) — labdavesztésnél az első "
                "dolog az Ő útjának lezárása: névre szóló fékező-"
                "feladat, és tilos őt a fal mögé engedni.")

    # Hetesre cserélt kapus: kire készüljön a hetes-lövőnk.
    if rep.svk_swaps >= 2:
        keys.append(
            f"Hetesre kapust cserélnek (az ellenük ítélt "
            f"{rep.svk_sevens} hetesből {rep.svk_swaps}-t frissen "
            "beállt kapus várt) — a hetes-lövőtök a BEUGRÓ kapus "
            "szokásaira készüljön, ne a kezdőére, és a lövést ki "
            "lehet várni: hadd álljon vissza előbb a specialista.")

    # Kilépő védő: hol nyílik a tér a faluk mögött.
    _adv_rows = [r for r in (rep.adv_players or [])
                 if r["frames"] >= 100]
    if len(_adv_rows) >= 3:
        _adv_rows = sorted(_adv_rows,
                           key=lambda r: -(r["depth_sum_m"]
                                           / r["frames"]))
        _adv_top = _adv_rows[0]
        _adv_others = _adv_rows[1:]
        _adv_base = (sum(r["depth_sum_m"] for r in _adv_others)
                     / max(1, sum(r["frames"] for r in _adv_others)))
        _adv_gap = _adv_top["depth_sum_m"] / _adv_top["frames"] - _adv_base
        if _adv_gap >= 2.5:
            keys.append(
                f"Kilépő védővel játszanak (a(z) "
                f"{_adv_top['player_id']} azonosítójú "
                f"{_adv_gap:.1f} méterrel a társai előtt áll) — a "
                "háta mögött nyílik a tér: elzárást kell rá vinni, "
                "és a mögé befutó emberrel 2 az 1-et játszani.")

    # Középkezdés-átvevő: van-e névre szóló célpontja a gól utáni
    # letámadásnak.
    if rep.rst_restarts >= 4 and rep.rst_players:
        _rst_top = max(rep.rst_players, key=lambda pr: pr["takes"])
        if 100.0 * _rst_top["takes"] / rep.rst_restarts >= 50.0:
            keys.append(
                f"Fix középkezdés-emberük van (a kapott gól után "
                f"{_rst_top['takes']}/{rep.rst_restarts} újraindítást "
                f"a(z) {_rst_top['player_id']} azonosítójú vett át) — "
                "a gól utáni letámadásnak névre szóló célpontja van: "
                "őt kell lefogni a felezőnél, és a középkezdésük "
                "megáll.")

    # Váltópárok: olvasható-e előre a cseréjük.
    if rep.swp_swaps >= 4 and rep.swp_pairs:
        _swp_top = max(rep.swp_pairs, key=lambda pr: pr["count"])
        if _swp_top["count"] >= 3:
            keys.append(
                f"Kiszámítható a váltópárjuk (a(z) "
                f"{_swp_top['out_id']} azonosítójút rendre a(z) "
                f"{_swp_top['in_id']} azonosítójú váltja, "
                f"{_swp_top['count']} alkalommal) — a beálló emberre "
                "kész B-terv legyen: amikor a kulcsemberük fárad, "
                "tudni lehet, ki jön, és már a csere előtt át lehet "
                "állni az ő gyengéjére.")

    # Visszahozott támadások: rámozduljon-e a fal az első betörésre.
    if rep.pb_entries >= 6:
        _pb_pct = 100.0 * rep.pb_pullbacks / rep.pb_entries
        if _pb_pct >= 45.0:
            keys.append(
                f"Behúzzák, aztán visszahozzák a labdát (a "
                f"{rep.pb_entries} betörésükből {rep.pb_pullbacks} "
                "lövés nélküli visszahozás) — a fal kivárhat: nem "
                "kell az első betörésre rámozdulni, a türelmes zárás "
                "kihozza belőlük a passzív jelet.")
        elif _pb_pct <= 15.0:
            keys.append(
                f"Az első betörésből lezárnak (a {rep.pb_entries} "
                f"betörésükből csak {rep.pb_pullbacks} visszahozás) — "
                "az első belépést kell megállítani: korai besegítés, "
                "és ha kell, korai szabálytalanság a 9-esen, mielőtt "
                "lendületbe jönnének.")

    # Szerzés utáni indítás: mi történik, ha eladjuk a labdát.
    if rep.stl_steals >= 6:
        _stl_pct = 100.0 * rep.stl_fwd / rep.stl_steals
        if _stl_pct >= 60.0:
            keys.append(
                f"Szerzés után azonnal indítanak (a {rep.stl_steals} "
                f"szerzésükből {rep.stl_fwd} után ment rögtön előre a "
                "labda) — a labdavesztés pillanatára kész terv kell: "
                "kijelölt fékező ember, a többiek sprintben hátra, és "
                "senki nem áll meg reklamálni.")
        elif _stl_pct <= 25.0:
            keys.append(
                f"Szerzés után biztosítanak (a {rep.stl_steals} "
                f"szerzésükből csak {rep.stl_fwd} után ment előre a "
                "labda) — labdavesztés után van idő rendezni a "
                "letámadást: az első hátrapasszukra rá lehet lépni, "
                "és a szerzett labdát nyugodtan vissza lehet nyerni.")

    # Hetes-fáradás: mikor jön az ajándék a testre vitt labdáért.
    if rep.s7f_fh + rep.s7f_sh >= 4:
        if rep.s7f_sh - rep.s7f_fh >= 2:
            keys.append(
                f"A második félidőben adják a heteseket ({rep.s7f_fh} "
                f"az elsőben, {rep.s7f_sh} a másodikban) — fáradva "
                "már kézzel védenek: a szünet után be kell vinni a "
                "labdát a testre, a beállós és a betörés ilyenkor "
                "hetest ér.")
        elif rep.s7f_fh - rep.s7f_sh >= 2:
            keys.append(
                f"Az elején adják a heteseket ({rep.s7f_fh} az "
                f"elsőben, {rep.s7f_sh} a másodikban) — hidegen "
                "kapkodnak: az első percekben kell a beállóst és a "
                "betörést erőltetni, amíg össze nem áll a faluk.")

    # Fal-fáradás: mikorra időzítsük a belső játékot.
    if rep.wf_fh_shots >= 5 and rep.wf_sh_shots >= 5:
        _wf_fh = rep.wf_fh_sum_xga / rep.wf_fh_shots
        _wf_sh = rep.wf_sh_sum_xga / rep.wf_sh_shots
        if _wf_sh - _wf_fh >= 0.08:
            keys.append(
                f"A második félidőre kinyílik a faluk (a kapott "
                f"lövéseik átlagos helyzet-értéke {_wf_fh:.2f}-ról "
                f"{_wf_sh:.2f}-ra nő) — a belső játékot (beállós, "
                "betörés) a második félidőre tartogassátok: az elején "
                "a kinti lövés is jó, a végén már befelé kell menni.")
        elif _wf_fh - _wf_sh >= 0.08:
            keys.append(
                f"A második félidőre áll össze a faluk (a kapott "
                f"lövéseik átlagos helyzet-értéke {_wf_fh:.2f}-ról "
                f"{_wf_sh:.2f}-ra esik) — az első félidőben kell "
                "megszerezni az előnyt: a szünet után bezár a bolt, "
                "ott már a türelmes figura-játék marad.")

    # Pad-gólok: fárasztható-e a góltermelésük.
    if rep.ben_goals >= 6:
        _ben_pct = 100.0 * rep.ben_bench / rep.ben_goals
        if _ben_pct <= 10.0:
            keys.append(
                f"Csak a kezdőik termelnek (a {rep.ben_goals} lövőhöz "
                f"köthető góljukból {rep.ben_bench} jött a padról) — "
                "fárasszátok őket: pörgetett tempó és letámadás "
                "mellett a hat emberük a második félidőre elfogy, és "
                "a padon nincs, aki átvegye a terhet.")
        elif _ben_pct >= 35.0:
            keys.append(
                f"A kispaduk is termel (a góljaik {_ben_pct:.0f}%-a "
                "padról beállóktól jön) — a tempó önmagában nem töri "
                "meg őket: minden sorukra névre szóló párosítás-terv "
                "kell, a cseréik után is tartani kell a kijelölt "
                "embereket.")

    # Labdaszerzés-típus: mitől kell óvni a saját passzjátékunkat.
    if rep.stt_steals >= 6:
        _stt_pct = 100.0 * rep.stt_int / rep.stt_steals
        if _stt_pct >= 60.0:
            keys.append(
                f"A passzsávakat zárják (a {rep.stt_steals} "
                f"szerzésükből {rep.stt_int} röptében elfogott passz) "
                "— keresztbe lebegtetni tilos ellenük: rövid, "
                "közvetlen passzok és betörések kellenek, a hosszú "
                "átemelést hagyjátok el.")
        elif _stt_pct <= 25.0:
            keys.append(
                f"Testre mennek szerelni (a {rep.stt_steals} "
                f"szerzésükből csak {rep.stt_int} passz-elfogás) — a "
                "gyors labdajáratás a fegyver ellenük: a labda "
                "hamarabb menjen tovább, mint ahogy a kontakt "
                "megérkezik, és a keresztpassz nyugodtan vállalható.")

    # Kapott helyzetek minősége: befelé vagy kívülről támadjunk.
    if rep.ccq_shots >= 8:
        _ccq_avg = rep.ccq_sum_xga / rep.ccq_shots
        if _ccq_avg >= 0.35:
            keys.append(
                f"Nagy helyzeteket engednek (a rájuk jövő "
                f"{rep.ccq_shots} lövés átlagos helyzet-értéke "
                f"{_ccq_avg:.2f}) — befelé kell játszani ellenük: "
                "beállós, áttörés, elzárás után kapott labda, mert a "
                "faluk beengedi a hatos közelébe a támadót.")
        elif _ccq_avg <= 0.22:
            keys.append(
                f"Csak nehéz helyzeteket engednek (a rájuk jövő "
                f"{rep.ccq_shots} lövés átlagos helyzet-értéke csak "
                f"{_ccq_avg:.2f}) — a 9 méteres lövés ajándék nekik: "
                "keresztmozgással és elzárással kell embert kihúzni, "
                "és a kapus mögé kerülni.")

    # Félidő-zárás: mit kezdenek a dudaszó előtti utolsó labdával.
    if rep.clo_attacks >= 3:
        _clo_pct = 100.0 * rep.clo_goals / rep.clo_attacks
        if _clo_pct >= 50.0:
            keys.append(
                f"Jól kezelik a záró labdát (a félidők utolsó "
                f"percében {rep.clo_attacks} támadásból "
                f"{rep.clo_goals} gól) — a félidő végén nem szabad "
                "idő előtt lőni ellenük: az órát ki kell húzni, hogy "
                "ne kapjanak még egy záró támadást.")
        elif _clo_pct <= 15.0:
            keys.append(
                f"Elpuskázzák a záró labdát (a félidők utolsó "
                f"percében {rep.clo_attacks} támadásból csak "
                f"{rep.clo_goals} gól) — nyugodtan vissza lehet adni "
                "nekik az utolsó labdát: a záró támadásuk ajándék, "
                "nem kockázat.")

    # Lerohanás-hatékonyság: veszélyes-e rájuk engedni a kontrát.
    if rep.fbc_breaks >= 5:
        _fbc_pct = 100.0 * rep.fbc_goals / rep.fbc_breaks
        if _fbc_pct >= 65.0:
            keys.append(
                f"Élesen fejezik be a kontrát ({rep.fbc_breaks} "
                f"lerohanásból {rep.fbc_goals} gól, "
                f"{_fbc_pct:.0f}%) — a visszarendeződés fegyelme "
                "dönt ellenük: kijelölt fékező ember, és lövés után "
                "senki nem marad elöl a kipattanóra.")
        elif _fbc_pct <= 35.0:
            keys.append(
                f"Elpuskázzák a kontrát ({rep.fbc_breaks} "
                f"lerohanásból csak {rep.fbc_goals} gól, "
                f"{_fbc_pct:.0f}%) — a kontra náluk ajándék: "
                "nyugodtan rájuk lehet engedni, mert a felállt "
                "támadásuk a veszélyesebb.")

    # Félidő-nyitás: mennyire fontosak ellenük az első percek.
    if rep.ho_for + rep.ho_against >= 4:
        _ho_diff = rep.ho_for - rep.ho_against
        if _ho_diff >= 2:
            keys.append(
                f"Jól nyitják a félidőket ({rep.ho_for}-"
                f"{rep.ho_against} a mérlegük a félidők első öt "
                "percében) — ellenük az első öt perc a "
                "legfontosabb: biztos, hibátlan játék kell, mert egy "
                "korai szériával elszaladnak.")
        elif _ho_diff <= -2:
            keys.append(
                f"Lassan indulnak ({rep.ho_for}-{rep.ho_against} a "
                "mérlegük a félidők első öt percében) — pont az "
                "első öt percben kell rámenni: ott szerezhető meg a "
                "vezetés, és utána már ők kergetnek.")

    # Időkérés utáni védekezés: rohanjunk vagy várjunk az időkérésük
    # után.
    if rep.tfd_timeouts >= 3:
        _tfd_pct = 100.0 * rep.tfd_conceded / rep.tfd_timeouts
        if _tfd_pct >= 60.0:
            keys.append(
                f"Az időkérésük után szivárog a faluk (az "
                f"időkéréseik {_tfd_pct:.0f}%-a után gól esett az "
                "első rohamból) — a megszakítás náluk nem a "
                "védekezésről szól: az újraindítás után azonnal, "
                "felállás nélkül kell támadni ellenük.")
        elif _tfd_pct <= 20.0:
            keys.append(
                f"Az időkérésük után friss a faluk (az időkéréseik "
                f"csak {_tfd_pct:.0f}%-a után kaptak gólt az első "
                "rohamból) — ott a gyors roham veszteség: rendezetten "
                "kell felállni és kivárni az első hibájukat.")

    # Gól utáni letámadás: mire számítson a kihozatalunk a kapott gól
    # után.
    if (rep.pag_after_frames >= 60 and rep.pag_base_frames >= 60):
        _pag_a = rep.pag_after_sum_m / rep.pag_after_frames
        _pag_b = rep.pag_base_sum_m / rep.pag_base_frames
        if _pag_a - _pag_b >= 1.5:
            keys.append(
                f"Saját góljuk után letámadnak (a faluk {_pag_a:.1f} "
                f"m-en áll a szokásos {_pag_b:.1f} m helyett) — a "
                "kapott gól utáni kihozatalt előre meg kell tervezni: "
                "hosszú indítás a kapustól vagy egy előre kilépő, "
                "biztos kezű átvevő, és senki ne induljon el a "
                "középkezdésre bemelegítetlenül.")
        elif _pag_b - _pag_a >= 1.5:
            keys.append(
                f"Saját góljuk után visszahúzódnak (a faluk csak "
                f"{_pag_a:.1f} m-en áll a szokásos {_pag_b:.1f} m "
                "helyett) — pont ilyenkor lehet nyugodtan felhozni a "
                "labdát: nyerjetek időt a felállásra, és a lassú "
                "kihozatal helyett rendezett támadás jöjjön.")

    # Felhozatal-idő: mennyi idő van rendezetten felállni.
    if rep.but_cases >= 5:
        _but_avg = rep.but_sum_s / rep.but_cases
        if _but_avg >= 7.0:
            keys.append(
                f"Lassan hozzák fel a labdát (átlag {_but_avg:.1f} mp "
                "alatt érnek át a támadó térfélre) — van idő "
                "rendezetten felállni ellenük: nem a visszafutás, "
                "hanem a fal szervezése dönt, és ki lehet tolni a "
                "védekezést a 9-esre.")
        elif _but_avg <= 4.0:
            keys.append(
                f"Gyorsan hozzák fel a labdát (átlag {_but_avg:.1f} mp "
                "alatt átérnek) — a lövés pillanatában már indulni "
                "kell hátra, és kell egy kijelölt fékező ember, aki a "
                "labdást lassítja, amíg a többiek beérnek.")

    # Fedezetten lövők: kire nem kell kilépni.
    _cov_rows = [p for p in (rep.covered_shooters or [])
                 if p["shots"] >= 5
                 and 100.0 * p["covered"] / p["shots"] >= 60.0]
    if _cov_rows:
        _cov_top = _cov_rows[0]
        _cov_pct = 100.0 * _cov_top["covered"] / _cov_top["shots"]
        _cov_who = (f"{_cov_top['jersey']}-es mezszámú"
                    if _cov_top.get("jersey") is not None
                    else f"{_cov_top['player_id']} azonosítójú")
        keys.append(
            f"A(z) {_cov_who} játékosuk fedezetten is elhúzza a "
            f"ravaszt (a lövései {_cov_pct:.0f}%-a fedezett volt, "
            f"{_cov_top['covered']}/{_cov_top['shots']}) — rá nem "
            "kell kilépni: elég a blokk-kéz és a kapus mögé "
            "rendezett fal, mert alacsony értékű lövéseket ad.")

    # Pressz-érzékeny játékosok: kire kell küldeni a kettőzést.
    _psp_rows = [p for p in (rep.pressure_players or [])
                 if p["press_events"] >= 5
                 and 100.0 * p["press_to"] / p["press_events"] >= 30.0]
    if _psp_rows:
        _psp_top = _psp_rows[0]
        _psp_pct = (100.0 * _psp_top["press_to"]
                    / _psp_top["press_events"])
        _psp_who = (f"{_psp_top['jersey']}-es mezszámú"
                    if _psp_top.get("jersey") is not None
                    else f"{_psp_top['player_id']} azonosítójú")
        keys.append(
            f"A(z) {_psp_who} játékosuk pressz-érzékeny (a nyomott "
            f"döntései {_psp_pct:.0f}%-a eladás lett, "
            f"{_psp_top['press_to']}/{_psp_top['press_events']}) — rá "
            "kell küldeni a kettőzést: nála a szorítás nem kockázat, "
            "hanem labdaszerzés.")

    # Elöl szerző védők: kinek az oldalán nem szabad kihozni a labdát.
    _hsp_rows = [p for p in (rep.high_stealers or [])
                 if p["steals"] >= 3
                 and 100.0 * p["high"] / p["steals"] >= 50.0]
    if _hsp_rows:
        _hsp_top = _hsp_rows[0]
        _hsp_who = (f"{_hsp_top['jersey']}-es mezszámú"
                    if _hsp_top.get("jersey") is not None
                    else f"{_hsp_top['player_id']} azonosítójú")
        keys.append(
            f"A(z) {_hsp_who} játékosuk elöl szedi a labdákat "
            f"({_hsp_top['high']}/{_hsp_top['steals']} szerzés a "
            "támadó térfelükön) — az ő oldalán nem szabad a "
            "kihozatalt vezetni: a kapus a másik oldalra indítson, és "
            "a felhozó ne fusson a sávjába.")

    # Pontatlan lövők: kire lehet ráengedni a lövést.
    _wst_rows = [p for p in (rep.wasteful_shooters or [])
                 if p["shots"] >= 5
                 and 100.0 * p["off_target"] / p["shots"] >= 40.0]
    if _wst_rows:
        _wst_top = _wst_rows[0]
        _wst_pct = 100.0 * _wst_top["off_target"] / _wst_top["shots"]
        _wst_who = (f"{_wst_top['jersey']}-es mezszámú"
                    if _wst_top.get("jersey") is not None
                    else f"{_wst_top['player_id']} azonosítójú")
        keys.append(
            f"A(z) {_wst_who} játékosuk lövései elkerülik a kaput (a "
            f"lövései {_wst_pct:.0f}%-a, "
            f"{_wst_top['off_target']}/{_wst_top['shots']}) — rá rá "
            "lehet engedni a lövést: nála a kilépés fölösleges "
            "kockázat, a mellé lövés utáni kidobás pedig azonnali "
            "indítás nektek.")

    # Kezdő hatos: kikre kell tervezni az első támadásokat.
    _opl_rows = [p for p in (rep.opening_players or [])
                 if p["frames"] > 0][:6]
    if len(_opl_rows) >= 4:
        _opl_names = []
        for _row in _opl_rows:
            _opl_names.append(
                f"{_row['jersey']}-es" if _row.get("jersey") is not None
                else f"#{_row['player_id']}")
        keys.append(
            f"A kezdő embereik: {', '.join(_opl_names)} — az első "
            "támadásokra név szerinti terv készíthető: kire megy a "
            "kettőzés, kit engedünk lőni, és ki marad a kispadon a "
            "hajrára.")

    # Hetes-kiharcolás poszt szerint: hol tilos a kéz.
    _ser_rows = list((rep.seven_earner_roles or {}).items())
    _ser_n = sum(n for _, n in _ser_rows)
    if _ser_n >= 3 and _ser_rows:
        _ser_rows.sort(key=lambda kv: -kv[1])
        _ser_poszt, _ser_top = _ser_rows[0]
        _ser_pct = 100.0 * _ser_top / _ser_n
        _ser_tie = len(_ser_rows) > 1 and _ser_rows[1][1] == _ser_top
        if _ser_pct >= 50.0 and not _ser_tie:
            _ser_what = {
                "szélső": ("a szélső-védekezésnél tilos a kéz: csak "
                           "lábbal, testtel szabad terelni, mert a "
                           "kifutó védő karja hetest ér"),
                "beálló": ("a beállót elölről kell fogni: a hátulról "
                           "nyúlás hetest ér, ezért az elé állást "
                           "kell gyakorolni"),
                "átlövő": ("a kilépésnél a kar nem mehet a lövő "
                           "karjára: a blokk felfelé nyitott kézzel "
                           "megy, különben büntetőt ér"),
                "irányító": ("a betörésénél a segítő védőnek testtel "
                             "kell zárnia, mert a kettőzésben a kéz "
                             "hetest ér"),
            }.get(_ser_poszt,
                  "ezen a poszton kell a legfegyelmezettebb kezű "
                  "védekezés")
            keys.append(
                f"A heteseik {_ser_pct:.0f}%-át a {_ser_poszt} "
                f"posztról harcolják ki ({_ser_top}/{_ser_n}) — "
                f"{_ser_what}.")

    # Időkérés utáni első támadás: kell-e rá külön készülni.
    if rep.tfa_timeouts >= 3:
        _tfa_pct = 100.0 * rep.tfa_goals / rep.tfa_timeouts
        if _tfa_pct >= 60.0:
            keys.append(
                f"Kész figurájuk van az időkérés utánra (az "
                f"időkéréseik {_tfa_pct:.0f}%-a után gólt szereztek, "
                f"{rep.tfa_goals}/{rep.tfa_timeouts}) — arra a "
                "támadásra előre fel kell készülni: kijelölt "
                "védekezés, a beállójuk elé állás, és a kapus is "
                "tudja, ki fog lőni.")
        elif _tfa_pct <= 20.0:
            keys.append(
                f"Üres az időkérésük (az időkéréseik csak "
                f"{_tfa_pct:.0f}%-a után jött gól, "
                f"{rep.tfa_timeouts} időkérés) — nem hoz megoldást a "
                "megszakítás: elég a szokásos fal, nem kell külön "
                "készülni az utána jövő támadásukra.")

    # Kockázatos passzolók: kinek a passzsávjába kell beállni.
    _rsk_rows = [p for p in (rep.risky_passers or [])
                 if p["tries"] >= 4
                 and 100.0 * p["turnovers"] / p["tries"] >= 40.0]
    if _rsk_rows:
        _rsk_top = _rsk_rows[0]
        _rsk_pct = 100.0 * _rsk_top["turnovers"] / _rsk_top["tries"]
        _rsk_who = (f"{_rsk_top['jersey']}-es mezszámú"
                    if _rsk_top.get("jersey") is not None
                    else f"{_rsk_top['player_id']} azonosítójú")
        keys.append(
            f"A(z) {_rsk_who} játékosuk hosszú labdái elfoghatók (a "
            f"hosszú kísérletei {_rsk_pct:.0f}%-a elveszett, "
            f"{_rsk_top['turnovers']}/{_rsk_top['tries']}) — az ő "
            "passzsávjába kell beállni: a letámadás és a sávba lépés "
            "nála azonnal labdát hoz.")

    # Elzárók: kire kell a váltás-kommunikáció.
    _scs_rows = rep.screen_setters or []
    if _scs_rows and _scs_rows[0]["screens"] >= 3:
        _scs_top = _scs_rows[0]
        _scs_who = (f"{_scs_top['jersey']}-es mezszámú"
                    if _scs_top.get("jersey") is not None
                    else f"{_scs_top['player_id']} azonosítójú")
        keys.append(
            f"A(z) {_scs_who} játékosuk állítja az elzárásaikat "
            f"({_scs_top['screens']} elzárás) — az ő oldalán kell a "
            "váltás-kommunikáció: hangos váltás vagy átcsúszás, és "
            "őt elölről kell fogni, mert nélküle a lövőjük nem marad "
            "tisztán.")

    # Kapus-bemelegedés: mit ér a meccs eleje ellenük.
    if rep.gke_early_faced >= 4 and rep.gke_rest_faced >= 4:
        _gke_e = 100.0 * rep.gke_early_saves / rep.gke_early_faced
        _gke_r = 100.0 * rep.gke_rest_saves / rep.gke_rest_faced
        if _gke_r - _gke_e >= 15.0:
            keys.append(
                f"Lassan melegszik be a kapusuk (az első tíz percben "
                f"{_gke_e:.0f}%-ot fog a későbbi {_gke_r:.0f}% "
                "helyett) — a meccs elején bátran kell rá lőni: ott "
                "szerezhető olcsó gól, és a korai előny beárazza a "
                "meccset.")
        elif _gke_e - _gke_r >= 15.0:
            keys.append(
                f"Azonnal formában van a kapusuk (az első tíz percben "
                f"{_gke_e:.0f}%-ot fog a későbbi {_gke_r:.0f}% "
                "helyett) — a meccs elején nem a lövésszám, hanem a "
                "helyzet minősége dönt: türelmesen, biztos "
                "helyzetekre kell játszani.")

    # Emberhátrány-lövők: ki a kontra-fenyegetésük öt emberrel.
    _shs_rows = rep.sh_shooters or []
    if _shs_rows and _shs_rows[0]["shots"] >= 2:
        _shs_top = _shs_rows[0]
        _shs_who = (f"{_shs_top['jersey']}-es mezszámú"
                    if _shs_top.get("jersey") is not None
                    else f"{_shs_top['player_id']} azonosítójú")
        keys.append(
            f"Emberhátrányban a(z) {_shs_who} játékosuk vállalja a "
            f"befejezést ({_shs_top['shots']} lövés, "
            f"{_shs_top['goals']} gól) — emberelőnyben ő a "
            "kontra-fenyegetés: az ő oldalán kell a labdabiztonság, "
            "és mögötte maradjon egy ember biztosításban.")

    # Hajrá-hibázók: kire kell menni a döntő szakaszban.
    _ctp_rows = rep.clutch_losers or []
    if _ctp_rows and _ctp_rows[0]["turnovers"] >= 2:
        _ctp_top = _ctp_rows[0]
        _ctp_who = (f"{_ctp_top['jersey']}-es mezszámú"
                    if _ctp_top.get("jersey") is not None
                    else f"{_ctp_top['player_id']} azonosítójú")
        keys.append(
            f"A hajrában a(z) {_ctp_who} játékosuknál megy el a labda "
            f"({_ctp_top['turnovers']} eladás a döntő szakaszban) — a "
            "végén rá kell menni: kettőzés és passzsáv-zárás nála, "
            "mert ott a legolcsóbb a labdaszerzés, amikor a legtöbbet "
            "ér.")

    # Csere-kiváltók: reagálnak vagy terveznek a kispadon.
    if rep.stg_subs >= 4:
        _stg_pct = 100.0 * rep.stg_after / rep.stg_subs
        if _stg_pct >= 50.0:
            keys.append(
                f"Kapott gólra cserélnek (a cseréik {_stg_pct:.0f}%-a "
                f"gól után jön, {rep.stg_after}/{rep.stg_subs}) — "
                "reagálnak, nem terveznek: a gólsorozat náluk "
                "cserezavart is okoz, ezért gyors gólváltásra kell "
                "játszani, és a csere pillanatában azonnal "
                "középkezdés.")
        elif _stg_pct <= 20.0:
            keys.append(
                f"Tervezett a csere-rendjük (a cseréiknek csak "
                f"{_stg_pct:.0f}%-a jön kapott gól után) — a "
                "csere-ritmusuk kiszámítható: a saját cseréiteket "
                "ahhoz lehet igazítani, és a friss emberük ellen "
                "időzíteni a támadást.")

    # Falépítés-idő: mennyi idő alatt áll fel a faluk.
    if rep.dst_cases >= 4 and rep.dst_sum_s > 0:
        _dst_avg = rep.dst_sum_s / rep.dst_cases
        if _dst_avg >= 8.0:
            keys.append(
                f"Lassan áll fel a faluk (átlag {_dst_avg:.1f} "
                f"másodperc a rendezett falig, {rep.dst_cases} mért "
                "birtokváltás) — a gyors indítás termel ellenük: a "
                "kapus azonnal indítson, a szélsők pedig már a lövés "
                "pillanatában fussanak.")
        elif _dst_avg <= 5.0:
            keys.append(
                f"Gyorsan rendeződik a faluk (átlag {_dst_avg:.1f} "
                "másodperc a rendezett falig) — a kontra ellenük "
                "kockázat: a felállt támadásra kell építeni, és csak "
                "biztos helyzetnél szabad vállalni a gyors "
                "befejezést.")

    # Kapus emberhátrányban: mit ér a két perc ellenük.
    if rep.gsh_sh_faced >= 4 and rep.gsh_eq_faced >= 4:
        _gsh_sh = 100.0 * rep.gsh_sh_saves / rep.gsh_sh_faced
        _gsh_eq = 100.0 * rep.gsh_eq_saves / rep.gsh_eq_faced
        if _gsh_sh - _gsh_eq >= 15.0:
            keys.append(
                f"A kapusuk emberhátrányban nő ({_gsh_sh:.0f}%-os "
                f"védés a szokásos {_gsh_eq:.0f}% helyett) — a két "
                "perc nem ingyen gól: türelmes emberelőnyt kell "
                "játszani, beállós és szélső-helyzetekkel, nem "
                "távoli lövéssel.")
        elif _gsh_eq - _gsh_sh >= 15.0:
            keys.append(
                f"A kapusuk emberhátrányban visszaesik "
                f"({_gsh_sh:.0f}%-os védés a szokásos {_gsh_eq:.0f}% "
                "helyett) — a fal nélkül maradó kapus sebezhető: "
                "emberelőnyben gyorsan kell befejezni, mielőtt "
                "rendeződnek.")

    # Emberelőny-lövők: kire kell rendezni az emberhátrányt.
    _pps_rows = rep.pp_shooters or []
    if _pps_rows and _pps_rows[0]["shots"] >= 3:
        _pps_top = _pps_rows[0]
        _pps_who = (f"{_pps_top['jersey']}-es mezszámú"
                    if _pps_top.get("jersey") is not None
                    else f"{_pps_top['player_id']} azonosítójú")
        keys.append(
            f"Emberelőnyben a(z) {_pps_who} játékosuk fejez be "
            f"({_pps_top['shots']} lövés, {_pps_top['goals']} gól) — "
            "emberhátrányban rá kell rendezni a falat: az ő oldalán "
            "jöjjön a kilépés vagy a kettőzés, a többieket pedig rá "
            "lehet engedni.")

    # Lövés-távolság esése: kifelé szorulnak-e a hajrára.
    if rep.sdf_fh_shots >= 4 and rep.sdf_sh_shots >= 4 \
            and rep.sdf_fh_sum_m > 0 and rep.sdf_sh_sum_m > 0:
        _sdf_fh = rep.sdf_fh_sum_m / rep.sdf_fh_shots
        _sdf_sh = rep.sdf_sh_sum_m / rep.sdf_sh_shots
        if _sdf_sh - _sdf_fh >= 1.0:
            keys.append(
                f"A hajrára kifelé szorulnak: a lövéseik átlagos "
                f"távolsága {_sdf_fh:.1f} m-ről {_sdf_sh:.1f} m-re nő "
                "a második félidőben — elfogy az erejük a "
                "betörésekhez: a hajrában elég a lövő-vonalba lépni, "
                "a közeli befejezést már nem vállalják.")

    # Kapott gólok támadás-típus szerint: melyik műfajból szivárognak.
    _cat_rows = list((rep.conceded_types or {}).items())
    _cat_n = sum(n for _, n in _cat_rows)
    if _cat_n >= 5 and _cat_rows:
        _cat_rows.sort(key=lambda kv: -kv[1])
        _cat_type, _cat_top = _cat_rows[0]
        _cat_pct = 100.0 * _cat_top / _cat_n
        _cat_tie = len(_cat_rows) > 1 and _cat_rows[1][1] == _cat_top
        if _cat_pct >= 40.0 and not _cat_tie:
            _cat_what = ("a visszarendeződésük a gyenge pont: a "
                         "gyors indítás és a korai befejezés termel "
                         "ellenük" if "lerohanás" in _cat_type
                         or "gyors" in _cat_type
                         else "a felállt faluk a gyenge pont: "
                         "figurákkal, beállós játékkal és "
                         "oldalváltással kell dolgozni")
            keys.append(
                f"A kapott góljaik {_cat_pct:.0f}%-a "
                f"{_cat_type}-ból jön ({_cat_top}/{_cat_n}) — "
                f"{_cat_what}.")

    # Áttörő játékosok: kire kell duplázni a falban.
    _btp_rows = rep.breakthrough_players or []
    if _btp_rows and _btp_rows[0]["entries"] >= 3:
        _btp_top = _btp_rows[0]
        _btp_who = (f"{_btp_top['jersey']}-es mezszámú"
                    if _btp_top.get("jersey") is not None
                    else f"{_btp_top['player_id']} azonosítójú")
        keys.append(
            f"A(z) {_btp_who} játékosuk töri át a falat "
            f"({_btp_top['entries']} betörés a 9 m-es körzetbe, ebből "
            f"{_btp_top['goals']} gólos támadás) — rá duplázni kell: "
            "a védője kapjon segítőt, és a betörés vonalát testtel "
            "kell zárni, mert ő nyitja szét a falat a többieknek.")

    # Két beállós játék: hány emberrel dolgoznak a 6 m-en.
    if rep.dpv_attacks >= 8:
        _dpv_pct = 100.0 * rep.dpv_double / rep.dpv_attacks
        if _dpv_pct >= 30.0:
            keys.append(
                f"Két beállóval játszanak (a támadásaik "
                f"{_dpv_pct:.0f}%-ában két emberük is a 6 m-es "
                f"zónában dolgozik, {rep.dpv_double}/"
                f"{rep.dpv_attacks}) — a fal közepét tömöríteni kell: "
                "a két középső védő NE adja át egymásnak a "
                "beállókat, a szélső védők pedig feljebb léphetnek, "
                "mert a szélek üresen maradnak.")
        elif _dpv_pct <= 10.0:
            keys.append(
                f"Egy beállós felállást játszanak (a támadásaiknak "
                f"csak {_dpv_pct:.0f}%-ában van két emberük a 6 m-en) "
                "— a segítő védő nyugodtan befelé dolgozhat, és a "
                "beállójuk körül lehet kettőzni.")

    # Hajrá-ötös: kikre kell tervezni a döntő szakaszt.
    _cll_rows = [p for p in (rep.clutch_players or [])
                 if p["frames"] > 0][:6]
    if len(_cll_rows) >= 4:
        _cll_names = []
        for _row in _cll_rows:
            _cll_names.append(
                f"{_row['jersey']}-es" if _row.get("jersey") is not None
                else f"#{_row['player_id']}")
        keys.append(
            f"A hajrá-embereik: {', '.join(_cll_names)} — a döntő "
            "szakaszra rájuk kell tervezni a párosítást: a "
            "kettőzésüket a legjobb befejezőjükre, és előre le kell "
            "beszélni, kit engedünk lőni.")

    # Kontra-kíséret: mennyi emberrel indulnak a lerohanásokra.
    if rep.fbs_breaks >= 3 and rep.fbs_sum_runners > 0:
        _fbs_avg = rep.fbs_sum_runners / rep.fbs_breaks
        if _fbs_avg >= 3.0:
            keys.append(
                f"Tömegesen kontráznak: a lerohanásaiknál átlag "
                f"{_fbs_avg:.1f} emberük van már elöl "
                f"({rep.fbs_breaks} lerohanás) — mindenkinek azonnal "
                "vissza kell rendeződnie: a lövés pillanatában már "
                "indulni kell hátra, és a fékező embert előre ki kell "
                "jelölni.")
        elif _fbs_avg <= 1.6:
            keys.append(
                f"Magányos kontrát futnak (átlag {_fbs_avg:.1f} "
                f"felfutó ember {rep.fbs_breaks} lerohanásnál) — elég "
                "egy fékező játékos: ő állítsa meg a labdást, a "
                "többiek nyugodtan álljanak fel a felállt "
                "védekezésbe.")

    # Kapus-hetesvédés iránya: hova kell lőni a hetest.
    _g7_faced = rep.g7d_faced or {}
    _g7_saved = rep.g7d_saved or {}
    _g7_n = sum(_g7_faced.values())
    if _g7_n >= 3:
        _g7_avg = 100.0 * sum(_g7_saved.values()) / _g7_n
        _g7_cand = [(d, n) for d, n in _g7_faced.items() if n >= 3]
        if _g7_cand:
            _g7_dir, _g7_dn = min(
                _g7_cand,
                key=lambda kv: _g7_saved.get(kv[0], 0) / kv[1])
            _g7_pct = 100.0 * _g7_saved.get(_g7_dir, 0) / _g7_dn
            if _g7_avg - _g7_pct >= 25.0:
                keys.append(
                    f"A kapusuk a {_g7_dir} sarokba menő hetesekre ér "
                    f"a legkésőbb (onnan {_g7_pct:.0f}%-ot fog "
                    f"{_g7_dn} hetesből, az átlaga {_g7_avg:.0f}%) — a "
                    "hetes-lövőtöknek kész terve legyen: oda kell "
                    "lőni, és nem a vonalnál kell eldönteni.")

    # Kihozatal-oldal: hova kell szervezni a letámadást.
    _bus_n = rep.bus_left + rep.bus_center + rep.bus_right
    if _bus_n >= 8:
        _bus_best, _bus_cnt = max(
            (("bal", rep.bus_left), ("közép", rep.bus_center),
             ("jobb", rep.bus_right)), key=lambda kv: kv[1])
        _bus_pct = 100.0 * _bus_cnt / _bus_n
        if _bus_pct >= 50.0 and _bus_best != "közép":
            keys.append(
                f"A {_bus_best} oldalon hozzák fel a labdát (a "
                f"támadásaik {_bus_pct:.0f}%-a onnan indul, "
                f"{_bus_cnt}/{_bus_n}) — oda kell szervezni a "
                "letámadást és a kettőzést; a másik oldalon addig "
                "elég egy ember, mert arra nem is indulnak.")

    # Lepattanó-szerzők: ki gyűjti a kipattanóikat.
    _rbw_rows = rep.rebounders or []
    if _rbw_rows and _rbw_rows[0]["rebounds"] >= 3:
        _rbw_top = _rbw_rows[0]
        _rbw_who = (f"{_rbw_top['jersey']}-es mezszámú"
                    if _rbw_top.get("jersey") is not None
                    else f"{_rbw_top['player_id']} azonosítójú")
        keys.append(
            f"A(z) {_rbw_who} játékosuk gyűjti a kipattanókat "
            f"({_rbw_top['rebounds']} visszaszerzett lepattanó) — a "
            "blokk után azonnal be kell zárni a teret: a kapus "
            "kipattanóját a legközelebbi védőnek kell kísérnie, és őt "
            "kell kiszorítani a 6 m-es térből.")

    # Lövő-távolság: kire kell kilépni, kit kell elöl fogadni.
    _shr_rows = [p for p in (rep.shooter_ranges or []) if p["shots"] >= 3]
    if _shr_rows:
        _shr_far = max(_shr_rows,
                       key=lambda p: p["sum_dist_m"] / p["shots"])
        _shr_close = min(_shr_rows,
                         key=lambda p: p["sum_dist_m"] / p["shots"])
        _far_avg = _shr_far["sum_dist_m"] / _shr_far["shots"]
        _close_avg = _shr_close["sum_dist_m"] / _shr_close["shots"]
        if _far_avg >= 9.5:
            _far_who = (f"{_shr_far['jersey']}-es mezszámú"
                        if _shr_far.get("jersey") is not None
                        else f"{_shr_far['player_id']} azonosítójú")
            keys.append(
                f"A(z) {_far_who} játékosuk távolról lő (átlag "
                f"{_far_avg:.1f} m, {_shr_far['shots']} lövés) — rá ki "
                "kell lépni a lövő-vonalba, mögötte segítővel, mert "
                "onnan büntetlenül eltalálja a kaput.")
        if _close_avg <= 7.0 and _shr_close is not _shr_far:
            _close_who = (f"{_shr_close['jersey']}-es mezszámú"
                          if _shr_close.get("jersey") is not None
                          else f"{_shr_close['player_id']} azonosítójú")
            keys.append(
                f"A(z) {_close_who} játékosuk közelről fejez be "
                f"(átlag {_close_avg:.1f} m, {_shr_close['shots']} "
                "lövés) — érte a fal nem bomolhat meg: elé kell "
                "állni és testtel fogadni, nem kihúzva várni.")

    # Emberhátrány-forma: milyen falat húznak öt emberrel.
    _shs_rows = list((rep.sh_shape or {}).items())
    _shs_n = sum(n for _, n in _shs_rows)
    if _shs_n >= 100 and _shs_rows:
        _shs_rows.sort(key=lambda kv: -kv[1])
        _shs_main, _shs_cnt = _shs_rows[0]
        _shs_pct = 100.0 * _shs_cnt / _shs_n
        if _shs_pct >= 60.0:
            _shs_what = {
                "5-0": ("mögötte az átlövés szabad: kívülről kell "
                        "lőni és a szélsőket etetni, mert öt emberrel "
                        "nem érnek ki a lövő-vonalba"),
                "4-1": ("az előretolt emberük mögött nyílik a tér: "
                        "oldalváltással kell kihúzni, és a beállót "
                        "pont az ő háta mögé kell beúsztatni"),
                "3-2": ("két előretolt ember mellett a szélek és a "
                        "beálló szabadok: gyors oldalváltás és "
                        "beállós befejezés a válasz"),
            }.get(_shs_main,
                  "a forma ellen az oldalváltás és a beállós játék a "
                  "kiindulás")
            keys.append(
                f"Emberhátrányban {_shs_main}-s falat húznak (a mért "
                f"kockák {_shs_pct:.0f}%-ában) — {_shs_what}.")

    # Emberelőny-tempó: hogyan játsszák a két percet.
    if rep.ppp_pp_attacks >= 3 and rep.ppp_eq_attacks >= 5 \
            and rep.ppp_pp_sum_s > 0 and rep.ppp_eq_sum_s > 0:
        _ppp_pp = rep.ppp_pp_sum_s / rep.ppp_pp_attacks
        _ppp_eq = rep.ppp_eq_sum_s / rep.ppp_eq_attacks
        _ppp_gap = _ppp_pp - _ppp_eq
        if _ppp_gap >= 5.0:
            keys.append(
                f"Elnyújtják az emberelőnyt ({_ppp_pp:.0f} mp-es "
                f"támadások emberelőnyben, {_ppp_eq:.0f} mp egyenlő "
                "létszámnál) — a biztos helyzetre várnak: emberhátrányban "
                "türelmes, zárt falat kell játszani, mert a kapkodó "
                "kilépés pont nekik dolgozik, és a passzív-jelig ki "
                "lehet húzni.")
        elif _ppp_gap <= -5.0:
            keys.append(
                f"Kapkodnak emberelőnyben ({_ppp_pp:.0f} mp-es "
                f"támadások a {_ppp_eq:.0f} mp-es átlaguk helyett) — a "
                "két perc alatt nagy a hibaszázalékuk: agresszív, "
                "kilépő védekezéssel kell fogadni őket, mert a korai "
                "lövésből lesz a ti kontrátok.")

    # Meccs-ritmus: szakadozott vagy folyamatos meccsre kell készülni.
    if rep.ptp_total_s >= 600.0:
        _ptp_eff = (100.0 * (rep.ptp_total_s - rep.ptp_stopped_s)
                    / rep.ptp_total_s)
        if _ptp_eff <= 80.0:
            keys.append(
                f"Szakadozott meccsképre kell készülni: az effektív "
                f"játékidő {_ptp_eff:.0f}% "
                f"({rep.ptp_stopped_s / 60.0:.0f} perc holt idő, "
                f"ebből {rep.ptp_own_stoppages} megszakítás náluk "
                "állt meg) — a ritmus-tartás a feladat: gyors "
                "középkezdés, és a megszakítások utáni első "
                "támadásra legyen kész terv.")
        elif _ptp_eff >= 92.0:
            keys.append(
                f"Folyamatos meccsre kell készülni: az effektív "
                f"játékidő {_ptp_eff:.0f}% — kevés a szusszanás, "
                "ezért a cserék időzítése és a bírás dönt: a "
                "kulcsembereket tervezetten kell pihentetni.")

    # Védekezés-keménység: hoz-e büntetést a faluk.
    if rep.agr_attacks >= 10:
        _agr_pct = (100.0 * (rep.agr_sevens + rep.agr_susp)
                    / rep.agr_attacks)
        if _agr_pct >= 12.0:
            keys.append(
                f"Kemény fal: a védekezett támadásaik "
                f"{_agr_pct:.0f}%-a végződik hetessel vagy "
                f"kiállítással ({rep.agr_sevens} hetes, "
                f"{rep.agr_susp} kiállítás) — a betörés duplán fizet "
                "ellenük: vagy áthaladtok, vagy hetes és emberelőny "
                "jön belőle, ezért a hetes-lövőtöknek végig "
                "hidegvérűnek kell maradnia.")
        elif _agr_pct <= 4.0:
            keys.append(
                f"Passzív fal: a védekezett támadásaiknak csak "
                f"{_agr_pct:.0f}%-a hoz hetest vagy kiállítást "
                f"({rep.agr_attacks} támadás) — tőlük nem kaptok "
                "ingyen büntetőt: figurákkal, beállós játékkal és "
                "oldalváltással kell helyzetet csinálni.")

    # Visszaérés-fegyelem: ki lóg elöl védekezéskor.
    _rcd_rows = [p for p in (rep.recovery_players or [])
                 if p["frames"] >= 200]
    if _rcd_rows:
        _rcd_worst = min(_rcd_rows,
                         key=lambda p: p["home_frames"] / p["frames"])
        _rcd_pct = 100.0 * _rcd_worst["home_frames"] / _rcd_worst["frames"]
        if _rcd_pct < 70.0:
            _rcd_who = (f"{_rcd_worst['jersey']}-es mezszámú"
                        if _rcd_worst.get("jersey") is not None
                        else f"{_rcd_worst['player_id']} azonosítójú")
            keys.append(
                f"A(z) {_rcd_who} játékosuk elöl lóg védekezéskor (a "
                f"védekezett időnek csak {_rcd_pct:.0f}%-ában van a "
                "saját térfelén) — az ő oldalán kell a gyors "
                "indítást vezetni: mögötte nincs védő, a kapus "
                "indítása azonnal helyzetet ér.")

    # Kapus-védés lövés-tempó szerint: erővel vagy helyezéssel kell lőni.
    if rep.gsp_hard_faced >= 4 and rep.gsp_placed_faced >= 4:
        _gsp_h = 100.0 * rep.gsp_hard_saves / rep.gsp_hard_faced
        _gsp_p = 100.0 * rep.gsp_placed_saves / rep.gsp_placed_faced
        if abs(_gsp_h - _gsp_p) >= 15.0:
            if _gsp_h > _gsp_p:
                keys.append(
                    f"A kapusuk a bombákat fogja ({_gsp_h:.0f}%), a "
                    f"helyezett lövéseket nem ({_gsp_p:.0f}%) — nem "
                    "erővel kell lőni rá: a sarkokba helyezve, "
                    "megemelt vagy pattintott lövéssel jön a gól.")
            else:
                keys.append(
                    f"A kapusuk a helyezett lövéseket fogja "
                    f"({_gsp_p:.0f}%), a keményeket nem "
                    f"({_gsp_h:.0f}%) — vele szemben a tempó dönt: "
                    "vállalni kell a kemény lövést, és nem "
                    "kicselezni akarni.")

    # Álló támadók: kit hagyhat ott a védője.
    _sta_rows = [p for p in (rep.static_attackers or [])
                 if p["seconds"] > 0]
    if _sta_rows:
        _sta_t = sum(p["seconds"] for p in _sta_rows)
        _sta_d = sum(p["dist_m"] for p in _sta_rows)
        _sta_cand = [p for p in _sta_rows if p["seconds"] >= 60.0]
        if _sta_t > 0 and _sta_cand:
            _sta_avg = _sta_d / _sta_t
            _sta_slow = min(_sta_cand,
                            key=lambda p: p["dist_m"] / p["seconds"])
            _sta_v = _sta_slow["dist_m"] / _sta_slow["seconds"]
            if _sta_avg > 0 and (100.0 * (_sta_avg - _sta_v)
                                 / _sta_avg) >= 30.0:
                _sta_who = (f"{_sta_slow['jersey']}-es mezszámú"
                            if _sta_slow.get("jersey") is not None
                            else f"{_sta_slow['player_id']} azonosítójú")
                keys.append(
                    f"A(z) {_sta_who} játékosuk alig mozog a "
                    f"támadásban ({_sta_v:.2f} m/s a csapatátlag "
                    f"{_sta_avg:.2f} m/s helyett) — az ő védője "
                    "nyugodtan otthagyhatja: befelé segíthet, "
                    "kettőzhet vagy a beállóra léphet, mert az álló "
                    "ember nem bünteti meg.")

    # Szélső-befejezés oldalanként: melyik szélsőjük veszélyes.
    if rep.wfs_left_shots >= 3 and rep.wfs_right_shots >= 3:
        _wfs_l = 100.0 * rep.wfs_left_goals / rep.wfs_left_shots
        _wfs_r = 100.0 * rep.wfs_right_goals / rep.wfs_right_shots
        if abs(_wfs_l - _wfs_r) >= 25.0:
            _wfs_strong = "bal" if _wfs_l > _wfs_r else "jobb"
            _wfs_weak = "jobb" if _wfs_l > _wfs_r else "bal"
            _wfs_spct = max(_wfs_l, _wfs_r)
            _wfs_wpct = min(_wfs_l, _wfs_r)
            keys.append(
                f"A {_wfs_strong} szélsőjük a veszélyes "
                f"({_wfs_spct:.0f}%-os befejezés, a másik oldalon "
                f"{_wfs_wpct:.0f}%) — vele szemben időben ki kell "
                f"futni és zárni a szöget (a kapus a rövid sarkot "
                f"veszi), a {_wfs_weak} szélsőjükre viszont rá lehet "
                "engedni a lövést: ott a befelé segítés többet ér.")

    # Beálló-oldal: melyik oldalon dolgozik a beállójuk.
    _pvs_n = rep.pvs_left + rep.pvs_center + rep.pvs_right
    if _pvs_n >= 100:
        _pvs_best, _pvs_cnt = max(
            (("bal", rep.pvs_left), ("közép", rep.pvs_center),
             ("jobb", rep.pvs_right)), key=lambda kv: kv[1])
        _pvs_pct = 100.0 * _pvs_cnt / _pvs_n
        if _pvs_pct >= 55.0 and _pvs_best != "közép":
            keys.append(
                f"A beállójuk a {_pvs_best} oldalon dolgozik (a mért "
                f"kockák {_pvs_pct:.0f}%-ában ott áll be) — az azon "
                "az oldalon lévő középső-oldalsó védőpárnak kell rá "
                "készülnie: átadás-fegyelem és testes fogadás ott, a "
                "másik oldalon pedig szűkíthető a segítés.")

    # Fal-csúszás: milyen gyorsan igazodik a faluk az oldalváltáshoz.
    if rep.dsl_frames >= 200 and rep.dsl_sum_s > 0:
        _dsl_lag = rep.dsl_sum_s / rep.dsl_frames
        if _dsl_lag >= 0.6:
            keys.append(
                f"Lassan csúszik a faluk: {_dsl_lag:.1f} mp késéssel "
                "követik a labda oldalváltásait — az oldalváltás a "
                "fegyver ellenük: két-három gyors átjátszás után a "
                "túloldalon nyílik a rés, oda kell érkeznie a "
                "befejezőnek.")
        elif _dsl_lag <= 0.2:
            keys.append(
                f"Gyorsan igazodik a faluk (csak {_dsl_lag:.1f} mp "
                "késéssel követik az oldalváltást) — az átjátszás "
                "ellenük csak a saját támadásotokat fárasztja: a "
                "résre indított betörés és a beállós játék a válasz.")

    # Passz-sebesség: éles vagy lágy a labdajáratásuk.
    if rep.psp_passes >= 10:
        _psp_avg = rep.psp_sum_ms / rep.psp_passes
        _psp_fast = 100.0 * rep.psp_fast / rep.psp_passes
        if _psp_fast >= 50.0:
            keys.append(
                f"Éles a labdajáratásuk: a passzaik "
                f"{_psp_fast:.0f}%-a feszes (átlag {_psp_avg:.1f} "
                f"m/s, {rep.psp_passes} mért passz) — a passz-vonalba "
                "nyúlás ellenük kockázatos: testtel kell zárni és a "
                "FOGADÓT megfogni, mert a labdát nem éritek utol.")
        elif _psp_fast <= 20.0:
            keys.append(
                f"Lágy a labdajáratásuk: a passzaiknak csak "
                f"{_psp_fast:.0f}%-a feszes (átlag {_psp_avg:.1f} "
                f"m/s, {rep.psp_passes} mért passz) — bele lehet érni: "
                "kilépéssel és beleérő védekezéssel az elfogott "
                "második passz azonnali kontrát ér.")

    # Beálló-kiszolgálók: kin keresztül él a beállójuk.
    _pf_rows = rep.pivot_feeders or []
    _pf_n = sum(p["feeds"] for p in _pf_rows)
    if _pf_n >= 4 and _pf_rows:
        _pf_top = _pf_rows[0]
        _pf_pct = 100.0 * _pf_top["feeds"] / _pf_n
        _pf_tie = (len(_pf_rows) > 1
                   and _pf_rows[1]["feeds"] == _pf_top["feeds"])
        if _pf_pct >= 50.0 and not _pf_tie:
            _pf_who = (f"{_pf_top['jersey']}-es mezszámú"
                       if _pf_top.get("jersey") is not None
                       else f"{_pf_top['player_id']} azonosítójú")
            keys.append(
                f"Egy ember szolgálja ki a beállójukat: a(z) "
                f"{_pf_who} játékosuk adja a beadások "
                f"{_pf_pct:.0f}%-át ({_pf_top['feeds']}/{_pf_n}) — őt "
                "kell zárni: rá kell lépni a beálló-vonalba, és az ő "
                "oldalán indítsátok a kettőzést, mert nélküle a "
                "beállójuk kiesik a játékból.")

    # Hetes-okozó védők: kinél szakad meg a védekezésük hetessel.
    _smc_rows = rep.seven_conceders or []
    if _smc_rows and _smc_rows[0]["conceded"] >= 2:
        _smc_top = _smc_rows[0]
        _smc_who = (f"{_smc_top['jersey']}-es mezszámú"
                    if _smc_top.get("jersey") is not None
                    else f"{_smc_top['player_id']} azonosítójú")
        keys.append(
            f"A(z) {_smc_who} védőjük {_smc_top['conceded']} hetest "
            "okozott — nála kézzel áll meg a betörés: ellene "
            "indítsatok betörést és beugrást, mert vagy áthaladtok, "
            "vagy hetest ér.")

    # Támadás-mélység: milyen messze állnak a kaputól felállt támadásban.
    if rep.adp_frames >= 100 and rep.adp_sum_m > 0:
        _adp = rep.adp_sum_m / rep.adp_frames
        if _adp <= 9.5:
            keys.append(
                f"Vonalra tapadnak: a támadóik átlagosan {_adp:.1f} "
                "m-re állnak a kaputól — betörésre és beugrásra "
                "játszanak: a falatok NE lépjen ki, a segítő-csúszás "
                "és a testes fogadás a válasz, a beállót elölről "
                "kell megfogni.")
        elif _adp >= 12.0:
            keys.append(
                f"Mélyen, hátrahúzódva támadnak (átlagosan "
                f"{_adp:.1f} m-re a kaputól) — idő kell nekik a "
                "lövés-előkészítéshez: ki kell lépni a lövő-vonalba, "
                "mert onnan a távoli lövés az egyetlen fegyverük, és "
                "a kilépés után is van idő visszazárni.")

    # Szélső-bevonás: eljut-e a labda a szélre a támadásaikban.
    if rep.wi_attacks >= 8:
        _wi_pct = 100.0 * rep.wi_with_wing / rep.wi_attacks
        if _wi_pct >= 60.0:
            keys.append(
                f"Széthúzzák a támadást: a támadásaik "
                f"{_wi_pct:.0f}%-ában kimegy a labda a szélre "
                f"({rep.wi_with_wing}/{rep.wi_attacks}) — a "
                "szélső-védekezés a feladat: időben kell kifutni, és "
                "a szélső mögötti területet a segítő védőnek kell "
                "zárnia, mert a szélre-húzás nyitja meg a beállót.")
        elif _wi_pct <= 30.0:
            keys.append(
                f"Közép-központúak: a támadásaiknak csak "
                f"{_wi_pct:.0f}%-ában jut ki a labda a szélre "
                f"({rep.wi_attacks} támadás) — a szélső-védőitek "
                "beljebb segíthetnek: tömör fallal a beállót és az "
                "átlövést kell elzárni, a szélt úgysem játsszák meg.")

    # Védekezési mélység állás szerint: mikor jön a nyomásuk.
    if rep.lhs_lead_frames >= 100 and rep.lhs_trail_frames >= 100:
        _lhs_lead = rep.lhs_lead_sum_m / rep.lhs_lead_frames
        _lhs_trail = rep.lhs_trail_sum_m / rep.lhs_trail_frames
        _lhs_gap = _lhs_trail - _lhs_lead
        if _lhs_gap >= 0.8:
            keys.append(
                f"Hátrányban feljebb lépnek: hátrányban "
                f"{_lhs_trail:.1f} m-en, vezetve {_lhs_lead:.1f} m-en "
                "áll a faluk — kapott gól után jön a letámadásuk, "
                "arra kell kész kihozatal (a kapussal együtt "
                "begyakorolt indítás); ha viszont ti vezettek, "
                "türelmesen kell játszani, mert a mély faluk a "
                "kapkodó átlövésre vár.")
        elif _lhs_gap <= -0.8:
            keys.append(
                f"Vezetve is fent maradnak: előnyben {_lhs_lead:.1f} "
                f"m-en, hátrányban {_lhs_trail:.1f} m-en áll a faluk "
                "— nem ülnek vissza, tehát a vezetésük ellen a "
                "letámadás-álló kihozatal a kulcs: gyors első passz "
                "és két kijelölt felhozó.")

    # Támadás-kimenetel: eljutnak-e egyáltalán a befejezésig.
    _ao_rows = rep.attack_outcomes or {}
    _ao_n = sum(_ao_rows.values())
    if _ao_n >= 8:
        _ao_shot = 100.0 * _ao_rows.get("lövés", 0) / _ao_n
        _ao_to = 100.0 * _ao_rows.get("eladás", 0) / _ao_n
        if _ao_to >= 25.0:
            keys.append(
                f"Lövés nélkül halnak el a támadásaik: a "
                f"{_ao_n} támadásuk {_ao_to:.0f}%-a eladással "
                f"zárult ({_ao_rows.get('eladás', 0)} db) — a "
                "kettőzés és a magas nyomás azonnal termel ellenük: "
                "a labdásra kell menni, mert a befejezésig sem "
                "jutnak el.")
        elif _ao_shot >= 85.0:
            keys.append(
                f"Mindent befejeznek: a {_ao_n} támadásuk "
                f"{_ao_shot:.0f}%-a lövéssel zárult — a rájuk "
                "erőltetett pressz kockázat, mert nem ajándékoznak: "
                "a blokk és a kapus mögé rendezett fal a válasz, és "
                "a lövés minőségét kell rontani.")

    # Kapus-védés posztonként: melyik szögből sebezhető a kapusuk.
    _gs_rows = list((rep.gk_role_saves or {}).items())
    _gs_faced = sum(r["faced"] for _, r in _gs_rows)
    _gs_saves = sum(r["saves"] for _, r in _gs_rows)
    if _gs_faced >= 8 and _gs_rows:
        _gs_avg = 100.0 * _gs_saves / _gs_faced
        _gs_cand = [(poszt, r) for poszt, r in _gs_rows
                    if r["faced"] >= 4]
        if _gs_cand:
            _gs_poszt, _gs_rec = min(
                _gs_cand, key=lambda kv: kv[1]["saves"] / kv[1]["faced"])
            _gs_pct = 100.0 * _gs_rec["saves"] / _gs_rec["faced"]
            if _gs_avg - _gs_pct >= 15.0:
                keys.append(
                    f"A kapusuk a {_gs_poszt} posztról sebezhető: "
                    f"onnan {_gs_pct:.0f}%-ot fog "
                    f"({_gs_rec['saves']}/{_gs_rec['faced']}), a "
                    f"csapat-átlaga {_gs_avg:.0f}% — oda kell "
                    "szervezni a befejezést, és onnan bátran kell "
                    "lőni rá, mert azt a szöget nem zárja.")

    # Hiba-sorozatok: egymás után jönnek-e az eladásaik.
    if rep.tc_turnovers >= 5:
        _tc_pct = 100.0 * rep.tc_clustered / rep.tc_turnovers
        if _tc_pct >= 50.0:
            keys.append(
                f"Sorozatban hibáznak: az eladásaik {_tc_pct:.0f}%-a "
                f"egy percen belül követte az előzőt "
                f"({rep.tc_clustered}/{rep.tc_turnovers}, "
                f"{rep.tc_clusters} sorozat) — egy eladás után "
                "kapkodni kezdenek: az első labdaszerzés után "
                "azonnal újra rá kell menni, mert ott jön a második "
                "ajándék.")
        elif _tc_pct <= 20.0:
            keys.append(
                f"Szórt hibák: az eladásaiknak csak {_tc_pct:.0f}%-a "
                f"jön sorozatban ({rep.tc_turnovers} eladás) — egy "
                "hibájuk után nem borulnak be, a rájuk erőltetett "
                "pressz fölösleges kockázat: a felállt védekezés a "
                "válasz.")

    # Kapott gólok posztonként: melyik poszt ellen szivárog a faluk.
    _cr_rows = list((rep.conceded_roles or {}).items())
    _cr_n = sum(n for _, n in _cr_rows)
    if _cr_n >= 5 and _cr_rows:
        _cr_rows.sort(key=lambda kv: -kv[1])
        _cr_poszt, _cr_top = _cr_rows[0]
        _cr_pct = 100.0 * _cr_top / _cr_n
        _cr_tie = len(_cr_rows) > 1 and _cr_rows[1][1] == _cr_top
        if _cr_pct >= 45.0 and not _cr_tie:
            _cr_what = {
                "szélső": ("a szélsőiteket kell etetni: szélességben "
                           "kell tartani a támadást, és a szélső "
                           "kapja meg a labdát a kifutásuk előtt"),
                "beálló": ("a beállós játékot kell futtatni: "
                           "keresztmozgás, beúszás és a beálló "
                           "kiszolgálása a rés felé"),
                "átlövő": ("a távoli befejezésre kell építeni: "
                           "átlövés a kilépésük előtt, illetve a "
                           "kilépés utáni betörés"),
                "irányító": ("az irányítótok kapja a lövő-helyzeteket: "
                             "kettőzés-csali után az ő befejezése jön"),
            }.get(_cr_poszt, "erre a posztra kell szervezni a támadást")
            keys.append(
                f"Egy poszt ellen szivárog a faluk: a kapott góljaik "
                f"{_cr_pct:.0f}%-a a {_cr_poszt} posztról jön "
                f"({_cr_top}/{_cr_n}) — {_cr_what}.")

    # Poszt szerinti gólmegoszlás: melyik posztra épül a befejezésük.
    _rg_rows = list((rep.role_goals or {}).items())
    _rg_n = sum(n for _, n in _rg_rows)
    if _rg_n >= 5 and _rg_rows:
        _rg_rows.sort(key=lambda kv: -kv[1])
        _rg_poszt, _rg_top = _rg_rows[0]
        _rg_pct = 100.0 * _rg_top / _rg_n
        _rg_tie = len(_rg_rows) > 1 and _rg_rows[1][1] == _rg_top
        if _rg_pct >= 45.0 and not _rg_tie:
            _rg_what = {
                "szélső": ("a szélső-védekezés az első feladat: időben "
                           "ki kell futni a szélsőre és zárni a szöget, "
                           "mert onnan élesből is betalálnak"),
                "beálló": ("a beálló elé kell állni: elölről megfogva, "
                           "a betörés vonalát elzárva, és a kiszolgáló "
                           "passzt kell megelőzni"),
                "átlövő": ("előre kell lépni a lövő-vonalba: felemelt "
                           "kézzel, a blokk mögé rendezett kapussal"),
                "irányító": ("az irányítójukra kell menni: kettőzés a "
                             "9 m-en kívül, hogy ne tudjon lövő-helyzetbe "
                             "fordulni"),
            }.get(_rg_poszt, "erre a posztra kell rendezni a védekezést")
            keys.append(
                f"Egy posztra épül a befejezésük: a góljaik "
                f"{_rg_pct:.0f}%-a a {_rg_poszt} posztról jön "
                f"({_rg_top}/{_rg_n}) — {_rg_what}.")

    # Gólpassz-zónák: melyik átadás-vonalról készítik elő a gólokat.
    _az_rows = list((rep.assist_zones or {}).items())
    _az_n = sum(n for _, n in _az_rows)
    if _az_n >= 4 and _az_rows:
        _az_rows.sort(key=lambda kv: -kv[1])
        _az_zone, _az_top = _az_rows[0]
        _az_pct = 100.0 * _az_top / _az_n
        _az_tie = len(_az_rows) > 1 and _az_rows[1][1] == _az_top
        if _az_pct >= 50.0 and not _az_tie:
            _az_what = {
                "szélről": ("a szélső–beálló tengelyt kell elvágni: a "
                            "szélső átadás-vonalába kell belépni, és a "
                            "beállót elölről kell megfogni"),
                "beállótól": ("a beálló kiszolgálását kell elvágni: "
                              "előtte kell állni és a befelé fordulást "
                              "kell megakadályozni, ne mögüle jöjjön a "
                              "labda"),
                "átlövésből": ("az átlövők passz-sávját kell zárni: "
                               "előrelépés a lövő-vonalba, felemelt "
                               "kézzel, hogy a beadás ne menjen át"),
            }.get(_az_zone, "ezt az átadás-vonalat kell zárni")
            keys.append(
                f"Egy vonalról készítik elő a gólokat: a gólpasszaik "
                f"{_az_pct:.0f}%-a {_az_zone} érkezik "
                f"({_az_top}/{_az_n}) — {_az_what}.")

    # Támadás-indítók: egy ember hozza-e fel a labdát.
    _st_rows = rep.starters or []
    _st_n = sum(p["starts"] for p in _st_rows)
    if _st_n >= 6 and _st_rows:
        _st_top = max(_st_rows, key=lambda p: p["starts"])
        _st_pct = 100.0 * _st_top["starts"] / _st_n
        _st_who = (f"{_st_top['jersey']}-es mezszámú"
                   if _st_top.get("jersey") is not None
                   else f"{_st_top['player_id']} azonosítójú")
        if _st_pct >= 40.0:
            keys.append(
                f"Egy ember hozza fel a labdát: a(z) {_st_who} "
                f"játékosuk indítja a támadások {_st_pct:.0f}%-át "
                f"({_st_top['starts']}/{_st_n}) — rá kell menni a "
                "felhozatalnál: letámadás és az átadás-vonal zárása, "
                "mert nélküle megakad a felállásuk.")
        elif _st_pct <= 25.0:
            keys.append(
                f"Megosztott kihozatal: a legtöbbet indító emberük is "
                f"csak a támadások {_st_pct:.0f}%-át hozza fel "
                f"({_st_n} mért indítás) — a letámadás itt nem fizet "
                "ki, mert bárki felhozza: inkább rendezetten álljatok "
                "fel a felállt védekezésben.")

    # Időkérés-időzítés: hol a küszöbük, és tartogatják-e a hajrára.
    if rep.tot_timeouts >= 2:
        _tot_avg = rep.tot_sum_before / rep.tot_timeouts
        _tot_late = 100.0 * rep.tot_late / rep.tot_timeouts
        if _tot_avg <= 1.5:
            keys.append(
                f"Korán fékeznek: átlag {_tot_avg:.1f} kapott gól "
                f"után kérnek időt ({rep.tot_timeouts} időkérés) — a "
                "sorozatot nem hagyják kifutni, ezért a gyors "
                "gólváltásra kell játszani, nem egy nagy hullámra: "
                "az időkérés utáni első támadásukra legyen kész terv.")
        elif _tot_avg >= 2.5:
            keys.append(
                f"Hagyják elszaladni a sorozatot: átlag "
                f"{_tot_avg:.1f} kapott gól után kérnek időt "
                f"({rep.tot_timeouts} időkérés) — ha megindul a "
                "hullám, van két-három támadásnyi ablak: azt kell "
                "maximálisan kihasználni.")
        if _tot_late >= 50.0:
            keys.append(
                f"A hajrára tartogatják az időkérést (az "
                f"időkéréseik {_tot_late:.0f}%-a az utolsó 10 "
                "percben) — a döntő szakaszban mindig rendezetten "
                "állnak fel: a záró támadásaitokat előre le kell "
                "beszélni, meglepetéssel nem lesz meg.")

    # Páros-mérleg: melyik kettősük megy a legjobban együtt.
    _prm_rows = [p for p in (rep.pair_plus_minus or [])
                 if p["frames"] / (rep.pair_fps or 25.0) / 60.0 >= 4.0]
    if _prm_rows:
        _prm_best = max(
            _prm_rows,
            key=lambda p: ((p["for"] - p["against"])
                           / max(0.1, p["frames"] / (rep.pair_fps or 25.0)
                                 / 60.0)))
        _prm_min = _prm_best["frames"] / (rep.pair_fps or 25.0) / 60.0
        if (_prm_best["for"] - _prm_best["against"]) / _prm_min >= 0.2:
            _prm_who = " és ".join(str(pid)
                                   for pid in _prm_best["players"])
            keys.append(
                f"A(z) {_prm_who} azonosítójú kettősük együtt megy a "
                f"legjobban ({_prm_best['for']}-{_prm_best['against']} "
                f"a mérleg {_prm_min:.0f} közös perc alatt) — a "
                "párost szét kell szedni: kettőzés arra, aki hamarabb "
                "fárad, és időkérés, ha együtt lendülnek meg.")

    # Csere-blokkok: egységekben cserélnek, vagy egyesével.
    if rep.sbl_waves >= 4:
        _sbl_pct = 100.0 * rep.sbl_block_waves / rep.sbl_waves
        _sbl_avg = rep.sbl_players / rep.sbl_waves
        if _sbl_pct >= 40.0:
            keys.append(
                f"Egységekben cserélnek (a {rep.sbl_waves} hullámból "
                f"{rep.sbl_block_waves} volt 2+ fős, átlag "
                f"{_sbl_avg:.1f} ember) — specialistákat mozgatnak: a "
                "gyors újraindítás a fegyver ellenük, mert csere "
                "közben egy ütemre rossz emberek vannak a pályán.")
        else:
            keys.append(
                f"Egyesével cserélnek ({rep.sbl_waves} hullám, átlag "
                f"{_sbl_avg:.1f} ember) — nincs külön támadó és "
                "védekező egységük: a célzott fárasztás működik, "
                "vigyétek rá a játékot a kulcsembereikre.")

    # Labdatartás-idő: kinél áll meg náluk a labda.
    _htp_rows = [p for p in (rep.hold_players or []) if p["holds"] >= 5]
    _htp_holds = sum(p["holds"] for p in (rep.hold_players or []))
    _htp_frames = sum(p["frames"] for p in (rep.hold_players or []))
    if _htp_rows and _htp_holds >= 5:
        _htp_avg = _htp_frames / _htp_holds / (rep.hold_fps or 25.0)
        _htp_slow = max(_htp_rows,
                        key=lambda p: p["frames"] / p["holds"])
        _htp_s = (_htp_slow["frames"] / _htp_slow["holds"]
                  / (rep.hold_fps or 25.0))
        if _htp_s - _htp_avg >= 0.8:
            _htp_who = (f"{_htp_slow['jersey']}-es mezszámú"
                        if _htp_slow.get("jersey") is not None
                        else f"{_htp_slow['player_id']} azonosítójú")
            keys.append(
                f"A(z) {_htp_who} játékosuknál áll meg a labda "
                f"(átlag {_htp_s:.1f} mp tartás a csapatátlag "
                f"{_htp_avg:.1f} mp helyett) — nála van idő odaérni: "
                "rá jöjjön a kettőzés és a letámadás, mert nála "
                "lassul a támadásuk.")

    # Védekezés-váltás: egy rendszert játszanak, vagy váltogatnak.
    if rep.fsw_attacks >= 6 and rep.fsw_pairs > 0 and rep.fsw_labels:
        _fsw_main = max(rep.fsw_labels.items(), key=lambda kv: kv[1])[0]
        _fsw_sw = 100.0 * rep.fsw_switches / rep.fsw_pairs
        _fsw_mainpct = (100.0 * rep.fsw_labels[_fsw_main]
                        / rep.fsw_attacks)
        if _fsw_sw >= 30.0:
            keys.append(
                f"Váltogatják a védekezést (a védekezett támadások "
                f"{_fsw_sw:.0f}%-ánál más fal, a fő formájuk a "
                f"{_fsw_main}) — a felismerés a feladat: a "
                "kihozatalnál hangosan be kell mondani a formát, és "
                "két kész változattal érkezni (elzárásos az egyik, "
                "beállós a másik).")
        elif _fsw_mainpct >= 80.0:
            keys.append(
                f"Végig egy rendszert játszanak védekezésben "
                f"({_fsw_main}, a védekezett támadások "
                f"{_fsw_mainpct:.0f}%-ában) — egy figurasort kell rá "
                "felépíteni és végig azt húzni: ha bejön a megoldás, "
                "nem fognak váltani rá.")

    # Célba vett védő: melyik védőjük előtt megy be a legtöbb lövés
    # (a csapatátlaguknál rosszabb gólarány = oda kell támadni).
    if rep.tdf_shots >= 4:
        _tdf_avg = 100.0 * rep.tdf_goals / rep.tdf_shots
        _tdf_weak = None
        for p in (rep.targeted_defenders or []):
            if p["shots"] < 4:
                continue
            _gap = 100.0 * p["goals"] / p["shots"] - _tdf_avg
            if _gap >= 15.0 and (_tdf_weak is None
                                 or _gap > _tdf_weak[1]):
                _tdf_weak = (p, _gap)
        if _tdf_weak is not None:
            _tdf_p = _tdf_weak[0]
            _tdf_who = (f"{_tdf_p['jersey']}-es mezszámú"
                        if _tdf_p.get("jersey") is not None
                        else f"{_tdf_p['player_id']} azonosítójú")
            keys.append(
                f"A(z) {_tdf_who} védőjük előtt megy be a legtöbb "
                f"lövés ({_tdf_p['goals']}/{_tdf_p['shots']}, a "
                f"csapatátlaguk felett {_tdf_weak[1]:.0f} "
                "százalékponttal) — oda kell vinni a befejezéseket: "
                "elzárással rá, és az ő oldalán a beálló.")

    # Lövő-erő: van-e a csapatátlag felett bombázó befejezőjük.
    if rep.spw_team_shots >= 6:
        _spw_avg = rep.spw_team_sum_kmh / rep.spw_team_shots
        for _spw_p in (rep.shooter_power or []):
            if _spw_p["shots"] < 4:
                continue
            _spw_pavg = _spw_p["sum_kmh"] / _spw_p["shots"]
            if _spw_pavg - _spw_avg >= 8.0:
                keys.append(
                    f"A(z) {_spw_p['player_id']} azonosítójú lövőjük "
                    f"bombáz ({_spw_pavg:.0f} km/h átlag, csapatátlag "
                    f"{_spw_avg:.0f} km/h; csúcs "
                    f"{_spw_p['max_kmh']:.0f} km/h) — ellene a fal ne "
                    "vakon blokkoljon, hanem zárja a szöget, a kapus "
                    "pedig korábban induljon.")
                break

    # Lövő-kapuoldal: van-e kiszámítható befejezőjük.
    for _shp_p in (rep.shooter_placement or []):
        if _shp_p["goals"] < 4:
            continue
        _shp_dom = max(("bal", "közép", "jobb"),
                       key=lambda k: _shp_p[k])
        _shp_share = 100.0 * _shp_p[_shp_dom] / _shp_p["goals"]
        if _shp_share >= 60.0:
            keys.append(
                f"A(z) {_shp_p['player_id']} azonosítójú lövőjük "
                f"kiszámítható: a {_shp_p['goals']} góljából "
                f"{_shp_share:.0f}% a {_shp_dom} oldalra ment — a "
                f"kapus álljon rá a {_shp_dom} sarokra, a fal a "
                "másik oldalt zárja.")
            break

    # Szélső-védekezés: nyitott-e a faluk a szélen.
    if rep.wdf_wing_shots >= 5 and rep.wdf_center_shots >= 5:
        _wdf_w = 100.0 * rep.wdf_wing_goals / rep.wdf_wing_shots
        _wdf_c = 100.0 * rep.wdf_center_goals / rep.wdf_center_shots
        if _wdf_w - _wdf_c >= 15.0:
            keys.append(
                f"A faluk a szélen nyitott: a szélső lövések "
                f"{_wdf_w:.0f}%-a gól ellenük, középről csak "
                f"{_wdf_c:.0f}% — vonjátok be a szélsőket: "
                "szélességben játszott támadás, oldalváltás, és a "
                "szélső kapja meg a labdát a tiszta szögben.")
        elif _wdf_c - _wdf_w >= 15.0:
            keys.append(
                f"A szélső lövéseket zárják ({_wdf_w:.0f}% gólarány, "
                f"középről {_wdf_c:.0f}%) — a szél zsákutca ellenük: "
                "a középső áttörés és a beálló-bejátszás a járható út.")

    # Drága eladók: kinek a hibája kerül náluk gólba.
    _ctp_worst = next((p for p in (rep.costly_turnover_players or [])
                       if p["turnovers"] >= 3 and p["punished"] >= 2),
                      None)
    if _ctp_worst is not None:
        keys.append(
            f"A(z) {_ctp_worst['player_id']} azonosítójú játékosuk "
            f"eladásai kerülnek gólba ({_ctp_worst['punished']} "
            f"kapott gól {_ctp_worst['turnovers']} eladásból) — rá "
            "kell menni: kettőzzétek a felhozatalnál, nála a "
            "legnagyobb a nyereség.")

    # Emberelőny-védekezés: emberelőnyben is szivárognak-e.
    if rep.ppd_seconds >= 90.0 and rep.ppd_eq_seconds > 0:
        _ppd = 60.0 * rep.ppd_conceded / rep.ppd_seconds
        _ppd_eq = 60.0 * rep.ppd_eq_conceded / rep.ppd_eq_seconds
        if _ppd - _ppd_eq >= 0.2:
            keys.append(
                f"Emberelőnyben is szivárognak ({_ppd:.2f} kapott "
                f"gól/perc, egyenlő létszámnál {_ppd_eq:.2f}) — ha "
                "kiállítást kaptok, ne csak túléljetek: hátrányban is "
                "vállaljátok a lerohanást, a befejezésük után azonnal "
                "induljon a kontra.")
        elif _ppd_eq - _ppd >= 0.2:
            keys.append(
                f"Emberelőnyben fegyelmezetten védekeznek ({_ppd:.2f} "
                f"kapott gól/perc, egyenlő létszámnál {_ppd_eq:.2f}) — "
                "hátrányban ellenük a labdatartás a reális cél: "
                "húzzátok ki a két percet eladás nélkül.")

    # Kapus szabad lövés ellen: a fal nélkül is véd-e a kapusuk.
    if rep.gkf_free_shots >= 5 and rep.gkf_cov_shots >= 5:
        _gkf_fr = 100.0 * rep.gkf_free_saves / rep.gkf_free_shots
        _gkf_cv = 100.0 * rep.gkf_cov_saves / rep.gkf_cov_shots
        if _gkf_cv - _gkf_fr >= 15.0:
            keys.append(
                f"A kapusuk falfüggő: fedezett lövésnél "
                f"{_gkf_cv:.0f}%-ot véd, szabadon leadottnál csak "
                f"{_gkf_fr:.0f}%-ot — tiszta lövéshelyzetet kell "
                "gyártani: elzárás után zavartalan átlövés, ne a "
                "falon keresztül lőjetek.")
        elif _gkf_fr - _gkf_cv >= 15.0:
            keys.append(
                f"A kapusuk a szabad lövéseket is fogja "
                f"({_gkf_fr:.0f}% védés, fedezett lövésnél "
                f"{_gkf_cv:.0f}%) — a távoli lövés ajándék neki: "
                "kidolgozott, közeli helyzetig kell játszani.")

    # Kettőzés: rálép-e a második védőjük a labdásra.
    if rep.dbl_holder_frames >= 250:
        _dbl = 100.0 * rep.dbl_doubled_frames / rep.dbl_holder_frames
        if _dbl >= 30.0:
            keys.append(
                f"Sokat kettőznek a labdáson (a labdás-idő "
                f"{_dbl:.0f}%-ában két védő is rálép, "
                f"{rep.dbl_forced_to} kikényszerített eladás) — a "
                "kettőzés ellen egy érintéssel kell játszani: gyors "
                "labdaeladás az üres oldalra, és a kettőzött játékos "
                "társa azonnal induljon a felszabadult helyre.")
        elif _dbl <= 10.0:
            keys.append(
                f"Nem kettőznek (csak a labdás-idő {_dbl:.0f}%-ában "
                "lép rá második védő) — 1v1-et hagynak: válasszátok "
                "ki a legjobb áttörőtöket, és menjetek rá "
                "ismételten ugyanarra a védőre.")

    # Kapus-indítás iránya: kiszámítható-e, merre nyit a kapusuk.
    if rep.gos_left + rep.gos_right >= 6:
        _gos_all = rep.gos_left + rep.gos_right
        _gos_share = rep.gos_left / _gos_all
        if _gos_share >= 0.65 or 1.0 - _gos_share >= 0.65:
            _gos_side = "bal" if _gos_share >= 0.65 else "jobb"
            _gos_pct = 100.0 * max(_gos_share, 1.0 - _gos_share)
            keys.append(
                f"A kapusuk szinte mindig a {_gos_side} oldalra indít "
                f"({_gos_pct:.0f}%, {_gos_all} indításból) — arra az "
                "oldalra kell előre elindulni: a fogadó szélsőjüket "
                "letámadva már a kidobásnál megfogható a lerohanásuk.")

    # Hajrá-eladás: nyomás alatt megőrzik-e a labdát.
    if rep.cto_early_to >= 5 and rep.cto_early_s > 0 \
            and rep.cto_clutch_s > 0:
        _cto_e = 60.0 * rep.cto_early_to / rep.cto_early_s
        _cto_c = 60.0 * rep.cto_clutch_to / rep.cto_clutch_s
        if _cto_c - _cto_e >= 0.3:
            keys.append(
                f"A hajrában széteseik a labdakezelésük (az "
                f"eladás-ütemük {_cto_e:.2f}-ről {_cto_c:.2f} "
                "eladás/percre ugrik) — a végén présbe kell tenni a "
                "labdavivőjüket: magasabb védekezés, kettőzés a "
                "felhozatalnál, és minden szerzés után futni.")
        elif _cto_e - _cto_c >= 0.3:
            keys.append(
                f"A hajrában hidegvérűek (az eladás-ütemük "
                f"{_cto_e:.2f}-ről {_cto_c:.2f}-re csökken) — a "
                "hibájukra várni hiba: a végén nektek kell gólt "
                "lőnötök, a saját támadásaitokat kell végigjátszani.")

    # Hátrány-támadás: kihúzzák-e a két percet, vagy megbénulnak.
    if rep.sha_seconds >= 90.0 and rep.sha_eq_seconds > 0:
        _sha = 60.0 * rep.sha_goals / rep.sha_seconds
        _sha_eq = 60.0 * rep.sha_eq_goals / rep.sha_eq_seconds
        if _sha_eq - _sha >= 0.15:
            keys.append(
                f"Emberhátrányban megbénulnak ({_sha:.2f} gól/perc, "
                f"egyenlő létszámnál {_sha_eq:.2f}) — minden "
                "kiharcolt kiállítás gólkülönbség: az emberelőnyt "
                "türelmesen, betanult figurából játsszátok végig.")
        else:
            keys.append(
                f"Emberhátrányban is támadnak ({_sha:.2f} gól/perc, "
                f"egyenlő létszámnál {_sha_eq:.2f}) — az emberelőny "
                "önmagában nem elég ellenük: kockázatos lövés nélkül, "
                "labdatartással kell végigjátszani a két percet, "
                "különben lerohanásból visszakapjátok.")

    # Fölény-befejezés: a fal ellen is veszélyesek-e.
    if rep.ovl_shots >= 5 and rep.ovl_set_shots >= 5:
        _ovl = 100.0 * rep.ovl_goals / rep.ovl_shots
        _set = 100.0 * rep.ovl_set_goals / rep.ovl_set_shots
        if _ovl - _set >= 15.0:
            keys.append(
                f"Létszámfölényben veszélyesek ({_ovl:.0f}% gólarány), "
                f"felállt fal ellen viszont csak {_set:.0f}% — "
                "kényszerítsétek őket felállt támadásba: minden "
                "befejezés után azonnali visszarendeződés-sprint, a "
                "szélsők is fussanak haza.")
        elif _set - _ovl >= 15.0:
            keys.append(
                f"A felállt falat is törik ({_set:.0f}% gólarány "
                f"ellene, fölényben {_ovl:.0f}%) — ellenük a puszta "
                "hazaérés kevés: kell a nyomás a lövő-távolságon "
                "kívül és a szoros emberfogás a fő befejezőn.")

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
        from .stats import player_plus_minus as _pm
        _fps = match.meta.fps if match.meta.fps > 0 else 25.0
        rep.pm_fps = _fps
        rep.player_plus_minus = [
            {"player_id": p["player_id"],
             "frames": round(p["minutes"] * 60.0 * _fps),
             "for": p["for"], "against": p["against"]}
            for p in _pm(match, config)[team.value]["players"]]
        from .tactics import formation_switching as _fsw
        fswrec = _fsw(match, config)[team.value]
        from .goalkeeper import keeper_involvement as _kiv
        kivrec = _kiv(match, config)[team.value]
        rep.kiv_spells = kivrec["attacks"]
        rep.kiv_with = kivrec["with_keeper"]
        from .attack_types import crossing_runs as _crx
        crxrec = _crx(match, config)[team.value]
        rep.crx_attacks = crxrec["attacks"]
        rep.crx_crosses = crxrec["crosses"]
        from .attack_types import wing_service as _wsv
        wsvrec = _wsv(match, config)[team.value]
        rep.wsv_receptions = wsvrec["receptions"]
        rep.wsv_running = wsvrec["running"]
        from .attack_types import pivot_service as _psv
        psvrec = _psv(match, config)[team.value]
        rep.psv_receptions = psvrec["receptions"]
        rep.psv_running = psvrec["running"]
        from .attack_types import fast_break_waves as _fbw
        fbwrec = _fbw(match, config)[team.value]
        rep.fbw_breaks = fbwrec["breaks"]
        rep.fbw_second = fbwrec["second"]
        from .attack_types import fast_break_headstart as _fbh
        fbhrec = _fbh(match, config)[team.value]
        rep.fbh_breaks = fbhrec["breaks"]
        rep.fbh_ahead = fbhrec["ahead"]
        from .defense import blocked_shooters as _bsh
        bshrec = _bsh(match, config)[team.value]
        rep.bsh_blocked = bshrec["blocked"]
        rep.bsh_shooters = {}
        for _bshrow in bshrec["shooters"]:
            _bshkey = (str(_bshrow["jersey"])
                       if _bshrow["jersey"] is not None
                       else "#" + str(_bshrow["player_id"]))
            rep.bsh_shooters[_bshkey] = _bshrow["blocked"]
        from .roles import assists_by_role as _abr
        abrrec = _abr(match, config)[team.value]
        rep.abr_assists = abrrec["assists"]
        rep.abr_roles = dict(abrrec["roles"])
        from .rules import susp_earner_roles as _sur
        surrec = _sur(match, config)[team.value]
        rep.sur_suspensions = surrec["suspensions"]
        rep.sur_roles = dict(surrec["roles"])
        from .defense import blocked_by_role as _bbr
        bbrrec = _bbr(match, config)[team.value]
        rep.bbr_blocked = bbrrec["blocked"]
        rep.bbr_roles = dict(bbrrec["roles"])
        from .goalkeeper import outlet_target_roles as _otr
        otrrec = _otr(match, config)[team.value]
        rep.otr_outlets = otrrec["outlets"]
        rep.otr_roles = dict(otrrec["roles"])
        from .attack_types import break_share_fade as _brf
        brfrec = _brf(match, config)[team.value]
        rep.brf_fh_attacks = brfrec["fh_attacks"]
        rep.brf_fh_breaks = brfrec["fh_breaks"]
        rep.brf_sh_attacks = brfrec["sh_attacks"]
        rep.brf_sh_breaks = brfrec["sh_breaks"]
        from .attack_types import wing_shot_depth as _wsd
        wsdrec = _wsd(match, config)[team.value]
        rep.wsd_shots = wsdrec["shots"]
        rep.wsd_depth_sum_m = wsdrec["depth_sum_m"]
        from .defense import doubling_defenders as _dtp
        dtprec = _dtp(match, config)[team.value]
        rep.dtp_frames = dtprec["doubled_frames"]
        rep.dtp_doublers = {}
        for _dtprow in dtprec["doublers"]:
            _dtpkey = (str(_dtprow["jersey"])
                       if _dtprow["jersey"] is not None
                       else "#" + str(_dtprow["player_id"]))
            rep.dtp_doublers[_dtpkey] = _dtprow["frames"]
        from .defense import beaten_defenders as _btn
        btnrec = _btn(match, config)[team.value]
        rep.btn_goals = btnrec["goals"]
        rep.btn_free = btnrec["free"]
        rep.btn_defenders = {}
        for _btnrow in btnrec["defenders"]:
            _btnkey = (str(_btnrow["jersey"])
                       if _btnrow["jersey"] is not None
                       else "#" + str(_btnrow["player_id"]))
            rep.btn_defenders[_btnkey] = _btnrow["beaten"]
        from .defense import unpressured_assists as _upa
        uparec = _upa(match, config)[team.value]
        rep.upa_assisted = uparec["assisted"]
        rep.upa_unpressured = uparec["unpressured"]
        from .substitutions import gap_punishment as _gpn
        gpnrec = _gpn(match, config)[team.value]
        rep.gpn_gap_s = gpnrec["gap_s"]
        rep.gpn_gaps = gpnrec["gaps"]
        rep.gpn_conceded = gpnrec["conceded"]
        from .defense import corridor_goals as _crg
        crgrec = _crg(match, config)[team.value]
        rep.crg_goals = crgrec["goals"]
        rep.crg_open = crgrec["open"]
        from .defense import conceded_tempo as _ctm
        ctmrec = _ctm(match, config)[team.value]
        rep.ctm_goals = ctmrec["goals"]
        rep.ctm_passes_sum = ctmrec["passes_sum"]
        from .defense import conceded_momentum as _cgm
        cgmrec = _cgm(match, config)[team.value]
        rep.cgm_goals = cgmrec["goals"]
        rep.cgm_running = cgmrec["running"]
        from .goalkeeper import wrongfooted_keeper as _wfk
        wfkrec = _wfk(match, config)[team.value]
        rep.wfk_goals = wfkrec["goals"]
        rep.wfk_fooled = wfkrec["fooled"]
        from .goalkeeper import reading_keeper as _rdk
        rdkrec = _rdk(match, config)[team.value]
        rep.rdk_saves = rdkrec["saves"]
        rep.rdk_read = rdkrec["read"]
        from .defense import double_punishment as _dbp
        dbprec = _dbp(match, config)[team.value]
        rep.dbp_doubled_frames = dbprec["doubled_frames"]
        rep.dbp_conceded_after = dbprec["conceded_after"]
        from .defense import stepout_punishment as _sop
        soprec = _sop(match, config)[team.value]
        rep.sop_goals = soprec["goals"]
        rep.sop_behind = soprec["behind_stepout"]
        from .momentum import punished_misses as _pmb
        pmbrec = _pmb(match, config)[team.value]
        rep.pmb_misses = pmbrec["misses"]
        rep.pmb_punished = pmbrec["punished"]
        from .goalkeeper import outlet_punishment as _olp
        olprec = _olp(match, config)[team.value]
        rep.olp_lost = olprec["lost"]
        rep.olp_punished = olprec["punished"]
        from .tactics import slow_attack_cost as _sac
        sacrec = _sac(match, config)[team.value]
        rep.sac_slow = sacrec["slow"]
        rep.sac_scored = sacrec["scored"]
        from .attack_types import balls_out as _obt
        rep.obt_out = _obt(match, config)[team.value]["out"]
        from .rules import suspensions_by_score as _sps
        spsrec = _sps(match, config)[team.value]
        rep.sps_tr = spsrec["trailing"]
        rep.sps_lead = spsrec["leading"]
        rep.sps_level = spsrec["level"]
        from .rules import sevens_by_score as _svs
        svsrec = _svs(match, config)[team.value]
        rep.svs_tr = svsrec["trailing"]
        rep.svs_lead = svsrec["leading"]
        rep.svs_level = svsrec["level"]
        from .attack_types import breaks_by_score as _bks
        bksrec = _bks(match, config)[team.value]
        rep.bks_tr_attacks = bksrec["trailing"]["attacks"]
        rep.bks_tr_breaks = bksrec["trailing"]["breaks"]
        rep.bks_rest_attacks = (bksrec["leading"]["attacks"]
                                + bksrec["level"]["attacks"])
        rep.bks_rest_breaks = (bksrec["leading"]["breaks"]
                               + bksrec["level"]["breaks"])
        from .goalkeeper import empty_net_by_score as _ens
        ensrec = _ens(match, config)[team.value]
        rep.ens_tr = ensrec["trailing"]
        rep.ens_lead = ensrec["leading"]
        rep.ens_level = ensrec["level"]
        from .goalkeeper import gk_save_streaks as _gst
        gstrec = _gst(match, config)[team.value]
        rep.gst_on_target = gstrec["on_target"]
        rep.gst_streaks = gstrec["streaks"]
        from .attack_types import assist_fade as _asf
        asfrec = _asf(match, config)[team.value]
        rep.asf_fh_goals = asfrec["fh_goals"]
        rep.asf_fh_assisted = asfrec["fh_assisted"]
        rep.asf_sh_goals = asfrec["sh_goals"]
        rep.asf_sh_assisted = asfrec["sh_assisted"]
        from .attack_types import second_chance_fade as _scf
        scfrec = _scf(match, config)[team.value]
        rep.scf_fh_misses = scfrec["fh_misses"]
        rep.scf_fh_won = scfrec["fh_won"]
        rep.scf_sh_misses = scfrec["sh_misses"]
        rep.scf_sh_won = scfrec["sh_won"]
        from .attack_types import AttackType as _AT
        from .attack_types import attack_mix_shift as _ams
        amsrec = _ams(match, config)[team.value]
        rep.ams_fh_attacks = amsrec["fh_attacks"]
        rep.ams_sh_attacks = amsrec["sh_attacks"]
        rep.ams_fh_break = amsrec["fh_mix"].get(_AT.FAST_BREAK.value, 0)
        rep.ams_sh_break = amsrec["sh_mix"].get(_AT.FAST_BREAK.value, 0)
        rep.ams_fh_quick = amsrec["fh_mix"].get(_AT.QUICK.value, 0)
        rep.ams_sh_quick = amsrec["sh_mix"].get(_AT.QUICK.value, 0)
        from .attack_types import pass_direction_by_score as _pds
        pdsrec = _pds(match, config)[team.value]
        rep.pds_lead_passes = pdsrec["leading"]["passes"]
        rep.pds_lead_back = pdsrec["leading"]["back"]
        rep.pds_rest_passes = (pdsrec["trailing"]["passes"]
                               + pdsrec["level"]["passes"])
        rep.pds_rest_back = (pdsrec["trailing"]["back"]
                             + pdsrec["level"]["back"])
        from .goalkeeper import gk_assists as _gka
        rep.gka_assists = _gka(match, config)[team.value]["assists"]
        from .event_detection import pass_length_by_score as _pls
        plsrec = _pls(match, config)[team.value]
        rep.pls_tr_passes = plsrec["trailing"]["passes"]
        rep.pls_tr_long = plsrec["trailing"]["long"]
        rep.pls_rest_passes = (plsrec["leading"]["passes"]
                               + plsrec["level"]["passes"])
        rep.pls_rest_long = (plsrec["leading"]["long"]
                             + plsrec["level"]["long"])
        from .tactics import defense_form_shift as _dfs
        dfsrec = _dfs(match, config)[team.value]
        rep.dfs_fh_attacks = dfsrec["fh_attacks"]
        rep.dfs_sh_attacks = dfsrec["sh_attacks"]
        rep.dfs_fh_labels = dict(dfsrec["fh_labels"])
        rep.dfs_sh_labels = dict(dfsrec["sh_labels"])
        from .tactics import attack_side_shift as _sds
        sdsrec = _sds(match, config)[team.value]
        rep.sds_fh_frames = sdsrec["fh_frames"]
        rep.sds_sh_frames = sdsrec["sh_frames"]
        rep.sds_fh_counts = dict(sdsrec["fh_counts"])
        rep.sds_sh_counts = dict(sdsrec["sh_counts"])
        from .attack_types import turnovers_by_score as _tbs
        tbsrec = _tbs(match, config)[team.value]
        rep.tbs_tr_attacks = tbsrec["trailing"]["attacks"]
        rep.tbs_tr_tos = tbsrec["trailing"]["turnovers"]
        rep.tbs_rest_attacks = (tbsrec["leading"]["attacks"]
                                + tbsrec["level"]["attacks"])
        rep.tbs_rest_tos = (tbsrec["leading"]["turnovers"]
                            + tbsrec["level"]["turnovers"])
        from .xg import defense_by_score as _dbs
        dbsrec = _dbs(match, config)[team.value]
        rep.dbs_lead_shots = dbsrec["leading"]["shots"]
        rep.dbs_lead_xg = dbsrec["leading"]["xg_sum"]
        rep.dbs_rest_shots = dbsrec["rest"]["shots"]
        rep.dbs_rest_xg = dbsrec["rest"]["xg_sum"]
        from .substitutions import subs_by_score as _sbs
        sbsrec = _sbs(match, config)[team.value]
        rep.sbs_lead_subs = sbsrec["lead_subs"]
        rep.sbs_rest_subs = sbsrec["rest_subs"]
        rep.sbs_lead_s = sbsrec["lead_s"]
        rep.sbs_rest_s = sbsrec["rest_s"]
        from .goalkeeper import outlet_pace_by_score as _ops
        opsrec = _ops(match, config)[team.value]
        rep.ops_lead_outlets = opsrec["lead"]["outlets"]
        rep.ops_lead_sum_s = opsrec["lead"]["sum_s"]
        rep.ops_rest_outlets = opsrec["rest"]["outlets"]
        rep.ops_rest_sum_s = opsrec["rest"]["sum_s"]
        from .substitutions import sub_gaps as _sbg
        rep.sbg_gap_s = _sbg(match, config)[team.value]["gap_s"]
        from .event_detection import assist_ranges as _asr
        asrrec = _asr(match, config)[team.value]
        rep.asr_assisted = asrrec["assisted"]
        rep.asr_long = asrrec["long"]
        from .goalkeeper import gk_rebound_control as _grc
        grcrec = _grc(match, config)[team.value]
        rep.grc_saves = grcrec["saves"]
        rep.grc_caught = grcrec["caught"]
        from .attack_types import long_attack_outcomes as _lao
        laorec = _lao(match, config)[team.value]
        rep.lao_n = laorec["long_attacks"]
        rep.lao_died = laorec["died"]
        from .attack_types import attack_headcount as _ahc
        ahcrec = _ahc(match, config)[team.value]
        rep.ahc_frames = ahcrec["frames"]
        rep.ahc_sum_up = round((ahcrec["avg_up"] or 0.0)
                               * ahcrec["frames"])
        from .defense import block_recoveries as _brc
        brcrec = _brc(match, config)[team.value]
        rep.brc_blocks = brcrec["blocks"]
        rep.brc_recovered = brcrec["recovered"]
        from .xg import big_chance_finishers as _bcf
        rep.bcf_players = [dict(pr) for pr in
                           _bcf(match, config)[team.value]["players"]]
        from .rules import post_seven_lapses as _psl
        pslrec = _psl(match, config)[team.value]
        rep.psl_sevens = pslrec["sevens_against"]
        rep.psl_extra = pslrec["extra_conceded"]
        from .attack_types import circulation_direction as _cir
        cirrec = _cir(match, config)[team.value]
        rep.cir_left = cirrec["left"]
        rep.cir_right = cirrec["right"]
        from .attack_types import screen_pairs as _scp
        rep.scp_pairs = [dict(pr) for pr in
                         _scp(match, config)[team.value]["pairs"]]
        from .defense import wing_closeouts as _wco
        wcorec = _wco(match, config)[team.value]
        rep.wco_shots = wcorec["shots"]
        rep.wco_sum_m = wcorec["sum_m"]
        from .momentum import drought_breakers as _drb
        rep.drb_players = [dict(pr) for pr in
                           _drb(match, config)[team.value]["players"]]
        from .momentum import hot_hands as _hh
        rep.hh_streaks = [dict(st) for st in
                          _hh(match, config)[team.value]["streaks"]]
        from .goalkeeper import gk_cold_streaks as _gcs
        gcsrec = _gcs(match, config)[team.value]
        rep.gcs_cold_faced = gcsrec["cold"]["faced"]
        rep.gcs_cold_saves = gcsrec["cold"]["saves"]
        rep.gcs_warm_faced = gcsrec["warm"]["faced"]
        rep.gcs_warm_saves = gcsrec["warm"]["saves"]
        from .attack_types import attack_vs_wall_height as _avw
        avwrec = _avw(match, config)[team.value]
        rep.avw_high_attacks = avwrec["high"]["attacks"]
        rep.avw_high_goals = avwrec["high"]["goals"]
        rep.avw_deep_attacks = avwrec["deep"]["attacks"]
        rep.avw_deep_goals = avwrec["deep"]["goals"]
        from .attack_types import break_sources as _bsrc
        rep.bsrc_sources = dict(
            _bsrc(match, config)[team.value]["sources"])
        from .goalkeeper import gk_goal_threat as _gkg
        gkgrec = _gkg(match, config)[team.value]
        rep.gkg_attempts = gkgrec["attempts"]
        rep.gkg_goals = gkgrec["goals"]
        from .stoppages import long_break_response as _lbr
        lbrrec = _lbr(match, config)[team.value]
        rep.lbr_breaks = lbrrec["breaks"]
        rep.lbr_for = lbrrec["goals_for"]
        rep.lbr_against = lbrrec["goals_against"]
        from .momentum import clutch_ball_hogs as _cbh
        cbhrec = _cbh(match, config)[team.value]
        rep.cbh_frames = cbhrec["frames"]
        rep.cbh_players = [dict(pr) for pr in cbhrec["players"]]
        from .momentum import quarter_profile as _qp
        qprec = _qp(match, config)[team.value]
        rep.qp_for = dict(qprec["for"])
        rep.qp_against = dict(qprec["against"])
        _qfps = match.meta.fps if match.meta.fps > 0 else 25.0
        rep.qp_min = ((match.frames[-1].t - match.frames[0].t)
                      / _qfps / 60.0) if match.frames else 0.0
        from .defense import pivot_guards as _pvg
        pvgrec = _pvg(match, config)[team.value]
        rep.pvg_frames = pvgrec["frames"]
        rep.pvg_guards = [dict(pr) for pr in pvgrec["guards"]]
        from .stoppages import timeout_sub_combo as _tsc
        tscrec = _tsc(match, config)[team.value]
        rep.tsc_timeouts = tscrec["timeouts"]
        rep.tsc_with_subs = tscrec["with_subs"]
        from .xg import shot_quality_by_score as _sqs
        sqsrec = _sqs(match, config)[team.value]
        rep.sqs_trail_shots = sqsrec["trail_shots"]
        rep.sqs_trail_sum_xg = ((sqsrec["trail_avg_xg"] or 0.0)
                                * sqsrec["trail_shots"])
        rep.sqs_other_shots = sqsrec["other_shots"]
        rep.sqs_other_sum_xg = ((sqsrec["other_avg_xg"] or 0.0)
                                * sqsrec["other_shots"])
        from .goalkeeper import gk_saves_by_score as _gks
        gksrec = _gks(match, config)[team.value]
        rep.gks_trail_faced = gksrec["trail"]["faced"]
        rep.gks_trail_saves = gksrec["trail"]["saves"]
        rep.gks_other_faced = gksrec["other"]["faced"]
        rep.gks_other_saves = gksrec["other"]["saves"]
        from .attack_types import width_by_score as _wbs
        wbsrec = _wbs(match, config)[team.value]
        rep.wbs_trail_frames = wbsrec["trail_frames"]
        rep.wbs_trail_sum_m = ((wbsrec["trail_avg_m"] or 0.0)
                               * wbsrec["trail_frames"])
        rep.wbs_other_frames = wbsrec["other_frames"]
        rep.wbs_other_sum_m = ((wbsrec["other_avg_m"] or 0.0)
                               * wbsrec["other_frames"])
        from .rules import post_powerplay as _ppp
        ppprec = _ppp(match, config)[team.value]
        rep.ppp_returns = ppprec["returns"]
        rep.ppp_for = ppprec["goals_for"]
        rep.ppp_against = ppprec["goals_against"]
        from .roles import turnovers_by_role as _tbr
        rep.tbr_roles = dict(_tbr(match, config)[team.value]["roles"])
        from .stats import distance_battle as _dbt
        dbtres = _dbt(match, config)
        rep.dbt_m = dbtres[team.value]["distance_m"]
        rep.dbt_opp_m = dbtres["away" if team.value == "home"
                               else "home"]["distance_m"]
        _dfps = match.meta.fps if match.meta.fps > 0 else 25.0
        rep.dbt_min = ((match.frames[-1].t - match.frames[0].t)
                       / _dfps / 60.0) if match.frames else 0.0
        from .roles import phase_specialists as _phs
        phsrec = _phs(match, config)[team.value]
        rep.phs_players = [dict(pr) for pr in phsrec["players"]]
        from .stats import sprint_threats as _spt
        sptrec = _spt(match, config)[team.value]
        rep.spt_players = [dict(pr) for pr in sptrec["players"]]
        from .goalkeeper import seven_keeper_swaps as _svk
        svkrec = _svk(match, config)[team.value]
        rep.svk_sevens = svkrec["sevens_against"]
        rep.svk_swaps = svkrec["swaps"]
        from .defense import advanced_defender as _adv
        advrec = _adv(match, config)[team.value]
        rep.adv_players = [
            {"player_id": r["player_id"], "jersey": r["jersey"],
             "frames": r["frames"],
             "depth_sum_m": r["avg_depth_m"] * r["frames"]}
            for r in advrec["players"]]
        from .momentum import restart_targets as _rst
        rstrec = _rst(match, config)[team.value]
        rep.rst_restarts = rstrec["restarts"]
        rep.rst_players = [dict(pr) for pr in rstrec["players"]]
        from .substitutions import swap_pairs as _swp
        swprec = _swp(match, config)[team.value]
        rep.swp_swaps = swprec["swaps"]
        rep.swp_pairs = [dict(pr) for pr in swprec["pairs"]]
        from .attack_types import pullback_rate as _pb
        pbrec = _pb(match, config)[team.value]
        rep.pb_entries = pbrec["entries"]
        rep.pb_pullbacks = pbrec["pullbacks"]
        from .defense import steal_launch as _stl
        stlrec = _stl(match, config)[team.value]
        rep.stl_steals = stlrec["steals"]
        rep.stl_fwd = stlrec["forward"]
        from .rules import sevens_fade as _s7f
        s7frec = _s7f(match, config)[team.value]
        rep.s7f_fh = s7frec["fh"]
        rep.s7f_sh = s7frec["sh"]
        from .xg import wall_fade as _wf
        wfrec = _wf(match, config)[team.value]
        rep.wf_fh_shots = wfrec["fh_shots"]
        rep.wf_fh_sum_xga = ((wfrec["fh_avg_xga"] or 0.0)
                             * wfrec["fh_shots"])
        rep.wf_sh_shots = wfrec["sh_shots"]
        rep.wf_sh_sum_xga = ((wfrec["sh_avg_xga"] or 0.0)
                             * wfrec["sh_shots"])
        from .momentum import bench_scoring as _ben
        benrec = _ben(match, config)[team.value]
        rep.ben_goals = benrec["goals"]
        rep.ben_bench = benrec["bench_goals"]
        from .defense import steal_types as _stt
        sttrec = _stt(match, config)[team.value]
        rep.stt_steals = sttrec["steals"]
        rep.stt_int = sttrec["interceptions"]
        from .xg import conceded_chance_quality as _ccq
        ccqrec = _ccq(match, config)[team.value]
        rep.ccq_shots = ccqrec["shots"]
        rep.ccq_sum_xga = (ccqrec["avg_xga"] or 0.0) * ccqrec["shots"]
        from .momentum import closing_attacks as _clo
        clorec = _clo(match, config)[team.value]
        rep.clo_attacks = clorec["attacks"]
        rep.clo_goals = clorec["goals"]
        from .attack_types import fast_break_conversion as _fbc
        fbcrec = _fbc(match, config)[team.value]
        rep.fbc_breaks = fbcrec["breaks"]
        rep.fbc_goals = fbcrec["goals"]
        from .momentum import half_openings as _hop
        hoprec = _hop(match, config)[team.value]
        rep.ho_for = hoprec["goals_for"]
        rep.ho_against = hoprec["goals_against"]
        from .stoppages import timeout_first_defense as _tfd
        tfdrec = _tfd(match, config)[team.value]
        rep.tfd_timeouts = tfdrec["timeouts"]
        rep.tfd_conceded = tfdrec["conceded"]
        from .defense import press_after_goal as _pag
        pagrec = _pag(match, config)[team.value]
        rep.pag_after_frames = pagrec["after_frames"]
        rep.pag_after_sum_m = ((pagrec["after_m"] or 0.0)
                               * pagrec["after_frames"])
        rep.pag_base_frames = pagrec["base_frames"]
        rep.pag_base_sum_m = ((pagrec["base_m"] or 0.0)
                              * pagrec["base_frames"])
        from .attack_types import buildup_time as _but
        butrec = _but(match, config)[team.value]
        rep.but_cases = butrec["cases"]
        rep.but_sum_s = (butrec["avg_s"] or 0.0) * butrec["cases"]
        from .defense import covered_shooters as _cov
        rep.covered_shooters = [
            dict(row)
            for row in _cov(match, config)[team.value]["players"]]
        from .decisions import pressure_sensitive_players as _psp
        rep.pressure_players = [
            dict(row)
            for row in _psp(match, config)[team.value]["players"]]
        from .defense import high_steal_players as _hsp
        rep.high_stealers = [
            dict(row)
            for row in _hsp(match, config)[team.value]["players"]]
        from .xg import wasteful_shooters as _wst
        rep.wasteful_shooters = [
            dict(row)
            for row in _wst(match, config)[team.value]["players"]]
        from .momentum import opening_lineup as _opl
        rep.opening_players = [
            {"player_id": p["player_id"], "jersey": p["jersey"],
             "frames": p["frames"]}
            for p in _opl(match, config)[team.value]["core"]]
        from .rules import seven_earner_roles as _ser
        rep.seven_earner_roles = dict(
            _ser(match, config)[team.value]["roles"])
        from .stoppages import timeout_first_attack as _tfa
        tfarec = _tfa(match, config)[team.value]
        rep.tfa_timeouts = tfarec["timeouts"]
        rep.tfa_goals = tfarec["goals"]
        from .attack_types import risky_passers as _rsk
        rep.risky_passers = [
            dict(row)
            for row in _rsk(match, config)[team.value]["players"]]
        from .attack_types import screen_setters as _scs
        rep.screen_setters = [
            dict(row)
            for row in _scs(match, config)[team.value]["players"]]
        from .goalkeeper import gk_early_saves as _gke
        gkerec = _gke(match, config)[team.value]
        rep.gke_early_faced = gkerec["early"]["faced"]
        rep.gke_early_saves = gkerec["early"]["saves"]
        rep.gke_rest_faced = gkerec["rest"]["faced"]
        rep.gke_rest_saves = gkerec["rest"]["saves"]
        from .rules import shorthanded_shooters as _shshoot
        rep.sh_shooters = [
            dict(row)
            for row in _shshoot(match, config)[team.value]["players"]]
        from .momentum import clutch_turnover_players as _ctp
        rep.clutch_losers = [
            dict(row)
            for row in _ctp(match, config)[team.value]["players"]]
        from .substitutions import substitution_triggers as _stg
        stgrec = _stg(match, config)[team.value]
        rep.stg_subs = stgrec["subs"]
        rep.stg_after = stgrec["after_conceded"]
        from .defense import defense_setup_time as _dst
        dstrec = _dst(match, config)[team.value]
        rep.dst_cases = dstrec["cases"]
        rep.dst_sum_s = round(
            (dstrec["avg_s"] or 0.0) * dstrec["cases"], 1)
        from .goalkeeper import gk_shorthanded_saves as _gsh
        gshrec = _gsh(match, config)[team.value]
        rep.gsh_sh_faced = gshrec["sh"]["faced"]
        rep.gsh_sh_saves = gshrec["sh"]["saves"]
        rep.gsh_eq_faced = gshrec["eq"]["faced"]
        rep.gsh_eq_saves = gshrec["eq"]["saves"]
        from .rules import powerplay_shooters as _pps
        rep.pp_shooters = [
            dict(row)
            for row in _pps(match, config)[team.value]["players"]]
        from .attack_types import shot_distance_fade as _sdf
        sdfrec = _sdf(match, config)[team.value]
        rep.sdf_fh_shots = sdfrec["fh_shots"]
        rep.sdf_fh_sum_m = round(
            (sdfrec["fh_avg_m"] or 0.0) * sdfrec["fh_shots"], 1)
        rep.sdf_sh_shots = sdfrec["sh_shots"]
        rep.sdf_sh_sum_m = round(
            (sdfrec["sh_avg_m"] or 0.0) * sdfrec["sh_shots"], 1)
        from .defense import conceded_by_attack_type as _cat
        rep.conceded_types = dict(
            _cat(match, config)[team.value]["types"])
        from .attack_types import breakthrough_players as _btp
        rep.breakthrough_players = [
            dict(row)
            for row in _btp(match, config)[team.value]["players"]]
        from .attack_types import double_pivot_usage as _dpv
        dpvrec = _dpv(match, config)[team.value]
        rep.dpv_attacks = dpvrec["attacks"]
        rep.dpv_double = dpvrec["double_attacks"]
        from .momentum import clutch_lineup as _cll
        rep.clutch_players = [
            {"player_id": p["player_id"], "jersey": p["jersey"],
             "frames": p["frames"]}
            for p in _cll(match, config)[team.value]["core"]]
        from .attack_types import fast_break_support as _fbs
        fbsrec = _fbs(match, config)[team.value]
        rep.fbs_breaks = fbsrec["breaks"]
        rep.fbs_sum_runners = round(
            (fbsrec["avg_runners"] or 0.0) * fbsrec["breaks"], 1)
        from .rules import gk_seven_directions as _g7d
        g7drec = _g7d(match, config)[team.value]
        rep.g7d_faced = {d: g7drec[d]["faced"]
                         for d in ("bal", "közép", "jobb")}
        rep.g7d_saved = {d: g7drec[d]["saved"]
                         for d in ("bal", "közép", "jobb")}
        from .attack_types import buildup_side as _bus
        busrec = _bus(match, config)[team.value]
        rep.bus_left = busrec["left"]
        rep.bus_center = busrec["center"]
        rep.bus_right = busrec["right"]
        from .attack_types import rebound_winners as _rbw
        rep.rebounders = [
            dict(row) for row in _rbw(match, config)[team.value]["off"]]
        from .attack_types import shooter_ranges as _shr
        rep.shooter_ranges = [
            {"player_id": p["player_id"], "jersey": p["jersey"],
             "shots": p["shots"],
             "sum_dist_m": round(p["avg_dist_m"] * p["shots"], 1)}
            for p in _shr(match, config)[team.value]["players"]]
        from .rules import shorthanded_shape as _shs
        rep.sh_shape = dict(_shs(match, config)[team.value]["labels"])
        from .rules import powerplay_pace as _ppp
        ppprec = _ppp(match, config)[team.value]
        rep.ppp_pp_attacks = ppprec["pp_attacks"]
        rep.ppp_pp_sum_s = round(
            (ppprec["pp_avg_s"] or 0.0) * ppprec["pp_attacks"], 1)
        rep.ppp_eq_attacks = ppprec["eq_attacks"]
        rep.ppp_eq_sum_s = round(
            (ppprec["eq_avg_s"] or 0.0) * ppprec["eq_attacks"], 1)
        from .stoppages import playing_time_profile as _ptp
        ptprec = _ptp(match, config)[team.value]
        rep.ptp_total_s = ptprec["total_s"]
        rep.ptp_stopped_s = ptprec["stopped_s"]
        rep.ptp_own_stoppages = ptprec["own_stoppages"]
        from .defense import defensive_aggression as _agr
        agrrec = _agr(match, config)[team.value]
        rep.agr_attacks = agrrec["attacks"]
        rep.agr_sevens = agrrec["sevens"]
        rep.agr_susp = agrrec["suspensions"]
        from .defense import recovery_discipline as _rcd
        rep.recovery_players = [
            {"player_id": p["player_id"], "jersey": p["jersey"],
             "frames": p["frames"], "home_frames": p["home_frames"]}
            for p in _rcd(match, config)[team.value]["players"]]
        from .goalkeeper import gk_saves_by_speed as _gsp
        gsprec = _gsp(match, config)[team.value]
        rep.gsp_hard_faced = gsprec["hard"]["faced"]
        rep.gsp_hard_saves = gsprec["hard"]["saves"]
        rep.gsp_placed_faced = gsprec["placed"]["faced"]
        rep.gsp_placed_saves = gsprec["placed"]["saves"]
        from .tactics import static_attackers as _sta
        rep.static_attackers = [
            {"player_id": p["player_id"], "jersey": p["jersey"],
             "seconds": p["seconds"],
             "dist_m": round(p["avg_mps"] * p["seconds"], 1)}
            for p in _sta(match, config)[team.value]["players"]]
        from .attack_types import wing_finishing_by_side as _wfs
        wfsrec = _wfs(match, config)[team.value]
        rep.wfs_left_shots = wfsrec["bal"]["shots"]
        rep.wfs_left_goals = wfsrec["bal"]["goals"]
        rep.wfs_right_shots = wfsrec["jobb"]["shots"]
        rep.wfs_right_goals = wfsrec["jobb"]["goals"]
        from .attack_types import pivot_side as _pvs
        pvsrec = _pvs(match, config)[team.value]
        rep.pvs_left = pvsrec["left"]
        rep.pvs_center = pvsrec["center"]
        rep.pvs_right = pvsrec["right"]
        from .defense import defensive_shift_lag as _dsl
        dslrec = _dsl(match, config)[team.value]
        if dslrec["lag_s"] is not None:
            rep.dsl_frames = dslrec["frames"]
            rep.dsl_sum_s = round(dslrec["lag_s"] * dslrec["frames"], 1)
        from .decisions import pass_speed as _psp
        psprec = _psp(match, config)[team.value]
        rep.psp_passes = psprec["passes"]
        rep.psp_sum_ms = round(
            (psprec["avg_ms"] or 0.0) * psprec["passes"], 1)
        rep.psp_fast = psprec["fast"]
        from .attack_types import pivot_feeders as _pfd
        rep.pivot_feeders = [
            {"player_id": p["player_id"], "jersey": p["jersey"],
             "feeds": p["feeds"]}
            for p in _pfd(match, config)[team.value]["players"]]
        from .rules import seven_meter_conceders as _smc
        rep.seven_conceders = [
            dict(row) for row in _smc(match, config)[team.value]["players"]]
        from .attack_types import attack_depth as _adp
        adprec = _adp(match, config)[team.value]
        if adprec["avg_depth_m"] is not None:
            rep.adp_frames = adprec["frames"]
            rep.adp_sum_m = round(
                adprec["avg_depth_m"] * adprec["frames"], 1)
        from .attack_types import wing_involvement as _win
        winrec = _win(match, config)[team.value]
        rep.wi_attacks = winrec["attacks"]
        rep.wi_with_wing = winrec["with_wing"]
        from .defense import line_height_by_score as _lhs
        lhsrec = _lhs(match, config)[team.value]
        rep.lhs_lead_frames = lhsrec["leading"]["frames"]
        rep.lhs_lead_sum_m = round(
            (lhsrec["leading"]["avg_height_m"] or 0.0)
            * lhsrec["leading"]["frames"], 1)
        rep.lhs_trail_frames = lhsrec["trailing"]["frames"]
        rep.lhs_trail_sum_m = round(
            (lhsrec["trailing"]["avg_height_m"] or 0.0)
            * lhsrec["trailing"]["frames"], 1)
        from .attack_types import attack_outcomes as _aou
        rep.attack_outcomes = dict(
            _aou(match, config)[team.value]["outcomes"])
        from .goalkeeper import gk_saves_by_role as _gsr
        rep.gk_role_saves = {
            poszt: {"faced": r["faced"], "saves": r["saves"]}
            for poszt, r in _gsr(match, config)[team.value]["roles"].items()}
        from .defense import turnover_clusters as _tcl
        tclrec = _tcl(match, config)[team.value]
        rep.tc_turnovers = tclrec["turnovers"]
        rep.tc_clustered = tclrec["clustered"]
        rep.tc_clusters = tclrec["clusters"]
        from .defense import conceded_by_role as _cbr
        rep.conceded_roles = dict(_cbr(match, config)[team.value]["roles"])
        from .roles import goals_by_role as _gbr
        rep.role_goals = dict(_gbr(match, config)[team.value]["roles"])
        from .event_detection import assist_zones as _azn
        rep.assist_zones = dict(_azn(match, config)[team.value]["zones"])
        from .attack_types import attack_starters as _ast
        rep.starters = [
            {"player_id": p["player_id"], "jersey": p["jersey"],
             "starts": p["starts"]}
            for p in _ast(match, config)[team.value]["players"]]
        from .stoppages import timeout_timing as _tot
        totrec = _tot(match, config)[team.value]
        rep.tot_timeouts = totrec["timeouts"]
        rep.tot_sum_before = totrec["sum_before"]
        rep.tot_late = totrec["late_timeouts"]
        from .stats import pair_plus_minus as _prm
        _pfps = match.meta.fps if match.meta.fps > 0 else 25.0
        rep.pair_fps = _pfps
        rep.pair_plus_minus = [
            {"players": p["players"],
             "frames": round(p["minutes"] * 60.0 * _pfps),
             "for": p["for"], "against": p["against"]}
            for p in _prm(match, config)[team.value]["pairs"]
            if p["minutes"] * 60.0 >= 60.0]
        from .substitutions import substitution_blocks as _sbl
        sblrec = _sbl(match, config)[team.value]
        rep.sbl_waves = sblrec["waves"]
        rep.sbl_players = sblrec["players"]
        rep.sbl_block_waves = sblrec["block_waves"]
        from .decisions import hold_time_players as _htp
        _hfps = match.meta.fps if match.meta.fps > 0 else 25.0
        rep.hold_fps = _hfps
        rep.hold_players = [
            {"player_id": p["player_id"], "jersey": p["jersey"],
             "holds": p["holds"],
             "frames": round(p["seconds"] * _hfps)}
            for p in _htp(match, config)[team.value]["players"]]
        rep.fsw_labels = dict(fswrec["labels"])
        rep.fsw_attacks = fswrec["attacks"]
        rep.fsw_pairs = max(0, fswrec["attacks"] - 1)
        rep.fsw_switches = fswrec["switches"]
        from .defense import targeted_defenders as _tdf
        tdfrec = _tdf(match, config)[team.value]
        rep.tdf_shots = tdfrec["shots"]
        rep.tdf_goals = tdfrec["goals"]
        rep.targeted_defenders = [
            {"player_id": p["player_id"], "jersey": p["jersey"],
             "shots": p["shots"], "goals": p["goals"]}
            for p in tdfrec["players"]]
        from .event_detection import shooter_power as _spw
        spwrec = _spw(match, config)[team.value]
        rep.shooter_power = [
            {"player_id": p["player_id"], "shots": p["shots"],
             "sum_kmh": round(p["avg_kmh"] * p["shots"], 1),
             "max_kmh": p["max_kmh"]}
            for p in spwrec["players"]]
        rep.spw_team_shots = sum(p["shots"] for p in spwrec["players"])
        rep.spw_team_sum_kmh = round(
            sum(p["avg_kmh"] * p["shots"] for p in spwrec["players"]), 1)
        from .attack_types import shooter_placement as _shp
        rep.shooter_placement = [
            {"player_id": p["player_id"], "goals": p["goals"],
             "bal": p["bal"], "közép": p["közép"], "jobb": p["jobb"]}
            for p in _shp(match, config)[team.value]["players"]]
        from .defense import wing_defense
        wdfrec = wing_defense(match, config)[team.value]
        rep.wdf_wing_shots = wdfrec["wing_shots"]
        rep.wdf_wing_goals = wdfrec["wing_goals"]
        rep.wdf_center_shots = wdfrec["center_shots"]
        rep.wdf_center_goals = wdfrec["center_goals"]
        from .defense import costly_turnover_players as _ctp
        rep.costly_turnover_players = _ctp(match, config)[team.value][
            "players"]
        from .rules import powerplay_defense
        ppdrec = powerplay_defense(match, config)[team.value]
        rep.ppd_seconds = ppdrec["pp_seconds"]
        rep.ppd_conceded = ppdrec["pp_conceded"]
        rep.ppd_eq_seconds = ppdrec["eq_seconds"]
        rep.ppd_eq_conceded = ppdrec["eq_conceded"]
        from .goalkeeper import gk_free_shot_saves
        gkfrec = gk_free_shot_saves(match, config)[team.value]
        rep.gkf_free_shots = gkfrec["free_shots"]
        rep.gkf_free_saves = gkfrec["free_saves"]
        rep.gkf_cov_shots = gkfrec["covered_shots"]
        rep.gkf_cov_saves = gkfrec["covered_saves"]
        from .defense import double_teams
        dblrec = double_teams(match, config)[team.value]
        rep.dbl_holder_frames = dblrec["holder_frames"]
        rep.dbl_doubled_frames = dblrec["doubled_frames"]
        rep.dbl_forced_to = dblrec["forced_turnovers"]
        from .goalkeeper import gk_outlet_side
        gosrec = gk_outlet_side(match, config)[team.value]
        rep.gos_left = gosrec["left"]
        rep.gos_right = gosrec["right"]
        from .momentum import clutch_turnovers
        ctoall = clutch_turnovers(match, config)
        if ctoall.get("available"):
            ctorec = ctoall[team.value]
            rep.cto_early_to = ctorec["early_to"]
            rep.cto_early_s = ctorec["early_s"]
            rep.cto_clutch_to = ctorec["clutch_to"]
            rep.cto_clutch_s = ctorec["clutch_s"]
        from .rules import shorthanded_attack
        sharec = shorthanded_attack(match, config)[team.value]
        rep.sha_seconds = sharec["sh_seconds"]
        rep.sha_shots = sharec["sh_shots"]
        rep.sha_goals = sharec["sh_goals"]
        rep.sha_eq_seconds = sharec["eq_seconds"]
        rep.sha_eq_goals = sharec["eq_goals"]
        from .attack_types import overload_finishing
        ovlrec = overload_finishing(match, config)[team.value]
        rep.ovl_shots = ovlrec["overload_shots"]
        rep.ovl_goals = ovlrec["overload_goals"]
        rep.ovl_set_shots = ovlrec["set_shots"]
        rep.ovl_set_goals = ovlrec["set_goals"]
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


def _merge_plus_minus(reports) -> list:
    """Játékos-mérleg: pályán töltött kockák és a rájuk eső gólok
    játékosonkénti összegzése (a mérleg szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for p in (r.player_plus_minus or []):
            rec = tally.setdefault(p["player_id"],
                                   {"frames": 0, "for": 0, "against": 0})
            for k in ("frames", "for", "against"):
                rec[k] += int(p.get(k, 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(
                tally.items(),
                key=lambda kv: -(kv[1]["for"] - kv[1]["against"]))]


def _merge_pp_shooters_rows(reports, field_name: str) -> list:
    """Lövő-sorok (lövés + gól) összegzése játékosonként, a lövésszám
    szerint csökkenő sorrendben."""
    tally: dict = {}
    for r in reports:
        for row in (getattr(r, field_name, None) or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "shots": 0,
                                    "goals": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["shots"] += int(row.get("shots", 0))
            rec["goals"] += int(row.get("goals", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["shots"])]


def _merge_clutch_losers(reports) -> list:
    """Hajrá-hibázók: játékosonként a hajrá-eladások összegzése (a
    darabszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for row in (r.clutch_losers or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "turnovers": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["turnovers"] += int(row.get("turnovers", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["turnovers"])]


def _merge_pp_shooters(reports) -> list:
    """Emberelőny-lövők: játékosonként a lövések és a gólok összegzése
    (a lövésszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for row in (r.pp_shooters or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "shots": 0,
                                    "goals": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["shots"] += int(row.get("shots", 0))
            rec["goals"] += int(row.get("goals", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["shots"])]


def _merge_conceded_types(reports) -> dict:
    """Kapott gólok támadás-típus szerint: típusonkénti összegzés (a
    gólszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for typ, n in (r.conceded_types or {}).items():
            tally[typ] = tally.get(typ, 0) + int(n)
    return dict(sorted(tally.items(), key=lambda kv: -kv[1]))


def _merge_breakthrough_players(reports) -> list:
    """Áttörő játékosok: játékosonként a betörések és a gólos
    támadások összegzése (a betörésszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for row in (r.breakthrough_players or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "entries": 0,
                                    "goals": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["entries"] += int(row.get("entries", 0))
            rec["goals"] += int(row.get("goals", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["entries"])]


def _merge_covered_shooters(reports) -> list:
    """Fedezetten lövők: játékosonként a lövések és a fedezett
    lövések összegzése (a fedezett lövés szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for row in (r.covered_shooters or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "shots": 0,
                                    "covered": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["shots"] += int(row.get("shots", 0))
            rec["covered"] += int(row.get("covered", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["covered"])]


def _merge_pressure_players(reports) -> list:
    """Pressz-érzékeny játékosok: játékosonként a nyomott döntések és
    az azokból lett eladások összegzése (az eladás szerint
    csökkenő)."""
    tally: dict = {}
    for r in reports:
        for row in (r.pressure_players or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "press_events": 0,
                                    "press_to": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["press_events"] += int(row.get("press_events", 0))
            rec["press_to"] += int(row.get("press_to", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["press_to"])]


def _merge_high_stealers(reports) -> list:
    """Elöl szerző védők: játékosonként a szerzések és az elöl
    szerzettek összegzése (az elöl-szerzés szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for row in (r.high_stealers or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "steals": 0,
                                    "high": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["steals"] += int(row.get("steals", 0))
            rec["high"] += int(row.get("high", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["high"])]


def _merge_wasteful_shooters(reports) -> list:
    """Pontatlan lövők: játékosonként a lövések és a kaput elkerülő
    lövések összegzése (a mellé-lövés szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for row in (r.wasteful_shooters or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "shots": 0,
                                    "off_target": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["shots"] += int(row.get("shots", 0))
            rec["off_target"] += int(row.get("off_target", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["off_target"])]


def _merge_clutch_players_rows(reports, field_name: str) -> list:
    """Játékos-kocka sorok összegzése (a kockaszám szerint
    csökkenő) — a kezdő és a hajrá-emberekhez egyaránt."""
    tally: dict = {}
    for r in reports:
        for row in (getattr(r, field_name, None) or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "frames": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["frames"] += int(row.get("frames", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["frames"])]


def _merge_clutch_players(reports) -> list:
    """Hajrá-emberek: játékosonként a hajrában töltött kockák
    összegzése (a kockaszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for row in (r.clutch_players or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "frames": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["frames"] += int(row.get("frames", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["frames"])]


def _merge_dir_counts(reports, field_name: str) -> dict:
    """Irány szerinti darabszámok összegzése (bal / közép / jobb)."""
    tally: dict = {}
    for r in reports:
        for d, n in (getattr(r, field_name, None) or {}).items():
            tally[d] = tally.get(d, 0) + int(n)
    return tally


def _merge_rebounders(reports) -> list:
    """Lepattanó-szerzők: játékosonként a visszaszerzett kipattanók
    összegzése (a darabszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for row in (r.rebounders or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "rebounds": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["rebounds"] += int(row.get("rebounds", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["rebounds"])]


def _merge_shooter_ranges(reports) -> list:
    """Lövő-távolság profil: lövőnként a lövések és a távolság-összeg
    összegzése (az átlagtávolság szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for row in (r.shooter_ranges or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "shots": 0,
                                    "sum_dist_m": 0.0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["shots"] += int(row.get("shots", 0))
            rec["sum_dist_m"] += float(row.get("sum_dist_m", 0.0))
    rows = [{"player_id": pid, "jersey": rec["jersey"],
             "shots": rec["shots"],
             "sum_dist_m": round(rec["sum_dist_m"], 1)}
            for pid, rec in tally.items() if rec["shots"] > 0]
    rows.sort(key=lambda r: -(r["sum_dist_m"] / r["shots"]))
    return rows


def _merge_sh_shape(reports) -> dict:
    """Emberhátrány-forma: formánként a mért kockák összegzése (a
    kockaszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for label, n in (r.sh_shape or {}).items():
            tally[label] = tally.get(label, 0) + int(n)
    return dict(sorted(tally.items(), key=lambda kv: -kv[1]))


def _merge_recovery_players(reports) -> list:
    """Visszaérés-fegyelem: játékosonként a védekezett és a saját
    térfélen töltött kockák összegzése (az arány szerint NÖVEKVŐ)."""
    tally: dict = {}
    for r in reports:
        for row in (r.recovery_players or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "frames": 0,
                                    "home_frames": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["frames"] += int(row.get("frames", 0))
            rec["home_frames"] += int(row.get("home_frames", 0))
    rows = [{"player_id": pid, **rec}
            for pid, rec in tally.items() if rec["frames"] > 0]
    rows.sort(key=lambda r: r["home_frames"] / r["frames"])
    return rows


def _merge_static_attackers(reports) -> list:
    """Álló támadók: játékosonként a támadásban mért idő és út
    összegzése (az átlagsebesség szerint NÖVEKVŐ)."""
    tally: dict = {}
    for r in reports:
        for row in (r.static_attackers or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "seconds": 0.0,
                                    "dist_m": 0.0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["seconds"] += float(row.get("seconds", 0.0))
            rec["dist_m"] += float(row.get("dist_m", 0.0))
    rows = [{"player_id": pid, "jersey": rec["jersey"],
             "seconds": round(rec["seconds"], 1),
             "dist_m": round(rec["dist_m"], 1)}
            for pid, rec in tally.items() if rec["seconds"] > 0]
    rows.sort(key=lambda r: r["dist_m"] / r["seconds"])
    return rows


def _merge_pivot_feeders(reports) -> list:
    """Beálló-kiszolgálók: játékosonként a beadások összegzése (a
    darabszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for row in (r.pivot_feeders or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "feeds": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["feeds"] += int(row.get("feeds", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["feeds"])]


def _merge_seven_conceders(reports) -> list:
    """Hetes-okozó védők: védőnként az okozott hetesek összegzése (a
    darabszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for row in (r.seven_conceders or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "conceded": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["conceded"] += int(row.get("conceded", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["conceded"])]


def _merge_attack_outcomes(reports) -> dict:
    """Támadás-kimenetel: kimenetelenként a támadások összegzése (a
    darabszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for kind, n in (r.attack_outcomes or {}).items():
            tally[kind] = tally.get(kind, 0) + int(n)
    return dict(sorted(tally.items(), key=lambda kv: -kv[1]))


def _merge_gk_role_saves(reports) -> dict:
    """Kapus-védés posztonként: posztonként a kapura tartó lövések és a
    védések összegzése (a lövésszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for poszt, rec in (r.gk_role_saves or {}).items():
            acc = tally.setdefault(poszt, {"faced": 0, "saves": 0})
            acc["faced"] += int(rec.get("faced", 0))
            acc["saves"] += int(rec.get("saves", 0))
    return dict(sorted(tally.items(), key=lambda kv: -kv[1]["faced"]))


def _merge_conceded_roles(reports) -> dict:
    """Kapott gólok posztonként: posztonként a kapott gólok összegzése
    (a gólszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for poszt, n in (r.conceded_roles or {}).items():
            tally[poszt] = tally.get(poszt, 0) + int(n)
    return dict(sorted(tally.items(), key=lambda kv: -kv[1]))


def _merge_role_goals(reports) -> dict:
    """Poszt szerinti gólmegoszlás: posztonként a gólok összegzése (a
    gólszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for poszt, n in (r.role_goals or {}).items():
            tally[poszt] = tally.get(poszt, 0) + int(n)
    return dict(sorted(tally.items(), key=lambda kv: -kv[1]))


def _merge_assist_zones(reports) -> dict:
    """Gólpassz-zónák: zónánként az előkészítések összegzése (a
    gólpassz-szám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for zone, n in (r.assist_zones or {}).items():
            tally[zone] = tally.get(zone, 0) + int(n)
    return dict(sorted(tally.items(), key=lambda kv: -kv[1]))


def _merge_starters(reports) -> list:
    """Támadás-indítók: játékosonként az indítások összegzése (az
    indítás-szám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for p in (r.starters or []):
            rec = tally.setdefault(p["player_id"],
                                   {"jersey": None, "starts": 0})
            if rec["jersey"] is None:
                rec["jersey"] = p.get("jersey")
            rec["starts"] += int(p.get("starts", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["starts"])]


def _merge_pair_plus_minus(reports) -> list:
    """Páros-mérleg: párosonként az együtt töltött kockák és a rájuk
    eső gólok összegzése (a mérleg szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for p in (r.pair_plus_minus or []):
            key = tuple(sorted(p["players"]))
            rec = tally.setdefault(key, {"frames": 0, "for": 0,
                                         "against": 0})
            for k in ("frames", "for", "against"):
                rec[k] += int(p.get(k, 0))
    return [{"players": list(key), **rec}
            for key, rec in sorted(
                tally.items(),
                key=lambda kv: -(kv[1]["for"] - kv[1]["against"]))]


def _merge_hold_players(reports) -> list:
    """Labdatartás: játékosonként a labdás szakaszok és a bennük
    töltött kockák összegzése (az átlagos tartás szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for p in (r.hold_players or []):
            rec = tally.setdefault(p["player_id"],
                                   {"jersey": None, "holds": 0,
                                    "frames": 0})
            if rec["jersey"] is None:
                rec["jersey"] = p.get("jersey")
            rec["holds"] += int(p.get("holds", 0))
            rec["frames"] += int(p.get("frames", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(
                tally.items(),
                key=lambda kv: -(kv[1]["frames"]
                                 / max(1, kv[1]["holds"])))]


def _merge_fsw_labels(reports) -> dict:
    """Védekezés-váltás: formánként a védekezett támadások összegzése
    (a támadás-szám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for lab, n in (r.fsw_labels or {}).items():
            tally[lab] = tally.get(lab, 0) + int(n)
    return dict(sorted(tally.items(), key=lambda kv: -kv[1]))


def _merge_targeted_defenders(reports) -> list:
    """Célba vett védők: védőnként a rá eső kapott lövések és gólok
    összegzése (a lövésszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for p in (r.targeted_defenders or []):
            rec = tally.setdefault(p["player_id"],
                                   {"jersey": None, "shots": 0,
                                    "goals": 0})
            if rec["jersey"] is None:
                rec["jersey"] = p.get("jersey")
            rec["shots"] += int(p.get("shots", 0))
            rec["goals"] += int(p.get("goals", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(
                tally.items(),
                key=lambda kv: (-kv[1]["shots"], -kv[1]["goals"]))]


def _merge_shooter_power(reports) -> list:
    """Lövő-erő: játékosonként a lövésszám és a sebesség-összeg
    összegzése (az átlag ebből pontosan visszaszámolható)."""
    tally: dict = {}
    for r in reports:
        for p in (r.shooter_power or []):
            rec = tally.setdefault(p["player_id"],
                                   {"shots": 0, "sum_kmh": 0.0,
                                    "max_kmh": 0.0})
            rec["shots"] += int(p["shots"])
            rec["sum_kmh"] += float(p["sum_kmh"])
            rec["max_kmh"] = max(rec["max_kmh"], float(p["max_kmh"]))
    return [{"player_id": pid, "shots": rec["shots"],
             "sum_kmh": round(rec["sum_kmh"], 1),
             "max_kmh": rec["max_kmh"]}
            for pid, rec in sorted(
                tally.items(),
                key=lambda kv: -(kv[1]["sum_kmh"]
                                 / max(1, kv[1]["shots"])))]


def _merge_shooter_placement(reports) -> list:
    """Lövő-kapuoldal: játékosonként és oldalanként összegzett gólok
    (a lista gólszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for p in (r.shooter_placement or []):
            rec = tally.setdefault(p["player_id"],
                                   {"goals": 0, "bal": 0, "közép": 0,
                                    "jobb": 0})
            for k in ("goals", "bal", "közép", "jobb"):
                rec[k] += int(p.get(k, 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["goals"])]


def _merge_costly_turnovers(reports) -> list:
    """Drága eladók: játékosonként az eladások és a gólba kerültek
    összege (a lista a gólba kerültek szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for w in (r.costly_turnover_players or []):
            rec = tally.setdefault(w["player_id"],
                                   {"turnovers": 0, "punished": 0})
            rec["turnovers"] += int(w["turnovers"])
            rec["punished"] += int(w["punished"])
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: (-kv[1]["punished"],
                                                   -kv[1]["turnovers"]))]


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


def _merge_earner_roles(reports) -> dict:
    """Hetes-kiharcolás poszt szerint: posztonkénti összegzés (a
    darabszám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for poszt, n in (r.seven_earner_roles or {}).items():
            tally[poszt] = tally.get(poszt, 0) + int(n)
    return dict(sorted(tally.items(), key=lambda kv: -kv[1]))


def _merge_risky_passers(reports) -> list:
    """Kockázatos passzolók: játékosonként a hosszú kísérletek és az
    eladások összegzése (az eladás-szám szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for row in (r.risky_passers or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "tries": 0,
                                    "turnovers": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["tries"] += int(row.get("tries", 0))
            rec["turnovers"] += int(row.get("turnovers", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["turnovers"])]


def _merge_screen_setters(reports) -> list:
    """Elzárók: játékosonként az elzárások összegzése (a darabszám
    szerint csökkenő)."""
    tally: dict = {}
    for r in reports:
        for row in (r.screen_setters or []):
            rec = tally.setdefault(row["player_id"],
                                   {"jersey": None, "screens": 0})
            if rec["jersey"] is None:
                rec["jersey"] = row.get("jersey")
            rec["screens"] += int(row.get("screens", 0))
    return [{"player_id": pid, **rec}
            for pid, rec in sorted(tally.items(),
                                   key=lambda kv: -kv[1]["screens"])]


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

    # 241) Az ő szünet utáni oldal-váltásuk × a ti falat váltó
    # védekezésetek: a súlypont-olvasás nálatok rutin.
    def _sds241_main(cnt, n):
        if n < 100 or not cnt:
            return None
        m241, c241 = max(cnt.items(), key=lambda kv: kv[1])
        return m241 if 100.0 * c241 / n >= 40.0 else None
    _sds241_fh = _sds241_main(opp.sds_fh_counts, opp.sds_fh_frames)
    _sds241_sh = _sds241_main(opp.sds_sh_counts, opp.sds_sh_frames)
    def _dfs241_main(labels, n):
        if n < 5 or not labels:
            return None
        m241b, c241b = max(labels.items(), key=lambda kv: kv[1])
        return m241b if 100.0 * c241b / n >= 60.0 else None
    if (_sds241_fh and _sds241_sh and _sds241_fh != _sds241_sh
            and _dfs241_main(own.dfs_fh_labels, own.dfs_fh_attacks)
            and _dfs241_main(own.dfs_sh_labels, own.dfs_sh_attacks)):
        plan.append(
            f"A szünet után oldalt váltanak ({_sds241_fh} → "
            f"{_sds241_sh}), a ti falatok pedig bizonyítottan tud "
            "átrendeződni (félidőnként stabil, kimondható formát "
            "játszotok) — a szünetben készítsétek elő a tükrözést: "
            "az erős védőtök és a kettőzés az új súlypont-oldalra "
            "kerüljön, és az első öt perc után hangos megerősítés.")

    # 240) Az ő szünet utáni fal-váltásuk × a ti bizonyított
    # játék-váltásotok: két figurasor, és nem ér meglepetés.
    def _dfs240_main(labels, n):
        if n < 5 or not labels:
            return None
        m240, c240 = max(labels.items(), key=lambda kv: kv[1])
        return m240 if 100.0 * c240 / n >= 60.0 else None
    _dfs240_fh = _dfs240_main(opp.dfs_fh_labels, opp.dfs_fh_attacks)
    _dfs240_sh = _dfs240_main(opp.dfs_sh_labels, opp.dfs_sh_attacks)
    if (_dfs240_fh and _dfs240_sh and _dfs240_fh != _dfs240_sh
            and own.ams_fh_attacks >= 6 and own.ams_sh_attacks >= 6):
        _ams240 = (abs(100.0 * own.ams_fh_break / own.ams_fh_attacks
                       - 100.0 * own.ams_sh_break
                       / own.ams_sh_attacks)
                   + abs(100.0 * own.ams_fh_quick
                         / own.ams_fh_attacks
                         - 100.0 * own.ams_sh_quick
                         / own.ams_sh_attacks)) / 2.0
        if _ams240 >= 30.0:
            plan.append(
                f"A szünet után falat váltanak ({_dfs240_fh} → "
                f"{_dfs240_sh}), ti pedig bizonyítottan tudtok "
                "játékot váltani (a saját támadás-mixetek is "
                "átrendeződik a szünetre) — két kész figurasorral "
                "érkezzetek, és a szünet utáni első támadásnál "
                "hangos forma-bemondás: nem érhet meglepetés.")

    # 239) Az ő hátrány-hosszúlabdáik × a ti passzsáv-zárásotok: az
    # átdobált labda a tiétek.
    if (opp.pls_tr_passes >= 10 and opp.pls_rest_passes >= 10
            and own.stt_steals >= 6):
        _pls239_tr = 100.0 * opp.pls_tr_long / opp.pls_tr_passes
        _pls239_rest = (100.0 * opp.pls_rest_long
                        / opp.pls_rest_passes)
        _stt239 = 100.0 * own.stt_int / max(1, own.stt_steals)
        if _pls239_tr - _pls239_rest >= 12.0 and _stt239 >= 60.0:
            plan.append(
                f"Hátrányban hosszú labdákra váltanak (hosszú passz "
                f"{_pls239_tr:.0f}% vs {_pls239_rest:.0f}%), ti pedig "
                f"a passzsávokat zárjátok (a szerzéseitek "
                f"{_stt239:.0f}%-a elfogás) — ha vezettek, a belsők "
                "üljenek a hosszú sávokra: az átdobált labdájuk "
                "levegőben a tiétek, és kontra a vége.")

    # 238) Az ő kapus-gólpasszaik × a ti visszazárásotok: a hosszú
    # kéz sávja elvágható.
    if (opp.gka_assists >= 2 and own.transition_turnovers >= 5):
        _gka238 = (100.0 * own.transition_goals_against
                   / own.transition_turnovers)
        if _gka238 <= 20.0:
            plan.append(
                f"A kapusuk keze gólt indít ({opp.gka_assists} "
                f"kapus-gólpassz), a ti visszazárásotok viszont bírja "
                f"(labdavesztés után csak {_gka238:.0f}% a gyors "
                "kapott gól) — a lövésetek pillanatában az első "
                "hazafutó a kapus-passz sávját vágja el: a hosszú "
                "indításuk így levegőben hal meg.")

    # 237) Az ő előny-hátrajáratásuk × a ti aktív kezetek: az
    # időölésükből szerzés lehet.
    if (opp.pds_lead_passes >= 10 and opp.pds_rest_passes >= 10
            and own.stt_steals >= 6):
        _pds237_lead = 100.0 * opp.pds_lead_back / opp.pds_lead_passes
        _pds237_rest = 100.0 * opp.pds_rest_back / opp.pds_rest_passes
        if _pds237_lead - _pds237_rest >= 12.0:
            plan.append(
                f"Előnyben hátrafelé járatják a labdát (hátra-passz "
                f"{_pds237_lead:.0f}% vs {_pds237_rest:.0f}%), ti "
                f"pedig aktívan szereztek ({own.stt_steals} "
                "labdaszerzés) — ha ők vezetnek, ne várjatok: magas "
                "letámadás, az első hátrapassz a jel, és az "
                "időölésükből tiszta kontra lesz.")

    # 236) Az ő mozdulatlan támadás-mixük × a ti bejáratott faltok:
    # egy terv kitart ellenük 60 percen át.
    if (opp.ams_fh_attacks >= 6 and opp.ams_sh_attacks >= 6
            and own.defense_main != "—"):
        _ams236 = (abs(100.0 * opp.ams_fh_break / opp.ams_fh_attacks
                       - 100.0 * opp.ams_sh_break
                       / opp.ams_sh_attacks)
                   + abs(100.0 * opp.ams_fh_quick
                         / opp.ams_fh_attacks
                         - 100.0 * opp.ams_sh_quick
                         / opp.ams_sh_attacks)) / 2.0
        if _ams236 <= 10.0:
            plan.append(
                f"Félidőn át ugyanazt játsszák (a támadás-mixük alig "
                f"mozdul a szünet után), nektek pedig bejáratott "
                f"fő-falatok van ({own.defense_main}) — ne "
                f"váltogassatok: a {own.defense_main} ellenük egész "
                "meccsen kitart, a szünetben a finomhangolásra "
                "menjen az idő, ne új tervre.")

    # 235) Az ő elfogyó lepattanó-harcuk × a ti blokkoló falatok: a
    # zárásban minden második labda a tiétek.
    if (opp.scf_fh_misses >= 3 and opp.scf_sh_misses >= 3
            and own.blocks >= 4):
        _scf235_fh = 100.0 * opp.scf_fh_won / opp.scf_fh_misses
        _scf235_sh = 100.0 * opp.scf_sh_won / opp.scf_sh_misses
        if _scf235_fh - _scf235_sh >= 25.0:
            plan.append(
                f"A hajrára elfogy a lepattanó-harcuk (visszaharcolt "
                f"lepattanó {_scf235_fh:.0f}% → {_scf235_sh:.0f}%), "
                f"a ti falatok pedig blokkol ({own.blocks} blokk) — "
                "a zárásban a blokk utáni labdára ti induljatok "
                "először: az ő lábuk már nem megy oda, minden "
                "második labda a tiétek lehet.")

    # 234) Az ő hajrában megálló labdájuk × a ti szabályos kezetek: a
    # labdás emberük a hajrában dupla nyomást kaphat.
    if (opp.asf_fh_goals >= 3 and opp.asf_sh_goals >= 3
            and own.suspensions <= 2):
        _asf234_fh = 100.0 * opp.asf_fh_assisted / opp.asf_fh_goals
        _asf234_sh = 100.0 * opp.asf_sh_assisted / opp.asf_sh_goals
        if _asf234_fh - _asf234_sh >= 25.0:
            plan.append(
                f"A hajrában megáll náluk a labda (gólpasszos gól "
                f"{_asf234_fh:.0f}% → {_asf234_sh:.0f}%), ti pedig "
                f"szabályosan tudtok keményen védekezni "
                f"({own.suspensions} kiállítás) — a második félidőben "
                "a labdás emberük kapjon dupla nyomást: a passz úgyis "
                "megállt, az egyéni megoldást pedig a tiszta test "
                "elviszi.")

    # 233) Az ő sorozat-kapusuk × a ti sok lábon álló támadásotok: a
    # szériát képváltással kell törni.
    if (opp.gst_on_target >= 6 and opp.gst_streaks >= 2
            and len([_sc for _sc in (own.scorer_goals or [])
                     if _sc.get("goals", 0) >= 2]) >= 4):
        plan.append(
            f"A kapusuk rákapós ({opp.gst_streaks} hármas "
            f"védés-széria), a ti gólszerzésetek viszont sok lábon "
            "áll — két védése után kötelező a lövés-kép váltás: más "
            "poszt fejezzen be, más zónába, más ritmusban; a "
            "sorozatát a változatosságotok töri meg, mielőtt "
            "meccset venne el tőletek.")

    # 232) Az ő rendszer-7a6-uk × a ti aktív kezetek: a szerzés után
    # az üres kapu az első nézés.
    if (opp.ens_tr + opp.ens_lead + opp.ens_level >= 3
            and (opp.ens_lead + opp.ens_level) - opp.ens_tr >= 2
            and own.stt_steals >= 6):
        plan.append(
            f"A 7 a 6 náluk rendszer, nem mentőöv "
            f"({opp.ens_lead + opp.ens_level} üres-kapus szakaszuk "
            f"nem hátrányban jött), ti pedig sokat szereztek "
            f"({own.stt_steals} labdaszerzés) — minden szerzésnél az "
            "első nézés a túloldali üres kapu: a középről elengedett "
            "dobás ellenük nem cirkusz, hanem a legolcsóbb gól.")

    # 231) Az ő kényszer-kontráik × a ti visszazárásotok: vezetésnél
    # futni fognak, és ti ezt elbírjátok.
    if (opp.bks_tr_attacks >= 5 and opp.bks_rest_attacks >= 5
            and own.transition_turnovers >= 5):
        _bks231 = (100.0 * opp.bks_tr_breaks / opp.bks_tr_attacks
                   - 100.0 * opp.bks_rest_breaks
                   / opp.bks_rest_attacks)
        _own_ga231 = (100.0 * own.transition_goals_against
                      / own.transition_turnovers)
        if _bks231 >= 12.0 and _own_ga231 <= 20.0:
            plan.append(
                f"Hátrányban kontrába menekülnek (a hátrány-"
                f"támadásaik lerohanás-többlete {_bks231:.0f} "
                f"százalékpont), a ti visszazárásotok pedig bírja "
                f"(a labdavesztéseitek után csak {_own_ga231:.0f}% "
                "a gyors kapott gól) — ha vezettek, hagyjátok őket "
                "futni: a kapkodó kontra a ti rendezett "
                "visszaérésetekkel szemben eladott labda.")

    # 230) Az ő hátrány-heteseik × a ti lábbal védekező faltok: a
    # menekülő-fegyverük elvehető.
    if (opp.svs_tr >= 3
            and opp.svs_tr - (opp.svs_lead + opp.svs_level) >= 2
            and own.suspensions <= 2):
        plan.append(
            f"Hátrányban a hetes a menekülő-fegyverük ({opp.svs_tr} "
            f"kiharcolt hetesük hátrányban jött), a ti falatok pedig "
            f"szabályosan dolgozik ({own.suspensions} kiállítás) — ha "
            "vezettek, a betörőik kontaktot és kezet keresnek: lábbal "
            "elzárt út, magasban tartott kéz, és a legolcsóbb "
            "góljukat veszitek el.")

    # 229) Az ő frusztrációs kiállításaik × a ti hideg fejetek: a
    # vezetés kiállítást terem.
    if (opp.sps_tr >= 3
            and opp.sps_tr - (opp.sps_lead + opp.sps_level) >= 2
            and own.suspensions <= 2):
        plan.append(
            f"Hátrányban elszáll a fegyelmük ({opp.sps_tr} kiállításuk "
            f"hátrányban jött), ti pedig hidegek maradtok "
            f"({own.suspensions} kiállítás) — ha megvan a vezetés, "
            "vállalt kontakt és türelmes labdajáratás: az ő "
            "frusztrációjuk emberelőnyt hoz nektek, a ti fegyelmetek "
            "nem ad vissza semmit.")

    # 228) Az ő kidobott labdáik × a ti aktív kezetek: az oldalvonal
    # a legjobb védőtök.
    if (opp.obt_out >= 3 and own.stt_steals >= 6):
        plan.append(
            f"Maguktól is kidobják a labdát ({opp.obt_out} oldalvonalon "
            f"elhagyott labda), a ti védelmetek pedig aktív "
            f"({own.stt_steals} labdaszerzés) — tereljétek a labdásukat "
            "az oldalvonal felé, és zárjátok a visszafelé vezető "
            "passzsávot: a szélső sávban a hibájuk magától jön.")

    # 227) Az ő üresjáratos hosszú támadásaik × a ti fegyelmezett
    # faltok: a passzív jel nektek dolgozik.
    if (opp.sac_slow >= 3 and own.suspensions <= 2):
        _sac227 = 100.0 * opp.sac_scored / opp.sac_slow
        if _sac227 <= 25.0:
            plan.append(
                f"Az elhúzódó támadásaik üresen zárulnak "
                f"({opp.sac_scored}/{opp.sac_slow} hosszú akciójuk "
                f"ért gólt), a ti falatok pedig fegyelmezett "
                f"({own.suspensions} kiállítás) — türelmes, hiba "
                "nélküli védekezéssel hagyjátok kifutni az akcióikat: "
                "a passzív jel nektek dolgozik, ne kockáztassatok "
                "korai szerzést.")

    # 226) Az ő gólba kerülő indítás-hibáik × a ti sáv-záró
    # védekezésetek: a kihozatal-vadászat bizonyítottan termel.
    if (opp.olp_punished >= 2 and own.stt_steals >= 6):
        _stt226 = 100.0 * own.stt_int / max(1, own.stt_steals)
        if _stt226 >= 60.0:
            plan.append(
                f"Az elszórt indításaik gólba kerülnek "
                f"({opp.olp_punished}/{opp.olp_lost} elveszett "
                f"kihozatal után jött gyors gól), ti pedig a "
                f"passzsávokat zárjátok (a szerzéseitek "
                f"{_stt226:.0f}%-a elfogás) — magas letámadással "
                "vadásszátok a kapus-indításaikat: náluk ez "
                "bizonyítottan azonnali gólt ér.")

    # 225) Az ő kihagyás utáni törékenységük × a ti gyors
    # újraindításotok: a kimaradt ziccerük a ti jeletek.
    if (opp.pmb_misses >= 4 and own.rs_restarts >= 4):
        _pmb225 = 100.0 * opp.pmb_punished / opp.pmb_misses
        _rs225 = 100.0 * own.rs_fast / max(1, own.rs_restarts)
        if _pmb225 >= 40.0 and _rs225 >= 40.0:
            plan.append(
                f"A kihagyásaik után azonnal büntethetők "
                f"({opp.pmb_punished}/{opp.pmb_misses} kihagyott "
                f"ziccerüket követte fél percen belüli gól), ti "
                f"pedig gyorsan indultok (az újraindításaitok "
                f"{_rs225:.0f}%-a gyors) — minden kihagyott "
                "ziccerük után azonnali tempó: kapura vitt első "
                "támadás, amíg a fejük még a kihagyásnál jár.")

    # 224) Az ő gólba kerülő kilépéseik × a ti beálló-játékotok: a
    # kilépő helyére a beálló fordul be.
    if (opp.sop_goals >= 5
            and own.pivot_attacks >= 6):
        _sop224 = 100.0 * opp.sop_behind / opp.sop_goals
        _pu224 = (100.0 * own.pivot_goals
                  / max(1, own.pivot_attacks))
        if _sop224 >= 40.0 and _pu224 >= 30.0:
            plan.append(
                f"A kilépésük mögé betalálnak ({opp.sop_behind}/"
                f"{opp.sop_goals} kapott gólnál volt kiugró védő), "
                f"ti pedig termő beállós játékot játszotok (a "
                f"beállós támadásaitok {_pu224:.0f}%-a gól) — a "
                "kilépés pillanatában a beálló a kiugró helyére "
                "forduljon be: a rés bizonyítottan gólt ér.")

    # 223) Az ő gólba kerülő kettőzésük × a ti gyors elengedésetek:
    # a kettőzés-jelre már megy is a labda az üres emberhez.
    if (opp.dbp_conceded_after >= 2 and own.sr_shots >= 10):
        _sr223 = 100.0 * own.sr_quick / max(1, own.sr_shots)
        if _sr223 >= 50.0:
            plan.append(
                f"A kettőzésük gólba kerül ({opp.dbp_conceded_after} "
                f"gól esett közvetlenül kettőzés után), ti pedig "
                f"gyorsan engeditek el a labdát (a lövéseitek "
                f"{_sr223:.0f}%-a gyors elengedés) — a kettőzés "
                "pillanatában egy-érintéses passz a felszabadult "
                "emberhez: náluk ez bizonyítottan gólt ér.")

    # 222) Az ő reflex-kapusuk × a ti sarokra lőtt góljaitok: első
    # ütemből, kitartott sarok.
    if opp.rdk_saves >= 5:
        _rdk222 = 100.0 * opp.rdk_read / opp.rdk_saves
        _own_total222 = (own.place_bal + own.place_kozep
                         + own.place_jobb)
        _own_corner222 = (100.0 * (own.place_bal + own.place_jobb)
                          / max(1, _own_total222))
        if (_rdk222 <= 15.0 and _own_total222 >= 8
                and _own_corner222 >= 70.0):
            plan.append(
                f"Reflexből véd a kapusuk (csak {opp.rdk_read}/"
                f"{opp.rdk_saves} olvasott védés), ti pedig sarokra "
                f"lövő csapat vagytok (a góljaitok "
                f"{_own_corner222:.0f}%-a oldalra ment) — első "
                "ütemből, kitartott sarok-lövésekkel dolgozzatok: "
                "nincs mit becsapni rajta, a pontosság dönt.")

    # 221) Az ő elmozdítható kapusuk × a ti betörőitek: közelről a
    # csel veri meg.
    if (opp.wfk_goals >= 5 and opp.wfk_fooled > 0
            and opp.matches >= 1):
        _wfk221 = 100.0 * opp.wfk_fooled / opp.wfk_goals
        _own_entries221 = sum((r.get("entries", 0) or 0)
                              for r in (own.breakthrough_players or []))
        if _wfk221 >= 40.0 and _own_entries221 >= 10:
            plan.append(
                f"Elmozdítható a kapusuk ({opp.wfk_fooled}/"
                f"{opp.wfk_goals} kapott gólnál ellenirányba "
                f"mozdult), ti pedig betörős csapat vagytok "
                f"({_own_entries221} bejutás a 9-esen belülre) — a "
                "betöréseitek végén kötelező a lövőcsel: közelről a "
                "kapus mindig elindul, a labda a másik oldalé.")

    # 220) Az ő késő bekísérésük × a ti befutóitok: a mozgásból
    # érkező embert nem tudják felvenni.
    if (opp.cgm_goals >= 5 and own.fbw_breaks >= 5):
        _cgm220 = 100.0 * opp.cgm_running / opp.cgm_goals
        _fbw220 = 100.0 * own.fbw_second / max(1, own.fbw_breaks)
        if _cgm220 >= 55.0 and _fbw220 >= 40.0:
            plan.append(
                f"Mozgásból kapják a gólokat ({opp.cgm_running}/"
                f"{opp.cgm_goals} gólnál lendületből érkezett a "
                f"lövő), a ti kontráitokat pedig gyakran a befutó "
                f"fejezi be ({own.fbw_second}/{own.fbw_breaks}) — a "
                "második hullámot és a betörőt játsszátok: az "
                "érkező embert nem veszik fel időben, a lendület "
                "átmegy rajtuk.")

    # 219) Az ő járatással bontható faluk × a ti oldalváltós
    # járatásotok: a tempó szedi szét őket.
    if (opp.ctm_goals >= 5 and own.ssw_passes >= 40):
        _ctm219 = opp.ctm_passes_sum / opp.ctm_goals
        _ssw219 = 100.0 * own.ssw_switches / own.ssw_passes
        if _ctm219 >= 3.0 and _ssw219 >= 8.0:
            plan.append(
                f"A járatás szedi szét őket (a kapott góljaik előtt "
                f"átlag {_ctm219:.1f} passz), ti pedig oldalváltós "
                f"csapat vagytok (a passzaitok {_ssw219:.0f}%-a "
                "keresztpassz) — pörgő, kétoldalas járatással "
                "bontsatok: a faluk a váltásoknál nyílik, a lövést "
                "a harmadik-negyedik passz után keressétek.")

    # 218) Az ő nyitott folyosóik × a ti éles kontrátok: a betörés
    # és a gyors átmenet a nyitott ajtón megy be.
    if (opp.crg_goals >= 5 and own.fbc_breaks >= 5):
        _crg218 = 100.0 * opp.crg_open / opp.crg_goals
        _fbc218 = 100.0 * own.fbc_goals / max(1, own.fbc_breaks)
        if _crg218 >= 50.0 and _fbc218 >= 40.0:
            plan.append(
                f"Nyitott folyosókon kapják a gólokat ({opp.crg_open}"
                f"/{opp.crg_goals} előtt senki nem állt a "
                f"lövésvonalban), ti pedig élesen fejezitek be a "
                f"kontrát (a lerohanásaitok {_fbc218:.0f}%-a gól) — "
                "minden szerzés után azonnali indulás: a faluk "
                "lassan zár vissza, a folyosó nyitva vár.")

    # 217) Az ő gólba kerülő csere-lyukaik × a ti gyors
    # újraindításotok: a cseréjük a ti órajeletek.
    if (opp.gpn_conceded >= 2 and own.rs_restarts >= 4):
        _rs217 = 100.0 * own.rs_fast / max(1, own.rs_restarts)
        if _rs217 >= 40.0:
            plan.append(
                f"A csere-lyukaik bizonyítottan gólba kerülnek "
                f"({opp.gpn_conceded} kapott gól öt fős játék "
                f"alatt), ti pedig gyorsan indítjátok újra a "
                f"játékot (az újraindításaitok {_rs217:.0f}%-a "
                "gyors) — a cseréjük a ti órajeletek: minden "
                "hullámuknál azonnali középkezdés és kapura vitt "
                "első támadás.")

    # 216) Az ő laza előkészítő-védekezésük × a ti gólpasszos
    # játékotok: az utolsó passz szabadon futhat.
    if (opp.upa_assisted >= 5 and own.asr_assisted >= 5):
        _upa216 = 100.0 * opp.upa_unpressured / opp.upa_assisted
        if _upa216 >= 60.0:
            plan.append(
                f"Az előkészítőt hagyják dolgozni ({opp.upa_unpressured}"
                f"/{opp.upa_assisted} kapott gólpasszuk zavartalan "
                f"kiadásból jött), ti pedig gólpasszos csapat vagytok "
                f"({own.asr_assisted} gólpasszos gól) — a kidolgozott "
                "játékotok az ő védekezésük ellen szabadon fut: "
                "türelmes járatás, és az utolsó passzt nyugodtan ki "
                "lehet mérni.")

    # 215) Az ő sokat átvert védőjük × a ti betörő embereitek: az
    # 1v1-et a nyitott ajtóra kell vinni.
    if (opp.btn_goals >= 4 and opp.btn_defenders
            and opp.matches >= 1):
        _btn_label215, _btn_n215 = next(iter(opp.btn_defenders.items()))
        _btn_vals215 = list(opp.btn_defenders.values())
        _btn_tie215 = (len(_btn_vals215) > 1
                       and _btn_vals215[1] == _btn_n215)
        _own_entries215 = sum((r.get("entries", 0) or 0)
                              for r in (own.breakthrough_players or []))
        if (100.0 * _btn_n215 / opp.btn_goals >= 40.0
                and not _btn_tie215 and _own_entries215 >= 10):
            plan.append(
                f"A kapott góljaiknál rendre a(z) {_btn_label215} "
                f"mezszámú védő veszíti a párharcot ({_btn_n215}/"
                f"{opp.btn_goals}), ti pedig betörős csapat vagytok "
                f"({_own_entries215} bejutás a 9-esen belülre) — az "
                "1v1-eket tudatosan az ő oldalára vigyétek: "
                "elzárással oda tereljétek a betörőt, ott nyílik az "
                "ajtó.")

    # 214) Az ő időhúzó kihozataluk × a ti gyors középkezdésetek: a
    # lassításuk ellen az azonnali újraindítás dolgozik.
    if (opp.ops_lead_outlets >= 4 and opp.ops_rest_outlets >= 4
            and own.rs_restarts >= 4):
        _ops_lead214 = opp.ops_lead_sum_s / opp.ops_lead_outlets
        _ops_rest214 = opp.ops_rest_sum_s / opp.ops_rest_outlets
        _rs214 = 100.0 * own.rs_fast / max(1, own.rs_restarts)
        if _ops_lead214 - _ops_rest214 >= 2.0 and _rs214 >= 40.0:
            plan.append(
                f"Vezetve lassítják az indítást (átlag "
                f"{_ops_lead214:.1f} mp kihozatal előnyben, "
                f"{_ops_rest214:.1f} egyébként), ti pedig gyorsan "
                f"indítjátok újra a játékot (a középkezdéseitek "
                f"{_rs214:.0f}%-a gyors) — hátrányban ne hagyjátok "
                "lassítani: kapott gól után azonnali középkezdés, "
                "és minden megnyert másodperc a tiétek.")

    # 213) Az ő csak-előnyben-forgató padjuk × a ti szoros-meccs
    # rutinotok: tartsd szorosan, és a kezdősoruk elfárad.
    if (opp.sbs_lead_s >= 120.0 and opp.sbs_rest_s >= 120.0
            and opp.sbs_lead_subs + opp.sbs_rest_subs >= 4
            and own.cg_wins + own.cg_losses >= 2):
        _sbs_lead213 = opp.sbs_lead_subs / opp.sbs_lead_s
        _sbs_rest213 = opp.sbs_rest_subs / opp.sbs_rest_s
        if (_sbs_lead213 >= 1.5 * _sbs_rest213
                and opp.sbs_lead_subs >= 3
                and own.cg_wins > own.cg_losses):
            plan.append(
                f"Vezetve forgatnak ({opp.sbs_lead_subs} cserehullám "
                f"előnyben, {opp.sbs_rest_subs} egyébként), ti pedig "
                f"jók vagytok a szoros meccsekben ({own.cg_wins} "
                f"szoros győzelem, {own.cg_losses} vereség) — "
                "tartsátok egy-két gólon belül a meccset: amíg "
                "szoros, nem mernek pihentetni, a kezdősoruk a "
                "hajrára elfárad, és az a ti terepetek.")

    # 212) Az ő előnyben leülő faluk × a ti kitartó, lövésig vitt
    # támadásaitok: hátrányból is visszajön a meccs.
    if (opp.dbs_lead_shots >= 5 and opp.dbs_rest_shots >= 5
            and own.lao_n >= 5):
        _dbs_lead212 = opp.dbs_lead_xg / opp.dbs_lead_shots
        _dbs_rest212 = opp.dbs_rest_xg / opp.dbs_rest_shots
        _lao212 = 100.0 * own.lao_died / own.lao_n
        if _dbs_lead212 - _dbs_rest212 >= 0.05 and _lao212 <= 35.0:
            plan.append(
                f"Előnyben leül a faluk (kapott átlag-xG vezetve "
                f"{_dbs_lead212:.2f}, egyébként {_dbs_rest212:.2f}), "
                f"a ti hosszú támadásaitok pedig lövésig érnek (csak "
                f"{_lao212:.0f}% hal el) — ha vezetnek, ne "
                "kapkodjatok: a türelmesen bevitt támadás pont az ő "
                "elkényelmesedő falukat bünteti, a meccs hátrányból "
                "is visszajön.")

    # 211) Az ő hátrány-kapkodásuk × a ti labdaszerző védekezésetek:
    # az első ellépés után a prés dönti el a meccset.
    if (opp.tbs_tr_attacks >= 5 and opp.tbs_rest_attacks >= 5
            and own.stt_steals >= 8):
        _tbs_tr211 = 100.0 * opp.tbs_tr_tos / opp.tbs_tr_attacks
        _tbs_rest211 = (100.0 * opp.tbs_rest_tos
                        / opp.tbs_rest_attacks)
        if _tbs_tr211 - _tbs_rest211 >= 10.0:
            plan.append(
                f"Hátrányban kapkodnak (az eladós támadásaik aránya "
                f"{_tbs_rest211:.0f}%-ról {_tbs_tr211:.0f}%-ra "
                f"ugrik), ti pedig labdaszerző védekezést játszotok "
                f"({own.stt_steals} szerzés) — az első 2-3 gólos "
                "ellépés után azonnal váltsatok présre: a nyomás "
                "alatt ontott labdáik a különbséget hizlalják, és a "
                "meccs korán eldönthető.")

    # 210) Az ő kiolvasható kettőzésük × a ti gyors elengedésetek: a
    # kettőzés pillanatában már el is ment a labda.
    if (opp.dtp_frames >= 50 and opp.dtp_doublers
            and own.sr_shots >= 10):
        _dtp_label210, _dtp_n210 = next(iter(opp.dtp_doublers.items()))
        _dtp_vals210 = list(opp.dtp_doublers.values())
        _dtp_tie210 = (len(_dtp_vals210) > 1
                       and _dtp_vals210[1] == _dtp_n210)
        _sr210 = 100.0 * own.sr_quick / max(1, own.sr_shots)
        if (100.0 * _dtp_n210 / opp.dtp_frames >= 40.0
                and not _dtp_tie210 and _sr210 >= 50.0):
            plan.append(
                f"Kiszámítható a kettőzésük (a(z) {_dtp_label210} "
                f"mezszámú jön másodiknak), ti pedig gyorsan "
                f"engeditek el a labdát (a lövéseitek "
                f"{_sr210:.0f}%-a gyors elengedés) — a kettőzés "
                "jelére az ő őrzöttje felé menjen az egy-érintéses "
                "passz: mire a kettőzés odaér, a labda már túl van "
                "rajta.")

    # 209) Az ő messziről lövő szélsőik × a ti jól védő kapusotok: a
    # szélső-szög ráengedhető, a kapus-párbaj a tiétek.
    if (opp.wsd_shots >= 5 and own.gk_on_target >= 10):
        _wsd209 = opp.wsd_depth_sum_m / opp.wsd_shots
        _gk209 = 100.0 * own.gk_saves / max(1, own.gk_on_target)
        if _wsd209 >= 8.5 and _gk209 >= 30.0:
            plan.append(
                f"Messziről lövő szélsőik vannak (átlag "
                f"{_wsd209:.1f} m-ről eresztik el), a ti kapusotok "
                f"pedig jól véd ({_gk209:.0f}% a kapura tartó "
                "lövésekre) — a szélső-szöget engedjétek rá: a fal "
                "maradjon szűken középen, a rossz szögű messzi "
                "lövés a kapusotok kenyere.")

    # 208) Az ő hajrá-kontráik × a ti biztos labdakezelésetek: a
    # második félidőben éheztetitek a rohanásukat.
    if (opp.brf_fh_attacks >= 5 and opp.brf_sh_attacks >= 5
            and opp.matches >= 1):
        _brf_fh208 = (100.0 * opp.brf_fh_breaks
                      / opp.brf_fh_attacks)
        _brf_sh208 = (100.0 * opp.brf_sh_breaks
                      / opp.brf_sh_attacks)
        _to208 = own.turnover_total / max(1, own.matches)
        if _brf_sh208 - _brf_fh208 >= 15.0 and _to208 <= 10.0:
            plan.append(
                f"A hajrára kontrázósabbak (a lerohanás-arányuk "
                f"{_brf_fh208:.0f}%-ról {_brf_sh208:.0f}%-ra nő), "
                f"ti pedig keveset hibáztok (meccsenként átlag "
                f"{_to208:.0f} labdaeladás) — a második félidőben "
                "türelmes, biztos labdakezeléssel éheztessétek a "
                "rohanásukat: kontra labdavesztés nélkül nincs.")

    # 207) Az ő egy-posztos felhozataluk × a ti passzsáv-záró
    # védekezésetek: a letámadás a kulcs-embert fogja.
    if (opp.otr_outlets >= 4 and opp.otr_roles
            and own.stt_steals >= 6):
        _otr_poszt207, _otr_n207 = next(iter(opp.otr_roles.items()))
        _otr_vals207 = list(opp.otr_roles.values())
        _otr_tie207 = (len(_otr_vals207) > 1
                       and _otr_vals207[1] == _otr_n207)
        _stt207 = 100.0 * own.stt_int / max(1, own.stt_steals)
        if (100.0 * _otr_n207 / opp.otr_outlets >= 50.0
                and not _otr_tie207 and _stt207 >= 60.0):
            plan.append(
                f"A felhozataluk a(z) {_otr_poszt207} posztra épül "
                f"({_otr_n207}/{opp.otr_outlets} indítás-célpont), "
                f"ti pedig a passzsávokat zárjátok (a szerzéseitek "
                f"{_stt207:.0f}%-a elfogás) — a letámadásnál a(z) "
                f"{_otr_poszt207} sávját vágjátok el: a kapus "
                "kényszer-hosszúja a tiétek, és onnan kontra jár.")

    # 206) Az ő falba lövő posztjuk × a ti termő blokkjaitok: ott a
    # fal tartása maga a védekezés.
    if (opp.bbr_blocked >= 4 and opp.bbr_roles
            and own.blocks >= 4):
        _bbr_poszt206, _bbr_n206 = next(iter(opp.bbr_roles.items()))
        _bbr_vals206 = list(opp.bbr_roles.values())
        _bbr_tie206 = (len(_bbr_vals206) > 1
                       and _bbr_vals206[1] == _bbr_n206)
        if (100.0 * _bbr_n206 / opp.bbr_blocked >= 50.0
                and not _bbr_tie206):
            plan.append(
                f"A falba lőtt lövéseik a(z) {_bbr_poszt206} "
                f"posztról jönnek ({_bbr_n206}/{opp.bbr_blocked} "
                f"lefogott lövés), ti pedig blokkolós csapat "
                f"vagytok ({own.blocks} blokk) — a(z) "
                f"{_bbr_poszt206} ellen a fal tartása maga a "
                "védekezés: ne lépjetek ki, a kilépés csak sávot "
                "nyitna, a blokk pedig magától termel.")

    # 205) Az ő egy-posztos kiállítás-termelésük × a ti fegyelmezett
    # falatok: nem adtok nekik emberelőnyt.
    if (opp.sur_suspensions >= 3 and opp.sur_roles
            and own.def_shots_against >= 10):
        _sur_poszt205, _sur_n205 = next(iter(opp.sur_roles.items()))
        _sur_vals205 = list(opp.sur_roles.values())
        _sur_tie205 = (len(_sur_vals205) > 1
                       and _sur_vals205[1] == _sur_n205)
        _free205 = (100.0 * own.def_free_shots
                    / max(1, own.def_shots_against))
        if (100.0 * _sur_n205 / opp.sur_suspensions >= 50.0
                and not _sur_tie205 and _free205 <= 35.0):
            plan.append(
                f"A kétperceseket jellemzően a(z) {_sur_poszt205} "
                f"posztról hozzák ({_sur_n205}/"
                f"{opp.sur_suspensions} kiharcolt kiállítás), a ti "
                f"falatok pedig fegyelmezett (a rátok jövő lövések "
                f"csak {_free205:.0f}%-a fedezetlen) — a(z) "
                f"{_sur_poszt205} ellen korai, testes lépéssel "
                "védekezzetek, kéz nélkül: ha nem adtok "
                "emberelőnyt, a legjobb fegyverük hatástalan.")

    # 204) Az ő egy-posztos előkészítésük × a ti sáv-záró
    # védekezésetek: a fő gólpassz-sáv elvágása a terv.
    if (opp.abr_assists >= 5 and opp.abr_roles
            and own.stt_steals >= 6):
        _abr_poszt204, _abr_n204 = next(iter(opp.abr_roles.items()))
        _abr_vals204 = list(opp.abr_roles.values())
        _abr_tie204 = (len(_abr_vals204) > 1
                       and _abr_vals204[1] == _abr_n204)
        _stt204 = 100.0 * own.stt_int / max(1, own.stt_steals)
        if (100.0 * _abr_n204 / opp.abr_assists >= 45.0
                and not _abr_tie204 and _stt204 >= 60.0):
            plan.append(
                f"A góljaikat jellemzően a(z) {_abr_poszt204} "
                f"posztról készítik elő ({_abr_n204}/"
                f"{opp.abr_assists} gólpassz), ti pedig a "
                f"passzsávokat zárjátok (a szerzéseitek "
                f"{_stt204:.0f}%-a elfogás) — a(z) {_abr_poszt204} "
                "gólpassz-sávjára álljatok rá: az ő keze nélkül a "
                "befejezőik éhen maradnak, az elfogás pedig "
                "nálatok kontrát ér.")

    # 203) Az ő lefogott lövőjük × a ti termő blokkjaitok: ellene a
    # fal dolgozik, nem a kifutás.
    if (opp.bsh_blocked >= 4 and opp.bsh_shooters
            and own.blocks >= 4):
        _bsh_label203, _bsh_n203 = next(iter(opp.bsh_shooters.items()))
        _bsh_vals203 = list(opp.bsh_shooters.values())
        _bsh_tie203 = (len(_bsh_vals203) > 1
                       and _bsh_vals203[1] == _bsh_n203)
        if (100.0 * _bsh_n203 / opp.bsh_blocked >= 50.0
                and not _bsh_tie203):
            plan.append(
                f"A(z) {_bsh_label203} mezszámú lövőjük lövését "
                f"rendre elviszi a fal ({_bsh_n203}/"
                f"{opp.bsh_blocked} lefogott lövés az övé), ti "
                f"pedig blokkolós csapat vagytok ({own.blocks} "
                "blokk) — ellene tudatosan maradjatok falban: ne "
                "fussatok ki rá, a blokk dolgozik helyettetek, a "
                "kifutás csak szabad sávot nyitna neki.")

    # 202) Az ő elszökős kontráik × a ti biztos labdakezelésetek: ha
    # nincs labdavesztés, az elszökött emberük éhen marad.
    if (opp.fbh_breaks >= 5
            and 100.0 * opp.fbh_ahead / opp.fbh_breaks >= 40.0
            and opp.matches >= 1):
        _to202 = own.turnover_total / max(1, own.matches)
        if _to202 <= 10.0:
            plan.append(
                f"Előre szökött emberrel kontráznak "
                f"({opp.fbh_ahead}/{opp.fbh_breaks} lerohanás a "
                f"labda előtt váró játékossal), ti pedig keveset "
                f"hibáztok (meccsenként átlag {_to202:.0f} "
                "labdaeladás) — türelmes, biztos labdakezeléssel az "
                "elszökött emberük éhen marad; a lövéseitek "
                "pillanatában pedig egy kijelölt védő már induljon "
                "hátra mélységbiztosításba.")

    # 201) Az ő második hullámos kontráik × a ti erős átmenet-
    # védekezésetek: a visszafutásnál a középső sáv a tiétek.
    if (opp.fbw_breaks >= 5
            and 100.0 * opp.fbw_second / opp.fbw_breaks >= 50.0
            and own.transition_turnovers >= 6):
        _td201 = (100.0 * own.transition_goals_against
                  / max(1, own.transition_turnovers))
        if _td201 <= 30.0:
            plan.append(
                f"A kontráikat a második hullám fejezi be "
                f"({opp.fbw_second}/{opp.fbw_breaks} lerohanás a "
                f"befutó lövésével), a ti átmenet-védekezésetek "
                f"pedig bírja (a labdavesztéseitek csak "
                f"{_td201:.0f}%-ából kaptok gólt) — a visszafutás "
                "rendjét tartsátok: az első védő az emberre, a "
                "többiek a középső sávot töltik fel, mert a "
                "góljuk a befutótól jön.")

    # 200) Az ő lefordulós beállójuk × a ti erős beálló-őrzésetek: a
    # bejátszás előtt kell elé lépni — a faletek bírja.
    if (opp.psv_receptions >= 5
            and 100.0 * opp.psv_running / opp.psv_receptions >= 55.0
            and own.pd_pivot_attacks >= 6):
        _pd200 = (100.0 * own.pd_pivot_goals
                  / max(1, own.pd_pivot_attacks))
        if _pd200 <= 40.0:
            plan.append(
                f"Mozgásból kapja a beállójuk a labdát "
                f"({opp.psv_running}/{opp.psv_receptions} átvétel "
                f"lefordulásból), a ti beálló-őrzésetek pedig bírja "
                f"(az ellenetek vezetett beállós támadások csak "
                f"{_pd200:.0f}%-a lett gól) — lépjetek elé már a "
                "bejátszás ELŐTT: a lefordulót a passzsáv zárása "
                "állítja meg, az átvétel utáni birkózás nem.")

    # 199) Az ő keresztjátékuk × a ti hangos falatok: a váltás-
    # fegyelem előre begyakorolva.
    if (opp.crx_attacks >= 8
            and opp.crx_crosses / opp.crx_attacks >= 1.0
            and own.def_shots_against >= 10):
        _free199 = (100.0 * own.def_free_shots
                    / max(1, own.def_shots_against))
        if _free199 <= 35.0:
            plan.append(
                f"Sokat kereszteznek (támadásonként "
                f"{opp.crx_crosses / opp.crx_attacks:.1f} oldalcsere), "
                f"a ti falatok pedig fegyelmezett (a rátok jövő "
                f"lövések csak {_free199:.0f}%-a fedezetlen) — a "
                "keresztjeikre előre begyakorolt váltás-szabállyal "
                "feleljetek: az első kereszt váltás, a második már "
                "kísérés, és hangos jelzés minden cserénél.")

    # 198) Az ő futtatott szélsőik × a ti sáv-záró védekezésetek: a
    # futópasszt kell elfogni, nem a lövést fogni.
    if (opp.wsv_receptions >= 6
            and 100.0 * opp.wsv_running / opp.wsv_receptions >= 55.0
            and own.stt_steals >= 6):
        _stt198 = 100.0 * own.stt_int / max(1, own.stt_steals)
        if _stt198 >= 60.0:
            plan.append(
                f"Futtatva kapják a szélsőik a labdát "
                f"({opp.wsv_running}/{opp.wsv_receptions} átvétel "
                f"mozgásból), ti pedig a passzsávakat zárjátok (a "
                f"szerzéseitek {_stt198:.0f}%-a elfogás) — a "
                "futópassz-sávra álljatok rá: az elfogott indítás "
                "után a szélsőjük már kifelé fut, a pálya pedig "
                "nyitva áll előttetek.")

    # 197) Az ő lyukas cseréik × a ti gyors újraindításotok: a csere
    # másodperceit kell büntetni.
    if (opp.sbg_gap_s >= 20.0 and own.rs_restarts >= 4):
        _rs197 = 100.0 * own.rs_fast / max(1, own.rs_restarts)
        if _rs197 >= 40.0:
            plan.append(
                f"Lyukas a cseréjük ({opp.sbg_gap_s:.0f} másodperc öt "
                f"fős játék), ti pedig gyorsan indítjátok újra a "
                f"játékot (az újraindításaitok {_rs197:.0f}%-a "
                "gyors) — a cseréjük pillanata a ti jelzésetek: "
                "azonnali középkezdés és kapura vitt első támadás, "
                "amíg öten vannak.")

    # 196) Az ő hosszú gólpasszaik × a ti sáv-záró védekezésetek: az
    # előkészítő labdáik a ti kontra-forrásotok.
    if (opp.asr_assisted >= 5
            and 100.0 * opp.asr_long / opp.asr_assisted >= 50.0
            and own.stt_steals >= 6):
        _stt196 = 100.0 * own.stt_int / max(1, own.stt_steals)
        if _stt196 >= 60.0:
            plan.append(
                f"Hosszú gólpasszokból élnek ({opp.asr_long}/"
                f"{opp.asr_assisted} előkészítés 8 méteren túlról), "
                f"ti pedig a passzsávakat zárjátok (a szerzéseitek "
                f"{_stt196:.0f}%-a elfogás) — az előkészítő labdáik "
                "a ti kontra-forrásotok: a hosszú bejátszás-sávokra "
                "álljatok rá, és minden elfogásból azonnal "
                "induljatok.")

    # 195) Az ő kiütő kapusuk × a ti lepattanó-vadászaitok: a hatosnál
    # maradó ember gólt terem.
    if (opp.grc_saves >= 4
            and 100.0 * opp.grc_caught / opp.grc_saves <= 40.0):
        _rbw195_rows = [pr for pr in (own.rebounders or [])
                        if pr.get("rebounds", 0) >= 2]
        if _rbw195_rows:
            plan.append(
                f"Kiüti a labdát a kapusuk (csak {opp.grc_caught}/"
                f"{opp.grc_saves} védés maradt nála), nálatok pedig "
                f"van lepattanó-vadász (a(z) "
                f"{_rbw195_rows[0]['player_id']} azonosítójú) — ő a "
                "lövések után a hatosnál marad: a kiütött labdára "
                "rárohanva a legolcsóbb gólokat szedhetitek össze.")

    # 194) Az ő elhaló hosszú támadásaik × a ti fegyelmezett falatok:
    # kivárásra kell játszani ellenük.
    if (opp.lao_n >= 5
            and 100.0 * opp.lao_died / opp.lao_n >= 40.0
            and own.def_shots_against >= 10):
        _free194 = (100.0 * own.def_free_shots
                    / max(1, own.def_shots_against))
        if _free194 <= 35.0:
            plan.append(
                f"A hosszú támadásaik elhalnak ({opp.lao_died}/"
                f"{opp.lao_n} lövés nélkül), a ti falatok pedig "
                f"fegyelmezett (a rátok jövő lövések csak "
                f"{_free194:.0f}%-a fedezetlen) — játsszatok "
                "kivárásra: semmi kapkodó kilépés, hadd járassák — a "
                "passzív jel és a saját türelmetlenségük nektek "
                "dolgozik.")

    # 193) Az ő mindenkit felküldő támadásuk × a ti gyors kapus-
    # indításotok: a hátuk mögötti üres pálya a tiétek.
    if (opp.ahc_frames >= 100
            and opp.ahc_sum_up / opp.ahc_frames >= 5.5
            and own.gk_outlets >= 4):
        _gk193 = 100.0 * own.gk_outlet_fast / max(1, own.gk_outlets)
        if _gk193 >= 40.0:
            plan.append(
                f"Mindenkit felküldenek (átlag "
                f"{opp.ahc_sum_up / opp.ahc_frames:.1f} mezőnyjátékos "
                f"fent), a ti kapusotok pedig gyorsan indít (az "
                f"indításaitok {_gk193:.0f}%-a gyors) — minden "
                "védésetek és szerzésetek mögött üres pálya vár: a "
                "kapus első gondolata a hosszú indítás legyen, a "
                "szélsők pedig már a lövésük pillanatában forduljanak.")

    # 192) Az ő visszahulló blokkjaik × a ti második hullámotok: a
    # blokkolt lövésetek nem labdavesztés, hanem újrajátszás.
    if (opp.brc_blocks >= 4
            and 100.0 * opp.brc_recovered / opp.brc_blocks <= 30.0
            and own.rn_made >= 2):
        plan.append(
            f"A blokkjaik visszahullanak (csak {opp.brc_recovered}/"
            f"{opp.brc_blocks} lepattanót szereznek meg), ti pedig "
            f"lendületből játszotok ({own.rn_made} gólsorozat) — a "
            "blokkolt lövés nálatok nem labdavesztés: a lövő mögé "
            "tervezett második hullám szedje a lepattanót, és "
            "azonnal jöhet az újrajátszás a rendezetlen fal ellen.")

    # 191) Az ő ziccer-biztos befejezőjük × a ti korai besegítésetek:
    # nála a helyzet kialakulását kell megelőzni.
    _bcf191: dict = {}
    for _bcf191_pr in (opp.bcf_players or []):
        _r191 = _bcf191.setdefault(_bcf191_pr["player_id"], [0, 0])
        _r191[0] += _bcf191_pr["chances"]
        _r191[1] += _bcf191_pr["goals"]
    _bcf191_safe = [(pid, c, g) for pid, (c, g) in _bcf191.items()
                    if c >= 3 and 100.0 * g / c >= 80.0]
    if _bcf191_safe and own.blk_attempts >= 4:
        _pid191, _c191, _g191 = max(_bcf191_safe,
                                    key=lambda x: x[1])
        plan.append(
            f"Ziccer-biztos befejezőjük a(z) {_pid191} azonosítójú "
            f"({_g191}/{_c191} nagy helyzet), ti pedig aktív "
            f"blokk-csapat vagytok ({own.blk_attempts} kísérlet) — "
            "nála ne a lövést próbáljátok fogni, hanem a helyzet "
            "kialakulását: korai besegítés és a bejátszó-sáv zárása, "
            "mert amit a hatoson megkap, az gól.")

    # 190) Az ő hetes utáni leragadásuk × a ti kiharcolt heteseitek: a
    # hetesetek duplán érhet.
    _psl190_earned = sum((own.seven_earner_roles or {}).values())
    if (opp.psl_sevens >= 3 and opp.psl_extra >= 2
            and _psl190_earned >= 3):
        plan.append(
            f"A hetes utáni percben is büntethetők ({opp.psl_extra} "
            f"további kapott gól a heteseik után), ti pedig rendre "
            f"kiharcoljátok a hetest ({_psl190_earned} megítélt "
            "büntető) — minden hetesetek után azonnal kész figurával "
            "támadjatok újra: a reklamáló, átrendeződő faluk ellen a "
            "hetes utáni perc a legkönnyebb gólszerzési ablakotok.")

    # 189) Az ő egyirányú forgásuk × a ti sáv-záró védekezésetek: az
    # ellenirányba terelés kizökkenti őket.
    _cir189_total = opp.cir_left + opp.cir_right
    if _cir189_total >= 20 and own.stt_steals >= 6:
        _cir189_lp = 100.0 * opp.cir_left / _cir189_total
        _stt189 = 100.0 * own.stt_int / max(1, own.stt_steals)
        if (_cir189_lp >= 60.0 or _cir189_lp <= 40.0) and _stt189 >= 60.0:
            _cir189_dir = "balra" if _cir189_lp >= 60.0 else "jobbra"
            plan.append(
                f"Egy irányba forgatnak ({_cir189_dir} megy az "
                f"oldalpasszaik {max(_cir189_lp, 100 - _cir189_lp):.0f}"
                f"%-a), ti pedig a passzsávakat zárjátok (a "
                f"szerzéseitek {_stt189:.0f}%-a elfogás) — zárjátok a "
                "megszokott forgás-sávot: a kényszerített ellenirányú "
                "passzaik lesznek a legkönnyebb elfogásaitok.")

    # 188) Az ő bejáratott elzárás-párosuk × a ti hangos
    # védekezésetek: a kettősük ellen kettősben kell készülni.
    _scp188: dict = {}
    for _scp188_pr in (opp.scp_pairs or []):
        _k188 = (_scp188_pr["setter_id"], _scp188_pr["shooter_id"])
        _scp188[_k188] = _scp188.get(_k188, 0) + _scp188_pr["shots"]
    if _scp188 and own.blk_attempts >= 4:
        _scp188_top = max(_scp188, key=lambda k: _scp188[k])
        if _scp188[_scp188_top] >= 3:
            plan.append(
                f"Bejáratott elzárás-párosuk van (a(z) "
                f"{_scp188_top[0]} zár a(z) {_scp188_top[1]} "
                f"azonosítójúnak, {_scp188[_scp188_top]} közös "
                f"lövés), ti pedig blokk-erős csapat vagytok "
                f"({own.blk_attempts} kísérlet) — a kettősük ellen "
                "kettősben készüljetek: korai kilépés az elzárás elé, "
                "és a blokk-kéz eleve a lövő erős oldalán.")

    # 187) Az ő késői szél-kifutásuk × a ti szélső-góljaitok: oda kell
    # hordani a labdát.
    if (opp.wco_shots >= 4 and own.wing_total_goals >= 8):
        _wco187 = opp.wco_sum_m / opp.wco_shots
        _wing187 = 100.0 * own.wing_goals / max(1, own.wing_total_goals)
        if _wco187 >= 2.5 and _wing187 >= 35.0:
            plan.append(
                f"Későn érnek ki a szélre (átlag {_wco187:.1f} m-re a "
                f"védőjük a lövő szélsőtől), a ti széljátékotok pedig "
                f"él (a góljaitok {_wing187:.0f}%-a szélről jön) — "
                "gyors oldalváltásokkal hordjátok a labdát a "
                "szélsőitekre: teljes szögből, kényelmesen lőhetnek.")

    # 186) Az ő válság-lövőjük × a ti sorozataitok: a lendületetek
    # alatt névre szólóan zárjátok a szelepüket.
    _drb186: dict = {}
    for _drb186_pr in (opp.drb_players or []):
        _drb186[_drb186_pr["player_id"]] = (
            _drb186.get(_drb186_pr["player_id"], 0)
            + _drb186_pr["breaks"])
    if _drb186 and own.rn_made >= 2:
        _drb186_pid = max(_drb186, key=lambda k: _drb186[k])
        if _drb186[_drb186_pid] >= 2:
            plan.append(
                f"Van válság-lövőjük (a(z) {_drb186_pid} azonosítójú, "
                f"{_drb186[_drb186_pid]} csend-törés), ti pedig tudtok "
                f"sorozatot építeni ({own.rn_made} gólsorozat) — amikor "
                "elkaptátok a fonalat, őt zárjátok név szerint: ha a "
                "szelepük nem nyílik ki, a sorozatotok duplán fáj "
                "nekik.")

    # 185) Az ő sorozatlövőjük × a ti páros-védekezésetek: az első
    # gólja után azonnal váltott őrzés jön rá.
    _hh185: dict = {}
    for _hh185_st in (opp.hh_streaks or []):
        _r185 = _hh185.setdefault(_hh185_st["player_id"],
                                  {"streaks": 0, "longest": 0})
        _r185["streaks"] += 1
        _r185["longest"] = max(_r185["longest"], _hh185_st["length"])
    _hh185_c = [(pid, r) for pid, r in _hh185.items()
                if r["streaks"] >= 2 or r["longest"] >= 3]
    if _hh185_c and own.steal_n >= 4:
        _hh185_pid, _hh185_top = max(
            _hh185_c, key=lambda kv: (kv[1]["streaks"],
                                      kv[1]["longest"]))
        plan.append(
            f"Van sorozatlövőjük (a(z) {_hh185_pid} azonosítójú, "
            f"{_hh185_top['streaks']} sorozat), ti pedig aktív "
            f"védekezők vagytok ({own.steal_n} labdaszerzés) — az "
            "első gólja legyen egyben jelzés is: a következő "
            "támadásban váltott őrzés és korai kettőzés megy rá, "
            "a sorozat nem indulhat el.")

    # 184) Az ő hidegen sebezhető kapusuk × a ti türelmes játékotok:
    # az éheztetés után jöjjön a kidolgozott lövés.
    if (opp.gcs_cold_faced >= 4 and opp.gcs_warm_faced >= 4
            and own.pass_attacks >= 10):
        _gcs184_c = 100.0 * opp.gcs_cold_saves / opp.gcs_cold_faced
        _gcs184_w = 100.0 * opp.gcs_warm_saves / opp.gcs_warm_faced
        _pt184 = own.pass_total / max(1, own.pass_attacks)
        if _gcs184_w - _gcs184_c >= 15.0 and _pt184 >= 6.0:
            plan.append(
                f"Hidegen sebezhető a kapusuk (hosszú csend után "
                f"{_gcs184_c:.0f}% a védés-aránya), ti pedig türelmesen "
                f"járatjátok a labdát (átlag {_pt184:.0f} passz "
                "támadásonként) — éheztessétek ki: hosszú birtoklás, "
                "és a kidolgozott lövés pont a csend végén érkezzen.")

    # 183) Az ő présre nincs válaszuk × a ti magas falatok: kilépős
    # védekezéssel kell fojtogatni őket.
    if (opp.avw_high_attacks >= 5 and opp.avw_deep_attacks >= 5
            and own.defensive_pressure_m > 0):
        _avw183_h = 100.0 * opp.avw_high_goals / opp.avw_high_attacks
        _avw183_d = 100.0 * opp.avw_deep_goals / opp.avw_deep_attacks
        if (_avw183_h - _avw183_d <= -20.0
                and own.defensive_pressure_m <= 2.5):
            plan.append(
                f"A felfutó fal megfogja őket (magas fal ellen "
                f"{_avw183_h:.0f}%, mély ellen {_avw183_d:.0f}% a "
                f"gólarányuk), ti pedig amúgy is szorosan védekeztek "
                f"(átlag {own.defensive_pressure_m:.1f} m-re a "
                "labdástól) — játsszatok végig kilépős, magas falat: "
                "ez az ő rémálmuk, és a ti alapjátékotok.")

    # 182) Az ő védésből induló kontráik × a ti lövés-választásotok: a
    # rossz lövés náluk azonnal visszaüt.
    _bsrc182_total = sum((opp.bsrc_sources or {}).values())
    if (_bsrc182_total >= 4
            and opp.bsrc_sources.get("védés", 0) / _bsrc182_total >= 0.5
            and own.shots >= 10 and own.goals is not None):
        _acc182 = 100.0 * own.goals / max(1, own.shots)
        if _acc182 <= 55.0:
            plan.append(
                f"A kontráik főleg védésből indulnak "
                f"({opp.bsrc_sources.get('védés', 0)}/{_bsrc182_total} "
                f"lerohanás), a ti lövés-hatékonyságotok pedig "
                f"alacsony ({_acc182:.0f}%) — minden rossz lövésetek "
                "az ő indításuk: lőjetek kevesebbet, de jobbat, és a "
                "lövés pillanatában már fusson hátra a fékező ember.")

    # 181) Az ő gólveszélyes kapusuk × a ti 7 a 6-otok: üres kapunál
    # kötelező a kijelölt visszafutó.
    if opp.gkg_attempts >= 1 and own.en_windows >= 2:
        plan.append(
            f"Gólveszélyes a kapusuk ({opp.gkg_attempts} kapura "
            f"dobás, {opp.gkg_goals} gól), ti pedig sokat játszotok "
            f"lehozott kapussal ({own.en_windows} szakasz) — a 7 a "
            "6-otok idejére nevezzetek ki visszafutó-felelőst: "
            "labdavesztés pillanatában ő indul a kapu síkjába, "
            "különben a kapusuk azonnal rádob.")

    # 180) Az ő kizökkenő újrakezdésük × a ti figura-kincsetek: a
    # hosszú állás utáni első támadás előre lebeszélve.
    if (opp.lbr_breaks >= 2 and opp.lbr_for - opp.lbr_against <= -2
            and own.num_figures >= 3):
        plan.append(
            f"A hosszú állások kizökkentik őket (a megszakítások "
            f"utáni mérlegük {opp.lbr_for}-{opp.lbr_against}), nektek "
            f"pedig van begyakorolt figurátok ({own.num_figures} "
            "felismert figura) — minden hosszú állás után előre "
            "lebeszélt figurával induljatok: az ő hideg perceikben "
            "a kész terv aránytalanul sokat ér.")

    # 179) Az ő egy kézben futó végjátékuk × a ti pressz-termelésetek:
    # a hajrá-kettőzés célszemélye adott.
    if (opp.cbh_frames >= 200 and opp.cbh_players
            and own.stt_steals >= 6):
        _cbh179 = max(opp.cbh_players, key=lambda r: r["frames"])
        if 100.0 * _cbh179["frames"] / opp.cbh_frames >= 35.0:
            plan.append(
                f"Egy kézben van a végjátékuk (a(z) "
                f"{_cbh179['player_id']} azonosítójú viszi a hajrá "
                f"labdás idejét), ti pedig jó labdaszerzők vagytok "
                f"({own.stt_steals} szerzés) — az utolsó öt percben "
                "a kettőzés név szerint rá menjen: vegyétek el tőle "
                "a labdát, és a záró figuráik el sem indulnak.")

    # 178) Az ő gyenge negyedórájuk × a ti mély rotációtok: a
    # hullámvölgyükre a friss sor jön.
    if opp.qp_min >= 40.0 and own.rotation_matches >= 1:
        _qp178 = {q: opp.qp_for.get(q, 0) - opp.qp_against.get(q, 0)
                  for q in ("1", "2", "3", "4")}
        _qp178_worst = min(_qp178, key=lambda q: _qp178[q])
        _rot178 = own.rotation_used_sum / max(1, own.rotation_matches)
        if _qp178[_qp178_worst] <= -3 and _rot178 >= 9.0:
            plan.append(
                f"A(z) {_qp178_worst}. negyedórában esnek szét "
                f"({_qp178[_qp178_worst]} ott a gólkülönbségük), ti "
                f"pedig mélyen rotáltok (átlag {_rot178:.0f} ember "
                "kap érdemi szerepet) — pont oda időzítsétek a friss "
                "sort és a pörgetett tempót: a hullámvölgyükben kell "
                "megnyerni a meccset.")

    # 177) Az ő egy-emberes beálló-őrzésük × a ti elzárásaitok: az
    # elzárás célpontja a beálló-őr legyen.
    if (opp.pvg_frames >= 300 and opp.pvg_guards
            and own.scu_shots >= 6):
        _pvg177 = max(opp.pvg_guards, key=lambda r: r["frames"])
        _scu177 = 100.0 * own.scu_screened / max(1, own.scu_shots)
        if (100.0 * _pvg177["frames"] / opp.pvg_frames >= 60.0
                and _scu177 >= 30.0):
            plan.append(
                f"A beálló-őrzésük egy emberen áll (a(z) "
                f"{_pvg177['player_id']} azonosítójún), ti pedig jól "
                f"használjátok az elzárást (az őrzött lövéseitek "
                f"{_scu177:.0f}%-a elzárásból jön) — az elzárás "
                "célpontja ő legyen: ha kihúzzátok a beállóról, "
                "mögötte szabad a bejátszás, és a besegítésük is "
                "borul.")

    # 176) Az ő cserélő időkérésük × a ti kiszámítható emberfogásotok:
    # az időkérésük után azonnal frissítendő a párosítás.
    if (opp.tsc_timeouts >= 2
            and 100.0 * opp.tsc_with_subs / opp.tsc_timeouts >= 70.0
            and (opp.swp_swaps >= 4 and opp.swp_pairs)):
        _swp176 = max(opp.swp_pairs, key=lambda pr: pr["count"])
        if _swp176["count"] >= 3:
            plan.append(
                f"Az időkérésük cserével jár ({opp.tsc_with_subs}/"
                f"{opp.tsc_timeouts}), és a váltópárjuk is "
                f"kiszámítható (a(z) {_swp176['out_id']} helyére "
                f"rendre a(z) {_swp176['in_id']} azonosítójú jön) — "
                "az időkérésük alatt ti is beszéljétek le előre az "
                "új párosítást: mire a játék újraindul, a beálló "
                "emberüknek már neve és őrzője legyen.")

    # 175) Az ő hátrányban kapkodó lövéseik × a ti lepattanó-uralmatok:
    # vezetésnél a rossz lövéseikből ti indultok.
    if (opp.sqs_trail_shots >= 5 and opp.sqs_other_shots >= 5
            and opp.sqs_other_sum_xg / opp.sqs_other_shots
            - opp.sqs_trail_sum_xg / opp.sqs_trail_shots >= 0.08
            and own.trans_steals >= 4 and own.trans_quick_goals >= 2):
        _sqs175_conv = 100.0 * own.trans_quick_goals / own.trans_steals
        plan.append(
            "Hátrányban elkapkodják a lövéseket, ti pedig a szerzett "
            f"labdát gyorsan gólra váltjátok ({own.trans_quick_goals}/"
            f"{own.trans_steals}, {_sqs175_conv:.0f}%) — ha vezettek, "
            "minden elkapkodott lövésük indítás nektek: a kapus-"
            "labdára és a lepattanóra kész kifutó párossal a "
            "hibáikból kontra lesz, és a különbség magától nő.")

    # 174) Az ő hátrányban összeeső kapusuk × a ti lövőerőtök: előnyben
    # rá kell lőni a megingott kapusra.
    if (opp.gks_trail_faced >= 4 and opp.gks_other_faced >= 4
            and own.shot_speed_n >= 5):
        _gks174_t = 100.0 * opp.gks_trail_saves / opp.gks_trail_faced
        _gks174_o = 100.0 * opp.gks_other_saves / opp.gks_other_faced
        _spd174 = own.shot_speed_sum_kmh / own.shot_speed_n
        if _gks174_o - _gks174_t >= 15.0 and _spd174 >= 70.0:
            plan.append(
                f"Hátrányban összeesik a kapusuk (a védés-aránya "
                f"{_gks174_o:.0f}%-ról {_gks174_t:.0f}%-ra esik), ti "
                f"pedig keményen lőtök (átlag {_spd174:.0f} km/h) — "
                "ha megvan az előny, ne kímélje senki: a kinti "
                "bombák is mehetnek, a megingott kapus minden újabb "
                "góllal tovább csúszik.")

    # 173) Az ő hátrányban beszűkülő támadásuk × a ti blokkjaitok: ha
    # vezettek, a közép bebetonozása mindent visz.
    if (opp.wbs_trail_frames >= 100 and opp.wbs_other_frames >= 100
            and own.blk_attempts >= 4):
        _wbs173_t = opp.wbs_trail_sum_m / opp.wbs_trail_frames
        _wbs173_o = opp.wbs_other_sum_m / opp.wbs_other_frames
        _blk173 = 100.0 * own.blk_for / max(1, own.blk_attempts)
        if _wbs173_o - _wbs173_t >= 2.0 and _blk173 >= 20.0:
            plan.append(
                f"Hátrányban beszűkül a támadásuk ({_wbs173_o:.0f} "
                f"m-ről {_wbs173_t:.0f} m-re), a ti blokkotok pedig "
                f"él (a kísérleteitek {_blk173:.0f}%-a fog) — ha "
                "vezettek, betonozzátok be a közepet: a szélsőiket "
                "hagyhatjátok, az erőltetett átlövéseik a kinyújtott "
                "kezekbe futnak.")

    # 172) Az ő zavaros visszaállásuk × a ti figura-kincsetek: a
    # lejáró kiállításra időzített, előre lebeszélt támadás.
    if (opp.ppp_returns >= 2 and opp.ppp_for - opp.ppp_against <= -2
            and own.num_figures >= 3):
        plan.append(
            f"A visszaállásnál megzavarodnak (a kiállításaik letelte "
            f"utáni perc mérlege {opp.ppp_for}-{opp.ppp_against}), "
            f"nektek pedig van begyakorolt figurátok "
            f"({own.num_figures} felismert figura) — a lejáró "
            "kiállításra időzítsetek előre lebeszélt figurát: a "
            "visszaérő ember hidegen jön, az ő zónájára menjen a "
            "kezdés.")

    # 171) Az ő hibázó posztjuk × a ti passzsáv-zárásotok: a sávot az
    # ő leggyengébb posztjára kell tenni.
    _tbr171_total = sum((opp.tbr_roles or {}).values())
    if _tbr171_total >= 6 and opp.tbr_roles and own.stt_steals >= 6:
        _tbr171 = sorted(opp.tbr_roles.items(), key=lambda kv: -kv[1])
        _tbr171_poszt, _tbr171_n = _tbr171[0]
        _tbr171_tie = (len(_tbr171) > 1
                       and _tbr171[1][1] == _tbr171_n)
        _stt171 = 100.0 * own.stt_int / max(1, own.stt_steals)
        if (100.0 * _tbr171_n / _tbr171_total >= 40.0
                and not _tbr171_tie and _stt171 >= 60.0):
            plan.append(
                f"A labdaeladásaik a(z) {_tbr171_poszt} posztról "
                f"jönnek ({_tbr171_n}/{_tbr171_total} eladás), ti "
                f"pedig a passzsávakat zárjátok (a szerzéseitek "
                f"{_stt171:.0f}%-a elfogott passz) — a sáv-zárást az "
                f"ő {_tbr171_poszt} posztjára állítsátok: oda "
                "csúszzon a kettőzés, és az elfogásból azonnal "
                "indulhat a kontra.")

    # 170) Az ő kifutott lábuk × a ti tempótok: a futóversenyt ti
    # nyeritek, vállaljátok fel.
    if (opp.dbt_min >= 10.0 and opp.dbt_m > 0 and opp.dbt_opp_m > 0
            and own.pace_minutes >= 10.0):
        _pace170 = own.pace_attacks / max(0.1, own.pace_minutes)
        if opp.dbt_m <= opp.dbt_opp_m * 0.90 and _pace170 >= 2.2:
            plan.append(
                f"Túlfutja őket az ellenfél (csak "
                f"{opp.dbt_m / max(0.1, opp.dbt_min):.0f} m/perc a "
                f"futásmennyiségük), ti pedig tempós meccseket "
                f"játszotok ({_pace170:.1f} támadás/perc) — "
                "vállaljátok fel a futóversenyt: gyors középkezdés "
                "és korai indítások minden labdánál, a második "
                "félidőre elfogy a lábuk.")

    # 169) Az ő váltott soraik × a ti gyors középkezdésetek: a csere
    # ütemében kell újraindítani.
    _phs169 = [r for r in (opp.phs_players or []) if r["frames"] >= 1500]
    _phs169_def = [r for r in _phs169
                   if 100.0 * r["def_frames"] / r["frames"] >= 75.0]
    _phs169_atk = [r for r in _phs169
                   if 100.0 * r["def_frames"] / r["frames"] <= 25.0]
    if (_phs169_def and _phs169_atk and own.rs_restarts >= 4):
        _rs169 = 100.0 * own.rs_fast / max(1, own.rs_restarts)
        if _rs169 >= 40.0:
            plan.append(
                "Váltott sorokkal játszanak (külön védekező és támadó "
                f"egységük van), ti pedig gyorsan indítjátok újra a "
                f"játékot (az újraindításaitok {_rs169:.0f}%-a "
                "gyors) — a középkezdés és a szerzés utáni indítás a "
                "cseréjük ütemére menjen: amíg a váltás tart, rossz "
                "emberek vannak fent, és a fent ragadt támadójuknál "
                "kell befejezni.")

    # 168) Az ő kijelölt kontra-emberük × a ti lassú felhozatalotok: a
    # fékező-feladat nálatok nem választás, hanem kényszer.
    _spt168 = opp.spt_players or []
    _spt168_total = sum(r["sprints"] for r in _spt168)
    if (_spt168_total >= 10 and _spt168
            and own.but_cases >= 5):
        _spt168_top = max(_spt168, key=lambda r: r["sprints"])
        _but168 = own.but_sum_s / own.but_cases
        if (100.0 * _spt168_top["sprints"] / _spt168_total >= 30.0
                and _but168 >= 7.0):
            plan.append(
                f"Kijelölt kontra-emberük van (a(z) "
                f"{_spt168_top['player_id']} azonosítójú viszi a "
                f"sprintjeik nagy részét), ti pedig lassan hozzátok "
                f"fel a labdát (átlag {_but168:.1f} mp) — a lassú "
                "felhozatal alatt hátul mindig maradjon egy ember, "
                "akinek egyetlen dolga az ő útjának lezárása: nála "
                "egy eladott labda azonnal gól.")

    # 167) Az ő hetes-kapuscseréjük × a ti biztos hetes-szerzésetek: a
    # beugró kapusról is legyen jelentés.
    _svk167_earned = sum((own.seven_earner_roles or {}).values())
    if opp.svk_swaps >= 2 and _svk167_earned >= 3:
        plan.append(
            f"Hetesre kapust cserélnek ({opp.svk_swaps} büntetőnél "
            f"frissen beállt kapus várt), ti pedig rendre "
            f"kiharcoljátok a hetest ({_svk167_earned} kiharcolt "
            "büntető) — a beugró kapusról is készüljön "
            "irány-jelentés, és a lövő a hetes előtt lassítson: a "
            "specialista a gyors, rutinból jövő lövést szereti.")

    # 166) Az ő kilépő védőjük × a ti elzárás-használatotok: az
    # elzárás a kilépőn ér a legtöbbet.
    _adv166 = [r for r in (opp.adv_players or []) if r["frames"] >= 100]
    if len(_adv166) >= 3 and own.scu_shots >= 6:
        _adv166 = sorted(_adv166,
                         key=lambda r: -(r["depth_sum_m"] / r["frames"]))
        _a166_top = _adv166[0]
        _a166_base = (sum(r["depth_sum_m"] for r in _adv166[1:])
                      / max(1, sum(r["frames"] for r in _adv166[1:])))
        _a166_gap = (_a166_top["depth_sum_m"] / _a166_top["frames"]
                     - _a166_base)
        _scu166 = 100.0 * own.scu_screened / max(1, own.scu_shots)
        if _a166_gap >= 2.5 and _scu166 >= 30.0:
            plan.append(
                f"Kilépő védővel játszanak (a(z) "
                f"{_a166_top['player_id']} azonosítójú "
                f"{_a166_gap:.1f} méterrel a sor előtt áll), ti pedig "
                f"jól használjátok az elzárást (az őrzött lövéseitek "
                f"{_scu166:.0f}%-a elzárásból jön) — az elzárás rajta "
                "ér a legtöbbet: tegyétek a kilépőre, és a mögé "
                "befutó ember 2 az 1-et kap a maradék sorral.")

    # 165) Az ő fix középkezdés-emberük × a ti gól utáni
    # letámadásotok: névre szóló célpont a felezőnél.
    if (opp.rst_restarts >= 4 and opp.rst_players
            and own.pag_after_frames >= 60 and own.pag_base_frames >= 60):
        _rst165 = max(opp.rst_players, key=lambda pr: pr["takes"])
        _pag165 = (own.pag_after_sum_m / own.pag_after_frames
                   - own.pag_base_sum_m / own.pag_base_frames)
        if (100.0 * _rst165["takes"] / opp.rst_restarts >= 50.0
                and _pag165 >= 1.5):
            plan.append(
                f"Fix középkezdés-emberük van (a(z) "
                f"{_rst165['player_id']} azonosítójú veszi át a "
                f"kapott gól utáni labdát), ti pedig gól után amúgy "
                f"is letámadtok (a falatok {_pag165:.1f} méterrel "
                "megy feljebb ilyenkor) — a letámadásnak legyen névre "
                "szóló célpontja: a gól pillanatában egy ember "
                "azonnal az átvevőre lép, és a középkezdésük megáll.")

    # 164) Az ő kiszámítható váltópárjuk × a ti mély rotációtok: a
    # csere pillanatában friss védő menjen a beállóra.
    if (opp.swp_swaps >= 4 and opp.swp_pairs
            and own.rotation_matches >= 1):
        _swp164 = max(opp.swp_pairs, key=lambda pr: pr["count"])
        _rot164 = own.rotation_used_sum / max(1, own.rotation_matches)
        if _swp164["count"] >= 3 and _rot164 >= 9.0:
            plan.append(
                f"Kiszámítható a váltópárjuk (a(z) "
                f"{_swp164['out_id']} azonosítójút rendre a(z) "
                f"{_swp164['in_id']} azonosítójú váltja), ti pedig "
                f"mélyen rotáltok (átlag {_rot164:.0f} ember kap "
                "érdemi szerepet) — a csere pillanatában küldjetek "
                "friss védőt a beállóra: az első támadásában "
                "döntsétek el a párharcot, mielőtt felvenné a "
                "ritmust.")

    # 163) Az ő türelmes visszahozásaik × a ti fegyelmezett falatok:
    # kivárásra lehet játszani, a passzív jel nektek dolgozik.
    if (opp.pb_entries >= 6 and own.def_shots_against >= 10):
        _pb163 = 100.0 * opp.pb_pullbacks / opp.pb_entries
        _free163 = (100.0 * own.def_free_shots
                    / max(1, own.def_shots_against))
        if _pb163 >= 45.0 and _free163 <= 35.0:
            plan.append(
                f"Behúzzák, aztán visszahozzák a labdát (a betöréseik "
                f"{_pb163:.0f}%-a lövés nélkül fordul vissza), a ti "
                f"falatok pedig fegyelmezett (a rátok jövő lövések "
                f"csak {_free163:.0f}%-a fedezetlen) — játsszatok "
                "kivárásra: nem kell rámozdulni az első betörésre, a "
                "türelmes zárás és a passzív jel elveszi a "
                "legjobb megoldásaikat.")

    # 162) Az ő szerzés utáni biztosításuk × a ti visszatámadásotok:
    # az eladott labdátok visszanyerhető, mielőtt ellenetek fordulna.
    if opp.stl_steals >= 6 and own.cpr_turnovers >= 8:
        _stl162 = 100.0 * opp.stl_fwd / opp.stl_steals
        _cpr162 = 100.0 * own.cpr_regained / max(1, own.cpr_turnovers)
        if _stl162 <= 25.0 and _cpr162 >= 30.0:
            plan.append(
                f"Szerzés után biztosítanak (a szerzéseik csak "
                f"{_stl162:.0f}%-a megy azonnal előre), ti pedig jól "
                f"támadtok vissza (az eladott labdáitok "
                f"{_cpr162:.0f}%-át visszaszerzitek) — az eladott "
                "labda ellenük nem tragédia: azonnali rátámadással "
                "még a felállásuk előtt visszavehető, mert nem "
                "menekítik előre.")

    # 161) Az ő fáradva adott heteseik × a ti beállós játékotok: a
    # második félidőben a testre vitt labda ingyen hetest ér.
    if (opp.s7f_fh + opp.s7f_sh >= 4 and opp.s7f_sh - opp.s7f_fh >= 2
            and own.pivot_total_attacks >= 10):
        _piv161 = 100.0 * own.pivot_attacks / max(1, own.pivot_total_attacks)
        if _piv161 >= 15.0:
            plan.append(
                f"A második félidőben adják a heteseket ({opp.s7f_fh} "
                f"az elsőben, {opp.s7f_sh} a másodikban), ti pedig "
                f"tudtok beállóst játszani (a támadásaitok "
                f"{_piv161:.0f}%-ában megy be a labda a beállóhoz) — "
                "a szünet után vigyétek a testre a labdát: a fáradó "
                "kéz belenyúl, és jön az ingyen hetes.")

    # 160) Az ő második félidőre kinyíló faluk × a ti betöréseitek: a
    # belső játékot a második félidőre kell tartogatni.
    if (opp.wf_fh_shots >= 5 and opp.wf_sh_shots >= 5
            and own.break_entries >= 8):
        _wf160_fh = opp.wf_fh_sum_xga / opp.wf_fh_shots
        _wf160_sh = opp.wf_sh_sum_xga / opp.wf_sh_shots
        if _wf160_sh - _wf160_fh >= 0.08:
            plan.append(
                f"A második félidőre kinyílik a faluk (a kapott "
                f"lövéseik átlagos helyzet-értéke {_wf160_fh:.2f}-ról "
                f"{_wf160_sh:.2f}-ra nő), ti pedig tudtok betörni "
                f"({own.break_entries} betörés) — az első félidőben "
                "érjétek be a kinti lövéssel és fárasszátok a falat, "
                "a betöréseket és a beállós játékot a második "
                "félidőre tartogassátok: akkor már nyílik a rés.")

    # 159) Az ő csak-kezdők termelésük × a ti mély rotációtok: a
    # tempóval kell elfárasztani a gólfelelőseiket.
    if (opp.ben_goals >= 6 and opp.rotation_matches >= 0
            and own.rotation_matches >= 1):
        _ben159 = 100.0 * opp.ben_bench / opp.ben_goals
        _rot159 = own.rotation_used_sum / max(1, own.rotation_matches)
        if _ben159 <= 10.0 and _rot159 >= 9.0:
            plan.append(
                f"Csak a kezdőik termelnek gólt (a góljaik "
                f"{_ben159:.0f}%-a jön a padról), ti pedig mélyen "
                f"rotáltok (átlag {_rot159:.0f} embernek jut érdemi "
                "szerep) — pörgessétek a tempót és a cseréket: az ő "
                "hat emberük fusson a ti tíz emberetek ellen, a "
                "második félidőre elfogy a lábuk és a gólerejük.")

    # 158) Az ő testre menő védekezésük × a ti széljátékotok: a
    # keresztpasszt nem zárják, szélesen lehet járatni.
    if opp.stt_steals >= 6 and own.wing_total_goals >= 8:
        _stt158 = 100.0 * opp.stt_int / opp.stt_steals
        _wing158 = 100.0 * own.wing_goals / max(1, own.wing_total_goals)
        if _stt158 <= 25.0 and _wing158 >= 35.0:
            plan.append(
                f"Testre mennek szerelni (a szerzéseiknek csak "
                f"{_stt158:.0f}%-a passz-elfogás), a ti széljátékotok "
                f"pedig él (a góljaitok {_wing158:.0f}%-a szélről "
                "jön) — nyugodtan járassátok szélesen: a "
                "keresztpasszt nem zárják, a szélsők futópasszal "
                "kapják a labdát, mielőtt a kontakt megérkezne.")

    # 157) Az ő nagy helyzeteket engedő faluk × a ti beállós
    # góljaitok: befelé kell játszani ellenük.
    if opp.ccq_shots >= 8 and own.pivot_total_attacks >= 10:
        _ccq157 = opp.ccq_sum_xga / opp.ccq_shots
        _piv157 = 100.0 * own.pivot_attacks / max(1, own.pivot_total_attacks)
        if _ccq157 >= 0.35 and _piv157 >= 15.0:
            plan.append(
                f"Nagy helyzeteket engednek (a rájuk jövő lövések "
                f"átlagos helyzet-értéke {_ccq157:.2f}), ti pedig "
                f"tudtok beállóst játszani (a támadásaitok "
                f"{_piv157:.0f}%-ában megy be a labda a beállóhoz) — "
                "befelé kell játszani: elzárás, beállós-csere és "
                "áttörés, mert a faluk a hatos közelében nyílik ki.")

    # 156) Az ő jól kezelt záró labdájuk × a ti pontos
    # lövés-időzítésetek: a félidő végén az órát kell kihúzni.
    if opp.clo_attacks >= 3 and own.shtim_n >= 5:
        _clo156 = 100.0 * opp.clo_goals / opp.clo_attacks
        _early156 = 100.0 * own.shtim_early / max(1, own.shtim_n)
        if _clo156 >= 50.0 and _early156 <= 40.0:
            plan.append(
                f"Jól kezelik a záró labdát (a félidők utolsó "
                f"percében {opp.clo_attacks} támadásból "
                f"{opp.clo_goals} gól), ti pedig ritkán kapkodtok a "
                f"lövéssel (a lövéseitek csak {_early156:.0f}%-a jön "
                "korán) — a félidő végén a saját támadásotokat az "
                "órára kell időzíteni: úgy zárjátok le, hogy nekik "
                "már ne maradjon idejük egy záró rohamra.")

    # 155) Az ő elpuskázott kontráik × a ti kevés eladásotok: nyugodt
    # felállás helyett vállalható a nyitottabb játék.
    if opp.fbc_breaks >= 5 and own.turnover_total >= 8:
        _fbc155 = 100.0 * opp.fbc_goals / opp.fbc_breaks
        _front155 = 100.0 * own.turnover_front / max(1, own.turnover_total)
        if _fbc155 <= 35.0 and _front155 <= 30.0:
            plan.append(
                f"Elpuskázzák a kontrát ({opp.fbc_breaks} "
                f"lerohanásból {opp.fbc_goals} gól), ti pedig ritkán "
                f"veszítitek el elöl a labdát (az eladásaitok "
                f"{_front155:.0f}%-a a támadó harmadban) — nem kell "
                "biztosításra emberrel hátramaradni: a kipattanóra "
                "menjen a második hullám, mert az ő kontrájuk "
                "kevesebbet ér, mint a ti második rohamotok.")

    # 154) Az ő lassú félidő-nyitásuk × a ti gyors kezdéseitek: az
    # első öt percben kell eldönteni a félidőket.
    if opp.ho_for + opp.ho_against >= 4 and own.ho_for + own.ho_against >= 4:
        _ho154 = opp.ho_for - opp.ho_against
        _own154 = own.ho_for - own.ho_against
        if _ho154 <= -2 and _own154 >= 1:
            plan.append(
                f"Lassan indulnak ({opp.ho_for}-{opp.ho_against} a "
                f"nyitó öt percekben), ti pedig jól kezdtek "
                f"({own.ho_for}-{own.ho_against}) — mindkét félidő "
                "első öt percét meccsnek kell venni: a legerősebb "
                "kezdő hetes, előre megbeszélt első két figura, és "
                "azonnali letámadás — a vezetést ott kell "
                "megszerezni.")

    # 153) Az ő időkérés utáni szivárgó faluk × a ti gyors
    # indításaitok: az újraindítás után azonnal rohanni kell.
    if opp.tfd_timeouts >= 3 and own.pace_attacks >= 10:
        _tfd153 = 100.0 * opp.tfd_conceded / opp.tfd_timeouts
        _fb153 = own.fast_break_pct
        if _tfd153 >= 60.0 and _fb153 >= 20.0:
            plan.append(
                f"Az időkérésük után szivárog a faluk (az "
                f"időkéréseik {_tfd153:.0f}%-a után gól esett az első "
                f"rohamból), ti pedig tudtok gyorsan támadni (a "
                f"támadásaitok {_fb153:.0f}%-a lerohanás) — az "
                "időkérésük utáni újraindításnál ne várjatok "
                "felállásra: az első labdával azonnal előre, mert "
                "ilyenkor a leglassabb a szervezésük.")

    # 152) Az ő gól utáni letámadásuk × a ti gyors kapus-indításaitok:
    # a kapott gól utáni kihozatal a kapusról induljon hosszan.
    if (opp.pag_after_frames >= 60 and opp.pag_base_frames >= 60
            and own.gk_outlets >= 4):
        _pag152 = (opp.pag_after_sum_m / opp.pag_after_frames
                   - opp.pag_base_sum_m / opp.pag_base_frames)
        _fast152 = 100.0 * own.gk_outlet_fast / max(1, own.gk_outlets)
        if _pag152 >= 1.5 and _fast152 >= 40.0:
            plan.append(
                f"Saját góljuk után letámadnak (a faluk {_pag152:.1f} "
                f"méterrel megy feljebb), a ti kapusotok pedig "
                f"gyorsan indít (az indításaitok {_fast152:.0f}%-a "
                "gyors) — a kapott gól utáni kihozatal a kapusról "
                "induljon, hosszan a letámadó vonal mögé: a "
                "letámadásuk pont az első passznál a legritkább.")

    # 151) Az ő lassú felhozataluk × a ti kevés szabad lövést engedő
    # falatok: ki lehet tolni a védekezést, van idő felállni.
    if opp.but_cases >= 5 and own.def_shots_against >= 10:
        _but151 = opp.but_sum_s / opp.but_cases
        _free151 = (100.0 * own.def_free_shots
                    / max(1, own.def_shots_against))
        if _but151 >= 7.0 and _free151 <= 35.0:
            plan.append(
                f"Lassan hozzák fel a labdát (átlag {_but151:.1f} mp "
                f"alatt érnek át), a ti falatok pedig keveset enged "
                f"szabadon lőni (a rátok jövő lövések "
                f"{_free151:.0f}%-a fedezetlen) — toljátok ki a "
                "védekezést a 9-esre: mire felállnak, a fal már kint "
                "van, és nincs mögé kerülésre idejük.")

    # 150) Az ő kapusra visszajátszásuk × a ti elöl szerzett
    # labdáitok: a letámadást ki kell terjeszteni a kapusra.
    if opp.kiv_spells >= 8 and own.steal_n >= 4:
        _kiv150 = 100.0 * opp.kiv_with / opp.kiv_spells
        _high150 = 100.0 * own.steal_high / max(1, own.steal_n)
        if _kiv150 >= 25.0 and _high150 >= 30.0:
            plan.append(
                f"Sokat játszanak vissza a kapusnak (a birtoklásaik "
                f"{_kiv150:.0f}%-ában megjárja a labda a kaput), ti "
                f"pedig elöl is tudtok szerezni (a labdaszerzéseitek "
                f"{_high150:.0f}%-a a támadó térfélen) — a "
                "letámadást ki kell terjeszteni a kapusra: egy ember "
                "rálép, a többiek a hosszú passz sávjait zárják.")

    # 149) Az ő fedezetten lövő emberük × a ti blokkjaitok: a
    # blokk-kéz nála többet ér, mint a kilépés.
    _cov149 = [p for p in (opp.covered_shooters or [])
               if p["shots"] >= 5
               and 100.0 * p["covered"] / p["shots"] >= 60.0]
    if _cov149 and own.blk_attempts >= 4:
        _top149 = _cov149[0]
        _pct149 = 100.0 * _top149["covered"] / _top149["shots"]
        _blk149 = 100.0 * own.blk_for / max(1, own.blk_attempts)
        _who149 = (f"{_top149['jersey']}-es mezszámú"
                   if _top149.get("jersey") is not None
                   else f"{_top149['player_id']} azonosítójú")
        if _blk149 >= 25.0:
            plan.append(
                f"A(z) {_who149} játékosuk fedezetten is lő (a "
                f"lövései {_pct149:.0f}%-a fedezett volt), ti pedig "
                f"blokkoltok (a lövéseik {_blk149:.0f}%-ába "
                "belenyúltatok) — nála nem kilépni kell, hanem "
                "blokk-kezet mutatni: hagyjátok lőni fedezetten, és "
                "a kapus a blokk mögé rendezkedjen.")

    # 148) Az ő pressz-érzékeny emberük × a ti kettőzésetek: a
    # szorítást rá kell szervezni.
    _psp148 = [p for p in (opp.pressure_players or [])
               if p["press_events"] >= 5
               and 100.0 * p["press_to"] / p["press_events"] >= 30.0]
    if _psp148 and own.dbl_holder_frames >= 250:
        _top148 = _psp148[0]
        _pct148 = 100.0 * _top148["press_to"] / _top148["press_events"]
        _dbl148 = 100.0 * own.dbl_doubled_frames / own.dbl_holder_frames
        _who148 = (f"{_top148['jersey']}-es mezszámú"
                   if _top148.get("jersey") is not None
                   else f"{_top148['player_id']} azonosítójú")
        if _dbl148 >= 30.0:
            plan.append(
                f"A(z) {_who148} játékosuk pressz-érzékeny (a nyomott "
                f"döntései {_pct148:.0f}%-a eladás lett), ti pedig "
                f"sokat kettőztök (a labdás-idő {_dbl148:.0f}%-ában) "
                "— a kettőzést rá kell szervezni: amint nála van a "
                "labda, jöjjön a második ember, mert nála a szorítás "
                "labdaszerzés.")

    # 147) Az ő elöl szedő védőjük × a ti kihozatal-oldalatok: a
    # felhozatalt a másik oldalra kell vinni.
    _hsp147 = [p for p in (opp.high_stealers or [])
               if p["steals"] >= 3
               and 100.0 * p["high"] / p["steals"] >= 50.0]
    _busn147 = own.bus_left + own.bus_center + own.bus_right
    if _hsp147 and _busn147 >= 8:
        _top147 = _hsp147[0]
        _best147, _cnt147 = max(
            (("bal", own.bus_left), ("jobb", own.bus_right)),
            key=lambda kv: kv[1])
        _pct147 = 100.0 * _cnt147 / _busn147
        _who147 = (f"{_top147['jersey']}-es mezszámú"
                   if _top147.get("jersey") is not None
                   else f"{_top147['player_id']} azonosítójú")
        if _pct147 >= 50.0:
            plan.append(
                f"A(z) {_who147} játékosuk elöl szedi a labdákat "
                f"({_top147['high']}/{_top147['steals']} szerzés a "
                f"támadó térfelükön), ti pedig jellemzően a "
                f"{_best147} oldalon hozzátok fel a labdát (a "
                f"támadásaitok {_pct147:.0f}%-a) — ezt tudatosan kell "
                "váltani: a kihozatalt vigyétek az ő oldalával "
                "szemben, és a kapus mindig a szabad oldalra "
                "indítson.")

    # 146) Az ő pontatlan lövőjük × a ti gyors kapus-indításotok: a
    # mellé lövése ajándék kontra.
    _wst146 = [p for p in (opp.wasteful_shooters or [])
               if p["shots"] >= 5
               and 100.0 * p["off_target"] / p["shots"] >= 40.0]
    if _wst146 and own.rs_restarts >= 4:
        _top146 = _wst146[0]
        _pct146 = 100.0 * _top146["off_target"] / _top146["shots"]
        _fast146 = 100.0 * own.rs_fast / own.rs_restarts
        _who146 = (f"{_top146['jersey']}-es mezszámú"
                   if _top146.get("jersey") is not None
                   else f"{_top146['player_id']} azonosítójú")
        if _fast146 >= 50.0:
            plan.append(
                f"A(z) {_who146} játékosuk lövései elkerülik a kaput "
                f"(a lövései {_pct146:.0f}%-a), ti pedig gyorsan "
                f"indítotok (az újraindításaitok {_fast146:.0f}%-ánál "
                "12 mp-en belül átér a labda) — rá kell engedni a "
                "lövést, és a kapus már a lövés pillanatában "
                "készüljön az indításra: az ő mellé lövése kész "
                "kontra nektek.")

    # 145) Az ő kezdő hatosuk × a ti nyitányotok: az első öt percre
    # név szerinti terv kell.
    _opl145 = [p for p in (opp.opening_players or []) if p["frames"] > 0]
    if len(_opl145) >= 4 and own.open_first_matches >= 1:
        _first145 = 100.0 * own.open_first_yes / own.open_first_matches
        if _first145 <= 40.0:
            _names145 = []
            for _r145 in _opl145[:6]:
                _names145.append(
                    f"{_r145['jersey']}-es"
                    if _r145.get("jersey") is not None
                    else f"#{_r145['player_id']}")
            plan.append(
                f"A kezdő embereik ismertek ({', '.join(_names145)}), "
                f"a ti nyitányotok viszont akadozik (a meccsek "
                f"{_first145:.0f}%-ában szereztétek a nyitógólt) — az "
                "első öt percre név szerinti terv kell: kijelölt "
                "védekezés az ő kezdő lövőjükre, és két bejátszott "
                "nyitó figura a sajátotokban.")

    # 144) Az ő hetes-kiharcolásuk posztja × a ti hetes-okozó
    # védőtök: ott találkozik a két kockázat.
    _ser144 = list((opp.seven_earner_roles or {}).items())
    _sern144 = sum(n for _, n in _ser144)
    _smc144 = own.seven_conceders or []
    if _ser144 and _sern144 >= 3 and _smc144 \
            and _smc144[0]["conceded"] >= 2:
        _ser144.sort(key=lambda kv: -kv[1])
        _poszt144, _top144 = _ser144[0]
        _pct144 = 100.0 * _top144 / _sern144
        _def144 = _smc144[0]
        _who144 = (f"{_def144['jersey']}-es mezszámú"
                   if _def144.get("jersey") is not None
                   else f"{_def144['player_id']} azonosítójú")
        if _pct144 >= 50.0:
            plan.append(
                f"A heteseik {_pct144:.0f}%-át a {_poszt144} "
                f"posztról harcolják ki, nálatok pedig a(z) {_who144} "
                f"védő okozta a legtöbb hetest "
                f"({_def144['conceded']}) — ez a két kockázat "
                f"egymásra talál: az ő {_poszt144} emberüket ne ő "
                "fogja, vagy legyen mögötte segítő, és a kéz "
                "maradjon lent.")

    # 143) Az ő időkérés utáni figurájuk × a ti időkérés-mérlegetek:
    # a megszakítás náluk fegyver, nálatok legyen az is.
    if opp.tfa_timeouts >= 3 and own.tfa_timeouts >= 3:
        _opp143 = 100.0 * opp.tfa_goals / opp.tfa_timeouts
        _own143 = 100.0 * own.tfa_goals / own.tfa_timeouts
        if _opp143 >= 60.0 and _own143 <= 40.0:
            plan.append(
                f"Az időkéréseik után {_opp143:.0f}%-ban betalálnak, "
                f"a ti időkéréseitek után csak {_own143:.0f}%-ban "
                "— két teendő: az ő megszakításuk utáni támadásukra "
                "kijelölt védekezéssel kell készülni, a sajátotokat "
                "pedig kész figurával kell zárni, nem beszéddel.")

    # 142) Az ő kockázatos passzolójuk × a ti labdaszerzéseitek: az ő
    # passzsávja kész gólforrás.
    _rsk142 = [p for p in (opp.risky_passers or [])
               if p["tries"] >= 4
               and 100.0 * p["turnovers"] / p["tries"] >= 40.0]
    if _rsk142 and own.steal_n >= 4:
        _top142 = _rsk142[0]
        _pct142 = 100.0 * _top142["turnovers"] / _top142["tries"]
        _high142 = 100.0 * own.steal_high / max(1, own.steal_n)
        _who142 = (f"{_top142['jersey']}-es mezszámú"
                   if _top142.get("jersey") is not None
                   else f"{_top142['player_id']} azonosítójú")
        if _high142 >= 30.0:
            plan.append(
                f"A(z) {_who142} játékosuk hosszú labdái elfoghatók "
                f"(a kísérletei {_pct142:.0f}%-a elveszett), ti pedig "
                f"elöl is tudtok szerezni (a labdaszerzéseitek "
                f"{_high142:.0f}%-a a támadó térfélen) — az ő "
                "passzsávjába kell beállni: a második védő olvassa "
                "az ő kezét, és minden elfogott labda azonnali "
                "kontra.")

    # 141) Az ő fő elzárójuk × a ti elzárás-védekezésetek: az ő
    # oldalán kell a váltás-fegyelem.
    _scs141 = opp.screen_setters or []
    if _scs141 and _scs141[0]["screens"] >= 3 \
            and own.scd_screened_shots >= 4 and own.scd_open_shots >= 4:
        _top141 = _scs141[0]
        _scr141 = (100.0 * own.scd_screened_goals
                   / own.scd_screened_shots)
        _open141 = 100.0 * own.scd_open_goals / own.scd_open_shots
        _who141 = (f"{_top141['jersey']}-es mezszámú"
                   if _top141.get("jersey") is not None
                   else f"{_top141['player_id']} azonosítójú")
        if _scr141 - _open141 >= 10.0:
            plan.append(
                f"A(z) {_who141} játékosuk állítja az elzárásaikat "
                f"({_top141['screens']} elzárás), ti pedig pont az "
                f"elzárásos lövések ellen szivárogtok (azokból "
                f"{_scr141:.0f}%, a tiszta lövésekből "
                f"{_open141:.0f}% gól) — az ő oldalán kell a "
                "váltás-fegyelem: hangos váltás minden elzárásnál, és "
                "a lövőt nem szabad egy ütemre sem elengedni.")

    # 140) Az ő lassan bemelegedő kapusuk × a ti nyitó góljaitok: a
    # meccs eleje kész gólforrás.
    if opp.gke_early_faced >= 4 and opp.gke_rest_faced >= 4 \
            and own.open_first_matches >= 1:
        _e140 = 100.0 * opp.gke_early_saves / opp.gke_early_faced
        _r140 = 100.0 * opp.gke_rest_saves / opp.gke_rest_faced
        _first140 = (100.0 * own.open_first_yes
                     / own.open_first_matches)
        if _r140 - _e140 >= 15.0 and _first140 >= 50.0:
            plan.append(
                f"Lassan melegszik be a kapusuk (az első tíz percben "
                f"{_e140:.0f}%-ot fog a későbbi {_r140:.0f}% helyett), "
                f"ti pedig gyakran szerzitek a nyitógólt (a meccsek "
                f"{_first140:.0f}%-ában) — a meccs elejét meg kell "
                "nyomni: az első tíz percben vállaljátok a lövést, "
                "mert ott a legolcsóbb a gól.")

    # 139) Az ő emberhátrányos kontra-fenyegetésük × a ti
    # emberelőnyös labdaeladásaitok: a biztosítás nem maradhat el.
    _shs139 = opp.sh_shooters or []
    if _shs139 and _shs139[0]["shots"] >= 2 and own.pp_shots >= 3:
        _top139 = _shs139[0]
        _eff139 = 100.0 * own.pp_goals / own.pp_shots
        _who139 = (f"{_top139['jersey']}-es mezszámú"
                   if _top139.get("jersey") is not None
                   else f"{_top139['player_id']} azonosítójú")
        if _eff139 <= 60.0:
            plan.append(
                f"Emberhátrányban a(z) {_who139} játékosuk vállalja a "
                f"befejezést ({_top139['shots']} lövés), a ti "
                f"emberelőnyötök pedig akadozik "
                f"({own.pp_goals}/{own.pp_shots} gól) — minden "
                "elveszített emberelőnyös labda az ő kontrája lesz: "
                "az ő oldalán kell a biztosítás, és a támadást "
                "biztos befejezéssel kell zárni.")

    # 138) Az ő hajrá-hibázójuk × a ti hajrá-védekezésetek: a végén
    # rá kell szervezni a nyomást.
    _ctp138 = opp.clutch_losers or []
    if _ctp138 and _ctp138[0]["turnovers"] >= 2 and own.steal_n >= 4:
        _top138 = _ctp138[0]
        _high138 = 100.0 * own.steal_high / max(1, own.steal_n)
        _who138 = (f"{_top138['jersey']}-es mezszámú"
                   if _top138.get("jersey") is not None
                   else f"{_top138['player_id']} azonosítójú")
        if _high138 >= 30.0:
            plan.append(
                f"A hajrában a(z) {_who138} játékosuknál megy el a "
                f"labda ({_top138['turnovers']} eladás a döntő "
                f"szakaszban), ti pedig elöl is tudtok szerezni (a "
                f"labdaszerzéseitek {_high138:.0f}%-a a támadó "
                "térfélen) — a záró percekben rá kell szervezni a "
                "nyomást: kettőzés az ő oldalán, és minden szerzés "
                "után azonnali befejezés.")

    # 137) Az ő reaktív cseréik × a ti gólsorozataitok: a
    # cserezavart azonnali középkezdéssel kell büntetni.
    if opp.stg_subs >= 4 and own.rn_made >= 2:
        _stg137 = 100.0 * opp.stg_after / opp.stg_subs
        if _stg137 >= 50.0:
            plan.append(
                f"Kapott gólra cserélnek (a cseréik {_stg137:.0f}%-a "
                f"gól után jön), ti pedig tudtok sorozatot vinni "
                f"({own.rn_made} gólsorozatotok volt) — a második "
                "góljuk után azonnal jön a cseréjük: pont ott kell "
                "gyors középkezdéssel támadni, mert a cserezavarban "
                "rossz emberek vannak a pályán.")

    # 136) Az ő lassan felálló faluk × a ti kontra-kíséretetek: a
    # tömeges indítás pont a rendezetlen fal ellen fizet.
    if opp.dst_cases >= 4 and opp.dst_sum_s > 0 and own.fbs_breaks >= 3 \
            and own.fbs_sum_runners > 0:
        _dst136 = opp.dst_sum_s / opp.dst_cases
        _fbs136 = own.fbs_sum_runners / own.fbs_breaks
        if _dst136 >= 8.0 and _fbs136 >= 2.5:
            plan.append(
                f"Lassan áll fel a faluk (átlag {_dst136:.1f} "
                f"másodperc a rendezett falig), ti pedig többedmagatokkal "
                f"indultok kontrára (átlag {_fbs136:.1f} felfutó ember) "
                "— ezt kell futtatni: minden megszerzett labda után "
                "azonnali indítás, és a második hullám is fusson, mert "
                "a faluk még nincs a helyén.")

    # 135) Az ő emberhátrányban visszaeső kapusuk × a ti
    # emberelőny-hatékonyságotok: gyorsan kell befejezni a két percet.
    if opp.gsh_sh_faced >= 4 and opp.gsh_eq_faced >= 4 \
            and own.pp_shots >= 3:
        _sh135 = 100.0 * opp.gsh_sh_saves / opp.gsh_sh_faced
        _eq135 = 100.0 * opp.gsh_eq_saves / opp.gsh_eq_faced
        _eff135 = 100.0 * own.pp_goals / own.pp_shots
        if _eq135 - _sh135 >= 15.0 and _eff135 <= 60.0:
            plan.append(
                f"A kapusuk emberhátrányban visszaesik ({_sh135:.0f}% "
                f"a szokásos {_eq135:.0f}% helyett), a ti "
                f"emberelőnyötök pedig akadozik "
                f"({own.pp_goals}/{own.pp_shots} gól) — a két percet "
                "gyorsan kell lezárni: két-három passz után jöjjön a "
                "befejezés, amíg a faluk nincs rendezve, mert utána "
                "a kapusuk sem segít nekik.")

    # 134) Az ő emberelőny-befejezőjük × a ti emberhátrány-védekezésetek:
    # a két percre név szerinti terv kell.
    _pps134 = opp.pp_shooters or []
    if _pps134 and _pps134[0]["shots"] >= 3 and own.ppd_seconds >= 90.0:
        _top134 = _pps134[0]
        _conc134 = 60.0 * own.ppd_conceded / own.ppd_seconds
        _who134 = (f"{_top134['jersey']}-es mezszámú"
                   if _top134.get("jersey") is not None
                   else f"{_top134['player_id']} azonosítójú")
        if _conc134 >= 1.0:
            plan.append(
                f"Emberelőnyben a(z) {_who134} játékosuk fejez be "
                f"({_top134['shots']} lövés, {_top134['goals']} gól), "
                f"a ti emberhátrány-védekezésetek pedig szivárog "
                f"(percenként {_conc134:.1f} kapott gól) — a két "
                "percre név szerinti terv kell: rá lépjen ki a "
                "kijelölt védő, és a kapus is az ő lövésére "
                "készüljön.")

    # 133) Az ő kifelé szoruló lövéseik × a ti blokkjaitok: a
    # hajrában a kilépés viszi el a meccset.
    if opp.sdf_fh_shots >= 4 and opp.sdf_sh_shots >= 4 \
            and opp.sdf_fh_sum_m > 0 and opp.sdf_sh_sum_m > 0 \
            and own.blk_attempts >= 4:
        _fh133 = opp.sdf_fh_sum_m / opp.sdf_fh_shots
        _sh133 = opp.sdf_sh_sum_m / opp.sdf_sh_shots
        _blk133 = 100.0 * own.blk_for / max(1, own.blk_attempts)
        if _sh133 - _fh133 >= 1.0 and _blk133 >= 25.0:
            plan.append(
                f"A hajrára kifelé szorulnak (a lövéseik "
                f"{_fh133:.1f} m-ről {_sh133:.1f} m-re kerülnek), ti "
                f"pedig blokkoltok (a lövéseik {_blk133:.0f}%-ába "
                "belenyúltatok) — a második félidőben fel kell "
                "vállalni a kilépést: a távoli lövéseiket blokkolni "
                "kell, mert a betörést már nem vállalják.")

    # 132) Az ő lerohanásból kapott góljaik × a ti gyors indításotok:
    # a kontra ellenük a legolcsóbb gólforrás.
    _cat132 = list((opp.conceded_types or {}).items())
    _catn132 = sum(n for _, n in _cat132)
    if _cat132 and _catn132 >= 5 and own.rs_restarts >= 4:
        _cat132.sort(key=lambda kv: -kv[1])
        _type132, _top132 = _cat132[0]
        _pct132 = 100.0 * _top132 / _catn132
        _fast132 = 100.0 * own.rs_fast / own.rs_restarts
        if _pct132 >= 40.0 and _fast132 >= 50.0 \
                and ("lerohanás" in _type132 or "gyors" in _type132):
            plan.append(
                f"A kapott góljaik {_pct132:.0f}%-a {_type132}-ból "
                f"jön, ti pedig gyorsan indítotok (az "
                f"újraindításaitok {_fast132:.0f}%-ánál 12 mp-en "
                "belül átér a labda) — a kontra ellenük a legolcsóbb "
                "gólforrás: minden védés és kapott gól után azonnal "
                "indítsatok, és a szélsők már a lövés pillanatában "
                "fussanak.")

    # 131) Az ő áttörő emberük × a ti kettőzésetek: a duplázást rá
    # kell tervezni, mert ő nyitja szét a falat.
    _btp131 = opp.breakthrough_players or []
    if _btp131 and _btp131[0]["entries"] >= 3 \
            and own.dbl_holder_frames >= 250:
        _top131 = _btp131[0]
        _dbl131 = 100.0 * own.dbl_doubled_frames / own.dbl_holder_frames
        if _dbl131 >= 30.0:
            _who131 = (f"{_top131['jersey']}-es mezszámú"
                       if _top131.get("jersey") is not None
                       else f"{_top131['player_id']} azonosítójú")
            plan.append(
                f"A(z) {_who131} játékosuk töri át a falat "
                f"({_top131['entries']} betörés), ti pedig tudtok "
                f"kettőzni (a labdás-idő {_dbl131:.0f}%-ában két védő "
                "is rálép) — a duplázást rá kell tervezni: amint "
                "elindul befelé, a szomszéd védő azonnal záródjon be, "
                "és a testtel kell elvenni a vonalát, nem kézzel.")

    # 130) Az ő két beállós játékuk × a ti széthúzott falatok: a
    # közepet tömöríteni kell, a szélek üresen maradnak.
    if opp.dpv_attacks >= 8 and own.defw_frames >= 100:
        _dpv130 = 100.0 * opp.dpv_double / opp.dpv_attacks
        _dw130 = own.defw_sum_m / own.defw_frames
        if _dpv130 >= 30.0 and _dw130 >= 15.0:
            plan.append(
                f"Két beállóval játszanak (a támadásaik "
                f"{_dpv130:.0f}%-ában két emberük is a 6 m-en van), a "
                f"ti falatok pedig széthúzott ({_dw130:.1f} m átlagos "
                "szélesség) — a közepet be kell zárni: a két középső "
                "védő szorosan egymás mellett, saját beállóval, és a "
                "szélső védők feljebb lépve, mert a szélek amúgy is "
                "üresen maradnak.")

    # 129) Az ő hajrá-emberük × a ti hajrá-mérlegetek: a záró
    # szakaszra név szerinti terv kell.
    _cll129 = [p for p in (opp.clutch_players or []) if p["frames"] > 0]
    _sc129 = opp.clutch_scorers or []
    if len(_cll129) >= 4 and _sc129 and own.clutch_matches >= 1:
        _diff129 = ((own.clutch_goals_for - own.clutch_goals_against)
                    / own.clutch_matches)
        _top129 = _sc129[0]
        _who129 = (f"{_top129['jersey']}-es mezszámú"
                   if _top129.get("jersey") is not None
                   else f"{_top129['player_id']} azonosítójú")
        if _diff129 <= 0.0:
            _names129 = []
            for _r129 in _cll129[:6]:
                _names129.append(
                    f"{_r129['jersey']}-es"
                    if _r129.get("jersey") is not None
                    else f"#{_r129['player_id']}")
            plan.append(
                f"A hajrá-embereik ismertek ({', '.join(_names129)}), a "
                f"hajrá-gólszerzőjük a(z) {_who129} játékos, a ti "
                f"hajrá-mérlegetek pedig nem pozitív (meccsenként "
                f"{_diff129:+.1f} gól) — a záró tíz percre név "
                "szerinti terv kell: rá a kettőzés, és a ti záró "
                "figuráitokat is előre ki kell osztani.")

    # 128) Az ő tömeges kontrájuk × a ti visszazárásotok: a
    # visszarendeződést előre ki kell osztani.
    if opp.fbs_breaks >= 3 and opp.fbs_sum_runners > 0 \
            and own.transition_turnovers >= 4:
        _fbs128 = opp.fbs_sum_runners / opp.fbs_breaks
        _tg128 = (100.0 * own.transition_goals_against
                  / own.transition_turnovers)
        if _fbs128 >= 3.0 and _tg128 >= 20.0:
            plan.append(
                f"Tömegesen kontráznak (átlag {_fbs128:.1f} emberük "
                f"fut fel a lerohanásoknál), ti pedig sok gyors gólt "
                f"kaptok labdavesztés után (az eladásaitok "
                f"{_tg128:.0f}%-a után jött az ellenfél gólja) — a "
                "visszarendeződést előre ki kell osztani: kijelölt "
                "fékező ember minden támadásnál, és a lövés "
                "pillanatában a két hátsó már indul vissza.")

    # 127) Az ő kapusuk gyenge hetes-sarka × a ti hetes-mérlegetek: a
    # hetes-tervet előre le kell beszélni.
    _g7f127 = opp.g7d_faced or {}
    _g7s127 = opp.g7d_saved or {}
    _n127 = sum(_g7f127.values())
    _own7_127 = own.seven_takers or []
    _att127 = sum(p.get("attempts", 0) for p in _own7_127)
    if _n127 >= 3 and _att127 >= 3:
        _cand127 = [(d, n) for d, n in _g7f127.items() if n >= 3]
        if _cand127:
            _avg127 = 100.0 * sum(_g7s127.values()) / _n127
            _dir127, _dn127 = min(
                _cand127, key=lambda kv: _g7s127.get(kv[0], 0) / kv[1])
            _pct127 = 100.0 * _g7s127.get(_dir127, 0) / _dn127
            _conv127 = (100.0 * sum(p.get("goals", 0)
                                    for p in _own7_127) / _att127)
            if _avg127 - _pct127 >= 25.0 and _conv127 <= 80.0:
                plan.append(
                    f"A kapusuk a {_dir127} sarokra ér a legkésőbb "
                    f"(onnan {_pct127:.0f}%-ot fog, az átlaga "
                    f"{_avg127:.0f}%), a ti hetes-mérlegetek pedig "
                    f"hagy kívánnivalót ({_conv127:.0f}%) — a "
                    f"hetes-tervet előre le kell beszélni: a {_dir127} "
                    "sarok a cél, és a kijelölt lövő ne változtasson "
                    "a vonalnál.")

    # 126) Az ő egyoldalas kihozataluk × a ti elöl szerzett
    # labdáitok: a letámadást pont oda kell szervezni.
    _busn126 = opp.bus_left + opp.bus_center + opp.bus_right
    if _busn126 >= 8 and own.steal_n >= 4:
        _best126, _cnt126 = max(
            (("bal", opp.bus_left), ("jobb", opp.bus_right)),
            key=lambda kv: kv[1])
        _pct126 = 100.0 * _cnt126 / _busn126
        _high126 = 100.0 * own.steal_high / max(1, own.steal_n)
        if _pct126 >= 50.0 and _high126 >= 30.0:
            plan.append(
                f"A {_best126} oldalon hozzák fel a labdát (a "
                f"támadásaik {_pct126:.0f}%-a onnan indul), ti pedig "
                f"elöl is tudtok szerezni (a labdaszerzéseitek "
                f"{_high126:.0f}%-a a támadó térfélen) — a "
                f"letámadást a {_best126} oldalra kell szervezni: két "
                "ember zárja a felhozatalt, a többiek csúsznak, mert "
                "a másik oldalra úgysem indulnak.")

    # 125) Az ő lepattanó-gyűjtőjük × a ti engedett második rohamaitok:
    # a kipattanó-kísérés a meccs egyik kulcsa.
    _rbw125 = opp.rebounders or []
    if _rbw125 and _rbw125[0]["rebounds"] >= 3 and own.sca_opp_misses >= 6:
        _top125 = _rbw125[0]
        _sca125 = 100.0 * own.sca_allowed / own.sca_opp_misses
        if _sca125 >= 30.0:
            _who125 = (f"{_top125['jersey']}-es mezszámú"
                       if _top125.get("jersey") is not None
                       else f"{_top125['player_id']} azonosítójú")
            plan.append(
                f"A(z) {_who125} játékosuk gyűjti a kipattanókat "
                f"({_top125['rebounds']} lepattanó), ti pedig sok "
                f"második rohamot engedtek (a kimaradt lövéseik "
                f"{_sca125:.0f}%-a után újra lőttek) — a "
                "kipattanó-kísérés a kulcs: minden blokk és védés "
                "után a legközelebbi védő azonnal a labdára megy, és "
                "őt kell kiszorítani a 6 m-es térből.")

    # 124) Az ő távoli lövőjük × a ti blokkjaitok: rá a kilépés
    # duplán fizet.
    _shr124 = [p for p in (opp.shooter_ranges or []) if p["shots"] >= 3]
    if _shr124 and own.blk_attempts >= 4:
        _far124 = max(_shr124, key=lambda p: p["sum_dist_m"] / p["shots"])
        _avg124 = _far124["sum_dist_m"] / _far124["shots"]
        _blk124 = 100.0 * own.blk_for / max(1, own.blk_attempts)
        if _avg124 >= 9.5 and _blk124 >= 25.0:
            _who124 = (f"{_far124['jersey']}-es mezszámú"
                       if _far124.get("jersey") is not None
                       else f"{_far124['player_id']} azonosítójú")
            plan.append(
                f"A(z) {_who124} játékosuk távolról lő (átlag "
                f"{_avg124:.1f} m, {_far124['shots']} lövés), ti pedig "
                f"blokkoltok is (a lövéseik {_blk124:.0f}%-ába "
                "belenyúltatok) — rá kell kilépni: a második vonal "
                "időben a lövő-vonalba, mögötte segítővel, mert az ő "
                "lövése a legolcsóbban elvehető helyzetük.")

    # 123) Az ő emberhátrány-faluk × a ti emberelőny-hatékonyságotok: a
    # forma megmondja, honnan kell lőni a két perc alatt.
    _shs123 = list((opp.sh_shape or {}).items())
    _shsn123 = sum(n for _, n in _shs123)
    if _shs123 and _shsn123 >= 100 and own.pp_shots >= 3:
        _shs123.sort(key=lambda kv: -kv[1])
        _main123, _cnt123 = _shs123[0]
        _pct123 = 100.0 * _cnt123 / _shsn123
        _eff123 = 100.0 * own.pp_goals / own.pp_shots
        if _pct123 >= 60.0 and _eff123 <= 50.0:
            _how123 = ("kívülről kell lőni, mert öt emberrel nem érnek "
                       "ki a lövő-vonalba" if _main123 == "5-0"
                       else "az előretolt emberük mögé kell beúsztatni "
                       "a beállót, oldalváltás után")
            plan.append(
                f"Emberhátrányban {_main123}-s falat húznak (a mért "
                f"kockák {_pct123:.0f}%-ában), a ti emberelőnyötök "
                f"pedig akadozik ({own.pp_goals}/{own.pp_shots} gól, "
                f"{_eff123:.0f}%) — a két percre kész terv kell: "
                f"{_how123}.")

    # 122) Az ő elnyújtott emberelőnyük × a ti emberhátrány-védekezésetek:
    # a türelmes fal pont az ő játékukat fárasztja.
    if opp.ppp_pp_attacks >= 3 and opp.ppp_eq_attacks >= 5 \
            and opp.ppp_pp_sum_s > 0 and opp.ppp_eq_sum_s > 0 \
            and own.ppd_seconds >= 90.0:
        _pp122 = opp.ppp_pp_sum_s / opp.ppp_pp_attacks
        _eq122 = opp.ppp_eq_sum_s / opp.ppp_eq_attacks
        _conc122 = 60.0 * own.ppd_conceded / own.ppd_seconds
        if _pp122 - _eq122 >= 5.0 and _conc122 <= 1.0:
            plan.append(
                f"Elnyújtják az emberelőnyt ({_pp122:.0f} mp-es "
                f"támadások a {_eq122:.0f} mp-es átlaguk helyett), a "
                f"ti emberhátrány-védekezésetek pedig bírja (percenként "
                f"{_conc122:.1f} kapott gól) — türelmes, zárt fal kell: "
                "ne lépjetek ki korán, húzzátok ki a passzív-jelig, "
                "mert a két perc végén nekik kell kockáztatniuk.")

    # 121) Az ő folyamatos meccsképük × a ti szűk rotációtok: a
    # kulcsembereitek pihentetését előre be kell tervezni.
    if opp.ptp_total_s >= 600.0 and own.rotation_matches >= 1:
        _eff121 = (100.0 * (opp.ptp_total_s - opp.ptp_stopped_s)
                   / opp.ptp_total_s)
        _used121 = own.rotation_used_sum / own.rotation_matches
        if _eff121 >= 92.0 and _used121 <= 10.0:
            plan.append(
                f"Folyamatos meccsre kell készülni (az effektív "
                f"játékidő {_eff121:.0f}%), ti pedig szűk rotációval "
                f"játszotok (átlag {_used121:.0f} bevetett játékos) — "
                "a pihentetést előre be kell tervezni: kijelölt "
                "cserepárok, és a kulcsembereitek a második félidő "
                "elején kapjanak két-három perc szusszanást, mert "
                "megállás nem lesz.")

    # 120) Az ő kemény faluk × a ti hetes-mérlegetek: a betörés
    # duplán fizet, ha a hetes nálatok kész gól.
    _own7 = own.seven_takers or []
    _att120 = sum(p.get("attempts", 0) for p in _own7)
    _gol120 = sum(p.get("goals", 0) for p in _own7)
    if opp.agr_attacks >= 10 and _att120 >= 3:
        _agr120 = (100.0 * (opp.agr_sevens + opp.agr_susp)
                   / opp.agr_attacks)
        _conv120 = 100.0 * _gol120 / _att120
        if _agr120 >= 12.0 and _conv120 >= 70.0:
            plan.append(
                f"Kemény fal (a védekezett támadásaik {_agr120:.0f}%-a "
                f"hetest vagy kiállítást hoz), a ti hetesetek pedig "
                f"kész gól ({_gol120}/{_att120}, {_conv120:.0f}%) — a "
                "betörést vállalni kell: minden áthaladás helyzet, "
                "minden lerántás hetes és emberelőny, és ott ti "
                "nyertek a mérlegen.")

    # 119) Az ő elöl lógó emberük × a ti gyors kapus-indításotok: a
    # kontrát pont az ő oldalán kell vezetni.
    _rcd119 = [p for p in (opp.recovery_players or [])
               if p["frames"] >= 200]
    if _rcd119 and own.rs_restarts >= 4:
        _worst119 = min(_rcd119,
                        key=lambda p: p["home_frames"] / p["frames"])
        _pct119 = 100.0 * _worst119["home_frames"] / _worst119["frames"]
        _fast119 = 100.0 * own.rs_fast / own.rs_restarts
        if _pct119 < 70.0 and _fast119 >= 50.0:
            _who119 = (f"{_worst119['jersey']}-es mezszámú"
                       if _worst119.get("jersey") is not None
                       else f"{_worst119['player_id']} azonosítójú")
            plan.append(
                f"A(z) {_who119} játékosuk elöl lóg védekezéskor (a "
                f"védekezett időnek csak {_pct119:.0f}%-ában van a "
                f"saját térfelén), ti pedig gyorsan indítotok (az "
                f"újraindításaitok {_fast119:.0f}%-ánál 12 mp-en "
                "belül átér a labda) — a kontrát az ő oldalán kell "
                "vezetni: a kapus azonnal arra indítson, mert ott "
                "eggyel kevesebben állnak vissza.")

    # 118) Az ő kapusuk gyenge tempó-sávja × a ti lövőerőtök: a
    # lövés-választást a kapusuk gyengéjéhez kell igazítani.
    if opp.gsp_hard_faced >= 4 and opp.gsp_placed_faced >= 4 \
            and own.spw_team_shots >= 6:
        _h118 = 100.0 * opp.gsp_hard_saves / opp.gsp_hard_faced
        _p118 = 100.0 * opp.gsp_placed_saves / opp.gsp_placed_faced
        _own118 = own.spw_team_sum_kmh / own.spw_team_shots
        if _p118 - _h118 >= 15.0 and _own118 >= 75.0:
            plan.append(
                f"A kapusuk a helyezett lövéseket fogja "
                f"({_p118:.0f}%), a keményeket nem ({_h118:.0f}%), a "
                f"ti átlagos lövés-sebességetek pedig "
                f"{_own118:.0f} km/h — vele szemben a tempó a "
                "megoldás: vállalni kell a kemény lövést a 9 m-ről, "
                "és nem a sarkokat keresgélni.")
        elif _h118 - _p118 >= 15.0:
            plan.append(
                f"A kapusuk a bombákat fogja ({_h118:.0f}%), a "
                f"helyezett lövéseket nem ({_p118:.0f}%) — a "
                "lövőitek ne erőből próbálkozzanak: sarokba helyezve, "
                "megemelt vagy pattintott lövéssel kell befejezni, "
                "és a hetesnél is ez a terv.")

    # 117) Az ő álló emberük × a ti kettőzésetek: pont onnan lehet
    # elvenni a védőt a kettőzéshez.
    _sta117 = [p for p in (opp.static_attackers or [])
               if p["seconds"] >= 60.0]
    _all117 = [p for p in (opp.static_attackers or [])
               if p["seconds"] > 0]
    if _sta117 and _all117 and own.dbl_holder_frames >= 250:
        _t117 = sum(p["seconds"] for p in _all117)
        _d117 = sum(p["dist_m"] for p in _all117)
        _avg117 = _d117 / _t117 if _t117 else 0.0
        _slow117 = min(_sta117, key=lambda p: p["dist_m"] / p["seconds"])
        _v117 = _slow117["dist_m"] / _slow117["seconds"]
        _dbl117 = 100.0 * own.dbl_doubled_frames / own.dbl_holder_frames
        if _avg117 > 0 and (100.0 * (_avg117 - _v117) / _avg117) >= 30.0 \
                and _dbl117 >= 30.0:
            _who117 = (f"{_slow117['jersey']}-es mezszámú"
                       if _slow117.get("jersey") is not None
                       else f"{_slow117['player_id']} azonosítójú")
            plan.append(
                f"A(z) {_who117} játékosuk alig mozog a támadásban "
                f"({_v117:.2f} m/s a csapatátlag {_avg117:.2f} m/s "
                f"helyett), ti pedig sokat kettőztök (a labdás-idő "
                f"{_dbl117:.0f}%-ában) — az ő védőjét kell a "
                "kettőzésre küldeni: onnan vehető el ember a "
                "legkisebb kockázattal.")

    # 116) Az ő gyenge szélsőjük × a ti kifutó szélső-védekezésetek: a
    # segítést arról az oldalról lehet befelé hozni.
    if opp.wfs_left_shots >= 3 and opp.wfs_right_shots >= 3 \
            and own.wg_frames >= 100:
        _l116 = 100.0 * opp.wfs_left_goals / opp.wfs_left_shots
        _r116 = 100.0 * opp.wfs_right_goals / opp.wfs_right_shots
        if abs(_l116 - _r116) >= 25.0:
            _weak116 = "jobb" if _l116 > _r116 else "bal"
            _strong116 = "bal" if _l116 > _r116 else "jobb"
            _wgap116 = 100.0 * own.wg_wide / own.wg_frames
            if _wgap116 >= 40.0:
                plan.append(
                    f"A {_weak116} szélsőjük gyengén fejez be "
                    f"({min(_l116, _r116):.0f}%, a {_strong116} "
                    f"oldalon {max(_l116, _r116):.0f}%), a ti falatok "
                    f"pedig réses (a kockák {_wgap116:.0f}%-ában 3,5 "
                    "m-nél nagyobb rés van) — a gyenge oldalon rá "
                    "lehet engedni a lövést, és onnan kell befelé "
                    "hozni a segítést, hogy a rések bezáruljanak.")

    # 115) Az ő beállójuk oldala × a ti gyenge védő-oldalatok: ha
    # egybeesik, ott kell a segítést megerősíteni.
    _pvsn115 = opp.pvs_left + opp.pvs_center + opp.pvs_right
    _wings115 = own.csb_left + own.csb_right
    if _pvsn115 >= 100 and _wings115 >= 8:
        _best115, _cnt115 = max(
            (("bal", opp.pvs_left), ("jobb", opp.pvs_right)),
            key=lambda kv: kv[1])
        _pct115 = 100.0 * _cnt115 / _pvsn115
        _weak115 = "bal" if own.csb_left >= own.csb_right else "jobb"
        _wpct115 = (100.0 * max(own.csb_left, own.csb_right)
                    / _wings115)
        # A támadó bal keze felőli oldal a fal JOBB oldalával néz szembe.
        _mirror115 = "jobb" if _best115 == "bal" else "bal"
        if _pct115 >= 55.0 and _wpct115 >= 65.0 \
                and _mirror115 == _weak115:
            plan.append(
                f"A beállójuk a {_best115} oldalukon dolgozik (a mért "
                f"kockák {_pct115:.0f}%-ában), és pont a ti falatok "
                f"{_weak115} oldala az átjárható (a kapott "
                f"szélső-sávos lövések {_wpct115:.0f}%-a onnan jön) — "
                "ez a két gyengeség egymásra talál: oda kell a "
                "legerősebb védőpár, előre megbeszélt átadással, és "
                "onnan ne induljon kilépés a beálló mögül.")

    # 114) Az ő lassan csúszó faluk × a ti oldalváltásaitok: a
    # keresztpassz pont az ő késésüket bünteti.
    if opp.dsl_frames >= 200 and opp.dsl_sum_s > 0 \
            and own.ssw_passes >= 30:
        _lag114 = opp.dsl_sum_s / opp.dsl_frames
        _ssw114 = 100.0 * own.ssw_switches / own.ssw_passes
        if _lag114 >= 0.6 and _ssw114 >= 12.0:
            plan.append(
                f"Lassan csúszik a faluk ({_lag114:.1f} mp késéssel "
                f"követik az oldalváltást), ti pedig amúgy is sokat "
                f"váltotok oldalt (a támadó passzaitok {_ssw114:.0f}%-a "
                "keresztpassz) — ezt kell fokozni: két gyors "
                "átjátszás, és a HARMADIK oldalon már érkezzen a "
                "befejező, mert a faluk ott még nincs a helyén.")

    # 113) Az ő lágy labdajáratásuk × a ti labdaszerzéseitek: a
    # beleérő védekezés pont ellenük fizet ki.
    if opp.psp_passes >= 10 and own.steal_n >= 4:
        _psp113 = 100.0 * opp.psp_fast / opp.psp_passes
        _avg113 = opp.psp_sum_ms / opp.psp_passes
        if _psp113 <= 20.0:
            plan.append(
                f"Lágy a labdajáratásuk (a passzaiknak csak "
                f"{_psp113:.0f}%-a feszes, átlag {_avg113:.1f} m/s), "
                f"ti pedig tudtok labdát szerezni "
                f"({own.steal_n} szerzés) — a beleérő védekezés pont "
                "ellenük fizet ki: a passzsávokba kell lépni, "
                "elsősorban a beadásoknál és az oldalváltásoknál, "
                "mert az elfogott labda azonnali kontra.")

    # 112) Az ő egyszemélyes beálló-kiszolgálásuk × a ti
    # beálló-védekezésetek: a kiszolgálót zárva a beállójuk kiesik.
    _pf112 = opp.pivot_feeders or []
    _pfn112 = sum(p["feeds"] for p in _pf112)
    if _pf112 and _pfn112 >= 4 and own.pd_pivot_attacks >= 4:
        _top112 = _pf112[0]
        _pct112 = 100.0 * _top112["feeds"] / _pfn112
        _pv112 = 100.0 * own.pd_pivot_goals / max(1, own.pd_pivot_attacks)
        _ot112 = (100.0 * own.pd_other_goals
                  / max(1, own.pd_other_attacks))
        _tie112 = (len(_pf112) > 1
                   and _pf112[1]["feeds"] == _top112["feeds"])
        if _pct112 >= 50.0 and not _tie112 and _pv112 - _ot112 >= 10.0:
            _who112 = (f"{_top112['jersey']}-es mezszámú"
                       if _top112.get("jersey") is not None
                       else f"{_top112['player_id']} azonosítójú")
            plan.append(
                f"A beállójukat a(z) {_who112} játékosuk szolgálja ki "
                f"(a beadások {_pct112:.0f}%-a), ti pedig pont a "
                f"beállós támadások ellen szivárogtok (azokból "
                f"{_pv112:.0f}%, a többiből {_ot112:.0f}% gól) — a "
                "megoldás nem a beállónál van, hanem a "
                "kiszolgálójánál: rá kell lépni az átadás-vonalba, "
                "és az ő oldalán kell kettőzni.")

    # 111) Az ő hetes-okozó védőjük × a ti hetes-kiharcolóitok: a
    # betörést oda kell irányítani, ahol a kéz megjelenik.
    _smc111 = opp.seven_conceders or []
    _sme111 = own.seven_earners or []
    if _smc111 and _smc111[0]["conceded"] >= 2 \
            and _sme111 and _sme111[0]["earned"] >= 2:
        _def111 = _smc111[0]
        _att111 = _sme111[0]
        _dwho111 = (f"{_def111['jersey']}-es mezszámú"
                    if _def111.get("jersey") is not None
                    else f"{_def111['player_id']} azonosítójú")
        _awho111 = (f"{_att111['jersey']}-es mezszámú"
                    if _att111.get("jersey") is not None
                    else f"{_att111['player_id']} azonosítójú")
        plan.append(
            f"A(z) {_dwho111} védőjük {_def111['conceded']} hetest "
            f"okozott, a ti {_awho111} játékosotok pedig "
            f"{_att111['earned']} hetest harcolt ki — őket kell "
            "egymásra irányítani: a betörés az ő oldalára menjen, "
            "mert ott vagy áthaladtok, vagy hetest és kiállítást ér.")

    # 110) Az ő mély támadásuk × a ti felfutó falatok: a kilépés pont
    # az ő lövés-előkészítésüket töri meg.
    if opp.adp_frames >= 100 and opp.adp_sum_m > 0 \
            and own.defline_frames >= 100 and own.defline_sum_m > 0:
        _adp110 = opp.adp_sum_m / opp.adp_frames
        _dl110 = own.defline_sum_m / own.defline_frames
        if _adp110 >= 12.0 and _dl110 >= 7.5:
            plan.append(
                f"Mélyen támadnak (átlagosan {_adp110:.1f} m-re a "
                f"kaputól), a ti falatok pedig amúgy is felfutó "
                f"({_dl110:.1f} m-en áll) — a kilépés pont az ő "
                "lövés-előkészítésüket töri meg: a második vonal "
                "időben lépjen a lövő-vonalba, mert onnan a távoli "
                "lövés az egyetlen fegyverük, és a mély felállásuk "
                "miatt van idő visszazárni a betörésre.")

    # 109) Az ő közép-központú támadásuk × a ti tömör falatok: a
    # szélső-védőitek nyugodtan segíthetnek befelé.
    if opp.wi_attacks >= 8 and own.defw_frames >= 100:
        _wi109 = 100.0 * opp.wi_with_wing / opp.wi_attacks
        _dw109 = own.defw_sum_m / own.defw_frames
        if _wi109 <= 30.0 and _dw109 <= 12.0:
            plan.append(
                f"Közép-központúak (a támadásaiknak csak "
                f"{_wi109:.0f}%-ában jut ki a labda a szélre), a ti "
                f"falatok pedig amúgy is tömör ({_dw109:.1f} m átlagos "
                "szélesség) — ez a párosítás nektek kedvez: a "
                "szélső-védőitek bátran segíthetnek befelé, kettőzzék "
                "a beállót és az átlövőt, mert a szélre-játékkal nem "
                "fognak megbüntetni.")

    # 108) Az ő hátrányban feljebb lépő faluk × a ti gyors
    # középkezdésetek: a letámadásuk pont akkor jön, amikor ti amúgy is
    # gyorsan indítanátok.
    if opp.lhs_lead_frames >= 100 and opp.lhs_trail_frames >= 100 \
            and own.rs_restarts >= 4:
        _lead108 = opp.lhs_lead_sum_m / opp.lhs_lead_frames
        _trail108 = opp.lhs_trail_sum_m / opp.lhs_trail_frames
        _fast108 = 100.0 * own.rs_fast / own.rs_restarts
        if _trail108 - _lead108 >= 0.8 and _fast108 >= 50.0:
            plan.append(
                f"Hátrányban feljebb lépnek (hátrányban "
                f"{_trail108:.1f} m-en, vezetve {_lead108:.1f} m-en "
                f"áll a faluk), ti pedig gyorsan indítotok "
                f"középről (az újraindításaitok {_fast108:.0f}%-ánál "
                "12 mp-en belül átér a labda) — a gólotok után "
                "azonnal jön a letámadásuk: pont ilyenkor kell a "
                "leggyorsabban kezdeni, mert a felfutó faluk mögött "
                "nagy a tér, és a második passz már helyzet.")

    # 107) Az ő lövés nélkül elhaló támadásaik × a ti kettőzésetek: a
    # nyomás pont ott fizet ki, ahol ők amúgy is elakadnak.
    _ao107 = opp.attack_outcomes or {}
    _aon107 = sum(_ao107.values())
    if _aon107 >= 8 and own.dbl_holder_frames >= 250:
        _to107 = 100.0 * _ao107.get("eladás", 0) / _aon107
        _dbl107 = 100.0 * own.dbl_doubled_frames / own.dbl_holder_frames
        if _to107 >= 25.0 and _dbl107 >= 30.0:
            plan.append(
                f"A támadásaik {_to107:.0f}%-a lövés nélkül, "
                f"eladással hal el ({_aon107} támadásból), ti pedig "
                f"sokat kettőztök (a labdás-idő {_dbl107:.0f}%-ában "
                f"két védő is rálép, {own.dbl_forced_to} "
                "kikényszerített eladás) — a kettőzést végig kell "
                "vinni: a labdásra menjetek rá a kidolgozás elején, "
                "mert ők a befejezésig sem jutnak el, és minden "
                "elvett labda azonnali kontra.")

    # 106) Az ő kapusuk gyenge szöge × a ti onnan szerzett góljaitok:
    # oda kell szervezni a befejezést.
    _gs106 = list((opp.gk_role_saves or {}).items())
    _gsf106 = sum(r["faced"] for _, r in _gs106)
    _gss106 = sum(r["saves"] for _, r in _gs106)
    _og106 = list((own.role_goals or {}).items())
    _ogn106 = sum(n for _, n in _og106)
    if _gs106 and _gsf106 >= 8 and _og106 and _ogn106 >= 5:
        _cand106 = [(poszt, r) for poszt, r in _gs106 if r["faced"] >= 4]
        if _cand106:
            _avg106 = 100.0 * _gss106 / _gsf106
            _poszt106, _rec106 = min(
                _cand106, key=lambda kv: kv[1]["saves"] / kv[1]["faced"])
            _pct106 = 100.0 * _rec106["saves"] / _rec106["faced"]
            _own106 = dict(_og106).get(_poszt106, 0)
            _ownpct106 = 100.0 * _own106 / _ogn106
            if _avg106 - _pct106 >= 15.0 and _ownpct106 >= 30.0:
                plan.append(
                    f"A kapusuk a {_poszt106} posztról csak "
                    f"{_pct106:.0f}%-ot fog (csapat-átlaga "
                    f"{_avg106:.0f}%), a ti góljaitok "
                    f"{_ownpct106:.0f}%-a pedig pont onnan született "
                    f"({_own106}/{_ogn106}) — a befejezést oda kell "
                    f"szervezni: a {_poszt106} kapja a labdát "
                    "helyzetben, és lőjön bátran, mert azt a szöget "
                    "a kapusuk nem zárja.")

    # 105) Az ő hiba-sorozataik × a ti gyors kontráitok: a második
    # ajándékot azonnal büntetni kell.
    if opp.tc_turnovers >= 5 and own.trans_steals >= 4:
        _tc105 = 100.0 * opp.tc_clustered / opp.tc_turnovers
        _cv105 = (100.0 * own.trans_quick_goals
                  / max(1, own.trans_steals))
        if _tc105 >= 50.0 and _cv105 >= 30.0:
            plan.append(
                f"Sorozatban hibáznak (az eladásaik {_tc105:.0f}%-a "
                f"egy percen belül követi az előzőt), ti pedig "
                f"gyorsan büntettek (a labdaszerzéseitek "
                f"{_cv105:.0f}%-ából lett azonnali gól) — az első "
                "megszerzett labda után maradjon fent a nyomás: "
                "azonnali letámadás a kihozatalukra, mert a második "
                "hiba percen belül jön, és az dönthet egy ötös "
                "sorozatot.")

    # 104) Az ő gyenge posztjuk × a ti ugyanonnan szerzett góljaitok:
    # oda kell szervezni a befejezést, ahol ők engednek.
    _cr104 = list((opp.conceded_roles or {}).items())
    _crn104 = sum(n for _, n in _cr104)
    _og104 = list((own.role_goals or {}).items())
    _ogn104 = sum(n for _, n in _og104)
    if _cr104 and _crn104 >= 5 and _og104 and _ogn104 >= 5:
        _cr104.sort(key=lambda kv: -kv[1])
        _og104.sort(key=lambda kv: -kv[1])
        _poszt104, _top104 = _cr104[0]
        _pct104 = 100.0 * _top104 / _crn104
        _own104 = dict(_og104).get(_poszt104, 0)
        _ownpct104 = 100.0 * _own104 / _ogn104
        if _pct104 >= 45.0 and _ownpct104 >= 30.0:
            plan.append(
                f"A kapott góljaik {_pct104:.0f}%-a a {_poszt104} "
                f"posztról jön ({_top104}/{_crn104}), a ti góljaitok "
                f"{_ownpct104:.0f}%-a pedig pont onnan született "
                f"({_own104}/{_ogn104}) — oda kell szervezni a "
                f"befejezést: a {_poszt104} posztra tervezett "
                "figurákkal indítsatok, mert ott találkozik az ő "
                "gyengéjük a ti erősségetekkel.")

    # 103) Az ő beállóra épülő befejezésük × a ti beálló-védekezésetek:
    # ha a beállós támadások ellen szivárogtok, ez a meccs kulcsa.
    _rg103 = list((opp.role_goals or {}).items())
    _rgn103 = sum(n for _, n in _rg103)
    if _rg103 and _rgn103 >= 5 and own.pd_pivot_attacks >= 4:
        _rg103.sort(key=lambda kv: -kv[1])
        _poszt103, _top103 = _rg103[0]
        _pct103 = 100.0 * _top103 / _rgn103
        _pv103 = 100.0 * own.pd_pivot_goals / max(1, own.pd_pivot_attacks)
        _ot103 = (100.0 * own.pd_other_goals
                  / max(1, own.pd_other_attacks))
        if _poszt103 == "beálló" and _pct103 >= 45.0 \
                and _pv103 - _ot103 >= 10.0:
            plan.append(
                f"A góljaik {_pct103:.0f}%-a a beálló posztról jön "
                f"({_top103}/{_rgn103}), ti pedig pont a beállós "
                f"támadások ellen szivárogtok (azokból {_pv103:.0f}%, "
                f"a többiből {_ot103:.0f}% gól) — ez a meccs kulcsa: "
                "a beálló elé kell állni, a kiszolgáló passzt "
                "megelőzni, és a középső védőknek hangosan kell "
                "átadniuk egymásnak.")

    # 102) Az ő gólpassz-vonaluk × a ti blokkjaitok: az átlövésből
    # előkészített gólok ellen az előrelépés fizet ki.
    _az102 = list((opp.assist_zones or {}).items())
    _azn102 = sum(n for _, n in _az102)
    if _az102 and _azn102 >= 4 and own.blk_attempts >= 4:
        _az102.sort(key=lambda kv: -kv[1])
        _zone102, _top102 = _az102[0]
        _pct102 = 100.0 * _top102 / _azn102
        _blk102 = 100.0 * own.blk_for / max(1, own.blk_attempts)
        if _zone102 == "átlövésből" and _pct102 >= 50.0 \
                and _blk102 >= 25.0:
            plan.append(
                f"A gólpasszaik {_pct102:.0f}%-a átlövésből érkezik "
                f"({_top102}/{_azn102}), ti pedig blokkoltok is (a "
                f"lövéseik {_blk102:.0f}%-ába belenyúltatok) — az "
                "előrelépés duplán fizet: a második vonal lépjen ki a "
                "lövő-vonalba felemelt kézzel, mert onnan nemcsak a "
                "lövés, az előkészítő beadás is elakad.")

    # 101) Az ő egyszemélyes kihozataluk × a ti elöl szerzett
    # labdáitok: a letámadás pont rá fizet ki.
    _st101 = opp.starters or []
    _stn101 = sum(x["starts"] for x in _st101)
    if _st101 and _stn101 >= 6 and own.steal_n >= 4:
        _top101 = max(_st101, key=lambda x: x["starts"])
        _pct101 = 100.0 * _top101["starts"] / _stn101
        _high101 = 100.0 * own.steal_high / max(1, own.steal_n)
        if _pct101 >= 40.0 and _high101 >= 30.0:
            _who101 = (f"{_top101['jersey']}-es mezszámú"
                       if _top101.get("jersey") is not None
                       else f"{_top101['player_id']} azonosítójú")
            plan.append(
                f"A(z) {_who101} játékosuk hozza fel a labdát a "
                f"támadások {_pct101:.0f}%-ában, ti pedig elöl is "
                f"tudtok szerezni (a labdaszerzéseitek "
                f"{_high101:.0f}%-a a támadó térfélen) — a "
                "letámadás pont rá fizet ki: kapott gól után ketten "
                "menjenek a kihozatalára, és zárjátok az első "
                "átadás-vonalát.")

    # 100) Az ő késői fékük × a ti gólsorozataitok: van két-három
    # támadásnyi ablak, ha megindul a hullám.
    if opp.tot_timeouts >= 2 and own.rn_made >= 2:
        _avg100 = opp.tot_sum_before / opp.tot_timeouts
        if _avg100 >= 2.5:
            plan.append(
                f"Későn fékeznek (átlag {_avg100:.1f} kapott gól után "
                f"kérnek időt), ti pedig tudtok sorozatot vinni "
                f"({own.rn_made} gólsorozatotok volt) — ha megindul a "
                "hullám, van két-három támadásnyi ablakotok az "
                "időkérésükig: ott kell a legnagyobbat ütni, gyors "
                "középkezdéssel és azonnali befejezéssel.")

    # 99) Az ő legjobb párosuk × a ti időkéréseitek: a jól menő
    # kettőst meg kell törni.
    _prm99 = [p for p in (opp.pair_plus_minus or [])
              if p["frames"] / (opp.pair_fps or 25.0) / 60.0 >= 4.0]
    if _prm99 and own.to_n >= 1:
        _b99 = max(_prm99,
                   key=lambda p: ((p["for"] - p["against"])
                                  / max(0.1, p["frames"]
                                        / (opp.pair_fps or 25.0) / 60.0)))
        _m99 = _b99["frames"] / (opp.pair_fps or 25.0) / 60.0
        if (_b99["for"] - _b99["against"]) / _m99 >= 0.2:
            plan.append(
                f"A(z) {' és '.join(str(i) for i in _b99['players'])} "
                f"azonosítójú kettősük együtt megy a legjobban "
                f"({_b99['for']}-{_b99['against']} {_m99:.0f} közös "
                "perc alatt) — tartsatok fenn egy időkérést arra a "
                "szakaszra, amikor együtt vannak a pályán, és "
                "kettőzzétek azt, aki hamarabb fárad: a párost szét "
                "kell szedni, nem egyenként legyőzni.")

    # 98) Az ő blokkos cseréjük × a ti gyors újraindításotok: csere
    # közben egy ütemre rossz emberek vannak a pályán.
    if opp.sbl_waves >= 4 and own.rs_restarts >= 4:
        _blk98 = 100.0 * opp.sbl_block_waves / opp.sbl_waves
        _fast98 = 100.0 * own.rs_fast / own.rs_restarts
        if _blk98 >= 40.0 and _fast98 >= 50.0:
            plan.append(
                f"Egységekben cserélnek (a {opp.sbl_waves} "
                f"hullámukból {opp.sbl_block_waves} volt 2+ fős), ti "
                f"pedig gyorsan indítotok újra (az "
                f"újraindításaitok {_fast98:.0f}%-ánál 12 mp-en belül "
                "átér a labda) — gól után azonnal indulni kell: a "
                "cseréjük közben egy ütemre rossz emberek vannak a "
                "pályán, és a védekező egységük támadásban "
                "kiszolgáltatott.")

    # 97) Az ő lövőerő-esésük × a ti mély falatok: a hajrában kintebb
    # lehet jönni.
    if opp.ssf_fh_n >= 5 and opp.ssf_sh_n >= 5 \
            and own.defline_frames >= 100:
        _fh97 = opp.ssf_fh_sum_kmh / opp.ssf_fh_n
        _sh97 = opp.ssf_sh_sum_kmh / opp.ssf_sh_n
        _line97 = own.defline_sum_m / own.defline_frames
        if _fh97 - _sh97 >= 6.0 and _line97 <= 6.5:
            plan.append(
                f"A 2. félidőre esik a lövéserejük ({_fh97:.0f} → "
                f"{_sh97:.0f} km/h), ti pedig mélyen védekeztek (a "
                f"falatok átlagosan {_line97:.1f} m-re áll a saját "
                "kaputoktól) — a hajrában kintebb lehet jönni: a "
                "fáradt átlövésük már nem üt át, a magasabb fal "
                "viszont a ziccerig kényszeríti őket.")

    # 96) Az ő labdatartójuk × a ti elöl-szerzéseitek: nála van idő
    # odaérni.
    _htp96 = [p for p in (opp.hold_players or []) if p["holds"] >= 5]
    _hold96 = sum(p["holds"] for p in (opp.hold_players or []))
    if _htp96 and _hold96 >= 5 and own.steal_n >= 6 \
            and 100.0 * own.steal_high / own.steal_n >= 35.0:
        _avg96 = (sum(p["frames"] for p in (opp.hold_players or []))
                  / _hold96 / (opp.hold_fps or 25.0))
        _slow96 = max(_htp96, key=lambda p: p["frames"] / p["holds"])
        _s96 = (_slow96["frames"] / _slow96["holds"]
                / (opp.hold_fps or 25.0))
        if _s96 - _avg96 >= 0.8:
            _who96 = (f"{_slow96['jersey']}-es mezszámú"
                      if _slow96.get("jersey") is not None
                      else f"{_slow96['player_id']} azonosítójú")
            plan.append(
                f"A(z) {_who96} játékosuknál áll meg a labda (átlag "
                f"{_s96:.1f} mp a csapatátlag {_avg96:.1f} mp "
                f"helyett), ti pedig sokat szereztek elöl (a "
                f"szerzéseitek "
                f"{100.0 * own.steal_high / own.steal_n:.0f}%-a) — a "
                "letámadást rá kell időzíteni: amikor nála van a "
                "labda, jöjjön a második védő, mert nála van idő "
                "odaérni.")

    # 95) Az ő védekezés-váltásuk × a ti lerohanásaitok: a váltás csak
    # felállt védekezésben él.
    if opp.fsw_attacks >= 6 and opp.fsw_pairs > 0 \
            and own.fast_break_pct >= 8.0:
        _sw95 = 100.0 * opp.fsw_switches / opp.fsw_pairs
        if _sw95 >= 30.0:
            _main95 = (max(opp.fsw_labels.items(),
                           key=lambda kv: kv[1])[0]
                       if opp.fsw_labels else "?")
            plan.append(
                f"Váltogatják a védekezést (a védekezett támadások "
                f"{_sw95:.0f}%-ánál más fal, alapból {_main95}), ti "
                f"pedig sokat rohantok le "
                f"({own.fast_break_pct:.0f}% lerohanás-arány) — a "
                "váltás csak felállt védekezésben él: minden "
                "labdaszerzés és kapott gól után azonnal indulni "
                "kell, mielőtt eldöntik, milyen falat állítanak.")

    # 94) Az ő gyenge védőjük × a ti elzárás-használatotok: oda kell
    # vinni a befejezéseket.
    if opp.tdf_shots >= 4 and own.scu_shots >= 8 \
            and 100.0 * own.scu_screened / own.scu_shots >= 40.0:
        _avg94 = 100.0 * opp.tdf_goals / opp.tdf_shots
        _w94 = None
        for p in (opp.targeted_defenders or []):
            if p["shots"] < 4:
                continue
            _g94 = 100.0 * p["goals"] / p["shots"] - _avg94
            if _g94 >= 15.0 and (_w94 is None or _g94 > _w94[1]):
                _w94 = (p, _g94)
        if _w94 is not None:
            _p94 = _w94[0]
            _who94 = (f"{_p94['jersey']}-es mezszámú"
                      if _p94.get("jersey") is not None
                      else f"{_p94['player_id']} azonosítójú")
            plan.append(
                f"A(z) {_who94} védőjük előtt megy be a legtöbb lövés "
                f"({_p94['goals']}/{_p94['shots']}, a csapatátlaguk "
                f"felett {_w94[1]:.0f} százalékponttal), ti pedig "
                f"sokat zártok el (a lövéseitek "
                f"{100.0 * own.scu_screened / own.scu_shots:.0f}"
                "%-ánál) — az elzárásokat rá kell szervezni: az ő "
                "oldalán jöjjön a beálló és a befejezés.")

    # 93) Az ő legjobb mérlegű játékosuk × a ti kettőzésetek: őt kell
    # a leginkább zavarni.
    _pm93 = [p for p in (opp.player_plus_minus or [])
             if p["frames"] / (opp.pm_fps or 25.0) / 60.0 >= 5.0]
    if _pm93 and own.dbl_holder_frames >= 250 \
            and 100.0 * own.dbl_doubled_frames / own.dbl_holder_frames \
            >= 30.0:
        _b93 = max(_pm93,
                   key=lambda p: ((p["for"] - p["against"])
                                  / max(0.1, p["frames"]
                                        / (opp.pm_fps or 25.0) / 60.0)))
        _m93 = _b93["frames"] / (opp.pm_fps or 25.0) / 60.0
        if (_b93["for"] - _b93["against"]) / _m93 >= 0.15:
            plan.append(
                f"A(z) {_b93['player_id']} azonosítójú játékosuk "
                f"pályán léte alatt megy a legjobban a játékuk "
                f"({_b93['for']}-{_b93['against']} {_m93:.0f} perc "
                f"alatt), ti pedig sokat kettőztök (a labdás-idő "
                f"{100.0 * own.dbl_doubled_frames / own.dbl_holder_frames:.0f}"
                "%-ában) — a kettőzést rá kell időzíteni: amikor nála "
                "a labda, jöjjön a második védő.")

    # 92) Az ő bombázójuk × a ti aktív falatok: a szöget kell zárni,
    # nem vakon blokkolni.
    if opp.spw_team_shots >= 6 and own.blocks >= 3:
        _spw_avg92 = opp.spw_team_sum_kmh / opp.spw_team_shots
        for _p92 in (opp.shooter_power or []):
            if _p92["shots"] < 4:
                continue
            _pavg92 = _p92["sum_kmh"] / _p92["shots"]
            if _pavg92 - _spw_avg92 >= 8.0:
                plan.append(
                    f"A(z) {_p92['player_id']} azonosítójú lövőjük "
                    f"bombáz ({_pavg92:.0f} km/h átlag, csapatátlag "
                    f"{_spw_avg92:.0f} km/h), ti pedig aktívan "
                    f"blokkoltok ({own.blocks} blokk) — ellene a fal "
                    "ne vakon ugorjon: zárjátok a szöget és a lövő "
                    "karját, a kapus a másik oldalt védje.")
                break

    # 91) Az ő kiszámítható lövőjük × a ti kapusotok formája: névre
    # szóló kapus-felkészítés.
    _shp91 = None
    for _p91 in (opp.shooter_placement or []):
        if _p91["goals"] < 4:
            continue
        _dom91 = max(("bal", "közép", "jobb"), key=lambda k: _p91[k])
        if 100.0 * _p91[_dom91] / _p91["goals"] >= 60.0:
            _shp91 = (_p91, _dom91,
                      100.0 * _p91[_dom91] / _p91["goals"])
            break
    if _shp91 is not None and own.gk_on_target >= 10 \
            and 100.0 * own.gk_saves / own.gk_on_target >= 30.0:
        _p91, _dom91, _sh91 = _shp91
        plan.append(
            f"A(z) {_p91['player_id']} azonosítójú lövőjük "
            f"kiszámítható (a {_p91['goals']} góljából {_sh91:.0f}% a "
            f"{_dom91} oldalra ment), a ti kapusotok pedig jó formában "
            f"van ({100.0 * own.gk_saves / own.gk_on_target:.0f}% "
            f"védés) — névre szóló felkészítés: a kapus álljon rá a "
            f"{_dom91} sarokra, a fal a másik oldalt zárja.")

    # 90) Az ő szélen nyitott faluk × a ti szélső-játékotok: a szélső
    # bevonása az első számú fegyver.
    if (opp.wdf_wing_shots >= 5 and opp.wdf_center_shots >= 5
            and (100.0 * opp.wdf_wing_goals / opp.wdf_wing_shots)
            - (100.0 * opp.wdf_center_goals / opp.wdf_center_shots)
            >= 15.0
            and own.wing_total_goals >= 5
            and 100.0 * own.wing_goals / own.wing_total_goals >= 25.0):
        plan.append(
            f"A faluk a szélen nyitott (a szélső lövések "
            f"{100.0 * opp.wdf_wing_goals / opp.wdf_wing_shots:.0f}%-a "
            f"gól ellenük, középről "
            f"{100.0 * opp.wdf_center_goals / opp.wdf_center_shots:.0f}"
            f"%), ti pedig sokat szereztek a szélről (a góljaitok "
            f"{100.0 * own.wing_goals / own.wing_total_goals:.0f}%-a) "
            "— szélességben játsszatok: oldalváltás, majd a szélső "
            "kapja meg a labdát tiszta szögben.")

    # 89) Az ő drága eladójuk × a ti magas szerzésetek: rá kell menni
    # a felhozatalnál.
    _ctp89 = next((p for p in (opp.costly_turnover_players or [])
                   if p["turnovers"] >= 3 and p["punished"] >= 2), None)
    if _ctp89 is not None and own.steal_high >= 3:
        plan.append(
            f"A(z) {_ctp89['player_id']} azonosítójú játékosuk "
            f"eladásai kerülnek gólba ({_ctp89['punished']} kapott gól "
            f"{_ctp89['turnovers']} eladásból), ti pedig magasan "
            f"szereztek labdát ({own.steal_high} magas szerzés) — "
            "menjetek rá a felhozatalnál: kettőzés rajta, a "
            "passzsávjait zárva, és a szerzés után azonnal kontra.")

    # 88) Az ő szivárgó emberelőny-védekezésük × a ti lerohanásotok:
    # hátrányban is futni kell ellenük.
    if (opp.ppd_seconds >= 90.0 and opp.ppd_eq_seconds > 0
            and (60.0 * opp.ppd_conceded / opp.ppd_seconds)
            - (60.0 * opp.ppd_eq_conceded / opp.ppd_eq_seconds) >= 0.2
            and own.fast_break_pct >= 10.0):
        plan.append(
            f"Emberelőnyben is szivárognak "
            f"({60.0 * opp.ppd_conceded / opp.ppd_seconds:.2f} kapott "
            f"gól/perc, egyenlő létszámnál "
            f"{60.0 * opp.ppd_eq_conceded / opp.ppd_eq_seconds:.2f}), "
            f"ti pedig sokat indultok ({own.fast_break_pct:.0f}% gyors "
            "indítás) — ha kiállítást kaptok, ne csak túléljetek: a "
            "befejezésük után azonnal induljon a kontra, hátrányban is.")

    # 87) Az ő falfüggő kapusuk × a ti elzárásos játékotok: az
    # elzárásból jövő tiszta átlövés az ellenszer.
    if (opp.gkf_free_shots >= 5 and opp.gkf_cov_shots >= 5
            and (100.0 * opp.gkf_cov_saves / opp.gkf_cov_shots)
            - (100.0 * opp.gkf_free_saves / opp.gkf_free_shots) >= 15.0
            and own.scu_shots >= 8
            and 100.0 * own.scu_screened / own.scu_shots >= 30.0):
        plan.append(
            f"A kapusuk falfüggő (fedezett lövésnél "
            f"{100.0 * opp.gkf_cov_saves / opp.gkf_cov_shots:.0f}%, "
            f"szabadon leadottnál "
            f"{100.0 * opp.gkf_free_saves / opp.gkf_free_shots:.0f}% "
            f"védés), ti pedig sokat játszotok elzárással (a "
            f"lövéseitek "
            f"{100.0 * own.scu_screened / own.scu_shots:.0f}%-a "
            "elzárásból) — ez a párosítás: elzárás után zavartalan "
            "átlövés, ne a falon keresztül lőjetek.")

    # 86) Az ő kettőzésük × a ti gyors passzjátékotok: a kettőzést egy
    # érintéssel kell megbüntetni.
    if (opp.dbl_holder_frames >= 250
            and 100.0 * opp.dbl_doubled_frames / opp.dbl_holder_frames
            >= 30.0
            and own.pt_poss_s >= 60.0
            and 60.0 * own.pt_passes / own.pt_poss_s >= 12.0):
        plan.append(
            f"Sokat kettőznek a labdáson (a labdás-idő "
            f"{100.0 * opp.dbl_doubled_frames / opp.dbl_holder_frames:.0f}"
            f"%-ában), ti pedig gyorsan járatjátok a labdát "
            f"({60.0 * own.pt_passes / own.pt_poss_s:.0f} passz/perc "
            "birtoklás) — ez ellenük a fegyver: egy érintéssel az üres "
            "oldalra, és a kettőzött játékos társa azonnal induljon a "
            "felszabadult helyre.")

    # 85) Az ő egyoldalú kapus-indításuk × a ti magas szerzésetek: az
    # indítás-sáv a ti csapdátok.
    if opp.gos_left + opp.gos_right >= 6 and own.steal_high >= 3:
        _g_all = opp.gos_left + opp.gos_right
        _g_share = opp.gos_left / _g_all
        if _g_share >= 0.65 or 1.0 - _g_share >= 0.65:
            plan.append(
                f"A kapusuk szinte mindig a "
                f"{'bal' if _g_share >= 0.65 else 'jobb'} oldalra "
                f"indít ({100.0 * max(_g_share, 1.0 - _g_share):.0f}%, "
                f"{_g_all} indításból), ti pedig magasan szereztek "
                f"labdát ({own.steal_high} magas szerzés) — állítsatok "
                "csapdát az indítás-sávjukba: a fogadó szélsőt "
                "letámadva a kidobásból lesz a ti kontrátok.")

    # 84) Az ő hajrá-eladásaik × a ti átmenet-támadásotok: a végén az
    # ő hibájuk a ti kontrátok.
    if (opp.cto_early_to >= 5 and opp.cto_early_s > 0
            and opp.cto_clutch_s > 0
            and (60.0 * opp.cto_clutch_to / opp.cto_clutch_s)
            - (60.0 * opp.cto_early_to / opp.cto_early_s) >= 0.3
            and own.trans_steals >= 5
            and own.trans_quick_goals >= 2):
        plan.append(
            f"A hajrában megugrik az eladás-ütemük "
            f"({60.0 * opp.cto_early_to / opp.cto_early_s:.2f} → "
            f"{60.0 * opp.cto_clutch_to / opp.cto_clutch_s:.2f} "
            f"eladás/perc), ti pedig gólra váltjátok a szerzéseket "
            f"({own.trans_quick_goals} gyors gól "
            f"{own.trans_steals} szerzésből) — a hajrában emeljétek a "
            "védekezést: kettőzés a labdavivőn, és minden szerzés "
            "után azonnal induljon a kontra.")

    # 83) Az ő megbénuló hátrány-támadásuk × a ti emberelőny-
    # hatékonyságotok: a két perc a ti aranybányátok.
    if (opp.sha_seconds >= 90.0 and opp.sha_eq_seconds > 0
            and (60.0 * opp.sha_eq_goals / opp.sha_eq_seconds)
            - (60.0 * opp.sha_goals / opp.sha_seconds) >= 0.15
            and own.pp_shots >= 3
            and 100.0 * own.pp_goals / own.pp_shots >= 50.0):
        plan.append(
            f"Emberhátrányban megbénulnak "
            f"({60.0 * opp.sha_goals / opp.sha_seconds:.2f} gól/perc, "
            f"egyenlő létszámnál "
            f"{60.0 * opp.sha_eq_goals / opp.sha_eq_seconds:.2f}), ti "
            f"pedig kihasználjátok az emberelőnyt "
            f"({100.0 * own.pp_goals / own.pp_shots:.0f}% "
            "gólarány) — minden kiharcolt kiállítás gólkülönbség: "
            "harcoljátok ki a hetest/kiállítást, és a két percet "
            "türelmesen, betanult figurából játsszátok végig.")

    # 82) Az ő fölény-függésük × a ti gyors visszarendeződésetek: ha
    # hazaértek, elfogy a fegyverük.
    if (opp.ovl_shots >= 5 and opp.ovl_set_shots >= 5
            and (100.0 * opp.ovl_goals / opp.ovl_shots)
            - (100.0 * opp.ovl_set_goals / opp.ovl_set_shots) >= 15.0
            and own.rec_transitions >= 4
            and own.rec_sum_s / own.rec_transitions <= 4.0):
        plan.append(
            f"Létszámfölényben veszélyesek "
            f"({100.0 * opp.ovl_goals / opp.ovl_shots:.0f}% gólarány), "
            f"felállt fal ellen csak "
            f"{100.0 * opp.ovl_set_goals / opp.ovl_set_shots:.0f}%, ti "
            f"pedig gyorsan hazaértek "
            f"({own.rec_sum_s / own.rec_transitions:.1f} mp átlagos "
            "visszarendeződés) — ez a meccs kulcsa: minden befejezés "
            "után azonnal induljon a visszarendeződés-sprint, és "
            "elfogy a fegyverük.")

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


def _merge_role_counts(dicts) -> dict:
    """Poszt szerinti darabszámok összegzése kulcs szerint."""
    acc: dict = {}
    for d in dicts:
        for k, v in (d or {}).items():
            acc[k] = acc.get(k, 0) + v
    return dict(sorted(acc.items(), key=lambda kv: -kv[1]))


def _merge_bcf_players(reports) -> list:
    """Ziccer-befejezők összegzése játékos szerint."""
    acc: dict = {}
    for r in reports:
        for pr in (r.bcf_players or []):
            rec = acc.setdefault(pr["player_id"], [0, 0])
            rec[0] += pr["chances"]
            rec[1] += pr["goals"]
    return [{"player_id": pid, "chances": c, "goals": g}
            for pid, (c, g) in sorted(acc.items(),
                                      key=lambda kv: -kv[1][0])]


def _merge_screen_pairs(reports) -> list:
    """Elzárás-párosok összegzése: (elzáró, lövő) kulcs szerint."""
    acc: dict = {}
    for r in reports:
        for pr in (r.scp_pairs or []):
            key = (pr["setter_id"], pr["shooter_id"])
            acc[key] = acc.get(key, 0) + pr["shots"]
    return [{"setter_id": s_, "shooter_id": sh_, "shots": n}
            for (s_, sh_), n in sorted(acc.items(),
                                       key=lambda kv: -kv[1])]


def _merge_drb_players(reports) -> list:
    """Csend-törők összegzése: játékos szerint összeadott törések."""
    acc: dict = {}
    for r in reports:
        for pr in (r.drb_players or []):
            acc[pr["player_id"]] = (acc.get(pr["player_id"], 0)
                                    + pr["breaks"])
    return [{"player_id": pid, "breaks": n}
            for pid, n in sorted(acc.items(), key=lambda kv: -kv[1])]


def _merge_cbh_players(reports) -> list:
    """Hajrá-birtokosok összegzése: játékos szerint összeadott labdás
    kockák."""
    acc: dict = {}
    jersey: dict = {}
    for r in reports:
        for pr in (r.cbh_players or []):
            pid = pr["player_id"]
            acc[pid] = acc.get(pid, 0) + pr["frames"]
            if pr.get("jersey") is not None:
                jersey.setdefault(pid, pr["jersey"])
    return [{"player_id": pid, "jersey": jersey.get(pid), "frames": n}
            for pid, n in sorted(acc.items(), key=lambda kv: -kv[1])]


def _merge_pivot_guards(reports) -> list:
    """Beálló-őrök összegzése: játékos szerint összeadott
    őrzés-kockák."""
    acc: dict = {}
    jersey: dict = {}
    for r in reports:
        for pr in (r.pvg_guards or []):
            pid = pr["player_id"]
            acc[pid] = acc.get(pid, 0) + pr["frames"]
            if pr.get("jersey") is not None:
                jersey.setdefault(pid, pr["jersey"])
    return [{"player_id": pid, "jersey": jersey.get(pid), "frames": n}
            for pid, n in sorted(acc.items(), key=lambda kv: -kv[1])]


def _merge_phase_players(reports) -> list:
    """Egyirányú játékosok összegzése: játékos szerint összeadott
    fázis- és védekezés-kockák."""
    acc: dict = {}
    jersey: dict = {}
    for r in reports:
        for pr in (r.phs_players or []):
            pid = pr["player_id"]
            n, d = acc.get(pid, (0, 0))
            acc[pid] = (n + pr["frames"], d + pr["def_frames"])
            if pr.get("jersey") is not None:
                jersey.setdefault(pid, pr["jersey"])
    return [{"player_id": pid, "jersey": jersey.get(pid),
             "frames": n, "def_frames": d}
            for pid, (n, d) in sorted(acc.items(),
                                      key=lambda kv: -kv[1][0])]


def _merge_sprint_threats(reports) -> list:
    """Sprint-veszély összegzése: játékos szerint összeadott sprintek
    és sprint-táv."""
    acc: dict = {}
    jersey: dict = {}
    for r in reports:
        for pr in (r.spt_players or []):
            pid = pr["player_id"]
            n, m = acc.get(pid, (0, 0.0))
            acc[pid] = (n + pr["sprints"], m + pr["sprint_m"])
            if pr.get("jersey") is not None:
                jersey.setdefault(pid, pr["jersey"])
    return [{"player_id": pid, "jersey": jersey.get(pid),
             "sprints": n, "sprint_m": round(m, 1)}
            for pid, (n, m) in sorted(acc.items(),
                                      key=lambda kv: -kv[1][0])]


def _merge_adv_players(reports) -> list:
    """Kilépő-védő jelöltek összegzése: játékos szerint összeadott
    kockák és mélység-összegek."""
    acc: dict = {}
    jersey: dict = {}
    for r in reports:
        for pr in (r.adv_players or []):
            pid = pr["player_id"]
            n, s_ = acc.get(pid, (0, 0.0))
            acc[pid] = (n + pr["frames"], s_ + pr["depth_sum_m"])
            if pr.get("jersey") is not None:
                jersey.setdefault(pid, pr["jersey"])
    return [{"player_id": pid, "jersey": jersey.get(pid),
             "frames": n, "depth_sum_m": s_}
            for pid, (n, s_) in sorted(acc.items(),
                                       key=lambda kv: -kv[1][0])]


def _merge_restart_targets(reports) -> list:
    """Középkezdés-átvevők összegzése: játékos szerint összeadott
    átvétel-darabszámok, csökkenő sorrendben."""
    acc: dict = {}
    jersey: dict = {}
    for r in reports:
        for pr in (r.rst_players or []):
            pid = pr["player_id"]
            acc[pid] = acc.get(pid, 0) + pr["takes"]
            if pr.get("jersey") is not None:
                jersey.setdefault(pid, pr["jersey"])
    return [{"player_id": pid, "jersey": jersey.get(pid), "takes": n}
            for pid, n in sorted(acc.items(), key=lambda kv: -kv[1])]


def _merge_swap_pairs(reports) -> list:
    """Váltópárok összegzése: (ki, be) kulcs szerint összeadott
    darabszámok, csökkenő sorrendben."""
    acc: dict = {}
    for r in reports:
        for pr in (r.swp_pairs or []):
            key = (pr["out_id"], pr["in_id"])
            acc[key] = acc.get(key, 0) + pr["count"]
    return [{"out_id": o, "in_id": i, "count": n}
            for (o, i), n in sorted(acc.items(), key=lambda kv: -kv[1])]


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

def _merge_count_dicts(dicts) -> dict:
    """Címke→darabszám szótárak összegzése kulcsonként."""
    out: dict = {}
    for d in dicts:
        for k, v in (d or {}).items():
            out[k] = out.get(k, 0) + v
    return out


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
        player_plus_minus=_merge_plus_minus(reports),
        pm_fps=(reports[0].pm_fps if reports else 25.0),
        targeted_defenders=_merge_targeted_defenders(reports),
        tdf_shots=sum(r.tdf_shots for r in reports),
        tdf_goals=sum(r.tdf_goals for r in reports),
        crx_attacks=sum(r.crx_attacks for r in reports),
        crx_crosses=sum(r.crx_crosses for r in reports),
        wsv_receptions=sum(r.wsv_receptions for r in reports),
        wsv_running=sum(r.wsv_running for r in reports),
        psv_receptions=sum(r.psv_receptions for r in reports),
        psv_running=sum(r.psv_running for r in reports),
        fbw_breaks=sum(r.fbw_breaks for r in reports),
        fbw_second=sum(r.fbw_second for r in reports),
        fbh_breaks=sum(r.fbh_breaks for r in reports),
        fbh_ahead=sum(r.fbh_ahead for r in reports),
        bsh_blocked=sum(r.bsh_blocked for r in reports),
        bsh_shooters=_merge_role_counts(
            [r.bsh_shooters for r in reports]),
        abr_assists=sum(r.abr_assists for r in reports),
        abr_roles=_merge_role_counts(
            [r.abr_roles for r in reports]),
        sur_suspensions=sum(r.sur_suspensions for r in reports),
        sur_roles=_merge_role_counts(
            [r.sur_roles for r in reports]),
        bbr_blocked=sum(r.bbr_blocked for r in reports),
        bbr_roles=_merge_role_counts(
            [r.bbr_roles for r in reports]),
        otr_outlets=sum(r.otr_outlets for r in reports),
        otr_roles=_merge_role_counts(
            [r.otr_roles for r in reports]),
        brf_fh_attacks=sum(r.brf_fh_attacks for r in reports),
        brf_fh_breaks=sum(r.brf_fh_breaks for r in reports),
        brf_sh_attacks=sum(r.brf_sh_attacks for r in reports),
        brf_sh_breaks=sum(r.brf_sh_breaks for r in reports),
        wsd_shots=sum(r.wsd_shots for r in reports),
        wsd_depth_sum_m=round(sum(r.wsd_depth_sum_m
                                  for r in reports), 1),
        dtp_frames=sum(r.dtp_frames for r in reports),
        dtp_doublers=_merge_role_counts(
            [r.dtp_doublers for r in reports]),
        btn_goals=sum(r.btn_goals for r in reports),
        btn_free=sum(r.btn_free for r in reports),
        btn_defenders=_merge_role_counts(
            [r.btn_defenders for r in reports]),
        upa_assisted=sum(r.upa_assisted for r in reports),
        upa_unpressured=sum(r.upa_unpressured for r in reports),
        gpn_gap_s=round(sum(r.gpn_gap_s for r in reports), 1),
        gpn_gaps=sum(r.gpn_gaps for r in reports),
        gpn_conceded=sum(r.gpn_conceded for r in reports),
        crg_goals=sum(r.crg_goals for r in reports),
        crg_open=sum(r.crg_open for r in reports),
        ctm_goals=sum(r.ctm_goals for r in reports),
        ctm_passes_sum=sum(r.ctm_passes_sum for r in reports),
        cgm_goals=sum(r.cgm_goals for r in reports),
        cgm_running=sum(r.cgm_running for r in reports),
        wfk_goals=sum(r.wfk_goals for r in reports),
        wfk_fooled=sum(r.wfk_fooled for r in reports),
        rdk_saves=sum(r.rdk_saves for r in reports),
        rdk_read=sum(r.rdk_read for r in reports),
        dbp_doubled_frames=sum(r.dbp_doubled_frames
                               for r in reports),
        dbp_conceded_after=sum(r.dbp_conceded_after
                               for r in reports),
        sop_goals=sum(r.sop_goals for r in reports),
        sop_behind=sum(r.sop_behind for r in reports),
        pmb_misses=sum(r.pmb_misses for r in reports),
        pmb_punished=sum(r.pmb_punished for r in reports),
        olp_lost=sum(r.olp_lost for r in reports),
        olp_punished=sum(r.olp_punished for r in reports),
        sac_slow=sum(r.sac_slow for r in reports),
        sac_scored=sum(r.sac_scored for r in reports),
        obt_out=sum(r.obt_out for r in reports),
        sps_tr=sum(r.sps_tr for r in reports),
        sps_lead=sum(r.sps_lead for r in reports),
        sps_level=sum(r.sps_level for r in reports),
        svs_tr=sum(r.svs_tr for r in reports),
        svs_lead=sum(r.svs_lead for r in reports),
        svs_level=sum(r.svs_level for r in reports),
        bks_tr_attacks=sum(r.bks_tr_attacks for r in reports),
        bks_tr_breaks=sum(r.bks_tr_breaks for r in reports),
        bks_rest_attacks=sum(r.bks_rest_attacks for r in reports),
        bks_rest_breaks=sum(r.bks_rest_breaks for r in reports),
        ens_tr=sum(r.ens_tr for r in reports),
        ens_lead=sum(r.ens_lead for r in reports),
        ens_level=sum(r.ens_level for r in reports),
        gst_on_target=sum(r.gst_on_target for r in reports),
        gst_streaks=sum(r.gst_streaks for r in reports),
        asf_fh_goals=sum(r.asf_fh_goals for r in reports),
        asf_fh_assisted=sum(r.asf_fh_assisted for r in reports),
        asf_sh_goals=sum(r.asf_sh_goals for r in reports),
        asf_sh_assisted=sum(r.asf_sh_assisted for r in reports),
        scf_fh_misses=sum(r.scf_fh_misses for r in reports),
        scf_fh_won=sum(r.scf_fh_won for r in reports),
        scf_sh_misses=sum(r.scf_sh_misses for r in reports),
        scf_sh_won=sum(r.scf_sh_won for r in reports),
        ams_fh_attacks=sum(r.ams_fh_attacks for r in reports),
        ams_fh_break=sum(r.ams_fh_break for r in reports),
        ams_fh_quick=sum(r.ams_fh_quick for r in reports),
        ams_sh_attacks=sum(r.ams_sh_attacks for r in reports),
        ams_sh_break=sum(r.ams_sh_break for r in reports),
        ams_sh_quick=sum(r.ams_sh_quick for r in reports),
        pds_lead_passes=sum(r.pds_lead_passes for r in reports),
        pds_lead_back=sum(r.pds_lead_back for r in reports),
        pds_rest_passes=sum(r.pds_rest_passes for r in reports),
        pds_rest_back=sum(r.pds_rest_back for r in reports),
        gka_assists=sum(r.gka_assists for r in reports),
        pls_tr_passes=sum(r.pls_tr_passes for r in reports),
        pls_tr_long=sum(r.pls_tr_long for r in reports),
        pls_rest_passes=sum(r.pls_rest_passes for r in reports),
        pls_rest_long=sum(r.pls_rest_long for r in reports),
        dfs_fh_attacks=sum(r.dfs_fh_attacks for r in reports),
        dfs_sh_attacks=sum(r.dfs_sh_attacks for r in reports),
        dfs_fh_labels=_merge_count_dicts(
            r.dfs_fh_labels for r in reports),
        dfs_sh_labels=_merge_count_dicts(
            r.dfs_sh_labels for r in reports),
        sds_fh_frames=sum(r.sds_fh_frames for r in reports),
        sds_sh_frames=sum(r.sds_sh_frames for r in reports),
        sds_fh_counts=_merge_count_dicts(
            r.sds_fh_counts for r in reports),
        sds_sh_counts=_merge_count_dicts(
            r.sds_sh_counts for r in reports),
        tbs_tr_attacks=sum(r.tbs_tr_attacks for r in reports),
        tbs_tr_tos=sum(r.tbs_tr_tos for r in reports),
        tbs_rest_attacks=sum(r.tbs_rest_attacks for r in reports),
        tbs_rest_tos=sum(r.tbs_rest_tos for r in reports),
        dbs_lead_shots=sum(r.dbs_lead_shots for r in reports),
        dbs_lead_xg=round(sum(r.dbs_lead_xg for r in reports), 2),
        dbs_rest_shots=sum(r.dbs_rest_shots for r in reports),
        dbs_rest_xg=round(sum(r.dbs_rest_xg for r in reports), 2),
        sbs_lead_subs=sum(r.sbs_lead_subs for r in reports),
        sbs_rest_subs=sum(r.sbs_rest_subs for r in reports),
        sbs_lead_s=round(sum(r.sbs_lead_s for r in reports), 1),
        sbs_rest_s=round(sum(r.sbs_rest_s for r in reports), 1),
        ops_lead_outlets=sum(r.ops_lead_outlets for r in reports),
        ops_lead_sum_s=round(sum(r.ops_lead_sum_s
                                 for r in reports), 1),
        ops_rest_outlets=sum(r.ops_rest_outlets for r in reports),
        ops_rest_sum_s=round(sum(r.ops_rest_sum_s
                                 for r in reports), 1),
        sbg_gap_s=sum(r.sbg_gap_s for r in reports),
        asr_assisted=sum(r.asr_assisted for r in reports),
        asr_long=sum(r.asr_long for r in reports),
        grc_saves=sum(r.grc_saves for r in reports),
        grc_caught=sum(r.grc_caught for r in reports),
        lao_n=sum(r.lao_n for r in reports),
        lao_died=sum(r.lao_died for r in reports),
        ahc_frames=sum(r.ahc_frames for r in reports),
        ahc_sum_up=sum(r.ahc_sum_up for r in reports),
        brc_blocks=sum(r.brc_blocks for r in reports),
        brc_recovered=sum(r.brc_recovered for r in reports),
        bcf_players=_merge_bcf_players(reports),
        psl_sevens=sum(r.psl_sevens for r in reports),
        psl_extra=sum(r.psl_extra for r in reports),
        cir_left=sum(r.cir_left for r in reports),
        cir_right=sum(r.cir_right for r in reports),
        scp_pairs=_merge_screen_pairs(reports),
        wco_shots=sum(r.wco_shots for r in reports),
        wco_sum_m=sum(r.wco_sum_m for r in reports),
        drb_players=_merge_drb_players(reports),
        hh_streaks=[st for r in reports for st in (r.hh_streaks or [])],
        gcs_cold_faced=sum(r.gcs_cold_faced for r in reports),
        gcs_cold_saves=sum(r.gcs_cold_saves for r in reports),
        gcs_warm_faced=sum(r.gcs_warm_faced for r in reports),
        gcs_warm_saves=sum(r.gcs_warm_saves for r in reports),
        avw_high_attacks=sum(r.avw_high_attacks for r in reports),
        avw_high_goals=sum(r.avw_high_goals for r in reports),
        avw_deep_attacks=sum(r.avw_deep_attacks for r in reports),
        avw_deep_goals=sum(r.avw_deep_goals for r in reports),
        bsrc_sources=_merge_role_counts(
            [r.bsrc_sources for r in reports]),
        gkg_attempts=sum(r.gkg_attempts for r in reports),
        gkg_goals=sum(r.gkg_goals for r in reports),
        lbr_breaks=sum(r.lbr_breaks for r in reports),
        lbr_for=sum(r.lbr_for for r in reports),
        lbr_against=sum(r.lbr_against for r in reports),
        cbh_frames=sum(r.cbh_frames for r in reports),
        cbh_players=_merge_cbh_players(reports),
        qp_for=_merge_role_counts([r.qp_for for r in reports]),
        qp_against=_merge_role_counts([r.qp_against for r in reports]),
        qp_min=sum(r.qp_min for r in reports),
        pvg_frames=sum(r.pvg_frames for r in reports),
        pvg_guards=_merge_pivot_guards(reports),
        tsc_timeouts=sum(r.tsc_timeouts for r in reports),
        tsc_with_subs=sum(r.tsc_with_subs for r in reports),
        sqs_trail_shots=sum(r.sqs_trail_shots for r in reports),
        sqs_trail_sum_xg=sum(r.sqs_trail_sum_xg for r in reports),
        sqs_other_shots=sum(r.sqs_other_shots for r in reports),
        sqs_other_sum_xg=sum(r.sqs_other_sum_xg for r in reports),
        gks_trail_faced=sum(r.gks_trail_faced for r in reports),
        gks_trail_saves=sum(r.gks_trail_saves for r in reports),
        gks_other_faced=sum(r.gks_other_faced for r in reports),
        gks_other_saves=sum(r.gks_other_saves for r in reports),
        wbs_trail_frames=sum(r.wbs_trail_frames for r in reports),
        wbs_trail_sum_m=sum(r.wbs_trail_sum_m for r in reports),
        wbs_other_frames=sum(r.wbs_other_frames for r in reports),
        wbs_other_sum_m=sum(r.wbs_other_sum_m for r in reports),
        ppp_returns=sum(r.ppp_returns for r in reports),
        ppp_for=sum(r.ppp_for for r in reports),
        ppp_against=sum(r.ppp_against for r in reports),
        tbr_roles=_merge_role_counts([r.tbr_roles for r in reports]),
        dbt_m=sum(r.dbt_m for r in reports),
        dbt_opp_m=sum(r.dbt_opp_m for r in reports),
        dbt_min=sum(r.dbt_min for r in reports),
        phs_players=_merge_phase_players(reports),
        spt_players=_merge_sprint_threats(reports),
        svk_sevens=sum(r.svk_sevens for r in reports),
        svk_swaps=sum(r.svk_swaps for r in reports),
        adv_players=_merge_adv_players(reports),
        rst_restarts=sum(r.rst_restarts for r in reports),
        rst_players=_merge_restart_targets(reports),
        swp_swaps=sum(r.swp_swaps for r in reports),
        swp_pairs=_merge_swap_pairs(reports),
        pb_entries=sum(r.pb_entries for r in reports),
        pb_pullbacks=sum(r.pb_pullbacks for r in reports),
        stl_steals=sum(r.stl_steals for r in reports),
        stl_fwd=sum(r.stl_fwd for r in reports),
        s7f_fh=sum(r.s7f_fh for r in reports),
        s7f_sh=sum(r.s7f_sh for r in reports),
        wf_fh_shots=sum(r.wf_fh_shots for r in reports),
        wf_fh_sum_xga=sum(r.wf_fh_sum_xga for r in reports),
        wf_sh_shots=sum(r.wf_sh_shots for r in reports),
        wf_sh_sum_xga=sum(r.wf_sh_sum_xga for r in reports),
        ben_goals=sum(r.ben_goals for r in reports),
        ben_bench=sum(r.ben_bench for r in reports),
        stt_steals=sum(r.stt_steals for r in reports),
        stt_int=sum(r.stt_int for r in reports),
        ccq_shots=sum(r.ccq_shots for r in reports),
        ccq_sum_xga=sum(r.ccq_sum_xga for r in reports),
        clo_attacks=sum(r.clo_attacks for r in reports),
        clo_goals=sum(r.clo_goals for r in reports),
        fbc_breaks=sum(r.fbc_breaks for r in reports),
        fbc_goals=sum(r.fbc_goals for r in reports),
        ho_for=sum(r.ho_for for r in reports),
        ho_against=sum(r.ho_against for r in reports),
        tfd_timeouts=sum(r.tfd_timeouts for r in reports),
        tfd_conceded=sum(r.tfd_conceded for r in reports),
        pag_after_frames=sum(r.pag_after_frames for r in reports),
        pag_after_sum_m=sum(r.pag_after_sum_m for r in reports),
        pag_base_frames=sum(r.pag_base_frames for r in reports),
        pag_base_sum_m=sum(r.pag_base_sum_m for r in reports),
        but_cases=sum(r.but_cases for r in reports),
        but_sum_s=sum(r.but_sum_s for r in reports),
        kiv_spells=sum(r.kiv_spells for r in reports),
        kiv_with=sum(r.kiv_with for r in reports),
        covered_shooters=_merge_covered_shooters(reports),
        pressure_players=_merge_pressure_players(reports),
        high_stealers=_merge_high_stealers(reports),
        wasteful_shooters=_merge_wasteful_shooters(reports),
        opening_players=_merge_clutch_players_rows(
            reports, "opening_players"),
        seven_earner_roles=_merge_earner_roles(reports),
        tfa_timeouts=sum(r.tfa_timeouts for r in reports),
        tfa_goals=sum(r.tfa_goals for r in reports),
        risky_passers=_merge_risky_passers(reports),
        screen_setters=_merge_screen_setters(reports),
        gke_early_faced=sum(r.gke_early_faced for r in reports),
        gke_early_saves=sum(r.gke_early_saves for r in reports),
        gke_rest_faced=sum(r.gke_rest_faced for r in reports),
        gke_rest_saves=sum(r.gke_rest_saves for r in reports),
        sh_shooters=_merge_pp_shooters_rows(reports, "sh_shooters"),
        clutch_losers=_merge_clutch_losers(reports),
        stg_subs=sum(r.stg_subs for r in reports),
        stg_after=sum(r.stg_after for r in reports),
        dst_cases=sum(r.dst_cases for r in reports),
        dst_sum_s=round(sum(r.dst_sum_s for r in reports), 1),
        gsh_sh_faced=sum(r.gsh_sh_faced for r in reports),
        gsh_sh_saves=sum(r.gsh_sh_saves for r in reports),
        gsh_eq_faced=sum(r.gsh_eq_faced for r in reports),
        gsh_eq_saves=sum(r.gsh_eq_saves for r in reports),
        pp_shooters=_merge_pp_shooters(reports),
        sdf_fh_shots=sum(r.sdf_fh_shots for r in reports),
        sdf_fh_sum_m=round(sum(r.sdf_fh_sum_m for r in reports), 1),
        sdf_sh_shots=sum(r.sdf_sh_shots for r in reports),
        sdf_sh_sum_m=round(sum(r.sdf_sh_sum_m for r in reports), 1),
        conceded_types=_merge_conceded_types(reports),
        breakthrough_players=_merge_breakthrough_players(reports),
        dpv_attacks=sum(r.dpv_attacks for r in reports),
        dpv_double=sum(r.dpv_double for r in reports),
        clutch_players=_merge_clutch_players(reports),
        fbs_breaks=sum(r.fbs_breaks for r in reports),
        fbs_sum_runners=round(sum(r.fbs_sum_runners for r in reports), 1),
        g7d_faced=_merge_dir_counts(reports, "g7d_faced"),
        g7d_saved=_merge_dir_counts(reports, "g7d_saved"),
        bus_left=sum(r.bus_left for r in reports),
        bus_center=sum(r.bus_center for r in reports),
        bus_right=sum(r.bus_right for r in reports),
        rebounders=_merge_rebounders(reports),
        shooter_ranges=_merge_shooter_ranges(reports),
        sh_shape=_merge_sh_shape(reports),
        ppp_pp_attacks=sum(r.ppp_pp_attacks for r in reports),
        ppp_pp_sum_s=round(sum(r.ppp_pp_sum_s for r in reports), 1),
        ppp_eq_attacks=sum(r.ppp_eq_attacks for r in reports),
        ppp_eq_sum_s=round(sum(r.ppp_eq_sum_s for r in reports), 1),
        ptp_total_s=round(sum(r.ptp_total_s for r in reports), 1),
        ptp_stopped_s=round(sum(r.ptp_stopped_s for r in reports), 1),
        ptp_own_stoppages=sum(r.ptp_own_stoppages for r in reports),
        agr_attacks=sum(r.agr_attacks for r in reports),
        agr_sevens=sum(r.agr_sevens for r in reports),
        agr_susp=sum(r.agr_susp for r in reports),
        recovery_players=_merge_recovery_players(reports),
        gsp_hard_faced=sum(r.gsp_hard_faced for r in reports),
        gsp_hard_saves=sum(r.gsp_hard_saves for r in reports),
        gsp_placed_faced=sum(r.gsp_placed_faced for r in reports),
        gsp_placed_saves=sum(r.gsp_placed_saves for r in reports),
        static_attackers=_merge_static_attackers(reports),
        wfs_left_shots=sum(r.wfs_left_shots for r in reports),
        wfs_left_goals=sum(r.wfs_left_goals for r in reports),
        wfs_right_shots=sum(r.wfs_right_shots for r in reports),
        wfs_right_goals=sum(r.wfs_right_goals for r in reports),
        pvs_left=sum(r.pvs_left for r in reports),
        pvs_center=sum(r.pvs_center for r in reports),
        pvs_right=sum(r.pvs_right for r in reports),
        dsl_frames=sum(r.dsl_frames for r in reports),
        dsl_sum_s=round(sum(r.dsl_sum_s for r in reports), 1),
        psp_passes=sum(r.psp_passes for r in reports),
        psp_sum_ms=round(sum(r.psp_sum_ms for r in reports), 1),
        psp_fast=sum(r.psp_fast for r in reports),
        pivot_feeders=_merge_pivot_feeders(reports),
        seven_conceders=_merge_seven_conceders(reports),
        adp_frames=sum(r.adp_frames for r in reports),
        adp_sum_m=round(sum(r.adp_sum_m for r in reports), 1),
        wi_attacks=sum(r.wi_attacks for r in reports),
        wi_with_wing=sum(r.wi_with_wing for r in reports),
        lhs_lead_frames=sum(r.lhs_lead_frames for r in reports),
        lhs_lead_sum_m=round(sum(r.lhs_lead_sum_m for r in reports), 1),
        lhs_trail_frames=sum(r.lhs_trail_frames for r in reports),
        lhs_trail_sum_m=round(sum(r.lhs_trail_sum_m for r in reports), 1),
        attack_outcomes=_merge_attack_outcomes(reports),
        gk_role_saves=_merge_gk_role_saves(reports),
        tc_turnovers=sum(r.tc_turnovers for r in reports),
        tc_clustered=sum(r.tc_clustered for r in reports),
        tc_clusters=sum(r.tc_clusters for r in reports),
        conceded_roles=_merge_conceded_roles(reports),
        role_goals=_merge_role_goals(reports),
        assist_zones=_merge_assist_zones(reports),
        starters=_merge_starters(reports),
        tot_timeouts=sum(r.tot_timeouts for r in reports),
        tot_sum_before=sum(r.tot_sum_before for r in reports),
        tot_late=sum(r.tot_late for r in reports),
        pair_plus_minus=_merge_pair_plus_minus(reports),
        pair_fps=(reports[0].pair_fps if reports else 25.0),
        sbl_waves=sum(r.sbl_waves for r in reports),
        sbl_players=sum(r.sbl_players for r in reports),
        sbl_block_waves=sum(r.sbl_block_waves for r in reports),
        hold_players=_merge_hold_players(reports),
        hold_fps=(reports[0].hold_fps if reports else 25.0),
        fsw_labels=_merge_fsw_labels(reports),
        fsw_attacks=sum(r.fsw_attacks for r in reports),
        fsw_pairs=sum(r.fsw_pairs for r in reports),
        fsw_switches=sum(r.fsw_switches for r in reports),
        shooter_power=_merge_shooter_power(reports),
        spw_team_shots=sum(r.spw_team_shots for r in reports),
        spw_team_sum_kmh=round(
            sum(r.spw_team_sum_kmh for r in reports), 1),
        shooter_placement=_merge_shooter_placement(reports),
        wdf_wing_shots=sum(r.wdf_wing_shots for r in reports),
        wdf_wing_goals=sum(r.wdf_wing_goals for r in reports),
        wdf_center_shots=sum(r.wdf_center_shots for r in reports),
        wdf_center_goals=sum(r.wdf_center_goals for r in reports),
        costly_turnover_players=_merge_costly_turnovers(reports),
        ppd_seconds=round(sum(r.ppd_seconds for r in reports), 1),
        ppd_conceded=sum(r.ppd_conceded for r in reports),
        ppd_eq_seconds=round(sum(r.ppd_eq_seconds for r in reports), 1),
        ppd_eq_conceded=sum(r.ppd_eq_conceded for r in reports),
        gkf_free_shots=sum(r.gkf_free_shots for r in reports),
        gkf_free_saves=sum(r.gkf_free_saves for r in reports),
        gkf_cov_shots=sum(r.gkf_cov_shots for r in reports),
        gkf_cov_saves=sum(r.gkf_cov_saves for r in reports),
        dbl_holder_frames=sum(r.dbl_holder_frames for r in reports),
        dbl_doubled_frames=sum(r.dbl_doubled_frames for r in reports),
        dbl_forced_to=sum(r.dbl_forced_to for r in reports),
        gos_left=sum(r.gos_left for r in reports),
        gos_right=sum(r.gos_right for r in reports),
        cto_early_to=sum(r.cto_early_to for r in reports),
        cto_early_s=round(sum(r.cto_early_s for r in reports), 1),
        cto_clutch_to=sum(r.cto_clutch_to for r in reports),
        cto_clutch_s=round(sum(r.cto_clutch_s for r in reports), 1),
        sha_seconds=round(sum(r.sha_seconds for r in reports), 1),
        sha_shots=sum(r.sha_shots for r in reports),
        sha_goals=sum(r.sha_goals for r in reports),
        sha_eq_seconds=round(sum(r.sha_eq_seconds for r in reports), 1),
        sha_eq_goals=sum(r.sha_eq_goals for r in reports),
        ovl_shots=sum(r.ovl_shots for r in reports),
        ovl_goals=sum(r.ovl_goals for r in reports),
        ovl_set_shots=sum(r.ovl_set_shots for r in reports),
        ovl_set_goals=sum(r.ovl_set_goals for r in reports),
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
