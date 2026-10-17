/// Kliensoldali figura-szimuláció — a backend play_simulation.py Dart-tükre.
///
/// Megtanulja egy csapat védekezési stílusát, lejátssza az edző figuráját a
/// tanult védelem ellen (Tracking kimenet), és pontozza a teremtett lövőhelyzetet.
/// Kliensoldalon, így backend nélkül (a betöltött/demó meccsből tanulva) is megy.
library;

import "dart:math" as math;
import "dart:ui";

import "../models/tracking.dart";
import "../ui/court_geometry.dart";
import "decisions.dart" show shotValue;
import "tactics.dart";

/// A fal védekezési rendszerei — a backend
/// play_simulation.VEDEKEZESI_RENDSZEREK párja (őr-teszt ellenőrzi):
/// rendszerenként az előretolt védők [mélység m a saját kaputól, y-eltolás
/// a középtől, labdakövetés]; a többi védő a hatos előtti vonalban.
const Map<String, List<List<double>>> defenseSystems = {
  "6-0": [],
  "5-1": [[9.5, 0.0, 0.8]],
  "4-2": [[9.0, -3.5, 0.6], [9.0, 3.5, 0.6]],
  "3-2-1": [[8.5, -4.5, 0.6], [8.5, 4.5, 0.6], [11.0, 0.0, 0.8]],
  "3-3": [[9.0, -5.5, 0.6], [9.5, 0.0, 0.7], [9.0, 5.5, 0.6]],
};

/// Az előretolt védő legalább ennyivel a vonal előtt áll (a backend
/// ELORETOLT_MIN_ELONY_M-je).
const double advancedMinLeadM = 1.5;

/// Egy csapat tanult védekezési stílusa.
class DefenseModel {
  final int numDefenders;
  final double lineDepthM;  // a védővonal mélysége a saját kaputól
  final double lateralGain; // mennyire követi a labda y-helyzetét
  final String rendszer;    // védekezési rendszer (defenseSystems kulcsa)

  const DefenseModel(
      {this.numDefenders = 6,
      this.lineDepthM = 6.0,
      this.lateralGain = 0.5,
      this.rendszer = "6-0"});

  /// A fal a hatos ívét követi KÍVÜLRŐL (6-0 fal): egy védő sem léphet a
  /// kapuelőtérbe — a lineDepthM a frontális mélység (alap: fél méterrel a
  /// hatos előtt), a széleken a fal az ívre simul. A rendszer előretolt
  /// védői a vonal előtt (a vonal után a listában). A backend
  /// play_simulation.py respond-jával azonos geometria.
  List<Offset> respond(double ballY, double goalX) {
    const margin = 0.5; // ennyivel a hatos íve előtt áll a fal alapból
    final sign = goalX == courtLength ? -1.0 : 1.0;
    final nOsszes = math.max(1, numDefenders);
    final elol = (defenseSystems[rendszer] ?? const <List<double>>[])
        .take(nOsszes - 1)
        .toList();
    final n = nOsszes - elol.length;
    final baseYs = <double>[];
    if (n == 1) {
      baseYs.add(courtWidth / 2);
    } else {
      const lo = 3.0;
      final hi = courtWidth - 3.0;
      for (int i = 0; i < n; i++) {
        baseYs.add(lo + (hi - lo) * i / (n - 1));
      }
    }
    final shift = lateralGain * (ballY - courtWidth / 2);
    final offset = math.max(margin, lineDepthM - goalAreaRadius + margin);
    final out = <Offset>[];
    for (final by in baseYs) {
      final y = (by + shift).clamp(1.0, courtWidth - 1.0).toDouble();
      // A hatos határa ennél az y-nál: a közelebbi kapufától 6 m.
      final lateral =
          math.max(0.0, (y - courtWidth / 2).abs() - goalWidth / 2);
      final boundary = lateral < goalAreaRadius
          ? math.sqrt(goalAreaRadius * goalAreaRadius - lateral * lateral)
          : 0.0;
      out.add(Offset(goalX + sign * (boundary + offset), y));
    }
    // Az előretoltak: a rendszer mélységén (a kitolt vonal előtt legalább
    // advancedMinLeadM-rel), a labda felé lépve.
    final eleje = goalAreaRadius + offset;
    for (final e in elol) {
      final y = (courtWidth / 2 + e[1] + e[2] * (ballY - courtWidth / 2))
          .clamp(1.0, courtWidth - 1.0)
          .toDouble();
      out.add(Offset(goalX + sign * math.max(e[0], eleje + advancedMinLeadM), y));
    }
    return out;
  }
}

/// Védekezési stílus tanulása egy meccsből (a defending csapat védőfázisaiból).
DefenseModel learnDefense(Match match, Team team,
    {TacticsConfig config = const TacticsConfig()}) {
  // (a backend DefenseModel.learn tükre: a leggyakoribb ismert rendszer —
  // holtversenyben a nagyobb címke —, nem 6-0-nál a vonal mélysége a
  // hátsó sorból, a 7 m-es sávhatárig)
  const hatsoMax = formationBackMaxM;
  final goalX = config.ownGoalX(team);
  final depths = <double>[];
  final hatso = <double>[];
  final formak = <String, int>{};
  final counts = <int>[];
  for (final f in match.frames) {
    final ph = classifyPhase(f, config);
    final defends = (team == Team.away && ph == Phase.homeAttack) ||
        (team == Team.home && ph == Phase.awayAttack);
    if (!defends) continue;
    final outfield = f.players.where((p) => p.team == team && (p.x - goalX).abs() > 2.0).toList();
    if (outfield.isNotEmpty) {
      counts.add(outfield.length);
      depths.addAll(outfield.map((p) => (p.x - goalX).abs()));
      hatso.addAll(outfield
          .map((p) => (p.x - goalX).abs())
          .where((d) => d <= hatsoMax));
      final cimke = detectFormation(f, team, config);
      if (defenseSystems.containsKey(cimke)) {
        formak[cimke] = (formak[cimke] ?? 0) + 1;
      }
    }
  }
  double mean(List<double> v) => v.isEmpty ? 0 : v.reduce((a, b) => a + b) / v.length;
  var rendszer = "6-0";
  var legtobb = -1;
  for (final e in formak.entries) {
    if (e.value > legtobb || (e.value == legtobb && e.key.compareTo(rendszer) > 0)) {
      rendszer = e.key;
      legtobb = e.value;
    }
  }
  return DefenseModel(
    numDefenders: counts.isEmpty ? 6 : (counts.reduce((a, b) => a + b) / counts.length).round(),
    lineDepthM: rendszer != "6-0" && hatso.isNotEmpty
        ? mean(hatso)
        : (depths.isEmpty ? 6.0 : mean(depths)),
    rendszer: rendszer,
  );
}

/// Az edző figurája: támadók útvonala lépésenként + ki birtokolja a labdát.
class SetPlay {
  final List<List<Offset>> attackers; // [támadó][lépés] = (x,y) méter
  final List<int> ballCarrier;        // lépésenként a labdás támadó indexe
  const SetPlay(this.attackers, this.ballCarrier);
  int get steps => ballCarrier.length;
}

/// Lejátssza a figurát a tanult védelem ellen → Match (Tracking).
Match simulateSetPlay(SetPlay setplay, DefenseModel defense,
    {TacticsConfig config = const TacticsConfig(), double fps = 25.0}) {
  final awayGoalX = config.ownGoalX(Team.away);
  final meta = MatchMeta(
    matchId: "setplay-sim", homeTeam: "Terv (támadó)", awayTeam: "Tanult védelem",
    fps: fps, frameWidth: 1920, frameHeight: 1080,
  );
  final frames = <Frame>[];
  for (int step = 0; step < setplay.steps; step++) {
    final players = <PlayerPosition>[];
    for (int ai = 0; ai < setplay.attackers.length; ai++) {
      final pt = setplay.attackers[ai][step];
      players.add(PlayerPosition(
        trackId: ai + 1, team: Team.home, x: pt.dx, y: pt.dy,
        source: PositionSource.measured, confidence: 1.0, jerseyNumber: ai + 1,
      ));
    }
    final carrier = setplay.ballCarrier[step];
    final bp = setplay.attackers[carrier][step];
    final ball = Ball(x: bp.dx, y: bp.dy, confidence: 1.0);
    final defs = defense.respond(bp.dy, awayGoalX);
    for (int di = 0; di < defs.length; di++) {
      players.add(PlayerPosition(
        trackId: 100 + di, team: Team.away, x: defs[di].dx, y: defs[di].dy,
        source: PositionSource.measured, confidence: 1.0,
      ));
    }
    frames.add(Frame(t: step, players: players, ball: ball));
  }
  return Match(meta: meta, frames: frames);
}

/// A szimulált figura kiértékelése: a teremtett legjobb lövőhelyzet.
class SetPlayEvaluation {
  final double bestShotValue;
  final int step;
  final int? attackerId;
  const SetPlayEvaluation(this.bestShotValue, this.step, this.attackerId);
}

SetPlayEvaluation evaluateSetPlay(Match match, {TacticsConfig config = const TacticsConfig()}) {
  final goalX = config.attacksTowardX(Team.home);
  double best = 0.0;
  int bestStep = -1;
  int? bestAtk;
  for (final f in match.frames) {
    final attackers = f.players.where((p) => p.team == Team.home);
    final defenders = f.players.where((p) => p.team == Team.away).toList();
    for (final a in attackers) {
      final sv = shotValue(a.x, a.y, goalX);
      double nd = 99.0;
      for (final d in defenders) {
        final dd = math.sqrt(math.pow(a.x - d.x, 2) + math.pow(a.y - d.y, 2));
        if (dd < nd) nd = dd;
      }
      final openness = (nd / 4.0).clamp(0.0, 1.0);
      final score = sv * openness;
      if (score > best) {
        best = score;
        bestStep = f.t;
        bestAtk = a.trackId;
      }
    }
  }
  return SetPlayEvaluation(best, bestStep, bestAtk);
}
