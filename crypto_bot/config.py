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
    scan_top_n: int = 20               # sa monedha (sipas volumit) të skanohen
    timeframe: str = "4h"
    candles: int = 500
    strategy: str = "breakout"         # "breakout" (thyerje maje), "score" (pikët e treguesve) ose "engulf"
    breakout_entry: int = 55           # bli kur çmimi mbyllet mbi majën e kaq qirinjve të fundit
    breakout_exit: int = 20            # shit kur çmimi mbyllet nën fundin e kaq qirinjve të fundit
    trend_ema: int = 200               # bli vetëm kur çmimi është mbi këtë mesatare (trend rritës)
    daily_trend_ema: int = 50          # bli vetëm kur çmimi ditor është mbi EMA ditore (0 = i fikur)
    allow_short: bool = False          # lejo edhe shitje short (fitim kur çmimi bie); vetëm MT5 ose simulim
    # --- strategjia "engulf" (shih crypto_bot/engulf.py; [I] = interpretim i rregullave) ---
    data_tz: str = "auto"              # ora e të dhënave: "auto" (UTC në bursa, ora e serverit në MT5) ose emër IANA
    session_start_hour: float = 1.0    # fillimi i sesionit aziatik, ora UK
    session_end_hour: float = 5.0      # fundi i sesionit aziatik, ora UK
    engulf_trade_end_hour: float = 20.0   # [I] pas kësaj ore (UK) nuk hapen hyrje të reja
    engulf_max_bars: int = 3           # [I] brenda sa qirinjve duhet konfirmuar një engulf
    engulf_bias_max_days: int = 10     # [I] sa ditë vlen bias-i i një engulf-i ditor
    engulf_bias_until_swing: bool = True   # [I] bias-i mbaron kur çmimi arrin swing-un e jashtëm pasues
    engulf_swing_strength: int = 2     # [I] sa ditë në secilën anë e bëjnë një majë/fund swing ditor
    engulf_swing_lookback_days: int = 60   # [I] sa ditë mbrapa merren swing-et si objektiva
    engulf_sweep_prev_day: bool = True # marrja e low/high të ditës së mëparshme vlen si marrje niveli
    engulf_use_mid: bool = True        # vazhdimi kërkon çmimin në anën e duhur të 50% të sesionit
    engulf_continuation: bool = True   # lejo hyrje vazhdimi pas hyrjes normale
    engulf_require_strong: bool = False    # kërko edhe thyerje strukture (engulf i fortë)
    engulf_structure_bars: int = 10    # [I] thyerje strukture = mbyllje përtej kaq qirinjve të fundit
    engulf_stop_buffer_atr: float = 0.2    # [I] hapësira e stop-it përtej swing-ut, në ATR
    engulf_min_rr: float = 1.0         # [I] raporti minimal fitim/rrezik deri te objektivi (0 = pa kufi)
    engulf_neutral_mode: bool = False  # tregto në të dy drejtimet kur bias-i ditor është i paqartë
    max_trades_per_day: int = 0        # numri maksimal i hyrjeve në ditë (0 = pa kufi; për engulf: 2)
    take_profit_pct: float = 0.0       # shit me fitim kur çmimi rritet kaq % (0 = i fikur, lër fitimin të rritet)
    stop_loss_pct: float = 8.0         # shit me humbje kur çmimi bie kaq %
    stop_loss_atr: float = 0.0         # nëse > 0: stop = hyrja − kaq × ATR (zëvendëson stop_loss_pct)
    trailing_stop_pct: float = 0.0     # 0 = i fikur; përndryshe stop-i ndjek çmimin më të lartë
    risk_per_trade_pct: float = 0.5    # humbja maksimale për tregti si % e kapitalit (0 = përdor vetëm position_size_pct)
    position_size_pct: float = 12.5    # % maksimale e kapitalit për një blerje
    max_open_positions: int = 8
    market_filter_symbol: str = "BTC/USDT"   # bli vetëm kur ky treg është në trend ditor rritës ("" = i fikur)
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
    predictions_file: str = "crypto_bot_predictions.jsonl"   # ditari i parashikimeve (komanda `ditar`)

    def validate(self):
        if self.strategy not in ("breakout", "score", "engulf"):
            raise ValueError("strategy duhet të jetë 'breakout', 'score' ose 'engulf'")
        if not 0 <= self.session_start_hour < self.session_end_hour <= 24:
            raise ValueError("orari i sesionit duhet të jetë 0 <= fillimi < fundi <= 24")
        if self.engulf_max_bars < 1 or self.engulf_swing_strength < 1 or self.engulf_structure_bars < 1:
            raise ValueError("engulf_max_bars, engulf_swing_strength dhe engulf_structure_bars duhet të jenë >= 1")
        if self.max_trades_per_day < 0 or self.engulf_min_rr < 0 or self.engulf_stop_buffer_atr < 0:
            raise ValueError("max_trades_per_day, engulf_min_rr dhe engulf_stop_buffer_atr duhet të jenë >= 0")
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
