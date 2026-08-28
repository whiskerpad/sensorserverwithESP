"""Flask アプリケーションファクトリ。

設計方針:
- 環境変数で全設定を上書き可能 (systemd の EnvironmentFile で管理しやすくする)
- ロギングは stdout + ファイル両出力 (systemd journal と app ログの双方に残す)
- DB は起動時に初期化 (スキーマ未存在なら作成)
"""
import os
import logging
from pathlib import Path

from flask import Flask

from .database import init_db
from .routes import bp

# プロジェクトルート (このファイルの2つ上のディレクトリ)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app():
    """Flask アプリケーションを生成して返す。"""
    app = Flask(
        __name__,
        static_folder=str(PROJECT_ROOT / 'static'),
        template_folder=str(PROJECT_ROOT / 'templates'),
    )

    # ---- 設定 ----
    app.config['DB_PATH'] = os.environ.get(
        'DB_PATH', str(PROJECT_ROOT / 'data' / 'temperature.db')
    )
    app.config['BASIC_AUTH_USER'] = os.environ.get('BASIC_AUTH_USER', 'admin')
    app.config['BASIC_AUTH_PASSWORD'] = os.environ.get(
        'BASIC_AUTH_PASSWORD', 'change-me'
    )

    # ---- ロギング ----
    log_dir = PROJECT_ROOT / 'logs'
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / 'server.log'
    log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(),  # systemd journal に流れる
        ],
    )

    # ---- DB 初期化 ----
    db_path = Path(app.config['DB_PATH'])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with app.app_context():
        init_db()

    # ---- Blueprint 登録 ----
    app.register_blueprint(bp)

    logging.getLogger(__name__).info(
        "Server initialized: DB=%s, Auth user=%s",
        app.config['DB_PATH'],
        app.config['BASIC_AUTH_USER'],
    )
    return app
