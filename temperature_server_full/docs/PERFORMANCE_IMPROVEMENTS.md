# パフォーマンス改善レポート

## 実施日
2026年1月3日

## 改善概要
ダッシュボードの初期読み込み時間とAPIリクエストの最適化を行いました。

## 実施した改善内容

### 1. 初期読み込みの最適化

#### 問題点
- 初期読み込み時に `/api/sensors` が複数回呼ばれていた（9.88秒、4.10秒など）
- 総読み込み時間が10秒以上かかっていた
- グラフ更新時に無限再試行が発生していた

#### 改善内容
- **プログレッシブローディング**: センサーカードを先に表示し、グラフは後から読み込む
- **重複リクエスト防止**: `getSensorsData()` で進行中のリクエストを共有する仕組みを追加
- **キャッシュTTL延長**: 2秒 → 10秒（5秒ごとの更新に対応）
- **初期化時の重複防止**: `updateChart()` にセンサーデータをパラメータで渡すように変更

### 2. デフォルト設定の変更

#### 変更内容
- **デフォルト時間範囲**: 24時間 → 1時間トレンド
- **間引き**: デフォルトで有効化（`downsamplingEnabled = true`）
- **データポイント制限**: 1時間以下の場合は200ポイントに制限

### 3. エラーハンドリングの改善

#### 問題点
- エラー発生時に無限再試行が発生していた
- 「更新中...」表示が消えない問題があった

#### 改善内容
- **再試行回数の制限**: 最大3回まで再試行
- **早期リターン時のフラグリセット**: `isChartUpdating` を確実にリセット
- **エラーカウントの管理**: 成功時にエラーカウントをリセット

### 4. サーバー側の最適化

#### 問題点
- `/api/temperature/batch` で500エラーが発生していた
- `hours` パラメータが `None` の場合にエラーが発生

#### 改善内容
- **None値の処理**: `hours` が `None` の場合はデフォルト値（24）を使用
- **統計情報の取得をオプション化**: 初期読み込み時は統計情報を取得しない（`include_stats: false`）
- **データポイント制限**: サーバー側でも間引きを強制

## 改善結果

### Before（改善前）
- 初期読み込み時間: 10秒以上
- `/api/sensors` の呼び出し: 複数回（9.88秒、4.10秒など）
- エラー時の動作: 無限再試行
- 500エラー: 頻発

### After（改善後）
- 初期読み込み時間: 約5秒（センサーカードは即座に表示）
- `/api/sensors` の呼び出し: 1回（キャッシュにより重複防止）
- エラー時の動作: 最大3回まで再試行、その後手動更新を促す
- 500エラー: 解消

## 技術的な詳細

### 1. 重複リクエスト防止の実装

```javascript
// 進行中のリクエストを共有
let sensorsDataPromise = null;

async function getSensorsData(forceRefresh = false) {
    // キャッシュが有効な場合は即座に返す
    if (!forceRefresh && cachedSensorsData && (now - lastSensorsUpdate) < SENSORS_CACHE_TTL) {
        return cachedSensorsData;
    }
    
    // 既に進行中のリクエストがあれば、それを待つ
    if (sensorsDataPromise) {
        return await sensorsDataPromise;
    }
    
    // 新しいリクエストを開始
    sensorsDataPromise = (async () => {
        // ... リクエスト処理 ...
        sensorsDataPromise = null; // 完了時にクリア
        return sensorsData;
    })();
    
    return await sensorsDataPromise;
}
```

### 2. プログレッシブローディングの実装

```javascript
// Step 1: センサーリストを取得（高速、先に表示）
const sensorsData = await getSensorsData();
// センサーカードを即座に表示

// Step 2: グラフデータを取得（バックグラウンド、非ブロッキング）
updateChart(sensorsData).then(() => {
    // グラフ表示完了
});
```

### 3. エラー再試行の制限

```javascript
let chartErrorRetryCount = 0;
const MAX_CHART_ERROR_RETRIES = 3;

// エラー時
if (chartErrorRetryCount <= MAX_CHART_ERROR_RETRIES) {
    // 再試行
    chartErrorRetryCount++;
    setTimeout(() => updateChart(), 5000);
} else {
    // 手動更新を促す
    errorMsg.textContent = 'グラフデータの読み込みに失敗しました。更新ボタンをクリックしてください。';
    chartErrorRetryCount = 0; // リセット
}
```

### 4. サーバー側のNone値処理

```python
# hoursがNoneの場合はデフォルト値を使用
hours_value = data.get('hours', 24)
hours = float(hours_value) if hours_value is not None else 24.0
```

## ファイル変更履歴

### 変更されたファイル

1. **`temperature_server/templates/dashboard.html`**
   - プログレッシブローディングの実装
   - 重複リクエスト防止の実装
   - エラーハンドリングの改善
   - デフォルト設定の変更

2. **`temperature_server/app/routes/api.py`**
   - None値の処理
   - 統計情報の取得をオプション化
   - データポイント制限の追加

## 今後の改善案

1. **ネットワーク転送の最適化**
   - Tailscale経由の転送が遅い可能性があるため、レスポンスサイズの削減を検討

2. **データベースクエリの最適化**
   - インデックスの確認と最適化
   - クエリの実行計画の確認

3. **フロントエンドの最適化**
   - Chart.jsの描画最適化
   - データ処理の最適化

## 参考資料

- [CODE_AUDIT_REPORT.md](./CODE_AUDIT_REPORT.md) - コード監査レポート
- [RASPBERRY_PI_INFO_100.x.x.x.md](../../RASPBERRY_PI_INFO_100.x.x.x.md) - ラズパイ情報



