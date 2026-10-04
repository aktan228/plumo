"""Read-side metrics. Numbers come from the database, not from the model."""

from app.domain.models import MetricsSnapshot
from app.domain.ports import MetricsStore


class MetricsService:
    def __init__(self, metrics: MetricsStore) -> None:
        self.metrics = metrics

    async def snapshot(self) -> MetricsSnapshot:
        return await self.metrics.collect()
