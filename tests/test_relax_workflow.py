from app.orchestration.context_manager import ContextManager
from app.orchestration.state import (
    Room,
    Mode,
    PowerState,
    PreparationState,
)
from app.orchestration.orchestrator import Orchestrator
from app.devices.mock_device import MockDeviceExecutor


context = ContextManager()

executor = MockDeviceExecutor(context)
orchestrator = Orchestrator(context, executor)


# Simulate that the user is already studying
context.set_current_room(Room.STUDY_ROOM)
context.set_mode(Mode.STUDY)

context.state.study.light = PowerState.ON
context.state.study.table = PreparationState.READY


print("\n" + "=" * 70)
print("INITIAL STATE")
print("=" * 70)

context.print_state()


print("\n" + "=" * 70)
print("EXECUTING RELAX WORKFLOW")
print("=" * 70)

orchestrator.execute_intent("RELAX_MODE")

print("\n" + "=" * 70)
print("FINAL STATE")
print("=" * 70)

context.print_state()
