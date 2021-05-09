from flask import request, jsonify, make_response
from functools import wraps
from app import SECRET_AUTH_TOKEN


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


def token_required(fn):
    @wraps(fn)
    def decorated_function(*args, **kws):
        if SECRET_AUTH_TOKEN is not None:
            if 'X-Auth-Token' not in request.headers:
                return make_response(
                    {'status': 'error', 
                     'message': 'The secret token for this request is required'}), 401

            if request.headers['X-Auth-Token'] != SECRET_AUTH_TOKEN:
                return make_response({'status': 'error', 
                                      'message': 'Wrong API token'}), 401

        return fn(*args, **kws)

    return decorated_function
