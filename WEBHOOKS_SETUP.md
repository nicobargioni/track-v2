# Configuración de Webhooks de Asana

Los webhooks de Asana permiten que cuando se complete una tarea, automáticamente se agregue una reacción ✅ en el mensaje de Slack que la generó.

## Requisitos previos

1. El servidor debe estar accesible desde Internet (no localhost)
2. Tener configurada la variable `WEBHOOK_URL` en tu archivo `.env`:
   ```
   WEBHOOK_URL=https://tu-dominio.com/asana/webhook
   ```

## Configuración automática (recomendada)

1. Ejecuta el script de configuración:
   ```bash
   python setup_asana_webhooks.py
   ```

2. El script te mostrará un menú con las siguientes opciones:
   - **Opción 1**: Crear webhooks para todos los proyectos automáticamente
   - **Opción 2**: Crear webhook para un proyecto específico
   - **Opción 3**: Listar webhooks existentes
   - **Opción 4**: Eliminar todos los webhooks
   - **Opción 5**: Salir

3. Para la configuración inicial, selecciona la **Opción 1** para crear todos los webhooks de una vez.

## Configuración manual (avanzada)

Si prefieres configurar los webhooks manualmente usando curl:

```bash
# Listar webhooks existentes
curl -X GET https://app.asana.com/api/1.0/webhooks \
  -H "Authorization: Bearer TU_ASANA_PAT"

# Crear un webhook para un proyecto
curl -X POST https://app.asana.com/api/1.0/webhooks \
  -H "Authorization: Bearer TU_ASANA_PAT" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "resource": "ID_DEL_PROYECTO",
      "target": "https://tu-dominio.com/asana/webhook",
      "filters": [{
        "resource_type": "task",
        "action": "changed",
        "fields": ["completed"]
      }]
    }
  }'

# Eliminar un webhook
curl -X DELETE https://app.asana.com/api/1.0/webhooks/WEBHOOK_ID \
  -H "Authorization: Bearer TU_ASANA_PAT"
```

## Verificación

Para verificar que los webhooks están funcionando:

1. Crea una tarea desde Slack (el bot debe reaccionar con 💡)
2. Ve a Asana y marca la tarea como completada
3. En unos segundos, deberías ver la reacción ✅ en el mensaje de Slack

## Solución de problemas

### El webhook no se activa
- Verifica que tu servidor sea accesible desde Internet
- Revisa los logs del servidor para ver si llegan las peticiones de Asana
- Asegúrate de que el webhook esté activo usando el script (opción 3)

### Error al crear webhooks
- Verifica que tu Personal Access Token tenga permisos suficientes
- Asegúrate de que los IDs de proyecto en `channel_map.json` sean correctos
- Revisa que no haya webhooks duplicados para el mismo proyecto

### Las reacciones no aparecen
- Verifica que el bot tenga el permiso `reactions:write` en Slack
- Revisa que el mapeo de tareas en `task_mapping.json` contenga la tarea
- Verifica los logs cuando se complete una tarea para ver posibles errores

## Notas importantes

- Asana permite un máximo de 100 webhooks por aplicación
- Los webhooks se desactivan automáticamente si fallan repetidamente
- Cada webhook debe responder al handshake inicial de Asana con el header `X-Hook-Secret`
- Los eventos de Asana llegan en lotes, pueden contener múltiples cambios