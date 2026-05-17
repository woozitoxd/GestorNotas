from flask import Flask, render_template, jsonify, request, send_file
import threading
import os
import re
import pandas as pd
from gestor_notas import (
    iniciar_navegador, iniciar_sesion,
    obtener_materias, extraer_alumnos, extraer_alumnos_con_notas,
    guardar_csv, cargar_notas,
    ARCHIVO_CSV
)

app = Flask(__name__)

# Driver compartido — vive mientras la app esté corriendo
_driver = None

estado = {
    "ocupado":          False,
    "mensaje":          "",
    "error":            None,
    "materias":         [],
    "materia_activa":   None,
    "navegador_abierto": False,
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _driver_vivo():
    """Devuelve True si el driver existe y responde. Si murió, lo limpia."""
    global _driver
    if not _driver:
        return False
    try:
        _ = _driver.title
        return True
    except Exception:
        _driver = None
        estado["navegador_abierto"] = False
        return False


def _leer_alumnos():
    if os.path.exists(ARCHIVO_CSV):
        return pd.read_csv(ARCHIVO_CSV).fillna("").to_dict("records")
    return []


# ── rutas principales ─────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", alumnos=_leer_alumnos())


@app.route("/status")
def status():
    # Actualizar estado del navegador en cada poll
    if estado["navegador_abierto"] and not _driver_vivo():
        estado["navegador_abierto"] = False
    return jsonify(estado)


# ── navegador ─────────────────────────────────────────────────────────────────

@app.route("/abrir", methods=["POST"])
def abrir_navegador():
    global _driver
    if _driver_vivo():
        return jsonify({"error": "El navegador ya está abierto"}), 400
    if estado["ocupado"]:
        return jsonify({"error": "Hay una operación en curso"}), 400

    def tarea():
        global _driver
        estado.update({"ocupado": True, "error": None, "mensaje": "Iniciando navegador..."})
        try:
            _driver = iniciar_navegador()
            estado["mensaje"] = "Verificando sesión..."
            if iniciar_sesion(_driver, estado):
                estado.update({
                    "navegador_abierto": True,
                    "mensaje": "Navegador listo — sesión activa",
                })
            else:
                estado.update({"error": "No se pudo iniciar sesión", "mensaje": ""})
                try:
                    _driver.quit()
                except Exception:
                    pass
                _driver = None
        except Exception as e:
            estado.update({"error": str(e), "mensaje": ""})
            if _driver:
                try:
                    _driver.quit()
                except Exception:
                    pass
                _driver = None
        finally:
            estado["ocupado"] = False

    threading.Thread(target=tarea, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/cerrar", methods=["POST"])
def cerrar_navegador():
    global _driver
    if not _driver_vivo():
        return jsonify({"error": "El navegador no está abierto"}), 400
    try:
        _driver.quit()
    except Exception:
        pass
    _driver = None
    estado.update({"navegador_abierto": False, "mensaje": "Navegador cerrado"})
    return jsonify({"ok": True})


# ── operaciones (usan el driver compartido, sin login) ────────────────────────

@app.route("/cargar_materias", methods=["POST"])
def cargar_materias():
    if not _driver_vivo():
        return jsonify({"error": "Abrí el navegador primero"}), 400
    if estado["ocupado"]:
        return jsonify({"error": "Hay una operación en curso"}), 400

    def tarea():
        estado.update({"ocupado": True, "error": None, "mensaje": "Cargando materias..."})
        try:
            materias = obtener_materias(_driver)
            if materias:
                estado["materias"] = materias
                estado["mensaje"] = f"Se encontraron {len(materias)} materias"
            else:
                estado.update({"error": "No se encontraron materias", "mensaje": ""})
        except Exception as e:
            estado.update({"error": str(e), "mensaje": ""})
        finally:
            estado["ocupado"] = False

    threading.Thread(target=tarea, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/seleccionar_materia", methods=["POST"])
def seleccionar_materia():
    datos = request.json or {}
    nombre      = datos.get("nombre", "").strip()
    url_alumnos = datos.get("url_alumnos", "").strip()
    url_notas   = datos.get("url_notas", "").strip()
    if not nombre or not url_alumnos:
        return jsonify({"error": "Datos incompletos"}), 400
    estado["materia_activa"] = {
        "nombre":          nombre,
        "url_alumnos":     url_alumnos,
        "url_notas":       url_notas,
        "comision_codigo": datos.get("comision_codigo", ""),
        "comision_nombre": datos.get("comision_nombre", ""),
    }
    return jsonify({"ok": True})


@app.route("/extraer", methods=["POST"])
def extraer():
    if not _driver_vivo():
        return jsonify({"error": "Abrí el navegador primero"}), 400
    if estado["ocupado"]:
        return jsonify({"error": "Hay una operación en curso"}), 400
    materia = estado["materia_activa"]
    if not materia:
        return jsonify({"error": "Seleccioná una materia primero"}), 400

    def tarea():
        estado.update({"ocupado": True, "error": None, "mensaje": "Extrayendo alumnos..."})
        try:
            alumnos = extraer_alumnos(_driver, materia["url_alumnos"])
            if alumnos:
                guardar_csv(alumnos)
                estado["mensaje"] = f"Se extrajeron {len(alumnos)} alumnos correctamente"
            else:
                estado.update({"error": "No se encontraron alumnos", "mensaje": ""})
        except Exception as e:
            estado.update({"error": str(e), "mensaje": ""})
        finally:
            estado["ocupado"] = False

    threading.Thread(target=tarea, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/extraer_con_notas", methods=["POST"])
def extraer_con_notas():
    if not _driver_vivo():
        return jsonify({"error": "Abrí el navegador primero"}), 400
    if estado["ocupado"]:
        return jsonify({"error": "Hay una operación en curso"}), 400
    materia = estado["materia_activa"]
    if not materia:
        return jsonify({"error": "Seleccioná una materia primero"}), 400
    if not materia.get("url_notas"):
        return jsonify({"error": "No se encontró URL de evaluaciones para esta materia"}), 400

    def tarea():
        estado.update({"ocupado": True, "error": None, "mensaje": "Extrayendo alumnos y notas..."})
        try:
            alumnos = extraer_alumnos_con_notas(_driver, materia["url_alumnos"], materia["url_notas"])
            if alumnos:
                guardar_csv(alumnos)
                estado["mensaje"] = f"Se extrajeron {len(alumnos)} alumnos con notas"
            else:
                estado.update({"error": "No se encontraron alumnos", "mensaje": ""})
        except Exception as e:
            estado.update({"error": str(e), "mensaje": ""})
        finally:
            estado["ocupado"] = False

    threading.Thread(target=tarea, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/guardar_notas", methods=["POST"])
def guardar_notas():
    datos = request.json.get("notas", [])
    if not datos:
        return jsonify({"error": "Sin datos para guardar"}), 400
    pd.DataFrame(datos).to_csv(ARCHIVO_CSV, index=False, encoding="utf-8")
    return jsonify({"ok": True, "mensaje": f"Notas guardadas ({len(datos)} alumnos)"})


@app.route("/cargar", methods=["POST"])
def cargar():
    if not _driver_vivo():
        return jsonify({"error": "Abrí el navegador primero"}), 400
    if estado["ocupado"]:
        return jsonify({"error": "Hay una operación en curso"}), 400
    materia = estado["materia_activa"]
    if not materia:
        return jsonify({"error": "Seleccioná una materia primero"}), 400
    if not materia.get("url_notas"):
        return jsonify({"error": "No se encontró URL de notas para esta materia"}), 400

    datos = request.json or {}
    evaluacion = int(datos.get("evaluacion", 1))

    def tarea():
        estado.update({"ocupado": True, "error": None,
                       "mensaje": f"Cargando notas (evaluación {evaluacion})..."})
        try:
            ok = cargar_notas(_driver, materia["url_notas"], evaluacion)
            if ok:
                estado["mensaje"] = f"Notas cargadas correctamente (evaluación {evaluacion})"
            else:
                estado.update({"error": f"Error al cargar notas (evaluación {evaluacion})", "mensaje": ""})
        except Exception as e:
            estado.update({"error": str(e), "mensaje": ""})
        finally:
            estado["ocupado"] = False

    threading.Thread(target=tarea, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/importar_excel", methods=["POST"])
def importar_excel():
    archivo = request.files.get("archivo")
    if not archivo:
        return jsonify({"error": "Sin archivo"}), 400

    try:
        nombre = archivo.filename.lower()
        if nombre.endswith(".xlsx"):
            df_import = pd.read_excel(archivo, engine="openpyxl")
        else:
            df_import = pd.read_csv(archivo)

        cols_nota = [c for c in ["Nota1", "Nota2", "Nota"] if c in df_import.columns]
        if "Nombre" not in df_import.columns or not cols_nota:
            return jsonify({"error": "El archivo debe tener columna 'Nombre' y al menos una de: Nota1, Nota2, Nota"}), 400

        def normalizar(s):
            import unicodedata
            s = str(s).strip().lower()
            s = unicodedata.normalize("NFD", s)
            s = "".join(c for c in s if unicodedata.category(c) != "Mn")
            return " ".join(s.split())

        if os.path.exists(ARCHIVO_CSV):
            df_base = pd.read_csv(ARCHIVO_CSV).fillna("")

            # Construir lookup: nombre_norm → {col: valor}
            lookup = {}
            for _, row in df_import.iterrows():
                entry = {}
                for col in cols_nota:
                    val = str(row[col]).strip()
                    if val and val.lower() != "nan":
                        entry[col] = val
                if entry:
                    lookup[normalizar(row["Nombre"])] = entry

            actualizados = 0
            for i, row in df_base.iterrows():
                key = normalizar(row["Nombre"])
                if key in lookup:
                    for col, val in lookup[key].items():
                        if col not in df_base.columns:
                            df_base[col] = ""
                        df_base.at[i, col] = val
                    actualizados += 1

            df_base.to_csv(ARCHIVO_CSV, index=False, encoding="utf-8")
        else:
            df_import.to_csv(ARCHIVO_CSV, index=False, encoding="utf-8")
            actualizados = len(df_import)

        return jsonify({"ok": True, "actualizados": actualizados,
                        "mensaje": f"Importación exitosa — {actualizados} alumnos importados"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/descargar")
def descargar():
    if not os.path.exists(ARCHIVO_CSV):
        return jsonify({"error": "Sin CSV disponible"}), 404
    return send_file(ARCHIVO_CSV, as_attachment=True)


@app.route("/descargar_excel")
def descargar_excel():
    if not os.path.exists(ARCHIVO_CSV):
        return jsonify({"error": "Sin datos disponibles. Extraé los alumnos primero."}), 404

    import io
    df = pd.read_csv(ARCHIVO_CSV)

    cols_extra = [c for c in ["Nota1", "Nota2", "Condicion"] if c in df.columns]
    exportar = df[["Nombre"] + cols_extra].copy()

    col_widths = {"A": 40, "B": 10, "C": 10, "D": 15, "E": 12}
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        exportar.to_excel(writer, index=False, sheet_name="Notas")
        ws = writer.sheets["Notas"]
        for i, _ in enumerate(exportar.columns):
            letra = chr(ord("A") + i)
            ws.column_dimensions[letra].width = col_widths.get(letra, 12)

    buffer.seek(0)
    materia      = estado.get("materia_activa") or {}
    codigo       = materia.get("comision_codigo", "")
    nombre_full  = materia.get("nombre", "")
    nombre_mat   = nombre_full.split(" — ", 1)[1].strip() if " — " in nombre_full else nombre_full
    partes       = [p for p in [codigo, nombre_mat] if p] or ["notas"]
    safe         = re.sub(r'[\\/:*?"<>|]', "", "_".join(partes)).strip()
    nombre_archivo = f"notas_{safe}.xlsx"

    return send_file(
        buffer,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, port=5000)
