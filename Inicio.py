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
# CONSTANTES Y PALETA DE COLORES (Inspirado en el portafolio)
# ---------------------------------------------------------------------------
AZUL_MARINO = "#1A2A44"  # Para títulos y textos oscuros
CREMA_FONDO = "#FCF8F2"  # Fondo general de la app
CREMA_PANEL = "#FFFDF8"  # Fondo de las tarjetas y paneles
CREMA_OSCURO = "#E8DCC8" # Bordes y sombras
MADERA_MESA = "#D4B895"  # Color de la mesa de trabajo
ROJO_ACENTO = "#D45A4A"  # Para el botón de interpretar
NARANJA_SEL = "#E8912D"  # Marco de selección

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
COLORES_PAPEL = [("Hueso", "#EDE5D1"), ("Crema", "#FCF8EC"), ("Blanco", "#FFFFFF"), ("Kraft", "#E5D2AC")]
MESAS = [("Nogal claro", "#C99A62"), ("Roble", "#D9B27C"), ("Cerezo", "#A8683F")]
ACABADOS = ["Acuarela", "Tiza"]

st.set_page_config(
    page_title="Espacio creativo para dibujar",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# ESTADO DE LA SESIÓN
# ---------------------------------------------------------------------------
for clave, valor in {
    "lienzo": 0, "nota": "", "historia": "", "vista": None,
    "pig": 0, "gro": 2, "tool": 0, "papel": 1,
    "papel_color": 1, "mesa": 1, "acabado": 0, "custom_hex": "#E873A5",
}.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor

def elegir(clave, valor):
    st.session_state[clave] = valor

def boton(etiqueta, **kw):
    try:
        return st.button(etiqueta, width="stretch", **kw)
    except TypeError:
        return st.button(etiqueta, use_container_width=True, **kw)

# ---------------------------------------------------------------------------
# UTILIDADES DE IMAGEN
# ---------------------------------------------------------------------------
def mini(texto):
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

# ---------------------------------------------------------------------------
# SVG DE FONDO (Mesa de trabajo)
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

def svg_madera(base):
    azar = random.Random(5)
    oscuro = mezcla(base, (92, 54, 22), 0.55)
    trazos = ""
    for _ in range(90):
        x = azar.randint(10, 680)
        y = azar.randint(10, 440)
        largo = azar.randint(60, 190)
        ond = azar.randint(3, 7)
        d = f"M{x} {y}"
        for _s in range(3):
            d += f" c{largo // 6} {-ond},{largo // 3} {ond},{largo // 3} 0"
        trazos += (
            f'<path d="{d}" stroke="{oscuro}" stroke-width="{azar.choice([2, 3, 4, 5])}" '
            f'stroke-opacity="{azar.choice([.28, .4, .55])}" fill="none" stroke-linecap="round"/>'
        )
    return envolver(700, 460, trazos)

SVG_TUBOS = envolver(300, 230, tubo(100, 100, -40, "#F5C02A") + tubo(205, 82, 30, "#3EAF5C", 0.95))
SVG_SPLAT = envolver(150, 150, salpicadura(75, 75, "#F28A2E", [(-34, -30), (34, -34), (40, 26), (-30, 34)], 15, 18, [(20, 120, 6), (130, 30, 6)]))

ANILLAS = uri(
    '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="32" viewBox="0 0 64 32">'
    '<circle cx="9" cy="16" r="3.6" fill="#2A1C10" opacity=".6"/>'
    '<circle cx="55" cy="16" r="3.6" fill="#2A1C10" opacity=".6"/>'
    '<g transform="rotate(-8 32 16)">'
    '<ellipse cx="32" cy="16" rx="28" ry="5.5" fill="none" stroke="#6F7885" stroke-width="3.4"/>'
    '<ellipse cx="32" cy="14.8" rx="28" ry="5.5" fill="none" stroke="#EEF1F6" stroke-width="1.3"/>'
    '</g></svg>'
)

@st.cache_data(show_spinner=False)
def css_fondo(mesa_hex):
    capas = [
        (SVG_SPLAT, "10% 5%", "auto 10vh"),
        (SVG_TUBOS, "85% 15%", "auto 20vh"),
        (SVG_SPLAT, "90% 80%", "auto 12vh"),
        (SVG_TUBOS, "5% 85%", "auto 18vh"),
    ]
    imagenes = [uri(c[0]) for c in capas] + [uri(svg_madera(mesa_hex))]
    repeticion = ["no-repeat"] * len(capas) + ["repeat"]
    posiciones = [c[1] for c in capas] + ["0 0"]
    tamanos = [c[2] for c in capas] + ["700px 460px"]
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
# CSS DINÁMICO
# ---------------------------------------------------------------------------
def css_dinamico(pig_hex):
    reglas = []
    papel_hex = COLORES_PAPEL[st.session_state.papel_color][1]

    for i, slot in enumerate(SLOTS):
        if slot is None: continue
        hex_ = slot[1]
        claro = mezcla(hex_, (255, 255, 255), 0.5)
        oscuro = mezcla(hex_, (0, 0, 0), 0.28)
        reglas.append(f".st-key-pig_{i} button{{background:radial-gradient(circle at 36% 30%, {claro} 0%, {hex_} 52%, {oscuro} 100%) !important;}}")

    for i, px in enumerate([3, 6, 10, 15, 22]):
        reglas.append(
            f".st-key-gro_{i} button::after{{width:{px}px;"
            "background:repeating-linear-gradient(72deg, rgba(255,255,255,.30) 0 2px, transparent 2px 5px), "
            f"{pig_hex};}}"
        )

    reglas.append(".st-key-pap_0 button{background:#FFFDF5 !important;}")
    reglas.append(".st-key-pap_1 button{background:repeating-linear-gradient(to bottom, transparent 0 9px, rgba(15,43,91,.4) 9px 10px), #FFFDF5 !important;}")
    reglas.append(".st-key-pap_2 button{background:linear-gradient(rgba(15,43,91,.34) 1px, transparent 1px) 0 0 / 12px 12px, linear-gradient(90deg, rgba(15,43,91,.34) 1px, transparent 1px) 0 0 / 12px 12px, #FFFDF5 !important;}")
    reglas.append(".st-key-pap_3 button{background:radial-gradient(circle, rgba(15,43,91,.62) 1.4px, transparent 1.8px) 0 0 / 11px 11px, #FFFDF5 !important;}")
    
    for i, (_, hex_) in enumerate(COLORES_PAPEL):
        reglas.append(f".st-key-pcol_{i} button{{background:{hex_} !important;}}")
    for i, (_, hex_) in enumerate(MESAS):
        reglas.append(f".st-key-mesa_{i} button{{background:{hex_} !important;}}")

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

    sel_pig = st.session_state.pig
    giro = "" if sel_pig == IDX_PERSONALIZADO else "rotate(-45deg) "
    reglas.append(f".st-key-pig_{sel_pig} button{{box-shadow:0 0 0 3px #FFF6DD, 0 0 0 6px {NARANJA_SEL}, 0 6px 8px rgba(0,0,0,.3) !important;transform:{giro}scale(1.1) !important;}}")
    reglas.append(f".st-key-gro_{st.session_state.gro} button{{background:#FFF1D2 !important;border:3px solid {NARANJA_SEL} !important;}}")
    reglas.append(
        f".st-key-tool_{st.session_state.tool} button, .st-key-fin_{st.session_state.acabado} button{{background:{AZUL_MARINO} !important;}}"
        f".st-key-tool_{st.session_state.tool} button p, .st-key-fin_{st.session_state.acabado} button p{{color:#FFF6DD !important;}}"
    )
    reglas.append(
        f".st-key-pap_{st.session_state.papel} button, .st-key-pcol_{st.session_state.papel_color} button, .st-key-mesa_{st.session_state.mesa} button{{"
        f"border:3px solid {NARANJA_SEL} !important; box-shadow:0 0 0 3px #FFF6DD, 0 0 0 5px {NARANJA_SEL} !important;}}"
    )
    return "<style>" + "\n".join(reglas) + "</style>"

# ---------------------------------------------------------------------------
# CSS BASE (Estilo Portafolio: Elegante, Creativo, Infantil)
# ---------------------------------------------------------------------------
CSS_BASE = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,700;1,500;1,700&family=Quicksand:wght@400;500;600;700&display=swap');

:root {{
  --azul: {AZUL_MARINO};
  --crema: {CREMA_PANEL};
  --crema-fondo: {CREMA_FONDO};
  --crema-oscuro: {CREMA_OSCURO};
  --rojo: {ROJO_ACENTO};
}}

html, .stApp {{ color-scheme: light; }}
[data-testid="stAppViewContainer"], [data-testid="stMain"], .main {{ background: transparent !important; }}

/* Tipografía general */
.stApp, .stApp p, .stApp label, .stApp li, .stApp [data-testid="stMarkdownContainer"] {{
  font-family: 'Quicksand', sans-serif;
  color: var(--azul);
}}
.stApp label p {{ font-weight: 600; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ max-width: 1400px; padding-top: 2rem; padding-bottom: 5rem; }}

/* --- BARRA LATERAL (Paleta y controles) --- */
[data-testid="stSidebar"][aria-expanded="true"] {{
  min-width: 440px !important;
  width: 440px !important;
}}
[data-testid="stSidebar"] {{
  background: var(--crema-fondo);
  border-right: 2px solid var(--crema-oscuro);
}}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding: 1.5rem 2rem; }}

/* Títulos de sección */
.sidebar-title {{
  font-family: 'Playfair Display', serif;
  font-weight: 700;
  font-size: 1.8rem;
  color: var(--azul);
  margin: 0 0 1.5rem 0;
  border-bottom: 2px solid var(--crema-oscuro);
  padding-bottom: 0.5rem;
}}
.panel-t {{
  font-family: 'Playfair Display', serif;
  font-weight: 700;
  font-size: 1.3rem;
  color: var(--azul);
  margin: 1.5rem 0 0.8rem 0;
}}
.panel-s {{ font-weight: 600; font-size: 1rem; margin: 1rem 0 0.5rem 0; color: var(--azul); }}

/* --- PALETA DE PINTOR REAL --- */
.st-key-paleta {{
  background:
    radial-gradient(ellipse at 30% 25%, rgba(255,255,255,0.4) 0%, transparent 60%),
    repeating-linear-gradient(100deg, rgba(150,95,40,.1) 0 2px, transparent 2px 9px),
    linear-gradient(135deg, #E8C99B, #D4B895);
  border: 4px solid #B08D6A;
  border-radius: 60% 40% 50% 50% / 50% 60% 40% 50%;
  padding: 60px 50px 90px;
  gap: 1.5rem !important;
  box-shadow: inset 0 4px 0 rgba(255,255,255,.5), 0 15px 20px -8px rgba(70,45,15,.6);
  position: relative;
  margin-bottom: 2rem;
}}
.st-key-paleta::after {{
  content: "";
  position: absolute;
  right: 18%; bottom: 12%;
  width: 60px; height: 70px;
  border-radius: 50%;
  background: #E8C99B;
  border: 3px solid #B08D6A;
  box-shadow: inset 4px 5px 8px rgba(70,45,15,.6);
}}
.st-key-paleta [data-testid="stHorizontalBlock"] {{ gap: 2rem !important; }}

/* Gotas de pintura */
[class*="st-key-pig_"] [data-testid="stButton"], [class*="st-key-pig_"] .stButton {{ width: 100% !important; display: flex; justify-content: center; }}
.st-key-pig_0, .st-key-pig_2 {{ margin-top: 15px; }}
.st-key-pig_6, .st-key-pig_8 {{ margin-top: -15px; }}
[class*="st-key-pig_"] button {{
  width: 65px !important; height: 65px !important;
  border-radius: 50% 0 50% 50% !important;
  transform: rotate(-45deg);
  box-shadow: inset -3px -4px 0 rgba(0,0,0,.2), 0 0 0 2px rgba(26,42,68,.5) !important;
  border: none !important;
  position: relative; padding: 0 !important;
  transition: transform .2s ease;
}}
[class*="st-key-pig_"] button p {{ font-size: 0; }}
[class*="st-key-pig_"] button::after {{
  content: ""; position: absolute; top: 22%; left: 30%;
  width: 30%; height: 15%; border-radius: 50%;
  background: rgba(255,255,255,.6); transform: rotate(45deg);
}}
[class*="st-key-pig_"] button:hover {{ transform: rotate(-45deg) scale(1.1) !important; }}

/* Extras */
.st-key-extras [data-testid="stHorizontalBlock"] {{ gap: 1rem !important; }}
.st-key-extras [class*="st-key-pig_"] button {{ width: 42px !important; height: 42px !important; }}

/* Botón + */
.st-key-pig_4 button {{
  background: var(--crema) !important; border: 3px dashed #B08D6A !important;
  border-radius: 50% !important; transform: none !important;
  display: flex; align-items: center; justify-content: center;
}}
.st-key-pig_4 button::after {{ content: "+"; font-family: 'Playfair Display', serif; font-size: 2.5rem; color: var(--azul); background: none; position: static; transform: none; width: auto; height: auto; }}

/* Grosor de tiza */
[class*="st-key-gro_"] button {{
  background: transparent !important; border: 2px solid transparent !important;
  border-radius: 12px !important; height: 70px !important;
}}
[class*="st-key-gro_"] button:hover {{ background: rgba(26,42,68,0.05) !important; }}
[class*="st-key-gro_"] button::after {{ content: ""; display: block; height: 45px; border-radius: 999px; transform: rotate(30deg); }}

/* Píldoras (Herramientas y Acabados) */
[class*="st-key-tool_"] button, [class*="st-key-fin_"] button {{
  width: 100% !important; height: 48px !important;
  background: var(--crema) !important; border: 2px solid var(--azul) !important;
  border-radius: 999px; box-shadow: none !important;
}}
[class*="st-key-tool_"] button p, [class*="st-key-fin_"] button p {{
  font-family: 'Quicksand', sans-serif; font-weight: 700; font-size: 1rem; color: var(--azul);
}}
[class*="st-key-tool_"] button:hover, [class*="st-key-fin_"] button:hover {{ background: #FFF0E0 !important; }}

/* Muestras de Papel y Mesa */
[class*="st-key-pap_"] button {{ width: 100% !important; height: 60px !important; border-radius: 12px !important; border: 2px solid rgba(26,42,68,.3) !important; }}
[class*="st-key-pcol_"] button, [class*="st-key-mesa_"] button {{ width: 50px !important; height: 50px !important; border-radius: 50% !important; border: 2px solid var(--azul) !important; }}
[class*="st-key-pap_"] button p, [class*="st-key-pcol_"] button p, [class*="st-key-mesa_"] button p {{ font-size: 0; }}

/* --- CUADERNO ABIERTO (Lienzo) --- */
.st-key-hoja {{
  max-width: 1000px;
  margin: 0 auto 2rem;
  background: var(--crema-fondo);
  border-radius: 20px;
  padding: 40px;
  box-shadow: 0 20px 40px -15px rgba(0,0,0,0.3), inset 0 2px 0 rgba(255,255,255,0.8);
  border: 1px solid var(--crema-oscuro);
  position: relative;
}}
.titulo-principal {{
  font-family: 'Playfair Display', serif;
  font-size: 3rem;
  font-weight: 700;
  color: var(--azul);
  text-align: center;
  margin-bottom: 0.5rem;
  font-style: italic;
}}
.subtitulo {{
  font-family: 'Quicksand', sans-serif;
  font-size: 1.2rem;
  color: var(--azul);
  text-align: center;
  font-weight: 500;
  margin-bottom: 2.5rem;
  opacity: 0.8;
}}

.st-key-paginas {{
  background-color: #FFFFFF;
  padding: 30px;
  border-radius: 8px;
  box-shadow: 0 2px 0 #E8DCC8, 0 4px 0 #D4C5AD, 0 6px 0 #E8DCC8, 0 8px 0 #D4C5AD, 0 15px 25px -10px rgba(0,0,0,0.4);
  position: relative;
  margin: 0 10px;
}}
/* Espiral del cuaderno */
.st-key-paginas::before {{
  content: ""; position: absolute; top: -10px; bottom: -10px; left: calc(50% - 32px);
  width: 64px; background-repeat: repeat-y; background-size: 64px 32px; z-index: 10; pointer-events: none;
}}
.st-key-paginas::after {{
  content: ""; position: absolute; inset: 0;
  background: linear-gradient(90deg, rgba(0,0,0,0) 0%, rgba(0,0,0,.03) 40%, rgba(0,0,0,.08) 50%, rgba(0,0,0,.03) 60%, rgba(0,0,0,0) 100%);
  pointer-events: none; border-radius: 8px;
}}

/* --- TARJETA DE ACCIONES Y RESULTADOS --- */
.st-key-acciones, .st-key-resultados {{
  max-width: 1000px;
  margin: 0 auto 2rem;
  background: var(--crema-panel);
  border: 2px solid var(--crema-oscuro);
  border-radius: 20px;
  padding: 25px 30px;
  box-shadow: 0 10px 25px -10px rgba(0,0,0,0.15);
}}

/* Botones generales (Azul con blanco) */
.stButton > button {{
  font-family: 'Quicksand', sans-serif; font-weight: 700; font-size: 1.05rem;
  color: white !important; background: var(--azul) !important;
  border: none; border-radius: 999px; padding: 0.6rem 1.5rem;
  transition: transform 0.2s ease, opacity 0.2s ease;
}}
.stButton > button p {{ color: white !important; }}
.stButton > button:hover {{ transform: translateY(-2px); opacity: 0.9; color: white !important; }}
.st-key-interpretar .stButton > button {{ background: var(--rojo) !important; }}
.st-key-interpretar .stButton > button:hover {{ background: #C04737 !important; }}

[data-baseweb="input"] {{ background: var(--crema-fondo) !important; border: 2px solid var(--azul) !important; border-radius: 12px !important; }}
[data-baseweb="input"] input {{ color: var(--azul) !important; font-family: 'Quicksand', sans-serif; }}

/* --- LIBRETA DE NOTAS (Cuadro de texto con contraste) --- */
.libreta {{
  background-color: #FFF6E5;
  background-image: repeating-linear-gradient(to bottom, transparent 0, transparent 31px, rgba(26,42,68,.15) 31px, rgba(26,42,68,.15) 32px);
  background-position: 0 15px;
  padding: 20px 25px 30px 75px;
  border-radius: 8px 16px 16px 8px;
  box-shadow: 2px 5px 15px rgba(0,0,0,.08);
  font-family: 'Quicksand', sans-serif;
  font-size: 1.05rem;
  line-height: 32px;
  color: var(--azul);
  border-left: 4px solid #E8C99B;
  position: relative;
  margin-bottom: 1.5rem;
}}
.libreta::before {{
  content: ""; position: absolute; top: 0; bottom: 0; left: 50px;
  width: 2px; background: rgba(212, 90, 74, 0.4);
}}
.libreta::after {{
  content: ""; position: absolute; top: 0; bottom: 0; left: 12px; width: 22px;
  background: radial-gradient(circle at 50% 50
