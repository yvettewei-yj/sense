"""
对话评估器
评估产品经理在对话中的表现
"""
import json
import re
from typing import Any, Dict, Optional
from llm_client import llm_client
from training_config import get_evaluation_criteria, get_scoring_rules, get_goals_config


class ConversationEvaluator:
    """对话评估器"""
    
    def __init__(
        self,
        criteria: Optional[Dict[str, Dict[str, Any]]] = None,
        scoring_rules: Optional[Dict[str, Any]] = None,
        goals_config: Optional[Dict[str, Any]] = None,
    ):
        self.criteria = criteria or get_evaluation_criteria()
        self.scoring_rules = scoring_rules or get_scoring_rules()
        self.goals_config = goals_config or get_goals_config()
        self._last_conversation_history: list = []
        
    def evaluate(self, conversation_history: list, user_profile: dict, 
                 final_trust_level: int, is_convinced: bool, 
                 concerns_addressed: list, turn_count: int,
                 scenario: Optional[dict] = None, mental_state: Optional[dict] = None,
                 end_reason: Optional[str] = None, end_detail: Optional[dict] = None) -> dict:
        """
        评估整个对话过程
        
        Args:
            conversation_history: 对话历史
            user_profile: 用户画像
            final_trust_level: 最终信任度
            is_convinced: 是否成功说服
            concerns_addressed: 已解答的顾虑列表
            turn_count: 对话轮数
            
        Returns:
            评估结果
        """
        # 构建评估提示词
        self._last_conversation_history = conversation_history or []
        evaluation_prompt = self._build_evaluation_prompt(
            conversation_history, user_profile, final_trust_level,
            is_convinced, concerns_addressed, turn_count, scenario, mental_state,
            end_reason=end_reason, end_detail=end_detail
        )
        
        messages = [
            {"role": "system", "content": "你是一个专业的产品经理培训评估专家，需要对产品经理与用户的对话进行专业评估。"},
            {"role": "user", "content": evaluation_prompt}
        ]
        
        response = llm_client.chat(messages, temperature=0.3)
        
        try:
            # 尝试解析JSON
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            else:
                json_str = response
            
            result = json.loads(json_str.strip())

            # 计算可解释的规则分（由配置控制）
            scoring_breakdown = self._compute_rule_based_score(
                final_trust_level=final_trust_level,
                is_convinced=is_convinced,
                concerns_addressed=concerns_addressed,
                turn_count=turn_count,
                user_profile=user_profile,
            )

            # 保留 LLM 维度评分，但以规则分作为 total_score（更可控、更可配置）
            scores = result.get("scores") if isinstance(result, dict) else None
            if not isinstance(scores, dict):
                scores = {}

            llm_weighted = calculate_weighted_score(scores, criteria=self.criteria)

            result["llm_weighted_score"] = llm_weighted
            result["scoring_breakdown"] = scoring_breakdown
            result["total_score"] = scoring_breakdown["total_score"]

            # 结束原因解释：用于“用户失去兴趣”等结算页说明
            if isinstance(result, dict) and not result.get("end_explanation"):
                result["end_explanation"] = self._build_end_explanation(
                    end_reason=end_reason,
                    end_detail=end_detail,
                    final_trust_level=final_trust_level,
                    turn_count=turn_count,
                )
            return result
        except:
            # 返回默认评估
            fallback = self._generate_default_evaluation(
                final_trust_level, is_convinced, concerns_addressed, turn_count
            )
            fallback["end_explanation"] = self._build_end_explanation(
                end_reason=end_reason,
                end_detail=end_detail,
                final_trust_level=final_trust_level,
                turn_count=turn_count,
            )
            fallback["scoring_breakdown"] = self._compute_rule_based_score(
                final_trust_level=final_trust_level,
                is_convinced=is_convinced,
                concerns_addressed=concerns_addressed,
                turn_count=turn_count,
                user_profile=user_profile,
            )
            fallback["total_score"] = fallback["scoring_breakdown"]["total_score"]
            return fallback
    
    def _build_evaluation_prompt(self, conversation_history: list, 
                                  user_profile: dict, final_trust_level: int,
                                  is_convinced: bool, concerns_addressed: list,
                                  turn_count: int,
                                  scenario: Optional[dict] = None,
                                  mental_state: Optional[dict] = None,
                                  end_reason: Optional[str] = None,
                                  end_detail: Optional[dict] = None) -> str:
        """构建评估提示词"""
        
        # 格式化对话历史
        formatted_history = []
        for i, msg in enumerate(conversation_history):
            role = "用户(小白)" if msg["role"] == "assistant" else "产品经理"
            formatted_history.append(f"{role}: {msg['content']}")
        
        conversation_text = "\n\n".join(formatted_history)

        # 场景/心理状态（用于更贴近真实用户的评估维度）
        scenario_text = "无（未配置）"
        if scenario:
            scenario_text = f"{scenario.get('name')}：{scenario.get('summary')}"
        mental_text = "无（未配置）"
        if mental_state:
            mental_text = f"{mental_state.get('name')}：{mental_state.get('description')}"

        goals = self.goals_config.get("success_conditions") or {}
        min_concerns = int(goals.get("min_concerns_addressed", 0) or 0)
        requires_ready = bool(goals.get("requires_ready_to_open_account", True))
        trust_threshold_needed = bool(goals.get("trust_at_least_profile_threshold", True))
        min_trust_level = goals.get("min_trust_level", None)
        pass_conditions = [
            f"解答顾虑数量 ≥ {min_concerns}",
            "用户明确表示准备开户" if requires_ready else "不要求用户明确表示准备开户",
            (
                f"信任度 ≥ {int(min_trust_level)}"
                if min_trust_level is not None
                else (f"信任度 ≥ {user_profile.get('trust_threshold', 8)}" if trust_threshold_needed else "不要求信任度达到阈值")
            ),
        ]
        
        return f"""请评估以下产品经理与潜在用户的对话表现。

## 用户背景
- 姓名: {user_profile['name']}
- 年龄: {user_profile['age']}岁
- 职业: {user_profile['occupation']}
- 背景: {user_profile['background']}
- 投资目标: {user_profile['investment_goal']}
- 主要顾虑: {', '.join(user_profile['pain_points'])}
- 说服难度: 信任度需达到{user_profile['trust_threshold']}/10才会开户
- 场景: {scenario_text}
- 心理状态: {mental_text}

## 对话内容
{conversation_text}

## 对话结果
- 对话轮数: {turn_count}轮
- 最终信任度: {final_trust_level}/10
- 是否成功说服开户: {'是' if is_convinced else '否'}
- 解答的顾虑: {concerns_addressed if concerns_addressed else '无'}
- 结束原因: {end_reason or '未知'}
- 结束补充信息: {end_detail if end_detail else '无'}

## 通关条件（来自配置）
{chr(10).join([f"- {x}" for x in pass_conditions])}

## 评估维度
请从以下维度进行评估（每项0-100分）：
1. 沟通技巧（communication_skills）: 是否能用通俗易懂的语言解释专业概念
2. 同理心（empathy）: 是否能理解用户的担忧和需求
3. 问题解决（problem_solving）: 是否能有效解答用户疑虑
4. 说服力（persuasion）: 是否能逐步建立信任并引导开户
5. 专业度（professionalism）: 对产品和投资知识的掌握程度

请用JSON格式返回评估结果：
{{
    "scores": {{
        "communication_skills": 分数,
        "empathy": 分数,
        "problem_solving": 分数,
        "persuasion": 分数,
        "professionalism": 分数
    }},
    "total_score": 加权总分,
    "highlights": ["做得好的地方1", "做得好的地方2", ...],
    "improvements": ["需要改进的地方1", "需要改进的地方2", ...],
    "key_insights": "关于用户sense的关键洞察",
    "overall_comment": "总体评价",
    "end_explanation": "用通俗的话解释：为什么对话会在这里结束（尤其当 end_reason=user_quit 时，说明用户为何失去兴趣/信任崩溃）"
}}"""

    def _build_end_explanation(
        self,
        *,
        end_reason: Optional[str],
        end_detail: Optional[dict],
        final_trust_level: int,
        turn_count: int,
    ) -> str:
        """生成结算页可展示的“结束原因解释”（不依赖 LLM，保证稳定可用）。"""
        end_reason = (end_reason or "").strip()
        detail = end_detail or {}

        if end_reason == "success":
            return "用户被成功说服并愿意开户，本局以成功结束。"
        if end_reason == "trust_full":
            return f"用户对你的信任已达到满分（{final_trust_level}/10），训练目标达成，系统直接进入结算。"
        if end_reason == "concerns_full":
            total = detail.get("total_concerns")
            addressed = detail.get("concerns_addressed")
            if total is not None and addressed is not None:
                return f"用户的主要顾虑已全部解答（{addressed}/{total}），训练目标达成，系统直接进入结算。"
            return "用户的主要顾虑已全部解答，训练目标达成，系统直接进入结算。"
        if end_reason == "max_turns":
            return f"对话已达到轮数上限（{turn_count} 轮），系统自动结束并进入结算。"
        if end_reason == "user_quit":
            qr = (detail.get("quit_reason") or "").strip()
            qe = (detail.get("quit_explanation") or "").strip()
            if qe:
                return qe
            if qr == "lost_interest_low_trust":
                return f"用户信任度已降至 {final_trust_level}/10，用户对继续沟通失去兴趣，选择结束对话。"
            return "用户在对话过程中失去兴趣/不愿继续，因此提前结束对话。"
        if end_reason:
            return f"对话因 {end_reason} 结束，进入结算。"
        return "对话已结束，进入结算。"

    def _generate_default_evaluation(self, final_trust_level: int, 
                                     is_convinced: bool, 
                                     concerns_addressed: list,
                                     turn_count: int) -> dict:
        """生成默认评估结果"""
        base_score = 50
        
        # 根据结果调整分数
        if is_convinced:
            base_score += 20
        base_score += final_trust_level * 2
        base_score += len(concerns_addressed) * 5
        
        # 效率奖励
        if is_convinced and turn_count <= 10:
            base_score += 10
            
        base_score = min(100, base_score)
        
        return {
            "scores": {
                "communication_skills": base_score,
                "empathy": base_score,
                "problem_solving": base_score,
                "persuasion": base_score + (10 if is_convinced else -10),
                "professionalism": base_score
            },
            "total_score": base_score,
            "highlights": ["完成了对话练习"],
            "improvements": ["建议多练习以提升表现"],
            "key_insights": "持续练习可以提升用户sense",
            "overall_comment": "继续加油！"
        }

    def _compute_rule_based_score(
        self,
        *,
        final_trust_level: int,
        is_convinced: bool,
        concerns_addressed: list,
        turn_count: int,
        user_profile: dict,
    ) -> Dict[str, Any]:
        """按 scoring_rules 生成可解释的规则分（可配置）"""
        r = self.scoring_rules or {}
        base_score = int(r.get("base_score", 50))
        success_bonus = int(r.get("success_bonus", 20))
        trust_point_per_level = int(r.get("trust_point_per_level", 2))
        concern_bonus = int(r.get("concern_addressed_bonus", 5))
        fast_turns_threshold = int(r.get("fast_success_turns_threshold", 10))
        fast_bonus = int(r.get("fast_success_bonus", 10))
        max_total = int(r.get("max_total_score", 100))
        bonuses = r.get("bonuses") or []
        penalties = r.get("penalties") or []

        # 提取 PM 话术（conversation_history 中 role=user 代表产品经理）
        pm_messages = []
        try:
            for msg in (self._last_conversation_history or []):  # type: ignore[attr-defined]
                if isinstance(msg, dict) and msg.get("role") == "user":
                    pm_messages.append(str(msg.get("content") or ""))
        except Exception:
            pm_messages = []
        pm_text = "\n".join(pm_messages)

        parts = []
        score = base_score
        parts.append({"name": "基础分", "delta": base_score})

        trust_delta = int(final_trust_level) * trust_point_per_level
        score += trust_delta
        parts.append({"name": "信任度奖励", "delta": trust_delta, "detail": f"{final_trust_level} × {trust_point_per_level}"})

        concerns_delta = len(concerns_addressed) * concern_bonus
        score += concerns_delta
        parts.append({"name": "解答顾虑奖励", "delta": concerns_delta, "detail": f"{len(concerns_addressed)} × {concern_bonus}"})

        if is_convinced:
            score += success_bonus
            parts.append({"name": "成功开户奖励", "delta": success_bonus})
            if turn_count <= fast_turns_threshold:
                score += fast_bonus
                parts.append({"name": "效率奖励", "delta": fast_bonus, "detail": f"turns≤{fast_turns_threshold}"})

        # 话术规则加/扣分（可配置）
        def apply_rules(rule_list, kind: str):
            nonlocal score
            if not isinstance(rule_list, list):
                return
            lower_text = pm_text.lower()
            for rule in rule_list:
                if not isinstance(rule, dict):
                    continue
                delta = int(rule.get("delta", 0) or 0)
                if delta == 0:
                    continue
                hit = False

                keyword_any = rule.get("keyword_any") or []
                if keyword_any:
                    for k in keyword_any:
                        ks = str(k).lower()
                        if ks and ks in lower_text:
                            hit = True
                            break

                regex_any = rule.get("regex_any") or []
                if not hit and regex_any:
                    for pat in regex_any:
                        try:
                            if re.search(str(pat), pm_text, flags=re.IGNORECASE):
                                hit = True
                                break
                        except Exception:
                            continue

                if hit:
                    score += delta
                    parts.append({
                        "name": f"{'加分' if kind == 'bonus' else '扣分'}：{rule.get('name') or rule.get('id')}",
                        "delta": delta,
                        "rule_id": rule.get("id"),
                    })

        apply_rules(bonuses, "bonus")
        apply_rules(penalties, "penalty")

        clamped = max(0, min(max_total, score))
        return {
            "total_score": clamped,
            "raw_score": score,
            "max_total_score": max_total,
            "parts": parts,
        }


def calculate_weighted_score(scores: dict, criteria: Optional[Dict[str, Dict[str, Any]]] = None) -> float:
    """计算加权总分"""
    criteria = criteria or get_evaluation_criteria()
    total = 0
    for key, value in scores.items():
        if key in criteria:
            total += value * criteria[key].get("weight", 0)
    return round(total, 1)
