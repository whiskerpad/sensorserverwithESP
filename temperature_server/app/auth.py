"""Basic 認証デコレータ。

ダッシュボードと GET 系 API に適用。
POST /api/sensor (ESP からの受信) は認証なし (LAN 内前提)。
"""
from functools import wraps
from flask import request, Response, current_app


def _check_credentials(username, password):
    """環境変数の値と照合。"""
    return (
        username == current_app.config['BASIC_AUTH_USER']
        and password == current_app.config['BASIC_AUTH_PASSWORD']
    )


def basic_auth_required(f):
    """@basic_auth_required デコレータ。認証失敗時は 401 を返す。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not _check_credentials(auth.username, auth.password):
            return Response(
                '認証が必要です。',
                401,
                {'WWW-Authenticate': 'Basic realm="Temperature Monitor"'},
            )
        return f(*args, **kwargs)
    return decorated
