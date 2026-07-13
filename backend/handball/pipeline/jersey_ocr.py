"""
[M2] Mezszám-OCR prototípus — kísérleti számfelismerés + szavazó.

Cél: a játékosok mezszámának automatikus leolvasása, hogy a track-ek
maguktól névre (számra) szólóvá váljanak. A feladat két, jól szétváló
részre bomlik:

1. FELISMERŐ (recognizer): egy mez-kivágásból (törzs-régió) számjegyeket
   olvas. Itt egy klasszikus képfeldolgozásos ALAPVONAL van (kontraszt-
   küszöbölés + kontúr-szűrés + sablon-illesztés) — tiszta, nagy számokon
   működik, éles videón korlátozott; a végleges megoldás egy tanított
   számjegy-osztályozó lesz (a finomhangolási eszköztárral gyűjthető
   adatból). A felismerő CSERÉLHETŐ: a szavazónak csak (szám, bizonyosság)
   párok kellenek.

2. SZAVAZÓ (JerseyVoter): egy track sok képkockán látszik — az egyes
   leolvasások zajosak, de a TÖBBSÉGI szavazat megbízható. A szavazó
   trackenként gyűjti a jelölteket, és csak elég szavazat + elég előny
   esetén hirdet eredményt. A kimenete pontosan a kézi mezszám-
   hozzárendelés (/matches/{id}/jerseys) formátuma — az OCR ugyanazt a
   tárat tölti majd, amit a kézi felület javítani tud.

A modul KÍSÉRLETI: a feldolgozó lánc alapból nem használja.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JerseyVoter:
    """Trackenkénti többségi szavazás a leolvasott mezszámokra.

    - min_votes:  ennyi (súlyozott) szavazat kell egy szám kihirdetéséhez.
    - min_margin: a győztesnek ennyiszer több szavazata kell legyen, mint a
                  második helyezettnek (zajos leolvasások kiszűrése).
    """
    min_votes: float = 3.0
    min_margin: float = 2.0
    _votes: dict = field(default_factory=dict)  # track_id -> {szám: súly}

    def add(self, track_id: int, number: int, confidence: float = 1.0) -> None:
        """Egy leolvasás hozzáadása (a bizonyosság a szavazat súlya)."""
        if not (0 <= number <= 99) or confidence <= 0:
            return
        bucket = self._votes.setdefault(track_id, {})
        bucket[number] = bucket.get(number, 0.0) + confidence

    def decide(self, track_id: int) -> int | None:
        """A track kihirdetett mezszáma, vagy None, ha még bizonytalan."""
        bucket = self._votes.get(track_id)
        if not bucket:
            return None
        ranked = sorted(bucket.items(), key=lambda kv: kv[1], reverse=True)
        best_num, best_w = ranked[0]
        if best_w < self.min_votes:
            return None
        second_w = ranked[1][1] if len(ranked) > 1 else 0.0
        if second_w > 0 and best_w / second_w < self.min_margin:
            return None
        return best_num

    def decisions(self) -> dict[int, int]:
        """Minden track kihirdetett száma ({track_id: szám}) — a
        /matches/{id}/jerseys tár formátumához igazodva."""
        out = {}
        for tid in self._votes:
            n = self.decide(tid)
            if n is not None:
                out[tid] = n
        return out


def torso_crop(img, box):
    """A mezszám-régió (törzs) kivágása egy játékos-dobozból.

    A szám jellemzően a mez hátán/mellén van: a doboz felső-középső
    sávját vágjuk (fej alatt, csípő felett, oldalt karok nélkül).
    Kicsi doboznál (nem olvasható szám) None."""
    x1, y1, x2, y2 = [int(v) for v in box]
    w, h = x2 - x1, y2 - y1
    if w < 24 or h < 60:
        return None
    ty1 = y1 + int(0.12 * h)
    ty2 = y1 + int(0.50 * h)
    tx1 = x1 + int(0.15 * w)
    tx2 = x2 - int(0.15 * w)
    H, W = img.shape[:2]
    ty1, ty2 = max(0, ty1), min(H, ty2)
    tx1, tx2 = max(0, tx1), min(W, tx2)
    if ty2 - ty1 < 20 or tx2 - tx1 < 16:
        return None
    return img[ty1:ty2, tx1:tx2]


def apply_jersey_decisions(match, decisions: dict) -> int:
    """A szavazó döntéseinek ráírása a Match kockáira ({track_id: szám}).

    Csak azoknak a trackeknek ír számot, amelyeknek még NINCS (a kézi
    hozzárendelés erősebb az OCR-nél). Visszaadja, hány tracknek adott."""
    if not decisions:
        return 0
    has_manual = set()
    for fr in match.frames:
        for p in fr.players:
            if p.jersey_number is not None:
                has_manual.add(p.track_id)
    applied = set()
    for fr in match.frames:
        for p in fr.players:
            if p.track_id in decisions and p.track_id not in has_manual:
                p.jersey_number = decisions[p.track_id]
                applied.add(p.track_id)
    return len(applied)


# ---------------------------------------------------------------------------
# Számjegy-osztályozás: TANÍTOTT kis háló (digit_net.npz — lásd
# scripts/train_digit_net.py), tartalékként sablon-illesztés.
# ---------------------------------------------------------------------------

_NET_CACHE: dict = {}


def _load_digit_net():
    """A csomaggal szállított tanított számjegy-háló betöltése (egyszer).
    None, ha a fájl hiányzik/sérült — ilyenkor sablon-illesztés megy."""
    if "net" in _NET_CACHE:
        return _NET_CACHE["net"]
    net = None
    try:
        import numpy as np
        from pathlib import Path
        p = Path(__file__).parent / "digit_net.npz"
        if p.exists():
            d = np.load(str(p))
            net = (d["w1"], d["b1"], d["w2"], d["b2"])
    except Exception:
        net = None
    _NET_CACHE["net"] = net
    return net


def _classify_digit(roi28, net):
    """Egy 28x28-as (fehér jegy fekete alapon) kivágás osztályozása a
    tanított hálóval → (számjegy, valószínűség).

    A 11 kimenetű hálónál a 10-es osztály az ELUTASÍTÁS ("nem számjegy":
    betű, gyűrődés, címer) — ilyenkor (None, valószínűség) jön vissza, és
    a hívó eldobja a jelöltet. A régi, 10 kimenetű háló változatlanul
    működik (ott nincs elutasító osztály)."""
    import numpy as np
    x = roi28.astype(np.float32).reshape(1, -1) / 255.0
    h = np.maximum(0.0, x @ net[0] + net[1])
    logits = h @ net[2] + net[3]
    e = np.exp(logits - logits.max())
    p = e / e.sum()
    d = int(p.argmax())
    conf = float(p[0, d])
    if p.shape[1] >= 11 and d >= 10:
        return None, conf  # "nem számjegy" — a hamis szám rosszabb a hiányzónál
    return d, conf

def _digit_templates(size: int = 28):
    """Számjegy-sablonok 0..9 — több vastagsággal renderelve (cv2.putText).

    A sablont a számjegy BEFOGLALÓJÁRA vágjuk, majd size×size-ra nyújtjuk —
    a felismerő a jelölt-kivágást ugyanígy normálja, ezért az illesztés a
    méret- és pozíció-eltérésekre érzéketlen."""
    import cv2
    import numpy as np
    templates = {}
    for d in range(10):
        variants = []
        for thickness in (2, 3):
            img = np.zeros((64, 64), np.uint8)
            cv2.putText(img, str(d), (8, 52), cv2.FONT_HERSHEY_SIMPLEX,
                        1.8, 255, thickness)
            ys, xs = np.nonzero(img)
            tight = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            variants.append(cv2.resize(tight, (size, size),
                                       interpolation=cv2.INTER_AREA))
        templates[d] = variants
    return templates


def read_jersey_number(crop, min_confidence: float = 0.55):
    """Mezszám leolvasása egy törzs-kivágásból.

    Visszatérés: (szám, bizonyosság) vagy None. Alapvonal-módszer:
    1. szürkeárnyalat + adaptív binarizálás (a szám világos VAGY sötét
       lehet a mezhez képest — mindkét polaritást próbáljuk);
    2. kontúr-szűrés: számjegy-szerű (arány/méret) komponensek balról
       jobbra, legfeljebb kettő;
    3. minden jelöltet 28x28-ra normálva sablon-illesztés (0..9), a
       bizonyosság az illeszkedési pontszám.
    """
    import cv2
    import numpy as np

    if crop is None or crop.size == 0 or min(crop.shape[:2]) < 20:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    gray = cv2.resize(gray, (96, 96), interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    templates = _digit_templates()
    best = None
    for invert in (False, True):
        _, bw = cv2.threshold(gray, 0, 255,
                              (cv2.THRESH_BINARY_INV if invert
                               else cv2.THRESH_BINARY) + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if h < 24 or h > 88 or w < 6 or w / h > 1.2 or h / w > 6:
                continue  # nem számjegy-szerű komponens
            boxes.append((x, y, w, h))
        if not (1 <= len(boxes) <= 2):
            continue
        boxes.sort(key=lambda b: b[0])  # balról jobbra (tízes, egyes)
        net = _load_digit_net()
        digits, confs = [], []
        for (x, y, w, h) in boxes:
            roi = bw[y:y + h, x:x + w]
            roi = cv2.resize(roi, (28, 28), interpolation=cv2.INTER_AREA)
            if net is not None:
                # Tanított háló: pontosabb és torzítás-tűrőbb, mint a sablon.
                best_d, best_score = _classify_digit(roi, net)
            else:
                best_d, best_score = None, -1.0
                for d, variants in templates.items():
                    for tpl in variants:
                        score = cv2.matchTemplate(
                            roi.astype(np.float32), tpl.astype(np.float32),
                            cv2.TM_CCOEFF_NORMED)[0][0]
                        if score > best_score:
                            best_d, best_score = d, float(score)
            digits.append(best_d)
            confs.append(best_score)
        if not digits or any(d is None for d in digits):
            continue
        number = digits[0] if len(digits) == 1 else digits[0] * 10 + digits[1]
        conf = min(confs)
        if conf >= min_confidence and (best is None or conf > best[1]):
            best = (number, conf)
    return best
