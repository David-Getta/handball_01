# 2. meccs — a vak jóslat összevetése az emberi jelöléssel

A három lövésfelismerő az 1. meccsen tanult (Veszprém–Flensburg, EHF BL), és a
2. meccsre (Magdeburg–Füchse Berlin 35:33, HBL, ARD-közvetítés, más csarnok,
más mezek, 50 fps) **újratanítás nélkül** jósolt. A jóslatok a jelölés ELŐTT
kerültek a repóba (`cimkek/meccs2_vak_josolt_lovesek_*.json`); a küszöb is az
1. meccsen rögzített (a 80%-os felidézéshez tartozó). Emberi jelölés:
`cimkek/meccs2_esemenyek.json` (Meccsjelölő; 128 élő lövés: 69 gól — köztük egy
visszafújt —, 43 védés, 12 mellé, 4 eredmény nélkül; 85 ismétlés, ezek itt nem számítanak).

Egy jelölt akkor talált, ha 1,5 s-on belül van egy jelölt lövés (ugyanaz a mérés,
mint az 1. meccsen).

| modell (rögzített küszöb) | jelölt | felidézés | pontosság | téves / perc | véletlennel felidézés |
|---|---|---|---|---|---|
| **póz + kamera** (`lovesfelismero_m1_kamera`, 0,25) | 186 | **103/128 (80%)** | **55%** | 0,90 | ~10% |
| csak póz (`lovesfelismero_m1_csakpoz`, 0,1) | 265 | 103/128 (80%) | 39% | 1,76 | ~13% |
| póz + közvetítés (`lovesfelismero_m1`, 0,3) | 104 | 68/128 (53%) | 65% | 0,39 | ~5% |

Az eredmény szerint (talált / összes):

| modell | gól | védés | mellé |
|---|---|---|---|
| póz + kamera | 63/69 | 31/43 | 6/12 |
| csak póz | 60/69 | 32/43 | 8/12 |
| póz + közvetítés | 63/69 | **4/43** | 1/12 |

Utólag választott küszöbbel (legjobb F1, optimista): póz + kamera 78% felidézés
/ 58% pontosság; csak póz 70% / 54%; póz + közvetítés 66% / 59%.

## Olvasat

- **A mozgás-felismerés átvihető egy új meccsre.** A póz + kamera modell az 1.
  meccsen rögzített küszöbbel 80%-ot talál meg a lövésekből 55%-os pontossággal,
  pedig a 2. meccset nem látta. Ez az 1. meccs keresztvalidált eredményével
  egyezik (ott a legjobb F1-nél 75% / 57%).
- **A vak jóslatkor leírt gyanú beigazolódott.** A teljes (közvetítés-jeles)
  modell gól-felismerő lett: a gólok 91%-át találja, a védések 9%-át. Az
  eredményjelző-változást tanulta meg, nem a lövést. Új közvetítőre ezért a
  kamera-jeles változat a jó; a közvetítés-jeleket csak ugyanannál a
  közvetítőnél érdemes használni.
- **A csak póz modell** ugyanannyit talál, de kétszer annyi téves riasztással;
  a kamera mozgása (követő svenkelés a lövés után) a pontosságot javítja.
- **Ami kimarad:** a mellé lövések fele. Ezek egy része a jelölő szerint
  visszafújt lövés (szabaddobás, hetes): a dobómozdulat valódi, de rövidebb.

## Jelölési megjegyzések

A jelölés az eredményjelzőről gépileg kiolvasott 68 góllal egyezik; a 69. élő
gól-jelölés (26:15) mögött nincs állásváltozás — a jelölő szerint a labda
bement, de belemenést (támadó faultot) fújtak. Lövésnek helyes, a címkében
`visszafujva` jelzéssel.
