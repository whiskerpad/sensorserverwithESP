# コード監査レポート
## dashboard.html と database/queries.py の変更監査

監査日: 2024年
監査対象:
- `temperature_server/templates/dashboard.html`
- `temperature_server/database/queries.py`
- `temperature_server/database/models.py`

**✅ 修正完了**: すべての重大・中程度の問題を修正しました（2024年）

---

## 🔴 重大な問題（✅ 修正済み）

### 1. XSS（クロスサイトスクリプティング）脆弱性 - dashboard.html

**場所**: `dashboard.html` の複数箇所

**修正内容**: HTMLエスケープ関数 `escapeHtml()` を追加し、すべてのユーザー入力箇所で適用しました。

**問題点**:
```562:574:temperature_server/templates/dashboard.html
            return `
                <div class="card">
                    <h3>${sensor.sensor_name || sensor.sensor_id}</h3>
                    <div class="temp-display">${sensor.temperature.toFixed(1)}°C</div>
                    <div class="sensor-info">
                        <p><strong>センサーID:</strong> ${sensor.sensor_id}</p>
                        <p><strong>最終更新:</strong> ${timeStr}</p>
                        ${sensor.humidity ? `<p><strong>湿度:</strong> ${sensor.humidity.toFixed(1)}%</p>` : ''}
                        ${sensor.rssi ? `<p><strong>WiFi信号:</strong> ${sensor.rssi} dBm ${signalBars}</p>` : ''}
                        <p><strong>電源:</strong> ${batteryIcon}</p>
                    </div>
                </div>
            `;
```

`sensor.sensor_name` と `sensor.sensor_id` がそのままHTMLに挿入されています。悪意のあるセンサー名（例: `<script>alert('XSS')</script>`）が挿入された場合、XSS攻撃が可能です。

**影響度**: 高（データベースに保存されたセンサー名がそのまま表示される）

**修正実装**:
```javascript
// HTMLエスケープ関数を追加（実装済み）
function escapeHtml(text) {
    if (text == null || text === undefined) {
        return '';
    }
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}
```

**修正箇所**:
- ✅ `createSensorCard` 関数内のセンサー名・ID・時刻
- ✅ `createMinimalSensorCard` 関数内のセンサー名・時刻
- ✅ アラート表示内のセンサー名・時刻
- ✅ リアルタイム更新時の時刻表示

---

## 🟡 中程度の問題（✅ 修正済み）

### 2. SQLインジェクション対策は良好だが、入力検証が不十分 - queries.py

**場所**: `queries.py` の `get_range_batch` メソッド

**現状**: プレースホルダーを使用しているため、SQLインジェクション自体は防げています。

```138:147:temperature_server/database/queries.py
            # プレースホルダーを生成
            placeholders = ','.join(['?' for _ in sensor_ids])
            
            # 全データを取得（間引きはPython側で実施）
            query = f"""
                SELECT * FROM temperatures 
                WHERE sensor_id IN ({placeholders}) AND timestamp >= ?
                ORDER BY sensor_id, timestamp ASC
            """
            cursor.execute(query, tuple(sensor_ids) + (since,))
```

**問題点**:
- `sensor_ids` の型チェックが不十分（API側でチェックしているが、直接呼び出された場合に脆弱）
- `sensor_id` の形式検証がない（空文字列、非常に長い文字列など）

**修正実装**: ✅ 完了
- `sensor_ids` の型チェック（list/tuple）
- 各 `sensor_id` の文字列検証（空文字列・長さ制限100文字）
- `hours` の範囲検証（0 < hours <= 8760）
- `max_points_per_sensor` の範囲検証（1 <= max_points <= 10000）
- 検証済みのIDのみを使用してクエリ実行

---

### 3. エラーハンドリングの改善 - dashboard.html（✅ 修正済み）

**修正内容**: `updateChart()` 関数にエラー表示と自動再試行機能を追加しました。

**修正実装**:
- エラー発生時にユーザーに視覚的なフィードバックを表示
- 5秒後に自動的に再試行
- エラーメッセージの適切なスタイリング

---

### 4. メモリリークの可能性 - dashboard.html

**場所**: `dashboard.html` のキャッシュ管理

**問題点**:
```612:651:temperature_server/templates/dashboard.html
        // ラベルフォーマット関数（期間に応じた表示形式、最適化）
        const formatLabelCache = new Map();
        function formatLabel(date, hours) {
            const cacheKey = `${date.getTime()}-${hours}`;
            if (formatLabelCache.has(cacheKey)) {
                return formatLabelCache.get(cacheKey);
            }
            
            let formatted;
            if (hours <= 1) {
                formatted = date.toLocaleTimeString('ja-JP', { 
                    hour: '2-digit', minute: '2-digit', second: hours <= 0.5 ? '2-digit' : undefined,
                    timeZone: 'Asia/Tokyo'
                });
            } else if (hours <= 24) {
                formatted = date.toLocaleTimeString('ja-JP', { 
                    hour: '2-digit', minute: '2-digit',
                    timeZone: 'Asia/Tokyo'
                });
            } else if (hours <= 168) {
                formatted = date.toLocaleString('ja-JP', { 
                    month: '2-digit', day: '2-digit',
                    hour: '2-digit', minute: '2-digit',
                    timeZone: 'Asia/Tokyo'
                });
            } else {
                formatted = date.toLocaleDateString('ja-JP', { 
                    month: '2-digit', day: '2-digit',
                    timeZone: 'Asia/Tokyo'
                });
            }
            
            // キャッシュサイズを制限（メモリリーク防止）
            if (formatLabelCache.size > 1000) {
                const firstKey = formatLabelCache.keys().next().value;
                formatLabelCache.delete(firstKey);
            }
            formatLabelCache.set(cacheKey, formatted);
            return formatted;
        }
```

キャッシュサイズ制限はありますが、LRU（Least Recently Used）方式ではなく、最初のエントリを削除する方式です。頻繁に使用されるラベルが削除される可能性があります。

**推奨修正**: LRUキャッシュの実装、またはタイムベースのキャッシュクリア

---


---

## 🟢 軽微な問題・改善提案

### 5. 間引きアルゴリズムの効率性 - queries.py

**場所**: `queries.py` の `get_range_batch` メソッド

**現状**:
```160:172:temperature_server/database/queries.py
            # さらにPython側で間引き（データベース側の間引きが不十分な場合）
            for sensor_id in results:
                if len(results[sensor_id]) > max_points_per_sensor:
                    # 均等に間引き（最初と最後は必ず含める）
                    original = results[sensor_id]
                    step = len(original) / max_points_per_sensor
                    downsampled = [original[0]]  # 最初のポイント
                    for i in range(1, len(original) - 1):
                        if int(i / step) != int((i - 1) / step):
                            downsampled.append(original[i])
                    if len(original) > 1:
                        downsampled.append(original[-1])  # 最後のポイント
                    results[sensor_id] = downsampled
```

**問題点**: 単純な均等間引きのため、重要なデータポイント（最大値・最小値・急激な変化）が失われる可能性があります。

**改善提案**: dashboard.html の `downsampleData` 関数と同様のロジックをサーバー側にも実装するか、サーバー側でより高度な間引きを実施。

---

### 6. タイムゾーン処理の一貫性 - queries.py（✅ 修正済み）

**修正内容**: すべてのタイムゾーン処理を明示的にJSTタイムゾーンを使用するように変更しました。

**修正箇所**:
- ✅ `insert_reading()` - データ挿入時のタイムスタンプ
- ✅ `get_range()` - 時間範囲取得
- ✅ `get_statistics()` - 統計計算
- ✅ `get_range_batch()` - バッチ取得
- ✅ `delete_old_records()` - 古いデータ削除
- ✅ `cleanup_old_logs()` - ログ削除

すべてのメソッドで `datetime.now(JST)` を使用するように統一しました。

---

### 7. データベース接続のリソース管理 - queries.py（✅ 修正済み）

**修正内容**: すべてのメソッドで `try-finally` ブロックを使用し、例外発生時でも確実に接続を閉じるようにしました。

**修正箇所**:
- ✅ `insert_reading()`
- ✅ `get_latest_reading()`
- ✅ `get_all_latest()`
- ✅ `get_range()`
- ✅ `get_statistics()`
- ✅ `get_range_batch()`
- ✅ `insert_log()`
- ✅ `get_recent_logs()`
- ✅ `cleanup_old_logs()`
- ✅ `delete_old_records()`
- ✅ `delete_test_sensors()`

すべてのメソッドで `try-finally` ブロックを追加し、リソースリークを防止しました。

---

### 8. パフォーマンス最適化の余地 - dashboard.html

**改善提案**:
- グラフ更新のデバウンス時間を調整可能にする（現在は100ms固定）
- センサー数が多い場合の表示最適化（仮想スクロールなど）
- Web Worker を使用してデータ処理をバックグラウンドで実行

---

## ✅ 良好な点

1. **SQLインジェクション対策**: プレースホルダーを適切に使用
2. **スレッドセーフティ**: `db_lock` を使用してデータベースアクセスを保護
3. **パフォーマンス最適化**: バッチAPI、キャッシュ、間引き処理を実装
4. **エラーログ**: 適切なログ記録
5. **インデックス**: データベースに適切なインデックスを設定

---

## 📋 優先度別の修正推奨事項

### 優先度: 高（即座に修正すべき）✅ 完了
1. ✅ XSS脆弱性の修正（dashboard.html）
2. ✅ 入力検証の強化（queries.py）

### 優先度: 中（次回リリースまでに修正）✅ 完了
3. ✅ エラーハンドリングの改善（dashboard.html）
4. ✅ タイムゾーン処理の明示化（queries.py）
5. ✅ データベース接続のリソース管理改善（queries.py）

### 優先度: 低（改善の余地あり）✅ 完了
6. ✅ 間引きアルゴリズムの改善（queries.py - 最大値・最小値・急激な変化を保持）
7. ✅ メモリ管理の最適化（dashboard.html - LRUキャッシュの実装）
8. ✅ パフォーマンスのさらなる最適化（dashboard.html - デバウンス調整、重複リクエスト防止、不要なDOM操作削減）

---

## 📝 まとめ

**✅ 修正完了**: すべての重大・中程度の問題を修正しました。

### 修正内容サマリー

1. **XSS脆弱性対策**: HTMLエスケープ関数を追加し、すべてのユーザー入力箇所で適用
2. **入力検証強化**: `get_range_batch()` メソッドに包括的な入力検証を追加
3. **エラーハンドリング改善**: グラフ更新時のエラー表示と自動再試行機能を追加
4. **タイムゾーン処理の統一**: すべてのタイムゾーン処理を明示的にJSTに統一
5. **リソース管理改善**: すべてのデータベース接続で `try-finally` ブロックを使用

### 追加で実装した改善（優先度: 低）✅ 完了

1. **間引きアルゴリズムの改善**:
   - `_downsample_temperature_data()` 関数を追加
   - 最大値・最小値・急激な変化（0.5°C以上）を保持
   - タイムスタンプでソートして順序を保証

2. **LRUキャッシュの実装**:
   - `LRUCache` クラスを実装
   - `formatLabelCache` をLRUキャッシュに変更
   - 最も使用頻度の低いエントリを自動削除

3. **パフォーマンス最適化**:
   - グラフ更新のデバウンス時間を調整可能に（`setChartDebounceDelay()`）
   - 重複リクエストの防止（`isChartUpdating` フラグ）
   - 不要なDOM操作の削減（値が変更された場合のみ更新）
   - センサーカードの再生成を最適化（センサー数・IDが変更された場合のみ）

### 実装詳細

#### 間引きアルゴリズム（queries.py）
- 最大値・最小値を検出して保持
- 急激な変化（0.5°C以上）を検出して保持
- 残りのポイントを均等に間引き
- 最初と最後のポイントは必ず含める

#### LRUキャッシュ（dashboard.html）
- 最大サイズ1000エントリ
- アクセスされたエントリを最後に移動
- 最大サイズ超過時に最も古いエントリを削除

#### パフォーマンス最適化（dashboard.html）
- デバウンス時間: デフォルト100ms（0-1000msで調整可能）
- 重複リクエスト防止: 更新中のリクエストをキューに追加
- DOM操作最適化: 値が変更された場合のみ更新
- センサーカード最適化: センサー数・IDが変更された場合のみ再生成

コードの品質、セキュリティ、パフォーマンスが大幅に向上しました。

