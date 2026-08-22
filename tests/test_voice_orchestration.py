from app.voice.controller import VoiceController
from app.orchestration.context_manager import ContextManager
from app.devices.mqtt_client import MQTTClient
from app.devices.mqtt_device import MQTTDeviceExecutor
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.state import Room, Mode

def main():

    # ==========================================================
    # CONTEXT
    # ==========================================================

    context = ContextManager()
    print("\n[DEBUG] Initial Room:", context.get_current_room())
    print("[DEBUG] Initial Mode:", context.get_current_mode())

    # ==========================================================
# TEST INITIAL STATE
# ==========================================================

    context.set_current_room(Room.SLEEP_ROOM)
    context.set_mode(Mode.SLEEP)

    # ==========================================================
    # MQTT
    # ==========================================================

    mqtt_client = MQTTClient(
        broker_host="localhost",
        broker_port=1883,
        client_id="voice_orchestrator"
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
    # VOICE CONTROLLER
    # ==========================================================

    voice_controller = VoiceController()

    # ==========================================================
    # GET VOICE INTENT
    # ==========================================================

    result = voice_controller.run()

    if result is None:

        print("\nNo valid command received.")

        mqtt_client.disconnect()

        return

    # ==========================================================
    # CHECK ACCEPTED INTENT
    # ==========================================================

    intent = result.get("intent")

    if not intent:

        print("\nNo intent returned.")

        mqtt_client.disconnect()

        return

    print("\n" + "=" * 70)
    print("VOICE → ORCHESTRATION")
    print("=" * 70)

    print(
        f"Intent → {intent}"
    )

    # ==========================================================
    # EXECUTE WORKFLOW
    # ==========================================================

    try:

        orchestrator.execute_intent(
            intent
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
