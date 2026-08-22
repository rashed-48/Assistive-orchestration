from app.orchestration.context_manager import ContextManager
from app.orchestration.state import (
    Room,
    Mode,
    PowerState,
)
from app.orchestration.workflow_engine import WorkflowEngine
from app.devices.mock_device import MockDeviceExecutor


# ======================================================
# CREATE SYSTEM
# ======================================================

context = ContextManager()

engine = WorkflowEngine(context)
executor = MockDeviceExecutor(context)


# ======================================================
# SIMULATE CURRENT ENVIRONMENT
# ======================================================

# User is currently in Sleep Room
context.set_current_room(Room.SLEEP_ROOM)

# User previously came from Relax Room
context.set_return_target(Room.RELAX_ROOM)

# Current activity is Sleep
context.set_mode(Mode.SLEEP)

# Sleep environment is currently active
context.state.sleep.light = PowerState.ON


# ======================================================
# INITIAL STATE
# ======================================================

print("\n" + "=" * 70)
print("INITIAL STATE")
print("=" * 70)

context.print_state()


# ======================================================
# CREATE MEAL WORKFLOW
# ======================================================

actions = engine.create_meal_workflow()


# ======================================================
# EXECUTE WORKFLOW
# ======================================================

print("\n" + "=" * 70)
print("EXECUTING MEAL WORKFLOW")
print("=" * 70)

executor.execute_workflow(
    actions,
    destination=Room.MEAL_ROOM,
    mode=Mode.MEAL
)


# ======================================================
# FINAL STATE
# ======================================================

print("\n" + "=" * 70)
print("FINAL STATE")
print("=" * 70)

context.print_state()