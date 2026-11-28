"""Lövésfelismerés MECCSEK KÖZÖTT: az egyiken tanít, a másikon mér — és mennyit ad a második meccs?

Három tanítási mód, mindig ugyanazon a teszt-meccsen (élő lövések):
  - "csak a másik meccs": a teszt-meccs egyetlen kockája sincs a tanításban (= vak átvitel);
  - "csak ez a meccs": időblokkos keresztvalidáció a teszt-meccsen (BLOCKS blokk, a határ ±5 s kimarad);
  - "a másik meccs + ez a meccs": a blokkos CV, de a másik meccs egésze is mindig a tanításban.

A jellemző-készletek: "póz + kamera" (az eredményjelző-jelek nélkül — a 2. meccsen ez vitte át
a tudást) és "csak póz". Kiértékelés: a küszöb-görbe legjobb F1-e és a 80%-os felidézéshez
tartozó pontosság / téves riasztás (utólag választott küszöb — a módok összevetésére jó, nem
egy rögzített működési pontra).

    python tools/meccsek_kozt.py --m1 m1_pose.npz m1_broadcast.npz m1_court.npz cimkek/meccs1_esemenyek.json \
        --m2 m2_pose.npz m2_broadcast.npz m2_court_v2.npz cimkek/meccs2_esemenyek.json --out eredmeny.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hbd.broadcast import load as load_bc  # noqa: E402
from hbd.court import filter_pose  # noqa: E402
from hbd.match_pose import load as load_pose  # noqa: E402
from hbd.shot_detect import (BLOCKS, at_recall, build_features, labels, match_events,  # noqa: E402
                             pick_peaks, shot_times, smooth)

SCOREBOARD = ("allas_valtozas", "eredmenyjelzo_latszik")
CONFIGS = {"póz + kamera": True, "csak póz": False}


def load_match(pose_p, bc_p, court_p, events_p, use_bc: bool) -> dict:
    pose = filter_pose(load_pose(pose_p), np.load(court_p)["on_court"])
    bc = load_bc(bc_p) if use_bc else None
    _, _, X, xn = build_features(pose, bc, True)
    keep = [i for i, n in enumerate(xn) if not n.startswith(SCOREBOARD)]
    doc = json.loads(Path(events_p).read_text())
    shots = shot_times(doc.get("data", doc), include_replays=False)
    t = pose["t"]
    return {"t": t, "X": X[:, keep], "names": [xn[i] for i in keep], "y": labels(t, shots),
            "st": np.array([s["t"] for s in shots])}


def _clf(seed=0):
    from sklearn.ensemble import HistGradientBoostingClassifier

    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                          l2_regularization=1.0, class_weight="balanced", random_state=seed)


def curve_of(t, score, st):
    minutes = (t.max() - t.min()) / 60
    out = []
    for thr in np.round(np.arange(0.05, 0.96, 0.05), 2):
        tp, fp, _ = match_events(pick_peaks(t, score, thr), st)
        p, r = tp / max(1, tp + fp), tp / max(1, len(st))
        out.append({"kuszob": float(thr), "felidezes": r, "pontossag": p, "teves_per_perc": fp / minutes,
                    "f1": 2 * p * r / max(1e-9, p + r)})
    return out


def scores(test: dict, other: dict | None, own_blocks: bool) -> np.ndarray:
    t, X, y = test["t"], test["X"], test["y"]
    if not own_blocks:
        clf = _clf().fit(other["X"][other["y"] >= 0], other["y"][other["y"] >= 0])
        return smooth(clf.predict_proba(X)[:, 1], 3)
    edges = np.linspace(t.min(), t.max() + 1e-6, BLOCKS + 1)
    s = np.zeros(len(t))
    for b in range(BLOCKS):
        te = (t >= edges[b]) & (t < edges[b + 1])
        tr = ~te & (np.abs(t - edges[b]) > 5) & (np.abs(t - edges[b + 1]) > 5) & (y >= 0)
        Xtr, ytr = X[tr], y[tr]
        if other is not None:
            m = other["y"] >= 0
            Xtr, ytr = np.concatenate([Xtr, other["X"][m]]), np.concatenate([ytr, other["y"][m]])
        s[te] = _clf().fit(Xtr, ytr).predict_proba(X[te])[:, 1]
    return smooth(s, 3)


def summarize(c: list[dict]) -> dict:
    b = max(c, key=lambda z: z["f1"])
    a = at_recall(c, 0.8)
    r = lambda v: round(float(v), 3)  # noqa: E731
    return {"legjobb_f1": {k: r(b[k]) for k in ("felidezes", "pontossag", "teves_per_perc", "f1", "kuszob")},
            "felidezes_80": None if a is None else {k: r(a[k]) for k in ("felidezes", "pontossag", "teves_per_perc")}}


FINAL_RECALL = 0.8


def save_final(m1: dict, m2: dict, path: Path) -> dict:
    """A végleges modell mindkét meccs összes élő lövésén. A küszöb: a kombinált blokkos CV-ben
    (a másik meccs + ez a meccs) mindkét meccsen legalább FINAL_RECALL felidézést adó küszöbök
    közül a kisebb (a jelölteket ember nézi át → inkább több, mint kevesebb)."""
    import joblib

    thr, cv = [], {}
    for name, test, other in (("m1", m1, m2), ("m2", m2, m1)):
        c = at_recall(curve_of(test["t"], scores(test, other, True), test["st"]), FINAL_RECALL)
        thr.append(c["kuszob"] if c else 0.05)
        cv[name] = c
    k = float(min(thr))
    X = np.concatenate([m1["X"][m1["y"] >= 0], m2["X"][m2["y"] >= 0]])
    y = np.concatenate([m1["y"][m1["y"] >= 0], m2["y"][m2["y"] >= 0]])
    bundle = {"model": _clf().fit(X, y), "features": m1["names"], "swing": True, "broadcast": True, "court": True,
              "kuszob": k, "kuszob_cv": cv}
    joblib.dump(bundle, path)
    print(f"végleges modell → {path} (küszöb {k}; CV a küszöbökön: {cv})")
    return bundle


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--m1", nargs=4, required=True, metavar=("POSE", "BROADCAST", "COURT", "EVENTS"))
    ap.add_argument("--m2", nargs=4, required=True, metavar=("POSE", "BROADCAST", "COURT", "EVENTS"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--save-model", help="a két meccsen együtt tanított póz + kamera modell (joblib) ide")
    ap.add_argument("--only-model", action="store_true", help="a kísérlet nélkül, csak a végleges modell")
    a = ap.parse_args(argv)
    if a.save_model:
        save_final(load_match(*a.m1, True), load_match(*a.m2, True), Path(a.save_model))
        if a.only_model:
            return 0
    res = {}
    for cname, use_bc in CONFIGS.items():
        M = {"m1": load_match(*a.m1, use_bc), "m2": load_match(*a.m2, use_bc)}
        assert M["m1"]["names"] == M["m2"]["names"]
        for test, other in (("m2", "m1"), ("m1", "m2")):
            T, O = M[test], M[other]
            for mode, (oth, own) in {"csak a másik meccs": (O, False), "csak ez a meccs": (None, True),
                                     "a másik meccs + ez a meccs": (O, True)}.items():
                s = summarize(curve_of(T["t"], scores(T, oth, own), T["st"]))
                res.setdefault(cname, {}).setdefault(test, {})[mode] = s
                f, r80 = s["legjobb_f1"], s["felidezes_80"]
                print(f"{cname:13s} teszt={test} {mode:28s} F1 {f['f1']:.2f} ({f['felidezes']:.0%}/{f['pontossag']:.0%})"
                      + (f"  80%-nál: pontosság {r80['pontossag']:.0%}, téves/perc {r80['teves_per_perc']:.2f}"
                         if r80 else "  80% nem érhető el"), flush=True)
        res[cname]["lovesek"] = {k: int(len(v["st"])) for k, v in M.items()}
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
