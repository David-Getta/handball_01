# Kliens — felülnézeti taktikai nézet (Flutter, desktop-first)

> **Dizájn**: prémium, letisztult, sötét felület (egységes dizájnrendszer:
> `lib/theme/app_theme.dart`) — kártyás elrendezés, visszafogott kontraszt, teal
> akcentus. A cél egy igényes, "exkluzív" termékélmény.

A kézilabda-elemző **kliens appja**. Lekéri a backendtől a Tracking JSON-t, és
kirajzolja a felülnézeti pályát: mozgó játékosok (mért = tele pont, **becsült =
halvány + szaggatott gyűrű**), labda, mezszámok, idővonal-lejátszás.

Funkciók:
- **Játékos-nézet**: mozgó pontok a felülnézeti pályán, lejátszással.
- **Hőtérkép-nézet**: a választott csapat látogatottsága a pályán (kapcsolható,
  csapatválasztóval).
- **Statisztika-panel** (jobb oldalt): játékosonkénti futott táv és átlagsebesség.
- **Élő taktikai felirat** (a pálya alatt): az aktuális fázis (hazai/vendég
  támadás, átmenet) és támadáskor a védő csapat formája (6-0 / 5-1 / 3-2-1).
- **Meccs-összegző** (jobb oldali "Összegzés" tab): csapatstílus egy nézetben —
  fázis-megoszlás, csapatonkénti védekezési forma, tempó (birtoklások, támadás-
  hossz, átmenet-arány, labda-tempó) és a visszatérő figurák száma.
- **Játékos-döntések** ("Döntések" tab): egy kiválasztott játékos passzeloszlása
  ("10/7-szer ide passzol") és a döntés-minőség (optimális arány, átlagos veszteség).
- **Figura-tervező** (fejléc gomb): az edző a felülnézeti pályán húzza a támadókat
  (Kezdő/Vég kulcs-pozíció), beállítja a tanult védelmet, és lejátszatja a figurát
  ellene — a rendszer pontozza a teremtett lövőhelyzetet (5. fázis).
- A hőtérkép és a statisztika a kliensen is kiszámolódik (a backend tükre), így
  **backend nélkül, demó-adattal is** működik.

> Architektúra: **desktop-first** (Windows/Mac/Linux), ugyanaz a kódbázis fut
> tableten (iPad/Android) is. **Lokális mód**: a backend a laptopon, a kliens a
> `localhost`-on éri el. Lásd a repó `docs/ARCHITECTURE.md`.

## Felépítés
```
client/
├── pubspec.yaml
└── lib/
    ├── main.dart                # belépési pont (desktop-first)
    ├── models/tracking.dart     # a backend Tracking JSON Dart-tükre
    ├── services/api_client.dart # lokális backend (localhost:8000) hívása
    ├── sim/demo_data.dart       # beágyazott demó → backend NÉLKÜL is mozog
    ├── analytics/
    │   ├── court_analytics.dart  # hőtérkép + játékos-statisztika (a backend tükre)
    │   ├── tactics.dart          # fázis/birtoklás/forma (az aktuális frame-re)
    │   └── match_summary.dart    # meccs-összegzés (fázis%, forma, tempó, figurák)
    └── ui/
        ├── court_geometry.dart  # pályaméretek + 6 m-es kapuelőtér alakja
        ├── court_painter.dart   # a felülnézeti rajzoló (CustomPainter)
        ├── heatmap_painter.dart # hőtérkép-réteg a pálya fölött
        ├── stats_panel.dart     # statisztika-panel (táv/sebesség)
        ├── summary_panel.dart   # meccs-összegző panel (csapatstílus)
        └── match_screen.dart    # betöltés + nézetváltó + tabos panel + lejátszó
```

## Futtatás (asztali gép / laptop)

Előfeltétel: Flutter SDK (stable). A desktop-támogatás egyszeri engedélyezése:
```bash
flutter config --enable-windows-desktop   # vagy --enable-macos-desktop / --enable-linux-desktop
```
A kliens mappában:
```bash
cd client
flutter pub get
flutter run -d windows     # vagy: -d macos / -d linux
```

**Backend nélkül is elindul**: ha a `localhost:8000` nem elérhető, a beágyazott
demó-adatot játssza le (mozgó pontok), így rögtön látható a felülnézeti nézet.

## Backenddel együtt (lokális mód)

1. Indítsd a backendet (lásd `backend/README.md`):
   ```bash
   cd backend && pip install -e . && uvicorn "handball.api.app:create_app" --factory
   ```
2. Töltsd fel a backend tárába a szimulált meccset (vagy a valódit), és a kliens a
   `MatchScreen(matchId: ...)`-ben megadott id-t kéri le.

## Megjegyzések
- A kék/piros itt **megjelenítési** szín, NEM a valódi mez — a valódi mezszínek
  meccsenként változnak (a backend kezeli, lásd `appearance.py`).
- A 6 m-es kapuelőteret sárgásan rajzoljuk (a valódi pályán is sárga volt).
