# P0 改造与离线验收
本轮只修改独立脱敏副本；原仓库只读，没有推送或公开，没有新增真实模型调用。
此前真实模型报告保持原样，本报告不把 fake 输出作为模型能力证据。

## 复杂虚构资料与原流程
demo/materials/ 提供规格 V1、冲突供应商便笺、人工确认 V2、有限范围证据、
无证据宣传草稿、当前/历史规则，以及第二种桌面配件。材料没有真实公司数据。

排练通过原 ProductImportService、EvidenceImportService、PlatformRuleImportService、
IngestionDedupService、RegistryService、ProductMediaService、KnowledgeService、
RunService、ReviewService、Worker 和 LangGraph 执行：
1. 导入确认 V1（96 页）并由脚本扮演审核员激活。
2. 同 SKU 的冲突资料形成新 Revision 草稿，保留警告，不覆盖权威版本。
3. 相同资料再次上传，在调用模型前被精确去重阻断。
4. 人工选择确认 V2（120 页），旧 Run 固定 V1，新 Run 固定 V2。
5. 证据先保持未验证，Claim 激活失败；脚本验证有限范围证据后激活“120 页”。
6. 没有证据的效率/防水 Claim 保留草稿，不进入后续 Run。
7. 生成带虚构标识的几何示意图，经原图片校验与存储服务关联产品。
8. 导入虚构规则，过期来源产生提醒；不是实际平台政策。
9. 三个候选走原合规、评分和有界返工；一个违规稿修正，一个仍有 blocker。
10. blocker 审批被拒；脚本要求修改安全候选，重新合规评分后再次待审，再批准。

警告和候选模型输出由显式确定性 fixtures 提供；这些断言证明流程和业务约束，
不证明模型能发现任意冲突、审核准确率或实际产品效果。证据真实性和支持范围仍需人工审核。
ReviewService 的脚本调用不代替 API 角色鉴权；角色权限由原 API 回归另行验证。

## 统一模型入口
- factory 的直连与 fake 使用 GovernedLLMGateway；Managed 也调用同一个 Registry 校验器。
- 统一核对用途、代码响应类型、Prompt Schema、品牌、用途 Key 和已激活版本。
- 运行中的历史 Prompt 可以是 retired；draft 或其他品牌 Prompt 在 HTTP 前被拒绝。
- 合规语义用途保留原 Key xhs_compliance，不能误当作 xhs_compliance_semantic Key。
- 连接测试使用固定 LLMProviderTestOutput 契约，无业务 Prompt；同样经过传输预算。
- Managed 和连接测试复制完整父 Settings，只覆盖供应商地址、模型和内存凭据。
  不重新读取 .env，也不丢失预算、输出上限、超时和网络重试设置。
- 所有付费 HTTP 都在同一适配器中先占用预算槽位；429/网络重试、Schema 降级、
  JSON 修复各算一次请求。路径与输出上限不能设为 None 绕过预算。
- 默认每响应输出上限 4096，默认禁止未知网络结果自动重试。
  仍允许有界格式降级/修复，它们也消耗预算；次数限制不是供应商金额限额。
- 超时、传输错误和取消保留占用；结果未知不退款；台账不可用时在发送前停止。
- fake 不发送付费 HTTP，不消费真实台账；离线测试拒绝外部 HTTP transport。
- 本地文件锁适用于同机 Linux/WSL 多进程；不声称支持多主机分布式预算。
  多实例部署必须共享同一台账及一致上限；不能给每实例各配独立预算然后称全局限制。

复杂违规资料还暴露了原合规流程的 UUID 序列化问题。本轮仅将送入 LLM 的
确定性 Finding 转成 JSON 类型，数据库内部仍保留 UUID。原并行图保持不变。
诊断时的 SQLite 锁错误是图异常后的次生问题；临时调度限制已经撤掉。

## 运行
临时 SQLite 零付费排练：
```bash
uv run --locked --extra dev python scripts/offline_demo.py
```
生成 reports/p0-offline-demo.json，临时数据库结束后销毁。
它使用 InMemorySaver，不证明跨进程恢复；不改变现有 PostgreSQL 中的历史业务记录。

向已初始化的本地虚构应用追加场景：
```bash
uv run --locked --extra dev python scripts/local_runtime.py demo-scenarios --mode fake --max-calls 40
uv run --locked --extra dev python scripts/local_runtime.py serve --mode fake --max-calls 40
```
安装记录位于忽略的 .runtime/p0-installed.json，成功后重复执行返回已有记录。
安装器使用 PostgreSQL checkpointer；发现部分安装而缺少完成记录时停止，不自动覆盖。
本轮最初排练形成的待审样例已另外补齐 PostgreSQL 检查点。
需要继续在界面处理待审任务时，在另一个终端启动 fake Worker：
```bash
uv run --locked --extra dev python scripts/local_runtime.py worker --mode fake --max-calls 40
```
40 仅沿用已有台账上限，fake 不消费请求。本轮不启动常驻 Worker。
后续真实验证应先明确新预算；不要删除台账清零或把 fake 切换成 real 后自动运行。

## 查看顺序
- 产品中心：NOTE01 的 V1、冲突草稿、V2，以及 CLIP02 与产品示意图。
- Claim/证据：已激活的页数 Claim，与仍为草稿的效率/防水 Claim。
- 运行与审核：P0 旧版本快照任务，以及已完成修改与批准的新版本任务。
- 候选详情：违规版本、合规 Findings、返工后的 Content Version 和评分记录。
- 规则页面：虚构当前规则及带 2020 日期的历史来源。
- 审计页面：导入决策、版本激活和审核记录；脚本操作者不是现实人工审核。

回归与精确结果见 reports/p0-validation.json。之前 reports/session-validation.json
和 live-e2e*.json 记录的是上一轮事实，不能把它们的真模型结论自动推广到本轮新增分支。

安装后的资料已形成演示记录，再次上传会触发去重提示。需要从头重演时用临时 SQLite
排练脚本；不要清空现有演示数据库或删除真实请求台账。
