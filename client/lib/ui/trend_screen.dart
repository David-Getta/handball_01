/// Fejlődés-követés — két időszak (korábbi vs. újabb meccsek) összevetése.
///
/// A vízió "csapat/játékos fejlődése" része: mutatónként régi → új érték,
/// javult/romlott jelöléssel, és magyar nyelvű összegzéssel. Működik a saját
/// csapatra ("fejlődünk-e?") és az ellenfélre ("változott-e a játékuk?").
/// Az adatokat a backend /scouting/trend végpontja adja.
library;

import "dart:io";

import "package:file_picker/file_picker.dart";
import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "shell/app_shell.dart";
import "anim.dart";
import "error_text.dart";
import "waiting.dart";

class TrendScreen extends StatefulWidget {
  final List<Map<String, String>> older; // a korábbi időszak meccsei
  final List<Map<String, String>> newer; // az újabb időszak meccsei

  const TrendScreen({super.key, required this.older, required this.newer});

  @override
  State<TrendScreen> createState() => _TrendScreenState();
}

class _TrendScreenState extends State<TrendScreen> {
  final ApiClient _api = ApiClient();
  Map<String, dynamic>? _trend;
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
      final t = await _api.fetchTrend(widget.older, widget.newer);
      if (!mounted) return;
      setState(() {
        _trend = t;
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

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.dashboard,
      crumbTag: "1g",
      crumbPath: "FEJLŐDÉS · KÉT IDŐSZAK ÖSSZEVETÉSE",
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
    final t = _trend;
    return Row(children: [
      IconButton(
        onPressed: () => Navigator.of(context).maybePop(),
        tooltip: "Vissza",
        icon: const Icon(Icons.arrow_back, color: AppColors.textSecondary),
      ),
      const SizedBox(width: 4),
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(t != null ? "${t["team_name"]} — fejlődés" : "Fejlődés", style: AppText.title),
          Text(
            t != null
                ? "Korábbi: ${t["older_matches"]} meccs · Újabb: ${t["newer_matches"]} meccs"
                : "Két időszak összevetése",
            style: AppText.subtitle,
          ),
        ],
      ),
      const Spacer(),
      // Nyomtatható fejlődés-riport mentése (HTML) — kiosztható.
      if (t != null)
        IconButton(
          tooltip: "Fejlődés-riport mentése (HTML)",
          onPressed: _saveReport,
          icon: const Icon(Icons.download, color: AppColors.accent),
        ),
    ]);
  }

  /// A nyomtatható riport letöltése és mentése a választott helyre.
  Future<void> _saveReport() async {
    try {
      final bytes =
          await _api.fetchTrendExport(widget.older, widget.newer);
      if (!mounted) return;
      final path = await FilePicker.platform.saveFile(
        dialogTitle: "Fejlődés-riport mentése (HTML)",
        fileName: "fejlodes_riport.html",
        type: FileType.custom,
        allowedExtensions: const ["html"],
      );
      if (path == null) return; // a felhasználó megszakította
      await File(path).writeAsBytes(bytes);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("Fejlődés-riport mentve: $path — böngészőből "
              "nyomtatható")));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text("Riport-hiba: ${humanError(e)}")));
    }
  }

  Widget _body() {
    if (_loading) {
      return const WaitingView("Időszakok összevetése…",
          hint: "A korábbi és az újabb meccsek külön-külön végigfutnak "
              "az elemzésen, azért tart tovább egy meccsnél.",
          icon: Icons.trending_up);
    }
    if (_error != null) {
      return Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.error_outline, size: 36, color: AppColors.away),
          const SizedBox(height: AppSpacing.md),
          Text("Nem sikerült az összevetés", style: AppText.value.copyWith(fontSize: 16)),
          const SizedBox(height: 6),
          Text(_error!, style: AppText.label, textAlign: TextAlign.center),
          const SizedBox(height: AppSpacing.lg),
          OutlinedButton.icon(onPressed: _load, icon: const Icon(Icons.refresh), label: const Text("Újra")),
        ]),
      );
    }
    final t = _trend!;
    final metrics = (t["metrics"] as List?)?.cast<Map<String, dynamic>>() ?? [];
    final summary = (t["summary"] as List?) ?? [];
    return ListView(
      children: [
        // Összegzés (a lényeg, kiemelve).
        FadeSlideIn(
          child: Container(
            decoration: BoxDecoration(
              // Halk arany fény a bal felső sarokból: az összegzés a lap
              // legfontosabb doboza, ránézésre is annak kell látszania.
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  AppColors.gold.withOpacity(0.10),
                  AppColors.surface,
                ],
                stops: const [0.0, 0.55],
              ),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: AppColors.gold.withOpacity(0.5)),
            ),
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  const Icon(Icons.insights, size: 18, color: AppColors.gold),
                  const SizedBox(width: 8),
                  Text("ÖSSZEGZÉS", style: AppText.sectionLabel.copyWith(color: AppColors.gold)),
                ]),
                const SizedBox(height: AppSpacing.md),
                for (final (i, s) in summary.indexed)
                  FadeSlideIn(
                    index: i + 1,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: Text("$s", style: AppText.value.copyWith(fontSize: 14)),
                    ),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        // Mutatónkénti sorok.
        Container(
          decoration: AppTheme.card(),
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text("MUTATÓK (korábbi → újabb)", style: AppText.sectionLabel),
              const SizedBox(height: AppSpacing.md),
              for (final (i, m) in metrics.indexed)
                FadeSlideIn(index: i + 2, child: _metricRow(m)),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.xl),
      ],
    );
  }

  Widget _metricRow(Map<String, dynamic> m) {
    final better = m["better"] as bool?;
    final color = better == null
        ? AppColors.textFaint
        : better
            ? AppColors.accent
            : AppColors.away;
    final icon = better == null
        ? Icons.remove
        : better
            ? Icons.trending_up
            : Icons.trending_down;
    final unit = (m["unit"] as String?) ?? "";
    final older = (m["older"] as num?)?.toDouble() ?? 0.0;
    final newer = (m["newer"] as num?)?.toDouble() ?? 0.0;
    // A segédfüggvény neve nem lehet "num" (kitakarná a beépített típust).
    String fmt(double d) =>
        d % 1 == 0 ? d.toInt().toString() : d.toStringAsFixed(1);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text("${m["label"]}",
                  style: AppText.value.copyWith(fontSize: 13.5)),
              const SizedBox(height: 5),
              // Változás-sáv: a hossz a nagyságrend, a színes farok maga a
              // változás — a szám elolvasása ELŐTT látszik, mennyit mozdult.
              _DeltaBar(older: older, newer: newer, color: color),
            ],
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Row(children: [
            Text("${fmt(older)}$unit",
                style: AppText.label.copyWith(fontSize: 12.5)),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6),
              child: Icon(Icons.arrow_forward,
                  size: 12, color: AppColors.textFaint),
            ),
            // A friss érték felpörög: a szem oda néz, ahol mozgás van.
            CountUp(
              value: newer,
              format: (v) => "${fmt(v)}$unit",
              style: AppText.value
                  .copyWith(fontSize: 14.5, color: color, fontWeight: FontWeight.w700),
            ),
          ]),
          const SizedBox(height: 3),
          _changeChip(older, newer, color),
        ]),
      ]),
    );
  }

  /// Relatív változás jelvénye ("+23%"). Nulláról indulva nincs értelmes
  /// százalék — ilyenkor az abszolút különbséget mondjuk ki.
  Widget _changeChip(double older, double newer, Color color) {
    final diff = newer - older;
    final String text;
    if (diff == 0) {
      text = "változatlan";
    } else if (older == 0) {
      text = "${diff > 0 ? "+" : ""}${diff % 1 == 0 ? diff.toInt() : diff.toStringAsFixed(1)}";
    } else {
      final pct = diff / older.abs() * 100;
      text = "${pct > 0 ? "+" : ""}${pct.toStringAsFixed(0)}%";
    }
    final dim = diff == 0;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
      decoration: BoxDecoration(
        color: (dim ? AppColors.textFaint : color).withOpacity(0.14),
        borderRadius: BorderRadius.circular(7),
      ),
      child: Text(text,
          style: AppText.label.copyWith(
              fontSize: 10.5,
              fontWeight: FontWeight.w700,
              color: dim ? AppColors.textFaint : color)),
    );
  }
}

/// Változás-sáv: a közös alap halvány, a KÜLÖNBSÉG színes.
///
/// A sáv teljes hossza a nagyobbik érték (a mutatók egymáshoz képest is
/// összemérhetők maradnak a soron belül), a halvány rész a kisebbik érték,
/// a színes farok a változás. Így egy pillantással látszik, hogy a mutató
/// sokat vagy alig mozdult — a puszta "12,3 → 15,1" ezt nem mutatja meg.
class _DeltaBar extends StatelessWidget {
  final double older;
  final double newer;
  final Color color;

  const _DeltaBar({required this.older, required this.newer, required this.color});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 6,
      child: TweenAnimationBuilder<double>(
        tween: Tween(begin: 0, end: 1),
        duration: reduceMotion(context)
            ? Duration.zero
            : const Duration(milliseconds: 750),
        curve: Curves.easeOutCubic,
        builder: (context, t, _) => CustomPaint(
          painter: _DeltaBarPainter(
              older: older, newer: newer, color: color, progress: t),
          size: Size.infinite,
        ),
      ),
    );
  }
}

class _DeltaBarPainter extends CustomPainter {
  final double older;
  final double newer;
  final Color color;
  final double progress;

  _DeltaBarPainter(
      {required this.older,
      required this.newer,
      required this.color,
      required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    final lo = older.abs() < newer.abs() ? older.abs() : newer.abs();
    final hi = older.abs() > newer.abs() ? older.abs() : newer.abs();
    if (hi <= 0) return;
    const r = Radius.circular(3);

    // Pálya (a teljes szélesség) — a sáv akkor is látszik, ha kicsi az érték.
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTWH(0, 0, size.width, size.height), r),
        Paint()..color = AppColors.surfaceAlt);

    final hiW = size.width * progress;
    final loW = hiW * (lo / hi);

    // A színes farok: a közös alaptól a nagyobbik értékig.
    canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTWH(0, 0, hiW, size.height), r),
        Paint()
          ..shader = LinearGradient(colors: [
            color.withOpacity(0.55),
            color,
          ]).createShader(Rect.fromLTWH(0, 0, hiW, size.height)));

    // A közös alap halványan — a különbség így "kilóg" belőle.
    canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTWH(0, 0, loW, size.height), r),
        Paint()..color = AppColors.textFaint.withOpacity(0.45));
  }

  @override
  bool shouldRepaint(covariant _DeltaBarPainter old) =>
      old.older != older ||
      old.newer != newer ||
      old.color != color ||
      old.progress != progress;
}
