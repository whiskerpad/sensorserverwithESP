"""
temperature_server/app/__init__.py
Flask アプリケーション初期化

コード監査 2026-07-17:
    - CORS 設定を r"/*" 1 本に集約 (元は r"/api/*", r"/wifi/*", r"/*" の三重定義)
    - リクエストロギングを軽量化 (Header 全ダンプ・DELETE 詳細ログを削除)

コード監査 2026-08-16:
    - /wifi/* blueprint と ENABLE_WIFI_API フラグを完全撤廃 (Trixie/NetworkManager
      環境で hostapd/dhcpcd 直操作は実運用と食い違うため)
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from pathlib import Path
from config import Config
from logger import setup_logger

# flask_compress はオプション
try:
    from flask_compress import Compress
    compress_available = True
except ImportError:
    compress_available = False

logger = setup_logger(__name__)


def create_app():
    """Flask アプリケーションを作成"""
    project_root = Path(__file__).parent.parent
    app = Flask(
        __name__,
        template_folder=str(project_root / 'templates'),
        static_folder=str(project_root / 'app' / 'static'),
    )

    # Flask 設定
    app.config['ENV'] = Config.FLASK_ENV
    app.config['DEBUG'] = Config.FLASK_DEBUG
    app.config['SECRET_KEY'] = Config.SECRET_KEY

    # gzip 圧縮 (オプション)
    if compress_available:
        Compress(app)
        logger.info("Response compression (gzip) enabled")

    # ===== リクエストロギング (軽量版) =====
    @app.before_request
    def log_request():
        """1 行だけの簡潔なリクエストログ"""
        logger.info(
            f"[REQUEST] {request.method} {request.path} from {request.remote_addr}"
        )

    @app.after_request
    def log_response(response):
        logger.info(
            f"[RESPONSE] {request.method} {request.path} -> {response.status_code}"
        )
        return response

    # ===== CORS (r"/*" 1 本に集約) =====
    CORS(app, resources={
        r"/*": {
            "origins": Config.ALLOWED_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "max_age": 3600,
        }
    })
    logger.info(f"CORS configured for origins: {Config.ALLOWED_ORIGINS}")

    # ===== ブループリント登録 =====
    # /api/* は必須
    try:
        from app.routes.api import api_bp
        app.register_blueprint(api_bp, url_prefix='/api')
        logger.info("Registered api blueprint with prefix '/api'")
    except Exception as e:
        logger.error(f"Failed to register api blueprint: {e}", exc_info=True)
        raise

    # dashboard も必須
    try:
        from app.routes.dashboard import dashboard_bp
        app.register_blueprint(dashboard_bp)
        logger.info("Registered dashboard blueprint")
    except ImportError:
        logger.warning("dashboard blueprint not found, skipping")

    # ===== エラーハンドラ (API パスは JSON、それ以外は Flask デフォルト) =====
    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith('/api/'):
            return jsonify(
                status='error',
                error_code='NOT_FOUND',
                message=f'API endpoint not found: {request.path}',
                path=request.path,
            ), 404
        return error

    @app.errorhandler(500)
    def internal_error(error):
        if request.path.startswith('/api/'):
            return jsonify(
                status='error',
                error_code='INTERNAL_ERROR',
                message='Internal server error',
                path=request.path,
            ), 500
        return error

    return app
