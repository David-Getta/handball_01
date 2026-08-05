/// Hibaüzenetek emberi nyelven.
///
/// A nyers kivétel semmit nem mond egy edzőnek. A leggyakoribb hiba —
/// hogy a háttérmotor nem fut — így néz ki nyersen:
///
///   SocketException: Connection refused (OS Error: Connection refused,
///   errno = 111), address = 127.0.0.1, port = 8000
///
/// Ebből a felhasználó nem tudja meg sem azt, MI történt, sem azt, mit
/// tegyen. Ez a modul a felismerhető eseteket lefordítja egy mondatra,
/// és hozzáteszi a teendőt. Amit nem ismer fel, azt VÁLTOZATLANUL adja
/// vissza: jobb egy nyers üzenet, mint egy félrevezető tipp.
library;

/// A felismert hiba-minták: (kulcsszavak, emberi mondat).
///
/// A kulcsszavakat kisbetűsítve keressük a kivétel szövegében; az első
/// illeszkedő minta nyer, ezért a sorrend a specifikustól halad az
/// általános felé.
const List<(List<String>, String)> kErrorPatterns = [
  (
    ["connection refused", "socketexception", "failed host lookup",
     "connection closed", "os error: connection"],
    "Nem érem el a háttérmotort. Fut a Sport Machine motor? "
        "A program újraindítása magától elindítja.",
  ),
  (
    ["timeout", "timed out"],
    "A motor nem válaszolt időben. Nagy felvételnél ez előfordul — "
        "próbáld újra, vagy várd meg a futó feldolgozás végét.",
  ),
  (
    ["no space left", "enospc"],
    "Betelt a lemez. Szabadíts fel helyet, és próbáld újra.",
  ),
  (
    ["permission denied", "access is denied", "eacces"],
    "Nincs jogosultság a fájlhoz vagy a mappához. Válassz másik "
        "helyet, vagy indítsd a programot megfelelő joggal.",
  ),
  (
    ["404"],
    "A kért elem nincs meg (lehet, hogy időközben törölték).",
  ),
  (
    ["401", "403"],
    "Nincs jogosultság a művelethez (hiányzó vagy lejárt hozzáférés).",
  ),
  (
    ["500", "internal server error"],
    "A motor hibára futott a feldolgozás közben. Ha megismétlődik, "
        "a naplóval együtt érdemes jelenteni.",
  ),
];

/// Egy kivétel emberi nyelvű üzenete.
///
/// Felismert esetnél a magyarázat + teendő; egyébként a nyers szöveg.
String humanError(Object e) {
  final raw = "$e";
  final low = raw.toLowerCase();
  for (final (keys, message) in kErrorPatterns) {
    for (final k in keys) {
      if (low.contains(k)) return message;
    }
  }
  return raw;
}
