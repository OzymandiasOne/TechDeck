"""The two-way flow client: the contract, the fallback, the outbox, the cache.

This helper is the single door every two-way Power Automate call goes through,
so a regression here breaks every feature built on it at once. Three things are
pinned hardest:

* **The envelope's keys** — the remote contract. The flows parse these names.
  Batch 488 is why: a refactor dropped the `buckets` key from a one-way
  payload, the flow's loop hit a null, and every run died at 858 ms while
  TechDeck logged DONE. A key a flow reads must be asserted by a test.
* **`ask_flow` never raises and always falls back.** A flow is an upgrade,
  never a dependency: with the flow down, offline, broken or answering
  gibberish, the caller must still get an answer object with `reached=False`
  and carry on.
* **`reached` vs `ok`.** `ok: false` is a real verdict the flow chose, so it is
  DELIVERED and leaves the outbox. Only a call that never got an answer stays
  queued. Confusing the two either re-sends a rejected command forever or
  silently drops a write nobody delivered.
"""
from __future__ import annotations

import json

import pytest

from techdeck.core import flow_client as fc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

URL = "https://example.invalid/flow"


@pytest.fixture(autouse=True)
def _isolated_flow_dir(tmp_path, monkeypatch):
    """Every test gets its own outbox/cache tree. The session conftest already
    keeps %LOCALAPPDATA% off the real one; this also keeps tests from reading
    each other's queues."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("TECHDECK_SANDBOX_922_ROOT", raising=False)
    return tmp_path


class FakeResponse:
    def __init__(self, status_code=200, body=None, text=None):
        self.status_code = status_code
        self._body = body
        self.text = text if text is not None else json.dumps(body or {})

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def answer_body(ok=True, reason="", message="", data=None):
    return {"ok": ok, "reason": reason, "message": message, "data": data or {}}


@pytest.fixture
def posts(monkeypatch):
    """Record every POST and reply with a scripted list of responses (the last
    one repeats). `posts.calls` holds (url, envelope, timeout) per call."""
    import requests

    class Recorder:
        def __init__(self):
            self.calls = []
            self.replies = [FakeResponse(200, answer_body())]

        def script(self, *replies):
            self.replies = list(replies)

        def __call__(self, url, json=None, timeout=None, **kw):
            self.calls.append((url, json, timeout))
            i = min(len(self.calls) - 1, len(self.replies) - 1)
            reply = self.replies[i]
            if isinstance(reply, Exception):
                raise reply
            return reply

    rec = Recorder()
    monkeypatch.setattr(requests, "post", rec)
    return rec


@pytest.fixture
def unreachable(monkeypatch):
    import requests

    def boom(*a, **kw):
        raise requests.exceptions.ConnectionError("proxy said no")

    monkeypatch.setattr(requests, "post", boom)


# ---------------------------------------------------------------------------
# The envelope — the remote contract
# ---------------------------------------------------------------------------

def test_envelope_carries_every_contract_key():
    """The flows read these names. Dropping one takes every flow down."""
    envelope = fc.build_envelope("post_cards", {"batch": 493})
    for key in fc.ENVELOPE_KEYS:
        assert key in envelope, f"the '{key}' key the flows read is missing"
    assert envelope["command"] == "post_cards"
    assert envelope["data"] == {"batch": 493}


def test_envelope_data_is_always_an_object():
    """A flow reading data?['x'] on a null body is a hard FAIL, not a skip, so
    `data` is sent as {} rather than omitted or null."""
    assert fc.build_envelope("probe")["data"] == {}
    assert fc.build_envelope("probe", None)["data"] == {}


def test_envelope_mints_a_command_id_and_keeps_a_given_one():
    """At-least-once delivery only works if a retry reuses the SAME id, so the
    flow can recognise the repeat and answer as it did the first time."""
    first = fc.build_envelope("probe")["command_id"]
    second = fc.build_envelope("probe")["command_id"]
    assert first and second and first != second
    assert fc.build_envelope("probe", command_id="keep-me")["command_id"] == "keep-me"


def test_envelope_data_is_copied_not_aliased():
    """The caller's dict must not keep changing under the flow's feet."""
    data = {"batch": 1}
    envelope = fc.build_envelope("probe", data)
    data["batch"] = 2
    assert envelope["data"]["batch"] == 1


# ---------------------------------------------------------------------------
# ask_flow — the fallback is the whole point
# ---------------------------------------------------------------------------

def test_no_url_configured_returns_the_fallback():
    answer = fc.ask_flow("", "probe", fallback={"created": 0})
    assert not answer.reached
    assert answer.reason == fc.REASON_NOT_CONFIGURED
    assert answer.data == {"created": 0}


def test_unreachable_flow_returns_the_fallback_and_never_raises(unreachable):
    answer = fc.ask_flow(URL, "probe", {"x": 1}, fallback={"created": 0})
    assert not answer.reached
    assert answer.ok is False
    assert answer.reason == fc.REASON_UNREACHABLE
    assert answer.data == {"created": 0}


def test_http_error_is_not_reached(posts):
    """A non-2xx means the FLOW broke — not that it decided anything."""
    posts.script(FakeResponse(500, None, text="boom"))
    answer = fc.ask_flow(URL, "probe", fallback={"created": 0})
    assert not answer.reached
    assert answer.reason == fc.REASON_FLOW_ERROR
    assert answer.status == 500
    assert answer.data == {"created": 0}


def test_answer_that_breaks_the_shape_is_not_reached(posts):
    """2xx with a body we cannot read is the flow breaking its contract. It
    must not be mistaken for a verdict."""
    posts.script(FakeResponse(200, None, text="Accepted"))
    answer = fc.ask_flow(URL, "probe", fallback={"created": 0})
    assert not answer.reached
    assert answer.reason == fc.REASON_BAD_ANSWER


def test_a_2xx_without_an_ok_key_is_not_reached(posts):
    posts.script(FakeResponse(200, {"message": "sure"}))
    answer = fc.ask_flow(URL, "probe")
    assert not answer.reached
    assert answer.reason == fc.REASON_BAD_ANSWER


def test_a_good_answer_comes_through_whole(posts):
    posts.script(FakeResponse(200, answer_body(
        ok=True, reason="created", message="Made 31 cards.",
        data={"created": 31, "skipped": 4})))
    answer = fc.ask_flow(URL, "post_cards", {"batch": 493})
    assert answer.reached and answer.ok
    assert answer.rejected is False
    assert answer.data["created"] == 31
    assert answer.message == "Made 31 cards."


def test_a_rejection_is_a_normal_answer_not_an_error(posts):
    """`ok: false` is the flow deliberately saying no. It was REACHED."""
    posts.script(FakeResponse(200, answer_body(
        ok=False, reason="already_posted", message="Batch 493 already has cards.")))
    answer = fc.ask_flow(URL, "post_cards", {"batch": 493}, fallback={"created": 0})
    assert answer.reached
    assert answer.ok is False
    assert answer.rejected is True
    assert answer.reason == "already_posted"
    # A real verdict is NOT replaced by the fallback.
    assert answer.data == {}


def test_a_broken_log_callback_cannot_kill_the_call(posts):
    def bad_log(_msg):
        raise RuntimeError("console is gone")

    answer = fc.ask_flow(URL, "probe", log=bad_log)
    assert answer.reached


def test_timeout_is_clamped_to_the_socket_ceiling(posts):
    fc.ask_flow(URL, "probe", timeout=9999)
    assert posts.calls[-1][2] == fc.MAX_TIMEOUT_S
    fc.ask_flow(URL, "probe", timeout=0)
    assert posts.calls[-1][2] == fc.DEFAULT_TIMEOUT_S


def test_our_socket_ceiling_sits_above_the_platform_answer_window():
    """Deliberate: we want the gateway's own reply -- its answer, or its
    'no response' error -- to win the race against our local timeout, so the
    app learns something instead of guessing."""
    assert fc.MAX_TIMEOUT_S > fc.PLATFORM_ANSWER_WINDOW_S
    assert fc.CARD_POST_TIMEOUT_S > fc.PLATFORM_ANSWER_WINDOW_S
    assert fc.CARD_POST_TIMEOUT_S <= fc.MAX_TIMEOUT_S


def test_a_timeout_is_not_the_same_as_never_arriving(posts):
    """The request WAS delivered and the flow is probably still working. The
    live card flow runs ~71 s against a 120 s window, so this is the realistic
    case. Calling it 'unreachable' would tell the user nothing happened."""
    import requests
    posts.script(requests.exceptions.ReadTimeout("took too long"))
    answer = fc.ask_flow(URL, "post_cards", fallback={"created": 0})
    assert answer.reason == fc.REASON_TIMED_OUT
    assert not answer.reached


def test_a_connect_timeout_counts_as_never_arriving(posts):
    """ConnectTimeout subclasses BOTH ConnectionError and Timeout. It is a
    connection that was never made, so it must land on `unreachable` -- which
    is why the ConnectionError branch has to be checked first."""
    import requests
    posts.script(requests.exceptions.ConnectTimeout("no route"))
    answer = fc.ask_flow(URL, "post_cards")
    assert answer.reason == fc.REASON_UNREACHABLE


def test_the_envelope_is_what_gets_posted(posts):
    fc.ask_flow(URL, "post_cards", {"batch": 493}, command_id="cid-1")
    url, envelope, _ = posts.calls[-1]
    assert url == URL
    assert envelope["command"] == "post_cards"
    assert envelope["command_id"] == "cid-1"
    assert envelope["data"] == {"batch": 493}


def test_a_fallback_flowanswer_is_returned_but_never_marked_reached(unreachable):
    """A caller may hand back a cached 'yes' as its fallback. It keeps its own
    ok/data, but `reached` stays False so nobody reports it as the flow's word."""
    cached = fc.FlowAnswer(ok=True, reason="from_cache", data={"version": "1.2"})
    answer = fc.ask_flow(URL, "probe", fallback=cached)
    assert answer.ok is True
    assert answer.reached is False
    assert answer.data == {"version": "1.2"}


def test_dry_run_sends_nothing(posts, tmp_path):
    answer = fc.ask_flow(URL, "probe", {"x": 1}, fallback={"created": 0},
                         dry_run=True)
    assert posts.calls == []
    assert not answer.reached
    assert answer.reason == fc.REASON_DRY_RUN
    assert answer.data == {"created": 0}


def test_sandbox_run_sends_nothing(posts, monkeypatch, tmp_path):
    monkeypatch.setenv("TECHDECK_SANDBOX_922_ROOT", str(tmp_path))
    answer = fc.ask_flow(URL, "probe", {"x": 1}, fallback={"created": 0})
    assert posts.calls == []
    assert answer.reason == fc.REASON_SANDBOX


def test_the_shared_empty_data_default_cannot_be_mutated():
    """A NamedTuple default is ONE shared object. If it were a plain {}, one
    caller writing into `answer.data` would poison every later answer."""
    answer = fc.FlowAnswer(ok=False)
    with pytest.raises(TypeError):
        answer.data["sneaky"] = 1  # type: ignore[index]


# ---------------------------------------------------------------------------
# The read cache
# ---------------------------------------------------------------------------

def test_a_good_answer_refreshes_the_cache(posts):
    posts.script(FakeResponse(200, answer_body(data={"kill_switch": False})))
    fc.ask_flow(URL, "get_settings", cache_key="settings")
    hit = fc.cache_get("settings")
    assert hit is not None
    data, age = hit
    assert data == {"kill_switch": False}
    assert age < 60


def test_a_rejection_does_not_overwrite_the_cache(posts):
    fc.cache_put("settings", {"kill_switch": False})
    posts.script(FakeResponse(200, answer_body(ok=False, reason="no")))
    fc.ask_flow(URL, "get_settings", cache_key="settings")
    hit = fc.cache_get("settings")
    assert hit is not None and hit[0] == {"kill_switch": False}


def test_the_cache_still_answers_when_the_flow_is_down(posts, unreachable):
    fc.cache_put("settings", {"kill_switch": True})
    answer = fc.ask_flow(URL, "get_settings", cache_key="settings")
    assert not answer.reached
    hit = fc.cache_get("settings")
    assert hit is not None and hit[0] == {"kill_switch": True}


def test_a_stale_cache_entry_is_refused():
    fc.cache_put("settings", {"a": 1})
    assert fc.cache_get("settings", max_age_s=3600) is not None
    assert fc.cache_get("settings", max_age_s=-1) is None


def test_a_missing_or_corrupt_cache_entry_reads_as_nothing():
    assert fc.cache_get("never_written") is None
    path = fc.cache_path("broken")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert fc.cache_get("broken") is None


def test_cache_clear_removes_it():
    fc.cache_put("settings", {"a": 1})
    fc.cache_clear("settings")
    assert fc.cache_get("settings") is None
    fc.cache_clear("settings")  # twice is not an error


# ---------------------------------------------------------------------------
# The outbox
# ---------------------------------------------------------------------------

def test_queue_then_flush_delivers_in_order(posts):
    fc.queue_command(URL, "save_row", {"n": 1})
    fc.queue_command(URL, "save_row", {"n": 2})
    assert fc.outbox_depth("save_row") == 2

    delivered, left = fc.flush_outbox("save_row")
    assert (delivered, left) == (2, 0)
    assert [c[1]["data"]["n"] for c in posts.calls] == [1, 2]
    assert fc.outbox_depth("save_row") == 0


def test_a_queued_command_keeps_its_id_across_a_retry(posts, unreachable):
    cid = fc.queue_command(URL, "save_row", {"n": 1})
    fc.flush_outbox("save_row")           # the flow is down: stays queued
    assert fc.outbox_depth("save_row") == 1
    assert fc.read_outbox("save_row")[0]["command_id"] == cid


def test_a_retry_resends_the_original_id_not_a_fresh_one(posts):
    """The whole point of the id: the flow must see the SAME one twice so it
    can recognise the repeat instead of doing the work again."""
    cid = fc.queue_command(URL, "save_row", {"n": 1})
    fc.flush_outbox("save_row")
    assert posts.calls[-1][1]["command_id"] == cid


def test_a_rejected_command_leaves_the_queue(posts):
    """The flow DECIDED. Re-sending it would just get rejected forever."""
    posts.script(FakeResponse(200, answer_body(ok=False, reason="duplicate")))
    fc.queue_command(URL, "save_row", {"n": 1})
    delivered, left = fc.flush_outbox("save_row")
    assert (delivered, left) == (1, 0)
    assert fc.outbox_depth("save_row") == 0


def test_an_unreachable_flow_keeps_everything_queued_and_stops_trying(posts):
    """Down for one is down for all: the flush must not hammer the flow once
    per queued row, and nothing may be lost or reordered."""
    import requests
    posts.script(requests.exceptions.ConnectionError("proxy said no"))
    for n in (1, 2, 3):
        fc.queue_command(URL, "save_row", {"n": n})

    delivered, left = fc.flush_outbox("save_row")
    assert (delivered, left) == (0, 3)
    assert len(posts.calls) == 1, "it should give up after the first failure"
    assert [e["data"]["n"] for e in fc.read_outbox("save_row")] == [1, 2, 3]


def test_a_flow_error_keeps_that_one_but_tries_the_rest(posts):
    """An HTTP 500 is this one command breaking the flow, not the network being
    gone, so the queue behind it still gets its chance."""
    posts.script(FakeResponse(500, None, text="boom"),
                 FakeResponse(200, answer_body()))
    fc.queue_command(URL, "save_row", {"n": 1})
    fc.queue_command(URL, "save_row", {"n": 2})

    delivered, left = fc.flush_outbox("save_row")
    assert (delivered, left) == (1, 1)
    assert [e["data"]["n"] for e in fc.read_outbox("save_row")] == [1]


def test_the_url_travels_with_the_queued_command(posts):
    """A command queued against the TEST flow must not later be delivered to
    the live one just because the caller's setting changed."""
    fc.queue_command("https://queued.invalid/flow", "save_row", {"n": 1})
    fc.flush_outbox("save_row", "https://live.invalid/flow")
    assert posts.calls[-1][0] == "https://queued.invalid/flow"


def test_a_queued_command_with_no_url_falls_back_to_the_flush_url(posts):
    fc.queue_command("", "save_row", {"n": 1})
    fc.flush_outbox("save_row", URL)
    assert posts.calls[-1][0] == URL


def test_a_queued_command_with_nowhere_to_go_is_parked_not_dropped(posts):
    """It must leave the live queue (which would otherwise grow forever on a
    machine that never had a URL) but it must NOT be counted as delivered.

    This used to report (1, 0) and discard the envelope. Fine for a telemetry
    row; data loss for anything a person wrote - a colleague's suggestion or
    crash report vanished while the app said "sent". Now it is parked where
    the debug report can see it, and it is neither delivered nor waiting.
    """
    fc.queue_command("", "save_row", {"n": 1})
    delivered, left = fc.flush_outbox("save_row")
    assert posts.calls == []
    assert (delivered, left) == (0, 0)
    assert fc.outbox_depth("save_row") == 0
    assert fc.dead_letter_depth("save_row") == 1
    parked = [json.loads(l) for l in
              fc.dead_letter_path("save_row").read_text(encoding="utf-8").splitlines()]
    assert parked[0]["data"]["n"] == 1
    assert parked[0]["command_id"]          # still identifiable afterwards


def test_parking_does_not_block_the_commands_behind_it(posts):
    """One undeliverable envelope must not strand a queue that is otherwise
    perfectly sendable."""
    fc.queue_command("", "save_row", {"n": 1})
    fc.queue_command(URL, "save_row", {"n": 2})
    delivered, left = fc.flush_outbox("save_row")
    assert (delivered, left) == (1, 0)
    assert fc.dead_letter_depth("save_row") == 1
    assert posts.calls[-1][1]["data"]["n"] == 2


def test_dead_letter_depth_is_zero_when_nothing_was_ever_parked():
    assert fc.dead_letter_depth("never_parked") == 0


def test_flush_respects_its_limit_and_leaves_the_rest_queued(posts):
    for n in range(5):
        fc.queue_command(URL, "save_row", {"n": n})
    delivered, left = fc.flush_outbox("save_row", limit=2)
    assert (delivered, left) == (2, 3)
    assert [e["data"]["n"] for e in fc.read_outbox("save_row")] == [2, 3, 4]


def test_flushing_an_empty_outbox_does_nothing(posts):
    assert fc.flush_outbox("never_queued") == (0, 0)
    assert posts.calls == []


def test_a_corrupt_outbox_line_does_not_strand_the_queue(posts):
    """A half-written line from a crash must not block the rows behind it."""
    fc.queue_command(URL, "save_row", {"n": 1})
    path = fc.outbox_path("save_row")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{half-written\n")
    fc.queue_command(URL, "save_row", {"n": 2})

    assert fc.outbox_depth("save_row") == 2
    delivered, left = fc.flush_outbox("save_row")
    assert (delivered, left) == (2, 0)


def test_a_sandbox_flush_sends_nothing_and_keeps_the_queue(posts, monkeypatch,
                                                           tmp_path):
    fc.queue_command(URL, "save_row", {"n": 1})
    monkeypatch.setenv("TECHDECK_SANDBOX_922_ROOT", str(tmp_path))
    delivered, left = fc.flush_outbox("save_row")
    assert posts.calls == []
    assert (delivered, left) == (0, 1)


def test_command_names_cannot_escape_their_folder():
    """A command name reaches a filename, so a stray slash or '..' must not
    land the outbox somewhere else on disk."""
    path = fc.outbox_path("../../evil name")
    assert path.parent == fc.flow_dir() / "outbox"
    assert "/" not in path.name and "\\" not in path.name
    assert fc.cache_path("a/b\\c").parent == fc.flow_dir() / "cache"
