<!-- 中文：内部上线范围和 DevOps 上线计划，定义 v0.1 生产就绪边界、验收标准和执行路线。 -->
<!-- English: Internal launch scope and DevOps launch plan defining v0.1 production readiness boundaries, acceptance criteria, and execution path. -->

# Origami Mini PIC 2.0 DevOps Platform Production Readiness

语言/Language：中文 | [English](PRODUCTION_READINESS.en.md)

## 上线范围

### 上线对象

Origami Mini PIC 2.0 DevOps Platform for Carry & Go developers.

### 上线目的

为 Carry & Go 开发者提供一个内部可访问的仿真验证平台，用于运行 PIC 2.0 pipeline、执行 Carry & Go 场景测试、查看 benchmark / audit / observability 结果，并在不依赖真实机器人和真实传感器数据的情况下进行开发前验证。

### 本次上线不包含

1. 不直接控制真实 Carry & Go 机器人。
2. 不接入生产机器人指令链路。
3. 不替代真实硬件测试。
4. 不作为最终模型训练平台。
5. 不处理真实用户隐私数据或客户数据。

## v0.1 成功标准

v0.1 上线成功意味着平台可以作为内部开发者仿真验证服务稳定使用，而不是作为机器人安全关键控制系统使用。

- 开发者可以通过内部网络访问 Dashboard 和 API。
- 开发者可以运行 smoke、scenario suite、multi-step scenario、benchmark 和 audit verification。
- Dashboard 可以展示 scenario、benchmark、audit、run history 和 observability 结果。
- 每次由平台触发的运行都有 run history、artifact 快照和 audit 记录。
- CI 质量门在发布前保持通过：lint、unit/smoke tests、scenario suite、benchmark、audit verification。
- 运行数据只来自仿真场景、测试配置或开发者手工构造输入。
- 平台失败不会影响真实机器人、生产指令链路、客户数据或隐私数据。
- 服务可以被回滚到上一个已知可用版本。

## 风险边界

| 领域 | v0.1 决策 |
| --- | --- |
| 机器人控制 | 禁止连接真实机器人控制链路。 |
| 传感器输入 | 只允许仿真、fixture、YAML 场景和开发者手工输入。 |
| 用户数据 | 禁止导入真实用户隐私数据或客户数据。 |
| 模型训练 | 只做开发前验证，不做最终训练平台。 |
| 安全结论 | 场景测试结果只能作为开发前信号，不能替代硬件测试或安全认证。 |
| 外部访问 | 仅允许内部网络或受控 VPN 访问。 |

## DevOps 上线计划

### Phase 0: 冻结上线边界，1 天

目标：确保团队对 v0.1 能做什么、不能做什么有同一套定义。

工作项：

- 评审本文档的上线范围和非范围。
- 明确 v0.1 的使用者：Carry & Go developers。
- 标记所有 Dashboard/API 文案，避免暗示平台可控制真实机器人。
- 在 issue tracker 中创建 v0.1 launch epic，并把后续 phase 拆成可追踪任务。

验收标准：

- 本文档经过项目 owner 接受。
- 所有 v0.1 任务都能映射到本文档的上线范围。

### Phase 1: 服务边界和访问安全，3-5 天

目标：让平台可以安全地暴露给内部开发者。

工作项：

- 为 API 增加最小鉴权，优先保护 `/runs/*`、`/api/scenarios/*`、`/api/history/*`、`/api/audit/*` 和 `/api/reports/*`。
- 从环境变量读取 API token、artifact root、Grafana URL、环境名和日志级别。
- 增加 CORS/host 策略，只允许内部域名或内部网关访问。
- 将 health 和 metrics 的访问策略单独定义，确保 Prometheus 可以抓取。
- 记录关键操作的 actor、request id、run id、时间戳和来源 IP。

验收标准：

- 未认证请求不能触发运行、修改场景或读取 audit/history/report。
- Prometheus 仍可以抓取 `/metrics`。
- 本地开发模式和内部部署模式都有清晰启动方式。

### Phase 2: 生产镜像和部署配置，3-5 天

目标：从本地开发 compose 过渡到可部署服务。

工作项：

- 将 Dockerfile 改为生产镜像：固定基础镜像版本、非 root 用户、不依赖源码挂载、安装锁定依赖。
- 保留本地 `docker-compose.yml`，新增生产部署配置，例如 `docker-compose.prod.yml` 或环境对应部署模板。
- 固定 Prometheus/Grafana 镜像版本，避免使用 `latest`。
- 关闭生产 Grafana anonymous admin，改用内部 SSO、反向代理鉴权或受控只读账号。
- 配置持久卷：artifacts、run history、audit、Prometheus data、Grafana data。
- 增加 resource limits、restart policy、healthcheck 和只读挂载。

验收标准：

- 生产镜像不需要挂载项目源码即可启动。
- `api`、`prometheus`、`grafana` 都有固定版本和健康检查。
- 部署重启后 artifacts/history/audit 不丢失。

### Phase 3: 运行可靠性和数据持久化，1 周

目标：多人内部使用时，运行记录可靠、可追溯，不互相覆盖。

工作项：

- 给 scenario、multi-step scenario 和 benchmark 运行分配唯一 run id。
- 将每次运行写入独立 artifact 目录，再更新 latest report 指针或索引。
- 增加文件锁或任务队列，避免并发运行写同一个 report/audit/event 文件。
- 将 audit/history 从“最新文件视图”升级为稳定索引，v0.1 可用 SQLite 或 append-only JSONL。
- 增加 artifact retention policy，例如保留最近 30 天或最近 500 次运行。
- 将 Dashboard 自定义场景写入持久 artifact/config 目录，生产镜像内置 `configs/scenarios` 保持只读。
- 增加结构化错误响应和输入 schema，减少宽松 `dict[str, Any]` 造成的无效运行。

验收标准：

- 两个开发者同时触发运行时不会覆盖彼此结果。
- 任意历史 run 可以从 Dashboard/API 中追溯到输入、输出、事件和 audit 记录。
- 旧 artifact 有清理策略，不会无限增长。

### Phase 4: CI/CD 和发布控制，1 周

目标：每个版本都可构建、可扫描、可部署、可回滚。

工作项：

- 整理 GitHub Actions，保留一条权威质量门。
- 在 CI 中构建生产镜像。
- 增加依赖漏洞扫描、镜像扫描和基础 SBOM 输出。
- main 分支合并后运行 staging smoke check。
- tag 或 release 后通过 `internal-production` environment 手动批准。
- 发布时记录版本号、git SHA、镜像 digest / image ID、迁移说明和回滚命令。

验收标准：

- staging 自动部署并运行 smoke/health check。
- production 部署需要人工批准。
- 任意版本可以在 15 分钟内回滚到上一个已知可用版本。

### Phase 5: Observability 和运维响应，3-5 天

目标：上线后问题能被发现、定位和处理。

工作项：

- 定义 v0.1 SLO：API availability、run success rate、scenario pass rate、benchmark quality gate、audit validity、API p95 latency。
- 将 Prometheus 告警接入 Slack、Email 或团队现有告警渠道。
- 增加 JSON structured logs，并贯穿 request id / run id。
- 为常见故障写 runbook：API down、quality gate failed、artifact volume full、Grafana unavailable、audit verification failed。
- 备份并演练恢复 artifacts/history/audit。

验收标准：

- 关键告警能到达负责渠道。
- 发生质量门失败时，开发者能在 Dashboard 中看到失败原因并定位 artifact。
- 运维人员可以按 runbook 完成重启、回滚、清理和恢复。

### Phase 6: 内部试运行和 v0.1 发布，1 周

目标：小范围验证真实开发流程，然后正式开放给 Carry & Go developers。

工作项：

- 在 staging 环境连续运行 5 个工作日。
- 每天自动跑 smoke、scenario suite、multi-step scenario、benchmark 和 audit verification。
- 邀请 2-3 位 Carry & Go 开发者试用 Dashboard 和 scenario builder。
- 记录试运行期间的 bug、误导性文案、性能问题和操作缺口。
- 完成 v0.1 release checklist，发布到 internal production。
- 发布后观察 48 小时，确认无 blocker 后扩大使用范围。

验收标准：

- 试运行期间无 P0/P1 阻塞问题。
- 质量门连续通过。
- 至少 2 位目标开发者完成一次 scenario 或 benchmark 工作流。
- v0.1 release notes、rollback plan 和 runbook 都已归档。

## v0.1 上线检查表

### Scope

- [x] 上线对象限定为 Carry & Go developers。
- [x] 平台定位限定为内部仿真验证。
- [x] 明确不连接真实机器人控制链路。
- [x] 明确不处理真实客户数据或隐私数据。

### Security

- [x] API/Dashboard 写操作已鉴权。
- [x] Report、audit 和 history 读取策略已定义。
- [x] Grafana 生产环境不使用 anonymous admin。
- [x] Google Workspace SSO 反向代理模板已提供：oauth2-proxy + Nginx。
- [x] API 可要求可信代理注入用户身份 header。
- [ ] Google OAuth client、公司域名和可选 Google Group 策略已在真实环境配置。
- [ ] 生产环境只允许内部网络或 VPN 访问。
- [x] 关键操作记录 actor 和 request id。

### Deployment

- [x] 生产镜像不依赖源码挂载。
- [x] 容器以非 root 用户运行。
- [x] 镜像版本固定，不使用 floating tag。
- [x] prod compose/chart 和 dev compose 分离。
- [x] artifacts/history/audit 使用持久卷。

### Reliability

- [x] 每次运行有唯一 run id。
- [x] 并发运行不会覆盖 artifact。
- [x] 历史 run 可以追溯输入、输出、事件和 audit。
- [x] artifact retention policy 已启用。
- [x] Dashboard 自定义场景写入持久配置目录，不修改生产镜像内置场景。
- [ ] 回滚流程已验证。

### Quality

- [x] `make quality` 通过。
- [x] scenario suite 通过。
- [x] multi-step scenario suite 通过。
- [x] benchmark quality gate 通过。
- [x] audit verification 通过。
- [x] 本地 production compose smoke check 通过：API healthy、自定义场景创建和运行。
- [x] CI release gate 已包含 staging smoke check。
- [x] CI release gate 已包含生产镜像构建、依赖扫描、镜像扫描和 SBOM。
- [x] tag release 已绑定 internal-production 手动审批 environment。
- [x] release manifest 会记录版本、git SHA、镜像标识、迁移说明和回滚命令。
- [x] 真实 staging 准备包已存在：env 模板、部署 runbook、主机预检、OAuth 单账号 allowlist 清单、SSO smoke 脚本。
- [ ] 真实 staging SSO smoke check 通过。
- [ ] 真实 staging 浏览器登录和用户隔离验收通过。

### Operations

- [ ] Prometheus 抓取 API 指标。
- [ ] Grafana dashboard 可访问。
- [ ] 关键告警接入团队渠道。
- [x] structured logs 包含 request id / run id。
- [x] staging deploy / smoke / rollback runbook 已写完。
- [ ] runbook 已在真实 staging 上演练。
- [x] artifacts/history/audit 有备份恢复说明。

## 发布节奏建议

| 周期 | 目标 | 主要交付 |
| --- | --- | --- |
| Week 1 | 安全边界和部署基础 | 鉴权、环境配置、生产 Docker/Compose、范围文档 |
| Week 2 | 运行可靠性 | run id、并发保护、持久化、retention、输入 schema |
| Week 3 | CI/CD 和运维 | 镜像构建、扫描、staging deploy、告警、runbook |
| Week 4 | 试运行和发布 | 内部试用、bug fix、release checklist、v0.1 发布 |

## 当前上线判断

以本文档定义的 v0.1 范围来看，项目已经具备内部开发者仿真验证平台的核心雏形：pipeline、scenario suite、multi-step runner、benchmark、audit、Dashboard、Prometheus/Grafana 配置和 CI 质量门都已存在。

主要剩余风险不在机器人安全控制，而在内部服务生产化：鉴权、生产镜像、持久化、并发安全、发布流水线、告警和运维流程。完成上述 phase 后，可以把 v0.1 定位为内部 production-ready developer validation platform。
