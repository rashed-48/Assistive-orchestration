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
# INITIAL SLEEP STATE
# ======================================================

context.set_current_room(Room.SLEEP_ROOM)
context.set_return_target(Room.RELAX_ROOM)
context.set_mode(Mode.SLEEP)

context.state.sleep.light = PowerState.ON
context.state.sleep.bed = PreparationState.READY


print("\n" + "=" * 70)
print("INITIAL STATE")
print("=" * 70)

context.print_state()


# ======================================================
# WAKE UP
# ======================================================

print("\n" + "=" * 70)
print("STEP 1: WAKE UP")
print("=" * 70)

orchestrator.execute_intent("WAKE_UP")

context.print_state()


# ======================================================
# PREPARE FOR SLEEP AGAIN
# ======================================================

print("\n" + "=" * 70)
print("STEP 2: PREPARE FOR SLEEP AGAIN")
print("=" * 70)

orchestrator.execute_intent("PREPARE_FOR_SLEEP")

context.print_state()
