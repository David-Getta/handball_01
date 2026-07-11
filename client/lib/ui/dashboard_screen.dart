/// Áttekintés (dashboard) — statisztika-kártyák + a tárolt meccsek könyvtára.
///
/// A "Sport Machine" design nyitó képernyője. A meccslistát a backend adja
/// (GET /matches); a kártyákra kattintva megnyílik a meccs-elemző a valódi
/// match_id-vel. Backend nélkül/üres tárnál barátságos állapotot mutat.
library;

import "dart:async";

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../services/update_service.dart";
import "../theme/app_theme.dart";
import "../version.dart";
import "match_screen.dart";
import "scouting_screen.dart";
import "shell/app_shell.dart";
import "trend_screen.dart";

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final ApiClient _api = ApiClient();

  bool _loading = true;
  bool _offline = false; // a backend nem elérhető
  List<Map<String, dynamic>> _matches = [];

  // Feldolgozási sor: a futó/sorban álló munkák a kezdőlapon is látszanak,
  // és amíg van aktív munka, pár másodpercenként frissülnek.
  List<Map<String, dynamic>> _jobs = [];
  Timer? _jobsTimer;

  bool _isActiveJob(Map<String, dynamic> j) =>
      j["status"] == "running" || j["status"] == "queued";

  Future<void> _refreshJobs() async {
    final jobs = await _api.fetchJobs();
    if (!mounted) return;
    final hadActive = _jobs.any(_isActiveJob);
    final hasActive = jobs.any(_isActiveJob);
    setState(() => _jobs = jobs);
    if (hasActive) {
      _jobsTimer ??= Timer.periodic(
          const Duration(seconds: 2), (_) => _refreshJobs());
    } else {
      _jobsTimer?.cancel();
      _jobsTimer = null;
      // Ha épp most fejeződött be egy munka, a könyvtár is frissül.
      if (hadActive) _load();
    }
  }

  // Automatikus frissítés: az elérhető új verzió (ha van) és az elrejtés.
  UpdateInfo? _update;
  bool _updateDismissed = false;

  @override
  void initState() {
    super.initState();
    _load();
    _checkUpdatesSilently();
  }

  @override
  void dispose() {
    _jobsTimer?.cancel();
    super.dispose();
  }

  /// Háttérben megnézi, van-e új kiadás — hibánál csendben marad (induláskor
  /// nem zavarjuk a felhasználót hálózati hibaüzenettel).
  Future<void> _checkUpdatesSilently() async {
    try {
      final u = await UpdateService().check();
      if (mounted && u != null) setState(() => _update = u);
    } catch (_) {
      // pl. nincs net, vagy privát a repó — a kézi ellenőrzés jelez érdemben
    }
  }

  /// Kézi "Frissítés keresése" — snackbarban jelzi az eredményt/hibát is.
  Future<void> _checkUpdatesManually() async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final u = await UpdateService().check();
      if (!mounted) return;
      if (u == null) {
        messenger.showSnackBar(const SnackBar(
            content: Text("A legújabb verziót használod ($appVersion).")));
      } else {
        setState(() {
          _update = u;
          _updateDismissed = false;
        });
      }
    } catch (e) {
      if (!mounted) return;
      final s = "$e";
      // 404: nincs kiadás VAGY privát a repó; 401/403: rossz/lejárt token.
      final authIssue = s.contains("404") || s.contains("401") || s.contains("403");
      messenger.showSnackBar(SnackBar(
        content: Text(authIssue
            ? "Nem érem el a kiadásokat — privát repónál add meg a "
                "GitHub-kulcsot (token)."
            : "Frissítés-ellenőrzési hiba: $e"),
        action: authIssue
            ? SnackBarAction(label: "Kulcs megadása", onPressed: _updateTokenDialog)
            : null,
        duration: const Duration(seconds: 8),
      ));
    }
  }

  /// GitHub hozzáférési kulcs (token) megadása privát repóhoz — egyszer kell.
  /// Fine-grained token, csak ehhez a repóhoz, csak "Contents: Read-only".
  Future<void> _updateTokenDialog() async {
    final current = await UpdateService.loadToken();
    if (!mounted) return;
    final ctrl = TextEditingController(text: current ?? "");
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text("Frissítési kulcs (GitHub token)"),
        content: SizedBox(
          width: 480,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                "Privát repónál az automatikus frissítéshez egy GitHub "
                "hozzáférési kulcs kell. Létrehozás: github.com → Settings → "
                "Developer settings → Fine-grained tokens → csak ehhez a "
                "repóhoz, csak Contents: Read-only joggal. A kulcs csak ezen "
                "a gépen tárolódik. Üresen hagyva törlődik.",
                style: AppText.label.copyWith(fontSize: 12),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: ctrl,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: "github_pat_…",
                  prefixIcon: Icon(Icons.key, size: 18, color: AppColors.gold),
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text("Mégse")),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: AppColors.gold, foregroundColor: AppColors.onAccent),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text("Mentés"),
          ),
        ],
      ),
    );
    if (ok != true) return;
    await UpdateService.saveToken(ctrl.text);
    if (!mounted) return;
    if (ctrl.text.trim().isEmpty) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text("A kulcs törölve.")));
    } else {
      // Mentés után rögtön ellenőrzünk — így azonnal kiderül, jó-e a kulcs.
      await _checkUpdatesManually();
    }
  }

  /// Letöltés + telepítés folyamat-ablakkal. Siker esetén az app újraindul.
  Future<void> _installUpdate(UpdateInfo info) async {
    final progress = ValueNotifier<double?>(0);
    // Nem zárható folyamat-ablak — a csere közben nem szabad kattintgatni.
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: Text("Frissítés ${info.version} verzióra…"),
        content: ValueListenableBuilder<double?>(
          valueListenable: progress,
          builder: (_, v, __) => Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              LinearProgressIndicator(value: v, color: AppColors.gold),
              const SizedBox(height: AppSpacing.md),
              Text(
                v == null
                    ? "Letöltés…"
                    : v < 1
                        ? "Letöltés: ${(v * 100).toStringAsFixed(0)}%"
                        : "Telepítés — az app mindjárt újraindul…",
                style: AppText.label,
              ),
            ],
          ),
        ),
      ),
    );
    try {
      await UpdateService().downloadAndInstall(info, onProgress: (v) {
        progress.value = v;
      });
      // Ide normál esetben nem jutunk el: a telepítő kilépteti az appot.
    } catch (e) {
      if (!mounted) return;
      Navigator.of(context, rootNavigator: true).pop(); // folyamat-ablak be
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text("Frissítési hiba: $e")));
    }
  }

  /// Arany figyelmeztető sáv a lista tetején: új verzió érhető el.
  Widget _updateBanner(UpdateInfo info) {
    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.lg),
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.gold.withOpacity(0.10),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.gold),
      ),
      child: Row(children: [
        const Icon(Icons.system_update_alt, color: AppColors.gold),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text("Új verzió érhető el: ${info.version}",
                  style: AppText.value.copyWith(color: AppColors.gold)),
              const SizedBox(height: 2),
              Text("Egy kattintás — az app letölti, telepíti és újraindul.",
                  style: AppText.label.copyWith(fontSize: 12)),
            ],
          ),
        ),
        TextButton(
          onPressed: () => setState(() => _updateDismissed = true),
          child: const Text("Később"),
        ),
        const SizedBox(width: AppSpacing.sm),
        FilledButton.icon(
          style: FilledButton.styleFrom(
              backgroundColor: AppColors.gold,
              foregroundColor: AppColors.onAccent),
          onPressed: () => _installUpdate(info),
          icon: const Icon(Icons.download, size: 18),
          label: const Text("Frissítés most"),
        ),
      ]),
    );
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final matches = await _api.listMatches();
      if (!mounted) return;
      setState(() {
        _matches = matches;
        _offline = false;
        _loading = false;
      });
      _refreshJobs();
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _offline = true;
        _matches = [];
        _loading = false;
      });
    }
  }

  /// Közös meccs-kiválasztó: pipa + meccsenként a FIGYELT csapat oldala.
  /// Visszaadja az items listát ({"match_id","team"}) vagy null-t (mégse).
  Future<List<Map<String, String>>?> _pickMatches(
      String title, String hint, String confirmLabel) async {
    final choice = <String, String?>{for (final m in _matches) m["match_id"] as String: null};
    return showDialog<List<Map<String, String>>>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDlg) {
          final selected = choice.values.where((v) => v != null).length;
          return AlertDialog(
            backgroundColor: AppColors.surface,
            title: Text(title),
            content: SizedBox(
              width: 480,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(hint, style: AppText.label.copyWith(fontSize: 12)),
                  const SizedBox(height: AppSpacing.md),
                  Flexible(
                    child: SingleChildScrollView(
                      child: Column(children: [
                        for (final m in _matches)
                          _pickRow(m, choice, setDlg),
                      ]),
                    ),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Mégse")),
              FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: AppColors.gold, foregroundColor: AppColors.onAccent),
                onPressed: selected == 0
                    ? null
                    : () => Navigator.pop(ctx, [
                          for (final e in choice.entries)
                            if (e.value != null)
                              {"match_id": e.key, "team": e.value!},
                        ]),
                child: Text("$confirmLabel ($selected meccs)"),
              ),
            ],
          );
        },
      ),
    );
  }

  /// Egyesített felderítés: az edző kiválasztja az ellenfél 2-3 meccsét, és
  /// meccsenként megjelöli, melyik oldalon játszott az ellenfél → egy zajmentes,
  /// több meccsen alapuló jelentés készül.
  Future<void> _combinedScouting() async {
    final items = await _pickMatches(
      "Egyesített felderítés",
      "Jelöld ki a meccseket, és meccsenként azt az oldalt, amelyiken a "
          "FELDERÍTETT csapat játszott.",
      "Felderítés",
    );
    if (items == null || items.isEmpty || !mounted) return;
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => ScoutingScreen(items: items)),
    );
  }

  /// Fejlődés-követés: két időszak (korábbi/újabb meccsek) összevetése —
  /// működik a saját csapatra ("fejlődünk-e?") és az ellenfélre ("változtak-e?").
  Future<void> _trendFlow() async {
    final older = await _pickMatches(
      "Fejlődés — 1/2: KORÁBBI időszak",
      "Jelöld ki a KORÁBBI meccseket, és meccsenként a FIGYELT csapat oldalát.",
      "Tovább",
    );
    if (older == null || older.isEmpty || !mounted) return;
    final newer = await _pickMatches(
      "Fejlődés — 2/2: ÚJABB időszak",
      "Most jelöld ki az ÚJABB meccseket ugyanarról a csapatról.",
      "Összevetés",
    );
    if (newer == null || newer.isEmpty || !mounted) return;
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => TrendScreen(older: older, newer: newer)),
    );
  }

  /// Egy meccs sora a kiválasztóban: pipa + a felderített oldal kiválasztása.
  Widget _pickRow(Map<String, dynamic> m, Map<String, String?> choice,
      void Function(void Function()) setDlg) {
    final id = m["match_id"] as String;
    final home = (m["home_team"] as String?) ?? "Hazai";
    final away = (m["away_team"] as String?) ?? "Vendég";
    final val = choice[id];
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(children: [
        Checkbox(
          value: val != null,
          activeColor: AppColors.gold,
          // Pipáláskor alapból a vendég oldalt derítjük fel (tipikus eset).
          onChanged: (v) => setDlg(() => choice[id] = (v ?? false) ? "away" : null),
        ),
        Expanded(child: Text("$home vs $away", style: AppText.value.copyWith(fontSize: 13),
            overflow: TextOverflow.ellipsis)),
        if (val != null)
          SegmentedButton<String>(
            showSelectedIcon: false,
            style: const ButtonStyle(visualDensity: VisualDensity.compact),
            segments: [
              ButtonSegment(value: "home", label: Text(home, overflow: TextOverflow.ellipsis)),
              ButtonSegment(value: "away", label: Text(away, overflow: TextOverflow.ellipsis)),
            ],
            selected: {val},
            onSelectionChanged: (s) => setDlg(() => choice[id] = s.first),
          ),
      ]),
    );
  }

  /// Csapatnevek átírása — a könyvtár és a felderítő jelentés is az újat mutatja.
  Future<void> _rename(Map<String, dynamic> m) async {
    final homeCtrl = TextEditingController(text: (m["home_team"] as String?) ?? "");
    final awayCtrl = TextEditingController(text: (m["away_team"] as String?) ?? "");
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text("Csapatnevek"),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: homeCtrl,
              decoration: const InputDecoration(
                labelText: "Hazai csapat",
                prefixIcon: Icon(Icons.groups, size: 18, color: AppColors.home),
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            TextField(
              controller: awayCtrl,
              decoration: const InputDecoration(
                labelText: "Vendég csapat",
                prefixIcon: Icon(Icons.groups, size: 18, color: AppColors.away),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text("Mégse")),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.accent, foregroundColor: AppColors.onAccent),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text("Mentés"),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await _api.updateMatchNames(m["match_id"] as String,
          homeTeam: homeCtrl.text.trim(), awayTeam: awayCtrl.text.trim());
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Átnevezési hiba: $e")));
    }
  }

  Future<void> _delete(String matchId) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text("Meccs törlése"),
        content: Text("Biztosan törlöd ezt: $matchId?", style: AppText.label),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text("Mégse")),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text("Törlés", style: TextStyle(color: AppColors.away)),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await _api.deleteMatch(matchId);
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Törlési hiba: $e")));
    }
  }

  double get _totalDurationS =>
      _matches.fold(0.0, (s, m) => s + ((m["duration_s"] as num?)?.toDouble() ?? 0.0));

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.dashboard,
      crumbTag: "1b",
      crumbPath: "DASHBOARD · MECCSEK ÁTTEKINTÉSE",
      child: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          children: [
            // Új verzió sáv — csak ha találtunk frissítést és nem rejtették el.
            if (_update != null && !_updateDismissed) _updateBanner(_update!),
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text("Áttekintés", style: AppText.title),
                      const SizedBox(height: 4),
                      // A verziószám látszik — így ellenőrizhető, hogy az
                      // automatikus frissítés tényleg az újat futtatja.
                      Text("Sport Machine · elemzett meccsek könyvtára · v$appVersion",
                          style: AppText.subtitle),
                    ],
                  ),
                ),
                PopupMenuButton<String>(
                  icon: const Icon(Icons.system_update_alt,
                      color: AppColors.textSecondary),
                  tooltip: "Programfrissítés",
                  color: AppColors.surface,
                  onSelected: (v) {
                    if (v == "check") _checkUpdatesManually();
                    if (v == "token") _updateTokenDialog();
                  },
                  itemBuilder: (_) => const [
                    PopupMenuItem(
                      value: "check",
                      child: ListTile(
                        leading: Icon(Icons.system_update_alt, size: 18),
                        title: Text("Frissítés keresése"),
                        dense: true,
                      ),
                    ),
                    PopupMenuItem(
                      value: "token",
                      child: ListTile(
                        leading: Icon(Icons.key, size: 18),
                        title: Text("Frissítési kulcs (privát repóhoz)"),
                        dense: true,
                      ),
                    ),
                  ],
                ),
                IconButton(
                  onPressed: _load,
                  icon: const Icon(Icons.refresh, color: AppColors.textSecondary),
                  tooltip: "Lista frissítése",
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.xl),
            Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(child: _statCard("ELEMZETT MECCS", "${_matches.length}",
                    _offline ? "backend offline" : "a tárolt könyvtárból", accent: true)),
                const SizedBox(width: AppSpacing.lg),
                Expanded(child: _statCard("ÖSSZ. JÁTÉKIDŐ",
                    "${(_totalDurationS / 60).toStringAsFixed(1)} perc",
                    "${_matches.length} meccs feldolgozva")),
              ],
            ),
            // Folyamatban lévő feldolgozások (sor): élő állapot + megszakítás.
            if (_jobs.any(_isActiveJob)) ...[
              const SizedBox(height: AppSpacing.xl),
              _jobsCard(),
            ],
            const SizedBox(height: AppSpacing.xl),
            Row(children: [
              Text("Meccs-könyvtár", style: AppText.value.copyWith(fontSize: 17)),
              const Spacer(),
              // Több meccsből egyesített ellenfél-jelentés (zajmentesebb profil).
              OutlinedButton.icon(
                onPressed: _matches.length < 2 ? null : _trendFlow,
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.accent,
                  side: BorderSide(
                      color: _matches.length < 2 ? AppColors.border : AppColors.accent),
                ),
                icon: const Icon(Icons.trending_up, size: 18),
                label: const Text("Fejlődés"),
              ),
              const SizedBox(width: AppSpacing.sm),
              OutlinedButton.icon(
                onPressed: _matches.length < 2 ? null : _combinedScouting,
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.gold,
                  side: BorderSide(
                      color: _matches.length < 2
                          ? AppColors.border
                          : AppColors.gold),
                ),
                icon: const Icon(Icons.assignment_outlined, size: 18),
                label: const Text("Egyesített felderítés"),
              ),
            ]),
            const SizedBox(height: AppSpacing.md),
            if (_loading)
              const Padding(
                padding: EdgeInsets.all(AppSpacing.xl),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_offline)
              _notice(Icons.cloud_off, "A backend nem elérhető",
                  "Indítsd el a lokális szervert (uvicorn), majd frissíts. Addig a demó megnyitható.",
                  action: _demoButton())
            else if (_matches.isEmpty)
              _notice(Icons.video_library_outlined, "Még nincs elemzett meccs",
                  "Tölts fel és dolgozz fel egy videót a Feltöltés fülön — itt fog megjelenni.",
                  action: _demoButton())
            else
              for (final m in _matches) ...[
                _matchCard(m),
                const SizedBox(height: AppSpacing.md),
              ],
          ],
        ),
      ),
    );
  }

  /// Demó meccs létrehozása a szerveren — az első kipróbáláshoz: a könyvtárba
  /// kerül egy szimulált meccs, amin minden funkció (elemzés, felderítés,
  /// export) azonnal kipróbálható.
  Future<void> _createDemo() async {
    try {
      final id = await _api.createDemoMatch();
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Demó meccs létrehozva: $id")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Demó-hiba: $e")));
    }
  }

  Widget _demoButton() {
    // Backend elérhető: szerver-oldali demó a könyvtárba (minden funkcióval).
    // Backend nélkül: a kliensbe épített helyi demó megnyitása.
    if (!_offline) {
      return FilledButton.icon(
        onPressed: _createDemo,
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.accent, foregroundColor: AppColors.onAccent),
        icon: const Icon(Icons.auto_awesome, size: 18),
        label: const Text("Demó meccs létrehozása"),
      );
    }
    return OutlinedButton.icon(
      onPressed: () => Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const MatchScreen()),
      ),
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.accent, side: const BorderSide(color: AppColors.accent)),
      icon: const Icon(Icons.play_arrow, size: 18),
      label: const Text("Demó megnyitása"),
    );
  }

  Widget _notice(IconData icon, String title, String body, {Widget? action}) {
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        children: [
          Icon(icon, size: 36, color: AppColors.textFaint),
          const SizedBox(height: AppSpacing.md),
          Text(title, style: AppText.value.copyWith(fontSize: 16)),
          const SizedBox(height: 6),
          Text(body, style: AppText.label, textAlign: TextAlign.center),
          if (action != null) ...[const SizedBox(height: AppSpacing.lg), action],
        ],
      ),
    );
  }

  /// A feldolgozási sor kártyája: futó/sorban álló munkák élő haladással.
  Widget _jobsCard() {
    final active = _jobs.where(_isActiveJob).toList();
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("FOLYAMATBAN LÉVŐ FELDOLGOZÁSOK", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          for (final j in active) _jobRow(j),
        ],
      ),
    );
  }

  Widget _jobRow(Map<String, dynamic> j) {
    final running = j["status"] == "running";
    final progress = (j["progress"] as num?)?.toDouble() ?? 0.0;
    final video = (j["video"] as String?) ?? (j["match_id"] as String? ?? "");
    final message = (j["message"] as String?) ?? "";
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(children: [
        Icon(running ? Icons.autorenew : Icons.schedule,
            size: 16, color: running ? AppColors.gold : AppColors.textFaint),
        const SizedBox(width: 8),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(video,
                style: AppText.value.copyWith(fontSize: 12.5),
                overflow: TextOverflow.ellipsis),
            const SizedBox(height: 3),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: running ? (progress > 0 ? progress : null) : 0,
                minHeight: 4,
                backgroundColor: AppColors.surfaceAlt,
                valueColor: const AlwaysStoppedAnimation(AppColors.gold),
              ),
            ),
            const SizedBox(height: 3),
            Text(running ? message : "sorban áll — előtte másik feldolgozás fut",
                style: AppText.label.copyWith(fontSize: 11),
                overflow: TextOverflow.ellipsis),
          ]),
        ),
        IconButton(
          onPressed: () async {
            try {
              await _api.cancelJob(j["job_id"] as String);
              await _refreshJobs();
            } catch (_) {}
          },
          icon: const Icon(Icons.close, size: 16, color: AppColors.textFaint),
          tooltip: "Megszakítás",
        ),
      ]),
    );
  }

  Widget _statCard(String label, String value, String note, {bool accent = false}) {
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.md),
          Text(value, style: AppText.statBig),
          const SizedBox(height: AppSpacing.sm),
          Text(note, style: AppText.label.copyWith(color: accent ? AppColors.accent : AppColors.textFaint)),
        ],
      ),
    );
  }

  Widget _matchCard(Map<String, dynamic> m) {
    final id = m["match_id"] as String;
    final home = (m["home_team"] as String?) ?? "Hazai";
    final away = (m["away_team"] as String?) ?? "Vendég";
    final frames = (m["num_frames"] as num?)?.toInt() ?? 0;
    final durS = (m["duration_s"] as num?)?.toDouble() ?? 0.0;
    final fps = (m["fps"] as num?)?.toDouble() ?? 25.0;
    final meta = "$id · $frames képkocka · ${durS.toStringAsFixed(1)} s · ${fps.toStringAsFixed(0)} fps";

    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: () => Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => MatchScreen(matchId: id)),
      ),
      child: Container(
        decoration: AppTheme.card(),
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Row(
          children: [
            const _MiniCourt(),
            const SizedBox(width: AppSpacing.lg),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Text(home, style: AppText.value.copyWith(fontSize: 17, color: AppColors.home)),
                    Text("  vs  ", style: AppText.label),
                    Text(away, style: AppText.value.copyWith(fontSize: 17, color: AppColors.away)),
                  ]),
                  const SizedBox(height: 6),
                  Text(meta, style: AppText.label.copyWith(fontSize: 12)),
                ],
              ),
            ),
            IconButton(
              onPressed: () => _rename(m),
              icon: const Icon(Icons.edit_outlined, color: AppColors.textFaint),
              tooltip: "Csapatnevek átírása",
            ),
            IconButton(
              onPressed: () => _delete(id),
              icon: const Icon(Icons.delete_outline, color: AppColors.textFaint),
              tooltip: "Törlés",
            ),
            const Icon(Icons.chevron_right, color: AppColors.textFaint),
          ],
        ),
      ),
    );
  }
}

/// Kis felülnézeti pálya-bélyegkép a meccskártyához.
class _MiniCourt extends StatelessWidget {
  const _MiniCourt();
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 92, height: 60,
      decoration: BoxDecoration(
        color: const Color(0xFF0C1119),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border),
      ),
      child: CustomPaint(painter: _MiniCourtPainter()),
    );
  }
}

class _MiniCourtPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final line = Paint()..color = AppColors.courtLine..style = PaintingStyle.stroke..strokeWidth = 1;
    canvas.drawLine(Offset(size.width / 2, 6), Offset(size.width / 2, size.height - 6), line);
    final home = Paint()..color = AppColors.home;
    final away = Paint()..color = AppColors.away;
    for (final o in [const Offset(0.28, 0.35), const Offset(0.34, 0.7), const Offset(0.2, 0.55)]) {
      canvas.drawCircle(Offset(o.dx * size.width, o.dy * size.height), 3, home);
    }
    for (final o in [const Offset(0.68, 0.4), const Offset(0.72, 0.65), const Offset(0.62, 0.5)]) {
      canvas.drawCircle(Offset(o.dx * size.width, o.dy * size.height), 3, away);
    }
    canvas.drawCircle(Offset(0.46 * size.width, 0.45 * size.height), 2.5, Paint()..color = AppColors.ball);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
