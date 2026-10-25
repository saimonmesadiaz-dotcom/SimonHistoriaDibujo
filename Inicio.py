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

PIGMENTOS = [
    ("Rojo carmín", "#D62839"),
    ("Naranja ocre", "#F26B21"),
    ("Amarillo cadmio", "#F7C325"),
    ("Verde hoja", "#3FA34D"),
    ("Verde oliva", "#8A9A2B"),
    ("Turquesa", "#2BB5C6"),
    ("Azul ultramar", "#2E5BBA"),
    ("Violeta", "#6B3FA0"),
    ("Rosa quinacridona", "#E873A5"),
    ("Tierra de siena", "#8A4B2A"),
    ("Gris de Payne", "#4A5568"),
    ("Negro humo", "#1E1B1A"),
]
COLOR_DE = dict(PIGMENTOS)

GROSORES = {"Fino": 2, "Medio": 7, "Grueso": 15, "Brocha": 30}

HERRAMIENTAS = {
    "Pincel libre": "freedraw",
    "Línea": "line",
    "Rectángulo": "rect",
    "Círculo": "circle",
    "Mover trazos": "transform",
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
}.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor


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


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------
def css_pigmentos():
    reglas = []
    for i, (_, hex_) in enumerate(PIGMENTOS, start=1):
        reglas.append(f".st-key-paleta label:nth-child({i}){{background:{hex_};}}")
    return "\n".join(reglas)


def css_grosores():
    reglas = []
    for i, px in enumerate([5, 10, 18, 30], start=1):
        reglas.append(
            f".st-key-grosor label:nth-child({i})::after{{width:{px}px;height:{px}px;}}"
        )
    return "\n".join(reglas)


CSS_BASE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Caveat+Brush&family=Kalam:wght@300;400;700&display=swap');

:root{
  --papel:#FCF8EC;
  --crema:#F6ECD3;
  --tinta:#3B2A20;
  --tinta-suave:#6B5545;
  --indigo:#2B2F6B;
}

.stApp{
  background-color:#F6ECD3;
  background-image:
    url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 .45 0 0 0 0 .35 0 0 0 0 .2 0 0 0 .10 0'/%3E%3C/filter%3E%3Crect width='220' height='220' filter='url(%23n)'/%3E%3C/svg%3E"),
    radial-gradient(circle at 0% 100%, rgba(43,181,198,.20), transparent 36%),
    radial-gradient(circle at 100% 0%, rgba(214,40,57,.10), transparent 30%);
  color:var(--tinta);
}
.stApp, .stApp p, .stApp label, .stApp li,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stCaptionContainer"]{
  font-family:'Kalam','Segoe Print',cursive;
  color:var(--tinta);
}
[data-testid="stHeader"]{background:transparent;}
.block-container{
  max-width:1280px;
  padding-top:2rem;
  padding-right:150px;
}

/* ---------- Encabezado ---------- */
.titulo{
  font-family:'Caveat Brush','Kalam',cursive;
  font-size:4.6rem;
  line-height:1;
  margin:0;
  color:var(--tinta);
  letter-spacing:.5px;
  transform:rotate(-1.2deg);
  transform-origin:left center;
}
.subrayado{width:min(440px,70%);height:auto;display:block;margin:2px 0 0 4px;}
.lema{font-size:1.3rem;margin:.4rem 0 0 4px;color:var(--tinta-suave);}

/* ---------- Barra lateral ---------- */
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#EFE2C2,#E6D4AA);
  border-right:1px solid rgba(120,90,50,.25);
}
.rotulo{
  font-family:'Caveat Brush','Kalam',cursive;
  font-size:2.2rem;
  line-height:1.1;
  margin:.2rem 0 .6rem;
  color:var(--tinta);
}
.rotulo.chico{font-size:1.5rem;margin-top:1.1rem;}

/* Paleta de madera */
.st-key-paleta{
  position:relative;
  background:linear-gradient(135deg,#E6BC7E,#CB9657 55%,#DDB070);
  padding:38px 26px 26px;
  border-radius:52% 48% 50% 50% / 58% 54% 46% 42%;
  box-shadow:
    inset 0 2px 6px rgba(255,255,255,.4),
    inset 0 -8px 14px rgba(90,50,10,.30),
    0 10px 18px -8px rgba(70,40,10,.55);
}
.st-key-paleta::before{
  content:"";
  position:absolute;
  top:20px;right:30px;
  width:26px;height:26px;
  border-radius:50%;
  background:#EADCB9;
  box-shadow:inset 0 3px 5px rgba(60,35,10,.45);
}
.st-key-paleta div[role="radiogroup"]{
  display:grid !important;
  grid-template-columns:repeat(3,1fr);
  gap:12px 8px;
  justify-items:center;
}
.st-key-paleta label{
  position:relative;
  width:46px;height:46px;
  min-width:46px;
  margin:0 !important;
  padding:0 !important;
  border-radius:50% 46% 52% 48%;
  cursor:pointer;
  box-shadow:
    inset 0 -5px 8px rgba(0,0,0,.22),
    inset 0 3px 5px rgba(255,255,255,.25),
    0 0 0 4px rgba(120,70,20,.35);
  transition:transform .15s ease, box-shadow .15s ease;
}
.st-key-paleta label::after{
  content:"";
  position:absolute;
  top:8px;left:11px;
  width:15px;height:8px;
  border-radius:50%;
  background:rgba(255,255,255,.55);
  transform:rotate(-25deg);
}
.st-key-paleta label:hover{transform:scale(1.08);}
.st-key-paleta label:has(input:checked){
  transform:scale(1.18);
  box-shadow:
    inset 0 -5px 8px rgba(0,0,0,.22),
    0 0 0 3px #FFF8E4,
    0 0 0 6px #3B2A20;
}
.st-key-paleta label:has(input:focus-visible){outline:3px solid #2E5BBA;outline-offset:5px;}
.st-key-paleta label > *:not(input),
.st-key-grosor label > *:not(input){
  position:absolute !important;
  width:1px;height:1px;
  overflow:hidden;
  clip:rect(0 0 0 0);
  opacity:0;
}

/* Grosores */
.st-key-grosor div[role="radiogroup"]{
  display:flex !important;
  flex-direction:row;
  gap:8px;
}
.st-key-grosor label{
  position:relative;
  width:50px;height:50px;
  margin:0 !important;
  padding:0 !important;
  display:flex;
  align-items:center;
  justify-content:center;
  background:var(--papel);
  border:2px dashed rgba(59,42,32,.35);
  border-radius:14px 10px 16px 10px;
  cursor:pointer;
}
.st-key-grosor label::after{
  content:"";
  display:block;
  border-radius:50%;
  background:var(--tinta);
}
.st-key-grosor label:has(input:checked){
  border:2px solid var(--tinta);
  background:#FFF2C9;
  box-shadow:3px 3px 0 var(--tinta);
}
.st-key-grosor label:has(input:focus-visible){outline:3px solid #2E5BBA;outline-offset:3px;}

/* Botones dibujados a mano */
.stButton > button{
  font-family:'Kalam',cursive;
  font-size:1.1rem;
  color:var(--tinta);
  background:var(--papel);
  border:2px solid var(--tinta);
  border-radius:255px 15px 225px 15px / 15px 225px 15px 255px;
  padding:.4rem 1.4rem;
  box-shadow:3px 3px 0 var(--tinta);
  transition:transform .12s ease, box-shadow .12s ease, background .12s ease;
}
.stButton > button:hover{
  background:#FFF2C9;
  color:var(--tinta);
  border-color:var(--tinta);
  transform:translate(-1px,-1px);
  box-shadow:4px 4px 0 var(--tinta);
}
.stButton > button:active{transform:translate(2px,2px);box-shadow:1px 1px 0 var(--tinta);}
.st-key-interpretar .stButton > button{background:#F7C325;font-weight:700;font-size:1.25rem;}
.st-key-interpretar .stButton > button:hover{background:#FFD24D;}

/* ---------- Bloc de acuarela ---------- */
.st-key-bloc{
  position:relative;
  background:#FFFDF5;
  margin-top:26px;
  padding:34px 22px 22px;
  border-radius:6px 6px 16px 16px;
  box-shadow:
    0 1px 0 #E6DCC3,
    0 14px 26px -10px rgba(80,50,20,.45),
    0 0 0 1px rgba(120,90,50,.18);
  transform:rotate(-.25deg);
}
.st-key-bloc::before{
  content:"";
  position:absolute;
  top:-12px;left:18px;right:18px;
  height:28px;
  background:radial-gradient(circle at 50% 60%, #2B2119 0 4px, #CFC8B8 5px 7px, transparent 8px) 0 0 / 34px 28px repeat-x;
}
.st-key-bloc iframe{
  border:1px solid rgba(120,90,50,.28);
  border-radius:3px;
  max-width:100%;
}

/* ---------- Libreta de notas ---------- */
.libreta{
  position:relative;
  background-color:#FFFDF4;
  background-image:repeating-linear-gradient(to bottom, transparent 0, transparent 31px, rgba(70,120,180,.30) 31px, rgba(70,120,180,.30) 32px);
  background-position:0 14px;
  background-repeat:repeat-y;
  padding:14px 24px 22px 78px;
  margin:1.4rem 0 1rem;
  border-radius:4px 10px 10px 4px;
  box-shadow:0 10px 20px -10px rgba(80,50,20,.5), 0 0 0 1px rgba(120,90,50,.18);
  transform:rotate(.5deg);
  font-family:'Kalam',cursive;
  font-size:1.12rem;
  line-height:32px;
  color:var(--indigo);
}
.libreta::before{
  content:"";
  position:absolute;
  top:0;bottom:0;left:56px;
  width:2px;
  background:rgba(214,40,57,.55);
}
.libreta::after{
  content:"";
  position:absolute;
  top:0;bottom:0;left:14px;
  width:22px;
  background:radial-gradient(circle at 50% 50%, #E9DCB8 0 8px, rgba(0,0,0,.18) 9px, transparent 10px) 0 28px / 22px 96px repeat-y;
}
.libreta-titulo{
  font-family:'Caveat Brush','Kalam',cursive;
  font-size:1.8rem;
  line-height:32px;
  color:#D62839;
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
  filter:drop-shadow(-4px 6px 6px rgba(60,40,20,.28));
}

@media (max-width:1100px){
  .pincel{display:none;}
  .block-container{padding-right:1.5rem;}
  .titulo{font-size:3.4rem;}
}
@media (prefers-reduced-motion:reduce){
  .stButton > button, .st-key-paleta label{transition:none;}
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
<path d="M172 -10 C204 -2 244 14 262 40 L262 140 C246 150 226 146 214 128 C202 110 178 112 162 98 C140 80 138 52 148 32 C154 16 160 -4 172 -10Z" fill="#D62839" opacity=".88"/>
<path d="M196 130 C196 160 194 190 198 218 C199 230 214 230 215 218 C218 190 214 160 214 128Z" fill="#D62839" opacity=".85"/>
<path d="M70 22 C88 6 118 12 124 34 C130 56 108 70 88 66 C66 62 54 38 70 22Z" fill="#2E5BBA" opacity=".85"/>
<path d="M92 64 C92 82 91 96 94 108 C95 116 105 116 106 108 C108 96 104 82 104 66Z" fill="#2E5BBA" opacity=".85"/>
<path d="M120 120 C134 108 156 114 158 134 C160 152 140 164 124 156 C110 150 108 130 120 120Z" fill="#F7C325" opacity=".92"/>
<circle cx="52" cy="92" r="4" fill="#2E5BBA"/>
<circle cx="132" cy="84" r="3" fill="#D62839"/>
<circle cx="236" cy="176" r="5" fill="#D62839"/>
<circle cx="104" cy="170" r="3.5" fill="#F7C325"/>
<circle cx="170" cy="190" r="2.5" fill="#2E5BBA"/>
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
<path d="M55 72 Q65 78 76 72" stroke="#D62839" stroke-width="5" fill="none" stroke-linecap="round"/>
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
<path d="M64 552 C34 584 96 614 60 640" fill="none" stroke="#6B3FA0" stroke-width="6" stroke-linecap="round" opacity=".7"/>
<path d="M70 560 C96 586 52 614 82 650" fill="none" stroke="#F7C325" stroke-width="5" stroke-linecap="round" opacity=".85"/>
<path d="M58 660 C40 676 70 690 56 708" fill="none" stroke="#E873A5" stroke-width="5" stroke-linecap="round" opacity=".8"/>
</g>
<circle cx="98" cy="556" r="4" fill="#2BB5C6"/>
<circle cx="26" cy="598" r="3" fill="#2BB5C6"/>
<circle cx="104" cy="628" r="3.5" fill="#F7C325"/>
<circle cx="22" cy="660" r="2.5" fill="#6B3FA0"/>
</g>
</svg>
""")

SVG_SUBRAYADO = mini("""
<svg class="subrayado" viewBox="0 0 420 30" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<path d="M6 14 C80 4 150 22 230 11 S370 8 414 13" stroke="#D62839" stroke-width="7" fill="none" stroke-linecap="round" opacity=".85"/>
<path d="M20 20 C110 11 200 25 300 16 S380 15 400 19" stroke="#2E5BBA" stroke-width="4" fill="none" stroke-linecap="round" opacity=".8"/>
<path d="M40 25 C120 19 210 28 290 22" stroke="#F7C325" stroke-width="4" fill="none" stroke-linecap="round" opacity=".9"/>
</svg>
""")

st.markdown(CSS_BASE, unsafe_allow_html=True)
st.markdown(f"<style>{css_pigmentos()}\n{css_grosores()}</style>", unsafe_allow_html=True)
st.markdown(SVG_GOTAS + SVG_PINCEL, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Barra lateral: paleta y herramientas
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="rotulo">Tu paleta</div>', unsafe_allow_html=True)

    with st.container(key="paleta"):
        pigmento = st.radio(
            "Pigmento",
            [nombre for nombre, _ in PIGMENTOS],
            key="pigmento",
            label_visibility="collapsed",
        )
    st.caption(f"Pigmento: {pigmento}")

    st.markdown('<div class="rotulo chico">Grosor del pincel</div>', unsafe_allow_html=True)
    with st.container(key="grosor"):
        grosor_nombre = st.radio(
            "Grosor",
            list(GROSORES),
            index=1,
            key="grosor_radio",
            label_visibility="collapsed",
        )
    st.caption(f"Pincel: {grosor_nombre.lower()}")

    intensidad = st.slider("Intensidad del pigmento", 20, 100, 70, format="%d%%")
    herramienta = st.selectbox("Herramienta", list(HERRAMIENTAS))
    goma = st.toggle("Goma de borrar")

    if st.button("Lienzo nuevo"):
        st.session_state.lienzo += 1
        st.session_state.nota = ""
        st.session_state.historia = ""
        st.session_state.acuarela = None

    clave_env = os.environ.get("OPENAI_API_KEY", "")
    with st.expander("Llave de OpenAI", expanded=not clave_env):
        ke = st.text_input("Ingresa tu clave", type="password")
    api_key = ke or clave_env

# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------
st.markdown(
    '<h1 class="titulo">Taller de arte</h1>'
    + SVG_SUBRAYADO
    + '<p class="lema">Dibuja lo que quieras y la máquina lo interpretará.</p>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Lienzo (bloc de acuarela)
# ---------------------------------------------------------------------------
r, g, b = hex_a_rgb(COLOR_DE[pigmento])
if goma:
    trazo = f"rgba({PAPEL[0]},{PAPEL[1]},{PAPEL[2]},1)"
    relleno = trazo
    ancho = GROSORES[grosor_nombre] * 1.6
else:
    alfa = intensidad / 100
    trazo = f"rgba({r},{g},{b},{alfa})"
    relleno = f"rgba({r},{g},{b},{alfa * 0.35})"
    ancho = GROSORES[grosor_nombre]

with st.container(key="bloc"):
    lienzo = st_canvas(
        fill_color=relleno,
        stroke_width=ancho,
        stroke_color=trazo,
        background_color=PAPEL_HEX,
        height=500,
        width=820,
        drawing_mode=HERRAMIENTAS[herramienta],
        key=f"lienzo_{st.session_state.lienzo}",
    )

with st.container(key="interpretar"):
    interpretar = st.button("Interpretar mi dibujo")

# ---------------------------------------------------------------------------
# Interpretación con IA
# ---------------------------------------------------------------------------
if interpretar:
    if not api_key:
        st.warning("Ingresa tu llave de OpenAI en la barra lateral para interpretar el dibujo.")
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

# ---------------------------------------------------------------------------
# Resultado: libreta de notas + versión acuarela
# ---------------------------------------------------------------------------
if st.session_state.nota:
    col_nota, col_acuarela = st.columns([1.15, 1])

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

    with col_acuarela:
        if st.session_state.acuarela is not None:
            st.image(st.session_state.acuarela, caption="Tu dibujo con acabado de acuarela")

    if st.session_state.historia:
        st.markdown(libreta("Cuento del taller", st.session_state.historia), unsafe_allow_html=True)
