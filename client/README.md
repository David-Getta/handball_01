# Kliens — felülnézeti taktikai nézet (Flutter, desktop-first)

A kézilabda-elemző **kliens appja**. Lekéri a backendtől a Tracking JSON-t, és
kirajzolja a felülnézeti pályát: mozgó játékosok (mért = tele pont, **becsült =
halvány + szaggatott gyűrű**), labda, mezszámok, idővonal-lejátszás.

Funkciók:
- **Játékos-nézet**: mozgó pontok a felülnézeti pályán, lejátszással.
- **Hőtérkép-nézet**: a választott csapat látogatottsága a pályán (kapcsolható,
  csapatválasztóval).
- **Statisztika-panel** (jobb oldalt): játékosonkénti futott táv és átlagsebesség.
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
    ├── analytics/court_analytics.dart  # hőtérkép + játékos-statisztika (a backend tükre)
    └── ui/
        ├── court_geometry.dart  # pályaméretek + 6 m-es kapuelőtér alakja
        ├── court_painter.dart   # a felülnézeti rajzoló (CustomPainter)
        ├── heatmap_painter.dart # hőtérkép-réteg a pálya fölött
        ├── stats_panel.dart     # oldalsó statisztika-panel (táv/sebesség)
        └── match_screen.dart    # betöltés + nézetváltó + lejátszó
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
