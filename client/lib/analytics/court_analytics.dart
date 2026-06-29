/// Kliensoldali elemzés — hőtérkép és játékos-statisztika a Match-ből.
///
/// A backend analytics.py / stats.py DART-tükre. Mivel a kliensnek úgyis megvan a
/// teljes Match (a backendtől vagy a beágyazott demóból), ezeket helyben is ki
/// tudja számolni — így a hőtérkép és a statisztika BACKEND NÉLKÜL is működik.
/// (Élesben ugyanezt a backend /heatmap és /stats végpontja is adja.)
library;

import "dart:math" as math;

import "../models/tracking.dart";
import "../ui/court_geometry.dart";

/// Egy játékos összesített statisztikája (táv, sebesség) — a stats.py tükre.
class PlayerStat {
  final int trackId;
  final Team team;
  final int? jerseyNumber;
  final double distanceM; // csak MÉRT pontok közötti táv
  final double avgSpeedMs;
  final int measuredFrames;
  final int estimatedFrames;

  PlayerStat({
    required this.trackId,
    required this.team,
    required this.jerseyNumber,
    required this.distanceM,
    required this.avgSpeedMs,
    required this.measuredFrames,
    required this.estimatedFrames,
  });
}

/// Játékosonkénti statisztika. A távot csak két egymást követő MÉRT pont között
/// számoljuk (a becsült mozgás nem valódi mérés) — pontosan mint a backend.
Map<int, PlayerStat> computePlayerStats(Match match) {
  final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
  final dt = 1.0 / fps;

  // track_id -> időrendi minták (x, y, source, team, jersey)
  final samples = <int, List<PlayerPosition>>{};
  for (final f in match.frames) {
    for (final p in f.players) {
      samples.putIfAbsent(p.trackId, () => []).add(p);
    }
  }

  final result = <int, PlayerStat>{};
  samples.forEach((trackId, pts) {
    double distance = 0.0;
    int measured = 0, estimated = 0;
    PlayerPosition? prev;
    for (final p in pts) {
      if (p.isEstimated) {
        estimated++;
      } else {
        measured++;
      }
      if (prev != null &&
          !prev.isEstimated &&
          !p.isEstimated) {
        distance += math.sqrt(
            math.pow(p.x - prev.x, 2) + math.pow(p.y - prev.y, 2));
      }
      prev = p;
    }
    final movingTime = math.max(1, measured) * dt;
    result[trackId] = PlayerStat(
      trackId: trackId,
      team: pts.first.team,
      jerseyNumber: pts.first.jerseyNumber,
      distanceM: distance,
      avgSpeedMs: distance / movingTime,
      measuredFrames: measured,
      estimatedFrames: estimated,
    );
  });
  return result;
}

/// Hőtérkép: a pályát rácsra osztva, cellánként a látogatottság.
class Heatmap {
  final int binsX;
  final int binsY;
  final List<List<double>> grid; // [binsY][binsX]
  final double total;
  final double maxCell;

  Heatmap(this.binsX, this.binsY, this.grid, this.total, this.maxCell);
}

/// Egy csapat hőtérképe (alapból csak a mért pozíciók) — az analytics.py tükre.
Heatmap computeTeamHeatmap(Match match, Team team,
    {int binsX = 20, int binsY = 10, bool includeEstimated = false}) {
  final grid = List.generate(binsY, (_) => List<double>.filled(binsX, 0.0));
  double total = 0.0, maxCell = 0.0;

  for (final f in match.frames) {
    for (final p in f.players) {
      if (p.team != team) continue;
      if (!includeEstimated && p.isEstimated) continue;
      var ix = (p.x / courtLength * binsX).floor();
      var iy = (p.y / courtWidth * binsY).floor();
      ix = ix.clamp(0, binsX - 1);
      iy = iy.clamp(0, binsY - 1);
      grid[iy][ix] += 1.0;
      total += 1.0;
      if (grid[iy][ix] > maxCell) maxCell = grid[iy][ix];
    }
  }
  return Heatmap(binsX, binsY, grid, total, maxCell);
}
