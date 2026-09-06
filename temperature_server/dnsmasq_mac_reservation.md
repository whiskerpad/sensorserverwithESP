# dnsmasq MAC 固定割当ガイド (静的IP と DHCP の衝突予防)

> ## ⚠️ このドキュメントは現在の本番構成では採用していません
>
> 本プロジェクトのネットワーク層は **方式D (ESP 側が MAC から IP を算出して静的宣言)**
> に切り替えました。ESP センサーノードに `dhcp-host=` の予約は使いません。
>
> | 範囲 | 用途 |
> |---|---|
> | `192.168.4.1` | Pi 自身 (wlan1、ゲートウェイ) |
> | `192.168.4.100` 〜 `.227` | ESP センサーノード (ESP が `100 + (mac[5] & 0x7F)` で自己宣言) |
> | `192.168.4.228` 〜 `.254` | DHCP プール (スマホ・PC 等の一時接続) |
>
> **切替理由:** DeepSleep 運用では起きるたびに DHCP 折衝
> (DISCOVER/OFFER/REQUEST/ACK) が入り、予約があっても往復回数は減りません。
> 電波状況が悪いとリトライで伸び、そのぶん Wi-Fi の通電時間 = 電池消費が増えます。
> 静的宣言なら折衝そのものが無くなり、加えて **新チップ追加時に Pi 側を触る必要が
> なくなります**。
>
> 現行の設計は `outputs/docs/デバイス識別設計.md` を参照してください。
> 本ファイルは **DHCP 予約という手法の参考資料**として残しています。
> 記載の `dhcp-range=192.168.4.100,192.168.4.199` は現行のアドレス設計と衝突するので、
> そのまま適用しないでください。

---

## 目的

ESP8266 スケッチは `WiFi.config(fixedIP, gateway, subnet)` でクライアント側から 192.168.4.208 のような固定 IP を主張する。
一方で Raspberry Pi の AP (dnsmasq) は 192.168.4.2 - 192.168.4.254 の範囲を DHCP プールとして持っている。

**問題**: DHCP プール内の IP が別の一時的なクライアント (スマホ等) に先に貸し出された場合、
その後 ESP8266 が起動しても、既に別のホストに 192.168.4.208 が割り当てられていて衝突する。
ESP8266 側は `WiFi.config` を先に呼んでいても、AP 側が別の MAC に対して同じ IP を維持していると
2 台に同じ IP が存在する状態になる。

**対処**: dnsmasq の `dhcp-host` オプションで **「この MAC アドレスにはこの IP を予約する」** ルールを設定。
プールから該当 IP が他のクライアントに貸し出されなくなり、ESP8266 の静的 IP と衝突しない。

---

## 手順

### 1. ESP8266 の MAC アドレスを採取する

3 通りの方法から選ぶ (どれか 1 つでよい)。

#### 方法 A: ESP8266 スケッチ内で一時的に Serial 出力

`ESP8266_DeepSleep_FixedIP_Sensor.ino` の `setup()` 冒頭に一時的に追加:

```cpp
Serial.begin(115200);
delay(100);
Serial.print("MAC: ");
Serial.println(WiFi.macAddress());
```

書き込んで Serial Monitor (115200 bps) を開き、起動時に `MAC: EC:FA:BC:12:34:56` のように出力される。
採取したら `Serial.begin` と Serial 系の行を削除して再書き込み (省電力のため)。

#### 方法 B: Raspberry Pi 側の dnsmasq ログから採取

ESP8266 が一度でも AP に接続していれば、Pi 側にログが残っている。

```bash
sudo journalctl -u dnsmasq --since "1 hour ago" | grep -i "DHCPACK\|DHCPOFFER"
```

`DHCPACK(wlan1) 192.168.4.208 ec:fa:bc:12:34:56 ESP_XXXXXX` のような行から MAC を採取。
※ `WiFi.config` で静的 IP を主張していても、AP 側の DHCP サーバーが接続時に MAC を認識するので記録される。

#### 方法 C: arp テーブルから採取

ESP8266 が最近通信していれば:

```bash
arp -an | grep 192.168.4.208
```

`? (192.168.4.208) at ec:fa:bc:12:34:56 [ether] on wlan1` のように出る。

---

### 2. dnsmasq 設定に予約を追記

wlan1 用 dnsmasq 設定ファイル (Phase 4 で作成済み) を編集:

```bash
sudo nano /etc/dnsmasq.d/wlan1.conf
```

末尾に **MAC-IP 対応の 1 行** を追加 (チップごとに 1 行):

```
# ESP8266 静的IP デバイス群 (MAC 固定割当)
dhcp-host=ec:fa:bc:12:34:56,192.168.4.208,ESP_208
dhcp-host=ec:fa:bc:AB:CD:EF,192.168.4.209,ESP_209
dhcp-host=ec:fa:bc:11:22:33,192.168.4.210,ESP_210
```

書式: `dhcp-host=<MAC>,<IP>,<hostname>`
- MAC は小文字コロン区切り
- IP は ESP8266 スケッチの `fixedIP` と同じ値
- hostname は任意 (dnsmasq のログや `dig` で見えるだけ、識別用)

### 3. dnsmasq を再起動して反映

```bash
sudo systemctl restart dnsmasq
sudo systemctl status dnsmasq --no-pager
```

エラーが出ていないことを確認。

### 4. 動作確認

ESP8266 を再起動 (電源入れ直し) して、Pi 側で:

```bash
sudo journalctl -u dnsmasq -f
```

`DHCPACK(wlan1) 192.168.4.208 ec:fa:bc:12:34:56 ESP_208` と出れば予約が効いている。

もう一つ確認:

```bash
sudo arp -an | grep wlan1
```

MAC と IP の対応が想定通りか確認。

---

## 補足: なぜ ESP 側で WiFi.config しているのに MAC 予約も必要?

- ESP 側 `WiFi.config(fixedIP, ...)` は **「DHCP を使わずこの IP を使う」** という宣言。ESP は最初から 192.168.4.208 を名乗ってサーバーと通信する。
- しかし AP 側 (dnsmasq) は ESP がその IP を使っているかどうか能動的に確認しない。DHCP プールから別のクライアントに同じ IP を割り当てる可能性が残る。
- MAC 予約を書くと、dnsmasq は **「この IP は特定 MAC に予約済みなので他に貸さない」** と動作する。ESP 側の静的 IP 宣言と噛み合って衝突が防げる。

## 補足: 別解 (DHCP プール範囲を狭める)

MAC 予約を書かない代替として、dnsmasq の DHCP プール範囲を狭くする方法もある。
例えば `dhcp-range=192.168.4.100,192.168.4.199,255.255.255.0,24h` にして、
200 番台を ESP 静的 IP 専用として温存する。

```
# /etc/dnsmasq.d/wlan1.conf
interface=wlan1
dhcp-range=192.168.4.100,192.168.4.199,255.255.255.0,24h
# 200-254 番は静的 IP 専用 (dnsmasq が触らない)
```

**メリット**: 個々の ESP の MAC を採取する必要がない
**デメリット**: プール範囲を消費 (100 台分は残るが)、DHCP プール外にいる ESP の管理は目視のみ

大量にチップを増やす予定がなければこちらの方が運用が単純。

---

## 推奨アプローチ

- **チップが 5 台以下**: 方法 A (Serial 出力) で MAC 採取 → dhcp-host 予約
- **チップが 10 台以上 or 動的に増減する**: DHCP プール範囲を 100-199 に狭める代替解
- **どちらでも運用可能**: 一貫性 (どの手法か決めて統一) が最も大事
