/// Játékos-fejlődés képernyő — egy játékos terhelése meccsről meccsre.
///
/// A mezszám-hozzárendelésre épül: csapat + mezszám megadása után minden
/// tárolt meccsből kigyűjti a játékos táv/max sebesség/sprint mutatóit,
/// időrendben. Az edző így látja a szezon-terhelést és a formagörbét —
/// pl. hogy a sérülés utáni visszatérésnél hol tart a játékos.
library;

import "dart:io";

import "package:file_picker/file_picker.dart";
import "package:flutter/material.dart";

import "anim.dart";
import "clips_screen.dart";
import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "shell/app_shell.dart";
import "error_text.dart";

class PlayerTrendScreen extends StatefulWidget {
  /// A csapatnevek a meccs-könyvtárból (a választóhoz). Üresen hagyva a
  /// képernyő maga tölti be — így a menüből közvetlenül is nyitható.
  final List<String> teams;

  /// Előre kitöltött csapat és mezszám: a keret-lapról egy sorra
  /// koppintva EGYBŐL a játékos görbéje jöjjön, ne egy üres űrlap.
  final String? initialTeam;
  final int? initialJersey;

  const PlayerTrendScreen({
    super.key,
    this.teams = const [],
    this.initialTeam,
    this.initialJersey,
  });

  @override
  State<PlayerTrendScreen> createState() => _PlayerTrendScreenState();
}

class _PlayerTrendScreenState extends State<PlayerTrendScreen> {
  final ApiClient _api = ApiClient();
  final TextEditingController _jerseyCtrl = TextEditingController();

  List<String> _teams = [];
  String? _team;
  bool _loading = false;
  String? _error;
  List<Map<String, dynamic>> _points = [];
  // SZEZON-szintű egyéni edzés-fókusz: mit gyakoroljon. Ez az a rész,
  // amiért a játékos elteszi a lapot — a görbe mellett a teendő.
  List<Map<String, dynamic>> _focus = [];

  // Forma-irány: mutatónként {recent, before, change_pct, verdict}.
  // A verdict None is lehet (kevés meccs vagy zajsávon belüli
  // változás) — akkor SZÁMOT mutatunk, ítéletet nem.
  Map<String, dynamic> _trend = {};
  int _trendWindow = 3;
  // A mezszámhoz felvitt játékos-név (a Keret-lapon adható meg). Ha van,
  // a cím a NEVET mutatja: a lapot a játékos kapja a kezébe.
  String? _name;

  @override
  void initState() {
    super.initState();
    _teams = List.of(widget.teams);
    if (widget.initialTeam != null && !_teams.contains(widget.initialTeam)) {
      _teams.insert(0, widget.initialTeam!);
    }
    _team = widget.initialTeam ?? (_teams.isNotEmpty ? _teams.first : null);
    if (widget.teams.isEmpty) {
      _loadTeams(); // menüből nyitva: csapatnevek a könyvtárból
    }
    if (widget.initialJersey != null) {
      _jerseyCtrl.text = "${widget.initialJersey}";
      // A keret-lapról érkezve a görbe azonnal töltsön: a kattintás
      // maga volt a kérés, nincs mit még egyszer megerősíteni.
      WidgetsBinding.instance.addPostFrameCallback((_) => _load());
    }
  }

  Future<void> _loadTeams() async {
    try {
      final ms = await _api.listMatches();
      if (!mounted) return;
      final teams = <String>{
        for (final m in ms) ...[
          if (m["home_team"] != null) m["home_team"] as String,
          if (m["away_team"] != null) m["away_team"] as String,
        ]
      }.toList()
        ..sort();
      setState(() {
        _teams = teams;
        if (_team == null && teams.isNotEmpty) _team = teams.first;
      });
    } catch (_) {
      // a képernyő enélkül is használható marad (üres választó)
    }
  }

  @override
  void dispose() {
    _jerseyCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final team = _team;
    final jersey = int.tryParse(_jerseyCtrl.text.trim());
    if (team == null || jersey == null) {
      setState(() => _error = "Válassz csapatot és adj meg mezszámot.");
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final r = await _api.fetchPlayerTrend(team, jersey);
      if (!mounted) return;
      setState(() {
        _points = (r["points"] as List).cast<Map<String, dynamic>>();
        _name = r["name"] as String?;
        _trend = ((r["trend"] as Map?) ?? const {})
            .cast<String, dynamic>();
        _trendWindow = (r["trend_window"] as num?)?.toInt() ?? _trendWindow;
        _loading = false;
      });
      // A fókusz külön kérés: hosszabb (minden meccset átnéz), és a
      // görbe nélküle is teljes — ne várakoztassa meg.
      try {
        final f = await _api.fetchPlayerFocus(team, jersey);
        if (!mounted) return;
        setState(() => _focus = f);
      } catch (_) {
        if (mounted) setState(() => _focus = []);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = "${humanError(e)}";
        _loading = false;
      });
    }
  }

  /// A szezon-lap letöltése és mentése a választott helyre.
  Future<void> _saveSeasonReport() async {
    final team = _team;
    final jersey = int.tryParse(_jerseyCtrl.text.trim());
    if (team == null || jersey == null) return;
    try {
      final bytes = await _api.fetchPlayerSeasonReport(team, jersey);
      if (!mounted) return;
      final safe = team.replaceAll(
          RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+"), "_");
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Szezon-lap mentése (HTML)",
        fileName: "szezon_lap_${safe}_$jersey.html",
        type: FileType.custom,
        allowedExtensions: const ["html"],
      );
      if (path == null) return; // a felhasználó megszakította
      await File(path).writeAsBytes(bytes);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Szezon-lap mentve: $path — böngészőből "
              "nyomtatható, kiosztható")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text("Szezon-lap hiba: ${humanError(e)}")));
    }
  }

  /// A Klipek lap a JÁTÉKOS mezszámával előre kijelölve. Ha a beírt
  /// mezszám még üres, a képernyő a szokásos (csapat-szintű) alakban
  /// nyílik — nem hibázunk, csak nem szűkítünk.
  // Szezon-válogatás állapota: fut-e, és mit üzen a motor.
  bool _seasonWorking = false;
  String _seasonMsg = "";

  /// Szezon-válogatás: a játékos ÖSSZES meccséből egy zip, meccsenkénti
  /// mappákkal. A vágás percekbe telhet — a gombon fut a haladás.
  Future<void> _seasonClips() async {
    final team = _team;
    final jersey = int.tryParse(_jerseyCtrl.text.trim());
    if (team == null || jersey == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text("Előbb válassz csapatot és adj meg mezszámot.")));
      return;
    }
    setState(() {
      _seasonWorking = true;
      _seasonMsg = "indítás…";
    });
    try {
      final jobId = await _api.startSeasonClips(team, jersey);
      String zaroUzenet = "";
      while (true) {
        await Future.delayed(const Duration(seconds: 1));
        if (!mounted) return;
        final job = await _api.fetchJob(jobId);
        final status = job["status"] as String?;
        setState(() =>
            _seasonMsg = (job["message"] as String?) ?? _seasonMsg);
        if (status == "done") {
          zaroUzenet = (job["message"] as String?) ?? "";
          break;
        }
        if (status == "error") {
          throw Exception(job["error"] ?? "ismeretlen hiba");
        }
      }
      final bytes = await _api.fetchSeasonClipsZip(team, jersey);
      if (!mounted) return;
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Szezon-válogatás mentése (zip)",
        fileName: "szezon_valogatas_#${jersey}_$team.zip".replaceAll(
            RegExp(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ#.-]+"), "_"),
        type: FileType.custom,
        allowedExtensions: const ["zip"],
      );
      if (path != null) {
        await File(path).writeAsBytes(bytes);
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text("Szezon-válogatás mentve: $path — "
                "$zaroUzenet")));
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content:
              Text("Szezon-válogatás hiba: ${humanError(e)}")));
    } finally {
      if (mounted) setState(() => _seasonWorking = false);
    }
  }

  void _openMyClips({List<String> types = const []}) {
    final jersey = int.tryParse(_jerseyCtrl.text.trim());
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ClipsScreen(
        initialJersey: jersey,
        initialTypes: types,
      ),
    ));
  }

  /// Egy fókusz-tétel klip-típusai. A backend üres listát is adhat (az
  /// erőnlétet egyetlen jelenet sem mutatja meg), és régebbi
  /// kiszolgálón a mező hiányozhat — mindkettő "nincs ajánlás".
  List<String> _clipsOf(Map<String, dynamic> f) {
    final raw = f["clips"];
    if (raw is! List) return const [];
    return [for (final e in raw) if (e is String) e];
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.playerTrend,
      crumbPath: "CSAPAT · JÁTÉKOS-FEJLŐDÉS",
      child: ListView(
        children: [
          Text(
              _name != null && _name!.isNotEmpty
                  ? "$_name — játékos-fejlődés"
                  : "Játékos-fejlődés",
              style: AppText.title),
          const SizedBox(height: 4),
          Text("egy játékos terhelése meccsről meccsre — mezszám alapján "
              "(a meccs-nézetben rendelj számot a játékoshoz)",
              style: AppText.subtitle),
          const SizedBox(height: AppSpacing.xl),
          Row(children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.border),
              ),
              child: DropdownButton<String>(
                value: _team,
                hint: Text("Csapat", style: AppText.label),
                underline: const SizedBox(),
                dropdownColor: AppColors.surfaceAlt,
                items: [
                  for (final t in _teams)
                    DropdownMenuItem(value: t, child: Text(t)),
                ],
                onChanged: (t) => setState(() => _team = t),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            SizedBox(
              width: 120,
              child: TextField(
                controller: _jerseyCtrl,
                keyboardType: TextInputType.number,
                style: AppText.value,
                decoration: InputDecoration(
                  isDense: true,
                  labelText: "Mezszám",
                  labelStyle: AppText.label,
                ),
                onSubmitted: (_) => _load(),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            FilledButton.icon(
              onPressed: _loading ? null : _load,
              icon: _loading
                  ? const SizedBox(width: 16, height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.timeline, size: 18),
              label: const Text("Lekérdezés"),
            ),
            // A SAJÁT klipek: a játékos a számok után a videót akarja
            // látni. Enélkül a Klipek menüben újra ki kellene keresnie
            // magát a keretből.
            const SizedBox(width: AppSpacing.md),
            OutlinedButton.icon(
              onPressed: _openMyClips,
              icon: const Icon(Icons.movie_creation_outlined, size: 17),
              label: const Text("Klipjeim"),
            ),
            // SZEZON-válogatás: az összes meccs góljai egy zip-ben. A
            // meccsenkénti csomag a "Klipjeim"; ez a szezon egésze —
            // amit a játékos megoszt, eltesz, visszanéz.
            const SizedBox(width: AppSpacing.sm),
            OutlinedButton.icon(
              onPressed: _seasonWorking ? null : _seasonClips,
              icon: _seasonWorking
                  ? const SizedBox(width: 15, height: 15,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.video_collection_outlined, size: 17),
              label: Text(_seasonWorking
                  ? _seasonMsg
                  : "Szezon-válogatás"),
            ),
            // Szezon-lap mentése (HTML) — csak ha van megjelenített adat.
            if (_points.isNotEmpty) ...[
              const SizedBox(width: AppSpacing.md),
              IconButton(
                tooltip: "Szezon-lap mentése (HTML)",
                onPressed: _saveSeasonReport,
                icon: const Icon(Icons.badge_outlined,
                    color: AppColors.accent),
              ),
            ],
          ]),
          const SizedBox(height: AppSpacing.lg),
          if (_error != null)
            Text(_error!, style: AppText.label.copyWith(color: AppColors.away)),
          if (!_loading && _error == null && _points.isEmpty)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xl),
              child: Text(
                "Nincs találat. Ellenőrizd, hogy a meccs-nézetben "
                "hozzárendelted-e ezt a mezszámot a játékoshoz.",
                style: AppText.label,
              ),
            ),
          if (_focus.isNotEmpty) ..._focusCard(),
          if (_points.isNotEmpty) ..._results(),
        ],
      ),
    );
  }

  /// MIT GYAKOROLJ — a szezon egyéni edzés-fókusza.
  ///
  /// A görbe megmutatja, hol tart a játékos; ez azt, hogy min kell
  /// dolgoznia. Ami több meccsen visszatér, az nem napi forma —
  /// ezért a meccs-darabszám ott van minden tétel mellett.
  List<Widget> _focusCard() {
    return [
      const SizedBox(height: AppSpacing.xl),
      Text("MIT GYAKOROLJ", style: AppText.sectionLabel),
      const SizedBox(height: AppSpacing.sm),
      Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: AppTheme.card(),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final f in _focus)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Expanded(
                        child: Text("${f["title"]}",
                            style: AppText.value.copyWith(fontSize: 13)),
                      ),
                      Text("${f["count"]} meccsen",
                          style: AppText.label.copyWith(
                              fontSize: 11, color: AppColors.gold)),
                    ]),
                    Text("miért: ${f["why"]}",
                        style: AppText.label.copyWith(
                            fontSize: 11.5,
                            color: AppColors.textPrimary)),
                    Text("gyakorlat: ${f["drill"]}",
                        style: AppText.label.copyWith(
                            fontSize: 11.5, color: AppColors.accent)),
                    // A gyakorlat elmondja, MIT kell csinálni — a
                    // felvétel azt, MIÉRT. A gomb a Klipek lapot
                    // ehhez a hibához illő csomagokkal nyitja.
                    if (_clipsOf(f).isNotEmpty)
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          style: TextButton.styleFrom(
                              padding: EdgeInsets.zero,
                              visualDensity: VisualDensity.compact),
                          onPressed: () => _openMyClips(types: _clipsOf(f)),
                          icon: const Icon(Icons.play_circle_outline,
                              size: 15),
                          label: const Text("Nézd meg a felvételen"),
                        ),
                      ),
                  ],
                ),
              ),
          ],
        ),
      ),
    ];
  }

  List<Widget> _results() {
    final maxDist = _points.fold(
        0.0, (m, p) => (p["distance_m"] as num) > m
            ? (p["distance_m"] as num).toDouble() : m);
    final totalSprints = _points.fold(
        0, (s, p) => s + ((p["sprint_count"] as num?)?.toInt() ?? 0));
    final bestTop = _points.fold(
        0.0, (m, p) => (p["top_speed_ms"] as num) > m
            ? (p["top_speed_ms"] as num).toDouble() : m);
    final totalShots = _points.fold(
        0, (s, p) => s + ((p["shots"] as num?)?.toInt() ?? 0));
    final totalGoals = _points.fold(
        0, (s, p) => s + ((p["goals"] as num?)?.toInt() ?? 0));
    // Szezon-szintű helyzetminőség: összes xG + befejezés-eltérés.
    final totalXg = _points.fold(
        0.0, (s, p) => s + ((p["xg"] as num?)?.toDouble() ?? 0.0));
    final totalXgDiff = _points.fold(
        0.0, (s, p) => s + ((p["xg_diff"] as num?)?.toDouble() ?? 0.0));
    // Kapus-mód: ha bármely meccsen van védés-mérleg, a kapus-oszlopok
    // is megjelennek (azonos adatok a szezon-lappal).
    final isGk = _points.any(
        (p) => ((p["gk_on_target"] as num?)?.toInt() ?? 0) > 0);
    // Emberfogás-mód: ha bármely meccsen van mért őrzés, az Őrzés
    // oszlop is megjelenik (azonos adatok a szezon-lappal).
    final hasMark = _points.any(
        (p) => ((p["mark_s"] as num?)?.toDouble() ?? 0) > 0);
    final markS = _points.fold(
        0.0, (s, p) => s + ((p["mark_s"] as num?)?.toDouble() ?? 0.0));
    final markWeighted = _points.fold(
        0.0,
        (s, p) =>
            s +
            ((p["mark_dist"] as num?)?.toDouble() ?? 0.0) *
                ((p["mark_s"] as num?)?.toDouble() ?? 0.0));
    final gkOn = _points.fold(
        0, (s, p) => s + ((p["gk_on_target"] as num?)?.toInt() ?? 0));
    final gkSaves = _points.fold(
        0, (s, p) => s + ((p["gk_saves"] as num?)?.toInt() ?? 0));
    final gkPrev = _points.fold(
        0.0, (s, p) => s + ((p["gk_prevented"] as num?)?.toDouble() ?? 0.0));
    return [
      // Szezon-összkép.
      Wrap(spacing: AppSpacing.lg, runSpacing: AppSpacing.sm, children: [
        _chip("${_points.length} meccs"),
        _chip("legjobb max sebesség: ${(bestTop * 3.6).toStringAsFixed(1)} km/h"),
        _chip("összes sprint: $totalSprints"),
        if (totalShots > 0)
          _chip("gól/lövés: $totalGoals/$totalShots "
              "(${(100.0 * totalGoals / totalShots).toStringAsFixed(0)}%)"),
        if (totalXg > 0)
          _chip("várható gól: ${totalXg.toStringAsFixed(1)} · befejezés: "
              "${totalXgDiff >= 0 ? "+" : ""}${totalXgDiff.toStringAsFixed(1)}"),
        if (isGk && gkOn > 0)
          _chip("védés: $gkSaves/$gkOn "
              "(${(100.0 * gkSaves / gkOn).toStringAsFixed(0)}%) · GSAx: "
              "${gkPrev >= 0 ? "+" : ""}${gkPrev.toStringAsFixed(1)}"),
        if (hasMark && markS > 0)
          _chip("őrzés: ${markS.toStringAsFixed(0)} mp · átl. "
              "${(markWeighted / markS).toStringAsFixed(1)} m"),
      ]),
      // HOL TARTOK A KERETEN BELÜL — a nyers "4,2 km" magában semmit
      // nem mond, a keret-átlaghoz mérve viszont döntés lesz belőle.
      ..._squadCompare(),
      // JAVULOK VAGY ROMLOK — a pontsorból ezt kinézni nem lehet,
      // mert minden második meccs jobb az előzőnél.
      ..._formCard(),
      const SizedBox(height: AppSpacing.lg),
      // Fejléc + meccsenkénti sorok (táv-csíkkal — a forma ránézésre látszik).
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(children: [
          const SizedBox(width: 170, child: SizedBox()),
          const Expanded(child: SizedBox()),
          _cell("táv", 64),
          _cell("max km/h", 66),
          _cell("sprint", 48),
          _cell("gól/löv", 56),
          _cell("xG ±", 52),
          if (isGk) _cell("védés", 52),
          if (isGk) _cell("GSAx", 50),
          if (hasMark) _cell("őrzés", 66),
          _cell("perc", 44),
        ]),
      ),
      ..._points.map((p) => _row(p, maxDist, isGk, hasMark)),
    ];
  }

  /// Keret-viszonyítás: futómunka perc-re vetítve a keret átlagához
  /// mérve, plusz a helyezés. Csak akkor jelenik meg, ha a backend
  /// adott viszonyítást (kevés mezszámnál / rövid játékidőnél nem).
  ///
  /// PERCRE VETÍTVE hasonlítunk (a backend is így számol): a 60 percet
  /// játszó irányító és a 15 percet játszó szélső nyers métere nem
  /// összemérhető.
  List<Widget> _squadCompare() {
    final velem = [
      for (final p in _points)
        if (p["team_distance_per_min"] != null &&
            p["distance_per_min"] != null)
          p
    ];
    if (velem.isEmpty) return const [];
    double sajat = 0, keret = 0;
    for (final p in velem) {
      sajat += (p["distance_per_min"] as num).toDouble();
      keret += (p["team_distance_per_min"] as num).toDouble();
    }
    sajat /= velem.length;
    keret /= velem.length;
    final elteres = keret > 0 ? 100.0 * (sajat - keret) / keret : 0.0;
    // Az utolsó meccs helyezése — a szezon-átlagnál frissebb kép.
    final utolso = velem.last;
    final hely = (utolso["distance_rank"] as num?)?.toInt();
    final letszam = (utolso["squad_size"] as num?)?.toInt();
    final tobb = elteres >= 0;
    return [
      const SizedBox(height: AppSpacing.md),
      Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: AppTheme.card(),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text("HOL TARTOK A KERETEN BELÜL", style: AppText.sectionLabel),
              const SizedBox(height: AppSpacing.sm),
              Wrap(spacing: AppSpacing.lg, runSpacing: AppSpacing.sm,
                  children: [
                    _chip("futómunka: ${sajat.toStringAsFixed(0)} m/perc"),
                    _chip("keret-átlag: ${keret.toStringAsFixed(0)} m/perc"),
                    _chip("${tobb ? "+" : ""}"
                        "${elteres.toStringAsFixed(0)}% a kerethez képest"),
                    if (hely != null && letszam != null)
                      _chip("a legutóbbi meccsen a $letszam játszó ember "
                          "közül a $hely."),
                  ]),
              const SizedBox(height: AppSpacing.sm),
              Text(
                  "Percre vetítve hasonlítunk: a végig játszó irányító és "
                  "a tizenöt percet kapó szélső nyers métere nem "
                  "összemérhető. A több futómunka önmagában nem jobb — a "
                  "poszt dönti el, mennyi kell belőle.",
                  style: AppText.label.copyWith(fontSize: 11.5)),
            ]),
      ),
    ];
  }

  /// Forma-irány: az utolsó N meccs az azt megelőző N-hez mérve.
  /// Csak akkor jelenik meg, ha a backend adott irányt — kevés
  /// meccsnél nem mondunk semmit, mert egy jó meccs bármikor jön.
  List<Widget> _formCard() {
    const nevek = {
      "shot_pct": "gólarány",
      "xg_diff": "befejezés a helyzetekhez képest",
      "goals": "gól",
    };
    final sorok = [
      for (final e in _trend.entries)
        if (nevek.containsKey(e.key) && e.value is Map) e
    ];
    if (sorok.isEmpty) return const [];
    return [
      const SizedBox(height: AppSpacing.md),
      Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: AppTheme.card(),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text("JAVULOK VAGY ROMLOK", style: AppText.sectionLabel),
              const SizedBox(height: 3),
              Text(
                  "az utolsó $_trendWindow meccs az azt megelőző "
                  "$_trendWindow-hoz mérve",
                  style: AppText.label.copyWith(fontSize: 11.5)),
              const SizedBox(height: AppSpacing.sm),
              for (final e in sorok) _formRow(nevek[e.key]!, e.value as Map),
            ]),
      ),
    ];
  }

  Widget _formRow(String nev, Map rec) {
    final valtozas = (rec["change_pct"] as num?)?.toDouble() ?? 0.0;
    final iteles = rec["verdict"] as String?;
    // Ítélet NÉLKÜL is kiírjuk a számokat: a játékos maga eldöntheti,
    // számít-e neki — de mi nem nevezzük iránynak a zajt.
    final szin = iteles == "javul"
        ? AppColors.home
        : iteles == "romlik"
            ? AppColors.away
            : AppColors.textFaint;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(children: [
        SizedBox(
            width: 230,
            child: Text(nev,
                style: AppText.label.copyWith(fontSize: 12))),
        Text("${rec["before"]} → ${rec["recent"]}",
            style: AppText.value.copyWith(fontSize: 12.5)),
        const SizedBox(width: AppSpacing.sm),
        Text(
            iteles == null
                ? "(${valtozas >= 0 ? "+" : ""}"
                    "${valtozas.toStringAsFixed(0)}% — nem irány, zaj)"
                : "$iteles (${valtozas >= 0 ? "+" : ""}"
                    "${valtozas.toStringAsFixed(0)}%)",
            style: AppText.label.copyWith(fontSize: 11.5, color: szin)),
      ]),
    );
  }

  Widget _chip(String text) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: AppColors.border),
        ),
        child: Text(text, style: AppText.value.copyWith(fontSize: 12)),
      );

  Widget _cell(String text, double width) => SizedBox(
      width: width,
      child: Text(text,
          textAlign: TextAlign.right,
          style: AppText.label.copyWith(fontSize: 10, color: AppColors.textFaint)));

  Widget _row(Map<String, dynamic> p, double maxDist, bool isGk,
      bool hasMark) {
    final dist = (p["distance_m"] as num?)?.toDouble() ?? 0.0;
    final frac = maxDist > 0 ? (dist / maxDist).clamp(0.0, 1.0) : 0.0;
    final date = (p["date"] as String?) ?? "";
    final label = date.isEmpty
        ? "vs ${p["opponent"]}"
        : "$date · vs ${p["opponent"]}";
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(children: [
        SizedBox(
            width: 170,
            child: Text(label,
                overflow: TextOverflow.ellipsis,
                style: AppText.label.copyWith(color: AppColors.textPrimary))),
        Expanded(
          child: AnimatedBar(
              value: frac,
              minHeight: 5,
              borderRadius: BorderRadius.circular(3)),
        ),
        SizedBox(
            width: 64,
            child: Text("${dist.toStringAsFixed(0)} m",
                textAlign: TextAlign.right,
                style: AppText.value.copyWith(fontSize: 13))),
        SizedBox(
            width: 66,
            child: Text(
                (((p["top_speed_ms"] as num?)?.toDouble() ?? 0) * 3.6)
                    .toStringAsFixed(1),
                textAlign: TextAlign.right,
                style: AppText.label.copyWith(
                    fontSize: 13, color: AppColors.accent))),
        SizedBox(
            width: 48,
            child: Text("${p["sprint_count"] ?? 0}×",
                textAlign: TextAlign.right,
                style: AppText.label.copyWith(
                    fontSize: 13, color: AppColors.gold))),
        SizedBox(
            width: 56,
            child: Text(
                ((p["shots"] as num?)?.toInt() ?? 0) > 0
                    ? "${p["goals"] ?? 0}/${p["shots"]}"
                    : "—",
                textAlign: TextAlign.right,
                style: AppText.label.copyWith(
                    fontSize: 13, color: AppColors.textPrimary))),
        // Befejezés-eltérés a meccsen (gól − xG): zöldes = a helyzetei
        // felett, piros = kihagyott helyzetek, — = nem lőtt.
        SizedBox(
            width: 52,
            child: Builder(builder: (_) {
              final d = (p["xg_diff"] as num?)?.toDouble();
              final color = d == null || d.abs() < 0.3
                  ? AppColors.textFaint
                  : (d > 0 ? AppColors.accent : AppColors.away);
              return Text(
                  d == null
                      ? "—"
                      : "${d >= 0 ? "+" : ""}${d.toStringAsFixed(1)}",
                  textAlign: TextAlign.right,
                  style: AppText.label.copyWith(fontSize: 13, color: color));
            })),
        // Kapus-cellák: védés-mérleg + GSAx (csak kapus-mezszámnál).
        if (isGk) ...[
          SizedBox(
              width: 52,
              child: Text(
                  ((p["gk_on_target"] as num?)?.toInt() ?? 0) > 0
                      ? "${p["gk_saves"] ?? 0}/${p["gk_on_target"]}"
                      : "—",
                  textAlign: TextAlign.right,
                  style: AppText.label.copyWith(
                      fontSize: 13, color: AppColors.textPrimary))),
          SizedBox(
              width: 50,
              child: Builder(builder: (_) {
                final g = (p["gk_prevented"] as num?)?.toDouble();
                final color = g == null || g.abs() < 0.3
                    ? AppColors.textFaint
                    : (g > 0 ? AppColors.accent : AppColors.away);
                return Text(
                    g == null
                        ? "—"
                        : "${g >= 0 ? "+" : ""}${g.toStringAsFixed(1)}",
                    textAlign: TextAlign.right,
                    style: AppText.label.copyWith(
                        fontSize: 13, color: color));
              })),
        ],
        // Emberfogás-cella: őrzés-idő + átlagtáv (ha van mért őrzés).
        if (hasMark)
          SizedBox(
              width: 66,
              child: Builder(builder: (_) {
                final ms = (p["mark_s"] as num?)?.toDouble();
                final md = (p["mark_dist"] as num?)?.toDouble();
                if (ms == null || ms <= 0) {
                  return Text("—",
                      textAlign: TextAlign.right,
                      style: AppText.label.copyWith(
                          fontSize: 13, color: AppColors.textFaint));
                }
                final loose = md != null && md >= 2.5;
                return Text(
                    "${ms.toStringAsFixed(0)}s·"
                    "${md == null ? "?" : md.toStringAsFixed(1)}m",
                    textAlign: TextAlign.right,
                    style: AppText.label.copyWith(
                        fontSize: 13,
                        color: loose
                            ? AppColors.gold
                            : AppColors.textPrimary));
              })),
        SizedBox(
            width: 44,
            child: Text("${p["minutes"] ?? "-"}",
                textAlign: TextAlign.right,
                style: AppText.label.copyWith(fontSize: 13))),
      ]),
    );
  }
}
