"""Open-loop actuation - the baseline this system argues against.

A great many IoT deployments actuate this way: publish a command and
move on. Nothing waits for the device to answer, so completion is
assumed after a fixed delay rather than confirmed. It is the default
shape of most home-automation examples, and it is cheap, simple, and
has no dependency on nodes replying at all.

What it cannot do is tell the difference between a command that worked
and one that went nowhere. That is the whole comparison:

    open loop    publish -> sleep delta -> declare success
    closed loop  publish -> await acknowledgement -> commit on it

This executor exists only to be measured against. It is never used by
the application: `ApplicationRuntime` builds an `MQTTDeviceExecutor`,
and this is injected explicitly by the baseline experiment.

Choosing delta is the baseline's whole problem, and both ends of it are
bad in different ways:

    delta too short  a dependent action is dispatched before its
                     prerequisite has physically finished - an
                     ordering violation
    delta too long   every action pays the worst device's cost, so a
                     66 ms lamp waits as long as a 2 s dispenser

Neither setting can detect an unreachable node, so both report
workflows complete that did nothing - a silent success.
"""

import time
import uuid

from app.devices.device_registry import DEVICE_NODE_MAP
from app.devices.json_protocol import JSONProtocol
from app.orchestration.actions import Action


class OpenLoopExecutor:
    """Publishes and assumes. Interface-compatible with the real one."""

    def __init__(self, mqtt_client, delay=2.1):
        self.mqtt_client = mqtt_client
        self.delay = delay

        # Recorded so an experiment can report what the baseline
        # believed, alongside what actually happened on the wire.
        self.dispatched = 0

    def execute(self, action: Action, timeout=5, max_retries=2):
        """Publish, wait out the delay, report success regardless.

        `timeout` and `max_retries` are accepted so this can stand in
        for the real executor unchanged, and ignored because open-loop
        actuation has nothing to time out on and nothing to retry: no
        reply is ever awaited.
        """

        device_id = action.device_id

        if device_id not in DEVICE_NODE_MAP:
            raise ValueError(f"Unknown device: {device_id}")

        node = DEVICE_NODE_MAP[device_id]

        # The same envelope the real executor sends, so a node cannot
        # tell the two apart and the comparison stays fair. The id is
        # minted here because JSONProtocol does not carry one.
        payload = dict(JSONProtocol.action_to_dict(action))
        command_id = str(uuid.uuid4())
        payload["command_id"] = command_id

        self.mqtt_client.publish(
            f"assistive/command/{node}",
            payload,
        )
        self.dispatched += 1

        time.sleep(self.delay)

        # No acknowledgement was sought, so this is an assumption
        # presented in the same shape as a measured result. Marked, so
        # nothing downstream can mistake it for one.
        return {
            "command_id": command_id,
            "node": node,
            "device": device_id,
            "action": action.action_type.value,
            "status": "success",
            "assumed": True,
        }
