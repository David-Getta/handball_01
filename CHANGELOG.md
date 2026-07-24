# Változásnapló (CHANGELOG)

A Sport Machine kiadásainak emberi nyelvű összefoglalója. A részletes
történet a squash-merge-elt PR-okban él; itt a lényeg, témák szerint.

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

## Kiadatlan (a v0.1.21 óta)

_(Még nincs bejegyzés — a v0.1.21 kiadás után indul.)_

## v0.1.21 — kiadva (2026-07-24, PR #543–#560)

> Kiadás-jegyzet: a legfontosabb a macOS-javítás — a feldolgozás többé
> nem szállhat el csendben ~2%-nál ("Connection refused"): a motor
> belépési pontja a natív OpenMP-ütközést induláskor hatástalanítja
> (#545). Mellé tizenkét új elemzés-réteg érkezett (mind a megszokott
> "egy réteg, sok felület" bekötéssel), a meccsjelentés új Csapat-profil
> táblát kapott, és az élő nézet két új félidei jelzést. Windows- és
> macOS-telepítővel a Releases oldalon.

### A v0.1.21 körei

- **Felderítő narratíva stílus-jegyekkel**: az "Így támadnak"
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

## v0.1.17 és korábbi
A korábbi kiadások tartalmát a Releases oldal és a PR-történet őrzi:
alap-pipeline (YOLO+ByteTrack, homográfia, pásztázás-követés),
esemény-felismerés, taktika/felderítés, figura-tervező, mezszám-OCR,
könyvtár-mentés, telepítők (Windows/macOS).
