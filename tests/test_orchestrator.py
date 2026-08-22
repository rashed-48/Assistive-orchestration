from app.orchestration.context_manager import ContextManager
from app.orchestration.state import (
    Room,
    Mode,
    PowerState,
)

from app.devices.mqtt_client import MQTTClient
from app.devices.mqtt_device import MQTTDeviceExecutor

from app.orchestration.orchestrator import Orchestrator


def main():

    # ==========================================================
    # CONTEXT
    # ==========================================================

    context = ContextManager()

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
    # MQTT
    # ==========================================================

    mqtt_client = MQTTClient(
        broker_host="localhost",
        broker_port=1883,
        client_id="orchestrator_test"
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

        orchestrator.execute_intent(
            "PREPARE_FOR_SLEEP"
        )

    except Exception as error:

        print("\n" + "=" * 70)
        print("WORKFLOW FAILED")
        print("=" * 70)

        print(
            f"Reason: {error}"
        )

    finally:

        input(
            "\nPress ENTER to disconnect..."
        )

        mqtt_client.disconnect()


if __name__ == "__main__":
    main()