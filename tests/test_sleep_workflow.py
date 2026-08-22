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
# CREATE SLEEP WORKFLOW
# ======================================================

actions = engine.create_sleep_workflow()


# ======================================================
# EXECUTE WORKFLOW
# ======================================================

print("\n" + "=" * 70)
print("EXECUTING SLEEP WORKFLOW")
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