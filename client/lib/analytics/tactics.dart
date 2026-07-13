/// Kliensoldali taktika — az AKTUÁLIS frame fázisa, birtoklása és a védekezési
/// forma (a backend tactics.py tükre, a minimumra szűkítve a élő felirathoz).
///
/// Így a lejátszás közben a kliens helyben tud élő taktikai feliratot mutatni,
/// backend nélkül is. Az átfogó összegzést (tempó, megoszlás) a backend /tactics
/// végpontja adja.
library;

import "dart:math" as math;

import "../models/tracking.dart";
import "../ui/court_geometry.dart";

/// A taktikai értelmezés beállításai (a backend TacticsConfig tükre).
class TacticsConfig {
  final bool homeAttacksPositive; // a hazai a +x (x=40) kapu felé támad-e
  final double possessionRadiusM;
  const TacticsConfig({this.homeAttacksPositive = true, this.possessionRadiusM = 3.0});

  /// Az adott csapat SAJÁT kapujának x-e (amit véd).
  double ownGoalX(Team team) {
    if (team == Team.home) return homeAttacksPositive ? 0.0 : courtLength;
    return homeAttacksPositive ? courtLength : 0.0;
  }

  /// Az a kapu-x, amely felé a csapat TÁMAD.
  double attacksTowardX(Team team) => courtLength - ownGoalX(team);
}

/// A játék pillanatnyi fázisa (a backend Phase tükre).
enum Phase { homeAttack, awayAttack, transition, unknown }

/// A labdát birtokló csapat (a labdához legközelebbi, sugáron belüli játékos).
Team? possessionTeam(Frame frame, TacticsConfig config) {
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
  return nearest.team;
}

/// Az aktuális frame fázisa a birtoklásból és a labda térfél-helyzetéből.
Phase classifyPhase(Frame frame, TacticsConfig config) {
  final ball = frame.ball;
  if (ball == null) return Phase.unknown;
  final poss = possessionTeam(frame, config);
  if (poss == null) return Phase.transition;
  final mid = courtLength / 2.0;
  final attacksPositive = config.attacksTowardX(poss) > mid;
  final inAttackingHalf = attacksPositive ? ball.x > mid : ball.x < mid;
  if (!inAttackingHalf) return Phase.transition;
  return poss == Team.home ? Phase.homeAttack : Phase.awayAttack;
}

/// A védekező csapat formája az AKTUÁLIS frame-en (a backend detect_formation tükre).
/// Visszaadja a címkét (pl. "6-0", "5-1", "3-2-1") vagy a sávok leírását.
String detectFormation(Frame frame, Team defendingTeam, TacticsConfig config) {
  const backMax = 7.0, midMax = 10.5, gkMax = 2.0;
  final goalX = config.ownGoalX(defendingTeam);
  int back = 0, mid = 0, high = 0;
  for (final p in frame.players) {
    if (p.team != defendingTeam) continue;
    final depth = (p.x - goalX).abs();
    if (depth <= gkMax) continue; // kapus
    if (depth <= backMax) {
      back++;
    } else if (depth <= midMax) {
      mid++;
    } else {
      high++;
    }
  }
  final advanced = mid + high;
  final total = back + mid + high;
  if (total == 6) {
    if (advanced == 0) return "6-0";
    if (advanced == 1) return "5-1";
    if (mid == 2 && high == 0) return "4-2";
    if (back == 3 && mid == 2 && high == 1) return "3-2-1";
    if (back == 3 && advanced == 3) return "3-3";
  }
  return "$back-$mid-$high";
}

/// Emberi olvasatú, magyar felirat az aktuális frame taktikai állapotáról.
String phaseLabelHu(Phase phase) {
  switch (phase) {
    case Phase.homeAttack:
      return "Hazai támadás";
    case Phase.awayAttack:
      return "Vendég támadás";
    case Phase.transition:
      return "Átmenet";
    case Phase.unknown:
      return "—";
  }
}

/// Egy idő-ablak védekezési képe: melyik csapat milyen formában védekezett
/// (null, ha az ablakban a csapat nem védekezett érdemben).
class FormationWindow {
  final int startFrame;
  final String? homeDefense;
  final String? awayDefense;
  const FormationWindow(this.startFrame, this.homeDefense, this.awayDefense);
}

/// Védekezés-idővonal: a meccset idő-ablakokra bontva csapatonként a
/// LEGGYAKORIBB védekezési forma — ebből látszik, MIKOR váltott az ellenfél
/// (pl. 6-0-ról 5-1-re a második félidőben). Ablakonként többségi címke;
/// kevés védekező kockánál (zaj) az ablak üres marad.
List<FormationWindow> computeFormationTimeline(Match match,
    {double windowS = 15.0, TacticsConfig config = const TacticsConfig()}) {
  final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
  final total = match.frames.length;
  if (total < 2) return const [];
  final winFrames = (windowS * fps).round().clamp(1, total);
  final nWin = (total / winFrames).ceil();
  // ablak × csapat → {forma: darab}
  final counts = List.generate(nWin, (_) => [<String, int>{}, <String, int>{}]);

  for (final f in match.frames) {
    final phase = classifyPhase(f, config);
    // A VÉDEKEZŐ csapat formáját számoljuk: hazai támadásnál a vendégét.
    final (defender, slot) = switch (phase) {
      Phase.homeAttack => (Team.away, 1),
      Phase.awayAttack => (Team.home, 0),
      _ => (null, -1),
    };
    if (defender == null) continue;
    final w = (f.t ~/ winFrames).clamp(0, nWin - 1);
    final label = detectFormation(f, defender, config);
    final bucket = counts[w][slot];
    bucket[label] = (bucket[label] ?? 0) + 1;
  }

  String? majority(Map<String, int> bucket) {
    // Legalább ~1 mp-nyi védekező kocka kell, hogy az ablak címkét kapjon.
    var total = 0;
    bucket.forEach((_, v) => total += v);
    if (total < fps) return null;
    String? best;
    var bestN = 0;
    bucket.forEach((k, v) {
      if (v > bestN) {
        best = k;
        bestN = v;
      }
    });
    return best;
  }

  return [
    for (var w = 0; w < nWin; w++)
      FormationWindow(
          w * winFrames, majority(counts[w][0]), majority(counts[w][1]))
  ];
}
