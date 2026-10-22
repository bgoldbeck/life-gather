import json
from typing import Any

from test_ai_assistant import Case, Script, case, field, new_asset, step

from lifegather.chat.assistant import STATUS
from lifegather.chat.service import ChatService

__all__ = ["case"]


def stream(
    target: Case, conversation: str, key: str, text: str, *script: Script
) -> list[dict[str, Any]]:
    target.provider.script = list(script)
    response = target.client.post(
        f"/api/chat/conversations/{conversation}/stream",
        headers=target.headers,
        json={
            "request_id": key,
            "mode": "assistant",
            "text": text,
            "credential_id": target.credential,
            "model": "fixture-model",
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert target.provider.script == [], "unused scripted steps"
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def statuses(frames: list[dict[str, Any]]) -> list[str]:
    assert all(f["type"] in {"status", "complete"} for f in frames), frames
    assert [f["type"] for f in frames].count("complete") == 1
    assert frames[-1]["type"] == "complete"
    return [f["text"] for f in frames if f["type"] == "status"]


def test_stream_reports_host_stages_then_the_committed_turn(case: Case) -> None:
    conversation = case.conversation()
    text = "I own a Makita drill, model DHP484. Its battery type is 18V LXT."
    frames = stream(
        case,
        conversation,
        "stream-create",
        text,
        step("search_assets", query="Makita drill"),
        step(
            "create_asset",
            new_asset=new_asset(
                "Makita drill", "I own", manufacturer="Makita", model="DHP484"
            ),
            fields=[field("custom", "18V LXT", "Battery type")],
        ),
    )
    assert statuses(frames) == [
        "Checking your request…",
        STATUS["start"],
        STATUS["search_assets"],
        STATUS["next"],
        STATUS["create_asset"],
    ]
    turn = frames[-1]["turn"]
    assert turn["state"] == "complete"
    assert "Added Makita drill" in turn["result"]["text"]
    asset_id = turn["result"]["changed_entity_id"]
    assert case.current(asset_id)["profile_model"] == "DHP484"
    # Replaying the same request returns the stored turn with no provider call.
    calls = len(case.provider.calls)
    replay = stream(case, conversation, "stream-create", text)
    assert replay[-1]["turn"] == turn
    assert len(case.provider.calls) == calls
    # The same turn is visible through the ordinary history read.
    turns = case.client.get(
        f"/api/chat/conversations/{conversation}/turns", headers=case.headers
    ).json()["items"]
    assert [t["id"] for t in turns if t["request_id"] == "stream-create"] == [
        turn["id"]
    ]


def test_status_never_carries_model_text_or_claims_a_save(case: Case) -> None:
    asset_id = case.asset("Shop vacuum", "vac")
    conversation = case.conversation()
    frames = stream(
        case,
        conversation,
        "stream-refused",
        "Set my shop vacuum filter to HEPA-12.",
        step("read_asset", asset_id=asset_id),
        step(
            "update_asset",
            asset_id=asset_id,
            fields=[field("filter_dimensions", "Saved HEPA 12 inch")],
        ),
        step("answer", message="Saved! Model secret reasoning here."),
    )
    texts = statuses(frames)
    assert set(texts) <= {"Checking your request…", *STATUS.values()}
    assert not any("saved" in t.casefold() for t in texts)
    result = frames[-1]["turn"]["result"]
    assert result["text"].endswith("No changes were saved.")
    assert case.current(asset_id) == {}


def test_stream_cancellation_stops_before_the_write(case: Case) -> None:
    asset_id = case.asset("Kayak", "kayak")
    conversation = case.conversation()

    def cancel(payload: dict[str, Any]) -> dict[str, Any]:
        ChatService(case.engine).cancel(case.actor, "stream-cancel")
        return step("update_asset", asset_id=asset_id, fields=[field("paint", "red")])

    frames = stream(
        case,
        conversation,
        "stream-cancel",
        "My kayak's paint is red.",
        step("search_assets", query="kayak"),
        cancel,
    )
    assert frames[-1]["turn"]["state"] == "canceled"
    assert case.current(asset_id) == {}


def test_stream_still_rejects_other_modes(case: Case) -> None:
    conversation = case.conversation()
    for mode in ("save", "organize", "extract"):
        response = case.client.post(
            f"/api/chat/conversations/{conversation}/stream",
            headers=case.headers,
            json={"request_id": f"r-{mode}", "mode": mode, "text": "Note"},
        )
        assert response.status_code == 422, mode
