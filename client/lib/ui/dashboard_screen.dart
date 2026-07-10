/// Áttekintés (dashboard) — statisztika-kártyák + a tárolt meccsek könyvtára.
///
/// A "Sport Machine" design nyitó képernyője. A meccslistát a backend adja
/// (GET /matches); a kártyákra kattintva megnyílik a meccs-elemző a valódi
/// match_id-vel. Backend nélkül/üres tárnál barátságos állapotot mutat.
library;

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "match_screen.dart";
import "scouting_screen.dart";
import "shell/app_shell.dart";

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

  @override
  void initState() {
    super.initState();
    _load();
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
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _offline = true;
        _matches = [];
        _loading = false;
      });
    }
  }

  /// Egyesített felderítés: az edző kiválasztja az ellenfél 2-3 meccsét, és
  /// meccsenként megjelöli, melyik oldalon játszott az ellenfél → egy zajmentes,
  /// több meccsen alapuló jelentés készül.
  Future<void> _combinedScouting() async {
    // Kiválasztás-állapot: match_id -> null (nincs kiválasztva) | "home" | "away".
    final choice = <String, String?>{for (final m in _matches) m["match_id"] as String: null};
    final items = await showDialog<List<Map<String, String>>>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDlg) {
          final selected = choice.values.where((v) => v != null).length;
          return AlertDialog(
            backgroundColor: AppColors.surface,
            title: const Text("Egyesített felderítés"),
            content: SizedBox(
              width: 480,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    "Jelöld ki a meccseket, és meccsenként azt az oldalt, amelyiken a "
                    "FELDERÍTETT csapat játszott.",
                    style: AppText.label.copyWith(fontSize: 12),
                  ),
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
                child: Text("Felderítés ($selected meccs)"),
              ),
            ],
          );
        },
      ),
    );
    if (items == null || items.isEmpty || !mounted) return;
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => ScoutingScreen(items: items)),
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
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text("Áttekintés", style: AppText.title),
                      const SizedBox(height: 4),
                      Text("Sport Machine · elemzett meccsek könyvtára", style: AppText.subtitle),
                    ],
                  ),
                ),
                IconButton(
                  onPressed: _load,
                  icon: const Icon(Icons.refresh, color: AppColors.textSecondary),
                  tooltip: "Frissítés",
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
            const SizedBox(height: AppSpacing.xl),
            Row(children: [
              Text("Meccs-könyvtár", style: AppText.value.copyWith(fontSize: 17)),
              const Spacer(),
              // Több meccsből egyesített ellenfél-jelentés (zajmentesebb profil).
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
