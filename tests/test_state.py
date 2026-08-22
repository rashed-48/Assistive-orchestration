from app.orchestration.context_manager import ContextManager
from app.orchestration.state import Room, Mode


context = ContextManager()

print("Initial state:")
context.print_state()

print("\nChanging state...")

context.set_current_room(Room.STUDY_ROOM)
context.set_mode(Mode.STUDY)
context.set_return_target(Room.RELAX_ROOM)

print("\nUpdated state:")
context.print_state()