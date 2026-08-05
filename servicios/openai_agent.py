# =====================================================================
# 1. IMPORTACIÓN DE LIBRERÍAS Y MÓDULOS NECESARIOS
# =====================================================================
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =====================================================================
# 2. FUNCIÓN PARA LEER ARCHIVOS EXTERNOS
# =====================================================================
def leer_archivo(ruta):
    """Abre un archivo de texto y devuelve su contenido."""
    try:
        # Usamos encoding='utf-8' para que lea perfectamente los acentos y emojis
        with open(ruta, 'r', encoding='utf-8') as archivo:
            return archivo.read()
    except FileNotFoundError:
        print(f"⚠️ Advertencia: No se encontró el archivo {ruta}")
        return ""

# =====================================================================
# 3. FUNCIÓN PRINCIPAL DE LA IA
# =====================================================================
async def generar_respuesta_ia(historial_mensajes, herramientas=None, funcion_guardar=None):
    try:
        # Cargamos los textos desde los archivos .md
        # Ajusta la ruta si guardaste los archivos dentro de alguna carpeta
        instrucciones = leer_archivo("prompt_sistema.md")
        knowledge_base = leer_archivo("base_conocimientos.md")

        # Se recalcula en cada mensaje (no al arrancar el servidor) y ya usa la hora de Puebla/CDMX
        fecha_hoy = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%d/%m/%Y")
        contexto_tiempo = f"""
        \n\n=== CONTEXTO TEMPORAL ===
        - La fecha de hoy es: {fecha_hoy}.
        - Si el usuario menciona fechas relativas como 'mañana' o 'la próxima semana', interpreta correctamente la fecha real para responder con precisión.
        """

        # Unimos todo en un solo bloque de texto para el sistema
        system_content = f"{instrucciones}\n\n=== BASE DE CONOCIMIENTOS ===\n{knowledge_base}\n{contexto_tiempo}"
        
        mensajes_para_enviar = [{"role": "system", "content": system_content}] + historial_mensajes

        print("=== EVALUANDO MENSAJE EN OPENAI ===")

        parametros_peticion = {
    "model": "gpt-4o-mini",
    "messages": mensajes_para_enviar,
    "temperature": 0.1,
    "max_tokens": 150,
    "top_p": 0.9
}

        if herramientas:
            parametros_peticion["tools"] = herramientas
            parametros_peticion["tool_choice"] = "auto"

        respuesta = await client.chat.completions.create(**parametros_peticion)
        mensaje_ia = respuesta.choices[0].message

        # =====================================================================
        # 4. INTERCEPCIÓN DE FUNCTION CALLING (GUARDADO DE DATOS)
        # =====================================================================
        if mensaje_ia.tool_calls:
            for tool_call in mensaje_ia.tool_calls:
                if tool_call.function.name == "registrar_paciente" and funcion_guardar:
                    
                    argumentos = json.loads(tool_call.function.arguments)
                    
                    nombre = argumentos.get("nombre_completo", "No especificado")
                    telefono = argumentos.get("telefono", "No especificado")
                    tratamiento = argumentos.get("tratamiento_interes", "No especificado")
                    cumpleanos = argumentos.get("fecha_cumpleanos", "No especificado")
                    
                    print(f"✅ OpenAI extrajo: {nombre} | {telefono} | {tratamiento} | {cumpleanos}")
                    
                    guardado_exitoso = funcion_guardar(nombre, telefono, tratamiento, cumpleanos)
                    
                    if guardado_exitoso:
                        return "¡Perfecto, muchas gracias! 💖 En un momento nuestro equipo te escribirá por WhatsApp para compartirte los horarios disponibles y ayudarte a confirmar tu cita. ¡Estamos muy emocionados de recibirte!"
                    else:
                        print("❌ Error al procesar el guardado en Sheets.")
                        return "Tuvimos un pequeño inconveniente al registrar tus datos, pero nuestro equipo ya tiene tu información y te contactará en breve. ¡Gracias!"
        
        return mensaje_ia.content

    except Exception as error:
        print(f"Error en OpenAI: {str(error)}")
        return "Permíteme revisar esa información con nuestro equipo para darte una respuesta correcta."

    # =====================================================================
# 5. DEFINICIÓN DE HERRAMIENTAS (FUNCTION CALLING)
# =====================================================================
herramientas_openai = [
    {
        "type": "function",
        "function": {
            "name": "registrar_paciente",
            "description": "Extrae los datos de un paciente cuando proporciona su información para agendar una cita.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre_completo": {
                        "type": "string",
                        "description": "El nombre completo del paciente."
                    },
                    "telefono": {
                        "type": "string",
                        "description": "El número de teléfono o WhatsApp."
                    },
                    "tratamiento_interes": {
                        "type": "string",
                        "description": "El tratamiento por el que está interesado."
                    },
                    "fecha_cumpleanos": {
                        "type": "string",
                        "description": "La fecha de cumpleaños o nacimiento."
                    }
                },
                "required": ["nombre_completo", "telefono"]
            }
        }
    }
]
