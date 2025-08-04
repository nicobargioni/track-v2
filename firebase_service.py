import firebase_admin, os
from firebase_admin import credentials,db
from dotenv import load_dotenv

load_dotenv()
databaseURL = os.environ['databaseURL']

def acces_firebase_db():
    if not firebase_admin._apps:

        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred, {'databaseURL': databaseURL, 
                                            'name':'fbapp'})
    ref = db.reference('/acceso')
    return ref.get()