# ina-device-hub

ina-device-hub は、MQTT で受信したセンサーデータやカメラ画像を集約し、ローカル／クラウドへ保存・連携する
軽量な IoT ハブです（Turso / S3 互換ストレージ対応、Flask による簡易 Web 表示、タイムラプス等）。

なにができるか（要点）

- デバイスからのデータ受信（MQTT）と加工
- `farm/{device_id}/telemetry` テレメトリの受信と保存
- デバイスごとの設定配信（MQTT request/reply/push）
- 画像／音声のローカル保存と S3 互換ストレージへのアップロード
- ローカル DB（Turso/libsql）との統合
- タイムラプス生成・スケジューリング（APScheduler）
- タイムラプス画像からの mp4 生成と Instagram Reel 自動投稿
- 簡易 Web 表示（Flask）

クイックスタート

1. rye を導入（未導入の場合）: https://rye.astral.sh/guide/installation/

2. 依存を同期

```bash
rye sync
```

3. 環境変数を用意（`.default.env` があればコピー）

```bash
cp .default.env .env
# 編集: .env の値を実運用に合わせて更新してください
```

4. 必要なら DB を作成

```bash
rye run db:create
```

5. ローカルで起動（開発）

```bash
rye run serve
# デフォルト: http://localhost:5151
```

systemd による自動起動（推奨）

このリポジトリにはテンプレートユニット `systemd/inas-device-hub@.service` と
インストーラースクリプト `scripts/install_service.sh` が含まれます。インストーラーの主な動作は次の通りです。

- リポジトリを指定ディレクトリへコピー（既定: `/home/<user>/ina-device-hub`）
- インストール実行者（`sudo` で実行した場合は元のユーザー）をサービス実行ユーザーに設定
- `.default.env` を `.env` にコピー（無ければ簡易テンプレートを作成）
- `systemd/inas-device-hub@.service` を `/etc/systemd/system/` に配置し、
	テンプレート内の `/home/pi` と `User=pi` をターゲットのパス・ユーザーに置換
- `inas-device-hub@frontend` と `inas-device-hub@backend` を有効化・起動

インストール例（sudo）

```bash
sudo ./scripts/install_service.sh

# --user と --target-dir で上書き可能
sudo ./scripts/install_service.sh --user mysvcuser --target-dir /opt/ina-device-hub
```

サービス確認

```bash
systemctl status inas-device-hub@frontend
systemctl status inas-device-hub@backend

journalctl -u inas-device-hub@frontend -f
journalctl -u inas-device-hub@backend -f
```

手動でテンプレートを配置する場合

```bash
sudo cp ./systemd/inas-device-hub@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now inas-device-hub@frontend
sudo systemctl enable --now inas-device-hub@backend
```

開発ワークフロー（短く）

- フォーマット

```bash
rye run format
```

- リント

```bash
rye run lint
```

主要ファイル（概要）

- `pyproject.toml` — 依存と rye スクリプト
- `src/ina_device_hub/` — アプリ本体（`setting.py`, `hub_mqtt_client.py`, `camera_connector.py` など）
- `systemd/inas-device-hub@.service` — systemd テンプレートユニット
- `scripts/install_service.sh` — systemd インストールスクリプト

主要な環境変数（要約）

詳細は `src/ina_device_hub/setting.py` を参照してください。主に次が必須です:

- TURSO_DATABASE_URL, TURSO_AUTH_TOKEN
- S3_ENDPOINT_URL, S3_BUCKET_NAME, S3_BUCKET_REGION, S3_ACCESS_KEY, S3_SECRET_KEY
- MQTT_BROKER_URL, MQTT_BROKER_PORT, MQTT_BROKER_USERNAME, MQTT_BROKER_PASSWORD
- TIMELAPSE_INTERVAL
- DEVICE_CONFIG_DEFAULT_NTP_SERVER, DEVICE_CONFIG_DEFAULT_TIMEZONE_OFFSET_SEC, DEVICE_CONFIG_DEFAULT_MOISTURE_THRESHOLD

Instagram 自動投稿を使う場合は、追加で次を設定してください。

- S3_TMP_ENDPOINT_URL, S3_TMP_BUCKET_NAME, S3_TMP_BUCKET_REGION, S3_TMP_ACCESS_KEY, S3_TMP_SECRET_KEY
- S3_TMP_BASE_URL
- INSTAGRAM_USER_ID, INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_CAMERA_ID
- INSTAGRAM_SENSOR_ID, INSTAGRAM_PLANT_POSITION_PROMPT
- AI_ENABLED, AI_AGENT_SCHEDULE_START
- AI_IMAGE_ANALYZE_API_KEY, AI_IMAGE_ANALYZE_BASE_URL, AI_IMAGE_ANALYZE_MODEL
- AI_TEXT_ANALYZE_API_KEY, AI_TEXT_ANALYZE_BASE_URL, AI_TEXT_ANALYZE_MODEL

Instagram 自動投稿フロー

- `TIMELAPSE_INTERVAL` ごとに RTSP から静止画を取得し、S3 とローカルの `timelapse_frames/` に保存します。
- `AI_AGENT_SCHEDULE_START` の時刻になると、前回投稿以降の静止画から mp4 を生成します。
- 生成した動画と代表画像を `S3_TMP_*` にアップロードし、公開 URL を作成します。
- AI に代表画像、タイムラプス動画 URL、センサースナップショット、`INSTAGRAM_PLANT_POSITION_PROMPT` を渡して投稿文を生成します。
- Instagram Graph API を使って Reel を投稿します。

注意:

- Instagram 投稿には公開アクセス可能な `S3_TMP_BASE_URL` が必要です。非公開バケット URL では投稿できません。
- `INSTAGRAM_CAMERA_ID` は `.camera_device_list.json` に登録済みのカメラ ID を指定してください。
- `INSTAGRAM_SENSOR_ID` を設定すると、最新センサーデータを投稿文生成に含めます。

貢献

PR・Issue を歓迎します。作業前に依存を同期し、`rye run format` と `rye run lint` を実行してください。

デバイス設定配信

- デバイスは `/<device_id>/kinds/config/request` へ publish します。
- Hub は `/<device_id>/kinds/config/reply` へ retained で設定 JSON を返します。
- 即時反映が必要な場合は `/<device_id>/kinds/config/push` に同じ JSON を publish できます。
- 設定は `WORK_DIR/.device_configs.json` に保存されます。

Farm Telemetry 受信

- Hub は `farm/+/telemetry` を購読します。
- payload は JSON として解釈し、`device_id` ごとの最新値を保存します。
- `soil_moisture_*`, `soil_temp_c`, `battery_v`, `rssi`, `timestamp` は `latest_sensor_data.extra.telemetry` に保持します。
- `soil_temp_c` は既存の温度グラフ互換のため `latest_sensor_data.temp` にも反映します。
- `null` を含む payload を許容します。欠損値があっても受信処理が落ちない前提です。
- デバイス詳細画面では最終受信時刻、電圧しきい値、未着時間に基づく簡易監視表示を出します。

ローカル API

- `GET /local/api/device-configs`
- `GET /local/api/device-configs/<device_id>`
- `PUT /local/api/device-configs/<device_id>`
- `POST /local/api/device-configs/<device_id>/push`

`PUT /local/api/device-configs/<device_id>?push=true` に設定 JSON を送ると、保存後に `push` まで実行します。

設定 JSON 例

```json
{
  "ntp_server": "my_device.local",
  "timezone_offset_sec": 32400,
  "moisture_threshold": 35,
  "schedules": [
    {
      "hour": 6,
      "minute": 30,
      "duration_sec": 20,
      "channel_mask": 1
    },
    {
      "hour": 18,
      "minute": 0,
      "duration_sec": 30,
      "channel_mask": 3
    }
  ]
}
```

NTP サーバ運用

- NTP サーバは MQTT Hub と同じ PC 上で、アプリとは別の OS サービスとして動かしてください。
- `ntp_server` には、ファームから名前解決できるホスト名または固定 IP を設定してください。
- ローカルネットワークから UDP 123 で到達できる必要があります。
- Hub 自体は `ntp_server` の値を配信するだけなので、実際の NTP 提供は `chronyd` や `ntpd` のような既存サービスで構成する前提です。

ライセンス

MIT ライセンス（`LICENSE` を参照）

---

必要であれば、Raspberry Pi 固有のセットアップ手順や systemd の環境ファイル対応を README に追記します。
