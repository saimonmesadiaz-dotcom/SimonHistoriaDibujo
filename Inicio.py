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

