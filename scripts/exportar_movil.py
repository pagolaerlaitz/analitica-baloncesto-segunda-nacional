"""Exporta los datos de la app de Streamlit a archivos JSON para la app móvil (carpeta app_movil).

Ejecutar después de actualizar mi_liga.db (y de etiquetar partidos):
    py scripts/exportar_movil.py
Reutiliza los cálculos de app.py y de las secciones, así que la app móvil da los mismos números.
"""
import json
import logging
import math
import os
import shutil
import sys
import types
import warnings
from datetime import datetime
from types import SimpleNamespace

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

import numpy as np
import pandas as pd

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(SCRIPTS)  # raíz del repositorio: datos, assets y app_movil
os.chdir(RAIZ)
sys.path.insert(0, SCRIPTS)
APP_MOVIL = os.path.join(RAIZ, "app_movil")
DATOS = os.path.join(APP_MOVIL, "data")
IMAGENES = os.path.join(APP_MOVIL, "img")


def cargar_app():
    """Ejecuta app.py hasta la marca de la interfaz: define los cálculos sin dibujar la app."""
    codigo = open(os.path.join(SCRIPTS, "app.py"), encoding="utf-8").read()
    corte = codigo.index("# ==== INTERFAZ ====")
    modulo = types.ModuleType("app")
    modulo.__file__ = os.path.join(SCRIPTS, "app.py")
    exec(compile(codigo[:corte], "app.py", "exec"), modulo.__dict__)
    return modulo


app = cargar_app()
import seccion_cuartos as sc  # noqa: E402
import seccion_partidos as sp  # noqa: E402
import seccion_propio as spr  # noqa: E402
import propio_bd as bd  # noqa: E402


# ------------------------------------------------------------------ UTILIDADES
def limpio(valor):
    """Convierte a tipos JSON: NaN/NA -> None, numpy -> Python, floats redondeados."""
    if isinstance(valor, dict):
        return {str(k): limpio(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set, frozenset)):
        return [limpio(v) for v in valor]
    if valor is None or valor is pd.NA or valor is pd.NaT:
        return None
    if isinstance(valor, (np.integer,)):
        return int(valor)
    if isinstance(valor, (np.bool_, bool)):
        return bool(valor)
    if isinstance(valor, (float, np.floating)):
        return None if math.isnan(valor) or math.isinf(valor) else round(float(valor), 4)
    return valor


def guardar(ruta, datos):
    ruta = os.path.join(DATOS, ruta)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(limpio(datos), f, ensure_ascii=False, separators=(",", ":"))


def num(valor):
    try:
        return None if pd.isna(valor) else float(valor)
    except (TypeError, ValueError):
        return None


def filas_resumen(df, columna, vacio="—"):
    """Posesiones, frecuencia, puntos y PPP agrupando por `columna` (como resumen_por de la sección Propio)."""
    res = spr.resumen_por(df, columna, vacio=vacio)
    return [{"g": str(r.grupo), "n": int(r.posesiones), "f": r.frecuencia, "pts": int(r.puntos), "ppp": r.ppp}
            for r in res.itertuples()]


def resumen_total(df):
    return {"n": len(df), "ppp": df["puntos"].sum() / len(df) if len(df) else None}


# ------------------------------------------------------------------ EQUIPOS, IMÁGENES Y DEFINICIONES
def exportar_meta(equipos, id_propio):
    tablas_estadistica = [{"titulo": titulo, "indicadores": [
        {"clave": c, "nombre": n, "def": d, "mejor": m, "formato": spr.FORMATO_ESTADISTICA.get(c, "{:.1f}%")}
        for c, n, d, m in indicadores]} for titulo, indicadores in spr.TABLAS_ESTADISTICA]
    tablas_individuales = [{"titulo": titulo, "columnas": [[c, p] for c, p in config["columnas"]],
                            "rating": config["rating_col"]} for titulo, config in app.TABLAS_INDIVIDUALES.items()]
    guardar("meta.json", {
        "actualizado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "id_propio": id_propio,
        "equipos": equipos,
        "def_equipo": app.DEFINICIONES_STATS,
        "def_jugador": app.DEFINICIONES_STATS_JUGADOR,
        "tablas_estadistica": tablas_estadistica,
        "tablas_individuales": tablas_individuales,
    })


def copiar_imagenes(equipos, jugadores):
    os.makedirs(os.path.join(IMAGENES, "escudos"), exist_ok=True)
    os.makedirs(os.path.join(IMAGENES, "jugadores"), exist_ok=True)
    for e in equipos:
        origen = os.path.join("assets", f"ESCUDO_{e['corto']}.png")
        e["escudo"] = os.path.exists(origen)
        if e["escudo"]:
            shutil.copyfile(origen, os.path.join(IMAGENES, "escudos", f"{e['corto']}.png"))
    con_foto = set()
    for j in jugadores.itertuples():
        origen = os.path.join("assets", f"{str(j.nombre).replace(' ', '_')}.png")
        if os.path.exists(origen):
            shutil.copyfile(origen, os.path.join(IMAGENES, "jugadores", f"{int(j.id_jugador)}.png"))
            con_foto.add(int(j.id_jugador))
    return con_foto


# ------------------------------------------------------------------ CLASIFICACIÓN Y PARTIDOS
def exportar_clasificacion():
    tabla_c, _ = app.calcular_clasificacion()
    guardar("clasificacion.json", [
        {"pos": r.posicion, "id": r.id_equipo, "pts": r.pts, "pj": r.pj, "v": r.v, "d": r.d, "pf": r.pf, "pc": r.pc,
         "dif": r.dif} for r in tabla_c.itertuples()])


COLUMNAS_BOX = ["seg", "pts", "tlm", "tla", "t2m", "t2a", "t3m", "t3a", "fp", "fr", "ast", "per", "rec", "tap", "ro",
                "rd", "rt", "val"]


def exportar_partido(p):
    eventos, convocatorias = sp.cargar_partido(p.id_partido)
    if eventos.empty:
        return None
    tramos = sp.intervalos_en_pista(eventos, convocatorias, p.id_equipo_local, p.id_equipo_visitante)

    finales = eventos.groupby("period")[["ml", "mv"]].max().cummax()
    parciales = finales.diff().fillna(finales).astype(int)
    periodos = ["1º", "2º", "3º", "4º"] + [f"PR{i}" for i in range(1, 10)]

    # Evolución del marcador: solo los momentos en que cambia
    puntos = [[0, 0, 0]]
    for t, ml, mv in eventos[["t", "ml", "mv"]].itertuples(index=False):
        if [ml, mv] != puntos[-1][1:]:
            puntos.append([int(t), int(ml), int(mv)])
    diferencias = pd.Series([0] + [a - b for _, a, b in puntos[1:]])
    empates, ventaja_l, ventaja_v, cambios = sp.datos_marcador(diferencias)

    boxscore, conteos = {}, {}
    for lado, id_eq, es_local in (("local", p.id_equipo_local, True), ("visitante", p.id_equipo_visitante, False)):
        df = sp.estadisticas_jugadores(eventos, convocatorias, tramos, id_eq, es_local)
        filas = [] if df.empty else [
            {"id": int(r.id_jugador), "dorsal": r.dorsal, "nombre": r.nombre, "titular": bool(r.titular),
             "mm": int(r.mas_menos), **{c: getattr(r, c) for c in COLUMNAS_BOX}} for r in df.itertuples()]
        totales = sp.totales_equipo(eventos, id_eq, df)
        boxscore[lado] = {"jugadores": filas, "totales": {c: totales[c] for c in COLUMNAS_BOX}}
        ev = eventos[eventos["id_equipo"] == id_eq]
        conteos[lado] = pd.Series({k: int(ev["idMove"].isin(m).sum()) for k, m in spr.CONTEOS.items()})
    minutos = sp.inicio_periodo(int(eventos["period"].max()) + 1) / 60

    # Rotación (tramos en pista / banquillo con su +/-) y quintetos, de cada equipo
    rotacion, quintetos = {}, {}
    for lado, id_eq, es_local in (("local", p.id_equipo_local, True), ("visitante", p.id_equipo_visitante, False)):
        col_pista, pts_pro, pts_con = ("pista_l", "pts_l", "pts_v") if es_local else ("pista_v", "pts_v", "pts_l")
        propio, rival = ("_l", "_v") if es_local else ("_v", "_l")
        df = sp.estadisticas_jugadores(eventos, convocatorias, tramos, id_eq, es_local)
        jugaron = df[df["seg"] > 0].sort_values("dorsal_num") if not df.empty else df
        filas = []
        for r in jugaron.itertuples():
            en_pista = tramos[col_pista].apply(lambda s, j=r.id_jugador: j in s)
            on, off = sp.ratings_tramos(tramos[en_pista], propio, rival), sp.ratings_tramos(tramos[~en_pista], propio, rival)
            filas.append({"id": int(r.id_jugador), "etiqueta": f"{r.dorsal} - {r.nombre}", "seg": r.seg,
                          "stints": [[t0, t1, int(en), int(dif)] for t0, t1, en, dif in
                                     sp.stints(tramos, col_pista, pts_pro, pts_con, r.id_jugador)],
                          "on": on, "off": off})
        rotacion[lado] = filas

        jugadores = convocatorias[convocatorias["id_equipo"] == id_eq]
        dorsales = {int(r.id_jugador): r.dorsal for r in jugadores.itertuples()}
        apellidos = {int(r.id_jugador): str(r.nombre).split()[-1] for r in jugadores.itertuples()}
        duracion = tramos["t1"] - tramos["t0"]
        validos = tramos[(tramos[col_pista].apply(len) == 5) & (duracion > 0)]
        segundos = validos.assign(seg=duracion).groupby(col_pista)["seg"].sum().sort_values(ascending=False)
        filas_q = []
        for quinteto, seg in segundos.items():
            en_pista = tramos[col_pista].apply(lambda s, q=quinteto: s == q)
            orden = sorted(quinteto, key=lambda j: (int(dorsales[j]) if str(dorsales.get(j, "")).isdigit() else 999, j))
            filas_q.append({"etiqueta": ", ".join(f"{dorsales.get(j, '-')} {apellidos.get(j, j)}" for j in orden), "seg": seg,
                            "on": sp.ratings_tramos(tramos[en_pista], propio, rival),
                            "off": sp.ratings_tramos(tramos[~en_pista], propio, rival)})
        quintetos[lado] = filas_q

    guardar(f"partidos/{int(p.id_partido)}.json", {
        "rotacion": rotacion, "quintetos": quintetos,
        "parciales": {"periodos": [periodos[int(per) - 1] for per in parciales.index],
                      "local": parciales["ml"].tolist(), "visitante": parciales["mv"].tolist()},
        "marcador": puntos, "duracion": int(minutos * 60),
        "datos": {"empates": empates, "ventaja_l": ventaja_l, "ventaja_v": ventaja_v, "cambios": cambios},
        "boxscore": boxscore,
        "estadisticas": {"local": spr._indicadores(conteos["local"], conteos["visitante"], minutos),
                         "visitante": spr._indicadores(conteos["visitante"], conteos["local"], minutos)},
    })
    return True


def exportar_partidos():
    partidos = sp.cargar_partidos()
    lista = []
    for p in partidos.itertuples():
        tiene_detalle = exportar_partido(p)
        lista.append({"id": int(p.id_partido), "jornada": str(p.jornada), "liga": bool(p.es_liga),
                      "orden": list(sp.orden_jornada(p.jornada, partidos)), "fecha": sp.formato_fecha(p.fecha_iso, p.fecha),
                      "fecha_iso": p.fecha_iso, "local": int(p.id_equipo_local), "visitante": int(p.id_equipo_visitante),
                      "pl": num(p.puntos_local), "pv": num(p.puntos_visitante), "detalle": bool(tiene_detalle)})
    guardar("partidos.json", lista)
    return partidos


# ------------------------------------------------------------------ EQUIPOS (LIGA)
def columnas_individuales():
    return [c for config in app.TABLAS_INDIVIDUALES.values() for c, _ in config["columnas"]]


def exportar_equipo(id_equipo, est_liga, indiv, h, nombres, fotos):
    plantilla = app.cargar_plantilla(id_equipo)
    # Estadística de equipo (ataque y defensa) con la posición en la liga, como en la app
    estadistica = {}
    if id_equipo in set(est_liga["id_equipo"]):
        fila = est_liga[est_liga["id_equipo"] == id_equipo].iloc[0]
        for fase in ("ataque", "defensa"):
            valores = {}
            for _, indicadores in spr.TABLAS_ESTADISTICA:
                for clave, _, _, mayor_es_mejor in indicadores:
                    columna = f"{fase}_{clave}"
                    sentido = mayor_es_mejor if fase == "ataque" or mayor_es_mejor is None else not mayor_es_mejor
                    ranking = est_liga[columna].rank(ascending=sentido is False, method="min")
                    posicion = ranking[est_liga["id_equipo"] == id_equipo].iloc[0]
                    valores[clave] = [fila[columna], None if pd.isna(posicion) else int(posicion)]
            estadistica[fase] = valores

    # Estadísticas individuales con percentiles y ratings (más PPP, para el gráfico de uso y eficiencia)
    columnas = columnas_individuales() + ["PPP"]
    ratings = [c["rating_col"] for c in app.TABLAS_INDIVIDUALES.values() if c["rating_col"]]
    df = indiv[indiv["id_equipo"] == id_equipo].merge(plantilla, on="id_jugador")
    individuales = [{"id": int(r["id_jugador"]),
                     "v": {c: [num(r.get(c)), num(r.get(f"{c}_pct"))] for c in columnas},
                     "r": {c: num(r.get(c)) for c in ratings}} for _, r in df.iterrows()]

    # Cuartos
    ev = sc.cargar_eventos(id_equipo)
    cuartos = None
    if not ev.empty:
        base = indiv[indiv["id_equipo"] == id_equipo]
        rendimiento = sc.ratings_por_periodo(ev, id_equipo)
        minutos = sc.minutos_por_periodo(ev)
        # Totales y "por partido" solo de minutos (como en la app); PPP para la tabla de uso de la sección Propio
        cols_cuarto = [c for c in columnas if c not in sc.ACUMULADAS or c in ("Minutos Totales", "Minutos por partido")]
        periodos = {}
        for periodo, etiqueta in sc.PERIODOS:
            if etiqueta not in set(ev["per"]):
                continue
            dfp = sc.datos_individuales(h, id_equipo, None, periodo, etiqueta, base, minutos, plantilla)
            ref = sc.referencia(base, periodo)
            periodos[etiqueta] = [] if dfp.empty else [
                {"id": int(r["id_jugador"]),
                 "v": {c: [num(r.get(c)), num(sc.valor_referencia(ref, int(r["id_jugador"]), c))] for c in cols_cuarto}}
                for _, r in dfp.iterrows()]
        cuartos = {
            "rendimiento": [{"periodo": nombre, **{k: r[k] for k in ("partidos", "pf", "pc", "ritmo", "ortg", "drtg", "net")}}
                            for nombre, r in rendimiento.iterrows()],
            "minutos": [{"id": int(j), **{c: num(v) for c, v in fila.items()}} for j, fila in minutos.iterrows()],
            "periodos": periodos,
        }

    guardar(f"equipos/{id_equipo}.json", {
        "plantilla": [{"id": int(r.id_jugador), "dorsal": r.dorsal, "nombre": r.nombre,
                       "foto": int(r.id_jugador) in fotos} for r in plantilla.itertuples()],
        "estadistica": estadistica, "individuales": individuales, "cuartos": cuartos,
        "en_pista": eventos_en_pista(id_equipo),
    })


MOVIMIENTOS_QUINTETO = {93, 100, 94, 97, 98, 92, 96, 104, 101, 107, 106}


def eventos_en_pista(id_equipo):
    """Play by play mínimo para calcular en la app el On/Off de cualquier combinación de jugadores (como
    calcular_stats_quinteto): [índice del quinteto propio en pista, lado (1 propio, 0 rival, -1 nadie), jugada, segundos]."""
    conexion = spr.conectar()
    df = pd.read_sql("""SELECT pb.id_partido, pb.idMove, pb.id_equipo, pb.quinteto_local, pb.quinteto_visitante,
                               pb.period, pb.min, pb.sec, p.id_equipo_local
                        FROM play_by_play pb JOIN partidos p ON pb.id_partido = p.id_partido
                        WHERE p.id_equipo_local = ? OR p.id_equipo_visitante = ?""",
                     conexion, params=(id_equipo, id_equipo))
    conexion.close()
    if df.empty:
        return None
    df["restante"] = df["min"].fillna(0).astype(int) * 60 + df["sec"].fillna(0).astype(int)
    df = df.sort_values(["id_partido", "period", "restante"], ascending=[True, True, False])
    siguiente = df.groupby(["id_partido", "period"])["restante"].shift(-1).fillna(0)
    df["seg"] = (df["restante"] - siguiente).clip(lower=0)
    quintetos, indices, filas = [], {}, []
    for r in df.itertuples():
        texto = r.quinteto_local if r.id_equipo_local == id_equipo else r.quinteto_visitante
        ids = tuple(sorted(bd.ids_quinteto(texto))) if pd.notna(texto) else ()
        lado = -1 if pd.isna(r.id_equipo) else int(r.id_equipo == id_equipo)
        jugada = int(r.idMove) if r.idMove in MOVIMIENTOS_QUINTETO and lado != -1 else 0
        if r.seg <= 0 and not jugada:
            continue
        if ids not in indices:
            indices[ids] = len(quintetos)
            quintetos.append(list(ids))
        filas.append([indices[ids], lado, jugada, int(r.seg)])
    return {"quintetos": quintetos, "ev": filas}


# ------------------------------------------------------------------ RANKINGS
RANKING_INDIVIDUAL = {
    "Impacto": ['Diferencial Offensive Rating', 'Diferencial Defensive Rating', 'Diferencial Net Rating'],
    "Minutos": ['Minutos Totales', 'Minutos por partido', '% Minutos'],
    "Anotación": ['Rating Anotación', 'Puntos totales', 'Puntos por partido', 'Puntos p100', '%T2', '2PAr', '%T3', '3PAr',
                  '%TL', 'FTr', 'eFG%', 'TS%', 'ASTFGM%', '%USG', 'PPP'],
    "Rebote": ['Rating Rebote', 'RD pp', 'RD p100', 'DREB%', 'RO pp', 'RO p100', 'OREB%', 'RT pp', 'RT p100', 'REB%'],
    "Cuidado de balón": ['Rating Cuidado de Balón', 'Asistencias pp', 'Asistencias p100', 'AST%', 'Pérdidas pp',
                         'Pérdidas p100', 'TOV%', 'AST / TO'],
    "Defensa": ['Rating Defensa', 'STL pp', 'STL p100', 'STL%', 'BLK pp', 'BLK p100', 'BLK%'],
}
RANKING_EQUIPO = {
    "Posesiones": ['Ritmo', 'Plays', 'Offensive Rating', 'Defensive Rating', 'Net Rating'],
    "Tiro": ['eFG%', 'TS%', 'FTr', '2PAr', '3PAr'],
    "Rebote": ['DREB%', 'OREB%', 'REB%'],
    "Cuidado de balón": ['TOV%', 'AST / TO ratio', 'AST%'],
}
MENOR_ES_MEJOR_RANKING = ['Pérdidas pp', 'Pérdidas p100', 'TOV%', 'Diferencial Defensive Rating', 'Defensive Rating']


def exportar_rankings(indiv, nombres_jug):
    stats = [s for lista in RANKING_INDIVIDUAL.values() for s in lista]
    df = indiv.merge(nombres_jug, on="id_jugador")
    jugadores = [{"id": int(r["id_jugador"]), "eq": int(r["id_equipo"]), "pj": num(r.get("PJ")),
                  "v": [num(r.get(s)) for s in stats]} for _, r in df.iterrows()]
    eq = app.calcular_stats_avanzadas_liga()
    stats_eq = [s for lista in RANKING_EQUIPO.values() for s in lista]
    equipos = [{"eq": int(r["id_equipo"]), "v": [num(r.get(s)) for s in stats_eq]} for _, r in eq.iterrows()]
    guardar("rankings.json", {"individual": RANKING_INDIVIDUAL, "equipo": RANKING_EQUIPO, "stats": stats,
                              "stats_eq": stats_eq, "menor_es_mejor": MENOR_ES_MEJOR_RANKING,
                              "jugadores": jugadores, "equipos": equipos})


# ------------------------------------------------------------------ PROPIO (POSESIONES ETIQUETADAS)
def filas_pr(df_pr, grupos):
    """Como tabla_pr: por grupo, nº de P&R, frecuencia, PPP y cómo acaba (manejador / bloqueador)."""
    datos = df_pr.assign(grupo=list(grupos))
    resumen = datos.groupby("grupo")["puntos"].agg(["size", "sum"]).sort_values("size", ascending=False)
    filas = []
    for grupo, r in resumen.iterrows():
        sub = datos[datos["grupo"] == grupo]
        acaba = []
        for playtype, _, _ in spr.ACABA:
            a = sub[sub["playtype"] == playtype]
            acaba.append([len(a) / len(sub) * 100, a["puntos"].sum() / len(a) if len(a) else None])
        filas.append({"g": str(grupo), "n": int(r["size"]), "f": r["size"] / len(datos) * 100,
                      "ppp": r["sum"] / r["size"], "acaba": acaba})
    return filas


def exportar_pr(df_pr, nombre, fase):
    if df_pr.empty:
        return None
    col_m, col_b = ("pr_handler", "pr_roller") if fase == "ataque" else ("defensor_pr_handler", "defensor_pr_roller")
    jugador = lambda j: nombre(j) if pd.notna(j) else "Sin indicar"
    manejadores = df_pr[col_m].apply(jugador)
    bloqueadores = df_pr[col_b].apply(jugador)

    # Analizador individual: rol, parejas y defensa del P&R de cada jugador (como en analisis_pr)
    t = spr.TEXTOS_PR[fase]
    analizador = {}
    ids = pd.concat([df_pr[col_m], df_pr[col_b]]).dropna().astype(int)
    for id_jugador in ids.value_counts().index:
        es_m, es_b = df_pr[col_m] == id_jugador, df_pr[col_b] == id_jugador
        df_jug = df_pr[es_m | es_b]
        rol = [t["rol_manejador"] if es_m[i] else t["rol_bloqueador"] for i in df_jug.index]
        companero = [t["con_bloqueador"].format(bloqueadores[i]) if es_m[i] else t["con_manejador"].format(manejadores[i])
                     for i in df_jug.index]
        analizador[int(id_jugador)] = {"n": len(df_jug), "f": len(df_jug) / len(df_pr) * 100,
                                       "ppp": df_jug["puntos"].sum() / len(df_jug),
                                       "rol": filas_pr(df_jug, rol), "parejas": filas_pr(df_jug, companero),
                                       "defensa_pr": filas_pr(df_jug, df_jug["pr_defense"].fillna("Sin indicar"))}
    return {**resumen_total(df_pr),
            "manejadores": filas_pr(df_pr, manejadores), "bloqueadores": filas_pr(df_pr, bloqueadores),
            "parejas": filas_pr(df_pr, manejadores + " - " + bloqueadores),
            "defensa_pr": filas_pr(df_pr, df_pr["pr_defense"].fillna("Sin indicar")),
            "analizador": analizador}


def exportar_secundarios(df, nombre):
    """Secondary playtypes: frecuencia, PPP, protagonistas, a qué playtype principal llevan y quién los genera."""
    con = df[df["playtype_secundario"].notna()]
    if con.empty:
        return None
    con = con.assign(generador=spr.generadores(con, nombre))
    corto = lambda texto: texto.partition(" - ")[2].split()[0].title() if " - " in texto else texto
    filas, genera = [], {}
    por = con.groupby("playtype_secundario")["puntos"].agg(["size", "sum"]).sort_values("size", ascending=False)
    for secundario, r in por.iterrows():
        sub = con[con["playtype_secundario"] == secundario]
        top = sub["generador"].value_counts().head(3)
        hijos = sub.groupby("playtype")["puntos"].agg(["size", "sum"]).sort_values("size", ascending=False)
        filas.append({"g": secundario, "n": int(r["size"]), "f": r["size"] / len(df) * 100, "ppp": r["sum"] / r["size"],
                      "top": [[corto(g), int(n)] for g, n in top.items()],
                      "hijos": [{"g": p, "n": int(h["size"]), "f": h["size"] / r["size"] * 100, "ppp": h["sum"] / h["size"]}
                                for p, h in hijos.iterrows()]})
        if secundario in spr.GENERADOR_SECUNDARIO:
            sub = sub.assign(genera=[f"{g} → {p}" for g, p in zip(sub["generador"], sub["playtype"])])
            genera[secundario] = filas_resumen(sub, "genera")
    return {"con": len(con), "total": len(df), "filas": filas, "genera": genera}


def exportar_propio(id_propio, nombres):
    nombre = lambda j: nombres.get(int(j), str(j))
    partidos = spr.partidos_del_equipo(id_propio)
    df_at, df_def = spr.cargar_posesiones(partidos)
    datos = {"ataque": None, "defensa": None, "cuartos": {}}

    if not df_at.empty:
        finalizador = [nombre(j) if pd.notna(j) else "Sin jugador" for j in df_at["id_jugador"]]
        df_at = df_at.assign(finalizador=finalizador,
                             jugador_playtype=[f"{f} · {p}" for f, p in zip(finalizador, df_at["playtype"])])
        sistemas = {}
        for fila in filas_resumen(df_at, "sistema", "Sin sistema"):
            s = fila["g"]
            df_s = df_at[df_at["sistema"].isna()] if s == "Sin sistema" else df_at[df_at["sistema"] == s]
            sistemas[s] = {**resumen_total(df_s), "playtypes": filas_resumen(df_s, "playtype"),
                           "finaliza": filas_resumen(df_s, "finalizador"),
                           "jugador_playtype": filas_resumen(df_s, "jugador_playtype"),
                           "secundarios": exportar_secundarios(df_s, nombre)}
        secundarias = df_at[df_at["playtype_secundario"].notna() & (df_at["playtype_secundario"] != df_at["playtype"])]
        con_secundario = pd.concat([df_at, secundarias.assign(playtype=secundarias["playtype_secundario"])])
        pt_con_sec = filas_resumen(con_secundario, "playtype")
        for f in pt_con_sec:
            f["f"] = f["n"] / len(df_at) * 100
        datos["ataque"] = {
            **resumen_total(df_at),
            "sistemas": filas_resumen(df_at, "sistema", "Sin sistema"), "sistema_detalle": sistemas,
            "playtypes": filas_resumen(df_at, "playtype"), "playtypes_con_secundario": pt_con_sec,
            "secundarios": exportar_secundarios(df_at, nombre),
            "pr": exportar_pr(df_at[df_at["playtype"].isin(spr.PLAYTYPES_PR)], nombre, "ataque"),
            "tipo_defensa": filas_resumen(df_at, "tipo_defensa", "Sin indicar"),
            "finalizador": filas_resumen(df_at, "finalizador"),
        }
        datos["ataque"]["tiros"] = tiros(df_at, lambda r: int(r.id_jugador) if pd.notna(r.id_jugador) else None)
        datos["ataque"]["finalizador_mapa"] = {dim: mapa_finalizador(df_at, col) for dim, col in
                                               (("Playtype", "playtype"), ("Sistema", "sistema"))}
        # Análisis individual: playtypes y sistemas de las posesiones que finaliza cada jugador
        datos["jugadores"] = {}
        for id_jugador in df_at["id_jugador"].dropna().astype(int).unique():
            df_jug = df_at[df_at["id_jugador"] == id_jugador]
            datos["jugadores"][int(id_jugador)] = {
                **resumen_total(df_jug),
                **{col: {"filas": filas_resumen(df_jug, col, vacio), "equipo": ppp_por_grupo(df_at, col, vacio)}
                   for col, vacio in (("playtype", "—"), ("sistema", "Sin sistema"))}}
        for periodo, etiqueta in sc.PERIODOS:
            df_q = df_at[df_at["period"] > 4] if periodo == "OT" else df_at[df_at["period"] == periodo]
            if len(df_q):
                datos["cuartos"][etiqueta] = {**resumen_total(df_q),
                                              "sistemas": filas_resumen(df_q, "sistema", "Sin sistema"),
                                              "playtypes": filas_resumen(df_q, "playtype")}

    if not df_def.empty:
        uno_contra_uno = {}
        for playtype in ("Isolation", "Post Up"):
            acciones = df_def[(df_def["playtype"] == playtype) & df_def["id_defensor"].notna()]
            ppp_equipo = df_def[df_def["playtype"] == playtype]["puntos"].mean()
            filas = []
            resumen = acciones.groupby(acciones["id_defensor"].astype(int))["puntos"].agg(["size", "sum"])
            for id_jugador, r in resumen.sort_values(["size", "sum"], ascending=[False, True]).iterrows():
                en_pista = int(df_def["en_pista"].apply(lambda ids, j=id_jugador: j in ids).sum())
                filas.append({"g": nombre(id_jugador), "n": int(r["size"]), "en_pista": en_pista,
                              "pct": r["size"] / en_pista * 100 if en_pista else None, "pts": int(r["sum"]),
                              "ppp": r["sum"] / r["size"]})
            uno_contra_uno[playtype] = {"ppp_equipo": ppp_equipo, "n": len(acciones), "filas": filas}
        datos["defensa"] = {
            **resumen_total(df_def),
            "playtypes": filas_resumen(df_def, "playtype"),
            "tipo_defensa": filas_resumen(df_def, "tipo_defensa", "Sin indicar"),
            "pr": exportar_pr(df_def[df_def["playtype"].isin(spr.PLAYTYPES_PR)], nombre, "defensa"),
            "uno_contra_uno": uno_contra_uno,
        }
        # Para filtrar en la app por jugadores en pista: posesiones y tiros del rival con el quinteto propio
        quintetos, indices = [], {}

        def indice_quinteto(ids):
            clave = tuple(sorted(ids))
            if clave not in indices:
                indices[clave] = len(quintetos)
                quintetos.append(list(clave))
            return indices[clave]

        playtypes = sorted(df_def["playtype"].dropna().unique())
        datos["defensa"]["quintetos"] = quintetos
        datos["defensa"]["playtypes_lista"] = playtypes
        datos["defensa"]["posesiones"] = [[playtypes.index(r.playtype), int(r.puntos), indice_quinteto(r.en_pista)]
                                          for r in df_def.itertuples()]
        datos["defensa"]["tiros"] = tiros(df_def, lambda r: indice_quinteto(r.en_pista))
    guardar("propio.json", datos)


def tiros(df, extra):
    """Tiros de campo con localización: [x, y, índice de zona, anotado, triple, extra (jugador o quinteto)]."""
    import cancha
    filas = []
    for r in df[df["idMove"].isin(spr.TIROS_CAMPO) & df["tiro_x"].notna()].itertuples():
        triple = r.idMove in spr.TRIPLES
        zona = cancha.zona_de_tiro(r.tiro_x, r.tiro_y, triple)
        filas.append([round(r.tiro_x, 2), round(r.tiro_y, 2), cancha.ZONAS_TIRO.index(zona),
                      int(r.idMove in spr.CANASTAS_CAMPO), int(triple), extra(r)])
    return filas


def ppp_por_grupo(df, columna, vacio):
    grupos = df[columna].fillna(vacio)
    return (df.groupby(grupos)["puntos"].sum() / df.groupby(grupos).size()).to_dict()


def mapa_finalizador(df_at, columna):
    """Como analisis_por_finalizador: PPP y posesiones por jugador que finaliza (filas) y categoría (columnas)."""
    df = df_at.assign(categoria=df_at[columna].fillna("Sin sistema"))
    agrupado = df.groupby(["finalizador", "categoria"])["puntos"].agg(["size", "sum"])
    filas = df["finalizador"].value_counts().index.tolist()
    columnas = df["categoria"].value_counts().index.tolist()
    n = agrupado["size"].unstack().reindex(index=filas, columns=columnas)
    ppp = (agrupado["sum"] / agrupado["size"]).unstack().reindex(index=filas, columns=columnas)
    return {"filas": filas, "columnas": columnas, "n": n.to_numpy().tolist(), "ppp": ppp.to_numpy().tolist()}


def exportar_cancha():
    """Geometría de la media cancha y de las 14 zonas de tiro (metros), para dibujar las cartas de tiro."""
    import cancha
    guardar("cancha.json", {
        "zonas": [[nombre, " ".join(f"{x:.3f},{y:.3f}" for x, y in puntos)] for nombre, puntos in cancha._poligonos_zonas()],
        "lineas": cancha.svg_lineas(), "etiquetas": cancha.POSICION_ETIQUETA, "orden": cancha.ZONAS_TIRO,
        "triples": sorted(cancha.ZONAS_TRIPLE), "esperado": spr.ACIERTO_ESPERADO, "y_max": cancha.Y_MAX_ZONAS,
    })


# ------------------------------------------------------------------ PRINCIPAL
def main():
    conexion = spr.conectar()
    id_propio = bd.obtener_id_equipo_propio(conexion)
    equipos_df = pd.read_sql("""SELECT id_equipo, nombre, nombre_corto, color FROM equipos WHERE id_equipo IN
                                (SELECT id_equipo_local FROM partidos UNION SELECT id_equipo_visitante FROM partidos)""",
                             conexion)
    jugadores = pd.read_sql("SELECT id_jugador, dorsal, nombre, id_equipo FROM jugadores", conexion)
    conexion.close()

    equipos = [{"id": int(r.id_equipo), "nombre": r.nombre, "corto": r.nombre_corto,
                "color": sp.color_valido(r.color, "#F97316")} for r in equipos_df.itertuples()]
    if os.path.exists(DATOS):
        shutil.rmtree(DATOS)
    fotos = copiar_imagenes(equipos, jugadores)
    exportar_meta(equipos, id_propio)
    guardar("jugadores.json", {int(r.id_jugador): [r.dorsal if pd.notna(r.dorsal) else "", r.nombre, int(r.id_equipo)
                                                   if pd.notna(r.id_equipo) else None, int(r.id_jugador) in fotos]
                               for r in jugadores.itertuples()})
    print("Clasificación…")
    exportar_clasificacion()
    print("Partidos…")
    exportar_partidos()

    print("Estadísticas de liga…")
    indiv = app.calcular_stats_individuales_liga()
    est_liga = spr.estadistica_liga()
    h = SimpleNamespace(calcular_stats_individuales_liga=app.calcular_stats_individuales_liga,
                        cargar_plantilla=app.cargar_plantilla)
    nombres = spr.cargar_nombres()
    for e in equipos:
        print(f"  Equipo {e['corto']}…")
        exportar_equipo(e["id"], est_liga, indiv, h, nombres, fotos)
    print("Rankings…")
    exportar_rankings(indiv, jugadores[["id_jugador"]])
    print("Propio…")
    exportar_propio(id_propio, nombres)
    exportar_cancha()

    # Versión de los datos: el service worker la usa para saber que hay datos nuevos
    with open(os.path.join(APP_MOVIL, "version.txt"), "w", encoding="utf-8") as f:
        f.write(datetime.now().strftime("%Y%m%d%H%M%S"))
    tamano = sum(os.path.getsize(os.path.join(d, a)) for d, _, archivos in os.walk(DATOS) for a in archivos)
    print(f"Listo: datos en {DATOS} ({tamano / 1024:.0f} KB).")


if __name__ == "__main__":
    main()
