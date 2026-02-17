"""Real-time communication domain journeys and actions.

Provides journey templates for:
- Chat and messaging flows
- Real-time notifications
- WebSocket connection management
"""

from venomqa.domains.realtime.journeys.chat import (
    direct_message_flow,
    group_chat_flow,
    message_delivery_flow,
)
from venomqa.domains.realtime.journeys.notifications import (
    notification_delivery_flow,
    notification_preferences_flow,
    push_notification_flow,
)

__all__ = [
    "direct_message_flow",
    "group_chat_flow",
    "message_delivery_flow",
    "push_notification_flow",
    "notification_preferences_flow",
    "notification_delivery_flow",
]

realtime_direct_message_flow = direct_message_flow
realtime_group_chat_flow = group_chat_flow
realtime_message_delivery_flow = message_delivery_flow
realtime_push_notification_flow = push_notification_flow
realtime_notification_preferences_flow = notification_preferences_flow
realtime_notification_delivery_flow = notification_delivery_flow
