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
