"""Shared helpers for the automated suite.

Nothing here may touch a broker, a network, real hardware, a microphone, or a
speech model. Everything is deterministic and in-memory.
"""

import contextlib
import io

from app.devices.device_registry import DEVICE_NODE_MAP
from app.devices.mock_device import MockDeviceExecutor
from app.orchestration.context_manager import ContextManager
from app.orchestration.orchestrator import Orchestrator


class FakeMQTTTransport:
    """In-memory stand-in for MQTTClient plus a perfectly behaved ESP32 fleet.

    It implements the publish()/wait_for_status() contract that
    MQTTDeviceExecutor depends on, so the real executor can be exercised
    with no broker and no hardware.

    fail_on and timeout_on hold 1-based publish attempt numbers, letting a
    test inject a device error or a lost acknowledgement at an exact point
    in a workflow.
    """

    def __init__(self, fail_on=None, timeout_on=None):
        self.published = []
        self.fail_on = set(fail_on or ())
        self.timeout_on = set(timeout_on or ())

    def publish(self, topic, payload):
        self.published.append(
            {
                "topic": topic,
                "payload": payload,
            }
        )

    def wait_for_status(self, command_id, timeout=5):

        attempt = len(self.published)

        if attempt in self.timeout_on:
            return None

        payload = self.published[-1]["payload"]

        return {
            "command_id": command_id,
            "node": DEVICE_NODE_MAP[payload["device"]],
            "device": payload["device"],
            "action": payload["action"],
            "status": "error" if attempt in self.fail_on else "success",
        }


@contextlib.contextmanager
def quiet():
    """Swallow the orchestration layer's console narration."""

    with contextlib.redirect_stdout(io.StringIO()):
        yield


def build_context(room, mode, return_target=None):
    """Create a ContextManager seeded with a starting logical position."""

    context = ContextManager()

    context.set_current_room(room)
    context.set_mode(mode)

    if return_target is not None:
        context.set_return_target(return_target)

    return context


def execute(context, intent):
    """Run an intent through the authoritative path with a mock executor.

    Returns (executor, results) so a test can assert both the physical
    action sequence and the acknowledgement results.
    """

    executor = MockDeviceExecutor(context)

    with quiet():
        results = Orchestrator(context, executor).execute_intent(intent)

    return executor, results


def action_signature(actions):
    return [
        (action.action_type, action.device_id)
        for action in actions
    ]


def logical_snapshot(context):
    """Full comparable picture of the logical environment state."""

    state = context.get_state()

    return {
        "current_room": state.current_room,
        "return_target": state.return_target,
        "current_mode": state.current_mode,
        "drawing_light": state.drawing_light,
        "exit_door": state.exit_door,
        "buzzer": state.buzzer,
        "study": (
            state.study.door,
            state.study.light,
            state.study.table,
        ),
        "relax": (
            state.relax.door,
            state.relax.light,
            state.relax.tv,
        ),
        "sleep": (
            state.sleep.door,
            state.sleep.light,
            state.sleep.bed,
            state.sleep.medication_servo,
        ),
        "meal": (
            state.meal.door,
            state.meal.light,
            state.meal.table,
        ),
    }
