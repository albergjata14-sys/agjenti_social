# Smart Albania – Qendra e Agjentëve AI

Aplikacion Streamlit (`streamlit run app.py`) me agjentët e Smart Albania dhe **robotin e kriptove**.

## 📈 Roboti i kriptove (`crypto_bot/`)

Analizon grafikun e Bitcoin-it (ose të çdo monedhe), jep sinjal dhe parashikim të detajuar, skanon
gjithë tregun e platformës dhe mund të blejë/shesë vetë me fitim dhe humbje të vendosur në përqindje.

> ⚠️ Nuk është këshillë financiare. Asnjë robot nuk e parashikon tregun me siguri – parashikimi është
> vlerësim statistikor. Nis gjithmonë në simulim dhe rrezikoni vetëm para që përballoni t'i humbni.

### Aplikacioni

Në Windows: dopio-klik te `start_robot.bat`. Hapet në shfletues te `http://localhost:8510`
(herën e parë instalon vetë libraritë). Në sisteme të tjera: `streamlit run crypto_app.py`.

- **Grafiku dhe pikat e hyrjes** – qirinjtë me nivelet e planit (blerje mbi, stop-loss, dalje nga trendi)
  dhe një portofol demo më vete për provat e tua me dorë.
- **Skanimi i tregut** – monedhat më të tregtuara, të renditura sipas afërsisë me sinjalin e blerjes.
- **Roboti (demo)** – butonat Nis / Ndalo, kapitali, pozicionet, tregtitë dhe vendimet e fundit.
- **Ditari i parashikimeve** dhe **Prova në të kaluarën**.

Roboti i nisur nga paneli vazhdon të punojë edhe kur mbyllet faqja; ndalet me butonin Ndalo.

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
python -m crypto_bot analizo --exchange binance   # e njëjta gjë në platformë tjetër: mexc, binance, bybit, mt5
```

E njëjta analizë, skanim dhe backtest gjenden edhe te paneli **Crypto Trading Agent** në `app.py`.

### Programimi i fitimit dhe humbjes (`crypto_bot/config.json`)

| Çelësi | Kuptimi |
|---|---|
| `strategy` | `breakout` (parazgjedhur) ose `score` – shih më poshtë |
| `breakout_entry` / `breakout_exit` / `trend_ema` | bli mbi majën e 55 qirinjve, shit nën fundin e 20 qirinjve, vetëm mbi EMA200 |
| `daily_trend_ema` | bli vetëm kur çmimi ditor është mbi EMA50 ditore (0 = i fikur) |
| `allow_short` | lejo edhe shitje short (fitim kur çmimi bie); vetëm në MT5 ose në simulim (parazgjedhur `false`) |
| `take_profit_pct` | shit me fitim kur çmimi rritet kaq % (0 = i fikur: fitimi lihet të rritet) |
| `stop_loss_pct` | shit me humbje kur çmimi bie kaq % nën çmimin e blerjes |
| `stop_loss_atr` | nëse > 0, stop-i vendoset kaq × ATR nën hyrjen (sipas luhatshmërisë), në vend të përqindjes |
| `trailing_stop_pct` | stop që ndjek çmimin më të lartë (0 = i fikur) |
| `risk_per_trade_pct` | humbja maksimale për tregti si % e kapitalit; madhësia e blerjes llogaritet nga largësia e stop-it (0 = i fikur) |
| `position_size_pct` | % maksimale e kapitalit për një blerje |
| `max_open_positions` | sa monedha mund të mbahen njëkohësisht |
| `max_daily_loss_pct` | pas kësaj humbjeje brenda ditës (UTC) nuk hapen blerje të reja (0 = i fikur) |
| `max_consecutive_losses` | pas kaq humbjesh radhazi brenda ditës nuk hapen blerje të reja (0 = i fikur) |
| `max_spread_pct` | mos bli kur diferenca mes çmimit të blerjes dhe shitjes e kalon këtë % (0 = i fikur) |
| `testnet` | `true` = rrjeti i testimit i platformës me para demo (Binance, Bybit) |
| `buy_threshold` / `sell_threshold` | vetëm për `score`: pikët (−100..100) për blerje / shitje |
| `exchange` | `mexc` (parazgjedhur), `binance`, `bybit`, `mt5`, ose çdo platformë tjetër e [ccxt](https://github.com/ccxt/ccxt) |
| `symbols`, `scan_market`, `scan_top_n` | lista e monedhave, ose skanim i N monedhave më të tregtuara |
| `timeframe`, `candles`, `poll_seconds` | intervali i qirinjve (parazgjedhur `4h`), historia, sa shpesh kontrollon |
| `fee_pct`, `paper_balance` | komisioni i platformës, kapitali virtual i simulimit |
| `state_file`, `log_file` | ku ruhen gjendja dhe regjistri i vendimeve |

### Si vendos roboti

**`breakout` (parazgjedhur)** – ndjekje trendi: blen kur një qiri mbyllet mbi majën e 55 qirinjve të
mëparshëm, çmimi është mbi EMA200 dhe trendi ditor është rritës (mbi EMA50 ditore); shet kur çmimi mbyllet nën fundin e 20 qirinjve, ose kur preket
stop-loss. Nuk ka kufi fitimi, sepse prerja e fitimeve herët e dobësoi rezultatin në prova.

**`score`** – pikë nga −100 në +100 nga pesë tregues (trendi EMA 35%, MACD 25%, RSI 20%, Bollinger 10%,
volumi 10%); blen mbi `buy_threshold`, shet nën `sell_threshold`. Pikët shfaqen gjithmonë në raport si
informacion, edhe kur strategjia është `breakout`.

Raporti jep edhe mbështetjen/rezistencën, brezin e pritshëm të çmimit (sipas luhatshmërisë ATR) dhe
planin hyrje / fitim / stop. Roboti tregton pa levë.

**Shitja short** (`--short` ose `"allow_short": true`) është pasqyra e blerjes: hap short kur çmimi
mbyllet nën fundin e 55 qirinjve, nën EMA200 dhe me trend ditor rënës; e mbyll kur çmimi mbyllet mbi
majën e 20 qirinjve ose kur preket stop-loss (që është sipër hyrjes). Punon në simulim në çdo platformë
dhe me urdhra në MT5; tregu spot i MEXC, Binance dhe Bybit nuk e lejon me urdhra realë.

### Çfarë treguan provat (MEXC, nëntor 2026)

8 monedha (BTC, ETH, SOL, XRP, BNB, DOGE, ADA, LINK), qirinj 4-orësh, korrik 2024 – nëntor 2026,
komision 0.1%:

| | Mesatarja | Me fitim | Rënia maks. mesatare |
|---|---|---|---|
| `breakout` me filtër ditor, 100% në një monedhë | +70.1% | 6 nga 8 | 37% |
| `breakout` pa filtër ditor, 100% në një monedhë | +40.8% | 7 nga 8 | 45% |
| `breakout` me parazgjedhjet (rrezik 1% për tregti) | +9.5% | 7 nga 8 | 7% |
| `score` (fitim 4% / humbje 2%), 100% në një monedhë | −6.2% | 4 nga 8 | 43% |
| Mbajtja pa tregtuar | +3.3% | | |

- Në periudha rënieje `breakout` prapë humbi (−3% deri −8% për periudhë), por shumë më pak se tregu.
- Vetëm rreth 40% e tregtive mbyllen me fitim; fitimi vjen nga pak tregti të mëdha.
- Në qirinj 1-orësh rezultati ishte rreth zeros, prandaj parazgjedhja është `4h`.
- Rezultati i së kaluarës nuk garanton të ardhmen. Zgjedhjet u bënë mbi të njëjtat të dhëna, ndaj
  prit rezultat më të dobët në të ardhmen.

Shitja short në të njëjtat të dhëna (100% në një monedhë): vetëm short −29%, blerje + short +22%
kundrejt +71% vetëm me blerje, dhe rënia maksimale u rrit nga 19% në 30%. Short-i fitoi vetëm në
periudhën më të fortë të rënies. Prandaj është i fikur si parazgjedhje.

Ide të provuara që **nuk** u futën, sepse e dobësuan rezultatin: mbyllja e pjesshme e fitimit
(50% në TP1 + stop në çmimin e hyrjes; 40/40/20) e uli totalin nga rreth +61% në +17–25%; filtri i
vëllimit 1.5× dhe hyrjet në tërheqje (RSI 40–45) nuk ndihmuan. Stop-i me ATR dha rezultat të ngjashëm me
8% fikse dhe mbetet si opsion (`stop_loss_atr`).

Ari i tokenizuar (PAXG) në MEXC: strategjia dha +18–28% kundrejt +66% të mbajtjes, dhe diferenca
blerje/shitje ishte rreth 0.25% (te BTC rreth 0.0003%). Kjo strategji nuk i përshtatet arit.

### Platformat

| Platforma | `exchange` | Simbolet | Demo |
|---|---|---|---|
| MEXC | `mexc` | `BTC/USDT` | vetëm simulimi i robotit (`nis` pa `--live`) |
| Binance | `binance` | `BTC/USDT` | simulimi, ose rrjeti i testimit: `--testnet --live` me çelësa të testnet-it |
| Bybit | `bybit` | `BTC/USDT` | simulimi, ose rrjeti i testimit: `--testnet --live` me çelësa të testnet-it |
| MetaTrader 5 | `mt5` | `BTCUSD`, `XAUUSD` (emrat e brokerit) | llogari demo e brokerit, e hapur në terminal |

Simulimi i robotit (`python -m crypto_bot nis --exchange ...`) punon njësoj në të katra: çmime reale,
para virtuale, pa çelësa.

**MetaTrader 5** kërkon Windows me terminalin MT5 të hapur dhe të kyçur, plus `pip install MetaTrader5`.
Vendos `"exchange": "mt5"` dhe simbolet me emrat e brokerit (monedha merret nga llogaria). Roboti tregton
pa levë (vlera e pozicionit nuk e kalon marzhin e lirë), dhe stop-loss vendoset edhe në serverin e
brokerit. Në MT5 duhet ndezur butoni Algo Trading. Shembull me urdhra në llogarinë demo:
`python -m crypto_bot nis --live --exchange mt5 --symbol XAUUSD,BTCUSD --short`. Për skanim përdoren simbolet e Market Watch.

Gjendja e verifikimit: MEXC dhe MT5 u provuan me të dhëna reale (analizë dhe backtest). Binance dhe
Bybit u provuan vetëm me teste të simuluara; dërgimi i urdhrave nuk është provuar ende në asnjë platformë. Provoji së pari në simulim,
pastaj në testnet / llogari demo.

### Ditari i parashikimeve

Për të matur sa i saktë është një burim parashikimesh (p.sh. "AI Analysis" i MEXC):

```bash
python -m crypto_bot ditar shto --drejtimi rënie --ore 24 --perqindja 74 --objektivi 73200
python -m crypto_bot ditar        # mbyll parashikimet që u ka ardhur afati dhe shfaq saktësinë
```

Çdo shtim regjistron edhe drejtimin që jep roboti në të njëjtin çast, për krahasim. Me më pak se 30
parashikime të mbyllura, përqindja nuk tregon ende asgjë.

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

Në MEXC, Binance dhe Bybit stop-loss dhe take-profit kontrollohen nga roboti çdo `poll_seconds` –
nuk vendosen si urdhra në platformë, prandaj mbrojnë vetëm kur roboti është ndezur. Në MT5 stop-loss
vendoset edhe në server. Gjendja ruhet te `crypto_bot_state*.json`.

### Testet

```bash
python -m pytest tests
```
