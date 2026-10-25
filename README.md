# 机器人机电执行器生产故障诊断 Agent

这是一个面向机器人机电执行器制造、装配和下线测试场景的可运行项目骨架。系统把工艺知识、历史故障经验和设备测量数据组织成一条可追踪的诊断链路，输出候选原因、证据、验证步骤、处置建议和安全提示。

项目采用 LangGraph 1.x 编排显式状态图，使用 LangChain 1.x 连接模型、结构化输出和工具。默认 `demo` 模式不需要 API Key，便于本地演示和测试；配置 OpenAI-compatible 模型后，会在相同流程内启用结构化 LLM 综合诊断。

## 诊断流程

```text
工程师提问 ---------\
                     > 输入校验 -> 基础知识检索 -> 拉取实时数据 -> 异常识别
产线报警装置 -------/                                      |
                                                            v
                                              生成数据增强检索语句
                                                            |
                                                            v
                                                精准检索解决办法
                                                            |
                                                            v
                                                结构化综合诊断报告
                                                            |
                                                   风险与证据闸门
                                                     /          \
                                               人工复核          自动完成
```

核心设计原则：

- 状态中保存原始事实和证据，不保存拼好的提示词。
- 安全联锁、绝缘耐压、过温等高风险判断不交给模型自由决定。
- 每条候选原因都必须绑定知识片段或测量证据；证据不足时明确列出待补数据。
- 读取型工具和写入型动作分离。本版本只有读取与建议，不会直接修改 PLC、MES 或设备参数。
- 高风险结论通过 LangGraph `interrupt()` 暂停，使用同一 `thread_id` 经人工确认后恢复。
- 工程师提问与设备报警共用同一套诊断图，避免维护两套判断逻辑。
- 知识库采用两次检索：先查基础标准，再用报警内容、实时数据和异常特征精准检索。

## 快速开始

推荐使用 Python 3.11+ 与 `uv`：

```powershell
Copy-Item .env.example .env
uv sync --extra dev
uv run actuator-agent demo
```

启动 API：

```powershell
uv run uvicorn actuator_fault_agent.api:app --reload --port 8000
```

发送诊断请求：

```powershell
$body = @{
  question = "EOL 测试时输出扭矩偏低，同时振动升高，请给出排查顺序"
  actuator_id = "RA-2407-018"
  station = "EOL-02"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/diagnoses `
  -ContentType "application/json" -Body $body
```

产线报警装置可以通过 webhook 主动触发 Agent：

```powershell
$alarm = Get-Content .\data\mock_alarm_event.json -Raw

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/alarms/events `
  -ContentType "application/json" -Body $alarm
```

如果 `.env` 配置了 `ALARM_WEBHOOK_TOKEN`，报警装置还需要发送
`X-Alarm-Token` 请求头。正式产线建议由 PLC 或检测设备先把事件发送给边缘网关、MES
或消息队列，再由适配器调用该 webhook，不建议让 PLC 直接访问 Agent 服务。

## 模型接入

将 `.env` 中的 `MODEL_MODE` 改为 `openai-compatible`，并设置模型名、地址和密钥。兼容服务可以是云端 API，也可以是企业内网的 vLLM、SGLang、Ollama 兼容网关或其他 OpenAI-compatible 服务。

```dotenv
MODEL_MODE=openai-compatible
MODEL_NAME=your-model-name
MODEL_BASE_URL=http://model-gateway.local/v1
MODEL_API_KEY=replace-me
```

## 目录

```text
src/actuator_fault_agent/
  api.py                 FastAPI 接口与中断恢复
  config.py              环境配置
  domain/                诊断数据模型和确定性规则
  graph/                 LangGraph 状态、节点和编排
  retrieval/             本地可解释检索器
  services/              模型、测量数据与工具适配
  skills/                报警事件接入能力
knowledge/               可替换的示例工艺知识
data/                    模拟测量数据
tests/                   规则与检索单元测试
docs/                    架构、接入和评测说明
```

## 生产化替换点

当前仓库刻意把外部系统放在适配器边界：

1. 用 MES、EOL、SCADA 或时序数据库适配器替换 `JsonTelemetryRepository`。
2. 用企业知识库的混合检索与重排器替换本地检索器，同时保留统一的 `Evidence` 输出。
3. 将内存 checkpointer 换成 PostgreSQL，保证跨进程恢复和审计。
4. 接入 LangSmith 或企业 OpenTelemetry 平台，记录节点耗时、检索命中、模型版本和人工反馈。
5. 将示例阈值替换为产品型号、工位和工艺版本对应的受控参数；阈值必须经过质量和工艺人员批准。
6. 将报警 webhook 前置到企业 API 网关或消息队列，并用事件编号实现持久化去重。

更详细的设计见 [架构说明](docs/architecture.md) 与 [接入指南](docs/integration.md)。

## 安全边界

本项目输出的是诊断建议，不替代锁定挂牌、设备安全规范、质量放行流程或现场工程师判断。示例知识和阈值只用于软件演示，不能直接用于实际生产放行。

