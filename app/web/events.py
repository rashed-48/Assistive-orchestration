"""What the browser watches: an ordered, replayable stream of events.

Everything visible in the interface's pipeline view comes through here
- speech transcribed, intent scored, plan produced, commands on the
wire, acknowledgements, completions, state commits. Each event carries
a sequence number so a client that reconnects can ask for everything
after the last one it saw, and a monotonic timestamp so the interface
can show real intervals rather than wall-clock guesses.

The bus never blocks a producer. Emitting is an append under a lock;
the only waiting happens on the consumer side, in `wait_for`.
"""

import threading
import time
from collections import deque


class EventBus:

    def __init__(self, capacity=2000):
        self._events = deque(maxlen=capacity)
        self._sequence = 0
        self._condition = threading.Condition()
        self._origin = time.perf_counter()

    def emit(self, kind, **data):
        """Append one event and wake every waiting consumer."""

        with self._condition:
            self._sequence += 1
            event = {
                "seq": self._sequence,
                "t": round((time.perf_counter() - self._origin) * 1000.0, 2),
                "kind": kind,
                **data,
            }
            self._events.append(event)
            self._condition.notify_all()
        return event

    def since(self, sequence):
        """Every event after `sequence`, oldest first."""

        with self._condition:
            return [e for e in self._events if e["seq"] > sequence]

    def wait_for(self, sequence, timeout):
        """Block until something newer than `sequence` exists, or
        `timeout` seconds pass. Returns the new events, possibly none."""

        deadline = time.time() + timeout
        with self._condition:
            while self._sequence <= sequence:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return []
                self._condition.wait(remaining)
            return [e for e in self._events if e["seq"] > sequence]

    @property
    def latest(self):
        with self._condition:
            return self._sequence
