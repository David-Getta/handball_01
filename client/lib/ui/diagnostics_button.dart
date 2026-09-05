/// "Diagnosztika másolása" gomb — egy kattintás, és a felhasználó
/// beilleszthet MINDENT, amiből a motor-hiba megfejthető.
///
/// Miért kell: a "nem indul el a motor" a leggyakoribb élő hiba, és a
/// naplófájl önmagában kevés. Ha a motor-program meg sem található,
/// vagy az adatmappa nem írható, akkor napló SINCS — a felhasználó
/// pedig csak annyit tud mondani, hogy "nem megy". Ez a gomb a hiányzó
/// feltételeket is kimondja (hol kerestük a motort, írható-e az
/// adatmappa, válaszol-e bármelyik port), és a vágólapra teszi.
library;

import "package:flutter/material.dart";
import "package:flutter/services.dart";

import "../services/backend_launcher.dart";
import "../theme/app_theme.dart";
import "../version.dart";

class DiagnosticsButton extends StatefulWidget {
  const DiagnosticsButton({super.key});

  @override
  State<DiagnosticsButton> createState() => _DiagnosticsButtonState();
}

class _DiagnosticsButtonState extends State<DiagnosticsButton> {
  bool _busy = false;

  Future<void> _copy() async {
    setState(() => _busy = true);
    final messenger = ScaffoldMessenger.of(context);
    String report;
    try {
      report = await BackendLauncher.diagnostics(appVersion: appVersion);
    } catch (e) {
      // Ez a jelentés MAGA a technikai kivonat — ide a nyers
      // kivétel-szöveg kell, nem emberi mondat (a felhasználó
      // beilleszti a hibabejelentésbe).
      report = "A diagnosztika összeállítása nem sikerült: $e"; // nyers-hiba-szándékos
    }
    await Clipboard.setData(ClipboardData(text: report));
    if (!mounted) return;
    setState(() => _busy = false);
    messenger.showSnackBar(const SnackBar(
        content: Text("A diagnosztika a vágólapon — illeszd be a "
            "hibabejelentésbe.")));
  }

  @override
  Widget build(BuildContext context) {
    return TextButton.icon(
      onPressed: _busy ? null : _copy,
      style: TextButton.styleFrom(foregroundColor: AppColors.textSecondary),
      icon: Icon(_busy ? Icons.hourglass_top : Icons.copy_all, size: 16),
      label: Text(_busy ? "Összeállítom…" : "Diagnosztika másolása"),
    );
  }
}
