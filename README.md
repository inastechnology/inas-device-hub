# ina-device-hub

ina-device-hub は、MQTT で受信したセンサーデータやカメラ画像を集約し、ローカル／クラウドへ保存・連携する
軽量な IoT ハブです（Turso / S3 互換ストレージ対応、Flask による簡易 Web 表示、タイムラプス等）。

なにができるか（要点）

- デバイスからのデータ受信（MQTT）と加工
- 画像／音声のローカル保存と S3 互換ストレージへのアップロード
- ローカル DB（Turso/libsql）との統合
- タイムラプス生成・スケジューリング（APScheduler）
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

貢献

PR・Issue を歓迎します。作業前に依存を同期し、`rye run format` と `rye run lint` を実行してください。

ライセンス

MIT ライセンス（`LICENSE` を参照）

---

必要であれば、Raspberry Pi 固有のセットアップ手順や systemd の環境ファイル対応を README に追記します。

