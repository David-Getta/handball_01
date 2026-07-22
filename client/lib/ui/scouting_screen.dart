/// Ellenfél-felderítő jelentés — a szoftver "headline" haszna edzőknek.
///
/// Egy csapatról (a felderített ellenfélről) ad egy edzői nyelven megírt
/// jelentést: hogyan játssz ellenük (kulcsok), erősségek/gyengeségek, védekezés,
/// tempó, befejezés, kulcsjátékosok. A backend /scouting végpontból tölt.
library;

import "dart:io";

import "package:file_picker/file_picker.dart";
import "package:flutter/foundation.dart" show kIsWeb;
import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "shell/app_shell.dart";

class ScoutingScreen extends StatefulWidget {
  final String matchId;
  final String homeName;
  final String awayName;
  final String team; // kezdetben melyik csapatot derítjük fel

  /// EGYESÍTETT mód: ha meg van adva, több meccsből készül a jelentés
  /// (elemei: {"match_id": ..., "team": ...}); ilyenkor a matchId/team nem számít,
  /// és a hazai/vendég váltó rejtve van (a team meccsenként rögzített).
  final List<Map<String, String>>? items;

  const ScoutingScreen({
    super.key,
    this.matchId = "",
    this.homeName = "Hazai",
    this.awayName = "Vendég",
    this.team = "away",
    this.items,
  });

  @override
  State<ScoutingScreen> createState() => _ScoutingScreenState();
}

class _ScoutingScreenState extends State<ScoutingScreen> {
  final ApiClient _api = ApiClient();
  late String _team = widget.team;
  List<String> _matchup = const [];
  Map<String, dynamic>? _report;
  // Figura-egyezés a mentett könyvtárral (csak egy-meccses módban töltjük).
  Map<String, dynamic>? _playbookMatch;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      // Egyesített mód: több meccs egy jelentésben; különben egy meccs.
      final r = widget.items != null
          ? await _api.fetchCombinedScouting(widget.items!)
          : await _api.fetchScouting(widget.matchId, _team);
      // Figura-egyezés: melyik MENTETT figurát játsszák (csak egy meccsnél).
      Map<String, dynamic>? pm;
      if (widget.items == null) {
        try {
          pm = await _api.fetchPlaybookMatch(widget.matchId, _team);
        } catch (_) {
          pm = null; // enélkül is teljes a jelentés
        }
      }
      // Meccsterv: a MI profilunk (ugyanezen meccsek másik oldala)
      // keresztezve az ellenfélével — enélkül is teljes a jelentés.
      List<String> matchup = const [];
      try {
        final oppItems = widget.items ??
            [
              {"match_id": widget.matchId, "team": _team}
            ];
        final ownItems = [
          for (final it in oppItems)
            {
              "match_id": it["match_id"],
              "team": (it["team"] == "home") ? "away" : "home",
            }
        ];
        matchup = await _api.fetchMatchupPlan(ownItems, oppItems);
      } catch (_) {
        matchup = const [];
      }
      if (!mounted) return;
      setState(() {
        _report = r;
        _playbookMatch = pm;
        _matchup = matchup;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = "$e";
        _loading = false;
      });
    }
  }

  /// A nyomtatható jelentés mentése fájlba (natív "Mentés másként" ablakkal).
  /// A mentett HTML böngészőben nyitható, onnan Ctrl+P → PDF.
  Future<void> _export() async {
    if (kIsWeb) return; // desktop-first; weben a böngésző maga tudja nyomtatni
    try {
      final bytes = widget.items != null
          ? await _api.fetchCombinedScoutingExport(widget.items!)
          : await _api.fetchScoutingExport(widget.matchId, _team);
      final name = (_report?["team_name"] as String? ?? "ellenfel")
          .replaceAll(RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+"), "_");
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Felderítő jelentés mentése",
        fileName: "felderites_$name.html",
        type: FileType.custom,
        allowedExtensions: const ["html"],
      );
      if (path == null) return; // a felhasználó megszakította
      await File(path).writeAsBytes(bytes);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Jelentés mentve: $path — böngészőből Ctrl+P → PDF")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Export hiba: $e")));
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.scouting,
      crumbTag: "1c",
      crumbPath: "FELDERÍTÉS · ELLENFÉL-JELENTÉS",
      collapsed: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _header(),
          const SizedBox(height: AppSpacing.lg),
          Expanded(child: _body()),
        ],
      ),
    );
  }

  Widget _header() {
    final r = _report;
    return Row(
      children: [
        IconButton(
          onPressed: () => Navigator.of(context).maybePop(),
          icon: const Icon(Icons.arrow_back, color: AppColors.textSecondary),
        ),
        const SizedBox(width: 4),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(r != null ? "${r["team_name"]} — felderítés" : "Felderítés", style: AppText.title),
            Text(
              widget.items != null
                  ? "Egyesített jelentés · ${widget.items!.length} meccs"
                  : "Ellenfél-jelentés · edzői kulcsok",
              style: AppText.subtitle,
            ),
          ],
        ),
        const Spacer(),
        // Nyomtatható jelentés mentése (HTML → böngészőből PDF).
        OutlinedButton.icon(
          onPressed: _report == null ? null : _export,
          style: OutlinedButton.styleFrom(
            foregroundColor: AppColors.gold,
            side: const BorderSide(color: AppColors.gold),
          ),
          icon: const Icon(Icons.print_outlined, size: 18),
          label: const Text("Mentés / nyomtatás"),
        ),
        const SizedBox(width: AppSpacing.md),
        // Melyik csapatot derítsük fel (egyesített módban meccsenként rögzített).
        if (widget.items == null)
          SegmentedButton<String>(
            showSelectedIcon: false,
            segments: [
              ButtonSegment(value: "home", label: Text(widget.homeName)),
              ButtonSegment(value: "away", label: Text(widget.awayName)),
            ],
            selected: {_team},
            onSelectionChanged: (s) {
              setState(() => _team = s.first);
              _load();
            },
          ),
      ],
    );
  }

  Widget _body() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.error_outline, size: 36, color: AppColors.away),
          const SizedBox(height: AppSpacing.md),
          Text("Nem sikerült a felderítés", style: AppText.value.copyWith(fontSize: 16)),
          const SizedBox(height: 6),
          Text(_error!, style: AppText.label, textAlign: TextAlign.center),
          const SizedBox(height: AppSpacing.lg),
          OutlinedButton.icon(onPressed: _load, icon: const Icon(Icons.refresh), label: const Text("Újra")),
        ]),
      );
    }
    final r = _report!;
    return ListView(
      children: [
        if (((r["narrative"] as List?) ?? const []).isNotEmpty) ...[
          _narrativeCard(r),
          const SizedBox(height: AppSpacing.lg),
        ],
        _keysCard(r),
        if (_matchup.isNotEmpty) _matchupCard(),
        const SizedBox(height: AppSpacing.lg),
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: _listCard("ERŐSSÉGEK", r["strengths"], AppColors.accent, Icons.trending_up)),
          const SizedBox(width: AppSpacing.lg),
          Expanded(child: _listCard("GYENGESÉGEK", r["weaknesses"], AppColors.away, Icons.trending_down)),
        ]),
        const SizedBox(height: AppSpacing.lg),
        _metricsCard(r),
        const SizedBox(height: AppSpacing.lg),
        _shotZonesCard(r),
        const SizedBox(height: AppSpacing.lg),
        _defZonesCard(r),
        const SizedBox(height: AppSpacing.lg),
        if (_playbookMatch != null) ...[
          _playbookCard(_playbookMatch!),
          const SizedBox(height: AppSpacing.lg),
        ],
        _defenseCard(r),
        const SizedBox(height: AppSpacing.lg),
        _keyPlayersCard(r),
        const SizedBox(height: AppSpacing.xl),
      ],
    );
  }

  /// Szöveges bevezető: hogyan játszanak — mondatokban, a számok elé.
  Widget _narrativeCard(Map<String, dynamic> r) {
    final sections =
        ((r["narrative"] as List?) ?? const []).cast<Map<String, dynamic>>();
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("ÍGY JÁTSZANAK", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          for (final s in sections)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Text.rich(TextSpan(children: [
                TextSpan(
                    text: "${s["title"]}. ",
                    style: AppText.value.copyWith(fontSize: 13)),
                TextSpan(
                    text: (s["body"] as String?) ?? "",
                    style: AppText.label.copyWith(
                        fontSize: 13, color: AppColors.textPrimary)),
              ])),
            ),
        ],
      ),
    );
  }

  /// A LEGFONTOSABB kártya: hogyan játssz ellenük.
  // Meccsterv: páros-specifikus tanácsok — a mi profilunk és az övék
  // keresztezéséből (POST /scouting/matchup).
  Widget _matchupCard() {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.lg),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: AppColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text("MECCSTERV (A KETTŐNK PÁROSÍTÁSA)",
                style: AppText.sectionLabel
                    .copyWith(color: AppColors.accent)),
            const SizedBox(height: AppSpacing.sm),
            for (final p in _matchup)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text("• $p",
                    style: AppText.label.copyWith(
                        fontSize: 12.5, color: AppColors.textPrimary)),
              ),
          ],
        ),
      ),
    );
  }

  Widget _keysCard(Map<String, dynamic> r) {
    final keys = (r["keys_to_game"] as List?) ?? const [];
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.gold.withOpacity(0.5)),
      ),
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.vpn_key, size: 18, color: AppColors.gold),
            const SizedBox(width: 8),
            Text("HOGYAN JÁTSSZ ELLENÜK", style: AppText.sectionLabel.copyWith(color: AppColors.gold)),
          ]),
          const SizedBox(height: AppSpacing.md),
          for (final k in keys)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Padding(
                  padding: EdgeInsets.only(top: 3, right: 10),
                  child: Icon(Icons.chevron_right, size: 18, color: AppColors.gold),
                ),
                Expanded(child: Text("$k", style: AppText.value.copyWith(fontSize: 14))),
              ]),
            ),
        ],
      ),
    );
  }

  Widget _listCard(String title, dynamic items, Color color, IconData icon) {
    final list = (items as List?) ?? const [];
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(icon, size: 16, color: color),
            const SizedBox(width: 8),
            Text(title, style: AppText.sectionLabel.copyWith(color: color)),
          ]),
          const SizedBox(height: AppSpacing.sm),
          if (list.isEmpty)
            Text("—", style: AppText.label)
          else
            for (final s in list)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Text("• $s", style: AppText.label.copyWith(color: AppColors.textPrimary, fontSize: 12)),
              ),
        ],
      ),
    );
  }

  /// A felderített csapat leglyukasabb védekezési zónája (legtöbb kapott
  /// gól, döntetlennél lövés) — a "hova játssz" gyors jele.
  /// A kapus leggyengébb sarka: a legalacsonyabb védés%-ú, legalább 3
  /// kapura tartó lövést kapott zóna (csak ha tényleg gyenge, <=50%).
  String? _gkWeakZone(Map<String, dynamic> r) {
    final faced = (r["gk_on_target_zones"] as Map?)?.cast<String, dynamic>();
    final conc = (r["gk_conceded_zones"] as Map?)?.cast<String, dynamic>();
    if (faced == null || faced.isEmpty) return null;
    String? worst;
    double worstPct = 101.0;
    faced.forEach((z, v) {
      final n = ((v as num?) ?? 0).toInt();
      if (n < 3) return;
      final c = ((conc?[z] as num?) ?? 0).toInt();
      final pct = 100.0 * (n - c) / n;
      if (pct < worstPct) {
        worstPct = pct;
        worst = z;
      }
    });
    if (worst == null || worstPct > 50.0) return null;
    return "$worst (${worstPct.toStringAsFixed(0)}% védés)";
  }

  /// A játékszervezés tengelye: a leggyakoribb passz-páros — csak
  /// bejáratott kapcsolatnál (min. 15 csapatpassz és 5 páros-passz).
  String? _passAxis(Map<String, dynamic> r) {
    final total = ((r["pass_total"] as num?) ?? 0).toInt();
    final pairs = (r["pass_pairs"] as List?)?.cast<Map<String, dynamic>>();
    if (total < 15 || pairs == null || pairs.isEmpty) return null;
    final p = pairs.first;
    final n = ((p["passes"] as num?) ?? 0).toInt();
    if (n < 5) return null;
    return "${p["from"]} → ${p["to"]} ($n passz)";
  }

  /// Félidőnkénti gólmérleg-váltás: "+2 → −1" — csak elég mintánál
  /// (8+ gól a felismert szünetű meccsekből).
  String? _halfPattern(Map<String, dynamic> r) {
    final fhF = ((r["fh_goals_for"] as num?) ?? 0).toInt();
    final fhA = ((r["fh_goals_against"] as num?) ?? 0).toInt();
    final shF = ((r["sh_goals_for"] as num?) ?? 0).toInt();
    final shA = ((r["sh_goals_against"] as num?) ?? 0).toInt();
    if (fhF + fhA + shF + shA < 8) return null;
    String d(int v) => v >= 0 ? "+$v" : "−${-v}";
    return "${d(fhF - fhA)} → ${d(shF - shA)}";
  }

  /// Lövés-erő: átlag + csúcs km/h — csak elég mért lövésnél (5+).
  // Kapus-indítás: a mért indítások átlagideje a felezőig — csak akkor
  // mutatjuk, ha a fele gyors (a kulcsokkal azonos küszöb).
  String? _gkOutlet(Map<String, dynamic> r) {
    final n = ((r["gk_outlets"] as num?) ?? 0).toInt();
    final fast = ((r["gk_outlet_fast"] as num?) ?? 0).toInt();
    if (n < 2 || fast / n < 0.5) return null;
    final avg = ((r["gk_outlet_sum_s"] as num?) ?? 0).toDouble() / n;
    return "átlag ${avg.toStringAsFixed(0)} mp";
  }

  // Gól-posztok: a legtermékenyebb poszt és aránya (6+ besorolt gól,
  // a narratívával azonos küszöb).
  String? _postGoals(Map<String, dynamic> r) {
    final pg = (r["post_goals"] as Map?)?.cast<String, dynamic>();
    if (pg == null || pg.isEmpty) return null;
    var total = 0;
    String? topKey;
    var topN = 0;
    pg.forEach((k, v) {
      final n = ((v as num?) ?? 0).toInt();
      total += n;
      if (n > topN) {
        topN = n;
        topKey = k;
      }
    });
    if (total < 6 || topKey == null) return null;
    return "$topKey ${(100.0 * topN / total).round()}%";
  }

  // Visszaérés: átlagos visszarendeződés-idő (4+ mért átmenetnél),
  // a kulcsokkal azonos 5 / 3 mp-es címke-küszöbökkel.
  String? _recovery(Map<String, dynamic> r) {
    final n = ((r["rec_transitions"] as num?) ?? 0).toInt();
    if (n < 4) return null;
    final avg = ((r["rec_sum_s"] as num?) ?? 0).toDouble() / n;
    final label = avg >= 5.0
        ? "lassú"
        : avg <= 3.0
            ? "villámgyors"
            : "átlagos";
    return "${avg.toStringAsFixed(1)} mp · $label";
  }

  // Gól-forrás: a fő támadás-eredet (50%+ aránynál, 5+ gólnál) —
  // a narratívával azonos küszöb.
  String? _goalSource(Map<String, dynamic> r) {
    final ao = (r["attack_origins"] as Map?)?.cast<String, dynamic>();
    if (ao == null || ao.isEmpty) return null;
    var total = 0;
    String? topKey;
    var topGoals = 0;
    ao.forEach((k, v) {
      final g = (((v as Map)["goals"] as num?) ?? 0).toInt();
      total += g;
      if (g > topGoals) {
        topGoals = g;
        topKey = k;
      }
    });
    if (total < 5 || topKey == null || topGoals / total < 0.5) {
      return null;
    }
    final pct = (100.0 * topGoals / total).round();
    return "$topKey $pct%";
  }

  // Kapus-xG: hárított xG és GSAx meccsenkénti átlaga — csak mért
  // védéseknél mutatjuk.
  String? _gkXg(Map<String, dynamic> r) {
    final saved = ((r["gk_xg_saved"] as num?) ?? 0).toDouble();
    final prevented = ((r["gk_xg_prevented"] as num?) ?? 0).toDouble();
    final matches = ((r["matches"] as num?) ?? 1).toInt().clamp(1, 999);
    if (saved == 0 && prevented == 0) return null;
    final s = (saved / matches).toStringAsFixed(1);
    final p = (prevented / matches);
    final ps = "${p >= 0 ? "+" : ""}${p.toStringAsFixed(1)}";
    return "$s hárított · $ps GSAx";
  }

  // Tempó-profil: támadás/perc (20+ mért percnél; a kulcsokkal azonos
  // 1,1 / 0,7 küszöbök adnak címkét).
  String? _pace(Map<String, dynamic> r) {
    final attacks = ((r["pace_attacks"] as num?) ?? 0).toInt();
    final minutes = ((r["pace_minutes"] as num?) ?? 0).toDouble();
    if (minutes < 20.0) return null;
    final perMin = attacks / minutes;
    final label = perMin >= 1.1
        ? "tempós"
        : perMin <= 0.7
            ? "lassú"
            : "közepes";
    return "${perMin.toStringAsFixed(1)}/perc · $label";
  }

  // A fal kulcsa: a legtöbb blokkot jegyző védő (3+ blokk, mint a
  // kulcsokban).
  String? _topBlocker(Map<String, dynamic> r) {
    final list = (r["blockers"] as List?) ?? const [];
    if (list.isEmpty) return null;
    final top = list.first as Map<String, dynamic>;
    final n = ((top["blocks"] as num?) ?? 0).toInt();
    if (n < 3) return null;
    return "${top["player_id"]}. · $n blokk";
  }

  // Hetes-dobó: a legtöbb hetest dobó játékos (2+ kísérlet).
  String? _sevenTaker(Map<String, dynamic> r) {
    final list = (r["seven_takers"] as List?) ?? const [];
    if (list.isEmpty) return null;
    final top = list.first as Map<String, dynamic>;
    final a = ((top["attempts"] as num?) ?? 0).toInt();
    if (a < 2) return null;
    final g = ((top["goals"] as num?) ?? 0).toInt();
    var txt = "${top["player_id"]}. · $g/$a gól";
    // Irány-szokás: ha a mért hetesei 70%+ egy sávba mennek (3+ mérés),
    // a csempe is kimondja — azonos küszöb a felderítési kulccsal.
    final dirs = (top["dirs"] as Map?)?.cast<String, dynamic>();
    if (dirs != null && dirs.isNotEmpty) {
      var total = 0;
      String? best;
      var bestN = 0;
      dirs.forEach((k, v) {
        final n = (v as num).toInt();
        total += n;
        if (n > bestN) {
          bestN = n;
          best = k;
        }
      });
      if (total >= 3 && bestN / total >= 0.7 && best != null) {
        const hu = {"bal": "balra", "jobb": "jobbra", "közép": "középre"};
        txt += " · jellemzően ${hu[best] ?? best} lövi";
      }
    }
    return txt;
  }

  // Támadás-szélesség: szélesen (14 m+) vagy szűken (9 m alatt)
  // támadnak — azonos küszöbök a felderítési kulccsal.
  String? _attackWidth(Map<String, dynamic> r) {
    final n = ((r["width_frames"] as num?) ?? 0).toInt();
    final sum = ((r["width_sum_m"] as num?) ?? 0).toDouble();
    if (n < 100 || sum <= 0) return null;
    final avg = sum / n;
    final verdict = avg >= 14.0
        ? "széles"
        : avg <= 9.0
            ? "szűk"
            : null;
    if (verdict == null) return null;
    return "${avg.toStringAsFixed(1)} m · $verdict";
  }

  // Fő figura: a leggólerősebb visszatérő minta (3+ támadás, 2+ gól
  // — azonos küszöb a felderítési kulccsal).
  String? _bestFigure(Map<String, dynamic> r) {
    final a = ((r["best_fig_attacks"] as num?) ?? 0).toInt();
    final g = ((r["best_fig_goals"] as num?) ?? 0).toInt();
    if (a < 3 || g < 2) return null;
    return "$a támadás · $g gól";
  }

  // Előny-kezelés: támadás-hossz vezetve vs hátrányban (időhúzás /
  // kapkodás jele, 8+ mp különbségnél — mint a felderítési kulcs).
  String? _leadPace(Map<String, dynamic> r) {
    final la = ((r["lead_attacks"] as num?) ?? 0).toInt();
    final ta = ((r["trail_attacks"] as num?) ?? 0).toInt();
    if (la < 3 || ta < 3) return null;
    final lavg = ((r["lead_sum_s"] as num?) ?? 0).toDouble() / la;
    final tavg = ((r["trail_sum_s"] as num?) ?? 0).toDouble() / ta;
    if ((lavg - tavg).abs() < 8.0) return null;
    final verdict = lavg > tavg ? "előnyben altatnak" : "hátrányban kapkodnak";
    return "${lavg.toStringAsFixed(0)}/${tavg.toStringAsFixed(0)} mp · $verdict";
  }

  // Szünet-kezdés: a 2. félidő első 5 percének mérlege (3+ gól
  // különbségnél mutatjuk — azonos küszöb a felderítési kulccsal).
  String? _restart(Map<String, dynamic> r) {
    final n = ((r["restart_matches"] as num?) ?? 0).toInt();
    if (n < 1) return null;
    final f = ((r["restart_for"] as num?) ?? 0).toInt();
    final a = ((r["restart_against"] as num?) ?? 0).toInt();
    if ((f - a).abs() < 3) return null;
    final verdict = f > a ? "ők ütnek először" : "rosszul jönnek ki";
    return "$f–$a · $verdict";
  }

  // Fegyelem: aki rendre kiül (2+ kiállítás) — támadható egy-egyben.
  String? _discipline(Map<String, dynamic> r) {
    final list = (r["susp_players"] as List?) ?? const [];
    if (list.isEmpty) return null;
    final top = list.first as Map<String, dynamic>;
    final n = ((top["suspensions"] as num?) ?? 0).toInt();
    if (n < 2) return null;
    return "${top["player_id"]}. · $n kiállítás";
  }

  // Laza emberfogó: a legnagyobb átlagtávú védő (50+ kocka, 2,5 m+)
  // — ugyanaz a küszöb, mint a kulcsokban és a 13. meccsterv-szabályban.
  String? _looseMarker(Map<String, dynamic> r) {
    final list = (r["markers"] as List?) ?? const [];
    Map<String, dynamic>? loose;
    double looseAvg = 0;
    for (final e in list) {
      final m = e as Map<String, dynamic>;
      final frames = ((m["frames"] as num?) ?? 0).toInt();
      if (frames < 50) continue;
      final avg = (((m["dist_sum"] as num?) ?? 0).toDouble()) / frames;
      if (loose == null || avg > looseAvg) {
        loose = m;
        looseAvg = avg;
      }
    }
    if (loose == null || looseAvg < 2.5) return null;
    return "${loose["player_id"]}-es · átl. ${looseAvg.toStringAsFixed(1)} m";
  }

  // Tapadó emberfogó: a legkisebb átlagtávú védő (50+ kocka, <=1,5 m)
  // — az ő oldalát elzárás nélkül nem érdemes támadni.
  String? _tightMarker(Map<String, dynamic> r) {
    final list = (r["markers"] as List?) ?? const [];
    Map<String, dynamic>? tight;
    double tightAvg = 0;
    for (final e in list) {
      final m = e as Map<String, dynamic>;
      final frames = ((m["frames"] as num?) ?? 0).toInt();
      if (frames < 50) continue;
      final avg = (((m["dist_sum"] as num?) ?? 0).toDouble()) / frames;
      if (tight == null || avg < tightAvg) {
        tight = m;
        tightAvg = avg;
      }
    }
    if (tight == null || tightAvg > 1.5) return null;
    return "${tight["player_id"]}-es · átl. ${tightAvg.toStringAsFixed(1)} m";
  }

  // Beálló-terhelés: a támadások hányada megy a beállón át (6+
  // támadásból, 40%+ arány) — a backend-kulcsokkal azonos küszöb.
  String? _pivotUsage(Map<String, dynamic> r) {
    final total = ((r["pivot_total_attacks"] as num?) ?? 0).toInt();
    final piv = ((r["pivot_attacks"] as num?) ?? 0).toInt();
    if (total < 6) return null;
    final share = 100.0 * piv / total;
    if (share < 40.0) return null;
    var txt = "${share.toStringAsFixed(0)}% a beállón át";
    if (piv >= 3) {
      final pg = 100.0 * ((r["pivot_goals"] as num?) ?? 0).toInt() / piv;
      txt += " · gól ${pg.toStringAsFixed(0)}%";
    }
    return txt;
  }

  // Betörés-sáv: hol lépnek be a 9 m-en belülre (5+ betörésből,
  // 40%+ egy sávban) — a backend-kulcsokkal azonos küszöb.
  String? _breakLane(Map<String, dynamic> r) {
    final total = ((r["break_entries"] as num?) ?? 0).toInt();
    final lanes = (r["break_lanes"] as Map?)?.cast<String, dynamic>();
    if (total < 5 || lanes == null || lanes.isEmpty) return null;
    final top = lanes.entries.first;
    final n = (((top.value as Map)["entries"] as num?) ?? 0).toInt();
    final share = 100.0 * n / total;
    if (share < 40.0) return null;
    return "${top.key} · ${share.toStringAsFixed(0)}%";
  }

  // Passz-lánc: átlagos passz-szám + a legjobb gólarányú lánc-hossz
  // (6+ támadásból; a backend-kulcsokkal azonos küszöbök).
  String? _passChain(Map<String, dynamic> r) {
    final attacks = ((r["pass_attacks"] as num?) ?? 0).toInt();
    final total = ((r["pass_total"] as num?) ?? 0).toInt();
    if (attacks < 6) return null;
    var txt = "átl. ${(total / attacks).toStringAsFixed(1)} passz";
    final buckets = (r["pass_buckets"] as Map?)?.cast<String, dynamic>();
    String? bestLab;
    double bestPct = 0;
    for (final e in (buckets ?? const {}).entries) {
      final m = (e.value as Map).cast<String, dynamic>();
      final a = ((m["attacks"] as num?) ?? 0).toInt();
      final g = ((m["goals"] as num?) ?? 0).toInt();
      if (a < 4 || g == 0) continue;
      final pct = 100.0 * g / a;
      if (bestLab == null || pct > bestPct) {
        bestLab = e.key;
        bestPct = pct;
      }
    }
    if (bestLab != null && bestPct >= 40.0) {
      txt += " · top: $bestLab";
    }
    return txt;
  }

  // Rotáció: átlag bevetett játékos + alapember (a mérhető meccsekből;
  // a backend-kulcsokkal azonos küszöbök).
  String? _rotation(Map<String, dynamic> r) {
    final n = ((r["rotation_matches"] as num?) ?? 0).toInt();
    if (n == 0) return null;
    final used = ((r["rotation_used_sum"] as num?) ?? 0).toInt() / n;
    final reg = ((r["rotation_regulars_sum"] as num?) ?? 0).toInt() / n;
    if (used > 8.0 && used < 11.0) return null; // csak a kirívó érdekes
    final tag = used <= 8.0 ? "szűk pad" : "széles pad";
    return "${used.toStringAsFixed(0)} játékos "
        "(${reg.toStringAsFixed(0)} alapember) · $tag";
  }

  // Labdaszerző: a legtöbb szerzést hozó játékos (3+ szerzés) — a
  // backend-kulcsokkal azonos küszöb.
  String? _ballWinner(Map<String, dynamic> r) {
    final list = (r["ball_winners"] as List?) ?? const [];
    if (list.isEmpty) return null;
    final top = list.first as Map<String, dynamic>;
    final n = ((top["steals"] as num?) ?? 0).toInt();
    if (n < 3) return null;
    return "${top["player_id"]}-es · $n szerzés";
  }

  // Kapus-típus: kint álló vagy vonalon maradó kapus (100+ kocka) —
  // a backend-kulcsokkal azonos küszöbök.
  String? _gkDepth(Map<String, dynamic> r) {
    final frames = ((r["gk_depth_frames"] as num?) ?? 0).toInt();
    if (frames < 100) return null;
    final avg =
        (((r["gk_depth_sum_m"] as num?) ?? 0).toDouble()) / frames;
    if (avg >= 1.5) {
      return "kint álló · átl. ${avg.toStringAsFixed(1)} m";
    }
    if (avg <= 0.8) {
      return "vonalon maradó · átl. ${avg.toStringAsFixed(1)} m";
    }
    return null;
  }

  // Átmenet-támadás: labdaszerzés → gyors gól konverzió (4+ szerzés,
  // 2+ gyors gól, 30%+) — a backend-kulcsokkal azonos küszöb.
  String? _transOffense(Map<String, dynamic> r) {
    final steals = ((r["trans_steals"] as num?) ?? 0).toInt();
    final quick = ((r["trans_quick_goals"] as num?) ?? 0).toInt();
    if (steals < 4 || quick < 2) return null;
    final conv = 100.0 * quick / steals;
    if (conv < 30.0) return null;
    return "$quick/$steals · ${conv.toStringAsFixed(0)}% gyors gól";
  }

  // Kontra-befejező: a legtöbb lerohanás-gólt szerző játékos (2+ gól).
  String? _fbFinisher(Map<String, dynamic> r) {
    final list = (r["fb_finishers"] as List?) ?? const [];
    if (list.isEmpty) return null;
    final top = list.first as Map<String, dynamic>;
    final g = ((top["goals"] as num?) ?? 0).toInt();
    if (g < 2) return null;
    return "${top["player_id"]}. · $g gól";
  }

  // Indítás-célpont: akihez a kapus-indítások zöme fut ki (2+, és az
  // indítások fele — mint a kulcsokban).
  String? _outletTarget(Map<String, dynamic> r) {
    final list = (r["gk_outlet_targets"] as List?) ?? const [];
    final outlets = ((r["gk_outlets"] as num?) ?? 0).toInt();
    if (list.isEmpty || outlets < 2) return null;
    final top = list.first as Map<String, dynamic>;
    final n = ((top["n"] as num?) ?? 0).toInt();
    if (n < 2 || n / outlets < 0.5) return null;
    return "${top["player_id"]}. · $n/$outlets indítás";
  }

  // Fő lövő szokása: a legkoncentráltabb lövő (4+ lövés, 60%+ egy
  // zónából) — a backend-kulcsokkal azonos küszöb.
  String? _shooterHabit(Map<String, dynamic> r) {
    final list = (r["shooter_zones"] as List?) ?? const [];
    final per = <int, Map<String, int>>{};
    for (final e in list) {
      final m = e as Map<String, dynamic>;
      final pid = (m["player_id"] as num).toInt();
      final zone = m["zone"] as String;
      final byZone = per.putIfAbsent(pid, () => <String, int>{});
      byZone[zone] = (byZone[zone] ?? 0) + (m["shots"] as num).toInt();
    }
    int? bestPid;
    String? bestZone;
    var bestN = 0;
    var bestTotal = 0;
    per.forEach((pid, zones) {
      var total = 0;
      zones.forEach((_, n) => total += n);
      String? z;
      var n = 0;
      zones.forEach((zone, cnt) {
        if (cnt > n) {
          n = cnt;
          z = zone;
        }
      });
      if (total >= 4 && n / total >= 0.6 && n > bestN) {
        bestPid = pid;
        bestZone = z;
        bestN = n;
        bestTotal = total;
      }
    });
    if (bestPid == null) return null;
    final pct = (100.0 * bestN / bestTotal).round();
    return "$bestPid. · $bestZone $pct%";
  }

  // Ziccer-mérleg: nagy helyzeteikből (xG >= 0,5) hány lett gól.
  String? _bigChances(Map<String, dynamic> r) {
    final total = ((r["big_total"] as num?) ?? 0).toInt();
    if (total < 4) return null;
    final missed = ((r["big_missed"] as num?) ?? 0).toInt();
    return "${total - missed}/$total gól";
  }

  String? _shotPower(Map<String, dynamic> r) {
    final n = ((r["shot_speed_n"] as num?) ?? 0).toInt();
    if (n < 5) return null;
    final sum = ((r["shot_speed_sum_kmh"] as num?) ?? 0).toDouble();
    final peak = ((r["shot_speed_max_kmh"] as num?) ?? 0).toDouble();
    final avg = (sum / n).toStringAsFixed(0);
    return "átl. $avg · csúcs ${peak.toStringAsFixed(0)} km/h";
  }

  /// Támadás-oldal megoszlás: "bal 55% · közép 30% · jobb 15%" — csak
  /// elég támadó-kockánál (250+, ~10 mp).
  String? _attackSides(Map<String, dynamic> r) {
    final sf = (r["side_frames"] as Map?)?.cast<String, dynamic>();
    if (sf == null || sf.isEmpty) return null;
    var total = 0;
    sf.forEach((_, v) => total += ((v as num?) ?? 0).toInt());
    if (total < 250) return null;
    final parts = <String>[];
    for (final k in ["bal", "közép", "jobb"]) {
      final n = ((sf[k] as num?) ?? 0).toInt();
      parts.add("$k ${(100.0 * n / total).toStringAsFixed(0)}%");
    }
    return parts.join(" · ");
  }

  /// Melyik védőforma ellen konvertálnak a legrosszabbul — csak elég
  /// mintánál (2+ forma, formánként 4+ lövés).
  String? _weakFormation(Map<String, dynamic> r) {
    final vf = (r["vs_formation"] as Map?)?.cast<String, dynamic>();
    if (vf == null) return null;
    String? worst;
    double worstPct = 200.0;
    var pools = 0;
    vf.forEach((form, v) {
      final m = (v as Map).cast<String, dynamic>();
      final shots = ((m["shots"] as num?) ?? 0).toInt();
      if (shots < 4) return;
      pools += 1;
      final pct = 100.0 * ((m["goals"] as num?) ?? 0).toInt() / shots;
      if (pct < worstPct) {
        worstPct = pct;
        worst = form;
      }
    });
    if (pools < 2 || worst == null) return null;
    return "$worst (${worstPct.toStringAsFixed(0)}% gólarány)";
  }

  /// A hosszú (35 mp+) támadások gólaránya — csak elég mintánál (4+).
  String? _longAttackYield(Map<String, dynamic> r) {
    final de = (r["duration_eff"] as Map?)?.cast<String, dynamic>();
    final rec = (de?["hosszú (35 mp+)"] as Map?)?.cast<String, dynamic>();
    if (rec == null) return null;
    final n = ((rec["attacks"] as num?) ?? 0).toInt();
    if (n < 4) return null;
    final g = ((rec["goals"] as num?) ?? 0).toInt();
    return "${(100.0 * g / n).toStringAsFixed(0)}% gól ($n támadásból)";
  }

  String? _worstZone(Map<String, dynamic> r) {
    final zones = (r["def_zones"] as Map?)?.cast<String, dynamic>();
    if (zones == null || zones.isEmpty) return null;
    String? best;
    var bestKey = const [-1, -1];
    zones.forEach((z, v) {
      final m = (v as Map).cast<String, dynamic>();
      final key = [((m["goals"] as num?) ?? 0).toInt(),
                   ((m["shots"] as num?) ?? 0).toInt()];
      if (key[0] > bestKey[0] ||
          (key[0] == bestKey[0] && key[1] > bestKey[1])) {
        bestKey = key;
        best = z;
      }
    });
    final g = bestKey[0];
    return g >= 2 ? "$best ($g gól)" : best;
  }

  Widget _metricsCard(Map<String, dynamic> r) {
    // FONTOS: a segédfüggvény neve NEM lehet "num" — az kitakarná a beépített
    // num típust (fordítási hiba volt az első CI-buildben).
    String fmt(dynamic v, [String unit = ""]) =>
        v == null ? "—" : "${(v is num) ? (v % 1 == 0 ? v.toInt() : v) : v}$unit";
    final tiles = <List<String>>[
      ["Szervezett támadás", fmt(r["attack_share_pct"], "%")],
      ["Gyors indítás", fmt(r["fast_break_pct"], "%")],
      ["Labda átlagsebesség", fmt(r["avg_ball_speed_ms"], " m/s")],
      ["Átl. támadáshossz", fmt(r["avg_attack_duration_s"], " s")],
      ["Lövés / gól", "${fmt(r["shots"])} / ${fmt(r["goals"])}"],
      ["Gólarány", fmt(r["shot_efficiency_pct"], "%")],
      // Csere-minták: hány hullám, és mit hoznak a cseréik.
      if (((r["sub_rotations"] as num?) ?? 0) >= 2) ...[
        ["Cserehullám", "${r["sub_rotations"]}"],
        [
          "Cserék utáni mérleg",
          "${(((r["sub_after_for"] as num?) ?? 0) - ((r["sub_after_against"] as num?) ?? 0)) >= 0 ? "+" : ""}"
              "${((r["sub_after_for"] as num?) ?? 0) - ((r["sub_after_against"] as num?) ?? 0)} gól"
        ],
      ],
      // Irányító-függés: mennyire épül minden a fő szervezőre.
      if (r["playmaker_dependency"] != null) ...[
        [
          "Irányító-függés",
          "${r["playmaker_dependency"]}"
              "${r["playmaker_drop"] != null ? " (−${(100 * (r["playmaker_drop"] as num)).toStringAsFixed(0)} pont nélküle)" : ""}"
        ],
      ],
      // A védekezésük gyengéi: szabad lövés-arány + leglyukasabb zóna.
      if (((r["def_shots_against"] as num?) ?? 0) >= 4) ...[
        [
          "Szabad lövést enged",
          "${(100.0 * ((r["def_free_shots"] as num?) ?? 0) / (r["def_shots_against"] as num)).toStringAsFixed(0)}%"
        ],
        if (_worstZone(r) != null) ["Lyukas zóna", _worstZone(r)!],
      ],
      // Helyzetminőség: várható gól + befejezés-eltérés (ha számolható).
      if (((r["xg"] as num?) ?? 0) > 0) ...[
        ["Várható gól (xG)", (r["xg"] as num).toStringAsFixed(1)],
        [
          "Befejezés (gól−xG)",
          "${((r["xg_diff"] as num?) ?? 0) >= 0 ? "+" : ""}"
              "${((r["xg_diff"] as num?) ?? 0).toStringAsFixed(1)}"
        ],
      ],
      [
        "Labdaeladás",
        fmt(r["turnovers"]) +
            (((r["turnover_total"] as num?) ?? 0) >= 5
                ? " (${(100.0 * ((r["turnover_front"] as num?) ?? 0) / (r["turnover_total"] as num)).toStringAsFixed(0)}% elöl)"
                : "")
      ],
      if (_gkWeakZone(r) != null) ["Kapus gyenge sarka", _gkWeakZone(r)!],
      if (((r["possession_pct"] as num?) ?? 0) > 0)
        ["Labdabirtoklás", "${(r["possession_pct"] as num).toStringAsFixed(0)}%"],
      if (((r["top_assist_count"] as num?) ?? 0) >= 2)
        ["Gólpassz-vezér", "${r["top_assist_count"]} gólpassz"],
      if (_passAxis(r) != null) ["Passz-tengely", _passAxis(r)!],
      if (((r["defensive_pressure_m"] as num?) ?? 0) > 0)
        ["Véd. nyomás", "${(r["defensive_pressure_m"] as num).toStringAsFixed(1)} m"],
      if (((r["blocks"] as num?) ?? 0) >= 3)
        ["Blokkolt lövés", "${r["blocks"]}"],
      // Kapusuk fogott ziccerei — ugyanaz a küszöb (2+), mint a kulcsokban.
      if (((r["gk_big_saves"] as num?) ?? 0) >= 2)
        ["Bravúr-védés", "${r["gk_big_saves"]}"],
      if (_gkOutlet(r) != null) ["Kapus-indítás", _gkOutlet(r)!],
      if (_shooterHabit(r) != null) ["Fő lövő", _shooterHabit(r)!],
      if (_topBlocker(r) != null) ["Fal kulcsa", _topBlocker(r)!],
      if (_sevenTaker(r) != null) ["Hetes-dobó", _sevenTaker(r)!],
      if (_discipline(r) != null) ["Fegyelem", _discipline(r)!],
      if (_looseMarker(r) != null) ["Laza emberfogó", _looseMarker(r)!],
      if (_tightMarker(r) != null)
        ["Tapadó emberfogó", _tightMarker(r)!],
      if (_pivotUsage(r) != null) ["Beálló-terhelés", _pivotUsage(r)!],
      if (_breakLane(r) != null) ["Betörés-sáv", _breakLane(r)!],
      if (_passChain(r) != null) ["Passz-lánc", _passChain(r)!],
      if (_rotation(r) != null) ["Rotáció", _rotation(r)!],
      if (_ballWinner(r) != null) ["Labdaszerző", _ballWinner(r)!],
      if (_gkDepth(r) != null) ["Kapus-típus", _gkDepth(r)!],
      if (_transOffense(r) != null)
        ["Átmenet-támadás", _transOffense(r)!],
      if (_restart(r) != null) ["Szünet-kezdés", _restart(r)!],
      if (_leadPace(r) != null) ["Előny-kezelés", _leadPace(r)!],
      if (_bestFigure(r) != null) ["Fő figura", _bestFigure(r)!],
      if (_attackWidth(r) != null)
        ["Támadás-szélesség", _attackWidth(r)!],
      if (_fbFinisher(r) != null) ["Kontra-befejező", _fbFinisher(r)!],
      if (_outletTarget(r) != null)
        ["Indítás-célpont", _outletTarget(r)!],
      if (_pace(r) != null) ["Tempó", _pace(r)!],
      if (_gkXg(r) != null) ["Kapus-xG", _gkXg(r)!],
      if (_goalSource(r) != null) ["Gól-forrás", _goalSource(r)!],
      if (_recovery(r) != null) ["Visszaérés", _recovery(r)!],
      if (_postGoals(r) != null) ["Gól-posztok", _postGoals(r)!],
      if (_bigChances(r) != null) ["Ziccer-mérleg", _bigChances(r)!],
      if (_halfPattern(r) != null) ["Félidő-mérleg", _halfPattern(r)!],
      if (_shotPower(r) != null) ["Lövés-erő", _shotPower(r)!],
      if (_attackSides(r) != null) ["Támadás-oldal", _attackSides(r)!],
      if (_weakFormation(r) != null)
        ["Ez a fal fogja meg őket", _weakFormation(r)!],
      if (_longAttackYield(r) != null)
        ["Hosszú támadás hozama", _longAttackYield(r)!],
      if (((r["clutch_matches"] as num?) ?? 0) >= 1)
        [
          "Hajrá-mérleg",
          "${(((r["clutch_goals_for"] as num?) ?? 0).toInt() - ((r["clutch_goals_against"] as num?) ?? 0).toInt()) >= 0 ? "+" : ""}"
              "${((r["clutch_goals_for"] as num?) ?? 0).toInt() - ((r["clutch_goals_against"] as num?) ?? 0).toInt()} gól"
        ],
      ["Figurák", fmt(r["num_figures"])],
    ];
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("MUTATÓK", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.md),
          Wrap(
            spacing: AppSpacing.lg,
            runSpacing: AppSpacing.md,
            children: [for (final t in tiles) _metricTile(t[0], t[1])],
          ),
        ],
      ),
    );
  }

  Widget _metricTile(String label, String value) {
    return SizedBox(
      width: 150,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value, style: AppText.value.copyWith(fontSize: 20, color: AppColors.accent)),
          const SizedBox(height: 2),
          Text(label, style: AppText.label.copyWith(fontSize: 11)),
        ],
      ),
    );
  }

  /// Lövési zónák: honnan lőnek és honnan eredményesek (gól/lövés zónánként).
  Widget _shotZonesCard(Map<String, dynamic> r) {
    final zones = (r["shot_zones"] as Map?)?.cast<String, dynamic>() ?? {};
    // Összes lövés a sáv-arányokhoz.
    int total = 0;
    for (final v in zones.values) {
      total += ((v as Map)["shots"] as num?)?.toInt() ?? 0;
    }
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("HONNAN LŐNEK (gól/lövés)", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.md),
          if (zones.isEmpty)
            Text("Nincs elég lövés-minta.", style: AppText.label)
          else
            for (final e in zones.entries)
              _zoneBar(e.key, (e.value as Map).cast<String, dynamic>(), total),
        ],
      ),
    );
  }

  /// Védekezési zónák: honnan KAPJÁK a lövéseket, és hol hagyják
  /// szabadon a lövőt — a "hova játssz ellene" képernyős párja a
  /// nyomtatott jelentés blokkjának.
  Widget _defZonesCard(Map<String, dynamic> r) {
    final zones = (r["def_zones"] as Map?)?.cast<String, dynamic>() ?? {};
    int total = 0;
    for (final v in zones.values) {
      total += ((v as Map)["shots"] as num?)?.toInt() ?? 0;
    }
    if (zones.isEmpty || total < 4) return const SizedBox.shrink();
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("HONNAN KAPJÁK A LÖVÉSEKET (védekezésük)",
              style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.md),
          for (final e in zones.entries)
            _zoneBar(e.key, (e.value as Map).cast<String, dynamic>(), total,
                showFree: true),
          const SizedBox(height: 4),
          Text("szabad: a lövés pillanatában nem volt védő a lövő 2 m-es "
              "körzetében",
              style: AppText.label.copyWith(
                  fontSize: 10, color: AppColors.textFaint)),
        ],
      ),
    );
  }

  Widget _zoneBar(String zone, Map<String, dynamic> rec, int total,
      {bool showFree = false}) {
    final shots = (rec["shots"] as num?)?.toInt() ?? 0;
    final goals = (rec["goals"] as num?)?.toInt() ?? 0;
    final frac = total > 0 ? shots / total : 0.0;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(children: [
        SizedBox(width: 110, child: Text(zone, style: AppText.value.copyWith(fontSize: 13))),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: frac.clamp(0.0, 1.0),
              minHeight: 8,
              backgroundColor: AppColors.surfaceAlt,
              valueColor: const AlwaysStoppedAnimation(AppColors.gold),
            ),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        SizedBox(
            width: showFree ? 108 : 44,
            child: Text(
                showFree &&
                        (((rec["free"] as num?)?.toInt() ?? 0) > 0)
                    ? "$goals/$shots · szabad: ${rec["free"]}"
                    : "$goals/$shots",
                textAlign: TextAlign.right,
                style: AppText.label.copyWith(fontSize: 12))),
      ]),
    );
  }

  /// Figura-egyezés: az ellenfél támadásai közül melyik egyezik egy MENTETT
  /// figurával a könyvtárunkból ("a Beúszós keresztet játszották 4x").
  Widget _playbookCard(Map<String, dynamic> pm) {
    final matched = (pm["matched"] as Map?)?.cast<String, dynamic>() ?? {};
    final total = (pm["total_attacks"] as num?)?.toInt() ?? 0;
    final unmatched = (pm["unmatched"] as num?)?.toInt() ?? 0;
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.menu_book_outlined, size: 16, color: AppColors.accent),
            const SizedBox(width: 8),
            Text("ISMERT FIGURÁIK (a könyvtárunkból)", style: AppText.sectionLabel),
          ]),
          const SizedBox(height: AppSpacing.md),
          if (total == 0)
            Text("Nincs felismert támadás-szakasz ebben a meccsben.", style: AppText.label)
          else if (matched.isEmpty)
            Text("Egyik támadásuk sem egyezik mentett figurával "
                "($total támadás). Ments figurákat a Figura-tervezőben.",
                style: AppText.label)
          else ...[
            for (final e in matched.entries)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(children: [
                  const Icon(Icons.check_circle_outline, size: 15, color: AppColors.accent),
                  const SizedBox(width: 8),
                  Expanded(child: Text(e.key, style: AppText.value.copyWith(fontSize: 13))),
                  Text("${e.value}×", style: AppText.value.copyWith(color: AppColors.accent)),
                ]),
              ),
            const SizedBox(height: 6),
            Text("$total támadásból $unmatched ismeretlen mintájú.",
                style: AppText.label.copyWith(fontSize: 11)),
          ],
        ],
      ),
    );
  }

  Widget _defenseCard(Map<String, dynamic> r) {
    final dist = (r["defense_distribution"] as Map?)?.cast<String, dynamic>() ?? {};
    final entries = dist.entries.toList()
      ..sort((a, b) => ((b.value as num).toDouble()).compareTo((a.value as num).toDouble()));
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("VÉDEKEZÉS (amikor ők védenek)", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.md),
          if (entries.isEmpty)
            Text("Nincs elég védekező minta.", style: AppText.label)
          else
            for (final e in entries) _defenseBar(e.key, (e.value as num).toDouble()),
        ],
      ),
    );
  }

  Widget _defenseBar(String label, double pct) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(children: [
        SizedBox(width: 56, child: Text(label, style: AppText.value.copyWith(fontSize: 13))),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (pct / 100).clamp(0.0, 1.0),
              minHeight: 8,
              backgroundColor: AppColors.surfaceAlt,
              valueColor: const AlwaysStoppedAnimation(AppColors.accent),
            ),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        SizedBox(width: 44, child: Text("${pct.toStringAsFixed(0)}%",
            textAlign: TextAlign.right, style: AppText.label.copyWith(fontSize: 12))),
      ]),
    );
  }

  Widget _keyPlayersCard(Map<String, dynamic> r) {
    final players = (r["key_players"] as List?) ?? const [];
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("KULCSJÁTÉKOSOK", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.md),
          if (players.isEmpty)
            Text("Több meccs felderítése pontosítja a játékos-profilt.", style: AppText.label)
          else
            for (final p in players) _playerRow(p as Map<String, dynamic>),
        ],
      ),
    );
  }

  Widget _playerRow(Map<String, dynamic> p) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(children: [
        CircleAvatar(
          radius: 14,
          backgroundColor: AppColors.surfaceAlt,
          child: Text("${p["track_id"]}", style: AppText.label.copyWith(color: AppColors.textPrimary, fontSize: 12)),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(child: Text("${p["role"] ?? "játékos"}", style: AppText.value.copyWith(fontSize: 13))),
        Text("birtoklás ${p["possession_frames"] ?? 0} · ${p["distance_m"] ?? 0} m",
            style: AppText.label.copyWith(fontSize: 11)),
      ]),
    );
  }
}
