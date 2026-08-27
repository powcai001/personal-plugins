---
description: 查看 claude-pet 电子宠物状态，并进行摸头、喂食、转生等互动。用户提到"宠物""摸头""喂食""转生"时使用。
---

# claude-pet 宠物面板

运行 `claude-pet status`（在 Bash 中直接可用，无需路径），把输出原样放进代码块展示给用户，不要改写数字。

然后按用户意图操作（每个动作都是一次独立的 Bash 调用，运行后把输出原文展示给用户）：

- 摸头 → `claude-pet pet`
- 喂零食（+经验）→ `claude-pet feed`
- 转生（需 Lv.45）→ `claude-pet rebirth`
- 学新知识 → 让 Claude 现场生成 5 条科技史小知识（用户没指定主题时自选有趣主题），
  去重后追加到 `/home/plugin/plugins/statusline/data/tech_facts.json` 的 facts 数组
  （原子写：tmp+rename；每条 {"y": 年份int, "t": "≤14字"}；与现有 t 重复的丢弃），
  然后运行 `claude-pet feed` 喂食一次作为奖励，并把新增条目展示给用户
- 只看状态 → 无需额外命令

用户没说具体动作时，只展示面板，然后一句话列出可做的事（摸头/喂食/转生/学新知识）。

若命令报"状态文件忙"或"还没有宠物档案"，如实转告：档案会在下一次对话开始时自动创建。
