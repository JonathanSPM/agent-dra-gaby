from fastapi import FastAPI, Request
import json
import os
import re
import html
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

from servicios.openai_agent import generar_respuesta_ia, herramientas_openai


app = FastAPI()

memoria_charlas = {}


@app.middleware("http")
async def log_todas_las_peticiones(request: Request, call_next):
    print("========== PETICION ENTRANTE ==========")
    print("METHOD:", request.method)
    print("URL:", str(request.url))
    print("HEADERS:", dict(request.headers))
    print("=======================================")

    response = await call_next(request)

    print("STATUS RESPONSE:", response.status_code)
    return response


@app.get("/")
async def home():
    return {
        "status": "ok",
        "message": "Servidor activo"
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy"
    }


@app.post("/test")
async def test_endpoint(datos: Request):
    raw_bytes = await datos.body()
    raw_texto = raw_bytes.decode("utf-8", errors="replace")

    print("========== TEST ENDPOINT ==========")
    print("BODY RECIBIDO:", repr(raw_texto))
    print("===================================")

    return {
        "ok": True,
        "body": raw_texto
    }


def normalizar_texto_usuario(texto):
    """
    Limpia mensajes recibidos desde ManyChat o WhatsApp.
    Convierte saltos de linea, saltos escapados, etiquetas HTML y espacios multiples.
    """
    if texto is None:
        return ""

    texto = str(texto)

    texto = html.unescape(texto)

    texto = re.sub(r"<br\s*/?>", " ", texto, flags=re.IGNORECASE)

    texto = texto.replace("\\r\\n", " ")
    texto = texto.replace("\\n", " ")
    texto = texto.replace("\\r", " ")

    texto = texto.replace("\r\n", " ")
    texto = texto.replace("\n", " ")
    texto = texto.replace("\r", " ")

    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


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
        google_credentials_raw = os.getenv("GOOGLE_CREDENTIALS")
        spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")

        if not google_credentials_raw:
            print("ERROR: No existe la variable GOOGLE_CREDENTIALS")
            return False

        if not spreadsheet_id:
            print("ERROR: No existe la variable GOOGLE_SHEET_ID")
            return False

        credenciales_dict = json.loads(google_credentials_raw)

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]

        creds = service_account.Credentials.from_service_account_info(
            credenciales_dict,
            scopes=scopes
        )

        service = build("sheets", "v4", credentials=creds)

        range_name = "Hoja 1!A:G"

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

        body = {
            "values": [row_data]
        }

        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()

        print("Prospecto guardado en Google Sheets")
        print("Nombre:", nombre)
        print("Telefono:", telefono)
        print("Tratamiento:", tratamiento)
        print("Fecha nacimiento o cumpleanos:", fecha_nacimiento)

        return True

    except Exception as e:
        print("Error al guardar en Google Sheets:", e)
        return False


@app.post("/webhook")
async def recibir_mensaje(datos: Request):
    raw_bytes = await datos.body()
    raw_texto = raw_bytes.decode("utf-8", errors="replace")

    try:
        cuerpo = json.loads(raw_texto, strict=False)

    except Exception as e:
        print("ERROR AL PARSEAR JSON")
        print("Error:", e)
        print("BODY CRUDO RECIBIDO:", repr(raw_texto))

        return {
            "respuesta_servidor": "Permíteme revisar esa información con nuestro equipo para darte una respuesta correcta."
        }

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

  # 1. Validación de mensajes vacíos o de sistema
    if not texto_usuario or texto_usuario == "Última entrada de texto":
        return {
            "respuesta_servidor": "¡Hola! 👋 Por el momento soy un asistente de texto y no puedo ver archivos. ¿Podrías escribirme tu duda o decirme en qué tratamiento estás interesada?"
        }

    palabras_multimedia = ["image", "imagen", "photo", "foto", "attachment", "video", "sticker"]
    if texto_usuario.lower() in palabras_multimedia:
        return {
            "respuesta_servidor": "¡Hola! 📸 Veo que me enviaste un archivo multimedia, pero por ahora solo puedo leer texto. ¿Me podrías escribir tu pregunta o describir lo que buscas, por favor? ✨"
        }

    palabras_reinicio = [
        "Hola"
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

    if len(memoria_charlas[identificador]) > 16:
        memoria_charlas[identificador] = memoria_charlas[identificador][-16:]

    print(
        "--- Memoria actual del usuario "
        + identificador
        + " Mensajes: "
        + str(len(memoria_charlas[identificador]))
        + " ---"
    )

    print(memoria_charlas[identificador])

   try:
        # Forzamos un límite de 12 segundos para que ManyChat no cierre la conexión
        respuesta_ia = await asyncio.wait_for(
            generar_respuesta_ia(
                memoria_charlas[identificador],
                herramientas_openai,
                guardar_prospecto_en_sheets
            ),
            timeout=12.0
        )
    except asyncio.TimeoutError:
        print("ERROR: Timeout en OpenAI (Tomó más de 12 segundos)")
        respuesta_ia = "¡Una disculpa! 😅 Mi sistema está recibiendo muchos mensajes y tardó un poco. ¿Me podrías repetir tu pregunta, por favor?"
        # Borramos el intento fallido de la memoria para no arrastrar el error
        if memoria_charlas[identificador]:
            memoria_charlas[identificador].pop()
    except Exception as e:
        print("ERROR INESPERADO AL LLAMAR A LA IA:", e)
        respuesta_ia = "Ups, tuve un pequeño inconveniente técnico. 🛠️ ¿Podrías intentar escribirme de nuevo en un momento?"
        if memoria_charlas[identificador]:
            memoria_charlas[identificador].pop()

    memoria_charlas[identificador].append({
        "role": "assistant",
        "content": respuesta_ia
    })

    print("========== IA RESPONDE ==========")
    print(respuesta_ia)
    print("=================================")

    return {
        "respuesta_servidor": respuesta_ia
    }
