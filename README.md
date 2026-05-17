# Gestor de Notas — DaVinci

Aplicación web local para extraer alumnos y cargar notas en la plataforma [dvcarreras.davinci.edu.ar](https://dvcarreras.davinci.edu.ar/).

---

## Requisitos

- Python 3.10 o superior
- Microsoft Edge instalado
- Conexión a internet

---

## Instalación

```bash
# Crear entorno virtual e instalar dependencias
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## Iniciar la aplicación

```bash
venv\Scripts\python.exe app.py
```

Luego abrí en el navegador: **http://localhost:5000**

---

## Flujo completo paso a paso

### 1. Abrir el navegador automatizado

Hacé clic en **Abrir navegador**.

Se abre una ventana de Microsoft Edge controlada por la app.

- **Si ya iniciaste sesión antes**: la app restaura la sesión desde las cookies guardadas y entrás directo.
- **Si es la primera vez o las cookies expiraron**: aparece el formulario de login de DaVinci. Completalo manualmente (usuario y contraseña). La sesión queda guardada automáticamente para la próxima vez.

---

### 2. Cargar las materias

Una vez con el navegador abierto, hacé clic en **Cargar materias**.

La app recorre tus comisiones y extrae todas las materias disponibles. Aparecen como una lista de botones.

---

### 3. Seleccionar una materia

Hacé clic en el nombre de la materia con la que querés trabajar. Queda marcada como **materia activa**.

Todos los pasos siguientes (extracción, carga, Excel) operan sobre esa materia.

---

### 4. Extraer alumnos

Tenés dos opciones:

#### Opción A — Extraer alumnos (solo nombres)

Hacé clic en **Extraer alumnos**.

Descarga la lista de alumnos inscriptos. Las columnas **Nota 1**, **Nota 2** y **Condición** quedan vacías.

Usá esta opción cuando todavía no cargaste ninguna evaluación en la plataforma.

#### Opción B — Extraer alumnos con notas

Hacé clic en **Extraer alumnos con notas** *(si existen evaluaciones)*.

Descarga la lista de alumnos **y** lee las notas ya asignadas en la plataforma:

- **Nota 1** → primera evaluación existente
- **Nota 2** → segunda evaluación existente
- **Condición** → calculada automáticamente:
  - `Libre`: alguna nota menor a 4
  - `Regular`: ambas ≥ 4 y promedio menor a 7
  - `Promovido`: ambas ≥ 4 y promedio ≥ 7

Usá esta opción para ver el estado actual o para revisar antes de modificar notas.

---

### 5. Editar notas en la tabla

Una vez extraídos los alumnos, la tabla muestra:

| # | Nombre | Nota 1 | Nota 2 | Condición | Nota (0–10) |
|---|--------|--------|--------|-----------|-------------|

La columna **Nota (0–10)** es editable directamente en la página. Escribí el valor para cada alumno y hacé clic en **Guardar notas** para persistirlo en el archivo local.

---

### 6. Cargar notas en la plataforma

Con las notas completadas en la tabla, hacé clic en:

- **1ra Evaluación** → carga los valores de la columna *Nota 1* a la primera evaluación de la plataforma
- **2da Evaluación** → carga los valores de la columna *Nota 2* a la segunda evaluación

La app navega automáticamente a la evaluación correspondiente y asigna cada nota haciendo clic en los botones de la plataforma. En la consola podés ver el progreso alumno por alumno.

---

### 7. Flujo con Excel (alternativo)

Si preferís editar las notas en una planilla:

#### Exportar

Hacé clic en **Descargar Excel**.

Se descarga un archivo `.xlsx` con el nombre de la materia (por ejemplo `notas_K1AB_Estadística I.xlsx`) con las columnas **Nombre**, **Nota 1**, **Nota 2** y **Condición**.

Editá las notas en Excel y guardá el archivo.

#### Importar

Hacé clic en **Importar Excel** y seleccioná el archivo modificado.

La app actualiza las columnas *Nota 1* y/o *Nota 2* en la tabla local. Aparece el mensaje **"Importación exitosa. X alumnos importados"** y se muestra el panel verde **Guardar desde Excel**.

#### Guardar desde Excel

Hacé clic en **1ra Evaluación** o **2da Evaluación** en el panel verde para enviar las notas importadas directamente a la plataforma.

---

## Solución de problemas

| Problema | Causa probable | Solución |
|----------|---------------|----------|
| El navegador no abre | Edge no está instalado | Instalá Microsoft Edge |
| No muestra materias | No estás logueado o la sesión expiró | Reabrí el navegador y logueate |
| `0 notas cargadas` | Las columnas Nota 1/Nota 2 están vacías | Completá las notas antes de cargar |
| Alumno no encontrado | Diferencia de nombre entre CSV y plataforma | Verificá el nombre en la tabla |
| Error al abrir (puerto en uso) | La app ya está corriendo | Cerrá la instancia anterior o cambiá el puerto en `app.py` |

---

## Archivos generados

| Archivo | Descripción |
|---------|-------------|
| `alumnos_notas.csv` | Lista de alumnos con notas (se sobreescribe al extraer) |
| `session_cookies.json` | Cookies de sesión guardadas (no subir a Git) |
| `debug_test_notes.html` | HTML de diagnóstico generado al extraer con notas |

Estos archivos están en `.gitignore` y no se suben al repositorio.
