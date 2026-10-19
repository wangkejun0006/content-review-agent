# 复杂虚构资料与契约边界

完整交互步骤见 [README](../README.md) 第3、4节。当前离线排练：

```bash
uv run --locked --extra dev python scripts/offline_demo.py --output .runtime/rehearsal-001/report.json
```

它通过原 ProductImportService、EvidenceImportService、PlatformRuleImportService、RegistryService、Worker 与 LangGraph 检查：V1/V2、冲突草稿、精确重复跳过、证据未验证拒绝激活、有限事实允许激活、无依据效果保留草稿、旧Run冻结、违规候选阻断、有界自动返工与脚本审核恢复。

本机安装预制案例必须使用单独实例，先setup，再demo-scenarios；参数和角色查看顺序见README。它不是从页面手工完成资料导入的证明。

模型端口的直连、Managed和连接测试仍共享原契约与预算校验。发布版推荐启动器只提供fake并安装HTTP门禁，不读取作者旧密钥或旧额度。通用适配代码的存在不等于本轮进行了真实验证或授权消费。

固定离线修改示例只证明指定模板路径；其他修改应人工编辑并核查。内容检查、引用及产品Claim不能替代真实来源验证。历史开发说明原样保留于 [历史文档](history/P0_IMPROVEMENTS.md)，其中旧命令不作为本候选操作指南。
