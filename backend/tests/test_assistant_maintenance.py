# ruff: noqa: F811
"""Maintenance tool writes share the chat transaction and retain exact history."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session
from test_ai_assistant import Case, case, step  # noqa: F401

from lifegather.chat.models import Turn
from lifegather.chat.service import ChatService
from lifegather.maintenance.schemas import (
    MaintenanceChange,
    MaintenanceCreate,
    MaintenanceHistory,
    MaintenancePage,
)
from lifegather.maintenance.service import MaintenanceService


def change(field: str, value: str | None, quote: str) -> dict[str, Any]:
    return {"field": field, "value": value, "quote": quote}


def write(quote: str, *changes: dict[str, Any]) -> dict[str, Any]:
    return {"intent_quote": quote, "changes": list(changes)}


def tasks(case: Case, asset: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = MaintenanceService(case.engine).list(
        case.actor, MaintenancePage(entity_id=asset, state="all")
    )["items"]
    return items


def seed(case: Case, asset: str, key: str = "seed") -> str:
    return MaintenanceService(case.engine).create(
        case.actor,
        MaintenanceCreate.model_validate(
            {
                "entity_id": asset,
                "request_id": key,
                "title": "oil change",
                "due_on": "2026-11-03",
                "timezone": "America/Los_Angeles",
                "text": "My oil change is due 2026-11-03",
            }
        ),
    )["id"]


@pytest.mark.parametrize("completed", [False, True])
def test_creates_one_sourced_task_and_replays_without_duplicate(
    case: Case, completed: bool
) -> None:
    asset = case.asset("Synthetic mower", "mower")
    text = (
        "Log completed oil change on my Synthetic mower"
        if completed
        else "Add oil change to my Synthetic mower"
    )
    conversation = case.conversation()
    fields = [change("title", "oil change", "oil change")]
    if completed:
        fields.append(change("state", "completed", "Log completed oil change"))
    result = case.send(
        conversation,
        "create-task",
        text,
        step("search_assets", query="mower"),
        step("read_asset", asset_id=asset),
        step("create_maintenance", asset_id=asset, maintenance=write(text, *fields)),
    )["result"]
    saved = tasks(case, asset)
    assert len(saved) == 1
    revision = saved[0]["revision"]
    assert revision["title"] == "oil change"
    assert revision["state"] == ("completed" if completed else "open")
    assert revision["due_on"] is None and revision["completed_on"] is None
    assert revision["origin"]["method"] == "ai_assistant"
    assert result["changed_entity_id"] == asset
    assert result["navigation"]["entity_id"] == asset
    assert result["maintenance"]["task_id"] == saved[0]["id"]
    assert result["maintenance"]["revision_id"] == revision["id"]
    assert result["sources"][0]["id"] == revision["source_id"]
    assert text in result["sources"][0]["text"]
    calls = len(case.provider.calls)
    assert case.send(conversation, "create-task", text)["result"] == result
    assert len(case.provider.calls) == calls and len(tasks(case, asset)) == 1


def test_task_and_source_roll_back_when_chat_receipt_fails(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lifegather.chat.assistant import AssistantRunner
    from lifegather.memory.service import MemoryError

    asset = case.asset("Synthetic mower", "mower")

    def fail(*args: Any, **kwargs: Any) -> None:
        raise MemoryError("Synthetic receipt failure")

    monkeypatch.setattr(AssistantRunner, "_commit", fail)
    result = case.send(
        case.conversation(),
        "rollback-task",
        "Add oil change to my Synthetic mower",
        step("search_assets", query="mower"),
        step("read_asset", asset_id=asset),
        step(
            "create_maintenance",
            asset_id=asset,
            maintenance=write(
                "Add oil change", change("title", "oil change", "oil change")
            ),
        ),
    )["result"]
    assert "Synthetic receipt failure" in result["text"]
    assert tasks(case, asset) == []


def test_revises_current_task_preserves_fields_history_and_old_replay(
    case: Case,
) -> None:
    asset = case.asset("Synthetic mower", "mower")
    identifier = seed(case, asset)
    service = MaintenanceService(case.engine)
    conversation = case.conversation()
    first = case.send(
        conversation,
        "complete-task",
        "Mark my mower oil change complete",
        step("search_assets", query="mower"),
        step("list_maintenance", asset_id=asset),
        step("read_maintenance", maintenance_task_id=identifier),
        step(
            "revise_maintenance",
            asset_id=asset,
            maintenance_task_id=identifier,
            maintenance=write(
                "Mark my mower oil change complete",
                change("state", "completed", "complete"),
            ),
        ),
    )["result"]
    current = service.get(case.actor, identifier)["revision"]
    assert current["state"] == "completed" and current["completed_on"] is None
    assert current["due_on"] == "2026-11-03"
    assert current["timezone"] == "America/Los_Angeles"
    assert current["title"] == "oil change"
    for state, verb in [("canceled", "Cancel"), ("open", "Reopen")]:
        case.send(
            conversation,
            state,
            f"{verb} my mower oil change",
            step("search_assets", query="mower"),
            step("list_maintenance", asset_id=asset),
            step("read_maintenance", maintenance_task_id=identifier),
            step(
                "revise_maintenance",
                asset_id=asset,
                maintenance_task_id=identifier,
                maintenance=write(
                    f"{verb} my mower oil change", change("state", state, verb)
                ),
            ),
        )
        current = service.get(case.actor, identifier)["revision"]
        assert current["state"] == state and current["completed_on"] is None
        assert current["due_on"] == "2026-11-03"
    calls = len(case.provider.calls)
    assert (
        case.send(conversation, "complete-task", "Mark my mower oil change complete")[
            "result"
        ]
        == first
    )
    assert len(case.provider.calls) == calls
    assert service.get(case.actor, identifier)["revision"]["state"] == "open"
    history = service.history(case.actor, MaintenanceHistory(task_id=identifier))
    assert len(history["items"]) == 4


@pytest.mark.parametrize(
    "text, quote",
    [
        ("Should I log oil change on my mower?", "log oil change"),
        ("Don't log oil change on my mower", "log oil change"),
        ('The manual says "log oil change" on my mower', "log oil change"),
        ("If I log oil change on my mower, what happens?", "log oil change"),
    ],
)
def test_questions_negation_and_quoted_instructions_do_not_authorize_writes(
    case: Case,
    text: str,
    quote: str,
) -> None:
    asset = case.asset("Synthetic mower", "mower")
    result = case.send(
        case.conversation(),
        "not-a-write",
        text,
        step("search_assets", query="mower"),
        step("read_asset", asset_id=asset),
        step(
            "create_maintenance",
            asset_id=asset,
            maintenance=write(quote, change("title", "oil change", "oil change")),
        ),
        step("answer", message="No maintenance was requested."),
    )["result"]
    assert tasks(case, asset) == [] and not result.get("changed_entity_id")


def test_same_name_assets_cannot_be_silently_selected(case: Case) -> None:
    first = case.asset("Synthetic mower", "first")
    second = case.asset("Synthetic mower", "second")
    result = case.send(
        case.conversation(),
        "ambiguous-asset",
        "Add oil change to my Synthetic mower",
        step("search_assets", query="mower"),
        step("read_asset", asset_id=first),
        step(
            "create_maintenance",
            asset_id=first,
            maintenance=write(
                "Add oil change", change("title", "oil change", "oil change")
            ),
        ),
        step(
            "clarify",
            message="Open the specific mower first.",
            choice_ids=[first, second],
        ),
    )["result"]
    assert result["choices"] and tasks(case, first) == [] and tasks(case, second) == []


def test_same_name_tasks_need_an_explicit_task_choice(case: Case) -> None:
    asset = case.asset("Synthetic mower", "mower")
    first, second = seed(case, asset, "first"), seed(case, asset, "second")
    result = case.send(
        case.conversation(),
        "ambiguous-task",
        "Mark my mower oil change complete",
        step("search_assets", query="mower"),
        step("list_maintenance", asset_id=asset),
        step("read_maintenance", maintenance_task_id=first),
        step(
            "revise_maintenance",
            asset_id=asset,
            maintenance_task_id=first,
            maintenance=write(
                "Mark my mower oil change complete",
                change("state", "completed", "complete"),
            ),
        ),
        step("clarify", message="Which oil change?", choice_ids=[first, second]),
    )["result"]
    assert len(result["maintenance_choices"]) == 2
    assert all(t["revision"]["state"] == "open" for t in tasks(case, asset))


def test_changes_after_read_are_refused_including_after_clarification(
    case: Case,
) -> None:
    asset = case.asset("Synthetic mower", "mower")
    identifier = seed(case, asset)
    conversation = case.conversation()
    result = case.send(
        conversation,
        "question",
        "Mark my mower oil change complete",
        step("search_assets", query="mower"),
        step("list_maintenance", asset_id=asset),
        step("read_maintenance", maintenance_task_id=identifier),
        step("clarify", message="Is the completion date unknown?"),
    )["result"]
    assert result["assistant_pending"]["maintenance_known"]
    service = MaintenanceService(case.engine)
    prior = service.get(case.actor, identifier)
    service.revise(
        case.actor,
        MaintenanceChange.model_validate(
            {
                "task_id": identifier,
                "state_token": prior["state_token"],
                "request_id": "direct-correct",
                "title": "corrected oil change",
                "due_on": None,
                "timezone": "UTC",
                "text": "Corrected task title",
            }
        ),
    )
    result = case.send(
        conversation,
        "stale-answer",
        "Yes, unknown",
        step("read_maintenance", maintenance_task_id=identifier),
        step(
            "revise_maintenance",
            asset_id=asset,
            maintenance_task_id=identifier,
            maintenance=write(
                "Mark my mower oil change complete",
                change("state", "completed", "complete"),
            ),
        ),
    )["result"]
    assert "changed" in result["text"] and not result.get("changed_entity_id")
    assert (
        service.get(case.actor, identifier)["revision"]["title"]
        == "corrected oil change"
    )


def test_explicit_task_choice_completes_only_the_chosen_task(case: Case) -> None:
    asset = case.asset("Synthetic mower", "mower")
    first, second = seed(case, asset, "first"), seed(case, asset, "second")
    conversation = case.conversation()
    result = case.send(
        conversation,
        "choose",
        "Mark my mower oil change complete",
        step("search_assets", query="mower"),
        step("list_maintenance", asset_id=asset),
        step("read_maintenance", maintenance_task_id=second),
        step("clarify", message="Which oil change?", choice_ids=[first, second]),
    )["result"]
    choice = next(c for c in result["maintenance_choices"] if c["id"] == second)
    saved = case.send(
        conversation,
        "chosen",
        "Use " + choice["name"],
        step("read_maintenance", maintenance_task_id=second),
        step(
            "revise_maintenance",
            asset_id=asset,
            maintenance_task_id=second,
            maintenance=write(
                "Mark my mower oil change complete",
                change("state", "completed", "complete"),
            ),
        ),
    )["result"]
    assert saved["maintenance"]["task_id"] == second
    service = MaintenanceService(case.engine)
    assert service.get(case.actor, first)["revision"]["state"] == "open"
    assert service.get(case.actor, second)["revision"]["state"] == "completed"


@pytest.mark.parametrize("answer", ["Never mind", "No", "What is an oil change?"])
def test_abandoned_pending_request_does_not_authorize_a_write(
    case: Case, answer: str
) -> None:
    asset = case.asset("Synthetic mower", "mower")
    conversation = case.conversation()
    case.send(
        conversation,
        "ask-first",
        "Add oil change to my mower",
        step("search_assets", query="mower"),
        step("read_asset", asset_id=asset),
        step("clarify", message="Should the due date stay unknown?"),
    )
    result = case.send(
        conversation,
        "abandon",
        answer,
        step(
            "create_maintenance",
            asset_id=asset,
            maintenance=write(
                "Add oil change", change("title", "oil change", "oil change")
            ),
        ),
        step("answer", message="No task saved."),
    )["result"]
    assert not result.get("changed_entity_id") and tasks(case, asset) == []


@pytest.mark.parametrize("revise", [False, True])
def test_research_read_blocks_every_maintenance_write(case: Case, revise: bool) -> None:
    asset = case.asset("Synthetic mower", "mower")
    identifier = seed(case, asset)
    script = [
        step("search_assets", query="mower"),
        step("list_maintenance", asset_id=asset),
    ]
    if revise:
        script.append(step("read_maintenance", maintenance_task_id=identifier))
    script += [
        step("read_asset_research", asset_id=asset),
        step(
            "revise_maintenance" if revise else "create_maintenance",
            asset_id=asset,
            maintenance_task_id=identifier if revise else None,
            maintenance=write(
                "Log completed oil change",
                change("title", "oil change", "oil change"),
                change("state", "completed", "completed"),
            ),
        ),
        step("answer", message="Please make a fresh request to save this."),
    ]
    result = case.send(
        case.conversation(), "research", "Log completed oil change on my mower", *script
    )["result"]
    assert not result.get("changed_entity_id") and len(tasks(case, asset)) == 1
    assert tasks(case, asset)[0]["revision"]["state"] == "open"


def test_cannot_complete_a_different_unmentioned_task(case: Case) -> None:
    asset = case.asset("Synthetic mower", "mower")
    identifier = seed(case, asset)
    result = case.send(
        case.conversation(),
        "wrong-task",
        "Mark my mower blade repair complete",
        step("search_assets", query="mower"),
        step("list_maintenance", asset_id=asset),
        step("read_maintenance", maintenance_task_id=identifier),
        step(
            "revise_maintenance",
            asset_id=asset,
            maintenance_task_id=identifier,
            maintenance=write(
                "Mark my mower blade repair complete",
                change("state", "completed", "complete"),
            ),
        ),
        step("clarify", message="Which task should I complete?"),
    )["result"]
    assert not result.get("changed_entity_id")
    assert tasks(case, asset)[0]["revision"]["state"] == "open"


def test_relative_completion_uses_local_request_day_and_survives_clarification_midnight(
    case: Case,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time

    asset = case.asset("Synthetic mower", "mower")
    instant = [datetime(2026, 10, 23, 6, 59, tzinfo=UTC)]
    monkeypatch.setattr(
        time,
        "time_ns",
        lambda: int(instant[0].timestamp() * 1_000_000_000),
    )
    conversation = case.conversation()

    def ask(payload: dict[str, Any]) -> dict[str, Any]:
        assert payload["maintenance_date_context"] == {
            "today": "2026-10-22",
            "timezone": "America/Los_Angeles",
        }
        return step("clarify", message="Should the due date stay unknown?")

    case.send(
        conversation,
        "before-midnight",
        "Log completed oil change today on my mower",
        step("search_assets", query="mower"),
        step("read_asset", asset_id=asset),
        ask,
        timezone="America/Los_Angeles",
    )
    instant[0] = datetime(2026, 10, 23, 7, 1, tzinfo=UTC)

    def save_after_midnight(payload: dict[str, Any]) -> dict[str, Any]:
        assert payload["origin_maintenance_dates"][0] == {
            "message_index": 0,
            "today": "2026-10-22",
            "timezone": "America/Los_Angeles",
        }
        return step(
            "create_maintenance",
            asset_id=asset,
            maintenance=write(
                "Log completed oil change today",
                change("title", "oil change", "oil change"),
                change("state", "completed", "completed"),
                change("completed_on", "2026-10-22", "today"),
            ),
        )

    result = case.send(
        conversation,
        "after-midnight",
        "Yes, unknown",
        save_after_midnight,
        timezone="America/Los_Angeles",
    )["result"]
    assert result["maintenance"]["completed_on"] == "2026-10-22"
    assert result["maintenance"]["timezone"] == "America/Los_Angeles"
    assert tasks(case, asset)[0]["revision"]["due_on"] is None


def test_relative_date_without_request_timezone_asks_instead_of_guessing(
    case: Case,
) -> None:
    asset = case.asset("Synthetic mower", "mower")
    result = case.send(
        case.conversation(),
        "unknown-zone",
        "Log completed oil change today on my mower",
        step("search_assets", query="mower"),
        step("read_asset", asset_id=asset),
        step(
            "create_maintenance",
            asset_id=asset,
            maintenance=write(
                "Log completed oil change today",
                change("title", "oil change", "oil change"),
                change("state", "completed", "completed"),
                change("completed_on", "2026-10-23", "today"),
            ),
        ),
        step("clarify", message="What calendar date was the oil change?"),
    )["result"]
    assert result["assistant_pending"] and tasks(case, asset) == []


def test_retained_task_retry_cites_original_revision_after_chat_reply_is_removed(
    case: Case,
) -> None:
    asset = case.asset("Synthetic mower", "mower")
    conversation = case.conversation()
    message = "Log completed oil change on my mower"

    def send() -> dict[str, Any]:
        result: dict[str, Any] = case.send(
            conversation,
            "retained-task",
            message,
            step("search_assets", query="mower"),
            step("read_asset", asset_id=asset),
            step(
                "create_maintenance",
                asset_id=asset,
                maintenance=write(
                    "Log completed oil change",
                    change("title", "oil change", "oil change"),
                    change("state", "completed", "completed"),
                ),
            ),
        )["result"]
        return result

    original = send()
    identifier = original["maintenance"]["task_id"]
    service = MaintenanceService(case.engine)
    observed = service.get(case.actor, identifier)
    service.revise(
        case.actor,
        MaintenanceChange.model_validate(
            {
                "task_id": identifier,
                "state_token": observed["state_token"],
                "request_id": "later-reopen",
                "title": "oil change",
                "state": "open",
                "due_on": None,
                "timezone": "UTC",
                "text": "Reopen this task",
            }
        ),
    )
    with Session(case.engine) as db:
        db.execute(
            delete(Turn).where(
                Turn.user_id == case.actor.id, Turn.request_id == "retained-task"
            )
        )
        db.commit()
    calls = len(case.provider.calls)
    retried = case.send(conversation, "retained-task", message)["result"]
    assert len(case.provider.calls) == calls
    assert len(tasks(case, asset)) == 1
    assert retried["maintenance"] == original["maintenance"]
    assert retried["sources"] == original["sources"]
    assert service.get(case.actor, identifier)["revision"]["state"] == "open"


def test_retained_revision_retry_needs_no_new_model_decision(case: Case) -> None:
    asset = case.asset("Synthetic mower", "mower")
    identifier = seed(case, asset)
    conversation = case.conversation()
    message = "Mark my mower oil change complete"
    original = case.send(
        conversation,
        "retained-revision",
        message,
        step("search_assets", query="mower"),
        step("list_maintenance", asset_id=asset),
        step("read_maintenance", maintenance_task_id=identifier),
        step(
            "revise_maintenance",
            asset_id=asset,
            maintenance_task_id=identifier,
            maintenance=write(message, change("state", "completed", "complete")),
        ),
    )["result"]
    service = MaintenanceService(case.engine)
    observed = service.get(case.actor, identifier)
    service.revise(
        case.actor,
        MaintenanceChange.model_validate(
            {
                "task_id": identifier,
                "state_token": observed["state_token"],
                "request_id": "later-reopen",
                "title": "oil change",
                "state": "open",
                "due_on": "2026-11-03",
                "timezone": "America/Los_Angeles",
                "text": "Reopen this task",
            }
        ),
    )
    with Session(case.engine) as db:
        db.execute(
            delete(Turn).where(
                Turn.user_id == case.actor.id, Turn.request_id == "retained-revision"
            )
        )
        db.commit()
    calls = len(case.provider.calls)
    replay = case.send(conversation, "retained-revision", message)["result"]
    assert len(case.provider.calls) == calls
    assert replay["maintenance"] == original["maintenance"]
    assert replay["sources"] == original["sources"]
    assert service.get(case.actor, identifier)["revision"]["state"] == "open"
    with Session(case.engine) as db:
        db.execute(
            delete(Turn).where(
                Turn.user_id == case.actor.id, Turn.request_id == "retained-revision"
            )
        )
        db.commit()
    changed = case.client.post(
        f"/api/chat/conversations/{conversation}/turns",
        headers=case.headers,
        json={
            "request_id": "retained-revision",
            "mode": "assistant",
            "text": "Cancel my mower oil change",
            "credential_id": case.credential,
            "model": "fixture-model",
        },
    )
    assert changed.status_code in {400, 409}
    assert "identity" in str(changed.json()).lower()


def test_exact_task_reply_replays_before_stale_context_validation(case: Case) -> None:
    from lifegather.chat.context import ContextRead, WorkspaceContexts

    asset = case.asset("Synthetic mower", "mower")
    observed = WorkspaceContexts(case.engine).read(
        case.actor, ContextRead(page="Assets", entity_id=asset)
    )
    context = {"page": "Assets", "entity_id": asset, "version": observed["version"]}
    conversation = case.conversation()
    message = "Add oil change to my mower"
    original = case.send(
        conversation,
        "context-replay",
        message,
        step(
            "create_maintenance",
            asset_id=asset,
            maintenance=write(message, change("title", "oil change", "oil change")),
        ),
        context=context,
    )["result"]
    replay = case.send(conversation, "context-replay", message, context=context)[
        "result"
    ]
    assert replay == original and len(tasks(case, asset)) == 1


def test_cancellation_before_maintenance_commit_saves_no_task(case: Case) -> None:
    asset = case.asset("Synthetic mower", "mower")

    def cancel(payload: dict[str, Any]) -> dict[str, Any]:
        ChatService(case.engine).cancel(case.actor, "cancel-maintenance")
        return step(
            "create_maintenance",
            asset_id=asset,
            maintenance=write(
                "Log oil change", change("title", "oil change", "oil change")
            ),
        )

    stopped = case.send(
        case.conversation(),
        "cancel-maintenance",
        "Log oil change on my mower",
        step("search_assets", query="mower"),
        step("read_asset", asset_id=asset),
        cancel,
    )
    assert stopped["state"] == "canceled" and tasks(case, asset) == []


def test_foreign_task_ids_are_not_available_to_read_or_revise(case: Case) -> None:
    own = case.asset("Synthetic mower", "own")
    foreign = case.asset("Private mower", "foreign", actor=case.other_actor)
    other = MaintenanceService(case.engine).create(
        case.other_actor,
        MaintenanceCreate.model_validate(
            {
                "entity_id": foreign,
                "request_id": "private-task",
                "title": "Private service",
                "due_on": None,
                "timezone": "UTC",
                "text": "Private source statement",
            }
        ),
    )["id"]

    def denied(payload: dict[str, Any]) -> dict[str, Any]:
        assert "Unknown maintenance task" in payload["steps"][-1]["error"]
        assert "Private source statement" not in str(payload)
        return step("answer", message="That task is unavailable.")

    result = case.send(
        case.conversation(),
        "foreign-task",
        "Mark my mower service complete",
        step("search_assets", query="mower"),
        step("list_maintenance", asset_id=own),
        step("read_maintenance", maintenance_task_id=other),
        denied,
    )["result"]
    assert not result.get("maintenance") and tasks(case, own) == []


def test_limited_task_list_needs_an_explicit_choice_before_writing(case: Case) -> None:
    asset = case.asset("Synthetic mower", "mower")
    service = MaintenanceService(case.engine)
    for i in range(21):
        service.create(
            case.actor,
            MaintenanceCreate.model_validate(
                {
                    "entity_id": asset,
                    "request_id": f"task-{i}",
                    "title": f"service {i}",
                    "due_on": None,
                    "timezone": "UTC",
                    "text": f"My service {i} task",
                }
            ),
        )
    chosen = service.list(
        case.actor, MaintenancePage(entity_id=asset, state="all", limit=20)
    )["items"][0]
    title = chosen["revision"]["title"]
    text = f"Mark my mower {title} complete"
    result = case.send(
        case.conversation(),
        "limited",
        text,
        step("search_assets", query="mower"),
        step("list_maintenance", asset_id=asset),
        step("read_maintenance", maintenance_task_id=chosen["id"]),
        step(
            "revise_maintenance",
            asset_id=asset,
            maintenance_task_id=chosen["id"],
            maintenance=write(text, change("state", "completed", "complete")),
        ),
        step("clarify", message="Please choose the task.", choice_ids=[chosen["id"]]),
    )["result"]
    assert not result.get("maintenance") and result["maintenance_choices"]


def test_contextual_wording_can_request_a_task(case: Case) -> None:
    asset = case.asset("Synthetic mower", "mower")
    text = "For my Synthetic mower, please log oil change"
    result = case.send(
        case.conversation(),
        "contextual-wording",
        text,
        step("search_assets", query="mower"),
        step("read_asset", asset_id=asset),
        step(
            "create_maintenance",
            asset_id=asset,
            maintenance=write(
                "please log oil change", change("title", "oil change", "oil change")
            ),
        ),
    )["result"]
    assert result["maintenance"]["title"] == "oil change"


def test_blank_task_title_returns_validation_feedback_without_saving(
    case: Case,
) -> None:
    asset = case.asset("Synthetic mower", "mower")
    result = case.send(
        case.conversation(),
        "blank-title",
        "Add    to my mower",
        step("search_assets", query="mower"),
        step("read_asset", asset_id=asset),
        step(
            "create_maintenance",
            asset_id=asset,
            maintenance=write("Add    to my mower", change("title", "   ", "   ")),
        ),
        step("clarify", message="What is the task title?"),
    )["result"]
    assert result["assistant_pending"] and tasks(case, asset) == []


@pytest.mark.parametrize(
    "text",
    [
        "Log oil change on my mower as not completed",
        "Log oil change on my mower without marking it completed",
    ],
)
def test_negated_completion_cannot_be_extracted_as_completed(
    case: Case, text: str
) -> None:
    asset = case.asset("Synthetic mower", "mower")
    result = case.send(
        case.conversation(),
        "negated-completion",
        text,
        step("search_assets", query="mower"),
        step("read_asset", asset_id=asset),
        step(
            "create_maintenance",
            asset_id=asset,
            maintenance=write(
                "Log oil change",
                change("title", "oil change", "oil change"),
                change("state", "completed", "completed"),
            ),
        ),
        step("clarify", message="Please state the task status directly."),
    )["result"]
    assert tasks(case, asset) == []
    assert not result.get("changed_entity_id")
