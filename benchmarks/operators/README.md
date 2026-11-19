# 本轮固定实验的恢复操作脚本

这些脚本保存本次WorkBuddy续测的实际管理入口，不改变原生Codex SDK、模型、题面或安全元数据。原模型请求、拒绝、失败历史和工作区均保留。

脚本中的路径固定为H20隔离实验根 `/mount-data/Codex-CLM/experiments/workbuddy-codex-20261118`。部署时将相应文件原样复制到该实验根再执行；不要直接从本目录启动，也不要覆盖正在运行的源码快照。脚本和用户确认记录的SHA写入运行计划。

- `resume_after_user_confirmed_access.py`：用户明确表示当前账号获准运行原批评测后，从固定的native61检查点发起一个新的受控尝试，后端仍经原SDK正常执行安全检查。它不会把原始cyber_policy错误当作临时错误；再次拒绝立即停止。用户确认是陈述来源，不等于独立取得服务商批准文件，也不得用脚本伪造授权。
- `start_resume66_owner.sh`：该次用户发起续测的排他owner，保留120条已评分前缀、完整当前home及原两thread。首次原配置实际获得14个完整响应/13条命令后遭遇流超时，原尝试原样封存。
- `qualify_stream_timeout_v6.py`：对明确的真实上游流超时运行零模型API资格回归，包含旧恢复用例、真实Docker检查点恢复、CLM投影复原、原始policy负例，以及错误信息含timeout时policy仍不可重试的负例。
- `start_resume67_owner.sh`：仅在source-v6资格通过后，使用正常临时故障恢复入口从上述流超时检查点继续，不重播已执行动作。

source-v6与source-v5的运行文件只有 `relay.py` 的两条显式超时消息匹配不同。请求字段、安全元数据和错误代码allowlist保持，原始policy checkpoint仍不符合自动恢复条件。后续任何新的policy拒绝都应停止，不能删字段、改历史或换通道规避。

本目录是已实际采用的实验恢复入口留档；完整65题和130条结果是否完成，应以真实accepted、独立题面/会话/评分绑定核验及最终交付证据判断。
