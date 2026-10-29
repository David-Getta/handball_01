# three.js 0.160.0 (a 3D/VR oldalhoz)

A böngészős 3D pálya (`handball/pipeline/view3d_html.py`) a three.js-t a
MOTORBÓL tölti (`/vendor/three@0.160.0/...`, `handball/api/app.py`), nem
CDN-ről — így a közös nézés internet nélkül is megy (edzőterem,
klub-hálózat), és a csomagolt kiadás is viszi (`packaging/backend.spec`).

Csak a két használt fájl van itt, változatlanul a hivatalos npm-csomagból
(`three-0.160.0.tgz`; a tarball sha512-je egyezik a npm regiszter
`dist.integrity`-jével):

| fájl | sha256 |
|---|---|
| `build/three.module.js` | `76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495` |
| `examples/jsm/webxr/VRButton.js` | `8ed40aedce76a40992a28980af9adf98543ce4233ea5649781245929a8fa052d` |

Licenc: MIT (`LICENSE`). Verzióváltáskor a fájlokat, a hash-eket (itt és
a `tests/test_three_helyben.py`-ban), a motor útját és az oldal import-
térképét együtt kell cserélni.
