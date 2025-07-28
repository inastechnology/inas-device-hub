# INA Device Hub — Setup Guide (Rye Edition)

This repository is a **Rye‑managed Python project** that collects sensor metrics, snapshots, and timelapse frames from edge devices, synchronises them to the cloud, analyses plant health with AI, and automatically publishes daily updates to Instagram while sending operational notifications to Discord.

---

## Contents

1. [Prerequisites](#prerequisites)
2. [Clone & Bootstrap](#clone--bootstrap)
3. [Platform Setup](#platform-setup)
   3.1 [Cloudflare R2](#cloudflare-r2)
   3.2 [Turso DB](#turso-db)
   3.3 [Instagram Graph API](#instagram-graph-api)
   3.4 [Discord Webhook](#discord-webhook)
   3.5 [AI Providers](#ai-providers)
   3.6 [Camera Devices](#camera-devices)
4. [Environment Variables](#environment-variables)
5. [Database Initialisation](#database-initialisation)
6. [Running the Hub](#running-the-hub)
7. [Production Notes](#production-notes)

---

## Prerequisites

| Requirement          | Notes                                                                               |        |
| -------------------- | ----------------------------------------------------------------------------------- | ------ |
| **Rye ≥ 0.28**       | Install: \`curl -sSf [https://rye-up.com/install.sh](https://rye-up.com/install.sh) | bash\` |
| **Python ≥ 3.11**    | Rye will auto‑download the pinned tool‑chain defined in `rye.toml`.                 |        |
| **git** & **ffmpeg** | `ffmpeg` used for timelapse compilation.                                            |        |
| Camera(s) (RTSP/FTP) | See [Camera Devices](#camera-devices).                                              |        |

> 👉 If you are new to Rye, skim the *5‑minute tour* first: [https://rye-up.com/guide/](https://rye-up.com/guide/).

---

## Clone & Bootstrap

```bash
# 1 · clone the repository
$ git clone https://github.com/your‑org/ina-device-hub.git
$ cd ina-device-hub

# 2 · install Python & all dependencies
$ rye sync   # reads pyproject.toml/requirements.lock

# 3 · run unit tests (optional)
$ rye test
```

No `pip` or `virtualenv` is needed—Rye keeps everything isolated inside `~/.rye`.

---

## Platform Setup

Below are the external services the hub integrates with. Follow the official guides and copy the resulting credentials into your `.env` (see next section).

### Cloudflare R2

|             |                                                                                                                                 |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose** | Temporary media storage (raw photos, timelapse MP4s) before they are pushed elsewhere.                                          |
| **Guide**   | [https://developers.cloudflare.com/r2/get-started/](https://developers.cloudflare.com/r2/get-started/)                          |
| **Steps**   | 1) Create an R2 bucket  2) Generate an **Access Key** & **Secret**  3) (Optional) Map a custom domain  4) Fill `S3_TMP_*` vars. |

### Turso DB

|             |                                                                  |
| ----------- | ---------------------------------------------------------------- |
| **Purpose** | Edge database for high‑frequency sensor data.                    |
| **Guide**   | [https://docs.turso.tech/](https://docs.turso.tech/)             |
| **Steps**   | `turso db create ina_hub` → `turso auth token` → copy to `.env`. |

### Instagram Graph API

|             |                                                                                                                                                                   |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose** | Publish reels/photos to the target business account.                                                                                                              |
| **Guide**   | [https://developers.facebook.com/docs/instagram-api](https://developers.facebook.com/docs/instagram-api)                                                          |
| **Steps**   | 1) Create a Facebook App  2) Add **Instagram Basic Display** + **Content Publishing**  3) Make the app *Live*  4) Grab **User ID** & **Long‑Lived Access Token**. |

### Discord Webhook

|             |                                                                                                                                                        |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Purpose** | Ops and error notifications.                                                                                                                           |
| **Guide**   | [https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks) |
| **Steps**   | In your server → *Integrations* → *Webhooks* → *New Webhook* → copy URL to `.env`.                                                                     |

### AI Providers

| Provider                | Docs                                                                                           |
| ----------------------- | ---------------------------------------------------------------------------------------------- |
| **OpenAI** (Vision)     | [https://platform.openai.com/docs/introduction](https://platform.openai.com/docs/introduction) |
| **Deepseek** (Reasoner) | [https://platform.deepseek.com/docs](https://platform.deepseek.com/docs)                       |

### Camera Devices

| Type               | Example Links                                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| **RTSP / ONVIF**   | TP-Link(Tapo) |
| **FTP Still Cams** | ReoLink E1, E1 pro                                                                              |

Add each camera to `{work_dir}}/.camera_device_list.json` in the following format:

#### Example Camera Device

##### RTSP Camera

```json
{
  "INACD-aaaa": {
    "id": "INACD-aaaa",
    "name": "INACD-aaaa",
    "location_id": null,
    "type": "RTSP", 
    "timelapse": true,
    "ip_address": "192.168.xxx.xxx",
    "username": "xxx",
    "password": "yyy!"
  }
}
```

##### FTP Camera

```json
{
    "INACD-bbbbb": {
        "id": "INACD-bbbbb",
        "name": "INACD-bbbbb",
        "location_id": null,
        "type": "FTP", 
        "timelapse": true,
        "directory": "/mnt/nas0/garden/ftp/reo/camera"
    }
}
```

---

## Environment Variables

Duplicate `.env.example` → `.env` and fill **every** placeholder. Important fields are highlighted below; the rest mirror the template exactly.

```dotenv
# ===============================
# General
# ===============================
LANGUAGE=en                         # Output language for logs & AI captions (en/ja)
WORK_DIR=~/.ina-device-hub          # Runtime files (cache, logs)
LOCAL_STORAGE_BASE_DIR=/mnt/...     # Local archival path for images/audio

# ===============================
# Turso (Edge DB)
# ===============================
TURSO_DATABASE_URL=libsql://        # e.g. libsql://ina_hub.turso.io
TURSO_AUTH_TOKEN=                   # `turso auth token`
TURSO_SYNC_INTERVAL=600             # Seconds between sync attempts (offline‑friendly)

# ===============================
# Permanent Object Storage (optional)
# ===============================
S3_ENDPOINT_URL=https://            # e.g. https://s3.wasabisys.com
S3_BUCKET_NAME=                     # Persistent bucket for long‑term media
S3_BUCKET_REGION=auto               # Set to your provider region if required
S3_ACCESS_KEY=                      # Access key (persistent bucket)
S3_SECRET_KEY=                      # Secret key (persistent bucket)

# ===============================
# Cloudflare R2 (temporary media)
# ===============================
S3_TMP_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com   # R2 endpoint
S3_TMP_BUCKET_NAME=ina-temporary    # Bucket name for raw frames & timelapses
S3_TMP_BUCKET_REGION=auto           # Always "auto" for R2
S3_TMP_ACCESS_KEY=                  # R2 access key
S3_TMP_SECRET_KEY=                  # R2 secret key
S3_TMP_BASE_URL=https://media.example.com  # Public base URL (cf. custom domain)

# ===============================
# Instagram Graph API
# ===============================
INSTAGRAM_USER_ID=                  # Numeric Business/Creator account ID
INSTAGRAM_ACCESS_TOKEN=             # Long‑lived token (60d/90d)

# Optional: fine‑grained control for post generator
INSTAGRAM_SENSOR_ID=                # Sensor device ID whose chart is embedded
INSTAGRAM_CAMERA_ID=                # Primary camera device ID for timelapse
INSTAGRAM_PLANT_POSITION_PROMPT="From left: blueberry, lychee"  # Caption helper

# ===============================
# MQTT Broker (sensor uplink)
# ===============================
MQTT_BROKER_URL=localhost           # Broker host or IP
MQTT_BROKER_PORT=1883               # Broker port
MQTT_BROKER_USERNAME=               # Leave empty for unauthenticated
MQTT_BROKER_PASSWORD=               # ---

# ===============================
# Local capture options
# ===============================
SENSOR_SAVE_IMAGE=false             # true = persist every still frame locally
SENSOR_SAVE_AUDIO=false             # true = save microphone recordings

TIMELAPSE_INTERVAL=600              # Seconds between timelapse snapshots

# ===============================
# AI Agent
# ===============================
AI_ENABLED=true                     # Disable to run hub without AI pipeline
AI_AGENT_SCHEDULE_START=09:01       # Daily summary HH:MM (24h local)

# --- Vision (OpenAI)
AI_IMAGE_ANALYZE_API_KEY=sk-****    # OpenAI key
AI_IMAGE_ANALYZE_BASE_URL=          # Optional custom endpoint
AI_IMAGE_ANALYZE_MODEL=gpt-4o       # Model name

# --- Text reasoning (Deepseek)
AI_TEXT_ANALYZE_API_KEY=sk-***      # Deepseek key
AI_TEXT_ANALYZE_BASE_URL=https://api.deepseek.com  # Endpoint
AI_TEXT_ANALYZE_MODEL=deepseek-reasoner            # Model

# ===============================
# Discord
# ===============================
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_url  # Ops alerts
```

---

## Running the Hub

```bash
rye run backend
rye run frontend
```

The service will begin polling MQTT topics, archiving imagery to R2, posting to Instagram, and pushing AI analyses back through the Discord webhook.

---

## Production Notes

* **systemd**: copy `systemd/inas-device-hub@.service` to `/etc/systemd/system/` and `systemctl enable --now inas-device-hub@backend`.
* **Docker**: build with `docker build -t device-hub@backend .` (multi‑stage file provided).
* **Offline**: tune `TURSO_SYNC_INTERVAL` to buffer longer when the internet is unstable.
* **Cloudflare Tunnel**: expose the RTSP/HTTP interface securely if remote access is required.

> Need help? Open an issue or jump into our Discord channel #ina‑dev.
