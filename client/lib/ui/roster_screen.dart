/// Keret — a csapat MINDEN mezszáma egy táblában, saját menüponttal.
///
/// A szezon-toplisták az öt legjobbat adják. A játékos viszont nem a
/// gólkirályt keresi, hanem a SAJÁT sorát; az edző pedig a teljes
/// keretet nézi végig, nem a kiugró neveket. Erre eddig nem volt hely
/// a felületen: a mezszám-alapú összegek megvoltak a motorban, de csak
/// a top 5 jutott ki belőlük.
///
/// A tábla rendezhető (koppints az oszlopfejre), és egy sorra koppintva
/// a játékos fejlődés-görbéje nyílik — előre kitöltve, nem üres űrlap.
///
/// A "meccs" oszlop szándékosan az első szám: enélkül egy alacsony
/// gólszám félrevezet — kevés játék vagy gyenge forma? Két külön
/// kérdés, két külön teendő.
library;

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "error_text.dart";
import "player_trend_screen.dart";
import "shell/app_shell.dart";
import "waiting.dart";

/// A tábla oszlopai: a válasz kulcsa és a fejléc-felirat.
const List<(String, String)> kRosterColumns = [
  ("matches", "Meccs"),
  ("goals", "Gól"),
  ("assists", "Gólpassz"),
  ("blocks", "Blokk"),
  ("steals", "Szerzés"),
  ("saves", "Védés"),
];

class RosterScreen extends StatefulWidget {
  const RosterScreen({super.key});

  @override
  State<RosterScreen> createState() => _RosterScreenState();
}

class _RosterScreenState extends State<RosterScreen> {
  final ApiClient _api = ApiClient();

  bool _loading = true;
  bool _rowsLoading = false;
  String? _error;
  List<String> _teams = [];
  String? _team;
  List<Map<String, dynamic>> _players = [];
  String _note = "";

  /// Rendezés: melyik oszlop szerint, és csökkenő-e. A mezszám az
  /// alapértelmezés (a keret-lap "névsora"), az teljesítmény-semleges.
  String _sortKey = "jersey";
  bool _desc = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final ms = await _api.listMatches();
      if (!mounted) return;
      final names = <String>{};
      for (final m in ms) {
        for (final k in const ["home_team", "away_team"]) {
          final n = m[k] as String?;
          if (n != null && n.isNotEmpty) names.add(n);
        }
      }
      final sorted = names.toList()..sort();
      setState(() {
        _teams = sorted;
        _team = sorted.isNotEmpty ? sorted.first : null;
        _loading = false;
      });
      if (_team != null) _loadRoster();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = "A meccs-könyvtár nem érhető el: ${humanError(e)}";
        _loading = false;
      });
    }
  }

  Future<void> _loadRoster() async {
    final team = _team;
    if (team == null) return;
    setState(() {
      _rowsLoading = true;
      _error = null;
    });
    try {
      final r = await _api.fetchTeamRoster(team);
      if (!mounted) return;
      setState(() {
        _players = [
          for (final p in (r["players"] as List? ?? []))
            Map<String, dynamic>.from(p as Map)
        ];
        _note = (r["note"] as String?) ?? "";
        _rowsLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _rowsLoading = false;
        _error = "A keret nem érhető el: ${humanError(e)}";
      });
    }
  }

  List<Map<String, dynamic>> get _sorted {
    final rows = List<Map<String, dynamic>>.of(_players);
    rows.sort((a, b) {
      final x = (a[_sortKey] as num?) ?? 0;
      final y = (b[_sortKey] as num?) ?? 0;
      final c = x.compareTo(y);
      return _desc ? -c : c;
    });
    return rows;
  }

  void _sortBy(String key) {
    setState(() {
      if (_sortKey == key) {
        _desc = !_desc;
      } else {
        _sortKey = key;
        // Teljesítmény-oszlopnál a nagy szám érdekes elöl; a mezszám
        // viszont névsor-szerű, ott a növekvő a természetes.
        _desc = key != "jersey";
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.roster,
      crumbPath: "CSAPAT · KERET",
      child: _loading
          ? const WaitingView("Meccs-könyvtár olvasása…",
              icon: Icons.groups_outlined)
          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text("Keret", style: AppText.title),
              const SizedBox(height: 4),
              Text(
                  "a csapat minden mezszáma egy táblában — koppints egy "
                  "sorra a játékos fejlődés-görbéjéhez",
                  style: AppText.subtitle),
              const SizedBox(height: AppSpacing.lg),
              if (_teams.isEmpty)
                Text(
                    "Még nincs elemzett meccs — előbb dolgozz fel egy "
                    "videót az Új elemzés menüben.",
                    style: AppText.label)
              else ...[
                _teamPicker(),
                const SizedBox(height: AppSpacing.md),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                    child: Text(_error!,
                        style:
                            AppText.label.copyWith(color: AppColors.away)),
                  ),
                if (_rowsLoading)
                  const Expanded(
                      child: WaitingView("Keret összeállítása…",
                          hint: "Minden tárolt meccset átnézünk.",
                          icon: Icons.groups_outlined))
                else if (_players.isEmpty)
                  Expanded(
                    child: Text(
                        _note.isNotEmpty
                            ? _note
                            : "Ebben a csapatban egyetlen mezszám sincs "
                                "kiosztva.",
                        style: AppText.label),
                  )
                else ...[
                  Expanded(child: _table()),
                  const SizedBox(height: AppSpacing.sm),
                  Text(_note, style: AppText.label.copyWith(fontSize: 11.5)),
                ],
              ],
            ]),
    );
  }

  Widget _teamPicker() {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Text("CSAPAT", style: AppText.sectionLabel),
      const SizedBox(width: AppSpacing.sm),
      DropdownButton<String>(
        value: _team,
        dropdownColor: AppColors.surface,
        style: AppText.value.copyWith(fontSize: 13),
        items: [
          for (final t in _teams) DropdownMenuItem(value: t, child: Text(t)),
        ],
        onChanged: _rowsLoading
            ? null
            : (v) {
                setState(() => _team = v);
                _loadRoster();
              },
      ),
    ]);
  }

  Widget _table() {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _headerRow(),
      const SizedBox(height: AppSpacing.xs),
      Expanded(
        child: ListView.builder(
          itemCount: _sorted.length,
          itemBuilder: (_, i) => _row(_sorted[i]),
        ),
      ),
    ]);
  }

  Widget _cell(String text, {bool header = false, int flex = 1}) {
    return Expanded(
      flex: flex,
      child: Text(text,
          textAlign: TextAlign.right,
          overflow: TextOverflow.ellipsis,
          style: header
              ? AppText.sectionLabel
              : AppText.value.copyWith(fontSize: 13)),
    );
  }

  Widget _headerRow() {
    Widget head(String key, String label, {int flex = 1}) {
      final on = _sortKey == key;
      return Expanded(
        flex: flex,
        child: InkWell(
          onTap: () => _sortBy(key),
          child: Row(mainAxisAlignment: MainAxisAlignment.end, children: [
            Flexible(
              child: Text(label,
                  textAlign: TextAlign.right,
                  overflow: TextOverflow.ellipsis,
                  style: AppText.sectionLabel.copyWith(
                      color:
                          on ? AppColors.accent : AppColors.textSecondary)),
            ),
            if (on)
              Icon(_desc ? Icons.arrow_drop_down : Icons.arrow_drop_up,
                  size: 16, color: AppColors.accent),
          ]),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
      child: Row(children: [
        head("jersey", "MEZ", flex: 2),
        for (final (key, label) in kRosterColumns)
          head(key, label.toUpperCase()),
      ]),
    );
  }

  Widget _row(Map<String, dynamic> p) {
    final jersey = (p["jersey"] as num?)?.toInt() ?? 0;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.xs),
      child: InkWell(
        onTap: () {
          final team = _team;
          if (team == null) return;
          Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => PlayerTrendScreen(
              teams: _teams,
              initialTeam: team,
              initialJersey: jersey,
            ),
          ));
        },
        child: Container(
          padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md, vertical: AppSpacing.sm),
          decoration: AppTheme.card(),
          child: Row(children: [
            Expanded(
              flex: 2,
              child: Row(children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 7, vertical: 2),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceAlt,
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: AppColors.borderStrong),
                  ),
                  child: Text("#$jersey",
                      style: AppText.value.copyWith(fontSize: 13)),
                ),
              ]),
            ),
            for (final (key, _) in kRosterColumns)
              _cell("${(p[key] as num?)?.toInt() ?? 0}"),
          ]),
        ),
      ),
    );
  }
}
