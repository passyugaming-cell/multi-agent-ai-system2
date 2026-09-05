import asyncio
import json
import logging
from collections import defaultdict
from typing import Any
import redis.asyncio as aioredis

from app.core.events.bus import EventBusInterface, EventHandler
from app.core.events.schemas import EventSchema
from app.core.events.exceptions import InvalidTenantContextError, EventPublishError

logger = logging.getLogger(__name__)


class RedisEventBus(EventBusInterface):
    """Production-ready durable Redis Streams backend for Event Bus."""

    STREAM_KEY = "event_bus_stream"
    CONSUMER_GROUP = "workflow_engine_group"

    def __init__(self, redis_url: str, consumer_name: str = "worker_1") -> None:
        self._redis_url = redis_url
        self._consumer_name = consumer_name
        self._redis: aioredis.Redis | None = None
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._listening_task: asyncio.Task[None] | None = None
        self._running = False

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def publish(self, event: EventSchema) -> None:
        if not event.tenant_id:
            raise InvalidTenantContextError("Event lacks tenant_id")

        redis_client = await self._get_redis()
        event_dict = event.model_dump(mode="json")
        payload_str = json.dumps(event_dict)

        try:
            await redis_client.xadd(self.STREAM_KEY, {"data": payload_str})
        except Exception as e:
            logger.error("Failed to publish event %s to Redis Stream: %s", event.event_id, e)
            raise EventPublishError(f"Failed to publish event to Redis: {e}") from e

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    async def start(self) -> None:
        redis_client = await self._get_redis()
        try:
            await redis_client.xgroup_create(self.STREAM_KEY, self.CONSUMER_GROUP, id="0", mkstream=True)
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                logger.warning("Error creating consumer group: %s", e)

        self._running = True
        self._listening_task = asyncio.create_task(self._consume_loop())

    async def _consume_loop(self) -> None:
        redis_client = await self._get_redis()
        while self._running:
            try:
                streams = await redis_client.xreadgroup(
                    groupname=self.CONSUMER_GROUP,
                    consumername=self._consumer_name,
                    streams={self.STREAM_KEY: ">"},
                    count=10,
                    block=1000,
                )
                if not streams:
                    continue

                for stream_name, messages in streams:
                    for message_id, message_data in messages:
                        try:
                            raw_data = message_data.get("data")
                            if raw_data:
                                event_dict = json.loads(raw_data)
                                event = EventSchema.model_validate(event_dict)
                                await self._dispatch_event(event)
                            await redis_client.xack(self.STREAM_KEY, self.CONSUMER_GROUP, message_id)
                        except Exception as ex:
                            logger.error("Error processing stream message %s: %s", message_id, ex)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in Redis Stream consume loop: %s", e)
                await asyncio.sleep(1)

    async def _dispatch_event(self, event: EventSchema) -> None:
        handlers = list(self._handlers.get(event.event_type, [])) + list(self._handlers.get("*", []))
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error("Error executing handler for event %s: %s", event.event_id, e, exc_info=True)

    async def stop(self) -> None:
        self._running = False
        if self._listening_task:
            self._listening_task.cancel()
            try:
                await self._listening_task
            except asyncio.CancelledError:
                pass
        if self._redis:
            await self._redis.aclose()
            self._redis = None
