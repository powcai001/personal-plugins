# personal-plugins

个人 Claude Code 插件合集（个人 marketplace：`personal-plugins`）。一键安装：

```
/plugin marketplace add <本仓库地址或本地路径>
/plugin install 插件名@personal-plugins
```

## 插件一览

| 插件 | 一句话 | 前置 |
|---|---|---|
| [health-reminder](plugins/health-reminder/) | 定时提醒站起来、喝水、伸懒腰；Stop 横幅 + 倒计时 | 无（纯 python3） |
| [statusline](plugins/statusline/) | 单行状态栏：模型 · 上下文占比 · git · 健康倒计时 | 无；装 health-reminder 后多出 💧 段 |
| [claude-pet](plugins/claude-pet/) | 放置挂机电子宠物：Claude 干活 = 宠物成长 | node ≥ 18 |

## 推荐组合

```
/plugin install health-reminder@personal-plugins
/plugin install statusline@personal-plugins
/health start 45m        # 开提醒
/statusline setup        # 装状态栏（自动备份原有 statusLine）
```

## 仓库结构

```
├── .claude-plugin/marketplace.json   # marketplace 清单（三插件注册）
├── plugins/
│   ├── health-reminder/   # 健康提醒（CLI + Stop hook + 倒计时）
│   ├── statusline/        # 状态栏渲染器（四段，逐段降级）
│   └── claude-pet/        # 电子宠物（XP/进化/转生）
└── docs/superpowers/      # 设计文档(specs) + 实现计划(plans)
```

各插件自带 README 与测试（`python3 tests/*.py` / claude-pet: `node --test "test/*.test.js"`）。

## 卸载

`/plugin uninstall 插件名`；statusline 装过的先 `/statusline setup --remove` 恢复原状态栏。
