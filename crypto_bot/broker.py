"""Ekzekutimi i urdhrave: simulim (paper) ose real në platformë, me gjendje të ruajtur në disk."""
import json
import os
import time
from pathlib import Path

from .strategy import exit_prices, position_cost


class Broker:
    """Mban kapitalin dhe pozicionet. Me `exchange` të dhënë, urdhrat dërgohen realisht."""

    def __init__(self, cfg, exchange=None):
        self.cfg, self.exchange = cfg, exchange
        self.live = exchange is not None
        self.path = Path(cfg.state_file)
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            if self.state.get("team"):
                raise RuntimeError(f"{self.path} është përmbledhja e ekipit; përdor një state_file tjetër ose nise me --ekip.")
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

    @staticmethod
    def value(pos: dict, price: float) -> float:
        """Vlera e një pozicioni: long = sasia × çmimi; short = marzhi + fitimi nga rënia e çmimit."""
        return pos["qty"] * (price if pos.get("side", 1) > 0 else 2 * pos["entry"] - price)

    def equity(self, prices: dict) -> float:
        return self.cash() + sum(self.value(p, prices.get(s, p["entry"])) for s, p in self.positions.items())

    def buy(self, symbol: str, price: float, equity: float, stop_pct: float = None, side: int = 1,
            stop_price: float = None, take_price: float = None):
        """Hap një pozicion sipas rrezikut të lejuar. Kthen pozicionin ose None nëse s'ka fonde.

        `stop_pct` është largësia e stop-loss nga hyrja në % (parazgjedhur stop_loss_pct).
        `side`: 1 = blerje (long), −1 = shitje short (fitim kur çmimi bie).
        `stop_price` / `take_price`: nivele të sakta nga sinjali (zëvendësojnë përqindjet).
        """
        cfg, fee = self.cfg, self.cfg.fee_pct / 100
        stop_pct = stop_pct or cfg.stop_loss_pct
        levels = exit_prices(cfg, price, stop_pct, side)
        if stop_price:
            levels = (stop_price, take_price)
            stop_pct = abs(price - stop_price) / price * 100
        cost = min(position_cost(cfg, equity, stop_pct), self.cash())
        if cost <= 0 or symbol in self.positions:
            return None
        server_stop = getattr(self.exchange, "stop_on_order", False)
        if self.live:
            if side < 0 and not server_stop:
                raise RuntimeError("Shitja short me urdhra realë punon vetëm në MT5 (tregu spot nuk e lejon)")
            qty = float(self.exchange.amount_to_precision(symbol, cost * (1 - fee) / price))
            limits = self.exchange.market(symbol).get("limits", {})
            if qty <= 0 or cost < (limits.get("cost", {}).get("min") or 0) or qty < (limits.get("amount", {}).get("min") or 0):
                return None
            # Platformat që e mbështesin (MT5) e vendosin stop-in edhe në server.
            params = {"stopLossPrice": levels[0]} if server_stop else {}
            order = self.exchange.create_order(symbol, "market", "buy" if side > 0 else "sell", qty, None, params)
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
        sl, tp = levels if stop_price else exit_prices(cfg, price, stop_pct, side)
        pos = {"side": side, "qty": qty, "entry": price, "cost": cost, "high": price, "opened": time.time(),
               "sl": sl, "tp": tp}
        self.positions[symbol] = pos
        self.save()
        return pos

    def sell(self, symbol: str, price: float, reason: str) -> dict:
        """Mbyll pozicionin (long ose short) dhe kthen tregtinë e përfunduar."""
        pos, fee = self.positions[symbol], self.cfg.fee_pct / 100
        side = pos.get("side", 1)
        if self.live:
            qty = float(self.exchange.amount_to_precision(symbol, pos["qty"]))
            if getattr(self.exchange, "stop_on_order", False):   # MT5: mbyll pozicionet e robotit në këtë simbol
                order = self.exchange.create_order(symbol, "market", "sell" if side > 0 else "buy", qty, None,
                                                   {"reduceOnly": True})
            else:
                order = self.exchange.create_order(symbol, "market", "sell", qty)
            order = self._settled(order, symbol)
            price = float(order.get("average") or price)
            qty = float(order.get("filled") or qty)
            proceeds = max(self.value({**pos, "qty": qty}, price) - qty * price * fee, 0.0)
        else:
            proceeds = max(self.value(pos, price) - pos["qty"] * price * fee, 0.0)
            self.state["cash"] += proceeds
        trade = {"symbol": symbol, "side": "long" if side > 0 else "short", "entry": pos["entry"], "exit": price,
                 "reason": reason, "pnl": proceeds - pos["cost"], "pnl_pct": (proceeds / pos["cost"] - 1) * 100,
                 "opened": pos.get("opened"), "closed": time.time()}
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
        long = pos.get("side", 1) > 0
        if (price <= pos["sl"]) if long else (price >= pos["sl"]):
            return "stop-loss"
        if pos["tp"] and ((price >= pos["tp"]) if long else (price <= pos["tp"])):
            return "take-profit"
        t = self.cfg.trailing_stop_pct / 100
        if t and ((price > pos["high"]) if long else (price < pos["high"])):
            pos["high"] = price   # çmimi më i mirë i arritur (maja për long, fundi për short)
            pos["sl"] = max(pos["sl"], price * (1 - t)) if long else min(pos["sl"], price * (1 + t))
            self.save()
        return None
