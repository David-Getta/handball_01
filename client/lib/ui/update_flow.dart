/// Frissítés-folyamat EGY helyen: keresés → megerősítés → letöltés →
/// telepítés, saját párbeszédekkel.
///
/// Miért külön fájl: a frissítéshez SE FIÓK, SE MOTOR nem kell (a
/// kiadásokat a GitHub adja), ezért minden olyan képernyőnek el kell
/// érnie, ahol a felhasználó elakadhat. Ez korábban nem így volt, és
/// pont ez zárta be a kört:
///
///   régi verzió → a motor nem indul → a fiók-kapu a MOTOR-HIBA
///   képernyőn áll meg → onnan nem volt út a frissítőhöz → a
///   felhasználó nem tud olyan verzióra jutni, amelyikben a motor-hiba
///   már javítva van.
///
/// A folyamat magát a hívó képernyőt nem ismeri: minden visszajelzést
/// (snackbar, párbeszéd) maga ad.
library;

import "package:flutter/material.dart";

import "../services/update_service.dart";
import "../theme/app_theme.dart";
import "../version.dart";
import "error_text.dart";

/// Frissítés keresése, és — ha a felhasználó kéri — letöltés+telepítés.
///
/// Nem dob: a hibát emberi mondatként mutatja meg. A végén a telepítő
/// indul, az app pedig magától újraindul.
Future<void> checkAndInstallUpdate(BuildContext context) async {
  final messenger = ScaffoldMessenger.of(context);
  UpdateInfo? info;
  try {
    info = await UpdateService().check();
  } catch (e) {
    if (!context.mounted) return;
    messenger.showSnackBar(
        SnackBar(content: Text("Frissítési hiba: ${humanError(e)}")));
    return;
  }
  if (!context.mounted) return;
  if (info == null) {
    messenger.showSnackBar(SnackBar(
        content: Text("A legújabb verziót használod ($appVersion).")));
    return;
  }

  final chosen = info;
  final go = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      backgroundColor: AppColors.surface,
      title: Text("Új verzió: ${chosen.version}"),
      content: const Text(
          "Letöltsem és telepítsem most? A program a végén magától "
          "újraindul.",
          style: AppText.label),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text("Később")),
        FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text("Frissítés most")),
      ],
    ),
  );
  if (go != true || !context.mounted) return;

  final progress = ValueNotifier<double?>(0);
  showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (_) => AlertDialog(
      backgroundColor: AppColors.surface,
      content: ValueListenableBuilder<double?>(
        valueListenable: progress,
        builder: (_, v, __) => Row(children: [
          const SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(
                  strokeWidth: 2.5, color: AppColors.accent)),
          const SizedBox(width: AppSpacing.md),
          Expanded(
              child: Text(
                  v == null
                      ? "Letöltés…"
                      : v < 1
                          ? "Letöltés: ${(v * 100).toStringAsFixed(0)}%"
                          : "Telepítés — az app mindjárt újraindul…",
                  style: AppText.label)),
        ]),
      ),
    ),
  );
  try {
    await UpdateService().downloadAndInstall(chosen, onProgress: (v) {
      progress.value = v;
    });
  } catch (e) {
    if (!context.mounted) return;
    Navigator.of(context, rootNavigator: true).pop();
    messenger.showSnackBar(
        SnackBar(content: Text("Frissítési hiba: ${humanError(e)}")));
  }
}
