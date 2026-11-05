"""
[5. fázis] Figura-szimuláció — az edző figurája egy TANULT ellenfél ellen.

A vízió "edző kipróbálja a kitalált figuráit egy adott csapat ellen" része:
1. DefenseModel.learn(...) — egy ellenfél meccséből megtanuljuk a védekezési
   stílusát (hány védő, milyen mélyen áll a saját kaputól, mennyire követi a labdát).
2. SetPlay — az edző által megtervezett figura: a támadók útvonala lépésenként +
   ki birtokolja a labdát.
3. simulate_setplay(...) — lejátssza a figurát: a támadók a terv szerint mozognak,
   a védők a TANULT modell szerint reagálnak. Kimenet egy Match (Tracking), amit a
   kliens ugyanúgy ki tud rajzolni, mint egy valódi meccset.
4. evaluate_setplay(...) — pontozza a figurát: teremtett-e szabad, közeli
   lövőhelyzetet (a legjobb várható gól * "szabadság" a védőktől).

Tiszta Python, videó nélkül tesztelhető. A védekezési modell egyszerű, de VALÓDI
adatból tanult paraméterekre épül — később finomabb (tanult) modellre cserélhető.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field, replace

from ..models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import TacticsConfig, classify_phase, Phase


# A 6 m-es kapuelőtér geometriája: a fal SOHA nem léphet a hatoson
# belülre — alapból fél méterrel a hatos íve előtt áll (6-0 fal).
GOAL_AREA_RADIUS_M = 6.0
GOAL_AREA_MARGIN_M = 0.5
_GOAL_HALF_W = 1.5  # kapufák: y = 8,5 és 11,5

# A fal VÉDEKEZÉSI RENDSZEREI: az előretolt védők — (mélység m-ben a saját
# kaputól, y-eltolás a pálya közepétől, mennyire követik a labda y-ját).
# A többi védő a hatos előtti vonalban (a 6-0 geometriája). A mélységek a
# forma-felismerés sávjaiba esnek (tactics.detect_formation: hátsó ≤ 7 m,
# közép ≤ 10,5 m, előretolt e fölött) — a szimulált fal ugyanazt a
# címkét kapja, mint a valódi. A sorrend a fontosság: kevés védőnél az
# első előretoltak maradnak (legalább egy védő a vonalban áll).
VEDEKEZESI_RENDSZEREK = {
    "6-0": (),
    "5-1": ((9.5, 0.0, 0.8),),
    "4-2": ((9.0, -3.5, 0.6), (9.0, 3.5, 0.6)),
    "3-2-1": ((8.5, -4.5, 0.6), (8.5, 4.5, 0.6), (11.0, 0.0, 0.8)),
    "3-3": ((9.0, -5.5, 0.6), (9.5, 0.0, 0.7), (9.0, 5.5, 0.6)),
}
# Az előretolt védő legalább ennyivel a vonal előtt áll (a kitolt
# vonalnál az előretoltak is kijjebb kerülnek).
ELORETOLT_MIN_ELONY_M = 1.5

# Kilépési hajlam: a labdás a saját kaputól ennyi méteren belül van
# (lőtávolság), és a legközelebbi mezőnyvédő ennyin belül van tőle —
# akkor "ráléptek". Ennyi ilyen labdás kocka kell a tanuláshoz (minta-
# szám: ritkítva is ennyi minta). A szimulációban a kilépő védő a labdás
# és a kapu-közép vonalán ennyire áll meg a labdás előtt.
PRESS_RANGE_M = 11.0
PRESS_CLOSE_M = 2.0
PRESS_LEARN_MIN_FRAMES = 50
PRESS_GAP_M = 1.0

# Labdakövetés: a hátsó sor közepe (a védők y-átlaga) mennyit mozdul a
# labda oldal-mozgásával — a kettő (pálya-középtől mért) eltérésének
# origón átmenő regressziója. Ennyi védekező kocka kell hozzá (minta-
# szám), és a labdának átlagosan (négyzetes középpel) legalább ennyi
# méterre kell a pálya hossztengelyétől oldalt lennie: középen álló
# labdából az eltolódás nem tanulható, ilyenkor az alapérték marad.
LATERAL_LEARN_MIN_FRAMES = 50
LATERAL_MIN_SPREAD_M = 2.0

# Védőnkénti kilépés (a játékos-modell a falban): egy védő SAJÁT
# kilépési hajlamához ennyi olyan kocka kell, ahol ő állt legközelebb a
# lőtávolságon belüli labdáshoz (mintaszám); a falba az a mezszám kerül,
# aki a védekező kockák legalább ekkora részén a pályán volt (a csere
# nem).
VEDO_PRESS_MIN = 15
VEDO_JELEN_ARANY = 0.3

# Kettőzési hajlam: a lőtávolságon belüli labdás kockák közül azok, ahol
# a labdáshoz legalább KÉT mezőnyvédő áll legfeljebb DOUBLE_CLOSE_M-re (a
# defense.double_teams küszöbe) — a tanuláshoz ugyanannyi minta kell,
# mint a kilépéshez. A szimulációban a második legközelebbi védő a saját
# helyéről a labdás felé lép, és ennyire áll meg tőle.
DOUBLE_CLOSE_M = 2.5
DOUBLE_GAP_M = 1.2

# Tanult kapus: a kaputra érkező lövések gól-aránya lövő-távolság szerint
# (a gk_save_ranges sávjai), a kézilabdában szokásos arány felé húzva —
# KAPUS_SULY "képzelt" lövés az alap aránnyal, mert egy meccs sávonként
# kevés lövést ad. A sáv szorzója a tanult és az alap gól-arány
# hányadosa, ebbe a sávba szorítva; a sávhoz legalább KAPUS_MIN_LOVES
# kaputra érkező lövés kell (alatta nincs szorzó — nem találgatunk).
KAPUS_ALAP_GOL = {"close": 0.70, "mid": 0.55, "far": 0.40}
KAPUS_SULY = 6
KAPUS_MIN_LOVES = 3
KAPUS_SZORZO_MIN = 0.7
KAPUS_SZORZO_MAX = 1.3
# A sávok a felületek mondataiban ("távolról 1,2× annyi gólt kap").
KAPUS_SAV_NEV = {"close": "közelről", "mid": "közepes távolságból",
                 "far": "távolról"}

# Tanult lövők — a játékos-modell a TÁMADÁSBAN: mezszámonként és
# lövőhely-sávonként (kapus_sav) a szerzett gól és a helyzetei xG-jének
# hányadosa — 1 felett a helyzeteinél TÖBBET lő be (jobb befejező az
# átlagnál), 1 alatt kevesebbet. LOVO_SULY képzelt, pontosan a várt
# értékű lövéssel simítva (egy meccs sávonként kevés lövést ad), ebbe a
# sávba szorítva; a sávhoz legalább LOVO_MIN_LOVES látott lövés kell
# (alatta nincs szorzó — nem találgatunk). A figura-értékelés a helyzetbe
# érő támadó (a mezszáma) sávjának szorzójával számol — ugyanaz a figura
# a biztos kezű lövővel a végén többet ér.
LOVO_SULY = 6
LOVO_MIN_LOVES = 3
LOVO_SZORZO_MIN = 0.7
LOVO_SZORZO_MAX = 1.3
# A feliratokban és a mondatokban ennél kisebb eltérés az 1-től nem hír,
# és legfeljebb ennyi lövőt nevezünk meg.
LOVO_FELIRAT_ELTERES = 0.1
LOVO_FELIRAT_MAX = 3
# Ennél kisebb sáv-szorzó a lövő GYENGE sávja — a játékos-edzésterv
# befejezés-tétele (a sávhoz legalább LOVO_MIN_LOVES lövés kell).
LOVO_GYENGE_SZORZO = 0.85
# Ennél nagyobb sáv-szorzó a kapus GYENGE sávja (az átlagnál ennyiszer
# több gólt kap onnan) — a játékos-edzésterv kapus-tétele (a sávhoz
# legalább KAPUS_MIN_LOVES kaputra tartó lövés kell).
KAPUS_GYENGE_SZORZO = 1.15


def kapus_sav(x: float, y: float, goal_x: float) -> str:
    """A lövőhely távolság-sávja a kaputól (a gk_save_ranges-é: közeli
    SHOT_RANGE_CLOSE_M-ig, közép SHOT_RANGE_MID_M-ig, utána távoli)."""
    from .attack_types import SHOT_RANGE_CLOSE_M, SHOT_RANGE_MID_M
    d = math.hypot(x - goal_x, y - COURT_WIDTH_M / 2.0)
    if d <= SHOT_RANGE_CLOSE_M:
        return "close"
    return "mid" if d <= SHOT_RANGE_MID_M else "far"


# ---- Tanult védekezési modell ---------------------------------------------

@dataclass
class DefenseModel:
    """Egy csapat védekezési stílusa, meccsadatból tanult paraméterekkel.

    - num_defenders: hány mezőnyvédő áll a vonalban (kapus nélkül).
    - line_depth_m:  a védővonal átlagos mélysége a SAJÁT kaputól (méter).
    - lateral_gain:  mennyire követi a védelem a labda y-helyzetét (0..1):
                     a labda oldal-mozgásának ekkora részével tolódik el
                     a fal (0 = helyben áll, 1 = teljesen a labdával megy).
    - rendszer:      a védekezési rendszer (VEDEKEZESI_RENDSZEREK kulcsa:
                     "6-0", "5-1", "4-2", "3-2-1", "3-3").
    - press_rate:    kilépési hajlam (0..1): a lőtávolságon belüli labdás
                     kockák mekkora részén lépett rá a legközelebbi védő
                     (PRESS_CLOSE_M-en belül). A szimulációban ennyire
                     lép ki a labdáshoz legközelebbi védő; 0 = zárt fal.
    - double_rate:   kettőzési hajlam (0..1): a lőtávolságon belüli labdás
                     kockák mekkora részén állt KÉT védő is a labdáshoz
                     DOUBLE_CLOSE_M-en belül. A szimulációban ennyire lép
                     a második legközelebbi védő is a labdásra.
    - kapus:         a tanult kapus sávonkénti szorzója ({"close" / "mid"
                     / "far": szorzó}): 1 felett az a sáv ellene többet ér
                     (többet enged be a szokásosnál), 1 alatt kevesebbet.
                     A figura-értékelés a lövőhely sávjának szorzójával
                     számol; üres = átlagos kapus.
    - vedok:         a fal védői mezszám szerint, a vonalbeli helyük (y)
                     sorrendjében: [{"mez", "y", "press_rate" (a SAJÁT
                     kilépési hajlama, vagy None, ha kevés a minta),
                     "kozel", "double_rate" (a saját kettőzési hajlama:
                     amikor ő a második legközelebbi, rálép-e), "masodik"}].
                     A szimulációban a labdáshoz legközelebbi vonal-védő a
                     saját hajlamával lép ki, a második legközelebbi a
                     saját kettőzésével (ha ismert), különben a csapatéval
                     — a játékos-modell a falban.
    """
    num_defenders: int = 6
    line_depth_m: float = 6.0
    lateral_gain: float = 0.5
    rendszer: str = "6-0"
    press_rate: float = 0.0
    double_rate: float = 0.0
    kapus: dict = field(default_factory=dict)
    vedok: list = field(default_factory=list)

    @classmethod
    def learn(cls, match: Match, defending_team: Team,
              config: TacticsConfig | None = None) -> "DefenseModel":
        """Megtanulja a védekezési stílust azokból a frame-ekből, ahol a csapat véd.

        A csapat akkor véd, amikor az ellenfél támad. Ezeken a frame-eken a
        mezőnyvédők (kapus nélkül) átlagos mélységét és átlagos számát becsüljük,
        és a felismert formák (tactics.detect_formation) közül a
        VEDEKEZESI_RENDSZEREK-ben szereplő leggyakoribbat — nem 6-0
        rendszernél a vonal mélysége a HÁTSÓ sor védőiből (az előretoltak
        nélkül), különben az összesből. A kilépési hajlam: a lőtávolságon
        (PRESS_RANGE_M) belüli labdás kockák közül azok aránya, ahol a
        labdáshoz legközelebbi mezőnyvédő PRESS_CLOSE_M-en belül állt —
        PRESS_LEARN_MIN_FRAMES alatt 0 (zárt fal, nem találgatunk). A
        labdakövetés: a hátsó sor y-átlagának és a labda y-jának
        (pálya-középtől mért) eltérése közti arány, origón átmenő
        regresszióval, 0..1-be szorítva — LATERAL_LEARN_MIN_FRAMES
        alatt, vagy ha a labda (négyzetes közép) oldal-eltérése
        LATERAL_MIN_SPREAD_M alatti, az alapérték (0,5) marad. A kettőzési
        hajlam a kilépéséhez hasonlóan: a lőtávolságon belüli labdás kockák
        közül azok aránya, ahol két mezőnyvédő is DOUBLE_CLOSE_M-en belül
        állt. A kapus: a csapat kapusára kaputra érkező lövések sávonkénti
        gól-aránya (goalkeeper.gk_save_ranges), KAPUS_SULY képzelt
        alap-lövéssel simítva, a KAPUS_ALAP_GOL-hoz mérve.

        A tanulás két lépés: a MINTA (_tanulas_minta — nyers összegek és
        darabszámok) és a modell a mintából (_modell_mintabol); a
        `learn_many` több meccs mintáját összeadva tanul.
        """
        config = config or TacticsConfig()
        return cls._modell_mintabol(
            _tanulas_minta(match, defending_team, config))

    @classmethod
    def learn_many(cls, meccsek: list,
                   config: TacticsConfig | None = None) -> "DefenseModel":
        """A csapat fala TÖBB meccséből: `meccsek` = [(match, a csapat
        oldala azon a meccsen), …]. A minták összeadódnak (kocka- és
        lövés-számok), így a hosszabb meccs súlya nagyobb, és a kevés-
        minta küszöbök (kilépés, labdakövetés, kapus) a teljes szezonra
        vonatkoznak — egy meccs kevés lövéséből a kapus sávjai alig
        tanulhatók, hatból igen. Üres listára az alap fal."""
        config = config or TacticsConfig()
        mintak = [_tanulas_minta(m, t, config) for m, t in meccsek]
        if not mintak:
            return cls()
        return cls._modell_mintabol(_mintak_osszege(mintak))

    @classmethod
    def _modell_mintabol(cls, m: dict) -> "DefenseModel":
        """A modell a (összeadott) mintából — a küszöbök itt dőlnek el."""
        kovetes = 0.5
        if m["kov_n"] >= LATERAL_LEARN_MIN_FRAMES \
                and m["kov_bb"] / m["kov_n"] >= LATERAL_MIN_SPREAD_M ** 2:
            kovetes = round(max(0.0, min(1.0, m["kov_bw"] / m["kov_bb"])), 3)
        # A leggyakoribb (holtversenyben a címke szerint — determinisztikus).
        formak = m["formak"]
        rendszer = (max(formak.items(), key=lambda kv: (kv[1], kv[0]))[0]
                    if formak else "6-0")
        melyseg = (m["hatso_osszeg"] / m["hatso_n"]
                   if rendszer != "6-0" and m["hatso_n"]
                   else m["melyseg_osszeg"] / m["melyseg_n"]
                   if m["melyseg_n"] else 6.0)
        lovo = m["lovo_kockak"]
        vedok = _vedok_mintabol(m.get("vedok", {}), m["kockak"])
        return cls(
            num_defenders=(round(m["vedo_osszeg"] / m["kockak"])
                           if m["kockak"] else 6),
            line_depth_m=melyseg,
            lateral_gain=kovetes,
            rendszer=rendszer,
            press_rate=(round(m["raleptek"] / lovo, 3)
                        if lovo >= PRESS_LEARN_MIN_FRAMES else 0.0),
            double_rate=(round(m["kettoztek"] / lovo, 3)
                         if lovo >= PRESS_LEARN_MIN_FRAMES else 0.0),
            kapus=_kapus_szorzo(m["kapus"]),
            vedok=vedok,
        )

    def vonal_vedok(self) -> int:
        """Hány védő áll a vonalban (az előretoltak nélkül) — a
        `respond` kimenetének első ennyi eleme a vonal, y szerint."""
        n_osszes = max(1, self.num_defenders)
        return n_osszes - len(VEDEKEZESI_RENDSZEREK.get(self.rendszer, ())
                               [:n_osszes - 1])

    def vedo_kilepes(self, slot: int) -> float:
        """A `slot`. vonal-védő kilépési hajlama: a sajátja (a tanult
        védő, aki ott áll), ha ismert, különben a csapaté."""
        if slot < self.vonal_vedok() and slot < len(self.vedok):
            r = self.vedok[slot].get("press_rate")
            if r is not None:
                return float(r)
        return self.press_rate

    def kilepo_vedo(self):
        """A fal leggyakrabban kilépő védője ({"mez", "press_rate"}) —
        None, ha egyik védő hajlama sem ismert vagy mind 0."""
        ismert = [v for v in self.vedok if v.get("press_rate")]
        if not ismert:
            return None
        return max(ismert, key=lambda v: (v["press_rate"], -v["mez"]))

    def vedo_kettozes(self, slot: int) -> float:
        """A `slot`. vonal-védő kettőzési hajlama (mint vedo_kilepes)."""
        if slot < self.vonal_vedok() and slot < len(self.vedok):
            r = self.vedok[slot].get("double_rate")
            if r is not None:
                return float(r)
        return self.double_rate

    def kettozo_vedo(self):
        """A fal leggyakrabban kettőző védője ({"mez", "double_rate"}) —
        None, ha nincs ismert, 0 feletti hajlam."""
        ismert = [v for v in self.vedok if v.get("double_rate")]
        if not ismert:
            return None
        return max(ismert, key=lambda v: (v["double_rate"], -v["mez"]))

    def kapus_szorzo(self, x: float, y: float, goal_x: float) -> float:
        """A lövőhely sávjának tanult kapus-szorzója (1, ha nincs)."""
        return float(self.kapus.get(kapus_sav(x, y, goal_x), 1.0))

    def respond(self, ball: Ball, goal_x: float) -> list[tuple[float, float]]:
        """A védők pozíciói a labdára reagálva (y-ban a labda felé eltolva).

        A fal a 6 m-es kapuelőtér ívét követi KÍVÜLRŐL (6-0 fal): egy
        védő sem léphet a hatoson belülre. A `line_depth_m` a fal
        frontális mélysége — a hatoshoz képest tolja kijjebb az egész
        falat (alapból fél méterrel a hatos előtt), a széleken a fal a
        hatos ívére simul. A `rendszer` előretolt védői
        (VEDEKEZESI_RENDSZEREK) a vonal ELŐTT állnak — legalább
        ELORETOLT_MIN_ELONY_M-rel —, és a labdát a saját mértékükben
        követik; a kimenetben a vonal után jönnek.
        """
        sign = -1.0 if goal_x == COURT_LENGTH_M else 1.0

        n_osszes = max(1, self.num_defenders)
        elol = VEDEKEZESI_RENDSZEREK.get(self.rendszer, ())[:n_osszes - 1]
        n = n_osszes - len(elol)
        # Egyenletes y-eloszlás a [3, 17] sávban.
        if n == 1:
            base_ys = [COURT_WIDTH_M / 2.0]
        else:
            lo, hi = 3.0, COURT_WIDTH_M - 3.0
            base_ys = [lo + (hi - lo) * i / (n - 1) for i in range(n)]

        shift = self.lateral_gain * (ball.y - COURT_WIDTH_M / 2.0)
        offset = max(GOAL_AREA_MARGIN_M,
                     self.line_depth_m - GOAL_AREA_RADIUS_M
                     + GOAL_AREA_MARGIN_M)
        out = []
        for by in base_ys:
            y = max(1.0, min(COURT_WIDTH_M - 1.0, by + shift))
            # A hatos határa ennél az y-nál: a közelebbi kapufától 6 m.
            lateral = max(0.0, abs(y - COURT_WIDTH_M / 2.0) - _GOAL_HALF_W)
            boundary = (math.sqrt(GOAL_AREA_RADIUS_M ** 2 - lateral ** 2)
                        if lateral < GOAL_AREA_RADIUS_M else 0.0)
            out.append((goal_x + sign * (boundary + offset), y))
        # Az előretoltak: a rendszer mélységén (a kitolt vonal előtt
        # legalább ELORETOLT_MIN_ELONY_M-rel), a labda felé lépve.
        eleje = GOAL_AREA_RADIUS_M + offset
        for melyseg, dy, kovet in elol:
            y = max(1.0, min(COURT_WIDTH_M - 1.0, COURT_WIDTH_M / 2.0 + dy
                             + kovet * (ball.y - COURT_WIDTH_M / 2.0)))
            out.append((goal_x + sign * max(melyseg,
                                            eleje + ELORETOLT_MIN_ELONY_M), y))
        return self._kilepes(out, ball, goal_x, sign)

    def _kilepes(self, out: list[tuple[float, float]], ball: Ball,
                 goal_x: float, sign: float) -> list[tuple[float, float]]:
        """A kilépési hajlam: lőtávolságon belüli labdánál a labdáshoz
        legközelebbi védő `press_rate` arányban a labdás elé lép (a labda
        és a kapu-közép vonalán, PRESS_GAP_M-re); a kettőzési hajlam: a
        második legközelebbi `double_rate` arányban a saját helyéről a
        labdás felé, DOUBLE_GAP_M-re tőle — a hatoson belülre egyik sem."""
        if not out or abs(ball.x - goal_x) > PRESS_RANGE_M:
            return out
        sorrend = sorted(range(len(out)), key=lambda k: (
            math.hypot(out[k][0] - ball.x, out[k][1] - ball.y), k))
        # A legközelebbi vonal-védő a SAJÁT hajlamával (a játékos-modell),
        # a második a saját kettőzésével.
        kilep = self.vedo_kilepes(sorrend[0])
        kettoz = (self.vedo_kettozes(sorrend[1]) if len(sorrend) >= 2
                  else 0.0)
        if kilep <= 0.0 and kettoz <= 0.0:
            return out

        def lep(hely, cel, r):
            nx = hely[0] + (cel[0] - hely[0]) * r
            ny = hely[1] + (cel[1] - hely[1]) * r
            lateral = max(0.0, abs(ny - COURT_WIDTH_M / 2.0) - _GOAL_HALF_W)
            boundary = (math.sqrt(GOAL_AREA_RADIUS_M ** 2 - lateral ** 2)
                        if lateral < GOAL_AREA_RADIUS_M else 0.0)
            if abs(nx - goal_x) < boundary + GOAL_AREA_MARGIN_M:
                nx = goal_x + sign * (boundary + GOAL_AREA_MARGIN_M)
            return nx, ny

        out = list(out)
        if kilep > 0.0:
            i = sorrend[0]
            dx, dy = goal_x - ball.x, COURT_WIDTH_M / 2.0 - ball.y
            d = math.hypot(dx, dy) or 1.0
            cel = (ball.x + dx / d * PRESS_GAP_M, ball.y + dy / d * PRESS_GAP_M)
            out[i] = lep(out[i], cel, min(1.0, kilep))
        if kettoz > 0.0 and len(sorrend) >= 2:
            j = sorrend[1]
            dx, dy = out[j][0] - ball.x, out[j][1] - ball.y
            d = math.hypot(dx, dy)
            if d > DOUBLE_GAP_M:
                cel = (ball.x + dx / d * DOUBLE_GAP_M,
                       ball.y + dy / d * DOUBLE_GAP_M)
                out[j] = lep(out[j], cel, min(1.0, kettoz))
        return out


def mezszam_nevelovel(mez: int) -> str:
    """A mezszám névelővel és a magyar sorszám-raggal ("a 6-os", "az
    5-ös", "a 3-as", "a 10-es", "a 20-as") — a mondatokba."""
    n = int(mez)
    utolso, tizes = n % 10, (n // 10) % 10
    if n and utolso == 0:
        rag = {1: "es", 2: "as", 3: "as", 4: "es", 5: "es", 6: "as",
               7: "es", 8: "as", 9: "es"}.get(tizes, "as")
    else:
        rag = {1: "es", 2: "es", 3: "as", 4: "es", 5: "ös", 6: "os",
               7: "es", 8: "as", 9: "es", 0: "ás"}[utolso]
    nevelo = "az" if n in (1, 5) or 50 <= n <= 59 else "a"
    return f"{nevelo} {n}-{rag}"


def _tanulas_minta(match: Match, defending_team: Team,
                   config: TacticsConfig) -> dict:
    """A védekezés-tanulás NYERS mintája egy meccsről (lásd
    DefenseModel.learn): összegek és darabszámok, amelyek meccsek közt
    összeadhatók — {"kockak" (védekező kockák mezőnyvédővel),
    "vedo_osszeg", "melyseg_osszeg", "melyseg_n", "hatso_osszeg",
    "hatso_n", "formak" (címke → kocka), "lovo_kockak", "raleptek",
    "kettoztek", "kov_n", "kov_bw", "kov_bb", "kapus" (sáv → [kaputra
    érkezett, védett])}."""
    from .decisions import ball_holder
    from .tactics import _BACK_MAX, detect_formation
    goal_x = config.own_goal_x(defending_team)
    m = {"kockak": 0, "vedo_osszeg": 0, "melyseg_osszeg": 0.0,
         "melyseg_n": 0, "hatso_osszeg": 0.0, "hatso_n": 0, "formak": {},
         "lovo_kockak": 0, "raleptek": 0, "kettoztek": 0,
         "kov_n": 0, "kov_bw": 0.0, "kov_bb": 0.0,
         "kapus": _kapus_minta(match, defending_team, config),
         "vedok": {}}
    kozep_y = COURT_WIDTH_M / 2.0
    for f in match.frames:
        ph = classify_phase(f, config)
        defends = ((defending_team == Team.AWAY and ph == Phase.HOME_ATTACK) or
                   (defending_team == Team.HOME and ph == Phase.AWAY_ATTACK))
        if not defends:
            continue
        outfield = [p for p in f.players
                    if p.team == defending_team and abs(p.x - goal_x) > 2.0]
        if not outfield:
            continue
        m["kockak"] += 1
        m["vedo_osszeg"] += len(outfield)
        hatso = [abs(p.x - goal_x) for p in outfield
                 if abs(p.x - goal_x) <= _BACK_MAX]
        m["melyseg_osszeg"] += sum(abs(p.x - goal_x) for p in outfield)
        m["melyseg_n"] += len(outfield)
        m["hatso_osszeg"] += sum(hatso)
        m["hatso_n"] += len(hatso)
        cimke = detect_formation(f, defending_team, config).label
        if cimke in VEDEKEZESI_RENDSZEREK:
            m["formak"][cimke] = m["formak"].get(cimke, 0) + 1
        holder = ball_holder(f, config)
        kozel = None
        if holder is not None and holder.team != defending_team \
                and abs(holder.x - goal_x) <= PRESS_RANGE_M:
            m["lovo_kockak"] += 1
            tav = sorted(math.hypot(p.x - holder.x, p.y - holder.y)
                         for p in outfield)
            if tav[0] <= PRESS_CLOSE_M:
                m["raleptek"] += 1
            if len(tav) >= 2 and tav[1] <= DOUBLE_CLOSE_M:
                m["kettoztek"] += 1
            sorban = sorted(outfield, key=lambda p: (
                math.hypot(p.x - holder.x, p.y - holder.y), p.track_id))
            kozel = sorban[0]
            masodik = sorban[1] if len(sorban) >= 2 else None
        else:
            masodik = None
        # Védőnként (mezszám szerint): hol áll, ő lép-e ki, amikor ő a
        # legközelebbi a labdáshoz, és ő kettőz-e, amikor ő a második.
        for p in outfield:
            if p.jersey_number is None:
                continue
            v = m["vedok"].setdefault(int(p.jersey_number), {
                "n": 0, "y_osszeg": 0.0, "kozel": 0, "ralepett": 0,
                "masodik": 0, "kettozott": 0})
            v["n"] += 1
            v["y_osszeg"] += p.y
            if kozel is not None and p is kozel:
                v["kozel"] += 1
                if math.hypot(p.x - holder.x, p.y - holder.y) <= PRESS_CLOSE_M:
                    v["ralepett"] += 1
            if masodik is not None and p is masodik:
                v["masodik"] += 1
                if math.hypot(p.x - holder.x, p.y - holder.y) <= DOUBLE_CLOSE_M:
                    v["kettozott"] += 1
        sor = [p.y for p in outfield if abs(p.x - goal_x) <= _BACK_MAX]
        if sor and f.ball is not None:
            b = f.ball.y - kozep_y
            m["kov_n"] += 1
            m["kov_bw"] += b * (statistics.fmean(sor) - kozep_y)
            m["kov_bb"] += b * b
    return m


def _vedok_mintabol(vedok_minta: dict, kockak: int) -> list:
    """A fal védői a (összeadott) védőnkénti mintából (lásd
    DefenseModel.vedok): aki a védekező kockák legalább VEDO_JELEN_ARANY
    részén (és PRESS_LEARN_MIN_FRAMES kockán) a falban állt, a tanult
    helyével (y) és a saját kilépési / kettőzési hajlamával (legalább
    VEDO_PRESS_MIN alkalomból, különben None); y szerint rendezve. A
    felderítés az összegzett mintából is ezt hívja."""
    vedok = []
    for mez, v in vedok_minta.items():
        if v["n"] < max(PRESS_LEARN_MIN_FRAMES, VEDO_JELEN_ARANY * kockak):
            continue
        vedok.append({
            "mez": int(mez), "y": round(v["y_osszeg"] / v["n"], 2),
            "press_rate": (round(v["ralepett"] / v["kozel"], 3)
                           if v["kozel"] >= VEDO_PRESS_MIN else None),
            "kozel": v["kozel"],
            "double_rate": (round(v["kettozott"] / v["masodik"], 3)
                            if v["masodik"] >= VEDO_PRESS_MIN else None),
            "masodik": v["masodik"]})
    vedok.sort(key=lambda r: (r["y"], r["mez"]))
    return vedok


def _mintak_osszege(mintak: list) -> dict:
    """Több meccs mintájának összege (minden mező összeadódik)."""
    ossz = {"kockak": 0, "vedo_osszeg": 0, "melyseg_osszeg": 0.0,
            "melyseg_n": 0, "hatso_osszeg": 0.0, "hatso_n": 0, "formak": {},
            "lovo_kockak": 0, "raleptek": 0, "kettoztek": 0,
            "kov_n": 0, "kov_bw": 0.0, "kov_bb": 0.0, "kapus": {},
            "vedok": {}}
    for m in mintak:
        for k, v in m.items():
            if k == "vedok":
                for mez, r in v.items():
                    o = ossz["vedok"].setdefault(mez, {
                        "n": 0, "y_osszeg": 0.0, "kozel": 0, "ralepett": 0,
                        "masodik": 0, "kettozott": 0})
                    for kk in o:
                        o[kk] += r[kk]
            elif k == "formak":
                for c, n in v.items():
                    ossz["formak"][c] = ossz["formak"].get(c, 0) + n
            elif k == "kapus":
                for sav, (faced, saves) in v.items():
                    r = ossz["kapus"].setdefault(sav, [0, 0])
                    r[0] += faced
                    r[1] += saves
            else:
                ossz[k] += v
    return ossz


def _kapus_minta(match: Match, defending_team: Team,
                 config: TacticsConfig) -> dict:
    """A kapus nyers mintája: sáv → [kaputra érkezett lövés, védés]
    (goalkeeper.gk_save_ranges) — csak a nem üres sávok."""
    from .goalkeeper import gk_save_ranges
    rng = gk_save_ranges(match, config).get(defending_team.value) or {}
    out = {}
    for sav in KAPUS_ALAP_GOL:
        rec = rng.get(sav) or {}
        faced = int(rec.get("faced") or 0)
        if faced:
            out[sav] = [faced, int(rec.get("saves") or 0)]
    return out


def _kapus_szorzo(minta: dict) -> dict:
    """A kapus sávonkénti szorzója a (összeadott) mintából (lásd
    DefenseModel.kapus) — KAPUS_MIN_LOVES alatti sáv kimarad."""
    out = {}
    for sav, alap in KAPUS_ALAP_GOL.items():
        faced, saves = minta.get(sav) or (0, 0)
        if faced < KAPUS_MIN_LOVES:
            continue
        arany = (faced - saves + KAPUS_SULY * alap) / (faced + KAPUS_SULY)
        out[sav] = round(max(KAPUS_SZORZO_MIN,
                             min(KAPUS_SZORZO_MAX, arany / alap)), 3)
    return out


def _kapus_tanul(match: Match, defending_team: Team,
                 config: TacticsConfig) -> dict:
    """A `defending_team` kapusának sávonkénti szorzója egy meccsből."""
    return _kapus_szorzo(_kapus_minta(match, defending_team, config))


def kapus_felirat(kapus: dict) -> str:
    """A tanult kapus egy sorban ("a kapus távolról 1,2×, közelről 0,8×
    annyi gólt kap, mint az átlag") — csak a 0,1-nél jobban eltérő sávok;
    üres, ha nincs ilyen."""
    reszek = []
    for sav in ("far", "mid", "close"):
        v = kapus.get(sav)
        if v is None or abs(v - 1.0) < 0.1:
            continue
        reszek.append(f"{KAPUS_SAV_NEV[sav]} "
                      + f"{v:.1f}".replace(".", ",") + "×")
    return ("a kapus " + ", ".join(reszek)
            + " annyi gólt kap, mint az átlag") if reszek else ""


# ---- Tanult támadás-modell: a lövők ----------------------------------------

@dataclass
class AttackModel:
    """Egy csapat lövői, meccsadatból tanult szorzókkal — a játékos-modell
    a TÁMADÁSBAN (a DefenseModel párja).

    - lovok: {mezszám: {"close" / "mid" / "far": szorzó}} — a lövő
      sávonkénti szorzója: 1 felett a helyzeteinél többet lő be, 1 alatt
      kevesebbet (lásd LOVO_SULY). A figura-értékelés (evaluate_setplay)
      a helyzetbe érő támadó sávjának szorzójával számol, ha a figura
      támadóihoz mezszám tartozik (a meccsből vett figura "mez" sora, a
      mentett figura "mez" mezője); üres / ismeretlen mezszám = átlagos
      lövő.
    """
    lovok: dict = field(default_factory=dict)

    @classmethod
    def learn(cls, match: Match, attacking_team: Team,
              config: TacticsConfig | None = None) -> "AttackModel":
        """A csapat lövői egy meccs látott lövéseiből (xg.match_xg): a
        lövő mezszáma az elengedés kockájáról, a sáv a lövőhelyé."""
        config = config or TacticsConfig()
        return cls._modell_mintabol(_lovo_minta(match, attacking_team, config))

    @classmethod
    def learn_many(cls, meccsek: list,
                   config: TacticsConfig | None = None) -> "AttackModel":
        """TÖBB meccsből: `meccsek` = [(match, a csapat oldala), …] — a
        lövések mezszámonként és sávonként összeadódnak, így a küszöb
        (LOVO_MIN_LOVES) a szezonra vonatkozik: egy meccs kevés lövéséből
        a lövő sávjai alig tanulhatók, hatból igen. Üres listára üres
        modell."""
        config = config or TacticsConfig()
        return cls._modell_mintabol(_lovo_mintak_osszege(
            [_lovo_minta(m, t, config) for m, t in meccsek]))

    @classmethod
    def _modell_mintabol(cls, m: dict) -> "AttackModel":
        """A modell a (összeadott) mintából — a küszöb itt dől el."""
        return cls(lovok=_lovo_szorzo(m))

    def lovo_szorzo(self, mez, x: float, y: float, goal_x: float) -> float:
        """A `mez` mezszámú lövő szorzója a lövőhely sávjában (1, ha
        nincs tanult lövő vagy sáv)."""
        if mez is None:
            return 1.0
        try:
            savok = self.lovok.get(int(mez)) or {}
        except (TypeError, ValueError):
            return 1.0
        return float(savok.get(kapus_sav(x, y, goal_x), 1.0))

    def figura_lovok(self, mezek) -> list:
        """A figura támadóinak sávonkénti szorzói a `mezek` (támadónként a
        mezszám vagy None) sorból — az evaluate_setplay `lovok` bemenete;
        üres lista, ha egyikük sem tanult lövő."""
        ki = []
        for mez in list(mezek or []):
            try:
                ki.append(dict(self.lovok.get(int(mez)) or {}))
            except (TypeError, ValueError):
                ki.append({})
        return ki if any(ki) else []

    def kiemelt(self) -> list:
        """A figyelemre méltó lövők: [{"mez", "sav", "szorzo"}, …] — az
        1-től legalább LOVO_FELIRAT_ELTERES-sel eltérő sávok, az eltérés
        szerint csökkenőben (holtversenyben mezszám, sáv), legfeljebb
        LOVO_FELIRAT_MAX."""
        sorok = [{"mez": mez, "sav": sav, "szorzo": v}
                 for mez, savok in self.lovok.items()
                 for sav, v in savok.items()
                 if abs(v - 1.0) >= LOVO_FELIRAT_ELTERES]
        sorok.sort(key=lambda r: (-abs(r["szorzo"] - 1.0), r["mez"], r["sav"]))
        return sorok[:LOVO_FELIRAT_MAX]


def _lovesek_mezszammal(match: Match, attacking_team: Team,
                        config: TacticsConfig):
    """A csapat látott lövései (xg.match_xg; a nem látott, középkezdésből
    következtetett gól nincs köztük) a lövő mezszámával — (mezszám,
    lövés-sor) párok; a mezszám az elengedés (release_t) vagy az esemény
    kockájáról, mezszám nélküli lövő kimarad."""
    from .xg import match_xg
    by_t = {f.t: f for f in match.frames}
    for sh in match_xg(match, config)["shots"]:
        pid = sh.get("player_id")
        if sh["team"] != attacking_team.value or pid is None:
            continue
        mez = None
        for t in (sh.get("release_t"), sh["t"]):
            f = by_t.get(t)
            if f is None:
                continue
            mez = next((int(p.jersey_number) for p in f.players
                        if p.track_id == pid and p.jersey_number is not None),
                       None)
            if mez is not None:
                break
        if mez is not None:
            yield mez, sh


def _lovo_minta(match: Match, attacking_team: Team,
                config: TacticsConfig) -> dict:
    """A lövők NYERS mintája egy meccsről: {mezszám: {sáv: [lövés, gól,
    xG-összeg]}} — a csapat mezszámos lövései (_lovesek_mezszammal), a
    sáv a lövőhelyé (kapus_sav). Meccsek közt összeadható."""
    goal_x = config.attacks_toward_x(attacking_team)
    out: dict = {}
    for mez, sh in _lovesek_mezszammal(match, attacking_team, config):
        r = out.setdefault(mez, {}).setdefault(
            kapus_sav(sh["x"], sh["y"], goal_x), [0, 0, 0.0])
        r[0] += 1
        r[1] += 1 if sh["outcome"] == "goal" else 0
        r[2] += float(sh["xg"])
    return out


def _lovo_mintak_osszege(mintak: list) -> dict:
    """Több meccs lövő-mintájának összege (mezszám és sáv szerint) — a
    mezszám-kulcs egész számra igazítva (a lemezes eredmény-tárból jövő,
    JSON-körbejárt minta szöveg-kulcsa és az élő minta egész kulcsa egy
    lövőt jelent)."""
    ossz: dict = {}
    for m in mintak:
        for mez, savok in m.items():
            for sav, (n, gol, xg) in savok.items():
                r = ossz.setdefault(int(mez), {}).setdefault(sav, [0, 0, 0.0])
                r[0] += n
                r[1] += gol
                r[2] += xg
    return ossz


def _lovo_szorzo(minta: dict) -> dict:
    """A lövők sávonkénti szorzója a (összeadott) mintából (lásd
    AttackModel.lovok): a gól és az xG hányadosa, LOVO_SULY képzelt, a
    sáv átlagos értékű lövésével simítva, a LOVO_SZORZO sávba szorítva;
    LOVO_MIN_LOVES alatti sáv kimarad (a lövő is, ha egy sávja sem
    marad)."""
    out: dict = {}
    for mez, savok in minta.items():
        for sav, (n, gol, xg) in savok.items():
            if n < LOVO_MIN_LOVES or xg <= 0:
                continue
            atlag = xg / n
            arany = (gol + LOVO_SULY * atlag) / (xg + LOVO_SULY * atlag)
            out.setdefault(int(mez), {})[sav] = round(
                max(LOVO_SZORZO_MIN, min(LOVO_SZORZO_MAX, arany)), 3)
    return out


def lovo_felirat(tamadas) -> str:
    """A tanult lövők egy sorban ("a lövők: a 7-es távolról 1,3×, a 10-es
    közelről 0,8× annyit lőnek be, mint amennyit a helyzeteik érnek") —
    csak az 1-től LOVO_FELIRAT_ELTERES-sel eltérő sávok
    (AttackModel.kiemelt); üres, ha nincs ilyen (vagy nincs modell)."""
    if tamadas is None:
        return ""
    reszek = [f"{mezszam_nevelovel(r['mez'])} {KAPUS_SAV_NEV[r['sav']]} "
              + f"{r['szorzo']:.1f}".replace(".", ",") + "×"
              for r in tamadas.kiemelt()]
    if not reszek:
        return ""
    return "a lövők: " + ", ".join(reszek) + (
        " annyit lő be, mint amennyit a helyzetei érnek" if len(reszek) == 1
        else " annyit lőnek be, mint amennyit a helyzeteik érnek")


def lovo_zaradek(sor: dict, elo: str = ", a végén ") -> str:
    """A figura-sor (setplay_3d_match / rank_playbook / defense_test
    kimenete) lövő-záradéka a mondatokba: "<elo>a 9-es lövésével, aki
    innen 1,3× annyit lő be, mint amennyit a helyzet ér" — üres, ha a
    sorhoz nincs tanult lövő, vagy a szorzója LOVO_FELIRAT_ELTERES-nél
    kevésbé tér el az 1-től."""
    mez = sor.get("lovo_mez")
    sz = sor.get("lovo_szorzo")
    if mez is None or sz is None or abs(float(sz) - 1.0) < LOVO_FELIRAT_ELTERES:
        return ""
    return (f"{elo}{mezszam_nevelovel(mez)} lövésével, aki innen "
            + f"{float(sz):.1f}".replace(".", ",")
            + "× annyit lő be, mint amennyit a helyzet ér")


# ---- Utolsó lövés: kire és honnan -----------------------------------------
# A hajrá-döntés modellje: a csapat tanult lövői (AttackModel) × az
# ELLENFÉL kapusának tanult sávjai (DefenseModel.kapus) — melyik lövőnk
# melyik sávból ér a legtöbbet ellenük. A sáv képviselő-helye a kapu
# előtt, középen, ennyi méterre (a sávhatárok — SHOT_RANGE_CLOSE_M = 7,
# SHOT_RANGE_MID_M = 9,5 — közé eső tipikus lövőhely); az érték az xG a
# képviselő-helyen × a lövő-szorzó × a kapus-szorzó. A jelöltek csak a
# TANULT lövő-sávok (ahol minta van); egy sem → None, a modell nem
# találgat. A "kerülendő" a leggyengébb jelölt, ha az ajánlottnál
# legalább UTOLSO_LOVES_ELTERES várható góllal kevesebbet ér.
UTOLSO_LOVES_TAV_M = {"close": 6.5, "mid": 8.5, "far": 10.0}
UTOLSO_LOVES_ELTERES = 0.08
# A sáv jelzőként a mondatokba ("a 7-es távoli lövését").
UTOLSO_LOVES_SAV_JELZO = {"close": "közeli", "mid": "közepes távolságú",
                          "far": "távoli"}


def _lovo_parosok(tamadas, kapus: dict | None = None) -> list:
    """A tanult lövő × sáv párosok értéke ELLENÜK: `tamadas` (AttackModel),
    `kapus` (a SZEMKÖZTI kapus sávonkénti szorzója; üres = átlagos kapus)
    — [{"mez", "sav", "sav_nev", "tav_m", "xg", "lovo_szorzo",
    "kapus_szorzo", "ertek"}, …] az érték szerint csökkenőben
    (holtversenyben mezszám, sáv); érték = xG a sáv képviselő-helyén
    (UTOLSO_LOVES_TAV_M) × lövő-szorzó × kapus-szorzó. Az utolsó lövés
    (last_shot_choice) és a lövés-elosztás (shot_allocation_from) közös
    alapja; üres, ha nincs tanult lövő-sáv."""
    from .xg import xg_of_position
    kapus = kapus or {}
    jeloltek = []
    for mez, savok in (tamadas.lovok if tamadas is not None else {}).items():
        for sav, lsz in savok.items():
            tav = UTOLSO_LOVES_TAV_M.get(sav)
            if tav is None:
                continue
            xg = xg_of_position(COURT_LENGTH_M - tav, COURT_WIDTH_M / 2.0,
                                COURT_LENGTH_M)
            ksz = float(kapus.get(sav, 1.0))
            jeloltek.append({
                "mez": int(mez), "sav": sav, "sav_nev": KAPUS_SAV_NEV[sav],
                "tav_m": tav, "xg": xg, "lovo_szorzo": float(lsz),
                "kapus_szorzo": ksz,
                "ertek": round(xg * float(lsz) * ksz, 3)})
    jeloltek.sort(key=lambda r: (-r["ertek"], r["mez"], r["sav"]))
    return jeloltek


def last_shot_choice(tamadas, kapus: dict | None = None) -> dict | None:
    """Az utolsó lövés a kész modellekből: `tamadas` (AttackModel — a
    lövők), `kapus` (a SZEMKÖZTI kapus sávonkénti szorzója,
    DefenseModel.kapus; üres = átlagos kapus). Minden tanult lövő × sáv
    párosra: érték = xG a sáv képviselő-helyén × lövő-szorzó × kapus-
    szorzó; a legjobb az "utolsó labda".

    Edzőileg: a hajrában, egyenlő állásnál az utolsó támadást nem a
    szokás, hanem a számok szerint kell megjátszani — kinek a kezében és
    honnan ér a legtöbbet a lövés ELLENÜK (az ő kapusukkal), és kit nem
    szabad lövőhelyzetbe hozni.

    Visszaad: {"mez", "sav", "sav_nev", "tav_m", "xg", "lovo_szorzo",
    "kapus_szorzo", "ertek", "jeloltek" (hány páros), "kerulendo"
    ({"mez", "sav", "sav_nev", "ertek"} vagy None), "verdict"} — None,
    ha nincs tanult lövő-sáv (kevés minta)."""
    jeloltek = _lovo_parosok(tamadas, kapus)
    if not jeloltek:
        return None
    b = dict(jeloltek[0])
    rossz = jeloltek[-1]
    kerul = None
    if (rossz["mez"], rossz["sav"]) != (b["mez"], b["sav"]) \
            and b["ertek"] - rossz["ertek"] >= UTOLSO_LOVES_ELTERES:
        kerul = {k: rossz[k] for k in ("mez", "sav", "sav_nev", "ertek")}

    def szam(v, d=2):
        return f"{v:.{d}f}".replace(".", ",")

    reszek = []
    if abs(b["lovo_szorzo"] - 1.0) >= LOVO_FELIRAT_ELTERES:
        reszek.append(f"ő innen {szam(b['lovo_szorzo'], 1)}× annyit lő be, "
                      "mint amennyit a helyzet ér")
    if abs(b["kapus_szorzo"] - 1.0) >= LOVO_FELIRAT_ELTERES:
        reszek.append(f"a kapusuk {b['sav_nev']} {szam(b['kapus_szorzo'], 1)}× "
                      "annyit kap, mint az átlag")
    verdict = (f"{mezszam_nevelovel(b['mez'])}é {b['sav_nev']} "
               f"({b['tav_m']:.0f} m): {szam(b['ertek'])} várható gól")
    if reszek:
        verdict += " — " + ", ".join(reszek)
    if kerul:
        verdict += (f"; ne {mezszam_nevelovel(kerul['mez'])}é "
                    f"{kerul['sav_nev']} ({szam(kerul['ertek'])})")
    b["jeloltek"] = len(jeloltek)
    b["kerulendo"] = kerul
    b["verdict"] = verdict
    return b


def last_shot_pick(match: Match, config: TacticsConfig | None = None) -> dict:
    """Utolsó lövés: kire és honnan — csapatonként ({"home": …, "away":
    …}): last_shot_choice a csapat ebből a meccsből tanult lövőivel
    (AttackModel.learn) és a SZEMKÖZTI kapus ebből a meccsből tanult
    sávjaival (_kapus_tanul). None, ha a csapatnak nincs tanult lövő-
    sávja (kevés minta — a modell nem találgat)."""
    config = config or TacticsConfig()
    out = {}
    for side, team, masik in (("home", Team.HOME, Team.AWAY),
                              ("away", Team.AWAY, Team.HOME)):
        out[side] = last_shot_choice(AttackModel.learn(match, team, config),
                                     _kapus_tanul(match, masik, config))
    return out


# ---- A figura (set play) és a szimuláció ----------------------------------

@dataclass
class SetPlay:
    """Az edző által tervezett figura.

    - attackers:    [támadó][lépés] = (x, y) — minden támadó útvonala lépésenként.
                    Minden támadó listája azonos hosszú (a lépések száma).
    - ball_carrier: lépésenként melyik támadó (index) birtokolja a labdát.
    """
    attackers: list[list[tuple[float, float]]]
    ball_carrier: list[int]

    @property
    def steps(self) -> int:
        return len(self.ball_carrier)


def simulate_setplay(setplay: SetPlay, defense: DefenseModel,
                     config: TacticsConfig | None = None,
                     fps: float = 25.0,
                     ball_positions: list | None = None) -> Match:
    """Lejátssza a figurát a tanult védelem ellen, és Match-et (Tracking) ad.

    A HAZAI a támadó (a +x kapu felé), a VENDÉG véd (saját kapuja x=40). A
    kimenet ugyanolyan Tracking, mint egy valódi meccs — a kliens kirajzolhatja.
    `ball_positions` (opcionális): lépésenként a labda helye (x, y) — a
    passz repülése; nélküle a labda a `ball_carrier` támadónál.
    """
    config = config or TacticsConfig()
    away_goal_x = config.own_goal_x(Team.AWAY)
    meta = MatchMeta(match_id="setplay-sim", home_team="Terv (támadó)",
                     away_team="Tanult védelem", fps=fps, frame_width=1920, frame_height=1080)
    frames: list[Frame] = []

    for step in range(setplay.steps):
        players: list[PlayerPosition] = []
        for ai, path in enumerate(setplay.attackers):
            x, y = path[step]
            players.append(PlayerPosition(track_id=ai + 1, team=Team.HOME, x=x, y=y,
                                          source=PositionSource.MEASURED, confidence=1.0,
                                          jersey_number=ai + 1))
        if ball_positions is not None:
            bx, by = ball_positions[step]
        else:
            carrier = setplay.ball_carrier[step]
            bx, by = setplay.attackers[carrier][step]
        ball = Ball(x=bx, y=by, confidence=1.0)
        for di, (dx, dy) in enumerate(defense.respond(ball, away_goal_x)):
            players.append(PlayerPosition(track_id=100 + di, team=Team.AWAY, x=dx, y=dy,
                                          source=PositionSource.MEASURED, confidence=1.0))
        frames.append(Frame(t=step, players=players, ball=ball))

    return Match(meta=meta, frames=frames)


# ---- A figura 3D-ben (böngésző / VR) ----------------------------------------
# A tervező 40 lépéses animációja 1,6 mp — a képernyőn áttekintésnek jó,
# a headsetben villanás. 3D-ben valós tempóban megy: a kulcs-pozíciók
# közti szakaszok egyforma ideig tartanak (mint a tervezőben — a
# játékosok EGYSZERRE érnek a "Közép" pontra), és a leggyorsabb szakasz
# is legfeljebb ekkora futótempó.
FIGURA_3D_TEMPO_MPS = 3.5
# A mozgás hossza ebbe a sávba szorítva (mp): a rövid figura se legyen
# villanás, a hosszú se vánszorogjon.
FIGURA_3D_MIN_S = 3.0
FIGURA_3D_MAX_S = 12.0
# Az elején és a végén ennyi mp állókép: a felállás és a végső helyzet
# látszik, mielőtt a mozgás indul / miután megállt.
FIGURA_3D_ALLAS_S = 1.5
# A beágyazott adat képrátája (a böngésző interpolál — mint a meccsnél).
FIGURA_3D_FPS = 6.0
# Bemeneti korlátok (a link a böngészőből jön).
FIGURA_3D_MAX_JATEKOS = 7
FIGURA_3D_MAX_PONT = 10
# A figura neve (a 3D fejléce, a /kovet sora) legfeljebb ennyi jel. A
# védelem neve hosszabb lehet: a tanult falé a csapatnév mellett a
# rendszert, a kilépést, a labdakövetést és a kettőzést is viszi.
FIGURA_3D_NEV_MAX = 60
FIGURA_3D_VEDO_NEV_MAX = 140


def figura_nev(s, hossz: int = FIGURA_3D_NEV_MAX) -> str:
    """A figura neve megtisztítva: a látható jelek (vezérlőjel nélkül),
    két szélén szóköz nélkül, legfeljebb `hossz` (alapból
    FIGURA_3D_NEV_MAX); üres, ha nincs. (A követő nevének tisztítója
    rövidebbre vág — az egy fej fölé fér.)"""
    s = "".join(ch for ch in str(s or "") if ch.isprintable()).strip()
    return s[:hossz].strip()
# A figura passza ennyi m/s-mal száll (a valódinál lassabb — a
# headsetben követhető), és legalább ennyi mp; a következő kulcs-pozícióra
# érkezik (ott már az átvevőnél van).
FIGURA_3D_PASSZ_MPS = 12.0
FIGURA_3D_PASSZ_MIN_S = 0.3
# A figura KÖZÖS NÉZÉSÉNEK azonosítója a meccsek helyén
# (/matches/figura/shared3d): az edző a figurát is vezetheti, a csapat a
# /kovet linkkel ugyanarra a figurára áll.
FIGURA_KOZOS_ID = "figura"
# A vezető által küldött figura-paraméterek (a /figura3d lekérdezése)
# legfeljebb ennyi jel.
FIGURA_KOZOS_MAX = 2000
# A csapat várólapja (/kovet) az edző legutóbbi 3D-figuráját ennyi mp-ig
# linkeli (egy edzés hossza — utána már nem "a mostani").
FIGURA_3D_KOVET_S = 3 * 3600
# A várólap ennyi mentett figurát kínál (a legutóbb mentetteket).
FIGURA_TAR_KOVET = 8
# A 3D figura védője legfeljebb ennyi m/s-mal lép a modell-helye felé
# (oldalazó csúsztatás — a passz 12 m/s-a ennél gyorsabb: a gyors
# labdajáratás rést nyit, mint a valóságban). A mozgás végére, az
# állóképben a fal beáll.
FIGURA_VEDO_MAX_MPS = 4.5
# Ha a késő fal a mozgás végére az állóképben sem áll be (széles
# keresztpassz a végén), az állókép legfeljebb ennyi mp-cel nyúlik.
FIGURA_3D_BEALL_MAX_S = 3.0


def _hatoson_kivulre(x: float, y: float, goal_x: float) -> tuple[float, float]:
    """A pont a 6 m-es kapuelőtéren KÍVÜLRE tolva (a közelebbi kapufától
    — a kapufák közt a gólvonaltól — sugárirányban); kívül maradó pont
    változatlan."""
    kozep = COURT_WIDTH_M / 2.0
    fa_y = min(kozep + _GOAL_HALF_W, max(kozep - _GOAL_HALF_W, y))
    dx, dy = x - goal_x, y - fa_y
    d = math.hypot(dx, dy)
    if d >= GOAL_AREA_RADIUS_M or d < 1e-9:
        return x, y
    k = GOAL_AREA_RADIUS_M / d
    return goal_x + dx * k, fa_y + dy * k


# A figura kapusának mezszáma; a védők ezután sorban (a fal balról
# jobbra, utána az előretoltak) — a szem=v1 a kapus, a szem=v2 … a védők
# szemével nyit.
FIGURA_KAPUS_MEZ = 1


def figura_link_kod(attackers, labda=None, nev=None) -> str:
    """Egy (mentett) figura a /figura3d link-paramétereire — mint a
    tervező "3D / VR ↗" gombja: `u` (támadónként "x,y,x,y,…" méterben,
    tizedre; a támadók ";"-vel), `l` (a labdás-sor, ha nem végig az 1.
    támadónál van), `cim` (a név, megtisztítva). A védelem a /figura3d
    kézi alap-fala (a mentett figura nem viszi). ValueError a hibás
    koordinátánál."""
    from urllib.parse import urlencode
    # (a 3D határain belül; a nem véges pontot kihagyjuk — a /figura3d is)
    utak = []
    regi_uj: dict[int, int] = {}
    for i, ut in enumerate(list(attackers)[:FIGURA_3D_MAX_JATEKOS]):
        pontok = [(float(x), float(y)) for x, y in list(ut)[:FIGURA_3D_MAX_PONT]]
        pontok = [(x, y) for x, y in pontok
                  if math.isfinite(x) and math.isfinite(y)]
        if pontok:
            regi_uj[i] = len(utak)
            utak.append(pontok)
    if not utak:
        raise ValueError("a figurában nincs érvényes pont")
    q = {"u": ";".join(",".join(f"{x:.1f},{y:.1f}" for x, y in ut)
                       for ut in utak)}
    # (a kiesett támadó után a labdás-sor átszámozva; a kiesettre mutató
    # elem az előzőé)
    sor: list[int] = []
    for v in (labda or []):
        uj = regi_uj.get(int(v))
        sor.append(uj if uj is not None else (sor[-1] if sor else 0))
    if any(v != 0 for v in sor):
        q["l"] = ",".join(str(v) for v in sor)
    cim = figura_nev(nev)
    if cim:
        q["cim"] = cim
    return urlencode(q, safe=",;")


def setplay_3d_match(keypoints: list, defense: DefenseModel, *,
                     ball: list | None = None,
                     name: str | None = None,
                     defense_name: str | None = None,
                     config: TacticsConfig | None = None,
                     tamadas: "AttackModel | None" = None,
                     mezek: list | None = None) -> tuple[Match, dict]:
    """A tervező figurája 3D-re (böngésző / VR): valós tempóban, kapussal.

    `keypoints`: támadónként a kulcs-pozíciók ([(x, y), …] — a tervező
    Kezdő / Közép / Vég pontjai, méterben). `ball`: kulcs-pozíciónként a
    labdás támadó sorszáma (0-tól; alapból végig az 1. támadó) — ahol
    változik, ott PASSZ: a labda a következő kulcs-pozícióra érkezik az
    átvevőhöz, FIGURA_3D_PASSZ_MPS-mal repülve. A védők a `defense`
    modell szerint, a labdára reagálnak (lásd
    `simulate_setplay`) — legfeljebb FIGURA_VEDO_MAX_MPS-mal lépve (a
    gyors passz előtt a fal nem ér át) —, és a kaput kapus védi (a labda
    felé lép, a vonalon). A mozgás előtt és után FIGURA_3D_ALLAS_S állókép.

    Edzőileg: a megrajzolt figura bejárható — a headsetben a játékos a
    saját útját a saját szemével látja, a tempóval és a fal reakciójával.

    `tamadas` + `mezek` (támadónként a mezszám vagy None): a tanult
    lövők — a kiértékelés a helyzetbe érő támadó sávjának lövő-
    szorzójával számol (AttackModel), a kimenet "lovo_mez" /
    "lovo_szorzo" mezője a helyzetbe érő támadó mezszáma és szorzója.

    Visszaad: (Match — a hazai a támadó, a vendég a védő; kiértékelés:
    {"best_shot_value", "t_s" (a legjobb helyzet ideje), "attacker_id",
    "lovo_mez", "lovo_szorzo", "hossz_s" (a mozgás), "utak" (támadónként
    a pályára szorított kulcs-pozíciók — a padló nyilaihoz), "labda"
    (kulcs-pozíciónként a labdás sorszáma), "passzok" ([[x1, y1, x2, y2],
    …] — a passzok a kulcs-pozíciókon), "kulcs_t" (kulcs-pozíciónként az
    idő mp-ben, a kezdő állóképpel együtt — a lépésenkénti
    megálláshoz)}). ValueError, ha nincs érvényes támadó."""
    config = config or TacticsConfig()
    utak = []
    # (régi sorszám → új: a pont nélküli támadó kiesik, a labdás-sor ehhez
    # igazodik — különben a passz a következő támadóhoz menne)
    regi_uj: dict[int, int] = {}
    for i, ut in enumerate(list(keypoints or [])[:FIGURA_3D_MAX_JATEKOS]):
        pontok = [(min(COURT_LENGTH_M, max(0.0, float(x))),
                   min(COURT_WIDTH_M, max(0.0, float(y))))
                  for x, y in list(ut)[:FIGURA_3D_MAX_PONT]
                  if math.isfinite(float(x)) and math.isfinite(float(y))]
        if pontok:
            regi_uj[i] = len(utak)
            utak.append(pontok)
    if not utak:
        raise ValueError("a figurában nincs támadó")
    # A mezszámok az ÚJ sorszámokon (a kiesett támadóé nélkül); a tanult
    # lövők szorzói ugyanígy.
    mezek = list(mezek or [])
    mezek_uj = [mezek[i] if i < len(mezek) else None
                for i in sorted(regi_uj, key=regi_uj.get)]
    lovok = tamadas.figura_lovok(mezek_uj) if tamadas is not None else None
    szakaszok = max(len(u) for u in utak) - 1
    # A leghosszabb szakasz (bármelyik támadóé) szabja a szakasz-időt.
    leghosszabb = 0.0
    for u in utak:
        for a, b in zip(u, u[1:]):
            leghosszabb = max(leghosszabb, math.hypot(b[0] - a[0], b[1] - a[1]))
    mozgas_s = (leghosszabb / FIGURA_3D_TEMPO_MPS) * max(1, szakaszok)
    mozgas_s = min(FIGURA_3D_MAX_S, max(FIGURA_3D_MIN_S, mozgas_s))
    fps = FIGURA_3D_FPS
    lepesek = max(2, int(round(mozgas_s * fps)) + 1)
    allas = int(round(FIGURA_3D_ALLAS_S * fps))

    def minta(u, t):
        """A kulcs-pozíciók útja t (0..1) helyen, szakaszonként lineárisan."""
        if len(u) == 1:
            return u[0]
        s = min(len(u) - 1.0, max(0.0, t * (len(u) - 1)))
        i = min(len(u) - 2, int(s))
        f = s - i
        return (u[i][0] + (u[i + 1][0] - u[i][0]) * f,
                u[i][1] + (u[i + 1][1] - u[i][1]) * f)

    tamadok = [[minta(u, s / (lepesek - 1)) for s in range(lepesek)]
               for u in utak]
    # A labdás kulcs-pozíciónként (a hibás / hiányzó sorszám az előzőé).
    pontszam = szakaszok + 1
    labda = []
    for k in range(pontszam):
        v = (list(ball or [])[k:k + 1] or [None])[0]
        try:
            v = regi_uj.get(int(v))
        except (TypeError, ValueError):
            v = None
        labda.append(v if v is not None and 0 <= v < len(utak)
                     else (labda[-1] if labda else 0))
    # A labda helye lépésenként: a labdásnál, passznál a kulcs-pozíció
    # előtt elindul, és a kulcs-pozícióra érkezik az átvevőhöz.
    szakasz_s = mozgas_s / max(1, szakaszok)
    labda_hely = []
    passzok = []
    for k in range(szakaszok):
        a, b = labda[k], labda[k + 1]
        if a != b:
            t_cel = (k + 1) / max(1, szakaszok)
            p1, p2 = minta(utak[a], t_cel), minta(utak[b], t_cel)
            passzok.append([round(p1[0], 1), round(p1[1], 1),
                            round(p2[0], 1), round(p2[1], 1)])
    for s in range(lepesek):
        ido = mozgas_s * s / (lepesek - 1)
        k = min(max(0, szakaszok - 1), int(ido / szakasz_s)) if szakaszok else 0
        a = labda[k]
        b = labda[k + 1] if szakaszok else a
        hely = tamadok[a][s]
        if a != b:
            erkezik = szakasz_s * (k + 1)
            cel = minta(utak[b], erkezik / mozgas_s)
            indul_hely = minta(utak[a], (erkezik - szakasz_s) / mozgas_s)
            tav = math.hypot(cel[0] - indul_hely[0], cel[1] - indul_hely[1])
            repul = min(szakasz_s, max(FIGURA_3D_PASSZ_MIN_S,
                                       tav / FIGURA_3D_PASSZ_MPS))
            indul = erkezik - repul
            if ido >= indul:
                honnan = minta(utak[a], indul / mozgas_s)
                f = min(1.0, (ido - indul) / repul)
                hely = (honnan[0] + (cel[0] - honnan[0]) * f,
                        honnan[1] + (cel[1] - honnan[1]) * f)
        labda_hely.append(hely)
    # Állókép az elején és a végén (az első / utolsó helyzet ismétlése).
    tamadok = [[u[0]] * allas + u + [u[-1]] * allas for u in tamadok]
    labda_hely = ([tamadok[labda[0]][0]] * allas + labda_hely
                  + [tamadok[labda[-1]][-1]] * allas)
    sim = simulate_setplay(SetPlay(attackers=tamadok,
                                   ball_carrier=[0] * len(tamadok[0])),
                           defense, config=config, fps=fps,
                           ball_positions=labda_hely)
    # A fal lépés-tempója: a védő kockánként legfeljebb
    # FIGURA_VEDO_MAX_MPS / fps métert tesz a modell-helye felé (a hatoson
    # belülre nem vág) — a kiértékelés már a késő falat látja.
    vedo_kapu_x = config.own_goal_x(Team.AWAY)
    lepes_max = FIGURA_VEDO_MAX_MPS / fps
    elozo: dict[int, tuple[float, float]] = {}
    for f in sim.frames:
        for p in f.players:
            if p.team != Team.AWAY:
                continue
            h = elozo.get(p.track_id)
            if h is not None:
                dx, dy = p.x - h[0], p.y - h[1]
                d = math.hypot(dx, dy)
                if d > lepes_max:
                    p.x, p.y = _hatoson_kivulre(h[0] + dx * lepes_max / d,
                                                h[1] + dy * lepes_max / d,
                                                vedo_kapu_x)
            elozo[p.track_id] = (p.x, p.y)
    # A beállás: amíg a fal nem ér a modell-helyére, az állókép nyúlik
    # (a támadók és a labda állnak, a védők lépnek).
    utolso = sim.frames[-1]
    cel = defense.respond(utolso.ball, vedo_kapu_x)
    for _ in range(int(round(FIGURA_3D_BEALL_MAX_S * fps))):
        vedok = [p for p in utolso.players if p.team == Team.AWAY]
        if all(math.hypot(p.x - cel[p.track_id - 100][0],
                          p.y - cel[p.track_id - 100][1]) < 1e-6
               for p in vedok):
            break
        uj = []
        for p in utolso.players:
            if p.team == Team.AWAY:
                cx, cy = cel[p.track_id - 100]
                dx, dy = cx - p.x, cy - p.y
                d = math.hypot(dx, dy)
                x, y = ((cx, cy) if d <= lepes_max else _hatoson_kivulre(
                    p.x + dx * lepes_max / d, p.y + dy * lepes_max / d,
                    vedo_kapu_x))
                uj.append(replace(p, x=x, y=y))
            else:
                uj.append(replace(p))
        utolso = Frame(t=utolso.t + 1, players=uj, ball=utolso.ball)
        sim.frames.append(utolso)
    # A kezdő állókép nélkül: a figura azt kapja, amit a MOZGÁS teremt.
    ertekeles = evaluate_setplay(sim, config=config, defense=defense,
                                 from_t=allas, lovok=lovok)
    # A kapus: a vonal előtt, a labda felé lépve (a kapufák közt). A
    # védők mezszámot kapnak (a kapus után sorban) — a szemükkel is
    # nézhető a figura.
    kapu_x = config.own_goal_x(Team.AWAY)
    elore = -1.0 if kapu_x == COURT_LENGTH_M else 1.0
    for f in sim.frames:
        for p in f.players:
            if p.team == Team.AWAY and p.track_id >= 100:
                p.jersey_number = FIGURA_KAPUS_MEZ + 1 + (p.track_id - 100)
        ky = COURT_WIDTH_M / 2.0
        if f.ball is not None:
            ky += max(-1.2, min(1.2, 0.2 * (f.ball.y - COURT_WIDTH_M / 2.0)))
        f.players.append(PlayerPosition(
            track_id=99, team=Team.AWAY, x=kapu_x + elore * 0.6, y=ky,
            source=PositionSource.MEASURED, confidence=1.0, role="kapus",
            jersey_number=FIGURA_KAPUS_MEZ))
    sim.meta.match_id = "figura-3d"
    sim.meta.home_team = figura_nev(name) or "Figura"
    sim.meta.away_team = (figura_nev(defense_name, FIGURA_3D_VEDO_NEV_MAX)
                          or "Védelem")
    tam = ertekeles["attacker_id"]
    return sim, {
        "best_shot_value": round(float(ertekeles["best_shot_value"]), 3),
        "t_s": (round(ertekeles["step"] / fps, 1)
                if ertekeles["step"] >= 0 else None),
        "attacker_id": tam,
        "lovo_mez": (mezek_uj[tam - 1]
                     if tam and 0 <= tam - 1 < len(mezek_uj) else None),
        "lovo_szorzo": round(float(ertekeles.get("lovo_szorzo", 1.0)), 3),
        # A mezszámok az érvényes támadók sorrendjében (a finomítónak).
        "mezek": list(mezek_uj),
        "hossz_s": round(mozgas_s, 1),
        "utak": [[[round(x, 1), round(y, 1)] for x, y in u] for u in utak],
        "labda": labda,
        "passzok": passzok,
        # A k. kulcs-pozíció a mozgás k/szakaszok részénél (az állókép után).
        "kulcs_t": [round((allas + k * (lepesek - 1) / max(1, szakaszok)) / fps, 2)
                    for k in range(szakaszok + 1)],
    }


# ---- A meccs támadásából figura ---------------------------------------------
# A valódi támadás a tervezőbe: ennél rövidebb (mp) szakasz nem figura, a
# kért pillanat körül ennyi mp-en belül keressük a legközelebbi támadást,
# és legfeljebb ennyi mezőnyjátékos (kapus nélkül) kerül bele. A játékos
# akkor számít, ha a szakasz kockáinak legalább ekkora részén látszik.
FIGURA_MECCSBOL_MIN_S = 2.0
FIGURA_MECCSBOL_KERES_S = 3.0
FIGURA_MECCSBOL_MAX_JATEKOS = 6
FIGURA_MECCSBOL_JELEN_ARANY = 0.3
# A saját térfelén (a felezőtől ennyi m-nél mélyebben) álló játékos — a
# kapus, a hátul maradó — nem része a figurának.
FIGURA_MECCSBOL_SAJAT_TERFEL_M = 2.0


def attack_figure(match: Match, t: int, *, pontok: int = 3,
                  config: TacticsConfig | None = None) -> dict | None:
    """A `t` kockát tartalmazó (vagy hozzá FIGURA_MECCSBOL_KERES_S-en belül
    legközelebbi) szervezett támadás FIGURAKÉNT: a támadó csapat
    mezőnyjátékosainak helye `pontok` kulcs-pozíción (a támadás elejétől a
    végéig egyenletesen), és kinél volt a labda (a labdához legközelebbi).

    Edzőileg: a jó (vagy az ellenfél veszélyes) támadása a Figura-
    tervezőbe kerül — szerkeszthető, menthető, más védelem ellen
    kipróbálható, 3D-ben/VR-ben bejárható.

    A figura mindig a +x kapura támad (a tervezőé): a -x felé támadást a
    pálya közepére FORGATJUK (x → 40-x, y → 20-y — a bal oldal bal marad).
    A hiányzó (takarásban lévő) játékos helye a hozzá legközelebbi kocka,
    ahol látszik; a saját térfelén álló (a kapus, ha a jelölés nem ismerte
    fel) kimarad. A játékosok a kezdő y szerint (balról jobbra) rendezve.

    Visszaad: {"attackers": [[[x, y], …], …], "labda": [sorszám, …],
    "csapat", "csapat_oldal" ("home"/"away"), "t0_s", "t1_s", "mez":
    [mezszám | None, …]} — None, ha nincs a közelben elég hosszú támadás,
    vagy kettőnél kevesebb játékos látszik."""
    from collections import Counter
    from bisect import bisect_left
    from .setplays import segment_attacks

    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    legjobb, legjobb_d = None, None
    for sz in segment_attacks(match, config):
        d = (0 if sz.start_t <= t <= sz.end_t
             else min(abs(t - sz.start_t), abs(t - sz.end_t)))
        if legjobb_d is None or d < legjobb_d:
            legjobb, legjobb_d = sz, d
    if legjobb is None or legjobb_d > FIGURA_MECCSBOL_KERES_S * fps:
        return None
    if (legjobb.end_t - legjobb.start_t) / fps < FIGURA_MECCSBOL_MIN_S:
        return None
    kockak = legjobb.frames
    csapat = legjobb.team
    db = Counter(p.track_id for f in kockak for p in f.players
                 if p.team == csapat and getattr(p, "role", None) != "kapus")
    tracks = [tid for tid, n in db.most_common()
              if n >= len(kockak) * FIGURA_MECCSBOL_JELEN_ARANY]
    pontok = max(2, min(FIGURA_3D_MAX_PONT, int(pontok)))
    idxs = [round(k * (len(kockak) - 1) / (pontok - 1)) for k in range(pontok)]
    helyek: dict = {tid: [] for tid in tracks}   # tid -> [(i, x, y)]
    mezek: dict = {}
    for i, f in enumerate(kockak):
        for p in f.players:
            if p.track_id in helyek and p.team == csapat:
                helyek[p.track_id].append((i, p.x, p.y))
                if p.jersey_number is not None:
                    mezek.setdefault(p.track_id, p.jersey_number)

    def hely(tid, i):
        sor = helyek[tid]
        j = bisect_left([e[0] for e in sor], i)
        jelolt = [sor[k] for k in (j - 1, j) if 0 <= k < len(sor)]
        e = min(jelolt, key=lambda e: abs(e[0] - i))
        return e[1], e[2]

    # Az irány a labdából (a kapus a saját kapujában elhúzná az átlagot);
    # labda nélkül a játékosok mediánjából.
    lx = sorted(f.ball.x for f in kockak if f.ball is not None)
    if not lx:
        lx = sorted(e[1] for tid in tracks for e in helyek[tid])
    if not lx:
        return None
    forgat = lx[len(lx) // 2] < COURT_LENGTH_M / 2.0

    def tamado_x(x):
        return COURT_LENGTH_M - x if forgat else x
    # A saját térfelén álló (kapus, hátul maradó) kimarad; a legtöbbet
    # látszók közül legfeljebb FIGURA_MECCSBOL_MAX_JATEKOS.
    tracks = [tid for tid in tracks
              if sum(tamado_x(e[1]) for e in helyek[tid]) / len(helyek[tid])
              >= COURT_LENGTH_M / 2.0 - FIGURA_MECCSBOL_SAJAT_TERFEL_M]
    tracks = tracks[:FIGURA_MECCSBOL_MAX_JATEKOS]
    if len(tracks) < 2:
        return None
    nyers = [[hely(tid, i) for i in idxs] for tid in tracks]

    def tr(x, y):
        return ((COURT_LENGTH_M - x, COURT_WIDTH_M - y) if forgat else (x, y))

    utak = [[tr(x, y) for x, y in u] for u in nyers]
    labda: list = []
    for k, i in enumerate(idxs):
        b = kockak[i].ball
        if b is None:
            labda.append(labda[-1] if labda else 0)
            continue
        bx, by = tr(b.x, b.y)
        tav = [math.hypot(u[k][0] - bx, u[k][1] - by) for u in utak]
        labda.append(tav.index(min(tav)))
    sorrend = sorted(range(len(utak)), key=lambda j: (utak[j][0][1], j))
    uj_index = {j: n for n, j in enumerate(sorrend)}
    return {
        "attackers": [[[round(x, 1), round(y, 1)] for x, y in utak[j]]
                      for j in sorrend],
        "labda": [uj_index[v] for v in labda],
        "csapat": (match.meta.home_team if csapat == Team.HOME
                   else match.meta.away_team),
        "csapat_oldal": "home" if csapat == Team.HOME else "away",
        "t0_s": round(legjobb.start_t / fps, 1),
        "t1_s": round(legjobb.end_t / fps, 1),
        "mez": [mezek.get(tracks[j]) for j in sorrend],
    }


def evaluate_setplay(match: Match, config: TacticsConfig | None = None,
                     defense: DefenseModel | None = None,
                     from_t: int = 0, lovok: list | None = None) -> dict:
    """Pontozza a szimulált figurát: a teremtett legjobb lövőhelyzet.

    Minden lépésben minden támadóra: várható gól (xg.xg_of_position — a
    termék xG-modellje: 6 m-ről ~0,6, 9 m-ről ~0,37, 12 m-ről ~0,15) *
    "szabadság" (a legközelebbi védő távolsága alapján — 4 m-en belül
    fedezett). A legjobb érték a figura pontszáma. A döntés-elemzés
    egyszerű lövésértéke (decisions.shot_value) a 13 m-es szabad lövést
    a fedezett 6 m-es fölé tette — a figura-ajánló és az AI-finomító így
    hátrébb tolta volna a támadókat.
    A `defense` tanult kapusa (DefenseModel.kapus) a lövőhely sávjának
    szorzójával súlyoz — a kapus gyenge sávjából jövő helyzet többet ér.
    `from_t`: ettől a kockától pontoz — a 3D figura a kezdő állóképet
    kihagyja (a felállás nem a figura által teremtett helyzet: a mozgás
    előtt a labdás 13 m-ről "szabad", és minden figura ugyanazt a
    pontot kapná).
    `lovok`: támadónként (a track_id − 1 sorszámon) a tanult lövő
    sávonkénti szorzója (AttackModel.figura_lovok) — a helyzetbe érő
    támadó sávjának szorzójával súlyoz: a biztos kezű lövő helyzete
    többet ér, a bizonytalané kevesebbet.

    Visszaad: {"best_shot_value", "step", "attacker_id", "lovo_szorzo"
    (a legjobb helyzetnél alkalmazott lövő-szorzó; 1, ha nincs)}.
    """
    from .xg import xg_of_position

    config = config or TacticsConfig()
    goal_x = config.attacks_toward_x(Team.HOME)
    best = {"best_shot_value": 0.0, "step": -1, "attacker_id": None,
            "lovo_szorzo": 1.0}

    for f in match.frames:
        if f.t < from_t:
            continue
        attackers = [p for p in f.players if p.team == Team.HOME]
        defenders = [p for p in f.players if p.team == Team.AWAY]
        for a in attackers:
            sv = xg_of_position(a.x, a.y, goal_x)
            if defenders:
                nd = min(math.hypot(a.x - d.x, a.y - d.y) for d in defenders)
            else:
                nd = 99.0
            openness = max(0.0, min(1.0, nd / 4.0))  # 4 m-en belül fedezett
            score = sv * openness
            if defense is not None and defense.kapus:
                score *= defense.kapus_szorzo(a.x, a.y, goal_x)
            lsz = 1.0
            if lovok:
                i = a.track_id - 1
                if 0 <= i < len(lovok) and lovok[i]:
                    lsz = float(lovok[i].get(kapus_sav(a.x, a.y, goal_x), 1.0))
                    score *= lsz
            if score > best["best_shot_value"]:
                best = {"best_shot_value": score, "step": f.t,
                        "attacker_id": a.track_id, "lovo_szorzo": lsz}
    return best


# ---- Figura-ajánló: melyik mentett figura működik EZ ellen a fal ellen ----
# A rangsor a 3D-figura kiértékelése (setplay_3d_match: valós tempó, a fal
# lépés-tempója), összevetve a kézi alap-fallal (6-0, 6 védő, 6 m).
# Ekkora százalékpontos eltérés számít úgy, hogy EZ a fal jobban vagy
# rosszabbul zárja a figurát, mint az alap; legfeljebb ennyi figurát
# értékelünk (a könyvtár mérete — egy kérés ne fusson percekig).
AJANLO_ELTERES_PP = 5.0
AJANLO_MAX = 60


# Alap-figurák (sablonok): mentett figura nélkül is van mit rangsorolni a
# tanult fal ellen — a kézilabda öt alapfigurája, a tervező alakjában
# (támadónként Kezdő / Közép / Vég kulcs-pozíció méterben, a +x kapura;
# "labda": kulcs-pozíciónként a labdás sorszáma). Az edző a tervezőben
# betöltheti és átrajzolhatja; a mentett figura a sablont kiszorítja.
ALAP_FIGURAK = [
    {"id": "sablon-kereszt", "name": "Keresztezés jobbra, beálló-leválás",
     "sablon": True, "labda": [0, 1, 1],
     "attackers": [[[28, 10], [30, 12], [31.5, 13.5]],
                   [[29, 14], [30, 11], [32, 9.5]],
                   [[33, 10], [33.5, 12], [34, 13]],
                   [[28, 5], [28, 5], [29, 6]]]},
    {"id": "sablon-pick", "name": "Pick & roll középen",
     "sablon": True, "labda": [0, 0, 1],
     "attackers": [[[27, 10], [30, 10], [32, 10.5]],
                   [[33, 10], [31.5, 9], [33.5, 11]],
                   [[28, 15], [29, 14], [30, 13]],
                   [[28, 5], [29, 5], [30, 6]]]},
    {"id": "sablon-szelso", "name": "Szélső beindulás második beállónak",
     "sablon": True, "labda": [1, 1, 0],
     "attackers": [[[32, 18.5], [33, 15], [34, 12]],
                   [[27, 10], [29, 10], [30, 10]],
                   [[33, 9], [33, 8], [33, 7]],
                   [[28, 15], [30, 14], [31, 13]]]},
    {"id": "sablon-atloves", "name": "Átlövés 9 m-ről, beálló-zárással",
     "sablon": True, "labda": [0, 1, 1],
     "attackers": [[[27, 10], [28, 11], [29, 12]],
                   [[27, 15], [29, 14], [30.5, 12.5]],
                   [[33, 11], [32.5, 12.5], [32, 13.5]],
                   [[28, 5], [29, 5], [30, 5.5]]]},
    {"id": "sablon-7a6", "name": "Hét a hat ellen, két beállóval",
     "sablon": True, "labda": [0, 0, 3],
     "attackers": [[[27, 10], [29, 10], [30, 10]],
                   [[27, 5], [29, 5], [30, 5.5]],
                   [[27, 15], [29, 15], [30, 14.5]],
                   [[33, 8], [33.5, 7.5], [34, 7]],
                   [[33, 12], [33.5, 12.5], [34, 13]],
                   [[32, 1.5], [33, 2], [34, 3]],
                   [[32, 18.5], [33, 18], [34, 17]]]},
]


def rank_playbook(figurak: list, defense: DefenseModel, *,
                  config: TacticsConfig | None = None,
                  tamadas: AttackModel | None = None) -> dict:
    """Figura-ajánló: a mentett figurák rangsora a `defense` fal ellen.

    Minden figurát lejátszunk a fal ellen (setplay_3d_match — mint a 3D
    és a figura-lap), és az alap-fal (DefenseModel()) ellen is: a
    különbség megmutatja, hogy EZ a védelem melyik figurát zárja
    rosszabbul (ott van a rés), és melyiket jobban.

    Edzőileg: "melyik figuránkat vegyük elő ellenük?" — a tanult fal (a
    rendszere, a mélysége, a kilépése, a labdakövetése, a kettőzése)
    ellen a legnagyobb lövőhelyzetet teremtő figura az első; az
    "óvatosan" figura az, amit ez a fal (az alap-falhoz mérten) legalább
    AJANLO_ELTERES_PP-vel jobban zár, mint az ajánlottat.

    `tamadas` (AttackModel — a MI tanult lövőink): a figura támadóinak
    mezszámaival ("mez" — a meccsből vett és onnan mentett figura hozza)
    a helyzetbe érő támadó lövő-szorzója is számít, MINDKÉT fal ellen
    (az eltérés a falé marad): a biztos kezű lövővel záruló figura
    többet ér.

    Visszaad: {"figurak": [{"id", "name", "pont_pct" (a legjobb
    lövőhelyzet ezen fal ellen, %), "alap_pct" (az alap-fal ellen),
    "elteres_pp", "t_s", "tamado" (a legjobb helyzetű támadó sorszáma,
    1-től), "lovo_mez" (a mezszáma, ha ismert), "lovo_szorzo"}, …] a
    pont szerint csökkenőben (holtversenyben név, id), és "ajanlas"
    (magyar mondat, vagy None, ha nincs értékelhető figura)}. A hibás
    (pont nélküli, nem szám koordinátájú) figura kimarad."""
    alap = DefenseModel()
    sorok = []
    for d in list(figurak or [])[:AJANLO_MAX]:
        if not isinstance(d, dict):
            continue
        mezek = d.get("mez") if isinstance(d.get("mez"), list) else None
        try:
            _, e = setplay_3d_match(d.get("attackers") or [], defense,
                                    ball=d.get("labda"), config=config,
                                    tamadas=tamadas, mezek=mezek)
            _, ea = setplay_3d_match(d.get("attackers") or [], alap,
                                     ball=d.get("labda"), config=config,
                                     tamadas=tamadas, mezek=mezek)
        except (TypeError, ValueError):
            continue          # hibás figura-fájl: kimarad a rangsorból
        pont, ap = e["best_shot_value"], ea["best_shot_value"]
        sorok.append({
            "id": d.get("id"),
            "name": figura_nev(d.get("name")) or "névtelen",
            "sablon": bool(d.get("sablon")),
            "pont_pct": round(100.0 * pont, 1),
            "alap_pct": round(100.0 * ap, 1),
            "elteres_pp": round(100.0 * (pont - ap), 1),
            "t_s": e["t_s"],
            "tamado": e["attacker_id"],
            "lovo_mez": e["lovo_mez"],
            "lovo_szorzo": e["lovo_szorzo"],
        })
    sorok.sort(key=lambda r: (-r["pont_pct"], r["name"].lower(),
                              str(r["id"] or "")))
    ajanlas = None
    if sorok:
        b = sorok[0]
        ajanlas = (f"Ellenük a(z) „{b['name']}” figura működik a "
                   f"legjobban: {b['pont_pct']:.0f}% lövőhelyzet")
        if b["tamado"] and b["t_s"] is not None:
            # (az 1. és az 5. — "első", "ötödik" — magánhangzóval kezdődik)
            nevelo = "az" if b["tamado"] in (1, 5) else "a"
            mp = f"{b['t_s']:.1f}".replace(".", ",")
            ajanlas += (f" ({mp} mp-nél, {nevelo} {b['tamado']}. támadónál"
                        + lovo_zaradek(b, elo=" — ") + ")")
        if b["elteres_pp"] >= AJANLO_ELTERES_PP:
            ajanlas += (f" — ez a fal {b['elteres_pp']:.0f} százalékponttal "
                        "rosszabbul zárja, mint az alap 6-0")
        ajanlas += "."
        # A "kerüld": amit ez a fal az alaphoz mérten legalább
        # AJANLO_ELTERES_PP-vel JOBBAN zár, mint az ajánlottat.
        kerul = [r for r in sorok[1:]
                 if r["elteres_pp"] <= min(0.0, b["elteres_pp"])
                 - AJANLO_ELTERES_PP]
        if kerul:
            k = min(kerul, key=lambda r: (r["elteres_pp"], r["name"].lower(),
                                          str(r["id"] or "")))
            ajanlas += (f" Óvatosan a(z) „{k['name']}” figurával: ellenük "
                        f"{k['pont_pct']:.0f}% (az alap fal ellen "
                        f"{k['alap_pct']:.0f}%).")
    return {"figurak": sorok, "ajanlas": ajanlas}


# ---- Védekezési próba: az ő visszatérő figuráik a MI tanult falunk ellen --
# Egy figura akkor "visszatérő", ha legalább ennyiszer játszották (a
# támadás-ujjlenyomatok klaszterében); legfeljebb ennyi figurát
# értékelünk. A figura képviselője a klaszter LEGHOSSZABB szakasza (abban
# látszik a teljes mozgás). Az alap-fal és az eltérés-küszöb a figura-
# ajánlóé (AJANLO_ELTERES_PP).
PROBA_MIN_ISMETLES = 2
PROBA_MAX = 8


def recurring_figures(match: Match, attacking: Team,
                      config: TacticsConfig | None = None) -> list:
    """Az `attacking` csapat visszatérő figurái: a meccs támadás-
    szakaszainak klaszterei (setplays), legalább PROBA_MIN_ISMETLES
    ismétléssel, az ismétlés szerint csökkenőben (holtversenyben a
    klaszter sorszáma) — [(figura: attack_figure a klaszter leghosszabb
    szakaszából, a klaszter szakaszai időrend nélkül), …]; a figurává
    nem alakítható klaszter kimarad. A védekezési próba és a
    falválasztás közös alapja."""
    from .setplays import (attack_signature, cluster_signatures,
                           segment_attacks)
    config = config or TacticsConfig()
    seqs = segment_attacks(match, config)
    labels = cluster_signatures([attack_signature(s) for s in seqs])
    klaszter: dict[int, list] = {}
    for s, lab in zip(seqs, labels):
        if s.team == attacking:
            klaszter.setdefault(lab, []).append(s)
    ki = []
    for lab in sorted(klaszter, key=lambda k: (-len(klaszter[k]), k)):
        tagok = klaszter[lab]
        if len(tagok) < PROBA_MIN_ISMETLES:
            continue
        rep = max(tagok, key=lambda s: (s.end_t - s.start_t, -s.start_t))
        fig = attack_figure(match, (rep.start_t + rep.end_t) // 2,
                            config=config)
        if fig is None:
            continue
        ki.append((fig, tagok))
    return ki


# ---- Falválasztás: melyik rendszerünk zárja a figuráikat --------------------
# Az ellenfél visszatérő figurái (recurring_figures) a MI tanult falunkkal
# lejátszva, de a rendszert cserélve (VEDEKEZESI_RENDSZEREK mind — a
# kilépés, a kettőzés, a labdakövetés, a kapus és a védők maradnak), a
# tanult lövőikkel; rendszerenként az ismétléssel súlyozott átlagos
# legjobb lövőhelyzet. A legkisebb a javasolt; váltást csak akkor mond,
# ha a javasolt legalább FALVALASZTAS_ELTERES_PP-vel kevesebbet enged a
# mostani (tanult) rendszernél. A felderítésben a javasolt rendszer
# meccsenként számolódik; a kulcshoz legalább FV_MIN_MECCS meccs kell.
FALVALASZTAS_ELTERES_PP = 3.0
FV_MIN_MECCS = 2


def rendszer_nevelovel(r: str) -> str:
    """A rendszer névelővel ("az 5-1", "a 6-0", "a 3-2-1")."""
    return ("az " if str(r).startswith("5") else "a ") + str(r)


def defense_system_choice(match: Match,
                          config: TacticsConfig | None = None) -> dict:
    """Falválasztás — csapatonként, a VÉDEKEZŐ oldal szemszögéből: az
    ellenfél visszatérő figurái ellen melyik rendszerünk (6-0, 5-1, 4-2,
    3-2-1, 3-3) teremt a legkisebb lövőhelyzetet — a tanult falunk
    szokásaival és az ő tanult lövőikkel lejátszva.

    Edzőileg: "ellenük milyen falat hozzunk?" — nem általában, hanem az
    ő figuráik ellen: ha a figurájuk a beállóra épül, az előretolt
    védős rendszer zárhatja jobban; ha átlövésre, a mély 6-0.

    Visszaad csapatonként: {"rendszerek" ({rendszer: lövőhelyzet %}),
    "mostani" (a tanult rendszerünk), "mostani_pct", "javasolt",
    "javasolt_pct", "javulas_pp", "valt" (érdemi-e a váltás), "figurak"
    (hány visszatérő figurájuk), "verdict"} — None, ha nincs visszatérő
    figurájuk (kevés minta — a modell nem találgat)."""
    config = config or TacticsConfig()
    out: dict = {}
    for side, team, masik in (("home", Team.HOME, Team.AWAY),
                              ("away", Team.AWAY, Team.HOME)):
        figurak = recurring_figures(match, masik, config)[:PROBA_MAX]
        if not figurak:
            out[side] = None
            continue
        fal = DefenseModel.learn(match, team, config)
        tam = AttackModel.learn(match, masik, config)
        pontok: dict = {}
        for r in VEDEKEZESI_RENDSZEREK:
            fal_r = replace(fal, rendszer=r)
            ossz = suly = 0.0
            for fig, tagok in figurak:
                try:
                    _, e = setplay_3d_match(fig["attackers"], fal_r,
                                            ball=fig["labda"], config=config,
                                            tamadas=tam, mezek=fig.get("mez"))
                except ValueError:
                    continue
                ossz += e["best_shot_value"] * len(tagok)
                suly += len(tagok)
            if suly:
                pontok[r] = round(100.0 * ossz / suly, 1)
        if not pontok:
            out[side] = None
            continue
        mostani = fal.rendszer if fal.rendszer in pontok else "6-0"
        javasolt = min(pontok, key=lambda r: (pontok[r], r != mostani, r))
        javulas = round(pontok[mostani] - pontok[javasolt], 1)
        valt = javasolt != mostani and javulas >= FALVALASZTAS_ELTERES_PP
        if valt:
            verdict = (f"a figuráik ellen {rendszer_nevelovel(javasolt)} zár "
                       f"jobban: {pontok[javasolt]:.0f}% lövőhelyzet a mostani "
                       f"{mostani} {pontok[mostani]:.0f}%-a helyett "
                       f"({javulas:.0f} százalékponttal kevesebb, "
                       f"{len(figurak)} figurájukból)")
        else:
            masik_r = min((r for r in pontok if r != mostani),
                          key=lambda r: (pontok[r], r), default=None)
            verdict = (f"a figuráik ellen a mostani {mostani} a jó: "
                       f"{pontok[mostani]:.0f}% lövőhelyzet"
                       + (f" (a legjobb másik rendszer, {rendszer_nevelovel(masik_r)}: "
                          f"{pontok[masik_r]:.0f}%)" if masik_r else ""))
        out[side] = {"rendszerek": pontok, "mostani": mostani,
                     "mostani_pct": pontok[mostani], "javasolt": javasolt,
                     "javasolt_pct": pontok[javasolt], "javulas_pp": javulas,
                     "valt": valt, "figurak": len(figurak), "verdict": verdict}
    return out


def defense_test(match: Match, attacking: Team, defense: DefenseModel, *,
                 config: TacticsConfig | None = None,
                 tamadas: AttackModel | None = None) -> dict:
    """Védekezési próba: az `attacking` csapat visszatérő figuráit (a
    meccs támadás-szakaszainak klaszterei, legalább PROBA_MIN_ISMETLES
    ismétléssel) lejátsszuk a `defense` fal ellen — mint a figura-
    ajánló, csak fordítva: az ő figurájuk, a mi falunk.

    Edzőileg: "melyik figurájukra NEM vagyunk felkészülve?" — amelyik a
    mi tanult falunk ellen nagyobb lövőhelyzetet teremt, mint egy alap
    6-0 ellen, ott a falunk szokása (a kilépés, a kettőzés, a
    labdakövetés) maga nyitja a rést; azt kell a meccs előtt
    begyakorolni.

    `tamadas` (AttackModel — az Ő tanult lövőik): a figura támadóinak
    mezszámával (a meccsből vett figura "mez" sora) a figurát záró lövő
    szorzója is számít, mindkét fal ellen — a biztos kezű lövőjükkel
    záruló figura veszélyesebb, és a mondat megnevezi.

    Visszaad: {"figurak": [{"t0_s", "t1_s", "ismetles", "pont_pct",
    "alap_pct", "elteres_pp", "attackers", "labda", "mez" (támadónként a
    mezszám vagy None), "lovo_mez" / "lovo_szorzo" (a helyzetbe érő
    támadó mezszáma és lövő-szorzója), "tagok" (a figura minden
    előfordulása: [[kezdő kocka, záró kocka], …] időrendben — az élő
    figura-riasztás ebből ismeri fel, melyik figura indul)}, …] a pont
    szerint csökkenőben (holtversenyben az idő), és "verdict" (magyar
    mondat, vagy None, ha nincs visszatérő figura)}."""
    config = config or TacticsConfig()
    alap = DefenseModel()
    sorok = []
    for fig, tagok in recurring_figures(match, attacking, config):
        try:
            _, e = setplay_3d_match(fig["attackers"], defense,
                                    ball=fig["labda"], config=config,
                                    tamadas=tamadas, mezek=fig.get("mez"))
            _, ea = setplay_3d_match(fig["attackers"], alap,
                                     ball=fig["labda"], config=config,
                                     tamadas=tamadas, mezek=fig.get("mez"))
        except ValueError:
            continue
        pont, ap = e["best_shot_value"], ea["best_shot_value"]
        sorok.append({
            "t0_s": fig["t0_s"], "t1_s": fig["t1_s"],
            "ismetles": len(tagok),
            "pont_pct": round(100.0 * pont, 1),
            "alap_pct": round(100.0 * ap, 1),
            "elteres_pp": round(100.0 * (pont - ap), 1),
            "attackers": fig["attackers"], "labda": fig["labda"],
            "mez": list(fig.get("mez") or []),
            "lovo_mez": e["lovo_mez"], "lovo_szorzo": e["lovo_szorzo"],
            "tagok": [[int(s.start_t), int(s.end_t)]
                      for s in sorted(tagok, key=lambda s: s.start_t)],
        })
        if len(sorok) >= PROBA_MAX:
            break
    sorok.sort(key=lambda r: (-r["pont_pct"], r["t0_s"]))
    verdict = None
    if sorok:
        b = sorok[0]
        perc = int(b["t0_s"] // 60)
        mp = int(b["t0_s"] % 60)
        verdict = (f"a legveszélyesebb visszatérő figurájuk "
                   f"({b['ismetles']}×, pl. {perc}:{mp:02d}-kor) a falatok "
                   f"ellen {b['pont_pct']:.0f}% lövőhelyzetet teremt"
                   + lovo_zaradek(b))
        if b["elteres_pp"] >= AJANLO_ELTERES_PP:
            verdict += (f" — a falatok szokása {b['elteres_pp']:.0f} "
                        "százalékponttal többet enged, mint egy alap 6-0: "
                        "ezt a figurát a meccs előtt be kell gyakorolni")
            # A játékos-modell: ki nyitja a rést (ha ismert és érdemi).
            kil = defense.kilepo_vedo()
            ket = defense.kettozo_vedo()
            kik = ([f"{mezszam_nevelovel(kil['mez'])} kilépése"]
                   if kil and kil["press_rate"] >= 0.3 else []) + (
                  [f"{mezszam_nevelovel(ket['mez'])} kettőzése"]
                   if ket and ket["double_rate"] >= 0.2 else [])
            if kik:
                verdict += " (" + " és ".join(kik) + " nyitja)"
    return {"figurak": sorok, "verdict": verdict}


# ---- AI-finomító: a figura kis módosításai a tanult fal ellen -------------
# Egy lépés ennyi méter egy kulcs-pozíción (nyolc irányban); legfeljebb
# ennyi javító kör fut; ennél kisebb javulás (százalékpont) nem lépés —
# az értékmodell zaja. A támadó a hatoson kívül legalább ennyivel áll
# (a kapuelőtérbe nem léphet), és a pálya szélétől is ennyire.
FINOMITO_LEPES_M = 1.0
FINOMITO_KOROK = 6
FINOMITO_MIN_JAVULAS_PP = 1.0
FINOMITO_RAHAGYAS_M = 0.3
# A passz-javaslat legfeljebb ekkora passz (m) lehet: a szimuláció nem
# ismeri az elfogást, a hosszú keresztpassz a modellben "ingyen" van.
FINOMITO_PASSZ_MAX_M = 12.0


def _pont_nev(i: int, k: int) -> str:
    """A kulcs-pozíció neve (mint a tervezőben és a figura-lapon)."""
    if k == 3:
        return ("Kezdő", "Közép", "Vég")[i]
    if k == 2:
        return ("Kezdő", "Vég")[i]
    return f"{i + 1}."


def refine_setplay(keypoints: list, defense: DefenseModel, *,
                   ball: list | None = None,
                   config: TacticsConfig | None = None,
                   tamadas: AttackModel | None = None,
                   mezek: list | None = None) -> dict:
    """AI-finomító: a figura kulcs-pozícióinak kis módosításai, amelyek a
    `defense` fal ellen nagyobb lövőhelyzetet teremtenek.

    Hegymászás: minden körben minden támadó minden kulcs-pozícióját (a
    KEZDŐ felállás kivételével — az az edzőé) nyolc irányba
    FINOMITO_LEPES_M-rel elmozdítjuk, a figurát a fal ellen lejátsszuk
    (setplay_3d_match), és a legjobb javító lépést megtartjuk — amíg a
    javulás FINOMITO_MIN_JAVULAS_PP alatt nem marad, legfeljebb
    FINOMITO_KOROK körig. A támadó a hatosba és a saját térfelére nem
    léphet. A futások mellett a PASSZOKAT is próbálja: egy kulcs-
    pozíciótól kezdve egy másik támadónál a labda (legfeljebb
    FINOMITO_PASSZ_MAX_M-es passzal). A tanult lövőkkel (`tamadas` +
    `mezek`: támadónként a mezszám) a SZEREPCSERÉT is: két támadó utat
    cserél — a biztos kezű lövő fusson arra az útra, amelyik a
    helyzetet teremti.

    Edzőileg: "hol nyit rést ez a fal a figurámon?" — a modell a fal
    tanult szokásai (kilépés, kettőzés, labdakövetés) ellen keresi meg,
    melyik futás végpontja ér többet néhány méterrel arrébb, kinek
    érdemes a labdát odaadni, és ki fejezze be. Javaslat, nem ítélet:
    az edző dönti el, átveszi-e.

    Visszaad: {"attackers" (a finomított kulcs-pozíciók), "labda", "mez"
    (támadónként a mezszám a finomítás után — a csere itt látszik),
    "pont_elotte", "pont_utana", "javulas_pp", "valtozasok" (magyar
    mondatok támadónként és pontonként, a labda új útja és a
    szerepcsere, ha változott), "verdict"}. ValueError, ha nincs
    érvényes támadó."""
    config = config or TacticsConfig()
    goal_x = config.attacks_toward_x(Team.HOME)
    _, e0 = setplay_3d_match(keypoints, defense, ball=ball, config=config,
                             tamadas=tamadas, mezek=mezek)
    utak = [[list(p) for p in u] for u in e0["utak"]]
    labda = list(e0["labda"])
    mez = list(e0["mezek"])
    kozep = COURT_WIDTH_M / 2.0

    def ervenyes(x: float, y: float) -> bool:
        r = FINOMITO_RAHAGYAS_M
        if not (r <= x <= COURT_LENGTH_M - r and r <= y <= COURT_WIDTH_M - r):
            return False
        if abs(x - goal_x) > COURT_LENGTH_M / 2.0:
            return False      # a saját térfelére nem fut vissza
        hx, hy = _hatoson_kivulre(x, y, goal_x)
        if (hx, hy) != (x, y):
            return False      # a hatoson belül
        fa_y = min(kozep + _GOAL_HALF_W, max(kozep - _GOAL_HALF_W, y))
        return math.hypot(x - goal_x, y - fa_y) >= GOAL_AREA_RADIUS_M + r

    def pont(u, lab, mz) -> float:
        _, e = setplay_3d_match(u, defense, ball=lab, config=config,
                                tamadas=tamadas, mezek=mz)
        return e["best_shot_value"]

    def passz_hossz(u, a: int, b: int, k: int) -> float:
        pa = u[a][min(k, len(u[a]) - 1)]
        pb = u[b][min(k, len(u[b]) - 1)]
        return math.hypot(pa[0] - pb[0], pa[1] - pb[1])

    alap = e0["best_shot_value"]
    most = alap
    lepes = FINOMITO_LEPES_M
    iranyok = [(lepes * math.cos(a), lepes * math.sin(a))
               for a in (k * math.pi / 4 for k in range(8))]
    # Szerepcsere csak tanult lövőkkel és legalább két mezszámmal.
    cserelhet = (tamadas is not None and tamadas.lovok
                 and sum(m is not None for m in mez) >= 2)
    for _ in range(FINOMITO_KOROK):
        legjobb = None
        for i, u in enumerate(utak):
            for k in range(1, len(u)):
                for dx, dy in iranyok:
                    x, y = u[k][0] + dx, u[k][1] + dy
                    if not ervenyes(x, y):
                        continue
                    proba = [list(map(list, v)) for v in utak]
                    proba[i][k] = [x, y]
                    p = pont(proba, labda, mez)
                    if legjobb is None or p > legjobb[0] + 1e-12:
                        legjobb = (p, proba, labda, mez)
        # A passzok: a k. kulcs-pozíciótól a j. támadónál a labda.
        for k in range(1, len(labda)):
            for j in range(len(utak)):
                if j == labda[k] or passz_hossz(
                        utak, labda[k - 1], j, k) > FINOMITO_PASSZ_MAX_M:
                    continue
                lab = labda[:k] + [j] * (len(labda) - k)
                p = pont(utak, lab, mez)
                if legjobb is None or p > legjobb[0] + 1e-12:
                    legjobb = (p, utak, lab, mez)
        # A szerepcsere: két mezszámos támadó utat cserél (a futások és a
        # labda útja marad, a lövő más).
        if cserelhet:
            for i in range(len(mez)):
                for j in range(i + 1, len(mez)):
                    if mez[i] is None or mez[j] is None:
                        continue
                    mz = list(mez)
                    mz[i], mz[j] = mz[j], mz[i]
                    p = pont(utak, labda, mz)
                    if legjobb is None or p > legjobb[0] + 1e-12:
                        legjobb = (p, utak, labda, mz)
        if legjobb is None \
                or 100.0 * (legjobb[0] - most) < FINOMITO_MIN_JAVULAS_PP:
            break
        most, utak, labda, mez = legjobb

    valtozasok = []
    for i, (regi, uj) in enumerate(zip(e0["utak"], utak)):
        for k, (a, b) in enumerate(zip(regi, uj)):
            d = math.hypot(b[0] - a[0], b[1] - a[1])
            if d < 0.05:
                continue
            reszek = []
            if abs(b[0] - a[0]) >= 0.3:
                reszek.append("a kapu felé" if abs(b[0] - goal_x)
                              < abs(a[0] - goal_x) else "hátrébb")
            if abs(b[1] - a[1]) >= 0.3:
                reszek.append("befelé" if abs(b[1] - kozep)
                              < abs(a[1] - kozep) else "kifelé")
            nevelo = "az" if i + 1 in (1, 5) else "a"
            m = f"{d:.1f}".replace(".", ",")
            valtozasok.append(
                f"{nevelo[0].upper()}{nevelo[1:]} {i + 1}. támadó "
                f"„{_pont_nev(k, len(uj))}” pontja {m} m-rel "
                + " és ".join(reszek or ["arrébb"]))
    if labda != list(e0["labda"]):
        def ut(lab):
            return " → ".join(f"{v + 1}." for v in lab)
        valtozasok.append(f"A labda útja a kulcs-pozíciókon: "
                          f"{ut(labda)} támadó (eddig {ut(e0['labda'])})")
    if mez != list(e0["mezek"]):
        cserek = [f"{mezszam_nevelovel(m)} "
                  f"{'az' if i + 1 in (1, 5) else 'a'} {i + 1}. támadó "
                  "útját futja"
                  for i, m in enumerate(mez)
                  if m is not None and m != e0["mezek"][i]]
        valtozasok.append("Szerepcsere: " + ", ".join(cserek))
    javulas = round(100.0 * (most - alap), 1)
    if valtozasok:
        verdict = (f"A modell szerint {javulas:.0f} százalékponttal "
                   f"nagyobb lövőhelyzet ({100 * alap:.0f}% → "
                   f"{100 * most:.0f}%), ha "
                   + "; ".join(v[:1].lower() + v[1:] for v in valtozasok)
                   + ".")
    else:
        verdict = ("A modell nem talált jobb változatot: ez a figura "
                   "ennél a falnál a kis módosításoknál nem javul.")
    return {"attackers": [[[round(x, 1), round(y, 1)] for x, y in u]
                          for u in utak],
            "labda": labda,
            "mez": mez,
            "pont_elotte": round(100.0 * alap, 1),
            "pont_utana": round(100.0 * most, 1),
            "javulas_pp": javulas,
            "valtozasok": valtozasok,
            "verdict": verdict}


# ---- Figura-kimenetek: sok lejátszás zajos fallal ---------------------------
# A szimuláció determinisztikus: egy figura egy fal ellen mindig ugyanazt
# adja. A valódi fal viszont hol kilép, hol nem, hol mélyebben áll —
# ezért KIMENET_N lejátszás, mindegyik egy kicsit más fallal: a kilépés
# és a kettőzés a tanult hajlammal mint VALÓSZÍNŰSÉGGEL (vagy kilép, vagy
# nem), a labdakövetés és a mélység kis szórással. Minden lejátszás
# kimenete: eladott labda (egy passz elfogva), gól (a legjobb helyzet
# értéke mint valószínűség) vagy kivédett / mellé. A passz-elfogás a
# passz vonalának KÖZEPÉHEZ legközelebbi védő távolságából — a passzoló
# mellől KIMENET_PASSZOLO_M, az átvevő mellől KIMENET_ATVEVO_M levágva
# (az átvevő őrzője nem a vonalban áll, hanem rajta; a beállóra adott
# labdát nem fogja el, csak nehezíti): KIMENET_ELFOG_M-en belül
# KIMENET_ELFOG_P, kétszer annyin belül a fele, különben az alap.
KIMENET_N = 200
KIMENET_KOVETES_SZORAS = 0.15
KIMENET_MELYSEG_SZORAS_M = 0.4
KIMENET_ELFOG_M = 1.0
KIMENET_ELFOG_P = 0.5
KIMENET_ELFOG_ALAP_P = 0.04
KIMENET_PASSZOLO_M = 1.0
KIMENET_ATVEVO_M = 2.0


def simulate_outcomes(keypoints: list, defense: DefenseModel, *,
                      ball: list | None = None, n: int = KIMENET_N,
                      seed: int = 0,
                      config: TacticsConfig | None = None,
                      tamadas: AttackModel | None = None,
                      mezek: list | None = None) -> dict:
    """Figura-kimenetek: a figura `n` lejátszása zajos fallal (lásd a
    KIMENET_* konstansokat), kimenetenként számolva. `tamadas` +
    `mezek`: a tanult lövőkkel (mint a setplay_3d_match) — a gól
    valószínűsége a helyzetbe érő támadó lövő-szorzójával.

    Edzőileg: a figura "pontszáma" egy szám; ez azt mondja meg, a sok
    lehetséges fal-reakcióból hányszor lesz gól, hányszor védés és
    hányszor eladott labda — "tízből hármat behoz, kettőt elad".

    Visszaad: {"n", "seed", "gol", "vedett", "eladott" (darab),
    "gol_pct", "vedett_pct", "eladott_pct", "atlag_pct" (a legjobb
    helyzet értékének átlaga, %), "verdict"}. Determinisztikus: ugyanaz
    a `seed` ugyanazt adja. ValueError, ha nincs érvényes támadó."""
    import random

    from .decisions import _point_segment_distance

    config = config or TacticsConfig()
    rng = random.Random(seed)
    gol = vedett = eladott = 0
    osszeg = 0.0
    for _ in range(max(1, int(n))):
        fal = replace(
            defense,
            press_rate=1.0 if rng.random() < defense.press_rate else 0.0,
            double_rate=1.0 if rng.random() < defense.double_rate else 0.0,
            lateral_gain=max(0.0, min(1.0, defense.lateral_gain
                                      + rng.gauss(0.0, KIMENET_KOVETES_SZORAS))),
            line_depth_m=max(GOAL_AREA_RADIUS_M, defense.line_depth_m
                             + rng.gauss(0.0, KIMENET_MELYSEG_SZORAS_M)))
        sim, e = setplay_3d_match(keypoints, fal, ball=ball, config=config,
                                  tamadas=tamadas, mezek=mezek)
        osszeg += e["best_shot_value"]
        # Passz-elfogás: a passz indulásának kockáján a védők a szakaszhoz.
        fps = sim.meta.fps or FIGURA_3D_FPS
        elfogva = False
        # (a j. passz a j. labdás-váltás kulcs-pozíciójára érkezik)
        valtasok = [i for i in range(1, len(e["labda"]))
                    if e["labda"][i] != e["labda"][i - 1]]
        for j, (x1, y1, x2, y2) in enumerate(e["passzok"]):
            if j >= len(valtasok):
                break
            t_erk = e["kulcs_t"][valtasok[j]]
            idx = min(len(sim.frames) - 1, max(0, int(round(t_erk * fps))))
            vedok = [p for p in sim.frames[idx].players
                     if p.team == Team.AWAY and p.role != "kapus"]
            hossz = math.hypot(x2 - x1, y2 - y1)
            kozep = hossz - KIMENET_PASSZOLO_M - KIMENET_ATVEVO_M
            if not vedok or kozep <= 0.5:
                pe = KIMENET_ELFOG_ALAP_P      # kézből kézbe: csak az alap
            else:
                ux, uy = (x2 - x1) / hossz, (y2 - y1) / hossz
                ax, ay = x1 + ux * KIMENET_PASSZOLO_M, y1 + uy * KIMENET_PASSZOLO_M
                bx, by = x2 - ux * KIMENET_ATVEVO_M, y2 - uy * KIMENET_ATVEVO_M
                d = min(_point_segment_distance(p.x, p.y, ax, ay, bx, by)
                        for p in vedok)
                pe = (KIMENET_ELFOG_P if d <= KIMENET_ELFOG_M
                      else KIMENET_ELFOG_P / 2 if d <= 2 * KIMENET_ELFOG_M
                      else KIMENET_ELFOG_ALAP_P)
            if rng.random() < pe:
                elfogva = True
                break
        if elfogva:
            eladott += 1
        elif rng.random() < e["best_shot_value"]:
            gol += 1
        else:
            vedett += 1
    ossz = gol + vedett + eladott
    verdict = (f"{ossz} lejátszásból {gol} gól, {vedett} kivédett vagy "
               f"mellé, {eladott} eladott labda — tízből "
               f"{round(10 * gol / ossz)} gól")
    return {"n": ossz, "seed": seed, "gol": gol, "vedett": vedett,
            "eladott": eladott,
            "gol_pct": round(100.0 * gol / ossz, 1),
            "vedett_pct": round(100.0 * vedett / ossz, 1),
            "eladott_pct": round(100.0 * eladott / ossz, 1),
            "atlag_pct": round(100.0 * osszeg / ossz, 1),
            "verdict": verdict}


# ---- Élő figura-ajánló: meccs közben, az addig látott fal ellen ------------
# Ezekben a percekben szól (a meccs kezdetétől mért játékidő), ha az
# addigi kockákból már tanulható a fal: legalább ennyi védekező kocka
# (mintaszám) kell. Csak az addigi kockákat nézi — előre nem lát.
LIVE_AJANLO_PERCEK = (15, 30, 45)
LIVE_AJANLO_MIN_KOCKA = 300


def live_figure_suggestions(match: Match, figurak: list,
                            config: TacticsConfig | None = None,
                            tamadas: dict | None = None) -> dict:
    """Élő figura-ajánló: a LIVE_AJANLO_PERCEK perceiben az addig látott
    fal ellen (DefenseModel.learn a kezdettől a percig tartó kockákon)
    rangsorolja a `figurak` listát (rank_playbook), és az első helyezettet
    mondja — mindkét csapat falára (a másik kispadnak szól).

    `tamadas` ({"home" / "away": AttackModel} — a fal oldala szerint az
    ELLENE támadó csapat tanult lövői, pl. a szezon korábbi meccseiből):
    a mezszámmal mentett figurák záró lövőjének szorzója is számít;
    ahol nincs, az addig látott kockákból tanul (okszerű).

    Edzőileg: a félidőben nem a teljes meccs, hanem az addig látott fal
    alapján kell dönteni — ez azt mondja meg, az eddigiek szerint melyik
    figuránk érne a legtöbbet ellenük. Okszerű: a percig látottakból, a
    későbbi kockák nélkül.

    Visszaad: {"alerts": [{"t" (kocka), "t_s", "perc", "team" (a VÉDŐ
    oldal, akinek a fala ellen), "team_name", "name", "pont_pct",
    "alap_pct", "sablon", "lovo_mez", "lovo_szorzo", "text"}, …]} t
    szerint; üres, ha nincs figura, vagy a fal még nem tanulható."""
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    alerts = []
    if not figurak or not match.frames:
        return {"alerts": alerts}
    t0 = match.frames[0].t
    for perc in LIVE_AJANLO_PERCEK:
        hatar = t0 + int(round(perc * 60 * fps))
        eddig = [f for f in match.frames if f.t <= hatar]
        if len(eddig) < 2 or eddig[-1].t < hatar - fps:
            continue      # a meccs még nem ért el idáig
        resz = Match(meta=match.meta, frames=eddig)
        for side in ("home", "away"):
            team = Team.HOME if side == "home" else Team.AWAY
            minta = _tanulas_minta(resz, team, config)
            if minta["kockak"] < LIVE_AJANLO_MIN_KOCKA:
                continue
            fal = DefenseModel._modell_mintabol(minta)
            # A fal ellen támadó csapat lövői: a megadott modell, vagy az
            # addig látott kockákból.
            tam = (tamadas or {}).get(side)
            if tam is None:
                tam = AttackModel.learn(
                    resz, Team.AWAY if side == "home" else Team.HOME, config)
            r = rank_playbook(figurak, fal, config=config, tamadas=tam)
            if not r["figurak"]:
                continue
            b = r["figurak"][0]
            nev = (match.meta.home_team if side == "home"
                   else match.meta.away_team)
            mibol = ("az alap-figurák közül a" if b["sablon"]
                     else "a figuráink közül a")
            alerts.append({
                "t": hatar, "t_s": round(hatar / fps, 1), "perc": perc,
                "team": side, "team_name": nev, "name": b["name"],
                "pont_pct": b["pont_pct"], "alap_pct": b["alap_pct"],
                "sablon": b["sablon"],
                "lovo_mez": b["lovo_mez"], "lovo_szorzo": b["lovo_szorzo"],
                "text": (f"Figura-ajánló ({perc}. perc): {nev} eddig "
                         f"látott fala ellen {mibol} „{b['name']}” ér a "
                         f"legtöbbet — {b['pont_pct']:.0f}% lövőhelyzet"
                         f"{lovo_zaradek(b, elo=' — ')} "
                         f"(alap fal: {b['alap_pct']:.0f}%)")})
    alerts.sort(key=lambda a: (a["t"], a["team"]))
    return {"alerts": alerts}


# ---- Kit kinek: a lövőik × a falunk védői -----------------------------------
# Az ő tanult lövőik közül a távolról vagy közepes távolságból veszélyes
# (a sáv szorzója legalább KITKINEK_LOVO_SZORZO) lövők, a lövőhelyük
# SÁVJA (a pálya szélessége KITKINEK_SAVOK egyenlő sávra osztva — a
# leggyakoribb sáv, legalább KITKINEK_MIN_LOVES lövésből), és a falunk
# védője, aki a tanult helye (y) szerint abban a sávban áll
# (DefenseModel.vedok). Ha az ott álló védő ritkán lép ki (a saját
# hajlama KITKINEK_LASSU alatt vagy ismeretlen) és van kilépő védőnk
# (legalább KITKINEK_KILEPO), a modell cserét javasol: a kilépő álljon
# a lövővel szemben. A sáv neve oldal-független ("szélső" / "középső"):
# a védőt a mezszáma nevezi meg, nem a bal / jobb.
KITKINEK_LOVO_SZORZO = 1.1
KITKINEK_SAVOK = 3
KITKINEK_MIN_LOVES = 3
KITKINEK_LASSU = 0.3
KITKINEK_KILEPO = 0.5
KITKINEK_SAV_NEV = {0: "szélső", 1: "középső", 2: "szélső"}


def lovo_sav_index(y: float) -> int:
    """A lövőhely (vagy a védő helye) sávja a pálya szélességén (0..
    KITKINEK_SAVOK−1) — a nyers y-ból, mindkét csapatra ugyanúgy (egy
    pályán állnak, szemben)."""
    return int(min(KITKINEK_SAVOK - 1,
                   max(0, y // (COURT_WIDTH_M / KITKINEK_SAVOK))))


def _lovo_sav_minta(match: Match, attacking_team: Team,
                    config: TacticsConfig) -> dict:
    """A lövők sáv-mintája: {mezszám: [lövés sávonként]} — a csapat
    mezszámos lövései a lövőhely y-sávja szerint. Meccsek közt
    összeadható."""
    out: dict = {}
    for mez, sh in _lovesek_mezszammal(match, attacking_team, config):
        out.setdefault(mez, [0] * KITKINEK_SAVOK)[lovo_sav_index(sh["y"])] += 1
    return out


def shooter_defender_pairs(tamadas, savok: dict, vedok: list) -> list:
    """Kit kinek a kész modellekből: `tamadas` (AttackModel — az ő
    lövőik), `savok` (a lövőik sáv-mintája, _lovo_sav_minta alakban,
    mezszám-kulccsal), `vedok` (a falunk védői, DefenseModel.vedok
    alakban). Visszaad: [{"lovo_mez", "sav" (index), "sav_nev", "band"
    ("far" / "mid"), "szorzo", "lovesek" (a sávban), "vedo_mez",
    "vedo_kilepes" (0..1 vagy None), "javasolt_mez", "javasolt_kilepes",
    "verdict"}, …] a szorzó szerint csökkenőben (holtversenyben
    mezszám); üres, ha nincs veszélyes lövő."""
    parok = []
    if tamadas is None:
        return parok
    for mez, bands in tamadas.lovok.items():
        jeloltek = [(float(bands[b]), b) for b in ("far", "mid") if b in bands]
        if not jeloltek:
            continue
        szorzo, band = max(jeloltek, key=lambda r: (r[0], r[1]))
        if szorzo < KITKINEK_LOVO_SZORZO:
            continue
        sav_db = list(savok.get(mez) or savok.get(str(mez)) or [])
        if not sav_db or max(sav_db) < KITKINEK_MIN_LOVES:
            continue
        sav = max(range(len(sav_db)), key=lambda i: (sav_db[i], -i))
        kozep = (sav + 0.5) * COURT_WIDTH_M / KITKINEK_SAVOK
        ott = [v for v in vedok if lovo_sav_index(v["y"]) == sav]
        vedo = (min(ott, key=lambda v: (abs(v["y"] - kozep), v["mez"]))
                if ott else None)
        javasolt = None
        if vedo is not None and (vedo.get("press_rate") is None
                                 or vedo["press_rate"] < KITKINEK_LASSU):
            kilepok = [v for v in vedok
                       if v.get("press_rate") is not None
                       and v["press_rate"] >= KITKINEK_KILEPO
                       and v["mez"] != vedo["mez"]]
            if kilepok:
                javasolt = max(kilepok, key=lambda v: (v["press_rate"],
                                                       -v["mez"]))
        sor = {"lovo_mez": int(mez), "sav": sav,
               "sav_nev": KITKINEK_SAV_NEV.get(sav, "középső"),
               "band": band, "szorzo": round(szorzo, 3),
               "lovesek": int(sav_db[sav]),
               "vedo_mez": vedo["mez"] if vedo else None,
               "vedo_kilepes": vedo.get("press_rate") if vedo else None,
               "javasolt_mez": javasolt["mez"] if javasolt else None,
               "javasolt_kilepes": (javasolt["press_rate"]
                                    if javasolt else None)}
        sz = f"{szorzo:.1f}".replace(".", ",")
        v = (f"{mezszam_nevelovel(sor['lovo_mez'])} ({KAPUS_SAV_NEV[band]} "
             f"{sz}× annyit lő be, mint amennyit a helyzetei érnek) a "
             f"{sor['sav_nev']} sávból lő ({sor['lovesek']} lövés)")
        if vedo is None:
            v += " — a falunkban ott nincs tanult védő"
        else:
            vk = vedo.get("press_rate")
            v += f"; ott {mezszam_nevelovel(vedo['mez'])} áll"
            if javasolt is not None:
                v += (f", aki " + (f"ritkán lép ki ({vk * 100:.0f}%)"
                                   if vk is not None else
                                   "kilépését nem ismerjük")
                      + f" — {mezszam_nevelovel(javasolt['mez'])} "
                      f"(kilépő, {javasolt['press_rate'] * 100:.0f}%) "
                      "álljon vele szemben")
            elif vk is not None and vk >= KITKINEK_LASSU:
                v += f", aki rendre kilép ({vk * 100:.0f}%) — jó a párosítás"
            else:
                v += (" — nincs kilépő védőnk, akit elé állíthatnánk: a "
                      "sáv védője lépjen ki rá")
        sor["verdict"] = v
        parok.append(sor)
    parok.sort(key=lambda r: (-r["szorzo"], r["lovo_mez"]))
    return parok


def shooter_defender_matchup(match: Match,
                             config: TacticsConfig | None = None) -> dict:
    """Kit kinek — csapatonként, a VÉDEKEZŐ oldal szemszögéből: az
    ellenfél távolról / közepes távolságból veszélyes lövői (az ő tanult
    lövőik, AttackModel.learn), a lövőhelyük sávja, és a falunk védője,
    aki ott áll (DefenseModel.learn → vedok) — csere-javaslattal a
    kilépő védőre (shooter_defender_pairs).

    Edzőileg: az emberfogás-kérdés — "ki álljon a 9-essel szemben?" A
    távoli lövőt az a védő tartja, aki rendre kilép; ha a sávjában a
    lassú kilépő áll, a fal sorrendjét kell cserélni.

    Visszaad csapatonként: {"parok": [...], "verdict"} — a verdict az
    első pár mondata, None, ha nincs veszélyes lövőjük vagy tanult
    védőnk (kevés minta — a modell nem találgat)."""
    config = config or TacticsConfig()
    out = {}
    for side, team, masik in (("home", Team.HOME, Team.AWAY),
                              ("away", Team.AWAY, Team.HOME)):
        vedok = DefenseModel.learn(match, team, config).vedok
        parok = (shooter_defender_pairs(
            AttackModel.learn(match, masik, config),
            _lovo_sav_minta(match, masik, config), vedok) if vedok else [])
        out[side] = {"parok": parok,
                     "verdict": parok[0]["verdict"] if parok else None}
    return out


# ---- Engedett lövő: kire NE lépjünk ki -------------------------------------
# A kit-kinek párja. Ott a távolról VESZÉLYES lövő elé állítunk kilépő
# védőt; itt az, akire a kilépés pazarlás: a tanult lövő-modellben
# (AttackModel) a lövő MINDEN tanult távoli / közepes sávja legfeljebb
# LOVO_GYENGE_SZORZO — a helyzeteinél kevesebbet lő be onnan. Ellene a
# fal maradjon hátul: a távoli lövése ajándék, a kilépés mögé viszont
# betörhet — főleg, ha közelről legalább KITKINEK_LOVO_SZORZO (ekkor a
# mondat külön szól a betörés zárásáról). A tanult sáv legalább
# LOVO_MIN_LOVES lövés; egy ilyen lövő sem → üres lista, a modell nem
# találgat.
ENGEDETT_SAVOK = ("far", "mid")


def allowed_shooters_from(tamadas, minta: dict) -> list:
    """Engedett lövők a kész modellből: `tamadas` (AttackModel — az ő
    lövőik), `minta` (a nyers lövő-minta, _lovo_minta alakban, mezszám-
    kulccsal — a lövésszámhoz és a gólhoz). Visszaad: [{"mez", "sav"
    ("far" / "mid" — a leggyengébb), "szorzo", "lovesek", "gol", "kozel"
    (a közeli sáv szorzója vagy None), "betores" (igaz, ha közelről
    veszélyes), "verdict"}, …] a szorzó szerint növekvőben (a leggyengébb
    távoli lövő elöl, holtversenyben mezszám); üres, ha nincs ilyen."""
    ki: list = []
    if tamadas is None:
        return ki
    for mez, bands in tamadas.lovok.items():
        tavoli = [(float(bands[b]), b) for b in ENGEDETT_SAVOK if b in bands]
        if not tavoli or max(v for v, _ in tavoli) > LOVO_GYENGE_SZORZO:
            continue
        szorzo, sav = min(tavoli)
        n, gol, _xg = ((minta.get(mez) or minta.get(str(mez)) or {})
                       .get(sav) or [0, 0, 0.0])
        kozel = bands.get("close")
        betores = kozel is not None and float(kozel) >= KITKINEK_LOVO_SZORZO
        sor = {"mez": int(mez), "sav": sav, "szorzo": round(szorzo, 3),
               "lovesek": int(n), "gol": int(gol),
               "kozel": round(float(kozel), 3) if kozel is not None else None,
               "betores": bool(betores)}
        sz = f"{szorzo:.1f}".replace(".", ",")
        v = (f"{mezszam_nevelovel(sor['mez'])} ellen nem kell kilépni: "
             f"{KAPUS_SAV_NEV[sav]} {sz}× annyit lő be, mint amennyit a "
             f"helyzetei érnek ({sor['lovesek']} lövés, {sor['gol']} gól) — "
             f"a {UTOLSO_LOVES_SAV_JELZO[sav]} lövése ajándék")
        if betores:
            kz = f"{float(kozel):.1f}".replace(".", ",")
            v += f", a betörését viszont zárni kell: közelről {kz}×"
        else:
            v += ", a fal maradjon hátul vele szemben"
        sor["verdict"] = v
        ki.append(sor)
    ki.sort(key=lambda r: (r["szorzo"], r["mez"]))
    return ki


def allowed_shooters(match: Match, config: TacticsConfig | None = None) -> dict:
    """Engedett lövő — csapatonként, a VÉDEKEZŐ oldal szemszögéből: az
    ellenfél lövői, akik távolról / közepes távolságból a helyzeteiknél
    érdemben kevesebbet lőnek be (az ő tanult lövőik, AttackModel.learn:
    minden tanult távoli sávjuk legfeljebb LOVO_GYENGE_SZORZO) — rájuk
    nem kell kilépni (allowed_shooters_from).

    Edzőileg: a kit-kinek fordítottja — "kire NE lépjünk ki?" A gyenge
    távoli lövőt hagyni kell lőni: a kilépés mögé betörne, a lövése
    viszont ajándék. Ha közelről veszélyes (KITKINEK_LOVO_SZORZO
    felett), a mondat a betörés zárásáról is szól.

    Visszaad csapatonként: {"lovok": [...], "verdict"} — a verdict az
    első (leggyengébb) lövő mondata, None, ha nincs ilyen lövőjük (kevés
    minta — a modell nem találgat)."""
    config = config or TacticsConfig()
    out = {}
    for side, masik in (("home", Team.AWAY), ("away", Team.HOME)):
        lovok = allowed_shooters_from(AttackModel.learn(match, masik, config),
                                      _lovo_minta(match, masik, config))
        out[side] = {"lovok": lovok,
                     "verdict": lovok[0]["verdict"] if lovok else None}
    return out


# ---- Lövés-elosztás: ki lő túl sokat és ki túl keveset ---------------------
# Az utolsó lövés párja a TELJES meccsre: a tanult lövő × sáv párosok
# értéke ellenük (_lovo_parosok: xG a sáv képviselő-helyén × lövő-szorzó
# × az ő kapusuk sáv-szorzója) szemben a TÉNYLEGES lövés-részesedéssel
# (a nyers lövő-minta: ki honnan hányat lőtt). Az átlagos részesedés
# 100% / a tanult párosok száma. Aki a legtöbbet ér, de az átlagnál
# kevesebbet lő → "többet lőhetne"; aki az átlagnál többet lő, pedig
# legalább LE_ELTERES várható góllal kevesebbet ér lövésenként →
# "kevesebbet". Legalább LE_MIN_LOVES mezszámos lövés és LE_MIN_PAROS
# tanult páros kell (különben None — a modell nem találgat); ha nincs
# ilyen pár, "kiegyensúlyozott".
LE_MIN_LOVES = 10
LE_MIN_PAROS = 2
LE_ELTERES = 0.05


def shot_allocation_from(tamadas, kapus: dict | None, minta: dict) -> dict | None:
    """Lövés-elosztás a kész modellekből: `tamadas` (AttackModel — a
    lövők), `kapus` (a SZEMKÖZTI kapus sávonkénti szorzója; üres =
    átlagos), `minta` (a nyers lövő-minta, _lovo_minta alakban, mezszám-
    kulccsal — a részesedéshez). Visszaad: {"parosok": [{"mez", "sav",
    "sav_nev", "ertek", "lovesek", "arany_pct"}, …] az érték szerint
    csökkenőben, "lovesek" (összes mezszámos lövés), "atlag_pct",
    "tobbet" / "kevesebbet" ({"mez", "sav", "sav_nev", "ertek", "lovesek",
    "arany_pct"} vagy None), "dontes" (igaz, ha mindkettő megvan),
    "verdict"} — None, ha kevés a minta."""
    parosok = _lovo_parosok(tamadas, kapus)
    if len(parosok) < LE_MIN_PAROS:
        return None
    ossz = 0
    for savok in minta.values():
        for v in savok.values():
            ossz += int(v[0])
    if ossz < LE_MIN_LOVES:
        return None
    sorok = []
    for p in parosok:
        n = int(((minta.get(p["mez"]) or minta.get(str(p["mez"])) or {})
                 .get(p["sav"]) or [0, 0, 0.0])[0])
        sorok.append({"mez": p["mez"], "sav": p["sav"], "sav_nev": p["sav_nev"],
                      "ertek": p["ertek"], "lovesek": n,
                      "arany_pct": round(100.0 * n / ossz, 1)})
    atlag = round(100.0 / len(sorok), 1)
    tobbet = next((s for s in sorok if s["arany_pct"] < atlag), None)
    kevesebbet = None
    if tobbet is not None:
        kevesebbet = next((s for s in reversed(sorok)
                           if s["arany_pct"] > atlag
                           and s["ertek"] <= tobbet["ertek"] - LE_ELTERES),
                          None)
    dontes = tobbet is not None and kevesebbet is not None

    def szam(v):
        return f"{v:.2f}".replace(".", ",")

    if dontes:
        verdict = (f"többet lőhetne {mezszam_nevelovel(tobbet['mez'])} "
                   f"{tobbet['sav_nev']} ({szam(tobbet['ertek'])} várható gól "
                   f"lövésenként, eddig {tobbet['lovesek']} lövés — "
                   f"{tobbet['arany_pct']:.0f}%), kevesebbet "
                   f"{mezszam_nevelovel(kevesebbet['mez'])} "
                   f"{kevesebbet['sav_nev']} ({szam(kevesebbet['ertek'])}; "
                   f"{kevesebbet['lovesek']} lövés — "
                   f"{kevesebbet['arany_pct']:.0f}%)")
    else:
        verdict = (f"a lövés-elosztás a modell szerint kiegyensúlyozott "
                   f"({ossz} lövés, {len(sorok)} tanult páros)")
    return {"parosok": sorok, "lovesek": ossz, "atlag_pct": atlag,
            "tobbet": tobbet, "kevesebbet": kevesebbet if dontes else None,
            "dontes": dontes, "verdict": verdict}


def shot_allocation(match: Match, config: TacticsConfig | None = None) -> dict:
    """Lövés-elosztás — csapatonként, a TÁMADÓ oldal szemszögéből: a
    csapat tanult lövői (AttackModel.learn) × a SZEMKÖZTI kapus tanult
    sávjai (_kapus_tanul) szerint ki ér a legtöbbet lövésenként, és ehhez
    képest ki lőtt túl sokat vagy túl keveset (shot_allocation_from a
    nyers lövő-mintával).

    Edzőileg: a lövés-választás csapat-szinten — "kinek kell többet
    lőnie ellenük, és ki lő feleslegesen". Az utolsó lövés egy labdáról
    szól; ez a teljes meccs lövés-elosztásáról.

    Visszaad csapatonként: shot_allocation_from kimenete vagy None
    (kevés minta — a modell nem találgat)."""
    config = config or TacticsConfig()
    out = {}
    for side, team, masik in (("home", Team.HOME, Team.AWAY),
                              ("away", Team.AWAY, Team.HOME)):
        out[side] = shot_allocation_from(
            AttackModel.learn(match, team, config),
            _kapus_tanul(match, masik, config),
            _lovo_minta(match, team, config))
    return out


def shooter_bands_from(minta: dict) -> list:
    """Egy lövő sávonkénti képe a nyers mintájából (`minta` = {sáv:
    [lövés, gól, xG]} — egy meccs vagy több meccs összege): [{"sav",
    "sav_nev", "lovesek", "gol", "xg", "szorzo"}, …] közelről, közepes,
    távolról sorrendben, csak a lövéses sávok; a szorzó a tanult
    (_lovo_szorzo: LOVO_MIN_LOVES lövéstől), kevesebbnél None."""
    szorzo = (_lovo_szorzo({0: minta}).get(0)) or {}
    out = []
    for sav in ("close", "mid", "far"):
        if sav not in minta:
            continue
        n, gol, xg = minta[sav]
        out.append({"sav": sav, "sav_nev": KAPUS_SAV_NEV[sav],
                    "lovesek": int(n), "gol": int(gol),
                    "xg": round(float(xg), 2), "szorzo": szorzo.get(sav)})
    return out


def keeper_bands_from(minta: dict) -> list:
    """Egy kapus sávonkénti képe a nyers mintájából (`minta` = {sáv:
    [kaputra érkezett, védett]}): [{"sav", "sav_nev", "kaputra", "vedes",
    "szorzo"}, …] közelről, közepes, távolról sorrendben; a szorzó a
    tanult (_kapus_szorzo: KAPUS_MIN_LOVES lövéstől — 1 felett az
    átlagnál több gólt kap onnan), kevesebbnél None."""
    szorzo = _kapus_szorzo(minta)
    out = []
    for sav in ("close", "mid", "far"):
        if sav not in minta:
            continue
        faced, saves = minta[sav]
        out.append({"sav": sav, "sav_nev": KAPUS_SAV_NEV[sav],
                    "kaputra": int(faced), "vedes": int(saves),
                    "szorzo": szorzo.get(sav)})
    return out

# ---- Egy játékos lövő-modellje ----------------------------------------------

def player_shooter_profile(match: Match, player_id: int,
                           config: TacticsConfig | None = None) -> dict | None:
    """Egy játékos tanult lövő-modellje egy meccsről (a Döntések panel
    játékos-lapjához): a mezszáma és a csapata a kockákból; sávonként a
    nyers minta (lövés, gól, xG — _lovo_minta) és a tanult szorzó
    (_lovo_szorzo: LOVO_MIN_LOVES lövéstől; kevesebbnél None — a modell
    nem találgat); a lövés-elosztásban (shot_allocation) a tanult
    sávjainak részesedése és értéke, és hogy ő-e a "többet lőhetne" /
    "kevesebbet" szereplője.

    Edzőileg: a játékos saját képe — honnan lő be többet a helyzeteinél,
    honnan kevesebbet, és a csapat lövéseiből mennyit vállal.

    Visszaad: {"jersey", "team", "savok": [{"sav", "sav_nev", "lovesek",
    "gol", "xg", "szorzo"}, …] (közelről, közepes, távolról sorrendben,
    csak a lövéses sávok), "felirat", "elosztas": {"szerep" ("tobbet" /
    "kevesebbet" / None), "parosok": [{"sav", "sav_nev", "ertek",
    "arany_pct"}], "verdict"} vagy None} — None, ha a játékosnak nincs
    mezszáma vagy mezszámos lövése."""
    config = config or TacticsConfig()
    jersey = team = None
    for f in match.frames:
        for p in f.players:
            if p.track_id == player_id and p.jersey_number is not None:
                jersey, team = int(p.jersey_number), p.team
                break
        if jersey is not None:
            break
    if jersey is None or team not in (Team.HOME, Team.AWAY):
        return None
    minta = (_lovo_minta(match, team, config).get(jersey)) or {}
    if not minta:
        return None
    savok = shooter_bands_from(minta)

    def sz(v, d=1):
        return f"{v:.{d}f}".replace(".", ",")

    reszek = []
    for s in savok:
        r = (f"{s['sav_nev']} {s['lovesek']} lövés, {s['gol']} gól "
             f"({sz(s['xg'])} várható)")
        r += (f" — {sz(s['szorzo'])}× annyit lő be, mint amennyit a "
              "helyzetei érnek" if s["szorzo"] is not None
              else " — kevés minta")
        reszek.append(r)
    elosztas = None
    try:
        le = shot_allocation(match, config).get(team.value)
    except Exception:
        le = None
    if le:
        szerep = ("tobbet" if (le.get("tobbet") or {}).get("mez") == jersey
                  else "kevesebbet"
                  if (le.get("kevesebbet") or {}).get("mez") == jersey
                  else None)
        elosztas = {"szerep": szerep,
                    "parosok": [{k: r[k] for k in ("sav", "sav_nev", "ertek",
                                                   "arany_pct")}
                                for r in le["parosok"] if r["mez"] == jersey],
                    "verdict": le["verdict"]}
    return {"jersey": jersey, "team": team.value, "savok": savok,
            "felirat": "; ".join(reszek), "elosztas": elosztas}


# ---- A lövő-modell próbája: előre jelez-e ----------------------------------
# A csapat meccsei időrendben: minden meccs lövéseit a KORÁBBI meccsekből
# tanult lövő-modell (AttackModel) becsli — lövő × sáv csoportonként a
# becsült gól = a csoport xG-je × a tanult szorzó —, és két viszonyítással
# vetjük össze: a nyers xG-vel és a CSAPAT korábbi befejezésével (egy
# szorzó mindenkire, ugyanúgy simítva és szorítva, mint a lövőé). Az
# összevetés az abszolút eltérés a csoport tényleges góljaitól,
# csoportonként összegezve. Csak az a csoport számít, ahol a korábbi
# meccsekből van tanult szorzó. Az EGYÉNI képesség akkor látszik, ha a
# lövő-modell a csapat-szorzót is veri: különben a javulás a csapat
# befejezése (vagy a helyzet-érték torzítása), nem az egyes lövőké.
# Legalább PROBA_MIN_CSOPORT csoport kell az ítélethez; a PROBA_ITELET_PCT-
# nél kisebb különbség "nagyjából ugyanolyan pontos".
PROBA_MIN_CSOPORT = 5
PROBA_ITELET_PCT = 5.0


def _csapat_szorzo(minta: dict) -> float:
    """A csapat egyetlen befejezési szorzója a (összeadott) lövő-mintából
    — mint a lövőé (_lovo_szorzo): a gól és az xG hányadosa, LOVO_SULY
    átlagos értékű lövéssel simítva, a LOVO_SZORZO sávba szorítva; 1, ha
    nincs lövés."""
    n = gol = xg = 0.0
    for savok in minta.values():
        for v in savok.values():
            n += float(v[0])
            gol += float(v[1])
            xg += float(v[2])
    if n <= 0 or xg <= 0:
        return 1.0
    atlag = xg / n
    arany = (gol + LOVO_SULY * atlag) / (xg + LOVO_SULY * atlag)
    return max(LOVO_SZORZO_MIN, min(LOVO_SZORZO_MAX, arany))


def shooter_model_backtest(mintak: list) -> dict | None:
    """A lövő-modell próbája egy csapat meccsein: `mintak` — a csapat
    meccsenkénti nyers lövő-mintái IDŐRENDBEN ([{mez: {sáv: [lövés, gól,
    xG]}}, …] — _lovo_minta vagy player_model_sample["lovo"] alakban).
    A k. meccs csoportjait az első k−1 meccsből tanult modell becsli.

    Edzőileg: a bizalom kérdése — érdemes-e a "a 7-es távolról 1,3×"
    mondatra építeni a meccstervet? Ha a korábbi meccsekből tanult EGYÉNI
    szorzó a következő meccsen pontosabban becsüli a gólokat, mint a nyers
    helyzet-érték ÉS a csapat átlagos befejezése, a lövő-modell valódi
    egyéni képességet mér, nem véletlent.

    Visszaad: {"meccsek", "csoportok" (hány lövő × sáv csoportot becsült
    tanult szorzóval), "lovesek", "xg_hiba", "csapat_hiba",
    "modell_hiba" (az abszolút eltérések összege, gólban), "javulas_pct"
    (a modell hibája mennyivel kisebb, mint a nyers xG-é), "egyeni_pct"
    (mennyivel kisebb, mint a csapat-szorzóé), "verdict"} — None, ha
    kevesebb mint PROBA_MIN_CSOPORT csoport becsülhető (kevés meccs vagy
    lövés)."""
    csoportok = 0
    lovesek = 0
    xg_hiba = 0.0
    csapat_hiba = 0.0
    modell_hiba = 0.0
    for k in range(1, len(mintak)):
        elozo = _lovo_mintak_osszege(mintak[:k])
        tam = AttackModel._modell_mintabol(elozo)
        csz = _csapat_szorzo(elozo)
        for mez, savok in sorted((mintak[k] or {}).items(),
                                 key=lambda kv: int(kv[0])):
            tanult = tam.lovok.get(int(mez)) or {}
            for sav, (n, gol, xg) in sorted(savok.items()):
                if sav not in tanult:
                    continue
                csoportok += 1
                lovesek += int(n)
                xg_hiba += abs(float(gol) - float(xg))
                csapat_hiba += abs(float(gol) - float(xg) * csz)
                modell_hiba += abs(float(gol) - float(xg) * float(tanult[sav]))
    if csoportok < PROBA_MIN_CSOPORT or xg_hiba <= 0:
        return None
    javulas = round(100.0 * (xg_hiba - modell_hiba) / xg_hiba, 1)
    egyeni = (round(100.0 * (csapat_hiba - modell_hiba) / csapat_hiba, 1)
              if csapat_hiba > 0 else 0.0)
    alap = (f"({csoportok} lövő × sáv csoport, {lovesek} lövés, "
            f"{len(mintak)} meccs)")
    eleje = ("a korábbi meccsekből tanult lövő-modell a következő meccs "
             "góljait ")
    if javulas >= PROBA_ITELET_PCT and egyeni >= PROBA_ITELET_PCT:
        verdict = (f"{eleje}{javulas:.0f}%-kal pontosabban becsülte, mint a "
                   f"nyers várható gól, és {egyeni:.0f}%-kal, mint a csapat "
                   f"átlagos befejezése {alap} — az egyéni szorzókra lehet "
                   "építeni")
    elif javulas >= PROBA_ITELET_PCT:
        verdict = (f"{eleje}{javulas:.0f}%-kal pontosabban becsülte, mint a "
                   "nyers várható gól, de a csapat átlagos befejezésénél nem "
                   f"jobban {alap} — a különbség a csapat befejezése, nem "
                   "az egyes lövőké: az egyéni szorzót óvatosan kell olvasni")
    elif javulas <= -PROBA_ITELET_PCT:
        verdict = (f"{eleje}{-javulas:.0f}%-kal pontatlanabbul becsülte, "
                   f"mint a nyers várható gól {alap} — a lövők formája "
                   "meccsről meccsre változik, a szorzót óvatosan kell "
                   "olvasni")
    else:
        verdict = (f"{eleje}nagyjából ugyanolyan pontosan becsülte, mint a "
                   f"nyers várható gól {alap}")
    return {"meccsek": len(mintak), "csoportok": csoportok,
            "lovesek": lovesek, "xg_hiba": round(xg_hiba, 2),
            "csapat_hiba": round(csapat_hiba, 2),
            "modell_hiba": round(modell_hiba, 2), "javulas_pct": javulas,
            "egyeni_pct": egyeni, "verdict": verdict}


def shooter_model_backtest_summary(sorok: list) -> dict | None:
    """Több csapat próbájának (shooter_model_backtest sorai) összege: a
    csoportok, a lövések és a két hiba összeadva, a javulás az összegből
    — {"csapatok", "csoportok", "lovesek", "xg_hiba", "modell_hiba",
    "javulas_pct", "verdict"}; None, ha nincs sor."""
    sorok = [r for r in (sorok or []) if r]
    if not sorok:
        return None
    xh = sum(float(r["xg_hiba"]) for r in sorok)
    ch = sum(float(r.get("csapat_hiba", r["xg_hiba"])) for r in sorok)
    mh = sum(float(r["modell_hiba"]) for r in sorok)
    cs = sum(int(r["csoportok"]) for r in sorok)
    lv = sum(int(r["lovesek"]) for r in sorok)
    javulas = round(100.0 * (xh - mh) / xh, 1) if xh > 0 else 0.0
    egyeni = round(100.0 * (ch - mh) / ch, 1) if ch > 0 else 0.0
    irany = ("pontosabban" if javulas >= PROBA_ITELET_PCT else
             "pontatlanabbul" if javulas <= -PROBA_ITELET_PCT else
             "nagyjából ugyanolyan pontosan")
    mennyi = (f"{abs(javulas):.0f}%-kal " if irany != "nagyjából ugyanolyan "
              "pontosan" else "")
    egyeni_mondat = (f", és {egyeni:.0f}%-kal, mint a csapatok átlagos "
                     "befejezése" if javulas >= PROBA_ITELET_PCT
                     and egyeni >= PROBA_ITELET_PCT else
                     ", de a csapatok átlagos befejezésénél nem jobban"
                     if javulas >= PROBA_ITELET_PCT else "")
    return {"csapatok": len(sorok), "csoportok": cs, "lovesek": lv,
            "xg_hiba": round(xh, 2), "csapat_hiba": round(ch, 2),
            "modell_hiba": round(mh, 2), "javulas_pct": javulas,
            "egyeni_pct": egyeni,
            "verdict": (f"a könyvtár {len(sorok)} csapatán a korábbi "
                        f"meccsekből tanult lövő-modell a következő meccs "
                        f"góljait {mennyi}{irany} becsülte, mint a nyers "
                        f"várható gól{egyeni_mondat} ({cs} lövő × sáv "
                        f"csoport, {lv} lövés)")}


# ---- A kapus-modell próbája --------------------------------------------------
# Mint a lövőké: a csapat meccsei időrendben, minden meccs kapus-sávjainak
# kapott gólját (kaputra érkezett − védett) a KORÁBBI meccsekből tanult
# kapus-szorzó becsli — kaputra × KAPUS_ALAP_GOL[sáv] × a sáv szorzója —,
# két viszonyítással: az átlagos kapus (szorzó 1) és a kapus EGYETLEN,
# sávok nélküli szorzója (_kapus_osszes_szorzo). A sávok akkor érnek
# valamit, ha a sávonkénti szorzó ezt is veri. Csoport = egy meccs egy
# tanult sávja; a küszöbök a lövőké (PROBA_MIN_CSOPORT, PROBA_ITELET_PCT).


def _kapus_osszes_szorzo(minta: dict) -> float:
    """A kapus egyetlen, sávok nélküli szorzója a (összeadott) sáv-
    mintából: a kapott gól és az átlagos kapus várt kapott góljának
    hányadosa, KAPUS_SULY képzelt átlagos lövéssel simítva, a KAPUS_SZORZO
    sávba szorítva; 1, ha nincs lövés."""
    faced = gol = vart = 0.0
    for sav, (f, sv) in minta.items():
        alap = KAPUS_ALAP_GOL.get(sav)
        if alap is None:
            continue
        faced += float(f)
        gol += float(f) - float(sv)
        vart += float(f) * alap
    if faced <= 0 or vart <= 0:
        return 1.0
    atlag = vart / faced
    arany = (gol + KAPUS_SULY * atlag) / (faced + KAPUS_SULY) / atlag
    return max(KAPUS_SZORZO_MIN, min(KAPUS_SZORZO_MAX, arany))


def keeper_model_backtest(mintak: list) -> dict | None:
    """A kapus-modell próbája egy csapat meccsein: `mintak` — a csapat
    kapusának meccsenkénti nyers sáv-mintái IDŐRENDBEN ([{sáv: [kaputra
    érkezett, védett]}, …] — _kapus_minta vagy player_model_sample
    ["kapus"] alakban). A k. meccs sávjait az első k−1 meccsből tanult
    kapus-szorzó becsli.

    Edzőileg: igaz-e a "távolról 1,2× annyit kap" mondat, vagy a kapus
    egyszerűen jó / rossz formában van — a kapus-edzést a sávra vagy az
    egész kapura kell-e szabni.

    Visszaad: {"meccsek", "csoportok" (meccs × tanult sáv), "lovesek"
    (kaputra érkezett), "atlag_hiba", "osszes_hiba", "modell_hiba" (az
    abszolút eltérések összege, gólban), "javulas_pct" (az átlagos
    kapushoz), "sav_pct" (a sávok nélküli szorzóhoz), "verdict"} — None,
    ha kevesebb mint PROBA_MIN_CSOPORT csoport becsülhető."""
    csoportok = 0
    lovesek = 0
    atlag_hiba = 0.0
    osszes_hiba = 0.0
    modell_hiba = 0.0
    for k in range(1, len(mintak)):
        elozo: dict = {}
        for m in mintak[:k]:
            for sav, (f, sv) in (m or {}).items():
                r = elozo.setdefault(sav, [0, 0])
                r[0] += int(f)
                r[1] += int(sv)
        ksz = _kapus_szorzo(elozo)
        osz = _kapus_osszes_szorzo(elozo)
        for sav, (f, sv) in sorted((mintak[k] or {}).items()):
            if sav not in ksz or sav not in KAPUS_ALAP_GOL:
                continue
            gol = float(f) - float(sv)
            vart = float(f) * KAPUS_ALAP_GOL[sav]
            csoportok += 1
            lovesek += int(f)
            atlag_hiba += abs(gol - vart)
            osszes_hiba += abs(gol - vart * osz)
            modell_hiba += abs(gol - vart * float(ksz[sav]))
    if csoportok < PROBA_MIN_CSOPORT or atlag_hiba <= 0:
        return None
    javulas = round(100.0 * (atlag_hiba - modell_hiba) / atlag_hiba, 1)
    sav_pct = (round(100.0 * (osszes_hiba - modell_hiba) / osszes_hiba, 1)
               if osszes_hiba > 0 else 0.0)
    alap = (f"({csoportok} meccs × sáv, {lovesek} kapura tartó lövés, "
            f"{len(mintak)} meccs)")
    eleje = ("a korábbi meccsekből tanult kapus-modell a következő meccs "
             "kapott góljait ")
    if javulas >= PROBA_ITELET_PCT and sav_pct >= PROBA_ITELET_PCT:
        verdict = (f"{eleje}{javulas:.0f}%-kal pontosabban becsülte, mint az "
                   f"átlagos kapus, és {sav_pct:.0f}%-kal, mint a kapus "
                   f"sávok nélküli szorzója {alap} — a kapus sávjaira lehet "
                   "építeni")
    elif javulas >= PROBA_ITELET_PCT:
        verdict = (f"{eleje}{javulas:.0f}%-kal pontosabban becsülte, mint az "
                   "átlagos kapus, de a sávok nélküli szorzójánál nem "
                   f"jobban {alap} — a kapus formája az egész kapura szól, "
                   "a sávokat óvatosan kell olvasni")
    elif javulas <= -PROBA_ITELET_PCT:
        verdict = (f"{eleje}{-javulas:.0f}%-kal pontatlanabbul becsülte, "
                   f"mint az átlagos kapus {alap} — a kapus meccsről "
                   "meccsre másképp véd, a sávokat óvatosan kell olvasni")
    else:
        verdict = (f"{eleje}nagyjából ugyanolyan pontosan becsülte, mint az "
                   f"átlagos kapus {alap}")
    return {"meccsek": len(mintak), "csoportok": csoportok,
            "lovesek": lovesek, "atlag_hiba": round(atlag_hiba, 2),
            "osszes_hiba": round(osszes_hiba, 2),
            "modell_hiba": round(modell_hiba, 2), "javulas_pct": javulas,
            "sav_pct": sav_pct, "verdict": verdict}



# A védő-modell próbája: a védő egyéni kilépési (és kettőzési) hajlama a
# KORÁBBI meccsekből (VEDO_PROBA_SULY képzelt alkalommal a fal átlaga
# felé simítva) a következő meccsen — a fal átlagához mérve. Egy védő ×
# meccs pár akkor számít, ha a meccsen legalább VEDO_PROBA_MIN_ALK
# alkalma volt; az ítélethez legalább PROBA_MIN_CSOPORT pár kell.
VEDO_PROBA_SULY = 10
VEDO_PROBA_MIN_ALK = 5


def defender_model_backtest(mintak: list) -> dict | None:
    """A védő-modell próbája egy csapat meccsein: `mintak` — a csapat
    meccseinek player_model_sample "vedok" mintái időrendben. Minden
    meccsen a védők kilépési aránya (rálépett / labdás a közelében) a
    korábbi meccsekből tanulva (simítva a fal korábbi átlaga felé),
    összevetve a meccs valódi arányával — és ugyanez a fal korábbi
    átlagával. Mit jelent edzőileg: ha az egyéni hajlam pontosabban jósol,
    a "kit kinek" és a figura-szimuláció fala egyénre szabható; ha nem, a
    kilépés a fal közös szokása, nem az egyes védőké. Visszatérés:
    {"parok", "modell_hiba", "atlag_hiba" (az arány alkalmakkal súlyozott
    átlagos abszolút hibája), "javulas_pct", "kettozes" (ugyanez a
    kettőzésre, vagy None), "verdict"} — None, ha PROBA_MIN_CSOPORT-nál
    kevesebb pár van."""
    eredmeny = {}
    for mezo, alk, tett in (("press", "kozel", "ralepett"),
                            ("double", "masodik", "kettozott")):
        kor: dict = {}
        hm = ha = suly = 0.0
        parok = 0
        for m in mintak:
            m = m or {}
            fal_alk = sum(int(v.get(alk, 0)) for v in kor.values())
            fal_tett = sum(int(v.get(tett, 0)) for v in kor.values())
            if fal_alk > 0:
                atlag = fal_tett / fal_alk
                for mez, v in m.items():
                    n = int(v.get(alk, 0))
                    if n < VEDO_PROBA_MIN_ALK:
                        continue
                    k = kor.get(str(mez))
                    if not k or int(k.get(alk, 0)) <= 0:
                        continue
                    becs = ((int(k[tett]) + VEDO_PROBA_SULY * atlag)
                            / (int(k[alk]) + VEDO_PROBA_SULY))
                    valodi = int(v.get(tett, 0)) / n
                    hm += abs(becs - valodi) * n
                    ha += abs(atlag - valodi) * n
                    suly += n
                    parok += 1
            for mez, v in m.items():
                r = kor.setdefault(str(mez), {alk: 0, tett: 0})
                r[alk] += int(v.get(alk, 0))
                r[tett] += int(v.get(tett, 0))
        if parok >= PROBA_MIN_CSOPORT and suly > 0:
            mh, ah = hm / suly, ha / suly
            j = (ah - mh) / ah * 100.0 if ah > 0 else 0.0
            eredmeny[mezo] = {"parok": parok, "modell_hiba": round(mh, 3),
                              "atlag_hiba": round(ah, 3),
                              "javulas_pct": round(j, 1)}
    if "press" not in eredmeny:
        return None
    p = eredmeny["press"]
    j = p["javulas_pct"]
    itelet = (f"a védők egyéni kilépési hajlama {j:.0f}%-kal pontosabban "
              "jósolt, mint a fal átlaga — a kit kinek egyénre szabható"
              if j >= PROBA_ITELET_PCT else
              f"a védők egyéni kilépési hajlama {-j:.0f}%-kal pontatlanabb "
              "volt a fal átlagánál — a kilépés a fal közös szokása"
              if j <= -PROBA_ITELET_PCT else
              "a védők egyéni kilépési hajlama nem jósolt jobban a fal "
              "átlagánál — a kilépés inkább a fal közös szokása")
    return {**p, "kettozes": eredmeny.get("double"),
            "verdict": f"{itelet} ({p['parok']} védő × meccs pár)"}


def keeper_model_backtest_summary(sorok: list) -> dict | None:
    """Több csapat kapus-próbájának (keeper_model_backtest sorai) összege
    — {"csapatok", "csoportok", "lovesek", "atlag_hiba", "osszes_hiba",
    "modell_hiba", "javulas_pct", "sav_pct", "verdict"}; None, ha nincs
    sor."""
    sorok = [r for r in (sorok or []) if r]
    if not sorok:
        return None
    ah = sum(float(r["atlag_hiba"]) for r in sorok)
    oh = sum(float(r["osszes_hiba"]) for r in sorok)
    mh = sum(float(r["modell_hiba"]) for r in sorok)
    cs = sum(int(r["csoportok"]) for r in sorok)
    lv = sum(int(r["lovesek"]) for r in sorok)
    javulas = round(100.0 * (ah - mh) / ah, 1) if ah > 0 else 0.0
    sav_pct = round(100.0 * (oh - mh) / oh, 1) if oh > 0 else 0.0
    if javulas >= PROBA_ITELET_PCT:
        irany = f"{javulas:.0f}%-kal pontosabban"
    elif javulas <= -PROBA_ITELET_PCT:
        irany = f"{-javulas:.0f}%-kal pontatlanabbul"
    else:
        irany = "nagyjából ugyanolyan pontosan"
    sav = ""
    if javulas >= PROBA_ITELET_PCT:
        sav = (f", és {sav_pct:.0f}%-kal, mint a kapusok sávok nélküli "
               "szorzója" if sav_pct >= PROBA_ITELET_PCT else
               ", de a sávok nélküli szorzónál nem jobban")
    return {"csapatok": len(sorok), "csoportok": cs, "lovesek": lv,
            "atlag_hiba": round(ah, 2), "osszes_hiba": round(oh, 2),
            "modell_hiba": round(mh, 2), "javulas_pct": javulas,
            "sav_pct": sav_pct,
            "verdict": (f"a könyvtár {len(sorok)} csapatán a korábbi "
                        "meccsekből tanult kapus-modell a következő meccs "
                        f"kapott góljait {irany} becsülte, mint az átlagos "
                        f"kapus{sav} ({cs} meccs × sáv, {lv} kapura tartó "
                        "lövés)")}


def trust_levels(lovo: dict | None, kapus: dict | None,
                 dontes: dict | None, vedo: dict | None = None) -> dict:
    """A három próba (shooter_model_backtest, keeper_model_backtest,
    decisions.decision_model_check) szintje modellenként — ezt olvassa az
    élő jelzések önkalibrálása (calibrate_alerts) és a meccs eleji
    "AI-megbízhatóság" sor (model_trust_summary). Visszatérés:
    {"lovo": "megbizhato" | "csapat" (az egyéni szorzó nem jobb a
    csapaténál) | "ovatos" | "semleges" | None, "kapus": "megbizhato" |
    "egeszeben" (a sávok nélküli szorzó jobb) | "ovatos" | "semleges" |
    None, "dontes": "igazolt" | "ovatos" | "semleges" | None, "vedo":
    "egyeni" (a védők egyéni kilépése pontosabban jósol a fal átlagánál) |
    "kozos" | None} — None, ahol a próba nem ítélt (kevés korábbi meccs)."""
    from .decisions import DONTES_PROBA_PP
    ki = {"lovo": None, "kapus": None, "dontes": None, "vedo": None}
    if vedo:
        ki["vedo"] = ("egyeni" if float(vedo["javulas_pct"]) >= PROBA_ITELET_PCT
                      else "kozos")
    if lovo:
        j, e = float(lovo["javulas_pct"]), float(lovo.get("egyeni_pct", 0.0))
        ki["lovo"] = ("megbizhato" if j >= PROBA_ITELET_PCT
                      and e >= PROBA_ITELET_PCT else
                      "csapat" if j >= PROBA_ITELET_PCT else
                      "ovatos" if j <= -PROBA_ITELET_PCT else "semleges")
    if kapus:
        j, sp = float(kapus["javulas_pct"]), float(kapus.get("sav_pct", 0.0))
        ki["kapus"] = ("megbizhato" if j >= PROBA_ITELET_PCT
                       and sp >= PROBA_ITELET_PCT else
                       "egeszeben" if j >= PROBA_ITELET_PCT else
                       "ovatos" if j <= -PROBA_ITELET_PCT else "semleges")
    if dontes:
        k = float(dontes["kulonbseg_pp"])
        ki["dontes"] = ("igazolt" if k >= DONTES_PROBA_PP else
                        "ovatos" if k <= -DONTES_PROBA_PP else "semleges")
    return ki


def model_trust_summary(lovo: dict | None, kapus: dict | None,
                        dontes: dict | None,
                        vedo: dict | None = None) -> str | None:
    """A három próba (shooter_model_backtest, keeper_model_backtest,
    decisions.decision_model_check) egy sorban — az élő képernyő meccs
    eleji "AI-megbízhatóság" sorához: "lövő-szorzók: megbízhatók (+48%);
    kapus-sávok: csak egészében (a sávok nélküli szorzó jobb); döntés-
    tanácsok: igazoltak (+20 százalékpont)". None, ha egyik próba sem
    ítélt (kevés korábbi meccs)."""
    sz = trust_levels(lovo, kapus, dontes)
    reszek = []
    if sz["lovo"]:
        j = float(lovo["javulas_pct"])
        reszek.append({
            "megbizhato": f"lövő-szorzók: megbízhatók (+{j:.0f}%)",
            "csapat": ("lövő-szorzók: csak csapat-szinten (az egyéni "
                       "szorzó nem jobb a csapaténál)"),
            "ovatos": f"lövő-szorzók: óvatosan ({j:.0f}%)",
            "semleges": "lövő-szorzók: semlegesek"}[sz["lovo"]])
    if sz["kapus"]:
        j = float(kapus["javulas_pct"])
        reszek.append({
            "megbizhato": f"kapus-sávok: megbízhatók (+{j:.0f}%)",
            "egeszeben": ("kapus-sávok: csak egészében (a sávok nélküli "
                          "szorzó jobb)"),
            "ovatos": f"kapus-sávok: óvatosan ({j:.0f}%)",
            "semleges": "kapus-sávok: semlegesek"}[sz["kapus"]])
    if sz["dontes"]:
        k = float(dontes["kulonbseg_pp"])
        reszek.append({
            "igazolt": f"döntés-tanácsok: igazoltak (+{k:.0f} százalékpont)",
            "ovatos": f"döntés-tanácsok: óvatosan ({k:.0f} százalékpont)",
            "semleges": "döntés-tanácsok: semlegesek"}[sz["dontes"]])
    if vedo:
        j = float(vedo["javulas_pct"])
        reszek.append(f"védő-modell: egyénre szabható (+{j:.0f}%)"
                      if j >= PROBA_ITELET_PCT else
                      "védő-modell: a kilépés a fal közös szokása")
    return "; ".join(reszek) if reszek else None


def forecast_trust_summary(elore: dict | None = None,
                           golszerzo: dict | None = None,
                           elo: dict | None = None,
                           vedekezes: dict | None = None,
                           forma: dict | None = None,
                           figura: dict | None = None) -> str | None:
    """Az előrejelző modellek próbái egy sorban — az élő képernyő meccs
    eleji második AI-sorához: az eredmény-előrejelzés és a gólszerzők a
    formához (forecast_rows_summary / scorer_forecast_backtest
    "javulas_pct"), az élő esély az álláshoz (in_play_backtest), a
    fal-becslés találata (defense_system_backtest), a napi forma
    (hot_hand_backtest "itelet"), a visszatérő figurák újra-jövése
    (setplays.figure_recurrence_backtest). Az ítélet a PROBA_ITELET_PCT
    küszöbével. None, ha egyik próba sem ítélt."""
    def sz(x):
        return f"{x:+.0f}%"

    def forma_mel(cim, p):
        j = float(p["javulas_pct"])
        if j >= PROBA_ITELET_PCT:
            return f"{cim}: pontosabb a formánál ({sz(j)})"
        if j <= -PROBA_ITELET_PCT:
            return f"{cim}: pontatlanabb a formánál ({sz(j)})"
        return f"{cim}: nagyjából olyan, mint a forma"

    reszek = []
    if elore:
        reszek.append(forma_mel("eredmény-előrejelzés", elore))
    if golszerzo:
        reszek.append(forma_mel("gólszerzők", golszerzo))
    if elo:
        j = float(elo["javulas_pct"])
        reszek.append(f"élő esély: pontosít az álláshoz ({sz(j)})"
                      if j >= PROBA_ITELET_PCT else
                      f"élő esély: ront az álláshoz ({sz(j)})"
                      if j <= -PROBA_ITELET_PCT else
                      "élő esély: nem tesz hozzá az álláshoz")
    if vedekezes:
        reszek.append(f"fal-becslés: {vedekezes['meccsek']} meccsből "
                      f"{vedekezes['talalat']} talált")
    if forma:
        reszek.append("napi forma: kitart" if forma.get("itelet") == "kitart"
                      else "napi forma: nem tart ki (a modell a jobb tipp)")
    if figura:
        reszek.append(f"figurák: {figura['visszatero']} esetből "
                      f"{figura['visszatero_jott']} jött újra")
    return "; ".join(reszek) if reszek else None


def decision_trust_summary(kapus_valasztas: dict | None = None,
                           hetes: dict | None = None,
                           hetes_irany: dict | None = None,
                           idokeres: dict | None = None,
                           kapus_forma: dict | None = None,
                           het_a_hat: dict | None = None) -> str | None:
    """A pad döntés-próbái egy sorban — az élő képernyő meccs eleji
    harmadik AI-sorához: a kapus-választás (keeper_choice_backtest), a
    hetes-dobó (seven_taker_backtest), a hetes-irány
    (seven_direction_backtest), az időkérés a sorozat ellen
    (timeout_run_backtest), a kapus napi formája (keeper_hot_hand_backtest)
    és a 7 a 6 mérlege (seven_six_backtest) — az ítéletük rövid alakja.
    Mit jelent edzőileg: a meccs elején látszik, a pad melyik döntésénél
    lehet a könyvtár szabályára építeni. None, ha egyik próba sem ítélt."""
    reszek = []
    if kapus_valasztas:
        reszek.append({"igazolt": "kapus-választás: igazolt",
                       "egyenlo": "kapus-választás: a szokásos kapus is jó",
                       "nem": "kapus-választás: nem igazolódott"}.get(
            kapus_valasztas.get("itelet"), "kapus-választás: nincs ítélet"))
    if hetes:
        reszek.append("hetes-dobó: a könyvtár dobója jobb"
                      if hetes.get("itelet") == "igazolt" else
                      "hetes-dobó: a napi forma döntsön")
    if hetes_irany:
        reszek.append("hetes-irány: jósolható"
                      if hetes_irany.get("itelet") == "josolhato" else
                      "hetes-irány: nem jósolható")
    if idokeres:
        reszek.append("időkérés: megtöri a sorozatot"
                      if idokeres.get("itelet") == "megtori" else
                      "időkérés: csak váltással ér valamit")
    if kapus_forma:
        reszek.append("kapus napi formája: kitart"
                      if kapus_forma.get("itelet") == "kitart" else
                      "kapus napi formája: nem tart ki")
    if het_a_hat:
        reszek.append({"megeri": "7 a 6: megéri",
                       "egyenlo": "7 a 6: annyit hoz, mint a 6 a 6",
                       "nem": "7 a 6: nem éri meg"}.get(
            het_a_hat.get("itelet"), "7 a 6: nincs ítélet"))
    return "; ".join(reszek) if reszek else None


def model_checks_overview(mc: dict) -> dict | None:
    """Az AI-próbák összképe: a /library/player-model-check válaszából
    (`mc`) próbánként, hogy ítélt-e, és bizonyított-e — a lövő-szorzók,
    a kapus-sávok és a döntés-tanácsok a trust_levels szintje szerint
    ("megbizhato" / "igazolt"), a védő-modell a csapatok többségén, az
    eredmény-előrejelzés, a gólszerzők és az élő esély a PROBA_ITELET_PCT
    javulástól, a fal-becslés a liga-viszonyításnál több találattal, a
    kapus-választás, ha a lövők szerinti választás a sima mérlegnél
    többet tud (keeper_choice_backtest), a figura-felderítés, ha a
    visszatérő figurákra érdemes készülni, a felderítés, ha a kulcsai
    átvihetők a következő meccsre (scouting_backtest), a hetes-dobó, ha
    a könyvtár dobója a többieknél jobb (seven_taker_backtest), a
    hetes-irány, ha a dobók fő iránya jósolható (seven_direction_backtest).
    Mit
    jelent edzőileg: egy pillantásra, mennyire lehet a klub saját
    könyvtárán az AI-ra építeni. Visszatérés: {"itelt", "bizonyitott",
    "sorok": [{"nev", "bizonyitott"}], "verdict"} — None, ha egyik próba
    sem ítélt."""
    mc = mc or {}
    sz = trust_levels(mc.get("osszes"), mc.get("kapus_osszes"),
                      mc.get("dontes_osszes"))
    sorok: list = []

    def add(nev, ok):
        sorok.append({"nev": nev, "bizonyitott": bool(ok)})

    if sz["lovo"]:
        add("lövő-szorzók", sz["lovo"] == "megbizhato")
    if sz["kapus"]:
        add("kapus-sávok", sz["kapus"] == "megbizhato")
    if sz["dontes"]:
        add("döntés-tanácsok", sz["dontes"] == "igazolt")
    vedok = mc.get("vedok") or []
    if vedok:
        jo = sum(1 for r in vedok if float(r["javulas_pct"]) >= PROBA_ITELET_PCT)
        add("védő-modell", 2 * jo > len(vedok))
    for kulcs, nev in (("elorejelzes", "eredmény-előrejelzés"),
                       ("golszerzo_proba", "gólszerzők"),
                       ("elo_esely_proba", "élő esély")):
        p = mc.get(kulcs)
        if p:
            add(nev, float(p["javulas_pct"]) >= PROBA_ITELET_PCT)
    v = mc.get("vedekezes_proba")
    if v:
        add("fal-becslés", int(v["talalat"]) > int(v["liga_talalat"]))
    kv = mc.get("kapus_valasztas_proba")
    if kv:
        add("kapus-választás", kv.get("itelet") == "igazolt")
    f = mc.get("figura_proba")
    if f:
        add("figura-felderítés", "érdemes készülni" in str(f.get("verdict")))
    fd = mc.get("felderites_proba")
    if fd:
        add("felderítés", fd.get("itelet") == "atviheto")
    hp = mc.get("hetes_proba")
    if hp:
        add("hetes-dobó", hp.get("itelet") == "igazolt")
    hi = mc.get("hetes_irany_proba")
    if hi:
        add("hetes-irány", hi.get("itelet") == "josolhato")
    if not sorok:
        return None
    k = sum(1 for r in sorok if r["bizonyitott"])
    igen = [r["nev"] for r in sorok if r["bizonyitott"]]
    nem = [r["nev"] for r in sorok if not r["bizonyitott"]]
    verdict = f"{len(sorok)} próbából {k} bizonyított"
    if igen:
        verdict += ": " + ", ".join(igen)
    if nem:
        verdict += "; még nem: " + ", ".join(nem)
    return {"itelt": len(sorok), "bizonyitott": k, "sorok": sorok,
            "verdict": verdict}


# ---- Az élő jelzések önkalibrálása ------------------------------------------
# Egy élő jelzés (kit kinek, lövés-elosztás, kapus-választás, döntés-
# figyelő) annyit ér, amennyit a mögötte álló modell a csapat KORÁBBI
# meccsein a próbán mutatott. Ahol a próba részleges vagy negatív
# (az alábbi szintek), a jelzés "óvatos": a szöveg végére kerül az ok,
# és a kliens alacsonyabb súllyal (szürkén) mutatja. A "semleges" szint
# nem óvatos: a modell nem rosszabb a viszonyításnál.
BIZALOM_OVATOS_OKOK = {
    ("lovo", "csapat"): ("az egyéni lövő-szorzó a korábbi meccseken nem "
                         "volt jobb a csapaténál"),
    ("lovo", "ovatos"): ("a lövő-modell a korábbi meccseken pontatlanabb "
                         "volt az xG-nél"),
    ("kapus", "egeszeben"): ("a kapus-sávok a korábbi meccseken csak "
                             "egészében igazolódtak"),
    ("kapus", "ovatos"): ("a kapus-modell a korábbi meccseken pontatlanabb "
                          "volt az átlagos kapusnál"),
    ("dontes", "ovatos"): ("a modell legjobb opciója a korábbi meccseken "
                           "nem hozott több gólt"),
    ("vedo", "kozos"): ("a védőink egyéni kilépése a korábbi meccseken nem "
                        "tért el a fal átlagától — a párosítás óvatos"),
}


def calibrate_alerts(alerts: list, szintek: dict) -> list:
    """Az élő jelzések önkalibrálása: `szintek` oldalanként (a jelzés
    "team" mezője szerint) a jelzés mögötti modellek próba-szintje
    ({"home": {"lovo": "csapat", "kapus": "megbizhato"}, ...} — a
    trust_levels értékei; None a nem ítélt modell). Minden jelzés új
    másolata "megbizhatosag" mezőt kap (a nem-None szintek) és "ovatos"
    jelzőt; óvatos szintnél a szöveg végére "(óvatosan: …)" az okkal
    (BIZALOM_OVATOS_OKOK). A bemenet nem változik."""
    ki = []
    for a in alerts or []:
        sz = {k: v for k, v in sorted(
            (szintek.get(a.get("team")) or {}).items()) if v}
        okok = [BIZALOM_OVATOS_OKOK[(k, v)] for k, v in sz.items()
                if (k, v) in BIZALOM_OVATOS_OKOK]
        b = dict(a)
        b["megbizhatosag"] = sz
        b["ovatos"] = bool(okok)
        if okok and b.get("text"):
            b["text"] = f"{b['text']} (óvatosan: {'; '.join(okok)})"
        ki.append(b)
    return ki


# ---- Meccs-előrejelzés a csapat-modellekből --------------------------------
# A következő meccs várható eredménye a két csapat KORÁBBI meccseiből
# tanult csapat-modellből, sávonként (közeli / közép / távoli lövés):
# - lövés-mennyiség: a támadó meccsenkénti lövései és a védő meccsenként
#   kapott lövései átlaga;
# - lövés-minőség: ugyanígy az xG / lövés;
# - befejezés: a támadó gól / xG aránya, kapus + védelem: a védő kapott
#   gól / xGA aránya — mindkettő ELOREJELZES_SULY képzelt lövéssel a
#   liga-szint (a két csapat összes lövésének gól / xG aránya) felé
#   simítva, és a liga-szinttel egyszer osztva (különben a liga xG-
#   torzítása kétszer számítana);
# - plusz a nem látott (középkezdésből következtetett) gólok átlaga.
# Az esélyek a gólkülönbség normál közelítéséből (szórás: a két várható
# gólszám összegének gyöke — Poisson); |különbség| < 0,5 a döntetlen.
ELOREJELZES_SULY = 20
# Csapatonként legalább ennyi korábbi meccs kell az előrejelzéshez.
ELOREJELZES_MIN_MECCS = 2
# A próba (forecast_backtest) ítéletéhez legalább ennyi előre jelzett meccs.
ELOREJELZES_PROBA_MIN = 5
ELOREJELZES_SAVOK = ("close", "mid", "far")


def match_forecast_sample(match: Match,
                          config: TacticsConfig | None = None) -> dict:
    """A meccs-előrejelzés NYERS, JSON-barát meccs-mintája (a lemezes
    eredmény-tárba tehető): oldalanként {"lovesek": {sáv: [lövés, gól,
    xG]} (a látott lövések, xg.match_xg), "golok" (az összes felismert
    gól, a nem látott is), "latott_golok", "gol_percek" (a gólok perce a
    felvétel kezdetétől, időrendben — az élő esély próbájához)}, és a
    felvétel hossza percben ("perc_hossz"). Meccsek közt összeadható."""
    from .event_detection import EventType, detect_shots
    from .xg import match_xg
    config = config or TacticsConfig()
    ki = {s: {"lovesek": {}, "golok": 0, "latott_golok": 0, "gol_percek": []}
          for s in ("home", "away")}
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    t0 = match.frames[0].t if match.frames else 0
    for sh in match_xg(match, config)["shots"]:
        side = sh["team"]
        if side not in ki:
            continue
        goal_x = config.attacks_toward_x(Team(side))
        r = ki[side]["lovesek"].setdefault(
            kapus_sav(sh["x"], sh["y"], goal_x), [0, 0, 0.0])
        gol = sh["outcome"] == "goal"
        r[0] += 1
        r[1] += int(gol)
        r[2] = round(r[2] + float(sh["xg"]), 3)
        ki[side]["latott_golok"] += int(gol)
    for e in sorted(detect_shots(match, config), key=lambda e: e.t):
        if e.type == EventType.GOAL and e.team.value in ki:
            ki[e.team.value]["golok"] += 1
            ki[e.team.value]["gol_percek"].append(
                round((e.t - t0) / fps / 60.0, 2))
    ki["perc_hossz"] = (round((match.frames[-1].t - t0) / fps / 60.0, 2)
                        if match.frames else 0.0)
    return ki


def _elorejelzes_profil(tortenet: list) -> dict:
    """Egy csapat profilja a korábbi meccseiből: `tortenet` = [(a csapat
    oldalának mintája, az ellenfél oldalának mintája)] (match_forecast_
    sample oldalai). Sávonként a leadott és a kapott lövés / gól / xG
    összege, a gólok (összes és látott) mindkét irányban, a meccsszám."""
    p = {"n": len(tortenet), "lo": {}, "kap": {}, "gf": 0, "ga": 0,
         "gf_l": 0, "ga_l": 0}
    for sajat, ellen in tortenet:
        for kulcs, minta in (("lo", sajat), ("kap", ellen)):
            for sav, (n, gol, xg) in (minta.get("lovesek") or {}).items():
                r = p[kulcs].setdefault(sav, [0, 0, 0.0])
                r[0] += int(n)
                r[1] += int(gol)
                r[2] += float(xg)
        p["gf"] += int(sajat.get("golok") or 0)
        p["gf_l"] += int(sajat.get("latott_golok") or 0)
        p["ga"] += int(ellen.get("golok") or 0)
        p["ga_l"] += int(ellen.get("latott_golok") or 0)
    return p


def _elorejelzes_gol(tam: dict, ved: dict, liga: float) -> float:
    """A `tam` profilú csapat várható gólja a `ved` profilú ellen (lásd
    az ELOREJELZES_ blokk kommentjét)."""
    xg = 0.0
    for sav in ELOREJELZES_SAVOK:
        lo = tam["lo"].get(sav, [0, 0, 0.0])
        kap = ved["kap"].get(sav, [0, 0, 0.0])
        menny = (lo[0] / tam["n"] + kap[0] / ved["n"]) / 2.0
        minos = [r[2] / r[0] for r in (lo, kap) if r[0] > 0]
        if menny > 0 and minos:
            xg += menny * sum(minos) / len(minos)

    def simit(gol, xg_ossz, n_loves):
        atlag = xg_ossz / n_loves if n_loves else 0.0
        nevezo = xg_ossz + ELOREJELZES_SULY * atlag
        return ((gol + ELOREJELZES_SULY * atlag * liga) / nevezo
                if nevezo > 0 else liga)

    lo_n = sum(r[0] for r in tam["lo"].values())
    lo_xg = sum(r[2] for r in tam["lo"].values())
    kap_n = sum(r[0] for r in ved["kap"].values())
    kap_xg = sum(r[2] for r in ved["kap"].values())
    befejezes = simit(tam["gf_l"], lo_xg, lo_n)
    vedelem = simit(ved["ga_l"], kap_xg, kap_n)
    szorzo = befejezes * vedelem / liga if liga > 0 else 1.0
    nem_latott = ((tam["gf"] - tam["gf_l"]) / tam["n"]
                  + (ved["ga"] - ved["ga_l"]) / ved["n"]) / 2.0
    return xg * szorzo + max(0.0, nem_latott)


def match_forecast(hazai: list, vendeg: list) -> dict | None:
    """Meccs-előrejelzés a két csapat KORÁBBI meccseiből: `hazai` /
    `vendeg` = [(a csapat oldalának mintája, az ellenfél oldalának
    mintája)] (match_forecast_sample oldalai, meccsenként). Mit jelent
    edzőileg: a meccs előtti várakozás a csapat-modellekből — ki a
    favorit, és mennyivel; a "forma" (naiv: a csapat lőtt és az ellenfél
    kapott góljainak átlaga) mellé. Visszatérés: {"home_goals",
    "away_goals" (várható gól, 1 tizedes), "p_home", "p_draw", "p_away"
    (esély, 0..1), "naiv_home", "naiv_away", "meccsek": {"home",
    "away"}} — None, ha valamelyik csapatnál ELOREJELZES_MIN_MECCS-nél
    kevesebb meccs van."""
    if len(hazai) < ELOREJELZES_MIN_MECCS or len(vendeg) < ELOREJELZES_MIN_MECCS:
        return None
    h, v = _elorejelzes_profil(hazai), _elorejelzes_profil(vendeg)
    gol = sum(p[k][s][1] for p in (h, v) for k in ("lo", "kap")
              for s in p[k])
    xg = sum(p[k][s][2] for p in (h, v) for k in ("lo", "kap")
             for s in p[k])
    liga = gol / xg if xg > 0 else 1.0
    eh, ev = _elorejelzes_gol(h, v, liga), _elorejelzes_gol(v, h, liga)
    mu, sd = eh - ev, math.sqrt(max(eh + ev, 1.0))

    def phi(z):
        return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    p_home = phi((mu - 0.5) / sd)
    p_away = 1.0 - phi((mu + 0.5) / sd)
    return {"home_goals": round(eh, 1), "away_goals": round(ev, 1),
            "p_home": round(p_home, 3), "p_away": round(p_away, 3),
            "p_draw": round(max(0.0, 1.0 - p_home - p_away), 3),
            "naiv_home": round((h["gf"] / h["n"] + v["ga"] / v["n"]) / 2, 1),
            "naiv_away": round((v["gf"] / v["n"] + h["ga"] / h["n"]) / 2, 1),
            "meccsek": {"home": h["n"], "away": v["n"]}}


def match_forecast_text(hazai_nev: str, vendeg_nev: str,
                        f: dict | None) -> str | None:
    """Az előrejelzés egy mondatban: "Hazai 27–24 Vendég — esélyek:
    Hazai 68%, döntetlen 9%, Vendég 23%" (a csapatnevekkel: a meccsterv
    "mi · ők" párosításán nincs pálya-oldal). None előrejelzés nélkül."""
    if not f:
        return None
    return (f"{hazai_nev} {f['home_goals']:.0f}–{f['away_goals']:.0f} "
            f"{vendeg_nev} — esélyek: {hazai_nev} {f['p_home'] * 100:.0f}%, "
            f"döntetlen {f['p_draw'] * 100:.0f}%, {vendeg_nev} "
            f"{f['p_away'] * 100:.0f}%")


# Élő esély: a meccs előtti előrejelzés és az addigi állás. A hátralévő
# idő várt gólja a meccs előtti várakozás (ELO_ELOZETES_PERC perc
# játéknak számít) és az addig lőtt gólok (a valódi játékidővel)
# összevont üteméből; a rendes játékidő ELO_MECCS_PERC perc. A "várt
# felett / alatt" mondat ELO_ELTERES_GOL góltól szól.
ELO_MECCS_PERC = 60
ELO_ELOZETES_PERC = 60
ELO_ELTERES_GOL = 1.5
# Esély-zuhanás: ha egy csapat győzelmi esélye az előző mérési pont (a
# meccs eleje, illetve az előző perc) óta legalább ennyi százalékponttal
# esett, az élő esély időkérést javasol.
ELO_ESES_PP = 20.0


def in_play_odds(f: dict, perc: float, gh: int, ga: int) -> dict:
    """Élő esély a `perc`. percben `gh`–`ga` állásnál a meccs előtti
    előrejelzésből (`f`, match_forecast): a hátralévő várt gól
    csapatonként (f gól + addigi gól) / (ELO_ELOZETES_PERC + perc) ×
    (ELO_MECCS_PERC − perc), a végső különbség normál közelítéssel (a
    szórás a hátralévő várt gólok összegének gyöke, legalább 1).
    Visszatérés: {"p_home", "p_draw", "p_away", "vart_home", "vart_away"
    (a perc-arányos meccs előtti várakozás), "elteres_home",
    "elteres_away" (addigi gól − várt)}."""
    hatra = max(0.0, ELO_MECCS_PERC - perc)
    uh = (f["home_goals"] + gh) / (ELO_ELOZETES_PERC + perc)
    ua = (f["away_goals"] + ga) / (ELO_ELOZETES_PERC + perc)
    rh, ra = uh * hatra, ua * hatra
    mu, sd = (gh - ga) + (rh - ra), math.sqrt(max(rh + ra, 1.0))

    def phi(z):
        return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    p_home = phi((mu - 0.5) / sd)
    p_away = 1.0 - phi((mu + 0.5) / sd)
    vh = f["home_goals"] * min(perc, ELO_MECCS_PERC) / ELO_MECCS_PERC
    va = f["away_goals"] * min(perc, ELO_MECCS_PERC) / ELO_MECCS_PERC
    return {"p_home": round(p_home, 3), "p_away": round(p_away, 3),
            "p_draw": round(max(0.0, 1.0 - p_home - p_away), 3),
            "vart_home": round(vh, 1), "vart_away": round(va, 1),
            "elteres_home": round(gh - vh, 1),
            "elteres_away": round(ga - va, 1)}


# Az élő esély próbájához legalább ennyi percpont (meccs × perc) kell.
ELO_PROBA_MIN = 10


def in_play_backtest(meccsek: list, csapat: str | None = None) -> dict | None:
    """Az élő esély próbája: `meccsek` időrendben [{"match_id", "home",
    "away", "minta" (match_forecast_sample — "gol_percek",
    "perc_hossz")}]. Minden meccsen, ahol a meccs előtti előrejelzés
    megvan (csak a korábbiakból, match_forecast), a LIVE_AJANLO_PERCEK
    perceiben (amíg a felvétel tart) az élő esély (in_play_odds) az
    addigi állással, és a viszonyítás: ugyanez SEMLEGES várakozással (a
    két csapat a két várható gól átlagával — csak az állás és az idő
    számít). A mérték a végeredményhez mért Brier-hiba (a három kimenet
    esélyének négyzetes hibája). A `csapat` megadásával csak a csapat
    meccsei. Edzőileg: hozzátesz-e a csapat-modell az álláshoz — érdemes-e
    a padon az élő esélyre figyelni. Visszatérés: {"meccsek", "pontok",
    "modell_brier", "semleges_brier", "javulas_pct", "verdict"} — None
    ELO_PROBA_MIN-nél kevesebb percpontnál."""
    tortenet: dict = {}
    pontok = 0
    mb = sb = 0.0
    meccs_db = 0
    for m in meccsek:
        mi, h, v = m.get("minta") or {}, m.get("home"), m.get("away")
        sh, sv = mi.get("home") or {}, mi.get("away") or {}
        f = match_forecast(tortenet.get(h, []), tortenet.get(v, []))
        tortenet.setdefault(h, []).append((sh, sv))
        tortenet.setdefault(v, []).append((sv, sh))
        if f is None or (csapat is not None and csapat not in (h, v)):
            continue
        gh, gv = int(sh.get("golok") or 0), int(sv.get("golok") or 0)
        kimenet = (1.0 if gh > gv else 0.0, 1.0 if gh == gv else 0.0,
                   1.0 if gh < gv else 0.0)
        atlag = (f["home_goals"] + f["away_goals"]) / 2.0
        semleges = {"home_goals": atlag, "away_goals": atlag}
        volt = False
        for perc in LIVE_AJANLO_PERCEK:
            if perc > float(mi.get("perc_hossz") or 0.0):
                continue
            ah = sum(1 for x in sh.get("gol_percek") or [] if x <= perc)
            av = sum(1 for x in sv.get("gol_percek") or [] if x <= perc)
            for vart, gy in ((f, "m"), (semleges, "s")):
                o = in_play_odds(vart, perc, ah, av)
                b = sum((p - k) ** 2 for p, k in zip(
                    (o["p_home"], o["p_draw"], o["p_away"]), kimenet))
                if gy == "m":
                    mb += b
                else:
                    sb += b
            pontok += 1
            volt = True
        meccs_db += int(volt)
    if pontok < ELO_PROBA_MIN:
        return None
    mbr, sbr = mb / pontok, sb / pontok
    j = (sbr - mbr) / sbr * 100.0 if sbr > 0 else 0.0

    def sz(x):
        return f"{x:.2f}".replace(".", ",")

    itelet = (f"a csapat-modell {j:.0f}%-kal pontosít az álláshoz képest"
              if j >= PROBA_ITELET_PCT else
              f"a csapat-modell {-j:.0f}%-kal ront az álláshoz képest"
              if j <= -PROBA_ITELET_PCT else
              "a csapat-modell nem tesz hozzá érdemben az álláshoz")
    return {"meccsek": meccs_db, "pontok": pontok,
            "modell_brier": round(mbr, 3), "semleges_brier": round(sbr, 3),
            "javulas_pct": round(j, 1),
            "verdict": (f"az élő esély {pontok} percponton ({meccs_db} "
                        f"meccs) átlagosan {sz(mbr)} Brier-hibával jósolta "
                        f"a végeredményt (a csak az állásból számolté "
                        f"{sz(sbr)}) — {itelet}")}


def live_forecast_alerts(match: Match, f: dict | None,
                         config: TacticsConfig | None = None) -> dict:
    """Élő esély a csapat-modellből: a LIVE_AJANLO_PERCEK perceiben az
    addigi állás (detect_shots CSAK az addigi kockákon — okszerű) és a
    meccs előtti előrejelzés (`f`, match_forecast) → a végeredmény
    esélye (in_play_odds), és ha egy csapat ELO_ELTERES_GOL-lal a
    várakozása felett vagy alatt jár, az is. Edzőileg: a "hol tartunk a
    várakozáshoz képest" — a félidei / időkérési beszéd alapja.
    Ha egy csapat győzelmi esélye az előző mérési pont óta legalább
    ELO_ESES_PP százalékponttal esett, a mondat időkérést javasol
    ("eses": {"team", "pp"}, különben None).
    Visszatérés: {"alerts": [{"t" (kocka), "t_s", "perc", "home_goals",
    "away_goals", "p_home", "p_draw", "p_away", "elteres_home",
    "elteres_away", "eses", "text"}]} — üres előrejelzés nélkül."""
    from .event_detection import EventType, detect_shots
    config = config or TacticsConfig()
    alerts: list = []
    if not f or not match.frames:
        return {"alerts": alerts}
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    t0 = match.frames[0].t
    hn, vn = match.meta.home_team, match.meta.away_team
    elozo = {"home": f["p_home"], "away": f["p_away"], "perc": None} \
        if "p_home" in f else None
    for perc in LIVE_AJANLO_PERCEK:
        hatar = t0 + int(round(perc * 60 * fps))
        eddig = [fr for fr in match.frames if fr.t <= hatar]
        if len(eddig) < 2 or eddig[-1].t < hatar - fps:
            continue      # a meccs még nem ért el idáig
        resz = Match(meta=match.meta, frames=eddig)
        gol = {"home": 0, "away": 0}
        for e in detect_shots(resz, config):
            if e.type == EventType.GOAL and e.team.value in gol:
                gol[e.team.value] += 1
        o = in_play_odds(f, perc, gol["home"], gol["away"])
        szoveg = (f"Élő esély ({perc}. perc, {gol['home']}–{gol['away']}): "
                  f"{hn} {o['p_home'] * 100:.0f}%, döntetlen "
                  f"{o['p_draw'] * 100:.0f}%, {vn} {o['p_away'] * 100:.0f}% "
                  f"— a meccs előtti várakozás {f['home_goals']:.0f}–"
                  f"{f['away_goals']:.0f}")
        nagy = max((("home", hn), ("away", vn)),
                   key=lambda x: (abs(o[f"elteres_{x[0]}"]), x[0] == "home"))
        el = o[f"elteres_{nagy[0]}"]
        if abs(el) >= ELO_ELTERES_GOL:
            irany = "felett" if el > 0 else "alatt"
            szam = f"{abs(el):.1f}".replace(".", ",")
            szoveg += f"; {nagy[1]} {szam} góllal a várt {irany}"
        eses = None
        if elozo is not None:
            for side, nev in (("home", hn), ("away", vn)):
                d = (elozo[side] - o[f"p_{side}"]) * 100.0
                if d >= ELO_ESES_PP and (eses is None or d > eses["pp"]):
                    eses = {"team": side, "pp": round(d, 1)}
            if eses is not None:
                ep = elozo["perc"]
                mikor = ("a meccs eleje" if ep is None else
                         f"{'az' if ep in (1, 5) or 50 <= ep < 60 else 'a'} "
                         f"{ep}. perc")
                szoveg += (f" — {hn if eses['team'] == 'home' else vn} "
                           f"esélye {mikor} óta {eses['pp']:.0f} "
                           "százalékponttal esett: érdemes időt kérni")
            elozo = {"home": o["p_home"], "away": o["p_away"], "perc": perc}
        alerts.append({"t": hatar, "t_s": round(hatar / fps, 1),
                       "perc": perc, "home_goals": gol["home"],
                       "away_goals": gol["away"], **o, "eses": eses,
                       "text": szoveg})
    return {"alerts": alerts}


def forecast_backtest(meccsek: list) -> dict | None:
    """Az előrejelzés próbája: `meccsek` időrendben [{"match_id", "home",
    "away" (csapatnevek), "minta" (match_forecast_sample)}]. Minden
    meccsre, ahol mindkét csapatnak legalább ELOREJELZES_MIN_MECCS
    korábbi meccse van a listában, előrejelzés CSAK a korábbiakból
    (match_forecast), és összevetés a tényleges eredménnyel — a modell és
    a forma (naiv) győztes-találata (döntetlennel végződött meccs nem
    számít a találatba) és a gólkülönbség átlagos abszolút hibája.
    Edzőileg: mennyire lehet a meccs előtti előrejelzésre építeni.
    Visszatérés: {"meccsek", "dontott" (nem döntetlen meccsek),
    "modell_talalat", "naiv_talalat", "modell_hiba", "naiv_hiba" (gól),
    "javulas_pct" (a modell hibája a formához képest; pozitív: a modell
    a pontosabb), "sorok"} — None, ha ELOREJELZES_PROBA_MIN-nél kevesebb
    meccs jelezhető előre."""
    tortenet: dict = {}
    sorok = []
    for m in meccsek:
        mi, h, v = m.get("minta") or {}, m.get("home"), m.get("away")
        sh, sv = mi.get("home") or {}, mi.get("away") or {}
        f = match_forecast(tortenet.get(h, []), tortenet.get(v, []))
        if f is not None:
            gh, gv = int(sh.get("golok") or 0), int(sv.get("golok") or 0)
            sorok.append({"match_id": m.get("match_id"), "home": h,
                          "away": v, "home_goals": gh, "away_goals": gv,
                          "vart_home": f["home_goals"],
                          "vart_away": f["away_goals"],
                          "naiv_home": f["naiv_home"],
                          "naiv_away": f["naiv_away"],
                          "p_home": f["p_home"], "p_draw": f["p_draw"],
                          "p_away": f["p_away"]})
        tortenet.setdefault(h, []).append((sh, sv))
        tortenet.setdefault(v, []).append((sv, sh))
    return forecast_rows_summary(sorok)


def forecast_rows_summary(sorok: list, csapat: str | None = None) -> dict | None:
    """A próba-sorok (forecast_backtest "sorok") összegzése — a `csapat`
    megadásával csak a csapat meccsei (a szezon-riport csapat-sora).
    Visszatérés a forecast_backtest alakjában, vagy None
    ELOREJELZES_PROBA_MIN-nél kevesebb sornál."""
    if csapat is not None:
        sorok = [r for r in sorok if csapat in (r["home"], r["away"])]
    if len(sorok) < ELOREJELZES_PROBA_MIN:
        return None

    def elojel(x):
        return (x > 0) - (x < 0)

    dontott = [r for r in sorok if r["home_goals"] != r["away_goals"]]
    talal = {k: sum(1 for r in dontott
                    if elojel(r[f"{k}_home"] - r[f"{k}_away"])
                    == elojel(r["home_goals"] - r["away_goals"]))
             for k in ("vart", "naiv")}
    hiba = {k: sum(abs((r[f"{k}_home"] - r[f"{k}_away"])
                       - (r["home_goals"] - r["away_goals"]))
                   for r in sorok) / len(sorok) for k in ("vart", "naiv")}
    javulas = ((hiba["naiv"] - hiba["vart"]) / hiba["naiv"] * 100.0
               if hiba["naiv"] > 0 else 0.0)
    return {"meccsek": len(sorok), "dontott": len(dontott),
            "modell_talalat": talal["vart"], "naiv_talalat": talal["naiv"],
            "modell_hiba": round(hiba["vart"], 2),
            "naiv_hiba": round(hiba["naiv"], 2),
            "javulas_pct": round(javulas, 1), "sorok": sorok}


def forecast_backtest_text(p: dict | None) -> str | None:
    """A próba egy mondatban: "a modell 12 eldőlt meccsből 8 győztest
    talált el (a formáé: 6); a gólkülönbség átlagos hibája 3,1 gól (a
    formáé 4,0; 14 előre jelzett meccs) — a modell 22%-kal pontosabb a
    formánál" (eldőlt meccs nélkül a találat-rész elmarad). Az ítélet a
    lövő-próba küszöbével (PROBA_ITELET_PCT). None próba nélkül."""
    if not p:
        return None
    j = p["javulas_pct"]
    itelet = (f"a modell {j:.0f}%-kal pontosabb a formánál"
              if j >= PROBA_ITELET_PCT else
              f"a modell {-j:.0f}%-kal pontatlanabb a formánál"
              if j <= -PROBA_ITELET_PCT else
              "a modell nagyjából olyan pontos, mint a forma")
    talalat = (f"a modell {p['dontott']} eldőlt meccsből "
               f"{p['modell_talalat']} győztest talált el (a formáé: "
               f"{p['naiv_talalat']}); " if p["dontott"] else "")
    return (f"{talalat}a gólkülönbség átlagos hibája "
            f"{str(p['modell_hiba']).replace('.', ',')} gól (a formáé "
            f"{str(p['naiv_hiba']).replace('.', ',')}; {p['meccsek']} "
            f"előre jelzett meccs) — {itelet}")


# ---- Várható gólszerzők: ki dönthet a következő meccsen -------------------
# A lövő várható gólja a következő meccsen a csapat KORÁBBI meccseiből:
# sávonként a meccsenkénti lövései (csak azokon a meccseken, ahol lőtt —
# a hiányzó lövő nem húzza le) × az xG / lövése × a tanult szorzója
# (_lovo_szorzo; tanulatlan sávban 1) × az ellenfél kapusának szorzója a
# sávban (_kapus_szorzo, az ellenfél korábbi meccseiből; ismeretlenben
# 1). Legalább GOLSZERZO_MIN_MECCS meccsen kellett lőnie; a mondat a
# GOLSZERZO_MAX legveszélyesebbet sorolja. A próbához (scorer_forecast_
# backtest) legalább GOLSZERZO_PROBA_MIN lövő × meccs pár kell.
GOLSZERZO_MIN_MECCS = 2
GOLSZERZO_MAX = 3
GOLSZERZO_PROBA_MIN = 20


def scorer_forecast(lovo_mintak: list, kapus_mintak: list) -> list:
    """Várható gólszerzők a következő meccsen: `lovo_mintak` a csapat
    korábbi meccseinek nyers lövő-mintái (player_model_sample "lovo",
    meccsenként), `kapus_mintak` az ellenfél korábbi meccseinek kapus-
    mintái (player_model_sample "kapus"). Mit jelent edzőileg: kire
    figyeljen a védekezés (az ő gólszerzőik) / kire járassuk a labdát
    (a mieink) — a lövő szokásos lövés-mennyiségéből, -helyéből, a
    befejezéséből és a szemközti kapus sávjaiból. Visszatérés a várható
    gól szerint csökkenőben (holtversenyben mezszám): [{"mez",
    "vart_gol", "vart_loves", "meccsek" (ahány meccsen lőtt), "fo_sav"
    (a legtöbb várható gólt adó sáv), "szorzo" (a lövő szorzója ott),
    "kapus_szorzo" (az ellenfél kapusáé ott), "ertek" (gól-érték a
    cserénél: a várható gólja mínusz ugyanannyi lövés a csapat többi
    lövőjének lövésenkénti várható góljával; None egyetlen lövőnél)}] —
    üres, ha senki sem lőtt legalább GOLSZERZO_MIN_MECCS meccsen."""
    ossz = _lovo_mintak_osszege(lovo_mintak)
    meccsek: dict = {}
    for m in lovo_mintak:
        for mez, savok in (m or {}).items():
            if any(int(v[0]) > 0 for v in savok.values()):
                meccsek[int(mez)] = meccsek.get(int(mez), 0) + 1
    szorzo = _lovo_szorzo(ossz)
    kap: dict = {}
    for m in kapus_mintak:
        for sav, (faced, saves) in (m or {}).items():
            r = kap.setdefault(sav, [0, 0])
            r[0] += int(faced)
            r[1] += int(saves)
    kszorzo = _kapus_szorzo(kap)
    ki = []
    for mez in sorted(ossz):
        db = meccsek.get(mez, 0)
        if db < GOLSZERZO_MIN_MECCS:
            continue
        gol = loves = 0.0
        fo = (0.0, None)
        for sav, (n, _g, xg) in sorted(ossz[mez].items()):
            if n <= 0:
                continue
            ls = szorzo.get(mez, {}).get(sav, 1.0)
            ks = kszorzo.get(sav, 1.0)
            g = (n / db) * (xg / n) * ls * ks
            gol += g
            loves += n / db
            if g > fo[0]:
                fo = (g, sav)
        ki.append({"mez": mez, "vart_gol": round(gol, 1),
                   "vart_loves": round(loves, 1), "meccsek": db,
                   "fo_sav": fo[1],
                   "szorzo": szorzo.get(mez, {}).get(fo[1], 1.0),
                   "kapus_szorzo": kszorzo.get(fo[1], 1.0)})
    # Gól-érték a cserénél: a lövő várható gólja mínusz ugyanannyi lövés
    # a csapat TÖBBI lövőjének átlagos (lövésenkénti várható) befejezésével.
    for r in ki:
        tobbi = [o for o in ki if o["mez"] != r["mez"]]
        tl = sum(o["vart_loves"] for o in tobbi)
        r["ertek"] = (round(r["vart_gol"] - r["vart_loves"]
                            * sum(o["vart_gol"] for o in tobbi) / tl, 1)
                      if tl > 0 else None)
    ki.sort(key=lambda r: (-r["vart_gol"], r["mez"]))
    return ki


# A kulcsember-mondat ennyi gól-értéktől (meccsenként, a csapat többi
# lövőjéhez képest ugyanannyi lövésből) szól.
KULCS_MIN_ERTEK = 0.5
# A szezon-riport kulcsember-listája legfeljebb ennyi lövőt sorol.
KULCS_SZEZON_MAX = 5


def season_key_players(lovo_mintak: list) -> list:
    """A szezon kulcsemberei: a csapat meccsenkénti nyers lövő-mintáiból
    (player_model_sample "lovo") a lövők gól-értéke a cserénél
    (scorer_forecast "ertek", átlagos szemközti kapussal), a legnagyobb
    elöl, legfeljebb KULCS_SZEZON_MAX — mondattal: "a 9-es: +1,4 gól
    meccsenként ugyanannyi lövésből, mint a csapat többi lövője (7,5
    lövés, 3,2 várható gól meccsenként)". Edzőileg: kire épül a
    támadásunk, kinek a hiánya fáj a legjobban."""
    sorok = [r for r in scorer_forecast(lovo_mintak, [])
             if r.get("ertek") is not None]
    sorok.sort(key=lambda r: (-r["ertek"], r["mez"]))

    def sz(x, d=1):
        return f"{x:.{d}f}".replace(".", ",")

    return [{**r, "verdict": (
        f"{mezszam_nevelovel(r['mez'])}: "
        + f"{r['ertek']:+.1f}".replace(".", ",")
        + " gól meccsenként ugyanannyi lövésből, mint a csapat többi "
        f"lövője ({sz(r['vart_loves'])} lövés, {sz(r['vart_gol'])} várható "
        "gól meccsenként)")} for r in sorok[:KULCS_SZEZON_MAX]]


def key_player_text(sorok: list) -> str | None:
    """A kulcsember egy mondatban: a legnagyobb gól-értékű lövő (a
    scorer_forecast "ertek" mezője), ha legalább KULCS_MIN_ERTEK — "a
    9-es: ugyanannyi lövésből 1,4 góllal többet ér meccsenként, mint a
    csapat többi lövője". Edzőileg: kit kell kivenni a játékból (az
    övék) / kit kell lövéshez juttatni (a miénk). None, ha nincs ilyen."""
    jo = [r for r in sorok or [] if r.get("ertek") is not None]
    if not jo:
        return None
    r = min(jo, key=lambda r: (-r["ertek"], r["mez"]))
    if r["ertek"] < KULCS_MIN_ERTEK:
        return None
    return (f"{mezszam_nevelovel(r['mez'])}: ugyanannyi lövésből "
            + f"{r['ertek']:.1f}".replace(".", ",")
            + " góllal többet ér meccsenként, mint a csapat többi lövője")


def key_player_absence(sorok: list, vart_gol: float | None) -> dict | None:
    """Mi lenne nélküle: a kulcsember (a legnagyobb gól-értékű lövő,
    legalább KULCS_MIN_ERTEK) kiesésekor a csapat várható gólja — a
    meccs-előrejelzés várható góljából (`vart_gol`) a gól-értéke
    levonva (a lövéseit a többiek viszik, a lövésenkénti átlagukkal).
    Visszatérés: {"mez", "ertek", "vart", "nelkule", "text"} vagy None."""
    if vart_gol is None:
        return None
    jo = [r for r in sorok or [] if r.get("ertek") is not None]
    if not jo:
        return None
    r = min(jo, key=lambda r: (-r["ertek"], r["mez"]))
    if r["ertek"] < KULCS_MIN_ERTEK:
        return None
    nelkule = round(max(0.0, vart_gol - r["ertek"]), 1)
    return {"mez": r["mez"], "ertek": r["ertek"], "vart": vart_gol,
            "nelkule": nelkule,
            "text": (f"ha {mezszam_nevelovel(r['mez'])} kiesik, a várható "
                     f"gól {vart_gol:.0f} helyett "
                     + f"{nelkule:.1f}".replace(".", ","))}


def scorer_forecast_text(sorok: list) -> str | None:
    """A várható gólszerzők egy mondatban (a GOLSZERZO_MAX első): "a 9-es
    5,2 gól (főleg távolról: 1,3× befejező, a szemközti kapus ott 1,2×
    annyi gólt kap, mint az átlag), a 7-es 4,1 gól, a 11-es 3,0 gól" — a
    záradék csak az elsőnél, és csak a
    LOVO_FELIRAT_ELTERES-nél jobban eltérő szorzóval. None üres listára."""
    if not sorok:
        return None

    def sz(x):
        return f"{x:.1f}".replace(".", ",")

    reszek = []
    for i, r in enumerate(sorok[:GOLSZERZO_MAX]):
        resz = f"{mezszam_nevelovel(r['mez'])} {sz(r['vart_gol'])} gól"
        if i == 0 and r.get("fo_sav"):
            ok = []
            if abs(r["szorzo"] - 1.0) >= LOVO_FELIRAT_ELTERES:
                ok.append(f"{sz(r['szorzo'])}× befejező")
            if abs(r["kapus_szorzo"] - 1.0) >= LOVO_FELIRAT_ELTERES:
                ok.append(f"a szemközti kapus ott {sz(r['kapus_szorzo'])}× "
                          "annyi gólt kap, mint az átlag")
            if ok:
                resz += (f" (főleg {KAPUS_SAV_NEV[r['fo_sav']]}: "
                         + ", ".join(ok) + ")")
        reszek.append(resz)
    return ", ".join(reszek)


def scorer_forecast_backtest(meccsek: list,
                             csapat: str | None = None) -> dict | None:
    """A várható gólszerzők próbája: `meccsek` időrendben [{"match_id",
    "home", "away" (csapatnevek), "minta": {"home" / "away":
    player_model_sample}}]. Minden meccsen és oldalon a lövők várható
    gólja CSAK a korábbi meccsekből (scorer_forecast: a csapat korábbi
    lövő-mintái, az ellenfél korábbi kapus-mintái), összevetve a meccsen
    lőtt góljaival — azokra a lövőkre, akik a meccsen lőttek. A
    viszonyítás a lövő korábbi meccsenkénti gólátlaga (a "forma").
    A `csapat` megadásával csak a csapat lövőinek párjai számítanak (a
    szezon-riport csapat-sora). Edzőileg: mennyire lehet a "rá
    figyeljetek" mondatra építeni.
    Visszatérés: {"parok" (lövő × meccs), "modell_hiba", "naiv_hiba"
    (átlagos abszolút hiba, gól), "javulas_pct", "verdict"} — None
    GOLSZERZO_PROBA_MIN-nél kevesebb párnál."""
    lovo_t: dict = {}
    kapus_t: dict = {}
    gol_t: dict = {}
    hm = hn = 0.0
    parok = 0
    for m in meccsek:
        mi = m.get("minta") or {}
        nevek = {"home": m.get("home"), "away": m.get("away")}
        for side, masik in (("home", "away"), ("away", "home")):
            nev, ellen = nevek[side], nevek[masik]
            if csapat is not None and nev != csapat:
                continue
            sorok = {r["mez"]: r for r in scorer_forecast(
                lovo_t.get(nev, []), kapus_t.get(ellen, []))}
            for mez, savok in ((mi.get(side) or {}).get("lovo") or {}).items():
                mez = int(mez)
                if mez not in sorok or not any(int(v[0]) > 0
                                               for v in savok.values()):
                    continue
                valodi = sum(int(v[1]) for v in savok.values())
                kor = gol_t.get((nev, mez), [])
                naiv = sum(kor) / len(kor) if kor else 0.0
                hm += abs(sorok[mez]["vart_gol"] - valodi)
                hn += abs(naiv - valodi)
                parok += 1
        for side, masik in (("home", "away"), ("away", "home")):
            nev = nevek[side]
            minta = mi.get(side) or {}
            lovo_t.setdefault(nev, []).append(minta.get("lovo") or {})
            kapus_t.setdefault(nev, []).append(minta.get("kapus") or {})
            for mez, savok in (minta.get("lovo") or {}).items():
                if any(int(v[0]) > 0 for v in savok.values()):
                    gol_t.setdefault((nev, int(mez)), []).append(
                        sum(int(v[1]) for v in savok.values()))
    if parok < GOLSZERZO_PROBA_MIN:
        return None
    mh, nh = hm / parok, hn / parok
    j = (nh - mh) / nh * 100.0 if nh > 0 else 0.0

    def sz(x):
        return f"{x:.2f}".replace(".", ",")

    itelet = (f"a modell {j:.0f}%-kal pontosabb a formánál"
              if j >= PROBA_ITELET_PCT else
              f"a modell {-j:.0f}%-kal pontatlanabb a formánál"
              if j <= -PROBA_ITELET_PCT else
              "a modell nagyjából olyan pontos, mint a forma")
    return {"parok": parok, "modell_hiba": round(mh, 2),
            "naiv_hiba": round(nh, 2), "javulas_pct": round(j, 1),
            "verdict": (f"a lövők várható gólja {parok} lövő × meccs páron "
                        f"átlagosan {sz(mh)} góllal tért el (a formáé "
                        f"{sz(nh)}) — {itelet}")}


# ---- Várakozás és valóság: a meccs után -----------------------------------
# A meccs után a meccs előtti várakozás (csak a KORÁBBI meccsekből) a
# valósághoz mérve: az eredmény (VISSZA_GOL góltól mondja ki, melyik
# csapat járt a várt felett / alatt), a lövők (VISSZA_LOVO_GOL góltól,
# legfeljebb VISSZA_MAX sor, a legnagyobb eltérés elöl) és a fal.
VISSZA_GOL = 2.0
VISSZA_LOVO_GOL = 1.5
VISSZA_MAX = 4


def forecast_review(nevek: dict, f: dict | None, golok: dict,
                    golszerzok: dict | None = None,
                    lovo_valodi: dict | None = None,
                    vedekezes: dict | None = None,
                    formak_valodi: dict | None = None) -> dict:
    """Várakozás és valóság a meccs után: `f` a meccs előtti előrejelzés
    (match_forecast, a korábbi meccsekből), `golok` a valódi gól
    oldalanként; `golszerzok` oldalanként a várható gólszerzők
    (scorer_forecast), `lovo_valodi` a meccs nyers lövő-mintája
    (player_model_sample "lovo"); `vedekezes` a várható rendszer
    (defense_system_forecast), `formak_valodi` a meccs "formak" mintája.
    Mit jelent edzőileg: hol lepett meg minket a meccs — ki lőtt
    többet / kevesebbet a vártnál, más fallal jöttek-e — a videó-elemzés
    és a felderítés javítása ide. Visszatérés: {"eredmeny" (vagy None),
    "lovok", "vedekezes", "sorok" (a mondatok)}."""
    sorok: list = []
    eredmeny = None

    def sz(x):
        return f"{x:.1f}".replace(".", ",")

    if f:
        gh, ga = int(golok.get("home") or 0), int(golok.get("away") or 0)
        eh, ea = round(gh - f["home_goals"], 1), round(ga - f["away_goals"], 1)
        eredmeny = {"vart_home": f["home_goals"], "vart_away": f["away_goals"],
                    "home": gh, "away": ga, "elteres_home": eh,
                    "elteres_away": ea}
        sor = (f"Várakozás: {nevek['home']} {f['home_goals']:.0f}–"
               f"{f['away_goals']:.0f} {nevek['away']} — lett: {gh}–{ga}")
        nagy = [(abs(e), side) for e, side in ((eh, "home"), (ea, "away"))
                if abs(e) >= VISSZA_GOL]
        if nagy:
            _, side = max(nagy)
            e = eh if side == "home" else ea
            sor += (f" ({nevek[side]} {sz(abs(e))} góllal a várt "
                    f"{'felett' if e > 0 else 'alatt'})")
        sorok.append(sor)
    lovok = []
    for side in ("home", "away"):
        valodi = {int(m): sum(int(v[1]) for v in sv.values())
                  for m, sv in ((lovo_valodi or {}).get(side) or {}).items()}
        for r in (golszerzok or {}).get(side) or []:
            g = valodi.get(int(r["mez"]), 0)
            e = round(g - r["vart_gol"], 1)
            if abs(e) >= VISSZA_LOVO_GOL:
                lovok.append({"team": side, "mez": int(r["mez"]),
                              "vart": r["vart_gol"], "valodi": g,
                              "elteres": e})
    lovok.sort(key=lambda r: (-abs(r["elteres"]), r["team"], r["mez"]))
    lovok = lovok[:VISSZA_MAX]
    for r in lovok:
        sorok.append(f"{nevek[r['team']]}: {mezszam_nevelovel(r['mez'])} "
                     f"{r['valodi']} gólt lőtt a várt {sz(r['vart'])} helyett")
    vedek = []
    for side in ("home", "away"):
        v = (vedekezes or {}).get(side)
        most = _fo_rendszer((formak_valodi or {}).get(side) or {})
        if v and most and most != v["fo"]:
            vedek.append({"team": side, "vart": v["fo"], "valodi": most})
            sorok.append(f"{nevek[side]} {most} fallal védekezett a várt "
                         f"{v['fo']} helyett")
    if f and len(sorok) == 1 and not lovok and not vedek \
            and eredmeny and max(abs(eredmeny["elteres_home"]),
                                 abs(eredmeny["elteres_away"])) < VISSZA_GOL:
        sorok.append("A meccs nagyjából a várakozás szerint alakult")
    return {"eredmeny": eredmeny, "lovok": lovok, "vedekezes": vedek,
            "sorok": sorok}


# A félidei várakozás és valóság ennyi játékpercnél szól (a meccs fele).
FELIDO_PERC = 30


def _review_until(match: Match, perc: float, nevek: dict, f: dict | None,
                  golszerzok: dict | None = None,
                  vedekezes: dict | None = None,
                  config: TacticsConfig | None = None) -> dict:
    """Várakozás és valóság a `perc`. percig (CSAK az addigi kockák —
    okszerű): a meccs előtti várakozás (`f`, `golszerzok`, `vedekezes` —
    a korábbi meccsekből) az eredményre és a lövőkre a perc-arányos
    részre (perc / ELO_MECCS_PERC), a fal az addigi fő rendszer
    (forecast_review). A félidei összevetés és az időkérés-jegyzet közös
    magja. Visszatérés: {"t", "t_s", "perc", "sorok", …a forecast_review
    mezői} — üres "sorok" és None "t", ha a meccs még nem ért el idáig."""
    from .event_detection import EventType, detect_shots
    config = config or TacticsConfig()
    ures = {"t": None, "t_s": None, "perc": perc, "eredmeny": None,
            "lovok": [], "vedekezes": [], "sorok": []}
    if not match.frames:
        return ures
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    t0 = match.frames[0].t
    hatar = t0 + int(round(perc * 60 * fps))
    eddig = [fr for fr in match.frames if fr.t <= hatar]
    if len(eddig) < 2 or eddig[-1].t < hatar - fps:
        return ures
    resz = Match(meta=match.meta, frames=eddig)
    arany = perc / ELO_MECCS_PERC
    golok = {"home": 0, "away": 0}
    for e in detect_shots(resz, config):
        if e.type == EventType.GOAL and e.team.value in golok:
            golok[e.team.value] += 1
    minta = {side: player_model_sample(resz, Team(side), config)
             for side in ("home", "away")}
    fh = ({**f, "home_goals": round(f["home_goals"] * arany, 1),
           "away_goals": round(f["away_goals"] * arany, 1)} if f else None)
    gh = {side: [{**r, "vart_gol": round(r["vart_gol"] * arany, 1)}
                 for r in (golszerzok or {}).get(side) or []]
          for side in ("home", "away")}
    r = forecast_review(nevek, fh, golok, golszerzok=gh,
                        lovo_valodi={k: v["lovo"] for k, v in minta.items()},
                        vedekezes=vedekezes,
                        formak_valodi={k: v["formak"] for k, v in minta.items()})
    return {**r, "t": hatar, "t_s": round(hatar / fps, 1), "perc": perc}


def halftime_review(match: Match, nevek: dict, f: dict | None,
                    golszerzok: dict | None = None,
                    vedekezes: dict | None = None,
                    config: TacticsConfig | None = None) -> dict:
    """Várakozás és valóság a FÉLIDŐBEN: a meccs előtti várakozás (`f`,
    `golszerzok`, `vedekezes` — a korábbi meccsekből) a FELIDO_PERC-ig
    látott valósághoz mérve (_review_until — CSAK az addigi kockák): az
    eredmény és a lövők várakozása a perc-arányos részre (fele), a fal a
    félidő fő rendszere. Mit jelent edzőileg: a félidei beszéd tényei —
    ki jár a várt felett / alatt, más fallal jöttek-e. Visszatérés: {"t",
    "t_s", "perc", "sorok", …a forecast_review mezői} — üres "sorok", ha a
    meccs még nem ért el a félidőig."""
    r = _review_until(match, FELIDO_PERC, nevek, f, golszerzok=golszerzok,
                      vedekezes=vedekezes, config=config)
    # A mondatok a félidőre szólnak (a forecast_review a meccs végére).
    sorok = [x.replace("Várakozás: ", "Félidei várakozás: ", 1)
              .replace(" — lett: ", " — a félidőben: ", 1)
              .replace("A meccs nagyjából a várakozás szerint alakult",
                       "Az első félidő nagyjából a várakozás szerint alakult")
             for x in r["sorok"]]
    return {**r, "sorok": sorok}


# ---- Időkérés-jegyzet ------------------------------------------------------
# Az időkérés egy perce a padon: a jegyzet elöl az utolsó IDO_JEGYZET_S
# másodperc állása, ha sorozat fut a kérő ellen, az időkérés próbájának
# ítélete, aztán a meccs előtti várakozás (a korábbi meccsekből) az
# időkérésig látott valósághoz mérve, a perc-arányos részre (mint a
# félidei összevetés).
IDO_JEGYZET_S = 300.0


def timeout_brief(match: Match, perc: float, nevek: dict, f: dict | None,
                  golszerzok: dict | None = None,
                  vedekezes: dict | None = None, kero: str | None = None,
                  idokeres_proba: dict | None = None,
                  config: TacticsConfig | None = None) -> dict:
    """Időkérés-jegyzet a `perc`. percben (CSAK az addigi kockák —
    okszerű): elöl az utolsó IDO_JEGYZET_S másodperc állása; ha a `kero`
    ("home" / "away", a kérő oldal) ellen legalább IDO_SOROZAT gólos
    sorozat fut, a sorozat és az időkérés próbájának ítélete
    (`idokeres_proba`, timeout_run_backtest); aztán a várakozás és
    valóság eddig (_review_until — a mondatok "eddig"-re fordítva). Mit
    jelent edzőileg: az időkérés egy percében a padnak a tények — mi
    történt az utolsó percekben, ki jár a várt felett, más fallal
    jöttek-e. Visszatérés: {"t", "t_s", "perc", "ora" ("pp:mm"), "kero",
    "sorok", …a forecast_review mezői} — üres "sorok", ha a meccs még nem
    ért el idáig."""
    from .event_detection import EventType, detect_shots
    config = config or TacticsConfig()
    r = _review_until(match, perc, nevek, f, golszerzok=golszerzok,
                      vedekezes=vedekezes, config=config)
    mp = int(round(perc * 60))
    ki = {**r, "ora": f"{mp // 60:02d}:{mp % 60:02d}", "kero": kero}
    if r["t"] is None:
        return ki
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    hatar = r["t"]
    tol = hatar - IDO_JEGYZET_S * fps
    utolso = {"home": 0, "away": 0}
    cur, hossz = None, 0
    for e in sorted(detect_shots(match, config), key=lambda e: e.t):
        if e.type != EventType.GOAL or e.team.value not in utolso \
                or e.t > hatar:
            continue
        if e.t > tol:
            utolso[e.team.value] += 1
        if e.team.value == cur:
            hossz += 1
        else:
            cur, hossz = e.team.value, 1
    elol = [f"Az utolsó {IDO_JEGYZET_S / 60:.0f} percben: {nevek['home']} "
            f"{utolso['home']}–{utolso['away']} {nevek['away']}"]
    if kero in ("home", "away") and cur not in (None, kero) \
            and hossz >= IDO_SOROZAT:
        sor = f"{nevek[cur]} {hossz}-0-s sorozatban van"
        if idokeres_proba and idokeres_proba.get("verdict"):
            sor += f" — {idokeres_proba['verdict']}"
        elol.append(sor)
    sorok = [x.replace("Várakozás: ", "Várakozás eddig: ", 1)
              .replace(" — lett: ", " — eddig: ", 1)
              .replace("A meccs nagyjából a várakozás szerint alakult",
                       "A meccs eddig nagyjából a várakozás szerint alakult")
             for x in r["sorok"]]
    return {**ki, "sorok": elol + sorok}


def live_timeout_briefs(match: Match, nevek: dict, f: dict | None,
                        golszerzok: dict | None = None,
                        vedekezes: dict | None = None,
                        idokeres_proba: dict | None = None,
                        config: TacticsConfig | None = None) -> dict:
    """Élő időkérés-jegyzetek: minden felismert időkérés (stoppages.
    detect_stoppages "időkérés" fajtája) kezdetén a timeout_brief, a
    valószínű kérő oldallal. Visszatérés: {"jegyzetek": [{…timeout_brief,
    "text"}]} — időrendben."""
    from .stoppages import detect_stoppages
    config = config or TacticsConfig()
    out: list = []
    if not match.frames:
        return {"jegyzetek": out}
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    t0 = match.frames[0].t
    for st in detect_stoppages(match, config):
        if st.get("kind") != "időkérés":
            continue
        b = timeout_brief(match, (st["start_frame"] - t0) / fps / 60.0,
                          nevek, f, golszerzok=golszerzok,
                          vedekezes=vedekezes, kero=st.get("likely_team"),
                          idokeres_proba=idokeres_proba, config=config)
        if b["sorok"]:
            out.append({**b, "text": timeout_brief_text(b, nevek)})
    return {"jegyzetek": out}


def timeout_brief_text(b: dict, nevek: dict) -> str:
    """Az időkérés-jegyzet egy sora: "Időkérés-jegyzet (pp:mm, a kérő):
    mondat; mondat; …"."""
    kero = nevek.get(b.get("kero")) if b.get("kero") else None
    return (f"Időkérés-jegyzet ({b.get('ora')}"
            + (f", {kero} kér időt" if kero else "") + "): "
            + "; ".join(b.get("sorok") or []))


# ---- A forró kéz próbája: kitart-e a napi forma ----------------------------
# A lövő napi formája a helyzetei feletti / alatti befejezés: (gól − xG) /
# lövés. A próba a könyvtár lövő × meccs párjain (félidőnként legalább
# FORMA_MIN_LOVES lövés): az első félidőben FORMA_KUSZOB felett ("forró")
# és alatta ("hideg") befejezők második félideje — ha a forróké
# FORMA_ITELET_PP százalékponttal jobb, a napi forma kitart; ha nem, a
# lövő a második félidőben visszaáll a szokásos szintjére, és a modell a
# jobb tipp. Csoportonként legalább FORMA_MIN_PAR pár kell. Élőben a
# 15., 30. és 45. percben szól, ha egy lövő legalább FORMA_MIN_LOVES
# lövésből FORMA_ELO_GOL góllal a modell várakozása felett vagy alatt jár.
FORMA_MIN_LOVES = 4
FORMA_KUSZOB = 0.15
FORMA_MIN_PAR = 8
FORMA_ITELET_PP = 5.0
FORMA_ELO_GOL = 1.5


def shooter_form_sample(match: Match, team: Team,
                        config: TacticsConfig | None = None) -> dict:
    """A forró kéz próbájának NYERS, JSON-barát meccs-mintája: a `team`
    mezszámos lövői félidőnként — {mez (str): [[lövés, gól, xG] az 1.
    félidőben, [lövés, gól, xG] a 2.-ban]}. A félidő-határ a felismert
    szünet (halftime.detect_halftime), különben a felvétel közepe."""
    from .halftime import detect_halftime
    config = config or TacticsConfig()
    if not match.frames:
        return {}
    try:
        ht = detect_halftime(match)
    except Exception:
        ht = None
    if ht is None:
        ht = match.frames[len(match.frames) // 2].t
    ki: dict = {}
    for mez, sh in _lovesek_mezszammal(match, team, config):
        r = ki.setdefault(str(mez), [[0, 0, 0.0], [0, 0, 0.0]])[
            0 if sh["t"] < ht else 1]
        r[0] += 1
        r[1] += 1 if sh["outcome"] == "goal" else 0
        r[2] = round(r[2] + float(sh["xg"]), 3)
    return ki


def hot_hand_backtest(mintak: list) -> dict | None:
    """A forró kéz próbája: `mintak` a könyvtár lövő-forma mintái
    (shooter_form_sample, csapat × meccs). A félidőnként legalább
    FORMA_MIN_LOVES lövéses párok közül az első félidőben forró (gól − xG
    lövésenként ≥ FORMA_KUSZOB) és hideg (≤ −FORMA_KUSZOB) lövők második
    félidei befejezése (gól − xG lövésenként, százalékpontban). Mit
    jelent edzőileg: a "járassátok a forró kezűre" / "vegyétek el a
    lövést a hidegtől" tanács csak akkor jó, ha a napi forma kitart —
    különben a modell (a szezon szorzója) a jobb tipp. Visszatérés:
    {"forro", "hideg" (párok), "forro_pp", "hideg_pp" (a második félidő
    gól − xG százalékpontban), "kulonbseg_pp", "itelet" ("kitart" /
    "visszaall"), "verdict"} — None, ha valamelyik csoportban
    FORMA_MIN_PAR-nál kevesebb pár van."""
    forro, hideg = [], []
    for m in mintak:
        for _mez, (f1, f2) in (m or {}).items():
            if int(f1[0]) < FORMA_MIN_LOVES or int(f2[0]) < FORMA_MIN_LOVES:
                continue
            r1 = (int(f1[1]) - float(f1[2])) / int(f1[0])
            r2 = (int(f2[1]) - float(f2[2])) / int(f2[0])
            if r1 >= FORMA_KUSZOB:
                forro.append(r2)
            elif r1 <= -FORMA_KUSZOB:
                hideg.append(r2)
    if len(forro) < FORMA_MIN_PAR or len(hideg) < FORMA_MIN_PAR:
        return None
    fp = sum(forro) / len(forro) * 100.0
    hp = sum(hideg) / len(hideg) * 100.0
    k = fp - hp
    kitart = k >= FORMA_ITELET_PP

    def sz(x):
        return f"{x:+.0f}"

    return {"forro": len(forro), "hideg": len(hideg),
            "forro_pp": round(fp, 1), "hideg_pp": round(hp, 1),
            "kulonbseg_pp": round(k, 1),
            "itelet": "kitart" if kitart else "visszaall",
            "verdict": (f"az első félidőben forró kezű lövők ({len(forro)} "
                        f"pár) a második félidőben lövésenként {sz(fp)} "
                        f"százalékpont gólt szereztek a helyzeteikhez képest "
                        f"(a hidegek, {len(hideg)} pár: {sz(hp)}) — "
                        + ("a napi forma kitart: a forró kezűt érdemes "
                           "játékba hozni" if kitart else
                           "a napi forma nem tart ki: a modellre (a "
                           "szezon szorzójára) építsetek"))}


def live_form_alerts(match: Match, tamadas: dict | None = None,
                     kapus: dict | None = None,
                     proba: dict | None = None,
                     config: TacticsConfig | None = None) -> dict:
    """Élő napi forma: a LIVE_AJANLO_PERCEK perceiben csapatonként (a
    TÁMADÓ oldal kispadjának) az a lövő, aki az addigi lövéseiből (CSAK
    az addigi kockák — okszerű; legalább FORMA_MIN_LOVES) a modell
    várakozása felett vagy alatt FORMA_ELO_GOL góllal jár. A várakozás
    lövésenként az xG × a lövő tanult szorzója (`tamadas`: {"home" /
    "away": AttackModel}, a szezon korábbi meccseiből) × a szemközti
    kapus szorzója (`kapus`: {…: {sáv: szorzó}}). A tanács a forró kéz
    próbájától (`proba`, hot_hand_backtest) függ: ha a napi forma nem
    tart ki, a modellre kell építeni ("ne vegyétek el tőle a lövést" /
    "ne építsetek csak rá"), ha kitart, a formára. Lövőnként és
    irányonként egyszer szól — a támadó kispadnak ("nezopont":
    "tamado") és a védőnek is ("vedo": a forró kezű ellen fogjátok-e
    szorosan, vagy ne bontsátok meg miatta a falat). Visszatérés:
    {"alerts": [{"t", "t_s", "perc", "team" (akinek szól), "team_name",
    "nezopont", "mez", "lovesek", "golok", "vart", "irany" ("forro" /
    "hideg"), "text"}]}."""
    config = config or TacticsConfig()
    alerts: list = []
    if not match.frames:
        return {"alerts": alerts}
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    t0 = match.frames[0].t
    nevek = {"home": match.meta.home_team, "away": match.meta.away_team}
    itelet = (proba or {}).get("itelet")
    szolt: set = set()
    for perc in LIVE_AJANLO_PERCEK:
        hatar = t0 + int(round(perc * 60 * fps))
        eddig = [fr for fr in match.frames if fr.t <= hatar]
        if len(eddig) < 2 or eddig[-1].t < hatar - fps:
            continue      # a meccs még nem ért el idáig
        resz = Match(meta=match.meta, frames=eddig)
        for side, team in (("home", Team.HOME), ("away", Team.AWAY)):
            masik = "away" if side == "home" else "home"
            tm = (tamadas or {}).get(side)
            ks = (kapus or {}).get(masik) or {}
            goal_x = config.attacks_toward_x(team)
            lov: dict = {}
            for mez, sh in _lovesek_mezszammal(resz, team, config):
                sav = kapus_sav(sh["x"], sh["y"], goal_x)
                lsz = (tm.lovok.get(mez, {}).get(sav, 1.0)
                       if tm is not None else 1.0)
                r = lov.setdefault(mez, [0, 0, 0.0])
                r[0] += 1
                r[1] += 1 if sh["outcome"] == "goal" else 0
                r[2] += float(sh["xg"]) * lsz * ks.get(sav, 1.0)
            for mez in sorted(lov):
                n, g, v = lov[mez]
                if n < FORMA_MIN_LOVES or abs(g - v) < FORMA_ELO_GOL:
                    continue
                irany = "forro" if g > v else "hideg"
                if (side, mez, irany) in szolt:
                    continue
                szolt.add((side, mez, irany))
                vsz = f"{v:.1f}".replace(".", ",")
                ki = (f"{'Forró' if irany == 'forro' else 'Hideg'} kéz "
                      f"({perc}. perc): {nevek[side]} — "
                      f"{mezszam_nevelovel(mez)} ma {g}/{n} (a modell "
                      f"szerint {vsz} gól)")
                if itelet == "visszaall":
                    ki += (" — a könyvtár szerint a napi forma nem tart "
                           "ki: " + ("ne vegyétek el tőle a lövést, a "
                                     "modell szerint jön" if irany == "hideg"
                                     else "ne építsetek csak rá a "
                                     "hajrában"))
                elif itelet == "kitart":
                    ki += (" — a könyvtár szerint a napi forma kitart: "
                           + ("járassátok rá a labdát" if irany == "forro"
                              else "adjátok a lövést másnak"))
                else:
                    ki += (" — a könyvtár még nem dönti el, kitart-e a "
                           "napi forma")
                alap = {"t": hatar, "t_s": round(hatar / fps, 1),
                        "perc": perc, "mez": mez, "lovesek": n, "golok": g,
                        "vart": round(v, 1), "irany": irany}
                alerts.append({**alap, "team": side, "team_name": nevek[side],
                               "nezopont": "tamado", "text": ki})
                # A védő kispadnak ugyanez a saját szemszögéből.
                vk = (f"{'Forró' if irany == 'forro' else 'Hideg'} kéz az "
                      f"ellenfélnél ({perc}. perc): {nevek[side]} — "
                      f"{mezszam_nevelovel(mez)} ma {g}/{n} (a modell "
                      f"szerint {vsz} gól)")
                if itelet == "visszaall":
                    vk += (" — a könyvtár szerint a napi forma nem tart "
                           "ki: " + ("ne bontsátok meg miatta a falat"
                                     if irany == "forro" else
                                     "a modell szerint jön, ne engedjétek "
                                     "szabadon lőni"))
                elif itelet == "kitart":
                    vk += (" — a könyvtár szerint a napi forma kitart: "
                           + ("fogjátok szorosan, kettőzzetek rá"
                              if irany == "forro" else
                              "rá ne lépjetek ki, hagyjátok lőni"))
                else:
                    vk += (" — a könyvtár még nem dönti el, kitart-e a "
                           "napi forma")
                alerts.append({**alap, "team": masik,
                               "team_name": nevek[masik],
                               "nezopont": "vedo", "text": vk})
    alerts.sort(key=lambda a: (a["t"], a["team"], a["mez"], a["nezopont"]))
    return {"alerts": alerts}


# ---- A kapus napi formája: kitart-e ----------------------------------------
# A kapus napi formája a várt felett / alatt védett gól: (várt kapott gól
# − kapott gól) / kaputra érkezett lövés, ahol a várt kapott gól az
# átlagos kapus sávonkénti gól-aránya (KAPUS_ALAP_GOL). A próba a
# könyvtár kapus × meccs párjain (félidőnként legalább KF_MIN_LOVES
# kaputra érkezett lövés): az első félidőben forró (KF_KUSZOB felett) és
# hideg kapusok második félideje — ha a forróké FORMA_ITELET_PP
# százalékponttal jobb, a kapus napi formája kitart. Élőben a 15., 30.
# és 45. percben szól, ha a kapuban álló kapus legalább KF_MIN_LOVES
# lövésből KF_ELO_GOL góllal a saját szokásos szintje felett vagy alatt
# jár (a szezon kapus-szorzójával).
KF_MIN_LOVES = 6
KF_KUSZOB = 0.12
KF_MIN_PAR = 6
KF_ELO_GOL = 1.5


def _kapus_varhato(minta: dict, szorzo: dict | None = None) -> float:
    """Egy kapus sávonkénti mintájából ({sáv: [kaputra érkezett,
    védett]}) a várt kapott gól: kaputra × KAPUS_ALAP_GOL[sáv] × a kapus
    szorzója a sávban (üres: átlagos kapus)."""
    return sum(int(v[0]) * KAPUS_ALAP_GOL.get(s, 0.55)
               * float((szorzo or {}).get(s, 1.0))
               for s, v in (minta or {}).items())


def keeper_form_sample(match: Match, team: Team,
                       config: TacticsConfig | None = None) -> dict:
    """A kapus napi formájának NYERS, JSON-barát meccs-mintája: a `team`
    kapusai félidőnként — {kapus mez (str): [[kaputra, kapott, várt
    kapott] az 1. félidőben, ugyanez a 2.-ban]}; a várt kapott az
    átlagos kapusé (_kapus_varhato). A félidő-határ a felismert szünet,
    különben a felvétel közepe."""
    from .halftime import detect_halftime
    config = config or TacticsConfig()
    if not match.frames:
        return {}
    try:
        ht = detect_halftime(match)
    except Exception:
        ht = None
    if ht is None:
        ht = match.frames[len(match.frames) // 2].t
    ki: dict = {}
    for i, frames in enumerate(([f for f in match.frames if f.t < ht],
                                [f for f in match.frames if f.t >= ht])):
        if len(frames) < 2:
            continue
        resz = Match(meta=match.meta, frames=frames)
        for mez, minta in _kapus_minta_kapusonkent(resz, team, config).items():
            faced = sum(int(v[0]) for v in minta.values())
            kapott = sum(int(v[0]) - int(v[1]) for v in minta.values())
            r = ki.setdefault(str(mez), [[0, 0, 0.0], [0, 0, 0.0]])[i]
            r[0] += faced
            r[1] += kapott
            r[2] = round(r[2] + _kapus_varhato(minta), 3)
    return ki


def keeper_hot_hand_backtest(mintak: list) -> dict | None:
    """A kapus napi formájának próbája: `mintak` a könyvtár kapus-forma
    mintái (keeper_form_sample, csapat × meccs). A félidőnként legalább
    KF_MIN_LOVES lövéses párok közül az első félidőben forró (várt
    kapott − kapott lövésenként ≥ KF_KUSZOB) és hideg (≤ −KF_KUSZOB)
    kapusok második félideje, százalékpontban. Mit jelent edzőileg: a
    "rossz napja van, cseréljük" döntés csak akkor jó, ha a kapus napi
    formája kitart — különben a szokásos szintje a jobb tipp.
    Visszatérés: {"forro", "hideg", "forro_pp", "hideg_pp",
    "kulonbseg_pp", "itelet" ("kitart" / "visszaall"), "verdict"} —
    None, ha valamelyik csoportban KF_MIN_PAR-nál kevesebb pár van."""
    forro, hideg = [], []
    for m in mintak:
        for _mez, (f1, f2) in (m or {}).items():
            if int(f1[0]) < KF_MIN_LOVES or int(f2[0]) < KF_MIN_LOVES:
                continue
            r1 = (float(f1[2]) - int(f1[1])) / int(f1[0])
            r2 = (float(f2[2]) - int(f2[1])) / int(f2[0])
            if r1 >= KF_KUSZOB:
                forro.append(r2)
            elif r1 <= -KF_KUSZOB:
                hideg.append(r2)
    if len(forro) < KF_MIN_PAR or len(hideg) < KF_MIN_PAR:
        return None
    fp = sum(forro) / len(forro) * 100.0
    hp = sum(hideg) / len(hideg) * 100.0
    k = fp - hp
    kitart = k >= FORMA_ITELET_PP
    return {"forro": len(forro), "hideg": len(hideg),
            "forro_pp": round(fp, 1), "hideg_pp": round(hp, 1),
            "kulonbseg_pp": round(k, 1),
            "itelet": "kitart" if kitart else "visszaall",
            "verdict": (f"az első félidőben jól védő kapusok ({len(forro)} "
                        f"pár) a második félidőben lövésenként {fp:+.0f} "
                        f"százalékponttal védtek a vártnál többet (a "
                        f"gyengén védők, {len(hideg)} pár: {hp:+.0f}) — "
                        + ("a kapus napi formája kitart: a rossz napon "
                           "érdemes kapust cserélni" if kitart else
                           "a kapus napi formája nem tart ki: egy gyenge "
                           "félidő miatt nem kell kapust cserélni"))}


def live_keeper_form_alerts(match: Match, kapus_szorzok: dict | None = None,
                            proba: dict | None = None,
                            config: TacticsConfig | None = None) -> dict:
    """Élő kapus-forma: a LIVE_AJANLO_PERCEK perceiben az a kapus, aki az
    addigi lövésekből (CSAK az addigi kockák — okszerű; legalább
    KF_MIN_LOVES kaputra érkezett) KF_ELO_GOL góllal a SAJÁT szokásos
    szintje (a szezon kapus-szorzója, `kapus_szorzok`: {"home" / "away":
    {kapus mez: {sáv: szorzó}}}; ismeretlenben az átlagos kapus) felett
    vagy alatt véd. A tanács a kapus napi formájának próbájától
    (`proba`, keeper_hot_hand_backtest) függ, mindkét kispadnak: a
    sajátnak ("sajat": maradjon / érdemes cserélni / ne cseréljétek egy
    szakasz miatt) és az ellenfélnek ("ellenfel": jobb helyzetekből /
    lőjetek bátran). Kapusonként és irányonként egyszer. Visszatérés:
    {"alerts": [{"t", "t_s", "perc", "team" (akinek szól), "team_name",
    "nezopont", "kapus_team", "mez", "kaputra", "vedett", "vart_vedes",
    "irany" ("forro" / "hideg"), "text"}]}."""
    config = config or TacticsConfig()
    alerts: list = []
    if not match.frames:
        return {"alerts": alerts}
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    t0 = match.frames[0].t
    nevek = {"home": match.meta.home_team, "away": match.meta.away_team}
    itelet = (proba or {}).get("itelet")
    szolt: set = set()
    for perc in LIVE_AJANLO_PERCEK:
        hatar = t0 + int(round(perc * 60 * fps))
        eddig = [fr for fr in match.frames if fr.t <= hatar]
        if len(eddig) < 2 or eddig[-1].t < hatar - fps:
            continue      # a meccs még nem ért el idáig
        resz = Match(meta=match.meta, frames=eddig)
        for side, team in (("home", Team.HOME), ("away", Team.AWAY)):
            masik = "away" if side == "home" else "home"
            szorzok = (kapus_szorzok or {}).get(side) or {}
            for mez, minta in sorted(_kapus_minta_kapusonkent(
                    resz, team, config).items()):
                faced = sum(int(v[0]) for v in minta.values())
                if faced < KF_MIN_LOVES:
                    continue
                kapott = sum(int(v[0]) - int(v[1]) for v in minta.values())
                vart = _kapus_varhato(minta, szorzok.get(int(mez))
                                      or szorzok.get(str(mez)))
                elteres = vart - kapott
                if abs(elteres) < KF_ELO_GOL:
                    continue
                irany = "forro" if elteres > 0 else "hideg"
                if (side, mez, irany) in szolt:
                    continue
                szolt.add((side, mez, irany))
                vedett = faced - kapott
                vv = f"{faced - vart:.1f}".replace(".", ",")
                alap = (f"{mezszam_nevelovel(int(mez))} ma {vedett}/{faced} "
                        f"védés (a szokásos szintje szerint {vv})")
                cim = "Forró" if irany == "forro" else "Hideg"
                if itelet == "kitart":
                    sajat = ("a napi formája kitart: maradjon a kapuban"
                             if irany == "forro" else
                             "a napi formája kitart: érdemes kapust cserélni")
                    ellen = ("a napi formája kitart: jobb helyzetekből "
                             "lőjetek, ne távolról" if irany == "forro" else
                             "a napi formája kitart: lőjetek többet")
                elif itelet == "visszaall":
                    sajat = ("a napi formája nem tart ki: ne építsetek rá, a "
                             "védekezés maradjon szoros" if irany == "forro"
                             else "a napi formája nem tart ki: egy gyenge "
                             "szakasz miatt nem kell kapust cserélni")
                    ellen = ("a napi formája nem tart ki: lőjetek bátran "
                             "tovább" if irany == "forro" else
                             "a napi formája nem tart ki: ne a kapusra "
                             "építsetek")
                else:
                    sajat = ellen = ("a könyvtár még nem dönti el, kitart-e "
                                     "a kapus napi formája")
                kozos = {"t": hatar, "t_s": round(hatar / fps, 1),
                         "perc": perc, "kapus_team": side, "mez": int(mez),
                         "kaputra": faced, "vedett": vedett,
                         "vart_vedes": round(faced - vart, 1),
                         "irany": irany}
                alerts.append({**kozos, "team": side,
                               "team_name": nevek[side], "nezopont": "sajat",
                               "text": (f"{cim} kapus ({perc}. perc): "
                                        f"{nevek[side]} — {alap} — {sajat}")})
                alerts.append({**kozos, "team": masik,
                               "team_name": nevek[masik],
                               "nezopont": "ellenfel",
                               "text": (f"{cim} kapus az ellenfélnél "
                                        f"({perc}. perc): {nevek[side]} — "
                                        f"{alap} — {ellen}")})
    alerts.sort(key=lambda a: (a["t"], a["kapus_team"], a["mez"],
                               a["nezopont"]))
    return {"alerts": alerts}



# ---- Időkérés a sorozat ellen: megtöri-e -----------------------------------
# Az edző egyik leggyakoribb meccs közbeni döntése, hogy a sorozat ellen
# időt kér-e. A próba a könyvtár meccsein: valahányszor egy csapat
# IDO_SOROZAT válasz nélküli gólhoz ér, a sorozatot kapó csapat vagy kér
# időt (IDO_ABLAK_S-en belül, a következő gól előtt), vagy nem — és ki
# szerzi a következő gólt. Ha időkérés után legalább IDO_ITELET_PP
# százalékponttal gyakrabban a sorozatot kapó csapat szerez, az időkérés
# megtöri a sorozatot. Élőben a sorozat IDO_SOROZAT-adik góljánál szól,
# mindkét kispadnak, a próba ítéletével.
IDO_SOROZAT = 3          # válasz nélküli gól = sorozat (mint momentum.RUN_MIN)
IDO_ABLAK_S = 120.0      # a sorozat-gól után eddig kért idő szól a sorozat ellen
IDO_MIN_ESET = 5         # csoportonként (kért / nem kért) legalább ennyi helyzet
IDO_ITELET_PP = 10.0     # a "megtöri" ítélethez kell ennyi százalékpont


def run_timeout_sample(match: Match,
                       config: TacticsConfig | None = None) -> dict:
    """Az időkérés-próba NYERS, JSON-barát meccs-mintája: a gólok
    időrendben ({"golok": [[perc, "home" / "away"], …]}, event_detection.
    detect_shots) és az időkérések ({"idokeresek": [[perc, a valószínű
    kérő "home" / "away" / None], …]}, stoppages.detect_stoppages
    "időkérés" fajtája) — a perc a felvétel kezdetétől."""
    from .event_detection import EventType, detect_shots
    from .stoppages import detect_stoppages
    config = config or TacticsConfig()
    if not match.frames:
        return {"golok": [], "idokeresek": []}
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    t0 = match.frames[0].t
    golok = [[round((e.t - t0) / fps / 60.0, 2), e.team.value]
             for e in sorted(detect_shots(match, config), key=lambda e: e.t)
             if e.type == EventType.GOAL and e.team.value in ("home", "away")]
    ido = [[round((st["start_frame"] - t0) / fps / 60.0, 2),
            st.get("likely_team")]
           for st in detect_stoppages(match, config)
           if st.get("kind") == "időkérés"]
    return {"golok": golok, "idokeresek": ido}


def _sorozat_helyzetek(minta: dict) -> list:
    """Egy meccs-mintából (run_timeout_sample) a sorozat-helyzetek: amikor
    egy csapat IDO_SOROZAT válasz nélküli gólhoz ér — [(perc, a sorozatot
    futó oldal, a következő gól oldala vagy None, kért-e időt a sorozatot
    kapó csapat a sorozat-gól után IDO_ABLAK_S-en belül, a következő gól
    előtt)]."""
    golok = sorted(((float(p), str(s)) for p, s in
                    (minta or {}).get("golok") or []), key=lambda g: g[0])
    ido = [(float(p), s) for p, s in (minta or {}).get("idokeresek") or []]
    ki: list = []
    cur, hossz = None, 0
    for i, (p, s) in enumerate(golok):
        if s == cur:
            hossz += 1
        else:
            cur, hossz = s, 1
        if hossz != IDO_SOROZAT:
            continue
        kapo = "away" if s == "home" else "home"
        kov = golok[i + 1] if i + 1 < len(golok) else None
        veg = kov[0] if kov else float("inf")
        kert = any(sk == kapo and p <= pk < veg
                   and (pk - p) * 60.0 <= IDO_ABLAK_S for pk, sk in ido)
        ki.append((p, s, kov[1] if kov else None, kert))
    return ki


def timeout_run_backtest(meccsek: list,
                         csapat: str | None = None) -> dict | None:
    """Az időkérés próbája a sorozat ellen: `meccsek` = [{"home", "away",
    "minta" (run_timeout_sample)}]. Minden sorozat-helyzetben
    (_sorozat_helyzetek; ami a meccs végéig gól nélkül maradt, kimarad):
    kért-e időt a sorozatot kapó csapat, és ő szerezte-e a következő
    gólt (megtört a sorozat). A `csapat` megadásával csak az ő
    sorozat-kapó helyzetei (a saját időkérés-döntéseik). Mit jelent
    edzőileg: a "most kérjünk időt" döntés a könyvtár meccsein igazolt-e,
    vagy a sorozat az időkérés után is ugyanúgy folytatódik. Visszatérés:
    {"kert", "kert_tores", "nem_kert", "nem_kert_tores", "kert_pct",
    "nem_kert_pct", "kulonbseg_pp", "itelet" ("megtori" / "nem_tori"),
    "verdict"} — None, ha valamelyik csoportban IDO_MIN_ESET-nél kevesebb
    a helyzet."""
    kert: list = []
    nem: list = []
    for m in meccsek or []:
        nevek = {"home": m.get("home"), "away": m.get("away")}
        for _p, s, kov, k in _sorozat_helyzetek(m.get("minta")):
            if kov is None:
                continue
            kapo = "away" if s == "home" else "home"
            if csapat is not None and nevek[kapo] != csapat:
                continue
            (kert if k else nem).append(kov == kapo)
    if len(kert) < IDO_MIN_ESET or len(nem) < IDO_MIN_ESET:
        return None
    kp = sum(kert) / len(kert) * 100.0
    np_ = sum(nem) / len(nem) * 100.0
    d = kp - np_
    megtori = d >= IDO_ITELET_PP
    return {"kert": len(kert), "kert_tores": sum(kert),
            "nem_kert": len(nem), "nem_kert_tores": sum(nem),
            "kert_pct": round(kp, 1), "nem_kert_pct": round(np_, 1),
            "kulonbseg_pp": round(d, 1),
            "itelet": "megtori" if megtori else "nem_tori",
            "verdict": (f"a sorozat elleni időkérés után a következő gólt "
                        f"{len(kert)} esetből {sum(kert)} alkalommal a "
                        f"sorozatot kapó csapat szerezte ({kp:.0f}%), "
                        f"időkérés nélkül {len(nem)} esetből {sum(nem)} "
                        f"alkalommal ({np_:.0f}%) — "
                        + ("az időkérés megtöri a sorozatot: kérjetek időt"
                           if megtori else
                           "az időkérés önmagában nem töri meg a "
                           "sorozatot: ha kértek, váltással (védekezés, "
                           "csere) együtt kérjétek"))}


def live_timeout_alerts(match: Match, proba: dict | None = None,
                        config: TacticsConfig | None = None) -> dict:
    """Élő időkérés-tanács a sorozat ellen: amikor egy csapat IDO_SOROZAT
    válasz nélküli gólhoz ér (a gól pillanatában, CSAK az addigi gólokból
    — okszerű), mindkét kispadnak szól: a sorozatot kapónak ("kapo":
    kérjetek időt / váltással együtt kérjétek) és a sorozatot futónak
    ("futo": készüljetek az időkérés utáni figurájukra / tartsátok a
    tempót). A tanács a `proba` (timeout_run_backtest) ítéletéből; ítélet
    nélkül a jelzés ezt mondja ki. Visszatérés: {"alerts": [{"t", "t_s",
    "perc", "team" (akinek szól), "team_name", "nezopont",
    "sorozat_team", "hossz", "allas" ([hazai, vendég]), "text"}]}."""
    from .event_detection import EventType, detect_shots
    config = config or TacticsConfig()
    alerts: list = []
    if not match.frames:
        return {"alerts": alerts}
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    t0 = match.frames[0].t
    nevek = {"home": match.meta.home_team, "away": match.meta.away_team}
    p = proba or {}
    itelet = p.get("itelet")
    if itelet == "megtori":
        kapo_txt = (f"a könyvtárban a sorozat elleni időkérés után "
                    f"{float(p['kert_pct']):.0f}%-ban a sorozatot kapó csapat "
                    f"szerezte a következő gólt (időkérés nélkül "
                    f"{float(p['nem_kert_pct']):.0f}%): kérjetek időt")
        futo_txt = ("a könyvtár szerint az időkérés megtöri a sorozatokat: "
                    "ha időt kérnek, készüljetek az utána jövő figurájukra")
    elif itelet == "nem_tori":
        kapo_txt = (f"a könyvtárban az időkérés önmagában nem törte meg a "
                    f"sorozatokat ({float(p['kert_pct']):.0f}%, időkérés "
                    f"nélkül {float(p['nem_kert_pct']):.0f}%): ha kértek, "
                    f"váltással (védekezés, csere) együtt kérjétek")
        futo_txt = ("a könyvtár szerint az időkérés önmagában nem töri meg "
                    "a sorozatot: tartsátok a tempót")
    else:
        kapo_txt = futo_txt = ("a könyvtár még nem dönti el, megtöri-e az "
                               "időkérés a sorozatot")
    allas = {"home": 0, "away": 0}
    cur, hossz = None, 0
    for e in sorted(detect_shots(match, config), key=lambda e: e.t):
        if e.type != EventType.GOAL or e.team.value not in allas:
            continue
        s = e.team.value
        allas[s] += 1
        if s == cur:
            hossz += 1
        else:
            cur, hossz = s, 1
        if hossz != IDO_SOROZAT:
            continue
        kapo = "away" if s == "home" else "home"
        perc = int((e.t - t0) / fps // 60) + 1
        at = f"{allas['home']}–{allas['away']}"
        kozos = {"t": e.t, "t_s": round(e.t / fps, 1), "perc": perc,
                 "sorozat_team": s, "hossz": hossz,
                 "allas": [allas["home"], allas["away"]]}
        alerts.append({**kozos, "team": kapo, "team_name": nevek[kapo],
                       "nezopont": "kapo",
                       "text": (f"Sorozat ellenetek ({perc}. perc, {at}): "
                                f"{nevek[s]} {hossz}-0-s sorozata — "
                                f"{kapo_txt}")})
        alerts.append({**kozos, "team": s, "team_name": nevek[s],
                       "nezopont": "futo",
                       "text": (f"Sorozatban vagytok ({perc}. perc, {at}): "
                                f"{hossz}-0 nektek — {futo_txt}")})
    return {"alerts": alerts}

# ---- Várható védekezési rendszer -------------------------------------------
# Az ellenfél védekezési rendszere a következő meccsen a KORÁBBI meccsei
# védekező kockáiból (detect_formation — a _tanulas_minta "formak"
# számlálója): az eloszlás és a fő rendszer. A meccs fő rendszere csak
# VR_MIN_KOCKA védekező kockától számít (a próbában és élőben is); a
# próbához legalább VR_PROBA_MIN előre jelzett meccs kell. Élőben a
# 15., 30. és 45. percben szól, ha az addigi fő rendszerük eltér a
# várttól (csapatonként egy rendszerre egyszer).
VR_MIN_KOCKA = 50
VR_PROBA_MIN = 5


def _rendszer_nevelovel(r: str) -> str:
    """A rendszer névelővel: "az 5-1", "a 6-0", "a 3-2-1"."""
    return f"{'az' if str(r).startswith('5') else 'a'} {r}"


def _fo_rendszer(formak: dict) -> str | None:
    """A legtöbb kockát kapott rendszer (holtversenyben név szerint) —
    None VR_MIN_KOCKA-nál kevesebb kockánál."""
    ossz = sum(int(v) for v in (formak or {}).values())
    if ossz < VR_MIN_KOCKA:
        return None
    return min(formak, key=lambda k: (-int(formak[k]), k))


def defense_system_forecast(form_mintak: list) -> dict | None:
    """A várható védekezési rendszer a csapat korábbi meccseiből:
    `form_mintak` meccsenként a player_model_sample "formak" mezője
    ({rendszer: védekező kocka}). Mit jelent edzőileg: mire készüljön a
    támadásunk — melyik fal ellen tervezzük a figurákat. Visszatérés:
    {"fo" (a fő rendszer), "eloszlas" ({rendszer: arány}, csökkenőben),
    "meccsek", "kockak"} — None, ha két meccsnél kevesebb van, vagy
    VR_MIN_KOCKA-nál kevesebb a kocka."""
    if len(form_mintak) < 2:
        return None
    ossz: dict = {}
    for m in form_mintak:
        for k, v in (m or {}).items():
            ossz[str(k)] = ossz.get(str(k), 0) + int(v)
    fo = _fo_rendszer(ossz)
    if fo is None:
        return None
    n = sum(ossz.values())
    return {"fo": fo, "eloszlas": {k: round(ossz[k] / n, 3) for k in sorted(
                ossz, key=lambda k: (-ossz[k], k))},
            "meccsek": len(form_mintak), "kockak": n}


def defense_system_text(f: dict | None) -> str | None:
    """A várható védekezés egy mondatban: "6-0 (a korábbi védekezésük
    70%-a), mellette 5-1 (25%)" — a második rendszer 10%-tól. None
    előrejelzés nélkül."""
    if not f:
        return None
    sorok = list(f["eloszlas"].items())
    ki = f"{f['fo']} (a korábbi védekezésük {sorok[0][1] * 100:.0f}%-a)"
    if len(sorok) > 1 and sorok[1][1] >= 0.1:
        ki += f", mellette {sorok[1][0]} ({sorok[1][1] * 100:.0f}%)"
    return ki


def defense_system_backtest(meccsek: list,
                            csapat: str | None = None) -> dict | None:
    """A várható védekezés próbája: `meccsek` időrendben [{"match_id",
    "home", "away", "minta": {"home" / "away": player_model_sample}}].
    Minden meccsen és oldalon, ahol a csapatnak legalább két korábbi
    meccse van, a fő rendszer a korábbiakból (defense_system_forecast)
    és a meccs valódi fő rendszere (VR_MIN_KOCKA kockától); a
    viszonyítás a liga addigi leggyakoribb fő rendszere. A `csapat`
    megadásával csak a csapat meccsei. Edzőileg: mennyire lehet a
    "6-0-ra készüljetek" mondatra építeni. Visszatérés: {"meccsek",
    "talalat", "liga_talalat", "verdict"} — None VR_PROBA_MIN-nél
    kevesebb előre jelzett meccsnél."""
    tort: dict = {}
    liga: dict = {}
    n = tal = liga_tal = 0
    for m in meccsek:
        mi = m.get("minta") or {}
        uj = []
        for side in ("home", "away"):
            nev = m.get(side)
            formak = (mi.get(side) or {}).get("formak") or {}
            valodi = _fo_rendszer(formak)
            f = defense_system_forecast(tort.get(nev, []))
            if (f is not None and valodi is not None
                    and (csapat is None or nev == csapat)):
                n += 1
                tal += int(f["fo"] == valodi)
                if liga:
                    liga_tal += int(min(liga, key=lambda k: (-liga[k], k))
                                    == valodi)
            uj.append((nev, formak, valodi))
        for nev, formak, valodi in uj:
            tort.setdefault(nev, []).append(formak)
            if valodi is not None:
                liga[valodi] = liga.get(valodi, 0) + 1
    if n < VR_PROBA_MIN:
        return None
    return {"meccsek": n, "talalat": tal, "liga_talalat": liga_tal,
            "verdict": (f"a várható fő védekezési rendszer {n} meccsből "
                        f"{tal} alkalommal jött be (a liga leggyakoribb "
                        f"rendszeréé: {liga_tal})")}


def live_defense_system_alerts(match: Match, varhato: dict,
                               config: TacticsConfig | None = None) -> dict:
    """Élő eltérő védekezés: a LIVE_AJANLO_PERCEK perceiben csapatonként
    az addigi védekező kockák fő rendszere (_tanulas_minta CSAK az
    addigi kockákon — okszerű) a várttól (`varhato`: {"home" / "away":
    defense_system_forecast}) eltér-e — csapatonként egy rendszerre
    egyszer. Edzőileg: a megszokottól eltérő fallal jöttek — a
    figura-tervet a mostani falhoz kell igazítani. Visszatérés:
    {"alerts": [{"t" (kocka), "t_s", "perc", "team" (a VÉDŐ oldal),
    "team_name", "most", "vart", "text"}]}."""
    config = config or TacticsConfig()
    alerts: list = []
    if not match.frames:
        return {"alerts": alerts}
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    t0 = match.frames[0].t
    nevek = {"home": match.meta.home_team, "away": match.meta.away_team}
    szolt: dict = {}
    for perc in LIVE_AJANLO_PERCEK:
        hatar = t0 + int(round(perc * 60 * fps))
        eddig = [fr for fr in match.frames if fr.t <= hatar]
        if len(eddig) < 2 or eddig[-1].t < hatar - fps:
            continue      # a meccs még nem ért el idáig
        resz = Match(meta=match.meta, frames=eddig)
        for side, team in (("home", Team.HOME), ("away", Team.AWAY)):
            v = (varhato or {}).get(side)
            if not v:
                continue
            most = _fo_rendszer(_tanulas_minta(resz, team, config)["formak"])
            if most is None or most == v["fo"] or szolt.get(side) == most:
                continue
            szolt[side] = most
            alerts.append({
                "t": hatar, "t_s": round(hatar / fps, 1), "perc": perc,
                "team": side, "team_name": nevek[side], "most": most,
                "vart": v["fo"],
                "text": (f"Eltérő védekezés ({perc}. perc): {nevek[side]} "
                         f"{most} fallal véd a várt {v['fo']} helyett — a "
                         f"figura-tervet {_rendszer_nevelovel(most)} "
                         "falhoz kell igazítani")})
    alerts.sort(key=lambda a: (a["t"], a["team"]))
    return {"alerts": alerts}


# ---- A játékos-modell fejlődése: két időszak tanult szorzói -----------------
# Két időszak (pl. a szezon két fele) tanult lövő- és kapus-szorzói
# összevetve: egy sáv akkor hír, ha MINDKÉT időszakban tanult (a
# küszöbök — LOVO_MIN_LOVES, KAPUS_MIN_LOVES — mindkettőben
# teljesülnek), és a szorzó legalább FEJLODES_ELTERES-sel változott.
# Legfeljebb FEJLODES_MAX sor, a változás nagysága szerint.
FEJLODES_ELTERES = 0.1
FEJLODES_MAX = 5


def player_model_development(regi_tamadas, uj_tamadas,
                             regi_kapus: dict | None = None,
                             uj_kapus: dict | None = None) -> dict:
    """A játékos-modell fejlődése két időszak között: `regi_tamadas` /
    `uj_tamadas` (AttackModel — a két időszak tanult lövői), `regi_kapus`
    / `uj_kapus` (a csapat kapusának sávonkénti szorzója a két
    időszakban). A lövőnél a nagyobb szorzó a jobb (többet lő be a
    helyzeteinél), a kapusnál a kisebb (kevesebb gólt kap az átlagnál).

    Edzőileg: a szezon-riport kérdése — melyik lövőnk javult melyik
    távolságból, és a kapus melyik sávja romlott; a heti munka iránya.

    Visszaad: {"lovok": [{"mez", "sav", "sav_nev", "regi", "uj",
    "valtozas", "irany" ("javul" / "romlik")}, …], "kapus": [{"sav",
    "sav_nev", "regi", "uj", "valtozas", "irany"}, …], "lovo_sorok",
    "kapus_sorok" (mondatok)} — a változás nagysága szerint csökkenőben
    (holtversenyben mezszám, sáv), legfeljebb FEJLODES_MAX soronként;
    üres listák, ha nincs érdemi változás."""
    regi = regi_tamadas.lovok if regi_tamadas is not None else {}
    uj = uj_tamadas.lovok if uj_tamadas is not None else {}
    lovok = []
    for mez in sorted(set(regi) & set(uj)):
        for sav in ("close", "mid", "far"):
            if sav not in regi[mez] or sav not in uj[mez]:
                continue
            a, b = float(regi[mez][sav]), float(uj[mez][sav])
            if abs(b - a) < FEJLODES_ELTERES:
                continue
            lovok.append({"mez": int(mez), "sav": sav,
                          "sav_nev": KAPUS_SAV_NEV[sav], "regi": a, "uj": b,
                          "valtozas": round(b - a, 3),
                          "irany": "javul" if b > a else "romlik"})
    lovok.sort(key=lambda r: (-abs(r["valtozas"]), r["mez"], r["sav"]))
    lovok = lovok[:FEJLODES_MAX]
    kapus = []
    rk, uk = regi_kapus or {}, uj_kapus or {}
    for sav in ("close", "mid", "far"):
        if sav not in rk or sav not in uk:
            continue
        a, b = float(rk[sav]), float(uk[sav])
        if abs(b - a) < FEJLODES_ELTERES:
            continue
        kapus.append({"sav": sav, "sav_nev": KAPUS_SAV_NEV[sav], "regi": a,
                      "uj": b, "valtozas": round(b - a, 3),
                      "irany": "javul" if b < a else "romlik"})
    kapus.sort(key=lambda r: (-abs(r["valtozas"]), r["sav"]))

    def sz(v):
        return f"{v:.1f}".replace(".", ",")

    lovo_sorok = [f"{mezszam_nevelovel(r['mez'])} {r['sav_nev']} "
                  f"{sz(r['regi'])}× → {sz(r['uj'])}× ({r['irany']})"
                  for r in lovok]
    kapus_sorok = [f"a kapus {r['sav_nev']} {sz(r['regi'])}× → "
                   f"{sz(r['uj'])}× annyi gólt kap, mint az átlag "
                   f"({r['irany']})" for r in kapus]
    return {"lovok": lovok, "kapus": kapus, "lovo_sorok": lovo_sorok,
            "kapus_sorok": kapus_sorok}


# ---- Élő lövés-elosztás: az eddigi lövések × a tanult lövők ----------------
# A LIVE_AJANLO_PERCEK perceiben a TÁMADÓ kispadnak: az ADDIG leadott
# mezszámos lövések részesedése × a csapat tanult lövőinek értéke az
# ellenfél kapusa ellen (a szezon korábbi meccseiből; ahol nincs, az addig
# látott kockákból) — shot_allocation_from. Csak döntésnél szól, és egy
# oldal ugyanazzal a párral (többet / kevesebbet) nem ismétlődik.


def live_shot_allocation_alerts(match: Match,
                                config: TacticsConfig | None = None, *,
                                tamadas: dict | None = None,
                                kapus: dict | None = None) -> dict:
    """Élő lövés-elosztás: a LIVE_AJANLO_PERCEK perceiben csapatonként (a
    TÁMADÓ oldal) az addig leadott lövések részesedése a tanult lövők
    értékéhez mérve — ki lőhetne többet és ki kevesebbet
    (shot_allocation_from). `tamadas` ({"home" / "away": AttackModel — a
    csapat lövői}) és `kapus` ({…: a SZEMKÖZTI kapus sávjai}) a szezon
    KORÁBBI meccseiből; ahol nincs, az addig látott kockákból tanul
    (okszerű). A részesedés mindig az addigi kockákból.

    Edzőileg: az időkérésen — "eddig a 10-es lőtt háromnegyedet, pedig a
    7-es közelről többet ér ellenük": a játékrendszer a ritkán lövő
    értékes lövőt hozza helyzetbe.

    Visszaad: {"alerts": [{"t" (kocka), "t_s", "perc", "team",
    "team_name", "tobbet_mez", "tobbet_sav", "kevesebbet_mez",
    "kevesebbet_sav", "lovesek", "verdict", "text"}, …]} t és csapat
    szerint; üres, ha nincs döntés (kevés lövés, nincs tanult lövő, vagy
    kiegyensúlyozott)."""
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    alerts: list = []
    if not match.frames:
        return {"alerts": alerts}
    t0 = match.frames[0].t
    utolso: dict = {}
    nevek = {"home": match.meta.home_team, "away": match.meta.away_team}
    for perc in LIVE_AJANLO_PERCEK:
        hatar = t0 + int(round(perc * 60 * fps))
        eddig = [f for f in match.frames if f.t <= hatar]
        if len(eddig) < 2 or eddig[-1].t < hatar - fps:
            continue      # a meccs még nem ért el idáig
        resz = Match(meta=match.meta, frames=eddig)
        for side, team, masik in (("home", Team.HOME, Team.AWAY),
                                  ("away", Team.AWAY, Team.HOME)):
            tam = (tamadas or {}).get(side)
            if tam is None:
                tam = AttackModel.learn(resz, team, config)
            kap = (kapus or {}).get(side)
            if kap is None:
                kap = _kapus_tanul(resz, masik, config)
            p = shot_allocation_from(tam, kap, _lovo_minta(resz, team, config))
            if not p or not p.get("dontes"):
                continue
            t_, k_ = p["tobbet"], p["kevesebbet"]
            par = (t_["mez"], t_["sav"], k_["mez"], k_["sav"])
            if utolso.get(side) == par:
                continue
            utolso[side] = par
            alerts.append({
                "t": hatar, "t_s": round(hatar / fps, 1), "perc": perc,
                "team": side, "team_name": nevek[side],
                "tobbet_mez": t_["mez"], "tobbet_sav": t_["sav"],
                "kevesebbet_mez": k_["mez"], "kevesebbet_sav": k_["sav"],
                "lovesek": p["lovesek"], "verdict": p["verdict"],
                "text": (f"Lövés-elosztás ({perc}. perc): {nevek[side]} — "
                         f"{p['verdict']}")})
    alerts.sort(key=lambda a: (a["t"], a["team"]))
    return {"alerts": alerts}

# ---- Élő kit kinek: a lövőik × az addig látott falunk ----------------------
# A LIVE_AJANLO_PERCEK perceiben (mint a figura-ajánló), ha az addig
# látott kockákból a falunk már tanulható (LIVE_AJANLO_MIN_KOCKA): az
# ellenfél tanult lövői (a szezon korábbi meccseiből — ahol nincs, az
# addig látott kockákból) × a falunk ADDIG látott védői → ki álljon a
# veszélyes távoli lövővel szemben (shooter_defender_pairs), és kire ne
# lépjünk ki (allowed_shooters_from). Ugyanaz a mondat nem ismétlődik:
# egy oldal egy fajta jelzése csak akkor szól újra, ha a tartalma
# változott (a fal átállt, más védő került a sávba). Okszerű: csak a
# percig látott kockák.
LIVE_KITKINEK_FAJTA = {"kit_kinek": "Kit kinek", "engedett": "Engedett lövő"}


def lovo_minta_many(meccsek: list, config: TacticsConfig | None = None) -> dict:
    """TÖBB meccs nyers lövő-mintája összeadva (`meccsek` = [(match, a
    csapat oldala), …]) — az AttackModel.learn_many párja a lövésszámhoz
    és a gólhoz (allowed_shooters_from). Üres listára üres."""
    config = config or TacticsConfig()
    return _lovo_mintak_osszege([_lovo_minta(m, t, config) for m, t in meccsek])


def lovo_sav_minta_many(meccsek: list,
                        config: TacticsConfig | None = None) -> dict:
    """TÖBB meccs lövő sáv-mintája összeadva ({mezszám: [lövés sávonként]},
    _lovo_sav_minta alakban) — a shooter_defender_pairs `savok` bemenete
    a szezonból. Üres listára üres."""
    config = config or TacticsConfig()
    ossz: dict = {}
    for m, t in meccsek:
        for mez, db in _lovo_sav_minta(m, t, config).items():
            r = ossz.setdefault(int(mez), [0] * KITKINEK_SAVOK)
            for i, x in enumerate(db):
                r[i] += int(x)
    return ossz


def live_matchup_alerts(match: Match, config: TacticsConfig | None = None, *,
                        tamadas: dict | None = None,
                        savok: dict | None = None,
                        mintak: dict | None = None) -> dict:
    """Élő kit kinek: a LIVE_AJANLO_PERCEK perceiben csapatonként (a VÉDŐ
    oldal, akinek a faláról szó van) a falunk addig látott védői
    (DefenseModel a kezdettől a percig) × az ellenfél tanult lövői:
    - "kit_kinek": a veszélyes távoli lövőjük és a sávjában álló védőnk,
      csere-javaslattal a kilépőre (shooter_defender_pairs első párja);
    - "engedett": a gyenge távoli lövőjük, akire nem kell kilépni
      (allowed_shooters_from első sora).
    `tamadas` ({"home" / "away": AttackModel}), `savok` ({…: a lövőik
    sáv-mintája}) és `mintak` ({…: a nyers lövő-mintájuk}) oldalanként az
    ADOTT fal ELLEN támadó csapatról, a szezon korábbi meccseiből; ahol
    nincs, az addig látott kockákból tanul (okszerű).

    Edzőileg: a félidei / időkérési emberfogás-döntés — ki álljon a 9-es
    elé, és kire ne pazaroljuk a kilépést — az addig látott falunkból,
    nem a meccs végéből.

    Visszaad: {"alerts": [{"t" (kocka), "t_s", "perc", "team",
    "team_name", "fajta" ("kit_kinek" / "engedett"), "lovo_mez",
    "vedo_mez" és "javasolt_mez" (csak a kit kinek-nél, különben None),
    "verdict", "text"}, …]} t, csapat és fajta szerint; egy oldal egy
    fajtája csak változásnál szól újra; üres, ha a fal még nem tanulható
    vagy nincs tanult lövőjük."""
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    alerts: list = []
    if not match.frames:
        return {"alerts": alerts}
    t0 = match.frames[0].t
    utolso: dict = {}
    for perc in LIVE_AJANLO_PERCEK:
        hatar = t0 + int(round(perc * 60 * fps))
        eddig = [f for f in match.frames if f.t <= hatar]
        if len(eddig) < 2 or eddig[-1].t < hatar - fps:
            continue      # a meccs még nem ért el idáig
        resz = Match(meta=match.meta, frames=eddig)
        for side, team, masik in (("home", Team.HOME, Team.AWAY),
                                  ("away", Team.AWAY, Team.HOME)):
            minta = _tanulas_minta(resz, team, config)
            if minta["kockak"] < LIVE_AJANLO_MIN_KOCKA:
                continue
            vedok = DefenseModel._modell_mintabol(minta).vedok
            tam = (tamadas or {}).get(side)
            if tam is None:
                tam = AttackModel.learn(resz, masik, config)
            sav = (savok or {}).get(side)
            if sav is None:
                sav = _lovo_sav_minta(resz, masik, config)
            nyers = (mintak or {}).get(side)
            if nyers is None:
                nyers = _lovo_minta(resz, masik, config)
            nev = (match.meta.home_team if side == "home"
                   else match.meta.away_team)
            parok = shooter_defender_pairs(tam, sav, vedok) if vedok else []
            engedett = allowed_shooters_from(tam, nyers)
            for fajta, sor in (("kit_kinek", parok[0] if parok else None),
                               ("engedett", engedett[0] if engedett else None)):
                if sor is None or utolso.get((side, fajta)) == sor["verdict"]:
                    continue
                utolso[(side, fajta)] = sor["verdict"]
                alerts.append({
                    "t": hatar, "t_s": round(hatar / fps, 1), "perc": perc,
                    "team": side, "team_name": nev, "fajta": fajta,
                    "lovo_mez": sor.get("lovo_mez", sor.get("mez")),
                    "vedo_mez": sor.get("vedo_mez"),
                    "javasolt_mez": sor.get("javasolt_mez"),
                    "verdict": sor["verdict"],
                    "text": (f"{LIVE_KITKINEK_FAJTA[fajta]} ({perc}. perc): "
                             f"{nev} eddig látott fala — {sor['verdict']}")})
    alerts.sort(key=lambda a: (a["t"], a["team"], a["fajta"]))
    return {"alerts": alerts}


# ---- Kapus-választás: melyik kapusunk az ő lövőik ellen --------------------
# Kapusonként (mezszám) a kaputra érkező lövések sávonkénti mérlege (a
# goalkeeper_timeline szolgálat-szakaszai szerint: ki védett a lövés
# pillanatában), ebből a kapus sávonkénti szorzója — mint a csapat-
# kapusé (KAPUS_SULY, KAPUS_MIN_LOVES). Az ő lövőik ellen (a nyers lövő-
# minta: ki honnan hányat lő, és a tanult szorzója) kapusonként a
# várható kapott gól LÖVÉSENKÉNT = Σ lövés × xG (a sáv képviselő-helye)
# × lövő-szorzó × a kapus sáv-szorzója / Σ lövés — a kisebb a jobb.
# Legalább két tanult kapus és egy tanult lövő-sáv kell; döntés csak
# KAPUS_VALASZTAS_ELTERES várható gól lövésenkénti különbség felett
# (különben "nincs érdemi különbség").
KAPUS_VALASZTAS_ELTERES = 0.02


def _kapus_minta_kapusonkent(match: Match, defending_team: Team,
                             config: TacticsConfig) -> dict:
    """Kapusonként a kaputra érkező lövések sáv-mérlege: {kapus mezszám:
    {sáv: [kaputra érkezett, védett]}} — a goalkeeper_timeline
    szolgálat-szakaszai szerint (ki védett a lövés pillanatában); a
    lövés és a sáv mint a csapat-kapusnál (gól vagy védés = kaputra
    érkezett, a sáv a lövőhelyé). Mezszám nélküli kapus kimarad.
    Meccsek közt összeadható."""
    from .goalkeeper import goalkeeper_timeline
    from .xg import match_xg
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    tl = goalkeeper_timeline(match, config).get(defending_team.value) or {}
    stints = tl.get("stints") or []
    if not stints:
        return {}
    mezek: dict = {}
    for f in match.frames:
        for p in f.players:
            if (p.team == defending_team and p.role == "kapus"
                    and p.jersey_number is not None
                    and p.track_id not in mezek):
                mezek[p.track_id] = int(p.jersey_number)

    def kapus_ekkor(t_s: float):
        utolso = None
        for st in stints:
            if st["from_s"] <= t_s <= st["to_s"]:
                return st["track_id"]
            if st["from_s"] <= t_s:
                utolso = st["track_id"]
        return utolso if utolso is not None else stints[0]["track_id"]

    masik = Team.AWAY if defending_team == Team.HOME else Team.HOME
    goal_x = config.attacks_toward_x(masik)
    out: dict = {}
    for sh in match_xg(match, config)["shots"]:
        if sh["team"] != masik.value or sh["outcome"] not in ("goal", "save"):
            continue
        tid = kapus_ekkor(sh["t"] / fps)
        if tid not in mezek:
            continue
        r = out.setdefault(mezek[tid], {}).setdefault(
            kapus_sav(sh["x"], sh["y"], goal_x), [0, 0])
        r[0] += 1
        if sh["outcome"] == "save":
            r[1] += 1
    return out


def keeper_choice_from(lovo_minta: dict, kapusok: dict) -> dict | None:
    """Kapus-választás a kész mintákból: `lovo_minta` (az ő lövőik nyers
    mintája, _lovo_minta alakban — {mez: {sáv: [lövés, gól, xG]}}),
    `kapusok` ({kapus mez: {sáv: [kaputra érkezett, védett]}},
    _kapus_minta_kapusonkent alakban). Kapusonként a várható kapott gól
    lövésenként az ő lövőik ellen; a kisebb a jobb.

    Visszaad: {"kapus_mez", "ertek", "masik_mez", "masik_ertek",
    "elteres", "dontes" (érdemi-e a különbség), "kapusok" ([{"mez",
    "ertek", "lovesek", "szorzok"}] érték szerint), "verdict"} — None,
    ha nincs legalább két tanult kapus (sávval) vagy tanult lövő-sáv."""
    from .xg import xg_of_position
    szorzok = _lovo_szorzo(lovo_minta or {})
    n_sav: dict = {}
    ertek_sav: dict = {}
    for mez, savok in (lovo_minta or {}).items():
        for sav, v in savok.items():
            tav = UTOLSO_LOVES_TAV_M.get(sav)
            if tav is None or not v or int(v[0]) <= 0:
                continue
            try:
                lsz = float((szorzok.get(int(mez)) or {}).get(sav, 1.0))
            except (TypeError, ValueError):
                lsz = 1.0
            xg = xg_of_position(COURT_LENGTH_M - tav, COURT_WIDTH_M / 2.0,
                                COURT_LENGTH_M)
            n_sav[sav] = n_sav.get(sav, 0) + int(v[0])
            ertek_sav[sav] = ertek_sav.get(sav, 0.0) + int(v[0]) * xg * lsz
    ossz_n = sum(n_sav.values())
    if not ossz_n:
        return None
    sorok = []
    for kmez, minta in (kapusok or {}).items():
        ksz = _kapus_szorzo(minta or {})
        if not ksz:
            continue
        ertek = sum(ertek_sav[s] * float(ksz.get(s, 1.0))
                    for s in ertek_sav) / ossz_n
        sorok.append({"mez": int(kmez), "ertek": round(ertek, 3),
                      "lovesek": int(sum(int(v[0]) for v in minta.values())),
                      "szorzok": ksz})
    if len(sorok) < 2:
        return None
    sorok.sort(key=lambda r: (r["ertek"], r["mez"]))
    b, m = sorok[0], sorok[1]
    elteres = round(m["ertek"] - b["ertek"], 3)
    dontes = elteres >= KAPUS_VALASZTAS_ELTERES

    def szam(v, d=2):
        return f"{v:.{d}f}".replace(".", ",")

    if dontes:
        okok = [f"{KAPUS_SAV_NEV[s]} {szam(v, 1)}× annyit kap, mint az átlag"
                for s, v in sorted(b["szorzok"].items(),
                                   key=lambda kv: (kv[1], kv[0]))
                if v <= 1.0 - LOVO_FELIRAT_ELTERES]
        verdict = (f"{mezszam_nevelovel(b['mez'])} álljon a kapuban az ő "
                   f"lövőik ellen: {szam(b['ertek'])} várható gól "
                   f"lövésenként ({mezszam_nevelovel(m['mez'])}: "
                   f"{szam(m['ertek'])})"
                   + (" — " + ", ".join(okok) if okok else ""))
    else:
        verdict = (f"a két kapusunk között nincs érdemi különbség az ő "
                   f"lövőik ellen ({mezszam_nevelovel(b['mez'])}: "
                   f"{szam(b['ertek'])}, {mezszam_nevelovel(m['mez'])}: "
                   f"{szam(m['ertek'])} várható gól lövésenként)")
    return {"kapus_mez": b["mez"], "ertek": b["ertek"],
            "masik_mez": m["mez"], "masik_ertek": m["ertek"],
            "elteres": elteres, "dontes": dontes, "kapusok": sorok,
            "verdict": verdict}


def keeper_choice(match: Match, config: TacticsConfig | None = None) -> dict:
    """Kapus-választás — csapatonként, a VÉDEKEZŐ oldal szemszögéből:
    melyik kapusunk álljon az ellenfél tanult lövői ellen
    (keeper_choice_from: az ő lövőik nyers mintája × a kapusaink
    kapusonkénti sáv-mérlege ebből a meccsből).

    Edzőileg: a kapus-kérdés nem általában dől el, hanem az ellenfél
    lövői szerint — aki távolról jó, az a távoli lövők ellen álljon.

    Visszaad csapatonként: a keeper_choice_from képe vagy None (egy
    kapus, kevés lövés — a modell nem találgat)."""
    config = config or TacticsConfig()
    out = {}
    for side, team, masik in (("home", Team.HOME, Team.AWAY),
                              ("away", Team.AWAY, Team.HOME)):
        out[side] = keeper_choice_from(
            _lovo_minta(match, masik, config),
            _kapus_minta_kapusonkent(match, team, config))
    return out



# ---- A kapus-választás próbája ---------------------------------------------
# A meccs előtti kapus-választás (keeper_choice_from: melyik kapusunk
# álljon az ő lövőik ellen) a könyvtár időrendjében: minden meccsre a
# KORÁBBI meccsekből (a mi kapusaink sáv-mérlege, az ő lövőik mintája)
# javasolt kapus — és a meccsen a két kapus lövésenként kapott gólja
# (mindkettő legalább KV_PROBA_MIN_LOVES kaputra érkezett lövéssel). A
# viszonyítás a sima szezon-mérleg (a korábbi meccseken összességében
# kevesebbet kapó kapus) — a lövők szerinti súlyozás ennél tud-e többet.
KV_PROBA_MIN_LOVES = 5
KV_PROBA_MIN = 5


def _kapott_arany(minta: dict) -> float | None:
    """Egy kapus sáv-mintájából ({sáv: [kaputra, védett]}) a lövésenként
    kapott gól — None, ha nincs kaputra érkezett lövés."""
    faced = sum(int(v[0]) for v in (minta or {}).values())
    if faced <= 0:
        return None
    return (faced - sum(int(v[1]) for v in minta.values())) / faced


def keeper_choice_backtest(meccsek: list,
                           csapat: str | None = None) -> dict | None:
    """A kapus-választás próbája: `meccsek` = [{"match_id", "home", "away",
    "minta": {"home", "away"} (player_model_sample: "lovo", "kapusok")}]
    időrendben. Minden meccsre és oldalra a KORÁBBI meccsekből a
    keeper_choice_from javaslata (ha érdemi, "dontes"); a meccsen a
    javasolt és a másik kapus lövésenként kapott gólja (mindkettő
    legalább KV_PROBA_MIN_LOVES lövéssel) — igazolt, ha a javasolt
    kevesebbet kapott. Viszonyítás: a sima szezon-mérleg szerinti kapus
    (a korábbi meccseken összességében kevesebbet kapó). A `csapat`
    megadásával csak az ő kapus-választásai. Mit jelent edzőileg: a
    "ki álljon a kapuban" tanács a klub saját meccsein igazolt-e, vagy a
    szokásos kapus is ugyanannyit tud. Visszatérés: {"meccsek",
    "igazolt", "naiv_meccsek", "naiv_igazolt", "atlag_pp", "sorok",
    "itelet" ("igazolt" / "egyenlo" / "nem"), "verdict"} — None, ha
    KV_PROBA_MIN-nél kevesebb a mérhető kapus-választás."""
    sorok: list = []
    for i, m in enumerate(meccsek or []):
        nevek = {"home": m.get("home"), "away": m.get("away")}
        for side in ("home", "away"):
            mi = nevek[side]
            ok = nevek["away" if side == "home" else "home"]
            if not mi or not ok or (csapat is not None and mi != csapat):
                continue
            kapusok = _kapus_mintak_osszege(
                [(x["minta"].get(s) or {}).get("kapusok") or {}
                 for x in meccsek[:i] for s in ("home", "away")
                 if x.get(s) == mi])
            lovok = _lovo_mintak_osszege(
                [(x["minta"].get(s) or {}).get("lovo") or {}
                 for x in meccsek[:i] for s in ("home", "away")
                 if x.get(s) == ok])
            kc = keeper_choice_from(lovok, kapusok)
            if not kc or not kc.get("dontes"):
                continue
            most = {int(k): v for k, v in
                    ((m["minta"].get(side) or {}).get("kapusok") or {}).items()}
            jav, masik = int(kc["kapus_mez"]), int(kc["masik_mez"])
            if any(sum(int(v[0]) for v in (most.get(k) or {}).values())
                   < KV_PROBA_MIN_LOVES for k in (jav, masik)):
                continue
            rj, rm = _kapott_arany(most[jav]), _kapott_arany(most[masik])
            # A sima mérleg: a korábbi meccseken összességében kevesebbet
            # kapó kapus a kettő közül (holtversenyben nincs naiv tipp).
            kj, km = _kapott_arany(kapusok.get(jav)), _kapott_arany(
                kapusok.get(masik))
            naiv = None
            if kj is not None and km is not None and kj != km:
                naiv = jav if kj < km else masik
            sorok.append({
                "match_id": m.get("match_id"), "team": mi,
                "javasolt": jav, "masik": masik,
                "javasolt_pct": round(rj * 100.0, 1),
                "masik_pct": round(rm * 100.0, 1),
                "elteres_pp": round((rm - rj) * 100.0, 1),
                "igazolt": rj < rm, "naiv": naiv,
                "naiv_igazolt": (None if naiv is None else
                                 (rj < rm) if naiv == jav else (rm < rj))})
    n = len(sorok)
    if n < KV_PROBA_MIN:
        return None
    k = sum(1 for r in sorok if r["igazolt"])
    naiv_sorok = [r for r in sorok if r["naiv"] is not None]
    nm = sum(1 for r in naiv_sorok if r["naiv_igazolt"])
    atlag = sum(r["elteres_pp"] for r in sorok) / n
    # A modell többségében igazolt ÉS jobb arányban, mint a sima mérleg.
    jobb_mint_naiv = (not naiv_sorok) or (k / n > nm / len(naiv_sorok))
    if 2 * k > n and atlag > 0 and jobb_mint_naiv:
        itelet = "igazolt"
    elif 2 * k > n and atlag > 0:
        itelet = "egyenlo"
    else:
        itelet = "nem"
    pp = f"{atlag:+.1f}".replace(".", ",")
    verdict = (f"a meccs előtti kapus-választás {n} meccsből {k} alkalommal "
               f"igazolódott (a javasolt kapus lövésenként átlag {pp} "
               f"százalékponttal kevesebb gólt kapott a másiknál; a sima "
               f"szezon-mérleg szerinti választás {len(naiv_sorok)} "
               f"meccsből {nm} alkalommal) — "
               + {"igazolt": "a lövők szerinti kapus-választásra lehet "
                             "építeni",
                  "egyenlo": "a lövők szerinti választás nem tud többet a "
                             "sima mérlegnél: a szokásos kapus is jó",
                  "nem": "a meccs előtti kapus-választás nem igazolódott: "
                         "a kapus-kérdést a napi forma döntse el"}[itelet])
    return {"meccsek": n, "igazolt": k, "naiv_meccsek": len(naiv_sorok),
            "naiv_igazolt": nm, "atlag_pp": round(atlag, 1), "sorok": sorok,
            "itelet": itelet, "verdict": verdict}


# ---- Hetes-dobó választás --------------------------------------------------
# Ki dobja a hetest? A könyvtár hetesei dobónként (rules.seven_meter_
# outcomes: gól / védés / kihagyva, a dobó mezszáma), simított aránnyal
# (HETES_SULY képzelt hetes a csapat arányával — két hetesből nem lesz
# valaki 100%-os dobó). A próba a könyvtár időrendjében: a KORÁBBI
# meccsekből javasolt dobó a meccsen lőtt hetesei a többiekéhez mérve;
# viszonyítás a szokásos dobó (aki eddig a legtöbbet dobta). Élőben a
# hetes pillanatában szól a dobó csapat kispadjának.
HETES_MIN_DOBAS = 3
HETES_SULY = 4
HETES_ALAP = 0.75
HETES_PROBA_MIN = 10
HETES_PROBA_MIN_TOBBI = 5
HETES_ITELET_PP = 10.0


def seven_taker_sample(match: Match, team: Team,
                       config: TacticsConfig | None = None) -> dict:
    """A hetes-dobó választás NYERS, JSON-barát meccs-mintája: a `team`
    hetesei dobónként — {mez (str): [dobás, gól]} (rules.seven_meter_
    outcomes; az ismeretlen kimenetű vagy dobó nélküli hetes kimarad).
    Meccsek közt összeadható."""
    from .rules import seven_meter_outcomes
    config = config or TacticsConfig()
    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)
    ki: dict = {}
    for sm in seven_meter_outcomes(match, config):
        if sm.get("team") != team.value or sm.get("shooter_id") is None \
                or sm.get("outcome") in (None, "ismeretlen"):
            continue
        mez = jersey.get(sm["shooter_id"])
        if mez is None:
            continue
        r = ki.setdefault(str(int(mez)), [0, 0])
        r[0] += 1
        r[1] += int(sm["outcome"] == "gól")
    return ki


def _hetes_osszeg(mintak: list) -> dict:
    """Több meccs hetes-mintájának összege — {mez (int): [dobás, gól]}."""
    ossz: dict = {}
    for m in mintak or []:
        for mez, v in (m or {}).items():
            r = ossz.setdefault(int(mez), [0, 0])
            r[0] += int(v[0])
            r[1] += int(v[1])
    return ossz


def seven_taker_choice(mintak: list) -> dict | None:
    """Hetes-dobó választás a kész mintákból (`mintak`: seven_taker_sample
    meccsenként): a legalább HETES_MIN_DOBAS hetest dobók simított aránya
    (gól + HETES_SULY × a csapat aránya) / (dobás + HETES_SULY) — a
    legjobb a javaslat. Visszaad: {"mez", "dobas", "gol", "arany",
    "masik" (a második vagy None), "dobok" ([{"mez", "dobas", "gol",
    "arany", "simitott"}] simított arány szerint), "verdict"} — None, ha
    senkinek nincs elég hetese."""
    ossz = _hetes_osszeg(mintak)
    n = sum(d for d, _g in ossz.values())
    if not n:
        return None
    alap = (sum(g for _d, g in ossz.values()) + HETES_SULY * HETES_ALAP) \
        / (n + HETES_SULY)
    dobok = [{"mez": mez, "dobas": d, "gol": g,
              "arany": round(100.0 * g / d, 1),
              "simitott": round((g + HETES_SULY * alap) / (d + HETES_SULY), 3)}
             for mez, (d, g) in ossz.items() if d >= HETES_MIN_DOBAS]
    if not dobok:
        return None
    dobok.sort(key=lambda r: (-r["simitott"], -r["dobas"], r["mez"]))
    b = dobok[0]
    m = dobok[1] if len(dobok) > 1 else None
    verdict = (f"a hetest {mezszam_nevelovel(b['mez'])} dobja ({b['gol']}/"
               f"{b['dobas']} a könyvtárban, {b['arany']:.0f}%)"
               + (f"; a második {mezszam_nevelovel(m['mez'])} ({m['gol']}/"
                  f"{m['dobas']})" if m else ""))
    return {"mez": b["mez"], "dobas": b["dobas"], "gol": b["gol"],
            "arany": b["arany"], "masik": m, "dobok": dobok,
            "verdict": verdict}


def seven_taker_backtest(meccsek: list,
                         csapat: str | None = None) -> dict | None:
    """A hetes-dobó választás próbája: `meccsek` = [{"match_id", "home",
    "away", "minta": {"home", "away"} (seven_taker_sample)}] időrendben.
    Minden meccsre és oldalra a KORÁBBI meccsekből javasolt dobó
    (seven_taker_choice) a meccsen lőtt hetesei a többi dobóéhoz mérve;
    viszonyítás a szokásos dobó (aki eddig a legtöbbet dobta). A `csapat`
    megadásával csak az ő hetesei. Mit jelent edzőileg: a hetest a
    könyvtár legjobb dobója dobja-e, vagy a napi forma — ha a javasolt
    dobó HETES_ITELET_PP százalékponttal jobb a többieknél, a választásra
    lehet építeni. Visszatérés: {"meccsek", "javasolt" ([dobás, gól]),
    "tobbi", "szokasos", "javasolt_pct", "tobbi_pct", "szokasos_pct",
    "kulonbseg_pp", "sorok", "itelet" ("igazolt" / "nem"), "verdict"} —
    None, ha a javasolt dobónak HETES_PROBA_MIN-nél, a többieknek
    HETES_PROBA_MIN_TOBBI-nál kevesebb hetese mérhető."""
    jav, tobbi, szok = [0, 0], [0, 0], [0, 0]
    sorok: list = []
    for i, m in enumerate(meccsek or []):
        nevek = {"home": m.get("home"), "away": m.get("away")}
        for side in ("home", "away"):
            nev = nevek[side]
            if not nev or (csapat is not None and nev != csapat):
                continue
            korabbi = [(x.get("minta") or {}).get(s) or {} for x in meccsek[:i]
                       for s in ("home", "away") if x.get(s) == nev]
            kc = seven_taker_choice(korabbi)
            most = {int(k): v for k, v in
                    ((m.get("minta") or {}).get(side) or {}).items()}
            if not kc or not most:
                continue
            jd, jg = most.get(kc["mez"], [0, 0])
            td = sum(int(v[0]) for k, v in most.items() if k != kc["mez"])
            tg = sum(int(v[1]) for k, v in most.items() if k != kc["mez"])
            ossz = _hetes_osszeg(korabbi)
            sz = max(ossz.items(), key=lambda kv: (kv[1][0], -kv[0]))[0]
            sd, sg = most.get(sz, [0, 0])
            jav[0] += int(jd)
            jav[1] += int(jg)
            tobbi[0] += td
            tobbi[1] += tg
            szok[0] += int(sd)
            szok[1] += int(sg)
            sorok.append({"match_id": m.get("match_id"), "team": nev,
                          "javasolt": kc["mez"], "javasolt_dobas": int(jd),
                          "javasolt_gol": int(jg), "tobbi_dobas": td,
                          "tobbi_gol": tg, "szokasos": sz})
    if jav[0] < HETES_PROBA_MIN or tobbi[0] < HETES_PROBA_MIN_TOBBI:
        return None
    jp = 100.0 * jav[1] / jav[0]
    tp = 100.0 * tobbi[1] / tobbi[0]
    szp = 100.0 * szok[1] / szok[0] if szok[0] else None
    d = jp - tp
    igazolt = d >= HETES_ITELET_PP
    return {"meccsek": len(sorok), "javasolt": jav, "tobbi": tobbi,
            "szokasos": szok, "javasolt_pct": round(jp, 1),
            "tobbi_pct": round(tp, 1),
            "szokasos_pct": None if szp is None else round(szp, 1),
            "kulonbseg_pp": round(d, 1), "sorok": sorok,
            "itelet": "igazolt" if igazolt else "nem",
            "verdict": (f"a könyvtár szerinti hetes-dobó {len(sorok)} meccsen "
                        f"{jav[1]}/{jav[0]} hetest lőtt be ({jp:.0f}%), a "
                        f"többiek {tobbi[1]}/{tobbi[0]} ({tp:.0f}%)"
                        + (f"; a szokásos dobó {szok[1]}/{szok[0]} "
                           f"({szp:.0f}%)" if szp is not None else "")
                        + " — "
                        + ("a hetes-dobó választásra lehet építeni" if igazolt
                           else "a könyvtár szerinti dobó nem jobb a "
                           "többieknél: a hetest a napi forma döntse el"))}


def live_seven_taker_alerts(match: Match, javaslatok: dict | None = None,
                            config: TacticsConfig | None = None) -> dict:
    """Élő hetes-dobó: a hetes pillanatában (rules.detect_seven_meters) a
    dobó csapat kispadjának a könyvtár szerinti dobó (`javaslatok`:
    {"home" / "away": seven_taker_choice}). Visszatérés: {"alerts":
    [{"t", "t_s", "perc", "team", "team_name", "mez", "text"}]}."""
    from .rules import detect_seven_meters
    config = config or TacticsConfig()
    alerts: list = []
    if not match.frames or not javaslatok:
        return {"alerts": alerts}
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    t0 = match.frames[0].t
    nevek = {"home": match.meta.home_team, "away": match.meta.away_team}
    for sm in detect_seven_meters(match, config):
        side = sm.get("team")
        j = (javaslatok or {}).get(side)
        if not j or side not in nevek:
            continue
        perc = int((sm["t"] - t0) / fps // 60) + 1
        alerts.append({"t": sm["t"], "t_s": round(sm["t"] / fps, 1),
                       "perc": perc, "team": side, "team_name": nevek[side],
                       "mez": int(j["mez"]),
                       "text": f"Hetes ({perc}. perc): {nevek[side]} — "
                               f"{j['verdict']}"})
    return {"alerts": alerts}


# ---- Hetes-irány: merre lő a dobó ------------------------------------------
# A kapus felkészítése a hetesre: a dobó fő iránya a könyvtárból (a dobó
# felől nézve bal / közép / jobb — rules.seven_meter_outcomes "irany").
# Egy dobó fő iránya akkor mondható ki, ha legalább HI_MIN_DOBAS
# irány-mérhető hetese van, és a fő irány részaránya legalább
# HI_DOMINANS. A próba a könyvtár időrendjében: a KORÁBBI meccsekből jósolt
# fő irány a meccs heteseiből hányat talált — a csapat fő irányához és a
# véletlenhez (három irány: 33%) mérve. Élőben a hetes pillanatában a
# VÉDEKEZŐ kispadnak szól.
HI_MIN_DOBAS = 3
HI_DOMINANS = 0.5
HI_PROBA_MIN = 8
HI_ITELET_PP = 15.0
HI_IRANYOK = ("bal", "közép", "jobb")
HI_IRANY_HU = {"bal": "balra", "közép": "középre", "jobb": "jobbra"}


def seven_direction_sample(match: Match, team: Team,
                           config: TacticsConfig | None = None) -> dict:
    """A hetes-irány NYERS, JSON-barát meccs-mintája: a `team` dobóinak
    hetesei irány szerint — {mez (str): {"bal", "közép", "jobb"}} (a dobó
    felől nézve; az irány vagy dobó nélküli hetes kimarad). Meccsek közt
    összeadható."""
    from .rules import seven_meter_outcomes
    config = config or TacticsConfig()
    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)
    ki: dict = {}
    for sm in seven_meter_outcomes(match, config):
        if sm.get("team") != team.value or sm.get("shooter_id") is None \
                or sm.get("irany") not in HI_IRANYOK:
            continue
        mez = jersey.get(sm["shooter_id"])
        if mez is None:
            continue
        r = ki.setdefault(str(int(mez)), {d: 0 for d in HI_IRANYOK})
        r[sm["irany"]] += 1
    return ki


def _irany_osszeg(mintak: list) -> dict:
    """Több meccs hetes-irány mintájának összege — {mez (int): {irány: n}}."""
    ossz: dict = {}
    for m in mintak or []:
        for mez, iranyok in (m or {}).items():
            r = ossz.setdefault(int(mez), {d: 0 for d in HI_IRANYOK})
            for d in HI_IRANYOK:
                r[d] += int((iranyok or {}).get(d, 0))
    return ossz


def _fo_irany(iranyok: dict, min_dobas: int = HI_MIN_DOBAS) -> tuple | None:
    """Egy irány-eloszlás fő iránya: (irány, dobás, részarány) — None, ha
    min_dobas-nál kevesebb a hetes, vagy a fő irány HI_DOMINANS alatt
    van. Holtversenyben a sorrend: bal, közép, jobb."""
    n = sum(int(iranyok.get(d, 0)) for d in HI_IRANYOK)
    if n < min_dobas:
        return None
    d = max(HI_IRANYOK, key=lambda x: (int(iranyok.get(x, 0)),
                                       -HI_IRANYOK.index(x)))
    arany = int(iranyok.get(d, 0)) / n
    if arany < HI_DOMINANS:
        return None
    return d, n, arany


def seven_direction_profile(mintak: list) -> dict | None:
    """A dobók hetes-irányai a kész mintákból (seven_direction_sample
    meccsenként): dobónként a fő irány (legalább HI_MIN_DOBAS hetes, a fő
    irány legalább HI_DOMINANS részarány), és a csapat egészének fő
    iránya. Visszaad: {"dobok": [{"mez", "dobas", "irany", "arany_pct",
    "verdict"}] (dobás szerint), "csapat": {"irany", "dobas",
    "arany_pct"} vagy None, "verdict"} — None, ha egy dobónak és a
    csapatnak sincs kimondható fő iránya."""
    ossz = _irany_osszeg(mintak)
    dobok = []
    for mez, iranyok in ossz.items():
        fo = _fo_irany(iranyok)
        if fo is None:
            continue
        d, n, arany = fo
        dobok.append({"mez": mez, "dobas": n, "irany": d,
                      "arany_pct": round(100.0 * arany, 1),
                      "verdict": (f"{mezszam_nevelovel(mez)} {100.0 * arany:.0f}% "
                                  f"{HI_IRANY_HU[d]} ({int(iranyok[d])}/{n})")})
    dobok.sort(key=lambda r: (-r["dobas"], r["mez"]))
    csapat_ir = {d: sum(int(v.get(d, 0)) for v in ossz.values())
                 for d in HI_IRANYOK}
    fo = _fo_irany(csapat_ir)
    csapat = None
    if fo is not None:
        d, n, arany = fo
        csapat = {"irany": d, "dobas": n, "arany_pct": round(100.0 * arany, 1)}
    if not dobok and csapat is None:
        return None
    if dobok:
        verdict = "hetes-irányaik (a dobó felől nézve): " + ", ".join(
            r["verdict"] for r in dobok)
    else:
        verdict = (f"hetes-irányuk (a dobó felől nézve): a csapat "
                   f"{csapat['arany_pct']:.0f}% {HI_IRANY_HU[csapat['irany']]} "
                   f"({csapat['dobas']} hetesből)")
    return {"dobok": dobok, "csapat": csapat, "verdict": verdict}


def seven_direction_backtest(meccsek: list,
                             csapat: str | None = None) -> dict | None:
    """A hetes-irány próbája: `meccsek` = [{"match_id", "home", "away",
    "minta": {"home", "away"} (seven_direction_sample)}] időrendben.
    Minden meccsre és oldalra a KORÁBBI meccsekből a dobók fő iránya; a
    meccs heteseiből (azoknak a dobóknak, akiknek van jósolt irányuk)
    hány ment a jósolt irányba — a csapat fő irányához (ugyanazokra a
    hetesekre) és a véletlenhez (33%) mérve. A `csapat` megadásával csak
    az ő dobóik. Mit jelent edzőileg: készülhet-e a kapus a dobó fő
    irányára, vagy a hetes-irány nem jósolható. Visszatérés: {"hetesek",
    "talalt", "talalat_pct", "csapat_talalt", "csapat_pct", "sorok",
    "itelet" ("josolhato" / "nem"), "verdict"} — None, ha HI_PROBA_MIN-nél
    kevesebb a jósolt hetes."""
    n = talalt = cs_talalt = 0
    cs_n = 0
    sorok: list = []
    for i, m in enumerate(meccsek or []):
        nevek = {"home": m.get("home"), "away": m.get("away")}
        for side in ("home", "away"):
            nev = nevek[side]
            if not nev or (csapat is not None and nev != csapat):
                continue
            korabbi = [(x.get("minta") or {}).get(s) or {} for x in meccsek[:i]
                       for s in ("home", "away") if x.get(s) == nev]
            ossz = _irany_osszeg(korabbi)
            if not ossz:
                continue
            cs_fo = _fo_irany({d: sum(int(v.get(d, 0)) for v in ossz.values())
                               for d in HI_IRANYOK})
            most = (m.get("minta") or {}).get(side) or {}
            for mez, iranyok in most.items():
                fo = _fo_irany(ossz.get(int(mez)) or {})
                if fo is None:
                    continue
                db = sum(int(iranyok.get(d, 0)) for d in HI_IRANYOK)
                if not db:
                    continue
                t = int(iranyok.get(fo[0], 0))
                n += db
                talalt += t
                ct = None
                if cs_fo is not None:
                    ct = int(iranyok.get(cs_fo[0], 0))
                    cs_n += db
                    cs_talalt += ct
                sorok.append({"match_id": m.get("match_id"), "team": nev,
                              "mez": int(mez), "josolt": fo[0], "hetesek": db,
                              "talalt": t, "csapat_irany":
                              cs_fo[0] if cs_fo else None, "csapat_talalt": ct})
    if n < HI_PROBA_MIN:
        return None
    pct = 100.0 * talalt / n
    cs_pct = 100.0 * cs_talalt / cs_n if cs_n else None
    josolhato = pct - 100.0 / 3 >= HI_ITELET_PP
    return {"hetesek": n, "talalt": talalt, "talalat_pct": round(pct, 1),
            "csapat_talalt": cs_talalt,
            "csapat_pct": None if cs_pct is None else round(cs_pct, 1),
            "sorok": sorok, "itelet": "josolhato" if josolhato else "nem",
            "verdict": (f"a dobók fő iránya {n} hetesből {talalt} alkalommal "
                        f"jött be ({pct:.0f}%"
                        + (f"; a csapat fő iránya: {cs_pct:.0f}%"
                           if cs_pct is not None else "")
                        + "; véletlen: 33%) — "
                        + ("a kapus készülhet a dobó fő irányára" if josolhato
                           else "a hetes-irányuk nem jósolható: a kapus a "
                           "mozdulatra figyeljen, ne a könyvtárra"))}


def live_seven_direction_alerts(match: Match, profilok: dict | None = None,
                                config: TacticsConfig | None = None) -> dict:
    """Élő hetes-irány: a hetes pillanatában (rules.detect_seven_meters) a
    VÉDEKEZŐ kispadnak a dobó csapat hetes-irányai (`profilok`: {"home" /
    "away": seven_direction_profile}). Visszatérés: {"alerts": [{"t",
    "t_s", "perc", "team" (a védekező), "team_name", "dobo_team",
    "text"}]}."""
    from .rules import detect_seven_meters
    config = config or TacticsConfig()
    alerts: list = []
    if not match.frames or not profilok:
        return {"alerts": alerts}
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    t0 = match.frames[0].t
    nevek = {"home": match.meta.home_team, "away": match.meta.away_team}
    for sm in detect_seven_meters(match, config):
        side = sm.get("team")
        if side not in nevek:
            continue
        pr = (profilok or {}).get(side)
        if not pr:
            continue
        masik = "away" if side == "home" else "home"
        perc = int((sm["t"] - t0) / fps // 60) + 1
        alerts.append({"t": sm["t"], "t_s": round(sm["t"] / fps, 1),
                       "perc": perc, "team": masik, "team_name": nevek[masik],
                       "dobo_team": side,
                       "text": f"Hetes ellenünk ({perc}. perc): {nevek[side]} — "
                               f"{pr['verdict']}"})
    return {"alerts": alerts}



# ---- Megéri-e a 7 a 6? -----------------------------------------------------
# A hátrányos hajrá klasszikus döntése: lehozzuk-e a kapust a hetedik
# mezőnyjátékosért. A könyvtár mérlege: a 7 a 6 szakaszok (goalkeeper.
# empty_net_goals) nettó hozama — a lőtt gólok mínusz az üres kapura
# kapottak, szakaszonként — a 6 a 6 elleni támadások gól-hozamához mérve
# (setplays.segment_attacks). Ha a 7 a 6 legalább HN_ITELET_GOL góllal
# többet hoz támadásonként, megéri; ha ennyivel kevesebbet, nem. Élőben a
# HN_ELO_PERCEK perceiben szól a HN_HATRANY_MAX góllal vesztő csapatnak.
HN_MIN_ABLAK = 8         # legalább ennyi 7 a 6 szakasz kell az ítélethez
HN_MIN_TAMADAS = 20      # és ennyi 6 a 6 támadás a viszonyításhoz
HN_ITELET_GOL = 0.05     # támadásonkénti gól-különbség az ítélethez
HN_ELO_PERCEK = (50, 55)
HN_HATRANY_MAX = 3


def seven_six_sample(match: Match, team: Team,
                     config: TacticsConfig | None = None) -> dict:
    """A 7 a 6 mérleg NYERS, JSON-barát meccs-mintája a `team` csapatra:
    {"ablak" (7 a 6 szakasz), "lott" (gól 7 a 6-ban), "kapott" (üres
    kapura kapott gól), "tamadas" (6 a 6 támadás: a támadás-szakaszok a 7
    a 6 szakaszok nélkül), "gol" (gól a 7 a 6-on kívül)}. Meccsek közt
    összeadható."""
    from .event_detection import EventType, detect_shots
    from .goalkeeper import empty_net_goals
    from .setplays import segment_attacks
    config = config or TacticsConfig()
    if not match.frames:
        return {"ablak": 0, "lott": 0, "kapott": 0, "tamadas": 0, "gol": 0}
    en = empty_net_goals(match, config).get(team.value) or {}
    ablak = int(en.get("windows", 0))
    lott = int(en.get("scored_7v6", 0))
    tam = sum(1 for sq in segment_attacks(match, config) if sq.team == team)
    gol = sum(1 for e in detect_shots(match, config)
              if e.type == EventType.GOAL and e.team == team)
    return {"ablak": ablak, "lott": lott,
            "kapott": int(en.get("conceded_empty", 0)),
            "tamadas": max(0, tam - ablak), "gol": max(0, gol - lott)}


def seven_six_backtest(meccsek: list,
                       csapat: str | None = None) -> dict | None:
    """A 7 a 6 mérlege a könyvtáron: `meccsek` = [{"home", "away",
    "minta": {"home", "away"} (seven_six_sample)}]. A 7 a 6 szakaszok
    nettó hozama ((lőtt − üres kapura kapott) / szakasz) a 6 a 6
    támadások gól-hozamához (gól / támadás) mérve; a `csapat` megadásával
    csak az ő 7 a 6-uk. Mit jelent edzőileg: a hátrányos hajrában a kapus
    lehozása a klub meccsein többet hozott-e, mint amennyibe került.
    Visszatérés: {"ablak", "lott", "kapott", "tamadas", "gol",
    "het_netto", "hat_hozam", "kulonbseg", "itelet" ("megeri" /
    "egyenlo" / "nem"), "verdict"} — None, ha HN_MIN_ABLAK-nál kevesebb a
    7 a 6 szakasz vagy HN_MIN_TAMADAS-nál a 6 a 6 támadás."""
    o = {"ablak": 0, "lott": 0, "kapott": 0, "tamadas": 0, "gol": 0}
    for m in meccsek or []:
        for side in ("home", "away"):
            if csapat is not None and m.get(side) != csapat:
                continue
            mi = (m.get("minta") or {}).get(side) or {}
            for k in o:
                o[k] += int(mi.get(k, 0))
    if o["ablak"] < HN_MIN_ABLAK or o["tamadas"] < HN_MIN_TAMADAS:
        return None
    het = (o["lott"] - o["kapott"]) / o["ablak"]
    hat = o["gol"] / o["tamadas"]
    d = het - hat
    itelet = ("megeri" if d >= HN_ITELET_GOL else
              "nem" if d <= -HN_ITELET_GOL else "egyenlo")

    def sz(x):
        return f"{x:.2f}".replace(".", ",")

    return {**o, "het_netto": round(het, 3), "hat_hozam": round(hat, 3),
            "kulonbseg": round(d, 3), "itelet": itelet,
            "verdict": (f"a 7 a 6 {o['ablak']} szakaszból {o['lott']} gólt "
                        f"hozott és {o['kapott']} gólt kapott üres kapura — "
                        f"nettó {sz(het)} gól szakaszonként, a 6 a 6 "
                        f"támadások {sz(hat)} góljához mérve: "
                        + {"megeri": "a hátrányos hajrában megéri lehozni "
                                     "a kapust",
                           "egyenlo": "a 7 a 6 nagyjából annyit hoz, mint a "
                                      "6 a 6 — a döntés a hetedik ember "
                                      "figuráján múlik",
                           "nem": "a 7 a 6 többe kerül, mint amennyit hoz: "
                                  "maradjon a kapus"}[itelet])}


def live_seven_six_alerts(match: Match, proba: dict | None = None,
                          config: TacticsConfig | None = None) -> dict:
    """Élő 7 a 6 tanács: a HN_ELO_PERCEK perceiben (CSAK az addigi gólok
    — okszerű) a legfeljebb HN_HATRANY_MAX góllal vesztő csapat
    kispadjának a 7 a 6 könyvtári mérlege (`proba`, seven_six_backtest)
    szerint. Visszatérés: {"alerts": [{"t", "t_s", "perc", "team",
    "team_name", "hatrany", "allas", "text"}]}."""
    from .event_detection import EventType, detect_shots
    config = config or TacticsConfig()
    alerts: list = []
    if not match.frames:
        return {"alerts": alerts}
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    t0 = match.frames[0].t
    nevek = {"home": match.meta.home_team, "away": match.meta.away_team}
    golok = sorted((e.t, e.team.value) for e in detect_shots(match, config)
                   if e.type == EventType.GOAL
                   and e.team.value in ("home", "away"))
    itelet = (proba or {}).get("itelet")
    tanacs = {"megeri": "a könyvtár szerint megéri lehozni a kapust",
              "egyenlo": "a könyvtár szerint a 7 a 6 annyit hoz, mint a 6 a "
                         "6 — csak kész figurával hozzátok le a kapust",
              "nem": "a könyvtár szerint a 7 a 6 többe kerül, mint amennyit "
                     "hoz: maradjon a kapus"}.get(
        itelet, "a könyvtár még nem dönti el, megéri-e a 7 a 6")
    for perc in HN_ELO_PERCEK:
        hatar = t0 + int(round(perc * 60 * fps))
        if match.frames[-1].t < hatar - fps:
            continue                      # a meccs még nem ért el idáig
        al = {"home": 0, "away": 0}
        for t, side in golok:
            if t <= hatar:
                al[side] += 1
        for side in ("home", "away"):
            masik = "away" if side == "home" else "home"
            hatrany = al[masik] - al[side]
            if not 1 <= hatrany <= HN_HATRANY_MAX:
                continue
            at = f"{al['home']}–{al['away']}"
            alerts.append({"t": hatar, "t_s": round(hatar / fps, 1),
                           "perc": perc, "team": side,
                           "team_name": nevek[side], "hatrany": hatrany,
                           "allas": [al["home"], al["away"]],
                           "text": (f"7 a 6? ({perc}. perc, {at}): "
                                    f"{nevek[side]} {hatrany} gól hátrányban "
                                    f"— {tanacs}"
                                    + (f" ({proba['verdict']})"
                                       if proba and proba.get("verdict")
                                       else ""))})
    return {"alerts": alerts}

# ---- A pad döntései a könyvtár tükrében ------------------------------------
# A meccs UTÁN: hogyan döntött a pad a könyvtár szabályaihoz képest —
# kértek-e időt a sorozat ellen (és megtört-e), ki dobta a heteseket (a
# könyvtár dobója-e), ki kezdett a kapuban (a könyvtár javaslata-e), és a
# hideg első félidő után cseréltek-e (a napi forma próbája szerint jó
# döntés-e). A próbák és a javaslatok a meccs NÉLKÜL (okszerű); ahol
# nincs próba, a mondat ítélet nélkül áll.


def decision_review(nevek: dict, idokeres_minta: dict | None,
                    hetes_mintak: dict | None,
                    kapusforma_mintak: dict | None, *,
                    idokeres_proba: dict | None = None,
                    hetes_javaslat: dict | None = None,
                    kapus_javaslat: dict | None = None,
                    kapusforma_proba: dict | None = None,
                    het_a_hat_mintak: dict | None = None,
                    het_a_hat_proba: dict | None = None) -> dict:
    """A pad döntései a könyvtár tükrében: `idokeres_minta` a meccs
    run_timeout_sample-je, `hetes_mintak` és `kapusforma_mintak`
    oldalanként a seven_taker_sample / keeper_form_sample; `idokeres_proba`
    oldalanként (timeout_run_backtest, a csapat saját időkérései),
    `hetes_javaslat` oldalanként (seven_taker_choice a többi meccsből),
    `kapus_javaslat` oldalanként (keeper_choice_from a többi meccsből),
    `kapusforma_proba` oldalanként (keeper_hot_hand_backtest),
    `het_a_hat_mintak` oldalanként (seven_six_sample) és
    `het_a_hat_proba` oldalanként (seven_six_backtest). Mit jelent
    edzőileg: a meccs utáni értekezlet pad-oldali tényei — mi volt a
    döntés, és mit mond rá a klub könyvtára. Visszatérés oldalanként:
    {"sorok": [mondatok], "idokeres": {"sorozat", "kert", "tores_kert",
    "tores_nem"} vagy None, "hetes": {"dobok": [[mez, dobás, gól]],
    "konyvtar_dobo"} vagy None, "kapus": {"kezdo", "masodik", "hideg",
    "csere"} vagy None, "het_a_hat": {"ablak", "lott", "kapott"} vagy
    None}."""
    ki: dict = {}
    helyzetek = _sorozat_helyzetek(idokeres_minta or {})
    for side in ("home", "away"):
        masik = "away" if side == "home" else "home"
        sorok: list = []
        # Időkérés a sorozat ellen.
        sajat = [h for h in helyzetek if h[1] == masik]
        ido = None
        if sajat:
            kert = [h for h in sajat if h[3]]
            tk = sum(1 for h in kert if h[2] == side)
            tn = sum(1 for h in sajat if not h[3] and h[2] == side)
            ido = {"sorozat": len(sajat), "kert": len(kert), "tores_kert": tk,
                   "tores_nem": tn}
            sor = (f"Sorozat ellenük {len(sajat)} alkalommal, időt kértek "
                   f"{len(kert)} alkalommal")
            if kert:
                sor += (f" — az időkérés után {tk} alkalommal ők szerezték a "
                        f"következő gólt")
            if len(kert) < len(sajat):
                sor += (f"; időkérés nélkül {tn} alkalommal "
                        f"({len(sajat) - len(kert)} sorozatból)")
            pr = (idokeres_proba or {}).get(side)
            if pr and pr.get("itelet") == "megtori":
                sor += (" — a könyvtár szerint az időkérés megtöri a sorozatot"
                        + (": a kihagyott sorozatnál is érdemes lett volna "
                           "időt kérni" if len(kert) < len(sajat) else
                           ": jó döntés"))
            elif pr and pr.get("itelet") == "nem_tori":
                sor += (" — a könyvtár szerint az időkérés önmagában nem töri "
                        "meg a sorozatot: váltással együtt ér valamit")
            sorok.append(sor)
        # Hetesek: ki dobta, a könyvtár dobója-e.
        hm = {int(k): v for k, v in ((hetes_mintak or {}).get(side) or {}).items()}
        hetes = None
        if hm:
            dobok = sorted(hm.items(), key=lambda kv: (-int(kv[1][0]), kv[0]))
            jav = (hetes_javaslat or {}).get(side)
            kd = int(jav["mez"]) if jav else None
            hetes = {"dobok": [[m, int(v[0]), int(v[1])] for m, v in dobok],
                     "konyvtar_dobo": kd}
            sor = "Heteseik: " + ", ".join(
                f"{mezszam_nevelovel(m)} {int(v[1])}/{int(v[0])}" for m, v in dobok)
            if kd is not None and kd in hm:
                sor += f" — a könyvtár dobója ({mezszam_nevelovel(kd)}) dobta"
                if any(m != kd for m, _v in dobok):
                    sor += ", de nem mindet"
            elif kd is not None:
                sor += (f" — a könyvtár szerint {mezszam_nevelovel(kd)} dobná "
                        f"({jav['gol']}/{jav['dobas']} a könyvtárban)")
            sorok.append(sor)
        # Kapus: ki kezdett, a könyvtár javaslata-e; csere a hideg félidő után.
        kf = {int(k): v for k, v in
              ((kapusforma_mintak or {}).get(side) or {}).items()}
        kapus = None
        elso = [(m, v[0]) for m, v in kf.items() if int(v[0][0]) > 0]
        if elso:
            kezdo, e1 = max(elso, key=lambda kv: (int(kv[1][0]), -kv[0]))
            masodik_l = [(m, v[1]) for m, v in kf.items() if int(v[1][0]) > 0]
            masodik, e2 = (max(masodik_l, key=lambda kv: (int(kv[1][0]), -kv[0]))
                           if masodik_l else (None, None))
            hideg = float(e1[2]) - int(e1[1]) <= -KF_ELO_GOL
            csere = masodik is not None and masodik != kezdo
            kapus = {"kezdo": kezdo, "masodik": masodik, "hideg": hideg,
                     "csere": csere}
            sor = (f"A kapuban {mezszam_nevelovel(kezdo)} kezdett "
                   f"({int(e1[0]) - int(e1[1])}/{int(e1[0])} az első "
                   f"félidőben)")
            kj = (kapus_javaslat or {}).get(side)
            if kj and kj.get("dontes"):
                sor += (" — a könyvtár is őt javasolta" if int(kj["kapus_mez"])
                        == kezdo else f" — a könyvtár "
                        f"{mezszam_nevelovel(int(kj['kapus_mez']))}t javasolta")
            sorok.append(sor)
            if hideg:
                vv = f"{float(e1[2]):.1f}".replace(".", ",")
                pr = (kapusforma_proba or {}).get(side)
                it = pr.get("itelet") if pr else None
                if csere:
                    sor = (f"Hideg első félidő ({int(e1[1])} kapott gól a várt "
                           f"{vv} helyett), a második félidőben "
                           f"{mezszam_nevelovel(masodik)} állt a kapuban "
                           f"({int(e2[0]) - int(e2[1])}/{int(e2[0])})")
                    if it == "kitart":
                        sor += " — a próba szerint a napi forma kitart: jó csere"
                    elif it == "visszaall":
                        sor += (" — a próba szerint a napi forma nem tart ki: a "
                                "csere nem a könyvtár szerinti")
                else:
                    sor = (f"Hideg első félidő ({int(e1[1])} kapott gól a várt "
                           f"{vv} helyett), {mezszam_nevelovel(kezdo)} maradt")
                    if e2 is not None:
                        sor += (f" (a második félidőben "
                                f"{int(e2[0]) - int(e2[1])}/{int(e2[0])})")
                    if it == "kitart":
                        sor += (" — a próba szerint a napi forma kitart: érdemes "
                                "lett volna cserélni")
                    elif it == "visszaall":
                        sor += (" — a próba szerint helyes: egy gyenge félidő "
                                "miatt nem kell cserélni")
                sorok.append(sor)
        # 7 a 6: ha lehozták a kapust, mit hozott, és mit mond a mérleg.
        hm7 = (het_a_hat_mintak or {}).get(side) or {}
        het = None
        if int(hm7.get("ablak", 0)) > 0:
            het = {k: int(hm7.get(k, 0)) for k in ("ablak", "lott", "kapott")}
            sor = (f"7 a 6: {het['ablak']} szakasz, {het['lott']} lőtt gól, "
                   f"{het['kapott']} kapott üres kapura")
            pr = (het_a_hat_proba or {}).get(side)
            it = pr.get("itelet") if pr else None
            if it == "megeri":
                sor += " — a könyvtár szerint a 7 a 6 megéri: jó döntés"
            elif it == "nem":
                sor += (" — a könyvtár szerint a 7 a 6 többe kerül, mint "
                        "amennyit hoz")
            elif it == "egyenlo":
                sor += (" — a könyvtár szerint annyit hoz, mint a 6 a 6: a "
                        "figurán múlik")
            sorok.append(sor)
        ki[side] = {"sorok": sorok, "idokeres": ido, "hetes": hetes,
                    "kapus": kapus, "het_a_hat": het}
    return ki

# ---- Élő kapus-választás ----------------------------------------------------
# A LIVE_AJANLO_PERCEK perceiben a VÉDŐ kispadnak: az ő lövőik nyers
# mintája (a szezon korábbi meccseiből + az ADDIG látottak) × a kapusaink
# kapusonkénti sáv-mérlege (a szezon korábbi meccseiből + az addig
# látottak) — keeper_choice_from. Csak akkor szól, ha a döntés érdemi
# (KAPUS_VALASZTAS_ELTERES) ÉS a kapuban most nem a javasolt kapus áll;
# egy oldal ugyanazzal a javaslattal nem ismétlődik. Okszerű: a meccsből
# csak a percig látott kockák számítanak.


def _kapus_mintak_osszege(mintak: list) -> dict:
    """Több kapusonkénti sáv-minta összege ({kapus mez: {sáv: [kaputra
    érkezett, védett]}} — _kapus_minta_kapusonkent alakban)."""
    ossz: dict = {}
    for m in mintak:
        for kmez, savok in (m or {}).items():
            for sav, (faced, saves) in savok.items():
                r = ossz.setdefault(int(kmez), {}).setdefault(sav, [0, 0])
                r[0] += int(faced)
                r[1] += int(saves)
    return ossz


def kapus_mintak_many(meccsek: list,
                      config: TacticsConfig | None = None) -> dict:
    """A csapat kapusonkénti sáv-mintája TÖBB meccsből (`meccsek` =
    [(match, a csapat oldala), …]) — a keeper_choice_from `kapusok`
    bemenete a szezonból. Üres listára üres."""
    config = config or TacticsConfig()
    return _kapus_mintak_osszege([_kapus_minta_kapusonkent(m, t, config)
                                  for m, t in meccsek])


def _kapus_most(match: Match, team: Team,
                config: TacticsConfig) -> int | None:
    """A kapuban a meccs (eddigi) végén álló kapus mezszáma — a
    goalkeeper_timeline utolsó szolgálat-szakasza szerint; None, ha nem
    ismert."""
    from .goalkeeper import goalkeeper_timeline
    stints = (goalkeeper_timeline(match, config).get(team.value) or {}
              ).get("stints") or []
    if not stints:
        return None
    tid = max(stints, key=lambda st: (st["to_s"], st["from_s"]))["track_id"]
    for f in reversed(match.frames):
        for p in f.players:
            if p.track_id == tid and p.jersey_number is not None:
                return int(p.jersey_number)
    return None


def live_keeper_alerts(match: Match, config: TacticsConfig | None = None, *,
                       lovo_mintak: dict | None = None,
                       kapus_mintak: dict | None = None) -> dict:
    """Élő kapus-választás: a LIVE_AJANLO_PERCEK perceiben csapatonként (a
    VÉDŐ oldal) melyik kapusunk álljon az ő lövőik ellen, ha most nem ő
    áll bent (keeper_choice_from). `lovo_mintak` ({"home" / "away": az
    adott kapu ELLEN támadó csapat nyers lövő-mintája}) és `kapus_mintak`
    ({…: a kapu csapatának kapusonkénti sáv-mintája}) a szezon KORÁBBI
    meccseiből — mindkettőhöz hozzáadódik az addig látott; nélkülük csak
    az addigiakból.

    Edzőileg: a kapus-csere időzítése — nem a "rossz napja van" érzésből,
    hanem az ő lövőik és a két kapus sávjai szerint.

    Visszaad: {"alerts": [{"t" (kocka), "t_s", "perc", "team",
    "team_name", "most_mez", "javasolt_mez", "elteres", "verdict",
    "text"}, …]} t és csapat szerint; üres, ha nincs érdemi különbség,
    vagy a javasolt kapus áll bent."""
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    alerts: list = []
    if not match.frames:
        return {"alerts": alerts}
    t0 = match.frames[0].t
    utolso: dict = {}
    nevek = {"home": match.meta.home_team, "away": match.meta.away_team}
    for perc in LIVE_AJANLO_PERCEK:
        hatar = t0 + int(round(perc * 60 * fps))
        eddig = [f for f in match.frames if f.t <= hatar]
        if len(eddig) < 2 or eddig[-1].t < hatar - fps:
            continue      # a meccs még nem ért el idáig
        resz = Match(meta=match.meta, frames=eddig)
        for side, team, masik in (("home", Team.HOME, Team.AWAY),
                                  ("away", Team.AWAY, Team.HOME)):
            lm = _lovo_mintak_osszege([(lovo_mintak or {}).get(side) or {},
                                       _lovo_minta(resz, masik, config)])
            km = _kapus_mintak_osszege([
                (kapus_mintak or {}).get(side) or {},
                _kapus_minta_kapusonkent(resz, team, config)])
            p = keeper_choice_from(lm, km)
            if not p or not p.get("dontes"):
                continue
            most = _kapus_most(resz, team, config)
            if most is None or most == p["kapus_mez"]:
                continue
            if utolso.get(side) == p["kapus_mez"]:
                continue
            utolso[side] = p["kapus_mez"]
            alerts.append({
                "t": hatar, "t_s": round(hatar / fps, 1), "perc": perc,
                "team": side, "team_name": nevek[side], "most_mez": most,
                "javasolt_mez": p["kapus_mez"], "elteres": p["elteres"],
                "verdict": p["verdict"],
                "text": (f"Kapus-választás ({perc}. perc): {nevek[side]} "
                         f"kapujában most {mezszam_nevelovel(most)} áll — "
                         f"{p['verdict']}")})
    alerts.sort(key=lambda a: (a["t"], a["team"]))
    return {"alerts": alerts}


# ---- Élő utolsó labda -------------------------------------------------------
# A hajrá: a felvétel vége előtt ennyi mp-cel szól (az utolsó támadások
# még elrendezhetők), ha az állás ekkor legfeljebb LIVE_UTOLSO_KULONBSEG
# gólos — mindkét kispadnak: a saját lövői az ellenfél kapusa ellen
# (last_shot_choice). A modellek a `tamadas` / `kapus` bemenetből (a
# szezon könyvtára — az API adja, EZ a meccs nélkül), különben az ADDIG
# látott kockákból tanulva: okszerű, a későbbi lövések nem számítanak.
LIVE_UTOLSO_ELOTTE_S = 180.0
LIVE_UTOLSO_KULONBSEG = 1


def kapus_many(meccsek: list, config: TacticsConfig | None = None) -> dict:
    """A csapat kapusának sávonkénti szorzója TÖBB meccsből (`meccsek` =
    [(match, a csapat oldala), …]): a sáv-minták összeadódnak
    (_kapus_minta), a szorzó az összegből (_kapus_szorzo) — a szezon-
    kapus, mint a DefenseModel.learn_many kapusa, a fal nélkül."""
    config = config or TacticsConfig()
    minta: dict = {}
    for m, t in meccsek:
        for sav, (faced, saves) in _kapus_minta(m, t, config).items():
            r = minta.setdefault(sav, [0, 0])
            r[0] += faced
            r[1] += saves
    return _kapus_szorzo(minta)


def player_model_sample(match: Match, team: Team,
                        config: TacticsConfig | None = None) -> dict:
    """A csapat játékos-modelljének NYERS, JSON-barát mintája egy meccsről
    — a lemezes eredmény-tárba tehető (a több meccses riport így a
    második hívásra nem tölti vissza a hideg meccseket), és meccsek közt
    összeadható (player_models_from_samples). {"lovo": {mez (str): {sáv:
    [lövés, gól, xG]}}, "sav": {mez (str): [lövés sávonként]}, "kapus":
    {sáv: [kaputra érkezett, védett]}, "vedok": {mez (str): {"n",
    "y_osszeg", "kozel", "ralepett", "masodik", "kettozott"}}, "kockak",
    "kapusok": {kapus mez (str): {sáv: [kaputra érkezett, védett]}},
    "formak": {védekezési rendszer: védekező kocka}} — a lövők a `team`
    lövései, a kapus, a fal és a rendszer a `team` védekezéséé."""
    config = config or TacticsConfig()
    tm = _tanulas_minta(match, team, config)
    return {
        "lovo": {str(m): {s: [int(v[0]), int(v[1]), float(v[2])]
                          for s, v in sv.items()}
                 for m, sv in _lovo_minta(match, team, config).items()},
        "sav": {str(m): [int(x) for x in v]
                for m, v in _lovo_sav_minta(match, team, config).items()},
        "kapus": {s: [int(v[0]), int(v[1])]
                  for s, v in (tm.get("kapus") or {}).items()},
        "vedok": {str(m): {k: (float(x) if k == "y_osszeg" else int(x))
                           for k, x in v.items()}
                  for m, v in (tm.get("vedok") or {}).items()},
        "kockak": int(tm.get("kockak", 0)),
        "kapusok": {str(k): {s: [int(v[0]), int(v[1])] for s, v in sv.items()}
                    for k, sv in _kapus_minta_kapusonkent(match, team,
                                                          config).items()},
        "formak": {str(k): int(v) for k, v in sorted(
            (tm.get("formak") or {}).items())}}


def player_models_from_samples(mintak: list) -> dict:
    """Több meccs player_model_sample-jéből a kész modellek: {"tamadas"
    (AttackModel), "kapus" ({sáv: szorzó}), "vedok" (DefenseModel.vedok
    alakban), "sav" ({mez (str): [lövés sávonként]}), "lovo" (az
    összegzett nyers lövő-minta), "kapusok" (kapusonkénti sáv-minta, a
    keeper_choice_from bemenete)} — a minták összeadva, a küszöbök az
    összegre (mint a learn_many / kapus_many / kapus_mintak_many)."""
    lovo = _lovo_mintak_osszege([m.get("lovo") or {} for m in mintak])
    sav: dict = {}
    kap: dict = {}
    vedok: dict = {}
    kockak = 0
    for m in mintak:
        for mez, db in (m.get("sav") or {}).items():
            r = sav.setdefault(str(mez), [0] * KITKINEK_SAVOK)
            for i, x in enumerate(db):
                r[i] += int(x)
        for s, (faced, saves) in (m.get("kapus") or {}).items():
            r = kap.setdefault(s, [0, 0])
            r[0] += int(faced)
            r[1] += int(saves)
        kockak += int(m.get("kockak") or 0)
        for mez, v in (m.get("vedok") or {}).items():
            r = vedok.setdefault(str(mez), {})
            for k, x in v.items():
                r[k] = r.get(k, 0) + x
    return {"tamadas": AttackModel._modell_mintabol(lovo),
            "kapus": _kapus_szorzo(kap),
            "vedok": _vedok_mintabol(vedok, kockak) if vedok else [],
            "sav": sav, "lovo": lovo,
            "kapusok": _kapus_mintak_osszege([m.get("kapusok") or {}
                                              for m in mintak])}


def live_last_shot_alerts(match: Match, config: TacticsConfig | None = None,
                          *, tamadas: dict | None = None,
                          kapus: dict | None = None) -> dict:
    """Élő utolsó labda: a hajrában (LIVE_UTOLSO_ELOTTE_S-szel a felvétel
    vége előtt), ha az állás szoros (legfeljebb LIVE_UTOLSO_KULONBSEG
    gól), csapatonként kimondja, kinek a kezében és honnan ér a
    legtöbbet az utolsó labda — a tanult lövőik az ellenfél kapusának
    tanult sávjai ellen (last_shot_choice). `tamadas` ({"home" / "away":
    AttackModel}) és `kapus` ({"home" / "away": a SZEMKÖZTI kapus
    sávjai}) a szezonból; ahol nincs, az addig látott kockákból tanul.

    Edzőileg: az időkérésen nem a szokás, hanem a számok döntsék el, ki
    kapja az utolsó labdát — és kit nem szabad helyzetbe hozni.

    Visszaad: {"alerts": [{"t", "t_s", "perc", "team", "team_name",
    "allas" ("hazai:vendég" a hajrá elején), "kulonbseg" (a csapat
    szemszögéből), "mez", "sav", "ertek", "text"}, …]} t és team
    szerint; üres, ha a meccs rövidebb a hajránál, az állás nem szoros,
    vagy a csapatnak nincs tanult lövő-sávja."""
    from .event_detection import EventType, detect_shots
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    frames = match.frames
    if not frames:
        return {"alerts": []}
    t_h = frames[-1].t - int(round(LIVE_UTOLSO_ELOTTE_S * fps))
    if t_h <= frames[0].t:
        return {"alerts": []}
    sc = {"home": 0, "away": 0}
    for e in detect_shots(match, config):
        if e.type == EventType.GOAL and e.t < t_h:
            sc[e.team.value] += 1
    if abs(sc["home"] - sc["away"]) > LIVE_UTOLSO_KULONBSEG:
        return {"alerts": []}
    eddig = Match(meta=match.meta, frames=[f for f in frames if f.t <= t_h])
    nevek = {"home": match.meta.home_team, "away": match.meta.away_team}
    perc = int((t_h - frames[0].t) / fps // 60)
    alerts = []
    for side, team, masik in (("home", Team.HOME, Team.AWAY),
                              ("away", Team.AWAY, Team.HOME)):
        tam = (tamadas or {}).get(side)
        if tam is None:
            tam = AttackModel.learn(eddig, team, config)
        kap = (kapus or {}).get(side)
        if kap is None:
            kap = _kapus_tanul(eddig, masik, config)
        p = last_shot_choice(tam, kap)
        if p is None:
            continue
        other = "away" if side == "home" else "home"
        kul = sc[side] - sc[other]
        helyzet = ("egál" if kul == 0 else
                   f"{abs(kul)} gól {'előny' if kul > 0 else 'hátrány'}")
        alerts.append({
            "t": t_h, "t_s": round(t_h / fps, 1), "perc": perc,
            "team": side, "team_name": nevek[side],
            "allas": f"{sc['home']}:{sc['away']}", "kulonbseg": kul,
            "mez": p["mez"], "sav": p["sav"], "ertek": p["ertek"],
            "text": (f"Utolsó labda ({perc}. perc, {sc['home']}:{sc['away']}, "
                     f"{helyzet}): {nevek[side]} utolsó labdája "
                     f"{p['verdict']}")})
    alerts.sort(key=lambda a: (a["t"], a["team"]))
    return {"alerts": alerts}
