import streamlit as st
import sqlite3
import pandas as pd
import base64
import os
import re

# 1. Configuración de página a ANCHO COMPLETO
st.set_page_config(page_title="Segunda Nacional Masculino 2026-27: Scouting", layout="wide")

# 2. Funciones de Base de Datos y Assets
@st.cache_data
def obtener_escudo_base64(nombre_corto):
    ruta = f"assets/ESCUDO_{nombre_corto}.png"
    if os.path.exists(ruta):
        with open(ruta, "rb") as f:
            datos = f.read()
            return base64.b64encode(datos).decode()
    return None

@st.cache_data
def obtener_foto_jugador_base64(nombre_jugador):
    nombre_archivo = str(nombre_jugador).replace(" ", "_")
    ruta = f"assets/{nombre_archivo}.png"
    if os.path.exists(ruta):
        with open(ruta, "rb") as f:
            datos = f.read()
            return base64.b64encode(datos).decode()
    return None

@st.cache_data
def cargar_partidos():
    try:
        conexion = sqlite3.connect("mi_liga.db")
        query = """
            SELECT id_partido, fecha, local_nombre, local_score, visitante_nombre, visitante_score 
            FROM partidos 
            ORDER BY fecha DESC
        """
        df = pd.read_sql(query, conexion)
        conexion.close()
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data
def cargar_equipos():
    try:
        conexion = sqlite3.connect("mi_liga.db")
        query = "SELECT id_equipo, nombre, nombre_corto, color FROM equipos WHERE id_equipo != 0 ORDER BY nombre ASC"
        df = pd.read_sql(query, conexion)
        conexion.close()
        return df
    except Exception:
        return pd.DataFrame()

def cargar_plantilla(id_equipo):
    try:
        conexion = sqlite3.connect("mi_liga.db")
        id_eq = int(id_equipo) 
        query = "SELECT dorsal, nombre FROM jugadores WHERE id_equipo = ?"
        df = pd.read_sql(query, conexion, params=(id_eq,))
        conexion.close()
        
        if not df.empty:
            df['dorsal_num'] = pd.to_numeric(df['dorsal'], errors='coerce')
            df = df.sort_values(by=['dorsal_num', 'nombre'], na_position='last')
        return df
    except Exception as e:
        st.error(f"Error de base de datos al cargar plantilla: {e}") 
        return pd.DataFrame()

@st.cache_data
def calcular_stats_tradicionales_liga(tipo="Totales"):
    try:
        conexion = sqlite3.connect("mi_liga.db")
        
        query_partidos = """
            SELECT id_equipo,
                   COUNT(id_partido) as partidos_jugados,
                   SUM(puntos_en_contra) as puntos_en_contra
            FROM (
                SELECT id_equipo_local as id_equipo, id_partido, puntos_visitante as puntos_en_contra FROM partidos
                UNION ALL
                SELECT id_equipo_visitante as id_equipo, id_partido, puntos_local as puntos_en_contra FROM partidos
            )
            GROUP BY id_equipo
        """
        df_partidos = pd.read_sql(query_partidos, conexion)

        query_stats = """
            SELECT 
                id_equipo,
                SUM(CASE WHEN idMove IN (93, 100) THEN 1 ELSE 0 END) as T2_anotados,
                SUM(CASE WHEN idMove IN (93, 100, 97) THEN 1 ELSE 0 END) as T2_intentados,
                SUM(CASE WHEN idMove = 94 THEN 1 ELSE 0 END) as T3_anotados,
                SUM(CASE WHEN idMove IN (94, 98) THEN 1 ELSE 0 END) as T3_intentados,
                SUM(CASE WHEN idMove = 92 THEN 1 ELSE 0 END) as TL_anotados,
                SUM(CASE WHEN idMove IN (92, 96) THEN 1 ELSE 0 END) as TL_intentados,
                SUM(CASE WHEN idMove = 104 THEN 1 ELSE 0 END) as Rebotes_Defensivos,
                SUM(CASE WHEN idMove = 101 THEN 1 ELSE 0 END) as Rebotes_Ofensivos,
                SUM(CASE WHEN idMove = 107 THEN 1 ELSE 0 END) as Asistencias,
                SUM(CASE WHEN idMove = 106 THEN 1 ELSE 0 END) as Pérdidas,
                SUM(CASE WHEN idMove = 103 THEN 1 ELSE 0 END) as Recuperaciones,
                SUM(CASE WHEN idMove = 102 THEN 1 ELSE 0 END) as Tapones,
                SUM(CASE WHEN idMove = 110 THEN 1 ELSE 0 END) as Faltas_recibidas,
                SUM(CASE WHEN idMove IN (109, 159, 160, 161, 162, 166, 540, 544, 565, 571) THEN 1 ELSE 0 END) as Faltas_cometidas
            FROM play_by_play
            WHERE id_equipo IS NOT NULL
            GROUP BY id_equipo
        """
        df_stats = pd.read_sql(query_stats, conexion)
        conexion.close()
        
        df = pd.merge(df_stats, df_partidos, on='id_equipo', how='inner')
        
        df['Puntos a favor'] = (df['T2_anotados'] * 2) + (df['T3_anotados'] * 3) + df['TL_anotados']
        df['Puntos en contra'] = df['puntos_en_contra']
        df['Rebotes totales'] = df['Rebotes_Defensivos'] + df['Rebotes_Ofensivos']
        
        cols_acumulables = [
            'Puntos a favor', 'Puntos en contra', 'Rebotes_Defensivos', 'Rebotes_Ofensivos', 'Rebotes totales',
            'Asistencias', 'Pérdidas', 'Recuperaciones', 'Tapones', 
            'T2_intentados', 'T2_anotados', 'T3_intentados', 'T3_anotados', 
            'TL_intentados', 'TL_anotados', 'Faltas_recibidas', 'Faltas_cometidas'
        ]
        
        if tipo == "Por Partido":
            for col in cols_acumulables:
                df[col] = (df[col] / df['partidos_jugados'].replace(0, 1)).round(1)
                
        df['%T2'] = ((df['T2_anotados'] / df['T2_intentados'].replace(0, pd.NA)) * 100).fillna(0).round(1)
        df['%T3'] = ((df['T3_anotados'] / df['T3_intentados'].replace(0, pd.NA)) * 100).fillna(0).round(1)
        df['%TL'] = ((df['TL_anotados'] / df['TL_intentados'].replace(0, pd.NA)) * 100).fillna(0).round(1)

        df.rename(columns={
            'Rebotes_Defensivos': 'Rebotes Defensivos', 'Rebotes_Ofensivos': 'Rebotes Ofensivos',
            'T2_intentados': 'T2 intentados', 'T2_anotados': 'T2 anotados',
            'T3_intentados': 'T3 intentados', 'T3_anotados': 'T3 anotados',
            'TL_intentados': 'TL intentados', 'TL_anotados': 'TL anotados',
            'Faltas_recibidas': 'Faltas recibidas', 'Faltas_cometidas': 'Faltas cometidas'
        }, inplace=True)

        invertir_rank = ['Puntos en contra', 'Pérdidas', 'Faltas cometidas']
        todas_categorias = cols_acumulables + ['%T2', '%T3', '%TL']
        todas_categorias = [c.replace('_', ' ') for c in todas_categorias]
        
        for col in todas_categorias:
            if col in df.columns:
                ascendente = True if col in invertir_rank else False
                df[f'{col}_rank'] = df[col].rank(ascending=ascendente, method='min').astype(int)
                
        return df
    except Exception as e:
        st.error(f"Error calculando estadísticas: {e}")
        return pd.DataFrame()


with st.sidebar:
    st.header("Navegación")
    menu = st.radio("Selecciona una vista:", ["Propio", "Liga", "Clasificación", "Próximo Rival"])

if 'submenu_liga' not in st.session_state:
    st.session_state.submenu_liga = 'Rankings'
if 'equipo_seleccionado' not in st.session_state:
    st.session_state.equipo_seleccionado = None

en_ficha_equipo = (menu == "Liga" and st.session_state.submenu_liga == "Equipos" and st.session_state.equipo_seleccionado is not None)

if not en_ficha_equipo:
    st.title("🏀 Segunda Nacional Masculino 2026-27: Scouting")


if menu == "Propio":
    st.markdown("### Mi Equipo")
    st.info("Sección en construcción.")

elif menu == "Liga":
    
    if not en_ficha_equipo:
        st.markdown("### Visión General de la Liga")
            
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("📊 Rankings", use_container_width=True):
                st.session_state.submenu_liga = 'Rankings'
                st.rerun()
        with col_btn2:
            if st.button("🛡️ Equipos", use_container_width=True):
                st.session_state.submenu_liga = 'Equipos'
                st.rerun()
                
        st.write("---")
    
    if st.session_state.submenu_liga == "Rankings":
        st.markdown("#### Últimos Resultados de la Jornada")
        df_partidos = cargar_partidos()

        if not df_partidos.empty:
            for index, fila in df_partidos.iterrows():
                col_local, col_vs, col_visitante, col_espacio = st.columns([2, 1, 2, 5])
                color_local = "#4CAF50" if fila['local_score'] > fila['visitante_score'] else "#E53935"
                color_visit = "#4CAF50" if fila['visitante_score'] > fila['local_score'] else "#E53935"
                
                with col_local:
                    st.markdown(f"**{fila['local_nombre']}**")
                    st.markdown(f"<h2 style='color: {color_local}; margin-top: -10px;'>{fila['local_score']}</h2>", unsafe_allow_html=True)
                with col_vs:
                    st.markdown("<h3 style='text-align: center; color: #888888; margin-top: 15px;'>VS</h3>", unsafe_allow_html=True)
                with col_visitante:
                    st.markdown(f"**{fila['visitante_nombre']}**")
                    st.markdown(f"<h2 style='color: {color_visit}; margin-top: -10px;'>{fila['visitante_score']}</h2>", unsafe_allow_html=True)
                    
                st.write("---")
        else:
            st.info("Aún no hay partidos registrados en la base de datos.")

    elif st.session_state.submenu_liga == "Equipos":
        if not en_ficha_equipo:
            st.markdown("#### Directorio de Equipos")
            df_equipos = cargar_equipos()

            if not df_equipos.empty:
                num_columnas = 4 
                for i in range(0, len(df_equipos), num_columnas):
                    columnas = st.columns(num_columnas)
                    for j in range(num_columnas):
                        if i + j < len(df_equipos):
                            equipo = df_equipos.iloc[i + j]
                            with columnas[j]:
                                nombre_corto = equipo['nombre_corto']
                                img_base64 = obtener_escudo_base64(nombre_corto)
                                if img_base64:
                                    grafico_equipo = f'<img src="data:image/png;base64,{img_base64}" style="max-width: 90px; max-height: 90px; object-fit: contain;">'
                                else:
                                    grafico_equipo = f'<div style="width: 80px; height: 80px; background-color: #CBD5E1; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #1A365D; font-weight: bold; font-size: 1.4rem; border: 2px solid #E2E8F0;">{nombre_corto[:3]}</div>'

                                st.markdown(f"""
                                <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px 10px 0 0; padding: 25px 15px 15px 15px; display: flex; flex-direction: column; align-items: center; justify-content: center; aspect-ratio: 1 / 1; border-bottom: none;">
                                    <div style="flex-grow: 1; display: flex; align-items: center; justify-content: center; width: 100%;">
                                        {grafico_equipo}
                                    </div>
                                    <div style="width: 100%; text-align: center; margin-top: 15px;">
                                        <h4 style="color: #1A365D; margin: 0 0 5px 0; font-size: 0.85rem; text-transform: uppercase; line-height: 1.2;">{equipo['nombre']}</h4>
                                        <p style="color: #64748B; margin: 0; font-size: 0.9rem; font-weight: bold;">{nombre_corto}</p>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                if st.button(f"Entrar", key=f"btn_eq_{equipo['id_equipo']}", use_container_width=True):
                                    st.session_state.equipo_seleccionado = equipo['id_equipo']
                                    st.rerun()
            else:
                st.info("No hay equipos registrados en la base de datos.")

        else:
            if st.button("⬅️ Volver al Directorio"):
                st.session_state.equipo_seleccionado = None
                st.rerun()
            
            df_equipos = cargar_equipos()
            equipo_actual = df_equipos[df_equipos['id_equipo'] == st.session_state.equipo_seleccionado].iloc[0]
            nombre_corto = equipo_actual['nombre_corto']
            img_base64 = obtener_escudo_base64(nombre_corto)
            color_equipo = equipo_actual['color'] if pd.notna(equipo_actual['color']) and str(equipo_actual['color']).strip() else "#1A365D"
            
            if img_base64:
                escudo_header = f'<img src="data:image/png;base64,{img_base64}" style="max-height: 80px; margin-right: 20px;">'
            else:
                escudo_header = f'<div style="width: 70px; height: 70px; background-color: #FFFFFF; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #1A365D; font-weight: bold; font-size: 1.2rem; margin-right: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">{nombre_corto[:3]}</div>'

            st.markdown(f"""
            <div style="background-color: {color_equipo}; border-radius: 12px; padding: 25px; display: flex; align-items: center; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                {escudo_header}
                <div>
                    <h1 style="color: #FFFFFF; margin: 0; font-size: 2rem; text-transform: uppercase; text-shadow: 1px 1px 3px rgba(0,0,0,0.5);">{equipo_actual['nombre']}</h1>
                    <span style="color: #FFFFFF; font-size: 1.1rem; font-weight: 600; letter-spacing: 2px; text-shadow: 1px 1px 3px rgba(0,0,0,0.5); opacity: 0.9;">{nombre_corto}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            if 'vista_equipo' not in st.session_state:
                st.session_state.vista_equipo = 'Plantilla'
                
            col_stats, col_plantilla = st.columns(2)
            with col_stats:
                if st.button("📊 Stats", key="btn_stats_eq", use_container_width=True):
                    st.session_state.vista_equipo = 'Stats'
            with col_plantilla:
                if st.button("👥 Plantilla", key="btn_plantilla_eq", use_container_width=True):
                    st.session_state.vista_equipo = 'Plantilla'
                    
            st.write("---")
            
            if st.session_state.vista_equipo == 'Stats':
                
                if 'sub_vista_stats' not in st.session_state:
                    st.session_state.sub_vista_stats = 'Stats tradicionales'
                    
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    if st.button("📉 Tradicionales", use_container_width=True): st.session_state.sub_vista_stats = 'Stats tradicionales'
                with c2:
                    if st.button("📈 Avanzadas", use_container_width=True): st.session_state.sub_vista_stats = 'Stats avanzadas'
                with c3:
                    if st.button("🔄 Quintetos", use_container_width=True): st.session_state.sub_vista_stats = 'Análisis de Quintetos'
                with c4:
                    if st.button("🔥 Estado de Forma", use_container_width=True): st.session_state.sub_vista_stats = 'Estado de Forma'
                
                st.markdown(f"### {st.session_state.sub_vista_stats}")
                
                if st.session_state.sub_vista_stats == 'Stats tradicionales':
                    
                    tipo_stat = st.radio("Formato de visualización:", ["Totales", "Por Partido"], horizontal=True, label_visibility="collapsed")
                    df_stats_liga = calcular_stats_tradicionales_liga(tipo=tipo_stat)
                    
                    if not df_stats_liga.empty:
                        stats_equipo = df_stats_liga[df_stats_liga['id_equipo'] == st.session_state.equipo_seleccionado]
                        
                        if not stats_equipo.empty:
                            stats = stats_equipo.iloc[0]
                            filas_html = ""
                            
                            categorias_mostrar = [
                                'Puntos a favor', 'Puntos en contra', 
                                'Rebotes Defensivos', 'Rebotes Ofensivos', 'Rebotes totales', 
                                'Asistencias', 'Pérdidas', 'Recuperaciones', 'Tapones', 
                                'T2 intentados', 'T2 anotados', '%T2', 
                                'T3 intentados', 'T3 anotados', '%T3', 
                                'TL intentados', 'TL anotados', '%TL', 
                                'Faltas recibidas', 'Faltas cometidas'
                            ]
                            
                            for i, cat in enumerate(categorias_mostrar):
                                valor = stats[cat]
                                ranking = stats.get(f'{cat}_rank', '-')
                                if '%' in cat: valor = f"{valor}%"
                                    
                                bg_color = "#FFFFFF" if i % 2 == 0 else "#F8FAFC"
                                color_rank = "#4CAF50" if ranking == 1 else "#1A365D"
                                font_weight = "bold" if ranking in [1, 2, 3] else "normal"
                                estrella = "⭐" if ranking == 1 else ""
                                
                                filas_html += f"""
                                <tr style="background-color: {bg_color}; border-bottom: 1px solid #E2E8F0;">
                                    <td style="padding: 12px 20px; font-weight: bold; color: #334155;">{cat}</td>
                                    <td style="padding: 12px 20px; color: #0F172A; font-size: 1.1rem; font-weight: 500;">{valor}</td>
                                    <td style="padding: 12px 20px; color: {color_rank}; font-weight: {font_weight};">{ranking}º {estrella}</td>
                                </tr>
                                """
                                
                            tabla_completa = f"""
                            <div style="box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-radius: 10px; overflow: hidden; border: 1px solid #E2E8F0; margin-top: 15px;">
                                <table style="width: 100%; border-collapse: collapse; text-align: left; font-family: sans-serif;">
                                    <thead>
                                        <tr style="background-color: #1A365D; color: white;">
                                            <th style="padding: 15px 20px; text-transform: uppercase; font-size: 0.85rem; letter-spacing: 1px; width: 40%;">Estadística</th>
                                            <th style="padding: 15px 20px; text-transform: uppercase; font-size: 0.85rem; letter-spacing: 1px; width: 30%;">Valor {tipo_stat}</th>
                                            <th style="padding: 15px 20px; text-transform: uppercase; font-size: 0.85rem; letter-spacing: 1px; width: 30%;">Posición en Liga</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {filas_html}
                                    </tbody>
                                </table>
                            </div>
                            """
                            
                            # LA MAGIA: Eliminamos todos los saltos de línea para que Markdown no lo interprete como código
                            html_limpio = re.sub(r'\n+', '', tabla_completa)
                            st.markdown(html_limpio, unsafe_allow_html=True)
                        else:
                            st.warning("No hay estadísticas registradas para este equipo.")
                else:
                    st.info(f"Sección en construcción: Datos de {st.session_state.sub_vista_stats.lower()}.")
                    
            elif st.session_state.vista_equipo == 'Plantilla':
                df_plantilla = cargar_plantilla(st.session_state.equipo_seleccionado)
                
                if not df_plantilla.empty:
                    num_columnas = 4
                    for i in range(0, len(df_plantilla), num_columnas):
                        columnas = st.columns(num_columnas)
                        for j in range(num_columnas):
                            if i + j < len(df_plantilla):
                                jugador = df_plantilla.iloc[i + j]
                                with columnas[j]:
                                    nombre_jugador = jugador['nombre']
                                    dorsal = jugador['dorsal'] if pd.notna(jugador['dorsal']) and str(jugador['dorsal']).strip() != '' else '-'
                                    foto_base64 = obtener_foto_jugador_base64(nombre_jugador)
                                    
                                    if foto_base64:
                                        grafico_jugador = f'<img src="data:image/png;base64,{foto_base64}" style="width: 100%; height: 200px; object-fit: cover; border-radius: 10px 10px 0 0;">'
                                    else:
                                        iniciales = "".join([p[0] for p in nombre_jugador.split()[:2]]).upper()
                                        grafico_jugador = f'<div style="width: 100%; height: 200px; background-color: #E2E8F0; border-radius: 10px 10px 0 0; display: flex; align-items: center; justify-content: center; color: #64748B; font-weight: bold; font-size: 3rem;">{iniciales}</div>'
                                    
                                    st.markdown(f"""
                                    <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; display: flex; flex-direction: column; align-items: center; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                                        {grafico_jugador}
                                        <div style="width: 100%; padding: 20px 15px; text-align: center; position: relative;">
                                            <div style="position: absolute; top: -20px; right: 15px; background-color: #1A365D; color: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; border: 3px solid #F8FAFC; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">{dorsal}</div>
                                            <h4 style="color: #1A365D; margin: 0; font-size: 1rem; line-height: 1.2;">{nombre_jugador}</h4>
                                        </div>
                                    </div>
                                    """, unsafe_allow_html=True)
                else:
                    st.warning("No se han encontrado jugadores para este equipo en la base de datos.")

elif menu == "Clasificación":
    st.markdown("### Clasificación General")
    st.info("Sección en construcción: Balance de victorias/derrotas de todos los equipos.")

elif menu == "Próximo Rival":
    st.markdown("### Scouting del Próximo Rival")
    st.info("Sección en construcción.")