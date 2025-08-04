import os, logging
import requests
from datetime import datetime
from utils import send_slack
from dotenv import load_dotenv

load_dotenv()

ASANA_PAT = os.getenv('ASANA_PERSONAL_ACCESS_TOKEN')

def create_asana_task(name, assignee_email, project_id, due_on=None, description=None, subtasks=None, assignee_gid=None):
    logging.info("Args received:")
    logging.info(f"name={name}, assignee_email={assignee_email}, project_id={project_id}, due_on={due_on}, description={description}, subtasks={subtasks}")
    headers = {
        'Authorization': f'Bearer {ASANA_PAT}',
        'Content-Type': 'application/json'
    }
    
    task_data = {
        'data': {
            'name': name,
            'projects': [project_id]
        }
    }
    
    # Agregar descripción si existe
    if description:
        task_data['data']['notes'] = description
    
    # Si se proporciona assignee_gid directamente, usarlo
    if assignee_gid:
        task_data['data']['assignee'] = assignee_gid
    elif assignee_email:
        logging.info(f"Buscando usuario en Asana con email: {assignee_email}")
        assignee_gid = get_user_by_email(assignee_email)
        if assignee_gid:
            logging.info(f"Usuario encontrado en Asana: {assignee_gid}")
            task_data['data']['assignee'] = assignee_gid
        else:
            logging.warning(f"Usuario NO encontrado en Asana con email: {assignee_email}")
    
    if due_on:
        try:
            parsed_date = parse_date(due_on)
            if parsed_date:
                task_data['data']['due_on'] = parsed_date
        except:
            pass
    
    response = requests.post(
        'https://app.asana.com/api/1.0/tasks',
        headers=headers,
        json=task_data
    )
    
    if response.status_code == 201:
        task = response.json()['data']
        task_gid = task['gid']
        
        # Crear subtareas si existen
        if subtasks:
            subtask_list = [s.strip() for s in subtasks.split('\n') if s.strip()]
            for subtask_name in subtask_list:
                create_subtask(task_gid, subtask_name, assignee_gid)
        
        return {
            'url': f"https://app.asana.com/0/{project_id}/{task_gid}",
            'assignee_found': assignee_gid is not None,
            'gid': task_gid
        }
    else:
        raise Exception(f"Error creating Asana task: {response.status_code} - {response.text}")

def create_subtask(parent_task_gid, name, assignee_gid=None):
    headers = {
        'Authorization': f'Bearer {ASANA_PAT}',
        'Content-Type': 'application/json'
    }
    
    subtask_data = {
        'data': {
            'name': name,
            'parent': parent_task_gid
        }
    }
    
    if assignee_gid:
        subtask_data['data']['assignee'] = assignee_gid
    
    response = requests.post(
        'https://app.asana.com/api/1.0/tasks',
        headers=headers,
        json=subtask_data
    )
    
    if response.status_code != 201:
        logging.error(f"Error creating subtask: {response.status_code} - {response.text}")
        send_slack(f"Error creating subtask: {response.status_code} - {response.text}")

def get_user_by_email(email):
    if not email:
        logging.warning("No se proporcionó email")
        return None
        
    headers = {
        'Authorization': f'Bearer {ASANA_PAT}'
    }
    
    try:
        workspace_gid = get_workspace_gid()
    except Exception as e:
        logging.error(f"Error obteniendo workspace: {e}")
        send_slack(f"Error obteniendo workspace: {e}")
        return None
    
    # Intentar buscar por email exacto
    response = requests.get(
        f'https://app.asana.com/api/1.0/workspaces/{workspace_gid}/users',
        headers=headers
    )
    
    if response.status_code == 200:
        all_users = response.json()['data']
        logging.info(f"Total usuarios en workspace: {len(all_users)}")
        
        # Buscar coincidencia exacta por email
        for user in all_users:
            user_detail = requests.get(
                f'https://app.asana.com/api/1.0/users/{user["gid"]}',
                headers=headers
            )
            if user_detail.status_code == 200:
                user_data = user_detail.json()['data']
                if user_data.get('email', '').lower() == email.lower():
                    logging.info(f"Usuario encontrado: {user_data.get('name')} - {user_data.get('email')}")
                    return user['gid']
    logging.warning(f"No se encontró usuario con email: {email}")
    return None

def get_workspace_gid():
    headers = {
        'Authorization': f'Bearer {ASANA_PAT}'
    }
    
    response = requests.get(
        'https://app.asana.com/api/1.0/workspaces',
        headers=headers
    )
    
    if response.status_code == 200:
        workspaces = response.json()['data']
        if workspaces:
            return workspaces[0]['gid']
    
    raise Exception("No workspace found")

def parse_date(date_str):
    date_formats = [
        '%Y-%m-%d',
        '%d/%m/%Y',
        '%d-%m-%Y',
        '%m/%d/%Y',
        '%m-%d-%Y'
    ]
    
    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt)
            return parsed_date.strftime('%Y-%m-%d')
        except ValueError:
            continue
    
    return None

def delete_asana_task(task_gid):
    """Elimina una tarea de Asana"""
    headers = {
        'Authorization': f'Bearer {ASANA_PAT}'
    }
    
    response = requests.delete(
        f'https://app.asana.com/api/1.0/tasks/{task_gid}',
        headers=headers
    )
    
    if response.status_code == 200:
        logging.info(f"Tarea {task_gid} eliminada exitosamente")
        return True
    else:
        logging.error(f"Error eliminando tarea: {response.status_code} - {response.text}")
        raise Exception(f"Error eliminando tarea: {response.status_code}")

def get_task_details(task_gid):
    """Obtiene los detalles de una tarea de Asana"""
    headers = {
        'Authorization': f'Bearer {ASANA_PAT}'
    }
    
    response = requests.get(
        f'https://app.asana.com/api/1.0/tasks/{task_gid}',
        headers=headers
    )
    
    if response.status_code == 200:
        return response.json()['data']
    else:
        logging.error(f"Error obteniendo detalles de tarea: {response.status_code} - {response.text}")
        return None