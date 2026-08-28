"""Manual MQTT integration script: PREPARE_FOR_SLEEP from the Relax Room.

Requires a running MQTT broker and the three simulated nodes:

    python -m app.devices.simulated_node esp32_a
    python -m app.devices.simulated_node esp32_b
    python -m app.devices.simulated_node esp32_c

Run with:

    python -m tests.test_mqtt_sleep_workflow

This script executes through Orchestrator.execute_intent(), which is the
only authoritative workflow execution path. The Orchestrator owns
current_room, current_mode, and return_target; MQTTDeviceExecutor only
carries actions to the nodes and waits for acknowledgements.

It previously called executor.execute_workflow() directly. That performs
transport without committing any logical state, so the script reported ten
successful actions and then printed a final state still claiming the user
was in the Relax Room. The workflow-level state authority must not be
bypassed by anything that goes on to present state as authoritative.

Expected outcome on success:

    current_room  = SLEEP_ROOM
    current_mode  = SLEEP
    return_target = RELAX_ROOM
"""

from app.devices.mqtt_client import MQTTClient
from app.devices.mqtt_device import (
    ActionExecutionError,
    MQTTDeviceExecutor,
)
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

    # Start from the Relax Room, mid-session.
    context.set_current_room(
        Room.RELAX_ROOM
    )

    context.set_return_target(
        Room.STUDY_ROOM
    )

    context.set_mode(
        Mode.RELAX
    )

    context.state.relax.light = PowerState.ON
    context.state.relax.tv = PowerState.ON

    # ==========================================================
    # INITIAL STATE
    # ==========================================================

    print("\n" + "=" * 70)
    print("INITIAL STATE")
    print("=" * 70)

    context.print_state()

    # ==========================================================
    # MQTT
    # ==========================================================

    print("\n" + "=" * 70)
    print("EXECUTING SLEEP WORKFLOW THROUGH MQTT")
    print("=" * 70)

    mqtt_client = MQTTClient(
        broker_host="localhost",
        broker_port=1883,
        client_id="sleep_workflow_test"
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
    # EXECUTE SLEEP INTENT
    # ==========================================================

    try:

        results = orchestrator.execute_intent(
            "PREPARE_FOR_SLEEP"
        )

        print("\n" + "=" * 70)
        print("SLEEP WORKFLOW COMPLETED SUCCESSFULLY")
        print("=" * 70)

        print(
            f"Acknowledged {len(results)} actions."
        )

    except ActionExecutionError as error:

        # ------------------------------------------------------
        # CONTROLLED ACTION FAILURE
        # ------------------------------------------------------

        print("\n" + "=" * 70)
        print("SLEEP WORKFLOW FAILED")
        print("=" * 70)

        print(
            f"Reason: {error}"
        )

        print(
            "\nRemaining workflow actions were not executed. "
            "Room and mode were deliberately left uncommitted."
        )

        context.print_state()

    except Exception as error:

        # ------------------------------------------------------
        # UNEXPECTED FAILURE
        # ------------------------------------------------------

        print("\n" + "=" * 70)
        print("SLEEP WORKFLOW ERROR")
        print("=" * 70)

        print(
            f"Unexpected error: {error}"
        )

        context.print_state()

    finally:

        input(
            "\nPress ENTER to disconnect..."
        )

        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
