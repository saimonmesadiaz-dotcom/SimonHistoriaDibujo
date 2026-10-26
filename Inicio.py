import base64
import html
import io
import random
import numpy as np
import streamlit as st
from PIL import Image, ImageFilter
from streamlit_drawable_canvas import st_canvas

# ---------------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Taller de Arte y Creación",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Constantes y Paletas de Pigmentos
# ---------------------------------------------------------------------------
TINTA = "#1A2B4C"  # Azul profundo institucional
SEL = "#E8851E"    # Naranja cálido de selección

SLOTS = [
    ("Azul Ultramar", "#1F5BC4"),
    ("Rojo Carmín", "#E0393E"),
    ("Verde Botánica", "#3E9E5F"),
    ("Amarillo Oro", "#F5C02A"),
    ("Naranja Taller", "#F28A2E"),
    ("Rosa Pastel", "#EE7FAE"),
    ("Morado Iris", "#7B4FB8"),
    ("Negro Carbón", "#26211F"),
    ("Turquesa", "#1FB5C5"),
    ("Celeste", "#6EC6F2"),
    ("Lima", "#A5C93B"),
    ("Café Siena", "#8A5530"),
    ("Burdeos", "#8E1F3D"),
    ("Blanco Tiza", "#FFFFFF"),
    None,  # Slot 14: Selector de color personalizado (+)
]
IDX_PERSONALIZADO = 14

GROSORES = [("Muy fino", 2), ("Fino", 5), ("Medio", 10), ("Grueso", 18), ("Brocha", 32)]
MUESTRA_GROSOR = [3, 6, 10, 15, 22]

HERRAMIENTAS = {"Pincel": "freedraw", "Línea": "line", "Rectángulo": "rect", "Círculo": "circle"}

PAPELES = ["Liso", "Rayado", "Cuadros", "Puntos"]
COLORES_PAPEL = [
    ("Hueso", "#FDFBF7"),
    ("Crema", "#F7F2E6"),
    ("Blanco Pura", "#FFFFFF"),
    ("Kraft", "#EAD7B7"),
]
MESAS = [
    ("Roble Cálido", "#D9B27C"),
    ("Nogal Oscuro", "#8C5A3C"),
    ("Cerezo Suave", "#C88A5E"),
]
ACABADOS = ["Normal", "Acuarela", "Tiza"]

FORMATOS = [
    ("Clásico", 720, 480),
    ("Panorámico", 840, 360),
    ("Cuadrado", 560, 560),
    ("Vertical", 460, 640),
]

# ---------------------------------------------------------------------------
# Inicialización del Estado
# ---------------------------------------------------------------------------
for clave, valor in {
    "lienzo": 0,
    "nota_titulo": "Mis Inspiraciones",
    "nota_texto": "Apunta aquí tus ideas, colores favoritos o el título de tu próxima obra...",
    "pig": 0,
    "gro": 2,
    "tool": 0,
    "papel": 0,
    "papel_color": 0,
    "mesa": 0,
    "acabado": 0,
    "custom_hex": "#E873A5",
    "lienzo_ancho": 720,
    "lienzo_alto": 480,
}.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor

# ---------------------------------------------------------------------------
# Utilidades de Color e Imagen
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

def imagen_del_lienzo(datos, papel_rgb):
    img = Image.fromarray(np.array(datos).astype("uint8"), "RGBA")
    fondo = Image.new("RGBA", img.size, tuple(papel_rgb) + (255,))
    fondo.alpha_composite(img)
    return fondo.convert("RGB")

def _desenfocar(a, radio):
    im = Image.fromarray(a.astype("uint8")).filter(ImageFilter.GaussianBlur(radio))
    return np.array(im).astype(np.float32)

def _ruido_suave(h, w, celda, rng):
    g = rng.random((h // celda + 2, w // celda + 2)).astype(np.float32)
    g = Image.fromarray((g * 255).astype("uint8")).resize((w, h), Image.BICUBIC)
    return np.array(g).astype(np.float32) / 255

def aplicar_acuarela(img, papel_rgb):
    arr = np.array(img.convert("RGB")).astype(np.float32)
    h, w, _ = arr.shape
    papel_arr = np.array(papel_rgb, dtype=np.float32)
    carga = np.clip(papel_arr - arr, 0, 255)
    lavado = _desenfocar(carga, 2.4)
    borde = np.clip(_desenfocar(carga, 1.0) - _desenfocar(carga, 6.0), 0, 255)
    rng = np.random.default_rng(7)
    grano = (0.78 + 0.44 * _ruido_suave(h, w, 6, rng))[..., None]
    total = (lavado * 0.95 + borde * 0.55) * grano
    fibra = rng.normal(0, 2.2, (h, w, 1)).astype(np.float32)
    return Image.fromarray(np.clip(papel_arr - total + fibra, 0, 255).astype("uint8"))

def aplicar_tiza(img, papel_rgb):
    arr = np.array(img.convert("RGB")).astype(np.float32)
    h, w, _ = arr.shape
    papel_arr = np.array(papel_rgb, dtype=np.float32)
    carga = np.clip(papel_arr - arr, 0, 255)
    suave = _desenfocar(carga, 1.1)
    rng = np.random.default_rng(11)
    fino = np.clip((rng.random((h, w, 1)).astype(np.float32) - 0.25) / 0.55, 0, 1)
    veta = (0.75 + 0.5 * _ruido_suave(h, w, 3, rng))[..., None]
    total = suave * (0.35 + 0.65 * fino) * veta
    return Image.fromarray(np.clip(papel_arr - total, 0, 255).astype("uint8"))

# ---------------------------------------------------------------------------
# Estilos CSS Exquisitos y Modernos
# ---------------------------------------------------------------------------
mesa_actual_hex = MESAS[st.session_state.mesa][1]
pigmento_actual = st.session_state.custom_hex if st.session_state.pig == IDX_PERSONALIZADO else SLOTS[st.session_state.pig][1]
papel_actual_hex = COLORES_PAPEL[st.session_state.papel_color][1]

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,600;0,700;1,600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

:root {{
    --tinta: {TINTA};
    --sel: {SEL};
    --mesa: {mesa_actual_hex};
    --papel: {papel_actual_hex};
}}

.stApp {{
    background-color: var(--mesa);
    background-image: radial-gradient(rgba(0,0,0,0.08) 1px, transparent 0);
    background-size: 24px 24px;
}}

[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stSidebar"] {{
    background: #FFFDF9;
    border-right: 1px solid rgba(0,0,0,0.08);
}}

/* Tipografía general */
h1, h2, h3, .atelier-title {{
    font-family: 'Playfair Display', Georgia, serif !important;
    color: var(--tinta);
}}
p, label, span, .stApp {{
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    color: var(--tinta);
}}

/* Tarjetas de taller estilizadas */
.atelier-card {{
    background: #FFFFFF;
    border: 1px solid rgba(26, 43, 76, 0.12);
    border-radius: 16px;
    padding: 20px;
    box-shadow: 0 10px 25px -5px rgba(0,0,0,0.05);
    margin-bottom: 1.2rem;
}}

/* Botones personalizados de herramientas */
.stButton button {{
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}}
.stButton button:hover {{
    border-color: var(--sel) !important;
    color: var(--sel) !important;
    transform: translateY(-1px);
}}

/* Lienzo marco de madera/cuaderno */
.canvas-container {{
    background: #FFFFFF;
    padding: 24px;
    border-radius: 16px;
    box-shadow: 0 20px 40px -10px rgba(0,0,0,0.15);
    display: flex;
    flex-direction: column;
    align-items: center;
    border: 1px solid rgba(0,0,0,0.08);
}}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Barra Lateral (Panel del Artista)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🎨 Rincón del Artista")
    st.markdown("Tu estudio creativo personal.")
    
    st.markdown("---")
    
    # 1. Selección de Herramientas
    st.markdown("### 🖌️ Herramienta")
    cols_tool = st.len = st.columns(2)
    for i, (nombre, val) in enumerate(HERRAMIENTAS.items()):
        col = cols_tool[i % 2]
        with col:
            if st.button(nombre, use_container_width=True, key=f"tool_{i}"):
                st.session_state.tool = i
    
    st.markdown("---")
    
    # 2. Paleta de Colores
    st.markdown("### 🎨 Paleta de Pigmentos")
    cols_paleta = st.columns(5)
    for i, slot in enumerate(SLOTS):
        col = cols_paleta[i % 5]
        with col:
            if slot is None:
                if st.button("➕", key=f"pig_{i}", help="Color personalizado"):
                    st.session_state.pig = i
            else:
                nombre_c, hex_c = slot
                if st.button(" ", key=f"pig_{i}", help=nombre_c):
                    st.session_state.pig = i
                    
    if st.session_state.pig == IDX_PERSONALIZADO:
        st.session_state.custom_hex = st.color_picker("Elige tu tono exclusivo", st.session_state.custom_hex)

    st.markdown("---")

    # 3. Grosor del Pincel
    st.markdown("### ✒️ Grosor del trazo")
    cols_gro = st.columns(len(GROSORES))
    for i, (nombre_g, val_g) in enumerate(GROSORES):
        with cols_gro[i]:
            if st.button(nombre_g[:3], key=f"gro_{i}", help=nombre_g, use_container_width=True):
                st.session_state.gro = i

    st.markdown("---")

    # 4. Configuración del Papel y Lienzo
    st.markdown("### 📄 Formato y Papel")
    
    f_opciones = [f[0] for f in FORMATOS]
    f_sel = st.selectbox("Formato del Lienzo", f_opciones, index=0)
    for nombre_f, w_f, h_f in FORMATOS:
        if nombre_f == f_sel:
            st.session_state.lienzo_ancho = w_f
            st.session_state.lienzo_alto = h_f

    p_col_opciones = [p[0] for p in COLORES_PAPEL]
    p_col_sel = st.selectbox("Tono del Papel", p_col_opciones, index=0)
    for idx_p, (nombre_pc, _) in enumerate(COLORES_PAPEL):
        if nombre_pc == p_col_sel:
            st.session_state.papel_color = idx_p

    mesa_sel = st.selectbox("Mesa de Trabajo", [m[0] for m in MESAS], index=0)
    for idx_m, (nombre_m, _) in enumerate(MESAS):
        if nombre_m == mesa_sel:
            st.session_state.mesa = idx_m

    st.markdown("---")

    # 5. La Libretica del Artista (Notas)
    st.markdown("### 📖 Libretica de Bocetos")
    st.session_state.nota_titulo = st.text_input("Título de la obra", st.session_state.nota_titulo)
    st.session_state.nota_texto = st.text_area("Notas o inspiración", st.session_state.nota_texto, height=100)


# ---------------------------------------------------------------------------
# Panel Principal (Área de Dibujo y Taller)
# ---------------------------------------------------------------------------
st.markdown(f"# 🖼️ Taller de Arte: *{st.session_state.nota_titulo}*")
st.markdown("Crea, experimenta con texturas y guarda tus creaciones maestras.")

# Controles superiores rápidos sobre el lienzo
col_acc1, col_acc2, col_acc3 = st.columns([2, 2, 4])
with col_acc1:
    acabado_sel = st.selectbox("Efecto / Acabado", ACABADOS, index=st.session_state.acabado)
    st.session_state.acabado = ACABADOS.index(acabado_sel)

with col_acc2:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🧹 Limpiar Lienzo", use_container_width=True):
        st.session_state.lienzo += 1
        st.rerun()

# Configuración del Canvas de Dibujo
ancho_canvas = st.session_state.lienzo_ancho
alto_canvas = st.session_state.lienzo_alto
herramienta_activa = list(HERRAMIENTAS.values())[st.session_state.tool]
grosor_activo = GROSORES[st.session_state.gro][1]

# Contenedor del Lienzo central
st.markdown('<div class="canvas-container">', unsafe_allow_html=True)

canvas_result = st_canvas(
    fill_color="rgba(255, 165, 0, 0.3)",
    stroke_width=grosor_activo,
    stroke_color=pigmento_actual,
    background_color=papel_actual_hex,
    update_streamlit=True,
    height=alto_canvas,
    width=ancho_canvas,
    drawing_mode=herramienta_activa,
    key=f"canvas_{st.session_state.lienzo}",
)

st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Procesamiento de Acabados y Exportación
# ---------------------------------------------------------------------------
if canvas_result.image_data is not None:
    papel_rgb = hex_a_rgb(papel_actual_hex)
    img_base = imagen_del_lienzo(canvas_result.image_data, papel_rgb)
    
    # Aplicar acabados artísticos si se seleccionan
    if st.session_state.acabado == 1:  # Acuarela
        img_final = aplicar_acuarela(img_base, papel_rgb)
    elif st.session_state.acabado == 2:  # Tiza
        img_final = aplicar_tiza(img_base, papel_rgb)
    else:
        img_final = img_base

    st.markdown("---")
    col_down1, col_down2 = st.columns(2)
    
    buf = io.BytesIO()
    img_final.save(buf, format="PNG")
    byte_im = buf.getvalue()

    with col_down1:
        st.download_button(
            label="📥 Descargar Obra de Arte (PNG)",
            data=byte_im,
            file_name=f"{st.session_state.nota_titulo.lower().replace(' ', '_')}.png",
            mime="image/png",
            use_container_width=True
        )
    with col_down2:
        st.success("✨ ¡Tu obra está lista para ser exhibida en la galería digital!")
