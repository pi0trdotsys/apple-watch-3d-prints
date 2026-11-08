# -*- coding: utf-8 -*-
"""
Obudowa w stylu iPoda classic dla Apple Watch Series 4/5/6/SE 44 mm.

Wymagania:  pip install -r ../requirements.txt   (manifold3d, trimesh, numpy, scipy, matplotlib)
Uruchom:    python generuj_ipod.py

Powstają: stl/ (części ułożone do druku), raport.json (kontrola kolizji)
i ../docs/dane_ipod.js (dane interaktywnego podglądu 3D, docs/index.html).
Układ osi (montaż): środek zegarka w (0, 0); X w prawo (koronka), Y w górę,
Z od tyłu (czujnik, z = 0) do przodu (szkło, z = 10,7).
"""
import base64
import json
import math
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import CrossSection, FillRule, JoinType, Manifold
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath

OUT = Path(__file__).resolve().parent
STL = OUT / "stl"
DOCS = OUT.parent / "docs"
SEG = 24

# ============================================================================
# ZEGAREK: Apple Watch Series 4/5/6/SE 44 mm
# Pewne (Apple): 44 x 38 x 10,7 mm. Reszta to SZACUNKI - sprawdza je wydruk testowy.
# ============================================================================
W, H = 38.0, 44.0
R = 10.0                 # promień narożnika koperty (szacunek)
T = 10.7                 # grubość z wypukłością czujnika
DOME_H = 1.9             # wysokość wypukłości czujnika (szacunek)
PROFIL = [               # (z, wcięcie względem obrysu 38x44) - profil boku koperty
    (1.9, 2.4), (2.3, 1.3), (2.9, 0.6), (3.7, 0.2), (4.8, 0.0), (6.5, 0.0),
    (7.8, 0.15), (8.8, 0.45), (9.5, 0.9), (10.1, 1.6), (10.5, 2.6), (10.7, 4.0),
]
KOPULA = [(0.0, 16.0), (0.6, 24.0), (1.2, 29.5), (1.9, 33.0)]   # (z, średnica) wypukłości czujnika
KORONKA = dict(y=7.5, z=5.7, d=5.8, wystaje=2.6)                 # prawa strona (+X)
PRZYCISK = dict(y0=-14.5, y1=-2.5, z0=4.2, z1=7.2, wystaje=0.3)
KRAZEK = dict(d=27.7, h=7.0)                                      # ładowarka Apple

# ============================================================================
# OBUDOWA
# ============================================================================
CW, CH, CR = 61.8, 103.5, 9.0       # obrys jak iPod classic, promień narożników
Y_TOP = H / 2 + 8.0                 # górna krawędź (zegarek 8 mm od góry)
Y_BOT = Y_TOP - CH
CY = (Y_TOP + Y_BOT) / 2
Z_FRONT = T + 0.6                   # front 0,6 mm nad szkłem (ochrona ekranu)
Z_SPLIT = DOME_H                    # styk korpusu z klapką
Z_BACK = Z_SPLIT - 1.6              # tył klapki (klapka 1,6 mm)
LUZ = 0.2                           # luz kieszeni na zegarek
R_KIESZEN = 9.0                     # promień narożników kieszeni (zapas na promień zegarka)
ZAKLADKA = 1.6                      # rant nad szkłem; okno ekranu 34,8 x 40,8 mm
KOLKO = dict(y=Y_TOP - 77.5, d=38.0, d_kolnierz=42.0, d_srodek=15.0, gl_przod=3.0, luz=0.2)
OKNO_LADOWARKI = 33.0
WKRETY = [(24.0, 25.0), (-24.0, 25.0), (24.0, -67.0), (-24.0, -67.0)]   # M2x6 stożkowe
SPREZYNY_Y = (19.0, -19.0)          # dwie sprężynki w klapce dociskają zegarek do przodu
DOCISK = 0.5                        # ugięcie sprężynek przy szacowanych wymiarach
DEKOR = True                        # ozdobny suwak "hold", gniazdo słuchawek, złącze dock

# Przedłużka koronki: gniazdo z TPU nasuwane na koronkę + wałek, na końcu pokrętło
SREDNICE_KORONKI = (5.0, 5.4, 5.8, 6.2, 6.6)   # średnice koronki, pod które są gniazda (wydrukuj i wybierz)
PK = dict(gniazdo_x0=W / 2 + 0.6, gl=2.0, dno=1.0, scianka=0.9, wal=4.5, otwor=5.4,
          kieszen_x1=26.5, kieszen_r=4.6, pogl_d=9.0, pogl_gl=1.5,
          pokretlo_d=8.0, pokretlo_h=2.2, szczelina=0.8, wcisk=1.8)
# Popychacz przycisku bocznego
PP = dict(dl=10.0, wys=2.6, kol_dl=12.0, kol_wys=3.8, kol_gr=1.0, wystaje=0.6, skok=0.8, luz=0.15)
PP_Y = (PRZYCISK["y0"] + PRZYCISK["y1"]) / 2
PP_Z = (PRZYCISK["z0"] + PRZYCISK["z1"]) / 2


# ============================================================================
# Pomocnicze bryły
# ============================================================================
def rrect_pts(w, h, r, z, cx=0.0, cy=0.0, n=SEG):
    r = max(min(r, w / 2 - 1e-3, h / 2 - 1e-3), 0.05)
    ax, ay = w / 2 - r, h / 2 - r
    pts = []
    for sx, sy, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + sx * ax + r * math.cos(a), cy + sy * ay + r * math.sin(a), z))
    return pts


def circle_pts(d, z, n=128):
    return [(d / 2 * math.cos(2 * math.pi * i / n), d / 2 * math.sin(2 * math.pi * i / n), z) for i in range(n)]


def hull(pts):
    return Manifold.hull_points(np.asarray(pts, dtype=np.float64))


def prism(w, h, r, z0, z1, cx=0.0, cy=0.0):
    return hull(rrect_pts(w, h, r, z0, cx, cy) + rrect_pts(w, h, r, z1, cx, cy))


def box(x0, x1, y0, y1, z0, z1):
    return Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def cyl_z(d, z0, z1, cx=0.0, cy=0.0, n=96):
    return Manifold.cylinder(z1 - z0, d / 2, circular_segments=n).translate((cx, cy, z0))


def cone_z(d0, d1, z0, z1, cx=0.0, cy=0.0, n=96):
    return Manifold.cylinder(z1 - z0, d0 / 2, d1 / 2, circular_segments=n).translate((cx, cy, z0))


def cyl_x(d, x0, x1, y, z, n=64, d1=None):
    m = Manifold.cylinder(x1 - x0, d / 2, (d1 if d1 is not None else d) / 2, circular_segments=n)
    return m.rotate((0, 90, 0)).translate((x0, y, z))


def cyl_y(d, y0, y1, x, z, n=64):
    return Manifold.cylinder(y1 - y0, d / 2, circular_segments=n).rotate((-90, 0, 0)).translate((x, y0, z))


def kropla_x(d, x0, x1, y, z):
    """Otwór poziomy wzdłuż X z daszkiem 45° w stronę tyłu (-Z) - korpus drukuje się frontem w dół."""
    tip = cyl_x(0.05, x0, x1, y, z - d / 2 * math.sqrt(2), n=8)
    return Manifold.batch_hull([cyl_x(d, x0, x1, y, z), tip])


def kropla_y(d, y0, y1, x, z):
    tip = cyl_y(0.05, y0, y1, x, z - d / 2 * math.sqrt(2), n=8)
    return Manifold.batch_hull([cyl_y(d, y0, y1, x, z), tip])


def rbox_x(x0, x1, y0, y1, z0, z1, r):
    """Prostopadłościan z zaokrąglonymi krawędziami w płaszczyźnie YZ, wzdłuż X."""
    cs = CrossSection.square((y1 - y0 - 2 * r, z1 - z0 - 2 * r)).translate((y0 + r, z0 + r))
    cs = cs.offset(r, JoinType.Round, circular_segments=32)
    return cs.extrude(x1 - x0).transform(np.array([[0, 0, 1, x0], [1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float64))


def rbox_y(x0, x1, y0, y1, z0, z1, r):
    """Prostopadłościan z zaokrąglonymi krawędziami w płaszczyźnie XZ, wzdłuż Y."""
    cs = CrossSection.square((x1 - x0 - 2 * r, z1 - z0 - 2 * r)).translate((x0 + r, -z1 + r))
    cs = cs.offset(r, JoinType.Round, circular_segments=32)
    # (u, v, w) -> (X = u, Y = w + y0, Z = -v)  (obrót, wyznacznik +1)
    return cs.extrude(y1 - y0).transform(np.array([[1, 0, 0, 0], [0, 0, 1, y0], [0, -1, 0, 0]], dtype=np.float64))


def tekst(s, rozmiar):
    tp = TextPath((0, 0), s, size=rozmiar, prop=FontProperties(family="DejaVu Sans", weight="bold"))
    polys = [np.asarray(p, dtype=np.float64) for p in tp.to_polygons() if len(p) >= 3]
    cs = CrossSection(polys, FillRule.EvenOdd)
    x0, y0, x1, y1 = cs.bounds()
    return cs.translate((-(x0 + x1) / 2, -(y0 + y1) / 2))


def wielokat(pts):
    return CrossSection([np.asarray(pts, dtype=np.float64)], FillRule.EvenOdd)


# ============================================================================
# Zegarek i ładowarka (do kontroli kolizji i podglądu)
# ============================================================================
def zegarek_korpus(luz=0.0):
    """Koperta (wypukła) + osobno wypukłość czujnika - tył koperty wokół niej jest płaski."""
    pts = []
    for z, d in PROFIL:
        dd = d - luz
        pts += rrect_pts(W - 2 * dd, H - 2 * dd, R - dd, z)
    if luz > 0:
        z, d = PROFIL[-1]
        pts += rrect_pts(W - 2 * d, H - 2 * d, R - d, z + luz)
        z, d = PROFIL[0]
        pts += rrect_pts(W - 2 * d, H - 2 * d, R - d, z - luz)
    kopula = []
    for z, dia in KOPULA:
        kopula += circle_pts(dia + 2 * luz, z - (luz if z == 0 else 0))
    kopula += circle_pts(KOPULA[-1][1], KOPULA[-1][0] + 0.3)   # zakładka w kopertę (bez szczeliny)
    return hull(pts) + hull(kopula)


def zegarek_pelny():
    k, p = KORONKA, PRZYCISK
    crown = cyl_x(k["d"], W / 2 - 1.0, W / 2 + k["wystaje"], k["y"], k["z"], n=48)
    btn = box(W / 2 - 0.8, W / 2 + p["wystaje"], p["y0"], p["y1"], p["z0"], p["z1"])
    return zegarek_korpus() + crown + btn


def ladowarka():
    d, h = KRAZEK["d"], KRAZEK["h"]
    puck = cyl_z(d, -h, 1.2) - zegarek_korpus()
    cable = Manifold.cylinder(30, 1.75, circular_segments=32).rotate((90, 0, 0)).translate((0, -d / 2 + 1.0, -h / 2))
    return puck + cable


# ============================================================================
# Części obudowy
# ============================================================================
def obrys_zaokraglony(z0, z1, er, gora=True):
    """Bryła o obrysie obudowy z zaokrągloną krawędzią z przodu (gora=True) albo z tyłu.
    Ta ściana leży na stole przy druku, więc łuk kończy się fazką 45° (bez nawisu)."""
    pts = rrect_pts(CW, CH, CR, z0 if gora else z1, cy=CY)
    for i in range(6):
        th = math.pi / 4 * i / 5                      # łuk 0..45°
        ins = er - er * math.cos(th)
        dz = er - er * math.sin(th)
        pts += rrect_pts(CW - 2 * ins, CH - 2 * ins, CR - ins, (z1 - dz) if gora else (z0 + dz), cy=CY)
    ins = er * (2 - math.sqrt(2))                     # fazka 45° do samej ściany
    pts += rrect_pts(CW - 2 * ins, CH - 2 * ins, CR - ins, z1 if gora else z0, cy=CY)
    return hull(pts)


def wybranie_pokretla():
    k = KORONKA
    return cyl_x(PK["pogl_d"], CW / 2 - PK["pogl_gl"], CW / 2 + 1, k["y"], k["z"])


def korpus():
    body = obrys_zaokraglony(Z_SPLIT, Z_FRONT, 1.0, gora=True)

    # kieszeń: z przodu dopasowana do szkła, dalej prosto do tyłu (zegarek wkłada się od tyłu)
    kieszen = zegarek_korpus(LUZ) + prism(W + 2 * LUZ, H + 2 * LUZ, R_KIESZEN + LUZ, Z_BACK - 1, 8.8)
    zp = ZAKLADKA
    okno = hull(rrect_pts(W - 2 * zp, H - 2 * zp, R - zp, T - 3.0)
                + rrect_pts(W - 2 * zp, H - 2 * zp, R - zp, Z_FRONT - 0.6)
                + rrect_pts(W - 2 * zp + 1.2, H - 2 * zp + 1.2, R - zp + 0.6, Z_FRONT + 0.01)
                + rrect_pts(W - 2 * zp + 1.2, H - 2 * zp + 1.2, R - zp + 0.6, Z_FRONT + 1.0))
    body = body - kieszen - okno

    # kółko: otwór z przodu, stożkowy stopień 45° (bez podpór) i kołnierz do tyłu
    k = KOLKO
    z_step = Z_FRONT - k["gl_przod"]
    d_f, d_k = k["d"] + 2 * k["luz"], k["d_kolnierz"] + 2 * k["luz"]
    st = (d_k - d_f) / 2
    body = body - cyl_z(d_f, z_step - 0.01, Z_FRONT + 1, cy=k["y"])
    body = body - cone_z(d_k, d_f, z_step - st, z_step, cy=k["y"])
    body = body - cyl_z(d_k, Z_BACK - 1, z_step - st + 0.001, cy=k["y"])

    # przedłużka koronki: kieszeń otwarta od tyłu, otwór łożyskowy, wybranie pod pokrętło
    kc, rk = KORONKA, PK["kieszen_r"]
    x0 = W / 2 - 1.0
    kies = cyl_x(2 * rk, x0, PK["kieszen_x1"], kc["y"], kc["z"]) + \
        box(x0, PK["kieszen_x1"], kc["y"] - rk, kc["y"] + rk, Z_BACK - 1, kc["z"])
    body = body - kies - kropla_x(PK["otwor"], PK["kieszen_x1"] - 0.5, CW / 2 + 1, kc["y"], kc["z"])
    body = body - wybranie_pokretla()

    # popychacz przycisku bocznego: kieszeń na kołnierz (od tyłu) + szczelina w ściance
    x_in = W / 2 + PRZYCISK["wystaje"] + 0.05
    x_kol = x_in + PP["kol_gr"] + PP["skok"]
    body = body - box(x0, x_kol, PP_Y - PP["kol_dl"] / 2 - 0.2, PP_Y + PP["kol_dl"] / 2 + 0.2,
                      Z_BACK - 1, PP_Z + PP["kol_wys"] / 2 + 0.2)
    body = body - rbox_x(x_kol - 0.01, CW / 2 + 1, PP_Y - PP["dl"] / 2 - PP["luz"], PP_Y + PP["dl"] / 2 + PP["luz"],
                         PP_Z - PP["wys"] / 2 - PP["luz"], PP_Z + PP["wys"] / 2 + PP["luz"], 0.5)

    # mikrofon (między koronką a przyciskiem) i głośnik (lewy bok)
    body = body - rbox_x(x0, CW / 2 + 1, -1.4, 2.0, 5.1, 6.3, 0.55)
    for y in (-6.0, -3.0, 0.0, 3.0, 6.0):
        body = body - cyl_x(1.6, -CW / 2 - 1, -W / 2 + 1, y, 5.7, n=24)

    # otwory pod wkręty M2 (samogwintujące)
    for x, y in WKRETY:
        body = body - cyl_z(1.7, Z_BACK - 1, Z_SPLIT + 6.5, x, y, n=24)

    if DEKOR:
        zc = (Z_BACK + Z_FRONT) / 2
        # suwak "hold" (lewa strona góry) - ozdobny, zablokowany w pozycji "wyłączony"
        body = body - box(-22.5, -13.5, Y_TOP - 1.6, Y_TOP + 1, zc - 1.3, zc + 1.3)
        body = body + box(-22.0, -18.3, Y_TOP - 1.65, Y_TOP - 0.6, zc - 1.0, zc + 1.0)
        # gniazdo słuchawek (prawa strona góry) - ozdobne
        body = body - kropla_y(3.6, Y_TOP - 6.0, Y_TOP + 1, 18.0, zc)
        # złącze dock (dół) - ozdobne
        body = body - rbox_y(-10.5, 10.5, Y_BOT - 1, Y_BOT + 1.5, zc - 1.3, zc + 1.3, 1.2)
    return body


def klapka():
    k = obrys_zaokraglony(Z_BACK, Z_SPLIT, 1.4, gora=False)
    # okno ładowarki z fazką od zewnątrz
    k = k - cyl_z(OKNO_LADOWARKI, Z_BACK - 1, Z_SPLIT + 1)
    k = k - cone_z(OKNO_LADOWARKI + 1.2, OKNO_LADOWARKI, Z_BACK - 0.01, Z_BACK + 0.6)
    # wybranie pod zegarkiem (dociskają go tylko sprężynki) i pod gniazdem przedłużki
    k = k - prism(W + 2 * LUZ, H + 2 * LUZ, R_KIESZEN + LUZ, Z_SPLIT - 0.4, Z_SPLIT + 1)
    kc, rk = KORONKA, PK["kieszen_r"]
    k = k - box(W / 2 - 0.5, PK["kieszen_x1"], kc["y"] - rk, kc["y"] + rk, Z_SPLIT - 0.6, Z_SPLIT + 1)
    k = k - wybranie_pokretla()
    # wkręty M2 z gniazdem stożkowym 90°
    for x, y in WKRETY:
        k = k - cyl_z(2.3, Z_BACK - 1, Z_SPLIT + 1, x, y, n=32)
        k = k - cone_z(4.0, 2.3, Z_BACK - 0.01, Z_BACK + 0.85, x, y, n=32)
    # sprężynki: belka 12 mm w szczelinie U, z guzkiem dociskającym tył zegarka
    for yb in SPREZYNY_Y:
        slot = box(-6.0, 6.6, yb - 1.8, yb + 1.8, Z_BACK - 1, Z_SPLIT + 1) - \
            box(-6.2, 6.0, yb - 1.2, yb + 1.2, Z_BACK - 2, Z_SPLIT + 2)
        k = k - slot
        k = k + cone_z(2.4, 0.8, Z_SPLIT - 0.41, Z_SPLIT + DOCISK, 4.5, yb, n=32)
    return k


def kolko():
    k = KOLKO
    cy, s = k["y"], k["luz"]
    z_step = Z_FRONT - k["gl_przod"]
    rf, rkol = k["d"] / 2, k["d_kolnierz"] / 2
    zt = Z_FRONT - 0.05
    z_cone0 = z_step - (rkol - rf) + s
    w = cyl_z(k["d"], z_step + s - 0.001, zt, cy=cy)
    w = w + cone_z(2 * rkol, 2 * rf, z_cone0, z_step + s, cy=cy)
    w = w + (cyl_z(2 * rkol, Z_SPLIT + 0.1, z_cone0 + 0.001, cy=cy) - cyl_z(2 * (rkol - 3.0), Z_SPLIT, z_cone0 - 0.4, cy=cy))
    # rowek wokół przycisku środkowego
    rs = k["d_srodek"] / 2
    w = w - (cyl_z(2 * (rs + 0.75), zt - 0.6, zt + 1, cy=cy) - cyl_z(2 * rs, zt - 0.7, zt + 1.1, cy=cy))
    # napisy i ikony wgłębione 0,5 mm
    gl = 0.5
    rr = (rs + 0.75 + rf) / 2

    def wytnij(cs, x, y):
        return cs.extrude(gl + 1.0).translate((x, cy + y, zt - gl))

    w = w - wytnij(tekst("MENU", 3.6), 0, rr)
    nast = wielokat([(-3, -1.6), (0, 0), (-3, 1.6)]) + wielokat([(0, -1.6), (3, 0), (0, 1.6)]) + \
        CrossSection.square((0.6, 3.2)).translate((3.0, -1.6))
    w = w - wytnij(nast.translate((-0.3, 0)), rr, 0)
    w = w - wytnij(nast.mirror((1, 0)).translate((0.3, 0)), -rr, 0)
    graj = wielokat([(-3.2, -1.7), (-0.4, 0), (-3.2, 1.7)]) + CrossSection.square((0.8, 3.4)).translate((0.6, -1.7)) + \
        CrossSection.square((0.8, 3.4)).translate((2.2, -1.7))
    w = w - wytnij(graj, 0.3, -rr)
    return w


def przedluzka(d_kor):
    kc = KORONKA
    x0 = PK["gniazdo_x0"]
    id_ = d_kor - 0.15                      # lekki wcisk, TPU trzyma koronkę
    od = id_ + 2 * PK["scianka"]
    x_dno = x0 + PK["gl"]
    x_tyl = x_dno + PK["dno"]
    g = cyl_x(od, x0, x_tyl, kc["y"], kc["z"]) - cyl_x(id_, x0 - 1, x_dno, kc["y"], kc["z"])
    g = g - cyl_x(id_ + 0.6, x0 - 0.01, x0 + 0.3, kc["y"], kc["z"], d1=id_)
    x_end = CW / 2 - PK["pogl_gl"] + PK["szczelina"] + PK["wcisk"]
    wal = Manifold.batch_hull([cyl_x(PK["wal"], x_tyl - 0.01, x_end - 0.4, kc["y"], kc["z"]),
                               cyl_x(PK["wal"] - 0.8, x_end - 0.01, x_end, kc["y"], kc["z"])])
    return g + wal


def pokretlo():
    kc = KORONKA
    x_in = CW / 2 - PK["pogl_gl"] + PK["szczelina"]
    x_out = x_in + PK["pokretlo_h"]
    d = PK["pokretlo_d"]
    p = Manifold.batch_hull([cyl_x(d, x_in, x_out - 0.4, kc["y"], kc["z"]),
                             cyl_x(d - 0.8, x_out - 0.01, x_out, kc["y"], kc["z"])])
    p = p - cyl_x(PK["wal"] - 0.2, x_in - 0.01, x_in + PK["wcisk"], kc["y"], kc["z"])
    for i in range(24):  # radełko
        g = Manifold.cube((x_out - x_in + 1, 0.5, 0.8), center=True).translate((0, 0, d / 2))
        p = p - g.rotate((360 * i / 24, 0, 0)).translate(((x_in + x_out) / 2, kc["y"], kc["z"]))
    return p


def popychacz():
    x_in = W / 2 + PRZYCISK["wystaje"] + 0.05
    kol = rbox_x(x_in, x_in + PP["kol_gr"], PP_Y - PP["kol_dl"] / 2, PP_Y + PP["kol_dl"] / 2,
                 PP_Z - PP["kol_wys"] / 2, PP_Z + PP["kol_wys"] / 2, 0.5)
    bar = rbox_x(x_in + PP["kol_gr"] - 0.01, CW / 2 + PP["wystaje"], PP_Y - PP["dl"] / 2, PP_Y + PP["dl"] / 2,
                 PP_Z - PP["wys"] / 2, PP_Z + PP["wys"] / 2, 0.6)
    return kol + bar


# ============================================================================
# Eksport i kontrola
# ============================================================================
def to_trimesh(m):
    mesh = m.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3], faces=np.asarray(mesh.tri_verts), process=True)


def do_druku(m, obrot):
    """Obrót do pozycji druku i postawienie na stole (z = 0), środek w XY = 0."""
    if obrot == "przod_w_dol":
        m = m.rotate((0, 180, 0))
    elif obrot == "x_w_gore":
        m = m.rotate((0, -90, 0))
    elif obrot == "x_w_dol":
        m = m.rotate((0, 90, 0))
    lo, hi = m.bounding_box()[:3], m.bounding_box()[3:]
    return m.translate((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))


def b64(m):
    return base64.b64encode(to_trimesh(m).export(file_type="stl")).decode("ascii")


def kolizja(a, b):
    return round((a ^ b).volume(), 3)


def main():
    STL.mkdir(exist_ok=True)
    zeg, puck = zegarek_pelny(), ladowarka()
    czesci = {
        "korpus": (korpus(), "przod_w_dol", 1.24),
        "klapka": (klapka(), None, 1.24),
        "kolko": (kolko(), "przod_w_dol", 1.24),
        "popychacz": (popychacz(), "x_w_gore", 1.24),
        "pokretlo": (pokretlo(), "x_w_dol", 1.24),
    }
    for d in SREDNICE_KORONKI:
        czesci[f"przedluzka_{d:.1f}"] = (przedluzka(d), "x_w_gore", 1.21)
    czesci["test_rog"] = (czesci["korpus"][0] ^ box(6, 33, -20, Y_TOP + 1, -5, 15), "przod_w_dol", 1.24)

    raport = {"czesci": {}, "kontrola": {}}
    for nazwa, (m, obrot, gest) in czesci.items():
        tm = to_trimesh(do_druku(m, obrot))
        tm.export(STL / f"ipod_{nazwa}.stl")
        raport["czesci"][nazwa] = {
            "szczelny": bool(tm.is_watertight),
            "bryly": len(tm.split(only_watertight=False)),
            "wymiary [mm]": [round(float(v), 1) for v in tm.extents],
            "waga [g]": round(m.volume() / 1000 * gest, 1),
        }

    K = {n: czesci[n][0] for n in ("korpus", "klapka", "kolko", "popychacz", "pokretlo")}
    prz = czesci["przedluzka_5.8"][0]   # gniazdo pasujące do szacowanej koronki 5,8 mm
    kt = raport["kontrola"]
    kt["korpus/zegarek [mm3]"] = kolizja(K["korpus"], zeg)
    kt["korpus/klapka"] = kolizja(K["korpus"], K["klapka"])
    kt["korpus/kolko"] = kolizja(K["korpus"], K["kolko"])
    kt["korpus/popychacz"] = kolizja(K["korpus"], K["popychacz"])
    kt["korpus/przedluzka"] = kolizja(K["korpus"], prz)
    kt["korpus/pokretlo"] = kolizja(K["korpus"], K["pokretlo"])
    kt["klapka/kolko"] = kolizja(K["klapka"], K["kolko"])
    kt["klapka/przedluzka"] = kolizja(K["klapka"], prz)
    kt["klapka/pokretlo"] = kolizja(K["klapka"], K["pokretlo"])
    kt["klapka/ladowarka"] = kolizja(K["klapka"], puck)
    kt["korpus/ladowarka"] = kolizja(K["korpus"], puck)
    kt["popychacz/zegarek"] = kolizja(K["popychacz"], zeg)
    kt["docisk sprezynek (klapka/zegarek, oczekiwane > 0)"] = kolizja(K["klapka"], zeg)
    kt["wcisk gniazda na koronke 5.8 (oczekiwane > 0)"] = kolizja(prz, zeg)
    kt["odstep ladowarka-klapka [mm]"] = round(K["klapka"].min_gap(puck, 5.0), 2)
    kt["wymiary obudowy [mm]"] = [CW, CH, round(Z_FRONT - Z_BACK, 2)]

    (OUT / "raport.json").write_text(json.dumps(raport, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(raport, ensure_ascii=False, indent=2))

    dane = {n: b64(m) for n, m in K.items()}
    dane["przedluzka"] = b64(prz)
    dane["zegarek"] = b64(zeg)
    dane["ladowarka"] = b64(puck)
    DOCS.mkdir(exist_ok=True)
    js = json.dumps({"raport": raport, "czesci": dane}, ensure_ascii=False)
    (DOCS / "dane_ipod.js").write_text(
        "window.MODELE = window.MODELE || {};\n" f'window.MODELE["ipod"] = {js};\n', encoding="utf-8")
    print("Zapisano stl/, raport.json i docs/dane_ipod.js")


if __name__ == "__main__":
    main()
