/// Számok magyar alakban: tizedesvessző ("97,4 perc", "1,2 – 0,8") —
/// a motor szövegei és az app többi része is így ír; a pont angolos.
library;

/// A meccs eredmény-címkéje a szezon-trendben: a VALÓDI (jegyzőkönyvi,
/// ✎-mel megadott) eredmény, ha van — a felismerés valódi felvételen
/// gyakran kevesebb gólt talál —, különben a felismert.
String trendScore(Map<String, dynamic> m) {
  final rh = m["real_goals_home"], ra = m["real_goals_away"];
  if (rh != null && ra != null) return "$rh:$ra";
  return "${m["goals_home"]}:${m["goals_away"]}";
}

/// A felismert figura befejezései (a motor playbook-match "outcomes"
/// sora): "2 gól · 1 lövés · 1 eladás" — a motor sorrendjében (gól,
/// hetes, lövés, eladás, egyéb); üres, ha nincs adat.
String playbookOutcomeText(Map<String, dynamic>? o) {
  if (o == null) return "";
  const sorrend = ["gól", "hetes", "lövés", "eladás", "egyéb"];
  return [
    for (final k in sorrend)
      if (((o[k] as num?) ?? 0) > 0) "${(o[k] as num).toInt()} $k"
  ].join(" · ");
}

/// Videó-időpont másodpercre: "4:30" (perc:mp), "83:40" (perc:mp egy
/// óra fölött is), "1:23:40" (óra:perc:mp — egy óránál hosszabb
/// felvételen a lejátszó így mutatja) vagy puszta másodperc ("750",
/// "95,5"). A másodperc — óra:perc:mp-nél a perc is — 0–59, tizedes
/// másodperc vesszővel is. Üresnél / hibás alaknál null.
double? parseClockSeconds(String s) {
  final t = s.trim().replaceAll(",", ".");
  if (t.isEmpty) return null;
  final reszek = [for (final r in t.split(":")) r.trim()];
  if (reszek.length > 3) return null;
  final mp = double.tryParse(reszek.last);
  if (mp == null || mp.isNaN || mp.isInfinite || mp < 0) return null;
  if (reszek.length == 1) return mp;
  if (mp >= 60) return null;
  final egeszek = [
    for (final r in reszek.sublist(0, reszek.length - 1)) int.tryParse(r)
  ];
  if (egeszek.any((v) => v == null || v < 0)) return null;
  if (reszek.length == 3 && egeszek[1]! > 59) return null;
  var ossz = 0.0;
  for (final v in egeszek) {
    ossz = ossz * 60 + v!;
  }
  return ossz * 60 + mp;
}

/// Másodperc → "perc:mp" (549 → "9:09"), egy óra fölött "óra:perc:mp"
/// (5020 → "1:23:40") — a parseClockSeconds párja.
String formatClock(double s) {
  final t = s.round();
  final ora = t ~/ 3600;
  final perc = (t % 3600) ~/ 60;
  final mp = (t % 60).toString().padLeft(2, "0");
  return ora > 0 ? "$ora:${perc.toString().padLeft(2, "0")}:$mp" : "$perc:$mp";
}

/// [v] [digits] tizedesre kerekítve, tizedesvesszővel.
String huNum(num v, [int digits = 1]) =>
    v.toStringAsFixed(digits).replaceAll(".", ",");
