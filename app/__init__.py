from flask import Flask
from flasgger import Swagger, swag_from
from pymongo import MongoClient

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
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT Authorization header using the Bearer scheme. Example: \"Authorization: Bearer {token}\""
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
database = client['cheats']

app = Flask(__name__)

app.config['SWAGGER'] = {
    'title': 'EZcheats Apps API',
    'uiversion': 3,
    "specs_route": "/api/docs/"
}
swagger = Swagger(app, template=template)