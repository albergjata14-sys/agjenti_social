"""Lidhja me MetaTrader 5 (p.sh. BTCUSD, XAUUSD) me të njëjtën ndërfaqe si platformat e ccxt.

Kërkon Windows me terminalin MT5 të hapur dhe të kyçur në llogari (reale ose demo) dhe
`pip install MetaTrader5`. Roboti blen vetëm long dhe pa levë: vlera e pozicionit nuk e kalon
marzhin e lirë. Stop-loss vendoset edhe në serverin e brokerit.
"""
import math
import os
import time

MAGIC = 20261110  # shenja me të cilën roboti njeh pozicionet e veta
TIMEFRAMES = {"1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30", "1h": "H1", "4h": "H4", "1d": "D1", "1w": "W1"}
SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}


class MT5Exchange:
    stop_on_order = True  # create_order pranon params["stopLossPrice"]

    def __init__(self, mt5=None):
        if mt5 is None:
            try:
                import MetaTrader5 as mt5
            except ImportError as e:
                raise RuntimeError("MetaTrader 5 kërkon Windows me terminalin MT5 të instaluar dhe "
                                   "`pip install MetaTrader5`") from e
        self.mt5 = mt5
        kwargs = {}
        if os.environ.get("MT5_LOGIN"):
            kwargs = {"login": int(os.environ["MT5_LOGIN"]), "password": os.environ.get("MT5_PASSWORD", ""),
                      "server": os.environ.get("MT5_SERVER", "")}
        if not mt5.initialize(**kwargs):
            raise RuntimeError(f"Nuk u lidh dot me terminalin MT5: {mt5.last_error()}")

    # --- të dhënat e tregut -------------------------------------------------
    def parse_timeframe(self, timeframe: str) -> int:
        if timeframe not in SECONDS:
            raise ValueError(f"Intervali '{timeframe}' nuk mbështetet në MT5")
        return SECONDS[timeframe]

    def milliseconds(self) -> int:
        return int(time.time() * 1000)

    def _info(self, symbol: str):
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise ValueError(f"Simboli '{symbol}' nuk gjendet në MT5 (kontrollo emrin te Market Watch)")
        if not info.visible:
            self.mt5.symbol_select(symbol, True)
        return info

    def fetch_closed_candles(self, symbol: str, timeframe: str, limit: int, closed_only: bool = True) -> list:
        """Qirinjtë nga terminali. Pozicioni 1 anashkalon qiririn që është ende i hapur."""
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Intervali '{timeframe}' nuk mbështetet në MT5")
        self._info(symbol)
        tf = getattr(self.mt5, "TIMEFRAME_" + TIMEFRAMES[timeframe])
        rates = self.mt5.copy_rates_from_pos(symbol, tf, 1 if closed_only else 0, limit)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"MT5 nuk ktheu qirinj për {symbol}: {self.mt5.last_error()}")
        return [[int(r["time"]) * 1000, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
                 float(r["tick_volume"])] for r in rates]

    def fetch_ticker(self, symbol: str) -> dict:
        self._info(symbol)
        t = self.mt5.symbol_info_tick(symbol)
        if t is None:
            raise RuntimeError(f"MT5 nuk ka çmim për {symbol}")
        return {"symbol": symbol, "bid": t.bid, "ask": t.ask, "last": t.last or (t.bid + t.ask) / 2}

    def load_markets(self) -> dict:
        """Simbolet e Market Watch (ato që ke zgjedhur në terminal)."""
        out = {}
        for s in self.mt5.symbols_get() or []:
            if s.visible:
                out[s.name] = {"spot": True, "active": True, "base": s.currency_base, "quote": s.currency_profit}
        return out

    def fetch_tickers(self) -> dict:
        # MT5 nuk jep volum 24-orësh të krahasueshëm: të gjitha simbolet trajtohen njësoj.
        return {name: {"quoteVolume": 1.0} for name in self.load_markets()}

    # --- llogaria dhe urdhrat -----------------------------------------------
    def fetch_balance(self) -> dict:
        a = self.mt5.account_info()
        if a is None:
            raise RuntimeError(f"MT5 nuk ktheu llogarinë: {self.mt5.last_error()}")
        return {"free": {a.currency: a.margin_free}, "total": {a.currency: a.equity}}

    def _lots(self, symbol: str, units: float) -> float:
        """Kthen sasinë (njësi të asetit) në lote, të rrumbullakosur poshtë sipas hapit të brokerit."""
        info = self._info(symbol)
        lots = math.floor(units / info.trade_contract_size / info.volume_step + 1e-9) * info.volume_step
        return round(lots, 8) if lots >= info.volume_min else 0.0

    def amount_to_precision(self, symbol: str, amount: float) -> str:
        return repr(self._lots(symbol, amount) * self._info(symbol).trade_contract_size)

    def market(self, symbol: str) -> dict:
        info = self._info(symbol)
        return {"limits": {"amount": {"min": info.volume_min * info.trade_contract_size}, "cost": {"min": 0}}}

    def _filling(self, info):
        m = self.mt5
        if info.filling_mode & 1:
            return m.ORDER_FILLING_FOK
        if info.filling_mode & 2:
            return m.ORDER_FILLING_IOC
        return m.ORDER_FILLING_RETURN

    def create_order(self, symbol, type_, side, amount, price=None, params=None) -> dict:
        m, info = self.mt5, self._info(symbol)
        if type_ != "market":
            raise ValueError("Në MT5 roboti përdor vetëm urdhra market")
        tick = m.symbol_info_tick(symbol)
        request = {"action": m.TRADE_ACTION_DEAL, "symbol": symbol, "deviation": 20, "magic": MAGIC,
                   "comment": "crypto_bot", "type_time": m.ORDER_TIME_GTC, "type_filling": self._filling(info)}
        if side == "buy":
            lots = self._lots(symbol, amount)
            if lots <= 0:
                raise ValueError(f"Sasia për {symbol} është nën minimumin e brokerit")
            request.update(type=m.ORDER_TYPE_BUY, volume=lots, price=tick.ask)
            stop = (params or {}).get("stopLossPrice")
            if stop:
                request["sl"] = round(stop, info.digits)
        else:
            mine = [p for p in (m.positions_get(symbol=symbol) or []) if p.magic == MAGIC]
            if not mine:  # pozicionin e ka mbyllur tashmë stop-i në server
                return {"id": None, "filled": amount, "average": tick.bid, "cost": amount * tick.bid}
            lots = round(sum(p.volume for p in mine), 8)
            results = [self._send({**request, "type": m.ORDER_TYPE_SELL, "volume": p.volume, "price": tick.bid,
                                   "position": p.ticket}) for p in mine]
            avg = sum(r.price * r.volume for r in results) / sum(r.volume for r in results)
            units = lots * info.trade_contract_size
            return {"id": results[-1].order, "filled": units, "average": avg, "cost": units * avg}
        r = self._send(request)
        units = r.volume * info.trade_contract_size
        return {"id": r.order, "filled": units, "average": r.price, "cost": units * r.price}

    def _send(self, request):
        r = self.mt5.order_send(request)
        if r is None or r.retcode != self.mt5.TRADE_RETCODE_DONE:
            detail = f"{r.retcode} {r.comment}" if r is not None else self.mt5.last_error()
            raise RuntimeError(f"MT5 e refuzoi urdhrin për {request['symbol']}: {detail}")
        return r
