/// Felderítés-választó — az "Ellenfél-felderítés" menüpont belépője.
///
/// A felderítéshez meccs + csapat kell; ez a képernyő a könyvtárból
/// kínálja fel őket: meccsenként egy sor, rajta a két csapat gombja —
/// arra koppintasz, AMELYIKET felderítenéd. Több meccs kijelölésével
/// EGYESÍTETT jelentés készül (több meccs = pontosabb kép).
library;

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "scouting_screen.dart";
import "shell/app_shell.dart";

class ScoutingPickerScreen extends StatefulWidget {
  const ScoutingPickerScreen({super.key});

  @override
  State<ScoutingPickerScreen> createState() => _ScoutingPickerScreenState();
}

class _ScoutingPickerScreenState extends State<ScoutingPickerScreen> {
  final ApiClient _api = ApiClient();
  List<Map<String, dynamic>> _matches = [];
  bool _loading = true;
  String? _error;
  // Egyesített módhoz: a kijelölt (match_id, team) párok.
  final List<Map<String, String>> _selected = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final ms = await _api.listMatches();
      if (!mounted) return;
      setState(() {
        _matches = ms;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = "A meccs-könyvtár nem érhető el: $e";
        _loading = false;
      });
    }
  }

  void _openSingle(Map<String, dynamic> m, String team) {
    Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => ScoutingScreen(
              matchId: m["match_id"] as String,
              homeName: (m["home_team"] as String?) ?? "Hazai",
              awayName: (m["away_team"] as String?) ?? "Vendég",
              team: team,
            )));
  }

  void _toggleSelect(Map<String, dynamic> m, String team) {
    final id = m["match_id"] as String;
    setState(() {
      final existing = _selected.indexWhere((e) => e["match_id"] == id);
      if (existing >= 0 && _selected[existing]["team"] == team) {
        _selected.removeAt(existing); // ugyanaz még egyszer = kivétel
      } else if (existing >= 0) {
        _selected[existing] = {"match_id": id, "team": team};
      } else {
        _selected.add({"match_id": id, "team": team});
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.scouting,
      crumbPath: "ELEMZÉS · ELLENFÉL-FELDERÍTÉS",
      child: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text("Ellenfél-felderítés", style: AppText.title),
              const SizedBox(height: 4),
              Text("válaszd ki, KIT derítesz fel: koppints a csapat nevére "
                  "— hosszan nyomva több meccset jelölhetsz ki egyesített "
                  "jelentéshez",
                  style: AppText.subtitle),
              const SizedBox(height: AppSpacing.lg),
              if (_error != null)
                Text(_error!,
                    style: AppText.label.copyWith(color: AppColors.away)),
              if (_error == null && _matches.isEmpty)
                Text("Még nincs elemzett meccs — előbb dolgozz fel egy "
                    "videót az Új elemzés menüben.",
                    style: AppText.label),
              Expanded(
                child: ListView.separated(
                  itemCount: _matches.length,
                  separatorBuilder: (_, __) =>
                      const SizedBox(height: AppSpacing.sm),
                  itemBuilder: (_, i) => _row(_matches[i]),
                ),
              ),
              if (_selected.length >= 2)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.md),
                  child: FilledButton.icon(
                    onPressed: () {
                      Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) => ScoutingScreen(
                              items: List.of(_selected))));
                    },
                    icon: const Icon(Icons.merge_type, size: 18),
                    label: Text(
                        "Egyesített felderítés (${_selected.length} meccs)"),
                  ),
                ),
            ]),
    );
  }

  Widget _row(Map<String, dynamic> m) {
    final id = m["match_id"] as String;
    final home = (m["home_team"] as String?) ?? "Hazai";
    final away = (m["away_team"] as String?) ?? "Vendég";
    final date = (m["date"] as String?) ?? "";
    String? selectedTeam;
    for (final e in _selected) {
      if (e["match_id"] == id) selectedTeam = e["team"];
    }
    Widget teamButton(String team, String name, Color color) {
      final selected = selectedTeam == team;
      return Expanded(
        child: GestureDetector(
          onLongPress: () => _toggleSelect(m, team),
          child: OutlinedButton(
            onPressed: () => _openSingle(m, team),
            style: OutlinedButton.styleFrom(
              side: BorderSide(
                  color: selected ? AppColors.gold : AppColors.border,
                  width: selected ? 2 : 1),
              backgroundColor:
                  selected ? AppColors.gold.withOpacity(0.12) : null,
            ),
            child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
              Container(width: 8, height: 8, decoration: BoxDecoration(
                  color: color, shape: BoxShape.circle)),
              const SizedBox(width: 6),
              Flexible(child: Text(name,
                  overflow: TextOverflow.ellipsis,
                  style: AppText.value.copyWith(fontSize: 13))),
            ]),
          ),
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: AppTheme.card(),
      child: Row(children: [
        Expanded(
          flex: 2,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text("$home vs $away",
                    overflow: TextOverflow.ellipsis,
                    style: AppText.value),
                if (date.isNotEmpty)
                  Text(date, style: AppText.label.copyWith(fontSize: 11)),
              ]),
        ),
        const SizedBox(width: AppSpacing.md),
        teamButton("home", home, AppColors.home),
        const SizedBox(width: AppSpacing.sm),
        teamButton("away", away, AppColors.away),
      ]),
    );
  }
}
