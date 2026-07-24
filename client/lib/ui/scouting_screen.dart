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
