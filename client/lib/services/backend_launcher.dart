/// A beépített backend (elemző motor) automatikus indítása — hogy a felhasználónak
/// SEMMIT ne kelljen parancssorból beírnia.
///
/// A becsomagolt kiadásban a Flutter-app mellé kerül a "motor" (a backend önálló,
/// telepítés nélküli futtatható programja). Ez az osztály:
///  1. megnézi, fut-e már backend a localhoston (/health) — ha igen, azt használja,
///  2. különben megkeresi a beépített motor-programot az app mellett, és elindítja,
///  3. megvárja, míg a motor válaszol (/health), majd jelzi, hogy kész.
/// Az app bezárásakor a motrot is leállítja.
///
/// Weben (kIsWeb) nincs alfolyamat: ilyenkor csak a /health-et ellenőrzi.
library;

import "dart:io";

import "package:flutter/foundation.dart";

import "api_client.dart";

/// A motor-indítás eredménye — ezt mutatja a kezdőképernyő.
enum BackendPhase {
  ready,        // fut és válaszol (mi indítottuk, vagy már futott)
  starting,     // épp indul
  noEngine,     // nincs beépített motor és nem is fut → demó módban is használható
  failed,       // volt motor, de nem indult el / nem válaszolt
}

class BackendStatus {
  final BackendPhase phase;
  final String message;
  const BackendStatus(this.phase, this.message);
}

class BackendLauncher {
  final String baseUrl;
  final int port;
  BackendLauncher({this.baseUrl = "http://localhost:8000", this.port = 8000});

  Process? _process;
  final _api = ApiClient(baseUrl: "http://localhost:8000");

  /// Elindítja (ha kell) a backendet, és visszaadja a végállapotot.
  /// `onLog`: a motor kimenete/állapot-üzenetek a kezdőképernyőnek.
  Future<BackendStatus> ensureRunning({void Function(String)? onLog}) async {
    // 1) Már fut?
    if (await _api.isHealthy()) {
      onLog?.call("A motor már fut.");
      return const BackendStatus(BackendPhase.ready, "A motor fut.");
    }

    // Weben nincs alfolyamat-indítás.
    if (kIsWeb) {
      return const BackendStatus(BackendPhase.noEngine,
          "Webes módban a motort külön kell futtatni.");
    }

    // 2) Megkeressük a beépített motort az app mellett.
    final exe = _findEngineExecutable();
    if (exe == null) {
      onLog?.call("Nem találom a beépített motort — demó mód elérhető.");
      return const BackendStatus(BackendPhase.noEngine,
          "Nincs beépített motor. A demó így is működik; a valós elemzéshez a "
          "teljes (motorral csomagolt) kiadás kell.");
    }

    // 3) Elindítjuk és megvárjuk, míg válaszol.
    onLog?.call("Motor indítása: ${exe.path}");
    try {
      _process = await Process.start(
        exe.path,
        const [],
        workingDirectory: exe.parent.path,
        environment: {"HANDBALL_HOST": "127.0.0.1", "HANDBALL_PORT": "$port"},
      );
      _process!.stdout.listen((d) => onLog?.call(String.fromCharCodes(d).trimRight()));
      _process!.stderr.listen((d) => onLog?.call(String.fromCharCodes(d).trimRight()));
    } catch (e) {
      return BackendStatus(BackendPhase.failed, "A motort nem sikerült elindítani: $e");
    }

    // A motor indulása (különösen az első alkalommal) eltarthat pár másodpercig.
    final ok = await _waitForHealth(const Duration(seconds: 40));
    if (ok) {
      return const BackendStatus(BackendPhase.ready, "A motor elindult.");
    }
    stop();
    return const BackendStatus(BackendPhase.failed,
        "A motor elindult, de nem válaszolt időben.");
  }

  /// Megvárja, míg a /health elérhető (rövid lekérdezésekkel), vagy lejár az idő.
  Future<bool> _waitForHealth(Duration timeout) async {
    final deadline = DateTime.now().add(timeout);
    while (DateTime.now().isBefore(deadline)) {
      if (await _api.isHealthy()) return true;
      await Future<void>.delayed(const Duration(milliseconds: 600));
    }
    return false;
  }

  /// Megkeresi a beépített motor futtatható fájlját az app mellett.
  /// Sorrend: HANDBALL_ENGINE env → az app melletti "engine/"/"backend/" mappa.
  File? _findEngineExecutable() {
    final name = Platform.isWindows ? "handball_backend.exe" : "handball_backend";

    // a) Kifejezett felülbírálás környezeti változóval (fejlesztéshez/haladóknak).
    final override = Platform.environment["HANDBALL_ENGINE"];
    if (override != null && File(override).existsSync()) return File(override);

    // b) Az app futtatható fájlja melletti szokásos helyek.
    final appDir = File(Platform.resolvedExecutable).parent;
    final candidates = <String>[
      _join([appDir.path, "engine", name]),
      _join([appDir.path, "backend", name]),
      _join([appDir.path, "data", "engine", name]),
      _join([appDir.path, name]),
      // macOS .app csomag: a Contents/MacOS mellett a Resources/engine.
      _join([appDir.parent.path, "Resources", "engine", name]),
    ];
    for (final c in candidates) {
      final f = File(c);
      if (f.existsSync()) return f;
    }
    return null;
  }

  String _join(List<String> parts) => parts.join(Platform.pathSeparator);

  /// Leállítja a motrot (ha mi indítottuk). Az app bezárásakor hívjuk.
  void stop() {
    _process?.kill();
    _process = null;
  }
}
