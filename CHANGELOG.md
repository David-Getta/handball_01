# Változásnapló (CHANGELOG)

A Sport Machine kiadásainak emberi nyelvű összefoglalója. A részletes
történet a squash-merge-elt PR-okban él; itt a lényeg, témák szerint.

## Kiadatlan — a v0.1.18 tartalma (a v0.1.17 óta, PR #57–#448)

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
- **Védekezési nyomás**: a labdás játékosra kilépő legközelebbi védő
  átlagos távolsága (szorosabb/lazább védekezés) — összefoglalóban,
  jelentésben, felderítésben, edzés-fókuszban. (#163, #164, #165)
- **Lövés-választás minősége**: átlagos xG lövésenként (nem csak az
  összeg) — csapat-mutató a jelentésben, a felderítésben és a
  lövéstérkép chipjén. (#166, #167, #168)
- **Kondíció-mutató**: első vs második félidő tempó-esése csapatonként
  (fáradás-jel a cserék időzítéséhez) — a /team-stats végponton, a
  csomag-exportban és a jelentés Csapat-mutatók táblájában. (#169,
  #170)
- **Kapus leggyengébb sarka**: zóna szerinti védés-hatékonyság — a
  jelentésben, a felderítési kulcsban ("ide lőjetek") és az
  összefoglalóban. (#174, #175)
- **Kapus-csere felismerés**: ki védett mikor (váltások időpontja),
  kapusonkénti külön kapott/védett mérleggel — az összefoglalóban és a
  jelentés kapus-táblája alatti jegyzetben. (#253, #254)
- **Ziccer-klipek**: kihagyott ziccerek (nagy xG, gól nélkül) és nagy
  védések (fogott ziccerek) egy-egy gombbal exportálhatók; a bravúr-
  védések száma az edzői összefoglaló kapus-sorába is bekerül.
  (#255, #256)
- **Ziccer-réteg mindenhol**: ziccer-mérleg a felderítésben (bravúr-
  kapus / kihagyós befejezés kulcsokkal), a meccsjelentés
  Helyzetminőség blokkjában (csapat-sor + lövőnkénti oszlop), és
  edzés-fókusz a kihagyott ziccerekből. (#257, #258, #259)
- **Kapus-indítás ív**: védés utáni felhozatal-sebesség (6 mp-en belül
  gyors) méréstől a felderítési kulcsig, jelentés-oszlopig és
  edzés-fókuszig; plusz az indítás tipikus célpontja ("őt vedd fel
  először"). (#260, #261, #262, #263, #274)
- **7 a 6 mérleg**: az üres kapura kapott gólok (az ára) és a 7 a 6-ban
  dobott gólok (a hozama) együtt — összefoglalóban, jelentésben,
  felderítési gyengeségben és edzés-fókuszban. (#264, #265, #268)
- **Játékos-profilok a felderítésben**: honnan lő a fő lövőjük
  (zóna-szokás), mikor fárad el (2. félidei tempó-esés), ki készíti
  elő a góljait (gól-tengely), ki a faluk kulcsa, ki dobja a
  heteseiket, ki fejezi be a kontráikat — mind több meccs közt
  pontosan összegzett számokból, klip-exporttal a fő lövőről.
  (#266, #267, #269, #270, #271, #273, #275, #276)
- **Kulcsemberek egy helyen**: közös réteg + tábla a jelentésben +
  kártya az appban — kinél dől el a meccs, a felderítési kulcsokkal
  azonos küszöbökkel. (#277, #278, #279)
- **Meccs-tempó**: támadás/perc címkével (gyors/közepes/lassú) az
  összefoglalóban és a jelentés fejléc-sávjában. (#280)
- **Fejlődés-követés bővítés**: bravúr-védés és gyors indítás
  meccsenkénti trendje (a nem mért időszak kimarad). (#272)
- **Poszt-becslés**: ki a beálló / szélső / átlövő / irányító a
  támadó-fázis mozgásképéből — Felállások szekció a jelentésben és az
  összefoglalóban, poszt-címkék a Kulcsemberekben és a terhelés-
  táblában, beálló- és szélső-függés kulcsok, gól-eloszlás posztok
  szerint, edzés-szabály a kimaradó szélsőkre, megbízhatósági jelzés.
  (#324–#332, #336, #340, #341, #342, #329, #330, #331)
- **A meccs története**: az összefoglaló és a jelentés folyó
  bekezdéssel nyit — eredmény, félidő, legnagyobb különbség,
  vezetés-váltások, fordulópont, a billenést hozó gól-sorozat oka és
  a meccs embere. (#338, #339, #349, #350)
- **Meccsterv-illesztés**: a saját és az ellenfél-profil keresztezése
  nyolc páros szabállyal ("az ő erősségük × a mi gyengeségünk") —
  végpont, kártya a felderítő képernyőn, Meccsterv szakasz a
  nyomtatható felderítő jelentésben. (#344–#348)
- **Jelentés-finomítások**: a Hétméteresek listája a dobót és a
  kimenetelt is mutatja; a Gól-idővonalon ott a gólszerző. (#351,
  #352)
- **Kapusonkénti GSAx — bejött-e a csere?**: kapuscserénél a két kapus
  a kapott lövések nehézségén át is összemérhető (hárított érték −
  kapott gól kapusonként); az edzői összefoglaló ki is mondja az
  ítéletet, a jelentés csere-jegyzete pedig számmal hozza. (#354,
  #355)
- **Hetes-szokás**: merre lövik a heteseiket (bal/közép/jobb a dobó
  szemszögéből) — kiszámítható dobónál a kapus konkrét utasítást kap
  ("induljon balra"); irány a jelentés-listában és az app csempéjén,
  hetes-mérleg sor a Csapat-mutatókban. (#357, #358, #359)
- **Játékos-lap**: minden játékos egyéni meccs-riportja kiosztható
  HTML-ben — játék-mérleg (gól/lövés, xG, ziccer, blokk, hetes,
  kiharcolások), fizikai mutatók és "Mire figyelj" személyes
  javaslatok; gomb a Statisztika fülön, jatekos_lapok/ mappa a
  csomagban, API-végpont. A kapus saját mérleget kap (védés%, GSAx,
  hetes-védés, indítás) kapus-javaslatokkal (forma-jel, leggyengébb
  zóna). (#395–#398, #400, #401)
- **Fejlődés-riport nyomtatva**: a két időszak trend-összevetése
  kiosztható HTML-ben (irány-jelekkel, összegzéssel) — letöltés-gomb
  a trend-képernyőn. (#402)
- **Meccs-főcímek a könyvtárban**: minden kártyán egymondatos
  történet ("Szoros Hazai-siker (28–26) — a meccs embere a 7.
  játékos") — a szezon görgetve is olvasható. (#403)
- **Szezon játékos-lap**: a játékos teljes szezonja egy nyomtatható
  oldalon (összesítő + meccsről meccsre tábla), letöltés-gombbal a
  játékos-fejlődés képernyőn. Kapus-mezszámnál védés- és GSAx-oszlop
  a lapon és a képernyőn is (színezett formagörbe). (#408, #409,
  #411, #412)
- **key_moments a gépi exportban**: a meccs gerince az
  elemzesek.json-ban is — a csomag minden rétege emberi ÉS gépi
  formában. (#413)
- **Támadás-szélesség**: szélesen vagy szűken támadnak-e — új réteg
  kulcsokkal, jelentés-sorral, csempével, összefoglaló-mondattal,
  csomag-réteggel és a 12. meccsterv-szabállyal (széles játék ×
  szél-gólok). (#446–#448)
- **Munkafolyamat-hidak**: kulcs-pillanatból jegyzet egy koppintással;
  meccsterv.txt a csomagban a visszavágóra; élő irány-tipp a
  hetes-jelzésben (csak a korábbi hetesekből); hetes-mérleg sor a
  könyvtár-összevetőben; közös irány-szótár. (#441–#445)
- **Hetes-irány kör bezárva**: a dobó a saját lapján látja az
  irány-képét és a kiszámíthatóság-figyelmeztetést, a kapus a kapott
  hetesek irányait, az edzésterv irány-váltogató sorozatot javasol
  (28. szabály); Meccsterv szakasz minden felderítő-exportban,
  FIGURÁK kártya az Összegzés fülön, "Gólcsend vége" kulcs-pillanat.
  (#434–#439)
- **Videó-dosszié és klip-rendszer**: a tematikus klip-csomagok egy
  olvasható menüben, Teljes videó-dosszié egy kattintásra; szabad
  lövő (fedezés-hiba) klipek; ismétlés-szűrés és a kimaradt jelenetek
  jelzése appon belül is. (#427–#431)
- **Meccsterv 11. szabály**: az ő működő figurájuk × a mi
  fedezés-hibáink ("a figura-felismerés nálatok életbiztosítás");
  mezszám-lefedettség sor a megbízhatósági önjelentésben.
  (#426, #432)
- **Figura-hatékonyság**: melyik begyakorolt támadás hozott gólt —
  csapatonként klaszterezett minták mérlege (támadás/lövés/gól),
  Figurák tábla a jelentésben, figura-klip export egy gombbal,
  Figura-frissítés edzés-szabály (27.), "van egy figurájuk, ami
  működik" felderítési kulcs és Fő figura csempe. (#419–#424)
- **Szezon-riport egy kattintásra**: a csapat szezonja automatikus
  időszak-bontású fejlődés-táblával + visszatérő edzés-fókuszokkal,
  csapat-választós gombbal a dashboardon. (#416, #417)
- **Élő vezetés-váltás jelzés**: az élő követés folyamában arany
  jelzés a fordulat pillanatában ("reagálj: időkérés vagy
  védekezés-váltás jöhet"). (#415)
- **A meccs gerince a jelentésben + ikonok**: a kulcs-pillanatok
  szekcióként a nyomtatható jelentésben (ötödik felület), az app
  kártyáján típus-ikonokkal és színekkel. (#405, #406)
- **A meccs gerince (kulcs-pillanatok)**: fordulópont, sorozatok,
  kiállítások, hetesek, kapuscserék és vezetés-váltások egy közös
  rétegben — kattintható kártya az appban (ugrás a videóban),
  olvasható txt a csomagban, API-végpont és egy gombos klip-csomag.
  (#385, #391–#393)
- **Jelentés-mélyítés**: FÉLIDŐ-jelölő a Gól-idővonalban a félidei
  állással; Gól/lövés és Gól−xG oszlop a Játékos-terhelésben;
  Leghosszabb gólcsend sor (mettől meddig); Fegyelmük narratíva-
  szakasz a felderítésben. (#387–#390)
- **Előny-kezelés**: időhúzás vezetve / kapkodás hátrányban (a
  támadás-hossz állás szerint) — kulcsok, jelentés-sor, csempe,
  összefoglaló-mondat, 10. meccsterv-szabály, csomag-réteg.
  (#381–#384)
- **Kulcs-pillanatok fájl**: időbélyeges visszanéző-lista a
  csomagban (fordulópont, sorozatok, kiállítások, hetesek,
  kapuscserék) + Hetes-dobóik irány-táblája a felderítő
  jelentésben. (#380, #385)
- **Szünet utáni kezdés**: ki üt először a 2. félidőben (az első 5
  perc mérlege) — felderítési kulcs mindkét irányban, csempe, a meccs
  történetének mondata, Szünet utáni protokoll edzés-fókusz (26.
  szabály) és csomag-réteg. (#374–#377)
- **xG-ítélet**: megérdemelt volt-e a győzelem a helyzetek alapján —
  közös ítélet-mondat az összefoglalóban és a jelentésben; 7 a 6
  ítélet (megérte-e a vállalás) az összefoglalóban. (#372, #373,
  #378)
- **Excel-kész játékos-CSV**: gól, lövés, xG, blokk és becsült poszt
  oszlopok a statisztika-exportban; kiállítás-számok a könyvtár-
  áttekintőben és a dashboard összevető táblájában. (#370, #371)
- **Fegyelem-réteg**: ki harcolja ki a kiállításokat és ki üli le őket
  (a hátrány alatt eltűnő track azonosítása) — felderítési kulcsok,
  "2 perc-hozó" Kulcsember-szerep, Fegyelem csempe, kiállítás-sor a
  jelentésben kiülőkkel, kiülők/kiharcolók az összefoglalóban,
  fegyelem-párbaj meccsterv-szabály, Kiállítás/meccs trend-mutató és
  Fegyelmezett védekezés edzés-fókusz (25. szabály).
  (#360–#368)
- **Visszarendeződés-idő**: labdavesztés után mikor áll fel a védelem
  — kulcsok, jelentés-sor, csempe és edzés-szabály. (#320–#323)
- **Támadás-eredet**: középkezdés / kidobás / labdaszerzés címkék
  gól-hozzárendeléssel — kulcs, narratíva, jelentés-tábla, csempe.
  (#316–#318)
- **Hetes-kiharcoló**: kit rántanak le — kulcs és Kulcsember-szerep.
  (#333, #334)
- **Lövés-választás és hidegvér**: átlag xG/lövés kulcsok, gól − xG
  többlet játékosonként, Ágyú és Hidegvérű befejező szerepek.
  (#307, #308, #312, #313, #298)
- **Csomag-bővítés**: edzesterv.txt + új rétegek az elemzesek.json-ban.
  (#319, #323, #327, #335, #337)
- **7 a 6 időzítés-jegyzet a jelentésben** (#314) és **kapus-xG
  csempék/sorok** (#309, #315, #305, #306).
- **Kapus-xG páros**: hárított xG (a nehéz védéseket díjazó mutató) és
  megmentett gólok (GSAx: kapott gól a helyzet-minőséghez mérve) —
  jelentés-oszlop és -sor, edzői mondat, felderítési erősség/gyengeség,
  trend, szezon-összkép és kapus-forma edzés-szabály.
  (#300–#306, #309, #310)
- **Kulcsemberek bővítés**: Gól-tengely, Ágyú (85+ km/h), Bravúr-kapus
  és Hidegvérű befejező szerepek; Kulcsemberek szekció az edzői
  összefoglalóban; szerep-tábla a nyomtatható felderítő jelentésben.
  (#291, #295, #297, #298, #299, #308)
- **7 a 6 időzítés + klipek**: mikor húzzák elő a lehozott kapust
  (hátrányban-minta kulccsal), és a szakaszok egy gombbal
  exportálhatók. (#282, #283)
- **Új klip-típusok**: fordulópont (a győzelmi esély billenése) és
  blokkolt lövések. (#284, #288)
- **Hidegvérű befejező és lövő-szokások a felderítésben**: gól − xG
  többlet kulccsal; tempó-profil (támadás/perc) kulcsokkal és
  csempével. (#286, #287, #296, #307)
- **Késő csere + rotáció**: elfáradt, le nem cserélt játékosok jelzése
  és rotáció-tervezés edzés-szabály. (#289, #290)
- **Meccs-tempó mélyítés**: félidőnkénti bontás, csapatonkénti
  Támadás/perc sor a jelentésben. (#292, #293)
- **Csomag-export bővítés**: 9 új réteg az elemzesek.json-ban. (#294)
- **Egy-tengelyű támadás edzés-szabály**: B-terv, ha a gólok zöme egy
  gólpasszoló → lövő párosból jön. (#285)
- **Labdaeladás-térkép**: hol veszik el a labdát (saját/közép/támadó
  harmad) — kontra-kulcs a felderítésben, edzés-fókusz és jelentés-sor.
  (#176, #177, #178, #179)
- **Passz-hálózat**: ki kinek adogat (párok, hubok) — a játékszervezés
  tengelye a "vágd el" felderítési kulccsal, narratívával, csempékkel.
  (#180, #181, #182)
- **Fordítás-felismerés**: a legnagyobb ledolgozott hátrány —
  összefoglalóban, jelentés-fejlécben, appban. (#183, #184)
- **Hajrá-elemzés (clutch)**: az utolsó 5 perc gólmérlege szoros
  állásnál — felderítési kulcsok ("ne hagyd a végjátékra" / "tartsd
  szorosan"), edzés-fókusz, kliens- és jelentés-megjelenítés. (#185,
  #186, #187, #189, #190)
- **Fejlődés-követés bővítés**: birtoklás, védekezési nyomás és elöl
  vesztett labdák a trend-összevetésben. (#188)
- **Lövés-sebesség**: km/h a labda-kinematikából — leggyorsabb lövés az
  összefoglalóban, sebesség-sorok a jelentésben, kliens-chip. (#191,
  #192, #193)
- **Gólcsend-elemzés**: a leghosszabb gól nélküli időszak — "ilyenkor
  kell ellépni" felderítési kulcs, összefoglaló és kliens-felirat.
  (#194, #195, #196)
- **Blokk-felismerés**: a mezőnyvédőn elakadó lövések — "aktív fal"
  erősség, "kerüld a falat" kulcs, edzés-fókusz, csempék. (#197, #198,
  #199, #200)
- **Passzív-veszély**: 35 mp fölé húzódó támadások aránya —
  figyelmeztetés az összefoglalóban, "maradj fegyelmezett" felderítési
  kulcs. (#201, #202)
- **Valódi félidő-határ + félidei állás**: a kondíció-mutató a felismert
  félidei szünetet használja; a félidei eredmény az összefoglalóban, a
  jelentés-fejlécben és az appban; félidő-minta felderítési kulcs
  ("a 2. félidőben feljavulnak/elfogynak"), narratíva-szekció, kliens-
  csempe és 2. félidei visszaesés edzés-fókusz. (#204–#211)
- **Lövés-erő a felderítésben**: átlag/csúcs km/h meccsek közt
  összegezve — "nagy erejű lövők" erősség, csempék. (#214, #215)
- **Nyomás alatti befejezés**: szabad vs fedezett lövések gólaránya —
  "elég a fegyelmezett fal" / "hidegvérű lövők" felderítési jelzések.
  (#216)
- **Játékos-fáradás**: első vs második félidei tempó játékosonként —
  összefoglaló-mondat, jelentés-oszlop, kliens-buborék; a csere-
  döntések nyers adata. (#217, #218, #219)
- **Támadás-oldal**: melyik szárnyra épül a játék (irány-normalizált
  bal/közép/jobb) — "told oda a falat" kulcs, narratíva, csempék.
  (#220, #221)
- **Válasz-gólok**: milyen gyorsan felel a csapat a kapott gólra —
  "stabil fejben" / "megtorpannak" jelzések, felderítési kulcsok és
  "Újraindulás" edzés-fókusz. (#223, #228)
- **Réteg-megbízhatóság**: mely elemzésekhez van elég minta ezen a
  meccsen, magyar indoklással — /quality mező és kliens-lista.
  (#224, #225)
- **Forma elleni hatékonyság**: melyik védekezési fal fogja meg az
  ellenfelet — "ellenük 6-0-ban állj fel" kulcs, narratíva, csempék és
  fal elleni figura edzés-fókusz. (#226, #227, #228)
- **Meccs-esély görbe + fordulópont**: P(hazai győzelem) a gólok mentén
  magyarázható modellel; a legnagyobb esély-ugrás a fordulópont —
  összefoglaló-mondat, jelentés-fejléc, kliens esély-sáv. (#243, #244,
  #245)
- **Támadás-hossz vs eredményesség**: rövid/közepes/hosszú támadások
  gólaránya — "kivárható őket" felderítési kulcs, narratíva, csempék és
  "Befejezés időkorláttal" edzés-fókusz. (#246, #247, #248)
- **Trend + szezon bővítés**: blokk/meccs a fejlődés-követésben;
  blokkok, leggyorsabb lövés a szezon-összevetésben; zóna-védés%
  oszlop a kapus-táblában; szimulátor félidei szünet opció. (#242,
  #249, #250, #251)

### Új bemenetek felé (útiterv + alapok)
- **TV-közvetítés előfeldolgozás**: vágás-felismerés (szín-hisztogram)
  és totál/premier-plán osztályozás (él-energia szórása) — a használható
  totálképes szakaszok kiszűrésére; /broadcast/segments végpont és
  kliens-gomb. Alap a jövőbeli élő-elemzéshez. (#134, #135)
- **Bemenet-roadmap**: a telepített több-kamerás + lidar arénarendszer és
  a közvetítés-elemzés útiterve dokumentálva (docs/BROADCAST_AND_SENSORS).
  Az elemzési rétegek méteres pozíciókon dolgoznak → szenzor-függetlenek,
  csak a bemenet cserélődik. (#134)
- **Pályavonal-felismerés (tévés út)**: fehér vonalak tiszta numpy
  Hough-transzformációval, sarok-jelöltek, kalibrációs négyszög-javaslat
  — /broadcast/lines végpont és a közvetítés-ellenőrzés kiegészítése.
  A vágásonkénti auto-kalibráció minden felvétel nélkül építhető része
  kész. (#230, #231, #232, #233)
- **Nézet-fúzió (arénarendszer)**: több kamera pozíció-folyamának
  egyesítése a közös méter-térben — pozíció-átlag, takarás-kitöltés,
  folytonos fúziós trackek; órajel-eltolás becslése a labda-pályából;
  POST /matches/fuse végpont + "Nézet-egyesítés" gomb a könyvtárban;
  fúziós nyereség-mutató. Két sima kamerával már ma kipróbálható.
  (#234, #235, #236, #237, #239)
- **Lidar-előkészítés**: pontfelhő-klaszterezés játékos-jelöltekké és a
  kamerás pozíciók lidar-ra igazítása (kamera = azonosság, lidar =
  geometria). (#240)

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
