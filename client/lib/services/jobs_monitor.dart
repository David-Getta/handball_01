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
    jobs.value = friss;
    if (voltAktiv && !vanAktiv) {
      // Épp most futott ki az utolsó munka: a könyvtárat frissíteni kell.
      finishedTick.value += 1;
    }
    _timer?.cancel();
    _timer = Timer(
        Duration(seconds: vanAktiv ? 2 : 30), () => unawaited(_poll()));
  }
}
