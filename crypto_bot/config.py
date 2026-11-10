"""Konfigurimi i robotit. Çdo vlerë mund të ndryshohet te config.json."""
import json
from dataclasses import dataclass, field, fields
from pathlib import Path

DEFAULT_PATH = Path(__file__).with_name("config.json")


@dataclass
class Config:
    exchange: str = "mexc"             # mexc, binance, bybit (dhe çdo platformë tjetër e ccxt) ose mt5
    testnet: bool = False              # True = rrjeti i testimit i platformës (Binance, Bybit), me para demo
    quote: str = "USDT"                # monedha bazë me të cilën blihet
    symbols: list = field(default_factory=lambda: ["BTC/USDT"])
    scan_market: bool = False          # True = skano gjithë tregun, jo vetëm `symbols`
    scan_top_n: int = 30               # sa monedha (sipas volumit) të skanohen
    timeframe: str = "4h"
    candles: int = 500
    strategy: str = "breakout"         # "breakout" (thyerje maje në trend rritës) ose "score" (pikët e treguesve)
    breakout_entry: int = 55           # bli kur çmimi mbyllet mbi majën e kaq qirinjve të fundit
    breakout_exit: int = 20            # shit kur çmimi mbyllet nën fundin e kaq qirinjve të fundit
    trend_ema: int = 200               # bli vetëm kur çmimi është mbi këtë mesatare (trend rritës)
    daily_trend_ema: int = 50          # bli vetëm kur çmimi ditor është mbi EMA ditore (0 = i fikur)
    take_profit_pct: float = 0.0       # shit me fitim kur çmimi rritet kaq % (0 = i fikur, lër fitimin të rritet)
    stop_loss_pct: float = 8.0         # shit me humbje kur çmimi bie kaq %
    stop_loss_atr: float = 0.0         # nëse > 0: stop = hyrja − kaq × ATR (zëvendëson stop_loss_pct)
    trailing_stop_pct: float = 0.0     # 0 = i fikur; përndryshe stop-i ndjek çmimin më të lartë
    risk_per_trade_pct: float = 1.0    # humbja maksimale për tregti si % e kapitalit (0 = përdor vetëm position_size_pct)
    position_size_pct: float = 25.0    # % maksimale e kapitalit për një blerje
    max_open_positions: int = 3
    max_daily_loss_pct: float = 5.0    # pas kësaj humbjeje brenda ditës nuk hapen blerje të reja (0 = i fikur)
    max_consecutive_losses: int = 3    # pas kaq humbjesh radhazi brenda ditës nuk hapen blerje të reja (0 = i fikur)
    max_spread_pct: float = 0.5        # mos bli kur diferenca blerje/shitje është më e madhe se kaq % (0 = i fikur)
    buy_threshold: float = 35          # pikët minimale (−100..100) për të blerë
    sell_threshold: float = -35        # pikët nën të cilat pozicioni mbyllet
    fee_pct: float = 0.1               # komisioni i platformës për çdo urdhër
    paper_balance: float = 1000.0      # kapitali fillestar në modalitetin simulim
    poll_seconds: int = 60
    state_file: str = "crypto_bot_state.json"
    log_file: str = "crypto_bot_decisions.jsonl"   # çdo vendim me arsyen ("" = pa regjistër)

    def validate(self):
        if self.strategy not in ("breakout", "score"):
            raise ValueError("strategy duhet të jetë 'breakout' ose 'score'")
        if self.take_profit_pct < 0:
            raise ValueError("take_profit_pct duhet të jetë >= 0 (0 = i fikur)")
        if self.breakout_entry < 2 or self.breakout_exit < 2 or self.trend_ema < 2:
            raise ValueError("breakout_entry, breakout_exit dhe trend_ema duhet të jenë >= 2")
        if self.stop_loss_atr < 0 or self.daily_trend_ema < 0 or self.max_consecutive_losses < 0:
            raise ValueError("stop_loss_atr, daily_trend_ema dhe max_consecutive_losses duhet të jenë >= 0")
        if not 0 <= self.risk_per_trade_pct <= 100 or self.max_spread_pct < 0:
            raise ValueError("risk_per_trade_pct duhet të jetë 0–100 dhe max_spread_pct >= 0")
        if not 0 <= self.max_daily_loss_pct < 100:
            raise ValueError("max_daily_loss_pct duhet të jetë midis 0 dhe 100")
        if not 0 < self.stop_loss_pct < 100:
            raise ValueError("stop_loss_pct duhet të jetë midis 0 dhe 100")
        if not 0 <= self.trailing_stop_pct < 100:
            raise ValueError("trailing_stop_pct duhet të jetë midis 0 dhe 100")
        if not 0 < self.position_size_pct <= 100:
            raise ValueError("position_size_pct duhet të jetë midis 0 dhe 100")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions duhet të jetë >= 1")
        return self


def load_config(path=None, **overrides) -> Config:
    """Lexon config.json dhe zbaton ndryshimet e dhëna (p.sh. nga rreshti i komandës)."""
    path = Path(path) if path else DEFAULT_PATH
    data = json.loads(path.read_text()) if path.exists() else {}
    known = {f.name for f in fields(Config)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"Çelësa të panjohur në {path}: {sorted(unknown)}")
    data.update({k: v for k, v in overrides.items() if v is not None})
    return Config(**data).validate()
