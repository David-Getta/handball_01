# A detektor finomhangolása kézilabdára

A program alapból egy általános YOLOv8-modellt használ — embert jól talál,
de a kis, gyors kézilabdát gyakran elveszti, és a tömörülésekben (falazás,
beállós körüli harc) téveszt. A pontosság következő szintje a SAJÁT
felvételeken finomhangolt modell. Ez a leírás a teljes munkafolyamat.

## Áttekintés (3 lépés)

```
1. GYŰJTÉS    python -m scripts.collect_dataset MECCS.mp4 --out dataset
2. ÁTNÉZÉS    a címkék javítása címkéző eszközben (CVAT / LabelImg)
3. TANÍTÁS    python -m scripts.finetune --data dataset/dataset.yaml --install
```

## 1. Tanítóadat gyűjtése (előcímkézés)

A gyűjtő a meglévő modellel ELŐCÍMKÉZI a mintavételezett képkockákat —
így nem nulláról kell dobozokat rajzolni, csak javítani:

```bash
cd backend
python -m scripts.collect_dataset MECCS1.mp4 MECCS2.mp4 --out dataset --samples 200
```

- Videónként ~200 egyenletesen elosztott képkockát ment (a sötét
  bevezetőket kihagyja), YOLO-formátumban: `images/train|val` +
  `labels/train|val` + `dataset.yaml`.
- Osztályok: `0 = person` (játékos), `1 = ball` (labda).
- Több videóból érdemes gyűjteni (különböző csarnok, mez, fényviszony) —
  ugyanabba a `--out` mappába futtatva az adathalmaz együtt nő.
- A kiírt összegzőben figyeld a "labda a képek X%-án" értéket: ha
  alacsony, a címkézésnél a labda pótlása a legfontosabb munka.

## 2. A címkék átnézése (ez adja a minőséget!)

Az előcímkék kb. 80–90%-ban jók — a maradék javítása embert igényel:

- **CVAT** (ingyenes, böngészős: cvat.ai) vagy **LabelImg** — mindkettő
  tudja a YOLO-formátumot importálni/exportálni.
- Mire figyelj:
  - **hiányzó labda-dobozok pótlása** (ez a leggyakoribb hiba és a
    legnagyobb nyereség);
  - tömörülésekben szétválasztani az összemosott játékos-dobozokat;
  - a lelátón/kispadon lévő embereket NE címkézd játékosnak — töröld
    (a pálya-régió szűrés élesben is kidobja őket, de a tanítóadatban
    csak zajt jelentenek);
  - a bírót játékosként hagyhatod (person) — a szín-szűrő élesben kezeli.
- Ökölszabály: **300–500 gondosan átnézett kép** már mérhető javulást ad;
  1000+ képpel és több helyszínnel lesz igazán jó.

## 3. Tanítás és élesbe állítás

```bash
python -m scripts.finetune --data dataset/dataset.yaml --epochs 60 --install
```

- GPU-n (NVIDIA/Apple Silicon) fut gyorsan; CPU-n is működik, csak lassú.
- A `--install` a kész modellt a felhasználói súly-mappába másolja
  (`yolov8n.pt` néven, a régi fájl `.bak` mentésével) — a feldolgozó ezt a
  mappát részesíti előnyben, így **a program azonnal az új modellt
  használja**, beállítás nélkül.
- Visszaállás az alapmodellre: töröld a felhasználói `weights/yolov8n.pt`
  fájlt (a rendszer újra letölti az eredetit), vagy másold vissza a `.bak`-ot.
- A feldolgozó a modell OSZTÁLYNEVEIBŐL ismeri fel a kiosztást (person/ball),
  ezért az előtanított (COCO) és a saját 2 osztályos modell is működik.

## Mérés: jobb lett-e?

- **Egy paranccsal, egymás mellett** (ez a fő eszköz):

  ```bash
  python -m scripts.compare_models MECCS.mp4 \
      --weights-b runs/handball/weights/best.pt
  ```

  Eredménylap (Markdown + JSON) készül a kulcsmutatókkal: **labda-
  lefedettség %** (ezen múlik az eseményfelismerés), átlagos játékos-
  darabszám és annak ingadozása, bizonyosságok, sebesség. A `--weights-b`
  nélkül futtatva a kiindulási szintet méred (tanítás ELŐTT érdemes).
- A tanítás végén az ultralytics is kiír val-metrikákat (mAP50 stb.) —
  a labda-osztály javulása a lényeg.
- Éles ellenpróba: dolgozd fel ugyanazt a félidőt mindkét modellel, és
  vesd össze a minőség-jelentést + az eseménylistát.

## Tippek

- Gyűjts a SAJÁT csarnokaidból és mezekkel — a modell arra lesz jó, amit lát.
- Vegyíts nappali/esti világítást, közeli/távoli pásztázást.
- A `--samples` növelése helyett inkább TÖBB KÜLÖNBÖZŐ videóból gyűjts.
- Az adathalmazt érdemes verziózni (pl. dataset-2026-07/), hogy a tanítások
  összehasonlíthatók legyenek.
