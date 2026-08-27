# 自写状态栏渲染器设计（statusline renderer）

- 日期：2026-08-27
- 状态：设计已评审通过（对话内确认），待实现
- 项目位置：`/home/plugin/plugins/health-reminder`（作为既有插件的新组件，非新插件）
- 前置：health-reminder v0.1.1 已完成并安装（本设计复用其 health_lib 与 setup 机制）

## 目标

用一个纯 python3 状态栏渲染器替换 npx powerline：单行、信息密度高、~40ms 刷新、
显示 模型 / 上下文占比 / git 分支 / 健康倒计时。不显示花费（用户明确不要）。

## 布局（单行）

```
 ✱ opus-5 │ ▓▓▓▓▓▓░░░░ 62% │ ⎇ feat/health-reminder✱ │ 💧 32m
```

## 段规格

| 段 | 数据源 | 渲染 | 隐藏条件 |
|---|---|---|---|
| 模型 | stdin JSON `model.display_name` | ` ✱ <小写名>` | display_name 缺失 |
| 上下文占比 | transcript_path 最后一条含 usage 的 assistant 记录：`(input_tokens + cache_read + cache_creation) / 窗口` | ` ▓×n░×(10-n) NN%`（n=floor(pct/10)） | transcript 读不到或无 usage 记录 |
| git | `git branch --show-current <dir>`（dir=workspace.current_dir，2s 超时）+ `git status --porcelain` 非空→`✱`后缀 | ` ⎇ <branch>✱?` | 非 git 仓库 / 命令失败 / 超时 |
| 健康 | health_lib.load_state + compute（复用现有四态逻辑与配色） | ` 💧 32m` / 红底 ` 🚨 站起来·喝水·伸懒腰 ` / ` ⏸ 45m` | 状态文件不存在（未启用） |

分隔符 ` │ `（dim 灰色）。

### 上下文占比细则

- 分母（上下文窗口）默认 200000，按 stdin JSON `model.id` 映射：
  含 `1m`（不区分大小写）→ 1000000；其余（含缺失）→ 200000
- 百分比 = tokens/分母×100，保留整数（四舍五入）；>100% 时显示实际值（如 `120%`），进度条满格
- 配色：pct<60 绿（color 2 / 24-bit `#5f875f` 兼容 256 色 `71`）、60≤pct<85 黄（`178`）、pct≥85 红（`167`）、
  进度条与百分数同色
- 窗口映射放独立函数 `window_for(model_id) -> int`，便于测试与未来扩充

### ANSI 细节

- 每段独立着色，段间分隔符 `\x1b[90m │ \x1b[0m`
- 模型段 dim（`\x1b[90m`→白 `\x1b[97m` 二选一：用 97 保证深色背景下可读）；git 段青色（`\x1b[36m`）
- 健康/占比段按上文配色；行尾统一 `\x1b[0m` 复位
- 输出以 `\n` 结尾（statusline 协议要求整行）

## 组件与数据流

```
Claude Code ──stdin JSON──▶ scripts/statusline
                              ├─ model 段：stdin 直接取
                              ├─ ctx 段：stdin.transcript_path → tail 扫描最后 usage
                              ├─ git 段：subprocess git（cwd=stdin.workspace.current_dir）
                              └─ health 段：health_lib（同目录 import）
                           ◀─ 单行 ANSI 输出
```

- 新文件：`plugins/health-reminder/scripts/statusline`（可执行，python3 标准库）
- 修改：`health_lib.cmd_setup`——安装的 statusLine 命令改为
  `python3 <插件脚本目录>/statusline`（`__file__` 推导，不硬编码 /home/plugin）；
  备份/回滚机制不变（备份里存的是用户原 statusLine=powerline，--remove 仍还原）
- 现有 `scripts/health_statusline`（包装器）保留不删：已用包装器的用户不受影响；
  本机切换方式 = 再次 `/health setup`（setup 幂等：检测到命令已指向本插件任一脚本则先还原再装新）

## setup 幂等调整

cmd_setup 安装前检查当前 statusLine.command：
- 含 `health_statusline` 或 `statusline`（本插件脚本名）→ 视为已在位，直接改写为新渲染器命令
  （不是报"已在位"跳过，而是升级到新命令，保证老安装平滑迁移）
- 否则备份原值后安装

## 错误处理（降级链）

- stdin JSON 解析失败 → 渲染纯健康段（唯一无外部依赖的段）
- transcript 文件缺失/无 usage 记录/JSON 行损坏 → 跳过该行继续扫描（tail 向前最多扫 500 行），
  全部失败则隐藏占比段
- git 失败/超时（2s）→ 隐藏 git 段
- health_lib 导入失败（理论不可能，同目录）→ 隐藏健康段
- 顶层 try/except：任何未捕获异常 → 输出空行（绝不让 Claude Code 报错）
- 性能预算：整链 < 150ms（无 node 进程；git 两次调用是大头，加 2s 超时上限）

## 测试（tests/test_statusline.py，无框架断言脚本）

1. window_for 映射（1m→1000000、常规→200000、缺失→200000）
2. 占比与进度条：62%→6 格、99%→9 格、120%→满格+120%、0%→0 格
3. 占比三色阈值（59/60/85 边界）
4. ctx 扫描：构造临时 jsonl（末行无 usage、倒数第二条有）→ 正确取值；空文件→隐藏段
5. git 段：临时 git 仓库有 dirty→`✱`；非 git 目录→整段隐藏（用 subprocess 真跑）
6. 健康四态复用：not-due/due/paused/disabled（复用 make_state/tmp_env 既有 helper，
   从 test_health_lib.py import 或复制最小 helper，实现计划中定）
7. 端到端：echo 完整 stdin JSON | statusline → 输出含全部四段；损坏 stdin → 仍有健康段
8. setup 迁移：预置 statusLine=health_statusline 命令 → setup 后变为新渲染器命令且备份不丢

## v2 候选（不做）

花费段、会话时长、输出 token 速率、24-bit 真彩探测、powerline 兼容主题包。
