import kaleido
from plotly import graph_objs as go
from plotly.subplots import make_subplots
from plotly.offline import plot
from datetime import datetime, timezone
from ina_device_hub.notification import Notification

if __name__ == "__main__":
    # test the plotly graph creation
    fig = make_subplots(rows=1, cols=1)
    fig.add_trace(go.Scatter(x=[1, 2, 3], y=[4, 5, 6], mode="lines+markers", name="Test Line"))
    fig.update_layout(title="Test Plotly Graph", xaxis_title="X Axis", yaxis_title="Y Axis")
    print("Plotly graph created successfully.")

    # notify image sending
    image_tuples = [("test_image.png", fig.to_image(format="png"))]
    Notification.send_discord_message_with_image("Test message with image", image_tuples)
    print("Notification sent with image.")
