"""Böngészős 3D / VR nézet — a meccs WebXR-képes oldalként.

A kliens "3D pálya" füle a képernyős bejárás; ez a modul UGYANAZT a
meccset egyetlen HTML-oldalként adja ki, amit egy böngésző — és a
jövőben egy önálló VR-headset (Quest-féle) böngészője — telepítés
nélkül megnyit. A WebXR biztonságos környezetet kér: a localhost az
(a headsetről USB + adb reverse tesz localhosttá), ezért az út a
motor `/matches/{id}/view3d` végpontja, nem egy mentett fájl.

A megjelenítés three.js (CDN-ről, a felhasználó böngészőjében), a
követési adat TÖMÖRÍTVE ágyazódik az oldalba: legfeljebb ~6 kép/mp,
deciméterre kerekítve — egy teljes meccs így is csak pár MB.

Videó nélkül tesztelhető: a kimenet szöveg.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..models.tracking import Match, PositionSource, Team

# A beágyazott adat cél-képrátája. A sima lejátszáshoz a böngészőben
# interpolálunk; ~6 kép/mp fölött az adat mérete nő, a látvány nem.
VIEW3D_MAX_FPS = 6.0


def _compact_data(match: Match, figure_alerts: list | None = None,
                  breakpoints: dict | None = None,
                  stoppers: dict | None = None) -> dict:
    """A követés tömör alakja: [[t_s, [[csapat,x,y],…], [bx,by]|0],…].

    `figure_alerts` (opcionális): a figura-riasztások ({"t", "team"}, a
    /figure-alerts alakja) — "f" típusú eseményként a jelenet-ugrásba és a
    feliratba: a visszatérő figura 3D-ben is megnézhető.
    `breakpoints` / `stoppers` (opcionális): a két csapat "feltörés"- és
    "megállítás"-listája (a court3d.tactical_keys_by_team két fele) — a
    végpont a lemezes tárból adja át, hogy a két teljes felderítés ne
    fusson le minden oldal-nyitásnál; None-nál itt számoljuk.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    lepes = max(1, int(round(fps / VIEW3D_MAX_FPS)))
    frames = []
    for i in range(0, len(match.frames), lepes):
        f = match.frames[i]
        jatekosok = [
            [1 if p.team == Team.HOME else 0,
             round(p.x, 1), round(p.y, 1),
             1 if p.source == PositionSource.MEASURED else 0,
             1 if getattr(p, "role", None) == "kapus" else 0,
             # Mezszám (0 = ismeretlen): a figura fölött címke — VR-ben
             # enélkül nem tudni, ki kicsoda.
             int(getattr(p, "jersey_number", None) or 0)]
            for p in f.players
        ]
        labda = ([round(f.ball.x, 1), round(f.ball.y, 1)]
                 if f.ball is not None else 0)
        frames.append([round(f.t / fps, 2), jatekosok, labda])
    # Események a jelenet-ugráshoz és a felirathoz: [t_s, típus, hazai?]
    # — a típus "g" (gól), "s" (lövés), "t" (eladás); a passz túl sűrű.
    esemenyek: list = []
    try:
        from .event_detection import detect_shots
        kod = {"goal": "g", "shot": "s", "turnover": "t"}
        for e in detect_shots(match):
            tipus = kod.get(getattr(e.type, "value", str(e.type)))
            if tipus is None:
                continue
            esemenyek.append([round(e.t / fps, 2), tipus,
                              1 if getattr(e.team, "value", e.team) == "home"
                              else 0])
    except Exception:
        esemenyek = []  # esemény nélkül is működjön a nézet
    # A visszatérő figura kezdete: "f" — a könyvtárból (több meccs kell).
    try:
        for a in (figure_alerts or []):
            esemenyek.append([round(int(a["t"]) / fps, 2), "f",
                              1 if a.get("team") == "home" else 0])
    except Exception:
        pass
    esemenyek.sort(key=lambda x: x[0])
    # A 3D eszközök közös számai (court3d): a tankönyvi falak (bal kapu
    # előtt, mélység + y) és az élő fal másodpercenként: [mp, hazai
    # védekezik?, forma-címke, a védett kapu x-e]. Hibája nem viheti el
    # a nézetet — a védekezés-panel ilyenkor csak a sablonokat adja.
    try:
        from .court3d import FORMATION_TEMPLATES
        formak = {nev: [list(p) for p in pontok]
                  for nev, pontok in FORMATION_TEMPLATES.items()}
    except Exception:
        formak = {}
    try:
        from .court3d import defence_timeline
        fal = [[r["s"], 1 if r["defending"] == "home" else 0, r["label"],
                r["goal_x"]] for r in defence_timeline(match)]
    except Exception:
        fal = []
    # Lövéstérkép: a meccs minden lövése a helyén (a match_xg az
    # elengedés kockájáról mér): [mp, hazai?, x, y, xG, kimenet, a
    # támadott kapu x-e] — a kimenet "g" gól, "v" védés, "m" mellé.
    try:
        from .tactics import TacticsConfig
        from .xg import match_xg
        cfg = TacticsConfig()
        kimenet = {"goal": "g", "save": "v"}
        lovesek = [
            [round(s["t"] / fps, 2), 1 if s["team"] == "home" else 0,
             s["x"], s["y"], round(float(s["xg"]), 3),
             kimenet.get(s["outcome"], "m"),
             cfg.attacks_toward_x(Team.HOME if s["team"] == "home"
                                  else Team.AWAY)]
            for s in match_xg(match, cfg)["shots"]]
    except Exception:
        lovesek = []  # lövéstérkép nélkül is működjön a nézet
    # Passzok: [mp, hazai?, x1, y1, x2, y2] — az adó és a fogadó helye a
    # passz kockáján; a futó passz vonala és a csapat passz-hálója ebből.
    try:
        from .event_detection import EventType, detect_events
        by_t = {f.t: f for f in match.frames}
        passzok = []
        for e in detect_events(match):
            if e.type != EventType.PASS or e.player_id is None:
                continue
            rid = (e.detail or {}).get("receiver_id")
            f = by_t.get(e.t)
            if rid is None or f is None:
                continue
            ado = next((p for p in f.players if p.track_id == e.player_id),
                       None)
            fogado = next((p for p in f.players if p.track_id == rid), None)
            if ado is None or fogado is None:
                continue
            passzok.append([round(e.t / fps, 2),
                            1 if getattr(e.team, "value", e.team) == "home"
                            else 0,
                            round(ado.x, 1), round(ado.y, 1),
                            round(fogado.x, 1), round(fogado.y, 1)])
    except Exception:
        passzok = []  # passz-vonalak nélkül is működjön a nézet
    # Döntés-pillanatok: ahol a modell szerint érdemben jobb opció is volt
    # — [mp, hazai?, passzoló x, y, választott x, y, érték, "s"/"p",
    # a jobb cél x, y, érték, különbség] időrendben (court3d).
    try:
        from .court3d import decision_moments
        dontesek = [
            [d["s"], 1 if d["team"] == "home" else 0, *d["passer"],
             *d["chosen"], d["chosen_value"],
             "s" if d["best_kind"] == "shoot" else "p", *d["best"],
             d["best_value"], d["gap"]]
            for d in decision_moments(match)["moments"]]
    except Exception:
        dontesek = []  # döntés-pillanatok nélkül is működjön a nézet
    # Szabad lövők: [mp, a védekező hazai?, lövő x, y, védő x, y | null,
    # távolság | null, gól?, xG] időrendben (court3d.free_shot_moments).
    try:
        from .court3d import free_shot_moments
        _fs = free_shot_moments(match)
        szabad_sugar = _fs["radius_m"]
        szabadok = [
            [m_["s"], 1 if m_["defending"] == "home" else 0,
             *m_["shooter"],
             *(m_["defender"] if m_["defender"] else [None, None]),
             m_["dist"], 1 if m_["goal"] else 0, m_["xg"]]
            for m_ in _fs["moments"]]
    except Exception:
        szabadok, szabad_sugar = [], 2.0
    # Labdavesztések: [mp, a vesztő hazai?, mez | null, vesztő x, y | null,
    # labda x, y | null, harmad (0 saját, 1 közép, 2 támadó) | null,
    # ellenfél x, y | null, távolság | null, kipréselt (1/0) | null,
    # gól ennyi mp múlva | null] időrendben (court3d.turnover_moments).
    try:
        from .court3d import turnover_moments
        _tm = turnover_moments(match)
        eladas_sugar = _tm["pressure_m"]
        _harmad = {"saját": 0, "közép": 1, "támadó": 2}
        eladasok = [
            [m_["s"], 1 if m_["team"] == "home" else 0, m_["jersey"],
             *(m_["loser"] or [None, None]), *(m_["ball"] or [None, None]),
             _harmad.get(m_["zone"]), *(m_["opponent"] or [None, None]),
             m_["dist"],
             None if m_["forced"] is None else (1 if m_["forced"] else 0),
             m_["goal_after_s"]]
            for m_ in _tm["moments"]]
    except Exception:
        eladasok, eladas_sugar = [], 2.5
    # Gól-akciók: [kezdet mp, gól mp, hazai?, [[ado x, y, fogado x, y,
    # ado mez, fogado mez], …], lövő x, y | null, lövő mez, kapu x, y,
    # passzok száma, időtartam] a gólok időrendjében (court3d).
    try:
        from .court3d import goal_build_ups
        golakciok = []
        for g in goal_build_ups(match)["moments"]:
            lanc = [[*(p["from"] or [None, None]), *(p["to"] or [None, None]),
                     p["from_jersey"], p["to_jersey"]]
                    for p in g["passes"]]
            golakciok.append([g["s"], g["goal_s"],
                              1 if g["team"] == "home" else 0, lanc,
                              *(g["shooter"] or [None, None]),
                              g["shooter_jersey"], *g["goal"],
                              g["n_passes"], g["duration_s"]])
    except Exception:
        golakciok = []
    # Emberelőny-szakaszok: [kezdet mp, vég mp, a hátrányban lévő hazai?,
    # az előnyben lévő góljai, a hátrányban lévő góljai, az előnyben
    # lévő kapura lövései, [[gól mp, hazai?], …]] (court3d).
    try:
        from .court3d import powerplay_moments
        emberek = [[w["s"], w["e"], 1 if w["team_down"] == "home" else 0,
                    w["goals_up"], w["goals_down"], w["shots_up"],
                    [[g[0], 1 if g[1] == "home" else 0] for g in w["goals"]]]
                   for w in powerplay_moments(match)["moments"]]
    except Exception:
        emberek = []
    # Lerohanások: [kezdet mp, a VÉDEKEZŐ hazai? (a lapozók közös
    # szűrőjéhez — a kapott lerohanás az ő hibája; a támadó a másik), lövő
    # mez | null, hullám ("e" első ember / "m" második) | null, elszökött
    # emberrel (1/0) | null, időtartam, kimenet ("g" gól / "l" lövés) |
    # null, [[x, y], …] a befejező útja, lövés x, y | null, kapu x, y,
    # labda x, y | null (induláskor), a jelenet vége mp (a lövés vagy a
    # szakasz vége)] időrendben (court3d.fast_break_moments).
    try:
        from .court3d import fast_break_moments
        kontrak = []
        for k in fast_break_moments(match)["moments"]:
            kontrak.append([k["s"], 1 if k["defending"] == "home" else 0,
                            k["shooter_jersey"],
                            {"first": "e", "second": "m"}.get(k["wave"]),
                            None if k["ahead"] is None
                            else (1 if k["ahead"] else 0),
                            k["duration_s"],
                            {"goal": "g", "shot": "l"}.get(k["outcome"]),
                            k["path"], *(k["shot"] or [None, None]),
                            *k["goal"], *(k["ball"] or [None, None]),
                            k["shot_s"] if k["shot_s"] is not None
                            else k["e"]])
    except Exception:
        kontrak = []
    # Kapott gólok: [mp, a VÉDEKEZŐ hazai? (a lapozók közös szűrőjéhez —
    # a lövő a másik), lövő mez | null, lövő x, y, sáv (0 kapuelőtér / 1
    # 6–9 m / 2 9 m-en túl), kapu-szög, távolság, védő x, y | null,
    # védő-távolság | null, szabadon (1/0) | null, kapus x, y | null,
    # kapus-mélység | null, kint (1/0) | null, xG, kapu x, y, az elengedés
    # kockája] időrendben (court3d.conceded_goal_moments).
    try:
        from .court3d import conceded_goal_moments
        _sav = {"kapuelőtér": 0, "6–9 m": 1, "9 m-en túl": 2}
        kapottak = [
            [g["s"], 1 if g["defending"] == "home" else 0,
             g["shooter_jersey"], *g["shooter"], _sav.get(g["zone"]),
             g["angle_deg"], g["dist_m"], *(g["defender"] or [None, None]),
             g["def_dist"],
             None if g["free"] is None else (1 if g["free"] else 0),
             *(g["keeper"] or [None, None]), g["keeper_depth"],
             None if g["keeper_out"] is None else (1 if g["keeper_out"] else 0),
             g["xg"], *g["goal"], g["t"]]
            for g in conceded_goal_moments(match)["moments"]]
    except Exception:
        kapottak = []
    # Hétméteresek: [mp, a dobó hazai?, mez | null, pont x, y | null,
    # dobó x, y | null, kimenet ("g" gól / "v" védés / "k" kihagyva / "?"),
    # irány (0 bal / 1 közép / 2 jobb) | null, cél x, y | null, kapus x, y
    # | null, kapus-mélység | null, kapu x, y, a lövés mp | null]
    # időrendben (court3d.seven_meter_moments).
    try:
        from .court3d import seven_meter_moments
        _kim = {"gól": "g", "védés": "v", "kihagyva": "k"}
        _ir = {"bal": 0, "közép": 1, "jobb": 2}
        hetesek = [
            [h["s"], 1 if h["team"] == "home" else 0, h["shooter_jersey"],
             *(h["spot"] or [None, None]), *(h["shooter"] or [None, None]),
             _kim.get(h["outcome"], "?"), _ir.get(h["irany"]),
             *(h["aim"] or [None, None]), *(h["keeper"] or [None, None]),
             h["keeper_depth"], *h["goal"], h["shot_s"]]
            for h in seven_meter_moments(match)["moments"]]
    except Exception:
        hetesek = []
    # Videózandó jelenetek: [mp, típus] párok (court3d.key_scene_rows — a
    # jelentés és a kezdőlap válogatása) — a jelenet-lista "Videózandó"
    # szűrője ezekre szűkít.
    try:
        from .court3d import key_scene_rows
        kulcs_jelenetek = [[r["s"], r["tipus"]]
                           for r in key_scene_rows(match)["rows"]]
    except Exception:
        kulcs_jelenetek = []
    # Feltörés: hol és mivel törhető fel a két csapat védekezése (a
    # felderítés rangsorának teteje) — a védekezés-panel a fal mellé írja.
    try:
        if breakpoints is None or stoppers is None:
            from .court3d import tactical_keys_by_team
            kulcsok = tactical_keys_by_team(match)
            breakpoints = breakpoints if breakpoints is not None \
                else kulcsok["breakpoints"]
            stoppers = stoppers if stoppers is not None \
                else kulcsok["stoppers"]
        feltores = {"home": list(breakpoints.get("home") or []),
                    "away": list(breakpoints.get("away") or [])}
        megallitas = {"home": list(stoppers.get("home") or []),
                      "away": list(stoppers.get("away") or [])}
    except Exception:
        feltores = {"home": [], "away": []}
        megallitas = {"home": [], "away": []}
    return {
        "match_id": match.meta.match_id,
        # A képráta: a jegyzetek kockában tárolódnak (a meccs-elemzővel
        # közös tár), az oldal másodpercben jár.
        "fps": match.meta.fps if match.meta.fps > 0 else 25.0,
        "home": match.meta.home_team,
        "away": match.meta.away_team,
        "frames": frames,
        "events": esemenyek,
        "formations": formak,
        "defence": fal,
        "shots": lovesek,
        "passes": passzok,
        "breakpoints": feltores,
        "stoppers": megallitas,
        "decisions": dontesek,
        "free_shots": szabadok,
        "free_radius": szabad_sugar,
        "turnovers": eladasok,
        "goal_build_ups": golakciok,
        "powerplays": emberek,
        "fast_breaks": kontrak,
        "conceded_goals": kapottak,
        "sevens": hetesek,
        "key_scenes": kulcs_jelenetek,
        "turnover_pressure": eladas_sugar,
    }


# A lövés-mérés a böngészőben — a `court3d.shot_geometry` PONTOS tükre
# (a teszt node-dal futtatja, és a Python-számokkal veti össze). Külön
# állandó, hogy a teszt az oldal nélkül is elérje.
LOVES_MERES_JS = """
function lovesMeres(x, y, kapu){
  // A court3d.shot_geometry tükre: a kapu közepének távolsága, a
  // kapufák közti szakasztól mért távolság (a 6 és 9 m-es vonal
  // mércéje), a két kapufa között látott kapu-szög és a sáv.
  if (kapu !== "bal" && kapu !== "jobb") kapu = x <= H/2 ? "bal" : "jobb";
  const gx = kapu === "bal" ? 0 : H, cy = W/2;
  const y1 = cy - KAPU_SZ/2, y2 = cy + KAPU_SZ/2;
  const v1x = gx - x, v1y = y1 - y, v2x = gx - x, v2y = y2 - y;
  const n1 = Math.hypot(v1x, v1y), n2 = Math.hypot(v2x, v2y);
  let szog = 180;
  if (n1 >= 1e-9 && n2 >= 1e-9){
    const c = (v1x*v2x + v1y*v2y) / (n1*n2);
    szog = Math.acos(Math.max(-1, Math.min(1, c))) * 180 / Math.PI;
  }
  const ny = Math.min(Math.max(y, y1), y2);
  const kapufa = Math.hypot(x - gx, y - ny);
  const sav = kapufa < 6 ? "kapuelőtér" : (kapufa < 9 ? "6–9 m" : "9 m-en túl");
  return {kapu, gx, tav: Math.hypot(x - gx, y - cy), kapufa, szog, sav};
}
"""


# A passzsávok a böngészőben — a `court3d.pass_lanes` PONTOS tükre (a
# decisions.pass_completion modellje; a teszt node-dal futtatja és a
# Python-számokkal veti össze). A konstansok a backendből jönnek.
PASSZSAV_JS = """
function passzSavok(jat, labda){
  // jat: [[hazai?, x, y], …]; labda: [x, y] | null. A court3d.pass_lanes
  // tükre: labdás a labdához legközelebbi, ha PS_SUGAR-on belül van;
  // csapattársanként a passz-esély a távolságból és a sávban (PS_SZEL)
  // álló ellenfelekből.
  if (!labda || !jat.length) return null;
  let h = null, hd = Infinity;
  for (const p of jat){
    const d = Math.hypot(p[1] - labda[0], p[2] - labda[1]);
    if (d < hd){ hd = d; h = p; }
  }
  if (hd > PS_SUGAR) return null;
  const szakasz = (px, py, ax, ay, bx, by) => {
    const dx = bx - ax, dy = by - ay, l2 = dx*dx + dy*dy;
    if (l2 === 0) return Math.hypot(px - ax, py - ay);
    let t = ((px - ax)*dx + (py - ay)*dy) / l2;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(px - (ax + t*dx), py - (ay + t*dy));
  };
  const lanes = [];
  for (const t of jat){
    if (t === h || !!t[0] !== !!h[0]) continue;
    const tav = Math.hypot(h[1] - t[1], h[2] - t[2]);
    const alap = Math.max(0.1, 1 - tav / 35);
    let blokk = 0;
    for (const o of jat){
      if (!!o[0] === !!h[0]) continue;
      if (szakasz(o[1], o[2], h[1], h[2], t[1], t[2]) <= PS_SZEL) blokk++;
    }
    const p = Math.max(0.05, Math.min(0.99, alap - 0.3 * blokk));
    const grade = p >= PS_JO ? "nyitott" : (p >= PS_KOCK ? "kockázatos" : "zárt");
    lanes.push({x: t[1], y: t[2], p, blockers: blokk, grade});
  }
  return {holder: [h[1], h[2], !!h[0]], lanes};
}
"""


# A fal-rések a böngészőben — a `court3d.wall_gap_segments` PONTOS tükre
# (a küszöböket a backend konstansaiból fűzzük elé, a teszt node-dal
# veti össze): a fal a mért, kapus nélküli védők a saját kaputól
# FR_MELY-en belül, y szerint (holtversenyben x szerint, mint a Python
# tuple-rendezése); a rés a szomszédok y-távolsága, a FR_RES-t elérő
# rés "széles"; a legnagyobb rés holtversenyben az első.
FALRES_JS = """
function falResek(jat, hazai, goalX){
  // jat: [[hazai (1/0), x, y, mért (1/0), kapus (1/0)], …]
  const fal = jat.filter(p => (!!p[0]) === hazai && p[3] && !p[4]
      && Math.abs(p[1] - goalX) <= FR_MELY)
    .map(p => [p[2], p[1]])
    .sort((a, b) => (a[0] - b[0]) || (a[1] - b[1]));
  if (fal.length < FR_MIN) return null;
  const resek = [], szeles = [];
  let maxI = 0;
  for (let i = 0; i + 1 < fal.length; i++){
    const g = fal[i + 1][0] - fal[i][0];
    resek.push(g); szeles.push(g >= FR_RES);
    if (g > resek[maxI]) maxI = i;
  }
  return {fal: fal.map(p => [p[1], p[0]]), resek, szeles, max: resek[maxI], maxI};
}
"""


# A pillanat-lapozó (Döntések, Szabad lövők ◀ ▶) közös logikája — külön
# állandó, hogy a teszt node-dal futtathassa. A "következő" az UTOLJÁRA
# ugrott pillanattól számít, amíg annak ablakában vagyunk (különben a
# lejátszófejtől): így az első 1,6 mp pillanatai is elérhetők, és a
# lapozó nem ragad le az épp nézett pillanaton.
LAPOZO_JS = """
function csoportUrit(cs){
  // A csoport elemeinek eltávolítása ÉS felszabadítása: a three.js a
  // levett geometriát és anyagot magától nem adja vissza — a képkockánként
  // újrarajzolt rétegek különben percenként ezreket szivárogtattak.
  while (cs.children.length){
    const o = cs.children[0];
    cs.remove(o);
    o.traverse(x => {
      if (x.geometry) x.geometry.dispose();
      // A közös ("tartós") anyagot nem: azt több réteg minden kockán
      // újra használja — felszabadítva a three.js a shader-programot is
      // eldobná, és a következő kockán újrafordítaná.
      const m = x.material;
      if (m) (Array.isArray(m) ? m : [m]).forEach(q => { if (!q.userData.tartos) q.dispose(); });
    });
  }
}
function lapozCel(idok, most, utolso, irany){
  // idok: a pillanatok ideje (mp), növekvő; utolso: az utoljára ugrott
  // pillanat ideje vagy null. Visszaad: a cél ideje vagy null.
  const benne = utolso !== null && most >= utolso - 1.6 && most <= utolso + 2.5;
  const alap = benne ? utolso : most;
  if (irany > 0){
    for (const s of idok){ if (benne ? s > alap + 1e-6 : s >= alap - 1e-6) return s; }
    return null;
  }
  for (let i = idok.length - 1; i >= 0; i--){
    if (benne ? idok[i] < alap - 1e-6 : idok[i] < alap - 0.5) return idok[i];
  }
  return null;
}
"""


# Az emberelőny-jelző szövege — tiszta függvény (a teszt node-dal
# futtatja): "Emberelőny: Szeged (Veszprém kiállítás miatt hiányos) ·
# még 1:12 · az előny alatt eddig 2–0".
EMBERELONY_JS = """
function emberSzoveg(d, t, nevH, nevV){
  const [s, e, downH, gu, gd, su, golok] = d;
  const elony = downH ? nevV : nevH, hatrany = downH ? nevH : nevV;
  const hatra = Math.max(0, Math.ceil(e - t));
  const ido = Math.floor(hatra / 60) + ":" + String(hatra % 60).padStart(2, "0");
  let fel = 0, le = 0;
  for (const [mp, h] of golok){
    if (mp > t) continue;
    if (!!h === !downH) fel++; else le++;
  }
  return "Emberelőny: " + elony + " (" + hatrany + " kiállítás miatt hiányos) · még " +
    ido + " · az előny alatt eddig " + fel + "–" + le;
}
"""


# A klip-munka állapot-szövege — tiszta függvény (a teszt node-dal
# futtatja): a /jobs válasz status/message mezőiből.
KLIPALLAPOT_JS = """
function klipAllapotSzoveg(job){
  if (!job) return "";
  if (job.status === "running") return "Klipek vágása… " + (job.message || "");
  if (job.status === "done") return job.message || "kész";
  return job.message || ("hiba: " + (job.error || "ismeretlen"));
}
"""


# A gól-akció felirata — tiszta függvény (a teszt node-dal futtatja):
# "Szeged gólja — #10 → #9 → … → #4 → #10 lő · 8 passz, 6,5 mp"; hosszú
# láncnál az első kettő és az utolsó két passzoló marad.
GOLAKCIO_JS = """
function golAkcioFelirat(d, nevH, nevV){
  const [s0, sg, hazai, lanc, lx, ly, lmez, gx, gy, n, hossz] = d;
  const m = (j) => j !== null && j !== undefined ? "#" + j : "?";
  let nevek = lanc.map(p => m(p[4]));
  if (nevek.length > 4) nevek = [...nevek.slice(0, 2), "…", ...nevek.slice(-2)];
  const lanct = nevek.length ? nevek.join(" → ") + " → " : "";
  const sz1 = (v) => v.toFixed(1).replace(".", ",");
  return (hazai ? nevH : nevV) + " gólja — " + lanct + m(lmez) + " lő · " +
    (n ? n + " passz, " + sz1(hossz) + " mp" : "passz nélkül");
}
"""


# A lerohanás felirata — tiszta függvény (a teszt node-dal futtatja):
# "Lerohanás (Szeged): #7 fejezi be · második hullám · elszökött emberrel
# · 4,2 mp · GÓL"; a hiányzó részek (lövő, hullám, elszökés) kimaradnak.
# A sor 2. eleme a VÉDEKEZŐ csapat — a támadó a másik.
KONTRA_JS = """
function kontraFelirat(d, nevH, nevV){
  const [s, defHazai, mez, hullam, elszokott, hossz, kimenet] = d;
  const reszek = [];
  if (mez !== null && mez !== undefined) reszek.push("#" + mez + " fejezi be");
  if (hullam === "e") reszek.push("első ember");
  if (hullam === "m") reszek.push("második hullám");
  if (elszokott === 1) reszek.push("elszökött emberrel");
  if (elszokott === 0) reszek.push("együtt felfutva");
  reszek.push(hossz.toFixed(1).replace(".", ",") + " mp");
  reszek.push(kimenet === "g" ? "GÓL" : kimenet === "l" ? "lövés" : "lövés nélkül");
  return "Lerohanás (" + (defHazai ? nevV : nevH) + "): " + reszek.join(" · ");
}
"""


# A kapott gól felirata — tiszta függvény (a teszt node-dal futtatja):
# "Kapott gól (Veszprém): Szeged #10 · 9 m-en túl, kapu-szög 13,8° · védő
# 6,2 m-re — szabadon · kapus 0,9 m-re a vonalon · xG 0,09". A sor 2.
# eleme a VÉDEKEZŐ csapat — a lövő a másik.
KAPOTT_JS = """
function kapottFelirat(d, nevH, nevV){
  const [s, defHazai, mez, lx, ly, sav, szog, tav, dx, dy, dtav, szabad, kx, ky, mely, kint, xg] = d;
  const sz1 = (v) => v.toFixed(1).replace(".", ",");
  const SAV = ["kapuelőtér", "6–9 m", "9 m-en túl"];
  const reszek = [
    (defHazai ? nevV : nevH) + (mez !== null && mez !== undefined ? " #" + mez : ""),
    SAV[sav] + ", kapu-szög " + sz1(szog) + "°",
    dtav === null ? "védő nem mérhető" : "védő " + sz1(dtav) + " m-re" + (szabad === 1 ? " — szabadon" : ""),
    mely === null ? "kapus nem mérhető" : "kapus " + sz1(mely) + " m-re " + (kint === 1 ? "kint" : "a vonalon"),
    "xG " + xg.toFixed(2).replace(".", ",")];
  return "Kapott gól (" + (defHazai ? nevH : nevV) + "): " + reszek.join(" · ");
}
"""


# A hétméteres felirata — tiszta függvény (a teszt node-dal futtatja):
# "Hetes (Szeged): #7 · középre · GÓL · kapus 0,9 m-re a kaputól".
HETES_JS = """
function hetesFelirat(d, nevH, nevV){
  const [s, hazai, mez, px, py, lx, ly, kim, ir, cx, cy, kx, ky, mely] = d;
  const IRANY = ["balra", "középre", "jobbra"];
  const KIM = {g: "GÓL", v: "védés", k: "kihagyva"};
  const reszek = [];
  if (mez !== null && mez !== undefined) reszek.push("#" + mez);
  if (ir !== null && ir !== undefined) reszek.push(IRANY[ir]);
  reszek.push(KIM[kim] || "kimenet ismeretlen");
  reszek.push(mely === null || mely === undefined ? "kapus nem mérhető"
    : "kapus " + mely.toFixed(1).replace(".", ",") + " m-re a kaputól");
  return "Hetes (" + (hazai ? nevH : nevV) + "): " + reszek.join(" · ");
}
"""


# A rajz-eszköz tiszta függvényei (a teszt node-dal futtatja): a nyílhegy
# szárnypontjai és a link "rajz" paraméterének kódolása. A nyilak
# pálya-méterben ([x1, y1, x2, y2, színkód]); a link 0,1 m-re kerekít, és
# legfeljebb RAJZ_MAX nyilat visz (a cím hossza miatt).
# DÖNTÉS-KVÍZ: a kvíz-válasz ítélete egy döntés-pillanatnál —
# court3d.quiz_verdict tükre (őr-teszt: node-dal ugyanazokon az eseteken).
# A döntés-sor a DONTESEK alakja: [mp, hazai?, passzoló x, y, választott
# x, y, érték, "s"/"p", a jobb cél x, y, érték, különbség].
KVIZ_JS = """
const KV_TALALAT = __KV_TALALAT__, KV_LOVES = __KV_LOVES__;
function kvizItelet(vx, vy, d){
  const cx = d[4], cy = d[5], fajta = d[7], bx = d[8], by = d[9];
  const db = Math.hypot(vx - bx, vy - by), dc = Math.hypot(vx - cx, vy - cy);
  return db < dc && db <= (fajta === "s" ? KV_LOVES : KV_TALALAT);
}
// A kvíz eredménye jegyzet-szövegként: valaszok = [[név, ítélet (true/
// false/null)], …] a csatlakozás sorrendjében; fajta: a jobb opció ("s"
// lövés, "p" passz; null: nem döntés-kvíz); hianyzik: a nem válaszolók
// száma. Az app (court_geometry.quizNoteText) ugyanezt írja.
function kvizJegyzetSzoveg(valaszok, fajta, hianyzik){
  const nevek = (f) => valaszok.filter(v => f(v[1])).map(v => v[0]).join(", ");
  const r = [];
  if (fajta){
    const jo = nevek(i => i === true), rossz = nevek(i => i === false);
    if (jo) r.push("✓ " + jo);
    if (rossz) r.push("✗ " + rossz);
  } else if (valaszok.length) r.push("válaszolt: " + nevek(() => true));
  if (hianyzik > 0) r.push("nem válaszolt: " + hianyzik);
  return (fajta ? "❓ Döntés-kvíz (jobb opció: " + (fajta === "s" ? "lövés" : "passz") + ")" : "❓ Kvíz")
    + (r.length ? " — " + r.join(" · ") : "");
}
"""

RAJZ_JS = """
const RAJZ_SZINEK = ["ffd23f", "4c9aff", "ff6b6b"];  // labda/passz, futás, védő
const RAJZ_MAX = 30;
const RAJZ_MIN_M = 0.6;  // ennél rövidebb húzás nem nyíl (elcsúszott katt)
function nyilFej(x1, y1, x2, y2, hossz, szel){
  // A nyílhegy két szárnypontja: a csúcs (x2, y2), a szárak hossz méterrel
  // vissza a nyíl tengelyén, onnan ±szel/2 oldalra.
  const d = Math.hypot(x2 - x1, y2 - y1) || 1;
  const ux = (x2 - x1) / d, uy = (y2 - y1) / d;
  const bx = x2 - ux * hossz, by = y2 - uy * hossz;
  return [[bx - uy * szel / 2, by + ux * szel / 2],
          [bx + uy * szel / 2, by - ux * szel / 2]];
}
function rajzKodol(rajzok){
  // [[x1, y1, x2, y2, k]] → "x1,y1,x2,y2,k;…" (0,1 m-re kerekítve).
  return rajzok.slice(0, RAJZ_MAX).map(r =>
    r.slice(0, 4).map(v => String(Math.round(v * 10) / 10)).join(",") + "," + r[4]).join(";");
}
function rajzDekodol(s){
  // A link "rajz" paramétere → nyilak; a hibás vagy pályán kívüli tag
  // kimarad, legfeljebb RAJZ_MAX nyíl.
  const ki = [];
  for (const tag of String(s || "").split(";")){
    const p = tag.split(",");
    // Csak a kódoló számalakja (-12.3; szín: egész) — a Number() a "",
    // "1e1", "0x10", "1.0" alakot is elfogadná, a Dart és a Python tükör
    // nem (ugyanez a szabály mindhárom helyen).
    if (p.length !== 5 || !p.slice(0, 4).every(x => /^-?[0-9]+(\\.[0-9]+)?$/.test(x.trim()))
        || !/^[0-9]+$/.test(p[4].trim())) continue;
    const v = p.slice(0, 4).map(Number);
    const k = Number(p[4]);
    if (v.some(x => !isFinite(x) || x < -10 || x > 50)) continue;
    if (!Number.isInteger(k) || k < 0 || k >= RAJZ_SZINEK.length) continue;
    if (Math.hypot(v[2] - v[0], v[3] - v[1]) < RAJZ_MIN_M) continue;
    ki.push([...v, k]);
    if (ki.length >= RAJZ_MAX) break;
  }
  return ki;
}
"""


# A jelenet-lista sorai: a jelenet-lapozók (Döntések, Szabad lövők,
# Labdavesztések, Lerohanások, Kapott gólok) jelenetei EGY időrendi
# listában, rövid magyar felirattal — tiszta függvény, hogy a teszt
# node-dal futtathassa.
JELENETLISTA_JS = """
function jelenetSorok(dontesek, szabadok, eladasok, nevH, nevV, lerohanasok, kapottak){
  // A tömör adat soraiból: [{s, ido ("p:mm"), tipus ("d"/"sz"/"e"/"k"/"kg"),
  // szoveg, gol}] időrendben; holtversenyben döntés, szabad lövés,
  // labdavesztés, kapott lerohanás, kapott gól sorrendben. A lerohanás és
  // a kapott gól a VÉDEKEZŐ csapat sora ("kinek a hibája"); a kapott gól
  // sora elmarad, ha ugyanarra a pillanatra szabad lövő GÓL-sor van.
  const sz1 = (v) => v.toFixed(1).replace(".", ",");
  const csapat = (h) => h ? nevH : nevV;
  const ido = (s) => { const t = Math.max(0, Math.floor(s));
    return Math.floor(t / 60) + ":" + String(t % 60).padStart(2, "0"); };
  const HARMAD = ["saját", "középső", "támadó"];
  const sorok = [];
  for (const d of dontesek){
    sorok.push({s: d[0], tipus: "d", gol: false,
      szoveg: csapat(d[1]) + " — jobb opció is volt: " +
        (d[7] === "s" ? "lövés" : "passz egy szabadabb társhoz")});
  }
  for (const d of szabadok){
    sorok.push({s: d[0], tipus: "sz", gol: !!d[7],
      szoveg: csapat(d[1]) + " védekezése — szabad lövő" +
        (d[6] !== null ? " (" + sz1(d[6]) + " m)" : "") + (d[7] ? " · GÓL" : "")});
  }
  for (const d of eladasok){
    sorok.push({s: d[0], tipus: "e", gol: d[12] !== null,
      szoveg: csapat(d[1]) + " — labdavesztés" + (d[2] !== null ? " #" + d[2] : "") +
        (d[7] !== null ? " (" + HARMAD[d[7]] + " harmad)" : "") +
        (d[12] !== null ? " · gól lett belőle" : "")});
  }
  for (const d of (lerohanasok || [])){
    const gol = d[6] === "g";
    sorok.push({s: d[0], tipus: "k", gol,
      szoveg: csapat(d[1]) + " védekezése — kapott lerohanás: " + csapat(!d[1]) +
        (d[2] !== null ? " #" + d[2] : "") +
        (gol ? " · GÓL" : d[6] === "l" ? " · lövés" : " · lövés nélkül")});
  }
  const szabadGolIdok = szabadok.filter(d => d[7]).map(d => d[0]);
  const SAV = ["kapuelőtér", "6–9 m", "9 m-en túl"];
  const JL_AZONOS_S = 0.05;  // court3d.SCENE_SAME_MOMENT_S tükre (őr-teszt)
  for (const d of (kapottak || [])){
    if (szabadGolIdok.some(s0 => Math.abs(d[0] - s0) < JL_AZONOS_S)) continue;
    sorok.push({s: d[0], tipus: "kg", gol: true,
      szoveg: csapat(d[1]) + " védekezése — kapott gól: " + csapat(!d[1]) +
        (d[2] !== null ? " #" + d[2] : "") + " (" + SAV[d[5]] + ")" +
        (d[10] !== null ? " · védő " + sz1(d[10]) + " m" : "") +
        (d[14] === null ? "" : d[15] === 1 ? " · kapus kint" : " · kapus a vonalon")});
  }
  const REND = {d: 0, sz: 1, e: 2, k: 3, kg: 4};
  sorok.sort((a, b) => (a.s - b.s) || (REND[a.tipus] - REND[b.tipus]));
  for (const r of sorok) r.ido = ido(r.s);
  return sorok;
}
"""


def view3d_html(match: Match, figure_alerts: list | None = None,
                breakpoints: dict | None = None,
                stoppers: dict | None = None) -> str:
    """A teljes, önálló HTML-oldal (three.js a motorból, adat beágyazva)."""
    # A "</" a <script>-ben nem maradhat nyersen: egy "</script>"-et
    # tartalmazó csapatnév (a könyvtár-import más gépről is hozhat ilyet)
    # kitörne a szkriptből. JSON-ban "</" csak szövegben állhat, ott a
    # "<\/" ugyanazt jelenti.
    adat = json.dumps(_compact_data(match, figure_alerts, breakpoints,
                                    stoppers),
                      ensure_ascii=False, separators=(",", ":")).replace(
                          "</", "<\\/")
    cim = f"{match.meta.home_team} vs {match.meta.away_team} — 3D"
    # Nem f-string: a JS tele van kapcsos zárójellel; a beszúrás
    # helyőrző-cserével megy.
    oldal = """<!DOCTYPE html>
<html lang="hu"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>__CIM__</title>
<style>
 body{margin:0;background:#0a0e14;color:#dfe7ef;font-family:system-ui,sans-serif;overflow:hidden}
 #hud{position:fixed;left:12px;top:10px;font-size:13px;opacity:.9}
 #vez{position:fixed;left:12px;bottom:12px;right:12px;display:flex;gap:10px;align-items:center}
 #ido{font-variant-numeric:tabular-nums}
 input[type=range]{flex:1}
 button{background:#173042;color:#dfe7ef;border:1px solid #2b4a5e;border-radius:8px;padding:6px 12px;cursor:pointer}
 #sugo{position:fixed;right:12px;top:36px;font-size:11.5px;opacity:.7;text-align:right;max-width:min(62vw,900px)}
 /* A súgó gombbal csukható: keskeny ablakban (1200 px alatt) alapból
    csukva — nyitva a pálya jobb harmadát takarta. */
 #sugoGomb{position:fixed;right:12px;top:8px;padding:3px 10px;font-size:11.5px;opacity:.85}
 /* A vezérlőpanel összecsukható (☰ / M): kivetítőn, kis ablakban a pálya
    nagyját takarta. */
 #panelGomb{padding:1px 8px;font-size:12px;margin-right:6px}
 #eszkoz.csukva{display:none}
 #felirat{position:fixed;left:12px;bottom:56px;padding:6px 12px;border:1px solid #d9b544;border-radius:8px;background:rgba(16,24,32,.85);color:#d9b544;font-weight:600;font-size:15px;display:none}
 /* A panel a lejátszó-sáv fölött véget ér és görgethető: a rétegek
    szaporodtával alacsony ablakban (1024×600) a sáv alá lógott, és az
    alsó gombok (Link másolása) nem voltak kattinthatók. */
 #eszkoz{position:fixed;left:12px;top:34px;display:flex;flex-direction:column;gap:6px;align-items:flex-start;font-size:12.5px;max-width:330px;max-height:calc(100vh - 110px);overflow-y:auto;overflow-x:hidden;padding-right:4px;scrollbar-width:thin}
 #eszkoz .sor{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
 select{background:#173042;color:#dfe7ef;border:1px solid #2b4a5e;border-radius:8px;padding:5px 8px}
 button.be{background:#2f86d6;border-color:#2f86d6;color:#fff}
 #falInfo,#lovesInfo{opacity:.92;line-height:1.35}
 #meres{position:fixed;left:12px;bottom:100px;padding:8px 12px;border:1px solid #2f86d6;border-radius:8px;background:rgba(16,24,32,.88);font-size:13.5px;display:none;line-height:1.45}
 #meres button{margin-left:8px;padding:2px 8px}
 #feliratOszlop{position:fixed;left:50%;top:52px;transform:translateX(-50%);display:flex;flex-direction:column;align-items:center;gap:6px;max-width:70vw;pointer-events:none}
 #dontesFelirat{padding:6px 14px;border:1px solid #d9b544;border-radius:8px;background:rgba(16,24,32,.88);font-size:13.5px;display:none;max-width:70vw;text-align:center}
 #szabadFelirat{padding:6px 14px;border:1px solid #ff6b6b;border-radius:8px;background:rgba(16,24,32,.88);font-size:13.5px;display:none;max-width:70vw;text-align:center}
 #jelenetLista{position:fixed;right:12px;top:40px;width:380px;max-height:calc(100vh - 170px);overflow-y:auto;padding:6px;border:1px solid #2b4a5e;border-radius:8px;background:rgba(16,24,32,.94);font-size:12.5px;display:none}
 #jelenetLista .jfej{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:2px 6px 8px;border-bottom:1px solid #2b4a5e;margin-bottom:4px}
 #jegyzetFelirat{padding:6px 14px;border:1px solid #e8eef5;border-radius:8px;background:rgba(16,24,32,.88);font-size:13.5px;display:none;max-width:70vw;text-align:center}
 #jelenetLista .jtorol{margin-left:auto;opacity:.6;padding:0 4px;cursor:pointer}
 #jelenetLista .jtorol:hover{opacity:1;color:#ff6b6b}
 #videoAblak{position:fixed;right:12px;bottom:150px;width:320px;border:1px solid #2b4a5e;border-radius:8px;background:#000;display:none;overflow:hidden;z-index:5}
 #videoAblak img{display:block;width:100%}
 #videoInfo{position:absolute;left:6px;bottom:4px;font-size:11px;color:#dfe7ef;text-shadow:0 0 3px #000}
 #vetitesJelzo{padding:4px 12px;border:1px solid #2f86d6;border-radius:8px;background:rgba(16,24,32,.88);color:#9fd0ff;font-size:12.5px;display:none}
 #jelenetLista .jfej .n{flex:1;opacity:.85}
 #jelenetLista .jfej button{padding:3px 9px;font-size:11.5px}
 #jelenetLista .jfej .kulcs{font-size:11.5px;white-space:nowrap;opacity:.9}
 #klipInfo{font-size:11px;opacity:.9;max-width:170px;text-align:right}
 #klipLetolt{color:#2fd9c4;font-size:11.5px}
 #jelenetLista .jsor{padding:4px 6px;border-radius:6px;cursor:pointer;display:flex;gap:7px;align-items:center}
 #jelenetLista .jsor:hover{background:#173042}
 #jelenetLista .jsor.aktiv{background:#2f86d6;color:#fff}
 #jelenetLista .jido{font-variant-numeric:tabular-nums;opacity:.8;min-width:38px}
 #jelenetLista .jpont{width:9px;height:9px;border-radius:50%;flex:none}
 #emberJelzo{position:fixed;left:50%;bottom:72px;transform:translateX(-50%);padding:6px 12px;border:1px solid #ffc857;border-radius:8px;background:rgba(16,24,32,.88);color:#ffc857;font-size:13px;display:none}
 #golFelirat{padding:6px 14px;border:1px solid #2fd9c4;border-radius:8px;background:rgba(16,24,32,.88);font-size:13.5px;display:none;max-width:70vw;text-align:center}
 #hetesFelirat{padding:6px 14px;border:1px solid #7dd3fc;border-radius:8px;background:rgba(16,24,32,.88);font-size:13.5px;display:none;max-width:70vw;text-align:center}
 #kapottFelirat{padding:6px 14px;border:1px solid #c084fc;border-radius:8px;background:rgba(16,24,32,.88);font-size:13.5px;display:none;max-width:70vw;text-align:center}
 #kontraFelirat{padding:6px 14px;border:1px solid #59d98c;border-radius:8px;background:rgba(16,24,32,.88);font-size:13.5px;display:none;max-width:70vw;text-align:center}
 #eladasFelirat{padding:6px 14px;border:1px solid #ff9f43;border-radius:8px;background:rgba(16,24,32,.88);font-size:13.5px;display:none;max-width:70vw;text-align:center}
 #jatekosHud{position:fixed;left:50%;top:12px;transform:translateX(-50%);padding:6px 14px;border:1px solid #2f86d6;border-radius:8px;background:rgba(16,24,32,.85);font-size:14px;font-variant-numeric:tabular-nums;display:none}
</style></head><body>
<div id="hud"><button id="panelGomb" title="A vezérlőpanel elrejtése / visszahozása (M) — a pálya teljes képe">☰</button><b>__CIM__</b></div>
<div id="eszkoz">
 <div class="sor">
  <button id="keringGomb" title="Keringés a pálya körül (O)">Keringés</button>
  <button id="tvGomb" title="TV-kamera: az oldalvonal felől, a labdát követve (T)">TV-kamera</button>
  <button id="jatekosKi" style="display:none" title="Vissza a szabad nézetbe (Esc)">Játékos-nézet ✕</button>
  <select id="jatekosKamera" title="Játékos-kamera: a kamera egy mezszámot követ hátulról (az appbeli Játékos-kamera párja)">
   <option value="">Játékos-kamera: ki</option>
  </select>
 </div>
 <div class="sor">
  <label>Védekezés
   <select id="fal">
    <option value="">ki</option>
    <option value="elo">élő — a mostani fal</option>
    <option value="6-0">6-0 sablon</option>
    <option value="5-1">5-1 sablon</option>
    <option value="4-2">4-2 sablon</option>
    <option value="3-2-1">3-2-1 sablon</option>
   </select></label>
  <select id="falOldal" title="Melyik kapu elé">
   <option value="auto">a védett kapu</option>
   <option value="bal">bal kapu</option>
   <option value="jobb">jobb kapu</option>
  </select>
 </div>
 <div id="falInfo"></div>
 <div class="sor">
  <label>Lövéstérkép
   <select id="lovesek" title="A meccs lövései a padlón; katt egy körre — odaugrik">
    <option value="">ki</option>
    <option value="mind">mind</option>
    <option value="eddig">eddig (a lejátszásig)</option>
    <option value="hazai">csak hazai</option>
    <option value="vendeg">csak vendég</option>
   </select></label>
 </div>
 <div id="lovesInfo"></div>
 <div class="sor">
  <label>Passzok
   <select id="passz" title="A futó passz vonala, vagy a csapat minden passza a padlón">
    <option value="">ki</option>
    <option value="elo">élő — a futó passz</option>
    <option value="hazai">hazai passz-háló</option>
    <option value="vendeg">vendég passz-háló</option>
   </select></label>
  <span id="passzInfo"></span>
 </div>
 <div class="sor">
  <label>Hőtérkép
   <select id="hoter" title="Hol tartózkodott a csapat a meccsen (mért helyek, 2 m-es cellák)">
    <option value="">ki</option>
    <option value="hazai">hazai</option>
    <option value="vendeg">vendég</option>
    <option value="mind">mindkettő</option>
   </select></label>
 </div>
 <div class="sor">
  <button class="nezet" data-n="lelato">Lelátó</button>
  <button class="nezet" data-n="kapu">Kapu mögül</button>
  <button class="nezet" data-n="palya">Pálya-szint</button>
  <button class="nezet" data-n="madar">Madártávlat</button>
 </div>
 <div class="sor">
  <label title="A jelenet-lapozók (Döntések, Szabad lövők, Labdavesztések, Lerohanások, Kapott gólok) csak ennek a csapatnak a hibáit mutatják: a rossz döntést, a szabadon hagyott lövőt, az elvesztett labdát, a kapott lerohanást, a kapott gólt">Kinek a hibái: <select id="jelenetCsapat"><option value="mind">mindkét csapat</option><option value="hazai">hazai</option><option value="vendeg">vendég</option></select></label>
  <button id="jelenetGomb" title="A jelenet-lapozók összes jelenete egy időrendi listában — katt egy sorra: odaugrik">Jelenet-lista</button>
 </div>
 <div class="sor">
  <span title="Passz-döntések, ahol a modell szerint jobb opció is volt">Döntések:</span>
  <button id="dontesElozo" title="Előző döntés-pillanat">◀</button>
  <button id="dontesKov" title="Következő döntés-pillanat">▶</button>
  <span id="dontesInfo"></span>
 </div>
 <div class="sor">
  <span title="Kapott lövések, ahol a lövőtől 2 m-en belül nem volt védő">Szabad lövők:</span>
  <button id="szabadElozo" title="Előző szabadon hagyott lövő">◀</button>
  <button id="szabadKov" title="Következő szabadon hagyott lövő">▶</button>
  <span id="szabadInfo"></span>
 </div>
 <div class="sor">
  <span title="Elvesztett labdák: ki, hol, kipréselve vagy magától, és gól lett-e belőle">Labdavesztések:</span>
  <button id="eladasElozo" title="Előző labdavesztés">◀</button>
  <button id="eladasKov" title="Következő labdavesztés">▶</button>
  <span id="eladasInfo"></span>
 </div>
 <div class="sor">
  <span title="A gólok előkészítése: a gólt megelőző saját passz-lánc, a lövéssel">Gól-akciók:</span>
  <button id="golElozo" title="Előző gól-akció">◀</button>
  <button id="golKov" title="Következő gól-akció">▶</button>
  <span id="golInfo"></span>
 </div>
 <div class="sor">
  <span title="Kiállítás miatti emberelőny-szakaszok: ki van hátrányban, meddig, és mi történt közben">Emberelőny:</span>
  <button id="emberElozo" title="Előző emberelőny">◀</button>
  <button id="emberKov" title="Következő emberelőny">▶</button>
  <span id="emberInfo"></span>
 </div>
 <div class="sor">
  <span title="Lerohanások: a befejező útja az indulástól a lövésig, első ember vagy második hullám, elszökött emberrel vagy együtt felfutva, és mi lett belőle">Lerohanások:</span>
  <button id="kontraElozo" title="Előző lerohanás">◀</button>
  <button id="kontraKov" title="Következő lerohanás">▶</button>
  <span id="kontraInfo"></span>
 </div>
 <div class="sor">
  <span title="Kapott gólok: ki lőtte, honnan (sáv, kapu-szög), a legközelebbi védő, a kapus mélysége, xG — minden kapott gól egy helyen">Kapott gólok:</span>
  <button id="kapottElozo" title="Előző kapott gól">◀</button>
  <button id="kapottKov" title="Következő kapott gól">▶</button>
  <span id="kapottInfo"></span>
 </div>
 <div class="sor">
  <span title="Hétméteresek: a dobó, a célzott kapu-harmad, a kimenet és a kapus helye">Hétméteresek:</span>
  <button id="hetesElozo" title="Előző hétméteres">◀</button>
  <button id="hetesKov" title="Következő hétméteres">▶</button>
  <span id="hetesInfo"></span>
 </div>
 <div class="sor">
  <button id="rajzGomb" title="Rajz (E): húzással nyíl a padlóra — a link viszi, VR-ben is látszik">✎ Rajz</button>
  <select id="rajzSzin" title="A nyíl színe">
   <option value="0">sárga — labda, passz</option>
   <option value="1">kék — futás</option>
   <option value="2">piros — védő</option>
  </select>
  <button id="rajzVissza" title="Az utolsó nyíl vissza">↶</button>
  <button id="rajzTorles" title="Minden nyíl törlése">Törlés</button>
  <span id="rajzInfo"></span>
 </div>
 <div class="sor">
  <button id="vezetGomb" title="Közös nézés — te vezetsz: a lejátszásod (idő, szünet, sebesség, rajz) a csapat headsetjein is fut; a csapat linkje a vágólapra kerül">📡 Vezetem</button>
  <button id="ideGomb" title="Ide mindenki: a követők kamerája a te mostani nézőpontodba ugrik (hely és irány) — pl. mindenki a kapus helyére. Csak vezetés közben" disabled>📍 Ide mindenki</button>
  <button id="kvizGomb" title="Kvíz a csapatnak: a jelenet megáll, a játékosok a padlóra mutatnak (hova passzolnál? hol a helyed?) — te névvel látod a válaszokat; másodszorra a csapatnak is megmutatod, harmadszorra vége — az eredmény a jegyzetek közé kerül. Csak vezetés közben" disabled>❓ Kvíz</button>
  <button id="felvetelGomb" title="Felvétel: a megbeszélés (a lejátszásod, a rajz, a mutató, a nézőpontok — és a hangod, ha a mikrofont engeded) visszanézhető — vezetés közben indítod, a végén a motor menti; a ▶ Felvételek listából bárki visszajátszhatja (VR-ben is)" disabled>⏺ Felvétel</button>
  <select id="felvetelValaszto" style="display:none" title="A mentett megbeszélések visszajátszása — mintha az edző most vezetne (VR-ben is)"></select>
  <select id="fejezetValaszto" style="display:none" title="A felvétel fejezetei — ahol az edző egy másik jelenetre ugrott (N / P: következő / előző; VR-ben A/X — B/Y)"></select>
  <select id="kzNevValaszto" style="display:none" title="Ki vagy? A neved a többiek headsetjén és a kvíz-mérlegben — a keretben felvitt nevek közül"></select>
  <button id="kovetGomb" title="Közös nézés — az edzőt követed: az ő lejátszása fut nálad, te a saját helyedről nézed (a pálya bejárható)">👥 Követem</button>
  <button id="kezGomb" style="display:none" title="Kérdésem van: az edző a fejed fölött, a felirat-sorban és VR-ben a tábláján látja (✋) — még egyszer: kéz le. Billentyű: H; VR-ben a markolat">✋ Kérdésem van</button>
  <span id="kozosInfo" style="font-size:11px;word-break:break-all"></span>
 </div>
 <div class="sor">
  <button id="videoGomb" title="Videó (K): a valódi felvétel a 3D mellett, szinkronban — kép a képben, és kivetítő a túlsó oldalvonal fölött (VR-ben is)">📺 Videó</button>
 </div>
 <div class="sor">
  <button id="jegyzetGomb" title="Jegyzet a mostani pillanathoz (J) — a jelenet-listába, a vetítésbe, a nyomtatott jelentésbe és a Klipek jegyzet-csomagjába kerül">📝 Jegyzet</button>
  <span id="jegyzetInfo"></span>
 </div>
 <div class="sor">
  <button id="linkGomb" title="Link a mostani jelenetre: idő, kamera-állás, bekapcsolt rétegek — megosztható">Link másolása</button>
  <span id="linkInfo"></span>
 </div>
</div>
<button id="sugoGomb" title="Billentyűk és rétegek — a súgó ki/be">Súgó ▴</button>
<div id="sugo">Húzás — körülnézés · WASD — mozgás · R/F (C) — fel/le · Shift — gyors<br>
Görgetés — előre ugrás (keringésben: közelítés) · O — keringés a pálya körül<br>
Dupla katt egy játékosra — az ő szemével, vele együtt (Esc kilép); fent: a sebessége és a megtett útja<br>
Játékos-kamera — egy mezszám hátulról, simítva követve (húzás/WASD visszavált)<br>
T — TV-kamera: az oldalvonal felől, a labdát követve (mint a közvetítés)<br>
Katt a padlóra — lövés-mérés (távolság, kapu-szög) · Szóköz — lejátszás<br>
Lövéstérkép: katt egy körre — odaugrik a lövéshez (kör = xG, arany gyűrű = gól)<br>
Lent: sebesség (0,5–4×) · Labda-nyom — a labda útja az utolsó 3 mp-ben<br>
Hőtérkép — hol tartózkodott a csapat (2 m-es cellák) · Nézet-gombok — kész kamera-állások<br>
Passzok — a futó passz vonala (adótól a fogadóig), vagy a csapat passz-hálója a padlón<br>
Passzsávok — a labdástól a társakig: zöld nyitott, sárga kockázatos, piros zárt (az elemzés modellje)<br>
Fal-rések — a védőfal szomszédos védői közt: zöld zárt, piros a 3,5 m-es rés (ott nyílik a fal)<br>
Döntések ◀ ▶ — ahol jobb opció is volt: fehér a választott passz, arany a jobb (passz vagy lövés)<br>
Szabad lövők ◀ ▶ — a fedezés-hibák: piros kör a lövő körül (2 m), vonal a legközelebbi védőhöz<br>
Labdavesztések ◀ ▶ — narancs kör a vesztő körül (a nyomás-sugár), vonal a legközelebbi ellenfélhez, X a labdánál<br>
Gól-akciók ◀ ▶ — a gólt megelőző passz-lánc (a régebbi passz halványabb), arany vonal a lövéstől a kapuig<br>
Emberelőny ◀ ▶ — a kiállítások szakaszai; közben lent középen élő jelző: ki van előnyben, mennyi van hátra, mi az állás az előny alatt<br>
Lerohanások ◀ ▶ — a befejező útja az indulástól a lövésig (a csapat színével, pont fél mp-enként), fehér az indítópassz, arany vonal a kapura<br>
Hétméteresek ◀ ▶ — X a 7 m-es ponton, arany vonal a célzott kapu-harmadba, a kapus helye és mélysége lilával<br>
Kapott gólok ◀ ▶ — minden kapott gól a védekezés olvasatával: gyűrű a lövő körül, vonal a legközelebbi védőhöz (piros, ha szabadon lőtt), a kapus helye és mélysége lilával, arany vonal a kapura<br>
Kinek a hibái — a jelenet-lapozók csak az egyik csapat hibáit mutatják (a saját vagy az ellenfélé)<br>
Jelenet-lista — a lapozók jelenetei egy időrendi listában; katt egy sorra: odaugrik · Klipek: a jelenetek videóként (zip)<br>
Vezetem / Követem — közös nézés: az edző lejátszása (idő, szünet, sebesség, rajz) a csapat headsetjein is fut, mindenki a saját helyéről nézi; vezetőként Shift+katt a padlóra: mutató a csapatnak, 📍 Ide mindenki: a követők a te nézőpontodba ugranak; a csarnokban látjátok egymást (fej és orr a nézés irányába, az edzőé arany; név a /kovet?nev=Peti linkkel); ⏺ Felvétel: a megbeszélés visszanézhető, 🎙 a hangoddal is (▶ Felvételek — VR-ben is); ❓ Kvíz: a jelenet megáll, a játékosok a padlóra mutatnak (kattintás, VR-ben ravasz), te névvel látod, másodszorra a csapat is; döntés-pillanatnál (Döntések ◀ ▶) a válasz ✓/✗ a modell jobb opciójához mérve (a csapat linkje: kovet=1; a headset USB-n — adb reverse — vagy a klub hálózatán éri el a motort, lásd docs/3D_PALYA.md)<br>
Videó (K) — a valódi felvétel a 3D mellett, a lejátszással szinkronban: kép a képben és kivetítő a túlsó oldalvonal fölött (VR-ben is)<br>
Jegyzet (J) — megjegyzés a mostani pillanathoz: a jelenet-listában (fehér pötty, ✕ törli), a vetítésben, a jelentésben és a Klipek jegyzet-csomagjában<br>
Rajz (E) — húzással nyíl a padlóra: sárga a labda/passz, kék a futás, piros a védő; ↶ vissza, Törlés; a link és a VR is viszi<br>
Link másolása — a mostani jelenet (idő, kamera, rétegek, rajz) megosztható címként<br>
[ / ] — előző / következő esemény (gól, lövés, eladás) · N / P — következő / előző jelenet (a jelenet-lista sorai) · V — vetítés: a lista sorai egymás után<br>
VR-headsetben: a lenti "ENTER VR" gomb — a jelenet-feliratok a szem előtt; kontroller: bal kar — mozgás, jobb kar oldalra — 30°-os fordulás; A/X — következő jelenet (felvétel visszajátszásakor: fejezet), B/Y — előző, ravasz — lejátszás/szünet, hüvelykujj-kar lenyomása — vetítés; felvétel visszajátszásakor a ravasz szünet/tovább; kvíz közben a ravasz a válaszod (ahova a kontroller mutat); közös nézés követőként: markolat — ✋ kérdésem van; vezetőként: markolat — jobb kéz mutató (ahova a kontroller mutat), bal kéz Ide mindenki; bal hüvelykujj-kar lenyomása — kvíz (indítás, mutasd a csapatnak, vége)</div>
<div id="meres"></div>
<div id="jatekosHud"></div>
<div id="feliratOszlop">
 <div id="vetitesJelzo"></div>
 <div id="jegyzetFelirat"></div>
 <div id="dontesFelirat"></div>
 <div id="szabadFelirat"></div>
 <div id="eladasFelirat"></div>
 <div id="golFelirat"></div>
 <div id="kontraFelirat"></div>
 <div id="kapottFelirat"></div>
 <div id="hetesFelirat"></div>
</div>
<div id="emberJelzo"></div>
<div id="videoAblak"><img id="videoKep" alt=""><span id="videoInfo"></span></div>
<div id="jelenetLista"></div>
<div id="felirat"></div>
<div id="vez">
 <button id="elozo" title="Előző esemény">⏮</button>
 <button id="lejatszas">▶</button>
 <button id="kov" title="Következő esemény">⏭</button>
 <input type="range" id="csuszka" min="0" max="0" step="0.01" value="0">
 <span id="ido">0:00</span>
 <select id="sebesseg" title="Lejátszás sebessége">
  <option value="0.5">0,5×</option>
  <option value="1" selected>1×</option>
  <option value="2">2×</option>
  <option value="4">4×</option>
 </select>
 <label title="A labda útja az utolsó 3 másodpercben"><input type="checkbox" id="nyom"> Labda-nyom</label>
 <label title="A labdás passzsávjai a csapattársakhoz (zöld nyitott, sárga kockázatos, piros zárt)"><input type="checkbox" id="passzsav"> Passzsávok</label>
 <label title="A védőfal rései szervezett védekezésben: zöld zárt, piros a 3,5 m-es vagy nagyobb rés — ott nyílik a fal"><input type="checkbox" id="falres"> Fal-rések</label>
</div>
<script type="importmap">{"imports":{
 "three":"/vendor/three@0.160.0/build/three.module.js",
 "three/addons/":"/vendor/three@0.160.0/examples/jsm/"
}}</script>
<script type="module">
import * as THREE from "three";
import {VRButton} from "three/addons/webxr/VRButton.js";

const ADAT = __ADAT__;
// A csapatnév (felhasználói adat) innerHTML-be csak escape-elve kerülhet.
const hx = (s) => String(s).replace(/[&<>"']/g,
  (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c]);
// 📦 FELVÉTEL-CSOMAG (egyetlen HTML-fájl, motor nélkül — view3d_csomag):
// a beágyazott felvétel ({adat, hang}); a motoros funkciók kikapcsolnak
// (mint a mentett oldalnál), a felvétel magától indul. Élő oldalon null.
const FV_CSOMAG = null;
if (FV_CSOMAG) ADAT.match_id = "";
const H = 40, W = 20, KAPU_SZ = 3;
__LOVES_JS__
__PASSZSAV_JS__

const szinpad = new THREE.Scene();
szinpad.background = new THREE.Color(0x0a0e14);
const kamera = new THREE.PerspectiveCamera(60, innerWidth/innerHeight, .1, 300);
// A VR-ben a kamera a "rig"-en ül: a rig mozog, a fejmozgás a headseté.
const rig = new THREE.Group();
rig.position.set(20, 1.6, 27); // pályaközép előtt, szemmagasságban
// VR-ben a headset a PADLÓTÓL méri a fej magasságát (local-floor): a
// kamera (és a kontrollerek) egy belső csoportban ülnek, ami VR-ben
// VR_SZEM-mel lejjebb kerül — így a rig y-ja asztalon és VR-ben is a SZEM
// magassága (a nézet-gombok, a játékos-kamera, az "Ide mindenki" ezzel
// számol); enélkül VR-ben a néző ~1,6 m-rel a padló fölött lebegett.
const VR_SZEM = 1.6;
const vrAllo = new THREE.Group();
rig.add(vrAllo);
vrAllo.add(kamera);
szinpad.add(rig);

const fest = new THREE.WebGLRenderer({antialias:true});
fest.setSize(innerWidth, innerHeight);
fest.xr.enabled = true;
fest.xr.addEventListener("sessionstart", () => { vrAllo.position.y = -VR_SZEM; });
fest.xr.addEventListener("sessionend", () => { vrAllo.position.y = 0; });
// A kontrollerek (a sugarukhoz — a közös nézés VR-mutatója) a kamerával
// azonos csoportban: a rig mozgása és a VR-magasság őket is viszi.
const vrKontrollerek = [0, 1].map(i => { const c = fest.xr.getController(i); vrAllo.add(c); return c; });
document.body.appendChild(fest.domElement);
document.body.appendChild(VRButton.createButton(fest));
addEventListener("resize", () => {
  kamera.aspect = innerWidth/innerHeight; kamera.updateProjectionMatrix();
  fest.setSize(innerWidth, innerHeight);
});

// Pálya: talaj + vonalak. A pálya-sík a three x/z síkja (y felfelé):
// pálya (x,y) → three (x, 0, W - y), így a nézet jobbkezes marad.
// CSARNOK: fa parketta a pályán (a vonalak rajta), sötétebb padló
// körülötte, és lelátó-tömbök a két hosszoldalon — a bejárás közben
// ettől lesz "teremben vagyunk" érzet, nem a semmiben lebegő vonalak.
const csarnokPadlo = new THREE.Mesh(
  new THREE.PlaneGeometry(H+40, W+40),
  new THREE.MeshLambertMaterial({color:0x151b24}));
csarnokPadlo.rotation.x = -Math.PI/2; csarnokPadlo.position.set(H/2, -0.02, W/2);
szinpad.add(csarnokPadlo);
const talaj = new THREE.Mesh(
  new THREE.PlaneGeometry(H+2, W+2),
  new THREE.MeshLambertMaterial({color:0x8a5a34}));
talaj.rotation.x = -Math.PI/2; talaj.position.set(H/2, -0.01, W/2);
szinpad.add(talaj);
// Parketta-csíkok: keskeny, váltakozó árnyalatú sávok a hossz mentén.
for (let i = 0; i < 20; i++){
  const csik = new THREE.Mesh(new THREE.PlaneGeometry(H+2, (W+2)/20 - 0.02),
    new THREE.MeshLambertMaterial({color: i % 2 ? 0x8f5e37 : 0x845531}));
  csik.rotation.x = -Math.PI/2;
  csik.position.set(H/2, -0.005, -1 + (W+2)/20*(i+0.5));
  szinpad.add(csik);
}
const lelatoAnyag = new THREE.MeshLambertMaterial({color:0x2b3a4a});
for (const oldal of [-1, 1]){
  for (let lepcso = 0; lepcso < 6; lepcso++){
    const tomb = new THREE.Mesh(new THREE.BoxGeometry(H+16, 0.5, 1.6), lelatoAnyag);
    const z = oldal < 0 ? -4 - lepcso*1.6 : W + 4 + lepcso*1.6;
    tomb.position.set(H/2, 0.25 + lepcso*0.5, z);
    szinpad.add(tomb);
  }
}
const vonalSzin = new THREE.LineBasicMaterial({color:0x9fb6c6});
function vonal(pontok){
  const g = new THREE.BufferGeometry().setFromPoints(
    pontok.map(p => new THREE.Vector3(p[0], 0.01, W - p[1])));
  szinpad.add(new THREE.Line(g, vonalSzin));
}
vonal([[0,0],[H,0],[H,W],[0,W],[0,0]]);
vonal([[H/2,0],[H/2,W]]);
// Szabálykönyv-hű kapuelőtér: negyedkör az alsó kapufa körül →
// egyenes a kapu előtt → negyedkör a felső kapufa körül. A 9 m-es
// szabaddobási vonal ugyanez az alak 9 m-rel — a pályán belüli része.
function kapufaIv(bal, r){
  const cx = bal ? 0 : H, also = W/2-1.5, felso = W/2+1.5;
  const ut = [];
  for (let a=-90; a<=0; a+=3){
    const rad = a*Math.PI/180;
    ut.push([cx + (bal?1:-1)*Math.cos(rad)*r, also + Math.sin(rad)*r]);
  }
  for (let a=0; a<=90; a+=3){
    const rad = a*Math.PI/180;
    ut.push([cx + (bal?1:-1)*Math.cos(rad)*r, felso + Math.sin(rad)*r]);
  }
  return ut.filter(p => p[1] >= 0 && p[1] <= W);
}
function kapuElo(bal, r){ vonal(kapufaIv(bal, r)); }
kapuElo(true, 6); kapuElo(false, 6);
// A 9 m-es vonal SZAGGATOTT (a szabálykönyv 15 cm-es szakaszai).
const szaggatottSzin = new THREE.LineDashedMaterial(
  {color:0x9fb6c6, dashSize:0.3, gapSize:0.3});
for (const bal of [true, false]){
  const g = new THREE.BufferGeometry().setFromPoints(
    kapufaIv(bal, 9).map(p => new THREE.Vector3(p[0], 0.01, W - p[1])));
  const l = new THREE.Line(g, szaggatottSzin);
  l.computeLineDistances();
  szinpad.add(l);
}
// Hetes-vonal (1 m, 7 m-re), kapus-vonal (4 m-re; láthatóra nyújtva),
// és a cserevonalak jele az oldalvonalon (a félpályától 4,5 m-re).
for (const bal of [true, false]){
  const x7 = bal ? 7 : H - 7, x4 = bal ? 4 : H - 4;
  vonal([[x7, W/2 - 0.5], [x7, W/2 + 0.5]]);
  vonal([[x4, W/2 - 0.475], [x4, W/2 + 0.475]]);
}
for (const x of [H/2 - 4.5, H/2 + 4.5]) vonal([[x, -0.15], [x, 0.15]]);
// Kapuk (3 m széles, 2 m magas keret).
const kapuSzin = new THREE.LineBasicMaterial({color:0xd9b544});
for (const x of [0, H]){
  const g = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(x, 0, W - (W/2-1.5)),
    new THREE.Vector3(x, 2, W - (W/2-1.5)),
    new THREE.Vector3(x, 2, W - (W/2+1.5)),
    new THREE.Vector3(x, 0, W - (W/2+1.5)),
  ]);
  szinpad.add(new THREE.Line(g, kapuSzin));
}

// Játékos-figurák készlete (újrahasznosítva képkockánként): fej hajjal,
// mez a csapatszínben, nadrág, karok és lábak — a haladás irányába
// fordulnak, a sebességgel arányosan lépnek. Ugyanaz, mint az appbeli
// 3D pályán.
const hazaiAnyag = new THREE.MeshLambertMaterial({color:0x2f86d6});
const vendegAnyag = new THREE.MeshLambertMaterial({color:0xd65a4a});
const hazaiNadrag = new THREE.MeshLambertMaterial({color:0x17436b});
const vendegNadrag = new THREE.MeshLambertMaterial({color:0x6b2d25});
const borAnyag = new THREE.MeshLambertMaterial({color:0xe3b98f});
const hajAnyag = new THREE.MeshLambertMaterial({color:0x3a2a1e});
const zokniAnyag = new THREE.MeshLambertMaterial({color:0xeeeeee});
const kapusAnyag = new THREE.MeshLambertMaterial({color:0x3fbf6f});
const kapusNadrag = new THREE.MeshLambertMaterial({color:0x1f5f38});
szinpad.add(new THREE.HemisphereLight(0xdfe7ef, 0x101820, 1.1));
const napfeny = new THREE.DirectionalLight(0xffffff, 0.6);
napfeny.position.set(10, 30, 10); szinpad.add(napfeny);
const babuk = [];
function vegtag(anyag, r, hossz){
  // Egy végtag-szakasz: a forgáspontja a felső végén (a csoport
  // origójában), a lekerekített test lefelé lóg — így a forgatás
  // lendítés. Kapszula: a végtag nem "cső", hanem gömbölyű.
  const cs = new THREE.Group();
  const m = new THREE.Mesh(new THREE.CapsuleGeometry(r, Math.max(0.05, hossz - 2*r), 3, 8), anyag);
  m.position.y = -hossz/2; cs.add(m);
  return cs;
}
function babu(){
  const cs = new THREE.Group();
  // Törzs: lekerekített kapszula (váll-szélesség), fölötte nyak.
  const mez = new THREE.Mesh(new THREE.CapsuleGeometry(0.19, 0.3, 4, 10), hazaiAnyag);
  mez.scale.set(1.15, 1, 0.75); mez.position.y = 1.2; cs.add(mez);
  const nyak = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.06, 0.1, 8), borAnyag);
  nyak.position.y = 1.5; cs.add(nyak);
  const nadrag = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.19, 0.28, 10), hazaiNadrag);
  nadrag.position.y = 0.82; cs.add(nadrag);
  const fej = new THREE.Mesh(new THREE.SphereGeometry(0.12, 12, 10), borAnyag);
  fej.scale.set(0.95, 1.1, 1.0); fej.position.y = 1.66; cs.add(fej);
  const haj = new THREE.Mesh(new THREE.SphereGeometry(0.125, 10, 6, 0, Math.PI*2, 0, Math.PI/2), hajAnyag);
  haj.position.y = 1.67; cs.add(haj);
  const tagok = {};
  for (const oldal of [-1, 1]){
    const comb = vegtag(borAnyag, 0.07, 0.42); comb.position.set(oldal*0.11, 0.92, 0);
    const labszar = vegtag(zokniAnyag, 0.055, 0.44); labszar.position.y = -0.42; comb.add(labszar);
    const felkar = vegtag(hazaiAnyag, 0.05, 0.3); felkar.position.set(oldal*0.25, 1.42, 0);
    const alkar = vegtag(borAnyag, 0.04, 0.28); alkar.position.y = -0.3; felkar.add(alkar);
    cs.add(comb); cs.add(felkar);
    tagok[oldal] = {comb, labszar, felkar, alkar};
  }
  const arnyek = new THREE.Mesh(new THREE.CircleGeometry(0.3, 12),
    new THREE.MeshBasicMaterial({color:0x000000, transparent:true, opacity:0.35}));
  arnyek.rotation.x = -Math.PI/2; arnyek.position.y = 0.005; cs.add(arnyek);
  // Mezszám-címke a fej fölött (sprite: mindig a kamera felé néz).
  const cimke = new THREE.Sprite(new THREE.SpriteMaterial({transparent:true, depthTest:false}));
  cimke.position.y = 2.0; cimke.scale.set(0.5, 0.28, 1); cimke.visible = false; cs.add(cimke);
  cs.userData = {mez, nadrag, felkarok:[tagok[-1].felkar, tagok[1].felkar], tagok, elozo:null,
                 cimke, cimkeKulcs:null};
  szinpad.add(cs);
  babuk.push(cs);
  return cs;
}
// Mezszám-textúrák: számonként és csapatonként egyszer rajzoljuk.
const szamTexturak = new Map();
function szamTextura(n, hazai){
  const kulcs = n + ":" + (hazai ? 1 : 0);
  if (szamTexturak.has(kulcs)) return szamTexturak.get(kulcs);
  const c = document.createElement("canvas"); c.width = 128; c.height = 72;
  const g = c.getContext("2d");
  g.fillStyle = hazai ? "rgba(76,154,255,0.92)" : "rgba(255,107,107,0.92)";
  g.beginPath(); g.roundRect(4, 4, 120, 64, 14); g.fill();
  g.fillStyle = "#ffffff"; g.font = "bold 44px sans-serif";
  g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(String(n), 64, 38);
  const tex = new THREE.CanvasTexture(c);
  szamTexturak.set(kulcs, tex);
  return tex;
}
function szinez(cs, hazai, kapus){
  // A kapus a valóságban is MÁS mezben játszik (a szabály előírja): a
  // 3D-ben zöld mez + hosszú (a nadrágig érő) nadrág jelzi.
  const u = cs.userData;
  const felso = kapus ? kapusAnyag : (hazai ? hazaiAnyag : vendegAnyag);
  u.mez.material = felso;
  u.nadrag.material = kapus ? kapusNadrag : (hazai ? hazaiNadrag : vendegNadrag);
  for (const f of u.felkarok) f.children[0].material = felso;
}
function lendit(cs, seb, t, k){
  // Lépés: a sebességgel nő az ütem és az amplitúdó; a két oldal
  // ellenütemben, a karok a lábakkal szemben.
  const amp = Math.min(1, seb/5), utem = 1.2 + seb*0.35;
  const f = Math.sin(t*2*Math.PI*utem + (k%7)*0.9) * amp;
  const u = cs.userData;
  for (const oldal of [-1, 1]){
    const s = -oldal*f;
    u.tagok[oldal].comb.rotation.x = s*0.6;
    u.tagok[oldal].labszar.rotation.x = Math.max(0, -s)*0.8;
    u.tagok[oldal].felkar.rotation.x = -s*0.5;
    u.tagok[oldal].alkar.rotation.x = -0.4;
  }
}
const labda = new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 10),
  new THREE.MeshBasicMaterial({color:0xe8a33d}));
szinpad.add(labda);

// Lejátszás + interpoláció.
const frames = ADAT.frames;
const veg = frames.length ? frames[frames.length-1][0] : 0;
// ?t=349 — a jelenet-ugrás: az appból (vagy megosztott linkből) az
// oldal az adott játékidő-másodpercen nyílik, és rögtön játszik.
const t0 = Math.max(0, Math.min(veg,
  parseFloat(new URLSearchParams(location.search).get("t") || "0") || 0));
let ido = t0, megy = t0 > 0, utolso = performance.now();
const csuszka = document.getElementById("csuszka");
csuszka.max = veg;
const lejatszasGomb = document.getElementById("lejatszas");
lejatszasGomb.onclick = () => { megy = !megy; lejatszasGomb.textContent = megy ? "⏸" : "▶"; };
if (megy) lejatszasGomb.textContent = "⏸";
csuszka.value = ido;
csuszka.oninput = () => { ido = parseFloat(csuszka.value); };
// Lejátszás sebessége (0,5–4×): a lassítás a jelenet-elemzésé, a
// gyorsítás az átnézésé.
const sebessegValaszto = document.getElementById("sebesseg");
let sebesseg = 1;
sebessegValaszto.onchange = () => { sebesseg = parseFloat(sebessegValaszto.value) || 1; };
// Esemény-ugrás (⏮/⏭ és [ / ]): a jelenet előtt 4 mp-cel, lejátszva —
// mint az appból érkezve. Egy másodpercnyi holt sáv, hogy az épp nézett
// esemény ne "ragadjon". A felirat a jelenet közben mondja, mi történik.
const ESEM = ADAT.events || [];
const NEV = {g: "GÓL", s: "Lövés", t: "Labdaeladás", f: "Ismert figura"};
function esemenyUgras(irany){
  if (!ESEM.length) return;
  let cel = null;
  if (irany > 0){ for (const e of ESEM){ if (e[0] > ido + 1){ cel = e; break; } } }
  else { for (let i = ESEM.length-1; i >= 0; i--){ if (ESEM[i][0] < ido - 1){ cel = ESEM[i]; break; } } }
  if (!cel) return;
  ido = Math.max(0, cel[0] - 4); megy = true; lejatszasGomb.textContent = "⏸";
  csuszka.value = ido;
}
document.getElementById("elozo").onclick = () => esemenyUgras(-1);
document.getElementById("kov").onclick = () => esemenyUgras(1);
const feliratElem = document.getElementById("felirat");
function felirat(t){
  for (const e of ESEM){
    if (t < e[0] - 0.3) break;
    if (t > e[0] + 2.5) continue;
    feliratElem.textContent = NEV[e[1]] + " — " + (e[2] ? ADAT.home : ADAT.away);
    feliratElem.style.display = "block";
    return;
  }
  feliratElem.style.display = "none";
}
function keres(t){
  let lo = 0, hi = frames.length-1;
  while (lo < hi){ const kozep = (lo+hi+1)>>1;
    if (frames[kozep][0] <= t) lo = kozep; else hi = kozep-1; }
  return lo;
}
// A legutóbb kirajzolt állás figuránként (pálya-méterben) — a
// játékos-nézet, a védekezés-panel és a dupla kattintás ebből dolgozik.
const allas = [];
function rajzol(t){
  if (!frames.length) return;
  const i = keres(t), a = frames[i],
        b = frames[Math.min(i+1, frames.length-1)];
  const ar = b[0] > a[0] ? (t - a[0]) / (b[0] - a[0]) : 0;
  const jat = a[1];
  allas.length = 0;
  while (babuk.length < jat.length) babu();
  for (let k = 0; k < babuk.length; k++){
    const cs = babuk[k];
    if (k >= jat.length){ cs.visible = false; continue; }
    cs.visible = true;
    // Index-alapú párosítás két kocka közt: csak azonos csapatú párra
    // interpolálunk (a sorrend kockánként eltérhet), különben ugrunk.
    const p = jat[k],
          q = (b[1] && b[1][k] && b[1][k][0] === p[0]) ? b[1][k] : p;
    const x = p[1] + (q[1]-p[1])*ar, y = p[2] + (q[2]-p[2])*ar;
    cs.position.set(x, 0, W - y);
    allas.push({k, x, y, hazai: !!p[0], mert: !!p[3], kapus: !!p[4], mez: p[5] || 0, seb: 0});
    szinez(cs, !!p[0], !!p[4]);
    // Mezszám-címke: csak ismert számnál; a textúra csapatonként/számonként egy.
    const mezszam = p[5] || 0, u = cs.userData;
    if (mezszam){
      const kulcs = mezszam + ":" + (p[0] ? 1 : 0);
      if (u.cimkeKulcs !== kulcs){
        u.cimke.material.map = szamTextura(mezszam, !!p[0]);
        u.cimke.material.needsUpdate = true; u.cimkeKulcs = kulcs;
      }
      u.cimke.visible = true;
    } else { u.cimke.visible = false; }
    // Irány és sebesség a két kocka elmozdulásából (követés-ugrás
    // kiszűrve); álló játékos tartja az előző irányát.
    const dx = q[1]-p[1], dy = q[2]-p[2], dt = Math.max(0.05, b[0]-a[0]);
    const seb = Math.hypot(dx, dy)/dt;
    allas[allas.length-1].seb = seb <= 8 ? seb : 0;
    if (seb > 0.3 && seb <= 8){ cs.rotation.y = Math.atan2(dx, -dy); }
    lendit(cs, seb <= 8 ? seb : 0, t, k);
    cs.scale.setScalar(p[3] ? 1 : 0.92);
  }
  let l = a[2];
  if (l){
    const l2 = b[2] || l;
    const lx = l[0] + (l2[0]-l[0])*ar, ly = l[1] + (l2[1]-l[1])*ar;
    labda.visible = true;
    // Ha van BIRTOKOSA (a legközelebbi figura karnyújtásnyira van), a
    // labda a kezében van — nem a földszint fölött lebeg.
    let birtokos = null, legkozelebb = 1.2;
    for (let k = 0; k < jat.length && k < babuk.length; k++){
      const d = Math.hypot(jat[k][1]-lx, jat[k][2]-ly);
      if (d < legkozelebb){ legkozelebb = d; birtokos = babuk[k]; }
    }
    if (birtokos){
      // A figura ELEJE a helyi +z: a forgatás atan2(dx, -dy), így a
      // (0,0,1) forgatva a haladás iránya. (A (0,0,-1) a háta mögé tette
      // a labdát.)
      const irany = new THREE.Vector3(0, 0, 1)
        .applyAxisAngle(new THREE.Vector3(0,1,0), birtokos.rotation.y);
      labda.position.set(birtokos.position.x + irany.x*0.32, 1.28,
                         birtokos.position.z + irany.z*0.32);
    } else {
      labda.position.set(lx, 0.5, W - ly);
    }
  } else labda.visible = false;
}

// ---- Kamera-módok -------------------------------------------------
// "szabad": húzás — körülnézés, WASD — mozgás, görgetés — előre ugrás.
// "kering": a pálya közepe körül; húzás — keringés, görgetés/csípés —
//           közelítés. WASD-re szabad módba vált (aki mozog, vezetni akar).
// "jatekos": a kiválasztott játékos SZEMÉVEL, vele együtt halad (dupla
//           kattintás egy figurára); húzás — körülnéz, Esc — kilép.
// "kovetes": JÁTÉKOS-KAMERA — egy mezszámot hátulról, 4 m-ről, 2,2 m
//           magasból, simítva követ (az appbeli Játékos-kamera párja);
//           húzás vagy WASD visszavált szabadra.
// "tv":     TV-KAMERA — az oldalvonal felől (7 m-re kint, 4,5 m magasan)
//           a labdát tartja képben, x-ben simítva követi (az appbeli
//           TV-kamera párja); húzás vagy WASD visszavált szabadra.
let mod = "szabad";
let yaw = 0, pitch = 0;
const CEL = new THREE.Vector3(H/2, 0, W/2);          // a pálya közepe (three-tér)
const kering = {theta: 0, phi: 0.6, r: 30};
const jatekosNez = {yaw: 0, pitch: -0.05};
let kovet = null;   // {hazai, mez, x, y, irany} — a játékos-nézet célja
const keringGomb = document.getElementById("keringGomb");
const jatekosKiGomb = document.getElementById("jatekosKi");
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

function modValt(uj){
  if (uj === "kering" && mod !== "kering"){
    // A keringés onnan indul, ahol a kamera áll — nem ugrik.
    const off = rig.position.clone().sub(CEL);
    kering.r = clamp(off.length(), 4, 80);
    kering.phi = clamp(Math.asin(clamp(off.y / Math.max(1e-6, off.length()), -1, 1)), 0.08, 1.5);
    kering.theta = Math.atan2(off.x, off.z);
  }
  if (uj === "szabad" && mod === "kering"){ yaw = kering.theta; pitch = -kering.phi; }
  if (uj === "szabad" && mod === "jatekos"){
    yaw = rig.rotation.y; pitch = jatekosNez.pitch;
    rig.position.y = Math.max(rig.position.y, 1.6);
  }
  if (uj !== "jatekos"){ kovet = null; jatekosHud.style.display = "none"; }
  if (uj === "szabad" && (mod === "kovetes" || mod === "tv")){ yaw = rig.rotation.y; pitch = kamera.rotation.x; }
  if (uj !== "kovetes"){ kovetKam = null; jatekosKameraValaszto.value = ""; }
  mod = uj;
  keringGomb.classList.toggle("be", mod === "kering");
  tvGomb.classList.toggle("be", mod === "tv");
  jatekosKiGomb.style.display = mod === "jatekos" ? "" : "none";
}
keringGomb.onclick = () => modValt(mod === "kering" ? "szabad" : "kering");
const tvGomb = document.getElementById("tvGomb");
tvGomb.onclick = () => {
  modValt(mod === "tv" ? "szabad" : "tv");
  if (mod === "tv" && !megy){ megy = true; lejatszasGomb.textContent = "⏸"; }
};
// TV-kamera: a labda helye a jelenetből (kézben vagy a padlón), a
// kamera az oldalvonal felől x-ben követi, a nézés a labdán.
function tvFrissit(dt){
  if (mod !== "tv" || !labda.visible) return;
  const lx = labda.position.x, lz = labda.position.z;
  const celX = clamp(lx, 4, 36), celZ = W + 7, celY = 4.5;
  const k = clamp(dt * 2.5, 0, 1);
  rig.position.x += (celX - rig.position.x) * k;
  rig.position.z += (celZ - rig.position.z) * k;
  rig.position.y += (celY - rig.position.y) * k;
  if (!fest.xr.isPresenting){
    const dx = lx - rig.position.x, dz = lz - rig.position.z, dy = 0.6 - rig.position.y;
    rig.rotation.y = Math.atan2(-dx, -dz);
    kamera.rotation.set(Math.atan2(dy, Math.hypot(dx, dz)), 0, 0);
  }
}

// ---- Játékos-kamera: egy mezszám hátulról követve ---------------------
// A mezszámok a kockákból (csapatonként, rendezve); a kamera a játékos
// mögé áll a simított haladási irányában, és a fejére néz. A zajos
// követés ne rángassa: erős simítás az irányon és a helyen is.
const jatekosKameraValaszto = document.getElementById("jatekosKamera");
let kovetKam = null;  // {hazai, mez, ix, iy, ex, ey}
{
  const mezek = {1: new Set(), 0: new Set()};
  for (const f of frames) for (const p of f[1]) if (p[5]) mezek[p[0]].add(p[5]);
  for (const cs of [1, 0]){
    for (const mez of [...mezek[cs]].sort((a, b) => a - b)){
      const o = document.createElement("option");
      o.value = (cs ? "h" : "v") + mez;
      o.textContent = (cs ? ADAT.home : ADAT.away) + " " + mez;
      jatekosKameraValaszto.appendChild(o);
    }
  }
}
jatekosKameraValaszto.onchange = () => {
  const v = jatekosKameraValaszto.value;
  if (!v){ if (mod === "kovetes") modValt("szabad"); return; }
  modValt("kovetes");
  kovetKam = {hazai: v[0] === "h", mez: parseInt(v.slice(1), 10), ix: 0, iy: 0, ex: null, ey: null};
  jatekosKameraValaszto.value = v;
  if (!megy){ megy = true; lejatszasGomb.textContent = "⏸"; }
};
function kovetesFrissit(dt){
  if (mod !== "kovetes" || !kovetKam) return;
  const cel = allas.find(s => s.hazai === kovetKam.hazai && s.mez === kovetKam.mez);
  if (!cel) return;
  const k = kovetKam;
  if (k.ex !== null && dt > 0){
    const vx = (cel.x - k.ex) / dt, vy = (cel.y - k.ey) / dt, seb = Math.hypot(vx, vy);
    if (seb > 0.6){
      const ks = clamp(dt * 1.5, 0, 1);
      k.ix += (vx / seb - k.ix) * ks; k.iy += (vy / seb - k.iy) * ks;
      const h = Math.hypot(k.ix, k.iy);
      if (h > 1e-6){ k.ix /= h; k.iy /= h; }
    }
  }
  k.ex = cel.x; k.ey = cel.y;
  // Cél-hely pálya-térben (a játékos mögött 4 m, 2,2 m magasan) → three.
  const cx = cel.x - k.ix * 4.0, cy = cel.y - k.iy * 4.0;
  const ka = clamp(dt * 3.0, 0, 1);
  rig.position.x += (cx - rig.position.x) * ka;
  rig.position.z += ((W - cy) - rig.position.z) * ka;
  rig.position.y += (2.2 - rig.position.y) * ka;
  if (!fest.xr.isPresenting){
    // A fejére néz: az előre-irány three-ben (−sin yaw, −cos yaw).
    const dx = cel.x - rig.position.x, dz = (W - cel.y) - rig.position.z, dy = 1.3 - rig.position.y;
    rig.rotation.y = Math.atan2(-dx, -dz);
    kamera.rotation.set(Math.atan2(dy, Math.hypot(dx, dz)), 0, 0);
  }
}
jatekosKiGomb.onclick = () => modValt("szabad");

// Asztali irányítás: billentyűk.
const gombok = new Set();
addEventListener("keydown", e => {
  if (e.target && (e.target.tagName === "SELECT" || e.target.tagName === "INPUT")) return;
  if (e.code === "Space"){ lejatszasGomb.onclick(); e.preventDefault(); return; }
  if (e.code === "BracketLeft"){ esemenyUgras(-1); return; }
  if (e.code === "BracketRight"){ esemenyUgras(1); return; }
  // következő / előző jelenet — a felvétel visszajátszásakor fejezet
  if (e.code === "KeyN"){ if (fvLejatszas) felvetelFejezet(1); else jelenetLep(1); return; }
  if (e.code === "KeyP"){ if (fvLejatszas) felvetelFejezet(-1); else jelenetLep(-1); return; }
  if (e.code === "KeyV"){ vetitesAllit(!vetites); return; }  // vetítés
  if (e.code === "KeyO"){ keringGomb.onclick(); return; }
  if (e.code === "KeyT"){ tvGomb.onclick(); return; }
  if (e.code === "KeyE"){ rajzModAllit(!rajzMod); return; }  // rajz
  if (e.code === "KeyJ"){ jegyzetIr(); return; }  // jegyzet
  if (e.code === "KeyM"){ panelAllit(!panelCsukva); return; }  // a vezérlőpanel
  if (e.code === "KeyH" && kozosMod === "kovet"){ kezAllit(!kzKez); return; }  // ✋
  if (e.code === "KeyK"){ videoAllit(!videoBe); return; }  // videó
  if (e.code === "Escape"){ if (mod === "jatekos") modValt("szabad"); else if (rajzMod) rajzModAllit(false); else meresTorles(); return; }
  if (["KeyW","KeyA","KeyS","KeyD","KeyR","KeyF","KeyC"].includes(e.code)
      && mod !== "szabad") modValt("szabad");
  gombok.add(e.code);
});
addEventListener("keyup", e => gombok.delete(e.code));

// Egér/érintés: húzás — nézés vagy keringés; rövid katt — mérés;
// dupla katt — játékos-nézet; két ujj — csípés-zoom.
const ujjak = new Map();
let huzas = null, csipes = null, kattIdozito = null;
const vaszon = fest.domElement;
vaszon.style.touchAction = "none";
vaszon.addEventListener("pointerdown", e => {
  ujjak.set(e.pointerId, {x: e.clientX, y: e.clientY});
  vaszon.setPointerCapture(e.pointerId);
  if (rajzMod && ujjak.size === 1 && !fest.xr.isPresenting){
    const p = padloPont(e.clientX, e.clientY);
    if (p){ rajzFolyo = [p[0], p[1], p[0], p[1], Number(rajzSzin.value) || 0]; huzas = null; return; }
  }
  if (ujjak.size === 2){
    rajzFolyo = null; rajzFrissit();  // két ujj: csípés, nem rajz
    const [p1, p2] = [...ujjak.values()];
    csipes = Math.hypot(p1.x - p2.x, p1.y - p2.y); huzas = null; return;
  }
  huzas = {x: e.clientX, y: e.clientY, mozdult: false};
});
vaszon.addEventListener("pointermove", e => {
  if (!ujjak.has(e.pointerId)) return;
  ujjak.set(e.pointerId, {x: e.clientX, y: e.clientY});
  if (rajzFolyo && ujjak.size === 1){
    const p = padloPont(e.clientX, e.clientY);
    if (p){ rajzFolyo[2] = p[0]; rajzFolyo[3] = p[1]; rajzFrissit(); }
    return;
  }
  if (ujjak.size === 2 && csipes){
    const [p1, p2] = [...ujjak.values()];
    const d = Math.hypot(p1.x - p2.x, p1.y - p2.y);
    if (d > 1){ zoom(csipes / d); csipes = d; }
    return;
  }
  if (!huzas) return;
  const dx = e.clientX - huzas.x, dy = e.clientY - huzas.y;
  if (!huzas.mozdult && Math.hypot(dx, dy) < 4) return;
  huzas.mozdult = true; huzas.x = e.clientX; huzas.y = e.clientY;
  if (mod === "kering"){
    kering.theta -= dx * 0.006;
    kering.phi = clamp(kering.phi + dy * 0.006, 0.08, 1.5);
  } else if (mod === "jatekos"){
    jatekosNez.yaw -= dx * 0.004;
    jatekosNez.pitch = clamp(jatekosNez.pitch - dy * 0.004, -1.2, 1.2);
  } else {
    if (mod === "kovetes" || mod === "tv") modValt("szabad");  // aki húz, vezetni akar
    yaw -= dx * 0.004;
    pitch = clamp(pitch - dy * 0.004, -1.45, 1.45);
  }
});
function ujjFel(e){
  ujjak.delete(e.pointerId);
  if (rajzFolyo){ rajzKesz(); return; }
  if (ujjak.size < 2) csipes = null;
  const katt = huzas && !huzas.mozdult;
  huzas = null;
  if (!katt || fest.xr.isPresenting) return;
  // Közös nézés: a vezető Shift+kattintása a padlóra MUTATÓ a csapatnak
  // (nem lövés-mérés) — a követőknél lüktető gyűrű ott.
  if (e.shiftKey && kozosMod === "vezet"){ mutatoKattintas(e.clientX, e.clientY); return; }
  // Kvíz közben a követő kattintása a padlóra a VÁLASZA.
  if (kvizValaszolhat()){ valaszKattintas(e.clientX, e.clientY); return; }
  // A dupla kattintás első fele ne mérjen: kicsit várunk.
  clearTimeout(kattIdozito);
  const cx = e.clientX, cy = e.clientY;
  kattIdozito = setTimeout(() => meresKattintas(cx, cy), 260);
}
vaszon.addEventListener("pointerup", ujjFel);
vaszon.addEventListener("pointercancel", e => { ujjak.delete(e.pointerId); huzas = null; csipes = null; rajzFolyo = null; rajzFrissit(); });
vaszon.addEventListener("dblclick", e => {
  clearTimeout(kattIdozito);
  jatekosValasztas(e.clientX, e.clientY);
});
vaszon.addEventListener("wheel", e => {
  e.preventDefault();
  zoom(Math.exp(e.deltaY * 0.0012));
}, {passive: false});
function zoom(arany){
  // arany > 1: távolodás. Keringésben a sugár változik; szabad módban
  // előre/hátra ugrás a nézés irányában ("dash").
  if (mod === "kering"){ kering.r = clamp(kering.r * arany, 4, 80); return; }
  if (mod === "jatekos" || mod === "kovetes" || mod === "tv") return;
  const lep = -Math.log(arany) * 12;
  const irany = new THREE.Vector3();
  kamera.getWorldDirection(irany);
  rig.position.addScaledVector(irany, lep);
  rig.position.y = clamp(rig.position.y, 0.4, 60);
}

// Képernyő-pont → sugár a jelenetbe.
const sugar = new THREE.Raycaster();
const ndc = new THREE.Vector2();
function sugarBeallit(cx, cy){
  const r = vaszon.getBoundingClientRect();
  ndc.set(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1);
  sugar.setFromCamera(ndc, kamera);
}

// ---- Játékos-nézet: dupla kattintás egy figurára -------------------
function jatekosValasztas(cx, cy){
  if (fest.xr.isPresenting) return;
  sugarBeallit(cx, cy);
  const talalat = sugar.intersectObjects(babuk.filter(b => b.visible), true)[0];
  if (!talalat) return;
  let o = talalat.object;
  while (o && !babuk.includes(o)) o = o.parent;
  const k = babuk.indexOf(o);
  const a = allas.find(s => s.k === k);
  if (!a) return;
  jatekosNez.yaw = 0; jatekosNez.pitch = -0.05;
  modValt("jatekos");
  kovet = {hazai: a.hazai, mez: a.mez, x: a.x, y: a.y, irany: o.rotation.y, k};
  // A gomb megmondja, kinek a szemével nézünk (csapat + mezszám).
  jatekosKiGomb.textContent = (a.hazai ? ADAT.home : ADAT.away) +
    (a.mez ? " #" + a.mez : "") + " szemével ✕";
  if (!megy){ megy = true; lejatszasGomb.textContent = "⏸"; }
}
// A játékos megtett útja kockánként összegezve (méter): a mezszám a
// fogódzó (azonosító nélkül nincs út); a lépésenkénti ugrás-szűrő
// MÉTER-korlát (TAV_UGRAS_M), hogy a követés-ugrás ne számítson, a
// sűrű remegés viszont ne essen ki. Meccsenként egyszer, mezszámonként.
const TAV_UGRAS_M = 3;
const tavTablak = new Map();
function tavTabla(hazai, mez){
  const kulcs = (hazai ? "h" : "v") + mez;
  if (tavTablak.has(kulcs)) return tavTablak.get(kulcs);
  const t = new Float64Array(frames.length);
  const cs = hazai ? 1 : 0;
  let ex = null, ey = null, ossz = 0;
  for (let i = 0; i < frames.length; i++){
    const p = frames[i][1].find(q => q[0] === cs && q[5] === mez);
    if (p){
      if (ex !== null){
        const d = Math.hypot(p[1] - ex, p[2] - ey);
        if (d <= TAV_UGRAS_M) ossz += d;
      }
      ex = p[1]; ey = p[2];
    }
    t[i] = ossz;
  }
  tavTablak.set(kulcs, t);
  return t;
}
const jatekosHud = document.getElementById("jatekosHud");
function hudFrissit(cel){
  if (!kovet || !cel){ jatekosHud.style.display = "none"; return; }
  let s = (kovet.hazai ? ADAT.home : ADAT.away) + (kovet.mez ? " #" + kovet.mez : "") +
    " · " + szam1(cel.seb * 3.6) + " km/h";
  if (kovet.mez){
    const m = tavTabla(kovet.hazai, kovet.mez)[keres(ido)];
    s += " · " + (m >= 1000 ? (m/1000).toFixed(2).replace(".", ",") + " km" : Math.round(m) + " m") + " eddig";
  }
  jatekosHud.textContent = s; jatekosHud.style.display = "block";
}
// A követett ember megkeresése az új kockán: azonos mezszám (ha van),
// különben az előző helyéhez legközelebbi csapattárs 3 m-en belül —
// a követés-azonosítók töredezettek, a mezszám és a hely a fogódzó.
function kovetFrissit(dt){
  if (!kovet) return;
  let cel = null;
  if (kovet.mez){
    cel = allas.find(s => s.hazai === kovet.hazai && s.mez === kovet.mez) || null;
  }
  if (!cel){
    let legjobb = 3.0;
    for (const s of allas){
      if (s.hazai !== kovet.hazai) continue;
      const d = Math.hypot(s.x - kovet.x, s.y - kovet.y);
      if (d < legjobb){ legjobb = d; cel = s; }
    }
  }
  hudFrissit(cel);
  if (cel){
    kovet.x = cel.x; kovet.y = cel.y; kovet.k = cel.k;
    // Az irány simítva követi a figura haladását (a zajos követés ne
    // rángassa a fejet); a rövidebb íven fordul.
    const celIrany = babuk[cel.k].rotation.y;
    let d = celIrany - kovet.irany;
    while (d > Math.PI) d -= 2*Math.PI;
    while (d < -Math.PI) d += 2*Math.PI;
    kovet.irany += d * Math.min(1, dt * 3);
    // A saját testét nem látja (a kamera a fejében ül).
    babuk[cel.k].visible = false;
  }
  const fx = Math.sin(kovet.irany), fz = Math.cos(kovet.irany);
  rig.position.set(kovet.x + fx * 0.12, 1.62, (W - kovet.y) + fz * 0.12);
  if (!fest.xr.isPresenting){
    rig.rotation.y = kovet.irany + Math.PI + jatekosNez.yaw;
    kamera.rotation.set(jatekosNez.pitch, 0, 0);
  }
}

// ---- Rajz: nyilak a padlón (a taktika-tábla a valódi jeleneten) -----
// Rajz-módban (E) a húzás nyilat rajzol a padlóra a választott színnel
// (sárga labda/passz, kék futás, piros védő) — az edző a megállított
// jeleneten megmutatja, hova kellett volna futni, passzolni, lépni. A
// nyilak a padlón élnek, tehát minden nézetből és VR-ben is látszanak; a
// link viszi őket (rajz=…), így a videó-elemzés egy címmel megosztható.
// A nyíl lapos test (a WebGL-vonal egy pixel vastag, messziről eltűnne).
const rajzCsoport = new THREE.Group();
szinpad.add(rajzCsoport);
const rajzok = [];          // [x1, y1, x2, y2, színkód] — pálya-méter
let rajzMod = false, rajzFolyo = null;  // a húzás alatti nyíl
const rajzGomb = document.getElementById("rajzGomb");
const rajzSzin = document.getElementById("rajzSzin");
const rajzInfo = document.getElementById("rajzInfo");
function padloPont(cx, cy){
  // Képernyő-pont → padló-pont pálya-méterben (a pálya ±3 m-es sávjában).
  sugarBeallit(cx, cy);
  const pont = new THREE.Vector3();
  if (!sugar.ray.intersectPlane(padloSik, pont)) return null;
  const x = pont.x, y = W - pont.z;
  if (x < -3 || x > H + 3 || y < -3 || y > W + 3) return null;
  return [x, y];
}
function nyilMesh(x1, y1, x2, y2, k){
  const d = Math.hypot(x2 - x1, y2 - y1) || 1;
  const fej = Math.min(0.9, d * 0.45), szel = 0.18;
  const ux = (x2 - x1) / d, uy = (y2 - y1) / d, nx = -uy * szel / 2, ny = ux * szel / 2;
  const bx = x2 - ux * fej, by = y2 - uy * fej;
  const [[ax, ay], [cx, cy]] = nyilFej(x1, y1, x2, y2, fej, fej * 0.9);
  const P = (x, y) => [x, 0.06, W - y];
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute([
    ...P(x1 + nx, y1 + ny), ...P(x1 - nx, y1 - ny), ...P(bx - nx, by - ny),
    ...P(bx + nx, by + ny), ...P(ax, ay), ...P(cx, cy), ...P(x2, y2)], 3));
  g.setIndex([0, 1, 2, 0, 2, 3, 4, 5, 6]);
  return new THREE.Mesh(g, new THREE.MeshBasicMaterial({
    color: parseInt(RAJZ_SZINEK[k] || RAJZ_SZINEK[0], 16), side: THREE.DoubleSide,
    transparent: true, opacity: 0.92, depthWrite: false}));
}
function rajzFrissit(){
  csoportUrit(rajzCsoport);
  for (const r of rajzok) rajzCsoport.add(nyilMesh(...r));
  if (rajzFolyo) rajzCsoport.add(nyilMesh(...rajzFolyo));
  rajzInfo.textContent = rajzok.length ? rajzok.length + " nyíl" : "";
}
function rajzKesz(){
  // A húzás vége: elég hosszú húzás nyíl lesz (a plafonig).
  const r = rajzFolyo; rajzFolyo = null; huzas = null;
  if (r && Math.hypot(r[2] - r[0], r[3] - r[1]) >= RAJZ_MIN_M && rajzok.length < RAJZ_MAX) rajzok.push(r);
  rajzFrissit();
}
function rajzModAllit(be){
  rajzMod = !!be; rajzFolyo = null;
  rajzGomb.classList.toggle("be", rajzMod);
  vaszon.style.cursor = rajzMod ? "crosshair" : "";
  rajzFrissit();
}
rajzGomb.onclick = () => rajzModAllit(!rajzMod);
document.getElementById("rajzVissza").onclick = () => { rajzok.pop(); rajzFrissit(); };
document.getElementById("rajzTorles").onclick = () => { rajzok.length = 0; rajzFrissit(); };
window.rajzProba = () => ({mod: rajzMod, nyilak: rajzok.map(r => r.slice()), kod: rajzKodol(rajzok)});

// ---- Lövés-mérés: katt a padlóra ----------------------------------
const meresElem = document.getElementById("meres");
const meresCsoport = new THREE.Group();
szinpad.add(meresCsoport);
const padloSik = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
function szam1(v){ return v.toFixed(1).replace(".", ","); }
function meresTorles(){
  csoportUrit(meresCsoport);
  meresElem.style.display = "none";
}
function meresKattintas(cx, cy){
  sugarBeallit(cx, cy);
  if (lovesKattintas()) return;
  const pont = new THREE.Vector3();
  if (!sugar.ray.intersectPlane(padloSik, pont)) return;
  const x = pont.x, y = W - pont.z;
  if (x < -3 || x > H + 3 || y < -3 || y > W + 3) return;
  meresRajzol(x, y);
}
function meresRajzol(x, y, kapu){
  meresTorles();
  const m = lovesMeres(x, y, kapu);
  const v = (px, py, h) => new THREE.Vector3(px, h, W - py);
  const p = v(x, y, 0.02);
  const y1 = W/2 - KAPU_SZ/2, y2 = W/2 + KAPU_SZ/2;
  // A lövő-háromszög: a pontból a két kapufáig — ennyi kapu "látszik".
  const tri = new THREE.BufferGeometry().setFromPoints(
    [p, v(m.gx, y1, 0.02), v(m.gx, y2, 0.02)]);
  tri.setIndex([0, 1, 2]);
  meresCsoport.add(new THREE.Mesh(tri, new THREE.MeshBasicMaterial(
    {color:0x2f86d6, transparent:true, opacity:0.28, side:THREE.DoubleSide, depthWrite:false})));
  const vonalAnyag = new THREE.LineBasicMaterial({color:0x4c9aff});
  for (const cel of [v(m.gx, y1, 0.02), v(m.gx, y2, 0.02)]){
    meresCsoport.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([p, cel]), vonalAnyag));
  }
  const kozep = new THREE.Line(new THREE.BufferGeometry().setFromPoints(
    [p, v(m.gx, W/2, 0.02)]), new THREE.LineDashedMaterial({color:0xffffff, dashSize:0.25, gapSize:0.2}));
  kozep.computeLineDistances(); meresCsoport.add(kozep);
  const gyuru = new THREE.Mesh(new THREE.RingGeometry(0.22, 0.32, 24),
    new THREE.MeshBasicMaterial({color:0xffffff, side:THREE.DoubleSide}));
  gyuru.rotation.x = -Math.PI/2; gyuru.position.copy(p); meresCsoport.add(gyuru);
  meresElem.innerHTML = "<b>Lövés-mérés</b> (" + (m.kapu === "bal" ? "bal" : "jobb") +
    " kapu)<br>" + szam1(m.tav) + " m a kapu közepétől · kapufától " + szam1(m.kapufa) +
    " m<br>Kapu-szög: " + szam1(m.szog) + "° · sáv: " + m.sav +
    '<button id="meresKi" title="Törlés (Esc)">✕</button>';
  meresElem.style.display = "block";
  document.getElementById("meresKi").onclick = meresTorles;
}

// ---- Passzok: a futó passz vonala / a csapat passz-hálója -------------
// Élő: a passz kockájától PASSZ_S másodpercig vonal mellmagasságban az
// adótól a fogadóig (halványodva). Háló: a csapat minden passza vékony
// vonalként a padlón — a játékszervezés fő tengelyei látszanak.
const PASSZOK = ADAT.passes || [];
const PASSZ_S = 1.0;
const passzValaszto = document.getElementById("passz");
const passzInfo = document.getElementById("passzInfo");
const passzElo = new THREE.Group(), passzHalo = new THREE.Group();
szinpad.add(passzElo); szinpad.add(passzHalo);
let passzHaloNev = null;
function passzSzin(hazai){ return hazai ? 0x4c9aff : 0xff6b6b; }
// Az élő passz-vonalak anyagai: csapatonként tíz átlátszóság-fok, egyszer
// létrehozva és megosztva ("tartós" — a csoportUrit nem szabadítja fel).
const PASSZ_ANYAGOK = new Map();
function passzAnyag(hazai, atlatszo){
  const fok = Math.max(1, Math.min(10, Math.round(atlatszo * 10)));
  const kulcs = (hazai ? "h" : "v") + fok;
  let a = PASSZ_ANYAGOK.get(kulcs);
  if (!a){
    a = new THREE.LineBasicMaterial({color: passzSzin(hazai), transparent: true, opacity: fok / 10});
    a.userData.tartos = true; PASSZ_ANYAGOK.set(kulcs, a);
  }
  return a;
}
function passzFrissit(t){
  const v = passzValaszto.value;
  csoportUrit(passzElo);
  passzHalo.visible = v === "hazai" || v === "vendeg";
  if (!v){ passzInfo.textContent = ""; return; }
  if (v === "elo"){
    let db = 0;
    for (const [mp, hazai, x1, y1, x2, y2] of PASSZOK){
      if (mp > t || t - mp > PASSZ_S) continue;
      const g = new THREE.BufferGeometry().setFromPoints(
        [new THREE.Vector3(x1, 1.0, W - y1), new THREE.Vector3(x2, 1.0, W - y2)]);
      passzElo.add(new THREE.Line(g, passzAnyag(hazai, 1 - (t - mp) / PASSZ_S)));
      db++;
    }
    passzInfo.textContent = db ? "passz úton" : "";
    return;
  }
  const hazai = v === "hazai" ? 1 : 0;
  if (passzHaloNev !== v){
    csoportUrit(passzHalo);
    const pontok = [];
    for (const [mp, h, x1, y1, x2, y2] of PASSZOK){
      if (h !== hazai) continue;
      pontok.push(new THREE.Vector3(x1, 0.015, W - y1), new THREE.Vector3(x2, 0.015, W - y2));
    }
    if (pontok.length){
      passzHalo.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pontok),
        new THREE.LineBasicMaterial({color: passzSzin(hazai), transparent: true, opacity: 0.35})));
    }
    passzHaloNev = v;
    passzInfo.textContent = (pontok.length / 2) + " passz — " + (hazai ? ADAT.home : ADAT.away);
  }
}

// ---- Hőtérkép: hol tartózkodott a csapat a meccsen -------------------
// A pályára fektetett, áttetsző textúra: 20×10 cella (2 m), a cella
// erőssége a MÉRT helyek száma a legsűrűbb cellához képest (ugyanaz a
// rács, mint az elemzés hőtérképe). Egyszer számoljuk, a váltás csak
// újrafesti a vásznat.
const HO_X = 20, HO_Y = 10;
const hoValaszto = document.getElementById("hoter");
const hoVaszon = document.createElement("canvas"); hoVaszon.width = 400; hoVaszon.height = 200;
const hoTextura = new THREE.CanvasTexture(hoVaszon);
const hoSik = new THREE.Mesh(new THREE.PlaneGeometry(H, W),
  new THREE.MeshBasicMaterial({map: hoTextura, transparent: true, depthWrite: false}));
hoSik.rotation.x = -Math.PI/2; hoSik.position.set(H/2, 0.008, W/2); hoSik.visible = false;
szinpad.add(hoSik);
function hoRacs(hazai){
  const r = Array.from({length: HO_Y}, () => new Array(HO_X).fill(0));
  let max = 0;
  for (const f of frames) for (const p of f[1]){
    if (!!p[0] !== hazai || !p[3]) continue;
    const ix = Math.min(HO_X-1, Math.max(0, Math.floor(p[1] / H * HO_X)));
    const iy = Math.min(HO_Y-1, Math.max(0, Math.floor(p[2] / W * HO_Y)));
    r[iy][ix]++; if (r[iy][ix] > max) max = r[iy][ix];
  }
  return {r, max};
}
let hoRacsok = null;
function hoFest(){
  const v = hoValaszto.value;
  hoSik.visible = !!v;
  if (!v) return;
  if (!hoRacsok) hoRacsok = {hazai: hoRacs(true), vendeg: hoRacs(false)};
  const g = hoVaszon.getContext("2d");
  g.clearRect(0, 0, hoVaszon.width, hoVaszon.height);
  const cw = hoVaszon.width / HO_X, ch = hoVaszon.height / HO_Y;
  for (const [nev, rgb] of [["hazai", "76,154,255"], ["vendeg", "255,107,107"]]){
    if (v !== "mind" && v !== nev) continue;
    const {r, max} = hoRacsok[nev];
    if (!max) continue;
    for (let iy = 0; iy < HO_Y; iy++) for (let ix = 0; ix < HO_X; ix++){
      const e = r[iy][ix] / max;
      if (e <= 0) continue;
      // A textúra teteje a pálya y = W széle (a sík a three x/z-re fekszik).
      g.fillStyle = "rgba(" + rgb + "," + (0.1 + 0.65*e).toFixed(2) + ")";
      g.fillRect(ix*cw, (HO_Y-1-iy)*ch, cw, ch);
    }
  }
  hoTextura.needsUpdate = true;
}
hoValaszto.onchange = hoFest;

// ---- Kész kamera-állások (az appbeli 3D pálya gombjainak párja) ------
// Pálya-koordinátában (x, y, magasság, irány, dőlés) → a rig helye a
// three-térben (x, h, W − y); az irány előjele a tükrözés miatt fordul.
const NEZETEK = {
  lelato: [20, -12, 9, 0, -0.5],
  kapu:   [-6, 10, 2.5, Math.PI/2, -0.12],
  palya:  [20, 4, 1.7, 0, 0],
  madar:  [20, 10, 34, 0, -1.45],
};
function nezet(nev){
  const [x, y, h, irany, doles] = NEZETEK[nev];
  modValt("szabad");
  utolsoNezet = nev;
  rig.position.set(x, h, W - y);
  yaw = -irany; pitch = doles;
}
for (const b of document.querySelectorAll("button.nezet")) b.onclick = () => nezet(b.dataset.n);

// ---- Megosztható link: a mostani jelenet címként -----------------------
// ?t=349&nezet=madar&kamera=h7&hoter=mind&loves=mind&passz=hazai&fal=elo
// — az oldal nyitáskor visszaállítja (a t-t a lejátszó-indítás már
// kezeli). Az edző így EGY jelenetet küld, nem egy meccset.
const URL_PARAM = new URLSearchParams(location.search);
let utolsoNezet = null;
function linkEpit(){
  const q = new URLSearchParams();
  q.set("t", Math.round(ido));
  if (mod === "kovetes" && kovetKam) q.set("kamera", (kovetKam.hazai ? "h" : "v") + kovetKam.mez);
  else if (mod === "tv") q.set("tv", "1");
  else if (utolsoNezet && mod === "szabad") q.set("nezet", utolsoNezet);
  for (const [nev, el] of [["hoter", hoValaszto], ["loves", lovesValaszto],
                           ["passz", passzValaszto], ["fal", falValaszto]]){
    if (el.value) q.set(nev, el.value);
  }
  if (falOldal.value !== "auto") q.set("falOldal", falOldal.value);
  if (nyomKapcsolo.checked) q.set("nyom", "1");
  if (passzsavKapcsolo.checked) q.set("passzsav", "1");
  if (falresKapcsolo.checked) q.set("falres", "1");
  if (jelenetCsapat.value !== "mind") q.set("jelenet", jelenetCsapat.value);
  if (jelenetLista.style.display === "block") q.set("lista", "1");
  if (csakKulcs) q.set("kulcs", "1");
  if (csakJegyzet) q.set("jegyzetek", "1");
  if (vetites) q.set("vetit", "1");
  if (rajzok.length) q.set("rajz", rajzKodol(rajzok));
  if (videoBe) q.set("video", "1");
  if (kozosMod === "kovet"){ q.set("kovet", "1"); if (KZ_NEV) q.set("nev", KZ_NEV); }
  if (sebesseg !== 1) q.set("seb", String(sebesseg));
  return location.origin + location.pathname + "?" + q.toString();
}
const linkInfo = document.getElementById("linkInfo");
document.getElementById("linkGomb").onclick = async () => {
  const url = linkEpit();
  try { await navigator.clipboard.writeText(url); linkInfo.textContent = "másolva"; }
  catch (e) { linkInfo.textContent = url; }
  setTimeout(() => { linkInfo.textContent = ""; }, 4000);
};
function linkAlkalmaz(){
  const v = (k) => URL_PARAM.get(k) || "";
  for (const [nev, el] of [["hoter", hoValaszto], ["loves", lovesValaszto],
                           ["passz", passzValaszto], ["fal", falValaszto]]){
    if (v(nev) && [...el.options].some(o => o.value === v(nev))){ el.value = v(nev); el.onchange && el.onchange(); }
  }
  if (v("falOldal")) falOldal.value = v("falOldal");
  if (v("nyom") === "1") nyomKapcsolo.checked = true;
  if (v("passzsav") === "1") passzsavKapcsolo.checked = true;
  if (v("falres") === "1") falresKapcsolo.checked = true;
  if (v("jelenet") === "hazai" || v("jelenet") === "vendeg"){
    jelenetCsapat.value = v("jelenet"); jelenetInfok();
  }
  if (v("kulcs") === "1" && KULCS.size) csakKulcs = true;
  if (v("jegyzetek") === "1"){ csakJegyzet = true; csakKulcs = false; }
  if (v("lista") === "1") jelenetListaNyit(true);
  if (v("seb")){ sebessegValaszto.value = v("seb"); sebessegValaszto.onchange(); }
  // A vetítés a szűrők és a sebesség után indul (a t-ből: az ott futó
  // jelenettől, különben a következőtől).
  // A jegyzet-vetítés a jegyzetek megjöttét várja (jegyzetBetolt indítja).
  if (v("vetit") === "1"){ if (csakJegyzet) vetitesVar = true; else vetitesAllit(true); }
  if (v("rajz")){ rajzok.push(...rajzDekodol(v("rajz"))); rajzFrissit(); }
  if (v("video") === "1") videoAllit(true);
  if (v("kovet") === "1") kozosAllit("kovet");
  else if (v("vezet") === "1") kozosAllit("vezet");
  if (v("nezet") && NEZETEK[v("nezet")]) nezet(v("nezet"));
  if (v("tv") === "1") modValt("tv");
  if (v("kamera") && [...jatekosKameraValaszto.options].some(o => o.value === v("kamera"))){
    jatekosKameraValaszto.value = v("kamera"); jatekosKameraValaszto.onchange();
  }
}

// ---- Labda-nyom: a labda útja az utolsó NYOM_S másodpercben ----------
// Narancs vonal a labda-magasságban: a passz-sorozat és a lövés íve
// egyben látszik, nem csak a pillanatnyi hely.
const NYOM_S = 3;
const nyomKapcsolo = document.getElementById("nyom");
const nyomGeom = new THREE.BufferGeometry();
const nyomVonal = new THREE.Line(nyomGeom,
  new THREE.LineBasicMaterial({color:0xe8a33d, transparent:true, opacity:0.85}));
nyomVonal.visible = false;
szinpad.add(nyomVonal);
function nyomFrissit(t){
  if (!nyomKapcsolo.checked || !frames.length){ nyomVonal.visible = false; return; }
  const pontok = [];
  for (let i = keres(Math.max(0, t - NYOM_S)); i < frames.length && frames[i][0] <= t; i++){
    const l = frames[i][2];
    if (l) pontok.push(new THREE.Vector3(l[0], 0.45, W - l[1]));
  }
  if (pontok.length < 2){ nyomVonal.visible = false; return; }
  nyomGeom.setFromPoints(pontok);
  nyomVonal.visible = true;
}

// ---- Passzsávok: a labdás opciói ------------------------------------
// A labdástól minden csapattársához egy vonal mellmagasságban, a passz-
// esély szerint színezve (a döntés-elemzés modellje, lásd passzSavok).
const passzsavKapcsolo = document.getElementById("passzsav");
const passzsavCsoport = new THREE.Group();
szinpad.add(passzsavCsoport);
const PS_SZIN = {"nyitott": 0x3fbf6f, "kockázatos": 0xd9b544, "zárt": 0xff6b6b};
// A sávok közös anyagai (kockánként újrarajzolt réteg — "tartós").
const PS_ANYAG = {};
for (const [fok, szin] of Object.entries(PS_SZIN)){
  PS_ANYAG[fok] = new THREE.LineBasicMaterial({color: szin, transparent: true, opacity: 0.85});
  PS_ANYAG[fok].userData.tartos = true;
}
const passzsavInfo = document.createElement("div");
passzsavInfo.style.cssText = "position:fixed;right:12px;bottom:56px;padding:6px 12px;border:1px solid #2b4a5e;border-radius:8px;background:rgba(16,24,32,.85);font-size:13px;display:none";
document.body.appendChild(passzsavInfo);
function passzsavFrissit(){
  csoportUrit(passzsavCsoport);
  if (!passzsavKapcsolo.checked){ passzsavInfo.style.display = "none"; return; }
  const jat = allas.map(s => [s.hazai ? 1 : 0, s.x, s.y]);
  const lb = labda.visible ? [labda.position.x, W - labda.position.z] : null;
  const r = passzSavok(jat, lb);
  if (!r){ passzsavInfo.textContent = "Most nincs labdás játékos."; passzsavInfo.style.display = "block"; return; }
  const db = {"nyitott": 0, "kockázatos": 0, "zárt": 0};
  for (const l of r.lanes){
    db[l.grade]++;
    const g = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(r.holder[0], 1.1, W - r.holder[1]),
      new THREE.Vector3(l.x, 1.1, W - l.y)]);
    passzsavCsoport.add(new THREE.Line(g, PS_ANYAG[l.grade]));
  }
  passzsavInfo.textContent = "Labdás (" + (r.holder[2] ? ADAT.home : ADAT.away) + "): " +
    db["nyitott"] + " nyitott, " + db["kockázatos"] + " kockázatos, " + db["zárt"] + " zárt sáv";
  passzsavInfo.style.display = "block";
}

// ---- Fal-rések: hol nyílik a védőfal ---------------------------------
// Szervezett védekezésben (az élő fal sora él) a védőfal szomszédos védői
// közt sáv a padlón: zöld, ha zárt, piros, ha a rés eléri a 3,5 m-t (a
// wall_gaps réteg mércéje) — ott kell betörni, oda úszik be a beálló.
const falresKapcsolo = document.getElementById("falres");
const falresCsoport = new THREE.Group();
szinpad.add(falresCsoport);
const falresInfo = document.createElement("div");
falresInfo.style.cssText = "position:fixed;right:12px;bottom:100px;padding:6px 12px;border:1px solid #2b4a5e;border-radius:8px;background:rgba(16,24,32,.85);font-size:13px;display:none";
document.body.appendChild(falresInfo);
const FR_ZOLD = new THREE.MeshBasicMaterial({color: 0x3ddc84, transparent: true, opacity: 0.85});
const FR_PIROS = new THREE.MeshBasicMaterial({color: 0xff6b6b, transparent: true, opacity: 0.95});
function falresFrissit(t){
  while (falresCsoport.children.length){
    const c = falresCsoport.children[0]; falresCsoport.remove(c); c.geometry.dispose();
  }
  if (!falresKapcsolo.checked){ falresInfo.style.display = "none"; return; }
  falresInfo.style.display = "block";
  const elo = eloFal(t);
  if (!elo){ falresInfo.textContent = "Most nincs szervezett támadás — a fal nem áll."; return; }
  const jat = allas.map(s => [s.hazai ? 1 : 0, s.x, s.y, s.mert ? 1 : 0, s.kapus ? 1 : 0]);
  const r = falResek(jat, elo.hazai, elo.goalX);
  const csapat = elo.hazai ? ADAT.home : ADAT.away;
  if (!r){ falresInfo.textContent = "Fal (" + csapat + "): nem áll — " + FR_MIN + " mért védőnél kevesebb a kapu előtt."; return; }
  for (let i = 0; i + 1 < r.fal.length; i++){
    const [x1, y1] = r.fal[i], [x2, y2] = r.fal[i + 1];
    const dx = x2 - x1, dz = (W - y2) - (W - y1), hossz = Math.hypot(dx, dz);
    if (hossz < 0.05) continue;
    // Lapos sáv a padlón (a vonal 1 px-es volna — messziről nem látszik).
    const sav = new THREE.Mesh(new THREE.BoxGeometry(hossz, 0.03, r.szeles[i] ? 0.28 : 0.16),
      r.szeles[i] ? FR_PIROS : FR_ZOLD);
    sav.position.set((x1 + x2) / 2, 0.04, W - (y1 + y2) / 2);
    sav.rotation.y = -Math.atan2(dz, dx);
    falresCsoport.add(sav);
  }
  const nyilt = r.szeles.filter(Boolean).length;
  falresInfo.innerHTML = "Fal (" + hx(csapat) + ", " + r.fal.length + " védő): " + (nyilt
    ? "<span style='color:#ff6b6b'>" + nyilt + " nyitott rés</span> — a legnagyobb " + szam1(r.max) + " m"
    : "zárt — a legnagyobb rés " + szam1(r.max) + " m");
}

// ---- Emberelőny: a kiállítások szakaszai ---------------------------------
// Élő jelző (lent középen), amíg egy szakaszon belül vagyunk: ki van
// előnyben, mennyi van hátra, és az előny alatti állás eddig; ◀ ▶ a
// szakaszok elejére ugrik (court3d.powerplay_moments — a
// powerplay_efficiency réteg szakaszai és lövés-szabálya).
const EMBEREK = ADAT.powerplays || [];
const emberJelzo = document.getElementById("emberJelzo");
document.getElementById("emberInfo").textContent = EMBEREK.length ? EMBEREK.length + " szakasz" : "nincs ilyen";
let emberUtolso = null;
function emberUgras(irany){
  if (!EMBEREK.length) return;
  const cel = lapozCel(EMBEREK.map(d => d[0]), ido, emberUtolso, irany);
  if (cel === null) return;
  emberUtolso = cel;
  ido = Math.max(0, cel - 1.5); megy = true; lejatszasGomb.textContent = "⏸";
  csuszka.value = ido;
}
document.getElementById("emberElozo").onclick = () => emberUgras(-1);
document.getElementById("emberKov").onclick = () => emberUgras(1);
function emberFrissit(t){
  const d = EMBEREK.find(x => t >= x[0] && t <= x[1]);
  if (!d){ emberJelzo.style.display = "none"; return; }
  emberJelzo.textContent = emberSzoveg(d, t, ADAT.home, ADAT.away);
  emberJelzo.style.display = "block";
}

// ---- Gól-akciók: a gólt megelőző passz-lánc ------------------------------
// ◀ ▶ a gólok közt ugrik (1,5 mp-cel az első passz előtt, lejátszva); a
// lánc a csapat színével (a régebbi passz halványabb), arany vonal a
// lövőtől a kapu közepéig; a felirat a mezszámokkal (court3d.
// goal_build_ups — a goal_buildup réteg lánc-szabályával).
const GOLAKCIOK = ADAT.goal_build_ups || [];
const golCsoport = new THREE.Group();
szinpad.add(golCsoport);
document.getElementById("golInfo").textContent = GOLAKCIOK.length ? GOLAKCIOK.length + " gól" : "nincs ilyen";
let golUtolso = null;
function golUgras(irany){
  if (!GOLAKCIOK.length) return;
  const cel = lapozCel(GOLAKCIOK.map(d => d[0]), ido, golUtolso, irany);
  if (cel === null) return;
  golUtolso = cel;
  ido = Math.max(0, cel - 1.5); megy = true; lejatszasGomb.textContent = "⏸";
  csuszka.value = ido;
}
document.getElementById("golElozo").onclick = () => golUgras(-1);
document.getElementById("golKov").onclick = () => golUgras(1);
function golFrissit(t){
  const d = GOLAKCIOK.find(x => t >= x[0] - 0.3 && t <= x[1] + 2.5);
  // Csak jelenet-váltáskor rajzolunk újra (a hurok minden kockán hív).
  if (golCsoport.userData.kesz && golCsoport.userData.d === d) return golCsoport.userData.szoveg;
  csoportUrit(golCsoport); golCsoport.userData.kesz = true; golCsoport.userData.d = d; golCsoport.userData.szoveg = null;
  if (!d) return null;
  const [s0, sg, hazai, lanc, lx, ly, lmez, gx, gy, n, hossz] = d;
  const szin = hazai ? 0x4c9aff : 0xff6b6b;
  lanc.forEach((p, i) => {
    if (p[0] === null || p[2] === null) return;
    const g = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(p[0], 1.0, W - p[1]), new THREE.Vector3(p[2], 1.0, W - p[3])]);
    golCsoport.add(new THREE.Line(g, new THREE.LineBasicMaterial(
      {color: szin, transparent: true, opacity: 0.35 + 0.65 * (i + 1) / lanc.length})));
  });
  if (lx !== null){
    const g = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(lx, 1.2, W - ly), new THREE.Vector3(gx, 1.0, W - gy)]);
    golCsoport.add(new THREE.Line(g, new THREE.LineBasicMaterial({color: 0xd9b544})));
  }
  return (golCsoport.userData.szoveg = golAkcioFelirat(d, ADAT.home, ADAT.away));
}

// ---- Jelenet-szűrő: kinek a hibái ---------------------------------------
// A három lapozó mind egy csapat HIBÁJÁT mutatja — a rossz döntést hozó, a
// lövőt szabadon hagyó és a labdát elvesztő csapatét; a sorok 2. eleme
// (hazai?) épp ez a csapat. A szűrővel csak a saját vagy csak az ellenfél
// jelenetei lapozhatók (és rajzolódnak ki).
const jelenetCsapat = document.getElementById("jelenetCsapat");
jelenetCsapat.options[1].textContent = ADAT.home;
jelenetCsapat.options[2].textContent = ADAT.away;
function szurt(lista){
  const v = jelenetCsapat.value;
  return v === "mind" ? lista : lista.filter(d => !!d[1] === (v === "hazai"));
}
function jelenetInfok(){
  const n = (lista) => szurt(lista).length;
  dontesInfo.textContent = n(DONTESEK) ? n(DONTESEK) + " pillanat" : "nincs ilyen pillanat";
  document.getElementById("szabadInfo").textContent = n(SZABADOK) ? n(SZABADOK) + " lövés" : "nincs ilyen";
  document.getElementById("eladasInfo").textContent = n(ELADASOK) ? n(ELADASOK) + " eladás" : "nincs ilyen";
  document.getElementById("kontraInfo").textContent = n(KONTRAK) ? n(KONTRAK) + " lerohanás" : "nincs ilyen";
  document.getElementById("kapottInfo").textContent = n(KAPOTTAK) ? n(KAPOTTAK) + " gól" : "nincs ilyen";
  if (jelenetLista.style.display === "block") jelenetListaEpit();
}
jelenetCsapat.onchange = () => {
  jelenetInfok();
  dontesUtolso = null; szabadUtolso = null; eladasUtolso = null; kontraUtolso = null; kapottUtolso = null;
};

// ---- Döntés-pillanatok: ahol jobb opció is volt -----------------------
// ◀ ▶ a pillanatok közt ugrik (1,5 mp-cel előtte, lejátszva); a pillanat
// körül a választott passz FEHÉR, a jobb opció ARANY vonal, a felirat
// megnevezi (court3d.decision_moments — a döntés-elemzés modellje).
const DONTESEK = ADAT.decisions || [];
const dontesCsoport = new THREE.Group();
szinpad.add(dontesCsoport);
const dontesFelirat = document.getElementById("dontesFelirat");
const dontesInfo = document.getElementById("dontesInfo");
let dontesUtolso = null;
function dontesUgras(irany){
  if (!szurt(DONTESEK).length) return;
  const cel = lapozCel(szurt(DONTESEK).map(d => d[0]), ido, dontesUtolso, irany);
  if (cel === null) return;
  dontesUtolso = cel;
  ido = Math.max(0, cel - 1.5); megy = true; lejatszasGomb.textContent = "⏸";
  csuszka.value = ido;
}
document.getElementById("dontesElozo").onclick = () => dontesUgras(-1);
document.getElementById("dontesKov").onclick = () => dontesUgras(1);
function szam2(v){ return v.toFixed(2).replace(".", ","); }
function dontesFrissit(t){
  const d = szurt(DONTESEK).find(x => t >= x[0] - 0.3 && t <= x[0] + 2.5);
  // A szabad lövés felirata KÜLÖN dobozban (a döntés-felirat alatt): két
  // egyszerre aktív pillanat nem takarhatja el egymást.
  const szabadSzoveg = szabadFrissit(t);
  const szabadFelirat = document.getElementById("szabadFelirat");
  if (szabadSzoveg){ szabadFelirat.textContent = szabadSzoveg; szabadFelirat.style.display = "block"; }
  else szabadFelirat.style.display = "none";
  emberFrissit(t);
  const golSzoveg = golFrissit(t);
  const golFelirat = document.getElementById("golFelirat");
  if (golSzoveg){ golFelirat.textContent = golSzoveg; golFelirat.style.display = "block"; }
  else golFelirat.style.display = "none";
  const eladasSzoveg = eladasFrissit(t);
  const eladasFelirat = document.getElementById("eladasFelirat");
  if (eladasSzoveg){ eladasFelirat.innerHTML = eladasSzoveg; eladasFelirat.style.display = "block"; }
  else eladasFelirat.style.display = "none";
  const kontraSzoveg = kontraFrissit(t);
  const kontraDoboz = document.getElementById("kontraFelirat");
  if (kontraSzoveg){ kontraDoboz.textContent = kontraSzoveg; kontraDoboz.style.display = "block"; }
  else kontraDoboz.style.display = "none";
  const kapottSzoveg = kapottFrissit(t);
  const kapottDoboz = document.getElementById("kapottFelirat");
  if (kapottSzoveg){ kapottDoboz.textContent = kapottSzoveg; kapottDoboz.style.display = "block"; }
  else kapottDoboz.style.display = "none";
  const hetesSzoveg = hetesFrissit(t);
  const hetesDoboz = document.getElementById("hetesFelirat");
  if (hetesSzoveg){ hetesDoboz.textContent = hetesSzoveg; hetesDoboz.style.display = "block"; }
  else hetesDoboz.style.display = "none";
  // Csak pillanat-váltáskor rajzolunk újra (a hurok minden kockán hív).
  if (dontesCsoport.userData.kesz && dontesCsoport.userData.d === d) return;
  csoportUrit(dontesCsoport); dontesCsoport.userData.kesz = true; dontesCsoport.userData.d = d;
  if (!d){ dontesFelirat.style.display = "none"; return; }
  const [mp, hazai, px, py, cx, cy, cval, fajta, bx, by, bval, gap] = d;
  const vonalD = (x2, y2, szin) => {
    const g = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(px, 1.15, W - py), new THREE.Vector3(x2, 1.15, W - y2)]);
    dontesCsoport.add(new THREE.Line(g, new THREE.LineBasicMaterial({color: szin})));
  };
  vonalD(cx, cy, 0xffffff);
  vonalD(bx, by, 0xd9b544);
  const jobb = fajta === "s" ? "LÖVÉS (" + szam2(bval) + ")" : "passz a másik társhoz (" + szam2(bval) + ")";
  dontesFelirat.innerHTML = "<b>" + hx(hazai ? ADAT.home : ADAT.away) + "</b> — jobb opció is volt: " +
    "<span style='color:#d9b544'>" + jobb + "</span> a választott passz (" + szam2(cval) +
    ") helyett · különbség " + szam2(gap);
  dontesFelirat.style.display = "block";
}

// ---- Szabad lövők: a fedezés-hibák pillanatai --------------------------
// ◀ ▶ a szabadon hagyott lövők közt ugrik (1,5 mp-cel előtte, lejátszva);
// a pillanat körül piros kör a lövő körül (a fedezés-sugár, 2 m) és vonal
// a legközelebbi mezőnyvédőhöz, a felirat megnevezi a távolságot
// (court3d.free_shot_moments — a védekezés-elemzés ítélete).
const SZABADOK = ADAT.free_shots || [];
const SZ_SUGAR = ADAT.free_radius || 2.0;
const szabadCsoport = new THREE.Group();
szinpad.add(szabadCsoport);
const szabadKor = new THREE.Mesh(new THREE.RingGeometry(SZ_SUGAR - 0.08, SZ_SUGAR + 0.04, 40),
  new THREE.MeshBasicMaterial({color: 0xff6b6b, side: THREE.DoubleSide, transparent: true, opacity: 0.9}));
szabadKor.rotation.x = -Math.PI/2; szabadKor.visible = false;
szinpad.add(szabadKor);
let szabadUtolso = null;
function szabadUgras(irany){
  if (!szurt(SZABADOK).length) return;
  const cel = lapozCel(szurt(SZABADOK).map(d => d[0]), ido, szabadUtolso, irany);
  if (cel === null) return;
  szabadUtolso = cel;
  ido = Math.max(0, cel - 1.5); megy = true; lejatszasGomb.textContent = "⏸";
  csuszka.value = ido;
}
document.getElementById("szabadElozo").onclick = () => szabadUgras(-1);
document.getElementById("szabadKov").onclick = () => szabadUgras(1);
function szabadFrissit(t){
  const d = szurt(SZABADOK).find(x => t >= x[0] - 0.3 && t <= x[0] + 2.5);
  if (szabadCsoport.userData.kesz && szabadCsoport.userData.d === d) return szabadCsoport.userData.szoveg;
  csoportUrit(szabadCsoport); szabadCsoport.userData.kesz = true; szabadCsoport.userData.d = d;
  szabadCsoport.userData.szoveg = null;
  if (!d){ szabadKor.visible = false; return null; }
  const [mp, vedHazai, sx, sy, dx, dy, tav, gol, xg] = d;
  szabadKor.position.set(sx, 0.03, W - sy); szabadKor.visible = true;
  if (dx !== null && dy !== null){
    const g = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(sx, 0.05, W - sy), new THREE.Vector3(dx, 0.05, W - dy)]);
    const l = new THREE.Line(g, new THREE.LineDashedMaterial({color: 0xff6b6b, dashSize: 0.3, gapSize: 0.2}));
    l.computeLineDistances(); szabadCsoport.add(l);
  }
  return (szabadCsoport.userData.szoveg = (vedHazai ? ADAT.home : ADAT.away) +
    " védekezése: szabadon hagyott lövő — a legközelebbi védő " +
    (tav !== null ? szam1(tav) + " m-re" : "nem mérhető") + " (" + (gol ? "GÓL" : "nem gól") +
    ", xG " + szam2(xg) + ")");
}

// ---- Labdavesztések: ki, hol, kipréselve vagy magától ------------------
// ◀ ▶ a labdavesztések közt ugrik (1,5 mp-cel előtte, lejátszva); a
// pillanat körül narancs kör a vesztő körül (a nyomás-sugár: ezen belül
// álló ellenfél = kipréselt eladás), szaggatott vonal a legközelebbi
// mezőnybeli ellenfélhez, X a labdánál; a felirat megnevezi a vesztőt,
// a harmadot, a nyomást és hogy gól lett-e belőle (court3d.turnover_moments
// — ugyanaz, mint a négy labdaeladás-réteg).
const ELADASOK = ADAT.turnovers || [];
const EL_SUGAR = ADAT.turnover_pressure || 2.5;
const EL_HARMAD = ["a saját harmadban", "a középső harmadban", "a támadó harmadban"];
const eladasCsoport = new THREE.Group();
szinpad.add(eladasCsoport);
const eladasKor = new THREE.Mesh(new THREE.RingGeometry(EL_SUGAR - 0.08, EL_SUGAR + 0.04, 40),
  new THREE.MeshBasicMaterial({color: 0xff9f43, side: THREE.DoubleSide, transparent: true, opacity: 0.9}));
eladasKor.rotation.x = -Math.PI/2; eladasKor.visible = false;
szinpad.add(eladasKor);
let eladasUtolso = null;
function eladasUgras(irany){
  if (!szurt(ELADASOK).length) return;
  const cel = lapozCel(szurt(ELADASOK).map(d => d[0]), ido, eladasUtolso, irany);
  if (cel === null) return;
  eladasUtolso = cel;
  ido = Math.max(0, cel - 1.5); megy = true; lejatszasGomb.textContent = "⏸";
  csuszka.value = ido;
}
document.getElementById("eladasElozo").onclick = () => eladasUgras(-1);
document.getElementById("eladasKov").onclick = () => eladasUgras(1);
function eladasFrissit(t){
  const d = szurt(ELADASOK).find(x => t >= x[0] - 0.3 && t <= x[0] + 2.5);
  if (eladasCsoport.userData.kesz && eladasCsoport.userData.d === d) return eladasCsoport.userData.szoveg;
  csoportUrit(eladasCsoport); eladasCsoport.userData.kesz = true; eladasCsoport.userData.d = d;
  eladasCsoport.userData.szoveg = null;
  if (!d){ eladasKor.visible = false; return null; }
  const [mp, hazai, mez, lx, ly, bx, by, harmad, ox, oy, tav, kipres, golMp] = d;
  const szin = 0xff9f43;
  if (lx !== null){
    eladasKor.position.set(lx, 0.03, W - ly); eladasKor.visible = true;
    if (ox !== null){
      const g = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(lx, 0.05, W - ly), new THREE.Vector3(ox, 0.05, W - oy)]);
      const l = new THREE.Line(g, new THREE.LineDashedMaterial({color: szin, dashSize: 0.3, gapSize: 0.2}));
      l.computeLineDistances(); eladasCsoport.add(l);
    }
  } else eladasKor.visible = false;
  if (bx !== null){
    // X a labda helyén (két keresztbe tett szakasz a padlón).
    for (const [ax, ay, cx, cy] of [[-0.45, -0.45, 0.45, 0.45], [-0.45, 0.45, 0.45, -0.45]]){
      const g = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(bx + ax, 0.06, W - (by + ay)), new THREE.Vector3(bx + cx, 0.06, W - (by + cy))]);
      eladasCsoport.add(new THREE.Line(g, new THREE.LineBasicMaterial({color: szin})));
    }
  }
  const ki = mez !== null ? mez + "-es" : "ismeretlen játékos";
  const hol = harmad !== null ? EL_HARMAD[harmad] : "ismeretlen helyen";
  const nyomas = kipres === null ? "a nyomás nem mérhető"
    : (kipres ? "kipréselve (ellenfél " + szam1(tav) + " m-re)"
              : "magától (a legközelebbi ellenfél " + szam1(tav) + " m-re)");
  const gol = golMp !== null
    ? " · <span style='color:#ff6b6b'>" + szam1(golMp) + " mp múlva kapott gól</span>" : "";
  return (eladasCsoport.userData.szoveg = "<b>" + hx(hazai ? ADAT.home : ADAT.away) +
    "</b> labdavesztés — " + ki + " · " + hol + " · " + nyomas + gol);
}

// ---- Lerohanások: ki fut, honnan, és mi lett belőle ---------------------
// ◀ ▶ a lerohanások közt ugrik (1,5 mp-cel az indulás előtt, lejátszva);
// a jelenet alatt a befejező útja a TÁMADÓ csapat színével a padlón (az
// indulástól a lövésig, pont a mintavételi helyeken), fehér szaggatott
// vonal a labda indulási helyétől az út elejéig (az indítópassz), arany
// vonal a lövéstől a kapuig; a felirat a kontra-rétegek ítéletével
// (court3d.fast_break_moments — a lerohanás-hatékonyság, a kontra-hullámok
// és a kontra-elszökés szabályai). A sor 2. eleme a VÉDEKEZŐ csapat (a
// kapott lerohanás az ő hibája) — a "Kinek a hibái" szűrő erre szűr.
const KONTRAK = ADAT.fast_breaks || [];
const kontraCsoport = new THREE.Group();
szinpad.add(kontraCsoport);
let kontraUtolso = null;
function kontraUgras(irany){
  if (!szurt(KONTRAK).length) return;
  const cel = lapozCel(szurt(KONTRAK).map(d => d[0]), ido, kontraUtolso, irany);
  if (cel === null) return;
  kontraUtolso = cel;
  ido = Math.max(0, cel - 1.5); megy = true; lejatszasGomb.textContent = "⏸";
  csuszka.value = ido;
}
document.getElementById("kontraElozo").onclick = () => kontraUgras(-1);
document.getElementById("kontraKov").onclick = () => kontraUgras(1);
function kontraFrissit(t){
  const d = szurt(KONTRAK).find(x => t >= x[0] - 0.3 && t <= x[14] + 2.5);
  // Csak jelenet-váltáskor rajzolunk újra (a hurok minden kockán hív).
  if (kontraCsoport.userData.kesz && kontraCsoport.userData.d === d) return kontraCsoport.userData.szoveg;
  csoportUrit(kontraCsoport); kontraCsoport.userData.kesz = true; kontraCsoport.userData.d = d; kontraCsoport.userData.szoveg = null;
  if (!d) return null;
  const [s, defHazai, mez, hullam, elszokott, hossz, kimenet, ut, lx, ly, gx, gy, bx, by] = d;
  const szin = defHazai ? 0xff6b6b : 0x4c9aff;  // a TÁMADÓ csapat színe
  const anyag = new THREE.MeshBasicMaterial({color: szin, side: THREE.DoubleSide});
  if (ut.length >= 2){
    const g = new THREE.BufferGeometry().setFromPoints(ut.map(p => new THREE.Vector3(p[0], 0.08, W - p[1])));
    kontraCsoport.add(new THREE.Line(g, new THREE.LineBasicMaterial({color: szin})));
  }
  for (const p of ut){
    const pont = new THREE.Mesh(new THREE.CircleGeometry(0.18, 12), anyag);
    pont.rotation.x = -Math.PI/2; pont.position.set(p[0], 0.07, W - p[1]);
    kontraCsoport.add(pont);
  }
  if (bx !== null && ut.length){
    const g = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(bx, 0.9, W - by), new THREE.Vector3(ut[0][0], 1.0, W - ut[0][1])]);
    const l = new THREE.Line(g, new THREE.LineDashedMaterial({color: 0xffffff, dashSize: 0.4, gapSize: 0.25}));
    l.computeLineDistances(); kontraCsoport.add(l);
  }
  if (lx !== null){
    const g = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(lx, 1.2, W - ly), new THREE.Vector3(gx, 1.0, W - gy)]);
    kontraCsoport.add(new THREE.Line(g, new THREE.LineBasicMaterial({color: 0xd9b544})));
  }
  return (kontraCsoport.userData.szoveg = kontraFelirat(d, ADAT.home, ADAT.away));
}

// ---- Kapott gólok: minden kapott gól a védekezés olvasatával -----------
// ◀ ▶ a kapott gólok közt ugrik (1,5 mp-cel az elengedés előtt, lejátszva);
// a pillanat körül gyűrű a lövő körül (a lövő csapat színével), szaggatott
// vonal a legközelebbi védőhöz (piros, ha a lövő szabadon lőtt — a 2 m-es
// fedezés-sugáron kívül —, különben szürke), a kapus helye lila gyűrűvel
// és vonal a kapu közepéig (a mélysége), arany vonal a lövéstől a kapuig;
// a felirat a védekezés olvasatával (court3d.conceded_goal_moments — a
// védekezés-elemzés gól-sorai, a lövés-mérés sávja, a kapus-kimozdulás
// mélysége). A sor 2. eleme a VÉDEKEZŐ csapat — a "Kinek a hibái" szűrő
// erre szűr; a lövő a másik csapat.
const KAPOTTAK = ADAT.conceded_goals || [];
const kapottCsoport = new THREE.Group();
szinpad.add(kapottCsoport);
let kapottUtolso = null;
function kapottUgras(irany){
  if (!szurt(KAPOTTAK).length) return;
  const cel = lapozCel(szurt(KAPOTTAK).map(d => d[0]), ido, kapottUtolso, irany);
  if (cel === null) return;
  kapottUtolso = cel;
  ido = Math.max(0, cel - 1.5); megy = true; lejatszasGomb.textContent = "⏸";
  csuszka.value = ido;
}
document.getElementById("kapottElozo").onclick = () => kapottUgras(-1);
document.getElementById("kapottKov").onclick = () => kapottUgras(1);
function kapottGyuru(x, y, r, szin){
  const g = new THREE.Mesh(new THREE.RingGeometry(r - 0.06, r + 0.04, 36),
    new THREE.MeshBasicMaterial({color: szin, side: THREE.DoubleSide, transparent: true, opacity: 0.9}));
  g.rotation.x = -Math.PI/2; g.position.set(x, 0.04, W - y);
  return g;
}
function kapottFrissit(t){
  const d = szurt(KAPOTTAK).find(x => t >= x[0] - 0.3 && t <= x[0] + 2.5);
  // Csak jelenet-váltáskor rajzolunk újra (a hurok minden kockán hív).
  if (kapottCsoport.userData.kesz && kapottCsoport.userData.d === d) return kapottCsoport.userData.szoveg;
  csoportUrit(kapottCsoport); kapottCsoport.userData.kesz = true; kapottCsoport.userData.d = d; kapottCsoport.userData.szoveg = null;
  if (!d) return null;
  const [s, defHazai, mez, lx, ly, sav, szog, tav, dx, dy, dtav, szabad, kx, ky, mely, kint, xg, gx, gy] = d;
  const szin = defHazai ? 0xff6b6b : 0x4c9aff;  // a LÖVŐ csapat színe
  const vonal = (x1, y1, h1, x2, y2, h2, anyag) => {
    const g = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(x1, h1, W - y1), new THREE.Vector3(x2, h2, W - y2)]);
    const l = new THREE.Line(g, anyag);
    if (anyag.isLineDashedMaterial) l.computeLineDistances();
    kapottCsoport.add(l);
  };
  kapottCsoport.add(kapottGyuru(lx, ly, 0.7, szin));
  if (dx !== null) vonal(lx, ly, 0.05, dx, dy, 0.05,
    new THREE.LineDashedMaterial({color: szabad === 1 ? 0xff6b6b : 0x9aa7b4, dashSize: 0.3, gapSize: 0.2}));
  if (kx !== null){
    kapottCsoport.add(kapottGyuru(kx, ky, 0.5, 0xc084fc));
    vonal(kx, ky, 0.05, gx, gy, 0.05, new THREE.LineBasicMaterial({color: 0xc084fc}));
  }
  vonal(lx, ly, 1.2, gx, gy, 1.0, new THREE.LineBasicMaterial({color: 0xd9b544}));
  return (kapottCsoport.userData.szoveg = kapottFelirat(d, ADAT.home, ADAT.away));
}

// ---- Hétméteresek: a dobó, az irány, a kimenet és a kapus ---------------
// ◀ ▶ a hetesek közt ugrik (1,5 mp-cel az álló labda előtt, lejátszva); a
// pillanat körül X a 7 m-es ponton, arany vonal a dobótól (vagy a ponttól)
// a célzott kapu-harmadba, a kapus lila gyűrűvel és vonal a kapu közepéig
// (a mélysége); a felirat a mezszámmal, az iránnyal, a kimenettel és a
// kapus mélységével (court3d.seven_meter_moments — a seven_meter_outcomes
// párosítása és iránya). Nem hiba-lapozó: a szűrő nem érinti.
const HETESEK = ADAT.sevens || [];
const hetesCsoport = new THREE.Group();
szinpad.add(hetesCsoport);
document.getElementById("hetesInfo").textContent = HETESEK.length ? HETESEK.length + " hetes" : "nincs ilyen";
let hetesUtolso = null;
function hetesUgras(irany){
  if (!HETESEK.length) return;
  const cel = lapozCel(HETESEK.map(d => d[0]), ido, hetesUtolso, irany);
  if (cel === null) return;
  hetesUtolso = cel;
  ido = Math.max(0, cel - 1.5); megy = true; lejatszasGomb.textContent = "⏸";
  csuszka.value = ido;
}
document.getElementById("hetesElozo").onclick = () => hetesUgras(-1);
document.getElementById("hetesKov").onclick = () => hetesUgras(1);
function hetesFrissit(t){
  const d = HETESEK.find(x => t >= x[0] - 0.3 && t <= (x[16] !== null ? x[16] : x[0]) + 2.5);
  // Csak jelenet-váltáskor rajzolunk újra (a hurok minden kockán hív).
  if (hetesCsoport.userData.kesz && hetesCsoport.userData.d === d) return hetesCsoport.userData.szoveg;
  csoportUrit(hetesCsoport); hetesCsoport.userData.kesz = true; hetesCsoport.userData.d = d; hetesCsoport.userData.szoveg = null;
  if (!d) return null;
  const [s, hazai, mez, px, py, lx, ly, kim, ir, cx, cy, kx, ky, mely, gx, gy] = d;
  const vonal = (x1, y1, h1, x2, y2, h2, szin) => {
    const g = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(x1, h1, W - y1), new THREE.Vector3(x2, h2, W - y2)]);
    hetesCsoport.add(new THREE.Line(g, new THREE.LineBasicMaterial({color: szin})));
  };
  if (px !== null){
    for (const [ax, ay, bx, by] of [[-0.4, -0.4, 0.4, 0.4], [-0.4, 0.4, 0.4, -0.4]])
      vonal(px + ax, py + ay, 0.06, px + bx, py + by, 0.06, 0x7dd3fc);
  }
  const ox = lx !== null ? lx : px, oy = lx !== null ? ly : py;
  if (ox !== null && cx !== null) vonal(ox, oy, 1.2, cx, cy, 1.0, 0xd9b544);
  if (kx !== null){
    const gy0 = new THREE.Mesh(new THREE.RingGeometry(0.44, 0.54, 36),
      new THREE.MeshBasicMaterial({color: 0xc084fc, side: THREE.DoubleSide, transparent: true, opacity: 0.9}));
    gy0.rotation.x = -Math.PI/2; gy0.position.set(kx, 0.04, W - ky);
    hetesCsoport.add(gy0);
    vonal(kx, ky, 0.05, gx, gy, 0.05, 0xc084fc);
  }
  return (hetesCsoport.userData.szoveg = hetesFelirat(d, ADAT.home, ADAT.away));
}

// ---- Jelenet-lista: a jelenet-lapozók jelenetei egy listában -----------
// A szűrt döntés-, szabad-lövés- és labdavesztés-pillanatok időrendben;
// katt egy sorra: odaugrik (1,5 mp-cel előtte, lejátszva), és a sor
// lapozója onnan lép tovább. Az épp aktív jelenet sora kiemelve.
const jelenetLista = document.getElementById("jelenetLista");
const jelenetGomb = document.getElementById("jelenetGomb");
const sugoElem = document.getElementById("sugo");
// A súgó ki/be: keskeny ablakban alapból csukva (a pálya jobb harmadát
// takarta); a jelenet-lista a helyén nyílik, addig a súgó rejtve marad,
// de a lista bezárása után a felhasználó állapota tér vissza.
const sugoGomb = document.getElementById("sugoGomb");
// A súgó: a böngésző megjegyzi a választást; először csak széles (1600 px
// fölötti) ablakban nyílik magától — mára akkora, hogy kisebben a kép felét
// takarná.
let sugoNyitva = (() => {
  try { const v = localStorage.getItem("sm3d.sugo"); if (v !== null) return v === "1"; }
  catch (e) { /* tárhely nélkül az alapérték */ }
  return innerWidth >= 1600;
})();
function sugoMent(){ try { localStorage.setItem("sm3d.sugo", sugoNyitva ? "1" : "0"); } catch (e) {} }
// A vezérlőpanel (☰ / M): elrejthető, a böngésző megjegyzi.
const panelElem = document.getElementById("eszkoz");
const panelGomb = document.getElementById("panelGomb");
let panelCsukva = (() => { try { return localStorage.getItem("sm3d.panel") === "0"; } catch (e) { return false; } })();
function panelAllit(csukva){
  panelCsukva = !!csukva;
  panelElem.classList.toggle("csukva", panelCsukva);
  panelGomb.classList.toggle("be", panelCsukva);
  panelGomb.textContent = panelCsukva ? "☰ Panel" : "☰";
  try { localStorage.setItem("sm3d.panel", panelCsukva ? "0" : "1"); } catch (e) {}
}
panelGomb.onclick = () => panelAllit(!panelCsukva);
panelAllit(panelCsukva);
window.panelProba = () => ({csukva: panelCsukva, latszik: getComputedStyle(panelElem).display !== "none",
                           sugo: sugoNyitva});
function sugoAllit(){
  const lathato = sugoNyitva && jelenetLista.style.display !== "block";
  sugoElem.style.display = lathato ? "" : "none";
  sugoGomb.textContent = sugoNyitva ? "Súgó ▴" : "Súgó ▾";
}
sugoGomb.onclick = () => { sugoNyitva = !sugoNyitva; sugoMent(); sugoAllit(); };
sugoAllit();
const JL_SZIN = {d: "#d9b544", sz: "#ff6b6b", e: "#ff9f43", k: "#59d98c", kg: "#c084fc", n: "#e8eef5"};
let jelenetSorokAkt = [], jelenetAktiv = -2;
const jelenetSorokElem = document.createElement("div");  // a sorok (a fejléc alatt)
// A jelenet-lista sorai a két szűrővel ("Kinek a hibái", "Videózandó") —
// a lista, az N/P (VR-kontroller) és a vetítés közös forrása.
function jelenetSorokSzurt(){
  // "Jegyzeteim": csak az edző jegyzetei — a vetítés a megjelölt
  // pillanatokat játssza, a csapat-megbeszélés válogatását.
  const sorok = csakJegyzet ? [] : kulcsSzur(jelenetSorok(szurt(DONTESEK), szurt(SZABADOK), szurt(ELADASOK),
    ADAT.home, ADAT.away, szurt(KONTRAK), szurt(KAPOTTAK)));
  // Az edző jegyzetei minden szűrővel a listában (a saját válogatása):
  // időrendben, az azonos pillanatú jelenet-sor UTÁN.
  for (const j of jegyzetek){
    let i = sorok.length;
    while (i > 0 && sorok[i - 1].s > j.s) i--;
    sorok.splice(i, 0, {s: j.s, ido: jegyzetIdo(j.s), tipus: "n",
                        szoveg: "Jegyzet: " + j.text + (j.rajz.length ? " ✎" : ""), gol: false, id: j.id});
  }
  return sorok;
}

// ---- Videó: a valódi felvétel a 3D mellett ------------------------------
// A "📺 Videó" (K) a forrás-videó épp nézett kockáját mutatja (a motor
// /frame végpontja, JPEG): kép a képben a sarokban, és egy kivetítőn a
// túlsó oldalvonal fölött — VR-ben ez látszik. Szinkronban a lejátszással:
// új kockát akkor kér, ha az előző megjött és az idő azóta lépett (a motor
// tempójában — nem torlódik). A kocka-szám a lejátszási idő × képráta (a
// tömör adat "fps"-e, mint a jegyzeteknél).
const videoGomb = document.getElementById("videoGomb");
const videoAblak = document.getElementById("videoAblak");
const videoKep = document.getElementById("videoKep");
const videoInfo = document.getElementById("videoInfo");
// A kivetítő textúrája egy ÁLLANDÓ méretű vászon (a megjött kocka ide
// másolódik): a textúra nem a képhez kötött, mert a kép új kockát tölt,
// mialatt a renderelő feltöltene — eltérő mérettel a WebGL elutasítja.
const videoVaszon = document.createElement("canvas");
videoVaszon.width = 640; videoVaszon.height = 360;
const videoKtx = videoVaszon.getContext("2d");
const videoTextura = new THREE.CanvasTexture(videoVaszon);
videoTextura.colorSpace = THREE.SRGBColorSpace;
// A kivetítő: 10 × 5,6 m-es vászon a túlsó oldalvonal mögött, 7 m magasan,
// a pálya felé fordulva.
const kivetito = new THREE.Mesh(new THREE.PlaneGeometry(10, 5.6),
  new THREE.MeshBasicMaterial({map: videoTextura, side: THREE.DoubleSide}));
kivetito.position.set(H / 2, 7, -6); kivetito.visible = false;
szinpad.add(kivetito);
let videoBe = false, videoToltes = false, videoKert = null, videoVolt = false;
// Nincs felvétel ezen a gépen (az első kocka sem jött): nem kérünk újra
// minden kockán — a K (újra bekapcsolás) próbálja újra.
let videoNincs = false;
function videoAllit(be){
  videoBe = !!be && !!ADAT.match_id;
  videoGomb.classList.toggle("be", videoBe);
  videoAblak.style.display = videoBe ? "block" : "none";
  kivetito.visible = videoBe && videoVolt;
  if (videoBe){ videoKert = null; videoNincs = false; }  // azonnal kér
  if (!!be && !ADAT.match_id){ videoAblak.style.display = "block"; videoInfo.textContent = "a videóhoz a motor kell"; }
}
function videoFrissit(t){
  if (!videoBe || videoToltes || videoNincs) return;
  const kocka = Math.max(0, Math.round(t * FPS));
  if (kocka === videoKert) return;
  videoKert = kocka; videoToltes = true;
  videoKep.src = "/matches/" + encodeURIComponent(ADAT.match_id) + "/frame?t=" + kocka + "&w=640";
}
videoKep.onload = () => {
  videoToltes = false; videoVolt = true; videoInfo.textContent = "";
  videoKtx.drawImage(videoKep, 0, 0, videoVaszon.width, videoVaszon.height);
  videoTextura.needsUpdate = true; kivetito.visible = videoBe;
};
videoKep.onerror = () => {
  videoToltes = false;
  // Ha már volt kép, csak ez az egy kocka hiányzik (pl. a videó vége):
  // a következő kockánál továbblép. Ha az első sem jött, megállunk.
  if (videoVolt) return;
  videoNincs = true;
  videoInfo.textContent = "a videó nem érhető el ezen a gépen (K: újra)";
};
videoGomb.onclick = () => videoAllit(!videoBe);
window.videoProba = () => ({be: videoBe, kert: videoKert, kivetito: kivetito.visible, info: videoInfo.textContent});

// ---- Közös nézés: az edző vezet, a csapat headsetjei követik ----------
// A "📡 Vezetem" a lejátszás állapotát (idő, megy-e, sebesség, rajz) a
// motorra küldi; a "👥 Követem" (a csapat linkje: kovet=1) ezt kérdezi és
// követi — mindenki a saját helyéről, a saját kamerájával nézi ugyanazt a
// pillanatot: a pálya bejárható, az edző mutatja a szituációt. A követő a
// vezető mostani idejét a válasz KORÁBÓL becsli (az órák eltérése nélkül),
// és csak KZ_TURES mp-nél nagyobb eltérésnél ugrik (court3d.SHARED3D_*).
const KZ_KULD = __KZ_KULD__, KZ_KERD = __KZ_KERD__, KZ_TURES = __KZ_TURES__;
const vezetGomb = document.getElementById("vezetGomb");
const kovetGomb = document.getElementById("kovetGomb");
const kozosInfo = document.getElementById("kozosInfo");
let kozosMod = null;  // null | "vezet" | "kovet"
let kzUton = false, kzUtolso = 0, kzRajz = null;
// A követő véletlen azonosítója (a vezető ebből látja, hányan követik), a
// vezető oldalán a csapat linkje és a követők száma.
const KZ_KID = Math.random().toString(36).slice(2, 12) || "k";
// A követő neve (a csapat linkjén: /kovet?nev=Peti) — a többiek a feje
// fölött látják; név nélkül a csatlakozás sorszáma (#3).
let KZ_NEV = (URL_PARAM.get("nev") || "").trim().slice(0, __KZ_NEV_MAX__);
let kzLink = "", kzVagolap = false, kzKovetok = null;
// JELENLÉT: a saját kamera helye és iránya a csapatnak (three-tér; a yaw
// a rig-forgatás szöge — a nézés iránya (−sin yaw, −cos yaw)). VR-ben a
// fej valódi helye (a kamera világ-helye).
const kzHelyV = new THREE.Vector3(), kzIranyV = new THREE.Vector3();
function sajatHely(){
  kamera.getWorldPosition(kzHelyV); kamera.getWorldDirection(kzIranyV);
  const k = (v) => Math.round(v * 100) / 100;
  return [k(kzHelyV.x), k(kzHelyV.y), k(kzHelyV.z),
          Math.round(Math.atan2(-kzIranyV.x, -kzIranyV.z) * 1000) / 1000];
}
// A többiek a csarnokban: fej (az edzőé arany, a csapaté fehér), orr a
// nézés irányába, gyűrű a padlón, fölötte a név (vagy a csatlakozás
// sorszáma). A saját kamerához KZ_KOZEL m-nél közelebbi nem látszik ("Ide
// mindenki" után mindenki egy helyen áll — nem a fejünkben ül). A hely a
// kérdések közt simítva mozog.
const KZ_KOZEL = __KZ_KOZEL__;
const avatarok = new Map();  // kulcs ("e" a vezető, "k<sorszám>") → csoport
const AV_FEJ = new THREE.SphereGeometry(0.16, 16, 12);
const AV_ORR = new THREE.ConeGeometry(0.06, 0.2, 10);
const AV_GYURU = new THREE.RingGeometry(0.22, 0.3, 24);
const avAnyag = (szin, fenyl) => new THREE.MeshStandardMaterial({color: szin, emissive: fenyl});
const AV_ANYAG = {e: avAnyag(0xffc83d, 0x4a3500), k: avAnyag(0xf2f5f8, 0x202830)};
const avGyuruAnyag = (szin) => new THREE.MeshBasicMaterial({color: szin, transparent: true,
  opacity: 0.6, side: THREE.DoubleSide, depthWrite: false});
const AV_GYURU_ANYAG = {e: avGyuruAnyag(0xffc83d), k: avGyuruAnyag(0xf2f5f8)};
function avatarCimke(szoveg, edzo){
  const c = document.createElement("canvas"); c.width = 256; c.height = 64;
  const g = c.getContext("2d");
  g.fillStyle = edzo ? "rgba(120,90,0,0.85)" : "rgba(10,14,20,0.8)";
  g.beginPath(); g.roundRect(2, 2, 252, 60, 16); g.fill();
  g.fillStyle = "#ffffff"; g.font = "bold 32px sans-serif";
  g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(szoveg, 128, 34, 240);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: new THREE.CanvasTexture(c), transparent: true}));
  sp.scale.set(1.0, 0.25, 1);
  return sp;
}
function avatarUj(cimke, edzo){
  const f = edzo ? "e" : "k";
  const cs = new THREE.Group();     // a padlón (x, 0, z)
  const fejCs = new THREE.Group();  // a fej magasságában, a nézés irányába
  fejCs.add(new THREE.Mesh(AV_FEJ, AV_ANYAG[f]));
  // A kúp csúcsa a +y; −90°-kal a −z (a nézés iránya) felé fordul.
  const orr = new THREE.Mesh(AV_ORR, AV_ANYAG[f]);
  orr.rotation.x = -Math.PI / 2; orr.position.z = -0.2; fejCs.add(orr);
  cs.add(fejCs);
  const gyuru = new THREE.Mesh(AV_GYURU, AV_GYURU_ANYAG[f]);
  gyuru.rotation.x = -Math.PI / 2; gyuru.position.y = 0.03; cs.add(gyuru);
  const cimkeSp = avatarCimke(cimke, edzo); cs.add(cimkeSp);
  cs.userData = {fejCs, cimkeSp, cimke, cel: null, uj: true};
  szinpad.add(cs);
  return cs;
}
function avatarTorol(kulcs){
  const cs = avatarok.get(kulcs);
  if (!cs) return;
  szinpad.remove(cs);
  cs.userData.cimkeSp.material.map.dispose(); cs.userData.cimkeSp.material.dispose();
  avatarok.delete(kulcs);
}
// lista: [{kulcs, cimke, edzo, hely: [x, y, z, yaw]}] — az eltűntek törlődnek.
function jelenletAllit(lista){
  const latott = new Set();
  for (const e of lista){
    latott.add(e.kulcs);
    let cs = avatarok.get(e.kulcs);
    if (cs && cs.userData.cimke !== e.cimke){ avatarTorol(e.kulcs); cs = null; }
    if (!cs){ cs = avatarUj(e.cimke, e.edzo); avatarok.set(e.kulcs, cs); }
    cs.userData.cel = e.hely;
  }
  for (const k of [...avatarok.keys()]) if (!latott.has(k)) avatarTorol(k);
}
function kzLista(csapat, vezeto){
  const l = (csapat || []).map(e => ({kulcs: "k" + e.sz,
                                     cimke: (e.kez ? "✋ " : "") + (e.nev || ("#" + e.sz)),
                                     edzo: false, hely: e.hely}));
  if (vezeto) l.push({kulcs: "e", cimke: "Edző", edzo: true, hely: vezeto});
  return l;
}
function jelenletFrissit(dt){
  if (!avatarok.size) return;
  kamera.getWorldPosition(kzHelyV);
  const a = Math.min(1, dt * 8);
  for (const cs of avatarok.values()){
    const u = cs.userData, c = u.cel;
    if (!c) continue;
    if (u.uj){
      cs.position.set(c[0], 0, c[2]); u.fejCs.position.y = c[1]; u.fejCs.rotation.y = c[3];
      u.uj = false;
    } else {
      cs.position.x += (c[0] - cs.position.x) * a;
      cs.position.z += (c[2] - cs.position.z) * a;
      u.fejCs.position.y += (c[1] - u.fejCs.position.y) * a;
      const d = c[3] - u.fejCs.rotation.y;  // a rövidebb úton fordul
      u.fejCs.rotation.y += Math.atan2(Math.sin(d), Math.cos(d)) * a;
    }
    const dx = cs.position.x - kzHelyV.x, dy = u.fejCs.position.y - kzHelyV.y,
          dz = cs.position.z - kzHelyV.z;
    const tav = Math.sqrt(dx * dx + dy * dy + dz * dz);
    cs.visible = tav > KZ_KOZEL;
    // A név messziről is olvasható: 10 m-en túl a távolsággal nő.
    const s = Math.max(1, tav / 10);
    u.cimkeSp.scale.set(s, 0.25 * s, 1);
    u.cimkeSp.position.y = u.fejCs.position.y + 0.3 + 0.12 * s;
  }
}
window.jelenletProba = () => [...avatarok.entries()].map(([k, cs]) => ({
  kulcs: k, cimke: cs.userData.cimke, latszik: cs.visible,
  x: cs.position.x, y: cs.userData.fejCs.position.y, z: cs.position.z,
  yaw: cs.userData.fejCs.rotation.y}));
window.sajatHelyProba = () => sajatHely();
let kzValaszDb = 0;  // a kvíz aktuális körére válaszolók (a motor szerint)
let kzJoDb = 0;      // közülük a jobb opciót mutatók (döntés-kvízben)
let kzVezetoCsapat = [];  // a motor legutóbbi csapat-listája (a vezetőnek)
// ✋ A kérdezni akarók (a vezetőnek): a motor legutóbbi csapat-listájából.
const kzKezek = () => kzVezetoCsapat.filter(e => e.kez).map(e => e.nev || ("#" + e.sz));
function kzVezetoInfo(){
  const kezek = kzKezek();
  kozosInfo.textContent = "📡 vezetsz" + (kzKovetok == null ? "" : " · " + kzKovetok + " követő")
    + (kezek.length ? " · ✋ " + kezek.join(", ") : "")
    + (kzKviz ? " · ❓ " + kzValaszDb + "/" + (kzKovetok || 0) + " válasz" : "")
    + (kzKviz && kvizDontes(kzKviz) ? " · ✓ " + kzJoDb + " a jobb opció" : "")
    + (kzFelvetel ? " · ⏺" + (kzFelvetel.hang ? "🎙 " : " ")
                      + fvOra((performance.now() - kzFelvetel.kezd) / 1000) : "")
    + (fvUzenet && performance.now() - fvUzenet.ido < FV_UZENET_MS ? " · " + fvUzenet.szoveg : "")
    + " — a csapat linkje: " + kzLink + (kzVagolap ? " (vágólapon)" : "");
}
// A követő állapot-szövege és a váltás ideje: a VR-tábla a váltás után
// KZ_VR_MS-ig mutatja (a "követed" nem ül végig a szem előtt), a
// hiba-állapotot ("nincs vezető", "nem válaszol") végig.
const KZ_KOVETED = "👥 az edzőt követed", KZ_VR_MS = 3000;
let kzInfoValtas = 0;
function kzInfo(s){
  if (kozosInfo.textContent === s) return;
  kozosInfo.textContent = s; kzInfoValtas = performance.now();
}
// MUTATÓ: a vezető Shift+kattintása a padlóra — nála és a követőknél
// KZ_MUTATO mp-ig lüktető gyűrű ott ("nézzétek ide"). A vezető minden
// küldéskor a legutóbbit küldi; a követő az új azonosítóra (n) mutat, és
// csak ha a motor szerint friss (a később csatlakozónál nem villan fel).
const KZ_MUTATO = __KZ_MUTATO__;
let kzMutato = null, kzMutatoN = null, mutatoKezd = 0;
const mutatoGyuru = new THREE.Mesh(new THREE.RingGeometry(0.45, 0.62, 40),
  new THREE.MeshBasicMaterial({color: 0xff4fd8, transparent: true, side: THREE.DoubleSide, depthWrite: false}));
mutatoGyuru.rotation.x = -Math.PI / 2; mutatoGyuru.visible = false;
szinpad.add(mutatoGyuru);
function mutatoMutat(x, y){
  mutatoGyuru.position.set(x, 0.05, W - y);
  mutatoKezd = performance.now(); mutatoGyuru.visible = true;
}
function mutatoKattintas(cx, cy){
  const p = padloPont(cx, cy);
  if (!p) return;
  mutatoBeallit(p[0], p[1]);
}
function mutatoBeallit(x, y){
  kzMutato = {x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10, n: Date.now()};
  mutatoMutat(x, y);
  kzUtolso = 0;  // azonnal megy a csapatnak
}
// VR-mutató: a kontroller sugarának (−z irány) padló-metszete pálya-
// méterben (a pálya ±3 m-es sávjában); null, ha nem a padlóra mutat.
function vrMutatoPont(origo, irany){
  if (irany.y >= -1e-6) return null;
  const k = -origo.y / irany.y;
  const x = origo.x + irany.x * k, y = W - (origo.z + irany.z * k);
  if (x < -3 || x > H + 3 || y < -3 || y > W + 3) return null;
  return [x, y];
}
// Az i-edik kontroller sugarának padló-pontja (vagy null).
function vrSugarPont(i){
  const c = vrKontrollerek[i];
  if (!c) return null;
  const o = new THREE.Vector3(), q = new THREE.Quaternion();
  c.getWorldPosition(o); c.getWorldQuaternion(q);
  // A kontroller sugara a helyi −z (a +z elforgatva, megfordítva — a
  // figurák eleje a +z, azt őr-teszt védi).
  return vrMutatoPont(o, new THREE.Vector3(0, 0, 1).applyQuaternion(q).negate());
}
function vrMutat(i){
  const p = vrSugarPont(i);
  if (p) mutatoBeallit(p[0], p[1]);
}
window.vrMutatoProba = (o, d) => vrMutatoPont(new THREE.Vector3(...o), new THREE.Vector3(...d));
window.vrAlloProba = () => vrAllo.position.y;
// (próbához: a VR-munkamenet kezdete/vége headset nélkül)
window.vrMunkamenetProba = (be) => fest.xr.dispatchEvent({type: be ? "sessionstart" : "sessionend"});
function mutatoFrissit(){
  if (!mutatoGyuru.visible) return;
  const el = (performance.now() - mutatoKezd) / 1000;
  if (el > KZ_MUTATO){ mutatoGyuru.visible = false; return; }
  const f = (el * 1.5) % 1;  // másodpercenként másfél lüktetés
  mutatoGyuru.scale.setScalar(1 + f * 1.6);
  mutatoGyuru.material.opacity = 0.9 * (1 - f) * (1 - 0.5 * el / KZ_MUTATO);
}
window.mutatoProba = () => ({latszik: mutatoGyuru.visible, x: mutatoGyuru.position.x,
                             y: W - mutatoGyuru.position.z, kuld: kzMutato});
// "📍 Ide mindenki": a vezető mostani nézőpontja (a rig helye, az irány)
// a csapatnak — a követő kamerája szabad módba vált, és oda ugrik (VR-ben
// a rig: a fej iránya a sajátja marad). Frissnek a mutatóval azonos
// ideig számít (a később csatlakozót nem rántja el).
let kzNezopont = null, kzNezopontN = null;
// Az ugrás híre a VR-táblán is KZ_VR_MS-ig áll (a következő kérdés nem
// írja felül rögtön a "követed"-del).
const KZ_IDE = "📍 az edző ide hívott";
const ideGomb = document.getElementById("ideGomb");
ideGomb.onclick = () => {
  if (kozosMod !== "vezet") return;
  // (a csarnok dobozában — a motor is oda szorítja)
  kzNezopont = {x: clamp(rig.position.x, -60, 100), y: clamp(rig.position.y, 0.2, 60),
                z: clamp(rig.position.z, -60, 80), yaw: rig.rotation.y,
                pitch: clamp(kamera.rotation.x, -1.6, 1.6), n: Date.now()};
  kzUtolso = 0;
  kozosInfo.textContent = "📍 a csapat ide ugrik";
};
function nezopontAlkalmaz(v){
  modValt("szabad");
  rig.position.set(v.x, v.y, v.z);
  yaw = v.yaw; pitch = v.pitch; rig.rotation.y = yaw;
  if (!fest.xr.isPresenting) kamera.rotation.set(pitch, 0, 0);
  kzInfo(KZ_IDE);
}
window.nezopontProba = () => ({x: rig.position.x, y: rig.position.y, z: rig.position.z, yaw: rig.rotation.y, mod, kuld: kzNezopont});
// ❓ KVÍZ: a vezető megállítja a jelenetet és kérdez ("hova passzolnál?",
// "hol a helyed?"); a követők a padlóra mutatnak (kattintás, VR-ben a
// ravasz a kontroller sugarával) — a vezető névvel látja a válaszokat, a
// második gombnyomásra a csapat is (a harmadikra vége). A motor csak az
// aktuális kör (n) válaszait adja, a csapatnak csak a felfedés után; a
// felfedés után a válasz nem módosítható.
const kvizGomb = document.getElementById("kvizGomb");
let kzKviz = null;        // a vezető köre: {n, mutat}
let kzKvizKor = null;     // a követő által látott kör: {n, mutat}
let kzValasz = null;      // a követő válasza: {x, y, n}
let kzUtolsoCsapat = [];  // a követő utolsó csapat-listája (a motor válasza)
const valaszJelek = new Map();  // kulcs ("v<sorszám>", "sajat") → csoport
const VJ_KOR = new THREE.CircleGeometry(0.32, 24);
const VJ_RUD = new THREE.CylinderGeometry(0.025, 0.025, 1.3, 8);
const vjAnyag = (szin) => new THREE.MeshBasicMaterial({color: szin, transparent: true,
  opacity: 0.85, side: THREE.DoubleSide, depthWrite: false});
const VJ_ANYAG = {masok: vjAnyag(0x3ddcff), sajat: vjAnyag(0xff4fd8)};
function valaszJelUj(cimke, sajat){
  const cs = new THREE.Group();
  const anyag = sajat ? VJ_ANYAG.sajat : VJ_ANYAG.masok;
  const kor = new THREE.Mesh(VJ_KOR, anyag);
  kor.rotation.x = -Math.PI / 2; kor.position.y = 0.04; cs.add(kor);
  const rud = new THREE.Mesh(VJ_RUD, anyag); rud.position.y = 0.65; cs.add(rud);
  const sp = avatarCimke(cimke, false); sp.position.y = 1.5; cs.add(sp);
  cs.userData = {cimke, sp};
  szinpad.add(cs);
  return cs;
}
function valaszJelTorol(kulcs){
  const cs = valaszJelek.get(kulcs);
  if (!cs) return;
  szinpad.remove(cs);
  cs.userData.sp.material.map.dispose(); cs.userData.sp.material.dispose();
  valaszJelek.delete(kulcs);
}
// lista: [{kulcs, cimke, sajat, x, y}] (pálya-méter) — az eltűntek törlődnek.
function valaszokAllit(lista){
  const latott = new Set();
  for (const v of lista){
    latott.add(v.kulcs);
    let cs = valaszJelek.get(v.kulcs);
    if (cs && cs.userData.cimke !== v.cimke){ valaszJelTorol(v.kulcs); cs = null; }
    if (!cs){ cs = valaszJelUj(v.cimke, v.sajat); valaszJelek.set(v.kulcs, cs); }
    cs.position.set(v.x, 0, W - v.y);
  }
  for (const k of [...valaszJelek.keys()]) if (!latott.has(k)) valaszJelTorol(k);
}
// A válasz neve messziről (madártávlatból) is olvasható: 10 m-en túl a
// távolsággal nő — mint a társak neve.
const vjHelyV = new THREE.Vector3();
function valaszJelFrissit(){
  if (!valaszJelek.size) return;
  kamera.getWorldPosition(vjHelyV);
  for (const cs of valaszJelek.values()){
    const sp = cs.userData.sp;
    const tav = Math.hypot(cs.position.x - vjHelyV.x, 1.5 - vjHelyV.y, cs.position.z - vjHelyV.z);
    const s = Math.max(1, tav / 10);
    sp.scale.set(s, 0.25 * s, 1); sp.position.y = 1.4 + 0.12 * s;
  }
}
// DÖNTÉS-KVÍZ: a kör döntés-pillanata (a kvíz indításakor látszó
// Döntések-sor; null: nem döntés-pillanatnál indult) — ehhez mérjük a
// válaszokat (kvizItelet = court3d.quiz_verdict): ✓ a jobb opció.
function kvizDontes(kor){
  if (!kor || kor.d == null) return null;
  return DONTESEK.find(x => Math.abs(x[0] - kor.d) < 0.01) || null;
}
const kvizCimke = (nev, x, y, d) => d ? nev + (kvizItelet(x, y, d) ? " ✓" : " ✗") : nev;
window.kvizDontesProba = () => kvizDontes(kozosMod === "vezet" ? kzKviz : kzKvizKor);
function kzValaszLista(csapat){
  const kor = kozosMod === "vezet" ? kzKviz : kzKvizKor;
  // Az ítélet a vezetőnél azonnal, a csapatnál a felfedés után.
  const d = (kozosMod === "vezet" || (kor && kor.mutat)) ? kvizDontes(kor) : null;
  const l = (csapat || []).filter(e => e.valasz).map(e => ({kulcs: "v" + e.sz,
    cimke: kvizCimke(e.nev || ("#" + e.sz), e.valasz[0], e.valasz[1], d), sajat: false,
    x: e.valasz[0], y: e.valasz[1]}));
  if (kzValasz && kzKvizKor && kzValasz.n === kzKvizKor.n)
    l.push({kulcs: "sajat", cimke: kvizCimke("Te", kzValasz.x, kzValasz.y, d), sajat: true,
            x: kzValasz.x, y: kzValasz.y});
  return l;
}
function kvizGombFelirat(){
  kvizGomb.textContent = !kzKviz ? "❓ Kvíz" : (kzKviz.mutat ? "✖ Kvíz vége" : "👁 Mutasd a csapatnak");
}
kvizGomb.onclick = () => {
  if (kozosMod !== "vezet") return;
  if (!kzKviz){
    // Döntés-pillanatnál (a Döntések felirata látszik) a válaszokat a
    // modell jobb opciójához mérjük.
    const d = szurt(DONTESEK).find(x => ido >= x[0] - 0.3 && ido <= x[0] + 2.5);
    kzKviz = d ? {n: Date.now(), mutat: false, d: d[0]} : {n: Date.now(), mutat: false};
    kzValaszDb = 0; kzJoDb = 0;
    // A kérdés a megállított jeleneten.
    megy = false; lejatszasGomb.textContent = "▶";
  } else if (!kzKviz.mutat) kzKviz = {...kzKviz, mutat: true};
  else { kvizMent(kzKviz, kzVezetoCsapat); kzKviz = null; valaszokAllit([]); }
  kvizGombFelirat(); kzVezetoInfo();
  kzUtolso = 0;  // azonnal megy a csapatnak
};
// A kvíz eredménye a jegyzetek közé (a kvíz végén, ha volt válasz): a
// jegyzet-listában, a nyomtatott jelentésben (ábrával) és a Klipek
// "Jegyzetelt pillanatok" csomagjában is ott van — döntés-kvízben a döntés
// kockáján, a passzolótól a válaszokig húzott nyilakkal (sárga ✓, piros ✗).
async function kvizMent(kor, csapat){
  const valaszolok = (csapat || []).filter(e => e.valasz);
  if (!kor || !valaszolok.length || !ADAT.match_id) return;
  const d = kvizDontes(kor);
  const itelet = (e) => d ? kvizItelet(e.valasz[0], e.valasz[1], d) : null;
  const szoveg = kvizJegyzetSzoveg(valaszolok.map(e => [e.nev || ("#" + e.sz), itelet(e)]),
    d ? d[7] : null, Math.max(0, (kzKovetok || 0) - valaszolok.length));
  const rajz = d ? rajzKodol(valaszolok.map(e => [d[2], d[3], e.valasz[0], e.valasz[1], itelet(e) ? 0 : 2])) : "";
  try {
    const v = await fetch(jegyzetCim(), {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({frame: Math.round((d ? d[0] : ido) * FPS), text: szoveg, rajz,
                            // szerkezetben is — a kvíz-mérleg (Jegyzetek) ebből számol
                            kviz: valaszolok.map(e => ({nev: e.nev || "", itelet: itelet(e)}))})});
    if (!v.ok) throw new Error("a motor " + v.status + "-at válaszolt");
    await jegyzetBetolt();
    jegyzetInfo.textContent = "📝 a kvíz eredménye jegyzetként mentve";
  } catch (e) { jegyzetInfo.textContent = "a kvíz eredménye nem mentődött: " + e.message; }
}
const KZ_KVIZ_KERDES = "❓ Kvíz: mutasd meg a padlón — kattintás (VR: ravasz a kontrollerrel)";
const KZ_KVIZ_KESZ = "❓ a válaszod a padlón — várjuk a többieket (még módosíthatod)";
const KZ_KVIZ_MUTAT = "👁 a csapat válaszai a padlón";
const KZ_KVIZ_JOBB = " — arany vonal: a modell jobb opciója (✓ eltalálta, ✗ nem)";
function kvizSzoveg(){
  if (!kzKvizKor) return KZ_KOVETED;
  if (kzKvizKor.mutat) return KZ_KVIZ_MUTAT + (kvizDontes(kzKvizKor) ? KZ_KVIZ_JOBB : "");
  return (kzValasz && kzValasz.n === kzKvizKor.n) ? KZ_KVIZ_KESZ : KZ_KVIZ_KERDES;
}
// A követő válasza (a felfedésig módosítható) — azonnal megy a motornak.
function valaszBeallit(x, y){
  if (kozosMod !== "kovet" || !kzKvizKor || kzKvizKor.mutat) return;
  kzValasz = {x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10, n: kzKvizKor.n};
  kzUtolso = 0;
  kzInfo(kvizSzoveg());
  valaszokAllit(kzValaszLista(kzUtolsoCsapat));
}
function valaszKattintas(cx, cy){
  const p = padloPont(cx, cy);
  if (p) valaszBeallit(p[0], p[1]);
}
function vrValasz(i){
  const p = vrSugarPont(i);
  if (p) valaszBeallit(p[0], p[1]);
}
const kvizValaszolhat = () => kozosMod === "kovet" && !!kzKvizKor && !kzKvizKor.mutat;
window.kvizProba = () => ({kviz: kzKviz, kor: kzKvizKor, valasz: kzValasz, gomb: kvizGomb.textContent,
  tiltva: kvizGomb.disabled, info: kozosInfo.textContent,
  jelek: [...valaszJelek.entries()].map(([k, cs]) => ({kulcs: k, cimke: cs.userData.cimke,
    x: Math.round(cs.position.x * 10) / 10, y: Math.round((W - cs.position.z) * 10) / 10}))});
window.valaszProba = (x, y) => valaszBeallit(x, y);
// "Ki vagy?" — a követő a keretben felvitt nevek közül választ (a headset
// billentyűzetén gépelni nehéz); a pontos név köti a kvíz-mérleget a
// kerethez. A választás a címbe is kerül (újratöltés után is megmarad).
const kzNevValaszto = document.getElementById("kzNevValaszto");
let kzNevekBetoltve = false;
async function nevValasztoMutat(be){
  kzNevValaszto.style.display = be ? "" : "none";
  if (!be || kzNevekBetoltve || !ADAT.match_id) return;
  kzNevekBetoltve = true;
  try {
    const v = await fetch("/library/players");
    const d = v.ok ? await v.json() : {};
    const opciok = [["", "— ki vagy? (a neved a kvízhez és a felvételekhez) —"]];
    for (const csapat of [ADAT.home, ADAT.away]){
      const nevek = (d.players || {})[csapat] || {};
      for (const [mez, nev] of Object.entries(nevek).sort((a, b) => Number(a[0]) - Number(b[0])))
        if (nev) opciok.push([String(nev).trim().slice(0, __KZ_NEV_MAX__), csapat + " " + mez + " — " + nev]);
    }
    if (KZ_NEV && !opciok.some(o => o[0] === KZ_NEV)) opciok.push([KZ_NEV, KZ_NEV]);
    kzNevValaszto.textContent = "";
    for (const [ertek, felirat] of opciok){
      const o = document.createElement("option"); o.value = ertek; o.textContent = felirat;
      kzNevValaszto.appendChild(o);
    }
    kzNevValaszto.value = KZ_NEV;
  } catch (e) { kzNevekBetoltve = false; }
}
kzNevValaszto.onchange = () => {
  KZ_NEV = kzNevValaszto.value;
  const q = new URLSearchParams(location.search);
  if (KZ_NEV) q.set("nev", KZ_NEV); else q.delete("nev");
  history.replaceState(null, "", location.pathname + "?" + q.toString());
  kzUtolso = 0;  // a név azonnal megy
};
const kzCim = () => "/matches/" + encodeURIComponent(ADAT.match_id) + "/shared3d";
function kozosAllit(m){
  if (!ADAT.match_id){ kozosInfo.textContent = "a közös nézéshez a motor kell"; return; }
  const elozo = kozosMod;
  kozosMod = (m === kozosMod) ? null : m;
  felvetelAll();
  if (elozo === "vezet" && kozosMod !== "vezet" && kzFelvetel) felvetelMent();
  // A leálló vezető szól: a követők nem a régi állapotot követik tovább.
  if (elozo === "vezet" && kozosMod !== "vezet")
    fetch(kzCim(), {method: "DELETE"}).catch(() => {});
  vezetGomb.classList.toggle("be", kozosMod === "vezet");
  kovetGomb.classList.toggle("be", kozosMod === "kovet");
  // Új vezetés: a régi mutató nem megy újra a csapatnak.
  kzRajz = null; kzUtolso = 0; kzMutato = null; kzNezopont = null;
  jelenletAllit([]);
  kzKviz = null; kzKvizKor = null; kzValasz = null; kzUtolsoCsapat = [];
  valaszokAllit([]); kvizGombFelirat();
  ideGomb.disabled = kozosMod !== "vezet";
  kvizGomb.disabled = kozosMod !== "vezet";
  kezGomb.style.display = kozosMod === "kovet" ? "" : "none";
  kezAllit(false);
  felvetelGombFelirat();
  nevValasztoMutat(kozosMod === "kovet");
  if (kozosMod === "vezet"){
    // A rövid csapat-link (a motor /kovet címe az élő közös nézésre
    // irányít) — a headset billentyűzetén begépelhető.
    kzLink = location.origin + "/kovet";
    kzVagolap = false; kzKovetok = null; kzVezetoInfo();
    if (navigator.clipboard) navigator.clipboard.writeText(kzLink).then(
      () => { kzVagolap = true; if (kozosMod === "vezet") kzVezetoInfo(); }, () => {});
    // Hálózati módban (a motor a klub-hálózat felé nyitva) a headsetek a
    // gép HÁLÓZATI címét érik el, nem a localhost-ot — a motor megmondja.
    fetch("/halozat").then(r => r.ok ? r.json() : null).then(h => {
      if (!h || !h.halozati || !(h.linkek || []).length || kozosMod !== "vezet") return;
      kzLink = h.linkek[0]; kzVagolap = false; kzVezetoInfo();
      if (navigator.clipboard) navigator.clipboard.writeText(kzLink).then(
        () => { kzVagolap = true; if (kozosMod === "vezet") kzVezetoInfo(); }, () => {});
    }).catch(() => {});
  } else if (kozosMod === "kovet"){
    // A követő saját vetítése a vezetővel versenyezne.
    if (vetites) vetitesAllit(false);
    kzInfo("👥 várakozás az edzőre…");
  } else kozosInfo.textContent = "";
}
function kozosFrissit(){
  if (!kozosMod || kzUton) return;
  const most = performance.now() / 1000;
  if (most - kzUtolso < (kozosMod === "vezet" ? KZ_KULD : KZ_KERD)) return;
  kzUtolso = most; kzUton = true;
  if (kozosMod === "vezet"){
    felvetelRogzit();
    fetch(kzCim(), {method: "PUT", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({t: ido, playing: megy, speed: sebesseg, rajz: rajzKodol(rajzok), kviz: kzKviz, hely: sajatHely(), mutato: kzMutato, nezopont: kzNezopont})})
      .then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(a => { if (kozosMod === "vezet"){ kzKovetok = a.followers;
                                            kzVezetoCsapat = a.csapat || [];
                                            if (kzFelvetel && kzFelvetel.jelen)
                                              for (const e of kzVezetoCsapat) if (e.nev) kzFelvetel.jelen.add(e.nev);
                                            kzValaszDb = kzVezetoCsapat.filter(e => e.valasz).length;
                                            const kd = kvizDontes(kzKviz);
                                            kzJoDb = kd ? (a.csapat || []).filter(
                                              e => e.valasz && kvizItelet(e.valasz[0], e.valasz[1], kd)).length : 0;
                                            kzVezetoInfo();
                                            jelenletAllit(kzLista(a.csapat, null));
                                            valaszokAllit(kzKviz ? kzValaszLista(a.csapat) : []); } })
      // Hibánál a mutató és a nézőpont nem megy újra (ha az okozta, a
      // következő küldés már átmegy).
      .catch(() => { kzMutato = null; kzNezopont = null;
                     if (kozosMod === "vezet") kozosInfo.textContent = "📡 a vezetés nem jut el a motorhoz"; })
      .finally(() => { kzUton = false; });
    return;
  }
  fetch(kzCim() + "?kid=" + KZ_KID + "&hely=" + sajatHely().join(",")
        + (KZ_NEV ? "&nev=" + encodeURIComponent(KZ_NEV) : "")
        + (kzKez ? "&kez=1" : "")
        + (kzValasz ? "&valasz=" + [kzValasz.x, kzValasz.y, kzValasz.n].join(",") : ""),
        {cache: "no-store"}).then(r => r.json()).then(a => {
    if (kozosMod !== "kovet") return;
    if (!a.active){
      jelenletAllit([]); kzKvizKor = null; kzValasz = null; valaszokAllit([]);
      kzInfo("👥 nincs vezető — az edző nem vezet (vagy bezárta)"); return;
    }
    jelenletAllit(kzLista(a.csapat, a.vezeto_hely));
    // A kvíz: új kör — a régi válasz törlődik; vége — a jelek is.
    kzUtolsoCsapat = a.csapat || [];
    kzKvizKor = a.kviz || null;
    if (kzValasz && (!kzKvizKor || kzValasz.n !== kzKvizKor.n)) kzValasz = null;
    valaszokAllit(kzKvizKor ? kzValaszLista(kzUtolsoCsapat) : []);
    if (!(kozosInfo.textContent === KZ_IDE && performance.now() - kzInfoValtas < KZ_VR_MS))
      kzInfo(kvizSzoveg() + (kzKez ? KZ_KEZ_JEL : ""));
    kzAllapotAlkalmaz(a);
  }).catch(() => { if (kozosMod === "kovet") kzInfo("👥 a motor nem válaszol"); })
    .finally(() => { kzUton = false; });
}
// ✋ KÉRDÉSEM VAN (követőként): a motor a jelenlét-sorban viszi — a vezető
// a fejünk fölött, a felirat-sorban és VR-ben a tábláján látja.
const kezGomb = document.getElementById("kezGomb");
const KZ_KEZ_JEL = " · ✋ jelezted — az edző látja";
let kzKez = false;
function kezAllit(be){
  kzKez = !!be && kozosMod === "kovet";
  kezGomb.textContent = kzKez ? "✋ Kéz le" : "✋ Kérdésem van";
  kezGomb.classList.toggle("be", kzKez);
  kzUtolso = 0;  // azonnal megy
  if (kozosMod === "kovet") kzInfo(kvizSzoveg() + (kzKez ? KZ_KEZ_JEL : ""));
}
kezGomb.onclick = () => kezAllit(!kzKez);
window.kezProba = () => ({kez: kzKez, gomb: kezGomb.textContent,
  latszik: kezGomb.style.display !== "none", info: kozosInfo.textContent});
// A vezető állapotának alkalmazása (a követő és a felvétel-visszajátszás
// közös útja): az idő a korral (csak KZ_TURES-nél nagyobb eltérésnél
// ugrik), szünet, sebesség, rajz, a friss mutató és nézőpont.
function kzAllapotAlkalmaz(a){
  const cel = Math.max(0, Math.min(veg, a.t + (a.playing ? a.kor * a.speed : 0)));
  if (Math.abs(ido - cel) > KZ_TURES){ ido = cel; csuszka.value = ido; }
  megy = !!a.playing; lejatszasGomb.textContent = megy ? "⏸" : "▶";
  if (a.speed !== sebesseg){ sebesseg = a.speed; sebessegValaszto.value = String(a.speed); }
  if (a.rajz !== kzRajz){
    kzRajz = a.rajz; rajzok.length = 0; rajzok.push(...rajzDekodol(a.rajz)); rajzFrissit();
  }
  if (a.mutato && a.mutato.n !== kzMutatoN){
    kzMutatoN = a.mutato.n;
    if (a.mutato.kor < KZ_MUTATO) mutatoMutat(a.mutato.x, a.mutato.y);
  }
  if (a.nezopont && a.nezopont.n !== kzNezopontN){
    kzNezopontN = a.nezopont.n;
    if (a.nezopont.kor < KZ_MUTATO) nezopontAlkalmaz(a.nezopont);
  }
}

// ⏺ FELVÉTEL — a megbeszélés visszanézhető: vezetés közben a vezető oldala
// a saját állapotát (idő, szünet, sebesség, rajz, mutató, nézőpont)
// gyűjti, a felvétel végén a motorba menti; a "▶ Felvételek" listából
// bárki visszajátszhatja (VR-ben is) — a követés útján, mintha az edző
// épp most vezetne. Legfeljebb FV_MAX állapot (court3d.SHARED3D_REC_MAX).
const FV_MAX = __FV_MAX__;
const felvetelGomb = document.getElementById("felvetelGomb");
const felvetelValaszto = document.getElementById("felvetelValaszto");
const fejezetValaszto = document.getElementById("fejezetValaszto");
let kzFelvetel = null;   // a vezető futó felvétele: {kezd, allapotok}
let fvLejatszas = null;  // a visszajátszás: {adat, kezd, szunet, i}
// A felvétel üzenete (mentve / nem mentődött / hang nélkül): vezetés
// közben a vezető állapot-sorában FV_UZENET_MS-ig marad (a következő
// motor-válasz különben 0,3 mp alatt felülírná); vezetés nélkül a sorba.
const FV_UZENET_MS = 8000;
let fvUzenet = null;  // {szoveg, ido}
function felvetelUzen(szoveg){
  fvUzenet = {szoveg, ido: performance.now()};
  if (kozosMod === "vezet") kzVezetoInfo(); else kozosInfo.textContent = szoveg;
}
// ?felvetel=<id> (az app "▶ Felvételek" listája): a lista első betöltése
// után magától indul.
let fvUrlIndit = URL_PARAM.get("felvetel") || "";
// 🎙 A HANG: a vezető mikrofonja a felvétel alatt (MediaRecorder, ha
// engedi) — a mentés után a motorba; a visszajátszás az időhöz igazítva
// szól (FV_HANG_CSUSZAS mp-nél nagyobb elcsúszásnál odaugrik).
const FV_HANG_CSUSZAS = 0.6;
// "Ki nézte meg?": a felvétel ennyi részének TÉNYLEGES végignézése után
// (court3d.SHARED3D_REC_WATCHED_FRAC) a néző neve a motorba megy.
const FV_MEGNEZTE = __FV_MEGNEZTE__;
const fvAudio = new Audio();
fvAudio.preload = "auto";
function fvHangTipus(){
  if (typeof MediaRecorder === "undefined" || !MediaRecorder.isTypeSupported) return "";
  for (const t of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"])
    if (MediaRecorder.isTypeSupported(t)) return t;
  return "";
}
async function felvetelHangIndit(f){
  const tipus = fvHangTipus();
  if (!tipus || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
  let stream = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio: true});
    if (kzFelvetel !== f){ stream.getTracks().forEach(t => t.stop()); return; }  // közben vége lett
    const rec = new MediaRecorder(stream, {mimeType: tipus, audioBitsPerSecond: 32000});
    const h = {rec, stream, darabok: [], tipus: tipus.split(";")[0],
               eltolas: (performance.now() - f.kezd) / 1000};
    rec.ondataavailable = (e) => { if (e.data && e.data.size) h.darabok.push(e.data); };
    rec.start(1000);
    f.hang = h; kzVezetoInfo();
  } catch (e) {
    if (stream) stream.getTracks().forEach(t => t.stop());
    if (kzFelvetel === f) felvetelUzen("⏺ felvétel hang nélkül (a mikrofon nem engedélyezett)");
  }
}
// A hang-felvétel vége: {blob, eltolas} (vagy null), a mikrofon elengedve.
// (Időkorláttal: ha a "stop" esemény FV_HANG_STOP_MS alatt nem jön meg,
// a meglévő darabokkal megyünk tovább — a kép felvétele nem akadhat el a
// hangon.)
const FV_HANG_STOP_MS = 3000;
function felvetelHangLeallit(h){
  if (!h) return Promise.resolve(null);
  return new Promise(res => {
    let kesz = false;
    const vege = () => { if (kesz) return; kesz = true;
      h.stream.getTracks().forEach(t => t.stop());
      res({blob: new Blob(h.darabok, {type: h.tipus}), eltolas: h.eltolas}); };
    if (h.rec.state === "inactive"){ vege(); return; }
    h.rec.onstop = vege;
    setTimeout(vege, FV_HANG_STOP_MS);
    try { h.rec.stop(); } catch (e) { vege(); }
  });
}
// Felvétel közben a lap bezárása előtt a böngésző rákérdez (a félbehagyott
// felvétel nem mentődhet el: előbb "⏹ Felvétel vége").
addEventListener("beforeunload", (e) => {
  if (kzFelvetel && kzFelvetel.allapotok.length >= 2){ e.preventDefault(); e.returnValue = ""; }
});
function fvHangForras(url){
  fvAudio.pause();
  if (url){ fvAudio.src = url; fvAudio.load(); }
  else if (fvAudio.getAttribute("src")){ fvAudio.removeAttribute("src"); fvAudio.load(); }
}
// Odaugrás, ha a hang elcsúszott — másodpercenként legfeljebb egyszer (a
// MediaRecorder webm-je nem mindig tekerhető: ilyenkor ne akadjon minden
// képkockán).
function fvHangUgrik(f, cel){
  if (Math.abs(fvAudio.currentTime - cel) <= FV_HANG_CSUSZAS
      || performance.now() < (f.hangUgrasKov || 0)) return;
  f.hangUgrasKov = performance.now() + 1000;
  try { fvAudio.currentTime = cel; } catch (er) { /* még nem tekerhető */ }
}
// A visszajátszás hangja a képkocka-ciklusból: szünetben és a hang előtt
// néma, különben szól — ha elcsúszott, odaugrik. Ha a böngésző nem enged
// hangot kattintás nélkül (?felvetel= link), másodpercenként újrapróbál.
function felvetelHangFrissit(f, e){
  const h = f.adat.hang;
  if (!h || !fvAudio.getAttribute("src")) return;
  const cel = e - (h.eltolas || 0);
  if (f.szunet !== null || cel < 0){ if (!fvAudio.paused) fvAudio.pause(); return; }
  if (fvAudio.ended || f.hangHiba) return;
  if (!fvAudio.paused) fvHangUgrik(f, cel);
  if (fvAudio.paused && !f.hangKer && performance.now() >= (f.hangKov || 0)){
    f.hangKer = true;
    fvHangUgrik(f, cel);
    // NotAllowedError: a böngésző kattintást vár (újrapróbál); minden más
    // (a hang nem tölthető): nem próbál újra, a felirat megmondja.
    fvAudio.play().then(() => { f.hangKer = false; f.hangTiltva = false; },
      (err) => { f.hangKer = false;
        if (err && err.name === "NotAllowedError"){ f.hangTiltva = true; f.hangKov = performance.now() + 1000; }
        else { f.hangTiltva = false; f.hangHiba = true; } });
  }
}
const fvCim = () => "/matches/" + encodeURIComponent(ADAT.match_id || "") + "/felvetelek";
const fvOra = (s) => { const t = Math.max(0, Math.floor(s));
  return Math.floor(t / 60) + ":" + String(t % 60).padStart(2, "0"); };
function felvetelGombFelirat(){
  felvetelGomb.textContent = kzFelvetel ? "⏹ Felvétel vége"
    : fvLejatszas ? (fvLejatszas.szunet !== null ? "▶ Felvétel tovább" : "⏸ Felvétel szünet")
    : "⏺ Felvétel";
  felvetelGomb.disabled = !(kozosMod === "vezet" || fvLejatszas);
}
// (a vezető küldésével együtt, KZ_KULD-onként)
function felvetelRogzit(){
  if (!kzFelvetel) return;
  kzFelvetel.allapotok.push([Math.round((performance.now() - kzFelvetel.kezd) / 10) / 100,
    {t: Math.round(ido * 100) / 100, playing: megy, speed: sebesseg, rajz: rajzKodol(rajzok),
     mutato: kzMutato, nezopont: kzNezopont,
     // a kvíz köre és a csapat válaszai (a visszajátszás a felfedés után
     // névvel mutatja őket)
     ...(kzKviz ? {kviz: kzKviz, valaszok: kzVezetoCsapat.filter(e => e.valasz)
        .map(e => ({nev: e.nev || ("#" + e.sz), x: e.valasz[0], y: e.valasz[1]}))} : {})}]);
  if (kzFelvetel.allapotok.length >= FV_MAX) felvetelMent();
}
async function felvetelMent(){
  const f = kzFelvetel;
  kzFelvetel = null; felvetelGombFelirat();
  const hang = f ? await felvetelHangLeallit(f.hang) : null;
  if (!f || f.allapotok.length < 2 || !ADAT.match_id) return;
  const nev = "Megbeszélés " + new Date().toLocaleString("hu-HU", {dateStyle: "short", timeStyle: "short"});
  try {
    const v = await fetch(fvCim(), {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({nev, allapotok: f.allapotok, jelen: [...(f.jelen || [])]})});
    if (!v.ok) throw new Error("a motor " + v.status + "-at válaszolt");
    const d = await v.json();
    let hangInfo = "";
    if (hang && hang.blob.size){
      try {
        const hv = await fetch(fvCim() + "/" + encodeURIComponent(d.id) + "/hang?eltolas="
          + hang.eltolas.toFixed(2), {method: "PUT", headers: {"Content-Type": hang.blob.type},
          body: hang.blob});
        hangInfo = hv.ok ? " 🎙 hanggal" : " (a hang nem mentődött: a motor " + hv.status + "-at válaszolt)";
      } catch (e) { hangInfo = " (a hang nem mentődött: " + e.message + ")"; }
    }
    felvetelUzen("⏺ felvétel mentve" + hangInfo + ": " + d.nev + " (" + fvOra(d.hossz_s)
      + ") — a ▶ Felvételek listából visszanézhető");
    felvetelListaBetolt();
  } catch (e) { felvetelUzen("⏺ a felvétel nem mentődött: " + e.message); }
}
async function felvetelListaBetolt(){
  if (FV_CSOMAG){
    felvetelValaszto.textContent = "";
    const fej = document.createElement("option"); fej.value = "";
    fej.textContent = "▶ Felvétel (újra)";
    const o = document.createElement("option"); o.value = FV_CSOMAG.adat.id;
    o.textContent = FV_CSOMAG.adat.nev + " · " + fvOra(FV_CSOMAG.adat.hossz_s);
    felvetelValaszto.append(fej, o); felvetelValaszto.style.display = "";
    felvetelValaszto.value = FV_CSOMAG.adat.id;
    // A modul végigfutása után: a később deklarált állapotok (pl. a
    // vetítés) addig nem érhetők el — a motoros út a fetch miatt eleve vár.
    setTimeout(() => felvetelIndit(FV_CSOMAG.adat.id), 0);
    return;
  }
  if (!ADAT.match_id) return;
  try {
    const v = await fetch(fvCim());
    if (!v.ok) return;
    const lista = (await v.json()).felvetelek || [];
    felvetelValaszto.textContent = "";
    const fej = document.createElement("option"); fej.value = "";
    fej.textContent = "▶ Felvételek (" + lista.length + ")";
    felvetelValaszto.appendChild(fej);
    for (const f of lista){
      const o = document.createElement("option"); o.value = f.id;
      o.textContent = f.nev + " · " + fvOra(f.hossz_s);
      felvetelValaszto.appendChild(o);
    }
    felvetelValaszto.style.display = lista.length ? "" : "none";
    const kert = fvUrlIndit; fvUrlIndit = "";
    if (kert && lista.some(f => f.id === kert)){
      felvetelValaszto.value = kert; felvetelIndit(kert);
    }
  } catch (e) { /* a motor nélkül (mentett oldal) nincs felvétel */ }
}
felvetelGomb.onclick = () => {
  if (kozosMod === "vezet"){
    if (kzFelvetel) felvetelMent();
    else {
      // (jelen: a felvétel alatt névvel jelenlévő követők — élőben követték)
      kzFelvetel = {kezd: performance.now(), allapotok: [], hang: null, jelen: new Set()}; kzUtolso = 0;
      felvetelHangIndit(kzFelvetel);
    }
    felvetelGombFelirat(); kzVezetoInfo();
    return;
  }
  if (fvLejatszas){
    if (fvLejatszas.szunet === null) fvLejatszas.szunet = performance.now();
    else { fvLejatszas.kezd += performance.now() - fvLejatszas.szunet; fvLejatszas.szunet = null; }
    felvetelGombFelirat();
  }
};
async function felvetelIndit(id){
  felvetelAll();
  if (!id) return;
  if (kozosMod){
    kozosInfo.textContent = "a visszajátszáshoz előbb állítsd le a közös nézést";
    felvetelValaszto.value = ""; return;
  }
  try {
    let adat;
    if (FV_CSOMAG) adat = FV_CSOMAG.adat;
    else {
      const v = await fetch(fvCim() + "/" + encodeURIComponent(id));
      if (!v.ok) throw new Error("a motor " + v.status + "-at válaszolt");
      adat = await v.json();
    }
    fvHangForras(FV_CSOMAG ? (FV_CSOMAG.hang || "")
      : adat.hang ? fvCim() + "/" + encodeURIComponent(id) + "/hang" : "");
    kzRajz = null; kzMutatoN = null; kzNezopontN = null;
    if (vetites) vetitesAllit(false);
    fvLejatszas = {adat, kezd: performance.now(), szunet: null, i: 0};
    fejezetListaToltes(adat);
    // Név nélkül a "Ki vagy?" előjön: a megnézés a névvel számít (a
    // csomagban nincs motor — nincs kinek jelezni).
    if (!KZ_NEV && ADAT.match_id) nevValasztoMutat(true);
    felvetelGombFelirat();
  } catch (e) { kozosInfo.textContent = "▶ a felvétel nem tölthető: " + e.message; }
}
function felvetelAll(){
  if (!fvLejatszas) return;
  fvLejatszas = null; megy = false; lejatszasGomb.textContent = "▶";
  fvHangForras(""); fejezetValaszto.style.display = "none";
  fvKvizKulcs = null; valaszokAllit([]);
  if (kozosMod !== "kovet") nevValasztoMutat(false);
  kozosInfo.textContent = ""; felvetelGombFelirat();
}
felvetelValaszto.onchange = () => felvetelIndit(felvetelValaszto.value);
// A felvétel kvíze: a felfedett kör válaszai névvel (döntés-kvíznél ✓/✗)
// — mint a követőnél a felfedés után. Csak változáskor rajzol újra.
let fvKvizKulcs = null;
function felvetelKvizAllit(a){
  const k = a && a.kviz && a.kviz.mutat ? a.kviz : null;
  const kulcs = k ? k.n + "|" + JSON.stringify(a.valaszok || []) : null;
  if (kulcs === fvKvizKulcs) return;
  fvKvizKulcs = kulcs;
  if (!k){ valaszokAllit([]); return; }
  const d = kvizDontes(k);
  valaszokAllit((a.valaszok || []).map((v, i) => ({kulcs: "f" + i,
    cimke: kvizCimke(v.nev, v.x, v.y, d), sajat: false, x: v.x, y: v.y})));
}
// FEJEZETEK: ahol az edző egy másik jelenetre ugrott (a motor számolja —
// court3d.shared3d_felvetel_fejezetek). A felirat a közeli jelenet-sor
// (FV_FEJEZET_KOZEL mp-en belül), különben a meccs pillanata; visszafelé
// lépve a fejezet elejére ugrik, ha már FV_FEJEZET_VISSZA mp-nél tovább
// tartunk benne (mint a lejátszók "előző" gombja).
const FV_FEJEZET_KOZEL = 8, FV_FEJEZET_VISSZA = 3;
function fejezetFelirat(fz, i){
  const [e, t] = fz;
  let jo = null;
  for (const r of jelenetSorokSzurt())
    if (Math.abs(r.s - t) <= FV_FEJEZET_KOZEL && (!jo || Math.abs(r.s - t) < Math.abs(jo.s - t))) jo = r;
  return (i + 1) + ". " + fvOra(e) + " — " + (jo ? jo.szoveg : "a meccs " + fvOra(t) + " pillanata");
}
function fejezetListaToltes(adat){
  const fz = adat.fejezetek || [];
  fejezetValaszto.textContent = "";
  fz.forEach((x, i) => { const o = document.createElement("option"); o.value = String(i);
    o.textContent = fejezetFelirat(x, i); fejezetValaszto.appendChild(o); });
  fejezetValaszto.style.display = fz.length > 1 ? "" : "none";
}
// Ugrás a felvételben (szünetben is): a cél előtti mutató és nézőpont nem
// villan fel újra — csak az utána jövők.
function fvUgras(eltelt){
  const f = fvLejatszas;
  if (!f) return;
  const most = performance.now(), all = f.adat.allapotok;
  f.kezd = most - eltelt * 1000;
  if (f.szunet !== null) f.szunet = most;
  let i = 0;
  while (i + 1 < all.length && all[i + 1][0] <= eltelt) i++;
  f.i = i;
  const a = all[i][1];
  if (a.mutato) kzMutatoN = a.mutato.n;
  if (a.nezopont) kzNezopontN = a.nezopont.n;
  // Azonnal oda (szünetben a képkocka-ciklus nem alkalmaz állapotot).
  kzAllapotAlkalmaz({...a, kor: Math.max(0, eltelt - all[i][0]), mutato: null, nezopont: null});
  if (f.szunet !== null){ megy = false; lejatszasGomb.textContent = "▶"; }
}
const fvEltelt = (f) => ((f.szunet !== null ? f.szunet : performance.now()) - f.kezd) / 1000;
function fejezetIndex(fz, e){
  let fi = 0;
  while (fi + 1 < fz.length && fz[fi + 1][0] <= e) fi++;
  return fi;
}
function felvetelFejezet(irany){
  const f = fvLejatszas;
  const fz = f ? (f.adat.fejezetek || []) : [];
  if (!fz.length) return null;
  const e = fvEltelt(f), fi = fejezetIndex(fz, e);
  const cel = irany < 0 && e - fz[fi][0] > FV_FEJEZET_VISSZA ? fi
    : Math.max(0, Math.min(fz.length - 1, fi + irany));
  fvUgras(fz[cel][0]);
  return cel;
}
window.felvetelFejezet = felvetelFejezet;
fejezetValaszto.onchange = () => {
  const f = fvLejatszas, x = f ? (f.adat.fejezetek || [])[+fejezetValaszto.value] : null;
  if (x) fvUgras(x[0]);
};
// A visszajátszás a képkocka-ciklusból: az eltelt időig utolsó állapot a
// követés útján (kzAllapotAlkalmaz); a mutató és a nézőpont az új
// azonosítónál (n) azonnal.
function felvetelFrissit(){
  const f = fvLejatszas;
  if (!f) return;
  const all = f.adat.allapotok;
  const e = ((f.szunet !== null ? f.szunet : performance.now()) - f.kezd) / 1000;
  while (f.i + 1 < all.length && all[f.i + 1][0] <= e) f.i++;
  const fz = f.adat.fejezetek || [], fi = fejezetIndex(fz, e);
  if (fz.length > 1 && fejezetValaszto.value !== String(fi)) fejezetValaszto.value = String(fi);
  const [e0, a] = all[f.i];
  if (f.szunet !== null){ megy = false; lejatszasGomb.textContent = "▶"; }
  else kzAllapotAlkalmaz({...a, kor: Math.max(0, e - e0),
                          mutato: a.mutato ? {...a.mutato, kor: 0} : null,
                          nezopont: a.nezopont ? {...a.nezopont, kor: 0} : null});
  felvetelHangFrissit(f, e);
  felvetelKvizAllit(a);
  const hossz = f.adat.hossz_s || all[all.length - 1][0];
  // A ténylegesen lejátszott idő (a szünet és az ugrás nem számít).
  const most = performance.now();
  if (f.szunet === null && f.utolso !== undefined)
    f.nezett = (f.nezett || 0) + Math.min(1, (most - f.utolso) / 1000);
  f.utolso = most;
  if (!f.jelentve && KZ_NEV && ADAT.match_id && f.adat.id && (f.nezett || 0) >= hossz * FV_MEGNEZTE){
    f.jelentve = true;
    fetch(fvCim() + "/" + encodeURIComponent(f.adat.id) + "/megnezte", {method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify({nev: KZ_NEV})})
      .then(v => { f.megnezve = v.ok; }).catch(() => {});
  }
  if (e > hossz + 1){
    felvetelAll(); felvetelValaszto.value = "";
    kozosInfo.textContent = "▶ a felvétel véget ért" + (f.megnezve ? " · ✓ megnézted (az edző látja)" : "");
    return;
  }
  const info = "▶ " + f.adat.nev + " · " + fvOra(Math.min(e, hossz)) + " / " + fvOra(hossz)
    + (f.szunet !== null ? " · szünet" : "")
    + (f.adat.hang ? (f.hangHiba ? " · 🎙 a hang nem tölthető"
                      : f.hangTiltva ? " · 🔊 kattints az oldalra a hanghoz" : " · 🎙") : "")
    + (fz.length > 1 ? " · " + (fi + 1) + "/" + fz.length + ". fejezet (N / P)" : "")
    + (f.megnezve ? " · ✓ megnézted" : "")
    + (a.kviz ? " · ❓ kvíz" + (a.kviz.mutat ? " — a csapat válaszai" : "") : "");
  if (kozosInfo.textContent !== info) kozosInfo.textContent = info;
}
window.felvetelProba = () => ({felvesz: !!kzFelvetel, db: kzFelvetel ? kzFelvetel.allapotok.length : 0,
  lejatszas: fvLejatszas ? {i: fvLejatszas.i, n: fvLejatszas.adat.allapotok.length,
                            szunet: fvLejatszas.szunet !== null} : null,
  gomb: felvetelGomb.textContent, tiltva: felvetelGomb.disabled,
  lista: [...felvetelValaszto.options].map(o => o.value), info: kozosInfo.textContent,
  ido, megy, rajz: rajzKodol(rajzok), hangFelvesz: !!(kzFelvetel && kzFelvetel.hang),
  hang: {src: !!fvAudio.getAttribute("src"), szol: !fvAudio.paused,
         ido: fvAudio.currentTime, tiltva: !!(fvLejatszas && fvLejatszas.hangTiltva),
         hiba: !!(fvLejatszas && fvLejatszas.hangHiba)},
  nezett: fvLejatszas ? (fvLejatszas.nezett || 0) : 0, megnezve: !!(fvLejatszas && fvLejatszas.megnezve),
  nevValaszto: kzNevValaszto.style.display !== "none",
  fejezet: fejezetValaszto.value, fejezetLatszik: fejezetValaszto.style.display !== "none",
  fejezetek: [...fejezetValaszto.options].map(o => o.textContent)});
felvetelListaBetolt();

vezetGomb.onclick = () => kozosAllit("vezet");
kovetGomb.onclick = () => kozosAllit("kovet");
window.kozosProba = () => ({mod: kozosMod, ido, megy, sebesseg, rajz: rajzKodol(rajzok), info: kozosInfo.textContent});

// ---- Jegyzetek: az edző megjegyzései a pillanatokhoz ------------------
// A "📝 Jegyzet" (J) a mostani pillanathoz ír megjegyzést a motor /notes
// végpontjára — ugyanaz a jegyzet-tár, amit a meccs-elemző használ: a
// jelenet-lista sorai közt (fehér pötty, ✕ törli), a vetítésben, a
// felirat-oszlopban (VR-ben a táblán), a nyomtatott jelentésben és a
// Klipek "Jegyzetelt pillanatok" csomagjában is megjelenik. A tár
// kockában tárol (a jegyzet "frame" mezője), az oldal másodpercben jár.
const FPS = ADAT.fps || 25;
let jegyzetek = [];  // [{id, s, text}] — időrendben
const jegyzetInfo = document.getElementById("jegyzetInfo");
const jegyzetFeliratElem = document.getElementById("jegyzetFelirat");
const jegyzetIdo = (s) => { const t = Math.max(0, Math.floor(s));
  return Math.floor(t / 60) + ":" + String(t % 60).padStart(2, "0"); };
const jegyzetCim = () => "/matches/" + encodeURIComponent(ADAT.match_id || "") + "/notes";
async function jegyzetBetolt(){
  if (!ADAT.match_id) return;
  try {
    const v = await fetch(jegyzetCim());
    // A sikertelen betöltéssel a jegyzetekre váró vetítés elmarad (egy
    // későbbi jegyzet-írás különben elindítaná).
    if (!v.ok){ vetitesVar = false; return; }
    const d = await v.json();
    jegyzetek = (d.notes || [])
      .map(n => ({id: n.id, s: Math.round((Number(n.frame) || 0) / FPS * 100) / 100, text: String(n.text || ""),
                  rajz: rajzDekodol(n.rajz || "")}))
      .sort((a, b) => a.s - b.s);
    jegyzetInfo.textContent = jegyzetek.length ? jegyzetek.length + " jegyzet" : "";
    if (jelenetLista.style.display === "block") jelenetListaEpit();
    if (vetitesVar){ vetitesVar = false; vetitesAllit(true); }
  } catch (e) { vetitesVar = false; /* a motor nélkül (mentett oldal) nincs jegyzet */ }
}
async function jegyzetIr(){
  if (!ADAT.match_id){ jegyzetInfo.textContent = "a jegyzethez a motor kell"; return; }
  const szoveg = prompt("Jegyzet ehhez a pillanathoz (" + jegyzetIdo(ido) + "):");
  if (!szoveg || !szoveg.trim()) return;
  try {
    // A padlón lévő nyilak a jegyzettel mentődnek (a jegyzet pillanatában
    // maguktól visszarajzolódnak), és a mentés után lekerülnek a padlóról.
    const rajzzal = rajzok.length > 0;
    const v = await fetch(jegyzetCim(), {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({frame: Math.round(ido * FPS), text: szoveg.trim(),
                            rajz: rajzzal ? rajzKodol(rajzok) : ""})});
    if (!v.ok) throw new Error("a motor " + v.status + "-at válaszolt");
    if (rajzzal){ rajzok.length = 0; rajzFrissit(); }
    await jegyzetBetolt();
    jegyzetInfo.textContent = "mentve" + (rajzzal ? " a rajzzal" : "") + " · " + jegyzetek.length + " jegyzet";
  } catch (e) { jegyzetInfo.textContent = "hiba: " + e.message; }
}
async function jegyzetTorol(id){
  try {
    const v = await fetch(jegyzetCim() + "/" + encodeURIComponent(id), {method: "DELETE"});
    if (!v.ok) throw new Error("a motor " + v.status + "-at válaszolt");
    await jegyzetBetolt();
  } catch (e) { jegyzetInfo.textContent = "hiba: " + e.message; }
}
// A jegyzettel mentett rajz: a jegyzet pillanata körül a padlón (külön
// csoport — a padló saját, szerkeszthető rajzát nem érinti).
const jegyzetRajzCsoport = new THREE.Group();
szinpad.add(jegyzetRajzCsoport);
let jegyzetRajzAkt = null;
function jegyzetFrissit(t){
  // A jegyzet a pillanata körül a felirat-oszlopban (VR-ben a táblán), a
  // rajza a padlón — csak jegyzet-váltáskor rajzolunk újra.
  const j = jegyzetek.find(x => t >= x.s - 0.3 && t <= x.s + 3) || null;
  if (j !== jegyzetRajzAkt){
    jegyzetRajzAkt = j;
    csoportUrit(jegyzetRajzCsoport);
    if (j) for (const r of j.rajz) jegyzetRajzCsoport.add(nyilMesh(...r));
  }
  if (!j){ jegyzetFeliratElem.style.display = "none"; return; }
  jegyzetFeliratElem.textContent = "📝 " + j.text + (j.rajz.length ? " ✎" : "");
  jegyzetFeliratElem.style.display = "block";
}
document.getElementById("jegyzetGomb").onclick = jegyzetIr;
window.jegyzetProba = () => jegyzetek.map(j => ({s: j.s, text: j.text, nyilak: j.rajz.length,
                                                  latszik: jegyzetRajzAkt === j ? jegyzetRajzCsoport.children.length : 0}));

// ---- Vetítés: a jelenet-lista sorai egymás után ------------------------
// A "▶ Vetítés" (V; VR-ben a hüvelykujj-kar lenyomása) a lista sorain (a
// két szűrő szerint) végigjátszik: minden jelenet 1,5 mp-cel előtte indul,
// és a pillanata után JL_VETITES_S mp-ig fut (court3d.SCENE_REEL_TAIL_S),
// aztán a lista KÖVETKEZŐ sora jön — az átfedő jelenetek sem maradnak ki
// (az N az időből lép, a vetítés a sorrendből). Az utolsó után megáll. A
// léptetés csak akkor jön, ha a lejátszás a futó jelenet végén halad át:
// kézi tekerés után nem ugrik el; egy sorra kattintva onnan folytatja.
const JL_VETITES_S = __JL_VETITES_S__;
let vetites = false, vetitesSor = null;
const vetitesJelzo = document.getElementById("vetitesJelzo");
function azonosSor(a, b){
  // Ugyanaz a sor (az újraépített listában is): a fajta, az idő, a
  // felirat és a jegyzet-azonosító — két jegyzet ugyanarra a kockára két sor.
  return a.tipus === b.tipus && a.s === b.s && a.szoveg === b.szoveg && (a.id || null) === (b.id || null);
}
function vetitesIndex(sorok, r){
  // A sor helye a (szűrt) listában; -1, ha a szűrő kivette.
  return r ? sorok.findIndex(x => azonosSor(x, r)) : -1;
}
function vetitesVeg(r){
  // A jelenet vége a vetítésben: a pillanata után JL_VETITES_S — a kapott
  // lerohanás sora az INDULÁS ideje, ott a befejezés (lövés) után.
  if (r.tipus === "k"){
    const k = KONTRAK.find(x => Math.abs(x[0] - r.s) < 0.01);
    if (k && k[14] !== null && k[14] !== undefined) return Math.max(r.s, k[14]) + JL_VETITES_S;
  }
  return r.s + JL_VETITES_S;
}
function vetitesJelzoFrissit(){
  const gomb = document.getElementById("vetitesGomb");
  if (gomb){ gomb.textContent = vetites ? "■ Vetítés" : "▶ Vetítés"; gomb.classList.toggle("be", vetites); }
  if (!vetites || !vetitesSor){ vetitesJelzo.style.display = "none"; return; }
  const sorok = jelenetSorokSzurt();
  const i = vetitesIndex(sorok, vetitesSor);
  vetitesJelzo.textContent = "Vetítés · " + (i >= 0 ? i + 1 : "–") + "/" + sorok.length + " · " + vetitesSor.ido;
  vetitesJelzo.style.display = "block";
}
function vetitesKov(){
  // A futó sor UTÁNI sor a lista sorrendjében (ha a szűrő közben kivette,
  // az első későbbi); null: a lista vége.
  const sorok = jelenetSorokSzurt();
  const i = vetitesIndex(sorok, vetitesSor);
  // A szó szerint azonos (kettőzött) sort átlépjük — különben a vetítés
  // a kettő közt körbe járna.
  if (i >= 0) return sorok.slice(i + 1).find(x => !azonosSor(x, vetitesSor)) || null;
  return sorok.find(x => x.s > vetitesSor.s) || null;
}
function vetitesAllit(be){
  vetites = !!be;
  const sorok = vetites ? jelenetSorokSzurt() : [];
  if (vetites && !sorok.length) vetites = false;
  if (vetites){
    // Az épp futó jelenettől (a legkésőbb indult), különben az első még
    // előttünk álló sortól; a lista végén az elejéről.
    let r = null;
    for (const x of sorok) if (ido >= x.s - 1.6 && ido < vetitesVeg(x)) r = x;
    r = r || sorok.find(x => x.s >= ido) || sorok[0];
    if (jelenetLista.style.display !== "block") jelenetListaNyit(true);
    vrJelenetUtolso = r.s;
    jelenetUgras(r);
  }
  vetitesJelzoFrissit();
}
function vetitesFrissit(t0, t1){
  // A lejátszás most haladt át a futó jelenet végén (vagy a meccs végére
  // ért) → a következő sor; a lista végén megáll.
  if (!vetites || !vetitesSor) return;
  const hatar = vetitesVeg(vetitesSor);
  if (!(t0 < hatar && (t1 >= hatar || t1 >= veg))) return;
  const kov = vetitesKov();
  if (kov){ vrJelenetUtolso = kov.s; jelenetUgras(kov); return; }
  vetites = false; megy = false; lejatszasGomb.textContent = "▶";
  vetitesJelzoFrissit();
}
window.vetitesProba = () => ({be: vetites, sor: vetitesSor && {s: vetitesSor.s, tipus: vetitesSor.tipus}});
function jelenetUgras(r){
  if (r.tipus === "d") dontesUtolso = r.s;
  else if (r.tipus === "sz") szabadUtolso = r.s;
  else if (r.tipus === "k") kontraUtolso = r.s;
  else if (r.tipus === "kg") kapottUtolso = r.s;
  else if (r.tipus === "e") eladasUtolso = r.s;
  ido = Math.max(0, r.s - 1.5); megy = true; lejatszasGomb.textContent = "⏸";
  csuszka.value = ido;
  vetitesSor = r; vetitesJelzoFrissit();  // a vetítés innen folytatja
}
// "Videózandó" szűrő: a lista (és az N/P, a VR-kontroller lépése) csak a
// kulcs-jeleneteken — a jelentés "Videózandó jelenetek" és a kezdőlap
// kártyájának válogatásán (court3d.key_scene_rows). A sorok a típus és az
// idő szerint egyeznek (ugyanazok a kerekített számok).
const KULCS = new Set((ADAT.key_scenes || []).map(k => k[1] + "@" + k[0]));
let csakKulcs = false;
// "Jegyzeteim" szűrő (a Videózandó párja; a kettő közül egy él), és a
// jegyzetekre váró vetítés (a link vetit=1-e: a jegyzetek a motorról
// később jönnek, mint a lista első építése).
let csakJegyzet = false, vetitesVar = false;
function kulcsSzur(sorok){
  return csakKulcs ? sorok.filter(r => KULCS.has(r.tipus + "@" + r.s)) : sorok;
}
function jelenetListaEpit(){
  jelenetSorokAkt = jelenetSorokSzurt();
  jelenetAktiv = -2;
  jelenetLista.textContent = "";
  jelenetSorokElem.textContent = "";
  // Fejléc: a jelenetek száma és a Klipek gomb (a jelenetek videóként).
  const fej = document.createElement("div"); fej.className = "jfej";
  const n = document.createElement("span"); n.className = "n";
  n.textContent = "Jelenetek · " + jelenetSorokAkt.length;
  const g = document.createElement("button"); g.id = "klipGomb"; g.textContent = "Klipek";
  g.title = "A lapozók jelenetei videóként (döntés-hibák, szabad lövők, drága eladások, kapott lerohanások; a Videózandó szűrővel a videózandó jelenetek egy csomagban, sorszámozva) — a motor vágja, kész zipre letöltő link";
  g.onclick = klipKer;
  const info = document.createElement("span"); info.id = "klipInfo";
  const link = document.createElement("a"); link.id = "klipLetolt"; link.textContent = "Letöltés";
  link.href = "/matches/" + encodeURIComponent(ADAT.match_id || "") + "/clips/download";
  link.style.display = "none";
  const kl = document.createElement("label"); kl.className = "kulcs";
  kl.title = "Csak a videózandó jelenetek (a jelentés és a kezdőlap válogatása: gólba került eladások, kapott lerohanás-gólok, gólt érő szabad lövők, a legnagyobb döntés-hibák)";
  const kc = document.createElement("input"); kc.type = "checkbox"; kc.id = "jelenetKulcs";
  kc.checked = csakKulcs; kc.disabled = !KULCS.size;
  kc.onchange = () => { csakKulcs = kc.checked; if (csakKulcs) csakJegyzet = false; vrJelenetUtolso = null; jelenetListaEpit(); };
  kl.append(kc, document.createTextNode(" Videózandó (" + KULCS.size + ")"));
  const jl = document.createElement("label"); jl.className = "kulcs";
  jl.title = "Csak a jegyzeteid — a vetítés a megjelölt pillanatokat játssza (a rajzzal): a csapat-megbeszélés válogatása";
  const jc = document.createElement("input"); jc.type = "checkbox"; jc.id = "jelenetJegyzet";
  jc.checked = csakJegyzet; jc.disabled = !jegyzetek.length && !csakJegyzet;
  jc.onchange = () => { csakJegyzet = jc.checked; if (csakJegyzet) csakKulcs = false; vrJelenetUtolso = null; jelenetListaEpit(); };
  jl.append(jc, document.createTextNode(" Jegyzeteim (" + jegyzetek.length + ")"));
  const vb = document.createElement("button"); vb.id = "vetitesGomb";
  vb.title = "Vetítés (V): a lista jelenetei egymás után — mindegyik 1,5 mp-cel előtte indul, és a pillanata után " + JL_VETITES_S + " mp-ig fut";
  vb.onclick = () => vetitesAllit(!vetites);
  vb.disabled = !jelenetSorokAkt.length;
  fej.append(n, kl, jl, vb, g, info, link);
  jelenetLista.append(fej, jelenetSorokElem);
  klipFrissit();
  vetitesJelzoFrissit();
  if (!jelenetSorokAkt.length){ jelenetSorokElem.textContent = "Nincs ilyen jelenet."; return; }
  jelenetSorokAkt.forEach((r) => {
    const sor = document.createElement("div");
    sor.className = "jsor";
    const i = document.createElement("span"); i.className = "jido"; i.textContent = r.ido;
    const p = document.createElement("span"); p.className = "jpont"; p.style.background = JL_SZIN[r.tipus];
    const t = document.createElement("span"); t.textContent = r.szoveg;
    sor.append(i, p, t);
    if (r.tipus === "n"){
      const x = document.createElement("span"); x.className = "jtorol"; x.textContent = "✕";
      x.title = "A jegyzet törlése";
      x.onclick = (e) => { e.stopPropagation(); jegyzetTorol(r.id); };
      sor.append(x);
    }
    sor.onclick = () => jelenetUgras(r);
    jelenetSorokElem.appendChild(sor);
  });
}

// ---- Klipek a jelenet-listából ------------------------------------------
// A három lapozó jelenetei videóként: a gomb a motor klip-exportját kéri
// (döntés-hibák, szabad lövők, drága eladások, kapott lerohanások — a
// nézett meccsről), az
// állapotot a /jobs végpontról követi, és kész zipre letöltő linket ad.
// Az oldalt a motor szolgálja ki, ezért a kérések relatív címre mennek.
const KLIP_TIPUSOK = ["bad_decision", "free_shot", "costly_turnover", "conceded_fast_break"];
let klipJob = null, klipIdozito = null;
function klipFrissit(){
  const info = document.getElementById("klipInfo");
  if (!info) return;
  info.textContent = klipAllapotSzoveg(klipJob);
  const gomb = document.getElementById("klipGomb");
  if (gomb) gomb.disabled = !!(klipJob && klipJob.status === "running");
  const link = document.getElementById("klipLetolt");
  if (link) link.style.display = (klipJob && klipJob.status === "done") ? "" : "none";
}
async function klipKer(){
  if (!ADAT.match_id || (klipJob && klipJob.status === "running")) return;
  klipJob = {status: "running", message: "kérés…"}; klipFrissit();
  try {
    const v = await fetch("/matches/" + encodeURIComponent(ADAT.match_id) + "/clips/export",
      {method: "POST", headers: {"Content-Type": "application/json"},
       // A Videózandó szűrővel a lista sorai egy csomagban, sorszámozva;
       // az edző jegyzetei (a lista sorai közt) a jegyzet-csomagban.
       body: JSON.stringify({types: csakJegyzet ? ["note"]
                                    : (csakKulcs ? ["key_scene"] : KLIP_TIPUSOK)
                                      .concat(jegyzetek.length ? ["note"] : [])})});
    if (!v.ok) throw new Error("a motor " + v.status + "-at válaszolt");
    const {job_id} = await v.json();
    const kovet = async () => {
      try {
        const j = await (await fetch("/jobs/" + job_id)).json();
        klipJob = j; klipFrissit();
        if (j.status === "running") klipIdozito = setTimeout(kovet, 1500);
      } catch (e) { klipJob = {status: "error", message: "hiba: " + e.message}; klipFrissit(); }
    };
    kovet();
  } catch (e) {
    klipJob = {status: "error", message: "hiba: a motor nem érhető el (" + e.message + ")"}; klipFrissit();
  }
}
function jelenetListaNyit(be){
  jelenetLista.style.display = be ? "block" : "none";
  sugoAllit();  // a súgó helyén nyílik; bezárva a súgó állapota tér vissza
  jelenetGomb.classList.toggle("be", be);
  if (be) jelenetListaEpit();
}
jelenetGomb.onclick = () => jelenetListaNyit(jelenetLista.style.display !== "block");
function jelenetListaJelol(t){
  if (jelenetLista.style.display !== "block" || !jelenetSorokAkt.length) return;
  // Átfedő ablakoknál a LEGKÉSŐBB indult jelenet az aktív (a frissen
  // kiválasztott, nem a még le nem járt előző).
  let i = -1;
  jelenetSorokAkt.forEach((r, k) => { if (t >= r.s - 0.3 && t <= r.s + 2.5) i = k; });
  // Vetítés közben a futó sor végig (az előfutás alatt is) kiemelve.
  if (vetites){ const v = vetitesIndex(jelenetSorokAkt, vetitesSor); if (v >= 0) i = v; }
  if (i === jelenetAktiv) return;
  const sorok = jelenetSorokElem.children;
  if (jelenetAktiv >= 0 && sorok[jelenetAktiv]) sorok[jelenetAktiv].classList.remove("aktiv");
  jelenetAktiv = i;
  if (i >= 0 && sorok[i]){ sorok[i].classList.add("aktiv"); sorok[i].scrollIntoView({block: "nearest"}); }
}

jelenetInfok();

// ---- Lövéstérkép: a meccs lövései a padlón --------------------------
// Egy lövés = egy kör a lövés helyén: a csapat színével, a sugara az
// xG-vel nő (nagy kör = nagy helyzet), a gólt arany gyűrű jelzi, a
// védett/kihagyott halványabb. Kattintás egy körre: odaugrik a
// jelenethez (4 mp-cel előtte, lejátszva) és kiírja a lövés számait.
const LOVESEK = ADAT.shots || [];
const lovesValaszto = document.getElementById("lovesek");
const lovesInfo = document.getElementById("lovesInfo");
const lovesCsoport = new THREE.Group();
szinpad.add(lovesCsoport);
const lovesJelek = [];
const aranyGyuruAnyag = new THREE.MeshBasicMaterial(
  {color:0xd9b544, side:THREE.DoubleSide, depthWrite:false});
for (const l of LOVESEK){
  const [mp, hazai, x, y, xg, kimenet] = l;
  const r = 0.22 + 0.5 * Math.min(1, Math.max(0, xg));
  const korong = new THREE.Mesh(new THREE.CircleGeometry(r, 20),
    new THREE.MeshBasicMaterial({color: hazai ? 0x4c9aff : 0xff6b6b,
      transparent:true, opacity: kimenet === "g" ? 0.9 : 0.45,
      side:THREE.DoubleSide, depthWrite:false}));
  korong.rotation.x = -Math.PI/2; korong.position.set(x, 0.018, W - y);
  korong.userData.loves = l;
  if (kimenet === "g"){
    const gyuru = new THREE.Mesh(new THREE.RingGeometry(r + 0.04, r + 0.12, 24), aranyGyuruAnyag);
    gyuru.rotation.x = -Math.PI/2; gyuru.position.set(x, 0.02, W - y);
    korong.userData.gyuru = gyuru; lovesCsoport.add(gyuru);
  }
  lovesCsoport.add(korong); lovesJelek.push(korong);
}
const KIMENET = {g: "gól", v: "védés", m: "mellé/kapufa"};
function lovesLatszik(l, t){
  const v = lovesValaszto.value;
  if (!v) return false;
  if (v === "eddig") return l[0] <= t;
  if (v === "hazai") return !!l[1];
  if (v === "vendeg") return !l[1];
  return true;
}
let lovesSzoveg = "";
function lovesFrissit(t){
  let db = 0, gol = 0;
  for (const j of lovesJelek){
    const lat = lovesLatszik(j.userData.loves, t);
    j.visible = lat; if (j.userData.gyuru) j.userData.gyuru.visible = lat;
    if (lat){ db++; if (j.userData.loves[5] === "g") gol++; }
  }
  const s = lovesValaszto.value
    ? (LOVESEK.length ? db + " lövés, " + gol + " gól — kék: " + ADAT.home + ", piros: " + ADAT.away
       : "Ehhez a meccshez nincs felismert lövés.")
    : "";
  if (s !== lovesSzoveg){ lovesSzoveg = s; lovesInfo.textContent = s; }
}
// Katt egy lövés-körre (a sugár már beállítva): ugrás + mérés-doboz a
// lövés helyén, a lövés számaival. Igaz, ha talált.
function lovesKattintas(){
  const lathato = lovesJelek.filter(j => j.visible);
  if (!lathato.length) return false;
  const t = sugar.intersectObjects(lathato, false)[0];
  if (!t) return false;
  const [mp, hazai, x, y, xg, kimenet, goalX] = t.object.userData.loves;
  ido = Math.max(0, mp - 4); megy = true; lejatszasGomb.textContent = "⏸";
  csuszka.value = ido;
  meresRajzol(x, y, goalX > H/2 ? "jobb" : "bal");
  const o = Math.floor(mp/60), s = Math.floor(mp%60);
  meresElem.insertAdjacentHTML("afterbegin",
    "<b>" + (hazai ? ADAT.home : ADAT.away) + " lövése</b> " + o + ":" +
    String(s).padStart(2, "0") + " · " + KIMENET[kimenet] + " · xG " +
    xg.toFixed(2).replace(".", ",") + "<br>");
  return true;
}

// ---- Védekezés-panel: tankönyvi fal vs a valódi -------------------
const falValaszto = document.getElementById("fal");
const falOldal = document.getElementById("falOldal");
const falInfo = document.getElementById("falInfo");
const FORMAK = ADAT.formations || {};
const FAL = ADAT.defence || [];
const FELTORES = ADAT.breakpoints || {home: [], away: []};
const MEGALLITAS = ADAT.stoppers || {home: [], away: []};
// A feltörés sávja a padlón (court3d.breakpoint_zone_band tükre): piros,
// áttetsző téglalap a védett kapu előtt, a 9 m-es vonalig, a sáv
// harmadában — a sáv a VÉDŐ nézőpontjából (a 0-s kaput védőnek a
// nagyobb y a bal keze).
const feltoresSik = new THREE.Mesh(new THREE.PlaneGeometry(1, 1),
  new THREE.MeshBasicMaterial({color:0xff6b6b, transparent:true, opacity:0.22, depthWrite:false, side:THREE.DoubleSide}));
feltoresSik.rotation.x = -Math.PI/2; feltoresSik.visible = false;
szinpad.add(feltoresSik);
function feltoresSav(sav, goalX){
  if (!["bal szél", "közép", "jobb szél"].includes(sav)) return null;
  const harmad = W / 3, balKapu = goalX < H / 2;
  let y0, y1;
  if (sav === "közép"){ y0 = harmad; y1 = 2*harmad; }
  else if ((sav === "bal szél") === balKapu){ y0 = 2*harmad; y1 = W; }
  else { y0 = 0; y1 = harmad; }
  return {x0: balKapu ? 0 : H - 9, x1: balKapu ? 9 : H, y0, y1};
}
const falCsoport = new THREE.Group();
szinpad.add(falCsoport);
const falGyuruk = [];
for (let i = 0; i < 6; i++){
  const g = new THREE.Mesh(new THREE.RingGeometry(0.34, 0.46, 28),
    new THREE.MeshBasicMaterial({color:0xd9b544, transparent:true, opacity:0.8, side:THREE.DoubleSide}));
  g.rotation.x = -Math.PI/2; g.position.y = 0.025; g.visible = false;
  falCsoport.add(g); falGyuruk.push(g);
}
// Az élő fal: a legutóbbi idővonal-sor, ha 1,5 mp-nél nem régebbi.
function eloFal(t){
  let lo = 0, hi = FAL.length - 1, talalt = -1;
  while (lo <= hi){ const k = (lo + hi) >> 1; if (FAL[k][0] <= t){ talalt = k; lo = k + 1; } else hi = k - 1; }
  if (talalt < 0 || t - FAL[talalt][0] > 1.5) return null;
  const r = FAL[talalt];
  return {hazai: !!r[1], cimke: r[2], goalX: r[3]};
}
// Átlagos eltérés a sablontól: mohó párosítás (a legközelebbi pár előbb).
function elteres(vedok, pontok){
  const parok = [];
  vedok.forEach((v, i) => pontok.forEach((p, j) =>
    parok.push([Math.hypot(v[0] - p[0], v[1] - p[1]), i, j])));
  parok.sort((a, b) => a[0] - b[0]);
  const vi = new Set(), pj = new Set();
  let osszeg = 0, db = 0;
  for (const [d, i, j] of parok){
    if (vi.has(i) || pj.has(j)) continue;
    vi.add(i); pj.add(j); osszeg += d; db++;
  }
  return db ? osszeg / db : null;
}
let falSzoveg = "";
function falKiir(s){ if (s !== falSzoveg){ falSzoveg = s; falInfo.innerHTML = s; } }
function falFrissit(t){
  const valasztas = falValaszto.value;
  falGyuruk.forEach(g => g.visible = false);
  if (!valasztas){ falKiir(""); return; }
  const elo = eloFal(t);
  const nev = valasztas === "elo" ? (elo ? elo.cimke : null) : valasztas;
  let goalX = null;
  if (falOldal.value === "bal") goalX = 0;
  else if (falOldal.value === "jobb") goalX = H;
  else if (elo) goalX = elo.goalX;
  const csapat = elo ? (elo.hazai ? ADAT.home : ADAT.away) : null;
  const sorok = [];
  if (elo) sorok.push("Most: " + hx(csapat) + " védekezik — <b>" + hx(elo.cimke) + "</b>");
  else sorok.push("Most nincs szervezett támadás — a fal nem áll.");
  // Feltörés: a védekező csapat falának leggyengébb pontja (a felderítés
  // rangsorának teteje) — hol és mivel kell támadni ellene.
  feltoresSik.visible = false;
  if (elo){
    const f = (elo.hazai ? FELTORES.home : FELTORES.away) || [];
    if (f.length) sorok.push("Feltörés: <b>" + f[0].hol + "</b> — " + f[0].mivel +
      " <span style='opacity:.7'>(" + f[0].miert + ")</span>");
    // Megállítás: a TÁMADÓ csapat támadásának leggyengébb pontja — mivel
    // állíthatja meg a védekező csapat (a felderítés rangsorának teteje).
    const m = (elo.hazai ? MEGALLITAS.away : MEGALLITAS.home) || [];
    if (m.length) sorok.push("Megállítás: <b>" + m[0].hol + "</b> — " + m[0].mivel +
      " <span style='opacity:.7'>(" + m[0].miert + ")</span>");
    // Az első sávos tétel piros sávként a padlón, a védett kapu előtt.
    const savos = f.find(t => t.sav);
    const sav = savos ? feltoresSav(savos.sav, elo.goalX) : null;
    if (sav){
      feltoresSik.scale.set(sav.x1 - sav.x0, sav.y1 - sav.y0, 1);
      feltoresSik.position.set((sav.x0 + sav.x1)/2, 0.012, W - (sav.y0 + sav.y1)/2);
      feltoresSik.visible = true;
      sorok.push("<span style='color:#ff6b6b'>piros sáv: ide kell betörni</span>");
    }
  }
  const sablon = nev ? FORMAK[nev] : null;
  if (sablon && goalX !== null){
    const jobb = goalX > H/2;
    const pontok = sablon.map(p => [jobb ? H - p[0] : p[0], p[1]]);
    pontok.forEach((p, i) => { falGyuruk[i].visible = true;
      falGyuruk[i].position.set(p[0], 0.025, W - p[1]); });
    sorok.push(nev + " sablon a " + (jobb ? "jobb" : "bal") + " kapu előtt (sárga körök)");
    // Eltérés a valódi faltól — csak ha épp az a kapu a védett.
    if (elo && elo.goalX === goalX){
      const vedok = allas.filter(s => s.hazai === elo.hazai && !s.kapus
        && Math.abs(s.x - goalX) > 2.0).map(s => [s.x, s.y]);
      if (vedok.length >= 4){
        const e = elteres(vedok, pontok);
        if (e !== null) sorok.push("Átlagos eltérés a tankönyvi faltól: " + szam1(e) + " m");
      }
    }
  } else if (valasztas === "elo" && elo){
    sorok.push("(ehhez a formához nincs tankönyvi sablon)");
  } else if (sablon && goalX === null){
    sorok.push("Válassz kaput, vagy várj egy szervezett támadásra.");
  }
  falKiir(sorok.join("<br>"));
}

function mozgas(dt){
  if (mod === "kering"){
    const cp = Math.cos(kering.phi);
    rig.position.set(CEL.x + Math.sin(kering.theta) * cp * kering.r,
                     CEL.y + Math.sin(kering.phi) * kering.r,
                     CEL.z + Math.cos(kering.theta) * cp * kering.r);
    if (!fest.xr.isPresenting){ rig.rotation.y = kering.theta; kamera.rotation.set(-kering.phi, 0, 0); }
    return;
  }
  if (mod === "jatekos" || mod === "kovetes" || mod === "tv") return;  // a követő módok viszik a kamerát
  const seb = (gombok.has("ShiftLeft")||gombok.has("ShiftRight")) ? 12 : 5;
  const ex = -Math.sin(yaw), ez = -Math.cos(yaw);
  const jx = Math.cos(yaw), jz = -Math.sin(yaw);
  if (gombok.has("KeyW")){ rig.position.x += ex*seb*dt; rig.position.z += ez*seb*dt; }
  if (gombok.has("KeyS")){ rig.position.x -= ex*seb*dt; rig.position.z -= ez*seb*dt; }
  if (gombok.has("KeyA")){ rig.position.x -= jx*seb*dt; rig.position.z -= jz*seb*dt; }
  if (gombok.has("KeyD")){ rig.position.x += jx*seb*dt; rig.position.z += jz*seb*dt; }
  if (gombok.has("KeyR")) rig.position.y += seb*dt;
  if (gombok.has("KeyF") || gombok.has("KeyC")) rig.position.y = Math.max(0.4, rig.position.y - seb*dt);
  if (!fest.xr.isPresenting){ kamera.rotation.set(pitch, 0, 0); rig.rotation.y = yaw; }
}
// VR-locomotion: a bal kar hüvelykujj-karja a nézés iránya szerint visz.
// A JOBB kar oldalra billentése: SNAP-FORDULÁS VR_FORDUL_FOK fokkal (ülve,
// forgószék nélkül is körbe lehet nézni; a folyamatos forgatás sokaknál
// émelygést okoz). Él-érzékelés: egy kitérés (VR_FORDUL_KUSZOB fölött) egy
// fordulás; a kar visszaengedése után jöhet a következő. A forgatás a FEJ
// körül megy (a fej helye marad).
const VR_FORDUL_FOK = 30, VR_FORDUL_KUSZOB = 0.7;
let vrFordulKi = false;
const vrFejA = new THREE.Vector3(), vrFejB = new THREE.Vector3();
function vrFordul(irany){
  kamera.getWorldPosition(vrFejA);
  rig.rotation.y += irany * VR_FORDUL_FOK * Math.PI / 180;
  rig.updateMatrixWorld(true);
  kamera.getWorldPosition(vrFejB);
  rig.position.x += vrFejA.x - vrFejB.x; rig.position.z += vrFejA.z - vrFejB.z;
}
// Egy kontroller karja (kez: "left" / "right" / ""): a jobb kéz fordít,
// a többi mozgat a nézés iránya szerint.
function vrKar(kez, ax, ay, dt){
  if (kez === "right"){
    const ki = Math.abs(ax) > VR_FORDUL_KUSZOB;
    if (ki && !vrFordulKi) vrFordul(ax > 0 ? -1 : 1);
    vrFordulKi = ki;
    return;
  }
  if (Math.abs(ax) < 0.15 && Math.abs(ay) < 0.15) return;
  const irany = new THREE.Vector3();
  kamera.getWorldDirection(irany); irany.y = 0; irany.normalize();
  const oldal = new THREE.Vector3().crossVectors(
    irany, new THREE.Vector3(0,1,0));
  rig.position.addScaledVector(irany, -ay * 3 * dt);
  rig.position.addScaledVector(oldal, ax * 3 * dt);
}
function vrMozgas(dt){
  const munkamenet = fest.xr.getSession && fest.xr.getSession();
  if (!munkamenet) return;
  for (const forras of munkamenet.inputSources){
    const gp = forras.gamepad;
    if (!gp || gp.axes.length < 4) continue;
    vrKar(forras.handedness || "", gp.axes[2], gp.axes[3], dt);
  }
}
// (próbához: a kar egy kitérése headset nélkül)
window.vrKarMozgasProba = (kez, ax, ay) => {
  vrKar(kez, ax, ay, 0.1);
  kamera.getWorldPosition(vrFejA);
  return {fok: Math.round(rig.rotation.y * 180 / Math.PI * 10) / 10,
          fej: [Math.round(vrFejA.x * 100) / 100, Math.round(vrFejA.z * 100) / 100],
          rig: [Math.round(rig.position.x * 100) / 100, Math.round(rig.position.z * 100) / 100]};
};

// ---- VR-kontroller: jelenet-lapozás a headsetben -------------------------
// A DOM-gombok VR-ben nem érhetők el: a kontroller A/X gombja (4) a
// következő, B/Y gombja (5) az előző jelenetre ugrik (a jelenet-lista
// sorai, a "Kinek a hibái" szűrő szerint), a ravasz (0) lejátszás/szünet,
// a hüvelykujj-kar lenyomása (3) a vetítés ki/be.
// Él-érzékelés: egy lenyomás egy lépés, a nyomva tartás nem pörget.
const vrGombElozo = new Map();
function vrGombEl(kulcs, index, lenyomva){
  // Igaz, ha a gomb MOST lett lenyomva (az előző kockán nem volt).
  const regi = vrGombElozo.get(kulcs) || [];
  const el = !!lenyomva && !regi[index];
  regi[index] = !!lenyomva; vrGombElozo.set(kulcs, regi);
  return el;
}
// A jelenet-lépés KÖZÖS a kontroller-gombokkal és az N/P billentyűkkel.
let vrJelenetUtolso = null;
function jelenetLep(irany){
  const sorok = jelenetSorokSzurt();
  if (!sorok.length) return null;
  const cel = lapozCel(sorok.map(r => r.s), ido, vrJelenetUtolso, irany);
  if (cel === null) return null;
  vrJelenetUtolso = cel;
  const r = sorok.find(x => x.s === cel);
  jelenetUgras(r);
  return r;
}
// A hüvelykujj-kar lenyomása: a vetítés ki/be — a közös nézés
// vezetőjeként a BAL kézben a kvíz következő lépése (indítás → felfedés →
// vége), hogy a kvíz a headsetből is vezethető legyen.
function vrKarNyomas(kez){
  if (kozosMod === "vezet" && kez === "left") kvizGomb.onclick();
  else vetitesAllit(!vetites);
}
window.vrKarProba = (kez) => vrKarNyomas(kez);
function vrGombok(){
  const munkamenet = fest.xr.getSession && fest.xr.getSession();
  if (!munkamenet) return;
  let k = 0;
  for (const forras of munkamenet.inputSources){
    k++;
    const gp = forras.gamepad;
    if (!gp || !gp.buttons) continue;
    const kulcs = (forras.handedness || "") + k;
    const nyom = (i) => !!(gp.buttons[i] && gp.buttons[i].pressed);
    // (a felvétel visszajátszásakor a fejezetek között)
    if (vrGombEl(kulcs, 4, nyom(4))){ if (fvLejatszas) felvetelFejezet(1); else jelenetLep(1); }
    if (vrGombEl(kulcs, 5, nyom(5))){ if (fvLejatszas) felvetelFejezet(-1); else jelenetLep(-1); }
    if (vrGombEl(kulcs, 0, nyom(0))){
      // Kvíz közben a követő ravasza a VÁLASZ (a kontroller sugarával).
      if (kvizValaszolhat()) vrValasz(k - 1);
      else if (fvLejatszas) felvetelGomb.onclick();
      else { megy = !megy; lejatszasGomb.textContent = megy ? "⏸" : "▶"; }
    }
    if (vrGombEl(kulcs, 3, nyom(3))) vrKarNyomas(forras.handedness);
    // Közös nézés vezetőként VR-ből: a markolat (1) a bal kézben "📍 Ide
    // mindenki", a jobb (vagy kéz nélküli) kontrolleren MUTATÓ a sugár
    // padló-metszetén.
    if (kozosMod === "vezet" && vrGombEl(kulcs, 1, nyom(1))){
      if (forras.handedness === "left") ideGomb.onclick();
      else vrMutat(k - 1);
    }
    // Követőként a markolat: ✋ kérdésem van / kéz le.
    if (kozosMod === "kovet" && vrGombEl(kulcs, 1, nyom(1))) kezAllit(!kzKez);
  }
}
window.vrJelenetLep = jelenetLep;  // a próbához: a kontroller-gomb párja

// ---- VR-felirat: a jelenet-feliratok a headsetben ----------------------
// A DOM-feliratok (esemény, döntés, szabad lövő, labdavesztés, gól-akció,
// emberelőny) a headsetben nem látszanak: VR-ben ugyanezeket egy, a
// fejhez rögzített táblára rajzoljuk (a kamera gyermeke — mindig szem
// előtt, a padló-vonalak nem takarják). A ?vrfelirat=1 headset nélkül
// is bekapcsolja (próbához).
const VR_FELIRAT_FORRASOK = ["vetitesJelzo", "jegyzetFelirat", "felirat", "dontesFelirat", "szabadFelirat", "eladasFelirat", "golFelirat", "kontraFelirat", "kapottFelirat", "hetesFelirat", "emberJelzo"];
const vrVaszon = document.createElement("canvas"); vrVaszon.width = 1024; vrVaszon.height = 320;
const vrTextura = new THREE.CanvasTexture(vrVaszon);
const vrTabla = new THREE.Sprite(new THREE.SpriteMaterial({map: vrTextura, transparent: true, depthTest: false}));
vrTabla.position.set(0, -0.42, -1.4); vrTabla.scale.set(1.28, 0.4, 1); vrTabla.visible = false;
kamera.add(vrTabla);
const VR_FELIRAT_KENYSZER = new URLSearchParams(location.search).get("vrfelirat") === "1";
let vrFeliratUtolso = null;
function vrFeliratSzoveg(){
  const sorok = VR_FELIRAT_FORRASOK.map(id => document.getElementById(id))
    .filter(e => e && e.style.display === "block")
    .map(e => e.textContent.replace(/\\s+/g, " ").trim()).filter(Boolean);
  // A követő a headsetben is lássa a közös nézés állapotát (a HTML panel
  // VR-ben nem látszik): váltáskor rövid ideig, hibánál végig.
  const kz = kozosMod === "kovet" ? kozosInfo.textContent : "";
  if (kz && (kz !== KZ_KOVETED || performance.now() - kzInfoValtas < KZ_VR_MS))
    sorok.unshift(kz);
  // A felvétel visszajátszása (a ravasz: szünet/tovább).
  if (!kozosMod && fvLejatszas && kozosInfo.textContent)
    sorok.unshift(kozosInfo.textContent + " — ravasz: szünet/tovább");
  // A vezető a kérdezni akarókat látja (VR-ben a felirat-sor nem látszik).
  if (kozosMod === "vezet" && kzKezek().length)
    sorok.unshift("✋ Kérdése van: " + kzKezek().join(", "));
  // A vezető a kvíz állását látja (a HTML panel VR-ben nem látszik).
  if (kozosMod === "vezet" && kzKviz)
    sorok.unshift("❓ Kvíz" + (kzKviz.mutat ? " (a csapat is látja)" : "") + ": "
      + kzValaszDb + "/" + (kzKovetok || 0) + " válasz"
      + (kvizDontes(kzKviz) ? " · ✓ " + kzJoDb : "")
      + " — bal hüvelykujj-kar: " + (kzKviz.mutat ? "vége" : "mutasd a csapatnak"));
  return sorok;
}
function vrSorok(szoveg, max){
  const ki = []; let sor = "";
  for (const szo of szoveg.split(" ")){
    if (sor && (sor + " " + szo).length > max){ ki.push(sor); sor = szo; }
    else sor = sor ? sor + " " + szo : szo;
  }
  if (sor) ki.push(sor);
  return ki;
}
function vrFeliratFrissit(){
  if (!(fest.xr.isPresenting || VR_FELIRAT_KENYSZER)){ vrTabla.visible = false; vrFeliratUtolso = null; return; }
  const sorok = vrFeliratSzoveg();
  const kulcs = sorok.join("\\n");
  if (kulcs === vrFeliratUtolso) return;
  vrFeliratUtolso = kulcs;
  if (!sorok.length){ vrTabla.visible = false; return; }
  const tordelt = [];
  for (const sz of sorok) tordelt.push(...vrSorok(sz, 56));
  const sorokKesz = tordelt.slice(0, 6);
  const g = vrVaszon.getContext("2d");
  g.clearRect(0, 0, vrVaszon.width, vrVaszon.height);
  const mag = 44 * sorokKesz.length + 30;
  g.fillStyle = "rgba(16,24,32,0.9)";
  g.beginPath(); g.roundRect(8, 8, vrVaszon.width - 16, mag, 18); g.fill();
  g.strokeStyle = "#d9b544"; g.lineWidth = 3; g.stroke();
  g.fillStyle = "#eaeef5"; g.font = "30px sans-serif"; g.textBaseline = "top";
  sorokKesz.forEach((sz, i) => g.fillText(sz, 28, 26 + i * 44));
  vrTextura.needsUpdate = true;
  vrTabla.visible = true;
}
window.vrFeliratProba = () => ({latszik: vrTabla.visible, sorok: vrFeliratSzoveg()});

const idoCimke = document.getElementById("ido");
linkAlkalmaz();
jegyzetBetolt();
fest.setAnimationLoop(() => {
  const most = performance.now();
  const dt = Math.min(0.1, (most - utolso)/1000); utolso = most;
  if (megy){ const t0 = ido; ido = Math.min(veg, ido + dt * sebesseg);
    vetitesFrissit(t0, ido);
    if (ido >= veg){ megy = false; lejatszasGomb.textContent = "▶"; }
    csuszka.value = ido; }
  mozgas(dt); vrMozgas(dt); vrGombok(); rajzol(ido); kovetFrissit(dt); kovetesFrissit(dt); tvFrissit(dt); falFrissit(ido); lovesFrissit(ido); nyomFrissit(ido); passzFrissit(ido); passzsavFrissit(); falresFrissit(ido); dontesFrissit(ido); jelenetListaJelol(ido); jegyzetFrissit(ido); videoFrissit(ido); kozosFrissit(); mutatoFrissit(); jelenletFrissit(dt); felvetelFrissit(); valaszJelFrissit(); felirat(ido); vrFeliratFrissit();
  const o = Math.floor(ido/60), mp = Math.floor(ido%60);
  idoCimke.textContent = o + ":" + String(mp).padStart(2,"0");
  fest.render(szinpad, kamera);
});
</script></body></html>
"""
    from .court3d import (PASS_LANE_GOOD, PASS_LANE_RISKY,
                          PASS_LANE_WIDTH_M, SCENE_REEL_TAIL_S,
                          SHARED3D_NAME_MAX, SHARED3D_NEAR_M,
                          SHARED3D_POINTER_S, SHARED3D_POLL_S,
                          SHARED3D_QUIZ_HIT_M, SHARED3D_QUIZ_SHOT_M,
                          SHARED3D_REC_MAX, SHARED3D_REC_WATCHED_FRAC,
                          SHARED3D_SEND_S, SHARED3D_TOLERANCE_S)
    from .defense import WALL_GAP_DEPTH_M, WALL_GAP_M, WALL_GAP_MIN_DEFENDERS
    from .tactics import TacticsConfig
    ps_kod = (f"const PS_SUGAR = {TacticsConfig().possession_radius_m}, "
              f"PS_SZEL = {PASS_LANE_WIDTH_M}, PS_JO = {PASS_LANE_GOOD}, "
              f"PS_KOCK = {PASS_LANE_RISKY};" + PASSZSAV_JS
              + f"const FR_RES = {WALL_GAP_M}, FR_MELY = {WALL_GAP_DEPTH_M}, "
              f"FR_MIN = {WALL_GAP_MIN_DEFENDERS};" + FALRES_JS)
    return (oldal.replace("__CIM__", cim.replace("<", "&lt;"))
                 .replace("__JL_VETITES_S__", repr(float(SCENE_REEL_TAIL_S)))
                 .replace("__KZ_KULD__", repr(float(SHARED3D_SEND_S)))
                 .replace("__KZ_KERD__", repr(float(SHARED3D_POLL_S)))
                 .replace("__KZ_TURES__", repr(float(SHARED3D_TOLERANCE_S)))
                 .replace("__KZ_MUTATO__", repr(float(SHARED3D_POINTER_S)))
                 .replace("__KZ_NEV_MAX__", str(int(SHARED3D_NAME_MAX)))
                 .replace("__KZ_KOZEL__", repr(float(SHARED3D_NEAR_M)))
                 .replace("__FV_MAX__", str(int(SHARED3D_REC_MAX)))
                 .replace("__FV_MEGNEZTE__", repr(float(SHARED3D_REC_WATCHED_FRAC)))
                 .replace("__PASSZSAV_JS__", ps_kod + LAPOZO_JS
                          + JELENETLISTA_JS + GOLAKCIO_JS + EMBERELONY_JS
                          + KLIPALLAPOT_JS + KONTRA_JS + KAPOTT_JS
                          + HETES_JS + RAJZ_JS
                          + KVIZ_JS.replace(
                              "__KV_TALALAT__",
                              repr(float(SHARED3D_QUIZ_HIT_M))).replace(
                              "__KV_LOVES__",
                              repr(float(SHARED3D_QUIZ_SHOT_M))))
                 .replace("__LOVES_JS__", LOVES_MERES_JS)
                 .replace("__ADAT__", adat))


# A three.js (0.160.0, MIT) a csomagban — a motor /vendor/three útjának
# forrása.
_THREE_VENDOR = Path(__file__).resolve().parent.parent / "vendor" / "three"


def view3d_csomag(oldal: str, felvetel: dict, hang: tuple | None = None) -> str:
    """📦 A FELVÉTEL-CSOMAG: a kész 3D oldalból (view3d_html) egyetlen,
    motor és internet nélkül is futó HTML-fájl. A three.js és a VRButton
    beágyazva (data: URL az import-térképben — a motor /vendor útja
    helyett), a felvétel (fejezetekkel) és a hang (`hang`: (bájtok,
    típus) — data: URL) a FV_CSOMAG állandóban; az oldal ilyenkor a
    meccs-azonosítót üresre állítja (a motoros funkciók — közös nézés,
    jegyzet, videó — kikapcsolnak, mint a mentett oldalnál), és a
    felvétel magától indul. A játékos otthon, a klub hálózata nélkül is
    megnézheti — böngészőben vagy headsetben."""
    import base64

    def data_url(tipus: str, bajtok: bytes) -> str:
        return f"data:{tipus};base64," + base64.b64encode(bajtok).decode("ascii")

    regi = ('''<script type="importmap">{"imports":{
 "three":"/vendor/three@0.160.0/build/three.module.js",
 "three/addons/":"/vendor/three@0.160.0/examples/jsm/"
}}</script>''')
    if oldal.count(regi) != 1:
        raise ValueError("a 3D oldal import-térképe nem a várt alakú")
    three = (_THREE_VENDOR / "build" / "three.module.js").read_bytes()
    vr = (_THREE_VENDOR / "examples" / "jsm" / "webxr" / "VRButton.js").read_bytes()
    uj = ('<script type="importmap">{"imports":{\n "three":"'
          + data_url("text/javascript", three)
          + '",\n "three/addons/webxr/VRButton.js":"'
          + data_url("text/javascript", vr) + '"\n}}</script>')
    csomag = {"adat": felvetel,
              "hang": data_url(hang[1], hang[0]) if hang else None}
    # (a beágyazott JSON-ban a "</" nem zárhatja le a szkriptet)
    kod = json.dumps(csomag, ensure_ascii=False,
                     separators=(",", ":")).replace("</", "<\\/")
    jel = "const FV_CSOMAG = null;"
    if oldal.count(jel) != 1:
        raise ValueError("a 3D oldalban nincs csomag-hely")
    return (oldal.replace(regi, uj)
                 .replace(jel, "const FV_CSOMAG = " + kod + ";"))
