"""
temperature_server/app/routes/dashboard.py
ダッシュボード HTML レンダリングルート + カメラ MJPEG ストリーミング

履歴:
    2026-07-17 監査: カメラ MJPEG 系を削除 (opencv 依存、当時未使用)
    2026-08-11    : USB/CSI カメラ復活のため I:\ 実績実装から復元
                    - /stream            : プレイヤー HTML
                    - /video_feed        : MJPEG バイトストリーム (cv2.VideoCapture(0))
                    - /video_feed/stop   : ストリーム停止
                    - /video_feed/resolution : 360p/720p/1080p 切替

注意:
    - opencv-python (cv2) が必須。venv に `pip install opencv-python-headless` 推奨
    - /dev/video<N> が Linux 側に存在すること (USB UVC カメラ or CSI カメラ)
    - cv2.VideoCapture(0) が /dev/video0 に相当。Trixie の libcamera スタックでは
      USB カメラの device index が動的に変わる可能性あり (別ガイド参照)
"""

from flask import Blueprint, render_template, Response, request, jsonify
from logger import setup_logger
import threading
import time

logger = setup_logger(__name__)
dashboard_bp = Blueprint('dashboard', __name__)

# ---------- カメラ状態 (プロセス全体で共有) ----------
_camera_state = {
    'resolution': (1280, 720),     # デフォルト 720p
    'fps': 30,
    'lock': threading.Lock(),
    'stop_event': threading.Event(),
}


@dashboard_bp.route('/')
def index():
    """ダッシュボードホームページ"""
    return render_template('dashboard.html')


@dashboard_bp.route('/management')
def management():
    """管理画面ページ"""
    return render_template('management.html')


# ============================================================
#  カメラ MJPEG ストリーミング (2026-08-11 復元)
# ============================================================

@dashboard_bp.route('/stream')
def stream():
    """ビデオストリーミングページ"""
    return render_template('stream.html')


@dashboard_bp.route('/video_feed')
def video_feed():
    """ビデオフィード (MJPEG マルチパートストリーム)"""
    try:
        import cv2
    except ImportError:
        logger.error("OpenCV (cv2) がインストールされていません")
        return "Error: OpenCV がインストールされていません (pip install opencv-python-headless)", 500

    # カメラを初期化 (デバイス 0 = 最初のカメラ)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logger.error("カメラを開けません (/dev/video0 が存在するか、"
                     "他プロセスが占有していないか確認)")
        return "Error: カメラが見つかりません", 500

    def generate_frames():
        """MJPEG フレームジェネレータ"""
        frame_count = 0
        last_w, last_h, last_fps = None, None, None
        jpeg_quality = 80

        try:
            while not _camera_state['stop_event'].is_set():
                # 解像度/FPS 変更検知 (毎フレーム set() を叩かない)
                with _camera_state['lock']:
                    w, h = _camera_state['resolution']
                    fps = _camera_state['fps']

                if (w, h, fps) != (last_w, last_h, last_fps):
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                    cap.set(cv2.CAP_PROP_FPS, fps)
                    last_w, last_h, last_fps = w, h, fps
                    logger.info(f"カメラ設定更新: {w}x{h}, {fps}FPS")

                ret, frame = cap.read()
                if not ret:
                    continue

                ret, buffer = cv2.imencode(
                    '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
                )
                if not ret:
                    continue

                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n'
                       b'\r\n' + frame_bytes + b'\r\n')
                frame_count += 1
        except Exception as e:
            logger.error(f"ビデオフィード生成エラー: {e}")
        finally:
            cap.release()
            _camera_state['stop_event'].clear()

    logger.info("ビデオフィード開始")
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@dashboard_bp.route('/video_feed/stop', methods=['GET', 'POST'])
def stop_video_feed():
    """ビデオフィード停止"""
    with _camera_state['lock']:
        _camera_state['stop_event'].set()
    logger.info("ビデオフィード停止リクエスト")
    return jsonify({'status': 'stopped'})


@dashboard_bp.route('/video_feed/resolution', methods=['POST'])
def change_resolution():
    """解像度変更 (360p / 720p / 1080p)"""
    try:
        data = request.get_json()
        if not data or 'resolution' not in data:
            return jsonify({'status': 'error',
                            'message': '解像度が指定されていません'}), 400

        res_str = data['resolution']
        res_map = {
            '360p':  (640, 360),
            '720p':  (1280, 720),
            '1080p': (1920, 1080),
        }
        if res_str not in res_map:
            return jsonify({'status': 'error',
                            'message': '無効な解像度です'}), 400

        with _camera_state['lock']:
            _camera_state['stop_event'].set()
            time.sleep(0.5)   # 既存 generator の停止待ち
            _camera_state['resolution'] = res_map[res_str]
            _camera_state['stop_event'].clear()

        logger.info(f"解像度変更: {res_str} ({res_map[res_str][0]}x{res_map[res_str][1]})")
        return jsonify({'status': 'success', 'resolution': res_str})
    except Exception as e:
        logger.error(f"解像度変更エラー: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
