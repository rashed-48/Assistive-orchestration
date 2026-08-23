from app.orchestration.context_manager import ContextManager
from app.orchestration.state import (
    Room,
    Mode,
    PowerState,
)
from app.orchestration.orchestrator import Orchestrator
from app.devices.mock_device import MockDeviceExecutor


# ======================================================
# CREATE SYSTEM
# ======================================================

context = ContextManager()

executor = MockDeviceExecutor(context)
orchestrator = Orchestrator(context, executor)


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
# EXECUTE
# ======================================================

print("\n" + "=" * 70)
print("EXECUTING RETURN WORKFLOW")
print("=" * 70)

orchestrator.execute_intent("RETURN_TO_ROOM")


# ======================================================
# FINAL STATE
# ======================================================

print("\n" + "=" * 70)
print("FINAL STATE")
print("=" * 70)

context.print_state()
