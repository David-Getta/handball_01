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

class ApiClient {
  /// A backend alap-URL-je. Lokális teszthez a laptopon ez a localhost.
  final String baseUrl;

  /// Az alapértelmezett cím — a motor-indító ÁTÁLLÍTJA, ha a motor tartalék
  /// porton indult (a 8000-es foglalt volt). Az ezután létrejövő kliensek
  /// automatikusan a jó címet használják.
  static String defaultBaseUrl = "http://127.0.0.1:8000";

  ApiClient({String? baseUrl}) : baseUrl = baseUrl ?? defaultBaseUrl;

  /// Életjel: igaz, ha a backend elérhető (GET /health).
  Future<bool> isHealthy() async {
    try {
      final resp = await http
          .get(Uri.parse("$baseUrl/health"))
          .timeout(const Duration(seconds: 2));
      return resp.statusCode == 200;
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
      throw Exception("Nem sikerült a demó létrehozása: HTTP ${resp.statusCode}");
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
      throw Exception("Nem sikerült a figura-egyeztetés: HTTP ${resp.statusCode}");
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// A figura-könyvtár listája (id + név + játékos-szám).
  Future<List<Map<String, dynamic>>> listPlays() async {
    final resp = await http.get(Uri.parse("$baseUrl/playbook"))
        .timeout(const Duration(seconds: 4));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült lekérni a figurákat: HTTP ${resp.statusCode}");
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return (json["plays"] as List).cast<Map<String, dynamic>>();
  }

  /// Egy mentett figura betöltése (attackers: játékosonként [[x,y],[x,y]]).
  Future<Map<String, dynamic>> fetchPlay(String playId) async {
    final resp = await http.get(Uri.parse("$baseUrl/playbook/$playId"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült betölteni a figurát: HTTP ${resp.statusCode}");
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
      throw Exception("Nem sikerült menteni a figurát: HTTP ${resp.statusCode}");
    }
    return (jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>)["id"] as String;
  }

  /// Figura törlése a könyvtárból.
  Future<void> deletePlay(String playId) async {
    final resp = await http.delete(Uri.parse("$baseUrl/playbook/$playId"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült törölni a figurát: HTTP ${resp.statusCode}");
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
      throw Exception("Nem sikerült a kalibráció mentése: HTTP ${resp.statusCode}");
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
      throw Exception("Nem sikerült a szimuláció: HTTP ${resp.statusCode}");
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Játékos-statisztika CSV-ben (GET .../stats/export) — Excel-barát.
  Future<Uint8List> fetchStatsCsv(String matchId) async {
    final resp =
        await http.get(Uri.parse("$baseUrl/matches/$matchId/stats/export"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült a statisztika-export: HTTP ${resp.statusCode}");
    }
    return resp.bodyBytes;
  }

  /// A meccs nyomtatható edzői jelentése HTML-ként (GET .../report/export).
  Future<Uint8List> fetchMatchReportExport(String matchId) async {
    final resp =
        await http.get(Uri.parse("$baseUrl/matches/$matchId/report/export"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült a jelentés: HTTP ${resp.statusCode}");
    }
    return resp.bodyBytes;
  }

  /// Felcseréli a két csapatot a meccsben (POST /matches/{id}/swap-teams) —
  /// ha a csapatszín-felismerés fordítva találta el, melyik szín a hazai.
  Future<void> swapTeams(String matchId) async {
    final resp = await http.post(Uri.parse("$baseUrl/matches/$matchId/swap-teams"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült a csapatok cseréje: HTTP ${resp.statusCode}");
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
      throw Exception("Nem sikerült az összefűzés: HTTP ${resp.statusCode}");
    }
    final data = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return data["match_id"] as String;
  }

  /// A feldolgozás minőség-jelentése (GET /matches/{id}/quality).
  Future<Map<String, dynamic>> fetchQuality(String matchId) async {
    final resp = await http.get(Uri.parse("$baseUrl/matches/$matchId/quality"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült a minőség-jelentés: HTTP ${resp.statusCode}");
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// A meccshez felvitt kiállítások (roster) lekérése.
  Future<Map<String, dynamic>> fetchRoster(String matchId) async {
    final resp = await http.get(Uri.parse("$baseUrl/matches/$matchId/roster"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült lekérni a kiállításokat: HTTP ${resp.statusCode}");
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
      throw Exception("Nem sikerült menteni a kiállításokat: HTTP ${resp.statusCode}");
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// A meccs felismert eseményei (passz/lövés/gól/labdaeladás) időrendben —
  /// az Események-panel ebből épül, kattintásra a lejátszó az eseményre ugrik.
  Future<List<Map<String, dynamic>>> fetchEvents(String matchId) async {
    final resp = await http.get(Uri.parse("$baseUrl/matches/$matchId/events"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült lekérni az eseményeket: HTTP ${resp.statusCode}");
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return (json["events"] as List).cast<Map<String, dynamic>>();
  }

  /// Videóklip-export indítása (POST /matches/{id}/clips/export) — job_id-t ad.
  Future<String> startClipExport(String matchId, List<String> types) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/matches/$matchId/clips/export"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"types": types}),
    );
    if (resp.statusCode != 200) {
      throw Exception("Nem indult el a klipvágás: HTTP ${resp.statusCode}");
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return json["job_id"] as String;
  }

  /// Egy job állapota (GET /jobs/{id}) — a klipvágás haladásához.
  Future<Map<String, dynamic>> fetchJob(String jobId) async {
    final resp = await http.get(Uri.parse("$baseUrl/jobs/$jobId"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült a job lekérése: HTTP ${resp.statusCode}");
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// A kész klip-csomag (zip) letöltése bájtokként.
  Future<List<int>> fetchClipsZip(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/clips/download"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült a klipek letöltése: HTTP ${resp.statusCode}");
    }
    return resp.bodyBytes;
  }

  /// A teljes meccskönyvtár letöltése zip-ként (GET /library/export).
  Future<List<int>> exportLibrary() async {
    final resp = await http.get(Uri.parse("$baseUrl/library/export"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült a könyvtár mentése: HTTP ${resp.statusCode}");
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
      throw Exception(
          "Nem sikerült a könyvtár visszaállítása: HTTP ${resp.statusCode}");
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
      throw Exception(
          "Nem sikerült a játékos-fejlődés lekérése: HTTP ${resp.statusCode}");
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
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
      throw Exception("Nem sikerült a mezszám mentése: HTTP ${resp.statusCode}");
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
      throw Exception("Nem indult el a csomag-készítés: HTTP ${resp.statusCode}");
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return json["job_id"] as String;
  }

  /// A kész meccs-csomag (zip) letöltése bájtokként.
  Future<List<int>> fetchPackageZip(String matchId) async {
    final resp = await http
        .get(Uri.parse("$baseUrl/matches/$matchId/package/download"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült a csomag letöltése: HTTP ${resp.statusCode}");
    }
    return resp.bodyBytes;
  }

  /// Edzői jegyzetek a meccshez (GET /matches/{id}/notes) — idő szerint.
  Future<List<Map<String, dynamic>>> fetchNotes(String matchId) async {
    final resp = await http.get(Uri.parse("$baseUrl/matches/$matchId/notes"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült lekérni a jegyzeteket: HTTP ${resp.statusCode}");
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return (json["notes"] as List).cast<Map<String, dynamic>>();
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
      throw Exception("Nem sikerült menteni a jegyzetet: HTTP ${resp.statusCode}");
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Jegyzet törlése (DELETE /matches/{id}/notes/{noteId}).
  Future<void> deleteNote(String matchId, String noteId) async {
    final resp = await http
        .delete(Uri.parse("$baseUrl/matches/$matchId/notes/$noteId"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült törölni a jegyzetet: HTTP ${resp.statusCode}");
    }
  }

  /// Ellenfél-felderítő jelentés egy csapatról EGY meccsből (GET .../scouting).
  Future<Map<String, dynamic>> fetchScouting(String matchId, String team) async {
    final uri = Uri.parse("$baseUrl/matches/$matchId/scouting")
        .replace(queryParameters: {"team": team});
    final resp = await http.get(uri);
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült a felderítés: HTTP ${resp.statusCode}");
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
      throw Exception("Nem sikerült az egyesített felderítés: HTTP ${resp.statusCode}");
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
      throw Exception("Nem sikerült a fejlődés-elemzés: HTTP ${resp.statusCode}");
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Az egyesített felderítés nyomtatható HTML-je (POST /scouting/export).
  Future<Uint8List> fetchCombinedScoutingExport(
      List<Map<String, String>> items) async {
    final resp = await http.post(
      Uri.parse("$baseUrl/scouting/export"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"items": items}),
    );
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült az export: HTTP ${resp.statusCode}");
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
      throw Exception("Nem sikerült az export: HTTP ${resp.statusCode}");
    }
    return resp.bodyBytes;
  }

  /// A tárolt meccsek listája (könyvtár/áttekintő nézethez). Minden elem összegző
  /// szótár: match_id, home_team, away_team, num_frames, fps, duration_s.
  Future<List<Map<String, dynamic>>> listMatches() async {
    final resp = await http.get(Uri.parse("$baseUrl/matches"))
        .timeout(const Duration(seconds: 4));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült lekérni a meccslistát: HTTP ${resp.statusCode}");
    }
    final json = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return (json["matches"] as List).cast<Map<String, dynamic>>();
  }

  /// Átírja a meccs csapatneveit (PATCH /matches/{id}) — a könyvtár és a
  /// felderítő jelentés is az új neveket mutatja; lemezre is mentődik.
  Future<void> updateMatchNames(String matchId,
      {String? homeTeam, String? awayTeam}) async {
    final body = <String, dynamic>{
      if (homeTeam != null) "home_team": homeTeam,
      if (awayTeam != null) "away_team": awayTeam,
    };
    final resp = await http.patch(
      Uri.parse("$baseUrl/matches/$matchId"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode(body),
    );
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült átnevezni: HTTP ${resp.statusCode}");
    }
  }

  /// Töröl egy meccset a backendről (memória + lemez).
  Future<void> deleteMatch(String matchId) async {
    final resp = await http.delete(Uri.parse("$baseUrl/matches/$matchId"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült törölni: HTTP ${resp.statusCode}");
    }
  }

  /// Lekéri egy meccs Tracking-jét és Match objektummá alakítja.
  Future<Match> fetchMatch(String matchId) async {
    final resp = await http.get(Uri.parse("$baseUrl/matches/$matchId"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült lekérni a meccset: HTTP ${resp.statusCode}");
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
      throw Exception("Feltöltés sikertelen: HTTP ${resp.statusCode}");
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
      throw Exception("Feltöltés sikertelen: HTTP ${resp.statusCode}");
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
  }) async {
    final body = <String, dynamic>{
      "path": path,
      "stride": stride,
      "max": max,
      "imgsz": imgsz,
      "start": start,
      if (weights != null) "weights": weights,
      if (calib != null) "calib": calib,
      if (calib != null && calibRegion != null) "calib_region": calibRegion,
      if (calib != null) "calib_rotate": calibRotate,
      if (calibs != null && calibs.isNotEmpty) "calibs": calibs,
      if (matchId != null) "match_id": matchId,
      if (homeTeam != null && homeTeam.isNotEmpty) "home_team": homeTeam,
      if (awayTeam != null && awayTeam.isNotEmpty) "away_team": awayTeam,
      if (jerseyOcr) "jersey_ocr": true,
    };
    final resp = await http.post(
      Uri.parse("$baseUrl/matches/process"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode(body),
    );
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült elindítani a feldolgozást: HTTP ${resp.statusCode}");
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// Lekéri egy feldolgozási munka állapotát (GET /jobs/{id}):
  /// {status, stage, progress, message, match_id, error}.
  Future<Map<String, dynamic>> fetchJob(String jobId) async {
    final resp = await http.get(Uri.parse("$baseUrl/jobs/$jobId"));
    if (resp.statusCode != 200) {
      throw Exception("Nem sikerült lekérni a munka állapotát: HTTP ${resp.statusCode}");
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// A feldolgozási munkák listája (GET /jobs) — legújabb elöl. A kezdőlap
  /// "folyamatban" kártyája ebből épül; hibánál üres listát adunk.
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
      throw Exception("Nem sikerült megszakítani: HTTP ${resp.statusCode}");
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
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
      throw Exception("Nem sikerült lekérni a képkockát: HTTP ${resp.statusCode}");
    }
    return resp.bodyBytes;
  }
}
