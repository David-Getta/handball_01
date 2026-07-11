/// Automatikus frissítés — a Claude-alkalmazáshoz hasonló élmény.
///
/// Az app induláskor (és kézi kérésre) megnézi a GitHub Releases legfrissebb
/// kiadását. Ha annak verziója újabb, mint a beépített [appVersion]:
///  - macOS: letölti a SportMachine-macOS.zip-et, leállítja a motort,
///    kicseréli önmagát (az .app csomagot), és újraindul.
///  - Windows: letölti a SportMachine-Setup.exe-t és csendes módban
///    lefuttatja (a telepítő maga cseréli a fájlokat, majd indítja az appot).
///
/// Fejlesztői futásnál ([appVersion] == "0.0.0-dev") az ellenőrzés kikapcsol.
///
/// FONTOS korlát: privát GitHub-repónál a /releases/latest hitelesítés nélkül
/// 404-et ad — ilyenkor a frissítés-ellenőrzés nem lát kiadást. Megoldás:
/// a repót publikussá tenni, vagy külön publikus "releases" repót használni.
library;

import "dart:convert";
import "dart:io";

import "package:http/http.dart" as http;

import "../version.dart";
import "backend_launcher.dart";

/// Egy elérhető frissítés adatai.
class UpdateInfo {
  /// Az új verzió (pl. "0.1.2" — a "v" előtag nélkül).
  final String version;

  /// A letöltendő csomag URL-je (browser_download_url).
  final String url;

  /// A csomag fájlneve (pl. "SportMachine-macOS.zip").
  final String assetName;

  const UpdateInfo({
    required this.version,
    required this.url,
    required this.assetName,
  });
}

class UpdateService {
  /// A GitHub repó, ahol a kiadások megjelennek.
  static const owner = "David-Getta";
  static const repo = "handball_01";

  /// "1.2.3" / "v1.2.3" → [1,2,3]; érthetetlen verziónál null.
  static List<int>? _parse(String v) {
    final m = RegExp(r"^v?(\d+)\.(\d+)\.(\d+)").firstMatch(v.trim());
    if (m == null) return null;
    return [1, 2, 3].map((i) => int.parse(m.group(i)!)).toList();
  }

  /// Igaz, ha `a` újabb, mint `b`.
  static bool _newer(List<int> a, List<int> b) {
    for (var i = 0; i < 3; i++) {
      if (a[i] != b[i]) return a[i] > b[i];
    }
    return false;
  }

  /// Ezen a platformon melyik kiadás-csomagot keressük?
  static String? get _assetName {
    if (Platform.isMacOS) return "SportMachine-macOS.zip";
    if (Platform.isWindows) return "SportMachine-Setup.exe";
    return null; // más platformra még nincs automatikus frissítés
  }

  /// Megnézi, van-e újabb kiadás. `null`, ha nincs (vagy fejlesztői a build).
  ///
  /// Hálózati/API hibánál (pl. privát repó → 404) kivételt dob, hogy a kézi
  /// ellenőrzés érdemi hibaüzenetet tudjon mutatni.
  Future<UpdateInfo?> check() async {
    final current = _parse(appVersion);
    if (current == null) return null; // fejlesztői build — nincs mit frissíteni

    final asset = _assetName;
    if (asset == null) return null;

    final resp = await http.get(
      Uri.parse("https://api.github.com/repos/$owner/$repo/releases/latest"),
      headers: {"Accept": "application/vnd.github+json"},
    ).timeout(const Duration(seconds: 8));
    if (resp.statusCode != 200) {
      throw HttpException("GitHub Releases: HTTP ${resp.statusCode}");
    }

    final body = jsonDecode(resp.body) as Map<String, dynamic>;
    final latest = _parse((body["tag_name"] as String?) ?? "");
    if (latest == null || !_newer(latest, current)) return null;

    final assets = (body["assets"] as List?) ?? const [];
    for (final a in assets) {
      final map = a as Map<String, dynamic>;
      if (map["name"] == asset) {
        return UpdateInfo(
          version: latest.join("."),
          url: map["browser_download_url"] as String,
          assetName: asset,
        );
      }
    }
    return null; // van újabb címke, de ehhez a platformhoz nincs csomag
  }

  /// Letölti és telepíti a frissítést, majd újraindítja az appot.
  /// `onProgress`: 0.0–1.0 a letöltés alatt (ismeretlen méretnél null).
  Future<void> downloadAndInstall(
    UpdateInfo info, {
    void Function(double?)? onProgress,
  }) async {
    final tmp = await Directory.systemTemp.createTemp("sportmachine_upd");
    final target = File("${tmp.path}${Platform.pathSeparator}${info.assetName}");

    // Letöltés folyamat-jelzéssel (a GitHub átirányít a tényleges tárolóra,
    // a http csomag ezt magától követi).
    final req = http.Request("GET", Uri.parse(info.url));
    final resp = await http.Client().send(req);
    if (resp.statusCode != 200) {
      throw HttpException("Letöltés sikertelen: HTTP ${resp.statusCode}");
    }
    final total = resp.contentLength;
    var received = 0;
    final sink = target.openWrite();
    await for (final chunk in resp.stream) {
      sink.add(chunk);
      received += chunk.length;
      onProgress?.call(total == null ? null : received / total);
    }
    await sink.close();

    // A futó motor fogná a fájlokat — a csere előtt leállítjuk.
    BackendLauncher.instance?.stop();

    if (Platform.isMacOS) {
      await _installMacOS(target, tmp);
    } else if (Platform.isWindows) {
      await _installWindows(target);
    }
  }

  /// macOS: kicsomagolás → az .app csomag cseréje → újraindítás.
  /// A cserét egy leválasztott shell végzi, MIUTÁN ez a folyamat kilépett
  /// (futó programot nem lehet biztonságosan felülírni).
  Future<void> _installMacOS(File zip, Directory tmp) async {
    final extractDir = "${tmp.path}${Platform.pathSeparator}extracted";
    final r = await Process.run(
        "/usr/bin/ditto", ["-xk", zip.path, extractDir]);
    if (r.exitCode != 0) {
      throw Exception("Kicsomagolás sikertelen: ${r.stderr}");
    }

    // Az új .app megkeresése a kicsomagolt mappában.
    String? newApp;
    await for (final e in Directory(extractDir).list()) {
      if (e.path.endsWith(".app")) {
        newApp = e.path;
        break;
      }
    }
    if (newApp == null) {
      throw Exception("A letöltött csomagban nincs .app.");
    }

    // A jelenlegi .app útvonala: .../SportMachine.app/Contents/MacOS/exe
    final appPath =
        File(Platform.resolvedExecutable).parent.parent.parent.path;
    if (!appPath.endsWith(".app")) {
      throw Exception("Nem .app csomagból fut az alkalmazás ($appPath) — "
          "a csere kihagyva.");
    }

    // Leválasztott csere-szkript: vár, töröl, másol, újraindít.
    await Process.start(
      "/bin/bash",
      [
        "-c",
        'sleep 1; rm -rf "\$0"; /usr/bin/ditto "\$1" "\$0"; open "\$0"',
        appPath,
        newApp,
      ],
      mode: ProcessStartMode.detached,
    );
    exit(0);
  }

  /// Windows: az Inno Setup telepítő csendes futtatása — az bezárja az appot,
  /// cseréli a fájlokat, majd újraindítja a programot.
  Future<void> _installWindows(File installer) async {
    await Process.start(
      installer.path,
      const ["/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
      mode: ProcessStartMode.detached,
    );
    exit(0);
  }
}
