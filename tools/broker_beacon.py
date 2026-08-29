"""Announce this host as the broker, on its own.

The web server and the console already do this while they run. This is
for the times they are not: bringing a board up, restarting the app
mid-demo, or checking that the announcement reaches the board at all
before it matters.

    python -m tools.broker_beacon

    python -m tools.broker_beacon --listen     (watch, do not announce)

--listen is the diagnostic half. Run it on a second machine on the same
network to see whether announcements are actually crossing - a router
that does not bridge broadcast between its 2.4 GHz and 5 GHz bands will
show nothing here even though the beacon is sending correctly.
"""

import argparse
import json
import socket
import sys
import time

from app.discovery import (
    DEFAULT_DISCOVERY_PORT,
    SERVICE_NAME,
    BrokerBeacon,
    broadcast_targets,
    local_ip,
)


def listen(port, seconds):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", port))
    sock.settimeout(1.0)

    print(f"Listening on udp/{port} the way a node does - Ctrl-C to stop.")
    deadline = time.time() + seconds if seconds else None
    heard = 0

    try:
        while deadline is None or time.time() < deadline:
            try:
                data, sender = sock.recvfrom(512)
            except socket.timeout:
                continue
            try:
                payload = json.loads(data.decode())
            except ValueError:
                continue
            if payload.get("service") != SERVICE_NAME:
                continue
            heard += 1
            if heard == 1 or heard % 10 == 0:
                print(f"  {time.strftime('%H:%M:%S')}  from {sender[0]}"
                      f"  -> broker {payload.get('broker')}:{payload.get('port')}")
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()

    print(f"heard {heard} announcement(s)")
    return 0 if heard else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_DISCOVERY_PORT)
    parser.add_argument("--broker-port", type=int, default=1883)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--seconds", type=float, default=0,
                        help="stop after this long; 0 runs until Ctrl-C")
    parser.add_argument("--listen", action="store_true",
                        help="watch for announcements instead of sending")
    args = parser.parse_args()

    if args.listen:
        return listen(args.port, args.seconds)

    beacon = BrokerBeacon(broker_port=args.broker_port,
                          discovery_port=args.port,
                          interval=args.interval)

    print(f"Announcing this host as the broker - Ctrl-C to stop.")
    print(f"  address   {local_ip()}:{args.broker_port}")
    print(f"  sending   udp/{args.port} to "
          f"{', '.join(broadcast_targets(local_ip()))}")
    print(f"  every     {args.interval}s")
    print()
    print("A node prints 'found <address>' once it hears this.")
    print()

    beacon.start()
    try:
        deadline = time.time() + args.seconds if args.seconds else None
        while deadline is None or time.time() < deadline:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        beacon.stop()

    print(f"stopped after {beacon.sent} datagram(s)")
    if beacon.last_error:
        print(f"last send error: {beacon.last_error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
