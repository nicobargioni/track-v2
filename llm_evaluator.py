import os
import json
import requests
import logging
from utils import send_slack
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')

# --------------------------------------------------------------------
# Prompt base con reglas, ejemplos y contra-ejemplos
# --------------------------------------------------------------------
BASE_SYSTEM_MSG = """
Sos un analista que detecta compromisos de trabajo en mensajes de Slack
y respondes SOLO con JSON válido (sin texto adicional, sin markdown).
Esto busca amplificar el pensamiento estratégico de los Product Managers
y ayudar a identificar tareas y responsables de manera precisa.

Esquema de salida:
{
  "es_compromiso": bool,          # true si hay compromiso
  "asignado_a": string | null,    # @usuario, “equipo”, o null
  "descripcion": string | null,   # síntesis de la tarea
  "fecha_limite": string | null   # ISO 8601 YYYY-MM-DD o null
}

Reglas:
• Un compromiso es cualquier mensaje que:
  1) asigne o proponga una acción futura relacionada con trabajo, o
  2) pida explícitamente la ejecución de una tarea,
  3) o solicite una revisión o seguimiento de algo pendiente, o
  4) signifique una coordinación de trabajo futura, o
  5) implique clarificar cualquier tipo de consulta de parte de un miembro del equipo o cliente
• Si el mensaje solo es social (café, saludos, emojis) → no hay compromiso.
• Si falta un responsable claro, usa null en "asignado_a".
• Si se menciona “mañana / viernes / 15-08”, intenta convertir a ISO; si no es inequívoco → null.
• No incluyas campos adicionales ni repitas el mensaje original.

En contexto de retencion de cuentas, escala de vínculos con cliente y fidelización, pueden existir mensajes sociales
que es importante que marques como compromiso, ya que son parte de la estrategia de engagement y retención.

Ejemplos de mensajes sociales:

"Si les parece, podemos reunirnos tal día"
"Voy a estar tal día en tal lugar, podríamos vernos"

---
Ejemplo POSITIVO #1
Mensaje:

@nicobargioni revisá las etiquetas SEO y armá el informe antes del 2025-08-05

Respuesta:
{"es_compromiso": true,
 "asignado_a": "@nicobargioni",
 "descripcion": "revisar etiquetas SEO y armar informe",
 "fecha_limite": "2025-08-05"}

Ejemplo POSITIVO #2
Mensaje:

Equipo, ¿vemos esto mañana?

Respuesta:
{"es_compromiso": true,
 "asignado_a": "equipo",
 "descripcion": "revisar pedido por canal",
 "fecha_limite": null}

Ejemplo POSITIVO #3
Mensaje:
"Tenemos dudas respecto a..."

Respuesta:
{"es_compromiso": true,
 "asignado_a": "equipo",
 "descripcion": "revisar pedido por canal",
 "fecha_limite": null}

Ejemplo POSITIVO #1
Mensaje:

¿Nos tomamos un café mañana para ponernos al día? ☕

Respuesta:
{"es_compromiso": true}

Ejemplo NEGATIVO #2
Mensaje:

¡Buen día! ¿Cómo están todos? 🙂

Respuesta:
{"es_compromiso": false}
---
"""

def build_prompt(message_text: str) -> list[dict]:
    """Crea la lista de mensajes para la llamada a la API."""
    return [
        {"role": "system", "content": BASE_SYSTEM_MSG},
        {"role": "user",   "content": f"Mensaje a evaluar:\n```{message_text}```"}
    ]

# --------------------------------------------------------------------
# Función principal
# --------------------------------------------------------------------
def evaluate_commitment(message_text: str):
    messages = build_prompt(message_text)

    if OPENAI_API_KEY:
        return evaluate_with_openai(messages)
    else:
        raise Exception("No LLM API key configured")

# --------------------------------------------------------------------
# OpenAI
# --------------------------------------------------------------------
def evaluate_with_openai(messages: list[dict]):
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "gpt-3.5-turbo",      # o el modelo que prefieras
        "messages": messages,
        "temperature": 0
    }

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=data
    )

    if response.status_code == 200:
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        return _extract_json(content)
    else:
        logging.error(f"Error calling OpenAI API: {response.status_code} - {response.text}")
        send_slack(f"Error calling OpenAI API: {response.status_code} - {response.text}")
        return None


# --------------------------------------------------------------------
# Utilidad para extraer JSON
# --------------------------------------------------------------------
def _extract_json(text: str):
    """Devuelve un dict si encuentra JSON válido en el texto; de lo contrario None."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start != -1 and json_end != 0:
            try:
                return json.loads(text[json_start:json_end])
            except json.JSONDecodeError:
                pass
    return None
