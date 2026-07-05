/// Kliensoldali MECCS-ÖSSZEGZŐ — csapatstílus egy nézetben.
///
/// A backend tactics.py / setplays.py összegzéseinek Dart-tükre, a kliensen
/// kiszámolva, hogy a "meccs-összegző" panel BACKEND NÉLKÜL, demóval is működjön.
/// Tartalom: fázis-megoszlás, csapatonkénti védekezési forma, tempó-metrikák,
/// és a visszatérő figurák száma.
library;

import "dart:math" as math;

import "../models/tracking.dart";
import "../ui/court_geometry.dart";
import "tactics.dart";

class MatchSummary {
  final Map<Phase, double> phasePercentages; // fázisonként %
  final String homeFormation;                // a hazai leggyakoribb védekezési formája
  final String awayFormation;                // a vendég leggyakoribb védekezési formája
  final int possessions;                     // birtoklás-szakaszok száma
  final double transitionPct;                // átmenet aránya (%)
  final double avgBallSpeedMs;               // labda átlagsebessége (m/s)
  final double avgAttackDurationS;           // átlagos támadás-hossz (mp)
  final int attacks;                         // felismert támadás-szakaszok
  final int numFigures;                      // visszatérő figurák száma

  MatchSummary({
    required this.phasePercentages,
    required this.homeFormation,
    required this.awayFormation,
    required this.possessions,
    required this.transitionPct,
    required this.avgBallSpeedMs,
    required this.avgAttackDurationS,
    required this.attacks,
    required this.numFigures,
  });
}

MatchSummary computeMatchSummary(Match match, {TacticsConfig config = const TacticsConfig()}) {
  final phases = [for (final f in match.frames) classifyPhase(f, config)];

  // Fázis-megoszlás (%).
  final counts = {for (final p in Phase.values) p: 0};
  for (final ph in phases) {
    counts[ph] = counts[ph]! + 1;
  }
  final n = phases.isEmpty ? 1 : phases.length;
  final pct = {for (final p in Phase.values) p: 100.0 * counts[p]! / n};

  return MatchSummary(
    phasePercentages: pct,
    homeFormation: _mostCommonFormation(match, Team.home, config),
    awayFormation: _mostCommonFormation(match, Team.away, config),
    possessions: _countPossessions(match, config),
    transitionPct: pct[Phase.transition]!,
    avgBallSpeedMs: _avgBallSpeed(match),
    avgAttackDurationS: _avgAttackDuration(match, config, phases),
    attacks: _segmentAttacks(match, config).length,
    numFigures: _discoverFigures(match, config),
  );
}

// A védekező csapat leggyakoribb formája (amikor az ellenfél támad).
String _mostCommonFormation(Match match, Team team, TacticsConfig cfg) {
  final tally = <String, int>{};
  for (final f in match.frames) {
    final ph = classifyPhase(f, cfg);
    final defending = ph == Phase.homeAttack
        ? Team.away
        : ph == Phase.awayAttack
            ? Team.home
            : null;
    if (defending != team) continue;
    final label = detectFormation(f, team, cfg);
    tally[label] = (tally[label] ?? 0) + 1;
  }
  if (tally.isEmpty) return "—";
  return tally.entries.reduce((a, b) => a.value >= b.value ? a : b).key;
}

int _countPossessions(Match match, TacticsConfig cfg) {
  Team? prev;
  int count = 0;
  for (final f in match.frames) {
    final poss = possessionTeam(f, cfg);
    if (poss != null && poss != prev) {
      count++;
      prev = poss;
    }
  }
  return count;
}

double _avgBallSpeed(Match match) {
  final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
  double dist = 0;
  int steps = 0;
  Ball? prev;
  for (final f in match.frames) {
    final b = f.ball;
    if (b != null && prev != null) {
      dist += math.sqrt(math.pow(b.x - prev.x, 2) + math.pow(b.y - prev.y, 2));
      steps++;
    }
    prev = b;
  }
  return steps == 0 ? 0.0 : dist / (steps / fps);
}

double _avgAttackDuration(Match match, TacticsConfig cfg, List<Phase> phases) {
  final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
  final runs = <int>[];
  int current = 0;
  Phase? curPhase;
  for (final ph in phases) {
    final isAttack = ph == Phase.homeAttack || ph == Phase.awayAttack;
    if (isAttack) {
      if (ph == curPhase) {
        current++;
      } else {
        if (current > 0) runs.add(current);
        current = 1;
        curPhase = ph;
      }
    } else {
      if (current > 0) runs.add(current);
      current = 0;
      curPhase = null;
    }
  }
  if (current > 0) runs.add(current);
  if (runs.isEmpty) return 0.0;
  return (runs.reduce((a, b) => a + b) / runs.length) / fps;
}

// --- Figura-felismerés (a backend setplays.py tükre, a minimumra szűkítve) ---

List<List<Frame>> _segmentAttacks(Match match, TacticsConfig cfg, {int minLength = 5}) {
  final sequences = <List<Frame>>[];
  List<Frame>? current;
  Team? curTeam;
  void close() {
    if (current != null && current!.length >= minLength) sequences.add(current!);
    current = null;
    curTeam = null;
  }

  for (final f in match.frames) {
    final ph = classifyPhase(f, cfg);
    final team = ph == Phase.homeAttack
        ? Team.home
        : ph == Phase.awayAttack
            ? Team.away
            : null;
    if (team == null) {
      close();
      continue;
    }
    if (current == null || curTeam != team) {
      close();
      current = [f];
      curTeam = team;
    } else {
      current!.add(f);
    }
  }
  close();
  return sequences;
}

List<double> _signature(List<Frame> seq, Team team, {int binsX = 6, int binsY = 3}) {
  final grid = List<double>.filled(binsX * binsY, 0.0);
  double total = 0;
  for (final f in seq) {
    for (final p in f.players) {
      if (p.team != team) continue;
      final ix = (p.x / courtLength * binsX).floor().clamp(0, binsX - 1);
      final iy = (p.y / courtWidth * binsY).floor().clamp(0, binsY - 1);
      grid[iy * binsX + ix] += 1;
      total += 1;
    }
  }
  if (total > 0) {
    for (int i = 0; i < grid.length; i++) {
      grid[i] /= total;
    }
  }
  return grid;
}

int _discoverFigures(Match match, TacticsConfig cfg, {double threshold = 0.15}) {
  final seqs = _segmentAttacks(match, cfg);
  if (seqs.isEmpty) return 0;
  final centroids = <List<double>>[];
  final counts = <int>[];
  for (final seq in seqs) {
    // a támadó csapatot az első frame fázisából tudjuk
    final ph = classifyPhase(seq.first, cfg);
    final team = ph == Phase.homeAttack ? Team.home : Team.away;
    final sig = _signature(seq, team);
    int best = -1;
    double bestD = double.infinity;
    for (int i = 0; i < centroids.length; i++) {
      double d = 0;
      for (int k = 0; k < sig.length; k++) {
        d += math.pow(sig[k] - centroids[i][k], 2).toDouble();
      }
      d = math.sqrt(d);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    if (best >= 0 && bestD <= threshold) {
      final c = centroids[best];
      final cnt = counts[best];
      for (int k = 0; k < c.length; k++) {
        c[k] = (c[k] * cnt + sig[k]) / (cnt + 1);
      }
      counts[best] = cnt + 1;
    } else {
      centroids.add(List<double>.from(sig));
      counts.add(1);
    }
  }
  return centroids.length;
}
