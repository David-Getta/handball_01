/// Belépés és fiók létrehozása.
///
/// A fiókok a saját gépen, a motor adatmappájában élnek (nincs felhő) — a
/// jelszó sose tárolódik nyíltan, csak lenyomatként (lásd
/// backend/handball/accounts.py). A fiók létrehozásához a felhasználási
/// feltételeket EL KELL FOGADNI: a jelölőnégyzet nélkül a "Fiók létrehozása"
/// gomb nem aktív, és a szerver is elutasítja a kérést.
library;

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../services/session_store.dart";
import "../theme/app_theme.dart";
import "../version.dart";
import "error_text.dart";
import "terms_screen.dart";

class AccountScreen extends StatefulWidget {
  const AccountScreen({super.key, required this.onSignedIn, this.onGuest});

  /// Sikeres belépés vagy fiók-létrehozás után hívjuk (a kapu lép tovább).
  final VoidCallback onSignedIn;

  /// Vendég-belépés fiók nélkül (a kapu intézi a tudomásulvételt és a
  /// vendég-munkamenet indítását). Null, ha a vendég-út nem elérhető.
  final VoidCallback? onGuest;

  @override
  State<AccountScreen> createState() => _AccountScreenState();
}

class _AccountScreenState extends State<AccountScreen> {
  final ApiClient _api = ApiClient();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _name = TextEditingController();
  final _team = TextEditingController();

  /// Igaz: fiók létrehozása; hamis: belépés meglévő fiókkal.
  bool _registerMode = false;
  bool _acceptTerms = false;
  bool _busy = false;
  bool _obscure = true;
  String? _error;
  String? _owner;
  int? _termsVersion;

  @override
  void initState() {
    super.initState();
    _loadStatus();
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _name.dispose();
    _team.dispose();
    super.dispose();
  }

  /// Az első indításnál nincs fiók — ilyenkor egyből a létrehozás nyílik.
  Future<void> _loadStatus() async {
    try {
      final st = await _api.fetchAccountsStatus();
      if (!mounted) return;
      setState(() {
        _registerMode = st["has_accounts"] != true;
        _owner = st["owner"] as String?;
        _termsVersion = st["terms_version"] as int?;
      });
    } catch (_) {
      // A motor még nem válaszol — a képernyő ilyenkor is használható,
      // a hiba a beküldéskor derül ki, beszélő üzenettel.
    }
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    Future<void> send() async {
      if (_registerMode) {
        await _api.registerAccount(
          email: _email.text.trim(),
          password: _password.text,
          name: _name.text.trim(),
          team: _team.text.trim(),
          acceptTerms: _acceptTerms,
        );
      } else {
        await _api.loginAccount(_email.text.trim(), _password.text);
      }
    }

    try {
      try {
        await send();
      } catch (e) {
        // Hálózati hiba: a motor menet közben ELMOZDULHATOTT (újraindult,
        // tartalék portra kötött), vagy MEGHALT a folyamata. A revive
        // előbb újra megkeresi, és ha sehol sem válaszol, újra is
        // indítja — utána EGYSZER újrapróbáljuk a beküldést. Ez fedi le
        // azt az esetet, amikor a képernyő betöltése még ment, a
        // beküldés már nem.
        if (!looksLikeConnectionIssue(e)) rethrow;
        if (!await ApiClient.reviveEngine()) rethrow;
        try {
          await send();
        } catch (e2) {
          // Ha az ELSŐ kísérlet valójában célba ért (a fiók létrejött,
          // csak a válasz veszett el), az ismétlés "már van fiók"
          // hibát ad — pedig a fiók él. Ilyenkor a belépés a helyes
          // folytatás, ugyanazokkal az adatokkal.
          if (!_registerMode || !"$e2".contains("már van fiók")) rethrow;
          await _api.loginAccount(_email.text.trim(), _password.text);
        }
      }
      if (!mounted) return;
      widget.onSignedIn();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = humanError(e);
        _busy = false;
      });
    }
  }

  void _openTerms() {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => const TermsScreen(readOnly: true),
    ));
  }

  InputDecoration _dec(String label, {String? hint}) => InputDecoration(
        labelText: label,
        hintText: hint,
        labelStyle: AppText.label,
        filled: true,
        fillColor: AppColors.surfaceAlt,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: AppColors.accent),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final canSubmit = !_busy &&
        _email.text.trim().isNotEmpty &&
        _password.text.isNotEmpty &&
        (!_registerMode || _acceptTerms);

    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.xl),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 56,
                    height: 56,
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(
                          colors: [AppColors.accent, Color(0xFF1B8F82)]),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: const Icon(Icons.change_history_rounded,
                        color: AppColors.onAccent, size: 30),
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  const Text("SPORT MACHINE", style: AppText.brand),
                  const SizedBox(height: 4),
                  Text(
                    _registerMode ? "Fiók létrehozása" : "Belépés",
                    style: AppText.title,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    _registerMode
                        ? "A fiók a saját gépeden készül el — a jelszavad "
                            "nem hagyja el a laptopot."
                        : "Lépj be a gépen létrehozott fiókoddal.",
                    style: AppText.subtitle,
                  ),
                  const SizedBox(height: AppSpacing.xl),

                  TextField(
                    controller: _email,
                    decoration: _dec("E-mail cím", hint: "edzo@egyesulet.hu"),
                    keyboardType: TextInputType.emailAddress,
                    autofillHints: const [AutofillHints.email],
                    onChanged: (_) => setState(() {}),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  TextField(
                    controller: _password,
                    decoration: _dec(
                      _registerMode ? "Jelszó (legalább 8 karakter)" : "Jelszó",
                    ).copyWith(
                      suffixIcon: IconButton(
                        icon: Icon(
                            _obscure
                                ? Icons.visibility_off
                                : Icons.visibility,
                            size: 18,
                            color: AppColors.textFaint),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                    obscureText: _obscure,
                    onChanged: (_) => setState(() {}),
                    onSubmitted: (_) => canSubmit ? _submit() : null,
                  ),

                  if (_registerMode) ...[
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      controller: _name,
                      decoration: _dec("Neved (nem kötelező)"),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      controller: _team,
                      decoration: _dec("Csapat / egyesület (nem kötelező)"),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    CheckboxListTile(
                      value: _acceptTerms,
                      onChanged: (v) =>
                          setState(() => _acceptTerms = v ?? false),
                      controlAffinity: ListTileControlAffinity.leading,
                      contentPadding: EdgeInsets.zero,
                      activeColor: AppColors.accent,
                      checkColor: AppColors.onAccent,
                      title: Text(
                        "Elfogadom a felhasználási feltételeket, és "
                        "tudomásul veszem, hogy a Sport Machine szoftver "
                        "${_owner ?? "a Tulajdonos"} szellemi és fizikai "
                        "tulajdona.",
                        style: AppText.label,
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.only(left: 40),
                      child: TextButton.icon(
                        onPressed: _openTerms,
                        style: TextButton.styleFrom(
                            foregroundColor: AppColors.accent,
                            padding: EdgeInsets.zero,
                            minimumSize: const Size(0, 32),
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap),
                        icon: const Icon(Icons.description_outlined, size: 16),
                        label: Text(
                          _termsVersion == null
                              ? "A feltételek elolvasása"
                              : "A feltételek elolvasása (v$_termsVersion)",
                        ),
                      ),
                    ),
                  ],

                  if (_error != null) ...[
                    const SizedBox(height: AppSpacing.md),
                    Container(
                      width: double.infinity,
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        border: Border.all(color: AppColors.away),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      padding: const EdgeInsets.all(AppSpacing.md),
                      child: Text(_error!,
                          style:
                              AppText.label.copyWith(color: AppColors.away)),
                    ),
                    // Elfelejtett jelszó: nincs e-mailes visszaállítás (a
                    // fiókok csak ezen a gépen élnek) — az őszinte út az
                    // új fiók, és ezt itt mondjuk el, nem egy súgóban.
                    if (!_registerMode) ...[
                      const SizedBox(height: AppSpacing.sm),
                      Text(
                        "Elfelejtetted a jelszavad? A fiókok csak ezen a "
                        "gépen élnek, ezért nincs e-mailes visszaállítás — "
                        "hozz létre új fiókot: a meccseid és elemzéseid "
                        "megmaradnak (azok a géphez tartoznak, nem a "
                        "fiókhoz).",
                        style: AppText.label.copyWith(fontSize: 12),
                      ),
                    ],
                  ],

                  const SizedBox(height: AppSpacing.lg),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: canSubmit ? _submit : null,
                      style: FilledButton.styleFrom(
                        backgroundColor: AppColors.accent,
                        foregroundColor: AppColors.onAccent,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                      ),
                      icon: _busy
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: AppColors.onAccent),
                            )
                          : Icon(
                              _registerMode
                                  ? Icons.person_add_alt_1
                                  : Icons.login,
                              size: 18),
                      label: Text(_registerMode
                          ? "Fiók létrehozása"
                          : "Belépés"),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  Center(
                    child: TextButton(
                      onPressed: _busy
                          ? null
                          : () => setState(() {
                                _registerMode = !_registerMode;
                                _error = null;
                              }),
                      style: TextButton.styleFrom(
                          foregroundColor: AppColors.textSecondary),
                      child: Text(_registerMode
                          ? "Van már fiókom — belépés"
                          : "Nincs még fiókom — létrehozom"),
                    ),
                  ),
                  if (widget.onGuest != null) ...[
                    const SizedBox(height: AppSpacing.sm),
                    const Divider(color: AppColors.border, height: 1),
                    const SizedBox(height: AppSpacing.sm),
                    Center(
                      child: TextButton.icon(
                        onPressed: _busy ? null : widget.onGuest,
                        style: TextButton.styleFrom(
                            foregroundColor: AppColors.textSecondary),
                        icon: const Icon(Icons.person_outline, size: 16),
                        label: const Text(
                            "Folytatás fiók nélkül (vendég)"),
                      ),
                    ),
                    Center(
                      child: Text(
                        SessionStore.devMode
                            ? "Fejlesztői mód BE: a vendég-munka "
                                "kilépés után is megmarad."
                            : "A vendégként végzett munka az app "
                                "bezárásakor elvész.",
                        style: AppText.label.copyWith(fontSize: 11),
                        textAlign: TextAlign.center,
                      ),
                    ),
                    // Fejlesztői mód: fejlesztés alatt a vendég-munka
                    // megőrzése — a fiók-menüből is kapcsolható.
                    Center(
                      child: TextButton(
                        onPressed: _busy
                            ? null
                            : () async {
                                await SessionStore.setDevMode(
                                    !SessionStore.devMode);
                                if (mounted) setState(() {});
                              },
                        style: TextButton.styleFrom(
                            foregroundColor: AppColors.textFaint,
                            padding: EdgeInsets.zero,
                            minimumSize: const Size(0, 28),
                            tapTargetSize:
                                MaterialTapTargetSize.shrinkWrap),
                        child: Text(SessionStore.devMode
                            ? "Fejlesztői mód kikapcsolása"
                            : "Fejlesztői mód bekapcsolása"),
                      ),
                    ),
                  ],
                  const SizedBox(height: AppSpacing.sm),
                  // A futó kiadás száma: egy hibajelentő képernyőképből
                  // így azonnal látszik, melyik verzió ad hibát.
                  Center(
                    child: Text("Sport Machine · v$appVersion",
                        style: AppText.label
                            .copyWith(fontSize: 11, color: AppColors.textFaint)),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
