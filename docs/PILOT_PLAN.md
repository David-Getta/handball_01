# TRL 7–8 sprint-terv — a leggyorsabb út az éles pilotig

A kód (TRL 4) kész és tesztelt. Innen a szintlépések **nem kódolással**, hanem
**valós validációval** jönnek — a kritikus úton a projektgazda lépései állnak.
Ez a terv a legrövidebb utat írja le, mérhető kapukkal.

---

## 1. hét — TRL 5: a lánc valódi adaton (kapu: minőség-pontszám)

**Teendők (projektgazda):**
1. **Telepítő-build indítása**: GitHub → Actions → `release` → *Run workflow*
   (vagy `git tag v0.1.0 && git push origin v0.1.0`). Ha hibázik, a log-üzenetet
   vissza a fejlesztésbe — jellemzően 1-2 iteráció.
2. **Telepítés a saját gépre** a kész `SportMachine-Setup.exe`-vel.
3. **Egy valódi meccsrészlet feldolgozása** az appból: feltöltés → kalibráció
   (4 sarok) → feldolgozás. GYORS teszthez: rövid (1-2 perces) részlet.

**Kapu (mérhető):** a meccs **minőség-jelvénye** (a meccs-nézet fejlécében)
- játékos-lefedettség: átlag ≥ 8 mért játékos/kocka,
- labda-lefedettség: ≥ 30% (ez alatt a birtoklás-elemzés jelezve gyenge),
- összpontszám ≥ 60/100 figyelmeztetések nélkül, vagy ismert okú figyelmeztetésekkel.

**Ha a kapu nem teljesül:** a minőség-párbeszéd teendőt ír (kalibráció,
tisztább felvétel, --start). A tipikus első hibák (sötét intró, bíró, kispad)
már kezelve vannak.

## 2. hét — TRL 6: teljes rendszer-demó éles formátumban

**Teendők:**
1. **Egy TELJES félidő** feldolgozása (30 perc). CPU-n ez órákig tarthat —
   éjszakára időzítve, vagy NVIDIA GPU-s gépen (a motor automatikusan használja
   a CUDA-t, ha elérhető).
2. A teljes edzői kör végigpróbálása a valódi meccsen: könyvtár → elemzés →
   események → felderítés → nyomtatott jelentés → figura-tervező.
3. `flutter analyze` + az app kipróbálása egy MÁSIK (tiszta) gépen a telepítőből.

**Kapu:** egy kívülálló (nem fejlesztő) a TELEPITES.md alapján, segítség nélkül
eljut a nyomtatott felderítő jelentésig.

## 3–6. hét — TRL 7: pilot egy igazi csapattal

**Teendők:**
1. **Pilot-partner**: egy csapat (akár a sajátod), heti 1-2 meccs feldolgozása.
2. Meccsenként: feldolgozás → minőség-pontszám naplózása → felderítő jelentés a
   következő ellenfélről → az edző HASZNÁLJA a meccsfelkészülésben.
3. **Visszajelzés-napló** (egyszerű táblázat): dátum, meccs, minőség-pontszám,
   "mi volt hasznos", "mi hiányzott/hibás". Ezek hajtják a javításokat.

**Kapuk (mérhetők):**
- ≥ 6 meccs feldolgozva, medián minőség-pontszám ≥ 60,
- az edző szerint a jelentés ≥ 3 meccsnél adott VALÓDI felkészülési előnyt,
- 0 adatvesztés (a könyvtár minden meccse visszanyitható).

## 7–8. hét — TRL 8: rendszer-minősítés

- A pilot alatt talált hibák javítva, a kiadás verziózva (v1.0),
- TELEPITES.md + a jelentések alapján egy MÁSIK csapat/edző is önállóan használja,
- (opcionális) aláírt telepítő a SmartScreen-figyelmeztetés ellen.

---

## Ismert kockázatok és ellenszereik

| Kockázat | Ellenszer |
|---|---|
| CI-build elsőre hibázik | a workflow füstteszttel bukik korán; a log alapján gyors javítás |
| CPU-feldolgozás lassú teljes meccsre | GPU-s gép a pilothoz; vagy éjszakai futás; stride növelése |
| Labda-lefedettség alacsony a felvételen | minőség-jelvény jelzi; közelebbi/élesebb kamera a pilotnál |
| Kalibráció-hiba (rossz sarkok) | az app élő előnézete + a minőség-figyelmeztetés fogja meg |
| Az edzőnek nem elég pontos az elemzés | a visszajelzés-napló célzottan mutatja, mit kell hangolni |

## Mit tud a rendszer MÁR MOST a pilothoz (beépítve)

- **Minőség-önellenőrzés** minden feldolgozásnál (pontszám + magyar teendők),
- zaj-kezelés (labda-kiugrók/hézagok, játékos-remegés, sötét intró),
- pásztázás-kompenzáció + képen kívüli becslés + kiállítás-korrekció,
- a teljes edzői kör: elemzés → felderítés → nyomtatható jelentés → playbook →
  fejlődés-követés,
- automata telepítő-gyártás (GitHub Actions → Releases).
