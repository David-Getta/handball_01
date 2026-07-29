# Változásnapló (CHANGELOG)

A Sport Machine kiadásainak emberi nyelvű összefoglalója. A részletes
történet a squash-merge-elt PR-okban él; itt a lényeg, témák szerint.

## Kiadatlan (a v0.1.25 óta)

- **Szélső-befejezés oldalanként**: MELYIK szélsőjük veszélyes. A
  szélső-befejezés a két szélt együtt méri — ez szétbontja: a
  szélső-sávos lövéseket a támadó bal keze felőli és a másik oldalra
  osztjuk, és oldalanként számolunk gólarányt (oldalanként 3+ lövés,
  25 százalékpontos eltérésnél). A jól befejező szélső ellen időben ki
  kell futni és zárni a szöget (a kapus a rövid sarkot veszi), a
  gyengére viszont rá lehet engedni a lövést — ott a befelé segítés
  többet ér. Egy réteg, sok felület: `wing_finishing_by_side` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (oldalankénti lövés/gól darabszámok + edzői kulcs + csempe), 116.
  meccsterv-szabály (az ő gyenge szélsőjük × a ti réses falatok), 137.
  edzés-szabály (szélső-befejezés éles szögből: három megoldás
  váltogatva, mindig befelé lépve).
- **Beálló-oldal**: MELYIK OLDALON dolgozik a beállójuk. A
  beálló-terhelés azt mondja meg, mennyit játszanak rajta, a
  beálló-kiszolgálás azt, kin keresztül — ez azt, hol: a becsült
  beálló helyét kockánként bal / közép / jobb sávba soroljuk (a
  támadó bal keze felőli oldal a "bal", mint az oldal-részrehajlásnál;
  a sáv-küszöb a beálló szűk mozgásteréhez igazítva 1,5 m). Ha a
  kockák több mint felében ugyanott áll be, az adott középső-oldalsó
  védőpárnak kell rá készülnie — ott az átadás-fegyelem és a testes
  fogadás, a másik oldalon szűkíthető a segítés. Egy réteg, sok
  felület: `pivot_side` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (sávonkénti kocka-darabszámok +
  edzői kulcs + csempe), 115. meccsterv-szabály (az ő beállójuk oldala
  × a ti átjárható védő-oldalatok), 136. edzés-szabály (oldalváltó
  beállózás: minden második támadásban átvált, a falon belül átvonulva).
- **Fal-csúszás késése**: MILYEN GYORSAN igazodik a faluk az
  oldalváltáshoz. Az oldalváltás a támadó oldalról méri, milyen
  gyakran viszik át a labdát — ez a védő oldali válasz: felállt
  védekezésben a labda oldalirányú helyét vetjük össze a fal
  y-súlypontjával több késleltetéssel, és azt vesszük a késésüknek,
  amelynél a kettő a legjobban fedi egymást (200+ védekezett kocka;
  0,6 mp felett lassú, 0,2 mp alatt gyors). Lassú fal ellen az
  oldalváltás a fegyver — két-három átjátszás után a túloldalon nyílik
  a rés; gyors fal ellen az átjátszás csak a saját támadást fárasztja,
  ott a betörés és a beállós játék a válasz. Egy réteg, sok felület:
  `defensive_shift_lag` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kocka- és késés-összegek + két
  edzői kulcs + csempe), 114. meccsterv-szabály (az ő lassan csúszó
  faluk × a ti oldalváltásaitok), 135. edzés-szabály (eltolás
  oldalváltásra: a labda érkezése előtt a helyén a fal).
- **Passz-sebesség**: ÉLES vagy LÁGY a labdajáratásuk. A passz-hossz
  azt mondja meg, mekkora távra passzolnak, a passz-tempó azt, milyen
  sűrűn — ez azt, milyen keményen: a passzoló döntés-pillanata és a
  fogadó átvétele közti repülési időből és távolságból számolt
  sebesség (10+ mért passztól; 50% felett éles, 20% alatt lágy). Az
  éles passz ellen a passz-vonalba nyúlás kockázatos — testtel kell
  zárni és a fogadót megfogni; a lágy labdajáratásba bele lehet érni,
  és az elfogott passz azonnali kontrát ér. Egy réteg, sok felület:
  `pass_speed` motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (passz-darab, sebesség-összeg és éles passzok +
  két edzői kulcs + csempe), 113. meccsterv-szabály (az ő lágy
  labdajáratásuk × a ti labdaszerzéseitek), 134. edzés-szabály (feszes
  passz: mellkasra menő, egy érintéses passzgyakorlat védővel).
- **Beálló-kiszolgálók**: KI adja be a labdát a beállónak. A
  beálló-terhelés azt mondja meg, a támadásaik mekkora része megy át a
  beállón — ez azt, kin keresztül: minden passzt számolunk, amelynek a
  fogadója a becsült beálló (4+ beadástól, 50%-os vezető
  kiszolgálónál, holtverseny nélkül). Ha egy ember adja a beadások
  felét, őt kell zárni: rá kell lépni a beálló-vonalba, és az ő
  oldalán indítani a kettőzést, mert nélküle a beállójuk kiesik a
  játékból. Egy réteg, sok felület: `pivot_feeders` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (játékosonkénti beadás-darabszámok + edzői kulcs + csempe), 112.
  meccsterv-szabály (az ő egyszemélyes beálló-kiszolgálásuk × a ti
  beállós védekezésetek), 133. edzés-szabály (beálló-kiszolgálás több
  kézből: a beálló egymás után kétszer nem kaphatja ugyanattól).
- **Hetes-okozó védők**: KINÉL szakad meg a védekezés hetessel. A
  hetes-kiharcolók a támadó oldalról nézik, kit rántanak le — ez a
  védő oldali párja: a hetes-jel előtt a kiharcolóhoz legközelebb álló
  mezőnyvédő kapja a jóváírást (2+ esettől, mert egy eset még nem
  minta). Aki két-három hetest is okoz, annál kézzel áll meg a
  betörés: ellene betörést és beugrást kell indítani, mert vagy
  áthaladtok, vagy hetest ér. Egy réteg, sok felület:
  `seven_meter_conceders` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (védőnkénti darabszámok mezszámmal +
  edzői kulcs + csempe), 111. meccsterv-szabály (az ő hetes-okozó
  védőjük × a ti hetes-kiharcolóitok), 132. edzés-szabály (lábbal
  védekezés: 1-1 hátrakulcsolt kézzel).
- **Támadás-mélység**: MILYEN MESSZE állnak a kaputól felállt
  támadásban. A támadás-szélesség az oldalirányú terjedelmet méri — ez
  a mélységet: birtoklású kockánként a támadók átlagos kapu-távolsága
  (100+ mért kocka; 9,5 m alatt vonalra tapadó, 12 m felett mély).
  Aki a 9 m-es vonalra tapad, betörésre és beugrásra játszik — ellene
  a fal ne lépjen ki, a segítő-csúszás és a testes fogadás a válasz;
  aki mélyen áll, annak idő kell a lövés-előkészítéshez — ellene ki
  kell lépni a lövő-vonalba. Egy réteg, sok felület: `attack_depth`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (kocka- és távolság-összegek + két edzői kulcs +
  csempe), 110. meccsterv-szabály (az ő mély támadásuk × a ti felfutó
  falatok), 131. edzés-szabály (vonalra lépő támadás: 9 m-en belülről
  befejezni).
- **Szélső-bevonás**: ELJUT-E a labda a szélre a támadásaikban. A
  szélső-befejezés azt méri, mennyire eredményes a szélső, ha lő — ez
  azt, hogy egyáltalán megkapja-e a labdát: támadásonként nézzük,
  járt-e a labda a szél-sávban (8+ támadástól; 60% felett széthúzzák,
  30% alatt közép-központúak). Aki széthúzza a támadást, ott a
  szélső-védekezés és az időben kifutás a feladat; aki
  közép-központú, ott a szélső-védők beljebb segíthetnek — tömör
  fallal a beállót és az átlövést kell elzárni. Egy réteg, sok
  felület: `wing_involvement` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (támadás- és szélre-jutás
  darabszámok + két edzői kulcs + csempe), 109. meccsterv-szabály (az
  ő közép-központú támadásuk × a ti tömör falatok), 130.
  edzés-szabály (szélesség-tartás: a befejezés előtt mindkét szélsőt
  meg kell járnia a labdának).
- **Védekezési mélység állás szerint**: ELŐNYBEN vagy HÁTRÁNYBAN
  jönnek-e előre. A vonal-magasság a meccs egészére adja meg a fal
  helyét, a támadás-hossz állás szerint pedig a támadó oldal
  állás-függő viselkedését — ez a kettő kereszteződése: védekező
  kockánként az állás (vezet / hátrányban / döntetlen) szerint
  átlagolt fal-magasság (állásonként 100+ mért kocka, 0,8 m-es rés).
  Ez mondja meg, mikor jön a nyomásuk: aki hátrányban előrelép, annál
  kapott gól után jön a letámadás — arra kell kész kihozatal; aki
  vezetve is fent marad, ellene letámadás-álló kihozatal kell. Egy
  réteg, sok felület: `line_height_by_score` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (állásonkénti kocka- és
  magasság-összegek + két edzői kulcs + csempe), 108.
  meccsterv-szabály (az ő hátrányban feljebb lépő faluk × a ti gyors
  középkezdésetek), 129. edzés-szabály (vezetés-védés azonos fallal).
- **Támadás-kimenetel**: MIVEL zárulnak a támadásaik. A
  támadás-hatékonyság azt mondja meg, mennyi lesz gól — ez azt, hogy
  eljutnak-e egyáltalán a befejezésig: minden támadás-szakaszt
  lövéssel, hetessel, eladással vagy egyébbel zárunk le (8+
  támadástól). A kettő közti rés a lényeg: egy 30%-os gólarány mást
  jelent 90%-os és 60%-os lövés-aránnyal. Ha a támadásaik negyede
  eladással hal el, a kettőzés és a magas nyomás azonnal termel; ha
  szinte mindent befejeznek (85% felett), a pressz kockázat — ott a
  blokk és a lövés minőségének rontása a válasz. Egy réteg, sok
  felület: `attack_outcomes` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kimenetelenkénti darabszámok + két
  edzői kulcs + csempe), 107. meccsterv-szabály (az ő lövés nélkül
  elhaló támadásaik × a ti kettőzésetek), 128. edzés-szabály
  (befejezésig vitt támadás: minden támadást lövéssel kell zárni).
- **Kapus-védés posztonként**: MELYIK SZÖGBŐL sebezhető a kapusuk. A
  távolság-sávos réteg (`gk_save_ranges`) azt mondja meg, milyen
  messziről — ez azt, milyen szögből: a kapura tartó lövéseket a lövő
  posztjához kötjük, és posztonként számolunk védési arányt (8+ lövés,
  posztonként 4+, 15 százalékpont elmaradás a csapat-átlagtól). A
  szélső lövése közeli, de éles szögű; az átlövés távoli, de szemből
  jön — a két kép más. Edzőileg: a leggyengébb posztra kell szervezni
  a befejezést, és onnan bátran lőni rá. Egy réteg, sok felület:
  `gk_saves_by_role` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (posztonkénti lövés/védés
  darabszámok + edzői kulcs + csempe), 106. meccsterv-szabály (az ő
  kapusuk gyenge szöge × a ti onnan szerzett góljaitok), 127.
  edzés-szabály (szög-védés: az adott posztról sorozatlövés
  kilépéssel és sarok-zárással).
- **Hiba-sorozatok**: EGYMÁS UTÁN jönnek-e az eladások. Az
  eladás-időzítés azt mondja meg, a birtokláson belül mikor adják el a
  labdát — ez azt, hogy a hibák a meccsen belül szóródnak-e, vagy
  sorozatban érkeznek (két eladás egy sorozat, ha egy percen belül
  követi egymást; 5+ eladástól, 50%-os küszöbbel). Ha sorozatban
  hibáznak, egy eladás után kapkodnak: az első labdaszerzés után
  azonnal újra rá kell menni, mert ott jön a második ajándék. Ha
  szórtak a hibák (20% alatt), a pressz fölösleges kockázat. Egy
  réteg, sok felület: `turnover_clusters` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (két edzői kulcs +
  csempe; az eladások, a sorozatban lévők és a sorozatok darabszáma
  tárolva), 105. meccsterv-szabály (az ő hiba-sorozataik × a ti gyors
  kontráitok), 126. edzés-szabály (hiba utáni rendezés: eladás után
  kötött következő támadás).
- **Kapott gólok posztonként**: MELYIK POSZT ELLEN szivárognak. A
  poszt szerinti gólmegoszlás védő-oldali tükre: a gólt a lövő
  posztjához kötjük, de a védekező csapat oldalán tartjuk nyilván (5+
  kapott gól, 45%-os vezető poszt, holtverseny nélkül). Ez mondja meg,
  hova kell játszani ellenük: szélső-gólok ellen a szélsőket etetni,
  beállós gólok ellen a beállós játékot futtatni, átlövő-gólok ellen a
  távoli befejezésre építeni, irányító-gólok ellen az irányítónak
  szervezni a lövő-helyzeteket. Egy réteg, sok felület:
  `conceded_by_role` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (posztonkénti kapott gólok + edzői
  kulcs a poszthoz illő támadó utasítással + csempe), 104.
  meccsterv-szabály (az ő gyenge posztjuk × a ti ugyanonnan szerzett
  góljaitok), 125. edzés-szabály (poszt-védekezés: az adott poszt
  elleni 1-1 és segítő-csúszás gyakorlása).
- **Poszt szerinti gólmegoszlás**: MELYIK POSZTRÓL jönnek a góljaik.
  A poszt-becslés megmondja, ki milyen poszton játszik — ez a réteg a
  gólokat köti a lövő posztjához, vagyis nem a gólfelelősüket, hanem
  azt mutatja, melyik posztra épül a befejezésük (5+ poszthoz kötött
  gól, 45%-os vezető poszt, holtverseny nélkül). Ez rendezi a
  védekezési feladatokat: szélső-gólok ellen kifutás és szög-zárás,
  beállós gólok ellen elé állás, átlövő-gólok ellen előrelépés a
  lövő-vonalba, irányító-gólok ellen kettőzés a 9 m-en kívül. Egy
  réteg, sok felület: `goals_by_role` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (posztonkénti darabszámok
  + edzői kulcs a poszthoz illő utasítással + csempe), 103.
  meccsterv-szabály (az ő beállóra épülő befejezésük × a ti beállós
  védekezésetek), 124. edzés-szabály (befejezés több posztról: a
  vezető posztról csak minden harmadik befejezés jöhet).
- **Gólpassz-zónák**: HONNAN érkezik a gólpassz — edzői ítélettel. A
  zónázást a meglévő gólpassz-forrás (`assist_sources`) végzi, ez a
  réteg abból von le ítéletet: van-e EGY vonal, amiről a gólpasszaik
  fele jön (4+ gólpassztól, 50%-os vezető zónánál, holtverseny
  nélkül). Ez adja meg az elvágandó átadás-vonalat: a szélső–beálló
  tengelyt, a beálló kiszolgálását vagy az átlövők passz-sávját.
  Egy réteg, sok felület: `assist_zones` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (edzői kulcs a zónához
  illő védekezési utasítással + csempe; zónánkénti darabszámok, hogy
  meccsek közt pontosan összegződjön), 102. meccsterv-szabály (az ő
  átlövésből előkészített gólpasszaik × a ti blokkjaitok), 123.
  edzés-szabály (előkészítés két vonalról: a gólpassz nem jöhet
  kétszer egymás után ugyanarról a vonalról).
- **Támadás-indítók**: KI hozza fel a labdát. A támadás-eredet azt
  mondja meg, MIBŐL indul a támadás (középkezdés, kidobás,
  labdaszerzés) — ez azt, ki indítja: minden támadás-szakasz első
  labdabirtokosa (a kapus nélkül), vagyis akinél a labda átjön a
  felezővonalon. Ha egy ember hozza fel a támadások 40%-át, ő a
  kihozatali kulcs: rá kell menni a felhozatalnál (letámadás, az első
  átadás-vonal zárása), mert nélküle megakad a felállásuk; ha
  megoszlik (25% alatti csúcs), a letámadás nem fizet ki, ott a
  felállt védekezés a válasz. Egy réteg, sok felület:
  `attack_starters` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (két edzői kulcs + csempe;
  játékosonként az indítások száma tárolva, hogy a részarány meccsek
  közt pontosan visszaszámolható legyen), 101. meccsterv-szabály (az ő
  egyszemélyes kihozataluk × a ti elöl szerzett labdáitok), 122.
  edzés-szabály (kihozatal több kézbe: 4-2 elleni kihozatal három
  felváltva indító emberrel).
- **Időkérés-időzítés**: MIKOR kérnek időt. Az időkérés-mérleg azt
  mondja meg, MŰKÖDÖTT-E a megszakítás — ez azt, hol a küszöbük: hány
  kapott gól után nyúlnak a jelzőkorongért (2+ időkéréstől; 1,5 alatt
  "gyors fék", 2,5 felett "hagyják elszaladni"), és mennyit
  tartogatnak a hajrára (az utolsó 10 perc). Aki már az első-második
  kapott gólnál fékez, nem hagyja kifutni a sorozatot — ellene a gyors
  gólváltás a cél; aki hármat is elenged, ott a sorozat két-három
  támadásnyi ablakot ér. A hajrára tartogatott időkérés azt jelenti, a
  zárásuk mindig rendezett: a döntő támadásokat előre le kell
  beszélni. Egy réteg, sok felület: `timeout_timing` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (két edzői
  kulcs + csempe; az időkérések, az előttük álló kapott gólok és a
  hajrában kértek száma tárolva, hogy az átlag meccsek közt pontosan
  visszaszámolható legyen), 100. meccsterv-szabály (az ő késői fékük ×
  a ti gólsorozataitok), 121. edzés-szabály (sorozat-kezelés: a
  második kapott gól után időkérés, 20 másodperces forgatókönyvvel).
- **Páros-mérleg**: MELYIK KETTŐ megy jól EGYÜTT a pályán. A
  játékos-mérleg egy emberre nézi a gólkülönbséget — ez a párokra:
  minden együtt töltött kockát a két játékos párosához írunk, a rájuk
  eső gólokkal együtt (4+ közös perctől, 0,2 gól/perc eltérés a
  csapatátlagtól). Így látszik, mely kettős emeli a csapatot, és
  melyik páros együtt nem működik — attól még külön-külön jók
  lehetnek. Edzőileg ez az egység-építés adata: a jó párost egy
  blokkban kell tartani (együtt cserélni), a rosszat szét kell húzni;
  az ellenfél legjobb párosát pedig a cseréikkel és időkéréssel lehet
  szétszedni. Egy réteg, sok felület: `pair_plus_minus` motor, edzői
  összefoglaló (mezszámmal), /analyze + meccs-csomag,
  felderítés-profil (edzői kulcs + csempe; párosonként az együtt
  töltött kockák és a gólok tárolva, hogy a mérleg meccsek közt
  pontosan visszaszámolható legyen), 99. meccsterv-szabály (az ő
  legjobb párosuk × a ti időkéréseitek), 120. edzés-szabály
  (egység-építés: fix feladat-megosztás vagy külön blokk).
- **Csere-blokkok**: egyesével cserélnek, vagy egységekben. A
  csere-hatás azt méri, MI TÖRTÉNIK a csere után, a késő csere azt,
  kit felejtenek bent — ez a harmadik kérdés: HOGYAN cserélnek. Ha egy
  hullámban rendre két-három ember jön-megy, a csapat specialistákat
  mozgat (támadó és védekező egység); ha egyesével, akkor pihentet
  (4+ cserehullámtól, 40% blokkos arány a küszöb). Edzőileg: a blokkos
  csere ellen a gyors újraindítás a fegyver — csere közben egy ütemre
  rossz emberek vannak a pályán; egyesével cserélő csapatnál a célzott
  fárasztás működik. Egy réteg, sok felület: `substitution_blocks`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (edzői kulcs + csempe; a hullámok, a mozgatott
  játékosok és a 2+ fős hullámok száma tárolva, hogy a blokk-arány
  meccsek közt pontosan visszaszámolható legyen), 98.
  meccsterv-szabály (az ő blokkos cseréjük × a ti gyors
  újraindításotok), 119. edzés-szabály (csere-fegyelem: holt
  játékhelyzetben cserélni, 3 mp alatti hullám).
- **Lövőerő-esés**: marad-e erő a karban a második félidőre. A
  befejezés-esés azt mutatja, mennyi megy be, a lövő-erő azt, ki lő
  keményen — ez a kettő metszete időben: a mért lövés-sebességek
  félidőnkénti átlaga (félidőnként 4+ mért lövéstől, 6 km/h eltérés a
  küszöb). Ha az átlagsebesség érdemben esik, a hajrában a távoli lövés
  már nem fegyver (kidolgozott helyzet kell, a fal kintebb jöhet); ha
  tartja vagy nő, a bombázójuk a hajrában is élő veszély — a kapusnak
  korábban kell indulnia. Egy réteg, sok felület: `shot_power_fade`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (edzői kulcs + csempe; félidőnként a lövésszám és a
  sebesség-összeg tárolva, hogy a félidő-átlag meccsek közt pontosan
  visszaszámolható legyen), 97. meccsterv-szabály (az ő
  lövőerő-esésük × a ti mély falatok), 118. edzés-szabály (fáradt
  befejezés: lövőgyakorlat magas pulzuson, törzs- és vállerő).
- **Labdatartás-idő**: KI meddig tartja magánál a labdát. A passz-tempó
  és a támadás-ritmus csapatszinten mondja meg, pörög-e a játék — ez a
  névre szóló olvasata: minden labdás szakasz hosszát a birtokoshoz
  írjuk (az érintésnyi, 5 kockánál rövidebb birtoklás zaj), és nézzük,
  kinél áll meg a labda (5+ labdás szakasztól, 0,8 mp-cel a
  csapatátlag felett). Edzőileg két irányba szól: ellenfélnél a hosszan
  tartó labdás a kettőzés célpontja (nála van idő odaérni, és nála
  lassul a támadásuk), saját oldalon a gyorsabb továbbítás témája. Egy
  réteg, sok felület: `hold_time_players` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (edzői kulcs + csempe;
  játékosonként a labdás szakaszok és a bennük töltött kockák tárolva,
  hogy az átlagos tartás meccsek közt pontosan visszaszámolható
  legyen), 96. meccsterv-szabály (az ő labdatartójuk × a ti
  elöl-szerzéseitek), 117. edzés-szabály (két-érintéses játék,
  kényszerítő döntés a labdatartónak).
- **Védekezés-váltás**: egy rendszert játszanak, vagy váltogatnak. A
  leggyakoribb forma azt mondja meg, MIT játszanak, a forma szerinti
  hatékonyság azt, melyik fal fogja meg őket — ez a harmadik kérdés:
  MENNYIRE állandó a rendszerük. Támadásonként (a védekező oldal
  szemszögéből) a fal uralkodó címkéjét vesszük, és számoljuk, hányszor
  tér el az előző védekezett támadásétól (6+ mért támadástól; 30%
  váltás-arány felett "váltogatós", 80% fő forma felett "egy
  rendszer"). Edzőileg: aki egy rendszert játszik, arra egy figurasort
  kell építeni és végig azt húzni; aki váltogat, ott a felismerés a
  feladat — a kihozatalnál hangosan bemondani a formát, és két kész
  változattal érkezni. Egy réteg, sok felület: `formation_switching`
  motor, edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (edzői kulcs + csempe; formánként a védekezett támadások, a
  támadás-párok és a váltások száma tárolva, hogy a váltás-arány
  meccsek közt pontosan visszaszámolható legyen), 95.
  meccsterv-szabály (az ő váltogatásuk × a ti lerohanásaitok: a váltás
  csak felállt védekezésben él), 116. edzés-szabály (második
  védekezési változat betanítása, ha végig egy rendszert játszunk).

## v0.1.25 — kiadva (2026-07-26)

> Kiadás-jegyzet: huszonöt új elemzés-réteg — a kör vezérfonala az,
> hogy a csapat-szintű képek NÉVRE szólóvá váltak. Eddig azt tudtuk,
> honnan és mikor esnek a gólok; mostantól azt is, KI mögött: ki lő a
> csapatátlag felett (lövő-erő), ki lő mindig ugyanabba a sarokba
> (lövő-kapuoldal), kinek a pályán léte alatt megy a játék
> (játékos-mérleg), kinek az eladásait büntetik (drága eladók), és
> melyik védő előtt fejeznek be (célba vett védő). Mellé bejött az
> IDŐZÍTÉS rétege (elsütés-idő, gól-előkészítés hossza,
> középkezdés-tempó, hajrá-eladás, hajrá-lövésválasztás), az
> elzárás mindkét oldala (elzárás-használat és -védekezés), az
> emberelőny/-hátrány teljes képe (fölény-befejezés, hátrány-támadás,
> emberelőny-védekezés), a kettőzés és az ellen-press mint mérhető
> fegyver, valamint két új kapus-olvasat (indítás iránya, szabad
> lövés elleni védés). A meccsterv 94, az edzés-fókusz 115 szabálynál
> jár; a backend csomag 782 teszttel zöld.

### A v0.1.25 körei

- **Célba vett védő**: KIRE lőnek, és kinél lesz belőle gól. A szabad
  lövés és a fal lyukai (wall_gaps, breakthrough_lanes) a HELYET
  mondják meg, a labdaszerzők a védekezés motorját — ez a hiányzó
  harmadik kérdés: melyik védő előtt fejeznek be. Minden kapott
  lövésnél a lövőhöz legközelebbi mezőnyvédő (6 m-en belül; távolabb
  nincs gazdája, az szabad lövés) kapja a lövést és a gólt is, ha
  bement. Edzőileg két olvasat: akire a legtöbbet lőnek, azt keresi
  az ellenfél (őt kell segíteni, mögé a kapus szöge), akinél pedig a
  csapatátlagnál 15 százalékponttal magasabb a gólarány (4+ rá eső
  lövéstől), ott a fal tényleg puha. Egy réteg, sok felület:
  `targeted_defenders` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (edzői kulcs + csempe; védőnként a
  lövés- és gólszám tárolva, hogy a gólarány meccsek közt pontosan
  visszaszámolható legyen), 94. meccsterv-szabály (az ő gyenge védőjük
  × a ti elzárás-használatotok), 115. edzés-szabály (védő-segítés:
  szomszéd zárja a lövőszöget, a kapussal egyeztetett szög).
- **Játékos-mérleg (+/−)**: kinek a pályán léte alatt jobb a
  gólkülönbség — a rotáció-mélység azt mutatja, KI mennyit játszik,
  ez azt, hogy MI TÖRTÉNIK, amíg játszik: a pályán töltött ideje
  alatt szerzett és kapott gólok különbsége, percre vetítve, a
  csapat saját átlagához mérve (5+ perc játékidőtől, 0.15 gól/perc
  eltérésnél). A magas mérlegű játékos ellen kell a legerősebb
  védekezés, és őt kell fárasztani; a negatív mérleg nem ítélet,
  hanem kérdés: kivel és mikor játszik. Egy réteg, sok felület:
  `player_plus_minus` motor, edzői összefoglaló (mezszámmal),
  /analyze + meccs-csomag, felderítés-profil (edzői kulcs + csempe;
  a pályán töltött kockák és a gólok tárolva, hogy a mérleg meccsek
  közt pontosan visszaszámolható legyen), 93. meccsterv-szabály (az
  ő legjobb mérlegű játékosuk × a ti kettőzésetek), 114.
  edzés-szabály (szerep-tisztázás: kivel és milyen állásnál játszik).
- **Lövő-erő**: kinek a legkeményebb a lövése — a lövés-sebességek
  csapat-átlagot és egy leggyorsabb lövést adnak, ez lövőnkénti
  profil: ki lő rendre a csapatátlag felett (4+ mért lövésből, 8+
  km/h eltérésnél). A bombázó ellen a fal ne vakon blokkoljon,
  hanem zárja a szöget, a kapusnak pedig korábban kell indulnia;
  saját olvasatban tudni kell, kire lehet a hajrában bízni a távoli
  befejezést. Egy réteg, sok felület: `shooter_power` motor, edzői
  összefoglaló (mezszámmal), /analyze + meccs-csomag,
  felderítés-profil (edzői kulcs + csempe; a sebesség-összeg és a
  lövésszám tárolva, hogy az átlag meccsek közt pontosan
  visszaszámolható legyen), 92. meccsterv-szabály (az ő bombázójuk ×
  a ti aktív falatok), 113. edzés-szabály (elzárás-figura a
  lövőtávjára, fal-átterhelés, lövés-sorozat fáradtan).
- **Lövő-kapuoldal**: ki melyik sarokba lő — a kapu-sarok
  (goal_placement) csapat-szinten mondja meg, merre mennek a gólok,
  ez lövőnként: a kapus akkor tud készülni, ha NÉVRE szól a jelzés.
  Aki a góljainak 60%-át ugyanarra az oldalra lövi (4+ gólból),
  kiszámítható: a kapus arra a sarokra állhat rá, a fal a másikat
  zárja. Saját olvasatban neki a kapuoldal-váltás a gyakorlandó.
  Egy réteg, sok felület: `shooter_placement` motor, edzői
  összefoglaló (mezszámmal), /analyze + meccs-csomag,
  felderítés-profil (edzői kulcs + csempe, meccsek közti
  játékosonkénti és oldalankénti összegzés), 91. meccsterv-szabály
  (az ő kiszámítható lövőjük × a ti kapusotok formája), 112.
  edzés-szabály (célzott lövés-sorozat a gyengébb oldalra,
  vezényszóra váltott sarok, lövőcsel a kapus mozdulatára).
- **Szélső-védekezés**: bírja-e a fal a szélső lövéseket — a
  szélső-befejezés a TÁMADÓ oldalról nézi, ki mennyire eredményes a
  szélről; ez a védő oldali tükre: a kapott lövéseket a lövő helye
  alapján szélső (a hosszanti középvonaltól 6,5 m-en túli) és
  középső sávra bontjuk, és a gólarányukat hasonlítjuk (sávonként
  5+ lövésből, 15+ százalékpont eltérésnél). Ha a szélről érkező
  lövések érdemben többször gólok, a szélső-őrzés és a kapus szöge
  a hiba: ellenük a szélső bevonása az első számú fegyver; ha a
  szél zsákutca, marad a középső áttörés és a beálló. Saját
  olvasatban a szélső védő kilépése és a kapus-védő egyeztetés az
  edzés-téma. Egy réteg, sok felület: `wing_defense` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (kétirányú kulcs + csempe), 90. meccsterv-szabály (az ő szélen
  nyitott faluk × a ti szélső-játékotok), 111. edzés-szabály
  (szélső védő kilépése szöget zárva, kapus-védő egyeztetés a rövid
  sarokra).
- **Drága eladók**: kinek az eladásai kerülnek gólba — a labdaeladók
  azt mutatják, KI veszti el a labdát, az eladás-büntetés azt, hogy
  a csapat eladásai MENNYIBE kerülnek; ez a kettő metszete:
  játékosonként hány eladásból lett fél percen belüli kapott gól
  (3+ eladás és 1+ gól a megnevezéshez). Akinek a hibái rendre gólt
  érnek, arra rá kell menni: őt kell kettőzni-zavarni a
  felhozatalnál, mert nála a legnagyobb a nyereség. Saját
  olvasatban vele kell a nyomás alatti labdakezelést gyakorolni.
  Egy réteg, sok felület: `costly_turnover_players` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (edzői
  kulcs + csempe, meccsek közti játékosonkénti összegzés), 89.
  meccsterv-szabály (az ő drága eladójuk × a ti magas szerzésetek),
  110. edzés-szabály (kettőzés elleni kiszabadulás, zavart átvétel,
  döntés-gyakorlat zárt sávnál).
- **Emberelőny-védekezés**: emberelőnyben is kapnak-e gólt — az
  emberelőny-hatékonyság azt méri, mit TÁMADNAK a kiállítás alatt,
  ez azt, mit VÉDEKEZNEK közben: egy emberrel többen is kaphatnak
  lerohanás-gólt, ha a befejezéseik után nem rendeződnek vissza. A
  perces kapott gól-ütemet hasonlítjuk az egyenlő létszámúhoz (90+
  mp előnyből, 0.2 gól/perc eltérésnél). Aki előnyben is szivárog,
  annál a kiállítás nem büntetés: hátrányban is vállalni kell a
  lerohanást ellene; aki fegyelmezett, azzal szemben hátrányban a
  labdatartás a reális cél. Saját olvasatban a befejezés utáni
  visszarendeződés az edzés-téma. Egy réteg, sok felület:
  `powerplay_defense` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kétirányú kulcs + csempe), 88.
  meccsterv-szabály (az ő szivárgó emberelőny-védekezésük × a ti
  lerohanásotok), 109. edzés-szabály (6-5 elleni támadás hazasprint-
  szabállyal, kijelölt biztosító a lövés pillanatában).
- **Kapus szabad lövés ellen**: a fal segítsége nélkül is véd-e a
  kapus — a védés-sávok a TÁVOLSÁG szerint bontanak, ez a
  FEDEZETTSÉG szerint: a kapura tartó lövéseket aszerint válogatjuk
  szét, hogy volt-e védő a lövőn (a védekezés-elemzés "szabad lövés"
  sugarával; sávonként 5+ lövésből, 15+ százalékpont eltérésnél).
  Akinek a kapusa csak a fal mögött véd, azt tiszta lövésekkel kell
  terhelni: elzárás után zavartalan átlövés; aki szabadon is fog,
  annál a távoli lövés ajándék — kidolgozott, közeli helyzet kell.
  Saját olvasatban a szabad lövés elleni kapusmunka és a fal-kapus
  egyeztetés az edzés-téma. Egy réteg, sok felület:
  `gk_free_shot_saves` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kétirányú kulcs + csempe), 87.
  meccsterv-szabály (az ő falfüggő kapusuk × a ti elzárásos
  játékotok), 108. edzés-szabály (zavartalan átlövés-sorozatok,
  helyezkedés-korrekció, fal-kapus oldalmegosztás).
- **Kettőzés**: rálép-e a második védő is a labdásra — a védekezési
  nyomás a LEGKÖZELEBBI védő távolságát méri, ez azt, hogy jön-e
  MÁSODIK: a labdás kockáin számoljuk, hányban van legalább két
  ellenfél 2,5 m-en belül (250+ labdás-kockából, 30% felett
  "kettőz", 10% alatt "1v1-et hagy"), és hány eladás lesz belőle 2
  másodpercen belül. A kettőző védekezés ellen egy érintéssel kell
  játszani (gyors labdaeladás az üres oldalra); aki nem kettőz,
  1v1-et hagy — a legjobb áttörőt kell rá küldeni. Saját olvasatban
  a kettőzés-mechanizmus és a mögötte lévő átvétel-csúszás az
  edzés-téma. Egy réteg, sok felület: `double_teams` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (kétirányú kulcs + csempe), 86. meccsterv-szabály (az ő
  kettőzésük × a ti gyors passzjátékotok), 107. edzés-szabály
  (kettőzés-jelre rálépés, átvétel-csúszás a beállóra).
- **Kapus-indítás iránya**: melyik oldalra nyit a kapus — az indítás
  hossza azt mondja meg, milyen messzire indít, a biztonsága azt,
  hogy elcsíphető-e; ez azt, hogy MERRE: a fogadó a pálya bal vagy
  jobb oldalán van-e (6+ indításból, 65% felett egyoldalú). Az
  egyoldalú kapus kiszámítható: arra az oldalra kell előre
  elindulni, a fogadó szélsőt letámadva a lerohanásuk már a
  kidobásnál megfogható. Saját olvasatban az indítás-irány
  variálása az edzés-téma. Egy réteg, sok felület: `gk_outlet_side`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (edzői kulcs + csempe), 85. meccsterv-szabály
  (az ő egyoldalú kapus-indításuk × a ti magas szerzésetek), 106.
  edzés-szabály (kidobás vezényszóra váltott irányba, letámadás
  elleni kihozatal).
- **Hajrá-eladás**: nyomás alatt megőrzik-e a labdát — a
  hajrá-lövésválasztás azt méri, milyen HELYZETEKBŐL lőnek a végén,
  ez azt, hogy egyáltalán eljutnak-e a lövésig: az utolsó 5 perc és
  az azt megelőző idő eladás/perc ütemét hasonlítjuk össze (5+ korai
  eladásból, 0.3 eladás/perc emelkedésnél "hajrá-hibázó"). Akinél a
  hajrában megugrik az eladás, az a döntéseiben esik szét: ellene a
  végén présbe kell tenni a labdavivőt (magasabb védekezés, kettőzés
  a felhozatalnál) és minden szerzés után futni; aki hidegvérű,
  annál a hibára várni hiba. Saját olvasatban a fix hajrá-felállás
  és a nyomás alatti döntés az edzés-téma. Egy réteg, sok felület:
  `clutch_turnovers` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kétirányú kulcs + csempe), 84.
  meccsterv-szabály (az ő hajrá-eladásaik × a ti átmenet-
  támadásotok), 105. edzés-szabály (fix hajrá-felállás, döntés-játék
  élő állással és fogyó idővel).
- **Hátrány-támadás**: mit támadnak a kiállítás alatt — az
  emberelőny-hatékonyság a kiállítás nyertes oldalát nézi (a
  hátrányban leadott lövéseket kifejezetten kihagyja), ez a hiányzó
  fele: a kiállított csapat maga mennyit támad egy emberrel
  kevesebben. A hátrányban töltött percre vetített gól-ütemet
  hasonlítjuk az egyenlő létszámúhoz (90+ mp hátrányból, 0.15
  gól/perc esésnél "megbénul"). Aki hátrányban is gólt szerez,
  kihúzza a két percet: ellene az emberelőnyt türelmesen, kockázatos
  lövés nélkül kell végigjátszani; aki megbénul, annál minden
  kiállítás azonnali gólkülönbség. Saját olvasatban a hátrányos
  labdatartás az edzés-téma. Egy réteg, sok felület:
  `shorthanded_attack` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kétirányú kulcs + csempe), 83.
  meccsterv-szabály (az ő megbénuló hátrány-támadásuk × a ti
  emberelőny-hatékonyságotok), 104. edzés-szabály (5-6 elleni
  labdatartás, ötös figura beállóval, hátrányban vállalt lerohanás).
- **Fölény-befejezés**: létszámfölényben vagy felállt fal ellen
  szereznek-e gólt — minden lövésnél megszámoljuk, hány támadó és
  hány védő van a támadott térfélen, és ha több a támadó,
  "fölényben" leadott lövésnek vesszük (sávonként 5+ lövésből, 15+
  százalékpont gólarány-eltérésnél ítélünk). Aki csak fölényben
  eredményes, azt vissza kell kényszeríteni a felállt támadásba: a
  visszarendeződés-sprint ér ellene a legtöbbet; aki a falat is töri,
  ellene a puszta hazaérés kevés — nyomás és szoros emberfogás kell.
  Saját olvasatban a felállt támadás figura-készlete az edzés-téma.
  Egy réteg, sok felület: `overload_finishing` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (kétirányú
  kulcs + csempe), 82. meccsterv-szabály (az ő fölény-függésük × a ti
  gyors visszarendeződésetek), 103. edzés-szabály (6-0 elleni
  figura-sor, 1v1-áttörés, lerohanás-tiltásos felállt támadás).
- **Ellen-press**: rátámadnak-e az eladott labdára — az
  eladás-büntetés azt méri, mennyibe KERÜL az eladás, a
  visszarendeződés-idő azt, milyen gyorsan érnek haza; ez a kettő
  közti pillanatot: az eladás utáni 6 másodpercben visszakerül-e
  hozzájuk a labda (8+ eladásból, 35% felett "visszatámad", 15%
  alatt "beletörődik"). Aki azonnal visszatámad, annál a szerzés
  utáni ELSŐ passznak kell tisztának lennie — nem cselezni a saját
  térfélen; aki beletörődik, annál minden labdaszerzés ingyen
  lerohanás. Saját olvasatban az eladás-jelre induló átmenet-játék
  az edzés-téma. Egy réteg, sok felület: `counter_press` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (kétirányú kulcs + csempe), 81. meccsterv-szabály (az ő beletörődő
  ellen-pressük × a ti lerohanásotok), 102. edzés-szabály
  (eladás-jelre induló rátámadás, 3 mp-es visszaszerzési szabály).
- **Hajrá-lövésválasztás**: milyen helyzetekből lőnek a meccs végén —
  a hajrá-teljesítmény a hajrá GÓLJAIT nézi, ez azt, hogy milyen
  HELYZETEKBŐL születnek: az utolsó 5 perc és az azt megelőző idő
  átlagos xG/lövés értékét hasonlítjuk össze (fázisonként 5+
  lövésből, 0.05 xG a küszöb). Aki a hajrában érdemben rosszabb
  helyzetekből lő, az nyomás alatt elkapkodja a befejezést: ellene a
  végén elég tartani a falat és nem hibázni, ők maguktól bevállalják
  a rossz lövéseket; aki javul, az a végén is kidolgozza a
  helyzeteket — ellene a hajrában sem lazulhat a fal. Saját
  olvasatban a hajrá-figurák és a fáradt-állapotú befejezés az
  edzés-téma. Egy réteg, sok felület: `clutch_shot_quality` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (kétirányú kulcs + csempe), 80. meccsterv-szabály (az ő
  hajrá-elkapkodásuk × a ti erős hajrátok), 101. edzés-szabály
  (hajrá-figurák, fáradtan is működő befejezés, türelem-szabály a
  kisjátékban).
- **Passz-kockázat**: a hosszú passzok eladás-aránya a rövidekhez
  képest — minden labda-továbbítási kísérletet (sikeres passz vagy
  eladás) a kiinduló és a megszerző játékos távolsága alapján hosszú
  (10 m+) és rövid sávra bontunk (sávonként 8+ kísérletből, 15+
  százalékpont a küszöb). Akinek a hosszú passzai érdemben többször
  vesznek el, annál a hosszú passzsávok lezárása a terv: letámadás
  és sávba állás; aki biztos kezű, ellene a passzsáv-vadászat nem
  fizet. Saját olvasatban a hosszú passz technikája az edzés-téma.
  Egy réteg, sok felület: `pass_risk` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (kétirányú kulcs +
  csempe), 79. meccsterv-szabály (az ő kockázatos hosszú passzaik ×
  a ti magas szerzésetek), 100. edzés-szabály (feszes hosszú passz
  technika, döntés-játék zárt sávnál).
- **Elzárás-védekezés**: bírja-e a fal az ellenfél elzárásait — az
  elzárás-használat védő-oldali tükre: ott az látszik, ki mennyit
  játszik elzárással, itt az, ki mennyire bírja ellene. Ha az
  elzárásos lövésekből 15+ százalékponttal többször esik gól, mint
  az elzárás nélküliekből (6+ elzárásos lövésből), a
  váltás-kommunikáció a gyenge pont: minden figurát zárral kell
  zárni ellenük; ha kevesebbszer, az elzárás zsákutca — tiszta
  1v1-et kell keresni. Egy réteg, sok felület: `screen_defense`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (kétirányú kulcs + csempe), 78.
  meccsterv-szabály (az ő gyenge elzárás-váltásuk × a ti
  elzárás-játékotok), 99. edzés-szabály (hangos váltás, átcsúszás a
  zár elé, zár-leolvasás).
- **Elzárás-használat**: elzárásból lőnek, vagy tisztán, 1v1-ből —
  lövésenként megnézzük, hogy a lövő őrzője mellett (2 m-en belül)
  áll-e támadó társ elzárásban (8+ őrzött lövésből; 40%+ =
  elzárásos, 10% alatt = elzárás nélküli). Az elzárásos csapat ellen
  a váltás-kommunikáció a meccs — hangos váltás vagy átcsúszás a zár
  alatt; az elzárás nélkül lövő csapat lövője magára van hagyva: a
  kilépés és a blokk ellene szinte ingyen van. Saját olvasatban az
  elzárás-játék hiánya edzés-téma. Egy réteg, sok felület:
  `screen_usage` motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (kétirányú kulcs + csempe), 77.
  meccsterv-szabály (az ő elzárás nélküli lövéseik × a ti
  blokk-falatok), 98. edzés-szabály (beállós elzárás-sor,
  átlövő-kereszt, leolvasás váltásnál).
- **Oldalváltás**: széthúzzák-e a falat gyors keresztpasszokkal — a
  támadó térfélen adott passzok közül a 10 m+ oldalirányú
  elmozdulásúak aránya (30+ passzból; 12%+ = oldalváltó, 3% alatt =
  egy-oldalas). Az oldalváltó ellen kompakt eltolás kell — a váltás
  alatt zárt sávok; az egy-oldalas ellen a fal bátran eltolható a
  kedvenc oldalukra, a túloldali szélsőjük éhen marad; saját
  olvasatban a keresztjáték hiánya edzés-téma. Egy réteg, sok
  felület: `side_switching` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kétirányú kulcs + csempe), 76.
  meccsterv-szabály (az ő egy-oldalas támadásuk × a ti
  szerzés-gépezetetek), 97. edzés-szabály (kötelező oldalváltás a
  kisjátékban, hosszú keresztpassz technika).
- **Lerohanás-védés**: hogy véd a kapus gyorsindítás ellen — a kaput
  eltaláló lövéseket fázisra bontjuk (a labda a lövés előtti 8 mp-ben
  még a támadó saját térfelén járt = gyorsindításos; különben
  rendezett), és a védő oldal kapusának védés-arányát hasonlítjuk
  össze (fázisonként 4+ lövésből, 15+ százalékpont a küszöb). Az
  érzékeny kapus ellen futni kell — minden szerzés után indíts; a
  lerohanás-fogó ellen a gyors befejezést is ki kell játszani (csel,
  visszatett labda). Egy réteg, sok felület: `gk_break_response`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (kétirányú kulcs + csempe), 75. meccsterv-szabály
  (az ő lerohanás-érzékeny kapusuk × a ti lerohanás-gépezetetek), 96.
  edzés-szabály (2v1/3v2 gyorsindítás elleni kapus-sorozat +
  visszarendeződés).
- **Gól-előkészítés hossza**: direkt vagy kombinatív gólokból élnek
  — gólonként megszámoljuk a gólt szerző csapat passzait az előző
  birtoklás-határig visszanézve. A direkt csapat (a gólok 50%+ része
  0–2 passzból, 4+ gólból) az első hullámból él: ellene a
  visszarendeződés a meccs; a kombinatív (50%+ rész 5+ passzból)
  kijátssza a falat: ellene türelmes, fegyelmezett fal kell — aki az
  ötödik passznál kilép, azon átmennek. Saját olvasatban a csak
  kombinatív góltermelés fogatlan első hullámot jelez. Egy réteg,
  sok felület: `goal_buildup` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kétirányú kulcs + csempe), 74.
  meccsterv-szabály (az ő kombinatív góltermelésük × a ti rés-mentes
  falatok), 95. edzés-szabály (2 passzos gyorsindítás, első hullámos
  befejezés).
- **Előkészítő-függés**: mennyire egy emberre épül a
  gólpassz-termelés — a lövő-koncentráció előkészítő-oldali párja:
  az asszist-függés azt mondja meg, MENNYIRE előkészítettek a gólok,
  ez azt, hogy KI készíti elő őket. Ha a gólpasszos gólok 50%+ része
  ugyanattól a játékostól jön (5+ gólpasszos gólból), a
  kulcs-előkészítő elvágása (előfogás, passzsáv-zárás, korai
  kettőzés) az egész befejezést megbénítja; saját olvasatban második
  játékszervezőt kell kinevelni. Egy réteg, sok felület:
  `assist_concentration` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 73.
  meccsterv-szabály (az ő egy-emberes előkészítésük × a ti
  labdaszerzésetek), 94. edzés-szabály (irányító-szerep forgatása,
  befejezés előkészítő nélkül).
- **Középkezdés-tempó**: kapott gól után mennyi idő alatt ér át a
  labda az ellenfél térfelére — az outlet_speed a védés utáni
  indítást méri, ez a kapott gól utánit: a lerohanás-jelző. A
  lerohanós csapat (az újraindítások 50%+ része 12 mp-en belüli
  térfél-átlépés, 4+ kapott gólból) ellen gól után tilos az
  ünneplés — azonnali visszarendeződés, fékező ember középen; a
  lassan újraindító (20% alatt) középkezdése letámadható; saját
  olvasatban a gyors középkezdés begyakorolható fegyver. Egy réteg,
  sok felület: `restart_speed` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kétirányú kulcs + csempe), 72.
  meccsterv-szabály (az ő lassú középkezdésük × a ti elöl-szerző
  presszetek), 93. edzés-szabály (kijelölt labdaszedő, 5 mp-es
  szabály).
- **Elsütés-idő**: kapásból lőnek vagy sokáig fogják a labdát —
  lövésenként visszafelé lépkedve mérjük, mennyi ideig volt a labda
  folyamatosan a lövőnél az elengedés előtt. A kapásból lövő csapat
  (60%+ elsütés 0,6 mp-en belül, 8+ lövésből) ellen a kapus a
  passzra mozduljon, ne a lövésre; a labdafogó (25% alatti gyors
  elsütés) időt ad — a kilépés és a blokk ellene szinte ingyen van,
  és saját olvasatban a gyors elsütés a téma. Egy réteg, sok
  felület: `shot_release` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kétirányú kulcs + csempe), 71.
  meccsterv-szabály (az ő labdafogó lövőik × a ti blokk-falatok),
  92. edzés-szabály (kapásból lövés sorozatban, lövő-kör
  időnyomással).
- **Beálló-védekezés**: mennyire bírja a fal az ellenfél beállóját —
  a beálló-terhelés (pivot_usage) védő-oldali tükre: ott az látszik,
  ki mennyit játszik a beállóval, itt az, ki mennyire bírja ellene.
  Ha az ellenük vezetett beállós támadások gólaránya 15+
  százalékponttal magasabb a beálló nélkülieknél (6+ beállós
  támadásból), a beálló-őrzés a gyenge pont: az ellenfélnek a
  beálló-etetés a terv; ha ugyanennyivel alacsonyabb, a beálló
  ellenük zsákutca — körbe kell játszani. Egy réteg, sok felület:
  `pivot_defense` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kétirányú kulcs + csempe), 70.
  meccsterv-szabály (az ő gyenge beálló-őrzésük × a ti beállós
  játékotok), 91. edzés-szabály (beálló-őrzés: elöl-mögött váltás,
  kettőzés-időzítés).

## v0.1.24 — kiadva (2026-07-25)

> Kiadás-jegyzet: tíz új elemzés-réteg, ezúttal a MÁSIK OLDALRÓL. A
> kör vezérfonala a tükrözés: több meglévő támadó-réteg mostantól
> megkapta a védekező párját (a lepattanó-harc mellé a lepattanó-fal,
> az oldal-részrehajlás mellé az engedett-oldal, a kihagyott ziccer
> ára mellé az eladás-büntetés), és két réteg az OKOT méri ott, ahol
> eddig csak a következmény látszott (fal-rés a betörés-folyosó mögé,
> gólcsend-anatómia a gólcsend mögé). Kibővült a kapus-kép is: a
> kihozatal gyorsasága mellé bejött a hossza (hosszú indítós vagy
> rövid kihozós) és a biztonsága (megérkezik-e a labda), plusz a
> fáradás-kép területi tagja (területi-fölény-esés) és két
> stílus-olvasat (asszist-függés, támadó-mozgás). A figura-tervezőben
> a védőfal alapból 6-0-ban, a hatoson kívül áll. A meccsterv 69, az
> edzés-fókusz 90 szabálynál jár; a backend csomag 757 teszttel zöld.

### A v0.1.24 körei

- **Indítás-biztonság**: a kapus-indítás kihez jut el először — az
  outlet_speed a kihozatal gyorsaságát, a gk_outlet_length a hosszát
  méri, ez azt, hogy MEGÉRKEZIK-e. Akinek az indításai 25%+ arányban
  az ellenfélnél kötnek ki (6+ indításból), annak a kihozatala
  letámadással kényszeríthető: ellene a fogadók lefedése + letámadó
  a kapusra; saját olvasatban az indítás-biztonság (biztos első
  passz, kihozatal-minták) a téma. Egy réteg, sok felület:
  `gk_outlet_security` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 69.
  meccsterv-szabály (az ő elcsíphető indításuk × a ti elöl-szerző
  presszetek), 90. edzés-szabály (indítás-biztonság nyomás alatt).
- **Támadó-mozgás**: álló vagy mozgásos a szervezett támadás — a
  támadó mezőnyjátékosok átlagsebessége szervezett támadásban (kapus
  és becsült pozíciók nélkül, track-ugrás szűréssel, 120+ mért
  játékos-másodpercből). Az "álló kézilabda" (0,9 m/s alatt) a védő
  álma: ellene a kilépés kockázat nélkül vállalható; a mozgásos (1,6
  m/s felett) ellen a fegyelmezett átadás-átvétel a kulcs. Egy réteg,
  sok felület: `attack_motion` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kétirányú kulcs + csempe), 68.
  meccsterv-szabály (az ő álló támadásuk × a ti kilépős
  védekezésetek), 89. edzés-szabály (passzolj és fuss,
  mozgás-szabályos 6 a 6).
- **Fal-rés**: mekkora réseket hagy a rendezett védőfal — a
  betörés-folyosó a következményt méri (hol törnek be), ez az okot.
  Rendezett védekezésben a fal szomszédos védői közti legnagyobb
  rést nézzük: akinél a falkockák 40%+ részében 3,5 m-nél nagyobb a
  rés (100+ mért kockából, legalább 4 fős falnál, kapus nélkül), az
  ellen a betörés és a beúszó beálló a terv; saját olvasatban a
  zárás-távolság tartása a téma. Egy réteg, sok felület: `wall_gaps`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (kulcs + csempe), 67. meccsterv-szabály (az ő
  réses faluk × a ti betörés-játékotok), 88. edzés-szabály
  (zárás-távolság, rés-zárás játék a 6-oson).
- **Gólcsend-anatómia**: a leghosszabb gólcsend alatt lő-e a csapat
  — a gólcsend (goal_droughts) csak azt mondja, meddig, ez azt, hogy
  MIÉRT. A "kihagyós" csendben (0,8+ lövés/perc) a helyzet megvan,
  a befejezés hiányzik — a téma a helyzetkihasználás és a túloldali
  kapus melegen tartása; a "néma" csendben (0,3 lövés/perc alatt)
  lövésig sem jutnak — a szervezés állt le, és az ellenfél pressze
  tartva tartja a csendet. Egy réteg, sok felület: `drought_anatomy`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (kétirányú kulcs + csempe), 66. meccsterv-szabály
  (az ő néma csendjük × a ti elöl-szerző presszetek), 87.
  edzés-szabály (csend-törő vész-figurák vs befejezés nyomás alatt).
- **Engedett-oldal**: a fal melyik oldala felől jönnek a kapott
  lövések — az oldal-részrehajlás védő-oldali tükre. Ha a kapott
  szélső-sávos lövések 65%+ része ugyanarról az oldalról jön (8+
  lövésből), az az oldal-védő és a segítő-csúszás gyengéje: az
  ellenfél oda szervezheti a befejezést; a "bal" a VÉDŐ fal bal
  oldala. Egy réteg, sok felület: `conceded_side_bias` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (kulcs +
  csempe), 65. meccsterv-szabály (az ő gyenge fal-oldaluk × a ti
  erős támadó-oldalatok — a két oldal-mező egymásra illesztve), 86.
  edzés-szabály (fal-oldal erősítés, zárás-technika párban).
- **Figura-tervező — a védőfal alapból 6-0, a hatoson kívül**: a
  tervező védői mostantól alapból hatan állnak, és a fal a 6 m-es
  kapuelőtér ívét követi KÍVÜLRŐL (középen fél méterrel a hatos
  előtt, a széleken az ívre simulva) — egy védő sem léphet a
  kapuelőtérbe, a mélység-csúszka a teljes falat tolja feljebb
  (6–12 m). A kliens-oldali szimuláció és a backend
  (play_simulation.py respond) azonos geometriát használ, így a
  meccsből tanult védelem elleni szimulációban sem kerülhet védő a
  hatoson belülre.
- **Eladás-büntetés**: az eladott labda fél percen belül gólba
  kerül-e — a kihagyott ziccer ára eladás-oldali párja: nem az a
  kérdés, mennyi labdát ad el a csapat, hanem hogy mennyibe kerül.
  Akinek az eladásai 35%+ arányban gyors kapott gólt érnek (6+
  eladásból), annál a váltás-sprint hiányzik: az ellenfél olvasata,
  hogy minden szerzés után azonnal indulni kell; saját olvasatban az
  eladás utáni visszarendeződés a téma. Egy réteg, sok felület:
  `turnover_punishment` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 64.
  meccsterv-szabály (az ő drága eladásaik × a ti kontra-gólgépetek),
  85. edzés-szabály (váltás-sprint eladás után).
- **Kapus-indítás hossza**: hosszú indítós vagy rövid kihozós a
  kapus — az outlet_speed a gyorsaságot méri, ez a hosszt. Ha a
  kapus-passzok 50%+ hányada 15 m feletti (6+ passzból), a szélső
  indítás-sávok zárása a terv; ha 15% alatti, a magas letámadás
  termel; az egysíkú kihozatal mindkét irányban kiszámítható — saját
  olvasatban az indítás-variancia a téma. Egy réteg, sok felület:
  `gk_outlet_length` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kétirányú kulcs + csempe), 63.
  meccsterv-szabály (az ő hosszú-indításos kapusuk × a ti gyors
  visszarendeződésetek), 84. edzés-szabály (indítás-variancia).
- **Területi-fölény-esés**: a field tilt 1. vs 2. félidei összevetése
  — a fáradás-kép terület-tagja. Akinek a 2. félidőre 12+
  százalékponttal esik a területi fölénye (félidőnként 100+ birtokos
  kockából), az fáradtan már nem tudja az ellenfél térfelén tartani a
  játékot: ellene a terv a türelem — az 1. félidei nyomást kiállni,
  mert a hajrára magától átfordul a pálya; saját olvasatban a magas
  birtoklás fáradtan (kihozatal-minták a 2. félidei presszre) a téma.
  Egy réteg, sok felület: `tilt_fade` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (kulcs + csempe), 62.
  meccsterv-szabály (az ő fölény-esésük × a ti kitartó tempótok), 83.
  edzés-szabály (magas pulzusú területjáték).
- **Asszist-függés**: a gólok mekkora része előkészített (gólpasszos)
  — a gólpassz-forrás a honnan kérdést nézi, ez a mennyire-t. A
  kollektív (70%+ asszisztált, 6+ gólból) csapat ellen a passzsávok
  elvágása a terv (aktív kéz, a beálló elé lépés), az egyéni
  megoldásokból élő (35%- asszisztált) ellen a kulcsember-párharc
  (emberfogás, kettőzés); saját olvasatban a kiadás-figurák és az
  előkészített befejezés a téma. Egy réteg, sok felület:
  `assist_reliance` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 61.
  meccsterv-szabály (az ő kiadás-függő támadásuk × a ti
  labdaszerzésetek), 82. edzés-szabály (előkészített befejezés, a
  gólpasszos gól két pontot ér).
- **Lepattanó-fal**: hány második rohamot enged a védekezés — a
  második roham réteg védő-oldali tükörképe: ott az látszik, ki
  harcolja vissza a saját lepattanóit, itt az, ki engedi vissza az
  ellenfélét. Ha az ellenfél a kimaradt lövései 35%+ hányadánál újra
  lőhet (6+ lehetőségből), a fal nem zár: az ellenfélnek a
  lepattanó-ember terv, saját olvasatban a box-out és a lövés utáni
  zárás a téma. Egy réteg, sok felület: `second_chance_allowed`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (kulcs + csempe), 60. meccsterv-szabály (az ő
  áteresztő faluk × a ti lepattanó-harcotok), 81. edzés-szabály
  (lepattanó-zárás, box-out).

## v0.1.23 — kiadva (2026-07-25)

> Kiadás-jegyzet: húsz új elemzés-réteg egyetlen körben — mind a
> megszokott "egy réteg, sok felület" bekötéssel (motor, edzői
> összefoglaló, /analyze + meccs-csomag, felderítés-profil,
> meccsterv- és edzés-szabály, kliens-csempe, teszt). A nagy témák: a
> kiszámíthatóság-profil (oldal-részrehajlás, ritmus-egyhangúság,
> lövő-koncentráció), a labdabiztonság két új olvasata
> (eladás-időzítés, pressz-tűrés), a mentális profil kibővülése
> (holtpont-mérleg, sorozat-törés, bravúr utáni lendület, félidei
> fordítás, gól utáni elalvás, szoros meccs-mérleg, félidő-zárás),
> a fáradás-kép új tagjai (tempó-esés, befejezés-esés,
> fegyelem-esés), valamint kapus-témák (hetes-védés,
> kapuscsere-hatás, kapus-gyengeoldal). Emellett bekerült a
> fejlesztési recept (CLAUDE.md): az új rétegek innentől checklist
> alapján készülnek. A meccsterv 59, az edzés-fókusz 80 szabálynál
> jár; a backend csomag 747 teszttel zöld.

### A v0.1.23 körei

- **Pressz-tűrés**: labdabiztonság testközeli védő mellett vs
  szabadon — a nyomás alatti befejezés (pressure_finishing) passz-
  oldali párja. Minden passznál és eladásnál megnézzük, volt-e 2 m-en
  belüli védő a labdásnál; ha rászorított védőnél az eladás-arány
  15+ százalékponttal magasabb (10+ esemény mindkét mintában), a
  csapat pressz-érzékeny: az agresszív, kilépő fal és a kettőzés
  ellene termelés; saját olvasatban a nyomás alatti passz (szűk
  területes labdatartás) a téma. Egy réteg, sok felület:
  `pass_security_under_pressure` motor, edzői összefoglaló, /analyze
  + meccs-csomag, felderítés-profil (kulcs + csempe), 59.
  meccsterv-szabály (az ő pressz-érzékenységük × a ti szoros
  falatok), 80. edzés-szabály (nyomás alatti passz).
- **Eladás-időzítés**: a birtoklás hányadik másodpercében jön a
  labdaeladás — a hely (turnover_zones) mellett az idő-olvasat. Aki
  az eladásai felét+ a birtoklás első 10 másodpercében követi el (6+
  eladásból), az a letámadásra érzékeny: ellene a magas, korai pressz
  a kihozatalnál azonnal termel; saját olvasatban a kihozatal nyomás
  alatt (biztonsági passz-opciók) a téma. Egy réteg, sok felület:
  `turnover_timing` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 58.
  meccsterv-szabály (az ő korai eladásaik × a ti elöl-szerzésetek),
  79. edzés-szabály (kihozatal letámadó védőkkel).
- **Kapus-gyengeoldal**: a kapu melyik oldalára kapja a csapat a
  gólokat (a kapus szemszögéből) — a kapu-sarok réteg védő-oldali
  tükörképe. Ha a bekapott gólok 45%+ hányada ugyanarra az oldalra
  megy (6+ gólból), az ellenfél lövő-terve egy mondat ("arra a
  sarokra fejezz be"), saját olvasatban a kapus oldal-technikája és
  beállás-korrekciója a téma. Egy réteg, sok felület: `gk_weak_side`
  motor (a goal_placement tükrözésével), edzői összefoglaló, /analyze
  + meccs-csomag, felderítés-profil (kulcs + csempe), 57.
  meccsterv-szabály (az ő gyenge kapu-oldaluk × a ti
  célzás-pontosságotok), 78. edzés-szabály (kapus-oldaltechnika).
- **Lövő-koncentráció**: mennyire egy emberre épül a lövés-terhelés —
  a kiszámíthatóság személyi olvasata. Ha a lövések 35%+ hányadát
  ugyanaz a játékos adja le (12+ azonosított lövésből), a védekezés
  személyre szabható: emberfogás/korai kettőzés a fő lövőn, és
  olyanoknak kell befejezniük, akik ezt nem szokták; saját olvasatban
  a lövés-elosztás (másod-lövők befejezései) a téma. Egy réteg, sok
  felület: `shot_concentration` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 56.
  meccsterv-szabály (az ő fő lövőjük × a ti aktív falatok), 77.
  edzés-szabály (lövés-elosztás, kettőzés elleni átadó-döntések).
- **Ritmus-egyhangúság**: mennyire egyforma hosszúak a támadások — a
  kiszámíthatóság idő-olvasata. Akinek belső órája van (a
  támadás-hossz relatív szórása kicsi), arra a védekezés ráállhat: az
  átlagidő előtt pár másodperccel időzített kettőzés/letámadás rendre
  a lövés-előkészítést töri meg; saját olvasatban a tudatos
  ritmus-váltás a téma. A szórás összeg + négyzetösszeg tárolással
  meccsek közt is pontosan számolódik. Egy réteg, sok felület:
  `attack_rhythm` motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (kulcs + csempe), 55. meccsterv-szabály (az ő
  belső órájuk × a ti labdaszerzésetek), 76. edzés-szabály
  (ritmus-váltás, kevert tempójú sorozatok).
- **Oldal-részrehajlás**: a lövések a támadás melyik oldaláról jönnek
  (bal/közép/jobb, a támadó bal keze felőli oldal a "bal") — a
  kiszámíthatóság térbeli olvasata. Akinek a szélső-sávos lövései
  kétharmadban egy oldalról jönnek, annak a támadása fél-oldalas: a
  fal eltolható, a segítő védő előre tudja, honnan jön a lövés; saját
  olvasatban a gyenge oldal terhelése és az oldalváltó passz a téma.
  Egy réteg, sok felület: `attack_side_bias` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (kulcs +
  csempe), 54. meccsterv-szabály (az ő fél-oldalas támadásuk × a ti
  blokk-erőtök), 75. edzés-szabály (oldal-egyensúly, oldalváltó
  passzok).
- **Célzás-pontosság**: a lövés-kísérletekből mennyi tart kapura. A
  mellé lőtt labda a legolcsóbb támadás-halál: nincs lepattanó, csak
  ajándék-kidobás azonnali ellen-indítással — aki sokat lő mellé, az
  ellen a mellé lövés a kidobás-indítás jele és a blokk-vállalás is
  olcsó; aki szinte mindent kapura tesz, az ellen a blokk-munka
  kötelező. Egy réteg, sok felület: `shot_accuracy` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (kulcs
  mindkét irányra + csempe), 53. meccsterv-szabály (az ő
  mellé-lövésük × a ti gyors átmenetetek), 74. edzés-szabály
  (célzás-edzés, lövés-válogatás).
- **Befejezés-esés (fáradó befejezés)**: a gólra váltás (gól az összes
  lövés-kísérletből, a mellé menőt is számolva) az 1. vs 2. félidőben
  — a fáradás-kép befejezés-tagja, a kapus-forma támadó-oldali párja.
  Akinek a 2. félidőre érdemben (15 pp+) esik, annál fáradtan már nem
  ül a lövés — ellene az első félidőt kell túlélni, a hajrában elég a
  tömör fal; akinek nő, az a végére lő formába. Egy réteg, sok
  felület: `finish_fade` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 52. meccsterv-
  szabály (az ő eső befejezésük × a ti kitartó tempótok),
  73. edzés-szabály (fáradt befejezés, hajrá-lövésszabály).
- **Bravúr utáni lendület**: a nagy védés után jön-e gyors gól elöl —
  a kihagyott ziccer ára védés-oldali tükre. Akinél a bravúr rendre
  gólt ér a túloldalon, ott a kapus indítás: a rossz lövés ellenük
  kontra — lövés-válogatás és bravúr utáni azonnali visszazárás kell;
  akinél a bravúr elhal, ott a kapus megfog, de nem büntet — a merész
  lövésnek nincs kontra-ára. Egy réteg, sok felület:
  `big_save_momentum` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs mindkét irányra + csempe),
  51. meccsterv-szabály (az ő elhaló bravúrjuk × a ti gyors
  visszarendeződésetek), 72. edzés-szabály (bravúr utáni indítás).
- **Sorozat-törés**: az elszenvedett 3+ gólos sorozat hol áll meg — a
  sorozatok réteg védekező-mentális párja. Aki a sorozatot rendre
  3-nál töri (időkérés, váltás, higgadt gól), az nem esik szét —
  sorozattal nem ölöd meg; akinél a 3-0-ból rendre 5-6-0 lesz, ott a
  mini-sorozat megnyomása duplán kifizetődik, és az időkérése sem
  mentőöv. Egy réteg, sok felület: `run_containment` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (kulcs
  mindkét irányra + csempe), 50. meccsterv-szabály (az ő elfutó
  sorozataik × a ti sorozat-képességetek), 71. edzés-szabály
  (sorozat-törés protokoll).
- **Holtpont-mérleg**: döntetlen állásról ki lép el góllal — a
  vezetés-váltások irány-párja, a legtisztább nyomás-teszt (a 0-0-tól
  minden kiegyenlítés utáni első gól). Aki a holtpontokat rendre
  elviszi, azzal nem szabad egálba összecsúszni — előnyből kell
  kontrollálni; aki rendre elengedi, azt utolérni elég: egálnál ő
  remeg. Egy réteg, sok felület: `parity_breaks` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (kulcs
  mindkét irányra + csempe), 49. meccsterv-szabály (az ő remegő
  holtpontjuk × a ti holtpont-erőtök), 70. edzés-szabály
  (holtpont-játék, nyomás alatti befejezés).
- **Félidei hátrányból fordítás**: a félidei állás vs a végeredmény,
  meccsek közt összegezve — a mentális profil új tagja a szoros
  meccs-mérleg mellett. Aki félidei hátrányból rendre fordít, az ellen
  a félidei előny nem ér semmit (60 perces meccsre kell készülni); aki
  sosem jön vissza, annál a félidei előny majdnem kész győzelem — a
  meccsterv az első 30 percre épülhet. Egy réteg, sok felület:
  `halftime_comeback` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 48. meccsterv-
  szabály (az ő feladott hátrányuk × a ti erős kezdésetek),
  69. edzés-szabály (szünet utáni fordítás-protokoll).
- **Tempó-esés (elfogyó láb)**: a csapat támadás/perc mutatója az
  1. vs 2. félidőben, a felismert félidő mentén. Akinél a 2. félidőre
  érdemben (0,2 támadás/perc+) esik az ütem, az már nem bírja futni a
  meccset — ellene a szünet után tempót KELL emelni; akinek kitart, az
  a hajrára kapcsol. A fáradás-kép hatodik tagja: lövőerő, fal, kéz,
  kapus és fej után a láb. Egy réteg, sok felület: `team_pace_fade`
  motor, edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (kulcs + csempe), 47. meccsterv-szabály (az ő elfogyó lábuk × a ti
  bírt tempótok), 68. edzés-szabály (tempó-állóképesség, rotáció).
- **Kihagyott ziccer ára**: a kihagyott nagy helyzet utáni fél percen
  belüli kapott gól — a klasszikus "a kihagyott helyzet a túloldalon
  gól". Akinél a kihagyást rendre azonnali büntetés követi, ott a
  kihagyás utáni fejlógatás a baj (a visszarendeződés a téma); az
  ellenfél olvasata: minden kihagyásuk indítás-jel. Egy réteg, sok
  felület: `miss_punishment` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 46. meccsterv-
  szabály (az ő kihagyás utáni zavaruk × a ti gyors átmenetetek),
  67. edzés-szabály (kihagyás utáni visszarendeződés).
- **Kapuscsere-hatás**: segít-e a kapuscsere — az első csere
  előtti vs utáni védés% összevetése. Akinél a csere rendre
  fordít, ott a lövő-terv a második kapusra is kell; akinél nem
  segít, ott az első kapus megingása után nincs mentőöv. Egy
  réteg, sok felület: `gk_change_effect` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (kulcs + csempe), 45. meccsterv-szabály (az ő mentőöv nélküli
  kapus-posztjuk × a ti erős kezdésetek), 66. edzés-szabály
  (kapus-alapok + fal-kapus összhang).
- **Hetes-védés (a kapus a hetesek ellen)**: a kapusra dobott
  kapura tartó hetesek mérlege — a hetest fogó (40%+) kapus ellen
  a hetes nem kész gól, a sosem fogó ellen a hetes-kiharcolás
  biztos üzlet. A hetes-dobó oldal (dobók + irány) régi rétegének
  kapus-oldali párja. Egy réteg, sok felület: `seven_meter_defense`
  motor, edzői összefoglaló (2+ fogott hetes), /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 44. meccsterv-
  szabály (az ő hetest nem fogó kapusuk × a ti kiharcolótok),
  65. edzés-szabály (kapus hetes-készülés).
- **Félidő-zárás (a szünet előtti 5 perc)**: ki üt utoljára az
  öltözőbe vonulás előtt — aki az 1. félidő hajráját rendre
  elengedi, annál ott olcsó gólok vannak; aki erősen zár, annál a
  félidő végén tilos kiengedni. A szünet utáni kezdés réteg párja
  a szünet másik oldaláról. Egy réteg, sok felület:
  `first_half_close` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 43. meccsterv-
  szabály (az ő elengedett zárásuk × a ti erős zárásotok),
  64. edzés-szabály (félidő-zárás begyakorlása).
- **Szoros meccs-mérleg**: az 1-2 gólos meccsek kimenetele meccsek
  közt összegezve — aki a szorosat rendre elbukja, azt elég
  meccsben tartani (a hajrában ők roppannak meg); aki hozza, attól
  nem jön ajándék. A mentális profil negyedik tagja. Egy réteg,
  sok felület: `close_game_record` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (kulcs + csempe),
  42. meccsterv-szabály (az ő szoros-meccs gyengeségük × a ti
  hajrá-erőtök), 63. edzés-szabály (hajrá-forgatókönyv szoros
  vereség után).
- **Gól utáni elalvás**: a saját gólokra fél percen belül
  visszakapott válasz-gólok aránya — a 40%+ a középkezdés utáni
  elalvás jele (a szerzett előny rendre azonnal elolvad), ellenük
  a középkezdés utáni azonnali letámadás a kulcs. A válasz-idő
  réteg párja a másik irányból. Egy réteg, sok felület:
  `post_goal_lapses` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 41. meccsterv-
  szabály (az ő elalvásuk × a ti gyors válaszotok), 62. edzés-
  szabály (gól utáni visszarendeződés).
- **Fegyelem-esés (fáradó fej)**: a kiállítások félidőnkénti
  eloszlása — akinek a hajrában jönnek a kiállításai, az fáradtan
  szabálytalankodik: ott emberelőny várható ellene. A fáradás-kép
  ötödik tagja (lövőerő, fal, kéz, kapus után a fej). Egy réteg,
  sok felület: `discipline_fade` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (kulcs + csempe),
  40. meccsterv-szabály (az ő hajrá-kiállításaik × a ti
  emberelőny-játékotok), 61. edzés-szabály (védekezés-technika
  fáradtan).

## v0.1.22 — kiadva (2026-07-25, PR #562–#570)

> Kiadás-jegyzet: a legfontosabb a két beragadás-javítás — a
> feldolgozás többé nem állhat meg csendben egy fix kockánál
> (elakadás-őrszem + OpenCV szál-korlát), és ha a motor mégis
> elakad, 3 perc után magától kilép és az addig kész részt teljes
> utómunkával, folytatható meccsként menti. Mellé hat új
> elemzés-réteg érkezett (mind a megszokott "egy réteg, sok
> felület" bekötéssel) — köztük a fáradás-kép így négytagúra
> bővült (lövőerő, fal, kéz, kapus), és az első mentális-profil
> réteg (előny-őrzés). Windows- és macOS-telepítővel a Releases
> oldalon.

### A v0.1.22 körei

- **Előny-őrzés (elengedett vezetés)**: a meccs közbeni legnagyobb
  vezetés vs a végeredmény — aki 3+ gólos előnyt is elenged, az
  ellen sosem szabad feladni; aki mindig megtartja, azt nem szabad
  hagyni ellépni. Egy réteg, sok felület: `lead_protection` motor
  (a vezetés-alakulás rétegre építve), edzői összefoglaló (fordulás
  nélküli elengedés), /analyze + meccs-csomag, felderítés-profil
  (kulcs + csempe, meccsek közt összegezve), 39. meccsterv-szabály
  (az ő elengedett vezetéseik × a ti hajrá-erőtök), 60. edzés-
  szabály (vezetés-menedzsment).
- **Kapus-forma félidőnként**: a védés-hatékonyság 1. vs 2. félidei
  összevetése — 15+ százalékpontos esés a hajrában verhető kapust
  jelent, a formába lendülő kapust az elején kell büntetni. A
  fáradás-kép negyedik (kapus-oldali) tagja. Egy réteg, sok
  felület: `gk_save_fade` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 38. meccsterv-
  szabály (az ő eső kapusuk × a ti hajrá-erőtök), 59. edzés-
  szabály (kapus-terhelés, tervezett kapuscsere).
- **Hibajavítás — a beragadt feldolgozás magától kilép és ment**:
  az elakadás-őrszem mellé motor-oldali védő került — ha a
  videó-olvasó/detektáló 3 percig nem ad új kockát, a feldolgozás
  megszakítja a várakozást, az addig kész rész teljes utómunkával,
  befejezetlen meccsként mentődik (a könyvtárból folytatható), a
  státusz pedig elmondja, mi történt.
- **Hibajavítás — beragadó feldolgozás (elakadás-őrszem + OpenCV
  szál-korlát)**: a feldolgozás egyes videóknál egy fix kockánál
  csendben megállhatott (a kijelzés örökké a friss becslést
  mutatta). Mostantól (1) a job-státusz szívverést követ, és 2 perc
  előrelépés nélkül a kliens FIGYELEM-üzenetet kap (a Megszakítás
  menti az addig kész részt); (2) az OpenCV egy szálra fogva fut a
  detektálás alatt — a PyTorch OpenMP-jével való ritka natív
  ütközés (beragadás-gyanús ok) kizárva.
- **Labdabiztonság-esés (fáradó kéz)**: az eladás-ütem 1. vs 2.
  félidei összevetése a birtoklás-időre vetítve — +0,2 eladás/perc
  romlás a hajrában törékeny labdabiztonságot jelez. A fáradás-kép
  harmadik pillére (lövőerő + fal-nyomás mellett). Egy réteg, sok
  felület: `turnover_fade` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 37. meccsterv-
  szabály (az ő 2. félidei eladás-dömpingjük × a ti szerzés-
  gólgépetek), 58. edzés-szabály (labdabiztonság fáradtan).
- **Időkérés-mérleg**: működik-e a "mentő" időkérésük — a
  sorozatot megtörő vs fordulat nélküli időkérések meccsek közt
  összegezve. Egy réteg, sok felület: `timeout_record` motor,
  /analyze + meccs-csomag, felderítés-profil (kulcs + csempe),
  36. meccsterv-szabály (az ő hatástalan időkérésük × a ti
  sorozat-képességetek), 57. edzés-szabály (időkérés-
  forgatókönyv).
- **Védekezés-fellazulás (fal-fáradás)**: a védekezési nyomás 1. vs
  2. félidei átlagának összevetése — 0,5 m+ lazulás a hajrában
  szabad lövőket jelent, a szorosodó fal kemény hajrát. A
  lövőerő-esés védekezés-oldali párja. Egy réteg, sok felület:
  `pressure_fade` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 35. meccsterv-
  szabály (az ő fellazuló faluk × a ti hajrá-erőtök), 56. edzés-
  szabály (védekezés-állóképesség).
- **Lövés-időzítés (első hullám vs kivárás)**: MIKOR lőnek a
  támadáson belül — az első hullámból élő csapat (45%+ lövés az első
  8 mp-ben) ellen a visszarendeződés, a kivárók (22+ mp átlag) ellen
  a türelmes fal a kulcs. Egy réteg, sok felület: `shot_timing`
  motor, edzői összefoglaló, /analyze + meccs-csomag, felderítés-
  profil (kulcs + csempe), 34. meccsterv-szabály (az ő első-hullám
  lövéseik × a ti lassú visszaérésetek), 55. edzés-szabály
  (támadás-lezárás).

## v0.1.21 — kiadva (2026-07-24, PR #543–#561)

> Kiadás-jegyzet: a legfontosabb a macOS-javítás — a feldolgozás többé
> nem szállhat el csendben ~2%-nál ("Connection refused"): a motor
> belépési pontja a natív OpenMP-ütközést induláskor hatástalanítja
> (#545). Mellé tizenkét új elemzés-réteg érkezett (mind a megszokott
> "egy réteg, sok felület" bekötéssel), a meccsjelentés új Csapat-profil
> táblát kapott, és az élő nézet két új félidei jelzést. Windows- és
> macOS-telepítővel a Releases oldalon.

### A v0.1.21 körei

- **Felderítő narratíva stílus- és fal-jegyekkel**: az "Így
  támadnak" és a "Védekezésük" szakasz az új rétegekből is
  mesél — tömör/széthúzott fal, ziccert engedő vs kiszorító
  védekezés, letámadó szerzések; illetve az "Így támadnak"
  bevezető az új rétegekből is mesél — pörgetett/álló labdajáratás,
  hosszú-passzos (elfogható) játék, elöl nyomó vs hátul ragadó
  birtoklás.
- **Passz-hossz profil**: rövid kombinációs vagy hosszú, direkt
  passzjáték — a sok hosszú passz (15+ passzból 30%+ 10 m fölötti)
  elfogható és kontra-forrás, a rövid kombináció présálló. Egy
  réteg, sok felület: `pass_length` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (kulcs + csempe),
  33. meccsterv-szabály (az ő hosszú passzaik × a ti
  labdaszerzőitek), 54. edzés-szabály (passz-szerkezet).
- **Élő félidei letámadás- és lepattanó-jel**: a szünetben a pad két
  új "félidei kép" jelzést kap az 1. félidő adataiból — ha az
  ellenfél elöl, letámadásból szerez (35%+), a kihozatalt kell
  előkészíteni; ha harcol a lepattanóért (25%+ második roham), a
  lövés utáni lezárás a kulcs. (/analyze `steal_height_fh` +
  `second_chance_fh` + élő nézet.)
- **Szerzés-magasság (letámadás-jel)**: HOL szerez labdát a csapat
  — az elöl (a saját támadó térfélen) született szerzés a letámadás
  terméke (35%+ = élő prés), a csak-hátul szerzés passzív elöl-játék.
  Egy réteg, sok felület: `steal_height` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (kulcs + csempe),
  32. meccsterv-szabály (az ő letámadásuk × a ti hátul ragadó
  birtoklásotok), 53. edzés-szabály (letámadás-gyakorlás).
- **Meccsjelentés: Csapat-profil tábla**: az öt stílus-réteg
  (területi fölény, passz-tempó, fal-szélesség, támogatás-távolság,
  falba lövés) ítéletei egy táblában — a meccs "ujjlenyomata"
  csapatonként a nyomtatható jelentésben is.
- **Falba lövés (támadó-oldali blokk-arány)**: a lövés-kísérletek
  mekkora hányada akad el az ellenfél blokkján (4+ blokkból 20%+ =
  rosszul előkészített, kényszerű lövések). Egy réteg, sok felület:
  `blocked_shot_rate` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (gyengeség + kulcs + csempe),
  31. meccsterv-szabály (az ő falba lövő támadásuk × a ti blokkoló
  falatok), 52. edzés-szabály (lövés-előkészítés).
- **Passz-tempó (labdajáratás sebessége)**: hány passz jut a saját
  birtoklás egy percére — pörgetett (22+/perc: dolgoztatja a falat) vs
  álló járatás (12 alatt: a védelem békében felállhat). Egy réteg, sok
  felület: `pass_tempo` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kulcs + csempe), 30. meccsterv-
  szabály (az ő álló járatásuk × a ti labdaszerzésetek), 51. edzés-
  szabály (tempó-gyakorlás).
- **Engedett lövésminőség (xG/lövés a védekezésben)**: milyen értékű
  lövéseket enged a fal — ziccert engedő (0,38+ xG/lövés) vs kiszorító
  (0,22 alatt) védekezés. A meglévő xg_against most meccsek közt is
  összegződik. Felületek: felderítés-profil (kulcs + csempe),
  29. meccsterv-szabály (az ő ziccert engedő faluk × a ti közeli
  befejezés-erőtök), 50. edzés-szabály (ziccer-megelőzés).
- **Védelmi tömörség (fal-szélesség)**: milyen szélesen áll a védőfal a
  felállt védekezésben — tömör (11 m alatt: a szélek nyitva) vs
  széthúzott (15 m fölött: a közép nyitva). A vonal-magasság melletti
  második térbeli fal-jellemző. Egy réteg, sok felület: `defensive_width`
  motor, edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (kulcs + csempe), 28. meccsterv-szabály (az ő tömör faluk × a ti erős
  szélső-játékotok), 49. edzés-szabály (fal-tömörség gyakorlás).
- **Területi fölény (field tilt)**: a birtoklás mekkora része zajlik az
  ellenfél térfelén — elöl nyomó csapat (65%+) vs a saját térfelén
  ragadó, kihozási gondokkal küzdő (45% alatt). Egy réteg, sok felület:
  `field_tilt` motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (kulcs + csempe), 27. meccsterv-szabály (az ő hátul
  ragadó birtoklásuk × a ti szoros védekezésetek), 48. edzés-szabály
  (labdakihozatal prés ellen).
- **Támogatás-távolság (izoláció-jel)**: milyen messze van a labdás
  játékostól a legközelebbi társa — magára hagyott labdás ellen a prés
  működik (kényszerített egyéni megoldások), szoros támogatás ellen
  kockázatos. Egy réteg, sok felület: `support_distance` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (kulcs +
  csempe), 26. meccsterv-szabály (az ő izolált labdásuk × a ti
  labdaszerzésből élő támadásotok), 47. edzés-szabály (támogató mozgás).
- **Gól-koncentráció (gólfüggés)**: egy emberre épül-e a csapat
  gólszerzése — a fő gólszerző részesedése a gólokból (40%+ = az ő
  kikapcsolása a meccs kulcsa; elosztott = csapat-védekezés kell). Egy
  réteg, sok felület: `goal_concentration` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (kulcs + csempe),
  25. meccsterv-szabály (az ő gólfüggésük × a ti tapadó emberfogótok),
  46. edzés-szabály (másodlagos befejezők építése).
- **Lövőerő-esés (fáradás-jel)**: a lövés-sebesség 1. vs 2. félidei
  átlagának összevetése — ha a hajrára érdemben (8%+) lassulnak a
  lövések, a csapat fárad; ha nőnek, mély a rotáció. Egy réteg, sok
  felület: `shot_speed_fade` motor, edzői összefoglaló (Intenzitás
  szakasz), /analyze + meccs-csomag, felderítés-profil (kulcs + csempe),
  24. meccsterv-szabály (az ő fáradásuk × a ti rotációtok), 45.
  edzés-szabály (lövőerő-állóképesség).
- **Hibajavítás — a motor csendben elszállt feldolgozás közben (macOS)**:
  a becsomagolt kiadásban a PyTorch és az OpenCV/numpy natív
  OpenMP-futásideje ütközhetett, és a motor az első nehéz számításnál
  (kalibráció) `abort()`-tal meghalt — a kliens csak "Connection
  refused"-öt látott ~2%-nál. A motor belépési pontja most minden nehéz
  import előtt beállítja a `KMP_DUPLICATE_LIB_OK=TRUE`-t és a
  `PYTORCH_ENABLE_MPS_FALLBACK=1`-et. (#545)
- **Kezdés-profil (nyitógól + korai állás)**: ki szerzi a meccs első
  gólját és milyen a korai (első 6 gól) mérleg — csak a gól-sorrendből,
  abszolút idő nélkül, ezért rövid felvételen is stabil (más, mint a
  félidő-mérleg vagy a szünet-kezdés). Egy réteg, sok felület:
  `opening_profile` motor, /momentum + meccs-csomag, meccs-történet
  mondat + meccsjelentés-sor, felderítés-profil (kulcs + csempe),
  23. meccsterv-szabály (lassú kezdésük × a ti jó kezdésetek),
  44. edzés-szabály (tervezett kezdés), trend-mutató (nyitógól-arány).
- **Második roham (lepattanó-visszaszerzés)**: a kimaradt (védett/mellé)
  lövés után a támadó visszaszerzi-e a labdát és újra lő-e, mielőtt az
  ellenfél lőne — a "harc a lepattanóért" agresszivitása és a második
  esélyek gólaránya. Egy réteg, sok felület: `second_chance` motor,
  edzői összefoglaló-jelzés, meccsjelentés (Befejezés-profil új oszlop),
  /analyze + meccs-csomag, felderítés-profil (kulcs + csempe), két
  meccsterv-szabály (gyenge lepattanó-harcuk × a ti kontrátok; erős
  lepattanó-harcuk × a ti blokkoló faluk), 43. edzés-szabály,
  trend-mutató (második roham/meccs).

## v0.1.20 — kiadva (2026-07-23, PR #535–#541)

> Kiadás-jegyzet: névváltás — a kiadott app és telepítő mostantól
> **SportMachine** (macOS app, Windows telepítő, ablak-címsor). Új
> munkafolyamat: az újonnan indított elemzés azonnal fut (LIFO sor + a
> futó feldolgozás szelíd félretétele), és egy dedikált „Elemzéseim" fül
> a befejezett/befejezetlen elemzéseket szétválasztva mutatja. A
> pontosság-validáció parancssorból (offline pilot-mérés) is elérhető, egy
> friss élő félidei (szélső) jelzéssel együtt. Windows- és
> macOS-telepítővel a Releases oldalon.

### Megbízhatóság — nem veszik el munka
- **Validáció parancssorból**: `python -m scripts.validate_match
  <meccs.json> <igazsag.csv> [--out riport.html]` — a pilot-operátor
  offline (szerver nélkül) méri a felismerés pontosságát a coach
  CSV-jéhez képest; kiírja az ítéletet és go/no-go kilépőkódot ad
  (0 = MEGFELEL). (#541)
- **Új elemzés azonnal indul**: a feldolgozási sor LIFO — a legújabb kérés
  fut következőnek, nem áll be a korábbiak mögé. Ráadásul ha épp fut egy
  (korábbi) feldolgozás, azt a rendszer szelíden félreteszi (az addigi
  rész elmentődik befejezetlen elemzésként, később folytatható), és rögtön
  a most indított munkával megy tovább. (#538)

### Kliens-élmény
- **„Elemzéseim" fül — befejezett/befejezetlen szétválasztva**: a könyvtár
  fejlécében egy dedikált, mindig látható szegmens-fül (Mind · Befejezett ·
  Befejezetlen, darabszámmal) — a korábbi elemzések egy koppintással,
  külön a kész és a folytatásra/törlésre váró munkák. (#539)
- **Átnevezés: handball_client → SportMachine**: a kiadott app és
  telepítő fájlneve mostantól `SportMachine.app` (macOS) és
  `SportMachine.exe` (Windows), a macOS menüsor/Finder név és a Windows
  ablak-címsor „Sport Machine" (a MaterialApp title már az volt). A kód
  névfüggetlen (a frissítő .app-ot mintára keres, a motor a
  resolvedExecutable-ből dolgozik), ezért az auto-frissítés változatlanul
  működik. A következő kiadástól (0.1.20) él. (#537, #540)
- **Élő félidei szélső-jelzés**: a szünetben szól, ha az ellenfél szélsői
  veszélyesek voltak az első félidőben — a szélső-védő lépjen ki, szűkítse
  a szöget a másodikban. (#536)

## v0.1.19 — kiadva (2026-07-23, PR #506–#534)

> Kiadás-jegyzet: a befejezés-elemzés négy új dimenzióval bővült
> (lövés-távolság, kapu-sarok, szélső-hatékonyság, kapus gyenge sávja), az
> építkezés kettővel (passz-irány, gólpassz-forrás), a védekezés az egyéni
> labdaeladókkal és a fal-magassággal; hat friss élő félidei jelzés a
> padnak, és egy teljes, valós felvételre szabott pontosság-validációs
> eszköztár (sablon → mérés → MEGFELEL/GYENGE ítélet → megosztható riport).
> A macOS auto-frissítés App Translocation-javítása (#510) is ebben a
> kiadásban él — ezt a verziót egyszer kézzel telepítve a jövőbeli
> frissítés magától lefut. Windows- és macOS-telepítővel a Releases oldalon.

### Megbízhatóság — nem veszik el munka
- **Pontosság-validáció valós felvételen**: új `POST /matches/{id}/validate`
  végpont + `validation.validate_events` — egy edző által kitölthető kézi
  eseménylistához (gólok/lövések időbélyeggel) hasonlítja a motor kimenetét,
  és precizitás/visszahívás/F1 értéket ad típusonként. A válasz edző-
  olvasható **ítéletet** is ad (MEGFELEL/GYENGE) a cél-küszöbökhöz mérve
  (visszahívás ≥90%, precizitás ≥85%). A kézi lista CSV/TSV-ből is
  beolvasható (`truth_csv`) — mm:ss idő és magyar címkék is jók, hogy az
  edző táblázatból dolgozhasson. A `GET /matches/{id}/validate-template` a
  felismert eseményekből előtöltött CSV-sablont ad — a coach ezt JAVÍTJA
  (nem nulláról gépeli), majd visszaadja. Megosztható, nyomtatható
  HTML-riport is kérhető (`{"format":"html"}`) a pilot go/no-go döntéshez.
  Ez a piaci validáció mérőeszköze — a szimulált benchmark mellé a valós
  footage mérése. (#529–#533)
- **macOS auto-frissítés javítása**: a „Frissítés most" a Letöltésekből
  indított (karanténos) appnál csendben elbukott (App Translocation) —
  most a kanonikus /Applications mappába telepít, előre letörli a
  karantént, és naplót ír a diagnózishoz. (#510)
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
- **20. meccsterv-szabály**: az ő kapusuk gyenge a távoli lövésekre × a ti
  távoli lövés-erőtök → „élesítsétek az átlövést" (a kapus-sáv és a
  lövés-távolság rétegek párosítása). (#534)
- **Hajrá-emberek**: KI szerzi a gólokat a meccs utolsó perceiben — a
  hajrá-teljesítmény egyéni bontása (kire adjuk a labdát / kire figyeljünk
  a végén). Összefoglaló, /analyze, csomag, felderítés-profil (mezszám-
  alapú összegzés) + „a hajrában rá figyelj" kulcs + csempe. (#523)
- **Labdaeladók**: KI veszíti el a legtöbbször a labdát — a labdabiztonság
  egyéni mutatója (a labdaszerzők és a labdaeladás-zónák párja: ki veszít).
  Összefoglaló, /analyze, csomag, felderítés-profil (mezszám-alapú
  összegzés) + „rá presselj" kulcs + csempe, és a 42. edzés-szabály
  (névre szóló labdabiztonság). (#520)
- **Gólpassz-forrás**: honnan készítik elő a gólokat — szélről (beadás),
  középről (beálló/betörés) vagy a hátsó sorból (átlövő-kiadás); a
  gólpasszoló helye a passz pillanatában. Más, mint az assziszt-háló (az
  ki-kinek). Összefoglaló, /analyze, csomag, felderítés-profil
  (count-alapú) + csempe, és a 41. edzés-szabály (gól-előkészítés
  változatossága). (#519)
- **Passz-irány**: mennyire viszik előre a labdát (vertikális, penetráló
  játék) vagy oldalra/hátra (türelmes körözés) — a passzoló és a fogadó
  kapu-távolságából. Összefoglaló, /analyze, csomag, felderítés-profil
  (count-alapú) + csempe, és a 40. edzés-szabály (vertikális építkezés
  túl sok oldalpassznál). (#518)
- **Védekezési vonal magassága**: milyen mélyen (passzív 6-0) vagy magasan
  (felfutó, agresszív 3-2-1) áll a fal — a felállt védekezés átlagos
  mélysége a saját kaputól. Más, mint a védekezési nyomás (az a labdástól
  mért táv). Összefoglaló, /analyze, csomag, felderítés-profil (count-alapú)
  + csempe, és a 39. edzés-szabály (felfutó falnál mögöttes tér zárása,
  mély falnál aktív kilépés). (#517)
- **Szélső-befejezés**: a szélső (éles) szögből, közelről leadott lövések
  gólaránya — erős szélső széthúzza a védelmet, gyengére ráengedhető a
  szög. Összefoglaló, /analyze, csomag, felderítés-profil (count-alapú,
  külön a "szélső-függéstől") + csempe, és a 38. edzés-szabály
  (szélső-befejezés gyakorlása). (#516)
- **Kapu-sarok (befejezés-hely)**: a gólok a kapu melyik oldalára mennek
  (bal/közép/jobb, a lövő szemszögéből) — a gólvonal-átlépés y-jából. Ha a
  góljaik zöme egy oldalra megy, kiszámíthatóak: a kapus felkészülhet.
  Összefoglaló, /analyze, csomag, felderítés-profil (count-alapú) +
  csempe, és a 37. edzés-szabály (befejezés-változatosság). (#515)
- **Kapus védés-hatékonyság távolság szerint**: melyik lövés-sávra
  (közeli/közép/távoli) a leggyengébb a kapus — a rá kaputra érkezett
  lövések védési aránya sávonként. Összefoglaló, /analyze, csomag,
  felderítés-profil (count-alapú, "ide tereld a befejezéseket" kulcs) +
  csempe, és a 36. edzés-szabály (saját kapus gyenge sávjának célzott
  gyakorlása). (#514)
- **Lövés-távolság profil**: honnan lő és honnan gólozik a csapat —
  közeli (beálló/szélső) / közép / távoli (átlövés) sávok lövés- és
  gólszámmal, sávonkénti gólaránnyal; összefoglaló-mondat, /analyze API,
  csomag-réteg, felderítés-profil + "kifelé zárni az átlövőkre" /
  "6-ost erősíteni" kulcsok + csempe, és a 35. edzés-szabály
  (lövésválasztás gyenge távoli gólaránynál). (#511)
- **Átmenet-támadás**: a labdaszerzésből mennyi gyors gól lesz
  (konverzió + átlagidő a szerzéstől a gólig) — összefoglaló, /analyze,
  csomag, felderítés-profil + kulcs + csempe, 34. edzés-szabály
  (kontra-befejezés). (#507–#509)
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
- **Szezon-történet és egymás ellen**: a szezon-riport meccsről
  meccsre főcím-táblával nyit; új Egymás ellen riport (két csapat
  közös mérlege és meccs-listája) dashboard-gombbal. (#450–#452)
- **Meccsterv a visszavágóra**: az Egymás ellen riport előre is néz —
  a legutóbbi közös meccs profiljait keresztezi a meccsterv-motorral
  (12 szabály), és terv-listát ad A csapat szemszögéből. (#454)
- **Őrzési párok**: ki kit fogott a védekezésben — védőnként a
  leggyakoribb őrzött, idő-aránnyal és átlagtávval, 2,5 m felett laza
  őrzés jelzéssel; öt felületen (API, edzői összefoglaló,
  jelentés-tábla, app-kártya, elemzés-csomag). (#455, #456)
- **Emberfogó-profil a felderítésben**: a laza (2,5 m+) emberfogó
  gyengeség + "oda vidd az egy-egyet" kulcs és 13. meccsterv-szabály;
  a tapadó (1,5 m alatti) erősség + "csak elzárással" kulcs és a fő
  lövővel párosított 14. szabály; két új csempe; 29. edzés-szabály
  (Emberfogás-tapadás) és játékos-lap védekezés-mérleg személyes
  tippel. (#458–#460)
- **Beálló-terhelés**: új réteg — a támadások hányada megy a beállón
  át, és gólarányban megéri-e; teljes kör: összefoglaló-mondat,
  jelentés-sor, API, csomag (#461), felderítés-profil + "szendvics a
  beállóra" kulcsok + 15. meccsterv-szabály (beálló-terhelés ×
  kiállítás-hajlam) + csempe (#462), 30. edzés-szabály
  (Beálló-kapcsolat, két ággal) + játékos-lap beálló-blokk (#463),
  trend-mutató és könyvtár-összevető sor (#464), beállós gól-klipek
  (#469).
- **Félidei élő jelzések**: a szünet pillanatában szól az élő nézet —
  laza őrzésnél "szorosabb tapadást a másodikra", kihasználatlan
  beállónál "keresd a beadást"; mindkettő csak az első félidő
  kockáiból, jövőbe nézés nélkül. (#466, #467)
- **Emberfogás az exportokban**: Őrzés-oszlopok a statisztika-CSV-ben,
  "Emberfogóik" tábla a nyomtatható felderítőben (LAZA/tapadó
  címkével), Őrzés-oszlop + összesítő a szezon játékos-lapon.
  (#468, #470)
- **Betörés-folyosók**: új réteg — hol lép be a labdás ember a kapu
  9 m-es körzetébe (öt sáv, oldal-normalizálva); összefoglaló +
  "átjáróház" kiemelés, jelentés-sor, API, csomag (#471),
  felderítés-profil + 16. meccsterv-szabály (betörés-sáv × laza fal)
  + csempe (#472), 31. edzés-szabály (Sáv-védelem) + betörés-klipek
  sávval a fájlnévben (#473).
- **Passz-lánc**: új réteg — hány passzból épül a támadás, és melyik
  lánc-hossz hozza a gólokat (0–2 / 3–5 / 6+ vödrök); összefoglaló,
  jelentés-sor, API, csomag (#475), felderítés-profil + "gyors első
  hullám" / "türelmes körbejáratás" kulcsok + 17. meccsterv-szabály
  + csempe (#476), 32. edzés-szabály (két ággal) + könyvtár-összevető
  sor (#477).
- **Rotáció-mélység**: új réteg — hány emberrel megy a meccs (bevetett
  / alapember, kapus és beugrók nélkül); összefoglaló-mondat,
  jelentés-sor, /team-stats API, csomag (#478), felderítés-profil +
  szűk pad / széles pad kulcsok + 18. meccsterv-szabály (tempó-terv)
  + csempe (#479), félidei élő rotáció-jelzés ("frissíts a
  másodikra") (#480).
- **Hazai vs idegen**: a szezon-riport pályaválasztás szerinti
  mérleg-táblát kap (meccsek, Gy/D/V, gólok). (#481)
- **Labdaszerzők**: új réteg — csapatváltásos birtokos-váltásnál az új
  birtokos kapja a jóváírást; API, csomag, összefoglaló-mondat,
  játékos-lap metrika (#483), felderítés-profil + "rövid, biztos
  passz" kulcs + csempe + szerzés-klipek (#484).
- **Egyéni védekezés egy helyen**: blokk + labdaszerzés + emberfogás
  közös táblában a jelentésben (a legaktívabb négy védő, #485) és
  kivonat-kártyán az appban (#486).
- **Szezon-toplisták**: gólkirály / védés-vezér / fal kulcsa /
  labdaszerző a teljes könyvtárból, mezszám-alapú összegzéssel — új
  /library/leaders végpont + dashboard-kártya (#487), és a csapatra
  szűrve "A szezon játékosai" szakasz a szezon-riportban (#488);
  ötödik kategóriaként Gólpassz-vezér (#490).
- **Élő hajrá-protokoll**: szoros állásnál az utolsó 5 perc kezdetén
  jelzés a padnak (időkérés-terv, hetes-dobó, 7 a 6 döntés). (#491)
- **Riport-bővítések**: Ellenfél-mérleg tábla a szezon-riportban
  (#492), "Ki viszi a meccseket" gólfelelős-tábla az Egymás ellen
  riportban (#493), Betörés-sávjaik tábla a felderítőben (#495).
- **Őrzés a fejlődés-képernyőn**: szezon-chip + meccsenkénti Őrzés
  cella laza-jelzéssel a játékos-fejlődés nézetben. (#494)
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
- **Élő félidei kapu-sarok jelzés**: a szünetben szól, ha az ellenfél
  góljainak zöme egy kapuoldalra ment — a kapus erre az oldalra
  készülhet a másodikban. (#528)
- **Élő félidei labdaeladó-jelzés**: a szünetben megnevezi, ki szórta a
  legtöbb labdát az első félidőben — présre őt a másodikra, zárd a
  passzsávjait. (#527)
- **Élő félidei passz-irány jelzés**: a szünetben szól, ha az ellenfél
  nagyon vertikálisan (zárj vissza gyorsabban) vagy nagyon türelmesen (a
  beállóra figyelj) épített az első félidőben — csak az addigi kockákból,
  a marking/pivot/rotáció félidei képek mellé. (#526)
- **Kalibráció összenézet egymás mellett**: a hatpontos egészpályás
  finomhangolás a bekalibrált bal és jobb térfelet a SAJÁT képkockáján,
  egymás mellett mutatja (nem egy közösre laposítva) — a felezővonal a két
  kártya közös éle, mindkét fél külön húzható. (#512)
- **„Csak a befejezetlenek" szűrő**: a Meccs-könyvtárban egy koppintással
  előjönnek a részleges (megkezdett, de be nem fejezett) elemzések —
  folytatásra vagy törlésre; a chip mutatja a darabszámot. (#513)
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
- **Játékos-lap bővítés**: a játékos-lapra bekerül a Labdaeladás
  (labdabiztonság) és a Hajrá-gól (a meccs végén szerzett gól) mutató —
  a két új egyéni réteg most a nyomtatható lapon is. (#524)
- **Védekezés-mutatók a jelentésben**: a csapatmutató-táblába bekerül a
  védekezési vonal magassága (mély/felfutó) és a kapus gyenge lövés-sávja
  — a két új védekezés-réteg most a nyomtatható jelentésben is. (#522)
- **Befejezés-profil a meccsjelentésben**: új tábla a lövés-rétegekből —
  távolság (közeli/közép/távoli, gólaránnyal), szélső-befejezés és a
  domináns kapu-sarok, csapatonként; addig ezek csak az összefoglaló
  szövegben voltak. (#521)
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

## v0.1.18 — kiadva (2026-07-22, PR #57–#505)

> Kiadás-jegyzet: a telepítő-buildet a legfrissebb stabil Flutterre
> (3.44.7) állás három ponton is elakasztotta; mind javítva —
> védtelen fastapi-import a CI-tesztekben (#499), három kliens
> fordítási hiba (törött string literál + két duplikált metódus,
> #502), és az AppExitResponse API-elmozdulás (#504, verzió-független
> onDetach-alapú kilépés-mentésre váltva). A kiadás Windows- és
> macOS-telepítővel felkerült a Releases oldalra.

### A záró körök (a v0.1.17 → v0.1.18 lezárásig)
- **Kapus-kimozdulás**: kint álló (átemelhető) vs vonalon maradó kapus
  — réteg, edzői összefoglaló, /goalkeepers API, csomag, felderítés-
  profil + kulcsok + csempe + 19. meccsterv-szabály (kint álló kapus ×
  kontra), 33. edzés-szabály, meccsjelentés-sor, kapus- és játékos-lap.
  (#497, #498, #501, #503, #505)
- **README-frissítés**: a Hol tartunk szakasz a valós számokra (50+
  réteg, 19 meccsterv- és 32 edzés-szabály, 8 riport, 670+ teszt).
  (#500)

## v0.1.17 és korábbi
A korábbi kiadások tartalmát a Releases oldal és a PR-történet őrzi:
alap-pipeline (YOLO+ByteTrack, homográfia, pásztázás-követés),
esemény-felismerés, taktika/felderítés, figura-tervező, mezszám-OCR,
könyvtár-mentés, telepítők (Windows/macOS).
