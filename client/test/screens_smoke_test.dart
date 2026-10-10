// Füstteszt: minden paraméter nélkül nyitható képernyő megnyílik BACKEND
// NÉLKÜL (a kérések bukása után hiba- vagy üres-állapottal), két
// ablakméretben, hiba nélkül. A Flutter a túlcsordulást ("RenderFlex
// overflowed") is hibaként jelenti — az eszköz-panelnél épp egy ilyen
// elrendezési hiba maradt rejtve, mert annak a képernyőnek a többi
// képernyőhöz hasonlóan nem volt tesztje.
import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:handball_client/services/jobs_monitor.dart";
import "package:handball_client/ui/bootstrap_screen.dart";
import "package:handball_client/ui/calibration_screen.dart";
import "package:handball_client/ui/clips_screen.dart";
import "package:handball_client/ui/dashboard_screen.dart";
import "package:handball_client/ui/jobs_screen.dart";
import "package:handball_client/ui/label_screen.dart";
import "package:handball_client/ui/live_screen.dart";
import "package:handball_client/ui/match_screen.dart";
import "package:handball_client/ui/matchup_screen.dart";
import "package:handball_client/ui/notes_screen.dart";
import "package:handball_client/ui/player_trend_screen.dart";
import "package:handball_client/ui/roster_screen.dart";
import "package:handball_client/ui/scouting_picker_screen.dart";
import "package:handball_client/ui/scouting_screen.dart";
import "package:handball_client/ui/season_screen.dart";
import "package:handball_client/ui/team_trend_screen.dart";
import "package:handball_client/ui/terms_screen.dart";
import "package:handball_client/ui/training_plan_screen.dart";
import "package:handball_client/ui/upload_screen.dart";

final Map<String, Widget Function()> _kepernyok = {
  "Bootstrap": () => const BootstrapScreen(),
  "Calibration": () => const CalibrationScreen(),
  "Clips": () => const ClipsScreen(),
  "Dashboard": () => const DashboardScreen(),
  "Jobs": () => const JobsScreen(),
  "Label": () => const LabelScreen(),
  "Live": () => const LiveScreen(),
  "Match": () => const MatchScreen(),
  "Matchup": () => const MatchupScreen(),
  "Notes": () => const NotesScreen(),
  "PlayerTrend": () => const PlayerTrendScreen(),
  "Roster": () => const RosterScreen(),
  "ScoutingPicker": () => const ScoutingPickerScreen(),
  "Scouting": () => const ScoutingScreen(),
  "Season": () => const SeasonScreen(),
  "TeamTrend": () => const TeamTrendScreen(),
  "Terms": () => const TermsScreen(),
  "TrainingPlan": () => const TrainingPlanScreen(),
  "Upload": () => const UploadScreen(),
};

Future<void> _zar(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  JobsMonitor.instance.stop();
  await tester.pump(const Duration(minutes: 3));
  JobsMonitor.instance.stop();
}

void main() {
  for (final meret in const [Size(1400, 900), Size(900, 700), Size(700, 600)]) {
    for (final e in _kepernyok.entries) {
      testWidgets(
          "${e.key} megnyílik backend nélkül "
          "(${meret.width.toInt()}×${meret.height.toInt()})", (tester) async {
        tester.view.physicalSize = meret;
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.reset);
        await tester.pumpWidget(MaterialApp(home: e.value()));
        // A kérések a tesztben azonnal buknak; néhány kör a hiba- és az
        // üres-állapotig.
        for (var i = 0; i < 20; i++) {
          await tester.pump(const Duration(milliseconds: 100));
        }
        expect(tester.takeException(), isNull, reason: e.key);
        await _zar(tester);
      });
    }
  }
}
