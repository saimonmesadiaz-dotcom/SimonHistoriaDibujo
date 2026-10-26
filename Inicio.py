import base64
import html
import io
import os
import random

import numpy as np
import streamlit as st
from openai import OpenAI
from PIL import Image, ImageFilter
from streamlit_drawable_canvas import st_canvas

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
TINTA = "#0F2B5B"  # azul oscuro de todas las letras (alto contraste)
SEL = "#E8912D"    # marco naranja de lo seleccionado

# Casillas de pigmento: 0-8 forman la paleta (la 4 es el botón "+"), 9-14 son extras
SLOTS = [
    ("Azul", "#1F5BC4"),
    ("Rojo carmín", "#E0393E"),
    ("Verde", "#3E9E5F"),
    ("Amarillo", "#F5C02A"),
    None,
    ("Naranja", "#F28A2E"),
    ("Rosa", "#EE7FAE"),
    ("Morado", "#7B4FB8"),
    ("Negro", "#26211F"),
    ("Turquesa", "#1FB5C5"),
    ("Celeste", "#6EC6F2"),
    ("Lima", "#A5C93B"),
    ("Café", "#8A5530"),
    ("Burdeos", "#8E1F3D"),
    ("Blanco tiza", "#FFFFFF"),
]
IDX_PERSONALIZADO = 4

GROSORES = [("Muy fino", 2), ("Fino", 5), ("Medio", 10), ("Grueso", 18), ("Brocha", 32)]

HERRAMIENTAS = {"Pincel libre": "freedraw", "Rectángulo": "rect", "Círculo": "circle"}
ETIQUETA_HERRAMIENTA = ["Pincel", "Cuadro", "Círculo"]

PAPELES = ["Liso", "Rayado", "Cuadros", "Puntos"]
COLORES_PAPEL = [
    ("Hueso", "#EDE5D1"),
    ("Crema", "#FCF8EC"),
    ("Blanco", "#FFFFFF"),
    ("Kraft", "#E5D2AC"),
]
MESAS = [("Nogal claro", "#C99A62"), ("Roble", "#D9B27C"), ("Cerezo", "#A8683F")]
ACABADOS = ["Acuarela", "Tiza"]

# Formatos del cuaderno: (nombre, ancho, alto) del lienzo en píxeles
FORMATOS = [
    ("Panorámico", 900, 360),
    ("Clásico", 780, 500),
    ("Compacto", 640, 440),
    ("Cuadrado", 580, 580),
    ("Vertical", 480, 680),
    ("Alto", 360, 740),
]

st.set_page_config(
    page_title="Taller de arte",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------
for clave, valor in {
    "lienzo": 0,
    "nota": "",
    "historia": "",
    "vista": None,
    "pig": 0,
    "gro": 2,
    "tool": 0,
    "papel": 1,
    "papel_color": 0,
    "mesa": 0,
    "acabado": 0,
    "custom_hex": "#E873A5",
    "lienzo_ancho": 780,
    "lienzo_alto": 500,
}.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor


def elegir(clave, valor):
    st.session_state[clave] = valor


def aplicar_formato(ancho, alto):
    st.session_state.lienzo_ancho = ancho
    st.session_state.lienzo_alto = alto


def boton(etiqueta, **kw):
    """Botón que ocupa todo el ancho de su columna (según la versión de Streamlit)."""
    try:
        return st.button(etiqueta, width="stretch", **kw)
    except TypeError:
        return st.button(etiqueta, use_container_width=True, **kw)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def mini(texto):
    """Colapsa espacios y saltos de línea para que Markdown no rompa el HTML."""
    return " ".join(texto.split())


def hex_a_rgb(hex_):
    hex_ = hex_.lstrip("#")
    return tuple(int(hex_[i:i + 2], 16) for i in (0, 2, 4))


def mezcla(hex_, destino, t):
    r, g, b = hex_a_rgb(hex_)
    return "#%02x%02x%02x" % (
        int(r + (destino[0] - r) * t),
        int(g + (destino[1] - g) * t),
        int(b + (destino[2] - b) * t),
    )


def imagen_del_lienzo(datos, papel):
    img = Image.fromarray(np.array(datos).astype("uint8"), "RGBA")
    fondo = Image.new("RGBA", img.size, tuple(papel) + (255,))
    fondo.alpha_composite(img)
    return fondo.convert("RGB")


def lienzo_en_blanco(img, papel):
    dif = np.abs(np.array(img).astype(int) - np.array(papel)).max(axis=2)
    return (dif > 12).sum() < 30


def a_base64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _desenfocar(a, radio):
    im = Image.fromarray(a.astype("uint8")).filter(ImageFilter.GaussianBlur(radio))
    return np.array(im).astype(np.float32)


def _ruido_suave(h, w, celda, rng):
    g = rng.random((h // celda + 2, w // celda + 2)).astype(np.float32)
    g = Image.fromarray((g * 255).astype("uint8")).resize((w, h), Image.BICUBIC)
    return np.array(g).astype(np.float32) / 255


def acuarela(img, papel):
    """Lavado suave, borde de pigmento y grano de papel."""
    arr = np.array(img.convert("RGB")).astype(np.float32)
    h, w, _ = arr.shape
    papel_arr = np.array(papel, dtype=np.float32)
    carga = np.clip(papel_arr - arr, 0, 255)

    lavado = _desenfocar(carga, 2.4)
    borde = np.clip(_desenfocar(carga, 1.0) - _desenfocar(carga, 6.0), 0, 255)

    rng = np.random.default_rng(7)
    grano = (0.78 + 0.44 * _ruido_suave(h, w, 6, rng))[..., None]
    total = (lavado * 0.95 + borde * 0.55) * grano
    fibra = rng.normal(0, 2.2, (h, w, 1)).astype(np.float32)
    return Image.fromarray(np.clip(papel_arr - total + fibra, 0, 255).astype("uint8"))


def tiza(img, papel):
    """Trazo seco y granulado, como tiza sobre papel."""
    arr = np.array(img.convert("RGB")).astype(np.float32)
    h, w, _ = arr.shape
    papel_arr = np.array(papel, dtype=np.float32)
    carga = np.clip(papel_arr - arr, 0, 255)

    suave = _desenfocar(carga, 1.1)
    rng = np.random.default_rng(11)
    fino = np.clip((rng.random((h, w, 1)).astype(np.float32) - 0.25) / 0.55, 0, 1)
    veta = (0.75 + 0.5 * _ruido_suave(h, w, 3, rng))[..., None]
    total = suave * (0.35 + 0.65 * fino) * veta
    return Image.fromarray(np.clip(papel_arr - total, 0, 255).astype("uint8"))


def libreta(titulo, texto):
    cuerpo = html.escape(texto).replace("\n", "<br>")
    return mini(
        f'<div class="libreta"><div class="libreta-titulo">{html.escape(titulo)}</div>'
        f'<div class="libreta-texto">{cuerpo}</div></div>'
    )


# ---------------------------------------------------------------------------
# Ilustraciones de la mesa (SVG planos usados como fondo, repartidos por todo el espacio)
# ---------------------------------------------------------------------------
def uri(svg):
    datos = base64.b64encode(mini(svg).encode("utf-8")).decode("ascii")
    return f'url("data:image/svg+xml;base64,{datos}")'


def envolver(w, h, interior):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{interior}</svg>'


def salpicadura(cx, cy, color, brazos, grosor=20, r=24, gotas=()):
    lineas = "".join(f'<path d="M{cx} {cy} L{cx + dx} {cy + dy}"/>' for dx, dy in brazos)
    puntos = "".join(f'<circle cx="{x}" cy="{y}" r="{rr}"/>' for x, y, rr in gotas)
    return (
        f'<g fill="{color}" stroke="{color}" stroke-width="{grosor}" stroke-linecap="round">'
        f'{lineas}<circle cx="{cx}" cy="{cy}" r="{r}" stroke="none"/>'
        f'<g stroke="none">{puntos}</g></g>'
    )


def chincheta(x, y, rot, color):
    oscuro = mezcla(color, (0, 0, 0), 0.25)
    return (
        f'<g transform="translate({x} {y}) rotate({rot})">'
        '<path d="M0 44 L0 104" stroke="#9AA0A8" stroke-width="4" stroke-linecap="round"/>'
        f'<rect x="-9" y="14" width="18" height="30" rx="5" fill="{oscuro}"/>'
        f'<ellipse cx="0" cy="44" rx="23" ry="7" fill="{color}"/>'
        f'<rect x="-15" y="-30" width="30" height="50" rx="13" fill="{color}"/>'
        f'<ellipse cx="0" cy="-30" rx="27" ry="9" fill="{color}"/>'
        '<rect x="-9" y="-22" width="5" height="34" rx="2.5" fill="#fff" opacity=".35"/>'
        '</g>'
    )


def tubo(x, y, rot, color, escala=1.0):
    return (
        f'<g transform="translate({x} {y}) rotate({rot}) scale({escala})">'
        '<path d="M-26 -70 L26 -70 L36 42 L-36 42Z" fill="#DDD9E0" stroke="#BDB8C6" stroke-width="2"/>'
        f'<path d="M-31 -12 L31 -12 L36 42 L-36 42Z" fill="{color}"/>'
        '<path d="M-26 -70 L26 -70 L26 -90 L-26 -90Z" fill="#CFCAD8"/>'
        '<path d="M-22 -80 H22 M-22 -86 H22" stroke="#B3AEC0" stroke-width="2"/>'
        '<rect x="-13" y="42" width="26" height="20" rx="5" fill="#EDEAF0"/>'
        f'<rect x="-7" y="62" width="14" height="10" rx="3" fill="{color}"/>'
        f'<ellipse cx="0" cy="78" rx="10" ry="8" fill="{color}"/>'
        '<path d="M-18 -60 L-22 30" stroke="#fff" stroke-width="5" opacity=".35" stroke-linecap="round"/>'
        '</g>'
    )


def _libros():
    datos = [("#6A4FA8", 22, 252, 238), ("#F28C28", 10, 214, 250), ("#3E9E5F", 20, 176, 240),
             ("#F5C02A", 8, 138, 246), ("#1F5BC4", 16, 100, 236)]
    piezas = ""
    for color, ox, y, w in datos:
        piezas += (
            f'<rect x="{ox}" y="{y}" width="{w}" height="36" rx="4" fill="{color}"/>'
            f'<rect x="{ox + w - 18}" y="{y + 3}" width="18" height="30" fill="#FBF3DD"/>'
            f'<rect x="{ox + 14}" y="{y + 6}" width="8" height="24" fill="#fff" opacity=".28"/>'
        )
    return piezas


def _aro_tiza(cy):
    return (
        '<defs><filter id="t"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" result="n"/>'
        '<feDisplacementMap in="SourceGraphic" in2="n" scale="6"/></filter></defs>'
        '<g filter="url(#t)" fill="none">'
        f'<circle cx="260" cy="{cy}" r="150" stroke="#5CC6DC" stroke-width="16"/>'
        f'<circle cx="260" cy="{cy}" r="124" stroke="#F4E27A" stroke-width="24"/>'
        f'<circle cx="260" cy="{cy}" r="96" stroke="#F4A9C8" stroke-width="22"/>'
        '</g>'
    )


def _frasco():
    pinceles = ""
    for ang, mango, cerda in [(-24, "#0F2B5B", "#7B4FB8"), (-8, "#E0393E", "#F5C02A"),
                              (9, "#8A5530", "#1F5BC4"), (25, "#F5C02A", "#E0393E")]:
        pinceles += (
            f'<g transform="translate(85 205) rotate({ang})">'
            f'<rect x="-4" y="-120" width="8" height="150" rx="3" fill="{mango}"/>'
            '<rect x="-5.5" y="-152" width="11" height="34" rx="2" fill="#C9D0DA"/>'
            f'<path d="M-5.5 -152 C-8 -184 8 -184 5.5 -152Z" fill="{cerda}"/>'
            '</g>'
        )
    return (
        pinceles
        + '<path d="M34 150 L136 150 L130 252 Q85 262 40 252Z" fill="#D5EAF6" fill-opacity=".85" stroke="#8DB8D4" stroke-width="3"/>'
        + '<ellipse cx="85" cy="150" rx="51" ry="9" fill="#E8F4FB" stroke="#8DB8D4" stroke-width="3"/>'
        + '<path d="M48 170 L52 240" stroke="#fff" stroke-width="6" opacity=".6" stroke-linecap="round"/>'
    )


SVG_TIZA_ARRIBA = envolver(520, 140, _aro_tiza(-12))
SVG_TIZA_ABAJO = envolver(520, 140, _aro_tiza(152))
SVG_CHINCHETAS = envolver(
    230, 190,
    chincheta(46, 40, -30, "#F5C02A") + chincheta(124, 30, -8, "#4DA3F0") + chincheta(92, 66, 24, "#E8381F"),
)
SVG_SPLAT_MORADO = envolver(
    200, 150,
    salpicadura(100, 76, "#6A4FA8", [(-56, -30), (-62, 18), (48, -34), (58, 26), (4, 52), (-6, -52)], 14, 22,
                [(34, 26, 6), (168, 100, 6), (172, 38, 5), (124, 130, 6)]),
)
SVG_SPLAT_AMARILLO = envolver(
    150, 150,
    salpicadura(75, 75, "#FDB92D", [(-38, -32), (32, -44), (46, 20), (-32, 36), (4, 50)], 16, 20,
                [(18, 40, 6), (130, 100, 6), (110, 134, 5)]),
)
SVG_SPLAT_NARANJA = envolver(
    150, 150,
    salpicadura(75, 75, "#F28A2E", [(-34, -30), (34, -34), (40, 26), (-30, 34)], 15, 18,
                [(20, 120, 6), (130, 30, 6)]),
)
SVG_SPLAT_VERDE = envolver(
    260, 120,
    '<path d="M0 120 C10 84 62 76 88 56 C112 24 176 30 192 74 C228 80 256 100 250 120Z" fill="#7FBC7B"/>',
)
SVG_TUBOS_ESQUINA = envolver(
    300, 230, tubo(100, 100, -40, "#F5C02A", 1.0) + tubo(205, 82, 30, "#3EAF5C", 0.95)
)
SVG_TUBOS_BAJOS = envolver(
    250, 260, tubo(80, 112, -15, "#E0393E", 1.0) + tubo(165, 142, 38, "#F06AA0", 0.95)
)
SVG_CRAYONES = envolver(
    260, 330,
    '<g transform="translate(150 190) rotate(-60)">'
    + "".join(
        f'<g><rect x="{-84 + k * 25}" y="-82" width="19" height="62" fill="{c}"/>'
        f'<path d="M{-84 + k * 25} -82 L{-65 + k * 25} -82 L{-74.5 + k * 25} -106Z" fill="{c}"/></g>'
        for k, c in enumerate(["#E0393E", "#F28A2E", "#3E9E5F", "#2F78D8", "#7B4FB8", "#6B4A2B", "#26211F"])
    )
    + '<rect x="-100" y="-34" width="200" height="96" rx="8" fill="#F9C23C"/>'
    '<rect x="-100" y="-4" width="200" height="9" fill="#1D1D1D"/>'
    '<rect x="-100" y="14" width="200" height="5" fill="#1D1D1D"/>'
    '<circle cx="70" cy="40" r="9" fill="#E0393E"/>'
    '<rect x="-100" y="-34" width="200" height="18" rx="8" fill="#FBD36B"/>'
    '</g>',
)
SVG_LIBROS = envolver(
    340, 290,
    _libros()
    + '<g transform="translate(0 -16)">'
    '<ellipse cx="136" cy="118" rx="46" ry="7" fill="#000" opacity=".18"/>'
    '<path d="M136 52 C100 38 82 70 92 100 C102 126 124 122 136 118 C148 122 170 126 180 100 C190 70 172 38 136 52Z" fill="#E0393E"/>'
    '<path d="M136 52 C136 36 144 26 158 22 C158 38 150 48 136 52Z" fill="#3E9E5F"/>'
    '<ellipse cx="116" cy="70" rx="7" ry="13" fill="#fff" opacity=".4" transform="rotate(18 116 70)"/>'
    '</g>',
)
SVG_FRASCO = envolver(170, 270, _frasco())
_CLIP = "M32 44 V104 a15 15 0 0 0 30 0 V32 a23 23 0 0 0 -46 0 V96"
SVG_CLIP = envolver(
    90, 150,
    '<g transform="rotate(18 45 75)">'
    f'<path d="{_CLIP}" fill="none" stroke="#6F7C93" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>'
    f'<path d="{_CLIP}" fill="none" stroke="#D5DCE8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" transform="translate(-1 -1)"/>'
    '</g>',
)
SVG_PINCEL = envolver(
    290, 80,
    '<g transform="translate(8 46) rotate(-9)">'
    '<rect x="0" y="-6" width="190" height="12" rx="6" fill="#8A5530"/>'
    '<rect x="6" y="-3" width="150" height="3" rx="1.5" fill="#fff" opacity=".25"/>'
    '<rect x="186" y="-9" width="44" height="18" rx="3" fill="#C9D0DA"/>'
    '<path d="M194 -9 V9 M204 -9 V9" stroke="#9AA3B2" stroke-width="2"/>'
    '<path d="M230 -9 C256 -12 270 -3 276 0 C270 3 256 12 230 9Z" fill="#E0393E"/>'
    '</g>',
)

# Anillas de la espiral del cuaderno: lomo vertical (hoja apaisada) y horizontal (hoja vertical)
ANILLAS = uri(
    '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="32" viewBox="0 0 64 32">'
    '<circle cx="9" cy="16" r="3.6" fill="#2A1C10" opacity=".6"/>'
    '<circle cx="55" cy="16" r="3.6" fill="#2A1C10" opacity=".6"/>'
    '<g transform="rotate(-8 32 16)">'
    '<ellipse cx="32" cy="16" rx="28" ry="5.5" fill="none" stroke="#6F7885" stroke-width="3.4"/>'
    '<ellipse cx="32" cy="14.8" rx="28" ry="5.5" fill="none" stroke="#EEF1F6" stroke-width="1.3"/>'
    '</g></svg>'
)
ANILLAS_H = uri(
    '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="64" viewBox="0 0 32 64">'
    '<circle cx="16" cy="9" r="3.6" fill="#2A1C10" opacity=".6"/>'
    '<circle cx="16" cy="55" r="3.6" fill="#2A1C10" opacity=".6"/>'
    '<g transform="rotate(8 16 32)">'
    '<ellipse cx="16" cy="32" rx="5.5" ry="28" fill="none" stroke="#6F7885" stroke-width="3.4"/>'
    '<ellipse cx="14.8" cy="32" rx="5.5" ry="28" fill="none" stroke="#EEF1F6" stroke-width="1.3"/>'
    '</g></svg>'
)


def svg_madera(base):
    """Mesa de madera: tablones con tonos distintos, juntas oscuras, vetas largas y nudos."""
    azar = random.Random(5)
    oscuro = mezcla(base, (70, 38, 14), 0.6)
    junta = mezcla(base, (50, 28, 10), 0.7)
    W, H, N = 800, 480, 5
    alto = H // N
    piezas = ""
    for p in range(N):
        y0 = p * alto
        tono = mezcla(base, (255, 235, 200), 0.10) if p % 2 else mezcla(base, (90, 50, 20), 0.10)
        if p % 3 == 2:
            tono = mezcla(base, (255, 255, 255), 0.03)
        piezas += f'<rect x="0" y="{y0}" width="{W}" height="{alto}" fill="{tono}"/>'
        for _ in range(9):
            y = y0 + azar.randint(8, alto - 8)
            a, b = azar.randint(-7, 7), azar.randint(-7, 7)
            piezas += (
                f'<path d="M0 {y} C{W * .25:.0f} {y + a},{W * .5:.0f} {y - b},{W * .75:.0f} {y + b} S{W} {y},{W} {y}" '
                f'stroke="{oscuro}" stroke-width="{azar.choice([1, 1.5, 2, 3])}" '
                f'stroke-opacity="{azar.choice([.18, .28, .4])}" fill="none" stroke-linecap="round"/>'
            )
        if p in (1, 3):
            cx, cy = azar.randint(140, 660), y0 + alto // 2
            for k, (rx, ry) in enumerate([(26, 11), (18, 7), (10, 4)]):
                piezas += (
                    f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="none" stroke="{oscuro}" '
                    f'stroke-width="2" stroke-opacity="{.5 - k * .1}"/>'
                )
        piezas += f'<rect x="0" y="{y0}" width="{W}" height="3" fill="{junta}" opacity=".75"/>'
        piezas += f'<rect x="0" y="{y0 + 3}" width="{W}" height="2" fill="#fff" opacity=".10"/>'
        # juntas verticales entre tablas (desfasadas por tablón)
        jx = (p * 263 + 90) % W
        piezas += f'<rect x="{jx}" y="{y0}" width="3" height="{alto}" fill="{junta}" opacity=".6"/>'
    return envolver(W, H, piezas)


def _x(p):
    """Posición horizontal dentro del espacio de trabajo (a la derecha de la barra lateral).
    --sb-w vale 0 cuando la barra se oculta, así los adornos se reparten por toda la pantalla."""
    return f"calc(var(--sb-w,0px) + (100% - var(--sb-w,0px)) * {p})"


@st.cache_data(show_spinner=False)
def css_fondo(mesa_hex):
    # (ilustración, posición, tamaño). Tamaños parecidos entre sí (7-21vh).
    capas = [
        # borde superior
        (SVG_CHINCHETAS, f"{_x(.02)} 2vh", "auto 15vh"),
        (SVG_CLIP, f"{_x(.27)} 1vh", "auto 12vh"),
        (SVG_SPLAT_AMARILLO, f"{_x(.50)} 1vh", "auto 10vh"),
        (SVG_TIZA_ARRIBA, f"{_x(.70)} 0", "auto 9vh"),
        # borde derecho
        (SVG_TUBOS_ESQUINA, "100% 0", "auto 19vh"),
        (SVG_CRAYONES, "100% 36%", "auto 21vh"),
        (SVG_PINCEL, "100% 57%", "auto 7vh"),
        (SVG_TUBOS_BAJOS, "100% 73%", "auto 14vh"),
        (SVG_LIBROS, "100% 100%", "auto 20vh"),
        # borde izquierdo del espacio de trabajo
        (SVG_SPLAT_MORADO, f"{_x(0)} 22%", "auto 10vh"),
        (SVG_FRASCO, f"{_x(0)} 42%", "auto 19vh"),
        (SVG_PINCEL, f"{_x(0)} 66%", "auto 7vh"),
        (SVG_TUBOS_ESQUINA, f"{_x(.01)} 84%", "auto 14vh"),
        # borde inferior
        (SVG_SPLAT_VERDE, f"{_x(.20)} 100%", "auto 9vh"),
        (SVG_CLIP, f"{_x(.36)} 99%", "auto 11vh"),
        (SVG_TIZA_ABAJO, f"{_x(.52)} 100%", "auto 9vh"),
        (SVG_SPLAT_NARANJA, f"{_x(.74)} 99%", "auto 10vh"),
    ]
    imagenes = [uri(c[0]) for c in capas] + [uri(svg_madera(mesa_hex))]
    repeticion = ["no-repeat"] * len(capas) + ["repeat"]
    posiciones = [c[1] for c in capas] + ["0 0"]
    tamanos = [c[2] for c in capas] + ["800px 480px"]
    return (
        "<style>.stApp{"
        f"background-color:{mesa_hex};"
        f"background-image:{','.join(imagenes)};"
        f"background-repeat:{','.join(repeticion)};"
        f"background-position:{','.join(posiciones)};"
        f"background-size:{','.join(tamanos)};"
        "background-attachment:fixed;}</style>"
    )


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------
def css_dinamico(pig_hex):
    reglas = []
    papel_hex = COLORES_PAPEL[st.session_state.papel_color][1]

    # Gotas de pintura (cada una con su color)
    for i, slot in enumerate(SLOTS):
        if slot is None:
            continue
        hex_ = slot[1]
        claro = mezcla(hex_, (255, 255, 255), 0.5)
        oscuro = mezcla(hex_, (0, 0, 0), 0.28)
        reglas.append(
            f".st-key-pig_{i} button{{background:radial-gradient(circle at 36% 30%, {claro} 0%, {hex_} 52%, {oscuro} 100%) !important;}}"
        )

    # Trazos de muestra con el color elegido (efecto tiza)
    for i, px in enumerate([3, 6, 10, 15, 22]):
        reglas.append(
            f".st-key-gro_{i} button::after{{width:{px}px;"
            "background:repeating-linear-gradient(72deg, rgba(255,255,255,.30) 0 2px, transparent 2px 5px), "
            f"{pig_hex};}}"
        )

    # Muestras de disposición del papel
    reglas.append(".st-key-pap_0 button{background:#FFFDF5 !important;}")
    reglas.append(
        ".st-key-pap_1 button{background:repeating-linear-gradient(to bottom, transparent 0 9px, rgba(15,43,91,.4) 9px 10px), #FFFDF5 !important;}"
    )
    reglas.append(
        ".st-key-pap_2 button{background:linear-gradient(rgba(15,43,91,.34) 1px, transparent 1px) 0 0 / 12px 12px, "
        "linear-gradient(90deg, rgba(15,43,91,.34) 1px, transparent 1px) 0 0 / 12px 12px, #FFFDF5 !important;}"
    )
    reglas.append(
        ".st-key-pap_3 button{background:radial-gradient(circle, rgba(15,43,91,.62) 1.4px, transparent 1.8px) 0 0 / 11px 11px, #FFFDF5 !important;}"
    )
    for i, (_, hex_) in enumerate(COLORES_PAPEL):
        reglas.append(f".st-key-pcol_{i} button{{background:{hex_} !important;}}")
    for i, (_, hex_) in enumerate(MESAS):
        reglas.append(f".st-key-mesa_{i} button{{background:{hex_} !important;}}")

    # Páginas del cuaderno: color y trama elegidos
    tramas = [
        "none",
        "repeating-linear-gradient(to bottom, transparent 0, transparent 35px, rgba(15,43,91,.22) 35px, rgba(15,43,91,.22) 36px)",
        "linear-gradient(rgba(15,43,91,.14) 1px, transparent 1px), linear-gradient(90deg, rgba(15,43,91,.14) 1px, transparent 1px)",
        "radial-gradient(circle, rgba(15,43,91,.34) 1.6px, transparent 2px)",
    ]
    tamanos = ["auto", "auto", "30px 30px", "28px 28px"]
    reglas.append(
        f".st-key-paginas{{background-color:{papel_hex};"
        f"background-image:{tramas[st.session_state.papel]};"
        f"background-size:{tamanos[st.session_state.papel]};}}"
        f".st-key-paginas::before{{background-image:{ANILLAS};}}"
    )

    # Selecciones actuales
    sel_pig = st.session_state.pig
    giro = "" if sel_pig == IDX_PERSONALIZADO else "rotate(-45deg) "
    reglas.append(
        f".st-key-pig_{sel_pig} button{{"
        f"box-shadow:0 0 0 3px #FFF6DD, 0 0 0 6px {SEL}, 0 6px 8px rgba(0,0,0,.3) !important;"
        f"transform:{giro}scale(1.1) !important;}}"
    )
    reglas.append(
        f".st-key-gro_{st.session_state.gro} button{{"
        f"background:#FFF1D2 !important;border:3px solid {SEL} !important;}}"
    )
    reglas.append(
        f".st-key-tool_{st.session_state.tool} button, .st-key-fin_{st.session_state.acabado} button{{"
        f"background:{TINTA} !important;}}"
        f".st-key-tool_{st.session_state.tool} button p, .st-key-fin_{st.session_state.acabado} button p{{color:#FFF6DD !important;}}"
    )
    reglas.append(
        f".st-key-pap_{st.session_state.papel} button, "
        f".st-key-pcol_{st.session_state.papel_color} button, "
        f".st-key-mesa_{st.session_state.mesa} button{{"
        f"border:3px solid {SEL} !important;"
        f"box-shadow:0 0 0 3px #FFF6DD, 0 0 0 5px {SEL} !important;}}"
    )
    # Formato del cuaderno: miniatura proporcional en cada botón
    ancho_l, alto_l = st.session_state.lienzo_ancho, st.session_state.lienzo_alto
    for k, (_, fw, fh) in enumerate(FORMATOS):
        esc = 46 / max(fw, fh)
        reglas.append(
            f".st-key-fmt_{k} button::before{{width:{fw * esc:.0f}px;height:{fh * esc:.0f}px;}}"
        )
        if (fw, fh) == (ancho_l, alto_l):
            reglas.append(
                f".st-key-fmt_{k} button{{border:3px solid {SEL} !important;"
                f"box-shadow:0 0 0 3px #FFF6DD, 0 0 0 5px {SEL} !important;}}"
            )

    # Hoja vertical: la espiral pasa arriba, como en un bloc de notas
    if alto_l > ancho_l * 1.05:
        reglas.append(
            ".st-key-paginas::before{top:-32px;bottom:auto;left:-6px;right:-6px;width:auto;height:64px;"
            f"background-image:{ANILLAS_H};background-repeat:repeat-x;background-size:32px 64px;}}"
            ".st-key-paginas::after{background:linear-gradient(180deg,"
            "rgba(0,0,0,0) 0%, rgba(0,0,0,.06) 38%, rgba(0,0,0,.14) 48.4%,"
            "rgba(0,0,0,.30) 50%, rgba(0,0,0,.14) 51.6%, rgba(0,0,0,.06) 62%, rgba(0,0,0,0) 100%);}"
        )
    return "<style>" + "\n".join(reglas) + "</style>"


CSS_BASE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,700;1,500;1,700&family=Lora:ital,wght@0,400;0,600;1,400;1,600&display=swap');

:root{
  --tinta:#0F2B5B;
  --tarjeta:#FFF6DD;
  --borde:#E4CC93;
  --sel:#E8912D;
}

html, .stApp{color-scheme:light;}
[data-testid="stAppViewContainer"], [data-testid="stMain"], .main{background:transparent !important;}
.stApp, .stApp p, .stApp label, .stApp li,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stCaptionContainer"]{
  font-family:'Lora',Georgia,serif;
  color:var(--tinta);
}
.stApp label p{font-weight:600;}
[data-testid="stHeader"]{background:transparent;}
.block-container{max-width:100%;padding:6.5rem 2.5rem 7rem;}

/* ---------- Barra lateral: ancha, casi hasta el centro ---------- */
.stApp{--sb-w:0px;}
@media (min-width: 900px){
  .stApp{--sb-w:clamp(460px, 44vw, 820px);}
  [data-testid="stSidebar"]:not([aria-expanded="false"]){
    width:var(--sb-w) !important;
    min-width:var(--sb-w) !important;
    max-width:var(--sb-w) !important;
  }
  [data-testid="stSidebar"]:not([aria-expanded="false"]) > div{width:100% !important;}
}
/* Con la barra oculta, los adornos del fondo se reparten por toda la pantalla */
.stApp:has([data-testid="stSidebar"][aria-expanded="false"]){--sb-w:0px !important;}

[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#FCEFC9,#F7E2A8);
  border-right:2px solid rgba(160,110,40,.4);
}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{padding:1.2rem clamp(1rem,2.2vw,2rem) 3rem;}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"]{gap:1.8rem;}
[data-testid="stSidebar"] label, [data-testid="stSidebar"] p{color:var(--tinta);}

[class*="st-key-panel_"]{
  background:linear-gradient(180deg,#FFF9E8,#FFF3D2);
  border:2px solid var(--borde);
  border-radius:26px;
  padding:clamp(18px,2vw,30px);
  box-shadow:0 10px 16px -8px rgba(110,70,20,.5), inset 0 2px 0 #fff;
}
[class*="st-key-panel_"] [data-testid="stVerticalBlock"]{gap:1.3rem;}

.panel-t{
  font-family:'Playfair Display',Georgia,serif;
  font-weight:700;
  font-size:clamp(1.35rem,1.9vw,1.75rem);
  line-height:1.15;
  color:var(--tinta);
  margin:0;
  overflow-wrap:normal;
  word-break:normal;
}
.panel-s{font-style:italic;font-weight:600;font-size:1.02rem;margin:.9rem 0 0;}
.actual{display:flex;align-items:center;gap:10px;font-weight:600;font-size:1.02rem;margin:.4rem 0 0;}
.actual i{
  display:inline-block;width:20px;height:20px;
  border-radius:50% 0 50% 50%;
  transform:rotate(-45deg);
  border:2px solid var(--tinta);
}

/* Todos los grupos de opciones son cuadrículas: nunca se apilan ni se pisan */
div[data-testid="stVerticalBlock"]:has(> .st-key-pig_0),
div[data-testid="stVerticalBlock"]:has(> .st-key-pig_9),
div[data-testid="stVerticalBlock"]:has(> .st-key-gro_0),
div[data-testid="stVerticalBlock"]:has(> .st-key-pap_0),
div[data-testid="stVerticalBlock"]:has(> .st-key-pcol_0),
div[data-testid="stVerticalBlock"]:has(> .st-key-mesa_0),
div[data-testid="stVerticalBlock"]:has(> .st-key-tool_0),
div[data-testid="stVerticalBlock"]:has(> .st-key-fin_0),
div[data-testid="stVerticalBlock"]:has(> .st-key-fmt_0){
  display:grid !important;
  align-items:center;
  justify-items:stretch;
}
div[data-testid="stVerticalBlock"]:has(> .st-key-pig_0){
  grid-template-columns:repeat(5,minmax(0,1fr));
  gap:clamp(22px,3.4vw,50px) clamp(8px,1.6vw,26px);
  justify-items:center;
}
div[data-testid="stVerticalBlock"]:has(> .st-key-pig_9){
  grid-template-columns:repeat(6,minmax(0,1fr));
  gap:14px;
  justify-items:center;
}
div[data-testid="stVerticalBlock"]:has(> .st-key-gro_0){grid-template-columns:repeat(5,minmax(0,1fr));gap:14px;}
div[data-testid="stVerticalBlock"]:has(> .st-key-pap_0){grid-template-columns:repeat(4,minmax(0,1fr));gap:18px;}
div[data-testid="stVerticalBlock"]:has(> .st-key-pcol_0){grid-template-columns:repeat(4,minmax(0,1fr));gap:18px;justify-items:center;}
div[data-testid="stVerticalBlock"]:has(> .st-key-mesa_0){grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;justify-items:center;}
div[data-testid="stVerticalBlock"]:has(> .st-key-tool_0){grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;}
div[data-testid="stVerticalBlock"]:has(> .st-key-fin_0){grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;}
div[data-testid="stVerticalBlock"]:has(> .st-key-fmt_0){grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;}

[class*="st-key-pig_"], [class*="st-key-gro_"], [class*="st-key-pap_"], [class*="st-key-pcol_"],
[class*="st-key-mesa_"], [class*="st-key-tool_"], [class*="st-key-fin_"], [class*="st-key-fmt_"]{
  width:100% !important;
  min-width:0;
}
[class*="st-key-pig_"] [data-testid="stButton"], [class*="st-key-pcol_"] [data-testid="stButton"],
[class*="st-key-mesa_"] [data-testid="stButton"], [class*="st-key-gro_"] [data-testid="stButton"],
[class*="st-key-pig_"] .stButton, [class*="st-key-pcol_"] .stButton,
[class*="st-key-mesa_"] .stButton, [class*="st-key-gro_"] .stButton{
  width:100% !important;
  display:flex;
  justify-content:center;
}

/* Paleta de pintor: ovalada y alargada, con agujero para el pulgar */
.st-key-paleta, .st-key-extras{container-type:inline-size;}
.st-key-paleta{
  position:relative;
  width:100%;
  background:
    radial-gradient(ellipse at 28% 22%, rgba(255,238,196,.6) 0%, transparent 62%),
    repeating-linear-gradient(100deg, rgba(150,95,40,.10) 0 2px, transparent 2px 9px),
    linear-gradient(135deg,#F0CC92,#DDA860);
  border:4px solid #A9733A;
  border-radius:50% 50% 47% 53% / 62% 58% 42% 38%;
  padding:clamp(44px,5vw,70px) 7% clamp(48px,5vw,72px);
  box-shadow:inset 0 3px 0 rgba(255,255,255,.45), 0 14px 18px -8px rgba(70,45,15,.6);
}
/* agujero del pulgar: ocupa la décima casilla (abajo a la derecha) */
.st-key-paleta::after{
  content:"";
  position:absolute;
  right:9%; bottom:15%;
  width:clamp(34px,6cqw,60px);
  height:clamp(42px,7.4cqw,74px);
  border-radius:50%;
  background:#F7E2A8;
  border:3px solid #A9733A;
  box-shadow:inset 3px 4px 7px rgba(70,45,15,.5);
}
/* ligera ondulación para que parezca pintura puesta a mano */
.st-key-pig_0, .st-key-pig_4{position:relative;top:18px;}
.st-key-pig_1, .st-key-pig_3{position:relative;top:2px;}
.st-key-pig_2{position:relative;top:-8px;}
.st-key-pig_5{position:relative;top:-10px;}
.st-key-pig_8{position:relative;top:-10px;}

[class*="st-key-pig_"] button{
  --d:clamp(40px,10cqw,68px);
  position:relative;
  display:block;
  width:var(--d) !important;
  min-width:var(--d) !important;
  height:var(--d) !important;
  min-height:var(--d) !important;
  padding:0 !important;
  border:0 !important;
  border-radius:50% 0 50% 50% !important;
  transform:rotate(-45deg);
  box-shadow:inset -3px -4px 0 rgba(0,0,0,.14), 0 0 0 1.5px rgba(15,43,91,.4) !important;
  overflow:visible;
  transition:transform .12s ease;
}
.st-key-extras [class*="st-key-pig_"] button{--d:clamp(28px,6.6cqw,42px);}
[class*="st-key-pig_"] button p{font-size:0;line-height:0;color:transparent;}
[class*="st-key-pig_"] button::after{
  content:"";
  position:absolute;
  top:22%;left:30%;
  width:28%;height:15%;
  border-radius:50%;
  background:rgba(255,255,255,.55);
  transform:rotate(45deg);
}
[class*="st-key-pig_"] button:hover{transform:rotate(-45deg) scale(1.1) !important;}

/* Botón "+" (color personalizado) */
.st-key-pig_4 button{
  background:#FFF9E8 !important;
  border:3px dashed #A9733A !important;
  border-radius:50% !important;
  transform:none;
  box-shadow:none !important;
  display:flex;
  align-items:center;
  justify-content:center;
}
.st-key-pig_4 button:hover{transform:scale(1.08) !important;}
.st-key-pig_4 button::after{
  content:"+";
  position:static;
  width:auto;height:auto;
  background:none;
  transform:none;
  font-family:'Playfair Display',Georgia,serif;
  font-size:2.2rem;
  font-weight:500;
  line-height:1;
  color:var(--tinta);
}

/* Grosor de tiza: trazos diagonales */
[class*="st-key-gro_"] button{
  width:100% !important;
  height:84px !important;
  min-height:84px !important;
  padding:0 !important;
  display:flex;
  align-items:center;
  justify-content:center;
  background:transparent !important;
  border:3px solid transparent !important;
  border-radius:14px;
  box-shadow:none !important;
  transform:none !important;
}
[class*="st-key-gro_"] button:hover{background:#FBEFCB !important;}
[class*="st-key-gro_"] button p{font-size:0;line-height:0;}
[class*="st-key-gro_"] button::after{
  content:"";
  display:block;
  height:56px;
  border-radius:999px;
  transform:rotate(34deg);
}

/* Píldoras: herramienta y acabado */
[class*="st-key-tool_"] button, [class*="st-key-fin_"] button{
  width:100% !important;
  height:54px !important;
  min-height:54px !important;
  padding:0 10px !important;
  background:#FFF9E8 !important;
  border:2px solid var(--tinta) !important;
  border-radius:999px;
  box-shadow:none !important;
  transform:none !important;
}
[class*="st-key-tool_"] button p, [class*="st-key-fin_"] button p{
  font-family:'Playfair Display',Georgia,serif;
  font-weight:700;
  font-size:1.05rem;
  color:var(--tinta);
  white-space:nowrap;
}
[class*="st-key-tool_"] button:hover, [class*="st-key-fin_"] button:hover{background:#FBEFCB !important;}

/* Formato del cuaderno: miniaturas */
[class*="st-key-fmt_"] button{
  width:100% !important;
  height:112px !important;
  min-height:112px !important;
  padding:8px 6px !important;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  gap:10px;
  background:#FFF9E8 !important;
  border:2px solid rgba(15,43,91,.32) !important;
  border-radius:16px;
  box-shadow:none !important;
  transform:none !important;
}
[class*="st-key-fmt_"] button::before{
  content:"";
  display:block;
  border:2px solid var(--tinta);
  border-radius:3px;
  background:#FFFDF5;
}
[class*="st-key-fmt_"] button p{font-size:.95rem;line-height:1.1;font-weight:700;margin:0;}
[class*="st-key-fmt_"] button:hover{background:#FBEFCB !important;}

/* Muestras de disposición, color de papel y mesa */
[class*="st-key-pap_"] button{
  width:100% !important;
  height:80px !important;
  min-height:80px !important;
  padding:0 !important;
  border:2px solid rgba(15,43,91,.32) !important;
  border-radius:14px;
  box-shadow:none !important;
  transform:none !important;
}
[class*="st-key-pcol_"] button, [class*="st-key-mesa_"] button{
  width:54px !important;
  min-width:54px !important;
  height:54px !important;
  min-height:54px !important;
  padding:0 !important;
  border:2px solid rgba(15,43,91,.4) !important;
  border-radius:50% !important;
  box-shadow:none !important;
  transform:none !important;
}
[class*="st-key-pap_"] button p, [class*="st-key-pcol_"] button p, [class*="st-key-mesa_"] button p{font-size:0;line-height:0;}

/* Botones generales */
.stButton > button{
  font-family:'Playfair Display',Georgia,serif;
  font-weight:700;
  font-size:1.02rem;
  color:var(--tinta);
  background:#FFF9E8;
  border:2px solid var(--tinta);
  border-radius:999px;
  padding:.45rem 1.5rem;
  box-shadow:none;
  transition:background .12s ease, transform .12s ease;
}
.stButton > button:hover{background:#FBEFCB;color:var(--tinta);border-color:var(--tinta);}
.stButton > button:active{transform:translateY(1px);}
.st-key-interpretar .stButton > button{background:var(--tinta);color:#FFF6DD;}
.st-key-interpretar .stButton > button p{color:#FFF6DD;}
.st-key-interpretar .stButton > button:hover{background:#244A8C;}

[data-baseweb="input"], [data-baseweb="base-input"]{
  background:#FFF9E8 !important;
  border-radius:14px !important;
}
[data-baseweb="input"]{border:2px solid var(--tinta) !important;}
[data-baseweb="input"] input, [data-baseweb="base-input"] input{
  background:#FFF9E8 !important;
  color:var(--tinta) !important;
  -webkit-text-fill-color:var(--tinta);
}
[data-baseweb="input"] input::placeholder{color:rgba(15,43,91,.55) !important;-webkit-text-fill-color:rgba(15,43,91,.55);}

/* ---------- Cuaderno abierto ---------- */
.st-key-hoja{
  position:relative;
  width:fit-content;
  min-width:min(100%, 440px);
  max-width:100%;
  align-self:center;
  margin:0 auto 1.6rem;
  padding:24px 28px 34px;
  background:
    repeating-linear-gradient(45deg, rgba(255,255,255,.035) 0 2px, transparent 2px 6px),
    linear-gradient(135deg,#1D3F73,#102A52);
  border-radius:18px;
  box-shadow:0 30px 40px -16px rgba(40,22,6,.7), inset 0 2px 0 rgba(255,255,255,.14);
  outline:2px dashed rgba(255,233,184,.4);
  outline-offset:-10px;
}
.rotulo{text-align:center;margin:0 0 .9rem;}
.rotulo h1{
  font-family:'Playfair Display',Georgia,serif;
  font-style:italic;
  font-weight:700;
  font-size:2.7rem;
  line-height:1.1;
  margin:0;
  padding:0;
  color:#FFE9B8;
  text-shadow:0 2px 0 rgba(0,0,0,.35);
}
.rotulo p{font-style:italic;font-size:1.08rem;margin:.3rem 0 0;color:#F3E4C2;}

.st-key-paginas{
  position:relative;
  padding:26px 28px;
  border-radius:6px;
  box-shadow:
    0 2px 0 #EAE1C8, 0 4px 0 #D3C9AB, 0 6px 0 #EAE1C8, 0 8px 0 #CDC2A2,
    0 16px 20px -6px rgba(0,0,0,.5);
}
/* Espiral del lomo */
.st-key-paginas::before{
  content:"";
  position:absolute;
  top:-8px;bottom:-8px;
  left:calc(50% - 32px);
  width:64px;
  background-repeat:repeat-y;
  background-size:64px 32px;
  z-index:5;
  pointer-events:none;
}
/* Sombra del pliegue central */
.st-key-paginas::after{
  content:"";
  position:absolute;
  inset:0;
  background:linear-gradient(90deg,
    rgba(0,0,0,0) 0%, rgba(0,0,0,.06) 38%, rgba(0,0,0,.14) 48.4%,
    rgba(0,0,0,.30) 50%, rgba(0,0,0,.14) 51.6%, rgba(0,0,0,.06) 62%, rgba(0,0,0,0) 100%);
  border-radius:6px;
  z-index:4;
  pointer-events:none;
}
.st-key-zona{padding:0;overflow-x:auto;}
.st-key-zona iframe{
  display:block;
  max-width:100%;
  background:transparent !important;
  color-scheme:light;
}

/* ---------- Tarjetas de acciones y resultados ---------- */
.st-key-acciones, .st-key-resultados{
  max-width:1000px;
  margin:0 auto 1.2rem;
  background:linear-gradient(180deg,#FFF9E8,#FFF3D2);
  border:2px solid var(--borde);
  border-radius:20px;
  padding:16px 20px;
  box-shadow:0 12px 18px -10px rgba(60,38,12,.6);
}

/* ---------- Libreta de notas ---------- */
.libreta{
  position:relative;
  background-color:#FFFDF4;
  background-image:repeating-linear-gradient(to bottom, transparent 0, transparent 31px, rgba(15,43,91,.2) 31px, rgba(15,43,91,.2) 32px);
  background-position:0 14px;
  background-repeat:repeat-y;
  padding:14px 20px 22px 74px;
  margin:.2rem 0 1rem;
  border:1.5px solid rgba(15,43,91,.3);
  border-radius:6px 16px 16px 6px;
  box-shadow:0 10px 16px -10px rgba(60,38,12,.5);
  font-family:'Lora',Georgia,serif;
  font-style:italic;
  font-weight:600;
  font-size:1.06rem;
  line-height:32px;
  color:var(--tinta);
}
.libreta::before{
  content:"";
  position:absolute;
  top:0;bottom:0;left:52px;
  width:2px;
  background:rgba(224,57,62,.5);
}
.libreta::after{
  content:"";
  position:absolute;
  top:0;bottom:0;left:12px;
  width:22px;
  background:radial-gradient(circle at 50% 50%, #E9D3A6 0 8px, rgba(15,43,91,.35) 9px, transparent 10px) 0 28px / 22px 96px repeat-y;
}
.libreta-titulo{
  font-family:'Playfair Display',Georgia,serif;
  font-style:normal;
  font-weight:700;
  font-size:1.4rem;
  line-height:32px;
}
.libreta-texto{line-height:32px;}
.libreta-texto, .libreta-titulo{margin:0;}

@media (prefers-reduced-motion:reduce){
  .stButton > button, [class*="st-key-pig_"] button{transition:none;}
}
</style>
"""

# ---------------------------------------------------------------------------
# Color actual
# ---------------------------------------------------------------------------
if st.session_state.pig == IDX_PERSONALIZADO:
    pig_nombre, pig_hex = "Color personalizado", st.session_state.custom_hex
else:
    pig_nombre, pig_hex = SLOTS[st.session_state.pig]
papel_rgb = hex_a_rgb(COLORES_PAPEL[st.session_state.papel_color][1])

st.markdown(CSS_BASE, unsafe_allow_html=True)
st.markdown(css_fondo(MESAS[st.session_state.mesa][1]), unsafe_allow_html=True)
st.markdown(css_dinamico(pig_hex), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
with st.sidebar:
    # --- Color de tiza: paleta de pintor alargada ---
    with st.container(key="panel_color"):
        st.markdown('<div class="panel-t">Color de tiza</div>', unsafe_allow_html=True)
        with st.container(key="paleta"):
            for i in range(9):
                nombre = SLOTS[i][0] if SLOTS[i] else "Color personalizado"
                boton(nombre, key=f"pig_{i}", help=nombre, on_click=elegir, args=("pig", i))
        if st.session_state.pig == IDX_PERSONALIZADO:
            st.session_state.custom_hex = st.color_picker(
                "Elige tu propio color",
                value=st.session_state.custom_hex,
                key="selector_personalizado",
            )

        st.markdown('<div class="panel-s">Más pigmentos</div>', unsafe_allow_html=True)
        with st.container(key="extras"):
            for i in range(9, 15):
                boton(SLOTS[i][0], key=f"pig_{i}", help=SLOTS[i][0], on_click=elegir, args=("pig", i))

        st.markdown(
            f'<div class="actual"><i style="background:{pig_hex}"></i>Pintando con: {pig_nombre}</div>',
            unsafe_allow_html=True,
        )

    # --- Grosor de tiza ---
    with st.container(key="panel_grosor"):
        st.markdown('<div class="panel-t">Grosor de tiza</div>', unsafe_allow_html=True)
        with st.container(key="g_gro"):
            for i, (nombre, _) in enumerate(GROSORES):
                boton(nombre, key=f"gro_{i}", help=nombre, on_click=elegir, args=("gro", i))
        intensidad = st.slider("Intensidad del pigmento", 20, 100, 80, format="%d%%")

    # --- Formato del cuaderno ---
    with st.container(key="panel_formato"):
        st.markdown('<div class="panel-t">Formato del cuaderno</div>', unsafe_allow_html=True)
        with st.container(key="g_fmt"):
            for k, (nombre, fw, fh) in enumerate(FORMATOS):
                boton(nombre, key=f"fmt_{k}", help=f"{fw} × {fh} px",
                      on_click=aplicar_formato, args=(fw, fh))
        st.slider("Ancho del lienzo", 340, 900, step=20, key="lienzo_ancho")
        st.slider("Alto del lienzo", 300, 780, step=20, key="lienzo_alto")
        st.caption("Al cambiar el formato se empieza una hoja limpia.")

    # --- Disposición del tablero ---
    with st.container(key="panel_disposicion"):
        st.markdown('<div class="panel-t">Disposición</div>', unsafe_allow_html=True)
        with st.container(key="g_pap"):
            for i, nombre in enumerate(PAPELES):
                boton(nombre, key=f"pap_{i}", help=nombre, on_click=elegir, args=("papel", i))

    # --- Papel y mesa ---
    with st.container(key="panel_papel"):
        st.markdown('<div class="panel-t">Papel y mesa</div>', unsafe_allow_html=True)
        st.markdown('<div class="panel-s">Color de las hojas</div>', unsafe_allow_html=True)
        with st.container(key="g_pcol"):
            for i, (nombre, _) in enumerate(COLORES_PAPEL):
                boton(nombre, key=f"pcol_{i}", help=nombre, on_click=elegir, args=("papel_color", i))
        st.markdown('<div class="panel-s">Madera de la mesa</div>', unsafe_allow_html=True)
        with st.container(key="g_mesa"):
            for i, (nombre, _) in enumerate(MESAS):
                boton(nombre, key=f"mesa_{i}", help=nombre, on_click=elegir, args=("mesa", i))

    # --- Herramienta y acabado ---
    with st.container(key="panel_herramienta"):
        st.markdown('<div class="panel-t">Herramienta</div>', unsafe_allow_html=True)
        with st.container(key="g_tool"):
            for i, nombre in enumerate(HERRAMIENTAS):
                boton(ETIQUETA_HERRAMIENTA[i], key=f"tool_{i}", help=nombre,
                      on_click=elegir, args=("tool", i))
        st.markdown('<div class="panel-s">Acabado de la imagen final</div>', unsafe_allow_html=True)
        with st.container(key="g_fin"):
            for i, nombre in enumerate(ACABADOS):
                boton(nombre, key=f"fin_{i}", on_click=elegir, args=("acabado", i))

herramienta = list(HERRAMIENTAS)[st.session_state.tool]

# ---------------------------------------------------------------------------
# Cuaderno abierto (tablero)
# ---------------------------------------------------------------------------
r, g, b = hex_a_rgb(pig_hex)
alfa = intensidad / 100
trazo = f"rgba({r},{g},{b},{alfa})"
relleno = f"rgba({r},{g},{b},{alfa * 0.35})"
ancho = GROSORES[st.session_state.gro][1]

with st.container(key="hoja"):
    st.markdown(
        '<div class="rotulo"><h1>Taller de arte</h1>'
        '<p>Dibuja lo que quieras y la máquina lo interpretará.</p></div>',
        unsafe_allow_html=True,
    )
    with st.container(key="paginas"):
        with st.container(key="zona"):
            lienzo = st_canvas(
                fill_color=relleno,
                stroke_width=ancho,
                stroke_color=trazo,
                background_color="rgba(255,255,255,0)",
                height=st.session_state.lienzo_alto,
                width=st.session_state.lienzo_ancho,
                drawing_mode=HERRAMIENTAS[herramienta],
                key=f"lienzo_{st.session_state.lienzo}_{st.session_state.lienzo_ancho}x{st.session_state.lienzo_alto}",
            )

# ---------------------------------------------------------------------------
# Acciones (los avisos aparecen dentro de la tarjeta para que se lean bien)
# ---------------------------------------------------------------------------
with st.container(key="acciones"):
    try:
        c_clave, c_interpretar, c_nuevo = st.columns([2.2, 1.5, 1], vertical_alignment="bottom")
    except TypeError:
        c_clave, c_interpretar, c_nuevo = st.columns([2.2, 1.5, 1])

    with c_clave:
        ke = st.text_input("Clave de OpenAI", type="password",
                           placeholder="Pega aquí tu clave de OpenAI")
        api_key = ke or os.environ.get("OPENAI_API_KEY", "")
    with c_interpretar:
        with st.container(key="interpretar"):
            interpretar = st.button("Interpretar mi dibujo")
    with c_nuevo:
        nuevo = st.button("Lienzo nuevo")
    aviso = st.container()

if nuevo:
    st.session_state.lienzo += 1
    st.session_state.nota = ""
    st.session_state.historia = ""
    st.session_state.vista = None
    st.rerun()

if interpretar:
    with aviso:
        if not api_key:
            st.warning("Ingresa tu clave de OpenAI para interpretar el dibujo.")
        elif lienzo.image_data is None:
            st.info("El tablero todavía no está listo. Intenta de nuevo en un momento.")
        else:
            imagen = imagen_del_lienzo(lienzo.image_data, papel_rgb)
            if lienzo_en_blanco(imagen, papel_rgb):
                st.info("El papel sigue en blanco. Haz unos trazos y vuelve a interpretar.")
            else:
                with st.spinner("Interpretando tus trazos..."):
                    try:
                        cliente = OpenAI(api_key=api_key)
                        respuesta = cliente.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": (
                                                "Eres un guía amable de un taller de arte. "
                                                "Describe en español, de forma breve (máximo 5 frases), "
                                                "lo que ves en este dibujo hecho a mano: formas, colores "
                                                "y qué podría representar."
                                            ),
                                        },
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/png;base64,{a_base64(imagen)}"
                                            },
                                        },
                                    ],
                                }
                            ],
                            max_tokens=500,
                        )
                        st.session_state.nota = respuesta.choices[0].message.content or ""
                        if st.session_state.acabado == 0:
                            st.session_state.vista = acuarela(imagen, papel_rgb)
                        else:
                            st.session_state.vista = tiza(imagen, papel_rgb)
                        st.session_state.historia = ""
                    except Exception as e:
                        st.error(f"No se pudo interpretar el dibujo: {e}")

# ---------------------------------------------------------------------------
# Resultado: libreta de notas + imagen con acabado
# ---------------------------------------------------------------------------
if st.session_state.nota:
    with st.container(key="resultados"):
        col_nota, col_vista = st.columns([1.15, 1], gap="large")

        with col_nota:
            st.markdown(libreta("Notas del taller", st.session_state.nota), unsafe_allow_html=True)

            if st.button("Convertir en cuento"):
                with st.spinner("Escribiendo el cuento..."):
                    try:
                        cliente = OpenAI(api_key=api_key)
                        cuento = cliente.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {
                                    "role": "user",
                                    "content": (
                                        f"Basándote en esta descripción: '{st.session_state.nota}', "
                                        "crea una historia infantil breve y entretenida. "
                                        "Debe ser creativa y apropiada para niños."
                                    ),
                                }
                            ],
                            max_tokens=500,
                        )
                        st.session_state.historia = cuento.choices[0].message.content or ""
                    except Exception as e:
                        st.error(f"No se pudo crear el cuento: {e}")

        with col_vista:
            if st.session_state.vista is not None:
                nombre_acabado = ACABADOS[st.session_state.acabado].lower()
                st.image(st.session_state.vista, caption=f"Tu dibujo con acabado de {nombre_acabado}")

        if st.session_state.historia:
            st.markdown(libreta("Cuento del taller", st.session_state.historia), unsafe_allow_html=True)
