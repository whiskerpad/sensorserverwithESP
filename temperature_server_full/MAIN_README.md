# デュアル WiFi 温度監視システム

**完全なドキュメント付きオープンソースプロジェクト**

このプロジェクトは、Raspberry Pi の USB WiFi ドングルを使用してアクセスポイント（AP）を構築し、複数の ESP32 マイコンから温度データを受け取るシステムです。

---

## 📚 ドキュメント一覧

本プロジェクトは、詳細なドキュメントによってサポートされています：

### 1. **[README.md](docs/README.md)** - プロジェクト概要
   - クイックスタート
   - システム要件
   - API リファレンス
   - パフォーマンス情報

### 2. **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - システム設計
   - ネットワーク構成図
   - データフロー図
   - コンポーネント詳細
   - データベーススキーマ

### 3. **[WIFI_SETUP.md](docs/WIFI_SETUP.md)** - ⭐ 最重要ガイド
   - 7ステップの詳細な WiFi 設定
   - ドライバインストール方法
   - 設定ファイルの詳細説明
   - よくある失敗パターン

### 4. **[SETUP_GUIDE.md](docs/SETUP_GUIDE.md)** - セットアップガイド
   - 7フェーズの初期設定
   - ステップバイステップの指示
   - 検証方法

### 5. **[LESSONS_LEARNED.md](docs/LESSONS_LEARNED.md)** - 教訓ドキュメント
   - 6時間の開発過程で学んだ 10 の重要な教訓
   - よくある落とし穴とその回避方法
   - デバッグの考え方

### 6. **[TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - トラブルシューティング
   - 8つの主要な問題と解決方法
   - 診断フロー
   - ログ収集スクリプト

### 7. **[ESP32_CODE.md](docs/ESP32_CODE.md)** - マイコン実装ガイド
   - 完全なサンプルコード
   - ハードウェア接線図
   - API リクエスト形式
   - よくある問題の解決

---

## 🚀 クイックスタート（5分）

### 要件
- Raspberry Pi 4（2GB以上）
- TP-Link Archer T2U Plus（RTL8821AU）
- ESP32 + DS18B20 温度センサー

### セットアップ（簡易版）

```bash
# 1. リポジトリをクローン
git clone https://github.com/YOUR_USERNAME/dual-wifi-temperature-monitoring.git
cd dual-wifi-temperature-monitoring

# 2. Python 環境を構築
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. 設定ファイルを確認
cat config.py  # WiFi SSID とパスワードを確認

# 4. Flask サーバーを起動
python3 server.py

# 5. ブラウザで確認
# http://192.168.4.1:5000/
```

**詳細な設定方法は [WIFI_SETUP.md](docs/WIFI_SETUP.md) を参照してください**

---

## 📊 ファイル構造

```
temperature_server/
├── app/
│   ├── __init__.py          # Flask アプリケーション
│   └── routes/
│       └── api.py           # API エンドポイント
├── services/
│   ├── wifi_manager.py      # WiFi 管理（修正済み）
│   └── background_tasks.py  # バックグラウンドタスク
├── database/
│   ├── models.py            # SQLite モデル
│   └── init_db.py           # データベース初期化
├── templates/
│   └── dashboard.html       # Web UI
├── config.py                # アプリケーション設定
├── server.py                # メインスクリプト
├── requirements.txt         # Python 依存パッケージ
├── setup.sh                 # Linux セットアップスクリプト
└── docs/                    # ドキュメント
    ├── README.md
    ├── ARCHITECTURE.md
    ├── WIFI_SETUP.md
    ├── SETUP_GUIDE.md
    ├── LESSONS_LEARNED.md
    ├── TROUBLESHOOTING.md
    └── ESP32_CODE.md
```

---

## 🔧 トラブルシューティング

**問題が発生した場合：**

1. まず [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) を確認
2. ログを確認：`journalctl -u temperature-server -n 50`
3. 診断スクリプトを実行：[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md#テンプレート問題の原因を特定する)

---

## 📈 プロジェクトの成長

このプロジェクトは、以下の技術を統合しています：

- **Raspberry Pi**: ゲートウェイとして機能
- **USB WiFi ドングル**: デュアル WiFi 対応
- **Flask**: REST API サーバー
- **SQLite**: データ永続化
- **ESP32**: IoT デバイス
- **DS18B20**: 温度測定

---

## 💡 主な特徴

✅ **完全に機能する dual WiFi システム**
- wlan0: 既存ネットワークへの接続（Station モード）
- wlan1: ESP32 用のアクセスポイント（AP モード）

✅ **REST API**
- POST /api/temperature: データ受信
- GET /api/sensors: 最新データ取得
- GET /api/status: システムステータス

✅ **リアルタイム Web ダッシュボード**
- 10秒ごとに自動更新
- 温度グラフ表示

✅ **詳細なドキュメント**
- 7つの包括的なマークダウンドキュメント
- 実例を交えた説明
- 初心者向けガイドから詳細な技術仕様まで

✅ **エラー処理と復旧**
- WiFi 接続管理
- データベースロック対策
- サービス自動再起動

---

## 🎓 学習リソース

このプロジェクトから学べること：

1. **Raspberry Pi 上の dual WiFi セットアップ**
2. **ESP32 の WiFi 接続と HTTP 通信**
3. **Linux ネットワーク設定（dhcpcd, hostapd, dnsmasq）**
4. **Flask による REST API 実装**
5. **SQLite データベースの利用**
6. **systemd サービスの管理**
7. **デバッグとトラブルシューティング**

---

## 🤝 貢献

このプロジェクトが役に立つ場合は、以下をお願いします：

- ⭐ GitHub でスターを付ける
- 🐛 バグを見つけたら Issue を報告
- 💬 改善提案は Discussion で
- 📝 ドキュメントの改善を提案

---

## 📝 ライセンス

MIT License - 詳細は LICENSE ファイルを参照

---

## 👤 作者

**開発者**: IoT 温度監視システム開発チーム

**最終更新**: 2025年12月24日

**サポート**: [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) または Issues を参照

---

## 🔗 関連リンク

- [Raspberry Pi 公式ドキュメント](https://www.raspberrypi.com/documentation/)
- [TP-Link Archer T2U Plus](https://www.tp-link.com/jp/home-networking/usb-adapter/archer-t2u-plus/)
- [ESP32 スペック](https://www.espressif.com/en/products/socs/esp32)
- [Flask ドキュメント](https://flask.palletsprojects.com/)

---

**このドキュメントの読了時間**: 約 3 分

すべてのドキュメントを読了するには約 2-3 時間必要です。段階的に進めることをお勧めします。
