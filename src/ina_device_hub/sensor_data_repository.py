# sensor data repository

import json
from datetime import UTC, datetime, timedelta, timezone

from ina_device_hub.general_log import logger
from ina_device_hub.ina_db_connector import ina_db_connector
from ina_device_hub.setting import setting


class SensorDataRepository:
    def __init__(
        self,
    ):
        self.db_connector = ina_db_connector()
        self.tmp_sensor_data_dict = {}
        self.tmp_file_path = setting().get_work_dir() + "/tmp_sensor_data.json"
        self.light_status_dict = {}

        # load tmp sensor data
        self.__load_tmp_sensor_data()

    def add(self, sensor_id: str, seqId: int, data: dict):
        # construct extra
        data["extra"] = {"light_status": self.light_status_dict.get(None, {})}

        # latest data record
        self.__insert_latest_data(sensor_id, data)

        # aggregate data record
        if sensor_id not in self.tmp_sensor_data_dict:
            self.tmp_sensor_data_dict[sensor_id] = {}

        current_yyyymmdd_hh = datetime.now(UTC).strftime("%Y%m%d%H")
        if current_yyyymmdd_hh not in self.tmp_sensor_data_dict[sensor_id]:
            self.tmp_sensor_data_dict[sensor_id][current_yyyymmdd_hh] = []

        self.tmp_sensor_data_dict[sensor_id][current_yyyymmdd_hh].append(data)

        # save tmp sensor data
        self.__save_tmp_sensor_data()

        # whether aggregate or not
        # older than 1hours
        for yyyymmdd_hh in list(self.tmp_sensor_data_dict[sensor_id].keys()):
            if datetime.strptime(yyyymmdd_hh, "%Y%m%d%H").replace(tzinfo=UTC) < (datetime.now(UTC) - timedelta(hours=1)):
                logger.info(f"aggregate data: sensor_id={sensor_id}, yyyymmdd_hh={yyyymmdd_hh}")
                aggregated_data = self.__aggregate_data(sensor_id, yyyymmdd_hh)
                if aggregated_data:
                    self.__insert_aggreated_data(sensor_id, yyyymmdd_hh, aggregated_data)
                    del self.tmp_sensor_data_dict[sensor_id][yyyymmdd_hh]
                    self.__save_tmp_sensor_data()

    def get_latest(self, sensor_id: str):
        data_as_tupple = self.db_connector.fetch_latest_sensor_data(sensor_id)
        if data_as_tupple is None:
            return None

        # sensor_id TEXT PRIMARY KEY,
        # temp REAL,
        # tds REAL,
        # ec REAL,
        # ph REAL,
        # dissolved_oxygen REAL,
        # ammonia REAL,
        # nitrate REAL,
        # location_id TEXT,
        # created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        # updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        # extra TEXT,
        try:
            extra = json.loads(data_as_tupple[11])
        except json.JSONDecodeError:
            extra = {}
        return {
            "sensor_id": data_as_tupple[0],
            "temp": data_as_tupple[1],
            "tds": data_as_tupple[2],
            "ec": data_as_tupple[3],
            "ph": data_as_tupple[4],
            "dissolved_oxygen": data_as_tupple[5],
            "ammonia": data_as_tupple[6],
            "nitrate": data_as_tupple[7],
            "location_id": data_as_tupple[8],
            "created_at": datetime.strptime(data_as_tupple[9], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).astimezone(),
            "updated_at": datetime.strptime(data_as_tupple[10], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).astimezone(),
            "extra": extra,
        }

    def get_latest_aggreated(self, sensor_id: str, limit: int = 50):
        data = self.db_connector.fetch_latest_aggregated_sensor_data(sensor_id, limit)
        if data is None:
            return None

        # sensor_id, temp, tds, ec, ph, dissolved_oxygen, ammonia, nitrate, yyyymmddhh, created_at, extra
        ret = []
        for d in data:
            try:
                extra = json.loads(d[10])
            except json.JSONDecodeError:
                extra = {}
            ret.append(
                {
                    "sensor_id": d[0],
                    "temp": d[1],
                    "tds": d[2],
                    "ec": d[3],
                    "ph": d[4],
                    "dissolved_oxygen": d[5],
                    "ammonia": d[6],
                    "nitrate": d[7],
                    "yyyymmddhh": datetime.strptime(str(d[8]), "%Y%m%d%H").replace(tzinfo=UTC).astimezone(),
                    "created_at": d[9],
                    "extra": extra,
                }
            )
        return ret

    def get_aggreated_by_range(self, sensor_id: str, start: str, end: str):
        return self.db_connector.fetch_aggregated_sensor_data_by_range(
            sensor_id,
            start,
            end,
        )

    def force_aggregate(self, sensor_id):
        for yyyymmdd_hh in list(self.tmp_sensor_data_dict[sensor_id].keys()):
            aggregated_data = self.__aggregate_data(sensor_id, yyyymmdd_hh)
            if aggregated_data:
                self.__insert_aggreated_data(
                    sensor_id,
                    yyyymmdd_hh,
                    aggregated_data,
                )
                del self.tmp_sensor_data_dict[sensor_id][yyyymmdd_hh]
                self.__save_tmp_sensor_data()

    def update_light_status(self, location_id: str, status: bool, confidence: float):
        self.light_status_dict[location_id] = {
            "status": status,
            "confidence": confidence,
            "updated_at": datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def __aggregate_data(self, sensor_id, yyyymmdd_hh):
        if sensor_id not in self.tmp_sensor_data_dict:
            return None

        if yyyymmdd_hh not in self.tmp_sensor_data_dict[sensor_id]:
            return None

        if len(self.tmp_sensor_data_dict[sensor_id][yyyymmdd_hh]) == 0:
            return None

        # aggregate
        temps = []
        tdss = []
        light_status_list = []
        light_status_average = 0

        data = self.tmp_sensor_data_dict[sensor_id][yyyymmdd_hh]

        for elem in data:
            if "temp" in elem and elem["temp"] != -1000:
                temps.append(elem["temp"])
            if "tds" in elem and elem["tds"] != -1000:
                tdss.append(elem["tds"])

            if "extra" in elem:
                try:
                    # status =false を負として confidence を加重平均
                    # 結果が正の場合は light=on
                    # 結果が負の場合は light=off
                    if "light_status" in elem["extra"]:
                        light_status = elem["extra"]["light_status"]
                        if "status" in light_status and "confidence" in light_status:
                            light_status_list.append(light_status)
                            if light_status["status"]:
                                light_status_average += light_status["confidence"]
                            else:
                                light_status_average -= light_status["confidence"]
                except Exception as e:
                    logger.exception(f"Failed to aggregate light status: {e}:{elem['extra']}")

        avg_temp = sum(temps) / len(temps) if len(temps) > 0 else -1000
        avg_tds = sum(tdss) / len(tdss) if len(tdss) > 0 else -1000
        led_status = True if light_status_average > 0 else False
        print(f"led_status: {led_status}, light_status_average: {light_status_average}")
        print(f"detailed light status: {light_status_list}")
        # construct extra
        extra = {
            "light_status": {
                "status": led_status,
            }
        }

        return {
            "temp": avg_temp,
            "tds": avg_tds,
            "extra": extra,
        }

    def __insert_latest_data(self, sensor_id: str, data: dict):
        self.db_connector.upsert_latest_sensor_data(
            sensor_id,
            data,
        )

    def __insert_aggreated_data(self, sensor_id: str, yyyymmdd_hh: str, data: dict):
        self.db_connector.insert_aggregated_sensor_data(
            sensor_id,
            yyyymmdd_hh,
            data,
        )

    def __save_tmp_sensor_data(self):
        with open(self.tmp_file_path, "w") as f:
            json.dump(self.tmp_sensor_data_dict, f, indent=4)

    def __load_tmp_sensor_data(self):
        try:
            with open(self.tmp_file_path, "r") as f:
                self.tmp_sensor_data_dict = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load tmp sensor data: {e}")
            # create empty dict
            self.tmp_sensor_data_dict = {}
            self.__save_tmp_sensor_data()


# singleton instance
__instance = None


def sensor_data_repository():
    global __instance
    if not __instance:
        __instance = SensorDataRepository()
    return __instance
