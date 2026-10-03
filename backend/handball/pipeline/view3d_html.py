"""Böngészős 3D / VR nézet — a meccs WebXR-képes oldalként.

A kliens "3D pálya" füle a képernyős bejárás; ez a modul UGYANAZT a
meccset egyetlen HTML-oldalként adja ki, amit egy böngésző — és a
jövőben egy önálló VR-headset (Quest-féle) böngészője — telepítés
nélkül megnyit. A WebXR biztonságos környezetet kér: a localhost az
(a headsetről USB + adb reverse tesz localhosttá), ezért az út a
motor `/matches/{id}/view3d` végpontja, nem egy mentett fájl.

A megjelenítés three.js (CDN-ről, a felhasználó böngészőjében), a
követési adat TÖMÖRÍTVE ágyazódik az oldalba: legfeljebb ~6 kép/mp,
deciméterre kerekítve — egy teljes meccs így is csak pár MB.

Videó nélkül tesztelhető: a kimenet szöveg.
"""

from __future__ import annotations

import json

from ..models.tracking import Match, PositionSource, Team

# A beágyazott adat cél-képrátája. A sima lejátszáshoz a böngészőben
# interpolálunk; ~6 kép/mp fölött az adat mérete nő, a látvány nem.
VIEW3D_MAX_FPS = 6.0


def _compact_data(match: Match, figure_alerts: list | None = None) -> dict:
    """A követés tömör alakja: [[t_s, [[csapat,x,y],…], [bx,by]|0],…].

    `figure_alerts` (opcionális): a figura-riasztások ({"t", "team"}, a
    /figure-alerts alakja) — "f" típusú eseményként a jelenet-ugrásba és a
    feliratba: a visszatérő figura 3D-ben is megnézhető.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    lepes = max(1, int(round(fps / VIEW3D_MAX_FPS)))
    frames = []
    for i in range(0, len(match.frames), lepes):
        f = match.frames[i]
        jatekosok = [
            [1 if p.team == Team.HOME else 0,
             round(p.x, 1), round(p.y, 1),
             1 if p.source == PositionSource.MEASURED else 0,
             1 if getattr(p, "role", None) == "kapus" else 0,
             # Mezszám (0 = ismeretlen): a figura fölött címke — VR-ben
             # enélkül nem tudni, ki kicsoda.
             int(getattr(p, "jersey_number", None) or 0)]
            for p in f.players
        ]
        labda = ([round(f.ball.x, 1), round(f.ball.y, 1)]
                 if f.ball is not None else 0)
        frames.append([round(f.t / fps, 2), jatekosok, labda])
    # Események a jelenet-ugráshoz és a felirathoz: [t_s, típus, hazai?]
    # — a típus "g" (gól), "s" (lövés), "t" (eladás); a passz túl sűrű.
    esemenyek: list = []
    try:
        from .event_detection import detect_shots
        kod = {"goal": "g", "shot": "s", "turnover": "t"}
        for e in detect_shots(match):
            tipus = kod.get(getattr(e.type, "value", str(e.type)))
            if tipus is None:
                continue
            esemenyek.append([round(e.t / fps, 2), tipus,
                              1 if getattr(e.team, "value", e.team) == "home"
                              else 0])
    except Exception:
        esemenyek = []  # esemény nélkül is működjön a nézet
    # A visszatérő figura kezdete: "f" — a könyvtárból (több meccs kell).
    try:
        for a in (figure_alerts or []):
            esemenyek.append([round(int(a["t"]) / fps, 2), "f",
                              1 if a.get("team") == "home" else 0])
    except Exception:
        pass
    esemenyek.sort(key=lambda x: x[0])
    # A 3D eszközök közös számai (court3d): a tankönyvi falak (bal kapu
    # előtt, mélység + y) és az élő fal másodpercenként: [mp, hazai
    # védekezik?, forma-címke, a védett kapu x-e]. Hibája nem viheti el
    # a nézetet — a védekezés-panel ilyenkor csak a sablonokat adja.
    try:
        from .court3d import FORMATION_TEMPLATES
        formak = {nev: [list(p) for p in pontok]
                  for nev, pontok in FORMATION_TEMPLATES.items()}
    except Exception:
        formak = {}
    try:
        from .court3d import defence_timeline
        fal = [[r["s"], 1 if r["defending"] == "home" else 0, r["label"],
                r["goal_x"]] for r in defence_timeline(match)]
    except Exception:
        fal = []
    # Lövéstérkép: a meccs minden lövése a helyén (a match_xg az
    # elengedés kockájáról mér): [mp, hazai?, x, y, xG, kimenet, a
    # támadott kapu x-e] — a kimenet "g" gól, "v" védés, "m" mellé.
    try:
        from .tactics import TacticsConfig
        from .xg import match_xg
        cfg = TacticsConfig()
        kimenet = {"goal": "g", "save": "v"}
        lovesek = [
            [round(s["t"] / fps, 2), 1 if s["team"] == "home" else 0,
             s["x"], s["y"], round(float(s["xg"]), 3),
             kimenet.get(s["outcome"], "m"),
             cfg.attacks_toward_x(Team.HOME if s["team"] == "home"
                                  else Team.AWAY)]
            for s in match_xg(match, cfg)["shots"]]
    except Exception:
        lovesek = []  # lövéstérkép nélkül is működjön a nézet
    # Passzok: [mp, hazai?, x1, y1, x2, y2] — az adó és a fogadó helye a
    # passz kockáján; a futó passz vonala és a csapat passz-hálója ebből.
    try:
        from .event_detection import EventType, detect_events
        by_t = {f.t: f for f in match.frames}
        passzok = []
        for e in detect_events(match):
            if e.type != EventType.PASS or e.player_id is None:
                continue
            rid = (e.detail or {}).get("receiver_id")
            f = by_t.get(e.t)
            if rid is None or f is None:
                continue
            ado = next((p for p in f.players if p.track_id == e.player_id),
                       None)
            fogado = next((p for p in f.players if p.track_id == rid), None)
            if ado is None or fogado is None:
                continue
            passzok.append([round(e.t / fps, 2),
                            1 if getattr(e.team, "value", e.team) == "home"
                            else 0,
                            round(ado.x, 1), round(ado.y, 1),
                            round(fogado.x, 1), round(fogado.y, 1)])
    except Exception:
        passzok = []  # passz-vonalak nélkül is működjön a nézet
    return {
        "home": match.meta.home_team,
        "away": match.meta.away_team,
        "frames": frames,
        "events": esemenyek,
        "formations": formak,
        "defence": fal,
        "shots": lovesek,
        "passes": passzok,
    }


# A lövés-mérés a böngészőben — a `court3d.shot_geometry` PONTOS tükre
# (a teszt node-dal futtatja, és a Python-számokkal veti össze). Külön
# állandó, hogy a teszt az oldal nélkül is elérje.
LOVES_MERES_JS = """
function lovesMeres(x, y, kapu){
  // A court3d.shot_geometry tükre: a kapu közepének távolsága, a
  // kapufák közti szakasztól mért távolság (a 6 és 9 m-es vonal
  // mércéje), a két kapufa között látott kapu-szög és a sáv.
  if (kapu !== "bal" && kapu !== "jobb") kapu = x <= H/2 ? "bal" : "jobb";
  const gx = kapu === "bal" ? 0 : H, cy = W/2;
  const y1 = cy - KAPU_SZ/2, y2 = cy + KAPU_SZ/2;
  const v1x = gx - x, v1y = y1 - y, v2x = gx - x, v2y = y2 - y;
  const n1 = Math.hypot(v1x, v1y), n2 = Math.hypot(v2x, v2y);
  let szog = 180;
  if (n1 >= 1e-9 && n2 >= 1e-9){
    const c = (v1x*v2x + v1y*v2y) / (n1*n2);
    szog = Math.acos(Math.max(-1, Math.min(1, c))) * 180 / Math.PI;
  }
  const ny = Math.min(Math.max(y, y1), y2);
  const kapufa = Math.hypot(x - gx, y - ny);
  const sav = kapufa < 6 ? "kapuelőtér" : (kapufa < 9 ? "6–9 m" : "9 m-en túl");
  return {kapu, gx, tav: Math.hypot(x - gx, y - cy), kapufa, szog, sav};
}
"""


def view3d_html(match: Match, figure_alerts: list | None = None) -> str:
    """A teljes, önálló HTML-oldal (three.js CDN-ről, adat beágyazva)."""
    adat = json.dumps(_compact_data(match, figure_alerts), ensure_ascii=False,
                      separators=(",", ":"))
    cim = f"{match.meta.home_team} vs {match.meta.away_team} — 3D"
    # Nem f-string: a JS tele van kapcsos zárójellel; a beszúrás
    # helyőrző-cserével megy.
    oldal = """<!DOCTYPE html>
<html lang="hu"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>__CIM__</title>
<style>
 body{margin:0;background:#0a0e14;color:#dfe7ef;font-family:system-ui,sans-serif;overflow:hidden}
 #hud{position:fixed;left:12px;top:10px;font-size:13px;opacity:.9}
 #vez{position:fixed;left:12px;bottom:12px;right:12px;display:flex;gap:10px;align-items:center}
 #ido{font-variant-numeric:tabular-nums}
 input[type=range]{flex:1}
 button{background:#173042;color:#dfe7ef;border:1px solid #2b4a5e;border-radius:8px;padding:6px 12px;cursor:pointer}
 #sugo{position:fixed;right:12px;top:10px;font-size:11.5px;opacity:.7;text-align:right}
 #felirat{position:fixed;left:12px;bottom:56px;padding:6px 12px;border:1px solid #d9b544;border-radius:8px;background:rgba(16,24,32,.85);color:#d9b544;font-weight:600;font-size:15px;display:none}
 #eszkoz{position:fixed;left:12px;top:34px;display:flex;flex-direction:column;gap:6px;align-items:flex-start;font-size:12.5px;max-width:330px}
 #eszkoz .sor{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
 select{background:#173042;color:#dfe7ef;border:1px solid #2b4a5e;border-radius:8px;padding:5px 8px}
 button.be{background:#2f86d6;border-color:#2f86d6;color:#fff}
 #falInfo,#lovesInfo{opacity:.92;line-height:1.35}
 #meres{position:fixed;left:12px;bottom:100px;padding:8px 12px;border:1px solid #2f86d6;border-radius:8px;background:rgba(16,24,32,.88);font-size:13.5px;display:none;line-height:1.45}
 #meres button{margin-left:8px;padding:2px 8px}
 #jatekosHud{position:fixed;left:50%;top:12px;transform:translateX(-50%);padding:6px 14px;border:1px solid #2f86d6;border-radius:8px;background:rgba(16,24,32,.85);font-size:14px;font-variant-numeric:tabular-nums;display:none}
</style></head><body>
<div id="hud"><b>__CIM__</b></div>
<div id="eszkoz">
 <div class="sor">
  <button id="keringGomb" title="Keringés a pálya körül (O)">Keringés</button>
  <button id="jatekosKi" style="display:none" title="Vissza a szabad nézetbe (Esc)">Játékos-nézet ✕</button>
  <select id="jatekosKamera" title="Játékos-kamera: a kamera egy mezszámot követ hátulról (az appbeli Játékos-kamera párja)">
   <option value="">Játékos-kamera: ki</option>
  </select>
 </div>
 <div class="sor">
  <label>Védekezés
   <select id="fal">
    <option value="">ki</option>
    <option value="elo">élő — a mostani fal</option>
    <option value="6-0">6-0 sablon</option>
    <option value="5-1">5-1 sablon</option>
    <option value="4-2">4-2 sablon</option>
    <option value="3-2-1">3-2-1 sablon</option>
   </select></label>
  <select id="falOldal" title="Melyik kapu elé">
   <option value="auto">a védett kapu</option>
   <option value="bal">bal kapu</option>
   <option value="jobb">jobb kapu</option>
  </select>
 </div>
 <div id="falInfo"></div>
 <div class="sor">
  <label>Lövéstérkép
   <select id="lovesek" title="A meccs lövései a padlón; katt egy körre — odaugrik">
    <option value="">ki</option>
    <option value="mind">mind</option>
    <option value="eddig">eddig (a lejátszásig)</option>
    <option value="hazai">csak hazai</option>
    <option value="vendeg">csak vendég</option>
   </select></label>
 </div>
 <div id="lovesInfo"></div>
 <div class="sor">
  <label>Passzok
   <select id="passz" title="A futó passz vonala, vagy a csapat minden passza a padlón">
    <option value="">ki</option>
    <option value="elo">élő — a futó passz</option>
    <option value="hazai">hazai passz-háló</option>
    <option value="vendeg">vendég passz-háló</option>
   </select></label>
  <span id="passzInfo"></span>
 </div>
 <div class="sor">
  <label>Hőtérkép
   <select id="hoter" title="Hol tartózkodott a csapat a meccsen (mért helyek, 2 m-es cellák)">
    <option value="">ki</option>
    <option value="hazai">hazai</option>
    <option value="vendeg">vendég</option>
    <option value="mind">mindkettő</option>
   </select></label>
 </div>
 <div class="sor">
  <button class="nezet" data-n="lelato">Lelátó</button>
  <button class="nezet" data-n="kapu">Kapu mögül</button>
  <button class="nezet" data-n="palya">Pálya-szint</button>
  <button class="nezet" data-n="madar">Madártávlat</button>
 </div>
 <div class="sor">
  <button id="linkGomb" title="Link a mostani jelenetre: idő, kamera-állás, bekapcsolt rétegek — megosztható">Link másolása</button>
  <span id="linkInfo"></span>
 </div>
</div>
<div id="sugo">Húzás — körülnézés · WASD — mozgás · R/F (C) — fel/le · Shift — gyors<br>
Görgetés — előre ugrás (keringésben: közelítés) · O — keringés a pálya körül<br>
Dupla katt egy játékosra — az ő szemével, vele együtt (Esc kilép); fent: a sebessége és a megtett útja<br>
Játékos-kamera — egy mezszám hátulról, simítva követve (húzás/WASD visszavált)<br>
Katt a padlóra — lövés-mérés (távolság, kapu-szög) · Szóköz — lejátszás<br>
Lövéstérkép: katt egy körre — odaugrik a lövéshez (kör = xG, arany gyűrű = gól)<br>
Lent: sebesség (0,5–4×) · Labda-nyom — a labda útja az utolsó 3 mp-ben<br>
Hőtérkép — hol tartózkodott a csapat (2 m-es cellák) · Nézet-gombok — kész kamera-állások<br>
Passzok — a futó passz vonala (adótól a fogadóig), vagy a csapat passz-hálója a padlón<br>
Link másolása — a mostani jelenet (idő, kamera, rétegek) megosztható címként<br>
[ / ] — előző / következő esemény (gól, lövés, eladás)<br>
VR-headsetben: a lenti "ENTER VR" gomb</div>
<div id="meres"></div>
<div id="jatekosHud"></div>
<div id="felirat"></div>
<div id="vez">
 <button id="elozo" title="Előző esemény">⏮</button>
 <button id="lejatszas">▶</button>
 <button id="kov" title="Következő esemény">⏭</button>
 <input type="range" id="csuszka" min="0" max="0" step="0.01" value="0">
 <span id="ido">0:00</span>
 <select id="sebesseg" title="Lejátszás sebessége">
  <option value="0.5">0,5×</option>
  <option value="1" selected>1×</option>
  <option value="2">2×</option>
  <option value="4">4×</option>
 </select>
 <label title="A labda útja az utolsó 3 másodpercben"><input type="checkbox" id="nyom"> Labda-nyom</label>
</div>
<script type="importmap">{"imports":{
 "three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
 "three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
}}</script>
<script type="module">
import * as THREE from "three";
import {VRButton} from "three/addons/webxr/VRButton.js";

const ADAT = __ADAT__;
const H = 40, W = 20, KAPU_SZ = 3;
__LOVES_JS__

const szinpad = new THREE.Scene();
szinpad.background = new THREE.Color(0x0a0e14);
const kamera = new THREE.PerspectiveCamera(60, innerWidth/innerHeight, .1, 300);
// A VR-ben a kamera a "rig"-en ül: a rig mozog, a fejmozgás a headseté.
const rig = new THREE.Group();
rig.position.set(20, 1.6, 27); // pályaközép előtt, szemmagasságban
rig.add(kamera);
szinpad.add(rig);

const fest = new THREE.WebGLRenderer({antialias:true});
fest.setSize(innerWidth, innerHeight);
fest.xr.enabled = true;
document.body.appendChild(fest.domElement);
document.body.appendChild(VRButton.createButton(fest));
addEventListener("resize", () => {
  kamera.aspect = innerWidth/innerHeight; kamera.updateProjectionMatrix();
  fest.setSize(innerWidth, innerHeight);
});

// Pálya: talaj + vonalak. A pálya-sík a three x/z síkja (y felfelé):
// pálya (x,y) → three (x, 0, W - y), így a nézet jobbkezes marad.
// CSARNOK: fa parketta a pályán (a vonalak rajta), sötétebb padló
// körülötte, és lelátó-tömbök a két hosszoldalon — a bejárás közben
// ettől lesz "teremben vagyunk" érzet, nem a semmiben lebegő vonalak.
const csarnokPadlo = new THREE.Mesh(
  new THREE.PlaneGeometry(H+40, W+40),
  new THREE.MeshLambertMaterial({color:0x151b24}));
csarnokPadlo.rotation.x = -Math.PI/2; csarnokPadlo.position.set(H/2, -0.02, W/2);
szinpad.add(csarnokPadlo);
const talaj = new THREE.Mesh(
  new THREE.PlaneGeometry(H+2, W+2),
  new THREE.MeshLambertMaterial({color:0x8a5a34}));
talaj.rotation.x = -Math.PI/2; talaj.position.set(H/2, -0.01, W/2);
szinpad.add(talaj);
// Parketta-csíkok: keskeny, váltakozó árnyalatú sávok a hossz mentén.
for (let i = 0; i < 20; i++){
  const csik = new THREE.Mesh(new THREE.PlaneGeometry(H+2, (W+2)/20 - 0.02),
    new THREE.MeshLambertMaterial({color: i % 2 ? 0x8f5e37 : 0x845531}));
  csik.rotation.x = -Math.PI/2;
  csik.position.set(H/2, -0.005, -1 + (W+2)/20*(i+0.5));
  szinpad.add(csik);
}
const lelatoAnyag = new THREE.MeshLambertMaterial({color:0x2b3a4a});
for (const oldal of [-1, 1]){
  for (let lepcso = 0; lepcso < 6; lepcso++){
    const tomb = new THREE.Mesh(new THREE.BoxGeometry(H+16, 0.5, 1.6), lelatoAnyag);
    const z = oldal < 0 ? -4 - lepcso*1.6 : W + 4 + lepcso*1.6;
    tomb.position.set(H/2, 0.25 + lepcso*0.5, z);
    szinpad.add(tomb);
  }
}
const vonalSzin = new THREE.LineBasicMaterial({color:0x9fb6c6});
function vonal(pontok){
  const g = new THREE.BufferGeometry().setFromPoints(
    pontok.map(p => new THREE.Vector3(p[0], 0.01, W - p[1])));
  szinpad.add(new THREE.Line(g, vonalSzin));
}
vonal([[0,0],[H,0],[H,W],[0,W],[0,0]]);
vonal([[H/2,0],[H/2,W]]);
// Szabálykönyv-hű kapuelőtér: negyedkör az alsó kapufa körül →
// egyenes a kapu előtt → negyedkör a felső kapufa körül. A 9 m-es
// szabaddobási vonal ugyanez az alak 9 m-rel — a pályán belüli része.
function kapufaIv(bal, r){
  const cx = bal ? 0 : H, also = W/2-1.5, felso = W/2+1.5;
  const ut = [];
  for (let a=-90; a<=0; a+=3){
    const rad = a*Math.PI/180;
    ut.push([cx + (bal?1:-1)*Math.cos(rad)*r, also + Math.sin(rad)*r]);
  }
  for (let a=0; a<=90; a+=3){
    const rad = a*Math.PI/180;
    ut.push([cx + (bal?1:-1)*Math.cos(rad)*r, felso + Math.sin(rad)*r]);
  }
  return ut.filter(p => p[1] >= 0 && p[1] <= W);
}
function kapuElo(bal, r){ vonal(kapufaIv(bal, r)); }
kapuElo(true, 6); kapuElo(false, 6);
// A 9 m-es vonal SZAGGATOTT (a szabálykönyv 15 cm-es szakaszai).
const szaggatottSzin = new THREE.LineDashedMaterial(
  {color:0x9fb6c6, dashSize:0.3, gapSize:0.3});
for (const bal of [true, false]){
  const g = new THREE.BufferGeometry().setFromPoints(
    kapufaIv(bal, 9).map(p => new THREE.Vector3(p[0], 0.01, W - p[1])));
  const l = new THREE.Line(g, szaggatottSzin);
  l.computeLineDistances();
  szinpad.add(l);
}
// Hetes-vonal (1 m, 7 m-re), kapus-vonal (4 m-re; láthatóra nyújtva),
// és a cserevonalak jele az oldalvonalon (a félpályától 4,5 m-re).
for (const bal of [true, false]){
  const x7 = bal ? 7 : H - 7, x4 = bal ? 4 : H - 4;
  vonal([[x7, W/2 - 0.5], [x7, W/2 + 0.5]]);
  vonal([[x4, W/2 - 0.475], [x4, W/2 + 0.475]]);
}
for (const x of [H/2 - 4.5, H/2 + 4.5]) vonal([[x, -0.15], [x, 0.15]]);
// Kapuk (3 m széles, 2 m magas keret).
const kapuSzin = new THREE.LineBasicMaterial({color:0xd9b544});
for (const x of [0, H]){
  const g = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(x, 0, W - (W/2-1.5)),
    new THREE.Vector3(x, 2, W - (W/2-1.5)),
    new THREE.Vector3(x, 2, W - (W/2+1.5)),
    new THREE.Vector3(x, 0, W - (W/2+1.5)),
  ]);
  szinpad.add(new THREE.Line(g, kapuSzin));
}

// Játékos-figurák készlete (újrahasznosítva képkockánként): fej hajjal,
// mez a csapatszínben, nadrág, karok és lábak — a haladás irányába
// fordulnak, a sebességgel arányosan lépnek. Ugyanaz, mint az appbeli
// 3D pályán.
const hazaiAnyag = new THREE.MeshLambertMaterial({color:0x2f86d6});
const vendegAnyag = new THREE.MeshLambertMaterial({color:0xd65a4a});
const hazaiNadrag = new THREE.MeshLambertMaterial({color:0x17436b});
const vendegNadrag = new THREE.MeshLambertMaterial({color:0x6b2d25});
const borAnyag = new THREE.MeshLambertMaterial({color:0xe3b98f});
const hajAnyag = new THREE.MeshLambertMaterial({color:0x3a2a1e});
const zokniAnyag = new THREE.MeshLambertMaterial({color:0xeeeeee});
const kapusAnyag = new THREE.MeshLambertMaterial({color:0x3fbf6f});
const kapusNadrag = new THREE.MeshLambertMaterial({color:0x1f5f38});
szinpad.add(new THREE.HemisphereLight(0xdfe7ef, 0x101820, 1.1));
const napfeny = new THREE.DirectionalLight(0xffffff, 0.6);
napfeny.position.set(10, 30, 10); szinpad.add(napfeny);
const babuk = [];
function vegtag(anyag, r, hossz){
  // Egy végtag-szakasz: a forgáspontja a felső végén (a csoport
  // origójában), a lekerekített test lefelé lóg — így a forgatás
  // lendítés. Kapszula: a végtag nem "cső", hanem gömbölyű.
  const cs = new THREE.Group();
  const m = new THREE.Mesh(new THREE.CapsuleGeometry(r, Math.max(0.05, hossz - 2*r), 3, 8), anyag);
  m.position.y = -hossz/2; cs.add(m);
  return cs;
}
function babu(){
  const cs = new THREE.Group();
  // Törzs: lekerekített kapszula (váll-szélesség), fölötte nyak.
  const mez = new THREE.Mesh(new THREE.CapsuleGeometry(0.19, 0.3, 4, 10), hazaiAnyag);
  mez.scale.set(1.15, 1, 0.75); mez.position.y = 1.2; cs.add(mez);
  const nyak = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.06, 0.1, 8), borAnyag);
  nyak.position.y = 1.5; cs.add(nyak);
  const nadrag = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.19, 0.28, 10), hazaiNadrag);
  nadrag.position.y = 0.82; cs.add(nadrag);
  const fej = new THREE.Mesh(new THREE.SphereGeometry(0.12, 12, 10), borAnyag);
  fej.scale.set(0.95, 1.1, 1.0); fej.position.y = 1.66; cs.add(fej);
  const haj = new THREE.Mesh(new THREE.SphereGeometry(0.125, 10, 6, 0, Math.PI*2, 0, Math.PI/2), hajAnyag);
  haj.position.y = 1.67; cs.add(haj);
  const tagok = {};
  for (const oldal of [-1, 1]){
    const comb = vegtag(borAnyag, 0.07, 0.42); comb.position.set(oldal*0.11, 0.92, 0);
    const labszar = vegtag(zokniAnyag, 0.055, 0.44); labszar.position.y = -0.42; comb.add(labszar);
    const felkar = vegtag(hazaiAnyag, 0.05, 0.3); felkar.position.set(oldal*0.25, 1.42, 0);
    const alkar = vegtag(borAnyag, 0.04, 0.28); alkar.position.y = -0.3; felkar.add(alkar);
    cs.add(comb); cs.add(felkar);
    tagok[oldal] = {comb, labszar, felkar, alkar};
  }
  const arnyek = new THREE.Mesh(new THREE.CircleGeometry(0.3, 12),
    new THREE.MeshBasicMaterial({color:0x000000, transparent:true, opacity:0.35}));
  arnyek.rotation.x = -Math.PI/2; arnyek.position.y = 0.005; cs.add(arnyek);
  // Mezszám-címke a fej fölött (sprite: mindig a kamera felé néz).
  const cimke = new THREE.Sprite(new THREE.SpriteMaterial({transparent:true, depthTest:false}));
  cimke.position.y = 2.0; cimke.scale.set(0.5, 0.28, 1); cimke.visible = false; cs.add(cimke);
  cs.userData = {mez, nadrag, felkarok:[tagok[-1].felkar, tagok[1].felkar], tagok, elozo:null,
                 cimke, cimkeKulcs:null};
  szinpad.add(cs);
  babuk.push(cs);
  return cs;
}
// Mezszám-textúrák: számonként és csapatonként egyszer rajzoljuk.
const szamTexturak = new Map();
function szamTextura(n, hazai){
  const kulcs = n + ":" + (hazai ? 1 : 0);
  if (szamTexturak.has(kulcs)) return szamTexturak.get(kulcs);
  const c = document.createElement("canvas"); c.width = 128; c.height = 72;
  const g = c.getContext("2d");
  g.fillStyle = hazai ? "rgba(76,154,255,0.92)" : "rgba(255,107,107,0.92)";
  g.beginPath(); g.roundRect(4, 4, 120, 64, 14); g.fill();
  g.fillStyle = "#ffffff"; g.font = "bold 44px sans-serif";
  g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(String(n), 64, 38);
  const tex = new THREE.CanvasTexture(c);
  szamTexturak.set(kulcs, tex);
  return tex;
}
function szinez(cs, hazai, kapus){
  // A kapus a valóságban is MÁS mezben játszik (a szabály előírja): a
  // 3D-ben zöld mez + hosszú (a nadrágig érő) nadrág jelzi.
  const u = cs.userData;
  const felso = kapus ? kapusAnyag : (hazai ? hazaiAnyag : vendegAnyag);
  u.mez.material = felso;
  u.nadrag.material = kapus ? kapusNadrag : (hazai ? hazaiNadrag : vendegNadrag);
  for (const f of u.felkarok) f.children[0].material = felso;
}
function lendit(cs, seb, t, k){
  // Lépés: a sebességgel nő az ütem és az amplitúdó; a két oldal
  // ellenütemben, a karok a lábakkal szemben.
  const amp = Math.min(1, seb/5), utem = 1.2 + seb*0.35;
  const f = Math.sin(t*2*Math.PI*utem + (k%7)*0.9) * amp;
  const u = cs.userData;
  for (const oldal of [-1, 1]){
    const s = -oldal*f;
    u.tagok[oldal].comb.rotation.x = s*0.6;
    u.tagok[oldal].labszar.rotation.x = Math.max(0, -s)*0.8;
    u.tagok[oldal].felkar.rotation.x = -s*0.5;
    u.tagok[oldal].alkar.rotation.x = -0.4;
  }
}
const labda = new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 10),
  new THREE.MeshBasicMaterial({color:0xe8a33d}));
szinpad.add(labda);

// Lejátszás + interpoláció.
const frames = ADAT.frames;
const veg = frames.length ? frames[frames.length-1][0] : 0;
// ?t=349 — a jelenet-ugrás: az appból (vagy megosztott linkből) az
// oldal az adott játékidő-másodpercen nyílik, és rögtön játszik.
const t0 = Math.max(0, Math.min(veg,
  parseFloat(new URLSearchParams(location.search).get("t") || "0") || 0));
let ido = t0, megy = t0 > 0, utolso = performance.now();
const csuszka = document.getElementById("csuszka");
csuszka.max = veg;
const lejatszasGomb = document.getElementById("lejatszas");
lejatszasGomb.onclick = () => { megy = !megy; lejatszasGomb.textContent = megy ? "⏸" : "▶"; };
if (megy) lejatszasGomb.textContent = "⏸";
csuszka.value = ido;
csuszka.oninput = () => { ido = parseFloat(csuszka.value); };
// Lejátszás sebessége (0,5–4×): a lassítás a jelenet-elemzésé, a
// gyorsítás az átnézésé.
const sebessegValaszto = document.getElementById("sebesseg");
let sebesseg = 1;
sebessegValaszto.onchange = () => { sebesseg = parseFloat(sebessegValaszto.value) || 1; };
// Esemény-ugrás (⏮/⏭ és [ / ]): a jelenet előtt 4 mp-cel, lejátszva —
// mint az appból érkezve. Egy másodpercnyi holt sáv, hogy az épp nézett
// esemény ne "ragadjon". A felirat a jelenet közben mondja, mi történik.
const ESEM = ADAT.events || [];
const NEV = {g: "GÓL", s: "Lövés", t: "Labdaeladás", f: "Ismert figura"};
function esemenyUgras(irany){
  if (!ESEM.length) return;
  let cel = null;
  if (irany > 0){ for (const e of ESEM){ if (e[0] > ido + 1){ cel = e; break; } } }
  else { for (let i = ESEM.length-1; i >= 0; i--){ if (ESEM[i][0] < ido - 1){ cel = ESEM[i]; break; } } }
  if (!cel) return;
  ido = Math.max(0, cel[0] - 4); megy = true; lejatszasGomb.textContent = "⏸";
  csuszka.value = ido;
}
document.getElementById("elozo").onclick = () => esemenyUgras(-1);
document.getElementById("kov").onclick = () => esemenyUgras(1);
const feliratElem = document.getElementById("felirat");
function felirat(t){
  for (const e of ESEM){
    if (t < e[0] - 0.3) break;
    if (t > e[0] + 2.5) continue;
    feliratElem.textContent = NEV[e[1]] + " — " + (e[2] ? ADAT.home : ADAT.away);
    feliratElem.style.display = "block";
    return;
  }
  feliratElem.style.display = "none";
}
function keres(t){
  let lo = 0, hi = frames.length-1;
  while (lo < hi){ const kozep = (lo+hi+1)>>1;
    if (frames[kozep][0] <= t) lo = kozep; else hi = kozep-1; }
  return lo;
}
// A legutóbb kirajzolt állás figuránként (pálya-méterben) — a
// játékos-nézet, a védekezés-panel és a dupla kattintás ebből dolgozik.
const allas = [];
function rajzol(t){
  if (!frames.length) return;
  const i = keres(t), a = frames[i],
        b = frames[Math.min(i+1, frames.length-1)];
  const ar = b[0] > a[0] ? (t - a[0]) / (b[0] - a[0]) : 0;
  const jat = a[1];
  allas.length = 0;
  while (babuk.length < jat.length) babu();
  for (let k = 0; k < babuk.length; k++){
    const cs = babuk[k];
    if (k >= jat.length){ cs.visible = false; continue; }
    cs.visible = true;
    // Index-alapú párosítás két kocka közt: csak azonos csapatú párra
    // interpolálunk (a sorrend kockánként eltérhet), különben ugrunk.
    const p = jat[k],
          q = (b[1] && b[1][k] && b[1][k][0] === p[0]) ? b[1][k] : p;
    const x = p[1] + (q[1]-p[1])*ar, y = p[2] + (q[2]-p[2])*ar;
    cs.position.set(x, 0, W - y);
    allas.push({k, x, y, hazai: !!p[0], kapus: !!p[4], mez: p[5] || 0, seb: 0});
    szinez(cs, !!p[0], !!p[4]);
    // Mezszám-címke: csak ismert számnál; a textúra csapatonként/számonként egy.
    const mezszam = p[5] || 0, u = cs.userData;
    if (mezszam){
      const kulcs = mezszam + ":" + (p[0] ? 1 : 0);
      if (u.cimkeKulcs !== kulcs){
        u.cimke.material.map = szamTextura(mezszam, !!p[0]);
        u.cimke.material.needsUpdate = true; u.cimkeKulcs = kulcs;
      }
      u.cimke.visible = true;
    } else { u.cimke.visible = false; }
    // Irány és sebesség a két kocka elmozdulásából (követés-ugrás
    // kiszűrve); álló játékos tartja az előző irányát.
    const dx = q[1]-p[1], dy = q[2]-p[2], dt = Math.max(0.05, b[0]-a[0]);
    const seb = Math.hypot(dx, dy)/dt;
    allas[allas.length-1].seb = seb <= 8 ? seb : 0;
    if (seb > 0.3 && seb <= 8){ cs.rotation.y = Math.atan2(dx, -dy); }
    lendit(cs, seb <= 8 ? seb : 0, t, k);
    cs.scale.setScalar(p[3] ? 1 : 0.92);
  }
  let l = a[2];
  if (l){
    const l2 = b[2] || l;
    const lx = l[0] + (l2[0]-l[0])*ar, ly = l[1] + (l2[1]-l[1])*ar;
    labda.visible = true;
    // Ha van BIRTOKOSA (a legközelebbi figura karnyújtásnyira van), a
    // labda a kezében van — nem a földszint fölött lebeg.
    let birtokos = null, legkozelebb = 1.2;
    for (let k = 0; k < jat.length && k < babuk.length; k++){
      const d = Math.hypot(jat[k][1]-lx, jat[k][2]-ly);
      if (d < legkozelebb){ legkozelebb = d; birtokos = babuk[k]; }
    }
    if (birtokos){
      // A figura ELEJE a helyi +z: a forgatás atan2(dx, -dy), így a
      // (0,0,1) forgatva a haladás iránya. (A (0,0,-1) a háta mögé tette
      // a labdát.)
      const irany = new THREE.Vector3(0, 0, 1)
        .applyAxisAngle(new THREE.Vector3(0,1,0), birtokos.rotation.y);
      labda.position.set(birtokos.position.x + irany.x*0.32, 1.28,
                         birtokos.position.z + irany.z*0.32);
    } else {
      labda.position.set(lx, 0.5, W - ly);
    }
  } else labda.visible = false;
}

// ---- Kamera-módok -------------------------------------------------
// "szabad": húzás — körülnézés, WASD — mozgás, görgetés — előre ugrás.
// "kering": a pálya közepe körül; húzás — keringés, görgetés/csípés —
//           közelítés. WASD-re szabad módba vált (aki mozog, vezetni akar).
// "jatekos": a kiválasztott játékos SZEMÉVEL, vele együtt halad (dupla
//           kattintás egy figurára); húzás — körülnéz, Esc — kilép.
// "kovetes": JÁTÉKOS-KAMERA — egy mezszámot hátulról, 4 m-ről, 2,2 m
//           magasból, simítva követ (az appbeli Játékos-kamera párja);
//           húzás vagy WASD visszavált szabadra.
let mod = "szabad";
let yaw = 0, pitch = 0;
const CEL = new THREE.Vector3(H/2, 0, W/2);          // a pálya közepe (three-tér)
const kering = {theta: 0, phi: 0.6, r: 30};
const jatekosNez = {yaw: 0, pitch: -0.05};
let kovet = null;   // {hazai, mez, x, y, irany} — a játékos-nézet célja
const keringGomb = document.getElementById("keringGomb");
const jatekosKiGomb = document.getElementById("jatekosKi");
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

function modValt(uj){
  if (uj === "kering" && mod !== "kering"){
    // A keringés onnan indul, ahol a kamera áll — nem ugrik.
    const off = rig.position.clone().sub(CEL);
    kering.r = clamp(off.length(), 4, 80);
    kering.phi = clamp(Math.asin(clamp(off.y / Math.max(1e-6, off.length()), -1, 1)), 0.08, 1.5);
    kering.theta = Math.atan2(off.x, off.z);
  }
  if (uj === "szabad" && mod === "kering"){ yaw = kering.theta; pitch = -kering.phi; }
  if (uj === "szabad" && mod === "jatekos"){
    yaw = rig.rotation.y; pitch = jatekosNez.pitch;
    rig.position.y = Math.max(rig.position.y, 1.6);
  }
  if (uj !== "jatekos"){ kovet = null; jatekosHud.style.display = "none"; }
  if (uj === "szabad" && mod === "kovetes"){ yaw = rig.rotation.y; pitch = kamera.rotation.x; }
  if (uj !== "kovetes"){ kovetKam = null; jatekosKameraValaszto.value = ""; }
  mod = uj;
  keringGomb.classList.toggle("be", mod === "kering");
  jatekosKiGomb.style.display = mod === "jatekos" ? "" : "none";
}
keringGomb.onclick = () => modValt(mod === "kering" ? "szabad" : "kering");

// ---- Játékos-kamera: egy mezszám hátulról követve ---------------------
// A mezszámok a kockákból (csapatonként, rendezve); a kamera a játékos
// mögé áll a simított haladási irányában, és a fejére néz. A zajos
// követés ne rángassa: erős simítás az irányon és a helyen is.
const jatekosKameraValaszto = document.getElementById("jatekosKamera");
let kovetKam = null;  // {hazai, mez, ix, iy, ex, ey}
{
  const mezek = {1: new Set(), 0: new Set()};
  for (const f of frames) for (const p of f[1]) if (p[5]) mezek[p[0]].add(p[5]);
  for (const cs of [1, 0]){
    for (const mez of [...mezek[cs]].sort((a, b) => a - b)){
      const o = document.createElement("option");
      o.value = (cs ? "h" : "v") + mez;
      o.textContent = (cs ? ADAT.home : ADAT.away) + " " + mez;
      jatekosKameraValaszto.appendChild(o);
    }
  }
}
jatekosKameraValaszto.onchange = () => {
  const v = jatekosKameraValaszto.value;
  if (!v){ if (mod === "kovetes") modValt("szabad"); return; }
  modValt("kovetes");
  kovetKam = {hazai: v[0] === "h", mez: parseInt(v.slice(1), 10), ix: 0, iy: 0, ex: null, ey: null};
  jatekosKameraValaszto.value = v;
  if (!megy){ megy = true; lejatszasGomb.textContent = "⏸"; }
};
function kovetesFrissit(dt){
  if (mod !== "kovetes" || !kovetKam) return;
  const cel = allas.find(s => s.hazai === kovetKam.hazai && s.mez === kovetKam.mez);
  if (!cel) return;
  const k = kovetKam;
  if (k.ex !== null && dt > 0){
    const vx = (cel.x - k.ex) / dt, vy = (cel.y - k.ey) / dt, seb = Math.hypot(vx, vy);
    if (seb > 0.6){
      const ks = clamp(dt * 1.5, 0, 1);
      k.ix += (vx / seb - k.ix) * ks; k.iy += (vy / seb - k.iy) * ks;
      const h = Math.hypot(k.ix, k.iy);
      if (h > 1e-6){ k.ix /= h; k.iy /= h; }
    }
  }
  k.ex = cel.x; k.ey = cel.y;
  // Cél-hely pálya-térben (a játékos mögött 4 m, 2,2 m magasan) → three.
  const cx = cel.x - k.ix * 4.0, cy = cel.y - k.iy * 4.0;
  const ka = clamp(dt * 3.0, 0, 1);
  rig.position.x += (cx - rig.position.x) * ka;
  rig.position.z += ((W - cy) - rig.position.z) * ka;
  rig.position.y += (2.2 - rig.position.y) * ka;
  if (!fest.xr.isPresenting){
    // A fejére néz: az előre-irány three-ben (−sin yaw, −cos yaw).
    const dx = cel.x - rig.position.x, dz = (W - cel.y) - rig.position.z, dy = 1.3 - rig.position.y;
    rig.rotation.y = Math.atan2(-dx, -dz);
    kamera.rotation.set(Math.atan2(dy, Math.hypot(dx, dz)), 0, 0);
  }
}
jatekosKiGomb.onclick = () => modValt("szabad");

// Asztali irányítás: billentyűk.
const gombok = new Set();
addEventListener("keydown", e => {
  if (e.target && (e.target.tagName === "SELECT" || e.target.tagName === "INPUT")) return;
  if (e.code === "Space"){ lejatszasGomb.onclick(); e.preventDefault(); return; }
  if (e.code === "BracketLeft"){ esemenyUgras(-1); return; }
  if (e.code === "BracketRight"){ esemenyUgras(1); return; }
  if (e.code === "KeyO"){ keringGomb.onclick(); return; }
  if (e.code === "Escape"){ if (mod === "jatekos") modValt("szabad"); else meresTorles(); return; }
  if (["KeyW","KeyA","KeyS","KeyD","KeyR","KeyF","KeyC"].includes(e.code)
      && mod !== "szabad") modValt("szabad");
  gombok.add(e.code);
});
addEventListener("keyup", e => gombok.delete(e.code));

// Egér/érintés: húzás — nézés vagy keringés; rövid katt — mérés;
// dupla katt — játékos-nézet; két ujj — csípés-zoom.
const ujjak = new Map();
let huzas = null, csipes = null, kattIdozito = null;
const vaszon = fest.domElement;
vaszon.style.touchAction = "none";
vaszon.addEventListener("pointerdown", e => {
  ujjak.set(e.pointerId, {x: e.clientX, y: e.clientY});
  vaszon.setPointerCapture(e.pointerId);
  if (ujjak.size === 2){
    const [p1, p2] = [...ujjak.values()];
    csipes = Math.hypot(p1.x - p2.x, p1.y - p2.y); huzas = null; return;
  }
  huzas = {x: e.clientX, y: e.clientY, mozdult: false};
});
vaszon.addEventListener("pointermove", e => {
  if (!ujjak.has(e.pointerId)) return;
  ujjak.set(e.pointerId, {x: e.clientX, y: e.clientY});
  if (ujjak.size === 2 && csipes){
    const [p1, p2] = [...ujjak.values()];
    const d = Math.hypot(p1.x - p2.x, p1.y - p2.y);
    if (d > 1){ zoom(csipes / d); csipes = d; }
    return;
  }
  if (!huzas) return;
  const dx = e.clientX - huzas.x, dy = e.clientY - huzas.y;
  if (!huzas.mozdult && Math.hypot(dx, dy) < 4) return;
  huzas.mozdult = true; huzas.x = e.clientX; huzas.y = e.clientY;
  if (mod === "kering"){
    kering.theta -= dx * 0.006;
    kering.phi = clamp(kering.phi + dy * 0.006, 0.08, 1.5);
  } else if (mod === "jatekos"){
    jatekosNez.yaw -= dx * 0.004;
    jatekosNez.pitch = clamp(jatekosNez.pitch - dy * 0.004, -1.2, 1.2);
  } else {
    if (mod === "kovetes") modValt("szabad");  // aki húz, vezetni akar
    yaw -= dx * 0.004;
    pitch = clamp(pitch - dy * 0.004, -1.45, 1.45);
  }
});
function ujjFel(e){
  ujjak.delete(e.pointerId);
  if (ujjak.size < 2) csipes = null;
  const katt = huzas && !huzas.mozdult;
  huzas = null;
  if (!katt || fest.xr.isPresenting) return;
  // A dupla kattintás első fele ne mérjen: kicsit várunk.
  clearTimeout(kattIdozito);
  const cx = e.clientX, cy = e.clientY;
  kattIdozito = setTimeout(() => meresKattintas(cx, cy), 260);
}
vaszon.addEventListener("pointerup", ujjFel);
vaszon.addEventListener("pointercancel", e => { ujjak.delete(e.pointerId); huzas = null; csipes = null; });
vaszon.addEventListener("dblclick", e => {
  clearTimeout(kattIdozito);
  jatekosValasztas(e.clientX, e.clientY);
});
vaszon.addEventListener("wheel", e => {
  e.preventDefault();
  zoom(Math.exp(e.deltaY * 0.0012));
}, {passive: false});
function zoom(arany){
  // arany > 1: távolodás. Keringésben a sugár változik; szabad módban
  // előre/hátra ugrás a nézés irányában ("dash").
  if (mod === "kering"){ kering.r = clamp(kering.r * arany, 4, 80); return; }
  if (mod === "jatekos" || mod === "kovetes") return;
  const lep = -Math.log(arany) * 12;
  const irany = new THREE.Vector3();
  kamera.getWorldDirection(irany);
  rig.position.addScaledVector(irany, lep);
  rig.position.y = clamp(rig.position.y, 0.4, 60);
}

// Képernyő-pont → sugár a jelenetbe.
const sugar = new THREE.Raycaster();
const ndc = new THREE.Vector2();
function sugarBeallit(cx, cy){
  const r = vaszon.getBoundingClientRect();
  ndc.set(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1);
  sugar.setFromCamera(ndc, kamera);
}

// ---- Játékos-nézet: dupla kattintás egy figurára -------------------
function jatekosValasztas(cx, cy){
  if (fest.xr.isPresenting) return;
  sugarBeallit(cx, cy);
  const talalat = sugar.intersectObjects(babuk.filter(b => b.visible), true)[0];
  if (!talalat) return;
  let o = talalat.object;
  while (o && !babuk.includes(o)) o = o.parent;
  const k = babuk.indexOf(o);
  const a = allas.find(s => s.k === k);
  if (!a) return;
  jatekosNez.yaw = 0; jatekosNez.pitch = -0.05;
  modValt("jatekos");
  kovet = {hazai: a.hazai, mez: a.mez, x: a.x, y: a.y, irany: o.rotation.y, k};
  // A gomb megmondja, kinek a szemével nézünk (csapat + mezszám).
  jatekosKiGomb.textContent = (a.hazai ? ADAT.home : ADAT.away) +
    (a.mez ? " #" + a.mez : "") + " szemével ✕";
  if (!megy){ megy = true; lejatszasGomb.textContent = "⏸"; }
}
// A játékos megtett útja kockánként összegezve (méter): a mezszám a
// fogódzó (azonosító nélkül nincs út); a lépésenkénti ugrás-szűrő
// MÉTER-korlát (TAV_UGRAS_M), hogy a követés-ugrás ne számítson, a
// sűrű remegés viszont ne essen ki. Meccsenként egyszer, mezszámonként.
const TAV_UGRAS_M = 3;
const tavTablak = new Map();
function tavTabla(hazai, mez){
  const kulcs = (hazai ? "h" : "v") + mez;
  if (tavTablak.has(kulcs)) return tavTablak.get(kulcs);
  const t = new Float64Array(frames.length);
  const cs = hazai ? 1 : 0;
  let ex = null, ey = null, ossz = 0;
  for (let i = 0; i < frames.length; i++){
    const p = frames[i][1].find(q => q[0] === cs && q[5] === mez);
    if (p){
      if (ex !== null){
        const d = Math.hypot(p[1] - ex, p[2] - ey);
        if (d <= TAV_UGRAS_M) ossz += d;
      }
      ex = p[1]; ey = p[2];
    }
    t[i] = ossz;
  }
  tavTablak.set(kulcs, t);
  return t;
}
const jatekosHud = document.getElementById("jatekosHud");
function hudFrissit(cel){
  if (!kovet || !cel){ jatekosHud.style.display = "none"; return; }
  let s = (kovet.hazai ? ADAT.home : ADAT.away) + (kovet.mez ? " #" + kovet.mez : "") +
    " · " + szam1(cel.seb * 3.6) + " km/h";
  if (kovet.mez){
    const m = tavTabla(kovet.hazai, kovet.mez)[keres(ido)];
    s += " · " + (m >= 1000 ? (m/1000).toFixed(2).replace(".", ",") + " km" : Math.round(m) + " m") + " eddig";
  }
  jatekosHud.textContent = s; jatekosHud.style.display = "block";
}
// A követett ember megkeresése az új kockán: azonos mezszám (ha van),
// különben az előző helyéhez legközelebbi csapattárs 3 m-en belül —
// a követés-azonosítók töredezettek, a mezszám és a hely a fogódzó.
function kovetFrissit(dt){
  if (!kovet) return;
  let cel = null;
  if (kovet.mez){
    cel = allas.find(s => s.hazai === kovet.hazai && s.mez === kovet.mez) || null;
  }
  if (!cel){
    let legjobb = 3.0;
    for (const s of allas){
      if (s.hazai !== kovet.hazai) continue;
      const d = Math.hypot(s.x - kovet.x, s.y - kovet.y);
      if (d < legjobb){ legjobb = d; cel = s; }
    }
  }
  hudFrissit(cel);
  if (cel){
    kovet.x = cel.x; kovet.y = cel.y; kovet.k = cel.k;
    // Az irány simítva követi a figura haladását (a zajos követés ne
    // rángassa a fejet); a rövidebb íven fordul.
    const celIrany = babuk[cel.k].rotation.y;
    let d = celIrany - kovet.irany;
    while (d > Math.PI) d -= 2*Math.PI;
    while (d < -Math.PI) d += 2*Math.PI;
    kovet.irany += d * Math.min(1, dt * 3);
    // A saját testét nem látja (a kamera a fejében ül).
    babuk[cel.k].visible = false;
  }
  const fx = Math.sin(kovet.irany), fz = Math.cos(kovet.irany);
  rig.position.set(kovet.x + fx * 0.12, 1.62, (W - kovet.y) + fz * 0.12);
  if (!fest.xr.isPresenting){
    rig.rotation.y = kovet.irany + Math.PI + jatekosNez.yaw;
    kamera.rotation.set(jatekosNez.pitch, 0, 0);
  }
}

// ---- Lövés-mérés: katt a padlóra ----------------------------------
const meresElem = document.getElementById("meres");
const meresCsoport = new THREE.Group();
szinpad.add(meresCsoport);
const padloSik = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
function szam1(v){ return v.toFixed(1).replace(".", ","); }
function meresTorles(){
  while (meresCsoport.children.length) meresCsoport.remove(meresCsoport.children[0]);
  meresElem.style.display = "none";
}
function meresKattintas(cx, cy){
  sugarBeallit(cx, cy);
  if (lovesKattintas()) return;
  const pont = new THREE.Vector3();
  if (!sugar.ray.intersectPlane(padloSik, pont)) return;
  const x = pont.x, y = W - pont.z;
  if (x < -3 || x > H + 3 || y < -3 || y > W + 3) return;
  meresRajzol(x, y);
}
function meresRajzol(x, y, kapu){
  meresTorles();
  const m = lovesMeres(x, y, kapu);
  const v = (px, py, h) => new THREE.Vector3(px, h, W - py);
  const p = v(x, y, 0.02);
  const y1 = W/2 - KAPU_SZ/2, y2 = W/2 + KAPU_SZ/2;
  // A lövő-háromszög: a pontból a két kapufáig — ennyi kapu "látszik".
  const tri = new THREE.BufferGeometry().setFromPoints(
    [p, v(m.gx, y1, 0.02), v(m.gx, y2, 0.02)]);
  tri.setIndex([0, 1, 2]);
  meresCsoport.add(new THREE.Mesh(tri, new THREE.MeshBasicMaterial(
    {color:0x2f86d6, transparent:true, opacity:0.28, side:THREE.DoubleSide, depthWrite:false})));
  const vonalAnyag = new THREE.LineBasicMaterial({color:0x4c9aff});
  for (const cel of [v(m.gx, y1, 0.02), v(m.gx, y2, 0.02)]){
    meresCsoport.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([p, cel]), vonalAnyag));
  }
  const kozep = new THREE.Line(new THREE.BufferGeometry().setFromPoints(
    [p, v(m.gx, W/2, 0.02)]), new THREE.LineDashedMaterial({color:0xffffff, dashSize:0.25, gapSize:0.2}));
  kozep.computeLineDistances(); meresCsoport.add(kozep);
  const gyuru = new THREE.Mesh(new THREE.RingGeometry(0.22, 0.32, 24),
    new THREE.MeshBasicMaterial({color:0xffffff, side:THREE.DoubleSide}));
  gyuru.rotation.x = -Math.PI/2; gyuru.position.copy(p); meresCsoport.add(gyuru);
  meresElem.innerHTML = "<b>Lövés-mérés</b> (" + (m.kapu === "bal" ? "bal" : "jobb") +
    " kapu)<br>" + szam1(m.tav) + " m a kapu közepétől · kapufától " + szam1(m.kapufa) +
    " m<br>Kapu-szög: " + szam1(m.szog) + "° · sáv: " + m.sav +
    '<button id="meresKi" title="Törlés (Esc)">✕</button>';
  meresElem.style.display = "block";
  document.getElementById("meresKi").onclick = meresTorles;
}

// ---- Passzok: a futó passz vonala / a csapat passz-hálója -------------
// Élő: a passz kockájától PASSZ_S másodpercig vonal mellmagasságban az
// adótól a fogadóig (halványodva). Háló: a csapat minden passza vékony
// vonalként a padlón — a játékszervezés fő tengelyei látszanak.
const PASSZOK = ADAT.passes || [];
const PASSZ_S = 1.0;
const passzValaszto = document.getElementById("passz");
const passzInfo = document.getElementById("passzInfo");
const passzElo = new THREE.Group(), passzHalo = new THREE.Group();
szinpad.add(passzElo); szinpad.add(passzHalo);
let passzHaloNev = null;
function passzSzin(hazai){ return hazai ? 0x4c9aff : 0xff6b6b; }
function passzFrissit(t){
  const v = passzValaszto.value;
  while (passzElo.children.length) passzElo.remove(passzElo.children[0]);
  passzHalo.visible = v === "hazai" || v === "vendeg";
  if (!v){ passzInfo.textContent = ""; return; }
  if (v === "elo"){
    let db = 0;
    for (const [mp, hazai, x1, y1, x2, y2] of PASSZOK){
      if (mp > t || t - mp > PASSZ_S) continue;
      const g = new THREE.BufferGeometry().setFromPoints(
        [new THREE.Vector3(x1, 1.0, W - y1), new THREE.Vector3(x2, 1.0, W - y2)]);
      passzElo.add(new THREE.Line(g, new THREE.LineBasicMaterial(
        {color: passzSzin(hazai), transparent: true, opacity: 1 - (t - mp) / PASSZ_S})));
      db++;
    }
    passzInfo.textContent = db ? "passz úton" : "";
    return;
  }
  const hazai = v === "hazai" ? 1 : 0;
  if (passzHaloNev !== v){
    while (passzHalo.children.length) passzHalo.remove(passzHalo.children[0]);
    const pontok = [];
    for (const [mp, h, x1, y1, x2, y2] of PASSZOK){
      if (h !== hazai) continue;
      pontok.push(new THREE.Vector3(x1, 0.015, W - y1), new THREE.Vector3(x2, 0.015, W - y2));
    }
    if (pontok.length){
      passzHalo.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pontok),
        new THREE.LineBasicMaterial({color: passzSzin(hazai), transparent: true, opacity: 0.35})));
    }
    passzHaloNev = v;
    passzInfo.textContent = (pontok.length / 2) + " passz — " + (hazai ? ADAT.home : ADAT.away);
  }
}

// ---- Hőtérkép: hol tartózkodott a csapat a meccsen -------------------
// A pályára fektetett, áttetsző textúra: 20×10 cella (2 m), a cella
// erőssége a MÉRT helyek száma a legsűrűbb cellához képest (ugyanaz a
// rács, mint az elemzés hőtérképe). Egyszer számoljuk, a váltás csak
// újrafesti a vásznat.
const HO_X = 20, HO_Y = 10;
const hoValaszto = document.getElementById("hoter");
const hoVaszon = document.createElement("canvas"); hoVaszon.width = 400; hoVaszon.height = 200;
const hoTextura = new THREE.CanvasTexture(hoVaszon);
const hoSik = new THREE.Mesh(new THREE.PlaneGeometry(H, W),
  new THREE.MeshBasicMaterial({map: hoTextura, transparent: true, depthWrite: false}));
hoSik.rotation.x = -Math.PI/2; hoSik.position.set(H/2, 0.008, W/2); hoSik.visible = false;
szinpad.add(hoSik);
function hoRacs(hazai){
  const r = Array.from({length: HO_Y}, () => new Array(HO_X).fill(0));
  let max = 0;
  for (const f of frames) for (const p of f[1]){
    if (!!p[0] !== hazai || !p[3]) continue;
    const ix = Math.min(HO_X-1, Math.max(0, Math.floor(p[1] / H * HO_X)));
    const iy = Math.min(HO_Y-1, Math.max(0, Math.floor(p[2] / W * HO_Y)));
    r[iy][ix]++; if (r[iy][ix] > max) max = r[iy][ix];
  }
  return {r, max};
}
let hoRacsok = null;
function hoFest(){
  const v = hoValaszto.value;
  hoSik.visible = !!v;
  if (!v) return;
  if (!hoRacsok) hoRacsok = {hazai: hoRacs(true), vendeg: hoRacs(false)};
  const g = hoVaszon.getContext("2d");
  g.clearRect(0, 0, hoVaszon.width, hoVaszon.height);
  const cw = hoVaszon.width / HO_X, ch = hoVaszon.height / HO_Y;
  for (const [nev, rgb] of [["hazai", "76,154,255"], ["vendeg", "255,107,107"]]){
    if (v !== "mind" && v !== nev) continue;
    const {r, max} = hoRacsok[nev];
    if (!max) continue;
    for (let iy = 0; iy < HO_Y; iy++) for (let ix = 0; ix < HO_X; ix++){
      const e = r[iy][ix] / max;
      if (e <= 0) continue;
      // A textúra teteje a pálya y = W széle (a sík a three x/z-re fekszik).
      g.fillStyle = "rgba(" + rgb + "," + (0.1 + 0.65*e).toFixed(2) + ")";
      g.fillRect(ix*cw, (HO_Y-1-iy)*ch, cw, ch);
    }
  }
  hoTextura.needsUpdate = true;
}
hoValaszto.onchange = hoFest;

// ---- Kész kamera-állások (az appbeli 3D pálya gombjainak párja) ------
// Pálya-koordinátában (x, y, magasság, irány, dőlés) → a rig helye a
// three-térben (x, h, W − y); az irány előjele a tükrözés miatt fordul.
const NEZETEK = {
  lelato: [20, -12, 9, 0, -0.5],
  kapu:   [-6, 10, 2.5, Math.PI/2, -0.12],
  palya:  [20, 4, 1.7, 0, 0],
  madar:  [20, 10, 34, 0, -1.45],
};
function nezet(nev){
  const [x, y, h, irany, doles] = NEZETEK[nev];
  modValt("szabad");
  utolsoNezet = nev;
  rig.position.set(x, h, W - y);
  yaw = -irany; pitch = doles;
}
for (const b of document.querySelectorAll("button.nezet")) b.onclick = () => nezet(b.dataset.n);

// ---- Megosztható link: a mostani jelenet címként -----------------------
// ?t=349&nezet=madar&kamera=h7&hoter=mind&loves=mind&passz=hazai&fal=elo
// — az oldal nyitáskor visszaállítja (a t-t a lejátszó-indítás már
// kezeli). Az edző így EGY jelenetet küld, nem egy meccset.
const URL_PARAM = new URLSearchParams(location.search);
let utolsoNezet = null;
function linkEpit(){
  const q = new URLSearchParams();
  q.set("t", Math.round(ido));
  if (mod === "kovetes" && kovetKam) q.set("kamera", (kovetKam.hazai ? "h" : "v") + kovetKam.mez);
  else if (utolsoNezet && mod === "szabad") q.set("nezet", utolsoNezet);
  for (const [nev, el] of [["hoter", hoValaszto], ["loves", lovesValaszto],
                           ["passz", passzValaszto], ["fal", falValaszto]]){
    if (el.value) q.set(nev, el.value);
  }
  if (falOldal.value !== "auto") q.set("falOldal", falOldal.value);
  if (nyomKapcsolo.checked) q.set("nyom", "1");
  if (sebesseg !== 1) q.set("seb", String(sebesseg));
  return location.origin + location.pathname + "?" + q.toString();
}
const linkInfo = document.getElementById("linkInfo");
document.getElementById("linkGomb").onclick = async () => {
  const url = linkEpit();
  try { await navigator.clipboard.writeText(url); linkInfo.textContent = "másolva"; }
  catch (e) { linkInfo.textContent = url; }
  setTimeout(() => { linkInfo.textContent = ""; }, 4000);
};
function linkAlkalmaz(){
  const v = (k) => URL_PARAM.get(k) || "";
  for (const [nev, el] of [["hoter", hoValaszto], ["loves", lovesValaszto],
                           ["passz", passzValaszto], ["fal", falValaszto]]){
    if (v(nev) && [...el.options].some(o => o.value === v(nev))){ el.value = v(nev); el.onchange && el.onchange(); }
  }
  if (v("falOldal")) falOldal.value = v("falOldal");
  if (v("nyom") === "1") nyomKapcsolo.checked = true;
  if (v("seb")){ sebessegValaszto.value = v("seb"); sebessegValaszto.onchange(); }
  if (v("nezet") && NEZETEK[v("nezet")]) nezet(v("nezet"));
  if (v("kamera") && [...jatekosKameraValaszto.options].some(o => o.value === v("kamera"))){
    jatekosKameraValaszto.value = v("kamera"); jatekosKameraValaszto.onchange();
  }
}

// ---- Labda-nyom: a labda útja az utolsó NYOM_S másodpercben ----------
// Narancs vonal a labda-magasságban: a passz-sorozat és a lövés íve
// egyben látszik, nem csak a pillanatnyi hely.
const NYOM_S = 3;
const nyomKapcsolo = document.getElementById("nyom");
const nyomGeom = new THREE.BufferGeometry();
const nyomVonal = new THREE.Line(nyomGeom,
  new THREE.LineBasicMaterial({color:0xe8a33d, transparent:true, opacity:0.85}));
nyomVonal.visible = false;
szinpad.add(nyomVonal);
function nyomFrissit(t){
  if (!nyomKapcsolo.checked || !frames.length){ nyomVonal.visible = false; return; }
  const pontok = [];
  for (let i = keres(Math.max(0, t - NYOM_S)); i < frames.length && frames[i][0] <= t; i++){
    const l = frames[i][2];
    if (l) pontok.push(new THREE.Vector3(l[0], 0.45, W - l[1]));
  }
  if (pontok.length < 2){ nyomVonal.visible = false; return; }
  nyomGeom.setFromPoints(pontok);
  nyomVonal.visible = true;
}

// ---- Lövéstérkép: a meccs lövései a padlón --------------------------
// Egy lövés = egy kör a lövés helyén: a csapat színével, a sugara az
// xG-vel nő (nagy kör = nagy helyzet), a gólt arany gyűrű jelzi, a
// védett/kihagyott halványabb. Kattintás egy körre: odaugrik a
// jelenethez (4 mp-cel előtte, lejátszva) és kiírja a lövés számait.
const LOVESEK = ADAT.shots || [];
const lovesValaszto = document.getElementById("lovesek");
const lovesInfo = document.getElementById("lovesInfo");
const lovesCsoport = new THREE.Group();
szinpad.add(lovesCsoport);
const lovesJelek = [];
const aranyGyuruAnyag = new THREE.MeshBasicMaterial(
  {color:0xd9b544, side:THREE.DoubleSide, depthWrite:false});
for (const l of LOVESEK){
  const [mp, hazai, x, y, xg, kimenet] = l;
  const r = 0.22 + 0.5 * Math.min(1, Math.max(0, xg));
  const korong = new THREE.Mesh(new THREE.CircleGeometry(r, 20),
    new THREE.MeshBasicMaterial({color: hazai ? 0x4c9aff : 0xff6b6b,
      transparent:true, opacity: kimenet === "g" ? 0.9 : 0.45,
      side:THREE.DoubleSide, depthWrite:false}));
  korong.rotation.x = -Math.PI/2; korong.position.set(x, 0.018, W - y);
  korong.userData.loves = l;
  if (kimenet === "g"){
    const gyuru = new THREE.Mesh(new THREE.RingGeometry(r + 0.04, r + 0.12, 24), aranyGyuruAnyag);
    gyuru.rotation.x = -Math.PI/2; gyuru.position.set(x, 0.02, W - y);
    korong.userData.gyuru = gyuru; lovesCsoport.add(gyuru);
  }
  lovesCsoport.add(korong); lovesJelek.push(korong);
}
const KIMENET = {g: "gól", v: "védés", m: "mellé/kapufa"};
function lovesLatszik(l, t){
  const v = lovesValaszto.value;
  if (!v) return false;
  if (v === "eddig") return l[0] <= t;
  if (v === "hazai") return !!l[1];
  if (v === "vendeg") return !l[1];
  return true;
}
let lovesSzoveg = "";
function lovesFrissit(t){
  let db = 0, gol = 0;
  for (const j of lovesJelek){
    const lat = lovesLatszik(j.userData.loves, t);
    j.visible = lat; if (j.userData.gyuru) j.userData.gyuru.visible = lat;
    if (lat){ db++; if (j.userData.loves[5] === "g") gol++; }
  }
  const s = lovesValaszto.value
    ? (LOVESEK.length ? db + " lövés, " + gol + " gól — kék: " + ADAT.home + ", piros: " + ADAT.away
       : "Ehhez a meccshez nincs felismert lövés.")
    : "";
  if (s !== lovesSzoveg){ lovesSzoveg = s; lovesInfo.textContent = s; }
}
// Katt egy lövés-körre (a sugár már beállítva): ugrás + mérés-doboz a
// lövés helyén, a lövés számaival. Igaz, ha talált.
function lovesKattintas(){
  const lathato = lovesJelek.filter(j => j.visible);
  if (!lathato.length) return false;
  const t = sugar.intersectObjects(lathato, false)[0];
  if (!t) return false;
  const [mp, hazai, x, y, xg, kimenet, goalX] = t.object.userData.loves;
  ido = Math.max(0, mp - 4); megy = true; lejatszasGomb.textContent = "⏸";
  csuszka.value = ido;
  meresRajzol(x, y, goalX > H/2 ? "jobb" : "bal");
  const o = Math.floor(mp/60), s = Math.floor(mp%60);
  meresElem.insertAdjacentHTML("afterbegin",
    "<b>" + (hazai ? ADAT.home : ADAT.away) + " lövése</b> " + o + ":" +
    String(s).padStart(2, "0") + " · " + KIMENET[kimenet] + " · xG " +
    xg.toFixed(2).replace(".", ",") + "<br>");
  return true;
}

// ---- Védekezés-panel: tankönyvi fal vs a valódi -------------------
const falValaszto = document.getElementById("fal");
const falOldal = document.getElementById("falOldal");
const falInfo = document.getElementById("falInfo");
const FORMAK = ADAT.formations || {};
const FAL = ADAT.defence || [];
const falCsoport = new THREE.Group();
szinpad.add(falCsoport);
const falGyuruk = [];
for (let i = 0; i < 6; i++){
  const g = new THREE.Mesh(new THREE.RingGeometry(0.34, 0.46, 28),
    new THREE.MeshBasicMaterial({color:0xd9b544, transparent:true, opacity:0.8, side:THREE.DoubleSide}));
  g.rotation.x = -Math.PI/2; g.position.y = 0.025; g.visible = false;
  falCsoport.add(g); falGyuruk.push(g);
}
// Az élő fal: a legutóbbi idővonal-sor, ha 1,5 mp-nél nem régebbi.
function eloFal(t){
  let lo = 0, hi = FAL.length - 1, talalt = -1;
  while (lo <= hi){ const k = (lo + hi) >> 1; if (FAL[k][0] <= t){ talalt = k; lo = k + 1; } else hi = k - 1; }
  if (talalt < 0 || t - FAL[talalt][0] > 1.5) return null;
  const r = FAL[talalt];
  return {hazai: !!r[1], cimke: r[2], goalX: r[3]};
}
// Átlagos eltérés a sablontól: mohó párosítás (a legközelebbi pár előbb).
function elteres(vedok, pontok){
  const parok = [];
  vedok.forEach((v, i) => pontok.forEach((p, j) =>
    parok.push([Math.hypot(v[0] - p[0], v[1] - p[1]), i, j])));
  parok.sort((a, b) => a[0] - b[0]);
  const vi = new Set(), pj = new Set();
  let osszeg = 0, db = 0;
  for (const [d, i, j] of parok){
    if (vi.has(i) || pj.has(j)) continue;
    vi.add(i); pj.add(j); osszeg += d; db++;
  }
  return db ? osszeg / db : null;
}
let falSzoveg = "";
function falKiir(s){ if (s !== falSzoveg){ falSzoveg = s; falInfo.innerHTML = s; } }
function falFrissit(t){
  const valasztas = falValaszto.value;
  falGyuruk.forEach(g => g.visible = false);
  if (!valasztas){ falKiir(""); return; }
  const elo = eloFal(t);
  const nev = valasztas === "elo" ? (elo ? elo.cimke : null) : valasztas;
  let goalX = null;
  if (falOldal.value === "bal") goalX = 0;
  else if (falOldal.value === "jobb") goalX = H;
  else if (elo) goalX = elo.goalX;
  const csapat = elo ? (elo.hazai ? ADAT.home : ADAT.away) : null;
  const sorok = [];
  if (elo) sorok.push("Most: " + csapat + " védekezik — <b>" + elo.cimke + "</b>");
  else sorok.push("Most nincs szervezett támadás — a fal nem áll.");
  const sablon = nev ? FORMAK[nev] : null;
  if (sablon && goalX !== null){
    const jobb = goalX > H/2;
    const pontok = sablon.map(p => [jobb ? H - p[0] : p[0], p[1]]);
    pontok.forEach((p, i) => { falGyuruk[i].visible = true;
      falGyuruk[i].position.set(p[0], 0.025, W - p[1]); });
    sorok.push(nev + " sablon a " + (jobb ? "jobb" : "bal") + " kapu előtt (sárga körök)");
    // Eltérés a valódi faltól — csak ha épp az a kapu a védett.
    if (elo && elo.goalX === goalX){
      const vedok = allas.filter(s => s.hazai === elo.hazai && !s.kapus
        && Math.abs(s.x - goalX) > 2.0).map(s => [s.x, s.y]);
      if (vedok.length >= 4){
        const e = elteres(vedok, pontok);
        if (e !== null) sorok.push("Átlagos eltérés a tankönyvi faltól: " + szam1(e) + " m");
      }
    }
  } else if (valasztas === "elo" && elo){
    sorok.push("(ehhez a formához nincs tankönyvi sablon)");
  } else if (sablon && goalX === null){
    sorok.push("Válassz kaput, vagy várj egy szervezett támadásra.");
  }
  falKiir(sorok.join("<br>"));
}

function mozgas(dt){
  if (mod === "kering"){
    const cp = Math.cos(kering.phi);
    rig.position.set(CEL.x + Math.sin(kering.theta) * cp * kering.r,
                     CEL.y + Math.sin(kering.phi) * kering.r,
                     CEL.z + Math.cos(kering.theta) * cp * kering.r);
    if (!fest.xr.isPresenting){ rig.rotation.y = kering.theta; kamera.rotation.set(-kering.phi, 0, 0); }
    return;
  }
  if (mod === "jatekos" || mod === "kovetes") return;  // a kovet(es)Frissit viszi a kamerát
  const seb = (gombok.has("ShiftLeft")||gombok.has("ShiftRight")) ? 12 : 5;
  const ex = -Math.sin(yaw), ez = -Math.cos(yaw);
  const jx = Math.cos(yaw), jz = -Math.sin(yaw);
  if (gombok.has("KeyW")){ rig.position.x += ex*seb*dt; rig.position.z += ez*seb*dt; }
  if (gombok.has("KeyS")){ rig.position.x -= ex*seb*dt; rig.position.z -= ez*seb*dt; }
  if (gombok.has("KeyA")){ rig.position.x -= jx*seb*dt; rig.position.z -= jz*seb*dt; }
  if (gombok.has("KeyD")){ rig.position.x += jx*seb*dt; rig.position.z += jz*seb*dt; }
  if (gombok.has("KeyR")) rig.position.y += seb*dt;
  if (gombok.has("KeyF") || gombok.has("KeyC")) rig.position.y = Math.max(0.4, rig.position.y - seb*dt);
  if (!fest.xr.isPresenting){ kamera.rotation.set(pitch, 0, 0); rig.rotation.y = yaw; }
}
// VR-locomotion: a bal kar hüvelykujj-karja a nézés iránya szerint visz.
function vrMozgas(dt){
  const munkamenet = fest.xr.getSession && fest.xr.getSession();
  if (!munkamenet) return;
  for (const forras of munkamenet.inputSources){
    const gp = forras.gamepad;
    if (!gp || gp.axes.length < 4) continue;
    const ax = gp.axes[2], ay = gp.axes[3];
    if (Math.abs(ax) < 0.15 && Math.abs(ay) < 0.15) continue;
    const irany = new THREE.Vector3();
    kamera.getWorldDirection(irany); irany.y = 0; irany.normalize();
    const oldal = new THREE.Vector3().crossVectors(
      irany, new THREE.Vector3(0,1,0));
    rig.position.addScaledVector(irany, -ay * 3 * dt);
    rig.position.addScaledVector(oldal, ax * 3 * dt);
  }
}

const idoCimke = document.getElementById("ido");
linkAlkalmaz();
fest.setAnimationLoop(() => {
  const most = performance.now();
  const dt = Math.min(0.1, (most - utolso)/1000); utolso = most;
  if (megy){ ido = Math.min(veg, ido + dt * sebesseg);
    if (ido >= veg){ megy = false; lejatszasGomb.textContent = "▶"; }
    csuszka.value = ido; }
  mozgas(dt); vrMozgas(dt); rajzol(ido); kovetFrissit(dt); kovetesFrissit(dt); falFrissit(ido); lovesFrissit(ido); nyomFrissit(ido); passzFrissit(ido); felirat(ido);
  const o = Math.floor(ido/60), mp = Math.floor(ido%60);
  idoCimke.textContent = o + ":" + String(mp).padStart(2,"0");
  fest.render(szinpad, kamera);
});
</script></body></html>
"""
    return (oldal.replace("__CIM__", cim.replace("<", "&lt;"))
                 .replace("__LOVES_JS__", LOVES_MERES_JS)
                 .replace("__ADAT__", adat))
