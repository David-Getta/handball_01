"""Nyilvános élő szöveges közvetítés (liveticker) → gépi címkék a meccsvideóhoz.

Az eredményjelző kiolvasása (`scoreboard`) megadja, MIKOR esett a gól a
videóban; a ticker megadja, KI lőtte, és gyakran azt is, HONNAN (beálló,
szélső, átlövés, hétméteres, indítás) — ezt a hozzászólás szövegéből,
kulcsszavakkal. A kettő a csapatonkénti gól-sorszámon keresztül párosítható
(a hazai csapat k-adik gólja mindkét forrásban ugyanaz), tehát nem kell hozzá
a játékóra és a ticker-idő sem.

A ticker a hétméteres-hibákat is tartalmazza (gól nélküli lövés!), a védéseket
és a mellé lövéseket viszont NEM: a teljes lövéslista továbbra is a kézi
jelölésből jön; a ticker a gólok és a hetesek címkéje.

A videóidő a nem-gól eseményeknél a falióra-időből (perc pontosságú) becsülhető:
a gólok (videóidő, falióra) párjaira illesztett egyenes, mert a felvétel az élő
adás folyamatos rögzítése.

A szabad szöveg NEM kerül a kimenetbe (szerzői jog), csak a belőle kinyert
kategória és a kulcsszó.

    python -m hbd.ticker --ticker sportschau.md --scoreboard allas.json --roster keret.json \\
        --home "SC Magdeburg" --out meccs2_ticker.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

# A lövés helyzete a hozzászólás kulcsszavaiból; az ELSŐ illeszkedő csoport dönt
# (a hetes és az indítás erősebb jel, mint a hely: a "Tempogegenstoß von außen" indítás).
HELYZET_KULCSOK = [
    ("hetes", r"siebenmeter\w*|7-meter\w*|vom punkt"),
    ("inditas", r"tempogegenstoß|gegenstoß|gegenzug|leere\w* tor|empty goal"),
    ("beallo", r"\bkreis\w*"),
    ("szelso", r"außen\w*|flügel\w*"),
    ("atlovo", r"rückraum\w*|distanz|halblink\w*|halbrecht\w*|zweite\w* reihe|zentrum|fernwurf|hüftwurf"),
]
KIPATTANO_KULCS = r"abpraller|nachwurf|nachsetz\w*|zweiten versuch"
# A falióra → videóidő egyenesnél ennyi percnél nagyobb maradékú gólt kihagyunk
# (a ticker néha később küldi be a bejegyzést).
ORA_MAX_MARADEK_S = 90.0

_GOAL = re.compile(r"^\*\*Tor für (.+?), (\d+):(\d+) durch (.+?)\*\*$")
_MISS7 = re.compile(r"^\*\*7-Meter verworfen von (.+?) \((.+?)\)\*\*$")
_MINUTE = re.compile(r"^- (\d+)\.$")
_CLOCK = re.compile(r"^(\d\d):(\d\d)$")


def helyzet(text: str) -> tuple[str | None, str | None]:
    """(kategória, a kulcsszó) a szövegből, vagy (None, None)."""
    low = text.lower()
    for cat, pat in HELYZET_KULCSOK:
        m = re.search(pat, low)
        if m:
            return cat, m.group(0)
    return None, None


def parse_sportschau(md: str, home: str) -> list[dict]:
    """A sportschau.de ticker (markdown) eseményei IDŐRENDBEN.

    Esemény: {perc, ora ("hh:mm"), tipus ("gol" | "hetes_kihagyva"), csapat
    ("hazai" | "vendeg"), jatekos, allas ([hazai, vendég], csak gólnál),
    helyzet, kulcsszo, kipattano}."""
    lines = md.split("\n")
    starts = [i for i, ln in enumerate(lines) if _MINUTE.match(ln.strip())]
    out = []
    for a, b in zip(starts, starts[1:] + [len(lines)]):
        block = [ln.strip() for ln in lines[a:b]]
        perc = int(_MINUTE.match(block[0]).group(1))
        ora = next((ln for ln in block[1:] if _CLOCK.match(ln)), None)
        text = " ".join(ln for ln in block[1:] if ln and not ln.startswith(("[", "**", "- ", "!"))
                        and not _CLOCK.match(ln))
        for ln in block:
            g, m7 = _GOAL.match(ln), _MISS7.match(ln)
            if g:
                team, h, v, who = g.group(1), int(g.group(2)), int(g.group(3)), g.group(4)
                ev = {"tipus": "gol", "csapat": "hazai" if team == home else "vendeg", "allas": [h, v],
                      "jatekos": who}
            elif m7:
                ev = {"tipus": "hetes_kihagyva", "csapat": "hazai" if m7.group(2) == home else "vendeg",
                      "jatekos": m7.group(1)}
            else:
                continue
            cat, key = helyzet(text)
            if ev["tipus"] == "hetes_kihagyva":
                cat, key = "hetes", key or "7-meter"
            ev.update(perc=perc, ora=ora, helyzet=cat, kulcsszo=key,
                      kipattano=bool(re.search(KIPATTANO_KULCS, text.lower())))
            out.append(ev)
    out.reverse()  # a ticker a legfrissebbel kezd
    return out


def _poszt(roster: dict | None, side: str, name: str) -> str | None:
    if not roster:
        return None
    # a ticker néha a teljes nevet írja ("Hákun West av Teigum"), a keret a rövidet
    toks = set(name.lower().split())
    for p in roster[side]["jatekosok"]:
        if p["nev"] == name or set(p["nev"].lower().split()) <= toks:
            return p["poszt"]
    return None


def align(events: list[dict], sb: dict, roster: dict | None = None) -> dict:
    """A ticker-események videóidővel.

    Gól: a csapat k-adik gólja = az eredményjelző idővonalán a csapat k-adik
    gólja → t_tol..t_ig (s). Minden esemény: a félidőnkénti falióra-egyenesből
    becsült t_becsult (perc pontosság; a ticker-bejegyzés késése is benne van)."""
    sb_by = {"hazai": [], "vendeg": []}
    for g in sb["golok"]:
        sb_by[g["csapat"]].append(g)
    k = {"hazai": 0, "vendeg": 0}
    out, mism = [], []
    for ev in events:
        e = dict(ev)
        e["poszt_keretbol"] = _poszt(roster, e["csapat"], e["jatekos"])
        if e["tipus"] == "gol":
            side = e["csapat"]
            k[side] += 1
            idx = 0 if side == "hazai" else 1
            if e["allas"][idx] != k[side]:
                mism.append({"ticker": e["allas"], "sorszam": k[side]})
            if k[side] <= len(sb_by[side]):
                g = sb_by[side][k[side] - 1]
                e.update(t_tol=g["t_tol"], t_ig=g["t_ig"], allas_kepbol=g["allas_utana"])
        out.append(e)
    # falióra → videóidő, FÉLIDŐNKÉNT: a felvételből a szünet (részben) kimaradhat,
    # ezért a két félidő eltolása más. A meredekség rögzített (60 s / perc, élő adás).
    fit = {}
    for half, sel in (("1", lambda e: e["perc"] <= 30), ("2", lambda e: e["perc"] > 30)):
        pts = [(_min_of_day(e["ora"]), e["t_ig"]) for e in out
               if sel(e) and e.get("t_ig") is not None and e.get("ora")]
        if len(pts) < 5:
            continue
        x, y = np.array(pts, float).T
        keep = np.ones(len(x), bool)
        for _ in range(3):
            b = float(np.median(y[keep] - 60.0 * x[keep]))
            res = y - (60.0 * x + b)
            keep = np.abs(res) <= ORA_MAX_MARADEK_S
        fit[half] = {"eltolas_s": round(b, 1), "golok_az_egyenesen": int(keep.sum()), "golok": len(x),
                     "maradek_median_s": round(float(np.median(np.abs(res[keep]))), 1)}
        for e in out:
            if sel(e) and e.get("ora"):
                e["t_becsult"] = round(60.0 * _min_of_day(e["ora"]) + b, 1)
    n_gol = sum(e["tipus"] == "gol" for e in out)
    return {"esemenyek": out, "golok": n_gol, "parositott_golok": sum("t_tol" in e for e in out),
            "allas_eltero": mism, "faliora": fit}


def _min_of_day(hhmm: str) -> float:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Liveticker → gól- és hetes-címkék a videóhoz")
    ap.add_argument("--ticker", required=True, help="a ticker oldala markdownként (sportschau.de)")
    ap.add_argument("--scoreboard", required=True, help="a hbd.scoreboard read kimenete (allas.json)")
    ap.add_argument("--home", required=True, help="a hazai csapat neve a tickerben")
    ap.add_argument("--roster", help="keret JSON (mez, név, poszt) — a poszt a helyzet tartaléka")
    ap.add_argument("--source", default="", help="a ticker URL-je (a kimenetbe kerül)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    ev = parse_sportschau(Path(a.ticker).read_text(), a.home)
    roster = json.loads(Path(a.roster).read_text()) if a.roster else None
    res = align(ev, json.loads(Path(a.scoreboard).read_text()), roster)
    res = {"forras": a.source, "megjegyzes": "a szabad szöveg nincs benne, csak a kinyert kategória", **res}
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    hel = {}
    for e in res["esemenyek"]:
        hel[e["helyzet"]] = hel.get(e["helyzet"], 0) + 1
    print(f"{res['golok']} gól ({res['parositott_golok']} párosítva), "
          f"{sum(e['tipus'] == 'hetes_kihagyva' for e in res['esemenyek'])} kihagyott hetes; "
          f"helyzet: {hel}; eltérő állás: {len(res['allas_eltero'])}; falióra: {res['faliora']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
