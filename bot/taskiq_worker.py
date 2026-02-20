from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import RedisAsyncResultBackend, RedisScheduleSource, RedisStreamBroker

from config import REDIS_URL

broker = RedisStreamBroker(
    REDIS_URL,
).with_result_backend(RedisAsyncResultBackend(REDIS_URL))

redis_source = RedisScheduleSource(REDIS_URL)
label_source = LabelScheduleSource(broker)

scheduler = TaskiqScheduler(broker, sources=[redis_source, label_source])

__all__ = ["broker", "redis_source", "scheduler"]
