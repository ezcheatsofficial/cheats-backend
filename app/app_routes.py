from app import app, subscribers_database, cheats_database
from flask import make_response
from datetime import datetime
from bson.objectid import ObjectId
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import json


@app.route('/api/app/time-left/<string:cheat_id>/<string:secret_data>/', methods=["GET"])
def get_user_subscription_time_left_enc(cheat_id, secret_data):
    """Полчение оставшегося времени подписки пользователя в открытом виде
        ---
        consumes:
          - application/json

        parameters:
          - in: path
            name: cheat_id
            type: string
            description: ObjectId чита в строковом формате
          - in: path
            name: secret_data
            type: string
            description: Секретный и уникальный ключ пользователя (например, HWID)

        responses:
          200:
            description: Информация о подписке
            schema:
              $ref: '#/definitions/Subscriber'
          400:
            schema:
              $ref: '#/definitions/Error'
    """
    if cheat_id not in subscribers_database.list_collection_names():
        return make_response({'status': 'error', 'message': 'Cheat not found'}), 400
    cheat = cheats_database['cheats'].find_one({'_id': ObjectId(cheat_id)})
    subscriber = subscribers_database[cheat_id].find_one({'secret_data': secret_data})
    if subscriber is not None:
        # получаем разницу во времени в минутах
        minutes = int((subscriber['expire_date'] - datetime.now()).total_seconds() / 60)

        json_string = json.dumps({'time_left': minutes, 'secret_data': secret_data})
        if not subscriber['active']:
            json_string = json.dumps({'time_left': 'inactive', 'secret_data': secret_data})
        elif subscriber['lifetime']:
            json_string = json.dumps({'time_left': 'lifetime', 'secret_data': secret_data})

        return make_response(json_string)
    return make_response({'status': 'error', 'message': 'Subscriber not found'}), 400
