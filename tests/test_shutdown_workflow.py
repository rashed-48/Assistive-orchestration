from app.orchestration.context_manager import ContextManager
from app.orchestration.state import (
    Room,
    Mode,
    PowerState,
)
from app.orchestration.workflow_engine import WorkflowEngine
from app.devices.mock_device import MockDeviceExecutor


context = ContextManager()

engine = WorkflowEngine(context)
executor = MockDeviceExecutor(context)


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
# CREATE SHUTDOWN WORKFLOW
# ======================================================

actions = engine.create_shutdown_workflow()


# ======================================================
# EXECUTE
# ======================================================

print("\n" + "=" * 70)
print("EXECUTING SHUTDOWN WORKFLOW")
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