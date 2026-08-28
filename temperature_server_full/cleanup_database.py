#!/usr/bin/env python3
"""
データベースのダミーデータを削除するスクリプト
本番データのみを残します
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database.models import get_connection

def cleanup_dummy_data():
    """ダミーデータを削除"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # ダミーデータのsensor_idリスト（必要に応じて変更）
    dummy_sensor_ids = ['test', 'TEST', 'TEST_02', 'Unknown']
    
    print("=" * 50)
    print("データベースクリーンアップ")
    print("=" * 50)
    
    # 削除前のデータ数を確認
    cursor.execute("SELECT COUNT(*) FROM temperatures")
    total_before = cursor.fetchone()[0]
    print(f"\n削除前の総データ数: {total_before}")
    
    # ダミーデータを削除
    deleted_count = 0
    for sensor_id in dummy_sensor_ids:
        cursor.execute("SELECT COUNT(*) FROM temperatures WHERE sensor_id = ?", (sensor_id,))
        count = cursor.fetchone()[0]
        if count > 0:
            cursor.execute("DELETE FROM temperatures WHERE sensor_id = ?", (sensor_id,))
            deleted_count += cursor.rowcount
            print(f"  - {sensor_id}: {count}件を削除")
    
    # 異常値（99.9°Cなど）を持つデータも削除（オプション）
    cursor.execute("SELECT COUNT(*) FROM temperatures WHERE temperature > 50 OR temperature < -10")
    abnormal_count = cursor.fetchone()[0]
    if abnormal_count > 0:
        cursor.execute("DELETE FROM temperatures WHERE temperature > 50 OR temperature < -10")
        deleted_count += cursor.rowcount
        print(f"  - 異常値データ: {abnormal_count}件を削除")
    
    conn.commit()
    
    # 削除後のデータ数を確認
    cursor.execute("SELECT COUNT(*) FROM temperatures")
    total_after = cursor.fetchone()[0]
    
    print(f"\n削除後の総データ数: {total_after}")
    print(f"削除したデータ数: {deleted_count}")
    
    # 残っているセンサーを表示
    cursor.execute("SELECT DISTINCT sensor_id, sensor_name FROM temperatures ORDER BY sensor_id")
    remaining_sensors = cursor.fetchall()
    print(f"\n残っているセンサー:")
    for sensor_id, sensor_name in remaining_sensors:
        cursor.execute("SELECT COUNT(*) FROM temperatures WHERE sensor_id = ?", (sensor_id,))
        count = cursor.fetchone()[0]
        print(f"  - {sensor_id} ({sensor_name}): {count}件")
    
    conn.close()
    print("\n" + "=" * 50)
    print("クリーンアップ完了！")
    print("=" * 50)

if __name__ == '__main__':
    try:
        cleanup_dummy_data()
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

