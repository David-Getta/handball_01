# Változásnapló (CHANGELOG)

A Sport Machine kiadásainak emberi nyelvű összefoglalója. A részletes
történet a squash-merge-elt PR-okban él; itt a lényeg, témák szerint.

## Kiadatlan — a v0.1.18 tartalma (a v0.1.17 óta, PR #57–#158)

### Megbízhatóság — nem veszik el munka
- **Szelíd megszakítás**: a Megszakítás gomb az addig feldolgozott részt
  elmenti (nem dob el órákat). (#89)
- **Bezárás-védelem**: az app bezárásakor a futó feldolgozás rendezetten
  leáll és mentésre kerül. (#90)
- **Időszakos checkpoint**: hosszú futásnál 3 percenként részeredmény-
  mentés — áramszünet/összeomlás legfeljebb pár percet visz el. (#91)
- **Részleges meccs jelölés + folytatás**: a félbemaradt meccs a
  könyvtárban címkét kap, és onnan folytatható, ahol megszakadt; a
  részek egy gombbal teljes meccsé fűzhetők (a lejátszás megmarad).
  (#94, #100)
- **Feldolgozás-előzmények + újra-feldolgozás**: a lezárt job-ok naplója
  újraindítás után is megvan; a hibás futás egy kattintással, a mentett
  beállításokkal újraindítható. (#124, #125)
- **Kalibráció-védelem**: önmetsző/elfajzott sarkokkal a feldolgozás el
  sem indul; a kalibrációs képernyő mentés előtt figyelmeztet; a
  detektálás-próba a pálya-modellt a próbaképre vetíti ("ebből N a
  pályán"). (#120, #121)
- **Rendszer-ellenőrzés**: telepítés-diagnosztika egy hívásban
  (csomagok, modell, írási jog, tárhely, kodek). (#127)

### AI-elemzés — új rétegek
- **Helyzetminőség (xG)**: minden lövés értéke a helyéből; csapat- és
  lövőnkénti várható gól, befejezés-hatékonyság — a lövéstérképen, az
  összefoglalóban, a jelentésben, a felderítésben és a játékos-trendben.
  (#95–#99)
- **Védekezés-elemzés**: szabadon hagyott lövők (fedezés-hiba),
  zóna-lyukak, kapott xG — térképen, jelentésben, felderítésben,
  zóna-sávokkal. (#101, #102, #128)
- **Gólpassz (assist)**: a gól előkészítője az eseménylistában és az
  összefoglalóban. (#93)
- **Momentum-okok**: a gól-sorozatok "miért" címkéi (emberelőny, 7 a 6,
  védekezés-váltás, tempó-esés, időkérés ellenére, cserehullám után).
  (#92, #110)
- **Hétméteres-kimenetel**: gól/védés/kihagyás + csapat- és
  kapus-mérleg. (#105, #106)
- **Csere-felismerés**: cserehullámok a cserezónán át + a cserék utáni
  mérleg — a felderítésben mintákkal ("hátrányban forgatnak"). (#107,
  #111)
- **Időkérés-felismerés + hatás**: a játék tartós leállása a mozgás-
  jelekből, a valószínű kérővel és "megtörte-e a sorozatot" ítélettel.
  (#108, #109)
- **Irányító-függés**: mi történik a támadással a fő szervező nélkül —
  "fogd meg" kulcs a felderítésben. (#103)
- **Edzés-fókusz**: a meccs gyengeségeiből következő gyakorlás-javaslatok
  (meccs- és szezon-szinten, visszatérő gyengeségekkel). (#114, #115,
  #117, #140, #142)
- **Támadás-hatékonyság**: melyik támadás-típus (lerohanás/gyors/felállt/
  7a6) mennyire eredményes — összefoglalóban, jelentésben, felderítésben,
  a meccs-nézetben. (#136, #137, #138, #139)
- **Átmenet-védekezés**: gyors kapott gólok labdavesztés után (a
  visszazárás mérőszáma) — kiemeléssel és felderítési kulccsal. (#141,
  #142)
- **Vezetés-alakulás**: legnagyobb előny, hányszor fordult a meccs, ki
  meddig vezetett — összefoglalóban, jelentés-fejlécben, appban. (#144,
  #145, #146)
- **Labdabirtoklás-arány**: melyik csapat birtokolta többet a labdát —
  összefoglalóban, jelentésben, felderítésben, szezon-összevetésben.
  (#148, #149, #150, #152)
- **Gólok idő-eloszlása**: mikor esnek a gólok (5 perces bontásban) —
  app-diagram és jelentés-blokk. (#153, #154, #155)
- **Gólpassz-hálózat**: ki kinek készíti elő a gólokat (gól-párosok,
  gólpassz-vezérek) — összefoglalóban és a csomag-exportban. (#156,
  #157, #158)

### Kliens-élmény
- **Meccs-sztori idővonal**: gólok, sorozatok, emberelőnyök, 7 a 6,
  hetesek, cserék, időkérések egy sávon a lejátszó felett. (#104, #107,
  #108)
- **Idő-szűrő**: 1./2. félidő külön nézete a lövéstérképen, hőtérképen
  és passz-hálón. (#123, #126)
- **Szezon-nézetek**: xG-trend kártya, visszatérő edzés-fókusz, két
  meccs gyors összevetése. (#112, #117, #119)
- **Első lépések + demó**: üres könyvtárnál vezetett útmutató; a demó
  meccs forgatókönyv-epizódokkal minden réteget megmutat. (#129, #130)
- **Gyorsbillentyű-súgó** (?/F1) és élő-mód riasztások az új
  rétegekből. (#118, #131)

### Export és jelentés
- **Klip-export bővítés**: hetes/időkérés/csere/jegyzet-klipek, a
  jegyzet szövegével a fájlnévben. (#113, #122)
- **Meccs-csomag**: minden elemzés géppel olvasható JSON-ban +
  szöveges összefoglaló + jegyzetek. (#116, #122)
- **Jelentés**: xG-blokk, védekezés-blokk zóna-sávokkal, edzés-fókusz,
  kapus 7 m-es oszlop, fejléc-összkép. (#97, #102, #106, #115, #128,
  #131)

### Bemenet-jövőkép (bővítési alap)
- **TV-közvetítés elő-feldolgozása**: vágás-felismerő + totálkép-szűrő —
  a vágott közvetítés csak a használható szakaszokból elemezhető (a
  visszajátszás nem számol duplán gólt). A tévés-út első lépcsője. (#134,
  #135)
- **`docs/BROADCAST_AND_SENSORS.md`**: a teljes bemenet-jövőkép —
  telepített többkamerás + lidaros csarnok-rendszer ÉS a tévés-út
  lépcsői (auto-kalibráció, eredményjelző-OCR, élő stream). (#134)

## v0.1.17 és korábbi
A korábbi kiadások tartalmát a Releases oldal és a PR-történet őrzi:
alap-pipeline (YOLO+ByteTrack, homográfia, pásztázás-követés),
esemény-felismerés, taktika/felderítés, figura-tervező, mezszám-OCR,
könyvtár-mentés, telepítők (Windows/macOS).
