# Változásnapló (CHANGELOG)

A Sport Machine kiadásainak emberi nyelvű összefoglalója. A részletes
történet a squash-merge-elt PR-okban él; itt a lényeg, témák szerint.

## Kiadatlan (a v0.1.24 óta)

- **Az üres panelek megmondják, miért üresek.** A statisztika-panel
  nulla felismert játékosnál is kirajzolta a fejlécet, a
  rendezés-gombokat és a két csapatnevet — alattuk semmivel; a
  meccs-elemző "Összegzés" füle pedig egyszerűen ÜRES DOBOZ volt, ha
  nem készült összefoglaló. Mindkettő ugyanaz a hiba, mint a néma
  pörgettyű: a felhasználó nem tudja eldönteni, hogy a program romlott
  el, vagy tényleg nincs adat. Mostantól közös üres-állapot mondja meg,
  mi hiányzik és MIÉRT ("A terhelés-tábla a követett játékosokból épül
  — ha nem sikerült a detektálás, nézd meg a kalibrációt"), egy
  csapatnyi hiányra pedig egysoros jelzés kerül. Őr-teszt tiltja a néma
  üres dobozt a feltételes ágakban.

- **A hibafelismerés nem téveszt fájlnévre.** A státuszkód-mintákat
  eddig puszta számként kerestük a kivétel szövegében: egy
  `match_404.mp4` útvonal vagy egy 401-et tartalmazó azonosító elég
  volt hozzá, hogy a program magabiztosan azt mondja, "a kért elem
  nincs meg". Egy ilyen véletlen találat rosszabb, mint a nyers üzenet
  — valótlant állít. Mostantól a kulcsok kontextussal keresnek ("http
  404", "404 not found", "status 404"), és a frissítés-ellenőrzés is
  ugyanezekből a nevesített listákból dolgozik (`looksLikeAccessIssue`)
  a saját kezű illesztés helyett — így a két hely nem tud széttartani.
  Őr-teszt tiltja a puszta számos kulcsot.

- **Minden jelentés megmondja, mikor készült.** Az edzőnél mappában
  állnak a nyomatok, és eddig egyetlen lapon sem volt dátum: ugyanarról
  az ellenfélről a szeptemberi és a novemberi felderítés
  megkülönböztethetetlen volt. Márpedig egy elavult felderítés rosszabb,
  mint a semmi — az edző elhiszi. Mostantól minden generált jelentés
  lábléce percre pontos készítés-bélyeget kap ("· Kelt: 2026-03-14
  09:05"); a meglévő láblécszöveg érintetlen marad, és ha egy
  jelentésnek nincs lábléce, nem nyúlunk hozzá.

- **A jelentések papíron is rendesen tördelődnek.** Hét generált
  jelentésből **ötben egyáltalán nem volt nyomtatási stílus** — azok a
  képernyős margókkal, tetszőleges tördeléssel kerültek papírra: a
  szakasz-cím árván maradt az oldal alján, a táblázat kettévágódott, a
  belső hivatkozás pedig kék aláhúzott linkként éktelenkedett. Mostantól
  minden jelentés ugyanazt a nyomtatási szabálykészletet kapja (cím a
  szakaszával együtt marad, táblázat/sor/csempe/ábra nem törik ketté,
  a horgony-linkek papíron feketék), a modern `break-*` és a régebbi
  `page-break-*` jelöléssel is — a felhasználó böngészőjét nem
  ismerjük. A két jelentés saját, hiányos nyomtatási blokkja megszűnt:
  egy hely, egy szabálykészlet.

- **Tartalomjegyzék a nyomtatható jelentésekben.** A meccsjelentés
  huszonöt-ötven szakaszig is elmegy, és papíron nincs keresés: az edző
  lapozgat, amíg megtalálja a "Hétméteresek" részt. Mostantól minden
  generált jelentés (felderítés, meccs, játékos, fejlődés, szezon,
  egymás elleni, játékos-szezon) a fejléc alatt sorszámozott
  tartalomjegyzéket kap, a szakaszokra mutató horgonyokkal — képernyőn
  kattintható, papíron a sorszám mondja meg, hányadik szakaszt keresse.
  Tizenkét szakasztól két hasábban. Négy szakasz alatt nincs jegyzék (a
  navigáció ilyenkor csak helyet venne el), és ha nincs hova beszúrni,
  a jelentés VÁLTOZATLAN marad — a jegyzék sose ronthat el egy
  jelentést.

- **A mutató-csempék végre olvashatók.** A csempék "értéke" nem szám: a
  283 csempe-mutató 371 lehetséges szövegéből **369 hosszabb 12
  karakternél** — jellemzően egész mondat ("62% elöl · területi
  nyomás"). A csempe viszont 20 pontos szám-betűvel, 150 pixeles
  dobozban rajzolta őket, így négy-öt sorba törtek: a fal ragadozott
  lett, és a szem nem találta, hol ér véget az egyik csempe. Mostantól
  a csempe az érték hosszához igazodik (rövidnél marad a nagy szám,
  mondatnál olvasható törzsméret és szélesebb doboz, három sor után
  elvágva), a CÍMKE kerül előre — a fal átfutásakor azt keresi az edző
  —, a teljes szöveg pedig a súgóbuborékban marad meg. Őr-teszt
  rögzíti a sor-korlátot, az elvágást és a súgóbuborékot.

- **Ugrás a jelentés szekciójára — tartalomjegyzék a felderítéshez.** A
  felderítő jelentés kilenc nagy kártyából áll, és képernyőkön át
  gördül; egy edző viszont a meccs előtt jellemzően EGY dolgot keres
  ("mit csinálnak hetesnél?"). Mostantól a jelentés tetején ugró-sáv
  áll: koppintásra odagördít ("Így játszanak", "Hogyan játssz
  ellenük", "Erősségek / gyengeségek", "Mutatók", "Honnan lőnek",
  "Honnan kapják a lövéseket", "Ismert figuráik", "Védekezésük",
  "Kulcsjátékosok"). A sávban csak a ténylegesen meglévő szekciók
  jelennek meg — üresbe ugró gomb rosszabb, mint a hiánya. Őr-teszt
  párosítja a csipeket a szekciókkal, hogy egy elgépelés ne adjon
  néma, semmit nem csináló gombot.

- **A várakozás megmondja, mire várunk.** Hét képernyőn néma pörgettyű
  pörgött: a felderítő jelentés több meccsen PERCEKIG fut, és közben
  semmi nem árulta el, hogy a program dolgozik-e vagy megakadt — aki
  ilyet lát, mégegyszer megnyomja a gombot, vagy kilép. Mostantól a
  várakozó nézet kiírja, MIT csinálunk ("Felderítő jelentés készül…"),
  MEDDIG szokott tartani ("több meccsnél ez percekig tart — ez
  normális"), és élő számlálóval azt is, mennyi ideje fut; fél perc
  után külön megnyugtató sort is. Őr-teszt tiltja az új néma
  pörgettyűt.

- **Hibaüzenetek emberi nyelven — a teendővel együtt.** Eddig a
  felület a nyers kivételt írta ki, például: `SocketException:
  Connection refused (OS Error: Connection refused, errno = 111),
  address = 127.0.0.1, port = 8000`. Ebből egy edző sem azt nem tudta
  meg, MI történt, sem azt, mit tegyen. Mostantól a felismert esetek
  egy mondatot kapnak a teendővel ("Nem érem el a háttérmotort. Fut a
  Sport Machine motor? A program újraindítása magától elindítja."):
  elérhetetlen motor, időtúllépés, betelt lemez, jogosultság, 404,
  401/403, 500. Amit a fordító nem ismer fel, azt VÁLTOZATLANUL adja
  vissza — jobb egy nyers üzenet, mint egy félrevezető tipp. 45
  kiírási hely tíz képernyőn; őr-teszt tiltja, hogy új nyers `$e`
  kerüljön a felületre (logikai illesztéshez jelöléssel maradhat).

- **Gyorsbillentyű-súgó mindenhonnan, egy listából.** Eddig csak a
  meccs-elemzőben létezett súgó (rejtett `?`/F1 gombra), és az
  app-szintű navigációs billentyűket (Cmd/Ctrl + 1..7) nem is
  említette — a felső sáv billentyű-ikonja pedig **kattintható
  látszatot keltett, de nem csinált semmit**. Mostantól a súgó a
  shellben él, két szekcióval ("Bárhol" · "Meccs-elemzőben"), a
  felső sáv ikonja megnyitja, és a `?`/F1 az egész alkalmazásban
  működik. A meccs-elemző ugyanezt a listát hívja — két külön lista
  előbb-utóbb széttartott volna.

## v0.1.24 — kiadva (2026-08-05)

> Kiadás-jegyzet: a v0.1.23 óta a fejlesztés három szálon futott.
> **(1) Sebesség**: a rétegek addig hívták újra ugyanazokat az
> alap-méréseket, hogy egy teljes meccs-csomag ~10 percig futott; a
> hatókörös gyorsítótár és a kocka-szintű memoizálás ezt bitre azonos
> kimenet mellett 2,4–3,2×-esére gyorsította. **(2) Poszt-lencse**: a
> posztok akkor is stabilak, ha a nevek meccsről meccsre cserélődnek,
> ezért a felkészülés gerince lett — tíz új réteg (hatékonyság,
> gólpassz-tengely, birtoklás, passzháló, átvételi zóna, labdatartás,
> eladási zóna, eladás-ár, szünet- és állás-váltás), egy közös
> Poszt-lencse szekcióval a jelentésben. **(3) Használhatóság**: a
> felderítés-képernyő 297 mérőszáma kereshető, csoportosított fallá
> lett, az edzői összefoglaló 43 mondatos bekezdése felsorolássá, a
> kezdőlap nyolc néma ikonja pedig nevesített művelet + egy menü.
>
> Külön érdemes kiemelni, ami NEM került be: egy tervezett
> poszt-lövőtávolság réteg mérése a lövő-hozzárendelés kapu-felé
> torzításán bukott volna. A réteg helyett a KORLÁT került be —
> dokumentálva, jellemző-teszttel leszögezve, és az EIC-terv TRL-4
> feladatai közé felvéve.

- **Kezdőlap: nyolc néma ikon helyett nevesített műveletek.** A
  fejlécben nyolc egyforma szürke ikon sorakozott (játékos-fejlődés,
  egymás ellen, szezon-riport, könyvtár, súgó, frissítés, újratöltés,
  rendszer-ellenőrzés) — melyik mit csinál, csak rámutatásra derült ki.
  Mostantól a három ELEMZŐ művelet felirattal látszik
  ("Játékos-fejlődés", "Egymás ellen", "Szezon-riport"), a karbantartás
  pedig egyetlen **"Továbbiak"** menübe került, olvasható tételekkel.
  A szezon-riport csapat-választása ikon mögötti legördülőből rendes
  párbeszédablak lett (üres könyvtárnál kimondja, hogy még nincs
  elemzett meccs).
- **Minden csak-ikonos gomb kapott súgóbuborékot.** Négy gombnak
  (meccs újratöltése, lejátszás/szünet a meccs- és élő nézetben,
  vissza a felderítésből és a fejlődés-nézetből) egyáltalán nem volt —
  ott a felhasználónak esélye sem volt kitalálni, mit csinál. **Új
  őr-teszt** végigmegy a kliens minden Dart-fájlján, és elbukik, ha
  tooltip nélküli `IconButton` kerül be.

- **Edzői összefoglaló: mondatokra bontva, felsorolásként.** A
  "Játékkép és tempó" szakasz a rétegekkel **4357 karakteres, 43
  mondatos EGYETLEN bekezdéssé** nőtt — minden új réteg egy mondatot
  fűzött hozzá, és a végeredményt már senki nem olvassa el. A
  `coach_summary` mostantól a szakaszok szövegét mondatokra bontva is
  átadja (`lines`); a `body` változatlan marad, tehát a meglévő
  fogyasztók nem törnek el. A tördelés megjelenítési segédlet, nem
  nyelvtani elemzés: a tizedes-pont (3.9 m/s) nem mondathatár, és a
  mondatok együtt szóról szóra kiadják a bekezdést — őr-teszt
  ellenőrzi mindkettőt. Felületek: a **meccs-jelentés** hosszú
  szakaszt felsorolásként ír ki (2 mondat alatt marad a bekezdés), az
  **appban** pedig a szakasz címe mellett ott a megállapítások száma,
  alapból az első öt mondat látszik, "Mind a N megállapítás" gombbal.

- **Felderítés-képernyő: olvashatóvá tett mutató-fal és listák.** A
  képernyő addig nőtt a rétegekkel, hogy használhatatlanná vált:
  **297 mérőszám** egyetlen tagolatlan blokkban, alatta 33 edzői kulcs
  és a teljes meccsterv, mind egyszerre. Amit egy edző keres, azt nem
  lehetett megtalálni.
  - **Mutató-fal**: mindig látható kiemelt sáv (lövés/gól, gólarány,
    labdabirtoklás, eladás, támadás-típusok, tempó, felkészülés-
    súlypont), **kereső** ("keress a mutatók közt" — a találatok
    csoportjai maguktól kinyílnak, a fejléc mutatja a találat-számot),
    és **hét lenyitható csoport** darabszámmal (Kapus, Posztok,
    Szabály és létszám, Idő/állás/forma, Védekezés, Támadás és
    befejezés, Emberek és cserék). A csoportot a címke kulcsszavai
    döntik el; **őr-teszt** vizsgálja, hogy minden csempe valódi
    csoportba esik-e — új réteg csempéje nem csúszhat csendben az
    "Egyéb" gyűjtőbe.
  - **Hosszú felsorolások** (edzői kulcsok, meccsterv): alapból az
    első hat látszik, "Mind a N megjelenítése" gombbal. A gomb
    szövege kimondja, hogy a rövidítés a jelentés SORRENDJÉBŐL vág —
    a rendszer itt nem állít fontossági rangsort, és nem is teszünk
    úgy, mintha tenne.

- **Poszt-eladási zóna** (`role_turnover_zones`): melyik posztjuk adja
  el a labdát a TÁMADÓ harmadban — vagyis kinek az eladása hív kontrát.
  A csapat-szintű eladási zónák (`turnover_zones`) azt mondják meg, a
  csapat hol veszíti el a labdát, az eladás-posztok
  (`turnovers_by_role`) azt, ki adja el; ez a kettőt köti össze. Az
  eladás-ár (`role_turnover_cost`) azt méri, mennyi gólba KERÜLT, ez
  azt, mennyire KOCKÁZATOS a hely — kevés meccsen az ár még zajos
  lehet, a zóna viszont már beszédes. Posztonként 5 eladás és 20
  százalékpont alatt nincs ítélet. Felületek:
  `/matches/{id}/attacks` + meccs-csomag (`role_turnover_zones`),
  edzői összefoglaló, meccs-jelentés Poszt-lencséje, felderítés
  (+ edzői kulcs + 262-es meccsterv-szabály), 283-as edzés-szabály
  ("Kockázatos eladási zóna"), kliens-csempe ("Poszt-eladási zóna").

- **Poszt-labdatartás** (`role_hold_time`): melyik posztnál áll meg a
  labda. A poszt-birtoklás (`role_possession_share`) az össz-időt
  osztja posztokra — ez az EGY ÉRINTÉSRE jutó időt; a kettő
  különbözik, mert egy poszt sok rövid érintéssel is vihet nagy
  össz-időt (az a labdajáratás) és kevés hosszú tartással is (az a
  megállás). A névre szóló változat (`hold_time_players`) a játékost
  nevezi meg; a poszt akkor is stabil, ha a nevek cserélődnek. Edzői
  olvasat: a hosszan tartó poszt a kettőzés célpontja — nála van idő
  odaérni, és nála lassul a támadásuk; saját oldalon ugyanez a
  gyorsabb továbbítás témája. Az érintésnyi (5 kockánál rövidebb)
  birtoklás zaj, azt nem számoljuk; posztonként 8 szakasz és 0,7 mp
  eltérés alatt nincs ítélet. A felderítésben szakasz-darabszám ÉS
  kocka-összeg tárolódik (átlag sose). Felületek:
  `/matches/{id}/attacks` + meccs-csomag (`role_hold_time`), edzői
  összefoglaló, meccs-jelentés Poszt-lencséje, felderítés (+ edzői
  kulcs + 261-es meccsterv-szabály), 282-es edzés-szabály
  ("Továbbítás-tempó"), kliens-csempe ("Poszt-labdatartás").

- **Poszt-átvételi zóna** (`role_receive_zones`): milyen messze a
  kaputól veszi át a labdát az egyes posztjuk. A poszt-passzháló
  (`role_pass_map`) azt mondja meg, ki kinek ad — ez azt, HOL kapja
  meg. **Miért az átvétel és nem a lövés:** a lövő-hozzárendelés
  kapu-felé torzít (lásd a mai bejegyzést), ezért egy lövés-távolság
  poszt-bontása ma nem lenne megbízható; az átvétel viszont pontosan
  mért — a passz-esemény kockáján a fogadó ott áll, ahol a labdát
  megkapta. Edzői olvasat: ez a fal magasságát és az elé állást
  állítja be — ha a beállójuk 6 méteren kapja a labdát, az elé állás
  már késő, a bejátszás vonalát kell testtel zárni. Posztonként 8
  átvétel és 1,5 m eltérés alatt nincs ítélet. A felderítésben
  darabszám ÉS távolság-ÖSSZEG tárolódik (átlag sose), hogy meccsek
  közt pontosan összegződjön. Felületek: `/matches/{id}/attacks` +
  meccs-csomag (`role_receive_zones`), edzői összefoglaló,
  meccs-jelentés Poszt-lencséje, felderítés (+ edzői kulcs + 260-as
  meccsterv-szabály), 281-es edzés-szabály ("Átvételi mélység"),
  kliens-csempe ("Poszt-átvételi zóna").

- **Poszt-passzháló** (`role_pass_map`): melyik vonalon jár a labda
  posztról posztra. A gólpassz-tengely (`assist_role_pairs`) csak a
  GÓLT érő passzokat nézi, a passz-hálózat a NEVEKET — ez az összes
  passzt, posztonként; a kép így sokkal sűrűbb (meccsenként több száz
  passz, gólpassz húsz körül). Edzői olvasat: a legterheltebb vonal
  az, ahol az elfogás a legvalószínűbb — oda érdemes a kezet és a
  testet tenni; ha egy vonal a passzok harmadát viszi, a
  labdajáratásuk kiszámítható. A réteg a birtokos-váltásokból dolgozik
  (nem a kapu-felé torzító lövő-hozzárendelésből). Húsz passz alatt,
  30%-os részarány alatt vagy holtversenynél nincs ítélet. Felületek:
  `/matches/{id}/attacks` + meccs-csomag (`role_pass_map`), edzői
  összefoglaló, meccs-jelentés Poszt-lencséje, felderítés
  (vonal-számlálók meccsek közt összegezve + edzői kulcs + 259-es
  meccsterv-szabály), 280-as edzés-szabály ("Passz-útvonalak
  bővítése"), kliens-csempe ("Poszt-passzháló").

- **Poszt-birtoklás** (`role_possession_share`): melyik posztnál van a
  labda a szervezett támadásaikban. A játékmester-függés és a
  tartás-idők a NEVEKET nézik — ez a posztot, ami akkor is stabil, ha
  a nevek meccsről meccsre cserélődnek. Edzői olvasat: ha a labda
  idejének több mint felét egyetlen poszt tartja, a letámadás
  címzettje adott, és a játékuk megakad; ha megoszlik, a nyomás nem
  térül meg, inkább a falat kell rendezni. **Lényeges: ez a réteg nem
  a lövő-hozzárendelésből dolgozik** (amely kapu-felé torzít), hanem a
  kockánkénti birtoklásból — a poszt-bontása közvetlenül mérhető.
  250 labdás kocka és 55%-os részarány alatt nincs ítélet. Felületek:
  `/matches/{id}/attacks` + meccs-csomag (`role_possession_share`),
  edzői összefoglaló, meccs-jelentés Poszt-lencséje, felderítés
  (poszt-bontású kocka-számlálók meccsek közt összegezve + edzői kulcs
  + 258-as meccsterv-szabály), 279-es edzés-szabály
  ("Labdatartás-megosztás"), kliens-csempe ("Poszt-birtoklás").

- **Mért, dokumentált korlát: a lövő-hozzárendelés kapu-felé
  torzítása.** A lövés-eseményt a labda kapu-megközelítésekor jelöljük
  (nem az elengedéskor), ezért a visszakeresési ablakban a labda már a
  kapu közelében jár — a távolról elengedett lövések így a kapuhoz
  közeli játékoshoz kerülnek. Ellenőrzésben 12 méterről elengedett
  lövések **mind** a 6 méteren álló játékoshoz kerültek. Ez a
  csapat-szintű számokat nem érinti, a játékos- és poszt-bontású
  lövés-rétegeket viszont igen. A korlát mostantól ki van mondva a
  `_shooter_before` docstringjében és az EIC-terv TRL-4 feladatai
  közt; javítása az elengedés-pillanat külön felismerését igényli, és
  a valós-videós validáció kiemelt tétele. (Emiatt egy tervezett
  poszt-lövőtávolság réteg NEM került be — a mérése ezen a torzításon
  bukott volna.) **Jellemző-teszt** rögzíti a jelenlegi viselkedést:
  ha valaki bevezeti az elengedés-pillanat felismerését, a teszt
  elbukik, és a hozzá tartozó dokumentációt is frissíteni kell.

- **A README száma is a szinkron alá került**: a nyitólap "Minőség"
  sora 1103 automata tesztet állított, miközben a valóság 1246 — épp
  az a szám volt elavult, amit egy érdeklődő először meglát. A
  `project_facts` mostantól a README-t is igazítja, az őr-teszt pedig
  ellenőrzi; a receptből így kikerült a "kiadáskor elég frissíteni"
  kézi lépés.

- **Az angol felderítő kártya poszt-alapú tényekkel bővült**: a
  leggyengébb befejező poszt (mit érdemes rájuk engedni) és a
  gólpassz-tengely angolul is megjelenik. A posztok angol néven
  szerepelnek (beálló → pivot, szélső → wing, átlövő → back, irányító
  → centre back) — egy angol brief ne magyarul nevezze meg a
  beállót; ismeretlen posztot változatlanul hagyunk. Küszöbök
  modul-szintű konstansban, a magyar felülettel azonos elven: kevés
  mintánál a sor egyszerűen kimarad.

- **Poszt-lencse**: a poszt-alapú rétegek egy helyen. A posztok akkor
  is stabilak, ha a nevek meccsről meccsre cserélődnek — ezért ez a
  lencse a felkészülés gerince. A meccs-jelentés új "Poszt-lencse"
  szekciója egy táblában hozza a megszólaló poszt-ítéleteket
  (gól-posztok, poszt-hatékonyság, gólpassz-tengely, eladás-ár
  posztonként, poszt-váltás a szünetre, poszt-állás); ha egyik réteg
  sem szólal meg, a szekció el sem készül. Három poszt-réteg mostantól
  kimondott `verdict` mezőt is ad (a kódbázis konvenciója szerint),
  így hárman bekerültek a **teendő-rangsorba** is: az eladás-ár az
  **ár**-családba (a hiba már gólban meg van fizetve), a szünet-váltás
  a **szünet**-, a poszt-állás pedig az **állás**-családba.

- **Poszt-állás** (`role_share_by_score`): melyik poszton keresztül
  fejeznek be HÁTRÁNYBAN. A poszt-váltás a szünetre
  (`role_share_shift`) az idő szerinti átrendeződést nézi — ez az
  eredményjelző szerintit: minden gólnál megnézzük az addigi állást,
  és a poszthoz kötött gólok megoszlását hátrányban, illetve minden
  más helyzetben. Edzői olvasat: feltételes, de nagyon konkrét — ha
  hátrányban mindent az átlövőikre bíznak, a szoros hajrában a 9
  méteres vonalat kell lezárni és vállalni a beállót; saját oldalon
  ugyanez a kérdés, hogy nyomás alatt szűkül-e a befejezésünk egyetlen
  posztra. Oldalanként 4 gól és 20 százalékpont alatt nincs ítélet.
  Felületek: `/matches/{id}/attacks` + meccs-csomag
  (`role_share_by_score`), edzői összefoglaló, felderítés
  (állás-bontású poszt-számlálók meccsek közt összegezve + edzői kulcs
  + 257-es meccsterv-szabály), 278-as edzés-szabály
  ("Hátrány-befejezés"), kliens-csempe ("Hátrány-befejezés").

- **Eladás-ár poszt szerint** (`role_turnover_cost`): melyik posztjuk
  eladása kerül gólba. Az eladás-posztok (`turnovers_by_role`) azt
  mondják meg, melyik poszt ADJA el a labdát, a csapat-szintű
  eladás-büntetés (`turnover_punishment`) azt, mennyibe kerül
  összesen — ez a kettőt köti össze: melyik POSZT eladása után esik a
  leggyakrabban fél percen belüli kapott gól. Edzői olvasat: ez a
  legdrágább információ, mert már gólban meg van fizetve — azt a
  posztot kell letámadni, ahol az eladás bizonyítottan büntetést ér;
  saját oldalon ugyanez a poszt visszarendeződését (váltás-sprint)
  írja elő. Posztonként 4 eladás és 35%-os büntetett arány alatt
  nincs ítélet. Felületek: `/matches/{id}/attacks` + meccs-csomag
  (`role_turnover_cost`), edzői összefoglaló, felderítés (poszt-bontású
  eladás/büntetett darabszámok meccsek közt összegezve + edzői kulcs +
  256-os meccsterv-szabály), 277-es edzés-szabály ("Eladás utáni
  visszarendeződés"), kliens-csempe ("Eladás-ár posztonként").

- **Poszt-váltás a szünetre** (`role_share_shift`): melyik posztra
  épül a befejezésük a második félidőben. A poszt szerinti
  gólmegoszlás (`goals_by_role`) az egész meccset nézi — de az edző a
  szünetben átrendezi a támadást; ez a réteg a félidő előtti és utáni
  gólok poszt-megoszlását veti össze, és megnevezi a legtöbbet mozduló
  posztot. Edzői olvasat: ez a meccs közbeni döntést írja felül — ha
  tudjuk, hogy a szünet után a beállójukra állnak rá, a beálló-őrzést
  már a félidőben meg kell erősíteni, nem a második kapott gól után.
  Felismert félidő nélkül, félidőnként 4 gól alatt vagy 20
  százalékpontnál kisebb elmozdulásnál nincs ítélet. Felületek:
  `/matches/{id}/attacks` + meccs-csomag (`role_share_shift`), edzői
  összefoglaló, felderítés (félidőnkénti poszt-számlálók meccsek közt
  összegezve + edzői kulcs + 255-ös meccsterv-szabály), 276-os
  edzés-szabály ("Félidei átrendezés"), kliens-csempe
  ("Poszt-váltás a szünetre").

- **Gólpassz-tengely** (`assist_role_pairs`): melyik poszt melyik
  posztnak adja a gólpasszt (pl. "irányító → beálló"). A
  gólpassz-posztok (`assists_by_role`) azt mondják meg, melyik poszt
  OSZTJA a gólpasszokat, a poszt szerinti gólmegoszlás
  (`goals_by_role`) azt, melyik poszt LŐ — ez a kettőt köti össze. A
  neveket használó gólpassz-hálózattal szemben akkor is látszik, ha a
  játékosok meccsről meccsre cserélődnek. Edzői olvasat: egyetlen,
  kiosztható feladat — a domináns tengelyt kell elvágni, nem két
  embert külön fogni. Négy poszthoz kötött pár alatt, 40% részarány
  alatt vagy holtversenynél nincs ítélet. Felületek:
  `/matches/{id}/attacks` + meccs-csomag (`assist_role_pairs`), edzői
  összefoglaló, felderítés (tengely-számlálók meccsek közt összegezve
  + edzői kulcs + 254-es meccsterv-szabály), 275-ös edzés-szabály
  ("Tengely-bővítés"), kliens-csempe ("Gólpassz-tengely").

- **Poszt-hatékonyság** (`shot_efficiency_by_role`): melyik posztról
  hány százalék megy be. A poszt szerinti gólmegoszlás
  (`goals_by_role`) azt mondja meg, honnan JÖNNEK a góljaik — de egy
  poszt attól is termelhet sok gólt, hogy sokat lő. Ez a réteg a
  poszt lövéseit és góljait együtt nézi. Edzői olvasat: ez fordítja
  meg a védekezési logikát — a csapat-átlagnál sokkal rosszabb
  posztra rá lehet engedni a lövést, a sokkal jobbat viszont el kell
  zárni, vállalva, hogy máshonnan lőnek ("hova tereld"). Posztonként
  5 lövés alatt és 15 százalékpontnál kisebb eltérésnél nincs ítélet.
  Felületek: `/matches/{id}/attacks` + meccs-csomag
  (`shot_efficiency_by_role`), edzői összefoglaló, felderítés
  (poszt-bontású lövés/gól darabszámok meccsek közt összegezve +
  edzői kulcs + 253-as meccsterv-szabály), 274-es edzés-szabály
  ("Poszt-befejezés"), kliens-csempe ("Poszt-hatékonyság").

- **Validáció: eltérés-lista a pontosság-mérés mellé.** A
  precision/recall szám megmondja, MENNYIRE pontos a felismerés — de
  nem azt, hol kell javítani. A `validate_events` mostantól tételesen
  visszaadja a **kimaradt** (a kézi listában van, a motor nem látta)
  és a **téves** (a motor jelezte, a kézi listában nincs) eseményeket,
  a `mismatch_lines` pedig idő szerinti, magyar mondatokká fordítja
  ("1:05 — kimaradt gól (hazai)"). Így a validáció munkaeszköz lesz:
  az annotáló végig tud menni a felvételen a felsorolt időpontokon.
  Felületek: `python -m scripts.validate_match` kimenete ("Mit nézz
  meg a felvételen") és a HTML-riport új szekciója; hibátlan futásnál
  a riport kimondja, hogy nincs eltérés. Hosszú lista levágva, a
  levágott darabszám kiírva.

- **A pályázati számokat őr-teszt tartja frissen**: az EIC-anyagok
  (executive summary, Part B, pitch deck, felkészülési terv) és az
  útiterv szövegében is szerepel a réteg- és teszt-szám — ezek eddig
  csendben elavultak minden réteg-commit után, pedig épp ezeket
  ellenőrzi az értékelő. Az új őr összeveti a dokumentumokban ÍRT
  számokat a generált `docs/SZAMOK.md`-vel, és eltérésnél elbukik. A
  meglévő számok frissítve, az útiterv állapot-összefoglalója pedig a
  valós számra javítva (114 helyett). Hogy ez ne legyen kézi munka
  minden réteg-commitnál, a `scripts/project_facts` mostantól a
  doksikba írt számokat is ÁTÍRJA a mérvadó értékre (a `--check` mód
  pedig jelzi, ha elavultak).

- **Angol felderítő kártya** (`scouting_cards_en`): a magyar felderítő
  jelentés a teljes mélység — ez a nemzetközi felület. Csapatonként
  rövid, tényszerű angol pontok az ellenfélről: támadó stílus
  (átmenet-arány, átlagos támadás-hossz), fő védekezési forma,
  befejezés-hatékonyság, helyzetminőség (gól − xG), mit engednek
  (szabad lövések aránya), labdabiztonság (eladások a támadó
  harmadban), labdabirtoklás, és a betörés utáni kiosztás célpontja.
  Csak a MEGÁLLAPÍTHATÓ tények kerülnek bele: amihez kevés a minta,
  az kimarad — üres meccsen a kártya néma. Felületek:
  `/matches/{id}/attacks` + meccs-csomag (`scouting_cards_en`), és a
  meccs-jelentés új "Scouting card (EN)" szekciója az angol
  meccs-kártya után.

- **Sorrend-érzékenység mérése** (`scripts/order_sensitivity` →
  `docs/SORREND_FUGGES.md`): a kapus-jelölés (`detect_goalkeepers`)
  beleír a meccsbe, és több réteg a szerepből dolgozik — emiatt egy
  réteg MÁS számot adhat friss meccsen, mint azután, hogy egy korábbi
  réteg már megjelölte a kapusokat. A szkript rétegenként két friss,
  azonos magból generált meccsen összeveti a két sorrendet, és kiírja,
  melyik réteget érinti. **Mérés (240 mp-es szimulált meccs): 299
  rétegből 38 sorrend-függő** (a kettőzés-, blokk-, fal-magasság- és
  emberfogás-családban a legtöbb). A szkript nem javít semmit — a
  lista a döntés alapja, hol érdemes kimondott, determinisztikus
  szerep-jelöléssel indítani. Új teszt-fájl
  (`tests/test_order_sensitivity.py`, 4 teszt), köztük egy, amely
  rögzíti, hogy a jelenség valós, nem a mérőeszköz hibája.

- **Kiosztás-célpont** (`kickout_targets`): ha a betörés nem lövéssel
  zárul, KIHEZ kerül a labda. Az áttörő emberek azt mondják meg, ki
  viszi be a labdát a falba, a visszahozás-arány azt, lezárják-e a
  betörést — ez azt, hova megy a kiosztás: minden betörés-epizód után
  megnézzük, ad-e a betörő 3 mp-en belül passzt, és ki a fogadó.
  Edzői olvasat: ez a legkonkrétabban kiosztható feladat — ha a labda
  mindig ugyanahhoz az emberhez megy (55% fölött), az ő védője előre
  elmozdulhat a passzsávba, és a betörésre indulhat a kettőzés; ha
  változatos a célpont, passz-olvasásra nem lehet védekezést építeni,
  magát a betörést kell megállítani. Négy kiosztás alatt nincs ítélet.
  Felületek: `/matches/{id}/attacks` + meccs-csomag
  (`kickout_targets`), edzői összefoglaló, felderítés (mezszám
  szerinti célpont-számláló meccsek közt összegezve + edzői kulcs +
  252-es meccsterv-szabály), 273-as edzés-szabály
  ("Kiosztás-variálás"), kliens-csempe ("Kiosztás-célpont").

- **Hatókörös elsődleges gyorsítótár** (`pipeline/primitive_cache`): a
  rétegek szándékosan önállóak, ezért ugyanazt az alap-mérést újra és
  újra elvégezték — egyetlen edzői összefoglaló futása alatt a
  lövés-felismerés négyszáznál is többször futott le ugyanarra a
  meccsre. Mostantól a nagy összeállítások (edzői összefoglaló,
  edzés-fókusz, teendő-rangsor, felderítő jelentés, meccs-jelentés,
  támadás-végpont, teljes meccs-csomag) egy kimondott hatókörben futnak, amelyen belül az alap-mérések
  (lövés- és eseményfelismerés, birtoklás-váltások, támadás-szakaszok,
  támadás-típusok, poszt-becslés, létszám-idővonal, játékos-statisztika,
  üres-kapus szakaszok, félidő-keresés) meccsenként egyszer futnak le.
  **Az eredmény bitre változatlan** — a hatókör csak kevesebbszer
  számol: mért gyorsulás egy 5 perces meccsen 2,4–2,7× (jelentés +
  összefoglaló + edzés-fókusz + rangsor: 97 mp → 37 mp; felderítő
  jelentés: 14 mp → 6,5 mp). Biztonsági
  elvek: a hatókör a meccs objektumhoz kötött és a blokk végén
  nyomtalanul eltűnik (nincs hosszú életű, elavuló tár); minden kiadott
  érték friss másolat, így egy réteg jelölése (pl. a gólpassz beírása)
  nem szivárog a következőbe; a kapus-szerep jelölése pedig a
  gyorsítótár-kulcs része, tehát amikor a jelölés megváltozik, a
  szerepből dolgozó mérések újraszámolnak. A legforróbb, KOCKÁNKÉNTI
  mérések (birtokos játékos, birtokló csapat, játékfázis) is a
  hatókörben memoizálódnak — ezek egy nagy összeállítás alatt
  milliószor futottak le ugyanazokra a kockákra; a bejegyzés magát a
  kockát is fogja, így ideiglenes kockák sem keverhetők össze vele.
  Új teszt-fájl (`tests/test_primitive_cache.py`, 12 teszt) rögzíti
  mindezt.

- **Teendő-rangsor** (`priority_findings`, új `pipeline/priorities`
  modul): a megszólaló ítéleteket összegyűjti a rangsorba vont
  rétegekből, és kimondott edzői elv szerint rendezi — **ár → ember →
  szünet → fáradás → állás** (a hiba megfizetett ára a legdrágább
  információ, a néven nevezett minta a legkönnyebben kiosztható
  feladat, a szünet-váltás felülírja a meccs közbeni döntést, a
  fáradás az utolsó húsz percet tervezi, az állás-függő minta pedig
  feltételes). Nem újabb mérés: háromszáz rétegből öt döntés. Ha
  semmi nem szólal meg, üres marad — nem találgat. Felületek:
  `/analyze` + meccs-csomag (`priority_findings`), edzői összefoglaló
  (a rangsor élével), meccs-jelentés új "Teendő-rangsor" szekciója a
  szabály-blokk elején, felderítés (családonkénti jelzés-számok
  meccsek közt összegezve + edzői kulcs + 251-es meccsterv-szabály),
  edzés-fókusz (272-es szabály: heti súlypont), kliens-csempe.
- **Befejező-váltás** (`finisher_rotation`): hányszor lő ugyanaz az
  ember kétszer egymás után (a kimenetel mindegy — a védekezés a lövő
  személyére áll rá). Hat mezőnyjátékosnál a véletlen ismétlődés ~17%,
  ezért a 35% feletti már tudatos minta, a 10% alatti jó rotáció.
  Edzői olvasat: a sorozat-befejezőjükre a következő támadásban is
  számítani kell (korai kilépés, kettőzés); a saját oldalon a
  befejezés-rotáció a téma. Felületek: `/analyze` + meccs-csomag
  (`finisher_rotation`), edzői összefoglaló, felderítés (edzői kulcs
  két iránnyal + 250-es meccsterv-szabály), edzés-fókusz (271-es
  szabály), kliens-csempe.
- **Generált tény-lap** (`docs/SZAMOK.md`) + `scripts/project_facts`:
  a hivatkozható projekt-számok (elemző rétegek, automata tesztek,
  meccsterv- és edzés-szabályok, kliens-csempék, pipeline-modulok) a
  kódbázisból, statikusan számolva — a pályázati és bemutató anyagok
  ide hivatkoznak az állításaikkal. Új őr-teszt nem engedi elavulni
  (`--check` mód), és a recept (CLAUDE.md) is előírja a
  regenerálást. A pályázati doksik elavult darabszámai frissítve.
- **Őr-teszt: csempe-helper hivatkozás-teljesség** — minden
  felderítés-csempében hivatkozott Dart-helpernek deklarálva is kell
  lennie; a hiányzó helper eddig csak a Flutter-buildnél bukott volna
  ki, mostantól a pytest fogja meg.
- **Gól-minta** (`goal_patterns`): a gólok tér-ujjlenyomata
  (oldal-sáv × lövéstáv, pl. "bal-távoli") — ha a gólok nagy része
  ugyanabból a mintából jön, egyetlen fal-igazítás elzárja a fő
  forrást. Edzői olvasat: ne általában védekezz jobban, azt az egy
  képet fogd meg; a saját oldalon a befejezés-szórás a téma.
  Felületek: `/analyze` + meccs-csomag (`goal_patterns`), edzői
  összefoglaló, felderítés (minta-szótár meccsek közt összegezve +
  edzői kulcs + 249-es meccsterv-szabály), edzés-fókusz (270-es
  szabály), kliens-csempe.
- **Kettős emberhátrány** (`double_shorthand`): a legfeljebb négy
  mezőnyjátékossal játszott szakaszok mérlege (idő + kapott gólok),
  két iránnyal: "végzetes nekik" / "túlélik". Edzői olvasat: akinél
  gólesőt hoz, ott a második kiállítás kiprovokálása fegyver; a saját
  oldalon a 4 fős fal és az időhúzó labdatartás a téma. Felületek:
  `/analyze` + meccs-csomag (`double_shorthand`), edzői összefoglaló,
  felderítés (edzői kulcs két iránnyal + 248-as meccsterv-szabály:
  végzetes kettős hátrányuk × hetes/kiállítás-kiharcolásotok),
  edzés-fókusz (269-es szabály), kliens-csempe.
- **Létszám-hiba** (`excess_players`): a csere-átfedésből pályán lévő
  hetedik mezőnyjátékos felismerése (a kiállítás-felismerés
  többlet-oldali párja). Edzői olvasat: az átfedő cseréjű ellenfél
  váltás-pillanata kettős célpont (zsűri-jelzés + gyors labda a
  rendezetlenségbe); a saját oldalon a cserefolyosó-fegyelem a téma.
  Felületek: `/analyze` + meccs-csomag (`excess_players`), edzői
  összefoglaló, felderítés (edzői kulcs + 247-es meccsterv-szabály:
  csere-átfedésük × gyors újraindításotok), edzés-fókusz (268-as
  szabály), kliens-csempe.
- **Meccs-jelentés: Match card (EN) szekció** — az angol meccs-kártya
  (eredménysor + tényszerű angol mondatok) megjelenik a
  HTML-jelentésben is, nemzetközi megosztáshoz.
- **Angol meccs-kártya** (`match_card_en`, új `pipeline/summary_en`
  modul): tömör, ítélet-mentes angol összefoglaló a meccsről
  (eredmény, félidő, gólfelelősök, hatékonyság, leghosszabb sorozat,
  hetesek, kiállítások) — a nemzetközi felület első lépése (EU-s
  pilotok, bemutatók, EIC-értékelők); ami nem állapítható meg, azt a
  kártya kihagyja, nem találgatja. Felület: `/analyze` + meccs-csomag.
- **Meccs-jelentés: Ember-lencse szekció** — a HTML-jelentésben új
  táblázat gyűjti egy helyre a néven nevezett játékos-minták
  megszólaló ítéleteit (tüzes kéz, aszály-törő, hajrá-birtokló,
  eltűnő ember, eltűnő védő, felzárkózás-húzó), csapatonként.
- **Felzárkózás-húzó** (`comeback_carriers`): játékosonkénti
  gól-részvétel aszerint, hogy a csapat épp hátrányban volt-e — kin
  keresztül jönnek vissza. Edzői olvasat: vezetésnél a mentőember
  kivétele a játékból (szoros fogás, korai kettőzés) a hátrányukat
  beragasztja; a saját oldalon a hátrány-teher szétosztása a téma.
  Felületek: `/analyze` + meccs-csomag (`comeback_carriers`), edzői
  összefoglaló, felderítés (játékosonkénti lista meccsek közt
  összegezve + edzői kulcs + 246-os meccsterv-szabály), edzés-fókusz
  (267-es szabály), kliens-csempe.
- **Eltűnő védő** (`fading_defenders`): játékosonkénti védő-akciók
  (labdaszerzés + blokk) félidőnként — az eltűnő ember védő-oldali
  párja: kinek a zónája nyílik ki a hajrára. Edzői olvasat: a második
  félidőben a kifulladó védő-motor zónáján át kell támadni; a saját
  oldalon a védő-rotáció (szünet körüli pihenő-blokk) a téma.
  Felületek: `/analyze` + meccs-csomag (`fading_defenders`), edzői
  összefoglaló, felderítés (játékosonkénti lista meccsek közt
  összegezve + edzői kulcs + 245-ös meccsterv-szabály), edzés-fókusz
  (266-os szabály), kliens-csempe.
- **Sprint-állás** (`sprints_by_score`): a sprint-ütem (sprint/perc)
  az eredményjelző szerint — a hátrányban megugró ütem a menekülő
  futás: a hajrára elfogyó energia leggyorsabb útja, a fáradás-rétegek
  korai előjele. Edzői olvasat: ellene a vezetés járatása duplán
  kifizetődő; a saját oldalon az ütemtartó felzárkózás a téma.
  Felületek: `/analyze` + meccs-csomag (`sprints_by_score`), edzői
  összefoglaló, felderítés (edzői kulcs + 244-es meccsterv-szabály:
  menekülő sprintjeik × vezetés-járatásotok), edzés-fókusz (265-ös
  szabály), kliens-csempe.
- **Réteg-katalógus** (`docs/RETEG_KATALOGUS.md`, generált): a
  meccs-csomag mind a 289 regisztrált rétege modulonként, a
  réteg-függvény docstringjének első sorával (az álnevek a lambda
  hívását követve feloldva). Generátor:
  `python -m scripts.layer_catalog` (`--check` móddal); új őr-teszt
  tartja szinkronban a kóddal. A pályázati "N elemző réteg" állítás
  ellenőrizhető alátámasztása.
- **Versenytárs-tábla** (`docs/VERSENYTARS_TABLA.md`): kvalitatív
  összevetés (Veo, Hudl, Spiideo, Catapult vs SportMachine) a pitch
  deck 7. diájához — szerkezeti különbségek (hardver, felhő,
  szabály-értés, magyarázhatóság, elemzői munkaigény) és a védhető
  pozicionálás egy mondatban.
- **Pályázati csomag: költségterv- és pitch deck-vázlat**: 24 hónapos,
  500 k€ grantra (~714 k€ összköltségre) méretezett költségterv-vázlat
  munkacsomag-bontással és önerő-forrásokkal
  (`docs/KOLTSEGTERV_VAZLAT.md`), valamint 10 diás pitch deck-vázlat +
  3 perces videó-forgatókönyv (`docs/PITCH_DECK_VAZLAT.md`); a README
  pályázat-szakasza a teljes anyag-listára mutat.
- **Pályázati csomag bővítése**: Part B angol vázlat munkacsomagokkal
  és KPI-kkal (`docs/PART_B_VAZLAT_EN.md`), kétnyelvű pilot
  LOI-sablon (`docs/LOI_SABLON.md`), annotációs útmutató a valós
  meccses pontosság-méréshez (`docs/ANNOTACIOS_UTMUTATO.md`) + a
  `scripts/validate_match` új `--sablon` módja (előtöltött annotációs
  CSV-t ír a motor felismeréseiből). A terv rögzíti a cél-beadást
  (2027. május 5-től) és a cél-keretet (500 k€ grant-plafon, ~714 k€
  összköltség; az 1 M€ feletti igény az Accelerator-lépcső), a
  visszafelé ütemezett mérföldkövekkel.
- **Mérési jegyzőkönyv (TRL-4 evidencia-napló)**: új
  `docs/MERESI_JEGYZOKONYV.md` napló + `validation_ledger_row` a
  validációs modulban + `--jegyzokonyv` kapcsoló a
  `scripts/validate_match`-ben — minden valós meccsen futtatott
  pontosság-mérés dátumozott, git-verziózott Markdown-sorként
  gyűlik, verziók közt összevethetően. A pályázati felkészülés
  (`docs/PALYAZAT_EIC_PRE_ACCELERATOR.md` 4. pont) kulcs-eszköze.
- **EIC Pre-accelerator felkészülési csomag**: új pályázati terv
  (`docs/PALYAZAT_EIC_PRE_ACCELERATOR.md`) a widening-országos EIC
  Pre-accelerator programra (300–500 k€, 70% ráta, TRL 4→6) —
  jogosultsági ellenőrzőlista, TRL-önértékelés bizonyíték-térképpel,
  Excellence/Impact/Implementation sztori, 2 éves projektváz és
  akcióterv; hozzá angol projekt-összefoglaló
  (`docs/EXECUTIVE_SUMMARY_EN.md`), kereszt-hivatkozás az EIC
  Accelerator-tervből és README-mutató.
- **Eltűnő ember** (`fading_scorers`): játékosonkénti gól-részvétel
  (gól + gólpassz) félidőnként — akinél az első félidei termelés a
  másodikra elhal, azt az első 30 percben kell megfogni. Edzői
  olvasat: friss őrzővel dupla figyelem az elején; a saját oldalon
  terhelés-menedzsment. Felületek: `/analyze` + meccs-csomag
  (`fading_scorers`), edzői összefoglaló, felderítés (játékosonkénti
  lista meccsek közt összegezve + edzői kulcs + 243-as
  meccsterv-szabály), edzés-fókusz (264-es szabály), kliens-csempe.
- **Fekete ötperc** (`black_window`): öt perces ablakonként a dobott
  és kapott gólok, a legrosszabb ablak ítélettel — a felderítésben az
  ablak-darabszámok meccsek közt összegződnek, így a visszatérő fekete
  ötperc is kirajzolódik. Edzői olvasat: az ellenfél fekete ötpercére
  időzített nyomás (friss sor, letámadás); a saját oldalra tervezett
  csere-blokk és időkérés-készenlét. Felületek: `/analyze` +
  meccs-csomag (`black_window`), edzői összefoglaló, felderítés (edzői
  kulcs + 242-es meccsterv-szabály: az ő fekete ötpercük × a ti
  arany-ablakotok), edzés-fókusz (263-as szabály), kliens-csempe.
- **Oldal-váltás a szünetre** (`attack_side_shift`): félidőnként a
  támadójáték fő oldala (bal/közép/jobb, a támadás iránya szerint
  normálva) — aki a szünet után szárnyat vált, annál a beállított
  fal-súlypont a 2. félidőben rossz oldalon áll. Edzői olvasat: a
  szünet utáni első öt percben újra kell olvasni a súlypontot, az erős
  védő és a kettőzés kerüljön át; a saját oldalon tudatos fegyver.
  Felületek: `/analyze` + meccs-csomag (`attack_side_shift`), edzői
  összefoglaló, felderítés (edzői kulcs + 241-es meccsterv-szabály),
  edzés-fókusz (262-es szabály, tükör-oldalra), kliens-csempe.
- **Meccs-jelentés: Szünet-lencse szekció** — a HTML-jelentésben új
  táblázat mutatja, mi változik a két félidő között: a támadás-mix
  átrendeződés (szünet-váltás) és a védekezési fal-váltás megszólaló
  ítéletei, csapatonként.
- **Fal-váltás a szünetre** (`defense_form_shift`): félidőnként a fő
  védekezési forma (a védekezett támadások uralkodó címkéje) — aki a
  szünet után falat vált (pl. 6-0 → 5-1), az ellen a támadó-tervet is
  váltani kell. Edzői olvasat: két kész figurasorral kell érkezni, a
  szünet utáni első támadásnál hangos forma-bemondás; a saját oldalon
  a felismerés-rutin a téma. Felületek: `/analyze` + meccs-csomag
  (`defense_form_shift`), edzői összefoglaló, felderítés (edzői kulcs
  + 240-es meccsterv-szabály), edzés-fókusz (261-es szabály,
  tükör-oldalra), kliens-csempe.
- **Meccs-jelentés: Lendület-lencse szekció** — a HTML-jelentésben új
  táblázat gyűjti egy helyre a sorozat- és hajrá-rétegek megszólaló
  ítéleteit (vezetés-őrzés, szoros meccs, félidei fordítás, gól-aszály,
  hajrá-lövésminőség, hajrá-hibák, félidő-rajt, kapus-sorozat,
  kapus-hullámvölgy, hiba-sorozat), csapatonként.
- **Meccs-jelentés: Ár-lencse szekció** — a HTML-jelentésben új
  táblázat gyűjti egy helyre a "megfizetett ár" rétegek megszólaló
  ítéleteit (eladott labda, kihagyás, kihagyás-büntetés, csere-lyuk,
  kettőzés, kilépés, indítás-hiba és elhúzódó támadás ára),
  csapatonként.
- **Meccs-jelentés: Fáradás-kép szekció** — a HTML-jelentésben új
  táblázat gyűjti egy helyre a félidők közti trend-rétegek megszólaló
  ítéleteit (tempó-, lövőerő-, lövéstáv-, kontra-, gólpassz-,
  lepattanó-, befejezés-esés, fal-fáradás, kapus-forma, fegyelem-,
  hetes-, hiba-, nyomás- és térfél-esés), csapatonként.
- **Meccs-jelentés: Állás-lencse szekció** — a HTML-jelentésben új
  táblázat gyűjti egy helyre az eredményjelző szerinti rétegek
  megszólaló ítéleteit (hiba-, kontra-, fegyelem-, hetes-, 7a6-,
  passz-irány- és passz-hossz-állás), csapatonként.
- **Passz-hossz-állás** (`pass_length_by_score`): a hosszú (10 m
  feletti) passzok részaránya az eredményjelző szerint — a hátrányban
  megugró hosszú-passz arány kapkodó átdobálás, elfogható labdákkal.
  Edzői olvasat: a vezető csapat üljön a passzsávokra; a saját oldalon
  a hátrányban is rövid, biztos kombináció a téma. Felületek:
  `/analyze` + meccs-csomag (`pass_length_by_score`), edzői
  összefoglaló, felderítés (edzői kulcs + 239-es meccsterv-szabály),
  edzés-fókusz (260-as szabály), kliens-csempe.
- **Kapus-gólpassz** (`gk_assists`): hány gól indul közvetlenül a
  kapus kezéből (a gólhoz bekönyvelt assziszt a kapusé) — a
  leggyorsabb gól a kézilabdában. Edzői olvasat: ellene a lövés
  pillanatában kell hátraindulni, az első hazafutó a kapus-passz
  sávját vágja el; a saját oldalon a kapus hosszú keze tudatos
  fegyver. Felületek: `/analyze` + meccs-csomag (`gk_assists`), edzői
  összefoglaló, felderítés (edzői kulcs + 238-as meccsterv-szabály),
  edzés-fókusz (259-es szabály, tükör-oldalra), kliens-csempe.
- **Passz-irány-állás** (`pass_direction_by_score`): a passz-irányok
  az eredményjelző szerint — az előnyben megugró hátrajáratás tudatos
  időölés (és letámadható minta), a hátrányban erőltetett előre-passz
  kapkodás. Edzői olvasat: a vezető, hátrajáratós csapatra magas
  letámadás (az első hátrapassz a jel); a saját oldalon a
  vezetés-játék tudatosítása. Felületek: `/analyze` + meccs-csomag
  (`pass_direction_by_score`), edzői összefoglaló, felderítés (edzői
  kulcs + 237-es meccsterv-szabály), edzés-fókusz (258-as szabály),
  kliens-csempe.
- **Szünet-váltás** (`attack_mix_shift`): a támadás-mix átrendeződése
  a két félidő között (össz-eltolódás százalékpontban). A nagy váltás
  alkalmazkodó, jól vezetett csapat jele; a mozdulatlan mix a
  kiszámíthatóé. Edzői olvasat: az átrendező ellen a szünetben a
  váltásukra készülj; a mozdulatlan ellen egy terv kitart 60 percen
  át; a saját oldalon a B-terv hiánya edzés-téma. Felületek:
  `/analyze` + meccs-csomag (`attack_mix_shift`), edzői összefoglaló,
  felderítés (edzői kulcs két iránnyal + 236-os meccsterv-szabály),
  edzés-fókusz (257-es szabály), kliens-csempe.
- **Lepattanó-esés** (`second_chance_fade`): a visszaharcolt második
  rohamok részaránya félidőnként — a hajrára elfogyó lepattanó-harc
  tiszta fáradás-jel (a lepattanó a láb és az akarat játéka). Edzői
  olvasat: ellene záráskor a blokk/védés utáni labda rendre a tiétek;
  a saját oldalon a fáradásos lepattanó-gyakorlat a téma. Felületek:
  `/analyze` + meccs-csomag (`second_chance_fade`), edzői
  összefoglaló, felderítés (edzői kulcs + 235-ös meccsterv-szabály),
  edzés-fókusz (256-os szabály), kliens-csempe.
- **Gólpassz-esés** (`assist_fade`): a gólpasszos gólok részaránya
  félidőnként — ha a hajrára beesik, a csapatjáték fáradt el: megáll a
  labda, jönnek az egyéni megoldások. Edzői olvasat: ellene a hajrában
  a labdás ember dupla nyomást kaphat; a saját oldalon a fáradásos
  hajra-csapatjáték az edzés-téma. Felületek: `/analyze` + meccs-csomag
  (`assist_fade`), edzői összefoglaló, felderítés (edzői kulcs +
  234-es meccsterv-szabály), edzés-fókusz (255-ös szabály),
  kliens-csempe.
- **Kapus-sorozat** (`gk_save_streaks`): a megszakítás nélküli
  védés-szériák a kapura tartó lövéseken (a tüzes kéz kapus-tükre).
  Edzői olvasat: a rákapó kapus ellen a lövés-képet kell váltani, nem
  a lövőt — más zóna, más ritmus, időkérés; a saját sorozat-kapust
  hagyni kell dolgozni. Felületek: `/analyze` + meccs-csomag
  (`gk_save_streaks`), edzői összefoglaló, felderítés (edzői kulcs +
  233-as meccsterv-szabály), edzés-fókusz (254-es szabály),
  kliens-csempe.
- **7a6-állás** (`empty_net_by_score`): az üres-kapus (7 a 6)
  szakaszok az eredményjelző szerint — akinél nem csak hátrányban jön,
  ott a 7a6 rendszer, nem mentőöv. Edzői olvasat: rendszer-7a6 ellen
  minden szerzés után az első nézés a túloldali üres kapu; a
  csak-hátrányban 7a6-ozó ellen a vezetés után kell átkapcsolni.
  Felületek: `/analyze` + meccs-csomag (`empty_net_by_score`), edzői
  összefoglaló, felderítés (edzői kulcs két iránnyal + 232-es
  meccsterv-szabály), edzés-fókusz (253-as szabály), kliens-csempe.
- **Kontra-állás** (`breaks_by_score`): a lerohanás-részarány az
  eredményjelző szerint — hátrányban megugró kontra-arány =
  kényszer-kontra, vezetésnél is futó csapat = ölő ösztön. Edzői
  olvasat: a kényszer-kontrás ellen vezetésnél a visszafutás-fegyelem
  dönt; a saját oldalon a hátrányban is szervezett visszajövetel a
  téma. Felületek: `/analyze` + meccs-csomag (`breaks_by_score`),
  edzői összefoglaló, felderítés (edzői kulcs + 231-es
  meccsterv-szabály), edzés-fókusz (252-es szabály), kliens-csempe.
- **Hetes-állás** (`sevens_by_score`): a kiharcolt hetesek az
  eredményjelző szerint — hátrányban sűrűsödő hetes = a betörés és a
  kontakt a menekülő-fegyver. Edzői olvasat: az ilyen csapat ellen
  vezetésnél lábbal védekező fal és kapus-hetes-készenlét kell; a saját
  oldalon a vezetés-őrző lábmunka a téma. Felületek: `/analyze` +
  meccs-csomag (`sevens_by_score`), edzői összefoglaló, felderítés
  (edzői kulcs + 230-as meccsterv-szabály), edzés-fókusz (251-es
  szabály), kliens-csempe.
- **Fegyelem-állás** (`suspensions_by_score`): a kiállítások az
  eredményjelző szerint — a kiállítás pillanatában vezetett, állt vagy
  hátrányban volt-e a kiállított csapat. Edzői olvasat: a hátrányban
  sűrűsödő kiállítás frusztrációs jel — ellene a vezetés maga a fegyver
  (vállalt kontakt kiállítást terem); a saját oldalon a hátrányban is
  hideg fej a téma. Felületek: `/analyze` + meccs-csomag
  (`suspensions_by_score`), edzői összefoglaló, felderítés (edzői kulcs
  + 229-es meccsterv-szabály), edzés-fókusz (250-es szabály),
  kliens-csempe.
- **Kidobott labda** (`balls_out`): az oldalvonalon kimenő labdák a
  kimenés előtti birtoklónak felírva (az alapvonal-közeli, elhajló
  lövéseket kihagyva). Edzői olvasat: a legolcsóbb eladás — ellenfél
  sem kell hozzá; aki sokat dob ki, azt az oldalvonalra kell szorítani,
  a saját oldalon a szélső-passz pontossága a téma. Felületek:
  `/analyze` + meccs-csomag (`balls_out`), edzői összefoglaló,
  felderítés (edzői kulcs + 228-as meccsterv-szabály), edzés-fókusz
  (249-es szabály), kliens-csempe.
- **Elhúzódó támadás ára** (`slow_attack_cost`): a passzív-veszélyes,
  35 mp-nél hosszabb támadó-akciók megtérülése — hány zárul góllal a
  szakasz alatt vagy közvetlenül utána. Edzői olvasat: az üresjáratos
  hosszú támadás ellen türelmes, hibátlan védekezéssel a passzív jel a
  védőnek dolgozik; a saját oldalon a támadás-lezárást (időre futtatott
  figura) kell edzeni. Felületek: `/analyze` + meccs-csomag
  (`slow_attack_cost`), edzői összefoglaló, felderítés (edzői kulcs +
  227-es meccsterv-szabály), edzés-fókusz (248-as szabály), kliens-csempe.
- **Indítás-hiba ára**: GÓLBA KERÜLNEK-E az elszórt kapus-indítások.
  Az indítás-biztonság azt méri, hány kihozatal vész el — ez az árát:
  az elveszett indítás utáni 10 másodpercen belüli ellenfél-gólok
  (2+ büntetett hiba = gólba kerül; 4+ elveszett indítás gól nélkül
  = megússzák). Akinél a hiba gólba kerül, ott a magas letámadás
  bizonyítottan termel — a kapus-indításokat kell vadászni; a saját
  oldalon a biztos első passz a téma. Egy réteg, sok felület:
  `outlet_punishment` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (darabszámok, edzői kulcs +
  csempe), 226. meccsterv-szabály (az ő gólba kerülő indítás-hibáik
  × a ti sáv-záró védekezésetek), 247. edzés-szabály
  (indítás-biztonság: két biztos rövid célpont, tilos a vak hosszú).

- **Kihagyás-büntetés**: MEGBÜNTETIK-E a kihagyott ziccereiket. A
  kihagyott nagy helyzetek a mennyiséget mérik — ez a következményt:
  a kihagyás utáni fél percen belüli ellenfél-gólok aránya (4+
  kihagyott ziccer; 40%+ büntetett = lélektanilag törékeny, 10%
  alatti = jól emészti). A törékeny ellen a ziccer-kimaradása a jel:
  azonnali tempó, amíg mentálisan lent vannak; a saját oldalon a
  kihagyás utáni 30 mp kiemelt fókusz-idő. Egy réteg, sok felület:
  `punished_misses` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (darabszámok, két edzői kulcs +
  csempe), 225. meccsterv-szabály (az ő törékenységük × a ti gyors
  újraindításotok), 246. edzés-szabály (kihagyás utáni fél perc:
  előbb védekezni, aztán bánkódni).

- **Kilépés-büntetés**: A KILÉPÉSÜK MÖGÉ betalálnak-e. A kiugró
  védő megmondja, ki játszik elöl — ez az árát: a kapott gólok
  hányadánál volt a fal-vonalból (a védők medián kapu-távolságából)
  3+ méterrel kiugró védő (5+ mért kapott gól; 40%+ aránytól). A
  kilépés mögötti rést az ilyen csapatnál bizonyítottan megjátsszák
  — ellene átemelés vagy betörés a kilépő helyére; a saját oldalon
  a szomszéd mögé csúszása a téma. Egy réteg, sok felület:
  `stepout_punishment` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (darabszámok, edzői kulcs +
  csempe), 224. meccsterv-szabály (az ő gólba kerülő kilépéseik × a
  ti beálló-játékotok), 245. edzés-szabály (mögé csúszás hangos
  jelre).

- **Kettőzés-büntetés**: MÖGÉ BETALÁLNAK-E a kettőzésüknek. A
  kettőzés-rétegek megmondják, jönnek-e és ki jön — ez az árát: a
  kettőzött pillanatok után 3 mp-en belül kapott gólok (2+ gól =
  gólba kerül; 150+ kettőzött kocka gól nélkül = büntetlenül
  termel). Akinek a kettőzése gólba kerül, ott a kettőzés-jel
  támadási jel — az első passz a felszabadult emberhez; a saját
  gólba kerülő kettőzésnél a csúszás-rend és a visszazárás a téma.
  Egy réteg, sok felület: `double_punishment` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (darabszámok, edzői kulcs + csempe), 223. meccsterv-szabály (az ő
  gólba kerülő kettőzésük × a ti gyors elengedésetek), 244.
  edzés-szabály (kettőzés-visszazárás kijelölt csúszással).

- **Olvasó kapus**: ELŐRE OLVASSA-E a lövéseket a kapusuk. A
  becsapott kapus a gólokat nézi — ez a védéseket: a kapus a védett
  lövéseknél már a labda érkezési oldala felé mozgott-e (5+ mért
  védés; 50%+ olvasó, 15% alatti reflex). Az olvasó kapus ellen
  ütem-váltás és csel — a korai elköteleződését kell büntetni; a
  reflex-kapus ellen a kitartott, pontos sarok-lövés visz be. Egy
  réteg, sok felület: `reading_keeper` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (darabszámok, két
  edzői kulcs + csempe), 222. meccsterv-szabály (az ő
  reflex-kapusuk × a ti sarokra lőtt góljaitok), 243. edzés-szabály
  (kapus-olvasás: a lövő elkötelező jeleinek tanulása).

- **Becsapott kapus**: ELMOZDÍTJÁK-E a kapusukat a gólok előtt. A
  gól-pillanati család kapus-tagja: a kapott góloknál a kapus
  oldalirányú mozgását vetjük össze a labda érkezési oldalával (5+
  mért kapott gól; 40%+ becsapott = a lövéscsel a fegyver, 10%
  alatti = a csel időpocsékolás, első ütemből a sarokba). Egy
  réteg, sok felület: `wrongfooted_keeper` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (darabszámok, két edzői kulcs + csempe), 221. meccsterv-szabály
  (az ő elmozdítható kapusuk × a ti betörőitek), 242. edzés-szabály
  (kapus csel-állás: az utolsó ütemig tartott alaphelyzet).

- **Lendület-gólok**: MOZGÁSBÓL ÉRKEZŐ lövőktől kapják-e a
  gólokat. A gól-pillanati család sebesség-tagja: a kapott góloknál
  a lövő mozgás-sebessége a lövés pillanata körül (5+ mért kapott
  gól; 55%+ mozgásos = a bekísérés késik, 25% alatti = állóhelyből
  is tiszta lövést engednek). A mozgásból bekapó ellen a betörőt és
  a befutót kell játszani; az állóból bekapó ellen a kivárt átlövés
  is termel. Egy réteg, sok felület: `conceded_momentum` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (darabszámok, két edzői kulcs + csempe), 220. meccsterv-szabály
  (az ő késő bekísérésük × a ti befutóitok), 241. edzés-szabály
  (bekísérés hangos átadás-jellel).

- **Bontó tempó**: A JÁRATÁS SZEDI-E SZÉT a védekezésüket. A
  gól-pillanati család negyedik tagja: a kapott gólok előtti 8
  másodperc passzainak átlaga (5+ kapott gól; 3+ passz a járatásos,
  1,5 alatti az egyéni-akciós gólok jele). Akit a pörgés bont meg,
  az ellen tempót kell emelni — a fal a váltásoknál nyílik; akit
  egyéni akciókból lőnek szét, arra az 1v1-ben erős embereket kell
  engedni. Egy réteg, sok felület: `conceded_tempo` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (darabszámok, két edzői kulcs + csempe), 219. meccsterv-szabály
  (az ő járatással bontható faluk × a ti oldalváltós járatásotok),
  240. edzés-szabály (váltás tempó alatt).

- **Folyosó-gólok**: NYITOTT FOLYOSÓN kapják-e a gólokat. Az
  átvert védők a lövő melletti párharcot nézik — ez a lövés útját:
  a kapott góloknál volt-e bárki a lövő és a kapu-közép közti
  sávban (a lövésvonaltól 1,5 m-en belül; 5+ kapott gól, 50%+
  nyitott / 20%- zárt). A nyitott folyosós gól a fal-zárás és a
  visszazárás hibája — ellene betörés és gyors átmenet; a zárt fal
  mögött is bekapott gól a kapus-oldal kérdése — ellene kimozgatás
  és pontos elhelyezés. Egy réteg, sok felület: `corridor_goals`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (darabszámok, két edzői kulcs + csempe), 218.
  meccsterv-szabály (az ő nyitott folyosóik × a ti éles kontrátok),
  239. edzés-szabály (folyosó-zárás: az első védő a kapu-lövő
  vonalra).

- **Csere-büntetés**: GÓLBA KERÜLNEK-E a csere-lyukak. A
  csere-lyukak a kitettséget mérik — ez a megfizetett árát: a rövid
  (cserés, nem kiállításos) öt fős szakaszok alatt és közvetlenül
  utánuk kapott gólok (2+ góltól büntetett; 20+ mp lyuk gól nélkül
  = büntetlenül megúszták). Akinél a lyuk gólba kerül, ott a
  csere-pillanat bizonyítottan támadható; a saját oldalon a
  csere-ütem javítása sürgős. Egy réteg, sok felület:
  `gap_punishment` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (lyuk-másodperc + darabszámok,
  edzői kulcs + csempe), 217. meccsterv-szabály (az ő gólba kerülő
  lyukaik × a ti gyors újraindításotok), 238. edzés-szabály
  (csere-ütem: ki és be egy ütemben).

- **Zavartalan előkészítők**: HAGYJÁK-E DOLGOZNI a gólpassz-adót.
  Az átvert védők a lövő párharcát nézik — ez az eggyel korábbi
  pillanatot: a kapott gólpasszos góloknál volt-e védő (2 m-en
  belül) a kiadó mellett a passz pillanatában (5+ gólpasszos kapott
  gól; 60%+ laza, 25% alatt rálépős). A gól ritkán a lövésnél dől
  el: a laza védekezés ellen a kidolgozott játék szabadon fut, a
  rálépős ellen egy-ütemű korai kiadás kell. Egy réteg, sok
  felület: `unpressured_assists` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (darabszámok, két
  edzői kulcs + csempe), 216. meccsterv-szabály (az ő laza
  előkészítő-védekezésük × a ti gólpasszos játékotok), 237.
  edzés-szabály (passzsáv-nyomás: kéz a sávban, test a kiadón).

- **Átvert védők**: KI MÖGÖTT esnek a kapott gólok. Az őrzési párok
  azt mérik, ki kit fog — ez azt, ki veszíti el a párharcot, amikor
  számít: minden kapott gólnál a lövőhöz legközelebbi (3,5 m-en
  belüli) védőt jegyezzük átvertként; a radiuson kívüli lövés
  fedezetlen (szerkezeti hiba, nem párharc-vereség). Az ellenfél
  sokat átvert védője a megtámadható ember — rá kell vinni az
  1v1-et; a saját átvert védőnk mellé segítés-rend és párharc-edzés
  kell. Egy réteg, sok felület: `beaten_defenders` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (mezszám
  szerinti darabszámok + fedezetlen gólok, edzői kulcs + csempe),
  215. meccsterv-szabály (az ő átvert védőjük × a ti betörő
  embereitek), 236. edzés-szabály (párharc-segítés kijelölt
  besegítővel).

- **Türelmes meccs-könyvtár betöltés**: az app indulásakor a
  beépített motor még bootolhat (első indításnál a rendszer át is
  vizsgálja — akár egy perc), és ha a felhasználó közben nyitotta
  meg pl. az Ellenfél-felderítést, nyers "Connection refused" hibát
  kapott. A meccs-lista lekérése mostantól kapcsolat-hibánál 75
  másodpercig másodpercenként újrapróbálkozik (közben a tartalék
  portra költöző motort is követi), és ha végleg nem megy, emberi
  nyelvű hibaüzenetet ad a motor-napló pontos helyével. Mind az öt
  könyvtár-olvasó képernyő (kezdőlap, felderítés, élő, fejlődés,
  figura-tervező) egyszerre gyógyult.

- **Kiadás-javítás + kliens-helper őr**: a scouting-képernyőn két
  különböző csempe-helper véletlenül ugyanazt a `_gkOutlet` nevet
  kapta (indítás-sebesség és indítás-hossz) — a Flutter build ezen
  bukott el a kiadáskor. A hossz-mérő átnevezve
  (`_gkOutletLength`, "Indítás-hossz" csempe-címkével), és új
  füstteszt őrzi, hogy kliens-helper név ne duplázódhasson többé.
- **Csempe-címke rendrakás + őr**: három csempe-címke ütközött
  ("Kapus-indítás" kétszer, "Félidő-zárás" kétszer, "Lövőerő-esés"
  kétszer) — az utolsó labda csempéje saját címkét kapott ("Utolsó
  labda"), a lövés-sebesség-esés duplikált csempéje (a
  Lövőerő-eséssel azonos mérés) törölve, és új füstteszt követeli a
  csempe-címkék egyediségét.
- **Duplikátum-motor kivezetve**: a shot_power_fade (a
  shot_speed_fade tartalmi duplikátuma) minden felületről eltűnt —
  a motor, az API-bekötések, a duplikált edzői mondat és kulcs, a
  spf_* felderítés-mezők és a duplikált teszt törölve; a 97.
  meccsterv-szabály és a Lövőerő-esés csempe az ssf_* mezőkre
  átkötve (5+ lövés/félidő, 8%-os küszöb — az egyetlen megmaradó
  motorral azonosan).

## v0.1.23 — kiadva (2026-08-01)

> Kiadás-jegyzet: a GitHub-kiadások a v0.1.22 után itt folytatódnak —
> a korábbi v0.1.23–v0.1.25 changelog-körök címke nélkül maradtak,
> így ez a kiadás azok MINDEN fejlesztését is tartalmazza, plusz az
> azóta született ~82 új réteget és a néma hibák elleni őr-teszteket.
> A vezérfonal kettős: egyrészt a poszt-lencse (gól, hiba, gólpassz,
> hetes, kiállítás, falba lövés, felhozatal poszt szerint) és az
> állás-lencse (tempó, lövés-minőség, kapus-védés, hiba, védekezés,
> csere, indítás állás szerint) családok kiépülése, másrészt a
> regisztry-füstteszt család: egyetlen réteg, kulcs vagy végpont sem
> bukhat el többé némán.

- **Indítás-állás**: VEZETVE LASSÍTJÁK-E a kapus-indítást. A
  kapus-indítás a teljes meccs átlagát méri — ez állás szerint: a
  védés utáni felező-átlépés ideje vezetés közben, szemben a többi
  állapottal (vödrönként 4+ indítás; +2 mp az időhúzás, −1 mp a
  pörgetés jele). Az időhúzós ellen hátrányban kapott gól után
  azonnali középkezdés kell; az előnyben is pörgető ellen a védésük
  utáni pillanat a legveszélyesebb. Egy réteg, sok felület:
  `outlet_pace_by_score` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (vödrönkénti indítás-darabszám +
  másodperc-összeg, két edzői kulcs + csempe), 214.
  meccsterv-szabály (az ő időhúzó kihozataluk × a ti gyors
  középkezdésetek), 235. edzés-szabály (indítás-kontroll: pörgetés/
  kontroll jelre).

- **Csere-állás**: VEZETVE FORGATNAK-E. A csere-kiváltók azt mérik,
  kapott gólra cserélnek-e — ez azt, mit tesznek az előnnyel: a
  cserehullámok ütemét (hullám/perc) vetjük össze a vezetésben és a
  többi állapotban töltött idő között (vödrönként 120+ mp, 4+
  hullám; 1,5-szeres ütem a forgatás, fele annyi a befagyott sor
  jele). A vezetve forgató ellen a szoros meccs a fegyver — amíg
  nincs meg az előnyük, nem mernek pihentetni; aki előnyben sem
  cserél, annál a fáradó kulcsembert kell a végén megtámadni. Egy
  réteg, sok felület: `subs_by_score` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (vödrönkénti
  hullám-darabszám + másodperc-összeg, két edzői kulcs + csempe),
  213. meccsterv-szabály (az ő csak-előnyben-forgató padjuk × a ti
  szoros-meccs rutinotok), 234. edzés-szabály (a pad bizalma:
  kihirdetett csere-rend, a pad külön pontversenye).

- **Előny-védekezés**: LEÜL-E A FALUK, amikor vezetnek. A kapott
  helyzetek minősége a teljes meccset nézi — ez állás szerint: a
  csapat ellen leadott lövések átlagos xG-je vezetés közben, szemben
  a többi állapottal (vödrönként 5+ lövés; +0,05 xG a leülés, −0,02
  a feszesen maradó fal jele). Az előnyben leülő ellen hátrányban
  sincs pánik — türelmes, bevitt támadásokkal visszajön a meccs; az
  előnyben is feszes ellen az elejét kell megnyerni. Egy réteg, sok
  felület: `defense_by_score` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (vödrönkénti lövés-darabszám +
  xG-összeg, két edzői kulcs + csempe), 212. meccsterv-szabály (az
  ő leülő faluk × a ti lövésig vitt hosszú támadásaitok), 233.
  edzés-szabály (előny-megtartó védekezés vezetésből indított
  edzésmeccsel).

- **Hiba-állás**: HÁTRÁNYBAN SZÓRJÁK-E a labdát. A tempó-állás azt
  méri, gyorsítanak-e hátrányban — ez azt, mi lesz a labdával:
  állásonként (vezet / hátrányban / döntetlen) az eladással záruló
  támadások aránya (vödrönként 5+ támadás; +10 százalékpont
  kapkodás, −5 rendezettség). A hátrányban kapkodó ellen az első
  ellépés után présre kell váltani — a nyomás alatt ontott labda a
  különbséget hizlalja; a hátrányban is rendezett ellen a prés nem
  térül meg. Egy réteg, sok felület: `turnovers_by_score` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (állás-vödrönkénti támadás/eladás darabszámok, két edzői kulcs +
  csempe), 211. meccsterv-szabály (az ő hátrány-kapkodásuk × a ti
  labdaszerző védekezésetek), 232. edzés-szabály (nyomás alatti
  rendezettség mesterséges hátrányból).

- **Kettőző emberek**: KI JÖN MÁSODIKNAK a labdásra. A kettőzés-
  réteg azt méri, kettőznek-e — ez azt, ki: a kettőzött kockákon a
  labdáshoz második legközelebbi védőt jegyezzük (50+ kettőzött
  kocka; 40%+ részarány, holtverseny nélkül). A mindig ugyanattól
  az embertől jövő kettőzés kiolvasható — a kettőző őrzöttje
  szabadul, oda megy az első passz begyakorolt jelre; a saját
  kettőzésünket forgatni kell. Egy réteg, sok felület:
  `doubling_defenders` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (mezszám szerinti kettőzés-
  darabszámok, edzői kulcs + csempe), 210. meccsterv-szabály (az ő
  kiolvasható kettőzésük × a ti gyors elengedésetek), 231.
  edzés-szabály (kettőzés-forgatás hangos jelre).

- **Szélső-mélység**: MILYEN MÉLYRŐL lőnek a szélsőik. A
  szélső-befejezés a zóna hatékonyságát méri — ez a befutás
  mélységét: a szélső-posztú lövések kapu-vonaltól mért átlagos
  távolsága (5+ lövés; 6,5 m alatt mélyre befutó, 8,5 m felett
  messziről lövő). A mélyre befutó szélső ellen a kapus várjon — a
  korai kifutás öngól, a szöget a kifutó védő zárja a befutás
  előtt; a messziről lövőnél a szög ráengedhető, a kapus bátran
  jöhet ki. Egy réteg, sok felület: `wing_shot_depth` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (lövés-darabszám + mélység-összeg, két edzői kulcs + csempe),
  209. meccsterv-szabály (az ő messziről lövő szélsőik × a ti jól
  védő kapusotok), 230. edzés-szabály (szélső-befutás: hatosról
  lőtt gól dupla pont).

- **Kontra-esés**: MELYIK FÉLIDŐBEN kontráznak. A fáradás-család
  kontra-tagja: a lerohanások részaránya az első és a második félidő
  támadásain belül (félidőnként 5+ támadás; 15 százalékpontos
  váltástól). Akinek a második félidőben eláll a kontrája, annál az
  elejét kell túlélni — a szünet után már a felállt fal dolgozik;
  aki a hajrára kontrázósabb, az ellen a második félidőben duplán
  szigorú a visszafutás-fegyelem. Egy réteg, sok felület:
  `break_share_fade` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (félidőnkénti támadás/kontra
  darabszámok, két edzői kulcs + csempe), 208. meccsterv-szabály
  (az ő hajrá-kontráik × a ti biztos labdakezelésetek), 229.
  edzés-szabály (kontra-kondicionálás fáradt lábbal).

- **Felhozatal-posztok**: MELYIK POSZTRA hozzák fel a labdát. A
  kapus-indítás célpontjai a nevet adják — ez a posztot: az
  indítás-célpontokat a poszt-becsléshez kötjük (4+ célpont; 50%+
  részarány, holtverseny nélkül), így akkor is látszik, kire épül a
  felhozataluk, ha a nevek cserélődnek. A letámadásnál a kulcs-poszt
  fogása az egész felhozatalt megakasztja — a kapus
  kényszer-hosszúja elfogható; a saját egy-utas felhozatalunknak
  második út kell. Egy réteg, sok felület: `outlet_target_roles`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (poszt szerinti célpont-darabszámok, edzői
  kulcs + csempe), 207. meccsterv-szabály (az ő egy-posztos
  felhozataluk × a ti passzsáv-záró védekezésetek), 228.
  edzés-szabály (második felhozatal-út letámadás ellen).

- **Falba lövő posztok**: MELYIK POSZTJUK lő rendre a falba. A
  lefogott lövők a nevet adják — ez a posztot: a lefogott lövőket a
  poszt-becsléshez kötjük (4+ lefogott lövés; 50%+ részarány,
  holtverseny nélkül), így akkor is látszik a minta, ha a nevek
  cserélődnek. Ahol a falba lövés posztra jellemző, ott a fal
  tartása maga a védekezés — nem kell kilépni, a blokk magától
  termel; a saját falba lövő posztunknak lövés-előkészítés kell
  (elzárás, egy-ütemű csel), nem több erő. Egy réteg, sok felület:
  `blocked_by_role` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (poszt szerinti darabszámok,
  edzői kulcs + csempe), 206. meccsterv-szabály (az ő falba lövő
  posztjuk × a ti termő blokkjaitok), 227. edzés-szabály
  (lövés-előkészítés: előkészített gól dupla pont).

- **Kiállítás-posztok**: MELYIK POSZTJUK hozza a kétperceseket. A
  kiállítás-kiharcolók a nevet adják — ez a posztot: a kiharcolókat
  a poszt-becsléshez kötjük, a hetes-posztok mintájára (3+ kiharcolt
  kiállítás; 50%+ részarány, holtverseny nélkül). Az átlövő betörése
  ellen korai, még lendület előtti lépés; a beálló elzárás-birkózása
  testtel, fegyelmezetten; a szélső kifutásánál tilos a kéz — a
  kései fogás emberelőnyt termel nekik. Egy réteg, sok felület:
  `susp_earner_roles` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (poszt szerinti
  kiállítás-darabszámok, edzői kulcs + csempe), 205.
  meccsterv-szabály (az ő kiállítás-termelő posztjuk × a ti
  fegyelmezett falatok), 226. edzés-szabály (kiharcolás-gyakorlat:
  kontakt-vállalás pontért).

- **Gólpassz-posztok**: MELYIK POSZTJUK készíti elő a góljaikat. A
  gólpassz-forrás a helyet nézi, a gólpassz-hálózat a neveket — ez a
  posztot: a gólokhoz rendelt gólpasszokat az előkészítő becsült
  posztjához kötjük (5+ gólpassz; 45%+ részarány, holtverseny
  nélkül), így akkor is látszik a minta, ha a nevek cserélődnek.
  Irányító-előkészítés ellen felső kettőzés, szélső ellen a
  visszatett labda zárása, beálló ellen elé állás a kiosztás ellen
  is. Egy réteg, sok felület: `assists_by_role` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (poszt
  szerinti gólpassz-darabszámok, edzői kulcs + csempe), 204.
  meccsterv-szabály (az ő egy-posztos előkészítésük × a ti sáv-záró
  védekezésetek), 225. edzés-szabály (második előkészítő-út: a nem
  a fő posztról érkező gólpassz dupla pont).

- **Lefogott lövők**: KINEK A LÖVÉSÉT viszi el rendre a fal. A falba
  lövés a csapat-tünetet méri — ez a személyt: minden blokknál
  visszakeressük a lövőt (a blokk előtti utolsó támadó
  labdabirtokos), és játékosonként számoljuk (4+ lefogott lövés,
  50%+ részarány, holtverseny nélkül). Az ellenfél kiemelt lefogott
  lövője ellen megéri falban maradni — a blokk dolgozik a védelem
  helyett; a saját sokat lefogott lövőnknek lövő-variáció kell.
  Egy réteg, sok felület: `blocked_shooters` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (mezszám szerinti lefogás-darabszámok, edzői kulcs + csempe),
  203. meccsterv-szabály (az ő lefogott lövőjük × a ti termő
  blokkjaitok), 224. edzés-szabály (lövő-variáció gyakorlat élő
  fal ellen).

- **Kontra-elszökés**: ELŐRE SZÖKÖTT emberrel kontráznak-e. A
  kontra-forrás azt mondja meg, miből indul a lerohanásuk, a
  kontra-hullámok azt, ki fejezi be — ez azt, hol állnak az
  induláskor: van-e a labdánál legalább 6 méterrel előrébb váró
  játékosuk (5+ kontra; 40% felett elszökős, 10% alatt együtt
  felfutó). Az elszökős csapat ellen állandó mélységbiztosítás kell
  és a hosszú indítás elvágása; az együtt felfutó ellen az első két
  visszafutó lassít, és a védelem beér. Egy réteg, sok felület:
  `fast_break_headstart` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (kontra-darabszámok, két edzői
  kulcs + csempe), 202. meccsterv-szabály (az ő elszökős kontráik ×
  a ti biztos labdakezelésetek), 223. edzés-szabály (elszökő-
  gyakorlat: a lövésünk pillanatában forduló szélső).

- **Kontra-hullámok**: az ELSŐ EMBER vagy a MÁSODIK HULLÁM fejezi-e
  be a lerohanásaikat. A kontra-befejezők a neveket adják, a
  kontra-hatásfok a végeredményt — ez a szerkezetet: a lövésig jutó
  kontráknál megnézzük, az induláskor legelöl lévő ember lő-e, vagy
  egy mögötte befutó (5+ kontra; 50% felett második hullám, 20%
  alatt első ember). A második hullámos csapat ellen az első ember
  felvétele nem elég — a visszafutásnál a középső sávot kell
  feltölteni; az első emberes ellen az indítópassz elvágása öli meg
  a kontrát. Egy réteg, sok felület: `fast_break_waves` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (kontra-darabszámok, két edzői kulcs + csempe), 201.
  meccsterv-szabály (az ő befutóik × a ti erős átmenet-védekezésetek),
  222. edzés-szabály (kontra-hullám gyakorlat: a második hullámból
  szerzett gól dupla pont).

- **Beálló-futtatás**: MOZGÁSBÓL vagy ÁLLVA kapja-e a beálló a
  labdát. A beálló-terhelés azt méri, mennyit megy rá a labda, a
  kiszolgálói azt, kitől — ez azt, HOGYAN érkezik: a beálló-átvételek
  fogadó-sebességéből (5+ átvétel; 55% felett lefordulós, 25% alatt
  beragadt). A lefordulva kapó beálló ellen a bejátszás ELŐTT kell
  elé lépni — az átvétel utáni birkózás késő; a beragadt beálló
  testes elé állással és azonnali kettőzéssel lezárható. Egy réteg,
  sok felület: `pivot_service` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (átvétel-darabszámok, két edzői
  kulcs + csempe), 200. meccsterv-szabály (az ő lefordulós beállójuk
  × a ti erős beálló-őrzésetek), 221. edzés-szabály (lefordulós
  átvétel: elzárás-leforduló párgyakorlat).

- **Réteg-regisztry füstteszt**: egyetlen elemzés-réteg sem bukhat
  el némán. A meccs-csomag `_layer` segédje és az /attacks végpont
  `try/except` blokkjai szándékosan lenyelik a hibát (egy réteg nem
  viheti el a többit) — az ára eddig az volt, hogy egy elromló motor
  észrevétlenül tűnt el a kimenetből. Az új teszt a forrásból olvassa
  ki az összes regisztrált réteg nevét (önfrissülő: új rétegnél
  semmit nem kell hozzáírni), lefuttat egy szimulált meccset a teljes
  csomag-exporton és az ÖSSZES elemzés-végponton (attacks, defense,
  goalkeepers, tactics, quality), és követeli, hogy mind a 246+
  csomag-réteg és minden végpont-kulcs ott legyen — a
  félidő-feltételes kulcsok kivételével. Plusz: két azonos nevű
  regisztráció (néma felülírás) is tesztet buktat, a
  combine_reports-nak a ScoutingReport MINDEN mezőjét kezelnie kell —
  a kimaradó mező több meccs összefésülésekor némán az alapértékére
  esne vissza (az örökölt, nem összegezhető mezők zárt listán) —, a
  kliens-csempék minden r["..."] kulcsának létező
  felderítés-mezőnek kell lennie (az elgépelt kulcs némán üres
  csempét adna), a meccsterv-/edzés-szabályok sorszámai nem
  ismétlődhetnek, a félidő-feltételes (_fh) kulcsok egy felismert
  félidejű szimulált meccsen mind elkészülnek, MINDEN GET végpont —
  a paraméteres játékos-végpontokkal együtt — 5xx nélkül fut le
  érvényes meccsen, és minden végpont-oldali réteg-kulcsnak a
  meccs-csomag regisztryjében is szerepelnie kell (a recept "KÉT
  helyre" lépésének őre, az örökölt kivételek zárt listán).

- **Keresztjáték**: MENNYIT KERESZTEZNEK a hátsó sorban. Az álló
  támadók rétege az egyéni mozgást méri — ez a szerkezetet: felállt
  támadásonként számoljuk a hátsó sor oldalcseréit (8+ támadás; 1,0
  felett sok, 0,3 alatt statikus). A sokat keresztező ellen a
  váltás-fegyelem dönt — hangos, korai átadás a védők közt; a
  statikus hátsó sor ellen ember-ember tartás is vállalható. Egy
  réteg, sok felület: `crossing_runs` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (támadás- és
  kereszt-darabszámok, két edzői kulcs + csempe), 199.
  meccsterv-szabály (az ő keresztjeik × a ti fegyelmezett falatok),
  220. edzés-szabály (keresztmozgások: kötelező kereszt a lövés
  előtt).

- **Szélső-futtatás**: LENDÜLETBŐL vagy ÁLLVA kapják-e a szélsők a
  labdát. A szél-bevonás azt méri, mennyit ér a szélső játék — ez
  azt, hogyan érkezik a labda: a szélső-átvételeknél a fogadó
  sebességét mérjük (6+ átvétel; 55% felett futtatott, 25% alatt
  álló). A futtatott szélsők ellen a futópassz sávját kell zárni — a
  kifutás mindig késik; az álló szélsők ellen a bátor, korai kifutás
  a recept. Egy réteg, sok felület: `wing_service` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (átvétel-
  darabszámok, két edzői kulcs + csempe), 198. meccsterv-szabály (az
  ő futtatott szélsőik × a ti sáv-záró védekezésetek), 219.
  edzés-szabály (futtatott széljáték: belépés a passz indulásakor).

- **Csere-lyukak**: MENNYI IDEIG JÁTSZANAK 5-EN csere közben. A
  kiállítás-felismerés a 45 másodpercnél hosszabb létszám-hiányt nézi
  — ez a rövidebbeket: azok a szakaszok, ahol a mezőnyjátékos-létszám
  a cserék lassúsága miatt esik ötre (20+ másodperc összesen a
  jelzéshez). A lyukas csere ingyen emberelőny — a cseréjük pillanata
  támadási jel: gyors középkezdés, amíg öten vannak. Egy réteg, sok
  felület: `sub_gaps` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (lyuk-másodperc összeg, edzői kulcs
  + csempe), 197. meccsterv-szabály (az ő lyukas cseréik × a ti gyors
  újraindításotok), 218. edzés-szabály (csere-ütem: kézjeles váltás,
  hangosan számolt öt fős másodpercek).

- **Gólpassz-hossz**: HOSSZÚ INDÍTÁSOKBÓL vagy RÖVID KOMBINÁCIÓKBÓL
  élnek. A gólpassz-hálózat azt mondja meg, ki kinek készít elő — ez
  azt, milyen messziről: minden gólpasszos gólnál megmérjük az
  előkészítő és a lövő távolságát (5+ gólpasszos gól; 50% felett
  hosszú, 20% alatt rövid). A hosszú gólpasszokból élő ellen a
  passzsávakat kell zárni — a hosszú labda elfogható; a rövid
  kombinációkból élő ellen a kis terület védése dönt. Egy réteg, sok
  felület: `assist_ranges` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (gólpassz-darabszámok, két edzői
  kulcs + csempe), 196. meccsterv-szabály (az ő hosszú gólpasszaik ×
  a ti sáv-záró védekezésetek), 217. edzés-szabály (hosszú
  előkészítés: átemelés- és bejátszás-blokk, duplán érő távoli
  előkészítés).

- **Kapus-kipattanó**: FOGJA vagy KIÜTI a labdát a kapusuk. A
  védés-számok azt mérik, hány lövést fog meg — ez azt, mi lesz a
  védett labdával: a védés utáni első stabil, megült birtokost nézzük
  (4+ mért védés; 70% felett fogó, 40% alatt kiütő kapus). A kiütő
  kapus ellen minden lövést kísérni kell — a kipattanó-vadász a
  hatosnál marad; a fogó kapus ellen a lövés pillanatában már hátra
  kell indulni, mert azonnali indítás jön. Egy réteg, sok felület:
  `gk_rebound_control` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (védés- és megfogás-darabszámok,
  két edzői kulcs + csempe), 195. meccsterv-szabály (az ő kiütő
  kapusuk × a ti lepattanó-vadászaitok), 216. edzés-szabály
  (kipattanó-irányítás: szélre ütés, hangos enyém/tiéd).

- **Kivárás-csapda**: MI LESZ A HOSSZÚ TÁMADÁSAIKBÓL. A
  passzív-kockázat réteg a hosszú, lövés nélküli szakaszokat listázza
  — ez ítéletet mond: a 25 másodpercnél hosszabb felállt
  támadásaikból mennyi hal el lövés nélkül (5+ hosszú támadás; 40%
  felett elhaló, 15% alatt lövésig érő). Akinek a hosszú támadásai
  elhalnak, annak a kivárás csapda — fegyelmezett, kivárós fal
  ellenük a recept; akinek lövésig érnek, az ellen korai megzavarás
  kell. Egy réteg, sok felület: `long_attack_outcomes` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (támadás-
  és elhalás-darabszámok, két edzői kulcs + csempe), 194.
  meccsterv-szabály (az ő elhaló támadásaik × a ti fegyelmezett
  falatok), 215. edzés-szabály (figura-zárás időben: 25 másodperces
  óra, kötelező B-zárás).

- **Felfutási létszám**: HÁNY EMBERREL támadnak. A támadás-szélesség
  a teret méri — ez a létszámot: támadó-térfeles birtoklás-kockánként
  megszámoljuk, hány mezőnyjátékosuk van fent (100+ kocka; 5,5 felett
  mindenki fent, 4,5 alatt biztosítás). A mindenkit felküldő csapat
  háta mögött üres a pálya — minden szerzés kontrát ér; a biztosítva
  támadó ellen a fal bátran kettőzhet, mert elöl emberhátrányban
  vannak. Egy réteg, sok felület: `attack_headcount` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (kocka- és
  létszám-összegek, két edzői kulcs + csempe), 193. meccsterv-szabály
  (az ő felküldött mindenki-jük × a ti gyors kapus-indításotok), 214.
  edzés-szabály (biztosítás-rend: kijelölt hátramaradó, duplán
  számító kontragól).

- **Blokk-lepattanó**: A BLOKK UTÁN ki szerzi meg a labdát. A
  blokk-arány azt méri, mennyi lövést fognak meg — ez azt, mit ér a
  blokk: a blokkolt labda lepattanóját a blokk utáni másodpercek első
  stabil birtokosához kötjük (4+ blokk; 60% felett teljes értékű, 30%
  alatt visszahulló). A visszahulló blokkú csapat ellen a blokkolt
  lövés után azonnal újra kell támadni; a lepattanót is megszerző
  ellen a blokkba lőtt labda labdavesztés. Egy réteg, sok felület:
  `block_recoveries` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (blokk- és lepattanó-darabszámok,
  két edzői kulcs + csempe), 192. meccsterv-szabály (az ő visszahulló
  blokkjaik × a ti második hullámotok), 213. edzés-szabály (blokk
  utáni lepattanó: fordulás és irányított felvétel).

- **Ziccer-befejezők**: KI ÉRTÉKESÍTI a nagy helyzeteket. A pazarló
  lövők minden lövést néznek — ez csak a ziccereket: játékosonként
  számoljuk a 0,5 feletti helyzet-értékű lövéseket és góljaikat (3+
  ziccer; 80% felett biztos, 40% alatt bizonytalan befejező). A
  ziccer-biztos ellen a helyzetet már a kialakulása előtt kell
  megelőzni; a bizonytalannál a fal vállalhatja, hogy inkább őt
  engedi helyzetbe. Egy réteg, sok felület: `big_chance_finishers`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (játékosonkénti ziccer-darabszámok összegzéssel,
  két edzői kulcs + csempe), 191. meccsterv-szabály (az ő
  ziccer-biztos befejezőjük × a ti korai besegítésetek), 212.
  edzés-szabály (ziccer-rutin: fáradt befejezés-sorozat
  időkényszerrel).

- **Hetes utáni percek**: LERAGADNAK-E az adott hetes után. A
  hetes-rétegek magát a büntetőt mérik — ez az utóhatását: az ellenük
  ítélt hetes utáni percben nézzük a további kapott gólokat, a
  hetes-lövés saját ablakát átugorva (3+ adott hetes, 2+ további
  kapott gól az ítélethez). A hetes körüli leállás sok csapat
  védekezés-ritmusát megtöri — ellenük a hetes utáni támadást is kész
  figurával kell megjátszani. Egy réteg, sok felület:
  `post_seven_lapses` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (hetes- és gól-darabszámok, edzői
  kulcs + csempe), 190. meccsterv-szabály (az ő hetes utáni
  leragadásuk × a ti kiharcolt heteseitek), 211. edzés-szabály (hetes
  utáni újrarendeződés: 10 másodperces protokoll).

- **Labda-forgatás iránya**: MERRE JÁRATJÁK a labdát felállt
  támadásban. A passz-irány az előre-hátra tengelyt méri — ez az
  oldalirányt: minden érdemi oldalpassznál megnézzük, a támadó
  szemszögéből balra vagy jobbra megy-e a labda (20+ oldalpassz, 60%
  részarány az ítélethez). Az egyirányba forgató csapat ellen a
  kettőzés a forgás végpontján ér a legtöbbet, az ellenirányba
  terelés pedig kizökkenti a ritmusukat. Egy réteg, sok felület:
  `circulation_direction` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (irány szerinti darabszámok, edzői
  kulcs + csempe), 189. meccsterv-szabály (az ő egyirányú forgásuk ×
  a ti sáv-záró védekezésetek), 210. edzés-szabály (kétirányú
  forgatás: tükrözött figurák, kötelező forgásváltás).

- **Elzárás-páros**: KI ZÁR KINEK — a bejáratott elzáró-lövő kettős.
  Az elzárás-emberek azt mondják meg, ki zár a legtöbbet — ez azt,
  kinek: minden elzárásból leadott lövésnél az (elzáró, lövő) párost
  jegyezzük fel (3+ közös lövés a bejáratott kettőshöz). A páros
  ellen a védekezés is párban készül — az elzáró őrzője előre szól, a
  lövő őrzője az elzárás előtt lép ki; a saját párost a
  kiszámíthatóságtól kell védeni. Egy réteg, sok felület:
  `screen_pairs` motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (páros szerinti darabszámok összegzéssel, edzői
  kulcs + csempe), 188. meccsterv-szabály (az ő elzárás-párosuk × a
  ti blokkjaitok), 209. edzés-szabály (elzárás-variálás: három
  változat, korlátozott fő páros).

- **Szélső-kifutás**: IDŐBEN ÉRNEK-E KI a szélső lövéseire. A poszt
  szerinti kapott gólok azt mondják meg, a szélsők ellen
  szivárognak-e — ez azt, miért: a szélső-posztú lövők lövéseinél
  megmérjük a legközelebbi védő távolságát a lövés pillanatában (4+
  lövés; 2,5 m felett késői, 1,2 m alatt zárt kifutás). A későn
  kifutó fal ellen a széljáték ingyen terem — gyors oldalváltásokkal
  kell oda hordani a labdát; a zárt fal ellen a beálló szabadul fel.
  Egy réteg, sok felület: `wing_closeouts` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (lövés-darabszám +
  távolság-összeg, két edzői kulcs + csempe), 187. meccsterv-szabály
  (az ő késői kifutásuk × a ti szélső-góljaitok), 208. edzés-szabály
  (szél-kifutás időzítése: indulás a passz levegőben létekor).

- **Csend-törők**: KI DOBJA a gólcsendet megtörő gólt. A
  gólcsend-elemzés a leghosszabb szárazságot méri — ez azt, ki vet
  véget neki: az 5+ perces saját gólcsend utáni gól lövője csend-törő
  jóváírást kap (2+ törés a kiemelt válság-lövőhöz). Az ellenfél
  válság-lövőjét pont a saját sorozatunk alatt kell a legszorosabban
  fogni — hozzá menekül a labda, amikor áll a szekerük. Egy réteg,
  sok felület: `drought_breakers` motor, edzői összefoglaló, /analyze
  + meccs-csomag, felderítés-profil (törés-darabszámok játékos
  szerinti összegzéssel, edzői kulcs + csempe), 186.
  meccsterv-szabály (az ő válság-lövőjük × a ti sorozataitok), 207.
  edzés-szabály (válság-lövő kijelölése: vész-figura megnevezett
  befejezővel).

- **Forró kéz**: VAN-E SOROZATLÖVŐJÜK. A gólfelelős-koncentráció a
  teljes meccs eloszlását nézi — ez a sorozatokat: a csapat góljait
  időrendben olvasva megszámoljuk, ki dob egymás után többet (2+
  kétgólos sorozat vagy egy 3+ hosszú az ítélethez). A sorozatlövő
  ellen az ELSŐ gólja után kell reagálni — őrzés-váltás vagy kettőzés
  rá, mielőtt lendületbe jönne; a saját forró kezű embert tudatosan
  kell játékba hozni. Egy réteg, sok felület: `hot_hands` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (gólsorozat-lista játékos szerinti összegzéssel, edzői kulcs +
  csempe), 185. meccsterv-szabály (az ő sorozatlövőjük × a ti aktív
  védekezésetek), 206. edzés-szabály (sorozat-törő reakció: kötelező
  őrzés-váltás a gólszerzőre).

- **Kapus-hidegedés**: HIDEG KÉZZEL beesik-e a védése. A védés-esés
  az idő előrehaladtát méri — ez a ritmust: minden rá kaputra érkező
  lövésnél megnézzük, mennyi ideje nem kapott lövést a kapus, és a
  hosszú csend (3 perc) utáni lövésekre külön védés-arányt számolunk
  (vödrönként 4+ lövés, 15 százalékpont az ítélethez). A hidegen
  sebezhető kapus ellen az éheztetés fegyver — türelmes birtoklás
  után jöjjön a kidolgozott lövés; a hidegen is stabil ellen ritmusból
  kell kizökkenteni. Egy réteg, sok felület: `gk_cold_streaks` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (vödrönkénti lövés- és védés-darabszámok, két edzői kulcs +
  csempe), 184. meccsterv-szabály (az ő hideg kapusuk × a ti türelmes
  labdajáratásotok), 205. edzés-szabály (kapus-melegentartás:
  szimulált csend-blokkok, aktivitás-rutin).

- **Fal-magasság elleni játék**: MEGBÜNTETIK-E A FELFUTÓ FALAT. A
  vonal-magasság a falat írja le — ez a támadó válaszát: minden
  támadásnál megmérjük az ellenfél falának átlagos magasságát, és
  külön gólarányt számolunk a felfutó (8 m feletti) és a mély fal
  ellen vívott támadásokra (vödrönként 5+ támadás, 20 százalékpont az
  ítélethez). Akit a felfutó fal megfog, az ellen bátran ki lehet
  lépni; aki megbünteti, az ellen a mély, kompakt fal a biztonságos
  terv. Egy réteg, sok felület: `attack_vs_wall_height` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (vödrönkénti támadás- és gól-darabszámok, két edzői kulcs +
  csempe), 183. meccsterv-szabály (az ő prés-gyengeségük × a ti
  szoros védekezésetek), 204. edzés-szabály (prés elleni játék:
  kötelező folytatás a kilépő mögé).

- **Kontra-forrás**: MIBŐL INDUL a lerohanásuk. A
  lerohanás-hatékonyság azt méri, mennyi lesz gól a kontrákból — ez
  azt, honnan jönnek: minden lerohanás előtti pillanatot
  megvizsgálunk — kapus-védés, kihagyott lövés vagy labdaszerzés a
  forrás (4+ lerohanás, 50% részarány az ítélethez). Forrásonként más
  a recept: védésnél a lövés pillanatában indul a visszarendeződés,
  kihagyott lövésnél a lepattanó-fegyelem dönt, labdaszerzésnél az
  átmeneti keresztpassz tilos. Egy réteg, sok felület:
  `break_sources` motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (forrás szerinti darabszámok kulcs szerinti
  összegzéssel, edzői kulcs + csempe), 182. meccsterv-szabály (az ő
  védésből induló kontráik × a ti lövés-választásotok), 203.
  edzés-szabály (kontra-forrás zárása: forrás-specifikus
  átmenet-gyakorlat).

- **Kapus-gól veszély**: RÁDOB-E A KAPUSUK az üres kapura. A modern
  kézilabdában a 7 a 6 ára az üres kapu — megszámoljuk a
  kapus-jelölésű játékoshoz köthető kapura tartó lövéseket és gólokat
  (már 1 kísérlet jelzést ad). A gólveszélyes kapus ellen a 7 a 6
  alatt mindig legyen kijelölt visszafutó, aki labdavesztésnél
  elsőként ér a kapu síkjába; a saját csapatban a kapus rádobása
  gyakorolható fegyver. Egy réteg, sok felület: `gk_goal_threat`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (kísérlet- és gól-darabszámok, edzői kulcs +
  csempe), 181. meccsterv-szabály (az ő gólveszélyes kapusuk × a ti 7
  a 6-otok), 202. edzés-szabály (üres kapu védése: kijelölt
  visszafutó sprint a kapu síkjába).

- **Hosszú állás utáni játék**: KIZÖKKENTI-E ŐKET a hosszú
  megszakítás. Az időkérés-rétegek a rövid, kért szünetet mérik — ez
  a hosszút (sérülés, technikai állás): a megszakítások utáni két
  perc gólmérlegét számoljuk mindkét oldalra (2+ hosszú állás, 2
  gólos különbség az ítélethez). A kizökkenő csapat ellen az
  újraindítás a ti pillanatotok — kész figurával és letámadással; a
  meglóduló ellen az első védekezés kapjon extra figyelmet. Egy
  réteg, sok felület: `long_break_response` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (állás- és
  gól-darabszámok, két edzői kulcs + csempe), 180. meccsterv-szabály
  (az ő kizökkenő újrakezdésük × a ti figura-kincsetek), 201.
  edzés-szabály (újraindulás-rutin: váratlan állások + kötelező
  visszatérési protokoll).

- **Hajrá-labdabirtoklás**: EGY KÉZBEN VAN-E a végjátékuk. A
  hajrá-ötös azt mondja meg, kik vannak fent a végén, a hajrá-emberek
  azt, ki lő — ez azt, kinél van a labda: az utolsó öt perc labdás
  kockáit játékosonként számoljuk (200+ mért kocka, 35% részesedés az
  ítélethez). Az egy kézben futó végjáték ellen a hajrá-kettőzés a
  recept — nem a lövőket kell fogni, hanem A kezet. Egy réteg, sok
  felület: `clutch_ball_hogs` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (játékosonkénti hajrá-kockák
  összegzéssel, edzői kulcs + csempe), 179. meccsterv-szabály (az ő
  egy kézben futó végjátékuk × a ti labdaszerzésetek), 200.
  edzés-szabály (második játékszervező: kétindítású hajrá-figurák,
  csali-szerep).

- **Negyedóra-profil**: MELYIK MECCS-SZAKASZ AZ ÖVÉK az óra szerint.
  A sorozat-elemzés esemény-alapú — ez óra-alapú: a gólokat 15 perces
  negyedórákba soroljuk, és negyedóránként gólkülönbséget számolunk
  (40+ mért perc, 3 gólos különbség az ítélethez). Az erős
  negyedórájuk előtt kell a saját időkérés és a friss sor; a gyenge
  negyedórájukra tempót kell időzíteni, mert ott esnek szét. Egy
  réteg, sok felület: `quarter_profile` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (negyedóránkénti
  gól-darabszámok kulcs szerinti összegzéssel, két edzői kulcs +
  csempe), 178. meccsterv-szabály (az ő gyenge negyedórájuk × a ti
  mély rotációtok), 199. edzés-szabály (negyedóra-terv: előre beírt
  csere-hullám és időkérés-pont a hullámvölgyre).

- **Beálló-őr**: KI ŐRZI az ellenfél beállóját. A beálló-védekezés
  azt mondja meg, mennyire bírja a fal a beállót — ez azt, ki a
  felelőse: felállt védekezésben megkeressük a becsült beállóhoz
  legközelebbi védőt (3 m-en belül; 300+ őrzés-kocka, 60% részesedés
  az ítélethez). Ha az őrzés egy emberen áll, az elzárást rá kell
  vinni — ha őt kihúzzák, a beálló felszabadul, és a besegítés rendje
  is borul. Egy réteg, sok felület: `pivot_guards` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (védőnkénti őrzés-kockák játékos szerinti összegzéssel, edzői kulcs
  + csempe), 177. meccsterv-szabály (az ő egy-emberes beálló-őrzésük
  × a ti elzárásaitok), 198. edzés-szabály (beálló-őrzés váltásban:
  kötelező elöl-mögött csere hangos jelzéssel).

- **Időkérés-csomag**: AZ IDŐKÉRÉSÜK CSERÉVEL JÁR-E. Az
  időkérés-hatás azt méri, mit hoz az időkérés — ez azt, mi van
  benne: az időkérés körüli percben keresünk azonos-csapatbeli
  cserehullámot (2+ időkérés, 70% arány az ítélethez). A cserélő
  időkérés után frissíteni kell a párosítást — friss lábú ember jön;
  a csere nélküli időkérés tiszta taktika: ugyanazok jönnek vissza új
  figurával, a fal extra figyelmet kapjon. Egy réteg, sok felület:
  `timeout_sub_combo` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (időkérés- és csere-darabszámok,
  két edzői kulcs + csempe), 176. meccsterv-szabály (az ő cserélő
  időkérésük × a kiszámítható váltópárjuk), 197. edzés-szabály
  (időkérés-eszköztár: kötelező döntés-lista minden időkéréshez).

- **Lövés-választás állás szerint**: HÁTRÁNYBAN ELKAPKODJÁK-E. Az
  előny-kezelés a támadás-hosszot méri állás szerint — ez a
  lövés-minőséget: a leadott lövések átlagos helyzet-értékét (xG)
  külön számoljuk hátrányban és egyébként (állapotonként 5+ lövés,
  0,08 xG-különbség az ítélethez). A hátrányban kapkodó csapat ellen
  a vezetés önmagát védi — a rossz lövéseik nektek dolgoznak; a
  hátrányban is türelmes ellen a vezetés sosem biztonságos. Egy
  réteg, sok felület: `shot_quality_by_score` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (állapotonkénti lövés- és helyzetérték-összegek, két edzői kulcs +
  csempe), 175. meccsterv-szabály (az ő kapkodó lövéseik × a ti gyors
  gólra váltásotok), 196. edzés-szabály (helyzet-válogatás nyomás
  alatt: zöld/piros minősített lövések hátrányból indulva).

- **Kapus állás szerint**: HÁTRÁNYBAN FELJAVUL vagy ÖSSZEESIK-E a
  kapusuk. A védés-esés az idő szerint bontja a kapus teljesítményét
  — ez az állás szerint: a rá kaputra érkezett lövéseket
  szétválasztjuk aszerint, hogy a csapata épp hátrányban volt-e
  (állapotonként 4+ lövés, 15 százalékpont az ítélethez). A
  hátrányban feljavuló kapusra vezetésnél csak kidolgozott helyzetet
  szabad lőni — a bravúrjaiból lendület lesz; az összeeső kapusra
  bátran jöhet a távoli lövés is. Egy réteg, sok felület:
  `gk_saves_by_score` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (állapotonkénti lövés- és
  védés-darabszámok, két edzői kulcs + csempe), 174.
  meccsterv-szabály (az ő összeeső kapusuk × a ti lövőerőtök), 195.
  edzés-szabály (kapus-újraindítás: gól utáni rutin-protokoll,
  hátrány-szimulált védés-sorozat).

- **Szorult játék**: HÁTRÁNYBAN mennyire húzzák szét a pályát. A
  támadás-szélesség a teljes meccs átlagát adja — ez állás szerint
  bontja: külön mérjük a támadók oldalirányú terjedelmét hátrányban
  és egyébként (állapotonként 100+ kocka, 2 m különbség az
  ítélethez). A hátrányban beszűkülő csapat ellen vezetésnél
  tömöríteni kell a falat — a szélsőik maguktól kikapcsolódnak; a
  kinyíló ellen a szélső-védelem és a kifutás dönt. Egy réteg, sok
  felület: `width_by_score` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (állapotonkénti kocka- és
  szélesség-összegek, két edzői kulcs + csempe), 173.
  meccsterv-szabály (az ő beszűkülő támadásuk × a ti blokkjaitok),
  194. edzés-szabály (szélesség nyomás alatt: hátrányból induló
  meccs, kötelező kétszélsős támadás).

- **Visszaállás**: MI TÖRTÉNIK, AMIKOR VISSZAÉR a kiállított ember.
  Az emberelőny-hatékonyság a kiállítás alatti játékot méri — ez az
  utánit: a kiállítás letelte utáni perc gólmérlege a visszaálló
  csapat szemszögéből (2+ mért visszaállás, 2 gólos különbség az
  ítélethez). Aki a visszaállásnál megzavarodik, annál a lejáró
  kiállítás az ellenfél támadás-jelzése; aki feltámad, annál a
  visszaérés utáni első támadást kell megfogni. Egy réteg, sok
  felület: `post_powerplay` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (visszaállás- és gól-darabszámok,
  két edzői kulcs + csempe), 172. meccsterv-szabály (az ő zavaros
  visszaállásuk × a ti figura-kincsetek), 193. edzés-szabály
  (visszaállás-rend: koreografált visszaérkezés, biztonsági első
  labda).

- **Poszt-hibák**: MELYIK POSZTJUK veszíti el a labdát. A labdaeladók
  a hibázó embert nevezik meg, a hiba-zónák a helyet — ez a posztot:
  a labdaeladásokat a vesztes becsült posztjához kötjük (6+ eladás,
  40% részarány, holtverseny nélkül), így a minta akkor is látszik,
  ha a nevek meccsről meccsre cserélődnek. Ez mondja meg, melyik
  passzsávban érdemes zavarni: beállónál a bejátszás-vonalra lépés,
  irányítónál a felső kettőzés, szélsőnél a szélső-bejátszások
  vadászata. Egy réteg, sok felület: `turnovers_by_role` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (poszt szerinti darabszámok kulcs szerinti összegzéssel, edzői
  kulcs + csempe), 171. meccsterv-szabály (az ő hibázó posztjuk × a
  ti passzsáv-zárásotok), 192. edzés-szabály (poszt-labdabiztonság:
  célzott blokk az érintett posztnak).

- **Futás-mérleg**: MELYIK CSAPAT FUTJA TÚL a másikat. A
  játékos-statisztika terhelés-monitor — ez a csapat-olvasata: a
  mezőnyjátékosok mért futott távját csapatonként összegezzük, és
  összevetjük a két oldalt (10+ mért perc, 10% táv-többlet az
  ítélethez). A futócsapattal nem szabad futóversenyt vállalni —
  lassított tempó, felállt fal; a keveset futó ellen a tempó a
  fegyver: gyors középkezdés, korai indítások, második hullám. Egy
  réteg, sok felület: `distance_battle` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (táv- és perc-összegek,
  két edzői kulcs + csempe), 170. meccsterv-szabály (az ő kifutott
  lábuk × a ti tempótok), 191. edzés-szabály (futás-mérleg:
  intervallum-alap + kötelező három sprint-lépés hátra).

- **Egyirányú játékosok**: KI JÁTSZIK CSAK VÉDEKEZNI vagy CSAK
  TÁMADNI. A csere-blokkok azt mondják meg, egységekben cserélnek-e —
  ez azt, kik az egységek: játékosonként megszámoljuk, a pályán
  töltött kockáiból mennyi esett a csapata védekezésére (1500+ kocka,
  75% részarány a specialistához). Ha védő- és támadó-specialista is
  van, a csapat váltott sorokkal játszik — a csere pillanatában
  sebezhető: a gyors középkezdés rossz embereket talál a pályán, a
  fent ragadt támadót pedig meg kell támadni. Egy réteg, sok felület:
  `phase_specialists` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (játékosonkénti fázis-kockák
  összegzéssel, edzői kulcs + csempe), 169. meccsterv-szabály (az ő
  váltott soraik × a ti gyors középkezdésetek), 190. edzés-szabály
  (sorváltás-ütem: stopperes váltás, névre szólóan jelzett fent
  ragadt emberek).

- **Sprint-veszély**: KI VISZI A KONTRÁT. A sprint-statisztika
  terhelés-monitornak készült — ez az ellenfél-olvasata: csapatonként
  kigyűjtjük, ki hányszor sprintel, és van-e ember, akire a csapat
  sprintjeinek nagy része jut (10+ csapat-sprint, 30% részesedés). A
  kézilabdában a sprint szinte mindig átmenet: aki a legtöbbet
  sprintel, az a lerohanások motorja — ellene névre szóló
  fékező-feladat kell, és tilos őt a fal mögé engedni. Egy réteg, sok
  felület: `sprint_threats` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (játékosonkénti sprint-darabszámok
  és -távok összegzéssel, edzői kulcs + csempe), 168.
  meccsterv-szabály (az ő kontra-emberük × a ti lassú
  felhozatalotok), 189. edzés-szabály (kontra második hulláma:
  lezárt első kifutó, kötelező második hullám).

- **Hetesre cserélt kapus**: HOZNAK-E SPECIALISTÁT a büntetőkre. A
  kapus-csere hatása az általános váltást méri — ez a célzottat: az
  ellenük megítélt heteseknél megnézzük, hogy a védő kapus szolgálata
  épp a hetes előtt (45 mp-en belül) kezdődött-e (2+ célzott csere az
  ítélethez). A specialista ellen a hetes-lövő a BEUGRÓ kapus
  szokásaira készüljön, és várja ki a lövést; a saját csapatban a
  beugró hideg-rutinja és a visszacsere üteme az edzés-téma. Egy
  réteg, sok felület: `seven_keeper_swaps` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (hetes- és
  csere-darabszámok, edzői kulcs + csempe), 167. meccsterv-szabály
  (az ő hetes-kapuscseréjük × a ti kiharcolt heteseitek), 188.
  edzés-szabály (hetes-kapus rutin: hidegről érkező beugró, órával
  gyakorolt csere-ütem).

- **Kilépő védő**: VAN-E ELŐRETOLT EMBERÜK a falban, és ki az. A
  vonal-magasság a fal átlagos helyét adja — ez a fal alakját:
  felállt védekezésben játékosonként mérjük a saját kaputól vett
  átlagos távolságot, és megnézzük, van-e a társai átlagánál legalább
  2,5 méterrel előrébb álló védő (az 5-1 vagy 3-2-1 kilépője; 3+ mért
  védő kell). A kilépő háta mögött nyílik a tér — elzárást kell rá
  vinni, és a mögé befutó emberrel 2 az 1-et játszani; a saját
  csapatban a kilépő mögötti biztosítás külön edzés-téma. Egy réteg,
  sok felület: `advanced_defender` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (védőnkénti kocka- és
  mélység-összegek, edzői kulcs + csempe), 166. meccsterv-szabály (az
  ő kilépő védőjük × a ti elzárás-használatotok), 187. edzés-szabály
  (kilépő mögötti biztosítás: hangos belső-váltás, kötelező hát mögé
  játszás).

- **Középkezdés-átvevő**: KINÉL indul újra a játék a kapott gól után.
  A középkezdés-tempó azt méri, milyen gyorsan ér át a labda — ez
  azt, kinél: a kapott gól utáni ablakban megkeressük a gólt kapó
  csapat első, felező-környéki labdabirtokosát (4+ mért újraindítás,
  50% részesedés a fix átvevőhöz). A fix átvevőjű csapat ellen a gól
  utáni letámadásnak névre szóló célpontja van — az átvevőt kell
  lefogni, és a középkezdésük megáll; a saját csapatban a
  kiszámítható átvevő variálandó. Egy réteg, sok felület:
  `restart_targets` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (újraindítás-darabszám +
  átvevő-lista összegzéssel, edzői kulcs + csempe), 165.
  meccsterv-szabály (az ő fix átvevőjük × a ti gól utáni
  letámadásotok), 186. edzés-szabály (középkezdés-variálás: két
  bejáratott átvevő + üresen kifutó harmadik).

- **Váltópárok**: KI KIT VÁLT a cseréknél. A csere-blokkok azt
  mondják meg, egységekben vagy egyesével cserélnek — ez azt, ki kit:
  az egy-ki-egy-be hullámokból párokat képzünk (mezszám szerint, ha
  az OCR kiolvasta), és megnézzük, van-e ismétlődő páros (4+ mért
  csere, 3+ ismétlődés). A kiszámítható váltópár kettőt is ér: a
  beálló emberre kész B-terv készíthető, és amikor a kulcsemberük
  fárad, előre tudni, ki jön. Egy réteg, sok felület: `swap_pairs`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (csere-darabszám + páros-lista összegzéssel,
  edzői kulcs + csempe), 164. meccsterv-szabály (az ő kiszámítható
  váltópárjuk × a ti mély rotációtok), 185. edzés-szabály
  (csere-variálás: két különböző profilú váltó, helyzethez kötve).

- **Visszahozott támadások**: LEZÁRJÁK vagy ÚJRAJÁRATJÁK a betörést.
  A betörés-folyosók azt mondják meg, hol lép be a labda a 9 méteren
  belülre — ez azt, mi lesz belőle: lövéssel zárul-e az epizód, vagy
  a csapat lövés nélkül visszahozza a labdát (6+ betörés; 45% felett
  türelmes, 15% alatt direkt lezárás; a labdavesztéses epizódok nem
  számítanak). A visszahozó csapat ellen a fal kivárhat — jön a
  passzív jel; a direkt lezáró ellen az első belépést kell
  megállítani, korai besegítéssel. Egy réteg, sok felület:
  `pullback_rate` motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (betörés- és visszahozás-darabszámok, két edzői
  kulcs + csempe), 163. meccsterv-szabály (az ő türelmes
  visszahozásaik × a ti fegyelmezett falatok), 184. edzés-szabály
  (betörés-lezárás: kötelező lezárás a 9-esen belül, tiltott
  visszapassz).

- **Szerzés utáni indítás**: AZONNAL ELŐRE megy-e a szerzett labda. A
  labdaszerzők azt mondják meg, ki szerez, a labdaszerzés-típus azt,
  hogyan — ez azt, mi történik utána: a szerzés utáni 4 másodpercben
  legalább 6 métert halad-e előre a labda a támadási irányban (6+
  szerzés; 60% felett azonnali, 25% alatt biztosító indítás). Az
  azonnal induló ellen a labdavesztés pillanatára kész terv kell —
  fékező ember, sprint hátra, semmi reklamálás; a biztosító ellen
  labdavesztés után van idő rendezni a letámadást. Egy réteg, sok
  felület: `steal_launch` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (szerzés- és előre-darabszámok, két
  edzői kulcs + csempe), 162. meccsterv-szabály (az ő biztosításuk ×
  a ti visszatámadásotok), 183. edzés-szabály (szerzésből indítás:
  3 másodperces előre-szabály, sprintelő szélsőkkel).

- **Hetes-fáradás**: MIKOR ADJÁK a heteseket. A hetes-adók azt
  mondják meg, ki ellen ítélik, a szabálytalanság-fáradás a
  kiállítások idejét — ez a hetesekét: a csapat által adott heteseket
  félidőnként számoljuk (4+ hetes, 2-es félidők közti többlet az
  ítélethez). Aki a második félidőben adja, az fáradva már kézzel véd
  — a szünet után be kell vinni a labdát a testre; aki az elején, az
  hidegen kapkod — az első percekben kell a beállóst és a betörést
  erőltetni. Egy réteg, sok felület: `sevens_fade` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (félidőnkénti darabszámok, két edzői kulcs + csempe), 161.
  meccsterv-szabály (az ő fáradva adott heteseik × a ti beállós
  játékotok), 182. edzés-szabály (hetes nélküli hajrá: fáradt
  test-védekezés hát mögötti kézzel).

- **Fal-fáradás**: MELYIK FÉLIDŐBEN nyílik ki a fal. A kapott
  helyzetek minősége a teljes meccset nézi — ez félidőnként: a csapat
  ellen leadott lövések átlagos helyzet-értékét külön mérjük a két
  félidőben (félidőnként 5+ lövés, 0,08 xG-változás az ítélethez). A
  második félidőre kinyíló fal ellen a belső játékot (beállós,
  betörés) a második félidőre kell tartogatni; az összeálló fal ellen
  az első félidőben kell megszerezni az előnyt, mert a szünet után
  bezár a bolt. Egy réteg, sok felület: `wall_fade` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (félidőnkénti darabszám + helyzetérték-összeg, két edzői kulcs +
  csempe), 160. meccsterv-szabály (az ő kinyíló faluk × a ti
  betöréseitek), 181. edzés-szabály (fal-állóképesség: védekezés
  fáradtan, hangos belső-váltásokkal).

- **Pad-gólok**: A KISPAD IS TERMEL-E, vagy csak a kezdők. A kezdő
  hatos azt mondja meg, kikkel kezdenek, a rotáció azt, hányan
  játszanak — ez azt, ki szerzi a gólokat: a lövőhöz köthető gólokat
  kettéosztjuk a kezdő mag és a padról beállók között (6+ gól; 35%
  felett mély, 10% alatt csak-kezdők termelés). Akinél csak a kezdők
  termelnek, azt fárasztani kell — pörgetett tempó mellett a hat
  emberük a második félidőre elfogy; akinél a pad is termel, ott
  minden sorra névre szóló párosítás-terv kell. Egy réteg, sok
  felület: `bench_scoring` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (gól-darabszámok, két edzői kulcs +
  csempe), 159. meccsterv-szabály (az ő csak-kezdők termelésük × a ti
  mély rotációtok), 180. edzés-szabály (pad-termelés: a második sor
  zárja a félidőket, duplán érő hajrá-gólokkal).

- **Labdaszerzés-típus**: ELFOGJÁK vagy LESZERELIK a labdát. A
  labdaszerzők azt mondják meg, ki szerez, az elöl szerzők azt, hol —
  ez azt, hogyan: ha a birtokos-váltás előtt a labda röptében járt
  (senkinél sem volt), a szerzés passz-elfogás; ha kézből kézbe
  került, testre szerelés (6+ szerzés; 60% felett sáv-záró, 25% alatt
  testre menő). A sáv-záró ellen keresztbe lebegtetni tilos — rövid,
  közvetlen passzok és betörések kellenek; a testre menő ellen a
  gyors labdajáratás a fegyver, és a keresztpassz vállalható. Egy
  réteg, sok felület: `steal_types` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (szerzés- és
  elfogás-darabszámok, két edzői kulcs + csempe), 158.
  meccsterv-szabály (az ő testre menő védekezésük × a ti
  széljátékotok), 179. edzés-szabály (passzsáv-olvasás:
  árnyék-védekezés kontakt nélkül, elfogás után azonnali indítással).

- **Kapott helyzetek minősége**: MILYEN LÖVÉSEKET ENGED a fal. A saját
  lövés-választást a match_xg lövésenkénti átlaga mutatja — ez a másik
  oldal: a csapat ELLEN leadott lövések átlagos helyzet-értéke. Nem
  azt méri, mennyit kapnak, hanem hogy egy-egy lövés mennyire volt
  ziccer (8+ kapott lövés; 0,35 felett nagy, 0,22 alatt nehéz
  helyzetek). Aki nagy helyzeteket enged, ott befelé kell játszani —
  beállós, áttörés, elzárás után kapott labda; aki csak nehezet, annál
  a 9 méteres lövés ajándék nekik: keresztmozgással, elzárással kell
  embert kihúzni. Egy réteg, sok felület: `conceded_chance_quality`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (lövés-darabszám + helyzetérték-összeg, két edzői
  kulcs + csempe), 157. meccsterv-szabály (az ő nagy helyzeteket
  engedő faluk × a ti beállós játékotok), 178. edzés-szabály (hatos
  előtti tér: szendvicsben tartott beálló, kettőzés az áttörő elé).

- **Félidő-zárás**: MIT KEZDENEK AZ UTOLSÓ LABDÁVAL. A hajrá-mérleg
  az utolsó perceket méri, a félidő-nyitás a kezdést — ez a két
  félidő utolsó 60 másodpercét: hány támadásuk indul ott, és hányból
  lesz gól (3+ záró támadás; 50% felett jó, 15% alatt elpuskázott
  kezelés). Aki a záró labdát gólig viszi, annál a félidő végén nem
  szabad idő előtt lőni — az órát ki kell húzni; aki elpuskázza,
  annál a záró támadás ajándék, nyugodtan vissza lehet adni a labdát.
  Egy réteg, sok felület: `closing_attacks` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (támadás- és
  gól-darabszámok, két edzői kulcs + csempe), 156. meccsterv-szabály
  (az ő jól kezelt záró labdájuk × a ti pontos lövés-időzítésetek),
  177. edzés-szabály (záró labda: óra elleni gyakorlat, lövés csak az
  utolsó 8 másodpercben).

- **Lerohanás-hatékonyság**: MENNYI LESZ GÓL a kontráikból. A
  lerohanás-arány azt mondja meg, milyen gyakran kontráznak, a
  kontra-befejezők azt, ki zárja le őket — ez azt, megy-e be: a
  lerohanásnak címkézett támadás-szakaszokból hányat zárt le a csapat
  gólja (5+ lerohanás; 65% felett éles, 35% alatt elpuskázott
  befejezés). Aki élesen fejez be, ott a visszarendeződés fegyelme
  dönt — kijelölt fékező ember, és lövés után senki nem marad elöl;
  aki elpuskázza, annál a kontra ajándék, nyugodtan rá lehet engedni.
  Egy réteg, sok felület: `fast_break_conversion` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (lerohanás- és gól-darabszámok, két edzői kulcs + csempe), 155.
  meccsterv-szabály (az ő elpuskázott kontráik × a ti kevés elöl
  elvesztett labdátok), 176. edzés-szabály (kontra-befejezés: fogyó
  létszámú 2-1 és 3-2 fáradtan, kimondott döntéssel).

- **Félidő-nyitás**: HOGYAN INDULNAK a két félidő első 5 percében. A
  félidő-mérleg a teljes félidőt méri, a hajrá-mérleg az utolsó
  perceket — ez a kezdést: a meccs és a második félidő első 300
  másodpercében szerzett és kapott gólokat összegezzük (4+ gól,
  2 gólos különbség az ítélethez). Aki jól nyitja a félidőket,
  bemelegítésből és öltözői beszédből él — ellene az első öt percben
  a hibátlan játék a legfontosabb; aki lassan indul, annál pont az
  első öt percben kell rámenni a vezetésért. Egy réteg, sok felület:
  `half_openings` motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (gól-darabszámok, két edzői kulcs + csempe), 154.
  meccsterv-szabály (az ő lassú félidő-nyitásuk × a ti gyors
  kezdéseitek), 175. edzés-szabály (félidő-nyitás: élesben induló
  "első öt perc" blokk, külön a szünet utáni kezdéssel).

- **Időkérés utáni védekezés**: MEGÁLL-E A FAL a megszakítás után.
  Az időkérés utáni első támadás azt méri, mit kezd a saját
  támadásával az időt kérő csapat — ez a másik oldalt: az időkérést
  kérő csapat védekezését nézzük az újraindítás után, és
  megszámoljuk, hányszor kapott gólt az ellenfél első rohamából (3+
  időkérés; 60% felett szivárgó, 20% alatt friss fal). Ha az
  időkérésük után rendre gólt kapnak, a megszakítás náluk nem a
  védekezésről szólt — azonnal, felállás nélkül kell támadni ellenük;
  ha a faluk megáll, ott a gyors roham veszteség, kivárás kell. Egy
  réteg, sok felület: `timeout_first_defense` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (időkérés-darabszámok, két edzői kulcs + csempe), 153.
  meccsterv-szabály (az ő időkérés utáni szivárgó faluk × a ti gyors
  indításaitok), 174. edzés-szabály (időkérés utáni védekezés:
  minden figura-megbeszélés után a kiosztás hangos ismétlése).

- **Gól utáni letámadás**: SAJÁT GÓL UTÁN feljebb megy-e a fal. A
  védekezési vonal magassága a teljes meccs átlagát adja — ez azt,
  hogy a csapat a saját gólja utáni 20 másodpercben magasabban
  védekezik-e, mint egyébként (60+ mért kocka mindkét oldalon, 1,5 m
  eltérés az ítélethez). Aki gól után letámad, annál a kapott gól
  utáni kihozatalt előre meg kell tervezni — hosszú indítás a
  kapustól vagy előre kilépő, biztos kezű átvevő; aki gól után
  visszahúzódik, annál pont ilyenkor lehet nyugodtan felhozni a
  labdát. Egy réteg, sok felület: `press_after_goal` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (kocka-darabszámok + méter-összegek, két edzői kulcs + csempe),
  152. meccsterv-szabály (az ő gól utáni letámadásuk × a ti gyors
  kapus-indításaitok), 173. edzés-szabály (gól utáni letámadás:
  góllövés után azonnal letámadásba forduló 6-6, egy hátul maradó
  emberrel).

- **Felhozatal-idő**: MILYEN GYORSAN érnek a támadó térfélre. A
  középkezdés-tempó csak a kapott gól utáni újraindítást méri, a
  kihozatal-oldal azt, hol jön át a labda — ez azt, mennyi idő alatt:
  minden birtoklás-kezdéstől mérjük, hány másodperc múlva lép át a
  labda a támadó térfélre (5+ mért felhozatal; 7 mp felett lassú, 4 mp
  alatt gyors). A lassan felhozó ellen van idő rendezetten felállni —
  ott a fal szervezése dönt, nem a visszafutás; a gyorsan felhozó
  ellen a lövés pillanatában már indulni kell hátra, és kijelölt
  fékező ember kell. Egy réteg, sok felület: `buildup_time` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (darabszám + másodperc-összeg, két edzői kulcs + csempe), 151.
  meccsterv-szabály (az ő lassú felhozataluk × a ti kevés szabad
  lövést engedő falatok), 172. edzés-szabály (gyors felhozatal:
  stopperes kihozatal-gyakorlat, cél a felezővonal 4 mp alatt).

- **Kapus-bevonás**: MENNYIRE JÁTSZANAK VISSZA a kapusnak. Az
  indítás-sebesség a védés utáni indítást méri, a kihozatal-oldal azt,
  hol jön át a labda — ez azt, hogy a támadás-építésbe bevonják-e a
  kapust: birtoklási szakaszonként (a kihozatalt is beleértve)
  megnézzük, volt-e a kapusuk labdabirtokos (8+ szakasz; 25% felett
  sok, 5% alatt semennyi). Aki sokat játszik vissza, annál a
  letámadásnak a kapusra is ki kell terjednie; aki soha, annál a
  passzsávokat kell zárni. Egy réteg, sok felület:
  `keeper_involvement` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (szakasz-darabszámok + két edzői
  kulcs + csempe), 150. meccsterv-szabály (az ő kapusra
  visszajátszásuk × a ti elöl szerzett labdáitok), 171. edzés-szabály
  (kapus a kihozatalban: rövid és hosszú megoldás, hangos jelzéssel).
- **Fedezetten lövők**: KI HÚZZA EL a ravaszt nyomás alatt is. A
  nyomás alatti befejezés csapat-szinten mondja meg, mennyit érnek a
  fedezett lövéseik — ez azt, ki vállalja őket: lövőnként a lövések és
  azok közül a fedezettek (5+ lövés, 60% feletti fedezett aránynál).
  Aki fedezetten is lő, alacsony értékű befejezéseket ad — rá nem kell
  kilépni, elég a blokk-kéz és a kapus mögé rendezett fal. Egy réteg,
  sok felület: `covered_shooters` motor, edzői összefoglaló, /analyze
  + meccs-csomag, felderítés-profil (játékosonkénti lövés- és
  fedezett-darabszámok + edzői kulcs + csempe), 149.
  meccsterv-szabály (az ő fedezetten lövő emberük × a ti blokkjaitok),
  170. edzés-szabály (lövés-választás nyomás alatt: fedezett
  helyzetből tilos lőni).
- **Pressz-érzékeny játékosok**: KI VESZÍTI EL a labdát szorításban.
  A pressz-tűrés csapat-szinten mondja meg, mennyivel nő az eladás
  testközeli védő mellett — ez játékosonként bontja: emberenként a
  nyomott labdás döntések és azok közül az eladások (5+ nyomott
  döntés, 30% feletti eladás-aránynál). A pressz-érzékeny emberre kell
  küldeni a kettőzést: nála a szorítás nem kockázat, hanem
  labdaszerzés. Egy réteg, sok felület: `pressure_sensitive_players`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (játékosonkénti darabszámok + edzői kulcs +
  csempe), 148. meccsterv-szabály (az ő pressz-érzékeny emberük × a ti
  kettőzésetek), 169. edzés-szabály (nyomás alatti kiadás: egy
  érintés, a szorítás ellenkező oldalára).
- **Elöl szerző védők**: KI SZED LABDÁT a támadó térfélen. A
  labdaszerzők azt mondják meg, ki szerzi a labdákat, a
  szerzés-magasság azt, hol történik ez csapat-szinten — ez a kettő
  kereszteződése: játékosonként hány szerzés születik a saját támadó
  térfélen (3+ szerzés, 50% feletti elöl-aránynál). Az elöl szedő
  ember oldalán nem szabad a kihozatalt vezetni: a kapus a másik
  oldalra indítson. Egy réteg, sok felület: `high_steal_players`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (játékosonkénti szerzés-darabszámok + edzői kulcs
  + csempe), 147. meccsterv-szabály (az ő elöl szedő védőjük × a ti
  kihozatal-oldalatok), 168. edzés-szabály (letámadás a szerzőnk köré).
- **Pontatlan lövők**: KINEK a lövései mennek mellé. A
  célzás-pontosság csapat-szinten mondja meg, a lövéseikből mennyi
  tart kapura — ez játékosonként bontja: lövőnként a kísérletek és a
  kaput elkerülő lövések (5+ lövés, 40% feletti mellé-aránynál).
  Akinek a lövései rendre elkerülik a kaput, arra rá lehet engedni a
  lövést: nála a kilépés fölösleges kockázat, és a mellé lövés utáni
  kidobás azonnali indítás. Egy réteg, sok felület:
  `wasteful_shooters` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (játékosonkénti lövés- és
  mellé-darabszámok + edzői kulcs + csempe), 146. meccsterv-szabály
  (az ő pontatlan lövőjük × a ti gyors kapus-indításotok), 167.
  edzés-szabály (kapura tartó lövés: célzás-blokk, fáradtan is).
- **Kezdő hatos**: KIKKEL KEZDENEK. A nyitány-profil azt mondja meg,
  hogyan indítják a meccset, a hajrá-ötös azt, kikkel zárják — ez a
  másik vége: az első öt percben játékosonként a pályán töltött kockák
  (a kezdő mag 100+ mért kockától). Így az első támadásokra név
  szerinti terv készíthető, és látszik, kit tartogatnak a kispadon a
  hajrára. Egy réteg, sok felület: `opening_lineup` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (játékosonkénti kocka-darabszámok + edzői kulcs + csempe), 145.
  meccsterv-szabály (az ő kezdő hatosuk × a ti akadozó nyitányotok),
  166. edzés-szabály (nyitó figurák: az edzés elején, hidegen, ezzel a
  felállással).
- **Hetes-kiharcolás poszt szerint**: MELYIK POSZTRÓL rántják le
  őket. A hetes-kiharcolók azt mondják meg, kit rántanak le — ez azt,
  milyen poszton: a kiharcolókat a poszt-becsléshez kötjük (3+
  poszthoz kötött hetes, 50%-os vezető poszt, holtverseny nélkül). Ha
  a hetesek zöme a szélsőikről jön, a szélső-védekezésnél tilos a kéz;
  ha a beállótól, az elé állást kell gyakorolni. Egy réteg, sok
  felület: `seven_earner_roles` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (posztonkénti darabszámok + edzői
  kulcs a poszthoz illő utasítással + csempe), 144. meccsterv-szabály
  (az ő hetes-kiharcolásuk posztja × a ti hetes-okozó védőtök), 165.
  edzés-szabály (kéz nélküli védekezés az adott poszt ellen).
- **Időkérés utáni első támadás**: VAN-E KÉSZ FIGURÁJUK. Az
  időkérés-mérleg azt mondja meg, megtörte-e a megszakítás a
  sorozatot, az időkérés-időzítés azt, mikor kérnek időt — ez azt, mit
  kezdenek vele: az időkérést kérő csapat első támadását nézzük az
  újraindítás után (3+ időkérés; 60% felett kész figura, 20% alatt
  üres időkérés). Aki rendre betalál, arra a támadásra előre fel kell
  készülni (kijelölt védekezés, a beállójuk elé állás); akinél elhal,
  ott elég a szokásos fal. Egy réteg, sok felület:
  `timeout_first_attack` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (időkérés- és gól-darabszámok + két
  edzői kulcs + csempe), 143. meccsterv-szabály (az ő időkérés utáni
  figurájuk × a ti időkérés-mérlegetek), 164. edzés-szabály (időkérés
  utáni figura: két-három bejátszott záró-figura, 20 másodperces
  megbeszéléssel).
- **Kockázatos passzolók**: KINEK a hosszú labdái foghatók el. A
  passz-kockázat csapat-szinten mondja meg, a hosszú passzaik
  gyakrabban vesznek-e el — ez játékosonként bontja: a hosszú
  továbbítási kísérleteket és azok közül az eladásokat a kiinduló
  játékoshoz írjuk (4+ hosszú kísérlet, 40% feletti eladás-aránynál).
  Az ő passzsávjába kell beállni: a letámadás és a sávba lépés nála
  azonnal labdát hoz. Egy réteg, sok felület: `risky_passers` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (játékosonkénti kísérlet- és eladás-darabszámok + edzői kulcs +
  csempe), 142. meccsterv-szabály (az ő kockázatos passzolójuk × a ti
  elöl szerzett labdáitok), 163. edzés-szabály (hosszú passz
  technikája: mellmagasságban, a futó társ elé vezetve).
- **Elzárók**: KI ÁLL ELZÁRÁSBA a lövőik előtt. Az elzárás-használat
  azt mondja meg, a lövéseik mekkora része jön elzárásból — ez azt, ki
  zár el: lövésenként a lövő őrzője mellett álló csapattársat
  jegyezzük fel elzáróként (3+ elzárástól). Az ő oldalán kell a
  váltás-kommunikáció: hangos váltás vagy átcsúszás, és elölről kell
  fogni, mert nélküle a lövőjük nem marad tisztán. Egy réteg, sok
  felület: `screen_setters` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (játékosonkénti elzárás-darabszámok
  + edzői kulcs + csempe), 141. meccsterv-szabály (az ő fő elzárójuk ×
  a ti elzárás-védekezésetek), 162. edzés-szabály (változatos
  elzárás-játék: minden támadásban más elzáró, leválással).
- **Kapus-bemelegedés**: HOGYAN VÉD a meccs első tíz percében. A
  kapus-forma félidőnként a fáradást méri, a nyitány-profil a csapat
  meccskezdését — ez a kapus meccskezdése: a kapura tartó lövéseket
  szétválasztjuk az első tíz percre és a maradékra (szakaszonként 4+
  lövés, 15 százalékpontos eltérésnél). A lassan bemelegedő kapus
  ellen az elején bátran kell lőni (ott a legolcsóbb a gól), az
  azonnal formában lévő ellen türelmesen, biztos helyzetekre. Egy
  réteg, sok felület: `gk_early_saves` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (szakaszonkénti lövés- és
  védés-darabszámok + két edzői kulcs + csempe), 140.
  meccsterv-szabály (az ő lassan bemelegedő kapusuk × a ti nyitó
  góljaitok), 161. edzés-szabály (meccs eleji készenlét: terheléses
  kapus-bemelegítés a kezdés előtt).
- **Emberhátrány-lövők**: KI VÁLLALJA a befejezést öt emberrel. Az
  emberhátrány-támadás azt mondja meg, mennyit érnek a két perc alatt,
  az emberhátrány-forma azt, milyen falat húznak — ez azt, ki lő
  ilyenkor: a kiállítás-ablakokban a hátrányban lévő csapat lövéseit a
  lövőhöz írjuk (2+ lövéstől). Emberelőnyben ő a kontra-fenyegetés: az
  ő oldalán kell a labdabiztonság, és mögötte maradjon egy ember
  biztosításban. Egy réteg, sok felület: `shorthanded_shooters` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (játékosonkénti lövés- és gól-darabszámok + edzői kulcs + csempe),
  139. meccsterv-szabály (az ő emberhátrányos kontra-fenyegetésük × a
  ti akadozó emberelőnyötök), 160. edzés-szabály (emberhátrányos
  befejezés: kiugratásból vagy beállós helyzetből, minden támadásban
  más emberrel).
- **Hajrá-hibázók**: KI ADJA EL a labdát a döntő szakaszban. A
  hajrá-eladás csapat-szinten mondja meg, megugrik-e az eladás-ütem a
  végén — ez azt, kinél: az utolsó öt perc labdaeladásait a vesztes
  játékoshoz írjuk (2+ hajrá-eladástól; rövid felvételen nincs kép). A
  végén rá kell menni: kettőzés és passzsáv-zárás nála, mert ott a
  legolcsóbb a labdaszerzés, amikor a legtöbbet ér. Egy réteg, sok
  felület: `clutch_turnover_players` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (játékosonkénti
  eladás-darabszámok + edzői kulcs + csempe), 138. meccsterv-szabály
  (az ő hajrá-hibázójuk × a ti elöl szerzett labdáitok), 159.
  edzés-szabály (nyomás alatti döntés: fáradtan, zajban játszott záró
  részlet).
- **Csere-kiváltók**: KAPOTT GÓL UTÁN cserélnek-e. A csere-blokkok azt
  mondják meg, hogyan cserélnek, a csere-hatás azt, mi lesz belőle —
  ez azt, miért: a cserehullámokat ahhoz kötjük, jött-e kapott gól az
  előző 30 másodpercben (4+ csere; 50% felett reaktív, 20% alatt
  tervezett csere-rend). Aki kapott gólra cserél, reagál és nem
  tervez: a gólsorozat nála cserezavart is okoz, ezért gyors
  gólváltásra kell játszani. Egy réteg, sok felület:
  `substitution_triggers` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (csere-darabszámok + két edzői kulcs
  + csempe), 137. meccsterv-szabály (az ő reaktív cseréik × a ti
  gólsorozataitok), 158. edzés-szabály (tervezett csere-rend: rögzített
  csere-pontok, kapott gól után soha).
- **Falépítés-idő**: MENNYI IDŐ ALATT ÁLL FEL a faluk. Az
  átmenet-védekezés azt mondja meg, mennyi gyors gólt kapnak
  labdavesztés után, a visszaérés-fegyelem azt, ki nem fut vissza — ez
  azt, mennyi idő a rendezett falig: birtokváltásonként mérjük, hány
  másodperc múlva áll legalább öt mezőnyvédőjük a saját kapu 12 m-es
  zónájában (4+ eset; 8 mp felett lassú, 5 mp alatt gyors). Lassan
  felálló fal ellen a gyors indítás termel, gyorsan rendeződő fal
  ellen a kontra kockázat. Egy réteg, sok felület:
  `defense_setup_time` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (eset- és idő-összegek + két edzői
  kulcs + csempe), 136. meccsterv-szabály (az ő lassan felálló faluk ×
  a ti kontra-kíséretetek), 157. edzés-szabály (gyors falépítés:
  stopperrel mért öt másodperces rendeződés).
- **Kapus emberhátrányban**: NŐ-E a kapusuk a két perc alatt. Az
  emberelőny-védekezés azt mondja meg, mennyi gólt kapnak
  emberhátrányban — ez azt, mennyi múlik a kapuson: a rá kaputra
  érkezett lövéseket szétválasztjuk emberhátrányra és egyenlő
  létszámra (helyzetenként 4+ lövés, 15 százalékpontos eltérésnél). Ha
  a kapusuk ilyenkor feljavul, a két perc nem ingyen gól — türelmes,
  helyzetre játszó emberelőny kell; ha visszaesik, gyorsan kell
  befejezni. Egy réteg, sok felület: `gk_shorthanded_saves` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (helyzetenkénti lövés- és védés-darabszámok + két edzői kulcs +
  csempe), 135. meccsterv-szabály (az ő emberhátrányban visszaeső
  kapusuk × a ti akadozó emberelőnyötök), 156. edzés-szabály (kapus
  emberhátrányban: a fallal egyeztetett sarok-választás).
- **Emberelőny-lövők**: KI FEJEZ BE a két perc alatt. Az
  emberelőny-hatékonyság azt mondja meg, mennyi gólt hoznak a
  kiállításokból, az emberelőny-tempó azt, hogyan játsszák — ez azt,
  kire megy a befejezés: a kiállítás-ablakokban leadott lövéseket a
  lövőhöz írjuk (3+ lövéstől). Emberhátrányban a fal nem érhet
  mindenhová, ezért a befejezőjükre kell rendezni: az ő oldalán jöjjön
  a kilépés vagy a kettőzés. Egy réteg, sok felület:
  `powerplay_shooters` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (játékosonkénti lövés- és
  gól-darabszámok + edzői kulcs + csempe), 134. meccsterv-szabály (az
  ő emberelőny-befejezőjük × a ti emberhátrány-védekezésetek), 155.
  edzés-szabály (emberelőny több befejezővel: ugyanaz az ember nem
  fejezhet be kétszer egymás után).
- **Lövés-távolság esése**: KIFELÉ SZORULNAK-E a hajrára. A
  lövőerő-esés a lövés sebességét méri félidőnként, a befejezés-esés a
  gólarányt — ez a helyet: félidőnként átlagolt lövés-távolság
  (félidőnként 4+ lövés, 1 m-es növekedésnél). Ha a második félidőben
  kijjebb kerülnek a lövéseik, elfogy az erő a betörésekhez: a
  hajrában elég a lövő-vonalba lépni, a közeli befejezést már nem
  vállalják. Egy réteg, sok felület: `shot_distance_fade` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (félidőnkénti lövés- és távolság-összegek + edzői kulcs + csempe),
  133. meccsterv-szabály (az ő kifelé szoruló lövéseik × a ti
  blokkjaitok), 154. edzés-szabály (fáradt befejezés: az edzés végén,
  fáradtan, csak 9 m-en belülről ér pontot a lövés).
- **Kapott gólok támadás-típus szerint**: MILYEN TÁMADÁSBÓL kapják a
  gólokat. A támadás-hatékonyság a támadó oldalról nézi, melyik műfaj
  eredményes — ez a védő oldali párja: a gólokat a támadás típusához
  (lerohanás / gyors indítás / felállt támadás / 7 a 6) kötjük, de a
  védekező csapat oldalán tartjuk nyilván (5+ kapott gól, 40%-os
  vezető típus, holtverseny nélkül). Ez rangsorolja a védekezési
  munkát: lerohanásból kapott gólnál a visszarendeződés a kulcs (nem a
  fal minősége), felállt támadásból kapottnál a fal szervezése. Egy
  réteg, sok felület: `conceded_by_attack_type` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (típusonkénti kapott gólok + edzői kulcs + csempe), 132.
  meccsterv-szabály (az ő lerohanásból kapott góljaik × a ti gyors
  indításotok), 153. edzés-szabály (visszarendeződés vagy a felállt
  fal szervezése, a vezető típustól függően).
- **Áttörő játékosok**: KI JUT BE labdával a falba. A
  betörés-folyosók azt mondják meg, melyik sávban lyukas a fal — ez
  azt, ki viszi be a labdát: támadásonként (emberenként egyszer)
  számoljuk, ki lép be a kapu 9 m-es körzetébe, és hány ilyen
  betörésből lett gólos támadás (3+ betöréstől). Az áttörő ember ellen
  duplázni kell: a védője kapjon segítőt, és a betörés vonalát testtel
  kell zárni. Egy réteg, sok felület: `breakthrough_players` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (játékosonkénti betörés- és gól-darabszámok + edzői kulcs + csempe),
  131. meccsterv-szabály (az ő áttörő emberük × a ti kettőzésetek),
  152. edzés-szabály (duplázás a betörőre: a szomszéd védő azonnali
  bezáródása, testtel).
- **Két beállós játék**: MENNYIT JÁTSZANAK két emberrel a 6 m-en. A
  beálló-terhelés azt mondja meg, mennyi támadás megy át a beállón, a
  beálló-oldal azt, hol dolgozik — ez azt, hány emberrel:
  támadásonként nézzük, a kockák mekkora részében van legalább két
  támadó a beálló-zónában (8+ támadás; 30% felett két beállós, 10%
  alatt egy beállós felállás). Két beálló ellen a fal közepét
  tömöríteni kell — a középső védők nem adhatják át egymásnak a
  beállókat, a szélső védők feljebb léphetnek; egy beállós felállásnál
  a segítő védő befelé dolgozhat. Egy réteg, sok felület:
  `double_pivot_usage` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (támadás-darabszámok + két edzői
  kulcs + csempe), 130. meccsterv-szabály (az ő két beállós játékuk ×
  a ti széthúzott falatok), 151. edzés-szabály (közép-tömörítés:
  minden középső védőnek saját beállója van).
- **Hajrá-ötös**: KIK VANNAK A PÁLYÁN a döntő szakaszban. A
  hajrá-teljesítmény azt mondja meg, ki bírja a meccs végét, a
  hajrá-gólszerzők azt, ki lő ilyenkor — ez azt, kit küldenek pályára:
  az utolsó 10 percben játékosonként a pályán töltött kockák (a
  hajrá-mag legalább 100 mért kockától; rövid felvételen nincs). Ha
  tudjuk, kik lesznek fent a végén, rájuk lehet tervezni a párosítást;
  a saját csapatban pedig a hajrá-emberek együtt gyakorolják a záró
  figurákat. Egy réteg, sok felület: `clutch_lineup` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (játékosonkénti kocka-darabszámok + edzői kulcs + csempe), 129.
  meccsterv-szabály (az ő hajrá-emberük × a ti hajrá-mérlegetek), 150.
  edzés-szabály (hajrá-ötös begyakorlása: edzés végén, fáradtan, ezzel
  a felállással).
- **Kontra-kíséret**: HÁNYAN FUTNAK FEL a lerohanásaiknál. A
  lerohanás-befejezők azt mondják meg, ki fejezi be a kontrát, az
  átmenet-támadás azt, mennyi gólt hoz — ez azt, mekkora erővel
  indulnak: a lerohanás-szakaszok elején hány saját mezőnyjátékos van
  már az ellenfél térfelén (3+ lerohanás; 3,0 felett tömeges, 1,6
  alatt magányos kontra). Tömeges kontra ellen mindenkinek azonnal
  vissza kell rendeződnie; magányos kontránál elég egy fékező ember, a
  többiek felállhatnak. Egy réteg, sok felület: `fast_break_support`
  motor, edzői összefoglaló, /analyze + meccs-csomag,
  felderítés-profil (lerohanás- és felfutó-összegek + két edzői kulcs
  + csempe), 128. meccsterv-szabály (az ő tömeges kontrájuk × a ti
  visszazárásotok), 149. edzés-szabály (kontra-kíséret: 3 a 2 elleni
  indítás két kötelező kísérővel).
- **Kapus-hetesvédés irány szerint**: MELYIK SAROKBA menő heteseket
  fogja a kapusuk. A hetes-védés azt mondja meg, mennyit fog — ez azt,
  merre: a hetes-kimenetelek irány-mezőjét (bal / közép / jobb, a dobó
  szemszögéből) használjuk, és irányonként számolunk védési arányt
  (irányonként 3+ hetes, 25 százalékpontos elmaradásnál). Így a
  hetes-lövőnek kész terve lehet: abba a sarokba kell lőni, ahol a
  kapus a leggyengébb, és nem a vonalnál kell dönteni. Egy réteg, sok
  felület: `gk_seven_directions` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (irányonkénti hetes- és
  védés-darabszámok + edzői kulcs + csempe), 127. meccsterv-szabály
  (az ő kapusuk gyenge hetes-sarka × a ti hetes-mérlegetek), 148.
  edzés-szabály (hetes-védés sarokra: lábmunka, majd a lövő karját
  figyelő indulás).
- **Kihozatal-oldal**: MELYIK OLDALON indítják a támadást. A
  támadás-indítók azt mondják meg, ki hozza fel a labdát, a
  kapus-indítás oldala azt, merre kezd a kapus — ez azt, hol jön át a
  labda: a támadás-szakaszok első kockájában a labda oldalirányú helye
  bal / közép / jobb sávban (8+ támadás, 50% feletti oldalnál). Ha a
  kihozataluk fele ugyanarról az oldalról jön, oda kell szervezni a
  letámadást és a kettőzést; a másik oldalon addig elég egy ember. Egy
  réteg, sok felület: `buildup_side` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (sávonkénti
  támadás-darabszámok + edzői kulcs + csempe), 126. meccsterv-szabály
  (az ő egyoldalas kihozataluk × a ti elöl szerzett labdáitok), 147.
  edzés-szabály (oldalváltó kihozatal: a kapus felváltva indít, a
  szélső hangos jelzésére).
- **Lepattanó-szerzők**: KI NYERI a kipattanókat. A második roham
  csapat-szinten mondja meg, hányszor szerzik vissza a saját, gólt nem
  érő lövésüket — ez azt, ki: minden nem gólos lövés után az első
  azonosított labdabirtokoshoz írjuk a labdát (3+ lepattanótól). A
  támadó lepattanókat gyűjtő ember ellen a blokk után azonnal be kell
  zárni a teret, a kapus kipattanóját a legközelebbi védőnek kell
  kísérnie. Egy réteg, sok felület: `rebound_winners` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (játékosonkénti lepattanó-darabszámok + edzői kulcs + csempe), 125.
  meccsterv-szabály (az ő lepattanó-gyűjtőjük × a ti engedett második
  rohamaitok), 146. edzés-szabály (kipattanó-kísérés: minden blokk
  után kötelező labdára indulás).
- **Lövő-távolság profil**: KI LŐ TÁVOLRÓL és ki közelről. A
  lövés-távolság profil csapat-szinten mondja meg, honnan lőnek — ez
  játékosonként bontja: lövőnként átlagolt kapu-távolság (3+ lövéstől;
  9,5 m felett távoli lövő, 7 m alatt közeli befejező). A távoli
  lövőre ki kell lépni (blokk a lövő-vonalba, mögötte segítővel), a
  közeli befejezőért viszont a fal nem bomolhat meg: elé állás és
  testes fogadás. Egy réteg, sok felület: `shooter_ranges` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (lövőnkénti lövés- és távolság-összegek + két edzői kulcs + csempe),
  124. meccsterv-szabály (az ő távoli lövőjük × a ti blokkjaitok),
  145. edzés-szabály (befejezés közelebbről: lövés csak befelé
  lépésből, a védő mellett elhaladva).
- **Emberhátrány-forma**: MIT JÁTSZANAK öt emberrel. Az
  emberhátrány-támadás azt mondja meg, mire mennek támadásban a két
  perc alatt, az emberelőny-védekezés azt, mennyit kapnak — ez azt,
  milyen falat húznak: a kiállítás-ablakokban a hátrányban lévő csapat
  formáját olvassuk ki kockánként, hátsó-előretolt bontásban (5-0,
  4-1, 3-2; 100+ mért kocka, 60% feletti fő formánál). Az 5-0 mögött
  az átlövés szabad, a 4-1 előretolt embere mögé kell beúsztatni a
  beállót. Egy réteg, sok felület: `shorthanded_shape` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (formánkénti kocka-darabszámok + edzői kulcs + csempe), 123.
  meccsterv-szabály (az ő emberhátrány-faluk × a ti akadozó
  emberelőnyötök), 144. edzés-szabály (emberhátrány-védekezés az adott
  alapállásból, hangos átadással).
- **Emberelőny-tempó**: ELNYÚJTJÁK vagy KAPKODJÁK az emberelőnyt. Az
  emberelőny-hatékonyság azt mondja meg, mennyi gólt hoznak a
  kiállításokból — ez azt, hogyan játsszák: a támadás-szakaszok
  hosszát vetjük össze emberelőnyben és egyenlő létszámnál (3+
  emberelőnyös és 5+ egyenlő létszámú támadás, 5 mp-es eltérésnél).
  Aki elnyújtja, a biztos helyzetre vár — ellene türelmes, zárt fal
  kell, mert a kapkodó kilépés neki dolgozik; aki emberelőnyben is
  gyorsan lő, ott az agresszív, kilépő védekezés fizet ki. Egy réteg,
  sok felület: `powerplay_pace` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (támadás-darabszámok és
  hossz-összegek + két edzői kulcs + csempe), 122. meccsterv-szabály
  (az ő elnyújtott emberelőnyük × a ti emberhátrány-védekezésetek),
  143. edzés-szabály (emberelőny kivárással: hat passz és egy
  oldalváltás a befejezés előtt).
- **Effektív játékidő**: MENNYI a tényleges játék a megszakításokhoz
  képest. A megszakítás-felismerés az egyes leállásokat adja, az
  időkérés-időzítés azt, mikor nyúlnak a korongért — ez a meccs
  ritmusát: a felismert megszakítások összegzett ideje a mért
  játékidőhöz mérve, és megszakításonként az a csapat, amelyik előtte
  birtokolt (10+ perc mért játékidőtől; 80% alatt szakadozott, 92%
  felett folyamatos). Szakadozott meccsképben a ritmus-tartás a
  feladat (gyors középkezdés, kész terv a leállások utáni első
  támadásra), folyamatos meccsen a cserék időzítése és a bírás dönt.
  Egy réteg, sok felület: `playing_time_profile` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil (játékidő-
  és holtidő-összegek + két edzői kulcs + csempe), 121.
  meccsterv-szabály (az ő folyamatos meccsképük × a ti szűk
  rotációtok), 142. edzés-szabály (ritmus-tartás: váratlan leállítás
  után kötött figurából befejezett első támadás).
- **Védekezés-keménység**: MENNYI BÜNTETÉST hoz a faluk. A védekezési
  nyomás azt méri, milyen közel mennek a labdáshoz, a vonal-magasság
  azt, hol áll a fal — ez azt, mennyibe kerül: a védekezett
  támadásokhoz viszonyítjuk az ellenük ítélt heteseket és a kapott
  kiállításokat (10+ védekezett támadás; 12% felett kemény, 4% alatt
  passzív fal). Kemény fal ellen a betörés duplán fizet (áthaladás
  vagy hetes + emberelőny), passzív fal ellen nem lesz ingyen
  büntető — ott figurákkal és beállós játékkal kell helyzetet
  csinálni. Egy réteg, sok felület: `defensive_aggression` motor,
  edzői összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (támadás-, hetes- és kiállítás-darabszámok + két edzői kulcs +
  csempe), 120. meccsterv-szabály (az ő kemény faluk × a ti
  hetes-mérlegetek), 141. edzés-szabály (szabályos keménység: törzzsel
  és lábbal útba állni, kézzel csak a labdára).
- **Visszaérés-fegyelem**: KI nem fut vissza védekezni. Az
  átmenet-védekezés csapat-szinten mondja meg, mennyi gyors gólt
  kapnak labdavesztés után — ez játékosonként bontja: a védekezett
  kockákban ki van a saját térfelén (200+ mért kocka, 70% alatti
  hazaérési aránynál). Az elöl lógó ember mögött nincs védő: az ő
  oldalán kell a gyors indítást vezetni, a saját csapatban pedig
  visszafutás-fegyelem a téma. Egy réteg, sok felület:
  `recovery_discipline` motor, edzői összefoglaló, /analyze +
  meccs-csomag, felderítés-profil (játékosonkénti kocka-darabszámok +
  edzői kulcs + csempe), 119. meccsterv-szabály (az ő elöl lógó emberük
  × a ti gyors kapus-indításotok), 140. edzés-szabály
  (visszafutás-fegyelem: az utolsó támadó a felezővonalig fut vissza).
- **Kapus-védés lövés-tempó szerint**: a BOMBÁKAT vagy a HELYEZETT
  lövéseket fogja-e a kapusuk. A távolság-sávos réteg azt mondja meg,
  milyen messziről sebezhető, a poszt szerinti azt, milyen szögből —
  ez azt, milyen tempójú lövés ellen: a kapura tartó lövéseket a mért
  lövés-sebesség alapján kemény (80 km/h felett) és helyezett sávra
  bontjuk (sávonként 4+ lövés, 15 százalékpontos eltérésnél). Aki a
  bombákat fogja, az ellen sarokba helyezve, pattintva kell
  befejezni; aki a helyezett lövéseket, ott a tempó dönt. Egy réteg,
  sok felület: `gk_saves_by_speed` motor, edzői összefoglaló,
  /analyze + meccs-csomag, felderítés-profil (sávonkénti lövés/védés
  darabszámok + edzői kulcs + csempe), 118. meccsterv-szabály (az ő
  kapusuk gyenge tempó-sávja × a ti lövőerőtök), 139. edzés-szabály
  (az adott sáv védése: reakció-indítás vagy lábmunka és alacsony kéz).
- **Álló támadók**: KI mozog labda nélkül a legkevesebbet. A
  támadó-mozgás csapat-szinten mondja meg, álló vagy mozgásos a
  támadásuk — ez játékosonként bontja: szervezett támadásban mért
  átlagsebesség a csapatátlaghoz viszonyítva (60+ mért másodperc, 30%
  elmaradás). Aki érdemben a csapatátlag alatt mozog, azt a védője
  nyugodtan otthagyhatja: befelé segíthet, kettőzhet vagy a beállóra
  léphet. Egy réteg, sok felület: `static_attackers` motor, edzői
  összefoglaló, /analyze + meccs-csomag, felderítés-profil
  (játékosonkénti idő- és út-összegek + edzői kulcs + csempe), 117.
  meccsterv-szabály (az ő álló emberük × a ti kettőzésetek), 138.
  edzés-szabály (labda nélküli munka: minden átadás után indulás).
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

## v0.1.25-ös changelog-kör (2026-07-26) — címke és GitHub-kiadás nélkül maradt; először a v0.1.23 kiadás telepítőjében jelenik meg

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

## v0.1.24-es changelog-kör (2026-07-25) — címke és GitHub-kiadás nélkül maradt; először a v0.1.23 kiadás telepítőjében jelenik meg

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

## v0.1.23-as changelog-kör (2026-07-25) — címke és GitHub-kiadás nélkül maradt; először a v0.1.23 kiadás telepítőjében jelenik meg

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
