/// Indító képernyő — a felhasználónak SEMMIT nem kell tennie: az app elindítja a
/// motort (backend), megvárja, míg kész, majd belép a dashboardra.
///
/// Ez teszi lehetővé a "letöltés → dupla kattintás → működik" élményt: nincs
/// terminál, nincs uvicorn-parancs. Ha nincs beépített motor (pl. csak a demó-
/// kiadás), akkor is tovább lehet lépni demó módban.
library;

import "dart:ui" show AppExitResponse;

import "package:flutter/material.dart";

import "../services/backend_launcher.dart";
import "../theme/app_theme.dart";
import "account_gate.dart";
import "update_flow.dart";

class BootstrapScreen extends StatefulWidget {
  const BootstrapScreen({super.key});

  @override
  State<BootstrapScreen> createState() => _BootstrapScreenState();
}

class _BootstrapScreenState extends State<BootstrapScreen> with WidgetsBindingObserver {
  final BackendLauncher _launcher = BackendLauncher();
  String _message = "Motor indítása…";
  BackendPhase? _phase;

  /// A motor naplójának utolsó sorai — CSAK sikertelen indításnál
  /// töltjük be. Ez az első képernyő, ahol az indulási hiba
  /// megjelenhet; a fiók-kapu és a nyitóképernyő is megmutatja a
  /// naplót, itt viszont eddig csak egy mondat állt, és a felhasználó
  /// nem tudott mit elküldeni.
  String? _log;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _start();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _launcher.stop(); // az app bezárásakor a motort is leállítjuk
    super.dispose();
  }

  @override
  Future<AppExitResponse> didRequestAppExit() async {
    _launcher.stop();
    return AppExitResponse.exit;
  }

  Future<void> _start() async {
    setState(() {
      _message = "Motor indítása…";
      _phase = BackendPhase.starting;
    });
    final status = await _launcher.ensureRunning(
      onLog: (line) {
        if (!mounted || line.isEmpty) return;
        setState(() => _message = line);
      },
    );
    if (!mounted) return;
    setState(() {
      _phase = status.phase;
      _message = status.message;
    });
    if (status.phase == BackendPhase.ready) {
      _enterApp();
      return;
    }
    if (status.phase == BackendPhase.failed) {
      final tail = await BackendLauncher.logTail();
      if (!mounted) return;
      setState(() => _log = tail);
    }
  }

  // A motor után a FIÓK-KAPU jön: belépés (vagy fiók létrehozása a
  // feltételek elfogadásával), és csak utána a dashboard. Motor nélküli
  // (demó) módban a kapu a rövid tulajdonjogi tudomásulvételt kéri.
  void _enterApp() {
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) =>
            AccountGate(engineReady: _phase == BackendPhase.ready),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final failed = _phase == BackendPhase.failed;
    final noEngine = _phase == BackendPhase.noEngine;
    final busy = _phase == null || _phase == BackendPhase.starting;

    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Márka-logó.
                Container(
                  width: 66, height: 66,
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(colors: [AppColors.accent, Color(0xFF1B8F82)]),
                    borderRadius: BorderRadius.circular(18),
                  ),
                  child: const Icon(Icons.change_history_rounded, color: AppColors.onAccent, size: 34),
                ),
                const SizedBox(height: AppSpacing.lg),
                const Text("SPORT MACHINE", style: AppText.brand),
                const SizedBox(height: 4),
                Text("Kézilabda-elemző", style: AppText.subtitle),
                const SizedBox(height: AppSpacing.xl),

                if (busy) ...[
                  const SizedBox(
                    width: 34, height: 34,
                    child: CircularProgressIndicator(strokeWidth: 3, color: AppColors.accent),
                  ),
                  const SizedBox(height: AppSpacing.lg),
                ] else
                  Icon(
                    failed ? Icons.error_outline : Icons.info_outline,
                    color: failed ? AppColors.away : AppColors.gold, size: 34,
                  ),
                const SizedBox(height: AppSpacing.md),
                Text(
                  busy ? "Az elemző motor indítása…" : (failed ? "A motor nem indult el" : "Motor nélküli (demó) mód"),
                  style: AppText.value.copyWith(fontSize: 16),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text(_message, style: AppText.label, textAlign: TextAlign.center),

                if (failed && _log != null && _log!.trim().isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.lg),
                  Text("A MOTOR NAPLÓJA (UTOLSÓ SOROK)",
                      style: AppText.sectionLabel),
                  const SizedBox(height: AppSpacing.sm),
                  Container(
                    width: double.infinity,
                    constraints: const BoxConstraints(maxHeight: 160),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceAlt,
                      border: Border.all(color: AppColors.border),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    padding: const EdgeInsets.all(AppSpacing.md),
                    child: SingleChildScrollView(
                      child: SelectableText(_log!,
                          style: AppText.label.copyWith(
                              fontSize: 11, color: AppColors.textPrimary)),
                    ),
                  ),
                ],

                if (failed || noEngine) ...[
                  const SizedBox(height: AppSpacing.xl),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      if (failed)
                        OutlinedButton.icon(
                          onPressed: _start,
                          style: OutlinedButton.styleFrom(
                            foregroundColor: AppColors.accent, side: const BorderSide(color: AppColors.accent)),
                          icon: const Icon(Icons.refresh, size: 18),
                          label: const Text("Újrapróbálom"),
                        ),
                      if (failed) const SizedBox(width: AppSpacing.md),
                      // A frissítéshez se fiók, se motor nem kell — és
                      // pont az akad itt el, aki olyan régi verziót
                      // futtat, amelyikben a motor még el sem indul.
                      if (failed)
                        OutlinedButton.icon(
                          onPressed: () => checkAndInstallUpdate(context),
                          style: OutlinedButton.styleFrom(
                              foregroundColor: AppColors.accent,
                              side: const BorderSide(color: AppColors.accent)),
                          icon: const Icon(Icons.system_update, size: 18),
                          label: const Text("Frissítés keresése"),
                        ),
                      if (failed) const SizedBox(width: AppSpacing.md),
                      FilledButton.icon(
                        onPressed: _enterApp,
                        style: FilledButton.styleFrom(
                          backgroundColor: AppColors.accent, foregroundColor: AppColors.onAccent),
                        icon: const Icon(Icons.play_arrow, size: 18),
                        label: const Text("Belépés (demó)"),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
