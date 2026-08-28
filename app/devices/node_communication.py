import json

import paho.mqtt.client as mqtt


class NodeCommunication:

    def __init__(self, node_id: str):

        self.node_id = node_id

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"node_comm_{node_id}"
        )

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

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
                f"[{self.node_id}] "
                "Node communication connected"
            )

            self.client.subscribe(
                "assistive/node/#",
                qos=1
            )

        else:

            print(
                f"[{self.node_id}] "
                f"Connection failed: {reason_code}"
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

            source = payload.get("source")
            target = payload.get("target")
            message_type = payload.get("type")
            data = payload.get("data", {})

            if target != self.node_id:
                return

            print(
                f"\n[{self.node_id}] "
                "NODE MESSAGE RECEIVED"
            )

            print(f"Source : {source}")
            print(f"Type   : {message_type}")

            # --------------------------------------------------
            # PING
            # --------------------------------------------------

            if message_type == "PING":

                self.send_message(
                    target=source,
                    message_type="ACK",
                    data={
                        "original_type": "PING"
                    }
                )

            # --------------------------------------------------
            # TRANSITION REQUEST
            # --------------------------------------------------

            elif message_type == "TRANSITION_REQUEST":

                destination = data.get(
                    "destination"
                )

                print(
                    f"[{self.node_id}] "
                    f"Transition requested -> "
                    f"{destination}"
                )

                # Simulate the node completing
                # its local transition work.
                self.handle_transition(
                    destination
                )

                self.send_message(
                    target=source,
                    message_type="TRANSITION_COMPLETE",
                    data={
                        "destination": destination,
                        "status": "success"
                    }
                )

        except Exception as error:

            print(
                f"[{self.node_id}] "
                f"Node message error: {error}"
            )

    def handle_transition(
        self,
        destination: str
    ):

        print(
            f"[{self.node_id}] "
            f"Handling transition to "
            f"{destination}"
        )

        # This is intentionally only a simulation
        # for now.
        #
        # Later this will execute the actual
        # local device actions.

    def connect(self):

        self.client.connect(
            "localhost",
            1883
        )

        self.client.loop_start()

    def send_message(
        self,
        target: str,
        message_type: str,
        data: dict | None = None
    ):

        payload = {
            "source": self.node_id,
            "target": target,
            "type": message_type,
            "data": data or {}
        }

        topic = (
            f"assistive/node/{target}"
        )

        self.client.publish(
            topic,
            json.dumps(payload),
            qos=1
        )

        print(
            f"[{self.node_id}] "
            f"Sent {message_type} -> {target}"
        )

    def disconnect(self):

        self.client.loop_stop()
        self.client.disconnect()