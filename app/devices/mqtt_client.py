import json
import threading
import time

import paho.mqtt.client as mqtt


class MQTTClient:

    def __init__(
        self,
        broker_host="localhost",
        broker_port=1883,
        client_id="python_orchestrator"
    ):

        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id
        )

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        self.status_messages = []

        self.status_condition = threading.Condition()

    def _on_connect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties
    ):

        if reason_code == 0:

            print(
                "[MQTT] Connected to broker"
            )

            self.client.subscribe(
                "assistive/status/#",
                qos=1
            )

            print(
                "[MQTT] Listening for device status"
            )

        else:

            print(
                f"[MQTT] Connection failed: "
                f"{reason_code}"
            )

    def _on_message(
        self,
        client,
        userdata,
        message
    ):

        try:

            payload = json.loads(
                message.payload.decode()
            )

            with self.status_condition:

                self.status_messages.append(
                    payload
                )

                self.status_condition.notify_all()

            print(
                "\n[MQTT] STATUS RECEIVED"
            )

            print(
                f"[MQTT] Command ID → "
                f"{payload.get('command_id')}"
            )

            print(
                f"[MQTT] Node       → "
                f"{payload.get('node')}"
            )

            print(
                f"[MQTT] Device     → "
                f"{payload.get('device')}"
            )

            print(
                f"[MQTT] Action     → "
                f"{payload.get('action')}"
            )

            print(
                f"[MQTT] Status     → "
                f"{payload.get('status')}"
            )

        except Exception as error:

            print(
                f"[MQTT] Status error: "
                f"{error}"
            )

    def connect(self):

        self.client.connect(
            self.broker_host,
            self.broker_port
        )

        self.client.loop_start()

        time.sleep(0.2)

    def publish(
        self,
        topic,
        payload
    ):

        if isinstance(payload, dict):

            payload = json.dumps(
                payload
            )

        result = self.client.publish(
            topic,
            payload,
            qos=1
        )

        if result.rc == mqtt.MQTT_ERR_SUCCESS:

            print(
                f"[MQTT] Published → "
                f"{topic}"
            )

            print(
                f"[MQTT] Payload   → "
                f"{payload}"
            )

        else:

            raise RuntimeError(
                f"MQTT publish failed: "
                f"{result.rc}"
            )

    def wait_for_status(
        self,
        command_id,
        timeout=5
    ):

        deadline = time.time() + timeout

        with self.status_condition:

            while True:

                for status in self.status_messages:

                    if (
                        status.get("command_id")
                        == command_id
                    ):
                        return status

                remaining = (
                    deadline - time.time()
                )

                if remaining <= 0:

                    return None

                self.status_condition.wait(
                    timeout=remaining
                )

    def get_status_messages(self):

        with self.status_condition:

            return list(
                self.status_messages
            )

    def clear_status_messages(self):

        with self.status_condition:

            self.status_messages.clear()

    def disconnect(self):

        self.client.loop_stop()

        self.client.disconnect()

        print(
            "[MQTT] Disconnected from broker"
        )