/// A Flutter-kliens belépési pontja (desktop-first, prémium sötét téma).
///
/// Ugyanaz a kódbázis fut Windows/Mac/Linux desktopon és tableten (iPad/Android).
/// Indítás (asztali, lokális teszt): `flutter run -d windows` (vagy macos/linux).
library;

import "dart:async";

import "package:flutter/material.dart";

import "services/api_client.dart";
import "theme/app_theme.dart";
import "ui/bootstrap_screen.dart";

void main() {
  runApp(const HandballApp());
}

class HandballApp extends StatefulWidget {
  const HandballApp({super.key});

  @override
  State<HandballApp> createState() => _HandballAppState();
}

class _HandballAppState extends State<HandballApp> {
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
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    super.dispose();
  }

  // Bezáráskor (a platform az ablak zárásakor detach-eli az appot):
  // ha épp feldolgozás fut, kérjük a szelíd leállítást — a szerver az
  // addig kész részt elmenti. Fire-and-forget: a detach után nincs mód
  // megvárni, de a kérés elindul, és a checkpoint fedezi a maradékot.
  void _onDetach() {
    if (_exitHandled) return;
    _exitHandled = true;
    unawaited(_stopRunningJobs());
  }

  Future<void> _stopRunningJobs() async {
    try {
      final api = ApiClient();
      final jobs =
          await api.fetchJobs().timeout(const Duration(seconds: 2));
      for (final j in jobs) {
        if (j["status"] == "running") {
          try {
            await api.cancelJob(j["job_id"] as String);
          } catch (_) {}
        }
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
