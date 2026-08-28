/// A lokális backend REST API kliense.
///
/// LOKÁLIS MÓD: a backend (Python/FastAPI) ugyanazon a laptopon fut, a kliens a
/// localhost-on éri el (lásd docs/ARCHITECTURE.md). Alapból http://localhost:8000.
/// Végpontok: GET /matches/{id} (Tracking JSON), GET /matches/{id}/stats.
library;

import "dart:convert";
import "dart:io";
import "dart:typed_data";
import "package:http/http.dart" as http;

import "../models/tracking.dart";
import "backend_launcher.dart";
import "session_store.dart";

class ApiClient {
  /// Kimondott cím-felülbírálás (port-próbákhoz). Ha null, a kliens az
  /// ÉPPEN érvényes alapértelmezést használja — lásd `baseUrl`.
  final String? _baseUrlOverride;

  /// A backend alap-URL-je. Lokális teszthez a laptopon ez a localhost.
  ///
  /// Szándékosan getter, nem a példány létrehozásakor befagyasztott érték:
  /// a motor menet közben is költözhet másik portra (újraindítás, tartalék
  /// port), és a régóta nyitva lévő képernyők addig a HALOTT címre
  /// beszéltek volna.
  String get baseUrl => _baseUrlOverride ?? defaultBaseUrl;

  /// Az alapértelmezett cím — a motor-indító ÁTÁLLÍTJA, ha a motor tartalék
  /// porton indult (a 8000-es foglalt volt). Az ezután létrejövő kliensek
  /// automatikusan a jó címet használják.
  static String defaultBaseUrl = "http://127.0.0.1:8000";

  /// Hány portot fésülünk át a 8000-estől felfelé, ha keressük a motort
  /// (a motor ugyanekkora tartományban keres szabad portot).
  static const int portRange = 11;

  ApiClient({String? baseUrl}) : _baseUrlOverride = baseUrl;

  /// Megkeresi ÚJRA, melyik porton válaszol a motor, és átállítja az
  /// alapértelmezett címet. Akkor kell, ha egy hívás hálózati hibára
  /// futott: a motor közben újraindulhatott másik porton (pl. két
  /// példány közül az egyik kilépett). Igaz, ha talált motort.
  static Future<bool> rediscoverEngine() async {
    final probes = [
      for (var p = 8000; p < 8000 + portRange; p++)
        ApiClient(baseUrl: "http://127.0.0.1:$p")
            .isHealthy()
            .then((ok) => ok ? p : null)
    ];
    for (final p in await Future.wait(probes)) {
      if (p != null) {
        defaultBaseUrl = "http://127.0.0.1:$p";
        return true;
      }
    }
    return false;
  }

  /// Mélyebb öngyógyítás hálózati hibánál: előbb ÚJRA MEGKERESSÜK a
  /// motort a port-tartományban (elmozdulhatott), és ha SEHOL nem
  /// válaszol, ÚJRA IS INDÍTJUK a motor-indítón keresztül — a
  /// motor-folyamat el is halhatott (frissítés utáni fájlcsere, a gép
  /// altatása, belső hiba), olyankor a port-keresés önmagában kevés,
  /// és a felhasználót eddig csak a program teljes újraindítása
  /// mentette meg. Igaz, ha a végén válaszol a motor.
  static Future<bool> reviveEngine() async {
    if (await rediscoverEngine()) return true;
    final launcher = BackendLauncher.instance;
    if (launcher == null) return false; // web/teszt: nincs mit indítani
    launcher.stop(); // a félholt (élő, de nem válaszoló) példány elengedése
    final st = await launcher.ensureRunning();
    return st.phase == BackendPhase.ready;
  }

  /// A motor /health-ből olvasott verziója — a kliens a sajátjával
  /// összevetve veszi észre a FÉL-FRISSÜLT telepítést (új app + régi
  /// motor, vagy fordítva). Null, amíg nem válaszolt a motor, vagy ha
  /// régi motor fut, amelyik még nem adja ki.
  static String? engineVersion;

  /// A szerver EMBERI hibaüzenete a válaszból (FastAPI `detail`).
  ///
  /// A motor sok hibára pontos, magyar mondatot ad — például hogy a
  /// videó útvonalában ékezet van, és mit tegyen a felhasználó. Ez a
  /// kliensben eddig ELVESZETT: minden hiba "HTTP 400" alakban
  /// csapódott le, tehát a legjobb magyarázatunk sosem jutott el
  /// odáig, ahol elolvassák.
  ///
  /// Üres sztringet ad, ha a válaszban nincs használható magyarázat.
  static String serverDetail(http.Response r) {
    try {
      final j = jsonDecode(utf8.decode(r.bodyBytes));
      if (j is Map && j["detail"] is String) {
        final d = (j["detail"] as String).trim();
        // A FastAPI alap-üzenetei angol kulcsszavak (pl. "Not Found") —
        // azokat ne mutassuk emberi magyarázatként.
        if (d.isNotEmpty && d.length > 3) return d;
      }
    } catch (_) {}
    return "";
  }

  /// Hibaszöveg: a szerver magyarázata, ha van; különben a státuszkód.
  static String _hiba(String mit, http.Response r) {
    final d = serverDetail(r);
    return d.isEmpty ? "$mit: HTTP ${r.statusCode}" : d;
  }

  /// Életjel: igaz, ha a backend elérhető (GET /health).
  Future<bool> isHealthy() async {
    try {
      final resp = await http
          .get(Uri.parse("$baseUrl/health"))
          .timeout(const Duration(seconds: 2));
      if (resp.statusCode != 200) return false;
      try {
        final body = jsonDecode(utf8.decode(resp.bodyBytes));
        final v = body is Map ? body["version"] : null;
        if (v is String && v.isNotEmpty) engineVersion = v;
      } catch (_) {}
      return true;
    } catch (_) {
      return false; // nincs backend → a hívó a beágyazott demóra eshet vissza
    }
  }

  /// Demó meccs létrehozása a szerveren (videó nélkül) — az első kipróbáláshoz.
  /// Visszaadja az új match_id-t.
  Future<String> createDemoMatch({double seconds = 30}) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/matches/demo"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"seconds": seconds}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a demó létrehozása", resp));
    }
    return (jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>)["match_id"] as String;
  }

  /// A meccs támadásainak hozzárendelése a mentett figurákhoz
  /// (GET /matches/{id}/playbook-match): {total_attacks, matched, unmatched}.
  Future<Map<String, dynamic>> fetchPlaybookMatch(String matchId, String team) async {
    final uri = Uri.parse("$baseUrl/matches/$matchId/playbook-match")
        .replace(queryParameters: {"team": team});
    final resp = await http.get(uri);
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a figura-egyeztetés", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// A figura-könyvtár listája (id + név + játékos-szám).
  Future<List<Map<String, dynamic>>> listPlays() async {
    final resp = await http.get(Uri.parse("$baseUrl/playbook"))
        .timeout(const Duration(seconds: 4));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a figurákat", resp));
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return (json["plays"] as List).cast<Map<String, dynamic>>();
  }

  /// Egy mentett figura betöltése (attackers: játékosonként [[x,y],[x,y]]).
  Future<Map<String, dynamic>> fetchPlay(String playId) async {
    final resp = await http.get(Uri.parse("$baseUrl/playbook/$playId"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült betölteni a figurát", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Figura mentése a könyvtárba; visszaadja az azonosítót.
  Future<String> savePlay(String name, List<List<List<double>>> attackers) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/playbook"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"name": name, "attackers": attackers}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült menteni a figurát", resp));
    }
    return (jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>)["id"] as String;
  }

  /// Figura törlése a könyvtárból.
  Future<void> deletePlay(String playId) async {
    final resp = await http.delete(Uri.parse("$baseUrl/playbook/$playId"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült törölni a figurát", resp));
    }
  }

  /// A videóhoz ELMENTETT kalibrációk (GET /calibration) — üres lista, ha nincs.
  Future<List<Map<String, dynamic>>> fetchCalibration(String videoPath) async {
    final uri = Uri.parse("$baseUrl/calibration")
        .replace(queryParameters: {"path": videoPath});
    final resp = await http.get(uri).timeout(const Duration(seconds: 4));
    if (resp.statusCode != 200) return const [];
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return ((json["calibs"] as List?) ?? const [])
        .whereType<Map>()
        .map((m) => Map<String, dynamic>.from(m))
        .toList();
  }

  /// A gépen MÁR ELMENTETT kalibrációk, ÁTVÉTELRE (GET
  /// /calibration/saved). Aki darabokban vesz fel, hat klipet kap
  /// ugyanarról a rögzített kameráról — enélkül mind a hatot külön
  /// kellene bejelölni.
  ///
  /// [excludePath] a most szerkesztett videó: a saját kalibrációját ne
  /// kínáljuk fel átvételre. Hibánál üres lista — az átvétel kényelem,
  /// nem kapu.
  Future<List<Map<String, dynamic>>> fetchSavedCalibrations(
      {String? excludePath}) async {
    final uri = Uri.parse("$baseUrl/calibration/saved").replace(
        queryParameters:
            excludePath == null ? null : {"exclude_path": excludePath});
    try {
      final resp = await http.get(uri).timeout(const Duration(seconds: 4));
      if (resp.statusCode != 200) return const [];
      final json =
          jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
      return ((json["items"] as List?) ?? const [])
          .whereType<Map>()
          .map((m) => Map<String, dynamic>.from(m))
          .toList();
    } catch (_) {
      return const [];
    }
  }

  /// Kalibrációk mentése a videóhoz (POST /calibration) — újrafeldolgozásnál
  /// nem kell újra bejelölni.
  Future<void> saveCalibration(
      String videoPath, List<Map<String, dynamic>> calibs) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/calibration"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"path": videoPath, "calibs": calibs}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a kalibráció mentése", resp));
    }
  }

  /// Az edző figurájának szimulációja egy meccsből TANULT védelem ellen
  /// (POST /matches/{id}/simulate-setplay). A szerver a `defending` csapat
  /// védekezését tanulja meg a meccsből, és az ellen játssza le a figurát.
  /// Visszaadja a szimulált Tracking-et (Match-ként parse-olható "tracking").
  Future<Map<String, dynamic>> simulateSetplayVsMatch(
    String matchId, {
    required List<List<List<double>>> attackers,
    required List<int> ballCarrier,
    String defending = "away",
  }) async {
    final uri = Uri.parse("$baseUrl/matches/$matchId/simulate-setplay")
        .replace(queryParameters: {"defending": defending});
    final resp = await http.post(
      uri,
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"attackers": attackers, "ball_carrier": ballCarrier}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a szimuláció", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Játékos-statisztika CSV-ben (GET .../stats/export) — Excel-barát.
  Future<Uint8List> fetchStatsCsv(String matchId) async {
    final resp =
        await http.get(Uri.parse("$baseUrl/matches/$matchId/stats/export"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a statisztika-export", resp));
    }
    return resp.bodyBytes;
  }

  /// A meccs nyomtatható edzői jelentése HTML-ként (GET .../report/export).
  Future<Uint8List> fetchMatchReportExport(String matchId) async {
    final resp =
        await http.get(Uri.parse("$baseUrl/matches/$matchId/report/export"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a jelentés", resp));
    }
    return resp.bodyBytes;
  }

  /// Felcseréli a két csapatot a meccsben (POST /matches/{id}/swap-teams) —
  /// ha a csapatszín-felismerés fordítva találta el, melyik szín a hazai.
  Future<void> swapTeams(String matchId) async {
    final resp = await http.post(Uri.parse("$baseUrl/matches/$matchId/swap-teams"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a csapatok cseréje", resp));
    }
  }

  /// Több feldolgozott felvétel (pl. 1.+2. félidő) összefűzése egy meccsé
  /// (POST /matches/merge). Az [ids] sorrendje számít: időrendben add meg!
  /// Visszaadja az új meccs azonosítóját.
  Future<String> mergeMatches(List<String> ids,
      {String? matchId, String? homeTeam, String? awayTeam}) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/matches/merge"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({
        "ids": ids,
        if (matchId != null && matchId.isNotEmpty) "match_id": matchId,
        if (homeTeam != null) "home_team": homeTeam,
        if (awayTeam != null) "away_team": awayTeam,
      }),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült az összefűzés", resp));
    }
    final data = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return data["match_id"] as String;
  }

  /// Kulcsemberek (GET /matches/{id}/key-players): kinél dől el a meccs.
  /// Szezon-riport (GET /season/report): a csapat szezonja nyomtatható
  /// HTML-ként, bájtokban.
  Future<List<int>> fetchSeasonReport(String team) async {
    final resp = await http.get(Uri.parse(
        "$baseUrl/season/report?team=${Uri.encodeQueryComponent(team)}"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a szezon-riport", resp));
    }
    return resp.bodyBytes;
  }

  /// Egymás ellen riport (GET /head-to-head/report): a két csapat
  /// közös meccseinek mérlege nyomtatható HTML-ként, bájtokban.
  Future<List<int>> fetchHeadToHead(String teamA, String teamB) async {
    final resp = await http.get(Uri.parse(
        "$baseUrl/head-to-head/report"
        "?team_a=${Uri.encodeQueryComponent(teamA)}"
        "&team_b=${Uri.encodeQueryComponent(teamB)}"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült az egymás elleni riport", resp));
    }
    return resp.bodyBytes;
  }

  /// Szezon játékos-lap (GET /players/season-report): a játékos szezonja
  /// nyomtatható HTML-ként, bájtokban.
  Future<List<int>> fetchPlayerSeasonReport(String team, int jersey) async {
    final resp = await http.get(Uri.parse(
        "$baseUrl/players/season-report?team=${Uri.encodeQueryComponent(team)}"
        "&jersey=$jersey"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a szezon-lap", resp));
    }
    return resp.bodyBytes;
  }

  /// Játékos-lap (GET /matches/{id}/players/{track}/report): egy játékos
  /// meccs-riportja nyomtatható HTML-ként, bájtokban.
  Future<List<int>> fetchPlayerReport(String matchId, int trackId) async {
    final resp = await http.get(Uri.parse(
        "$baseUrl/matches/$matchId/players/$trackId/report"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a játékos-lap", resp));
    }
    return resp.bodyBytes;
  }

  /// Figura-felismerés (GET /matches/{id}/setplays): visszatérő
  /// támadás-minták + hatékonyság (efficiency) csapatonként.
  Future<Map<String, dynamic>> fetchSetplays(String matchId) async {
    final resp =
        await http.get(Uri.parse("$baseUrl/matches/$matchId/setplays"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a figura-elemzés", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Kulcs-pillanatok (GET /matches/{id}/key-moments): a meccs gerince
  /// időrendben — az app kattintható listájához.
  Future<List<dynamic>> fetchKeyMoments(String matchId) async {
    final resp =
        await http.get(Uri.parse("$baseUrl/matches/$matchId/key-moments"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a kulcs-pillanat lista", resp));
    }
    final json =
        jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return (json["moments"] as List?) ?? const [];
  }

  Future<Map<String, dynamic>> fetchKeyPlayers(String matchId) async {
    final resp =
        await http.get(Uri.parse("$baseUrl/matches/$matchId/key-players"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a kulcsember-lista", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// A feldolgozás minőség-jelentése (GET /matches/{id}/quality).
  Future<Map<String, dynamic>> fetchQuality(String matchId) async {
    final resp = await http.get(Uri.parse("$baseUrl/matches/$matchId/quality"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a minőség-jelentés", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// A meccshez felvitt kiállítások (roster) lekérése.
  Future<Map<String, dynamic>> fetchRoster(String matchId) async {
    final resp = await http.get(Uri.parse("$baseUrl/matches/$matchId/roster"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a kiállításokat", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Kiállítások mentése → a backend újraszámolja a képen kívüli becslést.
  /// suspensions elemei: {"team": "home"|"away", "start_s": mp, "duration_s": mp}.
  Future<Map<String, dynamic>> saveRoster(
      String matchId, List<Map<String, dynamic>> suspensions) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/matches/$matchId/roster"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"suspensions": suspensions}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült menteni a kiállításokat", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// A meccs felismert eseményei (passz/lövés/gól/labdaeladás) időrendben —
  /// az Események-panel ebből épül, kattintásra a lejátszó az eseményre ugrik.
  Future<List<Map<String, dynamic>>> fetchEvents(String matchId) async {
    final resp = await http.get(Uri.parse("$baseUrl/matches/$matchId/events"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni az eseményeket", resp));
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return (json["events"] as List).cast<Map<String, dynamic>>();
  }

  /// Játékos-fáradás (GET /matches/{id}/team-stats → "player_fatigue"):
  /// track_id → 2. félidei tempó-esés (%). Üres, ha nem mérhető.
  Future<Map<int, double>> fetchPlayerFatigue(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/team-stats"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) return const {};
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    final rows = (json["player_fatigue"] as List?) ?? const [];
    final out = <int, double>{};
    for (final r in rows.cast<Map<String, dynamic>>()) {
      final id = (r["track_id"] as num?)?.toInt();
      final drop = (r["drop_pct"] as num?)?.toDouble();
      if (id != null && drop != null) out[id] = drop;
    }
    return out;
  }

  /// Csapat-összegzés nyersen (GET /matches/{id}/team-stats) — az élő
  /// nézet a félidei rotáció-képet (rotation_fh) olvassa belőle.
  Future<Map<String, dynamic>> fetchTeamStats(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/team-stats"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) return const {};
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Lövés-sebességek (GET /matches/{id}/events → "shot_speeds"):
  /// csapatonkénti átlag/max km/h + a meccs leggyorsabb lövése.
  Future<Map<String, dynamic>> fetchShotSpeeds(String matchId) async {
    final resp = await http.get(Uri.parse("$baseUrl/matches/$matchId/events"));
    if (resp.statusCode != 200) return const {};
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return (json["shot_speeds"] as Map?)?.cast<String, dynamic>() ?? const {};
  }

  /// Videóklip-export indítása (POST /matches/{id}/clips/export) — job_id-t ad.
  /// Kihez köthető jelenet ezen a meccsen — mezszám szerint, a
  /// jelenetek darabszámával. A klip-válogatás ebből tudja felkínálni
  /// a MŰKÖDŐ mezszámokat (a kiosztatlan szám némán üres zip-et adna).
  /// A nyers válasz: {"players": [...], "totals": {típus: db},
  /// "max_clips": N}. A `totals` és a plafon a BECSLÉSHEZ kell — a
  /// vágás percekbe telik, és a rossz kijelölés csak a végén derülne
  /// ki.
  Future<Map<String, dynamic>> fetchClipPlayers(String matchId) async {
    final resp =
        await http.get(Uri.parse("$baseUrl/matches/$matchId/clip-players"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("A játékos-lista nem érhető el", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// [jerseys] megadásával a csomag EGY (vagy néhány) játékos
  /// jeleneteire szűkül — a játékos saját válogatása.
  Future<String> startClipExport(String matchId, List<String> types,
      {List<int> jerseys = const []}) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/matches/$matchId/clips/export"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"types": types, "jerseys": jerseys}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem indult el a klipvágás", resp));
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return json["job_id"] as String;
  }

  /// A kész klip-csomag (zip) letöltése bájtokként.
  Future<List<int>> fetchClipsZip(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/clips/download"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a klipek letöltése", resp));
    }
    return resp.bodyBytes;
  }

  /// A teljes meccskönyvtár letöltése zip-ként (GET /library/export).
  Future<List<int>> exportLibrary() async {
    final resp = await http.get(Uri.parse("$baseUrl/library/export"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a könyvtár mentése", resp));
    }
    return resp.bodyBytes;
  }

  /// Meccskönyvtár visszaállítása zip-ből (POST /library/import).
  Future<Map<String, dynamic>> importLibrary(List<int> zipBytes) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/library/import"),
      headers: {"Content-Type": "application/zip"},
      body: zipBytes,
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a könyvtár visszaállítása", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Egy játékos fejlődése meccsről meccsre, mezszám alapján
  /// (GET /players/trend?team=...&jersey=...).
  Future<Map<String, dynamic>> fetchPlayerTrend(
      String team, int jersey) async {
    final uri = Uri.parse("$baseUrl/players/trend").replace(
        queryParameters: {"team": team, "jersey": "$jersey"});
    final resp = await http.get(uri);
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a játékos-fejlődés lekérése", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Egy játékos SZEZON-szintű edzés-fókusza (GET /players/focus):
  /// mit gyakoroljon. Ugyanaz, ami a nyomtatható szezon-lap "Mit
  /// gyakorolj" szakaszában áll — a count azt mondja meg, hány meccsen
  /// jött elő ugyanaz.
  Future<List<Map<String, dynamic>>> fetchPlayerFocus(
      String team, int jersey) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/players/focus"
            "?team=${Uri.encodeQueryComponent(team)}&jersey=$jersey"))
        .timeout(const Duration(seconds: 30));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a fókuszt", resp));
    }
    final data =
        jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return ((data["focus"] as List?) ?? const [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
  }

  /// Mezszám hozzárendelése egy játékoshoz (POST /matches/{id}/jerseys).
  /// jersey = null törli a hozzárendelést.
  Future<void> setJersey(String matchId, int trackId, int? jersey) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/matches/$matchId/jerseys"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"track_id": trackId, "jersey": jersey}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a mezszám mentése", resp));
    }
  }

  /// Meccs-csomag készítése (POST /matches/{id}/package/export) — job_id.
  Future<String> startPackageExport(
      String matchId, List<String> clipTypes) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/matches/$matchId/package/export"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"clip_types": clipTypes}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem indult el a csomag-készítés", resp));
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return json["job_id"] as String;
  }

  /// A kész meccs-csomag (zip) letöltése bájtokként.
  Future<List<int>> fetchPackageZip(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/package/download"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a csomag letöltése", resp));
    }
    return resp.bodyBytes;
  }

  /// A meccshez felvitt KÉZI esemény-javítások
  /// (GET /matches/{id}/event-overrides).
  Future<List<Map<String, dynamic>>> fetchEventOverrides(
      String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/event-overrides"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a javításokat", resp));
    }
    final data =
        jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return ((data["overrides"] as List?) ?? const [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
  }

  /// A kézi esemény-javítások mentése (POST /matches/{id}/event-overrides)
  /// — a TELJES lista cseréje. A javítás a lövés-felismerésbe épül be,
  /// tehát minden rétegen átüt (eredmény, xG, lövő-listák, felderítés).
  Future<List<Map<String, dynamic>>> saveEventOverrides(
      String matchId, List<Map<String, dynamic>> overrides) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/matches/$matchId/event-overrides"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"overrides": overrides}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült menteni a javítást", resp));
    }
    final data =
        jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return ((data["overrides"] as List?) ?? const [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
  }

  /// Edzői jegyzetek a meccshez (GET /matches/{id}/notes) — idő szerint.
  Future<List<Map<String, dynamic>>> fetchNotes(String matchId) async {
    final resp = await http.get(Uri.parse("$baseUrl/matches/$matchId/notes"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a jegyzeteket", resp));
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return (json["notes"] as List).cast<Map<String, dynamic>>();
  }

  /// MINDEN edzői jegyzet a könyvtárból (GET /library/notes), meccs-
  /// környezettel: {"match_id", "home_team", "away_team", "date", "id",
  /// "frame", "t_s", "text"}. A jegyzetek az edző fejében egyetlen
  /// listát alkotnak, meccsektől függetlenül.
  Future<List<Map<String, dynamic>>> fetchLibraryNotes() async {
    final resp = await http
        .get(Uri.parse("$baseUrl/library/notes"))
        .timeout(const Duration(seconds: 20));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a jegyzeteket", resp));
    }
    final data =
        jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return ((data["notes"] as List?) ?? const [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
  }

  /// Új edzői jegyzet az adott képkockához (POST /matches/{id}/notes).
  Future<Map<String, dynamic>> addNote(
      String matchId, int frame, String text) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/matches/$matchId/notes"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"frame": frame, "text": text}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült menteni a jegyzetet", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Jegyzet törlése (DELETE /matches/{id}/notes/{noteId}).
  Future<void> deleteNote(String matchId, String noteId) async {
    final resp = await http
        .delete(Uri.parse("$baseUrl/matches/$matchId/notes/$noteId"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült törölni a jegyzetet", resp));
    }
  }

  /// Ellenfél-felderítő jelentés egy csapatról EGY meccsből (GET .../scouting).
  Future<Map<String, dynamic>> fetchScouting(String matchId, String team) async {
    final uri = Uri.parse("$baseUrl/matches/$matchId/scouting")
        .replace(queryParameters: {"team": team});
    final resp = await http.get(uri);
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a felderítés", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// TÖBB meccsből egyesített felderítés (POST /scouting). Az items elemei:
  /// {"match_id": ..., "team": "home"|"away"} — meccsenként megadva, melyik
  /// oldalon játszott a felderített csapat.
  Future<Map<String, dynamic>> fetchCombinedScouting(
      List<Map<String, String>> items) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/scouting"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"items": items}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült az egyesített felderítés", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Fejlődés-követés: két időszak (meccs-csoport) összevetése (POST /scouting/trend).
  Future<Map<String, dynamic>> fetchTrend(
      List<Map<String, String>> older, List<Map<String, String>> newer) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/scouting/trend"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"older": {"items": older}, "newer": {"items": newer}}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a fejlődés-elemzés", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Fejlődés-riport nyomtatható HTML-je (POST /scouting/trend/export).
  Future<List<int>> fetchTrendExport(
      List<Map<String, String>> older,
      List<Map<String, String>> newer) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/scouting/trend/export"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode(
          {"older": {"items": older}, "newer": {"items": newer}}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a fejlődés-riport", resp));
    }
    return resp.bodyBytes;
  }

  /// Meccsterv-illesztés (POST /scouting/matchup): a saját és az
  /// ellenfél-profil keresztezéséből páros-specifikus tanácsok.
  Future<List<String>> fetchMatchupPlan(
      List<Map<String, dynamic>> ownItems,
      List<Map<String, dynamic>> oppItems) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/scouting/matchup"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({
        "own": {"items": ownItems},
        "opp": {"items": oppItems},
      }),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a meccsterv", resp));
    }
    final data = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return ((data["plan"] as List?) ?? const []).cast<String>();
  }

  /// A meccsterv TELJES válasza (POST /scouting/matchup): a "plan"
  /// mondatok mellett a "style" stílus-távolság is (tükör-meccs vagy
  /// ellentétes stílus, tengelyekre bontva).
  Future<Map<String, dynamic>> fetchMatchup(
      List<Map<String, dynamic>> ownItems,
      List<Map<String, dynamic>> oppItems) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/scouting/matchup"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({
        "own": {"items": ownItems},
        "opp": {"items": oppItems},
      }),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a meccsterv", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// A MECCSTERV nyomtatható lapja (POST /scouting/export): az
  /// ellenfél felderítése + a páros-specifikus meccsterv szakasz.
  ///
  /// A tükrözős változattól (fetchCombinedScoutingExport) az különíti
  /// el, hogy itt a SAJÁT oldal a saját csapat saját meccseiből jön —
  /// nem abból a feltevésből, hogy mi voltunk az ellenfelük.
  Future<Uint8List> fetchMatchupExport(
      List<Map<String, dynamic>> ownItems,
      List<Map<String, dynamic>> oppItems) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/scouting/export"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({
        "items": oppItems,
        "own": {"items": ownItems},
      }),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a meccsterv-lap", resp));
    }
    return resp.bodyBytes;
  }

  /// Az egyesített felderítés nyomtatható HTML-je (POST /scouting/export).
  Future<Uint8List> fetchCombinedScoutingExport(
      List<Map<String, String>> items) async {
    // A saját oldal a tükrözött items — ebből épül a nyomtatott
    // jelentés Meccsterv szakasza (mint a képernyő MECCSTERV kártyája).
    final own = [
      for (final it in items)
        {
          "match_id": it["match_id"],
          "team": (it["team"] == "home") ? "away" : "home",
        }
    ];
    final resp = await http.post(
      Uri.parse("$baseUrl/scouting/export"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({
        "items": items,
        "own": {"items": own},
      }),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült az export", resp));
    }
    return resp.bodyBytes;
  }

  /// A felderítő jelentés nyomtatható HTML-je bájtokban (GET .../scouting/export).
  /// A kliens fájlba menti; a böngészőből Ctrl+P → PDF.
  Future<Uint8List> fetchScoutingExport(String matchId, String team) async {
    final uri = Uri.parse("$baseUrl/matches/$matchId/scouting/export")
        .replace(queryParameters: {"team": team});
    final resp = await http.get(uri);
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült az export", resp));
    }
    return resp.bodyBytes;
  }

  /// A tárolt meccsek listája (könyvtár/áttekintő nézethez). Minden elem összegző
  /// szótár: match_id, home_team, away_team, num_frames, fps, duration_s.
  Future<List<Map<String, dynamic>>> listMatches() async {
    // Türelmes betöltés: az app indulásakor a beépített motor még
    // bootolhat (első indításnál a rendszer át is vizsgálja — akár egy
    // perc). Kapcsolat-hibánál ezért nem azonnal hibázunk, hanem
    // másodpercenként újrapróbáljuk, és közben a motor-indító által
    // frissített alapértelmezett címet is figyeljük (tartalék port).
    final deadline = DateTime.now().add(const Duration(seconds: 75));
    Object? lastError;
    while (true) {
      for (final base in {baseUrl, ApiClient.defaultBaseUrl}) {
        try {
          final resp = await http.get(Uri.parse("$base/matches"))
              .timeout(const Duration(seconds: 4));
          if (resp.statusCode != 200) {
            throw Exception(_hiba("Nem sikerült lekérni a meccslistát", resp));
          }
          final json =
              jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
          return (json["matches"] as List).cast<Map<String, dynamic>>();
        } on SocketException catch (e) {
          lastError = e;
        } on http.ClientException catch (e) {
          lastError = e;
        }
      }
      if (DateTime.now().isAfter(deadline)) {
        throw Exception(
            "A motor (elemző szolgáltatás) nem válaszol. Ha az app most "
            "indult, várj egy percet és próbáld újra — első indításkor a "
            "rendszer átvizsgálja a motort. Ha nem jön helyre, nézd meg a "
            "naplót: Library/Application Support/SportMachine/"
            "engine-app.log (Windowson: AppData/Local/SportMachine). "
            "Részlet: $lastError");
      }
      await Future.delayed(const Duration(seconds: 1));
    }
  }

  /// ÚJRA-feldolgozás a mentett beállításokkal
  /// (POST /matches/{id}/reprocess) — hibás futás után egy kattintás.
  Future<Map<String, dynamic>> reprocessMatch(String matchId) async {
    final resp = await http
        .post(Uri.parse("$baseUrl/matches/$matchId/reprocess"))
        .timeout(const Duration(seconds: 10));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült az újra-feldolgozás", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// RÉSZLEGES meccs feldolgozásának folytatása (POST /matches/{id}/resume):
  /// a mentett beállításokkal új feldolgozás indul onnan, ahol megszakadt.
  /// Visszatérés: {"job_id", "match_id"} — az új (folytatás-) meccsé.
  Future<Map<String, dynamic>> resumeMatch(String matchId) async {
    final resp = await http
        .post(Uri.parse("$baseUrl/matches/$matchId/resume"))
        .timeout(const Duration(seconds: 10));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a folytatás", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// TV-közvetítés elő-elemzése (GET /broadcast/segments): vágások +
  /// totál/közeli szakaszok, és hogy "közvetítésnek látszik-e".
  Future<Map<String, dynamic>> fetchBroadcastSegments(String path,
      {int stride = 5}) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/broadcast/segments").replace(
            queryParameters: {"path": path, "stride": "$stride"}))
        .timeout(const Duration(seconds: 120));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a közvetítés-elemzés", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Több nézet egyesítése (POST /matches/fuse): két külön feldolgozott,
  /// közös pályára kalibrált meccsből egy fúziós meccs. Az órajel-
  /// eltolást a backend a labda-pályából becsüli (auto_sync).
  Future<Map<String, dynamic>> fuseMatches(List<String> matchIds,
      {String? newId, bool autoSync = true}) async {
    final resp = await http
        .post(Uri.parse("$baseUrl/matches/fuse"),
            headers: {"Content-Type": "application/json"},
            body: jsonEncode({
              "match_ids": matchIds,
              if (newId != null) "match_id": newId,
              "auto_sync": autoSync,
            }))
        .timeout(const Duration(seconds: 60));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a nézet-egyesítés", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Pályavonal-jelöltek egy képkockából (GET /broadcast/lines):
  /// vonalak + sarok-jelöltek + javasolt kalibrációs négyszög.
  ///
  /// `lineColor`: a KÖVETENDŐ vonalszín. Több sportot kiszolgáló
  /// csarnokban a kézilabda-pálya vonala gyakran nem fehér, hanem piros
  /// (mellette a kosár/futsal kék-zöld vonalai) — az "auto" a képből
  /// dönti el, melyiket kövesse, és a válasz "line_color" mezője
  /// megmondja, mire jutott. Kézi felülbírálás: "feher", "piros",
  /// "kek", "zold", "sarga".
  Future<Map<String, dynamic>> fetchBroadcastLines(String path,
      {int frame = 0, String lineColor = "auto"}) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/broadcast/lines").replace(
            queryParameters: {
              "path": path,
              "frame": "$frame",
              "line_color": lineColor,
            }))
        .timeout(const Duration(seconds: 60));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a vonal-felismerés", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Egy-képkockás detektálás-próba (GET /detect-preview): a YOLO által
  /// talált játékosok/labda berajzolva + darabszámok — az indítás előtti
  /// gyors ellenőrzéshez. Az első hívás lassabb (modell-betöltés).
  Future<Map<String, dynamic>> fetchDetectPreview(String path,
      {int t = 100,
      List<List<int>>? calib,
      String region = "full",
      bool rotate = false}) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/detect-preview").replace(queryParameters: {
      "path": path,
      "t": "$t",
      // Kalibrációval a backend a pálya-modellt is a képre rajzolja,
      // és megszámolja, hány játékos esik a játéktérre méterben.
      if (calib != null) "calib": jsonEncode(calib),
      if (calib != null) "region": region,
      if (calib != null) "rotate": "$rotate",
    }))
        .timeout(const Duration(seconds: 90));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a detektálás-próba", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Gól-sorozatok (GET /matches/{id}/momentum): válasz nélküli szériák
  /// a felismert gólokból, a pillanatnyi állással.
  Future<List<Map<String, dynamic>>> fetchMomentum(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/momentum"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a sorozatokat", resp));
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return (json["runs"] as List).cast<Map<String, dynamic>>();
  }

  /// Vezetés-alakulás (GET /matches/{id}/momentum → "progression"):
  /// legnagyobb előny, vezetés-váltások, vezetett idő.
  Future<Map<String, dynamic>> fetchProgression(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/momentum"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni az állás-menetet", resp));
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    final prog = (json["progression"] as Map?)?.cast<String, dynamic>() ?? {};
    // A hajrá-mérleg és a gólcsend ugyanennek a válasznak a mezői — az
    // összefoglaló felirata együtt jeleníti meg az állás-menettel.
    final clutch = (json["clutch"] as Map?)?.cast<String, dynamic>();
    if (clutch != null) prog["clutch"] = clutch;
    final droughts = (json["droughts"] as Map?)?.cast<String, dynamic>();
    if (droughts != null) prog["droughts"] = droughts;
    final halftime = (json["halftime"] as Map?)?.cast<String, dynamic>();
    if (halftime != null) prog["halftime"] = halftime;
    final winProb = (json["win_prob"] as Map?)?.cast<String, dynamic>();
    if (winProb != null) prog["win_prob"] = winProb;
    return prog;
  }

  /// Gól-idővonal (GET /matches/{id}/momentum → "timeline"): dobott/kapott
  /// gólok idő-vödrönként.
  Future<List<Map<String, dynamic>>> fetchScoringTimeline(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/momentum"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) return const [];
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    final tl = (json["timeline"] as Map?)?.cast<String, dynamic>();
    return ((tl?["buckets"] as List?) ?? const [])
        .cast<Map<String, dynamic>>();
  }

  /// Helyzetminőség (GET /matches/{id}/xg): lövésenkénti xG + csapat-
  /// összegzés (várható gól vs tényleges).
  Future<Map<String, dynamic>> fetchXg(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/xg"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a helyzetminőséget", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Cserehullámok (GET /matches/{id}/substitutions): ki-be lépések a
  /// cserezónán át + a cserék utáni 90 mp mérlege.
  Future<Map<String, dynamic>> fetchSubstitutions(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/substitutions"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a cseréket", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Visszatérő edzés-fókuszok a teljes könyvtárból
  /// (GET /library/training-focus): ami legalább két meccsen előjött.
  Future<Map<String, dynamic>> fetchLibraryTrainingFocus() async {
    final resp = await http
        .get(Uri.parse("$baseUrl/library/training-focus"))
        .timeout(const Duration(seconds: 20));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a szezon-fókuszt", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// A csapat EGYÉNI edzés-terve (GET /library/training-focus/players)
  /// — a nyomtatható lap képernyős párja, ugyanabból a számolásból.
  Future<List<Map<String, dynamic>>> fetchTeamPlayerPlan(
      String team) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/library/training-focus/players"
            "?team=${Uri.encodeQueryComponent(team)}"))
        .timeout(const Duration(seconds: 120));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült az egyéni edzés-terv", resp));
    }
    final data =
        jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return ((data["players"] as List?) ?? const [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
  }

  /// A heti EDZÉSTERV nyomtatható HTML-je egy csapatra
  /// (GET /library/training-focus/export) — a pályán nincs képernyő.
  Future<List<int>> fetchTrainingPlanExport(String team) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/library/training-focus/export"
            "?team=${Uri.encodeQueryComponent(team)}"))
        .timeout(const Duration(seconds: 120));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült az edzésterv-lap", resp));
    }
    return resp.bodyBytes;
  }

  /// Edzés-fókusz javaslatok (GET /matches/{id}/training): csapatonként
  /// rangsorolt gyakorlás-fókuszok (terület, fókusz, indok, gyakorlat).
  Future<Map<String, dynamic>> fetchTraining(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/training"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni az edzés-fókuszt", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Játékmegszakítások (GET /matches/{id}/stoppages): időkérés-szerű
  /// tartós leállások a valószínű kérő csapattal.
  Future<List<Map<String, dynamic>>> fetchStoppages(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/stoppages"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a megszakításokat", resp));
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return (json["stoppages"] as List).cast<Map<String, dynamic>>();
  }

  /// Védekezés-elemzés (GET /matches/{id}/defense): kapott lövések —
  /// szabadon hagyott lövők, zóna-lyukak, kapott xG.
  Future<Map<String, dynamic>> fetchDefense(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/defense"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a védekezés-elemzést", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// 7 a 6 elleni (üres kapus) szakaszok (GET /matches/{id}/empty-net).
  Future<List<Map<String, dynamic>>> fetchEmptyNet(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/empty-net"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a 7a6-szakaszokat", resp));
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return (json["windows"] as List).cast<Map<String, dynamic>>();
  }

  /// Szabály-értő réteg (GET /matches/{id}/rules): emberhátrány-szakaszok,
  /// emberelőny-hatékonyság, hétméteresek, passzív-játék kockázat.
  Future<Map<String, dynamic>> fetchRules(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/rules"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a szabály-elemzést", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Támadás-szakaszok típus-címkével + csapatonkénti támadás-mix
  /// (GET /matches/{id}/attacks): {"attacks": [...], "mix": {...},
  /// "efficiency": {...}}.
  Future<Map<String, dynamic>> fetchAttacks(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/attacks"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a támadásokat", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Automatikus edzői összefoglaló (GET /matches/{id}/coach-summary):
  /// {"sections": [{"title","body"}...], "highlights": [...]} magyarul.
  Future<Map<String, dynamic>> fetchCoachSummary(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/coach-summary"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni az összefoglalót", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Szezon-toplisták (GET /library/leaders): gól/blokk/szerzés/védés
  /// vezérei a teljes könyvtárból, mezszám alapján összegezve.
  Future<Map<String, dynamic>> fetchLibraryLeaders() async {
    final resp = await http.get(Uri.parse("$baseUrl/library/leaders"))
        .timeout(const Duration(seconds: 12));
    if (resp.statusCode != 200) return const {};
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Keret-lap (GET /library/roster?team=...): a csapat ÖSSZES ismert
  /// mezszáma egy táblában — meccs-darabszámmal és szezon-összegekkel.
  /// A toplisták az öt legjobbat adják, ez MINDENKIT, aki mezszámmal
  /// szerepel a könyvtárban.
  /// A keret-lap CSV-ben (GET /library/roster.csv) — a vezetőségi
  /// kimutatáshoz. Nyers bájtok: a hívó menti fájlba.
  Future<List<int>> fetchTeamRosterCsv(String team) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/library/roster.csv"
            "?team=${Uri.encodeQueryComponent(team)}"))
        .timeout(const Duration(seconds: 30));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült a szezon-CSV", resp));
    }
    return resp.bodyBytes;
  }

  Future<Map<String, dynamic>> fetchTeamRoster(String team) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/library/roster"
            "?team=${Uri.encodeQueryComponent(team)}"))
        .timeout(const Duration(seconds: 30));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a keretet", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Játékos-név hozzárendelése egy csapat mezszámához
  /// (POST /library/players). ÜRES név törli a hozzárendelést.
  /// A név csapat-szintű (nem meccsenkénti): a mezszám a szezonban
  /// stabil, a track-azonosító nem.
  Future<void> setPlayerName(String team, int jersey, String name) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/library/players"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"team": team, "jersey": jersey, "name": name}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült menteni a nevet", resp));
    }
  }

  /// Szezon-összkép a kezdőlapnak (GET /library/summary): összesített
  /// mutatók (meccsek, játékidő, gólok, táv, sprintek) + meccsenkénti
  /// kivonat a "per_match" kulcs alatt.
  Future<Map<String, dynamic>> fetchLibrarySummary() async {
    final resp = await http.get(Uri.parse("$baseUrl/library/summary"))
        .timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni az összképet", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Átírja a meccs csapatneveit (PATCH /matches/{id}) — a könyvtár és a
  /// felderítő jelentés is az új neveket mutatja; lemezre is mentődik.
  Future<void> updateMatchNames(String matchId,
      {String? homeTeam, String? awayTeam, String? date}) async {
    final body = <String, dynamic>{
      if (homeTeam != null) "home_team": homeTeam,
      if (awayTeam != null) "away_team": awayTeam,
      // date: "" = a dátum törlése; null = nem nyúlunk hozzá.
      if (date != null) "date": date,
    };
    final resp = await http.patch(
      Uri.parse("$baseUrl/matches/$matchId"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode(body),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült átnevezni", resp));
    }
  }

  /// Töröl egy meccset a backendről (memória + lemez).
  Future<void> deleteMatch(String matchId) async {
    final resp = await http.delete(Uri.parse("$baseUrl/matches/$matchId"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült törölni", resp));
    }
  }

  /// Lekéri egy meccs Tracking-jét és Match objektummá alakítja.
  Future<Match> fetchMatch(String matchId) async {
    final resp = await http.get(Uri.parse("$baseUrl/matches/$matchId"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a meccset", resp));
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return Match.fromJson(json);
  }

  /// Feltölti a videót a backendre a LEMEZRŐL STREAM-elve (POST /upload) — a
  /// fájlt darabonként küldi, így egy több GB-os videó sem tölti be a memóriába.
  /// Visszaadja a backend-oldali mentett utat: {"path", "filename", "size"}.
  /// `onProgress`: 0..1 feltöltési arány (a felület folyamatjelzőjéhez).
  Future<Map<String, dynamic>> uploadVideoFromPath(
    String localPath,
    String filename, {
    void Function(double)? onProgress,
  }) async {
    final file = File(localPath);
    final total = await file.length();
    final uri = Uri.parse("$baseUrl/upload").replace(queryParameters: {"filename": filename});
    final req = http.StreamedRequest("POST", uri);
    req.headers["Content-Type"] = "application/octet-stream";
    req.contentLength = total;
    int sent = 0;
    file.openRead().listen(
      (chunk) {
        req.sink.add(chunk);
        sent += chunk.length;
        if (total > 0) onProgress?.call(sent / total);
      },
      onDone: () => req.sink.close(),
      onError: (Object e) => req.sink.addError(e),
      cancelOnError: true,
    );
    final resp = await http.Response.fromStream(await req.send());
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Feltöltés sikertelen", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Feltöltés MEMÓRIÁBAN lévő bájtokból (pl. weben, ahol nincs fájl-út).
  Future<Map<String, dynamic>> uploadVideoBytes(Uint8List bytes, String filename) async {
    final uri = Uri.parse("$baseUrl/upload").replace(queryParameters: {"filename": filename});
    final resp = await http.post(
      uri,
      headers: {"Content-Type": "application/octet-stream"},
      body: bytes,
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Feltöltés sikertelen", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Elindítja egy videó feldolgozását a backenden (POST /matches/process).
  /// A `path` a backend-oldali videó út; `calib` a 4 sarok képpont-koordinátája.
  /// Visszaadja: {"job_id": ..., "match_id": ...}. A haladást a fetchJob() adja.
  Future<Map<String, dynamic>> startProcessing(
    String path, {
    String? weights,
    int stride = 3,
    int max = 0, // 0 = a TELJES videó (éles meccsnél ez kell)
    int imgsz = 1280,
    int start = 0,
    List<List<int>>? calib,
    String? calibRegion, // "full" | "left" | "right" (térfél-kalibráció)
    bool calibRotate = false, // 180°-os forgatás (túloldali kamera)
    // TÖBB kalibráció (pl. külön bal és jobb térfél, akár külön képkockán):
    // [{"corners": [[x,y],...], "region": ..., "rotate": ..., "frame": ...}].
    List<Map<String, dynamic>>? calibs,
    String? matchId,
    String? homeTeam,
    String? awayTeam,
    bool jerseyOcr = false, // KÍSÉRLETI: mezszám-OCR a feldolgozás alatt
    // Ha épp FUT egy másik feldolgozás: true = ez megvárja a végét,
    // false (alap) = azonnal indul, a futót a szerver félreteszi (az
    // addig feldolgozott része elmentve marad, később folytatható).
    bool queueBehind = false,
    // KÉZI meccs-ablak másodpercben: hol kezdődik és hol ér véget a
    // MECCS a felvételen. A feltöltött videóban rendszerint benne van a
    // bemelegítés és a csapatbemutatás; ezekből a felismerő lövést és
    // eladott labdát csinálna. Ha meg van adva, felülír minden
    // automatikus meccs-ablak-felismerést.
    double? startS,
    double? endS,
    // HOSSZ-korlát MÁSODPERCBEN ("Próba ~2 perc", "Félidő ~35 perc").
    // A `max` kockában ugyanezt mondja, de a kliens csak 25 fps-sel tud
    // számolni — egy 30 fps-es telefonvideón a "35 perc" valójában 29
    // perc lenne. A motor a VALÓDI fps-sel váltja át; a `max` marad a
    // tartalék, ha az fps nem olvasható ki.
    double? maxS,
    // KÖTEG-CSOPORT: az egy meccshez tartozó darabok közös jele +
    // a darab sorszáma és a csoport teljes darabszáma. Ha minden darab
    // elkészült, a motor magától fűzi össze őket.
    String? mergeGroup,
    int mergeOrder = 0,
    int mergeTotal = 0,
  }) async {
    final body = <String, dynamic>{
      "path": path,
      "stride": stride,
      "max": max,
      "imgsz": imgsz,
      "start": start,
      if (startS != null) "start_s": startS,
      if (endS != null) "end_s": endS,
      if (maxS != null) "max_s": maxS,
      if (weights != null) "weights": weights,
      if (calib != null) "calib": calib,
      if (calib != null && calibRegion != null) "calib_region": calibRegion,
      if (calib != null) "calib_rotate": calibRotate,
      if (calibs != null && calibs.isNotEmpty) "calibs": calibs,
      if (matchId != null) "match_id": matchId,
      if (homeTeam != null && homeTeam.isNotEmpty) "home_team": homeTeam,
      if (awayTeam != null && awayTeam.isNotEmpty) "away_team": awayTeam,
      if (jerseyOcr) "jersey_ocr": true,
      if (queueBehind) "queue_behind": true,
      if (mergeGroup != null) ...{
        "merge_group": mergeGroup,
        "merge_order": mergeOrder,
        "merge_total": mergeTotal,
      },
    };
    final resp = await http.post(
      Uri.parse("$baseUrl/matches/process"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode(body),
    );
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült elindítani a feldolgozást", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Lekéri egy feldolgozási munka állapotát (GET /jobs/{id}):
  /// {status, stage, progress, message, match_id, error}.
  Future<Map<String, dynamic>> fetchJob(String jobId) async {
    final resp = await http.get(Uri.parse("$baseUrl/jobs/$jobId"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a munka állapotát", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Indítás ELŐTTI ellenőrzés egy videóra (POST /preflight): van-e elég
  /// hely, és a gép eddigi ütemét ismerve kb. meddig fog tartani.
  ///
  /// Hibánál üres térkép: az ellenőrzés kényelem, nem kapu — a
  /// feldolgozás indítását nem akadályozhatja meg egy megbicsakló
  /// kérés. (A tényleges hely-elutasítás a motorban van.)
  Future<Map<String, dynamic>> fetchPreflight(String path,
      {int? stride, int? imgsz, double? startS, double? endS,
      double? maxS}) async {
    try {
      final resp = await http
          .post(Uri.parse("$baseUrl/preflight"),
              headers: {"Content-Type": "application/json"},
              body: jsonEncode({
                "path": path,
                // A MOST választott minőségi profil: a becslés csak az
                // ugyanilyen beállítású korábbi futásokból számol (a
                // "Pontos" többszörös időt kér ugyanarra a videóra).
                if (stride != null) "stride": stride,
                if (imgsz != null) "imgsz": imgsz,
                // A meccs időablaka: a becslés a FELDOLGOZANDÓ szakaszra
                // szóljon, ne a teljes videóra.
                if (startS != null) "start_s": startS,
                if (endS != null) "end_s": endS,
                // A hossz-korlát is: a "Próba (~2 p)" becslése két
                // percre szóljon, ne a teljes videóra.
                if (maxS != null) "max_s": maxS,
              }))
          .timeout(const Duration(seconds: 8));
      if (resp.statusCode != 200) return const {};
      return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    } catch (_) {
      return const {};
    }
  }

  /// A feldolgozási munkák listája (GET /jobs) — legújabb elöl. A kezdőlap
  /// "folyamatban" kártyája ebből épül; hibánál üres listát adunk.
  /// A lezárt feldolgozások naplója (GET /jobs/history) — újraindítás
  /// után is megvan; hibánál üres lista.
  Future<List<Map<String, dynamic>>> fetchJobHistory({int limit = 10}) async {
    try {
      final resp = await http
          .get(Uri.parse("$baseUrl/jobs/history")
              .replace(queryParameters: {"limit": "$limit"}))
          .timeout(const Duration(seconds: 4));
      if (resp.statusCode != 200) return const [];
      final json =
          jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
      return ((json["jobs"] as List?) ?? const [])
          .whereType<Map>()
          .map((m) => Map<String, dynamic>.from(m))
          .toList();
    } catch (_) {
      return const [];
    }
  }

  /// Teljes rendszer-ellenőrzés (GET /health/full) — telepítés-
  /// diagnosztika: csomagok, modell, írási jog, tárhely, kodek.
  Future<Map<String, dynamic>> fetchHealthFull() async {
    final resp = await http
        .get(Uri.parse("$baseUrl/health/full"))
        .timeout(const Duration(seconds: 15));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült az ellenőrzés", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  Future<List<Map<String, dynamic>>> fetchJobs() async {
    try {
      final resp = await http
          .get(Uri.parse("$baseUrl/jobs"))
          .timeout(const Duration(seconds: 4));
      if (resp.statusCode != 200) return const [];
      final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
      return ((json["jobs"] as List?) ?? const [])
          .whereType<Map>()
          .map((m) => Map<String, dynamic>.from(m))
          .toList();
    } catch (_) {
      return const [];
    }
  }

  /// Megszakít egy futó feldolgozást (POST /jobs/{id}/cancel). A leállás nem
  /// azonnali: a feldolgozó a következő képkockánál veszi észre (másodpercek).
  Future<Map<String, dynamic>> cancelJob(String jobId) async {
    final resp = await http.post(Uri.parse("$baseUrl/jobs/$jobId/cancel"));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült megszakítani", resp));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  // --- Fiókok és felhasználási feltételek --------------------------------
  // A program a Tulajdonos szellemi és fizikai tulajdona; a használat
  // fiókhoz kötött, a fiók létrehozásához a feltételek elfogadása kell. A
  // munkamenet-kulcsot a SessionStore tartja (services/session_store.dart).

  Map<String, String> _authHeaders() {
    final t = SessionStore.token;
    return {
      "Content-Type": "application/json",
      if (t != null) "Authorization": "Bearer $t",
    };
  }

  /// A szerver magyar hibaüzenete, ha van — különben a HTTP-kód.
  String _errorText(http.Response resp, String fallback) {
    try {
      final body = jsonDecode(utf8.decode(resp.bodyBytes));
      if (body is Map && body["detail"] is String) {
        return body["detail"] as String;
      }
    } catch (_) {}
    return "$fallback (HTTP ${resp.statusCode})";
  }

  /// A felhasználási feltételek szövege és verziója (GET /legal/terms).
  Future<Map<String, dynamic>> fetchTerms() async {
    final resp = await http
        .get(Uri.parse("$baseUrl/legal/terms"))
        .timeout(const Duration(seconds: 5));
    if (resp.statusCode != 200) {
      throw Exception(_errorText(resp, "Nem sikerült lekérni a feltételeket"));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Van-e már fiók a gépen (GET /accounts/status).
  Future<Map<String, dynamic>> fetchAccountsStatus() async {
    final resp = await http
        .get(Uri.parse("$baseUrl/accounts/status"))
        .timeout(const Duration(seconds: 5));
    if (resp.statusCode != 200) {
      throw Exception(
          _errorText(resp, "Nem sikerült lekérni a fiók-állapotot"));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Fiók létrehozása (POST /accounts/register). A feltételek elfogadása
  /// KÖTELEZŐ — `acceptTerms: false` esetén a szerver elutasítja. Sikernél
  /// eltárolja a munkamenet-kulcsot, és visszaadja a fiókot.
  Future<Map<String, dynamic>> registerAccount({
    required String email,
    required String password,
    String name = "",
    String team = "",
    required bool acceptTerms,
  }) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/accounts/register"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({
        "email": email,
        "password": password,
        "name": name,
        "team": team,
        "accept_terms": acceptTerms,
      }),
    );
    if (resp.statusCode != 200) {
      throw Exception(_errorText(resp, "Nem sikerült a fiók létrehozása"));
    }
    final json =
        jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    await SessionStore.setToken(json["token"] as String?);
    return Map<String, dynamic>.from(json["account"] as Map);
  }

  /// Belépés (POST /accounts/login) — sikernél eltárolja a kulcsot.
  Future<Map<String, dynamic>> loginAccount(
      String email, String password) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/accounts/login"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"email": email, "password": password}),
    );
    if (resp.statusCode != 200) {
      throw Exception(_errorText(resp, "Nem sikerült a belépés"));
    }
    final json =
        jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    await SessionStore.setToken(json["token"] as String?);
    return Map<String, dynamic>.from(json["account"] as Map);
  }

  /// A belépett fiók (GET /accounts/me) — null, ha nincs érvényes kulcs.
  Future<Map<String, dynamic>?> fetchMe() async {
    if (SessionStore.token == null) return null;
    try {
      final resp = await http
          .get(Uri.parse("$baseUrl/accounts/me"), headers: _authHeaders())
          .timeout(const Duration(seconds: 5));
      if (resp.statusCode != 200) return null;
      return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  /// A megújult feltételek elfogadása (POST /accounts/accept-terms).
  Future<Map<String, dynamic>> acceptTerms() async {
    final resp = await http.post(
      Uri.parse("$baseUrl/accounts/accept-terms"),
      headers: _authHeaders(),
      body: jsonEncode({"token": SessionStore.token}),
    );
    if (resp.statusCode != 200) {
      throw Exception(
          _errorText(resp, "Nem sikerült elfogadni a feltételeket"));
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Kilépés (POST /accounts/logout) — a kulcs a szerveren és itt is elszáll.
  Future<void> logoutAccount() async {
    try {
      await http
          .post(Uri.parse("$baseUrl/accounts/logout"),
              headers: _authHeaders(),
              body: jsonEncode({"token": SessionStore.token}))
          .timeout(const Duration(seconds: 5));
    } catch (_) {
      // A motor már nem válaszol — a helyi kulcsot akkor is eldobjuk.
    }
    await SessionStore.clear();
  }

  /// Jelszócsere (POST /accounts/change-password) — új kulcsot ad, a
  /// korábbi munkamenetek érvénytelenné válnak.
  Future<Map<String, dynamic>> changePassword(
      String oldPassword, String newPassword) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/accounts/change-password"),
      headers: _authHeaders(),
      body: jsonEncode({
        "token": SessionStore.token,
        "old_password": oldPassword,
        "new_password": newPassword,
      }),
    );
    if (resp.statusCode != 200) {
      throw Exception(_errorText(resp, "Nem sikerült a jelszócsere"));
    }
    final json =
        jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    await SessionStore.setToken(json["token"] as String?);
    return Map<String, dynamic>.from(json["account"] as Map);
  }

  /// A kalibráló képernyő referencia-képkockájának URL-je (GET /reference-frame).
  /// A backend a `videoPath` videó `t`-edik képkockáját adja vissza PNG-ként.
  Uri referenceFrameUri(String videoPath, {int t = 100}) =>
      Uri.parse("$baseUrl/reference-frame")
          .replace(queryParameters: {"path": videoPath, "t": "$t"});

  /// Letölti a referencia-képkockát (PNG bájtok). A kalibráló képernyő ezt
  /// rajzolja a húzható sarkok alá; hiba esetén a hívó a helyőrzőre esik vissza.
  Future<Uint8List> fetchReferenceFrame(String videoPath, {int t = 100}) async {
    final resp = await http.get(referenceFrameUri(videoPath, t: t));
    if (resp.statusCode != 200) {
      throw Exception(_hiba("Nem sikerült lekérni a képkockát", resp));
    }
    return resp.bodyBytes;
  }
}
