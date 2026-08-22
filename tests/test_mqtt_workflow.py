from app.orchestration.context_manager import ContextManager
from app.orchestration.state import (
    Room,
    Mode,
    PowerState,
)

from app.orchestration.workflow_engine import WorkflowEngine

from app.devices.mqtt_client import MQTTClient
from app.devices.mqtt_device import MQTTDeviceExecutor


# ======================================================
# CONTEXT
# ======================================================

context = ContextManager()

context.set_current_room(Room.STUDY_ROOM)
context.set_mode(Mode.STUDY)

context.state.study.light = PowerState.ON


# ======================================================
# WORKFLOW ENGINE
# ======================================================

engine = WorkflowEngine(context)


# ======================================================
# MQTT CLIENT
# ======================================================

mqtt_client = MQTTClient(
    broker_host="localhost",
    broker_port=1883,
    client_id="workflow_test"
)

mqtt_client.connect()


# ======================================================
# DEVICE EXECUTOR
# ======================================================

executor = MQTTDeviceExecutor(
    mqtt_client
)


# ======================================================
# CREATE WORKFLOW
# ======================================================

actions = engine.create_relax_workflow()


# ======================================================
# EXECUTE
# ======================================================

print("\n" + "=" * 70)
print("EXECUTING RELAX WORKFLOW THROUGH MQTT")
print("=" * 70)

executor.execute_workflow(actions)


# ======================================================
# KEEP CONNECTION ALIVE BRIEFLY
# ======================================================

input("\nPress ENTER to disconnect...")


mqtt_client.disconnect()