import base64
import html
import io
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
AZUL = "#0A4AAE"
AMARILLO = "#FDB92D"
MORADO = "#6A4FA8"
VERDE = "#7FBC7B"
CREMA = "#FDF8EA"

PIGMENTOS = [
    ("Rojo", "#F0392B"),
    ("Azul", "#0A4AAE"),
    ("Verde", "#7FBC7B"),
    ("Morado", "#6A4FA8"),
    ("Naranja", "#F28C28"),
    ("Rosa", "#E873A5"),
    ("Celeste", "#4FB3E8"),
    ("Negro", "#1E1B1A"),
]
IDX_PERSONALIZADO = 8  # el botón "+"

GROSORES = [("Muy fino", 2), ("Fino", 5), ("Medio", 10), ("Grueso", 18), ("Brocha", 32)]

HERRAMIENTAS = {
    "Pincel libre": "freedraw",
    "Rectángulo": "rect",
    "Círculo": "circle",
}
ETIQUETA_HERRAMIENTA = ["Pincel", "Cuadro", "Círculo"]

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
# Estilos
# ---------------------------------------------------------------------------
RADIOS_MANCHA = [
    "54% 46% 58% 42% / 48% 56% 44% 52%",
    "46% 54% 42% 58% / 56% 44% 56% 44%",
    "58% 42% 52% 48% / 44% 58% 42% 56%",
    "44% 56% 48% 52% / 54% 46% 58% 42%",
]


def css_dinamico():
    reglas = []

    # Cada pigmento es una mancha de pintura plana con forma distinta
    for i, (_, hex_) in enumerate(PIGMENTOS):
        radio = RADIOS_MANCHA[i % len(RADIOS_MANCHA)]
        reglas.append(
            f".st-key-pig_{i} button{{background:{hex_} !important;border-radius:{radio} !important;}}"
        )

    # Barras de grosor
    for i, px in enumerate([3, 6, 10, 16, 24]):
        reglas.append(f".st-key-gro_{i} button::after{{height:{px}px;}}")

    # Selección actual
    reglas.append(
        f".st-key-pig_{st.session_state.pig} button{{"
        f"box-shadow:0 0 0 3px #FFFBEF, 0 0 0 7px {AZUL} !important;"
        "transform:scale(1.08) !important;}"
    )
    reglas.append(
        f".st-key-gro_{st.session_state.gro} button{{"
        f"background:#FFE7A3 !important;border:3px solid {AZUL} !important;}}"
    )
    reglas.append(
        f".st-key-tool_{st.session_state.tool} button{{"
        f"background:{AZUL} !important;border-color:{AZUL} !important;}}"
        f".st-key-tool_{st.session_state.tool} button p{{color:#FFFBEF !important;}}"
    )
    return "<style>" + "\n".join(reglas) + "</style>"


CSS_BASE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Delicious+Handrawn&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Caveat:wght@600&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Kalam:wght@400;700&display=swap');

:root{
  --crema:#FDF8EA;
  --papel:#FFFBEF;
  --azul:#0A4AAE;
  --azul-osc:#063276;
  --amarillo:#FDB92D;
  --morado:#6A4FA8;
  --verde:#7FBC7B;
  --texto:#16315E;
}

html, .stApp{color-scheme:light;}
.stApp{background:var(--crema);color:var(--texto);}
.stApp, .stApp p, .stApp label, .stApp li,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stCaptionContainer"]{
  font-family:'Nunito','Segoe UI',sans-serif;
  color:var(--texto);
}
[data-testid="stHeader"]{background:transparent;}
.block-container{
  max-width:1400px;
  padding-top:1rem;
  padding-right:150px;
}

/* ---------- Banner con manchas ---------- */
.banner{width:100%;height:auto;display:block;}
.lema{
  font-family:'Caveat','Delicious Handrawn',cursive;
  font-weight:600;
  font-size:2rem;
  text-align:center;
  color:var(--azul);
  margin:.2rem 0 1.4rem;
}

/* ---------- Secciones ---------- */
.seccion{display:flex;align-items:center;gap:14px;margin:0 0 1.1rem;}
.num{
  width:42px;height:42px;flex:none;
  display:grid;place-items:center;
  border-radius:50%;
  background:var(--azul);
  color:#FFFBEF;
  font-weight:800;
  font-size:1.2rem;
}
.num.b{background:var(--morado);}
.seccion-t{
  font-family:'Delicious Handrawn','Caveat Brush',cursive;
  font-size:2.3rem;
  color:var(--azul);
  line-height:1;
}
.seccion-l{flex:1;height:4px;background:var(--amarillo);border-radius:4px;}

/* ---------- Barra lateral ---------- */
[data-testid="stSidebar"][aria-expanded="true"]{
  min-width:400px !important;
  width:400px !important;
}
[data-testid="stSidebar"]{
  background:#F6EBCB;
  border-right:3px solid var(--azul);
}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{
  padding:1rem .9rem;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p{color:var(--texto);}

[class*="st-key-panel_"]{
  background:var(--papel);
  border:3px solid var(--azul);
  border-radius:24px;
  padding:16px 16px 18px;
  box-shadow:5px 5px 0 var(--amarillo);
  margin-bottom:16px;
}
.panel-t{
  font-family:'Delicious Handrawn','Caveat Brush',cursive;
  font-size:2rem;
  line-height:1.1;
  color:var(--azul);
  margin:0 0 .8rem;
}

/* Paleta de pintura plana (como la de tu referencia) */
.st-key-paleta{
  position:relative;
  background:var(--amarillo);
  border-radius:48% 52% 50% 50% / 56% 52% 48% 44%;
  padding:46px 26px 30px;
  margin:.2rem 0 .6rem;
  transform:rotate(-3deg);
}
.st-key-paleta::before{
  content:"";
  position:absolute;
  top:14px;right:22%;
  width:54px;height:26px;
  border-radius:50%;
  background:var(--papel);
  transform:rotate(-12deg);
}
[class*="st-key-pig_"] [data-testid="stButton"],
[class*="st-key-pig_"] .stButton{
  width:100% !important;
  display:flex;
  justify-content:center;
}
[class*="st-key-pig_"] button{
  width:100% !important;
  max-width:84px;
  aspect-ratio:1;
  height:auto !important;
  min-height:0 !important;
  padding:0 !important;
  border:0 !important;
  box-shadow:none !important;
  transition:transform .12s ease;
}
[class*="st-key-pig_"] button p{font-size:0;line-height:0;}
[class*="st-key-pig_"] button:hover{transform:scale(1.08) !important;}

/* Botón "+" (color personalizado) */
.st-key-pig_8 button{
  background:var(--papel) !important;
  border:4px dashed var(--azul) !important;
  border-radius:50% !important;
  display:flex;
  align-items:center;
  justify-content:center;
}
.st-key-pig_8 button::after{
  content:"+";
  font-family:'Delicious Handrawn','Nunito',sans-serif;
  font-size:3rem;
  line-height:1;
  color:var(--azul);
}

/* Grosor: barras que engordan */
[class*="st-key-gro_"] [data-testid="stButton"],
[class*="st-key-gro_"] .stButton{width:100% !important;}
[class*="st-key-gro_"] button{
  width:100% !important;
  height:62px !important;
  min-height:0 !important;
  padding:0 !important;
  display:flex;
  align-items:center;
  justify-content:center;
  background:transparent !important;
  border:3px solid transparent !important;
  border-radius:16px;
  box-shadow:none !important;
  transform:none !important;
}
[class*="st-key-gro_"] button:hover{background:#FFF1C8 !important;}
[class*="st-key-gro_"] button p{font-size:0;line-height:0;}
[class*="st-key-gro_"] button::after{
  content:"";
  display:block;
  width:78%;
  border-radius:999px;
  background:var(--azul);
}

/* Herramientas */
[class*="st-key-tool_"] [data-testid="stButton"],
[class*="st-key-tool_"] .stButton{width:100% !important;}
[class*="st-key-tool_"] button{
  width:100% !important;
  height:52px !important;
  min-height:0 !important;
  padding:0 6px !important;
  background:var(--papel) !important;
  border:3px solid var(--azul) !important;
  border-radius:999px;
  box-shadow:none !important;
  transform:none !important;
}
[class*="st-key-tool_"] button p{
  font-weight:800;
  font-size:1rem;
  color:var(--azul);
}
[class*="st-key-tool_"] button:hover{background:#FFF1C8 !important;}

/* Botones generales: píldoras planas */
.stButton > button{
  font-family:'Nunito',sans-serif;
  font-weight:800;
  font-size:1.05rem;
  color:var(--azul);
  background:var(--papel);
  border:3px solid var(--azul);
  border-radius:999px;
  padding:.45rem 1.6rem;
  box-shadow:0 4px 0 var(--azul);
  transition:transform .12s ease, box-shadow .12s ease, background .12s ease;
}
.stButton > button:hover{
  background:#FFF1C8;
  color:var(--azul);
  border-color:var(--azul);
  transform:translateY(-1px);
  box-shadow:0 5px 0 var(--azul);
}
.stButton > button:active{transform:translateY(3px);box-shadow:0 1px 0 var(--azul);}
.st-key-interpretar .stButton > button{
  background:var(--azul);
  color:#FFFBEF;
  font-size:1.25rem;
  padding:.65rem 2rem;
  border-color:var(--azul-osc);
  box-shadow:0 5px 0 var(--azul-osc);
}
.st-key-interpretar .stButton > button p{color:#FFFBEF;}
.st-key-interpretar .stButton > button:hover{background:#1F5FC6;}

/* Campo de clave */
[data-baseweb="input"]{
  background:var(--papel) !important;
  border:3px solid var(--azul) !important;
  border-radius:14px !important;
}
[data-baseweb="input"] input{background:transparent !important;color:var(--texto);}

/* ---------- Bloc de acuarela ---------- */
.st-key-bloc{
  position:relative;
  background:#FFFDF5;
  margin-top:26px;
  padding:34px 22px 22px;
  border:3px solid var(--azul);
  border-radius:22px;
  box-shadow:9px 9px 0 var(--amarillo);
}
.st-key-bloc::before{
  content:"";
  position:absolute;
  top:-14px;left:26px;right:26px;
  height:28px;
  background:radial-gradient(circle at 50% 60%, #0A4AAE 0 4px, #FFFBEF 5px 7px, transparent 8px) 0 0 / 34px 28px repeat-x;
}
.st-key-bloc iframe{
  border:2px solid rgba(10,74,174,.25);
  border-radius:6px;
  max-width:100%;
  color-scheme:light;
  background:#FCF8EC;
}

/* ---------- Libreta de notas ---------- */
.libreta{
  position:relative;
  background-color:#FFFDF4;
  background-image:repeating-linear-gradient(to bottom, transparent 0, transparent 31px, rgba(10,74,174,.22) 31px, rgba(10,74,174,.22) 32px);
  background-position:0 14px;
  background-repeat:repeat-y;
  padding:14px 20px 22px 74px;
  margin:1.4rem 0 1rem;
  border:3px solid var(--azul);
  border-radius:8px 18px 18px 8px;
  box-shadow:6px 6px 0 var(--morado);
  font-family:'Kalam',cursive;
  font-size:1.1rem;
  line-height:32px;
  color:#1F2A6B;
}
.libreta::before{
  content:"";
  position:absolute;
  top:0;bottom:0;left:52px;
  width:2px;
  background:rgba(240,57,43,.55);
}
.libreta::after{
  content:"";
  position:absolute;
  top:0;bottom:0;left:12px;
  width:22px;
  background:radial-gradient(circle at 50% 50%, #FDF8EA 0 8px, rgba(10,74,174,.45) 9px, transparent 10px) 0 28px / 22px 96px repeat-y;
}
.libreta-titulo{
  font-family:'Delicious Handrawn','Caveat Brush',cursive;
  font-size:2rem;
  line-height:32px;
  color:var(--azul);
}
.libreta-texto{line-height:32px;}
.libreta-texto, .libreta-titulo{margin:0;}

/* ---------- Pincel lateral ---------- */
.pincel{
  position:fixed;
  right:10px;
  top:50%;
  transform:translateY(-50%);
  height:82vh;
  width:auto;
  pointer-events:none;
  z-index:2;
}

@media (max-width:1100px){
  .pincel{display:none;}
  .block-container{padding-right:1.5rem;}
}
@media (prefers-reduced-motion:reduce){
  .stButton > button, [class*="st-key-pig_"] button{transition:none;}
}
</style>
"""

SVG_BANNER = mini("""
<svg class="banner" viewBox="0 0 1140 420" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Taller de arte">
<defs>
<path id="mancha" d="M0 -20 C12 -26 26 -14 22 -2 C30 8 18 24 4 20 C-8 28 -26 14 -20 0 C-28 -10 -12 -24 0 -20Z"/>
</defs>

<path d="M1040 110 C1090 100 1140 105 1140 105 L1140 420 C1100 440 1050 400 1060 350 C1070 300 1000 270 1000 220 C1000 170 1010 125 1040 110Z" fill="#6A4FA8"/>
<path d="M770 0 L1060 0 C1068 36 1104 56 1112 96 C1096 128 1030 130 990 122 C940 152 884 142 846 104 C796 84 748 62 770 0Z" fill="#0A4AAE"/>
<g stroke="#FDB92D" stroke-width="30" stroke-linecap="round" fill="none">
<path d="M1010 170 L955 112"/><path d="M1010 170 L1062 98"/><path d="M1010 170 L1098 160"/>
<path d="M1010 170 L1056 236"/><path d="M1010 170 L944 214"/>
</g>
<circle cx="1010" cy="170" r="44" fill="#FDB92D"/>
<circle cx="944" cy="304" r="17" fill="#FDB92D"/>

<path d="M0 150 C40 130 85 150 95 190 C135 185 165 215 150 258 C140 296 95 330 40 335 C20 338 0 330 0 330Z" fill="#6A4FA8"/>
<path d="M44 140 C34 108 48 86 56 64 C64 90 74 116 64 146Z" fill="#6A4FA8"/>
<ellipse cx="40" cy="112" rx="8" ry="17" fill="#6A4FA8" transform="rotate(-8 40 112)"/>
<ellipse cx="270" cy="246" rx="36" ry="14" fill="#6A4FA8" transform="rotate(-24 270 246)"/>
<circle cx="214" cy="330" r="9" fill="#6A4FA8"/>
<circle cx="190" cy="218" r="6" fill="#6A4FA8"/>

<path d="M120 420 C130 380 190 372 215 352 C240 318 310 322 328 366 C380 372 440 392 428 420Z" fill="#7FBC7B"/>

<g transform="translate(150 322) rotate(-32)">
<ellipse cx="0" cy="0" rx="120" ry="84" fill="#FDB92D"/>
<ellipse cx="-46" cy="22" rx="21" ry="12" fill="#FFFBEF"/>
<use href="#mancha" x="-72" y="-34" fill="#7FBC7B" transform="scale(1.15)"/>
<use href="#mancha" x="-10" y="-46" fill="#F0392B" transform="scale(1.1)"/>
<use href="#mancha" x="48" y="-32" fill="#FFFBEF" transform="scale(1.15)"/>
<use href="#mancha" x="76" y="14" fill="#6A4FA8" transform="scale(1)"/>
<use href="#mancha" x="22" y="46" fill="#F0392B" transform="scale(1.1)"/>
<use href="#mancha" x="-30" y="52" fill="#7FBC7B" transform="scale(.95)"/>
</g>

<g fill="#0A4AAE" text-anchor="middle" style="font-family:'Delicious Handrawn','Caveat Brush',cursive">
<text x="560" y="190" font-size="150">TALLER</text>
<text x="404" y="318" font-size="104" style="font-family:'Caveat','Delicious Handrawn',cursive;font-weight:600">de</text>
<text x="640" y="334" font-size="140">ARTE</text>
</g>

<g fill="none" stroke="#FDB92D" stroke-width="7" stroke-linecap="round" stroke-linejoin="round">
<path d="M742 300 L744 301"/><path d="M762 306 L764 307"/>
<path d="M792 318 C830 334 868 350 906 366 C930 374 926 342 944 340 C966 340 1010 366 1056 392"/>
<path d="M1020 392 L1058 394 L1050 356"/>
</g>
</svg>
""")

SVG_PINCEL = mini("""
<svg class="pincel" viewBox="0 0 130 720" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<g transform="rotate(7 65 360)">
<path d="M56 24 C56 8 74 8 74 24 C79 120 88 230 80 346 L50 346 C42 230 51 120 56 24Z" fill="#0A4AAE"/>
<circle cx="65" cy="26" r="3.5" fill="#FDF8EA"/>
<path d="M54 92 Q66 98 78 92" stroke="#FDB92D" stroke-width="7" fill="none" stroke-linecap="round"/>
<path d="M55 108 Q67 114 79 108" stroke="#7FBC7B" stroke-width="7" fill="none" stroke-linecap="round"/>
<path d="M50 346 L80 346 L84 408 L46 408Z" fill="#C9D0DA"/>
<path d="M48 366 L82 366 M47 386 L83 386" stroke="#9AA4B2" stroke-width="3"/>
<path d="M46 408 L84 408 C88 448 78 492 66 540 C65 546 63 546 62 540 C50 492 42 448 46 408Z" fill="#5A3A24"/>
<path d="M52 478 C58 490 72 490 78 478 C74 510 70 530 65 548 C60 530 54 510 52 478Z" fill="#6A4FA8"/>
<path d="M64 548 C26 580 104 610 56 644 S84 692 50 716" fill="none" stroke="#6A4FA8" stroke-width="15" stroke-linecap="round"/>
<path d="M70 560 C96 586 52 614 82 650" fill="none" stroke="#FDB92D" stroke-width="6" stroke-linecap="round"/>
<path d="M58 660 C40 676 70 690 56 708" fill="none" stroke="#7FBC7B" stroke-width="6" stroke-linecap="round"/>
<circle cx="98" cy="556" r="4" fill="#6A4FA8"/>
<circle cx="26" cy="598" r="3" fill="#6A4FA8"/>
<circle cx="104" cy="628" r="3.5" fill="#FDB92D"/>
</g>
</svg>
""")

st.markdown(CSS_BASE, unsafe_allow_html=True)
st.markdown(css_dinamico(), unsafe_allow_html=True)
st.markdown(SVG_PINCEL, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Barra lateral: paleta y herramientas
# ---------------------------------------------------------------------------
with st.sidebar:
    with st.container(key="panel_color"):
        st.markdown('<div class="panel-t">Color de pintura</div>', unsafe_allow_html=True)
        with st.container(key="paleta"):
            for fila in range(3):
                columnas = st.columns(3, gap="small")
                for c in range(3):
                    i = fila * 3 + c
                    with columnas[c]:
                        with st.container(key=f"pig_{i}"):
                            if i < len(PIGMENTOS):
                                nombre = PIGMENTOS[i][0]
                            else:
                                nombre = "Color personalizado"
                            boton(nombre, key=f"btn_pig_{i}", help=nombre,
                                  on_click=elegir_pigmento, args=(i,))
        if st.session_state.pig == IDX_PERSONALIZADO:
            st.session_state.custom_hex = st.color_picker(
                "Elige tu propio color",
                value=st.session_state.custom_hex,
                key="selector_personalizado",
            )

    with st.container(key="panel_grosor"):
        st.markdown('<div class="panel-t">Grosor del pincel</div>', unsafe_allow_html=True)
        cols_grosor = st.columns(5, gap="small")
        for i, (nombre, _) in enumerate(GROSORES):
            with cols_grosor[i]:
                with st.container(key=f"gro_{i}"):
                    boton(nombre, key=f"btn_gro_{i}", help=nombre,
                          on_click=elegir_grosor, args=(i,))

    with st.container(key="panel_herramienta"):
        st.markdown('<div class="panel-t">Herramienta</div>', unsafe_allow_html=True)
        cols_tool = st.columns(3, gap="small")
        for i, nombre in enumerate(HERRAMIENTAS):
            with cols_tool[i]:
                with st.container(key=f"tool_{i}"):
                    boton(ETIQUETA_HERRAMIENTA[i], key=f"btn_tool_{i}", help=nombre,
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
# Banner y lema
# ---------------------------------------------------------------------------
st.markdown(SVG_BANNER, unsafe_allow_html=True)
st.markdown(
    '<p class="lema">Dibuja lo que quieras y la máquina lo interpretará.</p>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Dos secciones: lienzo e interpretación
# ---------------------------------------------------------------------------
if st.session_state.pig == IDX_PERSONALIZADO:
    pig_hex = st.session_state.custom_hex
else:
    pig_hex = PIGMENTOS[st.session_state.pig][1]
gro_px = GROSORES[st.session_state.gro][1]

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

col_lienzo, col_analisis = st.columns([1.65, 1], gap="large")

with col_lienzo:
    st.markdown(seccion(1, "Lienzo"), unsafe_allow_html=True)
    with st.container(key="bloc"):
        lienzo = st_canvas(
            fill_color=relleno,
            stroke_width=ancho,
            stroke_color=trazo,
            background_color=PAPEL_HEX,
            height=470,
            width=700,
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
