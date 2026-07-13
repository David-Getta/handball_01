"""
Számjegy-felismerő tanítása SZINTETIKUS adatból — a mezszám-OCR agya.

Miért szintetikus: a mezszám-számjegyek zárt világ (0–9, nagy, kontrasztos
nyomtatott jegyek) — ez jól közelíthető renderelt jegyekkel: több betűtípus,
vastagság, elforgatás, eltolás, elmosás, zaj, vékonyítás/hízlalás. Így
VALÓDI címkézett adat nélkül is tanítható egy kis háló, ami a
sablon-illesztésnél lényegesen strapabíróbb.

A háló szándékosan pici (28x28 → 128 → 10, ~100k paraméter), numpy-val
tanítjuk és numpy-val is fut (jersey_ocr) — se torch, se új függőség a
kiadásban. A kész súly a handball/pipeline/digit_net.npz fájlba kerül
(a csomag része), a pontosság a metaadatban.

Használat:
    python -m scripts.train_digit_net [--epochs 12] [--samples 3000]
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np


def render_digit(digit: int, rng: np.random.Generator) -> np.ndarray:
    """Egy 28x28-as, [0,1] szürke számjegy-kép véletlen torzításokkal —
    ugyanaz a normalizálás (szoros vágás + átméretezés), mint élesben."""
    import cv2
    fonts = [cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX,
             cv2.FONT_HERSHEY_TRIPLEX, cv2.FONT_HERSHEY_PLAIN,
             cv2.FONT_HERSHEY_COMPLEX]
    font = fonts[rng.integers(len(fonts))]
    thickness = int(rng.integers(2, 6))
    scale = float(rng.uniform(1.4, 2.4))
    img = np.zeros((72, 72), np.uint8)
    cv2.putText(img, str(digit), (14, 58), font, scale, 255, thickness)

    # Elforgatás (a kamera és a test dőlése): ±14 fok.
    angle = float(rng.uniform(-14, 14))
    M = cv2.getRotationMatrix2D((36, 36), angle, 1.0)
    img = cv2.warpAffine(img, M, (72, 72))

    # Vastagság-ingadozás: erózió/dilatáció.
    k = int(rng.integers(0, 3))
    if k:
        kernel = np.ones((k, k), np.uint8)
        img = cv2.dilate(img, kernel) if rng.random() < 0.5 else \
            cv2.erode(img, kernel)

    # Szoros vágás a jegy befoglalójára — mint a felismerőben.
    ys, xs = np.nonzero(img)
    if len(ys) == 0:
        return render_digit(digit, rng)  # az erózió kiürítette — újra
    img = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    img = cv2.resize(img, (28, 28), interpolation=cv2.INTER_AREA)

    # Elmosás (mozgás/defókusz) + zaj + kontraszt-ingadozás.
    if rng.random() < 0.6:
        sigma = float(rng.uniform(0.4, 1.4))
        img = cv2.GaussianBlur(img, (3, 3), sigma)
    x = img.astype(np.float32) / 255.0
    x *= float(rng.uniform(0.7, 1.0))
    x += rng.normal(0, rng.uniform(0.01, 0.08), x.shape).astype(np.float32)
    return np.clip(x, 0.0, 1.0)


def make_dataset(per_digit: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for d in range(10):
        for _ in range(per_digit):
            xs.append(render_digit(d, rng).reshape(-1))
            ys.append(d)
    x = np.stack(xs).astype(np.float32)
    y = np.array(ys, np.int64)
    idx = rng.permutation(len(y))
    return x[idx], y[idx]


def train(epochs: int, per_digit: int, seed: int = 7):
    """Kis MLP (784→128→10) tanítása numpy-val (SGD + momentum)."""
    rng = np.random.default_rng(seed)
    x_train, y_train = make_dataset(per_digit, seed)
    x_val, y_val = make_dataset(max(200, per_digit // 5), seed + 1)

    n_in, n_hid, n_out = 784, 128, 10
    w1 = rng.normal(0, np.sqrt(2.0 / n_in), (n_in, n_hid)).astype(np.float32)
    b1 = np.zeros(n_hid, np.float32)
    w2 = rng.normal(0, np.sqrt(2.0 / n_hid), (n_hid, n_out)).astype(np.float32)
    b2 = np.zeros(n_out, np.float32)
    vw1 = np.zeros_like(w1); vb1 = np.zeros_like(b1)
    vw2 = np.zeros_like(w2); vb2 = np.zeros_like(b2)

    def forward(x):
        h = np.maximum(0, x @ w1 + b1)  # ReLU
        return h, h @ w2 + b2

    def accuracy(x, y):
        _, logits = forward(x)
        return float((logits.argmax(1) == y).mean())

    lr, momentum, batch = 0.08, 0.9, 128
    n = len(y_train)
    for epoch in range(epochs):
        order = rng.permutation(n)
        for i in range(0, n, batch):
            idx = order[i:i + batch]
            xb, yb = x_train[idx], y_train[idx]
            h, logits = forward(xb)
            # Softmax + kereszt-entrópia gradiens.
            e = np.exp(logits - logits.max(1, keepdims=True))
            p = e / e.sum(1, keepdims=True)
            p[np.arange(len(yb)), yb] -= 1.0
            p /= len(yb)
            gw2 = h.T @ p; gb2 = p.sum(0)
            gh = p @ w2.T
            gh[h <= 0] = 0.0
            gw1 = xb.T @ gh; gb1 = gh.sum(0)
            for (wv, gv, vv) in ((w1, gw1, vw1), (b1, gb1, vb1),
                                 (w2, gw2, vw2), (b2, gb2, vb2)):
                vv *= momentum
                vv -= lr * gv
                wv += vv
        acc = accuracy(x_val, y_val)
        print(f"epoch {epoch + 1}/{epochs} · val pontosság: {acc * 100:.2f}%")
    return (w1, b1, w2, b2), accuracy(x_val, y_val)


def main() -> int:
    ap = argparse.ArgumentParser(description="Számjegy-háló tanítása (numpy)")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--samples", type=int, default=3000,
                    help="minta számjegyenként (alap: 3000)")
    args = ap.parse_args()

    t0 = time.time()
    (w1, b1, w2, b2), acc = train(args.epochs, args.samples)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "handball", "pipeline", "digit_net.npz")
    np.savez_compressed(out, w1=w1, b1=b1, w2=w2, b2=b2,
                        val_accuracy=np.float32(acc),
                        trained_at=np.bytes_(time.strftime("%Y-%m-%d")))
    size_kb = os.path.getsize(out) / 1024
    print(f"\nkész: {out} ({size_kb:.0f} KB) · val pontosság: "
          f"{acc * 100:.2f}% · {time.time() - t0:.0f} mp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
