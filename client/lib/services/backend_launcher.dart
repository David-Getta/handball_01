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

  /// Az utoljára létrehozott indító — a frissítő ezen keresztül állítja le a
  /// motort a fájlcsere előtt (különben a futó motor fogná a fájlokat).
  static BackendLauncher? instance;

  BackendLauncher({this.baseUrl = "http://127.0.0.1:8000", this.port = 8000}) {
    instance = this;
  }

  Process? _process;
  final _api = ApiClient(baseUrl: "http://127.0.0.1:8000");

  /// A motor kimenetének naplófájlja a felhasználói adatmappában — ha a motor
  /// nem indul, ebből látszik, miért (engine-app.log).
  static File _logFile() {
    final home = Platform.environment["HOME"] ?? "";
    final String dir;
    if (Platform.isWindows) {
      final base = Platform.environment["LOCALAPPDATA"] ?? "$home\\AppData\\Local";
      dir = "$base\\SportMachine";
    } else if (Platform.isMacOS) {
      dir = "$home/Library/Application Support/SportMachine";
    } else {
      dir = "$home/.local/share/sportmachine";
    }
    return File("$dir${Platform.pathSeparator}engine-app.log");
  }

  IOSink? _log;

  /// Naplósor a fájlba ÉS a kezdőképernyőre (ha van hallgató). A naplózás
  /// hibája sosem akadályozhatja az indítást.
  void _logLine(String s, void Function(String)? onLog) {
    onLog?.call(s);
    try {
      _log?.writeln("${DateTime.now().toIso8601String()}  $s");
    } catch (_) {}
  }

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

    // Napló nyitása (csonkolva — mindig a legutóbbi indítás látszik benne).
    try {
      final f = _logFile();
      await f.parent.create(recursive: true);
      _log = f.openWrite();
    } catch (_) {}

    // 2) Megkeressük a beépített motort az app mellett.
    final exe = _findEngineExecutable();
    if (exe == null) {
      _logLine("Nem találom a beépített motort — demó mód elérhető.", onLog);
      return const BackendStatus(BackendPhase.noEngine,
          "Nincs beépített motor. A demó így is működik; a valós elemzéshez a "
          "teljes (motorral csomagolt) kiadás kell.");
    }

    // 3) macOS: karantén-öngyógyítás. A letöltött (nem notarizált) appban a
    // beágyazott motort a Gatekeeper a karantén-attribútum miatt CSENDBEN
    // blokkolhatja — az eredmény: "Connection refused", motor nélkül. Az
    // attribútum eltávolítása a saját csomagunkon belül biztonságos.
    if (Platform.isMacOS) {
      try {
        final r = await Process.run("/usr/bin/xattr",
            ["-dr", "com.apple.quarantine", exe.parent.path]);
        _logLine("karantén-attribútum eltávolítása (kilépési kód: ${r.exitCode})",
            onLog);
      } catch (e) {
        _logLine("karantén-eltávolítás kihagyva: $e", onLog);
      }
      try {
        await Process.run("/bin/chmod", ["+x", exe.path]);
      } catch (_) {}
    }

    // 4) Elindítjuk és megvárjuk, míg válaszol.
    _logLine("Motor indítása: ${exe.path}", onLog);
    var exited = false; // idő előtti leállás jelzése a várakozónak
    try {
      _process = await Process.start(
        exe.path,
        const [],
        workingDirectory: exe.parent.path,
        environment: {"HANDBALL_HOST": "127.0.0.1", "HANDBALL_PORT": "$port"},
      );
      _process!.stdout.listen((d) => _logLine(String.fromCharCodes(d).trimRight(), onLog));
      _process!.stderr.listen((d) => _logLine(String.fromCharCodes(d).trimRight(), onLog));
      _process!.exitCode.then((c) {
        exited = true;
        _logLine("A motor-folyamat leállt, kilépési kód: $c", onLog);
      });
    } catch (e) {
      _logLine("A motort nem sikerült elindítani: $e", onLog);
      return BackendStatus(BackendPhase.failed, "A motort nem sikerült elindítani: $e");
    }

    // A motor indulása (különösen az első alkalommal) eltarthat akár egy
    // percig is (a rendszer első futáskor átvizsgálja a nagy programfájlt).
    final ok = await _waitForHealth(const Duration(seconds: 90), isExited: () => exited);
    if (ok) {
      _logLine("A motor elindult és válaszol.", onLog);
      return const BackendStatus(BackendPhase.ready, "A motor elindult.");
    }
    final why = exited
        ? "A motor idő előtt leállt — részletek: ${_logFile().path}"
        : "A motor nem válaszolt időben — részletek: ${_logFile().path}";
    _logLine(why, onLog);
    stop();
    return BackendStatus(BackendPhase.failed, why);
  }

  /// Megvárja, míg a /health elérhető (rövid lekérdezésekkel), vagy lejár az
  /// idő. `isExited`: ha a motor-folyamat közben leállt, nincs mire várni.
  Future<bool> _waitForHealth(Duration timeout, {bool Function()? isExited}) async {
    final deadline = DateTime.now().add(timeout);
    while (DateTime.now().isBefore(deadline)) {
      if (await _api.isHealthy()) return true;
      if (isExited != null && isExited()) return false;
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
    try {
      _log?.close();
    } catch (_) {}
    _log = null;
  }
}
