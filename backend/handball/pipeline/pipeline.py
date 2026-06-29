"""
Pipeline-összefogó — a [A]–[H] lépéseket EGYBEN futtatja egy videón.

Ez a modul köti össze a többit: bemenet egy meccsvideó (+ kalibráció + esemény-
idővonal), kimenet a kész `Match` (Tracking) objektum, amit a backend JSON-ban ad
a Flutter-kliensnek.

A folyamat egy frame-re:
  [B] detektálás -> [C] követés(+ReID+OCR) -> [D] csapatba sorolás ->
  [E] pálya-koordináta -> [F] képen kívüli becslés
és a végén [H] statisztika a teljes Match-en.

Ebben a vázban a videó-beolvasás és a modellek placeholderek, de a VEZÉRLÉS
(milyen sorrendben, mit kap a következő lépés) már a végleges. Így a valódi
modellek lépésről lépésre behelyettesíthetők anélkül, hogy a szerkezet változna.
"""

from __future__ import annotations

from ..models.tracking import Match, MatchMeta, Frame, Team
from ..models.events import RosterTimeline
from .calibration import Calibrator, CourtCalibration
from .detection import Detector, DetectionClass
from .tracking_step import Tracker
from .teams import TeamClassifier
from .court_coords import player_to_court, ball_to_court
from .estimation import OffScreenEstimator
from .stats import compute_player_stats
from .roi import CourtRegion, ExclusionZones


class HandballPipeline:
    """A teljes feldolgozó pipeline egy meccsvideóra.

    Használat:
        pipe = HandballPipeline()
        match = pipe.run(video_path, meta, roster, reference_calib)
        json_text = match.to_json(indent=2)
    """

    def __init__(self):
        # A pipeline lépéseinek példányai. (A valódi modelleket ezek töltik be.)
        self.calibrator = Calibrator()
        self.detector = Detector()
        self.tracker = Tracker()
        self.team_classifier = TeamClassifier()

    def run(self, video_path: str, meta: MatchMeta,
            roster: RosterTimeline | None = None,
            reference_calib: CourtCalibration | None = None,
            court_region: CourtRegion | None = None,
            exclusions: ExclusionZones | None = None) -> Match:
        """Lefuttatja a teljes pipeline-t és visszaadja a kész Match-et.

        Paraméterek:
        - video_path:      a feldolgozandó meccsvideó útvonala.
        - meta:            a meccs fejléc-adatai (csapatnevek, fps, felbontás).
        - roster:          a létszám-/esemény-idővonal (kiállítások stb.). Ha None,
                           üres idővonalat használunk (mindig teljes létszám).
        - reference_calib: a kézi referencia-kalibráció. Ha None, üres kalibráció
                           (a koordináták egyelőre pixelben maradnak).
        - court_region:    a JÁTÉKTÉR (méterben). Az ezen kívülre vetülő
                           detektálásokat eldobjuk (lelátó, kispad, nézők). Ha None,
                           az alapértelmezett 40x20 m + tűréssáv.
        - exclusions:      KIZÁRÁSI ZÓNÁK (kép-pixelben), pl. a pálya fölé belógó
                           kosárpalánk. Az ezekbe eső detektálásokat figyelmen kívül
                           hagyjuk. Ha None, nincs kizárt zóna.

        Megjegyzés: ebben a vázban a videó-frame-ek beolvasása és a modellek még
        placeholderek, ezért a kimenet jelenleg ÜRES frame-listával tér vissza.
        A `scripts/run_pipeline.py` egy szintetikus Match-csel demonstrálja a
        kész adatszerződést (a valódi feldolgozás ide épül majd be).
        """
        roster = roster or RosterTimeline()
        reference_calib = reference_calib or CourtCalibration()
        court_region = court_region or CourtRegion()
        exclusions = exclusions or ExclusionZones()
        estimator = OffScreenEstimator(roster)

        match = Match(meta=meta, frames=[])

        # --- Frame-enkénti feldolgozás váza -----------------------------------
        # TODO: valódi videó-beolvasás (pl. OpenCV VideoCapture) és iterálás.
        for t, frame_img in self._iter_frames(video_path):
            # [A] az adott frame kalibrációja (a pásztázás követésével)
            calib = self.calibrator.homography_for_frame(frame_img, reference_calib)

            # [B] detektálás: játékosok + labda
            detections = self.detector.detect(frame_img)
            player_dets = [d for d in detections if d.cls == DetectionClass.PLAYER]
            ball_dets = [d for d in detections if d.cls == DetectionClass.BALL]

            # Szűrés 1. — KIZÁRÁSI ZÓNÁK (kép-térben): a fix belógó dolgokba (pl.
            # kosárpalánk) eső detektálásokat eldobjuk, mintha ott sem lennének.
            player_dets = [d for d in player_dets
                           if not exclusions.contains(*d.foot_point())]
            ball_dets = [d for d in ball_dets
                         if not exclusions.contains(*d.foot_point())]

            # [C] követés + ReID + mezszám-OCR → stabil id-k
            tracks = self.tracker.update(player_dets, frame_img)

            # [D] csapatba sorolás + [E] pálya-koordináta
            measured = []
            for tr in tracks:
                # Bírókat (sárga, nem-játékos) kiszűrjük — lásd FOOTAGE_NOTES.md.
                if self.team_classifier.is_referee(tr):
                    continue
                team = self.team_classifier.classify(tr)
                pos = player_to_court(tr, team, calib)
                # Szűrés 2. — PÁLYA-RÉGIÓ (méter-térben): a játéktéren kívülre
                # vetülő játékosokat (lelátó, kispad, nézők) eldobjuk.
                if court_region.contains(pos.x, pos.y):
                    measured.append(pos)

            # [F] képen kívüli játékosok becslése (kiegészíti a mértet)
            estimator.update_seen(t, measured)
            estimated = estimator.estimate_missing(t, measured)

            # labda (ha detektáltuk)
            ball = ball_to_court(ball_dets[0], calib) if ball_dets else None

            match.frames.append(Frame(t=t, players=measured + estimated, ball=ball))

        return match

    def _iter_frames(self, video_path: str):
        """Végigmegy a videó képkockáin: (t, frame_kép) párokat ad.

        TODO: valódi videó-beolvasás (OpenCV). Most placeholder: üres iterátor,
        ezért a `run` üres frame-listát ad — a szerkezet viszont kész.
        """
        return iter(())  # TODO: cv2.VideoCapture(video_path) alapú iterálás


# Kényelmi függvény: a statisztikát külön lehet kérni a kész Match-ből.
def summarize(match: Match):
    """A kész Match-ből játékosonkénti statisztikát számol ([H])."""
    return compute_player_stats(match)
