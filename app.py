from flask import Flask, request, render_template_string, redirect, url_for, flash, send_from_directory, Response
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import json
import tempfile
import pymupdf
import re
import time
import csv
import threading
from werkzeug.utils import secure_filename

ON_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super_secret_key_para_flash")
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER") or (
    os.path.join(tempfile.gettempdir(), "catalogos_uploads") if ON_VERCEL else "uploads"
)
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

@app.before_request
def verificar_acceso():
    if not ADMIN_PASSWORD:
        return None
    auth = request.authorization
    if auth and auth.username == ADMIN_USER and auth.password == ADMIN_PASSWORD:
        return None
    return Response("Acceso restringido", 401, {
        "WWW-Authenticate": 'Basic realm="Generador de catálogos"'
    })

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credenciales_json = os.environ.get("GOOGLE_CREDENTIALS")
if credenciales_json:
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(credenciales_json), scope)
else:
    creds = ServiceAccountCredentials.from_json_keyfile_name('credenciales.json', scope)
client = gspread.authorize(creds)
SHEET_ID = os.environ.get("SHEET_ID", "1fAZr-4AUmAW2RcMwOpquA85Mb50lpAHY-XQFa5G015g")

def leer_hoja_a_df(nombre_hoja):
    sheet = client.open_by_key(SHEET_ID)
    valores = sheet.worksheet(nombre_hoja).get_all_values()
    if len(valores) < 2:
        return pd.DataFrame()
    encabezados = [h.strip() for h in valores[0]]
    filas = valores[1:]
    indices_validos = []
    encabezados_limpios = []
    vistos = set()
    for idx, h in enumerate(encabezados):
        if h and h not in vistos:
            vistos.add(h)
            indices_validos.append(idx)
            encabezados_limpios.append(h)
    datos_limpios = [
        [fila[i] if i < len(fila) else "" for i in indices_validos]
        for fila in filas
    ]
    return pd.DataFrame(datos_limpios, columns=encabezados_limpios)

def buscar_en_sheet(termino):
    df_catalogo = leer_hoja_a_df("Catalogo_Original")
    df_notas = leer_hoja_a_df("Notas_y_Cruces")

    if df_catalogo.empty:
        return []

    if not df_notas.empty and "ID_Pieza" in df_catalogo.columns and "ID_Pieza_Relacionada" in df_notas.columns:
        df_catalogo["ID_Pieza"] = df_catalogo["ID_Pieza"].astype(str)
        df_notas["ID_Pieza_Relacionada"] = df_notas["ID_Pieza_Relacionada"].astype(str)
        df_merged = pd.merge(
            df_catalogo,
            df_notas,
            left_on="ID_Pieza",
            right_on="ID_Pieza_Relacionada",
            how="left"
        )
    else:
        df_merged = df_catalogo.copy()

    for col in ["Texto_Ingresado", "Tipo", "Codigo_Catalogo", "Descripcion", "Pagina", "Precio", "Coordenada_X", "Coordenada_Y", "Ancho", "Alto"]:
        if col not in df_merged.columns:
            df_merged[col] = ""

    if 'Catalogo_PDF' not in df_merged.columns and 'Archivo_Origen' in df_merged.columns:
        df_merged['Catalogo_PDF'] = df_merged['Archivo_Origen']
    elif 'Catalogo_PDF' in df_merged.columns and 'Archivo_Origen' in df_merged.columns:
        df_merged['Catalogo_PDF'] = df_merged['Catalogo_PDF'].replace('', pd.NA).fillna(df_merged['Archivo_Origen'])
    elif 'Catalogo_PDF' not in df_merged.columns:
        df_merged['Catalogo_PDF'] = ""

    termino_lower = str(termino).lower()
    mascara = (
        df_merged['Codigo_Catalogo'].astype(str).str.lower().str.contains(termino_lower, na=False, regex=False) |
        df_merged['Descripcion'].astype(str).str.lower().str.contains(termino_lower, na=False, regex=False) |
        df_merged['Texto_Ingresado'].astype(str).str.lower().str.contains(termino_lower, na=False, regex=False)
    )
    return df_merged[mascara].fillna('').to_dict(orient='records')

def extraer_piezas_pagina(texto_pagina):
    lineas = [l.strip() for l in texto_pagina.split("\n")]
    piezas = []
    inicio = 0
    for i, l in enumerate(lineas):
        if l.startswith("Emitido el"):
            inicio = i + 1
            break
    i = inicio
    codigo_actual = None
    descripcion_lineas = []
    while i < len(lineas):
        linea = lineas[i]
        if re.match(r'^[\d,]+\.\d{2}$', linea) and i + 1 < len(lineas) and lineas[i + 1] == "$":
            precio = linea.replace(',', '')
            piezas.append({
                'codigo': codigo_actual or '',
                'descripcion': ' '.join(descripcion_lineas).strip(),
                'precio': precio
            })
            codigo_actual = None
            descripcion_lineas = []
            i += 2
            continue
        if codigo_actual is None:
            codigo_actual = linea
        else:
            descripcion_lineas.append(linea)
        i += 1
    return piezas

def importar_filas(filas, esperar=False):
    hoja = client.open_by_key(SHEET_ID).worksheet("Catalogo_Original")
    insertadas = 0
    fallidas = []
    for i in range(0, len(filas), 20):
        lote = filas[i:i+20]
        try:
            hoja.append_rows(lote, value_input_option='USER_ENTERED')
            insertadas += len(lote)
        except Exception as e:
            print(f"[RETRY] Error en lote: {e}")
            fallidas.extend(lote)
        if esperar:
            time.sleep(2)
    return insertadas, fallidas

def importar_pendientes_background(ruta_csv):
    print(f"[BACKGROUND] Iniciando importación de {ruta_csv}...")
    try:
        with open(ruta_csv, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            filas = list(reader)
        insertadas, fallidas = importar_filas(filas, esperar=True)
        print(f"[BACKGROUND] {insertadas} insertadas, {len(fallidas)} fallidas.")
    except Exception as e:
        print(f"[BACKGROUND] Error: {e}")

def procesar_pdf(filepath, filename):
    doc = pymupdf.open(filepath)
    hoja_catalogo = client.open_by_key(SHEET_ID).worksheet("Catalogo_Original")
    df_existentes = leer_hoja_a_df("Catalogo_Original")
    existentes = df_existentes.to_dict(orient='records') if not df_existentes.empty else []
    ultimo_id = max([int(r['ID_Pieza']) for r in existentes if str(r.get('ID_Pieza', '')).isdigit()], default=0)
    filas_a_insertar = []
    ya_existentes = set([
        (
            str(r.get('Codigo_Catalogo', '')),
            str(r.get('Catalogo_PDF', r.get('Archivo_Origen', ''))),
            str(r.get('Pagina', ''))
        )
        for r in existentes
    ])

    for num_pagina, page in enumerate(doc, start=1):
        piezas = extraer_piezas_pagina(page.get_text("text"))
        for p in piezas:
            codigo = p['codigo'].strip()
            descripcion = re.sub(r'\s+', ' ', p['descripcion']).strip()
            precio = p['precio']
            if not codigo or not descripcion:
                continue
            clave = (codigo, filename, str(num_pagina))
            if clave in ya_existentes:
                continue
            ya_existentes.add(clave)
            coordenadas = page.search_for(codigo)
            if coordenadas:
                rect = coordenadas[0]
                x0, y0, ancho, alto = rect.x0, rect.y0, rect.x1 - rect.x0, rect.y1 - rect.y0
            else:
                x0, y0, ancho, alto = 0, 0, 0, 0
            ultimo_id += 1
            filas_a_insertar.append([
                str(ultimo_id),
                codigo,
                descripcion,
                precio,
                filename,
                str(num_pagina),
                str(int(x0)),
                str(int(y0)),
                str(int(ancho)),
                str(int(alto))
            ])

    insertadas = 0
    pendientes = []
    for i in range(0, len(filas_a_insertar), 40):
        lote = filas_a_insertar[i:i+40]
        try:
            hoja_catalogo.append_rows(lote, value_input_option='USER_ENTERED')
            insertadas += len(lote)
        except Exception as e:
            print(f"Error en lote (posible cuota): {e}")
            pendientes.extend(lote)

    if pendientes:
        if ON_VERCEL:
            guardadas, pendientes = importar_filas(pendientes)
            insertadas += guardadas
        else:
            base = os.path.splitext(os.path.basename(filename))[0]
            ruta_csv = os.path.join(UPLOAD_FOLDER, f"{base}_pendientes.csv")
            with open(ruta_csv, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'ID_Pieza', 'Codigo_Catalogo', 'Descripcion', 'Precio',
                    'Catalogo_PDF', 'Pagina', 'Coordenada_X', 'Coordenada_Y', 'Ancho', 'Alto'
                ])
                writer.writerows(pendientes)
            hilo = threading.Thread(target=importar_pendientes_background, args=(ruta_csv,))
            hilo.start()
    return insertadas, len(pendientes)

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Buscador de Catálogos MEJOR</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; margin: 0; padding: 0; background-color: #f4f6f8; color: #333; height: 100vh; display: flex; flex-direction: column; }
        header { background: white; padding: 15px 40px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); display: flex; justify-content: space-between; align-items: center; z-index: 10; }
        h1 { color: #0056b3; margin: 0; font-size: 24px; }
        .main-container { display: flex; flex: 1; overflow: hidden; }
        .left-panel { width: 40%; padding: 20px; overflow-y: auto; background: #fff; border-right: 1px solid #ddd; }
        .search-box { display: flex; margin-bottom: 20px; }
        input[type="text"] { flex: 1; padding: 12px; font-size: 15px; border: 1px solid #ccc; border-radius: 5px 0 0 5px; outline: none; }
        button { padding: 12px 20px; font-size: 15px; background-color: #0056b3; color: white; border: none; border-radius: 0 5px 5px 0; cursor: pointer; }
        button:hover { background-color: #004494; }
        .upload-box { display: flex; flex-direction: column; gap: 10px; background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 1px dashed #ccc; }
        .upload-box input[type="file"] { padding: 8px; background: white; border: 1px solid #ddd; border-radius: 4px; }
        .upload-box button { border-radius: 5px; width: 100%; }
        .resultado { background: white; padding: 15px; margin-bottom: 12px; border-left: 4px solid #0056b3; box-shadow: 0 2px 4px rgba(0,0,0,0.05); cursor: pointer; transition: 0.2s; border-radius: 0 5px 5px 0; }
        .resultado:hover { background: #f0f7ff; transform: translateX(5px); }
        .resultado h3 { margin: 0 0 5px 0; font-size: 16px; color: #0056b3; }
        .precio { font-size: 1.1em; font-weight: bold; color: #28a745; margin: 5px 0; }
        .tag { background: #e9ecef; padding: 4px 10px; border-radius: 12px; font-size: 0.8em; margin-right: 5px; display: inline-block; margin-top: 5px; }
        .tag.cross { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .tag.nota { background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
        .flash { padding: 10px; margin-bottom: 20px; border-radius: 5px; font-size: 14px; }
        .flash.success { background: #d4edda; color: #155724; }
        .flash.info { background: #cce5ff; color: #004085; }
        .flash.error { background: #f8d7da; color: #721c24; }
        .right-panel { width: 60%; position: relative; background: #e9ecef; display: flex; justify-content: center; align-items: center; overflow: auto; }
        .portada-container { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; justify-content: center; align-items: center; background: #ffffff; }
        .portada-img { max-width: 70%; max-height: 70%; object-fit: contain; opacity: 0.9; }
        #pdfViewer { display: none; width: 100%; height: 100%; padding: 20px; box-sizing: border-box; overflow: auto; }
        canvas { display: block; margin: 0 auto; box-shadow: 0 4px 10px rgba(0,0,0,0.15); background: white; }
        .pdf-title { position: absolute; top: 10px; left: 20px; background: rgba(0, 86, 179, 0.9); color: white; padding: 8px 15px; border-radius: 20px; font-size: 14px; z-index: 5; display: none; }
    </style>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.min.js"></script>
</head>
<body>
    <header>
        <h1>🔍 Buscador de Catálogos</h1>
    </header>

    <div class="main-container">
        <div class="left-panel">
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}
                {% for category, message in messages %}
                  <div class="flash {{ category }}">{{ message }}</div>
                {% endfor %}
              {% endif %}
            {% endwith %}

            <div class="upload-box">
                <strong>📄 Subir Nuevo Catálogo</strong>
                <form action="/upload" method="post" enctype="multipart/form-data" style="display: flex; flex-direction: column; gap: 10px;">
                    <input type="file" name="file" accept=".pdf" required>
                    <button type="submit" style="border-radius: 5px;">Subir y Procesar PDF</button>
                </form>
            </div>

            <form action="/buscar" method="get" class="search-box">
                <input type="text" name="q" value="{{ query }}" placeholder="Buscar por número de parte, descripción o nota..." required>
                <button type="submit">Buscar</button>
            </form>

            {% if query %}
                <h3 style="color: #555; margin-top: 0;">Resultados para: "{{ query }}"</h3>
                {% if resultados %}
                    {% for r in resultados %}
                    <div class="resultado"
                         data-archivo="{{ r.Catalogo_PDF | e }}"
                         data-pagina="{{ r.Pagina }}"
                         data-x="{{ r.Coordenada_X }}"
                         data-y="{{ r.Coordenada_Y }}"
                         data-ancho="{{ r.Ancho }}"
                         data-alto="{{ r.Alto }}"
                         onclick="abrirPdfDesdeElemento(this)">
                        <h3>{{ r.Codigo_Catalogo }} - {{ r.Descripcion }}</h3>
                        <p class="precio">$ {{ r.Precio }}</p>
                        <p style="font-size: 0.85em; color: #666; margin: 5px 0;">Pág. {{ r.Pagina }}</p>
                        {% if r.Texto_Ingresado %}
                            <span class="tag {{ 'cross' if r.Tipo == 'Numero Cruzado' else 'nota' }}">
                                {{ r.Texto_Ingresado }}
                            </span>
                        {% endif %}
                    </div>
                    {% endfor %}
                {% else %}
                    <p style="color: #dc3545; font-weight: bold;">No se encontraron resultados.</p>
                {% endif %}
            {% endif %}
        </div>

        <div class="right-panel">
            <div class="portada-container" id="portadaContainer">
                <img src="/portada.png" class="portada-img" alt="Portada Catálogos Interactivos">
            </div>

            <div class="pdf-title" id="pdfTitle">Catálogo Cargado</div>

            <div id="pdfViewer">
                <canvas id="pdfCanvas"></canvas>
            </div>
        </div>
    </div>

    <script>
        pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.worker.min.js';
        const ON_VERCEL = {{ 'true' if on_vercel else 'false' }};

        function abrirPdfDesdeElemento(elemento) {
            const archivo = elemento.getAttribute('data-archivo');
            const pagina = parseInt(elemento.getAttribute('data-pagina'), 10);
            const x = parseFloat(elemento.getAttribute('data-x')) || 0;
            const y = parseFloat(elemento.getAttribute('data-y')) || 0;
            const ancho = parseFloat(elemento.getAttribute('data-ancho')) || 0;
            const alto = parseFloat(elemento.getAttribute('data-alto')) || 0;

            if (!archivo || archivo === 'None' || archivo === '') {
                alert("No se encontró el nombre del archivo PDF para esta pieza en la base de datos.");
                return;
            }

            if (ON_VERCEL) {
                alert('La vista previa de PDF no está disponible en Vercel (los archivos son temporales). Consulta el catálogo público para ver el PDF.');
                return;
            }

            if (isNaN(pagina) || pagina < 1) {
                alert("Número de página inválido para esta pieza.");
                return;
            }

            document.getElementById('portadaContainer').style.display = 'none';
            document.getElementById('pdfViewer').style.display = 'block';
            document.getElementById('pdfTitle').style.display = 'block';
            document.getElementById('pdfTitle').innerText = 'Cargando ' + archivo + ' - Pág. ' + pagina + '...';

            const url = '/uploads/' + encodeURIComponent(archivo);
            const loadingTask = pdfjsLib.getDocument(url);

            loadingTask.promise.then(function(pdf) {
                return pdf.getPage(pagina);
            }).then(function(page) {
                const scale = 1.5;
                const viewport = page.getViewport({ scale: scale });
                const canvas = document.getElementById('pdfCanvas');
                const context = canvas.getContext('2d');
                canvas.height = viewport.height;
                canvas.width = viewport.width;

                const renderContext = {
                    canvasContext: context,
                    viewport: viewport
                };

                return page.render(renderContext).promise.then(function() {
                    if (ancho > 0 && alto > 0) {
                        context.strokeStyle = '#ff0000';
                        context.lineWidth = 3;
                        context.strokeRect(x * scale, y * scale, ancho * scale, alto * scale);
                    }
                    document.getElementById('pdfTitle').innerText = archivo + ' - Página ' + pagina;
                });
            }).catch(function(error) {
                alert('Error al cargar el PDF. Asegúrate de que el archivo exista en la carpeta uploads. Detalle: ' + error.message);
                document.getElementById('portadaContainer').style.display = 'flex';
                document.getElementById('pdfViewer').style.display = 'none';
                document.getElementById('pdfTitle').style.display = 'none';
            });
        }
    </script>
</body>
</html>'''

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, query='', resultados=[], on_vercel=ON_VERCEL)

@app.route('/buscar')
def buscar():
    query = request.args.get('q', '')
    try:
        resultados = buscar_en_sheet(query) if query else []
    except Exception as e:
        flash(f'Error al buscar en Google Sheets: {str(e)}', 'error')
        resultados = []
    return render_template_string(HTML_TEMPLATE, query=query, resultados=resultados, on_vercel=ON_VERCEL)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(url_for('index'))
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return redirect(url_for('index'))
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    try:
        insertadas, pendientes = procesar_pdf(filepath, filename)
        if pendientes > 0:
            if ON_VERCEL:
                flash(f'Se procesaron {insertadas} piezas. {pendientes} no se pudieron guardar por cuota de Google Sheets; vuelve a subir el PDF más tarde.', 'error')
            else:
                flash(f'Se procesaron {insertadas} piezas. {pendientes} quedaron en cola y se están subiendo automáticamente en segundo plano.', 'info')
        elif insertadas > 0:
            flash(f'Archivo "{filename}" procesado. Se agregaron {insertadas} piezas nuevas exitosamente.', 'success')
        else:
            flash('El archivo no contiene piezas nuevas o ya estaban registradas.', 'success')
    except Exception as e:
        flash(f'Error al procesar PDF: {str(e)}', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)