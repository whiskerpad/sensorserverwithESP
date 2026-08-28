#!/usr/bin/env python3
"""ESP8266 温度モニターサーバー - エントリーポイント

環境変数:
    HOST                    ... リッスンアドレス (default: 0.0.0.0)
    PORT                    ... リッスンポート (default: 5000)
    DB_PATH                 ... SQLite DB ファイルパス
    BASIC_AUTH_USER         ... ダッシュボード用ユーザ名
    BASIC_AUTH_PASSWORD     ... ダッシュボード用パスワード
"""
import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    # debug=False で本番運用 (systemd 経由の起動を想定)
    app.run(host=host, port=port, debug=False)
