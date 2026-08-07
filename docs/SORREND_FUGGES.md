# Sorrend-függés — mely rétegre hat a kapus-jelölés

*Generált fájl — ne kézzel szerkeszd. Frissítés:*
`cd backend && python -m scripts.order_sensitivity`

A `detect_goalkeepers` beleír a meccsbe (`role = "kapus"`), és
több réteg a szerepből dolgozik. Az alábbi rétegek eredménye
ezért ATTÓL FÜGG, megtörtént-e már a kapus-jelölés, amikor
lefutnak — egy nagy összeállításban tehát a kiértékelés
sorrendjétől. Ez a lista a döntés alapja: hol érdemes kimondott,
determinisztikus szerep-jelöléssel indítani.

Mérés: 240 mp-es szimulált meccs (mag: 7); **364 réteg** összevetve, ebből **0 sorrend-függő**.

## A mérés köre

**Fontos: ez a mérés a rétegeket KÖZVETLENÜL hívja, hatókör
nélkül.** A termék viszont `primitive_cache` hatókörben futtatja
őket (meccs-csomag, elemzés-végpontok, felderítés), a hatókör
nyitása pedig ELVÉGZI a kapus-jelölést — ott tehát a sorrend nem
számít. Az alábbi lista így azt mondja meg, mely rétegek
SZEREP-FÜGGŐK: ezeket közvetlenül (hatókörön kívül) hívva más
számot kaphatsz, mint a terméken belül.

A szimuláció ebben a futásban LŐ is (6
lövés/perc, a hazai mezőnyjátékosok körbejárva), tehát a
lövés-alapú rétegek valódi bemenetet kaptak. A szimuláció
alapértelmezésben csak mozgást modellez — enélkül ezek a
rétegek üres bemeneten futnának, és a mérés róluk nem
mondana semmit.

A szimuláció viszont EGY állóképet modellez: a hazai csapat
támad, a vendég 6-0-ban véd. Nincs birtoklás-váltás, tehát a
VENDÉG TÁMADÓ oldaláról (és minden átmenet-rétegről) ez a
mérés sem mond semmit — azokat valós felvételen kell
ellenőrizni.

Ezen a mintán egyetlen réteg sem bizonyult sorrend-függőnek.
