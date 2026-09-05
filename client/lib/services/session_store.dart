/// Munkamenet-tár — a belépés MEGMARAD az app újraindítása után is.
///
/// A program a felhasználó saját gépén fut, a fiókok is ott vannak (a motor
/// adatmappájában, lásd backend/handball/accounts.py). A kliens itt csak a
/// munkamenet-kulcsot (token) és az offline feltétel-elfogadást tárolja egy
/// kis JSON-fájlban, hogy ne kelljen minden indításkor újra belépni.
///
/// A fájl helye a backend adatmappa-logikáját tükrözi:
///   Windows: %LOCALAPPDATA%\SportMachine\session.json
///   macOS:   ~/Library/Application Support/SportMachine/session.json
///   Linux:   $XDG_DATA_HOME/sportmachine/session.json (vagy ~/.local/share/…)
library;

import "dart:convert";
import "dart:io";

class SessionStore {
  /// A belépett munkamenet kulcsa — a memóriában is tartjuk, hogy a
  /// hívások ne olvassák újra a lemezt.
  static String? token;

  /// A motor nélküli (demó) módban elfogadott feltétel-verzió — 0, ha
  /// még nem fogadták el.
  static int offlineTermsVersion = 0;

  /// Fejlesztői mód: a vendég-munkamenet munkája NEM vész el kilépéskor.
  /// A fiók-menüből és a belépő képernyőről kapcsolható.
  static bool devMode = false;

  /// Vendég-munkamenet fut-e (fiók nélküli belépés). Ha az app úgy zárul
  /// be, hogy ez igaz, a következő indulás — fejlesztői mód híján —
  /// eltakarítja a vendég-munkamenetben készült meccseket.
  static bool guestMode = false;

  /// A vendég-belépéskor MÁR MEGLÉVŐ meccsek azonosítói — a takarítás
  /// csak az ezután készülteket törli.
  static List<String> guestBaseline = [];

  static File _file() {
    Directory base;
    if (Platform.isWindows) {
      final local = Platform.environment["LOCALAPPDATA"];
      base = Directory(
          "${local ?? "${Platform.environment["USERPROFILE"]}\\AppData\\Local"}"
          "\\SportMachine");
    } else if (Platform.isMacOS) {
      base = Directory("${Platform.environment["HOME"]}"
          "/Library/Application Support/SportMachine");
    } else {
      final xdg = Platform.environment["XDG_DATA_HOME"];
      base = Directory(xdg != null && xdg.isNotEmpty
          ? "$xdg/sportmachine"
          : "${Platform.environment["HOME"]}/.local/share/sportmachine");
    }
    return File("${base.path}${Platform.pathSeparator}session.json");
  }

  /// Betöltés indításkor (hiányzó vagy sérült fájlnál csendben üres marad).
  static Future<void> load() async {
    try {
      final f = _file();
      if (!await f.exists()) return;
      final data = jsonDecode(await f.readAsString()) as Map<String, dynamic>;
      final t = data["token"];
      token = (t is String && t.isNotEmpty) ? t : null;
      final v = data["offline_terms_version"];
      offlineTermsVersion = v is int ? v : 0;
      devMode = data["dev_mode"] == true;
      guestMode = data["guest_mode"] == true;
      final gb = data["guest_baseline"];
      guestBaseline = gb is List
          ? gb.whereType<String>().toList()
          : <String>[];
    } catch (_) {
      token = null;
      offlineTermsVersion = 0;
      devMode = false;
      guestMode = false;
      guestBaseline = [];
    }
  }

  /// Mentés (a mappa létrehozásával együtt) — hiba esetén az app működik
  /// tovább, csak a következő indításkor újra be kell lépni.
  static Future<void> save() async {
    try {
      final f = _file();
      await f.parent.create(recursive: true);
      await f.writeAsString(jsonEncode({
        "token": token,
        "offline_terms_version": offlineTermsVersion,
        "dev_mode": devMode,
        "guest_mode": guestMode,
        "guest_baseline": guestBaseline,
      }));
    } catch (_) {}
  }

  /// Belépés után: a kulcs eltárolása.
  static Future<void> setToken(String? value) async {
    token = (value != null && value.isNotEmpty) ? value : null;
    await save();
  }

  /// A motor nélküli módban elfogadott feltétel-verzió rögzítése.
  static Future<void> setOfflineTerms(int version) async {
    offlineTermsVersion = version;
    await save();
  }

  /// Kilépés: a kulcs törlése (az offline elfogadás megmarad).
  static Future<void> clear() async {
    token = null;
    await save();
  }

  /// Fejlesztői mód kapcsolása (a vendég-munka megőrzése).
  static Future<void> setDevMode(bool value) async {
    devMode = value;
    await save();
  }

  /// Vendég-munkamenet indítása: a meglévő meccsek listájával.
  static Future<void> startGuest(List<String> baseline) async {
    guestMode = true;
    guestBaseline = baseline;
    await save();
  }

  /// A vendég-munkamenet lezárása (takarítás után vagy belépéskor).
  static Future<void> endGuest() async {
    guestMode = false;
    guestBaseline = [];
    await save();
  }
}
