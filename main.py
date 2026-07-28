from fastapi import FastAPI, Request
from servicios.openai_agent import generar_respuesta_ia
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime

# Definimos las herramientas de OpenAI fuera de las funciones
herramientas_openai = [
    {
        "type": "function",
        "function": {
            "name": "registrar_paciente",
            "description": "Guarda los datos del paciente cuando acepta agendar una valoración y proporciona su información.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre_completo": {
                        "type": "string",
                        "description": "El nombre completo del paciente"
                    },
                    "telefono": {
                        "type": "string",
                        "description": "El número de teléfono o WhatsApp del paciente"
                    },
                    "tratamiento_interes": {
                        "type": "string",
                        "description": "El tratamiento o servicio por el cual preguntó el paciente"
                    },
                    "fecha_cumpleanos": {
                        "type": "string",
                        "description": "La fecha de cumpleaños del paciente en formato DD/MM/AAAA"
                    }
                },
                "required": ["nombre_completo", "telefono", "tratamiento_interes", "fecha_cumpleanos"]
            }
        }
    }
]

def guardar_en_sheets(nombre, telefono, tratamiento, cumpleanos):
    # Configuración de credenciales
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    creds = service_account.Credentials.from_service_account_file('credenciales.json', scopes=SCOPES)
    # Conexión a la API
    service = build('sheets', 'v4', credentials=creds)
    
    # ID CORREGIDO: Solo el código alfanumérico
    SPREADSHEET_ID = '1U4Sr0Bgm4-dGhYzpEQeM_3LVvE6ceA_kPW0BSFsnIp8' 
    RANGE_NAME = 'Hoja 1!A:F' 
    
    # Obtener fecha actual
    fecha_registro = datetime.now().strftime("%d/%m/%Y")
    
    # Preparar la fila
    valores = [
        [fecha_registro, nombre, telefono, tratamiento, cumpleanos, "Prospecto"]
    ]
    
    body = {'values': valores}
    
    try:
        result = service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME,
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        return True
    except Exception as e:
        print(f"Error al guardar en Sheets: {e}")
        return False

# Inicializamos FastAPI
app = FastAPI()

# MEMORIA EN VIVO
memoria_charlas = {}

@app.post("/webhook")
async def recibir_mensaje(datos: Request):
    cuerpo = await datos.json()
    
    texto_usuario = str(cuerpo.get("texto", "")).strip()
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

    # Aquí le enviaremos también las herramientas a tu agente
    respuesta_ia = await generar_respuesta_ia(memoria_charlas[identificador], herramientas_openai, guardar_en_sheets)

    memoria_charlas[identificador].append({"role": "assistant", "content": respuesta_ia})

    print("=== IA RESPONDE ===", respuesta_ia)

    return {"respuesta_servidor": respuesta_ia}