#!/usr/bin/env python3
"""
腾讯自选股 - PM用户Sense训练系统 Web应用
"""
import json
import uuid
import traceback
import random
import os
import requests
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from jinja2 import TemplateNotFound

from config import LLM_CONFIG
from training_config import (
    find_by_id,
    get_evaluation_criteria as get_evaluation_criteria_config,
    get_goals_config,
    get_scoring_rules,
    get_training_options,
    get_user_profiles,
)
from user_simulator import UserSimulator
from evaluator import ConversationEvaluator

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
    static_url_path="/static",
)
app.secret_key = 'pm-trainer-secret-key-2024'
CORS(app)


# 全局错误处理器
@app.errorhandler(Exception)
def handle_exception(e):
    """全局异常处理：API 返回 JSON；页面返回 HTML"""
    # 让 Flask/werkzeug 的 HTTP 异常（404/400等）按原有语义返回
    if isinstance(e, HTTPException):
        if request.path.startswith('/api/'):
            return jsonify({"error": e.description}), e.code
        return e

    # 非 HTTP 异常：API 走 JSON，页面走 HTML（便于本地调试）
    if not request.path.startswith('/api/'):
        if isinstance(e, TemplateNotFound):
            return (
                f"TemplateNotFound: {e}\n"
                f"template_folder: {app.template_folder}\n"
                f"static_folder: {app.static_folder}\n",
                500,
                {"Content-Type": "text/plain; charset=utf-8"},
            )
        # 让 Flask 的 debug 页面/默认 500 页面接管
        raise e

    print(f"[GLOBAL ERROR] {type(e).__name__}: {str(e)}")
    traceback.print_exc()
    return jsonify({
        "error": f"服务器内部错误: {str(e)}",
        "type": type(e).__name__
    }), 500


@app.errorhandler(500)
def handle_500(e):
    """处理500错误"""
    if request.path.startswith('/api/'):
        return jsonify({"error": "服务器内部错误"}), 500
    return e


@app.errorhandler(404)
def handle_404(e):
    """处理404错误"""
    # 如果是API请求返回JSON，否则返回页面
    if request.path.startswith('/api/'):
        return jsonify({"error": "接口不存在"}), 404
    return render_template('index.html'), 404

# 存储活跃的训练会话
active_sessions = {}

def _difficulty_level_from_threshold(trust_threshold: int) -> str:
    """
    难度用于“通关条件”分层，而不是评估维度分。
    更贴近体感的默认划分：
    - easy:   ≤ 6
    - medium: 7-8
    - hard:   ≥ 9
    """
    try:
        t = int(trust_threshold)
    except Exception:
        t = 7
    if t <= 6:
        return "easy"
    if t <= 8:
        return "medium"
    return "hard"


def _apply_success_overrides(goals_config: dict, difficulty_level: str) -> dict:
    """根据难度覆盖 success_conditions，保证 simulator + evaluator 统一使用同一套通关判定。"""
    base = goals_config or {}
    merged = {**base}
    base_success = dict((base.get("success_conditions") or {}))
    by_diff = base.get("success_conditions_by_difficulty") or {}
    override = {}
    if isinstance(by_diff, dict):
        override = by_diff.get(difficulty_level) or {}
    if isinstance(override, dict):
        base_success.update(override)
    merged["success_conditions"] = base_success
    return merged


class TrainingSession:
    """训练会话管理"""
    def __init__(self, profile: dict, scenario: dict | None = None, mental_state: dict | None = None):
        self.session_id = str(uuid.uuid4())
        self.profile = profile
        self.scenario = scenario
        self.mental_state = mental_state
        self.goals_config = get_goals_config()
        self.difficulty_level = _difficulty_level_from_threshold(int(profile.get("trust_threshold", 7) or 7))
        self.effective_goals_config = _apply_success_overrides(self.goals_config, self.difficulty_level)
        self.simulator = UserSimulator(
            profile,
            scenario=scenario,
            mental_state=mental_state,
            goals_config=self.effective_goals_config,
        )
        self.turn_count = 0
        self.messages = []  # 前端显示的消息
        self.started = False
        self.end_reason: str | None = None
        self.end_detail: dict = {}
        
    def to_dict(self):
        return {
            "session_id": self.session_id,
            "profile": self.profile,
            "scenario": self.scenario,
            "mental_state": self.mental_state,
            "turn_count": self.turn_count,
            "trust_level": self.simulator.trust_level,
            "trust_threshold": self.profile["trust_threshold"],
            "concerns_addressed": self.simulator.concerns_addressed,
            "total_concerns": len(self.profile["pain_points"]),
            "is_convinced": self.simulator.is_convinced,
            "messages": self.messages,
            "end_reason": self.end_reason,
            "end_detail": self.end_detail,
            "difficulty_level": self.difficulty_level,
        }


@app.route('/')
def index():
    """首页"""
    return render_template('index.html')


@app.route('/train')
def train():
    """训练页面"""
    return render_template('train.html')


@app.route('/api/profiles')
def get_profiles():
    """获取所有用户画像"""
    try:
        profiles: list[dict] = []
        for p in (get_user_profiles() or []):
            if not isinstance(p, dict):
                continue

            # 容错：缺字段/类型异常时也不要 500
            try:
                threshold = int(p.get("trust_threshold", 7) or 7)
            except Exception:
                threshold = 7

            if threshold <= 6:
                difficulty = "简单"
                difficulty_stars = 1
            elif threshold <= 8:
                difficulty = "中等"
                difficulty_stars = 2
            else:
                difficulty = "困难"
                difficulty_stars = 3

            pain_points = p.get("pain_points") or []
            if not isinstance(pain_points, list):
                pain_points = []

            profiles.append({
                **p,
                "trust_threshold": threshold,
                "pain_points": pain_points,
                "difficulty": difficulty,
                "difficulty_stars": difficulty_stars,
                "difficulty_level": _difficulty_level_from_threshold(threshold),
            })

        return jsonify(profiles)
    except Exception as e:
        print(f"[ERROR] /api/profiles 失败: {type(e).__name__}: {e}")
        traceback.print_exc()
        # 前端期望是数组，避免返回对象导致 .map 崩溃
        return jsonify([])


@app.route('/api/training/options')
def get_training_options_api():
    """获取可选场景/心理状态配置"""
    return jsonify(get_training_options())


@app.route('/api/session/start', methods=['POST'])
def start_session():
    """开始新的训练会话"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "请求体为空"}), 400
        profile_id = data.get('profile_id')
        scenario_id = data.get('scenario_id')
        mental_state_id = data.get('mental_state_id')
        
        print(f"[SESSION] 开始创建会话，profile_id={profile_id}")
        
        # 查找对应的用户画像
        profile = None
        for p in get_user_profiles():
            if p.get('id') == profile_id:
                profile = p
                break
        
        if not profile:
            return jsonify({"error": "用户画像不存在"}), 404

        # 选择场景/心理状态（支持 random / 未传 / profile默认）
        options = get_training_options()
        scenarios = options.get("scenarios", [])
        mental_states = options.get("mental_states", [])

        selected_scenario = None
        selected_mental_state = None

        if scenarios:
            if scenario_id in (None, "", "random"):
                scenario_id = profile.get("default_scenario_id") or "random"
            selected_scenario = find_by_id(scenarios, scenario_id) if scenario_id != "random" else None
            if selected_scenario is None:
                selected_scenario = random.choice(scenarios)

        if mental_states:
            if mental_state_id in (None, "", "random"):
                mental_state_id = profile.get("default_mental_state_id") or "random"
            selected_mental_state = find_by_id(mental_states, mental_state_id) if mental_state_id != "random" else None
            if selected_mental_state is None:
                selected_mental_state = random.choice(mental_states)
        
        # 创建新会话
        session_obj = TrainingSession(profile, scenario=selected_scenario, mental_state=selected_mental_state)
        active_sessions[session_obj.session_id] = session_obj
        
        # 生成用户开场白（带异常处理）
        try:
            opening = session_obj.simulator.get_opening_message()
        except Exception as e:
            print(f"[ERROR] 生成开场白失败: {str(e)}")
            # 使用默认开场白
            opening = {
                "response": f"你好，我是{profile['name']}，{profile['trigger_scenario']}，但是我不太懂这些东西...",
                "inner_thought": "希望能有人帮我解答疑惑"
            }
        
        session_obj.messages.append({
            "role": "user",  # 这里user指的是模拟的小白用户
            "content": opening["response"],
            "inner_thought": opening.get("inner_thought", "")
        })
        session_obj.started = True
        
        return jsonify({
            "session_id": session_obj.session_id,
            "profile": profile,
            "scenario": selected_scenario,
            "mental_state": selected_mental_state,
            "opening_message": opening["response"],
            "inner_thought": opening.get("inner_thought", ""),
            "status": session_obj.to_dict()
        })
    except Exception as e:
        print(f"[ERROR] start_session异常: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": f"启动会话失败: {str(e)}"}), 500


@app.route('/api/session/<session_id>/chat', methods=['POST'])
def chat(session_id):
    """发送消息"""
    try:
        if session_id not in active_sessions:
            return jsonify({"error": "会话不存在"}), 404
        
        session_obj = active_sessions[session_id]
        data = request.json
        pm_message = data.get('message', '').strip()
        
        if not pm_message:
            return jsonify({"error": "消息不能为空"}), 400
        
        # 记录PM的消息
        session_obj.messages.append({
            "role": "pm",
            "content": pm_message
        })
        session_obj.turn_count += 1
        
        # 获取用户回复（带异常处理）
        try:
            response = session_obj.simulator.respond(pm_message)
        except Exception as e:
            print(f"[ERROR] 获取用户回复失败: {str(e)}")
            # 返回默认回复
            response = {
                "response": "嗯...让我想想...",
                "inner_thought": "（系统处理中）",
                "trust_change": 0,
                "concern_addressed": None,
                "willing_to_continue": True,
                "ready_to_open_account": False
            }
        
        # 记录用户回复
        session_obj.messages.append({
            "role": "user",
            "content": response["response"],
            "inner_thought": response.get("inner_thought", ""),
            "trust_change": response.get("trust_change", 0)
        })
        
        # 检查会话状态
        is_ended = False
        end_reason = None
        end_detail: dict = {}
        
        if session_obj.simulator.is_convinced:
            is_ended = True
            end_reason = "success"
        elif not response.get("willing_to_continue", True):
            is_ended = True
            end_reason = "user_quit"
            # 透传更具体的“失去兴趣原因”
            qr = response.get("quit_reason")
            qe = response.get("quit_explanation")
            if qr:
                end_detail["quit_reason"] = qr
            if qe:
                end_detail["quit_explanation"] = qe
            end_detail["final_trust"] = session_obj.simulator.trust_level
            end_detail["last_trust_change"] = response.get("trust_change", 0)
            end_detail["turn"] = session_obj.turn_count
        else:
            # 1) 信任度满分：直接结算（视为训练目标达成的一种）
            if int(session_obj.simulator.trust_level) >= 10:
                is_ended = True
                end_reason = "trust_full"
                end_detail["final_trust"] = session_obj.simulator.trust_level
                end_detail["turn"] = session_obj.turn_count

            # 2) 顾虑全部解答：直接结算（视为训练目标达成的一种）
            if not is_ended:
                try:
                    total_concerns = len(session_obj.profile.get("pain_points") or [])
                except Exception:
                    total_concerns = 0
                addressed = len(session_obj.simulator.concerns_addressed or [])
                if total_concerns > 0 and addressed >= total_concerns:
                    is_ended = True
                    end_reason = "concerns_full"
                    end_detail["concerns_addressed"] = addressed
                    end_detail["total_concerns"] = total_concerns
                    end_detail["turn"] = session_obj.turn_count

            max_turns = (get_goals_config().get("end_conditions") or {}).get("max_turns", 20)
            if session_obj.turn_count >= int(max_turns):
                is_ended = True
                end_reason = "max_turns"
                end_detail["turn"] = session_obj.turn_count

        if is_ended:
            session_obj.end_reason = end_reason
            session_obj.end_detail = end_detail
        
        return jsonify({
            "response": response["response"],
            "inner_thought": response.get("inner_thought", ""),
            "trust_change": response.get("trust_change", 0),
            "concern_addressed": response.get("concern_addressed"),
            "is_ended": is_ended,
            "end_reason": end_reason,
            "end_detail": end_detail,
            "status": session_obj.to_dict()
        })
    except Exception as e:
        print(f"[ERROR] chat异常: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": f"对话处理失败: {str(e)}"}), 500


@app.route('/api/session/<session_id>/evaluate', methods=['POST'])
def evaluate(session_id):
    """评估训练结果"""
    try:
        if session_id not in active_sessions:
            return jsonify({"error": "会话不存在"}), 404
        
        session_obj = active_sessions[session_id]
        evaluator = ConversationEvaluator(
            criteria=get_evaluation_criteria_config(),
            scoring_rules=get_scoring_rules(),
            goals_config=getattr(session_obj, "effective_goals_config", None) or get_goals_config(),
        )
        
        try:
            evaluation = evaluator.evaluate(
                session_obj.simulator.conversation_history,
                session_obj.profile,
                session_obj.simulator.trust_level,
                session_obj.simulator.is_convinced,
                session_obj.simulator.concerns_addressed,
                session_obj.turn_count,
                scenario=session_obj.scenario,
                mental_state=session_obj.mental_state,
                end_reason=session_obj.end_reason,
                end_detail=session_obj.end_detail,
            )
        except Exception as e:
            print(f"[ERROR] 评估失败: {str(e)}")
            # 返回默认评估
            evaluation = {
                "scores": {"communication_skills": 60, "empathy": 60, "problem_solving": 60, "persuasion": 60, "professionalism": 60},
                "total_score": 60,
                "highlights": ["完成了训练对话"],
                "improvements": ["继续练习以提升表现"],
                "key_insights": "持续练习可以提升用户感知能力",
                "overall_comment": "继续加油！"
            }
        
        # 添加会话统计
        evaluation["stats"] = {
            "turn_count": session_obj.turn_count,
            "final_trust": session_obj.simulator.trust_level,
            "trust_threshold": session_obj.profile["trust_threshold"],
            "is_convinced": session_obj.simulator.is_convinced,
            "concerns_addressed": len(session_obj.simulator.concerns_addressed),
            "total_concerns": len(session_obj.profile["pain_points"]),
            "end_reason": session_obj.end_reason,
            "end_detail": session_obj.end_detail,
        }
        
        return jsonify(evaluation)
    except Exception as e:
        print(f"[ERROR] evaluate异常: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": f"评估处理失败: {str(e)}"}), 500


@app.route('/api/session/<session_id>/status')
def get_status(session_id):
    """获取会话状态"""
    if session_id not in active_sessions:
        return jsonify({"error": "会话不存在"}), 404
    
    session_obj = active_sessions[session_id]
    return jsonify(session_obj.to_dict())


@app.route('/api/evaluation-criteria')
def get_evaluation_criteria_api():
    """获取评估标准"""
    return jsonify(get_evaluation_criteria_config())


@app.route('/api/llm/status')
def llm_status():
    """
    诊断接口：查看当前 LLM 配置是否生效（不会返回明文 key）
    - remote.key_configured: 是否读取到 LLM_API_KEY（或其兼容变量）
    - ollama.reachable: 本地 Ollama 是否可访问
    """
    remote_url = (LLM_CONFIG.get("url") or "").strip()
    remote_model = (LLM_CONFIG.get("model") or "").strip()
    remote_key = (LLM_CONFIG.get("api_key") or "").strip()

    ollama_base = (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
    ollama_model = (os.getenv("OLLAMA_MODEL") or "qwen2.5:7b-instruct").strip()
    ollama_reachable = False
    ollama_err = ""
    try:
        r = requests.get(f"{ollama_base}/api/tags", timeout=2)
        ollama_reachable = (r.status_code == 200)
        if not ollama_reachable:
            ollama_err = f"HTTP {r.status_code}"
    except Exception as e:
        ollama_err = f"{type(e).__name__}: {e}"

    return jsonify({
        "remote": {
            "url": remote_url,
            "model": remote_model,
            "key_configured": bool(remote_key),
        },
        "ollama": {
            "base_url": ollama_base,
            "model": ollama_model,
            "reachable": ollama_reachable,
            "error": ollama_err if not ollama_reachable else "",
        },
    })


if __name__ == '__main__':
    # use_reloader=False 避免热重载导致会话丢失
    app.run(debug=True, host='0.0.0.0', port=8080, use_reloader=False)
