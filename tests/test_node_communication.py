import time

from app.devices.node_communication import NodeCommunication


esp32_a = NodeCommunication("esp32_a")
esp32_c = NodeCommunication("esp32_c")


esp32_a.connect()
esp32_c.connect()

time.sleep(1)


print("\n" + "=" * 70)
print("ESP32-A → ESP32-C TRANSITION REQUEST")
print("=" * 70)

esp32_a.send_message(
    target="esp32_c",
    message_type="TRANSITION_REQUEST",
    data={
        "destination": "STUDY_ROOM"
    }
)


time.sleep(2)


esp32_a.disconnect()
esp32_c.disconnect()