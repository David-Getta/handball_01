"""
[Minőség-jelentés] — a feldolgozás ÖNELLENŐRZÉSE, pilothoz nélkülözhetetlen.

TRL 7-8 (éles pilot) követelmény: a rendszer FEJLESZTŐ NÉLKÜL is meg tudja
mondani, mennyire megbízható egy feldolgozás eredménye, és mit tegyen a
felhasználó, ha gyenge. Ez a modul a kész Tracking-ből számol:

- játékos-lefedettség: átlagos mért játékos/kocka, a "elég játékost látunk"
  kockák aránya, a becsült pozíciók aránya,
- labda-lefedettség: a labdás kockák aránya, a leghosszabb labda-hézag,
- 0-100-as összpontszám + MAGYAR figyelmeztetések konkrét teendővel
  ("Kevés labda-észlelés — ellenőrizd a kalibrációt / válassz tisztább szakaszt").

Tiszta adatfeldolgozás, videó nélkül tesztelhető.
"""

from __future__ import annotations

from ..models.tracking import Match, PositionSource

# Elvárások (teljes létszámú kézilabda): 2x7 játékos van a pályán.
EXPECTED_PLAYERS = 14
# "Elég játékos látszik" küszöb egy kockára (pásztázó kamerán sosem látszik mind).
GOOD_FRAME_MIN_PLAYERS = 8

# TÚL sok mért játékos: a pályán 14 lehet; a kispad, a bíró és a
# partjelző még belefér a mérés zajába, de e fölött az észlelések már
# biztosan nem a pályán lévő játékosok (nézőtér, kispad, vagy — a
# leggyakoribb ok — hibás pálya-kalibráció, ami a lelátót is a pályára
# vetíti). Ez NEM apró pontatlanság: ilyenkor a birtoklás, a fal-forma
# és a távolság-alapú rétegek mind mást mérnek, mint amit mondanak.
TOO_MANY_PLAYERS = 18.0
# Ha ennyinél több játékost mérünk kockánként, a feldolgozás egésze
# megkérdőjelezhető — hiába jó a labda-lefedettség. A birtoklás, a
# fal-forma és minden távolság-alapú réteg téves alapokon áll, tehát az
# összpontszám ezt a plafont nem lépheti át.
TOO_MANY_SCORE_CAP = 35

# E pontszám alatt a feldolgozás állításai bizonytalan alapokon állnak,
# és ezt a JELENTÉSEK ELEJÉN kell kimondani — nem a végén, és nem egy
# külön ablakban. A küszöböt az edzői összefoglaló és a nyomtatható
# meccsjelentés is innen veszi, hogy ne csússzanak szét.
LOW_SCORE_WARN = 50

# A felvétel LEFEDETTSÉGE: a feldolgozott szakasz ekkora aránya alatt
# szólunk, hogy a videónak csak egy részét elemeztük. Egy meccs-videó
# elején-végén van holt idő, és a kézi meccs-ablak is vág — a jelzés
# nem hiba, hanem tájékoztatás: aki azt hiszi, a teljes meccset
# elemezte, ne a számokból jöjjön rá, hogy nem.
VIDEO_COVERAGE_WARN_PCT = 60.0

# Réteg-megbízhatóság: a LABDA-alapú rétegek (birtoklás, passz, eladott
# labda, lövés) ekkora labda-lefedettség alatt nem megbízhatók. A 40%
# nem szigorúbb a figyelmeztetés 30%-os küszöbénél véletlenül: ott azt
# mondjuk ki, hogy BAJ VAN, itt azt, hogy ezekre a számokra nem érdemes
# meccstervet építeni — a kettő nem ugyanaz.
BALL_CONFIDENCE_PCT = 40.0

# Eladott labda / perc: e FÖLÖTT a szám már nem a játékról szól. Egy
# kézilabda-meccsen csapatonként nagyjából fél-másfél labdaeladás jut
# egy percre; négy fölött a birtokos-váltás BILLEG (a birtokos a
# labdához legközelebbi játékos, és tömörülésnél vagy zajos
# labda-észlelésnél ez kockánként ide-oda ugrik). Ilyenkor az
# eladás-alapú rétegek nem a csapatról állítanak valamit.
TURNOVER_RATE_MAX_PER_MIN = 4.0

# Gól / perc: e ALATT a felismerés nyilvánvalóan gólokat HAGYOTT KI.
# Felnőtt kézilabdában a két csapat együtt nagyjából 0,8–1,0 gólt szerez
# percenként (55–60 gól hatvan perc alatt); ennek a HARMADA már nem
# szoros meccs, hanem hiányzó felismerés. Csak ennél hosszabb
# felvételre nézzük — pár perces próbán a szórás önmagában eldönti.
GOALS_PER_MIN_LOW = 0.30
GOALS_RATE_MIN_MINUTES = 10.0

# Aránytalan eredmény: ennyi összes gól fölött nézzük, és ekkora
# szorzó fölött szólunk. Kézilabdában a nagy különbség is jellemzően
# kétszeres arány körül van (35-20); ötszörös arány (25-5) inkább azt
# jelenti, hogy az EGYIK KAPU felismerése hibás — például a kalibráció
# csak az egyik térfélre sikerült.
GOALS_LOPSIDED_MIN_TOTAL = 12
GOALS_LOPSIDED_FACTOR = 5.0

# KLIP vagy MECCS? Egy kézilabda-meccs 2x30 perc; ennél a küszöbnél
# rövidebb felvétel nem meccs, hanem KLIP (egy támadás-sorozat, egy
# félidő-részlet, egy próba). A klip teljesen jogos bemenet — de a
# meccs-szintű rétegek (hajrá, félidő-összevetés, kondíció, momentum)
# némán hallgatnak rajta, és a felhasználó ezt eddig HIBÁNAK látta:
# "megcsináltam, és a fele üres". Egy mondat elveszi ezt.
#
# IDŐTARTAM, tehát másodpercben (a termék minden 3. kockát dolgozza
# fel, egy kockában megadott küszöb a profiltól függően háromszoros
# valós időt jelentene).
CLIP_LENGTH_S = 1200.0   # 20 perc — ez alatt klip, nem meccs

# ELSŐ TEENDŐ: a figyelmeztetések fontossági SORRENDJE. Egy gyenge
# feldolgozás jellemzően négy-hat figyelmeztetést kap egyszerre, és a
# felhasználó ilyenkor nem tudja, mivel kezdje — pedig a lista eleje és
# a vége nem egyenrangú: a rossz kalibrációt kijavítva a többi jelzés
# fele magától eltűnik, míg a mezszám-hozzárendelés a rossz alapokon
# semmit nem ér.
#
# A párok: (a figyelmeztetésben KERESETT részlet, az EGY mondatos
# teendő). Az első találat nyer.
NEXT_ACTION_ORDER: tuple = (
    ("TÚL sok játékos",
     "Kalibrálj újra: a 4 sarokpont a JÁTÉKTÉR sarkain álljon. Amíg a "
     "nézőtér is a pályára esik, egyik szám sem használható."),
    ("kalibráció NÉLKÜL futott",
     "Jelöld be a 4 pályasarkot az Új elemzés lapon (a Sarkok javaslata "
     "gomb elő is tölti), és futtasd újra."),
    ("a pályán KÍVÜLRE esik",
     "Nyisd meg a Pálya-kalibrációt, és igazíts a sarokpontokon: a "
     "rajzolt 6 m-es és 9 m-es vonalnak rá kell ülnie a valódira."),
    ("meccs tényleges kezdetét nem sikerült",
     "Add meg a meccs időablakát (perc:másodperc) az Új elemzés lapon: "
     "a bemelegítés és a csapatbemutatás enélkül meccsnek számít."),
    ("Kevés játékos látszik",
     "Ellenőrizd, hogy a kamera a játékteret mutatja-e, és hogy a "
     "kalibráció a látható térfélre készült-e."),
    ("Aránytalan eredmény",
     "Nyisd meg a Pálya-kalibrációt, és ellenőrizd MINDKÉT térfelet: a "
     "rajzolt 6 m-es és 9 m-es vonalnak mindkét oldalon rá kell ülnie a "
     "valódira. Ha a kalibráció jó, az Események listán a hiányzó "
     "gólokat kézzel is felveheted."),
    ("eldönthető a térfélcsere",
     "Ellenőrizd az EREDMÉNYT: ha a második félidő góljai fordítva "
     "vannak, a könyvtárban a meccs sorának ⇄ gombjával fordítsd meg "
     "a gyanús szakaszt — az elemzés újraszámol."),
    ("Gyanúsan kevés gól",
     "Nézd végig az Események listát: a lövésként jelölt gólokat a sor "
     "⋮ menüjében egy kattintással gólra javíthatod (a javítás az "
     "egész elemzésen átüt)."),
    ("Gyanúsan sok hétméteres-jel",
     "Add meg a meccs időablakát (perc:másodperc), hogy a bemelegítés "
     "és a ceremónia kimaradjon."),
    # (A forrásban f-string töréspont van a "dolgoztuk" után — a
    # részlet szándékosan addig tart, hogy a forrás-őr is megtalálja.)
    ("%-át dolgoztuk",
     "Nézd meg a hossz-beállítást és a meccs-időablakot; megszakadt "
     "feldolgozásnál a könyvtárban a Folytatás viszi tovább."),
    ("Nem sikerült kapust azonosítani",
     "Ellenőrizd a kalibrációt: a kapuelőtérnek a pályán BELÜLRE kell "
     "esnie."),
    ("Gyanúsan sok eladott labda",
     "Nézd meg, hogy a felvétel eleje (bemelegítés, csapatbemutatás) "
     "kimaradt-e: add meg a meccs időablakát. Ha a meccs alatt is így "
     "van, a labda-észlelés a szűk keresztmetszet — futtasd újra a "
     "\"Pontos\" profillal."),
    ("Kevés labda-észlelés",
     "Futtasd újra a \"Pontos\" minőségi profillal (nagyobb felbontáson "
     "keresi a labdát) — távoli, széles felvételen ez a leggyorsabb "
     "javulás. A birtoklás- és passz-alapú számokat addig fenntartással "
     "kezeld."),
    ("A követés töredezett",
     "Rendelj mezszámokat a játékosokhoz a meccs-nézetben — a "
     "szétesett track-eket ez köti össze."),
)


def clock_label(seconds: float | None) -> str:
    """Másodperc → "óra:perc:mp" (egy óra alatt "perc:mp").

    A felhasználó a videót ebben az alakban keresi vissza — a "2054
    másodperc" használhatatlan információ, a "34:14" azonnal
    ellenőrizhető a lejátszóban.
    """
    if seconds is None or seconds < 0:
        return "?"
    ossz = int(round(seconds))
    ora, maradek = divmod(ossz, 3600)
    perc, mp = divmod(maradek, 60)
    if ora:
        return f"{ora}:{perc:02d}:{mp:02d}"
    return f"{perc}:{mp:02d}"


def next_action(warnings: list) -> str | None:
    """A legfontosabb EGY teendő a figyelmeztetések közül (vagy None).

    Nem a lista első eleme: a `NEXT_ACTION_ORDER` sorrendje szerint az
    első olyan teendő, amihez tartozik figyelmeztetés. Így a
    felhasználó azzal kezdi, ami a többit is megoldja.
    """
    for reszlet, teendo in NEXT_ACTION_ORDER:
        if any(reszlet in w for w in warnings):
            return teendo
    return None

# Kalibráció-drift: a pálya téglalapján ENNYIVEL kívülre eső mért pozíció
# még belefér (a kifutó szélső, a csereember és a mérés zaja), és a mért
# pozíciók ekkora aránya fölött mondjuk ki, hogy a kalibráció elcsúszott.
#
# Miért ez a jel? A pálya-vetítés EGY kalibrációra épül. Ha a sarokpontok
# rosszul állnak (vagy a kamera elmozdult a rögzítés óta), a játékosok
# rendre a pályán KÍVÜLRE vetülnek — a felhasználó ezt a felülnézeten
# látja is, de nem tudja, mit jelent. Ez a mérés kimondja.
OUT_OF_COURT_TOL_M = 2.0
OUT_OF_COURT_WARN_PCT = 12.0


def compute_quality_report(match: Match) -> dict:
    """A feldolgozás minőség-jelentése a kész Tracking-ből.

    Visszaad egy szótárt: lefedettségi mutatók + score (0-100) + warnings
    (magyar, teendővel). A kliens ezt mutatja a meccs mellett, hogy a
    felhasználó tudja, mennyire bízhat az elemzésben.
    """
    n = len(match.frames)
    if n == 0:
        return {
            "frames": 0, "score": 0,
            "avg_measured_players": 0.0, "good_player_frames_pct": 0.0,
            "estimated_ratio_pct": 0.0, "ball_coverage_pct": 0.0,
            "longest_ball_gap_s": 0.0,
            "warnings": ["Nincs feldolgozott képkocka — a videó/`--start` "
                         "beállítást ellenőrizd."],
        }
    fps = match.meta.fps if match.meta.fps > 0 else 25.0

    measured_total = 0
    estimated_total = 0
    good_frames = 0
    ball_frames = 0
    ball_filled = 0
    longest_gap = 0
    gap = 0
    from .ball_filter import INTERPOLATED_CONFIDENCE as _INTERP
    for f in match.frames:
        meas = sum(1 for p in f.players if p.source == PositionSource.MEASURED)
        est = len(f.players) - meas
        measured_total += meas
        estimated_total += est
        if meas >= GOOD_FRAME_MIN_PLAYERS:
            good_frames += 1
        if f.ball is not None:
            # A labda-lefedettség azt méri, milyen gyakran LÁTTUK a
            # labdát — a saját hézagpótlásunk nem számít bele. Egy
            # őszinteség-mutató nem hízhat a saját találgatásunkkal:
            # az interpolált pozíciókat épp azért jelöljük csökkentett
            # megbízhatósággal, hogy megkülönböztethetők legyenek.
            if f.ball.confidence > _INTERP:
                ball_frames += 1
            else:
                ball_filled += 1
            gap = 0
        else:
            gap += 1
            longest_gap = max(longest_gap, gap)

    avg_measured = measured_total / n
    good_pct = 100.0 * good_frames / n
    total_pos = measured_total + estimated_total
    est_ratio = 100.0 * estimated_total / total_pos if total_pos else 0.0
    ball_pct = 100.0 * ball_frames / n

    # Összpontszám: a játékos-lefedettség és a labda-lefedettség súlyozva.
    # (A becsült arány a játékos-részt rontja: a becslés hasznos, de nem mérés.)
    #
    # A TÖBBLET ugyanúgy hiba, mint a hiány. Korábban a lefedettséget
    # 1.0-ra vágtuk, tehát a 27 játékos/kocka (nézőtér a pályára vetítve)
    # TÖKÉLETES lefedettségnek számított, és a jelentés 70/100-at
    # mutatott egy használhatatlan feldolgozásra. Innentől a 14 fölötti
    # rész ugyanolyan meredeken ront, ahogy a hiány.
    if avg_measured <= EXPECTED_PLAYERS:
        coverage = avg_measured / EXPECTED_PLAYERS
    else:
        coverage = max(0.0,
                       1.0 - (avg_measured - EXPECTED_PLAYERS)
                       / EXPECTED_PLAYERS)
    player_score = coverage * (1.0 - est_ratio / 200.0)
    ball_score = ball_pct / 100.0
    score = round(100.0 * (0.6 * player_score + 0.4 * ball_score))
    # A lehetetlen létszám PLAFONT ad: jó labda-lefedettséggel se
    # mutathat "közepes" pontszámot egy olyan feldolgozás, amiben a
    # nézőtér is a pályán van.
    if avg_measured > TOO_MANY_PLAYERS:
        score = min(score, TOO_MANY_SCORE_CAP)

    warnings = []
    if avg_measured < GOOD_FRAME_MIN_PLAYERS:
        warnings.append(
            f"Kevés játékos látszik (átlag {avg_measured:.1f}/kocka) — ellenőrizd a "
            "kalibrációt (4 sarok) és hogy a kamera a játékteret mutatja-e.")
    if avg_measured > TOO_MANY_PLAYERS:
        warnings.append(
            f"TÚL sok játékos látszik (átlag {avg_measured:.1f}/kocka — a "
            f"pályán legfeljebb {EXPECTED_PLAYERS} lehet). A rendszer a "
            "nézőteret / kispadot is játékosnak méri, és emiatt a "
            "birtoklás, a fal-forma és MINDEN távolság-alapú elemzés "
            "félremegy. A leggyakoribb ok a pálya-kalibráció: a 4 "
            "sarokpont a JÁTÉKTÉR sarkait jelölje (ne a lelátót vagy a "
            "teljes képet), és ha a kezdőképen csak az egyik térfél "
            "látszik, a fél-pálya kalibrációt válaszd. Ellenőrzés: a "
            "kalibráló képen a rajzolt 6 m-es és 9 m-es vonalnak rá kell "
            "ülnie a valódi vonalakra.")
    if ball_pct < 30.0:
        warnings.append(
            f"Kevés labda-észlelés ({ball_pct:.0f}%) — a birtoklás/passz "
            "elemzés megbízhatatlan lehet. Széles, távoli felvételen a "
            "labda alig pár képpont: a \"Pontos\" minőségi profil "
            "(nagyobb felbontás) sokat javíthat rajta, és tisztább "
            "(közelebbi, élesebb) felvétel is segít.")
    if est_ratio > 40.0:
        warnings.append(
            f"Sok a becsült pozíció ({est_ratio:.0f}%) — a kamera sokat pásztáz; "
            "a becsültek szaggatott gyűrűvel jelennek meg a pályán.")
    if longest_gap / fps > 5.0:
        warnings.append(
            f"Hosszú labda-kiesés ({longest_gap / fps:.1f} mp) — az események egy "
            "része kimaradhat ebben a szakaszban.")

    # --- Követés-egészség: töredezettség, csapat-arány, mezszám-lefedettség ---
    track_meas: dict = {}       # track_id -> mért kockák száma
    team_meas = {"home": 0, "away": 0}
    tracks_with_jersey: set = set()
    for f in match.frames:
        for p in f.players:
            if p.source != PositionSource.MEASURED:
                continue
            track_meas[p.track_id] = track_meas.get(p.track_id, 0) + 1
            key = getattr(p.team, "value", p.team)
            if key in team_meas:
                team_meas[key] += 1
            if p.jersey_number is not None:
                tracks_with_jersey.add(p.track_id)

    track_count = len(track_meas)
    avg_track_s = (sum(track_meas.values()) / track_count / fps
                   if track_count else 0.0)
    # Töredezettség: hány track jut egy elvárt játékosra. Ideálisan ~1;
    # 3 fölött a követés sokat szakad (takarás, tömörülés, gyenge felvétel).
    fragmentation = track_count / EXPECTED_PLAYERS if track_count else 0.0
    if fragmentation > 3.0:
        warnings.append(
            f"A követés töredezett ({track_count} track ≈ "
            f"{fragmentation:.1f}x az elvárt játékosszám) — az automatikus "
            "track-összefűzés segít, a maradékot a mezszám-hozzárendeléssel "
            "kötheted össze a meccs-nézetben.")

    # --- Kalibráció-drift: a pályán kívülre vetülő mért pozíciók aránya ---
    from .calibration import COURT_LENGTH_M, COURT_WIDTH_M

    out_of_court = 0
    for f in match.frames:
        for p in f.players:
            if p.source != PositionSource.MEASURED:
                continue
            if (p.x < -OUT_OF_COURT_TOL_M
                    or p.x > COURT_LENGTH_M + OUT_OF_COURT_TOL_M
                    or p.y < -OUT_OF_COURT_TOL_M
                    or p.y > COURT_WIDTH_M + OUT_OF_COURT_TOL_M):
                out_of_court += 1
    measured_total = sum(track_meas.values())
    out_pct = (100.0 * out_of_court / measured_total
               if measured_total else 0.0)
    if out_pct >= OUT_OF_COURT_WARN_PCT:
        warnings.append(
            f"A mért pozíciók {out_pct:.0f}%-a a pályán KÍVÜLRE esik — a "
            "kalibráció valószínűleg elcsúszott (rossz sarokpont, vagy a "
            "kamera elmozdult a felvétel közben). Nyisd meg a "
            "Pálya-kalibrációt, és nézd meg, ráül-e a rajzolt 6 m-es ÉS "
            "9 m-es vonal a valódi vonalakra; ha nem, igazíts a "
            "sarokpontokon és futtasd újra.")

    total_team = team_meas["home"] + team_meas["away"]
    home_share = 100.0 * team_meas["home"] / total_team if total_team else 50.0
    if total_team and not (35.0 <= home_share <= 65.0):
        warnings.append(
            f"A csapat-besorolás egyoldalú (hazai arány: {home_share:.0f}%) — "
            "hasonló mezszíneknél előfordul; a meccs-nézet "
            "\"Csapatok felcserélése\" gombja és a mezszámok segítenek.")

    jersey_pct = (100.0 * len(tracks_with_jersey) / track_count
                  if track_count else 0.0)

    # --- Az új felismerők önellenőrzése: kapus, félidő, hétméteres ---
    duration_s = n / fps
    gk_teams: set = set()
    for f in match.frames:
        for p in f.players:
            if p.role == "kapus":
                gk_teams.add(getattr(p.team, "value", p.team))
    goalkeepers = {"home": "home" in gk_teams, "away": "away" in gk_teams}
    # Kapus-jelzés csak érdemi hosszúságú felvételen elvárás.
    if duration_s >= 120.0 and len(gk_teams) < 2:
        missing = [name for key, name in (("home", "hazai"), ("away", "vendég"))
                   if key not in gk_teams]
        warnings.append(
            f"Nem sikerült kapust azonosítani ({', '.join(missing)}) — a "
            "védés/kapus-statisztika hiányos lesz. Ellenőrizd a kalibrációt "
            "(a kapuelőtér a pályán belülre essen).")

    halftime_frame = None
    try:
        from .halftime import detect_halftime
        halftime_frame = detect_halftime(match)
    except Exception:
        pass
    # 40+ percnyi felvételben félidőnek lennie kell(ene).
    if duration_s >= 2400.0 and halftime_frame is None:
        warnings.append(
            "Hosszú felvétel félidő-jel nélkül — ha a videóban térfélcsere "
            "volt, a 2. félidő irány-érzékeny elemzései (támadás-irány, "
            "kapus-oldal) pontatlanok lehetnek.")

    # --- Hihető-e a labdaeladás-szám? ---
    # A felismerés az eladott labdához KITARTÁST vár (lásd
    # event_detection.TURNOVER_MIN_HOLD_S), tehát a kockánkénti billegés
    # már nem termel eladásokat. Ez a jelzés a HÁTSÓ VÉDVONAL: ha az
    # ütem így is hihetetlen, akkor vagy a labda-észlelés annyira
    # szakadozott, hogy a kitartást is zaj elégíti ki, vagy a
    # feldolgozott szakasz nem is meccs (bemelegítés, bemutatás).
    turnover_rate = None
    try:
        from .event_detection import EventType, detect_possession_changes
        perc = (n / fps / 60.0) if fps > 0 else 0.0
        if perc >= 1.0:
            eladas = sum(1 for e in detect_possession_changes(match)
                         if e.type == EventType.TURNOVER)
            # Csapatonként: a két oldal együtt adja a listát.
            turnover_rate = eladas / perc / 2.0
            if turnover_rate > TURNOVER_RATE_MAX_PER_MIN:
                warnings.append(
                    f"Gyanúsan sok eladott labda "
                    f"({turnover_rate:.1f}/perc/csapat) — valódi meccsen "
                    "ez fél-másfél szokott lenni. Két oka lehet: a "
                    "labda-észlelés annyira szakadozott, hogy a birtokos "
                    "hol az egyik, hol a másik csapatnál látszik "
                    "(ilyenkor a \"Pontos\" profil segít), vagy a "
                    "feldolgozott szakasz nem is meccs — bemelegítés, "
                    "csapatbemutatás (ilyenkor add meg a meccs "
                    "időablakát). Az eladás- és passz-alapú számokat "
                    "ezen a feldolgozáson ne vedd készpénznek.")
    except Exception:
        pass

    # --- Volt-e pálya-kalibráció? ---
    # Kalibráció nélkül a koordináta csak arányos becslés (a képet
    # nyújtjuk a pályára), és a pályán kívüli embereket — kispad, edző,
    # NÉZŐTÉR — nem lehet kiszűrni: mindenki "a pályán" lesz. Ez nem
    # apró pontatlanság, hanem az elemzés alapja, ezért ki kell mondani.
    # A None a RÉGI mentések állapota (a mező előttről): arról nem
    # állítunk semmit — csak a biztosan kalibráció nélküli futásról.
    calibrated = getattr(match.meta, "calibrated", None)
    if calibrated is False:
        warnings.append(
            "A feldolgozás pálya-kalibráció NÉLKÜL futott — a pozíciók "
            "csak arányos becslések (a kép széle a pálya széle), és a "
            "pályán kívüli embereket (kispad, edző, nézőtér) nem lehet "
            "kiszűrni: mindenki „a pályára” kerül. A távolság-, "
            "fal-forma- és birtoklás-alapú elemzések emiatt "
            "megbízhatatlanok. Az Új elemzés lapon jelöld be a 4 "
            "pályasarkot (a Sarkok javaslata gomb elő is tölti), és "
            "futtasd újra.")

    # --- A felvétel mekkora részét dolgoztuk fel? ---
    # "Az egész meccs helyett csak az első félidőt elemezte ki" — a
    # felhasználó ezt a számokból nem tudja kikövetkeztetni. A
    # feldolgozott szakasz a NYERS videó idejében: start_frame-től
    # ennyi ritkított kockán át.
    video_s = getattr(match.meta, "video_seconds", None)
    processed_pct = None
    # A feldolgozott szakasz KEZDETE és VÉGE a forrásvideó órája szerint.
    # A százalék önmagában nem elég: "60%" nem mondja meg, hogy az eleje
    # vagy a vége maradt ki. A felhasználó a videót perc:másodpercben
    # keresi vissza, tehát abban kell megmondani.
    processed_from_s = processed_to_s = None
    stride = max(1, int(match.meta.stride or 1))
    raw_fps = fps * stride
    if raw_fps > 0 and n > 0:
        processed_from_s = float(match.meta.start_frame or 0) / raw_fps
        processed_to_s = processed_from_s + n * stride / raw_fps
    if video_s and video_s > 0:
        processed_s = n * stride / raw_fps if raw_fps > 0 else 0.0
        processed_pct = 100.0 * processed_s / video_s
        if processed_pct < VIDEO_COVERAGE_WARN_PCT:
            _tol = clock_label(processed_from_s)
            _ig = clock_label(processed_to_s)
            warnings.append(
                f"A felvételnek csak a {processed_pct:.0f}%-át dolgoztuk "
                f"fel ({_tol}–{_ig} a "
                f"{clock_label(video_s)} hosszú videóból) — ha a TELJES meccset "
                "várnád, nézd meg a meccs-időablak mezőit és a "
                "hossz-beállítást (rövid próba / félidő / teljes videó); "
                "ha a feldolgozás megszakadt, a könyvtárban a "
                "Folytatás onnan viszi tovább, ahol abbamaradt.")

    # --- Megtaláltuk-e a MECCS tényleges kezdetét? ---
    # A felvételben rendszerint benne van a bemelegítés és a
    # csapatbemutatás. Ezeket a meccs-ablak felismerése levágja — de ha
    # NEM talált összefüggő játékot, akkor bennmaradtak, és a motor az
    # álldogálást is meccsnek látja (eladott labda, miközben a csapatok
    # csak állnak). A felhasználó ezt a számokból nem tudja kitalálni,
    # ezért ki kell mondani. A None a RÉGI mentések állapota — arról
    # nem állítunk semmit.
    gw_found = getattr(match.meta, "game_window_found", None)
    gw_head = getattr(match.meta, "game_trim_head_s", None)
    gw_tail = getattr(match.meta, "game_trim_tail_s", None)
    if gw_found is False:
        warnings.append(
            "A meccs tényleges kezdetét nem sikerült automatikusan "
            "megtalálni — a felismerés nem látott elég hosszú "
            "összefüggő játékot. Ha a felvételen bemelegítés vagy "
            "csapatbemutatás is van, az BENNMARADT az elemzésben: az "
            "álldogálást a motor eladott labdának, a bemelegítő kapura "
            "lövéseket lövésnek látja. Add meg a meccs időablakát "
            "(perc:másodperc) az Új elemzés lapon, és futtasd újra.")

    # --- Hihető-e a felismert EREDMÉNY? ---
    # Az edző az eredményből dönti el, hogy hisz-e a jelentésnek: ha az
    # állás nyilvánvalóan kevés, a többi szám sem ér semmit a szemében
    # — akkor sem, ha egyébként pontos. Mostantól javítható is, ezért a
    # figyelmeztetés nem zsákutca: megmondjuk, hol.
    goals = 0
    try:
        from .event_detection import EventType as _ET, detect_shots as _ds
        goals = sum(1 for e in _ds(match) if e.type is _ET.GOAL)
    except Exception:
        pass
    if duration_s / 60.0 >= GOALS_RATE_MIN_MINUTES:
        gol_perc = goals / (duration_s / 60.0)
        if gol_perc < GOALS_PER_MIN_LOW:
            warnings.append(
                f"Gyanúsan kevés gól ({goals} db {duration_s / 60:.0f} "
                f"perc alatt = {gol_perc:.2f} gól/perc) — kézilabdában a "
                "két csapat együtt percenként nagyjából egy gólt szerez, "
                "tehát a felismerés valószínűleg KIHAGYOTT gólokat "
                "(gyakran lövésként jelöli őket). Az Események listán a "
                "sorok ⋮ menüjében javítható: \"Ez GÓL volt\" — a "
                "javítás az egész elemzésen átüt (eredmény, xG, "
                "lövő-listák).")

    # --- Aránytalan-e az eredmény? ---
    # A két kapu felismerése külön-külön romolhat el (rossz kalibráció
    # az egyik térfélen, takarás, egyoldalú kameraállás). Ilyenkor a
    # végeredmény nem szoros vagy egyoldalú meccsről szól, hanem arról,
    # hogy az egyik oldalon nem látjuk a gólokat.
    try:
        from .event_detection import EventType as _ET2, detect_shots as _ds2
        _oldal = {"home": 0, "away": 0}
        for e in _ds2(match):
            if e.type is _ET2.GOAL:
                _oldal[getattr(e.team, "value", e.team)] += 1
        _ossz = _oldal["home"] + _oldal["away"]
        _kicsi = min(_oldal.values())
        _nagy = max(_oldal.values())
        if (_ossz >= GOALS_LOPSIDED_MIN_TOTAL
                and _nagy >= GOALS_LOPSIDED_FACTOR * max(1, _kicsi)):
            warnings.append(
                f"Aránytalan eredmény ({_oldal['home']}–{_oldal['away']}) "
                "— kézilabdában a nagy különbség is jellemzően kétszeres "
                "arány körül van. Ilyen eltérés inkább azt jelenti, hogy "
                "az EGYIK KAPU felismerése hibás: nézd meg, hogy a "
                "kalibráció mindkét térfélre ráül-e (a rajzolt 6 és 9 "
                "m-es vonalnak mindkét oldalon a valódin kell lennie), "
                "és hogy a felvétel nem takarja-e az egyik kaput.")
    except Exception:
        pass

    seven_meters = 0
    try:
        from .rules import detect_seven_meters
        seven_meters = len(detect_seven_meters(match))
    except Exception:
        pass
    # Aránytalanul sok "hétméteres" = álló labdás jelenetek (bemelegítés,
    # időkérés) kerültek a felvételre, vagy rossz a kalibráció.
    if duration_s > 0 and seven_meters / (duration_s / 60.0) > 0.8:
        warnings.append(
            f"Gyanúsan sok hétméteres-jel ({seven_meters} db) — valószínűleg "
            "álló labdás jelenetek (bemelegítés, időkérés) is a felvételen "
            "vannak; érdemes a meccs tényleges kezdetétől indítani a "
            "feldolgozást.")

    # ÖSSZEFŰZÖTT meccs eldöntetlen térfélcsere-határa: ha a szakaszok
    # közti fordulást kevés mért pozíció miatt nem lehetett eldönteni,
    # az eredmény ROSSZ IRÁNYÚ is lehet (a 2. félidő góljai a másik
    # csapathoz), és ezt semmi nem jelezné. Ez HIBA-gyanú, nem
    # tájékoztatás — a figyelmeztetések közé való.
    eldontetlen = [
        i for i, sz in enumerate(
            getattr(match.meta, "source_segments", None) or [])
        if isinstance(sz, dict) and sz.get("mirror_decided") is False]
    if eldontetlen:
        warnings.append(
            f"Az összefűzés {len(eldontetlen)} szakasz-határán nem volt "
            "eldönthető a térfélcsere (kevés mért pozíció a határ "
            "környékén) — ha a határ a félidei szünet volt, az "
            "eredmény és minden irány-alapú szám FORDÍTVA lehet a "
            "második félidőre. Ellenőrizd az eredményt; ha rossz, a "
            "könyvtárban a meccs sorának ⇄ gombjával fordítsd meg a "
            "gyanús szakaszt — az elemzés újraszámol.")

    # KLIP vagy MECCS: a rövid felvétel teljesen jogos bemenet, de a
    # meccs-szintű rétegek némán hallgatnak rajta — és a felhasználó
    # ezt HIBÁNAK látja ("megcsináltam, és a fele üres"). Egy mondat
    # elveszi ezt, és megnevezi, mi MŰKÖDIK.
    #
    # KÜLÖN MEZŐ, nem figyelmeztetés: ez nem probléma, hanem
    # tájékoztatás. A `warnings` a HIBÁKÉ — ha az információ is oda
    # kerülne, a "hibátlan feldolgozás = üres figyelmeztetés-lista"
    # szabály elveszne, és minden rövid próba gyanúsnak látszana.
    clip_note = None
    if 0 < duration_s < CLIP_LENGTH_S:
        clip_note = (
            f"Ez klip-hosszú felvétel ({duration_s / 60:.0f} perc, a "
            f"küszöb {CLIP_LENGTH_S / 60:.0f} perc) — nem hiba, csak "
            "tudni kell, mit vársz tőle. MŰKÖDIK: lövés és "
            "helyzetminőség, poszt- és felállás-kép, passz- és "
            "birtoklás-mutatók, klipvágás. NEM szólal meg: hajrá, "
            "félidő-összevetés, kondíció/fáradás, sorozatok — ezekhez "
            "teljes meccs kell. A réteg-megbízhatóság szakasz "
            "soronként is megmutatja, melyik mire épül.")

    return {
        # None, ha a felvétel meccs-hosszú — a mező LÉTEZIK mindig,
        # hogy a felület ne kulcs-hiányra fusson.
        "clip_note": clip_note,
        "frames": n,
        "score": score,
        "avg_measured_players": round(avg_measured, 1),
        "good_player_frames_pct": round(good_pct, 1),
        "estimated_ratio_pct": round(est_ratio, 1),
        "ball_coverage_pct": round(ball_pct, 1),
        # Amit nem láttunk, csak PÓTOLTUNK (rövid hézagok lineáris
        # kitöltése) — külön szám, hogy a lefedettség ne tűnjön jobbnak.
        "ball_filled_pct": round(100.0 * ball_filled / n, 1),
        "longest_ball_gap_s": round(longest_gap / fps, 1),
        "track_count": track_count,
        "avg_track_length_s": round(avg_track_s, 1),
        "fragmentation": round(fragmentation, 2),
        "home_share_pct": round(home_share, 1),
        "out_of_court_pct": round(out_pct, 1),
        "calibrated": calibrated,
        "game_window_found": gw_found,
        "game_trim_head_s": gw_head,
        "game_trim_tail_s": gw_tail,
        "turnover_rate_per_min": (round(turnover_rate, 2)
                                  if turnover_rate is not None else None),
        "video_seconds": round(video_s, 1) if video_s else None,
        "processed_pct": (round(processed_pct, 1)
                          if processed_pct is not None else None),
        # A feldolgozott szakasz a forrásvideó órája szerint (másodperc):
        # ebből mondja meg a kliens, hogy 0:00-tól 34:12-ig tart.
        "processed_from_s": (round(processed_from_s, 1)
                             if processed_from_s is not None else None),
        "processed_to_s": (round(processed_to_s, 1)
                           if processed_to_s is not None else None),
        "jersey_coverage_pct": round(jersey_pct, 1),
        "goalkeepers": goalkeepers,
        "halftime_frame": halftime_frame,
        "seven_meters": seven_meters,
        "warnings": warnings,
        # A legfontosabb EGY teendő: négy-hat figyelmeztetés mellett a
        # felhasználó egyébként nem tudja, mivel kezdje.
        "next_action": next_action(warnings),
    }


def analysis_confidence(match: Match) -> list[dict]:
    """Réteg-megbízhatóság: mely elemzési rétegeknek van elég mintája
    EZEN a meccsen — a kliens ebből tudja szürkíteni/megjelölni a kevés
    adatból számolt szekciókat.

    Minden réteghez: {"layer", "label", "available", "reason"} — a
    reason magyarul mondja el, mi hiányzik (vagy hogy rendben van).
    A küszöbök a rétegek saját minimum-követelményeinek tükrei.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    dur_s = len(match.frames) / fps if match.frames else 0.0

    shots = goals = 0
    for e in detect_shots(match, config):
        if e.type == EventType.GOAL:
            goals += 1
        elif e.type == EventType.SHOT:
            shots += 1
    attempts = shots + goals

    gk_marked = any(p.role == "kapus" for f in match.frames
                    for p in f.players)
    half_t = None
    try:
        from .halftime import detect_halftime
        half_t = detect_halftime(match)
    except Exception:
        pass

    n_positions = 0
    try:
        from .roles import estimate_positions
        est_q = estimate_positions(match, config)
        n_positions = sum(len(v) for v in est_q.values())
    except Exception:
        pass

    n_field = n_jersey = 0
    seen_tracks: set = set()
    for f in match.frames:
        for p in f.players:
            if p.track_id in seen_tracks or p.role == "kapus":
                continue
            seen_tracks.add(p.track_id)
            n_field += 1
            if p.jersey_number is not None:
                n_jersey += 1
    jersey_cov = (100.0 * n_jersey / n_field) if n_field else 0.0

    # Labda-lefedettség (a labda-alapú rétegek közös alapja).
    n_frames = len(match.frames)
    # Csak a MÉRT labda számít (a hézagpótlás a saját találgatásunk).
    from .ball_filter import INTERPOLATED_CONFIDENCE as _INTERP2
    ball_frames = sum(1 for f in match.frames
                      if f.ball is not None
                      and f.ball.confidence > _INTERP2)
    ball_pct = (100.0 * ball_frames / n_frames) if n_frames else 0.0

    # Pálya-vetítés épsége: lehetetlen létszám VAGY hiányzó kalibráció.
    measured = sum(1 for f in match.frames for p in f.players
                   if p.source == PositionSource.MEASURED)
    avg_meas = (measured / n_frames) if n_frames else 0.0
    calibrated = getattr(match.meta, "calibrated", None)
    if calibrated is False:
        court_ok = False
        court_ok_reason = ""
        court_fail_reason = ("nincs pálya-kalibráció — a pozíciók csak "
                             "arányos becslések, és a pályán kívüliek "
                             "nem szűrhetők")
    elif avg_meas > TOO_MANY_PLAYERS:
        court_ok = False
        court_ok_reason = ""
        court_fail_reason = (f"lehetetlen létszám ({avg_meas:.1f}/kocka, "
                             f"a pályán legfeljebb {EXPECTED_PLAYERS}) — a "
                             "kalibráció a pályán kívülieket is beveszi")
    else:
        court_ok = True
        court_ok_reason = f"hihető létszám ({avg_meas:.1f}/kocka)"
        court_fail_reason = ""

    def row(layer, label, ok, ok_reason, fail_reason):
        return {"layer": layer, "label": label, "available": bool(ok),
                "reason": ok_reason if ok else fail_reason}

    return [
        row("xg", "Helyzetminőség (xG)", attempts >= 4,
            f"{attempts} lövés-minta",
            f"kevés lövés ({attempts} < 4) — az xG-kép nem megbízható"),
        row("goalkeeper", "Kapus-teljesítmény", gk_marked,
            "van kapus-jelölés",
            "nincs kapus-jelölés — jelöld meg a kapusokat"),
        row("halftime", "Félidő-alapú rétegek", half_t is not None,
            "a félidei szünet felismerhető",
            "a szünet nem ismerhető fel — félidei állás/minta nincs"),
        row("clutch", "Hajrá-elemzés", dur_s >= 600.0,
            f"{dur_s / 60:.0f} perces felvétel",
            "10 percnél rövidebb felvétel — hajrá nem értelmezhető"),
        row("momentum", "Sorozatok / válasz-idő", goals >= 4,
            f"{goals} felismert gól",
            f"kevés gól ({goals} < 4) — a momentum-kép hiányos"),
        row("conditioning", "Kondíció / fáradás", dur_s >= 300.0,
            f"{dur_s / 60:.0f} perces felvétel",
            "5 percnél rövidebb felvétel — tempó-trend nem mérhető"),
        row("jerseys", "Mezszám-alapú rétegek (játékos-lap, trend)",
            jersey_cov >= 50.0,
            f"{jersey_cov:.0f}% mezszám-lefedettség",
            f"kevés mezszám ({jersey_cov:.0f}% < 50%) — rendelj "
            "számokat a játékosokhoz a meccs-nézetben"),
        row("positions", "Poszt-becslés", n_positions >= 6,
            f"{n_positions} játékos posztja becsülhető",
            f"kevés poszt-minta ({n_positions} < 6 játékos) — a "
            "felállás-kép hiányos"),
        # A labda a birtoklás, a passz, az eladott labda és a lövés
        # KÖZÖS alapja: ha ritkán látjuk, ezek a számok együtt gyengék.
        # A felhasználó ezt eddig sehol nem látta rétegre bontva —
        # ugyanolyan magabiztosan olvasta őket, mint a pozíció-alapúakat.
        row("ball", "Labda-alapú rétegek (birtoklás, passz, eladás, lövés)",
            ball_pct >= BALL_CONFIDENCE_PCT,
            f"{ball_pct:.0f}% labda-lefedettség",
            f"kevés labda-észlelés ({ball_pct:.0f}% < "
            f"{BALL_CONFIDENCE_PCT:.0f}%) — a birtoklás, a passz- és az "
            "eladás-számok nem megbízhatók; a \"Pontos\" profil javíthat"),
        # A pálya-vetítés minden TÁVOLSÁG-alapú réteg alapja. Ha a
        # nézőtér is a pályára esik (vagy nincs kalibráció), ezek a
        # számok mást mérnek, mint amit mondanak.
        row("court", "Pálya-alapú rétegek (távolság, fal-forma, zónák)",
            court_ok, court_ok_reason, court_fail_reason),
    ]
