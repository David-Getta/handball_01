# Annotációs útmutató — valós meccs pontosság-méréshez

Ez a recept zárja le a TRL 4-et valós adaton (lásd
`docs/PALYAZAT_EIC_PRE_ACCELERATOR.md`, 4. pont): egy valós
meccsfelvételből dokumentált precizitás/visszahívás mérés lesz a
mérési jegyzőkönyvben. Egy mérés kb. 60–90 perc emberi munka.

## 1. Feldolgozás

```bash
cd backend
python -m scripts.process_video /ut/a/felvetelhez.mp4
# → a meccs a data/matches/<id>.json alá kerül
```

## 2. Előtöltött annotációs sablon

A motor a saját felismeréseit kiírja ellenőrizhető CSV-be — az
annotátornak nem nulláról kell gépelnie:

```bash
python -m scripts.validate_match data/matches/<id>.json --sablon sablon.csv
# vagy a futó szerveren: GET /matches/<id>/validation-template
```

A sorok formátuma: `idő(perc:mp), típus (gól/lövés), csapat
(hazai/vendég)`.

## 3. Kézi javítás (az annotátor dolga)

A felvételt nézve a `sablon.csv`-ben:
- **töröld** a téves sorokat (a motor olyat látott, ami nem volt),
- **add hozzá** a kimaradt gólokat/lövéseket a videó órája szerint,
- a kapott `igazsag.csv` a kézi ground-truth.

Szabályok a következetességhez:
- a lövés ideje az elengedés pillanata, a gólé a gólvonal-átlépés;
- a blokkolt/mellé lövés is „lövés”; a hetes-gól „gól”;
- kétes esetet a videó lassítva dönt el, ne a jegyzőkönyv.

## 4. Mérés és jegyzőkönyvezés

```bash
python -m scripts.validate_match data/matches/<id>.json igazsag.csv \
    --jegyzokonyv [--out riport.html]
```

- A kimenet: gól/lövés precizitás, visszahívás, F1 + MEGFELEL/GYENGE
  ítélet a beépített cél-küszöbökhöz mérve.
- A `--jegyzokonyv` kapcsoló a mérést dátumozott, git-verziózott
  sorként a `docs/MERESI_JEGYZOKONYV.md` naplóhoz fűzi — ez a
  pályázati TRL-evidencia.
- A HTML-riport (`--out`) megosztható a klubbal/edzővel.

## 5. Célszámok

A pályázati vállaláshoz meccsenkénti mérés helyett a napló
ÖSSZKÉPE számít: legalább 3–5 különböző csarnokban, különböző
kameraállással mért meccs, verziónként újramérve. A cél-küszöböket a
`pipeline/validation.py` rögzíti (VALIDATION_TARGET_*) — a napló
sorai ezekhez mérten mondanak MEGFELEL/GYENGE ítéletet.
