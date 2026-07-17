/// A Flutter-kliens belépési pontja (desktop-first, prémium sötét téma).
///
/// Ugyanaz a kódbázis fut Windows/Mac/Linux desktopon és tableten (iPad/Android).
/// Indítás (asztali, lokális teszt): `flutter run -d windows` (vagy macos/linux).
library;

import "package:flutter/material.dart";
import "package:flutter/services.dart" show AppExitResponse;

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

  // Kilépés-védelem állapota: egyszer fusson le, és a felhasználó
  // kérhessen azonnali bezárást is (mentés nélkül).
  bool _exitHandled = false;
  bool _forceExit = false;

  @override
  void initState() {
    super.initState();
    // Bezárás-elfogás: ha épp feldolgozás fut, az app bezárása eddig
    // ELDOBTA az órákig gyűjtött munkát (a motor az apppal együtt áll le).
    // Mostantól kilépés előtt leállítjuk a futó feldolgozást — a szerver
    // szelíden befejezi és ELMENTI az addig kész részt (lásd stop_check).
    _lifecycle = AppLifecycleListener(onExitRequested: _onExitRequested);
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    super.dispose();
  }

  Future<AppExitResponse> _onExitRequested() async {
    if (_exitHandled) return AppExitResponse.exit;
    try {
      final api = ApiClient();
      final jobs =
          await api.fetchJobs().timeout(const Duration(seconds: 2));
      final running = [
        for (final j in jobs)
          if (j["status"] == "running") j
      ];
      if (running.isEmpty) return AppExitResponse.exit;

      _exitHandled = true;
      _forceExit = false;

      // Tájékoztató ablak, amíg a mentés fut (nem zárható kattintással;
      // a "Bezárás mentés nélkül" gomb a vészkijárat).
      final ctx = _navKey.currentContext;
      if (ctx != null) {
        // Nem várjuk meg a dialógus bezárását — az app úgyis kilép.
        showDialog<void>(
          context: ctx,
          barrierDismissible: false,
          builder: (_) => AlertDialog(
            backgroundColor: AppColors.surface,
            title: const Text("Feldolgozás fut"),
            content: Row(children: [
              const SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(strokeWidth: 2.5)),
              const SizedBox(width: 14),
              Expanded(
                child: Text(
                  "Az eddig feldolgozott rész mentése, utána az app bezárul "
                  "— ez legfeljebb egy-két perc.",
                  style: AppText.label.copyWith(fontSize: 13),
                ),
              ),
            ]),
            actions: [
              TextButton(
                onPressed: () => _forceExit = true,
                child: const Text("Bezárás mentés nélkül",
                    style: TextStyle(color: AppColors.away)),
              ),
            ],
          ),
        );
      }

      for (final j in running) {
        try {
          await api.cancelJob(j["job_id"] as String);
        } catch (_) {}
      }
      // Várunk, amíg a szerver befejezi a mentést (a szelíd leállítás az
      // utómunkát is lefuttatja) — de legfeljebb 2 percet, és a felhasználó
      // bármikor kérhet azonnali kilépést.
      final deadline = DateTime.now().add(const Duration(minutes: 2));
      while (!_forceExit && DateTime.now().isBefore(deadline)) {
        await Future<void>.delayed(const Duration(seconds: 1));
        try {
          final js = await api.fetchJobs();
          if (!js.any((j) => j["status"] == "running")) break;
        } catch (_) {
          break; // a motor már nem válaszol — nincs mire várni
        }
      }
      return AppExitResponse.exit;
    } catch (_) {
      // Hibánál SOSEM ragasztjuk be a felhasználót — kilépünk.
      return AppExitResponse.exit;
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
