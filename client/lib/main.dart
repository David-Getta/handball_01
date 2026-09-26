/// A Flutter-kliens belépési pontja (desktop-first, prémium sötét téma).
///
/// Ugyanaz a kódbázis fut Windows/Mac/Linux desktopon és tableten (iPad/Android).
/// Indítás (asztali, lokális teszt): `flutter run -d windows` (vagy macos/linux).
library;

import "dart:async";
import "dart:io";
import "dart:ui" show AppExitResponse;

import "package:flutter/material.dart";
import "package:media_kit/media_kit.dart";

import "services/api_client.dart";
import "services/backend_launcher.dart";
import "theme/app_theme.dart";
import "ui/bootstrap_screen.dart";

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // A Windows-os jelenet-lejátszó (media_kit/libmpv) inicializálása —
  // csak ott, ahol a natív könyvtárak be vannak csomagolva; a többi
  // platform a video_player-t használja (lásd ui/video_panel.dart).
  if (Platform.isWindows) {
    try {
      MediaKit.ensureInitialized();
    } catch (_) {
      // Ha a lejátszó-könyvtár hiányzik, az app a lejátszó nélkül fut
      // tovább — a videó-panel tájékoztató szöveget mutat.
    }
  }
  runApp(const HandballApp());
}

class HandballApp extends StatefulWidget {
  const HandballApp({super.key});

  @override
  State<HandballApp> createState() => _HandballAppState();
}

class _HandballAppState extends State<HandballApp>
    with WidgetsBindingObserver {
  final GlobalKey<NavigatorState> _navKey = GlobalKey<NavigatorState>();
  late final AppLifecycleListener _lifecycle;

  // Kilépés-védelem: a leállítás-kérés egyszer fusson le.
  bool _exitHandled = false;

  @override
  void initState() {
    super.initState();
    // Bezárás-elfogás: ha épp feldolgozás fut, az app bezárása eddig
    // ELDOBTA az órákig gyűjtött munkát (a motor az apppal együtt áll le).
    // Mostantól kilépés előtt leállítjuk a futó feldolgozást — a szerver
    // szelíden befejezi és ELMENTI az addig kész részt (lásd stop_check).
    // A kilépés-elhalasztó API (onExitRequested → AppExitResponse) Flutter-
    // verziónként változó szimbólum; helyette az onDetach-ra kötünk, ami
    // minden verzióban elérhető. A bezáráskor best-effort leállítjuk a
    // futó feldolgozást — a szerver a részt szelíden elmenti; a maradék
    // kockázatot a 3 percenkénti checkpoint amúgy is fedezi.
    _lifecycle = AppLifecycleListener(onDetach: _onDetach);
    // A kilépés-kérés (ablak bezárása, Cmd+Q) az APP szintjén él, az
    // egész futás alatt. Korábban az indító képernyőhöz volt kötve, ami
    // a belépéskor lecserélődik — a kilépéskori motor-leállítás így
    // sosem futott le, és a motor árván maradt a program után.
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _lifecycle.dispose();
    super.dispose();
  }

  /// Kilépés-kérés: előbb a futó feldolgozás szelíd leállítása (a szerver
  /// az addig kész részt ELMENTI — ezt meg is várjuk, legfeljebb
  /// `_exitSaveWait`-ig), utána a motor leállítása. A kilépést a mentés
  /// idejére halasztjuk: különben az órákig gyűjtött munka veszne el.
  @override
  Future<AppExitResponse> didRequestAppExit() async {
    await _shutdown(waitForSave: true);
    return AppExitResponse.exit;
  }

  static const Duration _exitSaveWait = Duration(seconds: 25);

  // Bezáráskor (a platform az ablak zárásakor detach-eli az appot), ha a
  // kilépés-kérés nem jött meg: best-effort, várakozás nélkül.
  void _onDetach() {
    unawaited(_shutdown(waitForSave: false));
  }

  Future<void> _shutdown({required bool waitForSave}) async {
    if (_exitHandled) return;
    _exitHandled = true;
    await _stopRunningJobs(waitForSave: waitForSave);
    // A motor leállítása: a KILÉPÉSKOR, nem korábban (lásd fent).
    BackendLauncher.instance?.stop();
  }

  Future<void> _stopRunningJobs({required bool waitForSave}) async {
    try {
      final api = ApiClient();
      final jobs =
          await api.fetchJobs().timeout(const Duration(seconds: 3));
      final futok = [
        for (final j in jobs)
          if (j["status"] == "running") j["job_id"] as String,
      ];
      for (final id in futok) {
        try {
          await api.cancelJob(id);
        } catch (_) {}
      }
      if (!waitForSave || futok.isEmpty) return;
      // Megvárjuk, amíg a futó munka lezárul (a rész-eredmény mentése).
      final hatarido = DateTime.now().add(_exitSaveWait);
      while (DateTime.now().isBefore(hatarido)) {
        await Future<void>.delayed(const Duration(seconds: 1));
        final most = await api.tryFetchJobs();
        if (most == null) return; // a motor már nem felel — nincs mit várni
        final meg = most.any(
            (j) => futok.contains(j["job_id"]) && j["status"] == "running");
        if (!meg) return;
      }
    } catch (_) {
      // A motor már nem válaszol vagy nincs futó munka — nincs teendő.
    }
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: "Sport Machine",
      debugShowCheckedModeBanner: false,
      navigatorKey: _navKey,
      theme: AppTheme.dark,
      // Az indító képernyő elindítja a motort (backend), majd belép a dashboardra.
      home: const BootstrapScreen(),
    );
  }
}
