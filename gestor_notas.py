"""
Gestor de Notas - Script para extraer alumnos y cargar notas automáticamente
Plataforma: https://dvcarreras.davinci.edu.ar/
"""

import os
import json
import unicodedata
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
from pathlib import Path

# ==================== CONFIGURACIÓN ====================
URL_BASE        = "https://dvcarreras.davinci.edu.ar/"
URL_COMMISSIONS = "https://dvcarreras.davinci.edu.ar/teacher_commissions.html"
ARCHIVO_CSV     = "alumnos_notas.csv"
COOKIES_FILE    = os.path.join(os.path.dirname(__file__), "session_cookies.json")

# ==================== FUNCIONES ====================

def iniciar_navegador():
    options = EdgeOptions()
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    driver = webdriver.Edge(options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver


def _guardar_cookies(driver):
    cookies = driver.get_cookies()
    with open(COOKIES_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f)
    print(f"Sesión guardada ({len(cookies)} cookies)")


def _cargar_cookies(driver):
    if not Path(COOKIES_FILE).exists():
        return False
    try:
        with open(COOKIES_FILE, encoding="utf-8") as f:
            cookies = json.load(f)
        for cookie in cookies:
            cookie.pop("sameSite", None)
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass
        return bool(cookies)
    except Exception as e:
        print(f"No se pudieron cargar cookies: {e}")
        return False


def esperar_cloudflare(driver, estado=None, timeout=90):
    """
    Espera hasta que Cloudflare resuelva el challenge.
    Si el challenge requiere interacción humana, el usuario puede resolverlo
    manualmente en el navegador mientras la app espera.
    """
    inicio = time.time()
    avisado = False
    while time.time() - inicio < timeout:
        titulo = driver.title.lower()
        if any(k in titulo for k in ["momento", "just a moment", "checking", "please wait"]):
            if not avisado:
                print("Cloudflare detectado — esperando resolución...")
                if estado is not None:
                    estado["mensaje"] = "Cloudflare detectado — si aparece un desafío en el navegador, completalo manualmente"
                avisado = True
            time.sleep(2)
        else:
            if avisado:
                print("Cloudflare resuelto")
            return True
    print("Timeout esperando Cloudflare")
    return False

def iniciar_sesion(driver, estado=None):
    print("Verificando sesión...")
    driver.get(URL_BASE)
    esperar_cloudflare(driver, estado, timeout=90)
    time.sleep(1)

    # Intentar restaurar sesión con cookies guardadas
    if _cargar_cookies(driver):
        print("Cookies cargadas — verificando sesión...")
        driver.get(URL_BASE)
        esperar_cloudflare(driver, estado, timeout=90)
        time.sleep(1)
        if not driver.find_elements(By.NAME, "user"):
            print("Sesión restaurada desde cookies")
            return True
        print("Cookies expiradas — se requiere login manual")
        Path(COOKIES_FILE).unlink(missing_ok=True)

    if not driver.find_elements(By.NAME, "user"):
        print("Sesión activa")
        return True

    print("Esperando login manual...")
    if estado is not None:
        estado["mensaje"] = "Iniciá sesión manualmente en el navegador (tenés 3 minutos)"

    try:
        WebDriverWait(driver, 180).until_not(
            EC.presence_of_element_located((By.NAME, "user"))
        )
        esperar_cloudflare(driver, estado, timeout=60)
        time.sleep(2)
        _guardar_cookies(driver)
        print("Login completado — sesión guardada")
        return True
    except Exception:
        print("Timeout esperando login manual")
        return False

def obtener_materias(driver):
    """
    1. Lee teacher_commissions.html y extrae los links teacher_inscriptions_subjects-*.html
    2. Navega a cada uno y extrae las materias con sus URLs de alumnos y notas
    """
    print("\nCargando materias...")
    driver.get(URL_COMMISSIONS)

    try:
        wait = WebDriverWait(driver, 15)
        esperar_cloudflare(driver, timeout=90)
        wait.until(EC.presence_of_element_located((By.ID, "view_commissions")))
        time.sleep(2)

        # Paso 1: recoger info de cada comisión (nombre, código, URL de materias)
        comisiones = driver.execute_script("""
            var result = [];
            document.querySelectorAll('#view_commissions table.striped tbody tr').forEach(function(fila) {
                var celdas = fila.querySelectorAll('td');
                if (celdas.length < 2) return;
                var strong = celdas[0].querySelector('strong');
                if (!strong) return;
                var nombre = strong.innerText.trim();
                var span   = celdas[0].querySelector('span');
                var codigo = span ? span.innerText.trim() : '';
                var url_subjects = '';
                fila.querySelectorAll('a[href*="teacher_inscriptions_subjects-"]').forEach(function(a) {
                    url_subjects = a.href;
                });
                if (url_subjects) result.push({ nombre: nombre, codigo: codigo, url: url_subjects });
            });
            return result;
        """)
        print(f"Comisiones encontradas: {len(comisiones)}")

        if not comisiones:
            with open("debug_commissions.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print("Sin comisiones — HTML guardado en debug_commissions.html")
            return []

        # Paso 2: visitar cada página y extraer sus materias
        materias = []
        for com in comisiones:
            try:
                driver.get(com["url"])
                esperar_cloudflare(driver, timeout=30)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.striped")))
                time.sleep(2)

                items = driver.execute_script("""
                    var comNombre = arguments[0];
                    var comCodigo = arguments[1];
                    var items = [];
                    document.querySelectorAll('table.striped tbody tr').forEach(function(fila) {
                        var celdas = fila.querySelectorAll('td');
                        if (celdas.length < 2) return;
                        var strong = celdas[0].querySelector('strong');
                        if (!strong) return;
                        var nombre_materia = strong.innerText.trim();
                        var link = celdas[celdas.length - 1]
                            .querySelector('a[href*="teacher_inscriptions-"]');
                        if (!link) return;
                        var url_alumnos = link.href;
                        var url_notas   = url_alumnos.replace('teacher_inscriptions-', 'tests-');
                        var etiqueta = comNombre;
                        if (comCodigo) etiqueta += ' [' + comCodigo + ']';
                        etiqueta += ' — ' + nombre_materia;
                        items.push({
                            nombre:          etiqueta.trim(),
                            comision_nombre: comNombre,
                            comision_codigo: comCodigo,
                            url_alumnos:     url_alumnos,
                            url_notas:       url_notas
                        });
                    });
                    return items;
                """, com["nombre"], com["codigo"])

                print(f"  {com['nombre']} [{com['codigo']}]: {len(items)} materias")
                materias.extend(items)

            except Exception as e:
                print(f"  Error en comisión {com.get('nombre','')}: {e}")

        print(f"Total materias: {len(materias)}")
        return materias

    except Exception as e:
        print(f"Error al obtener materias: {e}")
        return []


def extraer_alumnos(driver, url_alumnos):
    print("\nExtrayendo alumnos...")
    driver.get(url_alumnos)

    try:
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.striped")))
        time.sleep(1)

        alumnos = driver.execute_script("""
            var tabla = document.querySelector('table.striped');
            if (!tabla) return [];

            var ths = Array.from(tabla.querySelectorAll('thead tr th'));
            var headers = ths.map(function(th) { return th.innerText.trim().toLowerCase(); });

            function colIdx(keywords) {
                for (var i = 0; i < headers.length; i++)
                    for (var k = 0; k < keywords.length; k++)
                        if (headers[i].indexOf(keywords[k]) !== -1) return i;
                return -1;
            }

            var iNombre = colIdx(['nombre', 'apellido']); if (iNombre < 0) iNombre = 0;
            var iNota1  = colIdx(['nota 1', 'nota1', 'parcial 1', '1er']);
            var iNota2  = colIdx(['nota 2', 'nota2', 'parcial 2', '2do']);
            var iCond   = colIdx(['condici', 'final', 'estado', 'resultado']);

            var result = [];
            tabla.querySelectorAll('tbody tr').forEach(function(fila) {
                var celdas = fila.querySelectorAll('td');
                if (celdas.length < 2) return;
                var nombre = celdas[iNombre] ? celdas[iNombre].innerText.trim() : '';
                if (!nombre) return;
                result.push({
                    Nombre:    nombre,
                    Nota1:     iNota1 >= 0 && celdas[iNota1] ? celdas[iNota1].innerText.trim() : '',
                    Nota2:     iNota2 >= 0 && celdas[iNota2] ? celdas[iNota2].innerText.trim() : '',
                    Condicion: iCond  >= 0 && celdas[iCond]  ? celdas[iCond].innerText.trim()  : '',
                    Nota:      ''
                });
            });
            return result;
        """)

        print(f"Se extrajeron {len(alumnos)} alumnos")
        return alumnos

    except Exception as e:
        print(f"Error al extraer alumnos: {e}")
        return []


def _normalizar_nombre(nombre):
    s = unicodedata.normalize("NFD", str(nombre).strip().lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


def _calcular_condicion(nota1, nota2):
    try:
        n1 = int(nota1) if str(nota1).strip() not in ("", "nan") else None
        n2 = int(nota2) if str(nota2).strip() not in ("", "nan") else None
    except (ValueError, TypeError):
        return ""
    if n1 is None or n2 is None:
        return ""
    if n1 < 4 or n2 < 4:
        return "Libre"
    return "Promovido" if (n1 + n2) / 2 >= 7 else "Regular"


def extraer_alumnos_con_notas(driver, url_alumnos, url_notas):
    """
    Extrae la lista de alumnos y cruza con las notas ya asignadas en las
    evaluaciones (mismo DOM que cargar_notas). Primera evaluación → Nota1,
    segunda → Nota2. Calcula Condicion automáticamente.
    """
    print("\nExtrayendo alumnos con notas...")

    alumnos = extraer_alumnos(driver, url_alumnos)
    if not alumnos:
        return []

    driver.get(url_notas)
    wait = WebDriverWait(driver, 15)
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    esperar_cloudflare(driver, timeout=30)
    time.sleep(1)

    links = driver.find_elements(By.CSS_SELECTOR, "a[href*='test_notes']")
    urls_eval = [l.get_attribute("href") for l in links[:2]]

    if not urls_eval:
        print("Sin evaluaciones — devolviendo alumnos sin notas")
        return alumnos

    mapa = {}  # nombre.lower() → {Nota1, Nota2}

    for idx, url_eval in enumerate(urls_eval):
        campo = "Nota1" if idx == 0 else "Nota2"
        print(f"  Extrayendo {campo}...")
        driver.get(url_eval)
        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "table.striped.responsive-table")
        ))
        time.sleep(1)

        # Guardar HTML de la primera evaluación para diagnóstico
        if idx == 0:
            debug_path = os.path.join(os.path.dirname(__file__), "debug_test_notes.html")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print("  HTML guardado en debug_test_notes.html")

        filas = driver.execute_script("""
            var rows = [];
            document.querySelectorAll(
                'table.striped.responsive-table tbody tr'
            ).forEach(function(fila) {
                var td = fila.querySelector('td.hide-on-med-and-down');
                if (!td) return;
                var strong = td.querySelector('strong');
                if (!strong) return;
                var nombre = strong.innerText.trim();

                // Fuente directa: span td_result_* ya contiene la nota actual
                var span = td.querySelector('span[id^="td_result_"]');
                var nota = span ? span.innerText.trim() : '';
                if (nota === '0') nota = '';  // 0 = AU (ausente)

                // Fallback: botón con clase green tiene data-set con el valor
                if (!nota) {
                    var btns = Array.from(fila.querySelectorAll('a[data-person]'));
                    for (var i = 0; i < btns.length; i++) {
                        if (btns[i].className.indexOf('green') !== -1) {
                            var ds = btns[i].getAttribute('data-set');
                            if (ds && ds !== '0') { nota = ds; break; }
                        }
                    }
                }

                rows.push({ nombre: nombre, nota: nota });
            });
            return rows;
        """)

        con_nota = 0
        for item in filas:
            key = _normalizar_nombre(item["nombre"])
            if key not in mapa:
                mapa[key] = {"Nota1": "", "Nota2": ""}
            mapa[key][campo] = item["nota"]
            if item["nota"]:
                con_nota += 1
        print(f"  {campo}: {len(filas)} alumnos, {con_nota} con nota detectada")

    for alumno in alumnos:
        key = _normalizar_nombre(alumno["Nombre"])
        notas = mapa.get(key) or next(
            (v for k, v in mapa.items() if key in k or k in key), {}
        )
        n1 = notas.get("Nota1", "")
        n2 = notas.get("Nota2", "")
        alumno["Nota1"]     = n1
        alumno["Nota2"]     = n2
        alumno["Condicion"] = _calcular_condicion(n1, n2)

    print(f"Extracción completada: {len(alumnos)} alumnos")
    return alumnos



    return resultado

def guardar_csv(alumnos, nombre_archivo=ARCHIVO_CSV):
    """Guarda los alumnos en un archivo CSV"""
    df = pd.DataFrame(alumnos)
    df.to_csv(nombre_archivo, index=False, encoding='utf-8')
    print(f"Archivo guardado: {nombre_archivo}")
    print(f"   Abre este archivo, completa la columna 'Nota' y guárdalo")

def cargar_notas(driver, url_notas, evaluacion=1):
    """Carga las notas desde el CSV a la plataforma. evaluacion=1 → 1ra, 2 → 2da."""
    print(f"\nCargando notas (evaluación {evaluacion})...")

    if not Path(ARCHIVO_CSV).exists():
        print(f"El archivo {ARCHIVO_CSV} no existe")
        return False

    df = pd.read_csv(ARCHIVO_CSV).fillna("")

    # Columna a leer: Nota1/Nota2 si existe y tiene datos, si no 'Nota'
    col_eval = f"Nota{evaluacion}"
    if col_eval in df.columns and df[col_eval].astype(str).str.strip().ne("").any():
        columna = col_eval
    elif "Nota" in df.columns:
        columna = "Nota"
    else:
        print("No se encontró columna de notas en el CSV")
        return False
    print(f"Leyendo notas de columna '{columna}'")

    driver.get(url_notas)

    try:
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)

        # url_notas puede ser tests-*.html (lista de evaluaciones) o test_notes-*.html directamente
        # Si es tests-*.html, buscar los links test_notes y navegar al índice de evaluación
        if "test_notes" not in driver.current_url:
            links_notas = driver.find_elements(By.CSS_SELECTOR, "a[href*='test_notes']")
            if not links_notas:
                print("No se encontraron evaluaciones en la página de tests")
                return False
            idx = evaluacion - 1
            if idx >= len(links_notas):
                print(f"La evaluación {evaluacion} no existe (hay {len(links_notas)})")
                return False
            url_eval = links_notas[idx].get_attribute("href")
            print(f"Navegando a evaluación {evaluacion}: {url_eval}")
            driver.get(url_eval)
            time.sleep(2)

        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "table.striped.responsive-table")
        ))

        # Construir mapa nombre_normalizado → person_id via JS
        # (textContent funciona aunque el elemento esté oculto por CSS responsive)
        mapa_persona = driver.execute_script("""
            var mapa = {};
            document.querySelectorAll(
                'table.striped.responsive-table tbody tr'
            ).forEach(function(fila) {
                var td = fila.querySelector('td.hide-on-med-and-down');
                if (!td) return;
                var strong = td.querySelector('strong');
                if (!strong) return;
                var nombre = strong.textContent.trim();
                if (!nombre) return;
                var btns = fila.querySelectorAll('a[data-person]');
                if (!btns.length) return;
                mapa[nombre.toLowerCase()] = btns[0].getAttribute('data-person');
            });
            return mapa;
        """)

        print(f"Alumnos encontrados en la página: {len(mapa_persona)}")

        notas_cargadas = 0
        notas_omitidas = 0

        for _, row in df.iterrows():
            nombre = str(row['Nombre']).strip()
            nota   = row[columna]

            # Validar nota
            if str(nota).strip() == "":
                print(f"{nombre}: Nota vacía, omitida")
                notas_omitidas += 1
                continue

            try:
                nota_valor = int(round(float(nota)))
                if nota_valor < 0 or nota_valor > 10:
                    print(f"{nombre}: Nota {nota_valor} fuera de rango (0-10), omitida")
                    notas_omitidas += 1
                    continue
            except ValueError:
                print(f"{nombre}: Nota no válida, omitida")
                notas_omitidas += 1
                continue

            # Buscar person_id: exacto normalizado, luego substring
            nombre_key = _normalizar_nombre(nombre)
            person_id  = mapa_persona.get(nombre.lower()) or mapa_persona.get(nombre_key)

            if not person_id:
                for nombre_pag, pid in mapa_persona.items():
                    if nombre_key in _normalizar_nombre(nombre_pag) or \
                       _normalizar_nombre(nombre_pag) in nombre_key:
                        person_id = pid
                        break

            if not person_id:
                print(f"{nombre}: No encontrado en la página, omitido")
                notas_omitidas += 1
                continue

            # Hacer clic en el botón correspondiente: id="btn_note-{nota}-{person_id}"
            btn_id = f"btn_note-{nota_valor}-{person_id}"
            try:
                btn = driver.find_element(By.ID, btn_id)
                driver.execute_script("arguments[0].click();", btn)
                print(f"{nombre}: Nota {nota_valor} asignada")
                notas_cargadas += 1
                time.sleep(0.8)  # pausa para que el servidor registre el cambio
            except Exception as e:
                print(f"{nombre}: Error al asignar nota — {e}")
                notas_omitidas += 1

        print(f"\nSe cargaron {notas_cargadas} notas ({notas_omitidas} omitidas)")
        return True

    except Exception as e:
        print(f"Error al cargar notas: {e}")
        return False