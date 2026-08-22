from app.orchestration.context_manager import ContextManager
from app.orchestration.state import (
    Room,
    Mode,
    PreparationState,
    PowerState,
)
from app.orchestration.workflow_engine import WorkflowEngine
from app.devices.mock_device import MockDeviceExecutor


context = ContextManager()

engine = WorkflowEngine(context)
executor = MockDeviceExecutor(context)


# ======================================================
# CURRENT ENVIRONMENT
# ======================================================

context.set_current_room(Room.SLEEP_ROOM)
context.set_return_target(Room.RELAX_ROOM)
context.set_mode(Mode.SLEEP)

context.state.sleep.light = PowerState.ON
context.state.sleep.bed = PreparationState.READY


# ======================================================
# INITIAL STATE
# ======================================================

print("\n" + "=" * 70)
print("INITIAL STATE")
print("=" * 70)

context.print_state()


# ======================================================
# CREATE WAKE-UP WORKFLOW
# ======================================================

actions = engine.create_wake_up_workflow()


# ======================================================
# EXECUTE
# ======================================================

print("\n" + "=" * 70)
print("EXECUTING WAKE-UP WORKFLOW")
print("=" * 70)

executor.execute_workflow(
    actions,
    destination=Room.SLEEP_ROOM,
    mode=Mode.SLEEP
)


# ======================================================
# FINAL STATE
# ======================================================

print("\n" + "=" * 70)
print("FINAL STATE")
print("=" * 70)

context.print_state()