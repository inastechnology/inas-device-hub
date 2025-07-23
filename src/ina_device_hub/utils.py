from plotly import graph_objs as go
from plotly.subplots import make_subplots
from plotly.offline import plot
from datetime import datetime, timezone


class Utils:
    @staticmethod
    def create_latest_aggregated_graph_as_html(sensor_id, latest_aggregated_data):
        return plot(Utils.__create_latest_aggregated_graph(sensor_id, latest_aggregated_data), output_type="div")

    @staticmethod
    def create_latest_aggregated_graph_as_image(sensor_id, latest_aggregated_data):
        fig = Utils.__create_latest_aggregated_graph(sensor_id, latest_aggregated_data)
        if fig is None:
            return None
        return fig.to_image(format="png")

    @staticmethod
    def __create_latest_aggregated_graph(sensor_id, latest_aggregated_data):
        if latest_aggregated_data is None:
            return None

        # construct data
        temp_x = []
        temp_y = []
        tds_x = []
        tds_y = []
        watering_x = []
        watering_y = []
        moisture_x = []
        moisture_y = []

        for data in latest_aggregated_data:
            if "temp" in data and data["temp"] != -1000:
                temp_x.append(data["yyyymmddhh"])
                temp_y.append(data["temp"])
            if "tds" in data and data["tds"] != -1000:
                tds_x.append(data["yyyymmddhh"])
                tds_y.append(data["tds"])
            if "extra" in data:
                if "max_watering_sec" in data["extra"] and data["extra"]["max_watering_sec"] is not None and data["extra"]["max_watering_sec"] > 0:
                    watering_x.append(data["created_at"].astimezone().strftime("%Y-%m-%d %H:%M:%S"))
                    watering_y.append(data["extra"]["max_watering_sec"])
                if "min_soil_moisture" in data["extra"] and data["extra"]["min_soil_moisture"] is not None and 0 < data["extra"]["min_soil_moisture"] < 100:
                    moisture_x.append(data["created_at"].astimezone().strftime("%Y-%m-%d %H:%M:%S"))
                    moisture_y.append(data["extra"]["min_soil_moisture"])

        _rows = 0
        _cols = 0
        current_row = 1
        current_col = 1
        is_exist_temp_tds = len(temp_x) > 0 and len(tds_x) > 0
        if is_exist_temp_tds:
            _rows += 1
            _cols += 2  # temp and tds

        is_exist_watering_moisture = (len(watering_x) > 0 and len(watering_y) > 0) or (len(moisture_x) > 0 and len(moisture_y) > 0)
        if is_exist_watering_moisture:
            _rows += 1
            _cols += 1  # watering and soil moisture in the same subplot
        fig = make_subplots(rows=_rows, cols=_cols)
        fig.update_layout(title="Latest Sensor Data")

        if is_exist_temp_tds:
            # temp
            temp = go.Scatter(x=temp_x, y=temp_y, mode="lines+markers", name="temp")
            fig.add_trace(temp, row=current_row, col=current_col)
            current_col += 1

            # tds
            tds = go.Scatter(x=tds_x, y=tds_y, mode="lines+markers", name="tds")
            fig.add_trace(tds, row=current_row, col=current_col)
            current_row += 1
            current_col = 1

        if is_exist_watering_moisture:
            # watering & soil moisture
            # watering is shown as bar chart
            watering = go.Bar(x=watering_x, y=watering_y, name="watering")
            # soil moisture is shown as line chart
            moisture = go.Scatter(x=moisture_x, y=moisture_y, mode="lines+markers", name="soil moisture", line=dict(color="green", width=2, dash="dash"))
            # overlay watering and soil moisture in the same subplot
            fig.add_trace(watering, row=current_row, col=current_col)
            fig.add_trace(moisture, row=current_row, col=current_col)

        # add layout h:480px
        fig.update_layout(height=480, template="plotly_white")

        return fig
