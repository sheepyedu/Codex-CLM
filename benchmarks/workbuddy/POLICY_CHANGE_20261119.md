# WorkBuddy：去除题间主动压缩（2026-11-19）

正式串行入口已删除“上一题最终raw input ≥3MiB，或最近实际input ≥165,000 token，下一题前调用`thread/compact/start`”这项保护。两个阈值常量已从relay删除；`run.task_options`对两臂统一发出`compact:false`，不读取上一题压力值作为控制条件。新计划与逐题回执记录`context_policy: no-pre-task-compaction-v1`。

两臂继续使用自己的原thread、原生工具和独立CODEX_HOME。CLM仍由模型主动调用`clm-context`编辑API输入投影。这不删除CLI自身的活跃历史；原生Codex自动压缩仍可能发生。独立64MiB HTTP传输上限与模型窗口没有修改。容量探针的显式手动compact RPC仍可用；历史恢复操作器保留旧实验资格核验数值，不参与当前正式派发。

## 旧结果与新策略

已完成的65题是旧策略实验：CLM编辑3次、保护性原生压缩全程7次（选用成功尝试6次、失败分支成功压缩1次）、CLM自动压缩0次；原生基线自动压缩3次。删除阈值不改写旧轨迹和旧成绩，评分校正也不是新策略重跑结果。本次未启动新的作答、模型调用或Goal。

原科学源码快照、完整轨迹及原评分继续封存于`/mount-data/TeamShared/YangYang/rollouts/Codex-CLM/WorkBuddy-20261118`。新源码放在独立目录，不替换冻结source-environment-v6，不影响其他项目Codex。

## 验证

```sh
python3 benchmarks/check_workbuddy_no_guard.py
python3 -m unittest discover -s tests -v
```

零API回归覆盖两臂各4种压力，包括阈值边界和20MiB/2,000,000 token模拟历史：实际生产options函数接实际native turn driver的RPC记录器，均只执行initialize、thread/resume、turn/start，原thread及题面保持，无compact请求。另验证显式容量探针和原生自动压缩事件处理仍可用；CLM六项现有单测通过。此测试验证控制流，不宣称已验证新长链的实际provider容量。

详细[评分校正表](RESULTS_CORRECTED_20261119.md)与源码策略变化分开记录。
