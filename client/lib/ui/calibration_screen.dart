/// Kalibráló képernyő — a felhasználó a 4 pálya-sarkot ráhúzza a képkockára,
/// és ÉLŐBEN látja a pálya-modellt (négyszög + középvonal + 6 m + kapuk) ráugrani.
///
/// A 4 sarok = teljes homográfia (kép ↔ valós pálya). Ebből lesz a pontos
/// felülnézet és a pályán kívüliek (kispad/edző) szűrése. A referencia-képkockát
/// a backend adja a feltöltött videóból (/reference-frame); ha nincs backend vagy
/// videó, egy helyőrző mutatja a UX-et. A számítás a homography.dart-tal (a backend
/// tükre). Mentéskor a normalizált sarkokat a valódi képpont-koordinátára váltjuk
/// (a képkocka eredeti W×H-jából), és kiírjuk a backend --calib formátumában.
library;

import "dart:math" as math;
import "dart:typed_data";
import "dart:ui" as ui;

import "package:flutter/material.dart";
import "package:flutter/services.dart";

import "../analytics/homography.dart";
import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "court_geometry.dart";
import "shell/app_shell.dart";

class CalibrationScreen extends StatefulWidget {
  /// A feltöltött videó backend-oldali elérési útja (ebből tölti be a képkockát).
  /// Ha null, helyőrző jelenik meg a valódi kép helyett.
  final String? videoPath;

  /// A backend alap-URL-je (lokális módban localhost:8000).
  final String baseUrl;

  /// Melyik képkockát töltse be referenciának (a bevezető után, tartalmas rész).
  final int frameIndex;

  const CalibrationScreen({
    super.key,
    this.videoPath,
    this.baseUrl = "http://127.0.0.1:8000",
    this.frameIndex = 180,
  });

  @override
  State<CalibrationScreen> createState() => _CalibrationScreenState();
}

class _CalibrationScreenState extends State<CalibrationScreen> {
  // A 4 sarok a kép-területen belül, arányban (0..1), hogy méretfüggetlen legyen.
  // Sorrend: távoli-bal, távoli-jobb, közeli-jobb, közeli-bal.
  List<Offset> _corners = const [
    Offset(0.20, 0.35), Offset(0.75, 0.32), Offset(0.90, 0.72), Offset(0.10, 0.78),
  ];
  int? _drag;
  bool _saved = false;

  // A betöltött referencia-képkocka és eredeti mérete (a képpont-export miatt).
  Uint8List? _frameBytes;
  Size? _frameSize;
  bool _loading = false;
  String? _loadError;

  @override
  void initState() {
    super.initState();
    _loadReferenceFrame();
  }

  /// Betölti a referencia-képkockát a backendtől; hiba esetén helyőrzőre esünk vissza.
  Future<void> _loadReferenceFrame() async {
    if (widget.videoPath == null) return; // nincs videó → marad a helyőrző
    setState(() => _loading = true);
    try {
      final api = ApiClient(baseUrl: widget.baseUrl);
      final bytes = await api.fetchReferenceFrame(widget.videoPath!, t: widget.frameIndex);
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final img = frame.image;
      if (!mounted) return;
      setState(() {
        _frameBytes = bytes;
        _frameSize = Size(img.width.toDouble(), img.height.toDouble());
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadError = "$e";
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.upload,
      crumbTag: "1e",
      crumbPath: "KALIBRÁCIÓ · PÁLYA ILLESZTÉSE",
      collapsed: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("Pálya-kalibráció", style: AppText.title),
          const SizedBox(height: 4),
          Text("Húzd a 4 sarkot a pálya sarkaira — a modell élőben illeszkedik.", style: AppText.subtitle),
          const SizedBox(height: AppSpacing.lg),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(child: _frameCard()),
                const SizedBox(width: AppSpacing.lg),
                SizedBox(width: 280, child: _sidePanel()),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _frameCard() {
    return Container(
      decoration: AppTheme.card(),
      clipBehavior: Clip.antiAlias,
      child: LayoutBuilder(
        builder: (context, c) {
          final size = Size(c.maxWidth, c.maxHeight);
          final pts = [for (final f in _corners) Offset(f.dx * size.width, f.dy * size.height)];
          return GestureDetector(
            onPanStart: (d) {
              double best = 32;
              _drag = null;
              for (int i = 0; i < pts.length; i++) {
                final dist = (pts[i] - d.localPosition).distance;
                if (dist < best) { best = dist; _drag = i; }
              }
            },
            onPanUpdate: (d) {
              if (_drag == null) return;
              setState(() {
                _corners = [..._corners];
                _corners[_drag!] = Offset(
                  (d.localPosition.dx / size.width).clamp(0.0, 1.0),
                  (d.localPosition.dy / size.height).clamp(0.0, 1.0),
                );
                _saved = false;
              });
            },
            onPanEnd: (_) => _drag = null,
            // A valódi képkocka a sarkok ALATT (BoxFit.fill: a 0..1 arány közvetlenül
            // az eredeti képkocka arányára képződik le → tiszta képpont-export).
            child: Stack(
              fit: StackFit.expand,
              children: [
                if (_frameBytes != null)
                  Image.memory(_frameBytes!, fit: BoxFit.fill, gaplessPlayback: true)
                else
                  _placeholder(),
                CustomPaint(painter: _CalibPainter(pts, drawBackground: _frameBytes == null), size: size),
              ],
            ),
          );
        },
      ),
    );
  }

  /// Helyőrző, ha nincs valódi képkocka (nincs videó vagy backend).
  Widget _placeholder() {
    return Container(
      color: const Color(0xFF0C1119),
      alignment: Alignment.topLeft,
      padding: const EdgeInsets.all(16),
      child: Text(
        _loading
            ? "referencia képkocka betöltése…"
            : _loadError != null
                ? "nincs képkocka (backend/videó nélkül) — helyőrző"
                : "referencia képkocka (helyőrző)",
        style: AppText.label.copyWith(color: AppColors.textFaint),
      ),
    );
  }

  Widget _sidePanel() {
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text("SARKOK", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          _cornerRow("Távoli-bal", 0),
          _cornerRow("Távoli-jobb", 1),
          _cornerRow("Közeli-jobb", 2),
          _cornerRow("Közeli-bal", 3),
          const Spacer(),
          Text(
            _frameSize != null
                ? "Kép: ${_frameSize!.width.toInt()}×${_frameSize!.height.toInt()} px. "
                    "Mentéskor a sarkokat a valódi képpontokra váltjuk és a "
                    "vágólapra másoljuk (--calib formátum)."
                : "Éles használatban ide a feltöltött videó egy képkockája kerül; a 4 "
                    "sarokból a rendszer kiszámolja a homográfiát, és a pályán kívüli "
                    "személyeket (kispad, edző) automatikusan kiszűri.",
            style: AppText.label.copyWith(fontSize: 11),
          ),
          const SizedBox(height: AppSpacing.md),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: AppColors.accent, foregroundColor: AppColors.onAccent),
            onPressed: _save,
            icon: const Icon(Icons.check),
            label: Text(_saved ? "Kalibráció mentve" : "Kalibráció mentése"),
          ),
        ],
      ),
    );
  }

  /// A normalizált sarkokat képpont-koordinátára váltja (ha ismert a képméret),
  /// és a backend --calib formátumában a vágólapra másolja.
  Future<void> _save() async {
    final w = _frameSize?.width ?? 1920.0;
    final h = _frameSize?.height ?? 1080.0;
    final pixelCorners = [
      for (final cn in _corners) [(cn.dx * w).round(), (cn.dy * h).round()],
    ];
    // Egyszerű JSON kézzel (a --calib fájl [[x,y],...] alakot vár).
    final json = "[${pixelCorners.map((p) => "[${p[0]},${p[1]}]").join(",")}]";
    await Clipboard.setData(ClipboardData(text: json));
    if (!mounted) return;
    setState(() => _saved = true);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text("calib másolva a vágólapra: $json")),
    );
  }

  Widget _cornerRow(String name, int i) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Row(children: [
            Container(width: 10, height: 10, decoration: const BoxDecoration(color: AppColors.accent, shape: BoxShape.circle)),
            const SizedBox(width: 8),
            Text(name, style: AppText.label.copyWith(color: AppColors.textPrimary)),
          ]),
          Text("${(_corners[i].dx * 100).round()}, ${(_corners[i].dy * 100).round()}",
              style: AppText.label.copyWith(fontSize: 11)),
        ]),
      );
}

/// Kirajzolja a húzható sarkokat + a pálya-modellt (a képkocka fölé).
class _CalibPainter extends CustomPainter {
  final List<Offset> corners; // 4 kép-pont (pixel)
  final bool drawBackground; // helyőrző háttér (ha nincs valódi képkocka)
  _CalibPainter(this.corners, {this.drawBackground = true});

  @override
  void paint(Canvas canvas, Size size) {
    if (drawBackground) {
      canvas.drawRect(Offset.zero & size, Paint()..color = const Color(0xFF0C1119));
    }

    // Homográfia: pálya-sarkok (méter) -> a húzott kép-pontok.
    final courtCorners = [
      [0.0, 0.0], [courtLength, 0.0], [courtLength, courtWidth], [0.0, courtWidth],
    ];
    final dst = [for (final c in corners) [c.dx, c.dy]];
    final h = homographyFromPoints(courtCorners, dst);
    Offset p(double mx, double my) {
      final r = applyHomography(h, mx, my);
      return Offset(r[0], r[1]);
    }

    final line = Paint()..color = AppColors.accent..style = PaintingStyle.stroke..strokeWidth = 2.5;
    final gold = Paint()..color = AppColors.gold..style = PaintingStyle.stroke..strokeWidth = 2;
    final goalP = Paint()..color = AppColors.away..style = PaintingStyle.stroke..strokeWidth = 4;

    final path = Path()..moveTo(corners[0].dx, corners[0].dy);
    for (int i = 1; i < 4; i++) { path.lineTo(corners[i].dx, corners[i].dy); }
    path.close();
    canvas.drawPath(path, line);
    canvas.drawLine(p(courtLength / 2, 0), p(courtLength / 2, courtWidth), line);

    const cy = courtWidth / 2;
    canvas.drawLine(p(0, cy - 1.5), p(0, cy + 1.5), goalP);
    canvas.drawLine(p(courtLength, cy - 1.5), p(courtLength, cy + 1.5), goalP);

    for (final gx in [0.0, courtLength]) {
      final s = gx == courtLength ? -1.0 : 1.0;
      Offset? prev;
      for (int i = 0; i <= 20; i++) {
        final th = math.pi * i / 20;
        final cur = p(gx + s * 6 * math.sin(th), cy - 6 * math.cos(th));
        if (prev != null) canvas.drawLine(prev, cur, gold);
        prev = cur;
      }
    }

    for (final c in corners) {
      canvas.drawCircle(c, 11, Paint()..color = AppColors.accent.withOpacity(0.25));
      canvas.drawCircle(c, 7, Paint()..color = AppColors.accent);
      canvas.drawCircle(c, 7, Paint()..color = Colors.white..style = PaintingStyle.stroke..strokeWidth = 1.5);
    }
  }

  @override
  bool shouldRepaint(covariant _CalibPainter old) =>
      old.corners != corners || old.drawBackground != drawBackground;
}
