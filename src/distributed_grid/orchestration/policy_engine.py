from __future__ import annotations

from dataclasses import dataclass
from typing import List

from distributed_grid.monitoring.resource_metrics import ResourceSnapshot


@dataclass
class PolicyDecision:
    should_offload: bool
    reasons: List[str]


class PolicyEngine:
    def __init__(
        self,
        cpu_threshold: float,
        memory_threshold: float,
        gpu_threshold: float,
        queue_threshold: int,
    ) -> None:
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.gpu_threshold = gpu_threshold
        self.queue_threshold = queue_threshold

    def evaluate(self, head_snapshot: ResourceSnapshot, queue_depth: int) -> PolicyDecision:
        reasons: List[str] = []
        if head_snapshot.cpu_pressure >= self.cpu_threshold:
            reasons.append("cpu")
        if head_snapshot.memory_pressure >= self.memory_threshold:
            reasons.append("memory")
        if head_snapshot.gpu_pressure >= self.gpu_threshold:
            reasons.append("gpu")
        if queue_depth >= self.queue_threshold:
            reasons.append("queue")
        return PolicyDecision(should_offload=bool(reasons), reasons=reasons)
