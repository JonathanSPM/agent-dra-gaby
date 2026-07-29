from fastapi import FastAPI, Request
import json
import os
import re
import html
from datetime import datetime
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build
from servicios.openai_agent import generar_respuesta_ia, herramientas_openai

# 1. Inicializamos FastAPI
app = FastAPI()

# 2. Inicializamos la memoria
memoria_charlas = {}


def normalizar_texto_usuario(texto):
    """
    Limpia mensajes recibidos desde ManyChat/WhatsApp.
    Convierte saltos de línea reales, saltos escapados, etiquetas <br>
    y espacios múltiples en un texto plano entendible para la IA.
    """
    if texto is None:
        return ""

    texto = str(texto)

    # Decodifica entidades HTML como &nbsp;, &amp;, etc.
    texto = html.unescape(texto)

    # Convierte <br>, <br/>, <br /> en espacios
    texto = re.sub(r"<br\s*/?>", " ", texto, flags=re.IGNORECASE)

    # Convierte saltos escapados tipo "\\n"
    texto = texto.replace("\\r\\n", " ")
    texto = texto.replace("\\n", " ")
    texto = texto.replace("\\r", " ")

    # Convierte saltos reales
    texto = texto.replace("\r\n", " ")
    texto = texto.replace("\n", " ")
    texto = texto.replace("\r", " ")

    # Compacta espacios múltiples
    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


# 3. Definimos la función de Google Sheets
def guardar_prospecto_en_sheets(
    nombre: str,
    telefono: str,
    tratamiento: str = "No especificado",
    fecha_nacimiento: str = "No proporcionada"
):
    """
    Conecta con Google Sheets e inserta los datos del paciente.
    """
    try:
        credenciales_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS"))

        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

        creds = service_account.Credentials.from_service_account_info(
            credenciales_dict,
            scopes=SCOPES
        )

        service = build('sheets', 'v4', credentials=creds)

        SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID")
        RANGE_NAME = 'Hoja 1!A:G'

        fecha_registro = datetime.now(
            ZoneInfo("America/Mexico_City")
        ).strftime("%Y-%m-%d %H:%M:%S")

        row_data = [
            fecha_registro,
            nombre,
            telefono,
            tratamiento,
            fecha_nacimiento,
            "Pendiente"
        ]

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


# 4. Ruta de Webhook
@app.post("/webhook")
async def recibir_mensaje(datos: Request):
    raw_bytes = await datos.body()
    raw_texto = raw_bytes.decode("utf-8", errors="replace")

    try:
        cuerpo = json.loads(raw_texto, strict=False)
    except Exception as e:
        print(f"❌ ERROR AL PARSEAR JSON: {e}")
        print(f"📄 BODY CRUDO RECIBIDO: {repr(raw_texto)}")
        return {
            "respuesta_servidor": "Permíteme revisar esa información con nuestro equipo para darte una respuesta correcta."
        }

    # Buscamos primero el formato ManyChat Full Contact Data
    # y luego tus claves personalizadas como respaldo.
    texto_crudo = cuerpo.get("last_input_text", cuerpo.get("texto", ""))
    id_crudo = cuerpo.get("id", cuerpo.get("user_id", "usuario_default"))

    texto_usuario = normalizar_texto_usuario(texto_crudo)
    identificador = str(id_crudo).strip()

    print("========== WEBHOOK RECIBIDO ==========")
    print("RAW BODY:", repr(raw_texto))
    print("CUERPO PARSEADO:", cuerpo)
    print("TEXTO CRUDO:", repr(texto_crudo))
    print("TEXTO NORMALIZADO:", repr(texto_usuario))
    print("ID CRUDO:", repr(id_crudo))
    print("IDENTIFICADOR:", repr(identificador))
    print("======================================")

    if not texto_usuario or texto_usuario == "Última entrada de texto":
        return {
            "respuesta_servidor": "Hola, ¿en qué te puedo ayudar hoy? Si tienes alguna pregunta sobre tratamientos estéticos o deseas agendar una valoración, estoy aquí para apoyarte."
        }

    palabras_reinicio = [
        "reiniciar",
        "borrar",
        "empezar de cero",
        "clear",
        "nueva consulta"
    ]

    if any(palabra in texto_usuario.lower() for palabra in palabras_reinicio):
        memoria_charlas[identificador] = []
        return {
            "respuesta_servidor": "¡Listo! He borrado el historial de nuestra conversación anterior. ¿En qué nuevo tratamiento o servicio te gustaría que te ayude hoy?"
        }

    if identificador not in memoria_charlas:
        memoria_charlas[identificador] = []

    memoria_charlas[identificador].append({
        "role": "user",
        "content": texto_usuario
    })

    # Recomiendo subirlo de 8 a 16 para no perder contexto tan rápido
    if len(memoria_charlas[identificador]) > 16:
        memoria_charlas[identificador] = memoria_charlas[identificador][-16:]

    print(
        f"--- Memoria actual del usuario [{identificador}] "
        f"(Mensajes: {len(memoria_charlas[identificador])}) ---"
    )
    print(memoria_charlas[identificador])

    respuesta_ia = await generar_respuesta_ia(
        memoria_charlas[identificador],
        herramientas_openai,
        guardar_prospecto_en_sheets
    )

    memoria_charlas[identificador].append({
        "role": "assistant",
        "content": respuesta_ia
    })

    print("=== IA RESPONDE ===", respuesta_ia)

    return {
        "respuesta_servidor": respuesta_ia
    }