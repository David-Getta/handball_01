"""Elnyelt-kivétel jelentés: hol dob a kód olyan hibát, amit egy
try/except NÉMÁN elnyel.

A recept szerint minden felület try/except-ben ül, hogy egy réteg hibája
ne vigye el a többit. Az ára: a hibát is elnyeli — a szabály, a mondat
vagy a mező némán üres marad, a tesztek zöldek. Így maradt észrevétlen,
hogy a felderítés a `match_xg`-t a saját, KÉSŐBB álló helyi importja
előtt használta (UnboundLocalError): a szélső- és poszt-gólok minden
felderítésben üresek voltak.

A jelentés nyomkövetővel (sys.settrace / threading.settrace, csak a
hívás- és kivétel-események) lefuttatja
- minden regisztrált réteget (ugyanaz a lista, mint a sorrend-függésé),
- a négy nagy felületet (összefoglaló, felderítés, meccsterv, edzés),
- az API minden olyan GET-végpontját, ami csak meccs-azonosítót (és
  esetleg track-azonosítót) kér, valamint a több meccses felületeket
  (összevont felderítés, meccsterv, trend, szezon- és egymás-elleni
  riport, könyvtár, játékos-trend),
és összegyűjt minden kivételt, ami a `handball` csomag kódjában
SZÜLETETT — akkor is, ha valahol elnyelték. A generátor-zárás, a
bejárás vége, a fájl-hiány (a gyorsítótár "még nincs ilyen" ága) és a
végpontok szándékos HTTP-hibaválasza nem hiba.

Futtatás (a backend mappából, kiadás előtt — percekig fut):

    python3 -m scripts.swallowed_exceptions

A lista ÜRES, és annak is kell maradnia. A gyors, egy meccses őr
(a négy nagy felület) a `tests/test_nema_kivetelek.py`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

DEFAULT_SECONDS = 120.0
# Ezek nem hibák: a generátor lezárása és a bejárás vége vezérlés, a
# fájl-hiány a gyorsítótár "még nincs ilyen" ága, a HTTPException pedig a
# végpont szándékos hiba-VÁLASZA (pl. "nincs videó a kalibráció-
# rajzhoz" — 404), nem elnyelt hiba.
NEM_HIBA = {"GeneratorExit", "StopIteration", "FileNotFoundError",
            "HTTPException"}

_REPORT = (Path(__file__).resolve().parent.parent.parent / "docs"
           / "ELNYELT_KIVETELEK.md")


class _Gyujto:
    """A nyomkövető: a handball-kódban született kivételek felületenként."""

    def __init__(self, hb: str):
        self.hb = hb
        self.felulet = "?"
        self.talalat: dict = {}
        # Az objektumot ÉLETBEN tartjuk: az id() a felszabadított kivételé
        # után újrahasznosul, és a következőt "már látottnak" vennénk.
        self._latott: dict = {}
        self._zar = threading.Lock()

    def lokalis(self, frame, event, arg):
        if event == "exception":
            exc = arg[1]
            with self._zar:
                if id(exc) in self._latott:
                    return self.lokalis
                self._latott[id(exc)] = exc
            if type(exc).__name__ not in NEM_HIBA:
                kulcs = (type(exc).__name__,
                         os.path.relpath(frame.f_code.co_filename, self.hb),
                         frame.f_lineno, frame.f_code.co_name)
                with self._zar:
                    rec = self.talalat.setdefault(
                        kulcs, {"n": 0, "uzenet": str(exc)[:160],
                                "feluletek": []})
                    rec["n"] += 1
                    if self.felulet not in rec["feluletek"]:
                        rec["feluletek"].append(self.felulet)
        return self.lokalis

    def globalis(self, frame, event, arg):
        if frame.f_code.co_filename.startswith(self.hb):
            frame.f_trace_lines = False  # csak hívás/kivétel: gyors
            return self.lokalis
        return None

    def futtat(self, nev: str, fn) -> str | None:
        """Egy felület futtatása követve; hibánál a hiba szövege."""
        self.felulet = nev
        sys.settrace(self.globalis)
        try:
            fn()
            return None
        except Exception as e:  # a felület maga is elbukhat — azt is jelezzük
            return f"{type(e).__name__}: {e}"[:200]
        finally:
            sys.settrace(None)


def _kotelezo(param) -> bool:
    """Kötelező-e egy lekérdezés-paraméter (a FastAPI-változatok közt a
    jelző helye eltér)."""
    if hasattr(param, "required"):
        return bool(param.required)
    return bool(param.field_info.is_required())


def _meccs(seconds: float, seed: int, datum: str):
    from handball.sim.match_simulator import simulate_ground_truth
    m = simulate_ground_truth(duration_s=seconds, fps=25.0, seed=seed,
                              shots_per_min=8, halftime_break_s=30)
    m.meta.date = datum
    for f in m.frames:
        for p in f.players:
            p.jersey_number = (p.track_id % 14) + 1
    return m


def measure(seconds: float = DEFAULT_SECONDS) -> dict:
    """{"talalat": {(típus, fájl, sor, függvény): {...}}, "elbukott":
    [(felület, hiba)], "feluletek": db}."""
    import handball

    hb = os.path.dirname(os.path.abspath(handball.__file__))
    gy = _Gyujto(hb)
    elbukott: list = []
    db = 0

    def fut(nev, fn):
        nonlocal db
        db += 1
        hiba = gy.futtat(nev, fn)
        if hiba:
            elbukott.append((nev, hiba))

    # 1) Minden regisztrált réteg, friss meccsen.
    import importlib

    from scripts.order_sensitivity import _layer_functions

    # Egy közös meccs: a kivétel-keresésnek nem kell friss példány (a
    # sorrend-függés jelentésével ellentétben), és így percek helyett
    # a primitívek egyszer számolódnak.
    alap = _meccs(seconds, 5, "2026-01-15")
    for name, mod_name, fn_name in _layer_functions():
        mod = importlib.import_module(f"handball.pipeline.{mod_name}")
        fn = getattr(mod, fn_name)
        fut(f"réteg:{name}", lambda fn=fn: fn(alap))

    # 2) A négy nagy felület.
    from handball.models.tracking import Team
    from handball.pipeline.coach_summary import coach_summary
    from handball.pipeline.primitive_cache import primitive_cache
    from handball.pipeline.scouting import (matchup_plan, report_to_dict,
                                            scout_team)
    from handball.pipeline.training import training_focus

    def felderites():
        with primitive_cache(alap):
            h, a = scout_team(alap, Team.HOME), scout_team(alap, Team.AWAY)
            report_to_dict(h)
            report_to_dict(a)
            matchup_plan(h, a)
            matchup_plan(a, h)

    fut("összefoglaló", lambda: coach_summary(alap))
    fut("felderítés+meccsterv", felderites)
    fut("edzés-fókusz", lambda: training_focus(alap))

    # 3) Az API: a meccs-szintű GET-végpontok és a több meccses felületek.
    with tempfile.TemporaryDirectory() as tmp:
        regi_env = os.environ.get("HANDBALL_DATA_DIR")
        os.environ["HANDBALL_DATA_DIR"] = tmp
        try:
            d = Path(tmp) / "data" / "matches"
            d.mkdir(parents=True, exist_ok=True)
            ids = []
            for i, seed in enumerate((5, 11, 17)):
                m = _meccs(seconds, seed, f"2026-0{i + 1}-15")
                (d / f"{m.meta.match_id}.json").write_text(
                    json.dumps(m.to_dict()), encoding="utf-8")
                ids.append(m.meta.match_id)
            from fastapi.routing import APIRoute
            from fastapi.testclient import TestClient

            from handball.api.app import create_app
            app = create_app()
            # A szinkron végpontok SZÁLON futnak: a később induló szálakra
            # is kell a nyomkövető.
            threading.settrace(gy.globalis)
            c = TestClient(app)
            for r in app.routes:
                if not isinstance(r, APIRoute) or "GET" not in r.methods:
                    continue
                parameterek = {p.name for p in r.dependant.path_params}
                if not parameterek or not parameterek <= {"match_id",
                                                           "track_id"}:
                    continue
                if any(_kotelezo(q) for q in r.dependant.query_params):
                    continue
                ut = r.path.replace("{match_id}", ids[0]) \
                           .replace("{track_id}", "1")
                fut(f"GET {r.path}", lambda ut=ut: c.get(ut))
            H, V = "Szimu Hazai", "Szimu Vendég"
            hazai = {"items": [{"match_id": i, "team": "home"} for i in ids]}
            vendeg = {"items": [{"match_id": i, "team": "away"} for i in ids]}
            for nev, hivas in (
                    ("POST /scouting", lambda: c.post("/scouting", json=hazai)),
                    ("POST /scouting/matchup", lambda: c.post(
                        "/scouting/matchup", json={"own": hazai, "opp": vendeg})),
                    ("POST /scouting/trend", lambda: c.post(
                        "/scouting/trend",
                        json={"older": {"items": hazai["items"][:1]},
                              "newer": {"items": hazai["items"][1:]}})),
                    ("GET /season/report", lambda: c.get(
                        "/season/report", params={"team": H})),
                    ("GET /head-to-head/report", lambda: c.get(
                        "/head-to-head/report",
                        params={"team_a": H, "team_b": V})),
                    ("GET /library/summary", lambda: c.get("/library/summary")),
                    ("GET /library/training-focus", lambda: c.get(
                        "/library/training-focus", params={"team": H})),
                    ("GET /players/trend", lambda: c.get(
                        "/players/trend", params={"team": H, "jersey": 2})),
                    ("GET /players/season-report", lambda: c.get(
                        "/players/season-report",
                        params={"team": H, "jersey": 2}))):
                fut(nev, hivas)
        finally:
            threading.settrace(None)
            if regi_env is None:
                os.environ.pop("HANDBALL_DATA_DIR", None)
            else:
                os.environ["HANDBALL_DATA_DIR"] = regi_env
    return {"talalat": gy.talalat, "elbukott": elbukott, "feluletek": db}


def build_report(res: dict, seconds: float) -> str:
    sorok = [
        "# Elnyelt kivételek (generált jelentés)",
        "",
        "A `python3 -m scripts.swallowed_exceptions` írja — kézzel ne "
        "szerkeszd.",
        "",
        "Minden regisztrált réteg, a négy nagy felület (összefoglaló, "
        "felderítés + meccsterv, edzés-fókusz) és az API meccs-szintű "
        "GET-végpontjai, valamint a több meccses felületek, szimulált "
        f"meccseken ({int(seconds)} mp, félidővel, lövésekkel), "
        "nyomkövetővel. Minden kivétel, ami a `handball` kódban születik — "
        "akkor is, ha egy try/except elnyelte.",
        "",
        f"- átvizsgált felület: {res['feluletek']}",
        f"- elnyelt kivétel (hely): {len(res['talalat'])}",
        f"- maga is elbukott felület: {len(res['elbukott'])}",
        "",
    ]
    if res["talalat"]:
        sorok += ["## Elnyelt kivételek (JAVÍTANDÓ)", ""]
        for (tip, fajl, sor, fv), rec in sorted(res["talalat"].items()):
            sorok.append(f"- `{tip}` — `{fajl}:{sor}` ({fv}), "
                         f"{rec['n']}×: {rec['uzenet']}")
            sorok.append("  - felület: " + ", ".join(rec["feluletek"][:6]))
        sorok += [""]
    else:
        sorok += ["Az elnyelt-kivétel lista üres — és annak is kell "
                  "maradnia.", ""]
    if res["elbukott"]:
        sorok += ["## Elbukott felületek", ""]
        sorok += [f"- {n}: {h}" for n, h in res["elbukott"]]
        sorok += [""]
    return "\n".join(sorok)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seconds", type=float, default=DEFAULT_SECONDS)
    args = ap.parse_args(argv)
    res = measure(args.seconds)
    _REPORT.write_text(build_report(res, args.seconds), encoding="utf-8")
    print(f"Elnyelt-kivétel jelentés kiírva: {_REPORT}")
    print(f"  átvizsgált felület: {res['feluletek']}")
    print(f"  elnyelt kivétel (hely): {len(res['talalat'])}")
    for (tip, fajl, sor, fv), rec in sorted(res["talalat"].items()):
        print(f"    - {tip} {fajl}:{sor} ({fv}) {rec['n']}× — "
              f"{', '.join(rec['feluletek'][:3])}")
    print(f"  elbukott felület: {len(res['elbukott'])}")
    for n, h in res["elbukott"]:
        print(f"    - {n}: {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
