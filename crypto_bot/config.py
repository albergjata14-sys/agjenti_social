"""Konfigurimi i robotit. Çdo vlerë mund të ndryshohet te config.json."""
import json
from dataclasses import dataclass, field, fields
from pathlib import Path

DEFAULT_PATH = Path(__file__).with_name("config.json")


@dataclass
class Config:
    exchange: str = "mexc"             # mexc, mexc_futures, binance, bybit (dhe çdo platformë e ccxt) ose mt5
    focus: bool = False                # vetëm tregjet e listës `symbols` (ari, BTC, EURUSD, GBPUSD), pa skanim
    testnet: bool = False              # True = rrjeti i testimit i platformës (Binance, Bybit), me para demo
    quote: str = "USDT"                # monedha bazë me të cilën blihet
    symbols: list = field(default_factory=lambda: ["BTC/USDT"])
    scan_market: bool = False          # True = skano gjithë tregun, jo vetëm `symbols`
    scan_top_n: int = 20               # sa monedha (sipas volumit) të skanohen
    timeframe: str = "4h"
    candles: int = 500
    strategy: str = "breakout"         # "breakout" (thyerje maje), "momentum", "score" ose "engulf"
    # --- strategjia "momentum": hyrje lart ose poshtë sipas forcës së lëvizjes së ditëve të fundit ---
    momentum_days: float = 14.0        # mbi sa ditë matet lëvizja
    momentum_min_pct: float = 5.0      # lëvizja minimale (në %) për të hyrë
    momentum_ema: int = 100            # çmimi duhet të jetë mbi (long) ose nën (short) këtë mesatare
    momentum_daily_filter: bool = False   # momentum: blerje vetëm me trend ditor rritës, short vetëm me rënës
    rotate: bool = True                # kur vendet janë plot, këmbe pozicionin më të dobët me një monedhë më të fortë
    rotate_margin_pct: float = 10.0    # sa më e fortë duhet të jetë monedha e re që të bëhet këmbimi
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
    leverage: float = 1.0              # leva në simulim (marzhi = vlera e pozicionit / leva); 1 = pa levë
    max_total_risk_pct: float = 100.0  # rreziku i përbashkët i pozicioneve të hapura, % e kapitalit (Fokus: 2)
    take_profit_r: float = 0.0         # objektivi si shumëfish i rrezikut (2 = 2× largësia e stop-it); 0 = i fikur
    test_days: int = 120               # sa ditët e fundit përdor analisti si periudhë kontrolli
    recent_days: int = 30              # periudha e shkurtër: si po sillet strategjia në ditët më të fundit
    history_years: float = 3.0         # sa vite histori provon analisti (4h, 1h, 1 ditë; 15 min deri në 1 vit)
    use_mt5_data: bool = True          # merr historinë e XAUUSD/EURUSD/GBPUSD/BTCUSD nga MT5 kur është i hapur
    max_active: int = 4                # sa strategji luan ekipi njëkohësisht (të miratuara + provizore)
    provisional_risk: float = 0.5      # strategjitë provizore tregtojnë me këtë pjesë të rrezikut (0.5 = gjysma)
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
    # --- analisti dhe turneu (shih crypto_bot/analyst.py) ---
    recommendation_file: str = "crypto_bot_recommendation.json"   # rekomandimi i fundit i analistit
    follow_analyst: bool = False       # tregtari përdor strategjinë që rekomandon analisti
    analyst_hours: float = 4.0         # sa shpesh e rifreskon tregtari rekomandimin kur e ndjek analistin
    tournament: bool = False           # prova paralele me para demo e të gjitha strategjive kandidate
    memory_file: str = "crypto_bot_memory.db"   # kujtesa: çdo vendim, tregti, kapital dhe raport ditor ("" = pa)
    lab_hours: float = 24.0            # pa analistin e vazhdueshëm: sa shpesh punon laboratori (0 = i fikur)
    lab_candidates: int = 24           # sa strategji të reja provon laboratori çdo herë
    research: bool = True              # ekipi nis vetë analistin e vazhdueshëm (kërkim pa ndalur)
    research_minutes: float = 10.0     # analisti i vazhdueshëm: sa shpesh provon një grup strategjish të reja
    lab_batch: int = 8                 # sa strategji provon në çdo grup
    research_symbols: int = 30         # sa monedha studion analisti (strategjitë zgjedhin 10, 20 ose 30 prej tyre)
    radar_minutes: float = 10.0        # sa shpesh rifreskohet radari i monedhave në trend
    radar_file: str = "crypto_bot_radar.json"
    research_file: str = "crypto_bot_research.json"   # gjendja e analistit të vazhdueshëm
    tournament_days: float = 30.0      # strategjia e laboratorit që s'ngrihet në ekip brenda kësaj kohe lë vendin
    max_evolved: int = 6               # sa strategji të laboratorit mund të jenë njëkohësisht në turne
    promote_days: float = 14.0         # sa ditë fitimi në turne duhen që një strategji e re të hyjë në ekip
    label: str = ""                    # emri i strategjisë në njoftime dhe regjistër (ekipi / turneu)
    pause_entries: bool = False        # mos hap pozicione të reja (p.sh. kur analisti rekomandon pushim)
    # --- njoftimet (shih crypto_bot/notify.py) ---
    notify_file: str = "crypto_bot_notifications.jsonl"   # regjistri i njoftimeve që shfaq paneli
    alerts_file: str = "crypto_bot_alerts.json"           # alarmet e çmimit të vendosura nga përdoruesi
    notify_telegram: bool = True       # dërgo njoftimet edhe në Telegram kur është lidhur
    notify_trades: bool = True         # njofto çdo hyrje dhe dalje të robotit
    notify_signals: bool = True        # njofto kur një monedhë e ndjekur merr sinjal të ri
    alert_move_pct: float = 5.0        # njofto kur një monedhë lëviz kaq % nga njoftimi i fundit (0 = i fikur)

    def validate(self):
        if self.strategy not in ("breakout", "momentum", "score", "engulf"):
            raise ValueError("strategy duhet të jetë 'breakout', 'momentum', 'score' ose 'engulf'")
        if self.alert_move_pct < 0:
            raise ValueError("alert_move_pct duhet të jetë >= 0")
        if self.momentum_days <= 0 or self.momentum_min_pct < 0 or self.momentum_ema < 2 or self.rotate_margin_pct < 0:
            raise ValueError("rregullimet e momentumit duhet të jenë pozitive")
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
        if self.risk_per_trade_pct > self.max_total_risk_pct:
            raise ValueError("rreziku për tregti nuk mund të jetë më i madh se rreziku i përbashkët max_total_risk_pct")
        if self.leverage < 1 or self.take_profit_r < 0 or self.test_days < 10:
            raise ValueError("leverage >= 1, take_profit_r >= 0 dhe test_days >= 10")
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


# Mënyra aktive: hyn lart kur tregu (BTC) është në ngritje dhe poshtë kur është në rënie, te monedhat me
# lëvizjen më të fortë, dhe këmben pozicionet e dobëta me monedha më të forta. Short vetëm në simulim ose MT5.
ACTIVE = {"strategy": "momentum", "allow_short": True, "timeframe": "4h"}

# Mënyra Fokus: vetëm pesë tregje, me të dhënat e kontratave të MEXC (ari, BTC, EURUSD, GBPUSD).
FOCUS_SYMBOLS = ["XAU/USDT", "BTC/USDT", "BTC/USD", "EUR/USDT", "GBP/USDT"]
DISPLAY = {"XAU/USDT": "XAUUSD", "BTC/USDT": "BTCUSDT", "BTC/USD": "BTCUSD", "EUR/USDT": "EURUSD", "GBP/USDT": "GBPUSD"}
MT5_SYMBOLS = {"XAU/USDT": "XAUUSD", "BTC/USD": "BTCUSD", "BTC/USDT": "BTCUSD", "EUR/USDT": "EURUSD", "GBP/USDT": "GBPUSD"}
FOCUS = {"focus": True, "exchange": "mexc_futures", "symbols": FOCUS_SYMBOLS, "scan_market": False,
         "market_filter_symbol": "", "fee_pct": 0.04, "leverage": 10.0, "risk_per_trade_pct": 0.5,
         "max_total_risk_pct": 2.0, "position_size_pct": 100.0, "max_open_positions": 5, "stop_loss_atr": 2.0,
         "research_symbols": 5, "strategy": "momentum", "allow_short": True, "timeframe": "4h",
         "momentum_min_pct": 1.0, "test_days": 90}


def display(symbol: str) -> str:
    return DISPLAY.get(symbol, symbol)


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
