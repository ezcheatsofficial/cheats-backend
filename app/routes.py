import os
import requests
from app import app, cheats_database, subscribers_database
from flask import Flask, flash, request, redirect, url_for, session, jsonify, render_template, make_response, Response
from functools import wraps
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes


DISCOURSE_API_KEY = os.environ['DISCOURSE_API_KEY'] if 'DISCOURSE_API_KEY' in os.environ else None


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
    """Полчение информации о всех подписках на различные читы у конкретного пользователя
        ---
        consumes:
          - application/json

        parameters:
          - in: header
            name: X-Auth-Token
            type: string
            required: true
          - in: path
            name: user_id
            type: integer
            description: ID пользователя на сайте

        responses:
          200:
            description: Информация о всех подписках
            schema:
              type: object
              properties:
                subscriptions:
                  type: array
                  items:
                    type: object
                    properties:
                      cheat_id:
                        type: string
                        description: ObjectId чита в строковом формате
                      subscriber:
                        $ref: '#/definitions/Subscriber'
          400:
            schema:
              $ref: '#/definitions/Error'
    """

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
    """Полчение информации о подписке пользователя на конкретный чит
        ---
        consumes:
          - application/json

        parameters:
          - in: header
            name: X-Auth-Token
            type: string
            required: true
          - in: path
            name: cheat_id
            type: string
            description: ObjectId чита в строковом формате
          - in: path
            name: user_id
            type: integer
            description: ID пользователя на сайте

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
            lifetime:
              type: boolean
              required: false
              description: Если значение True, то пользователю будет начислена бесконечная подписка

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

        lifetime = False
        if 'lifetime' in data:
            lifetime = data['lifetime']

        # ID пользователя на сайте
        subscriber_user_id = data['user_id']

        # ник пользователя на сайте. Используется для поиска подписчика по нику
        discourse_user_info = requests.get('https://forum.ezcheats.ru/admin/users/{}.json'.format(subscriber_user_id),
                                           headers={'Api-Key': DISCOURSE_API_KEY}).json()
        if 'errors' in discourse_user_info:
            if 'error_type' == 'not_found':
                return make_response({'status': 'error', 'message': 'User not found'}), 400
            return make_response({'status': 'error', 'message': discourse_user_info['errors'][0]}), 400

        user_name = discourse_user_info['username']

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
                                                                  {'$set': {'expire_date': expire_date, 'active': True,
                                                                            'lifetime': lifetime},
                                                                   '$inc': {'subscriptions_count': 1}})
        # пользователь ещё не имел подписки на это чит. Добавляем его
        else:
            start_date = datetime.now()
            expire_date = start_date + timedelta(minutes=data['minutes'])
            subscriber_data = {'user_id': subscriber_user_id, 'user_name': user_name, 'start_date': start_date,
                               'expire_date': expire_date, 'ip_start': '', 'ip_last': '', 'secret_data': '',
                               'last_online_date': '', 'subscriptions_count': 1, 'lifetime': lifetime, 'active': True}

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


@app.route('/api/subscribers/<string:cheat_id>/<int:skip>/<int:limit>/', methods=["GET"])
def get_all_cheat_subscribers(cheat_id, skip, limit):
    """Получение определённого кол-ва подписчиков конкретного чита, начиная с определённой позиции
        ---
        definitions:
          Subscriber:
            type: object
            properties:
              _id:
                type: string
                description: ObjectId
              user_id:
                type: integer
                description: Пользовательский ID на сайте
              user_name:
                type: string
                description: Ник пользователя на сайте
              start_date:
                type: string
                description: Дата начала подписки (дата первой активации) (ISO формат)
              expire_date:
                type: string
                description: Дата окончания подписки (ISO формат)
              ip_start:
                type: string
                description: IP, с которого проводилась первая активация подписки
              ip_last:
                type: string
                description: IP, с которого пользователь последний раз зашёл в чит
              secret_data:
                type: string
                description: Секретный и уникальный ключ пользователя, который не меняется в рамках одного ПК. Например,
                    HWID + соль в зашифрованном виде
              last_online_date:
                type: string
                description: Дата последнего захода в чит (ISO формат)
              subscriptions_count:
                type: integer
                description: Количество активаций подписки
              lifetime:
                type: boolean
                description: Имеет ли пользователь бесконечную подписку. Если True, то expire_date не важна
              active:
                type: boolean
                description: Активная ли подписка у пользователя или приостановлена. Не используется для проверки
                    подписки в чите, только для проверки её активности. Если False, то считаем, что пользователь на
                    данный момент подписку не имеет, если True, то проверяем lifetime и expire_date

        consumes:
          - application/json

        parameters:
          - in: header
            name: X-Auth-Token
            type: string
            required: true
          - in: path
            name: cheat_id
            type: string
            description: ObjectId чита в строковом формате
          - in: path
            name: skip
            type: integer
            description: Позиция, с которой начать выборку подписчиков. Если 0, то будут выбраны все с начала
          - in: path
            name: limit
            type: integer
            description: Количество подписчиков для выборки

        responses:
          200:
            description: Список подписчиков по выборке
            schema:
              type: object
              properties:
                subscribers:
                  type: array
                  items:
                    $ref: '#/definitions/Subscriber'
          400:
            schema:
              $ref: '#/definitions/Error'
    """

    # skip - позиция, с которой начинаем выборку
    # limit - кол-во элементов для выборки
    cursor = subscribers_database[cheat_id].find({}).skip(skip).limit(limit)
    subscribers = []
    for document in cursor:
        # нормализуем ObjectId
        document['_id'] = str(document['_id'])
        subscribers.append(document)
    return make_response({'subscribers': subscribers})


@app.route('/api/subscribers/search/<string:cheat_id>/<string:name_substring>/', methods=["GET"])
def search_subscribers(cheat_id, name_substring):
    if cheat_id not in subscribers_database.list_collection_names():
        return make_response({'status': 'error', 'message': 'Cheat not found'}), 400

    subscribers_database[cheat_id].create_index([('user_name', 'text')], default_language="english")
    subscribers = []
    cursor = subscribers_database[cheat_id].find({'user_name': {'$regex': name_substring, '$options': '$i'}}).limit(50)

    for document in cursor:
        document['_id'] = str(document['_id'])
        subscribers.append(document)

    return make_response({'subscribers': subscribers})


@app.route('/api/cheats/', methods=["GET"])
def get_all_cheats():
    """Получения списка всех читов
        ---
        definitions:
          Cheat:
            type: object
            properties:
              _id:
                type: string
                description: ObjectId
              title:
                type: string
                description: Название чита
              owner_id:
                type: integer
                description: Пользовательский ID владельца на сайте
              version:
                type: string
                description: Строковая версия чита
              subscribers:
                type: integer
                description: Количество подписчиков с активной подпиской
              subscribers_for_all_time:
                type: integer
                description: Количество подписчиков за всё время
              subscribers_today:
                type: integer
                description: Количество новых подписчиков сегодня
              undetected:
                type: boolean
                description: Статус обнаружения чита античитом
              created_date:
                type: string
                description: Дата добавления чита (ISO формат)
              updated_date:
                type: string
                description: Дата последнего обновления чита (ISO формат)
              status:
                type: string
                description: Статус чита. working - работает, on_update - на обновлении, stopped - остановлен

        consumes:
          - application/json

        responses:
          200:
            description: Полный список приватных читов
            schema:
              type: object
              properties:
                cheats:
                  type: array
                  items:
                    $ref: '#/definitions/Cheat'
          400:
            schema:
              $ref: '#/definitions/Error'
    """
    cursor = cheats_database['cheats'].find({})
    cheats = []
    for document in cursor:
        # нормализуем ObjectId
        document['_id'] = str(document['_id'])
        # удаляем приватные данные:
        del document['secret_key']
        cheats.append(document)
    return make_response({'cheats': cheats})


@app.route('/api/cheats/<string:cheat_id>/', methods=["DELETE"])
def delete_cheat_by_id(cheat_id):
    """Удаление чита по его ObjectId и коллекцию подписчиков на чит
    ---
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
              description: ObjectId чита в строковом формате

    responses:
      200:
        description: Статус-код успешного удаления
        schema:
          type: object
          properties:
            status:
              type: string
              description: ok status
      400:
        schema:
          $ref: '#/definitions/Error'
    """
    try:
        cheat = cheats_database['cheats'].find_one({'_id': ObjectId(cheat_id)})

        if cheat is None:
            return make_response({'status': 'error', 'message': 'Cheat not found'}), 400

        cheats_database['cheats'].delete_one({'_id': ObjectId(cheat_id)})
        subscribers_database[cheat_id].remove()
        subscribers_database[cheat_id].drop()

        return make_response({'status': 'ok'})
    except:
        return make_response(
            {'status': 'error', 'message': 'One of the parameters specified was missing or invalid'}), 400