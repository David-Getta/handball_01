/// Pálya-geometria — a szabálykönyvi méretek és a 6 m-es kapuelőtér alakja.
///
/// A felülnézeti rajzhoz méteres koordinátákban dolgozunk (a backend is így ad
/// pozíciókat), és a rajzoló skálázza pixelre. A méretek a docs/RULES.md-ből.
library;

import "dart:math" as math;
import "dart:ui";

const double courtLength = 40.0; // x tengely (hosszú)
const double courtWidth = 20.0; // y tengely (rövid)
const double goalWidth = 3.0; // kapu szélessége → kapufák y=8.5 és y=11.5
const double goalAreaRadius = 6.0; // 6 m-es kapuelőtér sugár
const double freeThrowRadius = 9.0; // 9 m-es (szaggatott) szabaddobási vonal
const double sevenMeterX = 7.0; // a hetes-vonal távolsága a gólvonaltól
const double sevenMeterHalfLen = 0.5; // a hetes-vonal fél hossza (1 m-es vonal)
const double keeperLineX = 4.0; // 4 m-es kapus-vonal a gólvonaltól
const double keeperLineHalfLen = 0.075; // 15 cm-es vonal fele

/// Méter↔képernyő transzformáció — a felülnézeti pálya egységes leképezése.
///
/// Ugyanazt a skálát/eltolást adja, amit a rajzolók használnak, hogy a kirajzolás
/// és az érintés-találat (a figura-tervezőben) pontosan egyezzen.
class CourtTransform {
  final double scale;
  final double originX;
  final double originY;
  const CourtTransform(this.scale, this.originX, this.originY);

  factory CourtTransform.fit(Size size, {double margin = 28}) {
    final usableW = size.width - 2 * margin;
    final usableH = size.height - 2 * margin;
    final scale = math.min(usableW / courtLength, usableH / courtWidth);
    final ox = (size.width - courtLength * scale) / 2;
    final oy = (size.height - courtWidth * scale) / 2;
    return CourtTransform(scale, ox, oy);
  }

  Offset toScreen(double mx, double my) => Offset(originX + mx * scale, originY + my * scale);
  Offset toCourt(double px, double py) => Offset((px - originX) / scale, (py - originY) / scale);
}

/// A kapuelőtér (6 m-es zóna) határoló pontjai MÉTERBEN, az adott oldalra.
///
/// [leftSide] true esetén a bal kapu (x=0), false esetén a jobb (x=40).
/// A határ: alsó negyedkör (a lenti kapufa körül) → 3 m egyenes → felső negyedkör.
/// A köríveket [segments] szakasszal mintavételezzük, hogy sima legyen.
List<Offset> goalAreaBoundary({required bool leftSide, int segments = 16}) =>
    _postArcBoundary(
        radius: goalAreaRadius, leftSide: leftSide, segments: segments);

/// A 9 m-es SZABADDOBÁSI vonal pontjai — ugyanaz az alak, 9 m sugárral.
///
/// A szabálykönyvben ez SZAGGATOTT vonal (a rajzoló így is húzza meg): a
/// szabaddobást innen kell végrehajtani, és a védekező falnak is ez a
/// vonatkoztatási vonala — a felülnézeti képen ettől lesz "igazi" pálya.
List<Offset> freeThrowBoundary({required bool leftSide, int segments = 16}) =>
    _postArcBoundary(
        radius: freeThrowRadius, leftSide: leftSide, segments: segments);

/// A kapufák köré húzott, `radius` sugarú határvonal (a 6 m-es és a 9 m-es
/// vonal alakja azonos, csak a sugár más).
List<Offset> _postArcBoundary({
  required double radius,
  required bool leftSide,
  int segments = 16,
}) {
  final cy = courtWidth / 2.0; // 10 m
  final half = goalWidth / 2.0; // 1.5 m
  final lowerPostY = cy - half; // 8.5
  final upperPostY = cy + half; // 11.5
  final pts = <Offset>[];

  // Alsó negyedkör a lenti kapufa (x=0, y=8.5) körül.
  for (int i = 0; i <= segments; i++) {
    final theta = (math.pi / 2) * (i / segments); // 0..90°
    final x = radius * math.sin(theta);
    final y = lowerPostY - radius * math.cos(theta);
    pts.add(Offset(x, y));
  }
  // 3 m-es egyenes szakasz a két negyedkör között.
  pts.add(Offset(radius, lowerPostY));
  pts.add(Offset(radius, upperPostY));
  // Felső negyedkör a fenti kapufa (x=0, y=11.5) körül.
  for (int i = 0; i <= segments; i++) {
    final theta = (math.pi / 2) * (i / segments);
    final x = radius * math.cos(theta);
    final y = upperPostY + radius * math.sin(theta);
    pts.add(Offset(x, y));
  }

  // Jobb oldalra tükrözzük (x -> 40 - x).
  if (!leftSide) {
    return pts.map((p) => Offset(courtLength - p.dx, p.dy)).toList();
  }
  return pts;
}

/// A cserevonal jele az oldalvonalon: a félpályától ennyire (méter).
const double substitutionLineX = 4.5;

/// Lövés-mérés egy pálya-pontból — a backend `court3d.shot_geometry`
/// TÜKRE (ugyanazok a képletek; a backend teszt a böngészős tükröt
/// node-dal veti össze, ezt a forrás-őr nézi).
class ShotGeometry {
  final bool leftGoal; // a bal (x=0) kapura mérünk
  final double goalX;
  final double distance; // a kapu közepétől (m)
  final double postDistance; // a kapufák közti szakasztól (m) — 6/9 m mércéje
  final double angleDeg; // a két kapufa között látott szög
  final String zone; // "kapuelőtér" / "6–9 m" / "9 m-en túl"
  const ShotGeometry(this.leftGoal, this.goalX, this.distance,
      this.postDistance, this.angleDeg, this.zone);
}

ShotGeometry shotGeometry(double x, double y, {bool? leftGoal}) {
  final bal = leftGoal ?? x <= courtLength / 2;
  final gx = bal ? 0.0 : courtLength;
  final cy = courtWidth / 2;
  final y1 = cy - goalWidth / 2, y2 = cy + goalWidth / 2;
  final v1x = gx - x, v1y = y1 - y, v2x = gx - x, v2y = y2 - y;
  final n1 = math.sqrt(v1x * v1x + v1y * v1y);
  final n2 = math.sqrt(v2x * v2x + v2y * v2y);
  var szog = 180.0;
  if (n1 >= 1e-9 && n2 >= 1e-9) {
    final c = ((v1x * v2x + v1y * v2y) / (n1 * n2)).clamp(-1.0, 1.0);
    szog = math.acos(c) * 180 / math.pi;
  }
  final ny = y.clamp(y1, y2);
  final kapufa = math.sqrt((x - gx) * (x - gx) + (y - ny) * (y - ny));
  final sav = kapufa < goalAreaRadius
      ? "kapuelőtér"
      : (kapufa < freeThrowRadius ? "6–9 m" : "9 m-en túl");
  final tav = math.sqrt((x - gx) * (x - gx) + (y - cy) * (y - cy));
  return ShotGeometry(bal, gx, tav, kapufa, szog, sav);
}

/// Tankönyvi falak a BAL kapu előtt: (mélység a gólvonaltól, y) — a
/// backend `court3d.FORMATION_TEMPLATES` tükre (a forrás-őr veti össze).
/// A jobb kapura tükrözve: x → 40 − mélység.
const Map<String, List<(double, double)>> formationTemplates = {
  "6-0": [(4.2, 2.6), (6.3, 5.6), (6.7, 8.6), (6.7, 11.4), (6.3, 14.4), (4.2, 17.4)],
  "5-1": [(4.4, 2.8), (6.4, 6.0), (6.8, 10.0), (6.4, 14.0), (4.4, 17.2), (10.0, 10.0)],
  "4-2": [(4.6, 3.4), (6.6, 7.6), (6.6, 12.4), (4.6, 16.6), (9.6, 7.5), (9.6, 12.5)],
  "3-2-1": [(4.4, 3.0), (6.8, 10.0), (4.4, 17.0), (8.6, 6.0), (8.6, 14.0), (11.0, 10.0)],
};

/// A sablon pozíciói a `goalX` kapu előtt, pálya-méterben.
List<Offset> formationPositions(String name, double goalX) {
  final s = formationTemplates[name];
  if (s == null) return const [];
  final jobb = goalX > courtLength / 2;
  return [for (final (d, y) in s) Offset(jobb ? courtLength - d : d, y)];
}

/// Átlagos eltérés a sablontól: mohó párosítás (a legközelebbi pár előbb)
/// — a böngészős nézet `elteres` függvényének tükre.
double? formationDeviation(List<Offset> vedok, List<Offset> pontok) {
  final parok = <(double, int, int)>[];
  for (var i = 0; i < vedok.length; i++) {
    for (var j = 0; j < pontok.length; j++) {
      parok.add(((vedok[i] - pontok[j]).distance, i, j));
    }
  }
  parok.sort((a, b) => a.$1.compareTo(b.$1));
  final vi = <int>{}, pj = <int>{};
  var osszeg = 0.0;
  var db = 0;
  for (final (d, i, j) in parok) {
    if (vi.contains(i) || pj.contains(j)) continue;
    vi.add(i);
    pj.add(j);
    osszeg += d;
    db++;
  }
  return db == 0 ? null : osszeg / db;
}

/// A feltörés sávjának padló-téglalapja a `goalX` kaput védő fal előtt
/// (a backend `court3d.breakpoint_zone_band` tükre): a 9 m-es vonalig,
/// a sáv harmadában; a sáv a VÉDŐ nézőpontjából ("bal szél" / "közép" /
/// "jobb szél") — a 0-s kaput védőnek a nagyobb y a bal keze.
Rect? breakpointZoneBand(String? sav, double goalX) {
  if (sav != "bal szél" && sav != "közép" && sav != "jobb szél") return null;
  final harmad = courtWidth / 3.0;
  final balKapu = goalX < courtLength / 2;
  double y0, y1;
  if (sav == "közép") {
    y0 = harmad;
    y1 = 2 * harmad;
  } else if ((sav == "bal szél") == balKapu) {
    y0 = 2 * harmad;
    y1 = courtWidth;
  } else {
    y0 = 0.0;
    y1 = harmad;
  }
  final x0 = balKapu ? 0.0 : courtLength - freeThrowRadius;
  final x1 = balKapu ? freeThrowRadius : courtLength;
  return Rect.fromLTRB(x0, y0, x1, y1);
}

/// A passzsávok küszöbei (a backend `court3d` és a döntés-elemzés
/// `decisions.pass_completion` tükre).
const double passLaneWidthM = 1.5;
const double passLaneGood = 0.6;
const double passLaneRisky = 0.35;

/// A pillanatnyi labdás birtoklás-sugara (TacticsConfig.possession_radius_m).
const double possessionRadiusM = 3.0;

/// Egy passzsáv: a fogadó helye, a passz-esély, a sávban álló ellenfelek
/// száma és a fokozat ("nyitott" / "kockázatos" / "zárt").
class PassLane {
  final double x, y, p;
  final int blockers;
  final String grade;
  const PassLane(this.x, this.y, this.p, this.blockers, this.grade);
}

String passLaneGrade(double p) => p >= passLaneGood
    ? "nyitott"
    : (p >= passLaneRisky ? "kockázatos" : "zárt");

double _pontSzakasz(
    double px, double py, double ax, double ay, double bx, double by) {
  final dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy;
  if (l2 == 0) return math.sqrt((px - ax) * (px - ax) + (py - ay) * (py - ay));
  final t = (((px - ax) * dx + (py - ay) * dy) / l2).clamp(0.0, 1.0);
  final cx = ax + t * dx, cy = ay + t * dy;
  return math.sqrt((px - cx) * (px - cx) + (py - cy) * (py - cy));
}

/// A labdás passzsávjai (a backend `court3d.pass_lanes` tükre). `players`:
/// (hazai?, x, y); null, ha nincs labda vagy a legközelebbi játékos a
/// birtoklás-sugáron kívül van. Visszatérés: (labdás, sávok).
((bool, double, double), List<PassLane>)? passLanes(
    List<(bool, double, double)> players, Offset? ball) {
  if (ball == null || players.isEmpty) return null;
  (bool, double, double)? h;
  var hd = double.infinity;
  for (final p in players) {
    final d = math.sqrt(
        (p.$2 - ball.dx) * (p.$2 - ball.dx) + (p.$3 - ball.dy) * (p.$3 - ball.dy));
    if (d < hd) {
      hd = d;
      h = p;
    }
  }
  final holder = h!;
  if (hd > possessionRadiusM) return null;
  final lanes = <PassLane>[];
  for (final t in players) {
    if (identical(t, holder) || t.$1 != holder.$1) continue;
    final tav = math.sqrt((holder.$2 - t.$2) * (holder.$2 - t.$2) +
        (holder.$3 - t.$3) * (holder.$3 - t.$3));
    final alap = math.max(0.1, 1 - tav / 35);
    var blokk = 0;
    for (final o in players) {
      if (o.$1 == holder.$1) continue;
      if (_pontSzakasz(o.$2, o.$3, holder.$2, holder.$3, t.$2, t.$3) <=
          passLaneWidthM) {
        blokk++;
      }
    }
    final p = (alap - 0.3 * blokk).clamp(0.05, 0.99).toDouble();
    lanes.add(PassLane(t.$2, t.$3, p, blokk, passLaneGrade(p)));
  }
  return (holder, lanes);
}

/// A pillanat-lapozó (Döntések, Szabad lövők ◀ ▶) közös logikája — a
/// böngészős nézet `lapozCel`-jének tükre. `idok`: a pillanatok ideje
/// (mp, növekvő); `utolso`: az utoljára ugrott pillanat ideje vagy null.
/// A "következő" az utolsó ugrástól számít, amíg annak ablakában
/// (−1,6…+2,5 mp) vagyunk, különben a lejátszófejtől (az első 1,6 mp
/// pillanatai is elérhetők, és nem ragad le az épp nézett pillanaton).
double? lapozCel(List<double> idok, double most, double? utolso, int irany) {
  final benne = utolso != null && most >= utolso - 1.6 && most <= utolso + 2.5;
  final alap = benne ? utolso : most;
  if (irany > 0) {
    for (final s in idok) {
      if (benne ? s > alap + 1e-6 : s >= alap - 1e-6) return s;
    }
    return null;
  }
  for (var i = idok.length - 1; i >= 0; i--) {
    if (benne ? idok[i] < alap - 1e-6 : idok[i] < alap - 0.5) return idok[i];
  }
  return null;
}

/// A fal-rés réteg küszöbei (a backend defense.WALL_GAP_M,
/// WALL_GAP_DEPTH_M és WALL_GAP_MIN_DEFENDERS — teszt veti össze).
const double wallGapM = 3.5;
const double wallGapDepthM = 12.0;
const int wallGapMinDefenders = 4;

/// A védőfal rései EGY kockán: a fal védői (x, y) y szerint, a
/// szomszéd-párok y-rései, a széles (≥ wallGapM) rések jele és a
/// legnagyobb rés indexe (holtversenyben az első).
class WallGaps {
  final List<Offset> wall;
  final List<double> gaps;
  final List<bool> wide;
  final int maxIndex;
  const WallGaps(this.wall, this.gaps, this.wide, this.maxIndex);
  double get maxGap => gaps[maxIndex];
}

/// A védőfal rései (a backend `court3d.wall_gap_segments` tükre — UGYANAZ
/// a kiválogatás, mint a `wall_gaps` rétegben: a csapat mért, kapus
/// nélküli védői a saját kaputól wallGapDepthM-en belül, y szerint,
/// holtversenyben x szerint). `players`: (hazai?, x, y, mért?, kapus?);
/// null, ha a fal nem áll (wallGapMinDefenders alatti védő).
WallGaps? wallGapSegments(List<(bool, double, double, bool, bool)> players,
    bool home, double goalX) {
  final fal = [
    for (final p in players)
      if (p.$1 == home && p.$4 && !p.$5 && (p.$2 - goalX).abs() <= wallGapDepthM)
        (p.$3, p.$2)
  ]..sort((a, b) {
      final c = a.$1.compareTo(b.$1);
      return c != 0 ? c : a.$2.compareTo(b.$2);
    });
  if (fal.length < wallGapMinDefenders) return null;
  final gaps = <double>[], wide = <bool>[];
  var maxI = 0;
  for (var i = 0; i + 1 < fal.length; i++) {
    final g = fal[i + 1].$1 - fal[i].$1;
    gaps.add(g);
    wide.add(g >= wallGapM);
    if (g > gaps[maxI]) maxI = i;
  }
  return WallGaps([for (final p in fal) Offset(p.$2, p.$1)], gaps, wide, maxI);
}

/// A jelenet-lista "ugyanaz a pillanat" tűrése (mp) — a backend
/// court3d.SCENE_SAME_MOMENT_S tükre (őr-teszt): a kapott gól sora
/// elmarad, ha ennyin belül szabad lövő GÓL-sor van.
const double sceneSameMomentS = 0.05;

/// A jelenet-lista egy sora: idő (mp és "p:mm"), fajta ("d" döntés, "sz"
/// szabad lövés, "e" labdavesztés), felirat, és hogy gól lett-e.
class SceneRow {
  final double s;
  final String ido, tipus, szoveg;
  final bool gol;
  const SceneRow(this.s, this.ido, this.tipus, this.szoveg, this.gol);
}

/// A jelenet-lista sorai (a böngészős nézet `jelenetSorok`-jának tükre,
/// UGYANAZOKKAL a feliratokkal): a döntés-, szabad-lövés-,
/// labdavesztés-, lerohanás- és kapott-gól-pillanatok (az API sorai)
/// időrendben; holtversenyben döntés, szabad lövés, labdavesztés,
/// lerohanás, kapott gól. A kapott lerohanás és a kapott gól a VÉDEKEZŐ
/// csapat sora ("kinek a hibája"); a kapott gól sora elmarad, ha ugyanarra
/// a pillanatra szabad lövő GÓL-sor van (az már megnevezi).
List<SceneRow> sceneRows(
    List<Map<String, dynamic>> dontesek,
    List<Map<String, dynamic>> szabadok,
    List<Map<String, dynamic>> eladasok,
    String nevH,
    String nevV,
    [List<Map<String, dynamic>> lerohanasok = const [],
    List<Map<String, dynamic>> kapottGolok = const []]) {
  String sz1(num v) => v.toDouble().toStringAsFixed(1).replaceAll(".", ",");
  String csapat(dynamic side) => side == "home" ? nevH : nevV;
  String ido(double s) {
    final t = math.max(0, s.floor());
    return "${t ~/ 60}:${(t % 60).toString().padLeft(2, "0")}";
  }

  const harmad = {"saját": "saját", "közép": "középső", "támadó": "támadó"};
  final sorok = <SceneRow>[];
  double sOf(Map<String, dynamic> d) => ((d["s"] as num?) ?? 0).toDouble();
  for (final d in dontesek) {
    sorok.add(SceneRow(sOf(d), "", "d",
        "${csapat(d["team"])} — jobb opció is volt: "
            "${d["best_kind"] == "shoot" ? "lövés" : "passz egy szabadabb társhoz"}",
        false));
  }
  for (final d in szabadok) {
    final tav = d["dist"] as num?;
    final gol = d["goal"] == true;
    sorok.add(SceneRow(sOf(d), "", "sz",
        "${csapat(d["defending"])} védekezése — szabad lövő"
            "${tav != null ? " (${sz1(tav)} m)" : ""}${gol ? " · GÓL" : ""}",
        gol));
  }
  for (final d in eladasok) {
    final gol = d["goal_after_s"] != null;
    final mez = d["jersey"];
    final h = harmad[d["zone"]];
    sorok.add(SceneRow(sOf(d), "", "e",
        "${csapat(d["team"])} — labdavesztés${mez != null ? " #$mez" : ""}"
            "${h != null ? " ($h harmad)" : ""}${gol ? " · gól lett belőle" : ""}",
        gol));
  }
  for (final d in lerohanasok) {
    final gol = d["outcome"] == "goal";
    final mez = d["shooter_jersey"];
    final vege = gol
        ? " · GÓL"
        : d["outcome"] == "shot"
            ? " · lövés"
            : " · lövés nélkül";
    sorok.add(SceneRow(sOf(d), "", "k",
        "${csapat(d["defending"])} védekezése — kapott lerohanás: "
            "${csapat(d["team"])}${mez != null ? " #$mez" : ""}$vege",
        gol));
  }
  final szabadGolIdok = [
    for (final d in szabadok) if (d["goal"] == true) sOf(d)
  ];
  for (final d in kapottGolok) {
    final s = sOf(d);
    if (szabadGolIdok.any((s0) => (s - s0).abs() < sceneSameMomentS)) continue;
    final mez = d["shooter_jersey"];
    final tav = d["def_dist"] as num?;
    final mely = d["keeper_depth"] as num?;
    final kapus = mely == null
        ? ""
        : d["keeper_out"] == true
            ? " · kapus kint"
            : " · kapus a vonalon";
    sorok.add(SceneRow(s, "", "kg",
        "${csapat(d["defending"])} védekezése — kapott gól: "
            "${csapat(d["team"])}${mez != null ? " #$mez" : ""} (${d["zone"]})"
            "${tav != null ? " · védő ${sz1(tav)} m" : ""}$kapus",
        true));
  }
  const rend = {"d": 0, "sz": 1, "e": 2, "k": 3, "kg": 4};
  sorok.sort((a, b) {
    final c = a.s.compareTo(b.s);
    return c != 0 ? c : rend[a.tipus]!.compareTo(rend[b.tipus]!);
  });
  return [
    for (final r in sorok) SceneRow(r.s, ido(r.s), r.tipus, r.szoveg, r.gol)
  ];
}

/// A lerohanás felirata (a böngészős nézet `kontraFelirat`-jának tükre,
/// UGYANAZZAL a szöveggel): "Lerohanás (Szeged): #7 fejezi be · második
/// hullám · elszökött emberrel · 4,2 mp · GÓL" — a hiányzó részek (lövő,
/// hullám, elszökés) kimaradnak. `k`: a /fast-break-moments egy sora.
String fastBreakCaption(Map<String, dynamic> k, String nevH, String nevV) {
  final csapat = k["team"] == "home" ? nevH : nevV;
  final hossz = ((k["duration_s"] as num?) ?? 0).toDouble();
  final reszek = <String>[
    if (k["shooter_jersey"] != null) "#${k["shooter_jersey"]} fejezi be",
    if (k["wave"] == "first") "első ember",
    if (k["wave"] == "second") "második hullám",
    if (k["ahead"] == true) "elszökött emberrel",
    if (k["ahead"] == false) "együtt felfutva",
    "${hossz.toStringAsFixed(1).replaceAll(".", ",")} mp",
    k["outcome"] == "goal"
        ? "GÓL"
        : k["outcome"] == "shot"
            ? "lövés"
            : "lövés nélkül",
  ];
  return "Lerohanás ($csapat): ${reszek.join(" · ")}";
}

/// A kapott gól felirata (a böngészős nézet `kapottFelirat`-jának tükre,
/// UGYANAZZAL a szöveggel): "Kapott gól (Veszprém): Szeged #10 · 9 m-en
/// túl, kapu-szög 13,8° · védő 6,2 m-re — szabadon · kapus 0,9 m-re a
/// vonalon · xG 0,09". `g`: a /conceded-goals egy sora.
String concededGoalCaption(
    Map<String, dynamic> g, String nevH, String nevV) {
  String sz1(num v) => v.toDouble().toStringAsFixed(1).replaceAll(".", ",");
  final ved = g["defending"] == "home" ? nevH : nevV;
  final tam = g["team"] == "home" ? nevH : nevV;
  final mez = g["shooter_jersey"];
  final tav = g["def_dist"] as num?;
  final mely = g["keeper_depth"] as num?;
  final xg = ((g["xg"] as num?) ?? 0).toDouble();
  final reszek = <String>[
    "$tam${mez != null ? " #$mez" : ""}",
    "${g["zone"]}, kapu-szög ${sz1((g["angle_deg"] as num?) ?? 0)}°",
    tav == null
        ? "védő nem mérhető"
        : "védő ${sz1(tav)} m-re${g["free"] == true ? " — szabadon" : ""}",
    mely == null
        ? "kapus nem mérhető"
        : "kapus ${sz1(mely)} m-re ${g["keeper_out"] == true ? "kint" : "a vonalon"}",
    "xG ${xg.toStringAsFixed(2).replaceAll(".", ",")}",
  ];
  return "Kapott gól ($ved): ${reszek.join(" · ")}";
}

/// A gól-akció felirata (a böngészős nézet `golAkcioFelirat`-jának
/// tükre, UGYANAZZAL a szöveggel): "Szeged gólja — #10 → #9 → #7 → #10
/// lő · 3 passz, 6,5 mp"; hosszú láncnál az első kettő és az utolsó két
/// passzoló marad. `g`: a /goal-build-ups egy sora.
String goalBuildUpCaption(Map<String, dynamic> g, String nevH, String nevV) {
  String m(dynamic j) => j != null ? "#$j" : "?";
  final passzok = ((g["passes"] as List?) ?? const []).cast<Map>();
  var nevek = [for (final p in passzok) m(p["from_jersey"])];
  if (nevek.length > 4) {
    nevek = [...nevek.take(2), "…", ...nevek.skip(nevek.length - 2)];
  }
  final lanc = nevek.isEmpty ? "" : "${nevek.join(" → ")} → ";
  final n = ((g["n_passes"] as num?) ?? 0).toInt();
  final hossz = ((g["duration_s"] as num?) ?? 0).toDouble();
  final csapat = g["team"] == "home" ? nevH : nevV;
  return "$csapat gólja — $lanc${m(g["shooter_jersey"])} lő · "
      "${n > 0 ? "$n passz, ${hossz.toStringAsFixed(1).replaceAll(".", ",")} mp" : "passz nélkül"}";
}

/// Az emberelőny-jelző szövege (a böngészős nézet `emberSzoveg`-ének
/// tükre, UGYANAZZAL a szöveggel): "Emberelőny: Szeged (Veszprém
/// kiállítás miatt hiányos) · még 1:13 · az előny alatt eddig 1–0".
/// `w`: a /powerplay-moments egy sora, `t`: a lejátszófej (mp).
String powerplayCaption(
    Map<String, dynamic> w, double t, String nevH, String nevV) {
  final downH = w["team_down"] == "home";
  final elony = downH ? nevV : nevH, hatrany = downH ? nevH : nevV;
  final e = ((w["e"] as num?) ?? t).toDouble();
  final hatra = math.max(0, (e - t).ceil());
  final ido = "${hatra ~/ 60}:${(hatra % 60).toString().padLeft(2, "0")}";
  var fel = 0, le = 0;
  for (final g in ((w["goals"] as List?) ?? const [])) {
    final mp = ((g as List)[0] as num).toDouble();
    if (mp > t) continue;
    if (g[1] == w["team_up"]) {
      fel++;
    } else {
      le++;
    }
  }
  return "Emberelőny: $elony ($hatrany kiállítás miatt hiányos) · még $ido "
      "· az előny alatt eddig $fel–$le";
}
