from fastapi import FastAPI, Request
import json
# (Aquí van tus otras importaciones, como os, tu agente de OpenAI, Google, etc...)

# 1. ESTA ES LA LÍNEA CRÍTICA QUE FALTA O SE BORRÓ
app = FastAPI()

# 2. Inicializamos el diccionario de memoria si lo tienes aquí
memoria_charlas = {}

# 3. AHORA SÍ, viene tu código modificado
@app.post("/webhook")
async def recibir_mensaje(datos: Request):
    raw_bytes = await datos.body()
    raw_texto = raw_bytes.decode("utf-8", errors="replace")

    # Reparamos saltos de línea crudos dentro del JSON (Manychat no los escapa)
    texto_saneado = raw_texto.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    
    # ... (el resto de tu código sigue normal hacia abajo)

    try:
        cuerpo = json.loads(texto_saneado)
    except Exception as e:
        print(f"❌ ERROR AL PARSEAR JSON incluso después de sanear: {e}")
        print(f"📄 BODY CRUDO RECIBIDO: {raw_texto}")
        return {"respuesta_servidor": "Permíteme revisar esa información con nuestro equipo para darte una respuesta correcta."}

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

    respuesta_ia = await generar_respuesta_ia(memoria_charlas[identificador], herramientas_openai, guardar_en_sheets)

    memoria_charlas[identificador].append({"role": "assistant", "content": respuesta_ia})

    print("=== IA RESPONDE ===", respuesta_ia)

    return {"respuesta_servidor": respuesta_ia}