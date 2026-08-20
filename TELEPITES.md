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
   **SportMachine** alkalmazás.
3. **Húzd át** az alkalmazást a **Programok** (Applications) mappába, és onnan
   indítsd.
4. Első indításnál a Mac szólhat, hogy „ismeretlen fejlesztőtől származik":
   **jobb klikk (vagy Ctrl+kattintás) az ikonon → Megnyitás → Megnyitás**.
   Ezt csak egyszer kell. (Ha „sérült" üzenetet adna: nyiss egy Terminált, és
   írd be: `xattr -cr /Applications/SportMachine.app` — majd indítsd újra.)
5. Első indításkor „Az elemző motor indítása…" képernyő jelenik meg pár
   másodpercig — ez normális.

---

## Első indítás: fiók és feltételek

Az első indításnál a program **fiókot kér**:

1. Add meg az e-mail címed és egy legalább 8 karakteres jelszót (a neved és a
   csapatod nem kötelező).
2. Olvasd el a **felhasználási feltételeket** (a linkre kattintva a teljes
   szöveg megnyílik), és pipáld ki az elfogadást — enélkül a fiók nem jön létre.
3. **Fiók létrehozása** → és már bent is vagy.

Tudnivalók:

- A fiók a **saját gépeden** készül el, a program adatmappájában — nincs felhő,
  a jelszavad nem hagyja el a laptopot (és nem is tárolódik nyíltan, csak
  visszafejthetetlen lenyomatként).
- A belépés **90 napig** érvényes: nem kell minden indításkor újra belépni.
- Kilépni a jobb felső **fiók-ikonra** kattintva tudsz; ugyanott bármikor újra
  elolvashatod a feltételeket.
- Ha a feltételek szövege később megújul, a program belépéskor felkínálja
  elfogadásra — az elfogadás időpontját a fiókod őrzi.

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

## Automatikus frissítés

A programot **csak egyszer** kell telepíteni. Utána — a Claude alkalmazáshoz
hasonlóan — **magától észreveszi**, ha új verzió jelent meg:

1. Az **Áttekintés** képernyő tetején megjelenik egy arany sáv:
   *„Új verzió érhető el"*.
2. Kattints a **Frissítés most** gombra — a program letölti az új verziót,
   kicseréli önmagát, és **újraindul**. Semmi mást nem kell tenned.
3. Ha inkább később frissítenél, kattints a **Később** gombra. Kézzel is
   kereshetsz frissítést a fejléc **⭳ Programfrissítés keresése** ikonjával.

### Privát repónál: frissítési kulcs (egyszeri beállítás)

Ha a repó **privát**, a program csak egy GitHub-kulccsal (token) látja a
kiadásokat. Ezt **egyszer** kell megadni:

1. Böngészőben: **github.com → jobb felül a profilképed → Settings →
   Developer settings → Personal access tokens → Fine-grained tokens →
   Generate new token**.
2. Beállítások a tokenhez:
   - **Repository access:** *Only select repositories* → válaszd ki a
     `handball_01` repót.
   - **Permissions → Repository permissions → Contents:** *Read-only*.
   - Lejárat: állítsd hosszúra (pl. 1 év) — lejáratkor újat kell megadni.
3. **Generate token** → másold ki a `github_pat_…` kezdetű kulcsot.
4. A programban: fejléc **⭳ ikon → Frissítési kulcs (privát repóhoz)** →
   illeszd be → **Mentés**. A program rögtön ellenőrzi, hogy működik-e.

A kulcs **csak a te gépeden** tárolódik, és csak olvasásra jó ehhez az egy
repóhoz. Ezután az automatikus frissítés privát repóval is ugyanúgy működik.

---

## Gyakori kérdések

**Nem indul el / „A motor nem indult el" üzenet.** Zárd be, és indítsd újra a
programot. Ha marad, kattints az **Újrapróbálom** gombra a kezdőképernyőn.

**Lassú a feldolgozás.** Az elemzés a videó hosszától és a géped erejétől függ.
Erősebb (videokártyás) gépen gyorsabb. Hagyd a háttérben dolgozni.

**Elveszik-e a munkám, ha bezárom?** Nem. A feldolgozott meccsek megmaradnak, és
az **Áttekintés** fülön később is ott lesznek.

**Kell hozzá internet?** A telepítéshez igen (letöltés). Utána a program a saját
gépeden fut, internet nélkül is elemez — a fiók és a belépés is a saját gépeden
működik.

**Elfelejtettem a jelszavamat.** A fiókok csak a te gépeden vannak, ezért nincs
e-mailes visszaállítás. Ilyenkor hozz létre új fiókot — a korábbi meccseid és
elemzéseid megmaradnak, azok nem a fiókhoz, hanem a géphez tartoznak.
