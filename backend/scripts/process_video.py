"""
Valódi videó-feldolgozás — meccsvideóból Tracking JSON (YOLO + ByteTrack).

Detektáló módok:
  - YOLO (--weights yolov8n.pt): pontos; ByteTrack-kel stabil id-k. Nagy felbontású
    inferencia (imgsz) + alacsonyabb küszöb a kis/széli játékosok elkapásához.
    Bíró-szűrő (sárga mez) kiveszi a játékvezetőket.
  - HOG (alap): OpenCV beépített, letöltés nélkül; gyenge kis/gyors játékosokra.

Kalibrációval (--calib, 4 pálya-sarok):
- homográfia: kép → valós méter-koordináták, a pályán kívüliek (kispad, edző)
  szűrése (CourtRegion),
- pásztázás-követés: a kamera mozgásának kompenzálása (a kalibráció a pásztázás
  közben is érvényes marad) — a sarkokat a --start képkockához kell felvenni,
- képen kívüli becslés: a képből kilógó játékosok pótlása mozgásmodellel
  (source=ESTIMATED, halványítva a kliensben); kikapcsolás: --no-estimate.
Kalibráció nélkül egyszerű arányos kép→pálya leképezés (pontatlan, csak teszthez).

Használat:
    python -m scripts.process_video BE.mp4 KI.json [--weights yolov8n.pt]
        [--stride N] [--max N] [--imgsz 1280] [--conf 0.20] [--start N]
        [--calib calib.json] [--no-skip-dark] [--no-estimate] [--no-ball-smooth] [--no-track-smooth]
"""

from __future__ import annotations

import math
import sys

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.calibration import COURT_LENGTH_M, COURT_WIDTH_M

PROC_WIDTH = 960  # HOG feldolgozási szélesség


class StallSkippingFeed:
    """Időkorlátos kocka-adagoló: az ELAKADT képkockát átugorja.

    Terepen látott hiba: a videó-olvasás/detektálás natív szinten
    beragad EGY képkockánál, és a feldolgozás örökre megáll rajta. A
    termelőt ezért külön szál futtatja, a fogyasztó időkorlátos
    sorból olvas. Ha skip_timeout_s-ig nem érkezik új kocka, a
    beragadt termelőt elengedjük (a szála árván marad — a natív
    hívást nem lehet megszakítani), az elakadt kockát ÁTUGORJUK, és
    a resume_factory(start_frame) által adott új termelővel a
    KÖVETKEZŐ kockától folytatjuk. Legfeljebb max_skips átugrás után
    (vagy resume_factory nélkül) feladjuk: a stalled jelzővel az
    addig kész rész normál utómunkával mentődik.
    """

    _SENTINEL = object()

    # Ennyiszeresére nő az ugrás-táv minden EREDMÉNYTELEN átugrás után
    # (ha az új olvasó sem ad kockát, a hibás szakasz hosszabb egy
    # kockánál), és ennyi kockánál nem ugrunk többet egyszerre.
    _SKIP_GROWTH = 4
    _SKIP_MAX_FRAMES = 750

    def __init__(self, producer, resume_factory=None, stride=1,
                 start_pos=0, first_timeout_s=180.0,
                 skip_timeout_s=30.0, max_skips=20, on_skip=None):
        import queue
        import threading
        self._queue_mod = queue
        self._threading = threading
        self._q = queue.Queue(maxsize=8)
        self._resume_factory = resume_factory
        self._stride = max(1, int(stride))
        self._next_pos = start_pos   # a következő várt kocka kép-indexe
        self._first_timeout_s = first_timeout_s
        self._skip_timeout_s = skip_timeout_s
        self._max_skips = max_skips
        self._gen = 0
        self._on_skip = on_skip
        self._dry = 0        # egymást követő, kocka nélküli átugrások
        self.skips = 0
        self.skipped_frames = 0
        self.stalled = False
        self._start(producer)

    def _start(self, iterable):
        gen = self._gen

        def run():
            try:
                for item in iterable:
                    if not self._put(gen, item):
                        return
            except Exception as e:  # az olvasó hibája nem dönti a folyamatot
                print(f"FIGYELEM: a videó-olvasó hibával leállt: {e}")
            finally:
                try:
                    self._q.put_nowait((gen, self._SENTINEL))
                except self._queue_mod.Full:
                    pass  # a fogyasztó már kilépett — nincs kinek jelezni

        self._threading.Thread(target=run, daemon=True).start()

    def _put(self, gen, item):
        while gen == self._gen and not self.stalled:
            try:
                self._q.put((gen, item), timeout=1.0)
                return True
            except self._queue_mod.Full:
                continue
        return False

    def abandon(self):
        """A termelő elengedése (korai kilépéskor): jelzés+felébresztés."""
        self._gen += 1
        try:
            self._q.get_nowait()
        except self._queue_mod.Empty:
            pass

    def frames(self):
        """A kockák időkorlátos, elakadás-átugró folyama."""
        timeout = self._first_timeout_s
        while True:
            try:
                gen, item = self._q.get(timeout=timeout)
            except self._queue_mod.Empty:
                bad = self._next_pos
                if (self._resume_factory is None
                        or self.skips >= self._max_skips):
                    self.stalled = True
                    print(f"FIGYELEM: {int(timeout)} mp-e nem érkezik új "
                          "kocka a videó-olvasóból, és nincs több "
                          "folytatási kísérlet — a feldolgozás elakadt; "
                          "az addig kész rész feldolgozva mentődik.")
                    return
                self.skips += 1
                self._gen += 1
                # Ha az előző átugrás után sem jött kocka, a hibás
                # szakasz hosszabb egynél: nagyobbat lépünk.
                jump = min(self._SKIP_MAX_FRAMES,
                           self._stride
                           * (self._SKIP_GROWTH ** self._dry))
                self._dry += 1
                self._next_pos = bad + jump
                self.skipped_frames += jump
                msg = (f"elakadt a(z) {bad}. képkockánál — {jump} kocka "
                       "átugorva, folytatás a(z) "
                       f"{self._next_pos}. kockától "
                       f"({self.skips}/{self._max_skips} átugrás)")
                print(f"FIGYELEM: a feldolgozás {msg}.")
                if self._on_skip is not None:
                    try:
                        self._on_skip(msg)
                    except Exception:
                        pass   # a visszajelzés hibája nem állíthat meg
                try:
                    nxt = self._resume_factory(self._next_pos)
                except Exception as e:
                    self.stalled = True
                    print("FIGYELEM: a folytató videó-olvasó nem indult "
                          f"el: {e} — az addig kész rész mentődik.")
                    return
                self._start(nxt)
                timeout = self._skip_timeout_s
                continue
            if gen != self._gen:
                continue  # elavult (elengedett) termelő maradéka
            if item is self._SENTINEL:
                return
            timeout = self._skip_timeout_s
            self._dry = 0            # jött kocka: az ugrás-táv visszaáll
            self._next_pos += self._stride
            yield item


# Kockánkénti dúsítás (mezszám-OCR, labda-újrakeresés) időkorlátja és
# az egymást követő beragadások száma, ami után a dúsítót kikapcsoljuk.
ENRICH_TIMEOUT_S = 10.0
ENRICH_MAX_TIMEOUTS = 3


class TimeboxedEnricher:
    """Időkorlátos dúsító-hívás: a fő detektálást SOSEM állíthatja meg.

    A StallSkippingFeed a termelő oldalt (videó-olvasás + detektálás)
    védi — de a fogyasztó cikluson belüli natív hívások (mezszám-OCR,
    labda-újrakereső predict) is beragadhatnak, és olyankor a sor
    olvasása áll meg, tehát az átugró sem léphet működésbe: a haladás
    örökre megáll, pont a "percek óta nincs előrelépés" tünettel.

    Ezért minden dúsító hívás külön szálban, időkorláttal fut: ha
    lejár, a hívást kihagyjuk (a beragadt szál árván marad — a natív
    hívást nem lehet megszakítani), és max_timeouts beragadás után a
    dúsítót kikapcsoljuk a hátralévő kockákra. Egy-egy kihagyott
    OCR-minta vagy újrakeresés semmit nem ront az elemzésen; az örök
    állás mindent elrontana.
    """

    def __init__(self, name, timeout_s=ENRICH_TIMEOUT_S,
                 max_timeouts=ENRICH_MAX_TIMEOUTS, on_note=None):
        import threading
        self._threading = threading
        self._name = name
        self._timeout_s = timeout_s
        self._max_timeouts = max_timeouts
        self._on_note = on_note
        self._timeouts = 0
        self.disabled = False

    def call(self, fn):
        """fn() eredménye, vagy None (időtúllépés/kikapcsolt/hiba)."""
        if self.disabled:
            return None
        box = {}

        def run():
            try:
                box["out"] = fn()
            except Exception:
                box["out"] = None  # a dúsító hibája sosem állít meg

        th = self._threading.Thread(target=run, daemon=True)
        th.start()
        th.join(self._timeout_s)
        if th.is_alive():
            self._timeouts += 1
            msg = (f"a(z) {self._name} {int(self._timeout_s)} mp után sem "
                   f"tért vissza — kihagyva "
                   f"({self._timeouts}/{self._max_timeouts} beragadás)")
            print(f"FIGYELEM: {msg}.")
            if self._timeouts >= self._max_timeouts:
                self.disabled = True
                print(f"FIGYELEM: a(z) {self._name} kikapcsolva a "
                      "hátralévő kockákra — a fő feldolgozás megy tovább.")
            if self._on_note is not None:
                try:
                    self._on_note(msg)
                except Exception:
                    pass
            return None
        return box.get("out")


def _torso_bounds(x1, y1, x2, y2):
    h = y2 - y1
    return (max(0, y1 + int(0.20 * h)), max(0, y1 + int(0.55 * h)),
            x1 + int(0.25 * (x2 - x1)), x1 + int(0.75 * (x2 - x1)))


def _torso_color(frame_bgr, x1, y1, x2, y2):
    import numpy as np
    ty1, ty2, tx1, tx2 = _torso_bounds(x1, y1, x2, y2)
    crop = frame_bgr[ty1:ty2, tx1:tx2]
    if crop.size == 0:
        return (128.0, 128.0, 128.0)
    m = crop.reshape(-1, 3).mean(axis=0)
    return (float(m[2]), float(m[1]), float(m[0]))  # RGB


def _is_referee(frame_bgr, x1, y1, x2, y2):
    """Sárga mez → játékvezető (kiszűrendő)."""
    import cv2
    import numpy as np
    ty1, ty2, tx1, tx2 = _torso_bounds(x1, y1, x2, y2)
    crop = frame_bgr[ty1:ty2, tx1:tx2]
    if crop.size == 0:
        return False
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    yellow = ((hsv[:, 0] >= 20) & (hsv[:, 0] <= 40) & (hsv[:, 1] > 90) & (hsv[:, 2] > 90)).mean()
    return yellow > 0.35


def _is_dark(img, thresh=40.0):
    """Sötét bevezető/átúszó képkocka? (átlagfényesség a küszöb alatt.)
    A meccsvideók elején gyakran van fade-in — ezeken nincs mit detektálni,
    ezért kihagyjuk, hogy a --max ne fogyjon el üres képkockákra."""
    return float(img.mean()) < thresh


def _weights_ok(path):
    """Épség-ellenőrzés: a .pt fájl valójában zip — a 'PK' kezdet MELLETT a
    zip központi jegyzékét is ellenőrizzük (zipfile). Egy FÉLBESZAKADT
    letöltés ugyanis 'PK'-val kezdődik, de a vége (a jegyzék) hiányzik —
    az ilyen fájl betöltéskor érthetetlen zlib-hibát ad ("Error -3 ...
    incorrect header check"). Inkább itt szűrjük ki, és újratöltjük.
    """
    import zipfile
    try:
        with open(path, "rb") as f:
            if f.read(2) != b"PK":
                return False
        with zipfile.ZipFile(path) as z:
            z.namelist()  # csonka fájlnál (hiányzó jegyzék) itt dob
        return True
    except Exception:
        return False


def _resolve_weights(weights):
    """A súlyfájl (yolov8n.pt) tényleges elérési útja — hogy a BECSOMAGOLT
    (telepítés nélküli) kiadásban is megtalálja, ne kelljen letölteni.

    Sorrend: (1) ha a megadott út létezik ÉS ép, azt; (2) HANDBALL_WEIGHTS_DIR/
    <név>; (3) a PyInstaller csomag weights/<név> mappája (sys._MEIPASS);
    (4) az exe melletti weights/ mappa. Sérült jelöltet kihagyunk; ha egyik
    sincs, marad az eredeti név (az ultralytics letölti).
    """
    import os
    import sys
    if not weights:
        return weights
    if os.path.exists(weights) and _weights_ok(weights):
        return weights
    name = os.path.basename(weights)
    candidates = []
    env_dir = os.environ.get("HANDBALL_WEIGHTS_DIR")
    if env_dir:
        candidates.append(os.path.join(env_dir, name))
    meipass = getattr(sys, "_MEIPASS", None)  # PyInstaller kicsomagolt mappa
    if meipass:
        candidates.append(os.path.join(meipass, "weights", name))
    candidates.append(os.path.join(os.path.dirname(sys.executable), "weights", name))
    for c in candidates:
        if os.path.exists(c):
            if _weights_ok(c):
                return c
            print(f"FIGYELEM: sérült súlyfájl kihagyva: {c}")
    # Nincs ép helyi fájl → a puszta név marad, az ultralytics letölti egy
    # ÍRHATÓ helyre (a felhasználói adatmappába), nem az app csomagjába.
    try:
        from handball.storage import data_root
        dl_dir = data_root() / "weights"
        dl_dir.mkdir(parents=True, exist_ok=True)
        target = dl_dir / name
        if target.exists() and _weights_ok(str(target)):
            return str(target)
        import urllib.request
        url = ("https://github.com/ultralytics/assets/releases/latest/"
               f"download/{name}")
        print(f"súlyfájl letöltése: {url} → {target}")
        urllib.request.urlretrieve(url, str(target))
        if _weights_ok(str(target)):
            return str(target)
    except Exception as e:
        print(f"FIGYELEM: a súlyfájl letöltése nem sikerült: {e}")
    return weights


def _class_ids(names) -> tuple[list[int], list[int]]:
    """(játékos-osztályok, labda-osztályok) a modell osztálynevei alapján.

    Az előtanított COCO-modellben a person=0 és a sports ball=32; a saját,
    kézilabdára finomhangolt modellben (scripts/finetune.py) person=0 és
    ball=1. A neveket nézzük, így MINDKÉT modell külön beállítás nélkül
    működik — ismeretlen névlistánál a COCO-kiosztás a tartalék."""
    person, ball = [], []
    for k, v in (names or {}).items():
        n = str(v).strip().lower()
        if n == "person":
            person.append(int(k))
        elif "ball" in n:
            ball.append(int(k))
    return (person or [0]), (ball or [32])


def _pick_device():
    """A leggyorsabb elérhető inferencia-eszköz: CUDA (NVIDIA) → MPS (Apple
    Silicon GPU-ja, M1..M5) → CPU. Az MPS a Macen többszörös gyorsulást ad."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        mps = getattr(getattr(torch, "backends", None), "mps", None)
        if mps is not None and mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _calib_court_points(region="full", rotate=False):
    """A kalibráció 4 cél-pontja a pályán (méter), a kijelölt terület szerint.

    A képen bejelölt sarkok sorrendje: bal-fent, jobb-fent, jobb-lent, bal-lent.
    Pásztázó kameránál az induló képen sokszor csak az EGYIK TÉRFÉL látszik —
    ilyenkor a 4 pontot a térfél sarkaira (2 valódi sarok + a felezővonal két
    vége) kell húzni, és itt a térfélnek megfelelő cél-téglalapot használjuk.

    region: "full" (teljes pálya) | "left" (bal térfél) | "right" (jobb térfél)
    rotate: 180°-os forgatás — ha a kamera a túloldali lelátóról néz, és a
            pálya "fejjel lefelé" látszik a képen.
    """
    half = COURT_LENGTH_M / 2.0
    spans = {"full": (0.0, COURT_LENGTH_M), "left": (0.0, half), "right": (half, COURT_LENGTH_M)}
    x0, x1 = spans.get(region or "full", spans["full"])
    pts = [(x0, 0.0), (x1, 0.0), (x1, COURT_WIDTH_M), (x0, COURT_WIDTH_M)]
    if rotate:
        pts = pts[2:] + pts[:2]  # a sarok-hozzárendelés 180°-os forgatása
    return pts


def _normalize_max_frames(max_frames):
    """0/None/negatív képkocka-plafon → 'nincs plafon' (a teljes videó).

    Belül egy gyakorlatban elérhetetlen felső korláttal dolgozunk, így a
    feldolgozó ciklusoknak nem kell külön 'végtelen' ágat kezelniük.
    """
    if not max_frames or max_frames <= 0:
        return 10 ** 9
    return int(max_frames)


def _process_yolo(video_path, weights, stride, max_frames, imgsz, conf,
                  court_poly=None, start=0, skip_dark=True, on_frame=None,
                  pan=False, jersey_voter=None, ocr_every=5,
                  ball_recover=True, stop_check=None,
                  raw_out=None, colors_out=None, on_note=None,
                  pan_stats_out=None, anchor_frames=None):
    import os
    # Apple GPU (MPS): a ritka, nem-implementált műveletek essenek vissza CPU-ra
    # hiba helyett. A torch importja ELŐTT kell beállítani.
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    import numpy as np
    import cv2
    # Az OpenCV saját szál-poolja a PyTorch OpenMP-futásidejével ütközve
    # (különösen a becsomagolt macOS-kiadásban, ahol két OpenMP él egymás
    # mellett) ritkán BERAGADHAT egy kockán — a feldolgozás ilyenkor
    # csendben megáll egy fix pozíciónál. Az OpenCV-t egy szálra fogjuk:
    # az általunk használt műveletei (cvtColor, kivágások) olcsók, a
    # videó-dekódolást pedig az ffmpeg saját szálai viszik.
    try:
        cv2.setNumThreads(1)
    except Exception:
        pass
    from ultralytics import YOLO
    resolved = _resolve_weights(weights)
    try:
        model = YOLO(resolved)
    except Exception as first_err:
        # ÖNGYÓGYÍTÁS: ha a fájl a kezelt (letöltött) súly-mappánkban van és
        # nem tölthető be, sérültnek tekintjük — töröljük, újratöltjük, és
        # MÉG EGYSZER próbáljuk, mielőtt hibával leállnánk.
        retried = None
        try:
            from handball.storage import data_root
            managed = str(data_root() / "weights")
            if os.path.exists(resolved) and \
                    os.path.abspath(resolved).startswith(os.path.abspath(managed)):
                print(f"sérült súlyfájl törlése és újratöltése: {resolved}")
                os.remove(resolved)
                retried = _resolve_weights(weights)  # újratölti a friss fájlt
        except Exception:
            retried = None
        try:
            if retried is None:
                raise first_err
            model = YOLO(retried)
        except Exception as e:
            # Érthető hibaüzenet a felhasználónak (a nyers zlib/torch hiba
            # helyett), cselekvési javaslattal.
            raise RuntimeError(
                f"A detektáló modell nem tölthető be ({resolved}): {e} — "
                "a súlyfájl sérült lehet; internetkapcsolattal a rendszer "
                "magától letölti a jót, próbáld újra.") from e
    device = _pick_device()
    labels = {"cuda": "CUDA (NVIDIA GPU)", "mps": "MPS (Apple Silicon GPU)",
              "cpu": "CPU (lassabb — GPU-s gépen sokkal gyorsabb)"}
    print(f"inferencia-eszköz: {labels[device]}")
    poly = np.array(court_poly, np.int32) if court_poly else None
    # Pásztázás-követés: a kamera mozgását becsüljük, hogy a kalibráció a
    # pásztázás közben is érvényes maradjon (aktuális → alap képkocka mátrix).
    pan_tracker = None
    if pan:
        from handball.pipeline.pan_tracking import PanTracker
        pan_tracker = PanTracker()
    # A kalibrált kockák video-indexei növekvő sorban — ezekből lesz
    # kötelező horgony, amint a feldolgozás eléri őket.
    horgony_var = sorted(int(f) for f in (anchor_frames or []))
    # Labda-visszaszerzés: elveszett labdánál a várható helye körüli KIS
    # kivágásban keresünk újra — ott a labda relatíve nagy, jobb az esély.
    reacquirer = None
    if ball_recover:
        from handball.pipeline.ball_reacquire import BallReacquirer
        reacquirer = BallReacquirer()
    # A hívó adhat megosztott listákat (checkpoint-mentéshez): a detektálás
    # ezekbe épít, így a részeredmény menet közben is látható.
    raw = raw_out if raw_out is not None else []
    all_colors = colors_out if colors_out is not None else []
    # EGY menet nagy felbontáson (1920) + alacsony küszöb (0.05), hogy a kis labdát
    # is elkapja; a JÁTÉKOSOKAT utólag szűrjük a megadott (magasabb) küszöbre, hogy
    # ne jöjjenek téves emberek. Így egy inferencia/frame (kétszer gyorsabb).
    # A `start` a bevezető (sötét) rész átugrására: csak innen dolgozunk fel.
    # Osztály-kiosztás a modell NEVEI alapján (COCO: person=0, sports ball=32;
    # saját finomhangolt modell: person=0, ball=1) — mindkettő működik.
    person_ids, ball_ids = _class_ids(getattr(model, "names", None))
    results = model.track(source=video_path, stream=True, persist=True,
                          classes=person_ids + ball_ids, imgsz=1920, conf=0.05,
                          device=device,
                          vid_stride=stride, tracker="bytetrack.yaml", verbose=False)

    # ELAKADÁS-VÉDŐ: a kocka-generátort külön szál húzza, a feldolgozó
    # időkorlátos sorból olvas (StallSkippingFeed). Ha a videó-olvasás/
    # detektálás natív szinten beragad egy képkockánál (terepen látott
    # hiba: a haladás egy fix kockánál örökre megáll), az elakadt kockát
    # ÁTUGORJUK, és egy folytató-olvasóval a következő kockától megyünk
    # tovább — a feladás (részleges mentés) csak sok egymást követő
    # elakadásnál marad. Az első kockára türelmesebb a korlát: abban a
    # dekóder és a modell bemelegedése is benne van.
    STALL_FIRST_S = 180.0
    STALL_SKIP_S = 30.0
    STALL_MAX_SKIPS = 20

    def _resume_from(start_frame):
        """Folytató-olvasó az elakadt kocka UTÁNI pozíciótól: saját
        VideoCapture + kockánkénti track() hívás.

        SAJÁT modell-példánnyal dolgozik: az elakadt szál a natív
        hívásban ragadt bent, és ott feltehetően a KÖZÖS modellt
        fogja — ha ugyanarra a példányra hívnánk párhuzamosan, az
        összeomlást vagy újabb befagyást okozhatna. A friss példány
        ára egy modellnyi memória; cserébe a folytatás független az
        árván maradt száltól. A követési id-k emiatt újraindulnak, de
        egy elakadás után a folytonosság úgyis megszakadt.
        """
        def _iter():
            try:
                mdl = YOLO(resolved)
            except Exception as e:
                print("FIGYELEM: a folytató modell nem tölthető be "
                      f"({e}) — a közös példánnyal próbáljuk.")
                mdl = model
            from handball.video_io import open_capture
            cap = open_capture(video_path)
            try:
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                pos = start_frame
                while True:
                    if not cap.grab():
                        return
                    if (pos - start_frame) % stride == 0:
                        ok2, img = cap.retrieve()
                        if ok2 and img is not None:
                            rr = mdl.track(
                                img, persist=True,
                                classes=person_ids + ball_ids,
                                imgsz=1920, conf=0.05, device=device,
                                tracker="bytetrack.yaml",
                                verbose=False)
                            if rr:
                                yield rr[0]
                    pos += 1
            finally:
                cap.release()
        return _iter()

    feed = StallSkippingFeed(results, resume_factory=_resume_from,
                             stride=stride,
                             first_timeout_s=STALL_FIRST_S,
                             skip_timeout_s=STALL_SKIP_S,
                             max_skips=STALL_MAX_SKIPS,
                             # Az átugrás a FELÜLETRE is kimegy: enélkül a
                             # haladás-jelző (és az elakadás-őrszem
                             # szívverése) az átugrások alatt is állna, és
                             # a felhasználó azt látná, hogy semmi nem
                             # történik.
                             on_skip=on_note)

    # A dúsítók (OCR, újrakeresés) időkorlátos védelme — lásd a
    # TimeboxedEnricher docstringjét: a fogyasztó-oldali beragadás ellen
    # az átugró nem véd, ezért itt külön őr kell.
    ocr_guard = TimeboxedEnricher("mezszám-OCR", on_note=on_note)
    # Bőkezűbb korlát: az első hívásban a saját modell betöltése is
    # benne van (lassú lemezen fél perc is lehet) — az nem beragadás.
    reacq_guard = TimeboxedEnricher("labda-újrakeresés", timeout_s=45.0,
                                    on_note=on_note)
    # A labda-újrakeresés SAJÁT modell-példányt kap (lustán töltve): a
    # termelő szál a közös modellt streamelve hajtja, és az ultralytics
    # predictor nem szál-biztos — a közös példány párhuzamos hívása
    # összeomlást vagy befagyást okozhat. Ha a saját példány nem tölthető
    # be, az újrakeresés kimarad; a közös modellt SOSEM hívjuk innen.
    reacq_model_box = {}

    def _reacq_model():
        if "m" not in reacq_model_box:
            try:
                reacq_model_box["m"] = YOLO(resolved)
            except Exception as e:
                print("FIGYELEM: a labda-újrakereső modell nem tölthető "
                      f"be ({e}) — az újrakeresés kimarad.")
                reacq_model_box["m"] = None
        return reacq_model_box["m"]

    kept = 0
    skipped_dark = 0
    for fi, r in enumerate(feed.frames()):
        # Szelíd leállítás: a hívó (pl. a Megszakítás gomb) jelzésére a
        # detektálás megáll, de az ADDIG feldolgozott kockák megmaradnak —
        # az utómunka lefut rájuk, és az eredmény elmentődik.
        if stop_check is not None and stop_check():
            print(f"leállítás-kérés: a detektálás megáll ({kept} kocka kész)")
            break
        if fi * stride < start:  # a bevezető rész átugrása (kép-index alapján)
            continue
        if kept >= max_frames:
            break
        img = r.orig_img
        if skip_dark and _is_dark(img):  # sötét fade-in képkocka — kihagyjuk
            skipped_dark += 1
            continue
        kept += 1
        if on_frame is not None:  # élő haladás-jelzés a hívónak (job-státusz)
            on_frame(kept, max_frames)
        # Kameramozgás frissítése (az ALAP = az első feldolgozott képkocka; a
        # kalibrációt ehhez a képkockához kell felvenni — lásd --start).
        panH = None
        if pan_tracker is not None:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # A MOZGÓ embereket (minden detektált személy, küszöbtől
            # függetlenül) kimaszkoljuk: csak az álló háttér adja a
            # kamera mozgását.
            mozgo = []
            if r.boxes is not None:
                for b in r.boxes:
                    if int(b.cls[0]) in person_ids:
                        mozgo.append(tuple(
                            int(v) for v in b.xyxy[0].tolist()))
            # A KALIBRÁLT kockák kötelező horgonyok: a felhasználó pont
            # ezeket a nézeteket jelölte be, ide kell a legpontosabb
            # visszamérés. A kalibráció kocka-indexe nem feltétlenül esik
            # a ritkítás rácsára: az első ELÉRT feldolgozott kocka lesz az.
            kalibralt = False
            while horgony_var and fi * stride >= horgony_var[0]:
                horgony_var.pop(0)
                kalibralt = True
            panH = pan_tracker.update(gray, exclude=mozgo,
                                      force_anchor=kalibralt)
        persons, best_ball = [], None
        if r.boxes is not None:
            for b in r.boxes:
                cls = int(b.cls[0])
                bc = float(b.conf[0])
                x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
                fx = (x1 + x2) / 2.0
                if cls in person_ids:
                    if bc < conf:  # játékos-küszöb (a low-conf téves emberek kiszűrése)
                        continue
                    if poly is not None and cv2.pointPolygonTest(poly, (float(fx), float(y2)), False) < 0:
                        continue
                    if b.id is None or _is_referee(img, x1, y1, x2, y2):
                        continue
                    color = _torso_color(img, x1, y1, x2, y2)
                    all_colors.append(color)
                    tid = int(b.id[0])
                    persons.append((tid, fx, y2, color))
                    # KÍSÉRLETI mezszám-OCR: ritkított mintavétellel (minden
                    # ocr_every-edik megtartott kockán) leolvasás + szavazat.
                    if jersey_voter is not None and kept % ocr_every == 0:
                        from handball.pipeline.jersey_ocr import (
                            read_jersey_number, torso_crop)
                        crop = torso_crop(img, (x1, y1, x2, y2))
                        if crop is not None:
                            # Időkorlátos hívás: az OCR beragadása nem
                            # állíthatja meg a detektálást.
                            ocr_res = ocr_guard.call(
                                lambda c=crop: read_jersey_number(c))
                            if ocr_res is not None:
                                jersey_voter.add(
                                    tid, ocr_res[0], ocr_res[1])
                elif cls in ball_ids:  # labda — a legmegbízhatóbbat tartjuk
                    if best_ball is None or bc > best_ball[0]:
                        best_ball = (bc, (x1 + x2) / 2.0, (y1 + y2) / 2.0)
        ball_xy = (best_ball[1], best_ball[2]) if best_ball else None
        # Ha a teljes képen nem lett meg a labda, célzott újrakeresés a
        # várható helye körüli kivágásban (a kivágásban nagyobbnak látszik).
        if ball_xy is None and reacquirer is not None:
            roi = reacquirer.roi_for(fi * stride, img.shape[1], img.shape[0])
            if roi is not None:
                crop = img[roi[1]:roi[3], roi[0]:roi[2]]
                # Saját modell-példány + időkorlát: a közös modellt a
                # termelő szál hajtja, párhuzamos hívása befagyhatna;
                # az újrakeresés beragadása sem állíthatja meg a fő
                # detektálást (lásd TimeboxedEnricher).
                def _reacquire(crop=crop):
                    mdl = _reacq_model()
                    if mdl is None:
                        return None
                    rr = mdl.predict(crop, imgsz=640, conf=0.03,
                                     classes=ball_ids, device=device,
                                     verbose=False)
                    best = None
                    for r2 in rr:
                        if r2.boxes is None:
                            continue
                        for b2 in r2.boxes:
                            bc2 = float(b2.conf[0])
                            if best is None or bc2 > best[0]:
                                bx1, by1, bx2, by2 = \
                                    [float(v) for v in b2.xyxy[0].tolist()]
                                best = (bc2, (bx1 + bx2) / 2,
                                        (by1 + by2) / 2)
                    return best

                best = reacq_guard.call(_reacquire)
                if best is not None:
                    ball_xy = reacquirer.map_back(roi, best[1], best[2])
        if reacquirer is not None:
            reacquirer.note(fi * stride, ball_xy)
        raw.append((persons, ball_xy, panH))
    if skipped_dark:
        print(f"sötét bevezető képkocka kihagyva: {skipped_dark}")
    if pan_tracker is not None:
        tx, ty = pan_tracker.translation
        print(f"pásztázás-követés: össz-elmozdulás a végére: ({tx:.0f}, {ty:.0f}) px")
        print(pan_tracker.summary())
        if pan_stats_out is not None:  # a hívó a meta-ba teszi (minőség)
            pan_stats_out.update(pan_tracker.stats)
    # A termelő-szál elengedése: ha még él (korai break / plafon),
    # jelezzük, hogy nincs több fogyasztó, és felébresztjük.
    feed.abandon()
    return feed.stalled


class _SimpleTracker:
    def __init__(self, max_dist=80.0, max_gap=15):
        self.tracks = {}; self.next_id = 1; self.max_dist = max_dist; self.max_gap = max_gap

    def update(self, centers):
        assigned, used = {}, set()
        for (cx, cy) in centers:
            best, bd = None, self.max_dist
            for tid, st in self.tracks.items():
                if tid in used:
                    continue
                d = math.hypot(cx - st[0], cy - st[1])
                if d < bd:
                    bd, best = d, tid
            if best is None:
                best = self.next_id; self.next_id += 1
            self.tracks[best] = [cx, cy, 0]; used.add(best); assigned[(cx, cy)] = best
        for tid in list(self.tracks):
            if tid not in used:
                self.tracks[tid][2] += 1
                if self.tracks[tid][2] > self.max_gap:
                    del self.tracks[tid]
        return assigned


def _process_hog(video_path, stride, max_frames, stop_check=None,
                 raw_out=None, colors_out=None, on_frame=None, start=0):
    import cv2

    from handball.video_io import open_capture
    cap = open_capture(video_path)
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    scale = PROC_WIDTH / W if W > PROC_WIDTH else 1.0
    # Az OpenCV 5-ből kikerült a HOG személydetektor — nélküle a tartalék mód
    # detektálás nélkül fut (üres kockák), de nem száll el. (Az éles út a YOLO.)
    try:
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    except AttributeError:
        hog = None
    tracker = _SimpleTracker()
    if start > 0:  # folytatás/bevezető-átugrás: innen olvasunk
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(start))
    raw = raw_out if raw_out is not None else []
    all_colors = colors_out if colors_out is not None else []
    fi = out_i = 0
    while out_i < max_frames:
        if stop_check is not None and stop_check():
            break  # szelíd leállítás — az eddigi kockák megmaradnak
        ok, frame = cap.read()
        if not ok:
            break
        if fi % stride != 0:
            fi += 1; continue
        fi += 1
        small = cv2.resize(frame, None, fx=scale, fy=scale) if scale != 1.0 else frame
        if hog is not None:
            rects, weights = hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
        else:
            rects, weights = [], []
        boxes = [(int(x), int(y), int(x + w), int(y + h)) for (x, y, w, h), s in zip(rects, weights) if s >= 0.4]
        centers = [((x1 + x2) / 2.0, (y1 + y2) / 2.0) for (x1, y1, x2, y2) in boxes]
        ids = tracker.update(centers)
        persons = []
        for (x1, y1, x2, y2) in boxes:
            cx = (x1 + x2) / 2.0
            color = _torso_color(small, x1, y1, x2, y2)
            all_colors.append(color)
            persons.append((ids[(cx, (y1 + y2) / 2.0)], cx / scale, y2 / scale, color))
        raw.append((persons, None, None))  # HOG-nál nincs labda és pásztázás-mátrix
        out_i += 1
        if on_frame is not None:  # haladás-jelzés + időszakos checkpoint
            on_frame(out_i, max_frames)
    cap.release()
    return raw, all_colors


def process(video_path, out_path, weights=None, stride=3, max_frames=400, imgsz=1280,
            conf=0.20, court_poly=None, calib_corners=None, start=0, skip_dark=True,
            progress_cb=None, match_id="video-1", estimate=True,
            home_team="Csapat A", away_team="Csapat B", ball_smooth=True,
            track_smooth=True, calib_region="full", calib_rotate=False,
            calibs=None, jersey_ocr=False, stop_check=None,
            checkpoint_save=None, checkpoint_every_s=180.0,
            manual_window=False):
    """A videót Tracking-gé dolgozza fel; visszaadja a Match objektumot.

    Ha `out_path` meg van adva, a JSON-t fájlba is írja (CLI-hez). A `progress_cb`
    a feldolgozás állapotát jelzi a hívónak (a szerver ezt továbbítja a kliensnek):
    progress_cb(stage, progress, message) — stage a [A..H] lépéskód, progress 0..1.

    `stop_check` (opcionális, () -> bool): ha igazat ad, a detektálás
    SZELÍDEN leáll — az addig feldolgozott kockákra az utómunka lefut, és
    a (részleges) Match visszaadódik. Órákig tartó feldolgozásnál ez azt
    jelenti, hogy a Megszakítás nem dobja el az elvégzett munkát.

    `manual_window`: a felhasználó MEGMONDTA a meccs időablakát
    (perc:másodperc). Ilyenkor az automatikus meccs-ablak-felismerés nem
    vág tovább — az ő állítása erősebb, mint a felismerésé. Enélkül a
    kézi ablak ígérete ("felülír minden felismerést") nem lenne igaz:
    a felismerés a megadott szakasz elejéből-végéből még lecsíphetne.
    """
    import cv2
    import numpy as np

    def report(stage, prog, msg):
        if progress_cb is not None:
            progress_cb(stage, prog, msg)

    # A megnyitást a közös segéd végzi: ÉKEZETES windowsos útvonalon a
    # nyers VideoCapture némán elbukik, és akkor a fps/felbontás a
    # tartalék értékekre esne vissza — vagyis minden idő-alapú mutató
    # (sebesség, támadás-hossz, ütem) csendben elcsúszna.
    from handball.video_io import open_capture
    cap = open_capture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    print(f"videó: {W}x{H} @ {fps:.1f} fps | mód: {'YOLO' if weights else 'HOG'}")

    # max_frames = 0/None → a TELJES videó (éles meccsnél ez az alapeset).
    # A haladás-kijelzéshez a videó hosszából becsüljük a feldolgozandó
    # kockák számát (a sötét kockák kihagyása miatt ez felső becslés).
    max_frames = _normalize_max_frames(max_frames)
    est_total = max(1, max(0, n_total - start) // max(1, stride)) if n_total > 0 else 0
    disp_total = min(max_frames, est_total) if est_total else max_frames

    # [A] kalibráció (ha van 4 sarok). A haladás nagy részét a detektálás adja.
    # A kalibrációk EGYSÉGES listája: vagy a `calibs` (1-2 bejegyzés, pl.
    # külön bal és jobb térfél, akár KÜLÖN képkockán bejelölve), vagy a régi
    # egy-kalibrációs paraméterek egyetlen bejegyzésként.
    calib_list = []
    if calibs:
        calib_list = [dict(c) for c in calibs if c.get("corners")]
    elif calib_corners:
        calib_list = [{"corners": calib_corners, "region": calib_region,
                       "rotate": calib_rotate, "frame": start}]
    report("A", 0.02, "kalibráció" if calib_list else "kalibráció nélkül")

    # KÍSÉRLETI mezszám-OCR: feldolgozás közben leolvasás + szavazás; a
    # döntések a kész Match-re íródnak (a kézi hozzárendelés erősebb).
    jersey_voter = None
    if jersey_ocr:
        from handball.pipeline.jersey_ocr import JerseyVoter
        jersey_voter = JerseyVoter()

    # A detektálás KÖZBEN növekvő nyers listák — a checkpoint-mentés ezekre
    # futtatja le az utómunkát, ezért a hívó (process) birtokolja őket.
    raw: list = []
    all_colors: list = []

    def _finalize(raw, all_colors, quiet=False, partial=False):
        """A detektálás utáni TELJES utómunka: csapatszín, kalibráció,
        összefűzés, félidő, kapus, simítás, becslés → kész Match.

        A checkpoint-mentés is ezt hívja (quiet=True: napló/haladás-jelzés
        nélkül), így a részeredmény PONTOSAN ugyanazon az úton készül,
        mint a végleges — nincs külön "checkpoint-minőség".
        """
        def say(msg):
            if not quiet:
                print(msg)

        def rep(stage, prog, msg):
            if not quiet:
                report(stage, prog, msg)

        say(f"feldolgozott frame: {len(raw)}, észlelt személy: {len(all_colors)}")
        # A horgonyzás-arány a job-üzenetben is: a Feldolgozások képernyőn
        # látszik, mennyire hihetők a helyek a svenkelő kameránál.
        if pan_stats.get("frames"):
            _hp = 100.0 * pan_stats.get("anchored", 0) / pan_stats["frames"]
            rep("C", 0.78, f"követés kész — a kamera-mozgás a kockák "
                           f"{_hp:.0f}%-án a kalibrált képhez mérve")
        else:
            rep("C", 0.78, "követés kész")

        # [D] csapatszín-klaszterezés (kapus/bíró külön kezelése a szín-profilban).
        rep("D", 0.82, "csapatszín / kapus / bíró")
        centers2 = None
        if len(all_colors) >= 2:
            data = np.array(all_colors, dtype=np.float32)
            crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
            _, _, centers2 = cv2.kmeans(data, 2, None, crit, 5, cv2.KMEANS_PP_CENTERS)

        def team_of(color):
            if centers2 is None:
                return Team.HOME
            d0 = float(np.linalg.norm(np.array(color) - centers2[0]))
            d1 = float(np.linalg.norm(np.array(color) - centers2[1]))
            return Team.HOME if d0 <= d1 else Team.AWAY

        # Track-szintű TÖBBSÉGI csapat-döntés: a kockánkénti szín-döntés zajos
        # (árnyék/megvilágítás miatt egy játékos villoghatna a két csapat
        # között) — a track összes színmintája szavaz, a többség dönt.
        from handball.pipeline.teams import majority_team_by_track
        _colors_by_track: dict = {}
        for (persons_, _b_, _p_) in raw:
            for (tid_, _fx_, _fy_, color_) in persons_:
                _colors_by_track.setdefault(tid_, []).append(color_)
        team_of_track = majority_team_by_track(_colors_by_track, centers2)

        # KALIBRÁCIÓ: ha van 4 sarok (kép-pixel), homográfiával pontos pálya-koordinátára
        # váltunk, és a pályán KÍVÜL esőket (kispad/edző) eldobjuk (CourtRegion).
        to_court = None
        region = None
        if calib_list:
            from handball.pipeline._homography import (
                homography_from_points, apply_homography, invert_3x3, compose)
            from handball.pipeline.roi import CourtRegion
            region = CourtRegion(margin_m=2.0)

            # Minden kalibrációt az ALAP képkocka koordinátáira vezetünk vissza:
            # a kalibráció a saját képkockáján készült; a pásztázás-mátrix (G:
            # aktuális→alap) inverzével a H ∘ G⁻¹ már alap-pixelből ad pályametert.
            mappers = []  # (térfél x-tartománya, alapra vonatkoztatott H)
            for c in calib_list:
                pts = _calib_court_points(c.get("region", "full"), bool(c.get("rotate")))
                # Hm: a kalibráció homográfiája — szándékosan NEM `H`, hogy ne
                # árnyékolja a videó magasságát a bezáró (closure) hatókörben.
                Hm = homography_from_points([tuple(p) for p in c["corners"]], pts)
                fidx = int(c.get("frame", start))
                if raw:
                    idx = max(0, min(len(raw) - 1, round((fidx - start) / max(1, stride))))
                    panH_at = raw[idx][2]
                    if panH_at is not None and idx > 0:
                        Hm = compose(Hm, invert_3x3(panH_at))
                xs = [p[0] for p in pts]
                mappers.append((min(xs), max(xs), Hm))

            def to_court(px, py):
                # Az elsődleges kalibrációval számolunk; ha az eredmény egy MÁSIK
                # kalibráció térfelére esik, azzal pontosítunk (ott az élesebb).
                x, y = apply_homography(mappers[0][2], px, py)
                for (x0, x1, Hm) in mappers[1:]:
                    if x0 - 1.0 <= x <= x1 + 1.0:
                        try:
                            return apply_homography(Hm, px, py)
                        except ValueError:
                            return (x, y)
                return (x, y)

        def map_xy(px, py, panH=None):
            if to_court is not None:
                if panH is not None:
                    # Előbb vissza az ALAP képkocka koordinátáiba (a kamera mozgásának
                    # kompenzálása), és csak utána a pálya-homográfia.
                    from handball.pipeline.pan_tracking import apply_h
                    px, py = apply_h(panH, px, py)
                return to_court(px, py)
            return (px / W * COURT_LENGTH_M, py / H * COURT_WIDTH_M)  # kalibráció nélkül: arányos

        # [E] pálya-koordináta (homográfia/arányos) + [F] pályán kívüliek szűrése.
        rep("E", 0.90, "pálya-koordináta")
        # A meccs dátuma a videó metaadatából (mvhd creation_time, tartalék:
        # fájl-mtime) — a játékos-trend és a könyvtár időrendje erre épül.
        from handball.pipeline.video_meta import video_recording_date
        from handball.pipeline.calib_overlay import (
            sample_pan_keyframes as _sample_pan_keyframes)
        rec_date = video_recording_date(str(video_path))
        meta = MatchMeta(match_id=match_id, home_team=home_team, away_team=away_team,
                         fps=fps / stride, frame_width=W, frame_height=H,
                         # A videó-visszajátszáshoz: honnan játszható le a jelenet.
                         video_path=str(video_path), start_frame=int(start),
                         stride=int(stride), date=rec_date,
                         # Részleges eredménynél innen folytatható a feldolgozás.
                         partial=bool(partial),
                         next_start_frame=int(start) + len(raw) * int(stride),
                         # A FORRÁSVIDEÓ hossza: ebből derül ki, hogy a
                         # feldolgozás a felvétel mekkora részét fedte le.
                         video_seconds=((n_total / fps)
                                        if n_total > 0 and fps > 0 else None),
                         # Volt-e kalibráció: enélkül a koordináta arányos
                         # becslés, és a pályán kívüliek nem szűrhetők.
                         calibrated=bool(calib_list),
                         # Kalibráció-ellenőrzéshez: az elsődleges
                         # homográfia és a kamera-mozgás ritkított sora
                         # (calib_overlay) — a pályavonalak utólag
                         # bármelyik kockára visszarajzolhatók.
                         court_homography=(
                             [[float(v) for v in sor] for sor in mappers[0][2]]
                             if calib_list and mappers else None),
                         pan_keyframes=(
                             _sample_pan_keyframes([r_[2] for r_ in raw],
                                                   fps / stride)
                             if calib_list else None))
        if rec_date:
            say(f"meccs-dátum a videóból: {rec_date}")
        frames = []
        dropped = 0
        for t, (persons, ball_xy, panH) in enumerate(raw):
            players = []
            for (tid, fx, fy, color) in persons:
                cx, cy = map_xy(fx, fy, panH)
                if region is not None and not region.contains(cx, cy):
                    dropped += 1
                    continue  # pályán kívül (kispad/edző/néző)
                players.append(PlayerPosition(
                    track_id=tid,
                    # A track többségi csapata; tartalék a kockánkénti döntés.
                    team=team_of_track.get(tid, team_of(color)),
                    x=cx, y=cy, source=PositionSource.MEASURED, confidence=1.0))
            ball = None
            if ball_xy:
                bx, by = map_xy(ball_xy[0], ball_xy[1], panH)
                ball = Ball(x=bx, y=by, confidence=1.0)
            frames.append(Frame(t=t, players=players, ball=ball))
        if region is not None:
            say(f"kalibrációval: pályán kívüli detektálás eldobva: {dropped}")

        # [F] képen kívüli becslés — a pásztázó kamera képéből kilógó játékosokat
        # mozgásmodellel pótoljuk (source=ESTIMATED, csökkenő confidence), hogy a
        # felülnézeten a TELJES csapat látszódjon. Csak kalibrációval értelmes
        # (ott valós méter-koordináták vannak).
        rep("F", 0.95, "képen kívüli becslés")
        match = Match(meta=meta, frames=frames)

        # Track-összefűzés: a takarásnál megszakadt követés automatikus
        # helyreállítása (óvatos küszöbökkel) — az elemzés egy játékost lásson.
        # A track-színminták is beleszólnak: eltérő mez → nincs összefűzés.
        from handball.pipeline.track_stitch import stitch_tracks
        _stitch_rename: dict = {}
        stitched = stitch_tracks(
            match, colors_by_track=_colors_by_track,
            jerseys_by_track=(jersey_voter.decisions()
                              if jersey_voter is not None else None),
            rename_out=_stitch_rename)
        if stitched:
            say(f"track-összefűzés: {stitched} megszakadt track helyreállítva")

        # Meccs-ablak: a bemelegítés / meccs előtti rész / lefújás utáni
        # szakasz levágása — ezek nem a meccs részei (a bemelegítő kapura
        # lövés gólnak látszana, az üres percek felhígítanák az idő-alapú
        # mutatókat). A félidő-felismerés ELŐTT fut (annak a "felvétel
        # középső része" feltevését is javítja). Részleges (folytatható)
        # feldolgozásnál a VÉGÉT nem vágjuk — a folytatás oda fűz vissza.
        from handball.pipeline.game_window import trim_to_game
        _gw_info: dict = {}
        if manual_window:
            # A felhasználó megmondta, hol a meccs — az ő állítása
            # erősebb, mint a felismerésé. Vágni nem vágunk, de a
            # felismerés eredményét kiírjuk: ha ő is és a motor is
            # ugyanoda teszi a meccs kezdetét, az megerősítés.
            gw = None
            _gw_info["manual"] = True
            say("meccs-ablak: a KÉZI időablak érvényes, automatikus "
                "vágás nincs")
        else:
            gw = trim_to_game(match, tail=not partial, window_out=_gw_info)
        if gw is not None:
            say(f"meccs-ablak: eleje {gw['head_cut_s']:.0f}s, vége "
                f"{gw['tail_cut_s']:.0f}s levágva (bemelegítés / meccs "
                "előtti-utáni rész)")
        elif _gw_info.get("manual"):
            pass  # már kimondtuk fentebb
        elif _gw_info.get("found"):
            say("meccs-ablak: a felvétel eleje-vége is meccs, nincs mit "
                "levágni")
        else:
            # NEM sikerült: a bemelegítés és a ceremónia bennmaradhatott.
            # Ezt ki kell mondani — a felhasználó különben csak a kész
            # elemzésben látja a következményét ("eladott labda", miközben
            # a csapatok álltak), és nem tudja, mit tegyen ellene.
            say("meccs-ablak: NEM sikerült megtalálni a tényleges játék "
                "kezdetét — ha a felvételen bemelegítés vagy "
                "csapatbemutatás is van, add meg kézzel a meccs "
                "időablakát")
        # A felismerés eredménye a mentésbe is: enélkül a minőség-jelentés
        # nem tudná megmondani, kimaradt-e a bemelegítés.
        if not manual_window:
            match.meta.game_window_found = bool(_gw_info.get("found"))
            match.meta.game_trim_head_s = float(
                _gw_info.get("head_cut_s") or 0.0)
            match.meta.game_trim_tail_s = float(
                _gw_info.get("tail_cut_s") or 0.0)

        # Félidő-érzékelés + térfélcsere-normalizálás: teljes meccset egyben
        # tartalmazó felvételnél a 2. félidő koordinátáit tükrözi, hogy a
        # támadás-irányok egységesek legyenek. A kapus-azonosítás ELŐTT fut.
        from handball.pipeline.halftime import auto_normalize
        ht_info = auto_normalize(match)
        if ht_info is not None:
            if ht_info["swapped"]:
                say(f"félidő felismerve (frame {ht_info['halftime_t']}): "
                      f"térfélcsere normalizálva "
                      f"({ht_info['mirrored_frames']} kocka tükrözve)")
            else:
                say(f"félidő felismerve (frame {ht_info['halftime_t']}): "
                      "nincs térfélcsere-jel, a koordináták változatlanok")

        # Kapus-azonosítás pozíció-prior alapján: aki a mért idejének nagy
        # részét a kapuelőtérben tölti, role="kapus" jelölést kap. Az
        # összefűzés UTÁN fut (egyben látja a track teljes idejét).
        from handball.pipeline.goalkeeper import detect_goalkeepers
        gks = detect_goalkeepers(match)
        if gks:
            say("kapus-azonosítás: " + ", ".join(
                f"track {tid} ({share * 100:.0f}% kapuelőtér)"
                for tid, share in gks.items()))

        # KÍSÉRLETI mezszám-OCR: a szavazó döntéseinek ráírása a kockákra.
        if jersey_voter is not None:
            from handball.pipeline.jersey_ocr import apply_jersey_decisions
            # Az összefűzésnél beolvadt trackek OCR-döntéseit a megmaradó
            # azonosítóra visszük át — eddig ezek elvesztek.
            decisions = {}
            for tid, num in jersey_voter.decisions().items():
                decisions[_stitch_rename.get(tid, tid)] = num
            n_ocr = apply_jersey_decisions(match, decisions)
            if n_ocr:
                say(f"mezszám-OCR: {n_ocr} track kapott számot "
                      f"({jersey_voter.decisions()})")

        # Kispad- és néző-szűrés: a pálya-régió tűréssávjában ÜL a
        # cserepad és a nézők első sora — az egy helyben ülő, végig a
        # vonalon kívüli track nem játékos. A kilépő (mozgó) játékost nem
        # érinti.
        from handball.pipeline.track_filter import drop_bench_tracks
        bench = drop_bench_tracks(match)
        if bench["tracks"]:
            say(f"kispad-szűrés: {len(bench['tracks'])} álló, pályán "
                f"kívüli track eldobva ({bench['removed']} pozíció)")

        # Játékos-pálya simítás: a detektálási remegés (jitter) csökkentése — a
        # táv/sebesség statisztika ne a dobozok ugrálását mérje. Csak a mért
        # pozíciókat érinti, az éles irányváltást a kis ablak megőrzi.
        if track_smooth:
            from handball.pipeline.track_filter import smooth_player_tracks
            ts = smooth_player_tracks(match)
            if ts:
                say(f"játékos-simítás: {ts} pozíció simítva")

        # Labda-utómunka: a téves (kiugró) észlelések eldobása + a rövid hézagok
        # pótlása — a birtoklás/passz/lövés-felismerés folytonos labda-pályát igényel.
        if ball_smooth:
            from handball.pipeline.ball_filter import smooth_ball
            bs = smooth_ball(match)
            if bs["removed"] or bs["filled"]:
                say(f"labda-utómunka: {bs['removed']} kiugró eldobva, "
                      f"{bs['filled']} hézag-kocka pótolva")

        if estimate and calib_list:
            from handball.pipeline.estimation import augment_match_with_estimates
            added = augment_match_with_estimates(match)
            say(f"képen kívüli becslés: {added} becsült pozíció pótolva")

        # Minőség-önellenőrzés: a napló végén látszik, mennyire megbízható az eredmény.
        from handball.pipeline.quality import compute_quality_report
        q = compute_quality_report(match)
        say(f"minőség: {q['score']}/100 | játékos/kocka: {q['avg_measured_players']} | "
              f"labda-lefedettség: {q['ball_coverage_pct']}%")
        for w in q["warnings"]:
            say(f"  FIGYELEM: {w}")

        rep("H", 1.0, f"kész ({len(frames)} frame)")
        return match

    # [B]/[C] detektálás + követés — a képkockánkénti haladást ide képezzük le,
    # sebességgel és hátralévő idővel (teljes félidőnél ez órákban mérhető,
    # a felhasználónak látnia kell, mire számítson).
    import time as _time
    _t0 = _time.time()
    _cp = {"last": _time.time()}

    _last = {"kept": 0, "show": 0}

    def on_note(msg):
        """Közbeszóló üzenet a felületnek (pl. elakadt kocka átugorva).

        Enélkül az átugrások alatt a haladás-jelző ÁLLNA — a
        felhasználó azt látná, hogy semmi nem történik, holott a
        rendszer épp a hibás videó-szakaszon lépked át. A hívás egyben
        frissíti az elakadás-őrszem szívverését is.
        """
        kept = _last["kept"]
        show = _last["show"] or (disp_total or 0)
        frac = min(1.0, kept / max(1, show)) if show else 0.0
        report("B", 0.05 + 0.70 * frac,
               f"detektálás {kept}/{show} · {msg}")

    def on_frame(kept, total):
        # A kijelzéshez a becsült teljes darabszámot használjuk (a `total` a
        # belső plafon, ami teljes videónál csak egy óriási felső korlát).
        show = min(total, disp_total) if disp_total else total
        elapsed = _time.time() - _t0
        rate = kept / elapsed if elapsed > 0 else 0.0
        if rate > 0 and kept >= 3 and show > kept:  # az első pár kocka még torzít
            remain = (show - kept) / rate
            eta = f" · {rate:.1f} kocka/mp · ~{int(remain // 60)}:{int(remain % 60):02d} hátra"
        else:
            eta = ""
        frac = min(1.0, kept / max(1, show))
        _last["kept"], _last["show"] = kept, show
        report("B", 0.05 + 0.70 * frac, f"detektálás {kept}/{show}{eta}")
        # IDŐSZAKOS CHECKPOINT: pár percenként lefut az utómunka az addig
        # feldolgozott kockákra, és a részeredmény ELMENTŐDIK — a motor
        # összeomlása / áramszünet így legfeljebb pár percnyi munkát visz el.
        if (checkpoint_save is not None and kept >= 10
                and _time.time() - _cp["last"] >= checkpoint_every_s):
            _cp["last"] = _time.time()
            try:
                checkpoint_save(_finalize(raw, all_colors, quiet=True, partial=True))
                print(f"checkpoint: részeredmény mentve ({kept} kocka)")
            except Exception as e:  # a mentés hibája nem állíthatja le a futást
                print(f"FIGYELEM: részeredmény-mentés nem sikerült: {e}")

    stalled = False
    pan_stats: dict = {}
    if weights:
        # Pásztázás-követés csak kalibrációval együtt értelmes (ahhoz igazítunk).
        stalled = bool(_process_yolo(
            video_path, weights, stride, max_frames, imgsz, conf,
            court_poly, start=start, skip_dark=skip_dark,
            on_frame=on_frame, on_note=on_note, pan=bool(calib_list),
            jersey_voter=jersey_voter, stop_check=stop_check,
            raw_out=raw, colors_out=all_colors, pan_stats_out=pan_stats,
            anchor_frames={int(c.get("frame", start)) for c in calib_list}))
    else:
        _process_hog(video_path, stride, max_frames, stop_check=stop_check,
                     raw_out=raw, colors_out=all_colors, on_frame=on_frame,
                     start=start)
    stopped = bool(stop_check is not None and stop_check())
    if stalled:
        # A beragadt olvasás megszakítva — a job-üzenet is mondja el, hogy
        # az eredmény részleges, és a könyvtárból folytatható.
        report("B", 0.75,
               f"a videó-olvasás elakadt {len(raw)} kocka után — az addigi "
               "rész feldolgozva, a meccs befejezetlenként mentve "
               "(a könyvtárból folytatható)")
    match = _finalize(raw, all_colors, partial=stopped or stalled)
    # A horgonyzás-arány a meta-ba: a minőség-jelentés ebből mondja ki, ha
    # a svenkelés alatt a kalibrált képhez ritkán sikerült visszamérni.
    if pan_stats.get("frames"):
        match.meta.pan_anchor_pct = round(
            100.0 * pan_stats.get("anchored", 0) / pan_stats["frames"], 1)

    if out_path:  # CLI: fájlba is írjuk; a szerver közvetlenül a Match-et használja
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(match.to_json(indent=2))
        print(f"Tracking JSON kiírva: {out_path} ({len(match.frames)} frame)")
    return match

def main(argv):
    if len(argv) < 3:
        print("Használat: python -m scripts.process_video BE.mp4 KI.json [--weights W] "
              "[--stride N] [--max N] [--imgsz N] [--conf F] [--start N] [--no-skip-dark]")
        return 1
    def opt(name, default, cast):
        return cast(argv[argv.index(name) + 1]) if name in argv else default
    import json
    court_poly = json.load(open(argv[argv.index("--court") + 1])) if "--court" in argv else None
    # --calib: 4 kép-sarok [[x,y],...] a pálya (0,0),(40,0),(40,20),(0,20) sarkaihoz.
    calib = json.load(open(argv[argv.index("--calib") + 1])) if "--calib" in argv else None
    process(argv[1], argv[2],
            weights=opt("--weights", None, str),
            stride=opt("--stride", 3, int), max_frames=opt("--max", 400, int),
            imgsz=opt("--imgsz", 1280, int), conf=opt("--conf", 0.20, float),
            court_poly=court_poly, calib_corners=calib,
            start=opt("--start", 0, int), skip_dark="--no-skip-dark" not in argv,
            estimate="--no-estimate" not in argv,
            ball_smooth="--no-ball-smooth" not in argv,
            track_smooth="--no-track-smooth" not in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
