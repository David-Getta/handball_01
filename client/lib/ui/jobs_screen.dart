/// Feldolgozások — a futó és a lezárt elemzések egy helyen.
///
/// Egy meccs feldolgozása percekig fut. Eddig a haladást csak a
/// kezdőlap mutatta, és csak amíg a felhasználó ott állt: aki közben
/// átment a felderítésre vagy a figura-tervezőbe, elvesztette szem elől
/// — nem volt hová visszamennie. Ez a képernyő az a hely.
///
/// Amit ad:
///   - a FUTÓ munkák élő haladása (szakasz, százalék, eltelt idő),
///   - megszakítás,
///   - a kész meccs megnyitása egy kattintással (a feldolgozás után a
///     leggyakoribb következő lépés),
///   - és a LEZÁRT feldolgozások naplója: mi futott le, mikor, mi lett
///     a vége — a hibaüzenettel együtt, újraindítás után is.
library;

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../services/jobs_monitor.dart";
import "../theme/app_theme.dart";
import "anim.dart";
import "empty_state.dart";
import "error_text.dart";
import "match_screen.dart";
import "shell/app_shell.dart";

class JobsScreen extends StatefulWidget {
  const JobsScreen({super.key});

  @override
  State<JobsScreen> createState() => _JobsScreenState();
}

class _JobsScreenState extends State<JobsScreen> {
  final ApiClient _api = ApiClient();
  List<Map<String, dynamic>> _history = const [];

  @override
  void initState() {
    super.initState();
    JobsMonitor.instance.start();
    JobsMonitor.instance.refreshNow();
    _loadHistory();
  }

  Future<void> _loadHistory() async {
    final h = await _api.fetchJobHistory(limit: 25);
    if (mounted) setState(() => _history = h);
  }

  Future<void> _cancel(String jobId) async {
    try {
      await _api.cancelJob(jobId);
      await JobsMonitor.instance.refreshNow();
      await _loadHistory();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(humanError(e))));
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.jobs,
      crumbTag: "1h",
      crumbPath: "FELDOLGOZÁSOK · FUTÓ ÉS LEZÁRT ELEMZÉSEK",
      child: ValueListenableBuilder<List<Map<String, dynamic>>>(
        valueListenable: JobsMonitor.instance.jobs,
        builder: (context, jobs, _) {
          final aktiv = jobs.where(JobsMonitor.isActive).toList();
          return ListView(
            children: [
              Text("FUTÓ FELDOLGOZÁSOK", style: AppText.sectionLabel),
              const SizedBox(height: AppSpacing.sm),
              if (aktiv.isEmpty)
                const EmptyState(
                  "Most nem fut feldolgozás",
                  why: "Amikor elindítasz egy elemzést, itt látod a "
                      "haladását — akkor is, ha közben az app másik "
                      "részét nézed. A menüpont melletti szám mutatja, "
                      "hány munka fut.",
                  icon: Icons.hourglass_empty,
                )
              else
                for (final (i, j) in aktiv.indexed)
                  FadeSlideIn(index: i, child: _runningCard(j)),
              const SizedBox(height: AppSpacing.xl),
              Row(children: [
                Text("LEZÁRT FELDOLGOZÁSOK", style: AppText.sectionLabel),
                const SizedBox(width: AppSpacing.sm),
                Text("${_history.length}",
                    style: AppText.label.copyWith(fontSize: 11)),
                const Spacer(),
                IconButton(
                  tooltip: "Frissítés",
                  onPressed: _loadHistory,
                  icon: const Icon(Icons.refresh,
                      size: 18, color: AppColors.textSecondary),
                ),
              ]),
              const SizedBox(height: AppSpacing.sm),
              if (_history.isEmpty)
                Text("Még nincs lezárt feldolgozás.", style: AppText.label)
              else
                for (final (i, h) in _history.indexed)
                  FadeSlideIn(index: i, child: _historyRow(h)),
              const SizedBox(height: AppSpacing.xl),
            ],
          );
        },
      ),
    );
  }

  /// Egy FUTÓ munka kártyája: mi tart hol, mennyi ideje, és mit lehet
  /// vele kezdeni.
  Widget _runningCard(Map<String, dynamic> j) {
    final futo = j["status"] == "running";
    final p = ((j["progress"] as num?)?.toDouble() ?? 0).clamp(0.0, 1.0);
    final stage = (j["stage"] as String?) ?? "";
    final message = (j["message"] as String?) ?? "";
    final matchId = j["match_id"] as String?;
    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [AppColors.accent.withOpacity(0.10), AppColors.surface],
          stops: const [0.0, 0.6],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.accent.withOpacity(0.35)),
      ),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(futo ? Icons.autorenew : Icons.schedule,
                size: 16, color: AppColors.accent),
            const SizedBox(width: 8),
            Expanded(
              child: Text(matchId ?? "(még nincs meccs-azonosító)",
                  style: AppText.value.copyWith(fontSize: 14),
                  overflow: TextOverflow.ellipsis),
            ),
            CountUp(
                value: p * 100,
                format: (v) => "${v.toStringAsFixed(0)}%",
                style: AppText.value
                    .copyWith(fontSize: 15, color: AppColors.accent)),
          ]),
          // Hátralévő idő: percekig futó munkánál ez dönti el, hogy a
          // felhasználó megvárja-e, vagy elmegy a gép mellől.
          if (etaLabel(j) != null) ...[
            const SizedBox(height: 4),
            Row(children: [
              const Icon(Icons.schedule, size: 13, color: AppColors.gold),
              const SizedBox(width: 6),
              Text(etaLabel(j)!,
                  style: AppText.label
                      .copyWith(fontSize: 12, color: AppColors.gold)),
            ]),
          ],
          const SizedBox(height: AppSpacing.sm),
          AnimatedBar(value: p, minHeight: 7),
          const SizedBox(height: AppSpacing.sm),
          Text(
              futo
                  ? (message.isNotEmpty
                      ? message
                      : (stage.isNotEmpty ? stage : "feldolgozás…"))
                  : "sorban áll — előtte másik feldolgozás fut",
              style: AppText.label,
              overflow: TextOverflow.ellipsis),
          // Alvás-gátlás: a felhasználónak tudnia kell, hogy nyugodtan
          // elmehet a gép mellől — és azt is, hol a határ (lehajtott
          // tető külső kijelző nélkül a macOS-t akkor is elaltatja).
          if (futo && j["keep_awake"] == true) ...[
            const SizedBox(height: 6),
            Row(children: [
              const Icon(Icons.coffee, size: 13, color: AppColors.gold),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                    "A gép ébren marad a feldolgozás végéig — elmehetsz "
                    "mellőle. (MacBookon a LEHAJTOTT tető külső kijelző "
                    "nélkül így is alvást jelent.)",
                    style: AppText.label.copyWith(
                        fontSize: 11, color: AppColors.textFaint)),
              ),
            ]),
          ],
          const SizedBox(height: AppSpacing.md),
          Row(children: [
            // A részleges eredmény menet közben is megnyitható: a
            // feldolgozó három percenként menti, amit addig kiszámolt.
            if (matchId != null)
              OutlinedButton.icon(
                onPressed: () => Navigator.of(context).pushReplacement(
                    MaterialPageRoute(
                        builder: (_) => MatchScreen(matchId: matchId))),
                style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.accent,
                    side: const BorderSide(color: AppColors.accent)),
                icon: const Icon(Icons.play_circle_outline, size: 18),
                label: const Text("Ami eddig kész"),
              ),
            const Spacer(),
            TextButton.icon(
              onPressed: () => _cancel(j["job_id"] as String),
              style:
                  TextButton.styleFrom(foregroundColor: AppColors.textFaint),
              icon: const Icon(Icons.close, size: 16),
              label: const Text("Megszakítás"),
            ),
          ]),
        ],
      ),
    );
  }

  /// Egy LEZÁRT feldolgozás sora — a vége és (hiba esetén) a miértje.
  Widget _historyRow(Map<String, dynamic> h) {
    final status = (h["status"] as String?) ?? "";
    final hiba = status == "error" || status == "failed";
    final megszakitva = status == "cancelled";
    final matchId = h["match_id"] as String?;
    final err = (h["error"] as String?) ?? "";
    final szin = hiba
        ? AppColors.away
        : megszakitva
            ? AppColors.textFaint
            : AppColors.accent;
    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(children: [
        Icon(
            hiba
                ? Icons.error_outline
                : megszakitva
                    ? Icons.block
                    : Icons.check_circle_outline,
            size: 16,
            color: szin),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(matchId ?? "(nincs meccs-azonosító)",
                  style: AppText.value.copyWith(fontSize: 13),
                  overflow: TextOverflow.ellipsis),
              if (hiba && err.isNotEmpty)
                Text(err,
                    style: AppText.label
                        .copyWith(fontSize: 11.5, color: AppColors.away),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis),
            ],
          ),
        ),
        if (!hiba && !megszakitva && matchId != null)
          IconButton(
            tooltip: "Megnyitás",
            onPressed: () => Navigator.of(context).pushReplacement(
                MaterialPageRoute(
                    builder: (_) => MatchScreen(matchId: matchId))),
            icon: const Icon(Icons.play_circle_outline,
                size: 18, color: AppColors.accent),
          ),
      ]),
    );
  }
}
