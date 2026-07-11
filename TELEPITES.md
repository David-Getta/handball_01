# Sport Machine — Telepítés (egyszerű útmutató)

Ez az útmutató **bárkinek** szól, informatikai tudás nélkül is. A cél: pár perc
alatt működjön a program a gépeden.

---

## Windows

1. **Töltsd le** a `SportMachine-Setup.exe` fájlt a repo **Releases** oldaláról (vagy a kapott linkről).
2. **Kattints rá duplán.** Ha a Windows figyelmeztetést ad ("Ismeretlen kiadó"),
   kattints a **Több információ → Futtatás mindenképp** gombra. (Ez normális egy
   új programnál.)
3. Kövesd a telepítőt: **Tovább → Tovább → Telepítés**. Pár másodperc.
4. A végén pipáld be az **Asztali parancsikon** lehetőséget, majd **Befejezés**.
5. Indítsd el az asztalon megjelent **Sport Machine** ikonnal.

Első indításkor egy „Az elemző motor indítása…" képernyő jelenik meg pár
másodpercig — ez normális. Utána megnyílik a program.

---

## Mac

1. **Töltsd le** a `SportMachine-macOS.zip` fájlt a repo **Releases** oldaláról.
2. **Kattints rá duplán** — a Mac kicsomagolja, és megjelenik a
   **handball_client** alkalmazás.
3. **Húzd át** az alkalmazást a **Programok** (Applications) mappába, és onnan
   indítsd.
4. Első indításnál a Mac szólhat, hogy „ismeretlen fejlesztőtől származik":
   **jobb klikk (vagy Ctrl+kattintás) az ikonon → Megnyitás → Megnyitás**.
   Ezt csak egyszer kell. (Ha „sérült" üzenetet adna: nyiss egy Terminált, és
   írd be: `xattr -cr /Applications/handball_client.app` — majd indítsd újra.)
5. Első indításkor „Az elemző motor indítása…" képernyő jelenik meg pár
   másodpercig — ez normális.

---

## Mit tudsz csinálni a programban?

1. **Feltöltés** fül → kattints a mezőre, és válaszd ki a meccsvideót. Feltölti.
2. **Pálya-kalibráció (4 sarok)** → húzd a négy pontot a pálya sarkaira, majd
   **Mentés**. (Ez segít a pontos elemzésben.)
3. **Feldolgozás indítása** → megjelenik a haladás. Amikor kész, magától
   megnyílik a meccs elemzése.
4. **Áttekintés** fül → itt látod az összes korábbi meccsedet; bármelyikre
   kattintva újra megnyílik.
5. **Élő követés** fül → a meccs lejátszása közben valós idejű edzői javaslatok.

---

## Gyakori kérdések

**Nem indul el / „A motor nem indult el" üzenet.** Zárd be, és indítsd újra a
programot. Ha marad, kattints az **Újrapróbálom** gombra a kezdőképernyőn.

**Lassú a feldolgozás.** Az elemzés a videó hosszától és a géped erejétől függ.
Erősebb (videokártyás) gépen gyorsabb. Hagyd a háttérben dolgozni.

**Elveszik-e a munkám, ha bezárom?** Nem. A feldolgozott meccsek megmaradnak, és
az **Áttekintés** fülön később is ott lesznek.

**Kell hozzá internet?** A telepítéshez igen (letöltés). Utána a program a saját
gépeden fut, internet nélkül is elemez.
