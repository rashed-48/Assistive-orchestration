import json
import sys

import paho.mqtt.client as mqtt

from app.devices.local_node_controller import (
    LocalNodeController
)

from app.devices.node_devices import (
    ESP32_A_DEVICES,
    ESP32_B_DEVICES,
    ESP32_C_DEVICES,
)

from app.orchestration.actions import (
    Action,
    ActionType,
)


BROKER_HOST = "localhost"
BROKER_PORT = 1883


# ==============================================================
# DEVICE OWNERSHIP
# ==============================================================

NODE_DEVICES = {

    "esp32_a": ESP32_A_DEVICES,

    "esp32_b": ESP32_B_DEVICES,

    "esp32_c": ESP32_C_DEVICES,
}


class SimulatedESP32:

    def __init__(
        self,
        node_id: str
    ):

        self.node_id = node_id

        # ------------------------------------------------------
        # Command topic
        # ------------------------------------------------------

        self.command_topic = (
            f"assistive/command/{node_id}"
        )

        # ------------------------------------------------------
        # Status topic
        # ------------------------------------------------------

        self.status_topic = (
            f"assistive/status/{node_id}"
        )

        # ------------------------------------------------------
        # Local hardware controller
        # ------------------------------------------------------

        self.controller = LocalNodeController(

            node_id=node_id,

            devices=NODE_DEVICES[node_id]
        )

        # ------------------------------------------------------
        # MQTT client
        # ------------------------------------------------------

        self.client = mqtt.Client(

            mqtt.CallbackAPIVersion.VERSION2,

            client_id=f"simulator_{node_id}"
        )

        self.client.on_connect = (
            self.on_connect
        )

        self.client.on_message = (
            self.on_message
        )

    # ==========================================================
    # MQTT CONNECTED
    # ==========================================================

    def on_connect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties
    ):

        if reason_code == 0:

            print(
                f"[{self.node_id}] "
                "Connected to MQTT broker"
            )

            self.client.subscribe(
                self.command_topic,
                qos=1
            )

            print(
                f"[{self.node_id}] "
                f"Listening on "
                f"{self.command_topic}"
            )

        else:

            print(
                f"[{self.node_id}] "
                f"Connection failed: "
                f"{reason_code}"
            )

    # ==========================================================
    # COMMAND RECEIVED
    # ==========================================================

    def on_message(
        self,
        client,
        userdata,
        message
    ):

        payload = {}

        try:

            # --------------------------------------------------
            # Decode JSON
            # --------------------------------------------------

            payload = json.loads(
                message.payload.decode()
            )

            # --------------------------------------------------
            # Extract command
            # --------------------------------------------------

            device = payload["device"]

            action_name = payload["action"]

            parameters = payload.get(
                "parameters",
                {}
            )

            command_id = payload.get(
                "command_id"
            )

            print(
                "\n" + "=" * 60
            )

            print(
                f"[{self.node_id}] "
                "COMMAND RECEIVED"
            )

            print(
                f"Device     : "
                f"{device}"
            )

            print(
                f"Action     : "
                f"{action_name}"
            )

            print(
                f"Command ID : "
                f"{command_id}"
            )

            print(
                f"Parameters : "
                f"{parameters}"
            )

            print(
                "=" * 60
            )

            # --------------------------------------------------
            # Convert action name → ActionType
            # --------------------------------------------------

            action_type = ActionType[
                action_name
            ]

            # --------------------------------------------------
            # Create Action object
            # --------------------------------------------------

            action = Action(
                action_type,
                device
            )

            # --------------------------------------------------
            # Execute locally
            # --------------------------------------------------

            self.controller.execute(
                action
            )

            # --------------------------------------------------
            # Report success
            # --------------------------------------------------

            self.publish_status(

                device=device,

                action=action_name,

                status="success",

                command_id=command_id
            )

        except Exception as error:

            print(
                f"[{self.node_id}] "
                f"Command error: "
                f"{error}"
            )

            # --------------------------------------------------
            # Report failure
            # --------------------------------------------------

            self.publish_status(

                device=payload.get(
                    "device",
                    "unknown"
                ),

                action=payload.get(
                    "action",
                    "unknown"
                ),

                status="error",

                command_id=payload.get(
                    "command_id"
                )
            )

    # ==========================================================
    # PUBLISH STATUS
    # ==========================================================

    def publish_status(
        self,
        device,
        action,
        status,
        command_id=None
    ):

        payload = {

            "command_id": command_id,

            "node": self.node_id,

            "device": device,

            "action": action,

            "status": status,
        }

        self.client.publish(

            self.status_topic,

            json.dumps(payload),

            qos=1
        )

        print(
            f"[{self.node_id}] "
            "Status published"
        )

    # ==========================================================
    # START NODE
    # ==========================================================

    def start(self):

        print(
            f"\nStarting simulated "
            f"{self.node_id}"
        )

        self.client.connect(

            BROKER_HOST,

            BROKER_PORT
        )

        self.client.loop_forever()


# ==============================================================
# MAIN
# ==============================================================

if __name__ == "__main__":

    if len(sys.argv) != 2:

        print(
            "Usage:"
        )

        print(
            "python -m "
            "app.devices.simulated_node "
            "<esp32_a|esp32_b|esp32_c>"
        )

        sys.exit(1)

    node_id = sys.argv[1]

    if node_id not in NODE_DEVICES:

        print(
            "Invalid node."
        )

        print(
            "Use:"
        )

        print(
            "  esp32_a"
        )

        print(
            "  esp32_b"
        )

        print(
            "  esp32_c"
        )

        sys.exit(1)

    node = SimulatedESP32(
        node_id
    )

    node.start()