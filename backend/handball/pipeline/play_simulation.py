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
        vedok = []
        for mez, v in m.get("vedok", {}).items():
            if v["n"] < max(PRESS_LEARN_MIN_FRAMES,
                            VEDO_JELEN_ARANY * m["kockak"]):
                continue
            vedok.append({
                "mez": mez, "y": round(v["y_osszeg"] / v["n"], 2),
                "press_rate": (round(v["ralepett"] / v["kozel"], 3)
                               if v["kozel"] >= VEDO_PRESS_MIN else None),
                "kozel": v["kozel"],
                "double_rate": (round(v["kettozott"] / v["masodik"], 3)
                                if v["masodik"] >= VEDO_PRESS_MIN else None),
                "masodik": v["masodik"]})
        vedok.sort(key=lambda r: (r["y"], r["mez"]))
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
                     config: TacticsConfig | None = None) -> tuple[Match, dict]:
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

    Visszaad: (Match — a hazai a támadó, a vendég a védő; kiértékelés:
    {"best_shot_value", "t_s" (a legjobb helyzet ideje), "attacker_id",
    "hossz_s" (a mozgás), "utak" (támadónként a pályára szorított
    kulcs-pozíciók — a padló nyilaihoz), "labda" (kulcs-pozíciónként a
    labdás sorszáma), "passzok" ([[x1, y1, x2, y2], …] — a passzok a
    kulcs-pozíciókon), "kulcs_t" (kulcs-pozíciónként az idő mp-ben, a
    kezdő állóképpel együtt — a lépésenkénti megálláshoz)}). ValueError,
    ha nincs érvényes támadó."""
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
                                 from_t=allas)
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
    return sim, {
        "best_shot_value": round(float(ertekeles["best_shot_value"]), 3),
        "t_s": (round(ertekeles["step"] / fps, 1)
                if ertekeles["step"] >= 0 else None),
        "attacker_id": ertekeles["attacker_id"],
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
                     from_t: int = 0) -> dict:
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
    """
    from .xg import xg_of_position

    config = config or TacticsConfig()
    goal_x = config.attacks_toward_x(Team.HOME)
    best = {"best_shot_value": 0.0, "step": -1, "attacker_id": None}

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
            if score > best["best_shot_value"]:
                best = {"best_shot_value": score, "step": f.t, "attacker_id": a.track_id}
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
                  config: TacticsConfig | None = None) -> dict:
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

    Visszaad: {"figurak": [{"id", "name", "pont_pct" (a legjobb
    lövőhelyzet ezen fal ellen, %), "alap_pct" (az alap-fal ellen),
    "elteres_pp", "t_s", "tamado" (a legjobb helyzetű támadó sorszáma,
    1-től)}, …] a pont szerint csökkenőben (holtversenyben név, id), és
    "ajanlas" (magyar mondat, vagy None, ha nincs értékelhető figura)}.
    A hibás (pont nélküli, nem szám koordinátájú) figura kimarad."""
    alap = DefenseModel()
    sorok = []
    for d in list(figurak or [])[:AJANLO_MAX]:
        if not isinstance(d, dict):
            continue
        try:
            _, e = setplay_3d_match(d.get("attackers") or [], defense,
                                    ball=d.get("labda"), config=config)
            _, ea = setplay_3d_match(d.get("attackers") or [], alap,
                                     ball=d.get("labda"), config=config)
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
            ajanlas += f" ({mp} mp-nél, {nevelo} {b['tamado']}. támadónál)"
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


def defense_test(match: Match, attacking: Team, defense: DefenseModel, *,
                 config: TacticsConfig | None = None) -> dict:
    """Védekezési próba: az `attacking` csapat visszatérő figuráit (a
    meccs támadás-szakaszainak klaszterei, legalább PROBA_MIN_ISMETLES
    ismétléssel) lejátsszuk a `defense` fal ellen — mint a figura-
    ajánló, csak fordítva: az ő figurájuk, a mi falunk.

    Edzőileg: "melyik figurájukra NEM vagyunk felkészülve?" — amelyik a
    mi tanult falunk ellen nagyobb lövőhelyzetet teremt, mint egy alap
    6-0 ellen, ott a falunk szokása (a kilépés, a kettőzés, a
    labdakövetés) maga nyitja a rést; azt kell a meccs előtt
    begyakorolni.

    Visszaad: {"figurak": [{"t0_s", "t1_s", "ismetles", "pont_pct",
    "alap_pct", "elteres_pp", "attackers", "labda", "tagok" (a figura
    minden előfordulása: [[kezdő kocka, záró kocka], …] időrendben — az
    élő figura-riasztás ebből ismeri fel, melyik figura indul)}, …] a
    pont szerint csökkenőben (holtversenyben az idő), és "verdict"
    (magyar mondat, vagy None, ha nincs visszatérő figura)}."""
    from .setplays import (attack_signature, cluster_signatures,
                           segment_attacks)

    config = config or TacticsConfig()
    seqs = segment_attacks(match, config)
    labels = cluster_signatures([attack_signature(s) for s in seqs])
    klaszter: dict[int, list] = {}
    for s, lab in zip(seqs, labels):
        if s.team == attacking:
            klaszter.setdefault(lab, []).append(s)
    alap = DefenseModel()
    sorok = []
    for lab in sorted(klaszter, key=lambda k: (-len(klaszter[k]), k)):
        tagok = klaszter[lab]
        if len(tagok) < PROBA_MIN_ISMETLES:
            continue
        rep = max(tagok, key=lambda s: (s.end_t - s.start_t, -s.start_t))
        fig = attack_figure(match, (rep.start_t + rep.end_t) // 2,
                            config=config)
        if fig is None:
            continue
        try:
            _, e = setplay_3d_match(fig["attackers"], defense,
                                    ball=fig["labda"], config=config)
            _, ea = setplay_3d_match(fig["attackers"], alap,
                                     ball=fig["labda"], config=config)
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
                   f"ellen {b['pont_pct']:.0f}% lövőhelyzetet teremt")
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
                   config: TacticsConfig | None = None) -> dict:
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
    FINOMITO_PASSZ_MAX_M-es passzal).

    Edzőileg: "hol nyit rést ez a fal a figurámon?" — a modell a fal
    tanult szokásai (kilépés, kettőzés, labdakövetés) ellen keresi meg,
    melyik futás végpontja ér többet néhány méterrel arrébb, és kinek
    érdemes a labdát odaadni. Javaslat, nem ítélet: az edző dönti el,
    átveszi-e.

    Visszaad: {"attackers" (a finomított kulcs-pozíciók), "labda",
    "pont_elotte", "pont_utana", "javulas_pp", "valtozasok" (magyar
    mondatok támadónként és pontonként, és a labda új útja, ha
    változott), "verdict"}. ValueError, ha nincs érvényes támadó."""
    config = config or TacticsConfig()
    goal_x = config.attacks_toward_x(Team.HOME)
    _, e0 = setplay_3d_match(keypoints, defense, ball=ball, config=config)
    utak = [[list(p) for p in u] for u in e0["utak"]]
    labda = list(e0["labda"])
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

    def pont(u, lab) -> float:
        _, e = setplay_3d_match(u, defense, ball=lab, config=config)
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
                    p = pont(proba, labda)
                    if legjobb is None or p > legjobb[0] + 1e-12:
                        legjobb = (p, proba, labda)
        # A passzok: a k. kulcs-pozíciótól a j. támadónál a labda.
        for k in range(1, len(labda)):
            for j in range(len(utak)):
                if j == labda[k] or passz_hossz(
                        utak, labda[k - 1], j, k) > FINOMITO_PASSZ_MAX_M:
                    continue
                lab = labda[:k] + [j] * (len(labda) - k)
                p = pont(utak, lab)
                if legjobb is None or p > legjobb[0] + 1e-12:
                    legjobb = (p, utak, lab)
        if legjobb is None \
                or 100.0 * (legjobb[0] - most) < FINOMITO_MIN_JAVULAS_PP:
            break
        most, utak, labda = legjobb

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
                      config: TacticsConfig | None = None) -> dict:
    """Figura-kimenetek: a figura `n` lejátszása zajos fallal (lásd a
    KIMENET_* konstansokat), kimenetenként számolva.

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
        sim, e = setplay_3d_match(keypoints, fal, ball=ball, config=config)
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
