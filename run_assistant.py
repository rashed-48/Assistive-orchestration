"""Continuous voice runtime.

    .\\.venv\\Scripts\\python.exe run_assistant.py

State is created once and preserved for the whole session, so each
command is planned against whatever the previous command left behind.
Point it at another broker with ASSISTIVE_BROKER_HOST / _PORT.
"""

import os

from app.console import main
from app.runtime import DEFAULT_BROKER_HOST, DEFAULT_BROKER_PORT


if __name__ == "__main__":
    main(
        broker_host=os.environ.get(
            "ASSISTIVE_BROKER_HOST",
            DEFAULT_BROKER_HOST,
        ),
        broker_port=int(
            os.environ.get(
                "ASSISTIVE_BROKER_PORT",
                DEFAULT_BROKER_PORT,
            )
        ),
    )
