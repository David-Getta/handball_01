# 2. meccs (Magdeburg–Füchse Berlin, 35:33) — vak lövés-jóslat

> **Az emberi jelöléssel összevetve:** `meccs2_osszevetes.md` — a póz + kamera
> modell 81% felidézés, 55% pontosság a rögzített küszöbön; a teljes modell
> valóban gól-felismerő lett (védések: 4/43).

Az 1. meccsen tanított lövésfelismerő a 2. meccsen **újratanítás nélkül**, más
közvetítővel (ARD, 50 fps), más csarnokban, más mezekkel. A jóslatok a 2.
meccs emberi jelölése ELŐTT kerültek a repóba (`cimkek/meccs2_vak_josolt_*.json`).

## Amit emberi jelölés nélkül már mérni lehet: a gólok

A 68 gól idejét a gép maga olvasta ki az eredményjelzőből (`meccs2_allas.md`,
35:33 = hivatalos). Kérdés: van-e lövés-jelölt a gól (az állásváltozás) előtt?
Viszonyítás: ugyanennyi, véletlenül szórt jelölt mennyit "találna".

| modell | jelöltek | gól előtt jelölt (5 s) | véletlennel | gól előtt jelölt (8 s) | véletlennel |
|---|---|---|---|---|---|
| póz + közvetítés-jelek (`lovesfelismero_m1`) | 104 | **64/68 (94%)** | 14% | 66/68 (97%) | 19% |
| csak póz (`lovesfelismero_m1_csakpoz`) | 265 | **58/68 (85%)** | 33% | 62/68 (91%) | 42% |
| póz + kamera, eredményjelző nélkül (`lovesfelismero_m1_kamera`) | 186 | **62/68 (91%)** | 24% | 65/68 (96%) | 31% |

## Olvasat (óvatosan)

- **A mozgás-felismerés átvihető** egy új meccsre: a csak testpontokból dolgozó
  modell is a gólok 85%-a előtt jelez (véletlennel 33%).
- **A közvetítés-jeles modell nagyrészt GÓL-felismerő lett:** a 104 jelöltből
  95 után 12 s-on belül állásváltozás jön, és sok gólra két jelölt is esik. A
  modell a lövés UTÁNI eredményjelző-változást is látja (2–10 s-os ablak),
  és ez az új meccsen erősen húz. A védett / mellé ment lövésekre legfeljebb ~10
  jelölt jut — ezeket valószínűleg nagyrészt kihagyja.
- **Póz + kamera (eredményjelző nélkül)** a legkiegyensúlyozottabb: az 1.
  meccsen majdnem olyan jó, mint a teljes modell (legjobb F1-nél 75%
  felidézés, 57% pontosság), a 2. meccsen a gólok 91%-a előtt jelez, és a
  186 jelöltből 90 NEM köthető gólhoz — köztük lehetnek a védések és a mellé
  lövések, amiket a teljes modell kihagy. Ez az emberi jelöléssel dől el.
- A végső számot (felidézés MINDEN lövésre, pontosság) az emberi jelölés adja:

      python -m hbd.shot_detect --pose m2_pose.npz --broadcast m2_broadcast.npz --court m2_court.npz \
          --model modellek/lovesfelismero_m1.joblib --events cimkek/meccs2_esemenyek.json --live-only --out osszevetes

## Javított hiba közben

A pálya-szűrő a 2. meccsen a sötét lelátót is padlónak tanulta (a láb alatti
színek 2. leggyakoribb csoportja L≈7 volt) → az emberek 74%-át tartotta meg (1.
meccs: 42%). Javítva (padló csak világos szín lehet) → 46%; a jóslat alig
változott (107 → 104 jelölt), mert itt a közvetítés-jelek döntenek.
