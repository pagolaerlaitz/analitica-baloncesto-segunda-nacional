import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import propio_bd as bd
from cancha import ARO, layout_cancha

# App de registro del play by play avanzado del equipo propio.
# Se arranca aparte de la app principal:  py -m streamlit run scripts/etiquetador.py --server.port 8502

st.set_page_config(page_title="Registro de partidos", layout="wide")

CANASTAS = (93, 94, 100)
TIROS_CAMPO = (93, 94, 97, 98, 100)

# Campos que se etiquetan en cada fase: (columna, etiqueta, tipo)
CAMPOS = {
    "Ataque": [
        ("playtype", "Playtype", "playtype"),
        ("playtype_secundario", "Secondary playtype", "playtype"),
        ("tipo_defensa", "Tipo de defensa", "tipo_defensa"),
        ("sistema", "Sistema", "sistema"),
        ("pr_handler", "P&R Handler", "jugador"),
        ("pr_roller", "P&R Roller", "jugador"),
        ("pr_defense", "P&R Defense", "pr_defense"),
        ("jugador_secundario", "Secondary player", "jugador"),
    ],
    "Defensa": [
        ("playtype", "Playtype", "playtype"),
        ("playtype_secundario", "Secondary playtype", "playtype"),
        ("tipo_defensa", "Tipo de defensa", "tipo_defensa"),
        ("defensor_pr_handler", "Defensor del P&R Handler", "jugador"),
        ("defensor_pr_roller", "Defensor del P&R Roller", "jugador"),
        ("pr_defense", "P&R Defense", "pr_defense"),
        ("id_defensor", "dPlayer", "jugador"),
    ],
}
TABLAS = {"Ataque": "propio_ataque", "Defensa": "propio_defensa"}
ICONOS_FASE = {"Ataque": "⚔️", "Defensa": "🛡️"}
COLORES_FASE = {"Ataque": "#F97316", "Defensa": "#525252"}

# Campos que solo aparecen con ciertos playtypes; si no aparecen, se guardan vacíos.
# Cada campo indica qué playtypes lo activan y si basta con el playtype principal o solo cuenta el secundario.
PLAYTYPES_PR = ("P&R Handler", "P&R Roller")
PLAYTYPES_1C1 = ("Isolation", "Post Up")
DEPENDENCIAS = {
    "pr_handler": (PLAYTYPES_PR, ("playtype", "playtype_secundario")),
    "pr_roller": (PLAYTYPES_PR, ("playtype", "playtype_secundario")),
    "jugador_secundario": (PLAYTYPES_1C1, ("playtype_secundario",)),
    "defensor_pr_handler": (PLAYTYPES_PR, ("playtype", "playtype_secundario")),
    "defensor_pr_roller": (PLAYTYPES_PR, ("playtype", "playtype_secundario")),
    "pr_defense": (PLAYTYPES_PR, ("playtype", "playtype_secundario")),
    "id_defensor": (PLAYTYPES_1C1, ("playtype", "playtype_secundario")),
}


# En ataque, el jugador que finaliza la acción es por defecto el handler o el roller según el playtype
JUGADOR_POR_PLAYTYPE = {"pr_handler": "P&R Handler", "pr_roller": "P&R Roller"}


def falta_sin_datos(uuid):
    """Falta de tiros libres que no se ha marcado como 'De tiro' (bonus o sin responder): no lleva más datos."""
    clave = f"tipo_falta_{uuid}"
    return clave in st.session_state and st.session_state[clave] != "De tiro"


def campo_visible(col, uuid):
    if falta_sin_datos(uuid):
        return False
    if col not in DEPENDENCIAS:
        return True
    playtypes, campos_playtype = DEPENDENCIAS[col]
    return any(st.session_state.get(f"{campo}_{uuid}") in playtypes for campo in campos_playtype)


# ------------------------------------------------------------------ CANCHA
@st.cache_data
def rejilla_cancha(paso=0.1):
    """Puntos invisibles cada 10 cm: al hacer clic se selecciona el más cercano."""
    xs, ys = np.meshgrid(np.arange(0, 15 + paso / 2, paso), np.arange(0, 14 + paso / 2, paso))
    return xs.ravel().round(2), ys.ravel().round(2)


def figura_cancha(tiro, es_canasta):
    xs, ys = rejilla_cancha()
    fig = go.Figure()
    fig.add_trace(go.Scattergl(
        x=xs, y=ys, mode="markers", marker=dict(size=6, color="rgba(0,0,0,0)"),
        hovertemplate="%{x:.1f} m, %{y:.1f} m<extra></extra>", showlegend=False,
    ))
    if tiro:
        fig.add_trace(go.Scatter(
            x=[tiro[0]], y=[tiro[1]], mode="markers", hoverinfo="skip", showlegend=False,
            marker=dict(size=18, symbol="circle" if es_canasta else "x",
                        color="#4CAF50" if es_canasta else "#E53935", line=dict(color="#FFFFFF", width=1)),
        ))
    layout_cancha(fig)
    fig.update_layout(dragmode=False, clickmode="event+select")
    return fig


# ------------------------------------------------------------------ DATOS
def cargar_partidos_propios(conexion, id_propio):
    df = pd.read_sql('''
        SELECT p.id_partido, p.jornada, p.fecha, p.puntos_local, p.puntos_visitante,
               el.nombre_corto AS local, ev.nombre_corto AS visitante
        FROM partidos p
        JOIN equipos el ON el.id_equipo = p.id_equipo_local
        JOIN equipos ev ON ev.id_equipo = p.id_equipo_visitante
        WHERE ? IN (p.id_equipo_local, p.id_equipo_visitante)
    ''', conexion, params=(id_propio,))
    # Orden cronológico: la fecha viene como texto ("Oct 4, 2026, 8:00:00 PM")
    fecha_limpia = df["fecha"].str.replace(" ", " ").str.replace(",", "")
    df["fecha_dt"] = pd.to_datetime(fecha_limpia, format="%b %d %Y %I:%M:%S %p", errors="coerce")
    return df.sort_values("fecha_dt").reset_index(drop=True)


def etiqueta_partido(r):
    jornada = f"J{r.jornada}" if str(r.jornada).isdigit() else r.jornada
    fecha = r.fecha_dt.strftime("%d/%m") if pd.notna(r.fecha_dt) else ""
    return f"{jornada} · {fecha} · {r.local} {r.puntos_local}-{r.puntos_visitante} {r.visitante}"


def cargar_nombres(conexion):
    df = pd.read_sql("SELECT id_jugador, dorsal, nombre FROM jugadores", conexion)
    return {int(r.id_jugador): f"{r.dorsal if pd.notna(r.dorsal) and str(r.dorsal).strip() else '-'} - {r.nombre}"
            for r in df.itertuples()}


def cargar_dorsales(conexion):
    """Dorsal numérico de cada jugador, para ordenar; los que no tienen dorsal van al final."""
    dorsales = {}
    for id_jugador, dorsal in conexion.execute("SELECT id_jugador, dorsal FROM jugadores"):
        try:
            dorsales[int(id_jugador)] = int(dorsal)
        except (TypeError, ValueError):
            dorsales[int(id_jugador)] = 999
    return dorsales


def formato_tiempo(minuto, segundo):
    return f"{int(minuto or 0):02d}:{int(segundo or 0):02d}"


# ------------------------------------------------------------------ CALLBACKS
def motivo_bloqueo(fila):
    """Qué falta para poder guardar o avanzar (None si no falta nada). Se comprueba al pulsar el botón,
    con lo que hay en session_state en ese momento (incluido el clic en la cancha)."""
    if falta_sin_tipo(fila):
        return "Indica si la falta es por bonus o en acción de tiro para poder guardar y avanzar."
    if requiere_ubicacion(fila) and not tiene_ubicacion(fila):
        return "📍 Marca en la cancha dónde se lanzó el tiro para poder guardar y avanzar."
    return None


def mover(clave_idx, destino, fila=None):
    # Hacia delante (con fila) no se avanza si falta la ubicación del tiro o el tipo de falta
    motivo = motivo_bloqueo(fila) if fila is not None else None
    if motivo:
        st.session_state["aviso_etiquetador"] = motivo
        return
    st.session_state[clave_idx] = destino


def borrar_tiro(uuid):
    st.session_state[f"tiro_{uuid}"] = None
    st.session_state[f"cancha_n_{uuid}"] = st.session_state.get(f"cancha_n_{uuid}", 0) + 1


def requiere_ubicacion(fila):
    """La ubicación del tiro es obligatoria en los tiros de campo y en las faltas en acción de tiro
    (no en pérdidas ni en faltas por bonus)."""
    if fila["idMove"] in TIROS_CAMPO:
        return True
    clave_falta = f"tipo_falta_{fila['eventUuid']}"
    tipo_falta = st.session_state[clave_falta] if clave_falta in st.session_state else fila["tipo_falta"]
    return fila["idMove"] in bd.FALTAS_DEFENSIVAS and tipo_falta == "De tiro"


def falta_sin_tipo(fila):
    """Falta con tiros libres sin responder si es por bonus o de tiro (no se sabe si hace falta la ubicación)."""
    if fila["idMove"] not in bd.FALTAS_DEFENSIVAS:
        return False
    clave_falta = f"tipo_falta_{fila['eventUuid']}"
    tipo_falta = st.session_state[clave_falta] if clave_falta in st.session_state else fila["tipo_falta"]
    return tipo_falta not in bd.TIPOS_FALTA


def tiene_ubicacion(fila):
    clave_tiro = f"tiro_{fila['eventUuid']}"
    if clave_tiro in st.session_state:
        return st.session_state[clave_tiro] is not None
    return pd.notna(fila["tiro_x"])


def guardar(tabla, fase, uuid, clave_idx, destino, fila):
    motivo = motivo_bloqueo(fila)
    if motivo:
        # No se guarda ni se avanza: se avisa de lo que falta
        st.session_state["aviso_etiquetador"] = motivo
        return
    valores = {col: st.session_state.get(f"{col}_{uuid}") if campo_visible(col, uuid) else None
               for col, _, _ in CAMPOS[fase]}
    if f"tipo_falta_{uuid}" in st.session_state:
        valores["tipo_falta"] = st.session_state[f"tipo_falta_{uuid}"]
    tiro = st.session_state.get(f"tiro_{uuid}") if not falta_sin_datos(uuid) else None
    valores["tiro_x"], valores["tiro_y"] = tiro if tiro else (None, None)
    asignaciones = ", ".join(f"{col} = ?" for col in valores)
    conexion = bd.conectar()
    conexion.execute(f"UPDATE {tabla} SET {asignaciones} WHERE eventUuid = ?", (*valores.values(), uuid))
    conexion.commit()
    conexion.close()
    st.session_state["mensaje"] = "Jugada guardada."
    if destino is not None:
        st.session_state[clave_idx] = destino


# ------------------------------------------------------------------ INTERFAZ
conexion = bd.conectar()
bd.crear_tablas_propio(conexion)
id_propio = bd.obtener_id_equipo_propio(conexion)
if id_propio is None:
    st.error(f"No se encuentra el equipo '{bd.NOMBRE_EQUIPO_PROPIO}' en la base de datos.")
    st.stop()

df_partidos = cargar_partidos_propios(conexion, id_propio)
if df_partidos.empty:
    st.info("Todavía no hay partidos del equipo propio en la base de datos.")
    st.stop()

st.title("📝 Registro de partidos")
etiquetas_partido = {r.id_partido: etiqueta_partido(r) for r in df_partidos.itertuples()}
# Por defecto, el primer partido de la temporada
id_partido = st.selectbox("Partido a etiquetar", list(etiquetas_partido), format_func=etiquetas_partido.get, index=0)

with st.sidebar:
    st.header("Opciones")
    solo_pendientes = st.checkbox("Al guardar, saltar a la siguiente pendiente", value=True)

bd.preparar_partido(conexion, id_partido)
# Ataques y defensas juntos, en el orden en que ocurrieron en el partido
partes = []
for fase_tabla, nombre_tabla in TABLAS.items():
    parte = pd.read_sql(f"SELECT * FROM {nombre_tabla} WHERE id_partido = ?", conexion, params=(id_partido,))
    parte["fase"] = fase_tabla
    partes.append(parte)
df = pd.concat(partes, ignore_index=True).sort_values("orden").reset_index(drop=True)
nombres = cargar_nombres(conexion)
dorsales = cargar_dorsales(conexion)
sistemas_previos = [r[0] for r in conexion.execute(
    "SELECT DISTINCT sistema FROM propio_ataque WHERE sistema IS NOT NULL AND sistema != '' ORDER BY sistema")]
conexion.close()

if df.empty:
    st.info("Este partido no tiene jugadas.")
    st.stop()

# Una posesión está etiquetada si tiene playtype, o si es una falta por bonus (que no lleva más datos)
etiquetada = df["playtype"].notna() | (df["tipo_falta"] == "Bonus")
with st.sidebar:
    st.progress(etiquetada.mean(), text=f"{int(etiquetada.sum())} de {len(df)} posesiones etiquetadas")
    for fase_tabla in TABLAS:
        de_fase = df["fase"] == fase_tabla
        st.caption(f"{ICONOS_FASE[fase_tabla]} {fase_tabla}: {int(etiquetada[de_fase].sum())} de {int(de_fase.sum())}")

nombre_jugador = lambda j: nombres.get(int(j), "Desconocido") if pd.notna(j) else "—"
etiquetas_jugada = [
    f"{'✅' if etiquetada[i] else '⬜'} {ICONOS_FASE[r.fase]} {r.period}º {formato_tiempo(r.min, r.sec)} · "
    f"{r.move} · {nombre_jugador(r.id_jugador)}"
    for i, r in enumerate(df.itertuples())
]

clave_idx = f"idx_{id_partido}"
if clave_idx not in st.session_state:
    pendientes = np.flatnonzero(~etiquetada.to_numpy())
    st.session_state[clave_idx] = int(pendientes[0]) if len(pendientes) else 0

idx = st.session_state[clave_idx]
fila = df.iloc[idx]
uuid = fila["eventUuid"]
fase = fila["fase"]
tabla = TABLAS[fase]

# Destino al guardar: la siguiente jugada (o la siguiente pendiente)
siguientes = [i for i in range(idx + 1, len(df)) if not (solo_pendientes and etiquetada[i])]
destino_guardar = siguientes[0] if siguientes else None

col_prev, col_sel, col_next = st.columns([1, 8, 1])
col_prev.button("⬅️", use_container_width=True, disabled=idx == 0, on_click=mover, args=(clave_idx, idx - 1))
col_sel.selectbox("Jugada", range(len(df)), format_func=lambda i: etiquetas_jugada[i], key=clave_idx,
                  label_visibility="collapsed")
# Al avanzar se comprueba que no falte la ubicación del tiro ni el tipo de falta (si falta, se avisa y no avanza)
col_next.button("➡️", use_container_width=True, disabled=idx == len(df) - 1,
                on_click=mover, args=(clave_idx, idx + 1, fila))

if st.session_state.pop("mensaje", None):
    st.toast("Jugada guardada", icon="💾")

# Ficha de la jugada con los datos de la federación
quinteto_propio = ", ".join(nombre_jugador(j) for j in bd.ids_quinteto(fila["quinteto_propio"]))
quinteto_rival = ", ".join(nombre_jugador(j) for j in bd.ids_quinteto(fila["quinteto_rival"]))
st.markdown(f"""
<div style="background-color: rgba(255,255,255,0.05); border: 1px solid #3F3F3F; border-radius: 10px; padding: 15px 20px; margin: 10px 0 20px 0;">
  <div style="display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap;">
    <span>
      <span style="background-color: {COLORES_FASE[fase]}; color: #FFFFFF; font-weight: bold; padding: 3px 10px; border-radius: 6px; margin-right: 10px; text-transform: uppercase; font-size: 0.9rem;">{ICONOS_FASE[fase]} {fase}</span>
      <span style="color: #FFFFFF; font-size: 1.3rem; font-weight: bold;">{fila['move']}</span>
    </span>
    <span style="color: #D4D4D4;">{fila['period']}º cuarto · {formato_tiempo(fila['min'], fila['sec'])} · Marcador {fila['marcador_local']}-{fila['marcador_visitante']}</span>
  </div>
  <div style="color: #FFFFFF; font-size: 1.1rem; margin-top: 5px;">{nombre_jugador(fila['id_jugador'])}</div>
  <div style="color: #A3A3A3; font-size: 0.85rem; margin-top: 8px;"><b>Atlético:</b> {quinteto_propio or '—'}</div>
  <div style="color: #A3A3A3; font-size: 0.85rem;"><b>Rival:</b> {quinteto_rival or '—'}</div>
</div>
""", unsafe_allow_html=True)

col_form, col_cancha = st.columns([2, 3])

with col_form:
    # Solo los jugadores del Atlético en pista en el momento de la jugada, por dorsal
    opciones_jugadores = sorted(bd.ids_quinteto(fila["quinteto_propio"]), key=lambda j: (dorsales.get(j, 999), j))

    # Faltas con tiros libres: primero se pregunta si es por bonus o en acción de tiro
    es_falta = fila["idMove"] in bd.FALTAS_DEFENSIVAS
    if es_falta:
        valor_falta = fila["tipo_falta"] if fila["tipo_falta"] in bd.TIPOS_FALTA else None
        st.radio("¿Falta por bonus o en acción de tiro?", bd.TIPOS_FALTA, horizontal=True,
                 index=bd.TIPOS_FALTA.index(valor_falta) if valor_falta else None, key=f"tipo_falta_{uuid}")
        if st.session_state[f"tipo_falta_{uuid}"] is None:
            st.info("Elige el tipo de falta para continuar.")
        elif st.session_state[f"tipo_falta_{uuid}"] == "Bonus":
            st.caption("Falta por bonus: no hace falta introducir más datos.")

    # Los desplegables empiezan vacíos (index=None) si la jugada no tiene ese dato; la "x" los vacía
    for col, etiqueta, tipo in CAMPOS[fase]:
        # Los playtypes se dibujan antes que sus dependientes, así que su valor ya está en session_state
        if not campo_visible(col, uuid):
            continue
        valor = fila[col] if pd.notna(fila[col]) else None
        clave = f"{col}_{uuid}"
        if tipo == "playtype":
            opciones = bd.PLAYTYPES
            st.selectbox(etiqueta, opciones, index=opciones.index(valor) if valor in opciones else None,
                         placeholder="—", key=clave)
        elif tipo == "pr_defense":
            opciones = bd.PR_DEFENSAS
            st.selectbox(etiqueta, opciones, index=opciones.index(valor) if valor in opciones else None,
                         placeholder="—", key=clave)
        elif tipo == "tipo_defensa":
            opciones = bd.TIPOS_DEFENSA
            st.selectbox(etiqueta, opciones,
                         index=opciones.index(valor if valor in opciones else bd.TIPO_DEFENSA_POR_DEFECTO), key=clave)
        elif tipo == "sistema":
            # Primero la lista fija; después, los sistemas nuevos que se hayan escrito en otras jugadas
            opciones = bd.SISTEMAS + [s for s in sistemas_previos if s not in bd.SISTEMAS]
            if valor and valor not in opciones:
                opciones.append(valor)
            st.selectbox(etiqueta, opciones, index=opciones.index(valor) if valor else None,
                         placeholder="Elige o escribe un sistema", accept_new_options=True, key=clave,
                         help="Elige uno de la lista o escribe uno nuevo.")
        else:
            valor = int(valor) if valor is not None else None
            indice_api = False
            # Si el playtype es P&R Handler/Roller, ese campo se rellena con el jugador que finaliza la acción.
            # Si después cambia el playtype, el relleno automático se retira (salvo que se haya cambiado a mano).
            clave_auto = f"auto_{clave}"
            playtype_actual = st.session_state.get(f"playtype_{uuid}")
            if col in JUGADOR_POR_PLAYTYPE:
                actual = st.session_state.get(clave, valor)
                if JUGADOR_POR_PLAYTYPE[col] == playtype_actual and actual is None and pd.notna(fila["id_jugador"]):
                    valor = int(fila["id_jugador"])
                    st.session_state[clave_auto] = valor
                    if clave in st.session_state:
                        # El campo ya estaba visible y vacío: se rellena a través de session_state
                        st.session_state[clave] = valor
                        indice_api = True
                elif JUGADOR_POR_PLAYTYPE[col] != playtype_actual and st.session_state.get(clave_auto) is not None:
                    if actual == st.session_state.pop(clave_auto):
                        valor = None
                        if clave in st.session_state:
                            st.session_state[clave] = None
                            indice_api = True
            opciones = opciones_jugadores + ([valor] if valor is not None and valor not in opciones_jugadores else [])
            indice = opciones.index(valor) if valor is not None and not indice_api else None
            st.selectbox(etiqueta, opciones, index=indice,
                         format_func=nombre_jugador, placeholder="—", key=clave,
                         help="Jugadores del Atlético en pista en ese momento, por dorsal.")

def dibujar_cancha():
    if falta_sin_datos(uuid):
        st.caption("La localización del tiro se pide si la falta es en acción de tiro.")
        return

    clave_tiro = f"tiro_{uuid}"
    if clave_tiro not in st.session_state:
        st.session_state[clave_tiro] = (fila["tiro_x"], fila["tiro_y"]) if pd.notna(fila["tiro_x"]) else None
    tiro = st.session_state[clave_tiro]

    es_tiro = fila["idMove"] in TIROS_CAMPO or es_falta
    st.markdown("**Localización del tiro**" + (" _(obligatoria)_" if es_tiro else " _(opcional: esta jugada no es un tiro de campo)_"))
    evento = st.plotly_chart(
        figura_cancha(tiro, fila["idMove"] in CANASTAS),
        key=f"cancha_{uuid}_{st.session_state.get(f'cancha_n_{uuid}', 0)}",
        on_select="rerun", selection_mode="points", use_container_width=True,
        config={"displayModeBar": False},
    )
    puntos = evento.selection.points if evento and evento.selection else []
    if puntos:
        nuevo = (round(float(puntos[-1]["x"]), 2), round(float(puntos[-1]["y"]), 2))
        if nuevo != tiro:
            st.session_state[clave_tiro] = nuevo
            st.rerun()

    if tiro:
        distancia = math.hypot(tiro[0] - ARO[0], tiro[1] - ARO[1])
        c1, c2 = st.columns([3, 1])
        c1.caption(f"X = {tiro[0]:.2f} m · Y = {tiro[1]:.2f} m · {distancia:.2f} m del aro")
        c2.button("Borrar punto", on_click=borrar_tiro, args=(uuid,), use_container_width=True)
    else:
        st.caption("Haz clic en la cancha para marcar dónde se lanzó el tiro.")


with col_cancha:
    dibujar_cancha()

# El aviso solo aparece si se ha intentado guardar o avanzar sin completar la jugada (y se borra al leerlo)
aviso = st.session_state.pop("aviso_etiquetador", None)
if aviso and motivo_bloqueo(fila):
    st.warning(aviso)
st.button("💾 Guardar" + (" y siguiente" if destino_guardar is not None else ""), type="primary",
          use_container_width=True, on_click=guardar, args=(tabla, fase, uuid, clave_idx, destino_guardar, fila))
