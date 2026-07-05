/// Kliensoldali játékos-döntéselemzés — a backend decisions.py Dart-tükre.
///
/// Egy kiválasztott játékos passz-döntéseit elemzi: kihez passzol (eloszlás) és
/// mennyire optimálisan (az értékmodell szerinti legjobb opcióhoz képest). A
/// kliensen számolva, így backend nélkül, demóval is működik.
library;

import "dart:math" as math;

import "../models/tracking.dart";
import "../ui/court_geometry.dart";
import "tactics.dart";

const double _goalY = courtWidth / 2.0; // a kapu közepe y-ban (10 m)

/// xG-szerű lövésérték (0..1) a pozícióból, a megadott kapu felé.
double shotValue(double px, double py, double goalX) {
  final dist = math.sqrt(math.pow(px - goalX, 2) + math.pow(py - _goalY, 2));
  final lateral = (py - _goalY).abs();
  final angleFactor = math.max(0.25, 1.0 - lateral / 14.0);
  final base = math.max(0.0, 1.0 - dist / 22.0);
  return (base * angleFactor).clamp(0.02, 0.95);
}

double _pointSegmentDistance(
    double px, double py, double ax, double ay, double bx, double by) {
  final dx = bx - ax, dy = by - ay;
  final segLen2 = dx * dx + dy * dy;
  if (segLen2 == 0) return math.sqrt(math.pow(px - ax, 2) + math.pow(py - ay, 2));
  var t = ((px - ax) * dx + (py - ay) * dy) / segLen2;
  t = t.clamp(0.0, 1.0);
  final cx = ax + t * dx, cy = ay + t * dy;
  return math.sqrt(math.pow(px - cx, 2) + math.pow(py - cy, 2));
}

/// A passz sikeresélye (0..1): távolság + a vonalban álló ellenfelek alapján.
double passCompletion(PlayerPosition holder, PlayerPosition target, Frame frame,
    {double laneWidthM = 1.5}) {
  final dist = math.sqrt(math.pow(holder.x - target.x, 2) + math.pow(holder.y - target.y, 2));
  final base = math.max(0.1, 1.0 - dist / 35.0);
  int laneDef = 0;
  for (final p in frame.players) {
    if (p.team == holder.team) continue;
    final d = _pointSegmentDistance(p.x, p.y, holder.x, holder.y, target.x, target.y);
    if (d <= laneWidthM) laneDef++;
  }
  return (base - 0.3 * laneDef).clamp(0.05, 0.99);
}

/// Egy döntési opció: lövés vagy passz egy csapattárshoz, értékkel.
class Option {
  final String kind; // "shoot" | "pass"
  final int? targetId;
  final double value;
  Option(this.kind, this.targetId, this.value);
}

/// A labdát épp birtokló játékos (a labdához legközelebbi, sugáron belül).
PlayerPosition? ballHolder(Frame frame, TacticsConfig config) {
  final ball = frame.ball;
  if (ball == null || frame.players.isEmpty) return null;
  PlayerPosition? nearest;
  double bestD = double.infinity;
  for (final p in frame.players) {
    final d = math.sqrt(math.pow(p.x - ball.x, 2) + math.pow(p.y - ball.y, 2));
    if (d < bestD) {
      bestD = d;
      nearest = p;
    }
  }
  if (nearest == null || bestD > config.possessionRadiusM) return null;
  return nearest;
}

/// A labdás játékos összes opciója: lövés + passz minden csapattárshoz.
List<Option> evaluateOptions(Frame frame, PlayerPosition holder, TacticsConfig config) {
  final goalX = config.attacksTowardX(holder.team);
  final options = <Option>[Option("shoot", null, shotValue(holder.x, holder.y, goalX))];
  for (final p in frame.players) {
    if (p.team != holder.team || p.trackId == holder.trackId) continue;
    final sv = shotValue(p.x, p.y, goalX);
    final comp = passCompletion(holder, p, frame);
    options.add(Option("pass", p.trackId, sv * comp));
  }
  return options;
}

Option? bestOption(List<Option> options) {
  if (options.isEmpty) return null;
  return options.reduce((a, b) => a.value >= b.value ? a : b);
}

/// Egy felismert passz a döntés kontextusával.
class PassEvent {
  final int passerId;
  final int receiverId;
  final Frame decisionFrame;
  final PlayerPosition passerPos;
  PassEvent(this.passerId, this.receiverId, this.decisionFrame, this.passerPos);
}

/// Passzok felismerése: a labdabirtokos csapaton belüli váltása egy passz.
List<PassEvent> detectPasses(Match match, TacticsConfig config) {
  final passes = <PassEvent>[];
  PlayerPosition? prevHolder;
  Frame? prevFrame;
  for (final f in match.frames) {
    final holder = ballHolder(f, config);
    if (holder != null && prevHolder != null && prevFrame != null) {
      if (holder.team == prevHolder.team && holder.trackId != prevHolder.trackId) {
        passes.add(PassEvent(prevHolder.trackId, holder.trackId, prevFrame, prevHolder));
      }
    }
    if (holder != null) {
      prevHolder = holder;
      prevFrame = f;
    }
  }
  return passes;
}

/// Egy játékos döntéseinek összegzése.
class DecisionReport {
  final int playerId;
  final int passes;
  final Map<int, int> passDistribution; // fogadó id -> hány passz
  final double optimalRate;
  final double avgValueGap;
  DecisionReport(this.playerId, this.passes, this.passDistribution, this.optimalRate, this.avgValueGap);
}

DecisionReport analyzePlayerDecisions(Match match, int playerId,
    {TacticsConfig config = const TacticsConfig()}) {
  final passes = detectPasses(match, config).where((pe) => pe.passerId == playerId).toList();
  final dist = <int, int>{};
  int optimal = 0;
  final gaps = <double>[];

  for (final pe in passes) {
    dist[pe.receiverId] = (dist[pe.receiverId] ?? 0) + 1;
    final options = evaluateOptions(pe.decisionFrame, pe.passerPos, config);
    final best = bestOption(options);
    Option? actual;
    for (final o in options) {
      if (o.kind == "pass" && o.targetId == pe.receiverId) {
        actual = o;
        break;
      }
    }
    if (best != null && actual != null) {
      gaps.add(best.value - actual.value);
      if ((best.value - actual.value).abs() < 1e-9) optimal++;
    }
  }

  final n = passes.length;
  return DecisionReport(
    playerId,
    n,
    dist,
    n == 0 ? 0.0 : optimal / n,
    gaps.isEmpty ? 0.0 : gaps.reduce((a, b) => a + b) / gaps.length,
  );
}

/// Azoknak a játékosoknak az id-ja, akik passzoltak (a választóhoz).
List<int> passingPlayerIds(Match match, {TacticsConfig config = const TacticsConfig()}) {
  final ids = <int>{};
  for (final pe in detectPasses(match, config)) {
    ids.add(pe.passerId);
  }
  final list = ids.toList()..sort();
  return list;
}
