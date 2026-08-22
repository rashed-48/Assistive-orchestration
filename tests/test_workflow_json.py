from app.orchestration.context_manager import ContextManager
from app.orchestration.state import (
    Room,
    Mode,
    PowerState,
)
from app.orchestration.workflow_engine import WorkflowEngine
from app.devices.json_protocol import JSONProtocol


# ======================================================
# CREATE SYSTEM
# ======================================================

context = ContextManager()

engine = WorkflowEngine(context)


# ======================================================
# INITIAL ENVIRONMENT
# ======================================================

context.set_current_room(Room.STUDY_ROOM)
context.set_return_target(None)
context.set_mode(Mode.STUDY)

context.state.study.light = PowerState.ON


# ======================================================
# INITIAL STATE
# ======================================================

print("\n" + "=" * 70)
print("INITIAL STATE")
print("=" * 70)

context.print_state()


# ======================================================
# CREATE RELAX WORKFLOW
# ======================================================

actions = engine.create_relax_workflow()


# ======================================================
# SHOW ACTIONS
# ======================================================

print("\n" + "=" * 70)
print("GENERATED ACTIONS")
print("=" * 70)

for index, action in enumerate(actions, start=1):

    print(
        f"{index:02d}. "
        f"{action.action_type.value:<20} "
        f"{action.device_id}"
    )


# ======================================================
# CONVERT TO JSON
# ======================================================

json_commands = JSONProtocol.actions_to_json(actions)


# ======================================================
# SHOW JSON
# ======================================================

print("\n" + "=" * 70)
print("ESP32 JSON COMMANDS")
print("=" * 70)

print(json_commands)