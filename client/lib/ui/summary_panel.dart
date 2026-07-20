/// Meccs-összegző panel — csapatstílus egy nézetben (sötét téma).
library;

import "package:flutter/material.dart";

import "../analytics/court_analytics.dart";
import "../analytics/match_summary.dart";
import "../analytics/tactics.dart";
import "../theme/app_theme.dart";
import "defense_timeline.dart";
import "intensity_chart.dart";
import "score_chart.dart";

class SummaryPanel extends StatelessWidget {
  final MatchSummary summary;
  final String homeName;
  final String awayName;

  /// Gól-események az eredmény-alakulás grafikonhoz (üresnél nincs grafikon).
  final List<Map<String, dynamic>> goals;
  final int totalFrames;
  final double fps;
  final void Function(int frame)? onSeekFrame;

  /// Intenzitás-ablakok a tempó-grafikonhoz (2-nél kevesebbnél nincs grafikon).
  final List<IntensityWindow> intensity;

  /// Védekezés-idővonal ablakai (üresnél nincs sáv).
  final List<FormationWindow> formations;

  /// Automatikus edzői összefoglaló a backendtől:
  /// {"sections": [{"title","body"}...], "highlights": [...]} — null-nál
  /// a panel a grafikonokkal kezd (pl. demónál nincs backend-összefoglaló).
  final Map<String, dynamic>? coach;

  /// Gól-sorozatok az eredmény-grafikon kiemeléséhez (üresnél nincs sáv).
  final List<Map<String, dynamic>> runs;

  /// Kulcsemberek a backendtől: {"home": [{"role","player_id","detail"}]}
  final Map<String, dynamic>? keyPlayers;
  final List<dynamic> keyMoments;

  /// Edzés-fókusz javaslatok a backendtől: {"home": [...], "away": [...]}
  /// — elemenként {"area","title","why","drill"}. Null/üresnél nincs kártya.
  final Map<String, dynamic>? training;

  /// Vezetés-alakulás a backendtől: {biggest_lead, lead_changes,
  /// lead_time_s, final}. Üresnél nincs felirat.
  final Map<String, dynamic>? progression;

  /// Gól-idővonal: idő-vödrönkénti dobott/kapott gólok. Üresnél nincs blokk.
  final List<Map<String, dynamic>> goalTimeline;

  const SummaryPanel({
    super.key,
    required this.summary,
    required this.homeName,
    required this.awayName,
    this.goals = const [],
    this.totalFrames = 0,
    this.fps = 25.0,
    this.onSeekFrame,
    this.intensity = const [],
    this.formations = const [],
    this.coach,
    this.runs = const [],
    this.training,
    this.keyPlayers,
    this.keyMoments = const [],
    this.progression,
    this.goalTimeline = const [],
  });

  /// Gól-idővonal mini oszlopdiagram: idő-vödrönként a dobott (hazai/vendég)
  /// gólok — látszik, melyik szakaszban erős egy csapat.
  List<Widget> _goalTimelineBlock() {
    final b = goalTimeline;
    if (b.length < 2) return const [];
    var maxG = 1;
    for (final x in b) {
      final h = (x["home"] as num?)?.toInt() ?? 0;
      final a = (x["away"] as num?)?.toInt() ?? 0;
      if (h > maxG) maxG = h;
      if (a > maxG) maxG = a;
    }
    if (maxG == 0) return const [];
    return [
      const SizedBox(height: AppSpacing.md),
      Text("GÓLOK IDŐBEN (szakaszonként)", style: AppText.sectionLabel),
      const SizedBox(height: AppSpacing.sm),
      SizedBox(
        height: 56,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            for (final x in b) ...[
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    _bar(((x["home"] as num?)?.toInt() ?? 0) / maxG,
                        AppColors.home),
                    const SizedBox(height: 1),
                    _bar(((x["away"] as num?)?.toInt() ?? 0) / maxG,
                        AppColors.away),
                  ],
                ),
              ),
              const SizedBox(width: 3),
            ],
          ],
        ),
      ),
      const SizedBox(height: 2),
      Text("felső sáv: ${homeName} · alsó: ${awayName}",
          style: AppText.label.copyWith(
              fontSize: 10, color: AppColors.textFaint)),
    ];
  }

  /// Meccs-esély sáv: P(hazai) lépcsős kirajzolása a gólok mentén —
  /// kék (hazai) fölény felfelé, piros lefelé, 50% a középvonal.
  List<Widget> _winProbBlock() {
    final wp = (progression?["win_prob"] as Map?)?.cast<String, dynamic>();
    final tl = ((wp?["timeline"] as List?) ?? const [])
        .cast<Map<String, dynamic>>();
    if (tl.length < 3) return const []; // legalább 2 gól kell
    return [
      const SizedBox(height: AppSpacing.md),
      Text("MECCS-ESÉLY (gólok mentén)", style: AppText.sectionLabel),
      const SizedBox(height: AppSpacing.sm),
      SizedBox(
        height: 44,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            for (final x in tl) ...[
              Expanded(child: Builder(builder: (_) {
                final p = ((x["p_home"] as num?) ?? 0.5).toDouble();
                final up = p >= 0.5;
                final frac = (p - 0.5).abs() * 2;
                return Column(children: [
                  Expanded(
                      child: Align(
                          alignment: Alignment.bottomCenter,
                          child: up ? _probBar(frac, AppColors.home) : null)),
                  Container(height: 1, color: AppColors.border),
                  Expanded(
                      child: Align(
                          alignment: Alignment.topCenter,
                          child: up ? null : _probBar(frac, AppColors.away))),
                ]);
              })),
              const SizedBox(width: 3),
            ],
          ],
        ),
      ),
      const SizedBox(height: 2),
      Text(
          "középvonal = 50% · felfelé: $homeName esélye · lefelé: $awayName",
          style: AppText.label.copyWith(
              fontSize: 10, color: AppColors.textFaint)),
    ];
  }

  Widget _probBar(double frac, Color color) => FractionallySizedBox(
        heightFactor: frac.clamp(0.06, 1.0),
        child: Container(
          width: double.infinity,
          decoration: BoxDecoration(
            color: color.withOpacity(0.8),
            borderRadius: BorderRadius.circular(2),
          ),
        ),
      );

  Widget _bar(double frac, Color color) => Container(
        height: (2 + 22 * frac.clamp(0.0, 1.0)),
        decoration: BoxDecoration(
          color: color.withOpacity(frac > 0 ? 0.9 : 0.15),
          borderRadius: BorderRadius.circular(2),
        ),
      );

  /// Vezetés-alakulás felirat az eredmény-grafikon alatt: fordulatok +
  /// legnagyobb előny (ha a backend adott ilyet és volt fordulat).
  List<Widget> _progressionCaption() {
    final p = progression;
    if (p == null || p.isEmpty) return const [];
    final changes = (p["lead_changes"] as num?)?.toInt() ?? 0;
    final bl = (p["biggest_lead"] as Map?)?.cast<String, dynamic>() ?? {};
    final hLead = (bl["home"] as num?)?.toInt() ?? 0;
    final aLead = (bl["away"] as num?)?.toInt() ?? 0;
    if (changes < 1 && hLead == 0 && aLead == 0) return const [];
    final topName = hLead >= aLead ? homeName : awayName;
    final topLead = hLead >= aLead ? hLead : aLead;
    // Nagy fordítás (3+ gólos hátrányból vezetés) — külön említés.
    final cb = (p["comeback"] as Map?)?.cast<String, dynamic>() ?? {};
    final cbHome = (cb["home"] as num?)?.toInt() ?? 0;
    final cbAway = (cb["away"] as num?)?.toInt() ?? 0;
    var cbText = "";
    if (cbHome >= 3 || cbAway >= 3) {
      final cbName = cbHome >= cbAway ? homeName : awayName;
      final cbVal = cbHome >= cbAway ? cbHome : cbAway;
      cbText = " · $cbName $cbVal gólos hátrányból fordított";
    }
    // Hajrá-mérleg: szoros végjátéknál, legalább 2 gólos különbséggel.
    var clText = "";
    final cl = (p["clutch"] as Map?)?.cast<String, dynamic>();
    if (cl != null && cl["available"] == true && cl["close"] == true) {
      final gh = ((cl["home"] as Map?)?["goals"] as num?)?.toInt() ?? 0;
      final ga = ((cl["away"] as Map?)?["goals"] as num?)?.toInt() ?? 0;
      if ((gh - ga).abs() >= 2) {
        final wName = gh > ga ? homeName : awayName;
        final hi = gh > ga ? gh : ga;
        final lo = gh > ga ? ga : gh;
        clText = " · a hajrát $wName nyerte $hi–$lo-ra";
      }
    }
    // Gólcsend: 8+ perces saját gól nélküli szakasz — a hosszabbik.
    var drText = "";
    final dr = (p["droughts"] as Map?)?.cast<String, dynamic>();
    if (dr != null) {
      double best = 0;
      String? side;
      for (final k in ["home", "away"]) {
        final v = (((dr[k] as Map?)?["longest_s"]) as num?)?.toDouble() ?? 0;
        if (v > best) {
          best = v;
          side = k;
        }
      }
      if (best >= 480 && side != null) {
        final nm = side == "home" ? homeName : awayName;
        drText = " · $nm leghosszabb gólcsendje ${(best / 60).round()} perc";
      }
    }
    // Félidei állás (csak ha a szünet ténylegesen felismerhető volt).
    var htText = "";
    final ht = (p["halftime"] as Map?)?.cast<String, dynamic>();
    if (ht != null) {
      final h = ((ht["home"] as num?) ?? 0).toInt();
      final a = ((ht["away"] as num?) ?? 0).toInt();
      htText = "félidőben $h–$a · ";
    }
    return [
      const SizedBox(height: 4),
      Text(
          "${htText}A meccs ${changes}-szor fordult · legnagyobb előny: "
          "$topName +$topLead$cbText$clText$drText",
          style: AppText.label.copyWith(fontSize: 11, color: AppColors.textFaint)),
    ];
  }

  /// Kulcs-pillanatok kártya: a meccs gerince időrendben — koppintásra
  /// a lejátszó odaugrik (a csomag kulcs_pillanatok.txt párja).
  List<Widget> _keyMomentsCard() {
    if (keyMoments.isEmpty) return const [];
    String clk(num s) =>
        "${(s ~/ 60)}:${(s % 60).toInt().toString().padLeft(2, "0")}";
    return [
      Text("KULCS-PILLANATOK", style: AppText.sectionLabel),
      const SizedBox(height: AppSpacing.sm),
      Container(
        padding: const EdgeInsets.all(AppSpacing.sm),
        decoration: BoxDecoration(
          color: AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: AppColors.border),
        ),
        child: Column(children: [
          for (final m in keyMoments.cast<Map<String, dynamic>>())
            InkWell(
              borderRadius: BorderRadius.circular(8),
              onTap: onSeekFrame == null
                  ? null
                  : () => onSeekFrame!(((m["t"] as num?) ?? 0).toInt()),
              child: Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 6, vertical: 5),
                child: Row(children: [
                  Text(clk((m["t_s"] as num?) ?? 0),
                      style: AppText.value.copyWith(
                          fontSize: 12, color: AppColors.accent)),
                  const SizedBox(width: 10),
                  Expanded(
                      child: Text("${m["label"]}",
                          style: AppText.label.copyWith(fontSize: 12))),
                ]),
              ),
            ),
        ]),
      ),
      const SizedBox(height: AppSpacing.lg),
    ];
  }

  /// Kulcsemberek kártya: szereponként a meccs meghatározó játékosai —
  /// ugyanazokból a rétegekből, mint a jelentés Kulcsemberek táblája.
  List<Widget> _keyPlayersCard() {
    final kp = keyPlayers;
    if (kp == null) return const [];
    final sides = [
      ("home", homeName, AppColors.home),
      ("away", awayName, AppColors.away),
    ];
    final hasAny =
        sides.any((s) => ((kp[s.$1] as List?) ?? const []).isNotEmpty);
    if (!hasAny) return const [];
    return [
      Text("KULCSEMBEREK", style: AppText.sectionLabel),
      const SizedBox(height: AppSpacing.sm),
      Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: AppColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final (key, name, color) in sides)
              if (((kp[key] as List?) ?? const []).isNotEmpty) ...[
                Padding(
                  padding: const EdgeInsets.only(top: 2, bottom: 4),
                  child: Text(name,
                      style: AppText.value
                          .copyWith(fontSize: 12.5, color: color)),
                ),
                for (final it
                    in ((kp[key] as List).cast<Map<String, dynamic>>()))
                  Padding(
                    padding: const EdgeInsets.only(left: 8, bottom: 4),
                    child: Text.rich(TextSpan(children: [
                      TextSpan(
                          text: "${it["role"]}: ",
                          style: AppText.label.copyWith(
                              fontSize: 11.5,
                              color: AppColors.textFaint)),
                      TextSpan(
                          text: "${it["player_id"]}. játékos",
                          style: AppText.value.copyWith(fontSize: 12)),
                      TextSpan(
                          text: "  (${it["detail"]})",
                          style: AppText.label.copyWith(
                              fontSize: 11.5,
                              color: AppColors.textPrimary)),
                    ])),
                  ),
              ],
          ],
        ),
      ),
      const SizedBox(height: AppSpacing.xl),
    ];
  }

  /// Edzés-fókusz kártya: csapatonként a javasolt gyakorlás-fókuszok,
  /// indoklással (a meccs-adat) és gyakorlat-típussal.
  List<Widget> _trainingCard() {
    final t = training;
    if (t == null) return const [];
    final sides = [
      ("home", homeName, AppColors.home),
      ("away", awayName, AppColors.away),
    ];
    final hasAny = sides.any(
        (s) => ((t[s.$1] as List?) ?? const []).isNotEmpty);
    if (!hasAny) return const [];
    return [
      Text("EDZÉS-FÓKUSZ A MECCS ALAPJÁN", style: AppText.sectionLabel),
      const SizedBox(height: AppSpacing.sm),
      Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: AppColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final (key, name, color) in sides)
              if (((t[key] as List?) ?? const []).isNotEmpty) ...[
                Padding(
                  padding: const EdgeInsets.only(top: 2, bottom: 4),
                  child: Text(name,
                      style: AppText.value.copyWith(
                          fontSize: 12.5, color: color)),
                ),
                for (final it in ((t[key] as List).cast<Map<String, dynamic>>()))
                  Padding(
                    padding: const EdgeInsets.only(left: 8, bottom: 6),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text.rich(TextSpan(children: [
                          TextSpan(
                              text: "${it["title"]}",
                              style: AppText.value.copyWith(fontSize: 12)),
                          TextSpan(
                              text: "  ·  ${it["area"]}",
                              style: AppText.label.copyWith(
                                  fontSize: 11, color: AppColors.textFaint)),
                        ])),
                        Text("miért: ${it["why"]}",
                            style: AppText.label.copyWith(
                                fontSize: 11.5, color: AppColors.textPrimary)),
                        Text("gyakorlat: ${it["drill"]}",
                            style: AppText.label.copyWith(
                                fontSize: 11.5, color: AppColors.accent)),
                      ],
                    ),
                  ),
              ],
          ],
        ),
      ),
      const SizedBox(height: AppSpacing.xl),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final sections =
        ((coach?["sections"] as List?) ?? const []).cast<Map<String, dynamic>>();
    final highlights =
        ((coach?["highlights"] as List?) ?? const []).cast<String>();
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        if (sections.isNotEmpty) ...[
          Text("EDZŐI ÖSSZEFOGLALÓ", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: BoxDecoration(
              color: AppColors.surfaceAlt,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: AppColors.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final s in sections)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Text.rich(TextSpan(children: [
                      TextSpan(
                          text: "${s["title"]}. ",
                          style: AppText.value.copyWith(fontSize: 12.5)),
                      TextSpan(
                          text: (s["body"] as String?) ?? "",
                          style: AppText.label.copyWith(
                              fontSize: 12.5, color: AppColors.textPrimary)),
                    ])),
                  ),
                for (final h in highlights)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.tips_and_updates_outlined,
                              size: 14, color: AppColors.gold),
                          const SizedBox(width: 6),
                          Expanded(
                              child: Text(h,
                                  style: AppText.label.copyWith(
                                      fontSize: 12, color: AppColors.gold))),
                        ]),
                  ),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.xl),
        ],
        ..._keyMomentsCard(),
        ..._keyPlayersCard(),
        ..._trainingCard(),
        if (goals.isNotEmpty) ...[
          Text("EREDMÉNY-ALAKULÁS", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          ScoreChart(
            goals: goals,
            totalFrames: totalFrames,
            fps: fps,
            homeName: homeName,
            awayName: awayName,
            onSeekFrame: onSeekFrame,
            runs: runs,
          ),
          ..._progressionCaption(),
          ..._goalTimelineBlock(),
          ..._winProbBlock(),
          const SizedBox(height: AppSpacing.xl),
        ],
        if (intensity.length >= 2) ...[
          Text("TEMPÓ-ALAKULÁS (FÁRADÁS)", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          IntensityChart(
            windows: intensity,
            totalFrames: totalFrames,
            fps: fps,
            homeName: homeName,
            awayName: awayName,
            onSeekFrame: onSeekFrame,
          ),
          const SizedBox(height: AppSpacing.xl),
        ],
        if (formations.length >= 2) ...[
          Text("VÉDEKEZÉS-IDŐVONAL", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          DefenseTimeline(
            windows: formations,
            totalFrames: totalFrames,
            fps: fps,
            homeName: homeName,
            awayName: awayName,
            onSeekFrame: onSeekFrame,
          ),
          const SizedBox(height: AppSpacing.xl),
        ],
        Text("FÁZIS-MEGOSZLÁS", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        _bar("Hazai támadás", summary.phasePercentages[Phase.homeAttack] ?? 0, AppColors.home),
        _bar("Vendég támadás", summary.phasePercentages[Phase.awayAttack] ?? 0, AppColors.away),
        _bar("Átmenet", summary.phasePercentages[Phase.transition] ?? 0, AppColors.textSecondary),

        const SizedBox(height: AppSpacing.xl),
        Text("VÉDEKEZÉSI FORMA", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        _kv(homeName, summary.homeFormation),
        _kv(awayName, summary.awayFormation),

        const SizedBox(height: AppSpacing.xl),
        Text("TEMPÓ", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        _kv("Birtoklások", "${summary.possessions}"),
        _kv("Átlagos támadás", "${summary.avgAttackDurationS.toStringAsFixed(1)} s"),
        _kv("Átmenet aránya", "${summary.transitionPct.toStringAsFixed(0)} %"),
        _kv("Labda átlagseb.", "${summary.avgBallSpeedMs.toStringAsFixed(1)} m/s"),

        const SizedBox(height: AppSpacing.xl),
        Text("FIGURÁK", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        _kv("Felismert támadás", "${summary.attacks}"),
        _kv("Visszatérő figura", "${summary.numFigures}"),
      ],
    );
  }

  Widget _kv(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(k, style: AppText.label.copyWith(color: AppColors.textPrimary)),
            Text(v, style: AppText.value),
          ],
        ),
      );

  Widget _bar(String label, double pct, Color color) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label, style: AppText.label.copyWith(color: AppColors.textPrimary)),
              Text("${pct.toStringAsFixed(0)} %", style: AppText.value),
            ],
          ),
          const SizedBox(height: 5),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (pct / 100).clamp(0.0, 1.0),
              minHeight: 6,
              backgroundColor: AppColors.surfaceAlt,
              valueColor: AlwaysStoppedAnimation(color),
            ),
          ),
        ],
      ),
    );
  }
}
