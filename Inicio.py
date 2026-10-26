import streamlit as st
import base64
import os
import io
from openai import OpenAI
from PIL import Image, ImageFilter
import numpy as np
from streamlit_drawable_canvas import st_canvas

# ---------------------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA Y CONSTANTES
# ---------------------------------------------------------------------------
st.set_page_config(page_title='Espacio Creativo - El Pintor', layout="wide", initial_sidebar_state="expanded")

AZUL = "#1A2A44"
CREMA_FONDO = "#FCF8F2"
CREMA_PANEL = "#FFFDF8"
CREMA_OSCURO = "#E8DCC8"
MADERA_MESA = "#D4B895"
ROJO_ACENTO = "#D45A4A"

SLOTS = [
    ("Azul", "#1F5BC4"), ("Rojo", "#E0393E"), ("Verde", "#3E9E5F"),
    ("Amarillo", "#F5C02A"), None, ("Naranja", "#F28A2E"),
    ("Rosa", "#EE7FAE"), ("Morado", "#7B4FB8"), ("Negro", "#26211F")
]

# ---------------------------------------------------------------------------
# ESTADO DE LA SESIÓN
# ---------------------------------------------------------------------------
for clave, valor in {
    "lienzo": 0, "nota": "", "pig": 0, "gro": 2, 
    "tool": 0, "custom_hex": "#E873A5", "papel": 1
}.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor

def elegir(clave, valor):
    st.session_state[clave] = valor

# ---------------------------------------------------------------------------
# UTILIDADES
# ---------------------------------------------------------------------------
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

def a_base64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

# Filtro de acuarela básico para darle un toque artístico
def aplicar_acuarela(img):
    img = img.filter(ImageFilter.GaussianBlur(1.5))
    arr = np.array(img).astype(np.float32)
    noise = np.random.normal(0, 5, arr.shape[:2])[..., None]
    arr = np.clip(arr + noise, 0, 255).astype("uint8")
    return Image.fromarray(arr)

# ---------------------------------------------------------------------------
# CSS (Estilo Portafolio / Cuento Infantil / Pintor)
# ---------------------------------------------------------------------------
CSS_BASE = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,700;1,500&family=Quicksand:wght@400;500;600;700&display=swap');

:root {{
  --azul: {AZUL};
  --crema: {CREMA_PANEL};
  --crema-fondo: {CREMA_FONDO};
  --crema-oscuro: {CREMA_OSCURO};
  --rojo: {ROJO_ACENTO};
}}

html, .stApp {{ color-scheme: light; }}
[data-testid="stAppViewContainer"], [data-testid="stMain"], .main {{ background: transparent !important; }}

.stApp, .stApp p, .stApp label, .stApp li, .stApp [data-testid="stMarkdownContainer"] {{
  font-family: 'Quicksand', sans-serif;
  color: var(--azul);
}}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ max-width: 1400px; padding-top: 2rem; padding-bottom: 5rem; }}

/* BARRA LATERAL */
[data-testid="stSidebar"][aria-expanded="true"] {{
  min-width: 420px !important;
  width: 420px !important;
}}
[data-testid="stSidebar"] {{
  background: var(--crema-fondo);
  border-right: 3px solid var(--crema-oscuro);
}}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding: 1.5rem 2rem; }}

.panel-t {{
  font-family: 'Playfair Display', serif;
  font-weight: 700;
  font-size: 1.4rem;
  color: var(--azul);
  margin: 1.5rem 0 0.8rem 0;
  border-bottom: 2px solid var(--crema-oscuro);
  padding-bottom: 0.3rem;
}}

/* PALETA DE PINTOR */
.st-key-paleta {{
  background: linear-gradient(135deg, #E8C99B, #D4B895);
  border: 4px solid #B08D6A;
  border-radius: 60% 40% 50% 50% / 50% 60% 40% 50%;
  padding: 50px 40px 70px;
  gap: 1.5rem !important;
  box-shadow: inset 0 4px 0 rgba(255,255,255,.5), 0 15px 20px -8px rgba(70,45,15,.6);
  position: relative;
  margin-bottom: 2rem;
}}
.st-key-paleta::after {{
  content: ""; position: absolute; right: 18%; bottom: 12%;
  width: 50px; height: 60px; border-radius: 50%;
  background: #E8C99B; border: 3px solid #B08D6A;
  box-shadow: inset 4px 5px 8px rgba(70,45,15,.6);
}}

/* Gotas de color */
[class*="st-key-pig_"] button {{
  width: 55px !important; height: 55px !important;
  border-radius: 50% 0 50% 50% !important;
  transform: rotate(-45deg);
  box-shadow: inset -3px -4px 0 rgba(0,0,0,.2), 0 0 0 2px rgba(26,42,68,.5) !important;
  border: none !important; padding: 0 !important;
  transition: transform .2s ease;
}}
[class*="st-key-pig_"] button p {{ font-size: 0; }}
[class*="st-key-pig_"] button::after {{
  content: ""; position: absolute; top: 22%; left: 30%;
  width: 30%; height: 15%; border-radius: 50%;
  background: rgba(255,255,255,.6); transform: rotate(45deg);
}}
.st-key-pig_4 button {{
  background: var(--crema) !important; border: 3px dashed #B08D6A !important;
  border-radius: 50% !important; transform: none !important;
  display: flex; align-items: center; justify-content: center;
}}
.st-key-pig_4 button::after {{ content: "+"; font-family: 'Playfair Display', serif; font-size: 2rem; color: var(--azul); background: none; position: static; transform: none; width: auto; height: auto; }}

/* BOTONES Y CONTROLES */
.stButton > button {{
  font-family: 'Quicksand', sans-serif; font-weight: 700; font-size: 1.05rem;
  color: white !important; background: var(--azul) !important;
  border: none; border-radius: 999px; padding: 0.5rem 1.5rem;
  transition: transform 0.2s ease;
}}
.stButton > button p {{ color: white !important; }}
.stButton > button:hover {{ transform: translateY(-2px); opacity: 0.9; }}
.st-key-btn-interpretar .stButton > button {{ background: var(--rojo) !important; }}

[data-baseweb="input"] {{ background: var(--crema-fondo) !important; border: 2px solid var(--azul) !important; border-radius: 12px !important; }}
[data-baseweb="input"] input {{ color: var(--azul) !important; }}

/* CUADERNO ABIERTO */
.st-key-hoja {{
  max-width: 1050px; margin: 0 auto 2rem;
  background: var(--crema-fondo);
  border-radius: 20px; padding: 40px;
  box-shadow: 0 20px 40px -15px rgba(0,0,0,0.3);
  border: 1px solid var(--crema-oscuro);
}}
.titulo-principal {{
  font-family: 'Playfair Display', serif; font-size: 3rem;
  font-weight: 700; color: var(--azul); text-align: center; font-style: italic;
}}
.subtitulo {{
  font-size: 1.2rem; color: var(--azul); text-align: center;
  margin-bottom: 2rem; opacity: 0.8;
}}
.st-key-paginas {{
  background-color: #FFFFFF; padding: 30px; border-radius: 8px;
  box-shadow: 0 2px 0 #E8DCC8, 0 4px 0 #D4C5AD, 0 6px 0 #E8DCC8, 0 8px 0 #D4C5AD;
  position: relative; margin: 0 10px;
}}
.st-key-paginas::before {{
  content: ""; position: absolute; top: -10px; bottom: -10px; left: calc(50% - 32px);
  width: 64px; border-left: 4px dashed #D4C5AD; border-right: 4px dashed #D4C5AD;
  z-index: 10; pointer-events: none;
}}

/* LIBRETA DE NOTAS (Texto de la IA) */
.libreta {{
  background-color: #FFF6E5;
  background-image: repeating-linear-gradient(to bottom, transparent 0, transparent 31px, rgba(26,42,68,.15) 31px, rgba(26,42,68,.15) 32px);
  padding: 20px 25px 30px 75px; border-radius: 8px;
  font-size: 1.1rem; line-height: 32px; color: var(--azul);
  border-left: 4px solid #E8C99B; position: relative; margin-top: 1rem;
}}
.libreta::before {{
  content: ""; position: absolute; top: 0; bottom: 0; left: 50px;
  width: 2px; background: rgba(212, 90, 74, 0.4);
}}
</style>
"""
st.markdown(CSS_BASE, unsafe_allow_html=True)

# Fondo de mesa de madera
st.markdown(
    f"""<style>.stApp {{
    background-color: {MADERA_MESA};
    background-image: repeating-linear-gradient(45deg, rgba(0,0,0,.05) 0, rgba(0,0,0,.05) 2px, transparent 2px, transparent 10px);
    }}</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# BARRA LATERAL (Herramientas)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="panel-t">🎨 Tu Paleta</div>', unsafe_allow_html=True)
    
    with st.container(key="paleta"):
        for fila in range(3):
            cols = st.columns(3, gap="medium")
            for c in range(3):
                i = fila * 3 + c
                with cols[c]:
                    with st.container(key=f"pig_{i}"):
                        nombre = SLOTS[i][0] if SLOTS[i] else "Custom"
                        if st.button("", key=f"btn_pig_{i}", help=nombre, on_click=elegir, args=("pig", i)):
                            pass
                        
        if st.session_state.pig == 4:
            st.session_state.custom_hex = st.color_picker("Elige tu color", st.session_state.custom_hex)

    if st.session_state.pig == 4:
        color_actual = st.session_state.custom_hex
    else:
        color_actual = SLOTS[st.session_state.pig][1]

    st.markdown('<div class="panel-t">🖌️ Pincel</div>', unsafe_allow_html=True)
    grosor = st.slider("Grosor del trazo", 2, 30, 8)
    
    st.markdown('<div class="panel-t">🔑 Clave API</div>', unsafe_allow_html=True)
    api_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...")

# Configuración para el canvas
herramienta = "freedraw"
papel_rgb = (252, 248, 242) # Crema muy claro

r, g, b = hex_a_rgb(color_actual)
stroke_color = f"rgba({r},{g},{b},1)"

# ---------------------------------------------------------------------------
# ZONA PRINCIPAL (Cuaderno)
# ---------------------------------------------------------------------------
with st.container(key="hoja"):
    st.markdown('<div class="titulo-principal">Espacio creativo para dibujar</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitulo">¡Bienvenido pequeño pintor! Dibuja y deja que la IA traduzca tu arte en una fábula.</div>', unsafe_allow_html=True)
    
    with st.container(key="paginas"):
        lienzo = st_canvas(
            fill_color="rgba(255, 255, 255, 0)",
            stroke_width=grosor,
            stroke_color=stroke_color,
            background_color="#FFFFFF",
            height=500,
            width=850,
            drawing_mode=herramienta,
            key=f"canvas_{st.session_state.lienzo}",
        )

    # Botones de acción debajo del lienzo
    st.write("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.container(key="btn-interpretar"):
            analizar = st.button("✨ Interpretar mi dibujo", use_container_width=True)
        if st.button("Limpiar lienzo", use_container_width=True):
            st.session_state.lienzo += 1
            st.session_state.nota = ""
            st.rerun()

# ---------------------------------------------------------------------------
# LÓGICA DE OPENAI E INTERPRETACIÓN
# ---------------------------------------------------------------------------
if analizar:
    if not api_key:
        st.warning("Por favor, ingresa tu clave de OpenAI en la barra lateral para continuar.")
    elif lienzo.image_data is None:
        st.info("El lienzo está vacío. ¡Haz un dibujo primero!")
    else:
        with st.spinner("La IA está mezclando los colores y escribiendo tu historia..."):
            try:
                # Preparar la imagen para enviarla
                img = imagen_del_lienzo(lienzo.image_data, papel_rgb)
                img_acuarela = aplicar_acuarela(img)
                base64_img = a_base64(img_acuarela)
                
                client = OpenAI(api_key=api_key)
                
                prompt = (
                    "Eres un narrador de cuentos infantiles. Mira este dibujo hecho por un niño. "
                    "Escribe una fábula corta (máximo 2 párrafos) inspirada exactamente en lo que ves. "
                    "Usa un tono mágico y motivador, dirigiéndote al autor como 'pequeño pintor'."
                )
                
                respuesta = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_img}"}}
                            ]
                        }
                    ],
                    max_tokens=600
                )
                
                st.session_state.nota = respuesta.choices[0].message.content
                
            except Exception as e:
                st.error(f"Ocurrió un error al contactar a la IA: {e}")

# Mostrar el resultado si existe
if st.session_state.nota:
    with st.container(key="hoja"):
        st.markdown("<div class='panel-t'>📖 El cuento de tu dibujo</div>", unsafe_allow_html=True)
        texto_html = st.session_state.nota.replace("\n", "<br>")
        st.markdown(f'<div class="libreta">{texto_html}</div>', unsafe_allow_html=True)
