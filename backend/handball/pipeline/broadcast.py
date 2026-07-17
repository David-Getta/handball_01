"""TV-közvetítés elő-feldolgozása — vágás-felismerés és totálkép-szűrő.

A saját (pásztázó) kamerás felvétellel szemben a tévés közvetítés NEM egy
folyamatos kép: totál → közeli → visszajátszás → totál, gyakran másod-
percenként vágva. Ha ezt nyersen az elemzőbe engednénk:

- a közeli képeken nincs értelmezhető pálya-geometria (a kalibráció
  értelmetlen), és
- a visszajátszás DUPLÁN számolná ugyanazt a gólt.

Ez a modul a közvetítést előbb VÁGÁSOKKAL szakaszokra bontja (a képkockák
színhisztogramjának ugrásaiból), majd minden szakaszt totálkép / közeli
címkével lát el — csak a totálkép-szakaszok mennek tovább a valódi
elemzőbe. Ez a tévés-út első lépcsője; valódi közvetítés-felvétel nélkül
is építhető és tesztelhető, mert a mag tiszta számítás.

A `color_histogram` és a `content_spread` cv2-t használ (a képkockákból
számol jellemzőket); a többi függvény tiszta numpy/Python, videó nélkül
tesztelhető.
"""

from __future__ import annotations

from typing import Optional

# Vágás-küszöb: a szomszédos képkockák hisztogram-távolsága e fölött vágás.
CUT_THRESHOLD = 0.45
# Ennél közelebbi két vágást összevonunk (egy villódzó átúszás nem 5 vágás).
MIN_SHOT_FRAMES = 6
# Totálkép-küszöb: a képkocka-jellemzők átlagos "szórtsága" e fölött totál.
WIDE_SPREAD_MIN = 0.42
# Ennél rövidebb totál-szakasz sem elég stabil az elemzéshez (mp).
MIN_WIDE_SEGMENT_S = 3.0


def color_histogram(frame_bgr, bins: int = 8):
    """Egy képkocka normált szín-hisztogramja (bins³ hosszú vektor).

    A vágás-detektálás alapja: két egymást követő kocka hisztogramja
    hasonló egy folyamatos jeleneten belül, és HIRTELEN ugrik vágáskor."""
    import cv2
    import numpy as np

    hist = cv2.calcHist([frame_bgr], [0, 1, 2], None, [bins] * 3,
                        [0, 256] * 3)
    hist = hist.astype("float64")
    total = hist.sum()
    if total > 0:
        hist /= total
    return hist.ravel()


def hist_distance(a, b) -> float:
    """Két hisztogram távolsága (0..1) — fél-L1 (teljes variáció).

    Normált hisztogramokra a fél-L1 távolság pont [0,1] közé esik: 0 =
    azonos eloszlás, 1 = teljesen diszjunkt (biztos vágás)."""
    import numpy as np

    a = np.asarray(a, dtype="float64")
    b = np.asarray(b, dtype="float64")
    return float(np.abs(a - b).sum() / 2.0)


def detect_cuts(hists, threshold: float = CUT_THRESHOLD,
                min_gap: int = MIN_SHOT_FRAMES) -> list[int]:
    """Vágás-képkockák indexei a hisztogram-sorozatból.

    Egy i index vágás, ha a hists[i-1]→hists[i] távolság a küszöb fölött
    van; két vágás közt legalább min_gap kockányi hézagot tartunk (a
    rövid átúszásokat nem daraboljuk fel)."""
    cuts: list[int] = []
    last = -min_gap
    for i in range(1, len(hists)):
        if hist_distance(hists[i - 1], hists[i]) >= threshold:
            if i - last >= min_gap:
                cuts.append(i)
                last = i
    return cuts


def segment_stream(cuts, n_frames: int) -> list[tuple[int, int]]:
    """A vágás-indexekből [kezdő, záró] szakaszok (a képkocka-indexen).

    A szakaszok lefedik a teljes [0, n_frames) tartományt; a vágás a
    KÖVETKEZŐ szakasz első kockája."""
    if n_frames <= 0:
        return []
    bounds = [0] + [c for c in cuts if 0 < c < n_frames] + [n_frames]
    return [(bounds[i], bounds[i + 1] - 1) for i in range(len(bounds) - 1)
            if bounds[i + 1] - 1 >= bounds[i]]


def content_spread(frame_bgr) -> float:
    """A képkocka tartalmának térbeli SZÓRTSÁGA (0..1).

    Totálkép: az él-energia (pályavonalak, sok kis játékos) a KÉP EGÉSZÉN
    szétterül → nagy szórtság. Közeli: az energia egy nagy alakra
    koncentrálódik → kicsi szórtság. Az él-térkép súlypont körüli szórását
    a kép átlójára normáljuk."""
    import cv2
    import numpy as np

    g = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Laplacian(g, cv2.CV_64F)
    e = np.abs(edges)
    h, w = e.shape
    total = e.sum()
    if total <= 0:
        return 0.0
    ys, xs = np.mgrid[0:h, 0:w]
    cx = (e * xs).sum() / total
    cy = (e * ys).sum() / total
    var = (e * ((xs - cx) ** 2 + (ys - cy) ** 2)).sum() / total
    std = float(np.sqrt(var))
    diag = float(np.hypot(w, h))
    # Egyenletesen szétterülő energiánál a szórás a fél-átló ~0,4-szerese;
    # erre normálunk, hogy a totál ~0,45+ legyen, a közeli jóval alatta.
    return min(1.0, std / (0.41 * diag))


def classify_segments(segments, spread_scores,
                      wide_min: float = WIDE_SPREAD_MIN):
    """Minden szakaszhoz totál/közeli címke a kockánkénti szórtságból.

    spread_scores: kockánkénti content_spread érték. Egy szakasz "totál",
    ha a szakaszbeli kockák ÁTLAGOS szórtsága a küszöb fölött van.
    Visszatérés: [{"start","end","kind","spread"}] — kind: "totál"|"közeli"."""
    out = []
    for (a, b) in segments:
        vals = [spread_scores[i] for i in range(a, b + 1)
                if 0 <= i < len(spread_scores)]
        mean = sum(vals) / len(vals) if vals else 0.0
        out.append({"start": a, "end": b,
                    "kind": "totál" if mean >= wide_min else "közeli",
                    "spread": round(mean, 3)})
    return out


def usable_segments(classified, fps: float,
                    min_wide_s: float = MIN_WIDE_SEGMENT_S) -> list[dict]:
    """A HASZNÁLHATÓ (elég hosszú totálkép) szakaszok — ezekből elemzünk.

    A rövid totál-villanások (a vágás-detektor zaja) kiesnek. Ezekre a
    képkocka-tartományokra futtatható a valódi kalibráció + követés."""
    min_frames = max(1, round(min_wide_s * (fps if fps > 0 else 25.0)))
    return [s for s in classified
            if s["kind"] == "totál" and s["end"] - s["start"] + 1 >= min_frames]


def analyze_broadcast(video_path: str, stride: int = 5,
                      max_frames: int = 0) -> dict:
    """Egy közvetítés-felvétel elő-elemzése: vágások + szakasz-címkék.

    A `stride`-dal ritkított kockákból számol (a vágás-detektáláshoz a
    ritkított minta is elég, és sokszor gyorsabb). Visszatérés:
    {"fps", "n_frames", "stride", "cuts", "segments" (címkézve),
     "usable" (a totál-szakaszok), "looks_like_broadcast" (sok vágás?)}.
    A képkocka-indexek a RITKÍTOTT sorozatra vonatkoznak; az eredeti
    videó indexe: index * stride."""
    import cv2

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    hists = []
    spreads = []
    fi = kept = 0
    while True:
        if max_frames and kept >= max_frames:
            break
        ok, frame = cap.read()
        if not ok:
            break
        if fi % max(1, stride) == 0:
            small = cv2.resize(frame, (160, 90))
            hists.append(color_histogram(small))
            spreads.append(content_spread(small))
            kept += 1
        fi += 1
    cap.release()

    n = len(hists)
    cuts = detect_cuts(hists)
    segments = segment_stream(cuts, n)
    classified = classify_segments(segments, spreads)
    eff_fps = (fps / max(1, stride)) if fps > 0 else 25.0
    usable = usable_segments(classified, eff_fps)
    # Sok vágás rövid idő alatt = tévés közvetítés (a saját kamera nem vág).
    looks_broadcast = n > 0 and (len(cuts) / max(1, n)) > 0.01
    return {"fps": fps, "n_frames": n, "stride": stride,
            "cuts": cuts, "segments": classified, "usable": usable,
            "looks_like_broadcast": bool(looks_broadcast)}
