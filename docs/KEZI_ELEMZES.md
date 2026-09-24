# Kézi elemzés

Az edző SAJÁT elemzése egy meccshez: amit ő lát, beírva és lerajzolva. A
meccs-nézet "Kézi elemzés" gombjával nyílik, két része van.

## Esemény-napló

Soronként egy esemény: **idő** (a videó ideje, `pp:mm`), **csapat**,
**esemény** (lövés, passz, eladás, szerzés, kiállítás, hetes, időkérés,
csere, szabálytalanság, egyéb), **mez**, passznál **kinek**, lövésnél és
hetesnél a **kimenetel** (gól, védés, mellé, kapufa, blokk), és egy
**megjegyzés**. Egy esemény táblához is köthető. Koppintásra szerkeszthető,
a törlés visszavonható.

Az idő mező a meccs-nézet aktuális idejével indul; a mellette lévő gomb
oda állítja vissza, a kamera-gomb pedig a lejátszó mostani helyét veszi
át. A napló egy idejére kattintva a videó oda ugrik.

## A meccs videója közben

Ha a meccs eredeti videója ezen a gépen van, a képernyő tetején lejátszó
fut (a meccs-nézet idejéről indul, magától nem játszik). A kép
**nagyítható**: MacBook-touchpaden két ujjas csippentéssel (két ujjas
húzással mozgatható), egérrel Ctrl+görgővel (Macen ⌘+görgővel is), vagy
a kép sarkában a + / − / 1× gombokkal; dupla kattintás visszaállítja. A
videó-sáv magassága a sáv alatti elválasztó húzásával állítható (dupla
kattintás: alap-arány), a fejléc "Videó" kapcsolójával elrejthető.

A **taktikai tábla** ugyanígy nagyítható (csippentés, Ctrl/⌘+görgő, a
tábla sarkában + / − / teljes pálya); nagyítva az üres helyről húzás és
a görgő mozgatja. A touchpad-gesztus nem húz bábut — azt kattintva-húzva
mozgatod, mint eddig.

Az idő mindenhol az **eredeti videó ideje** — ugyanaz, amit a lejátszó
mutat; a "Pozíciók a meccsből" a feldolgozás kezdő-kockájával számol
vissza.

## Taktikai táblák

Egy tábla egy pálya-helyzet felülnézetben (40×20 m), mozgatható
bábukkal. Az alap-felállás: a hazai a jobb kapura támad (kapus, két
szélső, két átlövő, irányító, beálló), a vendég 6-0-s fallal véd.

Eszközök:

- **Mozgatás** — a bábu (és a labda) húzással mozgatható. Hosszan nyomva:
  felirat (mezszám vagy poszt) vagy a bábu törlése.
- **Passz** — koppints a passzolóra, majd a társra. A labda a címzetthez
  kerül, és a következő passz onnan folytatható. Üres helyre is lehet
  passzolni.
- **Futás** — a futó játékos, majd a cél-pont (szaggatott nyíl).
- **Lövés** — a lövő, majd a kapu felé mutató pont.

A nyilak sorszámot kapnak: ez a támadás menete. A **Folytatás** új táblát
nyit a mostani bábu-helyekről (nyilak nélkül) — így rakható össze egy
hosszabb támadás több lépésben. A **Pozíciók a meccsből** a felismert
játékos-helyeket tölti be a tábla idejéből; az edző ezután csak igazít.
Az **Esemény a naplóba** a tábla utolsó passzából esemény-javaslatot tesz
az űrlapba (idő, csapat, passzoló, címzett).

## Mentés

A munka FÉLKÉSZEN is megmarad:

- minden változás után három másodperccel magától ment, a "Mentés" gomb
  azonnal;
- előbb HELYBEN ír piszkozatot (a felhasználói adatmappa `annotations`
  mappájába), aztán a motorba (`{meccs}.annotations.json` a meccs
  mellett);
- ha a motor épp nem érhető el, a helyi piszkozat őrzi a munkát, és a
  program félpercenként, illetve a következő megnyitáskor feltölti;
- kilépéskor (vissza-gomb, ablak bezárása) is ír;
- a "Kész" jelölés csak állapot: a kész elemzés is tovább szerkeszthető.

A meccs törlése a kézi elemzést NEM törli (mint a jegyzeteket sem): ha
ugyanaz a meccs újra bekerül, a munka visszajön.

## CSV-export — összevetés a program kimenetével

A "Napló CSV-ben" gomb pontosvesszős, Excelben nyitható fájlt ad:

```
ido;ido_mp;csapat;esemeny;mez;kinek;kimenetel;megjegyzes;tabla
00:12;12,3;Hazai FC;passz;7;11;;;Kereszt balra
01:35;95,0;Vendég SE;lövés;14;;védés;bal szélről;
```

Ez a program mérőrúdja: a kézzel rögzített események a felismerés
kimenetével időre párosíthatók. Az idő a VIDEÓ ideje, nem a meccs órája.

## Technika

- Backend: `handball/annotations.py` (normalizálás, korlátok, CSV),
  végpontok: `GET/PUT /matches/{id}/annotations`,
  `GET /matches/{id}/annotations.csv`.
- Kliens: `client/lib/ui/annotation_screen.dart`.
- Tesztek: `backend/tests/test_annotations.py`, és a kliens-őr a
  `test_client_ui.py`-ban (a típuslisták és a korlátok a két oldalon
  egyeznek).
