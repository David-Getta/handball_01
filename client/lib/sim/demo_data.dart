/// Beágyazott demó-adat — hogy a kliens BACKEND NÉLKÜL is azonnal mutasson valamit.
///
/// Egy egyszerű, mozgó szintetikus meccset épít Dart-ban (két csapat + labda,
/// egy-két becsült játékossal), hasonló szellemben a backend handball.sim
/// moduljához. Amint a lokális backend elérhető, helyette a valódi Tracking jön.
library;

import "dart:math" as math;

import "../models/tracking.dart";
import "../ui/court_geometry.dart";

Match buildDemoMatch({int frames = 200, double fps = 25.0}) {
  final meta = MatchMeta(
    matchId: "demo",
    homeTeam: "Demó Hazai",
    awayTeam: "Demó Vendég",
    fps: fps,
    frameWidth: 1920,
    frameHeight: 1080,
    date: "2026-06-29",
  );

  // Alappozíciók (méter): 7 hazai (támad jobbra) + 7 vendég (véd a jobb kapunál).
  final cy = courtWidth / 2;
  final home = [
    [30.0, 2.5], [28.0, 6.0], [27.0, cy], [28.0, 14.0],
    [30.0, 17.5], [34.0, cy], [1.0, cy],
  ];
  final away = [
    [35.5, 3.0], [35.0, 6.5], [34.8, cy - 1], [34.8, cy + 1],
    [35.0, 13.5], [35.5, 17.0], [39.0, cy],
  ];

  final frameList = <Frame>[];
  for (int t = 0; t < frames; t++) {
    final sec = t / fps;
    final players = <PlayerPosition>[];
    final homePos = <List<double>>[]; // a hazai aktuális pozíciói (a labda-útvonalhoz)

    for (int i = 0; i < home.length; i++) {
      final bx = (home[i][0] + 0.8 * math.sin(0.7 * sec + i)).clamp(0.0, courtLength).toDouble();
      final by = (home[i][1] + 1.2 * math.sin(0.5 * sec + i * 1.3)).clamp(0.0, courtWidth).toDouble();
      homePos.add([bx, by]);
      players.add(PlayerPosition(
        trackId: i + 1,
        team: Team.home,
        x: bx,
        y: by,
        source: PositionSource.measured,
        confidence: 1.0,
        jerseyNumber: i + 1,
        // A sor UTOLSÓ embere a kapus (a saját kapujában áll) — a 3D
        // nézet ettől mutatja őt eltérő mezben, mint a valóságban.
        role: i == home.length - 1 ? "kapus" : null,
      ));
    }
    for (int i = 0; i < away.length; i++) {
      final bx = away[i][0] + 0.6 * math.sin(0.6 * sec + i);
      final by = away[i][1] + 1.0 * math.sin(0.45 * sec + i);
      // A túloldali vendég kapus (utolsó) néha "becsült" — a halvány megjelenítés demója.
      final estimated = (i == away.length - 1) && (math.sin(0.3 * sec) < -0.2);
      players.add(PlayerPosition(
        trackId: 11 + i,
        team: Team.away,
        x: bx.clamp(0.0, courtLength).toDouble(),
        y: by.clamp(0.0, courtWidth).toDouble(),
        source: estimated ? PositionSource.estimated : PositionSource.measured,
        confidence: estimated ? 0.5 : 1.0,
        jerseyNumber: 11 + i,
        role: i == away.length - 1 ? "kapus" : null,
      ));
    }

    // Labda: körbejár a hazai játékosok közt (passz-útvonal), hogy legyenek
    // felismerhető passzok a döntéselemzéshez. ~1 mp-enként vált birtokost.
    const route = [2, 1, 0, 3, 4, 5]; // irányító → szélső/átlövő/beálló
    final holderIdx = route[(t ~/ 25) % route.length];
    final hp = homePos[holderIdx];
    frameList.add(Frame(
      t: t,
      players: players,
      ball: Ball(x: hp[0], y: hp[1], confidence: 1.0),
    ));
  }

  return Match(meta: meta, frames: frameList);
}

/// Demó-lövések a lövéstérképhez (backend nélkül): a /xg "shots"
/// alakjában — t (kocka), team, x, y, xg, outcome. A hazai a jobb kapura
/// lő (a demó-meccs szerint), a vendég a balra.
List<Map<String, dynamic>> buildDemoShots({int frames = 200, double fps = 25.0}) {
  final cy = courtWidth / 2;
  final minta = [
    // (hazai?, x, y, xG, kimenet) — szél, átlövés, beálló, hetes.
    (true, 33.5, 2.8, 0.18, "miss"),
    (true, 31.0, cy - 2.0, 0.09, "save"),
    (true, 34.6, cy + 0.5, 0.55, "goal"),
    (true, 33.0, 10.0, 0.72, "goal"),
    (false, 6.5, cy + 3.0, 0.21, "goal"),
    (false, 9.5, cy - 4.0, 0.08, "save"),
  ];
  return [
    for (var i = 0; i < minta.length; i++)
      {
        "t": ((i + 1) * frames / (minta.length + 1)).floor(),
        "team": minta[i].$1 ? "home" : "away",
        "x": minta[i].$2,
        "y": minta[i].$3,
        "xg": minta[i].$4,
        "outcome": minta[i].$5,
      }
  ];
}

/// Demó-passzok a 3D passz-vonalakhoz (backend nélkül): a demó-labda
/// ~1 mp-enként vált birtokost a hazai útvonalon; egy passz = az előző
/// és az új birtokos helye a váltás kockáján. Alak: t, team, x1, y1, x2, y2.
List<Map<String, dynamic>> buildDemoPasses(Match m, {int lepes = 25}) {
  const route = [2, 1, 0, 3, 4, 5];
  final ki = <Map<String, dynamic>>[];
  for (var t = lepes; t < m.frames.length; t += lepes) {
    final f = m.frames[t];
    final elozo = route[(t ~/ lepes - 1) % route.length];
    final uj = route[(t ~/ lepes) % route.length];
    PlayerPosition? ado, fogado;
    for (final p in f.players) {
      if (p.team != Team.home) continue;
      if (p.trackId == elozo + 1) ado = p;
      if (p.trackId == uj + 1) fogado = p;
    }
    if (ado == null || fogado == null) continue;
    ki.add({
      "t": t, "team": "home",
      "x1": ado.x, "y1": ado.y, "x2": fogado.x, "y2": fogado.y,
    });
  }
  return ki;
}

/// Demó döntés-pillanatok a 3D "Döntések" lapozójához (backend nélkül):
/// a /decision-moments "moments" alakjában. A demó-passzokból épül — a
/// jobb opció lövés a jobb kapura (a demóban a hazai arra támad);
/// SZINTETIKUS, csak a felület bemutatására.
List<Map<String, dynamic>> buildDemoDecisions(Match m, {int lepes = 25}) {
  final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
  final ki = <Map<String, dynamic>>[];
  for (final p in buildDemoPasses(m, lepes: lepes).take(2)) {
    ki.add({
      "s": ((p["t"] as int) - 1) / fps,
      "team": "home",
      "passer": [p["x1"], p["y1"]],
      "chosen": [p["x2"], p["y2"]],
      "chosen_value": 0.18,
      "best_kind": "shoot",
      "best": [courtLength, courtWidth / 2],
      "best_value": 0.36,
      "gap": 0.18,
    });
  }
  return ki;
}

/// Demó emberelőny-szakasz a 3D "Emberelőny" lapozójához és élő
/// jelzőjéhez (backend nélkül): a /powerplay-moments "moments" alakjában
/// — a vendég a meccs második harmadában hiányos, közben egy hazai gól.
/// SZINTETIKUS, csak a felület bemutatására.
List<Map<String, dynamic>> buildDemoPowerplays(Match m) {
  final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
  final hossz = m.frames.length / fps;
  final s = (hossz / 3 * 10).round() / 10, e = (hossz * 2 / 3 * 10).round() / 10;
  return [
    {
      "s": s, "e": e, "team_down": "away", "team_up": "home",
      "duration_s": ((e - s) * 10).round() / 10,
      "shots_up": 1, "goals_up": 1, "goals_down": 0,
      "goals": [[((s + e) / 2 * 10).round() / 10, "home"]],
    }
  ];
}

/// Demó gól-akció a 3D "Gól-akciók" lapozójához (backend nélkül): a
/// /goal-build-ups "moments" alakjában — a demó-passzok első háromból
/// álló lánca, a végén lövés a jobb kapura (a demóban a hazai arra
/// támad). SZINTETIKUS, csak a felület bemutatására.
List<Map<String, dynamic>> buildDemoGoalBuildUps(Match m) {
  final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
  final passzok = buildDemoPasses(m).take(3).toList();
  if (passzok.length < 3) return const [];
  final utolso = passzok.last;
  final golT = (utolso["t"] as int) + 20;
  return [
    {
      "s": (passzok.first["t"] as int) / fps,
      "goal_s": golT / fps,
      "team": "home",
      "passes": [
        for (final p in passzok)
          {
            "from": [p["x1"], p["y1"]],
            "to": [p["x2"], p["y2"]],
            "from_jersey": null,
            "to_jersey": null,
          }
      ],
      "shooter": [utolso["x2"], utolso["y2"]],
      "shooter_jersey": null,
      "goal": [courtLength, courtWidth / 2],
      "n_passes": 3,
      "duration_s": ((golT - (passzok.first["t"] as int)) / fps * 10).round() / 10,
    }
  ];
}

/// Demó lerohanás a 3D "Lerohanások" lapozójához (backend nélkül): a
/// /fast-break-moments "moments" alakjában — a hazai első embere a
/// félpályáról fut a jobb kapura (a demóban a hazai arra támad), az
/// indítópassz a saját térfélről, a végén gól. SZINTETIKUS, csak a
/// felület bemutatására.
List<Map<String, dynamic>> buildDemoFastBreaks(Match m) {
  final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
  final passzok = buildDemoPasses(m).take(1).toList();
  if (passzok.isEmpty) return const [];
  final t0 = passzok.first["t"] as int;
  final s = t0 / fps;
  const hossz = 2.5;
  return [
    {
      "s": s,
      "e": ((s + hossz) * 100).round() / 100,
      "shot_s": ((s + hossz + 0.1) * 100).round() / 100,
      "team": "home",
      "defending": "away",
      "duration_s": hossz,
      "advance_ms": 3.0,
      "outcome": "goal",
      "shooter_jersey": null,
      "first_jersey": null,
      "wave": "first",
      "ahead": true,
      "path": [
        for (var i = 0; i <= 5; i++) [21.0 + 2.6 * i, 10.0 - 0.3 * i]
      ],
      "shot": [34.0, 8.5],
      "ball": [14.0, 11.0],
      "goal": [courtLength, courtWidth / 2],
    }
  ];
}

/// Demó kapott gól a 3D "Kapott gólok" lapozójához (backend nélkül): a
/// /conceded-goals "moments" alakjában — a hazai lő a jobb kapura 9 m-en
/// túlról, a legközelebbi vendég védő 1,7 m-re, a vendég kapus 2,7 m-re
/// kint (a sáv és a kapu-szög a backend shot_geometry-jéből számolva, a
/// "kint" a backend CG_KEEPER_OUT_M = 2,5 m küszöbe).
/// SZINTETIKUS, csak a felület bemutatására.
List<Map<String, dynamic>> buildDemoConcededGoals(Match m) {
  final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
  final t = math.min(150, math.max(0, m.frames.length - 1));
  return [
    {
      "s": t / fps,
      "t": t,
      "team": "home",
      "defending": "away",
      "shooter": [30.5, 9.0],
      "shooter_jersey": null,
      "zone": "9 m-en túl",
      "angle_deg": 17.8,
      "dist_m": 9.55,
      "defender": [29.0, 9.8],
      "def_dist": 1.7,
      "free": false,
      "keeper": [37.3, 10.4],
      "keeper_depth": 2.73,
      "keeper_out": true,
      "xg": 0.31,
      "goal": [courtLength, courtWidth / 2],
    }
  ];
}

/// Demó hétméteres a 3D "Hétméteresek" lapozójához (backend nélkül): a
/// /seven-meter-moments "moments" alakjában — a hazai dob a jobb kapura,
/// középre, gól; a vendég kapus 0,9 m-re a kaputól. SZINTETIKUS, csak a
/// felület bemutatására.
List<Map<String, dynamic>> buildDemoSevens(Match m) {
  final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
  final t = math.min(200, math.max(0, m.frames.length - 1));
  return [
    {
      "s": t / fps,
      "t": t,
      "shot_s": (t + 25) / fps,
      "team": "home",
      "defending": "away",
      "spot": [33.0, 10.0],
      "shooter": [32.6, 10.0],
      "shooter_jersey": null,
      "outcome": "gól",
      "irany": "közép",
      "aim": [courtLength, courtWidth / 2],
      "keeper": [39.1, 9.6],
      "keeper_depth": 0.98,
      "goal": [courtLength, courtWidth / 2],
    }
  ];
}

/// Demó védekezés-idővonal a 3D védekezés-paneljéhez és a fal-résekhez
/// (backend nélkül): a /defence-timeline "rows" alakjában — a demóban a
/// vendég végig a jobb kapu előtt védekezik (hat mezőnyvédő ~5 m-re a
/// kaputól: 6-0). SZINTETIKUS, csak a felület bemutatására.
List<Map<String, dynamic>> buildDemoDefenceTimeline(Match m) {
  final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
  final hossz = m.frames.length / fps;
  return [
    for (var s = 0; s < hossz; s++)
      {
        "t": (s * fps).round(),
        "s": s.toDouble(),
        "defending": "away",
        "label": "6-0",
        "goal_x": courtLength,
      }
  ];
}

/// Demó labdavesztések a 3D "Labdavesztések" lapozójához (backend nélkül):
/// a /turnover-moments "moments" alakjában, a demó-meccs két kockájából (a
/// hazai labdás veszít, a legközelebbi vendég a nyomás) — SZINTETIKUS,
/// csak a felület bemutatására.
List<Map<String, dynamic>> buildDemoTurnovers(Match m) {
  final fps = m.meta.fps > 0 ? m.meta.fps : 25.0;
  final ki = <Map<String, dynamic>>[];
  for (final i in [m.frames.length * 3 ~/ 5, m.frames.length * 17 ~/ 20]) {
    if (i <= 0 || i >= m.frames.length) continue;
    final f = m.frames[i];
    PlayerPosition? vesztes, ellen;
    for (final p in f.players) {
      if (p.team == Team.home && p.trackId == 2) vesztes = p;
    }
    if (vesztes == null) continue;
    var legjobb = double.infinity;
    for (final p in f.players) {
      if (p.team != Team.away) continue;
      final d = math.sqrt(math.pow(p.x - vesztes.x, 2) + math.pow(p.y - vesztes.y, 2));
      if (d < legjobb) {
        legjobb = d;
        ellen = p;
      }
    }
    if (ellen == null) continue;
    final tav = (legjobb * 100).round() / 100;
    ki.add({
      "s": i / fps,
      "team": "home",
      "jersey": vesztes.jerseyNumber,
      "loser": [vesztes.x, vesztes.y],
      "ball": [vesztes.x + 0.4, vesztes.y],
      "zone": "közép",
      "opponent": [ellen.x, ellen.y],
      "dist": tav,
      "forced": tav <= 2.5,
      "punished": ki.isEmpty,
      "goal_after_s": ki.isEmpty ? 6.0 : null,
    });
  }
  return ki;
}

/// Demó szabad lövők a 3D "Szabad lövők" lapozójához (backend nélkül): a
/// /free-shots "moments" alakjában, a demó-lövésekből (a hazai lő, a
/// vendég védekezik) — SZINTETIKUS, csak a felület bemutatására.
List<Map<String, dynamic>> buildDemoFreeShots({int frames = 200, double fps = 25.0}) {
  return [
    for (final l in buildDemoShots(frames: frames, fps: fps)
        .where((l) => l["team"] == "home")
        .take(2))
      {
        "s": (l["t"] as int) / fps,
        "defending": "away",
        "shooter": [l["x"], l["y"]],
        "defender": [(l["x"] as double) + 2.6, (l["y"] as double) + 1.2],
        "dist": 2.86,
        "goal": l["outcome"] == "goal",
        "xg": l["xg"],
        "zone": "demó",
      }
  ];
}
