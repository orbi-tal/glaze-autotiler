import asyncio
import json
import os

import pytest


class MockWebsocket:
    """Fake websocket simulating GlazeWM's server side of the connection."""

    def __init__(self, incoming_messages):
        self.incoming = list(incoming_messages)
        self.sent_commands = []

    async def recv(self):
        if not self.incoming:
            # Nothing left to deliver -- block briefly then let the caller's
            # own cancel_event/timeout logic decide what happens next,
            # rather than raising CancelledError ourselves (dwindle.py's
            # recv() is wrapped in asyncio.wait_for(..., timeout=1.0), so it
            # will hit TimeoutError on its own and loop back to check
            # cancel_event -- that's what actually ends the test).
            await asyncio.sleep(1.5)
            raise AssertionError("recv() should not be reached again after cancel_event is set")
        return self.incoming.pop(0)

    async def send(self, message):
        self.sent_commands.append(message)


@pytest.mark.asyncio
async def test_dwindle_layout_direction_change():
    """dwindle_layout() should send 'c set-tiling-direction horizontal' for a
    wide window and 'c set-tiling-direction vertical' for a tall one, and
    should not resend the same direction twice in a row."""
    from src.main import AutoTiler

    autotiler = AutoTiler(log_enabled=False)
    # pre_package_default_scripts() (run during __init__) writes the actual
    # packaged dwindle.py to scripts_dir -- load that real file, not a stub.
    script_path = os.path.join(autotiler.scripts_dir, "dwindle.py")
    dwindle_module = autotiler._load_layout_module("dwindle", script_path)
    assert dwindle_module is not None, "dwindle.py failed to load"
    assert hasattr(dwindle_module, "dwindle_layout")

    fake_events = [
        json.dumps({"messageType": "client_response", "success": True}),
        # Wide window -> expect horizontal
        json.dumps(
            {
                "messageType": "event_subscription",
                "data": {"managedWindow": {"width": 1920, "height": 1080}},
            }
        ),
        # Tall window -> expect vertical
        json.dumps(
            {
                "messageType": "event_subscription",
                "data": {"managedWindow": {"width": 1080, "height": 1920}},
            }
        ),
        # Same tall window again -> direction unchanged, should NOT resend
        json.dumps(
            {
                "messageType": "event_subscription",
                "data": {"managedWindow": {"width": 1080, "height": 1920}},
            }
        ),
    ]

    ws = MockWebsocket(fake_events)
    cancel_event = asyncio.Event()

    async def stop_soon():
        # Let the loop drain all fake_events, then cancel it -- dwindle_layout
        # only returns when cancel_event is set (or on CancelledError).
        while ws.incoming:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        cancel_event.set()

    await asyncio.gather(
        dwindle_module.dwindle_layout(ws, cancel_event),
        stop_soon(),
    )

    direction_commands = [c for c in ws.sent_commands if "set-tiling-direction" in c]

    assert direction_commands == [
        "c set-tiling-direction horizontal",
        "c set-tiling-direction vertical",
    ], (
        f"expected exactly one horizontal then one vertical command (the repeated "
        f"tall-window event should not resend the same direction), got: {direction_commands}"
    )

    # Also lock in the exact command syntax -- a missing 'c ' prefix here is
    # a real regression that has happened before and fails silently against
    # GlazeWM (the command is simply rejected, not a crash), so it wouldn't
    # be caught without asserting the literal string.
    assert all(cmd.startswith("c set-tiling-direction ") for cmd in direction_commands)
