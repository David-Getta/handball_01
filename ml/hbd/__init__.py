"""hbd — kézilabda-mozdulatfelismerés valódi videóból (UNIRI-HBD adathalmaz).

Ez a csomag SZÁNDÉKOSAN független a `backend/handball` szabályrétegeitől:
itt a gép tanul felvételekből, nem kézzel írt küszöbökből ítél. A kimenete
(testpont-sorozat, mozdulat-osztály, lövés-profil) később a backend
"gondolkodó" rétegeinek bemenete lesz.

Modulok:
    dataset     — az adathalmaz bejárása (klip → jelenet → kategória)
    video       — képkockák olvasása ffmpeg-gel (OpenCV-dekóder nélkül)
    locate      — a kivágott klip megkeresése a teljes jelenetben
    pose        — testpont-kinyerés előtanított YOLO-pose modellel (CLI)
    features    — testpont-normalizálás, sorozat, klip-szintű jellemzők
    goalkeeper  — kapus-szempontú lövés-profil (kartartás, lövőkar, felugrás)
    models      — kis időbeli konvolúciós háló (torch)
    train       — keresztvalidált kiértékelés + végső modellek (CLI)

Adatforrás: UNIRI-HBD, Ivašić-Kos, M., Pobar, M., University of Rijeka,
DOI 10.21227/0g0a-fe06, CC BY 4.0.
"""

__version__ = "0.1.0"
