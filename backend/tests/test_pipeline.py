"""
Tesztek a pipeline-összefogóra (pipeline.py): HandballPipeline.run + summarize.

A videó-beolvasás és a modellek a vázban placeholderek, a VEZÉRLÉS viszont
végleges: detektálás → kizárási zóna → követés → bíró-szűrés → csapat →
pálya-koordináta → pálya-régió → képen kívüli becslés → labda. Itt hamis
detektorral és követővel (kép nélkül) azt nézzük, hogy minden lépés azt
kapja és azt adja tovább, amit kell.

Futtatás:
    python -m pytest tests/test_pipeline.py -q
"""

from __future__ import annotations

from handball.models.tracking import Match, MatchMeta, PositionSource, Team
from handball.pipeline.appearance import AppearanceProfile
from handball.pipeline.calibration import CourtCalibration
from handball.pipeline.detection import Detection, DetectionClass
from handball.pipeline.pipeline import HandballPipeline, summarize
from handball.pipeline.roi import CourtRegion, ExclusionZones
from handball.pipeline.stats import compute_player_stats
from handball.pipeline.teams import TeamClassifier
from handball.pipeline.tracking_step import Track

FEHER, FEKETE, SARGA = (240, 240, 240), (20, 20, 20), (230, 210, 40)


def _meta(fps=25.0):
    return MatchMeta(match_id="p", home_team="H", away_team="A", fps=fps)


def _jatekos(x, y, conf=0.9):
    """Játékos-doboz, amelynek TALAJ-PONTJA (alsó él közepe) épp (x, y)."""
    return Detection(DetectionClass.PLAYER, x - 0.5, y - 2.0, x + 0.5, y, conf)


def _labda(x, y, conf=0.8):
    return Detection(DetectionClass.BALL, x - 0.1, y - 0.2, x + 0.1, y, conf)


class _HamisDetektor:
    """A "kép" itt egy szótár: {"jatekosok": [(id, szín, mez, doboz)],
    "labda": doboz vagy None} — a detektor a dobozokat adja vissza."""

    def detect(self, frame):
        dets = [d for (_, _, _, d) in frame["jatekosok"]]
        if frame.get("labda") is not None:
            dets.append(frame["labda"])
        return dets


class _HamisKoveto:
    """A kapott (már szűrt) játékos-dobozokhoz a kép szerinti id-t, színt
    és mezszámot rendeli; feljegyzi, mit kapott."""

    def __init__(self):
        self.kapott = []

    def update(self, detections, frame=None):
        self.kapott.append(list(detections))
        out = []
        for (tid, szin, mez, doboz) in frame["jatekosok"]:
            if any(d is doboz for d in detections):
                out.append(Track(track_id=tid, detection=doboz,
                                 jersey_number=mez, dominant_color=szin))
        return out


class _ProbaPipeline(HandballPipeline):
    """A váz a megadott "képeken" megy végig (videó helyett)."""

    def __init__(self, kepek):
        super().__init__()
        self.kepek = kepek
        self.detector = _HamisDetektor()
        self.tracker = _HamisKoveto()
        self.team_classifier = TeamClassifier(AppearanceProfile(
            home=FEHER, away=FEKETE, referee=[SARGA]))

    def _iter_frames(self, video_path):
        return iter(self.kepek)


def test_run_placeholder_videoval_ures_meccset_ad():
    """Valódi videó-beolvasás nélkül a váz végigfut: a fejléc megmarad, a
    kocka-lista üres (nem kivétel, nem None) — és a statisztika is üres."""
    meta = _meta()
    match = HandballPipeline().run("nincs_ilyen.mp4", meta)
    assert isinstance(match, Match)
    assert match.meta is meta
    assert match.frames == []
    assert summarize(match) == {}


def test_run_csapat_koordinata_es_labda_a_helyen():
    """Egy kocka: a fehér mez hazai, a fekete vendég; a talaj-pont (még
    kalibráció nélkül változatlanul) lesz a pozíció, MÉRT forrással, a
    detektor megbízhatóságával és a mezszámmal; a labda is átjön."""
    kep = {"jatekosok": [(1, FEHER, 9, _jatekos(12.0, 8.0, conf=0.7)),
                         (2, FEKETE, None, _jatekos(30.0, 11.0))],
           "labda": _labda(13.0, 8.5)}
    match = _ProbaPipeline([(0, kep)]).run("v.mp4", _meta())
    assert len(match.frames) == 1
    f = match.frames[0]
    assert f.t == 0
    mert = {p.track_id: p for p in f.players
            if p.source == PositionSource.MEASURED}
    assert set(mert) == {1, 2}
    assert mert[1].team == Team.HOME and mert[2].team == Team.AWAY
    assert (mert[1].x, mert[1].y) == (12.0, 8.0)
    assert (mert[2].x, mert[2].y) == (30.0, 11.0)
    assert mert[1].confidence == 0.7 and mert[1].jersey_number == 9
    assert mert[2].jersey_number is None
    assert (f.ball.x, f.ball.y, f.ball.confidence) == (13.0, 8.5, 0.8)


def test_run_a_referencia_kalibracioval_meterre_valt():
    """Kalibrációval a talaj-pont PIXELBŐL méterre vált (itt 1 m = 50 px),
    a játékosé és a labdáé is — a pálya-régió szűrése már méterben megy."""
    h = [[0.02, 0.0, 0.0], [0.0, 0.02, 0.0], [0.0, 0.0, 1.0]]
    kep = {"jatekosok": [(1, FEHER, None, _jatekos(600.0, 400.0)),
                         # 2500 px = 50 m → a pályán (és a tűréssávon) kívül
                         (2, FEKETE, None, _jatekos(2500.0, 400.0))],
           "labda": _labda(1000.0, 500.0)}
    match = _ProbaPipeline([(0, kep)]).run(
        "v.mp4", _meta(), reference_calib=CourtCalibration(homography=h))
    f = match.frames[0]
    mert = [p for p in f.players if p.source == PositionSource.MEASURED]
    assert [p.track_id for p in mert] == [1]
    assert abs(mert[0].x - 12.0) < 1e-9 and abs(mert[0].y - 8.0) < 1e-9
    assert abs(f.ball.x - 20.0) < 1e-9 and abs(f.ball.y - 10.0) < 1e-9


def test_run_kiszuri_a_birot_a_kizart_zonat_es_a_palyan_kivulit():
    """A bíró (sárga) nem játékos; a kizárási zónába (pl. belógó palánk)
    eső dobozt a követő meg sem kapja; a játéktéren kívülre vetülő
    (lelátó) alak kimarad; a zónába eső labda nem labda."""
    palank = ExclusionZones(polygons=[[(18.0, 0.0), (22.0, 0.0),
                                       (22.0, 4.0), (18.0, 4.0)]])
    biro = _jatekos(20.0, 10.0)
    palankos = _jatekos(20.0, 2.0)
    kep = {"jatekosok": [(1, FEHER, None, _jatekos(12.0, 8.0)),
                         (50, SARGA, None, biro),
                         (60, FEKETE, None, palankos),
                         (70, FEKETE, None, _jatekos(30.0, 27.0))],
           "labda": _labda(20.0, 3.0)}
    pipe = _ProbaPipeline([(0, kep)])
    match = pipe.run("v.mp4", _meta(), exclusions=palank)
    f = match.frames[0]
    assert [p.track_id for p in f.players
            if p.source == PositionSource.MEASURED] == [1]
    assert f.ball is None
    # A követő a zónán kívüli három dobozt kapta — a bíró ott még benne
    # van (őt a csapatba sorolás szűri ki), a palánkos nincs.
    assert len(pipe.tracker.kapott[0]) == 3
    assert any(d is biro for d in pipe.tracker.kapott[0])
    assert not any(d is palankos for d in pipe.tracker.kapott[0])


def test_run_sajat_palya_regioval_szukebb_a_jatekter():
    """A pálya-régió tűréssávja állítható: 0 m-es sávval a vonalon
    1 m-rel kívül álló játékos már kimarad, az alap 2 m-essel bent van."""
    kep = {"jatekosok": [(1, FEHER, None, _jatekos(12.0, 21.0))],
           "labda": None}
    alap = _ProbaPipeline([(0, kep)]).run("v.mp4", _meta())
    assert [p.track_id for p in alap.frames[0].players] == [1]
    szuk = _ProbaPipeline([(0, kep)]).run(
        "v.mp4", _meta(), court_region=CourtRegion(margin_m=0.0))
    assert szuk.frames[0].players == []
    assert szuk.frames[0].ball is None


def test_run_a_kepbol_kilepo_jatekost_becsli():
    """Aki az első kockán látszott, a másodikon nem, az BECSÜLT
    pozícióval a kockán marad (a mért lista mögött) — a becslő a mért
    pozíciókból tanul, kockáról kockára."""
    elso = {"jatekosok": [(1, FEHER, 9, _jatekos(12.0, 8.0)),
                          (2, FEKETE, None, _jatekos(30.0, 11.0))],
            "labda": _labda(13.0, 8.5)}
    masodik = {"jatekosok": [(1, FEHER, 9, _jatekos(12.5, 8.0))],
               "labda": None}
    match = _ProbaPipeline([(0, elso), (1, masodik)]).run("v.mp4", _meta())
    assert [f.t for f in match.frames] == [0, 1]
    f1 = match.frames[1]
    forras = {p.track_id: p.source for p in f1.players}
    assert forras == {1: PositionSource.MEASURED,
                      2: PositionSource.ESTIMATED}
    assert [p.track_id for p in f1.players] == [1, 2]      # mért elöl
    becsult = f1.players[1]
    assert becsult.team == Team.AWAY
    assert (becsult.x, becsult.y) == (30.0, 11.0)
    assert 0.0 < becsult.confidence < 1.0
    assert f1.ball is None


def test_summarize_a_kesz_meccs_jatekos_statisztikaja():
    """A summarize a [H] lépés: ugyanazt adja, mint a
    compute_player_stats — a mért kockákból távot, a becsültből csak
    darabszámot."""
    kepek = []
    for t in range(5):                         # az 1-es 0,5 m-t lép kockánként
        jatekosok = [(1, FEHER, None, _jatekos(10.0 + 0.5 * t, 8.0))]
        if t < 2:                              # a 2-es két kocka után kilép
            jatekosok.append((2, FEKETE, None, _jatekos(30.0, 11.0)))
        kepek.append((t, {"jatekosok": jatekosok, "labda": None}))
    match = _ProbaPipeline(kepek).run("v.mp4", _meta())
    stat = summarize(match)
    assert stat == compute_player_stats(match)
    assert set(stat) == {1, 2}
    assert stat[1].measured_frames == 5 and stat[1].estimated_frames == 0
    assert abs(stat[1].distance_m - 2.0) < 1e-9
    assert stat[2].measured_frames == 2 and stat[2].estimated_frames == 3
    assert stat[2].distance_m == 0.0           # a becslés nem fut távot


def test_summarize_ures_meccsen_ures():
    """Kocka nélküli meccsen nincs kiről statisztikát adni: üres szótár."""
    assert summarize(Match(_meta(), [])) == {}
