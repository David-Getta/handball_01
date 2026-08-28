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
