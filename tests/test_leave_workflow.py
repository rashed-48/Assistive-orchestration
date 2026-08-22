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
# CREATE LEAVE WORKFLOW
# ======================================================

actions = engine.create_leave_workflow()


# ======================================================
# EXECUTE
# ======================================================

print("\n" + "=" * 70)
print("EXECUTING LEAVE WORKFLOW")
print("=" * 70)

executor.execute_workflow(
    actions,
    destination=Room.OUTSIDE,
    mode=Mode.NONE
)


# ======================================================
# FINAL STATE
# ======================================================

print("\n" + "=" * 70)
print("FINAL STATE")
print("=" * 70)

context.print_state()