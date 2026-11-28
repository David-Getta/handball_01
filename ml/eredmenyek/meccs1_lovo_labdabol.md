# Ki lő? — a lövő a labdából (1. meccs)

A labdafelismerő (v2) a teljes 1920×1080 kockán, az elengedés körül ±2 kockán; a lövő az, akinek
a csuklója a labdajelöltekhez legközelebb van (megbízhatóság × csukló-közelség × méret-illeszkedés, a ±2 kockán összegezve). Kézi labda-kattintás NINCS; az elengedés
kockája még a kézi jelölésé.

**Félretett** = a labdafelismerő tanításából kimaradt lövések (ugyanaz a 20%, mint a labda-
kiértékelésnél) — ez a becsületes szám. Az **összes** klipen a labdafelismerő a klipek 80%-án
tanult, ezért az optimista.

| | félretett | összes (optimista) |
|---|---|---|
| klipek | 40 | 184 |
| a lövő a pózbecslő emberei közt van | 25 | 117 |
| testpont-választó (eddigi), ha a lövő jelölt | 52% | 50% |
| **labda-választó**, ha a lövő jelölt | **48%** | 53% |
| testpont + labda (tanult), ha a lövő jelölt | 60% | 60% |
| labda-választó, az összes klipből | 30% | 34% |
| a lövő HELYE — testpont-választó, az összesből | 60% | 55% |
| a lövő HELYE — testpont + labda, az összesből | 72% | 65% |
| **a lövő HELYE — labda-választó** (ember vagy labda), az összesből | **68%** | 58% |

A „lövő helye” azt méri, hogy a választott pont (a választott ember közepe, vagy ha embert nem
talál, a labda) a követett lövő dobozába esik-e. Ez kell a ráközelítő követés indításához — ott
eddig a kézi kattintás állt.

## Célzóna lent / fent — teljesen automatikusan

A lövő köré vágott képen a labda követve (hbd.ball.track), az elválás → repülés iránya.

- Félretett lövések (lent/fent: 25, ebből követhető repülés: 25), kézi pontokon tanított modell, automatikus repüléssel: **68% kiegyensúlyozott** (véletlen: 50%).
- Ugyanez a kézi labdapontokkal (felső korlát, 24 klip): 82%.
- Minden klipen, automatikus repüléssel, csoportosított CV (140 klip; optimista): 55%.

Megjegyzés: a félretett halmaz kicsi (≈40 lövés, ebből a lent/fent zónás még kevesebb) —
a különbségek pár lövésen múlnak. A végleges számot a második meccs adja.

## Olvasat

- **A lövő kiválasztása:** a labda egyedül nem jobb a testpont-választónál (48% vs 52% a
  félretett klipeken, 25 klipből), de a kettő együtt (a tanult választó labda-jellemzőkkel)
  **60%** (az eddigi 50–52% helyett).
- **A lövő helye** (amiből a ráközelítő követés indulhat — eddig ehhez kellett a kézi
  kattintás): testpont + labda **72%** a félretett klipeken (az eddigi 60% helyett), azokon a
  klipeken is, ahol a pózbecslő a lövőt külön emberként nem találja (40-ből 15).
- **Célzóna lent / fent, kattintás nélkül:** 68% kiegyensúlyozott a félretett 25 lövésen;
  ugyanezeken a kézi labdapontokkal 82% — a különbség a labdafelismerő hibája.

## Fenntartások

- Az **elengedés kockája** még a kézi jelölésé (a meccs-lövésjelölőből). Ahol az rossz (pl.
  m1_000: 65. kocka, a labda valójában a 76.-ban válik el), a ±2 kockás ablak nem találhat.
  A teljesen automatikus lánchoz az elengedés-becslő (medián hiba 80 ms) kell elé.
- A pontozás három beállítását (összegzés, SIGMA, méret-illesztés) 70 klipen választottuk,
  köztük 16 félretett is volt — a félretett szám emiatt kissé optimista.
- **Kocka-elcsúszás:** a `match_shots._orig_frames` az ffmpeg alap időzítésével olvas, ami a
  pontos ugrásnál az első kockát néha megduplázza (`[F, F, F+1, …]`); a klip-pózok 104/185-e
  így készült, ott a pózok 1 kockával (40 ms) késnek. Ez a modul saját, pontos olvasót
  használ (`-fps_mode passthrough`), és a póz-indexet klipenként korrigálja (`pose_lag`).
- Az álló hamis jelöltek szűrése (`suppress_static`) ezen a meccsen nem változtatott.

## Futtatás

    python -m hbd.shooter_ball --video meccs.mp4 --clips m1web/manifest.json \
        --poses m1_clip_poses --zoom m1_zoom2 --labels cimkek/meccs1_lovesek_cimkek.json \
        --ball-labels cimkek/meccs1_labda_cimkek.json --ball-manifest m1ball2/ball_manifest.json \
        --weights runs_ball/labda2/weights/best.pt --cache sb_cache --out res/

(CPU-n, 2 szálon kb. 15 s/klip a teljes képes kereséssel; a `--cache` miatt folytatható.)
