# 节律行实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 第二行节律四段（💧⏱🕐⚡）+ `/health done` 手动确认休息 + 提醒文案池轮换 + 宠物科技史小知识。

**Architecture:** health-reminder 加 `last_break` 字段与 `done` 子命令、BANNERS 池确定性轮换；statusline 渲染器第二行组装三个新段（各段独立降级）；知识库为纯数据 JSON + 宠物 SKILL 追加模型生成动作。

**Tech Stack:** python3 标准库（time/os/datetime 无需新依赖）、claude-pet node。

## Global Constraints

- 仅 python3 标准库；文案中文；UTF-8
- 运行时不硬编码 /home/plugin；facts.json 路径由 `__file__` 推导
- 渲染器段级 try/except，段缺失自动隐藏；绝不多行溢出（第二行恒 ≤ 4 段）
- 确定性轮换：banner 用 `missed % len(BANNERS)`、fact 用 `hour % len(facts)`，不用随机数
- 既有测试保持全绿：test_health_lib.py（24）、test_statusline.py（15）、claude-pet node（58）
- 每 Task 一 commit，不用 git add -A

---

### Task 1: health done + last_break + 文案池

**Files:**
- Modify: `plugins/health-reminder/scripts/health_lib.py`
- Test: `plugins/health-reminder/tests/test_health_lib.py`（追加）

**Interfaces:**
- Consumes: 既有 state/CLI 结构
- Produces: `state.last_break`（epoch；start 时=started_at；`do_done(s, now)` 同置 last_break 与 last_ack）；CLI 子命令 `done`；`BANNERS`（12 条 str 列表）；`banner_text(c)` 改为 `BANNERS[c["missed"] % len(BANNERS)] + 尾缀(休息完 /health done)（missed>1 先追加错过 N 次）`；`work_duration(s, now) -> int` 秒（last_break 缺失回退 started_at）；`fmt_work(seconds) -> str`（`45m`/`2.1h`）；status 输出加 `⏱ 连续 X`

- [ ] Step 1: 追加失败测试

```python
def test_done_and_work_duration():
    d, env = tmp_env()
    rc, out = run_cli(["start", "1h"], env)
    assert rc == 0
    s = health_lib.load_state(os.path.join(d, "state.json"))
    assert s["last_break"] == s["started_at"]
    # 手动改档案让连续时长可测
    s["last_break"] = 1000
    health_lib.save_state(s, os.path.join(d, "state.json"))
    assert health_lib.work_duration(s, now=4000) == 3000
    # done 同置两钟
    with health_lib.state_lock():
        s2 = health_lib.load_state()
        # 直接调用 do_done（单测层面）
    s3 = health_lib.do_done({"last_break": 1000, "last_ack": 1000,
                             "started_at": 1000, "interval_s": 600,
                             "paused": False, "paused_at": None}, now=5000)
    assert s3["last_break"] == 5000 and s3["last_ack"] == 5000
    rc, out = run_cli(["done"], env)   # CLI 层
    assert rc == 0 and "已记录休息" in out
    s4 = health_lib.load_state(os.path.join(d, "state.json"))
    assert s4["last_break"] > 1000


def test_work_duration_fallback_to_started():
    s = {"started_at": 1000, "interval_s": 600, "last_ack": 1000,
         "paused": False, "paused_at": None}  # 旧档案无 last_break
    assert health_lib.work_duration(s, now=2000) == 1000


def test_fmt_work():
    assert health_lib.fmt_work(45 * 60) == "45m"
    assert health_lib.fmt_work(2 * 3600 + 6 * 60) == "2.1h"
    assert health_lib.fmt_work(30 * 3600) == "30h"


def test_banner_pool_rotates_deterministically():
    pool = health_lib.BANNERS
    assert len(pool) >= 12 and len(set(pool)) == len(pool)
    texts = set()
    for missed in range(len(pool)):
        c = {"running": True, "paused": False, "due": True,
             "remaining_s": 0, "missed": missed}
        texts.add(health_lib.banner_text(c))
    assert len(texts) == len(pool)          # 每周期换一条
    c = {"running": True, "paused": False, "due": True,
         "remaining_s": 0, "missed": 3}
    assert "/health done" in health_lib.banner_text(c)   # 尾缀
    c["missed"] = 5
    assert "错过了 4 次" in health_lib.banner_text(c)
```

- [ ] Step 2: 跑测确认新测试 FAIL（无 done/BANNERS/work_duration）
- [ ] Step 3: 实现（health_lib.py 追加/修改）

```python
BANNERS = [
    "⏰ 该起来转转了，代码不会跑",
    "⏰ 喝口水，眼睛看看 6 米外",
    "⏰ 你的颈椎请求一次 5 分钟会议",
    "⏰ 站起来！你的椅子正在偷你的腰",
    "⏰ 伸个懒腰，肩胛骨会感谢你",
    "⏰ 屏幕看了太久，窗外的世界也是高清的",
    "⏰ 喝水提醒：你上一次喝水是什么时候？",
    "⏰ 起来走两步，bug 跑不掉的",
    "⏰ 眼睛干了吗？眨眼 20 次，看远 20 秒",
    "⏰ 腰在报警，起来晃晃",
    "⏰ 给身体充个电：站起、喝水、伸腰",
    "⏰ 代码要久坐，你不要",
]


def do_done(s, now):
    s = dict(s)
    s["last_break"] = int(now)
    s["last_ack"] = int(now)
    return s


def work_duration(s, now):
    base = s.get("last_break") or s.get("started_at") or now
    return max(0, int(now) - base)


def fmt_work(seconds):
    if seconds < 3600:
        return "%dm" % (seconds // 60)
    return "%.1fh" % (seconds / 3600.0)
```

`banner_text` 改为：

```python
def banner_text(c):
    msg = BANNERS[c["missed"] % len(BANNERS)]
    if c["missed"] > 1:
        msg += "（期间错过了 %d 次提醒）" % (c["missed"] - 1)
    msg += "（休息完 /health done）"
    return msg
```

CLI：`cmd_start` 写 state 时加 `"last_break": now`；`main_cli` 注册 `done`：

```python
def cmd_done(now):
    with state_lock():
        s = load_state()
        if not s:
            print(_msg_not_running())
            return 0
        save_state(do_done(s, now))
    print("👌 已记录休息，计时重新开始")
    return 0
```

`cmd_status` 非 due 分支追加 `· ⏱ 连续 %s`（fmt_work(work_duration(s, now))）。
注意：`valid_state` 不把 last_break 列为必需（旧档案兼容，缺失回退 started_at）。

- [ ] Step 4: 全量 `python3 tests/test_health_lib.py` → 28/28
- [ ] Step 5: 更新既有断言：`test_banner_text` 若断言旧文案则按新池语义改写（保持"错过 N 次"与尾缀断言）
- [ ] Step 6: Commit `feat: /health done 手动确认休息 + 连续工作计时 + 提醒文案池`

---

### Task 2: 第二行节律段（⏱🕐⚡）

**Files:**
- Modify: `plugins/statusline/scripts/statusline_lib.py`、`plugins/statusline/scripts/statusline`
- Test: `plugins/statusline/tests/test_statusline.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `work_duration/fmt_work`（经 health_lib import）；`health_segment` 现结构
- Produces: `work_segment(state) -> str`（` ⏱ 2.1h`，<1h `90` 灰 / ≥1h `33` 黄 / ≥2h `41;97` 红底）、`clock_segment(now) -> str`（` 🕐 14:32`，23:00-06:00 `31` 暗红否则 `90`）、`load_segment() -> str`（` ⚡0.8`，比率 <0.7 `90` / ≥0.7 `33` / ≥1.0 `31`；非 Linux/读失败 → `""`）；第二行组装改为 `health + work + clock + load` 四段

- [ ] Step 1: 追加失败测试

```python
def test_rhythm_segments():
    import time as _t
    st = {"started_at": 1, "interval_s": 600, "last_ack": 1,
          "last_break": 1, "paused": False, "paused_at": None}
    now = 1 + 45 * 60
    assert "⏱ 45m" in strip(sl.work_segment((st, now)[0], now))
    now2 = 1 + 2 * 3600
    assert "⏱ 2.0h" in strip(sl.work_segment(st, now2))
    seg = sl.clock_segment(_t.mktime((2026, 8, 27, 23, 30, 0, 0, 0, -1)))
    assert "23:30" in strip(seg)
    if hasattr(sl, "load_segment"):
        s = sl.load_segment()
        assert s == "" or "⚡" in strip(s)
```

- [ ] Step 2: FAIL 确认（无三函数）
- [ ] Step 3: 实现（statusline_lib.py 追加）

```python
def work_segment(state, now=None):
    import time as _t
    now = int(_t.time()) if now is None else now
    try:
        import health_lib
        secs = health_lib.work_duration(state, now)
    except Exception:  # noqa: BLE001
        return ""
    color = "90" if secs < 3600 else ("33" if secs < 7200 else "41;97")
    return " \x1b[%sm⏱ %s\x1b[0m" % (color, health_lib.fmt_work(secs))


def clock_segment(now=None):
    import time as _t
    now = _t.time() if now is None else now
    lt = _t.localtime(now)
    hhmm = _t.strftime("%H:%M", lt)
    color = "31" if (lt.tm_hour >= 23 or lt.tm_hour < 6) else "90"
    return " \x1b[%sm🕐 %s\x1b[0m" % (color, hhmm)


def load_segment():
    try:
        with open("/proc/loadavg", encoding="ascii") as f:
            one = float(f.read().split()[0])
        n = os.cpu_count() or 1
        ratio = one / n
    except Exception:  # noqa: BLE001  非 Linux/读失败
        return ""
    color = "90" if ratio < 0.7 else ("33" if ratio < 1.0 else "31")
    return " \x1b[%sm⚡%.1f\x1b[0m" % (color, one)
```

（statusline_lib 需要 `import os`——已有。）`scripts/statusline` 的第二行组装改为：

```python
    second_parts = []
    try:
        seg = health_segment()
        if seg:
            second_parts.append(seg.strip())
    except Exception:  # noqa: BLE001
        pass
    try:
        if health_lib is not None:
            st = health_lib.load_state()
            if st:
                seg = sl.work_segment(st)
                if seg:
                    second_parts.append(seg.strip())
    except Exception:  # noqa: BLE001
        pass
    try:
        second_parts.append(sl.clock_segment().strip())
    except Exception:  # noqa: BLE001
        pass
    try:
        seg = sl.load_segment()
        if seg:
            second_parts.append(seg.strip())
    except Exception:  # noqa: BLE001
        pass
    second = sl.SEP.join(second_parts)
```

（替换现有 second 构造块；third/print 逻辑不变。）

- [ ] Step 4: 全量两套测试 → 16/16、28/28
- [ ] Step 5: Commit `feat: 第二行节律段 ⏱🕐⚡（手动确认连续时长）`

---

### Task 3: 宠物科技史小知识（数据 + 渲染 + 学新知识）

**Files:**
- Create: `plugins/statusline/data/tech_facts.json`（~150 条，由实现者用下文生成脚本写出）
- Modify: `plugins/statusline/scripts/statusline`（pet_line 尾部加 📜）
- Modify: `plugins/claude-pet/skills/pet/SKILL.md`（追加"学新知识"）
- Test: `plugins/statusline/tests/test_statusline.py`（追加）

**Interfaces:**
- Consumes: pet_line 现结构
- Produces: `fact_segment(root) -> str`（` 📜 1969·ARPANET 首秀`，紫灰 `245`；facts.json 缺失/空/坏 → `""`）；pet_line 尾部追加该段；轮换 `hour = time.localtime().tm_hour; facts[hour % len(facts)]`

- [ ] Step 1: 生成 facts.json —— 实现者直接执行以下 python 脚本生成（保证数量与结构）：

```python
# scripts 生成 150 条：此脚本一次性运行，产物入库
facts = [
    {"y": 1969, "t": "ARPANET 四节点首次联机"},
    {"y": 1971, "t": "第一封电子邮件发出"},
    {"y": 1973, "t": "Xerox Alto 图形界面诞生"},
    # …… 实现者补全至 150 条，覆盖计算/网络/航天/医学/物理等，
    # 每条 {y, t}，y 为年份 int，t ≤14 汉字，事实需真实（不确定的不写）
]
import json
json.dump({"facts": facts}, open("plugins/statusline/data/tech_facts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
assert len(facts) == 150 and len(set(f["t"] for f in facts)) == 150
```

- [ ] Step 2: 追加失败测试

```python
def test_fact_segment_rotation_and_degradation():
    import json as _j
    import tempfile as _tf
    d = _tf.mkdtemp()
    p = os.path.join(d, "tech_facts.json")
    _j.dump({"facts": [{"y": 1969, "t": "ARPANET 首秀"},
                       {"y": 1991, "t": "Linux 诞生"}]}, open(p, "w"))
    sys.path.insert(0, SCRIPTS)
    import importlib
    import statusline as entry
    importlib.reload(entry)
    seg = entry.fact_segment(d)
    assert "📜" in strip(seg) and ("1969" in strip(seg) or "1991" in strip(seg))
    assert entry.fact_segment(os.path.join(d, "none.json")) == ""
    open(p, "w").write("broken")
    assert entry.fact_segment(d) == ""
```

- [ ] Step 3: 实现 `fact_segment(root)`（scripts/statusline，pet_line 之前）+ pet_line parts 追加：

```python
def fact_segment(data_root):
    """科技史小知识：按小时轮换一条，缺失/损坏 → 空。"""
    try:
        import time as _t
        p = os.path.join(data_root, "data", "tech_facts.json")
        with open(p, encoding="utf-8") as f:
            facts = json.load(f).get("facts") or []
        if not facts:
            return ""
        fact = facts[_t.localtime().tm_hour % len(facts)]
        return " \x1b[38;5;245m📜 %d·%s\x1b[0m" % (fact["y"], fact["t"])
    except Exception:  # noqa: BLE001
        return ""
```

pet_line 的 parts 追加：`fact_segment(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))`（插件根）。注意 fact 段放 parts 末尾。

- [ ] Step 4: SKILL.md 追加动作（放在转生条目后）：

```markdown
- 学新知识 → 让 Claude 现场生成 5 条科技史小知识（用户没指定主题时自选有趣主题），
  去重后追加到 `/home/plugin/plugins/statusline/data/tech_facts.json` 的 facts 数组
  （原子写：tmp+rename；每条 {"y": 年份int, "t": "≤14字"}；与现有 t 重复的丢弃），
  然后运行 `claude-pet feed` 喂食一次作为奖励，并把新增条目展示给用户
```

- [ ] Step 5: 全量三套测试 → statusline 17/17、health 28/28、claude-pet node 58 pass
- [ ] Step 6: Commit `feat: 宠物行科技史小知识（150 条库+小时轮换+学新知识）`；README 两处（statusline README 段表加 📜 行、health README 用法表加 done 行）

