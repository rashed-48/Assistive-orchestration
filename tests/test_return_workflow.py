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

# User is currently in Meal Room
context.set_current_room(Room.MEAL_ROOM)

# User entered Meal Room from Sleep Room
context.set_return_target(Room.SLEEP_ROOM)

# Current activity
context.set_mode(Mode.MEAL)

# Meal environment is active
context.state.meal.light = PowerState.ON


# ======================================================
# INITIAL STATE
# ======================================================

print("\n" + "=" * 70)
print("INITIAL STATE")
print("=" * 70)

context.print_state()


# ======================================================
# CREATE RETURN WORKFLOW
# ======================================================

actions = engine.create_return_workflow()


# ======================================================
# EXECUTE
# ======================================================

print("\n" + "=" * 70)
print("EXECUTING RETURN WORKFLOW")
print("=" * 70)

executor.execute_workflow(
    actions,
    destination=context.get_return_target(),
    mode=Mode.SLEEP
)


# ======================================================
# FINAL STATE
# ======================================================

print("\n" + "=" * 70)
print("FINAL STATE")
print("=" * 70)

context.print_state()