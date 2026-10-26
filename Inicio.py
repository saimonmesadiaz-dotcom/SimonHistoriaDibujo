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
# Configuración de página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Espacio Creativo - Taller de Arte",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Constantes y Estética del Portafolio
# ---------------------------------------------------------------------------
TINTA = "#0F2B5B"       # Azul oscuro institucional para alto contraste
SEL = "#E8912D"         # Naranja cálido de selección
CREMA_FONDO = "#F7F2E6" # Tono de fondo principal estilo portafolio
TARJETA_BG = "#FFFBF7"  # Tono crema para tarjetas y contenedores

SLOTS = [
    ("Azul", "#1F5BC4"),
    ("Rojo carmín", "#E0393E"),
    ("Verde", "#3E9E5F"),
    ("Amarillo", "#F5C02A"),
    None,  # Slot 4: Botón "+" (color personalizado)
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
COLORES_PAPEL = [
    ("Hueso", "#EDE5D1"),
    ("Crema", "#FCF8EC"),
    ("Blanco", "#FFFFFF"),
    ("Kraft", "#E5D2AC"),
]
MESAS = [("Nogal claro", "#C99A62"), ("Roble", "#D9B27C"), ("Cerezo", "#A8683F")]
ACABADOS = ["Normal", "Acuarela", "Tiza"]

# ---------------------------------------------------------------------------
# Inicialización del Estado
# ---------------------------------------------------------------------------
for clave, valor in {
    "lienzo": 0,
    "nota_titulo": "Mi obra maestra",
    "historia": "",
    "pig": 0,
    "gro": 2,
    "tool": 0,
    "papel": 1,
    "papel_color": 0,
    "mesa": 0,
    "acabado": 0,
    "custom_hex": "#E873A5",
    "api_key": "",
    "lienzo_ancho": 720,
    "lienzo_alto": 480,
}.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor

# ---------------------------------------------------------------------------
# Utilidades de Imagen
# ---------------------------------------------------------------------------
def hex_a_rgb(hex_):
    hex_ = hex_.lstrip("#")
    return tuple(int(hex_[i:i + 2], 16) for i in (0, 2, 4))

def imagen_del_lienzo(datos, papel):
    img = Image.fromarray(np.array(datos).astype("uint8"), "RGBA")
    fondo = Image.new("RGBA", img.size, tuple(papel) + (255,))
    fondo.alpha_composite(img)
    return fondo.convert("RGB")

def a_base64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

# ---------------------------------------------------------------------------
# Estilos CSS (Estética idéntica al portafolio: tonos crema, serifas y tarjetas)
# ---------------------------------------------------------------------------
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,700;1,500;1,700&family=Lora:ital,wght@0,400;0,600;1,400;1,600&display=swap');

:root {{
    --tinta: {TINTA};
    --tarjeta: {TARJETA_BG};
    --borde: #E4CC93;
    --sel: {SEL};
}}

html, .stApp {{
    color-scheme: light;
    background-color: {CREMA_FONDO} !important;
}}

[data-testid="stAppViewContainer"], [data-testid="stMain"], .main {{
    background: {CREMA_FONDO} !important;
}}

.stApp, .stApp p, .stApp label, .stApp li,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stCaptionContainer"] {{
    font-family: 'Lora', Georgia, serif;
    color: var(--tinta);
}}

.stApp label p {{ font-weight: 600; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ max-width: 1300px; padding: 4rem 2rem 5rem; }}

/* Barra lateral estilo portafolio */
[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, #FCEFC9, #F7E2A8);
    border-right: 2px solid rgba(160,110,40,.3);
}}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding: 1.5rem 1.2rem; }}

/* Tarjetas contenedoras elegantes */
.portfolio-card {{
    background: var(--tarjeta);
    border: 2px solid var(--borde);
    border-radius: 20px;
    padding: 24px;
    box-shadow: 0 10px 25px -8px rgba(110,70,20,.15);
    margin-bottom: 1.5rem;
}}

.port-title {{
    font-family: 'Playfair Display', Georgia, serif;
    font-weight: 700;
    font-size: 2.2rem;
    color: var(--tinta);
    line-height: 1.2;
    margin-bottom: 0.5rem;
}}

.port-subtitle {{
    font-family: 'Playfair Display', Georgia, serif;
    font-style: italic;
    font-size: 1.15rem;
    color: #4A5568;
    margin-bottom: 1.2rem;
}}

/* Cuadro de texto de la historia (Alto contraste: fondo crema, letra azul oscuro) */
.story-box {{
    background-color: #FCF8EC;
    border: 2px solid #D3C9AB;
    border-radius: 14px;
    padding: 20px;
    font-family: 'Lora', Georgia, serif;
    color: #0F2B5B;
    font-size: 1.05rem;
    line-height: 1.6;
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.03);
    margin-top: 1rem;
}}

/* Botones personalizados estilo portafolio */
.stButton > button {{
    font-family: 'Playfair Display', Georgia, serif;
    font-weight: 700;
    color: #0F2B5B;
    background: #FFF9E8;
    border: 2px solid #0F2B5B;
    border-radius: 999px;
    padding: 0.5rem 1.5rem;
    transition: all 0.2s ease;
}}
.stButton > button:hover {{
    background: #FBEFCB;
    border-color: #E8912D;
    color: #E8912D;
}}

[data-baseweb="input"] {{
    background: #FFF9E8 !important;
    border: 2px solid #0F2B5B !important;
    border-radius: 12px !important;
}}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Barra Lateral - Herramientas y Paleta
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🎨 Taller de Pintura")
    st.markdown("Elige tus colores y herramientas favoritas.")
    
    st.markdown("---")
    st.markdown("#### 🔑 Clave OpenAI")
    st.session_state.api_key = st.text_input(
        "API Key", 
        type="password", 
        value=st.session_state.api_key,
        help="Introduce tu clave de OpenAI para que la IA cree cuentos de tus dibujos."
    )

    st.markdown("---")
    st.markdown("#### 🖌️ Herramienta")
    for nombre, val in HERRAMIENTAS.items():
        if st.button(nombre, use_container_width=True):
            st.session_state.tool = list(HERRAMIENTAS.values()).index(val)

    st.markdown("---")
    st.markdown("#### 🎨 Paleta de Pigmentos")
    cols_p = st.columns(4)
    for i, slot in enumerate(SLOTS):
        col = cols_p[i % 4]
        with col:
            if slot is None:
                if st.button("➕", key=f"pig_{i}", help="Color personalizado"):
                    st.session_state.pig = i
            else:
                nom, hex_c = slot
                if st.button("●", key=f"pig_{i}", help=nom):
                    st.session_state.pig = i

    if st.session_state.pig == IDX_PERSONALIZADO:
        st.session_state.custom_hex = st.color_picker("Color mágico", st.session_state.custom_hex)

    st.markdown("---")
    st.markdown("#### ✒️ Grosor del Pincel")
    cols_g = st.columns(len(GROSORES))
    for i, (nombre_g, val_g) in enumerate(GROSORES):
        with cols_g[i]:
            if st.button(nombre_g[:3], key=f"gro_{i}", use_container_width=True):
                st.session_state.gro = i

# ---------------------------------------------------------------------------
# Panel Principal (Estilo Portafolio y Cuaderno Abierto)
# ---------------------------------------------------------------------------

# Cabecera principal solicitada
st.markdown(
    '<div class="portfolio-card">'
    '<div style="font-size: 1.1rem; font-weight: 600; color: #E8912D; margin-bottom: 0.3rem;">¡Bienvenido pequeño pintor!</div>'
    '<h1 class="port-title">Espacio creativo para dibujar, imagina más allá.</h1>'
    '<p class="port-subtitle">La Inteligencia Artificial va a traducir tu imagen o tu dibujo en una historia, en una cuentahistoria de fábulas, por ejemplo.</p>'
    '</div>', 
    unsafe_allow_html=True
)

# Contenedor del tablero de dibujo principal
col_ lienzo_1, col_lienzo_2 = st.columns([3, 2])

pigmento_activo = st.session_state.custom_hex if st.session_state.pig == IDX_PERSONALIZADO else (SLOTS[st.session_state.pig][1] if SLOTS[st.session_state.pig] else "#1F5BC4")
grosor_activo = GROSORES[st.session_state.gro][1]
herramienta_activa = list(HERRAMIENTAS.values())[st.session_state.tool]

with col_lienzo_1:
    st.markdown('<div class="portfolio-card">', unsafe_allow_html=True)
    st.markdown("### 🖼️ Tablero de Dibujo Mágico")
    st.markdown("Haz volar tu imaginación sobre el papel:")
    
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=grosor_activo,
        stroke_color=pigmento_activo,
        background_color="#FCF8EC",
        update_streamlit=True,
        height=st.session_state.lienzo_alto,
        width=st.session_state.lienzo_ancho,
        drawing_mode=herramienta_activa,
        key=f"canvas_{st.session_state.lienzo}",
    )
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("🧹 Limpiar Tablero", use_container_width=True):
            st.session_state.lienzo += 1
            st.session_state.historia = ""
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

with col_lienzo_2:
    st.markdown('<div class="portfolio-card">', unsafe_allow_html=True)
    st.markdown("### 📖 Cuentahistoria Mágica")
    st.markdown("Convierte tu arte en una fábula inspiradora.")
    
    titulo_obra = st.text_input("Título de tu obra:", "El viaje de la estrella valiente")
    
    if st.button("✨ ¡Traducir dibujo en fábula con IA!", use_container_width=True):
        if not st.session_state.api_key:
            st.error("Por favor, introduce tu clave de OpenAI en la barra lateral.")
        elif canvas_result.image_data is None:
            st.warning("¡Primero dibuja algo en el tablero!")
        else:
            with st.spinner("La magia está ocurriendo... Creando tu fábula..."):
                try:
                    img_final = imagen_del_lienzo(canvas_result.image_data, (252, 248, 236))
                    img_base64 = a_base64(img_final)
                    
                    client = OpenAI(api_key=st.session_state.api_key)
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text", 
                                        "text": f"Imagina que eres un cuentacuentos infantil entrañable. Con base en este dibujo titulado '{titulo_obra}', escribe una fábula corta, tierna y mágica dirigida a niños. Máximo 3 párrafos."
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": f"data:image/png;base64,{img_base64}"}
                                    }
                                ]
                            }
                        ],
                        max_tokens=400
                    )
                    st.session_state.historia = response.choices[0].message.content
                except Exception as e:
                    st.error(f"Ocurrió un error al conectar con OpenAI: {e}")

    # Cuadro de texto con contraste (Fondo crema, letra azul oscuro)
    if st.session_state.historia:
        st.markdown(
            f'<div class="story-box"><strong>📖 Fábula de tu dibujo:</strong><br><br>{st.session_state.historia}</div>', 
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="story-box" style="color: #8A7B60; font-style: italic;">Tu cuento aparecerá aquí en cuanto hagas clic en el botón mágico de IA...</div>', 
            unsafe_allow_html=True
        )
        
    st.markdown('</div>', unsafe_allow_html=True)
