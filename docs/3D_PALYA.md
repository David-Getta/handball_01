# A 3D pálya — edzői útmutató

A Sport Machine a követésből (ki hol volt, hol a labda) egy bejárható
3D-s csarnokot épít: szabályos 40×20 m-es pálya (6 m-es kapuelőtér,
szaggatott 9 m-es vonal, hetes-, kapus- és cserevonal, 3×2 m-es
kapuk), emberszerű figurák mezszámmal, labda a birtokos kezében.
Kétféle felületen ugyanaz a nézet él:

- **az appban** (a Meccs képernyő "3D" füle, vagy egy esemény
  "Megnézem 3D-ben" gombja),
- **a böngészőben / VR-headsetben** (az app "Böngészős 3D / VR" gombja
  — ugyanott, ugyanazzal a kamerával és rétegekkel nyílik, ahol az
  appban tartasz).

A két felület ugyanazokból a számokból dolgozik (a mérés, a falsablonok
és a hőtérkép rácsa a backend `court3d` és `analytics` moduljainak
tükre — őr-tesztek ellenőrzik, hogy nem térhetnek el).

## Heti menet — a csapat-megbeszélés egy oldalon

1. **Előkészítés (az appban):** a meccs "Videózandó jelenetei" és a
   saját jegyzeteid (J — a pillanathoz, a padló nyilaival) adják a
   megbeszélés sorrendjét; a "Jegyzeteim" szűrő + "▶ Vetítés" egymás
   után játssza őket.
2. **A megbeszélés:** "📡 Vezetem" (az appban vagy a böngészőben) — a
   csapat linkje (`…/kovet`) a vágólapra kerül; a headsetek ezt nyitják
   (névvel: `…/kovet?nev=Anna`). Klub-hálózaton a "🏟 Klub-hálózat"
   kapcsoló (az app következő indításától). Vezetés közben: Shift+katt —
   mutató, "📍 Ide mindenki", "❓ Kvíz" (a játékosok a padlóra mutatnak),
   és a játékosok "✋ Kérdésem van"-nal jeleznek.
3. **Felvétel:** a "⏺ Felvétel" a megbeszélést rögzíti (a böngészős
   vezetésnél a hangoddal) — fejezetekre bomlik, és rögzíti, ki követte
   élőben.
4. **Pótlás:** aki kimaradt, a csapat linkjén látja, mit nem látott még
   ("• még nem láttad"), és egy kattintással visszanézi (VR-ben is);
   otthonra a "▶ Felvételek" listából egyetlen HTML-fájlként küldhető.
5. **Követés:** a Keret-lapon játékosonként a kvíz-mérleg ("❓ 7/9") és a
   megbeszélés-követés ("👁 5/5" — élőben vagy felvételről); a
   kezdőlapon a legutóbbi megbeszélések; a meccs-jelentésben a
   "Megbeszélések (3D-felvétel)" szakasz.

## Mozgás a térben

| Mit akarsz | App | Böngésző |
|---|---|---|
| Körülnézni | húzás az egérrel/ujjal | húzás |
| Menni | W A S D, R/F (C) fel/le, Shift gyors | ugyanaz |
| Előre ugrani / közelíteni | görgetés / két ujj csípése | görgetés / csípés |
| Keringeni a pálya körül | **Keringés** gomb vagy **O** | ugyanaz |
| Kész állás | Lelátó · Kapu mögül · Pálya-szint · Madártávlat | ugyanaz |
| TV-kamera (a labdát követi az oldalvonal felől) | **TV-kamera (labda)** gomb | **TV-kamera** gomb vagy **T** |
| Játékos-kamera (egy mezszám hátulról) | **Játékos-kamera** választó | ugyanaz |
| A játékos SZEMÉVEL, vele együtt | dupla koppintás a figurára · Esc kilép | dupla katt · Esc |
| Lejátszás / sebesség | Szóköz · 0,5–4× | ugyanaz |
| Előző / következő esemény | ⏮ ⏭ | ⏮ ⏭ vagy [ / ] |
| Előző / következő jelenet (a jelenet-lista sorai) | ◀ ▶ a panelen vagy P / N | ◀ ▶ vagy P / N; VR-ben B/Y · A/X |

A játékos szemével nézve a kép tetején a HUD mutatja a **sebességét
(km/h)** és az addig **megtett útját** ("Szeged #7 · 14,2 km/h ·
1,18 km eddig"). A megtett út a mezszám mentén, kockánként összegezve
készül; a 3 m-nél nagyobb lépés (követés-ugrás) nem számít.

## Elemző rétegek a pályán

Mindegyik külön kapcsolható, egymásra is tehetők.

- **Lövés-mérés** — koppints/katts a padlóra: távolság a kapu
  közepétől és a kapufáktól, a **kapu-szög** (mennyi kapu "látszik"
  onnan) és a sáv (kapuelőtér / 6–9 m / 9 m-en túl), kék
  lövő-háromszöggel a két kapufáig. Esc törli.
- **Lövéstérkép** — a meccs minden lövése a helyén: kék a hazai, piros
  a vendég; a kör az **xG-vel nő**, a gólt **arany gyűrű** jelzi, a
  védett/kihagyott halványabb. Módok: minden lövés / a lejátszásig
  (a térkép a meccsel együtt épül) / csak hazai / csak vendég.
  **Katt egy körre: odaugrik a lövéshez** (4 mp-cel előtte), és a
  mérés-doboz a lövés sorával kezdődik ("Szeged lövése 12:40 · gól ·
  xG 0,55").
- **Védekezés** — a 6-0, 5-1, 4-2, 3-2-1 tankönyvi fal sárga körökkel a
  kapu előtt; "élő" módban a pillanatnyi fal neve ("Most: Szeged
  védekezik — 5-1") és az **átlagos eltérés** a tankönyvi faltól
  méterben. A kaput a védett / bal / jobb választó adja.
- **Passzok** — "élő": a futó passz vonala az adótól a fogadóig
  (egy másodpercig, halványodva); "háló": a csapat MINDEN passza vékony
  vonalként a padlón, összegzővel — a játékszervezés fő tengelyei.
- **Hőtérkép** — hol tartózkodott a csapat a meccsen (2 m-es cellák,
  csak a mért helyek), a legsűrűbb cellához mért erősséggel.
- **Labda-nyom** — a labda útja az utolsó 3 másodpercben narancs
  vonalként (a passz-sorozat és a lövés íve egyben).
- **Passzsávok** — a pillanatnyi labdástól minden csapattársához egy
  vonal: **zöld** nyitott, **sárga** kockázatos, **piros** zárt sáv,
  összegzővel ("Labdás (Szeged): 4 nyitott, 0 kockázatos, 2 zárt").
  A színezés a döntés-elemzés passz-modellje (a távolság és a sávban
  1,5 m-en belül álló ellenfelek), a labdás az elemzés birtoklás-
  sugarával (3 m) dől el — a 3D nem mond mást, mint az elemzés.
- **Fal-rések** — szervezett védekezésben a védőfal szomszédos védői
  közt sáv a padlón: **zöld**, ha zárt, **piros**, ha a rés eléri a
  3,5 m-t — ott nyílik a fal (oda kell betörni, oda úszik be a beálló).
  Összegző: "Fal (Szeged, 6 védő): 2 nyitott rés — a legnagyobb 4,1 m".
  A fal ugyanaz, mint a fal-rés rétegben: a mért, kapus nélküli védők a
  saját kaputól 12 m-en belül, a rés az oldalirányú távolság.
- **Feltörés és Megállítás** (a Védekezés "élő" módjában) — a fal
  mellé a felderítés két rangsorának teteje: HOL és MIVEL törhető fel a
  védekező csapat fala, és mivel állíthatja meg a most támadó csapatot;
  ha a feltörés egy sávra mutat, az **piros sávként** a padlón is
  megjelenik a védett kapu előtt ("ide kell betörni").

## Jelenetek lapozása

A felderítés és az elemzés arányokat mond ("60%-ban optimális
döntés", "a lövők 84%-át szabadon hagyják"). A lapozók a mögöttük
lévő JELENETEKRE ugranak — a jelenet előtt 1,5 mp-cel, lejátszva, a
pillanat körül rajzolva és felirattal (ha több egyszerre aktív, a
feliratok egymás alatt):

- **Döntések ◀ ▶** — a passz-döntések, ahol a döntés-elemzés modellje
  szerint érdemben (legalább 0,10 értékkel) jobb opció is volt: a
  választott passz **fehér**, a jobb opció **arany** vonal (egy másik
  társhoz, vagy lövésnél a kapura).
- **Szabad lövők ◀ ▶** — a kapott lövések, ahol a lövőtől 2 m-en belül
  nem volt mezőnyvédő: **piros kör** a lövő körül (a fedezés-sugár) és
  szaggatott vonal a legközelebbi védőhöz, a felirat a távolsággal.
- **Labdavesztések ◀ ▶** — az elvesztett labdák: **narancs kör** a
  vesztő körül (a 2,5 m-es nyomás-sugár: ha ezen belül állt ellenfél,
  az eladás KIPRÉSELT, különben MAGÁTÓL jött), szaggatott vonal a
  legközelebbi mezőnybeli ellenfélhez, **X** a labdánál; a felirat a
  vesztő mezszámával, a pálya-harmaddal, a nyomással, és ha fél percen
  belül gól lett belőle, azzal is. Ugyanaz a négy válasz, amit a
  labdaeladás-rétegek számokban mondanak — itt egy jeleneten.
- **Gól-akciók ◀ ▶** — a gólok előkészítése: a gólt megelőző saját
  passz-lánc a csapat színével (a régebbi passz halványabb), **arany**
  vonal a lövőtől a kapuig; a felirat a mezszámokkal ("#10 → #9 → … →
  #4 → #10 lő · 8 passz, 6,5 mp"). A lánc-szabály a gól-előkészítés
  rétegé: a gól előtti 20 mp saját passzai, a birtoklás-határig.
- **Emberelőny ◀ ▶** — a kiállítások szakaszai; amíg a lejátszás egy
  ilyenben jár, lent középen élő jelző: ki van előnyben, ki hiányos,
  mennyi van hátra, és az előny alatti állás eddig. A kiállítás-
  felismerés és a lövés-szabály az emberelőny-hatékonyság rétegé.
- **Lerohanások ◀ ▶** — a kontrák: a befejező útja az indulástól a
  lövésig a támadó csapat színével (pont fél másodpercenként), **fehér**
  szaggatott vonal a labda indulási helyétől az út elejéig (az
  indítópassz), **arany** vonal a lövéstől a kapuig; a felirat az edzői
  olvasattal ("Lerohanás (Szeged): #7 fejezi be · második hullám ·
  elszökött emberrel · 4,2 mp · GÓL"). Ugyanazok a szabályok, mint a
  kontra-rétegekben: a lerohanás-címke (legfeljebb 6 mp, a labda
  legalább 2 m/s-mal halad a kapu felé), a gól és a lövő a lerohanás-
  hatékonyság és a kontra-hullámok szabálya (első ember = az induláskor
  a kapuhoz legközelebbi mezőnyjátékos), az elszökés a kontra-elszökésé
  (a labdánál 6 m-rel előrébb váró ember).
- **Kapott gólok ◀ ▶** — minden kapott gól egy helyen, a védekezés
  olvasatával: gyűrű a lövő körül (a lövő csapat színével), szaggatott
  vonal a legközelebbi védőhöz (**piros**, ha a lövő szabadon lőtt — a
  2 m-es fedezés-sugáron kívül —, különben szürke), a kapus helye
  **lila** gyűrűvel és vonal a kapu közepéig (a mélysége), **arany**
  vonal a lövéstől a kapuig; a felirat: "Kapott gól (Veszprém): Szeged
  #10 · 9 m-en túl, kapu-szög 13,8° · védő 6,2 m-re — szabadon · kapus
  0,9 m-re a vonalon · xG 0,09". A forrás a védekezés-elemzés gól-sorai
  (ugyanaz az elengedési kocka, lövő-hely, védő-távolság és xG), a sáv
  és a kapu-szög a lövés-mérésé, a kapus mélysége a kapus-kimozdulás
  mérése (a "kint" a pillanatra szabott 2,5 m-es küszöb — a réteg 1,5
  m-e a meccs-átlagé).

- **Hétméteresek ◀ ▶** — a hetesek: **X** a 7 m-es ponton, **arany**
  vonal a dobótól a célzott kapu-harmadba (a dobó szemszögéből bal /
  közép / jobb), a kapus helye **lila** gyűrűvel és vonal a kapu
  közepéig (a mélysége); a felirat: "Hetes (Szeged): #7 · középre · GÓL
  · kapus 1,0 m-re a kaputól". A felismerés, a lövés-párosítás és az
  irány a hetes-rétegeké (a kísérletek és a gólok száma a hetes-mérleggel
  egyezik). Nem hiba-lapozó: a "Kinek a hibái" szűrő nem érinti.

A ▶ az utoljára nézett jelenettől lép tovább (nem ragad le, és a meccs
legelső pillanatai is elérhetők).

A lapozók jelenetei videóként is kivághatók: a "Döntés-hibák", a
"Szabad lövők", a "Drága eladások" (a gólba került labdavesztések) és a
"Kapott lerohanások" csomag (a saját kontrák a "Lerohanások" csomagban,
a befejező mezszámához írva). A jelenet-lista fejlécének **Klipek**
gombja az appban a Klipek képernyőt nyitja a nézett meccsel és e négy
csomaggal előre kijelölve (ott mezszámra is szűkíthető: "a #7 drága
eladásai"); a böngészőben
ugyanez a gomb a motortól kéri a vágást, mutatja az állapotát, és a
kész zipre letöltő linket ad.

A **Jelenet-lista** a hiba-lapozók (Döntések, Szabad lövők,
Labdavesztések, Lerohanások, Kapott gólok) összes jelenetét egy időrendi listában
mutatja ("12:40 · Szeged — labdavesztés #7 (támadó harmad) · gól lett
belőle"); koppintás egy sorra: odaugrik, az épp futó jelenet sora
kiemelve. Meccs-elemzéshez gyorsabb, mint a ◀ ▶ lapozás. A kapott
lerohanás a VÉDEKEZŐ csapat sora ("Veszprém védekezése — kapott
lerohanás: Szeged #13 · GÓL"): aki nem futott vissza, azé a hiba. A
kapott gól is a védekező csapat sora ("Veszprém védekezése — kapott
gól: Szeged #13 (kapuelőtér) · védő 0,7 m · kapus kint") — de ha
ugyanarra a pillanatra szabad lövő GÓL-sor van, a kapott gól sora
elmarad (az már megnevezi; a lapozóban minden kapott gól ott van).

Az **Edzésterv** lap egy-meccs nézetéből a fókusz-tételek "… 3D-ben"
gombja (Szabad lövők, Kapott gólok, Labdavesztések, Döntés-hibák,
Kapott lerohanások) a 3D pályát a tétel csapatának hibáira szűrve,
nyitott jelenet-listával, a típus első jelenetén nyitja — a tétel és a
lapozó párosítása a backend `training.scene_for_focus` táblázata (a
tétel területe és címe szerint).

A **kezdőlap** meccs-kártyája mondja, hány videózandó jelenet vár ("Videózandó:
N jelenet") — a gólba került labdavesztések és kapott lerohanások, a gólt
érő szabad lövők, a kapott gólok és a legnagyobb döntés-hibák; a "3D-ben"
gomb a pályát az első jeleneten nyitja, a hibázó csapatra szűrve. Ugyanez
a válogatás a nyomtatott jelentés "Videózandó jelenetek" szakasza
(`court3d.key_scene_rows`, végpont: `/matches/{id}/key-scenes`).

A lista fejlécének **Videózandó** szűrője a sorokat a kulcs-jelenetekre
szűkíti (a gólba került eladások, a kapott lerohanás-gólok, a gólt érő
szabad lövők, a legnagyobb döntés-hibák — a nyomtatott jelentés és a
kezdőlap kártyájának válogatása); bekapcsolva az N / P és a
VR-kontroller is ezeken lép. A kezdőlap "3D-ben" gombja és a jelentés
"3D ↗" linkje bekapcsolva nyit (link-paraméter: `kulcs=1`).

A fejléc **▶ Vetítés** gombja (billentyű: V; VR-ben a kontroller
hüvelykujj-karjának lenyomása) a lista sorain végigjátszik: minden
jelenet 1,5 mp-cel előtte indul, a pillanata után 3,5 mp-ig fut
(`court3d.SCENE_REEL_TAIL_S`), aztán a lista következő sora jön — a
Videózandó szűrővel bő egy perces összefoglaló a meccs kulcs-jeleneteiből.
A felirat-oszlop tetején (VR-ben a táblán) a "Vetítés · 3/15 · 12:34"
jelző mutatja, hol tart; a lista végén megáll. Kézi tekerés után nem ugrik
el, egy sorra kattintva onnan folytatja. Egy kattintásra: a nyomtatott
jelentés "Videózandó jelenetek" szakaszának "▶ Mind egymás után" linkje és
a kezdőlap kártyájának "Vetítés" gombja a 3D pályát a videózandó
jelenetek vetítésével nyitja (link-paraméter: `vetit=1`), TV-kamerával
(`tv=1` — a labdát követi az oldalvonal felől, mint egy közvetítés). A lista
Klipek gombja a Videózandó szűrővel a videózandó jeleneteket egy
klip-csomagban kéri (`key_scene`: időrendben sorszámozott fájlok — az
edzésen bármilyen lejátszóval sorban levetíthetők).

A **Kinek a hibái** választó a hiba-lapozókat egy csapatra szűri: mind
egy csapat hibáját mutatja (a rossz döntést, a szabadon hagyott lövőt,
az elvesztett labdát, a kapott lerohanást, a kapott gólt) — a saját csapatra szűrve
videóelemzés a játékosoknak, az ellenfélre szűrve felkészülés ellenük.

A jelenet-lista **Jegyzeteim** szűrője csak az edző jegyzeteit hagyja a
listában: a Vetítés pontosan a megjelölt pillanatokat játssza (a
rajzokkal) — ez a csapat-megbeszélés válogatása, a közös nézéssel a
headseteken is. A Klipek ilyenkor a jegyzet-csomagot kéri; a link viszi
(`jegyzetek=1`), a jelentés jegyzet-szakaszának "▶ A jegyzetek egymás
után" linkje így nyitja a 3D pályát.

## Rajz és jegyzet — elemzés a jeleneten

A **✎ Rajz** (billentyű: E) a taktika-tábla a valódi jeleneten: rajz-módban
a húzás nyilat rajzol a padlóra — sárga a labda/passz, kék a futás,
piros a védő mozgása. A megállított jeleneten az edző megmutatja, hova
kellett volna futni, passzolni, lépni; a nyilak a padlón élnek, ezért
minden nézetből és VR-ben is látszanak. ↶ az utolsót veszi vissza, a
Törlés mindet; a "Link másolása" viszi őket (`rajz=x1,y1,x2,y2,szín;…`,
0,1 m-re kerekítve, legfeljebb 30 nyíl), így a videó-elemzés egy címmel
megosztható. Az appban ugyanez a "✎ Rajz (E)" gomb a panelen (a színek
mellette, ↶ és törlés); a "Böngészőben" gomb a nyilakat — és a
jelenet-lista állapotát: a csapat-szűrőt, a nyitott listát, a Videózandó
szűrőt és a vetítést — is átviszi, így az appban rajzolt jelenet a
VR-headsetben ugyanúgy nyílik.

A **📝 Jegyzet** (billentyű: J) a mostani pillanathoz ír megjegyzést —
ugyanabba a jegyzet-tárba, amit a meccs-elemző használ (a motor
`/matches/{id}/notes` végpontja). A jegyzet a jelenet-lista sorai közt
fehér pöttyel jelenik meg (minden szűrővel — az edző saját válogatása; a
böngészőben a sor végi ✕ törli), a vetítés is megáll rajta, a pillanata
körül a felirat-oszlopban (VR-ben a táblán) látszik, és a nyomtatott
jelentésbe és a Klipek "Jegyzetelt pillanatok" csomagjába is bekerül.
Ha a jegyzet írásakor nyilak vannak a padlón (✎ Rajz), a jegyzettel
mentődnek: a jegyzet pillanatában — a vetítésben is — maguktól
visszarajzolódnak (a sor és a felirat végén ✎ jelzi), a szerkeszthető
padló-rajz pedig kiürül. A nyomtatott jelentés jegyzet-sorai a motor
címével "3D ↗" linket kapnak, a rajzos jegyzetek pedig felülnézeti ábrát
(`court3d.note_diagram`): a pálya, a pillanat játékosai csapatszínnel és
mezszámmal, a labda és a nyilak — kiosztható taktika-lap a
videó-elemzés után (legfeljebb 12 ábra). A Klipek "Jegyzetelt
pillanatok" csomagjában a rajzos jegyzet klipjére a nyilak a VIDEÓRA
rajzolódnak — a kalibrációval (a pálya-méterből pixelre, a svenkelő
kamera kulcs-kockáival) vetítve, a jegyzet pillanata előtt 1,5 mp-től a
klip végéig; kalibráció nélkül a klip rajz nélkül készül.

## Videó a 3D mellett

A **📺 Videó** (billentyű: K) a valódi felvételt mutatja a 3D mellett, a
lejátszással szinkronban: kép a képben a jobb alsó sarokban, és egy
kivetítőn a túlsó oldalvonal fölött — VR-ben ez látszik. A motor
`/matches/{id}/frame?t=…&w=…` végpontja adja a forrás-videó kockáját JPEG-ben
(összefűzött meccsnél a megfelelő szakaszból); a link viszi (`video=1`).
Ha a videó nem érhető el ezen a gépen, az ablak megmondja.
Az appbeli 3D fülön ugyanez a K (és a panel 📺 Videó gombja): a felvétel
a 3D kép MELLETT nyílik (a kép keskenyebb lesz, nem takarja), és a
böngészős nézet linkje is viszi.

## Közös nézés — az edző vezet, a csapat követi

A **📡 Vezetem / 👥 Követem** a közös nézés: az edző "Vezetem"-mel a
lejátszása állapotát (idő, szünet, sebesség, rajz) a motorra küldi, a
csapat headsetjei a "Követem"-mel (vagy a csapat linkjével: `kovet=1`)
ezt követik — a csapat linkje rövid: `localhost:8000/kovet` (a motor a
MOST élő közös nézésre irányít, a headset billentyűzetén begépelhető;
vezető nélkül egy "várunk az edzőre" lap magától továbblép, amint az
edző vezet) — mindenki a saját helyéről, a saját kamerájával nézi
ugyanazt a pillanatot: a pálya bejárható, az edző mutatja a szituációt.
A követő a vezető idejét a válasz korából becsli, és csak 0,4 mp-nél
nagyobb eltérésnél ugrik (nincs rángatás); ha az edző leáll vagy 15 mp-ig
hallgat, a követő "nincs vezető"-t lát. Vezetőként a Shift+kattintás a
padlóra MUTATÓ a csapatnak: a követőknél (és a vezetőnél) 4 mp-ig lüktető
gyűrű jelzi a pontot — "nézzétek ide"; a később csatlakozónál a régi
mutató nem villan fel (a motor a mutató korát is adja). A **📍 Ide mindenki** a
vezető mostani nézőpontját (hely és irány) küldi: a követők kamerája oda
ugrik (VR-ben a rig — a fej iránya a sajátja marad) — "álljatok mind a
kapus helyére". A közös nézésben **látjátok egymást**: mindenki
egy fejként jelenik meg a csarnokban, ott, ahonnan néz — orral a nézés
irányába, gyűrűvel a padlón, fölötte a név (az edzőé arany). A név a
csapat linkjén adható meg: `localhost:8000/kovet?nev=Peti` (név nélkül a
csatlakozás sorszáma látszik, pl. #3). Az edző így látja, ki áll rossz
helyen, ki néz másfelé; a saját fejedhez 1,2 m-nél közelebbi nem látszik
(az "Ide mindenki" után mindenki egy helyen áll). Az app 3D füléről
vezetve ugyanez: a csapat a 3D képen, a követők pedig az edzőt az app
kamerájának helyén látják.

A **❓ Kvíz** a megbeszélés kérdése a valódi jeleneten: a vezető
megnyomja, a jelenet megáll, és kérdez — "hova passzolnál?", "hol a
helyed, amikor a beálló kilép?". A játékosok a padlóra mutatnak
(kattintás; VR-ben a ravasz, a kontroller sugarával — a felfedésig
módosítható); a válaszuk náluk rózsaszín jel "Te" felirattal. Az edző a
válaszokat azonnal látja, névvel (kék jel a padlón, rajta a név), és az
állapot-sorban, hányan válaszoltak. A második gombnyomás ("👁 Mutasd a
csapatnak") mindenkinek megmutatja a válaszokat — itt jön a
megbeszélés, mellé a Döntések réteg jobb opciója —, a harmadik ("✖ Kvíz
vége") leveszi őket. **Döntés-kvíz:** ha a kvíz döntés-pillanatnál
indul (a Döntések ◀ ▶ felirata látszik — "jobb opció is volt"), a
válaszokat a modell jobb opciójához méri: ✓, ha a válasz a jobb célhoz
közelebb van, mint a választott passz céljához, és attól legfeljebb 3
m-re (lövésnél a kapu előtt, a kapuelőtérben); az edző azonnal látja a
neveken és az állapot-sorban ("✓ 2 a jobb opció"), a csapat a
felfedéskor. A kvíz végén az eredmény a **jegyzetek közé** kerül
(ha volt válasz): "❓ Döntés-kvíz (jobb opció: lövés) — ✓ Anna · ✗ Peti ·
nem válaszolt: 1" a döntés kockáján, a passzolótól a válaszokig húzott
nyilakkal (sárga ✓, piros ✗) — így a jegyzet-listában, a nyomtatott
jelentésben (ábrával) és a Klipek jegyzet-csomagjában is ott van, és
meccsről meccsre visszanézhető, ki látta a jobb megoldást. A
**Kvíz-mérleg** (az app Jegyzetek képernyőjén fölül) ezt össze is számolja:
játékosonként, meccseken át, hányszor mutatott a jobb opcióra ("Anna ·
7/9 ✓ (78%)" — 3-nál kevesebb ítélt válasznál arány nélkül); a név a
kulcs, ezért érdemes a csapat linkjén mindig ugyanazt a nevet megadni
(`/kovet?nev=Anna`), a név nélküli követő (#3) nem számít bele. A
követő oldalán a **"Ki vagy?"** lista a keretben felvitt nevek közül
választ (a headset billentyűzetén nem kell gépelni) — és a keret nevével
a mérleg a Keret képernyőn is megjelenik, a játékos neve mellett ("❓
7/9"), a Játékos-fejlődésben pedig meccsenként (a "kvíz" oszlop és az
összkép "döntés-kvíz" chipje) — látszik, olvassa-e jobban a játékot. Az app 3D
füléről vezetve ugyanez (a panel "❓
Kvíz" gombja, a gombon hányan válaszoltak — döntés-kvízben hányan
találták el, a válaszok felirata ✓/✗). A motor
a csapatnak csak a felfedés után adja a többiek válaszát (nem lehet
puskázni), és csak az aktuális kört (a régi kör válasza nem látszik). A
motor
`/matches/{id}/shared3d` végpontja (PUT/GET/DELETE) memóriában tartja az
állapotot. Az app 3D füle is vezethet ("📡 Vezetem" a panelen): az edző
a laptopon teker, megállít, rajzol, a headsetek követik.

### ✋ Kérdésem van

A követő **✋ Kérdésem van** gombja (billentyű: H, VR-ben a markolat)
jelzi, hogy kérdezne — a headsetben az edző nem látja a kezét. Az edző a
játékos feje fölött ("✋ Peti"), a felirat-sorban és VR-ben a tábláján
látja; az appban a csapat-fejeken és a "📡 Vezetsz" gombon. Még egyszer
megnyomva: kéz le.

### Felvétel — a megbeszélés visszanézhető

A **⏺ Felvétel** gomb vezetés közben a megbeszélést rögzíti: a
lejátszásodat (idő, szünet, sebesség), a padló nyilait, a mutatót és az
"Ide mindenki" nézőpontjait. A felvétel végén (vagy ha leállsz a
vezetéssel) a motor a meccs mellé menti. A **▶ Felvételek** listából
bárki visszajátszhatja — a böngészőben és VR-ben is —, a követés útján:
mintha az edző épp most vezetne, a néző a saját helyéről nézi. A gomb
visszajátszáskor szünet/tovább (VR-ben a ravasz). Aki kimaradt a
megbeszélésről, utólag végignézheti.

**Fejezetek**: a motor a felvételt ott bontja, ahol az edző egy másik
jelenetre ugrott (a csúszka húzása egy fejezet, a landolással). A
visszajátszás fejezet-választója a közeli jelenet feliratával mutatja
őket; N / P (VR-ben A/X — B/Y) a következő / előző fejezet — egy
egyórás megbeszélésben a játékos így a saját részét keresi meg.

🎙 **A hangod is**: a böngészős vezetés felvétele a mikrofont is rögzíti
(az első felvételnél a böngésző engedélyt kér; ha nem engeded, a
felvétel hang nélkül készül). A visszajátszás az edző magyarázatát az
időhöz igazítva játssza — szünetnél elhallgat, folytatásnál onnan
szól. A headset böngészője kattintás nélkül nem mindig enged hangot:
ilyenkor a felirat szól ("kattints az oldalra a hanghoz"). Az app
vezetése hangot nem rögzít.

**Ki nézte meg?** Ha a néző (a "Ki vagy?" nevével — visszajátszáskor név
nélkül a választó előjön) a felvétel 80%-át ténylegesen végignézte (a
szünet és az átugrott fejezetek nem számítanak), a motor rögzíti; az app
"▶ Felvételek" listája mutatja ("megnézte: Anna, Peti"), a Keret-lap
pedig játékosonként, meccseken át: a csapat felvett megbeszélései közül
hányat követett — élőben (a felvétel a közös nézés névvel jelenlévő
követőit is rögzíti) vagy felvételről ("👁 5/5", a tooltip bontja).

📦 **Otthonra**: a "▶ Felvételek" listában a letöltés-gomb a felvételt
egyetlen HTML-fájlként menti (a 3D oldal a felvétellel, a hangjával és a
three.js-szel együtt). Elküldhető; a játékos bármely böngészőben — a
headsetben is — megnyitja, és motor, internet nélkül lejátszódik. (A
csomagban a motoros funkciók — közös nézés, jegyzet, videó, "Ki nézte
meg?" — nem működnek.)

A meccs-jelentés **Megbeszélések (3D-felvétel)** szakasza is felsorolja
őket — fejezetenként (a meccs-idővel), ki követte élőben, ki nézte meg —:
a megbeszélés papírnyoma.

A kezdőlap **Legutóbbi megbeszélések** kártyája is mutatja őket
(meccsektől függetlenül, ki nézte meg), a "3D / VR" gomb a böngészőben
indítja.

A csapat linkje (`/kovet`) is kínálja őket: amíg nincs élő vezetés, a
"Várunk az edzőre" lap a legutóbbi megbeszéléseket listázza (meccsektől
függetlenül) — a headsetben egy kattintással indul a visszanézés. A
névvel nyitott link (`/kovet?nev=Anna`) jelöli, melyiket látta már a
játékos és melyiket nem ("• még nem láttad"), és a visszanézés a nevére
számít.

Az appban ugyanígy: vezetés közben a **⏺ Felvétel** gomb rögzít. A 3D fül
**▶ Felvételek** listája a meccs felvételeit mutatja: a sorra kattintva
a böngészős 3D nyílik, és a felvétel magától indul (link-paraméter:
`felvetel=<azonosító>`); itt nevezheted át ("Védekezés 6-0 — hétfő") és
törölheted is.

### Közös nézés több headsettel

Internet nem kell: a 3D oldal a three.js-t is a motorból tölti (a
csomagolt kiadás viszi), így az edzőteremben, a klub saját hálózatán is
megy.

A követő headsetnek el kell érnie a vezető gépén futó motort, és a
VR-mód (WebXR) csak biztonságos címen indul — a `localhost` ilyen. Két
út van:

1. **USB-n (néhány headsetre, ajánlott):** minden headset USB-kábellel
   a laptopra, és `adb reverse tcp:8000 tcp:8000` (ha a motor tartalék
   porton fut, azzal a számmal). A headset böngészőjében a csapat
   linkje (`http://localhost:8000/kovet`) így a
   laptop motorját éri el, és a VR-mód indul. USB-elosztóval több
   headset is mehet egyszerre.
2. **A klub hálózatán (sok headsetre):** az appban a 3D fül "🏟
   Klub-hálózat" kapcsolója (az app következő indításától; parancssor
   nélkül) — vagy kézzel: a motort kifejezetten a
   hálózat felé is meg kell nyitni — `HANDBALL_HOST=0.0.0.0` a
   `scripts/serve.py` indításakor (az app motor-indítója szándékosan
   csak a saját gépet szolgálja ki) —, a csapat linkjében a `localhost`
   helyére a laptop hálózati címe kerül (a vezető ilyenkor már ezt kapja
   a vágólapra — a motor `/halozat` végpontja megmondja a címet), és a headset böngészőjében
   ezt a címet biztonságosnak kell jelölni (Chromium-alapú böngészőben:
   `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, a
   laptop `http://<cím>:8000` címével), különben a VR-mód nem indul.
   **Hálózati őr:** ilyenkor a más gépekről (a headsetekről) CSAK a
   közös nézés követő-útja érhető el — a `/kovet`, a meccs 3D oldala, a
   közös nézés állapota, a videó-kockák, a jegyzetek olvasása és a
   névlista; a meccsek listája, az elemzések, az írás, a feltöltés és a
   törlés 403-at kap (a motor gépéről minden megy, mint eddig).
   **Figyelem:** ami nyitva marad, az belépés nélkül elérhető — a hálózat
   bármely gépe megnyithatja a meccs 3D oldalát és videó-kockáit, ha
   tudja a meccs azonosítóját. Csak megbízható, zárt hálózaton nyisd meg,
   és az edzés után indítsd újra a szokásos módon.

## Jelenet megosztása

A nyomtatható meccs-jelentés "Videózandó jelenetek" sorai végén "3D ↗"
link ugyanerre a címre mutat (a jelenet előtt 1,5 mp-cel, a hibázó
csapatra szűrve, nyitott listával) — a jelentés-export a motor címével
készíti, a meccs-csomag jelentése link nélkül.

A böngészős nézet **Link másolása** gombja a MOSTANI jelenetet adja
címként: idő, kamera-állás vagy Játékos-/TV-kamera és a bekapcsolt
rétegek. A címet megnyitva mindez visszaáll — így egy JELENETET
küldesz a stábnak, nem egy meccset. A paraméterek:

```
/matches/<meccs>/view3d?t=349&nezet=madar
   &kamera=h7 | &tv=1
   &hoter=mind&loves=hazai&passz=vendeg&fal=6-0&falOldal=jobb
   &nyom=1&passzsav=1&falres=1&jelenet=vendeg&lista=1&kulcs=1&seb=2
   &jegyzetek=1&vetit=1&rajz=20,13.1,28.4,16.8,0&video=1
   &kovet=1 | &vezet=1
```

Az újabbak: `jegyzetek=1` — a Jegyzeteim szűrő; `vetit=1` — a vetítés
indul (a Jegyzeteim szűrővel a jegyzetek megjöttét megvárja); `rajz=…` —
a padló nyilai; `video=1` — a felvétel a 3D mellett; `kovet=1` /
`vezet=1` — közös nézés követőként / vezetőként; `felvetel=<azonosító>` —
egy mentett megbeszélés visszajátszása indul.

## Figura 3D-ben — a megrajzolt figura bejárása

A **Figura-tervező** "3D / VR ↗" gombja a megrajzolt figurát a böngészős
3D-ben nyitja (VR-ben is): a támadók a Kezdő → Közép → Vég kulcs-pozíciók
közt VALÓS tempóban futnak (a leghosszabb szakasz is legfeljebb 3,5 m/s;
a mozgás 3–12 mp), az elején és a végén 1,5 mp állókép, a fal a védelem
modellje szerint reagál, a kaput kapus védi, és a figura ismétlődik. A
védelem a legutóbbi "Egy CSAPAT tanult védelme ellen" meccse és oldala,
különben a tervező fala (védőszám, mélység). A bal felső sarokban a
kiértékelés: a mozgás hossza és a legjobb lövőhelyzet (ki, hány %, mikor).
A támadók útjai nyílként a padlón (a labdás sárga, a többiek kék — a
Rajz-réteg nyilai: a "Törlés" leveszi, a link viszi).

Edzőileg: a játékos a saját útját a saját szemével látja — a
Játékos-kamerával (a mezszám a figura sorszáma) vagy dupla kattintással —,
a tempóval és a fal reakciójával; a rajz és a Link másolása működik (a
link a figurát viszi). A meccshez kötött funkciók (közös nézés, jegyzet,
videó, a meccs-jelenetek) a figurában nincsenek.

A csapat a várólapon éri el: amit az edző a saját gépéről nyitott meg, azt
a `/kovet` lap három órán át "▶ Figura: …" sorként linkeli — a headseten a
hosszú cím nem gépelhető. A cím (`/figura3d?u=…&cim=…&meccs=…&vedo=…`)
a klub-hálózatról is elérhető (olvasás).

## VR-headset

A böngészős oldal WebXR-képes: a lenti "ENTER VR" gombbal a csarnok
headsetben nyílik, a bal kar hüvelykujj-karja a nézés iránya szerint
visz, a jobb kar oldalra billentése 30°-kal fordít (ülve, forgószék
nélkül is körbe lehet nézni). A jelenet-feliratok (esemény, döntés, szabad lövő,
labdavesztés, gól-akció, lerohanás, kapott gól, hetes, emberelőny) a headsetben
egy fejhez rögzített
táblán látszanak, és a jelenetek a kontrollerrel lapozhatók: A/X — a
következő, B/Y — az előző jelenet, ravasz — lejátszás/szünet, a
hüvelykujj-kar lenyomása — vetítés (a lista sorai egymás után); a közös
nézés vezetőjeként a markolat a jobb kézben MUTATÓ (ahova a kontroller
mutat a padlón), a bal kézben "📍 Ide mindenki"; a bal hüvelykujj-kar
lenyomása a kvíz következő lépése (indítás → mutasd a csapatnak → vége
— a táblán a kvíz állása: hányan válaszoltak, hányan találták el). A WebXR
biztonságos környezetet kér — a localhost az; Quest-féle headsetről
USB-kábellel és `adb reverse`-szel érhető el az app gépe.

## Hol él a kód

- Backend: `backend/handball/pipeline/court3d.py` (lövés-geometria,
  falsablonok, védekezés-idővonal, `tactical_keys_by_team` — feltörés
  és megállítás, `pass_lanes` — passzsávok, `decision_moments` —
  döntés-pillanatok, `free_shot_moments` — szabadon hagyott lövők,
  `turnover_moments` — labdavesztések, `wall_gap_segments` — fal-rések,
  `goal_build_ups` — gól-akciók, `powerplay_moments` — emberelőny,
  `fast_break_moments` — lerohanások, `conceded_goal_moments` — kapott
  gólok, `seven_meter_moments` — hétméteresek, `scene_rows` — a
  jelenet-lista sorai, `key_scene_rows` — a
  videózandó jelenetek válogatása), `view3d_html.py` (a
  böngészős oldal és a tömör adat), végpontok: `/matches/{id}/view3d`,
  `/matches/{id}/defence-timeline`, `/matches/{id}/decision-moments`,
  `/matches/{id}/free-shots`, `/matches/{id}/turnover-moments`,
  `/matches/{id}/goal-build-ups`, `/matches/{id}/powerplay-moments`,
  `/matches/{id}/fast-break-moments`, `/matches/{id}/conceded-goals`,
  `/matches/{id}/seven-meter-moments`,
  `/matches/{id}/key-scenes`.
- App: `client/lib/ui/court3d_screen.dart` (szoftveres vetítés,
  gesztusok, rétegek), `court_geometry.dart` (a backend tükre).
- Tesztek: `backend/tests/test_view3d_eszkozok.py`,
  `test_court3d.py`; `client/test/court3d_screen_test.dart`,
  `court_geometry_test.dart`.
