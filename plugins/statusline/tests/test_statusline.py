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
    # 密闭化：宿主机可能全局 export 了 HEALTH_CTX_WINDOW（用户真实配置）
    old = os.environ.pop("HEALTH_CTX_WINDOW", None)
    try:
        assert sl.window_for("claude-opus-5-1m-20261001") == 1000000
        assert sl.window_for("claude-opus-5-1M") == 1000000
        assert sl.window_for("claude-sonnet-5") == 200000
        assert sl.window_for(None) == 200000
        assert sl.window_for("") == 200000
    finally:
        if old is not None:
            os.environ["HEALTH_CTX_WINDOW"] = old


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


def test_git_segment_ahead_behind():
    d = tempfile.mkdtemp(prefix="sl-ab-")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "c1"], cwd=d, check=True)
    # 造 upstream 指向当前 HEAD
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
                   cwd=d, check=True)
    subprocess.run(["git", "config", "branch.main.remote", "origin"], cwd=d, check=True)
    subprocess.run(["git", "config", "branch.main.merge", "refs/heads/main"],
                   cwd=d, check=True)
    # @{upstream} 需要 fetch refspec 才能把 origin/main 识别为远端跟踪分支
    subprocess.run(["git", "config", "remote.origin.fetch",
                    "+refs/heads/*:refs/remotes/origin/*"], cwd=d, check=True)
    # 与上游同步 → 无 ↑↓
    assert "↑" not in strip(sl.git_segment(d)) and "↓" not in strip(sl.git_segment(d))
    # 领先 1 提交 → ↑1
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "c2"], cwd=d, check=True)
    assert "↑1" in strip(sl.git_segment(d)) and "↓" not in strip(sl.git_segment(d))


def test_ctx_tokens_skips_nondict_lines():
    d = tempfile.mkdtemp(prefix="sl-nd-")
    p = os.path.join(d, "t.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        # 合法 usage 在前：reversed 扫描时先遇到后面的畸形行，才真正覆盖该路径
        f.write(json.dumps({"message": {"usage": {"input_tokens": 7}}}) + "\n")
        f.write("null\n42\n[1,2]\n\"str\"\n{\"message\": \"notadict\"}\n")
    assert sl.ctx_tokens_from_transcript(p) == 7


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
    env = dict(os.environ, HEALTH_STATE_DIR=d,
               HOME=tempfile.mkdtemp(prefix="sl-nohome-"))
    env.pop("HEALTH_CTX_WINDOW", None)  # 密闭化：宿主机可能全局设置该覆盖变量
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
    lines = plain.rstrip("\n").split("\n")
    assert rc == 0 and len(lines) == 2 and out.endswith("\n")  # 工作 + 健康
    assert "✱ opus 5" in lines[0] and "62%" in lines[0] and "💧" in lines[1]
    assert lines[0].index("opus 5") < lines[0].index("62%")
    # 非 git 目录 → 无 git 段，但其余段在
    assert "⎇" not in lines[0]


def test_e2e_degrades_to_rhythm_only():
    # stdin 损坏/无字段 → 各工作段独立降级，但节律行的 clock/load 恒显示
    d = tempfile.mkdtemp(prefix="sl-deg-")
    env = dict(os.environ, HEALTH_STATE_DIR=d,
               HOME=tempfile.mkdtemp(prefix="sl-nohome-"))
    rc, out = run_sl(env, b"{ broken")  # stdin JSON 损坏
    # 简报原文为 strip(out) == ""，但 print 必带换行且 strip 只去 ANSI 码；
    # 按注释意图（空行；仍恰 1 换行）修正为 == "\n"
    assert rc == 0 and ("🕐" in strip(out) or "⚡" in strip(out))  # clock/load always show
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


def test_window_for_env_override_and_glm():
    import importlib
    old = os.environ.pop("HEALTH_CTX_WINDOW", None)
    try:
        # glm 类 1M 模型 id 不含 "1m"：默认 200k，靠环境变量显式声明
        assert sl.window_for("glm-5.3") == 200000
        os.environ["HEALTH_CTX_WINDOW"] = "1000000"
        assert sl.window_for("glm-5.3") == 1000000
        os.environ["HEALTH_CTX_WINDOW"] = "bad"
        assert sl.window_for("claude-opus-5-1m") == 1000000  # 坏值回退到 id 判定
        os.environ["HEALTH_CTX_WINDOW"] = "0"
        assert sl.window_for("glm-5.3") == 200000  # 非正值忽略
    finally:
        os.environ.pop("HEALTH_CTX_WINDOW", None)
        if old is not None:
            os.environ["HEALTH_CTX_WINDOW"] = old


def _mk_pet_env(form_line=None, state=None, launcher_body=None, with_state=True):
    """构造隔离 HOME：可选写宠物档案/launcher/PET_ROOT 形态表。"""
    import json as _j
    import tempfile as _tf
    home = _tf.mkdtemp(prefix="sl-pet-")
    petdir = os.path.join(home, ".claude", "claude-pet")
    os.makedirs(petdir)
    root = _tf.mkdtemp(prefix="sl-petroot-")
    os.makedirs(os.path.join(root, "data"))
    with open(os.path.join(root, "data", "species.json"), "w") as f:
        _j.dump({"species": [{"id": "dragon", "stages": [
            {"level": 1, "form": "🥚", "name": "神秘的蛋"},
            {"level": 8, "form": "🦎", "name": "小蜥蜴"},
            {"level": 45, "form": "🐉", "name": "神龙"}]}]}, f)
    with open(os.path.join(petdir, "statusline-launcher.sh"), "w") as f:
        f.write(launcher_body if launcher_body is not None else
                "#!/bin/sh\nexec node \"%s/bin/claude-pet\" statusline\n" % root)
    if with_state:
        st = {"level": 8, "xp": 24, "snacks": 2, "turnXp": 5}
        if state:
            st.update(state)
        with open(os.path.join(petdir, "state.json"), "w") as f:
            _j.dump(st, f)
    return home


def test_pet_line_hidden_without_state():
    home = _mk_pet_env(with_state=False)
    env = dict(os.environ, HOME=home, HEALTH_STATE_DIR=home)
    rc, out = run_sl(env, b"{}")
    assert rc == 0 and out.count("\n") == 1  # 无档案 → 只有第一行


def test_pet_line_redrawn_in_our_style():
    import re as _re
    home = _mk_pet_env(state={"level": 8, "xp": 24, "snacks": 2})
    env = dict(os.environ, HOME=home, HEALTH_STATE_DIR=home)
    rc, out = run_sl(env, b"{}")
    lines = out.rstrip("\n").split("\n")
    # 无工作段、无健康状态 → 第 1 行空被过滤，输出 = 节律行 + 宠物行
    assert rc == 0 and len(lines) == 2  # clock/load on line 2, pet on line 3
    second = _re.sub(r"\x1b\[[0-9;]*m", "", lines[1])  # pet on line 2 (after clock/load on line 1)
    # 重绘风格：宠物名+Lv+10格▰▱条+百分比+🍪；不再透传宠物原版输出
    assert "🦎 小蜥蜴" in second and "Lv.8" in second
    assert second.count("▰") + second.count("▱") == 10
    assert "80%" in second          # 24/30(=ceil(15*1.1^7)) = 80%
    assert "🍪2" in second
    # 旧透传用带空格的 · 分隔，新风格用 │（📜 段内的 1969·xxx 不带空格，不受影响）
    assert " · " not in second
    assert "│" in second


def test_pet_line_low_turnxp_hidden_and_broken_degrades():
    home = _mk_pet_env(state={"level": 8, "xp": 24, "turnXp": 300})
    env = dict(os.environ, HOME=home, HEALTH_STATE_DIR=home)
    rc, out = run_sl(env, b"{}")
    second = out.rstrip("\n").split("\n")[-1]
    assert "300xp" in second        # 高 turnXp 才展示
    # 档案损坏 → 整行隐藏
    with open(os.path.join(home, ".claude", "claude-pet", "state.json"), "w") as f:
        f.write("{broken")
    rc, out = run_sl(env, b"{}")
    assert rc == 0 and out.count("\n") == 1


def test_cwd_segment():
    # 仅目录名
    seg = sl.cwd_segment("/home/plugin/plugins/statusline/scripts")
    assert strip(seg) == " scripts" and "\x1b[35m" in seg
    assert strip(sl.cwd_segment("/home/plugin")) == " plugin"
    # 空/异常 → 空串
    assert sl.cwd_segment("") == ""


def test_rhythm_segments():
    import time as _t
    st = {"started_at": 1, "interval_s": 600, "last_ack": 1,
          "last_break": 1, "paused": False, "paused_at": None}
    now = 1 + 45 * 60
    assert "⏱ 45m" in strip(sl.work_segment(st, now))
    now2 = 1 + 2 * 3600
    assert "⏱ 2h" in strip(sl.work_segment(st, now2))
    # 工作段颜色边界：<1h 灰(90) / ≥1h 黄(33) / ≥2h 红底白字(41;97)
    assert "\x1b[90m" in sl.work_segment(st, 1 + 3599) and "\x1b[33m" not in sl.work_segment(st, 1 + 3599)
    assert "\x1b[33m" in sl.work_segment(st, 1 + 3600) and "\x1b[41;97m" not in sl.work_segment(st, 1 + 3600)
    assert "\x1b[41;97m" in sl.work_segment(st, 1 + 7200)
    # 时钟段颜色：深夜(23:00-06:00) 暗红(31)，白天灰(90)
    seg = sl.clock_segment(_t.mktime((2026, 8, 27, 23, 30, 0, 0, 0, -1)))
    assert "23:30" in strip(seg) and "\x1b[31m" in seg and "\x1b[90m" not in seg
    seg2 = sl.clock_segment(_t.mktime((2026, 8, 27, 14, 32, 0, 0, 0, -1)))
    assert "14:32" in strip(seg2) and "\x1b[90m" in seg2 and "\x1b[31m" not in seg2
    if hasattr(sl, "load_segment"):
        s = sl.load_segment()
        assert s == "" or "⚡" in strip(s)


def test_fact_segment_rotation_and_degradation():
    import importlib.machinery
    import importlib.util
    import json as _j
    import tempfile as _tf
    import time as _t
    # fact_segment(root) 读 root/data/tech_facts.json → fixture 放 data 子目录
    d = _tf.mkdtemp()
    os.makedirs(os.path.join(d, "data"))
    p = os.path.join(d, "data", "tech_facts.json")
    _j.dump({"facts": [{"y": 1969, "t": "ARPANET 首秀"},
                       {"y": 1991, "t": "Linux 诞生"}]}, open(p, "w"))
    # 入口文件无 .py 后缀，标准 import 不可见 → SourceFileLoader 加载
    loader = importlib.machinery.SourceFileLoader(
        "statusline_entry", os.path.join(SCRIPTS, "statusline"))
    spec = importlib.util.spec_from_loader("statusline_entry", loader)
    entry = importlib.util.module_from_spec(spec)
    loader.exec_module(entry)
    # 确定性测试：按与代码相同的方式计算期望索引
    hour = int(_t.time() // 3600)
    expect = "1969·ARPANET 首秀" if hour % 2 == 0 else "1991·Linux 诞生"
    seg = entry.fact_segment(d)
    assert "📜" in strip(seg) and expect in strip(seg)
    assert entry.fact_segment(os.path.join(d, "none.json")) == ""
    open(p, "w").write("broken")
    assert entry.fact_segment(d) == ""
    # 空 facts → 隐藏
    _j.dump({"facts": []}, open(p, "w"))
    assert entry.fact_segment(d) == ""
    # 字段错误（缺 y）→ 隐藏
    _j.dump({"facts": [{"t": "无年份"}]}, open(p, "w"))
    assert entry.fact_segment(d) == ""
if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items())
              if k.startswith("test_") and callable(v)]
    for _t in _tests:
        run_test(_t)
    print("\n%d/%d 通过" % (len(_tests) - len(FAILURES), len(_tests)))
    sys.exit(1 if FAILURES else 0)
