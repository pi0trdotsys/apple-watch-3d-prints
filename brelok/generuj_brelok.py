# -*- coding: utf-8 -*-
"""
Brelok-ramka (bumper) na Apple Watch Series 4/5/6/SE 44 mm, z oczkiem na klucze.
Tył jest otwarty, więc krążek ładowarki przyczepia się bez wyjmowania zegarka.

Wymagania:  pip install -r ../requirements.txt   (manifold3d, trimesh, numpy, scipy)
Uruchom:    python generuj_brelok.py

Powstają pliki:
  stl/brelok_AW44_TPU.stl   - wersja zalecana (TPU 95A, elastyczna)
  stl/brelok_AW44_PETG.stl  - wersja sztywna (PETG), do przetestowania
  raport.json               - wymiary, masa i kontrola kolizji
  ../docs/dane_brelok.js    - dane interaktywnego podglądu 3D (docs/index.html)
Układ osi: X = szerokość (38), Y = wysokość (44, oczko u góry), Z = grubość (tył -> przód).
"""
import base64
import json
import math
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import CrossSection, JoinType, Manifold

OUT = Path(__file__).resolve().parent
STL = OUT / "stl"
DOCS = OUT.parent / "docs"
SEG = 24  # punktów na ćwiartkę łuku narożnika

# --------------------------------------------------------------------------
# ZEGAREK: Apple Watch Series 4/5/6/SE, 44 mm
# Pewne (dane Apple): 44 x 38 x 10,7 mm. Reszta to SZACUNKI - zmierz i popraw.
# --------------------------------------------------------------------------
W, H = 38.0, 44.0   # szerokość, wysokość koperty [mm]
R = 10.0            # promień narożnika koperty w widoku z przodu (szacunek)
T = 10.7            # grubość całkowita razem z wypukłością czujnika
DOME_H = 1.9        # wysokość wypukłości czujnika z tyłu (szacunek)
# Profil boku koperty: (z, wcięcie względem obrysu 38x44).
# z = 0 to wierzchołek czujnika, z = T to środek szkła.
PROFIL = [
    (1.9, 2.4), (2.3, 1.3), (2.9, 0.6), (3.7, 0.2), (4.8, 0.0), (6.5, 0.0),
    (7.8, 0.15), (8.8, 0.45), (9.5, 0.9), (10.1, 1.6), (10.5, 2.6), (10.7, 4.0),
]
KOPULA = [(0.0, 16.0), (0.6, 24.0), (1.2, 29.5), (1.9, 33.0)]  # (z, średnica) wypukłości czujnika
# Koronka i przycisk boczny (prawa strona, +X) - szacunki, tylko do podglądu/kontroli kolizji
KORONKA = dict(y=7.5, z=5.7, d=5.8, wystaje=2.6)
PRZYCISK = dict(y0=-14.5, y1=-2.5, z0=4.2, z1=7.2, wystaje=0.3)
# Krążek ładowarki Apple (ok. 27,7 mm średnicy)
KRAZEK = dict(d=27.7, h=7.0)

# --------------------------------------------------------------------------
# RAMKA - warianty
# --------------------------------------------------------------------------
WARIANTY = {
    "TPU": dict(
        luz=0.15,            # luz między zegarkiem a ramką
        scianka=1.8,         # grubość ścianki bocznej
        nad_szklem=0.6,      # o ile rant wystaje ponad szkło (ochrona przed kluczami)
        pod_plecami=1.2,     # grubość tylnego rantu pod krawędzią koperty
        zakladka_przod=1.6,  # o ile przedni rant zachodzi na kopertę (od obrysu 38x44)
        zakladka_tyl=2.2,    # o ile tylny rant zachodzi na kopertę
        gestosc=1.21,        # g/cm3 (do szacunku wagi)
    ),
    "PETG": dict(
        luz=0.25, scianka=1.5, nad_szklem=0.6, pod_plecami=1.2,
        zakladka_przod=1.6, zakladka_tyl=1.0, gestosc=1.27,
    ),
}
OKNO_Z = (DOME_H + 0.3, 9.4)       # wysokość okien bocznych (zostają cienkie ranty przód/tył)
OKNO_PRAWE_Y = (-16.5, 14.5)       # koronka + mikrofon + przycisk boczny
OKNO_LEWE_Y = (-10.0, 10.0)        # głośnik (słychać "Ping" z iPhone'a)
OKNO_FAZA = 0.6                   # fazka krawędzi okien od zewnątrz (łatwiejszy dostęp palcem)
OCZKO = dict(r=6.0, wysuniecie=4.5, otwor=5.5, grubosc=5.0, faza=0.6)


# --------------------------------------------------------------------------
def rrect_pts(w, h, r, z, n=SEG):
    """Punkty obrysu zaokrąglonego prostokąta (środek w 0,0) na wysokości z."""
    r = max(min(r, w / 2 - 1e-3, h / 2 - 1e-3), 0.05)
    cx, cy = w / 2 - r, h / 2 - r
    pts = []
    for sx, sy, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((sx * cx + r * math.cos(a), sy * cy + r * math.sin(a), z))
    return pts


def circle_pts(d, z, n=128):
    return [(d / 2 * math.cos(2 * math.pi * i / n), d / 2 * math.sin(2 * math.pi * i / n), z) for i in range(n)]


def hull(pts):
    return Manifold.hull_points(np.asarray(pts, dtype=np.float64))


def zegarek_korpus(luz=0.0):
    """Wypukła bryła koperty (bez koronki); luz > 0 daje ją powiększoną o luz."""
    pts = []
    for z, d in PROFIL:
        dd = d - luz
        pts += rrect_pts(W - 2 * dd, H - 2 * dd, R - dd, z)
    for z, dia in KOPULA:
        pts += circle_pts(dia + 2 * luz, z - (luz if z == 0 else 0))
    if luz > 0:
        z, d = PROFIL[-1]
        pts += rrect_pts(W - 2 * d, H - 2 * d, R - d, z + luz)
    return hull(pts)


def zegarek_pelny():
    body = zegarek_korpus()
    k = KORONKA
    crown = (Manifold.cylinder(k["wystaje"] + 1.0, k["d"] / 2, circular_segments=48)
             .rotate((0, 90, 0)).translate((W / 2 - 1.0, k["y"], k["z"])))
    p = PRZYCISK
    btn = Manifold.cube((p["wystaje"] + 0.8, p["y1"] - p["y0"], p["z1"] - p["z0"])).translate(
        (W / 2 - 0.8, p["y0"], p["z0"]))
    return body + crown + btn


def ladowarka():
    d, h = KRAZEK["d"], KRAZEK["h"]
    puck = Manifold.cylinder(h + 1.2, d / 2, circular_segments=96).translate((0, 0, -h))
    puck = puck - zegarek_korpus()  # wklęsłe gniazdo pod wypukłość czujnika
    cable = (Manifold.cylinder(30, 1.75, circular_segments=32)
             .rotate((90, 0, 0)).translate((0, -d / 2 + 1.0, -h / 2)))
    return puck + cable


def pryzma_x(x0, x1, y0, y1, z0, z1, r):
    """Prostopadłościan z zaokrąglonymi rogami w płaszczyźnie YZ, rozciągnięty wzdłuż X od x0 do x1."""
    cs = CrossSection.square((y1 - y0 - 2 * r, z1 - z0 - 2 * r)).translate((y0 + r, z0 + r))
    cs = cs.offset(r, JoinType.Round, circular_segments=32)
    # (u, v, w) -> (X = w + x0, Y = u, Z = v)
    return cs.extrude(x1 - x0).transform(
        np.array([[0, 0, 1, x0], [1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float64))


def okno_prawe(y0, y1, z0, z1, x_zew, r=2.0, faza=OKNO_FAZA):
    """Okno w prawej ściance (+X) z fazką od zewnątrz; lewe okno = lustro tej bryły."""
    rdzen = pryzma_x(W / 2 - 3.0, x_zew - faza, y0, y1, z0, z1, r)
    wylot = pryzma_x(x_zew, x_zew + 3.0, y0 - faza, y1 + faza, z0 - faza, z1 + faza, r + faza)
    return Manifold.batch_hull([rdzen, wylot])


def ramka(p):
    luz, t = p["luz"], p["scianka"]
    z_bot = DOME_H - p["pod_plecami"]
    z_top = T + p["nad_szklem"]
    Wo, Ho, Ro = W + 2 * (luz + t), H + 2 * (luz + t), R + luz + t

    # 1) skorupa zewnętrzna z zaokrąglonymi krawędziami
    eb, et, pts = 0.8, 1.2, []
    for i in range(9):
        th = math.pi / 2 * i / 8
        z, ins = z_bot + eb - eb * math.sin(th), eb - eb * math.cos(th)
        pts += rrect_pts(Wo - 2 * ins, Ho - 2 * ins, Ro - ins, z)
        z, ins = z_top - et + et * math.sin(th), et - et * math.cos(th)
        pts += rrect_pts(Wo - 2 * ins, Ho - 2 * ins, Ro - ins, z)
    body = hull(pts)

    # 2) oczko na kółko od kluczy (u góry, +Y), drukuje się bez podpór
    o = OCZKO
    yc = Ho / 2 + o["wysuniecie"]
    tab_cs = CrossSection.batch_hull([
        CrossSection.circle(o["r"], 64).translate((0, yc)),
        CrossSection.square((16.0, 2.0)).translate((-8.0, Ho / 2 - 3.0)),
    ])
    tab = Manifold.batch_hull([
        tab_cs.extrude(o["grubosc"] - o["faza"]).translate((0, 0, z_bot)),
        tab_cs.offset(-o["faza"], JoinType.Round).extrude(0.01).translate((0, 0, z_bot + o["grubosc"] - 0.01)),
    ])
    body = body + tab

    # 3) wnętrze = zegarek + luz
    body = body - zegarek_korpus(luz)

    # 4) okno z przodu (ekran) z fazką oraz okno z tyłu (czujnik + ładowarka)
    zp = p["zakladka_przod"]
    front = hull(
        rrect_pts(W - 2 * zp, H - 2 * zp, R - zp, T - 3.0)
        + rrect_pts(W - 2 * zp, H - 2 * zp, R - zp, z_top - 0.6)
        + rrect_pts(W - 2 * zp + 1.2, H - 2 * zp + 1.2, R - zp + 0.6, z_top + 0.01)
        + rrect_pts(W - 2 * zp + 1.2, H - 2 * zp + 1.2, R - zp + 0.6, z_top + 1.0))
    zt = p["zakladka_tyl"]
    back = hull(
        rrect_pts(W - 2 * zt + 1.0, H - 2 * zt + 1.0, R - zt + 0.5, z_bot - 1.0)
        + rrect_pts(W - 2 * zt + 1.0, H - 2 * zt + 1.0, R - zt + 0.5, z_bot - 0.01)
        + rrect_pts(W - 2 * zt, H - 2 * zt, R - zt, z_bot + 0.5)
        + rrect_pts(W - 2 * zt, H - 2 * zt, R - zt, DOME_H + 2.5))
    body = body - front - back

    # 5) okna boczne: prawe (koronka, mikrofon, przycisk), lewe (głośnik)
    body = body - okno_prawe(*OKNO_PRAWE_Y, *OKNO_Z, Wo / 2)
    body = body - okno_prawe(*OKNO_LEWE_Y, *OKNO_Z, Wo / 2).mirror((1, 0, 0))

    # 6) otwór w oczku z fazkami
    rr, f, zt2 = o["otwor"] / 2, 0.5, z_bot + o["grubosc"]
    hole = Manifold.cylinder(o["grubosc"] + 2, rr, circular_segments=64).translate((0, yc, z_bot - 1))
    hole = hole + Manifold.cylinder(f, rr + f, rr, circular_segments=64).translate((0, yc, z_bot - 0.001))
    hole = hole + Manifold.cylinder(f, rr, rr + f, circular_segments=64).translate((0, yc, zt2 - f + 0.001))
    body = body - hole
    return body, z_bot


def to_trimesh(m):
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3]
    f = np.asarray(mesh.tri_verts)
    return trimesh.Trimesh(vertices=v, faces=f, process=True)


def stl_b64(m):
    return base64.b64encode(to_trimesh(m).export(file_type="stl")).decode("ascii")


def overhang_area(tm, limit_deg=45.0, skip_below=0.05):
    """Pole powierzchni nawisów (> limit od pionu), z pominięciem spodu leżącego na stole."""
    n = tm.face_normals
    zc = tm.triangles_center[:, 2]
    zmin = tm.bounds[0, 2]
    mask = (n[:, 2] < -math.cos(math.radians(limit_deg))) & (zc > zmin + skip_below)
    return float(tm.area_faces[mask].sum())


def zapisz_podglad(model, czesci, raport):
    """Dane do docs/index.html: siatki w pozycji montażu (base64 STL) + raport."""
    DOCS.mkdir(exist_ok=True)
    dane = json.dumps({"raport": raport, "czesci": czesci}, ensure_ascii=False)
    (DOCS / f"dane_{model}.js").write_text(
        "window.MODELE = window.MODELE || {};\n" f"window.MODELE[{json.dumps(model)}] = {dane};\n", encoding="utf-8")


def main():
    zeg = zegarek_pelny()
    puck = ladowarka()
    STL.mkdir(exist_ok=True)
    raport, b64 = {}, {}
    for nazwa, p in WARIANTY.items():
        rm, z_bot = ramka(p)
        tm_print = to_trimesh(rm.translate((0, 0, -z_bot)))  # spód na stole: z = 0
        path = STL / f"brelok_AW44_{nazwa}.stl"
        tm_print.export(path)
        bb = tm_print.bounds
        raport[nazwa] = {
            "plik": path.name,
            "szczelny (watertight)": bool(tm_print.is_watertight),
            "rodzaj (genus)": int(rm.genus()),
            "wymiary [mm]": [round(float(x), 2) for x in (bb[1] - bb[0])],
            "objetosc [cm3]": round(rm.volume() / 1000, 2),
            "waga [g]": round(rm.volume() / 1000 * p["gestosc"], 1),
            "kolizja z zegarkiem [mm3]": round((rm ^ zeg).volume(), 3),
            "kolizja z ladowarka [mm3]": round((rm ^ puck).volume(), 3),
            "min. odstep od ladowarki [mm]": round(rm.min_gap(puck, 5.0), 2),
            "nawisy >45 st. [mm2]": round(overhang_area(tm_print), 1),
            "trojkaty": int(len(tm_print.faces)),
        }
        b64[nazwa] = stl_b64(rm)
    (OUT / "raport.json").write_text(json.dumps(raport, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(raport, ensure_ascii=False, indent=2))

    zapisz_podglad("brelok", {**b64, "zegarek": stl_b64(zeg), "ladowarka": stl_b64(puck)}, raport)
    print("Zapisano stl/, raport.json i docs/dane_brelok.js")


if __name__ == "__main__":
    main()
