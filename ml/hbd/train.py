"""Keresztvalidált kiértékelés + végső modellek.

Feladatok (`dataset.TASKS`): binary (lövés / nem lövés), shot3 (felugrásos /
helyből / egyéb), all7 (mind a 7 kategória).

Modellek:
  majority — mindig a leggyakoribb osztály (a viszonyítási alap: ennél
             jobbnak KELL lennie mindennek, különben nem tanult semmit),
  logreg   — logisztikus regresszió a klip-jellemzőkön,
  hgb      — gradiens-erősítéses döntési fák a klip-jellemzőkön,
  tcn      — kis időbeli konvolúciós háló a testpont-sorozaton (torch).

Felosztás: StratifiedGroupKFold a JELENET szerint (ugyanaz a jelenet sosem
lehet egyszerre tanító és teszt). Mérőszámok: pontosság, kiegyensúlyozott
pontosság, makró-F1, osztályonkénti felidézés, tévesztési mátrix.

Kapus-profil: minden lövésre `goalkeeper.shot_profile`; a felugrás-ítélet
a címkével (jump-shot vs shot) összevetve is ki van értékelve.

    python -m hbd.train --poses poses.npz --out results/
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from .dataset import TASKS
from .features import feature_matrix, sequence
from .goalkeeper import JUMP_MIN_RISE, shot_profile
from .pose import load_dataset

FOLDS = 5


def _sk_models(seed: int):
    from sklearn.dummy import DummyClassifier
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return {
        "majority": lambda: DummyClassifier(strategy="most_frequent"),
        "logreg": lambda: make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=3000, class_weight="balanced", C=0.5)),
        "hgb": lambda: HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0,
            class_weight="balanced", random_state=seed),
    }


def metrics(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int) -> dict:
    from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix,
                                 f1_score, recall_score)

    labels = list(range(n_classes))
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "recall_per_class": [float(v) for v in recall_score(
            y_true, y_pred, labels=labels, average=None, zero_division=0)],
        "confusion": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
    }


def group_folds(y: np.ndarray, groups: np.ndarray, n_splits: int, seed: int):
    """Rétegzett, csoportos felosztás; kis adatnál kevesebb hajtással."""
    from sklearn.model_selection import StratifiedGroupKFold

    n_groups = len(np.unique(groups))
    min_class = np.bincount(y).min() if len(y) else 0
    k = max(2, min(n_splits, n_groups, max(2, min_class)))
    return list(StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=seed).split(
        np.zeros(len(y)), y, groups))


def evaluate_task(task: str, X: np.ndarray, S: np.ndarray, cats: np.ndarray, groups: np.ndarray,
                  seed: int, use_nn: bool, nn_epochs: int, folds: int) -> dict:
    class_names, mapping = TASKS[task]
    y = np.array([mapping[c] for c in cats])
    present = np.unique(y)
    splits = group_folds(y, groups, folds, seed)
    model_makers = dict(_sk_models(seed))
    if use_nn:
        from .models import SeqClassifier

        model_makers["tcn"] = lambda: SeqClassifier(len(class_names), epochs=nn_epochs, seed=seed)

    out = {"classes": list(class_names), "n": int(len(y)),
           "class_counts": np.bincount(y, minlength=len(class_names)).tolist(),
           "folds": len(splits), "models": {}}
    for name, make in model_makers.items():
        pred = np.full(len(y), -1)
        for tr, te in splits:
            m = make()
            if name == "tcn":
                m.fit(S[tr], y[tr])
                pred[te] = m.predict(S[te])
            else:
                m.fit(X[tr], y[tr])
                pred[te] = m.predict(X[te])
        out["models"][name] = metrics(y, pred, len(class_names))
    out["present_classes"] = present.tolist()
    return out


def fit_final(task: str, X, S, cats, out_dir: Path, seed: int, use_nn: bool, nn_epochs: int,
              feature_names: list[str]) -> list[str]:
    """Végső modellek az ÖSSZES adaton (a Macen futtatáshoz)."""
    import joblib

    class_names, mapping = TASKS[task]
    y = np.array([mapping[c] for c in cats])
    saved = []
    hgb = _sk_models(seed)["hgb"]().fit(X, y)
    p = out_dir / f"model_{task}_hgb.joblib"
    joblib.dump({"model": hgb, "classes": list(class_names), "features": feature_names}, p)
    saved.append(p.name)
    if use_nn:
        from .models import SeqClassifier

        nn = SeqClassifier(len(class_names), epochs=nn_epochs, seed=seed).fit(S, y)
        p = out_dir / f"model_{task}_tcn.pt"
        nn.save(p)
        saved.append(p.name)
    return saved


def goalkeeper_report(clips: list[dict], out_dir: Path) -> dict:
    """Kapus-profil minden lövésre + a felugrás-ítélet összevetése a címkével."""
    rows, rises, labels = [], [], []
    for c in clips:
        if c["category"] not in ("jump-shot", "shot"):
            continue
        prof = shot_profile(c["kps"], c["boxes"], c["fps"])
        if prof is None:
            rows.append({"klip": c["name"], "kategoria": c["category"], "itelet": "kevés adat"})
            continue
        rows.append({"klip": c["name"], "kategoria": c["category"], **prof})
        rises.append(prof["csipo_emelkedes"])
        labels.append(int(c["category"] == "jump-shot"))
    if rows:
        keys = sorted({k for r in rows for k in r}, key=lambda k: (k not in ("klip", "kategoria"), k))
        with open(out_dir / "kapus_profilok.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    rep: dict = {"loves_db": len(rows), "profil_db": len(rises)}
    if len(set(labels)) == 2:
        from sklearn.metrics import roc_auc_score

        r, lab = np.array(rises), np.array(labels)
        pred = (r >= JUMP_MIN_RISE).astype(int)
        rep["felugras_pontossag"] = float((pred == lab).mean())
        rep["felugras_felidezes_jumpshot"] = float(pred[lab == 1].mean())
        rep["felugras_teves_riasztas_shot"] = float(pred[lab == 0].mean())
        rep["felugras_auc"] = float(roc_auc_score(lab, r))
    prof_rows = [r for r in rows if "kartartas" in r]
    for key in ("kartartas", "lovokez"):
        cnt: dict[str, int] = {}
        for r in prof_rows:
            cnt[r[key]] = cnt.get(r[key], 0) + 1
        rep[f"{key}_eloszlas"] = cnt
    return rep


def _md_table(task_res: dict) -> str:
    lines = ["| modell | pontosság | kiegy. pontosság | makró-F1 | felidézés osztályonként |",
             "|---|---|---|---|---|"]
    for name, m in task_res["models"].items():
        rec = ", ".join(f"{c}: {v:.2f}" for c, v in zip(task_res["classes"], m["recall_per_class"]))
        lines.append(f"| {name} | {m['accuracy']:.3f} | {m['balanced_accuracy']:.3f} | "
                     f"{m['macro_f1']:.3f} | {rec} |")
    best = max((n for n in task_res["models"] if n != "majority"),
               key=lambda n: task_res["models"][n]["macro_f1"], default=None)
    if best:
        cm = task_res["models"][best]["confusion"]
        lines += ["", f"Tévesztési mátrix ({best}; sor = valódi, oszlop = jósolt):", "",
                  "| | " + " | ".join(task_res["classes"]) + " |",
                  "|---" * (len(cm) + 1) + "|"]
        for cname, row in zip(task_res["classes"], cm):
            lines.append(f"| **{cname}** | " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def write_report(results: dict, out_dir: Path) -> Path:
    md = ["# UNIRI-HBD — mozdulatfelismerés testpontokból", "",
          f"Klipek: {results['n_clips']}; felosztás: {results['folds']}-szörös, jelenet szerint "
          "csoportosítva (ugyanaz a jelenet sosem tanító és teszt egyszerre).", "",
          "A `majority` a viszonyítási alap: ami nem jobb nála, az nem tanult semmit.", ""]
    for task, res in results["tasks"].items():
        md += [f"## Feladat: {task}", "",
               "Osztályok és darabszámok: " + ", ".join(
                   f"{c} = {n}" for c, n in zip(res["classes"], res["class_counts"])), "",
               _md_table(res), ""]
    gk = results.get("goalkeeper", {})
    if gk:
        md += ["## Kapus-profil (lövésenként, címke nélkül)", "",
               f"Lövések: {gk.get('loves_db')}, ebből profil készült: {gk.get('profil_db')}.", ""]
        if "felugras_pontossag" in gk:
            md += [f"- Felugrás-ítélet a címkéhez mérve (jump-shot vs shot): pontosság "
                   f"{gk['felugras_pontossag']:.3f}, AUC {gk['felugras_auc']:.3f}; felugrásosból "
                   f"felismert {gk['felugras_felidezes_jumpshot']:.2f}, helyből lövésnél tévesen "
                   f"felugrásnak mondott {gk['felugras_teves_riasztas_shot']:.2f}."]
        md += [f"- Kartartás az elengedéskor: {gk.get('kartartas_eloszlas')}",
               f"- Lövőkéz: {gk.get('lovokez_eloszlas')}",
               "- A kartartásra NINCS címke az adathalmazban: kézi mintán kell ellenőrizni "
               "(`kapus_profilok.csv`).", ""]
    if results.get("saved_models"):
        md += ["## Mentett végső modellek", ""] + [f"- `{p}`" for p in results["saved_models"]]
    p = out_dir / "results.md"
    p.write_text("\n".join(md) + "\n")
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="UNIRI-HBD: kiértékelés és tanítás")
    ap.add_argument("--poses", required=True, help="a hbd.pose kimenete (.npz)")
    ap.add_argument("--out", required=True, help="kimeneti mappa")
    ap.add_argument("--tasks", default="binary,shot3,all7")
    ap.add_argument("--folds", type=int, default=FOLDS)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-nn", action="store_true", help="a torch-háló kihagyása")
    ap.add_argument("--nn-epochs", type=int, default=80)
    ap.add_argument("--no-final", action="store_true", help="ne tanítson végső modellt")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    clips = [c for c in load_dataset(args.poses)["clips"] if len(c["kps"]) > 0]
    X, feat_names = feature_matrix(clips)
    S = np.stack([sequence(c["kps"], c["boxes"]) for c in clips])
    cats = np.array([c["category"] for c in clips])
    groups = np.array([c["scene_id"] for c in clips])
    use_nn = not args.no_nn
    if use_nn:
        try:
            import torch  # noqa: F401
        except ImportError:
            use_nn = False

    results = {"n_clips": len(clips), "folds": args.folds, "features": feat_names, "tasks": {}}
    saved = []
    for task in [t for t in args.tasks.split(",") if t]:
        print(f"== {task} ==", flush=True)
        res = evaluate_task(task, X, S, cats, groups, args.seed, use_nn, args.nn_epochs, args.folds)
        results["tasks"][task] = res
        for name, m in res["models"].items():
            print(f"  {name:9s} pontosság {m['accuracy']:.3f}  kiegy. {m['balanced_accuracy']:.3f}"
                  f"  makró-F1 {m['macro_f1']:.3f}", flush=True)
        if not args.no_final:
            saved += fit_final(task, X, S, cats, out, args.seed, use_nn, args.nn_epochs, feat_names)
    results["goalkeeper"] = goalkeeper_report(clips, out)
    results["saved_models"] = saved
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    p = write_report(results, out)
    print(f"Jelentés: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
