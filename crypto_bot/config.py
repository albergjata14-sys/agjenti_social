"""Konfigurimi i robotit. Çdo vlerë mund të ndryshohet te config.json."""
import json
from dataclasses import dataclass, field, fields
from pathlib import Path

DEFAULT_PATH = Path(__file__).with_name("config.json")


@dataclass
class Config:
    exchange: str = "binance"          # çdo platformë që mbështet ccxt (binance, kraken, bybit, okx...)
    quote: str = "USDT"                # monedha bazë me të cilën blihet
    symbols: list = field(default_factory=lambda: ["BTC/USDT"])
    scan_market: bool = False          # True = skano gjithë tregun, jo vetëm `symbols`
    scan_top_n: int = 30               # sa monedha (sipas volumit) të skanohen
    timeframe: str = "1h"
    candles: int = 500
    take_profit_pct: float = 4.0       # shit me fitim kur çmimi rritet kaq %
    stop_loss_pct: float = 2.0         # shit me humbje kur çmimi bie kaq %
    trailing_stop_pct: float = 0.0     # 0 = i fikur; përndryshe stop-i ndjek çmimin më të lartë
    position_size_pct: float = 10.0    # % e kapitalit për çdo blerje
    max_open_positions: int = 3
    buy_threshold: float = 35          # pikët minimale (−100..100) për të blerë
    sell_threshold: float = -35        # pikët nën të cilat pozicioni mbyllet
    fee_pct: float = 0.1               # komisioni i platformës për çdo urdhër
    paper_balance: float = 1000.0      # kapitali fillestar në modalitetin simulim
    poll_seconds: int = 60
    state_file: str = "crypto_bot_state.json"

    def validate(self):
        if not 0 < self.take_profit_pct:
            raise ValueError("take_profit_pct duhet të jetë > 0")
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
