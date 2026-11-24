import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ID del Google Sheet (lo sacas de la URL: /d/ESTE_ES_EL_ID/edit)
SHEET_ID = "1fAZr-4AUmAW2RcMwOpquA85Mb50lpAHY-XQFa5G015g"

# --- OPCIÓN A: Leer vía CSV (La más rápida y sin credenciales) ---
def leer_via_csv():
    print("--- Leyendo Catálogo Original (Vía CSV) ---")
    # URL de exportación CSV para la primera hoja (gid=0)
    url_csv = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"
    try:
        df = pd.read_csv(url_csv)
        print(df.head()) # Muestra las primeras 5 filas
        return df
    except Exception as e:
        print(f"Error al leer CSV: {e}")
        print("Asegúrate de que la hoja esté compartida como 'Cualquier persona con el enlace puede ver'.")

# --- OPCIÓN B: Leer vía gspread (Requiere credenciales JSON de Google Cloud) ---
# def leer_via_api():
#     scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
#     creds = ServiceAccountCredentials.from_json_keyfile_name('credenciales.json', scope)
#     client = gspread.authorize(creds)
#     sheet = client.open_by_key(SHEET_ID).sheet1
#     data = sheet.get_all_records()
#     df = pd.DataFrame(data)
#     print(df.head())

if __name__ == "__main__":
    df = leer_via_csv()
    print(f"\nTotal de filas leídas: {len(df)}")
