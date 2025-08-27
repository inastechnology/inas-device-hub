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

        # watering sec, if available
        if "watering" in data:
            data["extra"]["watering"] = data["watering"]

        # last soil moisture, if available
        if "last_soil_moisture" in data:
            data["extra"]["last_soil_moisture"] = data["last_soil_moisture"]

        # latest data record
        self.__insert_latest_data(sensor_id, data)

        # aggregate data record
        if sensor_id not in self.tmp_sensor_data_dict:
            self.tmp_sensor_data_dict[sensor_id] = {}

        current_yyyymmdd_hh = datetime.now(UTC).strftime("%Y%m%d%H")
        if current_yyyymmdd_hh not in self.tmp_sensor_data_dict[sensor_id]:
            self.tmp_sensor_data_dict[sensor_id][current_yyyymmdd_hh] = []

        self.tmp_sensor_data_dict[sensor_id][current_yyyymmdd_hh].append(data)

        # 受領したデータに watering と soil moisture の値がある場合は、データを即時アグリゲートする
        if "watering" in data and "last_soil_moisture" in data:
            aggregated_data = self.__aggregate_data(sensor_id, current_yyyymmdd_hh)
            if aggregated_data:
                self.__insert_aggreated_data(sensor_id, current_yyyymmdd_hh, aggregated_data)
                del self.tmp_sensor_data_dict[sensor_id][current_yyyymmdd_hh]
                self.__save_tmp_sensor_data()

            return
        else:
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
                if type(d[11]) is str:
                    # if extra is a string, parse it as JSON
                    extra = json.loads(d[11])
                elif type(d[11]) is dict:
                    # if extra is already a dict, use it as is
                    extra = d[11]
                else:
                    # if extra is neither, raise an error
                    raise ValueError(f"Unexpected type for extra: {type(d[11])}")
            except Exception as e:
                logger.exception(f"Failed to parse extra JSON: {d[11]} - {e}")
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
                    "location_id": d[9],
                    "created_at": datetime.strptime(d[10], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).astimezone(),
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
            "updated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
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
        light_status_point = 0

        max_watering_sec = 0
        min_soil_moisture = 1000

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
                                light_status_point += light_status["confidence"]
                            else:
                                light_status_point -= light_status["confidence"]
                except Exception as e:
                    logger.exception(f"Failed to aggregate light status: {e}:{elem['extra']}")

                # watering sec
                if "watering" in elem["extra"]:
                    max_watering_sec = max(
                        max_watering_sec,
                        elem["extra"]["watering"],
                    )

                # min soil moisture
                if "last_soil_moisture" in elem["extra"]:
                    min_soil_moisture = min(
                        min_soil_moisture,
                        elem["extra"]["last_soil_moisture"],
                    )

        avg_temp = sum(temps) / len(temps) if len(temps) > 0 else -1000
        avg_tds = sum(tdss) / len(tdss) if len(tdss) > 0 else -1000
        led_status = True if light_status_point > 0 else False
        print(f"led_status: {led_status}, light_status_point: {light_status_point}")
        print(f"detailed light status: {light_status_list}")
        # construct extra
        extra = {
            "light_status": {
                "status": led_status,
            },
            "max_watering_sec": max_watering_sec if max_watering_sec > 0 else None,
            "min_soil_moisture": min_soil_moisture if min_soil_moisture < 1000 else None,
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
        self.db_connector.upsert_aggregated_sensor_data(
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
