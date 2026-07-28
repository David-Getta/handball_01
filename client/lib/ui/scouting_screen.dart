/// Ellenfél-felderítő jelentés — a szoftver "headline" haszna edzőknek.
///
/// Egy csapatról (a felderített ellenfélről) ad egy edzői nyelven megírt
/// jelentést: hogyan játssz ellenük (kulcsok), erősségek/gyengeségek, védekezés,
/// tempó, befejezés, kulcsjátékosok. A backend /scouting végpontból tölt.
library;

import "dart:io";
import "dart:math";

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

  // Kezdés-profil: milyen arányban szerzik a meccs első gólját + a korai
  // (első 6 gól) mérleg — 3+ mért meccsnél, a kirívó kezdés érdekes (a
  // felderítési kulccsal azonos küszöb).
  String? _opening(Map<String, dynamic> r) {
    final n = ((r["open_first_matches"] as num?) ?? 0).toInt();
    if (n < 3) return null;
    final yes = ((r["open_first_yes"] as num?) ?? 0).toInt();
    final f = ((r["open_for"] as num?) ?? 0).toInt();
    final a = ((r["open_against"] as num?) ?? 0).toInt();
    final rate = 100.0 * yes / n;
    final bal = f - a;
    if (rate >= 65.0 || bal >= 3) {
      return "${rate.round()}% nyitógól ($f–$a korai) · erős kezdők";
    }
    if (rate <= 35.0 || bal <= -3) {
      return "${rate.round()}% nyitógól ($f–$a korai) · lassan kezdenek";
    }
    return null;
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

  // Lövés-távolság profil: melyik sávból lő a legtöbbet, milyen
  // gólaránnyal (8+ lövés kell hozzá; a backend-kulcsokkal azonos küszöb).
  String? _shotRange(Map<String, dynamic> r) {
    final close = ((r["sr_close_shots"] as num?) ?? 0).toInt();
    final mid = ((r["sr_mid_shots"] as num?) ?? 0).toInt();
    final far = ((r["sr_far_shots"] as num?) ?? 0).toInt();
    final total = close + mid + far;
    if (total < 8) return null;
    final closeG = ((r["sr_close_goals"] as num?) ?? 0).toInt();
    final farG = ((r["sr_far_goals"] as num?) ?? 0).toInt();
    final farShare = 100.0 * far / total;
    final closeShare = 100.0 * close / total;
    if (farShare >= 45.0) {
      final pct = far > 0 ? " · ${(100.0 * farG / far).round()}% gól" : "";
      return "${farShare.round()}% távoli (átlövés)$pct";
    }
    if (closeShare >= 45.0) {
      final pct =
          close > 0 ? " · ${(100.0 * closeG / close).round()}% gól" : "";
      return "${closeShare.round()}% közeli (beálló/szélső)$pct";
    }
    return null; // kiegyensúlyozott eloszlás — nem kirívó
  }

  // Kapusuk gyenge sávja: melyik lövés-távolságra véd a legkevésbé
  // (legalább 4 kaputra érkezett lövés, 50% alatti védés) — ide érdemes
  // lőni. A backend-kulcsokkal azonos küszöb.
  String? _gkWeakRange(Map<String, dynamic> r) {
    final bands = <List<Object>>[
      ["közelről", (r["gk_close_faced"] as num?) ?? 0,
        (r["gk_close_saves"] as num?) ?? 0],
      ["közép-távból", (r["gk_mid_faced"] as num?) ?? 0,
        (r["gk_mid_saves"] as num?) ?? 0],
      ["távolról", (r["gk_far_faced"] as num?) ?? 0,
        (r["gk_far_saves"] as num?) ?? 0],
    ];
    String? worstLbl;
    double worstPct = 100.0;
    int worstFaced = 0, worstSaves = 0;
    for (final b in bands) {
      final faced = (b[1] as num).toInt();
      final saves = (b[2] as num).toInt();
      if (faced < 4) continue;
      final pct = 100.0 * saves / faced;
      if (pct < worstPct) {
        worstPct = pct;
        worstLbl = b[0] as String;
        worstFaced = faced;
        worstSaves = saves;
      }
    }
    if (worstLbl == null || worstPct >= 50.0) return null;
    return "$worstLbl gyenge · ${worstPct.round()}% védés "
        "($worstSaves/$worstFaced)";
  }

  // Kapu-sarok: hova megy a góljaik zöme (bal/közép/jobb, a lövő
  // szemszögéből) — 6+ gólból 50%+ egy oldalra. A backend-kulcsokkal
  // azonos küszöb; a kapus felkészülhet rá.
  String? _goalPlacement(Map<String, dynamic> r) {
    final bal = ((r["place_bal"] as num?) ?? 0).toInt();
    final kozep = ((r["place_kozep"] as num?) ?? 0).toInt();
    final jobb = ((r["place_jobb"] as num?) ?? 0).toInt();
    final total = bal + kozep + jobb;
    if (total < 6) return null;
    final bands = <List<Object>>[
      ["bal", bal],
      ["közép", kozep],
      ["jobb", jobb],
    ];
    bands.sort((a, b) => (b[1] as int).compareTo(a[1] as int));
    final domLbl = bands.first[0] as String;
    final domN = bands.first[1] as int;
    final share = 100.0 * domN / total;
    if (share < 50.0) return null;
    return "${share.round()}% $domLbl kapuoldal ($domN/$total)";
  }

  // Szélső-befejezés: a szélső (éles) szögből leadott lövések gólaránya
  // (4+ szélső-lövés) — erős vagy gyenge szélső-játék. A backend-kulcsokkal
  // azonos küszöb.
  String? _wingFinishing(Map<String, dynamic> r) {
    final shots = ((r["wing_fin_shots"] as num?) ?? 0).toInt();
    final goals = ((r["wing_fin_goals"] as num?) ?? 0).toInt();
    if (shots < 4) return null;
    final pct = 100.0 * goals / shots;
    final tag = pct >= 55.0
        ? "veszélyes"
        : pct <= 25.0
            ? "gyenge"
            : null;
    if (tag == null) return null;
    return "$tag · ${pct.round()}% ($goals/$shots)";
  }

  // Védekezési vonal magassága: felfutó (agresszív) vagy mély (passzív)
  // fal — a felállt védekezés átlagos mélysége a saját kaputól (100+ mért
  // kocka). A backend-kulcsokkal azonos küszöb.
  String? _defLine(Map<String, dynamic> r) {
    final frames = ((r["defline_frames"] as num?) ?? 0).toInt();
    if (frames < 100) return null;
    final avg = ((r["defline_sum_m"] as num?) ?? 0).toDouble() / frames;
    if (avg >= 8.5) {
      return "felfutó (agresszív) · ${avg.toStringAsFixed(1)} m";
    }
    if (avg <= 6.5) {
      return "mély (passzív) · ${avg.toStringAsFixed(1)} m";
    }
    return null; // kiegyensúlyozott — nem kirívó
  }

  // Passz-irány: vertikális (előre) vagy türelmes (oldalra) építkezés
  // (30+ mért passz). A backend-kulcsokkal azonos küszöb.
  String? _passDirection(Map<String, dynamic> r) {
    final passes = ((r["pdir_passes"] as num?) ?? 0).toInt();
    if (passes < 30) return null;
    final fwd = ((r["pdir_forward"] as num?) ?? 0).toInt();
    final pct = 100.0 * fwd / passes;
    final tag = pct >= 45.0
        ? "vertikális"
        : pct <= 20.0
            ? "türelmes körözés"
            : null;
    if (tag == null) return null;
    return "$tag · ${pct.round()}% előre-passz";
  }

  // Gólpassz-forrás: honnan készítik elő a góljaik zömét (szél/közép/
  // hátsó), 4+ gólpasszból 50%+ egy forrásból. A backend-kulcsokkal azonos
  // küszöb.
  String? _assistSource(Map<String, dynamic> r) {
    final szel = ((r["asrc_szel"] as num?) ?? 0).toInt();
    final kozep = ((r["asrc_kozep"] as num?) ?? 0).toInt();
    final hatso = ((r["asrc_hatso"] as num?) ?? 0).toInt();
    final total = szel + kozep + hatso;
    if (total < 4) return null;
    final bands = <List<Object>>[
      ["szélről", szel],
      ["középről", kozep],
      ["hátsó sorból", hatso],
    ];
    bands.sort((a, b) => (b[1] as int).compareTo(a[1] as int));
    final domLbl = bands.first[0] as String;
    final domN = bands.first[1] as int;
    final share = 100.0 * domN / total;
    if (share < 50.0) return null;
    return "${share.round()}% $domLbl ($domN/$total)";
  }

  // Második roham: a kimaradt lövések utáni lepattanó-visszaszerzés aránya
  // (6+ kimaradás; a backend-kulcsokkal azonos küszöb). Csak a kirívó
  // (harcolnak / nem mennek rá) érdekes.
  String? _secondChance(Map<String, dynamic> r) {
    final misses = ((r["sc_misses"] as num?) ?? 0).toInt();
    if (misses < 6) return null;
    final second = ((r["sc_second"] as num?) ?? 0).toInt();
    final goals = ((r["sc_goals"] as num?) ?? 0).toInt();
    final pct = 100.0 * second / misses;
    if (pct >= 25.0) {
      final g = goals > 0 ? " · $goals gól" : "";
      return "${pct.round()}% visszaszerzés ($second/$misses)$g · harcol";
    }
    if (pct <= 8.0) {
      return "${pct.round()}% visszaszerzés ($second/$misses) · nem megy rá";
    }
    return null;
  }

  // Kapus-forma félidőnként: a védés% változása a 2. félidőre
  // (félidőnként 4+ kapura tartó lövésnél; a backend-kulccsal azonos
  // küszöb) — csak a kirívó (esik / formába lendül) érdekes.
  String? _gkSaveFade(Map<String, dynamic> r) {
    final fhFaced = ((r["gsf_fh_faced"] as num?) ?? 0).toInt();
    final shFaced = ((r["gsf_sh_faced"] as num?) ?? 0).toInt();
    if (fhFaced < 4 || shFaced < 4) return null;
    final fh = 100.0 * ((r["gsf_fh_saves"] as num?) ?? 0).toInt() / fhFaced;
    final sh = 100.0 * ((r["gsf_sh_saves"] as num?) ?? 0).toInt() / shFaced;
    if (fh - sh >= 15.0) {
      return "${fh.round()}% → ${sh.round()}% védés · a 2. félidőre esik";
    }
    if (sh - fh >= 15.0) {
      return "${fh.round()}% → ${sh.round()}% védés · formába lendül";
    }
    return null;
  }

  // Előny-őrzés: 3+ gólos ellépéseik sorsa — elengedik-e a vezetést,
  // vagy mindig megtartják (2+ ellépésnél már beszédes a "megtartja").
  String? _leadProtection(Map<String, dynamic> r) {
    final led = ((r["lp_led"] as num?) ?? 0).toInt();
    if (led < 1) return null;
    final blown = ((r["lp_blown"] as num?) ?? 0).toInt();
    final biggest = ((r["lp_biggest"] as num?) ?? 0).toInt();
    if (blown >= 1) {
      return "$led ellépésből $blown elengedve (volt $biggest gólos is) · "
          "sose add fel ellenük";
    }
    if (led >= 2) {
      return "$led ellépés, mind megtartva · nem szabad hagyni ellépni";
    }
    return null;
  }

  // Kihagyott ziccer ára: a kihagyás után fél percen belül kapott gólok
  // aránya (4+ kihagyásnál; a backend-kulccsal azonos küszöb).
  String? _missPunishment(Map<String, dynamic> r) {
    final misses = ((r["bcp_misses"] as num?) ?? 0).toInt();
    if (misses < 4) return null;
    final punished = ((r["bcp_punished"] as num?) ?? 0).toInt();
    if (100.0 * punished / misses >= 40.0) {
      return "$misses kihagyott ziccerből $punished után gyors büntetés · "
          "a kihagyásuk indítás-jel";
    }
    return null;
  }

  // Tempó-esés: a támadás/perc esése a 2. félidőre (8+ mért perc
  // félidőnként; a backend-kulccsal azonos küszöbök).
  String? _paceFade(Map<String, dynamic> r) {
    final fhMin = ((r["tpf_fh_min"] as num?) ?? 0).toDouble();
    final shMin = ((r["tpf_sh_min"] as num?) ?? 0).toDouble();
    if (fhMin < 8.0 || shMin < 8.0) return null;
    final fh = ((r["tpf_fh_attacks"] as num?) ?? 0).toInt() / fhMin;
    final sh = ((r["tpf_sh_attacks"] as num?) ?? 0).toInt() / shMin;
    if (fh - sh >= 0.2) {
      return "${fh.toStringAsFixed(1)} → ${sh.toStringAsFixed(1)} "
          "támadás/perc a 2. félidőre · elfogy a lábuk";
    }
    return null;
  }

  // Félidei hátrányból fordítás: a hátrányos félidők mérlege (2+ ilyen
  // meccsnél; a backend-kulccsal azonos küszöbök).
  String? _htComeback(Map<String, dynamic> r) {
    final behind = ((r["htc_behind"] as num?) ?? 0).toInt();
    if (behind < 2) return null;
    final turned = ((r["htc_turned"] as num?) ?? 0).toInt();
    final saved = ((r["htc_saved"] as num?) ?? 0).toInt();
    if (turned == 0 && saved == 0) {
      return "$behind félidei hátrányból 0 mentve · "
          "a félidei előny ellenük dönt";
    }
    if (2 * turned >= behind) {
      return "$behind félidei hátrányból $turned fordítás · "
          "60 perces meccs kell ellenük";
    }
    return null;
  }

  // Holtpont-mérleg: az egál-pillanatok mérlege (4+ holtpontnál; a
  // backend-kulccsal azonos küszöbök).
  String? _parityBreaks(Map<String, dynamic> r) {
    final ties = ((r["pb_ties"] as num?) ?? 0).toInt();
    if (ties < 4) return null;
    final won = ((r["pb_won"] as num?) ?? 0).toInt();
    final rate = 100.0 * won / ties;
    if (rate >= 65.0) {
      return "$ties holtpontból $won az övék · ne csússz velük egálba";
    }
    if (rate <= 35.0) {
      return "$ties holtpontból csak $won az övék · egálnál ők remegnek";
    }
    return null;
  }

  // Sorozat-törés: az elszenvedett 3+ gólos sorozatok átlag-hossza (3+
  // sorozatnál; a backend-kulccsal azonos küszöbök).
  String? _runContainment(Map<String, dynamic> r) {
    final suffered = ((r["rn_suffered"] as num?) ?? 0).toInt();
    if (suffered < 3) return null;
    final goals = ((r["rn_suffered_goals"] as num?) ?? 0).toInt();
    final avg = goals / suffered;
    if (avg >= 4.5) {
      return "$suffered sorozat fut el ellenük (átlag "
          "${avg.toStringAsFixed(1)} gól) · a 2-0-t nyomd meg";
    }
    if (avg <= 3.4) {
      return "a sorozatot 3-nál törik (átlag "
          "${avg.toStringAsFixed(1)} gól) · sorozattal nem ölöd meg";
    }
    return null;
  }

  // Bravúr utáni lendület: a nagy védésből lett-e gyors gól elöl (4+
  // bravúrnál; a backend-kulccsal azonos küszöbök).
  String? _bigSaveMomentum(Map<String, dynamic> r) {
    final saves = ((r["bsm_saves"] as num?) ?? 0).toInt();
    if (saves < 4) return null;
    final sparked = ((r["bsm_sparked"] as num?) ?? 0).toInt();
    final rate = 100.0 * sparked / saves;
    if (rate >= 40.0) {
      return "$saves bravúrból $sparked gyors gól elöl · "
          "a rossz lövés ellenük kontra";
    }
    if (sparked == 0) {
      return "$saves bravúrból 0 gyors gól · "
          "a kapusuk megfog, de nem büntet";
    }
    return null;
  }

  // Befejezés-esés: a gólra váltás esése a 2. félidőre (8+ kísérlet
  // félidőnként; a backend-kulccsal azonos küszöbök).
  String? _finishFade(Map<String, dynamic> r) {
    final fhShots = ((r["ff_fh_shots"] as num?) ?? 0).toInt();
    final shShots = ((r["ff_sh_shots"] as num?) ?? 0).toInt();
    if (fhShots < 8 || shShots < 8) return null;
    final fh = 100.0 * ((r["ff_fh_goals"] as num?) ?? 0).toInt() / fhShots;
    final sh = 100.0 * ((r["ff_sh_goals"] as num?) ?? 0).toInt() / shShots;
    if (fh - sh >= 15.0) {
      return "${fh.toStringAsFixed(0)}% → ${sh.toStringAsFixed(0)}% "
          "gólra váltás a 2. félidőre · fáradtan nem ül a lövésük";
    }
    return null;
  }

  // Célzás-pontosság: a kaput érő lövések aránya (10+ kísérletnél; a
  // backend-kulccsal azonos küszöbök).
  String? _shotAccuracy(Map<String, dynamic> r) {
    final attempts = ((r["ac_attempts"] as num?) ?? 0).toInt();
    if (attempts < 10) return null;
    final onTarget = ((r["ac_on_target"] as num?) ?? 0).toInt();
    final pct = 100.0 * onTarget / attempts;
    if (pct <= 55.0) {
      return "lövéseik ${pct.toStringAsFixed(0)}%-a ér kaput · "
          "a mellé lövés = a ti indításotok";
    }
    if (pct >= 80.0) {
      return "lövéseik ${pct.toStringAsFixed(0)}%-a kaput ér · "
          "blokk-munka kötelező";
    }
    return null;
  }

  // Oldal-részrehajlás: a szélső-sávos lövések oldal-megoszlása (10+
  // szélső-sávos lövésnél; a backend-kulccsal azonos küszöbök).
  String? _sideBias(Map<String, dynamic> r) {
    final left = ((r["sb_left"] as num?) ?? 0).toInt();
    final right = ((r["sb_right"] as num?) ?? 0).toInt();
    final wings = left + right;
    if (wings < 10) return null;
    final pct = 100.0 * (left > right ? left : right) / wings;
    if (pct < 65.0) return null;
    final side = left >= right ? "bal" : "jobb";
    return "szélső-lövéseik ${pct.toStringAsFixed(0)}%-a a $side "
        "oldalról · told el a falat";
  }

  // Ritmus-egyhangúság: a támadás-hossz relatív szórása (12+
  // támadásnál; a backend-kulccsal azonos küszöbök).
  String? _attackRhythm(Map<String, dynamic> r) {
    final n = ((r["ar_n"] as num?) ?? 0).toInt();
    final sum = ((r["ar_sum_s"] as num?) ?? 0).toDouble();
    final sumsq = ((r["ar_sumsq_s"] as num?) ?? 0).toDouble();
    if (n < 12 || sum <= 0) return null;
    final avg = sum / n;
    var variance = sumsq / n - avg * avg;
    if (variance < 0) variance = 0;
    final sd = sqrt(variance);
    if (avg > 0 && sd / avg <= 0.35) {
      return "belső óra: átlag ${avg.toStringAsFixed(0)} mp "
          "(±${sd.toStringAsFixed(0)}) · időzített kettőzés";
    }
    return null;
  }

  // Lövő-koncentráció: a fő lövő részaránya a lövésekből (12+
  // azonosított lövésnél, 35%+ részaránynál; a backend-kulccsal
  // azonos küszöbök).
  String? _shotConcentration(Map<String, dynamic> r) {
    final shots = ((r["sc_shots"] as num?) ?? 0).toInt();
    final top = ((r["sc_top_shots"] as num?) ?? 0).toInt();
    if (shots < 12) return null;
    final share = top / shots;
    if (share < 0.35) return null;
    return "a fő lövő adja a lövések "
        "${(100.0 * share).toStringAsFixed(0)}%-át ($top/$shots) · "
        "emberfogás/kettőzés";
  }

  // Játékos-mérleg: kinek a pályán léte alatt a legjobb a
  // gólkülönbségük (5+ perc, 0.15 gól/perc felett; a backend-kulccsal
  // azonos küszöbök).
  String? _plusMinus(Map<String, dynamic> r) {
    final list = r["player_plus_minus"];
    final fps = ((r["pm_fps"] as num?) ?? 25.0).toDouble();
    if (list is! List || fps <= 0) return null;
    Map? best;
    double bestRate = 0.0;
    double bestMin = 0.0;
    for (final e in list) {
      if (e is! Map) continue;
      final frames = ((e["frames"] as num?) ?? 0).toDouble();
      final minutes = frames / fps / 60.0;
      if (minutes < 5.0) continue;
      final diff = ((e["for"] as num?) ?? 0).toInt() -
          ((e["against"] as num?) ?? 0).toInt();
      final rate = diff / minutes;
      if (best == null || rate > bestRate) {
        best = e;
        bestRate = rate;
        bestMin = minutes;
      }
    }
    if (best == null || bestRate < 0.15) return null;
    return "a(z) ${best["player_id"]} játékosukkal megy a legjobban: "
        "${best["for"]}-${best["against"]} mérleg "
        "${bestMin.toStringAsFixed(0)} perc alatt · "
        "rá kell menni védekezésben is";
  }

  // Célba vett védő: melyik védőjük előtt megy be a legtöbb lövés (4+
  // rá eső lövés, a csapatátlaguknál 15 százalékponttal magasabb
  // gólarány; a backend-kulccsal azonos küszöbök).
  String? _targetedDefender(Map<String, dynamic> r) {
    final list = r["targeted_defenders"];
    final shots = ((r["tdf_shots"] as num?) ?? 0).toInt();
    final goals = ((r["tdf_goals"] as num?) ?? 0).toInt();
    if (list is! List || shots < 4) return null;
    final avg = 100.0 * goals / shots;
    Map? weak;
    double weakGap = 0.0;
    for (final e in list) {
      if (e is! Map) continue;
      final n = ((e["shots"] as num?) ?? 0).toInt();
      if (n < 4) continue;
      final gap = 100.0 * ((e["goals"] as num?) ?? 0).toInt() / n - avg;
      if (gap >= 15.0 && (weak == null || gap > weakGap)) {
        weak = e;
        weakGap = gap;
      }
    }
    if (weak == null) return null;
    final who = weak["jersey"] != null
        ? "${weak["jersey"]}-es"
        : "${weak["player_id"]} azonosítójú";
    return "a(z) $who védőjük előtt megy be a legtöbb lövés: "
        "${weak["goals"]}/${weak["shots"]} · a csapatátlaguk felett "
        "${weakGap.toStringAsFixed(0)} pp · oda vigyétek a "
        "befejezéseket (elzárás rá, az ő oldalán a beálló)";
  }

  // Időkérés-időzítés: hány kapott gól után kérnek időt (2+ időkérés,
  // 1,5 alatt gyors fék, 2,5 felett későn; a backend-kulccsal azonos
  // küszöbök).
  String? _timeoutTiming(Map<String, dynamic> r) {
    final n = ((r["tot_timeouts"] as num?) ?? 0).toInt();
    final before = ((r["tot_sum_before"] as num?) ?? 0).toInt();
    final late = ((r["tot_late"] as num?) ?? 0).toInt();
    if (n < 2) return null;
    final avg = before / n;
    final latePct = 100.0 * late / n;
    if (avg <= 1.5) {
      return "korán fékeznek: átlag ${avg.toStringAsFixed(1)} kapott "
          "gól után kérnek időt ($n időkérés) · gyors gólváltásra "
          "kell játszani, nem egy nagy hullámra";
    }
    if (avg >= 2.5) {
      return "hagyják elszaladni a sorozatot: átlag "
          "${avg.toStringAsFixed(1)} kapott gól után kérnek időt "
          "($n időkérés)${latePct >= 50.0 ? ", és a hajrára "
              "tartogatják" : ""} · ha megindul a hullám, van "
          "két-három támadásnyi ablak";
    }
    return null;
  }

  // Páros-mérleg: melyik kettősük megy együtt a legjobban (4+ közös
  // perc, 0,2 gól/perc felett; a backend-kulccsal azonos küszöbök).
  String? _pairPlusMinus(Map<String, dynamic> r) {
    final list = r["pair_plus_minus"];
    final fps = ((r["pair_fps"] as num?) ?? 25.0).toDouble();
    if (list is! List || fps <= 0) return null;
    Map? best;
    double bestRate = 0.0;
    double bestMin = 0.0;
    for (final e in list) {
      if (e is! Map) continue;
      final minutes = ((e["frames"] as num?) ?? 0).toDouble() / fps / 60.0;
      if (minutes < 4.0) continue;
      final diff = ((e["for"] as num?) ?? 0).toInt() -
          ((e["against"] as num?) ?? 0).toInt();
      final rate = diff / minutes;
      if (best == null || rate > bestRate) {
        best = e;
        bestRate = rate;
        bestMin = minutes;
      }
    }
    if (best == null || bestRate < 0.2) return null;
    final players = (best["players"] as List?) ?? const [];
    return "a(z) ${players.join(" és ")} kettősük megy együtt a "
        "legjobban: ${best["for"]}-${best["against"]} mérleg "
        "${bestMin.toStringAsFixed(0)} közös perc alatt · a párost "
        "szét kell szedni (kettőzés a fáradóbbra, időkérés)";
  }

  // Csere-blokkok: egységekben cserélnek-e (4+ cserehullám, 40%
  // blokkos arány; a backend-kulccsal azonos küszöbök).
  String? _subBlocks(Map<String, dynamic> r) {
    final waves = ((r["sbl_waves"] as num?) ?? 0).toInt();
    final players = ((r["sbl_players"] as num?) ?? 0).toInt();
    final block = ((r["sbl_block_waves"] as num?) ?? 0).toInt();
    if (waves < 4) return null;
    final pct = 100.0 * block / waves;
    final avg = players / waves;
    if (pct >= 40.0) {
      return "egységekben cserélnek: $waves hullámból $block volt 2+ "
          "fős (átlag ${avg.toStringAsFixed(1)} ember) · gyors "
          "újraindítással kell büntetni a csere ütemét";
    }
    return "egyesével cserélnek: $waves hullám, átlag "
        "${avg.toStringAsFixed(1)} ember · nincs külön támadó és "
        "védekező egységük, a célzott fárasztás működik";
  }

  // Lövőerő-esés: marad-e erő a karjukban a 2. félidőre (félidőnként
  // 4+ mért lövés, 6 km/h eltérés; a backend-kulccsal azonos
  // küszöbök).
  String? _shotPowerFade(Map<String, dynamic> r) {
    final fhN = ((r["spf_fh_shots"] as num?) ?? 0).toInt();
    final shN = ((r["spf_sh_shots"] as num?) ?? 0).toInt();
    if (fhN < 4 || shN < 4) return null;
    final fh = ((r["spf_fh_sum_kmh"] as num?) ?? 0).toDouble() / fhN;
    final sh = ((r["spf_sh_sum_kmh"] as num?) ?? 0).toDouble() / shN;
    if (fh - sh >= 6.0) {
      return "a 2. félidőre esik a lövéserejük: "
          "${fh.toStringAsFixed(0)} → ${sh.toStringAsFixed(0)} km/h · "
          "a hajrában kintebb jöhet a fal";
    }
    if (sh - fh >= 6.0) {
      return "a 2. félidőre erősödik a lövésük: "
          "${fh.toStringAsFixed(0)} → ${sh.toStringAsFixed(0)} km/h · "
          "a kapusnak korábban kell indulnia, a fal a szöget zárja";
    }
    return null;
  }

  // Labdatartás-idő: kinél áll meg a labda (5+ labdás szakasz, 0,8 mp
  // a csapatátlag felett; a backend-kulccsal azonos küszöbök).
  // Támadás-kimenetel: eljutnak-e a befejezésig (8+ támadás; 25%
  // feletti eladás-arány, illetve 85% feletti lövés-arány — a
  // backend-kulccsal azonos küszöbök).
  String? _attackOutcomes(Map<String, dynamic> r) {
    final outcomes = r["attack_outcomes"];
    if (outcomes is! Map || outcomes.isEmpty) return null;
    int total = 0;
    outcomes.forEach((_, v) => total += ((v as num?) ?? 0).toInt());
    if (total < 8) return null;
    final shots = ((outcomes["lövés"] as num?) ?? 0).toInt();
    final lost = ((outcomes["eladás"] as num?) ?? 0).toInt();
    final toPct = 100.0 * lost / total;
    final shotPct = 100.0 * shots / total;
    if (toPct >= 25.0) {
      return "lövés nélkül halnak el a támadásaik: a $total "
          "támadásuk ${toPct.toStringAsFixed(0)}%-a eladással zárult "
          "($lost db) · a kettőzés és a magas nyomás azonnal termel";
    }
    if (shotPct >= 85.0) {
      return "mindent befejeznek: a $total támadásuk "
          "${shotPct.toStringAsFixed(0)}%-a lövéssel zárult · a "
          "pressz kockázat, a lövés minőségét kell rontani";
    }
    return null;
  }

  // Kapus-védés posztonként: melyik szögből sebezhető a kapusuk (8+
  // kapura tartó lövés, posztonként 4+, 15 százalékpont elmaradás a
  // csapat-átlagtól — a backend-kulccsal azonos küszöbök).
  String? _gkRoleSaves(Map<String, dynamic> r) {
    final roles = r["gk_role_saves"];
    if (roles is! Map || roles.isEmpty) return null;
    int faced = 0;
    int saves = 0;
    String? weak;
    double weakPct = 0.0;
    int weakFaced = 0;
    roles.forEach((key, value) {
      if (value is! Map) return;
      final f = ((value["faced"] as num?) ?? 0).toInt();
      final sv = ((value["saves"] as num?) ?? 0).toInt();
      faced += f;
      saves += sv;
      if (f < 4) return;
      final pct = 100.0 * sv / f;
      if (weak == null || pct < weakPct) {
        weak = key.toString();
        weakPct = pct;
        weakFaced = f;
      }
    });
    if (faced < 8 || weak == null) return null;
    final avg = 100.0 * saves / faced;
    if (avg - weakPct < 15.0) return null;
    return "a kapusuk a $weak posztról sebezhető: onnan "
        "${weakPct.toStringAsFixed(0)}%-ot fog ($weakFaced lövésből), "
        "a csapat-átlaga ${avg.toStringAsFixed(0)}% · oda kell "
        "szervezni a befejezést";
  }

  // Hiba-sorozatok: egymás után jönnek-e az eladásaik (5+ eladás;
  // 50% felett sorozatos, 20% alatt szórt — a backend-kulccsal azonos
  // küszöbök).
  String? _turnoverClusters(Map<String, dynamic> r) {
    final n = ((r["tc_turnovers"] as num?) ?? 0).toInt();
    final clustered = ((r["tc_clustered"] as num?) ?? 0).toInt();
    final clusters = ((r["tc_clusters"] as num?) ?? 0).toInt();
    if (n < 5) return null;
    final pct = 100.0 * clustered / n;
    if (pct >= 50.0) {
      return "sorozatban hibáznak: az eladásaik "
          "${pct.toStringAsFixed(0)}%-a egy percen belül követi az "
          "előzőt ($clustered/$n, $clusters sorozat) · az első "
          "labdaszerzés után azonnal újra rá kell menni";
    }
    if (pct <= 20.0) {
      return "szórt hibák: az eladásaiknak csak "
          "${pct.toStringAsFixed(0)}%-a jön sorozatban ($n eladás) · "
          "egy hiba után nem borulnak be, a pressz fölösleges "
          "kockázat";
    }
    return null;
  }

  // Kapott gólok posztonként: melyik poszt ellen szivárog a faluk
  // (5+ kapott gól, 45% feletti vezető poszt, holtverseny nélkül — a
  // backend-kulccsal azonos küszöbök).
  String? _concededRoles(Map<String, dynamic> r) {
    final roles = r["conceded_roles"];
    if (roles is! Map || roles.isEmpty) return null;
    final rows = roles.entries
        .map((e) => [e.key.toString(), ((e.value as num?) ?? 0).toInt()])
        .toList()
      ..sort((a, b) => (b[1] as int).compareTo(a[1] as int));
    final total = rows.fold<int>(0, (s, e) => s + (e[1] as int));
    if (total < 5) return null;
    final top = rows.first[1] as int;
    if (rows.length > 1 && (rows[1][1] as int) == top) return null;
    final pct = 100.0 * top / total;
    if (pct < 45.0) return null;
    const what = {
      "szélső": "a szélsőiteket kell etetni",
      "beálló": "a beállós játékot kell futtatni",
      "átlövő": "a távoli befejezésre kell építeni",
      "irányító": "az irányítótok kapja a lövő-helyzeteket",
    };
    final poszt = rows.first[0] as String;
    return "a kapott góljaik ${pct.toStringAsFixed(0)}%-a a $poszt "
        "posztról jön ($top/$total) · ${what[poszt] ?? "erre a posztra "
            "kell szervezni a támadást"}";
  }

  // Poszt szerinti gólmegoszlás: melyik posztra épül a befejezésük
  // (5+ poszthoz kötött gól, 45% feletti vezető poszt, holtverseny
  // nélkül — a backend-kulccsal azonos küszöbök).
  String? _roleGoals(Map<String, dynamic> r) {
    final roles = r["role_goals"];
    if (roles is! Map || roles.isEmpty) return null;
    final rows = roles.entries
        .map((e) => [e.key.toString(), ((e.value as num?) ?? 0).toInt()])
        .toList()
      ..sort((a, b) => (b[1] as int).compareTo(a[1] as int));
    final total = rows.fold<int>(0, (s, e) => s + (e[1] as int));
    if (total < 5) return null;
    final top = rows.first[1] as int;
    if (rows.length > 1 && (rows[1][1] as int) == top) return null;
    final pct = 100.0 * top / total;
    if (pct < 45.0) return null;
    const what = {
      "szélső": "időben kifutni a szélsőre, zárni a szöget",
      "beálló": "a beálló elé állni, a kiszolgáló passzt megelőzni",
      "átlövő": "előrelépés a lövő-vonalba, felemelt kézzel",
      "irányító": "kettőzés az irányítóra a 9 m-en kívül",
    };
    final poszt = rows.first[0] as String;
    return "a góljaik ${pct.toStringAsFixed(0)}%-a a $poszt posztról "
        "jön ($top/$total) · ${what[poszt] ?? "erre a posztra kell "
            "rendezni a védekezést"}";
  }

  // Gólpassz-zónák: melyik vonalról készítik elő a gólokat (4+
  // gólpassz, 50% feletti vezető zóna, holtverseny nélkül — a
  // backend-kulccsal azonos küszöbök).
  String? _assistZones(Map<String, dynamic> r) {
    final zones = r["assist_zones"];
    if (zones is! Map || zones.isEmpty) return null;
    final rows = zones.entries
        .map((e) => [e.key.toString(), ((e.value as num?) ?? 0).toInt()])
        .toList()
      ..sort((a, b) => (b[1] as int).compareTo(a[1] as int));
    final total = rows.fold<int>(0, (s, e) => s + (e[1] as int));
    if (total < 4) return null;
    final top = rows.first[1] as int;
    if (rows.length > 1 && (rows[1][1] as int) == top) return null;
    final pct = 100.0 * top / total;
    if (pct < 50.0) return null;
    const what = {
      "szélről": "a szélső–beálló tengelyt kell elvágni",
      "beállótól": "a beálló kiszolgálását kell elvágni",
      "átlövésből": "az átlövők passz-sávját kell zárni",
    };
    final zone = rows.first[0] as String;
    return "a gólpasszaik ${pct.toStringAsFixed(0)}%-a $zone érkezik "
        "($top/$total) · ${what[zone] ?? "ezt a vonalat kell zárni"}";
  }

  // Támadás-indítók: egy ember hozza-e fel a labdát (6+ mért
  // indítás; 40% felett egyszemélyes, 25% alatt megosztott — a
  // backend-kulccsal azonos küszöbök).
  String? _attackStarters(Map<String, dynamic> r) {
    final list = r["starters"];
    if (list is! List || list.isEmpty) return null;
    int total = 0;
    Map? top;
    for (final e in list) {
      if (e is! Map) continue;
      final n = ((e["starts"] as num?) ?? 0).toInt();
      total += n;
      if (top == null || n > ((top["starts"] as num?) ?? 0).toInt()) {
        top = e;
      }
    }
    if (total < 6 || top == null) return null;
    final pct = 100.0 * ((top["starts"] as num?) ?? 0).toInt() / total;
    if (pct >= 40.0) {
      final who = top["jersey"] != null
          ? "${top["jersey"]}-es"
          : "${top["player_id"]} azonosítójú";
      return "egy ember hozza fel a labdát: a(z) $who játékosuk "
          "indítja a támadások ${pct.toStringAsFixed(0)}%-át "
          "(${top["starts"]}/$total) · letámadás a felhozatalára";
    }
    if (pct <= 25.0) {
      return "megosztott kihozatal: a legtöbbet indító emberük is csak "
          "a támadások ${pct.toStringAsFixed(0)}%-át hozza fel "
          "($total mért indítás) · a letámadás itt nem fizet ki";
    }
    return null;
  }

  String? _holdTime(Map<String, dynamic> r) {
    final list = r["hold_players"];
    final fps = ((r["hold_fps"] as num?) ?? 25.0).toDouble();
    if (list is! List || fps <= 0) return null;
    int holds = 0;
    int frames = 0;
    for (final e in list) {
      if (e is! Map) continue;
      holds += ((e["holds"] as num?) ?? 0).toInt();
      frames += ((e["frames"] as num?) ?? 0).toInt();
    }
    if (holds < 5) return null;
    final avg = frames / holds / fps;
    Map? slow;
    double slowS = 0.0;
    for (final e in list) {
      if (e is! Map) continue;
      final n = ((e["holds"] as num?) ?? 0).toInt();
      if (n < 5) continue;
      final s = ((e["frames"] as num?) ?? 0).toInt() / n / fps;
      if (slow == null || s > slowS) {
        slow = e;
        slowS = s;
      }
    }
    if (slow == null || slowS - avg < 0.8) return null;
    final who = slow["jersey"] != null
        ? "${slow["jersey"]}-es"
        : "${slow["player_id"]} azonosítójú";
    return "a(z) $who játékosuknál áll meg a labda: átlag "
        "${slowS.toStringAsFixed(1)} mp tartás (csapatátlag "
        "${avg.toStringAsFixed(1)} mp) · rá a kettőzés és a letámadás";
  }

  // Védekezés-váltás: egy rendszert játszanak, vagy váltogatnak (6+
  // védekezett támadás, 30% váltás-arány / 80% fő forma; a
  // backend-kulccsal azonos küszöbök).
  String? _formationSwitching(Map<String, dynamic> r) {
    final labels = r["fsw_labels"];
    final attacks = ((r["fsw_attacks"] as num?) ?? 0).toInt();
    final pairs = ((r["fsw_pairs"] as num?) ?? 0).toInt();
    final switches = ((r["fsw_switches"] as num?) ?? 0).toInt();
    if (labels is! Map || labels.isEmpty || attacks < 6 || pairs <= 0) {
      return null;
    }
    String main = "";
    int mainN = -1;
    labels.forEach((k, v) {
      final n = ((v as num?) ?? 0).toInt();
      if (n > mainN) {
        main = "$k";
        mainN = n;
      }
    });
    final swPct = 100.0 * switches / pairs;
    final mainPct = 100.0 * mainN / attacks;
    if (swPct >= 30.0) {
      return "váltogatják a védekezést: a védekezett támadások "
          "${swPct.toStringAsFixed(0)}%-ánál más fal (alapból $main) · "
          "a kihozatalnál mondjátok be a formát, két kész változattal";
    }
    if (mainPct >= 80.0) {
      return "végig egy rendszert játszanak: $main a védekezett "
          "támadások ${mainPct.toStringAsFixed(0)}%-ában · egy "
          "figurasort építsetek rá és húzzátok végig";
    }
    return null;
  }

  // Lövő-erő: ki lő rendre a csapatátlag felett (4+ mért lövés, 8+
  // km/h eltérés; a backend-kulccsal azonos küszöbök).
  String? _shooterPower(Map<String, dynamic> r) {
    final list = r["shooter_power"];
    final teamShots = ((r["spw_team_shots"] as num?) ?? 0).toInt();
    final teamSum = ((r["spw_team_sum_kmh"] as num?) ?? 0).toDouble();
    if (list is! List || teamShots < 6) return null;
    final teamAvg = teamSum / teamShots;
    for (final e in list) {
      if (e is! Map) continue;
      final shots = ((e["shots"] as num?) ?? 0).toInt();
      final sum = ((e["sum_kmh"] as num?) ?? 0).toDouble();
      if (shots < 4) continue;
      final avg = sum / shots;
      if (avg - teamAvg < 8.0) continue;
      final max = ((e["max_kmh"] as num?) ?? 0).toDouble();
      return "a(z) ${e["player_id"]} lövőjük bombáz: "
          "${avg.toStringAsFixed(0)} km/h átlag (csapatátlag "
          "${teamAvg.toStringAsFixed(0)}, csúcs "
          "${max.toStringAsFixed(0)}) · zárd a szöget, ne vakon "
          "blokkolj";
    }
    return null;
  }

  // Lövő-kapuoldal: ki lövi a góljai többségét ugyanabba a sarokba
  // (4+ gól, 60% felett kiszámítható; a backend-kulccsal azonos
  // küszöbök).
  String? _shooterPlacement(Map<String, dynamic> r) {
    final list = r["shooter_placement"];
    if (list is! List) return null;
    for (final e in list) {
      if (e is! Map) continue;
      final goals = ((e["goals"] as num?) ?? 0).toInt();
      if (goals < 4) continue;
      var dom = "bal";
      var best = ((e["bal"] as num?) ?? 0).toInt();
      for (final k in ["közép", "jobb"]) {
        final v = ((e[k] as num?) ?? 0).toInt();
        if (v > best) {
          best = v;
          dom = k;
        }
      }
      final share = 100.0 * best / goals;
      if (share < 60.0) continue;
      return "a(z) ${e["player_id"]} lövőjük kiszámítható: "
          "${share.toStringAsFixed(0)}% a $dom oldalra ($goals gólból) "
          "· a kapus álljon rá, a fal a másik oldalt zárja";
    }
    return null;
  }

  // Szélső-védekezés: a szélső vs középső sávból kapott lövések
  // gólaránya (sávonként 5+ lövésnél, 15+ százalékpont eltérésnél; a
  // backend-kulccsal azonos küszöbök).
  String? _wingDefense(Map<String, dynamic> r) {
    final ws = ((r["wdf_wing_shots"] as num?) ?? 0).toInt();
    final wg = ((r["wdf_wing_goals"] as num?) ?? 0).toInt();
    final cs = ((r["wdf_center_shots"] as num?) ?? 0).toInt();
    final cg = ((r["wdf_center_goals"] as num?) ?? 0).toInt();
    if (ws < 5 || cs < 5) return null;
    final wing = 100.0 * wg / ws;
    final center = 100.0 * cg / cs;
    if (wing - center >= 15.0) {
      return "a szélen nyitottak: ${wing.toStringAsFixed(0)}% "
          "gólarány a szélről (középről "
          "${center.toStringAsFixed(0)}%) · vond be a szélsőket";
    }
    if (center - wing >= 15.0) {
      return "a szélső lövéseket zárják "
          "(${wing.toStringAsFixed(0)}% vs "
          "${center.toStringAsFixed(0)}%) · középen és beállóval kell "
          "játszani";
    }
    return null;
  }

  // Drága eladók: kinek az eladásaiból lett fél percen belüli kapott
  // gól (3+ eladás és 2+ gól kell; a backend-kulccsal azonos
  // küszöbök).
  String? _costlyTurnovers(Map<String, dynamic> r) {
    final list = r["costly_turnover_players"];
    if (list is! List) return null;
    for (final e in list) {
      if (e is! Map) continue;
      final to = ((e["turnovers"] as num?) ?? 0).toInt();
      final pu = ((e["punished"] as num?) ?? 0).toInt();
      if (to < 3 || pu < 2) continue;
      return "a(z) ${e["player_id"]} játékosuk eladásai kerülnek "
          "gólba ($pu kapott gól $to eladásból) · kettőzd a "
          "felhozatalnál";
    }
    return null;
  }

  // Emberelőny-védekezés: az emberelőnyben kapott gól/perc ütem az
  // egyenlő létszámúhoz képest (90+ mp előnyben, 0.2 gól/perc
  // eltérésnél; a backend-kulccsal azonos küszöbök).
  String? _powerplayDefense(Map<String, dynamic> r) {
    final ppS = ((r["ppd_seconds"] as num?) ?? 0).toDouble();
    final ppC = ((r["ppd_conceded"] as num?) ?? 0).toInt();
    final eqS = ((r["ppd_eq_seconds"] as num?) ?? 0).toDouble();
    final eqC = ((r["ppd_eq_conceded"] as num?) ?? 0).toInt();
    if (ppS < 90.0 || eqS <= 0) return null;
    final pp = 60.0 * ppC / ppS;
    final eq = 60.0 * eqC / eqS;
    if (pp - eq >= 0.2) {
      return "emberelőnyben is szivárognak: ${pp.toStringAsFixed(2)} "
          "kapott gól/perc (egyenlő létszámnál "
          "${eq.toStringAsFixed(2)}) · hátrányban is vállald a kontrát";
    }
    if (eq - pp >= 0.2) {
      return "emberelőnyben fegyelmezettek "
          "(${pp.toStringAsFixed(2)} kapott gól/perc) · "
          "hátrányban a labdatartás a reális cél";
    }
    return null;
  }

  // Kapus szabad lövés ellen: a szabad vs fedezett lövések elleni
  // védés-arány (sávonként 5+ lövésnél, 15+ százalékpont eltérésnél;
  // a backend-kulccsal azonos küszöbök).
  String? _gkFreeShotSaves(Map<String, dynamic> r) {
    final fs = ((r["gkf_free_shots"] as num?) ?? 0).toInt();
    final fv = ((r["gkf_free_saves"] as num?) ?? 0).toInt();
    final cs = ((r["gkf_cov_shots"] as num?) ?? 0).toInt();
    final cv = ((r["gkf_cov_saves"] as num?) ?? 0).toInt();
    if (fs < 5 || cs < 5) return null;
    final free = 100.0 * fv / fs;
    final cover = 100.0 * cv / cs;
    if (cover - free >= 15.0) {
      return "falfüggő kapus: fedezve ${cover.toStringAsFixed(0)}%, "
          "szabad lövésnél ${free.toStringAsFixed(0)}% védés · "
          "elzárás után tiszta átlövés";
    }
    if (free - cover >= 15.0) {
      return "a szabad lövéseket is fogja "
          "(${free.toStringAsFixed(0)}% vs "
          "${cover.toStringAsFixed(0)}%) · kidolgozott, közeli "
          "helyzetig kell játszani";
    }
    return null;
  }

  // Kettőzés: a labdás-kockák hány százalékában lép rá második védő
  // (250+ labdás-kockánál, 30% felett kettőző, 10% alatt 1v1-et
  // hagyó; a backend-kulccsal azonos küszöbök).
  String? _doubleTeams(Map<String, dynamic> r) {
    final hf = ((r["dbl_holder_frames"] as num?) ?? 0).toInt();
    final df = ((r["dbl_doubled_frames"] as num?) ?? 0).toInt();
    final ft = ((r["dbl_forced_to"] as num?) ?? 0).toInt();
    if (hf < 250) return null;
    final pct = 100.0 * df / hf;
    if (pct >= 30.0) {
      return "kettőznek a labdáson (${pct.toStringAsFixed(0)}%, "
          "$ft kikényszerített eladás) · egy érintéssel az üres "
          "oldalra";
    }
    if (pct <= 10.0) {
      return "nem kettőznek (${pct.toStringAsFixed(0)}%) · "
          "1v1-et hagynak: a legjobb áttörőt kell rájuk küldeni";
    }
    return null;
  }

  // Kapus-indítás iránya: a bal/jobb oldalra adott indítások aránya
  // (6+ indításnál, 65% felett egyoldalú; a backend-kulccsal azonos
  // küszöbök).
  String? _gkOutletSide(Map<String, dynamic> r) {
    final l = ((r["gos_left"] as num?) ?? 0).toInt();
    final rt = ((r["gos_right"] as num?) ?? 0).toInt();
    final all = l + rt;
    if (all < 6) return null;
    final share = l / all;
    if (share < 0.65 && 1.0 - share < 0.65) return null;
    final side = share >= 0.65 ? "bal" : "jobb";
    final pct = 100.0 * (share >= 0.65 ? share : 1.0 - share);
    return "a kapusuk a $side oldalra indít "
        "(${pct.toStringAsFixed(0)}%, $all indításból) · "
        "arra az oldalra indulj előre, támadd le a fogadó szélsőt";
  }

  // Hajrá-eladás: a hajrá előtti vs a hajrá eladás/perc üteme (5+
  // korai eladásnál, 0.3 eladás/perc eltérésnél; a backend-kulccsal
  // azonos küszöbök).
  String? _clutchTurnovers(Map<String, dynamic> r) {
    final eTo = ((r["cto_early_to"] as num?) ?? 0).toInt();
    final eS = ((r["cto_early_s"] as num?) ?? 0).toDouble();
    final cTo = ((r["cto_clutch_to"] as num?) ?? 0).toInt();
    final cS = ((r["cto_clutch_s"] as num?) ?? 0).toDouble();
    if (eTo < 5 || eS <= 0 || cS <= 0) return null;
    final e = 60.0 * eTo / eS;
    final c = 60.0 * cTo / cS;
    if (c - e >= 0.3) {
      return "a hajrában szétesnek: ${e.toStringAsFixed(2)} → "
          "${c.toStringAsFixed(2)} eladás/perc · "
          "a végén présbe kell tenni a labdavivőt";
    }
    if (e - c >= 0.3) {
      return "a hajrában hidegvérűek: ${e.toStringAsFixed(2)} → "
          "${c.toStringAsFixed(2)} eladás/perc · "
          "a hibájukra várni hiba";
    }
    return null;
  }

  // Hátrány-támadás: a kiállítás alatti gól/perc ütem az egyenlő
  // létszámúhoz képest (90+ mp hátrányban, 0.15 gól/perc esésnél; a
  // backend-kulccsal azonos küszöbök).
  String? _shorthandedAttack(Map<String, dynamic> r) {
    final shS = ((r["sha_seconds"] as num?) ?? 0).toDouble();
    final shG = ((r["sha_goals"] as num?) ?? 0).toInt();
    final eqS = ((r["sha_eq_seconds"] as num?) ?? 0).toDouble();
    final eqG = ((r["sha_eq_goals"] as num?) ?? 0).toInt();
    if (shS < 90.0 || eqS <= 0) return null;
    final sh = 60.0 * shG / shS;
    final eq = 60.0 * eqG / eqS;
    if (eq - sh >= 0.15) {
      return "hátrányban megbénulnak: ${sh.toStringAsFixed(2)} gól/perc "
          "(egyenlő létszámnál ${eq.toStringAsFixed(2)}) · "
          "a kiállítás gólkülönbség";
    }
    return "hátrányban is támadnak: ${sh.toStringAsFixed(2)} gól/perc · "
        "az emberelőnyt labdatartással kell végigjátszani";
  }

  // Fölény-befejezés: a létszámfölényből vs a felállt fal ellen
  // leadott lövések gólaránya (sávonként 5+ lövésnél, 15+
  // százalékpont eltérésnél; a backend-kulccsal azonos küszöbök).
  String? _overloadFinishing(Map<String, dynamic> r) {
    final os = ((r["ovl_shots"] as num?) ?? 0).toInt();
    final og = ((r["ovl_goals"] as num?) ?? 0).toInt();
    final ss = ((r["ovl_set_shots"] as num?) ?? 0).toInt();
    final sg = ((r["ovl_set_goals"] as num?) ?? 0).toInt();
    if (os < 5 || ss < 5) return null;
    final ovl = 100.0 * og / os;
    final set = 100.0 * sg / ss;
    if (ovl - set >= 15.0) {
      return "fölény-függők: ${ovl.toStringAsFixed(0)}% fölényben, "
          "${set.toStringAsFixed(0)}% felállt fal ellen · "
          "kényszerítsd őket felállt támadásba";
    }
    if (set - ovl >= 15.0) {
      return "a falat is törik: ${set.toStringAsFixed(0)}% felállt fal "
          "ellen (fölényben ${ovl.toStringAsFixed(0)}%) · "
          "a hazaérés önmagában kevés";
    }
    return null;
  }

  // Ellen-press: az eladások hány százaléka után szerzik vissza a
  // labdát 6 mp-en belül (8+ eladásnál, 35% felett / 15% alatt; a
  // backend-kulccsal azonos küszöbök).
  String? _counterPress(Map<String, dynamic> r) {
    final to = ((r["cpr_turnovers"] as num?) ?? 0).toInt();
    final rg = ((r["cpr_regained"] as num?) ?? 0).toInt();
    if (to < 8) return null;
    final pct = 100.0 * rg / to;
    if (pct >= 35.0) {
      return "azonnal visszatámadnak: az eladásaik "
          "${pct.toStringAsFixed(0)}%-át visszaszerzik · "
          "a szerzés utáni első passz legyen tiszta";
    }
    if (pct <= 15.0) {
      return "beletörődnek az eladásba (csak "
          "${pct.toStringAsFixed(0)}% visszaszerzés) · "
          "minden szerzés ingyen lerohanás";
    }
    return null;
  }

  // Hajrá-lövésválasztás: a hajrá előtti vs a hajrá-lövések átlagos
  // helyzetértéke (fázisonként 5+ lövésnél, 0.05 xG eltérésnél; a
  // backend-kulccsal azonos küszöbök).
  String? _clutchShotQuality(Map<String, dynamic> r) {
    final es = ((r["csq_early_shots"] as num?) ?? 0).toInt();
    final exg = ((r["csq_early_xg"] as num?) ?? 0).toDouble();
    final cs = ((r["csq_clutch_shots"] as num?) ?? 0).toInt();
    final cxg = ((r["csq_clutch_xg"] as num?) ?? 0).toDouble();
    if (es < 5 || cs < 5) return null;
    final ea = exg / es;
    final ca = cxg / cs;
    if (ea - ca >= 0.05) {
      return "a hajrában elkapkodják: helyzetérték "
          "${ea.toStringAsFixed(2)} → ${ca.toStringAsFixed(2)} · "
          "a végén elég tartani a falat";
    }
    if (ca - ea >= 0.05) {
      return "a hajrában kidolgozzák: helyzetérték "
          "${ea.toStringAsFixed(2)} → ${ca.toStringAsFixed(2)} · "
          "a végén se lazuljon a fal";
    }
    return null;
  }

  // Passz-kockázat: a hosszú (10 m+) vs rövid passzok eladás-aránya
  // (sávonként 8+ kísérletnél, 15+ százalékpont eltérésnél; a
  // backend-kulccsal azonos küszöbök).
  String? _passRisk(Map<String, dynamic> r) {
    final lt = ((r["prk_long_tries"] as num?) ?? 0).toInt();
    final lto = ((r["prk_long_to"] as num?) ?? 0).toInt();
    final st = ((r["prk_short_tries"] as num?) ?? 0).toInt();
    final sto = ((r["prk_short_to"] as num?) ?? 0).toInt();
    if (lt < 8 || st < 8) return null;
    final lon = 100.0 * lto / lt;
    final sho = 100.0 * sto / st;
    if (lon - sho >= 15.0) {
      return "kockázatos hosszú passzok: "
          "${lon.toStringAsFixed(0)}% elveszik (rövidnél "
          "${sho.toStringAsFixed(0)}%) · állj a hosszú sávokba";
    }
    if (sho - lon >= 15.0) {
      return "a hosszú passzt is biztosan kezelik "
          "(${lon.toStringAsFixed(0)}% vs "
          "${sho.toStringAsFixed(0)}%) · a sáv-vadászat nem fizet";
    }
    return null;
  }

  // Elzárás-védekezés: az ellenük vezetett elzárásos vs elzárás
  // nélküli lövések gólaránya (6+ elzárásos lövésnél, 15+
  // százalékpont eltérésnél; a backend-kulccsal azonos küszöbök).
  String? _screenDefense(Map<String, dynamic> r) {
    final scrS = ((r["scd_screened_shots"] as num?) ?? 0).toInt();
    final scrG = ((r["scd_screened_goals"] as num?) ?? 0).toInt();
    final opnS = ((r["scd_open_shots"] as num?) ?? 0).toInt();
    final opnG = ((r["scd_open_goals"] as num?) ?? 0).toInt();
    if (scrS < 6 || opnS < 1) return null;
    final scr = 100.0 * scrG / scrS;
    final opn = 100.0 * opnG / opnS;
    if (scr - opn >= 15.0) {
      return "rosszul váltanak elzárás ellen: "
          "${scr.toStringAsFixed(0)}% gól elzárásból, "
          "${opn.toStringAsFixed(0)}% nélküle · zárj minden figurát";
    }
    if (opn - scr >= 15.0) {
      return "jól váltanak az elzárásokon "
          "(${scr.toStringAsFixed(0)}% vs "
          "${opn.toStringAsFixed(0)}%) · keress tiszta 1v1-et";
    }
    return null;
  }

  // Elzárás-használat: az elzárásból leadott lövések aránya az
  // őrzött lövésekben (8+ őrzött lövésnél; 40%+ = elzárásos, 10%- =
  // elzárás nélküli; a backend-kulccsal azonos küszöbök).
  String? _screenUsage(Map<String, dynamic> r) {
    final shots = ((r["scu_shots"] as num?) ?? 0).toInt();
    final screened = ((r["scu_screened"] as num?) ?? 0).toInt();
    if (shots < 8) return null;
    final pct = 100.0 * screened / shots;
    if (pct >= 40.0) {
      return "elzárásokból lőnek (${pct.toStringAsFixed(0)}% "
          "$screened/$shots) · hangos váltás, átcsúszás a zár alatt";
    }
    if (pct <= 10.0) {
      return "elzárás nélkül lőnek (csak "
          "${pct.toStringAsFixed(0)}%) · a lövőjük magára marad: "
          "kilépés + sánc";
    }
    return null;
  }

  // Oldalváltás: a keresztpasszok (10 m+ oldalirány) aránya a támadó
  // passzokban (30+ passznál; 12%+ = oldalváltó, 3%- = egy-oldalas;
  // a backend-kulccsal azonos küszöbök).
  String? _sideSwitching(Map<String, dynamic> r) {
    final passes = ((r["ssw_passes"] as num?) ?? 0).toInt();
    final switches = ((r["ssw_switches"] as num?) ?? 0).toInt();
    if (passes < 30) return null;
    final pct = 100.0 * switches / passes;
    if (pct >= 12.0) {
      return "oldalváltásokkal húzzák szét a falat "
          "(${pct.toStringAsFixed(0)}% keresztpassz) · kompakt "
          "eltolás, zárt sávok";
    }
    if (pct <= 3.0) {
      return "egy oldalon ragadnak (csak ${pct.toStringAsFixed(0)}% "
          "oldalváltás) · told el a falat a kedvenc oldalukra";
    }
    return null;
  }

  // Lerohanás-védés: a kapus védés-aránya gyorsindítás vs rendezett
  // támadás ellen (fázisonként 4+ kaput eltaláló lövésnél, 15+
  // százalékpont eltérésnél; a backend-kulccsal azonos küszöbök).
  String? _gkBreakResponse(Map<String, dynamic> r) {
    final ff = ((r["gkb_fast_faced"] as num?) ?? 0).toInt();
    final fs = ((r["gkb_fast_saves"] as num?) ?? 0).toInt();
    final sf = ((r["gkb_set_faced"] as num?) ?? 0).toInt();
    final ss = ((r["gkb_set_saves"] as num?) ?? 0).toInt();
    if (ff < 4 || sf < 4) return null;
    final fast = 100.0 * fs / ff;
    final set = 100.0 * ss / sf;
    if (set - fast >= 15.0) {
      return "a kapusuk lerohanásra érzékeny: gyorsindítás ellen "
          "${fast.toStringAsFixed(0)}%, rendezett ellen "
          "${set.toStringAsFixed(0)}% védés · fuss minden szerzésből";
    }
    if (fast - set >= 15.0) {
      return "lerohanás-fogó kapus (${fast.toStringAsFixed(0)}% vs "
          "${set.toStringAsFixed(0)}%) · a gyors befejezést is "
          "játszd ki";
    }
    return null;
  }

  // Gól-előkészítés hossza: a direkt (0-2 passzos) és kombinatív
  // (5+ passzos) gólok aránya (4+ gólnál, 50%+ résznél; a
  // backend-kulccsal azonos küszöbök).
  String? _goalBuildup(Map<String, dynamic> r) {
    final goals = ((r["gb_goals"] as num?) ?? 0).toInt();
    final short = ((r["gb_short"] as num?) ?? 0).toInt();
    final long = ((r["gb_long"] as num?) ?? 0).toInt();
    if (goals < 4) return null;
    final shortPct = 100.0 * short / goals;
    final longPct = 100.0 * long / goals;
    if (shortPct >= 50.0) {
      return "direkt gólok: ${shortPct.toStringAsFixed(0)}% "
          "legfeljebb 2 passzból ($short/$goals) · fogd meg az első "
          "hullámot";
    }
    if (longPct >= 50.0) {
      return "kombinatív gólok: ${longPct.toStringAsFixed(0)}% 5+ "
          "passzos akcióból ($long/$goals) · türelmes fal, ne lépj "
          "ki korán";
    }
    return null;
  }

  // Előkészítő-függés: a gólpasszok fő előkészítőre jutó hányada
  // (6+ gólpasszos gólnál, 50%+ résznél; a backend-kulccsal azonos
  // küszöbök).
  String? _assistConcentration(Map<String, dynamic> r) {
    final assists = ((r["ac_assists"] as num?) ?? 0).toInt();
    final top = ((r["ac_top_assists"] as num?) ?? 0).toInt();
    if (assists < 6) return null;
    final share = 100.0 * top / assists;
    if (share >= 50.0) {
      return "egy emberen múlik az előkészítés: a gólpasszok "
          "${share.toStringAsFixed(0)}%-a ($top/$assists) egy "
          "játékostól · vágd el: előfogás + kettőzés";
    }
    return null;
  }

  // Középkezdés-tempó: a gyors (12 mp-en belüli térfél-átlépésű)
  // újraindítások aránya kapott gól után (4+ újraindításnál; 50%+ =
  // lerohanós, 20%- = lassú; a backend-kulccsal azonos küszöbök).
  String? _restartSpeed(Map<String, dynamic> r) {
    final restarts = ((r["rs_restarts"] as num?) ?? 0).toInt();
    final fast = ((r["rs_fast"] as num?) ?? 0).toInt();
    final sumS = ((r["rs_sum_s"] as num?) ?? 0).toDouble();
    if (restarts < 4) return null;
    final pct = 100.0 * fast / restarts;
    if (pct >= 50.0) {
      return "kapott gól után is lerohannak "
          "(${pct.toStringAsFixed(0)}% gyors újraindítás) · gól után "
          "tilos az ünneplés";
    }
    if (pct <= 20.0) {
      return "lassú középkezdés: átlag "
          "${(sumS / restarts).toStringAsFixed(0)} mp az átjutásig · "
          "támadd le a középkezdést";
    }
    return null;
  }

  // Elsütés-idő: a gyors (0,6 mp-en belüli) elsütések aránya (8+
  // mérhető lövésnél; 60%+ = kapásból, 25%- = labdafogó; a
  // backend-kulccsal azonos küszöbök).
  String? _shotRelease(Map<String, dynamic> r) {
    final shots = ((r["sr_shots"] as num?) ?? 0).toInt();
    final quick = ((r["sr_quick"] as num?) ?? 0).toInt();
    if (shots < 8) return null;
    final pct = 100.0 * quick / shots;
    if (pct >= 60.0) {
      return "kapásból lőnek: ${pct.toStringAsFixed(0)}% gyors "
          "elsütés ($quick/$shots) · a kapus a passzra mozduljon";
    }
    if (pct <= 25.0) {
      return "labdafogó lövők: csak ${pct.toStringAsFixed(0)}% gyors "
          "elsütés · kilépés + blokk, van időd";
    }
    return null;
  }

  // Beálló-védekezés: az ellenük vezetett beállós vs beálló nélküli
  // támadások gólaránya (6+ beállós támadásnál, 15+ százalékpont
  // eltérésnél; a backend-kulccsal azonos küszöbök).
  String? _pivotDefense(Map<String, dynamic> r) {
    final pivA = ((r["pd_pivot_attacks"] as num?) ?? 0).toInt();
    final pivG = ((r["pd_pivot_goals"] as num?) ?? 0).toInt();
    final othA = ((r["pd_other_attacks"] as num?) ?? 0).toInt();
    final othG = ((r["pd_other_goals"] as num?) ?? 0).toInt();
    if (pivA < 6 || othA < 1) return null;
    final piv = 100.0 * pivG / pivA;
    final oth = 100.0 * othG / othA;
    if (piv - oth >= 15.0) {
      return "gyenge beálló-őrzés: beállóval ${piv.toStringAsFixed(0)}"
          "% gól ellenük, nélküle ${oth.toStringAsFixed(0)}% · etesd "
          "a beállót";
    }
    if (oth - piv >= 15.0) {
      return "bírják a beállót (${piv.toStringAsFixed(0)}% vs "
          "${oth.toStringAsFixed(0)}%) · játszd körbe, ne erőltesd";
    }
    return null;
  }

  // Indítás-biztonság: az ellenfélnél kikötő kapus-indítások aránya
  // (6+ indításnál, 25%+ aránynál; a backend-kulccsal azonos
  // küszöbök).
  String? _gkOutletSecurity(Map<String, dynamic> r) {
    final outlets = ((r["gos_outlets"] as num?) ?? 0).toInt();
    final lost = ((r["gos_lost"] as num?) ?? 0).toInt();
    if (outlets < 6) return null;
    final pct = 100.0 * lost / outlets;
    if (pct < 25.0) return null;
    return "elcsíphető indítás: $lost/$outlets kapus-indításuk az "
        "ellenfélé (${pct.toStringAsFixed(0)}%) · támadd le a "
        "kihozatalt";
  }

  // Támadó-mozgás: átlagsebesség szervezett támadásban (120+ mért
  // játékos-másodpercnél; 0,9 m/s alatt álló, 1,6 felett mozgásos;
  // a backend-kulccsal azonos küszöbök).
  String? _attackMotion(Map<String, dynamic> r) {
    final dist = ((r["am_dist_m"] as num?) ?? 0).toDouble();
    final time = ((r["am_time_s"] as num?) ?? 0).toDouble();
    if (time < 120.0) return null;
    final avg = dist / time;
    if (avg <= 0.9) {
      return "álló támadás: átlag ${avg.toStringAsFixed(1)} m/s · "
          "lépj ki bátran, segítség nem jön";
    }
    if (avg >= 1.6) {
      return "mozgásos támadás (${avg.toStringAsFixed(1)} m/s): "
          "keresztek, elfutások · átadás-átvétel, ne kövess embert";
    }
    return null;
  }

  // Fal-rés: a réses (3,5 m+ szomszéd-táv) falkockák aránya (100+
  // mért falkockánál, 40%+ aránynál; a backend-kulccsal azonos
  // küszöbök).
  String? _wallGaps(Map<String, dynamic> r) {
    final frames = ((r["wg_frames"] as num?) ?? 0).toInt();
    final wide = ((r["wg_wide"] as num?) ?? 0).toInt();
    if (frames < 100) return null;
    final pct = 100.0 * wide / frames;
    if (pct < 40.0) return null;
    return "réses fal: a rendezett védekezésük "
        "${pct.toStringAsFixed(0)}%-ában 3,5 m+ rés · betörés + "
        "beúszó beálló";
  }

  // Gólcsend-anatómia: a leghosszabb gólcsendek lövés-üteme (5+ perc
  // össz-csendnél; 0,3/perc alatt néma, 0,8/perc felett kihagyós; a
  // backend-kulccsal azonos küszöbök).
  String? _droughtAnatomy(Map<String, dynamic> r) {
    final droughtS = ((r["da_drought_s"] as num?) ?? 0).toDouble();
    final shots = ((r["da_shots"] as num?) ?? 0).toInt();
    if (droughtS < 300.0) return null;
    final perMin = shots / (droughtS / 60.0);
    final mins = (droughtS / 60.0).toStringAsFixed(0);
    if (perMin <= 0.3) {
      return "néma gólcsend: $mins perc csendben csak $shots lövés · "
          "ha megfogtad, tartsd a presszt";
    }
    if (perMin >= 0.8) {
      return "kihagyós gólcsend: a csendben is "
          "${perMin.toStringAsFixed(1)} lövés/perc · a kapusod tartja";
    }
    return null;
  }

  // Engedett-oldal: a kapott szélső-sávos lövések oldal-többsége (8+
  // szélső-sávos lövésnél, 65%+ többségnél; a backend-kulccsal
  // azonos küszöbök). A "bal" a fal bal oldala.
  String? _concededSide(Map<String, dynamic> r) {
    final left = ((r["csb_left"] as num?) ?? 0).toInt();
    final right = ((r["csb_right"] as num?) ?? 0).toInt();
    final wings = left + right;
    if (wings < 8) return null;
    final top = left >= right ? left : right;
    final pct = 100.0 * top / wings;
    if (pct < 65.0) return null;
    final side = left >= right ? "bal" : "jobb";
    return "a faluk $side oldala átjárható: a kapott szélső-lövések "
        "${pct.toStringAsFixed(0)}%-a arról jön ($top/$wings) · oda "
        "szervezz";
  }

  // Eladás-büntetés: az eladások fél percen belül góllal büntetett
  // hányada (6+ eladásnál, 35%+ aránynál; a backend-kulccsal azonos
  // küszöbök).
  String? _turnoverPunishment(Map<String, dynamic> r) {
    final turnovers = ((r["tpu_turnovers"] as num?) ?? 0).toInt();
    final punished = ((r["tpu_punished"] as num?) ?? 0).toInt();
    if (turnovers < 6) return null;
    final pct = 100.0 * punished / turnovers;
    if (pct < 35.0) return null;
    return "az eladásaik ${pct.toStringAsFixed(0)}%-a fél percen "
        "belül gól ($punished/$turnovers) · szerzés után azonnal";
  }

  // Kapus-indítás hossza: a 15 m feletti kapus-passzok aránya (6+
  // passznál; 50%+ = hosszú indítós, 15%- = rövid kihozós; a
  // backend-kulccsal azonos küszöbök).
  String? _gkOutlet(Map<String, dynamic> r) {
    final outlets = ((r["gko_outlets"] as num?) ?? 0).toInt();
    final long = ((r["gko_long"] as num?) ?? 0).toInt();
    if (outlets < 6) return null;
    final share = long / outlets;
    if (share >= 0.5) {
      return "hosszú indítós kapus: "
          "${(100.0 * share).toStringAsFixed(0)}% 15 m+ "
          "($long/$outlets) · zárd az indítás-sávokat";
    }
    if (share <= 0.15) {
      return "rövid kihozós kapus: csak $long/$outlets hosszú · "
          "magas letámadás";
    }
    return null;
  }

  // Területi-fölény-esés: a tilt 1. vs 2. félidőben (félidőnként
  // 100+ birtokos kockánál, 12+ százalékpont esésnél; a
  // backend-kulccsal azonos küszöbök).
  String? _tiltFade(Map<String, dynamic> r) {
    final fhFrames = ((r["tf_fh_frames"] as num?) ?? 0).toInt();
    final fhOpp = ((r["tf_fh_opp"] as num?) ?? 0).toInt();
    final shFrames = ((r["tf_sh_frames"] as num?) ?? 0).toInt();
    final shOpp = ((r["tf_sh_opp"] as num?) ?? 0).toInt();
    if (fhFrames < 100 || shFrames < 100) return null;
    final fhPct = 100.0 * fhOpp / fhFrames;
    final shPct = 100.0 * shOpp / shFrames;
    if (fhPct - shPct < 12.0) return null;
    return "a 2. félidőre hátracsúsznak "
        "(${fhPct.toStringAsFixed(0)}% → ${shPct.toStringAsFixed(0)}% "
        "elöl) · türelem, a hajrában told fel";
  }

  // Asszist-függés: a gólok gólpasszos aránya (6+ gólnál; 70%+ =
  // kollektív, 35%- = egyéni; a backend-kulccsal azonos küszöbök).
  String? _assistReliance(Map<String, dynamic> r) {
    final goals = ((r["ad_goals"] as num?) ?? 0).toInt();
    final assisted = ((r["ad_assisted"] as num?) ?? 0).toInt();
    if (goals < 6) return null;
    final pct = 100.0 * assisted / goals;
    if (pct >= 70.0) {
      return "kiadásból élnek: a gólok ${pct.toStringAsFixed(0)}%-a "
          "gólpasszos ($assisted/$goals) · vágd a passzsávot";
    }
    if (pct <= 35.0) {
      return "egyéni megoldások: csak ${pct.toStringAsFixed(0)}% "
          "gólpasszos ($assisted/$goals) · kulcsember-párharc";
    }
    return null;
  }

  // Lepattanó-fal: az ellenfél kimaradt lövései után visszaengedett
  // második rohamok aránya (6+ lehetőségnél, 35%+ aránynál; a
  // backend-kulccsal azonos küszöbök).
  String? _secondChanceAllowed(Map<String, dynamic> r) {
    final misses = ((r["sca_opp_misses"] as num?) ?? 0).toInt();
    final allowed = ((r["sca_allowed"] as num?) ?? 0).toInt();
    if (misses < 6) return null;
    final pct = 100.0 * allowed / misses;
    if (pct < 35.0) return null;
    return "a kimaradt lövések ${pct.toStringAsFixed(0)}%-ánál "
        "második hullámot engednek ($allowed/$misses) · lepattanóra rá";
  }

  // Pressz-tűrés: eladás-arány testközeli védőnél vs szabadon (10+
  // esemény mindkét mintában, 15+ százalékpont ugrás; a
  // backend-kulccsal azonos küszöbök).
  String? _passSecurity(Map<String, dynamic> r) {
    final pressPasses = ((r["ps_press_passes"] as num?) ?? 0).toInt();
    final pressTo = ((r["ps_press_to"] as num?) ?? 0).toInt();
    final freePasses = ((r["ps_free_passes"] as num?) ?? 0).toInt();
    final freeTo = ((r["ps_free_to"] as num?) ?? 0).toInt();
    final pressN = pressPasses + pressTo;
    final freeN = freePasses + freeTo;
    if (pressN < 10 || freeN < 10) return null;
    final pressPct = 100.0 * pressTo / pressN;
    final freePct = 100.0 * freeTo / freeN;
    if (pressPct - freePct < 15.0) return null;
    return "eladás testközeli védőnél ${pressPct.toStringAsFixed(0)}% "
        "(szabadon ${freePct.toStringAsFixed(0)}%) · agresszív fal";
  }

  // Eladás-időzítés: az eladások mekkora része korai, a birtoklás
  // első 10 mp-ében (6+ eladásnál, 50%+ aránynál; a backend-kulccsal
  // azonos küszöbök).
  String? _turnoverTiming(Map<String, dynamic> r) {
    final timed = ((r["tt_timed"] as num?) ?? 0).toInt();
    final early = ((r["tt_early"] as num?) ?? 0).toInt();
    if (timed < 6) return null;
    final share = early / timed;
    if (share < 0.5) return null;
    return "az eladásaik ${(100.0 * share).toStringAsFixed(0)}%-a a "
        "birtoklás első 10 mp-ében ($early/$timed) · magas letámadás";
  }

  // Kapus-gyengeoldal: hova kapják a gólokat a kapus szemszögéből (6+
  // gólnál, 45%+ részaránynál; a backend-kulccsal azonos küszöbök).
  String? _gkWeakSide(Map<String, dynamic> r) {
    final bal = ((r["gw_bal"] as num?) ?? 0).toInt();
    final kozep = ((r["gw_kozep"] as num?) ?? 0).toInt();
    final jobb = ((r["gw_jobb"] as num?) ?? 0).toInt();
    final goals = bal + kozep + jobb;
    if (goals < 6) return null;
    final tally = {"bal": bal, "közép": kozep, "jobb": jobb};
    final weak =
        tally.entries.reduce((a, b) => a.value >= b.value ? a : b);
    if (weak.value / goals < 0.45) return null;
    return "a bekapott gólok "
        "${(100.0 * weak.value / goals).toStringAsFixed(0)}%-a a "
        "${weak.key} oldalukra (${weak.value}/$goals) · oda célozz";
  }

  // Kapuscsere-hatás: a cserék előtti vs utáni védés% (2+ cserénél és
  // 4+ lövésnél mindkét oldalon; a backend-kulccsal azonos küszöbök).
  String? _gkChangeEffect(Map<String, dynamic> r) {
    final ch = ((r["gkc_changes"] as num?) ?? 0).toInt();
    final preF = ((r["gkc_pre_faced"] as num?) ?? 0).toInt();
    final postF = ((r["gkc_post_faced"] as num?) ?? 0).toInt();
    if (ch < 2 || preF < 4 || postF < 4) return null;
    final pre = 100.0 * ((r["gkc_pre_saves"] as num?) ?? 0).toInt() / preF;
    final post =
        100.0 * ((r["gkc_post_saves"] as num?) ?? 0).toInt() / postF;
    if (post - pre >= 15.0) {
      return "${pre.round()}% → ${post.round()}% védés a cserék után · "
          "a csere bejön";
    }
    if (pre - post >= 15.0) {
      return "${pre.round()}% → ${post.round()}% védés a cserék után · "
          "nincs mentőöv";
    }
    return null;
  }

  // Hetes-védés: a kapusuk mérlege a kapura tartó hetesekből (3+
  // hetesnél; a backend-kulccsal azonos küszöbök).
  String? _sevenDefense(Map<String, dynamic> r) {
    final faced = ((r["s7d_faced"] as num?) ?? 0).toInt();
    if (faced < 3) return null;
    final saved = ((r["s7d_saved"] as num?) ?? 0).toInt();
    if (100.0 * saved / faced >= 40.0) {
      return "$faced kapura tartó hetesből $saved fogás · hetest fog";
    }
    if (saved == 0 && faced >= 4) {
      return "$faced hetesből 0 fogás · a kiharcolt hetes kész gól";
    }
    return null;
  }

  // Félidő-zárás: a szünet előtti 5 perc gól-mérlege (a backend-kulccsal
  // azonos, 3 gólos különbség-küszöbbel).
  String? _firstHalfClose(Map<String, dynamic> r) {
    final m = ((r["fhc_matches"] as num?) ?? 0).toInt();
    if (m < 1) return null;
    final f = ((r["fhc_for"] as num?) ?? 0).toInt();
    final a = ((r["fhc_against"] as num?) ?? 0).toInt();
    if (a - f >= 3) return "$f–$a a szünet előtti 5 percben · elengedik";
    if (f - a >= 3) return "$f–$a a szünet előtti 5 percben · erősen zárnak";
    return null;
  }

  // Szoros meccs-mérleg: az 1-2 gólos meccsek kimenetele (2+ szoros
  // meccsnél; a backend-kulccsal azonos küszöb).
  String? _closeGames(Map<String, dynamic> r) {
    final w = ((r["cg_wins"] as num?) ?? 0).toInt();
    final l = ((r["cg_losses"] as num?) ?? 0).toInt();
    final d = ((r["cg_draws"] as num?) ?? 0).toInt();
    if (w + l + d < 2) return null;
    final merleg = d > 0 ? "$w–$l ($d döntetlen)" : "$w–$l";
    if (l >= 2 && l >= 2 * w) {
      return "$merleg a szoros meccseken · a hajrában megroppannak";
    }
    if (w >= 2 && w >= 2 * l) {
      return "$merleg a szoros meccseken · a szorosat hozzák";
    }
    return null;
  }

  // Gól utáni elalvás: a saját gólokra fél percen belül visszakapott
  // válasz-gólok aránya (5+ gólnál; a backend-kulccsal azonos küszöb).
  String? _postGoalLapses(Map<String, dynamic> r) {
    final goals = ((r["pgl_goals"] as num?) ?? 0).toInt();
    if (goals < 5) return null;
    final quick = ((r["pgl_quick"] as num?) ?? 0).toInt();
    final rate = 100.0 * quick / goals;
    if (rate >= 40.0) {
      return "$goals góljából $quick után jött azonnali válasz "
          "(${rate.round()}%) · gól után elalszanak";
    }
    if (rate <= 10.0 && goals >= 10) {
      return "$goals góljából csak $quick gyors válasz · gól után is "
          "ébren vannak";
    }
    return null;
  }

  // Fegyelem-esés: a kiállítások félidőnkénti eloszlása (3+ kiállításnál
  // és 2+ többletnél; a backend-kulccsal azonos küszöb).
  String? _disciplineFade(Map<String, dynamic> r) {
    final fh = ((r["disc_fh_susp"] as num?) ?? 0).toInt();
    final sh = ((r["disc_sh_susp"] as num?) ?? 0).toInt();
    if (fh + sh < 3) return null;
    if (sh - fh >= 2) {
      return "$fh → $sh kiállítás · a hajrában szabálytalankodnak";
    }
    if (fh - sh >= 2) return "$fh → $sh kiállítás · az elején kemények";
    return null;
  }

  // Labdabiztonság-esés: az eladás-ütem változása a 2. félidőre
  // (félidőnként 2+ perc mért birtoklásnál; a backend-kulccsal azonos
  // küszöb) — csak a kirívó romlás érdekes.
  String? _turnoverFade(Map<String, dynamic> r) {
    final fhPoss = ((r["tof_fh_poss_s"] as num?) ?? 0).toDouble();
    final shPoss = ((r["tof_sh_poss_s"] as num?) ?? 0).toDouble();
    if (fhPoss < 120.0 || shPoss < 120.0) return null;
    final fhTo = ((r["tof_fh_to"] as num?) ?? 0).toInt();
    final shTo = ((r["tof_sh_to"] as num?) ?? 0).toInt();
    final fh = 60.0 * fhTo / fhPoss;
    final sh = 60.0 * shTo / shPoss;
    if (sh - fh < 0.2) return null;
    return "${fh.toStringAsFixed(1)} → ${sh.toStringAsFixed(1)} "
        "eladás/perc · a 2. félidőben kienged";
  }

  // Időkérés-mérleg: működik-e a "mentő" időkérésük (2+ ítéletes
  // időkérésnél; a backend-kulcsokkal azonos küszöb).
  String? _timeoutRecord(Map<String, dynamic> r) {
    final broke = ((r["to_broke"] as num?) ?? 0).toInt();
    final failed = ((r["to_failed"] as num?) ?? 0).toInt();
    final total = broke + failed;
    if (total < 2) return null;
    if (broke > failed) {
      return "$broke/$total megtöri a sorozatot · működik";
    }
    if (failed > broke) {
      return "$failed/$total fordulat nélkül · hatástalan";
    }
    return null;
  }

  // Védekezés-fellazulás: a nyomás-átlag változása a 2. félidőre
  // (félidőnként 100+ mért kockánál; a backend-kulcsokkal azonos küszöb).
  String? _pressureFade(Map<String, dynamic> r) {
    final fhN = ((r["prf_fh_n"] as num?) ?? 0).toInt();
    final shN = ((r["prf_sh_n"] as num?) ?? 0).toInt();
    if (fhN < 100 || shN < 100) return null;
    final fhSum = ((r["prf_fh_sum_m"] as num?) ?? 0).toDouble();
    final shSum = ((r["prf_sh_sum_m"] as num?) ?? 0).toDouble();
    if (fhSum <= 0 || shSum <= 0) return null;
    final fh = fhSum / fhN;
    final sh = shSum / shN;
    final d = sh - fh;
    if (d >= 0.5) {
      return "${fh.toStringAsFixed(1)} → ${sh.toStringAsFixed(1)} m "
          "· a 2. félidőre fellazul";
    }
    if (d <= -0.5) {
      return "${fh.toStringAsFixed(1)} → ${sh.toStringAsFixed(1)} m "
          "· a hajrára szorosodik";
    }
    return null;
  }

  // Lövés-időzítés: az első hullámból lövők vs kivárók (5+ lőtt
  // támadásnál; a backend-kulcsokkal azonos küszöbök).
  String? _shotTiming(Map<String, dynamic> r) {
    final n = ((r["shtim_n"] as num?) ?? 0).toInt();
    if (n < 5) return null;
    final sum = ((r["shtim_sum_s"] as num?) ?? 0).toDouble();
    if (sum <= 0) return null;
    final early = ((r["shtim_early"] as num?) ?? 0).toInt();
    final earlyPct = 100.0 * early / n;
    final avg = sum / n;
    if (earlyPct >= 45.0) {
      return "${earlyPct.round()}% az első 8 mp-ben · első hullám";
    }
    if (avg >= 22.0) {
      return "átl. ${avg.toStringAsFixed(0)} mp a lövésig · kivárók";
    }
    return null;
  }

  // Passz-hossz: a hosszú (10 m+) passzok aránya és az átlaghossz (15+
  // mért passznál; a backend-kulcsokkal azonos küszöbök).
  String? _passLength(Map<String, dynamic> r) {
    final n = ((r["plen_n"] as num?) ?? 0).toInt();
    if (n < 15) return null;
    final sum = ((r["plen_sum_m"] as num?) ?? 0).toDouble();
    if (sum <= 0) return null;
    final longN = ((r["plen_long"] as num?) ?? 0).toInt();
    final avg = sum / n;
    final longPct = 100.0 * longN / n;
    if (longPct >= 30.0) {
      return "${longPct.round()}% hosszú (átl. ${avg.toStringAsFixed(0)} m) "
          "· elfogható";
    }
    if (avg <= 6.0) {
      return "átl. ${avg.toStringAsFixed(0)} m · rövid kombináció";
    }
    return null;
  }

  // Szerzés-magasság: az elöl (letámadásból) született szerzések aránya
  // (4+ szerzésnél; a backend-kulcsokkal azonos küszöbök).
  String? _stealHeight(Map<String, dynamic> r) {
    final n = ((r["steal_n"] as num?) ?? 0).toInt();
    if (n < 4) return null;
    final high = ((r["steal_high"] as num?) ?? 0).toInt();
    final pct = 100.0 * high / n;
    if (pct >= 35.0) {
      return "${pct.round()}% elöl ($high/$n) · élő letámadás";
    }
    if (pct <= 10.0 && n >= 6) {
      return "${pct.round()}% elöl · elöl nem zavarnak";
    }
    return null;
  }

  // Falba lövés: a lövés-kísérletek blokkon elakadó hányada (4+ blokknál;
  // a backend-kulcsokkal azonos küszöb) — csak a kirívó érdekes.
  String? _blockedRate(Map<String, dynamic> r) {
    final blocked = ((r["blk_for"] as num?) ?? 0).toInt();
    final attempts = ((r["blk_attempts"] as num?) ?? 0).toInt();
    if (blocked < 4 || attempts <= 0) return null;
    final pct = 100.0 * blocked / attempts;
    if (pct < 20.0) return null;
    return "${pct.round()}% blokkon akad el ($blocked/$attempts) · "
        "falba lőnek";
  }

  // Passz-tempó: passz/perc a saját birtoklásra vetítve (2+ perc mért
  // birtoklásnál; a backend-kulcsokkal azonos küszöbök) — a kirívó
  // (pörgetett / álló járatás) érdekes.
  String? _passTempo(Map<String, dynamic> r) {
    final poss = ((r["pt_poss_s"] as num?) ?? 0).toDouble();
    if (poss < 120.0) return null;
    final passes = ((r["pt_passes"] as num?) ?? 0).toInt();
    final perMin = 60.0 * passes / poss;
    if (perMin >= 22.0) {
      return "${perMin.round()} passz/perc · pörgetik";
    }
    if (perMin <= 12.0) {
      return "${perMin.round()} passz/perc · állva járatják";
    }
    return null;
  }

  // Engedett lövésminőség: a kapott lövések átlagos xG-je (8+ kapott
  // lövésnél; a backend-kulcsokkal azonos küszöbök) — a kirívó (ziccert
  // enged / kiszorít) érdekes.
  String? _allowedXg(Map<String, dynamic> r) {
    final n = ((r["def_shots_against"] as num?) ?? 0).toInt();
    if (n < 8) return null;
    final sum = ((r["xga_sum"] as num?) ?? 0).toDouble();
    if (sum <= 0) return null;
    final avg = sum / n;
    if (avg >= 0.38) {
      return "${avg.toStringAsFixed(2)} xG/lövés · ziccereket engednek";
    }
    if (avg <= 0.22) {
      return "${avg.toStringAsFixed(2)} xG/lövés · kiszorító fal";
    }
    return null;
  }

  // Védelmi tömörség: a fal átlagos y-terjedelme (100+ mért kockánál;
  // a backend-kulcsokkal azonos küszöbök) — tömör fal mellett a szélek,
  // széthúzott mellett a közép nyílik.
  String? _defWidth(Map<String, dynamic> r) {
    final n = ((r["defw_frames"] as num?) ?? 0).toInt();
    if (n < 100) return null;
    final sum = ((r["defw_sum_m"] as num?) ?? 0).toDouble();
    if (sum <= 0) return null;
    final avg = sum / n;
    if (avg <= 11.0) {
      return "${avg.toStringAsFixed(0)} m · tömör (a szélek nyitva)";
    }
    if (avg >= 15.0) {
      return "${avg.toStringAsFixed(0)} m · széthúzott (a közép nyitva)";
    }
    return null;
  }

  // Területi fölény: a birtoklás mekkora része zajlik az ellenfél térfelén
  // (100+ birtokos kockánál; a backend-kulcsokkal azonos küszöbök) — a
  // kirívó (elöl nyomnak / hátul ragadnak) érdekes.
  String? _fieldTilt(Map<String, dynamic> r) {
    final n = ((r["tilt_frames"] as num?) ?? 0).toInt();
    if (n < 100) return null;
    final opp = ((r["tilt_opp"] as num?) ?? 0).toInt();
    final pct = 100.0 * opp / n;
    if (pct >= 65.0) return "${pct.round()}% elöl · területi nyomás";
    if (pct <= 45.0) return "${pct.round()}% elöl · a saját térfelén ragad";
    return null;
  }

  // Támogatás-távolság: a labdás legközelebbi társának átlagtávolsága
  // (100+ mért kockánál; a backend-kulcsokkal azonos küszöbök) — a kirívó
  // (izolált labdás / szoros támogatás) érdekes.
  String? _supportDistance(Map<String, dynamic> r) {
    final n = ((r["sup_frames"] as num?) ?? 0).toInt();
    if (n < 100) return null;
    final sum = ((r["sup_sum_m"] as num?) ?? 0).toDouble();
    if (sum <= 0) return null;
    final iso = ((r["sup_iso"] as num?) ?? 0).toInt();
    final avg = sum / n;
    final isoPct = 100.0 * iso / n;
    if (avg >= 7.0 || isoPct >= 35.0) {
      return "átl. ${avg.toStringAsFixed(1)} m · ${isoPct.round()}% izolált "
          "· présre érzékeny";
    }
    if (avg <= 4.0) {
      return "átl. ${avg.toStringAsFixed(1)} m · szoros támogatás";
    }
    return null;
  }

  // Gól-koncentráció: a fő gólszerző részesedése (5+ azonosított gólnál;
  // a backend-kulcsokkal azonos küszöbök) — a kirívó (egy emberre épülő
  // vagy nagyon elosztott) gólszerzés érdekes.
  String? _goalConcentration(Map<String, dynamic> r) {
    final list = (r["scorer_goals"] as List?) ?? const [];
    if (list.isEmpty) return null;
    var total = 0;
    for (final w in list) {
      total += (((w as Map)["goals"] as num?) ?? 0).toInt();
    }
    if (total < 5) return null;
    final top = list.first as Map<String, dynamic>;
    final topGoals = ((top["goals"] as num?) ?? 0).toInt();
    final share = 100.0 * topGoals / total;
    if (share >= 40.0) {
      return "${top["player_id"]}-es · ${share.round()}% "
          "($topGoals/$total) · egy emberre épül";
    }
    if (share <= 25.0 && list.length >= 4) {
      return "elosztott (top ${share.round()}%) · csapat-védekezés kell";
    }
    return null;
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

  // Labdaeladó: a leggyengébb labdabiztonságú játékos (4+ eladás) — rá
  // érdemes presselni. A backend-kulcsokkal azonos küszöb.
  String? _turnoverPlayer(Map<String, dynamic> r) {
    final list = (r["turnover_players"] as List?) ?? const [];
    if (list.isEmpty) return null;
    final top = list.first as Map<String, dynamic>;
    final n = ((top["losses"] as num?) ?? 0).toInt();
    if (n < 4) return null;
    return "${top["player_id"]}-es · $n eladás";
  }

  // Hajrá-ember: aki a meccs végén gólt szerez (2+ hajrá-gól) — rá a
  // hajrában fokozott figyelem. A backend-kulcsokkal azonos küszöb.
  String? _clutchScorer(Map<String, dynamic> r) {
    final list = (r["clutch_scorers"] as List?) ?? const [];
    if (list.isEmpty) return null;
    final top = list.first as Map<String, dynamic>;
    final n = ((top["goals"] as num?) ?? 0).toInt();
    if (n < 2) return null;
    return "${top["player_id"]}-es · $n hajrá-gól";
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

  // Lövőerő-esés: az 1. és 2. félidei átlag lövés-sebesség összevetése
  // (félidőnként 5+ mért lövésnél; a backend-kulccsal azonos küszöb) —
  // csak a kirívó (fáradnak / erősödnek) érdekes.
  String? _shotFade(Map<String, dynamic> r) {
    final fhN = ((r["ssf_fh_n"] as num?) ?? 0).toInt();
    final shN = ((r["ssf_sh_n"] as num?) ?? 0).toInt();
    if (fhN < 5 || shN < 5) return null;
    final fhAvg = ((r["ssf_fh_sum_kmh"] as num?) ?? 0).toDouble() / fhN;
    final shAvg = ((r["ssf_sh_sum_kmh"] as num?) ?? 0).toDouble() / shN;
    if (fhAvg <= 0) return null;
    final drop = 100.0 * (fhAvg - shAvg) / fhAvg;
    if (drop >= 8.0) {
      return "${fhAvg.toStringAsFixed(0)} → ${shAvg.toStringAsFixed(0)} km/h "
          "(−${drop.round()}%) · fáradnak";
    }
    if (drop <= -8.0) {
      return "${fhAvg.toStringAsFixed(0)} → ${shAvg.toStringAsFixed(0)} km/h "
          "· a hajrában erősödnek";
    }
    return null;
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
      if (_passTempo(r) != null) ["Passz-tempó", _passTempo(r)!],
      if (_blockedRate(r) != null) ["Falba lövés", _blockedRate(r)!],
      if (_stealHeight(r) != null)
        ["Szerzés-magasság", _stealHeight(r)!],
      if (_passLength(r) != null) ["Passz-hossz", _passLength(r)!],
      if (_shotTiming(r) != null) ["Lövés-időzítés", _shotTiming(r)!],
      if (_pressureFade(r) != null)
        ["Védekezés-fellazulás", _pressureFade(r)!],
      if (_timeoutRecord(r) != null)
        ["Időkérés-mérleg", _timeoutRecord(r)!],
      if (_turnoverFade(r) != null)
        ["Labdabiztonság-esés", _turnoverFade(r)!],
      if (_gkSaveFade(r) != null) ["Kapus-forma", _gkSaveFade(r)!],
      if (_leadProtection(r) != null) ["Előny-őrzés", _leadProtection(r)!],
      if (_disciplineFade(r) != null)
        ["Fegyelem-esés", _disciplineFade(r)!],
      if (_postGoalLapses(r) != null)
        ["Gól utáni elalvás", _postGoalLapses(r)!],
      if (_closeGames(r) != null) ["Szoros meccsek", _closeGames(r)!],
      if (_firstHalfClose(r) != null)
        ["Félidő-zárás", _firstHalfClose(r)!],
      if (_sevenDefense(r) != null) ["Hetes-védés", _sevenDefense(r)!],
      if (_gkChangeEffect(r) != null)
        ["Kapuscsere-hatás", _gkChangeEffect(r)!],
      if (_missPunishment(r) != null)
        ["Kihagyott ziccer ára", _missPunishment(r)!],
      if (_paceFade(r) != null) ["Tempó-esés", _paceFade(r)!],
      if (_htComeback(r) != null)
        ["Félidei fordítás", _htComeback(r)!],
      if (_parityBreaks(r) != null)
        ["Holtpont-mérleg", _parityBreaks(r)!],
      if (_runContainment(r) != null)
        ["Sorozat-törés", _runContainment(r)!],
      if (_bigSaveMomentum(r) != null)
        ["Bravúr utáni lendület", _bigSaveMomentum(r)!],
      if (_finishFade(r) != null)
        ["Befejezés-esés", _finishFade(r)!],
      if (_shotAccuracy(r) != null)
        ["Célzás-pontosság", _shotAccuracy(r)!],
      if (_sideBias(r) != null)
        ["Oldal-részrehajlás", _sideBias(r)!],
      if (_attackRhythm(r) != null)
        ["Ritmus-egyhangúság", _attackRhythm(r)!],
      if (_shotConcentration(r) != null)
        ["Lövő-koncentráció", _shotConcentration(r)!],
      if (_gkWeakSide(r) != null)
        ["Kapus-gyengeoldal", _gkWeakSide(r)!],
      if (_turnoverTiming(r) != null)
        ["Eladás-időzítés", _turnoverTiming(r)!],
      if (_passSecurity(r) != null)
        ["Pressz-tűrés", _passSecurity(r)!],
      if (_secondChanceAllowed(r) != null)
        ["Lepattanó-fal", _secondChanceAllowed(r)!],
      if (_assistReliance(r) != null)
        ["Asszist-függés", _assistReliance(r)!],
      if (_tiltFade(r) != null)
        ["Területi-fölény-esés", _tiltFade(r)!],
      if (_gkOutlet(r) != null)
        ["Kapus-indítás", _gkOutlet(r)!],
      if (_turnoverPunishment(r) != null)
        ["Eladás-büntetés", _turnoverPunishment(r)!],
      if (_concededSide(r) != null)
        ["Engedett-oldal", _concededSide(r)!],
      if (_droughtAnatomy(r) != null)
        ["Gólcsend-anatómia", _droughtAnatomy(r)!],
      if (_wallGaps(r) != null)
        ["Fal-rés", _wallGaps(r)!],
      if (_attackMotion(r) != null)
        ["Támadó-mozgás", _attackMotion(r)!],
      if (_gkOutletSecurity(r) != null)
        ["Indítás-biztonság", _gkOutletSecurity(r)!],
      if (_pivotDefense(r) != null)
        ["Beálló-védekezés", _pivotDefense(r)!],
      if (_shotRelease(r) != null)
        ["Elsütés-idő", _shotRelease(r)!],
      if (_restartSpeed(r) != null)
        ["Középkezdés-tempó", _restartSpeed(r)!],
      if (_assistConcentration(r) != null)
        ["Előkészítő-függés", _assistConcentration(r)!],
      if (_goalBuildup(r) != null)
        ["Gól-előkészítés", _goalBuildup(r)!],
      if (_gkBreakResponse(r) != null)
        ["Lerohanás-védés", _gkBreakResponse(r)!],
      if (_sideSwitching(r) != null)
        ["Oldalváltás", _sideSwitching(r)!],
      if (_screenUsage(r) != null)
        ["Elzárás-használat", _screenUsage(r)!],
      if (_screenDefense(r) != null)
        ["Elzárás-védekezés", _screenDefense(r)!],
      if (_passRisk(r) != null)
        ["Passz-kockázat", _passRisk(r)!],
      if (_clutchShotQuality(r) != null)
        ["Hajrá-lövésválasztás", _clutchShotQuality(r)!],
      if (_counterPress(r) != null)
        ["Ellen-press", _counterPress(r)!],
      if (_overloadFinishing(r) != null)
        ["Fölény-befejezés", _overloadFinishing(r)!],
      if (_shorthandedAttack(r) != null)
        ["Hátrány-támadás", _shorthandedAttack(r)!],
      if (_clutchTurnovers(r) != null)
        ["Hajrá-eladás", _clutchTurnovers(r)!],
      if (_gkOutletSide(r) != null)
        ["Kapus-indítás iránya", _gkOutletSide(r)!],
      if (_doubleTeams(r) != null)
        ["Kettőzés", _doubleTeams(r)!],
      if (_gkFreeShotSaves(r) != null)
        ["Kapus szabad lövés ellen", _gkFreeShotSaves(r)!],
      if (_powerplayDefense(r) != null)
        ["Emberelőny-védekezés", _powerplayDefense(r)!],
      if (_costlyTurnovers(r) != null)
        ["Drága eladók", _costlyTurnovers(r)!],
      if (_wingDefense(r) != null)
        ["Szélső-védekezés", _wingDefense(r)!],
      if (_shooterPlacement(r) != null)
        ["Lövő-kapuoldal", _shooterPlacement(r)!],
      if (_shooterPower(r) != null)
        ["Lövő-erő", _shooterPower(r)!],
      if (_plusMinus(r) != null)
        ["Játékos-mérleg", _plusMinus(r)!],
      if (_targetedDefender(r) != null)
        ["Célba vett védő", _targetedDefender(r)!],
      if (_formationSwitching(r) != null)
        ["Védekezés-váltás", _formationSwitching(r)!],
      if (_holdTime(r) != null) ["Labdatartás", _holdTime(r)!],
      if (_shotPowerFade(r) != null)
        ["Lövőerő-esés", _shotPowerFade(r)!],
      if (_subBlocks(r) != null) ["Csere-blokkok", _subBlocks(r)!],
      if (_pairPlusMinus(r) != null)
        ["Páros-mérleg", _pairPlusMinus(r)!],
      if (_timeoutTiming(r) != null)
        ["Időkérés-időzítés", _timeoutTiming(r)!],
      if (_attackStarters(r) != null)
        ["Támadás-indítók", _attackStarters(r)!],
      if (_assistZones(r) != null)
        ["Gólpassz-zónák", _assistZones(r)!],
      if (_roleGoals(r) != null) ["Gólmegoszlás posztonként", _roleGoals(r)!],
      if (_concededRoles(r) != null)
        ["Kapott gólok posztonként", _concededRoles(r)!],
      if (_turnoverClusters(r) != null)
        ["Hiba-sorozatok", _turnoverClusters(r)!],
      if (_gkRoleSaves(r) != null)
        ["Kapus-védés posztonként", _gkRoleSaves(r)!],
      if (_attackOutcomes(r) != null)
        ["Támadás-kimenetel", _attackOutcomes(r)!],
      if (_rotation(r) != null) ["Rotáció", _rotation(r)!],
      if (_ballWinner(r) != null) ["Labdaszerző", _ballWinner(r)!],
      if (_turnoverPlayer(r) != null)
        ["Labdaeladó", _turnoverPlayer(r)!],
      if (_clutchScorer(r) != null) ["Hajrá-ember", _clutchScorer(r)!],
      if (_gkDepth(r) != null) ["Kapus-típus", _gkDepth(r)!],
      if (_transOffense(r) != null)
        ["Átmenet-támadás", _transOffense(r)!],
      if (_shotRange(r) != null) ["Lövés-távolság", _shotRange(r)!],
      if (_gkWeakRange(r) != null) ["Kapus gyenge sávja", _gkWeakRange(r)!],
      if (_goalPlacement(r) != null) ["Kapu-sarok", _goalPlacement(r)!],
      if (_wingFinishing(r) != null) ["Szélső-játék", _wingFinishing(r)!],
      if (_secondChance(r) != null) ["Második roham", _secondChance(r)!],
      if (_defLine(r) != null) ["Védekezési vonal", _defLine(r)!],
      if (_defWidth(r) != null) ["Fal-szélesség", _defWidth(r)!],
      if (_allowedXg(r) != null)
        ["Engedett lövésminőség", _allowedXg(r)!],
      if (_passDirection(r) != null) ["Passz-irány", _passDirection(r)!],
      if (_assistSource(r) != null) ["Gólpassz-forrás", _assistSource(r)!],
      if (_restart(r) != null) ["Szünet-kezdés", _restart(r)!],
      if (_opening(r) != null) ["Kezdés", _opening(r)!],
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
      if (_goalConcentration(r) != null)
        ["Gól-koncentráció", _goalConcentration(r)!],
      if (_supportDistance(r) != null)
        ["Támogatás-távolság", _supportDistance(r)!],
      if (_fieldTilt(r) != null) ["Területi fölény", _fieldTilt(r)!],
      if (_recovery(r) != null) ["Visszaérés", _recovery(r)!],
      if (_postGoals(r) != null) ["Gól-posztok", _postGoals(r)!],
      if (_bigChances(r) != null) ["Ziccer-mérleg", _bigChances(r)!],
      if (_halfPattern(r) != null) ["Félidő-mérleg", _halfPattern(r)!],
      if (_shotPower(r) != null) ["Lövés-erő", _shotPower(r)!],
      if (_shotFade(r) != null) ["Lövőerő-esés", _shotFade(r)!],
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
