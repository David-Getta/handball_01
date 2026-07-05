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

  ApiClient({this.baseUrl = "http://localhost:8000"});

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
    int max = 400,
    int start = 0,
    List<List<int>>? calib,
    String? matchId,
  }) async {
    final body = <String, dynamic>{
      "path": path,
      "stride": stride,
      "max": max,
      "start": start,
      if (weights != null) "weights": weights,
      if (calib != null) "calib": calib,
      if (matchId != null) "match_id": matchId,
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
