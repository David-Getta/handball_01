/// Csapat-fejlődés — "fejlődünk-e?", saját menüponttal.
///
/// A fejlődés-követés (két időszak összevetése) eddig csak a kezdőlap
/// egyik gombja volt, és két párbeszéd-ablakon át kellett KÉZZEL
/// kijelölni, melyik meccs melyik időszakba tartozik — meccsenként azt
/// is, hogy a figyelt csapat melyik oldalon játszott. Ez annyi
/// kattintás, hogy a kérdést ("fejlődünk-e?") a gyakorlatban senki nem
/// tette fel.
///
/// Itt egy csapatnév elég: a képernyő a könyvtárból összeszedi a csapat
/// ÖSSZES meccsét dátum szerint, és kettévágja őket korábbi/újabb
/// időszakra. A vágópont húzható — így a "szünet előtt vs szünet után"
/// vagy a "régi felállás vs új felállás" kérdés is feltehető.
///
/// Az összevetést maga a meglévő fejlődés-nézet (TrendScreen) rajzolja
/// ki: ez a képernyő csak a VÁLASZTÁS-t veszi le az edző válláról.
library;

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "error_text.dart";
import "shell/app_shell.dart";
import "trend_screen.dart";
import "waiting.dart";

class TeamTrendScreen extends StatefulWidget {
  const TeamTrendScreen({super.key});

  @override
  State<TeamTrendScreen> createState() => _TeamTrendScreenState();
}

class _TeamTrendScreenState extends State<TeamTrendScreen> {
  final ApiClient _api = ApiClient();

  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _matches = [];
  List<String> _teams = [];
  String? _team;

  /// Hány meccs tartozik a KORÁBBI időszakba (a maradék az újabb).
  int _split = 1;

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
        _matches = ms;
        _teams = sorted;
        _loading = false;
      });
      // A kezdő csapat az legyen, akinek a LEGTÖBB meccse van: a
      // fejlődés-kérdés csak több meccsből válaszolható meg.
      String? best;
      var bestN = 0;
      for (final t in sorted) {
        final n = _ofTeam(t).length;
        if (n > bestN) {
          best = t;
          bestN = n;
        }
      }
      if (!mounted) return;
      setState(() {
        _team = best;
        _split = bestN >= 2 ? bestN ~/ 2 : 1;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = "A meccs-könyvtár nem érhető el: ${humanError(e)}";
        _loading = false;
      });
    }
  }

  /// A csapat meccsei IDŐRENDBEN, a figyelt oldallal együtt.
  ///
  /// A dátum hiányozhat (régi feldolgozás); olyankor a lista sorrendje
  /// dönt, ami a könyvtár szerinti (felvételi) sorrend — a fejlődés
  /// kérdéséhez ez a legjobb közelítés, amink van.
  List<Map<String, dynamic>> _ofTeam(String team) {
    final out = <Map<String, dynamic>>[];
    for (final m in _matches) {
      final id = m["match_id"] as String?;
      if (id == null) continue;
      final side = m["home_team"] == team
          ? "home"
          : (m["away_team"] == team ? "away" : null);
      if (side == null) continue;
      out.add({
        "match_id": id,
        "team": side,
        "date": (m["date"] as String?) ?? "",
        "home_team": m["home_team"],
        "away_team": m["away_team"],
      });
    }
    out.sort((a, b) => (a["date"] as String).compareTo(b["date"] as String));
    return out;
  }

  List<Map<String, String>> _items(Iterable<Map<String, dynamic>> rows) => [
        for (final r in rows)
          {"match_id": r["match_id"] as String, "team": r["team"] as String}
      ];

  void _open() {
    final team = _team;
    if (team == null) return;
    final rows = _ofTeam(team);
    if (rows.length < 2) return;
    final vag = _split.clamp(1, rows.length - 1);
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => TrendScreen(
        older: _items(rows.take(vag)),
        newer: _items(rows.skip(vag)),
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final rows = _team == null ? const <Map<String, dynamic>>[] : _ofTeam(_team!);
    return AppShell(
      active: NavId.teamTrend,
      crumbPath: "CSAPAT · CSAPAT-FEJLŐDÉS",
      child: _loading
          ? const WaitingView("Meccs-könyvtár olvasása…",
              icon: Icons.trending_up)
          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text("Csapat-fejlődés", style: AppText.title),
              const SizedBox(height: 4),
              Text(
                  "fejlődünk-e? — a csapat meccsei kettévágva: korábbi "
                  "időszak vs újabb, mutatónként",
                  style: AppText.subtitle),
              const SizedBox(height: AppSpacing.lg),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Text(_error!,
                      style: AppText.label.copyWith(color: AppColors.away)),
                ),
              if (_teams.isEmpty)
                Text(
                    "Még nincs elemzett meccs — előbb dolgozz fel egy "
                    "videót az Új elemzés menüben.",
                    style: AppText.label)
              else ...[
                _teamPicker(),
                const SizedBox(height: AppSpacing.md),
                if (rows.length < 2)
                  Text(
                      "Ebből a csapatból csak ${rows.length} meccs van a "
                      "könyvtárban. A fejlődés KÉT időszak összevetése — "
                      "legalább két meccs kell hozzá, és minél több, "
                      "annál kevésbé szól bele a napi forma.",
                      style: AppText.label)
                else ...[
                  _splitControl(rows),
                  const SizedBox(height: AppSpacing.md),
                  Expanded(child: _matchList(rows)),
                  const SizedBox(height: AppSpacing.sm),
                  Align(
                    alignment: Alignment.centerRight,
                    child: FilledButton.icon(
                      onPressed: _open,
                      style: FilledButton.styleFrom(
                          backgroundColor: AppColors.accent,
                          foregroundColor: AppColors.onAccent),
                      icon: const Icon(Icons.trending_up, size: 18),
                      label: const Text("Összevetés"),
                    ),
                  ),
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
          for (final t in _teams)
            DropdownMenuItem(
                value: t, child: Text("$t (${_ofTeam(t).length} meccs)")),
        ],
        onChanged: (v) {
          if (v == null) return;
          final n = _ofTeam(v).length;
          setState(() {
            _team = v;
            _split = n >= 2 ? n ~/ 2 : 1;
          });
        },
      ),
    ]);
  }

  Widget _splitControl(List<Map<String, dynamic>> rows) {
    final vag = _split.clamp(1, rows.length - 1);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text("VÁGÓPONT", style: AppText.sectionLabel),
      Text(
          "korábbi időszak: $vag meccs · újabb: ${rows.length - vag} meccs",
          style: AppText.label.copyWith(fontSize: 12)),
      if (rows.length == 2)
        Text("Két meccsnél a vágópont adott (1–1).",
            style: AppText.label.copyWith(fontSize: 11.5))
      else
        Slider(
          value: vag.toDouble(),
          min: 1,
          max: (rows.length - 1).toDouble(),
          divisions: rows.length - 2 > 0 ? rows.length - 2 : null,
          label: "$vag",
          activeColor: AppColors.accent,
          onChanged: (v) => setState(() => _split = v.round()),
        ),
    ]);
  }

  Widget _matchList(List<Map<String, dynamic>> rows) {
    final vag = _split.clamp(1, rows.length - 1);
    return ListView.builder(
      itemCount: rows.length,
      itemBuilder: (_, i) {
        final r = rows[i];
        final korabbi = i < vag;
        final date = r["date"] as String;
        return Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.xs),
          child: Container(
            padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md, vertical: AppSpacing.sm),
            decoration: AppTheme.card(
                borderColor: korabbi ? AppColors.border : AppColors.accent),
            child: Row(children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: korabbi ? AppColors.surfaceAlt : AppColors.accentSoft,
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(korabbi ? "korábbi" : "újabb",
                    style: AppText.label.copyWith(fontSize: 10.5)),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                    "${r["home_team"] ?? "Hazai"} – "
                    "${r["away_team"] ?? "Vendég"}",
                    overflow: TextOverflow.ellipsis,
                    style: AppText.value.copyWith(fontSize: 13)),
              ),
              Text(date.isEmpty ? "dátum nélkül" : date,
                  style: AppText.label.copyWith(fontSize: 11)),
            ]),
          ),
        );
      },
    );
  }
}
