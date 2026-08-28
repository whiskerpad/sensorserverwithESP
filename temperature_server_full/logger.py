"""
temperature_server/logger.py
ロギング設定
"""

import logging
import logging.handlers
from config import Config

class SensitiveDataFilter(logging.Filter):
    """センシティブデータをマスクするフィルター"""
    
    def filter(self, record):
        """ログメッセージからセンシティブデータをマスク"""
        if hasattr(record, 'msg') and record.msg:
            msg = str(record.msg)
            # パスワードをマスク
            if Config.AP_PASSWORD and Config.AP_PASSWORD in msg:
                record.msg = msg.replace(Config.AP_PASSWORD, '***')
            # SECRET_KEYをマスク
            if Config.SECRET_KEY and Config.SECRET_KEY in msg:
                record.msg = msg.replace(Config.SECRET_KEY, '***')
        return True

def setup_logger(name):
    """ロガーをセットアップ"""
    logger = logging.getLogger(name)
    
    # 既にハンドラーが設定されている場合はスキップ
    if logger.handlers:
        return logger
    
    # ログレベル設定
    if Config.FLASK_ENV == 'production':
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.DEBUG)
    
    # ログファイルのパス
    log_file = Config.LOGS_DIR / f'{name}.log'
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # ローテーション付きファイルハンドラー
    handler = logging.handlers.TimedRotatingFileHandler(
        str(log_file),
        when='midnight',
        interval=1,
        backupCount=Config.LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    
    # フォーマッタ
    if Config.FLASK_ENV == 'production':
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    handler.setFormatter(formatter)
    
    # センシティブデータフィルターを追加
    handler.addFilter(SensitiveDataFilter())
    
    logger.addHandler(handler)
    
    # コンソールハンドラー（開発環境のみ）
    if Config.FLASK_DEBUG:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.addFilter(SensitiveDataFilter())
        logger.addHandler(console)
    
    return logger








