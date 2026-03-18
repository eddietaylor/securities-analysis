from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from securities_analysis.backtest.engine import StrategyBacktester
from securities_analysis.agents.contracts import Bar, MarketEvent
from securities_analysis.execution.alpaca import AlpacaTrader
from securities_analysis.risk.policy import RiskDecision, RiskPolicy
from securities_analysis.strategies.trend_following import TimeSeriesMomentumStrategy


@dataclass(slots=True)
class MvpExecutionService:
    trader: AlpacaTrader
    strategy: TimeSeriesMomentumStrategy
    risk_policy: RiskPolicy
    symbol: str
    asset_class: str
    interval_seconds: int
    dry_run: bool = True
    latest_quote: MarketEvent | None = None
    session_start_equity: float | None = None
    last_decision_time: datetime | None = None
    last_intended_signed_quantity: float | None = None
    time_in_force: str = "day"
    warmup_start: str | None = None
    warmup_end: str | None = None
    warmup_freq: str = "minute"

    def run(self) -> None:
        self._initialize_session()
        self._warmup_from_history()
        self.trader.stream_quotes(
            ticker=self.symbol,
            asset_class=self.asset_class,
            interval_seconds=self.interval_seconds,
            on_quote=self._handle_quote,
            on_bar=self._handle_bar,
        )

    def _initialize_session(self) -> None:
        account = self.trader.get_account_details()
        self.session_start_equity = float(account.equity)
        print(
            "MVP execution started | "
            f"symbol={self.symbol} "
            f"asset_class={self.asset_class} "
            f"equity={account.equity} "
            f"buying_power={account.buying_power} "
            f"dry_run={self.dry_run}"
        )

    def _warmup_from_history(self) -> None:
        if not self.warmup_start or not self.warmup_end:
            return
        backtester = StrategyBacktester(
            strategy=self.strategy,
            risk_policy=self.risk_policy,
            initial_equity=self.session_start_equity or 100_000.0,
        )
        bars = self.trader.get_historical_bar_objects(
            ticker=self.symbol,
            start=self.warmup_start,
            end=self.warmup_end,
            freq=self.warmup_freq,
            asset_class=self.asset_class,
        )
        warmed = backtester.warmup(bars)
        print(
            "MVP warmup loaded | "
            f"symbol={self.symbol} "
            f"bars={warmed} "
            f"start={self.warmup_start} "
            f"end={self.warmup_end}"
        )

    def _handle_quote(self, quote: MarketEvent) -> None:
        self.latest_quote = quote

    def _handle_bar(self, bar: Bar) -> None:
        signal = self.strategy.on_bar(bar)
        if signal is None:
            print(
                f"{bar.symbol} | warming up strategy | "
                f"bars={len(self.strategy.bars)}"
            )
            return

        account = self.trader.get_account_details()
        equity = float(account.equity)
        session_return = self._session_return(equity)
        spread_bps = self._spread_bps()
        price = bar.close_price
        current_quantity = self.trader.get_position_quantity(self.symbol)

        decision = self.risk_policy.evaluate(
            signal=signal,
            equity=equity,
            price=price,
            spread_bps=spread_bps,
            session_return=session_return,
            historical_strategy_returns=self.strategy.get_strategy_returns(),
        )

        self._print_decision(bar, signal, decision, current_quantity)

        if decision.flatten_position:
            self._flatten_position(current_quantity, signal)
            return

        if not decision.approved:
            return

        desired_quantity = decision.desired_quantity
        desired_signed_quantity = desired_quantity * (1.0 if signal.target_position >= 0 else -1.0)
        quantity_delta = desired_signed_quantity - current_quantity
        if abs(quantity_delta) <= 1e-8:
            self.last_intended_signed_quantity = desired_signed_quantity
            return

        if (
            self.last_intended_signed_quantity is not None
            and abs(self.last_intended_signed_quantity - desired_signed_quantity) <= 1e-8
        ):
            print(
                "ORDER SKIPPED | duplicate desired exposure pending | "
                f"desired_qty={desired_signed_quantity:.6f}"
            )
            return

        intent = self.risk_policy.build_order_intent(
            signal=signal,
            desired_quantity_delta=quantity_delta,
            time_in_force=self.time_in_force_for_asset(),
        )
        if intent is None:
            return

        if self.dry_run:
            self.last_intended_signed_quantity = desired_signed_quantity
            print(
                "DRY RUN ORDER | "
                f"side={intent.side.value} "
                f"qty={intent.quantity:.6f} "
                f"symbol={intent.symbol}"
            )
            return

        order = self.trader.submit_order_intent(intent)
        self.last_intended_signed_quantity = desired_signed_quantity
        print(
            "ORDER SUBMITTED | "
            f"id={order.id} "
            f"status={order.status} "
            f"side={order.side} "
            f"qty={getattr(order, 'qty', None)}"
        )

    def _flatten_position(self, current_quantity: float, signal) -> None:
        if abs(current_quantity) <= 1e-8:
            self.last_intended_signed_quantity = 0.0
            return

        side = "sell" if current_quantity > 0 else "buy"
        quantity = abs(current_quantity)
        if self.dry_run:
            self.last_intended_signed_quantity = 0.0
            print(f"DRY RUN FLATTEN | side={side} qty={quantity:.6f} symbol={self.symbol}")
            return

        order = self.trader.create_order(
            ticker=self.symbol,
            units=quantity,
            order_type="market",
            side=side,
            time_in_force=self.time_in_force_for_asset(),
        )
        self.last_intended_signed_quantity = 0.0
        print(f"FLATTEN ORDER SUBMITTED | id={order.id} status={order.status}")

    def _session_return(self, current_equity: float) -> float:
        if self.session_start_equity is None or self.session_start_equity <= 0:
            return 0.0
        return current_equity / self.session_start_equity - 1.0

    def _spread_bps(self) -> float | None:
        if self.latest_quote is None:
            return None
        if self.latest_quote.bid_price is None or self.latest_quote.ask_price is None:
            return None
        mid = (self.latest_quote.bid_price + self.latest_quote.ask_price) / 2.0
        if mid <= 0:
            return None
        return (self.latest_quote.ask_price - self.latest_quote.bid_price) / mid * 10000.0

    def _print_decision(self, bar: Bar, signal, decision: RiskDecision, current_quantity: float) -> None:
        report = decision.report
        report_text = "no_report"
        if report is not None:
            report_text = (
                f"sharpe={report.sharpe_ratio:.3f} "
                f"sortino={report.sortino_ratio:.3f} "
                f"mdd={report.max_drawdown:.3%} "
                f"es95={report.expected_shortfall_95:.5f} "
                f"kelly={decision.metadata.get('kelly_fraction', 0.0):.4f}"
            )
        print(
            f"{bar.symbol} | "
            f"close={bar.close_price:.4f} "
            f"target={signal.target_position:.4f} "
            f"current_qty={current_quantity:.6f} "
            f"approved={decision.approved} "
            f"reason={decision.reason} | "
            f"{report_text}"
        )

    def time_in_force_for_asset(self) -> str:
        return "gtc" if self.asset_class == "crypto" else self.time_in_force
