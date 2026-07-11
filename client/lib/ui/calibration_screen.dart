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

/// A kalibráció eredménye — a feltöltő képernyő ezt kapja vissza, és adja
/// tovább a feldolgozásnak (POST /matches/process).
class CalibrationResult {
  /// A 4 sarok képpont-koordinátában: [[x,y],...] (bal-fent, jobb-fent,
  /// jobb-lent, bal-lent sorrendben).
  final List<List<int>> corners;

  /// Melyik területre illesztettük: "full" | "left" | "right".
  final String region;

  /// 180°-os forgatás (a kamera a túloldalról néz).
  final bool rotate;

  const CalibrationResult({
    required this.corners,
    required this.region,
    required this.rotate,
  });
}

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

  // Melyik területet jelöljük be: teljes pálya vagy csak az egyik térfél
  // (pásztázó kameránál az induló képen sokszor csak egy térfél látszik).
  String _region = "full"; // full | left | right
  // 180°-os forgatás: ha a kamera a túloldali lelátóról néz.
  bool _rotate = false;

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
                CustomPaint(
                  painter: _CalibPainter(pts,
                      region: _region,
                      rotate: _rotate,
                      drawBackground: _frameBytes == null),
                  size: size,
                ),
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
          Text("TERÜLET", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          // Ha csak az egyik térfél látszik a képen, a 4 pontot a TÉRFÉL
          // sarkaira kell húzni (a felezővonal két vége is "sarok").
          SegmentedButton<String>(
            showSelectedIcon: false,
            style: const ButtonStyle(visualDensity: VisualDensity.compact),
            segments: const [
              ButtonSegment(value: "full", label: Text("Teljes")),
              ButtonSegment(value: "left", label: Text("Bal fél")),
              ButtonSegment(value: "right", label: Text("Jobb fél")),
            ],
            selected: {_region},
            onSelectionChanged: (s) => setState(() {
              _region = s.first;
              _saved = false;
            }),
          ),
          const SizedBox(height: AppSpacing.sm),
          // Forgatás: ha a pálya "fejjel lefelé" látszik (túloldali kamera).
          Row(children: [
            Expanded(
              child: Text("Forgatás 180°",
                  style: AppText.label.copyWith(color: AppColors.textPrimary)),
            ),
            Switch(
              value: _rotate,
              activeColor: AppColors.accent,
              onChanged: (v) => setState(() {
                _rotate = v;
                _saved = false;
              }),
            ),
          ]),
          const SizedBox(height: AppSpacing.md),
          Text("SARKOK", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          _cornerRow("Távoli-bal", 0),
          _cornerRow("Távoli-jobb", 1),
          _cornerRow("Közeli-jobb", 2),
          _cornerRow("Közeli-bal", 3),
          const Spacer(),
          Text(
            _region == "full"
                ? "Tipp: ha csak az egyik térfél látszik a képen, válaszd a "
                    "Bal/Jobb fél gombot — a pontokat a térfél sarkaira húzd "
                    "(a felezővonal két vége is sarok)."
                : "A 4 pontot a KIVÁLASZTOTT TÉRFÉL sarkaira húzd: 2 valódi "
                    "pályasarok + a felezővonal két vége.",
            style: AppText.label.copyWith(fontSize: 11, color: AppColors.gold),
          ),
          const SizedBox(height: AppSpacing.sm),
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

  /// A normalizált sarkokat képpont-koordinátára váltja, a vágólapra is
  /// másolja (CLI-hez), és VISSZAADJA a hívónak (a feltöltő képernyő ezt
  /// küldi el a feldolgozásnak a területtel/forgatással együtt).
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
    Navigator.of(context).pop(CalibrationResult(
      corners: pixelCorners,
      region: _region,
      rotate: _rotate,
    ));
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
  final String region; // full | left | right — mire illesztjük a 4 pontot
  final bool rotate; // 180°-os forgatás (túloldali kamera)
  final bool drawBackground; // helyőrző háttér (ha nincs valódi képkocka)
  _CalibPainter(this.corners,
      {this.region = "full", this.rotate = false, this.drawBackground = true});

  @override
  void paint(Canvas canvas, Size size) {
    if (drawBackground) {
      canvas.drawRect(Offset.zero & size, Paint()..color = const Color(0xFF0C1119));
    }

    // A kijelölt terület (teljes pálya vagy térfél) sarkai méterben.
    final (x0, x1) = switch (region) {
      "left" => (0.0, courtLength / 2),
      "right" => (courtLength / 2, courtLength),
      _ => (0.0, courtLength),
    };
    var courtCorners = [
      [x0, 0.0], [x1, 0.0], [x1, courtWidth], [x0, courtWidth],
    ];
    if (rotate) {
      // 180°: a képen bejelölt sarkok a terület átellenes sarkainak felelnek meg.
      courtCorners = [courtCorners[2], courtCorners[3], courtCorners[0], courtCorners[1]];
    }
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
    // Felezővonal — csak ha a kijelölt területre esik (térfélnél a széle).
    if (courtLength / 2 >= x0 && courtLength / 2 <= x1) {
      canvas.drawLine(p(courtLength / 2, 0), p(courtLength / 2, courtWidth), line);
    }

    const cy = courtWidth / 2;
    // Kapuk + 6 méteres ívek — csak a látható területen lévő kapukra.
    for (final gx in [0.0, courtLength]) {
      if (gx < x0 - 0.01 || gx > x1 + 0.01) continue; // ez a kapu nem látszik
      canvas.drawLine(p(gx, cy - 1.5), p(gx, cy + 1.5), goalP);
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
      old.corners != corners ||
      old.region != region ||
      old.rotate != rotate ||
      old.drawBackground != drawBackground;
}
