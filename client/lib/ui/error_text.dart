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

/// "Nincs ilyen elem" státuszok.
const List<String> kNotFoundKeys = [
  "http 404", "404 not found", "status 404",
];

/// "Nincs jogosultság" státuszok.
const List<String> kForbiddenKeys = [
  "http 401", "http 403", "401 unauthorized", "403 forbidden",
  "status 401", "status 403",
];

/// A felismert hiba-minták: (kulcsszavak, emberi mondat).
///
/// A kulcsszavakat kisbetűsítve keressük a kivétel szövegében; az első
/// illeszkedő minta nyer, ezért a sorrend a specifikustól halad az
/// általános felé.
const List<(List<String>, String)> kErrorPatterns = [
  (
    kConnectionKeys,
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
  (kNotFoundKeys, "A kért elem nincs meg (lehet, hogy időközben törölték)."),
  (
    kForbiddenKeys,
    "Nincs jogosultság a művelethez (hiányzó vagy lejárt hozzáférés).",
  ),
  (
    ["http 500", "internal server error", "status 500"],
    "A motor hibára futott a feldolgozás közben. Ha megismétlődik, "
        "a naplóval együtt érdemes jelenteni.",
  ),
];

/// Egy kivétel emberi nyelvű üzenete.
///
/// Felismert esetnél a magyarázat + teendő; egyébként a nyers szöveg.
///
/// A státuszkódokat SZÁNDÉKOSAN nem puszta számként keressük: a "404"
/// előfordulhat fájlnévben (`match_404.mp4`), azonosítóban vagy
/// időbélyegben is, és egy ilyen véletlen találat rosszabb, mint a
/// nyers üzenet — magabiztosan mondana valótlant. A kliens kivételei
/// mind "HTTP 404" alakúak, a külső könyvtáraké "404 Not Found".
String humanError(Object e) {
  // A Dart alap-kivételei "Exception: " előtaggal írják ki magukat — ez a
  // felhasználónak semmit nem mond, a mögötte lévő (nálunk magyar) mondat
  // viszont igen. Az előtagot ezért levágjuk.
  final raw = "$e".replaceFirst(RegExp(r"^Exception:\s*"), "");
  final low = raw.toLowerCase();
  for (final (keys, message) in kErrorPatterns) {
    for (final k in keys) {
      if (low.contains(k)) return message;
    }
  }
  return raw;
}

/// Kapcsolódási hibára utal-e a kivétel (nem érjük el a motort)?
///
/// A hívó ilyenkor tud okosat tenni: megkeresni a motort újra (másik
/// porton is indulhatott), és egyszer újrapróbálni. A minták ugyanabból
/// a nevesített listából jönnek, mint a hibafordító első szabálya — a
/// két hely nem tud széttartani.
const List<String> kConnectionKeys = [
  "connection refused", "socketexception", "failed host lookup",
  "connection closed", "os error: connection", "connection reset",
];

bool looksLikeConnectionIssue(Object e) {
  final low = "$e".toLowerCase();
  for (final k in kConnectionKeys) {
    if (low.contains(k)) return true;
  }
  return false;
}

/// Hozzáférési hibára utal-e a kivétel (nem megtalált VAGY nem
/// engedélyezett)?
///
/// A frissítés-ellenőrzésnek ez külön kell: privát repónál a GitHub
/// 404-et ad 403 helyett, és ilyenkor kulcsot (tokent) kell kérni a
/// felhasználótól. Ugyanazokat a nevesített minta-listákat használja,
/// mint a fordító — hogy a két hely ne tudjon széttartani.
bool looksLikeAccessIssue(Object e) {
  final low = "$e".toLowerCase();
  for (final k in [...kNotFoundKeys, ...kForbiddenKeys]) {
    if (low.contains(k)) return true;
  }
  return false;
}
