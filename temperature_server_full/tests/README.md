# テストガイド

## テストの実行方法

### すべてのテストを実行

```bash
cd /home/raspberry/temperature_server
source venv/bin/activate
python -m pytest tests/ -v
```

または

```bash
python -m unittest discover tests -v
```

### 特定のテストファイルを実行

```bash
# バリデーションテストのみ
python -m unittest tests.test_api_validation -v

# エンドポイントテストのみ
python -m unittest tests.test_api_endpoints -v
```

### 特定のテストクラスを実行

```bash
python -m unittest tests.test_api_validation.TestValidateTemperatureRequest -v
```

## テストカバレッジ

テストカバレッジを確認するには：

```bash
pip install coverage
coverage run -m pytest tests/
coverage report
coverage html  # HTMLレポートを生成
```

## テストファイル構成

- `test_api_validation.py`: バリデーション関数のユニットテスト
- `test_api_endpoints.py`: APIエンドポイントの統合テスト

## テスト項目

### バリデーションテスト
- ✅ 正常なリクエストの検証
- ✅ 無効なデータ形式の検証
- ✅ 境界値テスト（最小値・最大値）
- ✅ エラーメッセージの検証

### エンドポイントテスト
- ✅ POST /api/temperature の正常系・異常系
- ✅ GET /api/sensors の正常系
- ✅ GET /api/temperature/<sensor_id> の正常系・異常系
- ✅ GET /api/status の正常系

