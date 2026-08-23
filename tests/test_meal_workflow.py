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
# EXECUTE WORKFLOW
# ======================================================

print("\n" + "=" * 70)
print("EXECUTING MEAL WORKFLOW")
print("=" * 70)

orchestrator.execute_intent("PREPARE_FOR_MEAL")


# ======================================================
# FINAL STATE
# ======================================================

print("\n" + "=" * 70)
print("FINAL STATE")
print("=" * 70)

context.print_state()
