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

# A felvétel LEFEDETTSÉGE: a feldolgozott szakasz ekkora aránya alatt
# szólunk, hogy a videónak csak egy részét elemeztük. Egy meccs-videó
# elején-végén van holt idő, és a kézi meccs-ablak is vág — a jelzés
# nem hiba, hanem tájékoztatás: aki azt hiszi, a teljes meccset
# elemezte, ne a számokból jöjjön rá, hogy nem.
VIDEO_COVERAGE_WARN_PCT = 60.0

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
    longest_gap = 0
    gap = 0
    for f in match.frames:
        meas = sum(1 for p in f.players if p.source == PositionSource.MEASURED)
        est = len(f.players) - meas
        measured_total += meas
        estimated_total += est
        if meas >= GOOD_FRAME_MIN_PLAYERS:
            good_frames += 1
        if f.ball is not None:
            ball_frames += 1
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
            f"Kevés labda-észlelés ({ball_pct:.0f}%) — a birtoklás/passz elemzés "
            "megbízhatatlan lehet. Tisztább (közelebbi, élesebb) felvétel segít.")
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
    if video_s and video_s > 0:
        stride = max(1, int(match.meta.stride or 1))
        raw_fps = fps * stride
        processed_s = n * stride / raw_fps if raw_fps > 0 else 0.0
        processed_pct = 100.0 * processed_s / video_s
        if processed_pct < VIDEO_COVERAGE_WARN_PCT:
            warnings.append(
                f"A felvételnek csak a {processed_pct:.0f}%-át dolgoztuk "
                f"fel ({processed_s / 60.0:.0f} perc a "
                f"{video_s / 60.0:.0f} percből) — ha a TELJES meccset "
                "várnád, nézd meg a meccs-időablak mezőit és a "
                "hossz-beállítást (rövid próba / félidő / teljes videó); "
                "ha a feldolgozás megszakadt, a könyvtárban a "
                "Folytatás onnan viszi tovább, ahol abbamaradt.")

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

    return {
        "frames": n,
        "score": score,
        "avg_measured_players": round(avg_measured, 1),
        "good_player_frames_pct": round(good_pct, 1),
        "estimated_ratio_pct": round(est_ratio, 1),
        "ball_coverage_pct": round(ball_pct, 1),
        "longest_ball_gap_s": round(longest_gap / fps, 1),
        "track_count": track_count,
        "avg_track_length_s": round(avg_track_s, 1),
        "fragmentation": round(fragmentation, 2),
        "home_share_pct": round(home_share, 1),
        "out_of_court_pct": round(out_pct, 1),
        "calibrated": calibrated,
        "video_seconds": round(video_s, 1) if video_s else None,
        "processed_pct": (round(processed_pct, 1)
                          if processed_pct is not None else None),
        "jersey_coverage_pct": round(jersey_pct, 1),
        "goalkeepers": goalkeepers,
        "halftime_frame": halftime_frame,
        "seven_meters": seven_meters,
        "warnings": warnings,
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
    ]
