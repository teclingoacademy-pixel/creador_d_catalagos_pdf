import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1. Configurar credenciales
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credenciales.json', scope)
client = gspread.authorize(creds)

# 2. Abrir el Google Sheet
SHEET_ID = "1fAZr-4AUmAW2RcMwOpquA85Mb50lpAHY-XQFa5G015g"
sheet = client.open_by_key(SHEET_ID)
hoja_catalogo = sheet.worksheet("Catalogo_Original")

# 3. Datos de ejemplo (extraídos de tu PDF original)
# Columnas: ID_Pieza, Codigo_Catalogo, Descripcion, Precio, Catalogo_PDF, Pagina, Coordenada_X, Coordenada_Y, Ancho, Alto
datos = [
    ["1", "3803605", "Bomba Agua Cummins N14 / WP2260", "2128.00", "catalogo_ejemplo.pdf", "1", "0", "0", "0", "0"],
    ["2", "CALCAS FORD 5000", "Juego Calcomanias Ford 5000 =81822593 =VPM2042 =C9NN16N682C =S.8412", "340.00", "catalogo_ejemplo.pdf", "1", "0", "0", "0", "0"],
    ["3", "S3739", "Extension Toma Fuerza de 1000 a 540 RPM 1.3/8\" (21 x 6 Dientes) =110GG=S.3739", "920.00", "catalogo_ejemplo.pdf", "1", "0", "0", "0", "0"],
    ["4", "4410", "Enchufe Rapido Hembra 1/2\" (S4349) + PLACA =S.4410", "385.00", "catalogo_ejemplo.pdf", "1", "0", "0", "0", "0"],
    ["5", "D3NN478F", "Cilindro Hidráulico Ford 4000", "5768.00", "catalogo_ejemplo.pdf", "1", "0", "0", "0", "0"]
]

# 4. Insertar los datos
for fila in datos:
    hoja_catalogo.append_row(fila)

print("✅ 5 piezas insertadas en Catalogo_Original.")

# 5. Insertar un par de notas cruzadas de prueba
hoja_notas = sheet.worksheet("Notas_y_Cruces")
notas = [
    ["", "1", "WP2260", "Numero Cruzado", "Admin", "2026-11-22"],
    ["", "1", "Filtro alternativo Cummins", "Nota de Texto", "Admin", "2026-11-22"],
    ["", "5", "Cilindro rojo Ford", "Nota de Texto", "Admin", "2026-11-22"]
]
for nota in notas:
    hoja_notas.append_row(nota)

print("✅ Notas y cruces insertados.")