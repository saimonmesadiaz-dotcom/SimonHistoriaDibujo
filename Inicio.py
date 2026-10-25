import base64
import io
import os

import streamlit as st
import numpy as np
from PIL import Image
from openai import OpenAI
from streamlit_drawable_canvas import st_canvas


# ------------------------------------------------------------
# CONFIGURACIÓN GENERAL
# ------------------------------------------------------------
st.set_page_config(
    page_title="Trazos — Taller de historias",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAPER_RGB = (252, 248, 236)
PAPER_HEX = "#FCF8EC"
INK_BLUE = "#214F82"
CREAM = "#F8F0D9"
PALETTE = [
    ("Azul tinta", "#214F82"),
    ("Azul cielo", "#75B9D4"),
    ("Amarillo", "#E8B94F"),
    ("Terracota", "#C96D52"),
    ("Verde salvia", "#829B78"),
    ("Lavanda", "#9B8AB8"),
    ("Rosa", "#D98CA0"),
    ("Carbón", "#292D32"),
]
TOOLS = [
    ("Pincel", "freedraw"),
    ("Rectángulo", "rect"),
    ("Círculo", "circle"),
    ("Línea", "line"),
]
BRUSH_SIZES = [("Fino", 3), ("Medio", 7), ("Grueso", 13), ("Brocha", 22)]


# ------------------------------------------------------------
# ESTADO DE SESIÓN
# ------------------------------------------------------------
defaults = {
    "canvas_reset": 0,
    "selected_color": PALETTE[0][1],
    "custom_color": "#214F82",
    "brush_size": 7,
    "selected_tool": "Pincel",
    "board_width": 760,
    "board_height": 440,
    "intensity": 90,
    "eraser": False,
    "drawing_description": "",
    "generated_story": "",
    "last_drawing": None,
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ------------------------------------------------------------
# ESTILOS
# ------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&display=swap');

    :root {
        --cream: #F8F0D9;
        --paper: #FCF8EC;
        --blue: #214F82;
        --blue-dark: #173A60;
        --muted: #657386;
        --line: #D9CFB8;
        --gold: #E8B94F;
    }
    html, body, [data-testid="stAppViewContainer"] {
        color: var(--blue);
        background: var(--cream);
    }
    [data-testid="stAppViewContainer"] {
        background:
          radial-gradient(ellipse at 7% 16%, rgba(201,109,82,.14) 0 2px, transparent 3px),
          radial-gradient(ellipse at 92% 26%, rgba(33,79,130,.13) 0 3px, transparent 4px),
          radial-gradient(ellipse at 95% 78%, rgba(232,185,79,.23) 0 5px, transparent 6px),
          radial-gradient(ellipse at 3% 86%, rgba(130,155,120,.16) 0 4px, transparent 5px),
          var(--cream);
        background-size: 83px 91px, 117px 103px, 139px 131px, 109px 127px, auto;
    }
    [data-testid="stHeader"] { background: rgba(248,240,217,.92); }
    .block-container {
        max-width: 1380px;
        padding-top: 2rem;
        padding-bottom: 2.8rem;
    }
    h1, h2, h3, h4, p, label, div, span {
        color: var(--blue);
    }
    h1, h2, h3 {
        font-family: 'Libre Baskerville', Georgia, serif !important;
        font-weight: 400 !important;
    }
    p, label, .stMarkdown, [data-testid="stCaptionContainer"] {
        font-family: 'Libre Baskerville', Georgia, serif;
    }
    .eyebrow {
        font-family: 'DM Mono', monospace;
        text-transform: uppercase;
        letter-spacing: 2.2px;
        font-size: .68rem;
        color: #8B7150;
        margin-bottom: .7rem;
    }
    .hero-title {
        font-family: 'Libre Baskerville', Georgia, serif;
        font-size: clamp(1.8rem, 3.4vw, 2.65rem);
        line-height: 1.22;
        font-weight: 400;
        margin: 0 0 .65rem;
        color: var(--blue);
    }
    .hero-title em { color: #9A604A; }
    .hero-copy {
        font-size: .98rem;
        line-height: 1.8;
        max-width: 670px;
        color: #53667B;
    }
    .tiny-note {
        font-family: 'DM Mono', monospace;
        font-size: .66rem;
        letter-spacing: 1px;
        text-transform: uppercase;
        color: #8B7150;
    }
    [data-testid="stSidebar"] {
        background: #F2E5C4;
        border-right: 1px solid #D7C79F;
    }
    [data-testid="stSidebar"] > div:first-child { padding-top: 1.1rem; }
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        font-family: 'Libre Baskerville', Georgia, serif !important;
        font-size: 1.15rem !important;
    }
    .palette-card {
        background: #E8B94F;
        border: 1px solid #D4A43B;
        border-radius: 46% 54% 48% 52% / 9% 12% 10% 13%;
        padding: 1rem .8rem .9rem;
        margin: .5rem 0 1rem;
        box-shadow: 3px 4px 0 rgba(33,79,130,.12);
    }
    .palette-title {
        font-family: 'DM Mono', monospace;
        font-size: .67rem;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        text-align: center;
        margin-bottom: .75rem;
        color: #4B4A40;
    }
    .swatch-row { display:flex; flex-wrap:wrap; justify-content:center; gap:9px; }
    .swatch {
        width: 28px; height: 28px; border-radius: 50%;
        border: 2px solid rgba(255,255,255,.75);
        box-shadow: 0 1px 3px rgba(0,0,0,.18);
        display: inline-block;
    }
    .section-rule {
        display:flex; align-items:center; gap:12px;
        margin: 1.25rem 0 .85rem;
        font-family:'DM Mono', monospace;
        font-size:.68rem; letter-spacing:1.7px; text-transform:uppercase;
        color:#8B7150;
    }
    .section-rule:after { content:''; height:1px; background:var(--line); flex:1; }
    .paper-shell {
        position:relative;
        background:#FFFDF6;
        border:1px solid #D7CEB9;
        border-radius:8px 8px 5px 5px;
        padding:22px 15px 15px;
        box-shadow: 0 4px 0 #E5D9BC, 0 12px 28px rgba(76,63,43,.10);
        margin-top:14px;
    }
    .paper-shell:before {
        content:'';
        position:absolute;
        left:16px; right:16px; top:-12px; height:24px;
        background: radial-gradient(circle at 12px 12px, #D7CEB9 0 5px, #F8F0D9 5.5px 8px, transparent 8.5px) 0 0 / 42px 24px repeat-x;
    }
    .paper-caption {
        font-family:'DM Mono', monospace;
        font-size:.63rem;
        letter-spacing:1.4px;
        text-transform:uppercase;
        margin:0 0 12px 4px;
        color:#9A8462;
    }
    .stButton > button {
        border-radius:5px;
        border:1px solid var(--blue);
        color:var(--blue);
        background:#FFFDF6;
        font-family:'DM Mono', monospace;
        font-size:.72rem;
        letter-spacing:.6px;
        transition: all .15s ease;
    }
    .stButton > button:hover {
        color:white; background:var(--blue); border-color:var(--blue);
    }
    .st-key-create_story .stButton > button {
        background:var(--blue); color:white;
    }
    .st-key-create_story .stButton > button:hover {
        background:var(--blue-dark); color:white;
    }
    [data-baseweb="input"], [data-baseweb="select"], [data-baseweb="textarea"] {
        border-radius:4px;
    }
    [data-testid="stMetric"] {
        background:rgba(255,253,246,.72);
        border:1px solid var(--line);
        padding:12px;
        border-radius:5px;
    }
    .story-card {
        background:#FFFDF6;
        border-left:3px solid #E8B94F;
        padding:1rem 1.2rem;
        border-radius:0 5px 5px 0;
        line-height:1.85;
        box-shadow:0 4px 14px rgba(76,63,43,.06);
    }
    .brush-footer {
        margin:2.2rem auto .3rem;
        max-width:780px;
        display:flex;
        align-items:center;
        justify-content:center;
        gap:14px;
        color:var(--blue);
    }
    .brush-svg { width:min(44vw, 330px); height:auto; flex:none; }
    .brush-words {
        font-family:'Libre Baskerville', Georgia, serif;
        font-style:italic;
        font-size:clamp(.8rem, 1.5vw, 1rem);
        color:var(--blue);
    }
    .footnote {
        text-align:center;
        font-family:'DM Mono', monospace;
        font-size:.62rem;
        letter-spacing:1px;
        color:#8B7150;
        margin-top:1rem;
    }
    @media (max-width: 850px) {
        .block-container { padding:1.2rem 1rem 2rem; }
        .hero-title { font-size:1.9rem; }
        .brush-svg { width:38vw; }
    }
    @media (prefers-reduced-motion: reduce) {
        * { transition:none !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# UTILIDADES
# ------------------------------------------------------------
def canvas_to_image(image_data):
    """Convierte el lienzo RGBA a una imagen RGB sobre papel crema."""
    rgba = Image.fromarray(np.asarray(image_data).astype("uint8"), "RGBA")
    background = Image.new("RGBA", rgba.size, PAPER_RGB + (255,))
    background.alpha_composite(rgba)
    return background.convert("RGB")


def image_to_base64(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def is_blank(image):
    arr = np.asarray(image).astype(np.int16)
    paper = np.array(PAPER_RGB, dtype=np.int16)
    diff = np.abs(arr - paper).max(axis=2)
    return int((diff > 18).sum()) < 25


def current_api_key():
    # Recomendado en producción: st.secrets["OPENAI_API_KEY"].
    try:
        secret_key = st.secrets.get("OPENAI_API_KEY", "")
    except Exception:
        secret_key = ""
    return secret_key or os.environ.get("OPENAI_API_KEY", "") or st.session_state.get("api_key_input", "")


def safe_api_error(error):
    # No imprimimos la clave ni información sensible.
    return f"{type(error).__name__}: {error}"


# ------------------------------------------------------------
# CABECERA
# ------------------------------------------------------------
left, right = st.columns([1.65, 1], gap="large")
with left:
    st.markdown('<div class="eyebrow">CUADERNO DE IDEAS · LABORATORIO CREATIVO</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-title">Dibuja sin reglas.<br><em>Imagina sin límites.</em></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-copy">Haz un garabato, dibuja un barco, inventa una criatura o escribe números al azar. '
        'La inteligencia artificial observará tus trazos y los convertirá en el comienzo de una historia.</div>',
        unsafe_allow_html=True,
    )
with right:
    st.markdown(
        """
        <div style="min-height:150px;display:flex;align-items:center;justify-content:center;
                    background:rgba(255,253,246,.55);border:1px solid #D9CFB8;border-radius:8px;padding:18px;">
          <svg viewBox="0 0 320 145" width="100%" role="img" aria-label="Manchas de pintura decorativas">
            <path d="M36 54 C16 31 41 9 62 25 C77 4 103 22 96 43 C119 57 100 81 77 75 C58 93 33 77 36 54Z" fill="#75B9D4" opacity=".9"/>
            <path d="M115 84 C101 64 120 44 141 55 C159 37 179 57 170 76 C192 93 168 112 150 102 C131 116 111 103 115 84Z" fill="#E8B94F" opacity=".95"/>
            <path d="M211 46 C196 25 217 9 237 23 C256 7 276 26 264 44 C285 61 264 78 246 68 C227 82 206 66 211 46Z" fill="#C96D52" opacity=".88"/>
            <circle cx="90" cy="111" r="4" fill="#214F82"/><circle cx="105" cy="119" r="2.5" fill="#214F82"/>
            <circle cx="196" cy="24" r="3" fill="#829B78"/><circle cx="287" cy="91" r="5" fill="#9B8AB8"/>
            <path d="M202 100 Q223 89 238 105 T275 111" fill="none" stroke="#214F82" stroke-width="3" stroke-linecap="round"/>
            <path d="M28 111 Q43 101 54 113 T76 117" fill="none" stroke="#9B8AB8" stroke-width="3" stroke-linecap="round"/>
          </svg>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown('<div class="section-rule">01 — Prepara tu mesa de trabajo</div>', unsafe_allow_html=True)


# ------------------------------------------------------------
# SIDEBAR: PALETA Y HERRAMIENTAS
# ------------------------------------------------------------
with st.sidebar:
    st.markdown("## Tu rincón creativo")
    st.caption("Elige pigmentos, prepara el pincel y deja que la imaginación haga el resto.")

    st.markdown('<div class="palette-card"><div class="palette-title">Paleta de pigmentos</div>', unsafe_allow_html=True)
    palette_cols = st.columns(4, gap="small")
    for idx, (name, color) in enumerate(PALETTE):
        with palette_cols[idx % 4]:
            selected = st.session_state.selected_color == color
            label = f"● {idx + 1}" if selected else f"○ {idx + 1}"
            if st.button(
                label,
                key=f"color_{idx}",
                help=f"{name} · {color}",
                use_container_width=True,
            ):
                st.session_state.selected_color = color
                st.session_state.eraser = False
                st.rerun()
            st.markdown(
                f'<div style="height:7px;border-radius:5px;background:{color};margin:-7px 5px 9px;"></div>',
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)

    st.session_state.custom_color = st.color_picker(
        "Mezcla tu propio color",
        value=st.session_state.custom_color,
    )
    if st.button("Usar color personalizado", use_container_width=True):
        st.session_state.selected_color = st.session_state.custom_color
        st.session_state.eraser = False
        st.rerun()

    st.markdown("---")
    st.markdown("### Herramienta")
    tool_names = [item[0] for item in TOOLS]
    st.session_state.selected_tool = st.radio(
        "Elige cómo dibujar",
        options=tool_names,
        index=tool_names.index(st.session_state.selected_tool),
        horizontal=False,
        label_visibility="collapsed",
    )

    st.markdown("### Grosor del trazo")
    brush_names = [item[0] for item in BRUSH_SIZES]
    selected_brush_name = st.radio(
        "Tamaño del pincel",
        options=brush_names,
        index=next(
            (i for i, item in enumerate(BRUSH_SIZES) if item[1] == st.session_state.brush_size),
            1,
        ),
        horizontal=True,
        label_visibility="collapsed",
    )
    st.session_state.brush_size = dict(BRUSH_SIZES)[selected_brush_name]

    st.markdown("### Tamaño del bloc")
    st.session_state.board_width = st.slider(
        "Ancho del tablero",
        min_value=500,
        max_value=1000,
        value=int(st.session_state.board_width),
        step=20,
    )
    st.session_state.board_height = st.slider(
        "Alto del tablero",
        min_value=300,
        max_value=650,
        value=int(st.session_state.board_height),
        step=10,
    )
    st.session_state.intensity = st.slider(
        "Opacidad del pigmento",
        min_value=25,
        max_value=100,
        value=int(st.session_state.intensity),
        step=5,
        format="%d%%",
    )

    st.markdown("---")
    st.markdown("### Herramientas del papel")
    st.session_state.eraser = st.toggle("Goma de borrar", value=st.session_state.eraser)
    if st.button("Empezar un bloc nuevo", use_container_width=True):
        st.session_state.canvas_reset += 1
        st.session_state.drawing_description = ""
        st.session_state.generated_story = ""
        st.session_state.last_drawing = None
        st.rerun()

    st.markdown("---")
    st.markdown("### Conexión con la IA")
    st.caption("Añade tu clave de OpenAI aquí o configúrala como secreto en Streamlit Cloud.")
    st.session_state.api_key_input = st.text_input(
        "Clave de OpenAI",
        type="password",
        value=st.session_state.get("api_key_input", ""),
        placeholder="sk-…",
    )


# ------------------------------------------------------------
# LIENZO
# ------------------------------------------------------------
st.markdown('<div class="section-rule">02 — Tu bloc de dibujo</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="tiny-note">No tiene que parecerse a nada. Empieza por un trazo.</div>',
    unsafe_allow_html=True,
)

active_tool = dict(TOOLS)[st.session_state.selected_tool]
if st.session_state.eraser:
    stroke_color = PAPER_HEX
    fill_color = PAPER_HEX
else:
    stroke_color = st.session_state.selected_color
    fill_color = st.session_state.selected_color + "55" if len(st.session_state.selected_color) == 7 else st.session_state.selected_color

# El lienzo se mantiene en un contenedor tipo bloc con argollas.
st.markdown('<div class="paper-shell"><div class="paper-caption">Papel de acuarela · sesión abierta</div>', unsafe_allow_html=True)
canvas_result = st_canvas(
    fill_color=fill_color,
    stroke_width=int(st.session_state.brush_size),
    stroke_color=stroke_color,
    background_color=PAPER_HEX,
    height=int(st.session_state.board_height),
    width=int(st.session_state.board_width),
    drawing_mode=active_tool,
    key=f"canvas_{st.session_state.canvas_reset}",
    display_toolbar=False,
    update_streamlit=True,
)
st.markdown("</div>", unsafe_allow_html=True)

col_hint, col_action = st.columns([1.2, 1], gap="medium")
with col_hint:
    st.caption("Consejo: combina formas, números y garabatos. La IA puede encontrar una historia en lo inesperado.")
with col_action:
    interpret_clicked = st.button("Leer mi dibujo ↗", type="primary", use_container_width=True)


# ------------------------------------------------------------
# INTERPRETACIÓN CON VISIÓN
# ------------------------------------------------------------
if interpret_clicked:
    key = current_api_key()
    if not key:
        st.warning("Añade tu clave de OpenAI en la barra lateral o configúrala en los secretos de Streamlit.")
    elif canvas_result.image_data is None:
        st.info("El bloc todavía se está preparando. Intenta de nuevo.")
    else:
        drawing = canvas_to_image(canvas_result.image_data)
        if is_blank(drawing):
            st.info("El papel está en blanco todavía. Dibuja algo y vuelve a intentarlo.")
        else:
            try:
                client = OpenAI(api_key=key)
                with st.spinner("Observando tus trazos y buscando una historia..."):
                    vision_response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "Eres una persona guía de un taller artístico: observadora, imaginativa y amable. "
                                    "Describe con cuidado lo que realmente ves en el dibujo: formas, colores, letras o números "
                                    "si son reconocibles. No afirmes con seguridad algo que no se distinga; puedes ofrecer "
                                    "dos interpretaciones posibles. En español, en 3 a 5 frases. Después sugiere una semilla "
                                    "creativa para una historia, sin escribir aún el cuento completo."
                                ),
                            },
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "Observa este dibujo y ayúdame a descubrir qué podría ser."},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{image_to_base64(drawing)}"
                                        },
                                    },
                                ],
                            },
                        ],
                        max_tokens=350,
                    )
                st.session_state.drawing_description = vision_response.choices[0].message.content or ""
                st.session_state.generated_story = ""
                st.session_state.last_drawing = drawing
            except Exception as exc:
                st.error("No pude interpretar el dibujo. Revisa tu conexión, la clave y el acceso al modelo.")
                st.caption(safe_api_error(exc))


# ------------------------------------------------------------
# RESULTADO E HISTORIA
# ------------------------------------------------------------
if st.session_state.drawing_description:
    st.markdown('<div class="section-rule">03 — Lo que vio la máquina</div>', unsafe_allow_html=True)
    result_left, result_right = st.columns([1, 1.2], gap="large")
    with result_left:
        st.markdown("#### Una primera interpretación")
        st.write(st.session_state.drawing_description)
        if st.session_state.last_drawing is not None:
            st.image(st.session_state.last_drawing, caption="Tu dibujo original", use_container_width=True)
    with result_right:
        st.markdown("#### Hagamos una historia")
        st.write("Convierte los trazos en un pequeño relato. Puedes elegir el tono que más te guste.")
        story_style = st.selectbox(
            "Estilo del cuento",
            ["Mágico y fantástico", "Aventura", "Misterio amable", "Humor absurdo", "Fábula con moraleja"],
        )
        story_length = st.select_slider(
            "Extensión",
            options=["Muy breve", "Breve", "Un poco más larga"],
            value="Breve",
        )
        if st.button("Crear una historia con mis trazos ↗", key="create_story", use_container_width=True):
            key = current_api_key()
            if not key:
                st.warning("Añade tu clave de OpenAI en la barra lateral.")
            else:
                length_instruction = {
                    "Muy breve": "unas 100 palabras",
                    "Breve": "entre 150 y 220 palabras",
                    "Un poco más larga": "entre 250 y 350 palabras",
                }[story_length]
                try:
                    client = OpenAI(api_key=key)
                    with st.spinner("Dándole vida a tu dibujo..."):
                        story_response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {
                                    "role": "system",
                                    "content": (
                                        "Eres una escritora creativa que convierte dibujos infantiles y garabatos "
                                        "en relatos imaginativos. No te burles del dibujo ni exijas que sea perfecto. "
                                        "Usa detalles visuales de la interpretación como inspiración, permite que la "
                                        "imaginación complete lo ambiguo y entrega una historia coherente, evocadora "
                                        "y apropiada para todas las edades. Escribe en español."
                                    ),
                                },
                                {
                                    "role": "user",
                                    "content": (
                                        f"Descripción del dibujo:\n{st.session_state.drawing_description}\n\n"
                                        f"Escribe una historia de estilo: {story_style}. "
                                        f"Extensión aproximada: {length_instruction}. "
                                        "Dale un título bonito y un final memorable."
                                    ),
                                },
                            ],
                            max_tokens=700,
                        )
                    st.session_state.generated_story = story_response.choices[0].message.content or ""
                except Exception as exc:
                    st.error("No se pudo crear la historia. Comprueba la clave y el acceso a la API.")
                    st.caption(safe_api_error(exc))

        if st.session_state.generated_story:
            st.markdown("### Tu historia")
            st.markdown(
                f'<div class="story-card">{st.session_state.generated_story.replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True,
            )


# ------------------------------------------------------------
# PIE CON PINCEL HORIZONTAL
# ------------------------------------------------------------
st.markdown(
    """
    <div class="brush-footer">
      <svg class="brush-svg" viewBox="0 0 360 70" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Pincel horizontal">
        <path d="M22 30 L246 30 Q260 30 260 35 Q260 40 246 40 L22 40 Q9 40 9 35 Q9 30 22 30Z" fill="#214F82"/>
        <path d="M54 30 L54 40 M62 30 L62 40 M70 30 L70 40" stroke="#E8B94F" stroke-width="2"/>
        <path d="M246 27 L278 27 L287 35 L278 43 L246 43Z" fill="#C7C9C7" stroke="#A5AAA8" stroke-width="1"/>
        <path d="M278 27 Q306 24 332 31 Q341 35 332 39 Q306 46 278 43Z" fill="#9B8AB8"/>
        <path d="M287 30 Q307 31 329 34 M287 40 Q307 39 329 36" stroke="#78689A" stroke-width="1.5" fill="none"/>
        <circle cx="21" cy="35" r="2" fill="#E8B94F"/>
      </svg>
      <div class="brush-words">Deja volar tu imaginación.</div>
    </div>
    <div class="footnote">TRAZOS · UN PEQUEÑO GESTO PUEDE CONTENER UNA GRAN HISTORIA</div>
    """,
    unsafe_allow_html=True,
)
