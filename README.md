# Smart Albania – Qendra e Agjentëve AI

Aplikacion Streamlit (`streamlit run app.py`) me agjentët e Smart Albania dhe **robotin e kriptove**.

## 📈 Roboti i kriptove (`crypto_bot/`)

Analizon grafikun e Bitcoin-it (ose të çdo monedhe), jep sinjal dhe parashikim të detajuar, skanon
gjithë tregun e platformës dhe mund të blejë/shesë vetë me fitim dhe humbje të vendosur në përqindje.

> ⚠️ Nuk është këshillë financiare. Asnjë robot nuk e parashikon tregun me siguri – parashikimi është
> vlerësim statistikor. Nis gjithmonë në simulim dhe rrezikoni vetëm para që përballoni t'i humbni.

### Instalimi

```bash
pip install -r requirements.txt
```

### Komandat

```bash
python -m crypto_bot analizo                      # analizë + parashikim për BTC/USDT
python -m crypto_bot analizo --symbol ETH/USDT --timeframe 4h
python -m crypto_bot skano                        # rendit monedhat më të tregtuara sipas sinjalit
python -m crypto_bot backtest --candles 5000       # provo strategjinë në të kaluarën
python -m crypto_bot backtest --strategjia score --fitim 4 --humbje 2   # strategjia e vjetër me pikë
python -m crypto_bot nis                          # roboti punon vetë, në SIMULIM (para virtuale)
python -m crypto_bot nis --gjithe-tregun          # njësoj, por zgjedh nga gjithë tregu
python -m crypto_bot nis --live                   # PARA REALE (kërkon konfirmim dhe çelësa API)
```

E njëjta analizë, skanim dhe backtest gjenden edhe te paneli **Crypto Trading Agent** në `app.py`.

### Programimi i fitimit dhe humbjes (`crypto_bot/config.json`)

| Çelësi | Kuptimi |
|---|---|
| `strategy` | `breakout` (parazgjedhur) ose `score` – shih më poshtë |
| `breakout_entry` / `breakout_exit` / `trend_ema` | bli mbi majën e 55 qirinjve, shit nën fundin e 20 qirinjve, vetëm mbi EMA200 |
| `take_profit_pct` | shit me fitim kur çmimi rritet kaq % (0 = i fikur: fitimi lihet të rritet) |
| `stop_loss_pct` | shit me humbje kur çmimi bie kaq % nën çmimin e blerjes |
| `trailing_stop_pct` | stop që ndjek çmimin më të lartë (0 = i fikur) |
| `position_size_pct` | sa % e kapitalit përdoret për çdo blerje |
| `max_open_positions` | sa monedha mund të mbahen njëkohësisht |
| `max_daily_loss_pct` | pas kësaj humbjeje brenda ditës (UTC) nuk hapen blerje të reja (0 = i fikur) |
| `buy_threshold` / `sell_threshold` | vetëm për `score`: pikët (−100..100) për blerje / shitje |
| `exchange` | platforma (parazgjedhur `mexc`): `binance`, `kraken`, `bybit`, `okx`… (çdo platformë e [ccxt](https://github.com/ccxt/ccxt)) |
| `symbols`, `scan_market`, `scan_top_n` | lista e monedhave, ose skanim i N monedhave më të tregtuara |
| `timeframe`, `candles`, `poll_seconds` | intervali i qirinjve (parazgjedhur `4h`), historia, sa shpesh kontrollon |
| `fee_pct`, `paper_balance` | komisioni i platformës, kapitali virtual i simulimit |
| `state_file`, `log_file` | ku ruhen gjendja dhe regjistri i vendimeve |

### Si vendos roboti

**`breakout` (parazgjedhur)** – ndjekje trendi: blen kur një qiri mbyllet mbi majën e 55 qirinjve të
mëparshëm dhe çmimi është mbi EMA200; shet kur çmimi mbyllet nën fundin e 20 qirinjve, ose kur preket
stop-loss. Nuk ka kufi fitimi, sepse prerja e fitimeve herët e dobësoi rezultatin në prova.

**`score`** – pikë nga −100 në +100 nga pesë tregues (trendi EMA 35%, MACD 25%, RSI 20%, Bollinger 10%,
volumi 10%); blen mbi `buy_threshold`, shet nën `sell_threshold`. Pikët shfaqen gjithmonë në raport si
informacion, edhe kur strategjia është `breakout`.

Raporti jep edhe mbështetjen/rezistencën, brezin e pritshëm të çmimit (sipas luhatshmërisë ATR) dhe
planin hyrje / fitim / stop. Roboti tregton vetëm spot (blen dhe shet, pa levë dhe pa short).

### Çfarë treguan provat (MEXC, nëntor 2026)

8 monedha (BTC, ETH, SOL, XRP, BNB, DOGE, ADA, LINK), qirinj 4-orësh, korrik 2024 – nëntor 2026,
100% e kapitalit në një monedhë, komision 0.1%:

| | Mesatarja | Me fitim | Rënia maks. mesatare |
|---|---|---|---|
| `breakout` | +40.8% | 7 nga 8 | 45% |
| `score` (fitim 4% / humbje 2%) | −6.2% | 4 nga 8 | 43% |
| Mbajtja pa tregtuar | +3.3% | | |

- Në periudha rënieje `breakout` prapë humbi (−5% deri −17% për periudhë), por shumë më pak se tregu.
- Vetëm rreth 40% e tregtive mbyllen me fitim; fitimi vjen nga pak tregti të mëdha.
- Në qirinj 1-orësh rezultati ishte rreth zeros, prandaj parazgjedhja është `4h`.
- Rezultati i së kaluarës nuk garanton të ardhmen. Parametrat 55/20 janë vlera klasike, por zgjedhja
  mes strategjive u bë mbi të njëjtat të dhëna, ndaj prit rezultat më të dobët në të ardhmen.

### Regjistri i vendimeve

Çdo blerje, shitje dhe mosblerje shkruhet me arsyen te `crypto_bot_decisions.jsonl` (një rresht JSON
për vendim, një herë për çdo qiri të ri). Rregulli i punës: lëre robotin të bëjë 50–100 tregti në
simulim para se të ndryshosh diçka, dhe ndrysho vetëm një gjë në një kohë.

### Demo dhe tregtimi real në MEXC

Demo-ja brenda aplikacionit MEXC nuk lidhet me API, ndaj prova bëhet me simulimin e robotit:
`python -m crypto_bot nis` përdor çmimet reale të MEXC dhe para virtuale (`paper_balance`).
Për simulimin nuk duhet çelës API.

1. Te MEXC: Profili → API Management → krijo çelës **vetëm me leje Spot Trade – pa leje tërheqjeje**
   (Withdraw), mundësisht i lidhur me adresën IP të kompjuterit ku punon roboti.
2. Vendosi si variabla mjedisi (asnjëherë në kod apo në git):
   `export CRYPTO_API_KEY=...  CRYPTO_API_SECRET=...` (dhe `CRYPTO_API_PASSWORD` nëse platforma e kërkon).
3. `python -m crypto_bot nis --live`

Stop-loss dhe take-profit kontrollohen nga roboti çdo `poll_seconds` – nuk vendosen si urdhra në
platformë, prandaj mbrojnë vetëm kur roboti është ndezur. Gjendja ruhet te `crypto_bot_state*.json`.

### Testet

```bash
python -m pytest tests
```
