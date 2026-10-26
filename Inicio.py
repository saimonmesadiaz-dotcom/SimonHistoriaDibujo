import base64
import io

import streamlit as st
from PIL import Image, ImageDraw
from streamlit_drawable_canvas import st_canvas

st.set_page_config(page_title="Eres el pintor", page_icon="🎨", layout="wide")

# ----------------------------------------------------------------------------
# Datos
# ----------------------------------------------------------------------------
COLORES = [
    ("Azul", "#2f5fc4"), ("Rojo carmín", "#d9323f"), ("Verde", "#2e9e5b"),
    ("Amarillo", "#f2c230"), ("Naranja", "#f07d1e"), ("Morado", "#7c4dc4"),
    ("Rosa", "#ee6fa5"), ("Negro", "#222222"), ("Turquesa", "#1fb5c4"),
    ("Celeste", "#6cc4f0"), ("Lima", "#9ac43a"), ("Café", "#8a5a34"),
    ("Vino", "#8a1f45"), ("Blanco", "#ffffff"),
]
NOMBRES = [n for n, _ in COLORES] + ["+ Crear color"]
LIENZOS = {"Pequeño": (640, 400), "Mediano": (820, 520), "Grande": (980, 620)}
MODOS = {"Pincel libre": "freedraw", "Línea": "line",
         "Rectángulo": "rect", "Círculo": "circle"}
PAPEL = (243, 234, 211)

# ----------------------------------------------------------------------------
# Decoración de fondo (SVG incrustados)
# ----------------------------------------------------------------------------
def svg(s):
    return "url(\"data:image/svg+xml;utf8," + s.replace("#", "%23") + "\")"

PALETA = svg("<svg xmlns='http://www.w3.org/2000/svg' width='170' height='130'><ellipse cx='85' cy='65' rx='80' ry='58' fill='#f1d9a8' stroke='#b98a4e' stroke-width='5'/><circle cx='85' cy='95' r='9' fill='#c9955c'/><circle cx='45' cy='60' r='13' fill='#d9323f'/><circle cx='75' cy='36' r='13' fill='#2f5fc4'/><circle cx='112' cy='38' r='13' fill='#f2c230'/><circle cx='135' cy='68' r='13' fill='#2e9e5b'/><circle cx='55' cy='92' r='12' fill='#7c4dc4'/></svg>")
TUBOS = svg("<svg xmlns='http://www.w3.org/2000/svg' width='190' height='150'><g transform='rotate(35 95 75)'><rect x='60' y='20' width='34' height='100' rx='6' fill='#e9e9ee'/><rect x='60' y='20' width='34' height='38' rx='6' fill='#d9323f'/><rect x='68' y='6' width='18' height='16' fill='#c9ccd4'/></g><g transform='rotate(-20 140 80)'><rect x='125' y='30' width='30' height='90' rx='6' fill='#e9e9ee'/><rect x='125' y='30' width='30' height='34' rx='6' fill='#2e9e5b'/><rect x='132' y='16' width='16' height='16' fill='#c9ccd4'/></g></svg>")
PINCEL = svg("<svg xmlns='http://www.w3.org/2000/svg' width='200' height='60'><g transform='rotate(-12 100 30)'><rect x='10' y='25' width='130' height='9' rx='4' fill='#8a5a34'/><rect x='138' y='22' width='24' height='15' fill='#b9bcc6'/><path d='M162 22 L196 29 L162 37 Z' fill='#1d3a78'/></g></svg>")
LIBROS = svg("<svg xmlns='http://www.w3.org/2000/svg' width='170' height='150'><rect x='15' y='100' width='140' height='24' rx='4' fill='#6b4aa0'/><rect x='25' y='76' width='120' height='24' rx='4' fill='#f07d1e'/><rect x='20' y='52' width='125' height='24' rx='4' fill='#f2c230'/><rect x='30' y='28' width='110' height='24' rx='4' fill='#2f5fc4'/><circle cx='88' cy='16' r='14' fill='#d9323f'/><rect x='86' y='0' width='4' height='8' fill='#6b4a2a'/></svg>")
CRAYONES = svg("<svg xmlns='http://www.w3.org/2000/svg' width='150' height='150'><g transform='rotate(40 75 75)'><rect x='20' y='20' width='14' height='90' fill='#d9323f'/><rect x='38' y='20' width='14' height='90' fill='#f2c230'/><rect x='56' y='20' width='14' height='90' fill='#2e9e5b'/><rect x='74' y='20' width='14' height='90' fill='#2f5fc4'/><rect x='92' y='20' width='14' height='90' fill='#7c4dc4'/></g></svg>")
SALPICADURA = svg("<svg xmlns='http://www.w3.org/2000/svg' width='120' height='110'><circle cx='60' cy='55' r='30' fill='#7c4dc4'/><circle cx='20' cy='30' r='10' fill='#7c4dc4'/><circle cx='100' cy='25' r='8' fill='#7c4dc4'/><circle cx='98' cy='88' r='12' fill='#7c4dc4'/><circle cx='25' cy='90' r='7' fill='#7c4dc4'/></svg>")

gotas_css = ""
for i, (_, hexa) in enumerate(COLORES, start=1):
    gotas_css += f"""
section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child({i}) {{
    background: radial-gradient(circle at 30% 28%, rgba(255,255,255,.75) 0 12%, {hexa} 38%);
}}"""
n_plus = len(COLORES) + 1

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,600;1,500&family=Lora:ital@0;1&display=swap');
html, body, [class*="css"] {{ font-family: 'Lora', Georgia, serif; }}
h1, h2, h3, .titulo {{ font-family: 'Playfair Display', Georgia, serif !important; color: #1d3a78 !important; }}

/* Fondo: mesa de madera + elementos de arte */
.stApp {{
    background-color: #c9955c;
    background-image:
        {PALETA}, {TUBOS}, {PINCEL}, {LIBROS}, {CRAYONES}, {SALPICADURA},
        repeating-linear-gradient(8deg, rgba(120,70,30,.13) 0 2px, transparent 2px 38px),
        repeating-linear-gradient(-3deg, rgba(255,230,180,.16) 0 3px, transparent 3px 72px);
    background-repeat: no-repeat, no-repeat, no-repeat, no-repeat, no-repeat, no-repeat, repeat, repeat;
    background-position: 24rem 96%, 96% 3%, 97% 52%, 97% 97%, 24rem 4%, 60% 98%, 0 0, 0 0;
    background-attachment: fixed;
}}
header[data-testid="stHeader"] {{ background: transparent; }}

/* Barra lateral vertical, crema */
section[data-testid="stSidebar"] {{ background: #fdf3d9; border-right: 4px solid #1d3a78; }}
section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] p {{ color: #1d3a78; }}

/* Paleta de puras gotas */
section[data-testid="stSidebar"] div[role="radiogroup"] {{
    display: flex; flex-wrap: wrap; gap: 14px 12px; padding: 6px 4px 10px;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] > label {{
    width: 36px; height: 36px; min-width: 36px; margin: 0; padding: 0; cursor: pointer;
    border-radius: 50% 0 50% 50%; transform: rotate(-45deg);
    box-shadow: inset -4px -4px 7px rgba(0,0,0,.28), 0 2px 5px rgba(0,0,0,.35);
    transition: transform .15s;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child {{ display: none; }}
section[data-testid="stSidebar"] div[role="radiogroup"] > label p {{ font-size: 0; }}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {{ transform: rotate(-45deg) scale(1.15); }}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {{
    outline: 3px solid #1d3a78; outline-offset: 3px; transform: rotate(-45deg) scale(1.2);
}}
{gotas_css}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child({n_plus}) {{
    background: #fffdf4; border: 2px dashed #a86f38; box-shadow: none; position: relative;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child({n_plus})::after {{
    content: "+"; position: absolute; inset: 0; transform: rotate(45deg);
    text-align: center; line-height: 32px; font: 700 22px sans-serif; color: #a86f38;
}}

/* Libreta: tarjeta crema con marco azul */
.block-container {{
    max-width: 1100px; margin-top: 1.2rem; padding: 1.4rem 2rem 2rem;
    background: #fdf3d9; border: 6px solid #1d3a78; border-radius: 26px;
    box-shadow: 0 0 0 4px #0f2552, 0 14px 34px rgba(0,0,0,.4);
}}
.block-container iframe, .block-container canvas {{ border-radius: 4px; }}
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# Libreta (fondo del lienzo): papel con puntos, lomo y espiral
# ----------------------------------------------------------------------------
@st.cache_data
def libreta(w, h):
    img = Image.new("RGB", (w, h), PAPEL)
    d = ImageDraw.Draw(img, "RGBA")
    for x in range(18, w, 28):
        for y in range(18, h, 28):
            d.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(150, 145, 120, 255))
    cx = w // 2
    for k in range(40):  # sombra del lomo
        a = int(70 * (1 - k / 40))
        d.line((cx - k, 0, cx - k, h), fill=(70, 60, 35, a))
        d.line((cx + k, 0, cx + k, h), fill=(70, 60, 35, a))
    for y in range(14, h - 8, 36):  # anillas
        d.ellipse((cx - 18, y, cx + 18, y + 14), outline=(110, 120, 135, 255),
                  width=3, fill=(225, 230, 238, 255))
    return img

# ----------------------------------------------------------------------------
# Barra lateral
# ----------------------------------------------------------------------------
if "n_borrar" not in st.session_state:
    st.session_state.n_borrar = 0

with st.sidebar:
    st.markdown("## Color de tiza")
    eleccion = st.radio("Color", NOMBRES, label_visibility="collapsed")
    if eleccion == "+ Crear color":
        color = st.color_picker("Crea tu propio color", "#ff6b00")
        nombre = f"Color propio {color}"
    else:
        color = dict(COLORES)[eleccion]
        nombre = eleccion
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:8px;font-style:italic'>"
        f"<span style='width:20px;height:20px;border-radius:50%;background:{color};"
        f"border:2px solid #1d3a78;display:inline-block'></span>Pintando con: {nombre}</div>",
        unsafe_allow_html=True)

    st.markdown("## Trazo")
    modo = st.selectbox("Herramienta", list(MODOS))
    grosor = st.slider("Grosor de tiza", 1, 60, 8)
    borrador = st.checkbox("Usar borrador")

    st.markdown("## Lienzo")
    tam = st.select_slider("Tamaño del lienzo", list(LIENZOS), value="Mediano")

    if st.button("Limpiar lienzo", use_container_width=True):
        st.session_state.n_borrar += 1

    st.markdown("## Interpretación")
    api_key = st.text_input("Clave de OpenAI", type="password",
                            value=st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else "")

# ----------------------------------------------------------------------------
# Tablero
# ----------------------------------------------------------------------------
st.markdown("<h1 style='text-align:center;font-style:italic;margin-bottom:0'>Taller de arte</h1>"
            "<p style='text-align:center;font-style:italic;color:#1d3a78'>"
            "Tú eres el pintor: dibuja lo que quieras y la máquina lo interpretará.</p>",
            unsafe_allow_html=True)

w, h = LIENZOS[tam]
fondo = libreta(w, h)
trazo = "#%02x%02x%02x" % PAPEL if borrador else color

_, centro, _ = st.columns([1, 8, 1])
with centro:
    lienzo = st_canvas(
        fill_color="rgba(255,255,255,0)",
        stroke_width=grosor * 2 if borrador else grosor,
        stroke_color=trazo,
        background_image=fondo,
        height=h, width=w,
        drawing_mode=MODOS[modo],
        key=f"lienzo_{tam}_{st.session_state.n_borrar}",
        update_streamlit=True,
    )

# ----------------------------------------------------------------------------
# Acciones: guardar e interpretar
# ----------------------------------------------------------------------------
def imagen_final():
    if lienzo.image_data is None:
        return None
    capa = Image.fromarray(lienzo.image_data.astype("uint8"), "RGBA")
    base = fondo.convert("RGBA")
    base.alpha_composite(capa.resize(base.size))
    return base.convert("RGB")

c1, c2 = st.columns(2)
img = imagen_final()
with c1:
    if img is not None:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        st.download_button("Guardar como imagen", buf.getvalue(), "mi-dibujo.png",
                           "image/png", use_container_width=True)
with c2:
    interpretar = st.button("✦ Interpretar mi dibujo", use_container_width=True)

if interpretar:
    if not api_key:
        st.warning("Ingresa tu clave de OpenAI en la barra lateral.")
    elif img is None:
        st.info("Dibuja algo primero.")
    else:
        from openai import OpenAI
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        with st.spinner("Observando tu dibujo…"):
            try:
                r = OpenAI(api_key=api_key).chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=300,
                    messages=[{"role": "user", "content": [
                        {"type": "text", "text":
                         "Eres un crítico de arte amable y poético. Mira este dibujo hecho a mano. "
                         "Responde en español con: 1) un título para la obra, 2) qué crees que "
                         "representa, 3) una observación sobre colores y trazos, 4) una sugerencia "
                         "para continuar. Máximo 110 palabras, sin viñetas."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ]}],
                )
                st.markdown("### La mirada de la máquina")
                st.write(r.choices[0].message.content)
            except Exception as e:
                st.error(f"No se pudo interpretar el dibujo: {e}")
