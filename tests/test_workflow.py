from app.orchestration.context_manager import ContextManager
from app.orchestration.workflow_engine import WorkflowEngine
from app.devices.mock_device import MockDeviceExecutor


context = ContextManager()

engine = WorkflowEngine(context)
executor = MockDeviceExecutor(context)


print("\n" + "=" * 70)
print("INITIAL STATE")
print("=" * 70)

context.print_state()


actions = engine.create_study_workflow()


print("\n" + "=" * 70)
print("EXECUTING STUDY WORKFLOW")
print("=" * 70)



from app.orchestration.state import Room, Mode

executor.execute_workflow(
    actions,
    destination=Room.STUDY_ROOM,
    mode=Mode.STUDY
)

print("\n" + "=" * 70)
print("FINAL STATE")
print("=" * 70)

context.print_state()