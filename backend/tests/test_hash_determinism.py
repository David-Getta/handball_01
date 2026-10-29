"""A jelentés nem függhet a Python hash-véletlenítésétől.

A szöveg-kulcsú halmazok bejárási sorrendje folyamatonként más
(PYTHONHASHSEED), így ha egy szabály halmazon iterálva, szigorú
összehasonlítással választ, holtversenynél indításonként mást mond. Ezt
egy edző úgy látja, hogy ugyanaz a meccs két megnyitáskor más jelentést
ad. A "fekete ötperc" szabály pontosan így viselkedett (0–5. vagy 5–10.
perc, ugyanazzal a 0-40-es mérleggel).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.scouting import _window_order  # noqa: E402

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SZKRIPT = r'''
import json, sys
sys.path.insert(0, %r)
from handball.sim.match_simulator import simulate_ground_truth
from handball.pipeline.scouting import scout_team, report_to_dict, matchup_plan
from handball.models.tracking import Team
# A 10 perces meccs KELL: ezen áll elő a fekete-ötperc holtverseny
# (0–5. és 5–10. perc, ugyanazzal a mérleggel) — rövidebb meccsen a
# hibás kód is átmenne. Az 1-es és a 4-es hash-mag a régi kódon mérten
# eltérő választ adott.
m = simulate_ground_truth(duration_s=600, fps=25.0, seed=3, shots_per_min=8.0)
h = scout_team(m, Team.HOME)
m = simulate_ground_truth(duration_s=600, fps=25.0, seed=3, shots_per_min=8.0)
a = scout_team(m, Team.AWAY)
print(json.dumps({"home": report_to_dict(h), "away": report_to_dict(a),
                  "plan": matchup_plan(h, a), "plan2": matchup_plan(a, h)},
                 ensure_ascii=False, sort_keys=True, default=str))
''' % _BACKEND


def _futtat(hashseed: str) -> subprocess.Popen:
    env = dict(os.environ, PYTHONHASHSEED=hashseed)
    return subprocess.Popen([sys.executable, "-c", _SZKRIPT], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)


def test_a_felderites_es_a_meccsterv_hash_fuggetlen():
    """Két külön hash-véletlenítéssel futtatva a két felderítés és a két
    irányú meccsterv bitre azonos (a két folyamat párhuzamosan fut)."""
    p1, p2 = _futtat("1"), _futtat("4")
    out1, err1 = p1.communicate(timeout=600)
    out2, err2 = p2.communicate(timeout=600)
    assert p1.returncode == 0, err1[-2000:]
    assert p2.returncode == 0, err2[-2000:]
    a, b = json.loads(out1), json.loads(out2)
    for kulcs in a:
        if a[kulcs] != b[kulcs]:
            if isinstance(a[kulcs], dict):
                elter = sorted(k for k in a[kulcs]
                               if a[kulcs].get(k) != b[kulcs].get(k))
            else:
                elter = [x for x in a[kulcs] if x not in b[kulcs]][:3]
            raise AssertionError(f"hash-függő eredmény ({kulcs}): {elter}")


_HOLTVERSENY = r'''
import sys
sys.path.insert(0, %r)
from handball.pipeline.scouting import ScoutingReport, _coach_keys
rep = ScoutingReport(team="away", team_name="X", matches=1)
# Négy egyforma bukású ablak: a halmaz bejárási sorrendje hash-magonként
# más, tehát a hibás (halmazon iteráló) kód nem mindig az elsőt adja.
for b in ("0–5", "5–10", "10–15", "15–20"):
    rep.blw_scored[b] = 0
    rep.blw_conceded[b] = 4
print([k for k in _coach_keys(rep)[2] if "fekete ötpercük" in k][0])
''' % _BACKEND


def test_fekete_otperc_holtversenyben_a_korabbi_ablak():
    """Holtversenynél a KORÁBBI ablak a fekete ötperc — nyolc különböző
    hash-véletlenítés mellett is (egy folyamaton belül a hibás kód is
    átmehetne véletlenül: a halmaz sorrendje ott rögzített)."""
    folyamatok = []
    for mag in range(8):
        env = dict(os.environ, PYTHONHASHSEED=str(mag))
        folyamatok.append(subprocess.Popen(
            [sys.executable, "-c", _HOLTVERSENY], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    for f in folyamatok:
        out, err = f.communicate(timeout=300)
        assert f.returncode == 0, err[-2000:]
        assert "a 0–5. perc" in out, out


def test_az_ablak_rendezes_szamszeru():
    """A perc számként rendeződik ("10–15" a "5–10" után), a nem
    szabványos címke a végére."""
    assert sorted(["55–60", "5–10", "10–15", "0–5"], key=_window_order) == \
        ["0–5", "5–10", "10–15", "55–60"]
    assert _window_order("x") > _window_order("55–60")
