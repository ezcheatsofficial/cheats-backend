"""Роуты, запрос к которым происходит напрямую из приватного чита
"""
from app import app, subscribers_database, cheats_database, shared_data_database, scheduler
from flask import make_response, request, escape
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from Crypto.Cipher import AES
from app.decorators import required_params
import threading
import json


online_counter_dict = {}


@app.route('/api/app/time-left/<string:cheat_id>/<string:secret_data>/', methods=["GET"])
def get_user_subscription_time_left_enc(cheat_id, secret_data):
    """Получение оставшегося времени подписки пользователя в открытом виде
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
        return make_response({'status': 'error',
                              'message': 'Cheat not found'}), 400
    cheat = cheats_database['cheats'].find_one(
        {'_id': ObjectId(cheat_id)})
    subscriber = subscribers_database[cheat_id].find_one(
        {'secret_data': secret_data})
    if subscriber is not None:
        # получаем разницу во времени в минутах
        minutes = int((subscriber['expire_date'] -
                      datetime.now()).total_seconds() / 60)

        time_left_data = {'time_left': minutes,
                          'secret_data': escape(secret_data)}

        if not subscriber['active']:
            time_left_data['time_left'] = 'inactive'
        elif subscriber['lifetime']:
            time_left_data['time_left'] = 'lifetime'

        return make_response(time_left_data)
    return make_response(
        {'status': 'error', 'message': 'Subscriber not found'}), 400


def update_online_counter(cheat_id, secret_data):
    online_counter_dict[cheat_id].remove(secret_data)


def is_job_in_job(jobs, job_id):
    for job in jobs:
        if job_id == job.id:
            return True
    return False


@app.route('/api/app/online/<string:cheat_id>/', methods=["GET"])
def get_online(cheat_id):
    """Получение онлайна чита
        ---
        consumes:
          - application/json

        parameters:
          - in: path
            name: cheat_id
            type: string
            description: ObjectId чита в строковом формате


        responses:
          200:
            description: Успешный запрос
          400:
            schema:
              $ref: '#/definitions/Error'
    """
    count = 0
    if cheat_id in online_counter_dict:
        for _ in online_counter_dict[cheat_id]:
            count += 1
    return make_response({'online': count}), 400


@app.route('/api/app/online/', methods=["POST"])
@required_params({"cheat_id": str, "secret_data": str})
def update_online():
    """Обновление онлайна чита
        ---
        consumes:
          - application/json

        parameters:
          - in: body
            name: body
            type: object
            schema:
              properties:
                cheat_id:
                  type: string
                  description: ObjectId чита в строковом формате
                secret_data:
                  type: string
                  description: Секретный и уникальный ключ пользователя (например, HWID)

        responses:
          200:
            description: Успешный запрос
          400:
            schema:
              $ref: '#/definitions/Error'
    """
    try:
        data = request.get_json()
        cheat_id = data['cheat_id']
        secret_data = data['secret_data']
    except:
        return make_response(
            {'status': 'error',
             'message': 'One of the parameters specified was missing or invalid'}), 400

    # схема тут такая:
    # 1. если пользователя в счётчике онлайна нет, то добавляем его.
    # Устанавливаем ему job на удаление из счётчика через 2 минуты
    # 2. если пользователь в счётчике онлайна есть, то обновляем ему
    # job на удаление из счётчика (откладываем на 2 минуты)
    # таким образом, если пользователь не будет подавать онлайн
    # сигнала 2 минуты, то он удалится из счётчика
    if cheat_id in subscribers_database.list_collection_names():
        if subscribers_database[cheat_id].find_one({'secret_data': secret_data}) is not None:
            # атомарный доступ к переменной
            semaphore = threading.BoundedSemaphore()
            semaphore.acquire()
            if cheat_id not in online_counter_dict:
                online_counter_dict.update({cheat_id: [secret_data]})
            elif secret_data not in online_counter_dict[cheat_id]:
                online_counter_dict[cheat_id].append(secret_data)

            all_jobs = scheduler.get_jobs()
            if not is_job_in_job(all_jobs, secret_data):
                scheduler.add_job(id=secret_data, func=update_online_counter, trigger="date",
                                  run_date=datetime.now() + timedelta(minutes=2),
                                  kwargs={'cheat_id': cheat_id, 'secret_data': secret_data})
            else:
                scheduler.modify_job(
                    secret_data, next_run_time=datetime.now() + timedelta(minutes=2))
            semaphore.release()
    return ''


@app.route('/api/app/shared-data/', methods=["POST"])
@required_params({"cheat_id": str, "secret_data": str})
def update_shared_data():
    upsert = False
    try:
        data = request.get_json()
        cheat_id = data['cheat_id']
        secret_data = data['secret_data']
        shared_data = data['data']
        if shared_data is None:
            raise
        if 'upsert' in data:
            upsert = bool(data['upsert'])
    except:
        return make_response(
            {'status': 'error',
             'message': 'One of the parameters specified was missing or invalid'}), 400

    cheat = cheats_database.cheats.find_one({'_id': ObjectId(cheat_id)})
    if cheat_id is None:
        return make_response({'status': 'error', 'message': 'Cheat not found'}), 400

    user = subscribers_database[cheat_id].find_one(
        {'secret_data': secret_data})
    if user is None:
        return make_response({'status': 'error', 'message': 'Subscriber not found'}), 400

    shared_data_database[cheat_id].update_one({'secret_data': secret_data}, {
                                              '$set': {'secret_data': secret_data, 'data': shared_data}}, upsert=upsert)

    return make_response({'status': 'ok'})


@app.route('/api/app/shared-data/<string:cheat_id>/<string:secret_data>/', methods=["GET"])
def get_shared_data(cheat_id, secret_data):
    cheat = cheats_database.cheats.find_one({'_id': ObjectId(cheat_id)})
    if cheat_id is None:
        return make_response({'status': 'error', 'message': 'Cheat not found'}), 400

    user = subscribers_database[cheat_id].find_one(
        {'secret_data': secret_data})
    if user is None:
        return make_response({'status': 'error', 'message': 'Subscriber not found'}), 400

    shared_data = shared_data_database[cheat_id].find_one({'secret_data': secret_data}, {'_id': 0, 'secret_data': 0})
    if shared_data is not None:
        return make_response(shared_data)
    return {'status': 'error', 'message': "Shared data doesn't exist"}