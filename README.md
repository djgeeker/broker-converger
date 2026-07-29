# broker-converger

**Desired-state convergence for broker orders.** Read before act, one
corrective per cycle, never trust the echo.

Not a backtester, not a strategy library, not a broker client. It is the thin,
boring layer between "my strategy decided something" and "the broker actually
has it" — the layer where order-management bugs live.

```bash
pip install git+https://github.com/djgeeker/broker-converger      # core, zero dependencies
pip install "broker-converger[ib] @ git+https://github.com/djgeeker/broker-converger"   # + Interactive Brokers adapter
```

Not on PyPI yet — install from source.

---

## The problem

Command-style order management accumulates one bug per edge case, because every
writer keeps its own private picture of reality and they drift apart. Three
failure modes show up in every system that talks to a live broker, and they are
all silent:

**1. Duplicates after a restart.** A strategy that re-derives its state from
market data will, correctly, reach the same decision it reached before the
crash. Without a durable record that the decision was already acted on,
"correct" and "duplicate" are the same thing.

**2. Closing someone else's position.** Brokers report one net position per
instrument, unlabelled. When two strategies share an account, sizing a close
off the net closes both.

**3. Silence.** A submit call returns normally, the order is rejected on
arrival, the rejection lands after your process moved on, and nothing anywhere
turns red. A system that only listens for problems cannot detect silence.

These are not exotic. From the trackers of two of the largest open-source
trading projects:

- [NautilusTrader #3176](https://github.com/nautechsystems/nautilus_trader/issues/3176) — *"Duplicate orders created on restart with persistent cache due to position reconciliation"*
- [NautilusTrader #3655](https://github.com/nautechsystems/nautilus_trader/issues/3655) — *"Not able to automatically synchronize manual orders and positions"*
- [hummingbot #7294](https://github.com/hummingbot/hummingbot/issues/7294) — *"Failed Order Events followed by successful fills causing duplicate orders"*

This library is what those three problems look like once you stop patching them
one at a time.

---

## The idea

Stop sending commands. Every cycle, state what the broker **should** look like,
read what it **does** look like, and emit **at most one** correction.

A desired state has no memory, so it cannot drift. Crash recovery stops being a
special code path and becomes "the next cycle".

```python
from broker_converger import DesiredOrder, DesiredState, plan

snapshot = read_the_broker()                # raise if the read fails
desired  = my_strategy_to_desired_state()   # the only function you write
action   = plan(desired=desired, snapshot=snapshot, price_tick=0.25)

if action is not None:
    actuators[action.kind](action)          # your order code, unchanged
```

`plan` is pure — no IO, no clock, no broker. You can enumerate its entire input
space in a unit test, which is what you want from the code that decides whether
real money moves.

---

## The ladder

Rungs run in order of least-acceptable state. Each returns immediately, which
is what makes "one corrective per cycle" structural rather than aspirational:

| # | rung | fires when |
|---|------|-----------|
| 1 | **protection** | holding a position with no protective order — repaired before every other difference, however many exist |
| 2 | **exit** | strategy wants out — closes **its own** quantity, never the account's |
| 3 | **cancel** | strategy wants its resting orders gone — never touches protective orders |
| 4 | **place** | reserved but not yet sent — idempotent via your submission tag |
| 5 | **reprice** | a price differs by more than half a tick |

`None` means converged, and that should be the answer almost every cycle.

---

## What you get

| module | what it solves |
|--------|----------------|
| `ladder` | the five rungs, as one pure function |
| `ownership` | which part of the account's net position is mine (failure #2) |
| `outbox` | reserve-before-send, so a crash cannot duplicate a decision (failure #1) |
| `verification` | ask the broker whether the order you "sent" actually exists (failure #3) |
| `fills` | quantity-weighted average fill price, with partials as the normal case |
| `ib` | optional read-only Interactive Brokers adapter |

Placing orders stays in **your** code. Order construction is where
instrument- and strategy-specific detail lives, and a generic order builder
fits nobody. This library tells you which single action to take; how to say it
to the broker is yours.

That also means it **composes** with whatever you already run — NautilusTrader,
pysystemtrade, or your own loop — instead of replacing it.

---

## Try it

```bash
git clone https://github.com/djgeeker/broker-converger
cd broker-converger
PYTHONPATH=src python3 examples/minimal_leg.py
```

The fake broker in that example is deliberately hostile: it accepts your order
and then reports failure. Output:

```
cycle 1: place_bracket (reserved_not_yet_placed) slot='entry'
           broker echoed 'ERROR: submit failed' — ignored, next read decides
cycle 2: converged
cycle 3: modify_limit (desired_price_changed) slot='entry'
cycle 4: converged

Exactly one entry despite the failed echo — the next cycle found it by ref.
```

Tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

---

## Three rules worth internalising

**Read before act.** If the snapshot could not be read, do nothing this cycle.
"I don't know" is not "there is nothing there" — and an empty snapshot from a
failed read looks exactly like a flat account.

**One corrective per cycle.** Send it, stop, and let the next cycle's fresh read
tell you whether it worked. The return type enforces this; you cannot express
two orders in one pass.

**Never trust the echo.** A submit call's return value belongs in your logs and
nowhere else. Clients do misreport — a fully filled order can come back marked
cancelled with zero filled quantity, and acting on that echo puts you naked in
the market.

---

## Status

`0.1.0`. Extracted from a live futures system where each of the three failure
modes above happened for real. The core is dependency-free and pure; the IB
adapter is optional and read-only.

Issues and PRs welcome — particularly adapters for other brokers, since the
core was designed to make that a small job.

MIT licensed.

---

## 中文说明

**给券商订单做"期望态收敛"**：先读后动、一轮一单、不信回显。

它不是回测框架，不是策略库，也不是券商客户端。它是"策略做了决定"和"券商真的
有这张单"之间那薄薄的一层 —— 而订单管理的 bug 全住在这一层。

三种沉默的失败：

1. **重启后重复下单** —— 策略从行情重新推导状态，会正确地得出和崩溃前一样的
   决定。没有一份"这个决定已经执行过"的持久记录时，"正确"和"重复"是同一件事。
2. **平掉别人的仓** —— 券商只报一个净持仓且不带归属标签。两条策略共用账户时，
   按净头寸算平仓量就是把两边一起平掉。
3. **静默** —— 提交调用正常返回、订单在券商侧被拒、拒绝回报在你的进程走远之后
   才到，全系统没有一处变红。**只监听"出错"的系统，检测不到"沉默"。**

上面三个 NautilusTrader / hummingbot 的 issue 链接是同一批问题的公开证据 ——
不是没人想到，是真的难。

用法就是每轮说清楚"券商**应该**长什么样"，读一次"**实际**长什么样"，
最多发**一张**纠偏单。期望态没有记忆，所以不会漂；崩溃恢复不再是一条特殊路径，
它就是下一轮。

**下单仍然写在你自己的代码里** —— 订单构造是最吃品种和策略细节的地方，通用的
订单构造器谁都不合适。这层只告诉你"这一轮该动哪一个"。也正因如此，它能和你
已经在跑的东西（NautilusTrader、pysystemtrade、或你自己的循环）**共存**，
而不是取代。
