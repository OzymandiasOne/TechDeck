"""`sdk.post_cards` — the card flows reporting what really happened.

Batch 488 is the whole reason this exists: every one of 35 card runs died
inside the flow at 858 ms, the webhook had already returned a 2xx, and
TechDeck logged DONE. A 2xx means the flow ACCEPTED the message. Nothing more.

Two properties are load-bearing and easy to break by accident:

* **The payload goes out VERBATIM.** These four flows have a live contract and
  installed TechDecks pointed at them. Wrapping a card payload in the two-way
  envelope (as `ask_flow` does) would take every one of them down.
* **Nothing changes until a flow is upgraded.** A flow with no Response action
  returns a bare 2xx, and the plugin must then report exactly what it reports
  today — no scary error line, no claim that cards were created. This code has
  to be shippable before a single flow is touched.
"""
from __future__ import annotations

import json

import pytest

from techdeck.core import flow_client as fc
from techdeck.core import plugin_sdk as sdk

URL = "https://example.invalid/cards"

# A real-shaped 922 Setup card payload. The point is that it arrives unchanged.
CARD_PAYLOAD = {
    "plan": "D922 PIPELINE",
    "batch": "493",
    "buckets": [{"name": "BATCH 493: MODEL CHECK", "cards": []}],
    "titles": ["BATCH 493: 1234-5"],
}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
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


@pytest.fixture
def posts(monkeypatch):
    import requests

    class Recorder:
        def __init__(self):
            self.calls = []
            self.reply = FakeResponse(200, None, text="")

        def __call__(self, url, json=None, timeout=None, **kw):
            self.calls.append((url, json, timeout))
            if isinstance(self.reply, Exception):
                raise self.reply
            return self.reply

    rec = Recorder()
    monkeypatch.setattr(requests, "post", rec)
    return rec


@pytest.fixture
def log():
    lines = []
    return lines.append, lines


def card_answer(ok=True, message="", **data):
    return {"ok": ok, "reason": "created", "message": message, "data": data}


# ---------------------------------------------------------------------------
# The payload must not be touched
# ---------------------------------------------------------------------------

def test_the_card_payload_is_posted_verbatim(posts, log):
    """No envelope, no extra keys, no renames. The flow's contract is the
    payload, and an installed TechDeck is pointed at that same flow."""
    say, _ = log
    sdk.post_cards(URL, CARD_PAYLOAD, say, what="922 cards")
    _, sent, _ = posts.calls[-1]
    assert sent == CARD_PAYLOAD
    assert "command_id" not in sent and "data" not in sent


# ---------------------------------------------------------------------------
# A flow that cannot answer yet: nothing changes
# ---------------------------------------------------------------------------

def test_a_one_way_flow_still_reads_as_delivered(posts, log):
    say, lines = log
    result = sdk.post_cards(URL, CARD_PAYLOAD, say, what="922 cards")
    assert result.delivered is True
    assert result.knows is False
    assert result.answer.reason == fc.REASON_NO_ANSWER
    assert result.created is None, "it must not invent a count"


def test_a_one_way_flow_is_not_reported_as_an_error(posts, log):
    """A flow whose Response action has not been added yet is behaving
    correctly. Calling that an ERROR would cry wolf on every card post until
    all four flows are upgraded."""
    say, lines = log
    sdk.post_cards(URL, CARD_PAYLOAD, say, what="922 cards")
    assert not [ln for ln in lines if "ERROR" in ln], lines
    assert any("accepted the request" in ln for ln in lines), lines


def test_a_one_way_flow_headline_never_claims_cards_were_created(posts, log):
    say, _ = log
    result = sdk.post_cards(URL, CARD_PAYLOAD, say)
    line = result.headline(35)
    assert "Requested 35 card(s)" in line
    assert "created" not in line


def test_expecting_an_answer_makes_a_bare_2xx_a_fault(posts, log):
    """The flip side: once a flow IS known to answer, silence is a real
    problem and must not be swallowed."""
    say, lines = log
    answer = fc.post_payload(URL, CARD_PAYLOAD, label="cards", log=say,
                             expect_answer=True)
    assert answer.reason == fc.REASON_BAD_ANSWER
    assert any("ERROR" in ln for ln in lines)


# ---------------------------------------------------------------------------
# A flow that answers: the truth
# ---------------------------------------------------------------------------

def test_the_counts_come_through(posts, log):
    say, _ = log
    posts.reply = FakeResponse(200, card_answer(created=31, skipped=4, failed=1))
    result = sdk.post_cards(URL, CARD_PAYLOAD, say)
    assert (result.knows, result.created, result.skipped, result.failed) == \
        (True, 31, 4, 1)
    assert result.headline(35) == \
        "DONE. 31 card(s) created, 4 already there, 1 FAILED."


def test_counts_sent_as_strings_still_count(posts, log):
    """Power Automate hands back a string for a number often enough."""
    say, _ = log
    posts.reply = FakeResponse(200, card_answer(created="31", skipped="0"))
    result = sdk.post_cards(URL, CARD_PAYLOAD, say)
    assert result.created == 31
    assert result.skipped == 0


def test_rubbish_counts_read_as_unknown_not_zero(posts, log):
    """'0 created' and 'the flow did not say' must never look alike."""
    say, _ = log
    posts.reply = FakeResponse(200, card_answer(created="lots", skipped=None))
    result = sdk.post_cards(URL, CARD_PAYLOAD, say)
    assert result.created is None and result.skipped is None


def test_per_card_failures_are_logged_and_listed(posts, log):
    say, lines = log
    posts.reply = FakeResponse(200, card_answer(
        created=30, failed=1,
        failures=["BATCH 493: 1234-5 - label slot missing"],
        failed_titles=["BATCH 493: 1234-5"]))
    result = sdk.post_cards(URL, CARD_PAYLOAD, say)
    assert result.failed_titles == ["BATCH 493: 1234-5"]
    assert any("label slot missing" in ln for ln in lines), lines


def test_reported_failures_mark_the_run_as_a_warning(posts, log):
    """The Batch 488 fix in one assertion: a partial post must stop looking
    like a clean success."""
    say, _ = log
    params = {}
    posts.reply = FakeResponse(200, card_answer(created=30, failed=5))
    sdk.post_cards(URL, CARD_PAYLOAD, say, params=params)
    assert params["run_outcome"]["status"] == sdk.RUN_OUTCOME_WARNING
    assert "5 card(s) were not created" in params["run_outcome"]["message"]


def test_a_clean_post_leaves_the_run_outcome_alone(posts, log):
    say, _ = log
    params = {}
    posts.reply = FakeResponse(200, card_answer(created=31, failed=0))
    sdk.post_cards(URL, CARD_PAYLOAD, say, params=params)
    assert "run_outcome" not in params


def test_a_rejection_is_delivered_but_not_done(posts, log):
    """The flow decided, and it said no. Nothing was created, so a caller must
    not record the cards -- but the post itself did not fail."""
    say, _ = log
    params = {}
    posts.reply = FakeResponse(200, {
        "ok": False, "reason": "already_posted",
        "message": "Batch 493 already has its cards.", "data": {}})
    result = sdk.post_cards(URL, CARD_PAYLOAD, say, params=params)
    assert result.delivered is True
    assert result.knows is True
    assert result.answer.rejected is True
    assert result.headline(35) == "NOT DONE: Batch 493 already has its cards."
    assert params["run_outcome"]["status"] == sdk.RUN_OUTCOME_WARNING


def test_a_job_id_is_surfaced(posts, log):
    """A 35-card post can pass the platform's 120 s answer window, so the flow
    hands back a job id instead of finishing."""
    say, lines = log
    posts.reply = FakeResponse(200, card_answer(job_id="job-7"))
    result = sdk.post_cards(URL, CARD_PAYLOAD, say)
    assert result.job_id == "job-7"
    assert any("still working" in ln for ln in lines), lines


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------

def test_an_unreachable_flow_is_not_delivered(posts, log):
    import requests
    say, _ = log
    posts.reply = requests.exceptions.ConnectionError("proxy said no")
    result = sdk.post_cards(URL, CARD_PAYLOAD, say)
    assert result.delivered is False
    assert "FAILED" in result.headline(35)


def test_an_http_error_is_not_delivered(posts, log):
    say, _ = log
    posts.reply = FakeResponse(500, None, text="boom")
    result = sdk.post_cards(URL, CARD_PAYLOAD, say)
    assert result.delivered is False


def test_a_broken_flow_does_not_claim_nothing_was_created(posts, log):
    """The flow died partway. We have no idea how far it got, so the one thing
    the line must not say is that no cards exist."""
    say, _ = log
    posts.reply = FakeResponse(500, None, text="boom")
    line = sdk.post_cards(URL, CARD_PAYLOAD, say).headline(35)
    assert "may have been created" in line
    assert "were not created" not in line


# ---------------------------------------------------------------------------
# The slow flow
#
# The live 922 Setup flow runs ~71 s on a normal batch and averages nearer two
# minutes, against a 120 s platform answer window. A post that outlives the
# window is the realistic case, not a corner one, and the flow is still
# creating cards while it happens.
# ---------------------------------------------------------------------------

def test_a_card_post_waits_longer_than_a_quick_two_way_call(posts, log):
    """The 20 s default would have timed out on every single real card post."""
    say, _ = log
    sdk.post_cards(URL, CARD_PAYLOAD, say)
    assert posts.calls[-1][2] == fc.CARD_POST_TIMEOUT_S
    assert fc.CARD_POST_TIMEOUT_S > fc.PLATFORM_ANSWER_WINDOW_S


def test_a_timed_out_post_is_never_reported_as_a_failure(posts, log):
    """It is still working. Telling the user it failed sends them off to
    re-run a job that is already running."""
    import requests
    say, _ = log
    params = {}
    posts.reply = requests.exceptions.ReadTimeout("still going")
    result = sdk.post_cards(URL, CARD_PAYLOAD, say, params=params)
    assert result.delivered is True
    assert result.knows is False
    assert result.answer.reason == fc.REASON_TIMED_OUT
    line = result.headline(35)
    assert "FAILED" not in line
    assert "may still be on their way" in line
    # Not a clean success either - nobody knows yet whether the cards exist.
    assert params["run_outcome"]["status"] == sdk.RUN_OUTCOME_WARNING


def test_no_url_sends_nothing_and_is_not_delivered(posts, log):
    say, _ = log
    result = sdk.post_cards("", CARD_PAYLOAD, say)
    assert posts.calls == []
    assert result.delivered is False
    assert result.answer.reason == fc.REASON_NOT_CONFIGURED


# ---------------------------------------------------------------------------
# The sandbox
# ---------------------------------------------------------------------------

def test_a_sandbox_run_posts_nothing_but_carries_on(posts, log, monkeypatch,
                                                    tmp_path):
    """`sandbox_922 launch ready` runs the real apps against Batch 900. The
    only thing between that and real cards on the live Planner board is this
    check, so the sandbox must be honoured by every sender -- and the plugin
    must still take its success path, or the sandbox exercises nothing."""
    say, lines = log
    monkeypatch.setenv("TECHDECK_SANDBOX_922_ROOT", str(tmp_path))
    result = sdk.post_cards(URL, CARD_PAYLOAD, say, what="922 cards")
    assert posts.calls == [], "a sandbox run must never reach a real flow"
    assert result.delivered is True
    assert result.knows is False
    assert "sandbox" in result.headline(35).lower()
    assert any("SANDBOX" in ln for ln in lines), lines


def test_a_sandbox_run_leaves_the_payload_to_look_at(posts, log, monkeypatch,
                                                     tmp_path):
    say, _ = log
    monkeypatch.setenv("TECHDECK_SANDBOX_922_ROOT", str(tmp_path))
    sdk.post_cards(URL, CARD_PAYLOAD, say, what="922 cards")
    previews = list((tmp_path / "TechDeck").glob("last_flow_*.json"))
    assert previews, "the previewed payload should be inspectable"
    assert json.loads(previews[0].read_text(encoding="utf-8")) == CARD_PAYLOAD
