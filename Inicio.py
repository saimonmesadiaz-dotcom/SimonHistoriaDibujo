import base64
import html
import io
import math
import os

import numpy as np
import streamlit as st
from openai import OpenAI
from PIL import Image, ImageFilter
from streamlit_drawable_canvas import st_canvas

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
PAPEL = (252, 248, 236)
PAPEL_HEX = "#FCF8EC"
AZUL_TINTA = "#1B2F52"
ULTRAMAR = "#2E5BBA"

PIGMENTOS = [
    ("Azul ultramar", "#2E6BD6"),
    ("Rojo Carmín", "#D62839"),
    ("Verde hoja", "#3FA34D"),
    ("Amarillo cadmio", "#F7C325"),
    ("Naranja", "#F26B21"),
    ("Violeta", "#6B3FA0"),
]

GROSORES = [("Muy fino", 2), ("Fino", 5), ("Medio", 10), ("Grueso", 18), ("Brocha", 32)]

HERRAMIENTAS = {
    "Pincel libre": "freedraw",
    "Rectángulo": "rect",
    "Círculo": "circle",
}

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
    "acuarela": None,
    "pig": 1,
    "gro": 2,
    "tool": 0,
    "custom_hex": "#E873A5",
}.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor


def elegir_pigmento(i):
    st.session_state.pig = i


def elegir_grosor(i):
    st.session_state.gro = i


def elegir_herramienta(i):
    st.session_state.tool = i


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


def imagen_del_lienzo(datos):
    img = Image.fromarray(np.array(datos).astype("uint8"), "RGBA")
    fondo = Image.new("RGBA", img.size, PAPEL + (255,))
    fondo.alpha_composite(img)
    return fondo.convert("RGB")


def lienzo_en_blanco(img):
    dif = np.abs(np.array(img).astype(int) - np.array(PAPEL)).max(axis=2)
    return (dif > 12).sum() < 30


def a_base64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def acuarela(img):
    """Simula un acabado de acuarela: lavado suave, borde de pigmento y grano de papel."""
    arr = np.array(img.convert("RGB")).astype(np.float32)
    h, w, _ = arr.shape
    papel = np.array(PAPEL, dtype=np.float32)
    carga = np.clip(papel - arr, 0, 255)

    def desenfocar(a, radio):
        im = Image.fromarray(a.astype("uint8")).filter(ImageFilter.GaussianBlur(radio))
        return np.array(im).astype(np.float32)

    lavado = desenfocar(carga, 2.4)
    borde = np.clip(desenfocar(carga, 1.0) - desenfocar(carga, 6.0), 0, 255)

    rng = np.random.default_rng(7)
    g = rng.random((h // 6 + 2, w // 6 + 2)).astype(np.float32)
    g = np.array(
        Image.fromarray((g * 255).astype("uint8")).resize((w, h), Image.BICUBIC)
    ).astype(np.float32) / 255
    grano = (0.78 + 0.44 * g)[..., None]

    total = (lavado * 0.95 + borde * 0.55) * grano
    fibra = rng.normal(0, 2.2, (h, w, 1)).astype(np.float32)
    salida = np.clip(papel - total + fibra, 0, 255).astype("uint8")
    return Image.fromarray(salida)


def libreta(titulo, texto):
    cuerpo = html.escape(texto).replace("\n", "<br>")
    return mini(
        f'<div class="libreta"><div class="libreta-titulo">{html.escape(titulo)}</div>'
        f'<div class="libreta-texto">{cuerpo}</div></div>'
    )


def seccion(numero, titulo, variante=""):
    return mini(
        f'<div class="seccion"><span class="num {variante}">{numero}</span>'
        f'<span class="seccion-t">{titulo}</span><span class="seccion-l"></span></div>'
    )


# ---------------------------------------------------------------------------
# Geometría de la paleta (viewBox 300 x 236)
# ---------------------------------------------------------------------------
VB_W, VB_H = 300, 236

# (centro x, centro y, diámetro) de los 6 pigmentos y del botón "+" (índice 6)
POTES = [
    (62, 74, 58),
    (148, 50, 58),
    (236, 74, 58),
    (48, 146, 58),
    (252, 148, 58),
    (112, 190, 58),
    (150, 126, 38),
]


def svg_paleta():
    return mini(f"""
    <svg viewBox="0 0 {VB_W} {VB_H}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <defs>
    <linearGradient id="pal-madera" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="300" y2="236">
    <stop offset="0" stop-color="#F3CE94"/><stop offset=".55" stop-color="#E4AB65"/><stop offset="1" stop-color="#D4944C"/>
    </linearGradient>
    <clipPath id="pal-forma">
    <ellipse cx="150" cy="116" rx="142" ry="104"/>
    <ellipse cx="130" cy="190" rx="82" ry="38"/>
    </clipPath>
    </defs>
    <g fill="#7A4A22" stroke="#7A4A22" stroke-width="9" stroke-linejoin="round">
    <ellipse cx="150" cy="116" rx="142" ry="104"/>
    <ellipse cx="130" cy="190" rx="82" ry="38"/>
    </g>
    <g fill="url(#pal-madera)">
    <ellipse cx="150" cy="116" rx="142" ry="104"/>
    <ellipse cx="130" cy="190" rx="82" ry="38"/>
    </g>
    <g clip-path="url(#pal-forma)" fill="none" stroke-linecap="round">
    <path d="M10 70 C70 54 120 92 180 72 S260 52 296 76" stroke="#C98A47" stroke-opacity=".45" stroke-width="2"/>
    <path d="M6 112 C60 98 110 134 170 114 S250 96 298 120" stroke="#C98A47" stroke-opacity=".4" stroke-width="2"/>
    <path d="M10 160 C70 146 120 180 180 162 S260 148 296 168" stroke="#C98A47" stroke-opacity=".4" stroke-width="2"/>
    <path d="M30 206 C80 196 130 218 190 204 S250 196 280 210" stroke="#C98A47" stroke-opacity=".35" stroke-width="2"/>
    <path d="M28 82 C44 44 96 22 150 20" stroke="#FFF1CF" stroke-opacity=".75" stroke-width="4"/>
    </g>
    </svg>
    """)


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------
def icono(interior):
    interior = interior.replace("<", "%3C").replace(">", "%3E").replace("#", "%23")
    return (
        "url(\"data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E"
        + interior
        + "%3C/svg%3E\")"
    )


ICONOS_HERRAMIENTA = [
    icono(
        "<g stroke='#6B4A2B' stroke-width='3.5' stroke-linecap='round'>"
        "<path d='M8 30 L22 10'/><path d='M16 33 L30 12'/><path d='M24 35 L36 17'/></g>"
    ),
    icono(
        "<g fill='none' stroke='#6B4A2B' stroke-width='3' stroke-linecap='round'>"
        "<rect x='6' y='6' width='28' height='28' rx='4'/><path d='M20 6 V34 M6 20 H34'/></g>"
    ),
    icono(
        "<circle cx='20' cy='20' r='13' fill='none' stroke='#6B4A2B' stroke-width='3'/>"
    ),
]


def css_dinamico():
    reglas = []

    # Pigmentos y botón "+": posición sobre la paleta, color y globo con el nombre
    for i, (cx, cy, d) in enumerate(POTES):
        izq = (cx - d / 2) / VB_W * 100
        arr = (cy - d / 2) / VB_H * 100
        ancho = d / VB_W * 100
        reglas.append(
            f".st-key-pig_{i}{{left:{izq:.2f}%;top:{arr:.2f}%;width:{ancho:.2f}%;}}"
        )
        if i < len(PIGMENTOS):
            nombre, hex_ = PIGMENTOS[i]
            claro = mezcla(hex_, (255, 255, 255), 0.45)
            oscuro = mezcla(hex_, (0, 0, 0), 0.30)
            borde = mezcla(hex_, (0, 0, 0), 0.55)
            reglas.append(
                f".st-key-pig_{i} button{{"
                f"background:radial-gradient(circle at 34% 28%, {claro} 0%, {hex_} 50%, {oscuro} 100%) !important;"
                f"border:3px solid {borde} !important;}}"
            )
        else:
            nombre = "Color personalizado"
        if cx < VB_W * 0.3:
            ancla = "left:0;"
        elif cx > VB_W * 0.7:
            ancla = "right:0;"
        else:
            ancla = "left:50%;transform:translateX(-50%);"
        reglas.append(f'.st-key-pig_{i}::before{{content:"{nombre}";{ancla}}}')

    # Trazos de tiza: grosor y color
    anchos = [3, 6, 10, 15, 21]
    colores = ["#F6D84A", "#F4C430", "#F58A2B", "#E4452B", "#C62828"]
    for i, (px, col) in enumerate(zip(anchos, colores)):
        reglas.append(
            f".st-key-gro_{i} button::after{{width:{px}px;"
            f"background:repeating-linear-gradient(0deg, rgba(255,255,255,.22) 0 2px, transparent 2px 5px), {col};}}"
        )

    # Iconos de herramienta
    for i, url in enumerate(ICONOS_HERRAMIENTA):
        reglas.append(f".st-key-tool_{i} button{{background-image:{url} !important;}}")

    # Selección actual
    reglas.append(
        f".st-key-pig_{st.session_state.pig} button{{"
        "box-shadow:0 0 0 3px #FFF9EC, 0 0 0 6px #F0932B, 0 6px 8px rgba(0,0,0,.3) !important;"
        "transform:scale(1.1) !important;}"
    )
    reglas.append(
        f".st-key-gro_{st.session_state.gro} button, .st-key-tool_{st.session_state.tool} button{{"
        "border:3px solid #F0932B !important;background-color:#FFF3DC !important;}"
    )
    return "<style>" + "\n".join(reglas) + "</style>"


CSS_BASE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Caveat+Brush&family=Fredoka:wght@500;600&family=Kalam:wght@400;700&family=Nunito:wght@400;600;800&display=swap');

:root{
  --papel:#FCF8EC;
  --crema:#F4EBD9;
  --tinta:#1B2F52;
  --tinta-suave:#4A5F82;
  --ultramar:#2E5BBA;
  --cielo:#CFE0F5;
  --turquesa:#2BB5C6;
  --amarillo:#F7C325;
}

html, .stApp{color-scheme:light;}
.stApp{
  background-color:#F4EBD9;
  background-image:
    url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 .35 0 0 0 0 .35 0 0 0 0 .3 0 0 0 .09 0'/%3E%3C/filter%3E%3Crect width='220' height='220' filter='url(%23n)'/%3E%3C/svg%3E"),
    radial-gradient(circle at 0% 100%, rgba(46,91,186,.16), transparent 38%),
    radial-gradient(circle at 100% 0%, rgba(43,181,198,.14), transparent 30%);
  color:var(--tinta);
}
.stApp, .stApp p, .stApp label, .stApp li,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stCaptionContainer"]{
  font-family:'Nunito','Segoe UI',sans-serif;
  color:var(--tinta);
}
[data-testid="stHeader"]{background:transparent;}
.block-container{
  max-width:1400px;
  padding-top:1.4rem;
  padding-right:150px;
}

/* ---------- Barra superior ---------- */
.barra{
  display:flex;
  align-items:center;
  justify-content:space-between;
  background:var(--tinta);
  border-radius:6px;
  padding:14px 22px;
  box-shadow:0 8px 0 -3px rgba(27,47,82,.18);
}
.barra-izq{display:flex;align-items:center;gap:14px;}
.barra-icono{
  width:42px;height:42px;
  display:grid;place-items:center;
  background:var(--amarillo);
  border-radius:50%;
}
.barra-titulo{
  font-family:'Caveat Brush','Kalam',cursive;
  font-size:1.9rem;
  color:#FCF8EC;
  letter-spacing:.5px;
}
.barra-der{
  font-size:.95rem;
  color:#CFE0F5;
  border:1.5px solid var(--amarillo);
  border-radius:4px;
  padding:5px 12px;
}

/* ---------- Hero ---------- */
.hero{display:flex;gap:26px;align-items:flex-start;margin-top:1.4rem;}
.hero-dabs{width:120px;flex:none;height:auto;}
.chip{
  display:inline-block;
  background:var(--amarillo);
  color:var(--tinta);
  border:2px solid var(--tinta);
  font-weight:800;
  font-size:.95rem;
  padding:5px 14px;
  transform:rotate(-1.6deg);
}
.hero h1{
  font-family:'Caveat Brush','Kalam',cursive;
  font-weight:400;
  font-size:4.6rem;
  line-height:.98;
  margin:.6rem 0 .2rem;
  padding:0;
  color:var(--tinta);
}
.hero h1 .l2{color:var(--ultramar);display:block;}
.hero p{font-size:1.1rem;line-height:1.65;max-width:600px;margin:.9rem 0 0;color:var(--tinta-suave);}

.fichas{display:flex;flex-direction:column;gap:14px;margin-top:1.6rem;}
.ficha{
  background:var(--papel);
  border:2px solid var(--tinta);
  padding:10px 16px;
  box-shadow:4px 4px 0 var(--cielo);
}
.ficha:nth-child(1){transform:rotate(.8deg);}
.ficha:nth-child(2){transform:rotate(-.9deg);}
.ficha:nth-child(3){transform:rotate(.6deg);}
.ficha small{display:block;font-size:.8rem;color:var(--tinta-suave);}
.ficha b{display:flex;align-items:center;gap:9px;font-size:1.05rem;}
.punto{display:inline-block;width:14px;height:14px;border-radius:50%;border:2px solid var(--tinta);}

.linea{height:3px;background:var(--tinta);border-radius:2px;margin:1.6rem 0 1.8rem;}

/* ---------- Secciones ---------- */
.seccion{display:flex;align-items:center;gap:14px;margin:0 0 1rem;}
.num{
  width:38px;height:38px;flex:none;
  display:grid;place-items:center;
  border-radius:50%;
  background:var(--ultramar);
  color:#FCF8EC;
  font-weight:800;
}
.num.b{background:var(--turquesa);color:var(--tinta);}
.seccion-t{font-family:'Caveat Brush','Kalam',cursive;font-size:2rem;color:var(--tinta);line-height:1;}
.seccion-l{flex:1;height:3px;background:var(--tinta);border-radius:2px;}

/* ---------- Barra lateral ---------- */
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#F8E8C4,#F4DDA8);
  border-right:2px solid rgba(139,90,43,.28);
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p{color:#5A3A22;}

[class*="st-key-panel_"]{
  background:linear-gradient(180deg,#FDF3DE,#F9EACB);
  border:2px solid #EBD6A8;
  border-radius:20px;
  padding:16px 16px 18px;
  box-shadow:0 3px 0 #E2CB9A, inset 0 2px 0 rgba(255,255,255,.75);
  margin-bottom:6px;
}
.panel-t{
  font-family:'Fredoka','Nunito',sans-serif;
  font-weight:600;
  font-size:1.5rem;
  line-height:1.1;
  color:#5A3A22;
  margin:0 0 .7rem;
}

/* Paleta de pintura */
.st-key-paleta{
  position:relative;
  width:100%;
  aspect-ratio:300/236;
  margin:.1rem 0 .2rem;
  filter:drop-shadow(0 6px 4px rgba(90,58,34,.28));
}
.st-key-paleta_dibujo{position:absolute;top:0;left:0;width:100%;z-index:0;}
.st-key-paleta_dibujo svg{width:100%;height:auto;display:block;}
.st-key-paleta [class*="st-key-pig_"]{position:absolute;z-index:2;}
.st-key-paleta [class*="st-key-pig_"]:hover{z-index:10;}
.st-key-paleta [class*="st-key-pig_"] .stButton{width:100%;}
.st-key-paleta [class*="st-key-pig_"] button{
  width:100%;
  aspect-ratio:1;
  min-height:0;
  height:auto;
  padding:0;
  border-radius:50%;
  position:relative;
  display:flex;
  align-items:center;
  justify-content:center;
  box-shadow:inset 0 -5px 7px rgba(0,0,0,.22), 0 2px 3px rgba(0,0,0,.35);
  transition:transform .12s ease;
}
.st-key-paleta [class*="st-key-pig_"] button p{display:none;}
.st-key-paleta [class*="st-key-pig_"] button::after{
  content:"";
  position:absolute;
  top:14%;left:20%;
  width:34%;height:18%;
  border-radius:50%;
  background:rgba(255,255,255,.65);
  transform:rotate(-28deg);
}
.st-key-paleta [class*="st-key-pig_"] button:hover{transform:scale(1.08) !important;}

/* Botón "+" del centro (color personalizado) */
.st-key-pig_6 button{
  background:radial-gradient(circle at 34% 28%, #FFFDF5, #F6E7C6) !important;
  border:3px solid #8A5A2B !important;
}
.st-key-paleta .st-key-pig_6 button::after{
  content:"+";
  position:static;
  width:auto;height:auto;
  background:none;
  transform:none;
  font-family:'Fredoka','Nunito',sans-serif;
  font-size:1.9rem;
  font-weight:600;
  line-height:1;
  color:#5A3A22;
}

/* Globo con el nombre del pigmento */
.st-key-paleta [class*="st-key-pig_"]::before{
  position:absolute;
  bottom:112%;
  background:#FFF9EC;
  border:2px solid #8A5A2B;
  color:#5A3A22;
  font-family:'Nunito',sans-serif;
  font-weight:800;
  font-size:.85rem;
  padding:3px 11px;
  border-radius:12px;
  white-space:nowrap;
  opacity:0;
  pointer-events:none;
  z-index:20;
  transition:opacity .12s ease;
}
.st-key-paleta [class*="st-key-pig_"]:hover::before{opacity:1;}

/* Trazos de tiza (grosor) */
[class*="st-key-gro_"] .stButton{width:100%;}
[class*="st-key-gro_"] button{
  width:100%;
  height:64px;
  min-height:0;
  padding:0;
  display:flex;
  align-items:center;
  justify-content:center;
  background:transparent !important;
  border:3px solid transparent !important;
  border-radius:12px;
  box-shadow:none !important;
  transform:none !important;
}
[class*="st-key-gro_"] button:hover{background:rgba(240,147,43,.12) !important;}
[class*="st-key-gro_"] button p{display:none;}
[class*="st-key-gro_"] button::after{
  content:"";
  display:block;
  height:46px;
  border-radius:999px;
  transform:rotate(32deg);
}

/* Herramientas */
[class*="st-key-tool_"] .stButton{width:100%;}
[class*="st-key-tool_"] button{
  width:100%;
  height:64px;
  min-height:0;
  padding:0;
  background-color:#F3E3C0 !important;
  background-repeat:no-repeat !important;
  background-position:center !important;
  background-size:36px !important;
  border:2px solid #E3CDA0 !important;
  border-radius:14px;
  box-shadow:none !important;
  transform:none !important;
}
[class*="st-key-tool_"] button:hover{background-color:#F8EBCB !important;}
[class*="st-key-tool_"] button p{display:none;}

/* Botones dibujados a mano */
.stButton > button{
  font-family:'Nunito',sans-serif;
  font-weight:800;
  font-size:1.05rem;
  color:var(--tinta);
  background:var(--papel);
  border:2px solid var(--tinta);
  border-radius:255px 15px 225px 15px / 15px 225px 15px 255px;
  padding:.45rem 1.4rem;
  box-shadow:3px 3px 0 var(--tinta);
  transition:transform .12s ease, box-shadow .12s ease, background .12s ease;
}
.stButton > button:hover{
  background:var(--cielo);
  color:var(--tinta);
  border-color:var(--tinta);
  transform:translate(-1px,-1px);
  box-shadow:4px 4px 0 var(--tinta);
}
.stButton > button:active{transform:translate(2px,2px);box-shadow:1px 1px 0 var(--tinta);}
.st-key-interpretar .stButton > button{
  background:var(--ultramar);
  color:#FCF8EC;
  font-size:1.2rem;
  padding:.6rem 1.8rem;
  box-shadow:4px 4px 0 var(--tinta);
}
.st-key-interpretar .stButton > button p{color:#FCF8EC;}
.st-key-interpretar .stButton > button:hover{background:#3C6BCB;}

/* Campo de clave */
[data-baseweb="input"]{
  background:var(--papel) !important;
  border:2px solid var(--tinta) !important;
  border-radius:8px !important;
}
[data-baseweb="input"] input{background:transparent !important;color:var(--tinta);}

/* ---------- Bloc de acuarela ---------- */
.st-key-bloc{
  position:relative;
  background:#FFFDF5;
  margin-top:26px;
  padding:34px 22px 22px;
  border-radius:6px 6px 16px 16px;
  box-shadow:
    0 1px 0 #E6DCC3,
    8px 8px 0 var(--cielo),
    0 0 0 2px var(--tinta);
}
.st-key-bloc::before{
  content:"";
  position:absolute;
  top:-12px;left:18px;right:18px;
  height:28px;
  background:radial-gradient(circle at 50% 60%, #1B2F52 0 4px, #C9D3E0 5px 7px, transparent 8px) 0 0 / 34px 28px repeat-x;
}
.st-key-bloc iframe{
  border:1px solid rgba(27,47,82,.25);
  border-radius:3px;
  max-width:100%;
  color-scheme:light;
  background:#FCF8EC;
}

/* ---------- Libreta de notas ---------- */
.libreta{
  position:relative;
  background-color:#FFFDF4;
  background-image:repeating-linear-gradient(to bottom, transparent 0, transparent 31px, rgba(70,120,180,.30) 31px, rgba(70,120,180,.30) 32px);
  background-position:0 14px;
  background-repeat:repeat-y;
  padding:14px 20px 22px 74px;
  margin:1.4rem 0 1rem;
  border-radius:4px 10px 10px 4px;
  box-shadow:5px 5px 0 var(--cielo), 0 0 0 2px var(--tinta);
  transform:rotate(.4deg);
  font-family:'Kalam',cursive;
  font-size:1.1rem;
  line-height:32px;
  color:#2B2F6B;
}
.libreta::before{
  content:"";
  position:absolute;
  top:0;bottom:0;left:52px;
  width:2px;
  background:rgba(214,40,57,.5);
}
.libreta::after{
  content:"";
  position:absolute;
  top:0;bottom:0;left:12px;
  width:22px;
  background:radial-gradient(circle at 50% 50%, #F4EBD9 0 8px, rgba(0,0,0,.2) 9px, transparent 10px) 0 28px / 22px 96px repeat-y;
}
.libreta-titulo{
  font-family:'Caveat Brush','Kalam',cursive;
  font-size:1.8rem;
  line-height:32px;
  color:var(--ultramar);
}
.libreta-texto{line-height:32px;}
.libreta-texto, .libreta-titulo{margin:0;}

/* ---------- Decoración fija ---------- */
.gotas{
  position:fixed;
  top:0;right:0;
  width:250px;height:auto;
  pointer-events:none;
  z-index:2;
}
.pincel{
  position:fixed;
  right:8px;
  top:50%;
  transform:translateY(-50%);
  height:88vh;
  width:auto;
  pointer-events:none;
  z-index:2;
  filter:drop-shadow(-4px 6px 6px rgba(27,47,82,.28));
}

@media (max-width:1100px){
  .pincel{display:none;}
  .block-container{padding-right:1.5rem;}
  .hero h1{font-size:3.2rem;}
  .hero-dabs{display:none;}
}
@media (max-width:1500px){
  .barra-der{display:none;}
}
@media (prefers-reduced-motion:reduce){
  .stButton > button, .st-key-paleta [class*="st-key-pig_"] button{transition:none;}
}
</style>
"""

SVG_GOTAS = mini("""
<svg class="gotas" viewBox="0 0 260 270" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<defs>
<filter id="aq" x="-20%" y="-20%" width="140%" height="140%">
<feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="3" seed="4" result="r"/>
<feDisplacementMap in="SourceGraphic" in2="r" scale="9"/>
</filter>
</defs>
<g filter="url(#aq)" style="mix-blend-mode:multiply">
<path d="M172 -10 C204 -2 244 14 262 40 L262 140 C246 150 226 146 214 128 C202 110 178 112 162 98 C140 80 138 52 148 32 C154 16 160 -4 172 -10Z" fill="#2E5BBA" opacity=".9"/>
<path d="M196 130 C196 160 194 190 198 218 C199 230 214 230 215 218 C218 190 214 160 214 128Z" fill="#2E5BBA" opacity=".88"/>
<path d="M70 22 C88 6 118 12 124 34 C130 56 108 70 88 66 C66 62 54 38 70 22Z" fill="#2BB5C6" opacity=".88"/>
<path d="M92 64 C92 82 91 96 94 108 C95 116 105 116 106 108 C108 96 104 82 104 66Z" fill="#2BB5C6" opacity=".88"/>
<path d="M120 120 C134 108 156 114 158 134 C160 152 140 164 124 156 C110 150 108 130 120 120Z" fill="#F7C325" opacity=".92"/>
<circle cx="52" cy="92" r="4" fill="#2BB5C6"/>
<circle cx="132" cy="84" r="3" fill="#2E5BBA"/>
<circle cx="236" cy="176" r="5" fill="#2E5BBA"/>
<circle cx="104" cy="170" r="3.5" fill="#F7C325"/>
<circle cx="170" cy="190" r="2.5" fill="#1B2F52"/>
</g>
</svg>
""")

SVG_PINCEL = mini("""
<svg class="pincel" viewBox="0 0 130 720" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<defs>
<linearGradient id="madera" x1="0" x2="1">
<stop offset="0" stop-color="#E0A862"/><stop offset=".5" stop-color="#B8763A"/><stop offset="1" stop-color="#7C4A22"/>
</linearGradient>
<linearGradient id="metal" x1="0" x2="1">
<stop offset="0" stop-color="#9AA0A6"/><stop offset=".35" stop-color="#F4F4F2"/><stop offset=".7" stop-color="#B4B9BD"/><stop offset="1" stop-color="#7D8388"/>
</linearGradient>
<linearGradient id="cerda" x1="0" x2="1">
<stop offset="0" stop-color="#5A3A24"/><stop offset=".5" stop-color="#8A5A3A"/><stop offset="1" stop-color="#4A2F1D"/>
</linearGradient>
<filter id="aq2" x="-30%" y="-10%" width="160%" height="120%">
<feTurbulence type="fractalNoise" baseFrequency="0.05" numOctaves="3" seed="9" result="r"/>
<feDisplacementMap in="SourceGraphic" in2="r" scale="7"/>
</filter>
</defs>
<g transform="rotate(7 65 360)">
<path d="M56 24 C56 8 74 8 74 24 C79 120 88 230 80 346 L50 346 C42 230 51 120 56 24Z" fill="url(#madera)"/>
<path d="M62 40 C66 120 70 220 66 340" stroke="#7C4A22" stroke-width=".9" fill="none" opacity=".5"/>
<path d="M69 44 C73 120 78 220 74 336" stroke="#F0C48A" stroke-width=".8" fill="none" opacity=".45"/>
<circle cx="65" cy="26" r="3.5" fill="#4A2A12"/>
<path d="M55 72 Q65 78 76 72" stroke="#2E5BBA" stroke-width="5" fill="none" stroke-linecap="round"/>
<path d="M55 84 Q66 90 77 84" stroke="#F7C325" stroke-width="5" fill="none" stroke-linecap="round"/>
<path d="M56 96 Q67 102 78 96" stroke="#2BB5C6" stroke-width="5" fill="none" stroke-linecap="round"/>
<path d="M50 346 L80 346 L84 408 L46 408Z" fill="url(#metal)"/>
<path d="M49 362 L81 362" stroke="#6D7378" stroke-width="1.5"/>
<path d="M48 376 L82 376" stroke="#6D7378" stroke-width="1.5"/>
<path d="M46 408 L84 408" stroke="#5E6368" stroke-width="3"/>
<path d="M46 408 L84 408 C88 448 78 492 66 540 C65 546 63 546 62 540 C50 492 42 448 46 408Z" fill="url(#cerda)"/>
<path d="M52 478 C58 490 72 490 78 478 C74 510 70 530 65 548 C60 530 54 510 52 478Z" fill="#2BB5C6"/>
<g filter="url(#aq2)">
<path d="M64 548 C26 580 104 610 56 644 S84 692 50 716" fill="none" stroke="#2BB5C6" stroke-width="16" stroke-linecap="round" opacity=".92"/>
<path d="M64 552 C34 584 96 614 60 640" fill="none" stroke="#2E5BBA" stroke-width="6" stroke-linecap="round" opacity=".75"/>
<path d="M70 560 C96 586 52 614 82 650" fill="none" stroke="#F7C325" stroke-width="5" stroke-linecap="round" opacity=".85"/>
<path d="M58 660 C40 676 70 690 56 708" fill="none" stroke="#6B3FA0" stroke-width="5" stroke-linecap="round" opacity=".75"/>
</g>
<circle cx="98" cy="556" r="4" fill="#2BB5C6"/>
<circle cx="26" cy="598" r="3" fill="#2E5BBA"/>
<circle cx="104" cy="628" r="3.5" fill="#F7C325"/>
<circle cx="22" cy="660" r="2.5" fill="#6B3FA0"/>
</g>
</svg>
""")

SVG_DABS = mini("""
<svg class="hero-dabs" viewBox="0 0 120 150" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<g style="mix-blend-mode:multiply">
<path d="M18 40 C14 14 44 2 64 12 C86 22 92 50 76 66 C60 80 24 72 18 40Z" fill="#2E5BBA"/>
<path d="M54 56 C54 40 78 36 92 48 C106 60 100 84 82 90 C64 94 54 74 54 56Z" fill="#F7C325"/>
<path d="M10 100 C16 84 40 82 52 94 C64 106 58 128 40 134 C22 138 6 118 10 100Z" fill="#2BB5C6"/>
</g>
</svg>
""")

st.markdown(CSS_BASE, unsafe_allow_html=True)
st.markdown(css_dinamico(), unsafe_allow_html=True)
st.markdown(SVG_GOTAS + SVG_PINCEL, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Barra lateral: paleta y herramientas
# ---------------------------------------------------------------------------
with st.sidebar:
    with st.container(key="panel_color"):
        st.markdown('<div class="panel-t">Color de pintura</div>', unsafe_allow_html=True)
        with st.container(key="paleta"):
            with st.container(key="paleta_dibujo"):
                st.markdown(svg_paleta(), unsafe_allow_html=True)
            for i, (nombre, _) in enumerate(PIGMENTOS):
                with st.container(key=f"pig_{i}"):
                    st.button(nombre, key=f"btn_pig_{i}", on_click=elegir_pigmento, args=(i,))
            with st.container(key="pig_6"):
                st.button("Color personalizado", key="btn_pig_6", on_click=elegir_pigmento, args=(6,))
        if st.session_state.pig == 6:
            st.session_state.custom_hex = st.color_picker(
                "Color personalizado",
                value=st.session_state.custom_hex,
                key="selector_personalizado",
            )

    with st.container(key="panel_grosor"):
        st.markdown('<div class="panel-t">Grosor del pincel</div>', unsafe_allow_html=True)
        cols_grosor = st.columns(5, gap="small")
        for i, (nombre, _) in enumerate(GROSORES):
            with cols_grosor[i]:
                with st.container(key=f"gro_{i}"):
                    st.button(nombre, key=f"btn_gro_{i}", help=nombre,
                              on_click=elegir_grosor, args=(i,))

    with st.container(key="panel_herramienta"):
        st.markdown('<div class="panel-t">Herramienta</div>', unsafe_allow_html=True)
        cols_tool = st.columns(3, gap="small")
        for i, nombre in enumerate(HERRAMIENTAS):
            with cols_tool[i]:
                with st.container(key=f"tool_{i}"):
                    st.button(nombre, key=f"btn_tool_{i}", help=nombre,
                              on_click=elegir_herramienta, args=(i,))

    with st.container(key="panel_ajustes"):
        st.markdown('<div class="panel-t">Ajustes</div>', unsafe_allow_html=True)
        intensidad = st.slider("Intensidad del pigmento", 20, 100, 70, format="%d%%")
        goma = st.toggle("Goma de borrar")
        if st.button("Lienzo nuevo"):
            st.session_state.lienzo += 1
            st.session_state.nota = ""
            st.session_state.historia = ""
            st.session_state.acuarela = None

herramienta = list(HERRAMIENTAS)[st.session_state.tool]

# ---------------------------------------------------------------------------
# Encabezado: barra, hero y fichas
# ---------------------------------------------------------------------------
if st.session_state.pig == 6:
    pig_nombre, pig_hex = "Color personalizado", st.session_state.custom_hex
else:
    pig_nombre, pig_hex = PIGMENTOS[st.session_state.pig]
gro_nombre, gro_px = GROSORES[st.session_state.gro]

st.markdown(
    mini("""
    <div class="barra">
    <div class="barra-izq">
    <span class="barra-icono">
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 C12 2 5 10 5 15 a7 7 0 0 0 14 0 C19 10 12 2 12 2Z" fill="#1B2F52"/></svg>
    </span>
    <span class="barra-titulo">Taller de arte</span>
    </div>
    <div class="barra-der">Modelo GPT-4o mini · respuesta en español</div>
    </div>
    """),
    unsafe_allow_html=True,
)

col_hero, col_fichas = st.columns([2.3, 1], gap="large")
with col_hero:
    st.markdown(
        mini(f"""
        <div class="hero">
        {SVG_DABS}
        <div>
        <span class="chip">Taller de dibujo con visión de IA</span>
        <h1>Dibuja lo que quieras.<span class="l2">La máquina lo interpretará.</span></h1>
        <p>Elige un pigmento en la paleta de la izquierda, pinta sobre el bloc y pulsa
        Interpretar. La máquina describe tu dibujo en una libreta y te lo devuelve con acabado de acuarela.</p>
        </div>
        </div>
        """),
        unsafe_allow_html=True,
    )
with col_fichas:
    st.markdown(
        mini(f"""
        <div class="fichas">
        <div class="ficha"><small>Pigmento</small><b><span class="punto" style="background:{pig_hex}"></span>{pig_nombre}</b></div>
        <div class="ficha"><small>Pincel</small><b>{gro_nombre} · {gro_px} px</b></div>
        <div class="ficha"><small>Herramienta</small><b>{"Goma de borrar" if goma else herramienta}</b></div>
        </div>
        """),
        unsafe_allow_html=True,
    )

st.markdown('<div class="linea"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Dos secciones: lienzo y interpretación
# ---------------------------------------------------------------------------
col_lienzo, col_analisis = st.columns([1.65, 1], gap="large")

r, g, b = hex_a_rgb(pig_hex)
if goma:
    trazo = f"rgba({PAPEL[0]},{PAPEL[1]},{PAPEL[2]},1)"
    relleno = trazo
    ancho = gro_px * 1.6
else:
    alfa = intensidad / 100
    trazo = f"rgba({r},{g},{b},{alfa})"
    relleno = f"rgba({r},{g},{b},{alfa * 0.35})"
    ancho = gro_px

with col_lienzo:
    st.markdown(seccion(1, "Lienzo"), unsafe_allow_html=True)
    with st.container(key="bloc"):
        lienzo = st_canvas(
            fill_color=relleno,
            stroke_width=ancho,
            stroke_color=trazo,
            background_color=PAPEL_HEX,
            height=460,
            width=660,
            drawing_mode=HERRAMIENTAS[herramienta],
            key=f"lienzo_{st.session_state.lienzo}",
        )

with col_analisis:
    st.markdown(seccion(2, "Interpretación", "b"), unsafe_allow_html=True)
    ke = st.text_input("Clave de OpenAI", type="password")
    api_key = ke or os.environ.get("OPENAI_API_KEY", "")

    with st.container(key="interpretar"):
        interpretar = st.button("Interpretar mi dibujo")

    if interpretar:
        if not api_key:
            st.warning("Ingresa tu clave de OpenAI para interpretar el dibujo.")
        elif lienzo.image_data is None:
            st.info("El lienzo todavía no está listo. Intenta de nuevo en un momento.")
        else:
            imagen = imagen_del_lienzo(lienzo.image_data)
            if lienzo_en_blanco(imagen):
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
                        st.session_state.acuarela = acuarela(imagen)
                        st.session_state.historia = ""
                    except Exception as e:
                        st.error(f"No se pudo interpretar el dibujo: {e}")

    if st.session_state.nota:
        st.markdown(libreta("Notas del taller", st.session_state.nota), unsafe_allow_html=True)

        if st.session_state.acuarela is not None:
            st.image(st.session_state.acuarela, caption="Tu dibujo con acabado de acuarela")

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

        if st.session_state.historia:
            st.markdown(libreta("Cuento del taller", st.session_state.historia), unsafe_allow_html=True)
