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

# User is currently in Relax Room
context.set_current_room(Room.RELAX_ROOM)

# The previous functional room was Study
context.set_return_target(Room.STUDY_ROOM)

# Current activity is Relax
context.set_mode(Mode.RELAX)

# Relax environment is currently active
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
# EXECUTE WORKFLOW
# ======================================================

print("\n" + "=" * 70)
print("EXECUTING SLEEP WORKFLOW")
print("=" * 70)

orchestrator.execute_intent("PREPARE_FOR_SLEEP")


# ======================================================
# FINAL STATE
# ======================================================

print("\n" + "=" * 70)
print("FINAL STATE")
print("=" * 70)

context.print_state()
