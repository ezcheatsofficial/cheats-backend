from app import app, cheats_database, subscribers_database
from flask import Flask, flash, request, redirect, url_for, session, jsonify, render_template, make_response, Response
from functools import wraps
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes


def required_params(required):
    def decorator(fn):

        @wraps(fn)
        def wrapper(*args, **kwargs):
            _json = request.get_json()
            missing = [r for r in required.keys()
                       if r not in _json]
            if missing:
                response = {
                    "status": "error",
                    "message": "Request JSON is missing some required params",
                    "missing": missing
                }
                return jsonify(response), 400
            wrong_types = [r for r in required.keys()
                           if not isinstance(_json[r], required[r])]
            if wrong_types:
                response = {
                    "status": "error",
                    "message": "Data types in the request JSON doesn't match the required format",
                    "param_types": {k: str(v) for k, v in required.items()}
                }
                return jsonify(response), 400
            return fn(*args, **kwargs)

        return wrapper

    return decorator


@app.route('/api/subscribers/<int:user_id>/', methods=["GET"])
def get_all_user_subscriptions(user_id):
    subscriptions = []
    # проходимся по всем коллекциям и ищим подписки у пользователя
    for cheat_id in subscribers_database.list_collection_names():
        subscriber = subscribers_database[cheat_id].find_one({'user_id': user_id})
        if subscriber is not None:
            # нормализуем object_id, так как в json формат такое не съест
            subscriber['_id'] = str(subscriber['_id'])
            subscription_obj = {'cheat_id': cheat_id, 'subscriber': subscriber}
            subscriptions.append(subscription_obj)

    if len(subscriptions) > 0:
        return make_response({'subscriptions': subscriptions})

    return make_response({'status': 'error', 'message': 'Subscriptions not found'}), 400


@app.route('/api/subscribers/<string:cheat_id>/<int:user_id>/', methods=["GET"])
def get_user_subscription_by_cheat(cheat_id, user_id):
    if cheat_id not in subscribers_database.list_collection_names():
        return make_response({'status': 'error', 'message': 'Cheat not found'}), 400

    subscriber = subscribers_database[cheat_id].find_one({'user_id': user_id})
    if subscriber is not None:
        # нормализуем object_id, так как в json формат такое не съест
        subscriber['_id'] = str(subscriber['_id'])
        return make_response(subscriber)
    return make_response({'status': 'error', 'message': 'Subscriber not found'}), 400


@app.route('/api/subscribers/', methods=["POST"])
@required_params({"cheat_id": str, "minutes": int, "user_id": int})
def add_subscriber_or_subscription():
    """Добавление минут к подписке на приватный чит или нового подписчика, если он до этого не имел подписку
    ---
    definitions:
      AddSubscribeResult:
        type: object
        nullable: false
        properties:
          status:
            type: string
            description: ok
          expire_date:
            type: string
            description: ISO дата, которая соответствует дате, когда у пользователя кончается подписка на чит

    consumes:
      - application/json

    parameters:
      - in: header
        name: X-Auth-Token
        type: string
        required: true
      - in: body
        name: body
        type: object
        schema:
          properties:
            cheat_id:
              type: string
              required: true
              description: Строковый ObjectId чита
            minutes:
              type: integer
              required: true
              description: Количество минут, которые необходимо добавить пользователю к подписке
            user_id:
              type: integer
              required: true
              description: ID пользователя на сайте

    responses:
      200:
        description: Дата окончания подписки
        schema:
          $ref: '#/definitions/AddSubscribeResult'
      400:
        schema:
          $ref: '#/definitions/Error'
    """
    try:
        data = request.get_json()
        cheat = cheats_database.cheats.find_one({'_id': ObjectId(data['cheat_id'])})
        if cheat is None:
            return make_response({'status': 'error', 'message': 'Cheat not found'}), 400

        # ID пользователя на сайте
        subscriber_user_id = data['user_id']

        # ищем подписчика чита по его ID на сайте
        subscriber = subscribers_database[data.get('cheat_id')].find_one({'user_id': subscriber_user_id})

        # если пользователь уже до этого имел подписку на чит
        if subscriber is not None:
            # если пользователь уже имеет активную подписку, то просто добавляем ему время
            if (subscriber['expire_date'] - subscriber['start_date']).seconds > 0:
                expire_date = subscriber['expire_date'] + timedelta(minutes=data['minutes'])
            else:
                expire_date = datetime.now() + timedelta(minutes=data['minutes'])

            # устанавливаем новую дату окончания подписки, меняем статус на активную,
            # увеличиваем счётчик кол-ва подписок на 1
            subscribers_database[data.get('cheat_id')].update_one({'_id': subscriber['_id']},
                                                                  {'$set': {'expire_date': expire_date, 'active': True},
                                                                   '$inc': {'subscriptions_count': 1}})
        # пользователь ещё не имел подписки на это чит. Добавляем его
        else:
            start_date = datetime.now()
            expire_date = start_date + timedelta(minutes=data['minutes'])
            subscriber_data = {'user_id': subscriber_user_id, 'start_date': start_date, 'expire_date': expire_date,
                               'ip_start': '', 'ip_last': '', 'secret_data': '', 'last_online_date': '',
                               'subscriptions_count': 1, 'active': True}

            subscribers_database[data.get('cheat_id')].insert_one(subscriber_data)

        return make_response({'status': 'ok', 'expire_date': expire_date})

    except:
        return make_response(
            {'status': 'error', 'message': 'One of the parameters specified was missing or invalid'}), 400


@app.route('/api/cheats/', methods=["POST"])
@required_params({"title": str, "owner_id": int, "version": str})
def create_new_cheat():
    """Создание нового приватного чита
    ---
    definitions:
      Error:
        type: object
        properties:
          status:
            type: string
            description: Error status
          message:
            type: string

      ObjectId:
        type: object
        nullable: false
        properties:
          status:
            type: string
            description: ok
          object_id:
            type: string
            description: Уникальный ID (hex формата) созданного объекта в базе данных

    consumes:
      - application/json

    parameters:
      - in: header
        name: X-Auth-Token
        type: string
        required: true
      - in: body
        name: body
        type: object
        schema:
          properties:
            title:
              type: string
              description: Название приватного чита
            owner_id:
              type: integer
              description: ID пользователя на сайте
            version:
              type: string

    responses:
      200:
        description: ID вставленного объекта
        schema:
          $ref: '#/definitions/ObjectId'
      400:
        schema:
          $ref: '#/definitions/Error'
    """

    data = request.get_json()
    title = data['title']
    owner_id = data['owner_id']
    version = data['version']

    cheat = cheats_database.cheats.find_one({'title': title, 'owner_id': owner_id})
    if cheat is not None:
        return make_response({'status': 'error', 'message': 'Cheat already exists'}), 400
    else:
        # статусы чита:
        # working - работает, on_update - на обновлении, stopped - остановлен

        # секретный ключ чита, который используется при AES шифровании
        secret_key = get_random_bytes(16)  # Генерируем ключ шифрования

        object_id = str(cheats_database.cheats.insert_one({
            'title': title, 'owner_id': owner_id, 'version': version, 'subscribers': 0,
            'subscribers_for_all_time': 0, 'subscribers_today': 0, 'undetected': True,
            'created_date': datetime.now(), 'updated_date': datetime.now(), 'status': 'working',
            'secret_key': secret_key
        }).inserted_id)

    return make_response({'status': 'ok', 'object_id': object_id, 'secret_key': str(secret_key)})
