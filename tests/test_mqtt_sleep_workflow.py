from app.orchestration.context_manager import ContextManager
from app.orchestration.workflow_engine import WorkflowEngine

from app.devices.mqtt_client import MQTTClient
from app.devices.mqtt_device import (
    MQTTDeviceExecutor,
    ActionExecutionError,
)


def main():

    # ==========================================================
    # CONTEXT
    # ==========================================================

    context = ContextManager()

    # Start from Relax Room
    from app.orchestration.state import (
        Room,
        Mode,
        PowerState,
    )

    context.set_current_room(
        Room.RELAX_ROOM
    )

    context.set_return_target(
        Room.STUDY_ROOM
    )

    context.set_mode(
        Mode.RELAX
    )

    # Current Relax environment
    context.state.relax.light = PowerState.ON
    context.state.relax.tv = PowerState.ON

    # ==========================================================
    # WORKFLOW ENGINE
    # ==========================================================

    workflow_engine = WorkflowEngine(
        context
    )

    actions = (
        workflow_engine.create_sleep_workflow()
    )

    # ==========================================================
    # INITIAL STATE
    # ==========================================================

    print("\n" + "=" * 70)
    print("INITIAL STATE")
    print("=" * 70)

    context.print_state()

    # ==========================================================
    # DISPLAY WORKFLOW
    # ==========================================================

    print("\n" + "=" * 70)
    print("EXECUTING SLEEP WORKFLOW THROUGH MQTT")
    print("=" * 70)

    # ==========================================================
    # MQTT CLIENT
    # ==========================================================

    mqtt_client = MQTTClient(
        broker_host="localhost",
        broker_port=1883,
        client_id="sleep_workflow_test"
    )

    mqtt_client.connect()

    # ==========================================================
    # MQTT DEVICE EXECUTOR
    # ==========================================================

    executor = MQTTDeviceExecutor(
        mqtt_client
    )

    # ==========================================================
    # EXECUTE WORKFLOW
    # ==========================================================

    try:

        results = executor.execute_workflow(
            actions,
            timeout=5,
            max_retries=2
        )

        # ------------------------------------------------------
        # SUCCESS
        # ------------------------------------------------------

        print("\n" + "=" * 70)
        print("SLEEP WORKFLOW COMPLETED SUCCESSFULLY")
        print("=" * 70)

        print(
            f"Successfully executed "
            f"{len(results)} actions."
        )

        # ------------------------------------------------------
        # Print final state only after successful execution
        # ------------------------------------------------------

        print("\n" + "=" * 70)
        print("FINAL LOGICAL STATE")
        print("=" * 70)

        context.print_state()

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
            "\nRemaining workflow actions "
            "were not executed."
        )

    except TimeoutError as error:

        # ------------------------------------------------------
        # CONTROLLED TIMEOUT
        # ------------------------------------------------------

        print("\n" + "=" * 70)
        print("SLEEP WORKFLOW TIMEOUT")
        print("=" * 70)

        print(
            f"Reason: {error}"
        )

        print(
            "\nRemaining workflow actions "
            "were not executed."
        )

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

    finally:

        # ======================================================
        # DISCONNECT
        # ======================================================

        input(
            "\nPress ENTER to disconnect..."
        )

        mqtt_client.disconnect()


# ==============================================================
# MAIN
# ==============================================================

if __name__ == "__main__":

    main()