"""Kiosztható figura-lap — a Figura-tervező figurája papíron.

A 3D/VR a figura bejárására jó; az öltözőben, a táblánál és otthon a
papír a gyors: lépésenként (kulcs-pozíciónként) egy felülnézeti ábra — a
támadók mezszámmal (a figura sorszáma), a fal a védelem modellje szerint
(a labdára reagálva), a labda, a következő pontig futás (kék) és a passz
(sárga) nyila —, alatta a lépés leírása ("3. fut 4,2 m · passz 1 → 2"),
a lap tetején a kiértékelés (a mozgás hossza, a labda útja, a legjobb
lövőhelyzet). Böngészőből nyomtatható (PDF).

Az ábra a meccs-jelentés jegyzet-ábrájával azonos rajzoló
(report_html._note_diagram_svg) — a két papír ugyanúgy néz ki.
"""

from __future__ import annotations

import math
from html import escape

from ..models.tracking import Ball, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import TacticsConfig

# Egy ábra szélessége a lapon (px — A4-en kettő fér egy sorba).
FIGURA_LAP_ABRA_PX = 340
# Ennél rövidebb elmozdulás nem futás (nincs nyíl, nincs sor a leírásban).
FIGURA_LAP_FUTAS_MIN_M = 0.6
# Az ábra a támadó térfélre vág: a leghátsó támadó mögött ennyi m-től a
# gólvonalig (legfeljebb a felezőig) — a figura így kétszer akkora.
FIGURA_LAP_HATRA_M = 3.0


def _pont_felirat(i: int, k: int) -> str:
    """A kulcs-pozíció neve (mint a tervezőben): 3 pontnál Kezdő / Közép /
    Vég, 2-nél Kezdő / Vég, többnél sorszám."""
    if k == 3:
        return ("Kezdő", "Közép", "Vég")[i]
    if k == 2:
        return ("Kezdő", "Vég")[i]
    return f"{i + 1}. pont"


def _hely(ut: list, i: int, k: int) -> tuple:
    """Az út helye a k pontos figura i. kulcs-pozícióján (eltérő hosszú
    utaknál arányosan, szakaszonként lineárisan)."""
    if len(ut) == 1 or k == 1:
        return tuple(ut[0])
    s = i / (k - 1) * (len(ut) - 1)
    j = min(len(ut) - 2, int(s))
    f = s - j
    return (ut[j][0] + (ut[j + 1][0] - ut[j][0]) * f,
            ut[j][1] + (ut[j + 1][1] - ut[j][1]) * f)


def _vagott_abra(d: dict, x0: float) -> str:
    """A jegyzet-ábra (report_html._note_diagram_svg) a pálya x0..40 m-es
    szeletére vágva, FIGURA_LAP_ABRA_PX széles képként: a rajzoló a teljes
    pályát rajzolja, a nézet (viewBox) csak a szeletet mutatja."""
    from .report_html import _note_diagram_svg

    teljes = FIGURA_LAP_ABRA_PX * COURT_LENGTH_M / (COURT_LENGTH_M - x0)
    w = int(round(teljes))
    svg = _note_diagram_svg(d, width=w)
    s = w / COURT_LENGTH_M
    h = w // 2
    fej = (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" ')
    assert svg.startswith(fej)
    vx = x0 * s
    vw = w - vx
    magas = int(round(FIGURA_LAP_ABRA_PX * h / vw))
    return (f'<svg viewBox="{vx:.1f} 0 {vw:.1f} {h}" '
            f'width="{FIGURA_LAP_ABRA_PX}" height="{magas}" '
            + svg[len(fej):])


def _szam(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


# A lap stílusa és jelmagyarázata (a figura-lap és a figurafüzet közös).
_STILUS = (
    "body{font-family:system-ui,sans-serif;color:#1c2733;margin:24px;"
    "background:#fff}"
    "h1{font-size:20px;margin:0 0 4px}"
    ".al{color:#56657a;font-size:13px;margin-bottom:14px}"
    ".lapok{display:flex;flex-wrap:wrap;gap:16px}"
    ".lepes{border:1px solid #d6dde6;border-radius:8px;padding:8px;"
    "break-inside:avoid}"
    ".lc{font-weight:600;font-size:13px;margin-bottom:6px}"
    ".ll{font-size:12px;color:#33445a;margin-top:6px;max-width:340px}"
    ".jel{font-size:11px;color:#56657a;margin-top:16px}"
    "@media print{body{margin:10mm}}")
_JELMAGYARAZAT = (
    '<div class="jel">Kék nyíl: futás a következő pontig · sárga: passz · '
    "piros: a fal a védelem modellje szerint (a labdára reagál) · "
    "Sport Machine — Figura-tervező</div>")
# A figurafüzet legfeljebb ennyi figurát nyomtat (figuránként egy oldal).
FIGURA_FUZET_MAX = 40


def _dokumentum(cim: str, torzs: str, extra_stilus: str = "") -> str:
    return ('<!DOCTYPE html><html lang="hu"><head><meta charset="utf-8">'
            f"<title>{escape(cim)}</title><style>" + _STILUS + extra_stilus
            + "</style></head><body>" + torzs + _JELMAGYARAZAT
            + "</body></html>")


def figura_lap_html(utak: list, labda: list, defense, *, nev: str,
                    vedo_nev: str) -> str:
    """A figura nyomtatható lapja (önálló HTML).

    `utak`: támadónként a kulcs-pozíciók ([(x, y), …], méter); `labda`:
    kulcs-pozíciónként a labdás sorszáma; `defense`: a védelem modellje
    (play_simulation.DefenseModel). A kiértékelés a 3D-vel azonos
    (setplay_3d_match). ValueError, ha nincs érvényes támadó."""
    return _dokumentum(f"{nev} — figura-lap",
                       _figura_resz(utak, labda, defense, nev=nev,
                                    vedo_nev=vedo_nev))


def figura_fuzet_html(figurak: list, defense, *, vedo_nev: str,
                      cim: str = "Figurafüzet") -> str:
    """A csapat FIGURAFÜZETE (önálló, nyomtatható HTML): a mentett
    figurák ({"name", "attackers", "labda"} — a /playbook alakja) egy
    dokumentumban — elöl tartalomjegyzék, utána figuránként egy oldal (a
    figura-lap tartalma), a `defense` fallal. A hibás figura kimarad (a
    tartalomjegyzék alatt jelezve); legfeljebb FIGURA_FUZET_MAX figura.

    Edzőileg: a szezon figurái egy füzetben — az öltözőbe, az új
    játékosnak, a meccs előtti átnézéshez."""
    from .play_simulation import figura_nev

    reszek, nevek, kimaradt = [], [], []
    for d in list(figurak)[:FIGURA_FUZET_MAX]:
        nev = figura_nev(d.get("name")) or "névtelen"
        try:
            utak = [[(float(x), float(y)) for x, y in a] for a in d["attackers"]]
            reszek.append(_figura_resz(utak, list(d.get("labda") or []),
                                       defense, nev=nev, vedo_nev=vedo_nev))
            nevek.append(nev)
        except (KeyError, TypeError, ValueError):
            kimaradt.append(nev)
    if nevek:
        tartalom = ('<ol class="tj">' + "".join(
            f"<li>{escape(n)}</li>" for n in nevek) + "</ol>")
    else:
        tartalom = ('<div class="al">Még nincs mentett figura — a '
                    "Figura-tervezőben ments egyet.</div>")
    if kimaradt:
        tartalom += ('<div class="al">Kimaradt (hibás figura): '
                     + escape(", ".join(kimaradt)) + "</div>")
    torzs = (f"<h1>{escape(cim)}</h1>"
             f'<div class="al">{len(nevek)} figura · {escape(vedo_nev)}</div>'
             + tartalom
             + "".join(f'<section class="figura">{r}</section>' for r in reszek))
    return _dokumentum(cim, torzs,
                       ".tj{font-size:14px;line-height:1.7}"
                       ".figura{break-before:page;margin-top:24px}")


def _figura_resz(utak: list, labda: list, defense, *, nev: str,
                 vedo_nev: str) -> str:
    """Egy figura lapjának törzse (cím, kiértékelés, a lépések ábrái) —
    a figura-lap és a figurafüzet közös része."""
    from .play_simulation import setplay_3d_match

    _sim, e = setplay_3d_match(utak, defense, ball=labda, name=nev,
                               defense_name=vedo_nev)
    ut = e["utak"]
    lab = e["labda"]
    k = max(len(u) for u in ut)
    # A vágás bal széle: a leghátsó támadó mögött FIGURA_LAP_HATRA_M (a
    # felezőnél nem hátrább — a figura a +x kapura támad).
    x0 = min(COURT_LENGTH_M / 2.0,
             max(0.0, min(x for u in ut for x, _ in u) - FIGURA_LAP_HATRA_M))
    cfg = TacticsConfig()
    kapu_x = cfg.own_goal_x(Team.AWAY)
    elore = -1.0 if kapu_x == COURT_LENGTH_M else 1.0
    lepesek = []
    for i in range(k):
        helyek = [_hely(u, i, k) for u in ut]
        labdas = lab[min(i, len(lab) - 1)]
        bx, by = helyek[labdas]
        fal = defense.respond(Ball(x=bx, y=by, confidence=1.0), kapu_x)
        jatekosok = ([{"x": x, "y": y, "team": "home", "jersey": n + 1}
                      for n, (x, y) in enumerate(helyek)]
                     + [{"x": x, "y": y, "team": "away", "jersey": None}
                        for x, y in fal]
                     + [{"x": kapu_x + elore * 0.6,
                         "y": COURT_WIDTH_M / 2.0 + max(-1.2, min(1.2, 0.2 * (by - COURT_WIDTH_M / 2.0))),
                         "team": "away", "jersey": None}])
        nyilak, sorok = [], []
        if i < k - 1:
            kovetkezo = [_hely(u, i + 1, k) for u in ut]
            for n, ((x1, y1), (x2, y2)) in enumerate(zip(helyek, kovetkezo)):
                tav = math.hypot(x2 - x1, y2 - y1)
                if tav >= FIGURA_LAP_FUTAS_MIN_M:
                    nyilak.append((x1, y1, x2, y2, 1))
                    sorok.append(f"{n + 1}. fut {_szam(tav)} m")
            uj = lab[min(i + 1, len(lab) - 1)]
            if uj != labdas:
                (px1, py1), (px2, py2) = kovetkezo[labdas], kovetkezo[uj]
                if math.hypot(px2 - px1, py2 - py1) >= FIGURA_LAP_FUTAS_MIN_M:
                    nyilak.append((px1, py1, px2, py2, 0))
                sorok.append(f"passz: {labdas + 1} → {uj + 1}")
            if not sorok:
                sorok.append("helyben — várakozás")
        else:
            sorok.append(f"labda: {labdas + 1}. — befejezés")
        abra = _vagott_abra({"players": jatekosok, "ball": (bx, by),
                             "arrows": nyilak}, x0)
        cim = _pont_felirat(i, k) + (
            f" → {_pont_felirat(i + 1, k)}" if i < k - 1 else "")
        lepesek.append(
            f'<div class="lepes"><div class="lc">{i + 1}. {escape(cim)}</div>'
            f'{abra}<div class="ll">{escape(" · ".join(sorok))}</div></div>')

    osszegzes = [f"a mozgás {_szam(e['hossz_s'])} mp (valós tempóban)"]
    lu = [v for j, v in enumerate(lab) if j == 0 or v != lab[j - 1]]
    if len(lu) > 1:
        osszegzes.append("labda " + " → ".join(str(v + 1) for v in lu))
    if e.get("attacker_id") and e.get("best_shot_value", 0) > 0:
        osszegzes.append(
            f"legjobb lövőhelyzet: {e['attacker_id']}. játékos "
            f"({round(e['best_shot_value'] * 100)}%)")
    return (f"<h1>{escape(nev)}</h1>"
            f'<div class="al">{escape(vedo_nev)} · '
            f"{escape(' · '.join(osszegzes))}</div>"
            f'<div class="lapok">{"".join(lepesek)}</div>')
