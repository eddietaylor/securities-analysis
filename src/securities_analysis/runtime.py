from __future__ import annotations

from dataclasses import asdict, dataclass

from securities_analysis.risk.policy import RiskPolicy
from securities_analysis.strategies import StrategyProtocol, build_strategy


@dataclass(slots=True)
class StrategySpec:
    family: str
    lookback_bars: int
    vol_lookback_bars: int
    target_volatility: float
    max_gross_leverage: float
    allow_short: bool = False
    mean_reversion_entry_zscore: float = 1.0
    mean_reversion_exit_zscore: float = 0.25

    def build(self, symbol: str, periods_per_year: int) -> StrategyProtocol:
        return build_strategy(
            strategy_family=self.family,
            symbol=symbol,
            lookback_bars=self.lookback_bars,
            vol_lookback_bars=self.vol_lookback_bars,
            target_volatility=self.target_volatility,
            max_gross_leverage=self.max_gross_leverage,
            periods_per_year=periods_per_year,
            allow_short=self.allow_short,
            mean_reversion_entry_zscore=self.mean_reversion_entry_zscore,
            mean_reversion_exit_zscore=self.mean_reversion_exit_zscore,
        )

    def describe(self) -> str:
        description = (
            f"family={self.family} "
            f"lookback={self.lookback_bars} "
            f"vol_lookback={self.vol_lookback_bars} "
            f"target_vol={self.target_volatility:.3f} "
            f"max_leverage={self.max_gross_leverage:.3f} "
            f"allow_short={self.allow_short}"
        )
        if self.family == "mean_reversion":
            description += (
                f" entry_z={self.mean_reversion_entry_zscore:.3f} "
                f"exit_z={self.mean_reversion_exit_zscore:.3f}"
            )
        return description

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RiskSpec:
    periods_per_year: int
    max_gross_leverage: float
    max_position_notional_pct: float
    max_trade_notional_pct: float
    max_daily_drawdown_pct: float
    max_spread_bps: float
    fractional_kelly: float
    max_kelly_fraction: float
    allow_short: bool = False

    def build(self) -> RiskPolicy:
        return RiskPolicy(
            periods_per_year=self.periods_per_year,
            max_gross_leverage=self.max_gross_leverage,
            max_position_notional_pct=self.max_position_notional_pct,
            max_trade_notional_pct=self.max_trade_notional_pct,
            max_daily_drawdown_pct=self.max_daily_drawdown_pct,
            max_spread_bps=self.max_spread_bps,
            fractional_kelly=self.fractional_kelly,
            max_kelly_fraction=self.max_kelly_fraction,
            allow_short=self.allow_short,
        )

    def describe(self) -> str:
        return (
            f"max_leverage={self.max_gross_leverage:.3f} "
            f"max_position={self.max_position_notional_pct:.3f} "
            f"max_trade={self.max_trade_notional_pct:.3f} "
            f"max_dd={self.max_daily_drawdown_pct:.3f} "
            f"max_spread_bps={self.max_spread_bps:.2f} "
            f"fractional_kelly={self.fractional_kelly:.3f} "
            f"max_kelly={self.max_kelly_fraction:.3f} "
            f"allow_short={self.allow_short}"
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class TradingRuntimeSpec:
    symbol: str
    asset_class: str
    periods_per_year: int
    strategy: StrategySpec
    risk: RiskSpec

    def describe(self) -> str:
        return (
            f"symbol={self.symbol} "
            f"asset_class={self.asset_class} "
            f"periods_per_year={self.periods_per_year} | "
            f"strategy[{self.strategy.describe()}] | "
            f"risk[{self.risk.describe()}]"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "asset_class": self.asset_class,
            "periods_per_year": self.periods_per_year,
            "strategy": self.strategy.to_dict(),
            "risk": self.risk.to_dict(),
        }


def strategy_spec_from_args(args) -> StrategySpec:
    return StrategySpec(
        family=args.strategy_family,
        lookback_bars=args.lookback_bars,
        vol_lookback_bars=args.vol_lookback_bars,
        target_volatility=args.target_volatility,
        max_gross_leverage=args.max_gross_leverage,
        allow_short=args.allow_short,
        mean_reversion_entry_zscore=args.mean_reversion_entry_zscore,
        mean_reversion_exit_zscore=args.mean_reversion_exit_zscore,
    )


def risk_spec_from_args(args, periods_per_year: int) -> RiskSpec:
    return RiskSpec(
        periods_per_year=periods_per_year,
        max_gross_leverage=args.max_gross_leverage,
        max_position_notional_pct=args.max_position_notional_pct,
        max_trade_notional_pct=args.max_trade_notional_pct,
        max_daily_drawdown_pct=args.max_daily_drawdown_pct,
        max_spread_bps=args.max_spread_bps,
        fractional_kelly=args.fractional_kelly,
        max_kelly_fraction=args.max_kelly_fraction,
        allow_short=args.allow_short,
    )


def runtime_spec_from_args(args, periods_per_year: int) -> TradingRuntimeSpec:
    return TradingRuntimeSpec(
        symbol=args.symbol,
        asset_class=args.asset_class,
        periods_per_year=periods_per_year,
        strategy=strategy_spec_from_args(args),
        risk=risk_spec_from_args(args, periods_per_year),
    )
