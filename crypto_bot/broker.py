"""Ekzekutimi i urdhrave: simulim (paper) ose real në platformë, me gjendje të ruajtur në disk."""
import json
import os
import time
from pathlib import Path


class Broker:
    """Mban kapitalin dhe pozicionet. Me `exchange` të dhënë, urdhrat dërgohen realisht."""

    def __init__(self, cfg, exchange=None):
        self.cfg, self.exchange = cfg, exchange
        self.live = exchange is not None
        self.path = Path(cfg.state_file)
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            if self.state.get("live") != self.live:
                raise RuntimeError(f"{self.path} i përket modalitetit tjetër (simulim/real). "
                                   "Përdor një state_file tjetër.")
        else:
            self.state = {"live": self.live, "cash": float(cfg.paper_balance), "positions": {}, "trades": []}

    @property
    def positions(self) -> dict:
        return self.state["positions"]

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2))
        os.replace(tmp, self.path)

    def cash(self) -> float:
        if self.live:
            return float(self.exchange.fetch_balance()["free"].get(self.cfg.quote, 0) or 0)
        return self.state["cash"]

    def equity(self, prices: dict) -> float:
        return self.cash() + sum(p["qty"] * prices.get(s, p["entry"]) for s, p in self.positions.items())

    def buy(self, symbol: str, price: float, equity: float):
        """Blen me `position_size_pct` të kapitalit. Kthen pozicionin ose None nëse s'ka fonde."""
        cfg, fee = self.cfg, self.cfg.fee_pct / 100
        cost = min(equity * cfg.position_size_pct / 100, self.cash())
        if cost <= 0 or symbol in self.positions:
            return None
        if self.live:
            qty = float(self.exchange.amount_to_precision(symbol, cost * (1 - fee) / price))
            limits = self.exchange.market(symbol).get("limits", {})
            if qty <= 0 or cost < (limits.get("cost", {}).get("min") or 0) or qty < (limits.get("amount", {}).get("min") or 0):
                return None
            order = self.exchange.create_order(symbol, "market", "buy", qty)
            order = self._settled(order, symbol)
            qty = float(order.get("filled") or qty)
            price = float(order.get("average") or price)
            cost = float(order.get("cost") or qty * price)
            # Komisioni shpesh mbahet në monedhën e blerë; mos u përpiq të shesësh më shumë se ke.
            fee_info = order.get("fee") or {}
            if fee_info.get("currency") == symbol.split("/")[0]:
                qty -= float(fee_info.get("cost") or 0)
        else:
            qty = cost * (1 - fee) / price
            self.state["cash"] -= cost
        pos = {"qty": qty, "entry": price, "cost": cost, "high": price, "opened": time.time(),
               "sl": price * (1 - cfg.stop_loss_pct / 100),
               "tp": price * (1 + cfg.take_profit_pct / 100) if cfg.take_profit_pct else None}
        self.positions[symbol] = pos
        self.save()
        return pos

    def sell(self, symbol: str, price: float, reason: str) -> dict:
        pos, fee = self.positions[symbol], self.cfg.fee_pct / 100
        if self.live:
            qty = float(self.exchange.amount_to_precision(symbol, pos["qty"]))
            order = self._settled(self.exchange.create_order(symbol, "market", "sell", qty), symbol)
            price = float(order.get("average") or price)
            proceeds = float(order.get("cost") or qty * price) * (1 - fee)
        else:
            proceeds = pos["qty"] * price * (1 - fee)
            self.state["cash"] += proceeds
        trade = {"symbol": symbol, "entry": pos["entry"], "exit": price, "reason": reason,
                 "pnl": proceeds - pos["cost"], "pnl_pct": (proceeds / pos["cost"] - 1) * 100,
                 "closed": time.time()}
        del self.positions[symbol]
        self.state["trades"].append(trade)
        self.save()
        return trade

    def _settled(self, order: dict, symbol: str) -> dict:
        """Disa platforma nuk kthejnë çmimin e ekzekutimit menjëherë; rilexo urdhrin."""
        if order.get("average") and order.get("filled"):
            return order
        try:
            time.sleep(1)
            return self.exchange.fetch_order(order["id"], symbol)
        except Exception:
            return order

    def check_exit(self, symbol: str, price: float):
        """Kthen arsyen e daljes ('stop-loss' / 'take-profit') ose None; përditëson trailing stop."""
        pos = self.positions[symbol]
        if price <= pos["sl"]:
            return "stop-loss"
        if pos["tp"] and price >= pos["tp"]:
            return "take-profit"
        if self.cfg.trailing_stop_pct and price > pos["high"]:
            pos["high"] = price
            pos["sl"] = max(pos["sl"], price * (1 - self.cfg.trailing_stop_pct / 100))
            self.save()
        return None
