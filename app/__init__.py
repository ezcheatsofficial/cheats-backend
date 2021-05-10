import os
from flask import Flask
from flasgger import Swagger
from pymongo import MongoClient
from flask_apscheduler import APScheduler

template = {
    "swagger": "2.0",
    "info": {
        "title": "EZcheats Apps API",
        "description": "API приватных продуктов (читов) на EZcheats",
        "version": "2.0.0",
        "contact": {
            "name": "Oniel",
            "url": "https://vk.com/onie1",
        }
    },
    "securityDefinitions": {
        "ApiKeyAuth": {
            "type": "apiKey",
            "name": "X-Auth-Token",
            "in": "header",
            "description": "Secret authorization header",
        }
    },
    "security": [
        {
            "Bearer": []
        }
    ]

}

# MongoDB settings:
client = MongoClient('localhost', 27017)
cheats_database = client['cheats']
subscribers_database = client['subscribers']
shared_data_database = client['shared_data']

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024
app.config['SWAGGER'] = {
    'title': 'EZcheats Apps API',
    'uiversion': 3,
    "specs_route": "/api/docs/"
}

# scheduler for online counters
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

swagger = Swagger(app, template=template)

DISCOURSE_API_KEY = os.environ['DISCOURSE_API_KEY'] if 'DISCOURSE_API_KEY' in os.environ else None
SECRET_AUTH_TOKEN = os.environ['SECRET_AUTH_TOKEN'] if 'SECRET_AUTH_TOKEN' in os.environ else None

from app import subscribers_routes, cheats_routes, app_routes, decorators
