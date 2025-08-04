#!/usr/bin/env python3
"""
Script para configurar webhooks de Asana para los proyectos mapeados.
Esto permite que cuando se complete una tarea en Asana, se agregue 
una reacción ✅ en el mensaje de Slack que la generó.
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

ASANA_PAT = os.getenv('ASANA_PERSONAL_ACCESS_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://tu-dominio.com/asana/webhook')

def list_existing_webhooks():
    """Lista todos los webhooks existentes"""
    headers = {
        'Authorization': f'Bearer {ASANA_PAT}'
    }
    
    response = requests.get(
        'https://app.asana.com/api/1.0/webhooks',
        headers=headers
    )
    
    if response.status_code == 200:
        webhooks = response.json()['data']
        print(f"\n📋 Webhooks existentes: {len(webhooks)}")
        for webhook in webhooks:
            print(f"  - ID: {webhook['gid']}")
            print(f"    Recurso: {webhook.get('resource', {}).get('gid', 'N/A')}")
            print(f"    Target: {webhook.get('target', 'N/A')}")
            print(f"    Activo: {webhook.get('active', False)}")
            print("")
        return webhooks
    else:
        print(f"❌ Error listando webhooks: {response.status_code}")
        return []

def create_webhook(project_id, project_name):
    """Crea un webhook para un proyecto específico"""
    headers = {
        'Authorization': f'Bearer {ASANA_PAT}',
        'Content-Type': 'application/json'
    }
    
    data = {
        'data': {
            'resource': project_id,
            'target': WEBHOOK_URL,
            'filters': [
                {
                    'resource_type': 'task',
                    'action': 'changed',
                    'fields': ['completed']
                }
            ]
        }
    }
    
    print(f"\n🔄 Creando webhook para proyecto: {project_name} ({project_id})")
    
    response = requests.post(
        'https://app.asana.com/api/1.0/webhooks',
        headers=headers,
        json=data
    )
    
    if response.status_code == 201:
        webhook_data = response.json()['data']
        print(f"✅ Webhook creado exitosamente!")
        print(f"   - Webhook ID: {webhook_data['gid']}")
        print(f"   - Target: {webhook_data['target']}")
        return webhook_data
    else:
        print(f"❌ Error creando webhook: {response.status_code}")
        print(f"   Respuesta: {response.text}")
        return None

def delete_webhook(webhook_id):
    """Elimina un webhook específico"""
    headers = {
        'Authorization': f'Bearer {ASANA_PAT}'
    }
    
    response = requests.delete(
        f'https://app.asana.com/api/1.0/webhooks/{webhook_id}',
        headers=headers
    )
    
    if response.status_code == 200:
        print(f"✅ Webhook {webhook_id} eliminado exitosamente")
        return True
    else:
        print(f"❌ Error eliminando webhook: {response.status_code}")
        return False

def main():
    print("=== CONFIGURACIÓN DE WEBHOOKS DE ASANA ===")
    print(f"URL del webhook: {WEBHOOK_URL}")
    
    if not ASANA_PAT:
        print("❌ ERROR: No se encontró ASANA_PERSONAL_ACCESS_TOKEN en las variables de entorno")
        return
    
    # Verificar que la URL del webhook esté configurada correctamente
    if WEBHOOK_URL == 'https://tu-dominio.com/asana/webhook':
        print("\n⚠️  ADVERTENCIA: Estás usando la URL de ejemplo.")
        print("   Asegúrate de configurar WEBHOOK_URL en tu archivo .env")
        print("   Ejemplo: WEBHOOK_URL=https://tu-dominio-real.com/asana/webhook")
        continuar = input("\n¿Deseas continuar de todos modos? (s/n): ")
        if continuar.lower() != 's':
            return
    
    # Cargar proyectos desde channel_map.json
    try:
        with open('channel_map.json', 'r') as f:
            channel_map = json.load(f)
    except FileNotFoundError:
        print("❌ ERROR: No se encontró channel_map.json")
        return
    
    # Cargar nombres de proyectos desde asana_pj.json
    project_names = {}
    try:
        with open('asana_pj.json', 'r', encoding='utf-8') as f:
            asana_projects = json.load(f)
            # Invertir el mapeo para tener ID -> Nombre
            project_names = {v: k for k, v in asana_projects.items()}
    except:
        print("⚠️  No se pudo cargar asana_pj.json, se usarán IDs en lugar de nombres")
    
    # Obtener lista única de proyectos
    unique_projects = list(set(channel_map.values()))
    print(f"\n📊 Proyectos encontrados en channel_map.json: {len(unique_projects)}")
    
    # Listar webhooks existentes
    existing_webhooks = list_existing_webhooks()
    existing_resources = [w.get('resource', {}).get('gid') for w in existing_webhooks]
    
    # Menú de opciones
    while True:
        print("\n¿Qué deseas hacer?")
        print("1. Crear webhooks para todos los proyectos")
        print("2. Crear webhook para un proyecto específico")
        print("3. Listar webhooks existentes")
        print("4. Eliminar todos los webhooks")
        print("5. Salir")
        
        opcion = input("\nSelecciona una opción (1-5): ")
        
        if opcion == '1':
            # Crear webhooks para todos los proyectos
            created = 0
            skipped = 0
            
            for project_id in unique_projects:
                if project_id in existing_resources:
                    print(f"\n⏭️  Proyecto {project_id} ya tiene webhook, omitiendo...")
                    skipped += 1
                    continue
                
                project_name = project_names.get(project_id, f"Proyecto {project_id}")
                if create_webhook(project_id, project_name):
                    created += 1
            
            print(f"\n📊 Resumen: {created} webhooks creados, {skipped} omitidos")
            
        elif opcion == '2':
            # Mostrar lista de proyectos
            print("\n📋 Proyectos disponibles:")
            for i, project_id in enumerate(unique_projects):
                project_name = project_names.get(project_id, f"Proyecto {project_id}")
                status = "✅" if project_id in existing_resources else "❌"
                print(f"{i+1}. {status} {project_name} ({project_id})")
            
            try:
                idx = int(input("\nSelecciona el número del proyecto: ")) - 1
                if 0 <= idx < len(unique_projects):
                    project_id = unique_projects[idx]
                    project_name = project_names.get(project_id, f"Proyecto {project_id}")
                    
                    if project_id in existing_resources:
                        print(f"\n⚠️  Este proyecto ya tiene un webhook configurado")
                        confirmar = input("¿Deseas crear uno nuevo de todos modos? (s/n): ")
                        if confirmar.lower() != 's':
                            continue
                    
                    create_webhook(project_id, project_name)
                else:
                    print("❌ Número inválido")
            except ValueError:
                print("❌ Por favor ingresa un número válido")
            
        elif opcion == '3':
            list_existing_webhooks()
            
        elif opcion == '4':
            confirmar = input("\n⚠️  ¿Estás seguro de que deseas eliminar TODOS los webhooks? (s/n): ")
            if confirmar.lower() == 's':
                deleted = 0
                for webhook in existing_webhooks:
                    if delete_webhook(webhook['gid']):
                        deleted += 1
                print(f"\n📊 {deleted} webhooks eliminados")
                existing_webhooks = []
                existing_resources = []
            
        elif opcion == '5':
            print("\n👋 ¡Hasta luego!")
            break
        
        else:
            print("❌ Opción inválida")

if __name__ == '__main__':
    main()