from app.orchestration.context_manager import ContextManager
from app.orchestration.state import (
    Room,
    Mode,
    PowerState,
    PreparationState,
)
from app.orchestration.workflow_engine import WorkflowEngine
from app.devices.mock_device import MockDeviceExecutor


context = ContextManager()

engine = WorkflowEngine(context)
executor = MockDeviceExecutor(context)


# Simulate that the user is already studying
context.set_current_room(Room.STUDY_ROOM)
context.set_mode(Mode.STUDY)

context.state.study.light = PowerState.ON
context.state.study.table = PreparationState.READY


print("\n" + "=" * 70)
print("INITIAL STATE")
print("=" * 70)

context.print_state()


actions = engine.create_relax_workflow()


print("\n" + "=" * 70)
print("EXECUTING RELAX WORKFLOW")
print("=" * 70)

executor.execute_workflow(
    actions,
    destination=Room.RELAX_ROOM,
    mode=Mode.RELAX
)

print("\n" + "=" * 70)
print("FINAL STATE")
print("=" * 70)

context.print_state()