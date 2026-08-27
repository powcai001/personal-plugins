# health-reminder 插件实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一个 Claude Code 插件：定时（默认 45m）在会话内提醒用户站起来、喝水、伸懒腰（状态栏倒计时 + Stop 横幅），零模型调用、零后台进程。

**Architecture:** "墙上时钟"模型——状态文件只存起点/间隔/last_ack/paused，是否到期由当前时间纯计算得出。三个薄入口（CLI / Stop hook / statusline 包装器）共享一个 `health_lib.py`；提醒展示全部在 Claude Code 会话内完成。

**Tech Stack:** python3（仅标准库：json/os/re/time/fcntl/tempfile/subprocess/argparse），Claude Code 插件机制（plugin.json / commands / hooks / statusline）。

## Global Constraints

- 仅 python3 标准库，零第三方依赖；兼容 python3.6+（f-string 可用即可）
- 零后台进程、零模型调用：`/health` 命令经 `!` bash 直通 CLI；hook 只读写状态文件
- 运行时脚本**不得硬编码 `/home/plugin`**（插件会被复制到 `~/.claude/plugins/cache/...` 安装，路径只能来自 `__file__` / `$CLAUDE_PLUGIN_ROOT` / 环境变量）
- 用户可见文案一律中文；文件 UTF-8
- 状态目录：默认 `~/.local/state/health-reminder/`，可用环境变量 `HEALTH_STATE_DIR` 覆盖（测试用）
- hook 与 statusline 任何内部异常都必须静默降级（exit 0 / 透传原状态栏），绝不阻塞会话
- 每个 Task 完成即 commit；测试为一份无框架断言脚本 `tests/test_health_lib.py`，`python3 tests/test_health_lib.py` 运行，退出码 0/1

---

### Task 1: 仓库与插件脚手架

**Files:**
- Create: `.claude-plugin/marketplace.json`
- Create: `plugins/health-reminder/.claude-plugin/plugin.json`
- Create: `plugins/health-reminder/README.md`（骨架，Task 6 补全）
- Create: `.gitignore`

**Interfaces:**
- Consumes: 无
- Produces: marketplace 名 `personal-plugins`；插件名 `health-reminder`，版本 `0.1.0`，源路径 `./plugins/health-reminder`（后续任务与 README 引用这些名字）

- [ ] **Step 1: 创建目录与文件**

```
/home/plugin/.claude-plugin/marketplace.json
/home/plugin/plugins/health-reminder/.claude-plugin/plugin.json
/home/plugin/plugins/health-reminder/README.md
/home/plugin/.gitignore
```

`.claude-plugin/marketplace.json`：

```json
{
  "name": "personal-plugins",
  "owner": { "name": "plugin-dev" },
  "plugins": [
    {
      "name": "health-reminder",
      "source": "./plugins/health-reminder",
      "description": "定时提醒站起来、喝水、伸懒腰（状态栏倒计时 + 会话内横幅）",
      "category": "health"
    }
  ]
}
```

`plugins/health-reminder/.claude-plugin/plugin.json`：

```json
{
  "name": "health-reminder",
  "version": "0.1.0",
  "description": "定时提醒站起来、喝水、伸懒腰：状态栏倒计时 + Stop 横幅，零模型调用",
  "author": { "name": "plugin-dev" }
}
```

`README.md`（骨架）：

```markdown
# health-reminder

定时提醒站起来、喝水、伸懒腰。提醒只在 Claude Code 会话内可见：状态栏倒计时 + 对话横幅。

（用法与原理待补）
```

`.gitignore`：

```
claude-pet/
```

- [ ] **Step 2: 校验 JSON 合法**

Run: `python3 -m json.tool .claude-plugin/marketplace.json && python3 -m json.tool plugins/health-reminder/.claude-plugin/plugin.json`
Expected: 两个 JSON 原样打印，无报错

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin plugins/health-reminder .gitignore
git commit -m "feat: health-reminder 插件脚手架（marketplace + plugin.json）"
```

---

### Task 2: health_lib 核心（状态 + 时间逻辑）

**Files:**
- Create: `plugins/health-reminder/scripts/health_lib.py`
- Test: `plugins/health-reminder/tests/test_health_lib.py`

**Interfaces:**
- Consumes: 无（纯标准库）
- Produces（后续所有任务依赖，签名固定）:
  - `DEFAULT_INTERVAL_S = 2700`
  - `state_dir() -> str`（读 `HEALTH_STATE_DIR` 环境变量，默认 `~/.local/state/health-reminder`）
  - `state_path() -> str`
  - `valid_state(s) -> bool`
  - `load_state(path=None) -> dict | None`（缺失/损坏/非法 → None）
  - `save_state(s, path=None)`（临时文件 + `os.replace` 原子写，自动建目录）
  - `state_lock()`（contextmanager，flock `state.lock`）
  - `parse_interval(text) -> int`（`"45m"/"1h"/"10s"/"45"`→秒；非法/非正抛 `ValueError`）
  - `fmt_remaining(remaining_s) -> str`（分钟向上取整：`"32m"`、`"1h05m"`，最小 `1m`）
  - `fmt_duration(s) -> str`（`"10s"`、`"45m"`、`"1h30m"`）
  - `compute(s, now) -> dict`：`{"running": True, "paused": bool, "due": bool, "remaining_s": int, "missed": int}`；`missed = floor((now-last_ack)/interval_s)`，仅 due 时 ≥1，否则 0；paused 时 remaining 冻结为 `last_ack + interval_s - paused_at`
  - `do_ack(s, now) -> dict`（`last_ack = now`）
  - `do_pause(s, now) -> dict`（记 `paused_at`；已暂停则原样返回）
  - `do_resume(s, now) -> dict`（`last_ack += now - paused_at`；未暂停原样返回）
  - `banner_text(c) -> str`（`"⏰ 站起来喝水伸懒腰！"`；`missed>1` 追加 `"（期间错过了 {missed-1} 次提醒）"`）

- [ ] **Step 1: 写失败测试**

`tests/test_health_lib.py`（此文件后续任务继续追加 test_ 函数）：

```python
#!/usr/bin/env python3
"""health-reminder 测试（无框架断言脚本）。运行: python3 tests/test_health_lib.py"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)

import health_lib  # noqa: E402

FAILURES = []


def run_test(fn):
    try:
        fn()
        print("  PASS %s" % fn.__name__)
    except Exception as e:  # noqa: BLE001
        FAILURES.append(fn.__name__)
        print("  FAIL %s: %s" % (fn.__name__, e))


def tmp_env():
    d = tempfile.mkdtemp(prefix="health-test-")
    return d, dict(os.environ, HEALTH_STATE_DIR=d)


def make_state(last_ack=1000, interval=600, paused=False, paused_at=None):
    return {"started_at": 1000, "interval_s": interval, "last_ack": last_ack,
            "paused": paused, "paused_at": paused_at}


def test_parse_interval():
    assert health_lib.parse_interval("45m") == 2700
    assert health_lib.parse_interval("1h") == 3600
    assert health_lib.parse_interval("10s") == 10
    assert health_lib.parse_interval("45") == 2700  # 裸数字=分钟


def test_parse_interval_invalid():
    for bad in ("1x", "0m", "-5m", "abc", ""):
        try:
            health_lib.parse_interval(bad)
        except ValueError:
            continue
        raise AssertionError("应当抛 ValueError: %r" % bad)


def test_state_roundtrip_and_atomic():
    d, _ = tmp_env()
    p = os.path.join(d, "state.json")
    s = make_state()
    health_lib.save_state(s, p)
    loaded = health_lib.load_state(p)
    assert loaded == s
    leftovers = [f for f in os.listdir(d) if f.endswith(".tmp")]
    assert leftovers == [], "不应残留临时文件: %s" % leftovers


def test_load_invalid_returns_none():
    d, _ = tmp_env()
    p = os.path.join(d, "state.json")
    with open(p, "w") as f:
        f.write("{ not json")
    assert health_lib.load_state(p) is None
    with open(p, "w") as f:
        json.dump({"started_at": 1}, f)  # 缺字段
    assert health_lib.load_state(p) is None
    assert health_lib.load_state(os.path.join(d, "none.json")) is None


def test_compute_not_due():
    c = health_lib.compute(make_state(last_ack=1000, interval=600), now=1599)
    assert c["due"] is False and c["missed"] == 0 and c["remaining_s"] == 1


def test_compute_due_and_missed():
    c = health_lib.compute(make_state(last_ack=1000, interval=600), now=1600)
    assert c["due"] is True and c["missed"] == 1 and c["remaining_s"] == 0
    c = health_lib.compute(make_state(last_ack=1000, interval=600), now=2800)
    assert c["due"] is True and c["missed"] == 3


def test_compute_paused_freezes():
    s = make_state(last_ack=1000, interval=600, paused=True, paused_at=1500)
    c = health_lib.compute(s, now=99999)
    assert c["paused"] is True and c["due"] is False
    assert c["remaining_s"] == 100  # 1000+600-1500，与 now 无关


def test_ack_pause_resume_shift():
    s = make_state(last_ack=1000, interval=600)
    s = health_lib.do_pause(s, now=1200)
    s = health_lib.do_resume(s, now=2000)
    assert s["last_ack"] == 1800 and s["paused"] is False and s["paused_at"] is None
    c = health_lib.compute(s, now=2300)
    assert c["due"] is False and c["remaining_s"] == 100
    assert health_lib.compute(s, now=2400)["due"] is True
    s = health_lib.do_ack(s, now=2400)
    assert health_lib.compute(s, now=2400)["due"] is False


def test_banner_text():
    c = {"running": True, "paused": False, "due": True, "remaining_s": 0, "missed": 1}
    assert health_lib.banner_text(c) == "⏰ 站起来喝水伸懒腰！"
    c["missed"] = 3
    assert "错过了 2 次提醒" in health_lib.banner_text(c)


def test_fmt_helpers():
    assert health_lib.fmt_remaining(0) == "1m"
    assert health_lib.fmt_remaining(59) == "1m"
    assert health_lib.fmt_remaining(1920) == "32m"
    assert health_lib.fmt_remaining(3900) == "1h05m"
    assert health_lib.fmt_duration(10) == "10s"
    assert health_lib.fmt_duration(2700) == "45m"
    assert health_lib.fmt_duration(5400) == "1h30m"


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items())
              if k.startswith("test_") and callable(v)]
    for _t in _tests:
        run_test(_t)
    print("\n%d/%d 通过" % (len(_tests) - len(FAILURES), len(_tests)))
    sys.exit(1 if FAILURES else 0)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd plugins/health-reminder && python3 tests/test_health_lib.py`
Expected: FAIL（`ModuleNotFoundError: No module named 'health_lib'`）

- [ ] **Step 3: 实现 health_lib.py**

```python
#!/usr/bin/env python3
"""health-reminder 共享库：状态存取（原子+flock）、到期计算、间隔解析。

被三个薄入口复用：health（CLI）/ health_hook（Stop hook）/ health_statusline。
"""
import fcntl
import json
import math
import os
import re
import tempfile
import time
from contextlib import contextmanager

DEFAULT_INTERVAL_S = 45 * 60


def state_dir():
    return os.path.expanduser(
        os.environ.get("HEALTH_STATE_DIR", "~/.local/state/health-reminder"))


def state_path():
    return os.path.join(state_dir(), "state.json")


def valid_state(s):
    if not isinstance(s, dict):
        return False
    try:
        for k in ("started_at", "interval_s", "last_ack"):
            int(s[k])
        if not isinstance(s.get("paused"), bool):
            return False
        if s.get("paused_at") is not None:
            int(s["paused_at"])
        if int(s["interval_s"]) <= 0:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def load_state(path=None):
    path = path or state_path()
    try:
        with open(path, encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        return None
    return s if valid_state(s) else None


@contextmanager
def state_lock():
    d = state_dir()
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "state.lock"), "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def save_state(s, path=None):
    path = path or state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path),
                               prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


_UNIT = {"s": 1, "m": 60, "h": 3600}


def parse_interval(text):
    m = re.fullmatch(r"(\d+)([smh]?)", str(text).strip().lower())
    if not m:
        raise ValueError("无法识别的间隔: %r（示例: 45m / 1h / 10s）" % text)
    secs = int(m.group(1)) * _UNIT[m.group(2) or "m"]
    if secs <= 0:
        raise ValueError("间隔必须为正数")
    return secs


def fmt_remaining(remaining_s):
    m = max(1, int(math.ceil(remaining_s / 60.0)))
    if m >= 60:
        return "%dh%02dm" % (m // 60, m % 60)
    return "%dm" % m


def fmt_duration(s):
    if s >= 3600:
        return "%dh%02dm" % (s // 3600, (s % 3600) // 60)
    if s >= 60:
        return "%dm" % s // 60
    return "%ds" % s


def compute(s, now):
    interval = s["interval_s"]
    if s.get("paused"):
        frozen = s.get("paused_at") or now
        return {"running": True, "paused": True, "due": False, "missed": 0,
                "remaining_s": max(0, s["last_ack"] + interval - frozen)}
    due_at = s["last_ack"] + interval
    due = now >= due_at
    missed = (now - s["last_ack"]) // interval if due else 0
    return {"running": True, "paused": False, "due": due, "missed": missed,
            "remaining_s": max(0, due_at - now)}


def do_ack(s, now):
    s = dict(s)
    s["last_ack"] = int(now)
    return s


def do_pause(s, now):
    if s.get("paused"):
        return s
    s = dict(s)
    s["paused"] = True
    s["paused_at"] = int(now)
    return s


def do_resume(s, now):
    if not s.get("paused"):
        return s
    s = dict(s)
    s["last_ack"] = s["last_ack"] + (int(now) - s["paused_at"])
    s["paused"] = False
    s["paused_at"] = None
    return s


def banner_text(c):
    msg = "⏰ 站起来喝水伸懒腰！"
    if c["missed"] > 1:
        msg += "（期间错过了 %d 次提醒）" % (c["missed"] - 1)
    return msg
```

- [ ] **Step 4: 运行确认全部通过**

Run: `cd plugins/health-reminder && python3 tests/test_health_lib.py`
Expected: `10/10 通过`，退出码 0

- [ ] **Step 5: Commit**

```bash
git add plugins/health-reminder/scripts/health_lib.py plugins/health-reminder/tests/test_health_lib.py
git commit -m "feat: health_lib 状态与到期计算（原子写+flock，墙上时钟模型）"
```

---

### Task 3: CLI 入口 `health`

**Files:**
- Create: `plugins/health-reminder/scripts/health`
- Modify: `plugins/health-reminder/scripts/health_lib.py`（追加 `cmd_*` 与 `main_cli`）
- Test: `plugins/health-reminder/tests/test_health_lib.py`（追加 CLI 测试）

**Interfaces:**
- Consumes: Task 2 的全部函数
- Produces: `health_lib.main_cli(argv=None) -> int`（退出码：0 正常 / 2 用法错误）；子命令 `start [interval] / pause / resume / stop / status / ack`；`scripts/health` 为可执行薄入口。输出为一行中文。`start` 缺省间隔 = 现有状态的 interval_s，否则 45m；无参数 = status

- [ ] **Step 1: 追加失败测试（test_health_lib.py 末尾、`if __name__` 块之前）**

```python
def run_cli(args, env):
    r = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "health")] + args,
        capture_output=True, text=True, env=env, timeout=10)
    return r.returncode, r.stdout.strip()


def test_cli_lifecycle():
    d, env = tmp_env()
    rc, out = run_cli(["start", "10s"], env)
    assert rc == 0 and "已启动" in out and "10s" in out
    with open(os.path.join(d, "state.json")) as f:
        assert json.load(f)["interval_s"] == 10
    rc, out = run_cli(["status"], env)
    assert rc == 0 and "下次提醒" in out
    rc, out = run_cli(["pause"], env)
    assert rc == 0 and "暂停" in out
    rc, out = run_cli(["status"], env)
    assert "已暂停" in out
    rc, out = run_cli(["resume"], env)
    assert rc == 0 and "已恢复" in out
    rc, out = run_cli(["stop"], env)
    assert rc == 0 and "已停止" in out
    assert not os.path.exists(os.path.join(d, "state.json"))
    rc, out = run_cli(["status"], env)
    assert "未启用" in out


def test_cli_no_args_is_status():
    _, env = tmp_env()
    rc, out = run_cli([], env)
    assert rc == 0 and "未启用" in out


def test_cli_start_default_interval():
    d, env = tmp_env()
    rc, out = run_cli(["start"], env)
    assert rc == 0 and "45m" in out
    with open(os.path.join(d, "state.json")) as f:
        assert json.load(f)["interval_s"] == 2700
    run_cli(["stop"], env)
    rc, out = run_cli(["start", "10s"], env)
    run_cli(["stop"], env)  # stop 后无历史 → 回默认
    rc, out = run_cli(["start"], env)
    assert "45m" in out


def test_cli_reuses_running_interval():
    d, env = tmp_env()
    run_cli(["start", "10s"], env)
    run_cli(["start"], env)  # 运行中缺省 → 沿用 10s
    with open(os.path.join(d, "state.json")) as f:
        assert json.load(f)["interval_s"] == 10


def test_cli_bad_interval_exit_2():
    _, env = tmp_env()
    rc, out = run_cli(["start", "xx"], env)
    assert rc == 2 and "无法识别" in out


def test_cli_pause_resume_without_state():
    _, env = tmp_env()
    rc, out = run_cli(["pause"], env)
    assert rc == 0 and "未在运行" in out
    rc, out = run_cli(["ack"], env)
    assert rc == 0 and "未在运行" in out
```

- [ ] **Step 2: 运行确认新测试失败**

Run: `cd plugins/health-reminder && python3 tests/test_health_lib.py`
Expected: 新增的 6 个 CLI 测试 FAIL（`No such file or directory: …/scripts/health`），原 11 个仍 PASS

- [ ] **Step 3: 实现 CLI**

`scripts/health`（可执行）：

```python
#!/usr/bin/env python3
"""health CLI 薄入口——真正逻辑在 health_lib.main_cli。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import health_lib  # noqa: E402

if __name__ == "__main__":
    sys.exit(health_lib.main_cli())
```

`chmod +x scripts/health`

`health_lib.py` 末尾追加：

```python
# ---------------- CLI ----------------

def _msg_not_running():
    return "当前未在运行（/health start 45m 开始）"


def cmd_start(interval_arg, now):
    interval = None
    if interval_arg is not None:
        try:
            interval = parse_interval(interval_arg)
        except ValueError as e:
            print(e)
            return 2
    with state_lock():
        prev = load_state()
        if interval is None:
            interval = prev["interval_s"] if prev else DEFAULT_INTERVAL_S
        save_state({"started_at": now, "interval_s": interval,
                    "last_ack": now, "paused": False, "paused_at": None})
    print("✅ 已启动：每 %s 提醒一次（状态栏可见倒计时）" % fmt_duration(interval))
    return 0


def cmd_pause(now):
    with state_lock():
        s = load_state()
        if not s:
            print(_msg_not_running())
            return 0
        if s.get("paused"):
            print("⏸ 已处于暂停状态")
            return 0
        save_state(do_pause(s, now))
    print("⏸ 已暂停（resume 恢复）")
    return 0


def cmd_resume(now):
    with state_lock():
        s = load_state()
        if not s:
            print(_msg_not_running())
            return 0
        if not s.get("paused"):
            print("▶ 本来就在运行中")
            return 0
        s = do_resume(s, now)
        save_state(s)
    c = compute(s, now)
    print("▶ 已恢复，下次提醒还有 %s" % fmt_remaining(c["remaining_s"]))
    return 0


def cmd_stop():
    with state_lock():
        if os.path.exists(state_path()):
            os.unlink(state_path())
            print("🛑 已停止并清除状态")
            return 0
    print(_msg_not_running())
    return 0


def cmd_ack(now):
    with state_lock():
        s = load_state()
        if not s:
            print(_msg_not_running())
            return 0
        save_state(do_ack(s, now))
    print("👌 已确认，重新开始计时")
    return 0


def cmd_status(now):
    s = load_state()
    if not s:
        print("未启用：/health start 45m 开始")
        return 0
    c = compute(s, now)
    if c["paused"]:
        print("⏸ 已暂停（还剩 %s，resume 恢复）" % fmt_remaining(c["remaining_s"]))
    elif c["due"]:
        extra = "，错过了 %d 次" % (c["missed"] - 1) if c["missed"] > 1 else ""
        print("🚨 该提醒啦：站起来喝水伸懒腰%s" % extra)
    else:
        print("💧 下次提醒还有 %s（每 %s 一次）"
              % (fmt_remaining(c["remaining_s"]), fmt_duration(s["interval_s"])))
    return 0


def main_cli(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="health",
                                description="健康提醒：站起来、喝水、伸懒腰")
    sub = p.add_subparsers(dest="cmd")
    sp = sub.add_parser("start", help="开始提醒（默认 45m，可传 30m / 1h / 10s）")
    sp.add_argument("interval", nargs="?", default=None)
    for name, text in (("pause", "暂停"), ("resume", "恢复"),
                       ("stop", "停止并清除"), ("status", "查看状态"),
                       ("ack", "手动确认提醒")):
        sub.add_parser(name, help=text)
    args = p.parse_args(argv)
    now = int(time.time())
    table = {
        "start": lambda: cmd_start(args.interval, now),
        "pause": lambda: cmd_pause(now),
        "resume": lambda: cmd_resume(now),
        "stop": cmd_stop,
        "ack": lambda: cmd_ack(now),
        "status": lambda: cmd_status(now),
    }
    return table.get(args.cmd or "status", lambda: cmd_status(now))()
```

- [ ] **Step 4: 运行确认全部通过**

Run: `cd plugins/health-reminder && python3 tests/test_health_lib.py`
Expected: `16/16 通过`

- [ ] **Step 5: Commit**

```bash
git add plugins/health-reminder/scripts/health plugins/health-reminder/scripts/health_lib.py plugins/health-reminder/tests/test_health_lib.py
git commit -m "feat: health CLI（start/pause/resume/stop/status/ack）"
```

---

### Task 4: Stop hook

**Files:**
- Create: `plugins/health-reminder/scripts/health_hook`
- Create: `plugins/health-reminder/hooks/hooks.json`
- Test: `plugins/health-reminder/tests/test_health_lib.py`（追加）

**Interfaces:**
- Consumes: `load_state / save_state / state_lock / compute / do_ack / banner_text`（Task 2）
- Produces: `health_lib.main_hook() -> int`（恒 0）；到期时 stdout 打印 `{"systemMessage": "⏰ …"}` 并 ack；其余情况无输出。`hooks.json` 挂 Stop 事件，命令 `python3 "$CLAUDE_PLUGIN_ROOT/scripts/health_hook"`

- [ ] **Step 1: 追加失败测试**

```python
def run_hook(env, stdin='{"session_id":"t"}'):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "health_hook")],
                       input=stdin, capture_output=True, text=True, env=env,
                       timeout=10)
    return r.returncode, r.stdout.strip()


def write_state(d, **kw):
    s = make_state(**kw)
    with open(os.path.join(d, "state.json"), "w") as f:
        json.dump(s, f)
    return s


def test_hook_due_banners_and_acks():
    d, env = tmp_env()
    # last_ack=1000, interval=600；now 远大于 1600 → due, missed 巨大
    write_state(d)
    rc, out = run_hook(env)
    assert rc == 0 and "站起来喝水伸懒腰" in out and "systemMessage" in out
    with open(os.path.join(d, "state.json")) as f:
        s = json.load(f)
    assert s["last_ack"] > 1000  # 已 ack
    rc, out = run_hook(env)      # 幂等：第二次不再横幅
    assert rc == 0 and out == ""


def test_hook_silent_when_not_due_or_absent():
    d, env = tmp_env()
    rc, out = run_hook(env)      # 无状态
    assert rc == 0 and out == ""
    write_state(d, paused=True, paused_at=1000)  # 暂停中
    rc, out = run_hook(env)
    assert rc == 0 and out == ""
```

- [ ] **Step 2: 运行确认失败**

Run: `cd plugins/health-reminder && python3 tests/test_health_lib.py`
Expected: 新增 2 个测试 FAIL（找不到 `scripts/health_hook`），其余 PASS

- [ ] **Step 3: 实现 hook 与 hooks.json**

`scripts/health_hook`（可执行）：

```python
#!/usr/bin/env python3
"""Stop hook：到期则横幅提醒并 ack；任何异常静默退出 0。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import health_lib  # noqa: E402


def main_hook():
    try:
        sys.stdin.read()  # 丢弃 hook 输入
    except Exception:  # noqa: BLE001
        pass
    try:
        now = int(time.time())
        with health_lib.state_lock():
            s = health_lib.load_state()
            if not s:
                return 0
            c = health_lib.compute(s, now)
            if not c["due"]:
                return 0
            health_lib.save_state(health_lib.do_ack(s, now))
        print(json.dumps({"systemMessage": health_lib.banner_text(c)},
                         ensure_ascii=False))
    except Exception:  # noqa: BLE001  hook 绝不阻塞会话
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main_hook())
```

`chmod +x scripts/health_hook`

`hooks/hooks.json`：

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PLUGIN_ROOT/scripts/health_hook\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: 运行确认全部通过**

Run: `cd plugins/health-reminder && python3 tests/test_health_lib.py && python3 -m json.tool hooks/hooks.json`
Expected: `18/18 通过`；hooks.json 打印无错

- [ ] **Step 5: Commit**

```bash
git add plugins/health-reminder/scripts/health_hook plugins/health-reminder/hooks/hooks.json plugins/health-reminder/tests/test_health_lib.py
git commit -m "feat: Stop hook 到期横幅提醒（幂等 ack，异常静默）"
```

---

### Task 5: statusline 包装器与 setup

**Files:**
- Create: `plugins/health-reminder/scripts/health_statusline`
- Modify: `plugins/health-reminder/scripts/health_lib.py`（追加 `settings_path/backup_path/cmd_setup`，`main_cli` 注册 `setup`）
- Test: `plugins/health-reminder/tests/test_health_lib.py`（追加）

**Interfaces:**
- Consumes: Task 2/3 全部
- Produces:
  - `health_lib.main_statusline() -> int`；`health_lib.segment(state, now=None) -> str`（未启用→`""`；正常→`" \x1b[90m💧 32m\x1b[0m"`；到期→红底 `" \x1b[41;97m 🚨 站起来·喝水·伸懒腰 \x1b[0m"`；暂停→黄色 `⏸`）
  - `health_lib.settings_path() -> str`（`~/.claude/settings.json`）
  - `health_lib.backup_path() -> str`（`<state_dir>/statusline_backup.json`，内容 `{"statusLine": <原配置或null>}`）
  - `health_lib.cmd_setup(remove=False) -> int`；CLI 新子命令 `setup [--remove]`
  - 包装器命令写死为 `python3 <脚本所在目录>/health_statusline`（来自 `__file__`，装到 cache 也正确）

- [ ] **Step 1: 追加失败测试**

```python
ESC = "\x1b"


def run_statusline(env, stdin=b'{"model":{"display_name":"t"}}'):
    r = subprocess.run([sys.executable,
                        os.path.join(SCRIPTS, "health_statusline")],
                       input=stdin, capture_output=True, env=env, timeout=10)
    return r.returncode, r.stdout.decode("utf-8", "replace").strip()


def write_backup(d, cmd):
    with open(os.path.join(d, "statusline_backup.json"), "w") as f:
        json.dump({"statusLine": {"type": "command", "command": cmd}}, f)


def test_statusline_appends_segment():
    d, env = tmp_env()
    write_backup(d, "echo BASE")
    rc, out = run_statusline(env)
    assert rc == 0 and out.startswith("BASE") and "💧" in out
    write_state(d)  # last_ack=1000, interval=600 → now 必 due
    rc, out = run_statusline(env)
    assert "🚨" in out and "站起来" in out and "BASE" in out
    write_state(d, paused=True, paused_at=1000)
    rc, out = run_statusline(env)
    assert "⏸" in out


def test_statusline_degrades():
    d, env = tmp_env()
    write_backup(d, "echo BASE")
    rc, out = run_statusline(env)   # 无状态 → 只有原样输出
    assert rc == 0 and out == "BASE"
    write_state(d)
    with open(os.path.join(d, "statusline_backup.json"), "w") as f:
        f.write("broken")           # 备份损坏 → 只有健康段，不崩
    rc, out = run_statusline(env)
    assert rc == 0 and "🚨" in out


def test_setup_install_and_remove():
    d, env = tmp_env()
    home = tempfile.mkdtemp(prefix="health-home-")
    settings = os.path.join(home, ".claude", "settings.json")
    os.makedirs(os.path.dirname(settings))
    with open(settings, "w") as f:
        json.dump({"statusLine": {"type": "command", "command": "powerline x"},
                   "other": 1}, f)
    env2 = dict(env, HOME=home)
    rc, out = run_cli(["setup"], env2)
    assert rc == 0 and "已安装" in out
    with open(settings) as f:
        st = json.load(f)
    assert "health_statusline" in st["statusLine"]["command"]
    assert st["other"] == 1                      # 其他配置不动
    with open(os.path.join(d, "statusline_backup.json")) as f:
        assert json.load(f)["statusLine"]["command"] == "powerline x"
    rc, out = run_cli(["setup"], env2)           # 重复安装不二次包装
    assert rc == 0 and "已在位" in out
    with open(settings) as f:
        assert st["statusLine"] == json.load(f)["statusLine"]
    rc, out = run_cli(["setup", "--remove"], env2)
    assert rc == 0 and "恢复" in out
    with open(settings) as f:
        st2 = json.load(f)
    assert st2["statusLine"]["command"] == "powerline x" and st2["other"] == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd plugins/health-reminder && python3 tests/test_health_lib.py`
Expected: 新增 3 个测试 FAIL（缺 `scripts/health_statusline` 与 setup 子命令），其余 PASS

- [ ] **Step 3: 实现 statusline 与 setup**

`scripts/health_statusline`（可执行）：

```python
#!/usr/bin/env python3
"""statusline 包装器：透传原状态栏，追加健康段；任何异常只输出原结果。"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import health_lib  # noqa: E402

RESET = "\x1b[0m"
DIM = "\x1b[90m"
RED = "\x1b[41;97m"
YELLOW = "\x1b[33m"


def segment(state, now=None):
    if not state:
        return ""
    now = int(time.time()) if now is None else now
    c = health_lib.compute(state, now)
    if c["paused"]:
        return " %s⏸ %s%s" % (YELLOW,
                               health_lib.fmt_remaining(c["remaining_s"]), RESET)
    if c["due"]:
        return " %s 🚨 站起来·喝水·伸懒腰 %s" % (RED, RESET)
    return " %s💧 %s%s" % (DIM,
                           health_lib.fmt_remaining(c["remaining_s"]), RESET)


def original_command():
    try:
        with open(health_lib.backup_path(), encoding="utf-8") as f:
            cfg = json.load(f).get("statusLine")
    except (OSError, ValueError, AttributeError):
        return None
    if isinstance(cfg, dict) and cfg.get("type") == "command" and cfg.get("command"):
        return cfg
    return None


def main_statusline():
    data = sys.stdin.buffer.read()
    base = ""
    try:
        cfg = original_command()
        if cfg:
            r = subprocess.run(cfg["command"], shell=True, input=data,
                               capture_output=True, timeout=5)
            base = r.stdout.decode("utf-8", "replace").strip()
    except Exception:  # noqa: BLE001  原状态栏失败也不能丢
        base = ""
    try:
        seg = segment(health_lib.load_state())
    except Exception:  # noqa: BLE001
        seg = ""
    print((base + seg).strip() if (base or seg) else "")
    return 0


if __name__ == "__main__":
    sys.exit(main_statusline())
```

`chmod +x scripts/health_statusline`

`health_lib.py` 追加：

```python
# ---------------- statusline setup ----------------

def settings_path():
    return os.path.join(os.path.expanduser("~"), ".claude", "settings.json")


def backup_path():
    return os.path.join(state_dir(), "statusline_backup.json")


def cmd_setup(remove=False):
    sp = settings_path()
    try:
        with open(sp, encoding="utf-8") as f:
            settings = json.load(f)
        if not isinstance(settings, dict):
            settings = {}
    except (OSError, ValueError):
        settings = {}
    cur = settings.get("statusLine") or {}
    os.makedirs(state_dir(), exist_ok=True)
    if remove:
        try:
            with open(backup_path(), encoding="utf-8") as f:
                orig = json.load(f).get("statusLine")
        except (OSError, ValueError):
            orig = None
        if orig:
            settings["statusLine"] = orig
            print("✅ 已恢复原状态栏")
        else:
            settings.pop("statusLine", None)
            print("✅ 已移除状态栏包装器")
    else:
        cmd = cur.get("command") or ""
        if "health_statusline" in cmd:
            print("ℹ️ 状态栏包装器已在位，无需重复安装")
            return 0
        wrapper = "python3 " + os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "health_statusline")
        with open(backup_path(), "w", encoding="utf-8") as f:
            json.dump({"statusLine": cur or None}, f, ensure_ascii=False)
        settings["statusLine"] = {"type": "command", "command": wrapper}
        print("✅ 状态栏包装器已安装（原状态栏已备份，setup --remove 可恢复）")
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    return 0
```

`main_cli` 中注册子命令——在 `for name, text in (...)` 循环后加：

```python
    sp = sub.add_parser("setup", help="安装/恢复状态栏包装器")
    sp.add_argument("--remove", action="store_true", help="恢复原状态栏")
```

并把 `table` 字典加一行：

```python
        "setup": lambda: cmd_setup(getattr(args, "remove", False)),
```

- [ ] **Step 4: 运行确认全部通过**

Run: `cd plugins/health-reminder && python3 tests/test_health_lib.py`
Expected: `21/21 通过`

- [ ] **Step 5: 实测包装器开销**

```bash
cd plugins/health-reminder
export HEALTH_STATE_DIR=$(mktemp -d)
echo '{"statusLine":{"type":"command","command":"echo BASE"}}' > "$HEALTH_STATE_DIR/statusline_backup.json"
python3 - <<'PY'
import subprocess, sys, time
t0 = time.time()
for _ in range(10):
    subprocess.run([sys.executable, "scripts/health_statusline"],
                   input=b"{}", capture_output=True)
print("平均 %.0f ms/次" % ((time.time() - t0) / 10 * 1000))
PY
```

Expected: 平均 < 300 ms（python 启动 + shell echo；实际约为 40–80ms + echo 开销）。把实测数字记到 README“性能”一节。若 > 300ms，排查 subprocess 调用链后重测。

- [ ] **Step 6: Commit**

```bash
git add plugins/health-reminder/scripts/health_statusline plugins/health-reminder/scripts/health_lib.py plugins/health-reminder/tests/test_health_lib.py
git commit -m "feat: statusline 包装器与 setup 安装/回滚（异常透传降级）"
```

---

### Task 6: 命令文件与 README

**Files:**
- Create: `plugins/health-reminder/commands/health.md`
- Modify: `plugins/health-reminder/README.md`（补全）

**Interfaces:**
- Consumes: `scripts/health` 全部子命令（Task 3/5）
- Produces: TUI 斜杠命令 `/health …`（bash 直通，零模型调用）；README 为安装与使用文档

- [ ] **Step 1: 写命令文件**

`commands/health.md`：

```markdown
---
description: 健康提醒：定时提醒站起来、喝水、伸懒腰
argument-hint: "[start 45m | pause | resume | stop | status | ack | setup | setup --remove]"
---

!python3 "${CLAUDE_PLUGIN_ROOT}/scripts/health" $ARGUMENTS
```

- [ ] **Step 2: 补全 README**

```markdown
# health-reminder

定时提醒**站起来、喝水、伸懒腰**。提醒只在 Claude Code 会话内可见：

- 状态栏：`💧 32m` 倒计时；到点变红 `🚨 站起来·喝水·伸懒腰`；暂停显示 `⏸`
- 对话横幅：到期后 Claude 答完话时弹 `⏰ 站起来喝水伸懒腰！`（自动确认，长时间未回应会提示错过了几次）

## 安装

```
/plugin marketplace add /home/plugin
/plugin install health-reminder@personal-plugins
```

## 用法

| 命令 | 作用 |
|---|---|
| `/health start 45m` | 开始（间隔支持 30m / 1h / 10s；缺省沿用上次或 45m） |
| `/health pause` / `resume` | 暂停 / 恢复（暂停不吃掉剩余时间） |
| `/health stop` | 停止并清除 |
| `/health status` | 查看状态 |
| `/health ack` | 手动确认，重新计时 |
| `/health setup` | 安装状态栏包装器（包装你现有的 statusline，如 powerline；自动备份） |
| `/health setup --remove` | 恢复原状态栏 |

## 工作原理

"墙上时钟"：`~/.local/state/health-reminder/state.json` 只记 `started_at / interval_s / last_ack / paused`，是否到期由当前时间计算得出。无后台进程、无模型调用——`/health` 直接执行本地 python3 脚本，Stop hook 只读写状态文件。

## 性能

状态栏包装器实测开销：约 ___ ms/次（Task 5 Step 5 实测后填入）。

## 边界与 v2

提醒仅在 Claude Code 会话内可见（不改本地终端配置的前提下实测的最优解）。切到其他窗口且长时间不回来时够不着你。v2 候选：本地终端标签闪烁指引、企业 IM 推送、分动作间隔、历史统计。

状态目录可用 `HEALTH_STATE_DIR` 环境变量覆盖。
```

- [ ] **Step 3: 语法冒烟**

Run: `cd plugins/health-reminder && HEALTH_STATE_DIR=$(mktemp -d) python3 scripts/health start 30s && HEALTH_STATE_DIR=$(mktemp -d) python3 scripts/health && echo '{"session_id":"t"}' | HEALTH_STATE_DIR=$(mktemp -d) python3 scripts/health_hook && echo ok`
Expected: 三行输出分别为 已启动… / 未启用… / （空行或无输出）+ `ok`

- [ ] **Step 4: Commit**

```bash
git add plugins/health-reminder/commands/health.md plugins/health-reminder/README.md
git commit -m "feat: /health 命令文件与 README"
```

---

### Task 7: 安装与端到端验证

**Files:**
- Modify: 无（只验证；若发现问题，修复并追加到对应文件的测试）

**Interfaces:**
- Consumes: 完整插件
- Produces: 安装好的插件 + 验证结论

- [ ] **Step 1: 尝试非交互安装**

```bash
claude plugin marketplace add /home/plugin && claude plugin install health-reminder@personal-plugins
```

Expected: 安装成功。若该子命令在当前版本不存在（报错即知），改用 TUI：提示用户运行 `/plugin marketplace add /home/plugin` 与 `/plugin install health-reminder@personal-plugins`

- [ ] **Step 2: 全量测试最后一跑**

Run: `cd plugins/health-reminder && python3 tests/test_health_lib.py`
Expected: `21/21 通过`

- [ ] **Step 3: TUI 手动验证清单（用户配合）**

逐项确认，每项不符合则回到对应 Task 修复：

1. `/health start 30s` → 回复 `✅ 已启动`
2. 状态栏（若已 `setup`）出现 `💧` 倒计时；未 setup 则跳过此项
3. 等 30s 后发任意一句对话，Claude 答完 → 出现 `⏰ 站起来喝水伸懒腰！` 横幅，且只出现一次（幂等）
4. `/health status` → `💧 下次提醒还有…`（已自动 ack）
5. `/health pause` → status 显示 `⏸ 已暂停`；`resume` 恢复
6. `/health setup` → 状态栏 = 原 powerline 内容 + `💧` 段共存
7. `/health setup --remove` → 状态栏还原
8. `/health stop` → `🛑 已停止`，状态栏健康段消失

- [ ] **Step 4: 收尾提交（如有修复）**

```bash
git add -A ':!claude-pet'
git commit -m "fix: 端到端验证修复" || echo "无需修复，跳过"
```

