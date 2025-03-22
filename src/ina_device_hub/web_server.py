import os
import uuid
from datetime import datetime, timezone, UTC

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    render_template_string,
    request,
)

from ina_device_hub.camera_connector import camera_connector
from ina_device_hub.camera_device_repository import camera_device_repository
from ina_device_hub.camera_image_repository import camera_image_repository
from ina_device_hub.ina_db_connector import ina_db_connector
from ina_device_hub.location_repository import location_repository
from ina_device_hub.sensor_data_repository import sensor_data_repository
from ina_device_hub.sensor_device_repository import sensor_device_repository
from ina_device_hub.sensor_image_repogitory import sensor_image_repogitory
from ina_device_hub.setting import setting
from ina_device_hub.storage_connector import storage_connector
from ina_device_hub.utils import Utils

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    sensors = sensor_device_repository().get_all()
    locations = location_repository().get_all()
    cameras = camera_connector().camera_device_repository.get_all()
    template = """
    <html>
      <body>
        <h1>INA Device Hub</h1>
        <h2>sensors</h2>
        <ul>
          {% for sensor_id, info in sensors.items() %}
          <li>
            <a href="/sensors/{{ info.id }}">{{ info.name }}</a>
          </li>
          {% endfor %}
        </ul>
        <h2>Cameras</h2>
        <ul>
          {% for sensor_id, info in cameras.items() %}
          <li>
            <a href="/camera/{{ info.id }}/preview">{{ info.name }}</a>
          </li>
          {% endfor %}
        </ul>
        <h2>locations</h2>
        <botton onclick="location.href='/locations'">Add</botton>
        <ul>
          {% for location, info in locations.items() %}
          <li>
            <a href="/locations/{{ info.id }}">{{ info.name }}</a>
          </li>
          {% endfor %}
        </ul>
      </body>
    </html>
    """

    return render_template_string(template, sensors=sensors, locations=locations, cameras=cameras)


@app.route("/sensors/<sensor_id>", methods=["GET"])
def get_sensor_info(sensor_id):
    sensor_info = sensor_device_repository().get_by_id(sensor_id)
    if sensor_info is None:
        return jsonify({"error": "device not found"}), 404

    latest_sensor_data = sensor_data_repository().get_latest(sensor_id)
    latest_aggregated_data = sensor_data_repository().get_latest_aggreated(sensor_id)

    # plotly でグラフを描画
    # 画像を base64 エンコードして HTML に埋め込む
    agg_sensor_graph = Utils.create_latest_aggregated_graph_as_html(sensor_id, latest_aggregated_data)

    template = """
    <html>
      <body>
        <h1>INA Device Hub</h1>
        <h2>{{ sensor_id }}</h2>
          <li>Name: {{ info.name }}</li>
          <li>Location: {{ info.location }}</li>
          <li>Info: {{ info.info }}</li>
        <br>
        <h2>Last Sensor Data ({{ latest_sensor_data.updated_at }})</h2>
        <ul>
          <li>Temp: {{ latest_sensor_data.temp }}</li>
          <li>TDS: {{ latest_sensor_data.tds }}</li>
        </ul>
        <br>
        <h2>Graph</h2>
        <div>
          {{ agg_sensor_graph | safe }}
        </div>
        <br>
        <botton onclick="location.href='/sensors/{{ sensor_id }}/latest_image'">Latest Image</botton>
        <botton onclick="location.href='/sensors/{{ sensor_id }}/edit'">Edit</botton>
      </body>
    </html>
    """

    return render_template_string(
        template,
        sensor_id=sensor_id,
        info=sensor_info,
        agg_sensor_graph=agg_sensor_graph,
        latest_sensor_data=latest_sensor_data,
    )


@app.route("/sensors/<sensor_id>/edit", methods=["GET", "POST"])
def edit_sensor_info(sensor_id):
    sensor_info = sensor_device_repository().get(sensor_id)
    if not sensor_info:
        return jsonify({"error": "device not found"}), 404

    if request.method == "POST":
        new_info = request.form.get("info")
        sensor_device_repository().add(sensor_id, new_info)
        return jsonify({"message": "updated"})

    device_name = sensor_info.get("name", "")
    device_location = sensor_info.get("location", "")
    template = """
    <html>
      <body>
        <h1>INA Device Hub</h1>
        <h2>Edit Device Info</h2>
        <form method="post">
          <label for="info">Info</label>
          <input type="text" id="name" name="name" value="{{ device_name }}">
            <label for="location">Location</label>
            <input type="text" id="location" name="location" value="{{ device_location }}">
            <br>
            <br>
            <a href="/sensors/{{ sensor_id }}">Back</a>
            <br>
            <br>
          <button type="submit">Submit</button>
        </form>
      </body>
    </html>
    """

    return render_template_string(
        template,
        device_name=device_name,
        device_location=device_location,
        sensor_id=sensor_id,
    )


@app.route("/sensors/<sensor_id>/latest_image", methods=["GET"])
def get_latest_image(sensor_id):
    """
    デバイスIDに紐づく最新の画像を取得するエンドポイント

    Parameters
    ----------
    sensor_id : str
        デバイスID

    Returns
    -------
    response : http response
        デバイスIDに紐づく最新の画像を base64 エンコードしたもの
    """
    image_repo = sensor_image_repogitory()
    sensor_images = image_repo.fetch_latest(sensor_id, limit=24)
    if not sensor_images:
        return jsonify({"error": "no image"}), 404

    return render_template("image_page.html", sensor_images=sensor_images, sensor_id=sensor_id)


@app.route("/locations", methods=["GET"])
def get_location_list():
    locations = location_repository().get_all()
    for location_id, info in locations.items():
        sensors = sensor_device_repository().get_by_location(location_id)
        info["sensors"] = sensors

    template = """
    <html>
      <body>
        <h1>INA Device Hub</h1>
        <h2>Locations</h2>
        <ul>
          {% for location_id, info in locations.items() %}
          <li>
            <a href="/locations/{{ location_id }}">{{ location_id }}</a>
          </li>
          {% endfor %}
          <li>
            <a href="/locations/public">Public Location</a>
          </li>
        </ul>
        <botton onclick="location.href='/ctrl/locations/add'">Add</botton>
      </body>
    </html>
    """

    return render_template_string(template, locations=locations)


@app.route("/locations/<location_id>", methods=["GET"])
def get_location_detail(location_id):
    if location_id == "public":
        location_id = None
    location_info = location_repository().get(location_id)
    if location_info is None:
        return jsonify({"error": "location not found"}), 404

    # sensor info
    sensors = sensor_device_repository().get_by_location(location_id)
    for sensor in sensors:
        if sensor["name"] is None:
            sensor["name"] = sensor["id"]
        sensor["latest"] = sensor_data_repository().get_latest(sensor["id"])
        sensor["latest_aggreated"] = sensor_data_repository().get_latest_aggreated(sensor["id"])
        # create graph
        sensor["graph"] = Utils.create_latest_aggregated_graph_as_html(sensor["id"], sensor["latest_aggreated"])

    # camera info
    cameras = camera_device_repository().get_by_location(location_id)
    camera_latest_images = {}
    for camera in cameras:
        # {'id': 'INACD-a0b189d8-d789-4087-96d9-db91ecaf25c0',
        # 'name': 'INACD-a0b189d8-d789-4087-96d9-db91ecaf25c0',
        # 'location_id': None, 'type': 'INACD', 'timelapse': True,
        # 'ip_address': '192.168.xxx.xxx', 'username': '',
        # 'password': '[REDACTED]'}
        today_images = camera_image_repository().get_date_image_by_id(camera["id"], datetime.now(UTC), limit=6 * 24)

        camera_latest_images[camera["id"]] = today_images[0] if today_images else None

    if location_id is None:
        location_id = "public"
    template = """
    <html>
        <body>
        <h1>INA Device Hub</h1>
        <h2>{{ location_id }}</h2>
        <ul>
            <li>Name: {{ info.name }}</li>
            <li>Description: {{ info.description }}</li>
        </ul>
        <h2>Sensors</h2>
        <!-- show sensor stat card -->
        <ul>
            {% for sensor in sensors %}
            <li>
                <h3>{{ sensor.name }}</h3>
                <h4>Latest Data</h4>
                <ul>
                    <li>Temp: {{ sensor.latest.temp }}</li>
                    <li>TDS: {{ sensor.latest.tds }}</li>
                </ul>
                <div>
                    {{ sensor.graph | safe }}
                </div>
            </li>
            {% endfor %}
        </ul>
        <h2>Cameras</h2>
        <!-- show camera image -->
        <ul>
            {% for camera in cameras %}
            <li>
                <h3>{{ camera.name }}</h3>
                <ul>
                    <li>Location: {{ camera.location_id }}</li>
                    <li>Type: {{ camera.type }}</li>
                    <li>Timelapse: {{ camera.timelapse }}</li>
                    <li>IP Address: {{ camera.ip_address }}</li>
                    <li>Username: {{ camera.username }}</li>
                    <li>Password: REDACTED</li>
                </ul>
                <div>
                    <img 
                        src="{{ camera_latest_images[camera.id].presigned_url }}" 
                        alt="latest image" 
                        style="max-width: 100%; height: auto; display: block;"
                    >
                </div>
            </li>
            {% endfor %}
        </ul>
        <br>
        <botton onclick="location.href='/locations'">Back</botton>
        </body>
    </html>
    """

    return render_template_string(
        template, location_id=location_id, info=location_info, sensors=sensors, cameras=cameras, camera_latest_images=camera_latest_images
    )


@app.route("/ctrl/locations/add", methods=["GET", "POST"])
def add_location():
    if request.method == "POST":
        location_id = uuid.uuid4().hex
        location_name = request.form.get("location_name")
        location_description = request.form.get("location_description")
        location_image = request.files.get("location_image")
        # save image to cloud
        image_key = f"locations/{location_id}/{os.path.basename(location_image.filename)}"
        image_path = storage_connector().save_to_cloud(image_key, location_image.read(), "image/jpeg")
        location_repository().add(
            location_id,
            {
                "name": location_name,
                "description": location_description,
                "image_path": image_path,
            },
        )
        return jsonify({"message": "added"})

    template = """
    <html>
      <body>
        <h1>INA Device Hub</h1>
        <h2>Add Location</h2>
        <form method="post">
          <label for="location_name">Location Name</label>
          <input type="text" id="location_name" name="location_name">
          <label for="location_description">Location Description</label>
          <input type="text" id="location_description" name="location_description">
          <h3>Location Image</h3>
          <input type="file" id="location_image" name="location_image">
          <br>
          <br>
          <a href="/locations">Back</a>
          <br>
          <br>
          <button type="submit">Submit</button>
        </form>
      </body>
    </html>
    """

    return render_template_string(template)


@app.route("/camera/<sensor_id>", methods=["GET"])
def get_camera_info(sensor_id):
    camera_info = camera_connector().camera_device_repository.get(sensor_id)
    if camera_info is None:
        return jsonify({"error": "device not found"}), 404

    latest_image = storage_connector().fetch_files(f"{sensor_id}/timelapse", limit=10)

    template = """
    <html>
      <body>
        <h1>INA Device Hub</h1>
        <h2>{{ sensor_id }}</h2>
          <li>Name: {{ info.name }}</li>
          <li>Location: {{ info.location }}</li>
          <li>Info: {{ info.info }}</li>
        <br>
        <h2>Latest Image</h2>
        <ul>
          {% for image in latest_image %}
          <li>
           <img 
              src="{{ image.presigned_url }}" 
              alt="latest image" 
              style="max-width: 100%; height: auto; display: block;"
            >
          </li>
          {% endfor %}
        </ul>
        <br>
        <botton onclick="location.href='/camera/{{ sensor_id }}/preview'">Preview</botton>
        <botton onclick="location.href='/camera/{{ sensor_id }}/edit'">Edit</botton>
      </body>
    </html>
    """

    return render_template_string(template, sensor_id=sensor_id, info=camera_info, latest_image=latest_image)


@app.route("/camera/<sensor_id>/preview", methods=["GET"])
def preview_camera(sensor_id):
    # シンプルな HTML を生成して、sensor_id の見出しとレスポンシブな動画を表示
    html = """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Camera Stream - {{ sensor_id }}</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
            h1 { text-align: center; margin-bottom: 20px; }
            .video-container { display: flex; justify-content: center; }
            .video-container img { width: 100%; max-width: 800px; height: auto; }
        </style>
    </head>
    <body>
        <h1>Device: {{ sensor_id }}</h1>
        <div class="video-container">
            <img src="/local/api/camera/{{ sensor_id }}/video_feed" alt="Camera Stream">
        </div>
    </body>
    </html>
    """
    return render_template_string(html, sensor_id=sensor_id)


# ==========================================
# Local API
# ==========================================
@app.route("/local/api/sensors", methods=["GET"])
def get_sensors():
    sensors = sensor_device_repository().get_all()
    return jsonify(sensors)


@app.route("/local/api/locations", methods=["GET"])
def get_locations():
    locations = location_repository().get_all()
    return jsonify(locations)


@app.route("/local/api/images/<path:image_path>")
def get_image(image_path):
    image_repo = sensor_image_repogitory()
    sensor_images = image_repo.fetch_from_cloud_as_bytes(image_path)
    if not sensor_images:
        return jsonify({"error": "no image"}), 404
    return Response(sensor_images, mimetype="image/jpeg")


@app.route("/local/api/camera/<sensor_id>/video_feed")
def video_feed(sensor_id):
    # ブラウザで再生する場合、multipart/x-mixed-replace の形式で配信
    return Response(
        camera_connector().generate_frames(sensor_id),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


def flask_run():
    app.run(host="0.0.0.0", port=5151)


if __name__ == "__main__":
    setting().settings["turso"]["local_db_path"] = os.path.join(os.path.expanduser(setting().get_work_dir()), "ina_web_server.db")
    ina_db_connector()
    flask_run()
