# AGENTS.md

## Arquitectura: dos servidores independientes

### 1. Generador de catálogos (privado, local)

- Directorio: `~/proyects_conceptosmx_27/pdf_catalog_searcher`
- Arrancar (con el venv activo, el prompt muestra `(venv)`):

```bash
cd ~/proyects_conceptosmx_27/pdf_catalog_searcher
source venv/bin/activate
python3 app.py
```

- Flask escucha en `0.0.0.0:5000` → `http://localhost:5000` (`app.run(debug=False, host='0.0.0.0', port=5000)` en `app.py`).
- Función: subir PDFs, extraer piezas con `pymupdf` y escribirlas en la hoja `Catalogo_Original` del Google Sheet (`SHEET_ID` en `app.py`) usando `credenciales.json` (cuenta de servicio) en local, o `GOOGLE_CREDENTIALS` en Vercel. En local los lotes rechazados por cuota se guardan en `uploads/*_pendientes.csv` y se reintentan en un hilo de fondo; en Vercel se reintentan una vez de forma síncrona.
- No exponer públicamente sin autenticación: es el editor/generador.

### Despliegue del generador en Vercel

- El repo tiene `requirements.txt` y `.python-version` (3.12); Vercel detecta Flask desde `app.py` sin `vercel.json`.
- Variables de entorno obligatorias en el proyecto de Vercel:
  - `GOOGLE_CREDENTIALS`: contenido completo de `credenciales.json` como una sola línea JSON (el archivo no está en el repo).
  - `ADMIN_PASSWORD`: contraseña para el HTTP Basic Auth de todas las rutas.
  - `FLASK_SECRET_KEY`: clave larga y aleatoria para las sesiones/flash.
- Opcionales: `ADMIN_USER` (por defecto `admin`), `SHEET_ID` (por defecto el de `app.py`), `UPLOAD_FOLDER`.
- Limitaciones: en Vercel los archivos subidos van a `/tmp` (no persisten entre invocaciones), por lo que la vista previa de PDF está desactivada y no se puede servir `/uploads/<filename>`; usar el catálogo público para ver los PDFs. Procesar PDFs muy grandes puede superar el tiempo límite de la función.

### 2. Catálogo público (solo lectura)

- Directorio: `~/proyects_conceptosmx_27/CATALAGO_DINAMICO_V1`
- Arrancar en local (con el venv activo, el prompt muestra `(venv)`):

```bash
cd ~/proyects_conceptosmx_27/CATALAGO_DINAMICO_V1
npx vercel dev
```

- Producción: https://catalagodinamicv3.vercel.app/
- Función: interfaz pública de consulta de catálogos; endpoints en `api/catalog.js`, `api/proxy.js` y `api/admin/*`. Consulta un Apps Script que lee las hojas `IndiceParte`, `NotaReferencia`, `PrecioReferencia` y `VersionCatalogo` de su propio Google Sheet, no el `Catalogo_Original` del generador.

## Regla importante

No confundirlos: `python3 app.py` genera/escribe los catálogos; `npx vercel dev` solo los sirve/consulta para los usuarios. No hay sincronización automática comprobada entre ambos: tras generar catálogos nuevos, verificar que el sitio público refleje los cambios y actualizar sus hojas si hace falta.
