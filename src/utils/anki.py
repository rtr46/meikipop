import json
import base64
import requests
import logging

logger = logging.getLogger(__name__)

class AnkiConnect:
    def __init__(self, url="http://127.0.0.1:8765"):
        self.url = url

    def invoke(self, action, **params):
        requestJson = json.dumps({
            "action": action,
            "version": 6,
            "params": params
        })
        try:
            response = requests.post(self.url, requestJson).json()
        except requests.exceptions.ConnectionError:
            logger.error("Failed to connect to AnkiConnect. Is Anki running?")
            return None

        if len(response) != 2:
            logger.error("Response has an unexpected number of fields.")
            return None
        if "error" not in response:
            logger.error("Response is missing required error field.")
            return None
        if "result" not in response:
            logger.error("Response is missing required result field.")
            return None
        if response["error"] is not None:
            logger.error(f"AnkiConnect error: {response['error']}")
            return None
        return response["result"]

    def is_connected(self):
        try:
            return self.invoke("version") is not None
        except:
            return False

    def get_deck_names(self):
        return self.invoke("deckNames")

    def get_model_names(self):
        return self.invoke("modelNames")

    def get_model_field_names(self, model_name):
        return self.invoke("modelFieldNames", modelName=model_name)

    def store_media_file(self, filename, data_base64):
        return self.invoke("storeMediaFile", filename=filename, data=data_base64)

    def add_note(self, deck_name, model_name, fields, tags=None):
        note = {
            "deckName": deck_name,
            "modelName": model_name,
            "fields": fields,
            "tags": tags or []
        }
        return self.invoke("addNote", note=note)

    def create_model(self, model_name, in_order_fields, css, card_templates):
        return self.invoke("createModel", 
                           modelName=model_name, 
                           inOrderFields=in_order_fields, 
                           css=css, 
                           cardTemplates=card_templates)

