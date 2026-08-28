"""Test isolation for durable state.

ApplicationRuntime persists by default, which is right for production
and wrong for a test suite: without this, every test would load the
world the previous test left behind and the suite would stop being
deterministic.

Every test therefore gets its own empty state directory. Tests that
want to observe persistence ask for the `state_directory` fixture; the
rest simply never collide.
"""

import pytest


@pytest.fixture(autouse=True)
def state_directory(tmp_path, monkeypatch):
    """Point runtime persistence at a directory unique to this test."""

    directory = tmp_path / "state"

    monkeypatch.setattr(
        "app.runtime.DEFAULT_STATE_DIRECTORY",
        directory,
        raising=False,
    )

    return directory
