/// A lokális backend REST API kliense.
///
/// LOKÁLIS MÓD: a backend (Python/FastAPI) ugyanazon a laptopon fut, a kliens a
/// localhost-on éri el (lásd docs/ARCHITECTURE.md). Alapból http://localhost:8000.
/// Végpontok: GET /matches/{id} (Tracking JSON), GET /matches/{id}/stats.
library;

import "dart:convert";
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
}
