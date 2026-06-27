# Kézilabda szabályok — a rendszer szempontjából releváns kivonat

> Ez NEM a teljes szabálykönyv, hanem a **követést, létszámot és kalibrációt
> befolyásoló** szabályok strukturált kivonata, amit a rendszer logikája használ.
> A teljes (szerzői jogvédett) IHF szabálykönyvet nem tároljuk a repóban.
>
> **⚠️ Ellenőrizni:** a számokat/szabályokat egyeztetni kell az aktuális IHF
> szabálykönyvvel. A `(?)` jelölésű pontok bizonytalanok — kérlek erősítsd meg.

## 1. Pálya geometria (kalibrációhoz)
- Pálya: **40 m × 20 m**.
- Kapu: **3 m széles × 2 m magas**.
- Kapuelőtér-vonal (kapusvonal): **6 m** a kaputól (félkör). Ide csak a kapus léphet.
- Szabaddobási vonal: **9 m**, szaggatott.
- **7 m-es** vonal: büntetődobás.
- **4 m-es** vonal: kapus-korlátozó jel.
- Középvonal, oldalvonalak, alapvonalak.
- → Ezek metszéspontjai/ívei a homográfia-kalibráció referenciapontjai.

## 2. Létszám
- Keret: max. **14 (?) / 16 (?)** játékos versenytől függően (ellenőrizni).
- Pályán egyszerre csapatonként: **7 fő** (6 mezőnyjátékos + 1 kapus) — normál
  esetben. De a tényleges szám **változó** (lásd kiállítás, 7. mezőnyjátékos).
- Pozíciós szerepek (becsléshez): bal szélső, bal átlövő, irányító, jobb átlövő,
  jobb szélső, beálló, kapus.

## 3. Cserék
- **Bármikor, korlátlanul**, a saját **cserezónán** keresztül, bejelentés nélkül
  ("repülő csere").
- Következmény a követésre: játékosok eltűnhetnek/megjelenhetnek a cserezónánál —
  ezt meg kell különböztetni a kiállítástól és a képen kívüliségtől.

## 4. Kiállítások
- Alap: **2 perc**. Több játékos lehet **egyidejűleg** kiállítva.
- **4 perc (?)** is előfordulhat (gyakorlatilag két 2 perc) — felhasználói
  észrevétel alapján; pontos szabály ellenőrizni.
- **Progresszív büntetés**: ugyanazon játékos 3. kiállítása = kizárás (?).
- **Kizárás (piros lap)**: a játékos véglegesen kiáll, de a csapat **2 percig**
  hiányos létszámmal játszik tovább.
- Modell: kiállítás-intervallumok listája csapatonként (kezdet + 2/4 perc),
  átfedés megengedett. Pillanatnyi létszám = alap − aktív kiállítások.

## 5. Kapusszabály
- A kapus **eltérő mezszínt** visel a saját mezőnyjátékosaitól és az ellenfelektől
  → ez jelzés a csapat-szétválasztáshoz és a kapus azonosításához.
- A kapus mezőnyjátékossá válhat és vissza; mezőnyjátékos lehet kapus.
- **7. mezőnyjátékos a kapus helyett**: nincs kapus a pályán (üres kapu),
  helyette 7 mezőnyjátékos. Az "extra" játékos a kapus színét / megkülönböztető
  mezt visel (?). Jelzés a rendszernek: a kapus-szín eltűnik a pályáról.

## 6. Időkezelés
- Játékidő: **2 × 30 perc**, félidei szünet **10 perc (?)**.
- Kieséses meccsen hosszabbítás: **2 × 5 perc (?)**.
- **Csapat-időkérés (team timeout)**: **1 perc**, csapatonként **3 (?)** meccsenként
  (félidőnként max. 2 (?)).
- → Ezek tagolják az idővonalat és a fázis-szegmentálást.

## Hogyan használja ezt a rendszer
- **Kalibráció [A]**: az 1. pont geometriája adja a referenciapontokat.
- **Csapat-szétválasztás [D]** + **kapus**: az 5. pont mezszín-szabálya.
- **Létszám-állapot [F]**: a 2., 4., 5. pont határozza meg a pillanatnyi létszámot.
- **Esemény-idővonal**: a 3., 4., 6. pont eseményei (csere, kiállítás, időkérés,
  félidő) — MVP-ben kézzel felvíve, 2. fázisban automatikusan felismerve.

## Nyitott / megerősítendő pontok
- [ ] Keretlétszám pontos száma (14 vagy 16, versenyfüggő?).
- [ ] 4 perces kiállítás pontos szabálya.
- [ ] Progresszív büntetés / kizárás küszöbei.
- [ ] 7. mezőnyjátékos mezszín-szabálya (megkülönböztető mez?).
- [ ] Időkérések száma és időbeli korlátai.
