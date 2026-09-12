# Figura-könyvtár — mi tér vissza meccsről meccsre

A meccsen belüli figura-rétegek (`setplay_efficiency`, `setplay_finishers`,
`setplay_concentration`, …) EGY meccs támadásait klaszterezik, és sorszámmal
nevezik a figurát ("2. figura"). Két meccs "2. figurája" nem ugyanaz. A
könyvtár azt kérdezi: **melyik figurájuk tér vissza meccsről meccsre** —
ez a felderítés legbiztosabb lapja, mert amit minden meccsen hoznak, arra
biztosan lehet készülni. (`handball/pipeline/setplays.py`, a
"Figura-könyvtár MECCSEK KÖZÖTT" szakasz.)

## Hogyan épül

1. **Irány-normált ujjlenyomat** (`normalized_signature`). A támadás
   mozgás-ujjlenyomata a támadó csapat térbeli eloszlása egy 6×3-as
   rácson. Félidőben térfelet cserélnek, más meccsen más oldalról
   támadnak — a nyers alak tükörképként jönne ki. Ezért a −x kapura
   támadó szakaszt 180°-kal forgatjuk (x → 40−x, y → 20−y): mindig a +x
   kapu felé nézünk, és a támadó saját bal/jobb oldala marad (a
   lanes-rétegek oldal-egyezménye). Az irányt a támadók átlagos x-e adja
   (`attack_direction`).
2. **Alakok meccsenként** (`setplay_shapes`). A támadás-szakaszokat
   csapatonként klaszterezzük; minden legalább `SPL_MIN_ATTACKS` (3)
   támadásból álló klaszterből egy sor lesz: a középpont (`shape`), a
   támadások, a bennük (vagy 3 mp-en belül utánuk) esett lövések és
   gólok, a kezdő-kockák (`starts`, klip-exporthoz), és az **edzői név**.
3. **Edzői név** (`shape_zone`). A súlypont oldala és mélysége — "bal
   oldal, a kapuelőtér előtt": `SPL_DEEP_X_M` (31 m) fölött a kapuelőtér
   előtt, `SPL_MID_X_M` (24 m) fölött a 9-es körül, alatta távolról; a
   felezőtől `SPL_SIDE_Y_M` (2 m) odébb már oldal. "3. klaszter" senkinek
   nem mond semmit.
4. **Könyvtár** (`setplay_library`). Több meccs sorait fésüli össze: a
   `SPL_MERGE_THRESHOLD` (0,15) távolságon belüli alakok egy figurává
   olvadnak (a középpont a támadás-számmal súlyozott átlag), a
   darabszámok összeadódnak, és megszámoljuk, hány KÜLÖN meccsen fordult
   elő (a sorok `match_id`-je szerint). A legalább `SPL_MIN_MATCHES` (2)
   meccsen látott alak a **visszatérő figura**; az ítélet egy mondat.

## Hol jelenik meg

- **Felderítés** (`scouting.py`): a `ScoutingReport.setplay_shapes` a nyers
  sorokat tárolja (meccsek közt egymás mögé kerülnek — pontos), a
  `setplay_library` mezőt a `combine_reports` az összefésült sorokból
  ÚJRASZÁMOLJA. Edzői kulcs, 459. meccsterv-szabály (a visszatérő
  figurájuk × a ti szabad lövést engedő falatok), "Visszatérő figuráik"
  szakasz rajzzal a felderítő képernyőn és a nyomtatható jelentésben.
- **Szezon-riport**: "Saját visszatérő figuráink" — a saját csapat
  könyvtára a szezon összes meccséből, hozammal.
- **Meccs-elemző** és **meccsjelentés**: a meccs figurái alakkal (mini-
  pálya, edzői név), a 478. edzés-szabály (a leggyakoribb saját figura gól
  nélkül → új befejezés), edzői összefoglaló mondat.
- **Élő követés**: `GET /matches/{id}/figure-alerts` — amikor egy csapat a
  visszatérő figuráját kezdi játszani, jelzés a védekező oldalnak.
- **Klipek**: a "visszatérő figura" klip-típus — e meccs azon támadásai,
  amelyek a könyvtári alakot játsszák (`recurring_figure_segments`).

A csapat könyvtárát az API a könyvtár ÖSSZES elemzett meccséből építi
(`_team_figure_library`, a csapat NEVE szerint), meccsenkénti
alak-gyorsítótárral: (meccs-azonosító, kockaszám) kulccsal, hogy az
újrafeldolgozott meccs ne olvasson elavult alakot.

## Figura-nevek

A könyvtár zóna-neve ("bal oldal, a kapuelőtér előtt") helyett az edző
a saját szavával nevezheti a figurát ("beúszós kereszt"). A név
könyvtár-szintű (`figures.json` a meccs-mappa mellett, mint a
játékos-nevek), csapatonként az ALAKHOZ tartozik: a
`SPL_MERGE_THRESHOLD`-on belüli alak kapja — így a következő meccs
ugyanazon figurája is a nevét viseli. Végpontok: `GET/POST
/library/figures` (közeli alak átnevez, üres név töröl). Az API minden
figura-sort névvel ad (`_nevesit`): felderítés, `/setplays`, élő
riasztás szövege, klip-címke, és a nyomtatható jelentések
(`figure_namer` a meccsjelentésben). A kliens a felderítés figura-
sorának ceruza-gombjával nevez.

## Korlátok

- Egy meccsből nincs könyvtár: a felderítés-választó ezért kettőt kér.
- A csapat azonosítása a NÉV szerint megy: az "MTK" és az "MTK Budapest"
  két csapat.
- Az alak egy 6×3-as eloszlás, nem mozgáspálya: a "hol tömörülnek"
  kérdésre válaszol, a "ki hova fut" kérdésre a figura-tervező könyvtára
  (mentett figurák, `match_attacks_to_playbook`).

## Tesztek

`backend/tests/test_setplays.py` (a "Figura-könyvtár meccsek között"
szakasz): a tükörkép irány-normálva egy alak; edzői nevek; a könyvtár két
meccs (a másodikban a másik kapura támadva) között visszatérő figurát
talál, egy meccsből nem; a VALÓDI felderítés-út; a riasztás- és a
setplays-végpont; a meccsenkénti gyorsítótár. A rajz-felületek őrei a
`test_client_calib_check.py`-ban, a jelentések a `test_report_html.py` és
`test_match_report.py` fájlokban.
