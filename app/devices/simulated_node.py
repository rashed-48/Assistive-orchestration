import json
import sys
import threading
from collections import OrderedDict

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

    # How many completed command ids this node remembers. A real ESP32
    # has finite RAM, so the history is bounded and the oldest entries
    # are forgotten first.
    COMMAND_HISTORY_LIMIT = 128

    def __init__(
        self,
        node_id: str,
        broker_host: str = BROKER_HOST,
        broker_port: int = BROKER_PORT
    ):

        self.node_id = node_id

        self.broker_host = broker_host

        self.broker_port = broker_port

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

        self.client.on_subscribe = (
            self.on_subscribe
        )

        # Set once the broker confirms the command subscription, so a
        # caller can wait until this node can actually receive commands.
        self.ready = threading.Event()

        # Command ids this node has already carried out, mapped to the
        # status it answered with. A retry arrives with the same id and
        # must be re-acknowledged, never re-executed.
        self.processed_commands = OrderedDict()

        self.executed_count = 0
        self.duplicate_count = 0

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
    # SUBSCRIPTION CONFIRMED
    # ==========================================================

    def on_subscribe(
        self,
        client,
        userdata,
        mid,
        reason_codes,
        properties=None
    ):

        self.ready.set()

    def wait_until_ready(self, timeout=10):
        """Block until this node is subscribed to its command topic."""

        return self.ready.wait(timeout=timeout)

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
            # Duplicate command?
            #
            # The executor keeps one command id per logical action and
            # reuses it when it retries. Seeing an id we already
            # completed means the acknowledgement was lost, not that
            # the action should happen again.
            # --------------------------------------------------

            if (
                command_id is not None
                and command_id in self.processed_commands
            ):

                self.duplicate_count += 1

                previous = self.processed_commands[command_id]

                print(
                    f"[{self.node_id}] "
                    f"DUPLICATE command_id -> "
                    f"re-acknowledging without executing"
                )

                self.publish_status(
                    device=previous["device"],
                    action=previous["action"],
                    status=previous["status"],
                    command_id=command_id,
                    duplicate=True,
                )

                return

            # --------------------------------------------------
            # Convert action name -> ActionType
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

            self.executed_count += 1

            # --------------------------------------------------
            # Remember it, so a retry is not executed again.
            #
            # Only completed commands are recorded. One that raised
            # above never reaches here, so it stays retryable.
            # --------------------------------------------------

            self._remember(
                command_id,
                device=device,
                action=action_name,
                status="success",
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
    # COMMAND HISTORY
    # ==========================================================

    def _remember(self, command_id, device, action, status):

        if command_id is None:
            # Nothing to correlate a retry against.
            return

        self.processed_commands[command_id] = {
            "device": device,
            "action": action,
            "status": status,
        }

        while len(self.processed_commands) > self.COMMAND_HISTORY_LIMIT:
            self.processed_commands.popitem(last=False)

    # ==========================================================
    # PUBLISH STATUS
    # ==========================================================

    def publish_status(
        self,
        device,
        action,
        status,
        command_id=None,
        **extra
    ):

        payload = {

            "command_id": command_id,

            "node": self.node_id,

            "device": device,

            "action": action,

            "status": status,
        }

        # Additive only. The status contract stays as it was; a
        # duplicate is still a normal acknowledgement to the executor.
        payload.update(extra)

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
    # LOCAL SIMULATED HARDWARE STATE
    # ==========================================================

    def get_device_states(self) -> dict:
        """This node's simulated pin state.

        Deliberately separate from EnvironmentState: this is what the
        hardware believes, not what the application logically believes.
        """

        return self.controller.get_device_states()

    # ==========================================================
    # START / STOP
    # ==========================================================

    def connect(self):
        """Connect and service MQTT on a background thread."""

        self.client.connect(
            self.broker_host,
            self.broker_port
        )

        self.client.loop_start()

    def disconnect(self):
        """Stop servicing MQTT and leave the broker cleanly."""

        self.client.loop_stop()

        self.client.disconnect()

        print(
            f"[{self.node_id}] Disconnected from broker"
        )

    def start(self):
        """Run this node in the foreground until interrupted."""

        print(
            f"\nStarting simulated "
            f"{self.node_id} -> "
            f"{self.broker_host}:{self.broker_port}"
        )

        self.client.connect(
            self.broker_host,
            self.broker_port
        )

        try:

            self.client.loop_forever()

        except KeyboardInterrupt:

            print(
                f"\n[{self.node_id}] Shutting down"
            )

        finally:

            self.client.disconnect()

            print(
                f"[{self.node_id}] Disconnected from broker"
            )


# ==============================================================
# MAIN
# ==============================================================

if __name__ == "__main__":

    if len(sys.argv) not in (2, 4):

        print(
            "Usage:"
        )

        print(
            "python -m "
            "app.devices.simulated_node "
            "<esp32_a|esp32_b|esp32_c> "
            "[broker_host broker_port]"
        )

        sys.exit(1)

    node_id = sys.argv[1]

    host = sys.argv[2] if len(sys.argv) == 4 else BROKER_HOST

    port = int(sys.argv[3]) if len(sys.argv) == 4 else BROKER_PORT

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
        node_id,
        broker_host=host,
        broker_port=port
    )

    node.start()