from app.orchestration.context_manager import ContextManager
from app.orchestration.orchestrator import Orchestrator
from app.devices.mock_device import MockDeviceExecutor


context = ContextManager()

executor = MockDeviceExecutor(context)
orchestrator = Orchestrator(context, executor)


print("\n" + "=" * 70)
print("INITIAL STATE")
print("=" * 70)

context.print_state()


print("\n" + "=" * 70)
print("EXECUTING STUDY WORKFLOW")
print("=" * 70)

orchestrator.execute_intent("STUDY_MODE")

print("\n" + "=" * 70)
print("FINAL STATE")
print("=" * 70)

context.print_state()
