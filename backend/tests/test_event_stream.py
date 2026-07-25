from __future__ import annotations

import asyncio
import unittest

from stock_strategy.event_stream import EventBroker


class EventBrokerTest(unittest.IsolatedAsyncioTestCase):
    async def test_stream_delivers_named_json_events_after_ready_signal(self):
        broker = EventBroker(queue_size=2)

        async def connected() -> bool:
            return False

        stream = broker.stream(connected)
        ready = await anext(stream)
        broker.publish("job.updated", {"id": "job-1", "status": "running"})
        update = await asyncio.wait_for(anext(stream), timeout=1)
        await stream.aclose()

        self.assertIn("event: stream.ready", ready)
        self.assertIn("retry: 3000", ready)
        self.assertIn("event: job.updated", update)
        self.assertIn('"id":"job-1"', update)
        self.assertIn('"status":"running"', update)


if __name__ == "__main__":
    unittest.main()
