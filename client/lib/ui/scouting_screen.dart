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
import "error_text.dart";
import "waiting.dart";

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

  // --- Mutató-fal állapota -------------------------------------------------
  // Háromszáz körüli mutató egyetlen listában olvashatatlan. A fal ezért
  // KERESHETŐ és CSOPORTOSÍTOTT: alapból csak a kiemelt mutatók látszanak,
  // a csoportok lenyithatók, keresésre pedig automatikusan kinyílnak.
  String _metricQuery = "";
  final Set<String> _openMetricGroups = <String>{};

  // Hosszú felsorolások (edzői kulcsok, meccsterv) alapból rövidítve
  // jelennek meg — egy harminc pontos lista olvasatlan marad.
  bool _allKeys = false;
  bool _allPlan = false;

  /// Ennyi tétel látszik alapból a hosszú felsorolásokból.
  static const int _listPreview = 6;

  /// Szekció-ugráshoz: címke → a kártya kulcsa. A gördítést a
  /// `Scrollable.ensureVisible` intézi, ezért nem kell külön vezérlő
  /// (és nincs mit felszabadítani sem).
  final Map<String, GlobalKey> _sectionKeys = <String, GlobalKey>{};

  /// "Mind a N megjelenítése" / "Rövidítve" kapcsoló a hosszú listákhoz.
  /// Szándékosan kimondja, hogy a rövidítés a jelentés SORRENDJÉBŐL vág,
  /// nem fontossági rangsorból — rangsort a rendszer itt nem állít.
  Widget _moreToggle(int total, bool expanded, VoidCallback onTap) {
    if (total <= _listPreview) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: TextButton.icon(
        onPressed: onTap,
        icon: Icon(expanded ? Icons.expand_less : Icons.expand_more,
            size: 18),
        label: Text(expanded
            ? "Rövidítve (az első $_listPreview)"
            : "Mind a $total megjelenítése"),
      ),
    );
  }

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
        _error = "${humanError(e)}";
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
          SnackBar(content: Text("Export hiba: ${humanError(e)}")));
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
          tooltip: "Vissza",
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
    if (_loading) {
      return const WaitingView("Felderítő jelentés készül…",
          hint: "Több száz elemző réteg fut le a kijelölt meccseken. "
              "Több meccsnél ez PERCEKIG tart — ez normális.",
          icon: Icons.assignment_outlined);
    }
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
    final hasNarrative =
        ((r["narrative"] as List?) ?? const []).isNotEmpty;
    // Egyszer építjük fel: a sáv, a feltétel és a tartalom is ezt nézi.
    final keeperCard = _keeperPrepCard(r);
    // A sávban CSAK a ténylegesen megjelenő szekciók szerepelnek —
    // egy üresbe ugró gomb rosszabb, mint a hiánya.
    final jumps = <(String, IconData)>[
      if (hasNarrative) ("Így játszanak", Icons.menu_book_outlined),
      ("Hogyan játssz ellenük", Icons.gps_fixed),
      ("Erősségek / gyengeségek", Icons.compare_arrows),
      ("Mutatók", Icons.grid_view),
      ("Honnan lőnek", Icons.sports_handball),
      ("Honnan kapják a lövéseket", Icons.shield_outlined),
      if (_playbookMatch != null) ("Ismert figuráik", Icons.route_outlined),
      ("Védekezésük", Icons.security),
      if (keeperCard != null)
        ("Kapus-felkészítés", Icons.sports_kabaddi),
      ("Kulcsjátékosok", Icons.person_outline),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _jumpBar(jumps),
        const SizedBox(height: AppSpacing.md),
        Expanded(
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (hasNarrative) ...[
                  KeyedSubtree(
                      key: _sectionKey("Így játszanak"),
                      child: _narrativeCard(r)),
                  const SizedBox(height: AppSpacing.lg),
                ],
                KeyedSubtree(
                    key: _sectionKey("Hogyan játssz ellenük"),
                    child: _keysCard(r)),
                if (_matchup.isNotEmpty) _matchupCard(),
                const SizedBox(height: AppSpacing.lg),
                KeyedSubtree(
                  key: _sectionKey("Erősségek / gyengeségek"),
                  child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                            child: _listCard("ERŐSSÉGEK", r["strengths"],
                                AppColors.accent, Icons.trending_up)),
                        const SizedBox(width: AppSpacing.lg),
                        Expanded(
                            child: _listCard("GYENGESÉGEK", r["weaknesses"],
                                AppColors.away, Icons.trending_down)),
                      ]),
                ),
                const SizedBox(height: AppSpacing.lg),
                KeyedSubtree(
                    key: _sectionKey("Mutatók"), child: _metricsCard(r)),
                const SizedBox(height: AppSpacing.lg),
                KeyedSubtree(
                    key: _sectionKey("Honnan lőnek"),
                    child: _shotZonesCard(r)),
                const SizedBox(height: AppSpacing.lg),
                KeyedSubtree(
                    key: _sectionKey("Honnan kapják a lövéseket"),
                    child: _defZonesCard(r)),
                const SizedBox(height: AppSpacing.lg),
                if (_playbookMatch != null) ...[
                  KeyedSubtree(
                      key: _sectionKey("Ismert figuráik"),
                      child: _playbookCard(_playbookMatch!)),
                  const SizedBox(height: AppSpacing.lg),
                ],
                KeyedSubtree(
                    key: _sectionKey("Védekezésük"), child: _defenseCard(r)),
                const SizedBox(height: AppSpacing.lg),
                if (keeperCard != null) ...[
                  KeyedSubtree(
                      key: _sectionKey("Kapus-felkészítés"),
                      child: keeperCard),
                  const SizedBox(height: AppSpacing.lg),
                ],
                KeyedSubtree(
                    key: _sectionKey("Kulcsjátékosok"),
                    child: _keyPlayersCard(r)),
                const SizedBox(height: AppSpacing.xl),
              ],
            ),
          ),
        ),
      ],
    );
  }

  /// Szekció-ugró sáv: a jelentés kártyáira ugrik egy koppintással.
  ///
  /// A jelentés nyolc-kilenc nagy kártyából áll, képernyőkön át gördül.
  /// Egy edző a meccs előtt jellemzően EGY dolgot keres ("mit csinálnak
  /// hetesnél?"), és nem akar addig görgetni — ez a sáv a tartalomjegyzék.
  Widget _jumpBar(List<(String, IconData)> jumps) {
    return SizedBox(
      height: 38,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: jumps.length,
        separatorBuilder: (_, __) => const SizedBox(width: AppSpacing.sm),
        itemBuilder: (context, i) {
          final (label, icon) = jumps[i];
          return ActionChip(
            avatar: Icon(icon, size: 16, color: AppColors.textSecondary),
            label: Text(label),
            tooltip: "Ugrás ide: $label",
            onPressed: () => _jumpTo(label),
          );
        },
      ),
    );
  }

  /// A szekcióhoz tartozó kulcs (igény szerint jön létre).
  GlobalKey _sectionKey(String label) =>
      _sectionKeys.putIfAbsent(label, () => GlobalKey());

  /// Odagördít a szekcióhoz. Ha a kártya épp nincs kirakva (nem lehet
  /// megtalálni), NEM csinálunk semmit — ugrás helyett soha ne rántsuk
  /// el a jelentést egy rossz helyre.
  void _jumpTo(String label) {
    final ctx = _sectionKeys[label]?.currentContext;
    if (ctx == null) return;
    Scrollable.ensureVisible(ctx,
        duration: const Duration(milliseconds: 320),
        curve: Curves.easeOut,
        alignment: 0.02);
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
            for (final p in (_allPlan
                ? _matchup
                : _matchup.take(_listPreview)))
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text("• $p",
                    style: AppText.label.copyWith(
                        fontSize: 12.5, color: AppColors.textPrimary)),
              ),
            _moreToggle(_matchup.length, _allPlan,
                () => setState(() => _allPlan = !_allPlan)),
          ],
        ),
      ),
    );
  }

  Widget _keysCard(Map<String, dynamic> r) {
    final keys = (r["keys_to_game"] as List?) ?? const [];
    final shownKeys = _allKeys ? keys : keys.take(_listPreview).toList();
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
          for (final k in shownKeys)
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
          _moreToggle(keys.length, _allKeys,
              () => setState(() => _allKeys = !_allKeys)),
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
  // 5+ mért lövés, 8% eltérés; a backend-kulccsal azonos küszöbök).
  String? _shotPowerFade(Map<String, dynamic> r) {
    final fhN = ((r["ssf_fh_n"] as num?) ?? 0).toInt();
    final shN = ((r["ssf_sh_n"] as num?) ?? 0).toInt();
    if (fhN < 5 || shN < 5) return null;
    final fh = ((r["ssf_fh_sum_kmh"] as num?) ?? 0).toDouble() / fhN;
    final sh = ((r["ssf_sh_sum_kmh"] as num?) ?? 0).toDouble() / shN;
    if (fh <= 0) return null;
    if (100.0 * (fh - sh) / fh >= 8.0) {
      return "a 2. félidőre esik a lövéserejük: "
          "${fh.toStringAsFixed(0)} → ${sh.toStringAsFixed(0)} km/h · "
          "a hajrában kintebb jöhet a fal";
    }
    if (100.0 * (sh - fh) / fh >= 8.0) {
      return "a 2. félidőre erősödik a lövésük: "
          "${fh.toStringAsFixed(0)} → ${sh.toStringAsFixed(0)} km/h · "
          "a kapusnak korábban kell indulnia, a fal a szöget zárja";
    }
    return null;
  }

  // Labdatartás-idő: kinél áll meg a labda (5+ labdás szakasz, 0,8 mp
  // a csapatátlag felett; a backend-kulccsal azonos küszöbök).
  // Kapus-bevonás: mennyire játszanak vissza a kapusnak (8+ mért
  // birtoklás; 25% felett sok, 5% alatt semennyi — a
  // backend-kulccsal azonos küszöbök).
  String? _keeperInvolvement(Map<String, dynamic> r) {
    final spells = ((r["kiv_spells"] as num?) ?? 0).toInt();
    final withGk = ((r["kiv_with"] as num?) ?? 0).toInt();
    if (spells < 8) return null;
    final pct = 100.0 * withGk / spells;
    if (pct >= 25.0) {
      return "sokat játszanak vissza a kapusnak (a birtoklásaik "
          "${pct.toStringAsFixed(0)}%-ában) · a letámadásnak rá is ki "
          "kell terjednie";
    }
    if (pct <= 5.0) {
      return "nem játszanak vissza a kapusnak (a birtoklásaiknak csak "
          "${pct.toStringAsFixed(0)}%-ában) · a passzsávokat kell "
          "zárni, a kapusra menni fölösleges";
    }
    return null;
  }

  // Keresztjáték: mennyit kereszteznek a hátsó sorban (8+ támadás;
  // 1,0 felett sok, 0,3 alatt statikus — a backend-kulccsal azonos
  // küszöbök).
  String? _crossingRuns(Map<String, dynamic> r) {
    final attacks = ((r["crx_attacks"] as num?) ?? 0).toInt();
    final crosses = ((r["crx_crosses"] as num?) ?? 0).toInt();
    if (attacks < 8) return null;
    final per = crosses / attacks;
    if (per >= 1.0) {
      return "sokat kereszteznek (támadásonként "
          "${per.toStringAsFixed(1)} oldalcsere) · a váltás-fegyelem "
          "dönt, hangos átadásokkal";
    }
    if (per <= 0.3) {
      return "statikus a hátsó soruk (${per.toStringAsFixed(1)} "
          "keresztezés támadásonként) · ember-ember tartás is "
          "vállalható ellenük";
    }
    return null;
  }

  // Szélső-futtatás: lendületből vagy állva kapják-e (6+ átvétel;
  // 55% felett futtatott, 25% alatt álló — a backend-kulccsal azonos
  // küszöbök).
  String? _wingService(Map<String, dynamic> r) {
    final rec = ((r["wsv_receptions"] as num?) ?? 0).toInt();
    final run = ((r["wsv_running"] as num?) ?? 0).toInt();
    if (rec < 6) return null;
    final pct = 100.0 * run / rec;
    if (pct >= 55.0) {
      return "futtatva kapják a szélsők ($run/$rec átvétel "
          "mozgásból) · a futópassz sávját zárjátok, a kifutás "
          "késni fog";
    }
    if (pct <= 25.0) {
      return "állva kapják a szélsők (csak $run/$rec mozgásból) · "
          "bátor, korai kifutással lezárhatók";
    }
    return null;
  }

  // Beálló-futtatás: mozgásból vagy állva kapja-e a beálló (5+
  // átvétel; 55% felett lefordulós, 25% alatt beragadt — a
  // backend-kulccsal azonos küszöbök).
  String? _pivotService(Map<String, dynamic> r) {
    final rec = ((r["psv_receptions"] as num?) ?? 0).toInt();
    final run = ((r["psv_running"] as num?) ?? 0).toInt();
    if (rec < 5) return null;
    final pct = 100.0 * run / rec;
    if (pct >= 55.0) {
      return "mozgásból kapja a beállójuk ($run/$rec átvétel "
          "lefordulásból) · a bejátszás ELŐTT lépjetek elé, az "
          "átvétel utáni birkózás késő";
    }
    if (pct <= 25.0) {
      return "állva, beragadva kap a beállójuk (csak $run/$rec "
          "mozgásból) · testes elé állás + bejátszás utáni azonnali "
          "kettőzés";
    }
    return null;
  }

  // Kontra-hullámok: az első ember vagy a befutó fejezi be (5+
  // lövésig jutó kontra; 50% felett második hullám, 20% alatt első
  // ember — a backend-kulccsal azonos küszöbök).
  String? _fastBreakWaves(Map<String, dynamic> r) {
    final breaks = ((r["fbw_breaks"] as num?) ?? 0).toInt();
    final second = ((r["fbw_second"] as num?) ?? 0).toInt();
    if (breaks < 5) return null;
    final pct = 100.0 * second / breaks;
    if (pct >= 50.0) {
      return "a második hullám fejezi be a kontráikat ($second/"
          "$breaks a befutó lövésével) · az első ember felvétele "
          "nem elég: a középső sávot töltsétek fel visszafutásnál";
    }
    if (pct <= 20.0) {
      return "az első ember fejezi be a kontráikat (csak $second/"
          "$breaks a befutóé) · az indítópassz elvágása + az első "
          "ember korai felvétele megöli a kontrát";
    }
    return null;
  }

  // Kontra-elszökés: előre szökött emberrel vagy együtt futnak fel
  // (5+ kontra; 40% felett elszökős, 10% alatt együttes — a
  // backend-kulccsal azonos küszöbök).
  String? _fastBreakHeadstart(Map<String, dynamic> r) {
    final breaks = ((r["fbh_breaks"] as num?) ?? 0).toInt();
    final ahead = ((r["fbh_ahead"] as num?) ?? 0).toInt();
    if (breaks < 5) return null;
    final pct = 100.0 * ahead / breaks;
    if (pct >= 40.0) {
      return "előre szökött emberrel kontráznak ($ahead/$breaks "
          "lerohanás a labda előtt váró játékossal) · állandó "
          "mélységbiztosítás + a hosszú indítás elvágása";
    }
    if (pct <= 10.0) {
      return "együtt futnak fel a kontráik (csak $ahead/$breaks "
          "elszökött emberrel) · az első két visszafutó lassítson, "
          "a védelem beér";
    }
    return null;
  }

  // Lefogott lövők: kinek a lövését viszi el a fal (4+ lefogott
  // lövés; 50%+ részarány, holtverseny nélkül — a backend-kulccsal
  // azonos küszöbök).
  String? _blockedShooters(Map<String, dynamic> r) {
    final blocked = ((r["bsh_blocked"] as num?) ?? 0).toInt();
    final shooters = (r["bsh_shooters"] as Map?) ?? {};
    if (blocked < 4 || shooters.isEmpty) return null;
    final entries = shooters.entries.toList()
      ..sort((a, b) =>
          ((b.value as num?) ?? 0).compareTo((a.value as num?) ?? 0));
    final top = entries.first;
    final n = ((top.value as num?) ?? 0).toInt();
    final tie = entries.length > 1 &&
        ((entries[1].value as num?) ?? 0).toInt() == n;
    if (tie || 100.0 * n / blocked < 50.0) return null;
    return "a(z) ${top.key} mezes lövőjük lövését rendre elviszi a "
        "fal ($n/$blocked lefogott lövés az övé) · ellene falban "
        "maradni éri meg, nem kifutni";
  }

  // Gólpassz-posztok: melyik poszt készíti elő a gólokat (5+
  // gólpassz; 45%+ részarány, holtverseny nélkül — a
  // backend-kulccsal azonos küszöbök).
  String? _assistsByRole(Map<String, dynamic> r) {
    final assists = ((r["abr_assists"] as num?) ?? 0).toInt();
    final roles = (r["abr_roles"] as Map?) ?? {};
    if (assists < 5 || roles.isEmpty) return null;
    final entries = roles.entries.toList()
      ..sort((a, b) =>
          ((b.value as num?) ?? 0).compareTo((a.value as num?) ?? 0));
    final top = entries.first;
    final n = ((top.value as num?) ?? 0).toInt();
    final tie = entries.length > 1 &&
        ((entries[1].value as num?) ?? 0).toInt() == n;
    if (tie || 100.0 * n / assists < 45.0) return null;
    return "a góljaikat a(z) ${top.key} posztról készítik elő "
        "($n/$assists gólpassz) · az ő kezét fogd meg: kettőzés / "
        "a gólpassz-sáv zárása";
  }

  // Kiállítás-posztok: melyik poszt hozza a kétperceseket (3+
  // kiharcolt kiállítás; 50%+ részarány, holtverseny nélkül — a
  // backend-kulccsal azonos küszöbök).
  String? _suspEarnerRoles(Map<String, dynamic> r) {
    final susp = ((r["sur_suspensions"] as num?) ?? 0).toInt();
    final roles = (r["sur_roles"] as Map?) ?? {};
    if (susp < 3 || roles.isEmpty) return null;
    final entries = roles.entries.toList()
      ..sort((a, b) =>
          ((b.value as num?) ?? 0).compareTo((a.value as num?) ?? 0));
    final top = entries.first;
    final n = ((top.value as num?) ?? 0).toInt();
    final tie = entries.length > 1 &&
        ((entries[1].value as num?) ?? 0).toInt() == n;
    if (tie || 100.0 * n / susp < 50.0) return null;
    return "a kétperceseket a(z) ${top.key} posztról hozzák "
        "($n/$susp kiharcolt kiállítás) · ellene fegyelmezett kéz, "
        "korai testes lépés — ne adj emberelőnyt";
  }

  // Falba lövő posztok: melyik poszt lő a falba (4+ lefogott lövés;
  // 50%+ részarány, holtverseny nélkül — a backend-kulccsal azonos
  // küszöbök).
  String? _blockedByRole(Map<String, dynamic> r) {
    final blocked = ((r["bbr_blocked"] as num?) ?? 0).toInt();
    final roles = (r["bbr_roles"] as Map?) ?? {};
    if (blocked < 4 || roles.isEmpty) return null;
    final entries = roles.entries.toList()
      ..sort((a, b) =>
          ((b.value as num?) ?? 0).compareTo((a.value as num?) ?? 0));
    final top = entries.first;
    final n = ((top.value as num?) ?? 0).toInt();
    final tie = entries.length > 1 &&
        ((entries[1].value as num?) ?? 0).toInt() == n;
    if (tie || 100.0 * n / blocked < 50.0) return null;
    return "a falba lőtt lövéseik a(z) ${top.key} posztról jönnek "
        "($n/$blocked lefogott lövés) · ott a fal tartása elég, "
        "nem kell kilépni";
  }

  // Felhozatal-posztok: melyik posztra hozzák fel a labdát (4+
  // indítás-célpont; 50%+ részarány, holtverseny nélkül — a
  // backend-kulccsal azonos küszöbök).
  String? _outletTargetRoles(Map<String, dynamic> r) {
    final outlets = ((r["otr_outlets"] as num?) ?? 0).toInt();
    final roles = (r["otr_roles"] as Map?) ?? {};
    if (outlets < 4 || roles.isEmpty) return null;
    final entries = roles.entries.toList()
      ..sort((a, b) =>
          ((b.value as num?) ?? 0).compareTo((a.value as num?) ?? 0));
    final top = entries.first;
    final n = ((top.value as num?) ?? 0).toInt();
    final tie = entries.length > 1 &&
        ((entries[1].value as num?) ?? 0).toInt() == n;
    if (tie || 100.0 * n / outlets < 50.0) return null;
    return "a felhozataluk a(z) ${top.key} posztra épül ($n/$outlets "
        "indítás-célpont) · a letámadásnál őt fogd: nála akad meg a "
        "felhozatal";
  }

  // Kontra-esés: melyik félidőben kontráznak (félidőnként 5+
  // támadás; 15 százalékpontos váltás — a backend-kulccsal azonos
  // küszöbök).
  String? _breakShareFade(Map<String, dynamic> r) {
    final fhA = ((r["brf_fh_attacks"] as num?) ?? 0).toInt();
    final fhB = ((r["brf_fh_breaks"] as num?) ?? 0).toInt();
    final shA = ((r["brf_sh_attacks"] as num?) ?? 0).toInt();
    final shB = ((r["brf_sh_breaks"] as num?) ?? 0).toInt();
    if (fhA < 5 || shA < 5) return null;
    final fhPct = 100.0 * fhB / fhA;
    final shPct = 100.0 * shB / shA;
    if (shPct - fhPct <= -15.0) {
      return "a második félidőben eláll a kontrájuk "
          "(${fhPct.toStringAsFixed(0)}% → "
          "${shPct.toStringAsFixed(0)}% lerohanás-arány) · az elejét "
          "éld túl, a szünet után a felállt fal dolgozik";
    }
    if (shPct - fhPct >= 15.0) {
      return "a hajrára kontrázósabbak (${fhPct.toStringAsFixed(0)}% "
          "→ ${shPct.toStringAsFixed(0)}%) · a második félidőben "
          "duplán szigorú visszafutás-fegyelem";
    }
    return null;
  }

  // Szélső-mélység: milyen mélyről lőnek a szélsők (5+ lövés;
  // 6,5 m alatt mély, 8,5 m felett messzi — a backend-kulccsal
  // azonos küszöbök).
  String? _wingShotDepth(Map<String, dynamic> r) {
    final shots = ((r["wsd_shots"] as num?) ?? 0).toInt();
    final sum = ((r["wsd_depth_sum_m"] as num?) ?? 0).toDouble();
    if (shots < 5) return null;
    final avg = sum / shots;
    if (avg <= 6.5) {
      return "mélyre befutó szélsők (átlag "
          "${avg.toStringAsFixed(1)} m-ről lőnek) · a kapus várjon, "
          "a szöget a kifutó védő zárja a befutás előtt";
    }
    if (avg >= 8.5) {
      return "messziről lövő szélsők (átlag "
          "${avg.toStringAsFixed(1)} m) · a szög ráengedhető, a "
          "kapus bátran jöhet ki";
    }
    return null;
  }

  // Kettőző emberek: ki jön másodiknak a labdásra (50+ kettőzött
  // kocka; 40%+ részarány, holtverseny nélkül — a backend-kulccsal
  // azonos küszöbök).
  String? _doublingDefenders(Map<String, dynamic> r) {
    final frames = ((r["dtp_frames"] as num?) ?? 0).toInt();
    final doublers = (r["dtp_doublers"] as Map?) ?? {};
    if (frames < 50 || doublers.isEmpty) return null;
    final entries = doublers.entries.toList()
      ..sort((a, b) =>
          ((b.value as num?) ?? 0).compareTo((a.value as num?) ?? 0));
    final top = entries.first;
    final n = ((top.value as num?) ?? 0).toInt();
    final tie = entries.length > 1 &&
        ((entries[1].value as num?) ?? 0).toInt() == n;
    if (tie || 100.0 * n / frames < 40.0) return null;
    return "kiszámítható a kettőzésük: a(z) ${top.key} mezes jön "
        "másodiknak (${(100.0 * n / frames).toStringAsFixed(0)}%) · "
        "a kettőzés jelére az ő embere felé az első passz";
  }

  // Hiba-állás: hátrányban szórják-e a labdát (vödrönként 5+
  // támadás; +10 pp kapkodás, -5 pp rendezettség — a backend-
  // kulccsal azonos küszöbök).
  String? _turnoversByScore(Map<String, dynamic> r) {
    final trA = ((r["tbs_tr_attacks"] as num?) ?? 0).toInt();
    final trT = ((r["tbs_tr_tos"] as num?) ?? 0).toInt();
    final reA = ((r["tbs_rest_attacks"] as num?) ?? 0).toInt();
    final reT = ((r["tbs_rest_tos"] as num?) ?? 0).toInt();
    if (trA < 5 || reA < 5) return null;
    final trPct = 100.0 * trT / trA;
    final rePct = 100.0 * reT / reA;
    if (trPct - rePct >= 10.0) {
      return "hátrányban kapkodnak (eladós támadás: "
          "${rePct.toStringAsFixed(0)}% → ${trPct.toStringAsFixed(0)}"
          "%) · az első ellépés után válts présre, ontják a labdát";
    }
    if (trPct - rePct <= -5.0) {
      return "hátrányban is rendezettek (${trPct.toStringAsFixed(0)}"
          "% eladós támadás) · a prés nem térül meg, fegyelmezett "
          "fal kell";
    }
    return null;
  }

  // Előny-védekezés: leül-e a fal vezetve (vödrönként 5+ kapott
  // lövés; +0,05 xG leülés, -0,02 feszes — a backend-kulccsal
  // azonos küszöbök).
  String? _defenseByScore(Map<String, dynamic> r) {
    final ls = ((r["dbs_lead_shots"] as num?) ?? 0).toInt();
    final lx = ((r["dbs_lead_xg"] as num?) ?? 0).toDouble();
    final rs = ((r["dbs_rest_shots"] as num?) ?? 0).toInt();
    final rx = ((r["dbs_rest_xg"] as num?) ?? 0).toDouble();
    if (ls < 5 || rs < 5) return null;
    final lead = lx / ls;
    final rest = rx / rs;
    if (lead - rest >= 0.05) {
      return "előnyben leül a faluk (kapott átlag-xG "
          "${rest.toStringAsFixed(2)} → ${lead.toStringAsFixed(2)} "
          "vezetve) · hátrányban sincs pánik: türelmes, bevitt "
          "támadásokkal visszajön a meccs";
    }
    if (lead - rest <= -0.02) {
      return "előnyben is feszes a faluk (kapott átlag-xG "
          "${lead.toStringAsFixed(2)} vezetve) · az elejét kell "
          "megnyerni, vezetve sem nyílik ki";
    }
    return null;
  }

  // Csere-állás: vezetve forgatnak-e (vödrönként 120+ mp és 4+
  // hullám; 1,5x ütem forgatás, 0,5x alatt befagyott sor — a
  // backend-kulccsal azonos küszöbök).
  String? _subsByScore(Map<String, dynamic> r) {
    final ls = ((r["sbs_lead_subs"] as num?) ?? 0).toInt();
    final rs = ((r["sbs_rest_subs"] as num?) ?? 0).toInt();
    final lSec = ((r["sbs_lead_s"] as num?) ?? 0).toDouble();
    final rSec = ((r["sbs_rest_s"] as num?) ?? 0).toDouble();
    if (lSec < 120.0 || rSec < 120.0 || ls + rs < 4) return null;
    final leadRate = ls / lSec;
    final restRate = rs / rSec;
    if (leadRate >= 1.5 * restRate && ls >= 3) {
      return "vezetve forgatnak ($ls cserehullám előnyben, $rs "
          "egyébként) · tartsd szorosan a meccset: addig nem mernek "
          "pihentetni, a kezdősoruk elfárad";
    }
    if (leadRate <= 0.5 * restRate && rs >= 3) {
      return "vezetve sem nyúlnak a sorhoz (csak $ls hullám "
          "előnyben) · a fáradó kulcsemberük végig fent van — a "
          "végén őt támadd";
    }
    return null;
  }

  // Indítás-állás: vezetve lassítják-e a kihozatalt (vödrönként 4+
  // indítás; +2 mp időhúzás, -1 mp pörgetés — a backend-kulccsal
  // azonos küszöbök).
  String? _outletPaceByScore(Map<String, dynamic> r) {
    final lo = ((r["ops_lead_outlets"] as num?) ?? 0).toInt();
    final ls = ((r["ops_lead_sum_s"] as num?) ?? 0).toDouble();
    final ro = ((r["ops_rest_outlets"] as num?) ?? 0).toInt();
    final rs = ((r["ops_rest_sum_s"] as num?) ?? 0).toDouble();
    if (lo < 4 || ro < 4) return null;
    final lead = ls / lo;
    final rest = rs / ro;
    if (lead - rest >= 2.0) {
      return "vezetve lassítják az indítást "
          "(${lead.toStringAsFixed(1)} mp kihozatal előnyben, "
          "${rest.toStringAsFixed(1)} egyébként) · hátrányban "
          "azonnali középkezdés, ne hagyd lassítani";
    }
    if (lead - rest <= -1.0) {
      return "előnyben is pörgetik az indítást "
          "(${lead.toStringAsFixed(1)} mp) · a védésük utáni "
          "pillanatban azonnali visszarendeződés kell";
    }
    return null;
  }

  // Átvert védők: ki mögött esnek a kapott gólok (4+ védőhöz
  // rendelt gól; 40%+ részarány, holtverseny nélkül — a
  // backend-kulccsal azonos küszöbök).
  String? _beatenDefenders(Map<String, dynamic> r) {
    final goals = ((r["btn_goals"] as num?) ?? 0).toInt();
    final defs = (r["btn_defenders"] as Map?) ?? {};
    if (goals < 4 || defs.isEmpty) return null;
    final entries = defs.entries.toList()
      ..sort((a, b) =>
          ((b.value as num?) ?? 0).compareTo((a.value as num?) ?? 0));
    final top = entries.first;
    final n = ((top.value as num?) ?? 0).toInt();
    final tie = entries.length > 1 &&
        ((entries[1].value as num?) ?? 0).toInt() == n;
    if (tie || 100.0 * n / goals < 40.0) return null;
    return "a kapott góljaiknál a(z) ${top.key} mezes védő veszíti "
        "a párharcot ($n/$goals) · rá vidd az 1v1-et, az ő oldala "
        "a nyitott ajtó";
  }

  // Zavartalan előkészítők: hagyják-e dolgozni a gólpassz-adót (5+
  // gólpasszos kapott gól; 60%+ laza, 25%- rálépős — a
  // backend-kulccsal azonos küszöbök).
  String? _unpressuredAssists(Map<String, dynamic> r) {
    final assisted = ((r["upa_assisted"] as num?) ?? 0).toInt();
    final loose = ((r["upa_unpressured"] as num?) ?? 0).toInt();
    if (assisted < 5) return null;
    final pct = 100.0 * loose / assisted;
    if (pct >= 60.0) {
      return "az előkészítőt hagyják dolgozni ($loose/$assisted "
          "kapott gólpassz zavartalan kiadásból) · a kidolgozott "
          "játékod szabadon futhat ellenük";
    }
    if (pct <= 25.0) {
      return "az előkészítőre rálépnek (csak $loose/$assisted "
          "zavartalan) · egy-ütemű, korai kiadások kellenek";
    }
    return null;
  }

  // Csere-büntetés: gólba kerülnek-e a csere-lyukak (2+ lyuk alatt
  // kapott gól — a backend-kulccsal azonos küszöb).
  String? _gapPunishment(Map<String, dynamic> r) {
    final conceded = ((r["gpn_conceded"] as num?) ?? 0).toInt();
    final gapS = ((r["gpn_gap_s"] as num?) ?? 0).toDouble();
    if (conceded < 2) return null;
    return "a csere-lyukaik gólba kerülnek ($conceded kapott gól "
        "${gapS.toStringAsFixed(0)} mp öt fős játék alatt) · a "
        "cseréjük pillanata bizonyítottan támadható: azonnali "
        "középkezdés";
  }

  // Folyosó-gólok: nyitott folyosón kapják-e a gólokat (5+ kapott
  // gól; 50%+ nyitott, 20%- zárt — a backend-kulccsal azonos
  // küszöbök).
  String? _corridorGoals(Map<String, dynamic> r) {
    final goals = ((r["crg_goals"] as num?) ?? 0).toInt();
    final open = ((r["crg_open"] as num?) ?? 0).toInt();
    if (goals < 5) return null;
    final pct = 100.0 * open / goals;
    if (pct >= 50.0) {
      return "nyitott folyosókon kapják a gólokat ($open/$goals "
          "előtt senki nem állt a lövésvonalban) · betörést és "
          "gyors átmenetet erőltess, a faluk nem ér oda";
    }
    if (pct <= 20.0) {
      return "zárt fal mögött is bekapják (csak $open/$goals nyitott "
          "folyosón) · a kapus-oldal a kérdés: kimozgatás és pontos "
          "elhelyezés kell";
    }
    return null;
  }

  // Bontó tempó: a járatás szedi-e szét a védekezésüket (5+ kapott
  // gól; 3+ passz-átlag járatásos, 1,5- egyéni — a backend-kulccsal
  // azonos küszöbök).
  String? _concededTempo(Map<String, dynamic> r) {
    final goals = ((r["ctm_goals"] as num?) ?? 0).toInt();
    final sum = ((r["ctm_passes_sum"] as num?) ?? 0).toInt();
    if (goals < 5) return null;
    final avg = sum / goals;
    if (avg >= 3.0) {
      return "a járatás szedi szét őket (átlag "
          "${avg.toStringAsFixed(1)} passz a kapott góljaik előtt) · "
          "tempót emelj: oldalváltásoknál nyílik a faluk";
    }
    if (avg <= 1.5) {
      return "egyéni akciókból kapják a gólokat (átlag "
          "${avg.toStringAsFixed(1)} passz) · az 1v1-ben erős "
          "embereidet engedd rájuk";
    }
    return null;
  }

  // Lendület-gólok: mozgásból érkező lövőktől kapják-e a gólokat
  // (5+ mért kapott gól; 55%+ mozgásos, 25%- álló — a
  // backend-kulccsal azonos küszöbök).
  String? _concededMomentum(Map<String, dynamic> r) {
    final goals = ((r["cgm_goals"] as num?) ?? 0).toInt();
    final running = ((r["cgm_running"] as num?) ?? 0).toInt();
    if (goals < 5) return null;
    final pct = 100.0 * running / goals;
    if (pct >= 55.0) {
      return "mozgásból kapják a gólokat ($running/$goals lendületes "
          "lövőtől) · a bekísérésük késik: a betörőt és a befutót "
          "játszd";
    }
    if (pct <= 25.0) {
      return "állóhelyből is bekapják (csak $running/$goals "
          "mozgásból) · tiszta lövést engednek: a kivárt átlövés is "
          "termel";
    }
    return null;
  }

  // Becsapott kapus: elmozdítják-e a kapust a gólok előtt (5+ mért
  // kapott gól; 40%+ becsapott, 10%- állja — a backend-kulccsal
  // azonos küszöbök).
  String? _wrongfootedKeeper(Map<String, dynamic> r) {
    final goals = ((r["wfk_goals"] as num?) ?? 0).toInt();
    final fooled = ((r["wfk_fooled"] as num?) ?? 0).toInt();
    if (goals < 5) return null;
    final pct = 100.0 * fooled / goals;
    if (pct >= 40.0) {
      return "elmozdítható a kapusuk ($fooled/$goals kapott gólnál "
          "ellenirányba mozdult) · kötelező lövőcsel: a kapus "
          "elindul, a labda a másik oldalé";
    }
    if (pct <= 10.0) {
      return "a kapusuk állja a cseleket (csak $fooled/$goals "
          "rosszul mozdulás) · első ütemből, pontosan a sarokba "
          "kell lőni";
    }
    return null;
  }

  // Olvasó kapus: előre olvassa-e a lövéseket (5+ mért védés; 50%+
  // olvasó, 15%- reflex — a backend-kulccsal azonos küszöbök).
  String? _readingKeeper(Map<String, dynamic> r) {
    final saves = ((r["rdk_saves"] as num?) ?? 0).toInt();
    final read = ((r["rdk_read"] as num?) ?? 0).toInt();
    if (saves < 5) return null;
    final pct = 100.0 * read / saves;
    if (pct >= 50.0) {
      return "olvassa a lövéseket ($read/$saves védésnél indult "
          "előre) · ütem-váltással és csellel büntesd a korai "
          "elköteleződését";
    }
    if (pct <= 15.0) {
      return "reflexből véd (csak $read/$saves olvasott védés) · "
          "kitartott, pontos sarok-lövés visz be";
    }
    return null;
  }

  // Kettőzés-büntetés: mögé betalálnak-e a kettőzésnek (2+ gól
  // közvetlenül kettőzés után — a backend-kulccsal azonos küszöb).
  String? _doublePunishment(Map<String, dynamic> r) {
    final conceded = ((r["dbp_conceded_after"] as num?) ?? 0).toInt();
    if (conceded < 2) return null;
    return "a kettőzésük gólba kerül ($conceded gól közvetlenül "
        "kettőzés után) · a kettőzés-jelre azonnali passz a "
        "felszabadult emberhez — bizonyítottan gólt ér";
  }

  // Kilépés-büntetés: a kilépés mögé betalálnak-e (5+ mért kapott
  // gól; 40%+ kiugró-arány — a backend-kulccsal azonos küszöbök).
  String? _stepoutPunishment(Map<String, dynamic> r) {
    final goals = ((r["sop_goals"] as num?) ?? 0).toInt();
    final behind = ((r["sop_behind"] as num?) ?? 0).toInt();
    if (goals < 5) return null;
    if (100.0 * behind / goals < 40.0) return null;
    return "a kilépésük mögé betalálnak ($behind/$goals kapott "
        "gólnál volt kiugró védő) · a kilépőt játszd meg: átemelés "
        "vagy betörés a helyére";
  }

  // Kihagyás-büntetés: megbüntetik-e a kihagyott ziccereiket (4+
  // kihagyás; 40%+ büntetett, 10%- emésztő — a backend-kulccsal
  // azonos küszöbök).
  String? _punishedMisses(Map<String, dynamic> r) {
    final misses = ((r["pmb_misses"] as num?) ?? 0).toInt();
    final punished = ((r["pmb_punished"] as num?) ?? 0).toInt();
    if (misses < 4) return null;
    final pct = 100.0 * punished / misses;
    if (pct >= 40.0) {
      return "a kihagyásaik után azonnal büntethetők ($punished/"
          "$misses ziccer-kimaradást követett gyors gól) · a "
          "kihagyásuk a te jeled: azonnali tempó, kapura vitt "
          "támadás";
    }
    if (pct <= 10.0) {
      return "jól emésztik a kihagyást (csak $punished/$misses után "
          "jött gyors gól) · nincs ingyen lendület, vidd a "
          "megszokott játékot";
    }
    return null;
  }

  // Indítás-hiba ára: gólba kerülnek-e az elszórt indítások (2+
  // büntetett hiba — a backend-kulccsal azonos küszöb).
  String? _outletPunishment(Map<String, dynamic> r) {
    final punished = ((r["olp_punished"] as num?) ?? 0).toInt();
    final lost = ((r["olp_lost"] as num?) ?? 0).toInt();
    if (punished < 2) return null;
    return "az elszórt indításaik gólba kerülnek ($punished/$lost "
        "elveszett kihozatal után gyors gól) · magas letámadással "
        "vadászd a kapus-indításaikat";
  }

  // Poszt-kapuoldal: melyik posztjuk melyik sarkot keresi (6+ gól,
  // posztonként 4+, 60% részarány — a backenddel azonos küszöbök:
  // RGP_MIN_GOALS, RGP_SHARE_PCT).
  String? _goalPlacementRole(Map<String, dynamic> r) {
    final raw =
        (r["rgp_goals_by_role_side"] as Map?)?.cast<String, dynamic>();
    if (raw == null || raw.isEmpty) return null;
    var total = 0;
    final byPost = <String, Map<String, int>>{};
    raw.forEach((k, v) {
      final n = (v as num).toInt();
      final i = k.indexOf("|");
      if (i <= 0) return;
      byPost.putIfAbsent(k.substring(0, i), () => {})[k.substring(i + 1)] = n;
      total += n;
    });
    if (total < 6) return null;
    String? best, bestSide;
    var bestPct = 0.0;
    var bestGoals = 0;
    byPost.forEach((post, sides) {
      final sum = sides.values.fold(0, (a, b) => a + b);
      if (sum < 4) return;
      final dom = sides.keys.reduce((a, b) => sides[a]! >= sides[b]! ? a : b);
      final pct = 100.0 * sides[dom]! / sum;
      if (pct >= 60.0 && pct > bestPct) {
        best = post;
        bestSide = dom;
        bestPct = pct;
        bestGoals = sum;
      }
    });
    if (best == null) return null;
    return "a(z) $best posztjuk a góljai ${bestPct.round()}%-át $bestSide "
        "oldalra lövi ($bestGoals gól) · a kapus arra állhat rá, a fal a "
        "másikat zárja";
  }

  // Lepattanó-poszt: ki viszi a második rohamot (3+ poszthoz kötött
  // második lövés, 60% részarány — a backenddel azonos küszöbök:
  // SCR_MIN_SHOTS, SCR_SHARE_PCT).
  String? _reboundRole(Map<String, dynamic> r) {
    final byRole =
        (r["scr_shots_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a második rohamukat a(z) $top viszi (${pct.round()}%, "
        "$total második lövés) · a zárás után őt kell kivenni a "
        "lepattanóból";
  }

  // Hajrá-poszt: melyik posztjuk viszi a végjátékot (3+ hajrá-gól,
  // 60% részarány — a backenddel azonos küszöbök: CSR_MIN_GOALS,
  // CSR_SHARE_PCT).
  String? _clutchRole(Map<String, dynamic> r) {
    final byRole =
        (r["csr_goals_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a végjátékuk a(z) $top posztra fut ki (${pct.round()}%, "
        "$total hajrá-gól) · az utolsó öt percben őt kell fogni";
  }

  // Ziccer-előkészítő poszt: ki adja a passzt a nagy helyzethez (3+
  // előkészítés, 60% részarány — a backenddel azonos küszöbök:
  // BCF_FEED_MIN, BCF_FEED_SHARE_PCT).
  String? _bigChanceFeederRole(Map<String, dynamic> r) {
    final byRole =
        (r["bcf_chances_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a ziccereik ${pct.round()}%-át a(z) $top posztjuk "
        "teremti ($total előkészítés) · az ő bejátszó-sávját "
        "vágjátok el, a helyzet ki sem alakul";
  }

  // Kulcs-ember: hány EMBER-réteg ítélete mutat ugyanarra a
  // játékosra (4 egyező rétegtől — a backenddel azonos küszöb:
  // KPL_MIN_LAYERS).
  String? _keyPlayer(Map<String, dynamic> r) {
    final byPlayer = (r["kpl_layers_by_player"] as Map?)
        ?.cast<String, dynamic>();
    if (byPlayer == null || byPlayer.isEmpty) return null;
    String? top;
    var topN = 0;
    byPlayer.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null || topN < 4) return null;
    return "a kulcs-emberük a(z) $top. számú: $topN ember-réteg "
        "ítélete mutat rá · emberfogás, kettőzés vagy a labdaútja "
        "elvágása önmagában meccstervnyi feladat";
  }

  // Kétperc ára: mennyi gólba kerül egy kiállításuk (3+ ablak; 1,2
  // gól/kiállítás fölött drága, 0,5 alatt olcsó — a backenddel
  // azonos küszöbök: SCT_MIN_WINDOWS, SCT_COSTLY, SCT_CHEAP).
  String? _suspensionCost(Map<String, dynamic> r) {
    final windows = (r["sct_windows"] as num?)?.toInt() ?? 0;
    final conceded = (r["sct_conceded"] as num?)?.toInt() ?? 0;
    if (windows < 3) return null;
    final per = conceded / windows;
    if (per >= 1.2) {
      return "egy kiállításuk átlag ${per.toStringAsFixed(1)} gólba "
          "kerül ($conceded gól $windows kétperc alatt) · a "
          "kiharcolás náluk pont-termelés";
    }
    if (per <= 0.5) {
      return "egy kiállításuk csak ${per.toStringAsFixed(1)} gólba "
          "kerül ($conceded gól $windows kétperc alatt) · ne a "
          "kiállításra játsszatok";
    }
    return null;
  }

  // Emberfogás-váltás: a szünet után emberfogásra váltanak-e (2 m
  // alatt emberfogás, 0,7-es arány a váltás — a backenddel azonos
  // küszöbök: MSH_TIGHT_M, MSH_DROP_RATIO).
  String? _markingShift(Map<String, dynamic> r) {
    final fh = (r["msh_fh_dist_m"] as num?)?.toDouble() ?? 0.0;
    final sh = (r["msh_sh_dist_m"] as num?)?.toDouble() ?? 0.0;
    if (fh <= 0.0 || sh <= 0.0) return null;
    if (sh <= 2.0 && sh <= 0.7 * fh) {
      return "a szünet után emberfogásra váltanak (a legszorosabb "
          "páros ${sh.toStringAsFixed(1)} m az első félidei "
          "${fh.toStringAsFixed(1)} m helyett) · a fogott emberetek "
          "húzza el a védőjét";
    }
    if (fh <= 2.0 && fh <= 0.7 * sh) {
      return "a szünet után elengedik az emberfogást (a legszorosabb "
          "páros ${sh.toStringAsFixed(1)} m az első félidei "
          "${fh.toStringAsFixed(1)} m helyett) · a fogott emberetek "
          "visszakapja a labdát";
    }
    return null;
  }

  // Kipattanó-szedők: ki szedi össze a kipattanót védés után (2+
  // kipattanó ugyanattól a védőtől — a backenddel azonos küszöb:
  // RBCP_MIN_REBOUNDS).
  String? _reboundCollector(Map<String, dynamic> r) {
    final byPlayer = (r["rbcp_rebounds_by_player"] as Map?)
        ?.cast<String, dynamic>();
    if (byPlayer == null || byPlayer.isEmpty) return null;
    String? top;
    var topN = 0;
    byPlayer.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null || topN < 2) return null;
    return "a kipattanókat leggyakrabban a(z) $top. szedi össze "
        "($topN kipattanó) · a második helyzetnél őt kell blokkolni";
  }

  // Kétperc-páros: ki harcolja ki és ki fejezi be a kétpercüket (3+
  // lánc, 55% részarány — a backenddel azonos küszöbök:
  // SUP_MIN_PAIRS, SUP_SHARE_PCT).
  String? _suspensionChain(Map<String, dynamic> r) {
    final byPair =
        (r["sup_chains_by_pair"] as Map?)?.cast<String, dynamic>();
    if (byPair == null || byPair.isEmpty) return null;
    var total = 0;
    byPair.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byPair.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 55.0) return null;
    return "a kétperceik ${pct.round()}%-a ugyanazt a láncot futja "
        "($top, $total emberelőny-lövés) · a kiharcoló ellen "
        "testtel, a befejező ellen emberfogással";
  }

  // Hetes-kihagyók: ki hibázza el a hetest (2+ gól nélküli hetes
  // ugyanattól a dobótól — a backenddel azonos küszöb:
  // SVMP_MIN_MISSES).
  String? _sevenMissPlayer(Map<String, dynamic> r) {
    final byPlayer =
        (r["svmp_misses_by_player"] as Map?)?.cast<String, dynamic>();
    if (byPlayer == null || byPlayer.isEmpty) return null;
    String? top;
    var topN = 0;
    byPlayer.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null || topN < 2) return null;
    return "a heteseiket leggyakrabban a(z) $top. hagyja ki ($topN "
        "gól nélküli hetes) · ha ő áll oda, a kapusotok mehet a "
        "saját megérzésére";
  }

  // Sprint-esés: megfogy-e a láb a második félidőre (félidőnként 5+
  // játékperc, 8+ sprint, 0,7 arány alatt esés / 1,43 fölött
  // kapcsolás — a backenddel azonos küszöbök: SFD_MIN_HALF_MIN,
  // SFD_MIN_SPRINTS, SFD_DROP_RATIO).
  String? _sprintFade(Map<String, dynamic> r) {
    final fhS = (r["sfd_fh_sprints"] as num?)?.toInt() ?? 0;
    final shS = (r["sfd_sh_sprints"] as num?)?.toInt() ?? 0;
    final fhM = (r["sfd_fh_min"] as num?)?.toDouble() ?? 0.0;
    final shM = (r["sfd_sh_min"] as num?)?.toDouble() ?? 0.0;
    if (fhM < 5.0 || shM < 5.0 || fhS + shS < 8 || fhS == 0) {
      return null;
    }
    final f = fhS / fhM;
    final s = shS / shM;
    if (f <= 0) return null;
    final ratio = s / f;
    if (ratio <= 0.7) {
      return "a második félidőre megfogy a lábuk "
          "(${s.toStringAsFixed(1)} sprint/perc az "
          "${f.toStringAsFixed(1)} helyett) · a szünet után "
          "emeljetek tempót";
    }
    if (ratio >= 1.43) {
      return "a második félidőre kapcsolnak (${s.toStringAsFixed(1)} "
          "sprint/perc az ${f.toStringAsFixed(1)} helyett) · "
          "tartsátok a saját ritmusotokat";
    }
    return null;
  }

  // Óralopás: vezetve elhúzzák-e a támadást a hajrában (3+
  // hajrá-támadás vezetésben, 4+ alap-támadás, 3 mp eltérés — a
  // backenddel azonos küszöbök: CLK_MIN_ATTACKS, CLK_MIN_BASE,
  // CLK_DIFF_S).
  String? _clockManagement(Map<String, dynamic> r) {
    final lead = (r["clk_lead"] as num?)?.toInt() ?? 0;
    final base = (r["clk_base"] as num?)?.toInt() ?? 0;
    final leadSum = (r["clk_lead_sum_s"] as num?)?.toDouble() ?? 0.0;
    final baseSum = (r["clk_base_sum_s"] as num?)?.toDouble() ?? 0.0;
    if (lead < 3 || base < 4) return null;
    final l = leadSum / lead;
    final b = baseSum / base;
    final d = l - b;
    if (d.abs() < 3.0) return null;
    if (d > 0) {
      return "vezetve ${d.toStringAsFixed(1)} mp-cel hosszabb a "
          "támadásuk a hajrában (${l.toStringAsFixed(1)} mp a "
          "${b.toStringAsFixed(1)} mp helyett) · lopják az órát, "
          "játsszatok a passzív jelre";
    }
    return "vezetve ${d.abs().toStringAsFixed(1)} mp-cel rövidebb a "
        "támadásuk a hajrában (${l.toStringAsFixed(1)} mp a "
        "${b.toStringAsFixed(1)} mp helyett) · sietnek, elég zárt "
        "fallal kivárni";
  }

  // Kipattanó ára: a védéseik után kapott második-helyzet gólok (5+
  // védés, 15% fölött drága — a backenddel azonos küszöbök:
  // RPN_MIN_SAVES, RPN_COSTLY_PCT).
  String? _reboundPunishment(Map<String, dynamic> r) {
    final saves = (r["rpn_saves"] as num?)?.toInt() ?? 0;
    final punished = (r["rpn_punished"] as num?)?.toInt() ?? 0;
    if (saves < 5) return null;
    final pct = 100.0 * punished / saves;
    if (pct < 15.0) return null;
    return "a védéseik ${pct.round()}%-a után gól jön a kipattanóból "
        "($punished a $saves védésből) · minden lövésnél induljon a "
        "berobbanó ember";
  }

  // Visszaállás ára: a gól nélküli lövésük után kapott gyors gólok
  // (6+ lövés, 20% fölött drága — a backenddel azonos küszöbök:
  // RTP_MIN_SHOTS, RTP_COSTLY_PCT).
  String? _retreatPunishment(Map<String, dynamic> r) {
    final shots = (r["rtp_shots"] as num?)?.toInt() ?? 0;
    final punished = (r["rtp_punished"] as num?)?.toInt() ?? 0;
    if (shots < 6) return null;
    final pct = 100.0 * punished / shots;
    if (pct < 20.0) return null;
    return "a gól nélküli lövéseik ${pct.round()}%-át gyors kapott "
        "gól követi ($punished a $shots lövésből) · minden "
        "védésetekből azonnal indítsatok";
  }

  // Lepattanó-szedő poszt: védés után kinél marad a labda (3+
  // megszerzett kipattanó, 60% részarány — a backenddel azonos
  // küszöbök: RBC_MIN_REBOUNDS, RBC_SHARE_PCT).
  String? _defensiveReboundRole(Map<String, dynamic> r) {
    final byRole =
        (r["rbc_rebounds_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a kipattanók ${pct.round()}%-át a(z) $top posztjuk szedi "
        "össze ($total kipattanó) · oda küldjétek a berobbanó embert";
  }

  // Figura-koncentráció: egy figurára épül-e a támadójátékuk (6+
  // mért támadás; 40% fölött egy mintára készülni éri meg, 25%
  // alatt elvekre kell — a backenddel azonos küszöbök:
  // SPK_MIN_ATTACKS, SPK_TOP_PCT, SPK_VARIED_PCT).
  String? _setplayConcentration(Map<String, dynamic> r) {
    final attacks = (r["spk_attacks"] as num?)?.toInt() ?? 0;
    final top = (r["spk_top"] as num?)?.toInt() ?? 0;
    final figures = (r["spk_figures"] as num?)?.toInt() ?? 0;
    if (attacks < 6) return null;
    final pct = 100.0 * top / attacks;
    if (pct >= 40.0) {
      return "a támadásaik ${pct.round()}%-a egyetlen mintából jön "
          "($attacks mért támadás, $figures figura) · konkrét "
          "figurára készüljetek";
    }
    if (pct <= 25.0) {
      return "a támadásaik sokfelé oszlanak (a legnagyobb minta is "
          "csak ${pct.round()}%, $figures figura) · elvekre "
          "készüljetek, ne figurákra";
    }
    return null;
  }

  // Hajrá-kapus: nő vagy beesik a kapusuk az utolsó öt percben (3+
  // kaputra érkezett lövés mindkét szakaszban, 15 százalékpont
  // eltérés — a backenddel azonos küszöbök: GKC_MIN_FACED,
  // GKC_GAP_PP).
  String? _clutchKeeper(Map<String, dynamic> r) {
    final cf = (r["gkc_clutch_faced"] as num?)?.toInt() ?? 0;
    final cs = (r["gkc_clutch_saves"] as num?)?.toInt() ?? 0;
    final rf = (r["gkc_rest_faced"] as num?)?.toInt() ?? 0;
    final rs = (r["gkc_rest_saves"] as num?)?.toInt() ?? 0;
    if (cf < 3 || rf < 3) return null;
    final c = 100.0 * cs / cf;
    final b = 100.0 * rs / rf;
    final d = c - b;
    if (d.abs() < 15.0) return null;
    if (d > 0) {
      return "a kapusuk a hajrában nő (${c.round()}% a ${b.round()}% "
          "helyett, $cf lövésből) · a végén csak tiszta helyzetből "
          "lőjetek";
    }
    return "a kapusuk a hajrában beesik (${c.round()}% a "
        "${b.round()}% helyett, $cf lövésből) · a végén vigyétek fel "
        "a lövésszámot";
  }

  // Emberhátrány-hiba poszt: öt emberrel kinek a kezén vész el a
  // labdájuk (3+ hátrány-eladás, 60% részarány — a backenddel
  // azonos küszöbök: SHT_MIN_TURNOVERS, SHT_SHARE_PCT).
  String? _shorthandedTurnoverRole(Map<String, dynamic> r) {
    final byRole =
        (r["sht_turnovers_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "hátrányban ${pct.round()}%-ban a(z) $top kezén vész el a "
        "labdájuk ($total hátrány-eladás) · a hat az öt ellen az ő "
        "fogadására menjetek";
  }

  // Kapkodás-index: kapott gól után rövidül vagy nyúlik a támadásuk
  // (3+ válasz-támadás, 4+ alap-támadás, 3 mp eltérés — a
  // backenddel azonos küszöbök: RUS_MIN_ATTACKS, RUS_MIN_BASE,
  // RUS_DIFF_S).
  String? _postGoalRush(Map<String, dynamic> r) {
    final after = (r["rus_after"] as num?)?.toInt() ?? 0;
    final base = (r["rus_base"] as num?)?.toInt() ?? 0;
    final afterSum = (r["rus_after_sum_s"] as num?)?.toDouble() ?? 0.0;
    final baseSum = (r["rus_base_sum_s"] as num?)?.toDouble() ?? 0.0;
    if (after < 3 || base < 4) return null;
    final a = afterSum / after;
    final b = baseSum / base;
    final d = a - b;
    if (d.abs() < 3.0) return null;
    if (d < 0) {
      return "kapott gól után ${d.abs().toStringAsFixed(1)} mp-cel "
          "rövidebb a támadásuk (${a.toStringAsFixed(1)} mp a "
          "${b.toStringAsFixed(1)} mp helyett) · kapkodnak, a "
          "gólotok után álljatok vissza";
    }
    return "kapott gól után ${d.toStringAsFixed(1)} mp-cel hosszabb "
        "a támadásuk (${a.toStringAsFixed(1)} mp a "
        "${b.toStringAsFixed(1)} mp helyett) · befagynak, toljátok "
        "előre a védekezést";
  }

  // Visszaállás-idő: hány másodperc alatt áll össze a faluk a
  // lövésük után (4+ mért lövés, 8 mp fölött szólal meg — a
  // backenddel azonos küszöbök: RTT_MIN_SHOTS, RTT_SLOW_S).
  String? _retreatTime(Map<String, dynamic> r) {
    final shots = (r["rtt_shots"] as num?)?.toInt() ?? 0;
    final sum = (r["rtt_sum_s"] as num?)?.toDouble() ?? 0.0;
    final slow = (r["rtt_slow"] as num?)?.toInt() ?? 0;
    if (shots < 4) return null;
    final avg = sum / shots;
    if (avg <= 8.0) return null;
    return "a lövésük után átlag ${avg.toStringAsFixed(1)} mp, míg "
        "négy emberük hazaér ($shots lövésből $slow volt 8 mp "
        "fölött) · a kapusotok azonnal indítson";
  }

  // Időkérés-hiba poszt: a megbeszélt figura kinek a kezén hal el
  // (3+ időkérés utáni eladás, 60% részarány — a backenddel azonos
  // küszöbök: TOE_MIN_TURNOVERS, TOE_SHARE_PCT).
  String? _timeoutTurnoverRole(Map<String, dynamic> r) {
    final byRole =
        (r["toe_turnovers_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "az időkérés utáni labdájuk ${pct.round()}%-ban a(z) $top "
        "kezén vész el ($total eladás) · a figurát az ő indításánál "
        "nyomjátok meg";
  }

  // Válaszhiba-poszt: kapott gól után kinél vész el a labdájuk (3+
  // válasz-eladás, 60% részarány — a backenddel azonos küszöbök:
  // RTO_MIN_TURNOVERS, RTO_SHARE_PCT).
  String? _responseTurnoverRole(Map<String, dynamic> r) {
    final byRole =
        (r["rto_turnovers_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "kapott gól után ${pct.round()}%-ban a(z) $top kezén vész "
        "el a labdájuk ($total válasz-eladás) · a gólotok után "
        "azonnal az ő fogadására menjetek";
  }

  // Emberelőny-hiba poszt: kinek a kezén akad el az emberelőnyük (3+
  // emberelőny-eladás, 60% részarány — a backenddel azonos küszöbök:
  // PPT_MIN_TURNOVERS, PPT_SHARE_PCT).
  String? _powerplayTurnoverRole(Map<String, dynamic> r) {
    final byRole =
        (r["ppt_turnovers_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "az emberelőnyük ${pct.round()}%-ban a(z) $top kezén akad "
        "el ($total emberelőny-eladás) · hátrányban rá nyomjatok, az "
        "elvett labdából kontrázni lehet";
  }

  // Ziccerpáros-poszt: ki adja és ki fejezi be a nagy helyzeteiket
  // (3+ ziccer-páros, 55% részarány — a backenddel azonos küszöbök:
  // BCP_PAIR_MIN, BCP_PAIR_SHARE_PCT).
  String? _bigChancePair(Map<String, dynamic> r) {
    final byPair =
        (r["bcp_chances_by_pair"] as Map?)?.cast<String, dynamic>();
    if (byPair == null || byPair.isEmpty) return null;
    var total = 0;
    byPair.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byPair.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 55.0) return null;
    return "a ziccereik ${pct.round()}%-a ugyanabból a párosból jön "
        "($top, $total helyzet) · a köztük lévő passzsávot vágjátok "
        "el, ne külön-külön fogjátok őket";
  }

  // Hetes-kihagyó poszt: melyik posztjuk hibázza el a hetest (3+ gól
  // nélküli hetes, 60% részarány — a backenddel azonos küszöbök:
  // SVM_MIN_MISSES, SVM_SHARE_PCT).
  String? _sevenMissRole(Map<String, dynamic> r) {
    final byRole =
        (r["svm_misses_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a kihagyott heteseik ${pct.round()}%-a a(z) $top "
        "posztjukhoz kötődik ($total gól nélküli hetes) · ha ő áll "
        "oda, a kapus mehet a saját megérzésére";
  }

  // Vég-birtokos poszt: kinél ér véget a támadásuk lövés nélkül (4+
  // terméketlen támadás, 60% részarány — a backenddel azonos
  // küszöbök: LST_MIN_ATTACKS, LST_SHARE_PCT).
  String? _lastHolderRole(Map<String, dynamic> r) {
    final byRole =
        (r["lst_attacks_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 4) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a lövés nélkül záruló támadásaik ${pct.round()}%-a a(z) "
        "$top poszt kezében hal el ($total terméketlen támadás) · a "
        "támadás második felében rá toljátok a nyomást";
  }

  // Menekülő-poszt: nyomás alatt kihez megy a labda (5+ nyomás
  // alatti passz, 60% részarány — a backenddel azonos küszöbök:
  // ESC_MIN_PASSES, ESC_SHARE_PCT).
  String? _pressOutletRole(Map<String, dynamic> r) {
    final byRole =
        (r["esc_passes_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 5) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "szorításban a labda a(z) $top poszthoz menekül "
        "(${pct.round()}%, $total nyomás alatti passz) · a harmadik "
        "ember ott álljon lesben";
  }

  // Időkéréspáros-poszt: az időkérés utáni figura tengelye (3+
  // időkérés utáni lövés, 60% részarány — a backenddel azonos
  // küszöbök: TOP_MIN_SHOTS, TOP_SHARE_PCT).
  String? _timeoutPairRole(Map<String, dynamic> r) {
    final byRole =
        (r["top_shots_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "az időkérés utáni figurájuk a(z) $top tengelyen fut "
        "(${pct.round()}%, $total lövés) · az ELSŐ passzt vágjátok "
        "el, ott törik meg a legolcsóbban";
  }

  // Sávváltó-poszt: melyik posztjuk vált sávot a támadásban (5+
  // sávváltás, 60% részarány — a backenddel azonos küszöbök:
  // LSW_MIN_SWITCHES, LSW_SHARE_PCT).
  String? _laneSwitchRole(Map<String, dynamic> r) {
    final byRole =
        (r["lsw_switches_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 5) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a keresztmozgásuk a(z) $top posztra épül "
        "(${pct.round()}%, $total sávváltás) · előre döntsétek el: a"
        " védője követi vagy átadja";
  }

  // Elöl lógó poszt: melyik posztjuk nem ér haza védekezni (200+
  // védekezett kocka, 70% alatti hazaérés — a backenddel azonos
  // küszöbök: RCR_MIN_FRAMES, RCR_LOW_PCT).
  String? _recoveryRole(Map<String, dynamic> r) {
    final fr =
        (r["rcr_frames_by_role"] as Map?)?.cast<String, dynamic>();
    final hm =
        (r["rcr_home_by_role"] as Map?)?.cast<String, dynamic>();
    if (fr == null || fr.isEmpty) return null;
    String? post;
    var postPct = 100.0;
    fr.forEach((k, v) {
      final n = (v as num).toInt();
      if (n < 200) return;
      final h = ((hm?[k] as num?) ?? 0).toInt();
      final pct = 100.0 * h / n;
      if (pct < 70.0 && pct < postPct) {
        post = k;
        postPct = pct;
      }
    });
    if (post == null) return null;
    return "a(z) $post posztjuk elöl lóg (a védekezett idő "
        "${postPct.round()}%-ában van otthon) · a gyors indítást az "
        "ő oldalára vezessétek";
  }

  // Válasz-poszt: kapott gól után melyik posztjuk válaszol (3+
  // válasz-gól, 60% részarány — a backenddel azonos küszöbök:
  // RSP_MIN_GOALS, RSP_SHARE_PCT).
  String? _responseScorerRole(Map<String, dynamic> r) {
    final byRole =
        (r["rsp_goals_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "kapott gól után a(z) $top posztjuk válaszol "
        "(${pct.round()}%, $total válasz-gól) · a saját gólotok után"
        " azonnal az ő fogására váltsatok";
  }

  // Emberelőnypáros-poszt: melyik tengelyen fut a 6-5 játékuk (3+
  // emberelőny-lövés, 60% részarány — a backenddel azonos küszöbök:
  // PWP_MIN_SHOTS, PWP_SHARE_PCT).
  String? _powerplayPairRole(Map<String, dynamic> r) {
    final byRole =
        (r["pwp_shots_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a 6-5 játékuk a(z) $top tengelyen fut (${pct.round()}%, "
        "$total emberelőny-lövés) · öt emberrel ezt a tengelyt kell "
        "elvágni";
  }

  // Specialista-poszt: melyik posztot játsszák váltott sorban (120+
  // mp mért jelenlét posztonként, mindkét fázisban 60+ mp, 80%
  // egyoldalúság — a backenddel azonos küszöbök: SPC_MIN_S,
  // SPC_MIN_PHASE_S, SPC_SPEC_PCT).
  String? _specialistRole(Map<String, dynamic> r) {
    final fr =
        (r["spc_seconds_by_role"] as Map?)?.cast<String, dynamic>();
    final df = (r["spc_def_seconds_by_role"] as Map?)
        ?.cast<String, dynamic>();
    if (fr == null || fr.isEmpty) return null;
    var total = 0.0;
    var defTotal = 0.0;
    fr.forEach((k, v) => total += (v as num).toDouble());
    df?.forEach((k, v) => defTotal += (v as num).toDouble());
    // Mindkét fázis legyen meg: egy fél-támadásnyi felvétel is
    // 100%-ot mutatna.
    if (defTotal < 60.0 || total - defTotal < 60.0) return null;
    String? post;
    var postN = 0.0;
    var postPct = 0.0;
    fr.forEach((k, v) {
      final n = (v as num).toDouble();
      if (n < 120.0) return;
      final d = ((df?[k] as num?) ?? 0).toDouble();
      final pct = 100.0 * d / n;
      if ((pct >= 80.0 || pct <= 20.0) && n > postN) {
        post = k;
        postN = n;
        postPct = pct;
      }
    });
    if (post == null) return null;
    final egyold = postPct >= 80.0 ? postPct : 100.0 - postPct;
    final irany = postPct >= 80.0 ? "védekezésben" : "támadásban";
    return "a(z) $post posztjukat váltott sorban játsszák (idejük "
        "${egyold.round()}%-a $irany) · a csere-pillanatuk gyors "
        "középkezdéssel támadható";
  }

  // Kulcs-páros: hány páros-réteg mutat ugyanarra a kettősre (2+
  // egyező réteg, holtverseny nélkül — a backenddel azonos küszöb:
  // KPR_MIN_LAYERS).
  String? _keyPair(Map<String, dynamic> r) {
    final byPair =
        (r["kpr_layers_by_role"] as Map?)?.cast<String, dynamic>();
    if (byPair == null || byPair.isEmpty) return null;
    String? top;
    var topN = 0;
    var secondN = 0;
    byPair.forEach((k, v) {
      final n = (v as num).toInt();
      if (n > topN) {
        secondN = topN;
        top = k;
        topN = n;
      } else if (n > secondN) {
        secondN = n;
      }
    });
    if (top == null || topN < 2 || topN == secondN) return null;
    return "a kulcs-párosuk a(z) $top: $topN páros-réteg mutat rá · "
        "a kettejük közti sávot kell szétvágni";
  }

  // Lepattanópáros-poszt: melyik lövésükre ki érkezik (3+ második
  // roham, 60% részarány — a backenddel azonos küszöbök:
  // RBP_MIN_SHOTS, RBP_SHARE_PCT).
  String? _reboundPairRole(Map<String, dynamic> r) {
    final byRole =
        (r["rbp_shots_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a lepattanó-játékuk a(z) $top párra jár "
        "(${pct.round()}%, $total második roham) · a lövés zárása "
        "után az érkező útját kell elállni";
  }

  // Kettőzőpáros-poszt: melyik védő-kettősük kettőz együtt (100+
  // kettőzött kocka, 60% részarány — a backenddel azonos küszöbök:
  // DPP_MIN_FRAMES, DPP_SHARE_PCT).
  String? _doublingPairRole(Map<String, dynamic> r) {
    final byRole =
        (r["dpp_frames_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 100) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a kettőzésük a(z) $top védő-pároson áll "
        "(${pct.round()}% a kettőzött időből) · a kioldó passz "
        "célpontja fix, gyakoroljátok be";
  }

  // Gólpasszpáros-poszt: melyik tengelyen születnek a góljaik (3+
  // asszisztos gól, 60% részarány — a backenddel azonos küszöbök:
  // APR_MIN_GOALS, APR_SHARE_PCT).
  String? _assistPairRole(Map<String, dynamic> r) {
    final byRole =
        (r["apr_goals_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a góljaik a(z) $top tengelyen születnek "
        "(${pct.round()}%, $total asszisztos gól) · a kettős közti "
        "passzsáv a fő zárnivaló";
  }

  // Kontrapáros-poszt: melyik tengelyen futnak a kontráik (3+
  // lerohanás, 60% részarány — a backenddel azonos küszöbök:
  // FBP_MIN_BREAKS, FBP_SHARE_PCT).
  String? _fastBreakPairRole(Map<String, dynamic> r) {
    final byRole =
        (r["fbp_breaks_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a kontráik a(z) $top tengelyen futnak (${pct.round()}%,"
        " $total lerohanás) · az indítóra azonnali nyomás, a "
        "befejező sávját az első visszaérő zárja";
  }

  // Hetespáros-poszt: ki harcolja ki és ki dobja a hetest (3+
  // hetes, 60% részarány — a backenddel azonos küszöbök:
  // SVP_MIN_SEVENS, SVP_SHARE_PCT).
  String? _sevenPairRole(Map<String, dynamic> r) {
    final byRole =
        (r["svp_sevens_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a hetes-játékuk a(z) $top posztpárra jár "
        "(${pct.round()}%, $total hetes) · a kiharcoló ellen kéz "
        "nélkül, a dobóra a kapus készül";
  }

  // Csere-stílus: posztot tart vagy átszab a padjuk (3+ ki-be pár;
  // 70% fölött tartó, 40% alatt átszabó — a backenddel azonos
  // küszöbök: SWS_MIN_PAIRS, SWS_SAME_PCT, SWS_CROSS_PCT).
  String? _swapStyle(Map<String, dynamic> r) {
    final pairs = (r["sws_pairs"] as num?)?.toInt() ?? 0;
    final same = (r["sws_same"] as num?)?.toInt() ?? 0;
    if (pairs < 3) return null;
    final pct = 100.0 * same / pairs;
    if (pct >= 70.0) {
      return "posztot tartó a padjuk ($same/$pairs azonos-posztú "
          "váltás) · a párosítás a csere után is érvényes";
    }
    if (pct <= 40.0) {
      return "átszabó a padjuk ($same/$pairs azonos-posztú váltás) "
          "· a cserehullámuk után újra kell osztani a fogásokat";
    }
    return null;
  }

  // Elzárópáros-poszt: melyik posztpárra jár az elzárás-játékuk
  // (3+ elzárt lövés, 60% részarány — a backenddel azonos küszöbök:
  // SPP_MIN_SHOTS, SPP_SHARE_PCT).
  String? _screenPairRole(Map<String, dynamic> r) {
    final byRole =
        (r["spp_shots_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "az elzárás-játékuk a(z) $top posztpárra jár "
        "(${pct.round()}%, $total elzárt lövés) · párban készül a "
        "védekezés: az elzáró őrzője előre szól";
  }

  // Álló-poszt: melyik posztjuk áll labda nélkül (20+ mp mért
  // mozgás, a csapatátlagnál 20%-kal lassabb — a backenddel azonos
  // küszöbök: SAR_MIN_S, SAR_GAP_PCT).
  String? _staticAttackerRole(Map<String, dynamic> r) {
    final secs =
        (r["sar_seconds_by_role"] as Map?)?.cast<String, dynamic>();
    final mets =
        (r["sar_meters_by_role"] as Map?)?.cast<String, dynamic>();
    if (secs == null || secs.isEmpty || mets == null) return null;
    var totalS = 0.0;
    var totalM = 0.0;
    secs.forEach((k, v) => totalS += (v as num).toDouble());
    mets.forEach((k, v) => totalM += (v as num).toDouble());
    if (totalS <= 0) return null;
    final teamAvg = totalM / totalS;
    String? post;
    var postA = 0.0;
    secs.forEach((k, v) {
      final ps = (v as num).toDouble();
      if (ps < 20.0) return;
      final pa = ((mets[k] as num?) ?? 0).toDouble() / ps;
      if (teamAvg > 0 && pa <= teamAvg * 0.8 && post == null) {
        post = k;
        postA = pa;
      }
    });
    if (post == null) return null;
    return "a(z) $post posztjuk áll labda nélkül "
        "(${postA.toStringAsFixed(1)} m/s a "
        "${teamAvg.toStringAsFixed(1)} m/s átlag mellett) · a "
        "védője otthagyhatja, és befelé segíthet";
  }

  // Letámadó-poszt: melyik posztjuk szed labdát elöl (3+
  // elöl-szerzés, 60% részarány — a backenddel azonos küszöbök:
  // HSR_MIN_HIGH, HSR_SHARE_PCT).
  String? _highStealRole(Map<String, dynamic> r) {
    final byRole =
        (r["hsr_high_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "az elöl-szerzéseik ${pct.round()}%-a a(z) $top "
        "posztjuknál születik ($total letámadás-szerzés) · az ő "
        "oldalán tilos a kihozatalt vezetni";
  }

  // Célkereszt-poszt: melyik posztjuk előtt fejeznek be ellenük
  // (5+ rá-lövés, 60% részarány — a backenddel azonos küszöbök:
  // TGR_MIN_SHOTS, TGR_SHARE_PCT).
  String? _targetedDefenderRole(Map<String, dynamic> r) {
    final byRole =
        (r["tgr_shots_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 5) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "az ellenfelek ${pct.round()}%-ban a(z) $top posztjuk "
        "előtt fejeznek be ($total rá-lövés) · bevált minta: oda a "
        "támadás, a védője elé elzárás";
  }

  // Fedezett-lövő poszt: melyik posztjuk lő fedezetten is (3+
  // fedezett lövés, 60% részarány — a backenddel azonos küszöbök:
  // CVR_MIN_COVERED, CVR_SHARE_PCT).
  String? _coveredShooterRole(Map<String, dynamic> r) {
    final byRole =
        (r["cvr_covered_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a fedezett lövéseik ${pct.round()}%-a a(z) $top "
        "posztról jön ($total fedezett lövés) · rá nem kell "
        "kilépni, elég a blokk-kéz";
  }

  // Védőmotor-poszt: melyik posztjuk védő-motorja áll le (3+ első
  // félidei szerzés+blokk, legfeljebb 1 második félidei — a
  // backenddel azonos küszöbök: FDD_MIN_FH, FDD_MAX_SH).
  String? _fadingDefenderRole(Map<String, dynamic> r) {
    final fh =
        (r["fdd_fh_by_role"] as Map?)?.cast<String, dynamic>();
    final sh =
        (r["fdd_sh_by_role"] as Map?)?.cast<String, dynamic>();
    if (fh == null || fh.isEmpty) return null;
    String? post;
    var postFh = 0;
    fh.forEach((k, v) {
      final n = (v as num).toInt();
      final s2 = ((sh?[k] as num?) ?? 0).toInt();
      if (n >= 3 && s2 <= 1 && n > postFh) {
        post = k;
        postFh = n;
      }
    });
    if (post == null) return null;
    final postSh = ((sh?[post] as num?) ?? 0).toInt();
    return "a védő-motorjuk a(z) $post poszton az 1. félidőben "
        "pörög ($postFh szerzés+blokk), a 2.-ra leáll ($postSh) · "
        "a szünet után az ő zónáján át kell támadni";
  }

  // Áttörő-poszt: melyik posztjuk nyitja szét a falat (4+ labdás
  // betörés, 60% részarány — a backenddel azonos küszöbök:
  // BTR_MIN_ENTRIES, BTR_SHARE_PCT).
  String? _breakthroughRole(Map<String, dynamic> r) {
    final byRole =
        (r["btr_entries_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 4) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a falat ${pct.round()}%-ban a(z) $top posztjuk nyitja "
        "szét ($total labdás betörés) · a védője kapjon segítőt, a "
        "vonalát testtel kell zárni";
  }

  // Drága-eladó poszt: kinek a hibái kerülnek gólba (3+ büntetett
  // eladás, 60% részarány — a backenddel azonos küszöbök:
  // DTO_MIN_PUNISHED, DTO_SHARE_PCT).
  String? _costlyTurnoverRole(Map<String, dynamic> r) {
    final byRole =
        (r["dto_punished_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a gólba forduló eladásaik ${pct.round()}%-a a(z) $top "
        "posztnál történik ($total büntetett hiba) · a "
        "felhozatalnál őt kell kettőzni-zavarni";
  }

  // Beérkező-poszt: melyik posztra hoz frissítést a padjuk (3+
  // beállás, 60% részarány — a backenddel azonos küszöbök:
  // IBR_MIN_INS, IBR_SHARE_PCT).
  String? _subInRole(Map<String, dynamic> r) {
    final byRole =
        (r["ibr_ins_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a padjuk a(z) $top posztra hoz frissítést "
        "(${pct.round()}%, $total beállás) · a cserehullám után "
        "arra a sávra kell váltani";
  }

  // Forgatott-poszt: melyik posztjukat cserélik (3+ lecserélés,
  // 60% részarány — a backenddel azonos küszöbök: SBR_MIN_OUTS,
  // SBR_SHARE_PCT).
  String? _substitutedRole(Map<String, dynamic> r) {
    final byRole =
        (r["sbr_outs_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a forgatásuk a(z) $top posztra jár (${pct.round()}%, "
        "$total lecserélés) · a fárasztást a nem forgatott "
        "posztokra kell tervezni";
  }

  // Fáradt-fal poszt: a 2. félidőben melyik poszt jár át rajtuk
  // (3+ 2. félidei kapott gól, az 1. félidei legalább kétszerese —
  // a backenddel azonos küszöbök: TCR_MIN_SH, TCR_FACTOR).
  String? _tiredConcederRole(Map<String, dynamic> r) {
    final fh =
        (r["tcr_fh_by_role"] as Map?)?.cast<String, dynamic>();
    final sh =
        (r["tcr_sh_by_role"] as Map?)?.cast<String, dynamic>();
    if (sh == null || sh.isEmpty) return null;
    String? post;
    var postSh = 0;
    var postFh = 0;
    sh.forEach((k, v) {
      final n = (v as num).toInt();
      final f = ((fh?[k] as num?) ?? 0).toInt();
      final base = f < 1 ? 1 : f;
      if (n >= 3 && n >= 2 * base && n > postSh) {
        post = k;
        postSh = n;
        postFh = f;
      }
    });
    if (post == null) return null;
    return "a faluk a 2. félidőre a(z) $post poszt ellen ül le "
        "($postFh → $postSh kapott gól) · a szünet után onnan kell "
        "nyitni";
  }

  // Fáradt-lövő poszt: kinek megy szét a lövése a 2. félidőben (3+
  // 2. félidei mellé, az 1. félidei legalább kétszerese — a
  // backenddel azonos küszöbök: FSA_MIN_SH, FSA_FACTOR).
  String? _tiredShooterRole(Map<String, dynamic> r) {
    final fh =
        (r["fsa_fh_by_role"] as Map?)?.cast<String, dynamic>();
    final sh =
        (r["fsa_sh_by_role"] as Map?)?.cast<String, dynamic>();
    if (sh == null || sh.isEmpty) return null;
    String? post;
    var postSh = 0;
    var postFh = 0;
    sh.forEach((k, v) {
      final n = (v as num).toInt();
      final f = ((fh?[k] as num?) ?? 0).toInt();
      final base = f < 1 ? 1 : f;
      if (n >= 3 && n >= 2 * base && n > postSh) {
        post = k;
        postSh = n;
        postFh = f;
      }
    });
    if (post == null) return null;
    return "a(z) $post posztjuk kaput elkerülő lövései a 2. "
        "félidőre megugranak ($postFh → $postSh) · fáradtan rá "
        "lehet engedni";
  }

  // Fáradt-eladó poszt: kinek a labdái vesznek el a 2. félidőben
  // (3+ 2. félidei eladás, az 1. félidei legalább kétszerese — a
  // backenddel azonos küszöbök: FTO_MIN_SH, FTO_FACTOR).
  String? _tiredTurnoverRole(Map<String, dynamic> r) {
    final fh =
        (r["fto_fh_by_role"] as Map?)?.cast<String, dynamic>();
    final sh =
        (r["fto_sh_by_role"] as Map?)?.cast<String, dynamic>();
    if (sh == null || sh.isEmpty) return null;
    String? post;
    var postSh = 0;
    var postFh = 0;
    sh.forEach((k, v) {
      final n = (v as num).toInt();
      final f = ((fh?[k] as num?) ?? 0).toInt();
      final base = f < 1 ? 1 : f;
      if (n >= 3 && n >= 2 * base && n > postSh) {
        post = k;
        postSh = n;
        postFh = f;
      }
    });
    if (post == null) return null;
    return "a(z) $post posztjuk eladásai a 2. félidőre megugranak "
        "($postFh → $postSh) · a szünet után friss védővel őt kell "
        "nyomni";
  }

  // Hátrapassz-poszt: melyik posztjuknál fordul vissza a játék (5+
  // hátra-passz, 60% részarány — a backenddel azonos küszöbök:
  // BPR_MIN_PASSES, BPR_SHARE_PCT).
  String? _backwardPassRole(Map<String, dynamic> r) {
    final byRole =
        (r["bpr_passes_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 5) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a játékuk ${pct.round()}%-ban a(z) $top posztnál fordul"
        " vissza ($total hátra-passz) · a pressz rá jutalmat hoz";
  }

  // Térnyerő-poszt: melyik posztjuk viszi előre a labdát (50+
  // labdás előre-méter, 60% részarány — a backenddel azonos
  // küszöbök: TNR_MIN_M, TNR_SHARE_PCT).
  String? _ballCarrierRole(Map<String, dynamic> r) {
    final byRole =
        (r["tnr_meters_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0.0;
    byRole.forEach((k, v) => total += (v as num).toDouble());
    if (total < 50.0) return null;
    String? top;
    var topN = 0.0;
    byRole.forEach((k, v) {
      final n = (v as num).toDouble();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a térnyerésük a(z) $top poszt lábán van "
        "(${pct.round()}%, ${total.round()} labdás előre-méter) · "
        "hátrálva kell fogadni, lendületbe engedni tilos";
  }

  // Előnyben-poszt: vezetésnél melyik posztjuk viszi a játékot (3+
  // előnyben lőtt gól, 60% részarány — a backenddel azonos
  // küszöbök: LGR_MIN_GOALS, LGR_SHARE_PCT).
  String? _leadScorerRole(Map<String, dynamic> r) {
    final byRole =
        (r["lgr_goals_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "vezetésnél a(z) $top posztjuk viszi a játékot "
        "(${pct.round()}%, $total előnyben lőtt gól) · az ő "
        "kivétele töri a lendület-tartásukat";
  }

  // Előkészítő-poszt: melyik posztjuk készíti elő a lövéseket (5+
  // előkészítő passz, 60% részarány — a backenddel azonos küszöbök:
  // EPR_MIN_PASSES, EPR_SHARE_PCT).
  String? _lastPassRole(Map<String, dynamic> r) {
    final byRole =
        (r["epr_passes_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 5) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a lövéseiket ${pct.round()}%-ban a(z) $top posztjuk "
        "készíti elő ($total előkészítő passz) · az ő sávjának "
        "zárásával a lövőik elhalnak";
  }

  // Indító-poszt: melyik posztjuknál indul a támadás-szervezés (5+
  // szakasz, 60% részarány — a backenddel azonos küszöbök:
  // ATS_MIN_ATTACKS, ATS_SHARE_PCT).
  String? _attackStarterRole(Map<String, dynamic> r) {
    final byRole =
        (r["ats_attacks_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 5) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a támadásaik ${pct.round()}%-a a(z) $top posztnál indul"
        " ($total szakasz) · korai pressz rá már a felezőnél";
  }

  // Beállóőr-poszt: melyik posztjuk őrzi a beállót (300+
  // őrzés-kocka, 60% részarány — a backenddel azonos küszöbök:
  // PGR_MIN_FRAMES, PGR_SHARE_PCT).
  String? _pivotGuardRole(Map<String, dynamic> r) {
    final byRole =
        (r["pgr_frames_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 300) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a beálló-őrzésük a(z) $top posztjukon áll "
        "(${pct.round()}% az őrzött időből) · az elzárás őt húzza "
        "ki, és a beálló felszabadul";
  }

  // Kilépő-poszt: melyik posztjuk lép ki a falból (posztonként
  // 100+ kocka, 3+ mért poszt, 2,5 m mélység-többlet — a backenddel
  // azonos küszöbök: ADR_MIN_FRAMES, ADR_MIN_ROLES, ADR_GAP_M).
  String? _advancedDefRole(Map<String, dynamic> r) {
    final frames =
        (r["adr_frames_by_role"] as Map?)?.cast<String, dynamic>();
    final depth =
        (r["adr_depthm_by_role"] as Map?)?.cast<String, dynamic>();
    if (frames == null || frames.isEmpty || depth == null) return null;
    final ok = <String, int>{};
    frames.forEach((k, v) {
      final n = (v as num).toInt();
      if (n >= 100) ok[k] = n;
    });
    if (ok.length < 3) return null;
    String? top;
    var topAvg = 0.0;
    ok.forEach((k, n) {
      final avg = ((depth[k] as num?) ?? 0).toDouble() / n;
      if (top == null || avg > topAvg) {
        top = k;
        topAvg = avg;
      }
    });
    if (top == null) return null;
    var restN = 0;
    var restD = 0.0;
    ok.forEach((k, n) {
      if (k == top) return;
      restN += n;
      restD += ((depth[k] as num?) ?? 0).toDouble();
    });
    if (restN == 0) return null;
    final gap = topAvg - restD / restN;
    if (gap < 2.5) return null;
    return "a faluk a(z) $top posztnál lép ki (a társaknál "
        "${gap.toStringAsFixed(1)} m-rel előrébb) · elzárást rá, "
        "mögötte nyílik a tér";
  }

  // Ziccerhagyó-poszt: melyik posztjuk hagyja ki a ziccereket (3+
  // kihagyott nagy helyzet, 60% részarány — a backenddel azonos
  // küszöbök: MCR_MIN_MISSES, MCR_SHARE_PCT).
  String? _missedChanceRole(Map<String, dynamic> r) {
    final byRole =
        (r["mcr_misses_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a kihagyott ziccereik ${pct.round()}%-a a(z) $top "
        "posztnál esik ($total kihagyás) · az ő helyzetbe engedése "
        "a kisebbik rossz";
  }

  // Blokkolt-poszt: melyik posztjuk lövéseit blokkolják (3+
  // blokkolt lövés, 60% részarány — a backenddel azonos küszöbök:
  // BSR_MIN_BLOCKS, BSR_SHARE_PCT).
  String? _blockedShooterRole(Map<String, dynamic> r) {
    final byRole =
        (r["bsr_blocks_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a blokkolt lövéseik ${pct.round()}%-a a(z) $top "
        "posztról jön ($total blokk) · a fal ellene bátran zárhat";
  }

  // Hetesdobó-poszt: melyik posztjuk áll oda a hetesekhez (3+
  // hetes-kísérlet, 60% részarány — a backenddel azonos küszöbök:
  // STK_MIN_ATTEMPTS, STK_SHARE_PCT).
  String? _sevenTakerRole(Map<String, dynamic> r) {
    final byRole =
        (r["stk_attempts_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a heteseiket ${pct.round()}%-ban a(z) $top posztjuk "
        "dobja ($total hetes) · a kapus az ő szokás-irányaira "
        "készüljön";
  }

  // Újrakezdő-poszt: melyik posztjuk viszi a szünet utáni rajtot
  // (3+ gól a 2. félidő első tíz percében, 60% részarány — a
  // backenddel azonos küszöbök: SSR_MIN_GOALS, SSR_SHARE_PCT).
  String? _secondStartRole(Map<String, dynamic> r) {
    final byRole =
        (r["ssr_goals_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a szünet utáni rajtjuk a(z) $top posztra épül "
        "(${pct.round()}%, $total gól a 2. félidő első tíz "
        "percében) · a szünet után őt fogja a legjobb védő";
  }

  // Elzárt-poszt: melyik védőjük akad el az elzárásokban (3+
  // elakadás, 60% részarány — a backenddel azonos küszöbök:
  // SDR_MIN_SCREENS, SDR_SHARE_PCT).
  String? _screenedDefRole(Map<String, dynamic> r) {
    final byRole =
        (r["sdr_screens_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "az elzárások ${pct.round()}%-ban a(z) $top posztjukon "
        "lévő védőt találják meg ($total elakadás) · az ő oldalára "
        "kell vinni a figurákat";
  }

  // Kettőzött-poszt: melyik posztjukra érkezik a kettőzés (100+
  // kettőzött labdás kocka, 60% részarány — a backenddel azonos
  // küszöbök: DTR_MIN_FRAMES, DTR_SHARE_PCT).
  String? _doubledTargetRole(Map<String, dynamic> r) {
    final byRole =
        (r["dtr_frames_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 100) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "az ellenfelek kettőzései ${pct.round()}%-ban a(z) $top "
        "posztjukra érkeznek · bevált recept: oda a kettőzés, "
        "mögötte passzsáv-zárás";
  }

  // Fáradó-poszt: melyik posztjuk esik vissza a 2. félidőre (100+
  // cm/s tempó-alap, 20% esés — a backenddel azonos küszöbök:
  // FTR_MIN_CMS, FTR_DROP_PCT).
  String? _fatigueRole(Map<String, dynamic> r) {
    final first =
        (r["ftr_first_cms_by_role"] as Map?)?.cast<String, dynamic>();
    final second =
        (r["ftr_second_cms_by_role"] as Map?)?.cast<String, dynamic>();
    if (first == null || first.isEmpty) return null;
    String? worst;
    var worstDrop = 0.0;
    first.forEach((k, v) {
      final f = (v as num).toDouble();
      if (f < 100) return;
      final s2 = ((second?[k] as num?) ?? 0).toDouble();
      final drop = 100.0 * (f - s2) / f;
      if (worst == null || drop > worstDrop) {
        worst = k;
        worstDrop = drop;
      }
    });
    if (worst == null || worstDrop < 20.0) return null;
    return "a második félidőre a(z) $worst posztjuk esik vissza a "
        "legjobban (−${worstDrop.round()}% tempó) · a szünet után az"
        " ő sávjában kell támadni";
  }

  // Passzív-poszt: melyik posztjuknál hal el a felállt támadás
  // (250+ passzív labdás kocka, 60% részarány — a backenddel azonos
  // küszöbök: PVR_MIN_FRAMES, PVR_SHARE_PCT).
  String? _passiveHolderRole(Map<String, dynamic> r) {
    final byRole =
        (r["pvr_frames_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 250) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a terméketlen támadásaik a(z) $top posztnál halnak el "
        "(${pct.round()}% a passzív-gyanús labdás időből) · passzív"
        " jelzésnél őt kell nyomás alá tenni";
  }

  // Rajt-poszt: melyik posztjuk viszi a meccs elejét (3+ gól az
  // első tíz percben, 60% részarány — a backenddel azonos küszöbök:
  // OSR_MIN_GOALS, OSR_SHARE_PCT).
  String? _openingScorerRole(Map<String, dynamic> r) {
    final byRole =
        (r["osr_goals_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a rajtjuk a(z) $top posztra épül (${pct.round()}%, "
        "$total gól az első tíz percben) · a meccs elején őt fogja "
        "a legjobb védő";
  }

  // Kiszolgált-poszt: melyik posztjuk fejezi be a bejátszásokat (3+
  // asszisztos gól, 60% részarány — a backenddel azonos küszöbök:
  // ASR_MIN_ASSISTED, ASR_SHARE_PCT).
  String? _assistedScorerRole(Map<String, dynamic> r) {
    final byRole =
        (r["asr_assisted_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a kiszolgált góljaik ${pct.round()}%-át a(z) $top "
        "posztjuk fejezi be ($total asszisztos gól) · a felé futó "
        "passzt kell elvágni, és magától elhal";
  }

  // Hajrákéz-poszt: melyik poszt kezén fut a végjátékuk (200+
  // hajrá-labdás kocka, 60% részarány — a backenddel azonos
  // küszöbök: CHR_MIN_FRAMES, CHR_SHARE_PCT).
  String? _clutchHogRole(Map<String, dynamic> r) {
    final byRole =
        (r["chr_frames_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 200) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a végjátékuk a(z) $top poszt kezén fut (${pct.round()}%"
        " a hajrá labdás idejéből) · a hajrá-kettőzés őt fogja, nem"
        " a lövőt";
  }

  // Lágypassz-poszt: melyik posztjuk passzol lágyan (5+ lágy passz,
  // 60% részarány — a backenddel azonos küszöbök: SPS_MIN_SOFT,
  // SPS_SHARE_PCT).
  String? _softPassRole(Map<String, dynamic> r) {
    final byRole =
        (r["sps_soft_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 5) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a lágy passzaik ${pct.round()}%-a a(z) $top posztról "
        "jön ($total lágy passz) · az ő labdáiba bele lehet nyúlni";
  }

  // Sprint-poszt: melyik posztjuk futja a sprinteket (10+ sprint,
  // 60% részarány — a backenddel azonos küszöbök: SPR_MIN_SPRINTS,
  // SPR_SHARE_PCT).
  String? _sprintThreatRole(Map<String, dynamic> r) {
    final byRole =
        (r["spr_sprints_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 10) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a sprintjeik ${pct.round()}%-át a(z) $top posztjuk futja"
        " ($total sprint) · labdavesztésnél az ő útját kell először "
        "lezárni";
  }

  // Középkezdő-poszt: melyik posztjuknál indul a középkezdés (3+
  // átvétel, 60% részarány — a backenddel azonos küszöbök:
  // RTR_MIN_TAKES, RTR_SHARE_PCT).
  String? _restartTakerRole(Map<String, dynamic> r) {
    final byRole =
        (r["rtr_takes_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a középkezdésük ${pct.round()}%-ban a(z) $top posztnál "
        "indul ($total átvétel) · a gól utáni letámadás őt fogja le";
  }

  // Forró-poszt: melyik posztjuk lövi a gólsorozatokat (3+
  // sorozat-gól, 60% részarány — a backenddel azonos küszöbök:
  // HHR_MIN_GOALS, HHR_SHARE_PCT).
  String? _hotHandRole(Map<String, dynamic> r) {
    final byRole =
        (r["hhr_goals_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a gólsorozataik ${pct.round()}%-a a(z) $top posztról "
        "jön ($total sorozat-gól) · az első gólja után azonnal "
        "őrzés-váltás vagy kettőzés";
  }

  // Hajráhiba-poszt: melyik posztjuk adja el a labdát a hajrában
  // (3+ hajrá-eladás, 60% részarány — a backenddel azonos küszöbök:
  // CTR_MIN_TO, CTR_SHARE_PCT).
  String? _clutchTurnoverRole(Map<String, dynamic> r) {
    final byRole =
        (r["ctr_to_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a hajrá-eladásaik ${pct.round()}%-a a(z) $top posztnál "
        "történik ($total eladás az utolsó öt percben) · a záró "
        "percekben oda jön a pressz";
  }

  // Eltűnő-poszt: melyik posztjuk tűnik el a második félidőre (3+
  // első félidei gól-részvétel, legfeljebb 1 második félidei — a
  // backenddel azonos küszöbök: FDP_MIN_FH, FDP_MAX_SH).
  String? _fadingRole(Map<String, dynamic> r) {
    final fh =
        (r["fdp_fh_by_role"] as Map?)?.cast<String, dynamic>();
    final sh =
        (r["fdp_sh_by_role"] as Map?)?.cast<String, dynamic>();
    if (fh == null || fh.isEmpty) return null;
    String? post;
    var postFh = 0;
    fh.forEach((k, v) {
      final n = (v as num).toInt();
      final s2 = ((sh?[k] as num?) ?? 0).toInt();
      if (n >= 3 && s2 <= 1 && n > postFh) {
        post = k;
        postFh = n;
      }
    });
    if (post == null) return null;
    final postSh = ((sh?[post] as num?) ?? 0).toInt();
    return "a(z) $post posztjuk az első félidőben él ($postFh "
        "gól-részvétel), a másodikra eltűnik ($postSh) · az első 30 "
        "percben kell megfogni";
  }

  // Csendtörő-poszt: melyik posztjuk töri meg a gólcsendet (3+
  // csend-törő gól, 60% részarány — a backenddel azonos küszöbök:
  // GCT_MIN_BREAKS, GCT_SHARE_PCT).
  String? _droughtBreakRole(Map<String, dynamic> r) {
    final byRole =
        (r["gct_breaks_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a gólcsendjüket a(z) $top posztjuk töri meg "
        "(${pct.round()}%, $total csend-törő gól) · a sorozatotok "
        "alatt őt kell a legszorosabban fogni";
  }

  // Pressz-poszt: melyik posztjuk ejti a labdát szorításban (3+
  // nyomott eladás, 60% részarány — a backenddel azonos küszöbök:
  // PSR_MIN_TO, PSR_SHARE_PCT).
  String? _pressSensRole(Map<String, dynamic> r) {
    final byRole =
        (r["psr_to_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "szorításban a(z) $top posztjuk ejti a labdát "
        "(${pct.round()}%, $total nyomott eladás) · a kettőzés oda "
        "labdaszerzés";
  }

  // Labdatartó-poszt: melyik posztjuknál áll meg a labda (60+ mp
  // mért tartás, 60% részarány — a backenddel azonos küszöbök:
  // HTR_MIN_S, HTR_SHARE_PCT).
  String? _holdShareRole(Map<String, dynamic> r) {
    final byRole =
        (r["htr_seconds_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0.0;
    byRole.forEach((k, v) => total += (v as num).toDouble());
    if (total < 60.0) return null;
    String? top;
    var topN = 0.0;
    byRole.forEach((k, v) {
      final n = (v as num).toDouble();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a labda a(z) $top posztjuknál áll meg (${pct.round()}%, "
        "${total.round()} mp mért tartás) · a kettőzést rá kell "
        "időzíteni";
  }

  // Ziccer-poszt: melyik posztjuknál alakul ki a nagy helyzet (3+
  // ziccer, 60% részarány — a backenddel azonos küszöbök:
  // BCR_MIN_CHANCES, BCR_SHARE_PCT).
  String? _bigChanceRole(Map<String, dynamic> r) {
    final byRole =
        (r["bcr_chances_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a ziccereik ${pct.round()}%-a a(z) $top posztnál alakul "
        "ki ($total nagy helyzet) · korábbi besegítés és szűkítés az "
        "ő sávjában";
  }

  // Pazarló-poszt: melyik posztjuk lövi mellé a lövéseit (3+ kaput
  // elkerülő lövés, 60% részarány — a backenddel azonos küszöbök:
  // WSR_MIN_OFF, WSR_SHARE_PCT).
  String? _wastefulRole(Map<String, dynamic> r) {
    final byRole =
        (r["wsr_off_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a kaput elkerülő lövéseik ${pct.round()}%-a a(z) $top "
        "posztról jön ($total mellé/blokkolt lövés) · az ő lövését "
        "rá lehet engedni, a kidobásból azonnali indítás";
  }

  // Felzárkózás-poszt: melyik posztjuk hozza őket vissza hátrányból
  // (3+ hátrány-gól-részvétel, 60% részarány — a backenddel azonos
  // küszöbök: CBR_MIN_TRAILING, CBR_SHARE_PCT).
  String? _comebackRole(Map<String, dynamic> r) {
    final byRole =
        (r["cbr_trailing_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "hátrányból a(z) $top posztjuk hozza őket vissza "
        "(${pct.round()}%, $total hátrány-gól-részvétel) · vezetésnél "
        "őt kell kivenni, és a hátrányuk beragad";
  }

  // Emberhátrány-poszt: melyik posztjuk vállal be öt emberrel (3+
  // hátrány-lövés, 60% részarány — a backenddel azonos küszöbök:
  // SHR_MIN_SHOTS, SHR_SHARE_PCT).
  String? _shorthandedRole(Map<String, dynamic> r) {
    final byRole =
        (r["shr_shots_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "öt emberrel a(z) $top posztjuk vállal be "
        "(${pct.round()}%, $total lövés) · emberelőnyben az ő "
        "oldalán kell a labdabiztonság";
  }

  // Emberelőny-poszt: melyik posztjuk fejez be a két perc alatt (3+
  // emberelőny-lövés, 60% részarány — a backenddel azonos küszöbök:
  // PPR_MIN_SHOTS, PPR_SHARE_PCT).
  String? _powerplayRole(Map<String, dynamic> r) {
    final byRole =
        (r["ppr_shots_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "az emberelőnyük a(z) $top posztra fut ki "
        "(${pct.round()}%, $total lövés) · hátrányban az ő sávját "
        "kell tartani";
  }

  // Kiosztás-poszt: melyik posztra jár a betörés utáni labda (4+
  // kiosztás, 60% részarány — a backenddel azonos küszöbök:
  // KOR_MIN_KICKOUTS, KOR_SHARE_PCT).
  String? _kickoutRole(Map<String, dynamic> r) {
    final byRole =
        (r["kor_kickouts_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 4) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a betöréseik utáni labda a(z) $top posztra jár "
        "(${pct.round()}%, $total kiosztás) · a védője előre "
        "zárhatja a sávot";
  }

  // Kettőző-poszt: melyik posztjuk lép ki kettőzni (40+ kettőzött
  // kocka, 60% részarány — a backenddel azonos küszöbök:
  // DDR_MIN_FRAMES, DDR_SHARE_PCT).
  String? _doublingRole(Map<String, dynamic> r) {
    final byRole =
        (r["ddr_frames_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 40) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a kettőzésük a(z) $top posztról érkezik "
        "(${pct.round()}%) · az elhagyott embere felé menjen az "
        "első passz";
  }

  // Kockáztató-poszt: melyik posztjuk szórja el a hosszú labdákat
  // (3+ elszórt hosszú passz, 60% részarány — a backenddel azonos
  // küszöbök: RPR_MIN_TO, RPR_SHARE_PCT).
  String? _riskyPasserRole(Map<String, dynamic> r) {
    final byRole =
        (r["rpr_to_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a hazárd hosszú labdáik a(z) $top posztról indulnak "
        "(${pct.round()}%, $total eladás) · az ő passzsávjába kell "
        "beállni";
  }

  // Vasember-poszt: melyik posztjuk játszik végig csere nélkül
  // (10+ percnyi kocka, 85% jelenlét és 15 százalékpontos előny — a
  // backenddel azonos küszöbök: IRM_MIN_MATCH_MIN, IRM_SHARE_PCT,
  // IRM_GAP_PP; a kocka→perc váltás 25 fps-t feltételez).
  String? _ironManRole(Map<String, dynamic> r) {
    final byRole =
        (r["irm_on_by_role"] as Map?)?.cast<String, dynamic>();
    final total = (r["irm_total_frames"] as num?)?.toInt() ?? 0;
    if (byRole == null || byRole.isEmpty || total < 15000) return null;
    final shares = byRole.entries
        .map((e) => MapEntry(e.key, 100.0 * (e.value as num) / total))
        .toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final top = shares.first;
    final second = shares.length > 1 ? shares[1].value : 0.0;
    if (top.value < 85.0 || top.value - second < 15.0) return null;
    return "a(z) ${top.key} posztjuk végigjátssza a meccset "
        "(${top.value.round()}% jelenlét) · a hajrában oda kell "
        "vinni a tempót";
  }

  // Bejátszó-poszt: melyik posztjuk játssza be a beállót (4+
  // beálló-beadás, 60% részarány — a backenddel azonos küszöbök:
  // PFR_MIN_FEEDS, PFR_SHARE_PCT).
  String? _pivotFeederRole(Map<String, dynamic> r) {
    final byRole =
        (r["pfr_feeds_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 4) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a beálló-beadásaik a(z) $top posztról jönnek "
        "(${pct.round()}%, $total beadás) · az ő kezén kell a "
        "vonalba lépni";
  }

  // Indítás-vadász poszt: melyik posztjuk vadássza a kapus-indítást
  // (3+ elrabolt indítás, 60% részarány — a backenddel azonos
  // küszöbök: OHR_MIN_STEALS, OHR_SHARE_PCT).
  String? _outletHunterRole(Map<String, dynamic> r) {
    final byRole =
        (r["ohr_steals_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "az indítás-vadászatuk a(z) $top poszton fut "
        "(${pct.round()}%, $total rablás) · a kapus-indítás a másik "
        "oldalon nyisson";
  }

  // Kulcs-poszt: hány poszt-réteg ítélete fut ki ugyanarra a posztra
  // (3+ egyező réteg, holtverseny nélkül — a backenddel azonos
  // küszöb: KP_MIN_LAYERS).
  String? _keyPost(Map<String, dynamic> r) {
    final byPost =
        (r["kp_layers_by_post"] as Map?)?.cast<String, dynamic>();
    if (byPost == null || byPost.isEmpty) return null;
    String? top;
    var topN = 0;
    var tie = false;
    byPost.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
        tie = false;
      } else if (n == topN) {
        tie = true;
      }
    });
    if (top == null || topN < 3 || tie) return null;
    return "a kulcs-posztjuk a(z) $top: $topN poszt-réteg ítélete "
        "fut ki rá · az ő kezelése a meccsterv első lapja";
  }

  // Elzáró-poszt: melyik posztjuk áll elzárásba (3+ poszthoz kötött
  // elzárás, 60% részarány — a backenddel azonos küszöbök:
  // SCR2_MIN_SCREENS, SCR2_SHARE_PCT).
  String? _screenSetterRole(Map<String, dynamic> r) {
    final byRole =
        (r["sc2_screens_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "az elzárásaik a(z) $top posztról jönnek (${pct.round()}%, "
        "$total elzárás) · az ő oldalán hangos váltás kell";
  }

  // Átvert-poszt: melyik posztjuk mögött esnek a kapott gólok (3+
  // védőhöz rendelt gól, 60% részarány — a backenddel azonos
  // küszöbök: BTR_MIN_GOALS, BTR_SHARE_PCT).
  String? _beatenRole(Map<String, dynamic> r) {
    final byRole =
        (r["btr_beaten_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a kapott góljaik a(z) $top posztjuk mögött esnek "
        "(${pct.round()}%, $total gól) · oda kell vinni az 1v1-et";
  }

  // Visszafutás-poszt: ki marad le a visszarendeződésben (3+ mért
  // ellenfél-kontra, 60% részarány — a backenddel azonos küszöbök:
  // RTR_MIN_BREAKS, RTR_SHARE_PCT).
  String? _slowRetreatRole(Map<String, dynamic> r) {
    final byRole =
        (r["rtr_lags_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a visszarendeződésük a(z) $top poszton szakad el "
        "(${pct.round()}%, $total kontra) · a kontrát az ő sávjába "
        "kell vezetni";
  }

  // Kiülő-poszt: melyik posztjuk gyűjti a kétperceket (3+ poszthoz
  // kötött kiállítás, 60% részarány — a backenddel azonos küszöbök:
  // SUP_MIN_SUSP, SUP_SHARE_PCT).
  String? _suspendedRole(Map<String, dynamic> r) {
    final byRole =
        (r["sup_susp_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a kétperceik a(z) $top posztra járnak (${pct.round()}%, "
        "$total kiállítás) · a meccs elején oda kell vezetni a "
        "játékot";
  }

  // Hetes-okozó poszt: melyik sávjuk szakad be hetessel (3+ okozott
  // hetes, 60% részarány — a backenddel azonos küszöbök:
  // SVR_MIN_SEVENS, SVR_SHARE_PCT).
  String? _sevenConcederRole(Map<String, dynamic> r) {
    final byRole =
        (r["svr_sevens_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a heteseik a(z) $top poszton szakadnak be "
        "(${pct.round()}%, $total hetes) · oda érdemes betörést "
        "vezetni";
  }

  // 7a6-befejező poszt: kire fut ki a hetedik ember játéka (3+
  // 7a6-lövés, 60% részarány — a backenddel azonos küszöbök:
  // EN7_MIN_SHOTS, EN7_SHARE_PCT).
  String? _sevenSixRole(Map<String, dynamic> r) {
    final byRole =
        (r["en7_shots_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a 7 a 6-uk a(z) $top posztra fut ki (${pct.round()}%, "
        "$total lövés) · a lehozott kapusnál oda kell sűríteni";
  }

  // Blokk-poszt: melyik posztjuk blokkolja a lövéseket (3+ poszthoz
  // kötött blokk, 60% részarány — a backenddel azonos küszöbök:
  // RBK_MIN_BLOCKS, RBK_SHARE_PCT).
  String? _blockRole(Map<String, dynamic> r) {
    final byRole =
        (r["rbk_blocks_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a blokkjaik zöme a(z) $top poszttól jön (${pct.round()}%, "
        "$total blokk) · az ő sávjába csak elmozgatás után szabad "
        "lőni";
  }

  // Labdaszerző-poszt: melyik posztjuk nyeri a labdákat (5+ poszthoz
  // kötött szerzés, 50% részarány — a backenddel azonos küszöbök:
  // RSW_MIN_STEALS, RSW_SHARE_PCT).
  String? _stealRole(Map<String, dynamic> r) {
    final byRole =
        (r["rsw_steals_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 5) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 50.0) return null;
    return "a labdáik felét-többségét a(z) $top szedi (${pct.round()}%, "
        "$total szerzés) · az ő sávjába csak biztonsági passz mehet";
  }

  // Gólpassz-poszt: kinek a kezéből indulnak a góljaik (3+ poszthoz
  // kötött gólpassz, 60% részarány — a backenddel azonos küszöbök:
  // RAS_MIN_ASSISTS, RAS_SHARE_PCT).
  String? _assistRole(Map<String, dynamic> r) {
    final byRole =
        (r["ras_assists_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    byRole.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a góljaik a(z) $top kezéből indulnak (${pct.round()}%, "
        "$total gólpassz) · tőle a passzt kell elvenni, nem a lövést "
        "zárni";
  }

  // Hetes-oldal: merre dobják a heteseiket (3+ mérhető dobás, 60%
  // részarány — a backenddel azonos küszöbök: SVD_MIN_ATTEMPTS,
  // SVD_SHARE_PCT).
  String? _sevenSide(Map<String, dynamic> r) {
    final dirs = (r["svd_dirs"] as Map?)?.cast<String, dynamic>();
    if (dirs == null || dirs.isEmpty) return null;
    var total = 0;
    dirs.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    dirs.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a heteseik ${pct.round()}%-a $top oldalra megy ($total "
        "mérhető dobás) · hetesnél a kapus tudatosan arra vetődhet";
  }

  // Kontra-poszt: melyik posztjukon zárul a lerohanás (3+ kontra-lövés,
  // 60% részarány — a backenddel azonos küszöbök: RFB_MIN_SHOTS,
  // RFB_SHARE_PCT).
  String? _fastBreakRole(Map<String, dynamic> r) {
    final shots =
        (r["rfb_shots_by_role"] as Map?)?.cast<String, dynamic>();
    if (shots == null || shots.isEmpty) return null;
    var total = 0;
    shots.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    shots.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    return "a lerohanásaik a(z) $top poszton záródnak (${pct.round()}%, "
        "$total kontra-lövés) · visszafutásnál őt kell először felvenni";
  }

  // Lövésválasztás: felnéznek-e a lövés előtt (6+ mért lövés, 45%
  // felett "nem néznek fel", 15% alatt fegyelmezett — a backenddel
  // azonos küszöbök: SCQ_MIN_SHOTS, SCQ_HIGH_PCT, SCQ_LOW_PCT).
  String? _shotChoice(Map<String, dynamic> r) {
    final shots = (r["scq_shots"] as num?)?.toInt() ?? 0;
    final better = (r["scq_better"] as num?)?.toInt() ?? 0;
    if (shots < 6) return null;
    final pct = 100.0 * better / shots;
    if (pct >= 45.0) {
      return "a lövéseik ${pct.round()}%-ánál volt jobb SZABAD helyzet a "
          "pályán ($better/$shots) · nem néznek fel: a rossz szögű lövést "
          "rájuk lehet engedni, a szabad társukat kell zárni";
    }
    if (pct <= 15.0) {
      return "fegyelmezett lövésválasztás: csak ${pct.round()}%-nál volt "
          "jobb szabad helyzet ($better/$shots) · a helyzet-teremtést "
          "kell zárni, a lövésnél már késő";
    }
    return null;
  }

  // Időkérés-befejező: az időkérés után melyik posztra játszanak (3+
  // poszthoz kötött lövés, 60% részarány — a backenddel azonos
  // küszöbök: TOF_MIN_SHOTS, TOF_SHARE_PCT).
  String? _timeoutFinisher(Map<String, dynamic> r) {
    final shots =
        (r["tof_shots_by_role"] as Map?)?.cast<String, dynamic>();
    if (shots == null || shots.isEmpty) return null;
    var total = 0;
    shots.forEach((k, v) => total += (v as num).toInt());
    if (total < 3) return null;
    String? top;
    var topN = 0;
    shots.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    final pct = 100.0 * topN / total;
    if (pct < 60.0) return null;
    final timeouts = (r["tof_timeouts"] as num?)?.toInt() ?? 0;
    return "időkérés után a(z) $top posztjuk fejez be: a lövéseik "
        "${pct.round()}%-a onnan jött ($total lövés, $timeouts időkérés "
        "után) · ő kapja az embert, elé kell állni";
  }

  // Figura-befejező: hány figurájuk fut ki ugyanarra a posztra (2+
  // mérhető figura, 60% részarány — a backenddel azonos küszöb:
  // SPF_SHARE_PCT).
  String? _setplayFinisher(Map<String, dynamic> r) {
    final figures = (r["spf_figures"] as num?)?.toInt() ?? 0;
    final tel = (r["spf_telegraphed"] as num?)?.toInt() ?? 0;
    final byRole =
        (r["spf_telegraphed_by_role"] as Map?)?.cast<String, dynamic>();
    if (figures < 2 || tel < 1 || byRole == null || byRole.isEmpty) {
      return null;
    }
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      if (top == null || n > topN) {
        top = k;
        topN = n;
      }
    });
    if (top == null) return null;
    return "a figuráik $figures-ból $tel kiszámítható befejezésű, a "
        "legtöbb ($topN) a(z) $top posztra fut ki · a figura "
        "felismerésekor kell odacsúszni, nem a lövésnél";
  }

  // Poszt-nyomás: melyik posztjuk fejez be fedezetten is (8+ fedezett
  // lövés, posztonként 4+, 20 százalékpont eltérés — a backenddel
  // azonos küszöbök: RPF_MIN_SHOTS, RPF_GAP_PCT).
  String? _pressureFinishRole(Map<String, dynamic> r) {
    final shots =
        (r["rpf_covered_shots_by_role"] as Map?)?.cast<String, dynamic>();
    final goals =
        (r["rpf_covered_goals_by_role"] as Map?)?.cast<String, dynamic>();
    if (shots == null || shots.isEmpty || goals == null) return null;
    var total = 0;
    var totalG = 0;
    shots.forEach((k, v) => total += (v as num).toInt());
    goals.forEach((k, v) => totalG += (v as num).toInt());
    if (total < 8) return null;
    final teamPct = 100.0 * totalG / total;
    String? cold, shy;
    var coldPct = 0.0, shyPct = 0.0;
    var coldN = 0, shyN = 0;
    shots.forEach((k, v) {
      final n = (v as num).toInt();
      if (n < 4) return;
      final pct = 100.0 * ((goals[k] as num?) ?? 0).toInt() / n;
      if (cold == null || pct > coldPct) {
        cold = k;
        coldPct = pct;
        coldN = n;
      }
      if (shy == null || pct < shyPct) {
        shy = k;
        shyPct = pct;
        shyN = n;
      }
    });
    if (cold != null && coldPct - teamPct >= 20.0) {
      return "a(z) $cold posztjuk fedezetten is befejez: a fedezett "
          "lövéseik ${coldPct.round()}%-át belövi ($coldN lövés, "
          "csapat-átlag ${teamPct.round()}%) · őt ki kell zárni, a puszta "
          "kilépés nála kevés";
    }
    if (shy != null && teamPct - shyPct >= 20.0) {
      return "a(z) $shy posztjuk fedezetten beesik: a fedezett lövéseik "
          "${shyPct.round()}%-át lövi be ($shyN lövés, csapat-átlag "
          "${teamPct.round()}%) · rá érdemes kilépni, nála a nyomás "
          "megoldja a helyzetet";
    }
    return null;
  }

  // Poszt-lövéserő: melyik posztjuk lő keményen (8+ lövés,
  // posztonként 4+, 12 km/h eltérés — a backenddel azonos küszöbök:
  // RSP_MIN_SHOTS, RSP_GAP_KMH).
  String? _shotPowerRole(Map<String, dynamic> r) {
    final shots = (r["rsp_shots_by_role"] as Map?)?.cast<String, dynamic>();
    final sums = (r["rsp_kmh_sum_by_role"] as Map?)?.cast<String, dynamic>();
    if (shots == null || shots.isEmpty || sums == null) return null;
    var total = 0;
    var totalK = 0.0;
    shots.forEach((k, v) => total += (v as num).toInt());
    sums.forEach((k, v) => totalK += (v as num).toDouble());
    if (total < 8) return null;
    final teamAvg = totalK / total;
    String? hard;
    var hardAvg = 0.0;
    var hardN = 0;
    shots.forEach((k, v) {
      final n = (v as num).toInt();
      if (n < 4) return;
      final avg = ((sums[k] as num?) ?? 0).toDouble() / n;
      if (hard == null || avg > hardAvg) {
        hard = k;
        hardAvg = avg;
        hardN = n;
      }
    });
    if (hard == null || hardAvg - teamAvg < 12.0) return null;
    return "a(z) $hard posztjuk lő a legkeményebben: átlag "
        "${hardAvg.round()} km/h ($hardN lövés, csapat-átlag "
        "${teamAvg.round()} km/h) · a kapus korábban induljon, a fal "
        "szöget zárjon";
  }

  // Poszt-lövésidőzítés: melyik posztjuk mikor fejez be a támadáson
  // belül (8+ lövés, posztonként 4+, 4 mp eltérés — a backenddel
  // azonos küszöbök: RST_MIN_SHOTS, RST_GAP_S).
  String? _shotTimingRole(Map<String, dynamic> r) {
    final shots = (r["rst_shots_by_role"] as Map?)?.cast<String, dynamic>();
    final sums = (r["rst_time_sum_by_role"] as Map?)?.cast<String, dynamic>();
    if (shots == null || shots.isEmpty || sums == null) return null;
    var total = 0;
    var totalS = 0.0;
    shots.forEach((k, v) => total += (v as num).toInt());
    sums.forEach((k, v) => totalS += (v as num).toDouble());
    if (total < 8) return null;
    final teamAvg = totalS / total;
    String? early, late;
    var earlyAvg = 0.0, lateAvg = 0.0;
    var earlyN = 0, lateN = 0;
    shots.forEach((k, v) {
      final n = (v as num).toInt();
      if (n < 4) return;
      final avg = ((sums[k] as num?) ?? 0).toDouble() / n;
      if (early == null || avg < earlyAvg) {
        early = k;
        earlyAvg = avg;
        earlyN = n;
      }
      if (late == null || avg > lateAvg) {
        late = k;
        lateAvg = avg;
        lateN = n;
      }
    });
    if (early != null && teamAvg - earlyAvg >= 4.0) {
      return "a(z) $early posztjuk fejez be a leghamarabb: átlag "
          "${earlyAvg.toStringAsFixed(1)} mp ($earlyN lövés, csapat-átlag "
          "${teamAvg.toStringAsFixed(1)} mp) · a visszarendeződésnél kell "
          "rá ember";
    }
    if (late != null && lateAvg - teamAvg >= 4.0) {
      return "a(z) $late posztjuk a támadás végén lő: átlag "
          "${lateAvg.toStringAsFixed(1)} mp ($lateN lövés, csapat-átlag "
          "${teamAvg.toStringAsFixed(1)} mp) · a kivárt labdára kell "
          "koncentrálni";
    }
    return null;
  }

  // Poszt-lövéstávolság: melyik posztjuk milyen messziről fejez be
  // (8+ lövés, posztonként 4+, 2 m eltérés — a backenddel azonos
  // küszöbök: RSD_MIN_SHOTS, RSD_GAP_M).
  String? _shotDistanceRole(Map<String, dynamic> r) {
    final shots = (r["rsd_shots_by_role"] as Map?)?.cast<String, dynamic>();
    final sums = (r["rsd_dist_sum_by_role"] as Map?)?.cast<String, dynamic>();
    if (shots == null || shots.isEmpty || sums == null) return null;
    var total = 0;
    var totalM = 0.0;
    shots.forEach((k, v) => total += (v as num).toInt());
    sums.forEach((k, v) => totalM += (v as num).toDouble());
    if (total < 8) return null;
    final teamAvg = totalM / total;
    String? near, far;
    var nearAvg = 0.0, farAvg = 0.0;
    var nearN = 0, farN = 0;
    shots.forEach((k, v) {
      final n = (v as num).toInt();
      if (n < 4) return;
      final avg = ((sums[k] as num?) ?? 0).toDouble() / n;
      if (near == null || avg < nearAvg) {
        near = k;
        nearAvg = avg;
        nearN = n;
      }
      if (far == null || avg > farAvg) {
        far = k;
        farAvg = avg;
        farN = n;
      }
    });
    if (near != null && teamAvg - nearAvg >= 2.0) {
      return "a(z) $near posztjuk jön be a legközelebb: átlag "
          "${nearAvg.toStringAsFixed(1)} m ($nearN lövés, csapat-átlag "
          "${teamAvg.toStringAsFixed(1)} m) · őt ki kell zárni";
    }
    if (far != null && farAvg - teamAvg >= 2.0) {
      return "a(z) $far posztjuk távolról fejez be: átlag "
          "${farAvg.toStringAsFixed(1)} m ($farN lövés, csapat-átlag "
          "${teamAvg.toStringAsFixed(1)} m) · rá lehet engedni";
    }
    return null;
  }

  // Poszt-eladási zóna: kinek az eladása hív kontrát (10+ eladás,
  // posztonként 5+, 20 százalékpont eltérés — a backenddel azonos
  // küszöbök).
  String? _turnoverZoneRole(Map<String, dynamic> r) {
    final tos = (r["rtz_to_by_role"] as Map?)?.cast<String, dynamic>();
    final front = (r["rtz_front_by_role"] as Map?)?.cast<String, dynamic>();
    if (tos == null || tos.isEmpty || front == null) return null;
    var total = 0;
    var totalFront = 0;
    tos.forEach((k, v) => total += (v as num).toInt());
    front.forEach((k, v) => totalFront += (v as num).toInt());
    if (total < 10) return null;
    final teamPct = 100.0 * totalFront / total;
    String? worst;
    var worstPct = 0.0;
    var worstN = 0;
    var worstF = 0;
    tos.forEach((k, v) {
      final n = (v as num).toInt();
      if (n < 5) return;
      final f = ((front[k] as num?) ?? 0).toInt();
      final pct = 100.0 * f / n;
      if (pct > worstPct) {
        worstPct = pct;
        worst = k;
        worstN = n;
        worstF = f;
      }
    });
    if (worst == null || worstPct - teamPct < 20.0) return null;
    return "a(z) $worst posztjuk eladásainak ${worstPct.round()}%-a "
        "($worstF/$worstN) a támadó harmadban történik (csapat-átlag "
        "${teamPct.round()}%) · onnan indul a kontra";
  }

  // Poszt-labdatartás: melyik posztnál áll meg a labda (16+ szakasz,
  // posztonként 8+, 0,7 mp eltérés — a backenddel azonos küszöbök).
  String? _holdTimeRole(Map<String, dynamic> r) {
    final holds = (r["rht_holds_by_role"] as Map?)?.cast<String, dynamic>();
    final frames = (r["rht_frames_by_role"] as Map?)?.cast<String, dynamic>();
    if (holds == null || holds.isEmpty || frames == null) return null;
    var totalHolds = 0;
    var totalFrames = 0;
    holds.forEach((k, v) => totalHolds += (v as num).toInt());
    frames.forEach((k, v) => totalFrames += (v as num).toInt());
    if (totalHolds < 16) return null;
    final teamAvg = totalFrames / totalHolds / 25.0;
    String? slow;
    var slowAvg = 0.0;
    var slowN = 0;
    holds.forEach((k, v) {
      final n = (v as num).toInt();
      if (n < 8) return;
      final avg = ((frames[k] as num?) ?? 0).toInt() / n / 25.0;
      if (avg > slowAvg) {
        slowAvg = avg;
        slow = k;
        slowN = n;
      }
    });
    if (slow == null || slowAvg - teamAvg < 0.7) return null;
    return "a(z) $slow posztjuknál áll meg a labda "
        "(${slowAvg.toStringAsFixed(1)} mp/érintés, csapat-átlag "
        "${teamAvg.toStringAsFixed(1)} mp, $slowN szakasz) · ő a "
        "kettőzés célpontja";
  }

  // Poszt-átvételi zóna: hol veszi át a labdát az egyes posztjuk
  // (16+ átvétel, posztonként 8+, 1,5 m eltérés — a backenddel azonos
  // küszöbök).
  String? _receiveZone(Map<String, dynamic> r) {
    final cnt = (r["rrz_recv_by_role"] as Map?)?.cast<String, dynamic>();
    final sum = (r["rrz_dist_sum_by_role"] as Map?)?.cast<String, dynamic>();
    if (cnt == null || cnt.isEmpty || sum == null) return null;
    var total = 0;
    var distTotal = 0.0;
    cnt.forEach((k, v) => total += (v as num).toInt());
    sum.forEach((k, v) => distTotal += (v as num).toDouble());
    if (total < 16) return null;
    final teamAvg = distTotal / total;
    String? best;
    var bestAvg = 0.0;
    var bestN = 0;
    cnt.forEach((k, v) {
      final n = (v as num).toInt();
      if (n < 8) return;
      final avg = ((sum[k] as num?) ?? 0).toDouble() / n;
      if (best == null || avg < bestAvg) {
        best = k;
        bestAvg = avg;
        bestN = n;
      }
    });
    if (best == null || teamAvg - bestAvg < 1.5) return null;
    return "a(z) $best posztjuk ${bestAvg.toStringAsFixed(1)} m-en veszi "
        "át a labdát (csapat-átlag ${teamAvg.toStringAsFixed(1)} m, "
        "$bestN átvétel) · az elé állás késő, a bejátszás vonalát zárd";
  }

  // Poszt-passzháló: melyik vonalon jár a legtöbb passzuk (20+ passz,
  // 30%-os részarány — a backenddel azonos küszöbök).
  String? _passLane(Map<String, dynamic> r) {
    final lanes = (r["rpm_lanes"] as Map?)?.cast<String, dynamic>();
    if (lanes == null || lanes.isEmpty) return null;
    var total = 0;
    String? top;
    var topN = 0;
    lanes.forEach((k, v) {
      final n = (v as num).toInt();
      total += n;
      if (n > topN) {
        topN = n;
        top = k;
      }
    });
    if (total < 20 || top == null) return null;
    final pct = (100.0 * topN / total).round();
    if (pct < 30) return null;
    return "a poszthoz kötött passzaik $pct%-a a(z) $top vonalon megy "
        "($topN/$total) · az elfogás is itt a legvalószínűbb";
  }

  // Poszt-birtoklás: melyik poszt tartja a labdát (250+ kocka, 55%-os
  // részarány — a backenddel azonos küszöbök).
  String? _possessionRole(Map<String, dynamic> r) {
    final byRole = (r["rps_frames_by_role"] as Map?)?.cast<String, dynamic>();
    if (byRole == null || byRole.isEmpty) return null;
    var total = 0;
    String? top;
    var topN = 0;
    byRole.forEach((k, v) {
      final n = (v as num).toInt();
      total += n;
      if (n > topN) {
        topN = n;
        top = k;
      }
    });
    if (total < 250 || top == null) return null;
    final pct = (100.0 * topN / total).round();
    if (pct < 55) return null;
    return "szervezett támadásban a labda idejének $pct%-át a(z) $top "
        "tartja · a letámadásnak legyen kijelölt címzettje";
  }

  // Poszt-állás: melyik posztra szűkül a hátrány-befejezésük (mindkét
  // oldalon 4+ gól, 20 százalékpont eltérés — a backenddel azonos
  // küszöbök).
  String? _trailingFinisher(Map<String, dynamic> r) {
    final trail = (r["rbs_trailing"] as Map?)?.cast<String, dynamic>();
    final rest = (r["rbs_rest"] as Map?)?.cast<String, dynamic>();
    if (trail == null || rest == null) return null;
    var n1 = 0;
    var n2 = 0;
    trail.forEach((k, v) => n1 += (v as num).toInt());
    rest.forEach((k, v) => n2 += (v as num).toInt());
    if (n1 < 4 || n2 < 4) return null;
    String? best;
    var bestGap = 0.0;
    var bestTrail = 0.0;
    var bestRest = 0.0;
    for (final k in {...trail.keys, ...rest.keys}) {
      final q1 = 100.0 * (((trail[k] as num?) ?? 0).toInt()) / n1;
      final q2 = 100.0 * (((rest[k] as num?) ?? 0).toInt()) / n2;
      if (best == null || (q1 - q2).abs() > bestGap.abs()) {
        best = k;
        bestGap = q1 - q2;
        bestTrail = q1;
        bestRest = q2;
      }
    }
    if (best == null || bestGap < 20.0) return null;
    return "hátrányban a(z) $best posztra szűkül a befejezésük "
        "(${bestTrail.round()}% vs ${bestRest.round()}%) · szoros "
        "hajrában ezt a vonalat zárd le";
  }

  // Eladás-ár poszt szerint: melyik posztjukat érdemes letámadni
  // (posztonként 4+ eladás, 35%-os büntetett arány — a backenddel
  // azonos küszöbök).
  String? _turnoverCostRole(Map<String, dynamic> r) {
    final tos = (r["rtc_to_by_role"] as Map?)?.cast<String, dynamic>();
    final pun = (r["rtc_punished_by_role"] as Map?)?.cast<String, dynamic>();
    if (tos == null || tos.isEmpty || pun == null) return null;
    String? worst;
    var worstPct = 0.0;
    var worstN = 0;
    var worstP = 0;
    tos.forEach((k, v) {
      final n = (v as num).toInt();
      if (n < 4) return;
      final p = ((pun[k] as num?) ?? 0).toInt();
      final pct = 100.0 * p / n;
      if (pct > worstPct) {
        worstPct = pct;
        worst = k;
        worstN = n;
        worstP = p;
      }
    });
    if (worst == null || worstPct < 35.0) return null;
    return "a(z) $worst posztjuk eladásait ${worstPct.round()}%-ban "
        "gyors gól követi ($worstP/$worstN) · oda irányítsd a "
        "letámadást, ott a legnagyobb a hozam";
  }

  // Poszt-váltás a szünetre: melyik posztra állnak rá a második
  // félidőben (félidőnként 4+ gól, 20 százalékpont eltérés — a
  // backenddel azonos küszöbök).
  String? _halftimeRoleShift(Map<String, dynamic> r) {
    final first = (r["rss_first"] as Map?)?.cast<String, dynamic>();
    final second = (r["rss_second"] as Map?)?.cast<String, dynamic>();
    if (first == null || second == null) return null;
    var n1 = 0;
    var n2 = 0;
    first.forEach((k, v) => n1 += (v as num).toInt());
    second.forEach((k, v) => n2 += (v as num).toInt());
    if (n1 < 4 || n2 < 4) return null;
    String? best;
    var bestGap = 0.0;
    var bestFirst = 0.0;
    var bestSecond = 0.0;
    for (final k in {...first.keys, ...second.keys}) {
      final p1 = 100.0 * (((first[k] as num?) ?? 0).toInt()) / n1;
      final p2 = 100.0 * (((second[k] as num?) ?? 0).toInt()) / n2;
      if (best == null || (p2 - p1).abs() > bestGap.abs()) {
        best = k;
        bestGap = p2 - p1;
        bestFirst = p1;
        bestSecond = p2;
      }
    }
    if (best == null || bestGap.abs() < 20.0) return null;
    final dir = bestGap > 0 ? "nő" : "csökken";
    return "a szünet után a(z) $best szerepe $dir a befejezésükben "
        "(${bestFirst.round()}% → ${bestSecond.round()}%) · az "
        "átrendeződésre a félidőben készülj, ne a második kapott gól után";
  }

  // Gólpassz-tengely: melyik poszt-vonalon esnek a góljaik (4+ pár,
  // 40%-os részarány — a backenddel azonos küszöbök).
  String? _assistAxis(Map<String, dynamic> r) {
    final pairs = (r["arp_pairs"] as Map?)?.cast<String, dynamic>();
    if (pairs == null || pairs.isEmpty) return null;
    var total = 0;
    String? top;
    var topN = 0;
    pairs.forEach((k, v) {
      final n = (v as num).toInt();
      total += n;
      if (n > topN) {
        topN = n;
        top = k;
      }
    });
    if (total < 4 || top == null) return null;
    final pct = (100.0 * topN / total).round();
    if (pct < 40) return null;
    return "a gólpasszos góljaik $pct%-a a(z) $top vonalon esik "
        "($topN/$total) · ezt az egy vonalat vágd el, ne két embert fogj";
  }

  // Poszt-hatékonyság: melyik posztjukra lehet ráengedni a lövést
  // (10+ lövés, posztonként 5+, 15 százalékpont eltérés — a
  // backenddel azonos küszöbök).
  String? _roleEfficiency(Map<String, dynamic> r) {
    final shots = (r["ser_shots_by_role"] as Map?)?.cast<String, dynamic>();
    final goals = (r["ser_goals_by_role"] as Map?)?.cast<String, dynamic>();
    if (shots == null || shots.isEmpty || goals == null) return null;
    var total = 0;
    var totalGoals = 0;
    shots.forEach((k, v) => total += (v as num).toInt());
    goals.forEach((k, v) => totalGoals += (v as num).toInt());
    if (total < 10) return null;
    final teamPct = 100.0 * totalGoals / total;
    String? worst;
    var worstPct = 101.0;
    var worstShots = 0;
    var worstGoals = 0;
    shots.forEach((k, v) {
      final n = (v as num).toInt();
      if (n < 5) return;
      final g = ((goals[k] as num?) ?? 0).toInt();
      final pct = 100.0 * g / n;
      if (pct < worstPct) {
        worstPct = pct;
        worst = k;
        worstShots = n;
        worstGoals = g;
      }
    });
    if (worst == null || teamPct - worstPct < 15.0) return null;
    return "a(z) $worst posztjukról csak ${worstPct.round()}% megy be "
        "($worstGoals/$worstShots lövés, csapat-átlag "
        "${teamPct.round()}%) · oda engedd a lövést, a többi vonalat zárd";
  }

  // Kiosztás-célpont: kihez megy a labda a betörés után (4+ kiosztás,
  // 55%-os koncentráció — a backenddel azonos küszöbök).
  String? _kickoutTarget(Map<String, dynamic> r) {
    final total = ((r["kot_kickouts"] as num?) ?? 0).toInt();
    final targets = (r["kot_targets"] as Map?)?.cast<String, dynamic>();
    if (total < 4 || targets == null || targets.isEmpty) return null;
    String? top;
    var topN = 0;
    targets.forEach((k, v) {
      final c = (v as num).toInt();
      if (c > topN) {
        topN = c;
        top = k;
      }
    });
    if (top == null) return null;
    final pct = (100.0 * topN / total).round();
    if (pct < 55) {
      return "változatos a kiosztásuk a betörés után ($total kiosztás, "
          "a legtöbbet kapó is csak $pct%) · passz-olvasásra ne építs, "
          "magát a betörést állítsd meg";
    }
    return "a betörés után a labda $pct%-ban a(z) $top játékoshoz megy "
        "($topN/$total kiosztás) · az ő védője álljon be a passzsávba, "
        "a betörőre pedig induljon a kettőzés";
  }

  // Teendő-rangsor: honnan jön a legtöbb jelzés (4+ jelzés, 2+ egy
  // családban — a backenddel azonos küszöbök).
  String? _priorityFocus(Map<String, dynamic> r) {
    final fams = (r["prf_families"] as Map?)?.cast<String, dynamic>();
    if (fams == null || fams.isEmpty) return null;
    var total = 0;
    String? top;
    var topN = 0;
    fams.forEach((k, v) {
      final c = (v as num).toInt();
      total += c;
      if (c > topN) {
        topN = c;
        top = k;
      }
    });
    if (total < 4 || topN < 2 || top == null) return null;
    const hu = {
      "ár": "a hibáik megfizetett ára",
      "ember": "néven nevezhető emberi minták",
      "szünet": "a szünet utáni átrendeződésük",
      "fáradás": "az időbeli visszaesésük",
      "állás": "az eredményjelző-függő szokásaik",
    };
    return "a róluk gyűlt $total jelzésből $topN ide mutat: "
        "${hu[top] ?? top} · a felkészülés súlypontját is ide tedd";
  }

  // Befejező-váltás: egymás utáni befejezések ugyanattól (8+ lövés,
  // 35/10%-os ismétlés — a backenddel azonos küszöbök).
  String? _finisherRotation(Map<String, dynamic> r) {
    final shots = ((r["frt_shots"] as num?) ?? 0).toInt();
    final repeats = ((r["frt_repeats"] as num?) ?? 0).toInt();
    if (shots < 8) return null;
    final pct = 100.0 * repeats / (shots - 1);
    if (pct >= 35.0) {
      return "ugyanaz fejez be sorozatban "
          "(${pct.toStringAsFixed(0)}% ismétlés $shots lövésből) · a "
          "lövőjükre a következő támadásban is számíts: korai "
          "kilépés, kettőzés";
    }
    if (pct <= 10.0) {
      return "jól rotálják a befejezést "
          "(${pct.toStringAsFixed(0)}% ismétlés) · emberfogás ellenük "
          "nem működik: sáv- és falmunka kell";
    }
    return null;
  }

  // Gól-minta: ismétlődő gól-ujjlenyomat (3+ azonos minta, 40%-os
  // részarány — a backenddel azonos küszöbök).
  String? _goalPatterns(Map<String, dynamic> r) {
    final goals = ((r["gpt_goals"] as num?) ?? 0).toInt();
    final patterns =
        (r["gpt_patterns"] as Map?)?.cast<String, dynamic>();
    if (goals < 3 || patterns == null || patterns.isEmpty) return null;
    String? top;
    int topN = 0;
    patterns.forEach((k, v) {
      final c = (v as num).toInt();
      if (c > topN) {
        topN = c;
        top = k;
      }
    });
    if (top == null || topN < 3 || 100.0 * topN / goals < 40.0) {
      return null;
    }
    return "a góljaik egy képre járnak: $top ($topN/$goals) · azt az "
        "egy mintát fogd meg: kilépő védő a sávba, blokk arra a kézre";
  }

  // Kettős emberhátrány: négyfős játék mérlege (2+ kapott gól vagy
  // 20+ mp gól nélkül — a backenddel azonos küszöbök).
  String? _doubleShorthand(Map<String, dynamic> r) {
    final seconds = ((r["dsh_seconds"] as num?) ?? 0).toDouble();
    final conceded = ((r["dsh_conceded"] as num?) ?? 0).toInt();
    if (conceded >= 2) {
      return "a kettős emberhátrány végzetes nekik ($conceded kapott "
          "gól ${seconds.toStringAsFixed(0)} mp négyfős játékból) · "
          "az emberhátrányukban a második kiállítás is kiprovokálható";
    }
    if (seconds >= 20.0 && conceded == 0) {
      return "a kettős hátrányt is túlélik "
          "(${seconds.toStringAsFixed(0)} mp gól nélkül) · az "
          "emberelőnyt végig kell játszani: maguktól nem esnek szét";
    }
    return null;
  }

  // Létszám-hiba: csere-átfedés, hetedik ember a pályán (2+ ablak —
  // a backenddel azonos küszöb).
  String? _excessPlayers(Map<String, dynamic> r) {
    final windows = ((r["xsp_windows"] as num?) ?? 0).toInt();
    if (windows < 2) return null;
    return "a cseréik átfednek ($windows ablakban hetedik "
        "mezőnyjátékos a pályán) · a váltás-pillanatuk kettős "
        "célpont: jelezd a zsűrinek, és gyors labda a "
        "rendezetlenségbe";
  }

  // Felzárkózás-húzó: kiugró hátrány-termelés (3+ részvétel, 2x-es
  // arány — a backenddel azonos küszöbök).
  String? _comebackCarriers(Map<String, dynamic> r) {
    final players = (r["cbc_players"] as List?) ?? const [];
    for (final p in players) {
      final m = (p as Map).cast<String, dynamic>();
      final tr = ((m["trailing"] as num?) ?? 0).toInt();
      final rest = ((m["rest"] as num?) ?? 0).toInt();
      if (tr >= 3 && tr >= 2 * (rest < 1 ? 1 : rest)) {
        return "a(z) ${m["player_id"]}. hozza őket vissza hátrányból "
            "($tr gól-részvétel hátrányban, máskor $rest) · ha "
            "vezetsz, őt fogd ki: szoros fogás, korai kettőzés";
      }
    }
    return null;
  }

  // Eltűnő védő: első félidei szerzés+blokk, második félidei csend
  // (3+ akció, 3x-os arány — a backenddel azonos küszöbök).
  String? _fadingDefenders(Map<String, dynamic> r) {
    final players = (r["fdd_players"] as List?) ?? const [];
    for (final p in players) {
      final m = (p as Map).cast<String, dynamic>();
      final fh = ((m["fh"] as num?) ?? 0).toInt();
      final sh = ((m["sh"] as num?) ?? 0).toInt();
      if (fh >= 3 && fh >= 3 * (sh < 1 ? 1 : sh)) {
        return "a(z) ${m["player_id"]}. védőjük viszi az első félidőt "
            "($fh szerzés+blokk), aztán leáll ($sh) · a 2. félidőben "
            "az ő zónáján át támadj";
      }
    }
    return null;
  }

  // Sprint-állás: hátrányban megugró sprint-ütem (60+ mp mindkét
  // oldalon, 8+ sprint, 1,5x ütem — a backenddel azonos küszöbök).
  String? _sprintsByScore(Map<String, dynamic> r) {
    final trS = ((r["spb_tr_seconds"] as num?) ?? 0).toDouble();
    final trN = ((r["spb_tr_sprints"] as num?) ?? 0).toInt();
    final restS = ((r["spb_rest_seconds"] as num?) ?? 0).toDouble();
    final restN = ((r["spb_rest_sprints"] as num?) ?? 0).toInt();
    if (trS < 60.0 || restS < 60.0 || trN < 8) return null;
    final trRate = 60.0 * trN / trS;
    final restRate = 60.0 * restN / restS;
    if (trRate < 1.5 * (restRate > 0 ? restRate : 1e-9)) return null;
    return "hátrányban sprintbe menekülnek "
        "(${trRate.toStringAsFixed(1)} sprint/perc a szokásos "
        "${restRate.toStringAsFixed(1)} helyett) · ha vezetsz, "
        "járasd: minden perc az ő lábukat fogyasztja";
  }

  // Eltűnő ember: első félidei gól-részvétel, második félidei csend
  // (3+ részvétel, 3x-os arány — a backenddel azonos küszöbök).
  String? _fadingScorers(Map<String, dynamic> r) {
    final players = (r["fdr_players"] as List?) ?? const [];
    for (final p in players) {
      final m = (p as Map).cast<String, dynamic>();
      final fh = ((m["fh"] as num?) ?? 0).toInt();
      final sh = ((m["sh"] as num?) ?? 0).toInt();
      if (fh >= 3 && fh >= 3 * (sh < 1 ? 1 : sh)) {
        return "a(z) ${m["player_id"]}. az első félidőben él "
            "($fh gól-részvétel), a másodikban eltűnik ($sh) · az "
            "első 30 percben fogd duplán, friss őrzővel";
      }
    }
    return null;
  }

  // Fekete ötperc: a visszatérően elúszó öt perces ablak (3+ gólos
  // összesített bukás — a backenddel azonos küszöb).
  String? _blackWindow(Map<String, dynamic> r) {
    final scored = (r["blw_scored"] as Map?)?.cast<String, dynamic>();
    final conceded =
        (r["blw_conceded"] as Map?)?.cast<String, dynamic>();
    final keys = <String>{
      ...?scored?.keys,
      ...?conceded?.keys,
    };
    String? worst;
    var worstDiff = 0;
    for (final b in keys) {
      final d = ((scored?[b] as num?) ?? 0).toInt() -
          ((conceded?[b] as num?) ?? 0).toInt();
      if (d < worstDiff) {
        worst = b;
        worstDiff = d;
      }
    }
    if (worst == null || worstDiff > -3) return null;
    final sc = ((scored?[worst] as num?) ?? 0).toInt();
    final co = ((conceded?[worst] as num?) ?? 0).toInt();
    return "a fekete ötpercük a $worst. perc (összesítve $sc-$co) · "
        "oda időzítsd a nyomást: friss sor, letámadás, gyors "
        "középkezdés";
  }

  // Oldal-váltás a szünetre: más fő szárny a két félidőben
  // (félidőnként 100+ kocka, 40%-os fő oldal — a backenddel azonos).
  String? _attackSideShift(Map<String, dynamic> r) {
    String? mainOf(Map<String, dynamic>? counts, int n) {
      if (counts == null || counts.isEmpty || n < 100) return null;
      String? best;
      int bestN = 0;
      counts.forEach((k, v) {
        final c = (v as num).toInt();
        if (c > bestN) {
          bestN = c;
          best = k;
        }
      });
      if (best == null || 100.0 * bestN / n < 40.0) return null;
      return best;
    }

    final fh = mainOf(
        (r["sds_fh_counts"] as Map?)?.cast<String, dynamic>(),
        ((r["sds_fh_frames"] as num?) ?? 0).toInt());
    final sh = mainOf(
        (r["sds_sh_counts"] as Map?)?.cast<String, dynamic>(),
        ((r["sds_sh_frames"] as num?) ?? 0).toInt());
    if (fh == null || sh == null || fh == sh) return null;
    return "a szünet után oldalt váltanak ($fh → $sh) · a 2. félidő "
        "elején olvasd újra a súlypontot: erős védő és kettőzés az "
        "új oldalra";
  }

  // Fal-váltás a szünetre: más fő forma a két félidőben (félidőnként
  // 5+ címkézett védekezés, 60%-os uralkodó forma — a backenddel
  // azonos küszöbök).
  String? _defenseFormShift(Map<String, dynamic> r) {
    String? mainOf(Map<String, dynamic>? labels, int n) {
      if (labels == null || labels.isEmpty || n < 5) return null;
      String? best;
      int bestN = 0;
      labels.forEach((k, v) {
        final c = (v as num).toInt();
        if (c > bestN) {
          bestN = c;
          best = k;
        }
      });
      if (best == null || 100.0 * bestN / n < 60.0) return null;
      return best;
    }

    final fh = mainOf(
        (r["dfs_fh_labels"] as Map?)?.cast<String, dynamic>(),
        ((r["dfs_fh_attacks"] as num?) ?? 0).toInt());
    final sh = mainOf(
        (r["dfs_sh_labels"] as Map?)?.cast<String, dynamic>(),
        ((r["dfs_sh_attacks"] as num?) ?? 0).toInt());
    if (fh == null || sh == null || fh == sh) return null;
    return "a szünet után falat váltanak ($fh → $sh) · két kész "
        "figurasorral érkezz, a szünet utáni első támadásnál hangos "
        "forma-bemondás";
  }

  // Passz-hossz-állás: hátrányban hosszú labdázás (állapotonként 10+
  // passz, 12 pp többlet — a backenddel azonos küszöbök).
  String? _passLengthByScore(Map<String, dynamic> r) {
    final trP = ((r["pls_tr_passes"] as num?) ?? 0).toInt();
    final trL = ((r["pls_tr_long"] as num?) ?? 0).toInt();
    final restP = ((r["pls_rest_passes"] as num?) ?? 0).toInt();
    final restL = ((r["pls_rest_long"] as num?) ?? 0).toInt();
    if (trP < 10 || restP < 10) return null;
    final diff = 100.0 * trL / trP - 100.0 * restL / restP;
    if (diff < 12.0) return null;
    return "hátrányban hosszú labdákra váltanak "
        "(+${diff.toStringAsFixed(0)} pp hosszú passz hátrányban) · "
        "ha vezetsz, ülj a passzsávokra: az átdobált labda elfogható";
  }

  // Kapus-gólpassz: a kapus keze gólt indít (2+ — a backenddel
  // azonos küszöb).
  String? _gkAssists(Map<String, dynamic> r) {
    final assists = ((r["gka_assists"] as num?) ?? 0).toInt();
    if (assists < 2) return null;
    return "a kapusuk indítása gólpasszt ér ($assists kapus-gólpassz) "
        "· a lövésed pillanatában induljon a visszafutás: az első "
        "hazafutó a kapus-passz sávját vágja el";
  }

  // Passz-irány-állás: előnyben hátrajáratás (állapotonként 10+
  // passz, 12 pp többlet — a backenddel azonos küszöbök).
  String? _passDirectionByScore(Map<String, dynamic> r) {
    final leadP = ((r["pds_lead_passes"] as num?) ?? 0).toInt();
    final leadB = ((r["pds_lead_back"] as num?) ?? 0).toInt();
    final restP = ((r["pds_rest_passes"] as num?) ?? 0).toInt();
    final restB = ((r["pds_rest_back"] as num?) ?? 0).toInt();
    if (leadP < 10 || restP < 10) return null;
    final diff = 100.0 * leadB / leadP - 100.0 * restB / restP;
    if (diff < 12.0) return null;
    return "előnyben hátrafelé járatják a labdát "
        "(+${diff.toStringAsFixed(0)} pp hátra-passz vezetésnél) · "
        "ha ők vezetnek: magas letámadás, az első hátrapassz a jel";
  }

  // Szünet-váltás: a támadás-mix átrendeződése (félidőnként 6+
  // támadás, 30/10 pp küszöb — a backenddel azonos, a mix a
  // lerohanás+gyors indítás részarányából becsülve).
  String? _attackMixShift(Map<String, dynamic> r) {
    final fhA = ((r["ams_fh_attacks"] as num?) ?? 0).toInt();
    final shA = ((r["ams_sh_attacks"] as num?) ?? 0).toInt();
    if (fhA < 6 || shA < 6) return null;
    final fhB = ((r["ams_fh_break"] as num?) ?? 0).toInt();
    final shB = ((r["ams_sh_break"] as num?) ?? 0).toInt();
    final fhQ = ((r["ams_fh_quick"] as num?) ?? 0).toInt();
    final shQ = ((r["ams_sh_quick"] as num?) ?? 0).toInt();
    final shift = ((100.0 * fhB / fhA - 100.0 * shB / shA).abs() +
            (100.0 * fhQ / fhA - 100.0 * shQ / shA).abs()) /
        2.0;
    if (shift >= 30.0) {
      return "a szünet után átrendezik a támadójátékukat "
          "(~${shift.toStringAsFixed(0)} pp mix-váltás) · a "
          "szünetedben a váltásukra készülj, ne a folytatásra";
    }
    if (shift <= 10.0) {
      return "félidőn át ugyanazt játsszák (alig mozduló támadás-mix) "
          "· egy jól előkészített védő-terv kitart 60 percen át";
    }
    return null;
  }

  // Lepattanó-esés: a hajrára elfogyó második roham (félidőnként 3+
  // lehetőség, 25 pp esés — a backenddel azonos küszöbök).
  String? _secondChanceFade(Map<String, dynamic> r) {
    final fhM = ((r["scf_fh_misses"] as num?) ?? 0).toInt();
    final fhW = ((r["scf_fh_won"] as num?) ?? 0).toInt();
    final shM = ((r["scf_sh_misses"] as num?) ?? 0).toInt();
    final shW = ((r["scf_sh_won"] as num?) ?? 0).toInt();
    if (fhM < 3 || shM < 3) return null;
    final fhPct = 100.0 * fhW / fhM;
    final shPct = 100.0 * shW / shM;
    if (fhPct - shPct < 25.0) return null;
    return "a hajrára elfogy a lepattanó-harcuk (visszaharcolt "
        "lepattanó ${fhPct.toStringAsFixed(0)}% → "
        "${shPct.toStringAsFixed(0)}%) · záráskor a blokk utáni "
        "labda a tiéd";
  }

  // Gólpassz-esés: a hajrában megálló labda (félidőnként 3+ gól,
  // 25 pp esés — a backenddel azonos küszöbök).
  String? _assistFade(Map<String, dynamic> r) {
    final fhG = ((r["asf_fh_goals"] as num?) ?? 0).toInt();
    final fhA = ((r["asf_fh_assisted"] as num?) ?? 0).toInt();
    final shG = ((r["asf_sh_goals"] as num?) ?? 0).toInt();
    final shA = ((r["asf_sh_assisted"] as num?) ?? 0).toInt();
    if (fhG < 3 || shG < 3) return null;
    final fhPct = 100.0 * fhA / fhG;
    final shPct = 100.0 * shA / shG;
    if (fhPct - shPct < 25.0) return null;
    return "a hajrában megáll náluk a labda (gólpasszos gól "
        "${fhPct.toStringAsFixed(0)}% → ${shPct.toStringAsFixed(0)}%) "
        "· a 2. félidőben dupla nyomás a labdás emberre";
  }

  // Kapus-sorozat: rákapó kapus (6+ kapura lövés, 2+ hármas széria —
  // a backenddel azonos küszöbök).
  String? _gkSaveStreaks(Map<String, dynamic> r) {
    final onTarget = ((r["gst_on_target"] as num?) ?? 0).toInt();
    final streaks = ((r["gst_streaks"] as num?) ?? 0).toInt();
    if (onTarget < 6 || streaks < 2) return null;
    return "ha rákap, sorozatban véd a kapusuk ($streaks hármas "
        "védés-széria $onTarget kapura lövésből) · két védése után "
        "válts lövés-képet: más zóna, más ritmus";
  }

  // 7a6-állás: mikor vállalják az üres kaput (3+ szakasz, 2-es
  // többlet — a backenddel azonos küszöbök).
  String? _emptyNetByScore(Map<String, dynamic> r) {
    final tr = ((r["ens_tr"] as num?) ?? 0).toInt();
    final lead = ((r["ens_lead"] as num?) ?? 0).toInt();
    final level = ((r["ens_level"] as num?) ?? 0).toInt();
    final total = tr + lead + level;
    if (total < 3) return null;
    if ((lead + level) - tr >= 2) {
      return "a 7 a 6 náluk rendszer, nem mentőöv ($total üres-kapus "
          "szakaszból $tr hátrányban) · minden szerzés után az első "
          "nézés a túloldali üres kapu";
    }
    if (tr - (lead + level) >= 2) {
      return "csak hátrányban hozzák le a kapust ($tr/$total szakasz "
          "hátrányban) · ha vezetsz, számíts a 7 a 6-ra";
    }
    return null;
  }

  // Kontra-állás: hátrányban megugró lerohanás-arány (5+ támadás
  // állapotonként, 12 pp többlet — a backenddel azonos küszöbök).
  String? _breaksByScore(Map<String, dynamic> r) {
    final trA = ((r["bks_tr_attacks"] as num?) ?? 0).toInt();
    final trB = ((r["bks_tr_breaks"] as num?) ?? 0).toInt();
    final restA = ((r["bks_rest_attacks"] as num?) ?? 0).toInt();
    final restB = ((r["bks_rest_breaks"] as num?) ?? 0).toInt();
    if (trA < 5 || restA < 5) return null;
    final diff = 100.0 * trB / trA - 100.0 * restB / restA;
    if (diff < 12.0) return null;
    return "hátrányban kontrába menekülnek (+${diff.toStringAsFixed(0)} "
        "pp lerohanás-többlet hátrányban) · ha vezetsz, a "
        "visszafutás-fegyelem dönt: futni fognak";
  }

  // Hetes-állás: mikor harcolják ki a heteseket (3+ hetes, 2-es
  // hátrány-többlet — a backenddel azonos küszöbök).
  String? _sevensByScore(Map<String, dynamic> r) {
    final tr = ((r["svs_tr"] as num?) ?? 0).toInt();
    final lead = ((r["svs_lead"] as num?) ?? 0).toInt();
    final level = ((r["svs_level"] as num?) ?? 0).toInt();
    final total = tr + lead + level;
    if (total < 3 || tr - (lead + level) < 2) return null;
    return "hátrányban a hetes a menekülő-fegyverük ($tr/$total "
        "kiharcolt hetes hátrányban) · ha vezetsz, lábbal védekezz: "
        "a betörőjük a kezet keresi";
  }

  // Fegyelem-állás: kiállítások az állás szerint (3+ kiállítás, 2-es
  // többlet — a backenddel azonos küszöbök).
  String? _suspensionsByScore(Map<String, dynamic> r) {
    final tr = ((r["sps_tr"] as num?) ?? 0).toInt();
    final lead = ((r["sps_lead"] as num?) ?? 0).toInt();
    final level = ((r["sps_level"] as num?) ?? 0).toInt();
    final total = tr + lead + level;
    if (total < 3) return null;
    if (tr - (lead + level) >= 2) {
      return "hátrányban elszáll a fegyelmük ($tr/$total kiállítás "
          "hátrányban) · ha vezettek, vállald a kontaktot: a "
          "frusztrációjuk kiállítást terem";
    }
    if (lead - (tr + level) >= 2) {
      return "előnyben szabálytalankodnak ($lead/$total kiállítás "
          "vezetésnél) · ha ők vezetnek, védd a betörőt: jön az ütés";
    }
    return null;
  }

  // Kidobott labda: oldalvonalon elhagyott labdák (3+ — a backenddel
  // azonos küszöb).
  String? _ballsOut(Map<String, dynamic> r) {
    final out = ((r["obt_out"] as num?) ?? 0).toInt();
    if (out < 3) return null;
    return "sok kidobott labda ($out oldalvonalon elhagyott labda) · "
        "szorítsd a labdásukat az oldalvonalra: a szélső sávban "
        "pontatlanok";
  }

  // Elhúzódó támadás ára: üresen zárulnak-e a hosszú akcióik (3+
  // hosszú akció, 25% alatti gól-arány — a backenddel azonos küszöb).
  String? _slowAttackCost(Map<String, dynamic> r) {
    final slow = ((r["sac_slow"] as num?) ?? 0).toInt();
    final scored = ((r["sac_scored"] as num?) ?? 0).toInt();
    if (slow < 3) return null;
    final pct = 100.0 * scored / slow;
    if (pct <= 25.0) {
      return "az elhúzódó támadásaik üresen zárulnak ($scored/$slow "
          "hosszú akció ért gólt) · türelmes védekezéssel a passzív "
          "jel nektek dolgozik";
    }
    if (pct >= 60.0) {
      return "a hosszú akcióikat is gólra váltják ($scored/$slow) · "
          "a 35. másodpercben is teljes koncentráció a falban";
    }
    return null;
  }

  // Csere-lyukak: csere közbeni öt fős másodpercek (20+ mp — a
  // backend-kulccsal azonos küszöb).
  String? _subGaps(Map<String, dynamic> r) {
    final gapS = ((r["sbg_gap_s"] as num?) ?? 0).toDouble();
    if (gapS < 20.0) return null;
    return "lyukas a cseréjük (${gapS.toStringAsFixed(0)} mp öt fős "
        "játék csere közben) · a cseréjük pillanata támadási jel: "
        "gyors középkezdés, amíg öten vannak";
  }

  // Gólpassz-hossz: hosszú indítás vagy rövid kombináció (5+
  // gólpasszos gól; 50% felett hosszú, 20% alatt rövid — a
  // backend-kulccsal azonos küszöbök).
  String? _assistRanges(Map<String, dynamic> r) {
    final assisted = ((r["asr_assisted"] as num?) ?? 0).toInt();
    final long = ((r["asr_long"] as num?) ?? 0).toInt();
    if (assisted < 5) return null;
    final pct = 100.0 * long / assisted;
    if (pct >= 50.0) {
      return "hosszú gólpasszokból élnek ($long/$assisted "
          "előkészítés 8 m-en túlról) · a passzsávakat zárjátok, a "
          "hosszú labda elfogható";
    }
    if (pct <= 20.0) {
      return "rövid kombinációkból élnek (csak $long/$assisted "
          "hosszú előkészítés) · a kis terület védése dönt, hangos "
          "váltásokkal";
    }
    return null;
  }

  // Kapus-kipattanó: fogja vagy kiüti a labdát (4+ mért védés; 70%
  // felett fogó, 40% alatt kiütő — a backend-kulccsal azonos
  // küszöbök).
  String? _gkReboundControl(Map<String, dynamic> r) {
    final saves = ((r["grc_saves"] as num?) ?? 0).toInt();
    final caught = ((r["grc_caught"] as num?) ?? 0).toInt();
    if (saves < 4) return null;
    final pct = 100.0 * caught / saves;
    if (pct <= 40.0) {
      return "kiüti a labdát a kapusuk (csak $caught/$saves védés "
          "maradt nála) · kijelölt kipattanó-vadász maradjon a "
          "hatosnál minden lövés után";
    }
    if (pct >= 70.0) {
      return "fogja a labdát a kapusuk ($caught/$saves védés nála) · "
          "a lövés pillanatában már indulni kell hátra";
    }
    return null;
  }

  // Kivárás-csapda: mi lesz a hosszú támadásaikból (5+ hosszú
  // támadás; 40% felett elhaló, 15% alatt lövésig érő — a
  // backend-kulccsal azonos küszöbök).
  String? _longAttackOutcomes(Map<String, dynamic> r) {
    final n = ((r["lao_n"] as num?) ?? 0).toInt();
    final died = ((r["lao_died"] as num?) ?? 0).toInt();
    if (n < 5) return null;
    final pct = 100.0 * died / n;
    if (pct >= 40.0) {
      return "a hosszú támadásaik elhalnak ($died/$n lövés nélkül) · "
          "a kivárás nekik csapda, a passzív jel felétek dolgozik";
    }
    if (pct <= 15.0) {
      return "a hosszú támadásaik is lövésig érnek (csak $died/$n "
          "halt el) · korai megzavarás kell, a kivárás nem véd";
    }
    return null;
  }

  // Felfutási létszám: hány emberrel támadnak (100+ kocka; 5,5 felett
  // mindenki fent, 4,5 alatt biztosítás — a backend-kulccsal azonos
  // küszöbök).
  String? _attackHeadcount(Map<String, dynamic> r) {
    final frames = ((r["ahc_frames"] as num?) ?? 0).toInt();
    final sum = ((r["ahc_sum_up"] as num?) ?? 0).toDouble();
    if (frames < 100) return null;
    final avg = sum / frames;
    if (avg >= 5.5) {
      return "mindenkit felküldenek (átlag ${avg.toStringAsFixed(1)} "
          "mezőnyjátékos fent) · a hátuk mögött üres a pálya, minden "
          "szerzés kontrát ér";
    }
    if (avg <= 4.5) {
      return "biztosítva támadnak (átlag ${avg.toStringAsFixed(1)} "
          "fent) · kontra nehéz, de a fal bátran kettőzhet ellenük";
    }
    return null;
  }

  // Blokk-lepattanó: a blokk után ki szerzi meg a labdát (4+ blokk;
  // 60% felett teljes értékű, 30% alatt visszahulló — a
  // backend-kulccsal azonos küszöbök).
  String? _blockRecoveries(Map<String, dynamic> r) {
    final blocks = ((r["brc_blocks"] as num?) ?? 0).toInt();
    final rec = ((r["brc_recovered"] as num?) ?? 0).toInt();
    if (blocks < 4) return null;
    final pct = 100.0 * rec / blocks;
    if (pct >= 60.0) {
      return "a blokk után a labdát is megszerzik ($rec/$blocks "
          "lepattanó) · a blokkjukba lőtt labda labdavesztés, "
          "mellette kell ellőni";
    }
    if (pct <= 30.0) {
      return "a blokkjaik visszahullanak (csak $rec/$blocks "
          "lepattanó az övék) · blokkolt lövés után azonnal "
          "támadjatok újra";
    }
    return null;
  }

  // Ziccer-befejezők: ki értékesíti a nagy helyzeteket (3+ ziccer;
  // 80% felett biztos, 40% alatt bizonytalan — a backend-kulccsal
  // azonos küszöbök).
  String? _bigChanceFinishers(Map<String, dynamic> r) {
    final rows = r["bcf_players"];
    if (rows is! List || rows.isEmpty) return null;
    final acc = <int, List<int>>{};
    for (final pr in rows) {
      if (pr is! Map<String, dynamic>) continue;
      final pid = ((pr["player_id"] as num?) ?? 0).toInt();
      final rec = acc.putIfAbsent(pid, () => [0, 0]);
      rec[0] += ((pr["chances"] as num?) ?? 0).toInt();
      rec[1] += ((pr["goals"] as num?) ?? 0).toInt();
    }
    final pids = acc.keys.toList()
      ..sort((a, b) => acc[b]![0].compareTo(acc[a]![0]));
    for (final pid in pids) {
      final c = acc[pid]![0];
      final g = acc[pid]![1];
      if (c < 3) continue;
      final pct = 100.0 * g / c;
      if (pct >= 80.0) {
        return "ziccer-biztos befejezőjük a(z) $pid azonosítójú "
            "($g/$c nagy helyzet) · a helyzetet már a kialakulása "
            "előtt kell megelőzni";
      }
      if (pct <= 40.0) {
        return "a(z) $pid azonosítójú a ziccereket is kihagyja "
            "($g/$c) · vállalható, hogy inkább őt engeditek "
            "helyzetbe";
      }
    }
    return null;
  }

  // Hetes utáni percek: leragadnak-e az adott hetes után (3+ hetes,
  // 2+ további kapott gól — a backend-kulccsal azonos küszöbök).
  String? _postSevenLapses(Map<String, dynamic> r) {
    final sevens = ((r["psl_sevens"] as num?) ?? 0).toInt();
    final extra = ((r["psl_extra"] as num?) ?? 0).toInt();
    if (sevens < 3 || extra < 2) return null;
    return "a hetes utáni percben is büntethetők ($sevens adott "
        "hetes után $extra további kapott gól) · a hetesetek utáni "
        "támadást is kész figurával játsszátok meg";
  }

  // Labda-forgatás iránya: merre járatják a labdát (20+ oldalpassz,
  // 60% részarány — a backend-kulccsal azonos küszöbök).
  String? _circulationDirection(Map<String, dynamic> r) {
    final left = ((r["cir_left"] as num?) ?? 0).toInt();
    final right = ((r["cir_right"] as num?) ?? 0).toInt();
    final total = left + right;
    if (total < 20) return null;
    final lp = 100.0 * left / total;
    if (lp < 60.0 && lp > 40.0) return null;
    final dir = lp >= 60.0 ? "balra" : "jobbra";
    final pct = (lp >= 60.0 ? lp : 100 - lp).toStringAsFixed(0);
    return "egy irányba forgatnak ($dir megy az oldalpasszaik "
        "$pct%-a) · kettőzés a forgás végpontján, terelés az "
        "ellenirányba";
  }

  // Elzárás-páros: ki zár kinek (3+ közös lövés — a backend-kulccsal
  // azonos küszöb).
  String? _screenPairs(Map<String, dynamic> r) {
    final rows = r["scp_pairs"];
    if (rows is! List || rows.isEmpty) return null;
    final acc = <String, int>{};
    for (final pr in rows) {
      if (pr is! Map<String, dynamic>) continue;
      final key = "${pr["setter_id"]}→${pr["shooter_id"]}";
      acc[key] = (acc[key] ?? 0) + ((pr["shots"] as num?) ?? 0).toInt();
    }
    String? topKey;
    var topN = 0;
    acc.forEach((k, n) {
      if (n > topN) {
        topKey = k;
        topN = n;
      }
    });
    if (topKey == null || topN < 3) return null;
    return "bejáratott elzárás-párosuk van ($topKey, $topN közös "
        "lövés) · párban védekezzetek: korai kilépés az elzárás elé";
  }

  // Szélső-kifutás: időben érnek-e ki a szélső lövéseire (4+ lövés;
  // 2,5 m felett késői, 1,2 m alatt zárt — a backend-kulccsal azonos
  // küszöbök).
  String? _wingCloseouts(Map<String, dynamic> r) {
    final shots = ((r["wco_shots"] as num?) ?? 0).toInt();
    final sum = ((r["wco_sum_m"] as num?) ?? 0).toDouble();
    if (shots < 4) return null;
    final avg = sum / shots;
    if (avg >= 2.5) {
      return "későn érnek ki a szélre (átlag "
          "${avg.toStringAsFixed(1)} m-re a védő a lövő szélsőtől) · "
          "gyors oldalváltásokkal a szélsőitekre hordjatok labdát";
    }
    if (avg <= 1.2) {
      return "zárják a szélsőt (átlag ${avg.toStringAsFixed(1)} m) · "
          "a szélső-bejátszás zsákutca, a beállót keressétek";
    }
    return null;
  }

  // Csend-törők: ki töri meg a gólcsendjüket (2+ törés — a
  // backend-kulccsal azonos küszöb).
  String? _droughtBreakers(Map<String, dynamic> r) {
    final rows = r["drb_players"];
    if (rows is! List || rows.isEmpty) return null;
    final per = <int, int>{};
    for (final pr in rows) {
      if (pr is! Map<String, dynamic>) continue;
      final pid = ((pr["player_id"] as num?) ?? 0).toInt();
      per[pid] = (per[pid] ?? 0) + ((pr["breaks"] as num?) ?? 0).toInt();
    }
    int? topPid;
    var topN = 0;
    per.forEach((pid, n) {
      if (n > topN) {
        topPid = pid;
        topN = n;
      }
    });
    if (topPid == null || topN < 2) return null;
    return "van válság-lövőjük (a(z) $topPid azonosítójú, $topN "
        "csend-törés) · a sorozatotok alatt őt fogjátok a "
        "legszorosabban";
  }

  // Forró kéz: van-e sorozatlövőjük (2+ sorozat vagy 3+ hosszú — a
  // backend-kulccsal azonos küszöbök).
  String? _hotHands(Map<String, dynamic> r) {
    final rows = r["hh_streaks"];
    if (rows is! List || rows.isEmpty) return null;
    final per = <int, List<int>>{};
    for (final st in rows) {
      if (st is! Map<String, dynamic>) continue;
      final pid = ((st["player_id"] as num?) ?? 0).toInt();
      final len = ((st["length"] as num?) ?? 0).toInt();
      final rec = per.putIfAbsent(pid, () => [0, 0]);
      rec[0] += 1;
      if (len > rec[1]) rec[1] = len;
    }
    int? topPid;
    List<int>? top;
    per.forEach((pid, rec) {
      if (rec[0] < 2 && rec[1] < 3) return;
      if (top == null ||
          rec[0] > top![0] ||
          (rec[0] == top![0] && rec[1] > top![1])) {
        topPid = pid;
        top = rec;
      }
    });
    if (topPid == null) return null;
    return "van sorozatlövőjük (a(z) $topPid azonosítójú, "
        "${top![0]} gólsorozat, leghosszabb: ${top![1]}) · az első "
        "gólja után azonnal őrzés-váltás vagy kettőzés";
  }

  // Kapus-hidegedés: hideg kézzel beesik-e a védése (vödrönként 4+
  // lövés, 15 százalékpont — a backend-kulccsal azonos küszöbök).
  String? _gkColdStreaks(Map<String, dynamic> r) {
    final cF = ((r["gcs_cold_faced"] as num?) ?? 0).toInt();
    final wF = ((r["gcs_warm_faced"] as num?) ?? 0).toInt();
    if (cF < 4 || wF < 4) return null;
    final c = 100.0 * ((r["gcs_cold_saves"] as num?) ?? 0).toInt() / cF;
    final w = 100.0 * ((r["gcs_warm_saves"] as num?) ?? 0).toInt() / wF;
    if (w - c >= 15.0) {
      return "hidegen sebezhető a kapusuk (csend után "
          "${c.toStringAsFixed(0)}%, ritmusban "
          "${w.toStringAsFixed(0)}%) · éheztessétek, és a csend "
          "végén jöjjön a kidolgozott lövés";
    }
    if (c - w >= 15.0) {
      return "hidegen is stabil a kapusuk "
          "(${c.toStringAsFixed(0)}% csend után) · az éheztetés nem "
          "működik, ritmusból kell kizökkenteni";
    }
    return null;
  }

  // Fal-magasság elleni játék: megbüntetik-e a felfutó falat
  // (vödrönként 5+ támadás, 20 százalékpont — a backend-kulccsal
  // azonos küszöbök).
  String? _attackVsWallHeight(Map<String, dynamic> r) {
    final hA = ((r["avw_high_attacks"] as num?) ?? 0).toInt();
    final dA = ((r["avw_deep_attacks"] as num?) ?? 0).toInt();
    if (hA < 5 || dA < 5) return null;
    final h = 100.0 * ((r["avw_high_goals"] as num?) ?? 0).toInt() / hA;
    final d = 100.0 * ((r["avw_deep_goals"] as num?) ?? 0).toInt() / dA;
    if (h - d <= -20.0) {
      return "a felfutó fal megfogja őket (magas fal ellen "
          "${h.toStringAsFixed(0)}%, mély ellen "
          "${d.toStringAsFixed(0)}%) · bátran lépjetek ki, nincs "
          "válaszuk a nyomásra";
    }
    if (h - d >= 20.0) {
      return "a felfutó falat megbüntetik (${h.toStringAsFixed(0)}% "
          "vs ${d.toStringAsFixed(0)}%) · ellenük a mély, kompakt "
          "fal a biztonságos terv";
    }
    return null;
  }

  // Kontra-forrás: miből indul a lerohanásuk (4+ lerohanás, 50%
  // részarány — a backend-kulccsal azonos küszöbök).
  String? _breakSources(Map<String, dynamic> r) {
    final src = r["bsrc_sources"];
    if (src is! Map) return null;
    var total = 0;
    String? top;
    var topN = 0;
    var tie = false;
    src.forEach((k, v) {
      final n = ((v as num?) ?? 0).toInt();
      total += n;
      if (n > topN) {
        top = k.toString();
        topN = n;
        tie = false;
      } else if (n == topN && n > 0) {
        tie = true;
      }
    });
    if (total < 4 || top == null || tie) return null;
    if (100.0 * topN / total < 50.0) return null;
    return "a kontráik főleg ebből indulnak: $top ($topN/$total "
        "lerohanás) · ezt az egy pillanatot kell megölni a "
        "visszarendeződésben";
  }

  // Kapus-gól veszély: rádob-e a kapusuk az üres kapura (1+ kísérlet
  // — a backend-kulccsal azonos küszöb).
  String? _gkGoalThreat(Map<String, dynamic> r) {
    final att = ((r["gkg_attempts"] as num?) ?? 0).toInt();
    final goals = ((r["gkg_goals"] as num?) ?? 0).toInt();
    if (att < 1) return null;
    return "gólveszélyes a kapusuk ($att kapura dobás, $goals gól) · "
        "a 7 a 6 alatt kijelölt visszafutó kell a kapu síkjába";
  }

  // Hosszú állás utáni játék: kizökkenti-e őket (2+ hosszú
  // megszakítás, 2 gólos különbség — a backend-kulccsal azonos
  // küszöbök).
  String? _longBreakResponse(Map<String, dynamic> r) {
    final breaks = ((r["lbr_breaks"] as num?) ?? 0).toInt();
    final gf = ((r["lbr_for"] as num?) ?? 0).toInt();
    final ga = ((r["lbr_against"] as num?) ?? 0).toInt();
    if (breaks < 2) return null;
    if (gf - ga <= -2) {
      return "a hosszú állások kizökkentik őket ($gf-$ga a "
          "megszakítások utáni mérlegük) · minden sérülés-szünet a "
          "ti pillanatotok, kész figurával gyertek ki";
    }
    if (gf - ga >= 2) {
      return "a hosszú állások után meglódulnak ($gf-$ga) · az "
          "újraindítás utáni első védekezés extra figyelmet kapjon";
    }
    return null;
  }

  // Hajrá-labdabirtoklás: egy kézben van-e a végjáték (200+ hajrá-
  // kocka, 35% részesedés — a backend-kulccsal azonos küszöbök).
  String? _clutchBallHogs(Map<String, dynamic> r) {
    final frames = ((r["cbh_frames"] as num?) ?? 0).toInt();
    final rows = r["cbh_players"];
    if (frames < 200 || rows is! List || rows.isEmpty) return null;
    Map<String, dynamic>? top;
    for (final pr in rows) {
      if (pr is Map<String, dynamic> &&
          (top == null ||
              ((pr["frames"] as num?) ?? 0) >
                  ((top["frames"] as num?) ?? 0))) {
        top = pr;
      }
    }
    if (top == null) return null;
    final topF = ((top["frames"] as num?) ?? 0).toInt();
    if (100.0 * topF / frames < 35.0) return null;
    return "egy kézben van a végjátékuk (a(z) ${top["player_id"]} "
        "azonosítójú viszi a hajrá labdás idejét) · a hajrá-kettőzés "
        "név szerint rá menjen";
  }

  // Negyedóra-profil: melyik meccs-szakasz az övék (40+ mért perc,
  // 3 gólos negyedóra-különbség — a backend-kulccsal azonos
  // küszöbök).
  String? _quarterProfile(Map<String, dynamic> r) {
    final mins = ((r["qp_min"] as num?) ?? 0).toDouble();
    final qFor = r["qp_for"];
    final qAg = r["qp_against"];
    if (mins < 40.0 || qFor is! Map || qAg is! Map) return null;
    String? bestQ;
    var bestD = -999;
    String? worstQ;
    var worstD = 999;
    for (final q in ["1", "2", "3", "4"]) {
      final d = (((qFor[q] as num?) ?? 0).toInt()) -
          (((qAg[q] as num?) ?? 0).toInt());
      if (d > bestD) {
        bestD = d;
        bestQ = q;
      }
      if (d < worstD) {
        worstD = d;
        worstQ = q;
      }
    }
    if (bestD >= 3) {
      return "a(z) $bestQ. negyedóra az övék (+$bestD gólkülönbség) · "
          "az erős szakaszuk előtt jöjjön a saját időkérés és a "
          "friss sor";
    }
    if (worstD <= -3) {
      return "a(z) $worstQ. negyedórában esnek szét ($worstD) · oda "
          "kell tempót és friss cseréket időzíteni";
    }
    return null;
  }

  // Beálló-őr: ki őrzi a beállót (300+ őrzés-kocka, 60% részesedés —
  // a backend-kulccsal azonos küszöbök).
  String? _pivotGuards(Map<String, dynamic> r) {
    final frames = ((r["pvg_frames"] as num?) ?? 0).toInt();
    final rows = r["pvg_guards"];
    if (frames < 300 || rows is! List || rows.isEmpty) return null;
    Map<String, dynamic>? top;
    for (final pr in rows) {
      if (pr is Map<String, dynamic> &&
          (top == null ||
              ((pr["frames"] as num?) ?? 0) >
                  ((top["frames"] as num?) ?? 0))) {
        top = pr;
      }
    }
    if (top == null) return null;
    final topF = ((top["frames"] as num?) ?? 0).toInt();
    if (100.0 * topF / frames < 60.0) return null;
    return "egy ember őrzi a beállót (a(z) ${top["player_id"]} "
        "azonosítójú) · az elzárást rá kell vinni, mögötte "
        "felszabadul a beálló";
  }

  // Időkérés-csomag: az időkérés cserével jár-e (2+ időkérés, 70%
  // arány — a backend-kulccsal azonos küszöbök).
  String? _timeoutSubCombo(Map<String, dynamic> r) {
    final touts = ((r["tsc_timeouts"] as num?) ?? 0).toInt();
    final withSubs = ((r["tsc_with_subs"] as num?) ?? 0).toInt();
    if (touts < 2) return null;
    final pct = 100.0 * withSubs / touts;
    if (pct >= 70.0) {
      return "az időkérésük cserével jár ($withSubs/$touts) · utána "
          "frissítsétek a párosítást, friss lábú ember érkezik";
    }
    if (pct <= 30.0) {
      return "az időkérésük tiszta taktika ($touts időkérés, szinte "
          "csere nélkül) · az utána jövő első támadásnál a fal "
          "extra figyelmet kapjon";
    }
    return null;
  }

  // Lövés-választás állás szerint: hátrányban elkapkodják-e
  // (állapotonként 5+ lövés, 0,08 xG-különbség — a backend-kulccsal
  // azonos küszöbök).
  String? _shotQualityByScore(Map<String, dynamic> r) {
    final tN = ((r["sqs_trail_shots"] as num?) ?? 0).toInt();
    final oN = ((r["sqs_other_shots"] as num?) ?? 0).toInt();
    if (tN < 5 || oN < 5) return null;
    final t = ((r["sqs_trail_sum_xg"] as num?) ?? 0).toDouble() / tN;
    final o = ((r["sqs_other_sum_xg"] as num?) ?? 0).toDouble() / oN;
    if (o - t >= 0.08) {
      return "hátrányban elkapkodják a lövéseket "
          "(${o.toStringAsFixed(2)} → ${t.toStringAsFixed(2)} "
          "helyzet-átlag) · vezetésnél a rossz lövéseik nektek "
          "dolgoznak";
    }
    if (t - o >= 0.08) {
      return "hátrányban is türelmesek "
          "(${t.toStringAsFixed(2)} helyzet-átlag hátrányban is) · a "
          "vezetés ellenük sosem biztonságos";
    }
    return null;
  }

  // Kapus állás szerint: hátrányban feljavul-e (állapotonként 4+
  // kapura tartó lövés, 15 százalékpont — a backend-kulccsal azonos
  // küszöbök).
  String? _gkSavesByScore(Map<String, dynamic> r) {
    final tF = ((r["gks_trail_faced"] as num?) ?? 0).toInt();
    final oF = ((r["gks_other_faced"] as num?) ?? 0).toInt();
    if (tF < 4 || oF < 4) return null;
    final t = 100.0 * ((r["gks_trail_saves"] as num?) ?? 0).toInt() / tF;
    final o = 100.0 * ((r["gks_other_saves"] as num?) ?? 0).toInt() / oF;
    if (t - o >= 15.0) {
      return "hátrányban feljavul a kapusuk "
          "(${t.toStringAsFixed(0)}% a szokásos "
          "${o.toStringAsFixed(0)}% helyett) · vezetésnél csak "
          "kidolgozott helyzetet lőjetek rá";
    }
    if (o - t >= 15.0) {
      return "hátrányban összeesik a kapusuk (csak "
          "${t.toStringAsFixed(0)}%) · vezetésnél bátran jöhet a "
          "távoli lövés is";
    }
    return null;
  }

  // Szorult játék: hátrányban mennyire húzzák szét a pályát (100+
  // kocka mindkét állapotban, 2 m különbség — a backend-kulccsal
  // azonos küszöbök).
  String? _widthByScore(Map<String, dynamic> r) {
    final tN = ((r["wbs_trail_frames"] as num?) ?? 0).toInt();
    final oN = ((r["wbs_other_frames"] as num?) ?? 0).toInt();
    if (tN < 100 || oN < 100) return null;
    final t = ((r["wbs_trail_sum_m"] as num?) ?? 0).toDouble() / tN;
    final o = ((r["wbs_other_sum_m"] as num?) ?? 0).toDouble() / oN;
    if (o - t >= 2.0) {
      return "hátrányban beszűkülnek (${o.toStringAsFixed(0)} → "
          "${t.toStringAsFixed(0)} m) · vezetésnél tömörítsétek a "
          "falat, a szélsőik kikapcsolódnak";
    }
    if (t - o >= 2.0) {
      return "hátrányban kinyílnak (${o.toStringAsFixed(0)} → "
          "${t.toStringAsFixed(0)} m) · vezetésnél a szélső-védelem "
          "és a kifutás dönt";
    }
    return null;
  }

  // Visszaállás: mi történik a kiállítás letelte után (2+ mért
  // visszaállás, 2 gólos különbség — a backend-kulccsal azonos
  // küszöbök).
  String? _postPowerplay(Map<String, dynamic> r) {
    final returns = ((r["ppp_returns"] as num?) ?? 0).toInt();
    final gf = ((r["ppp_for"] as num?) ?? 0).toInt();
    final ga = ((r["ppp_against"] as num?) ?? 0).toInt();
    if (returns < 2) return null;
    if (gf - ga <= -2) {
      return "a visszaállásnál megzavarodnak (a kiállítás utáni perc "
          "mérlege $gf-$ga) · a lejáró kiállításuk a ti "
          "támadás-jelzésetek";
    }
    if (gf - ga >= 2) {
      return "a visszaálló emberrel feltámadnak ($gf-$ga) · a "
          "visszaérés utáni első támadásukat kell megfogni";
    }
    return null;
  }

  // Poszt-hibák: melyik poszt veszíti el a labdát (6+ eladás, 40%
  // részarány, holtverseny nélkül — a backend-kulccsal azonos
  // küszöbök).
  String? _turnoversByRole(Map<String, dynamic> r) {
    final roles = r["tbr_roles"];
    if (roles is! Map) return null;
    var total = 0;
    String? topPost;
    var topN = 0;
    var tie = false;
    roles.forEach((k, v) {
      final n = ((v as num?) ?? 0).toInt();
      total += n;
      if (n > topN) {
        topPost = k.toString();
        topN = n;
        tie = false;
      } else if (n == topN && n > 0) {
        tie = true;
      }
    });
    if (total < 6 || topPost == null || tie) return null;
    if (100.0 * topN / total < 40.0) return null;
    return "a labdaeladásaik a(z) $topPost posztról jönnek "
        "($topN/$total eladás) · ott érdemes zavarni, oda menjen a "
        "kettőzés";
  }

  // Futás-mérleg: melyik csapat futja túl a másikat (10+ mért perc,
  // 10% táv-többlet — a backend-kulccsal azonos küszöbök).
  String? _distanceBattle(Map<String, dynamic> r) {
    final own = ((r["dbt_m"] as num?) ?? 0).toDouble();
    final opp = ((r["dbt_opp_m"] as num?) ?? 0).toDouble();
    final mins = ((r["dbt_min"] as num?) ?? 0).toDouble();
    if (mins < 10.0 || own <= 0 || opp <= 0) return null;
    final perMin = (own / mins).toStringAsFixed(0);
    if (own >= opp * 1.10) {
      return "túlfutják az ellenfeleiket ($perMin m/perc) · nem "
          "szabad futóversenyt vállalni: lassított tempó, felállt "
          "fal";
    }
    if (own <= opp * 0.90) {
      return "túlfutja őket az ellenfél (csak $perMin m/perc) · a "
          "tempó a fegyver: gyors középkezdés, korai indítások";
    }
    return null;
  }

  // Egyirányú játékosok: váltott sorokkal játszanak-e (1500+ kocka,
  // 75% fázis-részarány — a backend-kulccsal azonos küszöbök).
  String? _phaseSpecialists(Map<String, dynamic> r) {
    final rows = r["phs_players"];
    if (rows is! List) return null;
    int? defId;
    int? atkId;
    for (final pr in rows) {
      if (pr is! Map<String, dynamic>) continue;
      final frames = ((pr["frames"] as num?) ?? 0).toInt();
      if (frames < 1500) continue;
      final defShare =
          100.0 * ((pr["def_frames"] as num?) ?? 0).toInt() / frames;
      final pid = ((pr["player_id"] as num?) ?? 0).toInt();
      if (defShare >= 75.0) defId ??= pid;
      if (defShare <= 25.0) atkId ??= pid;
    }
    if (defId == null || atkId == null) return null;
    return "váltott sorokkal játszanak (a(z) $defId azonosítójú csak "
        "védekezik, a(z) $atkId csak támad) · a csere pillanatában "
        "gyors középkezdéssel büntethetők";
  }

  // Sprint-veszély: ki viszi a kontrát (10+ csapat-sprint, 30%
  // részesedés — a backend-kulccsal azonos küszöbök).
  String? _sprintThreats(Map<String, dynamic> r) {
    final rows = r["spt_players"];
    if (rows is! List || rows.isEmpty) return null;
    var total = 0;
    Map<String, dynamic>? top;
    for (final pr in rows) {
      if (pr is! Map<String, dynamic>) continue;
      final n = ((pr["sprints"] as num?) ?? 0).toInt();
      total += n;
      if (top == null || n > ((top["sprints"] as num?) ?? 0).toInt()) {
        top = pr;
      }
    }
    if (total < 10 || top == null) return null;
    final topN = ((top["sprints"] as num?) ?? 0).toInt();
    if (100.0 * topN / total < 30.0) return null;
    return "kijelölt kontra-emberük van (a(z) ${top["player_id"]} "
        "azonosítójú futotta a $total sprintből $topN-t) · névre "
        "szóló fékező-feladat, tilos őt a fal mögé engedni";
  }

  // Hetesre cserélt kapus: hoznak-e specialistát a büntetőkre (2+
  // célzott csere — a backend-kulccsal azonos küszöb).
  String? _sevenKeeperSwaps(Map<String, dynamic> r) {
    final sevens = ((r["svk_sevens"] as num?) ?? 0).toInt();
    final swaps = ((r["svk_swaps"] as num?) ?? 0).toInt();
    if (swaps < 2) return null;
    return "hetesre kapust cserélnek ($sevens büntetőből $swaps-t "
        "frissen beállt kapus várt) · a hetes-lövő a beugró kapus "
        "szokásaira készüljön, és várja ki a lövést";
  }

  // Kilépő védő: van-e előretolt ember a falban (3+ mért védő, 2,5 m
  // előny — a backend-kulccsal azonos küszöbök).
  String? _advancedDefender(Map<String, dynamic> r) {
    final rows = r["adv_players"];
    if (rows is! List) return null;
    final measured = <Map<String, dynamic>>[];
    for (final pr in rows) {
      if (pr is Map<String, dynamic> &&
          ((pr["frames"] as num?) ?? 0).toInt() >= 100) {
        measured.add(pr);
      }
    }
    if (measured.length < 3) return null;
    measured.sort((a, b) {
      final da = ((a["depth_sum_m"] as num?) ?? 0).toDouble() /
          ((a["frames"] as num?) ?? 1).toInt();
      final db = ((b["depth_sum_m"] as num?) ?? 0).toDouble() /
          ((b["frames"] as num?) ?? 1).toInt();
      return db.compareTo(da);
    });
    final top = measured.first;
    var oFrames = 0;
    var oSum = 0.0;
    for (final pr in measured.skip(1)) {
      oFrames += ((pr["frames"] as num?) ?? 0).toInt();
      oSum += ((pr["depth_sum_m"] as num?) ?? 0).toDouble();
    }
    if (oFrames == 0) return null;
    final gap = ((top["depth_sum_m"] as num?) ?? 0).toDouble() /
            ((top["frames"] as num?) ?? 1).toInt() -
        oSum / oFrames;
    if (gap < 2.5) return null;
    return "kilépő védővel játszanak (a(z) ${top["player_id"]} "
        "azonosítójú ${gap.toStringAsFixed(1)} m-rel a sor előtt) · "
        "elzárást rá, és a háta mögé befutó emberrel 2 az 1-et";
  }

  // Középkezdés-átvevő: kinél indul újra a játék (4+ újraindítás, 50%
  // részesedés — a backend-kulccsal azonos küszöbök).
  String? _restartTargets(Map<String, dynamic> r) {
    final restarts = ((r["rst_restarts"] as num?) ?? 0).toInt();
    final players = r["rst_players"];
    if (restarts < 4 || players is! List || players.isEmpty) return null;
    Map<String, dynamic>? top;
    for (final pr in players) {
      if (pr is Map<String, dynamic> &&
          (top == null ||
              ((pr["takes"] as num?) ?? 0) >
                  ((top["takes"] as num?) ?? 0))) {
        top = pr;
      }
    }
    if (top == null) return null;
    final takes = ((top["takes"] as num?) ?? 0).toInt();
    if (100.0 * takes / restarts < 50.0) return null;
    return "fix középkezdés-emberük van (a(z) ${top["player_id"]} "
        "azonosítójú vett át $takes/$restarts újraindítást) · a gól "
        "utáni letámadás névre szóló célpontja";
  }

  // Váltópárok: ki kit vált a cseréknél (4+ mért csere, 3+ ismétlődés
  // — a backend-kulccsal azonos küszöbök).
  String? _swapPairs(Map<String, dynamic> r) {
    final swaps = ((r["swp_swaps"] as num?) ?? 0).toInt();
    final pairs = r["swp_pairs"];
    if (swaps < 4 || pairs is! List || pairs.isEmpty) return null;
    Map<String, dynamic>? top;
    for (final pr in pairs) {
      if (pr is Map<String, dynamic> &&
          (top == null ||
              ((pr["count"] as num?) ?? 0) >
                  ((top["count"] as num?) ?? 0))) {
        top = pr;
      }
    }
    if (top == null || ((top["count"] as num?) ?? 0).toInt() < 3) {
      return null;
    }
    return "kiszámítható a váltópárjuk (a(z) ${top["out_id"]} "
        "azonosítójút rendre a(z) ${top["in_id"]} váltja, "
        "${top["count"]} alkalommal) · a beállóra kész B-terv "
        "legyen, már a csere előtt";
  }

  // Visszahozott támadások: lezárják vagy újrajáratják a betörést (6+
  // betörés; 45% felett türelmes, 15% alatt direkt — a
  // backend-kulccsal azonos küszöbök).
  String? _pullbackRate(Map<String, dynamic> r) {
    final entries = ((r["pb_entries"] as num?) ?? 0).toInt();
    final pulls = ((r["pb_pullbacks"] as num?) ?? 0).toInt();
    if (entries < 6) return null;
    final pct = 100.0 * pulls / entries;
    if (pct >= 45.0) {
      return "behúzzák, aztán visszahozzák ($entries betörésből "
          "$pulls visszahozás) · a fal kivárhat, a türelmes zárás "
          "passzív jelet ér";
    }
    if (pct <= 15.0) {
      return "az első betörésből lezárnak ($entries betörésből csak "
          "$pulls visszahozás) · az első belépést kell megállítani, "
          "korai besegítéssel";
    }
    return null;
  }

  // Szerzés utáni indítás: azonnal előre megy-e a szerzett labda (6+
  // szerzés; 60% felett azonnali, 25% alatt biztosító — a
  // backend-kulccsal azonos küszöbök).
  String? _stealLaunch(Map<String, dynamic> r) {
    final steals = ((r["stl_steals"] as num?) ?? 0).toInt();
    final fwd = ((r["stl_fwd"] as num?) ?? 0).toInt();
    if (steals < 6) return null;
    final pct = 100.0 * fwd / steals;
    if (pct >= 60.0) {
      return "szerzés után azonnal indítanak ($steals szerzésből "
          "$fwd megy rögtön előre) · labdavesztéskor kész terv kell: "
          "fékező ember, sprint hátra, semmi reklamálás";
    }
    if (pct <= 25.0) {
      return "szerzés után biztosítanak ($steals szerzésből csak "
          "$fwd megy előre) · labdavesztés után van idő rendezni a "
          "letámadást";
    }
    return null;
  }

  // Hetes-fáradás: mikor adják a heteseket (4+ adott hetes, 2-es
  // félidők közti többlet — a backend-kulccsal azonos küszöbök).
  String? _sevensFade(Map<String, dynamic> r) {
    final fh = ((r["s7f_fh"] as num?) ?? 0).toInt();
    final sh = ((r["s7f_sh"] as num?) ?? 0).toInt();
    if (fh + sh < 4) return null;
    if (sh - fh >= 2) {
      return "a második félidőben adják a heteseket ($fh az elsőben, "
          "$sh a másodikban) · a szünet után testre vitt labda "
          "hetest ér";
    }
    if (fh - sh >= 2) {
      return "az elején adják a heteseket ($fh az elsőben, $sh a "
          "másodikban) · az első percekben kell a beállóst és a "
          "betörést erőltetni";
    }
    return null;
  }

  // Fal-fáradás: melyik félidőben nyílik ki a fal (félidőnként 5+
  // kapott lövés, 0,08 xG-változás — a backend-kulccsal azonos
  // küszöbök).
  String? _wallFade(Map<String, dynamic> r) {
    final fhN = ((r["wf_fh_shots"] as num?) ?? 0).toInt();
    final shN = ((r["wf_sh_shots"] as num?) ?? 0).toInt();
    if (fhN < 5 || shN < 5) return null;
    final fh = ((r["wf_fh_sum_xga"] as num?) ?? 0).toDouble() / fhN;
    final sh = ((r["wf_sh_sum_xga"] as num?) ?? 0).toDouble() / shN;
    if (sh - fh >= 0.08) {
      return "a második félidőre kinyílik a faluk "
          "(${fh.toStringAsFixed(2)} → ${sh.toStringAsFixed(2)} "
          "kapott helyzet-átlag) · a belső játékot a második félidőre "
          "tartogassátok";
    }
    if (fh - sh >= 0.08) {
      return "a második félidőre áll össze a faluk "
          "(${fh.toStringAsFixed(2)} → ${sh.toStringAsFixed(2)}) · az "
          "első félidőben kell megszerezni az előnyt";
    }
    return null;
  }

  // Pad-gólok: a kispad is termel-e (6+ lövőhöz köthető gól; 35%
  // felett mély, 10% alatt csak-kezdők — a backend-kulccsal azonos
  // küszöbök).
  String? _benchScoring(Map<String, dynamic> r) {
    final goals = ((r["ben_goals"] as num?) ?? 0).toInt();
    final bench = ((r["ben_bench"] as num?) ?? 0).toInt();
    if (goals < 6) return null;
    final pct = 100.0 * bench / goals;
    if (pct <= 10.0) {
      return "csak a kezdőik termelnek ($goals gólból $bench a "
          "padról) · fárasztani kell őket: pörgetett tempóval a "
          "második félidőre elfogynak";
    }
    if (pct >= 35.0) {
      return "a kispaduk is termel (a góljaik "
          "${pct.toStringAsFixed(0)}%-a padról jön) · minden sorukra "
          "névre szóló párosítás-terv kell";
    }
    return null;
  }

  // Labdaszerzés-típus: elfogják vagy leszerelik a labdát (6+ szerzés;
  // 60% felett sáv-záró, 25% alatt testre menő — a backend-kulccsal
  // azonos küszöbök).
  String? _stealTypes(Map<String, dynamic> r) {
    final steals = ((r["stt_steals"] as num?) ?? 0).toInt();
    final ints = ((r["stt_int"] as num?) ?? 0).toInt();
    if (steals < 6) return null;
    final pct = 100.0 * ints / steals;
    if (pct >= 60.0) {
      return "a passzsávakat zárják ($steals szerzésből $ints "
          "elfogott passz) · keresztbe lebegtetni tilos, rövid "
          "passzok és betörések kellenek";
    }
    if (pct <= 25.0) {
      return "testre mennek szerelni ($steals szerzésből csak $ints "
          "elfogás) · gyors labdajáratással megelőzhető a kontakt, a "
          "keresztpassz vállalható";
    }
    return null;
  }

  // Kapott helyzetek minősége: milyen lövéseket enged a fal (8+ kapott
  // lövés; 0,35 felett nagy, 0,22 alatt nehéz helyzetek — a
  // backend-kulccsal azonos küszöbök).
  String? _concededChanceQuality(Map<String, dynamic> r) {
    final shots = ((r["ccq_shots"] as num?) ?? 0).toInt();
    final sum = ((r["ccq_sum_xga"] as num?) ?? 0).toDouble();
    if (shots < 8) return null;
    final avg = sum / shots;
    if (avg >= 0.35) {
      return "nagy helyzeteket engednek (a rájuk jövő $shots lövés "
          "átlaga ${avg.toStringAsFixed(2)}) · befelé kell játszani: "
          "beállós, áttörés, elzárás után kapott labda";
    }
    if (avg <= 0.22) {
      return "csak nehéz helyzeteket engednek (a rájuk jövő $shots "
          "lövés átlaga ${avg.toStringAsFixed(2)}) · a 9 méteres "
          "lövés ajándék nekik, embert kell kihúzni";
    }
    return null;
  }

  // Félidő-zárás: mit kezdenek a dudaszó előtti utolsó labdával (3+
  // záró támadás; 50% felett jó, 15% alatt elpuskázott — a
  // backend-kulccsal azonos küszöbök).
  String? _closingAttacks(Map<String, dynamic> r) {
    final att = ((r["clo_attacks"] as num?) ?? 0).toInt();
    final goals = ((r["clo_goals"] as num?) ?? 0).toInt();
    if (att < 3) return null;
    final pct = 100.0 * goals / att;
    if (pct >= 50.0) {
      return "jól kezelik a záró labdát ($att záró támadásból $goals "
          "gól) · a félidő végén ki kell húzni az órát, ne kapjanak "
          "még egy támadást";
    }
    if (pct <= 15.0) {
      return "elpuskázzák a záró labdát ($att záró támadásból csak "
          "$goals gól) · nyugodtan vissza lehet adni nekik az utolsó "
          "labdát";
    }
    return null;
  }

  // Lerohanás-hatékonyság: mennyi lesz gól a kontrákból (5+ lerohanás;
  // 65% felett éles, 35% alatt elpuskázott — a backend-kulccsal
  // azonos küszöbök).
  String? _fastBreakConversion(Map<String, dynamic> r) {
    final breaks = ((r["fbc_breaks"] as num?) ?? 0).toInt();
    final goals = ((r["fbc_goals"] as num?) ?? 0).toInt();
    if (breaks < 5) return null;
    final pct = 100.0 * goals / breaks;
    if (pct >= 65.0) {
      return "élesen fejezik be a kontrát ($breaks lerohanásból "
          "$goals gól) · kijelölt fékező ember kell, és lövés után "
          "senki ne maradjon elöl";
    }
    if (pct <= 35.0) {
      return "elpuskázzák a kontrát ($breaks lerohanásból csak "
          "$goals gól) · nyugodtan rájuk lehet engedni, a felállt "
          "támadásuk a veszélyesebb";
    }
    return null;
  }

  // Félidő-nyitás: hogyan indulnak a félidők első 5 percében (4+ gól
  // a nyitó ablakokban, 2 gól különbség — a backend-kulccsal azonos
  // küszöbök).
  String? _halfOpenings(Map<String, dynamic> r) {
    final gf = ((r["ho_for"] as num?) ?? 0).toInt();
    final ga = ((r["ho_against"] as num?) ?? 0).toInt();
    if (gf + ga < 4) return null;
    final diff = gf - ga;
    if (diff >= 2) {
      return "jól nyitják a félidőket ($gf-$ga a nyitó öt percekben) "
          "· az első öt percben biztos, hibátlan játék kell";
    }
    if (diff <= -2) {
      return "lassan indulnak ($gf-$ga a nyitó öt percekben) · pont "
          "az első öt percben kell rámenni a vezetésért";
    }
    return null;
  }

  // Időkérés utáni védekezés: megáll-e a fal a megszakítás után (3+
  // időkérés; 60% felett szivárgó, 20% alatt friss — a
  // backend-kulccsal azonos küszöbök).
  String? _timeoutDefense(Map<String, dynamic> r) {
    final n = ((r["tfd_timeouts"] as num?) ?? 0).toInt();
    final conceded = ((r["tfd_conceded"] as num?) ?? 0).toInt();
    if (n < 3) return null;
    final pct = 100.0 * conceded / n;
    if (pct >= 60.0) {
      return "időkérés után szivárog a faluk (az időkéréseik "
          "${pct.toStringAsFixed(0)}%-a után gól az első rohamból) · "
          "az újraindítás után azonnal támadni kell";
    }
    if (pct <= 20.0) {
      return "időkérés után friss a faluk (csak "
          "${pct.toStringAsFixed(0)}%-a után kaptak gólt) · ott a "
          "gyors roham veszteség, rendezetten kell felállni";
    }
    return null;
  }

  // Gól utáni letámadás: saját gól után feljebb megy-e a fal (60+
  // kocka mindkét oldalon, 1,5 m eltérés — a backend-kulccsal azonos
  // küszöbök).
  String? _pressAfterGoal(Map<String, dynamic> r) {
    final aN = ((r["pag_after_frames"] as num?) ?? 0).toInt();
    final bN = ((r["pag_base_frames"] as num?) ?? 0).toInt();
    if (aN < 60 || bN < 60) return null;
    final a = ((r["pag_after_sum_m"] as num?) ?? 0).toDouble() / aN;
    final b = ((r["pag_base_sum_m"] as num?) ?? 0).toDouble() / bN;
    if (a - b >= 1.5) {
      return "saját góljuk után letámadnak (${a.toStringAsFixed(1)} m "
          "a szokásos ${b.toStringAsFixed(1)} m helyett) · a kapott "
          "gól utáni kihozatalt előre meg kell tervezni";
    }
    if (b - a >= 1.5) {
      return "saját góljuk után visszahúzódnak "
          "(${a.toStringAsFixed(1)} m a szokásos "
          "${b.toStringAsFixed(1)} m helyett) · ilyenkor nyugodtan "
          "fel lehet hozni a labdát";
    }
    return null;
  }

  // Felhozatal-idő: milyen gyorsan érnek a támadó térfélre (5+ mért
  // felhozatal; 7 mp felett lassú, 4 mp alatt gyors — a
  // backend-kulccsal azonos küszöbök).
  String? _buildupTime(Map<String, dynamic> r) {
    final cases = ((r["but_cases"] as num?) ?? 0).toInt();
    final sumS = ((r["but_sum_s"] as num?) ?? 0).toDouble();
    if (cases < 5) return null;
    final avg = sumS / cases;
    if (avg >= 7.0) {
      return "lassan hozzák fel a labdát (átlag "
          "${avg.toStringAsFixed(1)} mp) · van idő rendezetten "
          "felállni: a fal szervezése dönt, nem a visszafutás";
    }
    if (avg <= 4.0) {
      return "gyorsan hozzák fel a labdát (átlag "
          "${avg.toStringAsFixed(1)} mp) · a lövés pillanatában "
          "indulni kell hátra, kell egy kijelölt fékező ember";
    }
    return null;
  }

  // Fedezetten lövők: ki lő nyomás alatt is (5+ lövés, 60% feletti
  // fedezett arány — a backend-kulccsal azonos küszöbök).
  String? _coveredShooters(Map<String, dynamic> r) {
    final rows = r["covered_shooters"];
    if (rows is! List || rows.isEmpty) return null;
    for (final e in rows) {
      if (e is! Map) continue;
      final shots = ((e["shots"] as num?) ?? 0).toInt();
      final covered = ((e["covered"] as num?) ?? 0).toInt();
      if (shots < 5) continue;
      final pct = 100.0 * covered / shots;
      if (pct < 60.0) continue;
      final who = e["jersey"] != null
          ? "${e["jersey"]}-es"
          : "${e["player_id"]} azonosítójú";
      return "a(z) $who játékosuk fedezetten is lő (a lövései "
          "${pct.toStringAsFixed(0)}%-a fedezett, $covered/$shots) · "
          "rá nem kell kilépni, elég a blokk-kéz";
    }
    return null;
  }

  // Pressz-érzékeny játékosok: ki veszíti el a labdát szorításban (5+
  // nyomott döntés, 30% feletti eladás-arány — a backend-kulccsal
  // azonos küszöbök).
  String? _pressurePlayers(Map<String, dynamic> r) {
    final rows = r["pressure_players"];
    if (rows is! List || rows.isEmpty) return null;
    for (final e in rows) {
      if (e is! Map) continue;
      final events = ((e["press_events"] as num?) ?? 0).toInt();
      final tos = ((e["press_to"] as num?) ?? 0).toInt();
      if (events < 5) continue;
      final pct = 100.0 * tos / events;
      if (pct < 30.0) continue;
      final who = e["jersey"] != null
          ? "${e["jersey"]}-es"
          : "${e["player_id"]} azonosítójú";
      return "a(z) $who játékosuk pressz-érzékeny (a nyomott döntései "
          "${pct.toStringAsFixed(0)}%-a eladás lett, $tos/$events) · "
          "rá kell küldeni a kettőzést";
    }
    return null;
  }

  // Elöl szerző védők: ki szed labdát a támadó térfélen (3+ szerzés,
  // 50% feletti elöl-arány — a backend-kulccsal azonos küszöbök).
  String? _highStealers(Map<String, dynamic> r) {
    final rows = r["high_stealers"];
    if (rows is! List || rows.isEmpty) return null;
    for (final e in rows) {
      if (e is! Map) continue;
      final steals = ((e["steals"] as num?) ?? 0).toInt();
      final high = ((e["high"] as num?) ?? 0).toInt();
      if (steals < 3) continue;
      if (100.0 * high / steals < 50.0) continue;
      final who = e["jersey"] != null
          ? "${e["jersey"]}-es"
          : "${e["player_id"]} azonosítójú";
      return "a(z) $who játékosuk elöl szedi a labdákat "
          "($high/$steals szerzés a támadó térfelükön) · az ő oldalán "
          "ne vezessétek a kihozatalt";
    }
    return null;
  }

  // Pontatlan lövők: kinek a lövései kerülik el a kaput (5+ lövés,
  // 40% feletti mellé-arány — a backend-kulccsal azonos küszöbök).
  String? _wastefulShooters(Map<String, dynamic> r) {
    final rows = r["wasteful_shooters"];
    if (rows is! List || rows.isEmpty) return null;
    for (final e in rows) {
      if (e is! Map) continue;
      final shots = ((e["shots"] as num?) ?? 0).toInt();
      final off = ((e["off_target"] as num?) ?? 0).toInt();
      if (shots < 5) continue;
      final pct = 100.0 * off / shots;
      if (pct < 40.0) continue;
      final who = e["jersey"] != null
          ? "${e["jersey"]}-es"
          : "${e["player_id"]} azonosítójú";
      return "a(z) $who játékosuk lövései elkerülik a kaput (a "
          "lövései ${pct.toStringAsFixed(0)}%-a, $off/$shots) · rá rá "
          "lehet engedni a lövést";
    }
    return null;
  }

  // Kezdő hatos: kikkel kezdenek (legalább négy kezdő ember — a
  // backend-kulccsal azonos küszöb).
  String? _openingLineup(Map<String, dynamic> r) {
    final rows = r["opening_players"];
    if (rows is! List || rows.length < 4) return null;
    final names = <String>[];
    for (final e in rows.take(6)) {
      if (e is! Map) continue;
      names.add(e["jersey"] != null
          ? "${e["jersey"]}-es"
          : "#${e["player_id"]}");
    }
    if (names.length < 4) return null;
    return "kezdő embereik: ${names.join(", ")} · az első támadásokra "
        "név szerinti terv készíthető";
  }

  // Hetes-kiharcolás poszt szerint: honnan jönnek a heteseik (3+
  // hetes, 50% feletti vezető poszt, holtverseny nélkül — a
  // backend-kulccsal azonos küszöbök).
  String? _sevenEarnerRoles(Map<String, dynamic> r) {
    final roles = r["seven_earner_roles"];
    if (roles is! Map || roles.isEmpty) return null;
    final rows = roles.entries
        .map((e) => [e.key.toString(), ((e.value as num?) ?? 0).toInt()])
        .toList()
      ..sort((a, b) => (b[1] as int).compareTo(a[1] as int));
    final total = rows.fold<int>(0, (s, e) => s + (e[1] as int));
    if (total < 3) return null;
    final top = rows.first[1] as int;
    if (rows.length > 1 && (rows[1][1] as int) == top) return null;
    final pct = 100.0 * top / total;
    if (pct < 50.0) return null;
    const what = {
      "szélső": "a szélső-védekezésnél tilos a kéz",
      "beálló": "a beállót elölről kell fogni",
      "átlövő": "a kilépésnél a kar nem mehet a lövő karjára",
      "irányító": "a betörésénél testtel kell zárni",
    };
    final poszt = rows.first[0] as String;
    return "a heteseik ${pct.toStringAsFixed(0)}%-át a $poszt "
        "posztról harcolják ki ($top/$total) · ${what[poszt] ?? "ott "
            "kell a legfegyelmezettebb kezű védekezés"}";
  }

  // Időkérés utáni első támadás: van-e kész figurájuk (3+ időkérés;
  // 60% felett kész figura, 20% alatt üres időkérés — a
  // backend-kulccsal azonos küszöbök).
  String? _timeoutFirstAttack(Map<String, dynamic> r) {
    final n = ((r["tfa_timeouts"] as num?) ?? 0).toInt();
    final goals = ((r["tfa_goals"] as num?) ?? 0).toInt();
    if (n < 3) return null;
    final pct = 100.0 * goals / n;
    if (pct >= 60.0) {
      return "kész figurájuk van az időkérés utánra (az időkéréseik "
          "${pct.toStringAsFixed(0)}%-a után gól jött, $goals/$n) · "
          "arra a támadásra előre fel kell készülni";
    }
    if (pct <= 20.0) {
      return "üres az időkérésük (csak "
          "${pct.toStringAsFixed(0)}%-a után jött gól, $n időkérés) · "
          "nem kell külön készülni az utána jövő támadásukra";
    }
    return null;
  }

  // Kockázatos passzolók: kinek a hosszú labdái foghatók el (4+
  // hosszú kísérlet, 40% feletti eladás-arány — a backend-kulccsal
  // azonos küszöbök).
  String? _riskyPassers(Map<String, dynamic> r) {
    final rows = r["risky_passers"];
    if (rows is! List || rows.isEmpty) return null;
    for (final e in rows) {
      if (e is! Map) continue;
      final tries = ((e["tries"] as num?) ?? 0).toInt();
      final tos = ((e["turnovers"] as num?) ?? 0).toInt();
      if (tries < 4) continue;
      final pct = 100.0 * tos / tries;
      if (pct < 40.0) continue;
      final who = e["jersey"] != null
          ? "${e["jersey"]}-es"
          : "${e["player_id"]} azonosítójú";
      return "a(z) $who játékosuk hosszú labdái elfoghatók (a "
          "kísérletei ${pct.toStringAsFixed(0)}%-a elveszett, "
          "$tos/$tries) · az ő passzsávjába kell beállni";
    }
    return null;
  }

  // Elzárók: ki állítja az elzárásaikat (3+ elzárás — a
  // backend-kulccsal azonos küszöb).
  String? _screenSetters(Map<String, dynamic> r) {
    final rows = r["screen_setters"];
    if (rows is! List || rows.isEmpty) return null;
    final top = rows.first;
    if (top is! Map) return null;
    final n = ((top["screens"] as num?) ?? 0).toInt();
    if (n < 3) return null;
    final who = top["jersey"] != null
        ? "${top["jersey"]}-es"
        : "${top["player_id"]} azonosítójú";
    return "a(z) $who játékosuk állítja az elzárásaikat ($n elzárás) · "
        "az ő oldalán kell a hangos váltás, és elölről kell fogni";
  }

  // Kapus-bemelegedés: hogyan véd a meccs első tíz percében
  // (szakaszonként 4+ kapura tartó lövés, 15 százalékpontos eltérés —
  // a backend-kulccsal azonos küszöbök).
  String? _gkEarlySaves(Map<String, dynamic> r) {
    final eF = ((r["gke_early_faced"] as num?) ?? 0).toInt();
    final eS = ((r["gke_early_saves"] as num?) ?? 0).toInt();
    final rF = ((r["gke_rest_faced"] as num?) ?? 0).toInt();
    final rS = ((r["gke_rest_saves"] as num?) ?? 0).toInt();
    if (eF < 4 || rF < 4) return null;
    final e = 100.0 * eS / eF;
    final rest = 100.0 * rS / rF;
    if (rest - e >= 15.0) {
      return "lassan melegszik be a kapusuk (az első tíz percben "
          "${e.toStringAsFixed(0)}% a későbbi "
          "${rest.toStringAsFixed(0)}% helyett) · a meccs elején "
          "bátran kell rá lőni";
    }
    if (e - rest >= 15.0) {
      return "azonnal formában van a kapusuk (az első tíz percben "
          "${e.toStringAsFixed(0)}% a későbbi "
          "${rest.toStringAsFixed(0)}% helyett) · az elején biztos "
          "helyzetekre kell játszani";
    }
    return null;
  }

  // Emberhátrány-lövők: ki vállalja a befejezést öt emberrel (2+
  // emberhátrányban leadott lövés — a backend-kulccsal azonos küszöb).
  String? _shorthandedShooters(Map<String, dynamic> r) {
    final rows = r["sh_shooters"];
    if (rows is! List || rows.isEmpty) return null;
    final top = rows.first;
    if (top is! Map) return null;
    final shots = ((top["shots"] as num?) ?? 0).toInt();
    if (shots < 2) return null;
    final goals = ((top["goals"] as num?) ?? 0).toInt();
    final who = top["jersey"] != null
        ? "${top["jersey"]}-es"
        : "${top["player_id"]} azonosítójú";
    return "emberhátrányban a(z) $who játékosuk vállalja a befejezést "
        "($shots lövés, $goals gól) · emberelőnyben ő a "
        "kontra-fenyegetés, mögötte maradjon biztosítás";
  }

  // Hajrá-hibázók: kinél megy el a labda a döntő szakaszban (2+
  // hajrá-eladás — a backend-kulccsal azonos küszöb).
  String? _clutchLosers(Map<String, dynamic> r) {
    final rows = r["clutch_losers"];
    if (rows is! List || rows.isEmpty) return null;
    final top = rows.first;
    if (top is! Map) return null;
    final n = ((top["turnovers"] as num?) ?? 0).toInt();
    if (n < 2) return null;
    final who = top["jersey"] != null
        ? "${top["jersey"]}-es"
        : "${top["player_id"]} azonosítójú";
    return "a hajrában a(z) $who játékosuknál megy el a labda ($n "
        "eladás a döntő szakaszban) · a végén rá kell menni, "
        "kettőzéssel és passzsáv-zárással";
  }

  // Csere-kiváltók: kapott gól után cserélnek-e (4+ csere; 50% felett
  // reaktív, 20% alatt tervezett — a backend-kulccsal azonos
  // küszöbök).
  String? _substitutionTriggers(Map<String, dynamic> r) {
    final subs = ((r["stg_subs"] as num?) ?? 0).toInt();
    final after = ((r["stg_after"] as num?) ?? 0).toInt();
    if (subs < 4) return null;
    final pct = 100.0 * after / subs;
    if (pct >= 50.0) {
      return "kapott gólra cserélnek (a cseréik "
          "${pct.toStringAsFixed(0)}%-a gól után jön, $after/$subs) · "
          "gyors gólváltás és azonnali középkezdés ellenük";
    }
    if (pct <= 20.0) {
      return "tervezett a csere-rendjük (a cseréiknek csak "
          "${pct.toStringAsFixed(0)}%-a jön kapott gól után) · a "
          "csere-ritmusuk kiszámítható";
    }
    return null;
  }

  // Falépítés-idő: mennyi idő alatt áll fel a faluk (4+ mért
  // birtokváltás; 8 mp felett lassú, 5 mp alatt gyors — a
  // backend-kulccsal azonos küszöbök).
  String? _defenseSetupTime(Map<String, dynamic> r) {
    final cases = ((r["dst_cases"] as num?) ?? 0).toInt();
    final sum = ((r["dst_sum_s"] as num?) ?? 0).toDouble();
    if (cases < 4 || sum <= 0) return null;
    final avg = sum / cases;
    if (avg >= 8.0) {
      return "lassan áll fel a faluk (átlag "
          "${avg.toStringAsFixed(1)} mp a rendezett falig, $cases mért "
          "birtokváltás) · a gyors indítás termel ellenük";
    }
    if (avg <= 5.0) {
      return "gyorsan rendeződik a faluk (átlag "
          "${avg.toStringAsFixed(1)} mp) · a kontra kockázat, a "
          "felállt támadásra kell építeni";
    }
    return null;
  }

  // Kapus emberhátrányban: nő vagy visszaesik a két perc alatt
  // (helyzetenként 4+ kapura tartó lövés, 15 százalékpontos eltérés —
  // a backend-kulccsal azonos küszöbök).
  String? _gkShorthanded(Map<String, dynamic> r) {
    final shF = ((r["gsh_sh_faced"] as num?) ?? 0).toInt();
    final shS = ((r["gsh_sh_saves"] as num?) ?? 0).toInt();
    final eqF = ((r["gsh_eq_faced"] as num?) ?? 0).toInt();
    final eqS = ((r["gsh_eq_saves"] as num?) ?? 0).toInt();
    if (shF < 4 || eqF < 4) return null;
    final sh = 100.0 * shS / shF;
    final eq = 100.0 * eqS / eqF;
    if (sh - eq >= 15.0) {
      return "a kapusuk emberhátrányban nő "
          "(${sh.toStringAsFixed(0)}% a szokásos "
          "${eq.toStringAsFixed(0)}% helyett) · türelmes emberelőnyt "
          "kell játszani, beállós helyzetekkel";
    }
    if (eq - sh >= 15.0) {
      return "a kapusuk emberhátrányban visszaesik "
          "(${sh.toStringAsFixed(0)}% a szokásos "
          "${eq.toStringAsFixed(0)}% helyett) · emberelőnyben gyorsan "
          "kell befejezni";
    }
    return null;
  }

  // Emberelőny-lövők: ki fejez be a két perc alatt (3+ emberelőnyben
  // leadott lövés — a backend-kulccsal azonos küszöb).
  String? _powerplayShooters(Map<String, dynamic> r) {
    final rows = r["pp_shooters"];
    if (rows is! List || rows.isEmpty) return null;
    final top = rows.first;
    if (top is! Map) return null;
    final shots = ((top["shots"] as num?) ?? 0).toInt();
    if (shots < 3) return null;
    final goals = ((top["goals"] as num?) ?? 0).toInt();
    final who = top["jersey"] != null
        ? "${top["jersey"]}-es"
        : "${top["player_id"]} azonosítójú";
    return "emberelőnyben a(z) $who játékosuk fejez be ($shots lövés, "
        "$goals gól) · emberhátrányban rá kell rendezni a falat";
  }

  // Lövés-távolság esése: kifelé szorulnak-e a hajrára (félidőnként
  // 4+ lövés, 1 m-es növekedés — a backend-kulccsal azonos küszöbök).
  String? _shotDistanceFade(Map<String, dynamic> r) {
    final fhN = ((r["sdf_fh_shots"] as num?) ?? 0).toInt();
    final shN = ((r["sdf_sh_shots"] as num?) ?? 0).toInt();
    final fhSum = ((r["sdf_fh_sum_m"] as num?) ?? 0).toDouble();
    final shSum = ((r["sdf_sh_sum_m"] as num?) ?? 0).toDouble();
    if (fhN < 4 || shN < 4 || fhSum <= 0 || shSum <= 0) return null;
    final fh = fhSum / fhN;
    final sh = shSum / shN;
    if (sh - fh < 1.0) return null;
    return "a hajrára kifelé szorulnak: a lövéseik átlagos távolsága "
        "${fh.toStringAsFixed(1)} m-ről ${sh.toStringAsFixed(1)} m-re "
        "nő · a második félidőben elég a lövő-vonalba lépni";
  }

  // Kapott gólok támadás-típus szerint: melyik műfajból szivárognak
  // (5+ kapott gól, 40% feletti vezető típus, holtverseny nélkül — a
  // backend-kulccsal azonos küszöbök).
  String? _concededTypes(Map<String, dynamic> r) {
    final types = r["conceded_types"];
    if (types is! Map || types.isEmpty) return null;
    final rows = types.entries
        .map((e) => [e.key.toString(), ((e.value as num?) ?? 0).toInt()])
        .toList()
      ..sort((a, b) => (b[1] as int).compareTo(a[1] as int));
    final total = rows.fold<int>(0, (s, e) => s + (e[1] as int));
    if (total < 5) return null;
    final top = rows.first[1] as int;
    if (rows.length > 1 && (rows[1][1] as int) == top) return null;
    final pct = 100.0 * top / total;
    if (pct < 40.0) return null;
    final type = rows.first[0] as String;
    final fast = type.contains("lerohanás") || type.contains("gyors");
    return "a kapott góljaik ${pct.toStringAsFixed(0)}%-a $type-ból "
        "jön ($top/$total) · ${fast ? "a visszarendeződésük a gyenge "
            "pont, gyors indítás termel" : "a felállt faluk a gyenge "
            "pont, figurákkal kell dolgozni"}";
  }

  // Áttörő játékosok: ki jut be labdával a falba (3+ betörés — a
  // backend-kulccsal azonos küszöb).
  String? _breakthroughPlayers(Map<String, dynamic> r) {
    final rows = r["breakthrough_players"];
    if (rows is! List || rows.isEmpty) return null;
    final top = rows.first;
    if (top is! Map) return null;
    final entries = ((top["entries"] as num?) ?? 0).toInt();
    if (entries < 3) return null;
    final goals = ((top["goals"] as num?) ?? 0).toInt();
    final who = top["jersey"] != null
        ? "${top["jersey"]}-es"
        : "${top["player_id"]} azonosítójú";
    return "a(z) $who játékosuk töri át a falat ($entries betörés, "
        "ebből $goals gólos támadás) · rá duplázni kell, a vonalát "
        "testtel zárni";
  }

  // Két beállós játék: hány emberrel dolgoznak a 6 m-en (8+ támadás;
  // 30% felett két beállós, 10% alatt egy beállós — a backend-kulccsal
  // azonos küszöbök).
  String? _doublePivot(Map<String, dynamic> r) {
    final att = ((r["dpv_attacks"] as num?) ?? 0).toInt();
    final dbl = ((r["dpv_double"] as num?) ?? 0).toInt();
    if (att < 8) return null;
    final pct = 100.0 * dbl / att;
    if (pct >= 30.0) {
      return "két beállóval játszanak (a támadásaik "
          "${pct.toStringAsFixed(0)}%-ában, $dbl/$att) · a fal közepét "
          "tömöríteni kell, saját beállóval mindkét középső védőnek";
    }
    if (pct <= 10.0) {
      return "egy beállós felállás (a támadásaiknak csak "
          "${pct.toStringAsFixed(0)}%-ában van két emberük a 6 m-en) · "
          "a segítő védő befelé dolgozhat";
    }
    return null;
  }

  // Hajrá-ötös: kik vannak a pályán a döntő szakaszban (legalább négy
  // hajrá-ember — a backend-kulccsal azonos küszöb).
  String? _clutchLineup(Map<String, dynamic> r) {
    final rows = r["clutch_players"];
    if (rows is! List || rows.length < 4) return null;
    final names = <String>[];
    for (final e in rows.take(6)) {
      if (e is! Map) continue;
      names.add(e["jersey"] != null
          ? "${e["jersey"]}-es"
          : "#${e["player_id"]}");
    }
    if (names.length < 4) return null;
    return "hajrá-embereik: ${names.join(", ")} · a döntő szakaszra "
        "rájuk kell tervezni a párosítást";
  }

  // Kontra-kíséret: hányan futnak fel a lerohanásoknál (3+ lerohanás;
  // 3,0 felett tömeges, 1,6 alatt magányos — a backend-kulccsal azonos
  // küszöbök).
  String? _fastBreakSupport(Map<String, dynamic> r) {
    final breaks = ((r["fbs_breaks"] as num?) ?? 0).toInt();
    final sum = ((r["fbs_sum_runners"] as num?) ?? 0).toDouble();
    if (breaks < 3 || sum <= 0) return null;
    final avg = sum / breaks;
    if (avg >= 3.0) {
      return "tömegesen kontráznak: átlag "
          "${avg.toStringAsFixed(1)} emberük van elöl a "
          "lerohanásoknál ($breaks lerohanás) · mindenkinek azonnal "
          "vissza kell rendeződnie";
    }
    if (avg <= 1.6) {
      return "magányos kontrát futnak (átlag "
          "${avg.toStringAsFixed(1)} felfutó ember) · elég egy fékező "
          "játékos, a többiek felállhatnak";
    }
    return null;
  }

  // Kapus-hetesvédés iránya: melyik sarokra ér a legkésőbb
  // (irányonként 3+ hetes, 25 százalékpontos elmaradás — a
  // backend-kulccsal azonos küszöbök).
  String? _gkSevenDirections(Map<String, dynamic> r) {
    final faced = r["g7d_faced"];
    final saved = r["g7d_saved"];
    if (faced is! Map || saved is! Map || faced.isEmpty) return null;
    int total = 0;
    int totalSaved = 0;
    faced.forEach((k, v) {
      total += ((v as num?) ?? 0).toInt();
      totalSaved += ((saved[k] as num?) ?? 0).toInt();
    });
    if (total < 3) return null;
    String? weak;
    double weakPct = 0.0;
    int weakN = 0;
    faced.forEach((k, v) {
      final n = ((v as num?) ?? 0).toInt();
      if (n < 3) return;
      final pct = 100.0 * ((saved[k] as num?) ?? 0).toInt() / n;
      if (weak == null || pct < weakPct) {
        weak = k.toString();
        weakPct = pct;
        weakN = n;
      }
    });
    if (weak == null) return null;
    final avg = 100.0 * totalSaved / total;
    if (avg - weakPct < 25.0) return null;
    return "a kapusuk a $weak sarokra ér a legkésőbb (onnan "
        "${weakPct.toStringAsFixed(0)}%-ot fog $weakN hetesből, az "
        "átlaga ${avg.toStringAsFixed(0)}%) · oda kell lőni a hetest";
  }

  // Kihozatal-oldal: melyik oldalon indítják a támadást (8+ támadás,
  // 50% feletti oldal — a backend-kulccsal azonos küszöbök).
  String? _buildupSide(Map<String, dynamic> r) {
    final left = ((r["bus_left"] as num?) ?? 0).toInt();
    final center = ((r["bus_center"] as num?) ?? 0).toInt();
    final right = ((r["bus_right"] as num?) ?? 0).toInt();
    final total = left + center + right;
    if (total < 8) return null;
    var best = "bal";
    var cnt = left;
    if (center > cnt) {
      best = "közép";
      cnt = center;
    }
    if (right > cnt) {
      best = "jobb";
      cnt = right;
    }
    final pct = 100.0 * cnt / total;
    if (pct < 50.0 || best == "közép") return null;
    return "a $best oldalon hozzák fel a labdát (a támadásaik "
        "${pct.toStringAsFixed(0)}%-a onnan indul, $cnt/$total) · oda "
        "kell szervezni a letámadást";
  }

  // Lepattanó-szerzők: ki gyűjti a kipattanóikat (3+ lepattanó — a
  // backend-kulccsal azonos küszöb).
  String? _rebounders(Map<String, dynamic> r) {
    final rows = r["rebounders"];
    if (rows is! List || rows.isEmpty) return null;
    final top = rows.first;
    if (top is! Map) return null;
    final n = ((top["rebounds"] as num?) ?? 0).toInt();
    if (n < 3) return null;
    final who = top["jersey"] != null
        ? "${top["jersey"]}-es"
        : "${top["player_id"]} azonosítójú";
    return "a(z) $who játékosuk gyűjti a kipattanókat ($n lepattanó) · "
        "a blokk után azonnal be kell zárni a 6 m-es teret";
  }

  // Lövő-távolság profil: kire kell kilépni (3+ lövés; 9,5 m felett
  // távoli lövő — a backend-kulccsal azonos küszöbök).
  String? _shooterRanges(Map<String, dynamic> r) {
    final rows = r["shooter_ranges"];
    if (rows is! List || rows.isEmpty) return null;
    Map? far;
    double farAvg = 0.0;
    for (final e in rows) {
      if (e is! Map) continue;
      final shots = ((e["shots"] as num?) ?? 0).toInt();
      final sum = ((e["sum_dist_m"] as num?) ?? 0).toDouble();
      if (shots < 3) continue;
      final avg = sum / shots;
      if (far == null || avg > farAvg) {
        far = e;
        farAvg = avg;
      }
    }
    if (far == null || farAvg < 9.5) return null;
    final who = far["jersey"] != null
        ? "${far["jersey"]}-es"
        : "${far["player_id"]} azonosítójú";
    return "a(z) $who játékosuk távolról lő (átlag "
        "${farAvg.toStringAsFixed(1)} m, ${far["shots"]} lövés) · rá "
        "ki kell lépni a lövő-vonalba, mögötte segítővel";
  }

  // Emberhátrány-forma: milyen falat húznak öt emberrel (100+ mért
  // kocka, 60% feletti fő forma — a backend-kulccsal azonos küszöbök).
  String? _shorthandedShape(Map<String, dynamic> r) {
    final labels = r["sh_shape"];
    if (labels is! Map || labels.isEmpty) return null;
    final rows = labels.entries
        .map((e) => [e.key.toString(), ((e.value as num?) ?? 0).toInt()])
        .toList()
      ..sort((a, b) => (b[1] as int).compareTo(a[1] as int));
    final total = rows.fold<int>(0, (s, e) => s + (e[1] as int));
    if (total < 100) return null;
    final pct = 100.0 * (rows.first[1] as int) / total;
    if (pct < 60.0) return null;
    final main = rows.first[0] as String;
    const what = {
      "5-0": "mögötte az átlövés szabad, kívülről kell lőni",
      "4-1": "az előretolt emberük mögé kell beúsztatni a beállót",
      "3-2": "a szélek és a beálló szabadok, gyors oldalváltás kell",
    };
    return "emberhátrányban $main-s falat húznak (a mért kockák "
        "${pct.toStringAsFixed(0)}%-ában) · ${what[main] ?? "oldalváltás "
            "és beállós játék a válasz"}";
  }

  // Emberelőny-tempó: elnyújtják vagy kapkodják a két percet (3+
  // emberelőnyös és 5+ egyenlő létszámú támadás, 5 mp-es eltérés — a
  // backend-kulccsal azonos küszöbök).
  String? _powerplayPace(Map<String, dynamic> r) {
    final ppN = ((r["ppp_pp_attacks"] as num?) ?? 0).toInt();
    final ppS = ((r["ppp_pp_sum_s"] as num?) ?? 0).toDouble();
    final eqN = ((r["ppp_eq_attacks"] as num?) ?? 0).toInt();
    final eqS = ((r["ppp_eq_sum_s"] as num?) ?? 0).toDouble();
    if (ppN < 3 || eqN < 5 || ppS <= 0 || eqS <= 0) return null;
    final pp = ppS / ppN;
    final eq = eqS / eqN;
    final gap = pp - eq;
    if (gap >= 5.0) {
      return "elnyújtják az emberelőnyt (${pp.toStringAsFixed(0)} mp-es "
          "támadások a ${eq.toStringAsFixed(0)} mp-es átlaguk helyett) "
          "· türelmes, zárt fal kell emberhátrányban";
    }
    if (gap <= -5.0) {
      return "kapkodnak emberelőnyben (${pp.toStringAsFixed(0)} mp-es "
          "támadások a ${eq.toStringAsFixed(0)} mp-es átlaguk helyett) "
          "· agresszív, kilépő védekezés fizet ki";
    }
    return null;
  }

  // Meccs-ritmus: mennyi a tényleges játék (10+ perc mért játékidő;
  // 80% alatt szakadozott, 92% felett folyamatos — a backend-kulccsal
  // azonos küszöbök).
  String? _playingTime(Map<String, dynamic> r) {
    final total = ((r["ptp_total_s"] as num?) ?? 0).toDouble();
    final stopped = ((r["ptp_stopped_s"] as num?) ?? 0).toDouble();
    final own = ((r["ptp_own_stoppages"] as num?) ?? 0).toInt();
    if (total < 600.0) return null;
    final eff = 100.0 * (total - stopped) / total;
    if (eff <= 80.0) {
      return "szakadozott meccskép: az effektív játékidő "
          "${eff.toStringAsFixed(0)}% "
          "(${(stopped / 60.0).toStringAsFixed(0)} perc holt idő, "
          "ebből $own megszakítás náluk állt meg) · ritmus-tartás, "
          "gyors középkezdés";
    }
    if (eff >= 92.0) {
      return "folyamatos meccs: az effektív játékidő "
          "${eff.toStringAsFixed(0)}% · a cserék időzítése és a "
          "bírás dönt";
    }
    return null;
  }

  // Védekezés-keménység: hoz-e büntetést a faluk (10+ védekezett
  // támadás; 12% felett kemény, 4% alatt passzív — a backend-kulccsal
  // azonos küszöbök).
  String? _defAggression(Map<String, dynamic> r) {
    final att = ((r["agr_attacks"] as num?) ?? 0).toInt();
    final sevens = ((r["agr_sevens"] as num?) ?? 0).toInt();
    final susp = ((r["agr_susp"] as num?) ?? 0).toInt();
    if (att < 10) return null;
    final pct = 100.0 * (sevens + susp) / att;
    if (pct >= 12.0) {
      return "kemény fal: a védekezett támadásaik "
          "${pct.toStringAsFixed(0)}%-a hetest vagy kiállítást hoz "
          "($sevens hetes, $susp kiállítás) · a betörés duplán fizet";
    }
    if (pct <= 4.0) {
      return "passzív fal: a védekezett támadásaiknak csak "
          "${pct.toStringAsFixed(0)}%-a hoz büntetést ($att támadás) · "
          "figurákkal és beállós játékkal kell helyzetet csinálni";
    }
    return null;
  }

  // Visszaérés-fegyelem: ki lóg elöl védekezéskor (200+ mért kocka,
  // 70% alatti hazaérési arány — a backend-kulccsal azonos küszöbök).
  String? _recoveryDiscipline(Map<String, dynamic> r) {
    final rows = r["recovery_players"];
    if (rows is! List || rows.isEmpty) return null;
    Map? worst;
    double worstPct = 0.0;
    for (final e in rows) {
      if (e is! Map) continue;
      final frames = ((e["frames"] as num?) ?? 0).toInt();
      final home = ((e["home_frames"] as num?) ?? 0).toInt();
      if (frames < 200) continue;
      final pct = 100.0 * home / frames;
      if (worst == null || pct < worstPct) {
        worst = e;
        worstPct = pct;
      }
    }
    if (worst == null || worstPct >= 70.0) return null;
    final who = worst["jersey"] != null
        ? "${worst["jersey"]}-es"
        : "${worst["player_id"]} azonosítójú";
    return "a(z) $who játékosuk elöl lóg védekezéskor (a védekezett "
        "időnek csak ${worstPct.toStringAsFixed(0)}%-ában van a saját "
        "térfelén) · az ő oldalán vezessétek a kontrát";
  }

  // Kapus-védés lövés-tempó szerint: a bombákat vagy a helyezett
  // lövéseket fogja (sávonként 4+ lövés, 15 százalékpontos eltérés — a
  // backend-kulccsal azonos küszöbök).
  String? _gkSpeedBands(Map<String, dynamic> r) {
    final hf = ((r["gsp_hard_faced"] as num?) ?? 0).toInt();
    final hs = ((r["gsp_hard_saves"] as num?) ?? 0).toInt();
    final pf = ((r["gsp_placed_faced"] as num?) ?? 0).toInt();
    final ps = ((r["gsp_placed_saves"] as num?) ?? 0).toInt();
    if (hf < 4 || pf < 4) return null;
    final hp = 100.0 * hs / hf;
    final pp = 100.0 * ps / pf;
    if ((hp - pp).abs() < 15.0) return null;
    if (hp > pp) {
      return "a kapusuk a bombákat fogja "
          "(${hp.toStringAsFixed(0)}%), a helyezett lövéseket nem "
          "(${pp.toStringAsFixed(0)}%) · sarokba helyezve, "
          "pattintva kell befejezni";
    }
    return "a kapusuk a helyezett lövéseket fogja "
        "(${pp.toStringAsFixed(0)}%), a keményeket nem "
        "(${hp.toStringAsFixed(0)}%) · vállalni kell a kemény lövést";
  }

  // Álló támadók: ki mozog labda nélkül a legkevesebbet (60+ mért
  // másodperc, 30%-os elmaradás a csapatátlagtól — a backend-kulccsal
  // azonos küszöbök).
  String? _staticAttackers(Map<String, dynamic> r) {
    final rows = r["static_attackers"];
    if (rows is! List || rows.isEmpty) return null;
    double totalT = 0.0;
    double totalD = 0.0;
    Map? slow;
    double slowV = 0.0;
    for (final e in rows) {
      if (e is! Map) continue;
      final sec = ((e["seconds"] as num?) ?? 0).toDouble();
      final dist = ((e["dist_m"] as num?) ?? 0).toDouble();
      if (sec <= 0) continue;
      totalT += sec;
      totalD += dist;
      if (sec < 60.0) continue;
      final v = dist / sec;
      if (slow == null || v < slowV) {
        slow = e;
        slowV = v;
      }
    }
    if (totalT <= 0 || slow == null) return null;
    final avg = totalD / totalT;
    if (avg <= 0 || 100.0 * (avg - slowV) / avg < 30.0) return null;
    final who = slow["jersey"] != null
        ? "${slow["jersey"]}-es"
        : "${slow["player_id"]} azonosítójú";
    return "a(z) $who játékosuk alig mozog a támadásban "
        "(${slowV.toStringAsFixed(2)} m/s a csapatátlag "
        "${avg.toStringAsFixed(2)} m/s helyett) · az ő védője "
        "otthagyhatja, befelé segíthet";
  }

  // Szélső-befejezés oldalanként: melyik szélsőjük veszélyes
  // (oldalanként 3+ lövés, 25 százalékpontos eltérés — a
  // backend-kulccsal azonos küszöbök).
  String? _wingSides(Map<String, dynamic> r) {
    final ls = ((r["wfs_left_shots"] as num?) ?? 0).toInt();
    final lg = ((r["wfs_left_goals"] as num?) ?? 0).toInt();
    final rs = ((r["wfs_right_shots"] as num?) ?? 0).toInt();
    final rg = ((r["wfs_right_goals"] as num?) ?? 0).toInt();
    if (ls < 3 || rs < 3) return null;
    final lp = 100.0 * lg / ls;
    final rp = 100.0 * rg / rs;
    if ((lp - rp).abs() < 25.0) return null;
    final strong = lp > rp ? "bal" : "jobb";
    final weak = lp > rp ? "jobb" : "bal";
    final sp = lp > rp ? lp : rp;
    final wp = lp > rp ? rp : lp;
    return "a $strong szélsőjük a veszélyes "
        "(${sp.toStringAsFixed(0)}%-os befejezés, a $weak oldalon "
        "${wp.toStringAsFixed(0)}%) · vele szemben zárni a szöget, a "
        "gyengébbre rá lehet engedni a lövést";
  }

  // Beálló-oldal: melyik oldalon dolgozik a beállójuk (100+ mért
  // kocka, 55% feletti oldal — a backend-kulccsal azonos küszöbök).
  String? _pivotSide(Map<String, dynamic> r) {
    final left = ((r["pvs_left"] as num?) ?? 0).toInt();
    final center = ((r["pvs_center"] as num?) ?? 0).toInt();
    final right = ((r["pvs_right"] as num?) ?? 0).toInt();
    final total = left + center + right;
    if (total < 100) return null;
    var best = "bal";
    var cnt = left;
    if (center > cnt) {
      best = "közép";
      cnt = center;
    }
    if (right > cnt) {
      best = "jobb";
      cnt = right;
    }
    final pct = 100.0 * cnt / total;
    if (pct < 55.0 || best == "közép") return null;
    return "a beállójuk a $best oldalon dolgozik (a mért kockák "
        "${pct.toStringAsFixed(0)}%-ában) · ott kell a legerősebb "
        "védőpár és az átadás-fegyelem";
  }

  // Fal-csúszás késése: milyen gyorsan igazodik a faluk az
  // oldalváltáshoz (200+ védekezett kocka; 0,6 mp felett lassú, 0,2 mp
  // alatt gyors — a backend-kulccsal azonos küszöbök).
  String? _shiftLag(Map<String, dynamic> r) {
    final frames = ((r["dsl_frames"] as num?) ?? 0).toInt();
    final sum = ((r["dsl_sum_s"] as num?) ?? 0).toDouble();
    if (frames < 200 || sum <= 0) return null;
    final lag = sum / frames;
    if (lag >= 0.6) {
      return "lassan csúszik a faluk: ${lag.toStringAsFixed(1)} mp "
          "késéssel követik az oldalváltást · két-három gyors "
          "átjátszás után a túloldalon nyílik a rés";
    }
    if (lag <= 0.2) {
      return "gyorsan igazodik a faluk (${lag.toStringAsFixed(1)} mp "
          "késés) · az átjátszás nem fizet ki, betörés és beállós "
          "játék a válasz";
    }
    return null;
  }

  // Passz-sebesség: éles vagy lágy a labdajáratásuk (10+ mért passz;
  // 50% felett éles, 20% alatt lágy — a backend-kulccsal azonos
  // küszöbök).
  String? _passSpeed(Map<String, dynamic> r) {
    final n = ((r["psp_passes"] as num?) ?? 0).toInt();
    final sum = ((r["psp_sum_ms"] as num?) ?? 0).toDouble();
    final fast = ((r["psp_fast"] as num?) ?? 0).toInt();
    if (n < 10) return null;
    final avg = sum / n;
    final pct = 100.0 * fast / n;
    if (pct >= 50.0) {
      return "éles a labdajáratásuk: a passzaik "
          "${pct.toStringAsFixed(0)}%-a feszes (átlag "
          "${avg.toStringAsFixed(1)} m/s) · testtel zárni, a fogadót "
          "megfogni";
    }
    if (pct <= 20.0) {
      return "lágy a labdajáratásuk: a passzaiknak csak "
          "${pct.toStringAsFixed(0)}%-a feszes (átlag "
          "${avg.toStringAsFixed(1)} m/s) · bele lehet érni, beleérő "
          "védekezés";
    }
    return null;
  }

  // Beálló-kiszolgálók: ki adja be a labdát a beállónak (4+ beadás,
  // 50% feletti vezető kiszolgáló, holtverseny nélkül — a
  // backend-kulccsal azonos küszöbök).
  String? _pivotFeeders(Map<String, dynamic> r) {
    final rows = r["pivot_feeders"];
    if (rows is! List || rows.isEmpty) return null;
    int total = 0;
    for (final e in rows) {
      if (e is Map) total += ((e["feeds"] as num?) ?? 0).toInt();
    }
    if (total < 4) return null;
    final top = rows.first;
    if (top is! Map) return null;
    final feeds = ((top["feeds"] as num?) ?? 0).toInt();
    if (rows.length > 1 && rows[1] is Map &&
        ((rows[1]["feeds"] as num?) ?? 0).toInt() == feeds) {
      return null;
    }
    final pct = 100.0 * feeds / total;
    if (pct < 50.0) return null;
    final who = top["jersey"] != null
        ? "${top["jersey"]}-es"
        : "${top["player_id"]} azonosítójú";
    return "a beállójukat a(z) $who játékosuk szolgálja ki: a "
        "beadások ${pct.toStringAsFixed(0)}%-a ($feeds/$total) · rá "
        "kell lépni az átadás-vonalba";
  }

  // Hetes-okozó védők: kinél szakad meg a védekezésük hetessel (2+
  // okozott hetes — a backend-kulccsal azonos küszöb).
  String? _sevenConceders(Map<String, dynamic> r) {
    final rows = r["seven_conceders"];
    if (rows is! List || rows.isEmpty) return null;
    final top = rows.first;
    if (top is! Map) return null;
    final n = ((top["conceded"] as num?) ?? 0).toInt();
    if (n < 2) return null;
    final who = top["jersey"] != null
        ? "${top["jersey"]}-es"
        : "${top["player_id"]} azonosítójú";
    return "a(z) $who védőjük $n hetest okozott · nála kézzel áll meg "
        "a betörés: ellene betörés és beugrás";
  }

  // Támadás-mélység: milyen messze állnak a kaputól (100+ mért kocka;
  // 9,5 m alatt vonalra tapadó, 12 m felett mély — a backend-kulccsal
  // azonos küszöbök).
  String? _attackDepth(Map<String, dynamic> r) {
    final frames = ((r["adp_frames"] as num?) ?? 0).toInt();
    final sum = ((r["adp_sum_m"] as num?) ?? 0).toDouble();
    if (frames < 100 || sum <= 0) return null;
    final avg = sum / frames;
    if (avg <= 9.5) {
      return "vonalra tapadnak: a támadóik átlagosan "
          "${avg.toStringAsFixed(1)} m-re állnak a kaputól · a falatok "
          "NE lépjen ki, segítő-csúszás és testes fogadás";
    }
    if (avg >= 12.0) {
      return "mélyen, hátrahúzódva támadnak (átlagosan "
          "${avg.toStringAsFixed(1)} m-re a kaputól) · ki kell lépni "
          "a lövő-vonalba";
    }
    return null;
  }

  // Szélső-bevonás: eljut-e a labda a szélre (8+ támadás; 60% felett
  // széthúzzák, 30% alatt közép-központú — a backend-kulccsal azonos
  // küszöbök).
  String? _wingInvolvement(Map<String, dynamic> r) {
    final n = ((r["wi_attacks"] as num?) ?? 0).toInt();
    final wide = ((r["wi_with_wing"] as num?) ?? 0).toInt();
    if (n < 8) return null;
    final pct = 100.0 * wide / n;
    if (pct >= 60.0) {
      return "széthúzzák a támadást: a támadásaik "
          "${pct.toStringAsFixed(0)}%-ában kimegy a labda a szélre "
          "($wide/$n) · időben kell kifutni a szélsőre";
    }
    if (pct <= 30.0) {
      return "közép-központúak: a támadásaiknak csak "
          "${pct.toStringAsFixed(0)}%-ában jut ki a labda a szélre "
          "($n támadás) · a szélső-védőitek beljebb segíthetnek";
    }
    return null;
  }

  // Védekezési mélység állás szerint: mikor jön a nyomásuk (100+ mért
  // kocka mindkét állásban, 0,8 m-es rés — a backend-kulccsal azonos
  // küszöbök).
  String? _lineHeightByScore(Map<String, dynamic> r) {
    final leadF = ((r["lhs_lead_frames"] as num?) ?? 0).toInt();
    final trailF = ((r["lhs_trail_frames"] as num?) ?? 0).toInt();
    final leadSum = ((r["lhs_lead_sum_m"] as num?) ?? 0).toDouble();
    final trailSum = ((r["lhs_trail_sum_m"] as num?) ?? 0).toDouble();
    if (leadF < 100 || trailF < 100) return null;
    final lead = leadSum / leadF;
    final trail = trailSum / trailF;
    final gap = trail - lead;
    if (gap >= 0.8) {
      return "hátrányban feljebb lépnek: hátrányban "
          "${trail.toStringAsFixed(1)} m-en, vezetve "
          "${lead.toStringAsFixed(1)} m-en áll a faluk · kapott gól "
          "után jön a letámadásuk, arra kell kész kihozatal";
    }
    if (gap <= -0.8) {
      return "vezetve is fent maradnak: előnyben "
          "${lead.toStringAsFixed(1)} m-en, hátrányban "
          "${trail.toStringAsFixed(1)} m-en áll a faluk · "
          "letámadás-álló kihozatal kell ellenük";
    }
    return null;
  }

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
  String? _gkOutletLength(Map<String, dynamic> r) {
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
      if (_gkOutletLength(r) != null)
        ["Indítás-hossz", _gkOutletLength(r)!],
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
      if (_lineHeightByScore(r) != null)
        ["Védekezési mélység állás szerint", _lineHeightByScore(r)!],
      if (_wingInvolvement(r) != null)
        ["Szélső-bevonás", _wingInvolvement(r)!],
      if (_attackDepth(r) != null) ["Támadás-mélység", _attackDepth(r)!],
      if (_sevenConceders(r) != null)
        ["Hetes-okozó védők", _sevenConceders(r)!],
      if (_pivotFeeders(r) != null)
        ["Beálló-kiszolgálók", _pivotFeeders(r)!],
      if (_passSpeed(r) != null) ["Passz-sebesség", _passSpeed(r)!],
      if (_shiftLag(r) != null) ["Fal-csúszás késése", _shiftLag(r)!],
      if (_pivotSide(r) != null) ["Beálló-oldal", _pivotSide(r)!],
      if (_wingSides(r) != null)
        ["Szélső-befejezés oldalanként", _wingSides(r)!],
      if (_staticAttackers(r) != null)
        ["Álló támadók", _staticAttackers(r)!],
      if (_gkSpeedBands(r) != null)
        ["Kapus-védés lövés-tempó szerint", _gkSpeedBands(r)!],
      if (_recoveryDiscipline(r) != null)
        ["Visszaérés-fegyelem", _recoveryDiscipline(r)!],
      if (_defAggression(r) != null)
        ["Védekezés-keménység", _defAggression(r)!],
      if (_playingTime(r) != null) ["Meccs-ritmus", _playingTime(r)!],
      if (_powerplayPace(r) != null)
        ["Emberelőny-tempó", _powerplayPace(r)!],
      if (_shorthandedShape(r) != null)
        ["Emberhátrány-forma", _shorthandedShape(r)!],
      if (_shooterRanges(r) != null)
        ["Lövő-távolság", _shooterRanges(r)!],
      if (_rebounders(r) != null) ["Lepattanó-szerzők", _rebounders(r)!],
      if (_buildupSide(r) != null) ["Kihozatal-oldal", _buildupSide(r)!],
      if (_gkSevenDirections(r) != null)
        ["Kapus-hetesvédés iránya", _gkSevenDirections(r)!],
      if (_fastBreakSupport(r) != null)
        ["Kontra-kíséret", _fastBreakSupport(r)!],
      if (_clutchLineup(r) != null) ["Hajrá-ötös", _clutchLineup(r)!],
      if (_doublePivot(r) != null) ["Két beállós játék", _doublePivot(r)!],
      if (_breakthroughPlayers(r) != null)
        ["Áttörő játékosok", _breakthroughPlayers(r)!],
      if (_concededTypes(r) != null)
        ["Kapott gólok műfaj szerint", _concededTypes(r)!],
      if (_shotDistanceFade(r) != null)
        ["Lövés-távolság esése", _shotDistanceFade(r)!],
      if (_powerplayShooters(r) != null)
        ["Emberelőny-lövők", _powerplayShooters(r)!],
      if (_gkShorthanded(r) != null)
        ["Kapus emberhátrányban", _gkShorthanded(r)!],
      if (_defenseSetupTime(r) != null)
        ["Falépítés-idő", _defenseSetupTime(r)!],
      if (_substitutionTriggers(r) != null)
        ["Csere-kiváltók", _substitutionTriggers(r)!],
      if (_clutchLosers(r) != null) ["Hajrá-hibázók", _clutchLosers(r)!],
      if (_shorthandedShooters(r) != null)
        ["Emberhátrány-lövők", _shorthandedShooters(r)!],
      if (_gkEarlySaves(r) != null)
        ["Kapus-bemelegedés", _gkEarlySaves(r)!],
      if (_screenSetters(r) != null) ["Elzárók", _screenSetters(r)!],
      if (_riskyPassers(r) != null)
        ["Kockázatos passzolók", _riskyPassers(r)!],
      if (_timeoutFirstAttack(r) != null)
        ["Időkérés utáni támadás", _timeoutFirstAttack(r)!],
      if (_sevenEarnerRoles(r) != null)
        ["Hetes-kiharcolás posztja", _sevenEarnerRoles(r)!],
      if (_openingLineup(r) != null) ["Kezdő hatos", _openingLineup(r)!],
      if (_wastefulShooters(r) != null)
        ["Pontatlan lövők", _wastefulShooters(r)!],
      if (_highStealers(r) != null)
        ["Elöl szerző védők", _highStealers(r)!],
      if (_pressurePlayers(r) != null)
        ["Pressz-érzékeny játékosok", _pressurePlayers(r)!],
      if (_coveredShooters(r) != null)
        ["Fedezetten lövők", _coveredShooters(r)!],
      if (_keeperInvolvement(r) != null)
        ["Kapus-bevonás", _keeperInvolvement(r)!],
      if (_buildupTime(r) != null)
        ["Felhozatal-idő", _buildupTime(r)!],
      if (_pressAfterGoal(r) != null)
        ["Gól utáni letámadás", _pressAfterGoal(r)!],
      if (_timeoutDefense(r) != null)
        ["Időkérés utáni védekezés", _timeoutDefense(r)!],
      if (_halfOpenings(r) != null)
        ["Félidő-nyitás", _halfOpenings(r)!],
      if (_fastBreakConversion(r) != null)
        ["Lerohanás-hatékonyság", _fastBreakConversion(r)!],
      if (_closingAttacks(r) != null)
        ["Utolsó labda", _closingAttacks(r)!],
      if (_concededChanceQuality(r) != null)
        ["Kapott helyzetek", _concededChanceQuality(r)!],
      if (_stealTypes(r) != null)
        ["Labdaszerzés-típus", _stealTypes(r)!],
      if (_benchScoring(r) != null)
        ["Pad-gólok", _benchScoring(r)!],
      if (_wallFade(r) != null)
        ["Fal-fáradás", _wallFade(r)!],
      if (_sevensFade(r) != null)
        ["Hetes-fáradás", _sevensFade(r)!],
      if (_stealLaunch(r) != null)
        ["Szerzés utáni indítás", _stealLaunch(r)!],
      if (_pullbackRate(r) != null)
        ["Visszahozott támadások", _pullbackRate(r)!],
      if (_swapPairs(r) != null)
        ["Váltópárok", _swapPairs(r)!],
      if (_restartTargets(r) != null)
        ["Középkezdés-átvevő", _restartTargets(r)!],
      if (_advancedDefender(r) != null)
        ["Kilépő védő", _advancedDefender(r)!],
      if (_sevenKeeperSwaps(r) != null)
        ["Hetes-kapuscsere", _sevenKeeperSwaps(r)!],
      if (_sprintThreats(r) != null)
        ["Sprint-veszély", _sprintThreats(r)!],
      if (_phaseSpecialists(r) != null)
        ["Váltott sorok", _phaseSpecialists(r)!],
      if (_distanceBattle(r) != null)
        ["Futás-mérleg", _distanceBattle(r)!],
      if (_turnoversByRole(r) != null)
        ["Poszt-hibák", _turnoversByRole(r)!],
      if (_postPowerplay(r) != null)
        ["Visszaállás", _postPowerplay(r)!],
      if (_widthByScore(r) != null)
        ["Szorult játék", _widthByScore(r)!],
      if (_gkSavesByScore(r) != null)
        ["Kapus állás szerint", _gkSavesByScore(r)!],
      if (_shotQualityByScore(r) != null)
        ["Lövés-választás", _shotQualityByScore(r)!],
      if (_timeoutSubCombo(r) != null)
        ["Időkérés-csomag", _timeoutSubCombo(r)!],
      if (_pivotGuards(r) != null)
        ["Beálló-őr", _pivotGuards(r)!],
      if (_quarterProfile(r) != null)
        ["Negyedóra-profil", _quarterProfile(r)!],
      if (_clutchBallHogs(r) != null)
        ["Hajrá-birtoklás", _clutchBallHogs(r)!],
      if (_longBreakResponse(r) != null)
        ["Hosszú állások", _longBreakResponse(r)!],
      if (_gkGoalThreat(r) != null)
        ["Kapus-gól veszély", _gkGoalThreat(r)!],
      if (_breakSources(r) != null)
        ["Kontra-forrás", _breakSources(r)!],
      if (_attackVsWallHeight(r) != null)
        ["Fal-magasság ellen", _attackVsWallHeight(r)!],
      if (_gkColdStreaks(r) != null)
        ["Kapus-hidegedés", _gkColdStreaks(r)!],
      if (_hotHands(r) != null)
        ["Forró kéz", _hotHands(r)!],
      if (_droughtBreakers(r) != null)
        ["Csend-törők", _droughtBreakers(r)!],
      if (_wingCloseouts(r) != null)
        ["Szélső-kifutás", _wingCloseouts(r)!],
      if (_screenPairs(r) != null)
        ["Elzárás-páros", _screenPairs(r)!],
      if (_circulationDirection(r) != null)
        ["Labda-forgatás", _circulationDirection(r)!],
      if (_postSevenLapses(r) != null)
        ["Hetes utáni percek", _postSevenLapses(r)!],
      if (_bigChanceFinishers(r) != null)
        ["Ziccer-befejezők", _bigChanceFinishers(r)!],
      if (_blockRecoveries(r) != null)
        ["Blokk-lepattanó", _blockRecoveries(r)!],
      if (_attackHeadcount(r) != null)
        ["Felfutási létszám", _attackHeadcount(r)!],
      if (_longAttackOutcomes(r) != null)
        ["Kivárás-csapda", _longAttackOutcomes(r)!],
      if (_gkReboundControl(r) != null)
        ["Kapus-kipattanó", _gkReboundControl(r)!],
      if (_assistRanges(r) != null)
        ["Gólpassz-hossz", _assistRanges(r)!],
      if (_subGaps(r) != null)
        ["Csere-lyukak", _subGaps(r)!],
      if (_wingService(r) != null)
        ["Szélső-futtatás", _wingService(r)!],
      if (_pivotService(r) != null)
        ["Beálló-futtatás", _pivotService(r)!],
      if (_fastBreakWaves(r) != null)
        ["Kontra-hullámok", _fastBreakWaves(r)!],
      if (_fastBreakHeadstart(r) != null)
        ["Kontra-elszökés", _fastBreakHeadstart(r)!],
      if (_blockedShooters(r) != null)
        ["Lefogott lövők", _blockedShooters(r)!],
      if (_assistsByRole(r) != null)
        ["Gólpassz-posztok", _assistsByRole(r)!],
      if (_suspEarnerRoles(r) != null)
        ["Kiállítás-posztok", _suspEarnerRoles(r)!],
      if (_blockedByRole(r) != null)
        ["Falba lövő posztok", _blockedByRole(r)!],
      if (_outletTargetRoles(r) != null)
        ["Felhozatal-posztok", _outletTargetRoles(r)!],
      if (_breakShareFade(r) != null)
        ["Kontra-esés", _breakShareFade(r)!],
      if (_wingShotDepth(r) != null)
        ["Szélső-mélység", _wingShotDepth(r)!],
      if (_doublingDefenders(r) != null)
        ["Kettőző emberek", _doublingDefenders(r)!],
      if (_beatenDefenders(r) != null)
        ["Átvert védők", _beatenDefenders(r)!],
      if (_unpressuredAssists(r) != null)
        ["Zavartalan előkészítők", _unpressuredAssists(r)!],
      if (_gapPunishment(r) != null)
        ["Csere-büntetés", _gapPunishment(r)!],
      if (_corridorGoals(r) != null)
        ["Folyosó-gólok", _corridorGoals(r)!],
      if (_concededTempo(r) != null)
        ["Bontó tempó", _concededTempo(r)!],
      if (_concededMomentum(r) != null)
        ["Lendület-gólok", _concededMomentum(r)!],
      if (_wrongfootedKeeper(r) != null)
        ["Becsapott kapus", _wrongfootedKeeper(r)!],
      if (_readingKeeper(r) != null)
        ["Olvasó kapus", _readingKeeper(r)!],
      if (_doublePunishment(r) != null)
        ["Kettőzés-büntetés", _doublePunishment(r)!],
      if (_stepoutPunishment(r) != null)
        ["Kilépés-büntetés", _stepoutPunishment(r)!],
      if (_punishedMisses(r) != null)
        ["Kihagyás-büntetés", _punishedMisses(r)!],
      if (_outletPunishment(r) != null)
        ["Indítás-hiba ára", _outletPunishment(r)!],
      if (_slowAttackCost(r) != null)
        ["Elhúzódó támadás ára", _slowAttackCost(r)!],
      if (_ballsOut(r) != null)
        ["Kidobott labda", _ballsOut(r)!],
      if (_suspensionsByScore(r) != null)
        ["Fegyelem-állás", _suspensionsByScore(r)!],
      if (_sevensByScore(r) != null)
        ["Hetes-állás", _sevensByScore(r)!],
      if (_breaksByScore(r) != null)
        ["Kontra-állás", _breaksByScore(r)!],
      if (_emptyNetByScore(r) != null)
        ["7a6-állás", _emptyNetByScore(r)!],
      if (_gkSaveStreaks(r) != null)
        ["Kapus-sorozat", _gkSaveStreaks(r)!],
      if (_assistFade(r) != null)
        ["Gólpassz-esés", _assistFade(r)!],
      if (_secondChanceFade(r) != null)
        ["Lepattanó-esés", _secondChanceFade(r)!],
      if (_attackMixShift(r) != null)
        ["Szünet-váltás", _attackMixShift(r)!],
      if (_passDirectionByScore(r) != null)
        ["Passz-irány-állás", _passDirectionByScore(r)!],
      if (_gkAssists(r) != null)
        ["Kapus-gólpassz", _gkAssists(r)!],
      if (_passLengthByScore(r) != null)
        ["Passz-hossz-állás", _passLengthByScore(r)!],
      if (_defenseFormShift(r) != null)
        ["Fal-váltás a szünetre", _defenseFormShift(r)!],
      if (_attackSideShift(r) != null)
        ["Oldal-váltás a szünetre", _attackSideShift(r)!],
      if (_blackWindow(r) != null)
        ["Fekete ötperc", _blackWindow(r)!],
      if (_fadingScorers(r) != null)
        ["Eltűnő ember", _fadingScorers(r)!],
      if (_sprintsByScore(r) != null)
        ["Sprint-állás", _sprintsByScore(r)!],
      if (_fadingDefenders(r) != null)
        ["Eltűnő védő", _fadingDefenders(r)!],
      if (_comebackCarriers(r) != null)
        ["Felzárkózás-húzó", _comebackCarriers(r)!],
      if (_excessPlayers(r) != null)
        ["Létszám-hiba", _excessPlayers(r)!],
      if (_doubleShorthand(r) != null)
        ["Kettős emberhátrány", _doubleShorthand(r)!],
      if (_goalPatterns(r) != null)
        ["Gól-minta", _goalPatterns(r)!],
      if (_finisherRotation(r) != null)
        ["Befejező-váltás", _finisherRotation(r)!],
      if (_reboundRole(r) != null)
        ["Lepattanó-poszt", _reboundRole(r)!],
      if (_bigChanceFeederRole(r) != null)
        ["Ziccer-előkészítő poszt", _bigChanceFeederRole(r)!],
      if (_sevenMissRole(r) != null)
        ["Hetes-kihagyó poszt", _sevenMissRole(r)!],
      if (_bigChancePair(r) != null)
        ["Ziccerpáros-poszt", _bigChancePair(r)!],
      if (_powerplayTurnoverRole(r) != null)
        ["Emberelőny-hiba poszt", _powerplayTurnoverRole(r)!],
      if (_responseTurnoverRole(r) != null)
        ["Válaszhiba-poszt", _responseTurnoverRole(r)!],
      if (_timeoutTurnoverRole(r) != null)
        ["Időkérés-hiba poszt", _timeoutTurnoverRole(r)!],
      if (_retreatTime(r) != null)
        ["Visszaállás-idő", _retreatTime(r)!],
      if (_postGoalRush(r) != null)
        ["Kapkodás-index", _postGoalRush(r)!],
      if (_shorthandedTurnoverRole(r) != null)
        ["Emberhátrány-hiba poszt", _shorthandedTurnoverRole(r)!],
      if (_clutchKeeper(r) != null)
        ["Hajrá-kapus", _clutchKeeper(r)!],
      if (_setplayConcentration(r) != null)
        ["Figura-koncentráció", _setplayConcentration(r)!],
      if (_defensiveReboundRole(r) != null)
        ["Lepattanó-szedő poszt", _defensiveReboundRole(r)!],
      if (_retreatPunishment(r) != null)
        ["Visszaállás ára", _retreatPunishment(r)!],
      if (_reboundPunishment(r) != null)
        ["Kipattanó ára", _reboundPunishment(r)!],
      if (_clockManagement(r) != null)
        ["Óralopás", _clockManagement(r)!],
      if (_sprintFade(r) != null)
        ["Sprint-esés", _sprintFade(r)!],
      if (_sevenMissPlayer(r) != null)
        ["Hetes-kihagyó ember", _sevenMissPlayer(r)!],
      if (_suspensionChain(r) != null)
        ["Kétperc-páros", _suspensionChain(r)!],
      if (_reboundCollector(r) != null)
        ["Kipattanó-szedő ember", _reboundCollector(r)!],
      if (_markingShift(r) != null)
        ["Emberfogás-váltás", _markingShift(r)!],
      if (_suspensionCost(r) != null)
        ["Kétperc ára", _suspensionCost(r)!],
      if (_keyPlayer(r) != null)
        ["Kulcs-ember", _keyPlayer(r)!],
      if (_lastHolderRole(r) != null)
        ["Vég-birtokos poszt", _lastHolderRole(r)!],
      if (_pressOutletRole(r) != null)
        ["Menekülő-poszt", _pressOutletRole(r)!],
      if (_timeoutPairRole(r) != null)
        ["Időkéréspáros-poszt", _timeoutPairRole(r)!],
      if (_laneSwitchRole(r) != null)
        ["Sávváltó-poszt", _laneSwitchRole(r)!],
      if (_recoveryRole(r) != null)
        ["Elöl lógó poszt", _recoveryRole(r)!],
      if (_responseScorerRole(r) != null)
        ["Válasz-poszt", _responseScorerRole(r)!],
      if (_powerplayPairRole(r) != null)
        ["Emberelőnypáros-poszt", _powerplayPairRole(r)!],
      if (_specialistRole(r) != null)
        ["Specialista-poszt", _specialistRole(r)!],
      if (_keyPair(r) != null)
        ["Kulcs-páros", _keyPair(r)!],
      if (_reboundPairRole(r) != null)
        ["Lepattanópáros-poszt", _reboundPairRole(r)!],
      if (_doublingPairRole(r) != null)
        ["Kettőzőpáros-poszt", _doublingPairRole(r)!],
      if (_assistPairRole(r) != null)
        ["Gólpasszpáros-poszt", _assistPairRole(r)!],
      if (_fastBreakPairRole(r) != null)
        ["Kontrapáros-poszt", _fastBreakPairRole(r)!],
      if (_sevenPairRole(r) != null)
        ["Hetespáros-poszt", _sevenPairRole(r)!],
      if (_swapStyle(r) != null)
        ["Csere-stílus", _swapStyle(r)!],
      if (_screenPairRole(r) != null)
        ["Elzárópáros-poszt", _screenPairRole(r)!],
      if (_staticAttackerRole(r) != null)
        ["Álló-poszt", _staticAttackerRole(r)!],
      if (_highStealRole(r) != null)
        ["Letámadó-poszt", _highStealRole(r)!],
      if (_targetedDefenderRole(r) != null)
        ["Célkereszt-poszt", _targetedDefenderRole(r)!],
      if (_coveredShooterRole(r) != null)
        ["Fedezett-lövő poszt", _coveredShooterRole(r)!],
      if (_fadingDefenderRole(r) != null)
        ["Védőmotor-poszt", _fadingDefenderRole(r)!],
      if (_breakthroughRole(r) != null)
        ["Áttörő-poszt", _breakthroughRole(r)!],
      if (_costlyTurnoverRole(r) != null)
        ["Drága-eladó poszt", _costlyTurnoverRole(r)!],
      if (_subInRole(r) != null)
        ["Beérkező-poszt", _subInRole(r)!],
      if (_substitutedRole(r) != null)
        ["Forgatott-poszt", _substitutedRole(r)!],
      if (_tiredConcederRole(r) != null)
        ["Fáradt-fal poszt", _tiredConcederRole(r)!],
      if (_tiredShooterRole(r) != null)
        ["Fáradt-lövő poszt", _tiredShooterRole(r)!],
      if (_tiredTurnoverRole(r) != null)
        ["Fáradt-eladó poszt", _tiredTurnoverRole(r)!],
      if (_backwardPassRole(r) != null)
        ["Hátrapassz-poszt", _backwardPassRole(r)!],
      if (_ballCarrierRole(r) != null)
        ["Térnyerő-poszt", _ballCarrierRole(r)!],
      if (_leadScorerRole(r) != null)
        ["Előnyben-poszt", _leadScorerRole(r)!],
      if (_lastPassRole(r) != null)
        ["Előkészítő-poszt", _lastPassRole(r)!],
      if (_attackStarterRole(r) != null)
        ["Indító-poszt", _attackStarterRole(r)!],
      if (_pivotGuardRole(r) != null)
        ["Beállóőr-poszt", _pivotGuardRole(r)!],
      if (_advancedDefRole(r) != null)
        ["Kilépő-poszt", _advancedDefRole(r)!],
      if (_missedChanceRole(r) != null)
        ["Ziccerhagyó-poszt", _missedChanceRole(r)!],
      if (_blockedShooterRole(r) != null)
        ["Blokkolt-poszt", _blockedShooterRole(r)!],
      if (_sevenTakerRole(r) != null)
        ["Hetesdobó-poszt", _sevenTakerRole(r)!],
      if (_secondStartRole(r) != null)
        ["Újrakezdő-poszt", _secondStartRole(r)!],
      if (_screenedDefRole(r) != null)
        ["Elzárt-poszt", _screenedDefRole(r)!],
      if (_doubledTargetRole(r) != null)
        ["Kettőzött-poszt", _doubledTargetRole(r)!],
      if (_fatigueRole(r) != null)
        ["Fáradó-poszt", _fatigueRole(r)!],
      if (_passiveHolderRole(r) != null)
        ["Passzív-poszt", _passiveHolderRole(r)!],
      if (_openingScorerRole(r) != null)
        ["Rajt-poszt", _openingScorerRole(r)!],
      if (_assistedScorerRole(r) != null)
        ["Kiszolgált-poszt", _assistedScorerRole(r)!],
      if (_clutchHogRole(r) != null)
        ["Hajrákéz-poszt", _clutchHogRole(r)!],
      if (_softPassRole(r) != null)
        ["Lágypassz-poszt", _softPassRole(r)!],
      if (_sprintThreatRole(r) != null)
        ["Sprint-poszt", _sprintThreatRole(r)!],
      if (_restartTakerRole(r) != null)
        ["Középkezdő-poszt", _restartTakerRole(r)!],
      if (_hotHandRole(r) != null)
        ["Forró-poszt", _hotHandRole(r)!],
      if (_clutchTurnoverRole(r) != null)
        ["Hajráhiba-poszt", _clutchTurnoverRole(r)!],
      if (_fadingRole(r) != null)
        ["Eltűnő-poszt", _fadingRole(r)!],
      if (_droughtBreakRole(r) != null)
        ["Csendtörő-poszt", _droughtBreakRole(r)!],
      if (_pressSensRole(r) != null)
        ["Pressz-poszt", _pressSensRole(r)!],
      if (_holdShareRole(r) != null)
        ["Labdatartó-poszt", _holdShareRole(r)!],
      if (_bigChanceRole(r) != null)
        ["Ziccer-poszt", _bigChanceRole(r)!],
      if (_wastefulRole(r) != null)
        ["Pazarló-poszt", _wastefulRole(r)!],
      if (_comebackRole(r) != null)
        ["Felzárkózás-poszt", _comebackRole(r)!],
      if (_clutchRole(r) != null)
        ["Hajrá-poszt", _clutchRole(r)!],
      if (_shorthandedRole(r) != null)
        ["Emberhátrány-poszt", _shorthandedRole(r)!],
      if (_powerplayRole(r) != null)
        ["Emberelőny-poszt", _powerplayRole(r)!],
      if (_kickoutRole(r) != null)
        ["Kiosztás-poszt", _kickoutRole(r)!],
      if (_doublingRole(r) != null)
        ["Kettőző-poszt", _doublingRole(r)!],
      if (_riskyPasserRole(r) != null)
        ["Kockáztató-poszt", _riskyPasserRole(r)!],
      if (_ironManRole(r) != null)
        ["Vasember-poszt", _ironManRole(r)!],
      if (_pivotFeederRole(r) != null)
        ["Bejátszó-poszt", _pivotFeederRole(r)!],
      if (_outletHunterRole(r) != null)
        ["Indítás-vadász poszt", _outletHunterRole(r)!],
      if (_keyPost(r) != null)
        ["Kulcs-poszt", _keyPost(r)!],
      if (_screenSetterRole(r) != null)
        ["Elzáró-poszt", _screenSetterRole(r)!],
      if (_beatenRole(r) != null)
        ["Átvert-poszt", _beatenRole(r)!],
      if (_slowRetreatRole(r) != null)
        ["Visszafutás-poszt", _slowRetreatRole(r)!],
      if (_suspendedRole(r) != null)
        ["Kiülő-poszt", _suspendedRole(r)!],
      if (_sevenConcederRole(r) != null)
        ["Hetes-okozó poszt", _sevenConcederRole(r)!],
      if (_sevenSixRole(r) != null)
        ["7a6-befejező", _sevenSixRole(r)!],
      if (_blockRole(r) != null)
        ["Blokk-poszt", _blockRole(r)!],
      if (_stealRole(r) != null)
        ["Labdaszerző-poszt", _stealRole(r)!],
      if (_assistRole(r) != null)
        ["Gólpassz-poszt", _assistRole(r)!],
      if (_sevenSide(r) != null)
        ["Hetes-oldal", _sevenSide(r)!],
      if (_fastBreakRole(r) != null)
        ["Kontra-poszt", _fastBreakRole(r)!],
      if (_shotChoice(r) != null)
        ["Lövésválasztás", _shotChoice(r)!],
      if (_timeoutFinisher(r) != null)
        ["Időkérés-befejező", _timeoutFinisher(r)!],
      if (_setplayFinisher(r) != null)
        ["Figura-befejező", _setplayFinisher(r)!],
      if (_pressureFinishRole(r) != null)
        ["Poszt-nyomás", _pressureFinishRole(r)!],
      if (_goalPlacementRole(r) != null)
        ["Poszt-kapuoldal", _goalPlacementRole(r)!],
      if (_shotPowerRole(r) != null)
        ["Poszt-lövéserő", _shotPowerRole(r)!],
      if (_shotTimingRole(r) != null)
        ["Poszt-lövésidőzítés", _shotTimingRole(r)!],
      if (_shotDistanceRole(r) != null)
        ["Poszt-lövéstávolság", _shotDistanceRole(r)!],
      if (_turnoverZoneRole(r) != null)
        ["Poszt-eladási zóna", _turnoverZoneRole(r)!],
      if (_holdTimeRole(r) != null)
        ["Poszt-labdatartás", _holdTimeRole(r)!],
      if (_receiveZone(r) != null)
        ["Poszt-átvételi zóna", _receiveZone(r)!],
      if (_passLane(r) != null)
        ["Poszt-passzháló", _passLane(r)!],
      if (_possessionRole(r) != null)
        ["Poszt-birtoklás", _possessionRole(r)!],
      if (_trailingFinisher(r) != null)
        ["Hátrány-befejezés", _trailingFinisher(r)!],
      if (_turnoverCostRole(r) != null)
        ["Eladás-ár posztonként", _turnoverCostRole(r)!],
      if (_halftimeRoleShift(r) != null)
        ["Poszt-váltás a szünetre", _halftimeRoleShift(r)!],
      if (_assistAxis(r) != null)
        ["Gólpassz-tengely", _assistAxis(r)!],
      if (_roleEfficiency(r) != null)
        ["Poszt-hatékonyság", _roleEfficiency(r)!],
      if (_kickoutTarget(r) != null)
        ["Kiosztás-célpont", _kickoutTarget(r)!],
      if (_priorityFocus(r) != null)
        ["Felkészülés-súlypont", _priorityFocus(r)!],
      if (_turnoversByScore(r) != null)
        ["Hiba-állás", _turnoversByScore(r)!],
      if (_defenseByScore(r) != null)
        ["Előny-védekezés", _defenseByScore(r)!],
      if (_subsByScore(r) != null)
        ["Csere-állás", _subsByScore(r)!],
      if (_outletPaceByScore(r) != null)
        ["Indítás-állás", _outletPaceByScore(r)!],
      if (_crossingRuns(r) != null)
        ["Keresztjáték", _crossingRuns(r)!],
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
    return _metricsWall(tiles);
  }

  /// A mutató-csoportok sorrendje — ez adja a szekciók sorrendjét is.
  /// A rendezés a legspecifikusabbtól halad az általános felé, mert az
  /// első illeszkedő szabály nyer (pl. a "Kapus-védés posztonként" a
  /// KAPUS csoportba tartozik, nem a posztokba).
  static const List<(String, List<String>)> _metricGroups = [
    ("Kapus", ["kapus", "bravúr", "becsapott", "olvasó", "kipattanó",
               "hetes-védés", "kapu-sarok"]),
    ("Posztok", ["poszt"]),
    ("Szabály és létszám", ["hetes", "kiállítás", "fegyelem",
                            "emberelőny", "emberhátrány", "létszám", "kétperc",
                            "előny-", "hátrány-", "kettős ember"]),
    ("Idő, állás, forma", ["-állás", "állás szerint", "félidő", "félidei",
                           "szünet", "hajrá", "negyedóra", "ötperc",
                           "-esés", "fáradás", "holtpont", "ritmus",
                           "sorozat", "lendület", "elalvás", "gólcsend",
                           "csend-", "hidegedés", "bemelegedés",
                           "utolsó labda", "meccsek", "percek", "forró",
                           "hosszú áll", "kapkodás", "óra"]),
    ("Védekezés", ["véd", "fal", "kettőz", "emberfog", "blokk", "szerz",
                   "betörés", "kilép", "átvert", "lefogott", "őr",
                   "kifutás", "visszaérés", "visszaállás", "press",
                   "engedett", "kapott", "keménység", "mélység",
                   "folyosó", "szorult", "elöl szerző", "zóna"]),
    ("Támadás és befejezés", ["támad", "lövés", "lövő", "gól", "passz",
                              "beálló", "szélső", "elzár", "kontra",
                              "lerohan", "felhozatal", "kihozatal",
                              "indítás", "labdatartás", "forgatás",
                              "ziccer", "befejez", "célzás", "oldal",
                              "xg", "tempó", "birtoklás", "figur",
                              "keresztjáték", "roham", "áttörő",
                              "kivárás", "bontó", "kiosztás",
                              "előkészít", "asszist", "elsütés",
                              "középkezdés", "labda", "elad", "hiba",
                              "kockázatos", "pontatlan", "fedezett",
                              "kihagy"]),
    ("Emberek és cserék", ["csere", "váltó", "váltott", "rotáció",
                           "pad-", "sprint", "futás", "játékos",
                           "kezd", "ember", "páros", "időkérés",
                           "területi", "támogatás", "mérleg",
                           "felkészülés"]),
  ];

  /// Mindig látható mutatók: ezekkel kezdi az edző, ezért nem kell
  /// hozzájuk se keresés, se lenyitás.
  static const List<String> _coreMetrics = [
    "Lövés / gól",
    "Gólarány",
    "Labdabirtoklás",
    "Labdaeladás",
    "Szervezett támadás",
    "Gyors indítás",
    "Tempó",
    "Felkészülés-súlypont",
  ];

  /// Egy mutató csoportja a címkéje alapján (az első illeszkedő szabály
  /// nyer). Ismeretlen címke az "Egyéb" csoportba kerül — így egy új
  /// réteg csempéje sem tűnhet el a falról.
  String _metricGroupOf(String label) {
    final low = label.toLowerCase();
    for (final g in _metricGroups) {
      for (final k in g.$2) {
        if (low.contains(k)) return g.$1;
      }
    }
    return "Egyéb";
  }

  /// A mutató-fal: kiemelt sáv + kereső + lenyitható csoportok.
  Widget _metricsWall(List<List<String>> tiles) {
    final q = _metricQuery.trim().toLowerCase();
    final core = <List<String>>[
      for (final name in _coreMetrics)
        ...tiles.where((t) => t[0] == name),
    ];
    // Csoportosítás a megjelenítéshez (a nyers lista érintetlen marad).
    final grouped = <String, List<List<String>>>{};
    for (final t in tiles) {
      grouped.putIfAbsent(_metricGroupOf(t[0]), () => []).add(t);
    }
    final order = <String>[for (final g in _metricGroups) g.$1, "Egyéb"];
    final hits = q.isEmpty
        ? tiles.length
        : tiles.where((t) => t[0].toLowerCase().contains(q)).length;

    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Text("MUTATÓK", style: AppText.sectionLabel),
            const SizedBox(width: AppSpacing.sm),
            Text(q.isEmpty
                    ? "${tiles.length} mérőszám"
                    : "$hits találat ${tiles.length} mérőszámból",
                style: AppText.label.copyWith(fontSize: 11)),
            const Spacer(),
            SizedBox(
              width: 240,
              child: TextField(
                onChanged: (v) => setState(() => _metricQuery = v),
                style: AppText.value.copyWith(fontSize: 13),
                decoration: InputDecoration(
                  isDense: true,
                  hintText: "Keresés a mutatók közt…",
                  hintStyle: AppText.label.copyWith(fontSize: 12),
                  prefixIcon: const Icon(Icons.search, size: 18),
                  suffixIcon: q.isEmpty
                      ? null
                      : IconButton(
                          icon: const Icon(Icons.clear, size: 16),
                          onPressed: () =>
                              setState(() => _metricQuery = ""),
                        ),
                ),
              ),
            ),
          ]),
          const SizedBox(height: AppSpacing.md),
          // Kiemelt sáv: keresés közben elrejtjük, hogy a találat legyen
          // a fókuszban.
          if (q.isEmpty && core.isNotEmpty) ...[
            Wrap(
              spacing: AppSpacing.lg,
              runSpacing: AppSpacing.md,
              children: [for (final t in core) _metricTile(t[0], t[1])],
            ),
            const SizedBox(height: AppSpacing.lg),
            const Divider(height: 1),
            const SizedBox(height: AppSpacing.md),
          ],
          for (final name in order)
            if (grouped[name] != null)
              _metricGroupSection(name, grouped[name]!, q),
          if (q.isNotEmpty && hits == 0)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.md),
              child: Text("Nincs \"$_metricQuery\" nevű mutató.",
                  style: AppText.label),
            ),
        ],
      ),
    );
  }

  /// Egy csoport-szekció: fejléc (név + darabszám) és lenyitott tartalom.
  /// Keresés közben a találatot tartalmazó csoport magától nyílik.
  Widget _metricGroupSection(
      String name, List<List<String>> items, String query) {
    final shown = query.isEmpty
        ? items
        : items.where((t) => t[0].toLowerCase().contains(query)).toList();
    if (shown.isEmpty) return const SizedBox.shrink();
    final open = query.isNotEmpty || _openMetricGroups.contains(name);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: query.isNotEmpty
              ? null
              : () => setState(() {
                    if (!_openMetricGroups.remove(name)) {
                      _openMetricGroups.add(name);
                    }
                  }),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
            child: Row(children: [
              Icon(open ? Icons.expand_less : Icons.expand_more,
                  size: 18, color: AppColors.textSecondary),
              const SizedBox(width: 6),
              Text(name.toUpperCase(), style: AppText.sectionLabel),
              const SizedBox(width: AppSpacing.sm),
              Text("${shown.length}",
                  style: AppText.label.copyWith(fontSize: 11)),
            ]),
          ),
        ),
        if (open) ...[
          Wrap(
            spacing: AppSpacing.lg,
            runSpacing: AppSpacing.md,
            children: [for (final t in shown) _metricTile(t[0], t[1])],
          ),
          const SizedBox(height: AppSpacing.md),
        ],
      ],
    );
  }

  /// Ennyi karakterig számít az érték "számnak" (nagy betű, keskeny
  /// csempe). Fölötte mondat — annak olvasható méret és szélesebb hely
  /// kell.
  static const int _shortValueChars = 12;

  /// A mondat-értékek ennyi sor után elvágódnak (a teljes szöveg a
  /// súgóbuborékban marad meg).
  static const int _metricValueMaxLines = 3;

  /// Egy mutató-csempe.
  ///
  /// A csempék értéke NEM szám: a 283 csempe-mutató 371 lehetséges
  /// visszatérési szövegéből 369 hosszabb 12 karakternél — jellemzően
  /// egész mondat ("62% elöl · területi nyomás"). A régi csempe ezt
  /// 20 pontos betűvel, 150 pixeles dobozban rajzolta, így négy-öt
  /// sorba tört: a fal ragadozott lett, és a szem nem találta meg,
  /// hol ér véget az egyik csempe és hol kezdődik a másik.
  ///
  /// Mostantól a csempe az érték HOSSZÁHOZ igazodik:
  ///   - rövid érték → a régi, nagy szám-kinézet,
  ///   - mondat → olvasható törzsméret, szélesebb doboz, három sor
  ///     után elvágva; a teljes szöveg a súgóbuborékban.
  /// A címke KERÜL ELŐRE: a fal átfutásakor azt keresi az edző, nem az
  /// értéket.
  Widget _metricTile(String label, String value) {
    final short = value.length <= _shortValueChars;
    return SizedBox(
      width: short ? 150 : 240,
      child: Tooltip(
        message: "$label — $value",
        waitDuration: const Duration(milliseconds: 400),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style: AppText.label
                    .copyWith(fontSize: 11, color: AppColors.textFaint),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
            const SizedBox(height: 3),
            Text(value,
                style: AppText.value.copyWith(
                    fontSize: short ? 20 : 13,
                    height: short ? 1.0 : 1.35,
                    color: AppColors.accent),
                maxLines: short ? 1 : _metricValueMaxLines,
                overflow: TextOverflow.ellipsis),
          ],
        ),
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

  /// Kapus-felkészítés posztonként: a poszt-lencse három lövés-rétege
  /// EGY táblában — milyen messziről, milyen keményen, merre lő az adott
  /// poszt. Külön csempeként a kapusedző háromszor keresi meg ugyanazt a
  /// posztot; itt egy pillantás.
  ///
  /// Küszöbök a backenddel azonosak: posztonként 4 mért lövés, az oldal
  /// pedig 60% részaránytól szólal meg.
  Widget? _keeperPrepCard(Map<String, dynamic> r) {
    final shots = (r["rsd_shots_by_role"] as Map?)?.cast<String, dynamic>();
    final dists = (r["rsd_dist_sum_by_role"] as Map?)?.cast<String, dynamic>();
    final pShots = (r["rsp_shots_by_role"] as Map?)?.cast<String, dynamic>();
    final kmh = (r["rsp_kmh_sum_by_role"] as Map?)?.cast<String, dynamic>();
    final sidesRaw =
        (r["rgp_goals_by_role_side"] as Map?)?.cast<String, dynamic>();

    final sides = <String, Map<String, int>>{};
    sidesRaw?.forEach((k, v) {
      final i = k.indexOf("|");
      if (i <= 0) return;
      sides.putIfAbsent(k.substring(0, i), () => {})[k.substring(i + 1)] =
          (v as num).toInt();
    });

    final posts = <String>{
      ...?shots?.keys, ...?pShots?.keys, ...sides.keys
    }.toList()
      ..sort();

    final rows = <List<String>>[];
    for (final post in posts) {
      final nd = ((shots?[post] as num?) ?? 0).toInt();
      final dist = nd >= 4
          ? "${(((dists?[post] as num?) ?? 0).toDouble() / nd).toStringAsFixed(1)} m"
          : "—";
      final np = ((pShots?[post] as num?) ?? 0).toInt();
      final power = np >= 4
          ? "${(((kmh?[post] as num?) ?? 0).toDouble() / np).round()} km/h"
          : "—";
      var side = "—";
      final sm = sides[post];
      if (sm != null) {
        final tot = sm.values.fold(0, (a, b) => a + b);
        if (tot >= 4) {
          final dom = sm.keys.reduce((a, b) => sm[a]! >= sm[b]! ? a : b);
          final pct = 100.0 * sm[dom]! / tot;
          if (pct >= 60.0) side = "$dom (${pct.round()}%)";
        }
      }
      if (dist == "—" && power == "—" && side == "—") continue;
      rows.add([post, dist, power, side]);
    }
    if (rows.isEmpty) return null;   // adat nélkül nincs kártya

    Widget cell(String t, {bool head = false, int flex = 1}) => Expanded(
          flex: flex,
          child: Text(t,
              style: head
                  ? AppText.label.copyWith(fontSize: 11)
                  : AppText.value.copyWith(fontSize: 13)),
        );

    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("KAPUS-FELKÉSZÍTÉS POSZTONKÉNT", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          Row(children: [
            cell("Poszt", head: true, flex: 2),
            cell("Honnan lő", head: true),
            cell("Milyen keményen", head: true),
            cell("Merre lő", head: true),
          ]),
          const Divider(height: 12),
          for (final row in rows)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(children: [
                cell(row[0], flex: 2),
                cell(row[1]),
                cell(row[2]),
                cell(row[3]),
              ]),
            ),
          const SizedBox(height: AppSpacing.sm),
          Text(
              "A „—” azt jelenti, hogy abból a bontásból még nincs elég "
              "mért lövés (posztonként 4 kell). A „merre” csak 60% "
              "részaránytól szólal meg.",
              style: AppText.label.copyWith(fontSize: 11)),
        ],
      ),
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
