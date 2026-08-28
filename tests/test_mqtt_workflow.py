"""Manual MQTT integration script: RELAX_MODE from the Study Room.

Requires a running MQTT broker and the three simulated nodes:

    python -m app.devices.simulated_node esp32_a
    python -m app.devices.simulated_node esp32_b
    python -m app.devices.simulated_node esp32_c

Run with:

    python -m tests.test_mqtt_workflow

This script executes through Orchestrator.execute_intent(), which is the
only authoritative workflow execution path. The Orchestrator owns
current_room, current_mode, and return_target; MQTTDeviceExecutor only
carries actions to the nodes and waits for acknowledgements. Do not call
executor.execute_workflow() here: it performs transport without committing
any logical state, so the state it printed afterwards was meaningless.
"""

from app.devices.mqtt_client import MQTTClient
from app.devices.mqtt_device import MQTTDeviceExecutor
from app.orchestration.context_manager import ContextManager
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.state import (
    Mode,
    PowerState,
    Room,
)


def main():

    # ==========================================================
    # CONTEXT
    # ==========================================================

    context = ContextManager()

    context.set_current_room(
        Room.STUDY_ROOM
    )

    context.set_mode(
        Mode.STUDY
    )

    context.state.study.light = PowerState.ON

    print("\n" + "=" * 70)
    print("INITIAL STATE")
    print("=" * 70)

    context.print_state()

    # ==========================================================
    # MQTT
    # ==========================================================

    mqtt_client = MQTTClient(
        broker_host="localhost",
        broker_port=1883,
        client_id="workflow_test"
    )

    mqtt_client.connect()

    executor = MQTTDeviceExecutor(
        mqtt_client
    )

    # ==========================================================
    # ORCHESTRATOR
    # ==========================================================

    orchestrator = Orchestrator(
        context=context,
        device_executor=executor
    )

    # ==========================================================
    # EXECUTE RELAX INTENT
    # ==========================================================

    try:

        orchestrator.execute_intent(
            "RELAX_MODE"
        )

    except Exception as error:

        print("\n" + "=" * 70)
        print("WORKFLOW FAILED")
        print("=" * 70)

        print(
            f"Reason: {error}"
        )

        print(
            "\nRemaining workflow actions were not executed, and "
            "room/mode were not committed."
        )

    finally:

        input(
            "\nPress ENTER to disconnect..."
        )

        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
