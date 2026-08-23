from app.orchestration.context_manager import ContextManager
from app.orchestration.state import (
    Room,
    Mode,
    PreparationState,
    PowerState,
)
from app.orchestration.orchestrator import Orchestrator
from app.devices.mock_device import MockDeviceExecutor


context = ContextManager()

executor = MockDeviceExecutor(context)
orchestrator = Orchestrator(context, executor)


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
# EXECUTE
# ======================================================

print("\n" + "=" * 70)
print("EXECUTING WAKE-UP WORKFLOW")
print("=" * 70)

orchestrator.execute_intent("WAKE_UP")


# ======================================================
# FINAL STATE
# ======================================================

print("\n" + "=" * 70)
print("FINAL STATE")
print("=" * 70)

context.print_state()
