/// Feltöltés — meccsvideó → Tracking, a feldolgozási pipeline állapotával.
///
/// A "Sport Machine" design feltöltő képernyője: dropzone + folyamatban lévő
/// feldolgozás (kör-progress + a valós [A]–[H] pipeline-lépések állapota).
/// A tényleges feltöltés/feldolgozás a backendhez köthető; ez a felület.
library;

import "package:flutter/material.dart";

import "../theme/app_theme.dart";
import "shell/app_shell.dart";

class UploadScreen extends StatelessWidget {
  const UploadScreen({super.key});

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
          const SizedBox(height: AppSpacing.xl),
          Text("Feldolgozás alatt", style: AppText.value.copyWith(fontSize: 17)),
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
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const _RingProgress(value: 0.62),
              const SizedBox(width: AppSpacing.xl),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    const Icon(Icons.movie_outlined, size: 18, color: AppColors.textSecondary),
                    const SizedBox(width: 8),
                    Text("VESZ-SZE_2026-06-30.mp4", style: AppText.value.copyWith(fontSize: 15)),
                  ]),
                  const SizedBox(height: 6),
                  Text("4.2 GB · 40:12 hossz · 1080p · 25 fps", style: AppText.label.copyWith(fontSize: 12)),
                ],
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xl),
          _step("Kalibráció", "A", done: true),
          _step("Detektálás (YOLO)", "B", done: true),
          _step("Követés + ReID", "C", active: true),
          _step("Csapatszín / kapus / bíró", "D"),
          _step("Pálya-koordináta", "E"),
          _step("Képen kívüli becslés", "F"),
          _step("Statisztika + hőtérkép", "H"),
        ],
      ),
    );
  }

  Widget _step(String name, String tag, {bool done = false, bool active = false}) {
    final Color c = done ? AppColors.accent : active ? AppColors.gold : AppColors.textFaint;
    final IconData icon = done ? Icons.check_circle : active ? Icons.autorenew : Icons.circle_outlined;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(icon, size: 18, color: c),
          const SizedBox(width: AppSpacing.md),
          Text(name, style: AppText.value.copyWith(
              color: (done || active) ? AppColors.textPrimary : AppColors.textFaint, fontWeight: FontWeight.w500)),
          const SizedBox(width: 6),
          Text("[$tag]", style: AppText.label.copyWith(fontSize: 11, color: AppColors.textFaint)),
          const Spacer(),
          if (active) Text("folyamatban…", style: AppText.label.copyWith(fontSize: 11, color: AppColors.gold)),
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
