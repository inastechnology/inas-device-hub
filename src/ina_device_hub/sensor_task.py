import json
from ina_device_hub.setting import setting

from croniter import croniter
from datetime import datetime, timedelta, timezone
import struct


class SensorTask:
    taskName2Id = {
        "sensorDataReport": 0x01,
        "cameraImageCapture": 0x02,
        "audioCapture": 0x03,
        "fertilizer": 0x04,
        "watering": 0x05,
    }

    def __init__(self):
        self.sensor_task_dict = setting().get("sensor").get("task", {})

    def get_next_task(self, device_id: str, current_time: datetime = datetime.now()) -> tuple:
        """
        Get the task for the specified device ID.
        If the task is not found or the cron expression is invalid, return None.
        """
        sensorTaskList = self.sensor_task_dict.get(device_id, {}).get("tasks", [])
        if not sensorTaskList:
            return None

        # タスクごとの次の実行時間を計算して保持
        for task in sensorTaskList:
            cron_expression = task.get("schedule")
            if not cron_expression:
                continue
            cron = croniter(cron_expression, current_time)
            next_datetime = cron.get_next(datetime)
            task["next_datetime"] = next_datetime

        # 次の実行時間が最も近いタスクを取得(複数ある場合はすべて取得
        next_exec_time = min(task["next_datetime"] for task in sensorTaskList if "next_datetime" in task)
        until_next_exec_time = int((next_exec_time - current_time).total_seconds())
        next_tasks = [task for task in sensorTaskList if task.get("next_datetime") == next_exec_time]

        return until_next_exec_time, next_tasks

    def convert_tasks_to_bytes(self, tasks: list, until_next_exec_time: int) -> bytes:
        """
        Convert the list of tasks to bytes.
        """
        ret_bytes = bytes()
        # magic number for task data
        ret_bytes += struct.pack(">H", 0x1A5D)
        # next execution time 2 bytes
        ret_bytes += struct.pack(">H", until_next_exec_time)

        # tasks
        for task in tasks:
            task_name = task.get("taskName")
            task_id = self.taskName2Id.get(task_name)
            if not task_id:
                continue

            # Convert the task ID to bytes (1 bytes for unsigned short)
            ret_bytes += struct.pack(">B", task_id)

            # payload for the task (3 bytes)
            payload = b""
            if task_name == "sensorDataReport":
                payload = b"\x00\x00\x00"
            elif task_name == "fertilizer":
                # 1byte pump ID
                payload = struct.pack(">B", task.get("pumpId", 0))
                # 2 bytes duration in seconds
                payload += struct.pack(">H", task.get("durationSec", 0))
            elif task_name == "watering":
                # 1byte valve ID
                payload = struct.pack(">B", task.get("valveId", 0))
                # 2 bytes duration in seconds
                payload += struct.pack(">H", task.get("durationSec", 0))
            else:
                # For other tasks, we can just use 3 bytes of zero
                payload = b"\x00\x00\x00"
            # Ensure payload is 3 bytes
            if len(payload) < 3:
                payload += b"\x00" * (3 - len(payload))
            elif len(payload) > 3:
                payload = payload[:3]
            ret_bytes += payload

        # Calculate XOR checksum
        checksum = 0
        for byte in ret_bytes:
            checksum ^= byte
        # Append checksum
        ret_bytes += struct.pack(">B", checksum)
        return ret_bytes


if __name__ == "__main__":
    sensor_task = SensorTask()
    device_id = "INADS-110387bd-baaa-441b-ada9-0ab58407fd2c"
    current_time = datetime(year=2025, month=1, day=1, hour=7, minute=50, second=0)
    until_next_exec_time, next_tasks = sensor_task.get_next_task(device_id, current_time)
    print("Next task for device ID:", device_id)
    print("Current time:", current_time)
    print("Next execution time:", until_next_exec_time, "seconds")
    print("Next task for device:")
    for task in next_tasks:
        print(f"Task Name: {task.get('taskName')}, Next Execution: {task.get('next_datetime')}")

    # convert tasks to bytes
    if next_tasks:
        ret_bytes = sensor_task.convert_tasks_to_bytes(next_tasks, until_next_exec_time)
        print("Task bytes:", ret_bytes)
        print(f"request for sensor: 0x{ret_bytes.hex()}")
