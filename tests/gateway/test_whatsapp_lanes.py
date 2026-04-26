"""Regression tests for WhatsApp soft-thread lanes.

WhatsApp has a flat chat UI, but users can reply to older messages to fork or
return to a topic. The WhatsApp adapter maps those reply relationships to
synthetic ``source.thread_id`` values so the existing Hermes session-key
machinery isolates each lane without a new core session subsystem.
"""

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from gateway.config import PlatformConfig
from gateway.platforms.base import MessageEvent, MessageType
from gateway.session import build_session_key


@pytest.mark.asyncio
async def test_whatsapp_build_event_maps_quoted_fields_to_reply_context():
    from gateway.platforms.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter(PlatformConfig(enabled=True))
    data = {
        "messageId": "m2",
        "chatId": "123@lid",
        "senderId": "123@lid",
        "senderName": "Seb",
        "chatName": "Seb",
        "isGroup": False,
        "body": "yep",
        "hasMedia": False,
        "mediaUrls": [],
        "quotedMessageId": "q1",
        "quotedText": "the thing you said earlier",
    }

    event = await adapter._build_message_event(data)

    assert event is not None
    assert event.reply_to_message_id == "q1"
    assert event.reply_to_text == "the thing you said earlier"


def test_whatsapp_lane_router_reuses_latest_visible_lane_for_unquoted_messages():
    from gateway.platforms.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter(PlatformConfig(enabled=True, extra={"enable_lanes": True}))
    src = adapter.build_source(chat_id="123@lid", chat_type="dm", user_id="123@lid", user_name="Seb")

    first = MessageEvent(text="start topic", message_type=MessageType.TEXT, source=src, message_id="m1")
    routed_first = adapter._route_event_to_lane(first)
    assert routed_first.source.thread_id

    second = MessageEvent(text="follow up", message_type=MessageType.TEXT, source=src, message_id="m2")
    routed_second = adapter._route_event_to_lane(second)

    assert routed_second.source.thread_id == routed_first.source.thread_id
    assert build_session_key(routed_second.source).endswith(routed_first.source.thread_id)


def test_whatsapp_lane_router_creates_new_lane_for_unknown_quoted_reply():
    from gateway.platforms.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter(PlatformConfig(enabled=True, extra={"enable_lanes": True}))
    src = adapter.build_source(chat_id="123@lid", chat_type="dm", user_id="123@lid", user_name="Seb")
    focused = adapter._route_event_to_lane(
        MessageEvent(text="current topic", message_type=MessageType.TEXT, source=src, message_id="current")
    )

    quoted = MessageEvent(
        text="about that older thing",
        message_type=MessageType.TEXT,
        source=src,
        message_id="m-quoted",
        reply_to_message_id="unknown-old-message",
        reply_to_text="old quoted text",
    )
    routed = adapter._route_event_to_lane(quoted)

    assert routed.source.thread_id != focused.source.thread_id
    assert routed.reply_to_text == "old quoted text"
    assert adapter._whatsapp_message_lanes["unknown-old-message"] == routed.source.thread_id


def test_whatsapp_lane_router_routes_known_quoted_reply_to_original_lane():
    from gateway.platforms.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter(PlatformConfig(enabled=True, extra={"enable_lanes": True}))
    src = adapter.build_source(chat_id="123@lid", chat_type="dm", user_id="123@lid", user_name="Seb")
    lane_a = adapter._route_event_to_lane(
        MessageEvent(text="topic a", message_type=MessageType.TEXT, source=src, message_id="a1")
    ).source.thread_id
    adapter._register_whatsapp_lane_message("assistant-a", lane_a)
    lane_b = adapter._route_event_to_lane(
        MessageEvent(
            text="topic b",
            message_type=MessageType.TEXT,
            source=src,
            message_id="b1",
            reply_to_message_id="unknown-b",
            reply_to_text="seed b",
        )
    ).source.thread_id
    assert lane_b != lane_a

    routed = adapter._route_event_to_lane(
        MessageEvent(
            text="back to a",
            message_type=MessageType.TEXT,
            source=src,
            message_id="a2",
            reply_to_message_id="assistant-a",
            reply_to_text="assistant answer in topic a",
        )
    )

    assert routed.source.thread_id == lane_a


def test_whatsapp_lane_router_preserves_explicit_thread_id_for_internal_events():
    from gateway.platforms.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter(PlatformConfig(enabled=True, extra={"enable_lanes": True}))
    src = adapter.build_source(chat_id="123@lid", chat_type="dm", user_id="123@lid", user_name="Seb")
    lane_a = adapter._route_event_to_lane(
        MessageEvent(text="topic a", message_type=MessageType.TEXT, source=src, message_id="a1")
    ).source.thread_id
    lane_b = adapter._route_event_to_lane(
        MessageEvent(
            text="topic b",
            message_type=MessageType.TEXT,
            source=src,
            message_id="b1",
            reply_to_message_id="unknown-b",
            reply_to_text="seed b",
        )
    ).source.thread_id
    assert lane_b != lane_a

    # Simulates a background-process completion/watch notification whose
    # watcher stored the original lane id. Routing must not silently retarget
    # it to the currently focused lane.
    internal_src = adapter.build_source(
        chat_id="123@lid",
        chat_type="dm",
        user_id="123@lid",
        user_name="Seb",
        thread_id=lane_a,
    )
    routed = adapter._route_event_to_lane(
        MessageEvent(
            text="[SYSTEM: Background process completed]",
            message_type=MessageType.TEXT,
            source=internal_src,
            internal=True,
        )
    )

    assert routed.source.thread_id == lane_a


def test_whatsapp_lane_router_expires_idle_focus_lane_for_unquoted_messages():
    from gateway.platforms.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter(PlatformConfig(enabled=True, extra={"enable_lanes": True, "lane_idle_minutes": 60}))
    src = adapter.build_source(chat_id="123@lid", chat_type="dm", user_id="123@lid", user_name="Seb")
    first = adapter._route_event_to_lane(
        MessageEvent(text="old topic", message_type=MessageType.TEXT, source=src, message_id="old")
    )
    old_lane = first.source.thread_id
    adapter._whatsapp_lanes[old_lane].last_activity_at = time.time() - (61 * 60)

    routed = adapter._route_event_to_lane(
        MessageEvent(text="new after idle", message_type=MessageType.TEXT, source=src, message_id="new")
    )

    assert routed.source.thread_id != old_lane


@pytest.mark.asyncio
async def test_whatsapp_lane_command_lists_active_lanes_without_calling_agent():
    from gateway.platforms.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter(PlatformConfig(enabled=True, extra={"enable_lanes": True}))
    adapter.set_message_handler(AsyncMock(return_value="should not run"))
    adapter.send = AsyncMock(return_value=None)
    src = adapter.build_source(chat_id="123@lid", chat_type="dm", user_id="123@lid", user_name="Seb")
    lane_a = adapter._route_event_to_lane(
        MessageEvent(text="first topic", message_type=MessageType.TEXT, source=src, message_id="a1")
    ).source.thread_id
    lane_b = adapter._route_event_to_lane(
        MessageEvent(
            text="second topic",
            message_type=MessageType.TEXT,
            source=src,
            message_id="b1",
            reply_to_message_id="unknown-b",
            reply_to_text="second seed",
        )
    ).source.thread_id

    await adapter.handle_message(MessageEvent(text="/lanes", message_type=MessageType.COMMAND, source=src, message_id="cmd-list"))

    adapter._message_handler.assert_not_awaited()
    sent = adapter.send.await_args.args[1]
    assert "Active WhatsApp lanes" in sent
    assert "1." in sent and "2." in sent
    assert lane_b in sent
    assert lane_a in sent


@pytest.mark.asyncio
async def test_whatsapp_lane_new_command_moves_focus_without_calling_agent():
    from gateway.platforms.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter(PlatformConfig(enabled=True, extra={"enable_lanes": True}))
    adapter.set_message_handler(AsyncMock(return_value="should not run"))
    adapter.send = AsyncMock(return_value=None)
    src = adapter.build_source(chat_id="123@lid", chat_type="dm", user_id="123@lid", user_name="Seb")
    old_lane = adapter._route_event_to_lane(
        MessageEvent(text="old topic", message_type=MessageType.TEXT, source=src, message_id="old")
    ).source.thread_id

    await adapter.handle_message(MessageEvent(text="/lanes new", message_type=MessageType.COMMAND, source=src, message_id="cmd-new"))
    routed = adapter._route_event_to_lane(
        MessageEvent(text="now on forced new lane", message_type=MessageType.TEXT, source=src, message_id="after-new")
    )

    adapter._message_handler.assert_not_awaited()
    assert routed.source.thread_id != old_lane
    assert "New WhatsApp lane" in adapter.send.await_args.args[1]


@pytest.mark.asyncio
async def test_whatsapp_lane_new_command_with_message_sends_immediate_lane_notice():
    from gateway.platforms.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter(PlatformConfig(enabled=True, extra={"enable_lanes": True}))
    adapter.set_message_handler(AsyncMock(return_value="ok"))
    adapter.send = AsyncMock(return_value=None)
    src = adapter.build_source(chat_id="123@lid", chat_type="dm", user_id="123@lid", user_name="Seb")

    await adapter.handle_message(
        MessageEvent(text="/lanes new side quest", message_type=MessageType.COMMAND, source=src, message_id="cmd-new-msg")
    )

    adapter.send.assert_awaited_once()
    sent = adapter.send.await_args.args[1]
    assert "🧵 New WhatsApp lane" in sent
    assert "side quest" in sent


@pytest.mark.asyncio
async def test_whatsapp_auto_new_lane_sends_immediate_lane_notice_when_reply_starts_side_lane():
    from gateway.platforms.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter(PlatformConfig(enabled=True, extra={"enable_lanes": True}))
    adapter.set_message_handler(AsyncMock(return_value="ok"))
    adapter.send = AsyncMock(return_value=None)
    src = adapter.build_source(chat_id="123@lid", chat_type="dm", user_id="123@lid", user_name="Seb")
    first = adapter._route_event_to_lane(
        MessageEvent(text="active topic", message_type=MessageType.TEXT, source=src, message_id="active-root")
    )

    await adapter.handle_message(
        MessageEvent(
            text="separate side topic",
            message_type=MessageType.TEXT,
            source=src,
            message_id="side-root",
            reply_to_message_id="unknown-side",
            reply_to_text="old side seed",
        )
    )

    adapter.send.assert_awaited_once()
    sent = adapter.send.await_args.args[1]
    assert "🧵 New WhatsApp lane" in sent
    assert "separate side topic" in sent
    assert adapter.send.await_args.kwargs["reply_to"] == "side-root"
    assert adapter.send.await_args.kwargs["metadata"]["thread_id"] != first.source.thread_id


@pytest.mark.asyncio
async def test_whatsapp_lane_number_command_switches_focus_to_listed_lane():
    from gateway.platforms.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter(PlatformConfig(enabled=True, extra={"enable_lanes": True}))
    adapter.set_message_handler(AsyncMock(return_value="should not run"))
    adapter.send = AsyncMock(return_value=None)
    src = adapter.build_source(chat_id="123@lid", chat_type="dm", user_id="123@lid", user_name="Seb")
    lane_a = adapter._route_event_to_lane(
        MessageEvent(text="first topic", message_type=MessageType.TEXT, source=src, message_id="a1")
    ).source.thread_id
    lane_b = adapter._route_event_to_lane(
        MessageEvent(
            text="second topic",
            message_type=MessageType.TEXT,
            source=src,
            message_id="b1",
            reply_to_message_id="unknown-b",
            reply_to_text="second seed",
        )
    ).source.thread_id
    assert lane_b != lane_a

    await adapter.handle_message(MessageEvent(text="/lanes 2", message_type=MessageType.COMMAND, source=src, message_id="cmd-switch"))
    routed = adapter._route_event_to_lane(
        MessageEvent(text="back on selected lane", message_type=MessageType.TEXT, source=src, message_id="after-switch")
    )

    adapter._message_handler.assert_not_awaited()
    assert routed.source.thread_id == lane_a
    assert "Switched WhatsApp lane" in adapter.send.await_args.args[1]


@pytest.mark.asyncio
async def test_whatsapp_handle_message_routes_different_lane_without_interrupting_active_focus():
    from gateway.platforms.whatsapp import WhatsAppAdapter

    adapter = WhatsAppAdapter(PlatformConfig(enabled=True, extra={"enable_lanes": True}))
    adapter.set_message_handler(AsyncMock(return_value="ok"))
    adapter._send_with_retry = AsyncMock(return_value=None)
    src = adapter.build_source(chat_id="123@lid", chat_type="dm", user_id="123@lid", user_name="Seb")
    active = adapter._route_event_to_lane(
        MessageEvent(text="active topic", message_type=MessageType.TEXT, source=src, message_id="active-root")
    )
    active_key = build_session_key(active.source)
    adapter._active_sessions[active_key] = asyncio.Event()

    side = MessageEvent(
        text="separate side topic",
        message_type=MessageType.TEXT,
        source=src,
        message_id="side-root",
        reply_to_message_id="unknown-side",
        reply_to_text="old side seed",
    )
    await adapter.handle_message(side)

    assert adapter._active_sessions[active_key].is_set() is False
    assert "side-root" in adapter._whatsapp_message_lanes
    assert adapter._whatsapp_message_lanes["side-root"] != active.source.thread_id
