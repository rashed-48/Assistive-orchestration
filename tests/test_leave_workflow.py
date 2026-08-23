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

# User is currently in Study Room
context.set_current_room(Room.STUDY_ROOM)

# User previously came from Relax Room
context.set_return_target(Room.RELAX_ROOM)

# Current activity
context.set_mode(Mode.STUDY)

# Study environment is active
context.state.study.light = PowerState.ON


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
print("EXECUTING LEAVE WORKFLOW")
print("=" * 70)

orchestrator.execute_intent("LEAVE_ROOM")


# ======================================================
# FINAL STATE
# ======================================================

print("\n" + "=" * 70)
print("FINAL STATE")
print("=" * 70)

context.print_state()
