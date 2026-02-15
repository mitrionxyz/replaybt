# Gap Protection

## The Problem

In volatile markets, the next bar's open can gap past your stop loss or take profit level. If you always fill at the exact level, you're giving yourself a better price than the market actually offered.

## How replaybt Handles It

The engine checks the bar's **open price first**, before checking high/low:

```
Bar opens
│
├─ Open gapped past SL? → Exit at OPEN (worse fill)
├─ Open gapped past TP? → Exit at OPEN (better fill than expected)
│
├─ Otherwise, check High/Low:
│  ├─ High/Low hit SL? → Exit at SL level
│  └─ High/Low hit TP? → Exit at TP level
│
└─ No exit triggered → position stays open
```

## The 4 Cases

### LONG Position

| Scenario | Exit Price | Reason |
|----------|-----------|--------|
| Open gaps **below** SL | Open price (worse) | `STOP_LOSS_GAP` |
| Low touches SL intra-bar | SL level (exact) | `STOP_LOSS` |
| Open gaps **above** TP | Open price (better) | `TAKE_PROFIT_GAP` |
| High touches TP intra-bar | TP level (exact) | `TAKE_PROFIT` |

### SHORT Position

| Scenario | Exit Price | Reason |
|----------|-----------|--------|
| Open gaps **above** SL | Open price (worse) | `STOP_LOSS_GAP` |
| High touches SL intra-bar | SL level (exact) | `STOP_LOSS` |
| Open gaps **below** TP | Open price (better) | `TAKE_PROFIT_GAP` |
| Low touches TP intra-bar | TP level (exact) | `TAKE_PROFIT` |

## Example

```python
# LONG position entered at $2,000 with SL at $1,930 (3.5%)
# Bar opens at $1,920 (gapped below SL)

# WRONG: exit at $1,930 (the SL level)
# CORRECT: exit at $1,920 (the actual open price — worse fill)
```

## Adverse Slippage on Exits

After determining the exit price, adverse slippage is applied:

- **LONG exit**: price moves **down** (you receive less)
- **SHORT exit**: price moves **up** (you pay more)

```python
# Exit price = $1,920 (gap)
# Slippage = 0.02%
# Actual fill = $1,920 * (1 - 0.0002) = $1,919.62
```

## Why This Matters

Without gap protection, backtests overstate performance on volatile assets. A strategy that shows +50% might actually produce +20% when gap-through exits are properly modeled.

The `exit_breakdown` in results tells you how many exits were gap-triggered:

```python
results = engine.run()
print(results.exit_breakdown)
# {'STOP_LOSS': 15, 'STOP_LOSS_GAP': 3, 'TAKE_PROFIT': 20, 'TAKE_PROFIT_GAP': 1, ...}
```

Gap variants (`_GAP` suffix) are collapsed in the summary display but tracked separately in the raw breakdown.
