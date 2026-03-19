from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import numpy as np

from securities_analysis.agents.contracts import Bar, SignalDecision


class StrategyProtocol(Protocol):
    symbol: str
    bars: Sequence[Bar]

    def on_bar(self, bar: Bar) -> SignalDecision | None:
        ...

    def get_strategy_returns(self) -> np.ndarray:
        ...
