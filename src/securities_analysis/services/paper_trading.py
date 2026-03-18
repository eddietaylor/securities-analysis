from __future__ import annotations

from dataclasses import dataclass

from securities_analysis.agents.contracts import Bar
from securities_analysis.execution.alpaca import AlpacaTrader


@dataclass(slots=True)
class PaperTradingService:
    trader: AlpacaTrader
    symbol: str
    asset_class: str = "equity"
    interval_seconds: int = 60

    def print_account_summary(self) -> None:
        account = self.trader.get_account_details()
        print(
            "Account summary | "
            f"status={account.status} "
            f"equity={account.equity} "
            f"buying_power={account.buying_power}"
        )

    def run_quote_stream(self) -> None:
        self.trader.stream_quotes(
            ticker=self.symbol,
            asset_class=self.asset_class,
            interval_seconds=self.interval_seconds,
            on_bar=self._print_bar,
        )

    @staticmethod
    def _print_bar(bar: Bar) -> None:
        print(
            f"{bar.symbol} | "
            f"{bar.start_time.isoformat()} -> {bar.end_time.isoformat()} | "
            f"O={bar.open_price:.4f} "
            f"H={bar.high_price:.4f} "
            f"L={bar.low_price:.4f} "
            f"C={bar.close_price:.4f}"
        )

