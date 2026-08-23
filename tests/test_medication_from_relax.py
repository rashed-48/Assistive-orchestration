from app.orchestration.context_manager import ContextManager
from app.orchestration.state import (
    Room,
    Mode,
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

context.set_current_room(Room.RELAX_ROOM)
context.set_return_target(Room.STUDY_ROOM)
context.set_mode(Mode.RELAX)

context.state.relax.light = PowerState.ON
context.state.relax.tv = PowerState.ON


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
print("EXECUTING MEDICATION WORKFLOW")
print("=" * 70)

orchestrator.execute_intent("MEDICATION")


# ======================================================
# FINAL STATE
# ======================================================

print("\n" + "=" * 70)
print("FINAL STATE")
print("=" * 70)

context.print_state()
