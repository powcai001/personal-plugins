#!/usr/bin/env python3
"""statusline 插件 setup CLI 测试。运行: python3 tests/test_setup_cli.py"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "..", "scripts", "statusline_cli")

FAILURES = []


def run_test(fn):
    try:
        fn()
        print("  PASS %s" % fn.__name__)
    except Exception as e:  # noqa: BLE001
        FAILURES.append(fn.__name__)
        print("  FAIL %s: %s" % (fn.__name__, e))


def env_pair():
    d = tempfile.mkdtemp(prefix="sl-cli-")
    home = tempfile.mkdtemp(prefix="sl-home-")
    os.makedirs(os.path.join(home, ".claude"))
    settings = os.path.join(home, ".claude", "settings.json")
    env = dict(os.environ, HOME=home,
               HEALTH_STATE_DIR=os.path.join(d, "state"))
    return d, settings, env


def run_cli(args, env):
    r = subprocess.run([sys.executable, CLI] + args, capture_output=True,
                       text=True, env=env, timeout=10)
    return r.returncode, r.stdout.strip()


def test_setup_clean_and_remove():
    d, settings, env = env_pair()
    with open(settings, "w") as f:
        json.dump({"other": 1}, f)
    rc, out = run_cli(["setup"], env)
    assert rc == 0 and "已安装" in out
    with open(settings) as f:
        st = json.load(f)
    assert st["statusLine"]["command"].endswith(
        "plugins/statusline/scripts/statusline".replace("plugins/", "", 1)
    ) or st["statusLine"]["command"].endswith("/statusline")
    assert st["other"] == 1
    with open(os.path.join(d, "state", "statusline_backup.json")) as f:
        assert json.load(f)["statusLine"] is None  # 无原值 → 备份 None
    rc, out = run_cli(["setup", "--remove"], env)
    assert rc == 0 and "移除" in out
    with open(settings) as f:
        assert "statusLine" not in json.load(f)


def test_setup_upgrade_and_backup_preservation():
    d, settings, env = env_pair()
    # 首次：有原值 powerline
    with open(settings, "w") as f:
        json.dump({"statusLine": {"type": "command", "command": "npx powerline"}}, f)
    rc, out = run_cli(["setup"], env)
    assert rc == 0 and "已替换" in out
    with open(os.path.join(d, "state", "statusline_backup.json")) as f:
        assert json.load(f)["statusLine"]["command"] == "npx powerline"
    # 旧包装器在位 → 升级不覆盖备份
    with open(settings, "w") as f:
        json.dump({"statusLine": {"type": "command",
                                  "command": "python3 /x/health_statusline"}}, f)
    rc, out = run_cli(["setup"], env)
    assert rc == 0 and "升级" in out
    with open(os.path.join(d, "state", "statusline_backup.json")) as f:
        assert json.load(f)["statusLine"]["command"] == "npx powerline"
    # --remove 恢复最早原值
    rc, out = run_cli(["setup", "--remove"], env)
    with open(settings) as f:
        assert json.load(f)["statusLine"]["command"] == "npx powerline"


def test_path_subcommand():
    _, _, env = env_pair()
    rc, out = run_cli(["path"], env)
    assert rc == 0 and out.endswith("/statusline")


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items())
              if k.startswith("test_") and callable(v)]
    for _t in _tests:
        run_test(_t)
    print("\n%d/%d 通过" % (len(_tests) - len(FAILURES), len(_tests)))
    sys.exit(1 if FAILURES else 0)
