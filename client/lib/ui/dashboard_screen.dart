/// Áttekintés (dashboard) — statisztika-kártyák + legutóbbi meccsek.
///
/// A "Sport Machine" design nyitó képernyője. A meccsekre kattintva megnyílik a
/// meccs-elemző. (Az adatok itt még mintaadatok; a valódi listát a backend adja.)
library;

import "package:flutter/material.dart";

import "../theme/app_theme.dart";
import "match_screen.dart";
import "shell/app_shell.dart";

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.dashboard,
      crumbTag: "1b",
      crumbPath: "DASHBOARD · MECCSEK ÁTTEKINTÉSE",
      child: ListView(
        children: [
          Text("Áttekintés", style: AppText.title),
          const SizedBox(height: 4),
          Text("Veszprém HC · 2025/26 szezon", style: AppText.subtitle),
          const SizedBox(height: AppSpacing.xl),
          Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(child: _statCard("ELEMZETT MECCS", "24", "+3 e héten", accent: true)),
              const SizedBox(width: AppSpacing.lg),
              Expanded(child: _statCard("KÖVETETT JÁTÉKOS", "312", "14 meccs · átlag 21")),
            ],
          ),
          const SizedBox(height: AppSpacing.xl),
          Text("Legutóbbi meccsek", style: AppText.value.copyWith(fontSize: 17)),
          const SizedBox(height: AppSpacing.md),
          _matchCard(context, "Veszprém", "32", "29", "Szeged",
              "2026.06.28 · K&H Liga · 40:12 elemezve", ["6-0 véd", "lerohanás 18%"]),
          const SizedBox(height: AppSpacing.md),
          _matchCard(context, "Tatabánya", "27", "31", "Veszprém",
              "2026.06.21 · K&H Liga · 38:44 elemezve", ["5-1 véd", "lerohanás 24%"]),
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

  Widget _matchCard(BuildContext context, String home, String hs, String as, String away,
      String meta, List<String> tags) {
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: () => Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const MatchScreen()),
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
                    Text(home, style: AppText.value.copyWith(fontSize: 17)),
                    const SizedBox(width: 10),
                    Text(hs, style: AppText.value.copyWith(fontSize: 17, color: AppColors.accent)),
                    Text(" : ", style: AppText.label),
                    Text(as, style: AppText.value.copyWith(fontSize: 17, color: AppColors.away)),
                    const SizedBox(width: 10),
                    Text(away, style: AppText.value.copyWith(fontSize: 17)),
                  ]),
                  const SizedBox(height: 6),
                  Text(meta, style: AppText.label.copyWith(fontSize: 12)),
                  const SizedBox(height: AppSpacing.md),
                  Row(children: [for (final t in tags) Padding(padding: const EdgeInsets.only(right: 8), child: _tag(t))]),
                ],
              ),
            ),
            const Icon(Icons.chevron_right, color: AppColors.textFaint),
          ],
        ),
      ),
    );
  }

  Widget _tag(String t) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: AppColors.surfaceAlt,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: AppColors.border),
        ),
        child: Text(t, style: AppText.label.copyWith(fontSize: 11)),
      );
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
    // néhány játékos-pont
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
