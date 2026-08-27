#!/usr/bin/env python3
"""statusline 渲染段库：纯函数，各自独立降级。被 scripts/statusline 组装。"""
import json
import os
import subprocess

SEP = "\x1b[90m │ \x1b[0m"


def window_for(model_id):
    # 1M 上下文判定：显式环境变量 > 型号 id 特征
    env = os.environ.get("HEALTH_CTX_WINDOW")
    if env:
        try:
            w = int(env)
            if w > 0:
                return w
        except ValueError:
            pass
    if model_id:
        mid = model_id.lower()
        for pat in ("1m", "[1m]", "2000k", "longcontext"):
            if pat in mid:
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
            if not isinstance(d, dict):
                continue
            u = (d.get("message") or {})
            if not isinstance(u, dict):
                continue
            u = u.get("usage")
            if isinstance(u, dict):
                total = (u.get("input_tokens") or 0) \
                    + (u.get("cache_read_input_tokens") or 0) \
                    + (u.get("cache_creation_input_tokens") or 0)
                if total > 0:
                    return total
        except ValueError:
            continue
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


def _ab_counts(cwd):
    """upstream 对比计数：返回 (behind, ahead)。无 upstream/失败 → (0,0) 由调用方省略。"""
    try:
        r = subprocess.run(["git", "rev-list", "--left-right", "--count",
                            "@{upstream}...HEAD"], cwd=cwd,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=2)
        if r.returncode != 0:  # 无 upstream / detached → 不显示
            return (0, 0)
        parts = r.stdout.decode("utf-8", "replace").split()
        if len(parts) < 2:
            return (0, 0)
        return (int(parts[0]), int(parts[1]))  # <behind> <ahead>
    except Exception:  # noqa: BLE001
        return (0, 0)


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
        behind, ahead = _ab_counts(cwd)
        ab = ""
        if ahead:
            ab += "\x1b[32m ↑%d\x1b[36m" % ahead
        if behind:
            ab += "\x1b[31m ↓%d\x1b[36m" % behind
        # 测试锁定前缀 "\x1b[36m ⎇ "（颜色码在前、空格在内）；可见输出与 " \x1b[36m⎇ " 相同
        return "\x1b[36m ⎇ %s%s%s\x1b[0m" % (branch, ab, dirty)
    except Exception:  # noqa: BLE001  git 失败/超时 → 隐藏段
        return ""


def cwd_segment(cwd):
    """工作目录段：仅目录名（叶子），缺失 → 空。"""
    try:
        if not cwd:
            return ""
        name = os.path.basename(os.path.abspath(cwd))
        return " \x1b[35m%s\x1b[0m" % name if name else ""
    except Exception:  # noqa: BLE001
        return ""


def work_segment(state, now=None):
    """工作时长段：⏱ 格式，时长决定颜色（<1h灰/≥1h黄/≥2h红底）。"""
    import time as _t
    now = int(_t.time()) if now is None else now
    try:
        # 动态导入：health-reminder 未安装时优雅降级
        import sys
        import os
        hl_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "health-reminder", "scripts")
        if hl_path not in sys.path:
            sys.path.insert(0, hl_path)
        import health_lib
        secs = health_lib.work_duration(state, now)
    except Exception:  # noqa: BLE001  health-reminder 未安装/调用失败
        return ""
    color = "90" if secs < 3600 else ("33" if secs < 7200 else "41;97")
    return " \x1b[%sm⏱ %s\x1b[0m" % (color, health_lib.fmt_work(secs))


def clock_segment(now=None):
    """时钟段：🕐 时分，23:00-06:00 暗红否则灰。"""
    import time as _t
    now = _t.time() if now is None else now
    lt = _t.localtime(now)
    hhmm = _t.strftime("%H:%M", lt)
    color = "31" if (lt.tm_hour >= 23 or lt.tm_hour < 6) else "90"
    return " \x1b[%sm🕐 %s\x1b[0m" % (color, hhmm)


def load_segment():
    """系统负载段：⚡ 1分钟均值，比率决定颜色（<0.7灰/≥0.7黄/≥1.0红）。非 Linux → 空。"""
    try:
        with open("/proc/loadavg", encoding="ascii") as f:
            one = float(f.read().split()[0])
        n = os.cpu_count() or 1
        ratio = one / n
    except Exception:  # noqa: BLE001  非 Linux/读失败
        return ""
    color = "90" if ratio < 0.7 else ("33" if ratio < 1.0 else "31")
    return " \x1b[%sm⚡%.1f\x1b[0m" % (color, one)
