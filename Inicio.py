import base64
import colorsys
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
TINTA = "#1D3B70"  # azul de todas las letras
SEL = "#E8912D"    # marco naranja de lo seleccionado

# 9 casillas de la paleta (la 4 es el botón "+" de color personalizado)
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
}.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor


def elegir(clave, valor):
    st.session_state[clave] = valor


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
# Ilustraciones de la mesa (SVG planos que se usan como fondo)
# ---------------------------------------------------------------------------
def uri(svg):
    datos = base64.b64encode(mini(svg).encode("utf-8")).decode("ascii")
    return f'url("data:image/svg+xml;base64,{datos}")'


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


SVG_ARRIBA_DERECHA = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="440" height="340" viewBox="0 0 440 340">
<path d="M150 -4 L340 -4 C350 30 328 62 296 72 C274 80 252 70 232 60 C200 48 150 40 150 -4Z" fill="#0C4DB2"/>
{salpicadura(190, 112, "#FDB92D", [(-44, -38), (36, -52), (52, 22), (-40, 40), (4, 56)], 18, 22, [(120, 80, 8), (236, 90, 6), (156, 172, 7)])}
{tubo(300, 72, -42, "#F5C02A", 1.0)}
{tubo(398, 34, 28, "#3EAF5C", 0.95)}
{tubo(330, 200, -18, "#E0393E", 1.0)}
{tubo(414, 150, 58, "#2F78D8", 1.0)}
{tubo(400, 280, 6, "#F06AA0", 0.95)}
</svg>
"""

SVG_DERECHA_CRAYONES = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="260" height="330" viewBox="0 0 260 330">
<g transform="translate(150 190) rotate(-60)">
{''.join(
    f'<g><rect x="{-84 + k * 25}" y="-82" width="19" height="62" fill="{c}"/>'
    f'<path d="M{-84 + k * 25} -82 L{-65 + k * 25} -82 L{-74.5 + k * 25} -106Z" fill="{c}"/></g>'
    for k, c in enumerate(["#E0393E", "#F28A2E", "#3E9E5F", "#2F78D8", "#7B4FB8", "#6B4A2B", "#26211F"])
)}
<rect x="-100" y="-34" width="200" height="96" rx="8" fill="#F9C23C"/>
<rect x="-100" y="-4" width="200" height="9" fill="#1D1D1D"/>
<rect x="-100" y="14" width="200" height="5" fill="#1D1D1D"/>
<circle cx="70" cy="40" r="9" fill="#E0393E"/>
<rect x="-100" y="-34" width="200" height="18" rx="8" fill="#FBD36B"/>
</g>
</svg>
"""


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


SVG_ABAJO_DERECHA = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="340" height="310" viewBox="0 0 340 310">
{_libros()}
<ellipse cx="136" cy="96" rx="48" ry="8" fill="#000" opacity=".18"/>
<path d="M136 52 C100 38 82 70 92 100 C102 126 124 122 136 118 C148 122 170 126 180 100 C190 70 172 38 136 52Z" fill="#E0393E"/>
<path d="M136 52 C136 36 144 26 158 22 C158 38 150 48 136 52Z" fill="#3E9E5F"/>
<ellipse cx="116" cy="70" rx="7" ry="13" fill="#fff" opacity=".4" transform="rotate(18 116 70)"/>
{salpicadura(300, 200, "#FDB92D", [(-26, -34), (30, -30), (34, 24), (-22, 36)], 15, 16, [(264, 150, 6), (322, 262, 7)])}
</svg>
"""

SVG_ARRIBA_IZQUIERDA = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">
{chincheta(46, 70, -35, "#F5C02A")}
{chincheta(130, 40, -10, "#4DA3F0")}
{chincheta(100, 150, 22, "#E8381F")}
{salpicadura(290, 76, "#6A4FA8", [(-60, -34), (-70, 20), (52, -38), (62, 28), (6, 56), (-8, -58)], 14, 24, [(222, 38, 7), (338, 112, 6), (352, 50, 5), (260, 140, 6)])}
</svg>
"""


def _abanico():
    petalos = ""
    n = 20
    for k in range(n):
        ang = -96 + k * (92 / (n - 1))
        h, s, v = (205 + k * 14) % 360, 0.9, 0.82
        r, g, b = colorsys.hsv_to_rgb(h / 360, s, v)
        color = "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))
        petalos += f'<ellipse cx="130" cy="0" rx="130" ry="62" fill="{color}" opacity=".9" transform="rotate({ang:.1f})"/>'
    return petalos


SVG_ABAJO_IZQUIERDA = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="360" viewBox="0 0 400 360">
<g transform="translate(40 330)">{_abanico()}</g>
<path d="M250 360 C260 322 306 316 322 294 C338 262 384 272 392 312 C412 322 420 350 410 360Z" fill="#7FBC7B"/>
</svg>
"""


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


SVG_TIZA_ARRIBA = f'<svg xmlns="http://www.w3.org/2000/svg" width="520" height="140" viewBox="0 0 520 140">{_aro_tiza(-12)}</svg>'
SVG_TIZA_ABAJO = f'<svg xmlns="http://www.w3.org/2000/svg" width="520" height="140" viewBox="0 0 520 140">{_aro_tiza(152)}</svg>'


def svg_madera(base):
    """Veta de madera: trazos ondulados oscuros sobre el color de la mesa."""
    azar = random.Random(5)
    oscuro = mezcla(base, (92, 54, 22), 0.55)
    trazos = ""
    for _ in range(90):
        x = azar.randint(10, 680)
        y = azar.randint(10, 440)
        largo = azar.randint(60, 190)
        ond = azar.randint(3, 7)
        d = f"M{x} {y}"
        for s in range(3):
            d += f" c{largo // 6} {-ond},{largo // 3} {ond},{largo // 3} 0"
        trazos += (
            f'<path d="{d}" stroke="{oscuro}" stroke-width="{azar.choice([2, 3, 4, 5])}" '
            f'stroke-opacity="{azar.choice([.28, .4, .55])}" fill="none" stroke-linecap="round"/>'
        )
    motas = "".join(
        f'<circle cx="{azar.randint(5, 695)}" cy="{azar.randint(5, 455)}" r="{azar.choice([1, 1.5, 2])}" '
        f'fill="{oscuro}" opacity=".5"/>'
        for _ in range(120)
    )
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="700" height="460" viewBox="0 0 700 460">{trazos}{motas}</svg>'


@st.cache_data(show_spinner=False)
def css_fondo(mesa_hex):
    capas = [
        (uri(SVG_TIZA_ARRIBA), "no-repeat", "calc(50% + 190px) 0", "auto 15vh"),
        (uri(SVG_TIZA_ABAJO), "no-repeat", "calc(50% + 190px) 100%", "auto 15vh"),
        (uri(SVG_ARRIBA_DERECHA), "no-repeat", "right 0 top 0", "auto 38vh"),
        (uri(SVG_DERECHA_CRAYONES), "no-repeat", "right 0 top 46%", "auto 33vh"),
        (uri(SVG_ABAJO_DERECHA), "no-repeat", "right 0 bottom 0", "auto 32vh"),
        (uri(SVG_ARRIBA_IZQUIERDA), "no-repeat", "left 392px top 0", "auto 32vh"),
        (uri(SVG_ABAJO_IZQUIERDA), "no-repeat", "left 380px bottom 0", "auto 36vh"),
        (uri(svg_madera(mesa_hex)), "repeat", "0 0", "700px 460px"),
    ]
    return (
        "<style>.stApp{"
        f"background-color:{mesa_hex};"
        f"background-image:{','.join(c[0] for c in capas)};"
        f"background-repeat:{','.join(c[1] for c in capas)};"
        f"background-position:{','.join(c[2] for c in capas)};"
        f"background-size:{','.join(c[3] for c in capas)};"
        "background-attachment:fixed;}</style>"
    )


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------
def css_dinamico(pig_hex):
    reglas = []
    mesa_hex = MESAS[st.session_state.mesa][1]
    papel_hex = COLORES_PAPEL[st.session_state.papel_color][1]

    # Gotas de pintura
    for i, slot in enumerate(SLOTS):
        if slot is None:
            continue
        _, hex_ = slot
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
        ".st-key-pap_1 button{background:repeating-linear-gradient(to bottom, transparent 0 9px, rgba(29,59,112,.38) 9px 10px), #FFFDF5 !important;}"
    )
    reglas.append(
        ".st-key-pap_2 button{background:linear-gradient(rgba(29,59,112,.32) 1px, transparent 1px) 0 0 / 12px 12px, "
        "linear-gradient(90deg, rgba(29,59,112,.32) 1px, transparent 1px) 0 0 / 12px 12px, #FFFDF5 !important;}"
    )
    reglas.append(
        ".st-key-pap_3 button{background:radial-gradient(circle, rgba(29,59,112,.6) 1.4px, transparent 1.8px) 0 0 / 11px 11px, #FFFDF5 !important;}"
    )
    for i, (_, hex_) in enumerate(COLORES_PAPEL):
        reglas.append(f".st-key-pcol_{i} button{{background:{hex_} !important;}}")
    for i, (_, hex_) in enumerate(MESAS):
        reglas.append(f".st-key-mesa_{i} button{{background:{hex_} !important;}}")

    # Hoja del tablero
    tramas = [
        "none",
        "repeating-linear-gradient(to bottom, transparent 0, transparent 35px, rgba(29,59,112,.20) 35px, rgba(29,59,112,.20) 36px)",
        "linear-gradient(rgba(29,59,112,.13) 1px, transparent 1px), linear-gradient(90deg, rgba(29,59,112,.13) 1px, transparent 1px)",
        "radial-gradient(circle, rgba(29,59,112,.32) 1.6px, transparent 2px)",
    ]
    tamanos = ["auto", "auto", "30px 30px", "28px 28px"]
    hueco_osc = mezcla(mesa_hex, (0, 0, 0), 0.38)
    hueco_cl = mezcla(mesa_hex, (255, 255, 255), 0.05)
    hueco = uri(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="112" height="64" viewBox="0 0 112 64">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{hueco_osc}"/><stop offset="1" stop-color="{hueco_cl}"/></linearGradient></defs>'
        f'<rect x="4" y="0" width="76" height="64" fill="url(#g)"/></svg>'
    )
    reglas.append(
        f".st-key-hoja{{background-color:{papel_hex};}}"
        f".st-key-hoja::before{{background-image:{hueco};}}"
        f".st-key-zona{{background-image:{tramas[st.session_state.papel]};"
        f"background-size:{tamanos[st.session_state.papel]};}}"
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
    return "<style>" + "\n".join(reglas) + "</style>"


CSS_BASE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,700;1,500&family=Lora:ital,wght@0,400;0,600;1,400&display=swap');

:root{
  --tinta:#1D3B70;
  --tarjeta:#FFF6DD;
  --borde:#EBD7A3;
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
[data-testid="stHeader"]{background:transparent;}
.block-container{max-width:1500px;padding-top:3.4rem;padding-bottom:4rem;}

/* ---------- Barra lateral (como tu referencia) ---------- */
[data-testid="stSidebar"][aria-expanded="true"]{
  min-width:380px !important;
  width:380px !important;
}
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#FCEFC9,#F7E2A8);
  border-right:2px solid rgba(160,110,40,.35);
}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{padding:1rem .9rem;}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p{color:var(--tinta);}

[class*="st-key-panel_"]{
  background:linear-gradient(180deg,#FFF9E8,#FFF3D2);
  border:2px solid var(--borde);
  border-radius:22px;
  padding:16px 16px 18px;
  box-shadow:0 8px 14px -8px rgba(110,70,20,.45), inset 0 2px 0 #fff;
  margin-bottom:14px;
}
.panel-t{
  font-family:'Playfair Display',Georgia,serif;
  font-weight:700;
  font-size:1.5rem;
  line-height:1.1;
  color:var(--tinta);
  margin:0 0 .7rem;
}
.panel-s{font-style:italic;font-size:.95rem;margin:.7rem 0 .4rem;opacity:.85;}

/* Paleta de madera con gotas de pintura */
.st-key-paleta{
  position:relative;
  background:
    repeating-linear-gradient(100deg, rgba(150,95,40,.10) 0 2px, transparent 2px 9px),
    linear-gradient(135deg,#F0CC92,#DDA860);
  border:3px solid #A9733A;
  border-radius:50%;
  padding:36px 34px 34px;
  margin:.1rem 0 .6rem;
  box-shadow:inset 0 3px 0 rgba(255,255,255,.45), 0 10px 12px -6px rgba(70,45,15,.55);
}
[class*="st-key-pig_"] [data-testid="stButton"],
[class*="st-key-pig_"] .stButton{
  width:100% !important;
  display:flex;
  justify-content:center;
}
.st-key-pig_0, .st-key-pig_2{margin-top:12px;}
.st-key-pig_6, .st-key-pig_8{margin-top:-12px;}
[class*="st-key-pig_"] button{
  position:relative;
  width:100% !important;
  max-width:56px;
  aspect-ratio:1;
  height:auto !important;
  min-height:0 !important;
  padding:0 !important;
  border:0 !important;
  border-radius:50% 0 50% 50% !important;
  transform:rotate(-45deg);
  box-shadow:inset -3px -4px 0 rgba(0,0,0,.14) !important;
  transition:transform .12s ease;
}
[class*="st-key-pig_"] button p{font-size:0;line-height:0;}
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
[class*="st-key-gro_"] [data-testid="stButton"],
[class*="st-key-gro_"] .stButton{width:100% !important;}
[class*="st-key-gro_"] button{
  width:100% !important;
  height:68px !important;
  min-height:0 !important;
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
  height:48px;
  border-radius:999px;
  transform:rotate(34deg);
}

/* Píldoras: herramienta y acabado */
[class*="st-key-tool_"] [data-testid="stButton"], [class*="st-key-tool_"] .stButton,
[class*="st-key-fin_"] [data-testid="stButton"], [class*="st-key-fin_"] .stButton{width:100% !important;}
[class*="st-key-tool_"] button, [class*="st-key-fin_"] button{
  width:100% !important;
  height:46px !important;
  min-height:0 !important;
  padding:0 6px !important;
  background:#FFF9E8 !important;
  border:2px solid var(--tinta) !important;
  border-radius:999px;
  box-shadow:none !important;
  transform:none !important;
}
[class*="st-key-tool_"] button p, [class*="st-key-fin_"] button p{
  font-family:'Playfair Display',Georgia,serif;
  font-weight:700;
  font-size:1rem;
  color:var(--tinta);
}
[class*="st-key-tool_"] button:hover, [class*="st-key-fin_"] button:hover{background:#FBEFCB !important;}

/* Muestras de disposición, color de papel y mesa */
[class*="st-key-pap_"] [data-testid="stButton"], [class*="st-key-pap_"] .stButton,
[class*="st-key-pcol_"] [data-testid="stButton"], [class*="st-key-mesa_"] [data-testid="stButton"]{width:100% !important;}
[class*="st-key-pap_"] button{
  width:100% !important;
  height:58px !important;
  min-height:0 !important;
  padding:0 !important;
  border:2px solid rgba(29,59,112,.28) !important;
  border-radius:12px;
  box-shadow:none !important;
  transform:none !important;
}
[class*="st-key-pcol_"] button, [class*="st-key-mesa_"] button{
  width:100% !important;
  max-width:48px;
  aspect-ratio:1;
  height:auto !important;
  min-height:0 !important;
  padding:0 !important;
  border:2px solid rgba(29,59,112,.28) !important;
  border-radius:50% !important;
  box-shadow:none !important;
  transform:none !important;
}
[class*="st-key-pcol_"] [data-testid="stButton"], [class*="st-key-mesa_"] [data-testid="stButton"]{display:flex;justify-content:center;}
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
.st-key-interpretar .stButton > button:hover{background:#2A4E8F;}

[data-baseweb="input"]{
  background:#FFF9E8 !important;
  border:2px solid var(--tinta) !important;
  border-radius:14px !important;
}
[data-baseweb="input"] input{background:transparent !important;color:var(--tinta);}

/* ---------- Tablero: hoja de cuaderno sobre la mesa ---------- */
.st-key-hoja{
  position:relative;
  max-width:900px;
  margin:0 auto 1.4rem;
  padding:116px 34px 30px;
  border-radius:3px;
  box-shadow:0 26px 34px -14px rgba(50,28,8,.65), 0 3px 0 rgba(255,255,255,.35) inset;
}
.st-key-hoja::before{
  content:"";
  position:absolute;
  top:36px;left:44px;right:20px;
  height:64px;
  background-repeat:repeat-x;
  background-size:112px 64px;
  pointer-events:none;
}
.rotulo{text-align:center;margin:0 0 1rem;}
.rotulo h1{
  font-family:'Playfair Display',Georgia,serif;
  font-style:italic;
  font-weight:700;
  font-size:2.8rem;
  line-height:1.1;
  margin:0;
  padding:0;
  color:var(--tinta);
}
.rotulo p{font-style:italic;font-size:1.1rem;margin:.3rem 0 0;opacity:.85;}
.st-key-zona{padding:0;}
.st-key-zona iframe{
  display:block;
  max-width:100%;
  background:transparent !important;
  color-scheme:light;
}

/* ---------- Tarjetas de acciones y resultados ---------- */
.st-key-acciones, .st-key-resultados{
  max-width:900px;
  margin:0 auto 1.2rem;
  background:linear-gradient(180deg,#FFF9E8,#FFF3D2);
  border:2px solid var(--borde);
  border-radius:20px;
  padding:16px 20px;
  box-shadow:0 12px 18px -10px rgba(60,38,12,.55);
}

/* ---------- Libreta de notas ---------- */
.libreta{
  position:relative;
  background-color:#FFFDF4;
  background-image:repeating-linear-gradient(to bottom, transparent 0, transparent 31px, rgba(29,59,112,.18) 31px, rgba(29,59,112,.18) 32px);
  background-position:0 14px;
  background-repeat:repeat-y;
  padding:14px 20px 22px 74px;
  margin:.2rem 0 1rem;
  border:1.5px solid rgba(29,59,112,.25);
  border-radius:6px 16px 16px 6px;
  box-shadow:0 10px 16px -10px rgba(60,38,12,.5);
  font-family:'Lora',Georgia,serif;
  font-style:italic;
  font-size:1.08rem;
  line-height:32px;
  color:#1D3B70;
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
  background:radial-gradient(circle at 50% 50%, #E9D3A6 0 8px, rgba(29,59,112,.35) 9px, transparent 10px) 0 28px / 22px 96px repeat-y;
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
    pig_hex = st.session_state.custom_hex
else:
    pig_hex = SLOTS[st.session_state.pig][1]
papel_rgb = hex_a_rgb(COLORES_PAPEL[st.session_state.papel_color][1])

st.markdown(CSS_BASE, unsafe_allow_html=True)
st.markdown(css_fondo(MESAS[st.session_state.mesa][1]), unsafe_allow_html=True)
st.markdown(css_dinamico(pig_hex), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
with st.sidebar:
    # --- Color de tiza: gotas de pintura sobre la paleta ---
    with st.container(key="panel_color"):
        st.markdown('<div class="panel-t">Color de tiza</div>', unsafe_allow_html=True)
        with st.container(key="paleta"):
            for fila in range(3):
                columnas = st.columns(3, gap="small")
                for c in range(3):
                    i = fila * 3 + c
                    with columnas[c]:
                        with st.container(key=f"pig_{i}"):
                            nombre = SLOTS[i][0] if SLOTS[i] else "Color personalizado"
                            boton(nombre, key=f"btn_pig_{i}", help=nombre,
                                  on_click=elegir, args=("pig", i))
        if st.session_state.pig == IDX_PERSONALIZADO:
            st.session_state.custom_hex = st.color_picker(
                "Elige tu propio color",
                value=st.session_state.custom_hex,
                key="selector_personalizado",
            )

    # --- Grosor de tiza ---
    with st.container(key="panel_grosor"):
        st.markdown('<div class="panel-t">Grosor de tiza</div>', unsafe_allow_html=True)
        cols_grosor = st.columns(5, gap="small")
        for i, (nombre, _) in enumerate(GROSORES):
            with cols_grosor[i]:
                with st.container(key=f"gro_{i}"):
                    boton(nombre, key=f"btn_gro_{i}", help=nombre,
                          on_click=elegir, args=("gro", i))
        intensidad = st.slider("Intensidad del pigmento", 20, 100, 80, format="%d%%")

    # --- Disposición del tablero ---
    with st.container(key="panel_disposicion"):
        st.markdown('<div class="panel-t">Disposición</div>', unsafe_allow_html=True)
        cols_papel = st.columns(4, gap="small")
        for i, nombre in enumerate(PAPELES):
            with cols_papel[i]:
                with st.container(key=f"pap_{i}"):
                    boton(nombre, key=f"btn_pap_{i}", help=nombre,
                          on_click=elegir, args=("papel", i))

    # --- Papel y mesa ---
    with st.container(key="panel_papel"):
        st.markdown('<div class="panel-t">Papel y mesa</div>', unsafe_allow_html=True)
        st.markdown('<div class="panel-s">Color del papel</div>', unsafe_allow_html=True)
        cols_pcol = st.columns(4, gap="small")
        for i, (nombre, _) in enumerate(COLORES_PAPEL):
            with cols_pcol[i]:
                with st.container(key=f"pcol_{i}"):
                    boton(nombre, key=f"btn_pcol_{i}", help=nombre,
                          on_click=elegir, args=("papel_color", i))
        st.markdown('<div class="panel-s">Madera de la mesa</div>', unsafe_allow_html=True)
        cols_mesa = st.columns(3, gap="small")
        for i, (nombre, _) in enumerate(MESAS):
            with cols_mesa[i]:
                with st.container(key=f"mesa_{i}"):
                    boton(nombre, key=f"btn_mesa_{i}", help=nombre,
                          on_click=elegir, args=("mesa", i))

    # --- Herramienta y acabado ---
    with st.container(key="panel_herramienta"):
        st.markdown('<div class="panel-t">Herramienta</div>', unsafe_allow_html=True)
        cols_tool = st.columns(3, gap="small")
        for i, nombre in enumerate(HERRAMIENTAS):
            with cols_tool[i]:
                with st.container(key=f"tool_{i}"):
                    boton(ETIQUETA_HERRAMIENTA[i], key=f"btn_tool_{i}", help=nombre,
                          on_click=elegir, args=("tool", i))
        st.markdown('<div class="panel-s">Acabado de la imagen final</div>', unsafe_allow_html=True)
        cols_fin = st.columns(2, gap="small")
        for i, nombre in enumerate(ACABADOS):
            with cols_fin[i]:
                with st.container(key=f"fin_{i}"):
                    boton(nombre, key=f"btn_fin_{i}", on_click=elegir, args=("acabado", i))

herramienta = list(HERRAMIENTAS)[st.session_state.tool]

# ---------------------------------------------------------------------------
# Tablero: hoja de cuaderno
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
    with st.container(key="zona"):
        lienzo = st_canvas(
            fill_color=relleno,
            stroke_width=ancho,
            stroke_color=trazo,
            background_color="rgba(255,255,255,0)",
            height=480,
            width=800,
            drawing_mode=HERRAMIENTAS[herramienta],
            key=f"lienzo_{st.session_state.lienzo}",
        )

# ---------------------------------------------------------------------------
# Acciones
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

if nuevo:
    st.session_state.lienzo += 1
    st.session_state.nota = ""
    st.session_state.historia = ""
    st.session_state.vista = None
    st.rerun()

if interpretar:
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
