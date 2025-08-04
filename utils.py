import requests, json, logging
# import firebase_service

# ACCESO = firebase_service.acces_firebase_db()
# error_webhook = ACCESO['error_webhook']

def send_slack(text):
  # Temporalmente deshabilitado - necesita configurar Firebase
  logging.info(f"[TRACKER-BOT] {text}")
  # slack_data = {'text': "[TRACKER-BOT] " + text}
  # response = requests.post(error_webhook, data=json.dumps(slack_data), headers={'Content-Type': 'application/json'})
  # logging.info(response.status_code)