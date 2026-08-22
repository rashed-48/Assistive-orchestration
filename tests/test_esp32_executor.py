from threading import Thread
from time import sleep

from flask import Flask, request, jsonify

from app.orchestration.actions import Action, ActionType
from app.devices.esp32_device import ESP32DeviceExecutor


# ======================================================
# FAKE ESP32 SERVER
# ======================================================

app = Flask(__name__)


@app.route("/command", methods=["POST"])
def command():

    data = request.get_json()

    print("\n" + "=" * 70)
    print("FAKE ESP32 RECEIVED")
    print("=" * 70)

    print(data)

    return jsonify({
        "status": "success",
        "device": data["device"],
        "action": data["action"]
    })


def run_server():

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False
    )


# ======================================================
# START FAKE ESP32
# ======================================================

server_thread = Thread(
    target=run_server,
    daemon=True
)

server_thread.start()

sleep(1)


# ======================================================
# CREATE ESP32 EXECUTOR
# ======================================================

executor = ESP32DeviceExecutor(
    "http://127.0.0.1:5000"
)


# ======================================================
# TEST ACTION
# ======================================================

action = Action(
    ActionType.LIGHT_ON,
    "study_light"
)


print("\n" + "=" * 70)
print("SENDING COMMAND TO ESP32")
print("=" * 70)

result = executor.execute(action)


print("\n" + "=" * 70)
print("ESP32 RESPONSE")
print("=" * 70)

print(result)