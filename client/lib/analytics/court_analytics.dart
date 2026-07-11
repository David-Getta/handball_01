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

// Sprint-elemzés küszöbei (a backend stats.py-jal azonosan, kézilabdára):
const double sprintSpeedMs = 5.0; // e fölött sprint a mozgás (m/s)
const double sprintMinS = 0.5; // legalább ennyi ideig kell tartania (mp)
const double maxPlausibleMs = 11.0; // efölött követési hiba — kihagyjuk

/// Egy játékos összesített statisztikája (táv, sebesség, terhelés) — a
/// stats.py tükre.
class PlayerStat {
  final int trackId;
  final Team team;
  final int? jerseyNumber;
  final double distanceM; // csak MÉRT pontok közötti táv
  final double avgSpeedMs;
  final int measuredFrames;
  final int estimatedFrames;
  final double topSpeedMs; // legnagyobb (simított) sebesség
  final int sprintCount; // tartósan gyors szakaszok száma
  final double sprintDistanceM; // a sprintekben megtett táv
  final Map<String, double> zoneSeconds; // seta/kocogas/futas/sprint (mp)

  PlayerStat({
    required this.trackId,
    required this.team,
    required this.jerseyNumber,
    required this.distanceM,
    required this.avgSpeedMs,
    required this.measuredFrames,
    required this.estimatedFrames,
    this.topSpeedMs = 0.0,
    this.sprintCount = 0,
    this.sprintDistanceM = 0.0,
    this.zoneSeconds = const {},
  });
}

/// Játékosonkénti statisztika. A távot csak két egymást követő MÉRT pont között
/// számoljuk (a becsült mozgás nem valódi mérés) — pontosan mint a backend.
Map<int, PlayerStat> computePlayerStats(Match match) {
  final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
  final dt = 1.0 / fps;

  // track_id -> időrendi minták (frame-idő + pozíció)
  final samples = <int, List<(int, PlayerPosition)>>{};
  for (final f in match.frames) {
    for (final p in f.players) {
      samples.putIfAbsent(p.trackId, () => []).add((f.t, p));
    }
  }

  final result = <int, PlayerStat>{};
  samples.forEach((trackId, pts) {
    double distance = 0.0;
    int measured = 0, estimated = 0;
    PlayerPosition? prev;
    for (final (_, p) in pts) {
      if (p.isEstimated) {
        estimated++;
      } else {
        measured++;
      }
      if (prev != null && !prev.isEstimated && !p.isEstimated) {
        distance += math.sqrt(
            math.pow(p.x - prev.x, 2) + math.pow(p.y - prev.y, 2));
      }
      prev = p;
    }
    final movingTime = math.max(1, measured) * dt;
    // Terhelés-monitor: csúcssebesség, sprintek, zóna-idők (mint a backend).
    final segments = _speedSegments(pts, dt);
    var topSpeed = 0.0;
    var sprintCount = 0;
    var sprintDist = 0.0;
    final zones = {"seta": 0.0, "kocogas": 0.0, "futas": 0.0, "sprint": 0.0};
    var runS = 0.0, runD = 0.0;
    void closeRun() {
      if (runS >= sprintMinS) {
        sprintCount++;
        sprintDist += runD;
      }
      runS = runD = 0.0;
    }

    for (final (seconds, dist, speed) in segments) {
      if (speed > topSpeed) topSpeed = speed;
      final zone = speed < 1.4
          ? "seta"
          : speed < 3.0
              ? "kocogas"
              : speed < 5.0
                  ? "futas"
                  : "sprint";
      zones[zone] = zones[zone]! + seconds;
      if (speed >= sprintSpeedMs) {
        runS += seconds;
        runD += dist;
      } else {
        closeRun();
      }
    }
    closeRun();

    result[trackId] = PlayerStat(
      trackId: trackId,
      team: pts.first.$2.team,
      jerseyNumber: pts.first.$2.jerseyNumber,
      distanceM: distance,
      avgSpeedMs: distance / movingTime,
      measuredFrames: measured,
      estimatedFrames: estimated,
      topSpeedMs: topSpeed,
      sprintCount: sprintCount,
      sprintDistanceM: sprintDist,
      zoneSeconds: zones,
    );
  });
  return result;
}

/// A MÉRT pontpárok közti (idő mp, táv m, simított sebesség m/s) szakaszok —
/// a backend _speed_segments tükre: max 3 kockányi lyukat hidalunk át, a
/// követési hibás (irreálisan gyors) szakaszokat kihagyjuk, a sebességet
/// 3 szakaszos mozgóátlaggal simítjuk.
List<(double, double, double)> _speedSegments(
    List<(int, PlayerPosition)> pts, double dt) {
  final raw = <(double, double)>[]; // (szakasz-idő mp, táv m)
  (int, PlayerPosition)? prev;
  for (final s in pts) {
    if (s.$2.isEstimated) continue;
    if (prev != null) {
      final gap = s.$1 - prev.$1;
      if (gap > 0 && gap <= 3) {
        final seconds = gap * dt;
        final dist = math.sqrt(math.pow(s.$2.x - prev.$2.x, 2) +
            math.pow(s.$2.y - prev.$2.y, 2));
        if (seconds > 0 && dist / seconds <= maxPlausibleMs) {
          raw.add((seconds, dist));
        }
      }
    }
    prev = s;
  }
  final out = <(double, double, double)>[];
  for (var i = 0; i < raw.length; i++) {
    var wsec = 0.0, wdist = 0.0;
    for (var j = math.max(0, i - 1); j < math.min(raw.length, i + 2); j++) {
      wsec += raw[j].$1;
      wdist += raw[j].$2;
    }
    out.add((raw[i].$1, raw[i].$2, wsec > 0 ? wdist / wsec : 0.0));
  }
  return out;
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
