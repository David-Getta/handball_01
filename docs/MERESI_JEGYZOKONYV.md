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
