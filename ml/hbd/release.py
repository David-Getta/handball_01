"""Tanított lövés-profil: elengedés pillanata, kartartás, lövőkéz — kézi jelölésből.

A `goalkeeper` kézi küszöbei (a "leggyorsabb csukló" kockája) rosszul
találták meg az elengedést, ezért a kartartást is elrontották (a lövések
felét "lent"-nek mondták, a jelölés szerint 337-ből 2 az). Itt ugyanezt a
gép tanulja meg a lövésjelölő oldalon készült kézi jelölésekből:

  1. ELENGEDÉS: kis időbeli konvolúciós háló kockánként pontoz, a legjobb
     kocka az elengedés (tanítás: a jelölt kocka körüli puha célfüggvény).
  2. KARTARTÁS (fent / oldalt) és LÖVŐKÉZ (jobb / bal): logisztikus
     regresszió a testtartás-jellemzőkön az elengedés körüli ablakban.

Kiértékelés: jelenet szerint csoportosított keresztvalidáció, "végponttól
végpontig" — a teszt-részen a kartartást a MODELL által talált elengedésnél
mérjük, nem a kézi jelölésnél (úgy, ahogy élesben futna). Viszonyítás: a
régi szabály és a "mindig a leggyakoribb" tipp.

    python -m hbd.release --poses poses.npz --labels cimkek.csv --out results_release/
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from .features import (L_EL, L_SH, L_WR, NOSE, R_EL, R_SH, R_WR, normalize)
from .goalkeeper import shot_profile
from .pose import load_dataset

# Az elengedés körüli ablak a kartartás-jellemzőkhöz — IDŐTARTAM, ezért
# másodpercben (a jelenetek 30 és 48 fps-esek).
ARM_WINDOW_S = 0.08
# A puha célfüggvény szélessége (másodperc): a jelölés ±1-2 kockás
# bizonytalanságát nem büntetjük teljes hibaként.
TARGET_SIGMA_S = 0.03
# Kartartás-osztályok: a "lent" a jelölésben 337-ből 2 — ennyiből nem
# tanulható, az "oldalt"-hoz soroljuk (mindkettő: a kar a fej vonala alatt).
ARM_CLASSES = ("fent", "oldalt")
HAND_CLASSES = ("jobb", "bal")
FOLDS = 5


# ---------------------------------------------------------------- jelölések
def load_labels(path: str | Path) -> dict[str, dict]:
    """A jelölések CSV-ből (klip → sor); a "rossz" klipek kimaradnak."""
    out = {}
    with open(path) as fh:
        for r in csv.DictReader(fh):
            if r["rossz"].lower() in ("true", "1"):
                continue
            out[r["klip"]] = {"elengedes": int(r["elengedes"]), "kartartas": r["kartartas"],
                              "lovokez": r["lovokez"], "kategoria": r["kategoria"]}
    return out


# --------------------------------------------------------------- jellemzők
def frame_features(kps: np.ndarray, boxes: np.ndarray, fps: float) -> np.ndarray:
    """Kockánkénti bemenet az elengedés-hálónak: (T, F) float32.

    Testpontok a csípőhöz és törzshosszhoz normálva, a csuklók sebessége
    (egység / s) és magassága a vállhoz, plusz a test elmozdulása.
    """
    fps = fps or 30.0
    rel, motion, conf, _ = normalize(kps, boxes)
    T = len(kps)
    vel = np.zeros((T, 17, 2))
    if T > 1:
        vel[1:] = np.diff(rel, axis=0) * fps
    wr_speed = np.linalg.norm(vel[:, [L_WR, R_WR]], axis=-1) / 10.0
    wr_h = np.stack([rel[:, L_WR, 1] - rel[:, L_SH, 1], rel[:, R_WR, 1] - rel[:, R_SH, 1]], 1)
    mvel = np.zeros((T, 2))
    if T > 1:
        mvel[1:] = np.diff(motion, axis=0) * fps / 10.0
    return np.concatenate([rel.reshape(T, -1), vel.reshape(T, -1) / 10.0, wr_speed, wr_h,
                           motion, mvel, conf], 1).astype(np.float32)


def arm_hand_features(kps: np.ndarray, boxes: np.ndarray, fps: float, r: int) -> np.ndarray:
    """Testtartás az elengedés (r) körüli ablakban → jellemző-vektor."""
    fps = fps or 30.0
    rel, _, _, _ = normalize(kps, boxes)
    T = len(kps)
    w = max(1, int(round(ARM_WINDOW_S * fps)))
    a, b = max(0, r - w), min(T, r + w + 1)
    seg = rel[a:b]
    # a törzs "fel" iránya (csípő-közép → váll-közép); a kar szöge ehhez mérve:
    # fent ≈ 0–40°, oldalt ≈ 60–110° (a "sidearm" dobás lényege a szög, nem a magasság)
    up = (seg[:, L_SH] + seg[:, R_SH]) / 2
    up = up / (np.linalg.norm(up, axis=1, keepdims=True) + 1e-9)

    def ang(v):
        v = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
        return np.degrees(np.arccos(np.clip((v * up).sum(1), -1, 1)))

    f = []
    for wr, sh, el in ((L_WR, L_SH, L_EL), (R_WR, R_SH, R_EL)):
        h = seg[:, wr, 1] - seg[:, sh, 1]
        head = seg[:, wr, 1] - seg[:, NOSE, 1]
        side = np.abs(seg[:, wr, 0] - seg[:, sh, 0])
        elb = seg[:, el, 1] - seg[:, sh, 1]
        a_arm = ang(seg[:, wr] - seg[:, sh])
        a_upper = ang(seg[:, el] - seg[:, sh])
        f += [h.max(), h.mean(), head.max(), side.mean(), elb.max(),
              a_arm.min(), a_arm.mean(), a_upper.min(), a_upper.mean()]
    # a teljes klipen a csuklók legnagyobb magassága és sebessége (a lövőkéz
    # a lendítés során magasabbra és gyorsabban mozog)
    hl = rel[:, L_WR, 1] - rel[:, L_SH, 1]
    hr = rel[:, R_WR, 1] - rel[:, R_SH, 1]
    vl = np.linalg.norm(np.diff(rel[:, L_WR], axis=0), axis=1) * fps if T > 1 else np.zeros(1)
    vr = np.linalg.norm(np.diff(rel[:, R_WR], axis=0), axis=1) * fps if T > 1 else np.zeros(1)
    f += [hl.max() - hr.max(), np.percentile(vl, 90) - np.percentile(vr, 90),
          np.abs(seg[:, L_SH, 0] - seg[:, R_SH, 0]).mean()]
    return np.nan_to_num(np.array(f, np.float64))


# ------------------------------------------------------------ elengedés-háló
def _torch():
    import torch

    return torch


class ReleaseNet:
    """Kockánként pontozó időbeli konvolúciós háló; predict → elengedés kockája."""

    def __init__(self, epochs: int = 120, lr: float = 2e-3, seed: int = 0, width: int = 64):
        self.epochs, self.lr, self.seed, self.width = epochs, lr, seed, width
        self.model = None
        self.mu = self.sd = None
        torch = _torch()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def _build(self, f_in: int):
        torch = _torch()
        nn = torch.nn
        w = self.width
        return nn.Sequential(
            nn.Conv1d(f_in, w, 5, padding=2), nn.ReLU(),
            nn.Conv1d(w, w, 5, padding=4, dilation=2), nn.ReLU(),
            nn.Conv1d(w, w, 5, padding=8, dilation=4), nn.ReLU(),
            nn.Dropout(0.2), nn.Conv1d(w, 1, 1),
        ).to(self.device)

    def _batch(self, X: list[np.ndarray]):
        torch = _torch()
        T = max(len(x) for x in X)
        xb = np.zeros((len(X), T, X[0].shape[1]), np.float32)
        mask = np.zeros((len(X), T), bool)
        for i, x in enumerate(X):
            xb[i, :len(x)] = (x - self.mu) / self.sd
            mask[i, :len(x)] = True
        return (torch.tensor(xb, device=self.device).transpose(1, 2),
                torch.tensor(mask, device=self.device))

    def fit(self, X: list[np.ndarray], y: list[int], fps: list[float]):
        torch = _torch()
        torch.manual_seed(self.seed)
        rng = np.random.default_rng(self.seed)
        allx = np.concatenate(X)
        self.mu, self.sd = allx.mean(0), allx.std(0) + 1e-6
        self.model = self._build(allx.shape[1])
        opt = torch.optim.AdamW(self.model.parameters(), lr=self.lr, weight_decay=1e-3)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, self.epochs)
        self.model.train()
        for _ in range(self.epochs):
            for idx in np.array_split(rng.permutation(len(X)), max(1, len(X) // 16)):
                xb, mask = self._batch([X[i] for i in idx])
                logits = self.model(xb).squeeze(1).masked_fill(~mask, -1e9)
                tgt = np.zeros(mask.shape, np.float32)
                t = np.arange(mask.shape[1])
                for j, i in enumerate(idx):
                    sig = max(0.5, TARGET_SIGMA_S * fps[i])
                    g = np.exp(-0.5 * ((t - y[i]) / sig) ** 2) * mask[j].cpu().numpy()
                    tgt[j] = g / g.sum()
                tgt_t = torch.tensor(tgt, device=self.device)
                loss = -(tgt_t * torch.log_softmax(logits, 1)).sum(1).mean()
                opt.zero_grad()
                loss.backward()
                opt.step()
            sched.step()
        return self

    def predict(self, X: list[np.ndarray]) -> np.ndarray:
        torch = _torch()
        self.model.eval()
        out = []
        with torch.no_grad():
            for x in X:
                xb, mask = self._batch([x])
                out.append(int(self.model(xb).squeeze(1)[0, :len(x)].argmax()))
        return np.array(out)

    def save(self, path) -> None:
        torch = _torch()
        torch.save({"state": self.model.state_dict(), "mu": self.mu, "sd": self.sd,
                    "width": self.width}, path)


# ---------------------------------------------------------------- kiértékelés
def _clf():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(StandardScaler(),
                         LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5))


def evaluate(clips: list[dict], labels: dict[str, dict], seed: int = 0, epochs: int = 120) -> dict:
    from sklearn.metrics import balanced_accuracy_score
    from sklearn.model_selection import StratifiedGroupKFold

    data = [c for c in clips if c["name"] in labels and len(c["kps"]) >= 8]
    y_rel = np.array([min(labels[c["name"]]["elengedes"], len(c["kps"]) - 1) for c in data])
    y_arm = np.array([int(labels[c["name"]]["kartartas"] != "fent") for c in data])
    y_hand = np.array([int(labels[c["name"]]["lovokez"] == "bal") for c in data])
    fps = np.array([c["fps"] for c in data])
    groups = np.array([c["scene_id"] for c in data])
    F = [frame_features(c["kps"], c["boxes"], c["fps"]) for c in data]

    pred_rel = np.zeros(len(data), int)
    pred_arm = np.zeros(len(data), int)
    pred_hand = np.zeros(len(data), int)
    oracle_arm = np.zeros(len(data), int)
    strat = y_arm * 2 + y_hand
    for tr, te in StratifiedGroupKFold(FOLDS, shuffle=True, random_state=seed).split(
            np.zeros(len(data)), strat, groups):
        net = ReleaseNet(epochs=epochs, seed=seed).fit([F[i] for i in tr], y_rel[tr], fps[tr])
        pred_rel[te] = net.predict([F[i] for i in te])
        Xtr = np.stack([arm_hand_features(data[i]["kps"], data[i]["boxes"], fps[i], y_rel[i]) for i in tr])
        Xte_pred = np.stack([arm_hand_features(data[i]["kps"], data[i]["boxes"], fps[i], pred_rel[i]) for i in te])
        Xte_orc = np.stack([arm_hand_features(data[i]["kps"], data[i]["boxes"], fps[i], y_rel[i]) for i in te])
        arm = _clf().fit(Xtr, y_arm[tr])
        hand = _clf().fit(Xtr, y_hand[tr])
        pred_arm[te] = arm.predict(Xte_pred)
        oracle_arm[te] = arm.predict(Xte_orc)
        pred_hand[te] = hand.predict(Xte_pred)

    # a régi kézi szabály ugyanezeken a klipeken
    rule_rel, rule_arm, rule_hand = [], [], []
    for c in data:
        p = shot_profile(c["kps"], c["boxes"], c["fps"])
        rule_rel.append(p["elengedes_kocka"] if p else len(c["kps"]) // 2)
        rule_arm.append(int(not p or p["kartartas"] != "fent"))
        rule_hand.append(int(bool(p) and p["lovokez"] == "bal"))
    rule_rel, rule_arm, rule_hand = map(np.array, (rule_rel, rule_arm, rule_hand))

    def rel_stats(pred):
        err_f = np.abs(pred - y_rel)
        err_ms = err_f / fps * 1000
        return {"atlag_hiba_kocka": float(err_f.mean()), "median_hiba_ms": float(np.median(err_ms)),
                "pontos_2_kockan_belul": float((err_f <= 2).mean()),
                "pontos_100ms_belul": float((err_ms <= 100).mean())}

    def cls_stats(pred, y):
        return {"pontossag": float((pred == y).mean()),
                "kiegyensulyozott": float(balanced_accuracy_score(y, pred))}

    return {
        "klipek": len(data),
        "osztalyok": {"kartartas": {"fent": int((y_arm == 0).sum()), "oldalt/lent": int(y_arm.sum())},
                      "lovokez": {"jobb": int((y_hand == 0).sum()), "bal": int(y_hand.sum())}},
        "elengedes": {"modell": rel_stats(pred_rel), "regi_szabaly": rel_stats(rule_rel)},
        "kartartas": {"modell": cls_stats(pred_arm, y_arm),
                      "modell_kezi_elengedesnel": cls_stats(oracle_arm, y_arm),
                      "regi_szabaly": cls_stats(rule_arm, y_arm),
                      "mindig_fent": cls_stats(np.zeros_like(y_arm), y_arm)},
        "lovokez": {"modell": cls_stats(pred_hand, y_hand),
                    "regi_szabaly": cls_stats(rule_hand, y_hand),
                    "mindig_jobb": cls_stats(np.zeros_like(y_hand), y_hand)},
    }


def fit_final(clips, labels, out: Path, seed: int = 0, epochs: int = 120) -> list[str]:
    import joblib

    data = [c for c in clips if c["name"] in labels and len(c["kps"]) >= 8]
    y_rel = np.array([min(labels[c["name"]]["elengedes"], len(c["kps"]) - 1) for c in data])
    fps = np.array([c["fps"] for c in data])
    F = [frame_features(c["kps"], c["boxes"], c["fps"]) for c in data]
    ReleaseNet(epochs=epochs, seed=seed).fit(F, y_rel, fps).save(out / "release_net.pt")
    X = np.stack([arm_hand_features(c["kps"], c["boxes"], c["fps"], r) for c, r in zip(data, y_rel)])
    y_arm = np.array([int(labels[c["name"]]["kartartas"] != "fent") for c in data])
    y_hand = np.array([int(labels[c["name"]]["lovokez"] == "bal") for c in data])
    joblib.dump({"model": _clf().fit(X, y_arm), "classes": ARM_CLASSES}, out / "arm_clf.joblib")
    joblib.dump({"model": _clf().fit(X, y_hand), "classes": HAND_CLASSES}, out / "hand_clf.joblib")
    return ["release_net.pt", "arm_clf.joblib", "hand_clf.joblib"]


def write_report(res: dict, out: Path) -> Path:
    e, k, h = res["elengedes"], res["kartartas"], res["lovokez"]
    pct = lambda v: f"{100 * v:.1f}%"  # noqa: E731
    md = [
        "# Tanított lövés-profil (kézi jelölésből)", "",
        f"Klipek: {res['klipek']} (a „rossz” klipek nélkül); 5-szörös, jelenet szerint "
        "csoportosított keresztvalidáció. A kartartást és a lövőkezet a MODELL által talált "
        "elengedésnél mérjük, ahogy élesben futna.", "",
        f"Osztályok: kartartás {res['osztalyok']['kartartas']}, lövőkéz {res['osztalyok']['lovokez']}.", "",
        "## Elengedés pillanata", "",
        "| | átlagos hiba (kocka) | medián hiba | ±2 kockán belül | 100 ms-on belül |",
        "|---|---|---|---|---|",
    ]
    for name, key in (("tanított modell", "modell"), ("régi szabály", "regi_szabaly")):
        s = e[key]
        md.append(f"| {name} | {s['atlag_hiba_kocka']:.1f} | {s['median_hiba_ms']:.0f} ms | "
                  f"{pct(s['pontos_2_kockan_belul'])} | {pct(s['pontos_100ms_belul'])} |")
    md += ["", "## Kartartás (fent / oldalt)", "", "| | pontosság | kiegyensúlyozott |", "|---|---|---|"]
    for name, key in (("tanított modell", "modell"), ("modell a kézi elengedésnél", "modell_kezi_elengedesnel"),
                      ("régi szabály", "regi_szabaly"), ("mindig „fent”", "mindig_fent")):
        md.append(f"| {name} | {pct(k[key]['pontossag'])} | {pct(k[key]['kiegyensulyozott'])} |")
    md += ["", "## Lövőkéz (jobb / bal)", "", "| | pontosság | kiegyensúlyozott |", "|---|---|---|"]
    for name, key in (("tanított modell", "modell"), ("régi szabály", "regi_szabaly"),
                      ("mindig „jobb”", "mindig_jobb")):
        md.append(f"| {name} | {pct(h[key]['pontossag'])} | {pct(h[key]['kiegyensulyozott'])} |")
    p = out / "release_results.md"
    p.write_text("\n".join(md) + "\n")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Tanított lövés-profil a kézi jelölésből")
    ap.add_argument("--poses", required=True)
    ap.add_argument("--labels", required=True, help="a lövésjelölő CSV-je")
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    clips = load_dataset(args.poses)["clips"]
    labels = load_labels(args.labels)
    res = evaluate(clips, labels, args.seed, args.epochs)
    res["mentett_modellek"] = fit_final(clips, labels, out, args.seed, args.epochs)
    (out / "release_results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(write_report(res, out).read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
