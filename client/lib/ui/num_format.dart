/// Számok magyar alakban: tizedesvessző ("97,4 perc", "1,2 – 0,8") —
/// a motor szövegei és az app többi része is így ír; a pont angolos.
library;

/// [v] [digits] tizedesre kerekítve, tizedesvesszővel.
String huNum(num v, [int digits = 1]) =>
    v.toStringAsFixed(digits).replaceAll(".", ",");
