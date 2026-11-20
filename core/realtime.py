"""Real-time events via Server-Sent Events (SSE)."""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Dict, Set

logger = logging.getLogger(__name__)


class SSEManager:
    def __init__(self):
        self._queues: Dict[str, Set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, channel: str) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=100)
        self._queues[channel].add(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue):
        self._queues[channel].discard(queue)
        if not self._queues[channel]:
            del self._queues[channel]

    async def broadcast(self, channel: str, event: str, data: dict):
        """Broadcast to all subscribers of a channel."""
        if channel not in self._queues:
            return
        message = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        dead = set()
        for queue in self._queues[channel]:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                dead.add(queue)
        for q in dead:
            self.unsubscribe(channel, q)


# Global instance
sse_manager = SSEManager()

# Channel names
CHANNEL_WATCHED = "watched"
CHANNEL_UPDATES = "updates"
CHANNEL_DOWNLOADS = "downloads"