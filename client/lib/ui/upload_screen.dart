/// Feltöltés — meccsvideó → Tracking, a feldolgozási pipeline állapotával.
///
/// A "Sport Machine" design feltöltő képernyője: dropzone + folyamatban lévő
/// feldolgozás (kör-progress + a valós [A]–[H] pipeline-lépések állapota).
/// A tényleges feltöltés/feldolgozás a backendhez köthető; ez a felület.
library;

import "dart:async";

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "calibration_screen.dart";
import "shell/app_shell.dart";

/// A pipeline-lépések sorrendje (a backend ezeket a kódokat adja a job stage-ében).
const List<List<String>> _pipelineSteps = [
  ["A", "Kalibráció"],
  ["B", "Detektálás (YOLO)"],
  ["C", "Követés + ReID"],
  ["D", "Csapatszín / kapus / bíró"],
  ["E", "Pálya-koordináta"],
  ["F", "Képen kívüli becslés"],
  ["H", "Statisztika + hőtérkép"],
];

class UploadScreen extends StatefulWidget {
  const UploadScreen({super.key});

  @override
  State<UploadScreen> createState() => _UploadScreenState();
}

class _UploadScreenState extends State<UploadScreen> {
  // A backend-oldali videó elérési útja (lokális mód). A kalibráló képernyő ebből
  // tölti be a valódi referencia-képkockát a /reference-frame végponton keresztül.
  final _pathCtrl = TextEditingController();
  final _api = ApiClient();

  // Aktuális feldolgozási munka állapota (a backendtől, GET /jobs/{id}).
  String? _jobId;
  String _status = "idle"; // idle | running | done | error
  String _stage = "A";
  double _progress = 0.0;
  String _message = "";
  String? _error;
  Timer? _poll;

  @override
  void dispose() {
    _poll?.cancel();
    _pathCtrl.dispose();
    super.dispose();
  }

  /// Elindítja a feldolgozást a megadott videó-úton, majd időzítővel lekérdezi
  /// a haladást (GET /jobs/{id}) és frissíti a kártyát.
  Future<void> _startProcessing() async {
    final path = _pathCtrl.text.trim();
    if (path.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Adj meg egy backend-oldali videó-utat.")),
      );
      return;
    }
    setState(() {
      _status = "running";
      _stage = "A";
      _progress = 0.0;
      _message = "indítás";
      _error = null;
    });
    try {
      final r = await _api.startProcessing(path, weights: "yolov8n.pt");
      _jobId = r["job_id"] as String;
      _poll?.cancel();
      _poll = Timer.periodic(const Duration(milliseconds: 800), (_) => _pollJob());
    } catch (e) {
      setState(() {
        _status = "error";
        _error = "$e";
        _message = "nem sikerült elindítani";
      });
    }
  }

  /// Egy lekérdezés a job állapotára; leállítja az időzítőt, ha vége.
  Future<void> _pollJob() async {
    final id = _jobId;
    if (id == null) return;
    try {
      final j = await _api.fetchJob(id);
      if (!mounted) return;
      setState(() {
        _status = (j["status"] as String?) ?? "running";
        _stage = (j["stage"] as String?) ?? _stage;
        _progress = (j["progress"] as num?)?.toDouble() ?? _progress;
        _message = (j["message"] as String?) ?? "";
        _error = j["error"] as String?;
      });
      if (_status == "done" || _status == "error") {
        _poll?.cancel();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _status = "error";
        _error = "$e";
      });
      _poll?.cancel();
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.upload,
      crumbTag: "1f",
      crumbPath: "FELTÖLTÉS · FELDOLGOZÁSI PIPELINE",
      collapsed: true,
      child: ListView(
        children: [
          Text("Videó feltöltése", style: AppText.title),
          const SizedBox(height: 4),
          Text("Pásztázó-kamerás meccsvideó → Tracking adatmodell", style: AppText.subtitle),
          const SizedBox(height: AppSpacing.xl),
          _dropzone(),
          const SizedBox(height: AppSpacing.md),
          // Lokális mód: a backend-oldali videó útja, hogy a kalibráció a valódi
          // képkockát töltse be (fájlválasztó nélkül is működjön a desktop-teszt).
          TextField(
            controller: _pathCtrl,
            style: AppText.value.copyWith(fontSize: 13),
            decoration: InputDecoration(
              isDense: true,
              hintText: "Backend-oldali videó útja (pl. /home/.../match.mp4)",
              hintStyle: AppText.label.copyWith(fontSize: 12),
              prefixIcon: const Icon(Icons.folder_open, size: 18, color: AppColors.textSecondary),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: const BorderSide(color: AppColors.borderStrong),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: const BorderSide(color: AppColors.accent),
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          Align(
            alignment: Alignment.centerLeft,
            child: OutlinedButton.icon(
              onPressed: () {
                final path = _pathCtrl.text.trim();
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => CalibrationScreen(
                      videoPath: path.isEmpty ? null : path,
                    ),
                  ),
                );
              },
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.accent,
                side: const BorderSide(color: AppColors.accent),
              ),
              icon: const Icon(Icons.grid_on, size: 18),
              label: const Text("Pálya-kalibráció (4 sarok)"),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          Align(
            alignment: Alignment.centerLeft,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.accent, foregroundColor: AppColors.onAccent),
              onPressed: _status == "running" ? null : _startProcessing,
              icon: const Icon(Icons.play_arrow, size: 18),
              label: Text(_status == "running" ? "Feldolgozás folyamatban…" : "Feldolgozás indítása"),
            ),
          ),
          const SizedBox(height: AppSpacing.xl),
          Text("Feldolgozás állapota", style: AppText.value.copyWith(fontSize: 17)),
          const SizedBox(height: AppSpacing.md),
          _processingCard(),
        ],
      ),
    );
  }

  Widget _dropzone() {
    return DottedBorderBox(
      child: Row(
        children: [
          Container(
            width: 56, height: 56,
            decoration: BoxDecoration(color: AppColors.surfaceAlt, borderRadius: BorderRadius.circular(14)),
            child: const Icon(Icons.file_upload_outlined, color: AppColors.accent, size: 26),
          ),
          const SizedBox(width: AppSpacing.lg),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text("Húzd ide a meccsvideót, vagy tallózz", style: AppText.value.copyWith(fontSize: 16)),
              const SizedBox(height: 4),
              Text("MP4 / MOV · max 8 GB · 720p–4K · legfeljebb 75 perc", style: AppText.label.copyWith(fontSize: 12)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _processingCard() {
    // A jelenlegi stage indexe a lépéslistában (a done/active/pending eldöntéséhez).
    final curIdx = _pipelineSteps.indexWhere((s) => s[0] == _stage);
    final path = _pathCtrl.text.trim();
    final fileName = path.isEmpty ? "nincs kiválasztott videó" : path.split("/").last;

    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _RingProgress(value: _progress),
              const SizedBox(width: AppSpacing.xl),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      const Icon(Icons.movie_outlined, size: 18, color: AppColors.textSecondary),
                      const SizedBox(width: 8),
                      Expanded(child: Text(fileName, style: AppText.value.copyWith(fontSize: 15), overflow: TextOverflow.ellipsis)),
                    ]),
                    const SizedBox(height: 6),
                    Text(_statusLine(), style: AppText.label.copyWith(
                        fontSize: 12,
                        color: _status == "error" ? AppColors.away : AppColors.textSecondary)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xl),
          for (int i = 0; i < _pipelineSteps.length; i++)
            _step(
              _pipelineSteps[i][1], _pipelineSteps[i][0],
              // "done" ha korábbi lépés, vagy a job kész; "active" ha az aktuális
              // és fut; hibánál az aktuális lépés hibás.
              done: _status == "done" || (curIdx >= 0 && i < curIdx),
              active: _status == "running" && i == curIdx,
              error: _status == "error" && i == curIdx,
            ),
        ],
      ),
    );
  }

  /// A kártya alcíme: állapottól függő, olvasható szöveg.
  String _statusLine() {
    switch (_status) {
      case "idle":
        return "Nincs feldolgozás — add meg a videó-utat és indítsd el.";
      case "running":
        return "Feldolgozás… ${(_progress * 100).round()}% · $_message";
      case "done":
        return "Kész · $_message";
      case "error":
        return "Hiba · ${_error ?? _message}";
      default:
        return _message;
    }
  }

  Widget _step(String name, String tag, {bool done = false, bool active = false, bool error = false}) {
    final Color c = error
        ? AppColors.away
        : done
            ? AppColors.accent
            : active
                ? AppColors.gold
                : AppColors.textFaint;
    final IconData icon = error
        ? Icons.error_outline
        : done
            ? Icons.check_circle
            : active
                ? Icons.autorenew
                : Icons.circle_outlined;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(icon, size: 18, color: c),
          const SizedBox(width: AppSpacing.md),
          Text(name, style: AppText.value.copyWith(
              color: (done || active || error) ? AppColors.textPrimary : AppColors.textFaint,
              fontWeight: FontWeight.w500)),
          const SizedBox(width: 6),
          Text("[$tag]", style: AppText.label.copyWith(fontSize: 11, color: AppColors.textFaint)),
          const Spacer(),
          if (active) Text("folyamatban…", style: AppText.label.copyWith(fontSize: 11, color: AppColors.gold)),
          if (error) Text("hiba", style: AppText.label.copyWith(fontSize: 11, color: AppColors.away)),
        ],
      ),
    );
  }
}

/// Szaggatott keretű doboz (a dropzone-hoz).
class DottedBorderBox extends StatelessWidget {
  final Widget child;
  const DottedBorderBox({super.key, required this.child});
  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _DashedRectPainter(),
      child: Padding(padding: const EdgeInsets.all(AppSpacing.xl), child: child),
    );
  }
}

class _DashedRectPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppColors.borderStrong
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;
    final rrect = RRect.fromRectAndRadius(Offset.zero & size, const Radius.circular(14));
    final path = Path()..addRRect(rrect);
    // Szaggatás: a path mentén rövid szakaszokat rajzolunk.
    for (final metric in path.computeMetrics()) {
      double dist = 0;
      while (dist < metric.length) {
        final seg = metric.extractPath(dist, dist + 7);
        canvas.drawPath(seg, paint);
        dist += 13;
      }
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

/// Kör alakú folyamatjelző százalékkal.
class _RingProgress extends StatelessWidget {
  final double value;
  const _RingProgress({required this.value});
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 78, height: 78,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox(
            width: 78, height: 78,
            child: CircularProgressIndicator(
              value: value,
              strokeWidth: 6,
              backgroundColor: AppColors.surfaceAlt,
              valueColor: const AlwaysStoppedAnimation(AppColors.accent),
            ),
          ),
          Text("${(value * 100).round()}%", style: AppText.value.copyWith(fontSize: 16)),
        ],
      ),
    );
  }
}
