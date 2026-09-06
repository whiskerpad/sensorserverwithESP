# ARCHIVE — 廃止・レガシー資産

このリポジトリは反復開発の産物のため、途中で作って別実装に置き換わったコード
や、ハードウェア故障で退役したモジュール向けコードが残存している。
**新規に組む人・公開版利用者は本ファイル記載のフォルダには触らなくてよい。**

canonical (実装として採用中) の一覧はトップ `README.md` 参照。

---

## Flask サーバー

| フォルダ | 状態 | 経緯 |
|---|---|---|
| `temperature_server_full/` | ★**canonical (使用中)** | I:\ 実績版をベースに監査・整理した本命実装。`install.sh` で venv + systemd 一括導入。 |
| `temperature_server/` | 廃止 | 独自書き起こしの中間版。方針 P (I:\ 既存実装ベース採用) で不採用。参考程度に残置。 |
| `temperature_server_deploy/` | 一部参考 | 過去のデプロイ用 PowerShell スクリプト群 (deploy_cleanup.ps1 等)。手動デプロイの参考のみ。canonical は `temperature_server_full/install.sh`。`dnsmasq_mac_reservation.md` は 2026-09-03 に方式D へ移行したため **非採用**。DHCP 予約手法の参考資料として残す。 |

## ESP スケッチ

| フォルダ | 状態 | 経緯 |
|---|---|---|
| `ESP8266_DS18B20_HTTPPOST/` | 廃止 | 最初の DHCP 版 STEP 2。DeepSleep + 方式D (MAC 由来静的 IP) 採用で不採用。 |
| `ESP8266_DS18B20_Serial/` | 廃止 | 初期の Serial 送信版。WiFi POST 化で退役。 |
| `ESP8266_ESPNOW_Sensor/` | 誤配置 | 実態は WiFi POST 旧版。ファイル自体は stub 化済み。 |
| `ESP32C3_ESPNOW_Battery_Sensor/` | canonical | XIAO ESP32-C3 の ESP-NOW + DeepSleep 電池版。I:\ 実績スケッチベース。 |
| その他 `ESP8266_DeepSleep_FixedIP_Sensor*` | canonical | 本番用 (`_debug` はシリアル、`_LED` は現地診断)。 |
| `ESP32_DS18B20_WiFi/`, `ESP32_DS18B20_WiFi_Battery/` | canonical | ESP32 WROOM-DA の WiFi 直接 POST 版。 |
| `ESP32_ESPNOW_Master/`, `ESP32_ESPNOW_Sensor/`, `ESP32C3_XIAO_DS18B20_WiFi/` | canonical | 現行使用中。 |
| `ESP_MAC_Address_Getter/` | ユーティリティ (現役) | dnsmasq 予約用の MAC 取得。 |

## 現地表示器

| フォルダ | 状態 | 経緯 |
|---|---|---|
| `i2c_lcd_display/` | ★**canonical (使用中)** | HD44780 20x4 I2C LCD。半角カナ + CGRAM アイコン + RSSI↔経過時間交互表示。 |
| `nokia5110_display/` | 廃止 | Nokia 5110 SPI 版。バックライトはんだ不良 + 表示ハード自体の故障で退役。コードは歴史記録として残置 (現在の Pi にはインストール済でない)。 |

## ドキュメント

`temperature_server_full/docs/` 配下は開発期の履歴目的が多く、公開版としては
必須ではない。以下は参考価値のみ:

| ファイル | 種別 |
|---|---|
| `AUDIT_20260717.md` | 2026-07-17 監査ログ (削除 / 保留の記録) |
| `CODE_AUDIT_REPORT.md` | 同上、別視点 |
| `PERFORMANCE_IMPROVEMENTS.md` | 過去のパフォーマンス改善記録 |
| `CHANGE_LOG.md` | 内部変更履歴 |
| `DIAGNOSE_WIFI_ISSUE.md`, `TROUBLESHOOTING_WIFI_AP_SETUP.md` | AP 構築時のトラブル記録 |
| `MAC_ADDRESS_EXPLANATION.md` | canonical は `docs/デバイス識別設計.md` に集約済 |
| `esp_devices/*.md` | ESP 実装解説 (現役、外部利用者は参考可) |

公開版利用者が最初に読むのは `outputs/docs/` 配下と、各コンポーネントの `README.md`。

## 過去のセッションゴミ

- `_synctest*.txt` (もしあれば) — セッション同期確認用の一時ファイル。削除して問題なし。

## 完全削除の判断

「レガシー」に分類されているものも、以下の理由で **物理削除はしていない**:

1. Arduino IDE でスケッチパスを開いていた履歴が壊れないように
2. 過去の記事・ブログ連載で参照される可能性 (ユーザ本人が執筆中)
3. どこかで動作していたコードは、後から比較参照する価値がある

公開時に強く「消したい」なら、フォルダごと git 履歴を残したまま削除する方針を
別途検討。
