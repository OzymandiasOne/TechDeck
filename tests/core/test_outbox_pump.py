"""
Something has to empty the outbox.

`flow_client` shipped a complete, tested outbox in v0.8.8 and **nothing ever
called `flush_outbox`** - defined, re-exported through the SDK, zero call
sites. A queued command therefore sat in a JSONL file forever. These tests
exist so that can never silently become true again: if the pump stops being
wired up, or stops discovering a queue, these fail.
"""

from __future__ import annotations

import json
import threading

import pytest
import requests

from techdeck.core import flow_client as fc
from techdeck.core import outbox_pump

URL = "https://example.invalid/flow"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("TECHDECK_SANDBOX_922_ROOT", raising=False)
    outbox_pump._reset_for_tests()
    yield tmp_path
    outbox_pump._reset_for_tests()


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {
            "ok": True, "reason": "", "message": "", "data": {}}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


@pytest.fixture
def posts(monkeypatch):
    class Recorder:
        def __init__(self):
            self.calls = []

        def __call__(self, url, json=None, timeout=None, **kw):
            self.calls.append((url, json, timeout))
            return FakeResponse()

    rec = Recorder()
    monkeypatch.setattr(requests, "post", rec)
    return rec


class TestDiscovery:
    def test_no_outbox_directory_is_not_an_error(self):
        assert outbox_pump.pending_commands() == []
        assert outbox_pump.total_pending() == 0

    def test_it_finds_a_queue_without_being_told_it_exists(self):
        """Discovered from disk, so a new two-way feature drains the day it
        ships rather than when someone remembers to register it here."""
        fc.queue_command(URL, "send_debug_report", {"n": 1})
        fc.queue_command(URL, "suggestion_create", {"n": 2})
        assert outbox_pump.pending_commands() == ["send_debug_report",
                                                  "suggestion_create"]
        assert outbox_pump.total_pending() == 2

    def test_a_drained_queue_is_not_listed(self, posts):
        fc.queue_command(URL, "send_debug_report", {"n": 1})
        outbox_pump.pump_now()
        assert outbox_pump.pending_commands() == []
        assert outbox_pump.total_pending() == 0


class TestPumping:
    def test_it_actually_delivers(self, posts):
        fc.queue_command(URL, "send_debug_report", {"n": 1})
        delivered, waiting = outbox_pump.pump_now()
        assert (delivered, waiting) == (1, 0)
        assert posts.calls[0][0] == URL
        assert fc.outbox_depth("send_debug_report") == 0

    def test_it_drains_every_queue_not_just_the_first(self, posts):
        fc.queue_command(URL, "send_debug_report", {"n": 1})
        fc.queue_command(URL, "suggestion_create", {"n": 2})
        delivered, waiting = outbox_pump.pump_now()
        assert (delivered, waiting) == (2, 0)

    def test_it_keeps_a_small_bite(self, posts):
        """A backlog drains over a few launches instead of holding one
        launch hostage."""
        for n in range(12):
            fc.queue_command(URL, "send_debug_report", {"n": n})
        delivered, waiting = outbox_pump.pump_now()
        assert delivered == outbox_pump.PUMP_LIMIT == 5
        assert waiting == 7

    def test_its_timeout_is_well_under_a_frozen_app(self, posts):
        """flow_client's 20s default x a 25 limit is 500s. The pump must not
        inherit either number."""
        fc.queue_command(URL, "send_debug_report", {"n": 1})
        outbox_pump.pump_now()
        assert posts.calls[0][2] == outbox_pump.PUMP_TIMEOUT_S == 10.0
        assert outbox_pump.PUMP_LIMIT * outbox_pump.PUMP_TIMEOUT_S <= 60

    def test_an_unreachable_flow_leaves_the_queue_intact(self, monkeypatch):
        def boom(*a, **kw):
            raise requests.exceptions.ConnectionError("proxy said no")
        monkeypatch.setattr(requests, "post", boom)
        fc.queue_command(URL, "send_debug_report", {"n": 1})
        delivered, waiting = outbox_pump.pump_now()
        assert (delivered, waiting) == (0, 1)
        assert fc.outbox_depth("send_debug_report") == 1

    def test_one_broken_queue_does_not_stop_the_others(self, posts, monkeypatch):
        fc.queue_command(URL, "aaa_broken", {"n": 1})
        fc.queue_command(URL, "zzz_fine", {"n": 2})

        real = fc.flush_outbox

        def selective(command, *a, **kw):
            if command == "aaa_broken":
                raise RuntimeError("disk went away")
            return real(command, *a, **kw)

        monkeypatch.setattr(fc, "flush_outbox", selective)
        delivered, _ = outbox_pump.pump_now()
        assert delivered == 1          # zzz_fine still went

    def test_pump_now_never_raises(self, monkeypatch):
        monkeypatch.setattr(fc, "flush_outbox",
                            lambda *a, **kw: (_ for _ in ()).throw(OSError("nope")))
        fc.queue_command(URL, "send_debug_report", {"n": 1})
        assert outbox_pump.pump_now() == (0, 0)

    def test_a_sandbox_run_sends_nothing(self, posts, monkeypatch, tmp_path):
        """A dev sandbox run must never deliver a real command."""
        fc.queue_command(URL, "send_debug_report", {"n": 1})
        monkeypatch.setenv("TECHDECK_SANDBOX_922_ROOT", str(tmp_path))
        delivered, waiting = outbox_pump.pump_now()
        assert posts.calls == []
        assert (delivered, waiting) == (0, 1)


class TestStart:
    def test_it_runs_off_the_calling_thread(self, posts):
        """500 seconds of worst-case flush must never land on the UI thread."""
        seen = {}
        real = outbox_pump.pump_now

        def spy(*a, **kw):
            seen["thread"] = threading.current_thread().name
            return real(*a, **kw)

        outbox_pump.pump_now = spy
        try:
            fc.queue_command(URL, "send_debug_report", {"n": 1})
            outbox_pump.start()
            for t in threading.enumerate():
                if t.name == "OutboxPump":
                    t.join(timeout=5)
        finally:
            outbox_pump.pump_now = real
        assert seen.get("thread") == "OutboxPump"

    def test_starting_twice_pumps_once(self, posts):
        fc.queue_command(URL, "send_debug_report", {"n": 1})
        outbox_pump.start()
        outbox_pump.start()
        names = [t.name for t in threading.enumerate() if t.name == "OutboxPump"]
        assert len(names) <= 1

    def test_an_empty_outbox_starts_nothing_expensive(self, posts):
        outbox_pump.start()
        for t in threading.enumerate():
            if t.name == "OutboxPump":
                t.join(timeout=5)
        assert posts.calls == []
