/// Fiók-kapu — a program elé tett belépés és feltétel-elfogadás.
///
/// A Sport Machine a Tulajdonos szellemi és fizikai tulajdona (lásd
/// backend/handball/accounts.py), ezért a használat FIÓKHOZ kötött, a fiók
/// létrehozásához pedig a felhasználási feltételek elfogadása kell. Ez a
/// képernyő dönti el, mi következik:
///
///   1. van érvényes munkamenet + a feltételek aktuális verziója elfogadva
///      → egyből a dashboard,
///   2. van munkamenet, de a feltételek MEGÚJULTAK → elfogadó képernyő,
///      3. nincs munkamenet → belépés / fiók létrehozása,
///   4. nem fut a motor (demó mód) → offline tudomásulvétel, utána demó.
///
/// A kapu a motor indítása UTÁN jön (bootstrap_screen.dart), mert a fiókok
/// és a feltételek szövege a motortól jönnek.
library;

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../services/session_store.dart";
import "../theme/app_theme.dart";
import "../version.dart";
import "account_screen.dart";
import "dashboard_screen.dart";
import "terms_screen.dart";

/// A motor nélküli (demó) mód rövid tudomásulvétele. A TELJES szöveget a
/// motor adja (/legal/terms) — demó módban az sem érhető el, ezért itt a
/// lényeg szerepel, és a felhasználó a motor elindítása után látja a
/// teljes szöveget a fiók létrehozásakor.
const String kOfflineTermsSummary = """
Sport Machine — a használat feltételei (rövid, motor nélküli mód)

A Sport Machine szoftver — a forráskód, az elemző eljárások és modellek, a
felhasználói felület, a nevek és a megjelenés — a Tulajdonos kizárólagos
szellemi tulajdona; a program példányai és a hozzá adott eszközök a
Tulajdonos fizikai tulajdonát képezik. A program használatával Ön nem szerez
tulajdont, csak korlátozott, bármikor visszavonható használati engedélyt.

Tilos a program másolása, terjesztése, továbbadása, értékesítése,
visszafejtése, valamint származékos mű készítése belőle.

A teljes szöveget a program a motor elindítása után, a fiók létrehozásakor
mutatja meg — a demó mód csak kipróbálásra szolgál.
""";

/// A demó módban tudomásul vett szöveg verziója (a teljes feltételektől
/// külön számozva: a demó elfogadás nem váltja ki a fiókos elfogadást).
const int kOfflineTermsVersion = 1;

class AccountGate extends StatefulWidget {
  const AccountGate({super.key, this.engineReady = true});

  /// Fut-e a motor. Ha nem (demó mód), a kapu az offline tudomásulvételt kéri.
  final bool engineReady;

  @override
  State<AccountGate> createState() => _AccountGateState();
}

enum _GateStep { checking, engineDown, offline, account, terms, done }

class _AccountGateState extends State<AccountGate> {
  final ApiClient _api = ApiClient();
  _GateStep _step = _GateStep.checking;
  String? _error;
  bool _offlineAccepted = false;

  @override
  void initState() {
    super.initState();
    _decide();
  }

  Future<void> _decide() async {
    setState(() {
      _step = _GateStep.checking;
      _error = null;
    });
    await SessionStore.load();
    if (!widget.engineReady) {
      // Demó mód: a motor nem fut, fiók nem hozható létre — de a
      // tulajdonjogi tudomásulvétel ilyenkor is kell.
      if (!mounted) return;
      setState(() {
        _step = SessionStore.offlineTermsVersion >= kOfflineTermsVersion
            ? _GateStep.done
            : _GateStep.offline;
      });
      if (_step == _GateStep.done) _enterApp();
      return;
    }
    // A motor ÉL-E MOST? A fiók-lekérdezés hálózati hibára is null-t ad,
    // tehát önmagában nem különbözteti meg a "nincs bejelentkezve" és a
    // "nem fut a motor" esetet — a felhasználó pedig különben egy űrlapot
    // kapna, ami csak beküldéskor bukik el (a motor menet közben is
    // leállhat, pl. frissítés után).
    if (!await _api.isHealthy()) {
      // Lehet, hogy csak ELMOZDULT (tartalék port), de az is, hogy a
      // folyamata halt el — a revive megkeresi, és ha kell, ÚJRA IS
      // INDÍTJA a motort, mielőtt hibát mondanánk.
      if (!await ApiClient.reviveEngine()) {
        if (!mounted) return;
        setState(() => _step = _GateStep.engineDown);
        return;
      }
    }
    final me = await _api.fetchMe();
    if (!mounted) return;
    if (me == null) {
      setState(() => _step = _GateStep.account);
      return;
    }
    if (me["terms_ok"] != true) {
      setState(() => _step = _GateStep.terms);
      return;
    }
    setState(() => _step = _GateStep.done);
    _enterApp();
  }

  void _enterApp() {
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const DashboardScreen()),
    );
  }

  Future<void> _acceptOffline() async {
    await SessionStore.setOfflineTerms(kOfflineTermsVersion);
    _enterApp();
  }

  @override
  Widget build(BuildContext context) {
    switch (_step) {
      case _GateStep.checking:
      case _GateStep.done:
        return const Scaffold(
          body: Center(
            child: SizedBox(
              width: 34,
              height: 34,
              child: CircularProgressIndicator(
                  strokeWidth: 3, color: AppColors.accent),
            ),
          ),
        );
      case _GateStep.account:
        return AccountScreen(onSignedIn: _decide);
      case _GateStep.terms:
        // Belépve, de a feltételek megújultak: elfogadás nélkül nincs tovább.
        return TermsScreen(
          onAccepted: _decide,
          onCancelled: () async {
            await _api.logoutAccount();
            _decide();
          },
        );
      case _GateStep.offline:
        return _offlineNotice();
      case _GateStep.engineDown:
        return _engineDownNotice();
    }
  }

  /// A motor nem válaszol: beszélő képernyő ÚJRAPRÓBÁLÁSSAL — nem egy
  /// űrlap, ami csak a beküldésnél bukik el. A napló helyét is kiírjuk,
  /// mert a motor indulási hibája ott olvasható.
  Widget _engineDownNotice() {
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.error_outline,
                    color: AppColors.away, size: 34),
                const SizedBox(height: AppSpacing.md),
                const Text("A motor nem válaszol", style: AppText.title),
                const SizedBox(height: AppSpacing.sm),
                const Text(
                  "A fiókod a saját gépeden, a motorban él — amíg a motor "
                  "nem fut, belépni és fiókot létrehozni sem lehet.\n\n"
                  "Az Újrapróbálom gomb megkeresi, és ha kell, ÚJRA IS "
                  "INDÍTJA a motort (ez eltarthat fél percig). Ha ez sem "
                  "segít, zárd be teljesen a programot (Cmd+Q, illetve "
                  "Alt+F4), és indítsd újra. Ha marad a hiba, a motor "
                  "naplója megmondja, min akadt el — ezt küldd el a "
                  "fejlesztőnek:\n"
                  "macOS: ~/Library/Application Support/SportMachine/"
                  "engine-app.log\n"
                  "Windows: %LOCALAPPDATA%\\SportMachine\\engine-app.log\n\n"
                  "A futó kiadás: v$appVersion",
                  style: AppText.label,
                ),
                const SizedBox(height: AppSpacing.xl),
                Row(
                  children: [
                    FilledButton.icon(
                      onPressed: _decide,
                      style: FilledButton.styleFrom(
                          backgroundColor: AppColors.accent,
                          foregroundColor: AppColors.onAccent),
                      icon: const Icon(Icons.refresh, size: 18),
                      label: const Text("Újrapróbálom"),
                    ),
                    const SizedBox(width: AppSpacing.md),
                    OutlinedButton.icon(
                      // Ha a tulajdonjogi tudomásulvétel már megvolt, nem
                      // kérdezzük újra — egyenesen a demó módba lép.
                      onPressed: () => SessionStore.offlineTermsVersion >=
                              kOfflineTermsVersion
                          ? _enterApp()
                          : setState(() => _step = _GateStep.offline),
                      style: OutlinedButton.styleFrom(
                          foregroundColor: AppColors.textSecondary,
                          side: const BorderSide(color: AppColors.border)),
                      icon: const Icon(Icons.play_arrow, size: 18),
                      label: const Text("Tovább demó módban"),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// Motor nélküli mód: rövid tudomásulvétel, utána demó.
  Widget _offlineNotice() {
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 640),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text("TUDOMÁSULVÉTEL", style: AppText.sectionLabel),
                const SizedBox(height: AppSpacing.sm),
                const Text("A program a Tulajdonos tulajdona",
                    style: AppText.title),
                const SizedBox(height: AppSpacing.lg),
                Flexible(
                  child: Container(
                    decoration: BoxDecoration(
                      color: AppColors.surface,
                      border: Border.all(color: AppColors.border),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    padding: const EdgeInsets.all(AppSpacing.lg),
                    child: const SingleChildScrollView(
                      child: SelectableText(kOfflineTermsSummary,
                          style: TextStyle(
                              fontSize: 13,
                              height: 1.5,
                              color: AppColors.textSecondary)),
                    ),
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
                CheckboxListTile(
                  value: _offlineAccepted,
                  onChanged: (v) =>
                      setState(() => _offlineAccepted = v ?? false),
                  controlAffinity: ListTileControlAffinity.leading,
                  contentPadding: EdgeInsets.zero,
                  activeColor: AppColors.accent,
                  checkColor: AppColors.onAccent,
                  title: const Text(
                      "Elolvastam, és tudomásul veszem, hogy a program a "
                      "Tulajdonos szellemi és fizikai tulajdona.",
                      style: AppText.label),
                ),
                if (_error != null) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Text(_error!,
                      style: AppText.label.copyWith(color: AppColors.away)),
                ],
                const SizedBox(height: AppSpacing.md),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    FilledButton.icon(
                      onPressed: _offlineAccepted ? _acceptOffline : null,
                      style: FilledButton.styleFrom(
                          backgroundColor: AppColors.accent,
                          foregroundColor: AppColors.onAccent),
                      icon: const Icon(Icons.play_arrow, size: 18),
                      label: const Text("Belépés demó módban"),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
