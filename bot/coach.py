"""
Visual coach — Pine Script overlay + local HTML live coach dashboard.

Pine overlay:
  Static template with EMA 20/50/200, Supertrend, RSI panel, ATR stop line,
  buy/sell labels and current bot regime label. Pure read-only chart aid —
  TradingView Pine cannot place broker orders.

Live coach HTML:
  Single static file at KiteBot-Control/KiteBot-Live-Coach.html. Renders a
  local SVG chart plus optional TradingView iframe, and reads its data from a
  sibling file `live-coach.json` when served over HTTP. The latest state is
  also embedded for direct file-open mode. Pure observational.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from bot.logger_config import get_logger

log = get_logger("kite-bot.coach")

CONTROL_DIR        = Path(r"C:\Users\krish\OneDrive\Desktop\KiteBot-Control")
PINE_OVERLAY_PATH  = CONTROL_DIR / "KiteBot-Coach-Overlay.pine"
PINE_STRATEGY_PATH = CONTROL_DIR / "KiteBot-Coach-Strategy.pine"
LIVE_COACH_HTML    = CONTROL_DIR / "KiteBot-Live-Coach.html"
LIVE_COACH_JSON    = CONTROL_DIR / "live-coach.json"


# ── Pine overlay (read-only chart aid; never places orders) ──────────────────
PINE_TEMPLATE = """//@version=5
//
// KiteBot Coach Overlay — visual aid for the operator.
// PAPER-ONLY learning bot. This script does NOT place orders.
// TradingView Pine cannot route to exchanges or brokers from a strategy
// running in a chart. The bot's own paper ledger is the source of truth.
//
indicator("KiteBot Coach Overlay", overlay=true, max_labels_count=500)

// === User-tunable (mirrors bot/strategies/trend_ema_supertrend.py) ===
ema_fast_len   = input.int(20,  "EMA fast")
ema_mid_len    = input.int(50,  "EMA mid")
ema_slow_len   = input.int(200, "EMA slow")
st_period      = input.int(10,  "Supertrend period")
st_mult        = input.float(3.0, "Supertrend mult")
rsi_len        = input.int(14, "RSI length")
atr_len        = input.int(14, "ATR length")
atr_stop_mult  = input.float(2.0, "ATR stop multiple")

// === EMAs ===
ema_fast = ta.ema(close, ema_fast_len)
ema_mid  = ta.ema(close, ema_mid_len)
ema_slow = ta.ema(close, ema_slow_len)

plot(ema_fast, "EMA fast",  color=color.new(color.aqua,   0))
plot(ema_mid,  "EMA mid",   color=color.new(color.orange, 0))
plot(ema_slow, "EMA slow",  color=color.new(color.fuchsia, 0))

// === Supertrend ===
[st_line, st_dir] = ta.supertrend(st_mult, st_period)
plot(st_line, "Supertrend", color=st_dir == -1 ? color.green : color.red, linewidth=2)

// === ATR stop reference line (informational only) ===
atr_val   = ta.atr(atr_len)
atr_stop  = close - atr_stop_mult * atr_val
plot(atr_stop, "ATR stop ref", color=color.new(color.silver, 30), style=plot.style_circles)

// === RSI panel (separate sub-pane) ===
rsi_val = ta.rsi(close, rsi_len)
plot(rsi_val, "RSI", color=color.new(color.yellow, 0), display=display.none)
// Use the built-in RSI indicator for a separate pane; this is a marker.

// === Regime label ===
trend_bull   = ema_fast > ema_mid and ema_mid > ema_slow and st_dir == -1
trend_bear   = ema_fast < ema_mid and ema_mid < ema_slow and st_dir ==  1
range_mode   = not trend_bull and not trend_bear

regime_txt = trend_bull ? "TREND" : trend_bear ? "NO TRADE" : range_mode ? "RANGE" : "BREAKOUT"
regime_col = trend_bull ? color.green : trend_bear ? color.red : color.gray

var label regime_label = na
if barstate.islast
    label.delete(regime_label)
    regime_label := label.new(bar_index, high, "Regime: " + regime_txt,
        style=label.style_label_down, color=regime_col, textcolor=color.white, size=size.normal)

// === Buy-candidate marker (matches trend champion's bias filter) ===
buy_setup = trend_bull and rsi_val >= 50 and rsi_val <= 70
plotshape(buy_setup, "Buy setup", style=shape.triangleup, location=location.belowbar,
          color=color.green, size=size.tiny, text="BUY?")

// === Notice ===
// Note: This overlay is informational only. Orders are managed by the
// kite-bot paper engine, not by TradingView.
"""


# ── HTML live coach (TradingView Lightweight Charts via CDN) ─────────────────
PINE_TEMPLATE = """//@version=5
//
// KiteBot Coach Overlay PRO - visual coach for crypto paper trading.
// PAPER ONLY. This script does not place orders.
// The bot's internal paper ledger remains the source of truth.
//
indicator("KiteBot Coach Overlay PRO", overlay=true, max_labels_count=500,
     max_lines_count=500, max_boxes_count=100)

ema_fast_len  = input.int(20, "EMA fast", minval=2)
ema_mid_len   = input.int(50, "EMA mid", minval=5)
ema_slow_len  = input.int(200, "EMA slow", minval=20)
st_period     = input.int(10, "Supertrend period", minval=2)
st_mult       = input.float(3.0, "Supertrend multiplier", minval=0.5)
rsi_len       = input.int(14, "RSI length", minval=2)
atr_len       = input.int(14, "ATR length", minval=2)
atr_stop_mult = input.float(2.0, "ATR stop multiple", minval=0.25)
tp1_mult      = input.float(1.5, "TP1 ATR multiple", minval=0.25)
tp2_mult      = input.float(3.0, "TP2 ATR multiple", minval=0.5)
pivot_len     = input.int(5, "Trendline pivot length", minval=2, maxval=20)
show_mtf      = input.bool(true, "Show multi-timeframe panel")
show_lines    = input.bool(true, "Draw trendlines and support/resistance")
show_bands    = input.bool(true, "Draw SL/TP bands")
show_patterns = input.bool(true, "Mark triangles and breakouts")

ema_fast = ta.ema(close, ema_fast_len)
ema_mid  = ta.ema(close, ema_mid_len)
ema_slow = ta.ema(close, ema_slow_len)
[st_line, st_dir] = ta.supertrend(st_mult, st_period)
rsi_val = ta.rsi(close, rsi_len)
atr_val = ta.atr(atr_len)

trend_bull = ema_fast > ema_mid and ema_mid > ema_slow and st_dir == -1
trend_bear = ema_fast < ema_mid and ema_mid < ema_slow and st_dir == 1
range_mode = not trend_bull and not trend_bear

plot(ema_fast, "EMA 20", color=color.new(color.aqua, 0))
plot(ema_mid, "EMA 50", color=color.new(color.orange, 0))
plot(ema_slow, "EMA 200", color=color.new(color.fuchsia, 0))
plot(st_line, "Supertrend", color=st_dir == -1 ? color.green : color.red, linewidth=2)

long_stop = close - atr_stop_mult * atr_val
long_tp1  = close + tp1_mult * atr_val
long_tp2  = close + tp2_mult * atr_val

p_stop = plot(show_bands ? long_stop : na, "Long SL", color=color.new(color.red, 0), style=plot.style_linebr)
p_tp1  = plot(show_bands ? long_tp1 : na, "Long TP1", color=color.new(color.green, 10), style=plot.style_linebr)
p_tp2  = plot(show_bands ? long_tp2 : na, "Long TP2", color=color.new(color.green, 0), style=plot.style_linebr)
p_mid  = plot(show_bands ? close : na, "Entry ref", color=color.new(color.white, 70), style=plot.style_linebr)
fill(p_stop, p_mid, color=show_bands ? color.new(color.red, 90) : na, title="Risk zone")
fill(p_mid, p_tp2, color=show_bands ? color.new(color.green, 92) : na, title="Reward zone")

ph = ta.pivothigh(high, pivot_len, pivot_len)
pl = ta.pivotlow(low, pivot_len, pivot_len)

var float last_ph = na
var float prev_ph = na
var int last_ph_bar = na
var int prev_ph_bar = na
var float last_pl = na
var float prev_pl = na
var int last_pl_bar = na
var int prev_pl_bar = na
var line resistance_line = na
var line support_line = na

if not na(ph)
    prev_ph := last_ph
    prev_ph_bar := last_ph_bar
    last_ph := ph
    last_ph_bar := bar_index - pivot_len
    if show_lines and not na(prev_ph)
        line.delete(resistance_line)
        resistance_line := line.new(prev_ph_bar, prev_ph, last_ph_bar, last_ph,
             extend=extend.right, color=color.new(color.red, 15), width=2)

if not na(pl)
    prev_pl := last_pl
    prev_pl_bar := last_pl_bar
    last_pl := pl
    last_pl_bar := bar_index - pivot_len
    if show_lines and not na(prev_pl)
        line.delete(support_line)
        support_line := line.new(prev_pl_bar, prev_pl, last_pl_bar, last_pl,
             extend=extend.right, color=color.new(color.lime, 15), width=2)

plot(show_lines ? last_ph : na, "Resistance pivot", color=color.new(color.red, 65), style=plot.style_circles)
plot(show_lines ? last_pl : na, "Support pivot", color=color.new(color.lime, 65), style=plot.style_circles)

res_now = not na(resistance_line) ? line.get_price(resistance_line, bar_index) : na
sup_now = not na(support_line) ? line.get_price(support_line, bar_index) : na
res_slope = not na(prev_ph) and not na(last_ph) and last_ph_bar != prev_ph_bar ? (last_ph - prev_ph) / (last_ph_bar - prev_ph_bar) : na
sup_slope = not na(prev_pl) and not na(last_pl) and last_pl_bar != prev_pl_bar ? (last_pl - prev_pl) / (last_pl_bar - prev_pl_bar) : na
converging_triangle = show_patterns and not na(res_slope) and not na(sup_slope) and res_slope < 0 and sup_slope > 0

bb_basis = ta.sma(close, 20)
bb_dev = ta.stdev(close, 20)
bb_width = bb_basis != 0 ? (4.0 * bb_dev) / bb_basis : na
squeeze = not na(bb_width) and bb_width < ta.lowest(bb_width, 80) * 1.25

breakout_up = show_patterns and not na(res_now) and ta.crossover(close, res_now)
breakout_down = show_patterns and not na(sup_now) and ta.crossunder(close, sup_now)
buy_setup = trend_bull and rsi_val >= 45 and rsi_val <= 72 and close > ema_fast
triangle_long = converging_triangle and squeeze and breakout_up
triangle_short = converging_triangle and squeeze and breakout_down

plotshape(show_patterns and buy_setup, title="Buy setup", style=shape.triangleup,
     location=location.belowbar, color=color.green, size=size.tiny, text="BUY?")
plotshape(triangle_long, title="Triangle breakout long", style=shape.triangleup,
     location=location.belowbar, color=color.lime, size=size.small, text="TRI")
plotshape(triangle_short, title="Triangle breakdown", style=shape.triangledown,
     location=location.abovebar, color=color.red, size=size.small, text="TRI")
plotshape(show_patterns and breakout_up and not triangle_long, title="Resistance breakout",
     style=shape.arrowup, location=location.belowbar, color=color.new(color.green, 0), size=size.tiny, text="BO")
plotshape(show_patterns and breakout_down and not triangle_short, title="Support breakdown",
     style=shape.arrowdown, location=location.abovebar, color=color.new(color.red, 0), size=size.tiny, text="BD")

f_trend_score() =>
    f = ta.ema(close, ema_fast_len)
    m = ta.ema(close, ema_mid_len)
    s = ta.ema(close, ema_slow_len)
    r = ta.rsi(close, rsi_len)
    f > m and m > s and r > 50 ? 1 : f < m and m < s and r < 50 ? -1 : 0

mtf_5   = request.security(syminfo.tickerid, "5", f_trend_score())
mtf_15  = request.security(syminfo.tickerid, "15", f_trend_score())
mtf_60  = request.security(syminfo.tickerid, "60", f_trend_score())
mtf_240 = request.security(syminfo.tickerid, "240", f_trend_score())
mtf_1d  = request.security(syminfo.tickerid, "D", f_trend_score())

f_txt(x) => x == 1 ? "BULL" : x == -1 ? "BEAR" : "MIXED"
f_col(x) => x == 1 ? color.new(color.green, 0) : x == -1 ? color.new(color.red, 0) : color.new(color.gray, 0)

alignment = mtf_5 + mtf_15 + mtf_60 + mtf_240 + mtf_1d
mtf_bias = alignment >= 3 ? "BULL STACK" : alignment <= -3 ? "BEAR STACK" : "MIXED STACK"
mtf_col = alignment >= 3 ? color.green : alignment <= -3 ? color.red : color.gray

var table mtf_table = table.new(position.top_right, 2, 7, border_width=1)
if show_mtf and barstate.islast
    table.cell(mtf_table, 0, 0, "KiteBot MTF", bgcolor=color.new(color.blue, 0), text_color=color.white)
    table.cell(mtf_table, 1, 0, mtf_bias, bgcolor=mtf_col, text_color=color.white)
    table.cell(mtf_table, 0, 1, "5m")
    table.cell(mtf_table, 1, 1, f_txt(mtf_5), bgcolor=f_col(mtf_5), text_color=color.white)
    table.cell(mtf_table, 0, 2, "15m")
    table.cell(mtf_table, 1, 2, f_txt(mtf_15), bgcolor=f_col(mtf_15), text_color=color.white)
    table.cell(mtf_table, 0, 3, "1h")
    table.cell(mtf_table, 1, 3, f_txt(mtf_60), bgcolor=f_col(mtf_60), text_color=color.white)
    table.cell(mtf_table, 0, 4, "4h")
    table.cell(mtf_table, 1, 4, f_txt(mtf_240), bgcolor=f_col(mtf_240), text_color=color.white)
    table.cell(mtf_table, 0, 5, "1D")
    table.cell(mtf_table, 1, 5, f_txt(mtf_1d), bgcolor=f_col(mtf_1d), text_color=color.white)
    table.cell(mtf_table, 0, 6, "RSI / ATR")
    table.cell(mtf_table, 1, 6, str.tostring(rsi_val, "#.0") + " / " + str.tostring(atr_val, "#.####"))

regime_txt = trend_bull ? "TREND BULL" : trend_bear ? "NO TRADE / BEAR" : range_mode ? "RANGE" : "BREAKOUT"
regime_col = trend_bull ? color.green : trend_bear ? color.red : color.gray

var label regime_label = na
if barstate.islast
    label.delete(regime_label)
    label_text = "Regime: " + regime_txt + "\\nMTF: " + mtf_bias + "\\nSL: " + str.tostring(long_stop, "#.####") + " TP1: " + str.tostring(long_tp1, "#.####") + " TP2: " + str.tostring(long_tp2, "#.####")
    regime_label := label.new(bar_index, high, label_text,
         style=label.style_label_down, color=regime_col, textcolor=color.white, size=size.normal)

// Informational only. Orders are managed by the kite-bot paper engine.
"""

PINE_STRATEGY_TEMPLATE = """//@version=5
//
// KiteBot Coach Strategy - TradingView broker-emulator mirror.
// PAPER/SIMULATION ONLY. This uses TradingView Strategy Tester, not a broker.
//
strategy("KiteBot Coach Strategy PRO", overlay=true, pyramiding=3,
     initial_capital=50000, currency=currency.INR,
     commission_type=strategy.commission.percent, commission_value=0.10,
     slippage=2, max_labels_count=500, max_lines_count=500)

ema_fast_len  = input.int(20, "EMA fast", minval=2)
ema_mid_len   = input.int(50, "EMA mid", minval=5)
ema_slow_len  = input.int(200, "EMA slow", minval=20)
st_period     = input.int(10, "Supertrend period", minval=2)
st_mult       = input.float(3.0, "Supertrend multiplier", minval=0.5)
rsi_len       = input.int(14, "RSI length", minval=2)
atr_len       = input.int(14, "ATR length", minval=2)
atr_stop_mult = input.float(2.0, "ATR stop multiple", minval=0.25)
tp_mult       = input.float(2.0, "Take-profit ATR multiple", minval=0.5)
risk_pct      = input.float(5.0, "Notional % per entry", minval=0.1, maxval=35)

ema_fast = ta.ema(close, ema_fast_len)
ema_mid  = ta.ema(close, ema_mid_len)
ema_slow = ta.ema(close, ema_slow_len)
[st_line, st_dir] = ta.supertrend(st_mult, st_period)
rsi_val = ta.rsi(close, rsi_len)
atr_val = ta.atr(atr_len)

f_trend_score() =>
    f = ta.ema(close, ema_fast_len)
    m = ta.ema(close, ema_mid_len)
    s = ta.ema(close, ema_slow_len)
    r = ta.rsi(close, rsi_len)
    f > m and m > s and r > 50 ? 1 : f < m and m < s and r < 50 ? -1 : 0

mtf_5   = request.security(syminfo.tickerid, "5", f_trend_score())
mtf_15  = request.security(syminfo.tickerid, "15", f_trend_score())
mtf_60  = request.security(syminfo.tickerid, "60", f_trend_score())
mtf_240 = request.security(syminfo.tickerid, "240", f_trend_score())
mtf_1d  = request.security(syminfo.tickerid, "D", f_trend_score())
alignment = mtf_5 + mtf_15 + mtf_60 + mtf_240 + mtf_1d

trend_bull = ema_fast > ema_mid and ema_mid > ema_slow and st_dir == -1
trend_bear = ema_fast < ema_mid and ema_mid < ema_slow and st_dir == 1
long_setup = trend_bull and alignment >= 2 and rsi_val >= 45 and rsi_val <= 72
exit_setup = trend_bear or alignment <= -2 or rsi_val < 38

qty = strategy.equity * (risk_pct / 100.0) / close
sl = close - atr_stop_mult * atr_val
tp = close + tp_mult * atr_val

if long_setup
    strategy.entry("KiteBot Long", strategy.long, qty=qty)
    strategy.exit("KiteBot SL/TP", "KiteBot Long", stop=sl, limit=tp)

if exit_setup
    strategy.close("KiteBot Long")

plot(ema_fast, "EMA 20", color=color.new(color.aqua, 0))
plot(ema_mid, "EMA 50", color=color.new(color.orange, 0))
plot(ema_slow, "EMA 200", color=color.new(color.fuchsia, 0))
plot(st_line, "Supertrend", color=st_dir == -1 ? color.green : color.red, linewidth=2)
plot(sl, "SL", color=color.new(color.red, 0), style=plot.style_linebr)
plot(tp, "TP", color=color.new(color.green, 0), style=plot.style_linebr)
plotshape(long_setup, title="Long setup", style=shape.triangleup,
     location=location.belowbar, color=color.green, size=size.tiny, text="KB")
plotshape(exit_setup, title="Exit setup", style=shape.triangledown,
     location=location.abovebar, color=color.red, size=size.tiny, text="EXIT")

var table t = table.new(position.top_right, 2, 6, border_width=1)
if barstate.islast
    table.cell(t, 0, 0, "KiteBot Strategy", bgcolor=color.blue, text_color=color.white)
    table.cell(t, 1, 0, alignment >= 3 ? "BULL STACK" : alignment <= -3 ? "BEAR STACK" : "MIXED")
    table.cell(t, 0, 1, "5m/15m/1h")
    table.cell(t, 1, 1, str.tostring(mtf_5) + "/" + str.tostring(mtf_15) + "/" + str.tostring(mtf_60))
    table.cell(t, 0, 2, "4h/1D")
    table.cell(t, 1, 2, str.tostring(mtf_240) + "/" + str.tostring(mtf_1d))
    table.cell(t, 0, 3, "RSI")
    table.cell(t, 1, 3, str.tostring(rsi_val, "#.0"))
    table.cell(t, 0, 4, "SL / TP")
    table.cell(t, 1, 4, str.tostring(sl, "#.####") + " / " + str.tostring(tp, "#.####"))
    table.cell(t, 0, 5, "Mode")
    table.cell(t, 1, 5, long_setup ? "BUY SETUP" : exit_setup ? "EXIT/RISK OFF" : "WAIT")
"""

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>KiteBot Live Coach</title>
<meta http-equiv="refresh" content="10">
<style>
  body{margin:0;background:#0d1117;color:#e6edf3;font-family:system-ui,sans-serif}
  header{padding:14px 20px;border-bottom:1px solid #30363d;display:flex;
         justify-content:space-between;align-items:center}
  h1{font-size:18px;margin:0}
  .pill{padding:3px 10px;border-radius:12px;font-size:12px;background:#1f6feb}
  .pill.warn{background:#d29922}.pill.bad{background:#da3633}.pill.good{background:#238636}
  main{padding:18px 20px;display:grid;grid-template-columns:2fr 1fr;gap:18px}
  section{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px}
  h2{font-size:14px;margin:0 0 10px;color:#7d8590;text-transform:uppercase;letter-spacing:.5px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{padding:6px 8px;text-align:left;border-bottom:1px solid #21262d}
  th{color:#7d8590;font-weight:500}
  a{color:#58a6ff}
  .num{font-variant-numeric:tabular-nums;text-align:right}
  .green{color:#3fb950}.red{color:#f85149}
  pre{white-space:pre-wrap;font-size:12px;color:#7d8590}
  #chart{height:380px}
  .reason{max-width:760px}
  .stamp{font-size:11px;color:#7d8590}
</style>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<script>
window.KITEBOT_BOOTSTRAP = __KITEBOT_BOOTSTRAP__;
</script>
<meta name="kitebot-chart-engine" content="local-svg; lightweight-charts-compatible" />
</head>
<body>
<header>
  <h1>KiteBot Live Coach <span class="pill" id="state-pill">loading</span></h1>
  <div class="stamp" id="asof">—</div>
</header>
<main>
  <section>
    <h2>Active symbol &amp; chart</h2>
    <div id="chart"></div>
    <div class="stamp" id="chart-note">price ticks update each refresh</div>
  </section>
  <section>
    <h2>Coach</h2>
    <table>
      <tr><th>Mode</th>          <td id="mode">—</td></tr>
      <tr><th>Active strategy</th><td id="strategy">—</td></tr>
      <tr><th>Active symbol</th> <td id="symbol">—</td></tr>
      <tr><th>TradingView</th>   <td><a id="tv-link" href="#" target="_blank">—</a></td></tr>
      <tr><th>Capital tier</th>  <td id="tier">—</td></tr>
      <tr><th>Effective risk %</th><td id="risk" class="num">—</td></tr>
      <tr><th>Regime</th>        <td id="regime">—</td></tr>
      <tr><th>Confidence</th>    <td id="confidence" class="num">—</td></tr>
      <tr><th>Stop / Target</th> <td><span id="stop">—</span> / <span id="target">—</span></td></tr>
      <tr><th>P&amp;L (realized)</th><td id="pnl" class="num">—</td></tr>
      <tr><th>Open positions</th><td id="positions" class="num">—</td></tr>
    </table>
  </section>
  <section style="grid-column:1/-1">
    <h2>Multi-timeframe analysis</h2>
    <table id="mtf">
      <tr><th>TF</th><th>Bias</th><th class="num">RSI</th><th class="num">EMA 20</th><th class="num">EMA 50</th></tr>
    </table>
  </section>
  <section style="grid-column:1/-1">
    <h2>Open paper positions</h2>
    <table id="open-positions">
      <tr><th>Symbol</th><th class="num">Qty</th><th class="num">Entry</th><th class="num">Last</th><th class="num">Stop</th><th class="num">Target</th><th class="num">P&amp;L</th></tr>
    </table>
  </section>
  <section style="grid-column:1/-1">
    <h2>Last 20 decisions</h2>
    <table id="decisions">
      <tr><th>Time</th><th>Symbol</th><th>Signal</th><th class="num">Score</th>
          <th>Reason</th></tr>
    </table>
  </section>
  <section style="grid-column:1/-1">
    <h2>Strategy leaderboard</h2>
    <table id="leaderboard">
      <tr><th>Strategy</th><th class="num">Trades</th><th class="num">Win%</th>
          <th class="num">PF</th><th class="num">Max DD%</th>
          <th class="num">Score</th><th>Status</th></tr>
    </table>
  </section>
</main>
<script>
const $ = (id) => document.getElementById(id);
function render(d) {
    $('asof').textContent = 'updated ' + (d.asof || '');
    const sp = $('state-pill');
    sp.textContent = d.running_state || 'unknown';
    sp.className = 'pill ' +
      (d.running_state === 'RUNNING' ? 'good' :
       d.running_state === 'PAUSED'  ? 'warn' :
       d.running_state === 'HALTED'  ? 'bad'  : '');
    $('mode').textContent       = d.mode || '—';
    $('strategy').textContent   = d.active_strategy || '—';
    $('symbol').textContent     = d.active_symbol   || '—';
    $('tier').textContent       = d.capital_tier    || '—';
    $('risk').textContent       = (d.effective_risk_pct ?? '—') + '%';
    $('regime').textContent     = d.regime || '—';
    $('confidence').textContent = (d.confidence ?? '—');
    $('stop').textContent       = d.stop   ?? '—';
    $('target').textContent     = d.target ?? '—';
    $('pnl').textContent        = d.realized_pnl ?? '—';
    $('positions').textContent  = d.open_positions ?? '—';
    const tv = $('tv-link');
    if (d.tradingview_url) {
      tv.textContent = 'open ' + (d.active_symbol || 'chart');
      tv.href = d.tradingview_url;
    } else {
      tv.textContent = '—';
      tv.removeAttribute('href');
    }
    const mtf = $('mtf');
    mtf.innerHTML = '<tr><th>TF</th><th>Bias</th><th class="num">RSI</th><th class="num">EMA 20</th><th class="num">EMA 50</th></tr>';
    (d.mtf || []).forEach(x => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${x.tf||''}</td><td>${x.bias||''}</td>
        <td class="num">${x.rsi ?? ''}</td><td class="num">${x.ema_fast ?? ''}</td>
        <td class="num">${x.ema_slow ?? ''}</td>`;
      mtf.appendChild(tr);
    });
    const op = $('open-positions');
    op.innerHTML = '<tr><th>Symbol</th><th class="num">Qty</th><th class="num">Entry</th><th class="num">Last</th><th class="num">Stop</th><th class="num">Target</th><th class="num">P&L</th></tr>';
    (d.positions || []).forEach(x => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${x.symbol||''}</td><td class="num">${x.qty ?? ''}</td>
        <td class="num">${x.entry ?? ''}</td><td class="num">${x.last ?? ''}</td>
        <td class="num">${x.stop ?? ''}</td><td class="num">${x.target ?? ''}</td>
        <td class="num">${x.pnl ?? ''}</td>`;
      op.appendChild(tr);
    });
    const dec = $('decisions');
    dec.innerHTML = '<tr><th>Time</th><th>Symbol</th><th>Signal</th><th class="num">Score</th><th>Reason</th></tr>';
    (d.decisions || []).forEach(x => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${x.ts||''}</td><td>${x.symbol||''}</td>
        <td>${x.signal||''}</td><td class="num">${x.score ?? ''}</td>
        <td>${x.reason||''}</td>`;
      dec.appendChild(tr);
    });
    const lb = $('leaderboard');
    lb.innerHTML = '<tr><th>Strategy</th><th class="num">Trades</th>'
      + '<th class="num">Win%</th><th class="num">PF</th>'
      + '<th class="num">Max DD%</th><th class="num">Score</th><th>Status</th></tr>';
    (d.leaderboard || []).forEach(x => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${x.name}</td><td class="num">${x.trades}</td>
        <td class="num">${(x.win_rate*100).toFixed(1)}</td>
        <td class="num">${x.profit_factor.toFixed(2)}</td>
        <td class="num">${x.max_dd_pct.toFixed(1)}</td>
        <td class="num">${x.score.toFixed(2)}</td>
        <td>${x.status}</td>`;
      lb.appendChild(tr);
    });
    drawChart(d);
}
async function load() {
  try {
    let d = null;
    try {
      const r = await fetch('live-coach.json?_=' + Date.now());
      if (r.ok) d = await r.json();
    } catch (ignored) {
      // file:// pages often cannot fetch sibling JSON in Chrome/Edge.
      // The bot embeds the latest state into this HTML on every refresh.
    }
    if (!d) d = window.KITEBOT_BOOTSTRAP;
    if (!d) throw new Error('no live coach data yet');
    render(d);
  } catch (e) {
    $('state-pill').textContent = 'no data yet';
    $('state-pill').className   = 'pill warn';
  }
}
let chart, candleSeries, ema20Series, ema50Series, ema200Series;
let supportSeries, resistanceSeries;
let priceLineHandles = [];
function drawChart(d) {
  const candles = d.candles || [];
  if (!candles.length) return;
  if (!chart) {
    chart = LightweightCharts.createChart($('chart'), {
      width: $('chart').clientWidth, height: 380,
      layout: { background:{color:'#161b22'}, textColor:'#e6edf3' },
      grid:   { vertLines:{color:'#21262d'}, horzLines:{color:'#21262d'} },
    });
    candleSeries = chart.addCandlestickSeries({
      upColor:'#3fb950', downColor:'#f85149',
      borderUpColor:'#3fb950', borderDownColor:'#f85149',
      wickUpColor:'#3fb950', wickDownColor:'#f85149',
    });
    ema20Series = chart.addLineSeries({ color:'#00d4ff', lineWidth:1 });
    ema50Series = chart.addLineSeries({ color:'#f0a500', lineWidth:1 });
    ema200Series = chart.addLineSeries({ color:'#d65cff', lineWidth:1 });
    supportSeries = chart.addLineSeries({ color:'#3fb950', lineWidth:2 });
    resistanceSeries = chart.addLineSeries({ color:'#f85149', lineWidth:2 });
  }
  candleSeries.setData(candles);
  ema20Series.setData(d.ema20 || []);
  ema50Series.setData(d.ema50 || []);
  ema200Series.setData(d.ema200 || []);
  supportSeries.setData(d.support_line || []);
  resistanceSeries.setData(d.resistance_line || []);
  candleSeries.setMarkers(d.markers || []);
  priceLineHandles.forEach(line => candleSeries.removePriceLine(line));
  priceLineHandles = [];
  (d.price_lines || []).forEach(x => {
    priceLineHandles.push(candleSeries.createPriceLine({
      price: x.price, color: x.color || '#e6edf3',
      lineWidth: 1, lineStyle: 2, axisLabelVisible: true,
      title: x.title || ''
    }));
  });
  chart.timeScale().fitContent();
}
load(); setInterval(load, 5000);
</script>
</body>
</html>
"""


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>KiteBot Terminal</title>
<style>
  :root{
    --bg:#f5f7fb; --panel:#ffffff; --line:#e6eaf2; --line2:#dfe4ed;
    --text:#1f2937; --muted:#7b8794; --blue:#387ed1; --blue2:#2f6db5;
    --green:#00a676; --red:#df514c; --orange:#ff8a00; --dark:#17202a;
    --soft:#fbfcff; --hover:#eef6ff; --shadow:0 1px 2px rgba(15,23,42,.05);
  }
  body[data-theme="dark"]{
    --bg:#0b1118; --panel:#111923; --line:#253142; --line2:#314154;
    --text:#e8eef7; --muted:#8c9aad; --blue:#5aa2ff; --blue2:#8abfff;
    --green:#2bd68f; --red:#ff6b6b; --orange:#ffb020; --dark:#e8eef7;
    --soft:#141f2b; --hover:#17263a; --shadow:none;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif;font-size:12px}
  button,input,select{font:inherit}
  .topbar{height:48px;background:var(--panel);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 16px;box-shadow:var(--shadow)}
  .brand{display:flex;align-items:center;gap:10px;font-weight:700;color:var(--blue);font-size:17px}
  .brand-dot{width:26px;height:26px;border-radius:4px;background:var(--blue);color:#fff;display:grid;place-items:center;font-weight:800}
  .nav{display:flex;gap:16px;color:var(--muted);font-weight:600}
  .nav button{border:0;background:transparent;color:var(--muted);font-weight:750;cursor:pointer;padding:6px 0}
  .nav button.active{color:var(--orange);border-bottom:2px solid var(--orange)}
  .status{display:flex;align-items:center;gap:10px;color:var(--muted)}
  .theme-toggle{border:1px solid var(--line2);background:var(--panel);color:var(--text);border-radius:3px;height:28px;padding:0 10px;cursor:pointer}
  .pill{border-radius:999px;padding:4px 9px;background:#e8f1ff;color:var(--blue);font-weight:700}
  .pill.good{background:#e8fff5;color:var(--green)}.pill.warn{background:#fff4dc;color:#a15c00}.pill.bad{background:#ffeceb;color:var(--red)}
  .layout{height:calc(100vh - 48px);display:grid;grid-template-columns:300px minmax(560px,1fr) 360px;grid-template-rows:minmax(0,1fr) 275px;gap:8px;padding:8px}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:3px;overflow:hidden;min-height:0;min-width:0}
  .panel h2{height:34px;margin:0;padding:9px 12px;border-bottom:1px solid var(--line);font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);background:var(--soft)}
  .marketwatch{grid-row:1/3;display:flex;flex-direction:column}
  .search{padding:8px;border-bottom:1px solid var(--line)}
  .search input{width:100%;height:30px;border:1px solid var(--line2);border-radius:3px;padding:0 9px;color:var(--text);background:var(--panel)}
  .mw-list{overflow:auto}
  .mw-row{display:grid;grid-template-columns:1fr 66px 58px;gap:8px;align-items:center;padding:9px 10px;border-bottom:1px solid var(--line);cursor:pointer}
  .mw-row:hover{background:var(--hover)}
  .mw-row.active{background:var(--hover);border-left:3px solid var(--blue)}
  .sym{font-weight:700}.sub{font-size:10px;color:var(--muted);margin-top:2px}.ltp{text-align:right;font-variant-numeric:tabular-nums}.sig{text-align:right;font-weight:700}
  .green{color:var(--green)}.red{color:var(--red)}.orange{color:var(--orange)}.muted{color:var(--muted)}
  .chart-panel{display:flex;flex-direction:column}
  .chart-head{height:42px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 12px}
  .chart-title{font-size:16px;font-weight:700}.chart-sub{font-size:11px;color:var(--muted);margin-left:8px}
  .chart-tabs{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.chart-tabs button{padding:4px 8px;border:1px solid var(--line2);border-radius:3px;color:var(--muted);background:var(--panel);cursor:pointer}.chart-tabs .active{border-color:var(--blue);color:var(--blue)}
  .tv-wrap{flex:1;min-height:0;background:var(--panel);position:relative}.tv-frame{width:100%;height:100%;border:0;display:block}.tv-frame.hidden{display:none}
  .local-chart{width:100%;height:100%;display:block;background:var(--panel)}.local-chart.hidden{display:none}
  .chart-empty{position:absolute;inset:0;display:none;align-items:center;justify-content:center;color:var(--muted)}
  .chart-empty.show{display:flex}
  .right{display:flex;flex-direction:column;gap:8px;min-height:0}
  .account-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:10px}
  .metric{border:1px solid var(--line);border-radius:3px;padding:9px;background:var(--panel)}
  .metric .label{color:var(--muted);font-size:10px;text-transform:uppercase}.metric .value{font-size:17px;font-weight:750;margin-top:5px;font-variant-numeric:tabular-nums}
  .positions-side{flex:1;min-height:0;overflow:auto}
  table{width:100%;border-collapse:collapse;font-size:12px}
  th,td{padding:8px 9px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
  th{color:var(--muted);font-weight:700;background:var(--soft);position:sticky;top:0;z-index:1}
  tbody tr{cursor:pointer} tbody tr:hover{background:var(--hover)}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
  .bottom{grid-column:2/4;display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,.9fr) minmax(0,1.05fr);gap:8px;min-height:0;overflow:hidden}
  .bottom .panel{display:flex;flex-direction:column}
  .scroll{height:100%;min-height:0;overflow:auto;flex:1}
  .bottom table{min-width:520px}
  .reason{max-width:360px;min-width:180px;white-space:normal;color:#6b7280;line-height:1.35;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  .footer-note{height:24px;display:flex;align-items:center;padding:0 10px;color:var(--muted);border-top:1px solid var(--line);background:var(--soft)}
  .actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:10px;border-top:1px solid var(--line)}
  .actions select,.actions input{height:34px;border:1px solid var(--line2);border-radius:3px;padding:0 8px;background:var(--panel);color:var(--text)}
  .actions button{height:34px;border:0;border-radius:3px;color:#fff;font-weight:800;cursor:pointer}
  .buy{background:var(--blue)}.sell{background:var(--orange)}.flat{background:var(--red)}.pause{background:#6b7280}.resume{background:var(--green)}
  .action-msg{grid-column:1/-1;color:var(--muted);min-height:16px}
  .capital-edit{display:grid;grid-template-columns:1fr 104px 64px;gap:8px;padding:0 10px 10px}
  .capital-edit label{align-self:center;color:var(--muted);font-weight:700}
  .capital-edit input{height:32px;border:1px solid var(--line2);border-radius:3px;background:var(--panel);color:var(--text);padding:0 8px}
  .capital-edit button{height:32px;border:0;border-radius:3px;background:var(--blue);color:#fff;font-weight:800;cursor:pointer}
  .focus-pulse{outline:2px solid var(--orange);outline-offset:-2px}
  @media(max-width:1100px){.topbar{height:auto;align-items:flex-start;gap:8px;flex-direction:column;padding:10px}.nav{flex-wrap:wrap;gap:10px}.status{flex-wrap:wrap}.layout{grid-template-columns:1fr;grid-template-rows:auto;height:auto}.marketwatch{grid-row:auto}.chart-panel{min-height:560px}.chart-head{height:auto;min-height:42px;gap:8px;align-items:flex-start;padding:8px 12px;flex-direction:column}.bottom{grid-column:auto;grid-template-columns:1fr;overflow:visible}.bottom .panel{min-height:260px}.bottom table{min-width:560px}.tv-wrap{flex:0 0 480px;height:480px}.right{min-height:500px}.capital-edit{grid-template-columns:1fr 1fr}.capital-edit label,.capital-edit button{grid-column:1/-1}.actions{grid-template-columns:1fr 1fr}}
</style>
<script>
window.KITEBOT_BOOTSTRAP = __KITEBOT_BOOTSTRAP__;
</script>
<meta name="kitebot-chart-engine" content="local-svg; lightweight-charts-compatible" />
</head>
<body>
<div class="topbar">
  <div class="brand"><div class="brand-dot">K</div><div>KiteBot Terminal</div></div>
  <div class="nav">
    <button class="active" data-view="dashboard" onclick="setView('dashboard')">Dashboard</button>
    <button data-view="portfolio" onclick="setView('portfolio')">Portfolio</button>
    <button data-view="orders" onclick="setView('orders')">Orders</button>
    <button data-view="funds" onclick="setView('funds')">Funds</button>
    <button data-view="bot" onclick="setView('bot')">Bot Brain</button>
  </div>
  <div class="status"><button class="theme-toggle" id="theme-btn" onclick="toggleTheme()">Theme</button><span id="asof">waiting</span><span class="pill" id="state-pill">loading</span></div>
</div>
<main class="layout">
  <section class="panel marketwatch" data-panel="marketwatch">
    <h2>Marketwatch</h2>
    <div class="search"><input value="NSE equity paper watchlist" readonly></div>
    <div class="mw-list" id="watchlist"></div>
    <div class="footer-note">Click any coin to switch chart and order ticket.</div>
  </section>

  <section class="panel chart-panel" data-panel="chart">
    <div class="chart-head">
      <div><span class="chart-title" id="active-symbol">-</span><span class="chart-sub" id="active-exchange">-</span></div>
      <div class="chart-tabs">
        <button class="active" data-tf="5" onclick="setTimeframe('5')">5m</button>
        <button data-tf="15" onclick="setTimeframe('15')">15m</button>
        <button data-tf="60" onclick="setTimeframe('60')">1h</button>
        <button data-tf="240" onclick="setTimeframe('240')">4h</button>
        <button data-tf="D" onclick="setTimeframe('D')">1D</button>
        <button class="active" data-chart-mode="local" onclick="setChartMode('local')">Smooth</button>
        <button data-chart-mode="tv" onclick="setChartMode('tv')">TradingView</button>
      </div>
    </div>
    <div class="tv-wrap">
      <svg class="local-chart" id="local-chart" viewBox="0 0 1000 420" preserveAspectRatio="none"></svg>
      <iframe class="tv-frame hidden" id="tv-frame" title="TradingView chart"></iframe>
      <div class="chart-empty" id="chart-empty">Waiting for chart data...</div>
    </div>
  </section>

  <aside class="right">
    <section class="panel" data-panel="funds">
      <h2>Funds & P&amp;L</h2>
      <div class="account-grid">
        <div class="metric"><div class="label">Equity</div><div class="value" id="equity">-</div></div>
        <div class="metric"><div class="label">Available</div><div class="value" id="cash">-</div></div>
        <div class="metric"><div class="label">Open P&amp;L</div><div class="value" id="open-pnl">-</div></div>
        <div class="metric"><div class="label">Realized P&amp;L</div><div class="value" id="realized-pnl">-</div></div>
        <div class="metric"><div class="label">Used Margin</div><div class="value" id="used">-</div></div>
        <div class="metric"><div class="label">Max Budget</div><div class="value" id="budget">-</div></div>
      </div>
      <div class="capital-edit">
        <label for="capital-input">Paper capital cap</label>
        <input id="capital-input" type="number" min="500" max="5000" step="100" value="5000">
        <button onclick="setCapital()">Apply</button>
      </div>
    </section>
    <section class="panel positions-side" data-panel="portfolio">
      <h2>Positions</h2>
      <table id="positions-table">
        <thead><tr><th>Instrument</th><th class="num">Qty</th><th class="num">Avg</th><th class="num">LTP</th><th class="num">P&amp;L</th></tr></thead>
        <tbody></tbody>
      </table>
      <div class="actions">
        <select id="action-symbol" onchange="selectSymbol(this.value)"></select>
        <input id="action-note" value="phone/manual" aria-label="reason">
        <button class="buy" onclick="sendAction('buy')">BUY</button>
        <button class="sell" onclick="sendAction('sell')">SELL</button>
        <button class="flat" onclick="sendAction('flatten')">FLATTEN</button>
        <button class="pause" onclick="sendAction('pause')">PAUSE</button>
        <button class="resume" onclick="sendAction('resume')">RESUME</button>
        <button class="buy" onclick="sendAction('scan')">SCAN</button>
        <div id="action-msg" class="action-msg"></div>
      </div>
    </section>
  </aside>

  <section class="bottom" data-panel="bot">
    <section class="panel" data-panel="orders">
      <h2>Order / Trade Book</h2>
      <div class="scroll">
        <table id="trades-table">
          <thead><tr><th>Time</th><th>Instrument</th><th>Exchange</th><th>Type</th><th class="num">Qty</th><th class="num">Price</th><th class="num">Value</th><th class="num">P&amp;L</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </section>
    <section class="panel" data-panel="next-buys">
      <h2>Bot Thinking / Next Buys</h2>
      <div class="scroll">
        <table id="next-table">
          <thead><tr><th>Rank</th><th>Symbol</th><th>Signal</th><th class="num">Score</th><th>Reason</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </section>
    <section class="panel" data-panel="analysis">
      <h2>Live Analysis / Decisions</h2>
      <div class="scroll">
        <table id="decisions-table">
          <thead><tr><th>Time</th><th>Symbol</th><th>Signal</th><th class="num">Score</th><th>Reason</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </section>
  </section>
</main>
<script>
const $ = id => document.getElementById(id);
const rupee = v => (v === null || v === undefined || v === '') ? '-' :
  '₹' + Number(v).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});
const num = (v,d=4) => (v === null || v === undefined || v === '') ? '-' : Number(v).toLocaleString('en-IN',{maximumFractionDigits:d});
const cls = v => Number(v||0) > 0 ? 'green' : Number(v||0) < 0 ? 'red' : '';
let selectedSymbol = '';
let currentTimeframe = localStorage.getItem('kitebot_tf') || '5';
let chartMode = localStorage.getItem('kitebot_chart_mode') || 'local';
let currentTvUrl = '';
let lastGood = window.KITEBOT_BOOTSTRAP || {};
function applyTheme(theme){
  const next = theme || localStorage.getItem('kitebot_theme') || 'light';
  document.body.setAttribute('data-theme', next);
  localStorage.setItem('kitebot_theme', next);
  $('theme-btn').textContent = next === 'dark' ? 'Light' : 'Dark';
}
function toggleTheme(){
  applyTheme(document.body.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
  currentTvUrl = '';
  render(lastGood);
}
function setView(view){
  document.querySelectorAll('.nav button').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  const target = view === 'dashboard' ? document.querySelector('[data-panel="chart"]') :
    document.querySelector(`[data-panel="${view === 'portfolio' ? 'portfolio' : view}"]`);
  if (target) {
    target.scrollIntoView({behavior:'smooth', block:'nearest'});
    target.classList.add('focus-pulse');
    setTimeout(() => target.classList.remove('focus-pulse'), 700);
  }
}
function setTimeframe(tf){
  currentTimeframe = tf;
  localStorage.setItem('kitebot_tf', tf);
  document.querySelectorAll('[data-tf]').forEach(b => b.classList.toggle('active', b.dataset.tf === tf));
  currentTvUrl = '';
  render(lastGood);
}
function setChartMode(mode){
  chartMode = mode;
  localStorage.setItem('kitebot_chart_mode', mode);
  document.querySelectorAll('[data-chart-mode]').forEach(b => b.classList.toggle('active', b.dataset.chartMode === mode));
  render(lastGood);
}
function tvEmbedUrl(d, symbol){
  const row = (d.watchlist || []).find(x => x.symbol === symbol);
  const base = row && row.chart_url ? row.chart_url : d.tradingview_widget_url;
  if (base) return base.replace(/interval=[^&]*/, 'interval=' + encodeURIComponent(currentTimeframe))
    .replace(/theme=[^&]*/, 'theme=' + encodeURIComponent(document.body.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'));
  const url = d.tradingview_url || '';
  const m = url.match(/symbol=([^&]+)/);
  const sym = m ? m[1] : 'NSE%3ARELIANCE';
  const theme = document.body.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  return 'https://www.tradingview.com/widgetembed/?symbol=' + sym + '&interval=' + encodeURIComponent(currentTimeframe) + '&theme=' + theme + '&style=1&timezone=Asia%2FKolkata&hide_top_toolbar=0&hide_side_toolbar=0&save_image=0';
}
function selectSymbol(symbol){
  selectedSymbol = symbol || selectedSymbol;
  const sel = $('action-symbol');
  if (sel && symbol) sel.value = symbol;
  if (symbol && lastGood && symbol !== lastGood.active_symbol) {
    chartMode = 'tv';
    localStorage.setItem('kitebot_chart_mode', chartMode);
    document.querySelectorAll('[data-chart-mode]').forEach(b => b.classList.toggle('active', b.dataset.chartMode === chartMode));
  }
  currentTvUrl = '';
  render(lastGood);
}
function pointsFor(series){
  const vals = (series || []).map(x => Number(x.value ?? x.close)).filter(x => Number.isFinite(x));
  if (!vals.length) return '';
  const min = Math.min(...vals), max = Math.max(...vals), span = Math.max(max - min, 0.000001);
  return vals.map((v,i) => `${(i/(vals.length-1||1))*960+20},${390-((v-min)/span)*340}`).join(' ');
}
function drawLocalChart(d, symbol){
  const svg = $('local-chart');
  const empty = $('chart-empty');
  const series = d.chart_series || [];
  const pts = pointsFor(series);
  const themeDark = document.body.getAttribute('data-theme') === 'dark';
  if (!pts) {
    svg.innerHTML = '';
    empty.classList.add('show');
    return;
  }
  empty.classList.remove('show');
  const last = series[series.length - 1] || {};
  const vals = series.map(p => Number(p.value)).filter(Number.isFinite);
  const prices = (d.price_lines || []).map(x => Number(x.price)).filter(Number.isFinite);
  const min = Math.min(...vals.concat(prices));
  const max = Math.max(...vals.concat(prices));
  const span = Math.max(max - min, 0.000001);
  const levels = (d.price_lines || []).map(x => {
    const price = Number(x.price);
    if (!Number.isFinite(price)) return '';
    const y = 390 - ((price - min) / span) * 340;
    return `<line x1="20" y1="${y}" x2="980" y2="${y}" stroke="${x.color || '#999'}" stroke-width="1.5" stroke-dasharray="7 5"/><text x="780" y="${Math.max(16,y-4)}" fill="${x.color || '#999'}" font-size="13">${x.title || ''} ${num(price)}</text>`;
  }).join('');
  const lastY = pts.split(' ').pop().split(',')[1];
  svg.innerHTML = `
    <rect x="0" y="0" width="1000" height="420" fill="${themeDark ? '#111923' : '#ffffff'}"/>
    <g stroke="${themeDark ? '#253142' : '#e6eaf2'}" stroke-width="1">
      <line x1="20" y1="50" x2="980" y2="50"/><line x1="20" y1="135" x2="980" y2="135"/><line x1="20" y1="220" x2="980" y2="220"/><line x1="20" y1="305" x2="980" y2="305"/><line x1="20" y1="390" x2="980" y2="390"/>
    </g>
    ${levels}
    <polyline fill="none" stroke="#387ed1" stroke-width="3" points="${pts}"/>
    <circle cx="980" cy="${lastY}" r="5" fill="#387ed1"/>
    <text x="22" y="28" fill="${themeDark ? '#e8eef7' : '#1f2937'}" font-size="18" font-weight="700">${symbol || ''} live bot chart</text>
    <text x="22" y="410" fill="${themeDark ? '#8c9aad' : '#7b8794'}" font-size="13">Last ${num(last.value)} | refreshed ${d.asof || ''}</text>`;
}
function render(d){
  d = d || {};
  lastGood = d;
  const account = d.account || {};
  const activeSymbol = selectedSymbol || d.active_symbol || ((d.watchlist || [])[0] || {}).symbol || '';
  $('asof').textContent = 'updated ' + (d.asof || '-');
  const sp = $('state-pill');
  sp.textContent = d.running_state || 'UNKNOWN';
  sp.className = 'pill ' + (d.running_state === 'RUNNING' ? 'good' : d.running_state === 'PAUSED' ? 'warn' : d.running_state === 'HALTED' ? 'bad' : '');
  $('active-symbol').textContent = activeSymbol || '-';
  $('active-exchange').textContent = (d.exchange || 'NSE') + ' · ' + (d.mode || 'paper');
  const frame = $('tv-frame');
  const local = $('local-chart');
  const nextUrl = tvEmbedUrl(d, activeSymbol);
  frame.classList.toggle('hidden', chartMode !== 'tv');
  local.classList.toggle('hidden', chartMode !== 'local');
  if (chartMode === 'tv' && nextUrl && nextUrl !== currentTvUrl) {
    frame.src = nextUrl;
    currentTvUrl = nextUrl;
  }
  if (chartMode === 'local') drawLocalChart(d, activeSymbol);
  $('equity').textContent = rupee(account.equity);
  $('cash').textContent = rupee(account.cash);
  $('open-pnl').textContent = rupee(account.unrealized_pnl); $('open-pnl').className = 'value ' + cls(account.unrealized_pnl);
  $('realized-pnl').textContent = rupee(account.realized_pnl); $('realized-pnl').className = 'value ' + cls(account.realized_pnl);
  $('used').textContent = rupee(account.gross_exposure);
  $('budget').textContent = rupee(account.max_budget);
  $('capital-input').value = Number(account.paper_budget || account.max_budget || 5000);

  const wl = $('watchlist'); wl.innerHTML = '';
  const sel = $('action-symbol'); const currentSel = selectedSymbol || ''; sel.innerHTML = '';
  (d.watchlist || []).forEach(x => {
    const opt = document.createElement('option');
    opt.value = x.symbol || '';
    opt.textContent = x.symbol || '';
    sel.appendChild(opt);
    const row = document.createElement('div');
    row.className = 'mw-row ' + (x.symbol === activeSymbol ? 'active' : '');
    row.onclick = () => selectSymbol(x.symbol || '');
    row.title = 'Open ' + (x.symbol || '') + ' in the chart and order ticket';
    row.innerHTML = `<div><div class="sym">${x.symbol||''}</div><div class="sub">${x.exchange||''} · ${x.product||''}</div></div>
      <div class="ltp">${num(x.ltp)}</div><div class="sig ${x.signal === 'BUY_CANDIDATE' ? 'green' : x.signal === 'REJECTED' ? 'red' : 'orange'}">${x.signal||''}</div>`;
    wl.appendChild(row);
  });
  const preferredSymbol = currentSel || activeSymbol;
  if (preferredSymbol) sel.value = preferredSymbol;

  const pt = document.querySelector('#positions-table tbody'); pt.innerHTML = '';
  (d.positions || []).forEach(p => {
    const tr = document.createElement('tr');
    tr.onclick = () => selectSymbol(p.symbol || '');
    tr.innerHTML = `<td><b>${p.symbol||''}</b><div class="sub">${p.exchange||''} · ${p.product||''}</div></td>
      <td class="num">${num(p.qty,8)}</td><td class="num">${num(p.entry)}</td><td class="num">${num(p.last)}</td>
      <td class="num ${cls(p.pnl)}">${rupee(p.pnl)}</td>`;
    pt.appendChild(tr);
  });
  if (!(d.positions || []).length) pt.innerHTML = '<tr><td colspan="5" class="muted">No open positions</td></tr>';

  const tt = document.querySelector('#trades-table tbody'); tt.innerHTML = '';
  (d.trades || []).forEach(t => {
    const tr = document.createElement('tr');
    tr.onclick = () => selectSymbol(t.symbol || '');
    tr.innerHTML = `<td>${t.ts||''}</td><td><b>${t.symbol||''}</b></td><td>${t.exchange||''}</td><td>${t.action||''}</td>
      <td class="num">${num(t.qty,8)}</td><td class="num">${num(t.price)}</td><td class="num">${rupee(t.value)}</td>
      <td class="num ${cls(t.pnl)}">${t.pnl === null || t.pnl === undefined ? '-' : rupee(t.pnl)}</td>`;
    tt.appendChild(tr);
  });
  if (!(d.trades || []).length) tt.innerHTML = '<tr><td colspan="8" class="muted">No trades yet</td></tr>';

  const nt = document.querySelector('#next-table tbody'); nt.innerHTML = '';
  (d.next_buys || []).forEach((x, i) => {
    const tr = document.createElement('tr');
    tr.onclick = () => selectSymbol(x.symbol || '');
    tr.innerHTML = `<td>${i + 1}</td><td><b>${x.symbol||''}</b></td><td>${x.signal||''}</td>
      <td class="num">${num(x.score,3)}</td><td class="reason">${x.reason||''}</td>`;
    tr.querySelector('.reason').title = x.reason || '';
    nt.appendChild(tr);
  });
  if (!(d.next_buys || []).length) nt.innerHTML = '<tr><td colspan="5" class="muted">No candidates yet. Press SCAN or wait for the bot scan.</td></tr>';

  const dt = document.querySelector('#decisions-table tbody'); dt.innerHTML = '';
  (d.decisions || []).forEach(x => {
    const tr = document.createElement('tr');
    tr.onclick = () => selectSymbol(x.symbol || '');
    tr.innerHTML = `<td>${x.ts||''}</td><td>${x.symbol||''}</td><td>${x.signal||''}</td>
      <td class="num">${num(x.score,3)}</td><td class="reason">${x.reason||''}</td>`;
    tr.querySelector('.reason').title = x.reason || '';
    dt.appendChild(tr);
  });
}
async function sendAction(action){
  const msg = $('action-msg');
  const d = window.KITEBOT_LAST || window.KITEBOT_BOOTSTRAP || {};
  const base = location.protocol.startsWith('http') ? location.origin : (d.terminal_api_base || '');
  if (!base) {
    msg.textContent = 'Open the phone terminal URL shown by RUN_BOT. A standalone file cannot place orders.';
    return;
  }
  const symbol = $('action-symbol').value || d.active_symbol || '';
  const reason = $('action-note').value || 'phone/manual';
  msg.textContent = 'Sending ' + action + '...';
  try {
    const r = await fetch(base + '/api/' + action, {
      method:'POST',
      credentials:'same-origin',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbol, reason})
    });
    const out = await r.json();
    msg.textContent = out.ok ? (out.message || 'Done') : (out.error || 'Rejected');
    await load();
  } catch(e) {
    msg.textContent = 'Action failed: ' + e;
  }
}
async function setCapital(){
  const msg = $('action-msg');
  const d = window.KITEBOT_LAST || window.KITEBOT_BOOTSTRAP || {};
  const base = location.protocol.startsWith('http') ? location.origin : (d.terminal_api_base || '');
  if (!base) {
    msg.textContent = 'Open the paired terminal URL while RUN_BOT is running.';
    return;
  }
  const amount = Number($('capital-input').value || 0);
  msg.textContent = 'Updating capital cap...';
  try {
    const r = await fetch(base + '/api/set-capital', {
      method:'POST',
      credentials:'same-origin',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({amount})
    });
    const out = await r.json();
    msg.textContent = out.ok ? (out.message || 'Capital updated') : (out.error || 'Rejected');
    await load();
  } catch(e) {
    msg.textContent = 'Capital update failed: ' + e;
  }
}
async function load(){
  let d = null;
  if (location.protocol.startsWith('http')) try {
    const url = '/live-coach.json?_=' + Date.now();
    const r = await fetch(url, {cache:'no-store', credentials:'same-origin'});
    if (r.ok) d = await r.json();
  } catch(e) {}
  if (!d) d = lastGood || window.KITEBOT_BOOTSTRAP;
  window.KITEBOT_LAST = d;
  render(d);
}
applyTheme();
setTimeframe(currentTimeframe);
setChartMode(chartMode);
load(); setInterval(load, 2000);
</script>
</body>
</html>
"""

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>KiteBot Equity Console</title>
<style>
  :root{
    --bg:#f7f8fb;--panel:#fff;--soft:#fbfcff;--line:#e8ebf1;--line2:#d9dee8;
    --text:#3f4652;--strong:#151b2a;--muted:#8a93a3;--blue:#387ed1;--orange:#ff5722;
    --green:#2dac4f;--red:#f04438;--violet:#7657d6;--shadow:0 8px 24px rgba(15,23,42,.06);
    --watch-width:330px;
  }
  body[data-theme="dark"]{
    --bg:#0d1117;--panel:#121821;--soft:#151d28;--line:#263241;--line2:#334155;
    --text:#dbe3ee;--strong:#f8fafc;--muted:#94a3b8;--blue:#60a5fa;--orange:#fb6a3c;
    --green:#38d982;--red:#ff6b6b;--violet:#a78bfa;--shadow:0 8px 24px rgba(0,0,0,.25);
  }
  body[data-theme="mixed"]{
    --bg:#f3f6fa;--panel:#ffffff;--soft:#f8fafc;--line:#e5e7eb;--line2:#d8dee9;
    --text:#384152;--strong:#101828;--blue:#2563eb;--orange:#f97316;--green:#16a34a;--red:#ef4444;--violet:#7c3aed;
  }
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);font:13px/1.45 Inter,Segoe UI,Arial,sans-serif}
  button,input,select{font:inherit;color:var(--text)} button{cursor:pointer}
  input,select{background:var(--panel);border:1px solid var(--line2);border-radius:3px;height:34px;padding:0 10px;outline:none}
  input:focus,select:focus{border-color:var(--blue);box-shadow:0 0 0 3px color-mix(in srgb,var(--blue) 16%,transparent)}
  input[type=range]{accent-color:var(--blue);background:transparent;padding:0}
  body[data-theme="dark"] input,body[data-theme="dark"] select{background:#0f1722;color:var(--text);border-color:#344256}
  body[data-theme="dark"] input[type=range]::-webkit-slider-runnable-track{background:#263241}
  .top{height:48px;background:var(--panel);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 14px;box-shadow:0 1px 8px rgba(0,0,0,.04);position:sticky;top:0;z-index:20}
  .indices{display:flex;gap:18px;min-width:310px}.idx{font-size:12px;color:var(--muted)}.idx b{color:var(--strong);font-weight:650;margin-right:5px}.up{color:var(--green)}.down{color:var(--red)}
  .nav{display:flex;align-items:center;gap:18px}.nav button{height:48px;border:0;background:transparent;color:var(--text);font-weight:600;border-bottom:2px solid transparent}.nav button.active{color:var(--orange);border-bottom-color:var(--orange)}
  .actions-top{display:flex;align-items:center;gap:10px}.icon-btn{height:32px;min-width:32px;border:1px solid var(--line);background:var(--panel);border-radius:4px;color:var(--muted)}
  .top-modes{display:flex;border:1px solid var(--line);border-radius:4px;overflow:hidden}.top-modes button{height:30px;min-width:32px;border:0;border-right:1px solid var(--line);background:var(--panel);color:var(--muted)}.top-modes button:last-child{border-right:0}.top-modes button.active{background:var(--blue);color:#fff}
  .avatar{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,var(--blue),var(--violet));color:#fff;font-weight:800}.profile-id{font-weight:650;color:var(--strong)}
  .shell{height:calc(100vh - 48px);display:grid;grid-template-columns:auto minmax(0,1fr);gap:10px;padding:10px}
  .watch{width:var(--watch-width);min-width:260px;max-width:520px;background:var(--panel);border:1px solid var(--line);box-shadow:var(--shadow);resize:horizontal;overflow:auto}
  .watch-head{height:42px;display:flex;align-items:center;justify-content:space-between;padding:0 12px;border-bottom:1px solid var(--line)}
  .watch-title{font-weight:650;color:var(--strong)}.watch-tools{display:flex;gap:6px}.watch-tools button{height:28px;border:1px solid var(--line);background:var(--soft);border-radius:3px;color:var(--muted)}
  .search{padding:10px;border-bottom:1px solid var(--line)}.search input{width:100%}
  .watch-tabs{display:flex;gap:2px;padding:0 8px;border-bottom:1px solid var(--line)}.watch-tabs button{height:34px;flex:1;border:0;background:transparent;color:var(--muted)}.watch-tabs button.active{color:var(--orange);border-bottom:2px solid var(--orange)}
  .watch-list{height:calc(100vh - 190px);overflow:auto}.watch-row{display:grid;grid-template-columns:1fr 74px 52px;gap:8px;align-items:center;min-height:48px;padding:8px 12px;border-bottom:1px solid var(--line);cursor:pointer}
  .watch-row:hover,.watch-row.active{background:color-mix(in srgb,var(--blue) 8%,transparent)}.sym{font-weight:700;color:var(--strong)}.sub{font-size:10px;color:var(--muted);text-transform:uppercase}.ltp{text-align:right;font-variant-numeric:tabular-nums}.sig{text-align:right;font-weight:750}
  .workspace{min-width:0;overflow:auto}.page{display:none;min-height:100%}.page.active{display:block}
  .page-head{display:flex;align-items:center;justify-content:space-between;margin:2px 0 14px}.page-title{font-size:20px;color:var(--strong);font-weight:500}.page-actions{display:flex;gap:8px;align-items:center}
  .btn{height:34px;border:1px solid var(--line2);border-radius:4px;background:var(--panel);padding:0 12px;color:var(--text)}.btn.primary{background:var(--blue);border-color:var(--blue);color:#fff}.btn.green{background:var(--green);border-color:var(--green);color:#fff}.btn.red{background:var(--red);border-color:var(--red);color:#fff}
  .grid{display:grid;gap:10px}.dash-grid{grid-template-columns:minmax(0,1.45fr) minmax(300px,.75fr)}.three{grid-template-columns:repeat(3,minmax(0,1fr))}.two{grid-template-columns:repeat(2,minmax(0,1fr))}
  .card{background:var(--panel);border:1px solid var(--line);box-shadow:var(--shadow);min-width:0}.card.resizable{resize:both;overflow:auto;min-height:180px}.card>h2{margin:0;padding:12px 14px;border-bottom:1px solid var(--line);font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);background:var(--soft)}
  .pad{padding:14px}.metric-row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.metric{border:1px solid var(--line);background:var(--soft);padding:14px;min-height:84px}.metric label{display:block;font-size:11px;text-transform:uppercase;color:var(--muted)}.metric strong{display:block;margin-top:8px;font-size:22px;color:var(--strong);font-weight:500}
  .chart{height:430px;width:100%;display:block}.bar{height:50px;display:flex;overflow:hidden;margin:14px 0}.slice{height:100%}
  table{width:100%;border-collapse:collapse}th,td{padding:11px 12px;border-bottom:1px solid var(--line);white-space:nowrap;text-align:left}th{font-size:12px;color:var(--muted);font-weight:500;background:var(--soft);position:sticky;top:0;z-index:1}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}.table-wrap{overflow:auto;max-height:calc(100vh - 180px)}.reason{white-space:normal;min-width:260px;color:var(--muted)}
  .empty{height:420px;display:grid;place-items:center;color:var(--muted);text-align:center}.empty .mark{font-size:58px;color:#d1d5db}.loader{width:42px;height:42px;border:3px solid var(--line);border-top-color:var(--blue);border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 16px}@keyframes spin{to{transform:rotate(360deg)}}
  .drawer{position:fixed;right:0;top:48px;width:min(440px,100vw);height:calc(100vh - 48px);background:var(--panel);border-left:1px solid var(--line);box-shadow:-18px 0 32px rgba(15,23,42,.12);transform:translateX(105%);transition:.22s;z-index:30;overflow:auto}.drawer.open{transform:translateX(0)}.drawer-head{display:flex;justify-content:space-between;align-items:center;padding:16px;border-bottom:1px solid var(--line)}.drawer-body{padding:16px}
  .modal{position:fixed;inset:0;background:rgba(15,23,42,.38);display:none;align-items:center;justify-content:center;z-index:40}.modal.open{display:flex}.modal-card{width:min(720px,calc(100vw - 24px));max-height:86vh;overflow:auto;background:var(--panel);border:1px solid var(--line);box-shadow:var(--shadow)}.strategy-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}.strategy-card{border:1px solid var(--line);padding:12px;background:var(--soft);cursor:pointer}.strategy-card:hover{border-color:var(--blue)}
  .brain-list{display:grid;gap:10px}.brain-item{border-left:3px solid var(--blue);background:var(--soft);padding:12px}.mode-switch{display:flex;gap:6px}.mode-switch button.active{background:var(--blue);color:#fff;border-color:var(--blue)}
  @media(max-width:900px){.top{height:auto;min-height:54px;align-items:flex-start;gap:8px;flex-direction:column;padding:8px 10px}.indices{min-width:0;flex-wrap:wrap}.nav{overflow:auto;width:100%;gap:12px}.nav button{height:34px;flex:0 0 auto}.actions-top{position:absolute;right:10px;top:8px}.shell{height:auto;grid-template-columns:1fr;padding:8px}.watch{width:100%;max-width:none;resize:vertical}.watch-list{height:360px}.dash-grid,.three,.two{grid-template-columns:1fr}.metric-row{grid-template-columns:1fr 1fr}.chart{height:360px}.page-head{align-items:flex-start;gap:10px;flex-direction:column}.table-wrap{max-height:none}.drawer{top:0;height:100vh}.profile-id{display:none}}
</style>
<script>window.KITEBOT_BOOTSTRAP = __KITEBOT_BOOTSTRAP__;</script>
<meta name="kitebot-chart-engine" content="local-svg; lightweight-charts-compatible" />
</head>
<body data-theme="light">
<header class="top">
  <div class="indices" id="indices"></div>
  <nav class="nav" id="nav">
    <button class="active" data-page="dashboard">Dashboard</button>
    <button data-page="orders">Orders</button>
    <button data-page="holdings">Holdings</button>
    <button data-page="positions">Positions</button>
    <button data-page="funds">Funds</button>
    <button data-page="bids">Bids</button>
    <button data-page="brain">Brain</button>
  </nav>
  <div class="actions-top">
    <div class="top-modes" title="Theme">
      <button data-theme-choice="light">L</button>
      <button data-theme-choice="dark">D</button>
      <button data-theme-choice="mixed">M</button>
    </div>
    <button class="icon-btn" title="Basket">Cart</button>
    <button class="icon-btn" title="Notifications">Bell</button>
    <button class="avatar" id="profile-avatar" title="Profile">KB</button>
    <span class="profile-id">KITEBOT</span>
  </div>
</header>
<main class="shell">
  <aside class="watch">
    <div class="watch-head"><div class="watch-title">Watchlist 1 <span id="watch-count"></span></div><div class="watch-tools"><button id="collapse-watch">-</button><button id="new-group">+ New</button></div></div>
    <div class="search"><input id="stock-search" placeholder="Search stocks, indices, ETFs" /></div>
    <div class="watch-tabs"><button class="active">Default</button><button>2</button><button>3</button><button>4</button><button>5</button></div>
    <div class="watch-list" id="watchlist"></div>
  </aside>
  <section class="workspace">
    <section class="page active" id="page-dashboard"></section>
    <section class="page" id="page-orders"></section>
    <section class="page" id="page-holdings"></section>
    <section class="page" id="page-positions"></section>
    <section class="page" id="page-funds"></section>
    <section class="page" id="page-bids"></section>
    <section class="page" id="page-brain"></section>
  </section>
</main>
<aside class="drawer" id="stock-drawer"></aside>
<div class="modal" id="strategy-modal"><div class="modal-card" id="strategy-modal-card"></div></div>
<script>
const $ = id => document.getElementById(id);
const rupee = v => (v === null || v === undefined || v === '') ? '-' : 'Rs.' + Number(v).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});
const num = (v,d=2) => (v === null || v === undefined || v === '') ? '-' : Number(v).toLocaleString('en-IN',{maximumFractionDigits:d});
const pnlCls = v => Number(v||0) > 0 ? 'up' : Number(v||0) < 0 ? 'down' : '';
let state = window.KITEBOT_BOOTSTRAP || {};
let selectedSymbol = state.active_symbol || '';
let activePage = 'dashboard';
let lastPaint = 0;
const palette = ['#4f73e8','#19a7ce','#2997e6','#9c27b0','#673ab7','#3f51b5','#13b6c7','#00897b','#8bc34a','#cddc39','#ffc107','#ff9800','#795548','#607d8b','#e91e63','#009688','#7cb342'];
const defaultStrategies = [
  ['equity_vwap_breakout','VWAP Breakout','Intraday trend entry above VWAP with volume and ATR risk.','https://www.youtube.com/results?search_query=vwap+breakout+strategy+india'],
  ['orb_15','15-min ORB','Opening range breakout with strict stop and no averaging.','https://www.youtube.com/results?search_query=opening+range+breakout+strategy'],
  ['ema_supertrend','EMA + Supertrend','Trend-following using EMA alignment and Supertrend confirmation.','https://www.youtube.com/results?search_query=ema+supertrend+strategy'],
  ['darvas_box','Darvas Box','Breakout from consolidation boxes with volume confirmation.','https://www.youtube.com/results?search_query=darvas+box+strategy'],
  ['donchian_breakout','Donchian Breakout','Buys strength above prior highs with volatility filters.','https://www.youtube.com/results?search_query=donchian+breakout+strategy'],
  ['bollinger_reversion','Bollinger Reversion','Mean reversion only in range-bound markets.','https://www.youtube.com/results?search_query=bollinger+bands+mean+reversion'],
  ['rsi_pullback','RSI Pullback','Buys healthy pullbacks in a confirmed uptrend.','https://www.youtube.com/results?search_query=rsi+pullback+strategy'],
  ['macd_momentum','MACD Momentum','Momentum continuation after MACD confirmation.','https://www.youtube.com/results?search_query=macd+momentum+strategy'],
  ['minervini_trend','Trend Template','Stage-2 trend filters inspired by institutional momentum rules.','https://www.youtube.com/results?search_query=mark+minervini+trend+template'],
  ['canslim_screen','CAN SLIM Screen','Fundamental and price-strength screen before technical entry.','https://www.youtube.com/results?search_query=CANSLIM+stock+strategy'],
  ['sector_rotation','Sector Rotation','Ranks sectors and trades leaders only.','https://www.youtube.com/results?search_query=sector+rotation+trading+strategy'],
  ['gap_and_go','Gap and Go','Trades strong gaps only after confirmation.','https://www.youtube.com/results?search_query=gap+and+go+trading+strategy'],
  ['mean_reversion_vwap','VWAP Reversion','Reversion back to VWAP after extreme intraday moves.','https://www.youtube.com/results?search_query=vwap+mean+reversion+strategy'],
  ['atr_trailing','ATR Trail','Trend riding with ATR-based trailing stops.','https://www.youtube.com/results?search_query=atr+trailing+stop+strategy'],
  ['capital_defense','Capital Defense','No new entries after loss streaks or daily loss pressure.','https://www.youtube.com/results?search_query=trading+risk+management+strategy']
].map(([id,name,desc,url]) => ({id,name,desc,url,builder:'KiteBot research desk',risk:'Strict paper-only risk cap'}));

function setTheme(theme){document.body.dataset.theme=theme;localStorage.setItem('kitebot_theme',theme);document.querySelectorAll('[data-theme-choice]').forEach(b=>b.classList.toggle('active',b.dataset.themeChoice===theme));}
function setPage(page){activePage=page;document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));$('page-'+page).classList.add('active');document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.page===page));render(state);}
function compactReason(text){text=String(text||'');return text.length>130?text.slice(0,130)+'...':text;}
function getHoldings(d){return (d.holdings&&d.holdings.length?d.holdings:(d.positions||[])).map(x=>({...x, invested:x.invested||(Number(x.qty||0)*Number(x.entry||0)), current_value:x.value||(Number(x.qty||0)*Number(x.last||0))}));}
function renderIndices(d){const rows=d.indices||[{name:'NIFTY 50',value:d.nifty||'',change:''},{name:'SENSEX',value:d.sensex||'',change:''}];$('indices').innerHTML=rows.map(x=>`<div class="idx"><b>${x.name}</b><span>${num(x.value)}</span> <span class="${pnlCls(x.change)}">${x.change?num(x.change):''}</span></div>`).join('');}
function renderWatchlist(d){const q=($('stock-search').value||'').toUpperCase();const rows=(d.watchlist||[]).filter(x=>(x.symbol||'').includes(q));$('watch-count').textContent=`(${rows.length} / ${d.watchlist?.length||0})`;$('watchlist').innerHTML=rows.map(x=>`<div class="watch-row ${x.symbol===selectedSymbol?'active':''}" data-symbol="${x.symbol}"><div><div class="sym">${x.symbol||''}</div><div class="sub">${x.exchange||'NSE'} · ${x.product||'EQ'}</div></div><div class="ltp">${num(x.ltp)}</div><div class="sig ${x.signal==='REJECTED'?'down':x.signal?'up':''}">${x.signal||''}</div></div>`).join('');document.querySelectorAll('.watch-row').forEach(r=>r.onclick=()=>openStock(r.dataset.symbol));}
function drawChart(d){const series=d.chart_series||[];if(!series.length)return '<div class="empty"><div><div class="loader"></div>No chart data yet</div></div>';const vals=series.map(x=>Number(x.value)).filter(Number.isFinite);const min=Math.min(...vals),max=Math.max(...vals),span=Math.max(max-min,.0001);const pts=vals.map((v,i)=>`${20+i/(vals.length-1||1)*960},${390-(v-min)/span*340}`).join(' ');return `<svg class="chart" viewBox="0 0 1000 430" preserveAspectRatio="none"><rect width="1000" height="430" fill="var(--panel)"/><g stroke="var(--line)" stroke-width="1">${[50,135,220,305,390].map(y=>`<line x1="20" y1="${y}" x2="980" y2="${y}"/>`).join('')}</g><polyline fill="none" stroke="var(--blue)" stroke-width="3" points="${pts}"/><circle cx="980" cy="${pts.split(' ').pop().split(',')[1]}" r="6" fill="var(--blue)"/><text x="22" y="30" fill="var(--strong)" font-size="18" font-weight="700">${selectedSymbol||d.active_symbol||'NSE'} live paper chart</text><text x="22" y="418" fill="var(--muted)" font-size="12">Auto background refresh: 0.5s UI poll, backend tick cadence decides real quote freshness</text></svg>`;}
function renderDashboard(d){const a=d.account||{};const h=getHoldings(d);const totalInv=h.reduce((s,x)=>s+Number(x.invested||0),0);const cur=h.reduce((s,x)=>s+Number(x.current_value||0),0);$('page-dashboard').innerHTML=`<div class="page-head"><div><div class="page-title">Dashboard</div><div class="sub">Indian equity paper mode - ${d.asof||''}</div></div><div class="mode-switch"><button class="btn" data-theme-choice="light">Light</button><button class="btn" data-theme-choice="dark">Dark</button><button class="btn" data-theme-choice="mixed">Mixed</button></div></div><div class="grid dash-grid"><div class="grid"><div class="metric-row"><div class="metric"><label>Equity</label><strong>${rupee(a.equity)}</strong></div><div class="metric"><label>Available</label><strong>${rupee(a.cash)}</strong></div><div class="metric"><label>Open P&L</label><strong class="${pnlCls(a.unrealized_pnl)}">${rupee(a.unrealized_pnl)}</strong></div><div class="metric"><label>Realized P&L</label><strong class="${pnlCls(a.realized_pnl)}">${rupee(a.realized_pnl)}</strong></div></div><div class="card resizable"><h2>Market overview</h2>${drawChart(d)}</div></div><div class="grid"><div class="card resizable"><h2>Holdings snapshot</h2><div class="pad"><div class="metric-row" style="grid-template-columns:1fr 1fr"><div><label>Total investment</label><strong>${rupee(totalInv)}</strong></div><div><label>Current value</label><strong>${rupee(cur)}</strong></div></div><div class="bar">${h.slice(0,17).map((x,i)=>`<div class="slice" style="width:${100/Math.max(h.length,1)}%;background:${palette[i%palette.length]}" title="${x.symbol}"></div>`).join('')}</div><button class="btn primary" onclick="setPage('holdings')">View holdings</button></div></div><div class="card resizable"><h2>Bot state</h2><div class="pad brain-list"><div class="brain-item"><b>${d.running_state||'UNKNOWN'}</b><br>${d.active_strategy||'No strategy selected'}</div><div class="brain-item">Risk per trade: ${num(d.effective_risk_pct,2)}% - Open positions: ${d.open_positions||0}</div></div></div></div></div>`;document.querySelectorAll('[data-theme-choice]').forEach(b=>b.onclick=()=>setTheme(b.dataset.themeChoice));setTheme(localStorage.getItem('kitebot_theme')||document.body.dataset.theme||'light');}
function renderOrders(d){const trades=d.trades||[];$('page-orders').innerHTML=`<div class="page-head"><div class="page-title">Orders</div><div class="page-actions"><input placeholder="Search orders"><button class="btn">Filters</button><button class="btn primary" onclick="sendAction('scan')">Scan</button></div></div><div class="card"><h2>Orders</h2>${trades.length?table(['Time','Instrument','Type','Qty','Price','Value','P&L'],trades.map(t=>[t.ts,t.symbol,t.action,num(t.qty,4),num(t.price),rupee(t.value),`<span class="${pnlCls(t.pnl)}">${t.pnl==null?'-':rupee(t.pnl)}</span>`])):`<div class="empty"><div><div class="loader"></div>You haven't placed any orders today<br><button class="btn primary" onclick="setPage('dashboard')">Get started</button></div></div>`}</div>`;}
function renderHoldings(d){const h=getHoldings(d);const attribution=d.trade_attribution||[];$('page-holdings').innerHTML=`<div class="page-head"><div class="page-title">Holdings (${h.length})</div><div class="page-actions"><input placeholder="Search"><button class="btn">Analytics</button><button class="btn">Download</button></div></div><div class="metric-row"><div class="metric"><label>Total investment</label><strong>${rupee(h.reduce((s,x)=>s+Number(x.invested||0),0))}</strong></div><div class="metric"><label>Current value</label><strong>${rupee(h.reduce((s,x)=>s+Number(x.current_value||0),0))}</strong></div><div class="metric"><label>Day's P&L</label><strong class="${pnlCls((d.account||{}).unrealized_pnl)}">${rupee((d.account||{}).unrealized_pnl)}</strong></div><div class="metric"><label>Total P&L</label><strong class="${pnlCls((d.account||{}).realized_pnl)}">${rupee((d.account||{}).realized_pnl)}</strong></div></div><div class="card" style="margin-top:10px"><h2>Holdings</h2>${table(['Instrument','Qty','Avg. cost','LTP','Invested','Cur. val','P&L','Strategy'],h.map(x=>[x.symbol,num(x.qty,4),num(x.entry),num(x.last),rupee(x.invested),rupee(x.current_value),`<span class="${pnlCls(x.pnl)}">${rupee(x.pnl)}</span>`,x.strategy||d.active_strategy||'manual/legacy']))}</div><div class="card" style="margin-top:10px"><h2>Trade P&L attribution</h2>${table(['Trade','Symbol','Action','Strategy','Entry/Exit reason','P&L'],attribution.map(x=>[x.ts,x.symbol,x.action,x.strategy||'manual/legacy',x.reason||'',`<span class="${pnlCls(x.pnl)}">${x.pnl==null?'-':rupee(x.pnl)}</span>`]))}</div>`;}
function renderPositions(d){const p=d.positions||[];$('page-positions').innerHTML=`<div class="page-head"><div class="page-title">Positions (${p.length})</div><div class="page-actions"><button class="btn">Analytics</button><button class="btn red" onclick="sendAction('flatten')">Flatten all</button></div></div><div class="card"><h2>Positions</h2>${p.length?table(['Instrument','Qty','Avg','LTP','Stop','Target','P&L'],p.map(x=>[x.symbol,num(x.qty,4),num(x.entry),num(x.last),num(x.stop),num(x.target),`<span class="${pnlCls(x.pnl)}">${rupee(x.pnl)}</span>`])):`<div class="empty"><div class="mark">Anchor</div><div>You don't have any positions yet</div></div>`}</div>`;}
function renderFunds(d){const a=d.account||{};$('page-funds').innerHTML=`<div class="page-head"><div class="page-title">Funds</div><div class="page-actions"><button class="btn green">Add funds</button><button class="btn primary">Withdraw</button></div></div><div class="grid two"><div class="card"><h2>Equity</h2><div class="pad">${fundRow('Available margin',a.equity,true)}${fundRow('Used margin',a.gross_exposure)}${fundRow('Available cash',a.cash)}${fundRow('Opening balance',a.opening_balance||a.cash)}${fundRow('SPAN',0)}${fundRow('Exposure',0)}${fundRow('Collateral',0)}</div></div><div class="card"><h2>Risk controls</h2><div class="pad"><label>Paper capital cap</label><input id="capital-input" type="range" min="5000" max="50000" step="1000" value="${a.paper_budget||a.max_budget||50000}" oninput="$('capital-label').textContent=rupee(this.value)"><h2 id="capital-label">${rupee(a.paper_budget||a.max_budget||50000)}</h2><button class="btn primary" onclick="setCapital()">Apply</button><div id="action-msg" class="sub" style="margin-top:10px"></div></div></div></div>`;}
function renderBids(d){const rows=d.bids||[{instrument:'HARIKANTA',date:'20th - 27th May',price:'86 - 91',min_amount:'218400',status:'Apply'},{instrument:'MANIVENI',date:'22nd - 26th May',price:'51 - 52',min_amount:'208000',status:'Apply'},{instrument:'RFIL',date:'26th - 29th May',price:'59 - 63',min_amount:'252000',status:'Apply'}];$('page-bids').innerHTML=`<div class="page-head"><div class="page-title">Bids</div><div class="page-actions"><input placeholder="Search IPOs"></div></div><div class="card"><h2>IPOs and bids</h2>${table(['Instrument','Date','Price','Min. amount',''],rows.map(x=>[x.instrument||x.name,x.date,x.price,rupee(x.min_amount||x.amount),`<button class="btn primary">${x.status}</button>`]))}</div>`;}
function renderBrain(d){const catalog=d.strategy_catalog||defaultStrategies;const notes=d.brain_notes||[];$('page-brain').innerHTML=`<div class="page-head"><div><div class="page-title">Brain</div><div class="sub">Why the bot picked, skipped, won, or lost</div></div><div class="page-actions"><button class="btn primary" onclick="openStrategyModal()">Trading strategies</button><button class="btn" onclick="sendAction('pause')">Pause entries</button></div></div><div class="grid two"><div class="card"><h2>Recent decisions</h2><div class="table-wrap">${table(['Time','Symbol','Signal','Score','Why'],(d.decisions||[]).map(x=>[x.ts,x.symbol,x.signal,num(x.score,3),`<span title="${x.reason||''}">${compactReason(x.reason)}</span>`]))}</div></div><div class="card"><h2>Strategy desk</h2><div class="pad strategy-grid">${catalog.map(s=>`<div class="strategy-card" onclick="openStrategyModal('${s.id}')"><b>${s.name}</b><p>${s.desc}</p><span class="sub">${s.risk||''}</span></div>`).join('')}</div></div></div><div class="card" style="margin-top:10px"><h2>Loss/profit explanation</h2><div class="pad brain-list">${(notes.length?notes:explainTrades(d)).map(n=>`<div class="brain-item">${n}</div>`).join('')}</div></div>`;}
function table(headers,rows){return `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(r=>`<tr>${r.map((c,i)=>`<td class="${i>2?'num':''}">${c??''}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${headers.length}" class="sub">No records yet</td></tr>`}</tbody></table></div>`;}
function fundRow(k,v,big){return `<div style="display:flex;justify-content:space-between;align-items:center;padding:13px 0;border-bottom:1px solid var(--line)"><span>${k}</span><strong style="font-size:${big?'28px':'18px'};color:${big?'var(--blue)':'var(--strong)'}">${rupee(v)}</strong></div>`;}
function explainTrades(d){const rows=d.trade_attribution||[];if(!rows.length)return ['No closed trade attribution yet. New auto-buys and auto-exits will be logged with strategy and reason.'];return rows.slice(0,8).map(x=>`${x.symbol} ${x.action}: ${x.pnl==null?'open':rupee(x.pnl)} via ${x.strategy||'manual/legacy'} - ${x.reason||'no reason recorded on old trade'}`);}
function openStock(symbol){selectedSymbol=symbol;const row=(state.watchlist||[]).find(x=>x.symbol===symbol)||{};$('stock-drawer').innerHTML=`<div class="drawer-head"><div><h2>${symbol}</h2><div class="sub">${row.exchange||'NSE'} · ${row.product||'EQ'}</div></div><button class="btn" onclick="closeDrawer()">Close</button></div><div class="drawer-body"><div class="metric-row" style="grid-template-columns:1fr 1fr"><div class="metric"><label>LTP</label><strong>${num(row.ltp)}</strong></div><div class="metric"><label>Signal</label><strong class="${row.signal==='REJECTED'?'down':'up'}">${row.signal||'-'}</strong></div></div><p>${row.reason||'No current bot reason yet. Run Scan to generate a fresh view.'}</p><div class="grid two"><button class="btn primary" onclick="sendAction('allow-symbol','${symbol}')">Allow bot to trade</button><button class="btn" onclick="sendAction('scan')">Research / scan</button><button class="btn green" onclick="sendAction('buy','${symbol}')">Buy paper</button><button class="btn red" onclick="sendAction('sell','${symbol}')">Sell paper</button></div></div>`;$('stock-drawer').classList.add('open');renderWatchlist(state);}
function closeDrawer(){$('stock-drawer').classList.remove('open');}
function openStrategyModal(id){const catalog=state.strategy_catalog||defaultStrategies;const selected=catalog.find(s=>s.id===id)||catalog[0];$('strategy-modal-card').innerHTML=`<div class="drawer-head"><div><h2>${id?selected.name:'Trading strategies'}</h2><div class="sub">Paper-only strategy library</div></div><button class="btn" onclick="closeStrategyModal()">Close</button></div><div class="drawer-body">${id?strategyDetail(selected):`<div class="strategy-grid">${catalog.map(s=>`<div class="strategy-card" onclick="openStrategyModal('${s.id}')"><b>${s.name}</b><p>${s.desc}</p></div>`).join('')}</div>`}</div>`;$('strategy-modal').classList.add('open');}
function strategyDetail(s){const url=s.url||s.learn_url||'#';return `<p>${s.desc}</p><p><b>Builder:</b> ${s.builder||s.built_by||'KiteBot research desk'}</p><p><b>Risk:</b> ${s.risk||'Stops required. No averaging down.'}</p><p><a href="${url}" target="_blank">Learn this strategy</a></p><label>Conviction filter</label><input type="range" min="60" max="90" value="72"><br><br><button class="btn primary" onclick="applyStrategy('${s.id}')">Apply strategy</button>`;}
function closeStrategyModal(){$('strategy-modal').classList.remove('open');}
async function applyStrategy(id){localStorage.setItem('kitebot_strategy',id);await sendAction('apply-strategy',id);closeStrategyModal();}
async function sendAction(action,override){const d=state||{};const base=location.protocol.startsWith('http')?location.origin:(d.terminal_api_base||'');const msg=$('action-msg');if(msg)msg.textContent='Sending...';if(!base){if(msg)msg.textContent='Open the paired terminal URL while RUN_BOT is running.';return;}const symbol=override||selectedSymbol||d.active_symbol||'';try{const r=await fetch(base+'/api/'+action,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol,reason:'ui'})});const out=await r.json();if(msg)msg.textContent=out.ok?(out.message||'Done'):(out.error||'Rejected');await load(true);}catch(e){if(msg)msg.textContent='Action failed: '+e;}}
async function setCapital(){const amount=Number($('capital-input').value||0);await sendRaw('/api/set-capital',{amount});}
async function sendRaw(path,payload){const base=location.protocol.startsWith('http')?location.origin:(state.terminal_api_base||'');const msg=$('action-msg');try{const r=await fetch(base+path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const out=await r.json();if(msg)msg.textContent=out.ok?(out.message||'Done'):(out.error||'Rejected');await load(true);}catch(e){if(msg)msg.textContent='Action failed: '+e;}}
function render(d){state=d||{};if(!selectedSymbol)selectedSymbol=state.active_symbol||((state.watchlist||[])[0]||{}).symbol||'';renderIndices(state);renderWatchlist(state);if(activePage==='dashboard')renderDashboard(state);if(activePage==='orders')renderOrders(state);if(activePage==='holdings')renderHoldings(state);if(activePage==='positions')renderPositions(state);if(activePage==='funds')renderFunds(state);if(activePage==='bids')renderBids(state);if(activePage==='brain')renderBrain(state);}
async function load(force){let d=null;if(location.protocol.startsWith('http'))try{const r=await fetch('/live-coach.json?_='+Date.now(),{cache:'no-store',credentials:'same-origin'});if(r.ok)d=await r.json();}catch(e){}if(d)state=d;window.KITEBOT_LAST=state;render(state);lastPaint=Date.now();}
document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>setPage(b.dataset.page));document.querySelectorAll('[data-theme-choice]').forEach(b=>b.onclick=()=>setTheme(b.dataset.themeChoice));$('stock-search').oninput=()=>renderWatchlist(state);$('profile-avatar').onclick=()=>openStrategyModal();$('collapse-watch').onclick=()=>document.querySelector('.watch').style.width='260px';
setTheme(localStorage.getItem('kitebot_theme')||'light');render(state);setInterval(load,500);
</script>
</body>
</html>
"""

@dataclass
class CoachState:
    asof:               str = ""
    running_state:      str = "UNKNOWN"      # RUNNING / PAUSED / HALTED / STOPPED
    mode:               str = ""
    active_symbol:      str = ""
    tradingview_url:    str = ""
    active_strategy:    str = ""
    capital_tier:       str = ""
    effective_risk_pct: float = 0.0
    regime:             str = ""
    confidence:         float = 0.0
    stop:               Optional[float] = None
    target:             Optional[float] = None
    realized_pnl:       float = 0.0
    open_positions:     int = 0
    positions:          List[dict] = field(default_factory=list)
    mtf:                List[dict] = field(default_factory=list)
    decisions:          List[dict] = field(default_factory=list)
    leaderboard:        List[dict] = field(default_factory=list)
    chart_series:       List[dict] = field(default_factory=list)
    candles:            List[dict] = field(default_factory=list)
    ema20:              List[dict] = field(default_factory=list)
    ema50:              List[dict] = field(default_factory=list)
    ema200:             List[dict] = field(default_factory=list)
    support_line:       List[dict] = field(default_factory=list)
    resistance_line:    List[dict] = field(default_factory=list)
    price_lines:        List[dict] = field(default_factory=list)
    markers:            List[dict] = field(default_factory=list)
    account:            Dict = field(default_factory=dict)
    watchlist:          List[dict] = field(default_factory=list)
    trades:             List[dict] = field(default_factory=list)
    indices:            List[dict] = field(default_factory=list)
    holdings:           List[dict] = field(default_factory=list)
    trade_attribution:  List[dict] = field(default_factory=list)
    strategy_catalog:   List[dict] = field(default_factory=list)
    brain_notes:        List[str] = field(default_factory=list)
    allowed_symbols:    List[str] = field(default_factory=list)
    bids:               List[dict] = field(default_factory=list)
    next_buys:          List[dict] = field(default_factory=list)
    exchange:           str = ""
    tradingview_widget_url: str = ""
    terminal_api_base:  str = ""


# ── Public API ───────────────────────────────────────────────────────────────
def write_pine_overlay(path: Path = PINE_OVERLAY_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PINE_TEMPLATE, encoding="utf-8")
    return path


def write_pine_strategy(path: Path = PINE_STRATEGY_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PINE_STRATEGY_TEMPLATE, encoding="utf-8")
    return path


def write_live_coach_html(path: Path = LIVE_COACH_HTML,
                          bootstrap: Optional[dict] = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    embedded = json.dumps(bootstrap, default=str) if bootstrap else "null"
    path.write_text(
        HTML_TEMPLATE.replace("__KITEBOT_BOOTSTRAP__", embedded),
        encoding="utf-8",
    )
    return path


def update_live_coach_state(state: CoachState,
                            path: Path = LIVE_COACH_JSON) -> Path:
    """Write the JSON the HTML page polls. Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not state.asof:
            state.asof = datetime.now().isoformat(timespec="seconds")
        payload = asdict(state)
        path.write_text(json.dumps(payload, indent=2, default=str),
                        encoding="utf-8")
        # Also refresh the HTML with an embedded payload. This makes the
        # dashboard work when opened directly from Windows as file://, where
        # browser security may block fetch('live-coach.json').
        write_live_coach_html(path.with_name(LIVE_COACH_HTML.name), payload)
        return path
    except Exception as e:
        log.warning(f"failed to write live-coach.json: {e}")
        return path


def ensure_coach_assets() -> Dict[str, Path]:
    """
    Idempotently create the local coach assets on disk.

    Pine helpers stay available for old tests/manual experiments, but Pine is
    no longer part of the Windows runtime because the operator cannot use it.
    """
    return {"pine": write_pine_overlay(), "html": write_live_coach_html()}
