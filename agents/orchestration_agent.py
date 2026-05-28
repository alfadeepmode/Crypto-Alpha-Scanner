"""Orchestration Agent - role-based trade task pipeline."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from agents.decision_agent import DecisionAgent
from agents.risk_manager import RiskManager
from agents.future_simulator import FutureSimulator
from models.schemas import AlphaSignal, TradeDecision, TradeExecution
from tools.exchange_executor import ExchangeExecutor


class OrchestrationAgent:
    """Assign each signal to decision, risk, simulation, execution, and audit roles."""

    def __init__(self, config: dict):
        self.config = config
        self.decision_agent = DecisionAgent(config)
        self.risk_manager = RiskManager(config)
        self.future_simulator = FutureSimulator(config)
        self.executor = ExchangeExecutor(config)
        self.log_path = Path(config.get("orchestration", {}).get("log_path", "data/orchestration_log.jsonl"))

    def process_signals(self, signals: list[AlphaSignal]) -> tuple[list[TradeDecision], list[TradeExecution]]:
        if not signals:
            return [], []

        traces = []
        raw_decisions = []
        for signal in signals:
            trace = [self._task("SignalIntake", "accepted", f"{signal.token.symbol} {signal.action}")]
            decision = self.decision_agent.decide(signal)
            trace.append(self._task("DecisionAgent", decision.side, decision.reason))
            raw_decisions.append(decision)
            traces.append(trace)

        risk_decisions = self.risk_manager.approve_batch(raw_decisions)
        for trace, decision in zip(traces, risk_decisions):
            trace.append(self._task("RiskManager", decision.side, decision.reason))

        decisions = self.future_simulator.approve_batch(risk_decisions)
        for trace, decision in zip(traces, decisions):
            trace.append(self._task("FutureSimulator", decision.side, decision.reason))

        executions = []
        for signal, decision, trace in zip(signals, decisions, traces):
            execution = None
            if decision.side != "hold":
                execution = self.executor.execute(decision)
                executions.append(execution)
                trace.append(self._task("ExecutionTool", execution.status, execution.message))
            else:
                trace.append(self._task("ExecutionTool", "skipped", "hold decision"))
            self._write_log(signal, decision, execution, trace)

        return decisions, executions

    def process_signal(self, signal: AlphaSignal) -> tuple[TradeDecision, TradeExecution | None]:
        trace = []
        trace.append(self._task("SignalIntake", "accepted", f"{signal.token.symbol} {signal.action}"))

        decision = self.decision_agent.decide(signal)
        trace.append(self._task("DecisionAgent", decision.side, decision.reason))

        decision = self.risk_manager.approve_batch([decision])[0]
        trace.append(self._task("RiskManager", decision.side, decision.reason))

        decision = self.future_simulator.approve_batch([decision])[0]
        trace.append(self._task("FutureSimulator", decision.side, decision.reason))

        execution = None
        if decision.side != "hold":
            execution = self.executor.execute(decision)
            trace.append(self._task("ExecutionTool", execution.status, execution.message))
        else:
            trace.append(self._task("ExecutionTool", "skipped", "hold decision"))

        self._write_log(signal, decision, execution, trace)
        return decision, execution

    def _task(self, role: str, status: str, detail: str) -> dict:
        return {"role": role, "status": status, "detail": detail, "at": datetime.now().isoformat()}

    def _write_log(self, signal: AlphaSignal, decision: TradeDecision, execution: TradeExecution | None, trace: list[dict]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "at": datetime.now().isoformat(),
            "symbol": signal.token.symbol,
            "signal_action": signal.action,
            "decision": decision.side,
            "amount_usd": decision.amount_usd,
            "execution_status": execution.status if execution else "skipped",
            "execution_mode": execution.mode if execution else "none",
            "trace": trace,
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
