from flask import Flask, flash, request, redirect, url_for, session, jsonify, render_template, make_response, Response
from app import app, database
from functools import wraps
from datetime import datetime

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


@app.route('/api/cheats/', methods=["POST"])
@required_params({"title": str, "owner_id": int, "version": str})
def create_new_cheat():
    data = request.get_json()
    title = data['title']
    owner_id = data['owner_id']
    version = data['version']

    cheat = database.cheats.find_one({'title': title, 'owner_id': owner_id})
    if cheat is not None:
        return make_response({'status': 'error', 'message': 'Cheat already exists'}), 400
    else:
        # статусы чита:
        # working - работает, on_update - на обновлении, stopped - остановлен
        object_id = str(database.cheats.insert_one({
            "title": title, 'owner_id': owner_id, 'version': version, 'subscribers': 0,
            'new_subscribers_today': 0, 'undetected': True, 'created_date': datetime.now(),
            'updated_date': datetime.now(), 'status': 'working'
        }).inserted_id)
