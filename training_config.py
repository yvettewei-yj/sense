"""
训练配置加载器

目标：
- 让用户画像/场景/心理状态/通关条件/评分规则可配置
- 默认从 training_config.json 读取；读取失败时回退到 config.py 中的常量
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from config import USER_PROFILES as LEGACY_USER_PROFILES
from config import EVALUATION_CRITERIA as LEGACY_EVALUATION_CRITERIA


_CACHE: Optional[Dict[str, Any]] = None


def _default_config() -> Dict[str, Any]:
    return {
        "version": 1,
        "profiles": LEGACY_USER_PROFILES,
        "scenarios": [],
        "mental_states": [],
        "goals": {
            "end_conditions": {
                "max_turns": 20,
                # 当信任度低于该阈值时，用户会“失去兴趣/不愿继续”
                # 说明：当前初始信任度为 1，若你希望更容易触发，可提高初始信任度或将该值设为 1+
                "min_trust_to_continue": 0,
            },
            "success_conditions": {
                "requires_ready_to_open_account": True,
                "min_concerns_addressed": 0,
                "trust_at_least_profile_threshold": True,
            },
            # 按难度覆盖通关条件（评估标准不变，只是“是否通关”的判定更贴合难度）
            "success_conditions_by_difficulty": {
                "easy": {
                    "requires_ready_to_open_account": False,
                    "min_concerns_addressed": 1,
                    "trust_at_least_profile_threshold": False,
                    # easy 使用固定门槛，避免 profile trust_threshold（例如 5）在本地模型下过难达成
                    "min_trust_level": 3,
                },
                "medium": {
                    "requires_ready_to_open_account": False,
                    "min_concerns_addressed": 2,
                    "trust_at_least_profile_threshold": True,
                },
                "hard": {
                    "requires_ready_to_open_account": True,
                    "min_concerns_addressed": 2,
                    "trust_at_least_profile_threshold": True,
                },
            },
        },
        "evaluation_criteria": LEGACY_EVALUATION_CRITERIA,
        "scoring_rules": {
            "base_score": 50,
            "success_bonus": 20,
            "trust_point_per_level": 2,
            "concern_addressed_bonus": 5,
            "fast_success_turns_threshold": 10,
            "fast_success_bonus": 10,
            "max_total_score": 100,
            "bonuses": [],
            "penalties": [],
        },
    }


def get_config_path() -> str:
    """
    配置文件优先级：
    1) 环境变量 PMTRAINER_CONFIG_PATH
    2) 项目根目录 training_config.json
    """
    env_path = os.environ.get("PMTRAINER_CONFIG_PATH")
    if env_path:
        return env_path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "training_config.json")


def load_training_config(force_reload: bool = False) -> Dict[str, Any]:
    global _CACHE
    if _CACHE is not None and not force_reload:
        return _CACHE

    cfg = _default_config()
    path = get_config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            disk_cfg = json.load(f)
        if isinstance(disk_cfg, dict):
            cfg.update(disk_cfg)
    except Exception as e:
        # 读取失败：回退到默认（legacy）
        print(f"[CONFIG] 读取训练配置失败，将使用默认配置: path={path}, err={type(e).__name__}: {e}")

    # 最小兜底：关键字段存在
    cfg.setdefault("profiles", [])
    cfg.setdefault("scenarios", [])
    cfg.setdefault("mental_states", [])
    cfg.setdefault("goals", _default_config()["goals"])
    cfg.setdefault("evaluation_criteria", LEGACY_EVALUATION_CRITERIA)
    cfg.setdefault("scoring_rules", _default_config()["scoring_rules"])

    _CACHE = cfg
    return cfg


def get_user_profiles() -> List[Dict[str, Any]]:
    cfg = load_training_config()
    profiles = cfg.get("profiles") or []
    return profiles if isinstance(profiles, list) else []


def get_training_options() -> Dict[str, List[Dict[str, Any]]]:
    cfg = load_training_config()
    scenarios = cfg.get("scenarios") or []
    mental_states = cfg.get("mental_states") or []
    return {
        "scenarios": scenarios if isinstance(scenarios, list) else [],
        "mental_states": mental_states if isinstance(mental_states, list) else [],
    }


def get_evaluation_criteria() -> Dict[str, Dict[str, Any]]:
    cfg = load_training_config()
    criteria = cfg.get("evaluation_criteria") or {}
    return criteria if isinstance(criteria, dict) else LEGACY_EVALUATION_CRITERIA


def get_goals_config() -> Dict[str, Any]:
    cfg = load_training_config()
    goals = cfg.get("goals") or {}
    return goals if isinstance(goals, dict) else _default_config()["goals"]


def get_scoring_rules() -> Dict[str, Any]:
    cfg = load_training_config()
    scoring = cfg.get("scoring_rules") or {}
    return scoring if isinstance(scoring, dict) else _default_config()["scoring_rules"]


def find_by_id(items: List[Dict[str, Any]], item_id: Any) -> Optional[Dict[str, Any]]:
    for it in items:
        if it.get("id") == item_id:
            return it
    return None

