# Mérési jegyzőkönyv — esemény-felismerési pontosság valós meccseken

Ez a napló a SportMachine TRL-4 bizonyítéka: minden kézzel annotált,
VALÓS meccsfelvételen futtatott pontosság-mérés egy dátumozott,
verziózott sor. A pályázati felkészülés része
(`docs/PALYAZAT_EIC_PRE_ACCELERATOR.md`, 4. pont).

Új sor felvétele (a mérés után automatikusan ide ír):

    cd backend && python -m scripts.validate_match \
        data/matches/<id>.json igazsag.csv --jegyzokonyv

A precizitás/visszahívás oszlopok formátuma: `P/R`. Az ítélet a
beépített cél-küszöbökhöz mért (MEGFELEL/GYENGE — lásd
`pipeline/validation.py`).

| Dátum | Verzió | Meccs | Gól P/R | Lövés P/R | Össz F1 | Ítélet |
|---|---|---|---|---|---|---|

## Sebesség — mennyi idő az elemzés

Az edző nem vár órákat: a kész termék sebesség-célja
(`docs/ROADMAP.md`, "Sebesség-cél"), hogy egy 60 perces meccs TELJES
elemzése (felismerés + minden réteg) a pilot GPU-s szerverén 15 percen
belül, a "gyors kép" (eredmény, lövés-térkép, edzői összefoglaló) 3
percen belül kész legyen. A réteg-rész (a kész követésből a 500+
elemző réteg) kerete ebből ≤ 5 perc CPU-n — ezt méri a sebesség-profil
szimulált, teljes hosszú meccsen; a felismerés (detektálás) idejét a
pilot VALÓDI felvételen méri, külön sorban.

Új sor felvétele (a mérés után automatikusan ide ír):

    cd backend && python -m scripts.speed_profile --jegyzokonyv

A szám gépfüggő, ezért a Gép oszlop a mérés része. Hogy melyik réteg
viszi az időt: `docs/SEBESSEG.md`. Az ítélet a réteg-részre, a 60
percre vetítve (MEGFELEL/GYENGE — `scripts/speed_profile.py`,
`SEBESSEG_CEL_RETEGEK_S`).

| Dátum | Verzió | Felvétel | Rétegek | Réteg-csomag | Gyors kép | Gép | Ítélet |
|---|---|---|---|---|---|---|---|
| 2026-11-06 | v0.1.193+46c856d3 | szimulált, 60 perc, 30000 kocka | 521 | 2 perc 4 mp | 1 perc 20 mp | x86_64, 4 mag, Python 3.11.17 | MEGFELEL |
| 2026-11-07 | v0.1.193+855e17e4 | szimulált, 60 perc, 30000 kocka | 521 | 1 perc 36 mp | 1 perc 3 mp | x86_64, 4 mag, Python 3.11.17 | MEGFELEL |
| 2026-11-07 | v0.1.193+3a9da7c5 | szimulált, 60 perc, 30000 kocka | 521 | 1 perc 16 mp | 1 perc 4 mp | x86_64, 4 mag, Python 3.11.17 | MEGFELEL |
| 2026-11-07 | v0.1.193+8aa0932e | szimulált, 60 perc, 30000 kocka | 521 | 1 perc 9 mp | 59,0 mp | x86_64, 4 mag, Python 3.11.17 | MEGFELEL |
