/// Egy cím megnyitása a rendszer böngészőjében — az app böngészős 3D/VR
/// linkjei (a 3D fül, a kezdőlap megbeszélés-kártyája) ezen mennek.
///
/// Windowson NEM a `cmd /c start`: a cmd értelmezője a címet az első
/// `&`-nél elvágta (a több paraméteres link — idő, kamera, rétegek —
/// elvesztette a beállításokat). A `rundll32 url.dll,FileProtocolHandler`
/// a címet egyben adja a böngészőnek.
library;

import "dart:io";

/// Megnyitja a címet; hamis, ha nem sikerült (a hívó ilyenkor a címet
/// mutatja, hogy kézzel nyissák meg).
Future<bool> openInBrowser(String url) async {
  try {
    if (Platform.isMacOS) {
      return (await Process.run("open", [url])).exitCode == 0;
    }
    if (Platform.isWindows) {
      // (a rundll32 kilépési kódja nem megbízható — a kivétel a hiba jele)
      await Process.run("rundll32", ["url.dll,FileProtocolHandler", url]);
      return true;
    }
    return (await Process.run("xdg-open", [url])).exitCode == 0;
  } catch (_) {
    return false;
  }
}
