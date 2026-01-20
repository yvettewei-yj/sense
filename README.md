# 🎯 腾讯自选股 - PM用户Sense训练系统

这是一个对话式AI训练Web应用，帮助产品经理提升用户感知能力（User Sense）。

## 📋 功能特性

- **多角色模拟**: 5种不同背景的小白用户画像
- **情景演练**: 真实的多轮对话训练
- **智能评估**: AI驱动的对话质量评估
- **实时反馈**: 信任度变化、顾虑解答进度追踪
- **现代化UI**: 美观的Web界面，支持浏览器访问

## 🚀 快速开始

### 1. 激活虚拟环境

```bash
cd "PMtrainer 2"
source venv/bin/activate
```

### 2. 运行Web应用

```bash
python app.py
```

### 3. 访问应用

打开浏览器访问: **http://127.0.0.1:8080**

### 命令行版本（可选）

```bash
python main.py
```

## 👥 用户画像

| ID | 姓名 | 职业 | 难度 |
|----|------|------|------|
| 1 | 张阿姨 | 退休教师 | ⭐⭐⭐ 困难 |
| 2 | 小王 | 互联网程序员 | ⭐⭐ 中等 |
| 3 | 李姐 | 全职妈妈 | ⭐⭐ 中等 |
| 4 | 老刘 | 个体户老板 | ⭐⭐⭐ 困难 |
| 5 | 小陈 | 大四学生 | ⭐ 简单 |

## 📊 评估维度

- **沟通技巧** (25%): 能否用通俗语言解释专业概念
- **同理心** (25%): 能否理解用户担忧和需求
- **问题解决** (20%): 能否有效解答用户疑虑
- **说服力** (20%): 能否逐步建立信任并引导开户
- **专业度** (10%): 产品和投资知识掌握程度

## 🎮 使用指南

1. 启动程序后选择一个用户画像
2. 阅读用户档案，了解其背景和顾虑
3. 开始对话，你扮演产品经理/客服
4. 目标是通过多轮对话说服用户开户
5. 输入 `/quit` 可随时结束对话
6. 对话结束后查看AI评估报告

## 📁 项目结构

```
PMtrainer/
├── app.py            # Flask Web应用入口
├── main.py           # 命令行版本入口
├── config.py         # 配置文件（用户画像、评估标准、API配置）
├── llm_client.py     # LLM API客户端
├── user_simulator.py # 用户模拟器
├── evaluator.py      # 对话评估器
├── requirements.txt  # 依赖包
├── README.md         # 说明文档
├── templates/        # HTML模板
│   ├── index.html    # 首页
│   └── train.html    # 训练页面
└── static/           # 静态资源
    ├── css/
    │   ├── style.css # 全局样式
    │   └── train.css # 训练页样式
    └── js/
        └── train.js  # 训练页交互逻辑
```

## 🔧 配置

LLM 配置通过环境变量注入（避免把 API Key 提交到 GitHub）。

- 参考 `env.example`，复制成 `.env` 后填写真实值（`.gitignore` 已忽略 `.env`）

LLM 配置在 `config.py` 中读取（支持 OpenAI 兼容接口，包括企业/代理网关）：

```python
LLM_CONFIG = {
    "url": os.getenv("LLM_API_URL") or os.getenv("OPENAI_API_BASE") or "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "",
    "model": os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "qwen-plus",
}
```

### 在线 OpenAI 兼容（企业/代理网关）

如果你使用企业/代理的 OpenAI 兼容网关，可以直接设置：

- `OPENAI_API_BASE`（或 `LLM_API_URL`）
- `OPENAI_API_KEY`（或 `LLM_API_KEY`）
- `OPENAI_MODEL`（或 `LLM_MODEL`）

### 免费方案：本地大模型（Ollama，无需 API Key）

如果你暂时没有可用的云端 Key（或网络受限），推荐使用本地 Ollama（完全免费、离线可用）。

- 安装 Ollama 并启动（按 Ollama 官方安装即可）
- 拉取一个模型（示例）：

```bash
ollama pull qwen2.5:7b-instruct
```

- 在 `.env` 中配置（参考 `env.example`）：
  - `OLLAMA_BASE_URL=http://127.0.0.1:11434`
  - `OLLAMA_MODEL=qwen2.5:7b-instruct`

### 🔁 切回本地 Ollama（如果你之前配置过在线 OpenAI 兼容网关）

如果你之前在终端里 `export OPENAI_API_*` 或在 `.env` 里写过 `OPENAI_API_* / LLM_API_*`，会导致程序优先走远程。
要强制回到本地 Ollama：

1. **清掉环境变量（在启动 Flask 的同一个终端里执行）**：

```bash
unset OPENAI_API_BASE OPENAI_API_KEY OPENAI_MODEL
unset LLM_API_URL LLM_API_KEY LLM_MODEL
```

2. **（可选）检查/删除 `.env` 中的远程配置**：确保不包含 `OPENAI_API_*` 或 `LLM_API_*`（只保留 `OLLAMA_BASE_URL/OLLAMA_MODEL`）。

3. **重启 Flask**，再验证：
   - 访问 `http://127.0.0.1:8080/api/llm/status`
   - 看到 `ollama.reachable: true` 且 `remote.key_configured: false`，就说明已经在用 Ollama 了。

程序会在云端不可用/未配置 Key 时自动降级使用本地 Ollama。

## 💡 训练技巧

1. **换位思考**: 站在用户角度理解他们的顾虑
2. **通俗表达**: 避免使用专业术语，用生活化例子解释
3. **循序渐进**: 不要急于推销，先建立信任
4. **解答疑虑**: 针对用户具体问题给出答案
5. **适时引导**: 在信任建立后再引导开户

---

*腾讯自选股 - 产品经理训练平台*
