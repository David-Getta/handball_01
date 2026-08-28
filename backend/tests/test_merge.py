"""A meccs-összefűzés (két félidő → egy meccs) tesztjei."""
from handball.pipeline.merge import merge_matches
from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, Team,
)


def _part(match_id, n_frames, track_id):
    meta = MatchMeta(match_id=match_id, home_team="A", away_team="B", fps=8.0,
                     video_path=f"/tmp/{match_id}.mp4")
    frames = [
        Frame(t=i, players=[
            PlayerPosition(track_id=track_id, team=Team.HOME, x=1.0 * i, y=2.0),
        ], ball=Ball(x=20.0, y=10.0))
        for i in range(n_frames)
    ]
    return Match(meta=meta, frames=frames)


def test_merge_offsets_time_and_ids():
    a = _part("h1", 3, track_id=7)
    b = _part("h2", 2, track_id=7)
    m = merge_matches([a, b], "teljes")
    assert len(m.frames) == 5
    assert [f.t for f in m.frames] == [0, 1, 2, 3, 4]  # folytonos idő
    ids = {p.track_id for f in m.frames for p in f.players}
    assert len(ids) == 2  # a két "7-es" NEM mosódik össze


def test_merge_copies_do_not_alias_originals():
    a = _part("h1", 2, track_id=1)
    b = _part("h2", 2, track_id=1)
    m = merge_matches([a, b], "teljes")
    m.swap_teams()
    # az eredeti szakaszok érintetlenek
    assert a.frames[0].players[0].team == Team.HOME
    assert b.frames[0].players[0].team == Team.HOME


def test_merge_meta_and_video():
    a = _part("h1", 1, track_id=1)
    b = _part("h2", 1, track_id=1)
    m = merge_matches([a, b], "teljes", home_team="Deac", away_team="Szike")
    assert m.meta.match_id == "teljes"
    assert m.meta.home_team == "Deac" and m.meta.away_team == "Szike"
    assert m.meta.video_path is None  # nincs egyben lejátszható videó
    assert m.meta.fps == 8.0


def test_merge_same_video_keeps_playback():
    """Ha minden szakasz UGYANABBÓL a videóból jött (megszakadt feldolgozás
    folytatása), a lejátszás-hivatkozás és a kezdőkocka megmarad."""
    a = _part("resz", 3, track_id=1)
    b = _part("resz-folyt", 2, track_id=1)
    b.meta.video_path = a.meta.video_path  # ugyanaz a fájl
    b.meta.start_frame = 3
    m = merge_matches([a, b], "resz-teljes")
    assert m.meta.video_path == a.meta.video_path
    assert m.meta.start_frame == a.meta.start_frame
    assert m.meta.partial is False


def test_merge_inherits_partial_from_last_part():
    """Ha az utolsó szakasz maga is részleges (újra megszakadt), az
    összefűzött meccs is folytatható marad."""
    a = _part("resz", 3, track_id=1)
    b = _part("resz-folyt", 2, track_id=1)
    b.meta.video_path = a.meta.video_path
    b.meta.partial = True
    b.meta.next_start_frame = 5
    m = merge_matches([a, b], "resz-teljes")
    assert m.meta.partial is True
    assert m.meta.next_start_frame == 5
# ---- AKÁRHÁNY szakasz: a "két félidő" csak az egyik eset -------------


def test_hat_szakasz_is_osszefuzheto():
    """Aki telefonnal vagy fényképezőgéppel vesz fel, DARABOKBAN kapja
    a meccset: a felvétel négy gigánál vagy tíz percnél elvágódik, és
    hat-nyolc klip lesz belőle, nem kettő.

    A motor eddig is tudott N szakaszt — de ha ezt nem rögzíti teszt,
    egy kettőre szabott átalakítás némán elvihetné.
    """
    reszek = [_part(f"k{i}", 4, track_id=7) for i in range(6)]
    m = merge_matches(reszek, "teljes")
    assert len(m.frames) == 24
    # Folytonos idő végig — egy rossz eltolás minden idő-alapú réteget
    # elvinne.
    assert [f.t for f in m.frames] == list(range(24))
    # Hat KÜLÖN ember: a "7-es" az egyik klipen nem ugyanaz, mint a
    # másikon, és az összemosás hamis játékos-statisztikát adna.
    ids = {p.track_id for f in m.frames for p in f.players}
    assert len(ids) == 6


def test_a_sorrend_szamit_es_megmarad():
    """Az összefűzés IDŐRENDET vár. Ha a sorrendet elrontanánk, a
    meccs órája ugrálna, és minden idő-alapú réteg (hajrá, sorozatok,
    kondíció) mást mérne — némán, mert a frame-ek attól még
    folytonosak lennének.
    """
    a = _part("elso", 2, track_id=1)
    b = _part("masodik", 2, track_id=2)
    # A megkülönböztetés az x-ből jön: a _part x = 1.0 * i, tehát a
    # szakasz ELSŐ kockája x=0.
    elore = merge_matches([a, b], "ab")
    forditva = merge_matches([b, a], "ba")
    assert len(elore.frames) == len(forditva.frames) == 4
    # A kettő NEM ugyanaz: az összefűzés nem kommutatív, és ezt a
    # felületnek is tükröznie kell (sorszámozott, átrendezhető lista).
    elso_id = elore.frames[0].players[0].track_id
    masik_id = forditva.frames[0].players[0].track_id
    assert elso_id != masik_id


def test_egy_szakasz_nem_osszefuzes():
    """Egy szakaszt nincs mihez fűzni — a végpont is ezt kéri (>=2),
    és a felület gombja is ezért tiltott egy elemnél."""
    egy = _part("egy", 3, track_id=1)
    m = merge_matches([egy], "csak-egy")
    # A motor megengedi (érvényes másolat), de a jelentése "semmi sem
    # változott" — a KETTŐS korlát a végponton és a felületen van.
    assert len(m.frames) == 3
# ---- A KÉZI JAVÍTÁSOK túlélik az összefűzést -------------------------


def test_a_kezi_javitasok_atjonnek_es_elcsusznak_a_szakasszal():
    """Aki hat klipben kijavította a felismerés nyolc tévedését, EMBERI
    munkát végzett.

    Az összefűzés eddig NÉMÁN eldobta: az összerakott meccs megint rossz
    eredményt mutatott, és az edző nem értette, hova lettek a javításai.

    Az idő a szakasz eltolásával együtt mozog — enélkül a javítás egy
    MÁSIK esemény típusát írná át (vagy az egyeztetés-ablakon kívülre
    esve csendben elmaradna, ami még rosszabb: néma).
    """
    a = _part("h1", 10, track_id=1)
    a.meta.event_overrides = [{"op": "set_type", "t": 3, "type": "goal"}]
    b = _part("h2", 10, track_id=1)
    b.meta.event_overrides = [{"op": "add", "t": 5, "type": "goal",
                               "team": "home"}]

    m = merge_matches([a, b], "teljes")
    idok = [o["t"] for o in m.meta.event_overrides]
    assert idok == [3, 15], idok        # a második szakasz +10-zel


def test_a_javitas_lovoje_is_elcsuszik():
    """A kézzel felvett gól LÖVŐJE track-azonosító, azt pedig az
    összefűzés eltolja (a "7-es" az egyik klipen nem ugyanaz, mint a
    másikon). Eltolás nélkül a gól egy MÁSIK emberhez kerülne — és
    pont a góllövő-listán, ahol a legfeltűnőbb.
    """
    a = _part("h1", 4, track_id=1)
    b = _part("h2", 4, track_id=1)
    b.meta.event_overrides = [{"op": "add", "t": 1, "type": "goal",
                               "team": "home", "player_id": 1}]
    m = merge_matches([a, b], "teljes")
    ov = m.meta.event_overrides[0]
    # A második szakasz trackjei eltolva — a javítás lövője is.
    masodik_track_ids = {p.track_id for f in m.frames[4:] for p in f.players}
    assert ov["player_id"] in masodik_track_ids, (
        ov["player_id"], masodik_track_ids)


def test_a_rossz_alaku_javitas_nem_viszi_el_a_tobbit():
    """Egy sérült bejegyzés ne akadályozza meg a többi átvételét."""
    a = _part("h1", 4, track_id=1)
    a.meta.event_overrides = [
        {"op": "set_type", "t": "nem szám", "type": "goal"},
        {"op": "set_type", "t": 2, "type": "goal"},
        "nem is szótár",
    ]
    m = merge_matches([a, _part("h2", 4, track_id=1)], "teljes")
    assert m.meta.event_overrides == [
        {"op": "set_type", "t": 2, "type": "goal"}]


def test_javitas_nelkul_ures_marad():
    """Visszafelé kompatibilis: javítás nélküli szakaszokból javítás
    nélküli meccs lesz — nem hiba, nem kitalált bejegyzés."""
    m = merge_matches([_part("h1", 3, track_id=1),
                       _part("h2", 3, track_id=2)], "teljes")
    assert m.meta.event_overrides == []
def test_a_mezszamok_tulelik_az_osszefuzest():
    """ŐR: a kézzel kiosztott mezszám a KOCKÁKBA van beleírva (a
    mentés is úgy viszi), tehát az összefűzött másolatnak is vinnie
    kell — akkor is, ha a track-azonosítók eltolódnak.

    Ha ez elveszne, az összefűzött meccsen a játékos-lap, a
    góllövő-lista és a klip-szűrés is "számozatlan" embereket látna, és
    a felhasználó az egész mezszám-munkáját újrakezdené.
    """
    a = _part("h1", 3, track_id=7)
    b = _part("h2", 3, track_id=7)
    for f in a.frames:
        for p in f.players:
            p.jersey_number = 9
    for f in b.frames:
        for p in f.players:
            p.jersey_number = 11

    m = merge_matches([a, b], "teljes")
    mezek = sorted({p.jersey_number for f in m.frames for p in f.players})
    assert mezek == [9, 11], mezek
# ---- Térfélcsere a szakasz-határon -----------------------------------


def _terfeles_resz(match_id, n, home_x, video="/v/a.mp4",
                   fps=10.0):
    """Rész, ahol a HAZAI súlypontja home_x, a VENDÉGÉ a tükörképe."""
    from handball.pipeline.calibration import COURT_LENGTH_M

    meta = MatchMeta(match_id=match_id, home_team="Mi", away_team="Ok",
                     fps=fps, video_path=video)
    frames = []
    for i in range(n):
        frames.append(Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME,
                           x=home_x + (i % 5) * 0.1, y=8.0),
            PlayerPosition(track_id=2, team=Team.AWAY,
                           x=COURT_LENGTH_M - home_x - (i % 5) * 0.1,
                           y=12.0),
        ], ball=Ball(x=home_x, y=10.0)))
    return Match(meta, frames)


def test_a_masodik_felido_darabja_tukrozodik():
    """A DARABOK KÖZTI térfélcsere: egy videón belül a feldolgozás
    felismeri a szünetet és tükröz — a külön feldolgozott 2. félidő
    darabja viszont önmagában normalizálatlan. Tükrözés nélkül a
    lövés-felismerés a 2. félidő MINDEN gólját a rossz csapathoz írná
    (az irány-szabály az egész meccsre egy), és az összefűzött meccs
    eredménye értelmetlen lenne.
    """
    # 1. félidő: a hazai a bal térfélen (x≈10); 2. félidő: átment a
    # jobbra (x≈30) — 800 kocka / 10 fps, hogy a minta-küszöb meglegyen.
    a = _terfeles_resz("f1", 800, 10.0, video="/v/a.mp4")
    b = _terfeles_resz("f2", 800, 30.0, video="/v/b.mp4")
    m = merge_matches([a, b], "teljes")

    sz = m.meta.source_segments
    assert sz[0]["mirrored"] is False
    assert sz[1]["mirrored"] is True, sz

    # A tükrözés után a hazai VÉGIG a bal térfélen van.
    masodik = [f for f in m.frames if f.t >= sz[1]["t_from"]]
    hazai_x = [p.x for f in masodik for p in f.players
               if p.team == Team.HOME]
    assert max(hazai_x) < 15.0, (min(hazai_x), max(hazai_x))
    # A labda is tükröződött.
    assert all(f.ball.x < 15.0 for f in masodik if f.ball is not None)


def test_a_felidon_beluli_vagas_nem_tukrozodik():
    """Aki egy félidőt vett fel két darabban (a telefon elvágta), annál
    NINCS térfélcsere a határon — a tükrözés ott hiba lenne."""
    a = _terfeles_resz("g1", 800, 10.0, video="/v/a.mp4")
    b = _terfeles_resz("g2", 800, 10.0, video="/v/b.mp4")
    m = merge_matches([a, b], "teljes")
    assert m.meta.source_segments[1]["mirrored"] is False
    hazai_x = [p.x for f in m.frames for p in f.players
               if p.team == Team.HOME]
    assert max(hazai_x) < 15.0


def test_keves_mintanal_nem_tukrozunk_es_ki_van_mondva():
    """Kevés mért pozíciónál nem döntünk: a rossz irányú tükrözés
    ugyanakkora hiba, mint a kihagyott — a bejegyzés kimondja, hogy a
    döntés nem született meg (mirror_decided=False)."""
    a = _terfeles_resz("h1", 20, 10.0, video="/v/a.mp4")
    b = _terfeles_resz("h2", 20, 30.0, video="/v/b.mp4")
    m = merge_matches([a, b], "teljes")
    sz = m.meta.source_segments
    assert sz[1]["mirror_decided"] is False
    assert sz[1]["mirrored"] is False  # az állapot öröklődik (nem volt)


def test_a_gol_a_jo_csapathoz_kerul_a_tukrozes_utan():
    """A VALÓDI következmény: a 2. félidei hazai gól tükrözés nélkül a
    vendégé lenne. A lövés-felismerésen mérjük, nem a koordinátákon."""
    from handball.pipeline.calibration import COURT_LENGTH_M
    from handball.pipeline.event_detection import EventType, detect_shots

    # 1. félidő: hazai balról jobbra támad (labda a +x kapu felé fut).
    a = _terfeles_resz("i1", 800, 10.0, video="/v/a.mp4")
    for i in range(6):
        a.frames[700 + i].ball = Ball(x=34.0 + i, y=5.0, confidence=1.0)
    # 2. félidő: térfélcsere — a hazai most jobbról BALRA támad, a
    # gólja a -x kapura megy.
    b = _terfeles_resz("i2", 800, 30.0, video="/v/b.mp4")
    for i in range(6):
        b.frames[700 + i].ball = Ball(x=COURT_LENGTH_M - 34.0 - i,
                                      y=15.0, confidence=1.0)

    m = merge_matches([a, b], "teljes")
    lovesek = detect_shots(m)
    masodik_felido = [e for e in lovesek
                      if e.t >= m.meta.source_segments[1]["t_from"]]
    assert masodik_felido, "a 2. félidei lövés nem került felismerésre"
    # Tükrözés UTÁN a 2. félidei lövés is a hazaié.
    assert all(e.team == Team.HOME for e in masodik_felido), masodik_felido
