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
python -m crypto_bot backtest --fitim 5 --humbje 2 --candles 3000   # provo strategjinë në të kaluarën
python -m crypto_bot nis                          # roboti punon vetë, në SIMULIM (para virtuale)
python -m crypto_bot nis --gjithe-tregun          # njësoj, por zgjedh nga gjithë tregu
python -m crypto_bot nis --live                   # PARA REALE (kërkon konfirmim dhe çelësa API)
```

E njëjta analizë, skanim dhe backtest gjenden edhe te paneli **Crypto Trading Agent** në `app.py`.

### Programimi i fitimit dhe humbjes (`crypto_bot/config.json`)

| Çelësi | Kuptimi |
|---|---|
| `take_profit_pct` | shit me fitim kur çmimi rritet kaq % mbi çmimin e blerjes |
| `stop_loss_pct` | shit me humbje kur çmimi bie kaq % nën çmimin e blerjes |
| `trailing_stop_pct` | stop që ndjek çmimin më të lartë (0 = i fikur) |
| `position_size_pct` | sa % e kapitalit përdoret për çdo blerje |
| `max_open_positions` | sa monedha mund të mbahen njëkohësisht |
| `buy_threshold` / `sell_threshold` | pikët (−100..100) që japin sinjal blerjeje / shitjeje |
| `exchange` | platforma (parazgjedhur `mexc`): `binance`, `kraken`, `bybit`, `okx`… (çdo platformë e [ccxt](https://github.com/ccxt/ccxt)) |
| `symbols`, `scan_market`, `scan_top_n` | lista e monedhave, ose skanim i N monedhave më të tregtuara |
| `timeframe`, `candles`, `poll_seconds` | intervali i qirinjve, historia, sa shpesh kontrollon |
| `fee_pct`, `paper_balance` | komisioni i platformës, kapitali virtual i simulimit |

### Si vendos roboti

Çdo qiri merr pikë nga −100 në +100 nga pesë komponentë: trendi (EMA 20/50/200, 35%), momentumi
(MACD, 25%), RSI (20%), brezat Bollinger (10%) dhe volumi (10%). Pikët ≥ `buy_threshold` → **BLI**,
≤ `sell_threshold` → **SHIT**, përndryshe **PRIT**. Raporti jep edhe mbështetjen/rezistencën, brezin
e pritshëm të çmimit (sipas luhatshmërisë ATR) dhe planin hyrje / fitim / stop.

Roboti tregton vetëm spot (blen dhe shet, pa levë dhe pa short).

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
