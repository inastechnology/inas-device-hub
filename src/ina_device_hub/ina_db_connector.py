# センサーデバイスから受信したデータを保持するクラス
# 以下の機能を提供する
# - センサーデータ保存用のデータベースを作成する
# - センサーデータ保存用のテーブルを作成する
# - センサーデータをデータベースに保存する
# - センサーデータをデータベースから取得する
import json
import os
import re

import libsql_experimental as libsql

from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting


def turso_db_commit(func):
    """
    関数実行後、必ず commit と sync を実行するデコレーター
    """

    def wrapper(self, *args, **kwargs):
        try:
            result = func(self, *args, **kwargs)
            self.conn.commit()
            return result
        except Exception as e:
            # エラーハンドリング（必要に応じてログ出力等）
            logger.exception("Error occurred:", e)
            raise
        finally:
            pass

    return wrapper


class InaDBConnector:
    def __init__(self):
        turso_settings = setting().get("turso")
        db_path = turso_settings.get("local_db_path")
        url = turso_settings.get("database_url")
        auth_token = turso_settings.get("auth_token")
        sync_interval = turso_settings.get("sync_interval")
        try:
            self.conn = libsql.connect(db_path, sync_interval=sync_interval, sync_url=url, auth_token=auth_token)

        except ValueError as e:
            logger.error("Error occurred:", e)
            if "orphan index" in str(e):
                logger.info("orphan index error occurred. Reindexing the database.")
                self.__reindex()
                logger.info("Reindexing done. Reconnecting to the database.")
                self.conn = libsql.connect(db_path, sync_interval=sync_interval, sync_url=url, auth_token=auth_token)
            elif "malformed" in str(e):
                logger.info("Database is corrupted. Deleting the database file.")
                # delete target files
                db_name = os.path.basename(db_path)
                target_re = re.compile(rf"{db_name}.*")
                for file in os.listdir(os.path.dirname(db_path)):
                    if target_re.match(file):
                        logger.info(f"Deleting {file}")
                        os.remove(os.path.join(os.path.dirname(db_path), file))
                logger.info("Database file deleted. Reconnecting to the database.")
                self.conn = libsql.connect(db_path, sync_interval=sync_interval, sync_url=url, auth_token=auth_token)
            else:
                raise

        self.conn.sync()

    def __reindex(self):
        self.conn.execute("REINDEX")

    def fetch_location_all(self):
        """
        全ロケーション情報を取得します。
        """
        return self.conn.execute("SELECT * FROM location_table").fetchall()

    def upsert_location(self, location_id: str, info: dict):
        # location_id TEXT PRIMARY KEY,
        # name TEXT,
        # description TEXT,
        # longitude REAL,
        # latitude REAL,
        # info TEXT,
        # location_type TEXT,
        # country TEXT,
        # city TEXT,
        # created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        # updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        self.conn.execute(
            "INSERT INTO location_table (location_id, name, description, longitude, latitude, info, location_type, country, city) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(location_id) DO UPDATE SET "
            "name = excluded.name, "
            "description = excluded.description, "
            "longitude = excluded.longitude, "
            "latitude = excluded.latitude, "
            "info = excluded.info, "
            "location_type = excluded.location_type, "
            "country = excluded.country, "
            "city = excluded.city, "
            "updated_at = CURRENT_TIMESTAMP",
            (
                location_id,
                info.get("name", location_id),
                info.get("description", ""),
                info.get("longitude", -1000.0),
                info.get("latitude", -1000.0),
                json.dumps(info.get("info", {})),
                info.get("location_type", "unknown"),
                info.get("country", "unknown"),
                info.get("city", "unknown"),
            ),
        )

    def fetch_sensors_all(self):
        """
        全センサーデバイスを取得します。
        """
        return self.conn.execute("SELECT * FROM sensor_info").fetchall()

    def fetch_sensor(self, sensor_id: str):
        """
        指定された sensor_id に紐づくセンサーデバイスを取得します。
        """
        return self.conn.execute("SELECT * FROM sensor_info WHERE sensor_id = ?", (sensor_id,)).fetchone()

    def upsert_sensor(self, sensor_id: str, info: dict):
        """
        センサーデバイス情報を登録／更新します。
        INSERT 時は created_at が自動設定され、UPDATE 時は updated_at に CURRENT_TIMESTAMP が自動で設定されます。
        CREATE TABLE IF NOT EXISTS sensor_info (
            sensor_id TEXT PRIMARY KEY,
            info TEXT,
            sensor_type TEXT,
            firmware_version TEXT,
            installation_date TIMESTAMP,
            location_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (location_id) REFERENCES location_table(location_id)
        );
        """
        self.conn.execute(
            "INSERT INTO sensor_info (sensor_id, info, sensor_type, firmware_version, installation_date, location_id) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(sensor_id) DO UPDATE SET "
            "info = excluded.info, "
            "sensor_type = excluded.sensor_type, "
            "firmware_version = excluded.firmware_version, "
            "installation_date = excluded.installation_date, "
            "location_id = excluded.location_id, "
            "updated_at = CURRENT_TIMESTAMP",
            (
                sensor_id,
                json.dumps(info.get("info", {})),
                info.get("sensor_type"),
                info.get("firmware_version"),
                info.get("installation_date"),
                info.get("location_id"),
            ),
        )

    def fetch_sensors_by_location_id(self, location_id: str = None):
        """
        指定された location_id に紐づくセンサーデバイスを取得します。
        """
        if location_id is None:
            query = "SELECT * FROM sensor_info WHERE location_id IS NULL"
            param = ()
        else:
            query = "SELECT * FROM sensor_info WHERE location_id = ?"
            param = (location_id,)

        return self.conn.execute(query, param).fetchall()

    @turso_db_commit
    def upsert_latest_sensor_data(self, sensor_id: str, data: dict):
        """
        最新センサーデータ（拡張版：溶存酸素、アンモニア、硝酸塩追加）を登録／更新します。
        INSERT 時は created_at が自動設定され、UPDATE 時は updated_at に CURRENT_TIMESTAMP が自動で設定されます。
        """
        self.conn.execute(
            "INSERT INTO latest_sensor_data (sensor_id, temp, tds, ec, ph, dissolved_oxygen, ammonia, nitrate, extra) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(sensor_id) DO UPDATE SET "
            "temp = excluded.temp, "
            "tds = excluded.tds, "
            "ec = excluded.ec, "
            "ph = excluded.ph, "
            "dissolved_oxygen = excluded.dissolved_oxygen, "
            "ammonia = excluded.ammonia, "
            "nitrate = excluded.nitrate, "
            "updated_at = CURRENT_TIMESTAMP, "
            "extra = excluded.extra",
            (
                sensor_id,
                data.get("temp", -1000.0),
                data.get("tds", -1000.0),
                data.get("ec", -1000.0),
                data.get("ph", -1000.0),
                data.get("dissolved_oxygen", -1000.0),
                data.get("ammonia", -1000.0),
                data.get("nitrate", -1000.0),
                json.dumps(data.get("extra", {})),
            ),
        )

    @turso_db_commit
    def insert_aggregated_sensor_data(self, sensor_id: str, yyyymmdd_hh: str, data: dict):
        """
        集計済センサーデータ（拡張版）を登録します。複合キー（sensor_id, yyyymmddhh）。
        """
        self.conn.execute(
            "INSERT INTO aggregated_sensor_data (sensor_id, temp, tds, ec, ph, dissolved_oxygen, ammonia, nitrate, yyyymmddhh, extra) "
            "VALUES ("
            f'"{sensor_id}", {round(data.get("temp", -1000.0), 2)}, {round(data.get("tds", -1000.0), 2)}, '
            f"{round(data.get('ec', -1000.0), 2)}, {round(data.get('ph', -1000.0), 2)}, "
            f"{round(data.get('dissolved_oxygen', -1000.0), 2)}, "
            f"{round(data.get('ammonia', -1000.0), 2)}, {round(data.get('nitrate', -1000.0), 2)}, "
            f"'{yyyymmdd_hh}', \"{data.get('extra', '{}')}\""
            ") "
        )

    def fetch_latest_sensor_data(self, sensor_id: str):
        """
        最新センサーデータを取得します。
        """
        return self.conn.execute("SELECT * FROM latest_sensor_data WHERE sensor_id = ?", (sensor_id,)).fetchone()

    def fetch_latest_aggregated_sensor_data(self, sensor_id: str, limit: int = 50):
        """
        最新集計済センサーデータを取得します。
        """
        return self.conn.execute(
            "SELECT * FROM aggregated_sensor_data WHERE sensor_id = ? ORDER BY yyyymmddhh DESC LIMIT ?",
            (sensor_id, limit),
        ).fetchall()

    def fetch_aggregated_sensor_data_by_daily(self, sensor_id: str, yyyymmdd: str):
        """
        集計済センサーデータを取得します。
        daily: yyyymmdd
        """
        return self.conn.execute(
            "SELECT * FROM aggregated_sensor_data WHERE sensor_id = ? AND yyyymmddhh LIKE ?",
            (sensor_id, f"{yyyymmdd}%"),
        ).fetchall()

    def fetch_aggregated_sensor_data_by_range(self, sensor_id: str, start: str, end: str):
        """
        集計済センサーデータを取得します。
        range: start <= yyyymmddhh <= end
        """
        return self.conn.execute(
            "SELECT * FROM aggregated_sensor_data WHERE sensor_id = ? AND yyyymmddhh BETWEEN ? AND ?",
            (sensor_id, start, end),
        ).fetchall()

    def fetch_camera_all(self):
        """
        全カメラデバイスを取得します。
        """
        return self.conn.execute("SELECT * FROM camera_info").fetchall()

    def fetch_camera_by_location_id(self, location_id: str = None):
        """
        指定された location_id に紐づくカメラデバイスを取得します。
        """
        if location_id is None:
            query = "SELECT * FROM camera_info WHERE location_id IS NULL"
            param = ()
        else:
            query = "SELECT * FROM camera_info WHERE location_id = ?"
            param = (location_id,)

        return self.conn.execute(query, param).fetchall()

    def insert_camera_info(self, camera_id: str, location_id: str = None):
        """
        カメラデバイス情報を登録します。
        """
        self.conn.execute(
            "INSERT INTO camera_info (id, location_id) VALUES (?, ?)",
            (camera_id, location_id),
        )

    def upsert_camera_device(self, camera_id: str, info: dict):
        """
        カメラデバイス情報を登録／更新します。
        INSERT 時は created_at が自動設定され、UPDATE 時は updated_at に CURRENT_TIMESTAMP が自動で設定されます。
        """
        self.conn.execute(
            "INSERT INTO camera_info (id, location_id, ip_address, username, password, extra) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "location_id = excluded.location_id, "
            "ip_address = excluded.ip_address, "
            "username = excluded.username, "
            "password = excluded.password, "
            "updated_at = CURRENT_TIMESTAMP, "
            "extra = excluded.extra",
            (
                camera_id,
                info.get("location_id"),
                info.get("ip_address"),
                info.get("username"),
                info.get("password"),
                json.dumps(info.get("extra", {})),
            ),
        )

    def fetch_all_location(self):
        """
        全ロケーション情報を取得します。
        """
        return self.conn.execute("SELECT * FROM location_info").fetchall()

    def upsert_evaluation_result(self, location_id: str, input_data: str, output_data: str):
        """
        評価結果を登録／更新します。
        INSERT 時は created_at が自動設定され、UPDATE 時は updated_at に CURRENT_TIMESTAMP が自動で設定されます。

        evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id TEXT,
        input_data TEXT,
        output_data TEXT,
        summary TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (location_id) REFERENCES location_table(location_id)
        """
        if location_id is None:
            query = "INSERT INTO ai_agent_evaluation (input_data, output_data) VALUES (?, ?)"
            param = (input_data, output_data)
        else:
            query = "INSERT INTO ai_agent_evaluation (location_id, input_data, output_data) VALUES (?, ?, ?)"
            param = (location_id, input_data, output_data)

        self.conn.execute(query, param)


__instance = None


def ina_db_connector():
    global __instance
    if not __instance:
        __instance = InaDBConnector()
    return __instance
