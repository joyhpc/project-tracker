# Project Tracker (项目推进助手)

基于度信平台机型流程的硬件项目推进 CLI 工具。

## 安装

```bash
git clone git@github.com:joyhpc/project-tracker.git
cd project-tracker
pip install -e .
```

## 快速开始

```bash
# 创建项目
pt init A57-CAMRX --name "A57 摄像头测试设备 - CAMRX" --phase SAMPLE

# 查看状态
pt status

# 查看所有任务
pt tasks

# 查看下一步
pt next

# 开始任务
pt start pcb_sample

# 完成任务
pt done pcb_sample --note "PCB已发板厂"

# 标记阻塞
pt block pcb_eq --reason "等板厂回复EQ"

# 解除阻塞
pt unblock pcb_eq

# 推进到下一阶段
pt advance

# 添加备注
pt note "今天和PCB工程师确认了堆叠方案"

# 查看项目历史
pt log

# 列出所有项目
pt list

# 切换项目
pt switch A57-DCURX
```

## 项目结构

```
project-tracker/
├── pt                    # CLI 入口 (可直接 ./pt)
├── tracker/
│   ├── __init__.py
│   ├── cli.py            # CLI 命令定义
│   ├── core.py           # 核心逻辑
│   └── flow.py           # 流程定义加载
├── flows/
│   └── duxin.yaml        # 度信平台流程定义
├── projects/             # 项目数据 (git tracked)
│   └── A57-CAMRX.yaml
├── setup.py
└── README.md
```

## 流程阶段

```
REQ → FEAS → INIT → OUTLINE → DETAIL → SAMPLE → SW_DEV → INTEG
 │                    MS1                  MS2              MS3
 ↓
TEST_A → TEST_B → TEST_C → TRIAL → RELEASE → ACCEPT
                              MS4
```

## 设计原则

1. **数据即 Git** - 所有项目状态都是 YAML，换电脑 clone 即可
2. **CLI 闭环** - 所有操作通过命令行完成
3. **流程驱动** - 基于标准流程自动推荐下一步
4. **零依赖** - 只需 Python 3.10+ 和 PyYAML
