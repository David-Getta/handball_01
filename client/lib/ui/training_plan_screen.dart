/// Edzésterv — az edző HETI munkalapja, saját menüponttal.
///
/// Eddig az edzés-fókusz csak egy meccs mélyén (összefoglaló-panel), a
/// szezon-szintű, VISSZATÉRŐ fókusz pedig a kezdőlap egyik kártyáján
/// élt. Az edző munkarendjében viszont ez önálló feladat: "mit
/// gyakorolunk a héten" — ezért kap saját menüpontot.
///
/// Két nézet egy lapon:
///   SZEZON: ami legalább KÉT meccsen előjött (`/library/training-focus`)
///           — ez nem egyszeri kisiklás, hanem edzhető gyengeség;
///   EGY MECCS: a kiválasztott meccs fókuszai (`/matches/{id}/training`).
///
/// A csapatot a felhasználó választja: a saját csapatra edzéstervnek, az
/// ellenfélre "mit fognak ellenünk gyakorolni" olvasatnak jó.
library;

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "error_text.dart";
import "shell/app_shell.dart";
import "waiting.dart";

class TrainingPlanScreen extends StatefulWidget {
  const TrainingPlanScreen({super.key});

  @override
  State<TrainingPlanScreen> createState() => _TrainingPlanScreenState();
}

class _TrainingPlanScreenState extends State<TrainingPlanScreen> {
  final ApiClient _api = ApiClient();

  bool _loading = true;
  String? _error;

  // Szezon-nézet: csapatnév → visszatérő fókuszok, és meccs-darabszám.
  Map<String, List<Map<String, dynamic>>> _teams = {};
  Map<String, int> _matchCounts = {};
  String? _team;

  // Egy-meccs nézet.
  List<Map<String, dynamic>> _matches = [];
  String? _matchId;
  Map<String, dynamic>? _matchFocus; // {"home": [...], "away": [...]}
  bool _matchLoading = false;

  bool _seasonView = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final lib = await _api.fetchLibraryTrainingFocus();
      final ms = await _api.listMatches();
      if (!mounted) return;
      final teams = <String, List<Map<String, dynamic>>>{};
      for (final e in ((lib["teams"] as Map?) ?? {}).entries) {
        teams[e.key as String] = [
          for (final it in (e.value as List? ?? []))
            Map<String, dynamic>.from(it as Map)
        ];
      }
      final counts = <String, int>{};
      for (final e in ((lib["matches"] as Map?) ?? {}).entries) {
        counts[e.key as String] = (e.value as num).toInt();
      }
      setState(() {
        _teams = teams;
        _matchCounts = counts;
        _matches = ms;
        _team = teams.keys.isNotEmpty ? teams.keys.first : null;
        _matchId = ms.isNotEmpty ? ms.first["match_id"] as String : null;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = "Az edzésterv nem érhető el: ${humanError(e)}";
        _loading = false;
      });
    }
  }

  Future<void> _loadMatchFocus() async {
    final id = _matchId;
    if (id == null) return;
    setState(() {
      _matchLoading = true;
      _matchFocus = null;
    });
    try {
      final r = await _api.fetchTraining(id);
      if (!mounted) return;
      setState(() {
        _matchFocus = r;
        _matchLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _matchLoading = false;
        _error = "A meccs edzés-fókusza nem érhető el: ${humanError(e)}";
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.training,
      crumbPath: "CSAPAT · EDZÉSTERV",
      child: _loading
          ? const WaitingView("Edzés-fókuszok összegyűjtése…",
              hint: "Minden tárolt meccs fókuszait összesítjük.",
              icon: Icons.fitness_center)
          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text("Edzésterv", style: AppText.title),
              const SizedBox(height: 4),
              Text(
                  "amit a MECCSEK mondanak: mit kell gyakorolni — "
                  "területenként, indokkal és konkrét gyakorlattal",
                  style: AppText.subtitle),
              const SizedBox(height: AppSpacing.lg),
              _viewSwitch(),
              const SizedBox(height: AppSpacing.md),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Text(_error!,
                      style: AppText.label.copyWith(color: AppColors.away)),
                ),
              Expanded(
                  child: _seasonView ? _seasonBody() : _matchBody()),
            ]),
    );
  }

  Widget _viewSwitch() {
    Widget tab(String label, bool season, IconData icon) {
      final on = _seasonView == season;
      return OutlinedButton.icon(
        onPressed: () {
          setState(() => _seasonView = season);
          if (!season && _matchFocus == null) _loadMatchFocus();
        },
        icon: Icon(icon, size: 16),
        style: OutlinedButton.styleFrom(
          side: BorderSide(
              color: on ? AppColors.accent : AppColors.border,
              width: on ? 2 : 1),
          backgroundColor: on ? AppColors.accentSoft : null,
          foregroundColor:
              on ? AppColors.textPrimary : AppColors.textSecondary,
        ),
        label: Text(label),
      );
    }

    return Row(children: [
      tab("Szezon (visszatérő)", true, Icons.repeat),
      const SizedBox(width: AppSpacing.sm),
      tab("Egy meccs", false, Icons.play_circle_outline),
    ]);
  }

  // ---- Szezon-nézet --------------------------------------------------

  Widget _seasonBody() {
    if (_teams.isEmpty) {
      return Text(
          "Még nincs VISSZATÉRŐ fókusz. Ide az kerül, ami legalább két "
          "meccsen előjött ugyanannál a csapatnál — egyetlen meccs "
          "fókuszait az \"Egy meccs\" nézetben látod.",
          style: AppText.label);
    }
    final items = _teams[_team] ?? const [];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          for (final name in _teams.keys)
            ChoiceChip(
              selected: name == _team,
              onSelected: (_) => setState(() => _team = name),
              label: Text("$name (${_matchCounts[name] ?? 0} meccs)"),
              selectedColor: AppColors.accentSoft,
              backgroundColor: AppColors.surfaceAlt,
              labelStyle: AppText.value.copyWith(fontSize: 12.5),
            ),
        ],
      ),
      const SizedBox(height: AppSpacing.md),
      Expanded(
        child: ListView.separated(
          itemCount: items.length,
          separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
          itemBuilder: (_, i) => _focusCard(items[i],
              badge: "${items[i]["count"]} meccsen"),
        ),
      ),
    ]);
  }

  // ---- Egy meccs nézet -----------------------------------------------

  Widget _matchBody() {
    if (_matches.isEmpty) {
      return Text(
          "Még nincs elemzett meccs — előbb dolgozz fel egy videót az "
          "Új elemzés menüben.",
          style: AppText.label);
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      DropdownButton<String>(
        value: _matchId,
        dropdownColor: AppColors.surface,
        style: AppText.value.copyWith(fontSize: 13),
        items: [
          for (final m in _matches)
            DropdownMenuItem(
              value: m["match_id"] as String,
              child: Text(
                  "${m["home_team"] ?? "Hazai"} – ${m["away_team"] ?? "Vendég"}",
                  overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: (v) {
          setState(() => _matchId = v);
          _loadMatchFocus();
        },
      ),
      const SizedBox(height: AppSpacing.md),
      if (_matchLoading)
        // Expanded: a WaitingView Center-re épül, korlátlan magasságú
        // Column-ban túlcsordulna.
        const Expanded(
            child: WaitingView("Edzés-fókusz számítása…",
                icon: Icons.fitness_center))
      else if (_matchFocus == null)
        FilledButton.icon(
          onPressed: _loadMatchFocus,
          icon: const Icon(Icons.download_outlined, size: 18),
          label: const Text("Fókuszok lekérése"),
        )
      else
        Expanded(child: _matchFocusList()),
    ]);
  }

  Widget _matchFocusList() {
    final m = _matches.firstWhere((e) => e["match_id"] == _matchId,
        orElse: () => const <String, dynamic>{});
    final rows = <Widget>[];
    for (final side in const ["home", "away"]) {
      final name = (m[side == "home" ? "home_team" : "away_team"]
              as String?) ??
          (side == "home" ? "Hazai" : "Vendég");
      final list = (_matchFocus?[side] as List?) ?? const [];
      rows.add(Padding(
        padding: const EdgeInsets.only(
            top: AppSpacing.md, bottom: AppSpacing.xs),
        child: Text(name.toUpperCase(), style: AppText.sectionLabel),
      ));
      if (list.isEmpty) {
        rows.add(Text(
            "Ebből a meccsből nem jött ki edzés-fókusz — ez jó hír: a "
            "mért területeken nincs kilógó gyengeség.",
            style: AppText.label));
      }
      for (final it in list) {
        rows.add(Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
          child: _focusCard(Map<String, dynamic>.from(it as Map)),
        ));
      }
    }
    return ListView(children: rows);
  }

  // ---- Közös csempe --------------------------------------------------

  Widget _focusCard(Map<String, dynamic> it, {String? badge}) {
    final area = (it["area"] as String?) ?? "";
    final title = (it["title"] as String?) ?? "";
    final why = (it["why"] as String?) ?? "";
    final drill = (it["drill"] as String?) ?? "";
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: AppTheme.card(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          if (area.isNotEmpty)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: AppColors.surfaceAlt,
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: AppColors.borderStrong),
              ),
              child: Text(area.toUpperCase(),
                  style: AppText.label.copyWith(fontSize: 10.5)),
            ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(child: Text(title, style: AppText.value)),
          if (badge != null)
            Text(badge,
                style: AppText.label
                    .copyWith(fontSize: 11, color: AppColors.gold)),
        ]),
        if (why.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.sm),
          Text(why,
              style: AppText.label
                  .copyWith(fontSize: 12.5, color: AppColors.textSecondary)),
        ],
        if (drill.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.sm),
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Icon(Icons.sports_handball,
                size: 15, color: AppColors.accent),
            const SizedBox(width: 6),
            Expanded(
                child: Text(drill,
                    style: AppText.label.copyWith(
                        fontSize: 12.5, color: AppColors.textPrimary))),
          ]),
        ],
      ]),
    );
  }
}
