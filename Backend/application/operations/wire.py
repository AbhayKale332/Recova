"""Small wire serializers shared by the recovery event streams."""

from typing import Any

from application.entities import Message


def _ser_msg(message: Message) -> dict[str, Any]:
    """Serialize a persisted message for both batch and interactive SSE."""
    return {
        "id": message.id,
        "channel": message.channel.value,
        "direction": message.direction.value,
        "sender": message.sender.value,
        "body": message.body,
        "status": message.status.value,
        "seq": message.seq,
        "meta": message.meta_json,
        "created_at": message.created_at.isoformat(),
    }
