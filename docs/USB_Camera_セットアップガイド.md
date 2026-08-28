# USB カメラセットアップガイド (Raspberry Pi + Flask MJPEG ストリーミング)

作成: 2026-08-12
対象: temperature_server の `/stream` `/video_feed` ルート用
検証済ハード: ELECOM 2MP Webcam (UVC 1.00、`ID 056e:701a`)
検証済 OS: Raspberry Pi OS Trixie (kernel 6.12.75)

---

## 0. 前提

- USB カメラは UVC (USB Video Class) 準拠であること
  - 大半の Web カメラは UVC 準拠。非 UVC 品 (メーカ独自ドライバ必須品) は避ける
- Raspberry Pi の USB ポートに直挿し推奨
  - セルフパワー USB ハブ経由でも可 (Pi 側 USB からの電流不足で enumerated but not initialized を起こすカメラがあるため)
- `temperature_server` (Flask) が既に動作していること

## 1. カメラ認識確認

**Pi bash:**

```bash
# 1) USB 層で見えているか
lsusb | grep -i "cam\|webcam\|uvc"

# 2) uvcvideo モジュールが動いているか
lsmod | grep uvc

# 3) v4l2 に capture デバイスとして登録されているか
v4l2-ctl --list-devices
```

**期待結果**:
- `lsusb` にカメラのベンダー名 (例: `Elecom Co., Ltd ELECOM 2MP Webcam`)
- `lsmod` に `uvcvideo` の行
- `v4l2-ctl --list-devices` に USB カメラ名 + `/dev/video0` `/dev/video1` (0 = 映像、1 = メタデータ)

**capture デバイスが 1 個も見えない場合**:

```bash
sudo modprobe uvcvideo
sleep 2
v4l2-ctl --list-devices
```

これで `/dev/video0` が現れれば OK。それでも出ない場合は USB 電力不足を疑って、
セルフパワー USB ハブに移すか、Pi の別ポートに差し替えて再確認。

## 2. cv2 動作テスト (Flask を経由しない)

`temperature_server` の venv に入って直接テスト:

```bash
cd /home/pi/temperature_server
./venv/bin/python3 -c "
import cv2, numpy
print('numpy:', numpy.__version__, 'cv2:', cv2.__version__)
cap = cv2.VideoCapture(0)
print('isOpened:', cap.isOpened())
if cap.isOpened():
    ret, frame = cap.read()
    print('read:', ret, 'shape:', frame.shape if ret else 'N/A')
cap.release()
"
```

**期待**:
```
numpy: 2.5.2 cv2: 4.10.0.84
isOpened: True
read: True shape: (720, 1280, 3)
```

## 3. よくあるエラー

### 3.1 `ImportError: numpy.core.multiarray failed to import`

opencv-python-headless が NumPy 1.x 系でビルドされており、venv 内の NumPy 2.x
と ABI 非互換。**必ず opencv-python-headless>=4.10.0.84 を使う**。

**修正**:
```bash
cd /home/pi/temperature_server
./venv/bin/pip install --upgrade "opencv-python-headless>=4.10.0.84"
sudo systemctl restart temperature-server
```

### 3.2 `cv2.VideoCapture(0).isOpened() == False`

原因の切り分け:

| 症状 | 原因 | 対処 |
|---|---|---|
| `/dev/video0` が存在しない | uvcvideo 未ロード or カメラ未認識 | §1 の modprobe / lsusb 再確認 |
| `/dev/video0` はあるが Permission denied | 実行ユーザが `video` グループ非所属 | `sudo usermod -aG video pi` → 再ログイン |
| 別プロセスが `/dev/video0` を占有 | v4l2 は同時 1 プロセスのみ | `sudo fuser -v /dev/video0` で犯人特定 |
| カメラは USB として見えるが v4l2 なし | ハブ電力不足 or カメラ故障 | セルフパワーハブ / 別カメラで検証 |

### 3.3 ブラウザで「カメラに接続できませんでした」表示

`/video_feed` が 500 応答を返している。Flask ログを見ればわかる:

```bash
sudo journalctl -u temperature-server -f
```

同時に別セッションで `/video_feed` を叩く:

```bash
curl -v http://localhost:5000/video_feed --max-time 3 2>&1 | head -30
```

ログの `カメラを開けません` などのメッセージが原因を直接示す。

### 3.4 systemd 経由と手動起動で挙動が違う

pi ユーザが `video` グループに入っていても、systemd unit の `User=` が別ユーザ
だとそちらに権限が必要。unit を確認:

```bash
sudo systemctl cat temperature-server | grep -E "^User="
# → User=pi なら OK
```

## 4. cv2.VideoCapture のインデックスと /dev/videoN の対応

**注意**: cv2 の `VideoCapture(0)` は必ずしも `/dev/video0` を開くわけではない。
多くの環境では以下の対応:

| cv2 index | /dev/videoN | 内容 |
|---|---|---|
| 0 | `/dev/video0` | 最初に見つかった capture デバイス |
| 1 | `/dev/video1` | 2 番目 |

Raspberry Pi では bcm2835-isp や bcm2835-codec が先に登録され `/dev/video10-31`
を占有、その後 USB カメラが `/dev/video0` `/dev/video1` に付く典型。
このとき `cv2.VideoCapture(0)` が意図通り USB カメラを開く。

**確認方法** (venv 内):

```python
import cv2
for i in range(4):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"index {i}: {w}x{h} OK")
    cap.release()
```

USB カメラが index 0 以外に来る環境の場合は `app/routes/dashboard.py` の
`cv2.VideoCapture(0)` の数字を該当インデックスに書換える。

## 5. パフォーマンス調整

デフォルトは 720p / 30fps / JPEG quality 80。Pi 4 で問題なく動くが、
Pi Zero や無線帯域が狭い環境では以下を調整:

- **解像度**: ブラウザの `/stream` ページから 360p/720p/1080p 切替可能
- **JPEG quality**: `app/routes/dashboard.py` の `jpeg_quality = 80` を下げる
  (60 まで下げると帯域約 2/3 に、画質は目視でわずかに粗くなる程度)
- **fps**: `_camera_state['fps']` を下げる (20fps 前後で滑らかさ維持)

## 6. 自動起動の永続化

Trixie では `uvcvideo` は必要時に自動ロードされるので特別な設定は不要。
ただし念のため boot 時に強制ロードしたい場合:

```bash
echo "uvcvideo" | sudo tee /etc/modules-load.d/uvcvideo.conf
```

## 7. 検証チェックリスト

- [ ] `lsusb` に USB カメラのベンダー名が出る
- [ ] `lsmod | grep uvc` で uvcvideo モジュールが表示される
- [ ] `v4l2-ctl --list-devices` に USB カメラと `/dev/video0` が出る
- [ ] `./venv/bin/python3 -c "import cv2; ..."` で `isOpened: True` + フレーム取得
- [ ] `curl http://localhost:5000/video_feed` で MJPEG バイトが流れる
- [ ] ブラウザ `http://<Pi-IP>:5000/stream` で 720p 映像表示
- [ ] 解像度切替 (360p/720p/1080p) が動作する
- [ ] `passwd` / Tailscale などで外部からもアクセスできる (該当ガイド参照)

## 8. 関連ドキュメント

- `docs/RaspberryPi_セットアップガイド.md` — Pi 全体セットアップ
- `docs/Tailscale_導入ガイド.md` — 外部アクセス
- `temperature_server_full/README.md` — Flask 側の詳細
