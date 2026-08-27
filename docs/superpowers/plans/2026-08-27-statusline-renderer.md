# 状态栏渲染器实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 纯 python3 单行状态栏渲染器替换 npx powerline：模型 / 上下文占比 / git 分支 / 健康倒计时，~40ms 刷新，无花费段。

**Architecture:** 新脚本 `scripts/statusline` 读 stdin JSON，四个独立段函数各自降级（缺数据→隐藏该段），顶层 try/except 保证永不报错；健康段直接复用既有 `health_lib`（同目录 import）。`cmd_setup` 改为安装新渲染器并对老包装器安装做平滑迁移（备份不丢）。

**Tech Stack:** python3 标准库（json/subprocess/sys/os/re），无第三方；无框架断言测试脚本。

## Global Constraints

- 仅 python3 标准库，零第三方依赖；python3.6+ 语法（不用 capture_output= 等 3.7+ 特性，用 stdout=PIPE）
- 运行时脚本不得硬编码 `/home/plugin`（路径只来自 `__file__` / stdin JSON / 环境变量）
- 用户可见文案中文/紧凑符号；文件 UTF-8
- 状态目录与测试环境变量沿用 `HEALTH_STATE_DIR`
- 渲染器任何内部异常都必须降级（隐藏该段或输出空行），绝不让 Claude Code 报错、绝不输出多行
- 输出恰一个换行符结尾（statusline 协议整行）
- 测试为无框架断言脚本，`python3 tests/test_statusline.py` 运行，退出码 0/1；既有 `tests/test_health_lib.py`（22 项）必须始终保持全绿
- 每个 Task 完成即 commit；不用 git add -A（仓库有无关的 claude-pet/ 未跟踪目录）

---

### Task 1: 渲染核心库 statusline_lib（段函数 + 占比计算）

**Files:**
- Create: `plugins/health-reminder/scripts/statusline_lib.py`
- Test: `plugins/health-reminder/tests/test_statusline.py`

**Interfaces:**
- Consumes: 无（纯函数层；不 import health_lib——健康段在 Task 2 的入口脚本里接）
- Produces（Task 2 依赖，签名固定）:
  - `window_for(model_id) -> int`（`1m`（不区分大小写，子串匹配）→ 1000000；其余/None/空 → 200000）
  - `ctx_tokens_from_transcript(path, max_lines=500) -> int | None`（从文件末尾向前扫最多 max_lines 行，取最后一条含 `message.usage` 的记录，返回 `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`；文件缺失/全无 usage/行全损坏 → None；单行 JSON 损坏跳过继续）
  - `bar_pct(tokens, window) -> int`（`round(tokens/window*100)`，window≤0 → 0）
  - `bar(pct) -> str`（`▓`×n + `░`×(10-n)，n = min(10, pct//10)）
  - `pct_color(pct) -> str`（<60 → `"71"`，60≤<85 → `"178"`，≥85 → `"167"`）
  - `model_name(display_name) -> str | None`（小写化；空/None → None）
  - `git_segment(cwd) -> str | ""`（branch 缺失/dirty→`⎇ <branch>✱`；非 git/失败/超时 2s → `""`；青色 `\x1b[36m`，分支后缀 dirty 为红 `\x1b[31m✱\x1b[36m`，段尾 `\x1b[0m`）
  - `ctx_segment(pct) -> str`（` ▓▓░░ 62%`，条与百分数同色，配色见 pct_color，前导空格）
  - `model_segment(name) -> str`（` ✱ opus-5`，白 `\x1b[97m`，段尾复位）
  - `SEP = "\x1b[90m │ \x1b[0m"`

- [ ] **Step 1: 写失败测试 `tests/test_statusline.py`**

```python
#!/usr/bin/env python3
"""statusline 渲染器测试。运行: python3 tests/test_statusline.py"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)

import statusline_lib as sl  # noqa: E402

FAILURES = []


def run_test(fn):
    try:
        fn()
        print("  PASS %s" % fn.__name__)
    except Exception as e:  # noqa: BLE001
        FAILURES.append(fn.__name__)
        print("  FAIL %s: %s" % (fn.__name__, e))


def strip(s):
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def test_window_for():
    assert sl.window_for("claude-opus-5-1m-20261001") == 1000000
    assert sl.window_for("claude-opus-5-1M") == 1000000
    assert sl.window_for("claude-sonnet-5") == 200000
    assert sl.window_for(None) == 200000
    assert sl.window_for("") == 200000


def test_ctx_tokens_from_transcript():
    d = tempfile.mkdtemp(prefix="sl-test-")
    p = os.path.join(d, "t.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"message": {"usage": {
            "input_tokens": 100,
            "cache_read_input_tokens": 200,
            "cache_creation_input_tokens": 50}}}) + "\n")
        f.write(json.dumps({"type": "user", "message": {"role": "user"}}) + "\n")
        f.write("{ broken json\n")
        f.write(json.dumps({"message": {"usage": {
            "input_tokens": 1000,
            "cache_read_input_tokens": 119232,
            "cache_creation_input_tokens": 0}}}) + "\n")
    assert sl.ctx_tokens_from_transcript(p) == 120232  # 取最后一条 usage
    assert sl.ctx_tokens_from_transcript(os.path.join(d, "none.jsonl")) is None
    empty = os.path.join(d, "empty.jsonl")
    open(empty, "w").close()
    assert sl.ctx_tokens_from_transcript(empty) is None


def test_bar_and_pct():
    assert sl.bar_pct(120232, 200000) == 60
    assert sl.bar(60) == "▓▓▓▓▓▓░░░░"
    assert sl.bar(0) == "░░░░░░░░░░"
    assert sl.bar(99) == "▓▓▓▓▓▓▓▓▓░"
    assert sl.bar(120) == "▓▓▓▓▓▓▓▓▓▓"
    assert sl.bar_pct(100000, 0) == 0  # 防除零


def test_pct_color_thresholds():
    assert sl.pct_color(59) == "71"
    assert sl.pct_color(60) == "178"
    assert sl.pct_color(84) == "178"
    assert sl.pct_color(85) == "167"


def test_segments():
    assert sl.model_name("Opus 5") == "opus 5"
    assert sl.model_name(None) is None
    m = sl.model_segment("opus 5")
    assert strip(m) == " ✱ opus 5" and "\x1b[97m" in m and m.endswith("\x1b[0m")
    c = sl.ctx_segment(62)
    assert strip(c) == " ▓▓▓▓▓▓░░░░ 62%" and sl.pct_color(62) in c
    assert sl.ctx_segment(120) and strip(sl.ctx_segment(120)).endswith("120%")


def test_git_segment():
    d = tempfile.mkdtemp(prefix="sl-git-")
    # 非 git 目录 → 空
    assert sl.git_segment(d) == ""
    # init 仓库 → 有分支名
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    seg = sl.git_segment(d)
    assert seg.startswith("\x1b[36m ⎇ ") and "\x1b[0m" in seg
    # dirty → ✱ 后缀
    open(os.path.join(d, "dirty.txt"), "w").close()
    seg2 = sl.git_segment(d)
    assert "✱" in strip(seg2)


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items())
              if k.startswith("test_") and callable(v)]
    for _t in _tests:
        run_test(_t)
    print("\n%d/%d 通过" % (len(_tests) - len(FAILURES), len(_tests)))
    sys.exit(1 if FAILURES else 0)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd plugins/health-reminder && python3 tests/test_statusline.py`
Expected: FAIL（`ModuleNotFoundError: No module named 'statusline_lib'`）

- [ ] **Step 3: 实现 `scripts/statusline_lib.py`**

```python
#!/usr/bin/env python3
"""statusline 渲染段库：纯函数，各自独立降级。被 scripts/statusline 组装。"""
import json
import os
import re
import subprocess

SEP = "\x1b[90m │ \x1b[0m"


def window_for(model_id):
    if model_id and "1m" in model_id.lower():
        return 1000000
    return 200000


def ctx_tokens_from_transcript(path, max_lines=500):
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-max_lines:]
    except OSError:
        return None
    for ln in reversed(lines):
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        u = (d.get("message") or {}).get("usage")
        if isinstance(u, dict):
            total = (u.get("input_tokens") or 0) \
                + (u.get("cache_read_input_tokens") or 0) \
                + (u.get("cache_creation_input_tokens") or 0)
            if total > 0:
                return total
    return None


def bar_pct(tokens, window):
    if window <= 0 or tokens is None or tokens < 0:
        return 0
    return int(round(tokens / float(window) * 100))


def bar(pct):
    n = min(10, max(0, pct // 10))
    return "▓" * n + "░" * (10 - n)


def pct_color(pct):
    if pct < 60:
        return "71"
    if pct < 85:
        return "178"
    return "167"


def model_name(display_name):
    if not display_name or not str(display_name).strip():
        return None
    return str(display_name).strip().lower()


def model_segment(name):
    return " \x1b[97m✱ %s\x1b[0m" % name


def ctx_segment(pct):
    color = pct_color(pct)
    return " \x1b[38;5;%sm%s %d%%\x1b[0m" % (color, bar(pct), pct)


def git_segment(cwd):
    try:
        r = subprocess.run(["git", "branch", "--show-current"], cwd=cwd,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=2)
        branch = r.stdout.decode("utf-8", "replace").strip()
        if r.returncode != 0 or not branch:
            return ""
        dirty = ""
        r2 = subprocess.run(["git", "status", "--porcelain"], cwd=cwd,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=2)
        if r2.returncode == 0 and r2.stdout.strip():
            dirty = "\x1b[31m✱\x1b[36m"
        return " \x1b[36m⎇ %s%s\x1b[0m" % (branch, dirty)
    except Exception:  # noqa: BLE001  git 失败/超时 → 隐藏段
        return ""
```

- [ ] **Step 4: 运行确认全部通过**

Run: `cd plugins/health-reminder && python3 tests/test_statusline.py`
Expected: `7/7 通过`，退出码 0

- [ ] **Step 5: Commit**

```bash
git add plugins/health-reminder/scripts/statusline_lib.py plugins/health-reminder/tests/test_statusline.py
git commit -m "feat: statusline 渲染段库（模型/占比/git 段，各自降级）"
```

---

### Task 2: 入口脚本 scripts/statusline（组装 + 健康段 + 端到端）

**Files:**
- Create: `plugins/health-reminder/scripts/statusline`（可执行）
- Test: `plugins/health-reminder/tests/test_statusline.py`（追加）

**Interfaces:**
- Consumes: Task 1 全部函数；`health_lib.load_state/compute/fmt_remaining`（既有，签名见 tests/test_health_lib.py）；健康段配色沿用 `scripts/health_statusline` 的实现（DIM=`\x1b[90m`、RED=`\x1b[41;97m`、YELLOW=`\x1b[33m`）
- Produces: `main_statusline() -> int`（读 stdin JSON → 打印单行 → 0）；段顺序固定：模型 → 占比 → git → 健康；`git_segment` 的 cwd 取 stdin JSON `workspace.current_dir`；transcript 取 `transcript_path`

- [ ] **Step 1: 追加失败测试（`if __name__` 块之前）**

```python
def make_health_state(**kw):
    import time as _t
    now = int(_t.time())
    s = {"started_at": now - 100, "interval_s": 600, "last_ack": now - 100,
         "paused": False, "paused_at": None}
    s.update(kw)
    return s


def run_sl(env, stdin=b"{}"):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "statusline")],
                       input=stdin, capture_output=True, env=env, timeout=15)
    return r.returncode, r.stdout.decode("utf-8", "replace")


def write_health_state(d, s):
    with open(os.path.join(d, "state.json"), "w") as f:
        json.dump(s, f)


def test_e2e_all_segments():
    d = tempfile.mkdtemp(prefix="sl-e2e-")
    env = dict(os.environ, HEALTH_STATE_DIR=d)
    tp = os.path.join(d, "t.jsonl")
    with open(tp, "w") as f:
        f.write(json.dumps({"message": {"usage": {
            "input_tokens": 124000, "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0}}}) + "\n")
    write_health_state(d, make_health_state())
    stdin = json.dumps({
        "model": {"id": "claude-opus-5", "display_name": "Opus 5"},
        "workspace": {"current_dir": d},
        "transcript_path": tp,
    }).encode()
    rc, out = run_sl(env, stdin)
    plain = strip(out)
    assert rc == 0 and out.count("\n") == 1 and out.endswith("\n")
    assert "✱ opus 5" in plain and "62%" in plain and "💧" in plain
    assert plain.index("opus 5") < plain.index("62%")
    # 非 git 目录 → 无 git 段，但其余段在
    assert "⎇" not in plain


def test_e2e_degrades_to_health_only():
    d = tempfile.mkdtemp(prefix="sl-deg-")
    env = dict(os.environ, HEALTH_STATE_DIR=d)
    rc, out = run_sl(env, b"{ broken")  # stdin JSON 损坏
    assert rc == 0 and strip(out) == ""  # 无健康状态 → 空行；仍恰 1 换行
    write_health_state(d, make_health_state())
    rc, out = run_sl(env, b"{}")         # stdin 无任何字段
    assert rc == 0 and "💧" in strip(out) and "✱" not in strip(out)


def test_e2e_health_states():
    d = tempfile.mkdtemp(prefix="sl-hl-")
    env = dict(os.environ, HEALTH_STATE_DIR=d)
    stdin = b"{}"
    write_health_state(d, make_health_state(paused=True, paused_at=1))
    rc, out = run_sl(env, stdin)
    assert rc == 0 and "⏸" in strip(out)
    s = make_health_state()
    s["interval_s"] = 10  # 100s 前 ack、10s 间隔 → due
    write_health_state(d, s)
    rc, out = run_sl(env, stdin)
    assert rc == 0 and "🚨" in strip(out) and "\x1b[41;97m" in out
```

- [ ] **Step 2: 运行确认失败**

Run: `cd plugins/health-reminder && python3 tests/test_statusline.py`
Expected: 新增 3 个 FAIL（`No such file or directory: …/scripts/statusline`），原 7 个 PASS

- [ ] **Step 3: 实现 `scripts/statusline`（chmod +x）**

```python
#!/usr/bin/env python3
"""单行状态栏：模型 ✱ │ 占比 ▓░ NN% │ git ⎇ │ 健康 💧。任何异常降级不报错。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import statusline_lib as sl   # noqa: E402
import health_lib             # noqa: E402

RESET = "\x1b[0m"
DIM = "\x1b[90m"
RED = "\x1b[41;97m"
YELLOW = "\x1b[33m"


def health_segment():
    s = health_lib.load_state()
    if not s:
        return ""
    c = health_lib.compute(s, int(time.time()))
    if c["paused"]:
        return " %s⏸ %s%s" % (YELLOW, health_lib.fmt_remaining(c["remaining_s"]), RESET)
    if c["due"]:
        return " %s 🚨 站起来·喝水·伸懒腰 %s" % (RED, RESET)
    return " %s💧 %s%s" % (DIM, health_lib.fmt_remaining(c["remaining_s"]), RESET)


def main_statusline():
    data = {}
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        if not isinstance(data, dict):
            data = {}
    except Exception:  # noqa: BLE001  stdin 损坏 → 仅健康段
        data = {}
    segs = []
    try:
        name = sl.model_name((data.get("model") or {}).get("display_name"))
        if name:
            segs.append(sl.model_segment(name))
    except Exception:  # noqa: BLE001
        pass
    try:
        tp = data.get("transcript_path")
        tok = sl.ctx_tokens_from_transcript(tp)
        if tok is not None:
            pct = sl.bar_pct(tok, sl.window_for((data.get("model") or {}).get("id")))
            segs.append(sl.ctx_segment(pct))
    except Exception:  # noqa: BLE001
        pass
    try:
        cwd = (data.get("workspace") or {}).get("current_dir")
        if cwd and os.path.isdir(cwd):
            seg = sl.git_segment(cwd)
            if seg:
                segs.append(seg)
    except Exception:  # noqa: BLE001
        pass
    try:
        seg = health_segment()
        if seg:
            segs.append(seg)
    except Exception:  # noqa: BLE001
        pass
    print(sl.SEP.join(segs))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main_statusline())
    except Exception:  # noqa: BLE001  绝不让 Claude Code 报错
        print("")
        sys.exit(0)
```

`chmod +x scripts/statusline`

- [ ] **Step 4: 运行确认全部通过 + 回归**

Run: `cd plugins/health-reminder && python3 tests/test_statusline.py && python3 tests/test_health_lib.py`
Expected: `10/10 通过`；`22/22 通过`

- [ ] **Step 5: 实测性能**

```bash
cd plugins/health-reminder
export HEALTH_STATE_DIR=$(mktemp -d)
echo '{"message":{"usage":{"input_tokens":124000}}}' > "$HEALTH_STATE_DIR/t.jsonl"
python3 - <<'PY'
import json, subprocess, sys, time
stdin = json.dumps({"model": {"id": "claude-opus-5", "display_name": "Opus 5"},
                    "transcript_path": __import__("os").environ["HEALTH_STATE_DIR"] + "/t.jsonl",
                    "workspace": {"current_dir": "/tmp"}}).encode()
t0 = time.time()
for _ in range(10):
    subprocess.run([sys.executable, "scripts/statusline"], input=stdin,
                   stdout=subprocess.PIPE)
print("平均 %.0f ms/次" % ((time.time() - t0) / 10 * 1000))
PY
```

Expected: 平均 < 150 ms（无 git 仓库时 ~40-60ms）。记录数字到 README（Task 3）。

- [ ] **Step 6: Commit**

```bash
git add plugins/health-reminder/scripts/statusline plugins/health-reminder/tests/test_statusline.py
git commit -m "feat: statusline 入口（四段组装，逐段降级，端到端测试）"
```

---

### Task 3: setup 迁移到新渲染器 + README 更新

**Files:**
- Modify: `plugins/health-reminder/scripts/health_lib.py`（cmd_setup 的安装命令与幂等判断）
- Modify: `plugins/health-reminder/tests/test_health_lib.py`（追加迁移测试）
- Modify: `plugins/health-reminder/README.md`（状态栏章节改为新渲染器、性能数字、setup 迁移说明）

**Interfaces:**
- Consumes: Task 2 的 `scripts/statusline`；既有 `cmd_setup`/`settings_path`/`backup_path`
- Produces: setup 后 settings.json 的 statusLine.command = `python3 <插件脚本目录>/statusline`；已装旧包装器（命令含 `health_statusline`）再 setup → 命令升级为 statusline，备份文件不覆盖；`--remove` 行为不变

- [ ] **Step 1: 追加失败测试（test_health_lib.py，`if __name__` 前）**

```python
def test_setup_migrates_wrapper_to_renderer():
    d, env = tmp_env()
    home = tempfile.mkdtemp(prefix="health-home-")
    settings = os.path.join(home, ".claude", "settings.json")
    os.makedirs(os.path.dirname(settings))
    # 场景1: 干净 settings → 装新渲染器
    with open(settings, "w") as f:
        json.dump({"other": 1}, f)
    env2 = dict(env, HOME=home)
    rc, out = run_cli(["setup"], env2)
    assert rc == 0 and "已安装" in out
    with open(settings) as f:
        st = json.load(f)
    assert "/statusline" in st["statusLine"]["command"]
    assert "health_statusline" not in st["statusLine"]["command"]
    assert st["other"] == 1
    # 场景2: 已装旧包装器 → setup 升级到新渲染器，备份保留
    with open(settings, "w") as f:
        json.dump({"statusLine": {"type": "command",
                                  "command": "python3 /old/health_statusline"},
                   "other": 1}, f)
    with open(os.path.join(d, "statusline_backup.json"), "w") as f:
        json.dump({"statusLine": {"type": "command",
                                  "command": "npx powerline"}}, f)
    rc, out = run_cli(["setup"], env2)
    assert rc == 0
    with open(settings) as f:
        st2 = json.load(f)
    assert st2["statusLine"]["command"].endswith("/statusline")
    with open(os.path.join(d, "statusline_backup.json")) as f:
        assert json.load(f)["statusLine"]["command"] == "npx powerline"  # 备份未丢
    # 场景3: --remove 仍能还原到备份的原值
    rc, out = run_cli(["setup", "--remove"], env2)
    assert rc == 0 and "恢复" in out
    with open(settings) as f:
        st3 = json.load(f)
    assert st3["statusLine"]["command"] == "npx powerline" and st3["other"] == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd plugins/health-reminder && python3 tests/test_health_lib.py`
Expected: 新增 1 个 FAIL（setup 现在装的是 health_statusline，断言 `/statusline` 不满足；场景2 会把包装器命令写进备份导致场景3 还原错误），原 22 个 PASS

- [ ] **Step 3: 修改 `cmd_setup`**

安装分支整体替换为（保留 remove 分支与函数其余部分不动）：

```python
    else:
        cmd = cur.get("command") or ""
        already_ours = ("health_statusline" in cmd) or (
            cmd.endswith("/statusline"))
        renderer = "python3 " + os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "statusline")
        if already_ours:
            # 旧包装器/旧渲染器安装 → 平滑升级，不动已备份的原值
            settings["statusLine"] = {"type": "command", "command": renderer}
            print("✅ 已升级为新一代状态栏渲染器（备份的原状态栏不变）")
        else:
            with open(backup_path(), "w", encoding="utf-8") as f:
                json.dump({"statusLine": cur or None}, f, ensure_ascii=False)
            settings["statusLine"] = {"type": "command", "command": renderer}
            print("✅ 状态栏渲染器已安装（原状态栏已备份，setup --remove 可恢复）")
```

（注意：原实现中 `"health_statusline" in cmd → 打印已在位并 return 0` 的分支删除，由上面的升级分支取代。）

- [ ] **Step 4: 运行确认全部通过**

Run: `cd plugins/health-reminder && python3 tests/test_health_lib.py && python3 tests/test_statusline.py`
Expected: `23/23 通过`；`10/10 通过`

- [ ] **Step 5: 更新 README**

`README.md` 中：
- 标题下第一段改为描述新渲染器：单行 ` ✱ 模型 │ ▓░ 占比 │ ⎇ 分支 │ 💧 倒计时`（无花费段）
- 「用法」表 `setup` 行描述改为：安装状态栏渲染器（备份原状态栏；已装旧包装器会自动升级）
- 「性能」一节替换为：`状态栏渲染器实测开销：约 ___ ms/次（无 npx/node 进程）`，填入 Task 2 Step 5 实测数字
- 「工作原理」追加一句：状态栏渲染器为独立 python3 脚本，上下文占比取自会话 transcript 的最后一条 usage 记录，模型窗口按 id 含 "1m" 映射 1M、否则 200k

- [ ] **Step 6: 真机安装并冒烟**

```bash
cd /home/plugin
python3 plugins/health-reminder/scripts/health setup
echo '{"model":{"id":"claude-opus-5","display_name":"Opus 5"},"workspace":{"current_dir":"/home/plugin"},"transcript_path":"/root/.claude/projects/-home-plugin/3343d637-ee89-4e38-8627-6921f703d4a7.jsonl"}' | python3 plugins/health-reminder/scripts/statusline
```

Expected: setup 输出升级/安装成功；渲染行含 `✱ opus 5`、`%`、`⎇ feat/health-reminder`、`💧`（transcript 为本会话真实文件）

- [ ] **Step 7: Commit + 版本号**

```bash
git add plugins/health-reminder/scripts/health_lib.py plugins/health-reminder/tests/test_health_lib.py plugins/health-reminder/README.md plugins/health-reminder/.claude-plugin/plugin.json
git commit -m "feat: setup 安装新状态栏渲染器（旧包装器平滑迁移）+ README"
```

plugin.json version → `0.2.0`（一并提交）

