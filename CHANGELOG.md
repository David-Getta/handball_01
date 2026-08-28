# Változásnapló (CHANGELOG)

A Sport Machine kiadásainak emberi nyelvű összefoglalója. A részletes
történet a squash-merge-elt PR-okban él; itt a lényeg, témák szerint.

## Kiadatlan (a v0.1.84 óta)

- **A szakasz-párbeszéd mutatja a felismert eredményt** (könyvtár): a
  kézi térfél-döntés lényege az összevetés a VALÓDI végeredménnyel —
  eddig a párbeszéd csak annyit tudott mondani, "nézd meg máshol". A
  szakasz-lista és a fordítás válasza mostantól viszi a felismert
  eredményt (hazai : vendég), és a "Megfordítom" után azonnal frissül:
  látszik, hogy a fordítással a valódi végeredmény jött-e ki.

- **A súgó tanítja a darabokban felvett meccset** (kezdőlap): az "Első
  lépések" új lépése elmondja a teljes utat — az összes darab egy
  kötegben, időrendben; a köteg magától összeáll; a "térfél?" jelvény
  és a ⇄ gomb pedig az eredmény-ellenőrzéshez visz.

## v0.1.84 — kiadva (2026-08-28)

> Kiadás-jegyzet: a v0.1.83 sürgős javításának kiegészítése. Aki HÁROM
> vagy több darabból fűzött össze meccset a v0.1.83-mal, fűzze össze
> újra ezzel a verzióval (két darabnál nem kell). Az eldöntetlen
> térfél mostantól egy gombbal javítható, és az összefűzött meccsnek
> félideje is van.

- **Három vagy több darabnál a 2. félidő minden darabja jó irányba
  fordul** (motor, SÜRGŐS): a v0.1.83 szakasz-határos tükrözése az
  állapotot billegtette ("fordulás → átváltunk"), pedig a határ előtti
  ablak már a NORMALIZÁLT képet mutatja — ezért a tükrözött darab
  utáni nyers darab újra "fordulást" mutatott, és a hatklipes meccsben
  minden MÁSODIK 2. félidős darab visszafordult volna. A szabály
  mostantól: pontosan akkor tükrözünk, ha a nyers kép a normalizálthoz
  képest fordított. Két darabnál a viselkedés változatlan; aki 3+
  darabból fűzött össze a v0.1.83-mal, fűzze össze újra.

- **Az összefűzött meccsnek is van félideje** (motor): a darabokban
  felvett meccsben nincs felvett szünet (a telefon a szünet alatt
  állt), az aktivitás-alapú félidő-felismerés némán semmit sem talált
  — és minden félidő-tudatos réteg (félidei állás, fordítás,
  félidő-nyitás, momentum, fáradás-összevetés) elhallgatott, pont a
  darabokban felvett meccseken. A félidő-pont mostantól a
  szakasz-határ, ahol a térfél fordult — akár a gép döntött, akár az
  ember a ⇄ gombbal. Egyben felvett meccsen minden marad a régiben.

- **A térfél egy gombbal eldönthető — az ember dönt, ahol a gép nem
  tudott** (motor + könyvtár): az összefűzés kevés mért pozíciónál nem
  dönti el a térfélcserét, és eddig a jelentés csak annyit tudott
  mondani: ellenőrizd az eredményt, rossz esetben fűzd össze újra. A
  meccset látott ember viszont TUDJA a valódi végeredményt. A könyvtár
  sora mostantól jelzi az eldöntetlen határt ("térfél?" jelvény + ⇄
  gomb), a szakasz-párbeszéd megmutatja, melyik szakasz melyik fájlból
  jött és tükrözve van-e, a "Megfordítom" gomb pedig megfordítja a
  gyanús szakaszt. A döntés lemezre kerül (újraindítás után is él), az
  elemzés (eredmény, összefoglaló, edzés-fókusz, klip-számláló)
  újraszámol, és a figyelmeztetés elhallgat — döntés SZÜLETETT, csak
  nem géptől.

- **Az eldöntetlen térfélcsere-határ figyelmeztetést kap** (motor): ha
  az összefűzés egy határán kevés mért pozíció miatt nem dönthető el a
  csere, az eredmény rossz irányú is lehet — és a forrás-térképet a
  felhasználó sosem nézi meg. A minőség-jelentés mostantól kimondja,
  teendővel: ellenőrizd az eredményt; ha rossz, a meccs sorának ⇄
  gombjával fordítható vissza.

## v0.1.83 — kiadva (2026-08-28)

> Kiadás-jegyzet: SÜRGŐS javítás az összefűzéshez. A darabokban
> felvett meccsnél a térfélcsere a darabok KÖZÖTT van — tükrözés
> nélkül a 2. félidő minden gólja a rossz csapathoz került volna. Aki
> a v0.1.75–v0.1.82 alatt fűzött össze két-félidős meccset, fűzze
> össze újra ezzel a verzióval (a darabok megvannak — pont ezért).


- **Térfélcsere a szakasz-határokon — az összefűzött meccs eredménye
  helyes** (motor, SÜRGŐS): egy videón belül a feldolgozás felismeri a
  szünetet és tükrözi a második félidőt — de a darabokban felvett
  meccsnél a térfélcsere a DARABOK KÖZÖTT van, és a 2. félidő darabja
  önmagában normalizálatlan maradt. A lövés-felismerés irány-szabálya
  az egész meccsre egy, tehát az összefűzött meccs 2. félidejének
  MINDEN gólja a rossz csapathoz került volna — az eredmény
  értelmetlen. Az összefűzés mostantól minden szakasz-határon
  ellenőrzi a súlypont-fordulást (a szünet-felismerés szabályával), és
  tükrözi a fordult szakaszokat.

  Három védőkorlát: a félidőn BELÜLI vágásnál (a telefon elvágta a
  felvételt, de nincs csere) nem tükrözünk; kevés mért pozíciónál nem
  döntünk (a rossz irányú tükrözés ugyanakkora hiba, mint a
  kihagyott) és a bejegyzés kimondja, hogy a döntés nem született meg;
  az eldönthetetlen határon pedig az addigi irány öröklődik. A döntés
  szakaszonként a forrás-térképbe kerül. A klip-vágást nem érinti: a
  kép-indexek a videóra mutatnak, a tükrözés csak pálya-koordináta.

## v0.1.82 — kiadva (2026-08-28)

> Kiadás-jegyzet: a BIZONYÍTÉK kiadása. A felderítés kulcs-mondata
> ("a #7-esükre kettőzz") mellé egy kattintással ott a videó — a
> Célpont-videó az összes elemzett meccsükből vágja ki a megnevezett
> emberük hibáit. A jegyzet-lista fájlba menthető, a darabokban
> felvett meccs teljes útját pedig lánc-teszt őrzi a valódi
> végpontokon.


- **Célpont-videó a felderítésből** (felület): a kulcs-mondat ("a
  #7-esükre kettőzz — nála a szorítás labdaszerzés") megnevezi a
  célpontot, de a bizonyíték eddig kézi munka volt. Az
  Ellenfél-felderítés fejlécében egy gomb a megnevezett emberek
  (nyomás-érzékeny + hajrá-hibázó) eladásait és góljait vágja ki az
  ÖSSZES elemzett meccsükből, egy zip-be — a szezon-válogatás
  motorján. A mondat meggyőz; a felvétel felkészít.

- **A jegyzet-lista menthető** (felület): a Jegyzetek az edző
  teendő-listája — a videó-szobába fájlban megy, nem a program előtt
  ülve. A mentés a LÁTHATÓ (keresésre szűrt) listát viszi: az edző
  pont azt a válogatást viszi magával.

- **Lánc-teszt a darabokban felvett meccsre** (teszt): a v0.1.75–81
  története egyben, a VALÓDI végpontokon át — két klip köteg-csoporttal
  feldolgozva, a motor magától összefűzi, a könyvtár jelöli az egészet
  és a darabokat, az összkép egy meccset lát (nem hármat), a
  klip-számláló és a szezon-CSV válaszol, és az összefűzött meccsből
  klip vágható. A darab-tesztek mindezt külön őrzik; ez a kör azt
  mutatja meg, ha a lépések KÖZÖTT szakad meg valami.

## v0.1.81 — kiadva (2026-08-28)

> Kiadás-jegyzet: a SZEZON-VÁLOGATÁS. "Az összes gólom egy helyen" —
> a játékos-fejlődés lapról egy gomb az egész szezont vágja:
> meccsenkénti mappák, dátum + ellenfél, egy zip. Mellette a
> klip-becslő gyorsítótárat kapott, hogy a Klipek lap hosszú meccsen
> is azonnal nyíljon.


- **Szezon-válogatás egy játékosról** (API + felület): "az összes
  gólom egy helyen" — a meccsenkénti klipcsomag megvolt, a szezoné
  nem: a játékos meccsenként vágatott, és a zipeket kézzel szedte
  össze. A játékos-fejlődés lapon egy gomb az egész szezont vágja: a
  játékos minden meccséből az ő jelenetei, meccsenkénti mappákba
  rendezve (dátum + ellenfél), egy zip-ben. A videó nélküli meccsek
  kimaradnak és az üzenet megmondja, hány; ahol nincs jelenete, azt is.
  A vágás percekbe telhet — a gombon fut a motor haladás-üzenete. A
  szezon-szűrő itt is él: az összefűzött meccs darabjai nem duplázzák
  a válogatást.

- **A klip-számláló gyorsítótárazva** (API): a becslő most már a
  teljes bővített esemény-készletet építi, ami egy hosszú meccsen
  másodpercekbe telik — a Klipek lap pedig minden megnyitáskor lekéri.
  Az eredmény meccsekként gyorsítótárazódik; a kulcsban ott van minden,
  ami az eseményeket vagy a mezszám-képet változtatja (kockaszám,
  jegyzetek, kézi javítások, mezszám-kiosztás fájl-ideje), tehát a
  friss jegyzet azonnal látszik — a gyorsítótár nem mutathat régi
  képet (őr-teszt).

## v0.1.80 — kiadva (2026-08-28)

> Kiadás-jegyzet: a KAPUS is játékos. Az egyéni "Mit gyakorolj" eddig
> csak mezőnyjátékosról szólt — a kapus lapja üres maradt, a
> "Klipjeim" pedig üres csomagot adott neki, mert a nagy védés nem
> vitte, ki védte. Mostantól a kapus is kap egyéni fókuszt (a várható
> alatti védés-mérlegből), a nagy védés az övé, és a klip-becslő a
> bővített csomagokat is számolja — nem riaszt "üres csomaggal" ott,
> ahol a vágás klipeket adna.


- **A klip-becslő a bővített csomagokat is számolja** (API): a
  "kb. hány klip lesz" becslés eddig csak az alap-eseményeket
  (gól/lövés/eladás) látta — a bővített csomagokra (nagy védés,
  kulcs-pillanat, jegyzet, hétméteres, ...) NULLÁT mondott, a felület
  pedig "üres csomagot adna"-val riasztott, miközben a vágás klipeket
  adott volna. A becslő és a vágás mostantól UGYANABBÓL az
  esemény-építőből él (őr-teszt tiltja a saját listát), tehát nem
  tudnak széttartani.

- **A nagy védés a kapusé** (API): a nagy-védés klip eddig nem vitte,
  KI védte — a kapus a "Klipjeim" gombbal (mezszám-szűréssel) némán
  üres csomagot kapott, pedig pont az ő jelenetei ezek. Az esemény
  mostantól a szolgálatban lévő kapus track-jéhez kötődik (a
  kapus-idővonalból), tehát a kapus saját válogatása is működik.

- **A kapus is kap egyéni edzés-fókuszt** (motor): az egyéni "Mit
  gyakorolj" hét forrása mind mezőnyjátékosról szólt — a kapus lapja
  üresen maradt, miközben a csapat-szintű fókusznak van
  kapus-szabálya. Az üres lap azt mondja a kapusnak: a program nem lát
  téged. Új, nyolcadik forrás: a várható alatti védés-mérleg (GSAx) —
  legalább 6 kapura tartó lövésből, legalább egy "bevédhető" gólnyi
  elmaradással. A jelenet-ajánlás szándékosan üres: a kapott gól a
  MÁSIK csapat eseménye, mezszámra nem szűrhető — nem hazudunk "nézd
  meg" gombot.

## v0.1.79 — kiadva (2026-08-28)

> Kiadás-jegyzet: a KIMUTATÁS kiadása. A "küldd el Excelben, ki hány
> gólnál jár" mostantól egy gomb a Keret-lapon — ugyanabból a
> számolásból, amit az edző a képernyőn lát, névvel együtt. A
> meccs-CSV is kapott név-oszlopot, a felderítés-választó pedig jelzi
> a darabot, hogy az egyesített jelentés ne számolja kétszer ugyanazt
> a meccset.


- **Szezon-kimutatás CSV-ben a Keret-lapról** (API + felület): a
  meccs-szintű játékos-CSV megvolt, a szezon-szintű nem — pedig a
  "küldd el Excelben, ki hány gólnál jár" tipikus hét végi vezetőségi
  feladat, és eddig a képernyőről kellett kimásolni. A kimutatás
  UGYANABBÓL a számolásból él, mint a Keret-lap (őr-teszt köti ki: a
  vezetőség nem láthat mást, mint az edző), Excel-barát (pontosvessző
  + BOM, mert a magyar Excel a vesszőt tizedesjelnek olvasná), és a
  nevet is viszi — a kimutatásban a név a lényeg, nem a szám.

  A meccs-szintű statisztika-CSV is kapott "Név" oszlopot: nem
  mondhat kevesebbet, mint a szezon-kimutatás.

- **A felderítés-választó is jelzi a darabot** (felület): az
  egyesített felderítésbe a darabot ÉS az egészet kijelölve ugyanaz a
  meccs kétszer számolna — a "darab" címke (rámutatva a magyarázattal)
  megmondja, hogy az EGÉSZET jelöld ki.

## v0.1.78 — kiadva (2026-08-28)

> Kiadás-jegyzet: a szezon nem duplázódik. A v0.1.77 automatikus
> összefűzése után a darabok és az egész is a könyvtárban van — a
> szezon-számolás mostantól tudja, hogy ez ugyanaz a meccs: a
> góllövő-lista, a játékos-görbe, a mérlegek és a jegyzet-lista a
> teljes meccset számolja, egyszer. A könyvtárban címke mondja meg,
> melyik sor az egész ("teljes meccs · N darabból") és melyik a darab.
> A v0.1.77-tel EGYÜTT frissítendő: az automatikus összefűzés e nélkül
> a javítás nélkül duplázna.


- **Az összefűzött meccs darabjai nem duplázzák a szezont** (motor +
  API): összefűzés után a darabok és az egész is a könyvtárban van (a
  darab szándékosan megmarad — törölhető, külön is megnézhető). A
  szezon-szintű összesítés viszont így ugyanazt a meccset KÉTSZER
  számolta: a #7 gólja egyszer a darabban, egyszer az egészben — a
  góllövő-lista, a játékos-görbe, a szezon-mérleg, az egymás-elleni és
  a jegyzet-lista is duplázott. Az összefűzött meccs mostantól viszi,
  MIBŐL lett (`merged_from`), és minden szezon-számolás kihagyja a
  darabokat. A könyvtár-LISTA (a kezelő nézet) továbbra is mindent
  mutat: a törléshez látni kell. Aki nem fűz össze, annak semmi nem
  változik — erre külön őr van.

  A könyvtár-kártyák jelölik is: az egészen "teljes meccs · N
  darabból" címke, a darabon "darab" — rámutatva megmagyarázza, hogy a
  szezon-számok az egészben számolják, tehát nem duplázódik. Enélkül
  három egyforma "Mi vs Ők" sor lenne, és a felhasználó a
  szezon-számokat hinné hibásnak ("hova lett a meccsem?").

## v0.1.77 — kiadva (2026-08-28)

> Kiadás-jegyzet: a darabokban felvett meccs EGY mozdulat. A v0.1.75
> megengedte az akárhány szakaszt, a v0.1.76 megtartotta az emberi
> munkát — ez a kiadás pedig elveszi a kézimunkát: a köteg örökli a fő
> videó kalibrációját (nem fut 5/6-od meccs kalibrálatlanul), és a
> feldolgozás végén magától áll össze egy meccsé, jó sorrendben.
> Reggelre nem hat darabot találsz, hanem a kész meccset.


- **A köteg a végén magától összeáll egy meccsé** (motor + API +
  felület): aki egy meccs hat darabját tölti fel — jellemzően
  éjszakára —, reggel hat KÜLÖN "meccset" talált, és kézzel kellett
  összefűznie, jó sorrendben. Pont az a lépés, amit az ember elfelejt;
  a motor viszont tudja, mikor lett kész az utolsó darab. A köteg
  mostantól közös csoport-jelet visz, és az utolsó darab elkészültekor
  a motor magától fűzi össze őket (ugyanazon az úton, mint a kézi
  összefűzés — tehát a jegyzet-, javítás- és kiállítás-átvétellel
  együtt). A kapcsoló a köteg-listán van és KIKAPCSOLHATÓ: aki több
  külön meccset tölt fel egyszerre, annak az összefűzés hiba lenne.

  Három védőkorlát: ha bármelyik darab elhasalt vagy megszakadt, az
  összefűzés ELMARAD és az üzenet megmondja, miért (fél meccset
  összefűzni rosszabb, mint szólni); részleges darabot nem fűzünk
  össze (előbb a Folytatás); és a csoport a beküldött darabszámot is
  ismeri — különben versenyben egy darabbal "teljesnek" látszhatna.

- **A köteg örökli a fő videó kalibrációját** (felület): aki egy
  meccs hat darabját egyszerre tölti fel, a fő videót bekalibrálja —
  a köteg többi darabja viszont eddig kalibráció NÉLKÜL futott, tehát
  a meccs 5/6-án minden távolság-alapú réteg némán félrement. A darab
  mostantól a fő videó kalibrációját örökli (a saját mentett
  kalibrációja erősebb — azt nem írjuk felül), az örökölt kalibráció a
  darab videójához is elmentődik, és a felület kimondja: ha a kamera
  mozdult a darabok közt, kalibráld őket külön.

## v0.1.76 — kiadva (2026-08-27)

> Kiadás-jegyzet: az ÖSSZEFŰZÉS mostantól nem veszít el semmit. A
> v0.1.75 megengedte, hogy akárhány klipből egy meccs legyen — ez a
> kiadás teszi használhatóvá. Az összefűzött meccsből vágható klip (a
> forrás-térkép megmondja, melyik pillanat melyik fájlban van), és
> túléli az összefűzést minden EMBERI munka: a kézi esemény-javítás, a
> jegyzet és a kiállítás. Mellette a kalibráció átvehető egy másik
> videóról — hat klip ugyanarról a rögzített kameráról eddig
> huszonnégy sarok-kattintás volt.


- **A kézi javítások túlélik az összefűzést** (motor): aki hat klipben
  kijavította a felismerés nyolc tévedését, EMBERI munkát végzett — az
  összefűzés eddig **némán eldobta**, és az összerakott meccs megint
  rossz eredményt mutatott. Az edző nem értette, hova lettek a
  javításai; a program pedig pont azt a bizalmat vesztette el, amiért
  a javítás egyáltalán bekerült.

  A javítás ideje a szakasz eltolásával együtt mozog (különben egy
  MÁSIK esemény típusát írná át, vagy az egyeztetés-ablakon kívülre
  esve csendben elmaradna), és a kézzel felvett gól **lövője** is: az
  track-azonosító, azt pedig az összefűzés eltolja — eltolás nélkül a
  gól egy másik emberhez kerülne, pont a góllövő-listán.

- **A jegyzetek is túlélik az összefűzést** (API): ugyanaz a
  hibafajta egy szinttel odébb. A jegyzet **gépelt szöveg**, nem
  újratermelhető adat — aki hat klip közben megjelölt tizenöt
  pillanatot, majd összefűzte a meccset, eddig mindet elvesztette,
  némán. A kockaszám a szakasz eltolásával mozog (különben a "koppints
  a visszanézéshez" rossz helyre ugrana, ami rosszabb, mintha el sem
  jutna oda), és az összefűzött meccs jegyzetei **időrendben** állnak:
  a szakaszonkénti felvételi sorrend itt semmit nem mondana.

  A szakaszokat POZÍCIÓ szerint párosítjuk a részekhez, nem a videó
  útja szerint: két szakasz jöhet ugyanabból a fájlból (megszakadt
  feldolgozás folytatása), és egy útvonal-kulcsú párosítás
  összeolvasztaná őket — a jegyzet ettől még ott lenne, csak rossz
  időn. Erre külön őr van.

- **A kiállítások is túlélik az összefűzést** (API): a kiállítás
  kézzel felvitt adat, és az **emberelőny-rétegek** (emberelőny-hozam,
  hátrány-támadás, kiállítás-kiharcolás, 6-5 játék) ezen állnak.
  Összefűzéskor eddig elveszett, ezek a rétegek pedig némán
  elhallgattak — az edző azt hitte, nincs mit mérni. Az idő
  másodpercben tolódik (a roster is másodpercben tárol), és az átvétel
  a SAJÁT végpontunkon megy át, tehát a becslés-újraszámítás pontosan
  ugyanaz, mint kézi felvitelnél.

  A kapus-hiány jelzése egész meccsre szól, tehát szakaszonként
  ellentmondhat: csak akkor öröklődik, ha MINDEN szakasz egyetért —
  ugyanaz az elv, mint a kalibráltságnál (amiről nem tudunk, arról nem
  állítunk semmit).

- **Az összefűzött meccsből is vágható klip** (motor): a most
  engedélyezett N-szakaszos összefűzésnek volt egy csendes
  következménye — az összefűzött meccsnek nincs EGY videófájlja, ezért
  a klipvágás azt mondta, hogy "az eredeti videófájl nem érhető el".
  Ez félrevezető volt: a fájl megvan, csak több van belőle. Aki
  darabokban vesz fel, összerakta a meccset, megkapta a teljes elemzést
  — és pont a gólvideót nem tudta kivágni.

  Az összefűzés mostantól **forrás-térképet** ment (melyik játékidő
  melyik fájl melyik kép-indexén van), és a klipvágás szakaszonként
  nyitja a megfelelő videót. Az EGY videós eset ugyanazon a kódon megy
  (egyelemű térkép) — egy külön ág idővel szétcsúszna, és a hiba pont a
  ritkább eseten jönne elő. Ha egy szakasz fájlja hiányzik, az üzenet
  **megnevezi, melyik** és hányról van szó: a többi megvan.

- **Kalibráció átvétele másik videóról** (API + felület): a kalibráció
  a videó FÁJLNEVÉHEZ van kötve, tehát aki darabokban vesz fel, minden
  klipet külön jelölt be — hat klip ugyanarról a rögzített kameráról
  huszonnégy sarok-kattintás ugyanarra a pályára. Az Új elemzés lapon
  mostantól átvehető egy korábbi videó kalibrációja (a legfrissebb
  elöl), és az átvett sarkok utána a Pálya-kalibrációban igazíthatók.

  A program **kimondja a feltételt**: csak akkor helyes az átvétel, ha
  a kamera nem mozdult a két felvétel közt — ezt eldönteni nem tudja,
  elhallgatni viszont nem szabad. A saját kalibrációját nem kínálja
  fel (értelmetlen választás, és elrejti a valódit), és a kizárás a
  fájlnevet UGYANAZZAL a szabállyal tisztítja, mint a mentés —
  őr-teszttel, mert ékezetes vagy szóközös néven a saját kalibráció
  némán mégis megjelenne.

## v0.1.75 — kiadva (2026-08-27)

> Kiadás-jegyzet: az AMATŐR FELVÉTEL kiadása. Aki telefonnal vesz fel,
> nem egy tiszta, hatvanperces meccsfájlt kap, hanem darabokat — és
> eddig a program úgy tett, mintha nem így lenne. Mostantól: a
> szakaszok akárhányan összefűzhetők (nem csak "két félidő"), a rövid
> felvétel megmondja, mit várj tőle a hallgatás helyett, és a program
> szól, ha a rövid szakaszon megéri a "Pontos" profil — mert azon
> múlik a labda felismerése, amire a birtoklás, a passz, az eladás és
> a lövés is épül.


- **Az összefűzés akárhány szakaszt elfogad** (felület): aki telefonnal
  vagy fényképezőgéppel vesz fel, DARABOKBAN kapja a meccset — a
  felvétel négy gigánál vagy tíz percnél elvágódik, és hat-nyolc klip
  lesz belőle, nem kettő. A motor eddig is tudott N szakaszt
  összefűzni; a **felület kérdezett pontosan kettőt**, és emiatt a
  darabokban felvett meccs összerakhatatlan volt. Mostantól sorszámozott
  listába lehet felvenni akárhány szakaszt, a **sorrend látszik és
  javítható** (mozgatás, eltávolítás) — az összefűzés időrendet vár, és
  egy rossz sorrendű meccsen minden idő-alapú réteg (hajrá, sorozatok,
  kondíció) némán félremegy. A gomb neve sem "félidők" többé: az csak
  az egyik eset.

- **Rövid szakaszra a program ajánlja a "Pontos" profilt** (API +
  felület): a profil-választó eddig három nevet kínált, és sehol nem
  mondta meg, mikor melyik éri meg. A "Pontos" egy teljes meccsen
  órákat kér — jogosan nem az alapértelmezés —, egy pár perces klipen
  viszont csak perceket, és pont a **labda** felismerésén javít a
  legtöbbet: arra épül a birtoklás, a passz, az eladás és a lövés, és
  széles, távoli amatőr felvételen ez a különbség dönti el, használható
  lesz-e az elemzés. Az indítás előtti ellenőrzés ezért javaslatot ad,
  ha a feldolgozandó szakasz klip-hosszú. Aki már a Pontosat
  választotta, nem kap javaslatot — a meglévő döntést nem
  kérdőjelezzük meg. A küszöb KÖZÖS a "klip, nem teljes meccs"
  jelzéssel (őr-teszt köti ki): különben ugyanaz a felvétel kaphatna
  "ez rövid" javaslatot és meccs-szintű elemzést is.

- **"Klip, nem teljes meccs"** (motor + felület): egy kézilabda-meccs
  2×30 perc; egy pár perces felvétel nem meccs, hanem KLIP. Ez
  teljesen jogos bemenet — de a meccs-szintű rétegek (hajrá,
  félidő-összevetés, kondíció, sorozatok) némán hallgatnak rajta, és a
  felhasználó ezt eddig HIBÁNAK látta: "megcsináltam, és a fele üres".
  A 20 percnél rövidebb felvétel mostantól kap egy mondatot arról,
  **mi működik** (lövés és helyzetminőség, poszt- és felállás-kép,
  passz- és birtoklás-mutatók, klipvágás) és **mi nem**. Megjelenik a
  meccs-elemzőben, az edzői összefoglalóban (a szöveges alakban is,
  tehát a csomagban) és a nyomtatott jelentés elején.

  Szándékosan **nem figyelmeztetés és nem "első teendő"**, hanem külön
  mező: a `warnings` a hibáké. Ha az információ is oda kerülne,
  elveszne a "nincs figyelmeztetés = megbízható" szabály, és minden
  rövid próba gyanúsnak látszana. Ugyanezért nem a "mennyire bízhatsz
  ebben" dobozban van — hibátlan feldolgozású klipnél az riogatás
  lenne.

- **A "Javulok vagy romlok" a nyomtatott szezon-lapon is** (motor):
  a lapot a játékos TESZI EL — ha a képernyő megmondja, hogy javul, a
  nyomtatvány pedig nem, akkor a papír kevesebbet ér, mint a program,
  és pont az marad ki, amiért elteszi. Az ítélet nélküli esetet a lap
  is kimondja ("nem irány, zaj"), és a viszonyítási ablakot is leírja.
  Forma-irány nélkül a lap változatlan — nem üres címsor, hanem semmi.

## v0.1.74 — kiadva (2026-08-26)

> Kiadás-jegyzet: EGY fájl a beszélgetéshez, és egy mondat a görbe
> helyett. A klipcsomag mostantól viszi a hozzá tartozó lapot is — a
> játékoséba az ő meccs-lapja, a csapatéba az edzői összefoglaló:
> a videó megmutatja, MI történt, a lap azt, mit jelent. A
> játékos-görbe pedig végre irányt is mond ("javulok vagy romlok"),
> úgy, hogy kevés meccsből és zajsávon belüli mozgásból KIMONDOTTAN
> nem mond ítéletet.


- **"Javulok vagy romlok?"** (API + felület): a játékos-görbe eddig
  számokat mutatott meccsről meccsre — az irányt viszont egy
  pontsorból kinézni nem lehet, mert minden második meccs jobb az
  előzőnél. Az utolsó három meccs mostantól az azt megelőző háromhoz
  van mérve (gólarány, befejezés a helyzetekhez képest, gól). Két
  szándékos korlát: **kevés meccsből nincs ítélet** (egy jó meccs
  bármikor jön, és a játékos elhiszi), és a **10% alatti változás nem
  irány, hanem zaj** — a lap ilyenkor kiírja a számokat, de kimondja,
  hogy ez nem irány. A futómunka szándékosan kimarad: ott a több nem
  "jobb", csak több — a poszt dönti el, mennyi kell belőle. A
  kihagyott meccs (None) nem nullaként számít, különben egy sérülés
  romlásnak látszana.

- **A játékos lapja a klipek mellé kerül** (motor + API): az edző EGY
  fájlt visz a beszélgetésre, nem kettőt. Ha a klipcsomag mezszámra
  van szűkítve, a zip a játékos meccs-lapját (HTML) is viszi — több
  kijelölt játékosnál mindenki a saját mappájába. A videó megmutatja,
  MI történt, a lap azt, mit jelent; külön letöltve a kettő szétesik.
  Csapat-szintű csomagba nem kerül játékos-lap (ott nincs kihez
  tenni) — helyette az **edzői összefoglaló** megy a klipek mellé,
  ugyanaz a gondolat egy szinttel feljebb. Egy lap hibája nem viheti
  el a videót: az edző a felvételért vágatott.

## v0.1.73 — kiadva (2026-08-26)

> Kiadás-jegyzet: a klip mint MUNKAESZKÖZ. A v0.1.72 megnyitotta az
> utat a játékos saját videójához; ez a kiadás használhatóvá teszi.
> Három emberrel külön-külön ülsz le — mindenki külön mappát kap, és a
> plafon is emberenként oszlik, hogy senki mappájában ne maradjon két
> klip. A "Mit gyakorolj" tételeitől egy kattintás a felvételig: a
> gyakorlat elmondja, MIT kell csinálni, a klip azt, MIÉRT. És a vágás
> előtt megtudod, mennyi lesz — a percekig tartó vágás után derülne ki
> különben, hogy három csomaghoz nem volt jelenet.


- **A klipvágás előre megmondja, mennyi lesz** (API + felület): a
  vágás percekbe telik, és eddig csak a VÉGÉN derült ki, hogy három
  kijelölt csomaghoz nem volt jelenet — az edző addig várt a semmire.
  A Klipek lap mostantól a kijelölés mellett mutatja a becsült
  klipszámot, külön kiemelve a nullát ("a vágás üres csomagot adna"),
  és jelzi, ha a kijelölés a motor plafonja fölé megy (a csomag ott
  arányosan elosztva áll meg). A becslés FELSŐ korlát, ezért "kb."-t
  mond: az azonos pillanatra eső ismétléseket a motor kiszűri. A
  csapat-szintű darabszám a mezszám nélküli jeleneteket is viszi —
  őr-teszt köti ki, különben a becslés alábecsülne.

- **A gyakorlandótól egy kattintás a felvételig** (motor + API +
  felület): a "Mit gyakorolj" tételei eddig szövegek voltak — a
  játékos elolvasta, hogy nyomás alatt eladja a labdát, és nem tudta,
  melyik pillanatról van szó; a klip-válogatáshoz pedig ki kellett
  volna találnia, melyik csomagot kérje. Minden tétel mostantól viszi
  azokat a klip-típusokat, amelyeken a hiba LÁTSZIK, és a lapon egy
  "Nézd meg a felvételen" gomb nyitja a Klipek képernyőt a saját
  mezszámmal ÉS a megfelelő csomagokkal. Az erőnlét-tétel üres listát
  ad — azt egyetlen jelenet sem mutatja meg —, de a mező ott van
  minden tételen (a hiányzó kulcs try/except-ben némán elvinné az
  egész lapot). Új őr méri a rétegből jövő típusokat a klip-motor
  jegyzékéhez: egy elgépelt típus működő gombot és üres zip-et adna.

- **Több kijelölt játékosnál mindenki külön mappát kap** (motor +
  felület): az edző három emberrel KÜLÖN-KÜLÖN ül le, egy összekevert
  zip-ből viszont minden beszélgetés előtt újra kellene válogatnia. A
  játékos-mappa a KÜLSŐ (`#7/gol/…`), mert az edző emberenként készül,
  nem témánként. Egy kijelölt játékosnál nincs mappa — ott csak
  fölösleges kattintás lenne. A Klipek lap előre megmondja, mit fog
  kapni.

  A klip-plafon is JÁTÉKOSONKÉNT oszlik ilyenkor: enélkül ugyanaz a
  néma igazságtalanság tért volna vissza egy szinttel feljebb — a
  sokat szereplő ember elvitte volna a keretet, és a másik két
  játékos mappájában két klip maradt volna. Az edző pont azzal nem
  tudna leülni, akiről a legkevesebb anyaga van.

## v0.1.72 — kiadva (2026-08-26)

> Kiadás-jegyzet: a JÁTÉKOS lapja. Eddig mindenki a csapatnak készült
> termékből próbálta kiolvasni magát: a klipcsomag tizennyolc emberé
> volt, a toplista zsákutca, a futómunka pedig egy nyers szám, amihez
> nem volt mihez viszonyítani. Mostantól a klip mezszámra szűkíthető
> (és a saját lapról egy kattintás), a toplista sora a játékos lapjára
> visz, és a lap megmondja, hol tart a kereten belül. Az őr-hármas az
> 503 rétegre tiszta: sorrend-függés 0, tükrözés 0 hibás, stride 24
> (változatlan).


- **"Hol tartok a kereten belül"** (motor + felület): a játékos-lap
  eddig nyers számokat mutatott — a "4,2 kilométer" magában nem
  válasz arra, hogy sokat futott-e vagy keveset. A görbe mostantól a
  keret-átlagot és a helyezést is viszi: futómunka **percre vetítve**
  (a végig játszó irányító és a tizenöt percet kapó szélső nyers
  métere nem összemérhető), a keret átlagához mérve, és hogy a
  legutóbbi meccsen hányadik volt a játszó emberek közt. Mezszám
  szerint összegzünk, nem trackenként: a megszakadt követés különben
  két embernek látszana, és lehúzná az átlagot. Kevés mintánál (rövid
  játékidő, öt játszó ember alatt) nincs ítélet — a lap el sem kezdi
  mutatni. A szöveg kimondja, hogy a több futómunka önmagában nem
  jobb: a poszt dönti el, mennyi kell belőle.

- **A klipcsomag egy játékosra szűkíthető** (motor + API + felület): a
  klipvágás eddig csapat-szintű volt — a #7 a tizennyolc emberes
  gólvideóból kereste ki magát, ami az edzés előtti öt percben nem
  történik meg. A Klipek lapon mostantól ki lehet jelölni, KINEK
  vágjuk: a felkínált mezszámok a backendtől jönnek, jelenet-
  darabszámmal (kiosztatlan szám nem is jelenik meg), a kijelölés a
  fájlnévbe is bekerül, és üres kijelölés továbbra is az egész
  csapatot jelenti. Ha egy mezszámhoz nincs kért jelenet, a program
  megmondja, miért — nem néma "nem készült klip".

- **"Klipjeim" a játékos saját lapján** (felület): a játékos a számok
  után a videót akarja látni. A játékos-fejlődés lapról egy gomb a
  Klipek képernyőre visz, az ő mezszámával ELŐRE KIJELÖLVE — nem kell
  újra kikeresnie magát a keretből. Ha az adott meccsen nincs
  jelenete, a kijelölés magától elmarad.

- **A toplista sorából a játékos saját lapjára** (felület): a Szezon
  képernyő toplistái zsákutcák voltak — a játékos megtalálta magát a
  góllövők közt, de a saját görbéjéhez és a "Mit gyakorolj" listájához
  vissza kellett mennie a menübe, és kézzel begépelnie a csapatot meg
  a mezszámot. A sor mostantól koppintható (nyíl jelzi), és a
  játékos-lapot ELŐRE KITÖLTVE nyitja meg.

## v0.1.71 — kiadva (2026-08-26)

> Kiadás-jegyzet: az EMBER a lapon. A kézzel felvett gólnak mostantól
> lövője van (különben a góllövő-listákból kimaradt volna), a
> "Mit gyakorolj" ott van a meccs utáni játékos-lapon is, a Keret
> megmutatja, kivel van dolga az edzőnek, és a program sehol nem mond
> kevesebbet, mint a saját nyomtatványa. Az őr-hármas az 503 rétegre
> tiszta: sorrend-függés 0, tükrözés 0 hibás, stride 24 (változatlan).

- **A jegyzet-klipcsomag nem kínál működésképtelen kapcsolót**
  (felület): a "jegyzetelt pillanatok" csomag jegyzet nélkül némán
  üres zip-et adott volna. A Klipek lap mostantól kiírja, hány jegyzet
  van a meccshez, és ha nincs, letiltva megmondja, hol lehet írni.

- **A jegyzet-lista a legújabb meccsel kezd** (motor): a hét közbeni
  munka a legutóbbi meccsből indul; húsz meccs jegyzetei közt a
  felvételi sorrend semmit nem mondott. Meccsen belül marad az
  időrend, mert a jegyzetek a meccs menetét követik.

- **A kézzel felvett gólnak lehet LÖVŐJE** (motor + felület): eddig a
  javítás a gólt felvette az eredménybe, de a góllövő-listákból
  kimaradt — pedig az edző pont azt a gólt vette fel, amit a
  felismerés kihagyott, és pont annak a játékosnak nem számított. Ha
  ki van jelölve játékos a pályán, ő lesz a lövő; a menü meg is
  mondja, kiről van szó. Lövő nélkül is érvényes a javítás: nem
  mindig tudjuk, ki volt.

- **A meccsterv stílus-kártyája olvasható lett** (felület): a 0..1
  nyers szám nem tanács — csak az érti, aki a képletet ismeri.
  Mostantól százalék áll ott, és minden tengely alatt egy mondat
  arról, mit jelent a MAGASABB érték (pl. "magasabb = többet lő
  távolról"). Új őr-teszt köti össze a motor tengely-neveit a
  kliens-magyarázatokkal: átnevezésnél a magyarázat nem maradhat
  némán el.

- **"Mit gyakorolj" a meccs utáni játékos-lapon is** (motor): a
  szezon-lapon a VISSZATÉRŐ tételek állnak, itt a mai meccsé. A
  játékos ezért a részért teszi el a lapot — ha csak a számok lennének
  rajta, egyszer nézné meg. (A meccs-csomag `jatekos_lapok/` mappája
  is ezt a lapot viszi.)

- **A teljes lánc a mai újdonságokat is végigjárja** (teszt): a
  videó → feldolgozás → jelentés → csomag kör kiegészült a kézi
  javítással (a felvett gól átüt az esemény-listán, és a jelentés ki
  is mondja), a mezszám–név–keret–egyéni fókusz úttal, és az
  edzésterv nyomtatható lapjával. A modul-tesztek darabonként őrzik a
  motort; ez a kör azt mutatja meg, ha a VALÓDI úton szakad meg
  valami.

- **457. meccsterv-szabály: a hajrá-célpont** (motor): az ő
  hajrá-hibázójuk × a mi hajrá-mérlegünk — az utolsó percekben tudjuk,
  kit kell döntés-kényszerbe hozni. Csak akkor szólal meg, ha MI
  bírjuk a végjátékot: különben nem a mi fegyverünk, hanem üres
  jótanács.
- **A mentés viszi az EMBERI munkát** (teszt): a mezszám-nevek és a
  kézi esemény-javítások nem a videóból jönnek — valaki beírta őket.
  Új teszt bizonyítja, hogy a gépváltás (mentés → visszaállítás új
  gépen) mindkettőt megőrzi, és a javítás az új gépen is ÉL.

- **Az egyéni feladatok az Edzésterv EGY MECCS nézetében is**
  (felület): a végpont a csapat-lista mellett ezt is adja, és a
  szezon-nézet mutatja — ha itt kimaradna, a két nézet mást mondana
  ugyanarról a meccsről.
- **A jelentés kimondja a kézi javítást** (motor): ha az edző javította
  a felismerést, a nyomtatott lap megbízhatóság-szakasza megmutatja,
  hány javítás van benne. A jelentés így is a mérésről szól — de az
  olvasó (másik edző, vezetőség) lássa, hogy egy része emberi döntés.

- **A klip-export megnevezi az üres csomagokat** (motor + felület):
  aki hat csomagot kért és egy zip-et kapott, eddig nem tudta, hogy
  kettőhöz nem volt jelenet, vagy elromlott valami. A vágás eredménye
  mostantól típusonkénti darabszámot és a NÉMÁN üres csomagok listáját
  is viszi, és ez a záró üzenetben is megjelenik.
- **A jegyzet törölhető a Jegyzetek lapról** (felület): a lista az edző
  teendő-listája — a kipipált tételnek le kell tudnia kerülni róla.
  Megerősítéssel, mert a jegyzet gépelt szöveg, nem újratermelhető
  adat.

- **A Keret-lap megmutatja, kivel van dolga az edzőnek** (felület): a
  tábla eddig azt mutatta, ki mit teljesített — az edző viszont azért
  nézi végig a keretet, hogy eldöntse, kivel kell foglalkoznia. Az új
  oszlop a gyakorolnivalók számát hozza az egyéni edzés-tervből (egy
  kérés az egész keretre); a részletes lista a játékos görbéjén van.

- **Az egyéni edzés-fókusz védekezést is ad** (motor): a réteg hét
  forrásból dolgozik — bekerült az **egy az egy elleni védekezés** (a
  hozzá rendelhető kapott gólok mekkora része esett nála). E nélkül a
  lap csak a támadó-oldali hibákat sorolta, és a védekező munkát végző
  emberek úgy nézték, hogy nincs mit gyakorolniuk.

- **Az egyéni feladatok a képernyőn is, nem csak a nyomtatványon**
  (motor + felület): az edzésterv-lap viszi az egyéni feladatokat — a
  képernyő eddig nem, tehát a program kevesebbet mondott, mint a saját
  nyomtatványa. Új végpont (`/library/training-focus/players`), és a
  két felület KÖZÖS számolásból él. A csapat-választó mostantól minden
  csapatot kínál, nem csak azokat, akiknek van visszatérő
  csapat-gyengeségük: egyéni feladat akkor is lehet, ha csapat-szinten
  nincs kilógó hiba.

- **Az egyéni fókusz meccsenként egyszer számol** (motor): a
  szezon-szintű összegzés (a "Mit gyakorolj" és az edzésterv-lap)
  minden mezszámra újrafuttatta a réteget, az pedig minden
  forrás-mérését újraszámolta — húsz meccses könyvtárnál ez percekben
  mérhető. Mostantól meccsenként gyorsítótárazunk (a kulcs a kockaszám
  és a csapatnevek); a kézi esemény-javítás kifejezetten dobja a
  bejegyzést, mert a javítás a fókuszt is átírja.
- **A ROADMAP feljegyzi a javíthatatlan felismerés hibafajtáját** — a
  megoldással és a hihetőség-ellenőrzésekkel együtt.

## v0.1.70 — kiadva (2026-08-26)

> Kiadás-jegyzet: a papír és a célpont. A két új munkalap
> (Edzésterv, Meccsterv) mostantól nyomtatható — a pályán és a meccs
> előtti estén nincs képernyő. Az egyéni gyengeség pedig átmegy a
> meccstervre: nem "figyeljetek a labdabiztonságukra", hanem "a
> 7-esükre kettőzz". Mellette a motor szól, ha a felismert eredmény
> aránytalan — az egyik kapu felismerése külön is elromolhat.

- **"Aránytalan eredmény" figyelmeztetés** (motor): a két kapu
  felismerése KÜLÖN romolhat el (féloldalas kalibráció, takart kapu).
  Kézilabdában a nagy különbség is jellemzően kétszeres arány körül
  van; ötszörös eltérés (legalább 12 gól mellett) inkább azt jelenti,
  hogy az egyik oldalon nem látjuk a gólokat. A figyelmeztetés ezt
  kimondja, és a teendő-rangsorban a MINDKÉT térfél kalibrációjának
  ellenőrzésére küld.
- **Az egyéni feladatok a meccs-csomag edzéstervében is** (felület): a
  zip `edzesterv.txt` fájlja eddig csak a csapat-szintű fókuszokat
  hozta — az edző viszont emberre bontva osztja ki a hét munkáját, és
  a csomagot sokszor épp ezért nyitja meg.

- **Az egyéni gyengeség átmegy a MECCSTERVRE** (motor + felület): az
  általános felderítő-kulcsok a CSAPATRÓL szólnak — a meccsterv viszont
  attól lesz konkrét, hogy KIRE mit kell csinálni. A jelentés
  mostantól viszi, hogy melyik MEZSZÁM veszti el a labdát nyomás
  alatt, és kinek a kezén szakad el a hajrában (mezszámonkénti
  darabszám, tehát meccsek közt pontosan összegződik: ami több
  meccsen visszatér, az nem napi forma). Ebből lett két új edzői
  kulcs, a **456. meccsterv-szabály** (az ő nyomás-érzékeny emberük ×
  a ti labdaszerző védekezésetek — a kettőzésnek célpontja van, nem
  iránya) és két kliens-csempe (Kettőzés-célpont, Hajrá-célpont).
- **476. edzés-szabály: közös gyengeség** (motor): ha ugyanaz a hiba
  KÉT vagy több emberünknél jön elő, az már nem egyéni ügy, hanem
  csoportos edzés-blokk — a szabály meg is nevezi, kiknek.

- **Az egyéni edzés-fókusz két új forrása** (motor): a réteg négy
  helyett hat mérésből dolgozik — bekerült a **hosszú labda döntése**
  (kinek az indításai foghatók el) és a **döntés a hajrában** (kinél
  szakad el a labda a döntő szakaszban). Az őr-teszt is bővült: a
  "top"-ot adó rétegek MEZŐNEVEIT is ellenőrzi a valódi kimeneten,
  mert a szabályok try/except-je egy elgépelt kulcsot némán elnyelne.

- **Nyomtatható Edzésterv és Meccsterv** (motor + felület): a pályán
  és a meccs előtti estén nincs képernyő — az edző a papírt viszi. A
  két ma született munkalap eddig csak a képernyőn élt. Az
  **edzésterv-lap** (új végpont, `/library/training-focus/export`) egy
  oldalon hozza a csapat visszatérő gyakorlandóit ÉS az egyéni
  feladatokat mezszám (és név) szerint; üres listánál kimondja, hogy
  ez eredmény, nem hiányzó adat. A **meccsterv-lap** az ellenfél
  felderítését és a páros-specifikus tervet adja — a saját oldal a
  SAJÁT csapat saját meccseiből épül, nem abból a feltevésből, hogy mi
  voltunk az ellenfelük.

## v0.1.69 — kiadva (2026-08-26)

> Kiadás-jegyzet: a játékos lapjának lezárása. A "Mit gyakorolj"
> mostantól nem csak a nyomtatott szezon-lapon van rajta, hanem a
> képernyőn is, a saját görbe mellett — és a kettő ugyanabból a
> számolásból él. Plusz a recept egy új szabállyal: ha egy réteg
> MÁSIK réteg mezőit olvassa, kell mellé teszt, ami a valódi
> rétegeket futtatja (a try/except az elgépelt mezőnevet is elnyeli).

- **"Mit gyakorolj" a játékos KÉPERNYŐJÉN is** (motor + felület): a
  játékos a saját görbéjét nézi meg — a teendő legyen mellette, ne egy
  külön letöltött HTML-ben. Új végpont (`/players/focus`); a képernyő
  és a nyomtatott lap ugyanabból a számolásból él.
- **"Mit gyakorolj" a játékos szezon-lapján** (motor): a nyomtatható
  játékos-lap eddig azt mutatta, hány kilométert futott és hány gólt
  szerzett — ez az a rész, amiért a JÁTÉKOS elteszi a lapot: min kell
  dolgoznia. Az egyéni edzés-fókusz minden meccsből összegyűlik erre a
  mezszámra, és ami több meccsen visszatér, az kerül előre: az nem
  napi forma, hanem fejlesztendő terület.

## v0.1.68 — kiadva (2026-08-26)

> Kiadás-jegyzet: a JÁTÉKOS kiadása. Eddig minden elemzés a csapatról
> szólt; az 503. réteg emberre bontja a hét feladatait — nem "a csapat
> rosszul fejez be", hanem "neked ez a kettő". Ott van a képernyőn, az
> edzői összefoglalóban és a nyomtatott jelentésen is, mert az egyéni
> beszélgetés a papírból indul.

- **Az egyéni edzés-fókusz a nyomtatott jelentésben is** (felület): a
  papír az, amit az edző a kezébe vesz a hét első edzésén — az egyéni
  beszélgetés abból indul, nem a csapat-listából.
- **Egyéni edzés-fókusz** (új réteg, `player_training_focus`): a
  csapat-szintű fókusz megmondja, mit gyakoroljon a CSAPAT — a játékos
  viszont a saját nevét keresi, és az edző is emberre bontva osztja ki
  a hét feladatait. Az új réteg a már meglévő játékos-szintű
  mérésekből állít össze személyes fókuszokat, ugyanabban az alakban,
  mint a csapat-lista (terület, fókusz, indok, gyakorlat). Négy forrás,
  mind a maga küszöbével: nyomás alatti labdakezelés, fáradt eladás,
  befejezés a helyzetminőséghez képest (gól − xG), és második félidei
  tempó-esés. Emberenként legfeljebb két tétel — a fókusz attól fókusz,
  hogy kevés; üres lista érvényes eredmény (a mért területeken senkinél
  nincs kilógó gyengeség). Felületek: `/analyze` és a meccs-csomag, az
  edzés-végpont `players` kulcsa, az edzői összefoglaló új szakasza és
  az összegző panel EGYÉNI EDZÉS-FÓKUSZ csempéje. A tesztek közt egy
  őr, ami a VALÓDI forrás-rétegekkel fut: a szabályok `try/except`-ben
  ülnek, ami egy elgépelt mezőnevet is elnyelne — a szabály némán
  semmit sem csinálna, a teszt pedig zöld maradna.

## v0.1.67 — kiadva (2026-08-25)

> Kiadás-jegyzet: a BIZALOM kiadása. A felismerés téved — eddig ezt
> semmivel nem lehetett javítani, az edző pedig egy rossz eredményű
> jelentésnek egyetlen számát sem hiszi el, akkor sem, ha a többi jó.
> Mostantól a gólok kézzel javíthatók, a javítás az egész elemzésen
> átüt, az állás ott van a lista tetején, és a motor maga szól, ha az
> eredmény hihetetlenül kevés. Mellette a mezszám-kiosztás egy
> menetben — ez a kapuőr minden szezon-szintű lap előtt.

- **Mezszámok kiosztása egy menetben** (felület): a mezszám kapuőr —
  meccsek között csak ez köti össze a játékost, tehát nélküle a Keret,
  a toplisták és a Játékos-fejlődés néma marad. Eddig a szerkesztés
  játékosonként külön párbeszéd volt (pályára kattintás → ikon →
  ablak); tizennégy emberre ez nem munka, hanem elrettentés — és ezért
  maradt el. Az új listában minden követett játékos egy sor, JÁTÉKIDŐ
  szerint csökkenő sorrendben (elöl a valódi trackek, hátul a
  másodperces töredékek), csapatonként csoportosítva; mentéskor csak a
  változott sorok mennek el.

- **Eredmény-sáv az Események lapon** (felület): az edző az
  EREDMÉNYBŐL dönti el, hogy hisz-e a jelentésnek — ha a felismerés
  21–19-et mond a valós 24–22 helyett, a többi szám sem ér semmit a
  szemében. Az állás mostantól ott van a lista tetején, és mellette a
  mondat, hogy javítható (különben a javítás-eszközök rejtve
  maradnának); kézi javítás után a sáv a javítások számát mutatja.
- **"Gyanúsan kevés gól" figyelmeztetés** (motor): kézilabdában a két
  csapat együtt percenként nagyjából egy gólt szerez. Ha a felismerés
  ennek a töredékét látja (0,30 gól/perc alatt, legalább 10 perces
  felvételen), nem szoros meccset mért, hanem gólokat hagyott ki —
  jellemzően lövésként jelölte őket. A figyelmeztetés ezt kimondja, és
  megmondja, hol javítható: nem zsákutca, hanem teendő.

- **A felismerés kézzel javítható** (motor + felület): a felismerés
  téved — gólt lövésnek lát, lövést nem vesz észre —, és eddig ezt
  semmivel nem lehetett javítani. Az edző pedig egy rossz eredményű
  jelentésnek EGYETLEN számát sem hiszi el, akkor sem, ha a többi jó.
  Az eseménysoron mostantól három javítás érhető el ("ez GÓL volt",
  "ez csak lövés volt", "nem volt ilyen esemény"), a hiányzó gól pedig
  felvehető a jelenlegi pillanatra. A javítás a LÖVÉS-FELISMERÉSBE
  épül be, tehát minden rétegen átüt (eredmény, xG, lövő-listák,
  hajrá-elemzés, felderítés) — egyetlen helyen javítunk, nem
  ötszázon; a kézi eredetet a lista meg is jelöli, és minden javítás
  visszavonható. A javítás a MECCS tulajdonsága: külön fájlban él a
  meccs mellett, túléli a program újraindítását, és a
  könyvtár-mentésbe is bekerül. Az egyeztetés-ablak másodpercben van
  (`OVERRIDE_MATCH_S`), és egy régi, elcsúszott javítás csendben
  elmarad ahelyett, hogy egy MÁSIK esemény típusát írná át.

## v0.1.66 — kiadva (2026-08-25)

> Kiadás-jegyzet: a bal oldali menü kiegészítésének második köre, és
> egy régi adósság törlesztése. A játékosok mostantól NEVET kapnak, nem
> csak mezszámot — az edző nem számokban gondolkodik, a játékos pedig a
> saját nevét keresi a lapon. Mellette négy új menüpont (Klipek, Keret,
> Csapat-fejlődés, Jegyzetek), és a klipvágás két néma hibájának
> javítása.

- **A játékosok nevet kapnak, nem csak számot** (motor + felület): az
  egész termék "#7"-et mondott — az edző viszont nem számokban
  gondolkodik, a játékos pedig a saját nevét keresi. A név a
  CSAPATHOZ és a mezszámhoz tartozik, nem egy meccshez (a mezszám a
  szezonban stabil, a track-azonosító nem), ezért egy helyen kell
  megadni: a Keret-lapon, ceruza-ikonnal. Onnantól minden korábbi és
  későbbi meccsen látszik — keret, toplisták, játékos-fejlődés,
  nyomtatható szezon-lap. Új végpontok: `GET/POST /library/players`;
  a névjegyzék a meccs-mappa MELLETT él (a betöltő minden ottani
  *.json-t meccsnek próbál olvasni), és a könyvtár-mentésbe így is
  bekerül. A név kényelem, nem adat: sérült névjegyzék mellett a
  lapok a mezszámokkal ugyanúgy működnek.

- **Jegyzetek menüpont: egy lista, meccsektől függetlenül** (motor +
  felület): a jegyzetelés eddig egyirányú volt — a meccs közben meg
  lehetett jelölni egy pillanatot, de utána csak ANNAK a meccsnek a
  lejátszójában lehetett megtalálni. Az edző fejében viszont a
  jegyzetek egyetlen listát alkotnak ("amit vissza akarok nézni"), és
  a hét közbeni munka ebből indul. Új végpont (`/library/notes`) az
  összes jegyzettel, meccs-környezettel és JÁTÉKIDŐVEL (a
  képkocka-index az edzőnek semmit nem mond); a képernyő kereshető, és
  egy sorra koppintva a meccs-elemző a MEGJELÖLT pillanatnál nyílik.

- **Keret menüpont: a csapat MINDEN mezszáma egy táblában** (motor +
  felület): a szezon-toplisták az öt legjobbat adják — a játékos
  viszont nem a gólkirályt keresi, hanem a SAJÁT sorát, az edző pedig
  a teljes keretet nézi végig. Új végpont (`/library/roster`) a csapat
  minden mezszámával: meccs-darabszám, gól, gólpassz, blokk,
  labdaszerzés, védés. A meccs-oszlop szándékosan az első: enélkül egy
  alacsony gólszám félrevezet (kevés játék vagy gyenge forma? — két
  külön teendő). A tábla rendezhető, egy sorra koppintva a játékos
  fejlődés-görbéje nyílik ELŐRE KITÖLTVE. A toplista és a keret-lap
  ugyanabból a számolásból él, hogy ne tudjanak széttartani — teszt is
  méri az egyezést.
- **Csapat-fejlődés menüpont** (felület): a "fejlődünk-e?" kérdést
  eddig két párbeszéd-ablakon át, meccsenként kézzel kellett
  összekattintani (melyik időszak, melyik oldal) — annyi kattintás,
  hogy a gyakorlatban senki nem tette fel. Most egy csapatnév elég: a
  képernyő a könyvtárból összeszedi a csapat összes meccsét dátum
  szerint, és kettévágja korábbi/újabb időszakra; a vágópont húzható
  (szünet előtt vs után, régi vs új felállás). Az összevetést a
  meglévő fejlődés-nézet rajzolja — nem született belőle második,
  széttartó megjelenítés.

- **Klipek menüpont: szabadon kombinálható videó-csomagok** (felület):
  a klipvágás eddig csak a meccs-elemző eszköztárában élt, és ott is
  EGY csomag egyszerre — aki a gólokat és a kihagyott ziccereket is
  akarta, kétszer vágatott, két zip-be. Az új képernyőn a 19 csomag
  témák szerint csoportosítva áll (támadás · védekezés · kapus és
  helyzetek · a meccs gerince · egyéb), tetszőlegesen kijelölhető, és
  mind EGY zip-be kerül; négy gyors-összeállítás (teljes dosszié,
  támadás, védekezés, csak gólok) egy kattintás. A vágás haladása
  látszik — a néma várakozás megakadásnak látszik.
- **A klip-plafon típusonként igazságos** (motor, javítás): a hatvan
  klipes plafon eddig IDŐRENDBEN csonkolt, tehát aki sok csomagot kért
  egyszerre, a meccs első harmadát kapta meg, és a ritka csomagok
  (fordulópont, 7 a 6) simán kimaradtak, mert a gólok elvitték a
  keretet. Ez néma hiba: a zip tele van klippel, csak épp nem arról,
  amit az edző keresett. Mostantól minden kért típus kap kvótát (a
  szűkösek teljes anyaga befér, a maradék a bővebbeké), és a típuson
  belül a meccs TELJES idősávjából mintázunk.
- **A klip-zip típus-mappákba rendez** (motor): egy tizenhárom
  csomagos dosszié hatvan fájlja egy lapos mappában kezelhetetlen, az
  edzésen pedig témánként kell levetíteni. Egyetlen típusnál marad a
  lapos alak.

## v0.1.65 — kiadva (2026-08-24)

> Kiadás-jegyzet: a bal oldali menü kiegészítése edzői és játékos
> szemmel. A motor sok mindent tudott, aminek a felületen nem volt
> HELYE: az edzésterv, a szezon-toplisták és a meccsterv a kezdőlap,
> illetve a felderítés mélyén lakott. Egy funkció, amit nem találnak
> meg, nem létezik.

- **Meccsterv saját menüponttal** (felület): a meccs előtti este EGY
  kérdése — hogyan verjük meg ŐKET. A meccsterv-illesztés (a mi
  profilunk × az ő profiljuk) készen volt, de csak a felderítő
  jelentés egyik kártyájaként: hozzá kézzel kellett kijelölni minden
  meccset, amelyiken az ellenfél játszott, és külön a sajátjainkat is.
  Az új képernyőn két csapatnév elég (MI · ŐK) — a meccseket a
  könyvtárból maga gyűjti össze, oldallal együtt. Két rész: a
  sorszámozott, páros-specifikus TERV, és a STÍLUS-hasonlóság
  (0–100) a három legnagyobb eltérésű tengellyel — tükör-meccsen a
  részletek döntenek, ellentétes stílusnál az, ki kényszeríti rá a
  sajátját.

- **CSAPAT menücsoport: Edzésterv és Szezon** (felület): a bal oldali
  menü eddig két csoportot ismert (MUNKAFOLYAMAT, ELEMZÉS), és minden
  csapat-szintű munka a kezdőlap mélyén lakott. Aki nem görgetett
  odáig, nem is tudott róluk — pedig készen voltak a motorban.
  - **Edzésterv** (új képernyő): edzői szemmel a heti munkalap.
    SZEZON nézet = ami legalább KÉT meccsen előjött ugyanannál a
    csapatnál (`/library/training-focus`) — ez nem egyszeri kisiklás,
    hanem edzhető gyengeség; EGY MECCS nézet = a kiválasztott meccs
    fókuszai. Minden tétel: terület, fókusz, INDOK és konkrét
    gyakorlat.
  - **Szezon** (új képernyő): edzői szemmel az összkép (meccsek, mért
    játékidő, gól, lövés, védés, sprint, táv) és a nyomtatható
    szezon-/egymás elleni riport; JÁTÉKOS szemmel a toplisták (gól,
    gólpassz, blokk, labdaszerzés, védés) mezszám szerint. A lap
    kimondja, hogy a mezszám nélküli játékos KIMARAD a listából —
    különben hiányzó teljesítménynek olvasná.
  - A Játékos-fejlődés átkerült ide (nem egy meccsről szól), a menü
    tíz elemű lett, és a tizedikhez is jár gyorsbillentyű
    (Cmd/Ctrl+0).


- **Tíz esés-réteg a hajrá-profilban** (motor): a hajrá-profil eddig
  hét esés-jelet nézett, pedig a csomagban ennél több van — így az
  "egy lapon" ígéret hiányos volt. Bekötve az **elszálló labdák**
  (`turnover_fade`), az **elfogyó blokk** (`block_fade`) és a
  **beragadó befejezés** (`finish_fade`). A rangsor két kimondott elve
  most már a docstringben is ott áll: elöl, ami KÖZVETLENÜL gólt ér
  (kontra-ablak, eladott labda), utána a fal munkája (hely, nyomás,
  blokk), majd a támadó-oldali beszűkülés; hátul, ami inkább TÜNET
  (befejezés, sprint). Új őr-teszt mind a tíz olvasót megszólaltatja
  egyszerre — egy jel, amit felveszünk a listára, de az olvasója
  sosem fut le, némán hiányzik.

## v0.1.64 — kiadva (2026-08-24)

> Kiadás-jegyzet: egy hiány javítása a saját munkánkban. Az új réteg
> megszólalt a saját csempéjén, de az összképből kimaradt — az edző
> pedig az összképet olvassa. Egy réteg akkor kész, ha a szintézisben
> is ott van.


- **A támadás-mélység esése bekerült a hajrá-profilba** (motor): az új
  réteg a saját csempéjén megszólalt, de az ÖSSZKÉPBŐL kimaradt — ami
  rosszabb a semminél, mert az edző azt hiszi, mindent lát. (A
  hajrá-profil saját tesztje pontosan ezt mondja ki.) A rangsorban a
  beálló-esés UTÁN áll — az elárvult hatos vonal konkrétabb tét, mint
  a felállás hátrébb csúszása —, de a szélső-esés ELŐTT.

## v0.1.63 — kiadva (2026-08-24)

> Kiadás-jegyzet: az 502. elemző réteg, és a gyorsítótár
> szemantikájának lezárása. Az új réteg a fáradás legőszintébb jelét
> méri: hátrébb áll-e a támadás a hajrában. A hatos elleni munka
> (betörés, beugrás, elzárás utáni leválás) lábat kíván, és aki
> elfárad, egy lépéssel hátrébb marad — onnan viszont már csak a
> kényelmes, de nehéz átlövés jön. Ez hamarabb látszik, mint a
> lövés-távolság esése, mert nem kell hozzá lövés.


- **Támadás-mélység a hajrában** (új réteg, `attack_depth_fade`): a
  támadás-mélység megmondja, milyen messze állnak a kaputól felállt
  támadásban; ez a réteg azt teszi hozzá, hogy VÁLTOZIK-E a meccs
  alatt. A fáradás egyik legőszintébb jele: a hatos elleni munka
  (betörés, beugrás, elzárás utáni leválás) lábat kíván, és aki
  elfárad, egy lépéssel hátrébb marad — onnan viszont már csak a
  kényelmes, de nehéz átlövés jön. A `shot_distance_fade` a LÖVÉS
  helyét méri, ez a FELÁLLÁSÉT: a kettő oka ugyanaz, de a második
  hamarabb látszik, mert nem kell hozzá lövés. Ellenfélként a hajrára
  a fal beljebb tömörülhet (kilépésre nincs szükség, ha úgysem jönnek
  be); saját csapatra a teendő a hajrá-támadások első mozdulatának
  kikötése: valakinek BE kell indulnia. Felületek: /analyze,
  meccs-csomag, edzői összefoglaló, felderítés (edzői kulcs + 455.
  meccsterv-szabály), edzés-fókusz (475. szabály), kliens-csempe.

- **A gyorsítótár-kulcs szemantikája rögzítve** (motor + teszt): a
  v0.1.62-es javítás után a záró "nincs megadva" jelentésű
  argumentumok is kimaradnak a kulcsból, tehát a `réteg(meccs)`, a
  `réteg(meccs, None)` és a `réteg(meccs, alapbeállítás)` mind
  UGYANAZT az eredményt olvassa — mindhárom szó szerint ugyanazt
  számolja. A hívás maga változatlan (az eredeti argumentumokkal megy
  tovább), csak a kulcs rövidül. Teszt rögzíti, hogy a MÓDOSÍTOTT
  beállítás továbbra is külön kulcsot kap: a normalizálás nem moshatja
  össze a különböző beállításokat, mert az azt jelentené, hogy egy
  réteg más beállítás eredményét olvassa.

## v0.1.62 — kiadva (2026-08-24)

> Kiadás-jegyzet: rövidebb várakozás és őszintébb csomag. A
> gyorsítótár egy régi hiányossága miatt ugyanaz a mérés kétszer
> futott le, ha az egyik hívó kifejezetten átadta az alapértelmezett
> beállítást — javítva: az edzői összefoglaló 16, az ellenszer-lap 27
> százalékkal gyorsabb. Emellett a meccs-csomag mostantól megnevezi,
> ha egy elemzés mégsem készült el (a szöveges lapon is), és egy új
> teszt a TELJES láncot végigjárja egy videótól a csomagig.


- **Gyorsítás: az alapértelmezett beállítás nem számol újra** (motor):
  a gyorsítótár kulcsába a hívás argumentumai is beleszámítanak — és
  kiderült, hogy a `réteg(meccs)` és a `réteg(meccs, TacticsConfig())`
  KÜLÖN kulcsot kapott, pedig a `None` épp egy alapértelmezett
  beállítást jelent. Ugyanaz a mérés így kétszer futott le. A kulcs
  mostantól az alapértelmezett beállítást a `None`-nal azonosnak veszi
  (csak akkor, ha a mezői tényleg az alapértékek). Mérve, 15 perces
  meccsen: edzői összefoglaló 44,2 → 37,1 mp (−16%), ellenszer-lap
  30,5 → 22,2 mp (−27%). Az őr-hármas változatlan: sorrend-függés 0,
  tükrözés 0 hibás.
- **Gyorsítás: a hajrá-rétegek a hatókörbe** (motor): a mai öt
  esés-réteg és a hajrá-profil is memoizált lett. Ezeket az edzői
  összefoglaló és a hajrá-profil is kéri, és mindegyik a saját
  alap-mérését KÉTSZER számolja (a két félidőre külön) — valódi
  meccsen ez rétegenként tized-másodpercek, összeadva másodpercek.

- **Új teszt: a TELJES lánc egy futásban** (teszt): a modul-tesztek
  darabonként őrzik a motort, a réteg-regiszter őrei pedig szimulált
  meccsen néznek mindent — a kettő közt maradt egy rés: a valódi
  útvonal, ahol egy VIDEÓBÓL indulunk, a detektálás és az utómunka
  lefut, és a végén a felhasználó jelentést meg csomagot kap. Egy nap
  alatt hét idő-küszöböt és több némán kimaradó ágat javítottunk —
  pont az ilyen kör mutatja meg, ha valamelyik javítás elrontotta a
  valódi utat. Az új teszt végigmegy rajta: előellenőrzés →
  feldolgozás (másodperces hossz-korláttal) → a mentés meccs-ablak
  mezői → minőség-jelentés (feldolgozott szakasz, pótolt labda,
  korábbi pontszámok) → meccs-csomag (minden réteg elkészül) →
  nyomtatható jelentés.

- **A csomag szöveges lapja is szól a kimaradt elemzésekről** (motor):
  az elhasalt rétegek listája a v0.1.61 óta bekerül a csomag
  JSON-jába — de a ZIP-et megkapó edző jellemzően az
  `osszefoglalo.txt`-et nyitja meg elsőként. Ha ott nincs jelzés, a
  hiányzó elemzés ugyanúgy nyom nélkül marad el. Mostantól a szöveges
  lap végén ott a figyelmeztetés a darabszámmal és azzal, hol találja
  a neveket.

## v0.1.61 — kiadva (2026-08-24)

> Kiadás-jegyzet: a "néma kód" elleni kör. A motor minden rétegét és
> szabályát `try/except` védi, hogy egy elromló darab ne vigye el a
> többit — ez helyes, de az ára, hogy egy elgépelt név NÉMÁN semmit
> nem csinál, és a tesztek zöldek maradnak. Ma öt ilyen szabályt
> találtunk (a v0.1.60 javította őket); most a HIBAFAJTA kapott
> ellenszert: statikus őr a definiálatlan nevekre, az elgépelt
> felderítés-mezőnevekre és a rossz alakú edzés-tételekre — plusz a
> meccs-csomag mostantól megnevezi, ha egy réteg mégis elhasalt,
> ahelyett hogy nyom nélkül eltűnne.


- **A meccs-csomag megnevezi az elhasalt rétegeket** (motor): a
  csomagban minden elemző réteget `try/except` véd, hogy egy réteg
  hibája ne vigye el a többit. Az ára eddig az volt, hogy egy elhasaló
  réteg NYOM NÉLKÜL eltűnt: a kulcs nem került be, a felhasználó pedig
  azt hitte, az az elemzés nem is létezik. Mostantól a csomag mindig
  visz egy `_hibas_retegek` listát a réteg nevével és a hiba
  típusával — üresen is, mert a "nem hasalt el semmi" is állítás —, és
  ha volt hiba, a feldolgozás állapotüzenete is kimondja. A
  mintameccsen a lista üres, és ezt őr-teszt rögzíti.

- **Az őr párja: elgépelt felderítés-mezőnév** (teszt): a
  `rep.wif_fh_wingg` `AttributeError`-t dobna, amit a védő try/except
  ugyanúgy elnyel — a szabály némán kimarad. A meglévő "néma mező" őr
  ezt nem fogta meg (a nem létező név egyszerűen kiesett a mezők
  metszetéből), most külön ellenőrzés nézi. A kódbázis tisztán jött
  ki; az őr elbukását szándékos elgépeléssel ellenőriztem.
- **Új őr: definiálatlan nevek a motorban** (teszt): a v0.1.60-ban
  javított öt néma edzés-szabály gyökere egy elgépelt változónév volt.
  A rétegeket és szabályokat `try/except Exception: pass` védi —
  helyesen, hogy egy elromló réteg ne vigye el a többit —, így a
  `NameError` elveszik, a kód némán semmit nem csinál, és a tesztek
  zöldek maradnak. Futtatással ez nem elkapható; statikus elemzéssel
  harminc másodperc. Az új őr a Python hatókör-szabályait követve
  (függvény-, lambda- és osztály-hatókör külön) végigolvassa a motort
  és a szkripteket, és jelzi, ami sehol nincs kötve. Külső függősége
  nincs. A teljes kódbázis tisztán jött ki; az őr elbukását és a
  téves riasztás hiányát is teszt rögzíti.

## v0.1.60 — kiadva (2026-08-24)

> Kiadás-jegyzet: javító kiadás. A v0.1.56–57-ben bevezetett öt
> hajrá-edzésszabály (fal-mélység, visszaállás, széles játék,
> halmozott fáradás, beálló-bejátszás) NÉMÁN nem futott le: egy nem
> létező változóra hivatkoztak, a hibát pedig elnyelte a védő
> try/except, ami arra való, hogy egy elromló réteg ne vigye el a
> többit. A tesztek zöldek voltak, mert ezek a szabályok a
> mintameccsen amúgy sem szólaltak volna meg — a hibát csak MÉRÉSSEL
> lehetett megtalálni. Mind az öt javítva, és három új őr gondoskodik
> róla, hogy a "némán semmit nem csináló szabály" ne térhessen vissza.


- **JAVÍTÁS: öt új edzés-szabály soha nem futott le** (motor): a
  v0.1.56–57-ben bevezetett hajrá-rétegekhez tartozó öt edzés-fókusz
  szabály (fal-mélység, visszaállás, széles játék, halmozott fáradás,
  beálló-bejátszás) egy NEM LÉTEZŐ változóra hivatkozott. A szabályokat
  `try/except Exception: pass` védi — helyesen, hogy egy elromló réteg
  ne vigye el az egész listát —, így a `NameError` elveszett, és a
  szabályok némán semmit nem csináltak. A tesztek zöldek voltak, mert a
  fade-rétegek a mintameccsen nem szólalnak meg. Mind az öt javítva a
  közös `add(...)` alakra, ami a tétel szerkezetét (terület, cím,
  miért, gyakorlat) és a darabszám-korlátot is garantálja.
- **A hajrá-rétegek felderítés-oldali szabályai tesztet kaptak**
  (teszt): a réteg és a felület megléte nem elég — a kulcsnak MEG IS
  kell szólalnia a megfelelő adatra. Egy elgépelt mezőnév vagy egy
  rossz irányú összehasonlítás néma szabályt ad, és semmi nem hasal
  el. Az öt új edzői kulcs és az öt párosított meccsterv-szabály
  mostantól mind ellenőrzött (a beálló-szabály szándékosan más
  falformára szól, mint a szélső-szabály — ezt is rögzíti a teszt).
- **Új őr: az edzés-tételek csak a közös segéden át jöhetnek** (teszt):
  a fenti hiba a "némán eltűnő" fajtából való, amit futtatással nem
  lehet elkapni (a szabály amúgy sem szólalt volna meg). Az őr ezért a
  FORRÁST nézi: nyers `append` az edzés-listára tilos. Plusz egy párja,
  ami a tényleges kimenet alakját ellenőrzi a mintameccsen.

## v0.1.59 — kiadva (2026-08-24)

> Kiadás-jegyzet: az olvashatóság kiadása. Az ötszáz elemző réteg
> mellékhatása, hogy a jelentések MEGNŐTTEK: az edzői összefoglaló
> háromezer szavas lett (a "Játékkép és tempó" szakasz egymaga
> tizenhatezer karakter), a felderítés "Hogyan játssz ellenük"
> listája pedig 123 tételre. Egyik sem hibás — csak olvashatatlan.
> Hiányzott a FONTOSSÁGI SORREND, pedig a rendszer már kiszámolja.
> Mostantól az összefoglaló "A lényeg" szakasszal nyit (a rangsor
> első három tétele csapatonként, plusz hogy mennyi maradt), és a
> felderítésben a párosított meccsterv megelőzi a százas általános
> listát. Semmi nem veszett el: minden szakasz ott van mögötte.


- **A párosított meccsterv megelőzi az általános kulcsokat** (kliens +
  motor): a felderítés két listát ad. A "Hogyan játssz ellenük" kulcsok
  általánosak és SOKAN vannak — egy hatszáz másodperces mintameccsen
  123 kulcs, közel húszezer karakter. A meccsterv-szabályok viszont
  kifejezetten ERRE a párosításra szólnak ("az ő lassuló visszaállásuk
  × a ti kontrátok"), tehát azok a konkrétak. Eddig mégis a százas
  lista jött előbb — a felderítő képernyőn és a nyomtatható lapon is,
  ahol a meccsterv a támadás-mix és a védekezés-eloszlás MÖGÉ került.
  Mostantól mindkettőn a párosított terv áll elöl: aki két percet szán
  a felkészülésre, a konkrétat lássa elsőként.

- **Az edzői összefoglaló "A lényeg" szakasszal nyit** (motor): az
  ötszáz réteggel az összefoglaló HÁROMEZER szavassá nőtt — a
  "Játékkép és tempó" szakasz egymaga tizenhatezer karakter. Ezt
  végigolvasni nem reális, és a mondatokra bontás sem segít, ha
  negyven felsorolás-pont lesz belőle: a hiányzó darab a FONTOSSÁGI
  SORREND. A teendő-rangsor ezt már kiszámolja, csak eddig a jelentés
  belsejében lapult. Mostantól a meccs története (rövid, kontextust
  adó) után rögtön "A lényeg" jön: csapatonként a rangsor első három
  tétele, és hogy hány további jelzés maradt a részletes szakaszokra.
  Ez BEVEZETŐ, nem rövidítés — a hosszú szakaszok változatlanul ott
  vannak mögötte. Aki két percet szán a jelentésre, most is megkapja
  a három dolgot, ami számít. A kliens ezt a szakaszt nem csukja
  össze (a többi hosszú szakaszt öt mondat után igen): ha a nyolc
  tételéből ötöt mutatna, a rangsor vége és a "mennyi maradt" sor
  eltűnne — pont az, ami miatt a szakasz létezik. A nyomtatható
  meccsjelentésen kiemelt dobozba kerül: ha ugyanolyan felsorolás
  lenne, mint a többi tizennégy szakasz, elveszne bennük — pedig pont
  attól hasznos, hogy az olvasó ott megállhat.

## v0.1.58 — kiadva (2026-08-24)

> Kiadás-jegyzet: a visszacsatolás kiadása. Aki a gyenge feldolgozás
> után újrakalibrál és újrafuttat, eddig egy számot kapott a
> semmiben ("72/100") — most azt is megtudja, hogy JAVULT-E a
> legutóbbihoz képest. Emellett a labda-lefedettség többé nem hízik a
> saját hézagpótlásunktól: a szám azt méri, milyen gyakran LÁTTUK a
> labdát, a pótolt kockák külön jelennek meg. A háttérben négy új őr
> azokra a hibafajtákra, amiket nem lehet észrevenni: néma
> felderítés-mező, rossz feldolgozáson eltűnő réteg, elcsúszott
> kliens-küszöb.


- **A jelentés megmondja, hogy JAVULT-E** (motor + kliens): a
  minőség-pontszám eddig egy szám volt a semmiben. Aki a gyenge
  feldolgozás után újrakalibrál és újrafuttat, pont azt a választ
  keresi, hogy jó irányba ment-e — és a puszta "72/100" ezt nem mondja
  meg. A minőség-jelentés mostantól viszi a KORÁBBI feldolgozások
  pontszámát is (legfeljebb hármat, dátum szerint a legfrissebbel
  elöl), és a különbséget: "Javult: a legutóbbi feldolgozásod 41/100
  volt (+31 pont)." Az első feldolgozásnál üres a lista — nem találunk
  ki összehasonlítást. A pontszámok gyorsítótárazva vannak (a kulcsban
  a kockaszám is benne van, tehát egy újrafeldolgozott meccs friss
  pontszámot kap).

- **Új őr: nincs néma felderítés-mező** (teszt): a felderítés-jelentésnek
  több mint EZER mezője van, és a csempék meg a meccsterv-szabályok
  ezekből olvasnak. Ha egy mezőt senki nem tölt ki, az alapértéke
  (0 / üres) marad — a csempe pedig ÖRÖKRE néma, vagy ami rosszabb, a
  szabály hamis feltevéssel dolgozik. Semmi nem hasal el, semmi nem
  jelez: a réteg egyszerűen nincs ott, és senki nem tudja meg, hogy
  hiányzik. Az őr mindkét irányt nézi (olvasott-de-nem-töltött, és
  kiszámolt-de-sehol-nem-olvasott). Az első futás tisztán jött ki: az
  1052 mezőből egy sem néma.

- **Az őrök kiterjesztése** (teszt): (1) a réteg-eltűnés őre egy
  harmadik elfajzási esetet is néz — amikor a mezszín-klaszterezés
  összeomlik, és MINDEN játékos egy csapatba kerül (azonos színű mezek,
  rossz megvilágítás). Ilyenkor a legtöbb réteg jogosan hallgat, de a
  kulcsnak ott kell lennie. (2) A kliens-küszöb őre az indítás előtti
  detektálás-próbára is kiterjed: az a jelzés, ami elrontott
  kalibrációnál egy órát megspórol, a motoréval AZONOS küszöbnél kell
  megszólaljon. Az ellenőrzés a hivatkozás KÖRNYEZETÉBEN keresi az
  értéket — a fájl egésze túl laza lenne, mert egy véletlen tördelési
  szám "igazolna" egy elcsúszott küszöböt.

- **A labda-lefedettség nem hízik a saját pótlásunktól** (motor +
  kliens): a mutató eddig minden olyan kockát megszámolt, ahol volt
  labda-pozíció — beleértve azokat is, amiket MI pótoltunk a rövid
  hézagokba. Vagyis az őszinteség-mutató a saját találgatásunktól
  tűnt jobbnak, és a "kevés labda-észlelés" figyelmeztetés épp azokon
  a felvételeken hallgathatott, ahol a legnagyobb szükség lett volna
  rá. Mostantól a lefedettség azt méri, milyen gyakran LÁTTUK a
  labdát; a pótolt kockák külön számként jelennek meg (a kliens is
  így mutatja: "42% (+9% pótolt)"). A réteg-megbízhatóság
  labda-családja is a mért számot nézi.

- **Új őrök: a rossz feldolgozáson sem tűnhet el réteg nyom nélkül**
  (teszt): a meccs-csomag minden elemző rétegét `try/except` védi, hogy
  egy réteg hibája ne vigye el a többit — a hátulütő, hogy egy elhasaló
  réteg NÉMÁN eltűnik, és a felhasználó azt hiszi, az az elemzés nem is
  létezik. Eddig egy őr nézte ezt, a JÓ mintameccsen. Most a rossz eset
  párja is: (1) labda nélküli feldolgozás (távoli, széles felvételen
  reális), (2) két másodperces töredék (a megszakadt feldolgozás
  részleges mentése). Mindkettőn minden réteg-kulcsnak meg kell
  jelennie — a rétegnek nem kell mondania semmit (üres ítélet a helyes
  válasz kevés mintára), de a jelentés nem lehet némán hiányos. Épp
  ezeken a futásokon a legfontosabb, hogy a jelentés elmondja, mi
  történt.

## v0.1.57 — kiadva (2026-08-24)

> Kiadás-jegyzet: a "kocka vagy másodperc" kiadás. A feldolgozás
> ritkít (a termék alapja minden 3. kocka), és kiderült, hogy HÉT
> olyan küszöb volt a motorban, ami kockában szerepelt, pedig
> IDŐTARTAMOT jelent — vagyis a termék alapbeállításán mindegyik
> HÁROMSZOROS valós időt követelt. A leglátványosabb: a labda rövid
> eltűnéseit egyenes vonallal pótoljuk, de a "rövid" fél másodperc
> helyett közel másfél lett — annyi idő alatt kétszer is
> passzolhatnak, tehát a pótlás nem létező birtoklást és passzokat
> gyártott. A képen kívüli játékosokat pedig 2 helyett 6 másodpercig
> vetítettük előre egyenes vonalban, ami egy sprintelőt a pálya túlsó
> végébe visz. Mind a hét javítva, 25 fps-en pontosan az eredeti
> értékekre — ez nem hangolás, hanem a szándék helyreállítása.
> Mérhető hatás: a stride-érzékenységi jelentésből eltűnt a
> labdatartás-poszt réteg. Mellette két új őr, hogy ez a hibafajta ne
> jöjjön vissza, egy őr a kliens-küszöbök elcsúszására, és egy új
> elemzés (beálló-bevonás a hajrában).


- **Új őr: az idő-küszöbök nem eshetnek vissza kockára** (teszt +
  fejlesztési szabály): egyetlen nap alatt HÉT olyan küszöböt
  találtunk, ami kockában volt megadva, pedig IDŐTARTAMOT jelent — és
  mivel a feldolgozás ritkít, mindegyik háromszoros valós időt
  követelt a termék alapbeállításán. A visszaesés reális, ezért az
  átállított küszöbök kocka-alakja mostantól nem jelenhet meg futó
  kódban (csak visszafelé kompatibilis alapértékként, a saját
  definíciójában). A CLAUDE.md is kimondja a szabályt: MINTASZÁM
  maradhat kockában (100 minta tényleg 100 minta), IDŐTARTAM
  kötelezően másodpercben, a `match.meta.fps`-ből számolva.

- **Négy további idő-küszöb a valódi másodperchez igazítva** (motor):
  ugyanaz a hibafajta, mint a hossz-korlátnál, a labda-hézagpótlásnál
  és a becslésnél — kockában rögzített szám, ami valójában
  IDŐTARTAMOT jelent. Mivel a feldolgozás ritkít (a termék alapja
  minden 3. kocka), ezek a küszöbök a minőségi profiltól függően
  háromszoros valós időt követeltek:
  - **őrzési párok**: a kommentje eredetileg is "1 mp @ 25 fps"-t
    mondott, a termékben mégis HÁROM másodperces követést követelt —
    a rövid, de valódi őrzések kimaradtak a listából,
  - **blokkolt-poszt**: a lövőt a blokk előtti egy másodpercben
    keressük; ritkítva ez három másodperc visszanézés lett, és három
    másodperccel a blokk előtt rendszerint már MÁS volt a labdánál —
    vagyis a falba lőtt labdát a rossz posztra írhattuk,
  - **labdatartás**: az "ez csak érintés, nem birtoklás" küszöb 0,2
    helyett 0,6 másodperc lett,
  - **beálló-terhelés**: a villanás-szűrő szigora sem függhet a
    profiltól.
  Mind a négy 25 fps-en pontosan a régi érték, tehát ez az EREDETI
  szándék helyreállítása, nem hangolás.

- **A képen kívüli játékosok becslése nem szalad el** (motor): a
  pásztázó kamerából kicsúszott játékosokat az utolsó látott
  sebességükből vetítjük előre, és a sebesség hatása egy idő után
  "elfogy" (a játékos nem mozoghat örökké egyenesen). Ez az idő
  KOCKÁBAN volt megadva (50 kocka), a feldolgozás pedig ritkít: a
  termék alapbeállításán 2 helyett 6 másodpercig hatott. Egy 7 m/s-mal
  sprintelő játékost hat másodperc egyenes vonalú vetítés a pálya
  túlsó végébe visz — ami rosszabb, mint ha ott "megállna", ahol
  utoljára láttuk. Ugyanez állt a megbízhatóság felezési idejére is (1
  helyett 3 másodperc), vagyis a becsült pozíciók a kelleténél tovább
  látszottak magabiztosnak. Mindkettő mostantól VALÓS másodpercben
  értendő, a meccs saját képrátájából számolva — 25 fps-en pontosan a
  régi értékek, tehát ez az EREDETI szándék helyreállítása.

- **A labda-hézagpótlás nem gyárt többé nem létező passzokat** (motor):
  a felvételen a labda időnként eltűnik (takarás, motion blur), és a
  rövid hézagokat egyenes vonallal pótoljuk — mert a birtoklás-, passz-
  és lövés-felismerés folytonos labda-pályát igényel. A korlát viszont
  KOCKÁBAN volt megadva (12 kocka), a feldolgozás pedig ritkít: a
  termék alapbeállításán (minden 3. kocka) ez nem fél, hanem közel
  MÁSFÉL másodpercet jelentett. Másfél másodperc alatt kétszer is
  passzolhatnak — az odaképzelt egyenes vonal tehát nem létező
  birtoklást és passzokat gyártott, és pont a birtoklás-, passz- és
  eladás-alapú rétegek épülnek erre. A korlát mostantól VALÓS
  másodpercben értendő (fél másodperc — a takarás és a motion blur
  tipikus hossza, és pontosan ez volt az eredeti szándék is: 12 kocka
  25 fps-en). A hosszabb hézag marad üres: ott tényleg nincs adat, és
  ezt a labda-lefedettség száma is őszintén mutatja.
- **A kétperc-páros edzői kulcs a motor konstansait használja**
  (motor): eddig kézzel másolt számokkal (3 és 55%) dolgozott, most a
  réteg saját küszöbeit importálja — így egy küszöb-változás nem
  csúsztathatja szét a kulcsot és a réteget.

- **Beálló-bevonás a hajrában** (új réteg, `pivot_usage_fade`): a
  beálló-terhelés megmondja, a támadásaik mekkora része megy át a
  beállón; ez a réteg azt teszi hozzá, hogy ELFOGY-E a meccs alatt. A
  beállóba adott labda a kézilabda legnehezebb passza — takarásba,
  testek közé, pontos időzítéssel. Fáradtan ez fogy el először, és nem
  azért, mert a beálló nem dolgozik, hanem mert a KISZOLGÁLÓ nem meri
  (vagy nem látja) beadni. A következmény: a hatos vonal elárvul, a
  fal nyugodtan dolgozhat kifelé, és a támadás átlövésekbe szorul.
  Más kérdés, mint a szélső-bevonás esése: az a labda SZÉLES ívű
  járatásáról szól (lábmunka), ez a MÉLYSÉGI bejátszásról (bátorság és
  időzítés) — egy csapat elveszítheti a beállóját úgy is, hogy közben
  végig széthúzva játszik. Bekerült a hajrá-profil rangsorába is (a
  szélső-esés elé: elárvult hatos vonal mellett a fal kifelé dolgozhat,
  ami nagyobb tét, mint a középen ragadt labda). Felületek: /analyze,
  meccs-csomag, edzői összefoglaló, felderítés (edzői kulcs + 454.
  meccsterv-szabály), edzés-fókusz (474. szabály), kliens-csempe.

- **Új őr: a kliens küszöbei nem csúszhatnak el a motortól** (teszt):
  a felderítő képernyő közel ötszáz csempéje KÉZZEL másolt számokkal
  dolgozik ("8+ mért támadás", "60% részarány"), és minden helper
  kommentje megnevezi, melyik motor-konstanst tükrözi. Eddig semmi nem
  ellenőrizte, hogy a szám tényleg ugyanaz — egy elcsúszás azt
  jelentené, hogy a csempe olyat állít, amit a motor nem mondana ki
  (vagy hallgat ott, ahol a motor beszél), és ez a fajta hiba némán él
  évekig. Az új őr 363 küszöböt vet össze: megengedő az ÁBRÁZOLÁSSAL
  szemben (a Dart néha törtet használ százalék helyett, vagy kockát
  perc helyett), de szigorú a NÉVVEL: nem létező konstansra hivatkozni
  tilos, mert akkor a következő olvasó rossz helyen módosít. Az első
  futás egy rossz hivatkozást talált (a kétperc-páros csempe a
  KIÜLŐ-POSZT réteg konstansaira hivatkozott, más küszöbökkel — az
  értékek jók voltak, a név nem) és két félrevezető kommentet, ahol a
  szűrést valójában már a motor elvégzi. Mindhárom javítva.
- **Új őr: azonos nevű konstans két modulban** (teszt): ugyanaz a név
  eltérő értékkel két pipeline-modulban csapda, mert a kliens- és
  doksi-kommentek NÉVRE hivatkoznak. A hat meglévő ütközés dokumentálva
  (mind szándékos, pl. a kapuelőtér sugara a kapus-jelölésnél 6,8 m —
  a 6 m-es vonal plusz ráhagyás —, a szimulációban a valódi 6,0 m);
  újat csak tudatosan, a lista bővítésével lehet bevezetni.

- **Hajrá-profil** (új réteg, `fatigue_profile`): a csomagban egy tucat
  "esés"-réteg méri, mi változik a 2. félidőre (visszaállás,
  fal-mélység, védekezési nyomás, szélső-bevonás, sprint). Külön-külön
  mindegyik egy szám; együtt viszont az edző nem tudja, MIVEL kezdje —
  pontosan az a gond, amit a minőség-jelentésben az "első teendő" old
  meg. Ez a réteg összegyűjti a MEGSZÓLALÓ eséseket, és edzői leverage
  szerint rangsorolja: elöl az áll, ami közvetlenül gólt ér (a lassuló
  visszaállás minden lövés után kontra-ablakot nyit), utána a fal
  helye, és csak azután a támadó-oldali beszűkülés és a láb. Három
  egyidejű jel fölött külön kimondja, hogy ez már nem egy-egy szám,
  hanem a hatvan perc kérdése. Ha a lista ÜRES, az önmagában értékes
  információ: a csapat kibírja a hatvan percet, tehát ellene a meccset
  korábban kell eldönteni. Felületek: /analyze, meccs-csomag, edzői
  összefoglaló, felderítés (edzői kulcs + 453. meccsterv-szabály),
  edzés-fókusz (473. szabály), kliens-csempe.

- **Szélső-bevonás a hajrában** (új réteg, `wing_involvement_fade`): a
  szélső-bevonás megmondja, a támadásaik hány százalékában jár a labda
  a szél-sávban; ez a réteg azt teszi hozzá, hogy BESZŰKÜLNEK-E a
  meccs alatt. Ez a fáradás egyik legkorábbi jele, és a lövés-távolság
  esésének (`shot_distance_fade`) az OKA: a fáradó csapatban a lábmunka
  fogy el először, a labda nem megy át a széles ívben, minden támadás
  középen ragad — és onnan már csak a nehéz átlövés marad.
  Ellenfélként a hajrára a szélső-védők beljebb húzhatók; saját
  csapatra a teendő a hajrá-támadások első passzának kikötése a szélre
  (a labda gyorsabb, mint a láb). Felületek: /analyze, meccs-csomag,
  edzői összefoglaló, felderítés (edzői kulcs + 452. meccsterv-szabály),
  edzés-fókusz (472. szabály), kliens-csempe.

## v0.1.56 — kiadva (2026-08-24)

> Kiadás-jegyzet: az első éles meccs jelentésének utolsó nyitott
> pontjai. A hossz-beállítás mostantól TÉNYLEG annyi, amennyit ír
> (a régi számolás 25 fps-t feltételezett, egy 30 fps-es
> telefonvideón a "Félidő (~35 p)" 29 percet dolgozott fel — ez
> önmagában megmagyarázza a "csak az első félidőt elemezte ki"
> élményt). A jelentés megmondja, MELYIK szakaszt dolgozta fel a
> videó órája szerint, és hogy kimaradt-e a bemelegítés. A kézi
> időablak végre tényleg felülír minden felismerést. A meccsterv
> pedig — a legveszélyesebb hely, mert ez alapján dönt az edző —
> mostantól szintén elöl mondja meg, ha gyenge alapanyagból épült.
> Mellette két új elemzés a hajráról: hova áll a fal és milyen
> gyorsan ér haza a meccs végén.


- **A meccsterv is megmondja, mennyire hihető** (motor + kliens): az
  edzői összefoglaló és a nyomtatható meccsjelentés a v0.1.54 óta elöl
  visz egy figyelmeztetést gyenge feldolgozásnál — a FELDERÍTŐ jelentés
  viszont nem. Pedig ez a legveszélyesebb hely: a meccsterv az, ami
  alapján az edző dönt (kit állít a beállóra, hol fogja a legjobb
  lövőt, mikor kér időt), és minden mondata magabiztosan fogalmaz. Ha a
  mögötte lévő feldolgozás gyenge volt, a terv nem a másik csapatról
  szól, hanem a mérés zajáról. A jelentés mostantól viszi a mögötte
  lévő feldolgozások minőségét, és gyenge alapanyagnál a felderítő
  képernyő és a nyomtatható lap is ELÖL szól — a nyomtatott lapon a
  tartalomjegyzék után, az első szakasz előtt, ahogy a meccsjelentésben
  is. Több meccsből épült jelentésnél a gyenge feldolgozások SZÁMÁT is
  kimondja (5 meccsből 1 gyenge más helyzet, mint 5-ből 5). Régi
  jelentésről (nincs adat) továbbra sem állítunk semmit.

- **A nyomtatható jelentés is megmondja, melyik szakaszról szól**
  (motor): a lapot napokkal később olvassák vissza, és akkor már semmi
  nem árulja el, hogy a teljes meccsről szól-e vagy csak az első
  félidőről. A megbízhatóság-szakasz mostantól viszi a feldolgozott
  szakaszt a videó órája szerint (pl. "1:00–34:14"). Régi mentésnél
  (nincs adat) a sor egyszerűen kimarad — nem írunk oda kitalált
  értéket.

- **Visszaállás a hajrában** (új réteg, `retreat_fade`): a
  visszaállás-idő (`retreat_time`) megmondja, hány másodperc alatt áll
  össze a fal a saját lövés után; ez a réteg azt teszi hozzá, hogy
  ROMLIK-E a meccs alatt. Ez a késői összeomlás leggyakoribb
  mechanizmusa, és a gólszámban NEM látszik: a csapat ugyanannyit lő a
  2. félidőben, csak minden lövése után egy másodperccel később ér
  haza — és az az egy másodperc pont egy kontra-lépés. Ellenfélként ez
  a hajrá kontra-terve (a kapusnak azonnal indítania kell); saját
  csapatra a teendő nem futóedzés, hanem a lövés PILLANATÁBAN kijelölt
  első visszafutó — fáradtan a fejben dől el, ki fordul meg.
  Felületek: /analyze, meccs-csomag, edzői összefoglaló, felderítés
  (edzői kulcs + 451. meccsterv-szabály), edzés-fókusz (471. szabály),
  kliens-csempe.

- **A jelentés megmondja, MELYIK szakaszt dolgozta fel** (motor +
  kliens): eddig csak a százalékot mondta ("a felvétel 60%-át"). Az a
  szám viszont nem árulja el, hogy az eleje vagy a vége maradt ki —
  pedig a felhasználó pont ezt akarja tudni, amikor azt látja, hogy
  "csak az első félidőt elemezte ki". A jelentés mostantól a
  forrásvideó órája szerint mondja meg a szakaszt (pl. "1:00–2:40 a
  10:00 hosszú videóból"), tehát a lejátszóban azonnal ellenőrizhető.
  A minőség-ablakban külön sorban is látszik.

- **Fal-mélység a hajrában** (új réteg, `line_height_fade`): a
  védekezési vonal magasságát eddig egy átlagszám írta le az egész
  meccsre. Ez a réteg azt teszi hozzá, hogy VÁLTOZIK-E: a felismert
  félidő mentén kettébontva méri, milyen messze áll a fal a saját
  gólvonaltól. Ha a 2. félidőre közelebb kerül, a fal visszahúzódott —
  a fáradó láb nem lép ki, a fal beszorul a 6-os köré. Edzőileg ez a
  legkonkrétabb hajrá-információ a támadónak: visszahúzódó fal ellen a
  meccs végére a külső lövőket kell helyzetbe hozni (kilépő védő
  nélkül a 9 méteres lövés zavartalan), feljebb jövő fal ellen viszont
  a kilépő MÖGÉ kell játszani. Más kérdés, mint a védekezés-fellazulás
  (`pressure_fade`): az a labdástól mért távolságot méri, ez a fal
  HELYÉT — egy fal fellazulhat úgy is, hogy a helye nem változik.
  Felületek: /analyze, meccs-csomag, edzői összefoglaló, felderítés
  (edzői kulcs + 450. meccsterv-szabály), edzés-fókusz (470. szabály),
  kliens-csempe.

- **A kézi meccs-időablak tényleg felülír mindent** (motor): a kézi
  ablak leírása azt ígérte, hogy "felülír minden felismerést" — de nem
  ez történt. A megadott szakasz beolvasása UTÁN az automatikus
  meccs-ablak-felismerés még lefutott, és lecsíphetett a megadott
  szakasz elejéből-végéből. Aki perc:másodpercre megmondta, hol a
  meccs, nem erre számít; ráadásul pont azok a felvételek hívják elő a
  kézi ablakot, ahol a felismerés amúgy is téved. Kézi ablaknál
  mostantól a felismerés le sem fut, és a mentés meccs-ablak mezői
  ismeretlenek maradnak: a jelentés nem állít semmit olyasmiről, amit
  meg sem vizsgáltunk.

- **A "Félidő (~35 p)" tényleg 35 perc** (motor + kliens): a
  hossz-beállítás korlátját a kliens KOCKÁBAN küldte el, és 25 fps-sel
  számolt — mert a videó valódi képrátáját ott nem ismeri. Egy 30
  fps-es telefonvideón ez azt jelentette, hogy a "Félidő (~35 p)"
  valójában 29 percet dolgozott fel, egy 50 fps-esen 17,5-et; a "Próba
  (~2 p)" ugyanígy rövidült. A felhasználó a feliratot hiszi el, nem a
  kockaszámot — és utána azt látja, hogy "csak az első félidőt elemezte
  ki". A korlát mostantól MÁSODPERCBEN megy a motornak, ami a videó
  valódi fps-ével váltja kockára; a régi, kockában számolt érték
  tartalékként megmarad arra az esetre, ha az fps nem olvasható ki.
  Ugyanez az indítás előtti idő-becslésre is áll: a "Próba (~2 p)"
  becslése két percre szól, nem a teljes videóra. Ha időablak ÉS
  hossz-korlát is meg van adva, a szigorúbb nyer.

- **A jelentés megmondja, kimaradt-e a bemelegítés** (motor + kliens):
  a motor eddig is levágta a felvétel nem-meccs széleit (bemelegítés,
  csapatbemutatás, lefújás utáni rész), de az eredményét SEHOL nem
  mondta meg — pedig ha a vágás nem sikerült, az álldogálást eladott
  labdának, a bemelegítő kapura lövést lövésnek látja. A felismerés
  eredménye mostantól a mentésbe kerül (talált-e összefüggő játékot,
  és mennyit vágott az elejéből/végéből), a minőség-jelentés pedig
  kimondja. Három eset, három üzenet: (1) nem találta meg a játék
  kezdetét → figyelmeztetés + ELSŐ TEENDŐ a kézi időablakra, (2)
  vágott → megmondja, mennyit (percben), (3) nem volt mit vágni → ezt
  is kimondja, mert ez ELLENŐRIZHETŐ állítás: aki tudja, hogy a
  videóban benne volt a bemelegítés, azonnal látja, hogy a felismerés
  tévedett — nem a kész elemzés furcsaságaiból kell rájönnie.
  A régi mentésekről (nincs adat) továbbra sem állítunk semmit.

## v0.1.55 — kiadva (2026-08-24)

> Kiadás-jegyzet: ebben a kiadásban nincs új elemzés — a
> VÁRAKOZÁS lett rövidebb. A detektálás utáni számolás (az
> ~500 réteg kiértékelése) feleannyi idő alatt fut le, mint
> eddig. Az ítéletek egy betűt sem változtak: az őr-jelentések
> (sorrend-függés, tükrözés, stride) szám szerint ugyanazok,
> mint a gyorsítás előtt.


- **A feldolgozás utáni számolás 40%-kal gyorsabb** (motor): a
  detektálás után a ~500 elemző réteg kiszámítása is percekbe telik egy
  teljes meccsen — ez a felhasználó szempontjából ugyanolyan várakozás,
  mint maga a feldolgozás. Profilozás négy szűk keresztmetszetet
  mutatott, mind ugyanabból a családból: olyan mérések, amelyek a
  TELJES felvételt végigjárják, és amelyeket egy összeállítás alatt
  tucatnyi réteg kér újra és újra (kapus-jelölés, megszakítás-,
  csere- és hetes-felismerés, kezdő hatos) — ezek mostantól
  hatókörönként egyszer futnak. Emellett a legforróbb úton (a
  birtoklás-mérés kockánként, összeállításonként milliószor) a
  függvényen belüli import is mérhető költség volt: kiemelve.
  A további körökben a passz-felismerés (168 hívás/összeállítás), a
  fáradás-mérés és a figura-hatékonyság (öt figura-réteg közös, drága
  bemenete) is a hatókörbe került.
  Mérve, 15 perces meccsen: edzői összefoglaló 27,2 → 13,0 mp (−52%),
  felderítés 22,9 → 12,3 mp (−46%). A teljes teszt-csomag 8:18 → 4:38.

## v0.1.54 — kiadva (2026-08-24)

> Kiadás-jegyzet: a jelentések mostantól MAGUK mondják meg,
> mennyire hihetők. Az edzői összefoglaló és a nyomtatható
> meccsjelentés is ELÖL visz egy figyelmeztetést, ha a
> feldolgozás gyenge volt — a pontszámmal, a kifejezetten
> bizonytalan réteg-családokkal és az első teendővel. Eddig ezt
> csak egy külön ablakban lehetett megtudni, illetve a nyomtatott
> lap legalján. Emellett az újrafeldolgozás gombja megmondja, mit
> visz és mit nem.

- **Az edzői összefoglaló megmondja, mennyire hihető** (motor +
  kliens): a jelentés minden mondata magabiztosan fogalmaz — így is
  kell írni egy edzői jelentést. De ha a feldolgozás gyenge volt (a
  nézőtér is a pályára került, kevés a labda-észlelés), akkor ezek a
  mondatok zajról szólnak, és eddig ezt csak egy külön ablakban lehetett
  megtudni, amit nem biztos, hogy bárki megnyit. Az összefoglaló
  mostantól 50/100 alatt (vagy ha van rangsorolt teendő) visz egy
  figyelmeztetést: a pontszámot, a kifejezetten bizonytalan
  réteg-családokat (labda- és pálya-alapú) és az első teendőt. A
  felületen a jelentés FÖLÖTT áll, más formában; a szöveges alakban is
  elöl. A szekciók szerkezete változatlan (külön mezőn megy), és üres
  meccsre továbbra sem mondunk semmit.
- **A nyomtatható meccsjelentés is elöl szól** (motor): a részletes
  "Elemzés megbízhatósága" szakasz eddig a lap ALJÁN volt — egy
  nyomtatott jelentést viszont fentről lefelé olvasnak: aki a végén
  tudja meg, hogy az adat gyenge, addig már döntött. Gyenge
  feldolgozásnál mostantól a tartalomjegyzék után, az első tartalmi
  szakasz ELŐTT áll egy rövid, kiemelt doboz a pontszámmal és az első
  teendővel. A részletes szakasz a helyén marad.

- **A "gyanúsan sok eladott labda" magyarázata frissült** (motor): a
  jelzés szövege még a JAVÍTÁS ELŐTTI működést írta le ("a
  birtokos-váltás egyetlen képkockából eldől, és kockánként átugrik a
  másik csapatra") — ez a kitartás-követelmény óta nem igaz. Az app nem
  mondhat valótlant a saját működéséről. Az új szöveg a két valódi okot
  nevezi meg, teendővel: vagy a labda-észlelés annyira szakadozott,
  hogy a kitartást is zaj elégíti ki ("Pontos" profil), vagy a
  feldolgozott szakasz nem is meccs (meccs-időablak).

- **Az újrafeldolgozás megmondja, mit visz és mit nem** (kliens): a
  gomb a KALIBRÁCIÓT frissíti, a többi beállítást — a meccs időablakát,
  a minőségi profilt és a hosszt — viszont az EREDETI indításból viszi.
  Ha a baj éppen az volt, hogy a bemelegítés bekerült az elemzésbe, ez
  a gomb nem oldja meg. A megerősítő párbeszéd ezt kimondja, és
  odaküld, ahol megadható (Új elemzés lap) — egy fél-egy órás munkát
  nem indítunk el ilyen félreértéssel.

- **Az eladott labda kitartás-szabálya: két javítás önellenőrzésből**
  (motor): (1) a futam hosszát egy kockával rövidebbnek számoltuk (a
  záró kocka kimaradt), tehát a szabály a szándékoltnál egy hajszállal
  szigorúbb volt; (2) a felvétel ELEJÉN álló, meg nem erősített
  villanásból labdaVESZTÉST írtunk valakinek a nevére — pedig a széleken
  álló rövid futam sosem igazolja magát (nincs mellette mindkét oldalon
  szomszéd). A végén állóra ez már eddig is így volt; most szimmetrikus.

## v0.1.53 — kiadva (2026-08-24)

> Kiadás-jegyzet: két javítás ugyanabból a hibaosztályból — a
> hátralévő idő becslése olyankor tévedett, amikor a döntésed
> (megvárod-e, vagy elmész a gép mellől) éppen rajta múlik. A
> becslés eddig a minőségi profiltól függetlenül és a TELJES
> videóval számolt; mostantól csak azonos profilú korábbi
> futásokból, és a megadott meccs-időablakra.

- **A hátralévő idő becslése PROFIL-FÜGGŐ lett** (motor + kliens) —
  JAVÍTÁS: a becslés eddig a gépen mért ütemet a minőségi profiltól
  függetlenül használta. Csakhogy a "Pontos" profil sűrűbben mintavesz
  és nagyobb képen keres, tehát UGYANARRA a videóra többszörös időt
  kér: aki profilt váltott, "kb. 20 percet" olvasott egy másfél órás
  munkára — pont akkor, amikor a döntése (megvárja-e) ezen múlik.
  Mostantól a feldolgozás-napló viszi a profilt, és a becslés csak az
  AZONOS beállítású korábbi futásokból számol. Ismeretlen profilnál
  inkább nincs becslés, mint egy másikból vett szám. Az Új elemzés
  lapon a profil váltása azonnal újraszámolja a becslést.
- **A becslés a MECCS-ABLAKRA szól, nem a teljes videóra** (motor +
  kliens): ugyanaz a hibaosztály — ha megadod, hogy a meccs a 4. perctől
  a 40.-ig tart, csak azt a 36 percet dolgozzuk fel, a becslés viszont a
  teljes felvétellel számolt. Mostantól a `/preflight` a szűkített
  szakaszra becsül (a fordított vagy a videón túlnyúló ablakot
  értelemszerűen kezelve), és a kártya ki is írja: "kb. 1 óra 10 perc
  lesz (a 95 percből 36 perc feldolgozásával)".

## v0.1.52 — kiadva (2026-08-24)

> Kiadás-jegyzet: ez a kör az első éles meccs utolsó nyitott
> tünetét zárja le. A rendszer a meccs ELŐTTI felállásnál is
> eladott labdákat írt — az ok az volt, hogy a birtokos-váltás
> egyetlen képkockából eldőlt, és tömörülésnél a jel kockánként
> ide-oda billegett. Mostantól az eladott labdához kitartás kell:
> az ellenfélnek tényleg nála kell lennie a labdának. A csapaton
> belüli passz változatlan.

- **Az eladott labda BILLEGÉSE megoldva** (motor) — JAVÍTÁS: a birtokos
  a labdához LEGKÖZELEBBI játékos, és a váltás eddig egyetlen
  képkockából eldőlt. Tömörülésnél (elzárás, beállós harc) és zajos
  labda-észlelésnél ez kockánként ide-oda billegett, és minden
  billenésből ELADOTT LABDA lett — az első éles meccsen ez a meccs
  ELŐTTI felállásnál is eladásokat gyártott, miközben senki nem
  játszott. Mostantól az eladott labdához KITARTÁS kell: az ellenfélnek
  legalább 0,3 másodpercig nála kell lennie a labdának. A csapaton
  belüli passzra ez NEM vonatkozik — az kisebb állítás (a labda nem
  hagyta el a csapatot), és a passz-alapú rétegek a régi viselkedésre
  épülnek.

  A kitartást a CSAPATRA mérjük, nem az egyes játékosra: ha az ellenfél
  megszerzi a labdát és rögtön tovább is passzolja a társának, az attól
  még valódi szerzés. A küszöb óvatos — a termék alap-ritkításával ez
  ~0,36 másodpercnyi valós idő, ennél gyorsabban valódi labdaszerzés
  sem stabilizálódik —, tehát igazi eladást nem veszítünk el. A
  felvétel legvégén álló, meg nem erősített váltásból sem lesz esemény.

## v0.1.51 — kiadva (2026-08-24)

> Kiadás-jegyzet: ez a kör arról szól, hogy MELYIK SZÁMOT hidd el.
> A jelentés mostantól külön szól a labda-alapú (birtoklás, passz,
> eladás, lövés) és a pálya-alapú (távolság, fal-forma, zónák)
> rétegekről, és kimondja, ha a labdaeladás-szám nem a játékról
> szól, hanem a billegő birtokos-váltásról. Az Új elemzés lapon
> pedig ott a három pont ÉLŐ állapottal, MIELŐTT az óra elindulna:
> kalibráció, detektálás-próba, meccs-időablak. A kiadás-lánc
> saját őre is élessé vált: ha a becsomagolt motor nem ír naplót,
> a kiadás elbukik.

- **"Gyanúsan sok eladott labda" — kimondva** (motor): a birtokos a
  labdához LEGKÖZELEBBI játékos, és a váltás egyetlen képkockából
  eldől. Tömörülésnél (és ritka labda-észlelésnél) ez ide-oda billeg, és
  minden billenésből eladott labda lesz — az éles meccsen ez a meccs
  ELŐTTI felállásnál is termelt eladásokat. A számot most nem javítjuk
  ki (az a birtoklás-felismerés dolga, és külön, validált lépést
  érdemel — lásd az útitervet), de a jelentés kimondja, ha az ütem nem
  a játékról szól: valódi meccsen fél-másfél eladás jut egy percre
  csapatonként, négy fölött a jelzés bejön, teendővel együtt.

- **Réteg-megbízhatóság: külön szó a labda- és a pálya-alapú
  számokról** (motor): az első éles meccsen a felhasználó ugyanolyan
  magabiztosan olvasta a birtoklás- és passz-számokat, mint a
  pozíció-alapúakat — pedig a labdát a kockák negyedén láttuk, és a
  pálya-vetítés is hibás volt. A megbízhatósági lista (amit a
  minőség-ablak amúgy is mutat) mostantól két új sort visz: a
  LABDA-alapú rétegeket (birtoklás, passz, eladás, lövés) 40%-os
  labda-lefedettség alatt megjelöli, a PÁLYA-alapúakat (távolság,
  fal-forma, zónák) pedig akkor, ha lehetetlen a létszám vagy nincs
  kalibráció — mindkettőnél megmondva, MIÉRT.

- **A diagnózis-lánc ellenőrzése ÉLES lett** (kiadás): a windowsos
  füstteszt eddig csak JELEZTE, hogy a becsomagolt motor ír-e
  `engine.log`-ot — mert a futtató tényleges viselkedését még nem
  erősítettük meg. A v0.1.50 naplója megerősítette ("engine.log
  MEGVAN; indulási mérföldkövek: True"), ezért az ellenőrzés innentől
  megbuktatja a kiadást, ha a napló eltűnik vagy üres marad. Pontosan
  ez a hiba küldte úgy útjára a korábbi kiadást, hogy a felhasználó
  üres naplót látott, és nem volt mit elküldenie.

- **A labda-figyelmeztetés mostantól TEENDŐT mond** (motor): a kevés
  labda-észlelésre eddig annyi volt a válasz, hogy "tisztább felvétel
  segít" — ami igaz, de a már meglévő felvételen nem lehet vele mit
  kezdeni. Széles, távoli felvételen a labda alig pár képpont, ezért a
  "Pontos" minőségi profil (nagyobb felbontáson keres) a leggyorsabb
  javulás ugyanazon a videón. Ez most a figyelmeztetésben és az "első
  teendő" rangsorban is szerepel.

- **Indítás előtti ellenőrző lista** (kliens): az első éles meccs úgy
  ment el, hogy a felhasználó mindhárom buktatóba belelépett egyszerre
  — rossz kalibrációval indult, a bemelegítés és a csapatbemutatás
  bekerült az elemzésbe, és mindez csak egy óra múlva derült ki. Az Új
  elemzés lapon mostantól ott a három pont ÉLŐ állapottal, közvetlenül
  az indítás gomb fölött: bejelölted-e a pályát, lefuttattad-e a
  detektálás-próbát (és mit mutatott: hány ember esik a pályára), és
  megadtad-e a meccs időablakát. Nem tilt semmit — aki tudja, mit
  csinál, sárga pipákkal is indíthat.

## v0.1.50 — kiadva (2026-08-24)

> Kiadás-jegyzet: ez a kör bezárja a hurkot az első éles meccs
> tanulságai körül. A minőség-jelentés eddig felsorolt négy-hat
> figyelmeztetést; most kiemel EGY teendőt, amivel kezdeni kell —
> és rögtön mellette ott a gomb, amivel a javított kalibrációval
> újrafuttatható ugyanaz a meccs (eddig az újrafeldolgozás a régi,
> rossz kalibrációt vitte volna). Emellett egy tényleges
> felismerés-javítás: egy lövésből nem lesz négy esemény.

- **Lövés-csendidő: egy lövésből ne legyen négy** (motor) — JAVÍTÁS: az
  éles meccsen az eseménylistában négy „lövés" állt 1264,6 – 1267,1 mp
  között, vagyis EGY lövésből négy esemény lett. A hely-alapú
  ismétlés-szűrő (a labdának ki kell lépnie a kapu-zónából) zajos
  labda-észlelésnél nem elég: a labda ki-be billeg a zóna szélén.
  Mostantól ugyanarra a kapura fél másodpercen belül nem indul újabb
  esemény, és a csendidő minden elnyomott jelöltnél újraindul (a
  zaj-sorozat így egy eseménnyé olvad). A küszöb szándékosan óvatos:
  ennél gyorsabban két KÜLÖN lövés fizikailag sem hihető, tehát valódi
  eseményt nem dobunk el. A ritkább, 1–1,5 másodperces ismétléseket ez
  nem szűri — azok oka a hibás pálya-vetítés, és a kalibráció
  rendbetétele oldja meg.

- **Újrafeldolgozás a JAVÍTOTT kalibrációval** (motor + kliens): az
  újrafeldolgozás leggyakoribb oka éppen az, hogy a kalibráció rossz
  volt — a felhasználó ilyenkor újrakalibrál a varázslóban (az a
  videóhoz mentődik), és újraindítja a feldolgozást. Eddig viszont az
  újrafeldolgozás a JOB régi beállításait vitte, tehát pontosan ugyanazt
  a rossz eredményt adta volna még egyszer, egy újabb óra árán.
  Mostantól a videóhoz mentett (frissen javított) kalibráció élvez
  elsőbbséget, és a feldolgozás a legkorábbi kalibrált kockától indul.
  A gomb is a helyére került: eddig CSAK a hibára futott munkákon
  látszott a kezdőlapon — most ott van a meccs minőség-jelentésében is,
  ahol a baj kiderül.

- **"Első teendő" a minőség-jelentésben** (motor + kliens): egy gyenge
  feldolgozás négy-hat figyelmeztetést kap egyszerre, és a felhasználó
  nem tudja, mivel kezdje — pedig a lista eleje és a vége nem
  egyenrangú: a rossz kalibrációt kijavítva a jelzések fele magától
  eltűnik, míg a mezszám-hozzárendelés a rossz alapokon semmit nem ér.
  A jelentés mostantól rangsorol, és kiemel EGY mondatnyi teendőt,
  amivel kezdeni kell. Őr-teszt vigyáz rá, hogy minden figyelmeztetéshez
  tartozzon teendő.

## v0.1.49 — kiadva (2026-08-24)

> Kiadás-jegyzet: ez a kör a KALIBRÁCIÓRÓL szól — az első éles
> meccs tanulsága az volt, hogy a rosszul bejelölt pálya minden
> további számot elvisz. Mostantól a kalibráló képernyőn egy
> gombbal betölthető a sarok-javaslat a felismert pályavonalakból,
> az indítás rákérdez, ha nincs kalibráció, a futó feldolgozás
> pedig már pár perc után szól, ha az eredmény használhatatlan
> lesz — így nem megy el rá egy óra. A kész meccs jelentése
> kimondja, ha kalibráció nélkül futott.

- **Korai riasztás a futó feldolgozáson** (motor + kliens): egy meccs
  feldolgozása fél-egy óra, és eddig CSAK a végén derült ki, ha az
  egész használhatatlan lett (a nézőtér is a pályán, hiányzó
  kalibráció). Pedig a motor amúgy is ment részeredményt pár
  percenként — mostantól ugyanabból kiolvassa azt a két jelet, ami már
  a legelején eldönti a sorsát, és ráteszi a munkára. A Feldolgozások
  lapon és a kezdőlapon is látszik, tehát három perc után meg lehet
  szakítani, ahelyett hogy egy óra menne el rá. A riasztás hibája nem
  érintheti a részeredmény mentését: az fut le előbb.
- **Kalibráció nélkül rákérdez az indítás** (kliens): nem tiltás — van,
  amikor egy hozzávetőleges kép is ér valamit —, de a fél-egy órás
  munka nem indulhat el némán úgy, hogy a végén a nézőtér is a pályán
  lesz. A párbeszéd elmondja, mit veszít a felhasználó, és felkínálja
  mindkét utat.

- **"Kalibráció nélkül futott" — kimondva** (motor + kliens): eddig
  semmi nem jelezte, ha egy feldolgozás pálya-kalibráció NÉLKÜL futott.
  Pedig ilyenkor a koordináta csak arányos becslés (a kép széle a pálya
  széle), és a pályán kívüli embereket — kispad, edző, NÉZŐTÉR — nem
  lehet kiszűrni: mindenki „a pályára" kerül, tehát a távolság-,
  fal-forma- és birtoklás-alapú elemzések megbízhatatlanok. A meccs
  mostantól viszi ezt a tényt, a minőség-jelentés kimondja a teendővel
  együtt, és a kliens is mutatja. A RÉGI mentésekről (ahol nincs adat)
  szándékosan nem állítunk semmit.

- **Sarok-javaslat a kalibráló képernyőn** (kliens): a motor RÉGÓTA
  adott négyszög-javaslatot a felismert pályavonalakból
  (`/broadcast/lines` → `suggested_quad`), de a felület csak említette
  ("van javaslat") — használni nem lehetett. Mostantól egy gomb
  betölti a 4 sarkot, és a szöveg kimondja, hogy ELLENŐRIZNI kell:
  a javaslat segítség, nem garancia. Ez a legfontosabb kényelmi lépés
  a legdrágább hiba ellen — a rosszul jelölt sarok az egész elemzést
  elviszi (a lelátó a pályára vetül, a pozíciók félremennek).

## v0.1.48 — kiadva (2026-08-24)

> Kiadás-jegyzet: ez a kör az ELSŐ éles meccs tanulságairól szól. A
> legfontosabb egy javítás: a minőség-jelentés eddig a TÖBBLET
> észlelést jutalmazta, ezért egy olyan feldolgozás, amiben a lelátó is
> a pályára került (27 "játékos" kockánként), 70/100-at kapott. Most a
> többlet ugyanúgy ront, mint a hiány, a lehetetlen létszám plafont ad,
> és a detektálás-próba már az INDÍTÁS ELŐTT kimondja, ha a kalibráció
> a nézőteret is a játéktérre vetíti. A bemelegítés és a
> csapatbemutatás ellen kézi meccs-időablak jött (perc:másodperc), a
> "csak az első félidőt elemezte ki" élményre pedig lefedettség-jelzés.
> Emellett: hátralévő idő a feldolgozásoknál, "kész" bejelentés
> bárhonnan, indítás előtti hely-ellenőrzés, és új elemző réteg
> (támadás-ritmus).

- **Minőség-jelentés: a TÖBBLET is hiba** (motor + kliens) — JAVÍTÁS:
  egy éles meccsen a rendszer 27,4 játékost mért kockánként (a pályán
  14 lehet: a nézőteret és a kispadot is játékosnak mérte), a jelentés
  mégis 70/100-at mutatott. A képlet a játékos-lefedettséget 1.0-ra
  vágta, tehát a hibás feldolgozást TÖKÉLETESNEK látta. Innentől a 14
  fölötti rész ugyanolyan meredeken ront, ahogy a hiány, a lehetetlen
  létszám pedig PLAFONT ad az összpontszámra (jó labda-lefedettséggel
  se lehet "közepes" egy olyan feldolgozás, amiben a lelátó is a
  pályán van). Külön figyelmeztetés is jár hozzá, a leggyakoribb okkal
  és a teendővel: a 4 sarokpont a JÁTÉKTÉR sarkait jelölje, fél pálya
  esetén a fél-pálya kalibrációt kell választani, és a rajzolt 6/9
  m-es vonalnak rá kell ülnie a valódira.
- **Kézi meccs-időablak** (motor + kliens): a feltöltött felvételben
  rendszerint benne van a bemelegítés és a csapatbemutatás — ezekből a
  felismerő lövést és eladott labdát csinál. Az automatikus meccs-ablak
  eddig is vágott, de rossz kalibrációnál becsapható (ha a lelátó is a
  pályára vetül, a bemelegítés is "játéknak" látszik). Mostantól az Új
  elemzés lapon megadható perc:másodperc alakban, hol kezdődik és hol
  ér véget a MECCS; ez felülír minden felismerést, bekerül a mentett
  paraméterekbe (tehát a Folytatás is ezt viszi), és a köteg többi
  videójára is érvényes.
- **"A felvétel mekkora részét dolgoztuk fel"** (motor + kliens): a
  meccs mostantól viszi a FORRÁSVIDEÓ hosszát, és a minőség-jelentés
  kimondja, ha a feldolgozott szakasz a felvétel 60%-a alatt maradt.
  Enélkül a "csak az első félidőt elemezte ki" élmény
  megmagyarázhatatlan: nem derül ki, hogy megvágott feltöltésről, a
  hossz-beállításról vagy megszakadt feldolgozásról van-e szó.

- **Új elemző réteg: támadás-ritmus** (`attack_tempo_variety`): a
  támadó-szakaszok HOSSZÁT három sávba soroljuk (12 mp alatt gyors, 30
  mp fölött hosszú). Nem az a kérdés, melyik a jobb, hanem hogy
  egyfélék-e: aki egy tempóban játszik, kiszámítható. Edzőileg ez a
  felkészülés ritmusa — gyors befejezőknél a visszarendeződés a
  meccsterv első pontja, hosszan járatóknál türelmes, hibátlan fal kell
  (a passzív jel a védőnek dolgozik), váltogatóknál pedig a JELZÉSEKRE
  kell edzeni a felismerést. Felületek: /analyze, meccs-csomag, edzői
  összefoglaló, felderítés (kulcs + 449. meccsterv-szabály), edzés-fókusz
  (469. szabály), kliens-csempe.

- **Indítás előtti ellenőrzés: hely és várható idő** (motor + kliens):
  egy meccs feldolgozása fél-egy óra. A legrosszabb vég az, amikor ez
  az óra elmegy, és UTÁNA derül ki, hogy nem volt hova írni az
  eredményt. Mostantól a motor az indításkor megnézi a szabad helyet,
  és kevésnél el sem indítja a munkát — magyar indoklással, számokkal
  (mennyi van, mennyi kellene). A második kérdés a "meddig tart": az
  új `POST /preflight` a videó hosszából és a gépen KORÁBBAN mért
  ütemből ad becslést, tehát nem laborszám, hanem az adott gép saját
  tempója. Az első pár feldolgozásnál nincs becslés — inkább semmi,
  mint egy téves szám. Az Új elemzés lapon mindkettő ott van az
  indítás gomb mellett.

- **"Kész!" — a feldolgozás vége megtalál bárhol** (kliens): a
  Feldolgozások menüpont után maradt egy rés: ha a felhasználó közben
  máshol dolgozik az appban, a munka befejezéséről CSAK úgy értesült,
  ha visszament megnézni — a menü-jelvény eltűnése néma. Mostantól a
  burokban (tehát minden képernyőn) megjelenik egy sáv: kész a
  feldolgozás, itt a meccs, egy kattintás a megnyitás; hiba esetén a
  motor magyar indoklása és a részletek gomb. A megszakított munkát
  szándékosan NEM jelenti be — azt a felhasználó maga állította le. Az
  app indulása utáni első kör is néma: a tegnapi kész elemzést ma
  reggel bejelenteni értelmetlen lenne.

- **Hátralévő idő a feldolgozásnál** (motor + kliens): percekig futó
  munkánál ez volt a leghiányzóbb adat — a százalék önmagában nem
  mondja meg, hogy megvárd-e, vagy elmenj a gép mellől. A motor
  mostantól minden futó munkához ad becslést (`eta_s`): a TÉNYLEGES
  munkaidő és a haladás arányából, tehát a sorban töltött idő nem
  számít bele (különben a második munka becslése reménytelenül
  túllőne). Az első öt százalékban nincs becslés: ott a modell-betöltés
  és a videó-megnyitás torzít, és egy vadul téves "kb. 3 óra" rosszabb,
  mint a semmi. A felület emberi mondatként mutatja ("kb. 12 perc van
  hátra") a Feldolgozások lapon és a kezdőlapon is.
- **Windowsos telepítő: a diagnózis-lánc jelentése a napló végén**
  (kiadás): a füstteszt eddig is megnézte, hogy a becsomagolt motor
  hibája végigfut-e a diagnózis-láncon, de a válasza a hosszú napló
  közepén veszett el. Mostantól a windowsos munka UTOLSÓ lépése újra
  kiírja a verdiktet, tehát a napló rövid végéből is látszik.

## v0.1.47 — kiadva (2026-08-23)

> Kiadás-jegyzet: ebben a körben a hosszú feldolgozás körüli élet lett
> rendben. Új **Feldolgozások** menüpont: a menüben élő szám mutatja,
> hány elemzés fut, tehát nyugodtan átmehetsz máshova az appban, és egy
> kattintással visszatalálsz — a részleges eredmény menet közben is
> megnyitható. A motor emellett **ébren tartja a gépet** a munka
> idejére, hogy a tétlenségi alvás ne állítsa meg a számítást (a
> lehajtott MacBook-tető külső kijelző nélkül továbbra is alvás — ezt
> alkalmazásból nem lehet felülbírálni, és a felület ezt ki is mondja).
> Két régi, néma hiba is javult: az ÉKEZETES útvonalon lévő videó
> Windowson nem nyílt meg (magyar felhasználónál mindennapi eset), és a
> motor pontos magyar hibaüzenetei sosem jutottak el a képernyőig — 72
> hívóhely csak "HTTP 400"-at mutatott. Új elemző réteg:
> eladás-kényszer (kipréselik belőlük, vagy maguktól szórják el).

- **Feldolgozások: külön menüpont, élő jelvénnyel** (kliens): egy meccs
  feldolgozása percekig fut, de a haladás eddig CSAK a kezdőlapon
  látszott, és csak amíg a felhasználó ott állt. Aki közben átment a
  felderítésre vagy a figura-tervezőbe, elvesztette szem elől, és nem
  volt hová visszamennie. Mostantól saját menüpont van rá, a menüben
  ÉLŐ szám mutatja, hány elemzés dolgozik (bárhonnan látszik), a lapon
  pedig ott a szakasz, a százalék, a megszakítás, az "ami eddig kész"
  gomb (a részleges eredmény menet közben is megnyitható), és alatta a
  LEZÁRT feldolgozások naplója a hibaüzenetekkel. A kérdezgetést egy
  KÖZÖS figyelő végzi, tehát a kezdőlap és az új lap együtt sem
  terheli jobban a motort, mint eddig a kezdőlap egyedül. Őr-teszt
  védi.

- **A gép nem alszik el feldolgozás közben** (motor): a feldolgozás
  percekig-órákig tart, és közben a felhasználó nem a képernyőt nézi —
  elmegy, lehajtja a laptop tetejét. A rendszer ilyenkor tétlenségi
  alvásra vált, és a számítás megáll vagy lelassul. Mostantól a motor a
  MUNKA IDEJÉRE alvás-gátló zárat fog (macOS: caffeinate a saját
  folyamatunkhoz kötve; Windows: SetThreadExecutionState), és a végén —
  kész, hiba és megszakítás után is — MINDIG elengedi, hogy a gép ne
  maradjon ébren fölöslegesen. A Feldolgozások lap ki is írja, hogy a
  gép ébren marad. Őszintén a határról: MacBookon a LEHAJTOTT tető
  külső kijelző nélkül a macOS-t akkor is elaltatja — ezt alkalmazásból
  nem lehet felülbírálni; a zár a képernyő-elalvás utáni tétlenségi
  alvást és a lemez-alvást oldja meg. Három teszt védi, köztük az,
  hogy a zár hibája sosem akadályozhatja a feldolgozást.

- **Ékezetes útvonalon is megnyílik a videó** (motor, javítás): az
  OpenCV Windowson a rendszer kódlapján át nyitja a fájlt, ezért az
  ÉKEZETES útvonalon (magyar felhasználónál a mindennapi eset:
  `C:\Users\Dávid\Videók\meccs.mp4`) egyszerűen nem nyílt meg — és
  NEM is dobott hibát, csak "nem sikerült képkockát olvasni" lett
  belőle. A kódbázisban kilenc helyen nyitottunk videót, egyik sem
  nézte meg, sikerült-e. Mostantól egy közös megnyitó (`video_io.py`)
  csinálja: ha az ékezet miatt bukna, MÁSODIK próbálkozás a Windows
  rövid (8.3-as, csak ASCII) útvonalával, és ha úgy sem megy, EMBERI
  mondat jön a teendővel ("tedd a fájlt ékezet nélküli mappába"),
  megkülönböztetve a hiányzó fájltól és az ismeretlen kodektől. Öt
  teszt védi.

- **A szerver magyarázata eljut a felhasználóig** (kliens, javítás): a
  motor sok hibára pontos, magyar mondatot ad — például hogy az
  útvonalban ékezet van, és mit tegyen ellene. A kliensben ez
  ELVESZETT: 72 hívóhely csak "HTTP 400"-at dobott, tehát a legjobb
  magyarázatunk sosem jutott el odáig, ahol elolvassák. Mostantól
  minden hívás a szerver `detail` mezőjét mutatja, ha van; a
  státuszkód csak akkor marad, ha nincs jobb. Őr-teszt védi, hogy ne
  csússzon vissza.

- **Eladás-kényszer** (új réteg): az eladás-rétegek eddig azt mondták
  meg, KI veszíti el a labdát, HOL, MIKOR és mennyibe kerül — azt nem,
  hogy KI TEHET RÓLA. Pedig a kétféle eladás két különböző teendő: ha
  az ellenfél VESZI el (védő volt a labdás emberen), az a fal érdeme;
  ha üres térben szórják el, az a saját technikájuk hibája. Az új réteg
  minden eladás pillanatában megméri, milyen messze volt a legközelebbi
  ellenfél (2,5 m-en belül = kényszerített). Edzői olvasat: ha az
  ellenfél eladásai MAGUKTÓL jönnek, a letámadás keveset ad hozzá, a
  kockázata viszont megvan — maradjatok zárt falban. Ha kipréseltek, a
  prés működik: a kettőzést tartani kell. Saját oldalon a magától jött
  eladás edzés-téma, nem taktika. Felületek: /analyze, meccs-csomag,
  edzői összefoglaló, felderítő kulcs (mindkét irányra) + meccsterv
  (448.), edzés-fókusz (468.), kliens-csempe, 3 teszt.

- **Az indító képernyő mutatja, mennyi ideje vár** (kliens): az ELSŐ
  indítás percekig is tarthat (a víruskereső egyszer végigolvassa a
  programot), és eddig ilyenkor csak egy néma pörgettyű forgott. A
  felhasználó ebből azt hiszi, lefagyott, és bezárja a programot —
  pont azt a folyamatot lőve ki, amelyik mindjárt kész lenne.
  Mostantól három másodperc után látszik az eltelt idő (a bizonyíték,
  hogy megy), fél perc után pedig egy mondat is: az első indítás
  lassú, ne zárja be, a következő már gyors lesz. A számláló minden
  indítási kísérletnél nulláról indul, és a kísérlet végén megáll.

## v0.1.46 — kiadva (2026-08-23)

> Kiadás-jegyzet: ha eddig azt láttad, hogy "nem érem el a
> háttérmotort", és a napló semmit nem árult el — ez a kiadás pont
> ezért készült. Kiderült, hogy a motor üzenetei Windowson EGY MÁSIK
> FÁJLBA mentek (a becsomagolt motor ablak nélkül fut, ilyenkor a
> Pythonnak nincs kimenete), és a program ezt a fájlt meg sem nézte:
> a hiba-képernyőn ezért csak az állt, hogy "elindítottam" és
> "leállt". Mostantól mindkét naplót mutatja. A motor emellett
> elmondja, MEDDIG jutott az indulásban (a nehéz részek betöltése
> előtt is naplóz), a végzetes hibát tartós fájlba menti, és akkor
> sem hal meg némán, ha az adatmappa nem írható. A "Diagnosztika
> másolása" gomb mindezt egy kattintással a vágólapra teszi.

- **A nem írható adatmappa sem öl némán** (motor, javítás): a
  napló-átirányítás MAGA is elhasalhat, ha az adatmappa nem írható
  (vállalati gép, OneDrive-ra terelt AppData) — és eddig ez a
  hibakezelésen KÍVÜL futott, tehát a motor nyom nélkül halt meg: a
  hibajelentő maga sem futott le. Mostantól a hibakezelésen belül van,
  és a hibajelentő stdout nélkül is fájlba ír. Három őr-teszt védi (az
  egyik ténylegesen elveszi a stdout-ot, és ellenőrzi, hogy a napló
  így is elkészül).

- **Windowson végre látszik, mit mond a motor** (kliens, javítás): a
  becsomagolt motor ABLAK NÉLKÜLI programként fut, és Windowson
  ilyenkor a Pythonnak nincs stdout/stderr-je — vagyis a kliens
  csövébe SEMMI nem érkezik. A motor a saját üzeneteit ezért egy KÜLÖN
  fájlba írja (`engine.log`), az indító naplója (`engine-app.log`)
  mellé. A kliens viszont eddig csak a sajátját olvasta: a
  hiba-képernyőn ott állt, hogy "elindítottam" és "leállt", de a
  MIÉRT — ami a másik fájlban volt — soha nem látszott. Ez a
  legvalószínűbb oka annak, hogy a hibajelentések üresnek tűntek.
  Mostantól a napló-kivonat MINDKÉT fájlt összefűzi, külön
  fejlécekkel. Őr-teszt védi.

- **A motor elmondja, MEDDIG jutott az indulásban** (motor): a nehéz
  részek betöltése (torch, OpenCV) másodpercekig — becsomagolt
  kiadásban, víruskereső-átvizsgálással percekig — tart, és eddig az
  ELSŐ naplósor is csak utánuk jött. Ha a motor közben halt el
  (hiányzó rendszerkönyvtár, OpenMP-ütközés), a felhasználó ÜRES
  naplót látott, és nem lehetett megmondani, hol akadt el. Mostantól
  mérföldkövek jelzik az utat: "az indító elindult", "webszerver
  betöltése", "elemző motor betöltése", "a motor betöltve".

- **A végzetes indulási hiba nem vész el** (motor): a `main()`
  mostantól elkapja a halálos kivételt, kiírja a LÉNYEGET egyetlen
  sorban (típus + üzenet), és a teljes nyomkövetést tartós fájlba is
  menti (`engine-crash.log` a felhasználói adatmappában). Eddig a
  folyamat némán meghalt, és ha a kliens csöve közben eltört, a
  hibaüzenet nyomtalanul elveszett. A "Diagnosztika másolása" gomb
  ezt a fájlt is beolvassa. Két őr-teszt védi.

## v0.1.45 — kiadva (2026-08-23)

> Kiadás-jegyzet: ez a kiadás arról szól, MIÉRT nem indul el a motor —
> és a legvalószínűbb okot meg is javítja. A becsomagolt motor ~244 MB,
> és a víruskereső az ELSŐ futásnál végigolvassa; a kliens viszont 90
> másodperc után nemcsak feladta, hanem LE IS ÁLLÍTOTTA a folyamatot —
> vagyis pont azt lőtte ki, amelyik talán másodpercekre volt attól,
> hogy válaszoljon. Újrapróbálásnál az átvizsgálás elölről kezdődött: a
> hiba fenntartotta önmagát. Mostantól 180 másodperc a türelem, és a
> még ÉLŐ motrot futni hagyjuk. Mellé egy "Diagnosztika másolása"
> gomb került mindhárom elakadási pontra: egy kattintás, és a
> vágólapon ott van minden tény (hol kerestük a motort, írható-e az
> adatmappa, válaszol-e bármelyik port, a napló vége). A motor naplója
> ráadásul eddig összetörte a magyar ékezeteket — az is javítva.

- **Az időtúllépés többé nem öli meg az induló motrot** (kliens,
  KRITIKUS javítás): a becsomagolt motor negyedmilliárd bájt, és a
  víruskereső az ELSŐ futásnál végigolvassa, mielőtt a program
  egyáltalán elindulna — lassú lemezen ez simán túlmegy két percen. A
  kliens 90 másodperc után feladta, és — ez volt a baj — le is ÁLLÍTOTTA
  a folyamatot. Vagyis pont azt lőttük ki, amelyik talán másodpercekre
  volt attól, hogy válaszoljon; a felhasználó újrapróbált, és az egész
  átvizsgálás elölről kezdődött. A hiba önmagát tartotta életben.
  Mostantól a várakozás 180 másodperc, és ha a folyamat még ÉL, futni
  hagyjuk: az Újrapróbálom a port-tartomány végigfésülésével megtalálja,
  amint válaszol. A képernyő ezt ki is mondja ("ne zárd be a
  programot"). A leállítás a `_stoppedByUs` jelzőn át az őrkutyát is
  kikapcsolta — az is megszűnt. Őr-teszt védi.

- **"Diagnosztika másolása" gomb a motor-hibáknál** (kliens): a
  naplófájl önmagában kevés. Ha a motor-program meg sem található,
  vagy az adatmappa nem írható, akkor NAPLÓ SINCS — a felhasználó
  pedig csak annyit tud mondani, hogy "nem megy". Az új gomb egy
  kattintással a vágólapra teszi a hiányzó feltételeket is: app- és
  rendszer-verzió, hol kerestük a motor-programot (ha nincs meg,
  MINDEN keresett útvonalat felsorolva) és mekkora, írható-e az
  adatmappa, válaszol-e bármelyik port a 8000–8010 tartományban, és a
  napló utolsó 40 sora. Ott van mind a három elakadási ponton: az
  indító képernyőn, a motor-hiba képernyőn és a nyitóképernyő
  offline-értesítésén. Őr-teszt védi.

- **A motor naplója már olvasható magyarul** (kliens, javítás): a
  motor kimenetét a kliens bájtonként dekódolta
  (`String.fromCharCodes`), ami az ékezeteket összetörte ("Ã¡"
  az "á" helyett) — pont azt a naplót, amit hibakereséshez kérünk. A
  dekódolás mostantól UTF-8 (sérült darabhatárt is tűrve). Őr-teszt
  védi.

- **Nem szivárog a napló-fájlleíró** (kliens, javítás): az őrkutyás
  újraindítás új napló-sinket nyitott a régi lezárása nélkül.
  Windowson a még fogott fájl csonkoló megnyitása el is bukhat — azaz
  pont az újraindításnál veszett volna el a napló. Emellett a sikeres
  indulás mostantól nullázza az őrkutya újraindítás-kvótáját: a korlát
  a beindulni SEM tudó motor pörgetése ellen véd, nem az ellen, hogy
  egy hosszú munkamenetben többször kelljen újraéleszteni.

## v0.1.44 — kiadva (2026-08-23)

> Kiadás-jegyzet: ez a kiadás egyetlen dolog miatt fontos — feloldja
> azt a ZÁRT KÖRT, ami a régi verzión ragadt felhasználókat kizárta a
> javításokból. Ha a motor nem indult el, a program a motor-hiba
> képernyőn állt meg, és onnan nem vezetett út a frissítőhöz; a
> frissítéshez viszont se fiók, se motor nem kell. Mostantól a
> "Frissítés keresése" gomb ott van mindhárom elakadási ponton.
> (Aki még a régi, hibás verziót futtatja, annak EGYSZER kézzel kell
> letöltenie a telepítőt a Releases oldalról — utána a program már
> magától tud frissülni. A fiókokat és a meccseket ez nem érinti: azok
> külön adatmappában élnek.)
> Mellette: sima lejátszás gyengébb gépen (a mozgó felületekről eltűnt
> az elmosás), mozgás-csökkentés támogatása, beszélő jelmagyarázatok,
> és látszik, hogy a pálya nagyítható.

- **A frissítő motor nélkül is elérhető — a zárt kör feloldása**
  (kliens, KRITIKUS): a legsúlyosabb hibánk volt, és pont azokat
  zárta ki, akik régi verzión ragadtak. A lánc: régi verzió → a motor
  el sem indul → a fiók-kapu a MOTOR-HIBA képernyőn áll meg → onnan
  NEM vezetett út a frissítőhöz (az a fiók-képernyőn ült, ami motor
  nélkül el sem érhető) → a felhasználó soha nem jut olyan verzióra,
  amelyikben a hiba javítva van. Csak kézi újratelepítéssel lehetett
  kiszabadulni. A frissítéshez viszont SE FIÓK, SE MOTOR nem kell (a
  kiadásokat a GitHub adja), ezért a folyamat közös helyre került
  (`update_flow.dart`), és mostantól ott a "Frissítés keresése" gomb
  MINDHÁROM elakadási ponton: az indító képernyőn (ha a motor el sem
  indult), a motor-hiba képernyőn és a belépőn. A motor-hiba
  képernyő szövege ki is mondja, hogy ez a gomb motor nélkül is
  működik. Őr-teszt védi mind a hármat.

- **Látszik, hogy a pálya nagyítható** (kliens): a felülnézeti pálya, az
  élő nézet és a videó-panel régóta nagyítható (touchpad-csippentés,
  Ctrl+görgő, dupla kattintás = vissza) — de ez SEHOL nem volt
  kiírva, csak a forráskód kommentjében. Egy pályarajzon senki nem
  próbál csippenteni magától. Mostantól a nézet sarkában halvány
  jelzés áll: alaphelyzetben azt mondja, hogyan lehet nagyítani,
  nagyítva pedig a szorzót és a visszaállás módját ("×2,3 · dupla
  kattintás: vissza"). Mind a négy nagyítható felület egyszerre
  kapta meg, mert a jelzés magában a nagyítható nézetben ül. A
  "hogyan nagyíts" súgó CSAK rámutatásra jelenik meg — állandóan
  kiírva zaj lenne, főleg a videó fölött —, a nagyítás-szorzó
  viszont mindig látszik: az állapot, nem tipp.

- **A passzháló is megmondja, mit jelentenek a jelei** (kliens): a
  hőtérkép és a lövéstérkép már kimondja, mit kódol méretbe és színbe
  — a passzháló volt az utolsó térkép-réteg magyarázat nélkül.
  Mostantól a csipeten ott áll, hogy a korong mérete a
  passz-részvétel, a vonal vastagsága pedig a két ember közti passzok
  száma. (A rajzolóban maradó egyetlen elmosás mellé komment került
  arról, miért megengedett: a passzháló nem rajzolódik újra
  képkockánként, és csapatonként egyetlen ilyen ragyogás van.)

- **Az indító képernyő is megmutatja a motor naplóját** (kliens): a
  motor indulási hibája ELŐSZÖR itt jelenik meg — a fiók-kapu és a
  nyitóképernyő már eddig is kiírta a napló végét, ez a képernyő
  viszont egyetlen mondattal elintézte, és a felhasználónak nem volt
  mit elküldenie. Sikertelen indításnál mostantól itt is ott a napló
  utolsó sorai, kijelölhető szöveggel, az "Újrapróbálom" gomb fölött.

- **Az animációk tiszteletben tartják a csökkentett mozgást** (kliens,
  hozzáférhetőség): az app az elmúlt körökben tele lett úszó, pörgő és
  növekvő elemekkel. Akinél a rendszerben be van kapcsolva a
  mozgás-csökkentés (macOS: Kisegítő lehetőségek → Kijelző → Mozgás
  csökkentése; Windows: Animációk kikapcsolása), annál ez nem
  díszítés, hanem rosszullét. Mostantól a közös animációs elemek
  (belépő úszás, szám-felpörgetés, hover-emelés, mérő-sáv) és a
  grafikonok berajzolása is lekérdezi a beállítást, és mozgás nélkül,
  AZONNAL a végállapotot mutatja — a tartalom ugyanaz marad. A
  FOLYAMATOS mozgások is megállnak (a feldolgozás-lista forgó
  lépés-ikonja és a várakozó nézet lélegző ragyogása): a sosem
  álló mozgás a legzavaróbb fajta, és a haladást a kiemelt sáv, a
  "folyamatban…" felirat meg az élő másodperc-számláló úgyis
  elmondja. Őr-teszt védi.

- **A két grafikon is elmosás nélkül ragyog** (kliens, teljesítmény):
  az eredmény-alakulás és a lövéstérkép betöltéskor BERAJZOLÓDIK, és
  az animáció alatt képkockánként újrarajzolódnak — gólonként egy-egy
  elmosott ragyogással. Gólgazdag meccsen ez képkockánként több tucat
  külön rajz-menet. Mindkettő átállt a sugaras színátmenetre (a pálya
  és a sztori-sáv mintájára); az őr-teszt mostantól mind a négy
  képkockánként újrarajzolt felületet védi.

## v0.1.43 — kiadva (2026-08-23)

> Kiadás-jegyzet: ez a kör a GRAFIKÁKRÓL és a sima futásról szól. A
> lejátszás alatt másodpercenként 25-ször újrarajzolt felületekről
> (pálya, meccs-sztori sáv) eltűnt az elmosás — gyengébb gépen ettől
> akadozott volna a kép —, a labdás ember pedig visszakapta a
> csapatszínét: a korong marad kék vagy piros, csak a holdudvara
> arany. A hőtérkép mostantól megmondja, mit jelent a szín; a
> felderítés keresője kiemeli, HOL talált a 467 mutató közt; a
> döntés-panel kimondja, mihez képest "optimális" egy passz; az első
> lépések kártya pedig sorozatnak látszik, nem négy külön tippnek.
> Új elemző réteg: figura-indító — melyik posztról indul a figurájuk,
> mert azt a fal már az ELSŐ passznál olvashatja.

- **Figura-indító** (új réteg): a figura-befejező réteg megmondja, KIRE
  FUT KI a figurájuk — ez azt, HONNAN INDUL. A kettő nem ugyanaz a
  védekező szempontjából: a befejezőt a fal a lövés előtt egy-két
  másodperccel ismeri fel, az indítót viszont AZONNAL, az első
  passznál. A réteg minden figura-klaszterben megnézi, kinél volt a
  labda a támadás első mért pillanatában, és a poszthoz írja. Edzői
  olvasat: ha a figura mindig ugyanarról a posztról indul, elég a
  kiinduló passzsávot zárni — a figura el sem indul. Saját oldalon az
  indítást variálni kell. Felületek: /analyze, meccs-csomag, edzői
  összefoglaló, felderítő kulcs + meccsterv (447.), edzés-fókusz
  (467.), kulcs-poszt lista és jelentés-lencse, kliens-csempe,
  3 teszt.

- **A labdás ember megtartja a csapatszínét** (kliens): a labdát vivő
  játékos arany ragyogása eddig a korong FÖLÉ került, és rámosódott —
  a két csapat labdás embere egyforma sárgás foltnak látszott, pont
  amikor a legfontosabb tudni, KI van a labdánál. A ragyogás mostantól
  a korong alá kerül: a token marad kék vagy piros, és csak a
  holdudvara arany.

- **A hőtérkép megmondja, mit jelent a szín** (kliens): a lövés- és a
  passz-nézetnek volt magyarázó csipetje, a hőtérképnek nem — pedig
  ott a SZÍN maga az adat, magyarázat nélkül viszont csak "valami
  piros folt". Mostantól a bal felső sarokban ott a skála (ritkán →
  sokat), a csapat neve és a rács mérete. A skála-sáv pontosan azt a
  fedettség-tartományt mutatja, amit a rajzoló használ — nem ígér
  többet, mint amit a kép ad.

- **Az "első lépések" kártya sorozatnak látszik** (kliens): az üres
  könyvtárnál megjelenő négy lépés eddig négy egymás alá tett tippnek
  tűnt, pedig SORRENDBEN kell elvégezni őket (videó → kalibráció →
  indítás → elemzés). Mostantól a sorszámokat összekötő vonal fűzi
  össze, és a lépések lépcsőzve úsznak be — az első benyomás is
  megmutatja, hogy van egy út.

- **A felderítés keresője megmutatja, HOL talált** (kliens): 467
  mérőszám közt a puszta szűrés kevés — a szem újra végigolvassa a
  címeket, hogy megtalálja a keresett szót. Mostantól a találat
  akcentus-színnel, félkövéren kiemelve látszik a csempe címében. A
  csoport-nyitó nyíl pedig FORDUL (nem kicserélődik), így látszik,
  hogy ugyanaz a csoport nyílt ki.

- **Sima lejátszás gyengébb gépen is** (kliens, teljesítmény): a
  felülnézeti pálya és a meccs-sztori sávja a lejátszófej MINDEN
  lépésénél újrarajzolódik — másodpercenként 25-ször. Mindkettő
  elmosással (MaskFilter.blur) lágyította a puha árnyékokat és
  ragyogásokat: a pályán tizennégy játékos árnyéka + a labdás ember
  fénye + a labda izzása, a sávon gólonként egy-egy pötty. Ez
  képkockánként tucatnyi (gólgazdag meccsen több tucat) külön
  rajz-menetet jelent. A lágyságot mostantól sugaras/lineáris
  színátmenet adja — a látvány ugyanaz, a költség töredéke, és a
  pálya árnyéka a motor saját (olcsó) árnyék-útján megy. Őr-teszt
  védi mindkét felületet.

- **A döntés-panel megmondja, mit mér** (kliens): a passz-döntéseknél
  eddig ott állt egy szám ("62% optimális") anélkül, hogy bárhol
  kiderült volna, MIHEZ képest optimális. Mostantól egy mondat
  megmondja: a mezőny akkori állásából számolva hányszor választotta a
  legjobb elérhető opciót — és hogy a 100% nem reális cél, mert a
  kényszerpasszok is beleszámítanak. A két nagy szám felpörög
  (játékos-váltásnál eddig némán ugrott át, és könnyű volt a régit
  olvasni az újnak), a cél-lista pedig lépcsőzve épül fel.

## v0.1.42 — kiadva (2026-08-23)

> Kiadás-jegyzet: ez a kör arról szól, hogy a program a FELHASZNÁLÓ
> nyelvén beszéljen, és hogy a grafikák magukban is válaszoljanak.
> Ha a motor nem válaszol, mostantól van EGY GOMB, ami tényleg
> újraindítja (és port-újrakeresést is végez), a hibaüzenet pedig
> odamutat; a felületen pedig egységesen "motor" szerepel a
> "backend"/"uvicorn" helyett — őr-teszt védi. Az eredmény-grafikonon
> színes mező mutatja, ki vezetett és mennyivel; a fejlődés-lapon
> változás-sáv a mutatók nagyságrendjét; a lövéstérkép a meccs
> sorrendjében rakja ki a lövéseket. Új elemző réteg: hetes-ismétlés
> — másodszorra is ugyanoda megy-e a hetesük.

- **A motor-hiba üzenete a MEGOLDÁSRA mutat** (kliens): a kapcsolódási
  hiba eddig azt mondta, hogy "a program újraindítása magától
  elindítja" — csakhogy ha a motor egy mélyebb okból nem indul, az
  újraindítás sem segít, és a felhasználó zsákutcába jut. Mostantól az
  üzenet a nyitóképernyő új "Motor újraindítása" gombjára mutat (ami
  port-újrakeresést IS csinál), és csak másodsorban javasolja a
  program bezárását.

- **UI 16. kör: a terhelés-tábla a csapat nyelvén beszél** (kliens): a
  játékosonkénti táv-csíkok eddig mind akcentus-színűek voltak, pedig
  a pályán, a grafikonokon és a jelmagyarázatban minden a csapat
  színét viseli. Mostantól a csík is a csapaté, az aktuális rendezés
  ÉLÉN álló ember arany jelet és félkövér mezszámot kap (nem kell a
  lista tetejét külön keresni), a sorok pedig lépcsőzve úsznak be.

- **A meccs-kártya emberi adatokat mutat** (kliens): a könyvtár
  kártyáinak alsó sora eddig gépi adat volt ("d3f1a · 6000 képkocka ·
  240.0 s · 25 fps"). Az edzőt a HOSSZ érdekli, percben — mostantól
  "4:00 perc · 25 kép/mp" áll ott, az azonosító és a képkocka-szám
  pedig rámutatásra (Tooltip) jön elő, ahol a hibakereséshez kell.

- **Egy néven nevezzük a motort** (kliens, nyelv): a felületen hol
  "backend", hol "motor", hol "lokális szerver (uvicorn)" szerepelt —
  ugyanarra a dologra három név, közülük kettő fejlesztői zsargon.
  Mostantól mindenhol MOTOR: a nyitóképernyő állapotsorán, a
  meccs-forrás címkéjén, a demó-korlátozásoknál, a kalibráció
  helyőrzőjén és a videó-út mezőn. Őr-teszt védi: a megjelenített
  szövegekben nem lehet "backend" vagy "uvicorn" (a kódban, importban,
  kommentben persze maradhat).

- **"Motor újraindítása" gomb a nyitóképernyőn** (kliens): ha a motor
  nem válaszol, az értesítés eddig azt mondta, hogy "indítsd el a
  lokális szervert (uvicorn)" — fejlesztői mondat egy edzőnek, aki
  asztali alkalmazást telepített, és pont ezt a hibát látta. Mostantól
  emberi nyelven szól, és van benne EGY GOMB, ami tényleg megcsinálja:
  előbb újra megkeresi a motort a port-tartományban, és ha sehol nem
  válaszol, újra is indítja. Ha ez sem sikerül, felugrik a motor
  naplójának a vége (kijelölhető szöveggel) — enélkül a felhasználónak
  nincs mit elküldenie a hibáról.

- **UI 15. kör: beszédesebb szezon-összkép a nyitóképernyőn** (kliens):
  a négy nagy szám eddig négy egyforma szürke dobozban ült, felirat
  nélkül nem lehetett őket ránézésre megkülönböztetni. Mostantól
  mindegyik saját ikont kap puha korongon, a kiemelt kártya
  akcentus-keretet és halk fényt, a sor pedig balról jobbra úszik be —
  a nyitókép "felépül", nem egyszerre csapódik oda.

- **UI 14. kör: az edzői összefoglaló lett a lap hőse** (kliens): az
  összefoglaló az egész elemzés emberi nyelvű kivonata, mégis
  ugyanolyan szürke csempe volt, mint az alatta futó tucatnyi kártya.
  Mostantól arany keretet és halk arany fényt kap, a címe is aranyra
  vált ikonnal, a szakaszai és a kiemelések lépcsőzve úsznak be. A
  hosszú szakaszok kinyitása pedig már nem ugrik: a doboz simán
  megnő (AnimatedSize), így látszik, hogy ugyanaz a szakasz lett
  hosszabb.

- **UI 13. kör: a lövéstérkép sorra rakja ki a lövéseket** (kliens):
  eddig a nézetre váltáskor az egész pontfelhő egyszerre jelent meg —
  a szem ilyenkor egyben látja, és nem tudja, hol kezdje. Mostantól a
  jelölők a meccs SORRENDJÉBEN pattannak be (900 ms alatt), így a
  lövés-történet is olvasható belőle. A térkép-csipet ráadásul
  kimondja, hogy a jelölő MÉRETE a helyzet értéke (xG) — eddig a nagy
  körök magyarázat nélkül voltak nagyok.

- **UI 12. kör: az eredmény-grafikon megmutatja a VEZETÉST** (kliens):
  eddig két lépcsős vonal futott egymás mellett, és a "ki vezetett,
  mennyivel" kérdést a néző fejben vonta ki belőlük. Mostantól a két
  vonal KÖZÖTTI mező a vezető csapat színét viseli, a fedettsége
  pedig a különbséggel nő — ránézésre látszik, meddig tartott a
  vezetés és mikor fordult a meccs. A csapat-területek halványabbak
  lettek, hogy a vezetés-mező olvasható maradjon.

- **Hetes-ismétlés** (új réteg): a hetes-sarok réteg eddig a dobó
  ELOSZLÁSÁT adta ("a heteseinek 60%-a balra megy") — a kapusnak
  viszont a SORREND kell: hova megy a MOST következő. Két dobó
  ugyanazzal a 60%-kal teljesen mást jelent. Az új réteg a dobónkénti
  hetes-sorozat egymást követő párjait nézi: hány ment ugyanabba a
  sávba. Edzői olvasat: ismétlő dobónál a kapusnak a LEGUTÓBB látott
  sarkot kell bekiabálni; saját oldalon a dobó kiszámítható, tehát
  váltani kell. Felületek: /analyze, meccs-csomag, edzői összefoglaló,
  felderítő kulcs + meccsterv (446.), edzés-fókusz (466.),
  kulcsember-lista, kliens-csempe, 3 teszt.

- **UI 11. kör: a fejlődés-képernyő mutatja a nagyságrendet** (kliens):
  a "korábbi → újabb" sorok eddig csak két szám voltak egy nyíllal —
  abból nem derült ki, hogy a mutató SOKAT vagy alig mozdult.
  Mostantól minden mutató alatt változás-sáv fut: a hossza a
  nagyságrend, a halvány rész a közös alap, a színes farok maga a
  változás. Mellé relatív jelvény kerül ("+23%"), az új érték
  felpörög, a sorok lépcsőzve úsznak be, az összegzés doboza pedig
  halk arany fényt kap.

- **A minőség-csipet kimondja, ha van mit javítani** (kliens): a
  fejlécben ülő minőség-csipet eddig csak SZÍNNEL utalt a bajra, a
  figyelmeztetések (pl. az elcsúszott kalibráció) a párbeszéd
  megnyitásáig rejtve maradtak — így a leggyakoribb hiba észrevétlen
  maradhatott. Mostantól a csipeten arany jelvény mutatja a
  figyelmeztetések DARABSZÁMÁT, a rámutatás megmondja, mit tegyünk, a
  részletek pedig a pályán kívülre eső mérés arányát is kiírják.

- **Elcsúszott kalibráció felismerése** (motor): a minőség-jelentés
  mostantól méri, a mért pozíciók hány százaléka vetül a pályán KÍVÜLRE
  (2 m tűréssel — a kifutó szélső és a mérés zaja belefér). 12% fölött
  kimondja, hogy a kalibráció valószínűleg elcsúszott (rossz sarokpont,
  vagy a kamera elmozdult felvétel közben), és megmondja a teendőt:
  a Pálya-kalibrációban ellenőrizni kell, hogy a rajzolt 6 m-es ÉS az
  új 9 m-es vonal ráül-e a valódiakra. Eddig ez a hiba csak
  "furcsán néznek ki a pozíciók" élményként jelentkezett.

- **Gyorsabb hőtérkép** (kliens, teljesítmény): a puha hőfoltok
  mostantól sugaras színátmenettel készülnek, nem cellánkénti
  elmosással — a rácson 200 cella van, és cellánként egy-egy elmosás
  külön rajz-réteget kényszerített volna ki (gyengébb gépen akadozó
  kép). A látvány ugyanaz, a költség töredéke. Őr-teszt védi.

- **Élő feldolgozás-képernyő** (kliens): itt tölti a felhasználó a
  legtöbb várakozási időt, ezért a folyamat mostantól él — a
  kör-jelző simán úszik az új állásra (nem ugrik), a százalék
  felpörög, a gyűrű mögött halk akcentus-ragyogás lélegzik; az ÉPPEN
  FUTÓ lépés kiemelt sávot kap, és az ikonja tényleg FOROG (eddig
  mozdulatlan "autorenew" volt, ami pont a mozgás hiányát sugallta).

## v0.1.41 — kiadva (2026-08-23)

> Kiadás-jegyzet: a felülnézeti pálya mostantól IGAZI kézilabda-pálya —
> 9 m-es szaggatott vonal, hetes- és kapus-vonal, kapuháló, mélység és
> gömbölyű játékos-tokenek; a labdás embert arany ragyogás emeli ki. A
> vezérlők is megfoghatóbbak: a meccs-sztori sávján hover-előnézet
> mutatja a cél-időpontot, a védekezés-sáv szakaszai felfénylenek, a
> mezők/gombok/fülek pedig egységes téma-nyelvet kaptak.

- **Egységes gombok, mezők és fülek** (kliens): a beviteli mezők
  mostantól kitöltött, lekerekített dobozok akcentus-fókusszal (eddig
  csak a fiók-képernyő csinálta ezt kézzel, minden más a Material
  aláhúzott alapját kapta); a gombok egységes lekerekítést és tapintható
  méretet; a meccs-nézet fülei a vékony alsó vonal helyett lekerekített
  akcentus-pill kijelölést.

- **Idővonalak: hover-előnézet és megfogható szakaszok** (kliens): a
  meccs-sztori sávján az egér alatt megjelenik a CÉL-IDŐPONT egy kis
  buborékban (koppintás előtt látszik, hova ugrik a lejátszó), a
  lejátszófej ragyogó vonalat és felső fogantyút kapott, a gólok
  pöttyei ragyognak. A védekezés-idővonal szakaszai rámutatásra
  felfénylenek és megnyúlnak — látszik, melyikre lehet ugrani.

- **Igazi kézilabda-pálya a felülnézeti képen** (kliens): a rajz eddig
  a 6 m-es kapuelőteret és a középvonalat ismerte; mostantól ott a
  szabálykönyvi **9 m-es szaggatott szabaddobási vonal**, a **7 m-es**
  (hetes) és a **4 m-es kapus-vonal**, és a kapuk mögött finom
  háló-rács. Mellé mélység: a pálya színátmenetes felületet és vetett
  árnyékot kapott, a játékos-tokenek gömbölyűek (sugaras átmenet +
  árnyék), a labdás ember arany ragyogást kap, a labda izzik, a
  kijelölt játékos nyomvonala pedig elhalványuló farokká vált — így a
  MOZGÁS IRÁNYA is látszik rajta. Őr-teszt védi a pályaelemeket.

## v0.1.40 — kiadva (2026-08-23)

> Kiadás-jegyzet: a vizuális kör lezárása. Animált kitöltésű mérő-sávok
> minden mutató-felületen (közös AnimatedBar elem), animált belépő
> képernyő és egységes márka-ragyogás a logón — a v0.1.39-es animációs
> alapokra építve.

- **Belépő képernyő és márka-ragyogás** (kliens): a belépő kártya
  finoman úszik be (az első benyomás animált), a logó a belépőn és az
  oldalsávban puha akcentus-ragyogást kapott.

- **Animált mérő-sávok** (kliens): a játékos-táv, döntés-, összegző-,
  felderítő- és fejlődés-nézetek kitöltés-csíkjai animálva úsznak az
  értékükre (közös AnimatedBar elem) — a "mennyi?" kérdésre a mozgás
  maga is felel.

## v0.1.39 — kiadva (2026-08-23)

> Kiadás-jegyzet: vizuális kör — az app "megmozdult". Animációs
> eszköztár (belépő animációk, szám-felpörgetés, hover-emelés), élő
> grafikonok (berajzolás, terület-kitöltés, sima görbék, ragyogó
> gól-pontok), puha hőtérkép és ívelt passzháló, világító navigáció, és
> egységes téma-nyelv a Material szürke alapértelmezései helyett —
> külső csomag nélkül, csupa beépített Flutter-primitívvel.

- **UI-szépítés: animációk és élő grafikák** (kliens, 4 kör):
  - Új animációs eszköztár (anim.dart): lépcsőzött belépés
    (FadeSlideIn), szám-felpörgetés (CountUp), asztali hover-emelés
    (HoverLift) — csupa beépített primitív, külső csomag nélkül.
  - Eredmény-grafikon: berajzolás-animáció, csapatszínű
    terület-kitöltés, ragyogó gól-pontok; intenzitás-grafikon: sima
    görbék (Catmull-Rom), terület-kitöltés, berajzolás.
  - Lövéstérkép: a gólok puha csapatszínű ragyogást kapnak; passzháló:
    ívelt élek, sugaras átmenetű csomópontok, a legaktívabb ember
    ragyogással; hőtérkép: éles rácstéglák helyett puha, elmosott
    hőfoltok világosodó maggal.
  - Dashboard: a meccs-kártyák lépcsőzve úsznak be, hoverre
    megemelkednek; a statisztika-nagyszámok felpörögnek; a felderítés
    csempe-fala lépcsőzve épül fel; az oldalsáv kijelölt eleme
    világító pill.
  - Globális téma-nyelv: kártya-formájú dialógusok és felugró menük,
    lebegő lekerekített snackbar, olvasható sötét súgóbuborék,
    egységes chipek, vékony görgetősáv; a várakozó nézet lélegző
    ragyogást, az üres állapot belépő animációt és korong-hátteres
    ikont kapott.

## v0.1.38 — kiadva (2026-08-23)

> Kiadás-jegyzet: megbízhatósági kör. A kiadás mostantól a motorba is
> belepecsételi a verziót, a /health kiadja, a kliens összeveti — a
> fél-frissült telepítés (új app + régi motor) piros sávként jelenik
> meg, megoldással, nem rejtélyes hibaként. Mellé a gépi ellenőrzés
> erősödött: push-CI (Dart-elemzés + gyors backend-őr kör), és a
> hiányzó fastapi pótlása, ami miatt az API-őrök eddig némán kimaradtak
> a CI-futásokból; a csomagolás-füstteszt a verzió-pecsétet is állítja.

- **Fél-frissült telepítés felismerése** (motor + kliens): a kiadás
  mostantól a MOTORBA is belepecsételi a verziószámot, a /health
  kiadja, a kliens pedig összeveti a sajátjával — ha az app és a motor
  verziója eltér (a fájlcsere félbe maradt, vagy a régi app-példány
  indult el), a dashboard piros sávban kimondja, és a megoldást is
  adja (teljes újratelepítés a Releases-ről). A rejtélyes "néha
  furcsán viselkedik" hibaosztály így néven nevezhető. Őr-tesztek a
  /health-verzióra és a kliens-sávra.

- **A CI-k tényleg futtatják az API-őröket** (infrastruktúra): a
  teszt-függőségek közül hiányzott a fastapi+httpx, ezért az összes
  API-teszt (fiókok, réteg-regisztry, könyvtár, csomag) modul-szinten,
  NÉMÁN kimaradt a gépi futásokból — helyben zöld volt, a CI-ben
  láthatatlan. A push-CI és a kiadási teszt-kör is pótolta; a push-CI
  emellett gyors backend-őr kört is kapott a Dart-elemzés mellé.

- **Push-CI Dart-elemzéssel** (infrastruktúra): minden push-ra lefut
  egy ~2 perces `flutter analyze` — a fordítást blokkoló Dart-hibát
  nem a drága (~20 perces) kiadási build fogja meg, hanem már a
  pusholás. Tanulság a v0.1.36-ból: egy típushiba az első kiadási
  buildet buktatta el.

## v0.1.37 — kiadva (2026-08-22)

> Kiadás-jegyzet: a vendég-mód kerekítése és egy új fáradás-réteg. A
> vendég-munkamenet mostantól látható (sáv a dashboardon, egy-
> kattintásos védelemmel), és van belőle út a fiókba a munka
> megtartásával. Az Elzárás-fáradás a fáradás-család kiegészítése a
> legfizikálisabb támadó-munkával; mellé a lövés-jelenetet mérő 13
> réteg az elengedés kockájára állt (a ritkított felvétel pontossága).

- **A jelenet-mérő rétegek is az elengedés kockájáról** (motor): a
  lövés-jelenetet mérő rétegek (elzárás-használat/-hozam/-fáradás,
  elzárók és elzárás-párosok, elzárás-védekezés, átvert védők,
  folyosó-gólok, kapott-lendület, kilépés-büntetés, célba vett védők)
  a képet eddig az esemény kockáján olvasták — ritkított felvételen
  ott már mindenki elmozdult. A match_xg lövés-rekordja mostantól a
  release_t-t is hordozza, és mind a 13 jelenet-mérő az elengedés
  kockájából mér (tartalék a régi viselkedés).

- **Vendégből fiókba — a munka megtartásával** (kliens): a vendég a
  fiók-menüből egy kattintással eljut a belépéshez ("Belépés / fiók
  létrehozása"), a belépési szándékkal nyitott kapu nem takarít, és
  sikeres belépésnél a vendég-munkamenet úgy zárul le, hogy a munka
  MEGMARAD — aki fiókot csinált, magáénak vallotta. Ha mégsem lép be,
  a következő hideg indulás takarít a szokott módon. Őr-teszt védi.

- **Elzárás-fáradás** (új réteg): ELFOGY-E az elzárás-munka a második
  félidőre — a fáradás-család (blokk-, fal-rés-, láb-fáradás)
  kiegészítése a legfizikálisabb támadó-munkával. Félidőnként méri, az
  őrzött lövéseik mekkora hányada elé érkezett elzárás. Edzői olvasat:
  az elfogyó elzárású csapat ellen a hajrában bátrabban léphet ki a
  fal (a lövő fedetlenül érkezik); a saját elfogyó elzárás kondíció-
  kérdés — az elzárók forgatása és a fáradt elzárás-gyakorlat az
  edzés-téma. Felületek: /analyze + meccs-csomag, edzői összefoglaló,
  felderítés (félidőnkénti darabszámok, edzői kulcs, 445.
  meccsterv-szabály), 465. edzés-szabály, kliens-csempe.

- **Vendég-sáv a dashboardon** (kliens): fiók nélküli munkamenetben a
  meccs-lista tetején sáv jelzi, hogy a most készülő munka az app
  következő indításakor törlődik — és egy kattintással védhetővé
  tehető ("Megőrzöm a munkám" = fejlesztői mód). Csendben elveszett
  munka így nem lehet. A telepítési útmutató a vendég-belépést és a
  kapu előtti frissítést is leírja. Őr-teszt védi.

## v0.1.36 — kiadva (2026-08-22)

> Kiadás-jegyzet: a belépésnél elakadt felhasználó kiszabadítása, két
> úton. Egy: vendég-belépés — az app fiók nélkül is használható (a
> tulajdonjogi tudomásulvétellel), a vendég-munka a következő
> induláskor törlődik, KIVÉVE ha a fejlesztői mód be van kapcsolva.
> Kettő: a frissítés-keresés és -telepítés a belépő képernyőről is
> elérhető — a frissítő eddig a fiók-kapu mögött volt, így aki a
> belépésnél akadt el, régi verzión ragadt, és a javítások sosem értek
> el hozzá.

- **Frissítés a kapu előtt** (kliens): a frissítés-keresés és
  -telepítés mostantól a BELÉPŐ képernyőről is elérhető — eddig csak a
  dashboardon (a fiók-kapu mögött) élt, így a belépésnél elakadt
  felhasználó régi verzión ragadt, és a javítások sosem értek el
  hozzá. A frissítéshez se fiók, se futó motor nem kell. Őr-teszt
  védi.

- **Vendég-belépés + fejlesztői mód** (kliens): az appba mostantól
  fiók nélkül is be lehet lépni ("Folytatás fiók nélkül (vendég)" a
  belépő képernyőn). A vendég-út nem kerüli meg a tulajdonjogi
  tudomásulvételt (első alkalommal a rövid elfogadó képernyő jön), és
  a vendégként végzett munka az app következő indulásakor törlődik — a
  takarítás alapvonal-alapú: csak a vendég-belépés UTÁN készült
  meccseket törli, a korábbiakat nem, és ha a motor nem érhető el,
  inkább nem töröl semmit. KIVÉTEL a fejlesztői mód: bekapcsolva a
  vendég-munka megmarad — a belépő képernyőről és a fiók-menüből is
  kapcsolható (fejlesztési fázisra való). Őr-tesztek: a
  tudomásulvétel megkerülhetetlensége, az alapvonal-alapú takarítás
  és a fejlesztői mód elsőbbsége is védve.

## v0.1.35 — kiadva (2026-08-22)

> Kiadás-jegyzet: három új poszt-réteg egy éjszaka alatt — a
> réteg-térkép ember/poszt pár-auditjának terméke (mindkét irányban
> végigfésülve; ezzel a pár-tér lefedett). A Rejtett szervező poszt, az
> Egálbontó poszt és a Befutó poszt közös elve: a minta posztról
> ismerszik meg, nem emberről — a felderítési kép a cserék és a
> meccsek közt is összeadódik. Mellé a poszt-távolság mérés
> elengedés-kockás pontosítása került még a v0.1.34-be; itt a
> stride-jelentés frissítése zárja a kört (26 dokumentált, mintavételi
> természetű eltérés).

- **Befutó poszt** (új réteg): MELYIK POSZT a második hullám a
  kontráikban — a befutó emberek poszt-szintű párja. A második
  hullámos kontra-befejezéseket a lövő posztjához írja: a "mindig az
  átlövő fut be másodikként" típusú kontra-szokás posztról ismerszik
  meg, a minta a cserék után is él. Edzői olvasat: a
  visszafutás-parancs posztra szól — az első ember felvétele után a
  poszt sávjába kell hátralépni, akárki játssza; a saját, egy posztra
  épülő második hullám kiszámítható — a befutót variálni kell.
  Felületek: /analyze + meccs-csomag, edzői összefoglaló, felderítés
  (posztonkénti darabszámok, edzői kulcs, 444. meccsterv-szabály),
  464. edzés-szabály, kliens-csempe, Kulcs-poszt regisztráció +
  riport-lencse sor.

- **Egálbontó poszt** (új réteg): MELYIK POSZTJUK viszi el a
  holtpontokat — az egálbontó emberek poszt-szintű párja. A
  döntetlenről szerzett gólokat a lövő posztjához írja: a "feszült
  pillanatban a beállóra megy a labda" típusú holtpont-terv posztról
  ismerszik meg, és a minta a cserék után is él. Edzői olvasat:
  egálnál a poszt sávjára korai kettőzés, akárki játssza; a saját, egy
  posztra épülő holtpont-tervnek második befejezési ág kell másik
  poszton. Felületek: /analyze + meccs-csomag, edzői összefoglaló,
  felderítés (posztonkénti darabszámok, edzői kulcs, 443.
  meccsterv-szabály), 463. edzés-szabály, kliens-csempe, Kulcs-poszt
  regisztráció + riport-lencse sor.

- **Rejtett szervező poszt** (új réteg): MELYIK POSZTON fut a
  másod-előkészítés — a hoki-assziszt (rejtett szervező) poszt-szintű
  párja. A gólpassz előtti passzokat az adó posztjához írja: a
  "mindig az irányító fordítja meg a falat" típusú szervezés posztról
  ismerszik meg, nem emberről — a minta a cserék után is él. Edzői
  olvasat: a passzsáv-zárást a poszt sávjában kell kezdeni, akárki
  játssza; a saját, egy posztra épülő szervezés kiszámítható — második
  indító-forrás kell. Felületek: /analyze + meccs-csomag, edzői
  összefoglaló, felderítés (posztonkénti darabszámok, edzői kulcs,
  442. meccsterv-szabály), 462. edzés-szabály, kliens-csempe,
  Kulcs-poszt regisztráció + riport-lencse sor.

## v0.1.34 — kiadva (2026-08-22)

> Kiadás-jegyzet: az elengedés-kocka (release_t) elvének végigvitele a
> teljes motoron. A v0.1.33 a lövés helyét és a kezességet állította az
> elengedés pillanatára — ez a kör a maradék hely-olvasót is: zónák,
> kapu-sarok (közös metszéspont-logikából), poszt-távolság,
> fedezettség, kapus-mérések és a lövés-döntés minősége. A release_t
> emellett idő-korlátot kapott (követés-lyukon át nem mutat régi
> kockára). Ritkított felvételen minden hely-alapú ítélet a tényleges
> elengedési pontból születik.

- **Zónák és kapus-mérések is az elengedés kockájáról** (motor): a
  lövés-zóna (felderítés), a kapus zóna-bontása, a kapus-forma
  fedezettség-szűrése és a lövés-döntés minősége (jobb passz-opciók) is
  az elengedés kockájáról (release_t) mér — az esemény kockáján a labda
  már métereket repült, a játékosok elmozdultak. Tartalék mindenhol a
  régi viselkedés.

- **A fedezettség is az elengedés pillanatából** (motor): a védekezés
  képe (defense), a fedezetten lövők (covered_shooters) és a
  szélső-kifutás (wing_closeout) a lövő és a védők távolságát eddig az
  esemény kockáján mérte — ott a labda már úton van, a lövő és a fal
  is elmozdult (ritkítva métereket). A mérés az elengedés kockájára
  (release_t) áll; a release_t pedig idő-korlátot kapott: követés-lyuk
  esetén a lövő NEVE megmarad, de a hely nem állítódik túl régi
  kockából.

- **A poszt-távolság is az elengedés kockájáról** (motor): a
  lövés-távolság poszt-bontása (role_shot_distance) a lövő helyét
  eddig az esemény kockáján olvasta — ritkított felvételen a lövő ott
  már elmozdult a lövése óta, és a távolság lefelé torzult. A mérés a
  release_t kockára áll (tartalék a régi viselkedés).

- **A kapu-sarok a tényleges beérkezési pontból** (motor): a
  gól-felismerés és az elhelyezés-rétegek közös metszéspont-logikát
  kaptak (goal_crossing_y). A lövő-kapuoldal réteg eddig a gólvonal
  0,7 m-es sávjába eső mintát követelt — ritkított felvételen ilyen
  sokszor nincs, az ítélet üresen maradt; mostantól a szakasz-metszés
  (vagy törésnél az extrapolált pont) y-ja adja a sarkot. A gól-minták
  rétege a lövő helyét az elengedés kockájáról olvassa. A stride-őr
  listája 27-ről 25-re rövidült; a maradék eltérés mintavételi
  természetű (kevesebb minta → óvatosabb ítélet), a jelentés
  dokumentálja.


## v0.1.33 — kiadva (2026-08-21)

> Kiadás-jegyzet: a v0.1.32 aznapi folytatása két szálon. Egyrészt a
> motor-elérés végleges megerősítése: őrkutya (az elhalt motort a
> program magától újraindítja), a motor-napló a hiba-képernyőn, és az
> elveszett válaszú regisztráció belépésbe futtatása. Másrészt a
> stride-őr leleteinek mélyjavítása: a lövés helye és a kezesség az
> elengedés kockájáról mérve, az együtemű lövés lövője a röppálya
> töréspontjából — ritkítva is 24/24 lövő-egyezés, az xG-torzítás
> eltűnt, a stride-eltéréslista 38-ról 27-re rövidült. Új réteg a
> Szuper-csere poszt (a tegnapi névre szóló réteg poszt-párja).

- **A kezesség az elengedés kockájáról mérve** (motor): a
  kezesség-becslés a labda test-melletti oldal-eltolását eddig az
  esemény-kocka előtti kockán mérte — ott a labda (ritkított felvételen
  különösen) már repül, és a röppálya oldal-eltolása hamis
  kezesség-jelet adhatott. A mérés mostantól az elengedés kockájára
  (release_t) áll: ott a labda még a lövő kezében van — a docstring
  eredeti szándéka szerint.

- **Az együtemű lövés lövője ritkítva is a lövő** (motor): a
  röppálya-töréspont szabálya. Ritkított felvételen az elkapásból
  azonnal (együtemben) leadott lövésnél a labda kézben-tartott kockája
  eltűnhet a minták közül — a lövő-kereső ilyenkor a PASSZOLÓT nevezte
  lövőnek (a szimulált meccsen ritkítva 4/24 gól csúszott át a
  passzolóra). Ritka felvételen (15 fps alatt) a felismerés mostantól a
  röppálya töréspontját keresi meg (ahol a passz-szár lövés-szárba
  vált), és a mellette álló saját mezőnyjátékost nevezi lövőnek — sűrű
  felvételen nem szólal meg. Az elengedés-hely javítással együtt a
  szimulált meccsen ritkítva is 24/24 a lövő-egyezés, az átlag xG
  0,141 vs 0,140 (a torzítás eltűnt), a stride-őr eltéréslistája 38-ról
  27 rétegre rövidült. Egység-teszt: együtemű szélső gól ritkítva.

- **A lövés helye az elengedés kockája** (motor): a stride-őr második
  lelete. A lövés-esemény a labda KAPU-MEGKÖZELÍTÉSEKOR jelölődik —
  ekkor a labda már úton van, és ritkított felvételen kockánként
  métereket ugrik: aki ott méri a lövés helyét, az a kapuhoz
  közelebbről mér, és az xG felfelé torzul (mérve: 0,14 → 0,20 átlag
  ritkítva). Az esemény mostantól az ELENGEDÉS kockáját is rögzíti
  (release_t: az utolsó kocka, ahol a lövő még birtokolta a labdát), és
  az xG onnan mér — az egyező lövőjű lövések helye ritkítva is kockára
  azonos. Ami marad: a nagyon gyors (szélső) lövések lövő-hozzárendelése
  ritkítva néha a passzolóra csúszik — ez mintavételi korlát, a
  stride-jelentés dokumentálja. Regressziós teszt: a 12 m-es átlövés
  akkor is 12 m-esként mérődik, ha a lövő utána besétál a hatosig.

- **Motor-őrkutya** (kliens): ha a motor-folyamat magától elhal, a
  program azonnal, magától újraindítja (munkamenetenként legfeljebb 3
  próbával — a hibás motort nem pörgeti örökké), a szándékos
  leállítást (kilépés, frissítés előtti fájlcsere) pedig békén hagyja.
  A felhasználó így a legtöbb motor-elhalást észre sem veszi: a
  következő kattintás már az új példányhoz ér. Őr-teszt védi.

- **Szuper-csere poszt** (új réteg): MELYIK POSZTRÓL termel a paduk —
  a névre szóló Szuper-csere poszt-szintű párja (a kódbázis bevett
  emberek/poszt réteg-pár mintája szerint). A padról beállók góljait a
  lövő posztjához írja: a minta akkor is látszik, ha a nevek meccsről
  meccsre cserélődnek. Edzői olvasat: a posztról olvasható pad ellen az
  arra a posztra érkező friss embert az érkezése pillanatában kell
  felvenni; a saját, egy posztra épülő pad kiszámítható — második
  pad-megoldás kell. Felületek: /analyze + meccs-csomag, edzői
  összefoglaló, felderítés (posztonkénti pad-gól számok, edzői kulcs,
  441. meccsterv-szabály), 461. edzés-szabály, kliens-csempe,
  Kulcs-poszt regisztráció + riport-lencse sor.

- **Elveszett válaszú regisztráció → belépés** (kliens): ha az első
  fiók-létrehozó kérés célba ért, de a válasz elveszett (a motor épp
  elhalt), az újraélesztett ismétlés "már van fiók" hibát adna — pedig
  a fiók él. A kliens ilyenkor belépéssel folytatja ugyanazokkal az
  adatokkal. Őr-teszt védi.

- **A motor naplója a hiba-képernyőn** (kliens): ha a motor az
  újraélesztés után sem válaszol, a hiba-képernyő a motor-napló utolsó
  sorait is megmutatja (kijelölhető szövegként) — a kiváltó ok így
  egyetlen hibajelentő képernyőképen elfér, a felhasználónak nem kell
  fájlok közt keresgélnie. Őr-teszt védi.

## v0.1.32 — kiadva (2026-08-21)

> Kiadás-jegyzet: gyors javító+bővítő kör a v0.1.31 után. A fő ok a
> fiók-képernyő ismételt "Nem érem el a háttérmotort" hibája: a kliens
> mostantól nem csak keresi, hanem újra is INDÍTJA az elhalt motort, és
> a képernyők kiírják a futó verziót. Mellé a stride-őr első komoly
> leletének javítása (ritkított felvételen elveszett gólok) és egy új
> névre szóló réteg (Szuper-csere).

- **Szuper-csere** (új réteg): KI termel a padról — névre szólóan. A
  pad-gólok réteg azt mondja meg, termel-e a kispad egyáltalán; ez azt,
  ki: a kezdő maghoz nem tartozó gólszerzők név szerint, és ha a
  pad-gólok legalább fele (3+ gólból) egy emberé, ő a csapat
  szuper-cseréje. Edzői olvasat: a szuper-cserés csapat ellen a
  beállása a jelzés — onnantól rá külön figyelő és friss védő; a saját
  szuper-cserénk pedig időzítve ér a legtöbbet (a fáradó fal ellen
  álljon be, ne csak pihentetésként). Felületek: /analyze +
  meccs-csomag, edzői összefoglaló, felderítés (játékosonkénti
  pad-gól számok, edzői kulcs, 440. meccsterv-szabály), 460.
  edzés-szabály, kliens-csempe, kulcs-ember regisztráció.

- **A motor-újraélesztés mostantól újra is INDÍT** (kliens-javítás): a
  fiók-képernyő ismételt "Nem érem el a háttérmotort" hibája nyomán. A
  v0.1.30-as öngyógyítás hálózati hibánál újra MEGKERESTE a motort a
  port-tartományban — de ha a motor-folyamat közben elhalt (frissítés
  utáni fájlcsere, a gép altatása, belső hiba), a keresés kevés volt,
  és csak a program teljes újraindítása segített. A kliens mostantól
  ilyenkor ÚJRA IS INDÍTJA a motort (reviveEngine → BackendLauncher),
  a fiók-kapun és a beküldésnél is; a motor-hiba képernyő elmondja,
  hogy az Újrapróbálom gomb ezt megteszi, és hova kell nyúlni a
  naplóért. A fiók-képernyő és a hiba-képernyő ezentúl a futó kiadás
  számát is kiírja — egy hibajelentő képernyőképből azonnal látszik,
  melyik verzió adta a hibát. Őr-tesztek: a mély öngyógyítás és a
  látható verziószám is védve.

- **A gól ritkított felvételen is gól** (motor): a stride-érzékenység
  őr első komoly lelete. A gól-felismerés eddig azt követelte, hogy a
  labda egy MINTÁN a gólvonal 0,7 m-es sávjában legyen — a termék
  alap-ritkításánál (minden 3. kocka, effektív ~8 fps) viszont a labda
  kockánként métereket lép, és a sávot ÁTUGORJA: a szimulált meccsen a
  gólok kétharmada sima lövésnek minősült. A felismerés mostantól három,
  egymást kiegészítő jelre épül: (1) minta a sávban (a hálóban megülő
  labda), (2) a két egymást követő minta közti útvonal átlépi a
  gólvonalat a kapufák között, (3) ritkított felvételen (15 fps alatt) a
  vonal egy lépésén belül járó, kapu felé tartó labda extrapolált
  átlépése, ha a követés ott megszakad (élesben a hálóba érő labdát a
  háló kitakarja, és a középkezdésnél bukkan fel) — folytonos követésnél
  az extrapoláció nem szólal meg, sűrű felvételen a viselkedés
  változatlan. A szimulált meccsen stride 1/2/3 mellett most mind a 24
  gól megvan (korábban 24/4/8); a stride-őr eltérés-listája 53-ról 37
  rétegre rövidült. Regressziós tesztek mindhárom jelre.

## v0.1.31 — kiadva (2026-08-21)

> Kiadás-jegyzet: a v0.1.30 óta a kör három szálon futott — egy
> JAVÍTÁS a kiadott fal-rés réteghez, négy új elemző réteg és a fiók
> felületének kerekítése, valamint két új minőség-őr.
>
> **(1) Fal-rés javítás.** A v0.1.29–30-ban kiadott fal-rés térkép két
> helyen félrevezethetett: az oldal-nevet a pálya nyers
> koordinátájából adta (a két csapat szemben áll — az egyik falról
> fordított oldalt mondott), és a szerep-jelölés nélküli kapus hamis,
> több méteres "rést" nyithatott. Mindkettő javítva, őr-tesztekkel; a
> sáv mostantól a FAL saját nézőpontjából kap nevet, mint az
> engedett-oldal rétegben.
>
> **(2) Négy új réteg.** Vasemberek (KI játssza végig csere nélkül — a
> hajrá név szerinti célpontja), Hoki-assziszt (a gólpassz ELŐTTI
> passz — a rejtett szervező), Hetes-sarok emberre (melyik sarkát
> keresi a dobó — a kapus előre dönthet), Fal-rés fáradás (szétnyílnak-e
> a közök a 2. félidőre — a betörős figurákat akkorra kell tenni).
> Mind a teljes felület-sorral: /analyze + meccs-csomag, edzői
> összefoglaló, felderítés + meccsterv-szabály, edzés-szabály,
> kliens-csempe; a névre szóló rétegek a Kulcs-ember lencsébe is.
>
> **(3) Fiók-felület és minőség-őrök.** Jelszócsere a fiók-menüből,
> elfelejtett-jelszó útmutató a belépőn. Két új jelentés-szintű őr:
> tükrözés-őr (a bal/jobb oldal-nevek helyessége — 11 oldal-címkés
> réteg, mind helyes) és stride-érzékenység őr (a kocka-ritkítás
> hatása az ítéletekre — 486 rétegből 53 érintett, dokumentálva).
>
> A csomag 486 elemző réteget, 439 meccsterv- és 459 edzés-szabályt
> tartalmaz; a teljes backend csomag zöld (1755 teszt), a
> sorrend-függés lista üres.


- **Stride-érzékenység őr** (minőség-eszköz): új jelentés-szkript
  (`scripts.stride_sensitivity` → `docs/STRIDE_ERZEKENYSEG.md`). A
  feldolgozó alapból minden harmadik képkockát dolgozza fel (stride=3,
  effektív fps = fps/3) — a kockaszám-küszöbbel ítélő rétegek ugyanarról
  a meccsről ritkítva másképp (jellemzően óvatosabban) ítélhetnek. Az őr
  ugyanazt a szimulált meccset sűrűn és ritkítva futtatja, és csak az
  ÍTÉLET-mezőket veti össze (verdict, top, main_role, …) — a nyers
  számok ritkítva jogosan térnek el. Az első teljes futás: 486 rétegből
  53 ítél másképp — ez a lista a küszöb-kalibrálás leltára, a CLAUDE.md
  recepthez hozzáadva. Gyors tesztek rögzítik a mechanikát (a ritkítás
  a termék modelljét követi: t újraszámozva, fps harmadolva — az
  időzítés pontos marad).
- **Fal-rés fáradás**: SZÉTNYÍLNAK-E a közök a második félidőre. A
  fal-fáradás (wall_fade) a következményt méri — jobb helyzeteket
  engednek a 2. félidőben; ez az okot: a szomszédos védők közti
  legnagyobb köz átlagát félidőnként (a fal-rés térkép közös
  motorjával). Ítélet félidőnként 60+ értékelhető kockától, 0,8 m
  növekedéstől. Edzői olvasat: a fáradt fal nem lassabban fut, hanem
  később zár — aki ellen a 2. félidőben nyílnak a közök, ott a betörős
  figurákat a MÁSODIK félidőre kell tartogatni (az első félidei "nem
  ment" nem ítélet); saját oldalon ez csere-terv: a belső védőket kell
  forgatni, mielőtt a köz kinyílik. Felületek: /analyze + meccs-csomag,
  edzői összefoglaló, felderítés (edzői kulcs + 439. meccsterv-szabály
  a betörő emberrel párosítva), 459. edzés-szabály, kliens-csempe.
- **Jelszócsere a fiók-menüből + elfelejtett-jelszó útmutató**
  (kliens): a jelszócsere-végpont eddig felület nélkül állt — mostantól
  a jobb felső fiók-menü "Jelszócsere" pontja nyitja (jelenlegi + új
  jelszó; a csere a máshol nyitva maradt belépéseket érvényteleníti, az
  itteni munkamenet új kulcsot kap, tehát nem dob ki). A belépő
  képernyő sikertelen belépésnél elmondja az elfelejtett jelszó őszinte
  útját is: a fiókok csak ezen a gépen élnek, nincs e-mailes
  visszaállítás — új fiókkal a meccsek és elemzések megmaradnak (a
  géphez tartoznak, nem a fiókhoz). Őr-teszt rögzíti, hogy a
  jelszócsere elérhető a felületről, és az útmutató ott van a belépőn.
- **Hetes-sarok emberre**: MELYIK SARKÁT keresi a hetesdobójuk. A
  hetes-oldal réteg csapatra mondja meg, merre mennek a hetesek — a
  kapusnak viszont a DOBÓ kell: a hetesnél ő az egyetlen, akinek van
  ideje dönteni, és a dobók szokás-állatok — nyomás alatt a begyakorolt
  sarkukat keresik. A réteg a hétméterek irány-jelét dobóra bontja;
  ítélet dobónként 3+ irány-mérhető hetestől, 60%+ részaránytól. Edzői
  olvasat: a bejáratott sarkú dobónál a kapus NE olvasson, hanem előre
  döntsön — tudatosan arra a sarokra vetődjön; a szórónál a mozdulatból
  kell olvasnia. Saját oldalon: a kiszámítható dobónk sarkát variálni
  kell, és második dobót építeni. Felületek: /analyze + meccs-csomag,
  edzői összefoglaló, felderítés (edzői kulcs + 438. meccsterv-szabály
  a fogó kapussal párosítva), 458. edzés-szabály, Kulcs-ember lencse,
  kliens-csempe.
- **Hoki-assziszt (rejtett szervező)**: KI adja a gólpassz ELŐTTI
  passzt. A gólpasszos mindig látszik — a valódi szervező sokszor
  eggyel korábban van: ő adja azt a passzt, ami elmozdítja a falat
  (oldalváltás, betörés utáni kiosztás), a gólpassz utána már csak
  végrehajtás. A réteg a gólokhoz a gólpassz előtti utolsó, a
  gólpasszolóhoz érkező saját passzt köti (6 mp-en belül, és nem
  átnyúlva az előző lövésen — az más támadás volt), emberre összesítve;
  ítélet 2+ másod-előkészítéstől, a láncolt gólok felétől. Edzői
  olvasat: a rejtett szervező ellen a passzsáv-zárást EGGYEL korábban
  kell kezdeni — ha ő nem tudja megjátszani a beadót, a gólgyár el sem
  indul; saját oldalon ez a láthatatlan munka kimutatása (a
  hoki-asszisztos embert a gól/gólpassz statisztika alulméri), és
  figyelmeztetés: a szervezés ne egy rejtett kézen fusson. Felületek:
  /analyze + meccs-csomag, edzői összefoglaló, felderítés (edzői kulcs
  + 437. meccsterv-szabály a labdaszerzéssel párosítva), 457.
  edzés-szabály, Kulcs-ember lencse, kliens-csempe.
- **Vasemberek**: KI játssza végig a meccset csere nélkül — a
  vasember-poszt ember-ikre. A poszt a tervhez kell (hova vigyük a
  tempót), a név a padhoz: a mezszám szerint összevont
  jelenlét-időkből kigyűjti, ki van a pályán a meccs 85%-a felett
  (10+ perces felvételtől; háromnál több végigjátszó már csapat-stílus,
  nem célpont — ott a rotáció-mélység beszél). Edzői olvasat: a
  végigjátszó ember a hajrában a legfáradtabb a pályán — az utolsó tíz
  percben ŐT kell futtatni (elzárások hozzá, betörés az ő sávjában), és
  vele szemben mindig friss láb jöjjön; saját oldalon a hajrá-hibái nem
  formahanyatlás, hanem terhelés — tervezett pihentetés vagy tudatos
  tempóváltás kell. Felületek: /analyze + meccs-csomag, edzői
  összefoglaló, felderítés (edzői kulcs + 436. meccsterv-szabály a mély
  paddal párosítva), 456. edzés-szabály, kliens-csempe.
- **Tükrözés-őr** (minőség-eszköz): új jelentés-szkript
  (`scripts.mirror_sides` → `docs/TUKROZES.md`), amely a pálya
  hossztengelyére tükrözött meccsen ellenőrzi, hogy minden
  oldal-megnevezés ("bal szél" → "jobb szél") helyesen megfordul-e. A
  fal-rés hibája ihlette: aki a nyers y-koordinátából nevez oldalt, az
  a védekező csapatról fordítva állít, mert a két csapat szemben áll. A
  mérés a magyar nyelv csapdáját is kezeli (a "jobb" better-t is
  jelent: csak a pontos oldal-címkék cserélődnek, a próza soha). Az első
  futás eredménye: 11 oldal-címkés réteg, mind helyesen tükröződik.
  Gyors tesztek rögzítik a mechanikát (test_mirror_sides.py); a teljes
  söprés kiadás előtti feladat, a CLAUDE.md recepthez hozzáadva.
- **Fal-rés térkép: javítás az oldal-megnevezésben és a jelöletlen
  kapusnál**. Két félrevezető állítást javít az előző kiadásban
  bemutatott rétegen: (1) a rés sávját eddig a pálya nyers y-koordinátája
  szerint nevezte meg, holott a két csapat SZEMBEN áll — ugyanaz a
  pálya-sáv az egyik falnak a bal, a másiknak a jobb oldala, tehát az
  egyik csapatról fordított oldalt mondtunk (a saját kapujától a pálya
  felé néző védő bal keze a nagyobb y felé esik; ugyanez a konvenció,
  mint az engedett-oldal rétegben); (2) a kapust eddig csak a
  szerep-jelölés alapján hagyta ki, így egy jelöletlen kapus több
  méteres HAMIS rést nyitott a fal és a kapu között — mostantól a
  kaputól 2 m-en belül álló játékos akkor is kimarad, ha nincs
  szerepe. Mindkettőre őr-teszt került.

## v0.1.30 — kiadva (2026-08-20)

> Kiadás-jegyzet: javító kiadás a v0.1.29 fiók-kapujához.
>
> A fiók-képernyő betöltése ment (a feltételek és a tulajdonos neve
> megjött a motortól), a "Fiók létrehozása" viszont "Nem érem el a
> háttérmotort" hibát adhatott: a kliens a képernyő létrehozásakor
> BEFAGYASZTOTTA a motor címét, így ha a motor közben másik portra
> költözött (újraindulás, tartalék port, vagy két app-példányból az
> egyik kilépett a motorjával együtt), a képernyő a halott címre
> beszélt. Mostantól a cím mindig az éppen érvényes, a fiók-kapu és a
> fiók-készítő pedig hálózati hibánál MEGKERESI a motort újra, és
> egyszer újrapróbálja a kérést. Ha tényleg nem fut motor, a kapu
> beszélő képernyőt mutat — teendővel, a napló helyével és
> Újrapróbálom gombbal — nem egy űrlapot, ami csak beküldéskor bukik el.
>
> Megelőzésként a kiadás füsttesztje már nem áll meg a /health-nél: a
> becsomagolt motoron végigjátssza a teljes belépő-utat, és a csomagoló
> a saját csomagok minden almodulját beveszi.


- **A motor elmozdulása nem dobja el a kérést** (kliens): a kliens
  eddig a példány létrehozásakor BEFAGYASZTOTTA a motor címét — ha a
  motor közben másik portra költözött (újraindult, tartalék portra
  kötött, vagy két app-példányból az egyik kilépett a motorjával
  együtt), a régóta nyitva lévő képernyők a halott címre beszéltek.
  Ettől fordulhatott elő, hogy a fiók-képernyő BETÖLTÉSE még ment (a
  feltételek és a tulajdonos neve megjött), a "Fiók létrehozása" viszont
  már "Nem érem el a háttérmotort" hibát adott. Mostantól a cím mindig
  az éppen érvényes alapértelmezés, a fiók-kapu és a fiók-készítő pedig
  hálózati hibánál MEGKERESI a motort újra (8000-től felfelé), és
  egyszer újrapróbálja a kérést.
- **A kiadás füsttesztje a fiók-folyamatot is végigjátssza** (CI): eddig
  csak a /health-et hívta a becsomagolt motoron. A fiók-végpontok
  futásidőben importálnak, ezért egy csomagolási hiány csak a
  felhasználónál bukott volna ki — az első képernyőn. A build mostantól
  lekéri a feltételeket és a fiók-állapotot, létrehoz egy próba-fiókot,
  ellenőrzi, hogy elfogadás NÉLKÜL elutasít (400), és belép — izolált
  adatmappában, mindkét platformon. Emellé a csomagoló a `handball` és a
  `scripts` MINDEN almodulját beveszi (a projekt sok modult a függvény
  testéből importál), és őr-tesztek rögzítik mindkettőt.
- **A fiók-kapu megmondja, ha nem fut a motor** (kliens): a fiókok a
  motorban élnek, a fiók-lekérdezés viszont hálózati hibára is
  "nincs bejelentkezve"-t adott — a felhasználó ezért egy űrlapot
  kapott, ami csak a BEKÜLDÉSNÉL bukott el ("Nem érem el a
  háttérmotort"). A kapu mostantól előbb megnézi, él-e a motor, és ha
  nem, beszélő képernyőt mutat: mit tegyen (teljes újraindítás), hol a
  motor naplója (engine-app.log, platformonkénti útvonallal), plusz egy
  Újrapróbálom gomb és a demó módba lépés. A motor menet közben is
  leállhat (pl. frissítés után), ezért az újrapróbálás ugyanazt a
  teljes ellenőrzést futtatja le.

## v0.1.29 — kiadva (2026-08-20)

> Kiadás-jegyzet: a v0.1.28 óta a kör három szálon futott — a program
> JOGI és FIÓK-kerete, a valódi csarnok-felvételekhez igazított
> felismerés, és tizenegy új elemző réteg.
>
> **(1) Fiókok és felhasználási feltételek.** A program mostantól
> fiókhoz kötött, és az első használat előtt el kell fogadni a
> feltételeket: a Sport Machine a Tulajdonos kizárólagos SZELLEMI
> tulajdona, a példányai és a hozzá adott eszközök a FIZIKAI
> tulajdonát képezik, a felhasználó pedig korlátozott, át nem
> ruházható, bármikor visszavonható használati engedélyt kap. A fiók a
> saját gépen készül el (nincs felhő), a jelszó sose tárolódik
> nyíltan, a belépés 90 napig érvényes, a feltételek verziózottak — ha
> a szöveg megújul, a belépés újra elfogadásra kínálja, és az
> elfogadás verzióját + időpontját a fiók őrzi.
>
> **(2) Valódi csarnok, valódi felvétel.** A vonal-felismerés eddig
> FEHÉR vonalat keresett — a több sportot kiszolgáló csarnokokban
> viszont a kézilabda-pályát gyakran PIROS vonal jelöli, a kosár- és
> futsal-vonalak meg keresztezik. Mostantól van szín-alapú vonalmaszk
> (piros/kék/zöld/sárga) és "auto" mód, ami a képből dönti el, melyik
> szín vonalait kövesse; a festett mezők belseje nem vonal, csak a
> szélük. Emellé jött a kispad- és néző-szűrés: a vonal mellett VÉGIG
> EGY HELYBEN ülő track nem játékos — eddig felfelé húzta a létszámot
> és beleszólt a fal-mérésekbe. A bevonulás/köszöntés meccs-ablakon
> kívül tartását őr-teszt rögzíti.
>
> **(3) Tizenegy új elemző réteg.** Kezesség-becslés (melyik kézzel
> lőnek) és a poszt-párja; a kapus-védés kezesség szerint (bírja-e a
> balkezeseket); a fal geometriája — védekezési formáció-biztosság
> (mennyire ÁLLANDÓ a fal alakja) és fal-rés térkép (hol és mekkora a
> legnagyobb köz); befejezés-mérleg (fenntartható-e a gólterméskük);
> csere-fázis (támadásban vagy védekezésben cserélnek); meccs-ablak,
> egálbontó, befutó, leforduló és keresztjáró emberek, futtatott
> szélsők.
>
> A csomag 480 elemző réteget, 435 meccsterv-szabályt és 455
> edzés-szabályt tartalmaz; a teljes backend csomag zöld (1732 teszt),
> és a sorrend-függés lista üres (482 rétegből 0).


- **Poszt-kezesség**: MELYIK POSZTJUKON lő balkezes. A kezesség-becslés
  névre mondja meg, ki balkezes — ez posztra: a név meccsről meccsre
  cserélődhet, a poszt marad, ezért a védekezés-terv és a
  kapus-felkészítés poszt-alapon tart ki. Ítélet posztonként 4+
  értékelhető lövéstől, 70%+ egyoldalúságtól. Edzői olvasat: a balkezes
  a JOBB oldali posztok (jobbszélső, jobbátlövő) fegyvere — befelé jövet
  a megszokott sánc-kéz mellett lő el, ezért azon az oldalon tükrözni
  kell (a sánc a másik kezét emelje, a kapus a túlsó sarkat vegye
  alapba, a befelé vezető utat elzárni); saját oldalon a balkezes
  posztra külön figurát érdemes építeni. Felületek: /analyze +
  meccs-csomag, edzői összefoglaló, felderítés (edzői kulcs + 435.
  meccsterv-szabály), 455. edzés-szabály, kliens-csempe.
- **Kispad- és néző-szűrés a követésben**: a pálya-régió szándékosan
  hagy tűréssávot a vonalon kívül (a játékos néha kilép: partdobás,
  cserezóna) — a csarnokban viszont pont ebben a sávban ül a CSEREPAD és
  a nézők első sora. A felhasználó felvételén a padok székei
  közvetlenül az oldalvonal mellett vannak, tehát a rajtuk ülők eddig
  "játékosnak" számítottak (felfelé húzva a létszámot, és a fal-, a
  formáció- és a rés-mérésbe is beleszólva). Mostantól a feldolgozás
  eldobja azt a track-et, amelyik a mért kockái legalább 80%-ában a
  vonalakon kívül van, ÉS a mozgása belefér egy 3 m-es dobozba (ül vagy
  áll) — legalább 50 mért kockából. A kilépő, de MOZGÓ játékos
  (partdobás, csere) megmarad, és a rövid track-ekről nem ítélünk. A
  napló kiírja, hány álló, pályán kívüli track esett ki.
- **Fal-rés térkép**: HOL és MEKKORA a legnagyobb köz a falukban. A
  fal-szélesség a fal teljes terjedelmét méri, a formáció az alakját —
  ez a KÖZÖKET: felállt védekezésnél a mezőnyvédőket keresztirányban
  sorba rakja, és megnézi a szomszédos védők közti legnagyobb hézagot,
  a méretét és a sávját (bal szél / közép / jobb szél). Ítélet 100+
  kockától: 3,5 m feletti átlagos legnagyobb rés = rés-veszélyes fal, és
  40% feletti részaránynál a sáv is nevesül. Edzői olvasat: ez a betörés
  címe — egy 4 m-es résbe lendületből befér egy ember, az elzárást a rés
  MELLÉ kell tenni, hogy ne záródjon; ha a rés mindig ugyanabban a
  sávban nyílik, az bejáratott gyengeség (rendszerint a kilépő védő
  mellett), és a figurát arra kell építeni. Saját oldalon a szomszédok
  átadás-rendjét kell gyakorolni. Felületek: /analyze + meccs-csomag,
  edzői összefoglaló, felderítés (edzői kulcs + 434. meccsterv-szabály),
  454. edzés-szabály, kliens-csempe.
- **Kapus-védés a lövő kezessége szerint**: bírja-e a kapusuk a
  BALKEZESEKET. A posztonkénti és a távolság-sávos kapus-kép után a
  harmadik tengely a lövő KEZE: a balkezes lövő tükör-feladat a
  kapusnak (az alapállás, a láb-munka és a sarok-olvasás a
  jobbkezesekre van bejáratva), és sok kapus mérhetően gyengébb
  ellenük. Ítélet kezenként 4+ kapura tartó lövéstől, 15
  százalékpontos különbségtől. Edzői olvasat: ha a kapusuk a
  balkezesek ellen gyengébb, a balkezes emberünket kell rá szervezni —
  az ő oldaláról indított figurákkal, és hetesnél is ő álljon oda; ha
  a saját kapusunk esik vissza, balkezes dobókkal (vagy tükrözött
  gyakorlattal) kell edzeni. Felületek: /analyze + meccs-csomag, edzői
  összefoglaló, felderítés (edzői kulcs + 433. meccsterv-szabály),
  453. edzés-szabály, kliens-csempe.
- **Színes pályavonalak: a piros kézilabda-vonal is pálya**: a
  vonal-felismerés eddig FEHÉR vonalat keresett (a padlónál világosabb
  pixelt). A több sportot kiszolgáló csarnokokban viszont a padlón
  egymáson futnak a kosár-, futsal- és röplabda-vonalak, és a
  kézilabda-pályát gyakran PIROS vonal jelöli — nagy festett mezőkkel
  együtt (sárga kapuelőtér, színes pályafelület). Mostantól van
  szín-alapú vonalmaszk (piros/kék/zöld/sárga), és az "auto" mód a
  képből dönti el, melyik szín vonalait kövesse: a fehér csak akkor
  veszít, ha egy szín érdemben több vonal-pixelt hoz. A festett mezők
  BELSEJE nem vonal — csak a szélük —, így a sárga kapuelőtér nem
  árasztja el a felismerést. A /broadcast/lines végpont új `line_color`
  paramétert kapott (alap: "auto"), és visszaadja, melyik színt
  használta; a kliens közvetítés-ellenőrzője ki is írja ("… piros
  vonalak alapján"), hogy látszódjon, mit követ a rendszer.
- **Bevonulás/köszöntés a meccs-ablakon kívül** (őr-teszt): a
  meccs-ablak eddig is a MOZGÁSBÓL ismerte fel a ceremóniát — mostantól
  ezt teszt is rögzíti: a felezővonalnál sorban álló két csapat (elég
  ember a pályán, közeli súlypontok, de nincs mozgás) nem játék, és a
  csak ceremóniát tartalmazó felvételre nincs meccs-ablak.
- **Befejezés-mérleg**: FENNTARTHATÓ-E a gólterméskük — a gól és a
  várható gól (xG) különbsége edzői ítélettel. A meccs-xG eddig is
  kiszámolta a különbséget, de nem mondta meg, mit kezdjen vele az edző.
  Ítélet 12+ lövéstől, 2,5 gólnyi eltéréstől: aki a helyzetei FELETT
  teljesít, annak a gólszáma szebb a játékánál — ugyanezekből a
  helyzetekből legközelebb kevesebb gól lesz; aki ALATT, annál a játék
  jó, csak a befejezés nem ült, ő veszélyesebb, mint amit az eredmény
  mutat. Edzői olvasat felderítésben: a felülteljesítő ellen NEM kell
  átszabni a védekezést — ugyanazokat a lövéseket kell rájuk
  kényszeríteni, és a kapus alapállását a bejáratott sarkukra állítani;
  az alulteljesítő ellen a helyzet-teremtést kell megfogni. Saját
  oldalon az alulteljesítés befejezés-edzést jelent a MEGLÉVŐ
  helyzet-típusokra. Felületek: /analyze + meccs-csomag, edzői
  összefoglaló, felderítés (edzői kulcs + 432. meccsterv-szabály), 452.
  edzés-szabály, kliens-csempe.
- **Csere-fázis**: MIKOR indul a cseréjük — a cserehullám pillanatában
  kinél volt a labda. A csere-kiváltók azt mondják meg, mire cserélnek, a
  csere-lyukak azt, meddig vannak öten; ez azt, hogy saját birtoklásban
  (olcsó), az ellenfél támadása alatt (drága) vagy megszakításban
  váltanak-e. Ítélet 4+ cseréről: 40% felett kockázatos csere-rend, 15%
  alatt fegyelmezett. Edzői olvasat: aki az ellenfél birtoklása közben is
  forgat, annál a fal egy emberrel kevesebbel áll fel — a csere
  pillanatában azonnal indítani kell a csere OLDALÁRA, és a rövid ideig
  nyitva lévő szélen befejezni; saját oldalon a szabály egyszerű:
  cserélni birtoklásban vagy megszakításban lehet, az ellenfél támadása
  alatt nem. Felületek: /analyze + meccs-csomag, edzői összefoglaló,
  felderítés (edzői kulcs + 431. meccsterv-szabály), 451. edzés-szabály,
  kliens-csempe.
- **Fiókok és felhasználási feltételek**: a program mostantól fiókhoz
  kötött, és az első használat előtt el kell fogadni a felhasználási
  feltételeket. A feltételek kimondják, hogy a Sport Machine szoftver — a
  forráskód, az elemző eljárások és modellek, a felület, a nevek és a
  megjelenés — a Tulajdonos kizárólagos **szellemi tulajdona**, a program
  példányai és a hozzá adott eszközök pedig a **fizikai tulajdonát**
  képezik; a felhasználó csak korlátozott, át nem ruházható, bármikor
  visszavonható használati engedélyt kap (másolás, terjesztés,
  továbbadás, visszafejtés, származékos mű tilos). A fiókok a saját gépen,
  a program adatmappájában készülnek (nincs felhő), a jelszó sose
  tárolódik nyíltan — csak PBKDF2-HMAC-SHA256 lenyomatként, egyedi sóval;
  a belépés 90 napig érvényes munkamenet-kulcsot ad, így nem kell minden
  indításnál újra belépni. A feltételek verziózottak: ha a szöveg
  megújul, a belépés után újra el kell fogadni, és az elfogadás verziója
  + időpontja a fiókban marad. Felületek: fiók-kapu a motor indulása után
  (belépés / fiók létrehozása a feltételek elfogadásával), teljes jogi
  szöveg olvasó nézetben, fiók-menü a felső sávban (feltételek, kilépés),
  motor nélküli demó módban rövid tulajdonjogi tudomásulvétel. Végpontok:
  `/legal/terms`, `/accounts/status|register|login|me|accept-terms|
  logout|change-password`.
- **Védekezési formáció-biztosság**: MENNYIRE ÁLLANDÓ a faluk alakja. A
  leggyakoribb forma (`most_common_formations`) megnevezi a falat, de nem
  mondja meg, mennyire tartják — pedig egy 95%-ban tartott 6-0 és egy
  40%-ban tartott 6-0 két különböző ellenfél. A réteg a felállt védekezés
  kockáit a projekt EGYETLEN forma-osztályozójával címkézi (6-0 / 5-1 /
  4-2 / 3-2-1 / 3-3), és a részarányból ítél: 100+ kockától nevez meg
  formációt, ha a leggyakoribb alak eléri az 50%-ot — különben a
  "váltogatnak" maga az információ. Edzői olvasat: a 6-0 ellen a távoli
  lövés és a gyors oldalváltás (a fal nem lép ki), az 5-1 ellen a kitolt
  védő MÖGÖTTI tér (kettős elzárás mellette, a beálló a háta mögé), a
  3-2-1 ellen a szélek és a gyors keresztmozgás, a 4-2 ellen a két
  kilépő mögötti és közötti tér; ha nincs állandó alak, a felismerés a
  feladat (a felhozó mondja be a formát, két kész figurasorral).
  Saját olvasatban a 80% feletti egy-alakúság kiszámíthatóság — a
  második fal-alakot is be kell gyakorolni. Felületek: /analyze +
  meccs-csomag, edzői összefoglaló, felderítés (edzői kulcs + 429.
  meccsterv-szabály), 449. edzés-szabály, kliens-csempe.
- **Kezesség-becslés**: MELYIK KÉZZEL lőnek a lövőik — az elengedés
  előtti kockán a labda a lövő testéhez képest a dobó kéz oldalán van;
  a kapu-irányhoz mért oldal-eltolás előjele lövésenként megmondja a
  kezet, játékosonként összesítve a kezességet (4+ értékelhető lövés,
  70%+ egyoldalúság). Edzői olvasat: a balkezes lövő a védelemnek
  tükör-feladat — a sánc a másik kezét emelje, a kapus alapállása a
  túlsó sarokra álljon, és a jobb oldalról befelé jövő útját kell
  elzárni; saját olvasatban a balkezes a jobbszélső/jobbátlövő poszt
  fegyvere, a hozzá menő passz a bal kezéhez érkezzen. Felületek:
  /analyze + meccs-csomag, edzői összefoglaló, felderítés (edzői kulcs
  + 428. meccsterv-szabály), 448. edzés-szabály, prioritások
  (ember-család + Kulcs-ember), kliens-csempe.
- **Meccs-ablak: a bemelegítés és a nem-meccs részek kimaradnak**
  (motor): a feltöltött felvételben gyakran benne van a bemelegítés, a
  meccs előtti ceremónia és a lefújás utáni rész is — eddig ezek is
  "meccsnek" számítottak (a bemelegítő kapura lövés gólnak látszott,
  az üres percek felhígították az idő-alapú mutatókat). A feldolgozás
  mostantól megkeresi a tényleges játék első és utolsó jelét (elég
  játékos a pályán, a két csapat EGY kapu körül — bemelegítésnél
  ki-ki a sajátjánál —, és tényleges mozgás), és a felvétel nem-meccs
  éleit levágja; a félidei szünet-sávba eső "lövéseket/gólokat"
  (kapus-bemelegítés, labdaszedők) pedig az eseménydetektor szűri ki.
  A videó-időzítés (jelenet-lejátszás, klipek) változatlanul pontos, a
  félidő-felismerés és a térfélcsere-normalizálás érintetlen.
- **Egálbontó emberek**: KI viszi el góllal a holtpontjaikat — a
  holtpont-mérleg ember-ikre: a döntetlen állásról szerzett (egált
  bontó) gólokat emberre bontja; akinél a zömük landol (2+, 50%+), ő
  a holtpont-ember. Edzői olvasat: egálnál az ő kivétele az első
  dolog — szoros fogás, korai kettőzés, a kedvenc befejezése
  letiltva; a saját csapatnak a holtpont ne egy emberen álljon — a
  második és harmadik opció is merje vállalni a döntést. Felületek:
  /analyze + meccs-csomag, edzői összefoglaló, felderítés (edzői
  kulcs + 427. meccsterv-szabály), 447. edzés-szabály, prioritások
  (ember-család + Kulcs-ember), kliens-csempe.
- **Befutó emberek**: KI a második hullám embere a kontráikban — a
  kontra-hullámok ember-ikre: a második hullámos (nem a legelöl futó
  által lőtt) kontra-befejezéseket emberre bontja; akinél a zömük
  landol (2+, 50%+), ő a befutó ember. Edzői olvasat: a visszafutásnál
  őt kell megtalálni — az első ember felvétele után nem szabad
  megállni, a középső sávot kell feltölteni; a saját csapatnak az egy
  befutóra épülő kontra kiszámítható — két sávból, változó időzítéssel
  kell befutni. Felületek: /analyze + meccs-csomag, edzői
  összefoglaló, felderítés (edzői kulcs + 426. meccsterv-szabály),
  446. edzés-szabály, prioritások (ember-család + Kulcs-ember),
  kliens-csempe.
- **Az azonnali indítás tényleg azonnal indul** (motor): a "kezdje
  most" választásnál az új elemzés eddig a soros munkáson várta végig
  a félretett munka utómunkáját/mentését (ami perceket — beragadt
  feldolgozásnál korábban akár örökké — tartott). Mostantól az új
  elemzés saját szálon AZONNAL indul, a félretett munka a háttérben
  menti az addig kész részt (félbehagyott elemzésként a könyvtárba
  kerül); a "megvárja az előzőt" választás viselkedése változatlan.
- **Elemzés-könyvtár a meccs-elemzőben** (kliens): új gomb a
  meccs-képernyő eszközsorában — fülekkel (Mind · Befejezett ·
  Félbehagyott), megnyitással és törléssel; a félbehagyott elemzés
  jelölést kap, és innen is megnyitható vagy törölhető, nem csak a
  dashboardról.
- **Leforduló beállók**: MELYIK beálló kapja mozgásból a labdát — a
  beálló-futtatás ember-ikre: a mozgásból (elzárásból lefordulva)
  hozott beálló-átvételeket emberre bontja; akinél a zömük landol
  (2+, 50%+), ő a lefordulós játék címzettje. Edzői olvasat: nála a
  bejátszás ELŐTT kell elé lépni (hangos váltás, passzsáv-zárás a
  lefordulás előtt) — az átvétel utáni birkózás késő; a saját
  csapatnak az egy beállóra épülő lefordulás kiszámítható — több
  vállra, több emberre kell variálni. Felületek: /analyze +
  meccs-csomag, edzői összefoglaló, felderítés (edzői kulcs + 425.
  meccsterv-szabály), 445. edzés-szabály, prioritások (ember-család
  + Kulcs-ember), kliens-csempe.
- **Videó-lejátszás Windowson** (kliens): a jelenet-lejátszó eddig
  csak macOS/iOS/Android alatt működött, Windowson tájékoztató
  szöveg volt helyette — mostantól Windowson is játszik (media_kit /
  libmpv lejátszóval), ugyanazzal a felülettel: eseményre kattintva
  a jelenetre ugrik, ±5 mp, lejátszás/megállítás, és a videókép itt
  is nagyítható (csippentés / Ctrl+görgő).
- **Beragadás-javítás a kockánkénti dúsítóknál** (motor): terepen
  látott hiba — a feldolgozás úgy állt meg örökre ("X perce nincs
  előrelépés"), hogy az elakadás-átugró sem lépett működésbe. Ok: az
  átugró csak a videó-olvasást/fő detektálást védte, a kockánkénti
  dúsítók (mezszám-OCR, labda-újrakeresés) beragadása ellen nem volt
  őr — ráadásul az újrakeresés a közös modellt hívta párhuzamosan a
  termelő szállal, ami maga is befagyást okozhat. Javítás: minden
  dúsító hívás időkorláttal fut (beragadásnál kihagyjuk, 3 beragadás
  után a dúsító kikapcsol és a fő feldolgozás megy tovább — a
  felület értesül), és a labda-újrakeresés saját modell-példányt
  kapott.
- **Keresztjáró emberek**: KIN keresztül fut a keresztjáték — minden
  hátsó-sori oldalcserénél a helyet cserélő játékosokat írjuk fel;
  akin a keresztek 60%-a átfut (3+ kereszt, holtverseny nélkül), ő a
  keresztjáték motorja. Edzői olvasat: az ő sávjában kell a hangos,
  korai váltás; a saját csapatnak az egy emberre épülő kereszt
  kiszámítható — variálni kell. Felületek: /analyze + meccs-csomag,
  edzői összefoglaló, felderítés (edzői kulcs + 424. meccsterv-
  szabály), 444. edzés-szabály, prioritások (ember-család +
  Kulcs-ember), kliens-csempe.
- **Nagyítható nézetek** (kliens): a pálya-nézet (meccs-képernyő és
  élő nézet) és a jelenet-videó nagyítható — touchpadon két ujjas
  csippentéssel, egérrel Ctrl+görgővel (a kurzor, illetve a
  csippentés középpontja körül), két ujjas húzással mozgatható,
  dupla kattintásra visszaáll. A sima görgő viselkedése nem változik,
  a játékos-kijelölés nagyítva is pontos marad.
- **Futtatott szélsők** (ember-réteg): MELYIK szélső kapja lendületből
  a labdát — a szélső-futtatás (wing_service) ember-ikre, a lendületes
  szélső-átvételeket emberre bontja. Edzői olvasat: a futtatott szélső
  ellen nem a kifutás véd, hanem a futópassz-sáv zárása — és azt az ő
  oldalán kell begyakorolni; a saját csapatnak: az egy szélsőre járó
  futtatás kiszámítható, mindkét szélre kell variálni. Felületek:
  /analyze + meccs-csomag (`wing_runners`), edzői összefoglaló,
  felderítés (edzői kulcs + 423. meccsterv-szabály a labdaszerzéssel
  párosítva), 443. edzés-szabály, prioritás-regiszter (ember-család +
  Kulcs-ember lencse), kliens-csempe.

## v0.1.28 — kiadva (2026-08-14)

> Kiadás-jegyzet: a v0.1.27 óta a kör vezérfonala az EMBER- és a
> HOZAM-lencse kiteljesítése volt, két új szintézissel.
>
> **(1) Tizenhat néven nevező EMBER-réteg.** A poszt-lencse rétegek
> ember-szintű párjai sorra elkészültek: Kettőzött emberek,
> Ziccerhagyók, Fáradt lövők, Lágy passzolók, Passzív-birtoklók,
> Előkészítő emberek, Válaszoló emberek, Rajt-emberek, Újrakezdő
> emberek, Előnyben-emberek, Elzárt védők, 7a6-befejezők — mind a
> Kulcs-ember bizonyíték-rétegei közé is bekerült. A Kulcs-ember
> küszöbe közben a lencse méretével nő (a padló és a lista tizede
> közül a nagyobbik), így a bővülő lista nem hígítja a szintézist.
>
> **(2) Kilenc HOZAM-mérés.** Mennyit ér egy-egy játékelem:
> Csere-hozam, Kapus-visszaérés, Figura-kopás, Futómunka-eloszlás,
> Kapus a kapott gól után, Hetes-forrás, Kontroll-idővonal,
> Gólpassz-duó, Időkérés-hozam, Kapuscsere-hozam,
> Emberhátrány-túlélés, Középkezdés-hozam — ezek árazzák be a
> cserét, az időkérést, a kapuscserét, a kétperc-védekezést és a
> gól utáni újraindítást.
>
> **(3) Két új szintézis és okosabb lapok.** Az Ellenszer-lap minden
> teendőhöz hozzárendeli a kész edzés-gyakorlatot (és őszintén
> jelzi, mire nincs válasz); a Stílus-távolság megmondja,
> tükör-meccs jön-e vagy stílus-ütközés — a meccsterv-lap élére
> került, és a kliens MECCSTERV kártyáján is látszik. A meccsterv
> mondatai téma szerint rendeződnek (kapus → védekezés → támadás →
> fegyelem → hajrá), a jelentés pedig három új táblát kapott:
> Hozam-lencse, Ember-lencse és a bővített lencse-sorok.
>
> **(4) Gyorsabb és változatlanul őszinte.** A teendő-rangsor és az
> edzés-fókusz meccsenként egyszer számolódik (memoizálás
> védő-másolattal) — az ellenszer-lap ára 2,7 mp-ről 0,7 mp-re
> esett; minden réteg kevés mintánál hallgat, és a kiadás előtt
> lefutott a lassú sorrend-jelentés: 470 rétegből 0 sorrend-függő.
>
> Számokban: 470 elemző réteg, 422 meccsterv-szabály, 442
> edzés-szabály, 443 kliens-csempe, 1674 zöld teszt.


- **Középkezdés-hozam: gólra váltják-e a gól utáni újraindítást.** A
  középkezdés-tempó azt méri, milyen gyorsan hozzák játékba a labdát
  a kapott gól után — az új réteg azt, mit ér: minden kapott góljuk
  után megnézi, szereznek-e saját gólt 25 másodpercen belül.
  Edzőileg: aki a kapott gólra rendre azonnali góllal válaszol, az
  ellen a gól utáni ünneplés tilos — kijelölt fékező ember középen,
  azonnali visszarendeződés, mert a legolcsóbb gólokat az ünneplő fal
  kapja; akinél az újraindítás üresjárat, ott a saját gól után
  nyugodtan rendezhető a fal. Saját csapatra a gyors középkezdés-rutin
  az edzés-téma. Négy mért újraindítástól ítél. A rangsorban a
  "felkészülés" családba tartozik. Felületek: /analyze + meccs-csomag
  (`restart_yield`), edzői összefoglaló, felderítés (`rsy_restarts` /
  `rsy_answered` mezők + edzői kulcs + 422. meccsterv-szabály),
  edzés-fókusz (442. szabály), kliens-csempe.

- **Emberhátrány-túlélés: mit ér ellenük az emberelőny.** Az
  emberelőny-hozam a nyertes oldalt nézi — az új réteg a büntetett
  oldalt: a hátrányban töltött időre vetíti a hátrányban kapott
  gólokat (gól / két perc hátrány). Edzőileg ez az emberelőny-terv
  címzettje: ha hátrányban beszakadnak, a kiállításukat végig kell
  büntetni (türelmes, zárt figurák — az idő nekik fáj); ha hátrányban
  is állnak, a kettős fölény ellenük keveset ér — emberelőnyben is az
  1v1 és a betörés dolgozik. Saját csapatra a hátrány-védekezés
  (zárt 5-ös fal, időhúzás) az edzés-téma. Kilencven másodperc mért
  hátránytól ítél. A rangsorban az "ár" családba tartozik, és a
  jelentés Hozam-lencséjébe is bekerült. Felületek: /analyze +
  meccs-csomag (`shorthanded_survival`), edzői összefoglaló,
  felderítés (`shs_seconds` / `shs_conceded` mezők + edzői kulcs +
  421. meccsterv-szabály), edzés-fókusz (441. szabály),
  kliens-csempe.

- **A Hozam-lencse a mai új rétegeket is hozza.** A meccs-jelentés
  Hozam-lencse táblája kiegészült a Hetes-forrás, a Gólpassz-duó, a
  Kapuscsere-hozam és az Időkérés-hozam ítéleteivel — az
  ár-kalkulációs kép így a friss rétegekkel együtt teljes.

- **Kapuscsere-hozam: fordít-e a kapuscseréjük.** A kapuscsere-hatás
  a nyers védés-változást adja — az új réteg az ítéletet: a csere
  utáni védés-százalék változásából mondja ki, hogy a második kapus
  mentőöv-e. Edzőileg ez a lövő-terv B-lapja: ha a cseréjük rendre
  fordít, a lövő-tervet a második kapusra is el kell készíteni, és a
  beállása utáni első percekben kell büntetni, amíg hideg; ha a csere
  sem segít, az első kapus megingása után nincs mentőövük — nyomni
  kell tovább ugyanazt. Saját csapatra a második kapus beállás-rutinja
  az edzés-téma. Tizenöt százalékpontos változástól ítél. A rangsorban
  a "felkészülés" családba tartozik. Felületek: /analyze +
  meccs-csomag (`gk_change_yield`), edzői összefoglaló, felderítés
  (`gcy_changes` / `gcy_delta_dpp` mezők + edzői kulcs + 420.
  meccsterv-szabály), edzés-fókusz (440. szabály), kliens-csempe.

- **Időkérés-hozam: működik-e a mentő időkérésük.** Az
  időkérés-mérleg a nyers számokat adja — az új réteg az ítéletet: a
  megtört sorozatok arányából mondja ki, hogy az időkérésük rendez-e.
  Edzőileg ez a sorozat-építés terve: ha az időkérésük rendre megtöri
  a sorozatot, utána nem szabad kapkodni (rendezett fal jön); ha
  hatástalan, a megkezdett gól-sorozat a zöld karton után is tolható.
  Saját csapatra a hatástalan időkérés tartalom-kérdés: egy kimondott
  első támadás, egy védekezés-igazítás — nem általános buzdítás. Két
  ítéletes időkéréstől és 67%-os aránytól mond ítéletet. A rangsorban
  a "felkészülés" családba tartozik. Felületek: /analyze +
  meccs-csomag (`timeout_yield`), edzői összefoglaló, felderítés
  (`toy_broke` / `toy_failed` mezők + edzői kulcs + 419.
  meccsterv-szabály), edzés-fókusz (439. szabály), kliens-csempe.

- **Gólpassz-duó: melyik kettősön fut a gólgyártásuk.** A
  gólpassz-hálózat minden párost felsorol — az új réteg az ítéletet:
  ha az asszisztos gólok nagy része ugyanazon az (adó → befejező)
  kettősön születik, a duó bejáratott gólgyár. Edzőileg a duó ellen
  párban kell védekezni: az adót testtel, a kettejük passzsávját
  beleéréssel — ha a sáv zárva, a gépezet áll, mert a befejező
  magától nem teremt ugyanennyit. Saját csapatra: a bejáratott duó
  kiszámíthatóság is, kell egy második gól-tengely. Két közös góltól
  és az asszisztos gólok 40%-ától ítél. A rangsorban a "felkészülés"
  családba tartozik (kettőst nevez meg, ezért se a Kulcs-ember, se a
  Kulcs-páros poszt-lencséjébe nem való). Felületek: /analyze +
  meccs-csomag (`assist_duos`), edzői összefoglaló, felderítés
  (`adu_goals_by_duo` mező + edzői kulcs + 418. meccsterv-szabály),
  edzés-fókusz (438. szabály), kliens-csempe.

- **7a6-befejező emberek: kire fut ki a hetedik ember játéka.** A
  7a6-befejező poszt a posztot nevezi meg — az új réteg az embert: a
  felismert üres-kapus szakaszaik alatt leadott lövéseket a lövő
  nevéhez írja. Edzőileg a 7 a 6 értelme a túlterhelés — a plusz
  mezőnyjátékos valakit felszabadít; ha ez rendre ugyanaz az ember, a
  lehozott kapus felismerésekor a védekezés első dolga ŐT megtalálni
  és besűríteni a sávját — a hetedik ember játéka kiszámítható, és
  minden megvárt másodperc nekik kockázat. Saját csapatra: a 7 a
  6-nak két kifutása legyen. Két 7a6-lövéstől és a lövések felétől
  emel ki nevet. A rangsorban az "ember" családba tartozik, és a
  Kulcs-ember bizonyíték-rétegei közé is bekerült. Felületek:
  /analyze + meccs-csomag (`seven_six_finishers`), edzői
  összefoglaló, felderítés (`en7p_shots_by_player` mező + edzői kulcs
  + 417. meccsterv-szabály), edzés-fókusz (437. szabály),
  kliens-csempe.

- **Elzárt védők: ki akad el az elzárásokban.** Az elzárt-poszt a
  posztot nevezi meg — az új réteg az embert: lövésenként megkeresi a
  lövő őrzőjét és a mellé állított elzárót, és az elakadt őrző
  nevéhez írja az esetet. Edzőileg ez az elzárás-célpont terve névre
  szólóan: akire a zárás rendre ráragad, oda kell vinni a figurákat —
  az ő oldalán a zárás tisztán hagyja a lövőt. Saját csapatra: neki
  átcsúszás- és váltás-gyakorlás kell hangos kommunikációval — az
  elakadás nem alkat, hanem technika kérdése. Két elakadástól és az
  elakadások felétől emel ki nevet. A rangsorban az "ember" családba
  tartozik, és a Kulcs-ember bizonyíték-rétegei közé is bekerült.
  Felületek: /analyze + meccs-csomag (`screened_defenders`), edzői
  összefoglaló, felderítés (`sdp_screens_by_player` mező + edzői
  kulcs + 416. meccsterv-szabály), edzés-fókusz (436. szabály),
  kliens-csempe.

- **Előnyben-emberek: ki viszi a játékot vezetésnél.** Az
  előnyben-poszt a posztot nevezi meg — az új réteg az embert: a
  saját vezetés közben lőtt gólokat a lövő nevéhez írja. Edzőileg ez
  a lendület-törés terve hátrányban, névre szólóan: ha ők vezetnek,
  és az előny-tartásuk egy emberen áll, az ő kivétele (szoros fogás,
  kettőzés) töri meg a lendület-tartásukat — a felzárkózásra ez a
  leggyorsabb út. Saját csapatra: a vezetés-tartás ne egy emberen
  álljon. Két vezetésnél lőtt góltól és a gólok felétől emel ki
  nevet. A rangsorban az "ember" családba tartozik, és a Kulcs-ember
  bizonyíték-rétegei közé is bekerült. Felületek: /analyze +
  meccs-csomag (`lead_scorers`), edzői összefoglaló, felderítés
  (`lgp_goals_by_player` mező + edzői kulcs + 415.
  meccsterv-szabály), edzés-fókusz (435. szabály), kliens-csempe.

- **Újrakezdő emberek: ki viszi a szünet utáni rajtot.** Az
  újrakezdő-poszt a posztot nevezi meg — az új réteg az embert: a
  második félidő első tíz percének góljait a lövő nevéhez írja.
  Edzőileg ez a szünet utáni párosítás terve névre szólóan: sok
  csapat a szünetben beszéli meg, kire építi az újrakezdést — ha az
  rendre ugyanaz az ember, a második félidő elején ŐT kell a legjobb
  védővel megfogni. Saját csapatra: a második félidei nyitó-megoldás
  ne egy emberen álljon. Két szünet utáni góltól és a gólok felétől
  emel ki nevet; félidő-jel nélkül hallgat. A rangsorban az "ember"
  családba tartozik, és a Kulcs-ember bizonyíték-rétegei közé is
  bekerült. Felületek: /analyze + meccs-csomag
  (`second_start_scorers`), edzői összefoglaló, felderítés
  (`ssp_goals_by_player` mező + edzői kulcs + 414.
  meccsterv-szabály), edzés-fókusz (434. szabály), kliens-csempe.

- **Rajt-emberek: ki viszi a meccs elejét.** A rajt-poszt a posztot
  nevezi meg — az új réteg az embert: a meccs első tíz percének
  góljait a lövő nevéhez írja. Edzőileg ez a meccs eleji párosítás
  terve névre szólóan: az első tíz percben ŐT kell a legjobb védővel
  megfogni — a korai elhúzásuk motorja nélkül a nyitás kiegyenlített
  marad. Saját csapatra: az egy emberre épülő rajt kockázat, kell a
  második nyitó-megoldás. Két nyitó-góltól és a nyitó-gólok felétől
  emel ki nevet. A rangsorban az "ember" családba tartozik, és a
  Kulcs-ember bizonyíték-rétegei közé is bekerült. Felületek:
  /analyze + meccs-csomag (`opening_scorers`), edzői összefoglaló,
  felderítés (`osp_goals_by_player` mező + edzői kulcs + 413.
  meccsterv-szabály), edzés-fókusz (433. szabály), kliens-csempe.

- **Válaszoló emberek: kapott gól után ki válaszol.** A válasz-poszt
  a posztot nevezi meg — az új réteg az embert: a kapott gólt egy
  percen belül követő saját gólokat a lövő nevéhez írja. Edzőileg ez
  a saját gólunk utáni első védekezés terve névre szólóan: a gólunk
  után azonnal az ő fogására kell váltani (kiemelt őrzés, korai
  kettőzés) — a lendületük ott törik meg, ahol elindulna. Saját
  csapatra: ha a válasz egy emberen áll, a bekapott gól után
  kiszámíthatók vagyunk. Két válasz-góltól és a válasz-gólok felétől
  emel ki nevet. A rangsorban az "ember" családba tartozik, és a
  Kulcs-ember bizonyíték-rétegei közé is bekerült. Felületek:
  /analyze + meccs-csomag (`response_scorers`), edzői összefoglaló,
  felderítés (`rspp_goals_by_player` mező + edzői kulcs + 412.
  meccsterv-szabály), edzés-fókusz (432. szabály), kliens-csempe.

- **Előkészítő emberek: ki készíti elő a lövéseiket.** Az
  előkészítő-poszt a posztot nevezi meg — az új réteg az embert:
  minden felismert lövéshez megkeresi a lövő felé menő utolsó
  passzt, és a lövést a PASSZOLÓ nevéhez írja (a gólpassz-listával
  szemben itt minden lövés számít, nem csak a beérett gólok).
  Edzőileg ez a passzsáv-zárás címzettje: nem a lövőt kell fogni,
  hanem a kiszolgálót — az ő átadás-vonalainak elvágásával a lövőik
  előkészítetlenül maradnak. Saját csapatra a második előkészítő
  kinevelése az edzés-téma. Négy előkészítéstől és az előkészítések
  felétől emel ki nevet. A rangsorban az "ember" családba tartozik, és
  a Kulcs-ember bizonyíték-rétegei közé is bekerült. Felületek:
  /analyze + meccs-csomag (`last_passers`), edzői összefoglaló,
  felderítés (`epp_passes_by_player` mező + edzői kulcs + 411.
  meccsterv-szabály), edzés-fókusz (431. szabály), kliens-csempe.

- **Kulcs-ember: a küszöb a lencse méretével nő.** A Kulcs-ember
  eddig négy egyező réteg fölött szólalt meg — de ahogy az
  ember-rétegek száma nőtt (mára ötven fölött), négy egyezés egyre
  kevesebbet jelentett: több lista mellett könnyebb véletlenül
  négyszer az élre kerülni. Mostantól a tényleges küszöb a padló (4)
  és a lista tizede közül a nagyobbik — kis lencsénél marad a régi
  viselkedés, a mai nagy lencsénél szigorodik (jelenleg 5 egyezés
  kell). Új őr-teszt rögzíti mindkét ágat.

- **Passzív-birtoklók: kinél hal el a felállt támadásuk.** A
  passzív-poszt a posztot nevezi meg — az új réteg az embert: a
  lövés nélküli, hosszú felállt támadások labdás kockáit a birtokos
  nevéhez írja. Edzőileg ez a passzív jelzés terve névre szólóan: a
  jelzés alatt ŐT kell nyomás alá tenni (időzített kettőzés), mert
  nála jön a kényszer-lövés vagy az eladás. Saját csapatra neki kell
  kész befejező megoldás, mielőtt a játékvezető keze felmegy.
  Kétszáz passzív labdás kockától és a passzív idő felétől emel ki
  nevet. A rangsorban az "ember" családba tartozik, és a Kulcs-ember
  bizonyíték-rétegei közé is bekerült. Felületek: /analyze +
  meccs-csomag (`passive_holders`), edzői összefoglaló, felderítés
  (`pvp_frames_by_player` mező + edzői kulcs + 410.
  meccsterv-szabály), edzés-fókusz (430. szabály), kliens-csempe.

- **Lágy passzolók: kinek a labdáiba lehet belenyúlni.** A
  lágypassz-poszt a posztot nevezi meg — az új réteg az embert: a
  lassú, ívelt passzokat a passzoló nevéhez írja. Edzőileg ez a
  beleérő védekezés címzettje: a letámadás az ő ÁTADÁSAIT célozza,
  ne a labdást szorítsa — ott a leggyorsabb a labdaszerzés. Saját
  csapatra a passz-élesség (csuklós, feszes átadás) az edzés-témája.
  Négy lágy passztól és a lágy passzok felétől emel ki nevet. A
  rangsorban az "ember" családba tartozik, és a Kulcs-ember
  bizonyíték-rétegei közé is bekerült. Felületek: /analyze +
  meccs-csomag (`soft_passers`), edzői összefoglaló, felderítés
  (`spp_soft_by_player` mező + edzői kulcs + 409. meccsterv-szabály),
  edzés-fókusz (429. szabály), kliens-csempe.

- **Fáradt lövők: kinek megy szét a lövése a második félidőre.** A
  fáradt-lövő poszt a posztot nevezi meg — az új réteg az embert: a
  kaput elkerülő (mellé/blokkolt) lövéseket félidőnként a lövő
  nevéhez írja, és megkeresi, kinek ugrik meg a pontatlansága a
  szünet után. Edzőileg ez a második félidei fal-terv névre szólóan:
  akinek fáradtan szétmegy a lövése, arra rá lehet engedni — a
  kilépés nála fölösleges kockázat, elég a lövő-vonalba állni. Saját
  csapatra fáradt célzás-blokk és a befejezés átosztása a hajrában.
  Két második félidei pontatlan lövéstől és kétszeres ugrástól emel
  ki nevet; félidő-jel nélkül hallgat. A rangsorban az "ember"
  családba tartozik, és a Kulcs-ember bizonyíték-rétegei közé is
  bekerült. Felületek: /analyze + meccs-csomag (`tired_shooters`),
  edzői összefoglaló, felderítés (`fsp_sh_by_player` /
  `fsp_fh_by_player` mezők + edzői kulcs + 408. meccsterv-szabály),
  edzés-fókusz (428. szabály), kliens-csempe.

- **Ziccerhagyó emberek: ki hagyja ki a ziccereket.** A
  ziccerhagyó-poszt a posztot nevezi meg — az új réteg az embert: a
  nagy helyzet-értékű (ziccer), gól nélkül záruló lövéseket a lövő
  nevéhez írja. Edzőileg ez a fal kockázat-kezelése névre szólóan:
  akinél a ziccer rendre kimarad, nála a helyzetbe engedés a kisebbik
  rossz — a besegítés a biztos kezű társakra menjen, a kapus pedig
  bevárhatja őt. Saját csapatra befejezés-gyakorlás jár hozzá
  (ziccer-sorozat kapussal, fáradtan is). Két kihagyástól és a
  kihagyások felétől emel ki nevet. A rangsorban az "ember" családba
  tartozik, és a Kulcs-ember bizonyíték-rétegei közé is bekerült.
  Felületek: /analyze + meccs-csomag (`missed_chance_players`), edzői
  összefoglaló, felderítés (`mcp_misses_by_player` mező + edzői kulcs
  + 407. meccsterv-szabály), edzés-fókusz (427. szabály),
  kliens-csempe.

- **Kontroll-idővonal: ki diktált ötpercenként.** A negyedóra-profil
  az EREDMÉNYT bontja szakaszokra — az új réteg a KONTROLLT:
  ötperces blokkonként megnézi, kié volt a birtoklás nagyobb része, és
  mennyi helyzetet (xG) teremtettek benne. Egy blokk akkor "övék", ha
  a birtoklásuk eléri a 60%-ot. Edzőileg: a gólkülönbség hazudhat (két
  kapus-bravúr átírja) — a kontroll-kép azt mutatja, hol kellett volna
  időkérés; ha egy csapat egymás utáni blokkokat visz, a másik
  oldalon a felállás vagy a fal nem működik. Három mért blokktól
  ítél. A rangsorban az "állás" családba tartozik. Felületek:
  /analyze + meccs-csomag (`control_timeline`), edzői összefoglaló,
  felderítés (`ctl_won` / `ctl_lost` / `ctl_blocks` mezők + edzői
  kulcs + 406. meccsterv-szabály), edzés-fókusz (426. szabály),
  kliens-csempe.

- **Stílus-távolság: tükör-meccs vagy ellentétes stílus.** A
  meccsterv-illesztés az erősség–gyengeség kereszteket adja — az új
  mérés a KÉPET: a két felderítés közös stílus-tengelyeit
  (lövés-távolság, tempó, lerohanás, elzárás, beállós játék,
  keménység) veti össze, és 0–100-as hasonlóság-pontot ad. Edzőileg:
  a tükör-meccsen a részletek döntenek (rutinok, fegyelem, kapus) —
  ott a terv nem hoz különbséget; az ellentétes stílusú meccs viszont
  arról szól, ki kényszeríti rá a sajátját, és a réteg megnevezi a
  legnagyobb szakadékot, ahol ezt meg lehet tenni. Csak KÖZÖS
  tengelyeken hasonlít (a hiányzó mérés nem hamisít egyezést), és
  négy tengely alatt hallgat. Felületek: a meccsterv-lap élére került
  405. szabályként (a téma-rendezés új "jelleg" témája keretezi a
  lapot), a `/scouting/matchup` válasz új `style` mezője, és a
  kliens MECCSTERV kártyájának fejlécében a stílus-egyezés
  százaléka.

- **Hetes-forrás: milyen helyzetből jön a hetesük.** A
  hetes-kiharcolók az embert nevezik meg, a hetes-okozók a védőt — az
  új réteg a JÁTÉKHELYZETET: minden felismert hetest ahhoz a
  támadás-szakaszhoz köt, amelyben esett, és a szakasz típusa szerint
  csoportosít (lerohanás, felállt támadás, átmenet). Edzőileg ez a
  szabálytalanság-fegyelem címzettje: ha a heteseik zöme
  lerohanásból jön, a visszafutásnál tilos a kézzel fékezés (inkább
  menjen be a gól, mint a hetes plusz kiállítás); ha felállt
  támadásból, a fal lábmunkája a kérdés. Saját csapatra fordítva
  ugyanez mutatja, honnan tudunk hetest kiharcolni. Három felismert
  hetestől és 60%-os aránytól ítél. A rangsorban a "felkészülés"
  családba tartozik. Felületek: /analyze + meccs-csomag
  (`seven_sources`), edzői összefoglaló, felderítés
  (`svs_sevens_by_type` mező + edzői kulcs + 404. meccsterv-szabály),
  edzés-fókusz (425. szabály), kliens-csempe.

- **A meccsterv téma szerint rendeződik.** A meccsterv-illesztés
  szabályai történeti sorrendben álltak a lapon (a legújabb szabály
  elöl), ami az edzőnek semmit nem jelent. Mostantól a mondatok téma
  szerint csoportosulnak, kimondott sorrendben: kapus (innen jönnek a
  legolcsóbb gólok) → védekezés → támadás → fegyelem és létszám →
  hajrá és erőnlét → egyéb; a témán belül a szabályok eredeti
  sorrendje marad (stabil rendezés, determinisztikus kimenet). Egyetlen
  mondat sem vész el, csak a sorrend lett olvasható. A témákat
  szótövek azonosítják (a magyar toldalék az utolsó magánhangzót is
  átírja, ezért pl. "kontr" és nem "kontra").

- **Kapus a kapott gól után: beesik-e, amíg friss a seb.** A
  kapus-sorozat a jó szériát méri, a kapus-hidegedés a tétlenséget —
  az új réteg a lélektant: minden rá kaputra érkező lövésnél
  megnézi, hányadik a legutóbb kapott gólja óta, és a következő két
  lövést külön vödörbe teszi. Edzőileg: ha a kapusuk a kapott gól
  után beesik, a gól UTÁNI percben kell újra lőni (gyors
  középkezdés, ugyanaz a kép, ugyanaz a sarok); ha éppen felébred
  tőle, a gól utáni kapkodás ajándék — a következő támadást ki kell
  dolgozni. Saját kapusnál ez rutin-kérdés: rögzített újraindulás a
  kapott gól után. Sávonként négy lövéstől és 15 százalékpontos
  eltéréstől ítél. A rangsorban a "fáradás" családba tartozik.
  Felületek: /analyze + meccs-csomag (`gk_after_goal`), edzői
  összefoglaló, felderítés (`gka_*` mezők + edzői kulcs + 403.
  meccsterv-szabály), edzés-fókusz (424. szabály), kliens-csempe.

- **Ember-lencse a meccs-jelentésben.** A néven nevező rétegek eddig
  csak az app csempéin és a Kulcs-ember indoklásában látszottak — most
  a nyomtatható jelentés is hoz egy táblát belőlük: melyik réteg kit
  nevez meg, csapatonként. Ez a meccsterv névsora: kit kell fogni, kit
  éheztetni, kire kell rálépni az átvételnél, kinél éri meg megvárni a
  fáradást. A lista a Kulcs-ember nyilvántartásából (KPL_LAYERS)
  épül, tehát minden új ember-réteggel magától bővül.

- **Hozam-lencse a meccs-jelentésben.** A nyomtatható meccs-jelentés
  eddig két lencse-táblát hozott (Befejező- és Védő-lencse, mindkettő
  poszt-profilokból). Most kapott egy harmadikat: a Hozam-lencse azt
  gyűjti egy helyre, MENNYIT ÉR nekik egy-egy játékelem —
  emberelőny-hozam, hetes-hozam, elzárás-hozam, 7a6 eladás,
  kapus-visszaérés, blokk-fáradás, csere-hozam, figura-kopás,
  passzív-kockázat és futómunka-eloszlás. Ez az ár-kalkuláció a
  védekezéshez és a hajrához: mennyibe kerül ellenük egy kétperc vagy
  egy hetes, és meddig működik a figurájuk. A lencse-sorokat építő
  segédfüggvény kikerült a blokkból, így mindhárom tábla ugyanazt a
  rétegenként izolált (try/except) építőt használja.

- **Futómunka-eloszlás: rövid felvételen hallgat.** A réteg pár
  másodperces felvételen is ítéletet mondott (ott az eloszlás semmit
  nem jelent) — mostantól 500 mért futott méter alatt csendben marad.

- **Gyorsabb csomag: a rangsor és az edzés-fókusz csak egyszer
  számolódik.** Az ellenszer-lap bevezetésével a teendő-rangsor és az
  edzés-fókusz kétszer futott le minden meccsnél (egyszer önálló
  rétegként, egyszer a lap párosításához). Mostantól mindkettő a
  `primitive_cache` hatókörön belül meccsenként EGYSZER számolódik, és
  minden hívó saját védő-másolatot kap — az eredmény bitre azonos, az
  ellenszer-lap ára viszont 2,7 mp-ről 0,7 mp-re esett (60 mp-es
  szimulált meccsen). Két új őr-teszt rögzíti, hogy a rangsor
  hatókörön belül egyszer fut, és hogy a másolat módosítása nem
  szennyezi a gyorsítótárat.

- **Futómunka-eloszlás: hány emberre épül a futásuk.** A futás-mérleg
  a két csapatot veti össze — az új réteg a csapaton BELÜLI
  eloszlást: mekkora hányadát futja a csapat-távnak a három
  legtöbbet futó mezőnyjátékos. Edzőileg: ha a futómunka néhány
  emberre koncentrálódik, ők a hajrára elfogynak — az utolsó húsz
  percben rájuk kell vinni a tempót (kontra, gyors középkezdés az ő
  oldalukra), és a cserehullámuk után nem szabad lassítani; ha a
  futás egyenletes, tempóval nem lehet szétszedni őket, ott a
  lövés-választás és a fal minősége dönt. Saját csapatra a
  terhelés-szétosztás (kontra-futások körbeadása, csere-ritmus) az
  edzés-téma. Hat mért mezőnyjátékostól ítél, 55%-os top-3 aránytól
  jelez. A rangsorban a "fáradás" családba tartozik. Felületek:
  /analyze + meccs-csomag (`running_load_balance`), edzői
  összefoglaló, felderítés (`lbl_*` mezők + edzői kulcs + 402.
  meccsterv-szabály), edzés-fókusz (423. szabály), kliens-csempe.

- **Figura-kopás: működik-e még a figura a második ismétlésre.** A
  figura-hatékonyság azt mondja meg, melyik figurájuk veszélyes — az
  új réteg azt, meddig: minden figura ELSŐ előfordulását
  szétválasztja az ismétlésektől, és a két sávban külön számol
  gólarányt. Edzőileg ez a felismerés értéke számokban: ha az
  ismétlésre érdemben esik a hozamuk, a fal maga megoldja a
  felismerést (elég lefuttatni velük a figurát); ha az ismétlés is
  ugyanúgy gólt hoz, nem a felismerés a baj, hanem a párharc — a
  befejezőre emberfogás vagy kettőzés kell. Saját csapatra: minden
  figurához két befejezés (variáció) az edzés-téma. Sávonként négy
  figura-támadástól és 15 százalékpontos eltéréstől ítél. A
  rangsorban a "felkészülés" családba tartozik. Felületek: /analyze +
  meccs-csomag (`setplay_decay`), edzői összefoglaló, felderítés
  (`spd_*` mezők + edzői kulcs + 401. meccsterv-szabály),
  edzés-fókusz (422. szabály), kliens-csempe.

- **Ellenszer-lap: teendő → hozzá tartozó gyakorlat.** A
  teendő-rangsor megmondja, MI a baj; az edzés-fókusz azt, MIT lehet
  gyakorolni — de a kettő eddig két külön lista volt, és az edzőnek
  fejben kellett összekötnie. Az új szintézis-réteg elvégzi a
  párosítást: minden teendőhöz megkeresi a legjobban illeszkedő
  edzés-tételt (közös szótövek a címke/ítélet és a gyakorlat
  címe/indoklása között, magyar toldalékokra csonkolva), és egy
  gyakorlatot csak egyszer használ fel. Ahol nincs párja egy
  teendőnek, az őszinte jelzés: arra még nincs kész edzés-válasz, ott
  a vezetőedző döntése kell. Edzés-szabályt szándékosan NEM kapott: a
  réteg maga olvassa az edzés-fókuszt, egy oda írt szabály
  körkörös lenne. Felületek: /analyze + meccs-csomag
  (`counter_plan`), edzői összefoglaló, felderítés (`cpl_total` /
  `cpl_matched` mezők + edzői kulcs), kliens-csempe.

- **Kapus-visszaérés: milyen gyorsan ér haza a lehozott kapus.** Az
  üres kapura kapott gólok az árat mérik — az új réteg a
  mechanizmust: minden 7 a 6 szakasz vége után megméri, hány
  másodperc alatt ér vissza a kapus a kapuja körzetébe, és közben
  hány gólt kapnak. Edzőileg ez a hajrá-terv egyik legolcsóbb pontja:
  ha a kapusuk lassan ér vissza, a labdaszerzés után NEM felállni
  kell, hanem azonnal dobni — a kapu még üres. Saját csapatra a
  hazafutás edzhető (kijelölt útvonal, a hetedik mezőnyjátékos zárja
  a lövő-vonalat), és a 7 a 6 csak akkor vállalható, ha ez megy. Két
  mért szakasztól ítél, 4 másodperc fölött lassúnak minősít. A
  rangsorban az "ár" családba tartozik. Felületek: /analyze +
  meccs-csomag (`keeper_return`), edzői összefoglaló, felderítés
  (`krt_measured` / `krt_sum_ds` / `krt_conceded` mezők + edzői kulcs
  + 400. meccsterv-szabály), edzés-fókusz (421. szabály),
  kliens-csempe.

- **Kettőzött emberek: kire jár rá az ellenfelek kettőzése.** A
  kettőzött-poszt a posztot nevezi meg — az új réteg az embert: a
  kettőzött (két védővel szorongatott) labdás kockákat a birtokos
  nevéhez írja. Edzőileg ez kollektív felderítés névre szólóan: ha az
  ellenfelek rendre ugyanarra az emberükre küldik a kettőzést, a
  minta bevált recept — érdemes követni, de a kettőzés mögött kilépő
  passzsávot is zárni kell. Saját csapatra: akit rendre kettőznek,
  annak lekapcsolódó társ és begyakorolt kettőzés-elleni leadás kell,
  különben minden támadásunk rajta akad el. Hetvenöt kettőzött
  kockától és a kockák felétől emel ki nevet. A rangsorban az "ember"
  családba tartozik, és a Kulcs-ember bizonyíték-rétegei közé is
  bekerült. Felületek: /analyze + meccs-csomag (`doubled_targets`),
  edzői összefoglaló, felderítés (`dtp_frames_by_player` mező + edzői
  kulcs + 399. meccsterv-szabály), edzés-fókusz (420. szabály),
  kliens-csempe.

- **Csere-hozam: nyernek vagy vesztenek a cseréik után.** A
  csere-büntetés a lyukas cserét árazza — az új réteg a friss emberek
  hatását: a cserék utáni másfél percben összeveti a dobott és a
  kapott gólokat. Edzőileg ez a csere-pillanat menetrendje: ha a
  cseréik után rendre több gólt kapnak, mint dobnak, a csere-pillanat
  célzottan támadható (gyors középkezdés, azonnali befejezés); ha a
  cseréik után ők jönnek fel, saját időkérés vagy lassított felállás
  töri meg a lendületet. Saját csapatra a csere-fegyelem edzés-téma:
  csak saját birtoklásban cserélünk, a beérkező a helyére fut.
  Négy mért cserétől és két gólos különbségtől ítél. A rangsorban az
  "ár" családba tartozik. Felületek: /analyze + meccs-csomag
  (`substitution_yield`), edzői összefoglaló, felderítés (`sby_*`
  mezők + edzői kulcs + 398. meccsterv-szabály), edzés-fókusz (419.
  szabály), kliens-csempe.

## v0.1.27 — kiadva (2026-08-09)

> Kiadás-jegyzet: a v0.1.26 óta három vezérfonal futott.
>
> **(1) Új elemzés futó feldolgozás mellett: mostantól te döntesz.**
> Eddig egy új videó indítása MINDIG félretette az éppen futót. Most
> a program megkérdezi: megvárja az előző elemzés végét, vagy azonnal
> kezdje az újat. Várakozásnál a futó feldolgozáshoz nem nyúlunk (az
> új szépen sorba áll mögé); azonnali kezdésnél marad a régi
> viselkedés — a futó munka szelíden félrekerül, az addig
> feldolgozott része elmentve marad, és később folytatható. A
> párbeszéd a "Mégse" gombbal el is hagyható, a több videós köteg
> pedig továbbra is mindig egymás után dolgozódik fel.
>
> **(2) Tizenhárom új réteg — EMBER- és HOZAM-lencse.** Hét
> réteg néven nevez: Fáradt-eladók, Visszafutás-lemaradók,
> Fáradt-fal emberek, Indítás-vadász emberek, Kiszolgált befejezők,
> Kétperc-gyűjtők, Felhozatal-emberek — mind bekerült a Kulcs-ember
> szintézis bizonyíték-rétegei közé is. Mellettük hat mérés arról
> szól, MENNYIT ÉR egy-egy játékelem: 7a6 eladás, Elzárás-hozam,
> Blokk-fáradás, Emberelőny-hozam, Hetes-hozam és Passzív-kockázat —
> ezek árazzák be a kétpercet, a hetest, az elzárást és a türelmet,
> vagyis megmondják, hova érdemes a védekező munkát tenni.
>
> **(3) A mérési igazság változatlanul kötelező.** Minden réteg
> kevés mintánál hallgat (nincs hallgatólagos nulla), a felderítés
> csak darabszámot tárol (így meccsek közt pontosan összegződik), és
> a felületek külön-külön try/except-tel futnak — egy réteg hibája
> nem viszi el a többit. A kiadás előtt lefutott a lassú
> sorrend-jelentés is: 445 rétegből 0 sorrend-függő.
>
> Számokban: 445 elemző réteg, 397 meccsterv-szabály, 418
> edzés-szabály, 418 kliens-csempe, 1616 zöld teszt.


- **Új elemzés futó feldolgozás mellett: mostantól te döntesz.**
  Eddig egy új videó indítása mindig félretette az éppen futót. Most
  a program megkérdezi: *megvárja az előző elemzés végét*, vagy
  *azonnal kezdje az újat*. A várakozásnál a futó feldolgozáshoz nem
  nyúlunk, az új szépen sorba áll mögé; az azonnali kezdésnél marad a
  régi viselkedés — a futó munka szelíden félrekerül, az addig
  feldolgozott része elmentve marad, és később folytatható. A
  párbeszéd a "Mégse" gombbal el is hagyható. A több videós köteg
  (pl. két félidő) továbbra is mindig egymás után dolgozódik fel.
  Felületek: `/matches/process` új `queue_behind` mezője, kliens
  párbeszéd az indítás előtt.

- **Passzív-kockázat: mennyire futnak bele a passzív jelbe.** A
  passzív-kockázatú szakaszok eddig csak listaként léteztek — az új
  réteg az arányt adja: a lövés nélkül elnyúló felállt támadásokat az
  összes felállt támadáshoz viszonyítja. Edzőileg ez a türelem
  jutalma: ha rendszeresen belefutnak a passzív jelbe, ellenük a
  zárt, türelmes fal dolgozik — nem kell kilépni és kockáztatni, az
  óra és a játékvezető a szövetségesünk. Saját csapatra: a lövés
  nélkül elnyúló támadás nem stílus, hanem befejezés-hiány, a második
  hullámnak befejezés-lehetőséggel kell érkeznie. Négy felállt
  támadástól és 20%-os aránytól ítél. A rangsorban a "felkészülés"
  családba tartozik. Felületek: /analyze + meccs-csomag
  (`passive_risk`), edzői összefoglaló, felderítés (`psr_positional`
  / `psr_passive` mezők + edzői kulcs + 397. meccsterv-szabály),
  edzés-fókusz (418. szabály), kliens-csempe.

- **Hetes-hozam: mennyit ér náluk egy megítélt hetes.** A
  hétméteres-mérleg eddig csak a nyers számokat adta — az új réteg az
  ítéletet: a felismert hetesek gólarányát méri, és megmondja, mit ér
  ellenük a hetest érő szabálytalanság. Edzőileg ez a védekezés
  ár-kalkulációja: ha a heteseik szinte mindig bemennek, a hetest érő
  szabálytalanság a legrosszabb üzlet (lábbal védekező fal, a beugró
  elé testtel, nem kézzel); ha a hetesük megfogható, a biztos
  helyzetet megállító szabálytalanság vállalható, és a kapusnak külön
  készülnie kell rá. Saját csapatra: a hetes-értékesítésünk mérhető,
  és 60% alatt edzés-téma (fix rutin, fáradtan gyakorolt hetes). Négy
  mért hetestől ítél. A rangsorban a "felkészülés" családba tartozik.
  Felületek: /analyze + meccs-csomag (`seven_yield`), edzői
  összefoglaló, felderítés (`svy_attempts` / `svy_goals` mezők +
  edzői kulcs + 396. meccsterv-szabály), edzés-fókusz (417.
  szabály), kliens-csempe.

- **Emberelőny-hozam: megbüntetik-e a kiállítást.** Az
  emberelőny-hatékonyság eddig csak a nyers számokat adta — az új
  réteg az ítéletet: összeveti a kaputra tartó lövések gólarányát
  emberelőnyben és egyenlő létszámnál. Edzőileg ez rangsorolja a
  fegyelmet: ha emberelőnyben érdemben jobban fejeznek be, ellenük a
  kétperc a legdrágább hiba (lábbal védekező fal, taktikai
  szabálytalanság nélkül); ha nem, a két perc ellenük olcsó, a
  szükséges taktikai megállítás vállalható. Saját csapatra az
  emberelőny-figurák hozama mérhető, nem érzés kérdése. Sávonként
  négy kaputra tartó lövéstől és 15 százalékpontos különbségtől ítél.
  A rangsorban az "ár" családba tartozik. Felületek: /analyze +
  meccs-csomag (`powerplay_yield`), edzői összefoglaló, felderítés
  (`ppy_*` mezők + edzői kulcs + 395. meccsterv-szabály),
  edzés-fókusz (416. szabály), kliens-csempe.

- **Blokk-fáradás: elfogy-e a blokk-munka a második félidőre.** A
  blokkolt lövések rétege a darabszámot adja — az új réteg a
  kitartást: félidőnként elosztja a blokkokat az ellenfél
  lövés-kísérleteivel (blokk + kaputra jutott lövés), így a mennyiség
  nem torzít, ha az egyik félidőben többet lőttek rájuk. Edzőileg a
  blokk tiszta akarat-munka: ha a második félidőre érdemben
  visszaesik, az utolsó húsz percben tudatosan az átlövésre kell
  építeni — ott már nem lépnek a lövő-vonalba; ha viszont a hajrára
  nő, a végén a bejátszás és a kiugratás a megoldás. Saját csapatra a
  blokkoló emberek pihentetése és a lábmunka-állóképesség az
  edzés-téma. Félidőnként öt lövés-kísérlettől és 10 százalékpontos
  eltéréstől ítél. A rangsorban a "fáradás" családba tartozik.
  Felületek: /analyze + meccs-csomag (`block_fade`), edzői
  összefoglaló, felderítés (`blf_*` mezők + edzői kulcs + 394.
  meccsterv-szabály), edzés-fókusz (415. szabály), kliens-csempe.

- **Elzárás-hozam: megéri-e nekik az elzárás.** Az elzárás-használat
  a gyakoriságot méri — az új réteg a hozamot: az őrzött lövéseket
  két sávra bontja (elzárásból lőtt vagy tisztán), és sávonként
  számol gólarányt. Edzőileg ez dönti el, hova megy a védekező
  munka: ha az elzárásos lövéseik érdemben jobban mennek be, a
  váltás-kommunikáció (hangos váltás, átcsúszás) a meccs kulcsa — az
  elzárás megtörése többet ér, mint a lövő szorítása; ha az
  elzárásból ugyanannyi vagy kevesebb gól esik, hagyni kell őket
  elzárni és a lövő-vonalra menni. Saját csapatra: az elzárás-játék
  hozama mérhető, nem hitkérdés. Sávonként négy lövéstől és 15
  százalékpontos különbségtől ítél. A rangsorban a "felkészülés"
  családba tartozik. Felületek: /analyze + meccs-csomag
  (`screen_yield`), edzői összefoglaló, felderítés (`scy_*` mezők +
  edzői kulcs + 393. meccsterv-szabály), edzés-fókusz (414. szabály,
  mindkét irányban), kliens-csempe.

- **Felhozatal-emberek: kire hozzák fel a labdát a kaputól.** A
  felhozatal-posztok a posztot nevezik meg — az új réteg az embert: a
  kapus-indítások célpontjait névre bontva összegzi. Edzőileg ez a
  letámadás címzettje: ha a felhozataluk egy emberen megy át, a
  letámadásnál ŐT kell fogni (rálépés az átvételnél, a visszapassz
  sávjának lezárása), mert nála akad meg az egész kihozatal. Saját
  csapatra: ha a labda mindig ugyanahhoz megy, az ellenfél egy
  emberrel megfogja a kihozatalunkat — kell második és harmadik
  felkínálás is. Három átvételtől és az indítások felétől emel ki
  nevet. A rangsorban az "ember" családba tartozik, és a Kulcs-ember
  bizonyíték-rétegei közé is bekerült. Felületek: /analyze +
  meccs-csomag (`outlet_targets`), edzői összefoglaló, felderítés
  (`otp_outlets_by_player` mező + edzői kulcs + 392.
  meccsterv-szabály), edzés-fókusz (413. szabály), kliens-csempe.

- **Kétperc-gyűjtők: ki ül ki náluk a legtöbbször.** A kiülő-poszt
  a posztot nevezi meg — az új réteg az embert: a felismert
  kiállításokat a kiülő játékos nevéhez összegzi. Edzőileg ez a
  szabályok adta erőforrás: akinél már két kétperc van, egy lépésre
  áll a kizárástól — rá kell vinni a játékot (betörés az ő sávjába,
  elzárás rá), mert vagy fékezve véd, vagy elmegy a meccs hátralévő
  részére. Saját csapatra: ha a kétperceink egy emberre gyűlnek, az
  nem pech, hanem rendszer-hiba (hiányzó besegítés, későn kezdett
  párharcok). Két kiállítástól emel ki nevet. A rangsorban az "ember"
  családba tartozik, és a Kulcs-ember bizonyíték-rétegei közé is
  bekerült. Felületek: /analyze + meccs-csomag
  (`suspension_collectors`), edzői összefoglaló, felderítés
  (`stc_susp_by_player` mező + edzői kulcs + 391. meccsterv-szabály),
  edzés-fókusz (412. szabály), kliens-csempe.

- **Kiszolgált befejezők: ki él a bejátszásokból.** A kiszolgált-
  poszt a posztot nevezi meg — az új réteg az embert: minden gólnál
  megnézi, volt-e gólpassz, és a befejező nevéhez írja. Edzőileg ez
  dönti el, mit kell ellene tenni: aki a góljai nagy részét
  bejátszásból szerzi, azt nem fogni kell, hanem éheztetni (a felé
  futó passzt elvágni sávzárással, előrelépő védővel) — egyénileg nem
  teremt helyzetet; aki maga teremt, ott a passz elvágása keveset ér,
  oda emberfogás vagy kettőzés kell. Saját csapatra: aki csak
  kiszolgálásból él, a bejátszója kiesésekor terv nélkül marad. Három
  kiszolgált góltól és a góljai 60%-ától emel ki nevet. A rangsorban
  az "ember" családba tartozik, és a Kulcs-ember bizonyíték-rétegei
  közé is bekerült. Felületek: /analyze + meccs-csomag
  (`assisted_scorers`), edzői összefoglaló, felderítés
  (`asp_assisted_by_player` / `asp_goals_by_player` mezők + edzői
  kulcs + 390. meccsterv-szabály), edzés-fókusz (411. szabály),
  kliens-csempe.

- **7a6 eladás: mennyibe kerül egy elvesztett labda üres kapunál.**
  Az üres kapura kapott gólok rétege a 7 a 6 teljes mérlegét adja —
  az új réteg a mechanizmust: megszámolja a lehozott kapus mellett
  elvesztett labdákat, és megnézi, hányat büntettek meg nyolc
  másodpercen belül góllal. Edzőileg a 7 a 6 kockázata nem a létszám,
  hanem a labdakezelés: ha az eladásaikat rendre megbüntetik, a
  szerzés után az első nézés MINDIG az üres kapu legyen, ne a
  felállás; saját csapatra a lehozott kapus mellé kijelölt, biztos
  kezű ötös és tiltott-megoldás-lista tartozik. Két eladástól ítél,
  alatta hallgat. A rangsorban az "ár" családba tartozik. Felületek:
  /analyze + meccs-csomag (`empty_net_turnovers`), edzői összefoglaló,
  felderítés (`ent_turnovers` / `ent_punished` mezők + edzői kulcs +
  389. meccsterv-szabály), edzés-fókusz (410. szabály), kliens-csempe.

- **Indítás-vadász emberek: ki ugrik rá a kapus-indításra.** Az
  indítás-vadász poszt a posztot nevezi meg — az új réteg az embert:
  minden elveszett kapus-indításnál a labdát megszerző játékos
  nevéhez ír egy rablást. Edzőileg kétirányú és azonnal használható:
  ellenük a saját kapus indítása ne az ő térfelére nyisson (másik
  oldal, vagy a feje fölött hosszan), saját csapatra pedig figyelmeztet,
  ha a letámadásunk egyetlen emberen áll — azt az ellenfél egy cserével
  hatástalanítja. Két elcsípett indítástól emel ki nevet. A rangsorban
  az "ember" családba tartozik, és a Kulcs-ember bizonyíték-rétegei
  közé is bekerült. Felületek: /analyze + meccs-csomag
  (`outlet_hunters`), edzői összefoglaló, felderítés
  (`ohp_steals_by_player` mező + edzői kulcs + 388. meccsterv-szabály),
  edzés-fókusz (409. szabály), kliens-csempe.

- **Fáradt-fal emberek: ki jár át rajtuk a második félidőre.** A
  fáradt-fal poszt a posztot nevezi meg — az új réteg az embert: a
  kapott gólokat félidőnként a LÖVŐ nevéhez írja, és megkeresi, kinek
  a góljai ugranak meg a szünet után. Edzőileg ez a hajrá-figurák
  terve névre szólóan: aki a második félidőben rendre átjár a falon,
  arra kell építeni; saját csapatra fordítva rá kell friss védőt és
  kijelölt besegítőt tervezni, mert nem a rendszer, hanem a fáradás
  nyitja meg ellene a falat. Két második félidei góltól és kétszeres
  ugrástól emel ki nevet; félidő-jel nélkül hallgat. A rangsorban az
  "ember" családba tartozik, és a Kulcs-ember bizonyíték-rétegei közé
  is bekerült. Felületek: /analyze + meccs-csomag
  (`tired_conceder_players`), edzői összefoglaló, felderítés
  (`tcp_sh_by_player` / `tcp_fh_by_player` mezők + edzői kulcs + 387.
  meccsterv-szabály), edzés-fókusz (408. szabály), kliens-csempe.

- **Visszafutás-lemaradók: ki marad elöl a kontrák alatt.** A
  visszafutás-poszt a posztot nevezi meg — az új réteg az embert: az
  ellenfél lerohanás-szakaszainak végén megnézi, a védekező csapat
  melyik mezőnyjátékosa van legmesszebb a saját kapujától, és a
  lemaradást a nevéhez írja. Edzőileg ez két dolgot ad: ellenük a
  saját lerohanást tudatosan az ő oldalára kell vezetni (ott egy
  emberrel kevesebben érnek vissza), saját csapatra pedig a
  visszafutás-sorrend edzés-téma — a lövés pillanatában kijelölt
  első visszafutó nem lehet mindig ugyanaz. Három lemaradástól emel
  ki nevet, alatta hallgat. A rangsorban az "ember" családba
  tartozik, és a Kulcs-ember bizonyíték-rétegei közé is bekerült.
  Felületek: /analyze + meccs-csomag (`slow_retreat_players`), edzői
  összefoglaló, felderítés (`srp_lags_by_player` mező + edzői kulcs
  + 386. meccsterv-szabály), edzés-fókusz (407. szabály),
  kliens-csempe.

- **Fáradt-eladók: kinek a labdái vesznek el fáradtan.** A
  fáradt-eladó poszt a posztot nevezi meg — az új réteg az embert: a
  labdaeladásokat félidőnként a vesztes játékoshoz írja, és
  megkeresi, kinek ugranak meg az eladásai a második félidőre.
  Edzőileg ez a második félidei pressz-terv névre szólóan: akinek az
  eladásai fáradtan megugranak, azt a szünet után kell nyomás alá
  tenni; saját csapatra a terhelés-menedzsment és a fáradt
  labdabiztonság-edzés a téma. Két második félidei eladástól és
  kétszeres ugrástól emel ki nevet; félidő-jel nélkül hallgat. A
  rangsorban az "ember" családba tartozik, és a Kulcs-ember
  bizonyíték-rétegei közé is bekerült. Felületek: /analyze +
  meccs-csomag (`tired_turnover_players`), edzői összefoglaló,
  felderítés (`ftop_sh_by_player` / `ftop_fh_by_player` mezők +
  edzői kulcs + 385. meccsterv-szabály), edzés-fókusz (406.
  szabály), kliens-csempe.

- **Hátrapasszolók: kinél fordul vissza a játék.** A
  hátrapassz-poszt a posztot nevezi meg — az új réteg az embert: a
  kaputól távolabbi társhoz menő passzokat a passzoló játékoshoz
  írja. Edzőileg ez a pressz jutalma névre szólóan: ha nyomás alatt
  rendre ugyanaz fordítja vissza a labdát, rá érdemes kimenni — a
  hátrapassz időt ad a falnak; saját csapatra a labdás mögé érkező
  felkínálás a téma. Három hátra-passztól emel ki nevet. A
  rangsorban az "ember" családba tartozik, és a Kulcs-ember
  bizonyíték-rétegei közé is bekerült. Felületek: /analyze +
  meccs-csomag (`backward_passers`), edzői összefoglaló, felderítés
  (`bprp_passes_by_player` mező + edzői kulcs + 384.
  meccsterv-szabály), edzés-fókusz (405. szabály), kliens-csempe.

- **Térnyerők: ki viszi előre a labdát.** A térnyerő-poszt a
  posztot nevezi meg — az új réteg az embert: a labdás játékos
  egymást követő kockái közt a támadott kapu felé megtett métereket
  játékosonként összegzi. Edzőileg ez a lendület-fék névre szóló
  terve: őt nem a hatosnál kell fogadni, hanem a felezőtől hátrálva
  — lendületbe engedni tilos, mert onnan már csak
  szabálytalansággal állítható meg; saját csapatra a második
  labdavivő a téma. Huszonöt métertől emel ki nevet. A rangsorban az
  "ember" családba tartozik, és a Kulcs-ember bizonyíték-rétegei
  közé is bekerült. Felületek: /analyze + meccs-csomag
  (`ball_carriers`), edzői összefoglaló, felderítés
  (`tnrp_meters_by_player` mező + edzői kulcs + 383.
  meccsterv-szabály), edzés-fókusz (404. szabály), kliens-csempe.

## v0.1.26 — kiadva (2026-08-09)

> Kiadás-jegyzet: a v0.1.25 óta rövid, de sűrű kör futott. Két
> vezérfonala van: az EMBER-lencse kiteljesítése (a poszt-lencse
> névre szóló párja), és egy terepről visszajött hiba kijavítása,
> ami eddig egész feldolgozásokat vitt el.
>
> **(1) Az elakadt videó-szakaszon tényleg átjut a feldolgozás.** A
> felhasználó jelezte: a feldolgozás 22 percig állt ugyanannál a
> képkockánál, pedig az átugró-adagoló már benne volt a v0.1.25-ben.
> Három külön ok volt, mindhárom javítva: (a) az átugrás csak a
> konzolra írt, így a felület haladás-jelzője állni látszott — most
> minden átugrás kimegy a felületre is; (b) minden újraindítás
> egyetlen kockányit lépett a hibás pozíció után, ezért ugyanabban a
> sérült szakaszban toporgott — most az ugrás-táv négyszereződik
> (legfeljebb 750 kocka), és sikeres kocka után visszaáll; (c) a
> folytató-olvasó a KÖZÖS modell-példányt hívta, miközben az elakadt
> szál épp abban ragadt bent — most saját példánnyal dolgozik. Az
> átugrás időkorlátja 60 → 30 másodperc.
>
> **(2) Kulcs-ember: a harmadik szintézis.** A Kulcs-poszt a
> posztot, a Kulcs-páros a kettőst nevezi meg — az új réteg az
> EMBERT: a néven nevező rétegek élén álló játékosokat számolja
> össze, és ha négy különböző szempont ugyanoda mutat, kimondja a
> kulcs-embert. A meccs-jelentésben önálló szakaszként, a
> bizonyíték-rétegek felsorolásával jelenik meg. Őr-teszt vigyáz
> arra, hogy új ember-réteg ne maradhasson ki a névsorból — élesben
> rögtön talált is egy hiányt (Kilépő védő).
>
> **(3) Tíz új EMBER-réteg.** A poszt-lencse mintáinak névre szóló
> párja: Hetesdobók, Hetes-kihagyók, Emberelőny- és
> Emberhátrány-hibázók, Időkérés-hibázók, Válaszhiba-emberek,
> Ziccer-előkészítők, Vég-birtokosok, Menekülők, Sávváltók,
> Kipattanó-szedők. Mindegyik ugyanazt az utat járja be (motor →
> /analyze és meccs-csomag → edzői összefoglaló → felderítés →
> edzés-fókusz → kliens-csempe → teszt), és mindegyik bizonyítékként
> beszámít a Kulcs-emberbe.
>
> **(4) Új mérések a csapat-oldalon.** Áttörés-hozam (bejutnak-e a
> falba, és büntetnek-e onnan), Kétperc ára (mennyi gólba kerül egy
> kiállításuk), Emberfogás-váltás (a szünet után emberfogásra
> váltanak-e — a leggyakoribb meccs közbeni tervmódosítás).
>
> **(5) Mérési igazság.** A réteg-katalógus, a tény-lap és a
> pályázati doksik számai generáltak, őr-teszttel; a sorrend-függés
> jelentése a kiadás előtt újra lefutott: **430 rétegből 0
> sorrend-függő**.
>
> A kiadás számai: **430 elemző réteg**, **1582 automata teszt**,
> 382 meccsterv-szabály, 403 edzés-szabály, 403 kliens-csempe.

- **Sávváltók: ki viszi a keresztmozgást.** A sávváltó-poszt a
  posztot nevezi meg — az új réteg az embert: ugyanazokat a
  megerősített (két másodpercig tartott) sávváltásokat számolja
  játékosonként. Edzőileg ez a keresztmozgás névre szóló kezelése:
  az ő védőjéről előre el kell dönteni, hogy követi a sávváltáson
  át, vagy átadja a szomszédnak — a bizonytalan átadásból nyílik a
  lyuk; saját csapatra a keresztmozgás szélesítése a téma. Négy
  sávváltástól emel ki nevet. A rangsorban az "ember" családba
  tartozik, és a Kulcs-ember bizonyíték-rétegei közé is bekerült.
  Felületek: /analyze + meccs-csomag (`lane_switchers`), edzői
  összefoglaló, felderítés (`lswp_switches_by_player` mező + edzői
  kulcs + 382. meccsterv-szabály), edzés-fókusz (403. szabály),
  kliens-csempe.

- **Menekülők: nyomás alatt kihez megy a labda.** A menekülő-poszt a
  posztot nevezi meg — az új réteg az embert: a testközeli védő
  mellett meghozott passzokat a fogadó játékoshoz írja. Edzőileg ez
  teszi a presszt labdaszerzéssé névre szólóan: ha szorításban a
  labda rendre ugyanahhoz megy, a kettőzés mögötti harmadik ember
  előre tudja, hol kell lesben állnia — a menekülő passz így nem
  kiút, hanem elfogott labda; saját csapatra a második kiút a téma.
  Három nyomás alatti passztól emel ki nevet. A rangsorban az
  "ember" családba tartozik, és a Kulcs-ember bizonyíték-rétegei
  közé is bekerült. Felületek: /analyze + meccs-csomag
  (`press_outlets`), edzői összefoglaló, felderítés
  (`escp_passes_by_player` mező + edzői kulcs + 381.
  meccsterv-szabály), edzés-fókusz (402. szabály), kliens-csempe.

- **Vég-birtokosok: kinek a kezében hal el a támadásuk.** A
  vég-birtokos poszt a posztot nevezi meg — az új réteg az embert:
  minden lövés nélkül záruló támadás utolsó labdabirtokosát számolja
  játékosonként. Edzőileg ez a nyomás névre szóló címzettje: a
  támadás második felében rá kell tolni a nyomást, mert nála zárul a
  támadás, és ott a legolcsóbb a labdaszerzés; saját csapatra a
  befejezés-felelősség tisztázása a téma. Három terméketlen
  támadástól emel ki nevet. A rangsorban az "ember" családba
  tartozik, és a Kulcs-ember bizonyíték-rétegei közé is bekerült.
  Felületek: /analyze + meccs-csomag (`last_holders`), edzői
  összefoglaló, felderítés (`lstp_attacks_by_player` mező + edzői
  kulcs + 380. meccsterv-szabály), edzés-fókusz (401. szabály),
  kliens-csempe.

- **Ziccer-előkészítők: ki adja a passzt a nagy helyzethez.** A
  ziccer-előkészítő poszt a posztot nevezi meg — az új réteg az
  embert: a nagy helyzet-értékű lövésekhez megkeresi a lövő felé menő
  utolsó passzt, és a helyzetet a passzoló játékoshoz írja.
  Edzőileg ez a legdrágább passzsáv névre szólóan: az ő
  bejátszó-sávját kell elvágni (testtel zárás, előrelépő védő) — a
  helyzet így ki sem alakul; saját csapatra a fő előkészítő
  tehermentesítése a téma. Két előkészítéstől emel ki nevet. A
  rangsorban az "ember" családba tartozik, és a Kulcs-ember
  bizonyíték-rétegei közé is bekerült. Felületek: /analyze +
  meccs-csomag (`big_chance_feeders`), edzői összefoglaló, felderítés
  (`bcfp_chances_by_player` mező + edzői kulcs + 379.
  meccsterv-szabály), edzés-fókusz (400. szabály), kliens-csempe.

- **Válaszhiba-emberek: kapott gól után ki veszíti el a labdát.** A
  válaszhiba-poszt a posztot nevezi meg — az új réteg az embert:
  ugyanazokat a kapott gólt egy percen belül követő labdaeladásokat
  játékosonként számolja. Edzőileg ez a saját gólunk utáni pressz
  névre szóló célpontja: a gólunk után azonnal az ő fogadására kell
  menni, mert nála a legolcsóbb a labdaszerzés; saját csapatra a
  bekapott gól utáni első támadás átcímzése a téma. Két eladástól
  emel ki nevet. A rangsorban az "ember" családba tartozik, és a
  Kulcs-ember bizonyíték-rétegei közé is bekerült. Felületek:
  /analyze + meccs-csomag (`response_turnover_players`), edzői
  összefoglaló, felderítés (`rtop_turnovers_by_player` mező + edzői
  kulcs + 378. meccsterv-szabály), edzés-fókusz (399. szabály),
  kliens-csempe.

- **Időkérés-hibázók: a megbeszélt figura kinek a kezén hal el.** Az
  időkérés-hiba poszt a posztot nevezi meg — az új réteg az embert:
  ugyanazokat az időkérés utáni ablakban elkövetett labdaeladásokat
  játékosonként számolja. Edzőileg ez az időkérés utáni védekezés
  névre szóló mondata: a táblára rajzolt figura ott a
  legsérülékenyebb, ahol eddig is elhalt — az ő fogadására menjen a
  kilépés és a kettőzés; saját csapatra a kulcspassz átcímzése a
  téma. Két eladástól emel ki nevet. A rangsorban az "ember"
  családba tartozik, és a Kulcs-ember bizonyíték-rétegei közé is
  bekerült. Felületek: /analyze + meccs-csomag
  (`timeout_turnover_players`), edzői összefoglaló, felderítés
  (`toep_turnovers_by_player` mező + edzői kulcs + 377.
  meccsterv-szabály), edzés-fókusz (398. szabály), kliens-csempe.

- **Őr-teszt a Kulcs-ember névsorára.** A Kulcs-poszt lefedettségét
  eddig is őrizte teszt; mostantól az ember-oldalt is: minden
  pipeline-függvény, amely a `top` mezőjében EMBERT nevez meg
  (`player_id`), szerepelnie kell a `KPL_LAYERS` listában — a
  poszt- és páros-lencse rétegek nevesített kivételek. Az őr rögtön
  dolgozott is: a Kilépő védő (`advanced_defender`) kimaradt a
  névsorból, most bekerült, így a Kulcs-ember bizonyíték-lánca
  teljes.

- **Hetesdobók: ki áll oda a hétméteresekhez.** A hetesdobó-poszt a
  posztot nevezi meg, a hetes-kihagyók azt, ki hibázza el — az új
  réteg azt, ki áll oda egyáltalán: a felismert hétméteresek dobóit
  számolja játékosonként (góllal és gól nélkül zárulókat együtt).
  Edzőileg ez a kapus felkészítésének első lapja: ha a heteseket
  ugyanaz dobja, a kapus RÁ készülhet (szokás-sarok, lépésritmus,
  csel), és a videó-elemzés is egy emberre szűkül; saját csapatra az
  egyetlen hetesdobó kockázat. Két hetestől emel ki nevet. A
  rangsorban az "ember" családba tartozik, és a Kulcs-ember
  bizonyíték-rétegei közé is bekerült. Felületek: /analyze +
  meccs-csomag (`seven_taker_players`), edzői összefoglaló,
  felderítés (`stp_sevens_by_player` mező + edzői kulcs + 376.
  meccsterv-szabály), edzés-fókusz (397. szabály), kliens-csempe.

- **Javítás — az elakadt szakaszon tényleg átjut a feldolgozás.** Az
  átugró-adagoló eddig három ponton is elakadhatott ugyanott: (1) az
  átugrás nem jelzett vissza a felületnek, így a haladás-jelző (és az
  elakadás-őrszem szívverése) állni látszott, a felhasználó pedig azt
  látta, hogy húsz perce nem történik semmi; (2) minden újraindítás
  ugyanabból a hibás szakaszból próbálkozott egyetlen kockányit
  lépve, holott a sérült rész hosszabb — most, ha a folytatás sem ad
  kockát, az ugrás-táv négyszereződik (legfeljebb 750 kockáig), és
  sikeres kocka után visszaáll a legkisebbre; (3) a folytató-olvasó a
  KÖZÖS modell-példányt hívta, miközben az elakadt szál épp abban
  ragadt bent — mostantól saját példánnyal dolgozik. Az átugrás
  időkorlátja 60-ról 30 másodpercre csökkent, így a hibás szakaszon
  gyorsabban jutunk át. A felület üzenete is pontosabb: az átugrás
  folyamatban van, több lépésben.

- **Áttörés-hozam: bejutnak-e a falba, és büntetnek-e onnan.** Az
  áttörő játékosok rétege azt mondja meg, ki viszi be a labdát, az
  áttörő-poszt azt, melyik posztjuk — az új réteg a hozamot: a
  betörések hány százaléka végződik góllal, és hány betörés jut egy
  támadásra. A két szám más-más tervet ír elő: ha sokat jutnak be ÉS
  büntetnek is, a falat előbb kell zárni (kilépés a lövő elé, a
  betörés vonalának testtel zárása); ha bejutnak, de nem büntetnek, a
  záró-fal és a kapus dolgozik — nem a rendszert kell átszabni,
  hanem a kipattanóra embert küldeni. Öt betörés alatt hallgat
  (None). Felületek: /analyze + meccs-csomag (`breakthrough_yield`),
  edzői összefoglaló, felderítés (`bty_entries` / `bty_goals` mezők +
  edzői kulcs mindkét irányra + 375. meccsterv-szabály), edzés-fókusz
  (396. szabály, külön mondattal az erősségre és a befejezés-gondra),
  kliens-csempe.

- **Emberhátrány-hibázók: öt emberrel ki veszíti el a labdát.** Az
  emberhátrány-hiba poszt a posztot nevezi meg — az új réteg az
  embert: ugyanazokat a kiállítás-ablakokban, emberhátrányban
  elkövetett labdaeladásokat játékosonként számolja. Edzőileg ez az
  emberelőny-játékunk névre szóló célpontja: a hat az öt ellen az ő
  fogadására kell menni, mert az elvett labdából üres kapura indulhat
  a kontra; saját csapatra a labdatartó kijelölése a téma. Két
  eladástól emel ki nevet. A rangsorban az "ember" családba
  tartozik, és a Kulcs-ember bizonyíték-rétegei közé is bekerült.
  Felületek: /analyze + meccs-csomag
  (`shorthanded_turnover_players`), edzői összefoglaló, felderítés
  (`shtp_turnovers_by_player` mező + edzői kulcs + 374.
  meccsterv-szabály), edzés-fókusz (395. szabály), kliens-csempe.

- **Emberelőny-hibázók: ki adja el a labdát a két perc alatt.** Az
  emberelőny-hiba poszt a posztot nevezi meg — az új réteg az
  embert: ugyanazokat a kiállítás-ablakokban, emberelőnyben
  elkövetett labdaeladásokat játékosonként számolja. Edzőileg ez a
  hátrány-védekezés névre szóló célpontja: hátrányban rá kell nyomni
  (kettőzés, passzsáv-zárás a fogadásánál), mert az ő elvett labdája
  dupla büntetés. Két eladástól emel ki nevet. A rangsorban az
  "ember" családba tartozik, és a Kulcs-ember bizonyíték-rétegei
  közé is bekerült. Felületek: /analyze + meccs-csomag
  (`powerplay_turnover_players`), edzői összefoglaló, felderítés
  (`pptp_turnovers_by_player` mező + edzői kulcs + 373.
  meccsterv-szabály), edzés-fókusz (394. szabály), kliens-csempe.

- **Kulcs-ember: hány réteg mutat ugyanarra a játékosra.** A
  Kulcs-poszt a posztot, a Kulcs-páros a kettőst nevezi meg — az új,
  harmadik szintézis az EMBERT: a néven nevező rétegek (tüzes kéz,
  aszály-törő, hajrá-birtokló, letámadó, áttörő, elzáró,
  kipattanó-szedő, hetes-kihagyó, sprint-veszély, …) élén álló
  játékosokat számolja össze csapatonként. A három lista
  szándékosan külön áll: a "melyik poszt", a "melyik kettős" és a
  "melyik EMBER" kérdés más-más választ ad. Edzőileg ez a személyre
  szóló feladat lapja: ha négy különböző szempont ugyanazt az embert
  dobja ki, az ő kezelése (emberfogás, kettőzés, a labdaútjának
  elvágása) önmagában meccstervnyi; saját csapatra ugyanez
  figyelmeztetés a tehermentesítésre. Négy egyező réteg alatt vagy
  holtversenynél hallgat (None). A rangsorban az "ember" családba
  tartozik. Felületek: /analyze + meccs-csomag (`key_player`), edzői
  összefoglaló, felderítés (`kpl_layers_by_player` mező + edzői
  kulcs + 372. meccsterv-szabály), edzés-fókusz (393. szabály),
  HTML-riport (önálló Kulcs-ember szakasz a bizonyíték-rétegek
  felsorolásával), kliens-csempe.

- **Kétperc ára: mennyi gólba kerül egy kiállításuk.** Az
  emberelőny-hatékonyság azt méri, mit támadnak a két perc alatt, az
  emberelőny-védekezés azt, mit kapnak közben — az új réteg a
  hátrány oldalát egyetlen számban: hány gólt kapnak átlagosan egy
  kiállítás-ablak alatt. Edzőileg ez a fegyelem ára forintosítva: ha
  egy kétperc átlag több mint egy gólba kerül, a kiharcolás
  önmagában pont-termelés (a betöréseket vállalni kell); ha olcsón
  megússzák, nem szabad a kiállításra játszani. Három
  kiállítás-ablak alatt hallgat (None). A rangsorban az "ár"
  családba tartozik. Felületek: /analyze + meccs-csomag
  (`suspension_cost`), edzői összefoglaló, felderítés (edzői kulcs
  mindkét irányra + 371. meccsterv-szabály), edzés-fókusz (392.
  szabály, külön mondattal a drága és az olcsó hátrányra),
  kliens-csempe.

- **Emberfogás-váltás: a szünet után emberfogásra váltanak-e.** Az
  őrzési párok a meccs egészére mondják meg, ki kit fogott — az új
  réteg a váltást: félidőnként megkeresi a legszorosabb párost, és
  összeveti a két átlagtávolságot. A szünetben hozott emberfogás a
  leggyakoribb meccs közbeni tervmódosítás, és a felkészülésben ez a
  legdrágább meglepetés. Edzőileg: ha a szünet után emberfogásra
  váltanak, a fogott játékosnak el kell húznia a védőjét, és a
  felszabaduló területet kell megjátszani; ha elengedik, a korábban
  fogott ember visszakapja a labdát. Félidő-jel nélkül vagy kevés
  őrzés-kocka mellett hallgat (None). A rangsorban a "szünet"
  családba tartozik. Felületek: /analyze + meccs-csomag
  (`marking_shift`), edzői összefoglaló, felderítés (edzői kulcs
  mindkét irányra + 370. meccsterv-szabály), edzés-fókusz (391.
  szabály, külön mondattal a váltásra és az elengedésre),
  kliens-csempe.

## v0.1.25 — kiadva (2026-08-09)

> Kiadás-jegyzet: a v0.1.24 óta a fejlesztés hat szálon futott. A kör
> vezérfonala a POSZT-LENCSE kiteljesítése: a rendszer immár nemcsak
> azt mondja meg, MI történt, hanem azt is, MELYIK POSZTJUKNÁL — és
> ami ebből következik, KI ELLEN mit kell tenni.
>
> **(1) Poszt-lencse mindenre**: kilencven fölötti új réteg vitte
> végig ugyanazt a formát a játék minden szakaszán — befejezés
> (ziccer, ziccerhagyó, pazarló, blokkolt, fedezett, fáradt lövő),
> építkezés (indító, előkészítő, bejátszó, térnyerő, hátrapassz,
> labdatartó, lágypassz, kockáztató, sávváltó, vég-birtokos),
> védekezés (kilépő, átvert, elzárt, kettőző, kettőzött, célkereszt,
> beállóőr, letámadó, visszafutás, elöl lógó, védőmotor,
> lepattanó-szedő), szabály és létszám (hetesdobó, hetes-okozó,
> hetes-kihagyó, kiülő, emberelőny, emberhátrány, 7a6-befejező),
> valamint a végjáték és a lélektan (hajrá, hajrákéz, hajráhiba,
> válasz, válaszhiba, csendtörő, forró, eltűnő, felzárkózás, rajt,
> újrakezdő, középkezdő). Minden réteg ugyanazt az utat járja be: motor
> → /analyze és meccs-csomag → edzői összefoglaló → felderítés (mező,
> edzői kulcs, sorszámozott meccsterv-szabály, több meccs összegzése)
> → edzés-fókusz → HTML-jelentés lencse-sora → kliens-csempe → teszt.
>
> **(2) Páros-lencse és a két szintézis**: kilenc réteg már nem egy
> posztot, hanem egy KETTŐST nevez meg (elzáró-, hetes-, kontra-,
> gólpassz-, kettőző-, lepattanó-, emberelőny-, időkérés- és
> ziccerpáros, majd a kétperc-lánc). Fölébük két összegző réteg
> került: a **Kulcs-poszt** azt mondja meg, hány réteg mutat ugyanarra
> az EGY posztra, a **Kulcs-páros** azt, hány réteg ugyanarra a
> KETTŐSRE — a két lista szándékosan külön áll, hogy a "melyik ember"
> és a "melyik kettős" kérdés ne hígítsa egymást. A jelentésben mindkettő
> indoklással, a bizonyíték-rétegek felsorolásával jelenik meg.
>
> **(3) Ár és végjáték**: új "ár"-rétegek mondják meg, mennyibe kerül
> egy szokás — a **visszaállás ára** (a gól nélküli lövés után kapott
> gyors gól) és a **kipattanó ára** (a védés utáni második-helyzet
> gól). A végjátékot a **hajrá-kapus**, az **óralopás** (vezetve
> elhúzzák-e a támadást), a **kapkodás-index** (kapott gól után
> rövidül-e) és a **sprint-esés** írja le. Ide tartozik a
> **figura-koncentráció** is: megmondja, egyáltalán érdemes-e konkrét
> figurára készülni ellenük, vagy elvekre kell.
>
> **(4) Feldolgozás: nem áll meg egy rossz képkockán.** A videó-feldolgozó
> eddig 3 perc előrelépés nélkül feladta és részleges meccset mentett.
> Mostantól a beragadt képkockát ÁTUGORJA, és a következőtől folytatja
> (legfeljebb húsz ugrás), a felület pedig ki is írja, hogy ez történik.
>
> **(5) Szerkezeti őr-tesztek**: a kör során több olyan háló készült,
> ami nem egy réteget mér, hanem a rendszer épségét — kétszer definiált
> modul-konstans és függvény, kimaradt Kulcs-poszt bizonyíték-réteg,
> lefedetlen kliens-csempe-csoport, hiányzó lencse-sor. Ezek élesben
> fogtak meg valódi hibákat: egy néma küszöb-felülírás miatt a kapus
> gyengeoldal-rétege 0,45 helyett 0,65-ös küszöbbel futott, egy másik
> a Kiülő-poszt küszöbét írta át, egy ütköző teszt-helper pedig két
> meglévő tesztet döntött be.
>
> **(6) Mérési igazság**: a réteg-katalógus, a tény-lap és a pályázati
> doksik számai generáltak, őr-teszttel; a sorrend-függés jelentése a
> kiadás előtt újra lefutott, és **417 rétegből 0 sorrend-függő** — a
> termék minden összeállítása sorrend-független.
>
> A kiadás számai: **417 elemző réteg**, **1548 automata teszt**, 369
> meccsterv-szabály, 390 edzés-szabály, 390 kliens-csempe.

- **Kipattanó-szedők: ki szedi össze a kipattanót védés után.** A
  lepattanó-szedő poszt a posztot nevezi meg — az új réteg az
  embert: ugyanazokat a megszerzett kipattanókat játékosonként
  számolja. Edzőileg ez a berobbanó ember célpontja: aki rendre
  összeszedi a kipattanókat, azt a második helyzetnél blokkolni kell
  (test, elzárás a kipattanó-zónában); saját csapatra a
  kipattanó-munka kiosztása a téma. Két kipattanótól emel ki nevet.
  A rangsorban az "ember" családba tartozik. Felületek: /analyze +
  meccs-csomag (`defensive_rebound_players`), edzői összefoglaló,
  felderítés (`rbcp_rebounds_by_player` mező + edzői kulcs + 369.
  meccsterv-szabály), edzés-fókusz (390. szabály), kliens-csempe.
- **Kétperc-páros: ki harcolja ki és ki fejezi be a kétpercüket.**
  A kiállítás-kiharcolás poszt szerint azt mondja meg, ki hozza a
  kétperceseket, az emberelőny-poszt azt, kire fut ki a hat az öt
  ellen — az új réteg a kettőt köti össze kiállításonként: a
  (kiharcoló poszt → emberelőny-befejező poszt) párost számolja az
  ablakon belüli lövéseik alapján. Edzőileg egy kiállítás két
  feladatot ad egyszerre: a kiharcoló posztja ellen fegyelmezetten,
  testtel kell védekezni (nála a kései fogás kétpercet ér), a
  befejező posztját pedig hátrányban letiltani — a lánc így már az
  elején elvágható. Három lánc és 55% párosrészarány alatt hallgat
  (None). Felületek: /analyze + meccs-csomag
  (`suspension_chain_roles`), edzői összefoglaló, felderítés (edzői
  kulcs + 368. meccsterv-szabály), edzés-fókusz (389. szabály),
  HTML-riport (Befejező-lencse sor), Kulcs-páros bizonyíték-réteg,
  kliens-csempe.
- **Hetes-kihagyók: ki hibázza el a hetest.** A hetes-mérleg
  csapat-szinten mondja meg, mennyi megy be a hetesekből, a
  hetes-kihagyó poszt a posztot — az új réteg az embert: a gól
  nélkül záruló hétméteresek (védés vagy mellé) a dobó játékoshoz
  kerülnek. Edzőileg ez a kapus felkészítésének névsora: ha ő áll
  oda, a kapus mehet a saját megérzésére (kimozdulás, késleltetett
  vetődés) — nála a hetes nem automatikus gól. Saját csapatra a
  hetes-sorrend és a második dobó kijelölése a téma. Két kihagyástól
  emel ki nevet (a hetes ritka esemény). A rangsorban az "ember"
  családba tartozik. Felületek: /analyze + meccs-csomag
  (`seven_miss_players`), edzői összefoglaló, felderítés
  (`svmp_misses_by_player` mező dobónként + edzői kulcs + 367.
  meccsterv-szabály), edzés-fókusz (388. szabály), kliens-csempe.
- **Sprint-esés: megfogy-e a láb a második félidőre.** A
  sprint-állás az eredményjelzőn nézi a futást, a játékos-fáradás
  emberenként — az új réteg csapatszinten, félidőnként: a
  sprint/perc ütemet veti össze az első és a második félidőben.
  Edzőileg ez a második félidő tempó-döntése: ha a lábuk megfogy, a
  szünet után tempót kell emelni (minden labdaszerzésből futni, mert
  a visszarendeződésük már nem megy); ha nő, ők kapcsolnak a hajrára
  — akkor a saját ritmust kell tartani. Félidő-jel nélkül, öt
  játékperc vagy nyolc sprint alatt hallgat (None). A rangsorban a
  "fáradás" családba tartozik. Felületek: /analyze + meccs-csomag
  (`sprint_fade`), edzői összefoglaló, felderítés (edzői kulcs
  mindkét irányra + 366. meccsterv-szabály), edzés-fókusz (387.
  szabály, külön mondattal az esésre és a kapcsolásra),
  kliens-csempe.
- **Óralopás: vezetve elhúzzák-e a támadást a hajrában.** A
  kapkodás-index a kapott gól utáni tempót méri, a hajrá-rétegek
  azt, ki viszi a végjátékot — az új réteg az órát: a felvétel
  utolsó öt percében, vezetésben indított támadásaik átlagos hosszát
  veti össze a többi támadásukéval. Edzőileg ez a végjáték egyik
  döntése: ha vezetve elhúzzák a támadást, a passzív jelre kell
  játszani (korai kettőzés, azonnali kontra); ha nem lassítanak, elég
  zárt fallal kivárni, mert maguktól hoznak helyzetet. Három
  hajrá-támadás és négy alap-támadás alatt hallgat (None), és három
  másodperc eltérés kell az ítélethez. A rangsorban az "állás"
  családba tartozik. Felületek: /analyze + meccs-csomag
  (`clock_management`), edzői összefoglaló, felderítés (edzői kulcs
  mindkét irányra + 365. meccsterv-szabály), edzés-fókusz (386.
  szabály, külön mondattal az időhúzásra és a kapkodásra),
  kliens-csempe.
- **Kipattanó ára: a védésük után kapott második-helyzet gól.** A
  kapus-kipattanó azt mondja meg, fogja-e vagy kiüti a kapus a
  labdát, a lepattanó-szedő poszt azt, ki szedi össze — az új réteg
  azt, mennyibe kerül: a védéseiket nézi, és megszámolja, hányat
  követett négy másodpercen belül a támadó csapat gólja. A védés így
  nem megúszott helyzet, hanem elhalasztott. Edzőileg ez a berobbanó
  ember számlája: ha a védéseik hatoda gólba fut, minden lövésnél
  indítani kell a kipattanó-zónába; saját csapatra a kapus
  terelés-iránya (a szélre üsse, ne középre) és a
  kipattanó-felelősség kiosztása a téma. Öt védés alatt hallgat
  (None); az ítélet 15% fölött szólal meg. A rangsorban az "ár"
  családba tartozik. Felületek: /analyze + meccs-csomag
  (`rebound_punishment`), edzői összefoglaló, felderítés (edzői
  kulcs + 364. meccsterv-szabály), edzés-fókusz (385. szabály),
  kliens-csempe.
- **Visszaállás ára: a gól nélküli lövésük után kapott gyors gól.**
  A visszaállás-idő azt mondja meg, hány másodperc alatt áll össze a
  faluk — az új réteg azt, mennyibe kerül: a gól nélkül záruló
  lövéseiket (védés, mellé, blokk) nézi, és megszámolja, hányat
  követett tizenkét másodpercen belül az ellenfél gólja (a góllal
  záruló lövések kimaradnak: onnan középkezdés jön, nem lerohanás).
  Edzőileg ez a lassú visszaállás számlája: ha a lövéseik ötödét
  gyors kapott gól követi, nem a fal minősége a baj, hanem hogy a
  fal nincs ott. Hat gól nélküli lövés alatt hallgat (None); az
  ítélet 20% fölött szólal meg. A rangsorban az "ár" családba
  tartozik. Felületek: /analyze + meccs-csomag
  (`retreat_punishment`), edzői összefoglaló, felderítés (edzői
  kulcs + 363. meccsterv-szabály), edzés-fókusz (384. szabály),
  kliens-csempe.
- **Lepattanó-szedő poszt: védés után kinél marad a labda.** A
  kapus-kipattanó azt mondja meg, fogja-e a kapus a labdát, a
  lepattanó-poszt azt, ki lő másodszor — az új réteg a védekező
  oldalt: a kapusuk védése utáni négy másodpercben megszerzett
  kipattanókat a labdát megszerző védőjük posztjához írja (ha a
  kapus egy másodpercnél tovább tartja, az fogás, nem kipattanó — az
  ilyen eset nem számít). Edzőileg ez a második helyzet terve: ha a
  kipattanókat rendre ugyanaz a posztjuk szedi össze, oda kell
  küldeni a berobbanó embert, mert a második lövés a legolcsóbb gól.
  Legalább 3 megszerzett kipattanó és 60% posztrészarány alatt
  hallgat (None). Felületek: /analyze + meccs-csomag
  (`defensive_rebound_roles`), edzői összefoglaló, felderítés (edzői
  kulcs + 362. meccsterv-szabály), edzés-fókusz (383. szabály),
  HTML-riport (Védő-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Figura-koncentráció: egy figurára épül-e a támadójátékuk.** A
  figura-hatékonyság azt mondja meg, melyik figurájuk veszélyes, a
  figura-befejező azt, kire fut ki — az új réteg a repertoár
  szélességét: a támadás-szakaszokat csapatonként klaszterezi, és
  megnézi, mekkora hányad esik a legnagyobb klaszterbe, illetve hány
  figura fedi le a támadások 80%-át. Edzőileg ez a felkészülés
  terjedelme: 40% fölött konkrét figurára lehet készülni (videó,
  bejátszott védekezés, előre megbeszélt kettőzés), 25% alatt viszont
  figurákra készülni pazarlás — elvekre kell (kilépés-szabály,
  beálló-átadás, kettőzés-jel). Hat mért támadás alatt hallgat
  (None). Felületek: /analyze + meccs-csomag
  (`setplay_concentration`), edzői összefoglaló, felderítés (edzői
  kulcs mindkét irányra + 361. meccsterv-szabály), edzés-fókusz (382.
  szabály, külön mondattal a szűk és a széles repertoárra),
  kliens-csempe. Nem poszt-lencse: a Kulcs-poszt bizonyíték-rétegek
  közé nem kerül be.
- **Hajrá-kapus: nő vagy beesik a kapusuk az utolsó öt percben.** A
  kapus-bemelegedés a meccs elejét méri, a kapus-forma félidőnként a
  fáradást — az új réteg a végjátékot: a rá kaputra érkezett
  lövéseket szétválasztja a felvétel utolsó öt percére és a
  maradékra. Edzőileg ez a hajrá-terv kapus-fejezete: ha a kapusuk a
  végén nő, a döntő percekben nem szabad félhelyzetből lőni
  (kiugratás, beállós helyzet vagy hetes kell); ha beesik, minden
  tiszta lövés megéri, és a lövésszámot fel kell vinni. Szakaszonként
  három kaputra érkezett lövés és 15 százalékpont eltérés alatt
  hallgat (None). Felületek: /analyze + meccs-csomag
  (`gk_clutch_saves`), edzői összefoglaló, felderítés (edzői kulcs +
  360. meccsterv-szabály, mindkét irányra), edzés-fókusz (381.
  szabály, külön mondattal a beeső és az erősödő kapusra),
  kliens-csempe. Nem poszt-lencse: a Kulcs-poszt bizonyíték-rétegek
  közé nem kerül be.
- **Emberhátrány-hiba poszt: öt emberrel kinek a kezén vész el a
  labdájuk.** Az emberhátrány-poszt azt mondja meg, ki vállalja a
  befejezést öt emberrel — az új réteg a párja: a kiállítás-
  ablakokban, emberhátrányban elkövetett labdaeladásokat a vesztes
  posztjához írja (az emberelőny-hiba poszt a két percet előnyből
  nézi, ez hátrányból, ahol egy elvesztett labda azonnal gólt ér).
  Edzőileg ez az emberelőny-játékunk célpontja: a hat az öt ellen az
  ő fogadására kell menni, mert az elvett labdából üres kapura
  indulhat a kontra. Legalább 3 hátrány-eladás és 60%
  posztrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`shorthanded_turnover_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 359. meccsterv-szabály), edzés-fókusz
  (380. szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Kapkodás-index: kapott gól után rövidül vagy nyúlik a
  támadásuk.** A válasz-poszt és a válaszhiba-poszt embert nevez meg
  — az új réteg a tempót: a kapott gólt egy percen belül követő
  támadásaik átlagos hosszát veti össze a többi támadásukéval. A
  különbség előjele mondja meg, mit csinálnak a bekapott góllal: 3
  másodperccel rövidebb támadás = kapkodás, ennyivel hosszabb =
  befagyás. Edzőileg ez a saját gólunk utáni terv egy mondata: ha
  kapkodnak, vissza kell állni (az elsietett lövés nekünk termel
  labdát); ha befagynak, előre kell tolni a védekezést, mert az óra
  nekik ketyeg. Három válasz-támadás és négy alap-támadás alatt
  hallgat (None). Felületek: /analyze + meccs-csomag
  (`post_goal_rush`), edzői összefoglaló, felderítés (edzői kulcs +
  358. meccsterv-szabály), edzés-fókusz (379. szabály, mindkét
  irányra külön mondattal), kliens-csempe. Nem poszt-lencse:
  csapatszintű szám, a Kulcs-poszt bizonyíték-rétegek közé nem
  kerül be.
- **Visszaállás-idő: hány másodperc alatt áll össze a faluk a
  lövésük után.** A visszafutás-poszt azt mondja meg, KI marad le —
  az új réteg azt, MENNYI IDŐ alatt áll össze a fal: minden lövésük
  után megméri, mennyi idő telik el, míg négy mezőnyjátékosuk a
  saját térfelükre ér (ha húsz másodperc alatt sem, a felső
  korláttal számol — a lassúságot nem hallgatja el). Edzőileg ez a
  kontra-terv egy száma: nyolc másodperc fölött a lövésük után
  indított első hullám még üres pályát talál, a kapusnak azonnal
  indítania kell. Négy mért lövés alatt hallgat (None). Felületek:
  /analyze + meccs-csomag (`retreat_time`), edzői összefoglaló,
  felderítés (edzői kulcs + 357. meccsterv-szabály), edzés-fókusz
  (378. szabály), kliens-csempe. Nem poszt-lencse: csapatszintű
  szám, ezért a Kulcs-poszt bizonyíték-rétegek közé nem kerül be.
- **Időkérés-hiba poszt: a megbeszélt figura kinek a kezén hal
  el.** Az időkérés-befejező és az időkéréspáros a sikeres figurát
  írja le — az új réteg a kudarcát: az időkérés utáni ablakban
  elkövetett labdaeladásokat a vesztes posztjához írja. Edzőileg ez
  az időkérés utáni védekezés második mondata: a figura ott a
  legsérülékenyebb, ahol eddig is elhalt — az ő indításánál kell
  megnyomni (előrelépő védő, kettőzés az első bejátszásnál). Saját
  csapatra: ha a kulcspasszt mindig ugyanaz rontja el, egyszerűbb
  kezdés kell. Legalább 3 időkérés utáni eladás és 60%
  posztrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`timeout_turnover_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 356. meccsterv-szabály), edzés-fókusz
  (377. szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Válaszhiba-poszt: kapott gól után kinél vész el a labdájuk.**
  A válasz-poszt azt mondja meg, kire fut ki a bekapott gól utáni
  válaszuk — az új réteg a másik felét: a kapott gólt egy percen
  belül követő labdaeladásokat a vesztes posztjához írja (a
  poszt-hibák rétege az egész meccset nézi, ez csak a gól utáni
  percet, amikor a csapat kapkod). Edzőileg ez a saját gólunk utáni
  presszterv: ha a kapott gól után rendre ugyanannak a kezén vész el
  a labda, a gólunk után azonnal az ő fogadására kell menni — a
  válaszuk el sem indul, és a labdából jöhet a következő gólunk.
  Legalább 3 válasz-eladás és 60% posztrészarány alatt hallgat
  (None). Felületek: /analyze + meccs-csomag
  (`response_turnover_roles`), edzői összefoglaló, felderítés (edzői
  kulcs + 355. meccsterv-szabály), edzés-fókusz (376. szabály),
  HTML-riport (Befejező-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Emberelőny-hiba poszt: kinek a kezén akad el az
  emberelőnyük.** Az emberelőny-poszt azt mondja meg, kire fut ki a
  hat a öt ellen — az új réteg azt, kinél vész el: a
  kiállítás-ablakokban, emberelőnyben elkövetett labdaeladásokat a
  vesztes posztjához írja (a poszt-hibák rétege az egész meccset
  nézi, ez csak a két percet, ahol a hiba a legdrágább). Edzőileg ez
  a hátrányban álló csapat esélye: ha az emberelőnyük rendre
  ugyanannak a kezén akad el, rá kell nyomni — az ő elvett labdája
  dupla büntetés, mert a kétperc alatt kontrázni lehet belőle.
  Legalább 3 emberelőny-eladás és 60% posztrészarány alatt hallgat
  (None). Felületek: /analyze + meccs-csomag
  (`powerplay_turnover_roles`), edzői összefoglaló, felderítés
  (edzői kulcs + 354. meccsterv-szabály), edzés-fókusz (375.
  szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Ziccerpáros-poszt: ki adja és ki fejezi be a nagy
  helyzeteiket.** A ziccer-előkészítő poszt azt mondja meg, kinek a
  kezéből indul a helyzet, a ziccer-poszt azt, kinél alakul ki — az
  új réteg a kettőt köti össze helyzetenként: az (előkészítő poszt →
  befejező poszt) párost számolja. A gólpasszpáros a góllal zárult
  összjátékot nézi, ez a helyzet-értéket: a bejáratott ziccer-gyár
  akkor is látszik, ha a befejezés sokszor kimarad. Edzőileg egy
  mozdulattal két posztot fog ki a védekezés: nem külön-külön kell
  fogni őket, hanem a köztük lévő passzsávot elvágni — zárt sávnál a
  ziccer ki sem alakul. Legalább 3 ziccer-páros és 55%
  párosrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`big_chance_pair_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 353. meccsterv-szabály), edzés-fókusz
  (374. szabály), HTML-riport (Befejező-lencse sor), Kulcs-páros
  bizonyíték-réteg, kliens-csempe.
- **Hetes-kihagyó poszt: melyik posztjuk hibázza el a hetest.** A
  hetesdobó-poszt azt mondja meg, ki áll oda — az új réteg azt, ki
  hibáz: a felismert hétméteresek közül a gól NÉLKÜL zárulókat
  (védés vagy mellé) a dobó posztjához írja. Edzőileg ez a kapus
  felkészítésének második fele: ha a kihagyásaik egy posztra
  sűrűsödnek, a kapus tudja, melyik dobó ellen érdemes a saját
  megérzésére hagyatkozni (kimozdulás, késleltetett vetődés) — nála a
  hetes nem automatikus gól. Saját csapatra a hetes-rutin és a
  második dobó kijelölése a téma. Legalább 3 gól nélküli hetes és
  60% posztrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`seven_miss_roles`), edzői összefoglaló, felderítés
  (edzői kulcs + 352. meccsterv-szabály), edzés-fókusz (373.
  szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Ziccer-előkészítő poszt: ki adja a passzt a nagy helyzethez.** A
  ziccer-poszt azt mondja meg, melyik posztnál alakul ki a nagy
  helyzet — az új réteg azt, ki teremti: a nagy helyzet-értékű
  lövésekhez megkeresi a lövő felé menő utolsó passzt, és a
  helyzetet a passzoló posztjához írja (az előkészítő-poszt minden
  lövést néz, ez csak a veszélyeseket). Edzőileg a legdrágább
  passzsáv: az előkészítő bejátszó-sávját elvágva a helyzet ki sem
  alakul, nem a befejezést kell hárítani. Legalább 3
  ziccer-előkészítés és 60% posztrészarány alatt hallgat (None).
  Felületek: /analyze + meccs-csomag (`big_chance_feeder_roles`),
  edzői összefoglaló, felderítés (edzői kulcs + 351. meccsterv-
  szabály), edzés-fókusz (372. szabály), HTML-riport (Befejező-
  lencse sor), Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Vég-birtokos poszt: kinél ér véget a támadásuk lövés nélkül.** A
  passzív-poszt csak a hosszú, felállt támadásokat nézi — az új
  réteg minden lövés nélkül záruló támadást: a szakasz utolsó
  labdabirtokosát a posztjához írja, így a rövid, eladásba fulladó
  támadások vége is látszik. Edzőileg a nyomás címzettje: ha a
  terméketlen támadásaik rendre ugyanannak a posztnak a kezében
  halnak el, a támadás második felében rá kell tolni a nyomást —
  ott zárul a támadás, és ott a legolcsóbb a labdaszerzés. Saját
  oldalon a befejezés-felelősség tisztázása az edzés-téma. Legalább
  4 terméketlen támadás és 60% posztrészarány alatt hallgat (None).
  Felületek: /analyze + meccs-csomag (`last_holder_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 350. meccsterv-szabály),
  edzés-fókusz (371. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Menekülő-poszt: nyomás alatt kihez megy a labda.** A
  pressz-poszt azt mondja meg, melyik posztjuk veszíti el a labdát
  szorításban — az új réteg azt, hová menekül: a testközeli védő
  mellett meghozott passzokat a FOGADÓ posztjához írja. Edzőileg ez
  teszi a presszt labdaszerzéssé: ha szorításban a labda rendre
  ugyanahhoz a poszthoz megy, a kettőzés mögötti harmadik ember
  előre tudja, hol kell lesben állnia — a menekülő passz így nem
  kiút, hanem elfogott labda. Saját oldalon a két irányba nyíló kiút
  az edzés-téma. Legalább 5 nyomás alatti passz és 60%
  posztrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`press_outlet_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 349. meccsterv-szabály), edzés-fókusz
  (370. szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Időkéréspáros-poszt: az időkérés utáni figura tengelye.** Az
  időkérés-befejező a figura végpontját nevezi meg — az új réteg a
  tengelyt: az időkérés utáni ablakban leadott lövésekhez megkeresi a
  lövő felé menő utolsó passzt, és a lövést az (előkészítő poszt →
  befejező poszt) párhoz írja. Edzőileg a megbeszélés egy mondata: a
  fal tudja, hogy kész figura jön — ha a tengely ismert, nem csak a
  befejezőre kell figyelni, hanem az ELSŐ passzt kell elvágni, mert
  ott törik meg a figura a legolcsóbban. Legalább 3 időkérés utáni
  lövés és 60% párrészarány alatt hallgat (None). Felületek:
  /analyze + meccs-csomag (`timeout_pair_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 348. meccsterv-szabály),
  edzés-fókusz (369. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Sávváltó-poszt: melyik posztjuk vált sávot a támadásban.** Új
  mérés (nem meglévő motor lencséje): a saját támadás közben
  megszámolja, hányszor lép át egy játékos a pálya szélességének
  másik harmadába úgy, hogy ott legalább egy másodpercig marad, és a
  sávváltást a posztjához írja. Edzőileg a védekezés váltás-szabálya:
  ha a keresztmozgásuk egy posztra épül, előre el kell dönteni, hogy
  a védője KÖVETI a sávváltáson át, vagy ÁTADJA a szomszédnak — a
  bizonytalan átadásból nyílik a lyuk. Saját oldalon a
  figura-repertoár mérője. Legalább 5 sávváltás és 60%
  posztrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`lane_switch_roles`), edzői összefoglaló, felderítés
  (edzői kulcs + 347. meccsterv-szabály), edzés-fókusz (368.
  szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Elöl lógó poszt: melyik posztjuk nem ér haza védekezni.** A
  visszaérés-fegyelem rétege az embert nevezi meg — az új réteg a
  posztot: a védekezett kockákat posztonként összegzi, és megnézi,
  melyik poszt tölti az idejének nagy részét az ellenfél térfelén. A
  visszafutás-poszttól abban tér el, hogy az a kontrák VÉGÉN mért
  lemaradást nézi, ez pedig a védekezett IDŐ eloszlását. Edzőileg a
  gyors indítás iránya: az elöl lógó poszt mögött nincs védő — a
  kihozatalt az ő oldalára kell vezetni. Posztonként 200 védekezett
  kocka és 70% fölötti hazaérés mellett hallgat (None). Felületek:
  /analyze + meccs-csomag (`recovery_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 346. meccsterv-szabály), edzés-fókusz
  (367. szabály), HTML-riport (Védő-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Válasz-poszt: kapott gól után melyik posztjuk válaszol.** A
  kapott gól utáni megingás csapat-szinten mondja meg, mi történik a
  bekapott gól után — az új réteg a posztot: a kapott gólt 60
  másodpercen belül követő saját gólokat a lövő posztjához írja.
  Edzőileg a gól utáni első védekezés terve: ha a válaszuk rendre
  ugyanarról a posztról jön, a saját gólunk után azonnal az ő
  fogására kell váltani — ott törik meg a lendületük, mielőtt
  elindulna. Saját oldalon a B-s válasz-forgatókönyv az edzés-téma.
  Legalább 3 válasz-gól és 60% posztrészarány alatt hallgat (None).
  Felületek: /analyze + meccs-csomag (`response_scorer_roles`),
  edzői összefoglaló, felderítés (edzői kulcs + 345. meccsterv-
  szabály), edzés-fókusz (366. szabály), HTML-riport (Befejező-
  lencse sor), Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Emberelőnypáros-poszt: melyik tengelyen fut a 6-5 játékuk.** Az
  emberelőny-poszt a befejezőt nevezi meg — az új réteg a tengelyt:
  minden emberelőnyben leadott lövésnél megkeresi a lövő felé menő
  utolsó passzt, és a lövést az (előkészítő poszt → befejező poszt)
  párhoz írja. Edzőileg az öt emberrel is kiosztható feladat:
  hátrányban nincs elég kéz mindenre, ezért a tengelyt kell elvágni
  — az előkészítő passzsávját a fal széle zárja, a befejezőre jusson
  a kilépés. Legalább 3 emberelőny-lövés és 60% párrészarány alatt
  hallgat (None). Felületek: /analyze + meccs-csomag
  (`powerplay_pair_roles`), edzői összefoglaló, felderítés (edzői
  kulcs + 344. meccsterv-szabály), edzés-fókusz (365. szabály),
  HTML-riport (Befejező-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Javítás — kétszer definiált modul-konstansok.** Új őr-teszt
  (`test_nincs_ketszer_definialt_modul_konstans`) számolja a
  pipeline-modulok NAGYBETŰS modul-konstansait: ha egy új réteg
  elveszi egy meglévő konstans nevét, a Python csendben felülírja a
  régit, és a régi réteg küszöbe megváltozik. Az őr két valódi
  ütközést talált: a Védőmotor-poszt konstansai elvették az "Eltűnő
  védő" rétegéit (azonos érték, törékeny név → FDR_ előtag), a
  kapus-indítás oldal-küszöbe (0,65) pedig FELÜLÍRTA a
  kapus-gyengeoldal küszöbét (0,45) — az utóbbi réteg eddig csendben
  szigorúbb határral futott a dokumentáltnál, mostantól külön néven
  (`GK_OUTLET_SIDE_SHARE`) a helyes értékkel dolgozik.
- **Specialista-poszt: melyik posztot játsszák váltott sorban.** Az
  egyirányú játékosok rétege az embert nevezi meg — az új réteg a
  posztot: a fázis-besorolt kockákat posztonként összegzi, és
  megnézi, melyik poszt tölti az idejét szinte csak védekezésben
  vagy szinte csak támadásban. Edzőileg a csere-pillanat
  kihasználása: a váltott sorban játszott poszt a labda
  elvesztésekor/megszerzésekor cserélődik — a gyors középkezdés és a
  szerzés utáni azonnali indítás pont ott talál rossz embert a
  pályán. Saját oldalon a csere-fegyelem az edzés-téma. Posztonként
  120 mp mért jelenlét, csapat-szinten mindkét fázisban 60 mp, és
  80% egyoldalúság alatt hallgat (None) — a kétfázisú küszöb nélkül
  egy fél-támadásnyi felvétel is 100%-ot mutatna.
  Felületek: /analyze + meccs-csomag (`specialist_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 343. meccsterv-szabály),
  edzés-fókusz (364. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Kulcs-páros: hány réteg mutat ugyanarra a posztpárra.** A hat
  páros-lencse (elzárás-, hetes-, kontra-, gólpassz-, kettőző- és
  lepattanó-páros) egyenként egy bejáratott kettőst nevez meg — az
  új réteg összeszámolja őket, és kimondja a csapat kulcs-párosát.
  Edzőileg a meccsterv második lapja: a kulcs-poszt egy embert jelöl
  ki, a kulcs-páros egy tengelyt — a kettejük közti sáv szétvágásával
  több minta hal el egyszerre. A páros-rétegek ezzel kikerültek a
  kulcs-poszt listájából (KP_PAIRS a KP_LAYERS mellett): a
  kulcs-poszt embert keres, a kulcs-páros kettőst, a keverés
  mindkét számot hígítaná. 2 egyező réteg alatt (vagy holtversenynél)
  hallgat (None). Felületek: /analyze + meccs-csomag (`key_pair`),
  edzői összefoglaló, felderítés (edzői kulcs + 342. meccsterv-
  szabály), edzés-fókusz (363. szabály), HTML-riport (önálló
  Kulcs-páros szakasz bizonyíték-rétegekkel), kliens-csempe.
- **Lepattanópáros-poszt: melyik lövésükre ki érkezik.** A
  lepattanó-poszt az érkezőt nevezi meg — az új réteg a párost:
  minden megnyert második rohamnál az eredeti lövő és az újra lövő
  posztját párba állítja. Edzőileg a zárás sorrendje: ha az egyik
  posztjuk lövésére rendre ugyanaz a másik poszt indul be, a lövés
  zárása UTÁN azonnal az ő útját kell elállni. Saját oldalon a
  lepattanó-útvonalak bővítése az edzés-téma. Legalább 3 második
  roham és 60% párrészarány alatt hallgat (None). Felületek:
  /analyze + meccs-csomag (`rebound_pair_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 341. meccsterv-szabály),
  edzés-fókusz (362. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Kettőzőpáros-poszt: melyik védő-kettősük kettőz együtt.** A
  kettőző-poszt az egy védőt nevezi meg — az új réteg a párost: a
  kettőzött labdás kockákon a labdáshoz legközelebbi két védő
  posztpárját számolja. Edzőileg a kioldó-passz térképe: ha a
  kettőzés mindig ugyanattól a párostól jön, a kettőzés miatt
  elhagyott ember fix — a kioldó passz oda menjen, még a szorítás
  előtt begyakorolva. Saját oldalon a kettőző-páros forgatása az
  edzés-téma. Legalább 100 kettőzött kocka és 60% párrészarány
  alatt hallgat (None). Felületek: /analyze + meccs-csomag
  (`doubling_pair_roles`), edzői összefoglaló, felderítés (edzői
  kulcs + 340. meccsterv-szabály), edzés-fókusz (361. szabály),
  HTML-riport (Védő-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Gólpasszpáros-poszt: melyik tengelyen születnek a góljaik.** A
  gólpassz-poszt az adót, a kiszolgált-poszt a befejezőt nevezi meg
  — az új réteg a kettőt köti össze gólonként: az asszisztos gólokat
  az (adó poszt → befejező poszt) párhoz írja. Edzőileg a
  tengely-vágás terve: a kettős közti passzsáv a fal első számú
  zárnivalója — az adót testtel, a sávot beleéréssel. Saját oldalon
  a második gól-tengely az edzés-téma. Legalább 3 asszisztos gól és
  60% párrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`assist_pair_roles`), edzői összefoglaló, felderítés
  (edzői kulcs + 339. meccsterv-szabály), edzés-fókusz (360.
  szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Kontrapáros-poszt: melyik tengelyen futnak a kontráik.** A
  kontra-poszt a befejezőt nevezi meg — az új réteg a teljes
  tengelyt: minden lerohanásnál az első labdabirtokos (indító) és a
  lövést elengedő (befejező) posztját párba állítja. Edzőileg a
  kontra két ponton fogható: az indítóra azonnali nyomás a
  labdavesztés pillanatában, a befejező sávját az első visszaérő
  zárja. Saját oldalon a második kontra-tengely az edzés-téma.
  Legalább 3 lerohanás és 60% párrészarány alatt hallgat (None).
  Felületek: /analyze + meccs-csomag (`fast_break_pair_roles`),
  edzői összefoglaló, felderítés (edzői kulcs + 338. meccsterv-
  szabály), edzés-fókusz (359. szabály), HTML-riport (Befejező-
  lencse sor), Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Hetespáros-poszt: ki harcolja ki és ki dobja a heteseiket.** A
  hetes-kiharcoló és a hetesdobó poszt külön ismert — az új réteg a
  kettőt köti össze hetesenként: a (kiharcoló poszt → dobó poszt)
  párost számolja. Edzőileg két kiosztható feladat egyszerre: a
  kiharcoló ellen kéz nélkül, lábmunkával kell védekezni, a dobó
  szokás-irányait a kapus tanulja. Saját oldalon mindkettőhöz kell
  tartalék. Legalább 3 hetes és 60% párrészarány alatt hallgat
  (None). Felületek: /analyze + meccs-csomag (`seven_pair_roles`),
  edzői összefoglaló, felderítés (edzői kulcs + 337. meccsterv-
  szabály), edzés-fókusz (358. szabály), HTML-riport (Befejező-
  lencse sor), Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Csere-stílus: posztot tart vagy átszab a padjuk.** A
  cserehullám-rétegek a posztokat nézik külön — az új réteg a ki-be
  párokat: minden hullámban a lecserélt és a beálló játékost párba
  állítja, és megnézi, azonos posztra érkezik-e a váltás. Edzőileg:
  posztot tartó pad ellen a párosítás a csere után is érvényes;
  átszabó pad ellen a hullám utáni első támadásnál újra kell osztani
  a fogásokat. Saját oldalon a csere utáni rendeződés a téma. 3
  ki-be pár alatt hallgat (None); 70% fölött tartó, 40% alatt
  átszabó az ítélet. Felületek: /analyze + meccs-csomag
  (`swap_style`), edzői összefoglaló, felderítés (edzői kulcs + 336.
  meccsterv-szabály), edzés-fókusz (357. szabály), kliens-csempe.
- **Elzárópáros-poszt: melyik posztpárra jár az elzárás-játékuk.**
  Az elzárás-páros rétege a két embert nevezi meg — az új réteg a
  posztpárt: minden elzárt lövést az (elzáró poszt → lövő poszt)
  kettőshöz ír. Edzőileg a páros elleni felkészülés: az elzáró
  posztjának őrzője előre szól, a lövőé az elzárás előtt lép ki.
  Saját oldalon a figura tükrözése a másik oldalra az edzés-téma.
  Legalább 3 elzárt lövés és 60% párrészarány alatt hallgat (None).
  Felületek: /analyze + meccs-csomag (`screen_pair_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 335. meccsterv-szabály),
  edzés-fókusz (356. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Álló-poszt: melyik posztjuk áll labda nélkül.** Az álló támadók
  rétege az embert nevezi meg — az új réteg a posztot: a szervezett
  támadás mozgás-másodperceit és métereit a játékos posztjához
  összegzi, és megnézi, melyik posztjuk mozog érdemben a csapatátlag
  alatt. Edzőileg a besegítés-forrás: az álló posztot a védője
  otthagyhatja — befelé segíthet, kettőzhet vagy a beállóra léphet.
  Saját oldalon a labda nélküli munka az edzés-téma. Posztonként 20
  mp mért mozgás és 20% lemaradás alatt hallgat (None). Felületek:
  /analyze + meccs-csomag (`static_attacker_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 334. meccsterv-szabály),
  edzés-fókusz (355. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Letámadó-poszt: melyik posztjuk szed labdát elöl.** Az elöl
  szerző védők rétege az embert nevezi meg — az új réteg a posztot:
  a támadó térfélen született szerzéseket a szerző posztjához írja.
  Edzőileg a kihozatal-terv: a letámadó poszt oldalán tilos a
  kihozatalt vezetni — a kapus a másik oldalra indítson. Saját
  oldalon a letámadás-motor biztosítása (mögötte nyíló tér) a téma.
  Legalább 3 elöl-szerzés és 60% posztrészarány alatt hallgat
  (None). Felületek: /analyze + meccs-csomag (`high_steal_roles`),
  edzői összefoglaló, felderítés (edzői kulcs + 333. meccsterv-
  szabály), edzés-fókusz (354. szabály), HTML-riport (Védő-lencse
  sor), Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Célkereszt-poszt: melyik posztjuk előtt fejeznek be ellenük.**
  A célba vett védő rétege az embert nevezi meg — az új réteg a
  posztot: a kapott lövéseket a lövőhöz legközelebbi védő posztjához
  írja. Edzőileg kollektív felderítés: ha az ellenfelek rendre
  ugyanannak a posztnak az orra előtt fejeznek be, a minta bevált —
  a támadást oda kell szervezni, a védője elé elzárást. Saját
  oldalon a célba vett poszt segítséget kap. Legalább 5 rá-lövés és
  60% posztrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`targeted_defender_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 332. meccsterv-szabály), edzés-fókusz
  (353. szabály), HTML-riport (Védő-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Fedezett-lövő poszt: melyik posztjuk lő fedezetten is.** A
  fedezetten lövők rétege az embert nevezi meg — az új réteg a
  posztot: a testközeli védő melletti lövéseket a lövő posztjához
  írja. Edzőileg a fal takarékossága: amelyik posztjuk fedezetten
  is elhúzza a ravaszt, arra nem kell kilépni — a fedezett lövés
  alacsony értékű, elég a blokk-kéz és a mögé rendezett fal. Saját
  oldalon a lövés-szelekció az edzés-téma. Legalább 3 fedezett
  lövés és 60% posztrészarány alatt hallgat (None). Felületek:
  /analyze + meccs-csomag (`covered_shooter_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 331. meccsterv-szabály),
  edzés-fókusz (352. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Védőmotor-poszt: melyik posztjuk védő-motorja áll le.** Az
  eltűnő védő rétege az embert nevezi meg — az új réteg a posztot: a
  védő-akciókat (labdaszerzés + blokk) félidőnként a védő posztjához
  írja, és megkeresi, melyik posztjuk motorja áll le a másodikra.
  Edzőileg a második félidei támadás-irány: az első félidei kép
  alapján a pörgő védő-zónát kerülnénk — pedig a másodikra már nem
  ér oda, a szünet után pont ott kell támadni. Saját oldalon a
  védő-motor tervezett pihenője az edzés-téma. Felismert szünet
  nélkül, 3 első félidei akció és legfeljebb 1 második félidei alatt
  szólal meg. Felületek: /analyze + meccs-csomag
  (`fading_defender_roles`), edzői összefoglaló, felderítés (edzői
  kulcs + 330. meccsterv-szabály), edzés-fókusz (351. szabály),
  HTML-riport (Védő-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Áttörő-poszt: melyik posztjuk nyitja szét a falat.** Az áttörő
  játékosok rétege az embert nevezi meg — az új réteg a posztot: a
  labdás betöréseket (a kapu közeli körzetébe lépés) a betörő
  posztjához írja. Edzőileg a kettőzés-terv belső köre: az áttörő
  poszt védője segítőt kap, a betörés vonalát testtel kell zárni —
  nélküle a többiek kívül rekednek. Saját oldalon a második áttörő
  az edzés-téma. Legalább 4 betörés és 60% posztrészarány alatt
  hallgat (None). Felületek: /analyze + meccs-csomag
  (`breakthrough_roles`), edzői összefoglaló, felderítés (edzői
  kulcs + 329. meccsterv-szabály), edzés-fókusz (350. szabály),
  HTML-riport (Befejező-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Drága-eladó poszt: kinek a hibái kerülnek gólba.** A drága
  eladók rétege az embert nevezi meg — az új réteg a posztot: a
  gólba forduló (kapott góllal büntetett) eladásokat a vesztes
  posztjához írja. Edzőileg a nyereség-térkép: amelyik posztjuk
  hibái rendre gólt érnek, a felhozatalnál őt kell kettőzni-zavarni
  — nála a legnagyobb a szerezhető nyereség. Saját oldalon a nyomás
  alatti labdakezelés és a hiba utáni visszazárás az edzés-téma.
  Legalább 3 büntetett eladás és 60% posztrészarány alatt hallgat
  (None). Felületek: /analyze + meccs-csomag
  (`costly_turnover_roles`), edzői összefoglaló, felderítés (edzői
  kulcs + 328. meccsterv-szabály), edzés-fókusz (349. szabály),
  HTML-riport (Befejező-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Beérkező-poszt: melyik posztra hoz frissítést a padjuk.** A
  forgatott-poszt a lecserélteket nézi — az új réteg a beállókat: a
  cserehullámokkal érkező játékosokat a posztjukhoz írja. Edzőileg a
  cserehullám utáni figyelem-irány: ha a padjuk rendre ugyanarra a
  posztra hoz friss embert, a hullám után arra a sávra kell váltani
  — friss láb, új lendület, az addigi párosítás ott elavul. Saját
  oldalon a második sor szélesítése az edzés-téma. Legalább 3
  beállás és 60% posztrészarány alatt hallgat (None). Felületek:
  /analyze + meccs-csomag (`sub_in_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 327. meccsterv-szabály), edzés-fókusz
  (348. szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Forgatott-poszt: melyik posztjukat cserélik.** A
  cserehullám-rétegek a hullámot nézik — az új réteg a posztot: a
  lecserélt játékosokat a posztjukhoz írja. Edzőileg a
  fárasztás-terv iránya: a sokat forgatott posztra fárasztásra
  építeni hiba — oda mindig friss ember jön; a terhelés-csapdát a
  nem forgatott posztokra kell tenni. Saját oldalon a forgatás-terv
  kiegyenlítése az edzés-téma. Legalább 3 lecserélés és 60%
  posztrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`substituted_roles`), edzői összefoglaló, felderítés
  (edzői kulcs + 326. meccsterv-szabály), edzés-fókusz (347.
  szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Fáradt-fal poszt: a második félidőben melyik poszt jár át
  rajtuk.** A kapott gólok poszt-térképe a teljes meccset nézi — az
  új réteg a fáradást: a kapott gólokat félidőnként a lövő
  posztjához írja, és megkeresi, melyik poszt góljai ugranak meg
  ellenük a másodikra. Edzőileg a szünet utáni támadás-terv: a faluk
  leülő sávjából kell nyitni — ott fáradnak, ott nyílik a rés. Saját
  oldalon a sáv-frissítés (tervezett védő-csere, kondíció) az
  edzés-téma. Felismert szünet nélkül, 3 második félidei kapott gól
  és kétszeres ugrás alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`tired_conceder_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 325. meccsterv-szabály), edzés-fókusz
  (346. szabály), HTML-riport (Védő-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Fáradt-lövő poszt: kinek megy szét a lövése a második
  félidőben.** A pazarló-poszt a teljes meccset nézi — az új réteg a
  fáradást: a kaput elkerülő lövéseket félidőnként a lövő posztjához
  írja, és megkeresi, melyik posztjuk pontatlansága ugrik meg a
  másodikra. Edzőileg a szünet utáni fal-terv: fáradtan szétmegy a
  lövése — rá lehet engedni, a kilépés nála fölösleges kockázat.
  Saját oldalon a fáradt célzás-blokk és a befejezés átosztása az
  edzés-téma. Felismert szünet nélkül, 3 második félidei mellé és
  kétszeres ugrás alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`tired_shooter_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 324. meccsterv-szabály), edzés-fókusz
  (345. szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Fáradt-eladó poszt: kinek a labdái vesznek el a második
  félidőben.** Az eladás-rétegek a teljes meccset nézik — az új
  réteg a fáradást: a labdaeladásokat félidőnként a vesztes
  posztjához írja, és megkeresi, melyik posztjuk eladásai ugranak
  meg a másodikra. Edzőileg a második félidei pressz-terv: fáradtan
  nála nyílik ki a kéz — a szünet után friss védővel őt kell nyomás
  alá tenni. Saját oldalon a terhelés-menedzsment és a fáradt
  labdabiztonság az edzés-téma. Felismert szünet nélkül, 3 második
  félidei eladás és kétszeres ugrás alatt hallgat (None). Felületek:
  /analyze + meccs-csomag (`tired_turnover_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 323. meccsterv-szabály),
  edzés-fókusz (344. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Hátrapassz-poszt: melyik posztjuknál fordul vissza a játék.** A
  passz-irány rétege csapat-szinten mondja meg, mennyit játszanak
  hátrafelé — az új réteg posztonként: a kaputól legalább 1 méterrel
  távolabbi társhoz menő passzokat a passzoló posztjához írja.
  Edzőileg a pressz-jutalom: amelyik posztjuk nyomás alatt hátrafelé
  menekül, arra rá lehet menni — a hátra-passza után a fal feljebb
  tolható. Saját oldalon az előre-játék bátorság az edzés-téma.
  Legalább 5 hátra-passz és 60% posztrészarány alatt hallgat (None).
  Felületek: /analyze + meccs-csomag (`backward_pass_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 322. meccsterv-szabály),
  edzés-fókusz (343. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Térnyerő-poszt: melyik posztjuk viszi előre a labdát.** A
  labdatartó-poszt azt méri, kinél áll a labda — az új réteg azt,
  kinél halad: a labdás játékos kockái közt a támadott kapu felé
  megtett métereket a birtokos posztjához összegzi. Edzőileg a
  lendület-fék terve: a térnyerő posztot a felezőtől hátrálva kell
  fogadni — lendületbe engedni tilos. Saját oldalon a második
  labdavivő az edzés-téma. Legalább 50 labdás előre-méter és 60%
  posztrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`ball_carrier_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 321. meccsterv-szabály), edzés-fókusz
  (342. szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Előnyben-poszt: vezetésnél melyik posztjuk viszi a játékot.** A
  felzárkózás-poszt a hátrányt nézi, a hajrá-poszt a záró perceket —
  az új réteg a vezetést: a saját vezetés közben lőtt gólokat a lövő
  posztjához írja. Edzőileg a lendület-törés terve hátrányban: ha
  vezetnek, az előny-vivőjük kivétele (szoros fogás, kettőzés) a
  leggyorsabb visszaút. Saját oldalon a két lábon álló előny-tartás
  az edzés-téma. Legalább 3 előnyben lőtt gól és 60% posztrészarány
  alatt hallgat (None). Felületek: /analyze + meccs-csomag
  (`lead_scorer_roles`), edzői összefoglaló, felderítés (edzői kulcs
  + 320. meccsterv-szabály), edzés-fókusz (341. szabály),
  HTML-riport (Befejező-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Előkészítő-poszt: melyik posztjuk készíti elő a lövéseket.** A
  gólpassz-poszt csak a gólok passzait nézi — az új réteg minden
  lövését: a lövés előtti utolsó passzt a passzoló posztjához írja.
  Edzőileg a passzsáv-zárás nagyobb képe: ha a lövéseik
  előkészítése rendre egy posztról jön, az ő sávjának zárásával a
  lövéseik előkészítetlenné válnak — a lövők maguktól elhalnak.
  Saját oldalon a második előkészítő az edzés-téma. Legalább 5
  előkészítő passz és 60% posztrészarány alatt hallgat (None).
  Felületek: /analyze + meccs-csomag (`last_pass_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 319. meccsterv-szabály),
  edzés-fókusz (340. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Indító-poszt: melyik posztjuknál indul a támadás-szervezés.** A
  támadás-szakaszok a szakaszt adják — az új réteg a posztot: minden
  szakasz első labdabirtokosát megkeresi, és a szakaszt az ő
  posztjához írja. Edzőileg a korai pressz címzettje: ha a
  támadásaik rendre ugyanannál a posztnál indulnak, a felhozatalt őt
  presszingelve lehet borítani — korai nyomás rá már a felezőnél.
  Saját oldalon a második labdafelhozó az edzés-téma. Legalább 5
  szakasz és 60% posztrészarány alatt hallgat (None). Felületek:
  /analyze + meccs-csomag (`attack_starter_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 318. meccsterv-szabály),
  edzés-fókusz (339. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Beállóőr-poszt: melyik posztjuk őrzi a beállót.** A beálló-őr
  rétege az embert nevezi meg — az új réteg a posztot: az
  őrzés-kockákat az őrző (támadó-fázisból becsült) posztjához írja.
  Edzőileg az elzárás-terv magja: ha a beálló-őrzésük egy poszton
  áll, az elzárás pont őt húzza ki — a beálló felszabadul, és a
  belső biztosításuk borul. Saját oldalon a váltás-szabály az
  edzés-téma. Legalább 300 őrzés-kocka és 60% posztrészarány alatt
  hallgat (None). Felületek: /analyze + meccs-csomag
  (`pivot_guard_roles`), edzői összefoglaló, felderítés (edzői kulcs
  + 317. meccsterv-szabály), edzés-fókusz (338. szabály),
  HTML-riport (Védő-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Kilépő-poszt: melyik posztjuk lép ki a falból.** A kilépő védő
  rétege az embert nevezi meg — az új réteg a posztot: a felállt
  védekezés mért kockáit és kapu-távolságait a védő posztjához
  összegzi, és megnézi, van-e a többieknél legalább 2,5 méterrel
  előrébb álló poszt. Edzőileg: a kilépő mögött nyílik a tér —
  elzárást rá, és a háta mögé befutóval 2 az 1-et. Saját oldalon a
  kilépés mögötti biztosítás az edzés-téma. Posztonként 100 mért
  kocka, 3 mért poszt és 2,5 m mélység-többlet alatt hallgat (None).
  Felületek: /analyze + meccs-csomag (`advanced_defender_roles`),
  edzői összefoglaló, felderítés (edzői kulcs + 316. meccsterv-
  szabály), edzés-fókusz (337. szabály), HTML-riport (Védő-lencse
  sor), Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Ziccerhagyó-poszt: melyik posztjuk hagyja ki a ziccereket.** A
  ziccer-befejezők rétege az embert nevezi meg — az új réteg a
  posztot: a nagy helyzet-értékű, gól nélkül záruló lövéseket a lövő
  posztjához írja. Edzőileg a fal kockázat-kezelése: amelyik
  posztjuk a ziccert rendre kihagyja, annál a helyzetbe engedés a
  kisebbik rossz — a besegítés a biztos kezű társakra menjen. Saját
  oldalon a befejezés-gyakorlás az edzés-téma. Legalább 3 kihagyott
  ziccer és 60% posztrészarány alatt hallgat (None). Felületek:
  /analyze + meccs-csomag (`missed_chance_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 315. meccsterv-szabály),
  edzés-fókusz (336. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Blokkolt-poszt: melyik posztjuk lövéseit blokkolják.** A
  blokk-réteg a védő oldalt nevezi meg — az új réteg a megakasztott
  lövőt: minden blokkhoz megkeresi a blokk előtti utolsó támadó
  labdabirtokost, és a blokkot az ő posztjához írja. Edzőileg a fal
  bátorsága: amelyik posztjuk rendre falba lő, ellene a blokk nem
  szerencse, hanem terv — a védője bátran zárhat elé. Saját oldalon
  a lövés-előkészítés (elzárás, lövőcsel, lövés-szelekció) az
  edzés-téma. Legalább 3 blokkolt lövés és 60% posztrészarány alatt
  hallgat (None). Felületek: /analyze + meccs-csomag
  (`blocked_shooter_roles`), edzői összefoglaló, felderítés (edzői
  kulcs + 314. meccsterv-szabály), edzés-fókusz (335. szabály),
  HTML-riport (Befejező-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Hetesdobó-poszt: melyik posztjuk áll oda a hetesekhez.** A
  hetes-dobók listája az embert nevezi meg — az új réteg a posztot:
  a felismert hétméteresek kimenetel-lövéseit a dobó posztjához
  írja. Edzőileg a kapus-felkészülés és a fárasztás terve: ha a
  heteseiket rendre ugyanaz a poszt dobja, a kapus az ő
  szokás-irányait tanulja, a meccsterv pedig tudja: ha ezt a posztot
  kiveszik, a hetes-rutinjuk is vele megy. Saját oldalon a második
  kijelölt dobó a téma. Legalább 3 hetes és 60% posztrészarány alatt
  hallgat (None). Felületek: /analyze + meccs-csomag
  (`seven_taker_roles`), edzői összefoglaló, felderítés (edzői kulcs
  + 313. meccsterv-szabály), edzés-fókusz (334. szabály),
  HTML-riport (Befejező-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Javítás — az elakadt képkockát a feldolgozó átugorja.** Terepen
  látott hiba: a videó-olvasás/detektálás natív szinten beragadt egy
  fix képkockánál, és a feldolgozás örökre megállt rajta (a védő
  eddig ilyenkor feladta, és csak az addig kész részt mentette). Az
  új adagoló (StallSkippingFeed) az elakadt kockát átugorja, és egy
  folytató-olvasóval a következő képkockától megy tovább — a
  követési azonosítók megmaradnak (persist), feladás csak 20 egymást
  követő elakadás után jár. Az első kockára türelmesebb az időkorlát
  (dekóder- és modell-bemelegedés), az állapot-üzenet pedig jelzi,
  hogy a rendszer magától folytatja.
- **Újrakezdő-poszt: melyik posztjuk viszi a szünet utáni rajtot.**
  A félidő-nyitások rétege csapat-szinten mondja meg, hogyan jönnek
  ki a szünetről — az új réteg a posztot: a második félidő első tíz
  percének góljait a lövő posztjához írja. Edzőileg a szünet utáni
  párosítás terve: ha az újrakezdés rendre ugyanarra a posztra épül,
  a második félidő első tíz percében őt kell a legjobb védővel
  megfogni. Saját oldalon a B-s nyitó-forgatókönyv a téma. Felismert
  szünet nélkül, 3 gól és 60% posztrészarány alatt hallgat (None).
  Felületek: /analyze + meccs-csomag (`second_start_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 312. meccsterv-szabály),
  edzés-fókusz (333. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Elzárt-poszt: melyik védőjük akad el az elzárásokban.** Az
  elzárók rétege a támadó oldalt nevezi meg — az új réteg a
  megtalált védőt: lövésenként az elzáróval elakasztott őrző
  posztjához írja az esetet. Edzőileg az elzárás-célpont terve:
  amelyik védő-posztjuk rendre elakad, ellene oda kell vinni a
  figurákat — az ő oldalán az elzárás tisztán hagyja a lövőt. Saját
  oldalon átcsúszás- és váltás-gyakorlás a téma. Legalább 3 elakadás
  és 60% posztrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`screened_defender_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 311. meccsterv-szabály), edzés-fókusz
  (332. szabály), HTML-riport (Védő-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Kettőzött-poszt: melyik posztjukra érkezik a kettőzés.** A
  kettőzés-réteg a védő oldalt minősíti — az új réteg a megtámadott
  posztot: a két védővel szorongatott labdás kockákat a birtokos
  posztjához írja a támadó oldalon. Edzőileg kollektív felderítés:
  ha az ellenfelek kettőzései rendre ugyanarra a posztjukra
  érkeznek, a minta bevált recept — követni kell, és zárni a
  kettőzés mögött kilépő passzsávot. Saját oldalon a kettőzött
  posztnak lekapcsolódó társ és kettőzés-elleni leadás kell.
  Legalább 100 kettőzött labdás kocka és 60% posztrészarány alatt
  hallgat (None). Felületek: /analyze + meccs-csomag
  (`doubled_target_roles`), edzői összefoglaló, felderítés (edzői
  kulcs + 310. meccsterv-szabály), edzés-fókusz (331. szabály),
  HTML-riport (Befejező-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Fáradó-poszt: melyik posztjuk esik vissza a második félidőre.**
  A játékos-fáradás rétege az embert nevezi meg — az új réteg a
  posztot: a félidőnkénti átlagsebességeket a játékos posztjához
  összegzi, és megkeresi, melyik posztjuk tempója esik a
  legnagyobbat. Edzőileg a második félidő terve: a visszaeső poszt
  ellen a szünet után kell támadni — ott jön a tempó-fölény, és oda
  éri meg a friss embert időzíteni. Saját oldalon kondicionális
  blokk és korábbi pihentetés a téma. 100 cm/s tempó-alap és 20%
  esés alatt hallgat (None). Felületek: /analyze + meccs-csomag
  (`fatigue_roles`), edzői összefoglaló, felderítés (edzői kulcs +
  309. meccsterv-szabály), edzés-fókusz (330. szabály), HTML-riport
  (Befejező-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Passzív-poszt: melyik posztjuknál hal el a felállt támadás.** A
  passzív-kockázat rétege a szakaszt nevezi meg — az új réteg a
  posztot: a lövés nélküli, hosszú felállt támadások labdás kockáit
  a birtokos posztjához írja. Edzőileg a passzív jelzés terve: ha a
  terméketlen támadásaik ideje rendre ugyanannál a posztnál telik, a
  jelzés alatt őt kell nyomás alá tenni — nála jön a kényszer-lövés
  vagy az eladás. Saját oldalon a passzív-protokoll (kész befejező
  megoldás) a téma. Legalább 250 passzív labdás kocka és 60%
  posztrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`passive_holder_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 308. meccsterv-szabály), edzés-fókusz
  (329. szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Rajt-poszt: melyik posztjuk viszi a meccs elejét.** A
  nyitás-profil csapat-szinten mondja meg, hogyan rajtolnak — az új
  réteg a posztot: a meccs első tíz percének góljait a lövő
  posztjához írja. Edzőileg a meccs eleji párosítás terve: ha a
  rajtjuk rendre ugyanarról a posztról indul, az első tíz percben őt
  kell a legjobb védővel megfogni — a nyitó-motorjuk nélkül a korai
  elhúzásuk elmarad. Saját oldalon a második nyitó-megoldás a téma.
  Legalább 3 meccs eleji gól és 60% posztrészarány alatt hallgat
  (None). Felületek: /analyze + meccs-csomag
  (`opening_scorer_roles`), edzői összefoglaló, felderítés (edzői
  kulcs + 307. meccsterv-szabály), edzés-fókusz (328. szabály),
  HTML-riport (Befejező-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Kiszolgált-poszt: melyik posztjuk fejezi be a bejátszásokat.**
  A gólpassz-poszt azt mondja meg, kinek a kezéből indul a gól — az
  új réteg azt, hova érkezik: az asszisztos gólokat a befejező
  posztjához írja. Edzőileg a passzsáv-zárás címzettje: a
  kiszolgálásból élő posztot nem fogni kell, hanem éheztetni — a
  felé futó passzt elvágni, és magától elhal. Saját oldalon az
  önálló helyzet-teremtés az edzés-téma. Legalább 3 asszisztos gól
  és 60% posztrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`assisted_scorer_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 306. meccsterv-szabály), edzés-fókusz
  (327. szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Hajrákéz-poszt: melyik poszt kezén fut a végjátékuk.** A
  hajrá-labdabirtoklás rétege az embert nevezi meg — az új réteg a
  posztot: az utolsó öt perc labdás kockáit a birtokos posztjához
  írja. Edzőileg a hajrá-kettőzés címzettje: ha a végjátékuk egy
  poszt kezén fut, nem a lövőket kell fogni, hanem A kezet — ha az
  a poszt nem kap labdát, a záró figuráik el sem indulnak. Saját
  oldalon a második labdakihozó kijelölése a téma. Legalább 200
  hajrá-labdás kocka és 60% posztrészarány alatt hallgat (None).
  Felületek: /analyze + meccs-csomag (`clutch_hog_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 305. meccsterv-szabály),
  edzés-fókusz (326. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Lágypassz-poszt: melyik posztjuk passzol lágyan.** A
  passz-sebesség rétege csapat-szinten mondja meg, éles-e a
  labdajáratás — az új réteg posztonként: a 8 m/s alatti röptű
  (lágy, ívelt) passzokat a passzoló posztjához írja. Edzőileg a
  beleérő védekezés iránya: amelyik posztjuk lágyan passzol, annak a
  labdáiba bele lehet nyúlni — kilépés és passzsáv-támadás az ő
  sávjában azonnal termel. Saját oldalon a passz-élesség az
  edzés-téma. Legalább 5 lágy passz és 60% posztrészarány alatt
  hallgat (None). Felületek: /analyze + meccs-csomag
  (`soft_pass_roles`), edzői összefoglaló, felderítés (edzői kulcs +
  304. meccsterv-szabály), edzés-fókusz (325. szabály), HTML-riport
  (Befejező-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Sprint-poszt: melyik posztjuk futja a sprinteket.** A
  sprint-veszély rétege az embert nevezi meg — az új réteg a
  posztot: a mért sprinteket a futó posztjához írja. Edzőileg a
  kontra-fék terve: a sprint a kézilabdában szinte mindig átmenet —
  ha a sprintek rendre ugyanarról a posztról jönnek, labdavesztésnél
  először annak az útját kell lezárni, és tilos a fal mögé engedni.
  Saját oldalon a sprint-teher a rotáció-tervezés bemenete. Legalább
  10 sprint és 60% posztrészarány alatt hallgat (None). Felületek:
  /analyze + meccs-csomag (`sprint_threat_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 303. meccsterv-szabály),
  edzés-fókusz (324. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Középkezdő-poszt: melyik posztjuknál indul a középkezdés.** A
  középkezdés-átvevő rétege az embert nevezi meg — az új réteg a
  posztot: a kapott gól utáni első felező-környéki labdaátvételeket
  az átvevő posztjához írja. Edzőileg a gól utáni letámadás terve:
  ha a középkezdésük rendre ugyanannál a posztnál indul, a
  letámadásnak posztra szóló célpontja van — őt kell lefogni, és a
  középkezdésük megáll. Saját oldalon a kiszámítható átvevő
  variálandó. Legalább 3 átvétel és 60% posztrészarány alatt hallgat
  (None). Felületek: /analyze + meccs-csomag
  (`restart_taker_roles`), edzői összefoglaló, felderítés (edzői
  kulcs + 302. meccsterv-szabály), edzés-fókusz (323. szabály),
  HTML-riport (Befejező-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Forró-poszt: melyik posztjuk lövi a gólsorozatokat.** A forró
  kéz rétege az embert nevezi meg — az új réteg a posztot: a
  sorozatban (két vagy több szomszédos csapatgól ugyanattól a
  lövőtől) lőtt gólokat a lövő posztjához írja. Edzőileg a
  lendület-törés terve: ha a sorozataik rendre ugyanarról a posztról
  jönnek, az első gólja után azonnal reagálni kell — őrzés-váltás
  vagy kettőzés, mielőtt a második-harmadik jönne. Saját oldalon a
  második lendület-vivő kijelölése a téma. Legalább 3 sorozat-gól és
  60% posztrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`hot_hand_roles`), edzői összefoglaló, felderítés
  (edzői kulcs + 301. meccsterv-szabály), edzés-fókusz (322.
  szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Hajráhiba-poszt: melyik posztjuk adja el a labdát a hajrában.**
  A hajrá-hibázók rétege az embert nevezi meg — az új réteg a
  posztot: az utolsó öt perc labdaeladásait a vesztes posztjához
  írja. Edzőileg a záró percek pressz-terve: amelyik posztjuknál a
  végén rendre elmegy a labda, oda a hajrában kettőzés és
  passzsáv-zárás jön — ott a legolcsóbb a labdaszerzés, amikor a
  legtöbbet ér. Saját oldalon a hajrá-figurák tehermentesítése a
  téma. Legalább 3 hajrá-eladás és 60% posztrészarány alatt hallgat
  (None). Felületek: /analyze + meccs-csomag
  (`clutch_turnover_roles`), edzői összefoglaló, felderítés (edzői
  kulcs + 300. meccsterv-szabály), edzés-fókusz (321. szabály),
  HTML-riport (Befejező-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Eltűnő-poszt: melyik posztjuk tűnik el a második félidőre.** Az
  eltűnő ember rétege az embert nevezi meg — az új réteg a posztot:
  a gól-részvételeket (gól + gólpassz) félidőnként a játékos
  posztjához írja, és megkeresi, melyik posztjuk termelése hal el a
  másodikra. Edzőileg az első 30 perc terve: az eltűnő posztra
  duplán, cserével frissen tartott őrzővel kell ráállni — a második
  félidő magától megoldódik. Saját oldalon a terhelés-menedzsment
  témája. Legalább 3 első félidei részvétel és legfeljebb 1 második
  félidei alatt szólal meg; felismert szünet nélkül hallgat (None).
  Felületek: /analyze + meccs-csomag (`fading_scorer_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 299. meccsterv-szabály),
  edzés-fókusz (320. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Csendtörő-poszt: melyik posztjuk töri meg a gólcsendet.** A
  csend-törők rétege az embert nevezi meg — az új réteg a posztot: a
  300+ másodperces gólcsendet megtörő gólokat a lövő posztjához
  írja. Edzőileg a saját sorozat védelme: amikor áll a szekerük, a
  labda a válság-posztjukhoz menekül — pont a sorozatunk alatt őt
  kell a legszorosabban fogni. Saját oldalon az egy poszton álló
  csend-törés kiszámítható válság-megoldás. Legalább 3 csend-törő
  gól és 60% posztrészarány alatt hallgat (None). Felületek:
  /analyze + meccs-csomag (`drought_breaker_roles`), edzői
  összefoglaló, felderítés (edzői kulcs + 298. meccsterv-szabály),
  edzés-fókusz (319. szabály), HTML-riport (Befejező-lencse sor),
  Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Pressz-poszt: melyik posztjuk ejti a labdát szorításban.** A
  pressz-érzékeny játékosok rétege az embert nevezi meg — az új
  réteg a posztot: a nyomott (testközeli védő melletti) eladásokat a
  labdavesztő posztjához írja. Edzőileg a kettőzés iránya: amelyik
  posztjuk szorításban rendre eladja a labdát, oda a kettőzés nem
  kockázat, hanem labdaszerzés; saját oldalon a nyomás alatti kiadás
  a gyakorlandó. Legalább 3 nyomott eladás és 60% posztrészarány
  alatt hallgat (None). Felületek: /analyze + meccs-csomag
  (`press_sensitive_roles`), edzői összefoglaló, felderítés (edzői
  kulcs + 297. meccsterv-szabály), edzés-fókusz (318. szabály),
  HTML-riport (Befejező-lencse sor), Kulcs-poszt bizonyíték-réteg,
  kliens-csempe.
- **Labdatartó-poszt: melyik posztjuknál áll meg a labda.** A
  labdatartás-idő rétege az embert nevezi meg — az új réteg a
  posztot: minden mért labdás szakasz idejét a birtokos posztjához
  írja. Edzőileg a kettőzés időzítése: amelyik posztjuknál rendre
  megáll a labda, ott van idő odaérni a nyomással, és ott lassul a
  támadásuk. Saját oldalon a gyorsabb továbbítás edzés-témája.
  Legalább 60 mp mért tartás és 60% posztrészarány alatt hallgat
  (None). Felületek: /analyze + meccs-csomag (`hold_time_roles`),
  edzői összefoglaló, felderítés (edzői kulcs + 296. meccsterv-
  szabály), edzés-fókusz (317. szabály), HTML-riport (Befejező-
  lencse sor), Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Ziccer-poszt: melyik posztjuknál alakul ki a nagy helyzet.** A
  ziccer-befejezők rétege az embert nevezi meg — az új réteg a
  posztot: a BIG_CHANCE_XG feletti helyzet-értékű lövéseket a lövő
  posztjához írja. Edzőileg a megelőzés terve: ha a ziccereik rendre
  ugyanannál a posztnál alakulnak ki, a helyzetet a kialakulása
  előtt kell megfogni — korábbi besegítés és szűkítés az ő sávjában.
  Legalább 3 nagy helyzet és 60% posztrészarány alatt hallgat
  (None). Felületek: /analyze + meccs-csomag (`big_chance_roles`),
  edzői összefoglaló, felderítés (edzői kulcs + 295. meccsterv-
  szabály), edzés-fókusz (316. szabály), HTML-riport (Befejező-
  lencse sor), Kulcs-poszt bizonyíték-réteg, kliens-csempe.
- **Pazarló-poszt: melyik posztjuk lövi mellé a lövéseit.** A
  pontatlan lövők rétege az embert nevezi meg — az új réteg a
  posztot: a kaput elkerülő (mellé/blokkolt) lövéseket a lövő
  posztjához írja. Edzőileg a védekezés-takarékosság terve: amelyik
  posztjuk rendre mellé lő, arra rá lehet engedni a lövést — ott a
  kilépés fölösleges kockázat, a mellé lövés utáni kidobás pedig
  azonnali indítás. Legalább 3 kaput elkerülő lövés és 60%
  posztrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`wasteful_shooter_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 294. meccsterv-szabály), edzés-fókusz
  (315. szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Felzárkózás-poszt: melyik posztjuk hozza őket vissza hátrányból.**
  A felzárkózás-húzó rétege az embert nevezi meg — az új réteg a
  posztot: a hátrányban lőtt gólok és gólpasszok részvételeit a
  játékos posztjához írja. Edzőileg ez a vezetés megtartásának terve:
  ha vezetünk, és tudjuk, melyik posztjukon keresztül szoktak
  visszajönni, annak a kivétele (szoros fogás, korai kettőzés) a
  hátrányukat beragasztja. Legalább 3 hátrány-gól-részvétel és 60%
  posztrészarány alatt hallgat (None). Felületek: /analyze +
  meccs-csomag (`comeback_carrier_roles`), edzői összefoglaló,
  felderítés (edzői kulcs + 293. meccsterv-szabály), edzés-fókusz
  (314. szabály), HTML-riport (Befejező-lencse sor), Kulcs-poszt
  bizonyíték-réteg, kliens-csempe.
- **Hajrá-poszt: melyik posztjuk viszi a végjátékot.** A
  hajrá-emberek rétege az embert nevezi meg — az új réteg a posztot:
  a meccs utolsó öt percének góljait a lövő posztjához írja.
  Edzőileg ez az utolsó öt perc terve: szoros állásnál nem kell
  találgatni, kire fut ki a támadásuk — a záró percekben őt kell
  fogni (akár emberfogással), és az ő sávjára áll rá a kapus is.
  Saját csapatra: az egy emberre épülő hajrához B-forgatókönyv kell.
  Felületek: `/analyze` és meccs-csomag (`clutch_scorer_roles`),
  edzői összefoglaló, felderítő edzői kulcs, meccsterv-szabály (292:
  az ő hajrá-posztjuk × a ti mély padotok → friss fogó ember a záró
  percekre), edzés-fókusz (313: hajrá-forgatókönyv B-vel,
  lekapcsolódás-gyakorlattal), teendő-rangsor, a kulcs-poszt lencse
  és a meccs-jelentés Befejező-lencse táblája, kliens-csempe.

- **Emberhátrány-poszt: melyik posztjuk vállal be öt emberrel.** Az
  emberhátrány-lövők rétege az embert nevezi meg — az új réteg a
  posztot: a kiállítás-ablakokban a hátrányban lévő csapat lövéseit
  a lövő posztjához írja. Edzőileg ez az emberelőny-védelem terve:
  az ő hátrány-lövő posztjuk a kontra-fenyegetés — a saját
  emberelőnyben az ő oldalán kell a labdabiztonság, mert onnan indul
  az ellentámadásuk. Saját csapatra: az egy posztra futó
  hátrány-játékhoz második vállaló kell. Felületek: `/analyze` és
  meccs-csomag (`shorthanded_shooter_roles`), edzői összefoglaló,
  felderítő edzői kulcs, meccsterv-szabály (291: az ő
  hátrány-posztjuk × a ti kiharcolt két perceitek → az emberelőnyötök
  biztonsági terve), edzés-fókusz (312: hátrány-repertoár két
  befejezéssel), teendő-rangsor, a kulcs-poszt lencse és a
  meccs-jelentés Befejező-lencse táblája, kliens-csempe.

- **Emberelőny-poszt: melyik posztjuk fejez be a két perc alatt.**
  Az emberelőny-lövők rétege az embert nevezi meg — az új réteg a
  posztot: a kiállítás-ablakok lövéseit a lövő posztjához írja.
  Edzőileg ez az emberhátrány-terv: öt védővel a fal nem érhet
  mindenhová — ha az emberelőnyük rendre ugyanarra a posztra fut ki,
  hátrányban az ő sávját kell tartani, a többieket rá lehet engedni.
  Saját csapatra: az egy posztra futó emberelőnyhöz második kifutási
  út kell. Felületek: `/analyze` és meccs-csomag
  (`powerplay_shooter_roles`), edzői összefoglaló, felderítő edzői
  kulcs, meccsterv-szabály (290: az ő emberelőny-posztjuk × a ti sok
  két percetek → megírt hátrány-védekezés), edzés-fókusz (311:
  emberelőny-figurák két befejezési úttal), teendő-rangsor, a
  kulcs-poszt lencse és a meccs-jelentés Befejező-lencse táblája,
  kliens-csempe.

- **Kiosztás-poszt: melyik posztra jár a betörés utáni labda.** A
  kiosztás-célpont rétege az embert nevezi meg — az új réteg a
  posztot: a betörés utáni kiosztásokat a fogadó posztjához írja.
  Edzőileg ez a passzsáv-terv: ha a betöréseik után a labda rendre
  ugyanarra a posztra megy, annak a védője előre elmozdulhat a
  passzsávba, és a betörésre indulhat a kettőzés — a kiosztás
  elveszti az értelmét. Felületek: `/analyze` és meccs-csomag
  (`kickout_target_roles`), edzői összefoglaló, felderítő edzői
  kulcs, meccsterv-szabály (289: az ő kiszámítható kiosztásuk × a ti
  kettőzés-készségetek → a betörésük zsákutca), edzés-fókusz (310:
  kiosztás-variációk két opcióval induló betörővel), teendő-rangsor,
  a kulcs-poszt lencse és a meccs-jelentés Befejező-lencse táblája,
  kliens-csempe.

- **Kettőző-poszt: melyik posztjuk lép ki kettőzni.** A kettőző
  emberek rétege az embert nevezi meg — az új réteg a posztot: a
  kettőzött kockákat a másodiknak érkező védő posztjához írja.
  Edzőileg ez a kijátszás-terv: ha a kettőzésük rendre ugyanarról a
  posztról érkezik, előre tudni, hol nyílik ki a pálya — a kettőzés
  pillanatában az ő elhagyott embere felé megy az első passz, mert ő
  szabadult fel. Saját csapatra: a kiolvasható kettőzést forgatni
  kell. Felületek: `/analyze` és meccs-csomag
  (`doubling_defender_roles`), edzői összefoglaló, felderítő edzői
  kulcs, meccsterv-szabály (288: az ő kiolvasható kettőzésük × a ti
  nyomásálló passzjátékotok → minden kilépésük emberelőny),
  edzés-fókusz (309: kettőzés-forgó besegítővel), teendő-rangsor, a
  kulcs-poszt lencse és a meccs-jelentés Védő-lencse táblája,
  kliens-csempe.

- **Kulcs-poszt indoklással a meccs-jelentésben.** A jelentés
  Kulcs-poszt szekciója az ítélet mellé mostantól felsorolja, MELY
  rétegek mutatnak a megnevezett posztra (pl. "rétegek:
  Labdaszerző-poszt, Blokk-poszt, Átvert-poszt") — a magyarázható
  lánc a papíron is követhető, az edző látja, miből áll össze a
  meccsterv első lapja. Őr-teszt ellenőrzi.

- **Kulcs-poszt: teljes lencse-lefedettség + őr-teszt.** A
  kulcs-poszt összegzés mostantól mind a 17 poszt-ítéletes réteget
  számolja (bekerült az Indítás-vadász, a Bejátszó-, a Kockáztató-
  és a Vasember-poszt is), és őr-teszt figyeli, hogy minden
  "main_role" ítéletet adó pipeline-függvény szerepeljen a
  KP_LAYERS listában — új poszt-réteg többé nem maradhat ki az
  összegzésből.

- **Kockáztató-poszt: melyik posztjuk szórja el a hosszú labdákat.**
  A kockázatos passzolók rétege az embert nevezi meg — az új réteg a
  posztot: a hosszú passzokból lett eladásokat a kiinduló játékos
  posztjához írja. Edzőileg ez a labdaszerzés-terv: ha a hazárd
  labdáik rendre ugyanarról a posztról indulnak (tipikusan az
  irányítótól), az ő passzsávjába kell beállni — a sávba lépés nála
  azonnal labdát hoz, mögötte nyitott a pálya. Saját csapatra: az
  egy poszton gyűlő eladás passz-technika edzés-téma. Felületek:
  `/analyze` és meccs-csomag (`risky_passer_roles`), edzői
  összefoglaló, felderítő edzői kulcs, meccsterv-szabály (287: az ő
  kockáztató-posztjuk × a ti kontra-játékotok → az ő sávja a
  kontra-forrásotok), edzés-fókusz (308: passz-technika blokk sávba
  lépő védővel), teendő-rangsor és a meccs-jelentés Befejező-lencse
  táblája, kliens-csempe.

- **Vasember-poszt: melyik posztjuk játszik végig csere nélkül.** A
  rotáció-mélység azt mondja meg, hány emberrel játszanak — az új
  réteg azt, HOL nincs váltás: posztonként a legtöbbet pályán lévő
  játékos jelenlét-aránya, és ítélet, ha egy poszt kilóg (85%+
  jelenlét, 15 százalékponttal a mezőny fölött, 10+ perces
  felvételen). Edzőileg ez a hajrá-terv: a végigjátszó poszt a meccs
  végére elfárad — az utolsó tíz percben oda kell vinni a tempót, és
  vele szemben friss ember jöjjön; saját cserétlen posztunk ugyanígy
  figyelmeztetés. Felületek: `/analyze` és meccs-csomag
  (`iron_man_roles`), edzői összefoglaló, felderítő edzői kulcs,
  meccsterv-szabály (286: az ő vasember-posztjuk × a ti mély padotok
  → a hajrá a tiétek), edzés-fókusz (307: váltóember-építés heti
  játékperc-céllal), teendő-rangsor és a meccs-jelentés
  Befejező-lencse táblája, kliens-csempe.

- **Bejátszó-poszt: melyik posztjuk játssza be a beállót.** A
  beálló-kiszolgálók rétege az embert nevezi meg — az új réteg a
  posztot: a beállóhoz futó beadásokat a passzoló posztjához írja.
  Edzőileg ez a beálló-vonal zárásának térképe: ha a beadásaik
  rendre ugyanarról a posztról jönnek (tipikusan az irányítótól), az
  ő kezén kell a vonalba lépni, és az ő oldalán indul a kettőzés — a
  bejátszó zárása többet ér, mint a beálló birkózása. Felületek:
  `/analyze` és meccs-csomag (`pivot_feeder_roles`), edzői
  összefoglaló, felderítő edzői kulcs, meccsterv-szabály (285: az ő
  bejátszó-posztjuk × a ti beállóval szenvedő falatok → a bejátszó
  zárása a terv), edzés-fókusz (306: beadás-forgó posztonként
  begyakorolt beadás-fajtákkal), teendő-rangsor és a meccs-jelentés
  Befejező-lencse táblája, kliens-csempe.

- **Indítás-vadász poszt: melyik posztjuk vadássza az indítást.**
  Az indítás-hiba ára réteg az indító oldalt nézi — az új réteg a
  rabló oldalt: minden elveszett kapus-indításnál a labdát megszerző
  játékos posztjához ír egy rablást. Edzőileg kétirányú. Ellenük: ha
  a rablásaik rendre ugyanarról a posztról jönnek (tipikusan a
  szélső ugrik az első passzra), a saját kapus a másik oldalon vagy
  a feje fölött nyisson. Saját csapatra: az egy emberen futó
  letámadást az ellenfél egy cserével hatástalanítja. Felületek:
  `/analyze` és meccs-csomag (`outlet_hunter_roles`), edzői
  összefoglaló, felderítő edzői kulcs, meccsterv-szabály (284: az ő
  vadász-posztjuk × a ti elszórt indításaitok → megbeszélt
  indítás-terv), edzés-fókusz (305: letámadás-forgó jelre vándorló
  vadásszal), teendő-rangsor és a meccs-jelentés Védő-lencse
  táblája, kliens-csempe.

- **Kulcs-poszt: hány réteg mutat ugyanarra a posztra.** A
  poszt-lencse rétegek (kire fut ki a játékuk, hol sebezhető a
  védekezésük) egyenként egy-egy mintát mondanak ki — az új réteg
  összeszámolja őket: ha a megszólaló ítéletek zöme (3+ réteg,
  holtverseny nélkül) ugyanazt a posztot nevezi meg, az a csapat
  KULCS-POSZTJA. Edzőileg ez a meccsterv első lapja: az ellenfélnél
  egyetlen ember kezelése (fogás, zárás, kettőzés) több mintát
  kapcsol ki egyszerre; saját csapatnál az egy emberre futó játék
  kiszámíthatóság — tehermentesítés kell. Felületek: `/analyze` és
  meccs-csomag (`key_post`), edzői összefoglaló, felderítő edzői
  kulcs, meccsterv-szabály (283: a kulcs-posztjuk ismert → az ő
  kezelése az első pont), edzés-fókusz (304: tehermentesítő hét
  második felelősökkel), teendő-rangsor, a meccs-jelentés önálló
  Kulcs-poszt szekciója a lencse-táblák előtt, kliens-csempe.

- **Elzáró-poszt: melyik posztjuk áll elzárásba.** Az elzárók
  rétege az embert nevezi meg — az új réteg a posztot: az
  elzárásokat az elzáró játékos posztjához írja. Edzőileg ez a
  váltás-terv: ha az elzárásaik rendre ugyanarról a posztról jönnek
  (tipikusan a beálló), a védekezés előre tudja, honnan érkezik a
  test — az ő oldalán hangos váltás vagy átcsúszás kell, és őt
  elölről kell fogni, mert nélküle a lövőjük nem marad tisztán.
  Felületek: `/analyze` és meccs-csomag (`screen_setter_roles`),
  edzői összefoglaló, felderítő edzői kulcs, meccsterv-szabály (282:
  az ő elzáró-posztjuk × a ti gyenge elzárás-védekezésetek →
  poszt-szintű váltás-terv), edzés-fókusz (303: elzárás-variációk
  váltakozó elzáró-poszttal), teendő-rangsor és a meccs-jelentés
  Befejező-lencse táblája, kliens-csempe.

- **Átvert-poszt: melyik posztjuk mögött esnek a kapott gólok.** Az
  átvert védők rétege az embert nevezi meg — az új réteg a posztot:
  a védőhöz rendelt kapott gólokat az átvert játékos posztjához
  írja. Edzőileg ez az 1v1-térkép: ha a kapott góljaik rendre
  ugyanannak a posztnak a párharc-vereségéből esnek, oda kell vinni
  az 1v1-et — a figura az ő emberét támadja, elzárás is hozzá
  terelje a lövőt. Saját csapatra: a sokat átvert posztunk mellé
  besegítő váltás és párharc-edzés kell. Felületek: `/analyze` és
  meccs-csomag (`beaten_defender_roles`), edzői összefoglaló,
  felderítő edzői kulcs, meccsterv-szabály (281: az ő átvert
  posztjuk × a ti 1v1-erőtök → a figura célpontja adott),
  edzés-fókusz (302: párharc-blokk besegítő váltással + videó),
  teendő-rangsor és a meccs-jelentés Védő-lencse táblája,
  kliens-csempe.

- **Visszafutás-poszt: ki marad le a visszarendeződésben.** Az
  ellenfél kontráinak kifutásakor megnézi, a védekező csapat melyik
  mezőnyjátékosa van legmesszebb a saját kapujától, és a lemaradást
  a posztjához írja. Edzőileg két olvasat. Ellenük: ha rendre
  ugyanaz a posztjuk marad elöl, a saját kontrát tudatosan az ő
  sávjába kell vezetni — ott a pálya üres. Saját csapatra: a
  visszafutás sorrendje edzés-téma — kijelölt első visszafutó kell,
  és nem lehet mindig ugyanaz a lemaradó. Felületek: `/analyze` és
  meccs-csomag (`slow_retreat_roles`), edzői összefoglaló, felderítő
  edzői kulcs, meccsterv-szabály (280: az ő lemaradó posztjuk × a ti
  kontra-játékotok → az indítás célzottan az ő sávjába), edzés-fókusz
  (301: visszafutás-staféta sípszóra mérve), teendő-rangsor és a
  meccs-jelentés Védő-lencse táblája, kliens-csempe.

- **Védő-lencse a meccs-jelentésben.** A Befejező-lencse táblába
  időközben védő-oldali ítéletek is kerültek — most szétválik: a
  Befejező-lencse a támadó-oldali "kire fut ki a játékuk" ítéleteké
  (poszt-nyomás, időkérés-, kontra-, lepattanó-, 7a6-befejező,
  gólpassz-poszt, hetes-oldal), az új Védő-lencse pedig a "hol
  sebezhető a védekezésük" térképe: melyik sáv blokkol
  (Blokk-poszt), hol szakad be a hetes (Hetes-okozó poszt), ki
  gyűjti a kétperceket (Kiülő-poszt), ki szedi a labdákat
  (Labdaszerző-poszt). Edzői olvasat: az egyik tábla azt mondja, KIT
  fogj, a másik azt, HOVÁ támadj — őr-teszt mindkettőre.

- **Kiülő-poszt: melyik posztjuk gyűjti a kétperceket.** A "ki ült
  ki" réteg az embert nevezi meg — az új réteg a posztot: a
  kiállításokat a kiülő játékos posztjához írja. Edzőileg két olvasat
  egyszerre. Ellenük: ha a kétperceik rendre ugyanarról a posztról
  jönnek, a meccs elején oda kell vezetni a játékot — az az ember
  hamar behúzza az első kettőt, és onnantól vagy hiányzik, vagy
  fékezve véd. Saját csapatra: az egy poszton gyűlő két perc
  rendszer-hiba (hiányzó besegítés), nem pech. Felületek: `/analyze`
  és meccs-csomag (`suspended_roles`), edzői összefoglaló, felderítő
  edzői kulcs, meccsterv-szabály (279: az ő kiülő-posztjuk × a ti
  kiállítás-kiharcolótok → meccs eleji párosítás-terv), edzés-fókusz
  (300: szituációs 1v1 besegítővel + videó), teendő-rangsor és a
  meccs-jelentés Befejező-lencse táblája, kliens-csempe.

- **Hetes-okozó poszt: melyik sávjuk szakad be hetessel.** A
  hetes-okozó védők rétege az embert nevezi meg — az új réteg a
  posztot: az okozott heteseket az okozó védő posztjához írja, így a
  minta akkor is látszik, ha a nevek meccsről meccsre cserélődnek.
  Edzőileg ez a betörés-térkép: ha a heteseik rendre ugyanazon a
  poszton szakadnak be, az a sáv kézzel véd a lábmunka helyett — oda
  érdemes betörést vezetni, mert gól vagy hetes lesz belőle (idővel
  kiállítás). Felületek: `/analyze` és meccs-csomag
  (`seven_conceder_roles`), edzői összefoglaló, felderítő edzői
  kulcs, meccsterv-szabály (278: az ő beszakadó sávjuk × a ti biztos
  hetes-lövőtök → a betörés kétszeresen fizet), edzés-fókusz (299:
  lábmunka-gyakorlat tiltott kézhasználattal), teendő-rangsor és a
  meccs-jelentés Befejező-lencse táblája, kliens-csempe.

- **7a6-befejező poszt: kire fut ki a hetedik ember játéka.** A
  7 a 6 rétegei eddig azt mondták meg, MIKOR és MENNYIT játsszák a
  lehozott kapust — az új réteg azt, KIRE: az üres-kapus szakaszok
  alatti lövéseiket a lövő posztjához írja. Edzőileg a 7 a 6 értelme
  a túlterhelés; ha a lövéseik rendre ugyanarról a posztról jönnek, a
  hetedik ember játéka kiszámíthatóvá vált — a lehozott kapus
  felismerésekor a védekezés első dolga oda sűríteni, és minden
  labdaszerzés üres kapura támadható. Felületek: `/analyze` és
  meccs-csomag (`seven_six_finisher_roles`), edzői összefoglaló,
  felderítő edzői kulcs, meccsterv-szabály (277: az ő kiszámítható
  7 a 6-uk × a ti labdaszerzésetek → besűrítés, a szerzés mögött üres
  a kapu), edzés-fókusz (298: 7 a 6 két kijátszási úttal),
  teendő-rangsor és a meccs-jelentés Befejező-lencse táblája,
  kliens-csempe.

- **Blokk-poszt: melyik posztjuk blokkol.** A blokkolt lövések
  rétege az embert nevezi meg — az új réteg a posztot: a blokkokat a
  blokkoló játékos posztjához írja. Edzőileg ez a lövés-előkészítés
  térképe: ha a blokkjaik zöme egy posztról jön (tipikusan a középső
  védőtől), az ő sávjába átlövéssel próbálkozni ajándék labdavesztés
  — oda csak elmozgatás UTÁN szabad lőni: a figura először őt húzza
  ki, és a lövés a megnyílt sávba megy. Felületek: `/analyze` és
  meccs-csomag (`role_block_sources`), edzői összefoglaló, felderítő
  edzői kulcs, meccsterv-szabály (276: az ő blokk-posztjuk × a ti
  falba lövésetek → előkészítés nélkül oda nem megy lövés),
  edzés-fókusz (297: blokk-staféta, a blokk a falé legyen, ne egy
  emberé), teendő-rangsor és a meccs-jelentés Befejező-lencse
  táblája, kliens-csempe.

- **Lepattanó-poszt: ki lő másodszor.** A második roham rétege
  csapat-szinten mondja meg, harcolnak-e a lepattanóért — az új réteg
  azt, KI: minden megnyert második rohamnál a második lövést az
  elengedő játékos posztjához írja. Edzőileg ez a zárás sorrendje: a
  lövés pillanatában a fal dolga nem ér véget — ha a második lövéseik
  rendre ugyanarról a posztról jönnek (tipikusan a beálló), a zárás
  utáni első mozdulat őt kivenni a lepattanóból, nem a lövőt nézni.
  Felületek: `/analyze` és meccs-csomag (`second_chance_roles`), edzői
  összefoglaló, felderítő edzői kulcs, meccsterv-szabály (275: az ő
  lepattanó-posztjuk × a ti visszaengedett második rohamaitok → egy
  kijelölt ember, egy mozdulat), edzés-fókusz (296: lepattanó-játék
  váltakozó második hullámmal), teendő-rangsor és a meccs-jelentés
  Befejező-lencse táblája, kliens-csempe.

- **Labdaszerző-poszt: melyik posztjuk nyeri a labdákat.** A
  labdaszerzők rétege az embert nevezi meg — az új réteg a posztot: a
  birtokos-váltásokat a szerző játékos posztjához írja (a küszöb itt
  50%, mert a labdaszerzés a legszórtabb esemény). Edzőileg mindkét
  irányban éles: ellenük az ő szedő-posztjuk sávjába csak biztonsági
  passz mehet, a támadást a másik oldalon kell átvezetni; a saját
  oldalon az egy emberen álló letámadás egyetlen cserével
  hatástalanítható — a nyomás-váltást több posztra kell szétosztani.
  Felületek: `/analyze` és meccs-csomag (`role_steal_sources`), edzői
  összefoglaló, felderítő edzői kulcs, meccsterv-szabály (274: az ő
  szedő-posztjuk × a ti nyomás alatti eladásaitok → a sávját kerülő
  labdavezetés), edzés-fókusz (295: nyomás-váltó gyakorlat),
  teendő-rangsor és a meccs-jelentés Befejező-lencse táblája,
  kliens-csempe.

- **A lövésválasztás is a teendő-rangsorban.** A lövésválasztás
  rétege ("volt-e jobb szabad helyzet a pályán") eddig kimaradt a
  rangsorból — pedig az ítélete kiosztható feladat. Mostantól a
  "felkészülés" családban rangsorolódik, és az őr-teszt számon kéri.

- **Gólpassz-poszt: kinek a kezéből indulnak a góljaik.** A
  gólpassz-forrás a pálya-zónát nézi, a gólpassz-hálózat az embert — az
  új réteg a POSZTOT: a gólokhoz rendelt gólpasszokat az adó játékos
  posztjához írja. Edzőileg ez a védekezés célpont-váltása: a
  befejező-lencse megmondja, ki fejez be, de ha a gólok nagy része
  ugyanannak a posztnak (tipikusan az irányítónak) a kezéből INDUL, a
  lövés zárása késő — tőle a passzt kell elvenni, és a lövők maguktól
  elhalkulnak. Felületek: `/analyze` és meccs-csomag
  (`role_assist_sources`), edzői összefoglaló, felderítő edzői kulcs,
  meccsterv-szabály (273: az ő elosztójuk × a ti kettőzési
  hajlandóságotok → a kettőzés célpontja az elosztó, nem a lövő),
  edzés-fókusz (294: második elosztó gyakorlat), teendő-rangsor és a
  meccs-jelentés Befejező-lencse táblája, kliens-csempe.

- **Befejező-lencse a meccs-jelentésben.** A négy "kire fut ki"
  ítélet (poszt-nyomás, időkérés-befejező, kontra-poszt, hetes-oldal)
  eddig az app felderítő-csempéin és a teendő-rangsorban élt — a
  nyomtatható HTML meccs-jelentésből hiányzott. Új szekció gyűjti őket
  egy táblába, a figura-tábla mellé; üres meccsen a szekció el sem
  készül. A figura-tábla emellett új "Befejező poszt" oszlopot kapott
  (a figura-befejező rétegből): a magas gól-arányú figura mellett most
  az is látszik, MERRE fut ki.

- **Hetes-oldal: merre dobják a heteseiket.** A hetes-mérleg eddig
  megmondta, hogyan konvertálnak — azt nem, HOVA: az új réteg a
  hetes-kimenetelek irány-jelét (bal/közép/jobb a dobó szemszögéből)
  csapatonként összegzi. Edzőileg ez a kapus-megbeszélés legolcsóbb
  mondata: a hetes az egyetlen helyzet, ahol a kapusnak van ideje
  DÖNTENI, merre vetődik, a dobók pedig nyomás alatt a begyakorolt
  sarkukat keresik. Ha a heteseik jelentős része ugyanarra az oldalra
  megy, a kapus tudatosan arra vetődhet; ha szórnak, a dobó
  mozdulatából kell olvasnia. Felületek: `/analyze` és meccs-csomag
  (`seven_shot_directions`), edzői összefoglaló, felderítő edzői kulcs,
  meccsterv-szabály (272: az ő kiszámítható hetes-oldaluk × a ti
  kapusotok gyenge mérlege → előre eldöntött vetődés), edzés-fókusz
  (293: hetes-sorozat edzői jelre, fáradtan), kliens-csempe.

- **Kontra-poszt: melyik posztjukon zárul a lerohanás.** A
  kontra-befejezők rétege a gólt szerző EMBERT nevezi meg — ez a
  posztot, és nemcsak a gólnál: a lerohanás-szakaszok minden lövését az
  elengedő játékos posztjához írja. Edzőileg ez a visszafutás
  sorrendje: visszarendeződéskor nem lehet mindenkit egyszerre
  felvenni — azt kell először, aki a kontrát ténylegesen befejezi. Ha
  szórt a befejezésük, a labdát kell késleltetni, nem a befejezőt
  keresni. Felületek: `/analyze` és meccs-csomag (`role_fast_breaks`),
  edzői összefoglaló, felderítő edzői kulcs, meccsterv-szabály (271: az
  ő egy-csatornás kontrájuk × a ti lassú visszarendeződésetek → egy
  kijelölt ember, nem a labda), edzés-fókusz (292: kétsávos
  kontra-gyakorlat), teendő-rangsor ("felkészülés" család),
  kliens-csempe.

- **Lövésválasztás: volt-e jobb helyzet a pályán.** A
  helyzetminőség (xG) eddig megmondta, MILYEN helyzetekből lőnek — azt
  viszont nem, hogy a lövés pillanatában volt-e JOBB. Az új réteg
  minden lövésnél összeveti az elengedő játékos helyzetértékét a
  legjobb SZABADON álló csapattársáéval; ha a társé érdemben nagyobb, a
  lövés "eldobott jobb helyzet". Edzőileg ez a támadó-játék fegyelme: a
  magas arány nem azt jelenti, hogy rosszul lőnek, hanem hogy nem
  néznek fel — a fal ellenük tudatosan hagyhatja a rossz szögű lövést,
  a szabad társat viszont zárni kell. Felületek: `/analyze` és
  meccs-csomag (`shot_choice_quality`), edzői összefoglaló, felderítő
  edzői kulcs, meccsterv-szabály (270: az ő rossz lövésválasztásuk × a
  ti széles falatok → tömörítés), edzés-fókusz (291: döntés-játék, ahol
  a lövés csak a szabadabb társ megnevezése után érvényes),
  kliens-csempe.

- **A befejező-lencse eljut a teendő-rangsorba.** A három új
  befejező-réteg (poszt-nyomás, figura-befejező, időkérés-befejező)
  ítélete eddig csak a saját felületén látszott: a rangsor (a
  háromszáz rétegből öt teendő) nem olvasta őket, így a legkonkrétabb
  mondatok — "őt ki kell zárni", "a figura indulásakor csússz",
  "időkérés után ő kapja az embert" — csak böngészéssel voltak
  megtalálhatók. Most a "felkészülés" családban rangsorba kerülnek, és
  az őr-teszt is számon kéri őket.

- **Időkérés-befejező: az időkérés után kire játszanak.** Az időkérés
  utáni első támadás rétege eddig megmondta, van-e kész figurájuk — azt
  viszont nem, hogy a kész figura kire fut ki. Az új réteg az
  újraindítás utáni 40 másodperc lövéseit az elengedő játékos
  posztjához írja. Edzőileg ez a legolcsóbb felkészülés a meccsen
  belül: az időkérés után a fal TUDJA, hogy figura jön — csak azt nem,
  kire. Ha a lövések nagy része ugyanarra a posztra megy, a
  megbeszélésen egy mondat elég ("időkérés után rá figyelünk, elé
  állunk, a többit hagyjuk"); ha szórt, arra a támadásra nem érdemes
  külön embert rendelni. Felületek: `/analyze` és meccs-csomag
  (`timeout_finisher`), edzői összefoglaló, felderítő edzői kulcs,
  meccsterv-szabály (269: az ő időkérés-befejezőjük × a ti ritka
  kettőzésetek → egy előre megbeszélt kettőzés arra az egy támadásra),
  edzés-fókusz (290: két időkérés-figura azonos indítással),
  kliens-csempe.

- **Figura-befejező: melyik figurájuk kire fut ki.** A
  figura-hatékonyság eddig megmondta, melyik figurájuk veszélyes — azt
  viszont nem, hogy a veszélyes figura KIRE fut ki. Az új réteg minden
  figura-klaszterhez összegyűjti a benne esett lövéseket, és az
  elengedő játékos posztjához írja őket. Edzőileg ez a felismerés
  haszna: egy figurát a fal a második-harmadik ismétlésre megismer, de
  a felismerésből csak akkor lesz védés, ha tudja, mire fut ki. Ha a
  lövések nagy része ugyanarra a posztra megy, a fal már a figura
  INDULÁSAKOR arra az oldalra csúszhat, ahelyett hogy a lövés
  pillanatában reagálna. A felderítésben a figura-azonosító nem
  tárolható (meccsenként újra képződik), ezért a DARABSZÁM megy át:
  hány figurájuk mérhető, ebből hány kiszámítható befejezésű, és
  melyik posztra. Felületek: `/analyze` és meccs-csomag
  (`setplay_finishers`), edzői összefoglaló, felderítő edzői kulcs,
  meccsterv-szabály (268: az ő kiszámítható figuráik × a ti lassú
  fal-csúszásotok → a csúszás a figura indulására induljon),
  edzés-fókusz (289: második befejező a saját figuránkba),
  kliens-csempe.

- **Poszt-nyomás: melyik posztjuk fejez be fedezetten is.** Eddig
  csapat-szinten tudtuk, mennyit ér a fedezés ellenük
  (`pressure_finishing`) — azt viszont nem, KIN fog. Az új réteg minden
  lövésnél megkeresi az elengedő játékost, és az elengedés kockáján a
  legközelebbi mezőny-védő távolságát: a két méteren belüli lövés
  fedezett. A fedezett lövések gólarányát a lövő posztjához írja.
  Edzőileg ez a "kire lépj ki" döntés: aki fedezetten is belövi, azt ki
  kell zárni (a kinyújtott kéz nála kevés), aki fedezetten beesik, arra
  épp rá kell engedni — a fal nem tud mindenkire kilépni. Felületek:
  `/analyze` és meccs-csomag (`role_pressure_finish`), edzői
  összefoglaló, felderítő edzői kulcs, meccsterv-szabály (267: az ő
  hidegvérű posztjuk × a ti amúgy is szoros falatok → kizárás, nem
  kilépés), edzés-fókusz (288: a fedezetten beeső posztunknak kontakt
  alatti befejezés gyakorlása), kliens-csempe.

- **A teszt-csomag negyedével gyorsabb (8:20 → 6:10).** A recept
  minden commit előtt teljes futást ír elő, a csomag viszont nyolc perc
  fölé nőtt — ez már elriaszt a futtatástól, és pont az őrzés vész el
  vele. A mérés (`--durations`) szerint négy meccsjelentés-teszt vitte
  az idő negyedét: 12-20 perces jeleneteket építettek 25 fps-sel, és a
  teljes jelentés minden réteget végigfuttat rajtuk. A jelenetek
  MÁSODPERCEKBEN vannak megfogalmazva (a rétegek is abból számolnak),
  ezért ahol nem kellett lövés-fizika, ötödére csökkent a
  képkocka-sebesség; ahol igen, ott a kitöltő szakaszok rövidültek az
  arányok megtartásával. A leglassabb teszt 65 → 12 másodperc, a
  jelenetek jelentése változatlan.

- **A TRL-4 bizonyíték-út őrzés alá került.** A pontosság-mérés
  útja — annotációs sablon → kézi javítás → mérés → dátumozott,
  verziózott naplósor — a pályázat egyik fő bizonyítéka, de a
  parancssori eszköznek eddig csak a riport-ága volt tesztelve. A
  `--sablon` és a `--jegyzokonyv` kapcsoló fedetlen maradt: ha
  elromlanak, az a valós felvétel érkezésekor derült volna ki, amikor
  a legdrágább. Végigpróbáltam a teljes utat egy szimulált meccsen
  (működik), és mindkét ágra teszt került — a napló-írásnál arra is,
  hogy a meglévő tartalom ne vesszen el.

- **A fejlődés-követés végre látja a befejezést is.** A trend eddig
  csak SKALÁR mezőket tudott követni, a poszt-lencse viszont
  darabszám/összeg szótárakban áll (hogy meccsek közt pontosan
  összegződjön) — így egy tipikus szezon-kérdés megválaszolhatatlan
  volt: "közelebbről fejezünk-e be, mint ősszel?". Mostantól két
  SZÁRMAZTATOTT mutató is bekerül: **befejezés-távolság** (a csökkenés
  a javulás — közelebbről lőni jobb) és **lövéserő**. Az átlag mindig
  frissen számolódik az összegekből. Ha valamelyik időszakban nincs
  elég mért lövés (nyolc alatt), a mutató KIMARAD — nem látszik
  nulla-esésnek.

- **A poszt-lencse ítéletei eljutnak a teendő-rangsorba.** A rangsor
  háromszáz rétegből ötöt emel ki, öt kimondott család szerint (ár →
  ember → szünet → fáradás → állás). A poszt-lencse lövés-rétegei
  egyikbe sem tartoztak, így az ítéletük ("őt ki kell zárni", "a kapus
  arra állhat rá") csak böngészéssel volt megtalálható. Új, HATODIK
  család: **felkészülés** — poszt-profil, ami nem hiba és nem romlás,
  hanem állandó tulajdonság. Szándékosan a sor VÉGÉN áll: nem tolja el
  a sürgősebb jelzéseket, viszont ha azok hallgatnak (rövid felvétel,
  kevés esemény), a lista nem marad üresen. Őr-teszt rögzíti a család
  helyét és azt, hogy minden nyilvántartott család szerepel a
  sorrendben.

- **Kapus-felkészítés posztonként: egy tábla három réteg helyett.** A
  poszt-lencse kapus-hármasa (honnan lő, milyen keményen, merre lő)
  három külön csempeként szóródott szét a 300-as mutató-falon — a
  kapusedző háromszor kereste meg ugyanazt a posztot. Mostantól a
  felderítő jelentés kap egy külön szakaszt (képernyőn kártya, papíron
  táblázat), ahol posztonként egy sorban áll mind a három. Ahol még
  nincs elég mért lövés, ott KIMONDOTT hiány-jel ("—") áll, nem nulla
  vagy üres cella, és a lábjegyzet megmondja, mennyi kellene. Adat
  nélkül a szakasz elmarad — üres fejléc rosszabb, mint a hiánya. A
  jelentés ugró-sávjába is bekerült.

- **Poszt-kapuoldal: melyik sarokra állhat rá a kapus.** Új elemző
  réteg, és a poszt-lencse kapus-hármasának harmadik darabja: a
  lövéstávolság megmondja, MEDDIG lépj ki, a lövéserő azt, MIKOR
  indulj, ez pedig azt, MERRE. A lövő-kapuoldal eddig névre mondta meg,
  ki kiszámítható — ez posztra, tehát akkor is használható, ha az
  ellenfél mást állít be. Ha egy posztjuk a góljainak 60%-át ugyanabba
  a sarokba lövi, a kapus arra állhat rá, a fal pedig a másikat zárja.
  Négy gól alatt, illetve szétszórt oldalaknál nincs ítélet. Felületek:
  elemzés-végpont, meccs-csomag, edzői összefoglaló, felderítő kulcsok,
  meccsterv (266. szabály), edzés-fókusz (287. szabály:
  kapuoldal-váltás a kapus MOZDULATÁRA döntve), felderítés-képernyő
  csempéje.

- **Az új-elemzés varázsló magyarázata őrzés alá került.** A "Tovább"
  gomb letiltva marad, amíg a lépés nincs kész — magyarázat nélkül ez
  néma zsákutca lenne (a felhasználó egy szürke gombot néz, és nem
  tudja, mit kellene tennie). A varázsló ma mindhárom lépésnél
  megmondja, mi hiányzik vagy mivel jár a kihagyása; új őr-teszt
  rögzíti, hogy ez így is maradjon.

- **A sorrend-jelentés a másik vakfoltját is kimondja.** A szimuláció
  EGY állóképet modellez: a hazai csapat támad, a vendég 6-0-ban véd.
  Nincs birtoklás-váltás, tehát a vendég TÁMADÓ oldaláról és minden
  átmenet-rétegről ez a mérés sem mond semmit — akkor sem, ha lövések
  vannak benne. A jelentés "A mérés köre" szakasza mostantól ezt is
  leírja, őr-teszttel rögzítve.

- **A kliens-őrzések külön fájlba kerültek.** A réteg-regisztry
  füstteszt mostanra 28 tesztből 14-gyel a Flutter-felületről szólt
  (elgépelt kulcs, néma pörgettyű, nyers kivétel a képernyőn, célt nem
  találó ugró-gomb) — a fájl neve és leírása viszont a backend
  réteg-regisztrációjáról. A kliens-őrzések átkerültek a
  `tests/test_client_ui.py`-ba: azok a Dart forrásból olvasnak, nem
  kell hozzájuk se FastAPI, se szimulált meccs, ezért **0,2 másodperc
  alatt** lefutnak a regisztry 35 másodperce helyett. Aki a felületen
  dolgozik, mostantól ezt az egy fájlt futtatja.

- **Kiadás-jegyzet: a Windows-futtató kódolása elhasalt rajta.** Az
  első éles futás megbukott: a Windows-gépen a Python alapértelmezett
  kimeneti kódolása cp1252, és a magyar szöveg nyilai (→)
  `UnicodeEncodeError`-t adtak — a kiadás lépése emiatt kimaradt (a
  telepítő és a macOS-csomag addigra már fent volt, tehát a kiadás nem
  sérült). A szkript mostantól FÁJLBA ír, kimondott UTF-8 kódolással
  (`--out`), és stdout-ra íráskor is beállítja azt. Két őr-teszt
  rögzíti: a fájl-írás nem-ASCII szöveggel is működik, és a workflow a
  `--out` kapcsolót használja, nem átirányítást.

- **A frissítés-jegyzet olvashatóan jelenik meg.** A jegyzet a
  CHANGELOG-ból jön, tehát markdown (`**félkövér**`, `> idézet`,
  `## cím`, `- felsorolás`) — egy sima szövegdobozban ezek NYERSEN
  látszottak volna: a felhasználó csillagokat és kettőskereszteket
  olvasott volna éppen abban az ablakban, amit azért nyitott meg, hogy
  megértse, mi változik. Markdown-megjelenítő csomagot nem húztunk be
  emiatt (az app offline működik, a szöveg pedig felsorolás és
  bekezdés): a jelölők eltűnnek, a felsorolás pontot kap, a hármas
  üres sorok összevonódnak. Őr-teszt rögzíti.

- **A kiadás leírása a CHANGELOG-ból épül.** Az előző pont után az app
  megmutatja a GitHub-kiadás leírását a frissítés előtt — csakhogy ott
  eddig sablonszöveg állt ("Újdonságok: lásd a CHANGELOG.md-t"). A
  felhasználó tehát pont ott olvasta volna el, mi változik, és pont ott
  nem kapott választ. Mostantól a kiadási workflow a
  `scripts.release_notes` szkriptből veszi a leírást: az kiszedi a
  CHANGELOG adott verziójú szakaszát, elé teszi a telepítési
  tudnivalót mindkét platformra, és túl hosszú listát vág (a vágást ki
  is mondva). Hiányzó szakasznál a telepítési rész akkor is kimegy —
  egy elfelejtett changelog-bejegyzés miatt nem maradhat el a kiadás.
  Őr-teszt rögzíti, hogy a workflow tényleg ezt a szkriptet hívja, és
  hogy a régi sablon eltűnt.

- **A frissítés megmondja, mi változik — letöltés előtt.** A
  frissítés-ajánló eddig csak egy verziószámot mutatott, holott egy
  frissítés 200–300 MB letöltés ÉS az app újraindítása. A felhasználó
  így vakon döntött, vagy inkább nem frissített. Mostantól az ajánló
  kiírja a csomag méretét, és a **"Mi változik?"** gomb megnyitja a
  kiadás jegyzetét (a GitHub-kiadás leírását), ahonnan egyből
  frissíteni is lehet. Őr-teszt rögzíti, hogy a jegyzet eljut a
  felületig.

- **A fejlesztési recept igazodott a sorrend-függés lezárásához.** A
  `CLAUDE.md` eddig úgy írta le a sorrend-mérést, mint amiből még
  DÖNTENI kell; a döntés azóta megszületett és be is épült. Mostantól
  kimondja, hogy a lista üres, és hogy egy megjelenő réteg
  REGRESSZIÓ — nem elfogadandó állapot.

## v0.1.24 — kiadva (2026-08-06)

> Kiadás-jegyzet: a v0.1.23 óta a fejlesztés négy szálon futott.
>
> **(1) Sebesség**: a rétegek addig hívták újra ugyanazokat az
> alap-méréseket, hogy egy teljes meccs-csomag ~10 percig futott; a
> hatókörös gyorsítótár és a kocka-szintű memoizálás ezt bitre azonos
> kimenet mellett 2,4–3,2×-esére gyorsította.
>
> **(2) Poszt-lencse**: a posztok akkor is stabilak, ha a nevek
> meccsről meccsre cserélődnek, ezért a felkészülés gerince lett —
> tizenhárom új réteg (hatékonyság, gólpassz-tengely, birtoklás,
> passzháló, átvételi zóna, labdatartás, eladási zóna, eladás-ár,
> szünet- és állás-váltás, majd lövéstávolság, lövésidőzítés és
> lövéserő), egy közös Poszt-lencse szekcióval a jelentésben.
>
> **(3) Használhatóság**: a felderítés-képernyő 297 mérőszáma
> kereshető, csoportosított fallá lett, az edzői összefoglaló 43
> mondatos bekezdése felsorolássá, a kezdőlap nyolc néma ikonja
> nevesített művelet + egy menü. Ide tartozik a hibaüzenetek emberi
> nyelvre fordítása, a "mire várunk és meddig" várakozó nézet, a
> jelentés-ugrósáv, az olvasható mutató-csempék és a megszólaló üres
> panelek is.
>
> **(4) Mérési igazság**: ez a kör hozta a legfontosabb javításokat. A
> lövő-hozzárendelés kapu-felé torzítása — amely az előző jegyzet
> szerint még NYITOTT korlát volt, és emiatt maradt ki a tervezett
> poszt-lövéstávolság réteg — MEGSZŰNT: a felismerés az elengedés
> pillanatát keresi meg, a réteg pedig (két testvérével együtt)
> leszállt. Kiderült továbbá, hogy a szimuláció egyáltalán nem termelt
> lövést, tehát száznál több réteg üres bemenettel futott minden
> mérésben; és hogy a kapus-felismerés holtversenynél a fal középső
> védőjét jelölte kapusnak a valódi kapus helyett. Ez utóbbi volt a
> sorrend-függés valódi oka: a mérés 313 rétegből 48-at talált
> érintettnek, a javítás után egyet sem.


- **Kapus-felismerés: a fal középső védőjét jelölte kapusnak.** A
  felismerés kapunként egy játékost választ, a kapuelőtérben töltött
  idő aránya alapján — holtversenynél viszont a beolvasás SORRENDJE
  döntött. A szimulált meccsen ez konkrétan azt jelentette, hogy a 6-0
  fal középső védője (13) kapta meg a kapus szerepet a valódi kapus
  (17) helyett: mindketten 100%-ban a kapuelőtérben voltak. A védő így
  kiesett minden védekező számításból. Mostantól azonos aránynál a
  KAPUHOZ KÖZELEBBI nyer — a kapus a gólvonalon áll, a fal embere hat
  méterrel kijjebb.
  Ez volt a sorrend-függés valódi oka: a mérés **313 rétegből 48-at**
  talált érintettnek, a javítás után **egyet sem**. A
  `docs/SORREND_FUGGES.md` listája üres.

- **A kiértékelés sorrendje már nem befolyásolja az eredményt.** A
  kapus-jelölés (`role = "kapus"`) eddig CSAK akkor történt meg, ha épp
  lefutott egy kapus-réteg — több mint ötven réteg viszont a szerepből
  dolgozik (a kapust nem számolja védőnek, birtokosnak, lövőnek).
  Ugyanaz a réteg tehát más számot adott attól függően, hányadikként
  értékeltük ki; ezt mérte a `docs/SORREND_FUGGES.md`. Mostantól a
  jelölés a `primitive_cache` hatókör NYITÁSAKOR megtörténik, tehát a
  termék minden összeállítása (meccs-csomag, elemzés-végpontok,
  felderítés, edzői összefoglaló) sorrend-független. Őr-teszt rögzíti
  a garanciát. A jelentés listája továbbra is hasznos: azt mondja meg,
  mely rétegek SZEREP-FÜGGŐK — ezeket hatókörön kívül, közvetlenül
  hívva más számot lehet kapni, mint a terméken belül; a jelentés
  mostantól ezt ki is mondja.

- **A réteg-őrzés végre látja a lövés-rétegeket is.** Az "egyetlen
  réteg sem bukhat el némán" füstteszt eddig 8 másodperces szimulált
  meccsen futott — lövés nélkül. A lövés-alapú rétegek így üres
  szerkezetet adtak vissza, a teszt pedig zölden átment anélkül, hogy
  a rétegek érdemi ága egyszer is lefutott volna. A mintameccs
  mostantól LŐ (40 mp, 8 lövés azonosított lövővel), és új őrzés
  követeli meg, hogy a lövés-rétegek ne üresen jöjjenek vissza — a
  "kulcs ott van" ellenőrzés önmagában gyenge volt. A füstteszt 11-ről
  38 másodpercre lassult; cserébe több mint száz réteg érdemi ága
  végigfut minden körben.

- **A szimuláció tud lőni — és ezzel száz réteg került mérés alá.** A
  `simulate_ground_truth` eddig CSAK mozgást modellezett: egyetlen
  lövés-eseményt sem termelt. Emiatt a lövés-alapú rétegek (több mint
  száz) minden szimulációs mérésben üres bemenettel futottak — a
  sorrend-mérés például "nem sorrend-függőnek" LÁTTA őket, holott
  semmit nem mért rajtuk. Mostantól opcionálisan (`shots_per_min`) a
  hazai csapat rendszeresen lő is, a mezőnyjátékosok körbejárva, és a
  labda a lövő kezéből indul, tehát minden lövésnek van azonosított
  lövője. Az alapértelmezés KIKAPCSOLT: a meglévő mérések és tesztek
  erre a viselkedésre épülnek. A sorrend-mérés viszont bekapcsolva
  fut, és rögtön **13 újabb sorrend-függő réteget** talált
  (38 → 50): `ball_winners`, `beaten_defenders`, `clutch_ball_hogs`,
  `corridor_goals`, `gk_shorthanded_saves`, `momentum`,
  `powerplay_shooters`, `steal_launch`, `steal_types`,
  `targeted_defenders`, `transition_offense`, `unpressured_assists`,
  `wrongfooted_keeper` — ezekről eddig egyszerűen nem volt adat.

- **A sorrend-mérés kimondja, mit NEM tud.** A sorrend-függés
  jelentése szimulált meccsen dolgozik, az viszont mozgást modellez és
  lövés-eseményt nem termel. A lövés-alapú rétegek ezért üres
  bemenettel futnak: mindkét ágon ugyanazt a semmit adják, tehát "nem
  sorrend-függőnek" LÁTSZANAK — holott a mérés róluk nem mond semmit.
  Ez a legkönnyebben félreolvasható pont a jelentésben, ezért mostantól
  külön szakasz mondja ki, őr-teszttel rögzítve. A jelentés újra is
  generálva: 313 réteg összevetve, 38 sorrend-függő.

- **A demó góljainak van lövőjük.** A demó meccs gól-epizódjaiban a
  labda a semmiből indult a kapu felé — elengedés-pillanat nélkül. A
  javított lövő-felismerés ezért a demóban a négy gólból kettőnél nem
  talált lövőt, és a játékos-bontású lövés-rétegek üresen maradtak
  volna: aki először nyitja meg a programot, épp azokat a rétegeket
  nem látta volna működni. Mostantól minden demó-gólnak KIJELÖLT lövője
  van (a hazai mezőnyjátékosok közül, a hármas sorozatban más-más
  emberrel), aki a lövés idejére a 9 méteres vonalra áll, kezében a
  labdával.

- **Poszt-lövéserő: melyik posztra készüljön a kapus.** Új elemző
  réteg. A lövő-erő eddig NÉVRE mondta meg, ki a bombázó — ez posztra
  mondja. A név meccsről meccsre cserélődhet (sérülés, csere, más
  felállás), a poszt viszont marad, ezért a kapus felkészítése
  poszt-alapon tart. Edzői olvasat: a kemény lövésre a kapusnak
  korábban kell indulnia és inkább a szöget zárnia, mint reagálnia; a
  helyezett lövésnél fordítva, ott a kivárás fizet. A fal ugyanezt a
  döntést hozza. Ha nem tudjuk, melyik posztjuk melyik, a kapus
  mindkettőre félig készül. Négy lövés alatt, illetve 12 km/h-nál
  kisebb eltérésnél nincs ítélet. Felületek: elemzés-végpont,
  meccs-csomag, edzői összefoglaló, felderítő kulcsok, meccsterv (265.
  szabály: az ő kemény lövő posztjuk × a ti kapusotok tempó-profilja),
  edzés-fókusz (286. szabály), felderítés-képernyő csempéje.

- **Poszt-lövésidőzítés: ki lő korán, ki vár ki.** Új elemző réteg.
  Minden lövéshez megkeressük a támadás-szakasz kezdetét, és az addig
  eltelt időt az elengedő játékos posztjához írjuk. Edzői olvasat: ez a
  KÉSZENLÉT beosztása. Aki az első pár másodpercben fejez be, az a
  visszarendeződés hibájából él — rá a visszafutásnál kell embert
  rendelni, mert a felállt fal már nem éri el. Aki a támadás végén lő,
  az a fal megfáradását várja ki — ott a húsz másodperc utáni
  koncentráció és a passzív-jel előtti utolsó labda a kérdés. Ugyanaz a
  fal nem tud mindkettőre egyszerre készülni. Négy lövés alatt,
  illetve 4 másodpercnél kisebb eltérésnél nincs ítélet. Felületek:
  elemzés-végpont, meccs-csomag, edzői összefoglaló, felderítő kulcsok,
  meccsterv (264. szabály: az ő korai befejezőjük × a ti lassú
  visszarendeződésetek), edzés-fókusz (285. szabály: kötött idejű
  befejezés-gyakorlat), felderítés-képernyő csempéje.

- **Poszt-lövéstávolság: kire lépj ki, kire lehet ráengedni.** Új
  elemző réteg. Minden felismert lövéshez megkeressük az ELENGEDŐ
  játékost és a helyét az elengedés pillanatában, majd a kaputól mért
  távolságot a posztjához írjuk. Edzői olvasat: aki rendre 11-12
  méterről lő, arra rá lehet engedni (a távoli lövés a kapusnak
  dolgozik, és a passzsáv zárása többet ér); aki viszont beugrással 7
  méterre jön be, azt ki kell zárni, mert onnan a kapusnak alig van
  esélye. A csapat-átlag keveset mond — a posztok közti KÜLÖNBSÉG adja
  a "meddig lépj ki" döntést. Négy lövés alatt, illetve 2 méternél
  kisebb eltérésnél nincs ítélet. Ez a réteg eddig azért hiányzott,
  mert a lövő-hozzárendelés kapu-felé torzított; a torzítás javítása
  után lett mérhető. Felületek: elemzés-végpont, meccs-csomag, edzői
  összefoglaló, felderítő kulcsok, meccsterv (263. szabály),
  edzés-fókusz (284. szabály), felderítés-képernyő csempéje.

- **A lövés a valódi lövőhöz kerül (mért torzítás javítva).** A
  lövés-eseményt a labda kapu-megközelítésekor jelöljük, és a lövőt
  visszafelé keresve a "legközelebbi játékos" szabállyal találtuk meg.
  Ez rendszeresen tévedett: mérve, **12 méterről elengedett lövések MIND
  a 6 méteren álló játékoshoz kerültek** — a röppálya mellett álló
  beálló lett a "lövő". A visszakeresés mostantól kihagyja azokat a
  kockákat, ahol a labda sebessége lövés-szintű (9 m/s fölött): ott a
  labda úton van, nincs birtokosa. Így az elengedés pillanata a
  hivatkozási pont. Ha ilyen pillanat nincs a keresési ablakban, a
  lövő azonosítatlan marad — a "nem tudjuk" jobb, mint a magabiztosan
  rossz név. A javítás **minden játékos- és poszt-bontású
  lövés-réteget** érint (lövő-erő, elhelyezés, ziccer-befejezők,
  emberelőnyös befejező, gólpassz-párok, sorozatlövő, válság-lövő, …);
  a csapat-szintű számok változatlanok. A pályázati doksi TRL-4
  nyitott pontja ezzel lezárult.

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
