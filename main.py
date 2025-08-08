import os
import json
import hashlib
import hmac
import time
import threading
import logging
import requests
import traceback
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from llm_evaluator import evaluate_commitment
from slack_helpers import post_thread_message, get_user_info, add_reaction, remove_reaction, post_ephemeral_message, get_channel_info
from asana_client import create_asana_task, delete_asana_task
from channel_map import get_asana_project_id
# import google.cloud.logging
from utils import send_slack

# Inicializa el cliente de Cloud Logging - Temporalmente deshabilitado
# logging_client = google.cloud.logging.Client(project='gothic-calling-325317')
# logging_client.setup_logging()

# Configurar logging detallado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('slack_bot.log')
    ]
)


load_dotenv()

app = Flask(__name__)

SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
SLACK_SIGNING_SECRET = os.getenv('SLACK_SIGNING_SECRET')

logging.info(f"=== STARTING SLACK-ASANA INTEGRATION ===")
logging.info(f"SLACK_BOT_TOKEN configured: {'Yes' if SLACK_BOT_TOKEN else 'No'}")
logging.info(f"SLACK_SIGNING_SECRET configured: {'Yes' if SLACK_SIGNING_SECRET else 'No'}")
logging.info(f"Bot token starts with: {SLACK_BOT_TOKEN[:10]}..." if SLACK_BOT_TOKEN else "No bot token")
logging.info(f"="*40)

# Cache para evitar procesar eventos duplicados
processed_events = set()

# Mapeo de tareas creadas (message_ts -> asana_task_gid)
task_mapping = {}
task_mapping_file = 'task_mapping.json'

# Cargar mapeo de tareas existente
try:
    with open(task_mapping_file, 'r') as f:
        task_mapping = json.load(f)
except:
    task_mapping = {}

# Cargar mapeo de usuarios
with open('merged_accounts.json', 'r') as f:
    user_mapping = json.load(f)

def save_task_mapping():
    with open(task_mapping_file, 'w') as f:
        json.dump(task_mapping, f, indent=2)

def get_slack_user_from_asana_gid(asana_gid):
    for email, data in user_mapping.items():
        if asana_gid in data.get('asana_ids', []):
            slack_ids = data.get('slack_ids', [])
            return slack_ids[0] if slack_ids else None
    return None

def get_asana_gid_from_slack_user(slack_user_id):
    for email, data in user_mapping.items():
        if slack_user_id in data.get('slack_ids', []):
            asana_ids = data.get('asana_ids', [])
            return asana_ids[0] if asana_ids else None
    return None

@app.route('/')
def home():
    logging.info("🏠 Home endpoint accessed")
    return 'Slack-Asana Integration Service is running!'

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy', 
        'service': 'slack-asana-integration',
        'bot_token_configured': bool(SLACK_BOT_TOKEN),
        'signing_secret_configured': bool(SLACK_SIGNING_SECRET)
    })

@app.route('/test', methods=['GET', 'POST'])
def test():
    print(f"TEST endpoint hit - Method: {request.method}")
    print(f"Headers: {dict(request.headers)}")
    if request.method == 'POST':
        print(f"Body: {request.get_data(as_text=True)}")
    return jsonify({'message': 'Test successful', 'method': request.method})

def verify_slack_signature(request_body, timestamp, signature):
    req = str.encode(f"v0:{timestamp}:{request_body}")
    request_hash = 'v0=' + hmac.new(
        str.encode(SLACK_SIGNING_SECRET),
        req,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(request_hash, signature)

def process_asana_task_creation(event, commitment_data):
    """Procesa la creación automática de tarea en Asana"""
    try:
        logging.info("🏗️ === STARTING ASANA TASK CREATION ===")
        channel = event['channel']
        message_ts = event['ts']
        user_who_posted = event['user']
        
        logging.info(f"📍 Channel: {channel}")
        logging.info(f"⏰ Message timestamp: {message_ts}")
        logging.info(f"👤 User who posted: {user_who_posted}")
        logging.info(f"📊 Commitment data: {commitment_data}")
        
        # Obtener información del usuario que creó la tarea
        creator_info = get_user_info(user_who_posted)
        creator_name = creator_info.get('real_name') or creator_info.get('display_name') or creator_info.get('name') or f"<@{user_who_posted}>"
        
        # Obtener información del canal
        channel_info = get_channel_info(channel)
        channel_name = channel_info.get('name', channel)
        
        # Obtener proyecto de Asana del canal
        asana_project_id = get_asana_project_id(channel)
        logging.info(f"🎯 Asana project ID for channel: {asana_project_id}")
        if not asana_project_id:
            logging.info(f"❌ No hay proyecto de Asana configurado para el canal {channel}")
            return
        
        # Extraer usuario mencionado del texto
        mentioned_user_id = None
        text = event['text']
        logging.info(f"📝 Message text: {text}")
        # Buscar menciones en formato <@USERID>
        import re
        mentions = re.findall(r'<@(U[A-Z0-9]+)>', text)
        logging.info(f"👥 Found mentions: {mentions}")
        if mentions:
            mentioned_user_id = mentions[0]
        
        # Verificar si hay asignación o si es un compromiso sin asignación
        sin_asignacion = commitment_data.get('sin_asignacion', False)
        asana_gid = None
        user_email = None
        
        if mentioned_user_id:
            # Obtener Asana GID del usuario mencionado
            asana_gid = get_asana_gid_from_slack_user(mentioned_user_id)
            if not asana_gid:
                logging.info(f"No se encontró mapeo de Asana para el usuario de Slack {mentioned_user_id}")
            
            # Obtener info del usuario para el email
            user_info = get_user_info(mentioned_user_id)
            user_email = user_info.get('profile', {}).get('email')
        else:
            logging.info("No se encontró usuario mencionado en el mensaje")
            if not sin_asignacion:
                # Si no hay mención y no está marcado como sin asignación, salir
                return
            
            # Si no hay mención, asignar la tarea al usuario que la creó
            logging.info("Asignando tarea al usuario que la creó")
            creator_email = creator_info.get('profile', {}).get('email')
            asana_gid = get_asana_gid_from_slack_user(user_who_posted)
            user_email = creator_email
        
        # Crear tarea (con o sin asignación)
        task_result = create_asana_task(
            name=commitment_data['descripcion'],
            assignee_email=user_email,
            assignee_gid=asana_gid,
            project_id=asana_project_id,
            due_on=commitment_data.get('fecha_limite'),
            description=f"Tarea creada desde Slack por: {creator_name}\n\nMensaje original: {text}\n\nCanal: #{channel_name}\n\nLink al mensaje: https://nomadicseo.slack.com/archives/{channel}/p{message_ts.replace('.','')}"
        )
        
        # Guardar mapeo de tarea con timestamp de creación
        task_key = f"{channel}:{message_ts}"
        creation_time = time.time()
        task_mapping[task_key] = {
            'asana_gid': task_result['gid'],
            'channel': channel,
            'message_ts': message_ts,
            'user_who_posted': user_who_posted,
            'assigned_to': mentioned_user_id,
            'project_id': asana_project_id,
            'created_at': creation_time,
            'can_be_cancelled': True,
            'task_name': commitment_data['descripcion'],  # Guardar nombre de la tarea
            'thread_ts': event.get('thread_ts')  # Guardar thread_ts para mensajes ephemeral
        }
        save_task_mapping()
        
        logging.info(f"💾 Task saved with cancellation window until: {time.ctime(creation_time + 300)}")
        
        # Programar desactivación de cancelación después de 5 minutos
        def disable_cancellation():
            time.sleep(300)  # 5 minutos
            if task_key in task_mapping:
                task_mapping[task_key]['can_be_cancelled'] = False
                save_task_mapping()
                logging.info(f"⏰ Cancellation window expired for task: {task_key}")
        
        cancellation_thread = threading.Thread(target=disable_cancellation)
        cancellation_thread.daemon = True
        cancellation_thread.start()
        
        # Agregar reacción 💡
        add_reaction(channel, message_ts, 'bulb')
        
        # Enviar mensaje efímero solo al usuario que creó la tarea
        project_name = None
        # Buscar nombre del proyecto en asana_pj.json
        try:
            with open('asana_pj.json', 'r', encoding='utf-8') as f:
                asana_projects = json.load(f)
                for name, pid in asana_projects.items():
                    if pid == asana_project_id:
                        project_name = name
                        break
        except:
            pass
        
        # Mensaje ephemeral simplificado: solo emoji + link
        task_url = task_result.get('url', f"https://app.asana.com/0/{asana_project_id}/{task_result['gid']}")
        message = f"✅ <{task_url}|Ver tarea en Asana>"
        
        logging.info(f"📨 Sending ephemeral message to user {user_who_posted} in channel {channel}")
        logging.info(f"📝 Message content: {message}")
        ephemeral_result = post_ephemeral_message(
            channel=channel,
            user=user_who_posted,
            text=message,
            thread_ts=event.get('thread_ts')
        )
        logging.info(f"📨 Ephemeral message result: {ephemeral_result}")
        
    except Exception as e:
        logging.error(f"Error creando tarea automática: {str(e)}")
        logging.exception("Exception details:")
        send_slack(f"Error creando tarea automática: {str(e)}")

def handle_task_deletion(task_info, channel, message_ts):
    """Maneja la eliminación de una tarea cuando el creador reacciona con 🚫"""
    try:
        logging.info(f"🗑️ === STARTING TASK DELETION ===")
        logging.info(f"📍 Channel: {channel}")
        logging.info(f"⏰ Message timestamp: {message_ts}")
        logging.info(f"🎯 Asana task GID: {task_info['asana_gid']}")
        logging.info(f"👤 User who posted: {task_info['user_who_posted']}")
        
        # Eliminar tarea de Asana
        logging.info(f"🔥 Deleting task from Asana...")
        delete_asana_task(task_info['asana_gid'])
        logging.info(f"✅ Task deleted from Asana successfully")
        
        # Quitar reacción 💡
        logging.info(f"💡 Removing bulb reaction...")
        remove_reaction(channel, message_ts, 'bulb')
        
        # Quitar reacción 🚫 también
        logging.info(f"🚫 Removing no_entry_sign reaction...")
        remove_reaction(channel, message_ts, 'no_entry_sign')
        
        # Eliminar del mapeo
        task_key = f"{channel}:{message_ts}"
        if task_key in task_mapping:
            logging.info(f"🗂️ Removing task from mapping...")
            del task_mapping[task_key]
            save_task_mapping()
            logging.info(f"✅ Task removed from mapping")
        
        # Calcular tiempo de cancelación
        current_time = time.time()
        creation_time = task_info.get('created_at', current_time)
        time_elapsed = current_time - creation_time
        
        # Notificar al usuario que creó la tarea
        post_ephemeral_message(
            channel=channel,
            user=task_info['user_who_posted'],
            text="🗑️",
            thread_ts=task_info.get('thread_ts')
        )
        
        logging.info(f"✅ Task deletion completed successfully in {time_elapsed:.1f} seconds")
        
    except Exception as e:
        logging.error(f"❌ Error eliminando tarea: {str(e)}")
        logging.exception("Exception details:")
        send_slack(f"Error eliminando tarea: {str(e)}")

@app.route('/slack/events', methods=['POST'])
def slack_events():
    logging.info("🔥 === SLACK EVENTS ENDPOINT HIT ===")
    logging.info(f"📋 Method: {request.method}")
    logging.info(f"📍 Remote Address: {request.remote_addr}")
    logging.info(f"📑 Headers: {dict(request.headers)}")
    logging.info(f"📄 Content-Type: {request.content_type}")
    
    if request.content_type != 'application/json':
        logging.error(f"❌ ERROR: Invalid content type: {request.content_type}")
        send_slack(f"ERROR: Invalid content type: {request.content_type}")
        return jsonify({'error': 'Content-Type must be application/json'}), 400
    
    timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
    signature = request.headers.get('X-Slack-Signature', '')
    logging.info(f"⏰ Timestamp: {timestamp}")
    logging.info(f"🔐 Signature: {signature[:20]}..." if signature else "No signature")
    
    if abs(time.time() - float(timestamp)) > 60 * 5:
        logging.error("❌ ERROR: Request timestamp too old")
        send_slack("ERROR: Request timestamp too old")
        return jsonify({'error': 'Request timestamp too old'}), 400
    
    # Obtener el body raw para verificación
    request_body = request.get_data(as_text=True)
    logging.info(f"📦 Raw Body: {request_body[:500]}{'...' if len(request_body) > 500 else ''}")
    
    if not verify_slack_signature(request_body, timestamp, signature):
        logging.error("❌ ERROR: Invalid signature")
        send_slack("ERROR: Invalid signature")
        return jsonify({'error': 'Invalid signature'}), 403
    
    logging.info("✅ Signature verification passed!")
    
    # Parsear el JSON después de verificar la firma
    try:
        data = json.loads(request_body)
        logging.info(f"📊 Parsed JSON data: {json.dumps(data, indent=2)}")
    except json.JSONDecodeError as e:
        logging.error(f"❌ ERROR: Invalid JSON - {str(e)}")
        send_slack("ERROR: Invalid JSON")
        return jsonify({'error': 'Invalid JSON'}), 400
    
    # URL verification challenge de Slack
    if data.get('type') == 'url_verification':
        challenge = data['challenge']
        logging.info(f"🔐 URL Verification challenge: {challenge}")
        return jsonify({'challenge': challenge})
    
    if 'event' in data:
        event = data['event']
        event_id = data.get('event_id')
        logging.info(f"🎯 Processing event ID: {event_id}")
        logging.info(f"📋 Event type: {event.get('type')}")
        logging.info(f"📝 Event data: {json.dumps(event, indent=2)}")
        
        # Evitar procesar eventos duplicados
        if event_id in processed_events:
            logging.info(f"⏭️ Event {event_id} already processed, skipping")
            return jsonify({'status': 'ok'})
        
        processed_events.add(event_id)
        
        # Limpiar cache después de 1000 eventos
        if len(processed_events) > 1000:
            processed_events.clear()
            logging.info("🧹 Cleaned processed events cache")
        
        if (event.get('type') == 'message' and 
            not event.get('bot_id') and 
            event.get('text')):
            
            text = event['text']
            logging.info(f"💬 Processing message: {text}")
            logging.info(f"📍 Channel: {event.get('channel')}")
            logging.info(f"👤 User: {event.get('user')}")
            
            # Siempre evaluar el mensaje, tenga o no menciones
            logging.info("🔍 Evaluating message for commitment...")
            commitment_data = evaluate_commitment(text)
            logging.info(f"🤖 LLM evaluation result: {commitment_data}")
            logging.info(f"🤖 Type of result: {type(commitment_data)}")
            
            if commitment_data and commitment_data.get('es_compromiso'):
                logging.info("✅ Message identified as commitment")
                
                # Verificar si hay menciones en el texto para determinar si hay asignación
                has_mention = '@' in text
                if not has_mention:
                    logging.info("⚠️ Commitment detected but no user mentioned")
                    # Marcar que no hay asignación clara
                    commitment_data['sin_asignacion'] = True
                
                # Crear tarea automáticamente
                thread = threading.Thread(target=process_asana_task_creation, args=(event, commitment_data))
                thread.daemon = True
                thread.start()
            else:
                logging.info("❌ Message not identified as commitment")
        
        elif event.get('type') == 'reaction_added':
            logging.info(f"😀 Reaction added: {event['reaction']}")
            # Manejar reacción de prohibido (🚫)
            if event['reaction'] == 'no_entry_sign':
                logging.info("🚫 Delete reaction detected, processing...")
                item = event['item']
                if item['type'] == 'message':
                    task_key = f"{item['channel']}:{item['ts']}"
                    task_info = task_mapping.get(task_key)
                    logging.info(f"🔍 Looking for task: {task_key}, found: {bool(task_info)}")
                    
                    if task_info and event['user'] == task_info['user_who_posted']:
                        # Verificar si la tarea aún puede ser cancelada
                        current_time = time.time()
                        creation_time = task_info.get('created_at', 0)
                        can_be_cancelled = task_info.get('can_be_cancelled', False)
                        time_elapsed = current_time - creation_time
                        
                        logging.info(f"⏰ Time elapsed since creation: {time_elapsed:.1f} seconds")
                        logging.info(f"🔒 Can be cancelled: {can_be_cancelled}")
                        
                        if can_be_cancelled and time_elapsed <= 300:  # 5 minutos = 300 segundos
                            logging.info("✅ Within 5-minute cancellation window, deleting task...")
                            # Eliminar tarea de Asana
                            thread = threading.Thread(target=handle_task_deletion, args=(task_info, item['channel'], item['ts']))
                            thread.daemon = True
                            thread.start()
                        else:
                            logging.info("❌ Cancellation window expired (5 minutes passed)")
                            # Enviar mensaje efímero informando que ya no se puede cancelar
                            post_ephemeral_message(
                                channel=item['channel'],
                                user=event['user'],
                                text="⏰ Ya no puedes cancelar esta tarea. Han pasado más de 5 minutos desde su creación.",
                                thread_ts=task_info.get('thread_ts')
                            )
                            # Remover la reacción ya que no es válida
                            remove_reaction(item['channel'], item['ts'], 'no_entry_sign')
                    else:
                        logging.info("⛔ Unauthorized user or task not found")
                        if task_info and event['user'] != task_info['user_who_posted']:
                            # Informar al usuario que no puede cancelar tareas de otros
                            post_ephemeral_message(
                                channel=item['channel'],
                                user=event['user'],
                                text="❌ Solo el creador de la tarea puede cancelarla.",
                                thread_ts=task_info.get('thread_ts')
                            )
                            # Remover la reacción ya que no es válida
                            remove_reaction(item['channel'], item['ts'], 'no_entry_sign')
        else:
            logging.info(f"⏭️ Unhandled event type: {event.get('type')}")
    else:
        logging.info("📭 No event data in request")
    
    logging.info("✅ Request processed successfully")
    return jsonify({'status': 'ok'})

@app.route('/asana/webhook', methods=['POST'])
def asana_webhook():
    """Webhook para recibir eventos de Asana"""
    logging.info("🎯 === ASANA WEBHOOK ENDPOINT HIT ===")
    logging.info(f"📑 Headers: {dict(request.headers)}")
    
    # Verificación del webhook (handshake)
    if 'X-Hook-Secret' in request.headers:
        secret = request.headers['X-Hook-Secret']
        logging.info(f"🤝 Handshake request with secret: {secret}")
        response = jsonify({'X-Hook-Secret': secret})
        response.headers['X-Hook-Secret'] = secret
        return response
    
    # Procesar eventos
    data = request.json
    logging.info(f"📦 Asana webhook data: {json.dumps(data, indent=2)}")
    events = data.get('events', [])
    logging.info(f"📊 Processing {len(events)} events")
    
    for event in events:
        logging.info(f"🔍 Processing event: action={event.get('action')}, resource_type={event.get('resource', {}).get('resource_type')}")
        
        if event.get('action') == 'changed' and event.get('resource', {}).get('resource_type') == 'task':
            # Verificar cambios en el campo
            change_field = event.get('change', {}).get('field', '')
            logging.info(f"📝 Changed field: {change_field}")
            
            # Verificar si la tarea fue completada
            if 'completed' in change_field:
                task_gid = event['resource']['gid']
                new_value = event.get('change', {}).get('new_value', {})
                
                logging.info(f"✅ Task completion status changed for GID: {task_gid}")
                logging.info(f"📊 New value: {new_value}")
                
                # Si la tarea fue marcada como completada (no des-completada)
                if new_value.get('resource_subtype') == 'completed':
                    logging.info(f"✓ Task {task_gid} was marked as completed")
                    
                    # Buscar la tarea en nuestro mapeo
                    task_found = False
                    for task_key, task_info in task_mapping.items():
                        if task_info['asana_gid'] == task_gid:
                            task_found = True
                            logging.info(f"📍 Found task in mapping: {task_key}")
                            logging.info(f"📺 Channel: {task_info['channel']}, Message TS: {task_info['message_ts']}")
                            
                            # Agregar reacción ✅ al mensaje original
                            # No importa quién completó la tarea
                            reaction_result = add_reaction(task_info['channel'], task_info['message_ts'], 'white_check_mark')
                            logging.info(f"🎯 Reaction result: {reaction_result}")
                            
                            # Opcional: Enviar notificación al creador de la tarea
                            user_who_completed = event.get('user', {}).get('gid')
                            if user_who_completed:
                                slack_user_completed = get_slack_user_from_asana_gid(user_who_completed)
                                if slack_user_completed:
                                    post_ephemeral_message(
                                        channel=task_info['channel'],
                                        user=task_info['user_who_posted'],
                                        text=f"✅ La tarea '{task_info.get('task_name', 'Sin nombre')}' fue completada por <@{slack_user_completed}> en Asana",
                                        thread_ts=task_info.get('thread_ts')
                                    )
                            break
                    
                    if not task_found:
                        logging.warning(f"⚠️ Task {task_gid} not found in mapping")
                else:
                    logging.info(f"↩️ Task {task_gid} was uncompleted or status changed to: {new_value.get('resource_subtype')}")
    
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)