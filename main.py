from fastapi import FastAPI, Request
import json
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from servicios.openai_agent import generar_respuesta_ia, herramientas_openai

# 1. Inicializamos FastAPI
app = FastAPI()

# 2. Inicializamos la memoria
memoria_charlas = {}

# 3. Definimos la función de Google Sheets ANTES de usarla en el webhook
def guardar_prospecto_en_sheets(nombre: str, telefono: str, tratamiento: str = "No especificado", fecha_nacimiento: str = "No proporcionada"):
    """
    Conecta con Google Sheets e inserta los datos del paciente.
    """
    try:
        credenciales_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(credenciales_dict, scopes=SCOPES)
        service = build('sheets', 'v4', credentials=creds)
        
        SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID") 
        RANGE_NAME = 'Hoja 1!A:G' 
        
        fecha_registro = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Ahora guardamos: Fecha, Nombre, Teléfono, Tratamiento, Cumpleaños, Estado
        row_data = [fecha_registro, nombre, telefono, tratamiento, fecha_nacimiento, "Pendiente"]
        
        body = {'values': [row_data]}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME,
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
        return True
    except Exception as e:
        print(f"Error al guardar en Google Sheets: {e}")
        return False
    
# 4. Tu ruta de Webhook
@app.post("/webhook")
async def recibir_mensaje(datos: Request):
    raw_bytes = await datos.body()
    raw_texto = raw_bytes.decode("utf-8", errors="replace")

    try:
        # strict=False soluciona el problema de los saltos de línea crudos de ManyChat
        cuerpo = json.loads(raw_texto, strict=False)
    except Exception as e:
        print(f"❌ ERROR AL PARSEAR JSON: {e}")
        print(f"📄 BODY CRUDO RECIBIDO: {raw_texto}")
        return {"respuesta_servidor": "Permíteme revisar esa información con nuestro equipo para darte una respuesta correcta."}

# Aplanamos el texto para que la IA no se confunda con múltiples renglones
    texto_usuario = str(cuerpo.get("texto", "")).replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
    identificador = str(cuerpo.get("user_id", "usuario_default")).strip()

    print(f"📥 MENSAJE RECIBIDO de [{identificador}]: '{texto_usuario[:45]}...'")
    
    if not texto_usuario or texto_usuario == "Última entrada de texto":
        return {"respuesta_servidor": "Hola, ¿en qué te puedo ayudar hoy? Si tienes alguna pregunta sobre tratamientos estéticos o deseas agendar una valoración, estoy aquí para apoyarte."}

    palabras_reinicio = ["reiniciar", "borrar", "empezar de cero", "clear", "nueva consulta"]
    if any(palabra in texto_usuario.lower() for palabra in palabras_reinicio):
        memoria_charlas[identificador] = []
        return {"respuesta_servidor": "¡Listo! He borrado el historial de nuestra conversación anterior. ¿En qué nuevo tratamiento o servicio te gustaría que te ayude hoy?"}

    if identificador not in memoria_charlas:
        memoria_charlas[identificador] = []

    memoria_charlas[identificador].append({"role": "user", "content": texto_usuario})

    if len(memoria_charlas[identificador]) > 8:
        memoria_charlas[identificador] = memoria_charlas[identificador][-8:]

    print(f"--- Memoria actual del usuario [{identificador}] (Mensajes: {len(memoria_charlas[identificador])}) ---")

    # Ahora sí, el editor reconoce la función porque está definida arriba
    respuesta_ia = await generar_respuesta_ia(memoria_charlas[identificador], herramientas_openai, guardar_prospecto_en_sheets)

    memoria_charlas[identificador].append({"role": "assistant", "content": respuesta_ia})

    print("=== IA RESPONDE ===", respuesta_ia)

    return {"respuesta_servidor": respuesta_ia}