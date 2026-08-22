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
# INITIAL SLEEP STATE
# ======================================================

context.set_current_room(Room.SLEEP_ROOM)
context.set_return_target(Room.RELAX_ROOM)
context.set_mode(Mode.SLEEP)

context.state.sleep.light = PowerState.ON
context.state.sleep.bed = PreparationState.READY


print("\n" + "=" * 70)
print("INITIAL STATE")
print("=" * 70)

context.print_state()


# ======================================================
# WAKE UP
# ======================================================

print("\n" + "=" * 70)
print("STEP 1: WAKE UP")
print("=" * 70)

actions = engine.create_wake_up_workflow()

executor.execute_workflow(
    actions,
    destination=Room.SLEEP_ROOM,
    mode=Mode.SLEEP
)

context.print_state()


# ======================================================
# PREPARE FOR SLEEP AGAIN
# ======================================================

print("\n" + "=" * 70)
print("STEP 2: PREPARE FOR SLEEP AGAIN")
print("=" * 70)

actions = engine.create_sleep_workflow()

executor.execute_workflow(
    actions,
    destination=Room.SLEEP_ROOM,
    mode=Mode.SLEEP
)

context.print_state()