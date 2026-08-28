"""
リクエストトレーシング機能
各リクエストに一意のIDを付与してログを追跡可能にする
"""

import uuid
from functools import wraps
from flask import request, g
from logger import setup_logger

logger = setup_logger(__name__)


def generate_request_id() -> str:
    """リクエストIDを生成"""
    return str(uuid.uuid4())[:8]


def get_request_id() -> str:
    """現在のリクエストIDを取得"""
    if not hasattr(g, 'request_id'):
        g.request_id = generate_request_id()
    return g.request_id


def trace_request(f):
    """
    リクエストトレーシングデコレータ
    各リクエストに一意のIDを付与し、ログに記録
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # リクエストIDを生成
        request_id = generate_request_id()
        g.request_id = request_id
        
        # リクエスト情報をログに記録
        logger.info(
            f"[{request_id}] {request.method} {request.path} "
            f"from {request.remote_addr}"
        )
        
        try:
            result = f(*args, **kwargs)
            logger.info(f"[{request_id}] Request completed successfully")
            return result
        except Exception as e:
            logger.error(
                f"[{request_id}] Request failed: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            raise
    
    return decorated_function


def log_with_request_id(message: str, level: str = 'info') -> str:
    """
    リクエストID付きでログを記録
    
    Args:
        message: ログメッセージ
        level: ログレベル ('info', 'warning', 'error', 'debug')
    
    Returns:
        リクエストID
    """
    try:
        request_id = get_request_id()
    except RuntimeError:
        # Flaskコンテキスト外の場合はIDを生成しない
        request_id = 'no-context'
    
    log_message = f"[{request_id}] {message}"
    
    if level == 'info':
        logger.info(log_message)
    elif level == 'warning':
        logger.warning(log_message)
    elif level == 'error':
        logger.error(log_message)
    elif level == 'debug':
        logger.debug(log_message)
    
    return request_id

