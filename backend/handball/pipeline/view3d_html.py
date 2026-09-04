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


def _compact_data(match: Match) -> dict:
    """A követés tömör alakja: [[t_s, [[csapat,x,y],…], [bx,by]|0],…]."""
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    lepes = max(1, int(round(fps / VIEW3D_MAX_FPS)))
    frames = []
    for i in range(0, len(match.frames), lepes):
        f = match.frames[i]
        jatekosok = [
            [1 if p.team == Team.HOME else 0,
             round(p.x, 1), round(p.y, 1),
             1 if p.source == PositionSource.MEASURED else 0]
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
        esemenyek.sort(key=lambda x: x[0])
    except Exception:
        esemenyek = []  # esemény nélkül is működjön a nézet
    return {
        "home": match.meta.home_team,
        "away": match.meta.away_team,
        "frames": frames,
        "events": esemenyek,
    }


def view3d_html(match: Match) -> str:
    """A teljes, önálló HTML-oldal (three.js CDN-ről, adat beágyazva)."""
    adat = json.dumps(_compact_data(match), ensure_ascii=False,
                      separators=(",", ":"))
    cim = f"{match.meta.home_team} vs {match.meta.away_team} — 3D"
    # Nem f-string: a JS tele van kapcsos zárójellel; a beszúrás
    # helyőrző-cserével megy.
    oldal = """<!DOCTYPE html>
<html lang="hu"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
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
</style></head><body>
<div id="hud"><b>__CIM__</b></div>
<div id="sugo">Kattints a képre: egér-nézelődés (Esc kilép)<br>
WASD — mozgás · R/F — fel/le · Shift — gyors · Szóköz — lejátszás<br>
[ / ] — előző / következő esemény (gól, lövés, eladás)<br>
VR-headsetben: a lenti "ENTER VR" gomb</div>
<div id="felirat"></div>
<div id="vez">
 <button id="elozo" title="Előző esemény">⏮</button>
 <button id="lejatszas">▶</button>
 <button id="kov" title="Következő esemény">⏭</button>
 <input type="range" id="csuszka" min="0" max="0" step="0.01" value="0">
 <span id="ido">0:00</span>
</div>
<script type="importmap">{"imports":{
 "three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
 "three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
}}</script>
<script type="module">
import * as THREE from "three";
import {VRButton} from "three/addons/webxr/VRButton.js";

const ADAT = __ADAT__;
const H = 40, W = 20;

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
const talaj = new THREE.Mesh(
  new THREE.PlaneGeometry(H+8, W+8),
  new THREE.MeshBasicMaterial({color:0x101820}));
talaj.rotation.x = -Math.PI/2; talaj.position.set(H/2, -0.01, W/2);
szinpad.add(talaj);
const vonalSzin = new THREE.LineBasicMaterial({color:0x9fb6c6});
function vonal(pontok){
  const g = new THREE.BufferGeometry().setFromPoints(
    pontok.map(p => new THREE.Vector3(p[0], 0.01, W - p[1])));
  szinpad.add(new THREE.Line(g, vonalSzin));
}
vonal([[0,0],[H,0],[H,W],[0,W],[0,0]]);
vonal([[H/2,0],[H/2,W]]);
// Szabálykönyv-hű kapuelőtér: negyedkör az alsó kapufa körül →
// egyenes a kapu előtt → negyedkör a felső kapufa körül.
function kapuElo(bal, r){
  const cx = bal ? 0 : H, also = W/2-1.5, felso = W/2+1.5;
  const ut = [];
  for (let a=-90; a<=0; a+=6){
    const rad = a*Math.PI/180;
    ut.push([cx + (bal?1:-1)*Math.cos(rad)*r, also + Math.sin(rad)*r]);
  }
  for (let a=0; a<=90; a+=6){
    const rad = a*Math.PI/180;
    ut.push([cx + (bal?1:-1)*Math.cos(rad)*r, felso + Math.sin(rad)*r]);
  }
  vonal(ut);
}
kapuElo(true, 6); kapuElo(false, 6);
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

// Játékos-bábuk készlete (újrahasznosítva képkockánként).
const hazaiAnyag = new THREE.MeshBasicMaterial({color:0x2f86d6});
const vendegAnyag = new THREE.MeshBasicMaterial({color:0xd65a4a});
const babuk = [];
function babu(){
  const test = new THREE.Mesh(
    new THREE.CylinderGeometry(0.22, 0.22, 1.5, 8), hazaiAnyag);
  const csoport = new THREE.Group();
  test.position.y = 0.9; csoport.add(test);
  const fej = new THREE.Mesh(new THREE.SphereGeometry(0.16, 8, 8),
    hazaiAnyag);
  fej.position.y = 1.78; csoport.add(fej);
  szinpad.add(csoport);
  babuk.push(csoport);
  return csoport;
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
// Esemény-ugrás (⏮/⏭ és [ / ]): a jelenet előtt 4 mp-cel, lejátszva —
// mint az appból érkezve. Egy másodpercnyi holt sáv, hogy az épp nézett
// esemény ne "ragadjon". A felirat a jelenet közben mondja, mi történik.
const ESEM = ADAT.events || [];
const NEV = {g: "GÓL", s: "Lövés", t: "Labdaeladás"};
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
function rajzol(t){
  if (!frames.length) return;
  const i = keres(t), a = frames[i],
        b = frames[Math.min(i+1, frames.length-1)];
  const ar = b[0] > a[0] ? (t - a[0]) / (b[0] - a[0]) : 0;
  const jat = a[1];
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
    const anyag = p[0] ? hazaiAnyag : vendegAnyag;
    cs.children.forEach(gy => gy.material = anyag);
    cs.children.forEach(gy => gy.material.opacity = 1);
    if (!p[3]){ /* becsült: halványítás helyett kisebb bábu */ }
  }
  let l = a[2];
  if (l){
    const l2 = b[2] || l;
    labda.visible = true;
    labda.position.set(l[0] + (l2[0]-l[0])*ar, 0.5, W - (l[1] + (l2[1]-l[1])*ar));
  } else labda.visible = false;
}

// Asztali irányítás: pointer-lock nézelődés + WASD.
let yaw = 0, pitch = 0;
const gombok = new Set();
addEventListener("keydown", e => {
  if (e.code === "Space"){ lejatszasGomb.onclick(); e.preventDefault(); return; }
  if (e.code === "BracketLeft"){ esemenyUgras(-1); return; }
  if (e.code === "BracketRight"){ esemenyUgras(1); return; }
  gombok.add(e.code);
});
addEventListener("keyup", e => gombok.delete(e.code));
fest.domElement.addEventListener("click", () => {
  if (!fest.xr.isPresenting) fest.domElement.requestPointerLock();
});
addEventListener("mousemove", e => {
  if (document.pointerLockElement !== fest.domElement) return;
  yaw -= e.movementX * 0.0025;
  pitch = Math.max(-1.45, Math.min(1.45, pitch - e.movementY * 0.0025));
});
function mozgas(dt){
  const seb = (gombok.has("ShiftLeft")||gombok.has("ShiftRight")) ? 12 : 5;
  const ex = -Math.sin(yaw), ez = -Math.cos(yaw);
  const jx = Math.cos(yaw), jz = -Math.sin(yaw);
  if (gombok.has("KeyW")){ rig.position.x += ex*seb*dt; rig.position.z += ez*seb*dt; }
  if (gombok.has("KeyS")){ rig.position.x -= ex*seb*dt; rig.position.z -= ez*seb*dt; }
  if (gombok.has("KeyA")){ rig.position.x -= jx*seb*dt; rig.position.z -= jz*seb*dt; }
  if (gombok.has("KeyD")){ rig.position.x += jx*seb*dt; rig.position.z += jz*seb*dt; }
  if (gombok.has("KeyR")) rig.position.y += seb*dt;
  if (gombok.has("KeyF")) rig.position.y = Math.max(0.4, rig.position.y - seb*dt);
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
fest.setAnimationLoop(() => {
  const most = performance.now();
  const dt = Math.min(0.1, (most - utolso)/1000); utolso = most;
  if (megy){ ido = Math.min(veg, ido + dt);
    if (ido >= veg){ megy = false; lejatszasGomb.textContent = "▶"; }
    csuszka.value = ido; }
  mozgas(dt); vrMozgas(dt); rajzol(ido); felirat(ido);
  const o = Math.floor(ido/60), mp = Math.floor(ido%60);
  idoCimke.textContent = o + ":" + String(mp).padStart(2,"0");
  fest.render(szinpad, kamera);
});
</script></body></html>
"""
    return (oldal.replace("__CIM__", cim.replace("<", "&lt;"))
                 .replace("__ADAT__", adat))
