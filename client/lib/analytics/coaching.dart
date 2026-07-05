/// Kliensoldali élő edzői javaslatok — a backend coaching.py tükre.
///
/// A lejátszás közben (Élő követés) a kliens HELYBEN számol javaslatokat az
/// aktuális frame-re, backend nélkül is: védekezési forma kihasználása,
/// ember-előny/hátrány, szabad csapattárs, gyors indítás. A backend /coaching
/// végpont az "igazság forrása" és a tesztelt hely; ez a smooth élő folyamhoz kell.
library;

import "dart:math" as math;

import "../models/tracking.dart";
import "../ui/court_geometry.dart";
import "tactics.dart";

// A kapushoz ilyen közel lévőt NEM mezőnyjátékosnak veszünk (létszámhoz).
const double _gkMax = 2.0;
// Ekkora távolságon túl a legközelebbi védőtől egy támadó "szabad".
const double _openRadiusM = 3.5;
// A labda ekkora (támadó irányú) sebessége (m/s) felett "gyors indítás".
const double _fastbreakMs = 6.0;

/// Egy edzői javaslat: prioritás (1..5, nagyobb = sürgősebb), kategória, szöveg.
class Suggestion {
  final int priority;
  final String category;
  final String text;
  const Suggestion(this.priority, this.category, this.text);
}

List<PlayerPosition> _fieldPlayers(Frame frame, Team team, TacticsConfig config) {
  final goalX = config.ownGoalX(team);
  return [
    for (final p in frame.players)
      if (p.team == team && (p.x - goalX).abs() > _gkMax) p,
  ];
}

String _sideLabel(double y) {
  if (y < courtWidth * 0.33) return "bal oldalon";
  if (y > courtWidth * 0.66) return "jobb oldalon";
  return "középen";
}

Suggestion _formationSuggestion(String label) {
  const table = {
    "6-0": "Mély 6-0 fal — keresd a beúszót és a 9 m-es lövést; csald ki a védőt.",
    "5-1": "5-1 — az előretolt védő mögötti tér a kulcs; gyors lefordulás, kétszemélyes fal.",
    "4-2": "4-2 — a két előretolt közti középső rés a cél; beálló-játék.",
    "3-2-1": "3-2-1 — terheld a beállót és a szélső réseket; mozgasd a magas védőt.",
    "3-3": "3-3 — széles járatás, a hátsó és első lépcső közti tér kihasználható.",
  };
  final text = table[label];
  if (text == null) {
    return Suggestion(2, "forma", "Védőforma: $label — keresd a legüresebb sávot.");
  }
  return Suggestion(3, "forma", text);
}

double _ballSpeedTowardAttack(
    Frame frame, Frame? prev, Team attacking, TacticsConfig config, double fps) {
  if (prev == null || frame.ball == null || prev.ball == null) return 0.0;
  final targetX = config.attacksTowardX(attacking);
  final sign = targetX > courtLength / 2.0 ? 1.0 : -1.0;
  final dx = (frame.ball!.x - prev.ball!.x) * sign;
  return dx * fps;
}

/// Az adott frame edzői javaslatai a BIRTOKLÓ (támadó) csapat szemszögéből,
/// prioritás szerint csökkenő sorrendben.
List<Suggestion> suggestForFrame(Frame frame,
    {TacticsConfig config = const TacticsConfig(), Frame? prevFrame, double fps = 25.0}) {
  final out = <Suggestion>[];

  final ball = frame.ball;
  if (ball == null) {
    return const [Suggestion(1, "altalanos", "Nincs labda a képen — kövesd a felépítést.")];
  }
  final poss = possessionTeam(frame, config);
  if (poss == null) {
    return const [Suggestion(4, "tempo", "Szabad labda — harcolj érte, vagy zárj vissza gyorsan!")];
  }

  final attacking = poss;
  final defending = attacking == Team.home ? Team.away : Team.home;

  // 1) Ember-előny/hátrány.
  final attN = _fieldPlayers(frame, attacking, config).length;
  final defN = _fieldPlayers(frame, defending, config).length;
  final diff = attN - defN;
  if (diff >= 1) {
    out.add(Suggestion(5, "emberelony", "Emberelőny (+$diff) — gyors oldalváltás, használd ki!"));
  } else if (diff <= -1) {
    out.add(Suggestion(4, "emberhatrany", "Emberhátrány ($diff) — húzd az időt, biztos passzok."));
  }

  // 2) Gyors indítás / lefutás.
  final speed = _ballSpeedTowardAttack(frame, prevFrame, attacking, config, fps);
  if (speed >= _fastbreakMs) {
    out.add(const Suggestion(5, "tempo", "Gyors indítás — lefutás lehetséges, indíts előre!"));
  }

  // 3) Szabad csapattárs a támadó térfélen — a legüresebbet ajánljuk.
  PlayerPosition carrier = frame.players.first;
  double bestCarrier = double.infinity;
  for (final p in frame.players) {
    final d = math.sqrt(math.pow(p.x - ball.x, 2) + math.pow(p.y - ball.y, 2));
    if (d < bestCarrier) {
      bestCarrier = d;
      carrier = p;
    }
  }
  final targetX = config.attacksTowardX(attacking);
  final attackPositive = targetX > courtLength / 2.0;
  PlayerPosition? openPlayer;
  double openDist = 0.0;
  for (final p in frame.players) {
    if (p.team != attacking || identical(p, carrier)) continue;
    final onAttackingHalf = attackPositive ? p.x > courtLength / 2.0 : p.x < courtLength / 2.0;
    if (!onAttackingHalf) continue;
    double nearestDef = double.infinity;
    for (final d in frame.players) {
      if (d.team != defending) continue;
      final dist = math.sqrt(math.pow(p.x - d.x, 2) + math.pow(p.y - d.y, 2));
      if (dist < nearestDef) nearestDef = dist;
    }
    if (nearestDef >= _openRadiusM && nearestDef > openDist) {
      openDist = nearestDef;
      openPlayer = p;
    }
  }
  if (openPlayer != null) {
    out.add(Suggestion(4, "szabad", "Szabad ember ${_sideLabel(openPlayer.y)} — passzold neki!"));
  }

  // 4) Védekezési forma szerinti alap-irány (mindig ad egyet).
  out.add(_formationSuggestion(detectFormation(frame, defending, config)));

  out.sort((a, b) => b.priority.compareTo(a.priority));
  return out;
}
