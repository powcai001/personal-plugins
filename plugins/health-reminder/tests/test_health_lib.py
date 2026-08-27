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
    # New pool semantics: banner from pool + suffix
    text = health_lib.banner_text(c)
    assert any(b in text for b in health_lib.BANNERS), "Should contain one of the banner texts"
    assert "休息完 /health done" in text, "Should have the suffix"
    c["missed"] = 3
    text = health_lib.banner_text(c)
    assert "期间错过了 2 次提醒" in text, "Should mention missed reminders"
    assert "休息完 /health done" in text, "Should still have the suffix"


def test_fmt_helpers():
    assert health_lib.fmt_remaining(0) == "1m"
    assert health_lib.fmt_remaining(59) == "1m"
    assert health_lib.fmt_remaining(1920) == "32m"
    assert health_lib.fmt_remaining(3900) == "1h05m"
    assert health_lib.fmt_duration(10) == "10s"
    assert health_lib.fmt_duration(2700) == "45m"
    assert health_lib.fmt_duration(5400) == "1h30m"


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
    # New pool semantics: check for common banner elements
    assert rc == 0 and ("⏰" in out or "站起" in out or "喝水" in out) and "systemMessage" in out
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
    import time
    now = int(time.time())
    write_state(d, last_ack=now - 100, interval=600)  # Not due: last_ack 100s ago, interval 600s
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
    rc, out = run_cli(["setup"], env2)           # 替换已有 powerline
    assert rc == 0 and "检测到其他状态栏" in out
    with open(settings) as f:
        st = json.load(f)
    assert st["statusLine"]["command"].endswith("/statusline")
    assert st["other"] == 1                      # 其他配置不动
    with open(os.path.join(d, "statusline_backup.json")) as f:
        assert json.load(f)["statusLine"]["command"] == "powerline x"
    rc, out = run_cli(["setup"], env2)           # 重复安装 → 平滑升级，备份不变
    assert rc == 0 and "已升级" in out
    with open(settings) as f:
        assert st["statusLine"] == json.load(f)["statusLine"]
    with open(os.path.join(d, "statusline_backup.json")) as f:
        assert json.load(f)["statusLine"]["command"] == "powerline x"
    rc, out = run_cli(["setup", "--remove"], env2)
    assert rc == 0 and "恢复" in out
    with open(settings) as f:
        st2 = json.load(f)
    assert st2["statusLine"]["command"] == "powerline x" and st2["other"] == 1


def test_statusline_slow_original_survives():
    # 回归：原命令耗时长于旧 5s 超时（用户 npx powerline 实测 7.3s 冷启动）时不得被杀
    d, env = tmp_env()
    write_backup(d, "sleep 6; echo BASE")
    rc, out = run_statusline(env)
    assert rc == 0 and out.strip() == "BASE"


def test_setup_preserves_first_backup_when_taken_over():
    d, env = tmp_env()
    home = tempfile.mkdtemp(prefix="health-home-")
    settings = os.path.join(home, ".claude", "settings.json")
    os.makedirs(os.path.dirname(settings))
    env2 = dict(env, HOME=home)
    # 首次安装：settings 里已有原状态栏（powerline）
    with open(settings, "w") as f:
        json.dump({"statusLine": {"type": "command", "command": "npx powerline"}}, f)
    run_cli(["setup"], env2)
    with open(os.path.join(d, "statusline_backup.json")) as f:
        assert json.load(f)["statusLine"]["command"] == "npx powerline"
    # 其他插件接管（如 claude-pet）
    with open(settings, "w") as f:
        json.dump({"statusLine": {"type": "command",
                                  "command": "/root/.claude/claude-pet/launcher.sh"}}, f)
    rc, out = run_cli(["setup"], env2)
    assert rc == 0 and "检测到其他状态栏" in out
    # 最早的 powerline 备份未被覆盖
    with open(os.path.join(d, "statusline_backup.json")) as f:
        assert json.load(f)["statusLine"]["command"] == "npx powerline"
    with open(settings) as f:
        assert json.load(f)["statusLine"]["command"].endswith("/statusline")


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


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items())
              if k.startswith("test_") and callable(v)]
    for _t in _tests:
        run_test(_t)
    print("\n%d/%d 通过" % (len(_tests) - len(FAILURES), len(_tests)))
    sys.exit(1 if FAILURES else 0)
