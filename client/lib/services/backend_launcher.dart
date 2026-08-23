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

import "dart:convert";
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
  final int port;

  /// Hány portot fésülünk át a kezdőtől felfelé — a motor (serve.py)
  /// ugyanekkora tartományban keres szabad portot, ha a 8000-es foglalt.
  static const portRange = 11;

  /// Az utoljára létrehozott indító — a frissítő ezen keresztül állítja le a
  /// motort a fájlcsere előtt (különben a futó motor fogná a fájlokat).
  static BackendLauncher? instance;

  BackendLauncher({this.port = 8000}) {
    instance = this;
  }

  Process? _process;

  /// Igaz, ha a leállítást MI kértük (kilépés, frissítés előtti csere) —
  /// ilyenkor az őrkutya nem indítja újra a motort.
  bool _stoppedByUs = false;

  /// Hányszor indította újra az őrkutya a magától elhalt motort ebben a
  /// munkamenetben — a korlát a hibás motor végtelen pörgetését állítja meg.
  int _watchdogRestarts = 0;
  static const int watchdogMaxRestarts = 3;

  /// Megkeresi, melyik porton válaszol a motor (a kezdőtől felfelé), és
  /// TALÁLATKOR átállítja az alapértelmezett kliens-címet is — az ezután
  /// létrejövő ApiClient-ek automatikusan a jó portra beszélnek.
  Future<int?> _findHealthyPort() async {
    // Párhuzamos próbák (a nem futó portok azonnal elutasítanak) — a
    // legkisebb válaszoló portot választjuk.
    final probes = [
      for (var p = port; p < port + portRange; p++)
        ApiClient(baseUrl: "http://127.0.0.1:$p")
            .isHealthy()
            .then((ok) => ok ? p : null)
    ];
    final results = await Future.wait(probes);
    for (final p in results) {
      if (p != null) {
        ApiClient.defaultBaseUrl = "http://127.0.0.1:$p";
        return p;
      }
    }
    return null;
  }

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

  /// A motor-napló utolsó sorai — a hiba-képernyő mutatja meg, hogy a
  /// kiváltó ok egy képernyőképen elférjen (a felhasználónak ne kelljen
  /// fájlok közt keresgélnie). Hibánál null (pl. még nincs napló).
  static Future<String?> logTail({int lines = 40}) async {
    try {
      final all = await _logFile().readAsLines();
      if (all.isEmpty) return null;
      final from = all.length > lines ? all.length - lines : 0;
      return all.sublist(from).join("\n");
    } catch (_) {
      return null;
    }
  }

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
  /// Az indítási szándék a leállítási szándékot is törli (revive után
  /// az őrkutya újra élesedik).
  Future<BackendStatus> ensureRunning({void Function(String)? onLog}) async {
    _stoppedByUs = false;
    // 1) Már fut valamelyik porton? (A 8000-es foglaltsága esetén a motor
    // tartalék portra köt — ugyanazt a tartományt fésüljük át.)
    final running = await _findHealthyPort();
    if (running != null) {
      onLog?.call("A motor már fut (port: $running).");
      return const BackendStatus(BackendPhase.ready, "A motor fut.");
    }

    // Weben nincs alfolyamat-indítás.
    if (kIsWeb) {
      return const BackendStatus(BackendPhase.noEngine,
          "Webes módban a motort külön kell futtatni.");
    }

    // Napló nyitása (csonkolva — mindig a legutóbbi indítás látszik benne).
    // Az ELŐZŐ sinket le kell zárni: az őrkutyás újraindítás ide is
    // visszatér, és nyitva hagyott sinkkel fájl-leírók szivárognának —
    // Windowson ráadásul a még fogott fájl csonkoló megnyitása el is
    // bukhat, azaz pont az újraindításnál veszne el a napló.
    try {
      await _log?.close();
    } catch (_) {}
    _log = null;
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
      // A motor UTF-8-ban ír, és a sorai MAGYARUL szólnak. A
      // String.fromCharCodes bájtonként képez karaktert, tehát az
      // ékezeteket összetörte ("Ã¡") — pont a naplót, amit a
      // felhasználótól hibakereséshez kérünk. Az allowMalformed azért
      // kell, mert egy darabhatár félbevághat egy több bájtos karaktert:
      // egy sérült jel elfogadható, a kivétel miatt elveszett napló nem.
      _process!.stdout.listen(
          (d) => _logLine(utf8.decode(d, allowMalformed: true).trimRight(),
              onLog));
      _process!.stderr.listen(
          (d) => _logLine(utf8.decode(d, allowMalformed: true).trimRight(),
              onLog));
      _process!.exitCode.then((c) {
        exited = true;
        _logLine("A motor-folyamat leállt, kilépési kód: $c", onLog);
        _watchdog(onLog);
      });
    } catch (e) {
      _logLine("A motort nem sikerült elindítani: $e", onLog);
      return BackendStatus(BackendPhase.failed, "A motort nem sikerült elindítani: $e");
    }

    // A motor indulása — KÜLÖNÖSEN az első alkalommal — sokáig tarthat: a
    // becsomagolt motor negyedmilliárd bájt, és a Windows Defender (vagy
    // más víruskereső) az ELSŐ futásnál végigolvassa, mielőtt a program
    // egyáltalán elindulna. Lassú lemezen ez simán túlmegy két percen.
    final ok = await _waitForHealth(const Duration(seconds: 180),
        isExited: () => exited);
    if (ok) {
      // Sikeres indulás után az őrkutya kvótája újratöltődik: a korlát a
      // BEINDULNI SEM TUDÓ motor pörgetése ellen véd, nem az ellen, hogy
      // egy hosszú munkamenetben többször is kelljen újraéleszteni.
      _watchdogRestarts = 0;
      _logLine("A motor elindult és válaszol.", onLog);
      return const BackendStatus(BackendPhase.ready, "A motor elindult.");
    }
    // FONTOS: itt NEM állítjuk le a motrot.
    //
    // Korábban a lejárt idő stop()-ot hívott — vagyis pont azt a
    // folyamatot lőttük ki, amelyik talán másodpercekre volt attól, hogy
    // válaszoljon (első futás, víruskereső-átvizsgálás). A felhasználó
    // ilyenkor újrapróbált, és az egész átvizsgálás elölről kezdődött:
    // a hiba önmagát tartotta életben. Ráadásul a stop() a
    // `_stoppedByUs` jelzőt is beállítja, ami az őrkutyát is kikapcsolja.
    //
    // Ha a folyamat még ÉL, hagyjuk indulni: az Újrapróbálom (és a
    // motor-újraélesztés) a port-tartomány végigfésülésével úgyis
    // megtalálja, amint válaszol.
    final String why;
    if (exited) {
      why = "A motor idő előtt leállt — részletek: ${_logFile().path}";
    } else {
      why = "A motor még mindig indul (első indításnál a víruskereső "
          "átvizsgálja a programot — ez percekig tarthat). NE zárd be a "
          "programot: várj egy kicsit, és nyomd meg az Újrapróbálom "
          "gombot — amint válaszol, megtalálja.";
    }
    _logLine(why, onLog);
    return BackendStatus(BackendPhase.failed, why);
  }

  /// Őrkutya: ha a motor MAGÁTÓL halt el (nem mi állítottuk le), rövid
  /// várakozás után újraindítja — a felhasználó így észre sem veszi, a
  /// következő kérés már az új példányhoz ér. Korlátozott számú próba:
  /// az induláskor azonnal elhaló (hibás) motort nem pörgetjük örökké.
  Future<void> _watchdog(void Function(String)? onLog) async {
    if (_stoppedByUs) return;
    if (_watchdogRestarts >= watchdogMaxRestarts) {
      _logLine("Őrkutya: elértük az újraindítás-korlátot "
          "($watchdogMaxRestarts) — kézi újraindítás kell.", onLog);
      return;
    }
    _watchdogRestarts += 1;
    _logLine("Őrkutya: a motor magától leállt — újraindítás "
        "($_watchdogRestarts/$watchdogMaxRestarts)…", onLog);
    await Future<void>.delayed(const Duration(seconds: 2));
    if (_stoppedByUs) return; // közben kilépett a program
    await ensureRunning(onLog: onLog);
  }

  /// Megvárja, míg a /health elérhető a port-tartomány VALAMELYIK portján
  /// (a motor tartalék portra köthetett), vagy lejár az idő.
  /// `isExited`: ha a motor-folyamat közben leállt, nincs mire várni.
  Future<bool> _waitForHealth(Duration timeout, {bool Function()? isExited}) async {
    final deadline = DateTime.now().add(timeout);
    while (DateTime.now().isBefore(deadline)) {
      if (await _findHealthyPort() != null) return true;
      if (isExited != null && isExited()) return false;
      await Future<void>.delayed(const Duration(milliseconds: 600));
    }
    return false;
  }

  /// Azok az útvonalak, ahol a beépített motort keressük — sorrendben.
  /// Statikus, mert a DIAGNOSZTIKA is kiírja: ha a motor nincs meg, a
  /// felhasználó (és mi) csak ebből látjuk, hol kerestük.
  static List<String> engineCandidates() {
    final name = Platform.isWindows ? "handball_backend.exe" : "handball_backend";
    final appDir = File(Platform.resolvedExecutable).parent;
    return <String>[
      _join([appDir.path, "engine", name]),
      _join([appDir.path, "backend", name]),
      _join([appDir.path, "data", "engine", name]),
      _join([appDir.path, name]),
      // macOS .app csomag: a Contents/MacOS mellett a Resources/engine.
      _join([appDir.parent.path, "Resources", "engine", name]),
    ];
  }

  /// Megkeresi a beépített motor futtatható fájlját az app mellett.
  /// Sorrend: HANDBALL_ENGINE env → az app melletti "engine/"/"backend/" mappa.
  static File? findEngine() {
    // a) Kifejezett felülbírálás környezeti változóval (fejlesztéshez/haladóknak).
    final override = Platform.environment["HANDBALL_ENGINE"];
    if (override != null && File(override).existsSync()) return File(override);
    for (final c in engineCandidates()) {
      final f = File(c);
      if (f.existsSync()) return f;
    }
    return null;
  }

  File? _findEngineExecutable() => findEngine();

  static String _join(List<String> parts) => parts.join(Platform.pathSeparator);

  /// Egy oldalnyi TÉNY arról, miért nem indul a motor — kimásolható
  /// szövegként.
  ///
  /// A "nem indul el a motor" a leggyakoribb élő hiba, és a napló
  /// önmagában kevés: ha a motor-program meg sem található, vagy az
  /// adatmappa nem írható, a naplóban ennek nyoma sincs (nem is jött
  /// létre). Ez a jelentés a hiányzó feltételeket is kimondja.
  static Future<String> diagnostics({String appVersion = "?"}) async {
    final b = StringBuffer();
    b.writeln("SPORT MACHINE — DIAGNOSZTIKA");
    b.writeln("app verzió: $appVersion");
    b.writeln("rendszer:   ${Platform.operatingSystem} "
        "${Platform.operatingSystemVersion}");
    b.writeln("app helye:  ${Platform.resolvedExecutable}");

    // 1) Megvan-e a motor-program?
    final exe = findEngine();
    if (exe == null) {
      b.writeln("motor:      NINCS MEG — ezeken a helyeken kerestem:");
      for (final c in engineCandidates()) {
        b.writeln("            - $c");
      }
      b.writeln("            (ilyenkor csak a demó mód működik; a teljes,");
      b.writeln("             motorral csomagolt kiadás kell)");
    } else {
      var size = -1;
      try {
        size = await exe.length();
      } catch (_) {}
      b.writeln("motor:      ${exe.path}");
      b.writeln("            méret: ${size < 0 ? "?" : "${size ~/ (1024 * 1024)} MB"}");
    }

    // 2) Írható-e az adatmappa? (Ide megy a napló és ide kerülnek a
    // fiókok — ha nem írható, a motor elindul, de azonnal elhasal.)
    final dir = _logFile().parent;
    try {
      await dir.create(recursive: true);
      final probe = File("${dir.path}${Platform.pathSeparator}.iras-proba");
      await probe.writeAsString("ok");
      await probe.delete();
      b.writeln("adatmappa:  ${dir.path} (írható)");
    } catch (e) {
      b.writeln("adatmappa:  ${dir.path}");
      b.writeln("            NEM ÍRHATÓ: $e");
    }

    // 3) Válaszol-e valamelyik porton?
    final answering = <int>[];
    final probes = [
      for (var p = 8000; p < 8000 + portRange; p++)
        ApiClient(baseUrl: "http://127.0.0.1:$p")
            .isHealthy()
            .then((ok) => ok ? p : null)
    ];
    for (final p in await Future.wait(probes)) {
      if (p != null) answering.add(p);
    }
    b.writeln("portok:     ${answering.isEmpty ? "egyik sem válaszol "
        "(8000–${8000 + portRange - 1})" : answering.join(", ")}");

    // 4) Az ÖSSZEOMLÁS-napló, ha van. A motor ide írja a végzetes
    // indulási kivételt (hiányzó rendszerkönyvtár, OpenMP-ütközés,
    // jogosultsági hiba) — ez a legbeszédesebb egyetlen forrás.
    try {
      final crash = File("${dir.path}${Platform.pathSeparator}"
          "engine-crash.log");
      if (await crash.exists()) {
        final lines = await crash.readAsLines();
        final from = lines.length > 30 ? lines.length - 30 : 0;
        b.writeln("");
        b.writeln("--- a motor ÖSSZEOMLÁS-naplója (vége) ---");
        b.writeln(lines.sublist(from).join("\n"));
      }
    } catch (_) {}

    // 5) A napló vége.
    final tail = await logTail(lines: 40);
    b.writeln("");
    b.writeln("--- a motor naplójának vége ---");
    b.writeln((tail == null || tail.trim().isEmpty)
        ? "(nincs napló — úgy tűnik, a motor el sem indult)"
        : tail);
    return b.toString();
  }

  /// Leállítja a motrot (ha mi indítottuk). Az app bezárásakor hívjuk.
  void stop() {
    _stoppedByUs = true;
    _process?.kill();
    _process = null;
    try {
      _log?.close();
    } catch (_) {}
    _log = null;
  }
}
