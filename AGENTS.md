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
- Función: subir PDFs, extraer piezas con `pymupdf` y escribirlas en la hoja `Catalogo_Original` del Google Sheet (`SHEET_ID` en `app.py`) usando `credenciales.json` (cuenta de servicio). Los lotes rechazados por cuota se guardan en `uploads/*_pendientes.csv` y se reintentan en un hilo de fondo.
- No exponer públicamente: es el editor/generador.

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
