# 强制题中编辑 Context

这是 WorkBuddy 串行控制器的可选插件。普通 Codex CLM 负责作答，控制器在每两道题取得有效评分后，打开一个独立的英文上下文整理回合。题目得零分也计为已回答。两种回合复用同一条原生 Codex thread。采用上一轮 50 题原顺序（Code 20、Office 12、Web 18），共 50 个评分回合和 25 个整理阶段，包括第 50 题后的收尾整理。

完整英文提示在 [plugin.py](plugin.py) 的 `PROMPT` 中。模型要先查看 `clm-context status`，选择本回合开始之前的旧工具交换，用 `clm-context edit --drop … --note …` 提交编辑，再检查状态。CLM 的编辑修改后续 API 输入投影。作答中的自发编辑和 Codex 自身的自动压缩仍可发生。此分支的正式入口运行 CLM 加插件一组，不挂载上一轮 skill，沿用无 165,000 token／3 MiB 题间主动压缩策略。

## 调度与验收

1. 每题沿用原 WorkBuddy 试题、隔离镜像、评分器和可恢复的串行作答入口。
2. 整理阶段使用独立的无外网、非 root 容器和空工作区，带入上一个已完成单元的 HOME 和 CLM 状态快照。控制器发送专用 `turn/start`。本阶段的工作区和挂载均不含下一题。
3. 控制器检查同 thread 的原生回合完成事件、模型发出的编辑命令、网关接受的编辑和实际投影。至少一次已生效的编辑必须移除整理回合之前的完整工具交换。相同请求的成功终态、传输结果和原始／已发送请求的哈希均留档。只回复“已整理”、只清理本回合的工具输出或编辑被拒时，下一题保持阻塞。
4. 通过验收后才把该次整理的会话和 CLM 状态交给下一题。最后一对题也要通过整理验收，之后才写入全轮完成回执。整理回合独立计费和统计，不计入题目数或评分分母。

## H20 入口

```sh
prior=/mount-data/Codex-CLM/experiments/workbuddy-clm-skill50-20261120/run
experiment=/mount-data/Codex-CLM/experiments/workbuddy-forced-context-20261121
# 一次性准备。验证旧计划、全部题面／任务配置、50 个任务镜像和原生二进制。
benchmarks/forced_context_edit/h20.sh prepare "$prior" "$experiment/formal50"
# 使用已准备的计划开始正式运行，或继续已经验收的前缀。
benchmarks/forced_context_edit/h20.sh run "$experiment/formal50"
```

准备只冻结实验配置。启动时会再次核对计划、代码、运行时和评分环境配置。一次只允许一个控制器写入同一运行目录。已提交的单元按回执校验并跳过。整理阶段的失败尝试留在独立副本，下次调用从已验收的前一单元重试。遇到状态不明的作答尝试时，控制器停止并保留现场供恢复。

## 证据

- `units.json` 记录按时间顺序提交的 task 和 maintenance 单元。正式完成条件为 75 个单元，`accepted.json` 记录题目数和整理次数。
- `clm/evidence/`、`clm/trials/` 保留正常作答与评分证据，`clm/failed-attempts/` 保存历史失败。
- `maintenance/NNN/attempt-*/` 独立保存提示词、原生会话事件、原始与已发送的 API 请求、响应、编辑状态及用量。其父目录的 `receipt.json` 指向被采纳的尝试。失败仍有可检查的轨迹。
- 零 API 回归使用 `python3 -m unittest discover -s tests -v`。真实冒烟入口 `h20.sh smoke 新目录` 使用三道合成小题，验证第 2 题后实际编辑和第 3 题首个请求继承短记忆。
