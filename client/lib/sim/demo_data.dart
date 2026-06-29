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

    for (int i = 0; i < home.length; i++) {
      final bx = home[i][0] + 0.8 * math.sin(0.7 * sec + i);
      final by = home[i][1] + 1.2 * math.sin(0.5 * sec + i * 1.3);
      players.add(PlayerPosition(
        trackId: i + 1,
        team: Team.home,
        x: bx.clamp(0.0, courtLength).toDouble(),
        y: by.clamp(0.0, courtWidth).toDouble(),
        source: PositionSource.measured,
        confidence: 1.0,
        jerseyNumber: i + 1,
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
      ));
    }

    // Labda: a hazai irányító (index 2) körül, kis mozgással.
    final bx = home[2][0] + 0.8 * math.sin(0.7 * sec + 2) + 1.0;
    final by = home[2][1] + 1.2 * math.sin(0.5 * sec + 2.6);
    frameList.add(Frame(
      t: t,
      players: players,
      ball: Ball(
          x: bx.clamp(0.0, courtLength).toDouble(),
          y: by.clamp(0.0, courtWidth).toDouble(),
          confidence: 1.0),
    ));
  }

  return Match(meta: meta, frames: frameList);
}
