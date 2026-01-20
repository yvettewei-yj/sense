"""
小白用户模拟器
模拟不同背景的用户与产品经理进行对话
"""
import json
import random
from llm_client import llm_client
from training_config import get_goals_config, get_user_profiles as load_user_profiles


class UserSimulator:
    """小白用户模拟器"""
    
    def __init__(self, profile: dict, scenario: dict | None = None, mental_state: dict | None = None, goals_config: dict | None = None):
        self.profile = profile
        self.scenario = scenario
        self.mental_state = mental_state
        self.goals_config = goals_config or get_goals_config()
        self.trust_level = 1  # 初始信任度为1（满分10）
        self.conversation_history = []
        self.concerns_addressed = []  # 已解答的顾虑
        self.is_convinced = False
        self.pm_turn_count = 0
        self.active_events: list[dict] = []
        
    def _is_event_triggered(self, event: dict, pm_message: str) -> bool:
        trigger = event.get("trigger") or {}
        if not isinstance(trigger, dict):
            return False

        # turn_gte
        turn_gte = trigger.get("turn_gte")
        if turn_gte is not None and self.pm_turn_count < int(turn_gte):
            return False

        # trust_gte
        trust_gte = trigger.get("trust_gte")
        if trust_gte is not None and self.trust_level < int(trust_gte):
            return False

        # keyword_any
        keyword_any = trigger.get("keyword_any") or []
        if keyword_any:
            text = (pm_message or "").lower()
            keywords = [str(k).lower() for k in keyword_any]
            if not any(k and k in text for k in keywords):
                return False

        # probability (默认 1.0)
        prob = trigger.get("probability", 1.0)
        try:
            prob = float(prob)
        except Exception:
            prob = 1.0
        if prob < 1.0 and random.random() > prob:
            return False

        return True

    def _update_active_events(self, pm_message: str) -> None:
        if not self.scenario:
            return
        events = self.scenario.get("events") or []
        if not isinstance(events, list) or not events:
            return

        already = {e.get("id") for e in self.active_events}
        for ev in events:
            if not isinstance(ev, dict):
                continue
            ev_id = ev.get("id")
            if ev_id in already:
                continue
            if self._is_event_triggered(ev, pm_message):
                self.active_events.append(ev)

    def get_system_prompt(self) -> str:
        """生成用户模拟的系统提示词"""
        scenario_block = ""
        if self.scenario:
            scenario_block = f"""
## 你所处的场景（非常重要）
- 场景名称: {self.scenario.get('name')}
- 场景概述: {self.scenario.get('summary')}
- 场景上下文: {self.scenario.get('context')}
- 市场状态: {self.scenario.get('market_state')}
- 你此刻的目标: {self.scenario.get('user_goal_in_this_moment')}
- 场景约束: {', '.join(self.scenario.get('constraints', []) or [])}
"""

        mental_block = ""
        if self.mental_state:
            mental_block = f"""
## 你当前的心理状态（非常重要）
- 心理状态: {self.mental_state.get('name')}
- 描述: {self.mental_state.get('description')}
- 行为指引: {', '.join(self.mental_state.get('behavior_guidelines', []) or [])}
"""

        events_block = ""
        if self.active_events:
            lines = []
            for ev in self.active_events:
                impact = ev.get("impact") or {}
                add_ctx = ""
                if isinstance(impact, dict):
                    add_ctx = str(impact.get("add_context") or "").strip()
                lines.append(f"- {ev.get('name')}: {ev.get('description')}{('；' + add_ctx) if add_ctx else ''}")
            events_block = f"""
## 你刚刚经历/正在经历的事件（会影响你的态度与提问）
{chr(10).join(lines)}
"""

        return f"""你现在要扮演一个腾讯自选股App的潜在用户，进行角色扮演训练。

## 你的角色信息
- 姓名: {self.profile['name']}
- 年龄: {self.profile['age']}岁
- 职业: {self.profile['occupation']}
- 背景: {self.profile['background']}
- 投资目标: {self.profile['investment_goal']}
- 风险承受能力: {self.profile['risk_tolerance']}
- 主要顾虑: {', '.join(self.profile['pain_points'])}
- 触发场景: {self.profile['trigger_scenario']}
- 性格特点: {self.profile['personality']}
{scenario_block}
{mental_block}
{events_block}

## 角色扮演规则
1. 你是一个对股票投资了解很少的"小白用户"，要表现出真实的困惑和担忧
2. 你的问题要符合你的角色背景，比如{self.profile['age']}岁的{self.profile['occupation']}会怎么问问题
3. 不要一开始就被说服，要根据对方的回答质量逐步建立信任
4. 你可以提出你的顾虑清单中的问题，也可以根据对话自然延伸新问题
5. 如果对方的解释不清楚或太专业，要追问或表示听不懂
6. 当你觉得对方真的解答了你的疑虑时，可以表现出态度软化
7. 保持角色一致性，用符合角色的语气说话

## 当前状态
- 信任度: {self.trust_level}/10 (达到{self.profile['trust_threshold']}才会考虑开户)
- 已解答的顾虑: {self.concerns_addressed if self.concerns_addressed else '暂无'}

## 回复格式
请用JSON格式回复，包含以下字段：
{{
    "response": "你作为用户的回复内容",
    "inner_thought": "你内心的真实想法（对产品经理不可见，用于评估）",
    "trust_change": 信任度变化（-2到+2之间的整数）,
    "concern_addressed": "如果某个顾虑被解答了，写出是哪个，否则为null",
    "willing_to_continue": true/false（是否愿意继续对话）,
    "ready_to_open_account": true/false（是否准备好开户）
}}

请始终保持角色扮演，用第一人称回复。"""

    def respond(self, pm_message: str) -> dict:
        """
        根据产品经理的消息生成用户回复
        
        Args:
            pm_message: 产品经理的消息
            
        Returns:
            用户回复的结构化数据
        """
        self.pm_turn_count += 1
        self._update_active_events(pm_message)

        self.conversation_history.append({
            "role": "user",  # 这里user是产品经理
            "content": pm_message
        })
        
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            *self.conversation_history
        ]
        
        response_text = llm_client.chat(messages, temperature=0.7)
        
        # 解析JSON响应
        try:
            # 尝试提取JSON部分
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0]
            else:
                json_str = response_text
                
            result = json.loads(json_str.strip())
            
            # 更新信任度
            trust_change = result.get("trust_change", 0)
            # 允许信任度跌到 0，用于“失去兴趣”触发条件
            try:
                trust_change = int(trust_change)
            except Exception:
                trust_change = 0
            self.trust_level = max(0, min(10, self.trust_level + trust_change))
            
            # 记录解答的顾虑
            if result.get("concern_addressed"):
                if result["concern_addressed"] not in self.concerns_addressed:
                    self.concerns_addressed.append(result["concern_addressed"])
            
            # 检查是否被说服（按 goals_config 可配置）
            success_cfg = (self.goals_config.get("success_conditions") or {})
            requires_ready = bool(success_cfg.get("requires_ready_to_open_account", True))
            min_concerns = int(success_cfg.get("min_concerns_addressed", 0) or 0)
            trust_at_least_threshold = bool(success_cfg.get("trust_at_least_profile_threshold", True))

            ready_ok = bool(result.get("ready_to_open_account")) if requires_ready else True
            # 支持“标准化阈值”：min_trust_level（优先级高于 profile trust_threshold）
            min_trust_level = success_cfg.get("min_trust_level", None)
            trust_ok = True
            if min_trust_level is not None:
                try:
                    trust_ok = self.trust_level >= int(min_trust_level)
                except Exception:
                    trust_ok = True
            elif trust_at_least_threshold:
                trust_ok = self.trust_level >= int(self.profile.get("trust_threshold", 8))
            concerns_ok = len(self.concerns_addressed) >= min_concerns

            if ready_ok and trust_ok and concerns_ok:
                self.is_convinced = True

            # 结束条件：信任度过低 -> 用户失去兴趣，不愿继续
            end_cfg = (self.goals_config.get("end_conditions") or {})
            try:
                min_trust_to_continue = int(end_cfg.get("min_trust_to_continue", 0) or 0)
            except Exception:
                min_trust_to_continue = 0
            if (not self.is_convinced) and self.trust_level <= min_trust_to_continue:
                result["willing_to_continue"] = False
                result["ready_to_open_account"] = False
                result["quit_reason"] = "lost_interest_low_trust"
                # 给一个可解释的退出理由，供结算页/评估使用
                result.setdefault(
                    "quit_explanation",
                    f"信任度降到{self.trust_level}/10，我感觉你的回答没解决我的核心疑问/太难理解，所以先不聊了。"
                )
                
            # 添加到对话历史
            self.conversation_history.append({
                "role": "assistant",
                "content": result["response"]
            })
            
            return result
            
        except (json.JSONDecodeError, KeyError) as e:
            # 如果解析失败，返回原始文本
            fallback = {
                "response": response_text,
                "inner_thought": "（解析失败）",
                "trust_change": 0,
                "concern_addressed": None,
                "willing_to_continue": True,
                "ready_to_open_account": False
            }
            self.conversation_history.append({
                "role": "assistant", 
                "content": response_text
            })
            return fallback
    
    def get_opening_message(self) -> dict:
        """生成用户的开场白"""
        prompt = f"""作为{self.profile['name']}，你刚刚打开腾讯自选股App，因为"{self.profile['trigger_scenario']}"。
        
请生成你的第一句话，表达你的困惑或需求。记住你是一个小白用户。

用JSON格式回复：
{{
    "response": "你的开场白",
    "inner_thought": "你内心的真实想法"
}}"""
        
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": prompt}
        ]
        
        # 开场白不需要太长，且首次冷启动可能较慢：缩短 max_tokens + timeout，超时走兜底模板
        response_text = llm_client.chat(messages, temperature=0.8, max_tokens=300, timeout=45)
        
        try:
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0]
            else:
                json_str = response_text
            result = json.loads(json_str.strip())
            
            self.conversation_history.append({
                "role": "assistant",
                "content": result["response"]
            })
            return result
        except:
            return {
                "response": f"你好，我想问一下...我是{self.profile['occupation']}，{self.profile['trigger_scenario']}，但是我不太懂这些...",
                "inner_thought": "希望能有人帮我解答"
            }


def get_user_profiles():
    """获取所有用户画像"""
    return load_user_profiles()


def create_simulator(profile_id: int) -> UserSimulator:
    """根据ID创建用户模拟器"""
    for profile in load_user_profiles():
        if profile["id"] == profile_id:
            return UserSimulator(profile)
    raise ValueError(f"未找到ID为{profile_id}的用户画像")
