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
I njëjti panel gjendet edhe te `app.py`, si zgjedhja "Crypto Trading Agent".

- Lart: çmimet e gjalla të 6 monedhave kryesore dhe zgjedhja e monedhës; mënyra dhe rregullimet në "⚙️".
- **Grafiku** – grafik i gjallë me [TradingView Lightweight Charts™](https://www.tradingview.com/)
  (rifreskim çdo 5 sekonda): zmadhim me rrotën e miut ose me dy gishta, lëvizje duke tërhequr, butonat
  "E gjitha", "Tani" dhe "Zmadho". Tregon vijat Hyrja / Stop-loss / Fitimi (TP), shigjeta për hyrjet dhe
  rrathë për daljet. Poshtë: Bli / Shit short / Mbyll për provat me dorë me para demo.
- Grafiku tregon si parazgjedhje kontratat **Futures (Perpetual)** të MEXC, si në aplikacionin e tyre: maja,
  fundi dhe volumi 24 orë, norma e financimit me numërim mbrapsht, kontratat e hapura, mesataret MA5/10/30/60
  (butoni MA) dhe çmimin **LIVE** çdo sekondë nga lidhja e drejtpërdrejtë e MEXC (`wss://contract.mexc.com/edge`).
  Kur ka sinjal, shfaqet **plani i tregtimit** (zona e hyrjes, stop-loss, objektivi) si kuti në grafik dhe si
  kartë, me butonin "Hap në demo me këtë plan". Kur strategjia e lë fitimin të hapur, objektivi i kartës është
  2 herë rreziku, vetëm orientues. Pranë është "Gjendja e tregut": lëvizja 14-ditore, mesatarja, financimi,
  indeksi i frikës dhe lakmisë ([alternative.me](https://alternative.me/crypto/fear-and-greed-index/)) dhe
  pjesa e blerësve/shitësve në librin e urdhrave.
- **Tregu** – ecuria e 10–30 monedhave: 24 orë, 7 ditë, lëvizja 14-ditore, financimi, gjendja, sinjali i robotit dhe
  "gjasat historike" për 24 orët e ardhshme (shih më poshtë se çfarë janë).
- **Roboti** – Nis / Ndalo, kapitali demo, pozicionet, tregtitë dhe arsyet e vendimeve.
- **Njoftime** – lidhja me Telegram, alarmet e çmimit dhe njoftimet e fundit.
- **Prova** – prova në të kaluarën dhe ditari i parashikimeve.

### Njoftimet

Roboti njofton çdo hyrje e dalje, sinjalet e reja te monedhat e ndjekura, lëvizjet mbi
`alert_move_pct` (5%) dhe alarmet e çmimit që vendos ti. Njoftimet shfaqen në panel dhe, kur lidhet,
vijnë në telefon përmes Telegram-it:

```bash
python -m crypto_bot njoftime lidh                   # një herë: lidh robotin tënd të Telegram-it
python -m crypto_bot njoftime test                   # mesazh provë
python -m crypto_bot njoftime shto --symbol BTC/USDT --mbi 80000   # alarm çmimi
python -m crypto_bot njoftime                        # vetëm njoftime, pa tregtuar
```

Tokeni ruhet te `crypto_bot_telegram.json` (jashtë git-it). Në Streamlit Cloud vendosen te Settings →
Secrets si `TELEGRAM_BOT_TOKEN` dhe `TELEGRAM_CHAT_ID`. Njoftimet automatike dërgohen nga procesi që
punon (`nis` ose `njoftime`); në Streamlit Cloud ai nuk rri ndezur, ndaj atje kontrollohen vetëm alarmet e
çmimit sa kohë është e hapur faqja.

**Gjasat historike** te "Tregu" janë sa herë, në të kaluarën e këtyre monedhave, çmimi ishte më lart pas
24 orësh kur tregu ishte në gjendje të ngjashme. Nuk janë parashikim: në një provë jashtë mostrës
(40 monedha, 2024–2026) e qëlluan drejtimin 51% të herëve, më pak se 53% që do të jepte gjithmonë
"poshtë" në atë periudhë. Për "AI Analysis" të MEXC nuk gjeta asnjë përshkrim të metodës; mund ta
matësh vetë me ditarin e parashikimeve.

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
python -m crypto_bot portofol --candles 5000      # si do të kishte dalë roboti mbi shumë monedha njëherësh
python -m crypto_bot nis                          # roboti punon vetë, në SIMULIM (para virtuale)
python -m crypto_bot nis --gjithe-tregun          # njësoj, por zgjedh nga gjithë tregu
python -m crypto_bot analist                       # analisti: provon 6 strategji dhe miraton ato që fitojnë
python -m crypto_bot nis --ekip                    # analisti + tregtari + turneu (simulim)
python -m crypto_bot nis --aktiv                   # mënyra aktive: lart ose poshtë, gjithë tregu, me këmbim
python -m crypto_bot portofol --aktiv --candles 5000   # prova e mënyrës aktive në të kaluarën
python -m crypto_bot nis --live                   # PARA REALE (kërkon konfirmim dhe çelësa API)
python -m crypto_bot analizo --exchange binance   # e njëjta gjë në platformë tjetër: mexc, binance, bybit, mt5
```

E njëjta analizë, skanim dhe backtest gjenden edhe te paneli **Crypto Trading Agent** në `app.py`.

### Programimi i fitimit dhe humbjes (`crypto_bot/config.json`)

| Çelësi | Kuptimi |
|---|---|
| `strategy` | `breakout` (parazgjedhur), `score` ose `engulf` – shih më poshtë |
| `max_trades_per_day` | numri maksimal i hyrjeve në ditë (0 = pa kufi) |
| `breakout_entry` / `breakout_exit` / `trend_ema` | bli mbi majën e 55 qirinjve, shit nën fundin e 20 qirinjve, vetëm mbi EMA200 |
| `daily_trend_ema` | bli vetëm kur çmimi ditor është mbi EMA50 ditore (0 = i fikur) |
| `allow_short` | lejo edhe shitje short (fitim kur çmimi bie); vetëm në MT5 ose në simulim (parazgjedhur `false`) |
| `take_profit_pct` | shit me fitim kur çmimi rritet kaq % (0 = i fikur: fitimi lihet të rritet) |
| `stop_loss_pct` | shit me humbje kur çmimi bie kaq % nën çmimin e blerjes |
| `stop_loss_atr` | nëse > 0, stop-i vendoset kaq × ATR nën hyrjen (sipas luhatshmërisë), në vend të përqindjes |
| `trailing_stop_pct` | stop që ndjek çmimin më të lartë (0 = i fikur) |
| `risk_per_trade_pct` | humbja maksimale për tregti si % e kapitalit; madhësia e blerjes llogaritet nga largësia e stop-it (0 = i fikur) |
| `position_size_pct` | % maksimale e kapitalit për një blerje |
| `max_open_positions` | sa monedha mund të mbahen njëkohësisht (parazgjedhur 8) |
| `market_filter_symbol` | bli vetëm kur ky treg (parazgjedhur `BTC/USDT`) është mbi mesataren ditore; `""` = i fikur |
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

### Ekipi: analisti + tregtari (`nis --ekip`)

Dy robotë që punojnë bashkë:

- **Analisti** (`python -m crypto_bot analist`) shkarkon historinë e 20 monedhave më të tregtuara dhe provon
  6 strategji: si do të kishin dalë në periudhën më të vjetër ("mësimi") dhe në 120 ditët e fundit
  ("kontrolli"). **Miraton** ato që fituan në të dyja dhe bënë mjaft tregti; kur asnjë nuk e bën,
  rekomandon **pushim**. Rekomandimi ruhet te `crypto_bot_recommendation.json`.
- **Tregtari** (`python -m crypto_bot nis --ekip`) i luan njëkohësisht të gjitha strategjitë e miratuara, secila
  me pjesën e vet të kapitalit demo; ato që nuk miratohen vetëm mbyllin pozicionet që kanë. Rifreskon vetë
  analizën çdo `analyst_hours` (12) orë.
- **Turneu** (pjesë e `--ekip`, hiqet me `--pa-turne`) provon pa ndalur çdo strategji me gjithë kapitalin
  demo, në kohë reale. Analisti nuk miraton më një strategji që po humbet qartë në turne (nën −5% pas 15 tregtive).

Pse miratim dhe jo vetëm "më e mira": në një provë jashtë mostrës (20 monedha, 14 muaj, vendim çdo 60
ditë), kalimi te strategjia që kishte fituar më shumë së fundmi dha +2.6%; luajtja e të gjitha të
miratuarave njëherësh dha +12.7%; të gjitha pa filtër +6.6%. Strategjitë e mira të mbajtura fikse dhanë
+13% deri +17%, por kjo dihet vetëm pas faktit. Ekipi punon vetëm në simulim.

### Mënyra aktive (`--aktiv`, strategjia `momentum`)

Roboti mat lëvizjen e 14 ditëve të fundit për çdo monedhë të skanuar dhe hyn te më të fortat:

- **lart (blerje)** kur lëvizja është mbi +5%, çmimi mbi mesataren 100 dhe BTC në trend ditor rritës;
- **poshtë (short)** kur lëvizja është nën −5%, çmimi nën mesataren 100 dhe BTC në trend ditor rënës;
- **dalje** kur lëvizja e monedhës kthehet në anën tjetër, ose te stop-loss;
- **këmbim**: kur të 8 vendet janë plot dhe një monedhë tjetër lëviz të paktën 10 pikë më fort se
  pozicioni më i dobët, ai mbyllet dhe hapet e reja.

Shitja short punon në simulim dhe në MT5; në tregun spot me urdhra realë roboti bën vetëm blerjet.

Prova mbi 20 monedha (4h, shtator 2024 – nëntor 2026): +72%, rënia maksimale 30%, gjysmat +44% / +20%,
16 muaj me fitim dhe 10 me humbje, 803 tregti. Blerjet dhanë +833 USDT, short-et −207 USDT: short-et
vetë dolën me humbje në çdo variant të provuar, edhe kur hapeshin vetëm me BTC në rënie. Pa rregullin e
drejtimit sipas BTC, gjysma e dytë doli −25%. Variante të tjera të provuara dhe të hedhura poshtë:
lëvizje 3-ditore (−33%), 30-ditore (rreth zeros), dhe 60 kombinime me fitime të vogla (të gjitha me humbje).

### Prova e portofolit dhe çfarë thonë studimet

Roboti nuk tregton një monedhë të vetme: skanon tregun dhe mban disa pozicione njëherësh. Komanda
`portofol` e simulon pikërisht këtë, me kapital të përbashkët. Rezultati mbi 20 monedhat më të
tregtuara të MEXC me histori të plotë (4h, shtator 2024 – nëntor 2026, komision 0.1%):

| Rregullimi | Totali | Rënia maks. | Gjysma 1 / 2 | Muaj me fitim / zero / humbje |
|---|---|---|---|---|
| I kujdesshëm: 8 pozicione, rrezik 0.5%, filtër BTC, 20 monedha | +51% | 17% | +44% / +5% | 9 / 5 / 12 |
| Aktiv: lart/poshtë sipas BTC, me këmbim, 20 monedha | +72% | 30% | +44% / +20% | 16 / 0 / 10 |
| I vjetër: 3 pozicione, rrezik 1%, pa filtër, 30 monedha | +9% | 27% | +12% / −3% | 9 / 0 / 17 |

Tre gjëra dolën të qëndrueshme në të gjitha kombinimet e provuara dhe përputhen me studimet:
më shumë pozicione njëherësh (shpërndarje), blerje vetëm kur BTC është në trend ditor rritës, dhe
kufizim te monedhat më të tregtuara. Renditja sipas momentumit 30-ditor nuk ndihmoi.

Kufizimet: fitimi nuk është i rregullt (pothuajse gjysma e muajve janë me humbje dhe shumica e fitimit
erdhi në tremujorin e parë); mbajtja e thjeshtë e të njëjtave monedha dha më shumë; dhe monedhat janë
zgjedhur sipas volumit të sotëm, pra janë ato që mbijetuan, ndaj shifrat janë optimiste.

Burimet e përdorura:
- Ndjekja e trendit (momentumi në seri kohore) është gjetur në 58 tregje të ndryshme dhe në të dhëna që
  shkojnë 137 vjet mbrapa, por janë prova mbi të kaluarën, jo fitime të realizuara
  ([Moskowitz, Ooi, Pedersen 2012](https://papers.ssrn.com/abstract=2089463);
  [A Century of Evidence on Trend-Following](https://www.TrendFollowing.com/whitepaper/Century_Evidence_Trend_Following.pdf)).
- Te kriptot momentumi në kohë është i dokumentuar dhe kthimi i tregut parashikon javët pasuese, por
  rezultatet janë bruto dhe studime më të reja gjejnë rrëzime të forta
  ([Liu, Tsyvinski, Wu](https://www.nber.org/papers/w25882.pdf);
  [studim i vitit 2025](https://link.springer.com/article/10.1007/s11408-025-00474-9)).
- 74–89% e llogarive të vogla humbasin para në CFD sipas rregullatorit evropian
  ([ESMA](https://www.esma.europa.eu/sites/default/files/library/esma35-43-1135_notice_of_pi_decisions_on_cfds_and_binary_options.pdf)).
- Arbitrazhi i normës së financimit (spot kundrejt kontratave pa afat) jep kthime më të rregullta por
  jo pa rrezik; kërkon tregun e kontratave dhe nuk është ndërtuar në këtë robot
  ([He, Manela et al.](https://arxiv.org/pdf/2212.06888v2)).

### Strategjia `engulf` (eksperimentale)

Rregulla të qarta, pa AI: bias ditor nga engulf-i i fundit ditor, sesioni aziatik 01:00–05:00 ora UK
(GMT/BST automatikisht), marrje (sweep) e fundit/majës së sesionit dhe hyrje me engulf të konfirmuar në
intervalin e hyrjes (15m). Stop-i vendoset përtej swing-ut të marrjes, objektivi te high/low i ditës së
mëparshme ose swing-u ditor pasues. Madhësia del nga rreziku dhe largësia e stop-it.

```bash
python -m crypto_bot backtest --exchange mt5 --symbol EURUSD --strategjia engulf --timeframe 15m --short --candles 30000
```

Për të kufizuar hyrjet vendos `"max_trades_per_day": 2` te `config.json`. Ora e serverit të MT5 njihet
vetë; mund të vendoset me dorë me `data_tz`.

Çfarë është interpretim (rregullat origjinale nuk e përcaktojnë saktë; secila ka parametër `engulf_*`
te `crypto_bot/config.py`): brenda sa qirinjve konfirmohet një engulf, sa zgjat bias-i ditor, si
përkufizohet swing-u ditor, çfarë është "thyerje strukture", hapësira e stop-it, raporti minimal
fitim/rrezik dhe ora e fundit e hyrjeve. Hyrja bëhet në konfirmimin e engulf-it, jo në rikthimin te zona.

Çfarë **nuk** është ndërtuar: hyrja "injection" (varet nga gjykim vizual), përdorimi i zonave engulf
kundërshtare H4/H1 si pengesa, kushti "trendy" për 50% (ka vetëm çelësin `engulf_use_mid`), dhe leva
(roboti tregton pa levë, ndaj me stop të ngushtë rreziku real për tregti del më i vogël se 1%).

Rezultati në prova (15m, janar–nëntor 2026, të dhëna MEXC, me short; R = fitimi pjesëtuar me rrezikun):

| Tregu | Tregti | Fituese | Mesatarja me kosto 0.01% | Mesatarja me komision 0.1% |
|---|---|---|---|---|
| EUR/USDT | 114 | 29% | −0.14R | −2.76R |
| BTC/USDT | 160 | 24% | −0.18R | −0.62R |
| ETH/USDT | 160 | 26% | −0.11R | −0.45R |
| SOL/USDT | 176 | 24% | −0.12R | −0.42R |
| XRP/USDT | 123 | 24% | −0.17R | −0.47R |
| Ari (PAXG) | 166 | 21% | −0.14R | −1.24R |

Humbi në të gjashtë tregjet dhe në të gjitha variantet e provuara (vetëm engulf i fortë, pa vazhdim,
raport minimal 2, me bias neutral). EUR/USDT në MEXC është vetëm një përafrim i EURUSD; prova e duhur
bëhet me të dhënat e brokerit në MT5.

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
