import os
import json
import requests
import logging
from utils import send_slack
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')

def add_reaction(channel, timestamp, reaction):
    """Agrega una reacción a un mensaje"""
    headers = {
        'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    data = {
        'channel': channel,
        'timestamp': timestamp,
        'name': reaction
    }
    
    response = requests.post(
        'https://slack.com/api/reactions.add',
        headers=headers,
        json=data
    )
    
    if response.status_code != 200 or not response.json().get('ok'):
        logging.error(f"Error adding reaction: {response.json()}")
    
    return response.json()

def remove_reaction(channel, timestamp, reaction):
    """Quita una reacción de un mensaje"""
    headers = {
        'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    data = {
        'channel': channel,
        'timestamp': timestamp,
        'name': reaction
    }
    
    response = requests.post(
        'https://slack.com/api/reactions.remove',
        headers=headers,
        json=data
    )
    
    if response.status_code != 200 or not response.json().get('ok'):
        logging.error(f"Error removing reaction: {response.json()}")
    
    return response.json()

def post_ephemeral_message(channel, user, text):
    """Envía un mensaje efímero que solo el usuario especificado puede ver"""
    headers = {
        'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    data = {
        'channel': channel,
        'user': user,
        'text': text
    }
    
    response = requests.post(
        'https://slack.com/api/chat.postEphemeral',
        headers=headers,
        json=data
    )
    
    if response.status_code != 200 or not response.json().get('ok'):
        logging.error(f"Error posting ephemeral message: {response.json()}")
    
    return response.json()

def post_message_with_button(channel, thread_ts, original_message, commitment_data, message_ts):
    headers = {
        'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    attachments = [
        {
            "text": "📝 Este mensaje parece un compromiso. ¿Querés crear una tarea en Asana?",
            "fallback": "No se puede mostrar el botón interactivo",
            "callback_id": "create_asana_task",
            "color": "warning",
            "attachment_type": "default",
            "actions": [
                {
                    "name": "create_asana_task",
                    "text": "✅ Crear tarea en Asana",
                    "type": "button",
                    "value": json.dumps({
                        "commitment_data": commitment_data,
                        "original_message": original_message,
                        "thread_ts": thread_ts,
                        "message_ts": message_ts
                    })
                }
            ]
        }
    ]
    
    data = {
        'channel': channel,
        'thread_ts': thread_ts,
        'attachments': attachments
    }
    
    response = requests.post(
        'https://slack.com/api/chat.postMessage',
        headers=headers,
        json=data
    )
    
    if response.status_code != 200 or not response.json().get('ok'):
        logging.error(f"Error posting message with button: {response.json()}")
        send_slack(f"Error posting message with button: {response.json()}")
    
    return response.json()

def post_thread_message(channel, thread_ts, text):
    headers = {
        'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    data = {
        'channel': channel,
        'thread_ts': thread_ts,
        'text': text
    }
    
    response = requests.post(
        'https://slack.com/api/chat.postMessage',
        headers=headers,
        json=data
    )
    
    if response.status_code != 200 or not response.json().get('ok'):
        logging.error(f"Error posting thread message: {response.json()}")
        send_slack(f"Error posting thread message: {response.json()}")
    
    return response.json()

def get_user_info(user_id):
    headers = {
        'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    params = {
        'user': user_id
    }
    
    response = requests.get(
        'https://slack.com/api/users.info',
        headers=headers,
        params=params
    )
    
    if response.status_code == 200 and response.json().get('ok'):
        return response.json().get('user', {})
    else:
        logging.error(f"Error getting user info: {response.json()}")
        send_slack(f"Error getting user info: {response.json()}")
        return {}

def open_task_dialog(trigger_id, commitment_data, original_message, channel, thread_ts):
    headers = {
        'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
        'Content-Type': 'application/json'
    }
    msg_url = f"https://nomadicseo.slack.com/archives/{channel}/p{thread_ts.replace('.','')}"
    # Cargar proyectos de Asana
    current_dir = os.path.dirname(os.path.abspath(__file__))
    asana_projects_path = os.path.join(current_dir, 'asana_pj.json')
    
    try:
        with open(asana_projects_path, 'r', encoding='utf-8') as f:
            asana_projects = json.load(f)
    except:
        asana_projects = {}
    
    # Crear opciones para el selector de proyectos
    full_project_options = [
    {
        "text": {
            "type": "plain_text",
            "text": project_name[:75]
        },
        "value": project_id
    }
    for project_name, project_id in sorted(asana_projects.items())
]

    project_options = full_project_options[:100]  # Slack permite como máximo 100 opciones
    
    # Obtener el proyecto por defecto basado en el canal
    from channel_map import get_asana_project_id
    try:
        default_project_id = get_asana_project_id(channel)
    except:
        default_project_id = None
    
    view = {
        "type": "modal",
        "callback_id": "create_asana_task_modal",
        "title": {
            "type": "plain_text",
            "text": "Crear tarea en Asana"
        },
        "submit": {
            "type": "plain_text",
            "text": "Crear tarea"
        },
        "close": {
            "type": "plain_text",
            "text": "Cancelar"
        },
        "private_metadata": json.dumps({
            "commitment_data": commitment_data,
            "original_message": original_message,
            "channel": channel,
            "thread_ts": thread_ts
        }),
        "blocks": [
            {
                "type": "input",
                "block_id": "project_block",
                "label": {
                    "type": "plain_text",
                    "text": "Proyecto de Asana"
                },
                "element": {
                    "type": "static_select",
                    "action_id": "project_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Seleccionar proyecto"
                    },
                    "options": project_options,
                    **({"initial_option": next((opt for opt in project_options if opt["value"] == default_project_id), None)} if default_project_id and any(opt["value"] == default_project_id for opt in project_options) else {})
                }
            },
            {
                "type": "input",
                "block_id": "title_block",
                "label": {
                    "type": "plain_text",
                    "text": "Título de la tarea"
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "title_input",
                    "initial_value": commitment_data['descripcion'],
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Ingresa el título"
                    }
                }
            },
            {
                "type": "input",
                "block_id": "description_block",
                "label": {
                    "type": "plain_text",
                    "text": "Descripción"
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "description_input",
                    "multiline": True,
                    "initial_value": f"Mensaje original: {original_message} en {msg_url}",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Agrega una descripción detallada"
                    }
                },
                "optional": True
            },
            {
                "type": "input",
                "block_id": "assignee_block",
                "label": {
                    "type": "plain_text",
                    "text": "Asignar a"
                },
                "element": {
                    "type": "users_select",
                    "action_id": "assignee_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Seleccionar usuario"
                    }
                }
            },
            {
                "type": "input",
                "block_id": "due_date_block",
                "label": {
                    "type": "plain_text",
                    "text": "Fecha límite"
                },
                "element": {
                    "type": "datepicker",
                    "action_id": "due_date_picker",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Seleccionar fecha"
                    }
                },
                "optional": True
            },
            {
                "type": "input",
                "block_id": "subtasks_block",
                "label": {
                    "type": "plain_text",
                    "text": "Subtareas"
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "subtasks_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Una subtarea por línea"
                    }
                },
                "optional": True,
                "hint": {
                    "type": "plain_text",
                    "text": "Separa cada subtarea con un salto de línea"
                }
            }
        ]
    }
    
    data = {
        "trigger_id": trigger_id,
        "view": view
    }
    
    logging.info(f"Opening modal with trigger_id: {trigger_id}")
    #logging.info("Modal data being sent: " + json.dumps(data, separators=(',', ':')))
    
    response = requests.post(
        'https://slack.com/api/views.open',
        headers=headers,
        json=data
    )
    
    logging.info(f"Response status code: {response.status_code}")
    logging.info(f"Response body: {response.json()}")
    
    if response.status_code != 200 or not response.json().get('ok'):
        logging.error(f"Error opening dialog: {response.json()}")
        send_slack(f"Error opening dialog: {response.json()}")
    
    return response.json()