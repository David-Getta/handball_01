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

/// [v] [digits] tizedesre kerekítve, tizedesvesszővel.
String huNum(num v, [int digits = 1]) =>
    v.toStringAsFixed(digits).replaceAll(".", ",");
