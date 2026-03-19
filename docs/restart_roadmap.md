# Securities Analysis Reboot

## Where The Repo Left Off

The strongest thread in this repo is:

1. strategy research in notebooks
2. Alpaca wrapper development
3. paper-trading order experiments
4. streaming and aggregation experiments

The project did not stall because the broker API was unreachable. It stalled at the transition from notebook prototypes to a durable event-driven trading system.

## Current Best Direction

The best near-term path is to focus on one strategy family:

- intraday momentum / trend following on liquid instruments

Why this path:

- it already exists in the repo's research lineage
- it fits the streaming work you started
- it fits Alpaca paper trading cleanly
- it is easier to operationalize than sentiment-heavy or broad ML-first ideas

## Agent Roles

These are software system roles, not model-specific commitments.

### Market Data Agent

Responsibilities:

- historical data fetches
- live quote / trade / bar stream ingestion
- bar aggregation
- persistence of normalized market events

Outputs:

- `MarketEvent`
- `Bar`

### Strategy Agent

Responsibilities:

- feature generation
- signal generation
- position intent generation

Outputs:

- `SignalDecision`
- `OrderIntent`

### Risk Agent

Responsibilities:

- sizing
- exposure limits
- daily stop rules
- kill switch decisions
- duplicate-order prevention

Outputs:

- approved or rejected `OrderIntent`

### Execution Agent

Responsibilities:

- broker API integration
- order submission
- order status reconciliation
- fill handling
- portfolio state sync

Outputs:

- `OrderRecord`
- `PositionSnapshot`

### Backtest Agent

Responsibilities:

- event-driven simulation
- fee and slippage modeling
- walk-forward validation
- benchmark comparisons

Outputs:

- performance reports
- risk reports

### Ops Agent

Responsibilities:

- config loading
- secrets management
- deployment
- scheduling
- logging and alerting

## Build Order

### Phase 1

- move core logic out of `notebooks/`
- define shared contracts
- standardize config and secrets
- create a paper-trading service entrypoint

### Phase 2

- build market-data ingestion service
- persist bars, orders, fills, and positions
- add strategy-to-risk-to-execution pipeline

### Phase 3

- build event-driven backtester using the same contracts
- add evaluation metrics and walk-forward tests
- add monitoring and deployment automation

## Immediate Priorities

1. remove runtime dependence on local secret files
2. promote the Alpaca wrapper into package code
3. define the message contracts between agents
4. build a paper-trading loop before touching live capital

## Non-Goals For Now

- multiple strategies at once
- alt-data-heavy sentiment trading
- live trading with real money
- fancy cloud architecture before the local service is trustworthy
