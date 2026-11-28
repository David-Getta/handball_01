// A Döntések panel játékos-modellje: a motor helyzet-profilját (GET
// /matches/{id}/players/{pid}/decisions) helyzetenként, színes sávval és
// a szorított döntésekkel rajzolja. A teszt egy hamis motorral fut — a
// válasz alakja ugyanaz, mint a backend tests/test_player_decisions_api.py
// által őrzött végponté.
import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:handball_client/models/tracking.dart";
import "package:handball_client/services/api_client.dart";
import "package:handball_client/ui/decisions_panel.dart";

class _FakeApi extends ApiClient {
  final Map<String, dynamic>? valasz;
  final List<int> kert = [];
  _FakeApi(this.valasz) : super(baseUrl: "http://127.0.0.1:9");

  @override
  Future<Map<String, dynamic>> fetchPlayerDecisions(
      String matchId, int playerId) async {
    kert.add(playerId);
    if (valasz == null) throw Exception("a motor nem válaszolt");
    return valasz!;
  }
}

/// Két hazai játékos: az 1-es a 2-esnek passzol (így az 1-es választható).
Match _meccs() {
  Map<String, dynamic> pl(int id, double x, double y) => {
        "track_id": id, "team": "home", "x": x, "y": y,
        "source": "measured", "confidence": 1.0,
      };
  Map<String, dynamic> frame(int t, double bx, double by) => {
        "t": t,
        "players": [pl(1, 22.0, 10.0), pl(2, 35.0, 10.0)],
        "ball": {"x": bx, "y": by, "confidence": 1.0},
      };
  return Match.fromJson({
    "meta": {"match_id": "dp", "home_team": "A", "away_team": "B",
             "fps": 25.0},
    "frames": [frame(0, 22.0, 10.0), frame(1, 22.0, 10.0),
               frame(2, 35.0, 10.0)],
  });
}

Future<void> _rajzol(WidgetTester tester, ApiClient? api) async {
  await tester.binding.setSurfaceSize(const Size(500, 1400));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(MaterialApp(
      home: Scaffold(
          body: DecisionsPanel(
              key: UniqueKey(), match: _meccs(), api: api))));
  await tester.pump(const Duration(milliseconds: 50));
  await tester.pump(const Duration(seconds: 2));
}

void main() {
  testWidgets("a helyzet-profil helyzetenként és szorítva is látszik",
      (tester) async {
    final api = _FakeApi({
      "situations": {
        "kilépnek rá": {"decisions": 10, "actions": {"visszajátszás": 10},
                        "match": 0},
        "szabad lőhely": {"decisions": 3, "actions": {"lövés": 3},
                          "match": 3},
      },
      "pressure": {"press": 10, "press_best": 0, "team_free_pct": 75.0},
    });
    await _rajzol(tester, api);
    expect(api.kert, [1]);
    expect(find.text("HELYZETENKÉNT"), findsOneWidget);
    expect(find.text("Ha kilépnek rá"), findsOneWidget);
    expect(find.text("10 döntés · legjobb: 0/10"), findsOneWidget);
    // A motor SIT_MIN-je alatt nincs szokás, csak eset.
    expect(find.text("3 döntés · legjobb: 3/3 · kevés minta"),
        findsOneWidget);
    expect(find.textContaining("10 döntéséből 0 volt a legjobb"),
        findsOneWidget);
    expect(find.textContaining("75% az arány"), findsOneWidget);
  });

  testWidgets("motor nélkül magyarázó sor, hibánál nem érhető el",
      (tester) async {
    await _rajzol(tester, null);
    expect(find.textContaining("az elemző motor számolja"), findsOneWidget);
    await _rajzol(tester, _FakeApi(null));
    expect(find.textContaining("most nem érhető el"), findsOneWidget);
  });
}
