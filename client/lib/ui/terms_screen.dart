/// Felhasználási feltételek — a TELJES szöveg elfogadó gombbal.
///
/// Két helyen kerül elő:
///   - a fiók létrehozásakor (account_screen.dart nyitja meg olvasásra),
///   - ha a feltételek a fiók létrehozása óta ÚJ VERZIÓT kaptak: ilyenkor a
///     fiók-kapu (account_gate.dart) ide irányít, és elfogadás nélkül nincs
///     tovább (a kilépés visszavisz a belépéshez).
///
/// A szöveget mindig a motor adja (GET /legal/terms) — egy forrás, nincs
/// két helyen karbantartott jogi szöveg.
library;

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "error_text.dart";

class TermsScreen extends StatefulWidget {
  const TermsScreen({
    super.key,
    this.onAccepted,
    this.onCancelled,
    this.readOnly = false,
  });

  /// Elfogadás után hívjuk (a kapu ilyenkor újraértékeli az állapotot).
  final VoidCallback? onAccepted;

  /// Elutasítás/kilépés (a kapu ilyenkor kilépteti a fiókot).
  final VoidCallback? onCancelled;

  /// Csak olvasás: nincs elfogadó gomb (a fiók-készítőből megnyitva).
  final bool readOnly;

  @override
  State<TermsScreen> createState() => _TermsScreenState();
}

class _TermsScreenState extends State<TermsScreen> {
  final ApiClient _api = ApiClient();
  Map<String, dynamic>? _terms;
  String? _error;
  bool _checked = false;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final t = await _api.fetchTerms();
      if (!mounted) return;
      setState(() => _terms = t);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = humanError(e));
    }
  }

  Future<void> _accept() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await _api.acceptTerms();
      if (!mounted) return;
      widget.onAccepted?.call();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = humanError(e);
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final terms = _terms;
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 780),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text("FELHASZNÁLÁSI FELTÉTELEK",
                    style: AppText.sectionLabel),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  terms == null
                      ? "Feltételek betöltése…"
                      : (terms["title"] as String? ?? "Feltételek"),
                  style: AppText.title,
                ),
                if (terms != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    "Verzió ${terms["version"]} · hatályos: "
                    "${terms["updated"]} · tulajdonos: ${terms["owner"]}",
                    style: AppText.label,
                  ),
                ],
                const SizedBox(height: AppSpacing.lg),
                Expanded(
                  child: Container(
                    width: double.infinity,
                    decoration: BoxDecoration(
                      color: AppColors.surface,
                      border: Border.all(color: AppColors.border),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    padding: const EdgeInsets.all(AppSpacing.lg),
                    child: terms == null
                        ? Center(
                            child: _error == null
                                ? const SizedBox(
                                    width: 28,
                                    height: 28,
                                    child: CircularProgressIndicator(
                                        strokeWidth: 3,
                                        color: AppColors.accent),
                                  )
                                : Text(_error!,
                                    style: AppText.label
                                        .copyWith(color: AppColors.away)),
                          )
                        : SingleChildScrollView(
                            child: SelectableText(
                              terms["text"] as String? ?? "",
                              style: const TextStyle(
                                  fontSize: 13,
                                  height: 1.55,
                                  color: AppColors.textSecondary),
                            ),
                          ),
                  ),
                ),
                if (!widget.readOnly) ...[
                  const SizedBox(height: AppSpacing.md),
                  CheckboxListTile(
                    value: _checked,
                    onChanged: terms == null
                        ? null
                        : (v) => setState(() => _checked = v ?? false),
                    controlAffinity: ListTileControlAffinity.leading,
                    contentPadding: EdgeInsets.zero,
                    activeColor: AppColors.accent,
                    checkColor: AppColors.onAccent,
                    title: const Text(
                        "Elolvastam és elfogadom a feltételeket, és "
                        "tudomásul veszem, hogy a szoftver a Tulajdonos "
                        "szellemi és fizikai tulajdona.",
                        style: AppText.label),
                  ),
                  if (_error != null && terms != null) ...[
                    const SizedBox(height: AppSpacing.sm),
                    Text(_error!,
                        style: AppText.label.copyWith(color: AppColors.away)),
                  ],
                  const SizedBox(height: AppSpacing.sm),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      TextButton(
                        onPressed: _busy ? null : widget.onCancelled,
                        child: const Text("Nem fogadom el (kilépés)"),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      FilledButton.icon(
                        onPressed:
                            (_checked && !_busy && terms != null) ? _accept : null,
                        style: FilledButton.styleFrom(
                            backgroundColor: AppColors.accent,
                            foregroundColor: AppColors.onAccent),
                        icon: _busy
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: AppColors.onAccent),
                              )
                            : const Icon(Icons.check, size: 18),
                        label: const Text("Elfogadom"),
                      ),
                    ],
                  ),
                ] else ...[
                  const SizedBox(height: AppSpacing.md),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      FilledButton(
                        onPressed: () => Navigator.of(context).pop(),
                        style: FilledButton.styleFrom(
                            backgroundColor: AppColors.accent,
                            foregroundColor: AppColors.onAccent),
                        child: const Text("Bezárom"),
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
