# Project Tracker Requirements Architecture

Status: current design and boundary document for `pt req`. Implementation details should be checked against `tracker/requirements.py` and `tracker/commands/req_cmd.py`.

这份文档定义 `pt req` 模块的目标、边界和落地方式。它解决的不是“再加几个 Markdown 模板”，而是把硬件项目的需求链路平台化，同时保持项目正文文档仍然归属于各自项目仓库。

## 1. 要解决的问题

当前 A57/CAMRX 的实践已经证明，硬件项目真正缺的不是单份需求文档，而是一条可持续复用、可追溯、可校验的需求主链路：

`根本目的 -> 系统原则 -> 业务场景 -> 平台能力 -> 工程约束 -> 接口定义 -> 原理图实现 -> PCB实现 -> 样机/调试 -> 验证项 -> 发布结论`

现状问题：

1. 这条链路目前主要靠人工记忆和手工复制模板。
2. 不同项目会逐步长出相似结构，但没有统一的生成、校验、索引机制。
3. 如果把项目正文直接写进 `project-tracker`，会破坏项目边界，导致工具仓和项目仓职责混乱。
4. 当前 `pt` 已经有 `docs/review/gate/prompt`，但缺少“需求阶段”这一层的系统抽象。

因此，`pt req` 的目标不是替代项目文档仓，而是：

- 提供统一需求范式和模板骨架
- 在目标项目 repo 中生成文档
- 校验需求链路是否闭环
- 维护索引页和追溯矩阵
- 将关键需求文档挂接回 `pt` 项目状态

## 2. 核心原则

### 2.1 工具与项目分离

- `project-tracker` 负责方法、模板、索引、校验、同步、编排。
- 项目正文必须写入目标项目 repo。
- `pt` 可以在任意目录调用，但操作对象始终是 `active project + linked repo`。

### 2.2 共享方法，不共享设计文件

- CAMRX、DCURX、后续新项目可以共享需求方法和模板。
- 它们不共享正式设计文件。
- 临时验证借板只能作为执行记录中的受控事实，不能混入正式设计归属。

### 2.3 先骨架，后实例化

- `pt req` 提供的是“骨架生成 + 索引 + 校验”。
- 具体内容由项目团队在目标 repo 中持续实例化和审核。
- 模板必须能裁剪，不能把 A57 当前结论硬编码成所有项目的默认真理。
- 运行期真理源依赖显式角色绑定，而不是文件名猜测。

### 2.4 需求链路必须可追溯

每条关键需求至少应当能被追到以下四类证据之一：

1. 项目级根本目的或商业目标
2. 系统级约束或业务场景
3. 接口/硬件/实现文档
4. 验证记录与放行结论

### 2.5 显式绑定优于运行时猜测

- `pt req` 的运行期真理源是角色绑定 manifest。
- 文件名 pattern 只允许在 `pt req init` 首次接入时执行一次，用于自动发现历史文档。
- `pt req check / index` 运行期只认显式 binding，不再回退到 pattern 猜测。

### 2.6 文档元数据契约

- 核心需求文档需要带 frontmatter。
- 当前最小元数据契约为：`pt_role`、`id`、`version`、`status`、`baseline`。
- `status` 应显式受控，而不是按“最新文档优先”这种隐式规则判断。

## 3. 模块边界

`pt req` 只负责以下四层：

1. 模板层
   - 项目级需求模板
   - 子项目目标矩阵模板
   - 追溯矩阵模板
   - 执行记录模板
   - 基线表模板
2. 生成层
   - 将模板写入目标 repo
   - 根据项目 ID、子项目名、日期、语言风格填充初值
   - 首次接入时自动发现历史文档并固化 binding
3. 校验层
   - 校验文档存在性
   - 校验 binding 是否存在并指向有效文件
   - 校验 frontmatter 元数据是否完整
   - 校验索引页引用是否闭环
   - 校验追溯矩阵字段是否齐全
   - 校验链接是否断裂
4. 编排层
   - 将关键需求文档挂到 `pt` 节点
   - 在 `.pt/` 中保存生成元信息
   - 在项目状态里记录生成和校验日志

`pt req` 不负责以下内容：

1. 不直接保存项目正式需求正文于 `project-tracker` 仓库
2. 不替代 `sch-review` 的审核职责
3. 不替代具体项目团队做业务判断
4. 不自动修改设计结论，只负责骨架、索引和一致性检查

## 3.1 当前真理源

当前实现中，`pt req` 的运行期真理源是目标 repo 下的：

```text
.pt/requirements_manifest.yaml
```

其中记录：

- `profile`
- `root`
- `subprojects`
- `bindings`

`bindings` 负责把“逻辑角色 ID”绑定到“实际文件路径”。

## 4. 目标用户与使用场景

### 4.1 项目初始化

新项目或新子项目建立时，快速生成一套可审核的需求骨架。

### 4.2 中途接入

已有项目文档散落在仓库里，需要导入统一需求主链路。

### 4.3 版本治理

需求变更多次发生后，需要知道当前有效口径、历史冻结口径和未闭环项。

### 4.4 跨项目复制

后续 DCURX 或新平台启动时，需要复用同一方法，而不是复制旧项目正文。

## 5. CLI 设计

## 5.1 一级命令

新增一级命令：

```bash
pt req ...
```

命令风格与现有 `pt docs`、`pt review`、`pt gate` 一致，默认围绕当前 active project 及其 linked repo 工作。

## 5.2 子命令

### `pt req init`

作用：

- 在目标 repo 中生成需求目录骨架
- 写入项目级起始文档和索引页
- 可选生成子项目模板
- 首次接入时自动发现历史文档，并把 binding 固化到 manifest

建议参数：

```bash
pt req init --profile hardware-platform
pt req init --profile hardware-platform --subprojects CAMRX,DCURX
pt req init --profile hardware-platform --root 01_需求阶段_Requirements
pt req init --dry-run
```

最小生成集：

1. 项目第一性原理需求文档
2. 项目起始三问模板
3. 项目级需求追溯矩阵
4. 当前有效结论页
5. 项目级 README / 索引页
6. 每个子项目的应用目标矩阵模板

### `pt req trace`

作用：

- 创建或刷新追溯矩阵
- 将显式 binding 的需求文档收敛到统一追溯矩阵
- 当前默认纳入 `trace_included: true` 的角色
- 对 `Active/Frozen` 文档强制检查 `verification_refs`
- 若文档未显式给出 `conclusion_refs`，默认回落到 `req_current_conclusion` 绑定
- 对项目级追溯矩阵，允许新扩展列头、旧版列头和 A57 早期实战列头并存，避免项目为了工具强制返工
- 对子项目应用目标矩阵，允许两类列头格式并存：
  - 模板型：`应用目标ID / 应用场景 / 用户价值 / 平台能力 / 约束/风险 / 当前结论`
  - A57 当前实战型：`目标ID / 目标名称 / 为什么重要 / 当前状态`

建议参数：

```bash
pt req trace
pt req trace --dry-run
pt req trace --json
```

### `pt req baseline`

作用：

- 生成专项基线文档骨架
- 用于接口基线、EEPROM 字段基线、日志字段基线、放行判定表等

建议参数：

```bash
pt req baseline interface --subproject CAMRX
pt req baseline eeprom --subproject CAMRX
pt req baseline release-criteria --subproject CAMRX
```

### `pt req index`

作用：

- 重建需求阶段索引页
- 汇总项目级文档、子项目文档、执行记录、当前有效结论
- 按 manifest 的显式 binding 组织核心入口

建议参数：

```bash
pt req index
pt req index --subproject CAMRX
```

### `pt req check`

作用：

- 对需求链路做静态校验
- 给出缺页、断链、未闭环项、无当前有效结论项
- 校验 binding 文档 frontmatter 是否满足最小契约
- 对项目级追溯矩阵列头，兼容扩展版、旧版与 A57 早期实战版
- 对应用目标矩阵列头，兼容模板型与 A57 当前实战型两种格式

建议参数：

```bash
pt req check
pt req check --strict
pt req check --json
```

### `pt close-check`

作用：

- 对“能力成立 / 验证跑通 / 设计决策完成 / 正式冻结”类任务执行 `Merge-to-Close` 门禁检查
- 检查正式对象、借用对象、适用范围、样机编号、协议板对象、固件版本、FPGA 版本、证据路径和 `A57-docs` 回写路径

建议参数：

```bash
pt close-check <task_id>
pt close-check <task_id> --json
pt gate closure <task_id>
pt closure scaffold <task_id>
```

### `pt req attach`

作用：

- 将关键需求文档自动挂接到对应任务节点
- 作为 `pt docs --attach` 的批量化高层封装

建议参数：

```bash
pt req attach
pt req attach --phase REQ
pt req attach --subproject CAMRX
```

## 6. Profile 设计

`pt req` 不应只有一个模板集合，而应支持 profile。

首个 profile 建议为：

```text
hardware-platform
```

它覆盖：

1. 项目级根本目的与商业目标
2. 系统原则
3. 业务场景
4. 平台能力
5. 工程约束
6. 接口定义
7. 原理图/PCB/样机/调试链路
8. 验证与发布结论

后续可扩展：

1. `embedded-board`
2. `test-platform`
3. `consumer-electronics`

## 7. 目录与模板落点

## 7.1 `project-tracker` 内部模板目录

建议新增：

```text
tracker/templates/requirements/
  hardware_platform/
    manifest.yaml
    project_level/
    subproject/
    baseline/
    execution/
```

其中：

- `manifest.yaml` 定义模板集合、目标文件名、默认目录、可选变量
- 模板正文使用 Markdown
- 模板变量只做轻量替换，不引入复杂模板引擎

## 7.2 目标 repo 落点

`pt req init` 不往 `project-tracker` 写项目正文，而是写入 linked repo，例如：

```text
<target-repo>/
  01_需求阶段_Requirements/
    00_项目级需求_Project_Level/
    01_CAMRX/
    02_DCURX/
```

具体目录名允许 profile 自定义，但必须保持：

1. 项目级
2. 子项目级
3. 专项基线
4. 执行记录
5. 当前有效结论

这五类结构可被 `pt req index/check` 稳定识别。

## 8. 数据与状态

## 8.1 项目 YAML 中新增的最小状态

建议在项目 YAML 中增加一个轻量区块：

```yaml
requirements:
  profile: hardware-platform
  root: 01_需求阶段_Requirements
  manifest: .pt/requirements_manifest.yaml
  bindings_count: 7
  generated_at: 2026-03-20 12:00
  last_checked_at: 2026-03-20 12:10
  last_check_status: pass
```

作用：

1. 记录项目是否已启用 `req` 体系
2. 记录目标目录根
3. 为 `pt status` / `pt brief` 提供需求健康度摘要

## 8.2 `.pt/` 中的元信息

当前实现中，目标 repo 的 `.pt/` 下生成：

```text
.pt/requirements_manifest.yaml
```

用于记录：

- profile 与 root
- 子项目清单
- 显式角色 binding
- 自动发现/生成结果

项目主 YAML 只保留轻量摘要，不复制完整 binding 表。

## 9. 校验规则

`pt req check` 第一阶段只做静态校验，不做语义推理。

最小校验集：

1. requirements manifest 是否存在
2. 必需 binding 是否存在
3. binding 指向的文件是否存在
4. binding 文档 frontmatter 元数据是否完整
5. 追溯矩阵必需列是否完整
6. 当前有效结论页是否存在
7. 子项目是否至少有一个应用目标矩阵

`--strict` 下再追加：

1. Markdown 相对链接不可断裂
2. 元数据与 binding 不一致时报错

## 10. 与现有模块的关系

### 与 `pt docs`

- `pt docs` 仍保留为通用文档挂接能力
- `pt req attach` 是面向需求体系的批量高层封装

### 与 `pt review` / `pt gate`

- `pt review` / `pt gate` 处理审核与放行
- `pt req` 负责需求主链路和追溯闭环
- 两者通过“验证项 / 放行判定表 / 当前有效结论”在项目 repo 中汇合

### 与 `pt prompt`

- `pt prompt` 后续应把需求文档纳入 BM25 检索源
- 但需求文档的生成与校验不应耦死在 prompt 模块里

## 11. 推荐实现顺序

### Phase 1: 骨架可落地

1. CLI 路由 `pt req`
2. `req init`
3. `req index`
4. `req check`
5. 项目 YAML 增加 `requirements` 轻量状态

目标：

- 能在目标 repo 中稳定生成一套需求骨架
- 能检查最基本的缺页和断链

### Phase 2: 追溯与挂接

1. `req trace`
2. `req attach`
3. `.pt/requirements_manifest.yaml`

目标：

- 需求文档与项目任务形成稳定挂接关系

### Phase 3: 深度集成

1. `pt status` 增加需求健康度摘要
2. `pt brief` / `pt prompt` 消费需求文档
3. `req check --strict` 增加更多一致性规则

## 12. 当前结论

`pt req` 的正确定位不是“把 A57 经验复制成更多 Markdown”，而是把 A57 已验证有效的方法抽象成：

1. 可生成的骨架
2. 可校验的结构
3. 可追溯的索引
4. 可挂接到项目状态的执行体系

只有这样，后续 DCURX 和新项目才能真正复用方法，而不是复制历史包袱。
