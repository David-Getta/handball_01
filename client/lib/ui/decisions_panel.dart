/// Döntések-panel — egy kiválasztott játékos passz-döntései (sötét téma).
library;

import "package:flutter/material.dart";

import "anim.dart";
import "../analytics/decisions.dart";
import "../models/tracking.dart";
import "../services/api_client.dart";
import "../theme/app_theme.dart";

class DecisionsPanel extends StatefulWidget {
  final Match match;

  /// Az elemző motor: a helyzetenkénti játékos-modell innen jön. Nélküle
  /// (pl. motor nélküli nézet) a panel a helyben számolt passz-képet
  /// mutatja, a helyzet-profil helyén egy magyarázó sorral.
  final ApiClient? api;
  const DecisionsPanel({super.key, required this.match, this.api});

  @override
  State<DecisionsPanel> createState() => _DecisionsPanelState();
}

class _DecisionsPanelState extends State<DecisionsPanel> {
  int? _playerId;
  late Map<int, int?> _jerseyById;
  late List<int> _passers;
  Future<Map<String, dynamic>>? _profile;

  // A helyzetek és a választások a motor sorrendjében
  // (decisions.SIT_SITUATIONS, SIT_ACTIONS); ennyi döntés alatt a motor
  // sem mond szokást (SIT_MIN).
  static const _sits = ["kilépnek rá", "szabad a 6 m-es társ",
                        "szabad lőhely"];
  static const _sitTitle = {
    "kilépnek rá": "Ha kilépnek rá",
    "szabad a 6 m-es társ": "Ha szabad a 6 m-es társa",
    "szabad lőhely": "Szabad lőhelyen",
  };
  static const _acts = ["lövés", "passz a 6 m-re", "passz a szélre",
                        "visszajátszás", "átadás"];
  static const _actColors = [AppColors.ball, AppColors.accent,
                             AppColors.home, AppColors.textFaint,
                             AppColors.gold];
  static const _sitMin = 8;

  @override
  void initState() {
    super.initState();
    _jerseyById = _buildJerseyMap(widget.match);
    _passers = passingPlayerIds(widget.match);
    _playerId = _passers.isNotEmpty ? _passers.first : null;
    _loadProfile();
  }

  void _loadProfile() {
    final api = widget.api;
    final id = _playerId;
    _profile = (api == null || id == null)
        ? null
        : api.fetchPlayerDecisions(widget.match.meta.matchId, id);
  }

  Map<int, int?> _buildJerseyMap(Match match) {
    final map = <int, int?>{};
    for (final f in match.frames) {
      for (final p in f.players) {
        map.putIfAbsent(p.trackId, () => p.jerseyNumber);
      }
    }
    return map;
  }

  String _label(int id) {
    final j = _jerseyById[id];
    return j != null ? "#$j" : "id $id";
  }

  @override
  Widget build(BuildContext context) {
    if (_passers.isEmpty) {
      return Center(child: Text("Nincs felismert passz.", style: AppText.label));
    }

    final report = analyzePlayerDecisions(widget.match, _playerId!);
    final dist = report.passDistribution.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        Text("JÁTÉKOS", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: AppColors.surfaceAlt,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: AppColors.border),
          ),
          child: DropdownButton<int>(
            value: _playerId,
            isExpanded: true,
            underline: const SizedBox(),
            dropdownColor: AppColors.surfaceAlt,
            items: [for (final id in _passers) DropdownMenuItem(value: id, child: Text(_label(id)))],
            onChanged: (v) => setState(() {
              _playerId = v;
              _loadProfile();
            }),
          ),
        ),

        const SizedBox(height: AppSpacing.lg),
        Row(
          children: [
            _metric("Passzok", report.passes.toDouble(), (v) => "${v.round()}"),
            _metric("Optimális", report.optimalRate * 100,
                (v) => "${v.toStringAsFixed(0)}%",
                accent: true),
          ],
        ),
        const SizedBox(height: 6),
        // A "62%" magában semmit nem mond: a szám ÉRTELMÉT ide kell
        // odaírni, különben az edző nem tudja, mihez viszonyítson.
        Text(
            "Az \"optimális\" azt méri, hányszor a LEGJOBB elérhető opciót "
            "választotta — a mezőny akkori állásából számolva. A 100% nem "
            "reális cél: a kényszerpasszok is beleszámítanak.",
            style: AppText.label.copyWith(fontSize: 11)),

        const SizedBox(height: AppSpacing.lg),
        Text("KIHEZ PASSZOL", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        if (dist.isEmpty) Text("—", style: AppText.label),
        for (final (i, e) in dist.indexed)
          FadeSlideIn(
              index: i,
              child: _distRow(_label(e.key), e.value, report.passes)),

        const SizedBox(height: AppSpacing.lg),
        Text("HELYZETENKÉNT", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        if (_profile == null)
          Text("A helyzetenkénti profilt az elemző motor számolja — "
              "motor nélkül csak a passz-kép látszik.",
              style: AppText.label)
        else
          FutureBuilder<Map<String, dynamic>>(
            future: _profile,
            builder: (context, snap) {
              if (snap.connectionState != ConnectionState.done) {
                return const LinearProgressIndicator(minHeight: 2);
              }
              if (snap.hasError || snap.data == null) {
                return Text("A helyzet-profil most nem érhető el (a motor "
                    "nem válaszolt).", style: AppText.label);
              }
              return _situationProfile(snap.data!);
            },
          ),
      ],
    );
  }

  /// A játékos-modell: helyzetenként mit választ, és hányszor a legjobbat.
  Widget _situationProfile(Map<String, dynamic> d) {
    final sits = (d["situations"] as Map?)?.cast<String, dynamic>() ?? {};
    final rows = <Widget>[];
    for (final s in _sits) {
      final rec = (sits[s] as Map?)?.cast<String, dynamic>();
      final n = (rec?["decisions"] as num?)?.toInt() ?? 0;
      if (rec == null || n == 0) continue;
      final acts = (rec["actions"] as Map?)?.cast<String, dynamic>() ?? {};
      final best = (rec["match"] as num?)?.toInt() ?? 0;
      rows.add(_situationRow(s, n, best, acts));
    }
    final pr = (d["pressure"] as Map?)?.cast<String, dynamic>();
    final press = (pr?["press"] as num?)?.toInt() ?? 0;
    final pressBest = (pr?["press_best"] as num?)?.toInt() ?? 0;
    final teamFree = (pr?["team_free_pct"] as num?)?.toDouble();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (rows.isEmpty)
          Text("Ezen a meccsen nincs besorolható döntése (kilépés, szabad "
              "6 m-es társ, szabad lőhely).", style: AppText.label)
        else ...[
          for (final (i, w) in rows.indexed)
            FadeSlideIn(index: i, child: w),
          const SizedBox(height: 6),
          Wrap(spacing: 10, runSpacing: 4, children: [
            for (final (i, a) in _acts.indexed)
              Row(mainAxisSize: MainAxisSize.min, children: [
                Container(width: 9, height: 9, color: _actColors[i]),
                const SizedBox(width: 4),
                Text(a, style: AppText.label.copyWith(fontSize: 11)),
              ]),
          ]),
        ],
        if (press > 0) ...[
          const SizedBox(height: AppSpacing.md),
          Text(
              "Szorítva (védő 2 m-en belül): $press döntéséből $pressBest "
              "volt a legjobb opció"
              "${teamFree != null ? " — a csapat szabad döntéseinél "
                  "${teamFree.round()}% az arány" : ""}.",
              style: AppText.label.copyWith(color: AppColors.textPrimary)),
        ],
        const SizedBox(height: 6),
        Text(
            "A \"legjobb\" a döntés pillanatában a modell szerint legtöbbet "
            "érő opció (a fogott fogadó és a szorított lövő kevesebbet ér). "
            "$_sitMin döntés alatt ez még nem szokás, csak egy-egy eset.",
            style: AppText.label.copyWith(fontSize: 11)),
      ],
    );
  }

  Widget _situationRow(String sit, int n, int best,
      Map<String, dynamic> acts) {
    final counts = [for (final a in _acts) (acts[a] as num?)?.toInt() ?? 0];
    final keves = n < _sitMin;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Wrap, nem Row: keskeny panelen a szám a cím alá törik,
          // ahelyett hogy kilógna.
          Wrap(
            alignment: WrapAlignment.spaceBetween,
            spacing: 8,
            runSpacing: 2,
            children: [
              Text(_sitTitle[sit] ?? sit,
                  style: AppText.label
                      .copyWith(color: AppColors.textPrimary)),
              Text(
                  "$n döntés · legjobb: $best/$n"
                  "${keves ? " · kevés minta" : ""}",
                  style: AppText.value),
            ],
          ),
          const SizedBox(height: 5),
          ClipRRect(
            borderRadius: BorderRadius.circular(3),
            child: SizedBox(
              height: 8,
              child: Row(children: [
                for (final (i, c) in counts.indexed)
                  if (c > 0)
                    Expanded(
                        flex: c,
                        child: Container(color: _actColors[i])),
              ]),
            ),
          ),
        ],
      ),
    );
  }

  /// Egy mérő-doboz. A szám FELPÖRÖG (CountUp): játékos-váltáskor a
  /// mozgás jelzi, hogy az érték kicserélődött — eddig némán átugrott,
  /// és könnyű volt a régi számot olvasni az újnak.
  Widget _metric(String label, double value, String Function(double) format,
          {bool accent = false}) =>
      Expanded(
        child: Container(
          margin: const EdgeInsets.only(right: AppSpacing.sm),
          padding: const EdgeInsets.all(AppSpacing.md),
          decoration: BoxDecoration(
            color: AppColors.surfaceAlt,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppColors.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CountUp(
                  value: value,
                  format: format,
                  style: AppText.valueBig.copyWith(
                      color: accent
                          ? AppColors.accent
                          : AppColors.textPrimary)),
              const SizedBox(height: 2),
              Text(label, style: AppText.label.copyWith(fontSize: 11)),
            ],
          ),
        ),
      );

  Widget _distRow(String target, int count, int total) {
    final frac = total > 0 ? count / total : 0.0;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text("→ $target", style: AppText.label.copyWith(color: AppColors.textPrimary)),
              Text("$count/$total · ${(frac * 100).toStringAsFixed(0)}%", style: AppText.value),
            ],
          ),
          const SizedBox(height: 5),
          AnimatedBar(value: frac, minHeight: 6),
        ],
      ),
    );
  }
}
