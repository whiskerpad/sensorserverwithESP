# Tailscale 導入ガイド (Raspberry Pi 遠隔 SSH)

作成: 2026-08-09
対象: ESPSARVER プロジェクトの Raspberry Pi (`takemetothehospital` / `192.168.11.200`)
目的: 現地 LAN 外 (自宅・外出先・別現場) から Pi に SSH できる状態を作る。

---

## 0. なぜ Tailscale か

現状の Pi は LAN 内 IP `192.168.11.200` でしか SSH できない。外から入るには
「ルータでポート開放して DDNS」といった従来手順が必要で、ルータ管理権限
(この現場では建物側の権限がなく不可) や DDNS 契約が要る。

Tailscale は WireGuard ベースの VPN オーバーレイで、以下が特徴:

- **ルータ側の穴あけ不要** (NAT 越え内蔵、TCP:41641 UDP は使うが outbound のみ)
- **P2P 直結** を試みて、無理なら中継サーバ (DERP) にフォールバック
- **Google 認証で登録**、無料 tier で個人 100 デバイスまで
- Pi の既存 wlan0 (LAN) / wlan1 (ESP 用 AP) にネットワーク的に干渉しない
  (新規に `tailscale0` 仮想 IF を追加するのみ)

## 1. 用意するもの

- Google アカウント (取得済とのこと)
- ブラウザが動く PC (Windows 想定)
- Pi (SSH で LAN 内から入れる状態、この時点では在宅 LAN で作業する想定)
- スマホ (任意、Tailscale アプリで外出先確認に便利)

## 2. Tailscale アカウント作成 (Google 認証)

**ブラウザで作業:**

1. https://login.tailscale.com/start を開く
2. **Sign up with Google** をクリック
3. 保有している Google アカウント (`your-account@example.com`) を選択
4. Google 側の同意画面 → 承認
5. Tailscale 側の初回セットアップ (組織名は個人利用なら Google アカウント名がそのまま `tailnet` 名として設定される)
6. ブラウザで管理コンソール https://login.tailscale.com/admin/machines が開く
   - この画面で全端末を管理する。今はまだ空。

> **Note**: 無料プランは Personal (最大 100 デバイス、3 users)。個人利用ならこのまま。

## 3. Windows PC に Tailscale をインストール

Pi より先に Windows でインストールしておくと、Pi 認証時にすぐ動作確認できる。

**PowerShell (管理者権限は不要、ブラウザからインストーラ DL):**

1. https://tailscale.com/download/windows から `tailscale-setup-<version>.exe` を DL
   (2026-08 時点最新: 1.102.2)
2. `.exe` を実行して普通にインストール
3. インストール後、タスクトレイの Tailscale アイコンをクリック
4. **Log in** → ブラウザが起動し Google 認証 → 完了
5. 管理コンソール https://login.tailscale.com/admin/machines に PC 名 (例
   `desktop-abc123`) が表示されることを確認
6. PowerShell で自分の tailnet 内 IP を確認:
   ```powershell
   tailscale ip -4
   ```
   `100.x.y.z` の IP が返れば OK。

## 4. Pi に Tailscale をインストール

Pi は Debian Trixie (`6.12.75+rpt-rpi-v8`) なので Raspbian Trixie 用リポジトリを使う。

**Pi bash (SSH で入って):**

```bash
ssh pi@192.168.11.200
```

以下を Pi bash で 1 ブロックずつ実行:

```bash
# 1) Tailscale GPG 鍵の設置
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkgs.tailscale.com/stable/raspbian/trixie.noarmor.gpg \
  | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null

# 2) APT リポジトリ登録
curl -fsSL https://pkgs.tailscale.com/stable/raspbian/trixie.tailscale-keyring.list \
  | sudo tee /etc/apt/sources.list.d/tailscale.list

# 3) パッケージ更新 + Tailscale インストール
sudo apt-get update
sudo apt-get install -y tailscale

# 4) tailscaled サービスが有効か確認 (パッケージが自動で enable する)
sudo systemctl status tailscaled --no-pager
```

`tailscaled` の状態が `active (running)` なら OK。

## 5. Pi を tailnet に参加させる (認証)

**Pi bash:**

```bash
sudo tailscale up
```

実行するとコンソールに以下のような URL が出る:

```
To authenticate, visit:

    https://login.tailscale.com/a/xxxxxxxxxxxx
```

**Windows PC のブラウザ** で URL を開く (Pi にはブラウザがないため)。
既に Windows で Google 認証済なので、自動で Tailscale アカウントに紐付けされ、
「このマシンを追加しますか?」の確認画面 → **Connect** で承認。

Pi 側コンソールにプロンプトが戻ればネットワーク参加完了。

**Pi bash で自分の tailnet IP を確認:**

```bash
tailscale ip -4
```

`100.x.y.z` (例: `100.x.x.x`) が返れば OK。

## 6. 接続確認

**Windows PC PowerShell から Pi の tailnet IP に SSH:**

```powershell
ssh pi@100.x.x.x
```

(上記の 100.x.y.z は Pi 実機で出た値に置き換え)

初回のみ ssh フィンガープリント確認 → yes → パスワード → ログインできれば成功。

**tailnet 内のマシン一覧確認 (Pi でも Windows でも):**

```bash
tailscale status
```

以下のように出れば正常:

```
100.x.x.x     takemetothehospital  <you>@       linux    -
100.y.y.y     desktop-abc123       <you>@       windows  active; direct 192.168.11.13:41641, tx 3400 rx 8100
```

## 7. 便利設定 (推奨)

### 7.1 Pi のキー期限を無効化 (Key Expiry Disable)

デフォルトでは各デバイスの鍵は **90 日で期限切れ** になり、再認証が必要。
Pi のような常設サーバでは期限切れで突然接続不能になるのを防ぐため、
Pi のみ期限無効化を推奨。

**ブラウザ (管理コンソール):**

1. https://login.tailscale.com/admin/machines
2. `takemetothehospital` の行の右端「...」メニュー
3. **Disable key expiry** をクリック → 確認

Windows PC は日常的に使うので期限ありのままで問題ない (期限切れ時は
タスクトレイから再ログインするだけ)。

### 7.2 MagicDNS を有効化 (ホスト名で ssh 可能に)

IP を覚えなくても `ssh pi@takemetothehospital` で入れるようになる。

**ブラウザ (管理コンソール):**

1. https://login.tailscale.com/admin/dns
2. **MagicDNS** セクション → **Enable MagicDNS**
3. (推奨) **HTTPS Certificates** は今回は使わないのでオフのまま

有効化後は以下で ssh 可能:

```powershell
ssh pi@takemetothehospital
```

### 7.3 SSH タグ / ACL (任意、今は不要)

個人用途で自分しか使わないなら ACL の初期設定 (全端末互いに疎通可) のまま。
複数ユーザや権限分離が必要になったタイミングで検討する。

### 7.4 SSH 鍵認証への切替え (強く推奨)

パスワード認証は「デフォルトパスワード未変更」警告の温床であり、
ブルートフォースの標的にもなる。tailnet 内部のみのアクセスとはいえ、
**鍵認証に切替えて sshd の PasswordAuthentication を no** にするのが安全。

Tailscale VPN + SSH 鍵の 2 層で守れば、tailnet アカウント (Google) と
Windows PC の秘密鍵の両方が漏れないと侵入できない構成になる。

#### 手順 A: Windows PC で鍵ペアを生成

**PowerShell (管理者不要):**

```powershell
# 既に鍵がある人はスキップ (C:\Users\<user>\.ssh\id_ed25519 の有無を確認)
ssh-keygen -t ed25519 -C "you@your-pc"
```

- 保存先: そのまま Enter (`C:\Users\<user>\.ssh\id_ed25519`)
- パスフレーズ: 任意 (空でも可、tailnet 内なら空でも実用上支障なし)

生成物 2 ファイル:
- `id_ed25519` (秘密鍵、絶対に他人に渡さない)
- `id_ed25519.pub` (公開鍵、Pi に登録する)

#### 手順 B: 公開鍵を Pi の authorized_keys に登録

Windows には `ssh-copy-id` がないので、PowerShell 1 行で送信:

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub `
  | ssh pi@100.x.x.x "mkdir -p -m 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

パスワード入力を求められるので、これが **最後のパスワード認証** になる想定で入力。

#### 手順 C: 鍵認証で入れるか確認

**PowerShell から (パスワード聞かれなければ成功):**

```powershell
ssh pi@100.x.x.x
```

パスフレーズ設定した人はここで聞かれる (パスワードではなく鍵のパスフレーズ)。

**必ず「パスワード聞かれずに入れる」ことを確認してから次に進む。**
ここで確認せずに sshd 側でパスワード無効化すると、鍵が動かなかったときに詰む。

#### 手順 D: sshd でパスワード認証を無効化

**Pi bash (鍵で入ったセッションから):**

```bash
# ドロップイン設定として置く (メイン sshd_config を触らない)
sudo tee /etc/ssh/sshd_config.d/no-password-auth.conf >/dev/null <<'EOF'
# 鍵認証への切替え (2026-08-11)
# 事前に authorized_keys 登録済みの端末以外を弾く
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
EOF

# 設定 syntax チェック (0 なら OK)
sudo sshd -t && echo "SSHD CONFIG OK"

# 反映
sudo systemctl reload ssh
```

#### 手順 E: パスワードでは入れないことを最終確認

**別セッションを開かないまま**、PowerShell からもう 1 度接続:

```powershell
ssh pi@100.x.x.x
```

鍵で問題なく入れば OK。念のためわざとパスワードを試すには:

```powershell
ssh -o PubkeyAuthentication=no pi@100.x.x.x
# → "Permission denied (publickey)." で拒否されれば正常
```

これで **passwd 未変更警告も含めて事実上無害化** できた状態。ただし
`passwd` で LAN 側の物理コンソール用パスワードだけは更新しておくと安心
(物理コンソール等 sshd を経由しないルートでのログインには依然パスワードが要るため)。

#### 補足: 別の Windows PC / スマホからもアクセスしたい場合

各端末で手順 A → B を繰り返す (鍵は端末ごとに個別生成し、`authorized_keys` に
複数行として追記する)。既存端末の秘密鍵を USB で持ち回すのは避ける。

## 8. 既存構成への影響と注意点

### 8.1 wlan0 / wlan1 / hostapd / dnsmasq への影響

Tailscale は物理インターフェースを触らず、`tailscale0` という
仮想 IF (`utun` 相当) を追加するだけ。以下は **影響なし** :

- wlan0 (LAN 側管理接続、`192.168.11.200`)
- wlan1 (AP 側、hostapd で `192.168.4.1`、ESP センサーの POST 受付)
- dnsmasq (wlan1 側 DHCP 予約)
- Flask temperature-server / i2c-lcd-display 等の systemd サービス

### 8.2 tailnet 側から Flask ダッシュボードを見る (副次的な便利機能)

同じ tailnet に居る PC のブラウザから直接:

```
http://takemetothehospital:5000/
http://100.x.x.x:5000/
```

でダッシュボードが開ける (Flask は 0.0.0.0 で listen しているため)。

### 8.3 ESP センサー側からは Tailscale IP は見えない

ESP は wlan1 AP `192.168.4.1` にしか繋がっていないので、tailnet の
100.x.y.z アドレスは到達不可。これは仕様通りで問題ない (センサー POST 経路は変わらず)。

### 8.4 セキュリティ上の注意

- Tailscale IP は tailnet 内 (自分の Google アカウントに紐付いた端末群) からしか到達不可。インターネット全体には公開されない。
- ただし tailnet に招待した他ユーザは疎通できる。個人利用なら他人を招待しないこと。
- Google アカウントの 2 段階認証を必ず有効化しておく (tailnet アクセスの根本的な鍵になるため)。
- **前回未対応の警告**: `pi` ユーザのパスワードがデフォルトのまま。SSH ログイン時に警告が出ている:
  ```
  SSH is enabled and the default password for the 'pi' user has not been changed.
  ```
  Tailscale 有効化で外部から届きうる状態になるので、この機会に:
  ```bash
  passwd
  ```
  で必ず変更しておく。

## 9. トラブルシューティング

### 9.1 `sudo apt-get install tailscale` で 404

リポジトリ登録 (手順 4-2) の URL が Trixie 用になっているか確認:
```bash
cat /etc/apt/sources.list.d/tailscale.list
# → deb ... trixie main   の行があるはず
```

### 9.2 認証 URL を開いても何も起きない

`sudo tailscale up --reset` で再試行。または既に別アカウントに紐付いている可能性 → `sudo tailscale logout` してから再度 `up`。

### 9.3 `tailscale ip -4` で IP が返らない

デーモン起動失敗の可能性:
```bash
sudo systemctl status tailscaled
sudo journalctl -u tailscaled -n 50 --no-pager
```

### 9.4 Windows から Pi に ssh できない (Timeout)

- Windows PC 側で `tailscale status` を実行し、Pi 行に `active` または `direct/relay` が出ているか確認
- 出ていない → 両方が同じ tailnet か管理コンソールで再確認
- 出ている → 通常の ssh 側の問題 (Pi の sshd が動いているか、パスワード誤り等)

### 9.5 sshd が `Timeout before authentication` で切断される (実際に起きた症状)

**症状**: `ssh pi@<tailnet-ip>` でパスワード入力後 (or 入力前) にサーバから
`Connection closed by <ip> port 22` で切断され、Pi 側 `journalctl -u ssh` に
`Timeout before authentication for connection from <tailnet-ip>` が残る。

**原因**: sshd が接続元 IP (100.x.y.z) の逆引き DNS ルックアップを試み、
MagicDNS 未有効・PTR レコード未登録のためタイムアウト待ち → 120 秒経過で
sshd 側が LoginGraceTime で切断。

**対策 A** (即効、5 秒で解決): sshd で逆引きを無効化

```bash
echo "UseDNS no" | sudo tee -a /etc/ssh/sshd_config.d/no-usedns.conf
sudo systemctl reload ssh
```

**対策 B** (根本): MagicDNS を有効化 (§7.2 参照)。以降 tailnet 内で PTR も引けるようになる。

対策 A は無条件で入れておいて損はない (逆引きに依存しないポリシーは
セキュリティ上も推奨されている)。

### 9.6 P2P できず DERP 中継 (relay) になる

`tailscale status` の Pi 行に `relay "tokyo"` などが出る場合、UDP が塞がれている環境。
機能上は動くが遅延が大きい (~50-150ms 追加)。SSH 用途なら実用上問題なし。
気になる場合はルータの UDP outbound を許可するか、`--advertise-exit-node` 等の高度設定を検討 (本ガイド範囲外)。

## 10. アンインストール手順 (念のため記録)

将来 Tailscale をやめる場合:

**Pi bash:**

```bash
# 1) 停止と離脱
sudo tailscale down
sudo tailscale logout

# 2) パッケージ削除
sudo apt-get purge -y tailscale
sudo rm -f /etc/apt/sources.list.d/tailscale.list
sudo rm -f /usr/share/keyrings/tailscale-archive-keyring.gpg
sudo apt-get update
```

**ブラウザ (管理コンソール):**

- https://login.tailscale.com/admin/machines で対象マシンを Delete
- 全端末削除後、アカウント自体を削除したい場合は Settings → Account → Delete

## 11. 付録: スマホ (iOS / Android) からも接続

外出先で緊急対応する用途にはスマホの Tailscale アプリが便利。

- App Store / Google Play で "Tailscale" 検索してインストール
- 起動 → Google でログイン (Pi と同じアカウント)
- 追加後、スマホの ssh クライアント (Termius など) から
  `pi@takemetothehospital` または `pi@100.x.y.z` で接続可能

現地の LCD 表示異常を出張先で確認、systemd 再起動、といった対処ができるようになる。

## 12. 検証チェックリスト (完了時に上から順に確認)

- [ ] Tailscale 管理コンソールに Google 認証でログインできる
- [ ] Windows PC で `tailscale ip -4` が `100.x.y.z` を返す
- [ ] Pi の `tailscaled` が `active (running)`
- [ ] Pi で `tailscale ip -4` が `100.x.y.z` を返す
- [ ] Windows PC から `ssh pi@<Pi の 100.x.y.z>` でログインできる
- [ ] (任意) MagicDNS 有効化後 `ssh pi@takemetothehospital` でログインできる
- [ ] (任意) 別ネットワーク (スマホテザリング等) の Windows PC からも接続できる
- [ ] Pi の `pi` ユーザパスワードを変更した
- [ ] 管理コンソールで Pi のキー期限を Disable にした
- [ ] Flask ダッシュボードが `http://takemetothehospital:5000/` で開ける

---

## 参考リンク

- Tailscale 公式 Debian/Raspbian: https://tailscale.com/kb/1174/install-debian-bookworm (Trixie も類似手順)
- パッケージ一覧: https://pkgs.tailscale.com/stable/
- MagicDNS: https://tailscale.com/kb/1081/magicdns
- Key expiry: https://tailscale.com/kb/1028/key-expiry
