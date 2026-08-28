import uuid
import warnings

from app.orchestration.actions import Action
from app.devices.device_registry import DEVICE_NODE_MAP
from app.devices.json_protocol import JSONProtocol
from app.devices.mqtt_client import MQTTClient


class ActionExecutionError(Exception):
    """Raised when an action cannot be executed successfully."""
    pass


class MQTTDeviceExecutor:

    def __init__(
        self,
        mqtt_client: MQTTClient
    ):
        self.mqtt_client = mqtt_client

    # ==========================================================
    # EXECUTE ONE ACTION WITH RETRY
    # ==========================================================

    def execute(
        self,
        action: Action,
        timeout=5,
        max_retries=2
    ):

        device_id = action.device_id

        # ------------------------------------------------------
        # Find ESP32 responsible for this device
        # ------------------------------------------------------

        if device_id not in DEVICE_NODE_MAP:

            raise ValueError(
                f"Unknown device: {device_id}"
            )

        node = DEVICE_NODE_MAP[
            device_id
        ]

        topic = (
            f"assistive/command/{node}"
        )

        # ------------------------------------------------------
        # Convert action to JSON
        # ------------------------------------------------------

        payload = JSONProtocol.action_to_dict(
            action
        )

        # ------------------------------------------------------
        # Total attempts
        #
        # max_retries = 2 means:
        #
        # Attempt 1
        # Attempt 2
        # Attempt 3
        # ------------------------------------------------------

        total_attempts = max_retries + 1

        # ------------------------------------------------------
        # One command ID for this logical action, reused by every
        # attempt.
        #
        # A retry happens because an acknowledgement did not arrive,
        # not because the action did not happen. Giving each attempt a
        # fresh id made a retry indistinguishable from a new command,
        # so a lost ACK could open the same door twice. Keeping the id
        # stable lets the node recognise the retry and re-acknowledge
        # instead of re-executing.
        # ------------------------------------------------------

        command_id = str(
            uuid.uuid4()
        )

        last_command_id = command_id

        command_payload = dict(
            payload
        )

        command_payload[
            "command_id"
        ] = command_id

        for attempt in range(
            1,
            total_attempts + 1
        ):

            print(
                "\n" + "=" * 60
            )

            print(
                "[MQTT] EXECUTING ACTION"
            )

            print(
                f"[MQTT] Attempt     -> "
                f"{attempt}/{total_attempts}"
            )

            print(
                f"[MQTT] Node        -> "
                f"{node}"
            )

            print(
                f"[MQTT] Device      -> "
                f"{device_id}"
            )

            print(
                f"[MQTT] Action      -> "
                f"{action.action_type.value}"
            )

            print(
                f"[MQTT] Command ID  -> "
                f"{command_id}"
            )

            print(
                "=" * 60
            )

            # --------------------------------------------------
            # Send command
            # --------------------------------------------------

            self.mqtt_client.publish(
                topic,
                command_payload
            )

            # --------------------------------------------------
            # Wait for matching acknowledgement
            # --------------------------------------------------

            status = (
                self.mqtt_client.wait_for_status(
                    command_id,
                    timeout=timeout
                )
            )

            # --------------------------------------------------
            # SUCCESS
            # --------------------------------------------------

            if status is not None:

                if status.get(
                    "status"
                ) == "success":

                    print(
                        "\n[MQTT] ACTION CONFIRMED"
                    )

                    print(
                        f"[MQTT] Attempt    -> "
                        f"{attempt}"
                    )

                    print(
                        f"[MQTT] Command ID -> "
                        f"{command_id}"
                    )

                    return status

                # ------------------------------------------------
                # ESP32 explicitly reported ERROR
                # ------------------------------------------------

                print(
                    "\n[MQTT] ACTION FAILED"
                )

                print(
                    f"[MQTT] ESP32 reported "
                    f"status: "
                    f"{status.get('status')}"
                )

                raise ActionExecutionError(
                    f"Device execution failed "
                    f"for {device_id}: "
                    f"{status}"
                )

            # --------------------------------------------------
            # TIMEOUT
            # --------------------------------------------------

            print(
                "\n[MQTT] ACK TIMEOUT"
            )

            print(
                f"[MQTT] No response from "
                f"{node}"
            )

            print(
                f"[MQTT] Attempt "
                f"{attempt}/{total_attempts} "
                f"failed"
            )

            # --------------------------------------------------
            # Retry if attempts remain
            # --------------------------------------------------

            if attempt < total_attempts:

                print(
                    "[MQTT] RETRYING ACTION..."
                )

                continue

            # --------------------------------------------------
            # All attempts exhausted
            # --------------------------------------------------

            print(
                "\n[MQTT] ACTION PERMANENTLY FAILED"
            )

            print(
                f"[MQTT] Node   -> {node}"
            )

            print(
                f"[MQTT] Device -> {device_id}"
            )

            print(
                f"[MQTT] Action -> "
                f"{action.action_type.value}"
            )

            raise ActionExecutionError(
                f"Action failed after "
                f"{total_attempts} attempts. "
                f"Node={node}, "
                f"Device={device_id}, "
                f"Action="
                f"{action.action_type.value}, "
                f"LastCommandID="
                f"{last_command_id}"
            )

    # ==========================================================
    # EXECUTE COMPLETE WORKFLOW
    # ==========================================================

    def execute_workflow(
        self,
        actions,
        timeout=5,
        max_retries=2
    ):
        """Execute actions sequentially without logical workflow authority.

        This compatibility helper performs transport execution only. Use
        Orchestrator.execute_intent() for authoritative workflow execution and
        ContextManager state synchronization.
        """

        warnings.warn(
            "MQTTDeviceExecutor.execute_workflow() is non-authoritative; "
            "use Orchestrator.execute_intent() for logical workflow execution.",
            DeprecationWarning,
            stacklevel=2,
        )

        results = []

        for action in actions:

            result = self.execute(
                action,
                timeout=timeout,
                max_retries=max_retries
            )

            results.append(
                result
            )

        return results
