import os


def _load_env_file_if_present() -> None:
    """
    轻量读取项目根目录的 .env（如果存在），把 KEY=VALUE 注入到环境变量里。
    - 不覆盖已存在的环境变量
    - 仅用于本地开发，避免“复制了 .env 但程序读不到”的困惑
    """
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(base_dir, ".env")
        if not os.path.exists(env_path):
            return

        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f.readlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if not k:
                    continue
                # 如果环境变量不存在或为空，则以 .env 为准
                cur = os.getenv(k)
                if cur is None or cur == "":
                    os.environ[k] = v

        # 兼容：不少人会按厂商/代理文档写不同的变量名
        # - OpenAI 兼容：OPENAI_API_KEY / OPENAI_API_BASE
        # - 厂商 Key：DASHSCOPE_API_KEY / QWEN_API_KEY / DEEPSEEK_API_KEY
        # 若未显式配置 LLM_API_KEY，则从这些变量兜底一份
        if not (os.getenv("LLM_API_KEY") or "").strip():
            for alt in ("OPENAI_API_KEY", "DASHSCOPE_API_KEY", "QWEN_API_KEY", "DEEPSEEK_API_KEY"):
                v = (os.getenv(alt) or "").strip()
                if v:
                    os.environ["LLM_API_KEY"] = v
                    break

        # 若未显式配置 LLM_API_URL，则从 OPENAI_API_BASE 兜底
        if not (os.getenv("LLM_API_URL") or "").strip():
            base = (os.getenv("OPENAI_API_BASE") or "").strip()
            if base:
                os.environ["LLM_API_URL"] = base

        # 若未显式配置 LLM_MODEL，则从 OPENAI_MODEL 兜底
        if not (os.getenv("LLM_MODEL") or "").strip():
            m = (os.getenv("OPENAI_MODEL") or "").strip()
            if m:
                os.environ["LLM_MODEL"] = m
    except Exception:
        # .env 加载失败不应影响主流程
        return


_load_env_file_if_present()

# LLM API 配置
# 为避免泄露敏感信息，请通过环境变量注入配置（不要把真实 key 提交到 GitHub）
LLM_CONFIG = {
    # 默认使用通义千问（DashScope OpenAI 兼容模式）
    # base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    # （等价于 OpenAI 的 /v1/chat/completions）
    # 优先 LLM_API_URL；否则兼容读取 OPENAI_API_BASE（企业/代理 OpenAI 兼容）
    "url": os.getenv("LLM_API_URL") or os.getenv("OPENAI_API_BASE") or "https://dashscope.aliyuncs.com/compatible-mode/v1",
    # 优先 LLM_API_KEY；否则兼容读取 OPENAI_API_KEY
    "api_key": os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "",  # 必填：通过环境变量注入
    # 优先 LLM_MODEL；否则兼容读取 OPENAI_MODEL
    "model": os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "qwen-plus",
}

# 用户画像库
USER_PROFILES = [
    {
        "id": 1,
        "name": "张阿姨",
        "age": 55,
        "occupation": "退休教师",
        "background": "刚退休，有一笔积蓄想保值增值，对股票完全不懂，孩子建议她学习理财",
        "investment_goal": "稳健保值，跑赢银行存款利率",
        "risk_tolerance": "极低",
        "pain_points": ["担心被骗", "不会用手机App", "对专业术语恐惧", "害怕亏钱"],
        "trigger_scenario": "儿子推荐她下载了腾讯自选股",
        "trust_threshold": 8,  # 信任度达到8才会考虑开户
        "personality": "谨慎、爱问问题、需要反复确认安全性"
    },
    {
        "id": 2,
        "name": "小王",
        "age": 26,
        "occupation": "互联网程序员",
        "background": "工作3年攒了一些钱，看到同事炒股赚钱了也想试试，但怕亏",
        "investment_goal": "想快速积累财富，对高收益有兴趣",
        "risk_tolerance": "中等",
        "pain_points": ["不知道从哪开始", "担心入场时机不对", "没时间盯盘", "对股票术语不熟"],
        "trigger_scenario": "看到比特币暴涨的新闻，想了解什么是比特币和如何投资",
        "trust_threshold": 6,
        "personality": "好奇心强、学习能力强、但容易被FOMO情绪影响"
    },
    {
        "id": 3,
        "name": "李姐",
        "age": 38,
        "occupation": "全职妈妈",
        "background": "以前在银行工作过，对理财有基础认知，现在全职带娃，想利用碎片时间投资",
        "investment_goal": "为孩子教育基金做长期投资",
        "risk_tolerance": "中低",
        "pain_points": ["时间碎片化", "担心影响家庭开支", "需要老公同意", "想要简单易操作"],
        "trigger_scenario": "朋友推荐说腾讯自选股可以定投基金",
        "trust_threshold": 7,
        "personality": "理性、有主见、但需要家人支持"
    },
    {
        "id": 4,
        "name": "老刘",
        "age": 48,
        "occupation": "个体户老板",
        "background": "做生意多年，手里有闲钱，以前炒过股亏过，对股市有阴影",
        "investment_goal": "分散投资，不想把鸡蛋放一个篮子里",
        "risk_tolerance": "中等",
        "pain_points": ["曾经被套牢的心理阴影", "不相信推荐", "怕被割韭菜", "对券商有不信任感"],
        "trigger_scenario": "听说现在的智能投顾不一样了，想再了解一下",
        "trust_threshold": 9,  # 很难被说服
        "personality": "多疑、爱抬杠、需要看到实际数据"
    },
    {
        "id": 5,
        "name": "小陈",
        "age": 22,
        "occupation": "大四学生",
        "background": "即将毕业，有一点实习赚的钱想试试投资，看了很多财经博主的视频",
        "investment_goal": "学习投资，积累经验，小额尝试",
        "risk_tolerance": "较高（因为本金少）",
        "pain_points": ["本金少", "怕被嘲笑不懂", "信息来源混乱", "容易被网红观点影响"],
        "trigger_scenario": "刷到一个财经博主说现在是入场好时机",
        "trust_threshold": 5,
        "personality": "冲动、好学、但缺乏判断力"
    }
]

# 评估维度
EVALUATION_CRITERIA = {
    "communication_skills": {
        "name": "沟通技巧",
        "description": "是否能用通俗易懂的语言解释专业概念",
        "weight": 0.25
    },
    "empathy": {
        "name": "同理心",
        "description": "是否能理解用户的担忧和需求",
        "weight": 0.25
    },
    "problem_solving": {
        "name": "问题解决",
        "description": "是否能有效解答用户疑虑",
        "weight": 0.2
    },
    "persuasion": {
        "name": "说服力",
        "description": "是否能逐步建立信任并引导开户",
        "weight": 0.2
    },
    "professionalism": {
        "name": "专业度",
        "description": "对产品和投资知识的掌握程度",
        "weight": 0.1
    }
}
