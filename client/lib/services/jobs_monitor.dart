/// A futó feldolgozások KÖZÖS figyelője — egy helyen, minden képernyőnek.
///
/// Egy meccs feldolgozása percekig fut. Eddig a haladást csak a kezdőlap
/// mutatta, és csak amíg ott állt a felhasználó: aki közben átment a
/// felderítésre vagy a figura-tervezőbe, elvesztette a szem elől, és
/// nem volt hová visszamennie. Ez a figyelő teszi lehetővé, hogy
///
///   - a menüben BÁRHONNAN látszódjon, hány feldolgozás fut (jelvény),
///   - legyen egy külön képernyő, ahová vissza lehet térni hozzájuk,
///   - és mindehhez EGY kérdezgető járjon, ne képernyőnként külön.
///
/// A ritmus szándékosan kétsebességes: amíg fut valami, kétmásodpercenként
/// kérdezünk (a haladás-sáv így folyamatosan mozog), üresjáratban viszont
/// csak félpercenként — hogy az elemzés, amit a felhasználó MÁSHOL indított
/// (vagy egy korábbi munkamenetből maradt), előbb-utóbb megjelenjen, de a
/// motort ne terheljük fölöslegesen.
library;

import "dart:async";

import "package:flutter/foundation.dart";

import "api_client.dart";

/// A hátralévő idő emberi feliratként — vagy null, ha nincs becslés.
///
/// A motor csak akkor ad becslést, ha már van mire alapozni (az első pár
/// százalék félrevezető: ott a modell-betöltés és a videó-megnyitás
/// torzít). Az "kb." szó szándékos: becslés, nem ígéret.
String? etaLabel(Map<String, dynamic> job) {
  final s = (job["eta_s"] as num?)?.toInt();
  if (s == null || s <= 0) return null;
  if (s < 60) return "kb. $s másodperc van hátra";
  final perc = (s / 60).round();
  if (perc < 60) return "kb. $perc perc van hátra";
  final ora = s ~/ 3600;
  final maradek = ((s % 3600) / 60).round();
  return "kb. $ora óra ${maradek} perc van hátra";
}

class JobsMonitor {
  JobsMonitor._();

  /// Egyetlen példány: a menü-jelvény és a Feldolgozások képernyő
  /// ugyanazt az állapotot látja, és egyetlen kérdezgető jár.
  static final JobsMonitor instance = JobsMonitor._();

  final ApiClient _api = ApiClient();

  /// A feldolgozási munkák — legújabb elöl. A hallgatók (menü-jelvény,
  /// képernyő) ebből épülnek.
  final ValueNotifier<List<Map<String, dynamic>>> jobs =
      ValueNotifier<List<Map<String, dynamic>>>(const []);

  /// Igaz, ha épp most fejeződött be egy munka — a kezdőlap ilyenkor
  /// újratölti a könyvtárat. A hallgató a leolvasás után nullázza.
  final ValueNotifier<int> finishedTick = ValueNotifier<int>(0);

  /// Az ÉPP MOST befejeződött munka rekordja — vagy null, ha nincs
  /// bejelentenivaló.
  ///
  /// Ez az értesítés lelke: a feldolgozás percekig fut, a felhasználó
  /// közben máshol dolgozik az appban, és eddig CSAK úgy tudta meg, hogy
  /// kész, ha visszament megnézni. Innentől a burok bárhol szól neki.
  /// A megszakított munkát szándékosan nem jelentjük be: azt ő maga
  /// állította le, nem hír.
  final ValueNotifier<Map<String, dynamic>?> lastFinished =
      ValueNotifier<Map<String, dynamic>?>(null);

  /// Az értesítés elrejtése (elolvasta, vagy továbblépett rajta).
  void dismissFinished() => lastFinished.value = null;

  /// A legutóbb LÁTOTT állapotok munkánként — ebből derül ki, melyik
  /// munka lépett át futóból késszé (a puszta "nincs több aktív" ezt
  /// nem mondja meg, márpedig a felhasználót az érdekli, MELYIK).
  final Map<String, String> _elozoAllapot = <String, String>{};

  Timer? _timer;
  bool _running = false;

  /// Fut vagy sorban áll-e a munka.
  static bool isActive(Map<String, dynamic> j) =>
      j["status"] == "running" || j["status"] == "queued";

  /// Hány feldolgozás aktív most (ez megy a menü-jelvényre).
  int get activeCount => jobs.value.where(isActive).length;

  /// Elindítja a figyelést (többszöri hívás ártalmatlan).
  void start() {
    if (_running) return;
    _running = true;
    _poll();
  }

  /// Leállítja a figyelést (az app bezárásakor).
  void stop() {
    _running = false;
    _timer?.cancel();
    _timer = null;
  }

  /// Azonnali frissítés — pl. miután a felhasználó elindított egy
  /// elemzést, ne kelljen a következő körre várni.
  Future<void> refreshNow() => _poll();

  Future<void> _poll() async {
    if (!_running) return;
    final friss = await _api.fetchJobs();
    final voltAktiv = jobs.value.any(isActive);
    final vanAktiv = friss.any(isActive);
    _jeloldMegAzUjonnanKeszet(friss);
    jobs.value = friss;
    if (voltAktiv && !vanAktiv) {
      // Épp most futott ki az utolsó munka: a könyvtárat frissíteni kell.
      finishedTick.value += 1;
    }
    _timer?.cancel();
    _timer = Timer(
        Duration(seconds: vanAktiv ? 2 : 30), () => unawaited(_poll()));
  }

  /// Megkeresi, melyik munka lépett át AKTÍVBÓL lezártba, és azt teszi
  /// be bejelentésre.
  ///
  /// Az első kör szándékosan néma: ott minden munka "új" a figyelőnek,
  /// és a tegnapi kész elemzést ma reggel bejelenteni értelmetlen.
  void _jeloldMegAzUjonnanKeszet(List<Map<String, dynamic>> friss) {
    final elsoKor = _elozoAllapot.isEmpty;
    for (final j in friss) {
      final id = j["job_id"] as String?;
      if (id == null) continue;
      final most = (j["status"] as String?) ?? "";
      final elozo = _elozoAllapot[id];
      _elozoAllapot[id] = most;
      if (elsoKor || elozo == null) continue;
      final voltAktiv = elozo == "running" || elozo == "queued";
      final mostAktiv = most == "running" || most == "queued";
      // A megszakítást nem jelentjük be: azt a felhasználó kérte.
      if (voltAktiv && !mostAktiv && most != "cancelled") {
        lastFinished.value = j;
      }
    }
  }
}
