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
BANNER_SHOW_S = 60  # 到期横幅展示时长：超过后静默，直到手动 done

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
        if s.get("last_break") is not None:
            int(s["last_break"])
        if s.get("banner_seq") is not None:
            int(s["banner_seq"])
        if s.get("banner_seq_at") is not None:
            int(s["banner_seq_at"])
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
        return "%dm" % (s // 60)
    return "%ds" % s


def fmt_work(seconds):
    if seconds < 3600:
        return "%dm" % (seconds // 60)
    hours = seconds / 3600.0
    if hours == int(hours):
        return "%dh" % int(hours)
    return "%.1fh" % hours


def work_duration(s, now):
    base = s.get("last_break") or s.get("started_at") or now
    return max(0, int(now) - base)


def do_done(s, now):
    s = dict(s)
    s["last_break"] = int(now)
    s["last_ack"] = int(now)
    s["banner_seq"] = 0
    s["banner_seq_at"] = None
    return s


def compute(s, now):
    interval = s["interval_s"]
    if s.get("paused"):
        frozen = s.get("paused_at") or now
        return {"running": True, "paused": True, "due": False, "missed": 0,
                "remaining_s": max(0, s["last_ack"] + interval - frozen)}
    due_at = s["last_ack"] + interval
    due = now >= due_at
    # 到期后横幅只显示 BANNER_SHOW_S 秒（hook 首弹时记 banner_seq_at）：
    # 没记录过 → 视为"还没弹出过"，本次照常显示；超过窗口即静默，
    # 手动 /health done 仍可随时重置计时。
    seq_at = s.get("banner_seq_at")
    if due and seq_at is None:
        show_banner = True          # 尚未展示过：这条必须让用户看到
    else:
        show_banner = due and (now - (seq_at or due_at)) < BANNER_SHOW_S
    missed = (now - s["last_ack"]) // interval if due else 0
    return {"running": True, "paused": False, "due": due,
            "show_banner": show_banner, "missed": missed,
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


def banner_text(c, seq=None):
    """seq=None 按 missed 轮换（兼容旧行为）；传序号则按弹出次数轮换，
    保证相邻两次提醒看到不同的文案（missed 固定为 1 时旧逻辑会一直同一条）。"""
    i = c["missed"] if seq is None else max(0, int(seq))
    msg = BANNERS[i % len(BANNERS)]
    if c["missed"] > 1:
        msg += "（期间错过了 %d 次提醒）" % (c["missed"] - 1)
    msg += "（休息完 /health done）"
    return msg

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
                    "last_ack": now, "paused": False, "paused_at": None,
                    "last_break": now, "banner_seq": 0, "banner_seq_at": None})
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


def cmd_done(now):
    with state_lock():
        s = load_state()
        if not s:
            print(_msg_not_running())
            return 0
        save_state(do_done(s, now))
    print("👌 已记录休息，计时重新开始")
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
        work_str = fmt_work(work_duration(s, now))
        print("💧 下次提醒还有 %s（每 %s 一次）· ⏱ 连续 %s"
              % (fmt_remaining(c["remaining_s"]), fmt_duration(s["interval_s"]), work_str))
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
                       ("ack", "手动确认提醒"), ("done", "手动确认休息")):
        sub.add_parser(name, help=text)
    sp = sub.add_parser("setup", help="安装/恢复状态栏包装器")
    sp.add_argument("--remove", action="store_true", help="恢复原状态栏")
    args = p.parse_args(argv)
    now = int(time.time())
    table = {
        "start": lambda: cmd_start(args.interval, now),
        "pause": lambda: cmd_pause(now),
        "resume": lambda: cmd_resume(now),
        "stop": cmd_stop,
        "ack": lambda: cmd_ack(now),
        "done": lambda: cmd_done(now),
        "status": lambda: cmd_status(now),
        "setup": lambda: cmd_setup(getattr(args, "remove", False)),
    }
    return table.get(args.cmd or "status", lambda: cmd_status(now))()

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
        already_ours = ("health_statusline" in cmd) or (
            cmd.endswith("/statusline"))
        renderer = "python3 " + os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "statusline")
        if already_ours:
            # 旧包装器/旧渲染器安装 → 平滑升级，不动已备份的原值
            settings["statusLine"] = {"type": "command", "command": renderer}
            print("✅ 已升级为新一代状态栏渲染器（备份的原状态栏不变）")
        else:
            if not os.path.exists(backup_path()):
                # 首次安装：备份当前原值；已有备份(曾被其他状态栏接管)则保留最早的原值不被覆盖
                with open(backup_path(), "w", encoding="utf-8") as f:
                    json.dump({"statusLine": cur or None}, f,
                              ensure_ascii=False)
            settings["statusLine"] = {"type": "command", "command": renderer}
            if cmd:
                print("⚠️ 检测到其他状态栏，已替换（最早的原状态栏保留在备份中，"
                      "setup --remove 可恢复）")
            else:
                print("✅ 状态栏渲染器已安装（setup --remove 可移除）")
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    return 0
